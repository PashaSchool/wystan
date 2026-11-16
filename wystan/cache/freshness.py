"""Detect how stale a feature map is vs the current git state.

Used by the MCP server to warn AI agents and by CLI `refresh` to
decide whether any work is needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from wystan.analyzer.git_runner import GitAnswerUnavailable, GitError, revision, run_git
from wystan.models.types import FeatureMap


@dataclass
class FreshnessReport:
    is_stale: bool
    current_sha: str
    scanned_sha: str
    commits_behind: int
    changed_files_count: int
    has_new_files: bool
    days_since_scan: int

    def to_dict(self) -> dict:
        return {
            "is_stale": self.is_stale,
            "current_sha": self.current_sha[:8],
            "scanned_sha": self.scanned_sha[:8] if self.scanned_sha else "",
            "commits_behind": self.commits_behind,
            "changed_files": self.changed_files_count,
            "has_new_files": self.has_new_files,
            "days_since_scan": self.days_since_scan,
        }


def check_freshness(
    feature_map: FeatureMap,
    repo_path: str = ".",
) -> FreshnessReport:
    """Compare feature map's last_scanned_sha to the current git HEAD.

    Reports commit count behind and rough file-change count. Safe to
    call often — only spawns git commands, no LLM.
    """
    current_sha = _git_rev_parse(repo_path)
    scanned_sha = feature_map.last_scanned_sha or ""

    days_since = 0
    if feature_map.analyzed_at:
        from datetime import datetime, timezone
        delta = datetime.now(tz=timezone.utc) - feature_map.analyzed_at
        days_since = max(0, delta.days)

    if not scanned_sha or not current_sha:
        # Legacy map or git unavailable — assume fresh enough
        return FreshnessReport(
            is_stale=False,
            current_sha=current_sha or "",
            scanned_sha=scanned_sha,
            commits_behind=0,
            changed_files_count=0,
            has_new_files=False,
            days_since_scan=days_since,
        )

    if scanned_sha == current_sha:
        return FreshnessReport(
            is_stale=False,
            current_sha=current_sha,
            scanned_sha=scanned_sha,
            commits_behind=0,
            changed_files_count=0,
            has_new_files=False,
            days_since_scan=days_since,
        )

    behind = _count_commits(scanned_sha, current_sha, repo_path)
    changed, has_new = _diff_files(scanned_sha, current_sha, repo_path, feature_map)

    return FreshnessReport(
        is_stale=True,
        current_sha=current_sha,
        scanned_sha=scanned_sha,
        commits_behind=behind,
        changed_files_count=len(changed),
        has_new_files=has_new,
        days_since_scan=days_since,
    )


#: Freshness is a quick probe; a slow repository reads as "unknown".
_REV_PARSE_TIMEOUT_SEC = 5.0
_RANGE_TIMEOUT_SEC = 10.0


def _git_rev_parse(repo_path: str) -> str:
    try:
        return run_git(repo_path, "rev-parse", "HEAD", timeout=_REV_PARSE_TIMEOUT_SEC).universal_text.strip()
    except GitError:
        return ""


def _count_commits(from_sha: str, to_sha: str, repo_path: str) -> int:
    try:
        out = run_git(
            repo_path, "rev-list", "--count", f"{revision(from_sha)}..{revision(to_sha)}",
            timeout=_RANGE_TIMEOUT_SEC,
        ).universal_text.strip()
        return int(out)
    except (GitError, ValueError) as exc:
        raise GitAnswerUnavailable(f"commits between {from_sha} and {to_sha} unavailable: {exc}") from exc


def _diff_files(
    from_sha: str,
    to_sha: str,
    repo_path: str,
    feature_map: FeatureMap,
) -> tuple[set[str], bool]:
    """Returns (changed_files, has_new_files).

    A file is "new" if it doesn't belong to any feature in the map —
    a strong signal that features might need re-detection, not just
    metric updates.
    """
    try:
        # Plumbing: what `git diff --name-only A..B` printed (renames on),
        # without the porcelain that may refresh the clone's index.
        out = run_git(
            repo_path, "diff-tree", "-r", "-M", "--name-only", revision(from_sha), revision(to_sha),
            timeout=_RANGE_TIMEOUT_SEC,
        ).universal_text
    except GitError as exc:
        # Not "nothing changed": the caller must not treat the map as fresh.
        raise GitAnswerUnavailable(f"files changed between {from_sha} and {to_sha} unavailable: {exc}") from exc

    changed = {line.strip() for line in out.splitlines() if line.strip()}
    if not changed:
        return set(), False

    tracked = set()
    for f in feature_map.features:
        tracked.update(f.paths)
        for fl in f.flows:
            tracked.update(fl.paths)

    has_new = bool(changed - tracked)
    return changed, has_new
