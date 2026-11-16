"""The layout of a git index file, read the way git reads it, in a bounded
window.

Only what decides whether git may read the index is needed: the header,
where the entry region ends, and the extension signatures after it. The
entries are walked by their on-disk sizes (git's ``create_from_disk``: the
name length from the flags, ``strlen`` when it is 0xFFF; version 4's
prefix-compressed names) without building them, so a 256 MiB index costs a
window of about a megabyte, not its size. The extensions are then visited
by their headers, as git's loop does (``while offset <= size - hash - 8``),
reading eight bytes each and seeking over the rest.
"""

from __future__ import annotations

import os
import struct
from collections.abc import Callable
from typing import NamedTuple

_SIGNATURE = b"DIRC"
_HEADER = struct.Struct(">4sII")
_EXTENSION = struct.Struct(">4sI")
_VERSIONS = (2, 3, 4)
#: Fixed part of an entry before the object id (ctime..size), and the flags
#: after it; the id is 20 bytes (sha1) or 32 (sha256).
_STAT_BYTES = 40
_FLAG_BYTES = 2
_EXTENDED_FLAG = 0x4000
_EXTENDED_FLAG_BYTES = 2
_NAME_MASK = 0x0FFF
_ENTRY_ALIGN = 8
#: Bytes read from the file at a time.
WINDOW_BYTES = 1 << 20
#: The longest entry the walk accepts. A path is bounded by the
#: filesystem's PATH_MAX (1 KiB on macOS, 4 KiB on Linux), so a longer entry
#: is a crafted file; refusing it keeps the window bounded.
MAX_ENTRY_BYTES = 64 << 10
#: The most entries walked: a tree of a million files (chromium's index has
#: about 400k). Each costs a loop turn; more is refused, which keeps the
#: inspection of a crafted 256 MiB index (4M minimal entries) well under a
#: second.
MAX_INDEX_ENTRIES = 1 << 20
#: Real indexes carry fewer than ten extensions; more is a crafted file.
MAX_EXTENSIONS = 64

#: ``visit(window, entry_start, name_start, name_length)`` for callers that
#: need the entries (none in the scan; the parser's own tests do). For
#: version 4 the name is the stored suffix only.
Visit = Callable[[bytes, int, int, int], None]


class IndexLayout(NamedTuple):
    version: int
    entries: int
    extensions: frozenset[bytes]


class _Window:
    """A bounded view of the file: ``data`` holds bytes from ``base``."""

    def __init__(self, fd: int, size: int) -> None:
        self.fd, self.size = fd, size
        self.data, self.base = b"", 0

    def hold(self, offset: int) -> None:
        """Make the window start at ``offset`` and hold WINDOW_BYTES (or up
        to the end of the file) after it."""
        kept = self.data[offset - self.base:] if self.base <= offset <= self.base + len(self.data) else b""
        want = min(WINDOW_BYTES + MAX_ENTRY_BYTES, self.size - offset)
        chunks = [kept]
        held = len(kept)
        while held < want:
            chunk = os.pread(self.fd, want - held, offset + held)
            if not chunk:
                break
            chunks.append(chunk)
            held += len(chunk)
        self.data, self.base = b"".join(chunks), offset

    def end(self) -> int:
        return self.base + len(self.data)


def _varint(data: bytes, offset: int) -> tuple[int, int] | None:
    """git's ``decode_varint`` (offset encoding); (value, next offset)."""
    if offset >= len(data):
        return None
    byte = data[offset]
    value, offset = byte & 0x7F, offset + 1
    while byte & 0x80:
        if offset >= len(data):
            return None
        byte = data[offset]
        value = ((value + 1) << 7) | (byte & 0x7F)
        offset += 1
    return value, offset


def _compressed_entry(data: bytes, o: int, fixed: int, previous: int) -> tuple[int, int, int, int] | None:
    """(on-disk size, suffix start, suffix length, full name length) of the
    version 4 entry at ``o``, as git computes them; ``None`` when it does
    not parse."""
    if o + fixed > len(data):
        return None
    flags = (data[o + fixed - 2] << 8) | data[o + fixed - 1]
    name = o + fixed + (_EXTENDED_FLAG_BYTES if flags & _EXTENDED_FLAG else 0)
    decoded = _varint(data, name)
    if decoded is None or decoded[0] > previous:
        return None
    strip, suffix = decoded
    copied = previous - strip
    length = flags & _NAME_MASK
    if length == _NAME_MASK:
        nul = data.find(b"\0", suffix, o + MAX_ENTRY_BYTES)
        if nul < 0:
            return None
        length = nul - suffix + copied
    if length < copied:
        return None
    return suffix - o + (length - copied) + 1, suffix, length - copied, length


