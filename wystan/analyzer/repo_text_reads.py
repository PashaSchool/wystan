"""Drop-in reads for call sites that read a repository file.

Each returns what the standard call it replaced returned, through the guarded
reader (``repo_reader``): ``read_repo_text_or_raise`` is
``Path.read_text(encoding, errors)`` (universal newlines, the same
``UnicodeDecodeError``), ``read_repo_bytes_or_raise`` is ``Path.read_bytes()``,
``read_repo_head_or_raise`` is ``open(path, "rb").read(size)`` and
``read_repo_text_head_or_raise`` is ``open(path, "r", encoding=...,
errors=...).read(chars)``. Each raises an ``OSError`` where the file is
missing or refused, so a site that handled an unreadable file handles a
refused one the same way. Re-exported by ``repo_reader``.
"""

from __future__ import annotations

import codecs
import io
import locale
import os
import sys

from wystan.analyzer.repo_reader import (
    MANIFEST_READ_MAX_BYTES,
    REFUSED_MISSING,
    TEXT_READ_MAX_BYTES,
    open_repo_file,
    read_repo_bytes,
)

__all__ = [
    "MANIFEST_READ_MAX_BYTES",
    "TEXT_READ_MAX_BYTES",
    "read_repo_bytes_or_raise",
    "read_repo_head_or_raise",
    "read_repo_text_head_or_raise",
    "read_repo_text_or_raise",
]




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
    # ``read_text()`` decodes with the codec's incremental decoder (it differs
    # from ``bytes.decode``: UTF-16 without a byte-order mark is an error),
    # and with no encoding uses the locale's.
    codec = locale.getpreferredencoding(False) if encoding is None else encoding
    text = codecs.getincrementaldecoder(codec)(errors or "strict").decode(read.data, final=True)
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
    with open_repo_file(path, repo_root, max_bytes=sys.maxsize) as (fd, _size, refused):
        if fd is None:
            raise _refusal_error(path, refused)
        chunks, total = [], 0
        while total < size and (chunk := os.read(fd, size - total)):
            chunks.append(chunk)
            total += len(chunk)
        return b"".join(chunks)


class _BoundedRaw(io.RawIOBase):
    """A descriptor read as a raw stream that ends after ``budget`` bytes:
    a text head never reads past the cap, even of a file that grows."""

    def __init__(self, fd: int, budget: int) -> None:
        super().__init__()
        self._fd, self._budget = fd, budget

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        size = min(len(buffer), self._budget)
        data = os.read(self._fd, size) if size > 0 else b""
        buffer[:len(data)] = data
        self._budget -= len(data)
        return len(data)


def read_repo_text_head_or_raise(
    path: os.PathLike[str] | str, repo_root: os.PathLike[str] | str, chars: int, *,
    encoding: str | None = "utf-8", errors: str | None = "strict", max_bytes: int | None = None,
) -> str:
    """The first ``chars`` characters of a text file of the repository, as
    ``open(path, "r", encoding=..., errors=...).read(chars)`` returns them
    (the same decoder and newline translation), reading only as far as they
    need and never more than ``max_bytes`` (default ``TEXT_READ_MAX_BYTES``)."""
    cap = TEXT_READ_MAX_BYTES if max_bytes is None else max_bytes
    with open_repo_file(path, repo_root, max_bytes=cap) as (fd, _size, refused):
        if fd is None:
            raise _refusal_error(path, refused)
        raw = io.BufferedReader(_BoundedRaw(fd, cap))
        text = io.TextIOWrapper(raw, encoding=locale.getpreferredencoding(False) if encoding is None else encoding,
                                errors=errors or "strict")
        try:
            return text.read(chars)
        finally:
            text.detach()
