"""Every location an untrusted tree could own, found without running git.

The runner must exclude these from git's search path BEFORE any git runs
(even the probe that asks git for its own view). Git's discovery is not
reproduced but over-approximated: from the scanned path up to the file
system root, every ancestor that holds a ``.git`` entry of any kind (file,
directory, symbolic link, valid or not) is a root, and so is each target a
``.git`` file (``gitdir:``), a ``.git`` link, or a ``commondir`` file names.
Git stops at the first valid repository; this walk never stops, so its set
is at least as wide (for exclusion, wider is the safe direction).

Pointer files inside the scan root are read through the engine's guarded
reader (``repo_reader``, the root as its boundary). Pointer files outside it
(the ``.git`` entries of ancestors, and the git directories they name) are
read ONLY by the exclusion walk, whose reads can only widen the set of
locations no git is taken from: ``lstat`` must say regular file, the open
is non-blocking and does not follow links, ``fstat`` must agree, at most
``POINTER_FILE_BYTES`` are read (listed as ``above_scan_root`` in the read
guard's allowlist). A FIFO, a device, a link or anything else reads as "no
pointer" (its ancestor is still a root).
"""

from __future__ import annotations

import functools
import os
import stat

from wystan.analyzer.path_identity import is_within
from wystan.analyzer.repo_open import _EXHAUSTED_ERRNOS, DescriptorsExhausted
from wystan.analyzer.repo_reader import read_repo_bytes

#: A ``.git`` file or ``commondir`` file is one short line; read no more.
POINTER_FILE_BYTES = 4096
_GITDIR_PREFIX = "gitdir:"
_DOT_GIT = ".git"
_COMMONDIR = "commondir"
_POINTER_FLAGS = (
    os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
)


def read_pointer(path: str, root: str, limit: int = POINTER_FILE_BYTES) -> str | None:
    """The content (at most ``limit`` bytes) of a small regular file inside
    the scan root ``root``, read through the guarded reader; ``None`` when it
    is outside the root, missing, refused or larger."""
    if not is_within(path, root):
        return None
    read = read_repo_bytes(path, root, max_bytes=limit, stop_at_binary=False)
    return read.data.decode("utf-8", "replace").strip() if read.data is not None else None


def _read_outside(path: str, limit: int = POINTER_FILE_BYTES) -> str | None:
    """A pointer file outside the scan root, for the exclusion walk only."""
    try:
        before = os.lstat(path)
        if not stat.S_ISREG(before.st_mode):
            return None
        fd = os.open(path, _POINTER_FLAGS)
    except OSError as exc:
        if exc.errno in _EXHAUSTED_ERRNOS:
            raise DescriptorsExhausted(f"no file descriptor left to read {path}") from exc
        return None
    try:
        after = os.fstat(fd)
        if not stat.S_ISREG(after.st_mode) or (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino):
            return None
        data = os.read(fd, limit)
    except OSError:
        return None
    finally:
        os.close(fd)
    return data.decode("utf-8", "replace").strip()


def read_git_metadata(path: str, start: str, limit: int = POINTER_FILE_BYTES) -> str | None:
    """A small git metadata file (a ``.git`` pointer, ``commondir``, the
    repository config): inside the scan root through the guarded reader;
    outside it through the bounded read above, used only to decide what git
    may be allowed to do (exclusions, the index inspection), never put into
    a map."""
    return read_pointer(path, start, limit) if is_within(path, start) else _read_outside(path, limit)




def _common_dir(git_dir: str, start: str) -> list[str]:
    pointer = read_git_metadata(os.path.join(git_dir, _COMMONDIR), start)
    return [os.path.normpath(os.path.join(git_dir, pointer))] if pointer else []


def _entry_targets(ancestor: str, dot_git: str, start: str) -> list[str]:
    """What the ``.git`` entry of ``ancestor`` points at, besides itself."""
    try:
        mode = os.lstat(dot_git).st_mode
    except OSError:
        return []
    if stat.S_ISLNK(mode):
        target = os.path.realpath(dot_git)
        return [target, *_common_dir(target, start)]
    if stat.S_ISDIR(mode):
        return _common_dir(dot_git, start)
    pointer = read_git_metadata(dot_git, start)
    if pointer and pointer.startswith(_GITDIR_PREFIX):
        git_dir = os.path.normpath(os.path.join(ancestor, pointer[len(_GITDIR_PREFIX):].strip()))
        return [git_dir, *_common_dir(git_dir, start)]
    return []


@functools.lru_cache(maxsize=64)
def exclusion_roots(start: str) -> tuple[str, ...]:
    """The scanned path, every ancestor holding a ``.git`` entry, and every
    git directory those entries point at; the real path of ``start`` first."""
    roots = [os.path.realpath(start)]
    current = roots[0]
    while True:
        dot_git = os.path.join(current, _DOT_GIT)
        if os.path.lexists(dot_git):
            roots += [current, *_entry_targets(current, dot_git, roots[0])]
        parent = os.path.dirname(current)
        if parent == current:
            return tuple(dict.fromkeys(roots))
        current = parent


def topmost_repository_ancestor(start: str) -> str | None:
    """The highest ancestor of ``start`` holding a ``.git`` entry."""
    found = None
    current = os.path.realpath(start)
    while True:
        if os.path.lexists(os.path.join(current, _DOT_GIT)):
            found = current
        parent = os.path.dirname(current)
        if parent == current:
            return found
        current = parent
