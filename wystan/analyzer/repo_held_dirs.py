"""Directory descriptors the reader keeps between guarded reads.

Opening a file beneath the boundary costs one ``open`` per path component;
on macOS that was most of the reader's cost (seven opens per read on a
Stage 0 to 1 replay). The process therefore keeps the descriptors of the
directories it last read in, each opened beneath the boundary with
``O_NOFOLLOW`` at every component, and opens the next file of such a
directory with one ``openat``. Per-component no-follow is unchanged: a held
descriptor was obtained by the same no-follow walk.

Bounded per PROCESS, not per thread (``held_bound``: one eighth of the soft
``RLIMIT_NOFILE``, at least ``_HELD_FLOOR``, at most ``_HELD_CEILING``; 32 at
the macOS default of 256): a scan's worker threads share one store, so they
can never exhaust the descriptor limit between them. Least recently used
first out; only a descriptor no read is using is ever closed.

Leases: ``lease_dir`` hands a descriptor to one read and counts it as in use
until ``release``; eviction, a stale entry and ``release_idle`` close a
descriptor only when no read holds it, so no thread ever opens beneath a
descriptor another thread closed (whose number the system could reuse). When
the store is full of descriptors in use, the read gets a transient one,
closed by ``release``.

Freshness: before a held descriptor is used, the directory's path is
``lstat``-ed and must still be the held directory (device and inode); a
directory renamed away and recreated, or a repository replaced at its path,
is walked afresh. The window left is the one between that ``lstat`` and the
open, the same any open has.

Fork: a child process closes its copies of the held descriptors
(``os.register_at_fork``); descriptors are never inherited across ``exec``
(non-inheritable, PEP 446).
"""

from __future__ import annotations

import os
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable

__all__ = ["HeldDir", "held_bound", "lease_dir", "release", "release_idle"]

#: The share of the soft descriptor limit the store may hold: one eighth
#: leaves the rest to the scan's files in flight, git, caches and sockets.
_SHARE_OF_LIMIT = 8
#: Fewer than this and holding saves little; more than this and the store
#: costs memory with no measurable gain (a read uses one directory).
_HELD_FLOOR = 4
_HELD_CEILING = 64


@dataclass
class HeldDir:
    """One held directory descriptor, its identity, and the reads using it."""

    fd: int
    identity: tuple[int, int]
    users: int = 0
    retired: bool = False


_store: OrderedDict[tuple[str, tuple[str, ...]], HeldDir] = OrderedDict()
_lock = threading.Lock()


def held_bound() -> int:
    """How many directory descriptors the process may hold (module doc)."""
    try:
        import resource

        soft = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
    except (ImportError, OSError, ValueError):
        return _HELD_FLOOR
    if soft == resource.RLIM_INFINITY:
        return _HELD_CEILING
    return max(_HELD_FLOOR, min(_HELD_CEILING, soft // _SHARE_OF_LIMIT))


def _identity_of(found: os.stat_result) -> tuple[int, int]:
    return found.st_dev, found.st_ino


def _retire(key: tuple[str, tuple[str, ...]], entry: HeldDir) -> None:
    """Under the lock: forget ``entry``; close it once no read uses it."""
    del _store[key]
    entry.retired = True
    if entry.users == 0:
        os.close(entry.fd)


def _make_room() -> bool:
    """Under the lock: evict idle descriptors below the bound; ``False``
    when every held descriptor is in use."""
    bound = held_bound()
    while len(_store) >= bound:
        idle = next((key for key, entry in _store.items() if entry.users == 0), None)
        if idle is None:
            return False
        _retire(idle, _store[idle])
    return True


def _leased(key: tuple[str, tuple[str, ...]], identity: tuple[int, int]) -> HeldDir | None:
    """Under the lock: the held entry for ``key`` if it is still the
    directory at that path, now counted as in use."""
    entry = _store.get(key)
    if entry is None:
        return None
    if entry.identity != identity:
        _retire(key, entry)
        return None
    entry.users += 1
    _store.move_to_end(key)
    return entry


def lease_dir(real: str, dir_parts: tuple[str, ...], open_dir: Callable[[], int]) -> tuple[int, HeldDir | None]:
    """A descriptor of ``real/dir_parts`` for one read: a held one when it is
    still that directory, else ``open_dir()``'s, held when there is room.
    Pass the result to ``release``. ``OSError`` when the directory is gone."""
    key = (real, dir_parts)
    identity = _identity_of(os.lstat(os.path.join(real, *dir_parts)))
    with _lock:
        entry = _leased(key, identity)
    if entry is not None:
        return entry.fd, entry
    fd = open_dir()
    opened = _identity_of(os.fstat(fd))
    with _lock:
        if key in _store or not _make_room():
            return fd, None
        entry = _store[key] = HeldDir(fd, opened, users=1)
    return fd, entry


def release(fd: int, entry: HeldDir | None) -> None:
    """End a read's use of a descriptor from ``lease_dir``."""
    with _lock:
        if entry is None:
            os.close(fd)
            return
        entry.users -= 1
        if entry.retired and entry.users == 0:
            os.close(entry.fd)


def release_idle() -> int:
    """Close every held descriptor no read is using (the process ran out of
    descriptors); the number closed."""
    with _lock:
        idle = [key for key, entry in _store.items() if entry.users == 0]
        for key in idle:
            _retire(key, _store[key])
    return len(idle)


def _forget_in_child() -> None:
    # The child is single-threaded: no read is using any copy, and the lock
    # may have been held by another thread at the fork: replace it.
    global _lock
    _lock = threading.Lock()
    for entry in _store.values():
        os.close(entry.fd)
    _store.clear()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_forget_in_child)
