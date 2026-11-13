"""Lines of code that are code: what the map reports and what "large" means.

The line count stage stamps every counted file's lines into ``loc``, and
every pass after it reads that number: to decide whether a feature survives,
what a model is told about it, where lines go when code changes owner. Those
decisions must not move because one of a feature's files turned out to be a
vocabulary or a bundle, so this module leaves them alone.

Non-code lines matter in one place only: what the map REPORTS as lines of
code (:func:`settle_code_lines`, the last step before the map is written).
No decision and no model request in the pipeline reads the result.

A file's non-code lines stay visible: they move from ``loc`` to
``artifact_ink_loc``, the channel the map already has for lines that exist
and are not product code.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "NON_CODE_SAMPLES",
    "non_code_lines_by_row",
    "settle_code_lines",
]

# Ledger key under which the settle step leaves its report once it has run.
_SETTLED = "code_lines_settled"

# How many of the largest non-code files the telemetry names. Enough to
# explain a total by eye; the counts and the per-class sums are exact.
NON_CODE_SAMPLES = 20


def _uuid(row: Any) -> str:
    return str(getattr(row, "uuid", "") or "")


def _is_developer(row: Any) -> bool:
    return getattr(row, "layer", "developer") != "product"


def _index_owner(path_index: Any, path: str) -> str:
    entry = (path_index or {}).get(path)
    if isinstance(entry, dict):
        return str(entry.get("feature_uuid") or "")
    return str(getattr(entry, "feature_uuid", "") or "")


def _holder(path: str, ledger: dict[str, Any], path_index: Any, rows: dict[str, Any]) -> str | None:
    """The developer row whose ``loc`` holds this file's lines now.

    Two passes move files after the line count and each keeps one record
    current: the capability split the ledger, fold-evidence demotion the
    path index. The row that a record names AND that still lists the file
    is the holder; a file neither record can place is left where it is."""
    for owner in ((ledger.get("owner_by_file") or {}).get(path), _index_owner(path_index, path)):
        row = rows.get(str(owner or ""))
        if row is not None and path in (getattr(row, "paths", None) or ()):
            return str(owner)
    return None


def non_code_lines_by_row(
    features: list[Any], ledger: dict[str, Any] | None, path_index: Any = None,
) -> dict[str, dict[str, int]]:
    """Developer row uuid -> ``{path: lines}`` of the non-code files whose
    lines its ``loc`` holds. Empty when the line count classed no file."""
    non_code = (ledger or {}).get("non_code") or {}
    if not non_code:
        return {}
    rows = {_uuid(f): f for f in features if _is_developer(f) and _uuid(f)}
    file_loc = ledger.get("file_loc") or {}
    held: dict[str, dict[str, int]] = {}
    for path in sorted(non_code):
        holder = _holder(path, ledger, path_index, rows)
        lines = int(file_loc.get(path, 0))
        if holder is not None and lines > 0:
            held.setdefault(holder, {})[path] = lines
    return held


def _move_to_ink(row: Any, lines: int) -> int:
    """Take up to ``lines`` out of the row's ``loc`` into its ink; returns
    what was taken (a row never goes below zero)."""
    current = getattr(row, "loc", None)
    if not isinstance(current, int) or isinstance(current, bool):
        return 0
    taken = min(lines, current)
    if taken <= 0:
        return 0
    row.loc = current - taken
    row.artifact_ink_loc = int(getattr(row, "artifact_ink_loc", None) or 0) + taken
    # Flow lines are a part of ``loc``; they cannot exceed what is left.
    flow_lines = getattr(row, "loc_flow", None)
    if isinstance(flow_lines, int) and flow_lines > row.loc:
        row.loc_flow = row.loc
    return taken


def _own_listed_lines(row: Any, ledger: dict[str, Any]) -> int:
    """Non-code lines a product feature with no developer rows holds
    through the files it lists itself. Such a feature's ``loc`` was summed
    from its own member files (a feature minted from a container's files,
    or one the line count expanded from its paths), not from developer
    rows, so no developer row's debit reaches it."""
    non_code = ledger.get("non_code") or {}
    file_loc = ledger.get("file_loc") or {}
    listed = {str(p) for p in getattr(row, "paths", None) or ()}
    listed |= {str(getattr(m, "path", "") or "") for m in getattr(row, "member_files", None) or ()}
    return sum(int(file_loc.get(path, 0)) for path in sorted(listed) if path in non_code)


