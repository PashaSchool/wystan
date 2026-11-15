"""Write the tree of one commit to a directory, from raw blobs.

Why it exists: ``pipeline_v2/snapshots.run_snapshots`` (the impact
snapshots of Stage 6.96) used ``git worktree add`` and ``git checkout`` to
see the repository at older commits. A checkout runs the clone's content
filters and hooks in a working-tree context of its own, which no filter
list computed for the main tree covers. Here nothing is checked out: the
tree is listed (``ls-tree``), sizes are asked first (``cat-file
--batch-check``), and each blob the caller wants is streamed raw to disk
(``cat-file --batch`` applies no filter, textconv or end-of-line
conversion). Every other file is a sparse placeholder of the blob's size,
so a walk or a size check sees the tree as a checkout would without its
bytes being read or written. A blob that is not in the object store (a
partial clone) fails the export with :class:`MissingObjects`.

Tree entry names come from the untrusted repository: names a checkout on
this platform would refuse are skipped and recorded (:func:`refusal_reason`;
Windows-only rules apply only on Windows); symbolic links and submodules
are never materialised, only recorded; every file and directory is created
relative to a no-follow directory descriptor with ``O_EXCL``. Only the
executable bit is taken from an entry's mode. Entries, content bytes and
path length are capped.
"""

from __future__ import annotations

import os
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import BinaryIO, Callable

from wystan.analyzer.git_history import object_sizes
from wystan.analyzer.git_runner import GitError, object_name, run_git, stream_git
from wystan.analyzer.path_identity import is_within

#: Caps against a crafted tree filling the disk or the inode table. The
#: largest corpus tree (posthog, 2026-11-15) has 69,882 files, 854 MB and a
#: longest path of 242 characters; each cap leaves a wide margin.
MAX_TREE_ENTRIES = 500_000
MAX_TREE_BYTES = 8 * 1024 ** 3
MAX_PATH_BYTES = 1024
#: The longest file name the common file systems accept.
MAX_COMPONENT_BYTES = 255
#: Bytes copied per read while streaming a blob to its file.
_COPY_CHUNK_BYTES = 1 << 20
#: Directory descriptors kept open while writing (files arrive grouped by
#: directory, so a small cache opens each directory about once).
_OPEN_DIRECTORIES = 64

