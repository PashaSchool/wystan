"""The layout of a git index file, read the way git reads it, in a bounded
window.

Only what decides whether git may read the index is needed: the header,
where the entry region ends, and the extension signatures after it. The
entries are walked by their on-disk sizes (git's ``create_from_disk``: the
name length from the flags, ``strlen`` when it is 0xFFF; version 4's
prefix-compressed names) without building them, so a 256 MiB index costs a
window of about a megabyte, not its size. The extensions are then visited
by their headers, as git's sequential loop does, reading eight bytes each
and seeking over the rest. git reads the extensions from another place only
through ``EOIE`` with threaded loading; the runner pins
``index.threads=1`` and ``git_index_eoie`` refuses any index whose ``EOIE``
does not agree with this walk.

Every loop the file's bytes steer has a named bound: at most
MAX_INDEX_ENTRIES entries, each advancing by at least its fixed part; a
name's NUL searched for within MAX_ENTRY_BYTES (and the entry then
consumes what was searched); a varint read for at most MAX_VARINT_BYTES;
at most MAX_EXTENSIONS extension headers; a window refill of at most
WINDOW_BYTES + MAX_ENTRY_BYTES that fails on a short read.
"""

from __future__ import annotations

import errno
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
#: The most entries an index header may declare (2**20 = 1,048,576); a
#: header declaring more is refused before any entry is read. Why this
#: value: it is above every real tree the engine targets (chromium's index,
#: among the largest public ones, has about 400k entries), and it bounds the
#: walk, which costs one loop turn per entry: 2**20 minimal entries take
#: about 0.5 s of CPU (versions 2 and 3) and 1.9 s (version 4), where a
#: 256 MiB file could otherwise declare 4M. A larger tree loses only
#: dirty-tree detection (``index_unread``), never the scan.
MAX_INDEX_ENTRIES = 1 << 20
#: Real indexes carry fewer than ten extensions; more is a crafted file.
MAX_EXTENSIONS = 64
#: The longest varint git's ``decode_varint`` (varint.c) accepts. It keeps
#: the value in a 64-bit ``uintmax_t`` and gives up before a shift that
#: could overflow, when ``value + 1`` reaches 2**57 (its top 7 bits): the
#: tenth byte is the last it can read, so an eleventh is never read here.
MAX_VARINT_BYTES = 10
_VARINT_OVERFLOW = 1 << (64 - 7)

#: ``visit(window, entry_start, name_start, name_length)`` for callers that
#: need the entries (none in the scan; the parser's own tests do). For
#: version 4 the name is the stored suffix only.
Visit = Callable[[bytes, int, int, int], None]


class AmbiguousIndex(ValueError):
    """git could read this index differently from the engine's walk."""


class Extension(NamedTuple):
    offset: int
    name: bytes
    size: int


class IndexLayout(NamedTuple):
    version: int
    entries: int
    #: Where the walked entries end and the extensions begin.
    entries_end: int
    chain: tuple[Extension, ...]

    @property
    def extensions(self) -> frozenset[bytes]:
        return frozenset(ext.name for ext in self.chain)


def _shrunk(offset: int) -> OSError:
    """The file ends before the size it was inspected with (replaced or
    truncated meanwhile): without this a short read would leave the walk
    at the same offset forever."""
    return OSError(errno.EIO, f"the index changed while it was inspected (short read at {offset})")


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
                raise _shrunk(offset + held)
            chunks.append(chunk)
            held += len(chunk)
        self.data, self.base = b"".join(chunks), offset

    def end(self) -> int:
        return self.base + len(self.data)


def _varint(data: bytes, offset: int) -> tuple[int, int] | None:
    """git's ``decode_varint`` (offset encoding); (value, next offset).
    ``None`` where git's own decoder gives up (its overflow check, so at
    most MAX_VARINT_BYTES are read: the work is constant, not quadratic in
    a run of continuation bytes) or the data ends. On overflow git returns
    0 without consuming the bytes and reads the name from them, which this
    walk does not model: the index is refused instead."""
    end = min(len(data), offset + MAX_VARINT_BYTES)
    if offset >= end:
        return None
    byte = data[offset]
    value, offset = byte & 0x7F, offset + 1
    while byte & 0x80:
        value += 1
        if value >= _VARINT_OVERFLOW or offset >= end:
            return None
        byte = data[offset]
        value = (value << 7) | (byte & 0x7F)
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
    # A strip longer than the previous name is git's "malformed name field"
    # (it dies). For the first entry git ignores the strip; it writes 0
    # there, and anything else is refused (``previous`` is 0).
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


def _extension_chain(fd: int, offset: int, end: int) -> tuple[Extension, ...]:
    """The extensions from ``offset`` (where the walked entries end) up to
    ``end`` (the trailing checksum), visited by their headers as git's
    sequential loop does. Honest indexes end exactly at the checksum; a
    header or body running past it, or too many extensions, is refused."""
    chain = []
    while offset + _EXTENSION.size <= end:
        if len(chain) == MAX_EXTENSIONS:
            raise AmbiguousIndex(f"more than {MAX_EXTENSIONS} extensions")
        header = os.pread(fd, _EXTENSION.size, offset)
        if len(header) < _EXTENSION.size:
            raise _shrunk(offset)
        name, size = _EXTENSION.unpack(header)
        if offset + _EXTENSION.size + size > end:
            raise AmbiguousIndex(f"extension {name!r} at {offset} runs past the checksum")
        chain.append(Extension(offset, name, size))
        offset += _EXTENSION.size + size
    if offset != end:
        raise AmbiguousIndex(f"extensions end at {offset}, the checksum starts at {end}")
    return tuple(chain)


def index_layout(fd: int, size: int, oid_bytes: int, visit: Visit | None = None) -> IndexLayout | None:
    """The layout of the index open on ``fd`` (``size`` bytes), ``None`` when
    it does not parse; :class:`AmbiguousIndex` when git could see other
    extensions than this walk does (``git_index_eoie``)."""
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
    chain = _extension_chain(fd, offset, size - oid_bytes)
    return IndexLayout(version, count, offset, chain)
