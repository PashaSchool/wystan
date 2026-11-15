"""Bounded, contained reads of one file of an untrusted repository.

The one reader every read of a repository path goes through. It never opens
what a scanned repository must not make the engine open:

* The caller passes the repository root and a path relative to it; an
  absolute path or one with a ``..`` segment is refused (``repo_path``).
* Containment (``analyzer.safe_read``, switch ``WYSTAN_SYMLINK_CONTAINMENT``,
  default on): the path is resolved; it must resolve inside the resolved
  root. The file is then opened component by component under a descriptor of
  the root, every component with ``O_NOFOLLOW`` (``os.open`` with
  ``dir_fd``), so a directory or a symlink swapped in between the check and
  the open is refused, not followed: the opened file is inside the root by
  construction. An in-repository symlink is read as the file it resolves to.
  Where the platform has no ``dir_fd`` support, the resolved path is opened
  with ``O_NOFOLLOW`` and the descriptor's device and inode must equal those
  of the checked target (a parent swapped before the check is caught; one
  swapped and swapped back between the two ``stat`` calls is not).
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

import os
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Iterator

__all__ = [
    "MAX_FILE_BYTES",
    "REFUSED_BINARY",
    "REFUSED_MISSING",
    "REFUSED_NOT_REGULAR",
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
_READ_CHUNK = 1 << 20
_FILE_FLAGS = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
_NO_FOLLOW = getattr(os, "O_NOFOLLOW", 0)
_DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | _NO_FOLLOW
_HAS_DIR_FD = os.open in os.supports_dir_fd


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


def _resolved_parts(path: Path, repo_root: Path) -> tuple[Path, tuple[str, ...]] | None:
    """``(resolved root, components of the resolved path under it)``, or
    ``None`` when the path resolves outside the root (or loops)."""
    try:
        real_root = Path(os.path.realpath(repo_root))
        real = Path(os.path.realpath(path))
        parts = real.relative_to(real_root).parts
    except (OSError, ValueError, RuntimeError):
        return None
    return (real_root, parts) if parts else None


def _open_beneath(real_root: Path, parts: tuple[str, ...]) -> int:
    """Open ``real_root/parts...`` without following any symlink on the way;
    raises ``OSError`` when a component is a symlink or missing."""
    dir_fd = os.open(real_root, _DIR_FLAGS & ~_NO_FOLLOW)
    try:
        for name in parts[:-1]:
            next_fd = os.open(name, _DIR_FLAGS, dir_fd=dir_fd)
            os.close(dir_fd)
            dir_fd = next_fd
        return os.open(parts[-1], _FILE_FLAGS | _NO_FOLLOW, dir_fd=dir_fd)
    finally:
        os.close(dir_fd)


def _open_checked(real: Path) -> int:
    """No ``dir_fd``: open the resolved path and require the descriptor to
    be the file that was checked (same device and inode)."""
    checked = os.stat(real)
    fd = os.open(real, _FILE_FLAGS | _NO_FOLLOW)
    opened = os.fstat(fd)
    if (opened.st_dev, opened.st_ino) != (checked.st_dev, checked.st_ino):
        os.close(fd)
        raise OSError("the file changed between the check and the open")
    return fd


def _containment_on() -> bool:
    # Late import: ``safe_read`` re-exports this module's names at its end.
    from wystan.analyzer.safe_read import symlink_containment_enabled

    return symlink_containment_enabled()


def _open(path: Path, repo_root: Path) -> tuple[int | None, str | None]:
    """A descriptor for a regular-looking, contained file, or the refusal."""
    try:
        link = os.lstat(path)
    except OSError:
        return None, REFUSED_MISSING
    if not stat.S_ISLNK(link.st_mode) and not stat.S_ISREG(link.st_mode):
        return None, REFUSED_NOT_REGULAR
    if not _containment_on():
        try:  # the kill switch: legacy reads, file type and cap still checked
            return os.open(path, _FILE_FLAGS), None
        except OSError:
            return None, REFUSED_NOT_REGULAR
    resolved = _resolved_parts(path, repo_root)
    if resolved is None:
        return None, REFUSED_OUTSIDE
    try:
        if _HAS_DIR_FD:
            return _open_beneath(*resolved), None
        return _open_checked(resolved[0].joinpath(*resolved[1])), None
    except FileNotFoundError:
        return None, REFUSED_MISSING
    except OSError:
        return None, REFUSED_OUTSIDE


@contextmanager
def open_repo_file(
    path: os.PathLike[str] | str, repo_root: os.PathLike[str] | str, *, max_bytes: int | None = None,
) -> Iterator[tuple[int | None, int, str | None]]:
    """Yield ``(fd, size, refusal)``: a descriptor only for a regular file
    inside the repository of at most ``max_bytes`` (default
    ``MAX_FILE_BYTES``, read at call time); ``fd`` is ``None`` with the
    refusal otherwise. Rules: module doc."""
    cap = MAX_FILE_BYTES if max_bytes is None else max_bytes
    fd, refused = _open(Path(path), Path(repo_root))
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
        return FileBytes(None, REFUSED_NOT_REGULAR)


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
    import locale

    # ``read_text()`` with no encoding decodes with the locale's encoding.
    text = read.data.decode(locale.getpreferredencoding(False) if encoding is None else encoding, errors or "strict")
    return text.replace("\r\n", "\n").replace("\r", "\n")


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