_EXECUTABLE_MODE = b"100755"
_FILE_MODES = frozenset({b"100644", _EXECUTABLE_MODE})
_SYMLINK_MODE = b"120000"
_GITLINK_MODE = b"160000"
_DIRECTORY_PERMISSIONS = 0o700
_FILE_PERMISSIONS = {True: 0o700, False: 0o600}
_ON_WINDOWS = os.name == "nt"
_WINDOWS_DEVICES = frozenset(
    {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
)
#: Code points HFS+ ignores in names, so ``.g‌it`` is ``.git`` there.
_HFS_IGNORED = re.compile("[‌-‏‪-‮⁪-⁯﻿]")
_NTFS_SHORT_NAME = re.compile(r"[^~]{1,6}~\d+(\..{0,3})?")
_GIT_NAMES = frozenset({".git", "git~1"})
_NO_FOLLOW_DIR_FD = all(hasattr(os, name) for name in ("O_NOFOLLOW", "O_DIRECTORY")) and {
    os.open, os.mkdir,
} <= os.supports_dir_fd

#: ``wants_content(path, size)``: write the blob's bytes, or a placeholder.
ContentPolicy = Callable[[str, int], bool]


class TreeTooLarge(GitError):
    """The tree exceeds an export cap; nothing past the cap is written."""


class MissingObjects(GitError):
    """Blobs of the tree are not in the object store (a partial clone)."""

    def __init__(self, count: int) -> None:
        self.count = count
        super().__init__(f"{count} blob(s) of the tree are not in the object store")


@dataclass
class ExportReport:
    written: int = 0
    placeholders: int = 0
    refused: list[tuple[str, str]] = field(default_factory=list)
    symlinks_skipped: list[str] = field(default_factory=list)
    submodules_skipped: list[str] = field(default_factory=list)


def _is_git_name(part: str) -> bool:
    return _HFS_IGNORED.sub("", part).rstrip(". ").lower() in _GIT_NAMES


def _windows_reason(part: str) -> str | None:
    if ":" in part or "\\" in part:
        return "colon or backslash"
    if part.endswith((".", " ")):
        return "ends with a dot or space"
    if part.split(".", 1)[0].rstrip(" ").upper() in _WINDOWS_DEVICES:
        return "reserved device name"
    if _NTFS_SHORT_NAME.fullmatch(part):
        return "NTFS short name"
    return None


def _component_reason(part: str) -> str | None:
    if part in ("", ".", ".."):
        return "empty, . or .. component"
    if "\0" in part:
        return "NUL"
    if _is_git_name(part):
        return ".git component"
    if len(part.encode("utf-8", "surrogateescape")) > MAX_COMPONENT_BYTES:
        return "component too long"
    return _windows_reason(part) if _ON_WINDOWS else None


def refusal_reason(path: str) -> str | None:
    """Why ``path`` (a tree entry, repository-relative) must not be written
    on this platform, or ``None`` when it may."""
    if len(path.encode("utf-8", "surrogateescape")) > MAX_PATH_BYTES:
        return "path too long"
    if path.startswith("/"):
        return "absolute path"
    if _ON_WINDOWS and (PureWindowsPath(path).drive or PureWindowsPath(path).anchor):
        return "absolute or drive path"
    for part in path.split("/"):
        reason = _component_reason(part)
        if reason:
            return reason
    return None


def _entries(repo_root: str, sha: str) -> list[tuple[bytes, bytes, str]]:
    """``(mode, object id, path)`` of every non-tree entry of the commit."""
    listing = run_git(repo_root, "ls-tree", "-r", "-z", "--full-tree", object_name(sha)).stdout
    rows = []
    for record in listing.split(b"\0"):
        if not record:
            continue
        if len(rows) >= MAX_TREE_ENTRIES:
            raise TreeTooLarge(f"tree {sha} has more than {MAX_TREE_ENTRIES} entries")
        meta, _, raw_path = record.partition(b"\t")
        mode, _kind, oid = meta.split(b" ")
        rows.append((mode, oid, raw_path.decode("utf-8", "surrogateescape")))
    return rows


class _ContainedWriter:
    """Creates files under ``base`` without ever following a link."""

    def __init__(self, base: Path) -> None:
        self.base = base
        self.base_fd = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW) if _NO_FOLLOW_DIR_FD else None
        self._dirs: OrderedDict[tuple[str, ...], int] = OrderedDict()

    def close(self) -> None:
        for fd in self._dirs.values():
            os.close(fd)
        self._dirs.clear()
        if self.base_fd is not None:
            os.close(self.base_fd)

    def _directory(self, parts: tuple[str, ...]) -> int:
        if not parts:
            return self.base_fd
        cached = self._dirs.get(parts)
        if cached is not None:
            self._dirs.move_to_end(parts)
            return cached
        parent = self._directory(parts[:-1])
        try:
            os.mkdir(parts[-1], _DIRECTORY_PERMISSIONS, dir_fd=parent)
        except FileExistsError:
            pass
        fd = os.open(parts[-1], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        self._dirs[parts] = fd
        while len(self._dirs) > _OPEN_DIRECTORIES:
            os.close(self._dirs.popitem(last=False)[1])
        return fd

    def create(self, path: str, executable: bool) -> int:
        """A new regular file at ``path``, opened for writing."""
        *parents, name = path.split("/")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        mode = _FILE_PERMISSIONS[executable]
        if self.base_fd is not None:
            return os.open(name, flags, mode, dir_fd=self._directory(tuple(parents)))
        target = self.base.joinpath(*parents)
        target.mkdir(parents=True, exist_ok=True, mode=_DIRECTORY_PERMISSIONS)
        if not is_within(os.path.realpath(target), str(self.base)):
            raise OSError(f"parent of {path!r} resolves outside the export")
        return os.open(target / name, flags, mode)


def _plan(rows: list[tuple[bytes, bytes, str]], report: ExportReport) -> list[tuple[bytes, bytes, str]]:
    """The regular files to write; everything else is recorded."""
    files = []
    for mode, oid, path in rows:
        reason = refusal_reason(path)
        if reason:
            report.refused.append((path, reason))
        elif mode == _SYMLINK_MODE:
            report.symlinks_skipped.append(path)
        elif mode == _GITLINK_MODE:
            report.submodules_skipped.append(path)
        elif mode in _FILE_MODES:
            files.append((mode, oid, path))
        else:
            report.refused.append((path, f"unknown mode {mode.decode()}"))
    return files


def _open_or_refuse(writer: _ContainedWriter, path: str, executable: bool, report: ExportReport) -> int | None:
    try:
        return writer.create(path, executable)
    except OSError as exc:
        # A name colliding with another (case-insensitive file system) or
        # with a directory: recorded, never overwritten.
        report.refused.append((path, f"not writable inside the export: {exc.strerror or exc}"))
        return None


def _copy_blob(stream: BinaryIO, oid: bytes, size: int, fd: int | None) -> None:
    header = stream.readline().rstrip(b"\n").split(b" ")
    if len(header) != 3 or header[0] != oid or header[1] != b"blob" or int(header[2]) != size:
        raise GitError(f"cat-file did not return blob {oid.decode()}: {header!r}")
    left = size
    while left:
        chunk = stream.read(min(left, _COPY_CHUNK_BYTES))
        if not chunk:
            raise GitError(f"cat-file stopped inside blob {oid.decode()}")
        if fd is not None:
            os.write(fd, chunk)
        left -= len(chunk)
    stream.read(1)  # the newline after each object


def _write_contents(root: str, wanted: list, writer: _ContainedWriter, report: ExportReport) -> None:
    """Stream the wanted blobs (in order) from one ``cat-file --batch``."""

    def consume(stream: BinaryIO) -> None:
        for (mode, oid, path), size in wanted:
            fd = _open_or_refuse(writer, path, mode == _EXECUTABLE_MODE, report)
            try:
                _copy_blob(stream, oid, size, fd)
            finally:
                if fd is not None:
                    os.close(fd)
                    report.written += 1

    if wanted:
        stream_git(root, "cat-file", "--batch", stdin=b"".join(oid + b"\n" for (_m, oid, _p), _s in wanted),
                   consume=consume)


def _write_placeholders(placeholders: list, writer: _ContainedWriter, report: ExportReport) -> None:
    for (mode, _oid, path), size in placeholders:
        fd = _open_or_refuse(writer, path, mode == _EXECUTABLE_MODE, report)
        if fd is not None:
            try:
                os.ftruncate(fd, size)  # sparse: the size is right, no byte is written
                report.placeholders += 1
            finally:
                os.close(fd)


def export_tree(
    repo_root: str | os.PathLike[str], sha: str, dest: str | os.PathLike[str],
    wants_content: ContentPolicy | None = None,
) -> ExportReport:
    """Write ``sha``'s tree under ``dest`` (an empty directory the engine
    created): the bytes of each blob ``wants_content(path, size)`` accepts
    (all, by default), a sparse placeholder of the right size for the rest."""
    root, base = os.fspath(repo_root), Path(dest)
    if any(base.iterdir()):
        raise OSError(f"export destination is not empty: {base}")
    report = ExportReport()
    files = _plan(_entries(root, sha), report)
    sizes = object_sizes(root, [oid for _m, oid, _p in files])
    missing = sum(size is None for size in sizes)
    if missing:
        raise MissingObjects(missing)
    sized = list(zip(files, sizes))
    wanted = [(f, s) for f, s in sized if wants_content is None or wants_content(f[2], s)]
    if sum(s for _f, s in wanted) > MAX_TREE_BYTES:
        raise TreeTooLarge(f"tree {sha} holds more than {MAX_TREE_BYTES} bytes to write")
    chosen = {f[2] for f, _s in wanted}
    writer = _ContainedWriter(base)
    try:
        _write_contents(root, wanted, writer, report)
        _write_placeholders([(f, s) for f, s in sized if f[2] not in chosen], writer, report)
    finally:
        writer.close()
    return report
