"""Write the tree of one commit to a directory, from raw blobs.

Why it exists: ``pipeline_v2/snapshots.run_snapshots`` (the impact
snapshots of Stage 6.96) used ``git worktree add`` and ``git checkout`` to
see the repository at older commits. A checkout runs the clone's content
filters and hooks in a working-tree context of its own (``includeIf
"gitdir:"``, a per-worktree config, submodules), which no filter list
computed for the main tree covers. Here nothing is checked out: the tree is
listed (``ls-tree``) and each blob read raw (``cat-file --batch`` applies no
filter, textconv or end-of-line conversion), so git never runs a filter.

Tree entry names come from the untrusted repository, so the write is
contained by construction: every name is checked against the rules a
checkout on any platform would need (see :func:`refusal_reason`); refused
entries are skipped and recorded; symbolic links (mode 120000) and
submodules (160000) are never materialised, only recorded, so no later
entry can be written through a link; each directory is created and opened
relative to an open descriptor of its parent with no-follow, and each file
with ``O_CREAT | O_EXCL | O_NOFOLLOW`` (where the platform lacks
descriptor-relative calls, the parent's real path is checked to lie inside
the destination by identity before each write). The only mode bit taken
from an entry is "executable". Entry count, total bytes and path length
are capped. Content is the blob as stored: attributes asking for
``eol=crlf``, ``ident`` or a ``working-tree-encoding`` are not applied.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath

from wystan.analyzer.git_history import OBJECTS_PER_BATCH, read_objects
from wystan.analyzer.git_runner import GitError, object_name, run_git
from wystan.analyzer.path_identity import is_within

#: Caps against a crafted tree filling the disk or the inode table. The
#: largest corpus tree (posthog, 2026-11-15) has 69,882 files, 854 MB and a
#: longest path of 242 characters; each cap leaves a wide margin.
MAX_TREE_ENTRIES = 500_000
MAX_TREE_BYTES = 8 * 1024 ** 3
MAX_PATH_BYTES = 1024
#: The longest file name the common file systems accept.
MAX_COMPONENT_BYTES = 255

_EXECUTABLE_MODE = b"100755"
_FILE_MODES = frozenset({b"100644", _EXECUTABLE_MODE})
_SYMLINK_MODE = b"120000"
_GITLINK_MODE = b"160000"
_DIRECTORY_PERMISSIONS = 0o700
_FILE_PERMISSIONS = {True: 0o700, False: 0o600}
_WINDOWS_DEVICES = frozenset(
    {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
)
#: ``.git`` and its NTFS short name, compared case-insensitively.
_GIT_DIR_NAMES = frozenset({".git", "git~1"})
_NO_FOLLOW_DIR_FD = all(hasattr(os, name) for name in ("O_NOFOLLOW", "O_DIRECTORY")) and {
    os.open, os.mkdir,
} <= os.supports_dir_fd


class TreeTooLarge(GitError):
    """The tree exceeds an export cap; nothing past the cap is written."""


@dataclass
class ExportReport:
    written: int = 0
    refused: list[tuple[str, str]] = field(default_factory=list)
    symlinks_skipped: list[str] = field(default_factory=list)
    submodules_skipped: list[str] = field(default_factory=list)


def _component_reason(part: str) -> str | None:
    if part in ("", ".", ".."):
        return "empty, . or .. component"
    if "\0" in part or ":" in part or "\\" in part:
        return "NUL, colon or backslash"
    if part.endswith((".", " ")):
        return "ends with a dot or space"
    if len(part.encode("utf-8", "surrogateescape")) > MAX_COMPONENT_BYTES:
        return "component too long"
    if part.split(".", 1)[0].rstrip(" ").upper() in _WINDOWS_DEVICES:
        return "reserved device name"
    if part.lower() in _GIT_DIR_NAMES:
        return ".git component"
    return None


def refusal_reason(path: str) -> str | None:
    """Why ``path`` (a tree entry, repository-relative) must not be
    written, or ``None`` when it may."""
    if len(path.encode("utf-8", "surrogateescape")) > MAX_PATH_BYTES:
        return "path too long"
    windows = PureWindowsPath(path)
    if path.startswith("/") or windows.drive or windows.anchor:
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

    def close(self) -> None:
        if self.base_fd is not None:
            os.close(self.base_fd)

    def _open_parent(self, parts: list[str]) -> int:
        fd = os.dup(self.base_fd)
        try:
            for part in parts:
                try:
                    os.mkdir(part, _DIRECTORY_PERMISSIONS, dir_fd=fd)
                except FileExistsError:
                    pass
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
        except BaseException:
            os.close(fd)
            raise
        return fd

    def _open_by_path(self, parents: list[str], name: str, flags: int, mode: int) -> int:
        target = self.base.joinpath(*parents)
        target.mkdir(parents=True, exist_ok=True, mode=_DIRECTORY_PERMISSIONS)
        if not is_within(os.path.realpath(target), str(self.base)):
            raise OSError(f"parent of {name!r} resolves outside the export")
        return os.open(target / name, flags, mode)

    def write(self, path: str, data: bytes, executable: bool) -> None:
        *parents, name = path.split("/")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        mode = _FILE_PERMISSIONS[executable]
        if self.base_fd is None:
            fd = self._open_by_path(parents, name, flags, mode)
        else:
            parent = self._open_parent(parents)
            try:
                fd = os.open(name, flags, mode, dir_fd=parent)
            finally:
                os.close(parent)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)


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


def _write_batch(writer: _ContainedWriter, batch: list, blobs: list[bytes], report: ExportReport) -> None:
    for (mode, _oid, path), data in zip(batch, blobs):
        try:
            writer.write(path, data, mode == _EXECUTABLE_MODE)
            report.written += 1
        except OSError as exc:
            # A name that collides with another (case-insensitive file
            # system) or with a directory: recorded, never overwritten.
            report.refused.append((path, f"not writable inside the export: {exc.strerror or exc}"))


def export_tree(repo_root: str | os.PathLike[str], sha: str, dest: str | os.PathLike[str]) -> ExportReport:
    """Write the regular files of ``sha``'s tree under ``dest`` (an empty
    directory the engine created); returns what was written and recorded."""
    root, base = os.fspath(repo_root), Path(dest)
    if any(base.iterdir()):
        raise OSError(f"export destination is not empty: {base}")
    report = ExportReport()
    files = _plan(_entries(root, sha), report)
    writer, total = _ContainedWriter(base), 0
    try:
        for start in range(0, len(files), OBJECTS_PER_BATCH):
            batch = files[start:start + OBJECTS_PER_BATCH]
            blobs = read_objects(root, [oid for _m, oid, _p in batch], b"blob")
            total += sum(len(b) for b in blobs)
            if total > MAX_TREE_BYTES:
                raise TreeTooLarge(f"tree {sha} holds more than {MAX_TREE_BYTES} bytes")
            _write_batch(writer, batch, blobs, report)
    finally:
        writer.close()
    return report
