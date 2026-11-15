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

Not closed by any reader: a hard link inside the repository to a file
outside it (same inode; git never creates one).
"""

from __future__ import annotations

import locale
import os
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Iterator

from wystan.analyzer.repo_boundary import boundary_of
from wystan.analyzer.repo_open import (
    FILE_FLAGS,
    NotRegularFile,
    OutsideRepository,
    open_contained,
    symlink_containment_enabled,
)

__all__ = [
    "MAX_FILE_BYTES",
    "REFUSED_BINARY",
    "REFUSED_MISSING",
    "REFUSED_NOT_REGULAR",
    "REFUSED_OPEN_ERROR",
    "REFUSED_OUTSIDE",
    "REFUSED_OVER_CAP",
    "SNIFF_BYTES",
    "FileBytes",
    "MANIFEST_READ_MAX_BYTES",
    "TEXT_READ_MAX_BYTES",
    "open_repo_file",
    "read_repo_bytes_or_raise",
    "read_repo_head_or_raise",
    "read_repo_text_or_raise",
    "read_repo_bytes",
    "repo_path",
]

#: Largest file a counting reader opens. The largest tracked text file on
#: the ten corpus clones is 10.7 MB (a bundled script); six times that keeps
#: every file the map has ever counted and bounds what a crafted file costs.
MAX_FILE_BYTES = 64 * 1024 * 1024
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
            return _read_rest(fd, head, cap)
    except OSError:
        return FileBytes(None, REFUSED_OPEN_ERROR)


# ── Drop-in text reads for call sites that read a repository file ───────

#: Cap of a text read whose purpose sets no tighter bound (a source file, a
#: catalog). The same as the line counters' cap: the largest tracked text
#: file on the corpus is 10.7 MB.
TEXT_READ_MAX_BYTES = MAX_FILE_BYTES
#: Cap of a manifest or config read (package.json, tsconfig, Cargo.toml,
#: go.mod, pyproject.toml, workspace files, git config). The largest such
#: tracked file on the 27 corpus clones is 84 KB; 4 MiB is fifty times that.
MANIFEST_READ_MAX_BYTES = 4 * 1024 * 1024


def _refusal_error(path: os.PathLike[str] | str, refused: str | None) -> OSError:
    """The error ``Path.read_text`` raises for a file it cannot read, so a
    call site that handles a missing or unreadable file handles a refused one
    the same way."""
    if refused == REFUSED_MISSING:
        return FileNotFoundError(2, "No such file or directory", str(path))
    return PermissionError(13, f"refused by the repository reader ({refused})", str(path))


def read_repo_text_or_raise(
    path: os.PathLike[str] | str, repo_root: os.PathLike[str] | str, *,
    encoding: str | None = "utf-8", errors: str | None = "strict", max_bytes: int | None = None,
) -> str:
    """``Path(path).read_text(encoding, errors)`` through the guarded reader:
    the same text (universal newlines), the same ``UnicodeDecodeError``, and
    an ``OSError`` where the file is missing or refused."""
    read = read_repo_bytes(path, repo_root, max_bytes=TEXT_READ_MAX_BYTES if max_bytes is None else max_bytes,
                           stop_at_binary=False)
    if read.data is None:
        raise _refusal_error(path, read.refused)
    # ``read_text()`` with no encoding decodes with the locale's encoding.
    text = read.data.decode(locale.getpreferredencoding(False) if encoding is None else encoding, errors or "strict")
    # Universal newlines; most files have no CR, and the scan for one is
    # cheaper than two replacing passes.
    return text.replace("\r\n", "\n").replace("\r", "\n") if "\r" in text else text


def read_repo_bytes_or_raise(
    path: os.PathLike[str] | str, repo_root: os.PathLike[str] | str, *, max_bytes: int | None = None,
) -> bytes:
    """``Path(path).read_bytes()`` through the guarded reader; ``OSError``
    where the file is missing or refused."""
    read = read_repo_bytes(path, repo_root, max_bytes=TEXT_READ_MAX_BYTES if max_bytes is None else max_bytes,
                           stop_at_binary=False)
    if read.data is None:
        raise _refusal_error(path, read.refused)
    return read.data


def read_repo_head_or_raise(path: os.PathLike[str] | str, repo_root: os.PathLike[str] | str, size: int) -> bytes:
    """The first ``size`` bytes of a regular file inside the repository
    (``open(path, "rb").read(size)`` guarded; no size cap applies, only the
    head is read); ``OSError`` where the file is missing or refused."""
    import sys

    with open_repo_file(path, repo_root, max_bytes=sys.maxsize) as (fd, _size, refused):
        if fd is None:
            raise _refusal_error(path, refused)
        chunks, total = [], 0
        while total < size and (chunk := os.read(fd, size - total)):
            chunks.append(chunk)
            total += len(chunk)
        return b"".join(chunks)
