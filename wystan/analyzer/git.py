import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from rich.progress import Progress, SpinnerColumn, TextColumn

from wystan.analyzer.git_history import (
    FIELD_END,
    count_commits_since,
    head_commits,
    numstat_file_keys,
    split_records,
)
from wystan.analyzer.git_repository import (
    GitRepository,
    NotARepository,
    has_commit,
    head_blob_paths,
    open_repository,
    origin_url,
    repository_root,
)
from wystan.analyzer.git_runner import GitError, run_git
from wystan.models.types import Commit

logger = logging.getLogger(__name__)

# Regex to extract PR numbers from commit messages.
# Handles two common GitHub merge strategies:
#   "Merge pull request #123 from branch"  (merge commit)
#   "fix: something (#123)"                (squash merge)
_PR_MERGE_RE  = re.compile(r"Merge pull request #(\d+)", re.IGNORECASE)
_PR_SQUASH_RE = re.compile(r"\(#(\d+)\)\s*(?:\n|$)")

# Regex patterns that identify bug fix commits
BUG_FIX_PATTERNS = [
    r"\bfix\b", r"\bbug\b", r"\bhotfix\b", r"\bpatch\b",
    r"\brevert\b", r"\bregression\b", r"\bcrash\b", r"\berror\b",
    r"\bbroken\b", r"\bissue\b", r"\bdefect\b",
    r"\bresolve\b", r"\btimeout\b", r"\bnull\s*(?:pointer|check|ref)\b",
    r"\bundefined\b", r"\bNaN\b", r"\brace\s*condition\b",
    r"\bdeadlock\b", r"\bmemory\s*leak\b", r"\boverflow\b",
]

BUG_FIX_REGEX = re.compile("|".join(BUG_FIX_PATTERNS), re.IGNORECASE)

# Patterns that indicate a "fix" commit is NOT a real bug fix
_FALSE_POSITIVE_PATTERNS = [
    r"\bfix\s+(?:typo|lint|format\w*|style|import|indent|spacing|whitespace)\b",
    r"\bfix\s+(?:test|spec|mock|snapshot)\b",
    r"\bfix\s+(?:docs?|readme|comment|changelog)\b",
    r"\bfix\s+(?:merge|conflict|rebase)\b",
    r"\bfix\s+(?:ci|pipeline|build|deploy)\b",
]
_FALSE_POSITIVE_REGEX = re.compile("|".join(_FALSE_POSITIVE_PATTERNS), re.IGNORECASE)

# Approximate seconds per commit based on profiling (git stats I/O)
_SECONDS_PER_COMMIT = 0.008
# Approximate seconds per LLM call for flow detection (one call per feature)
_SECONDS_PER_FLOW_FEATURE = 4
# Rough estimate of features for flow duration estimate (before actual detection)
_ESTIMATED_FLOW_FEATURES = 20
# Commit-window cap. Raised 5k→7k (2026-06-14) so a busy repo's history window is
# not truncated before the Stage 6.95 feature-timeline is computed (infisical hit
# the old 5k cap over 365d). Paired with the worker's 180-day default window.
DEFAULT_MAX_COMMITS = 7_000


def is_bug_fix(message: str) -> bool:
    if not BUG_FIX_REGEX.search(message):
        return False
    # Exclude false positives: "fix typo", "fix lint", "fix test", etc.
    if _FALSE_POSITIVE_REGEX.search(message):
        return False
    return True


def extract_pr_number(message: str) -> int | None:
    """Extracts a GitHub PR number from a commit message, or None if not found."""
    m = _PR_MERGE_RE.search(message)
    if m:
        return int(m.group(1))
    m = _PR_SQUASH_RE.search(message)
    if m:
        return int(m.group(1))
    return None


def get_remote_url(repo: GitRepository) -> str:
    """
    Returns the GitHub base URL for the repo (without .git suffix), or empty string.
    Normalizes SSH remotes to HTTPS: git@github.com:org/repo.git → https://github.com/org/repo
    """
    try:
        url = _origin_url(repo)
        if url.startswith("git@"):
            url = re.sub(r"^git@([^:]+):", r"https://\1/", url)
        url = url.rstrip("/")
        if url.endswith(".git"):
            url = url[:-4]
        return url
    except Exception:
        return ""


def _origin_url(repo) -> str:
    if isinstance(repo, GitRepository):
        return origin_url(repo)
    # Any other handle (a caller's GitPython Repo) answers from its parsed
    # config; no git runs.
    return repo.remotes.origin.url


def normalize_subpath(src: str | None) -> str | None:
    """Return ``src`` as a clean posix prefix WITHOUT a trailing slash.

    ``"apps/web/"`` → ``"apps/web"``; ``"./apps/web"`` → ``"apps/web"``;
    ``""`` / ``"."`` / ``None`` → ``None`` (whole-repo, no scoping).
    """
    if not src:
        return None
    norm = Path(src).as_posix().strip("/")
    if norm in ("", "."):
        return None
    return norm


