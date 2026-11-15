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
import re
from collections import deque
from dataclasses import dataclass

from wystan.analyzer.git_runner import GitError, GitFailed, UnsafeGit, run_git


class NotARepository(GitError, ValueError):
    """``path`` is not (the top level of) a git working tree."""


class ForeignOwnedRepository(GitError):
    """``path`` lies inside a repository another user owns, which the user
    did not name: git's ownership check stands, the engine says why."""


_DUBIOUS = re.compile(r"dubious ownership in repository at '([^']*)'")


@dataclass(frozen=True)
class GitRepository:
    """A handle on a repository. ``working_tree_dir`` is the logical path
    (the caller's spelling, as GitPython gave it) and ``None`` for a bare
    repository; ``git_dir`` absolute."""

    working_tree_dir: str | None
    git_dir: str
    #: The path the user named. git runs there (it finds the top itself), so
    #: ``safe.directory`` never names a repository the user did not name.
    named_root: str | None = None

    @property
    def root(self) -> str:
        """Where git runs: the named path, else the working tree, else the
        git directory."""
        return self.named_root or self.working_tree_dir or self.git_dir


def repository_root(repo: object) -> str | None:
    """The working tree (else git directory) of ``repo``: a
    :class:`GitRepository` or any object with GitPython's attributes."""
    root = (getattr(repo, "named_root", None) or getattr(repo, "working_tree_dir", None)
            or getattr(repo, "git_dir", None))
    return os.fspath(root) if root else None


def open_repository(path: str | os.PathLike[str], *, search_parent_directories: bool = True) -> GitRepository:
    """The working tree containing ``path`` (or only ``path`` itself when
    ``search_parent_directories`` is false, like ``Repo(path)``)."""
    start = os.path.abspath(os.fspath(path))
    if not os.path.exists(start):
        raise FileNotFoundError(start)
    stay_inside = not search_parent_directories
    bare, git_dir = _git_dir_of(start, stay_inside)
    if bare:
        # GitPython loaded a bare repository too (no working tree).
        if stay_inside and os.path.realpath(git_dir) != os.path.realpath(start):
            raise NotARepository(f"{start!r} is not the top of a git repository")
        return GitRepository(None, git_dir, start)
    cdup = _rev_parse(start, stay_inside, "--show-cdup")[0]
    if cdup and stay_inside:
        raise NotARepository(f"{start!r} is not the top of a git working tree")
    return GitRepository(os.path.normpath(os.path.join(start, cdup)), git_dir, start)


def _rev_parse(start: str, stay_inside: bool, *flags: str) -> list[str]:
    """``git rev-parse <flags>`` lines; a failure means "not a repository",
    except when no safe git exists or the enclosing repository belongs to
    another user, which the caller must see as is."""
    try:
        lines = run_git(start, "rev-parse", *flags, stay_inside=stay_inside).text.splitlines()
    except UnsafeGit:
        raise
    except GitFailed as exc:
        foreign = _DUBIOUS.search(exc.stderr)
        if foreign:
            raise ForeignOwnedRepository(
                f"this directory is inside a git repository owned by another user ({foreign.group(1)}); "
                "scan the repository's top level or pass it with --subpath"
            ) from exc
        raise NotARepository(f"{start!r} is not a git repository") from exc
    except GitError as exc:
        raise NotARepository(f"{start!r} is not a git repository") from exc
    if len(lines) != len(flags):
        raise NotARepository(f"{start!r} is not a git repository")
    return lines


def _git_dir_of(start: str, stay_inside: bool) -> tuple[bool, str]:
    is_bare, git_dir = _rev_parse(start, stay_inside, "--is-bare-repository", "--absolute-git-dir")
    return is_bare == "true", git_dir


def has_commit(repo: GitRepository) -> bool:
    """HEAD names a commit (false on an unborn branch)."""
    result = run_git(repo.root, "rev-parse", "--verify", "--quiet", "HEAD^{commit}", check=False)
    return result.returncode == 0


def head_sha(repo: GitRepository) -> str:
    return run_git(repo.root, "rev-parse", "HEAD").text.strip()


def origin_url(repo: GitRepository) -> str:
    """``remote.origin.url`` as configured (no ``insteadOf`` rewrite, like
    GitPython's config reader); raises when there is none."""
    return run_git(repo.root, "config", "--get", "remote.origin.url").text.strip()


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
