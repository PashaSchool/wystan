"""``scan_meta.partial_clone``: what a partial clone could not provide.

The engine never fetches, so a blobless or treeless clone scans with what
its object store holds. This record says so: the clone's filter, how the
history was read (``git_partial``), and how many impact snapshots were
skipped for objects not in the store. It exists only for a partial clone,
so the map of an ordinary repository is unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from wystan.analyzer.git import history_note
from wystan.analyzer.git_partial import HISTORY_COMPLETE, partial_clone_filter
from wystan.analyzer.git_repository import GitError, open_repository


def partial_clone_record(repo_path: Path | str, impact_telemetry: dict[str, Any] | None) -> dict[str, Any] | None:
    try:
        repo = open_repository(repo_path)
    except (GitError, OSError):
        return None
    clone_filter = partial_clone_filter(repo.root)
    if clone_filter is None:
        return None
    record: dict[str, Any] = {"filter": clone_filter}
    record.update(history_note(repo) or {"history": HISTORY_COMPLETE})
    skipped = (impact_telemetry or {}).get("impact_skipped_missing_objects", 0)
    record["snapshots_skipped_missing_objects"] = skipped
    return record