def scope_files_to_subpath(
    files: list[str], src: str | None
) -> list[str]:
    """Filter ``files`` to those under ``src`` and relativize them.

    ``["apps/web/page.tsx", "apps/worker/x.ts"]`` scoped to ``apps/web``
    → ``["page.tsx"]``. Matching is on path *segments* so ``apps/web``
    does NOT match a sibling ``apps/web-extra``. ``src=None`` returns
    ``files`` unchanged (whole-repo).
    """
    norm = normalize_subpath(src)
    if norm is None:
        return list(files)
    prefix = norm + "/"
    out: list[str] = []
    for f in files:
        posix = Path(f).as_posix()
        if posix == norm:
            # The subpath itself as a file (degenerate) — skip; it's a dir.
            continue
        if posix.startswith(prefix):
            out.append(posix[len(prefix):])
    return out


def load_repo(path: str) -> GitRepository:
    """The working tree containing ``path``, through the hardened runner."""
    try:
        repo = open_repository(path, search_parent_directories=True)
    except NotARepository:
        raise ValueError(f"'{path}' is not a git repository")

    if not has_commit(repo):
        raise ValueError(
            f"Repository at '{path}' has no commits yet. "
            "Make at least one commit before running analysis."
        )

    return repo


def estimate_commits(repo: GitRepository, days: int, max_commits: int = DEFAULT_MAX_COMMITS) -> int:
    """
    Quickly estimates the number of commits in the date range.
    Uses git rev-list --count which is near-instant regardless of repo size.
    """
    try:
        count = count_commits_since(repository_root(repo), f"{days} days ago")
        return min(count, max_commits)
    except Exception:
        return 0


def estimate_duration(commit_count: int, use_llm: bool = False, use_flows: bool = False) -> str:
    """Returns a human-readable time estimate for the analysis."""
    seconds = commit_count * _SECONDS_PER_COMMIT
    if use_llm:
        seconds += 5  # avg LLM API round-trip for feature detection
    if use_flows:
        seconds += _ESTIMATED_FLOW_FEATURES * _SECONDS_PER_FLOW_FEATURE  # ~20 features * 4 sec

    if seconds < 10:
        return "< 10 sec"
    elif seconds < 60:
        return f"~ {int(seconds)} sec"
    else:
        minutes = seconds / 60
        return f"~ {minutes:.1f} min"


def get_commits(
    repo: GitRepository,
    days: int = 365,
    max_commits: int = DEFAULT_MAX_COMMITS,
    src: str | None = None,
) -> list[Commit]:
    """Returns all commits from the last N days (up to max_commits).

    Sprint G perf fix (2026-05-20): replaces the per-commit
    ``commit.stats.files.keys()`` walk (4586 git subprocess calls on
    supabase, 240s wall) with a single ``git log --name-only`` invocation
    that streams all commits + their changed files in one pass (~6s on
    the same repo, ~40× speedup). Falls back to the per-commit walk on
    any git failure so unusual repo states (shallow clones,
    detached HEADs, custom worktrees) still work.

    Args:
        src: Optional repo-root-relative subdirectory (e.g. ``apps/web``).
            When given, history is scoped to that subtree: commits that
            touched no file under ``src`` are dropped, and every
            surviving commit's ``files_changed`` is filtered to the
            subtree AND relativized to it (``apps/web/page.tsx`` →
            ``page.tsx``). This keeps co-change / bug-ratio / coverage
            from computing over the whole monorepo. ``None`` preserves
            the whole-repo behaviour (back-compat).
    """
    fast = _get_commits_fast(repo, days=days, max_commits=max_commits, src=src)
    if fast is not None:
        return fast

    # Fallback — the original per-commit walk. Slow on large histories
    # but maximally compatible.
    commits = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task("Reading git history (fallback)...", total=None)

        root = repository_root(repo)
        shallow_logged = False
        for commit in head_commits(root, max_commits):
            commit_date = datetime.fromtimestamp(
                commit.committed, tz=timezone.utc
            )
            age_days = (datetime.now(tz=timezone.utc) - commit_date).days
            if age_days > days:
                break

            if commit.shallow_boundary and not shallow_logged:
                # Recorded once per walk: the parent of a boundary commit is
                # not in the clone, so it is diffed as git's shallow view
                # (a root), as the fast path lists it.
                logger.warning("git history: shallow_clone at %s; boundary commits diffed as roots", root)
                shallow_logged = True
            diff_parents = () if commit.shallow_boundary else commit.parents
            files_changed = numstat_file_keys(root, commit.sha, diff_parents)
            if src is not None:
                files_changed = scope_files_to_subpath(files_changed, src)
                if not files_changed:
                    # Commit touched nothing under the subpath — drop it
                    # so co-change / bug-ratio don't count it.
                    continue
            msg = commit.message.strip()
            commits.append(Commit(
                sha=commit.sha[:8],
                message=msg,
                author=commit.author,
                date=commit_date,
                files_changed=files_changed,
                is_bug_fix=is_bug_fix(msg),
                pr_number=extract_pr_number(msg),
            ))

    return commits


