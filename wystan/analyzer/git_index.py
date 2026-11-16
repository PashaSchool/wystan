"""May git read this clone's index without writing into the clone?

Three git commands read the index (status, diff-index, ls-files). Reading
writes in some index states: a split index re-dates its
``sharedindex.<sha>`` (git's ``freshen_shared_index`` on every read), a
sparse index is expanded and its tree objects written. The engine looks at
the index itself first (bounded reads, no git) and refuses those commands
when the index is not a regular file inside the git directory, is larger
than :data:`MAX_INDEX_BYTES`, or is split or sparse (a ``sharedindex.*``
file, a ``link`` or ``sdir`` extension). A refused index means no
dirty-tree detection, recorded in ``scan_meta.index_unread``.
"""

from __future__ import annotations

import functools
import os
import stat
import struct

from wystan.analyzer.git_discovery import read_pointer

#: Larger than any real index (posthog's 70k entries: a few MiB); a larger
#: one is not read at all.
MAX_INDEX_BYTES = 256 << 20
_SIGNATURE = b"DIRC"
_HEADER = struct.Struct(">4sII")
_EXTENSION = struct.Struct(">4sI")
#: Fixed part of an index entry before its flags (ctime..sha1, 20-byte id).
_ENTRY_FIXED = 62
_EXTENDED_FLAG = 0x4000
_SPLIT, _SPARSE = b"link", b"sdir"
_GITDIR_PREFIX = "gitdir:"
_OID_BYTES = 20


def git_dir_of(root: str) -> str | None:
    dot_git = os.path.join(root, ".git")
    if os.path.isdir(dot_git) and not os.path.islink(dot_git):
        return dot_git
    pointer = read_pointer(dot_git)
    if pointer and pointer.startswith(_GITDIR_PREFIX):
        return os.path.normpath(os.path.join(root, pointer[len(_GITDIR_PREFIX):].strip()))
    if os.path.isfile(os.path.join(root, "HEAD")) and os.path.isdir(os.path.join(root, "objects")):
        return root  # a bare repository
    return None


def _entry_end(data: bytes, start: int, version: int) -> int | None:
    """Offset past one entry: fixed part, optional extended flags, then the
    path (v2/v3: NUL-padded to a multiple of 8, git's ``ondisk_ce_size``;
    v4: a prefix-strip varint and a NUL-terminated suffix, no padding)."""
    if start + _ENTRY_FIXED > len(data):
        return None
    flags = struct.unpack_from(">H", data, start + _ENTRY_FIXED - 2)[0]
    header = _ENTRY_FIXED + (2 if version >= 3 and flags & _EXTENDED_FLAG else 0)
    offset = start + header
    if version >= 4:
        while offset < len(data) and data[offset] & 0x80:
            offset += 1
        offset += 1
    end = data.find(b"\0", offset)
    if end < 0:
        return None
    if version >= 4:
        return end + 1
    return start + ((header + (end - offset) + 8) & ~7)


def _skip_entries(data: bytes, version: int, count: int) -> int | None:
    """Offset just past the entries, or ``None`` when they do not parse."""
    offset: int | None = _HEADER.size
    for _ in range(count):
        offset = _entry_end(data, offset, version)
        if offset is None:
            return None
    return offset


def index_extensions(data: bytes) -> set[bytes] | None:
    """Extension signatures of an index file's bytes, ``None`` if unparsable."""
    if len(data) < _HEADER.size:
        return None
    signature, version, count = _HEADER.unpack_from(data)
    if signature != _SIGNATURE or version not in (2, 3, 4):
        return None
    offset = _skip_entries(data, version, count)
    if offset is None:
        return None
    found, end = set(), len(data) - _OID_BYTES
    while offset + _EXTENSION.size <= end:
        name, size = _EXTENSION.unpack_from(data, offset)
        found.add(name)
        offset += _EXTENSION.size + size
    return found


@functools.lru_cache(maxsize=64)
def _refusal(index: str, size: int, mtime_ns: int) -> str | None:
    with open(index, "rb") as fh:
        extensions = index_extensions(fh.read(size))
    if extensions is None:
        return "index does not parse"
    if _SPLIT in extensions:
        return "split index (git re-dates its shared index file on every read)"
    if _SPARSE in extensions:
        return "sparse index (git writes tree objects when it expands it)"
    return None


def _enclosing_git_dir(root: str) -> str | None:
    """The git directory of the repository ``root`` is in (``root`` may be a
    subdirectory of the working tree)."""
    current = os.path.realpath(root)
    while True:
        git_dir = git_dir_of(current)
        if git_dir is not None:
            return git_dir
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def index_refusal(root: str) -> str | None:
    """Why the clone's index must not be read, or ``None`` when it may be
    (also when there is none)."""
    git_dir = _enclosing_git_dir(root)
    if git_dir is None:
        return None
    if any(name.startswith("sharedindex.") for name in os.listdir(git_dir)):
        return "split index (sharedindex file present)"
    index = os.path.join(git_dir, "index")
    try:
        info = os.lstat(index)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode):
        return "index is not a regular file"
    if info.st_size > MAX_INDEX_BYTES:
        return f"index larger than {MAX_INDEX_BYTES} bytes"
    return _refusal(index, info.st_size, info.st_mtime_ns)
