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
clone's config never does. Refused: no index, not a regular file, larger
than :data:`MAX_INDEX_BYTES`, not parsable, an object format the engine
does not know, a split (``link``) or sparse (``sdir``) index. A refused
index means no dirty-tree detection, recorded in ``scan_meta.index_unread``.
"""

from __future__ import annotations

import errno
import functools
import os
import stat
from pathlib import Path

from wystan.analyzer.git_index_layout import index_layout
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
_NO_FOLLOW = getattr(os, "O_NOFOLLOW", 0)


def repository_facts(root: str) -> tuple[str, str] | None:
    """(git directory, object format) as git finds them (no index read)."""
    from wystan.analyzer.git_runner import GitError, run_git  # the runner imports this module

    try:
        found = run_git(root, "rev-parse", "--absolute-git-dir", "--show-object-format", check=False)
    except GitError:
        return None
    lines = found.text.split("\n")
    if found.returncode != 0 or len(lines) < 2 or not lines[0].strip():
        return None
    return lines[0].strip(), lines[1].strip()


def git_dir(root: str) -> str | None:
    """The repository's git directory, as git finds it (no index read)."""
    facts = repository_facts(root)
    return facts[0] if facts else None


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
    except OSError as exc:
        return f"index not readable ({exc.strerror or exc})"
    finally:
        os.close(fd)
    if layout is None:
        return "index does not parse"
    if _SPLIT in layout.extensions:
        return "split index (git re-dates its shared index file on every read)"
    if _SPARSE in layout.extensions:
        return "sparse index (git writes tree objects when it expands it)"
    return None


def _shared_index_present(found_dir: str) -> bool:
    try:
        return any(name.startswith("sharedindex.") for name in os.listdir(found_dir))
    except OSError:
        return False


def index_refusal(root: str) -> str | None:
    """Why the clone's index must not be read, or ``None`` when it may be:
    only after the engine inspected it and found an ordinary index. Not a
    repository at all: ``None`` (git refuses the command itself)."""
    facts = repository_facts(root)
    if facts is None:
        return None
    found_dir, found_format = facts
    if _shared_index_present(found_dir):
        return "split index (sharedindex file present)"
    index = os.path.join(found_dir, "index")
    try:
        info = os.lstat(index)
    except FileNotFoundError:
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
