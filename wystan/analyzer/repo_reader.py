"""Bounded, contained reads of one file of an untrusted repository.

The one reader every read of a repository path goes through. It never opens
what a scanned repository must not make the engine open:

* The caller passes the repository root and a path relative to it; an
  absolute path or one with a ``..`` segment is refused (``repo_path``).
* Containment (``analyzer.safe_read``, switch ``WYSTAN_SYMLINK_CONTAINMENT``,
  default on): the path is resolved; it must resolve inside the boundary of
  the root (``repo_boundary``: the root itself, or the repository the user
  passed for a ``--subpath`` subtree; never anything above). The file is then
  opened beneath the boundary without following a link swapped in
  (``repo_open``: the ``dir_fd`` path, or where the platform lacks it the
  fallback, whose remaining race that module states). An in-repository link
  is read as the file it resolves to.
* Only a regular file is read: ``lstat`` refuses anything else before the
  open, the open is non-blocking (a FIFO swapped in never blocks), and
  ``fstat`` on the descriptor checks again. A device swapped in at the last
  moment is opened (never read).
* The head (``SNIFF_BYTES``) is read first; a binary file can stop there.
* At most ``max_bytes`` are read (default ``MAX_FILE_BYTES``), checked on the
  descriptor's size and again while reading (a file that grows).
* Every refusal (not a missing file, not a binary head) is recorded for the
  scan's ``scan_meta.repository_reads`` (``repo_read_tally``).

Not closed by any reader: a hard link inside the repository to a file
outside it (same inode; git never creates one).
"""

from __future__ import annotations

import os
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Iterator

from wystan.analyzer.repo_boundary import boundary_of
from wystan.analyzer.repo_read_tally import (
    REASON_NOT_REGULAR,
    REASON_OPEN_ERROR,
    REASON_OUTSIDE,
    REASON_OVER_CAP,
    record_refusal,
)
from wystan.analyzer.repo_open import (
    FILE_FLAGS,
    NotRegularFile,
    OutsideRepository,
    open_contained,
    symlink_containment_enabled,
)

__all__ = [
    "MANIFEST_READ_MAX_BYTES",
    "MAX_FILE_BYTES",
    "REFUSED_BINARY",
    "REFUSED_MISSING",
    "REFUSED_NOT_REGULAR",
    "REFUSED_OPEN_ERROR",
    "REFUSED_OUTSIDE",
    "REFUSED_OVER_CAP",
    "SNIFF_BYTES",
    "TEXT_READ_MAX_BYTES",
    "FileBytes",
    "open_repo_file",
    "read_repo_bytes",
    "repo_path",
    "require_repo_root",
]

#: Largest file a counting reader opens. The largest tracked text file on
#: the ten corpus clones is 10.7 MB (a bundled script); six times that keeps
#: every file the map has ever counted and bounds what a crafted file costs.
MAX_FILE_BYTES = 64 * 1024 * 1024
#: Cap of a text read whose purpose sets no tighter bound (a source file, a
#: catalog). The same as the line counters' cap: the largest tracked text
#: file on the corpus is 10.7 MB.
TEXT_READ_MAX_BYTES = MAX_FILE_BYTES
#: Cap of a manifest or config read (package.json, tsconfig, Cargo.toml,
#: go.mod, pyproject.toml, workspace files, git config). The largest such
#: tracked file on the 27 corpus clones is 84 KB; 4 MiB is fifty times that.
#: The smallest cap the guard sets: a smaller ``max_bytes`` is a call site's
#: own work bound (it skipped the same files before the guard), and a file
#: over it is not reported as a refusal.
MANIFEST_READ_MAX_BYTES = 4 * 1024 * 1024
#: Head inspected for a NUL byte before a file is read on (the line count's
#: binary sniff has always read this much). The one copy of this number.
SNIFF_BYTES = 8192
#: Why a read returned no bytes.
REFUSED_MISSING = "missing_on_disk"
REFUSED_OUTSIDE = "symlink_outside_repo"
REFUSED_NOT_REGULAR = "not_regular_file"
REFUSED_OVER_CAP = "over_read_cap"
REFUSED_BINARY = "binary_content"
REFUSED_OPEN_ERROR = "open_error"
_READ_CHUNK = 1 << 20


@dataclass(frozen=True)
class FileBytes:
    """The bytes of a file, or why it was not read (``REFUSED_*``)."""

    data: bytes | None
    refused: str | None


def repo_path(repo_root: os.PathLike[str] | str, rel_path: str) -> Path | None:
    """``repo_root / rel_path``, or ``None`` for a path that cannot name a
    file of the repository (absolute, or with a ``..`` segment)."""
    rel = str(rel_path or "").replace("\\", "/")
    parts = PurePath(rel).parts
    if not rel or os.path.isabs(rel) or rel.startswith("/") or ".." in parts:
        return None
    return Path(repo_root) / rel


_roots_checked: set[str] = set()


def require_repo_root(repo_root: os.PathLike[str] | str, signature: str) -> None:
    """Raise ``TypeError`` when ``repo_root`` exists and is not a directory.

    For readers whose first argument changed meaning from a file path to the
    repository root while keeping its position: a call written for the old
    signature (``count_file_loc(root / rel, rel)``) passes an existing file
    and would otherwise count nothing, silently. A root that does not exist
    (a fixture's ``/repo``, a replay without its clone) holds no file to
    read, so the reader returns what it returned for a missing file, as
    ``dev`` did; an old-style call naming a missing file gave 0 on ``dev``
    too. Checked once per root and process."""
    raw = os.fspath(repo_root)
    if raw in _roots_checked:
        return
    if os.path.isdir(raw):
        _roots_checked.add(raw)
    elif os.path.exists(raw):
        raise TypeError(f"{signature}: the first argument must be the repository root directory, got {raw!r}")


