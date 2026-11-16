"""May git read this clone's index without writing into the clone?

Three git commands read the index (status, diff-index, ls-files). Reading
writes in some index states: a split index re-dates its
``sharedindex.<sha>`` (git's ``freshen_shared_index`` on every read), a
sparse index is expanded and its tree objects written. Before those
commands run, the engine inspects the index itself, wherever the working
tree's git directory is (also above the scan root, for a subdirectory
scan): a bounded, regular-file-only, no-follow, non-blocking read of its
layout (``git_index_layout``), used only to decide this refusal, never put
into a map. Only that inspection can allow git to read the index; the
clone's config never does. The git directory and the object format are
found from the file system (``git_dir_discovery``) and confirmed by git,
one value per call. Refused: an unclear git directory or object format
(missing, malformed or disagreeing answers), no index, not a regular file,
larger than :data:`MAX_INDEX_BYTES`, not parsable, an ``EOIE`` that does
not agree with the walk (:data:`LAYOUT_AMBIGUOUS`; ``git_index_eoie``), a
split (``link``), sparse (``sdir``) or other mandatory extension. A refused
index means no dirty-tree detection, recorded in ``scan_meta.index_unread``.
"""

from __future__ import annotations

import errno
import functools
import os
import stat
from pathlib import Path

from wystan.analyzer.git_dir_discovery import (
    configured_object_format,
    discovered_git_dir,
    has_unsafe_characters,
    is_plain_directory,
    one_value,
)
from wystan.analyzer.git_index_eoie import check_eoie
from wystan.analyzer.git_index_layout import AmbiguousIndex, index_layout
from wystan.analyzer.path_identity import is_within
from wystan.analyzer.repo_boundary import boundary_of
from wystan.analyzer.repo_open import (
    _EXHAUSTED_ERRNOS,
    FILE_FLAGS,
    DescriptorsExhausted,
    open_contained,
)

#: Larger than any real index (posthog's 70k entries: a few MiB); a larger
#: one is not read at all.
MAX_INDEX_BYTES = 256 << 20
#: git's object format -> object id length in bytes.
_OID_BYTES_BY_FORMAT = {"sha1": 20, "sha256": 32}
_SPLIT, _SPARSE = b"link", b"sdir"
#: The refusal of an index git could read differently from the engine.
LAYOUT_AMBIGUOUS = "index_layout_ambiguous"
_NO_FOLLOW = getattr(os, "O_NOFOLLOW", 0)


def _single_answer(root: str, flag: str) -> str | None:
    """git's one-value answer to ``rev-parse <flag>``: exactly one line,
    no other line break, no NUL; ``None`` for anything else."""
    from wystan.analyzer.git_runner import GitError, run_git  # the runner imports this module

    try:
        found = run_git(root, "rev-parse", flag, check=False)
    except GitError:
        return None
    return one_value(found.stdout) if found.returncode == 0 else None


class _Unclear(Exception):
    """The git directory or its object format is not certain: refused."""


def repository_facts(root: str) -> tuple[str, str] | None:
    """(git directory, object format) the index inspection uses: found
    from the file system, each confirmed by git in a call of its own.
    ``None`` when neither finds a repository; :class:`_Unclear` with the
    reason for a missing, malformed or disagreeing answer."""
    found_dir = discovered_git_dir(root)
    answered_dir = _single_answer(root, "--absolute-git-dir")
    if found_dir is None and answered_dir is None:
        return None
    if found_dir is None or answered_dir is None:
        raise _Unclear(f"git directory unclear (found {found_dir!r}, git answered {answered_dir!r})")
    if has_unsafe_characters(found_dir) or os.path.realpath(found_dir) != os.path.realpath(answered_dir):
        raise _Unclear(f"git directory unclear (found {found_dir!r}, git answered {answered_dir!r})")
    if not is_plain_directory(found_dir):
        raise _Unclear(f"git directory {found_dir!r} is not a directory")
    configured = configured_object_format(found_dir, root)
    answered = _single_answer(root, "--show-object-format")
    if configured is None or configured != answered:
        raise _Unclear(f"object format unclear (config {configured!r}, git answered {answered!r})")
    return found_dir, configured


