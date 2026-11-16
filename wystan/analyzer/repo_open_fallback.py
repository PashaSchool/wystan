"""The open path of ``repo_open`` where the platform has no ``dir_fd`` (or no
``O_NOFOLLOW``): resolve, require the resolved path inside the boundary,
``stat`` it (it must be a regular file: a link to a FIFO or device is never
opened), open it (``O_NOFOLLOW`` where defined), then require the
descriptor's device and inode to equal the checked target's, and resolve the
path again and require the same: still inside, and the file there is the
descriptor's. What remains: a parent directory swapped for a link out of the
repository before the first ``stat``, back before the second resolution, and
out again before the second ``stat`` (three swaps, each inside a window of a
few system calls) yields an outside file whose identity matches.
"""

from __future__ import annotations

import errno
import os
import stat
from pathlib import Path

from wystan.analyzer import repo_open as _opener
from wystan.analyzer.repo_boundary import Boundary

__all__ = ["open_checked"]


def _identity(found: os.stat_result) -> tuple[int, int]:
    return found.st_dev, found.st_ino


def _same_file_after_open(path: Path, boundary: Boundary, fd: int, checked: os.stat_result) -> None:
    """The checks after the open (module doc)."""
    opened = _identity(os.fstat(fd))
    again = _opener._resolve_inside(path, boundary)
    if opened != _identity(checked) or again is None or _identity(os.stat(again)) != opened:
        raise _opener.OutsideRepository(errno.EACCES, "the file changed while it was opened", str(path))


def open_checked(path: Path, boundary: Boundary) -> int:
    """Open the resolved path and prove it is the checked, contained file
    (module doc)."""
    _opener._require_examinable(path)
    resolved = _opener._resolved_parts(path, boundary)
    if resolved is None:
        raise _opener._not_inside(path, boundary)
    target = resolved[0].joinpath(*resolved[1])
    checked = os.stat(target)
    if not stat.S_ISREG(checked.st_mode):
        raise _opener.NotRegularFile(errno.EACCES, "not a regular file", str(path))
    fd = os.open(target, _opener.FILE_FLAGS | _opener._NO_FOLLOW)
    try:
        _same_file_after_open(path, boundary, fd, checked)
    except BaseException:
        os.close(fd)
        raise
    return fd