def _walk_fixed(window: _Window, count: int, fixed: int, visit: Visit | None) -> int | None:
    """Versions 2 and 3: each entry's size follows from its flags alone.
    The inner loop runs once per entry (up to MAX_INDEX_ENTRIES times), so
    it does only that: inside the window's safe zone an entry (at most
    MAX_ENTRY_BYTES) cannot run past the data, and bounds are checked once
    per window instead of once per entry."""
    offset, wide, mask = _HEADER.size, fixed + _EXTENDED_FLAG_BYTES, -_ENTRY_ALIGN
    high, low = fixed - _FLAG_BYTES, fixed - 1
    while count:
        window.hold(offset)
        data = window.data
        at_end = window.end() >= window.size
        safe = len(data) - (fixed if at_end else MAX_ENTRY_BYTES)
        o = 0
        while count and o <= safe:
            flags = (data[o + high] << 8) | data[o + low]
            head = wide if flags & _EXTENDED_FLAG else fixed
            length = flags & _NAME_MASK
            if length == _NAME_MASK:
                nul = data.find(b"\0", o + head, o + MAX_ENTRY_BYTES)
                if nul < 0:
                    return None
                length = nul - o - head
            if visit is not None:
                visit(data, o, o + head, length)
            o += (head + length + _ENTRY_ALIGN) & mask
            count -= 1
        if o > len(data) or (count and at_end):
            return None
        offset += o
    return offset


def _walk_compressed(window: _Window, count: int, fixed: int, visit: Visit | None) -> int | None:
    """Version 4: each name strips a prefix of the previous one (a varint)
    and stores the rest NUL-terminated, without padding."""
    offset, previous = _HEADER.size, 0
    window.hold(offset)
    while count:
        if offset + MAX_ENTRY_BYTES > window.end() and window.end() < window.size:
            window.hold(offset)
        data, o = window.data, offset - window.base
        found = _compressed_entry(data, o, fixed, previous)
        if found is None:
            return None
        size, suffix, suffix_length, previous = found
        if size > MAX_ENTRY_BYTES or o + size > len(data):
            return None
        if visit is not None:
            visit(data, o, suffix, suffix_length)
        offset += size
        count -= 1
    return offset


def _extensions(fd: int, offset: int, end: int) -> frozenset[bytes] | None:
    """Signatures of the extensions from ``offset`` up to ``end`` (the
    trailing checksum), visited by their headers as git does."""
    found = set()
    for _ in range(MAX_EXTENSIONS + 1):
        if offset + _EXTENSION.size > end:
            return frozenset(found)
        header = os.pread(fd, _EXTENSION.size, offset)
        if len(header) < _EXTENSION.size:
            return None
        name, size = _EXTENSION.unpack(header)
        found.add(name)
        offset += _EXTENSION.size + size
    return None


def index_layout(fd: int, size: int, oid_bytes: int, visit: Visit | None = None) -> IndexLayout | None:
    """The layout of the index open on ``fd`` (``size`` bytes), ``None`` when
    it does not parse."""
    if size < _HEADER.size + oid_bytes:
        return None
    header = os.pread(fd, _HEADER.size, 0)
    if len(header) < _HEADER.size:
        return None
    signature, version, count = _HEADER.unpack(header)
    if signature != _SIGNATURE or version not in _VERSIONS:
        return None
    if count > MAX_INDEX_ENTRIES:
        return None
    window, fixed = _Window(fd, size), _STAT_BYTES + oid_bytes + _FLAG_BYTES
    walk = _walk_compressed if version == 4 else _walk_fixed
    offset = walk(window, count, fixed, visit)
    if offset is None:
        return None
    extensions = _extensions(fd, offset, size - oid_bytes)
    if extensions is None:
        return None
    return IndexLayout(version, count, extensions)