def _open_above_root(index: str, before: os.stat_result) -> int:
    """The index of a working tree whose git directory lies above the scan
    root: opened without following a link and without blocking, and only
    when it is still the regular file that was examined."""
    try:
        fd = os.open(index, FILE_FLAGS | _NO_FOLLOW)
    except OSError as exc:
        if exc.errno in _EXHAUSTED_ERRNOS:
            raise DescriptorsExhausted(f"no file descriptor left to inspect {index}") from exc
        raise
    after = os.fstat(fd)
    if not stat.S_ISREG(after.st_mode) or (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino):
        os.close(fd)
        raise OSError(errno.EACCES, "the index changed while it was inspected", index)
    return fd


def _open_index(index: str, root: str, before: os.stat_result) -> int:
    if is_within(index, root):
        # Inside the scan root: the guarded reader's open (no link out of
        # the root, regular files only, non-blocking).
        return open_contained(Path(index), boundary_of(root))
    return _open_above_root(index, before)


@functools.lru_cache(maxsize=64)
def _inspected_refusal(index: str, identity: tuple[int, int, int, int], oid_bytes: int, root: str) -> str | None:
    """The refusal for the index file ``identity`` (dev, inode, size,
    mtime) names; cached per identity, so one scan inspects it once."""
    try:
        fd = _open_index(index, root, os.lstat(index))
    except OSError as exc:
        return f"index not readable ({exc.strerror or exc})"
    try:
        layout = index_layout(fd, identity[2], oid_bytes)
        if layout is not None:
            check_eoie(fd, identity[2], oid_bytes, layout)
    except AmbiguousIndex as exc:
        return f"{LAYOUT_AMBIGUOUS} ({exc})"
    except OSError as exc:
        return f"index not readable ({exc.strerror or exc})"
    finally:
        os.close(fd)
    if layout is None:
        return "index does not parse"
    return _extension_refusal(layout.extensions)


def _extension_refusal(extensions: frozenset[bytes]) -> str | None:
    if _SPLIT in extensions:
        return "split index (git re-dates its shared index file on every read)"
    if _SPARSE in extensions:
        return "sparse index (git writes tree objects when it expands it)"
    # A lowercase first letter marks an extension git must understand; an
    # unknown one could change how git reads the index.
    mandatory = sorted(name for name in extensions if name[:1].islower())
    if mandatory:
        return f"unknown mandatory index extension {mandatory[0]!r}"
    return None


def _shared_index_present(found_dir: str) -> bool:
    try:
        return any(name.startswith("sharedindex.") for name in os.listdir(found_dir))
    except OSError:
        return False


def index_refusal(root: str) -> str | None:
    """Why the clone's index must not be read, or ``None`` when it may be:
    only after the engine inspected it and found an ordinary index. Not a
    repository by both the file system and git: ``None`` (git refuses the
    command itself). Every unclear answer is a refusal."""
    try:
        facts = repository_facts(root)
    except _Unclear as exc:
        return str(exc)
    if facts is None:
        return None
    found_dir, found_format = facts
    if _shared_index_present(found_dir):
        return "split index (sharedindex file present)"
    index = os.path.join(found_dir, "index")
    try:
        info = os.lstat(index)
    except FileNotFoundError:
        # A refusal, though git would read a missing index as empty: with no
        # index the engine cannot tell staged from committed, so the
        # identity keys on the files (``unread:``; a bare repository, with
        # no work tree, is ``vcs: none``) instead of "clean". A clone always
        # writes an index, so this is a work tree whose index was removed,
        # or a bare repository. Neither stops the scan;
        # ``scan_meta.index_unread`` says "no index file".
        return "no index file"
    except OSError as exc:
        return f"index not readable ({exc.strerror or exc})"
    if not stat.S_ISREG(info.st_mode):
        return "index is not a regular file"
    if info.st_size > MAX_INDEX_BYTES:
        return f"index larger than {MAX_INDEX_BYTES} bytes"
    oid_bytes = _OID_BYTES_BY_FORMAT.get(found_format)
    if oid_bytes is None:
        return f"unknown object format ({found_format or 'none reported'})"
    identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    return _inspected_refusal(index, identity, oid_bytes, os.path.realpath(root))
