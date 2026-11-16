"""Does git's ``EOIE`` (end of index entries) extension agree with the
engine's walk of the index?

git reads the extensions of an index from where its entries end. With
threaded loading (``index.threads`` above one, which a clone's own config
can ask for), it does not walk the entries first: it takes the offset the
``EOIE`` extension records and reads the extensions from there, in a
thread of their own (``read_eoie_extension`` in git's ``read-cache.c``,
measured on git 2.39: an ``EOIE`` pointing at a hidden mandatory extension
makes ``-c index.threads=4 ls-files`` fail on it; unset or ``1`` does
not). The runner pins ``index.threads=1``; this check is the second line:
an ``EOIE`` where git looks for one (the last extension before the
checksum, sized as git expects) must record exactly the offset where the
walked entries end, be the last extension of the walked chain, and carry
the hash git computes over the headers of the extensions before it. Any
``EOIE`` elsewhere, or any disagreement, makes the index ambiguous.
"""

from __future__ import annotations

import hashlib
import os
import struct

from wystan.analyzer.git_index_layout import AmbiguousIndex, IndexLayout

_EOIE = b"EOIE"
_EXTENSION_HEADER_BYTES = 8
_OFFSET = struct.Struct(">I")
#: git's ``EOIE_SIZE`` is a 4-byte offset and a 20-byte (sha1-sized) hash;
#: a 32-byte hash is also accepted here so a sha256 index is not missed.
_SHA1_RAWSZ = 20
_HASH_BY_OID_BYTES = {20: "sha1", 32: "sha256"}


def _candidate_sizes(oid_bytes: int) -> tuple[int, ...]:
    return tuple(sorted({_OFFSET.size + _SHA1_RAWSZ, _OFFSET.size + oid_bytes}))


def _where_git_looks(fd: int, file_size: int, oid_bytes: int) -> tuple[int, int] | None:
    """(position, recorded entry end) of an ``EOIE`` git would take."""
    for body in _candidate_sizes(oid_bytes):
        position = file_size - oid_bytes - _EXTENSION_HEADER_BYTES - body
        if position < 0:
            continue
        header = os.pread(fd, _EXTENSION_HEADER_BYTES + _OFFSET.size, position)
        if len(header) == _EXTENSION_HEADER_BYTES + _OFFSET.size and header[:4] == _EOIE \
                and _OFFSET.unpack(header[4:8])[0] == body:
            return position, _OFFSET.unpack(header[8:])[0]
    return None


def _headers_digest(layout: IndexLayout, oid_bytes: int) -> bytes:
    digest = hashlib.new(_HASH_BY_OID_BYTES[oid_bytes])
    for ext in layout.chain[:-1]:
        digest.update(ext.name + _OFFSET.pack(ext.size))
    return digest.digest()


def check_eoie(fd: int, file_size: int, oid_bytes: int, layout: IndexLayout) -> None:
    """Raise :class:`AmbiguousIndex` unless git's ``EOIE`` view of the index
    (if any) is the walked one."""
    named = [ext for ext in layout.chain if ext.name == _EOIE]
    found = _where_git_looks(fd, file_size, oid_bytes)
    if found is None:
        if named:
            raise AmbiguousIndex("an EOIE extension where git does not look for one")
        return
    position, recorded = found
    if not layout.chain or layout.chain[-1].offset != position or len(named) != 1:
        raise AmbiguousIndex("git's EOIE is not the last extension of the walked chain")
    if recorded != layout.entries_end:
        raise AmbiguousIndex(f"EOIE records entries ending at {recorded}, the walk ends at {layout.entries_end}")
    # git compares the hash's full length at the EOIE body's hash field.
    stored = os.pread(fd, oid_bytes, position + _EXTENSION_HEADER_BYTES + _OFFSET.size)
    if stored != _headers_digest(layout, oid_bytes):
        raise AmbiguousIndex("the EOIE hash does not verify")
