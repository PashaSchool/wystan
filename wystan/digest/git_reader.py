"""
Standalone git reader for daily digest.

Reads commits merged to main/master for a given date. Its only engine
imports are the hardened git runner and the repository helpers built on it
(the commands are the ones GitPython ran, so the digest is unchanged).
"""

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

from wystan.analyzer.git_history import numstat_file_keys, raw_parents
from wystan.analyzer.git_repository import GitRepository, open_repository, origin_url
from wystan.analyzer.git_runner import object_name, revision, run_git

# Field and record separators of the pretty format (never in commit data).
_FIELD = "\x1f"
_RECORD = "\x1e"
_DIGEST_FORMAT = f"%H{_FIELD}%P{_FIELD}%an{_FIELD}%ae{_FIELD}%cI{_FIELD}%B{_RECORD}"
_DIGEST_FIELDS = 6
_DEFAULT_BRANCHES = ("main", "master")
_HEADS_PREFIX = "refs/heads/"


@dataclass
class DigestCommit:
    sha: str
    message: str
    author: str
    date: str  # ISO format
    files_changed: list[str] = field(default_factory=list)
    is_bug_fix: bool = False
    pr_number: int | None = None


_BUG_FIX_RE = re.compile(
    r"\bfix\b|\bbug\b|\bhotfix\b|\bpatch\b|\brevert\b|\bregression\b"
    r"|\bcrash\b|\berror\b|\bbroken\b|\bissue\b|\bdefect\b",
    re.IGNORECASE,
)
_FALSE_POSITIVE_RE = re.compile(
    r"\bfix\s+(?:typo|lint|format\w*|style|import|indent|spacing|test|docs?|merge|ci|build)\b",
    re.IGNORECASE,
)
_PR_MERGE_RE = re.compile(r"Merge pull request #(\d+)", re.IGNORECASE)
_PR_SQUASH_RE = re.compile(r"\(#(\d+)\)\s*(?:\n|$)")


def _is_bug_fix(message: str) -> bool:
    if not _BUG_FIX_RE.search(message):
        return False
    if _FALSE_POSITIVE_RE.search(message):
        return False
    return True


def _extract_pr(message: str) -> int | None:
    m = _PR_MERGE_RE.search(message)
    if m:
        return int(m.group(1))
    m = _PR_SQUASH_RE.search(message)
    if m:
        return int(m.group(1))
    return None


def _get_remote_url(repo: GitRepository) -> str:
    try:
        url = origin_url(repo)
        if url.startswith("git@"):
            url = re.sub(r"^git@([^:]+):", r"https://\1/", url)
        url = url.rstrip("/")
        if url.endswith(".git"):
            url = url[:-4]
        return url
    except Exception:
        return ""


def _has_branch(root: str, name: str) -> bool:
    found = run_git(root, "rev-parse", "--verify", "--quiet", f"{_HEADS_PREFIX}{name}", check=False)
    return found.returncode == 0


def _active_branch(root: str) -> str:
    """The checked-out branch; fails on a detached HEAD (as GitPython did)."""
    ref = run_git(root, "symbolic-ref", "HEAD").text.strip()
    return ref[len(_HEADS_PREFIX):] if ref.startswith(_HEADS_PREFIX) else ref


def _first_parent_records(root: str, branch: str, since: datetime, until: datetime) -> list[tuple]:
    """``iter_commits(branch, since, until, first_parent=True)``: sha,
    parents, author name, author email, committer date (ISO), message."""
    out = run_git(
        root, "log", "--first-parent", f"--since={since.isoformat()}", f"--until={until.isoformat()}",
        f"--pretty=format:{_DIGEST_FORMAT}", "-z", revision(branch), "--",
    ).text
    records = []
    for raw in out.split(_RECORD):
        parts = raw.lstrip("\0\n").split(_FIELD, _DIGEST_FIELDS - 1)
        if len(parts) == _DIGEST_FIELDS:
            sha, _grafted, author, email, committed, msg = parts
            records.append((sha, author, email, committed, msg))
    # Parents as the commit object names them (GitPython's view), not as
    # shallow grafts rewrite them.
    parents = raw_parents(root, [r[0] for r in records])
    return [(r[0], p, *r[1:]) for r, p in zip(records, parents)]


