"""Every location an untrusted tree could own, found without running git.

The runner must exclude these from git's search path BEFORE any git runs
(even the probe that asks git for its own view). Git's discovery is not
reproduced but over-approximated: from the scanned path up to the file
system root, every ancestor that holds a ``.git`` entry of any kind (file,
directory, symbolic link, valid or not) is a root, and so is each target a
``.git`` file (``gitdir:``), a ``.git`` link, or a ``commondir`` file names.
Git stops at the first valid repository; this walk never stops, so its set
is at least as wide (for exclusion, wider is the safe direction).

Pointer files are read like any repository file: ``lstat`` must say regular
file, the open is non-blocking and does not follow links, ``fstat`` must
agree, and at most ``POINTER_FILE_BYTES`` are read. A FIFO, a device, a
link or anything else reads as "no pointer" (its ancestor is still a root).
Replace ``read_pointer`` with ``wystan.analyzer.repo_reader`` once
``fix/guarded-repo-reads`` and this branch are both in ``dev``.
"""

from __future__ import annotations

import functools
import os
import stat

#: A ``.git`` file or ``commondir`` file is one short line; read no more.
POINTER_FILE_BYTES = 4096
_GITDIR_PREFIX = "gitdir:"
_DOT_GIT = ".git"
_COMMONDIR = "commondir"
_POINTER_FLAGS = (
    os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
)


def read_pointer(path: str) -> str | None:
    """The first line-ish content of a small regular file, or ``None``."""
    try:
        before = os.lstat(path)
        if not stat.S_ISREG(before.st_mode):
            return None
        fd = os.open(path, _POINTER_FLAGS)
    except OSError:
        return None
    try:
        after = os.fstat(fd)
        if not stat.S_ISREG(after.st_mode) or (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino):
            return None
        data = os.read(fd, POINTER_FILE_BYTES)
    except OSError:
        return None
    finally:
        os.close(fd)
    return data.decode("utf-8", "replace").strip()


def _common_dir(git_dir: str) -> list[str]:
    pointer = read_pointer(os.path.join(git_dir, _COMMONDIR))
    return [os.path.normpath(os.path.join(git_dir, pointer))] if pointer else []


def _entry_targets(ancestor: str, dot_git: str) -> list[str]:
    """What the ``.git`` entry of ``ancestor`` points at, besides itself."""
    try:
        mode = os.lstat(dot_git).st_mode
    except OSError:
        return []
    if stat.S_ISLNK(mode):
        target = os.path.realpath(dot_git)
        return [target, *_common_dir(target)]
    if stat.S_ISDIR(mode):
        return _common_dir(dot_git)
    pointer = read_pointer(dot_git)
    if pointer and pointer.startswith(_GITDIR_PREFIX):
        git_dir = os.path.normpath(os.path.join(ancestor, pointer[len(_GITDIR_PREFIX):].strip()))
        return [git_dir, *_common_dir(git_dir)]
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
            roots += [current, *_entry_targets(current, dot_git)]
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