# The single history read of a scan; past this the per-commit fallback runs.
_LOG_TIMEOUT_SEC = 120.0
#: ``%H %ct %an %B``, each field NUL-terminated (``git_history.split_records``).
_FAST_FORMAT = f"%H{FIELD_END}%ct{FIELD_END}%an{FIELD_END}%B{FIELD_END}"
_FAST_FIELDS = 4
#: Pathspec magic: the path is relative to the top of the working tree.
_TOP_PATHSPEC = ":(top)"


def _get_commits_fast(
    repo: GitRepository,
    *,
    days: int,
    max_commits: int,
    src: str | None = None,
) -> list[Commit] | None:
    """Stream commit metadata + file lists via one ``git log --name-only -z``.

    Returns ``None`` on any git failure — the caller falls back to the
    per-commit walk. Stops parsing when the per-commit cutoff (``days``)
    is reached so we don't pay to scan deep history on long-lived repos.
    ``-- <subpath>`` makes ``git log`` list only commits that touched the
    subtree; ``--name-only`` still prints every file of such a commit, so
    the list is filtered and relativized in memory.
    """
    try:
        repo_path = repository_root(repo)
    except Exception:
        return None
    if not repo_path:
        return None
    cmd = ["log", f"--max-count={max_commits}", f"--since={days}.days.ago",
           f"--pretty=format:{_FAST_FORMAT}", "--name-only", "-z"]
    norm_src = normalize_subpath(src)
    if norm_src is not None:
        # git may run from the named subdirectory: the pathspec is the
        # top-relative subpath either way.
        cmd += ["--", f"{_TOP_PATHSPEC}{norm_src}"]
    try:
        result = run_git(repo_path, *cmd, timeout=_LOG_TIMEOUT_SEC, check=False)
    except GitError:
        return None
    if result.returncode != 0:
        return None
    # Read as dev's text-mode read did (universal newlines).
    return _commits_from_log(result.universal_text, days, norm_src)


def _commits_from_log(raw: str, days: int, norm_src: str | None) -> list[Commit]:
    """Commits of a fast-path log, newest first, until the ``days`` cutoff."""
    commits: list[Commit] = []
    now = datetime.now(tz=timezone.utc)
    for (sha, ct_raw, author, body), names in split_records(raw, _FAST_FIELDS, with_files=True):
        try:
            commit_date = datetime.fromtimestamp(int(ct_raw), tz=timezone.utc)
        except ValueError:
            continue
        if (now - commit_date).days > days:
            break  # newest first: every later commit is older
        files_changed = [f.strip() for f in names if f.strip()]
        if norm_src is not None:
            files_changed = scope_files_to_subpath(files_changed, norm_src)
            if not files_changed:
                # A rename-only commit can surface with an empty in-subtree
                # set after relativization — skip it.
                continue
        commit = _commit(sha, body.strip(), author, commit_date, files_changed)
        if commit is not None:
            commits.append(commit)
    return commits


def _commit(sha: str, msg: str, author: str, date: datetime, files: list[str]) -> Commit | None:
    try:
        return Commit(sha=sha[:8], message=msg, author=author, date=date, files_changed=files,
                      is_bug_fix=is_bug_fix(msg), pr_number=extract_pr_number(msg))
    except Exception:
        return None  # a malformed record shouldn't poison the whole list


def get_tracked_files(repo: GitRepository, src: str | None = None) -> list[str]:
    """
    Returns all tracked files in the repository.

    Args:
        repo: the repository handle from ``load_repo`` (any object with
            ``working_tree_dir`` is accepted; only its path is read).
        src: Optional subdirectory to restrict analysis to (e.g. 'src/').
             Files outside this path are excluded.
    """
    skip_extensions = {
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
        ".pdf", ".zip", ".tar", ".gz", ".lock", ".sum",
        ".woff", ".woff2", ".ttf", ".eot", ".map",
    }
    skip_dirs = {
        # Package managers / dependencies
        "node_modules", "vendor", "venv", ".venv",
        # Build output
        "dist", "build", ".next", "out", "coverage", "storybook-static",
        # Git internals
        ".git",
        # Python cache
        "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
        # Tooling / CI — not source code
        ".github", ".husky", ".storybook", ".circleci",
        # AI assistants / IDE configs leaking project-internal docs
        # into the scan (caused superset to detect a bogus
        # ``ai-assistant-protocol`` feature from .claude/projects/...).
        ".claude", ".cursor", ".idea", ".vscode", ".aider",
        # Lockfiles directories (some repos)
        ".turbo", ".cache", ".parcel-cache",
        # Test fixtures that produce noise
        ".devcontainer",
    }
    skip_filenames = {
        # Config and lockfiles at any depth
        "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
        ".eslintrc", ".prettierrc", ".editorconfig",
    }

    src_prefix = Path(src) if src else None

    files = []
    for item_path in head_blob_paths(repository_root(repo)):
        path = Path(item_path)

        # Filter to subdirectory if --src is specified
        if src_prefix and not path.is_relative_to(src_prefix):
            continue

        if any(part in skip_dirs for part in path.parts):
            continue
        if path.suffix.lower() in skip_extensions:
            continue
        if path.name in skip_filenames:
            continue

        files.append(item_path)

    return files