def _report(held: dict[str, dict[str, int]], classes: dict[str, str]) -> dict[str, Any]:
    files = {path: lines for paths in held.values() for path, lines in paths.items()}
    by_class: dict[str, int] = {}
    for path, lines in files.items():
        by_class[classes[path]] = by_class.get(classes[path], 0) + lines
    largest = sorted(files, key=lambda path: (-files[path], path))
    return {
        "files": len(files),
        "lines": sum(files.values()),
        "by_class": {cls: by_class[cls] for cls in sorted(by_class)},
        "largest": [
            {"path": path, "class": classes[path], "lines": files[path]}
            for path in largest[:NON_CODE_SAMPLES]
        ],
    }


def _settle_developer_rows(features: list[Any], held: dict[str, dict[str, int]]) -> dict[str, int]:
    """Move each developer row's held non-code lines to its ink; returns
    developer row uuid -> lines moved, for the rows that moved any."""
    taken_by_row: dict[str, int] = {}
    for row in features:
        if not _is_developer(row):
            continue
        taken = _move_to_ink(row, sum(held.get(_uuid(row), {}).values()))
        if taken:
            taken_by_row[_uuid(row)] = taken
    return taken_by_row


def _settle_product_rows(
    features: list[Any], product_features: list[Any], ledger: dict[str, Any], taken_by_row: dict[str, int],
) -> int:
    """Move on each product row the lines its developer rows moved (or, for
    a row with none, its own listed non-code lines); returns what product
    features moved."""
    taken_by_product: dict[str, int] = {}
    homes: set[str] = set()
    for row in features:
        if _is_developer(row):
            home = str(getattr(row, "product_feature_id", "") or "")
            homes.add(home)
            taken_by_product[home] = taken_by_product.get(home, 0) + taken_by_row.get(_uuid(row), 0)
    taken_product = 0
    seen: set[int] = set()
    for row in list(product_features) + [f for f in features if not _is_developer(f)]:
        if id(row) in seen:
            continue
        seen.add(id(row))
        name = str(getattr(row, "name", "") or "")
        lines = taken_by_product.get(name, 0) if name in homes else _own_listed_lines(row, ledger)
        taken = _move_to_ink(row, lines)
        if any(row is pf for pf in product_features):
            taken_product += taken
    return taken_product


def _settle_lane_rows(lane_rows: list[dict[str, Any]] | None, features: list[Any], taken_by_row: dict[str, int]) -> None:
    """A lane row shows its developer row's lines (the lane sync copied
    them), so it moves exactly the lines its developer row moved. A lane row
    whose developer row moved nothing is not touched: ink its developer row
    carries by path convention was never on the lane row, and this step does
    not put it there. Rows are matched by name, as the lane sync matches."""
    by_name = {str(getattr(f, "name", "") or ""): f for f in features if _is_developer(f)}
    for row in lane_rows or ():
        developer = by_name.get(str(row.get("name") or ""))
        lines = taken_by_row.get(_uuid(developer)) if developer is not None else None
        current = row.get("loc")
        if not lines or not isinstance(current, int) or isinstance(current, bool):
            continue
        taken = min(lines, current)
        if taken > 0:
            row["loc"] = current - taken
            row["artifact_ink_loc"] = int(row.get("artifact_ink_loc") or 0) + taken


def settle_code_lines(
    features: list[Any],
    product_features: list[Any],
    ledger: dict[str, Any] | None,
    path_index: Any = None,
    loc_accounting: dict[str, Any] | None = None,
    *,
    lane_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Move the lines of non-code files from ``loc`` to ``artifact_ink_loc``
    on every feature and lane row that holds them, in place, and on no other
    row. Run once, when ownership is final and the lane is in sync, so that
    nothing is left to read ``loc`` but the map's readers.

    Returns telemetry, or ``None`` when no file was classed: a repository
    with no such file is written exactly as before. A second call changes
    nothing and returns the first call's telemetry: the lines have left
    ``loc`` and must not leave it again."""
    if ledger is not None and _SETTLED in ledger:
        return ledger[_SETTLED]
    held = non_code_lines_by_row(features, ledger, path_index)
    if not held:
        return None
    taken_by_row = _settle_developer_rows(features, held)
    taken_product = _settle_product_rows(features, product_features, ledger or {}, taken_by_row)
    _settle_lane_rows(lane_rows, features, taken_by_row)
    if loc_accounting is not None and isinstance(loc_accounting.get("sum_pf_owned"), int):
        loc_accounting["sum_pf_owned"] -= taken_product
        if "sum_artifact_ink" in loc_accounting:
            loc_accounting["sum_artifact_ink"] += taken_product
    report = _report(held, (ledger or {}).get("non_code") or {})
    report["rows_changed"] = len(taken_by_row)
    report["product_lines_moved"] = taken_product
    ledger[_SETTLED] = report
    return report