def _open_uncontained(path: str) -> tuple[int | None, str | None]:
    """The kill switch: legacy reads; the file type and the cap still hold."""
    try:
        link = os.lstat(path)
    except OSError:
        return None, REFUSED_MISSING
    if not stat.S_ISLNK(link.st_mode) and not stat.S_ISREG(link.st_mode):
        return None, REFUSED_NOT_REGULAR
    try:
        return os.open(path, FILE_FLAGS), None
    except OSError:
        return None, REFUSED_OPEN_ERROR


def _open(path: str, repo_root: os.PathLike[str] | str) -> tuple[int | None, str | None]:
    """A descriptor for a regular-looking, contained file, or the refusal."""
    if not symlink_containment_enabled():
        return _open_uncontained(path)
    try:
        return open_contained(path, boundary_of(repo_root)), None
    except FileNotFoundError:
        return None, REFUSED_MISSING
    except NotRegularFile:
        return None, REFUSED_NOT_REGULAR
    except OutsideRepository:
        return None, REFUSED_OUTSIDE
    except OSError:
        return None, REFUSED_OPEN_ERROR


#: Refusals the scan reports (``repo_read_tally``); a missing file and a
#: binary head are not refusals.
_TALLIED = {
    REFUSED_OUTSIDE: REASON_OUTSIDE,
    REFUSED_NOT_REGULAR: REASON_NOT_REGULAR,
    REFUSED_OVER_CAP: REASON_OVER_CAP,
    REFUSED_OPEN_ERROR: REASON_OPEN_ERROR,
}


def _is_reported(path: os.PathLike[str] | str, reason: str, cap: int) -> bool:
    """Not reported, so an ordinary repository's map is unchanged: a
    directory where a file was expected (a probe that found nothing;
    ``read_text`` raised there too), and a file over a call site's own work
    bound below the guard's caps (the site skipped it before the guard)."""
    if reason == REASON_NOT_REGULAR:
        return not os.path.isdir(path)
    if reason == REASON_OVER_CAP:
        return cap >= MANIFEST_READ_MAX_BYTES
    return True


def _tally(path: os.PathLike[str] | str, repo_root: os.PathLike[str] | str, refused: str | None, cap: int) -> None:
    reason = _TALLIED.get(refused) if refused else None
    if reason is not None and _is_reported(path, reason, cap):
        record_refusal(path, repo_root, reason)


@contextmanager
def open_repo_file(
    path: os.PathLike[str] | str, repo_root: os.PathLike[str] | str, *, max_bytes: int | None = None,
) -> Iterator[tuple[int | None, int, str | None]]:
    """Yield ``(fd, size, refusal)``: a descriptor only for a regular file
    inside the repository of at most ``max_bytes`` (default
    ``MAX_FILE_BYTES``, read at call time); ``fd`` is ``None`` with the
    refusal otherwise. Rules: module doc."""
    cap = MAX_FILE_BYTES if max_bytes is None else max_bytes
    # Strings, not ``Path`` objects: building two per read cost more than
    # the system calls of the open.
    fd, refused = _open(os.fspath(path), repo_root)
    size = 0
    try:
        if fd is not None:
            opened = os.fstat(fd)
            size = opened.st_size
            if not stat.S_ISREG(opened.st_mode):
                refused = REFUSED_NOT_REGULAR
            elif size > cap:
                refused = REFUSED_OVER_CAP
        _tally(path, repo_root, refused, cap)
        yield (None if refused else fd), size, refused
    finally:
        if fd is not None:
            os.close(fd)


def _read_rest(fd: int, head: bytes, cap: int) -> FileBytes:
    chunks, total = [head], len(head)
    if total > cap:  # the file grew past the cap after fstat
        return FileBytes(None, REFUSED_OVER_CAP)
    while chunk := os.read(fd, min(_READ_CHUNK, cap + 1 - total)):
        chunks.append(chunk)
        total += len(chunk)
        if total > cap:
            return FileBytes(None, REFUSED_OVER_CAP)
    return FileBytes(b"".join(chunks), None)


def read_repo_bytes(
    path: os.PathLike[str] | str, repo_root: os.PathLike[str] | str, *,
    max_bytes: int | None = None, stop_at_binary: bool = True,
) -> FileBytes:
    """All bytes of a regular file inside the repository, at most
    ``max_bytes`` (default ``MAX_FILE_BYTES``). With ``stop_at_binary`` a NUL
    byte in the first ``SNIFF_BYTES`` ends the read there
    (``REFUSED_BINARY``). Never raises."""
    cap = MAX_FILE_BYTES if max_bytes is None else max_bytes
    try:
        with open_repo_file(path, repo_root, max_bytes=cap) as (fd, _size, refused):
            if fd is None:
                return FileBytes(None, refused)
            head = os.read(fd, min(SNIFF_BYTES, cap + 1))
            if stop_at_binary and b"\x00" in head:
                return FileBytes(None, REFUSED_BINARY)
            read = _read_rest(fd, head, cap)
    except OSError:
        read = FileBytes(None, REFUSED_OPEN_ERROR)
    _tally(path, repo_root, read.refused, cap)  # growth past the cap, a failed read
    return read


# The drop-ins live in ``repo_text_reads`` (they use the reader above); their
# names are served from here too so call sites import one module. Resolved on
# first use (PEP 562), so either module may be imported first.
_TEXT_READS = frozenset({
    "read_repo_bytes_or_raise",
    "read_repo_head_or_raise",
    "read_repo_text_head_or_raise",
    "read_repo_text_or_raise",
})


def __getattr__(name: str):
    if name in _TEXT_READS:
        from wystan.analyzer import repo_text_reads

        return getattr(repo_text_reads, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
