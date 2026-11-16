"""Has a submodule moved? Answered without running git inside it.

The runner never lets git look inside a submodule (``--ignore-submodules=all``
on the commands that read the working tree): a submodule's own config,
hooks and filters would apply there. dev's ``git diff HEAD`` and ``git
status`` reported a submodule checked out at another commit than the
superproject records; this restores that one fact by reading the
submodule's HEAD as plain files (``<sub>/.git`` -> ``HEAD`` -> loose ref or
``packed-refs``) through the guarded reader, with the scan root as the one
boundary. A submodule whose ``.git``, git directory or common directory
lies outside the scan root (the usual layout puts the git directory in the
superproject's ``.git/modules``: inside for a scan of the repository top,
outside for a subdirectory scan; or a ``.git`` naming another repository, or
a submodule directory that is a link) is "state unknown": nothing there is
read, the path is neither moved nor clean, and the caller records it.
Not restored: modified or untracked content inside a submodule.
"""

from __future__ import annotations

import os
import re

from wystan.analyzer.git_discovery import read_pointer
from wystan.analyzer.git_runner import GitError, run_git
from wystan.analyzer.path_identity import is_within

_GITLINK = b"160000"
_GITDIR_PREFIX = "gitdir:"
_SYMREF_PREFIX = "ref:"
_HEX = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
#: ``packed-refs`` of a large submodule holds many refs; read no more.
_PACKED_REFS_BYTES = 8 << 20


class _Unknown:
    """A submodule whose state cannot be read inside the scan root."""


UNKNOWN = _Unknown()


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


def _git_dir(work: str, root: str) -> str | None | _Unknown:
    """The submodule's git directory inside ``root``, ``None`` when it is not
    initialised, :data:`UNKNOWN` when it (or its ``.git``) is outside."""
    dot_git = os.path.join(work, ".git")
    if not os.path.lexists(dot_git):
        return None
    if not is_within(dot_git, root):
        return UNKNOWN
    if os.path.isdir(dot_git) and not os.path.islink(dot_git):
        return dot_git
    pointer = read_pointer(dot_git, root)
    if not pointer or not pointer.startswith(_GITDIR_PREFIX):
        return None
    git_dir = os.path.normpath(os.path.join(work, pointer[len(_GITDIR_PREFIX):].strip()))
    return git_dir if is_within(git_dir, root) else UNKNOWN


def _ref_path_is_plain(ref: str) -> bool:
    parts = ref.split("/")
    return ref.startswith("refs/") and all(p not in ("", ".", "..") for p in parts) and "\\" not in ref


def _common_dir(git_dir: str, root: str) -> str:
    """The common directory a linked git directory names (itself when it
    names none); the caller checks it lies inside ``root``."""
    named = read_pointer(os.path.join(git_dir, "commondir"), root) or "."
    return os.path.normpath(os.path.join(git_dir, named.strip()))


def _resolve(git_dir: str, common: str, ref: str, root: str) -> str | None:
    if not _ref_path_is_plain(ref):
        return None
    for base in (git_dir, common):
        loose = read_pointer(os.path.join(base, *ref.split("/")), root)
        if loose and _HEX.fullmatch(loose):
            return loose
    packed = read_pointer(os.path.join(common, "packed-refs"), root, _PACKED_REFS_BYTES) or ""
    for line in packed.splitlines():
        oid, _, name = line.partition(" ")
        if name == ref and _HEX.fullmatch(oid):
            return oid
    return None


def checked_out_commit(work: str, root: str | None = None) -> str | None | _Unknown:
    """The commit a submodule's working tree has checked out; ``None`` when
    it is not initialised or cannot be read; :data:`UNKNOWN` when its git
    directory lies outside the scan root ``root`` (default: the directory
    that contains the submodule)."""
    boundary = root if root is not None else os.path.dirname(os.path.realpath(work))
    git_dir = _git_dir(work, boundary)
    if git_dir is None or git_dir is UNKNOWN:
        return git_dir
    # A common directory outside the root makes the whole repository
    # outside it, even when HEAD itself (detached) could be read inside.
    common = _common_dir(git_dir, boundary)
    if not is_within(common, boundary):
        return UNKNOWN
    head = read_pointer(os.path.join(git_dir, "HEAD"), boundary)
    if not head:
        return None
    if _HEX.fullmatch(head):
        return head
    if head.startswith(_SYMREF_PREFIX):
        return _resolve(git_dir, common, head[len(_SYMREF_PREFIX):].strip(), boundary)
    return None


def submodule_states(root: str) -> tuple[list[tuple[str, str, str]], list[str]]:
    """``(moved, unknown)``: ``(path, recorded, checked out)`` for every
    submodule whose HEAD tree, index and checked-out commit do not all agree,
    and the paths whose state cannot be read inside ``root``; sorted."""
    try:
        staged, committed = _gitlinks(root), _gitlinks(root, "HEAD")
    except GitError:
        return [], []
    moved, unknown = [], []
    for path in sorted(set(staged) | set(committed)):
        checked_out = checked_out_commit(os.path.join(root, *path.split("/")), root)
        if checked_out is UNKNOWN:
            unknown.append(path)
            continue
        recorded = committed.get(path, "")
        current = checked_out or staged.get(path, "")
        if recorded != staged.get(path, "") or (checked_out and checked_out != staged.get(path, "")):
            moved.append((path, recorded, current))
    return moved, unknown


def moved_submodules(root: str) -> list[tuple[str, str, str]]:
    return submodule_states(root)[0]


def unread_submodules(root: str) -> list[str]:
    return submodule_states(root)[1]
