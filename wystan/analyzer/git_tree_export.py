"""Write the tree of one commit to a directory, from raw blobs.

Replaces ``git worktree add`` / ``git checkout`` for the impact snapshots.
A checkout applies the clone's content filters (smudge, process), its
hooks, and whatever configuration the new working tree's context selects
(``includeIf "gitdir:"``, a per-worktree config, submodules), which a
filter list computed for the main tree cannot cover. Here nothing is
checked out: the tree is listed (``ls-tree``) and each blob read raw
(``cat-file --batch`` applies no filter, textconv or end-of-line
conversion), so git never runs a content filter, by construction.

What it writes: every regular file (mode kept: executable or not) and an
empty directory per submodule, as a checkout leaves an uninitialised one.
Symbolic links are not created (the snapshot readers skip them). A path
that a checkout would refuse (``..``, ``.git``, empty or ``.`` components,
an absolute path) is refused here too and fails the export. Content is the
blob as stored, so a file whose attributes ask for ``eol=crlf``, ``ident``
or a ``working-tree-encoding`` is not converted.
"""

from __future__ import annotations

import os
from pathlib import Path

from wystan.analyzer.git_runner import GitError, object_name, run_git

#: Blobs read per ``cat-file --batch`` call: bounds the output one call holds
#: in memory (the runner's output cap applies per call).
_BLOBS_PER_BATCH = 2000
_EXECUTABLE_MODE = b"100755"
_FILE_MODES = frozenset({b"100644", _EXECUTABLE_MODE})
_GITLINK_MODE = b"160000"
_DIRECTORY_PERMISSIONS = 0o755
_FILE_PERMISSIONS = {True: 0o755, False: 0o644}
#: Path components git refuses to check out.
_REFUSED_COMPONENTS = frozenset({"", ".", ".."})
#: ``.git`` in any case, trailing dots and spaces ignored (git's own rule
#: on case-insensitive HFS/NTFS file systems).
_GIT_DIR_NAME = ".git"


class UnsafeTreePath(GitError):
    """The tree holds a path a checkout would refuse."""


def _checked_path(raw: bytes) -> str:
    path = raw.decode("utf-8", "surrogateescape")
    parts = path.split("/")
    if path.startswith("/") or "\\" in path or any(
        p in _REFUSED_COMPONENTS or p.rstrip(". ").lower() == _GIT_DIR_NAME for p in parts
    ):
        raise UnsafeTreePath(f"refusing tree path {path!r}")
    return path


def _entries(repo_root: str, sha: str) -> list[tuple[bytes, bytes, str]]:
    """``(mode, object id, path)`` of every non-tree entry of the commit."""
    listing = run_git(repo_root, "ls-tree", "-r", "-z", "--full-tree", object_name(sha)).stdout
    rows = []
    for record in listing.split(b"\0"):
        if record:
            meta, _, raw_path = record.partition(b"\t")
            mode, _kind, oid = meta.split(b" ")
            rows.append((mode, oid, _checked_path(raw_path)))
    return rows


def _read_blobs(repo_root: str, oids: list[bytes]) -> list[bytes]:
    """The raw contents of ``oids``, in order; a missing object fails."""
    out = run_git(repo_root, "cat-file", "--batch", stdin=b"".join(o + b"\n" for o in oids)).stdout
    blobs, offset = [], 0
    for oid in oids:
        header_end = out.index(b"\n", offset)
        header = out[offset:header_end].split(b" ")
        if len(header) != 3 or header[0] != oid or header[1] != b"blob":
            raise GitError(f"cat-file did not return blob {oid.decode()}: {header!r}")
        start = header_end + 1
        size = int(header[2])
        blobs.append(out[start:start + size])
        offset = start + size + 1  # the newline after each object
    return blobs


def _write_file(target: Path, data: bytes, executable: bool) -> None:
    target.parent.mkdir(parents=True, exist_ok=True, mode=_DIRECTORY_PERMISSIONS)
    # No O_EXCL: two names that differ only in case are one file on a
    # case-insensitive file system and the later wins, as in a checkout. No
    # link is ever created here, and O_NOFOLLOW refuses one regardless.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(target, flags, _FILE_PERMISSIONS[executable])
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)


def export_tree(repo_root: str | os.PathLike[str], sha: str, dest: str | os.PathLike[str]) -> int:
    """Write the tree of ``sha`` under the empty directory ``dest``; returns
    the number of files written."""
    root, base = os.fspath(repo_root), Path(dest)
    rows = _entries(root, sha)
    for mode, _oid, path in rows:
        if mode == _GITLINK_MODE:
            (base / path).mkdir(parents=True, exist_ok=True, mode=_DIRECTORY_PERMISSIONS)
    files = [(mode, oid, path) for mode, oid, path in rows if mode in _FILE_MODES]
    for start in range(0, len(files), _BLOBS_PER_BATCH):
        batch = files[start:start + _BLOBS_PER_BATCH]
        for (mode, _oid, path), data in zip(batch, _read_blobs(root, [oid for _m, oid, _p in batch])):
            _write_file(base / path, data, mode == _EXECUTABLE_MODE)
    return len(files)
