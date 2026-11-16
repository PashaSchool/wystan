"""What the guarded reader refused during a scan, for ``scan_meta``.

A refused read (a link out of the scanned tree, a FIFO or device, a file over
its cap, an open that failed) returns to its call site as an unreadable file,
so the map alone cannot show it. The reader records each refusal here, by
reason, under the boundary it read in; the scan takes the record at the end
(``repository_reads_block``) and puts it under ``scan_meta.repository_reads``.

Counts are of distinct repository-relative paths, so a file read by several
stages, or twice by racing threads, counts once and two runs on one input
give the same record. At most ``PATHS_LISTED`` paths are listed per reason,
the first in sorted order. A missing file (probes for optional manifests) and
a binary file stopped at its head, a directory where a file was expected, and a
file over a call site's own work bound below the guard's caps (it was skipped
before the guard too) are not refusals.

Scope: refusals are recorded under the root the reader was given and taken
by the scan whose root is that root or lies above it, so a refusal is reported
whether a site spelled the scan's root as a ``Path``, a ``str``, or a sub-root.
A scan clears that record when it starts (``begin_scan``); two scans of one
tree, or of nested trees, running at the same time in one process share it.

The block is emitted only when something was refused or the process uses the
fallback open path (``repo_open``): an ordinary repository's map keeps every
byte it had.
"""

from __future__ import annotations

import os
import threading

from wystan.analyzer.repo_open import OPEN_PATH_DIR_FD, open_path

__all__ = [
    "PATHS_LISTED",
    "REASON_NOT_REGULAR",
    "REASON_OPEN_ERROR",
    "REASON_OUTSIDE",
    "REASON_OVER_CAP",
    "REASONS",
    "begin_scan",
    "record_refusal",
    "repository_reads_block",
]

REASON_OUTSIDE = "outside_repository"
REASON_NOT_REGULAR = "not_regular_file"
REASON_OVER_CAP = "over_cap"
REASON_OPEN_ERROR = "open_error"
#: The reasons, in the order the block lists them.
REASONS = (REASON_OUTSIDE, REASON_NOT_REGULAR, REASON_OVER_CAP, REASON_OPEN_ERROR)
#: Paths named per reason: enough to find the cause, bounded on a crafted
#: repository with thousands of refused links.
PATHS_LISTED = 20

#: ``{absolute root a reader was given: {reason: {absolute path}}}``.
_records: dict[str, dict[str, set[str]]] = {}
_lock = threading.Lock()


def _absolute(path: os.PathLike[str] | str) -> str:
    return os.path.abspath(os.fspath(path))


def _within(root: str, scan_root: str) -> bool:
    return root == scan_root or root.startswith(scan_root.rstrip(os.sep) + os.sep)


def record_refusal(path: os.PathLike[str] | str, repo_root: os.PathLike[str] | str, reason: str) -> None:
    """Record that the read of ``path`` under ``repo_root`` was refused."""
    with _lock:
        _records.setdefault(_absolute(repo_root), {}).setdefault(reason, set()).add(_absolute(path))


def _take(scan_root: str) -> dict[str, set[str]]:
    """Under the lock: remove and merge every record of a root at or below
    ``scan_root`` (a reader given a sub-root, a ``str`` or a ``Path`` of the
    scan root, records under the same scan)."""
    merged: dict[str, set[str]] = {}
    for root in [root for root in _records if _within(root, scan_root)]:
        for reason, paths in _records.pop(root).items():
            merged.setdefault(reason, set()).update(paths)
    return merged


def begin_scan(scan_root: os.PathLike[str] | str) -> None:
    """Clear the record of the tree a scan starts on."""
    with _lock:
        _take(_absolute(scan_root))


def _relative(path: str, scan_root: str) -> str:
    """The path as the scanned tree spells it (no machine-specific prefix)."""
    return os.path.relpath(path, scan_root).replace(os.sep, "/")


def repository_reads_block(scan_root: os.PathLike[str] | str) -> dict | None:
    """The ``scan_meta.repository_reads`` value of the scan of
    ``scan_root``, or ``None`` when nothing was refused on the ``dir_fd``
    open path (module doc). Takes every record of the scan."""
    top = _absolute(scan_root)
    with _lock:
        found = {reason: {_relative(path, top) for path in paths} for reason, paths in _take(top).items()}
    used = open_path()
    if not any(found.values()) and used == OPEN_PATH_DIR_FD:
        return None
    return {
        "open_path": used,
        "refused": {reason: len(found.get(reason, ())) for reason in REASONS},
        "paths": {reason: sorted(found[reason])[:PATHS_LISTED] for reason in REASONS if found.get(reason)},
    }
