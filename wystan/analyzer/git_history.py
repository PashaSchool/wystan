"""Commit history read through the runner, for the slow fallback walk.

These reproduce what GitPython returned for ``repo.iter_commits`` and
``commit.stats.files``: the same commits in the same order, and the file
keys of ``git diff --numstat --no-renames`` against the first parent (or
``git diff-tree --root`` for a root commit), so the fallback answers what
it answered before without GitPython.
"""

from __future__ import annotations

from dataclasses import dataclass

from wystan.analyzer.git_runner import object_name, run_git

# Field and record separators of the pretty format: ASCII unit and record
# separators never occur in commit data (same choice as ``_get_commits_fast``).
_FIELD = "\x1f"
_RECORD = "\x1e"
_RECORD_FORMAT = f"%H{_FIELD}%P{_FIELD}%ct{_FIELD}%an{_FIELD}%B{_RECORD}"
_RECORD_FIELDS = 5


@dataclass(frozen=True)
class CommitRecord:
    sha: str
    parents: tuple[str, ...]
    committed: int
    author: str
    message: str


def _parse_records(text: str) -> list[CommitRecord]:
    records: list[CommitRecord] = []
    for raw in text.split(_RECORD):
        raw = raw.lstrip("\0\n")
        if not raw:
            continue
        parts = raw.split(_FIELD, _RECORD_FIELDS - 1)
        if len(parts) < _RECORD_FIELDS:
            continue
        sha, parents, committed, author, message = parts
        records.append(CommitRecord(sha, tuple(parents.split()), int(committed), author, message))
    return records


def head_commits(root: str, max_count: int) -> list[CommitRecord]:
    """The newest ``max_count`` commits reachable from HEAD, newest first
    (``rev-list --max-count`` order, what ``iter_commits`` walked)."""
    out = run_git(
        root, "log", f"--max-count={int(max_count)}", f"--pretty=format:{_RECORD_FORMAT}", "-z", "HEAD", "--",
    )
    return _parse_records(out.text)


def count_commits_since(root: str, since: str) -> int:
    """``git rev-list --count --since=<since> HEAD``."""
    return int(run_git(root, "rev-list", "--count", f"--since={since}", "HEAD").text.strip())


def numstat_file_keys(root: str, sha: str, parents: tuple[str, ...]) -> list[str]:
    """The keys of GitPython's ``commit.stats.files``, in its order: the
    numstat half of a ``--raw --numstat`` diff against the first parent."""
    if parents:
        out = run_git(
            root, "diff", "--numstat", "--no-renames", "--raw",
            object_name(parents[0]), object_name(sha), "--",
        ).text
        lines = out.splitlines()
    else:
        out = run_git(root, "diff-tree", "--numstat", "--no-renames", "--root", "--raw", object_name(sha), "--").text
        lines = out.splitlines()[1:]  # the first line names the commit
    keys: dict[str, None] = {}
    for _raw, numstat in zip(lines, lines[len(lines) // 2:]):
        _insertions, _deletions, filename = numstat.split("\t")
        keys[filename.strip()] = None
    return list(keys)
