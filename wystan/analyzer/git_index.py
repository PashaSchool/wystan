"""May git read this clone's index without writing into the clone?

Three git commands read the index (status, diff-index, ls-files). Reading
writes in some index states: a split index re-dates its
``sharedindex.<sha>`` (git's ``freshen_shared_index`` on every read), a
sparse index is expanded and its tree objects written. Before those
commands run, the index is judged: refused when it is not a regular file,
is larger than :data:`MAX_INDEX_BYTES`, or is split or sparse. The git
directory comes from git (``rev-parse --absolute-git-dir``); the engine
reads the index and the config only when they lie inside the scan root
(the guarded reader, the root as its boundary), parsing the extensions with
the repository's object id length. Above the scan root (a subdirectory
scan) the engine opens nothing: the ``sharedindex.*`` listing, ``lstat`` and
git's own ``index.sparse``/``core.splitIndex`` answers decide. A refused
index means no dirty-tree detection, recorded in ``scan_meta.index_unread``.
"""

from __future__ import annotations

import functools
import os
import stat
import struct

from wystan.analyzer.git_discovery import read_pointer
from wystan.analyzer.path_identity import is_within
from wystan.analyzer.repo_reader import read_repo_bytes

#: Larger than any real index (posthog's 70k entries: a few MiB); a larger
#: one is not read at all.
MAX_INDEX_BYTES = 256 << 20
_SIGNATURE = b"DIRC"
_HEADER = struct.Struct(">4sII")
_EXTENSION = struct.Struct(">4sI")
#: Fixed part of an index entry before the object id (ctime..size) and the
#: flags after it; the id is 20 bytes (sha1) or 32 (sha256).
_STAT_BYTES = 40
_FLAG_BYTES = 2
#: ``extensions.objectFormat`` -> object id length in bytes.
_OID_BYTES_BY_FORMAT = {"sha1": 20, "sha256": 32}
_DEFAULT_FORMAT = "sha1"
#: A repository config is small; read no more of it.
_CONFIG_READ_BYTES = 1 << 20
_EXTENDED_FLAG = 0x4000
_SPLIT, _SPARSE = b"link", b"sdir"


def _entry_end(data: bytes, start: int, version: int, oid_bytes: int) -> int | None:
    """Offset past one entry: fixed part, optional extended flags, then the
    path (v2/v3: NUL-padded to a multiple of 8, git's ``ondisk_ce_size``;
    v4: a prefix-strip varint and a NUL-terminated suffix, no padding)."""
    fixed = _STAT_BYTES + oid_bytes + _FLAG_BYTES
    if start + fixed > len(data):
        return None
    flags = struct.unpack_from(">H", data, start + fixed - _FLAG_BYTES)[0]
    header = fixed + (2 if version >= 3 and flags & _EXTENDED_FLAG else 0)
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


def _skip_entries(data: bytes, version: int, count: int, oid_bytes: int) -> int | None:
    """Offset just past the entries, or ``None`` when they do not parse."""
    offset: int | None = _HEADER.size
    for _ in range(count):
        offset = _entry_end(data, offset, version, oid_bytes)
        if offset is None:
            return None
    return offset


def index_extensions(data: bytes, oid_bytes: int = _OID_BYTES_BY_FORMAT[_DEFAULT_FORMAT]) -> set[bytes] | None:
    """Extension signatures of an index file's bytes, ``None`` if unparsable."""
    if len(data) < _HEADER.size:
        return None
    signature, version, count = _HEADER.unpack_from(data)
    if signature != _SIGNATURE or version not in (2, 3, 4):
        return None
    offset = _skip_entries(data, version, count, oid_bytes)
    if offset is None:
        return None
    found, end = set(), len(data) - oid_bytes
    while offset + _EXTENSION.size <= end:
        name, size = _EXTENSION.unpack_from(data, offset)
        found.add(name)
        offset += _EXTENSION.size + size
    return found


def object_format(git_dir: str, root: str) -> str | None:
    """``extensions.objectFormat`` of the repository's config (``sha1`` when
    unset), read through the guarded reader under the scan root; ``None``
    for a value the engine cannot parse."""
    text = read_pointer(os.path.join(git_dir, "config"), root, _CONFIG_READ_BYTES) or ""
    section, found = "", _DEFAULT_FORMAT
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            section = stripped.strip("[]").strip().lower()
        elif section == "extensions" and "=" in stripped:
            key, _, value = stripped.partition("=")
            if key.strip().lower() == "objectformat":
                found = value.split("#")[0].split(";")[0].strip().strip('"').lower()
    return found if found in _OID_BYTES_BY_FORMAT else None


@functools.lru_cache(maxsize=64)
def _parsed_refusal(index: str, size: int, mtime_ns: int, oid_bytes: int, root: str) -> str | None:
    read = read_repo_bytes(index, root, max_bytes=MAX_INDEX_BYTES, stop_at_binary=False)
    if read.data is None:
        return f"index not readable ({read.refused})"
    extensions = index_extensions(read.data, oid_bytes)
    if extensions is None:
        return "index does not parse"
    if _SPLIT in extensions:
        return "split index (git re-dates its shared index file on every read)"
    if _SPARSE in extensions:
        return "sparse index (git writes tree objects when it expands it)"
    return None


def git_dir(root: str) -> str | None:
    """The repository's git directory, as git finds it (no index read)."""
    from wystan.analyzer.git_runner import GitError, run_git  # the runner imports this module

    try:
        found = run_git(root, "rev-parse", "--absolute-git-dir", check=False)
    except GitError:
        return None
    return found.text.strip() or None if found.returncode == 0 else None


def _config_says(root: str, key: str) -> bool:
    from wystan.analyzer.git_runner import GitError, run_git

    try:
        return run_git(root, "config", "--get", key, check=False).text.strip().lower() == "true"
    except GitError:
        return False


def _outside_refusal(root: str) -> str | None:
    """The index lies above the scan root, where the engine reads nothing:
    git's own configuration answers instead of the file."""
    if _config_says(root, "index.sparse"):
        return "sparse index (index.sparse; the index lies above the scan root)"
    if _config_says(root, "core.splitIndex"):
        return "split index (core.splitIndex; the index lies above the scan root)"
    return None


def index_refusal(root: str) -> str | None:
    """Why the clone's index must not be read, or ``None`` when it may be
    (also when there is none). The index is parsed only when it lies inside
    the scan root (guarded reader); above it, only its metadata and git's
    answers are used."""
    found_dir = git_dir(root)
    if found_dir is None:
        return None
    if any(name.startswith("sharedindex.") for name in os.listdir(found_dir)):
        return "split index (sharedindex file present)"
    index = os.path.join(found_dir, "index")
    try:
        info = os.lstat(index)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode):
        return "index is not a regular file"
    if info.st_size > MAX_INDEX_BYTES:
        return f"index larger than {MAX_INDEX_BYTES} bytes"
    if not is_within(index, root):
        return _outside_refusal(root)
    found_format = object_format(found_dir, root)
    if found_format is None:
        return "unknown object format (extensions.objectFormat)"
    return _parsed_refusal(index, info.st_size, info.st_mtime_ns, _OID_BYTES_BY_FORMAT[found_format],
                           os.path.realpath(root))
