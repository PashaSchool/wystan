"""Open one file of a scanned repository without leaving the repository.

``open_contained(path, boundary)`` returns a descriptor of the file only when
the file lies inside the boundary (``repo_boundary``); it raises
``FileNotFoundError`` for a missing file, ``NotRegularFile`` for anything but
a regular file (checked before the open: a FIFO or device is never opened),
``OutsideRepository`` for a path that leaves the repository (or a link swapped
in while it is opened), and another ``OSError`` when the open itself fails.

Two open paths, chosen once per platform (``open_path()``):

* ``dir_fd`` (macOS, Linux): the boundary directory is opened, then every
  component beneath it with ``os.open(..., dir_fd=...)`` and ``O_NOFOLLOW``
  (directories ``O_DIRECTORY``), so the opened file lies beneath the boundary
  by construction; a link swapped in at any component fails the open. The
  components are first taken as the path spells them under the boundary (no
  ``realpath``: a read costs a few system calls). Only when one of them is a
  link, or the path has a ``..`` or is not spelled under the boundary, is the
  path resolved, required to resolve inside the boundary, and its resolved
  components opened the same way, so an in-repository link reads as the file
  it names. A thread keeps the descriptors of the directories it last read in
  (``repo_held_dirs``: per thread, bounded, keyed by the boundary's identity),
  so the next file of such a directory costs one ``fstatat`` and one
  ``openat``; the file type is checked on that ``fstatat`` (no follow) before
  the open.
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
import stat
from pathlib import Path

from wystan.analyzer.repo_boundary import Boundary
from wystan.analyzer.repo_held_dirs import HeldDirs, held_for

__all__ = [
    "FILE_FLAGS",
    "file_flags",
    "OPEN_PATH_DIR_FD",
    "OPEN_PATH_FALLBACK",
    "SYMLINK_CONTAINMENT_ENV",
    "NotRegularFile",
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
_HAS_DIR_FD = (os.open in os.supports_dir_fd and os.stat in os.supports_dir_fd
               and os.stat in os.supports_follow_symlinks)


class OutsideRepository(OSError):
    """The path leaves the repository, or a link was swapped in."""


class NotRegularFile(OSError):
    """The path names a FIFO, socket, device or directory."""


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


def _lexical_parts(path: Path, boundary: Boundary) -> tuple[str, ...] | None:
    """The components of ``path`` under the boundary as the path spells them,
    or ``None`` when it has a ``..`` (resolved instead: a ``..`` after a link
    goes where the link leads) or is not spelled under the boundary."""
    raw = os.fspath(path)
    if f"{os.sep}..{os.sep}" in f"{os.sep}{raw}{os.sep}":
        return None
    prefix = boundary.lexical.rstrip(os.sep) + os.sep
    absolute = os.path.abspath(raw)
    if not absolute.startswith(prefix):
        return None
    return tuple(absolute[len(prefix):].split(os.sep))


def _open_dir_beneath(real_root: Path | str, dir_parts: tuple[str, ...]) -> int:
    """A descriptor of ``real_root/dir_parts...`` opened without following
    any link beneath ``real_root``; ``OSError`` when a component is a link."""
    dir_fd = os.open(real_root, _BOUNDARY_FLAGS)
    try:
        for name in dir_parts:
            next_fd = os.open(name, _DIR_FLAGS, dir_fd=dir_fd)
            os.close(dir_fd)
            dir_fd = next_fd
    except BaseException:
        os.close(dir_fd)
        raise
    return dir_fd


def _open_beneath(real_root: Path | str, parts: tuple[str, ...]) -> int:
    """Open ``real_root/parts...`` without following any link on the way;
    ``OSError`` when a component is a link or missing."""
    dir_fd = _open_dir_beneath(real_root, parts[:-1])
    try:
        _require_regular_beneath(dir_fd, parts[-1])
        return os.open(parts[-1], FILE_FLAGS | _NO_FOLLOW, dir_fd=dir_fd)
    finally:
        os.close(dir_fd)


def _require_regular_beneath(dir_fd: int, name: str) -> None:
    """Refuse, before the open, a resolved target that is not a regular file
    (a link to a FIFO or device is never opened). A link here was swapped in
    after the resolution."""
    found = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    if stat.S_ISLNK(found.st_mode):
        raise OSError(errno.ELOOP, "a link was swapped in", name)
    if not stat.S_ISREG(found.st_mode):
        raise NotRegularFile(errno.EACCES, "not a regular file", name)


def _require_examinable(path: Path) -> None:
    """A path that cannot be examined counts as missing, as it always did.
    (Its type is checked on the resolved target, before the open.)"""
    try:
        os.lstat(path)
    except OSError as err:
        raise FileNotFoundError(errno.ENOENT, "cannot be examined", str(path)) from err


def _held_dir(held: HeldDirs, real_root: str, dir_parts: tuple[str, ...]) -> tuple[int, bool]:
    """``(descriptor of the directory, whether it was already held)``."""
    fd = held.get(dir_parts)
    if fd is not None:
        return fd, True
    fd = _open_dir_beneath(real_root, dir_parts)
    held.put(dir_parts, fd)
    return fd, False


def _open_in_held_dir(held: HeldDirs, boundary: Boundary, parts: tuple[str, ...]) -> int | None:
    """Open the file ``parts[-1]`` in its held directory; ``None`` when a
    component is a link (resolve instead)."""
    dir_fd, was_held = _held_dir(held, boundary.real, parts[:-1])
    try:
        found = os.stat(parts[-1], dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        if not was_held:
            raise
        held.drop(parts[:-1])  # the held directory was replaced: walk again
        return _open_in_held_dir(held, boundary, parts)
    if stat.S_ISLNK(found.st_mode):
        return None
    if not stat.S_ISREG(found.st_mode):
        raise NotRegularFile(errno.EACCES, "not a regular file", parts[-1])
    return os.open(parts[-1], FILE_FLAGS | _NO_FOLLOW, dir_fd=dir_fd)


def _open_lexical(path: Path, boundary: Boundary) -> int | None:
    """The fast ``dir_fd`` open (module doc), or ``None`` to resolve."""
    parts = _lexical_parts(path, boundary)
    if parts is None:
        return None
    try:
        return _open_in_held_dir(held_for(boundary.real), boundary, parts)
    except OSError as err:
        if err.errno in _LINK_ERRNOS:
            return None
        raise


def _not_inside(path: Path, boundary: Boundary) -> OSError:
    """The refusal of a path that does not resolve strictly inside the
    boundary: the boundary directory itself is not a regular file (as a
    directory, it is not reported); anything else leaves the repository."""
    try:
        is_boundary = os.path.realpath(path) == boundary.real
    except (OSError, ValueError):
        is_boundary = False
    if is_boundary:
        return NotRegularFile(errno.EACCES, "the scanned directory itself", str(path))
    return OutsideRepository(errno.EACCES, "resolves outside the repository", str(path))


def _open_resolved(path: Path, boundary: Boundary) -> int:
    _require_examinable(path)
    resolved = _resolved_parts(path, boundary)
    if resolved is None:
        raise _not_inside(path, boundary)
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
    _require_examinable(path)
    resolved = _resolved_parts(path, boundary)
    if resolved is None:
        raise _not_inside(path, boundary)
    target = resolved[0].joinpath(*resolved[1])
    checked = os.stat(target)
    if not stat.S_ISREG(checked.st_mode):  # a link to a FIFO or device is never opened
        raise NotRegularFile(errno.EACCES, "not a regular file", str(path))
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
    fd = _open_lexical(path, boundary)
    return _open_resolved(path, boundary) if fd is None else fd
