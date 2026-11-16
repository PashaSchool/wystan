"""Has a submodule moved? Answered without running git inside it.

The runner never lets git look inside a submodule (``--ignore-submodules=all``
on the commands that read the working tree): a submodule's own config,
hooks and filters would apply there. dev's ``git diff HEAD`` and ``git
status`` reported a submodule checked out at another commit than the
superproject records; this restores that one fact by reading the
submodule's HEAD as plain files (``<sub>/.git`` -> ``HEAD`` -> loose ref or
``packed-refs``), with the guarded, bounded reads of ``git_discovery``.
Not restored: modified or untracked content inside a submodule (that needs
git to run there).
"""

from __future__ import annotations

import os
import re

from wystan.analyzer.git_discovery import read_pointer
from wystan.analyzer.git_runner import GitError, run_git

_GITLINK = b"160000"
_GITDIR_PREFIX = "gitdir:"
_SYMREF_PREFIX = "ref:"
_HEX = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
#: ``packed-refs`` of a large submodule holds many refs; read no more.
_PACKED_REFS_BYTES = 8 << 20


def _gitlinks(root: str, *source: str) -> dict[str, str]:
    """path -> recorded commit of every submodule entry of the index
    (``ls-files -s``) or of a tree (``ls-tree -r <tree>``). Both are limited
    to ``root`` and relative to it (no ``--full-tree``), so a scan of a
    subdirectory compares like with like."""
    args = ("ls-tree", "-r", "-z", *source) if source else ("ls-files", "-s", "-z")
    out = run_git(root, *args).stdout
    links = {}
    for record in out.split(b"\0"):
        meta, _, path = record.partition(b"\t")
        fields = meta.split(b" ")
        if fields and fields[0] == _GITLINK:
            # ls-tree: "<mode> <type> <oid>"; ls-files -s: "<mode> <oid> <stage>"
            links[path.decode("utf-8", "surrogateescape")] = (fields[2] if source else fields[1]).decode()
    return links


def _git_dir(work: str) -> str | None:
    dot_git = os.path.join(work, ".git")
    if os.path.isdir(dot_git) and not os.path.islink(dot_git):
        return dot_git
    pointer = read_pointer(dot_git)
    if pointer and pointer.startswith(_GITDIR_PREFIX):
        return os.path.normpath(os.path.join(work, pointer[len(_GITDIR_PREFIX):].strip()))
    return None


def _ref_path_is_plain(ref: str) -> bool:
    parts = ref.split("/")
    return ref.startswith("refs/") and all(p not in ("", ".", "..") for p in parts) and "\\" not in ref


def _resolve(git_dir: str, ref: str) -> str | None:
    if not _ref_path_is_plain(ref):
        return None
    common = os.path.normpath(os.path.join(git_dir, (read_pointer(os.path.join(git_dir, "commondir")) or ".")))
    for base in (git_dir, common):
        loose = read_pointer(os.path.join(base, *ref.split("/")))
        if loose and _HEX.fullmatch(loose):
            return loose
    packed = read_pointer(os.path.join(common, "packed-refs"), _PACKED_REFS_BYTES) or ""
    for line in packed.splitlines():
        oid, _, name = line.partition(" ")
        if name == ref and _HEX.fullmatch(oid):
            return oid
    return None


def checked_out_commit(work: str) -> str | None:
    """The commit a submodule's working tree has checked out, or ``None``
    when it is not initialised or cannot be read."""
    git_dir = _git_dir(work)
    head = read_pointer(os.path.join(git_dir, "HEAD")) if git_dir else None
    if not head:
        return None
    if _HEX.fullmatch(head):
        return head
    if head.startswith(_SYMREF_PREFIX):
        return _resolve(git_dir, head[len(_SYMREF_PREFIX):].strip())
    return None


def moved_submodules(root: str) -> list[tuple[str, str, str]]:
    """``(path, recorded, checked out)`` for every submodule whose HEAD tree,
    index and checked-out commit do not all agree, sorted by path."""
    try:
        staged, committed = _gitlinks(root), _gitlinks(root, "HEAD")
    except GitError:
        return []
    moved = []
    for path in sorted(set(staged) | set(committed)):
        checked_out = checked_out_commit(os.path.join(root, *path.split("/")))
        recorded = committed.get(path, "")
        current = checked_out or staged.get(path, "")
        if recorded != staged.get(path, "") or (checked_out and checked_out != staged.get(path, "")):
            moved.append((path, recorded, current))
    return moved