def _raw_diff_first_paths(raw: bytes) -> list[str]:
    """``a_path or b_path`` of each entry of a ``--raw -z`` diff, as
    GitPython parsed it: the source path of a rename or copy, else the path."""
    text = raw.decode("utf-8")
    _, _, text = text.partition(":")
    paths = []
    for entry in text.split("\x00:"):
        if not entry:
            continue
        meta, _, path = entry.partition("\x00")
        path = path.rstrip("\x00").strip("\n")
        if meta.split(None, 4)[4][0] in "CR":
            path = path.split("\x00", 1)[0]
        if path:
            paths.append(path)
    return paths


def _changed_files(root: str, sha: str, parents: tuple[str, ...]) -> list[str]:
    """Files of the commit against its first parent (renames detected), or
    the numstat keys of a root commit; empty when git fails."""
    try:
        if not parents:
            return numstat_file_keys(root, sha, parents)
        raw = run_git(
            root, "diff-tree", object_name(parents[0]), object_name(sha), "-r",
            "--abbrev=40", "--full-index", "-M", "--raw", "-z", "--no-color",
        ).stdout
        return _raw_diff_first_paths(raw)
    except Exception:
        return []


def get_daily_commits(
    repo_path: str,
    date: str,
    branch: str | None = None,
) -> dict:
    """Get all commits merged to main/master on a given date.

    Args:
        repo_path: Path to the git repository.
        date: Date string in YYYY-MM-DD format.
        branch: Branch name. Auto-detects main/master if None.

    Returns:
        Dict with repo info and commits list, ready for JSON serialization.
    """
    repo = open_repository(repo_path, search_parent_directories=False)
    root = repo.working_tree_dir
    remote_url = _get_remote_url(repo)

    # Resolve branch
    if not branch:
        branch = next((c for c in _DEFAULT_BRANCHES if _has_branch(root, c)), None)
        if not branch:
            branch = _active_branch(root)

    # Parse date range
    target = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    since = target.replace(hour=0, minute=0, second=0)
    until = target.replace(hour=23, minute=59, second=59)

    # Get commits on the branch for that date
    commits: list[DigestCommit] = []
    for record in _first_parent_records(root, branch, since, until):
        sha, parents, author, email, committed, msg = record
        msg = msg.strip()
        first_line = msg.split("\n")[0]
        commits.append(DigestCommit(
            sha=sha[:8],
            message=first_line,
            author=author or email,
            date=committed,
            files_changed=_changed_files(root, sha, parents),
            is_bug_fix=_is_bug_fix(first_line),
            pr_number=_extract_pr(msg),
        ))

    # Group by author
    authors: dict[str, int] = {}
    for c in commits:
        authors[c.author] = authors.get(c.author, 0) + 1

    # Group files by top-level directory
    dir_changes: dict[str, int] = {}
    for c in commits:
        for f in c.files_changed:
            parts = Path(f).parts
            top_dir = parts[0] if len(parts) > 1 else "(root)"
            dir_changes[top_dir] = dir_changes.get(top_dir, 0) + 1

    repo_name = Path(repo_path).resolve().name

    return {
        "repo_name": repo_name,
        "repo_path": str(Path(repo_path).resolve()),
        "remote_url": remote_url,
        "branch": branch,
        "date": date,
        "total_commits": len(commits),
        "bug_fixes": sum(1 for c in commits if c.is_bug_fix),
        "authors": dict(sorted(authors.items(), key=lambda x: -x[1])),
        "dir_changes": dict(sorted(dir_changes.items(), key=lambda x: -x[1])),
        "commits": [asdict(c) for c in commits],
    }
