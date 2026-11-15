"""Directory descriptors a thread keeps between guarded reads.

Opening a file beneath the boundary costs one ``open`` per path component;
on macOS that was most of the reader's cost (seven opens per read on a
Stage 0 to 1 replay). A thread therefore keeps the descriptors of the
directories it last read in, each opened beneath the boundary with
``O_NOFOLLOW`` at every component, and opens the next file in such a
directory with one ``openat``. Per-component no-follow is unchanged: a held
descriptor was obtained by the same no-follow walk.

What holding changes: a directory replaced by a link after its descriptor is
held is not followed; the held directory (the one that was inside the
boundary) is read instead. Its contents are whatever that directory holds,
which only a process with write access to it can change.

Safety of the descriptors:

* Per thread (``threading.local``): a descriptor is used and closed only by
  the thread that opened it, so none is closed while another thread reads
  beneath it.
* Bounded (``_DIRS_HELD_PER_THREAD``), least recently used closed first.
* One boundary per thread at a time, keyed by the boundary's device and inode
  (``os.stat`` on every read): a repository replaced at its path (re-cloned in
  a long-lived process) or another boundary closes every held descriptor.
* Closed when the thread's store is collected (thread exit), and in a forked
  child (``os.register_at_fork``); never inherited by an exec'd child
  (descriptors are non-inheritable, PEP 446).
"""

from __future__ import annotations

import os
import threading
from collections import OrderedDict

__all__ = ["HeldDirs", "held_for"]

#: Directories a thread keeps open: enough for consecutive reads in one
#: directory and its neighbours, far below the default descriptor limit
#: (256 on macOS) times the scan's worker threads.
_DIRS_HELD_PER_THREAD = 32

_local = threading.local()


class HeldDirs:
    """The directory descriptors one thread holds beneath one boundary."""

    def __init__(self, real: str, identity: tuple[int, int]) -> None:
        self.real = real
        self.identity = identity
        self._fds: OrderedDict[tuple[str, ...], int] = OrderedDict()

    def get(self, parts: tuple[str, ...]) -> int | None:
        fd = self._fds.get(parts)
        if fd is not None:
            self._fds.move_to_end(parts)
        return fd

    def put(self, parts: tuple[str, ...], fd: int) -> None:
        self._fds[parts] = fd
        if len(self._fds) > _DIRS_HELD_PER_THREAD:
            _parts, oldest = self._fds.popitem(last=False)
            os.close(oldest)

    def drop(self, parts: tuple[str, ...]) -> None:
        fd = self._fds.pop(parts, None)
        if fd is not None:
            os.close(fd)

    def close(self) -> None:
        while self._fds:
            _parts, fd = self._fds.popitem()
            os.close(fd)

    def __del__(self) -> None:
        self.close()


def held_for(real: str) -> HeldDirs:
    """This thread's held directories beneath the boundary ``real``, emptied
    when the boundary at that path is not the one they were opened under."""
    found = os.stat(real)
    identity = (found.st_dev, found.st_ino)
    held = getattr(_local, "held", None)
    if held is None or held.real != real or held.identity != identity:
        if held is not None:
            held.close()
        held = _local.held = HeldDirs(real, identity)
    return held


def _forget_in_child() -> None:
    held = getattr(_local, "held", None)
    if held is not None:
        held.close()
        _local.held = None


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_forget_in_child)
