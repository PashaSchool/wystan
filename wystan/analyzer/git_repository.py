"""A git repository the engine scans, opened and read through the runner.

Replaces GitPython's ``Repo`` in the engine. GitPython cannot run git in a
fixed environment (``Git.execute`` always starts from ``os.environ``, so an
inherited ``GIT_DIR`` or ``GIT_EXTERNAL_DIFF`` reaches the child) and runs
``git version`` from ``PATH`` when it is imported. Each function here runs
the git command GitPython ran for the same question, so the answers are the
same for an ordinary repository.
"""

from __future__ import annotations

import os
from collections import deque
from dataclasses import dataclass

from wystan.analyzer.git_runner import GitError, run_git


class NotARepository(GitError, ValueError):
    """``path`` is not (the top level of) a git working tree."""


@dataclass(frozen=True)
class GitRepository:
    """A handle on a working tree. ``working_tree_dir`` is the logical path
    (the caller's spelling, as GitPython gave it), ``git_dir`` absolute."""

    working_tree_dir: str
    git_dir: str


def repository_root(repo: object) -> str | None:
    """The working tree (else git directory) of ``repo``: a
    :class:`GitRepository` or any object with GitPython's attributes."""
    root = getattr(repo, "working_tree_dir", None) or getattr(repo, "git_dir", None)
    return os.fspath(root) if root else None


def open_repository(path: str | os.PathLike[str], *, search_parent_directories: bool = True) -> GitRepository:
    """The working tree containing ``path`` (or only ``path`` itself when
    ``search_parent_directories`` is false, like ``Repo(path)``)."""
    start = os.path.abspath(os.fspath(path))
    if not os.path.exists(start):
        raise FileNotFoundError(start)
    try:
        lines = run_git(start, "rev-parse", "--show-cdup", "--absolute-git-dir").text.splitlines()
    except GitError as exc:
        raise NotARepository(f"{start!r} is not a git working tree") from exc
    if len(lines) != 2:
        raise NotARepository(f"{start!r} is not a git working tree")
    cdup, git_dir = lines
    if cdup and not search_parent_directories:
        raise NotARepository(f"{start!r} is not the top of a git working tree")
    return GitRepository(os.path.normpath(os.path.join(start, cdup)), git_dir)


def has_commit(repo: GitRepository) -> bool:
    """HEAD names a commit (false on an unborn branch)."""
    result = run_git(repo.working_tree_dir, "rev-parse", "--verify", "--quiet", "HEAD^{commit}", check=False)
    return result.returncode == 0


def head_sha(repo: GitRepository) -> str:
    return run_git(repo.working_tree_dir, "rev-parse", "HEAD").text.strip()


def origin_url(repo: GitRepository) -> str:
    """``remote.origin.url`` as configured (no ``insteadOf`` rewrite, like
    GitPython's config reader); raises when there is none."""
    return run_git(repo.working_tree_dir, "config", "--get", "remote.origin.url").text.strip()


def _children_by_directory(listing: bytes) -> dict[str, list[tuple[bytes, str]]]:
    """``ls-tree -r -t -z`` records grouped by parent directory, each group
    in tree order. Names decode like GitPython's (UTF-8, surrogateescape)."""
    children: dict[str, list[tuple[bytes, str]]] = {}
    for record in listing.split(b"\0"):
        if not record:
            continue
        meta, _, raw_path = record.partition(b"\t")
        kind = meta.split(b" ")[1]
        path = raw_path.decode("utf-8", "surrogateescape")
        children.setdefault(path.rpartition("/")[0], []).append((kind, path))
    return children


def head_blob_paths(root: str) -> list[str]:
    """Every blob path of the HEAD tree in GitPython's ``tree().traverse()``
    order (breadth first, tree order within a directory). Symbolic links
    are blobs; submodules (``commit`` entries) are not."""
    listing = run_git(root, "ls-tree", "-r", "-t", "-z", "--full-tree", "HEAD").stdout
    children = _children_by_directory(listing)
    blobs: list[str] = []
    pending = deque([""])
    while pending:
        for kind, path in children.get(pending.popleft(), ()):
            if kind == b"blob":
                blobs.append(path)
            elif kind == b"tree":
                pending.append(path)
    return blobs
