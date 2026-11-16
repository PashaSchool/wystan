"""Is a path inside a directory? Decided by file identity, not by spelling.

A string prefix is defeated by a case-insensitive file system (macOS,
Windows: ``/tmp/REPO`` is ``/tmp/repo``), by another spelling of the same
directory (a link, ``..``) and by a directory reached twice. Here the path
is resolved, and it and each of its parents is compared with the directory
by device and inode (what ``os.path.samefile`` compares). Results per
directory are remembered, so asking for every file of a repository costs
one ``stat`` per distinct directory.
"""

from __future__ import annotations

import os

#: Distinct (directory, container) answers remembered.
_MEMO_ENTRIES = 1 << 16


def _identity(path: str) -> tuple[int, int] | None:
    try:
        info = os.stat(path)
    except OSError:
        return None
    return info.st_dev, info.st_ino


_MEMO: dict[tuple[str, tuple[int, int]], bool] = {}


def _directory_within(directory: str, container: tuple[int, int]) -> bool:
    """``directory`` (resolved) or one of its parents is ``container``;
    every directory walked is remembered with the answer."""
    walked: list[str] = []
    current, found = directory, False
    while True:
        known = _MEMO.get((current, container))
        if known is not None:
            found = known
            break
        walked.append(current)
        if _identity(current) == container:
            found = True
            break
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    if len(_MEMO) + len(walked) > _MEMO_ENTRIES:
        _MEMO.clear()
    for path in walked:
        _MEMO[(path, container)] = found
    return found


def is_within(path: str, directory: str) -> bool:
    """``path`` is ``directory`` or lies under it, by identity."""
    container = _identity(directory)
    if container is None:
        return False
    real = os.path.realpath(path)
    if _identity(real) == container:
        return True
    return _directory_within(os.path.dirname(real), container)
