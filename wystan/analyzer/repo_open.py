"""Open one file of a scanned repository without leaving the repository.

``open_contained(path, boundary)`` returns a descriptor of the file only when
the file lies inside the boundary (``repo_boundary``); it raises
``FileNotFoundError`` for a missing file, ``OutsideRepository`` for a path
that leaves the repository (or a link swapped in while it is opened), and
another ``OSError`` when the open itself fails.

Two open paths, chosen once per platform (``open_path()``):

* ``dir_fd`` (macOS, Linux): the boundary directory is opened, then every
  component beneath it with ``os.open(..., dir_fd=...)`` and ``O_NOFOLLOW``
  (directories ``O_DIRECTORY``), so the opened file lies beneath the boundary
  by construction; a link swapped in at any component fails the open. The
  path is resolved first and must resolve inside the boundary; its resolved
  components are opened, so an in-repository link reads as the file it names.
* ``fallback`` (no ``dir_fd`` or no ``O_NOFOLLOW``): resolve, require the resolved path
  inside the boundary, ``stat`` it, open it (``O_NOFOLLOW`` where defined),
  then require the descriptor's device and inode to equal the checked
  target's, and resolve the path again and require the same: still inside,
  and the file there is the descriptor's. What remains: a parent directory
  swapped for a link out of the repository before the first ``stat``, back
  before the second resolution, and out again before the second ``stat``
  (three swaps, each inside a window of a few system calls) yields an outside
  file whose identity matches. A hard link inside the repository to an outside
  file is indistinguishable on either path (git never creates one).
"""

from __future__ import annotations

import errno
import os
from pathlib import Path

from wystan.analyzer.repo_boundary import Boundary

__all__ = [
    "FILE_FLAGS",
    "file_flags",
    "OPEN_PATH_DIR_FD",
    "OPEN_PATH_FALLBACK",
    "SYMLINK_CONTAINMENT_ENV",
    "OutsideRepository",
    "open_contained",
    "open_path",
    "symlink_containment_enabled",
]

SYMLINK_CONTAINMENT_ENV = "WYSTAN_SYMLINK_CONTAINMENT"
_CONTAINMENT_ON = {"1", "true", "yes", "on"}
OPEN_PATH_DIR_FD = "dir_fd"
OPEN_PATH_FALLBACK = "fallback"
_NO_FOLLOW = getattr(os, "O_NOFOLLOW", 0)


def file_flags() -> int:
    """Flags of a file open. Non-blocking: a FIFO swapped in after the
    file-type check never blocks the open. Binary: on Windows a text-mode
    descriptor would translate CRLF and stop at 0x1A; the callers decode the
    bytes themselves."""
    return os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)


FILE_FLAGS = file_flags()
_DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | _NO_FOLLOW
#: The boundary itself may be reached through links above the repository
#: (``/var -> /private/var``): those are the user's, not the repository's.
_BOUNDARY_FLAGS = _DIR_FLAGS & ~_NO_FOLLOW
#: What ``O_NOFOLLOW`` raises on a link (``ENOTDIR`` with ``O_DIRECTORY``).
_LINK_ERRNOS = frozenset({errno.ELOOP, errno.ENOTDIR})
_HAS_DIR_FD = os.open in os.supports_dir_fd


class OutsideRepository(OSError):
    """The path leaves the repository, or a link was swapped in."""


def symlink_containment_enabled() -> bool:
    """Default ON. ``WYSTAN_SYMLINK_CONTAINMENT`` = ``0``/``false``/``off``/
    ``no``/``""`` turns containment off (the kill switch)."""
    return os.environ.get(SYMLINK_CONTAINMENT_ENV, "1").strip().lower() in _CONTAINMENT_ON


def _dir_fd_path_available() -> bool:
    # The descriptor walk is only as strong as ``O_NOFOLLOW``: without it a
    # link component would be followed, so the fallback's checks are used.
    return _HAS_DIR_FD and bool(_NO_FOLLOW)


def open_path() -> str:
    """Which open path this process uses (module doc)."""
    return OPEN_PATH_DIR_FD if _dir_fd_path_available() else OPEN_PATH_FALLBACK


def _resolve_inside(path: Path, boundary: Boundary) -> str | None:
    """``realpath(path)`` when it lies strictly inside the boundary."""
    try:
        real = os.path.realpath(path)
    except (OSError, ValueError, RuntimeError):
        return None
    prefix = boundary.real.rstrip(os.sep) + os.sep
    return real if real.startswith(prefix) else None


def _resolved_parts(path: Path, boundary: Boundary) -> tuple[Path, tuple[str, ...]] | None:
    """``(resolved boundary, components of the resolved path under it)``, or
    ``None`` when the path resolves outside the boundary (or loops)."""
    real = _resolve_inside(path, boundary)
    if real is None:
        return None
    parts = tuple(real[len(boundary.real.rstrip(os.sep)) + 1:].split(os.sep))
    return Path(boundary.real), parts


def _open_beneath(real_root: Path | str, parts: tuple[str, ...]) -> int:
    """Open ``real_root/parts...`` without following any link on the way;
    ``OSError`` when a component is a link or missing."""
    dir_fd = os.open(real_root, _BOUNDARY_FLAGS)
    try:
        for name in parts[:-1]:
            next_fd = os.open(name, _DIR_FLAGS, dir_fd=dir_fd)
            os.close(dir_fd)
            dir_fd = next_fd
        return os.open(parts[-1], FILE_FLAGS | _NO_FOLLOW, dir_fd=dir_fd)
    finally:
        os.close(dir_fd)


def _open_resolved(path: Path, boundary: Boundary) -> int:
    resolved = _resolved_parts(path, boundary)
    if resolved is None:
        raise OutsideRepository(errno.EACCES, "resolves outside the repository", str(path))
    try:
        return _open_beneath(*resolved)
    except OSError as err:
        if err.errno in _LINK_ERRNOS:  # a link swapped in after the resolution
            raise OutsideRepository(errno.EACCES, "a link was swapped in", str(path)) from err
        raise


def _identity(found: os.stat_result) -> tuple[int, int]:
    return found.st_dev, found.st_ino


def _same_file_after_open(path: Path, boundary: Boundary, fd: int, checked: os.stat_result) -> None:
    """The fallback's checks after the open (module doc)."""
    opened = _identity(os.fstat(fd))
    again = _resolve_inside(path, boundary)
    if opened != _identity(checked) or again is None or _identity(os.stat(again)) != opened:
        raise OutsideRepository(errno.EACCES, "the file changed while it was opened", str(path))


def _open_checked(path: Path, boundary: Boundary) -> int:
    """No ``dir_fd``: open the resolved path and prove it is the checked,
    contained file (module doc)."""
    resolved = _resolved_parts(path, boundary)
    if resolved is None:
        raise OutsideRepository(errno.EACCES, "resolves outside the repository", str(path))
    target = resolved[0].joinpath(*resolved[1])
    checked = os.stat(target)
    fd = os.open(target, FILE_FLAGS | _NO_FOLLOW)
    try:
        _same_file_after_open(path, boundary, fd, checked)
    except BaseException:
        os.close(fd)
        raise
    return fd


def open_contained(path: Path, boundary: Boundary) -> int:
    """A descriptor of ``path`` opened inside ``boundary`` (module doc)."""
    if not _dir_fd_path_available():
        return _open_checked(path, boundary)
    return _open_resolved(path, boundary)
