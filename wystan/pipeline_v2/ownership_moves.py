"""One implementation of "this code or journey changes owner".

Three passes move ownership late in the finalize phase: the demotion of
features with no name (with its veto), the capability split, and name or
reject. Each used to keep its own books, and each got them wrong once: lines
counted under two owners, lines counted under none, journeys deleted. The
rules they share live here.

  * A journey is never deleted by these passes. One that is not a product
    journey keeps its place in the journey layer with no parent and a mark;
    the split's unowned pool skips marked journeys.
  * Lines follow the developer feature that owns the files. When a developer
    feature changes product feature, the feature it leaves is debited and
    the one it joins is credited with the same number.
  * The total everyone checks is the same: lines of product features plus
    lines of developer features no living product feature owns.

A product feature's line count and the sum of its developer features' line
counts are stamped by different laws and differ on some features. Removing
such a feature moves the total by that difference; it is reported as
``ruler_gap`` instead of being hidden.
"""

from __future__ import annotations

from typing import Any, Iterable

__all__ = [
    "NOT_PRODUCT_SCOPE",
    "conservation_report",
    "credit_lines",
    "is_not_product",
    "mark_not_product",
    "product_layer_total",
    "sync_lane_rows",
]

# ``UserFlow.surface_scope`` of a journey judged not to be a product journey.
NOT_PRODUCT_SCOPE = "not_product"


def mark_not_product(journey: Any) -> dict[str, str]:
    """Take the journey out of the product layer without deleting it: no
    parent, marked. Returns the id and name for telemetry."""
    journey.product_feature_id = None
    journey.surface_scope = NOT_PRODUCT_SCOPE
    return {"id": str(journey.id), "name": str(getattr(journey, "name", "") or "")}


def is_not_product(journey: Any) -> bool:
    return getattr(journey, "surface_scope", None) == NOT_PRODUCT_SCOPE


def _lines(row: Any) -> int:
    return int(getattr(row, "loc", None) or 0)


def credit_lines(lines: int, source: Any | None, target: Any | None) -> None:
    """Move ``lines`` from one product feature's count to another's. Either
    side may be absent (code coming from or going to no product feature) or
    not yet counted (``loc`` is ``None``): that side is left alone."""
    if not lines:
        return
    if source is not None and getattr(source, "loc", None) is not None:
        source.loc = max(int(source.loc) - lines, 0)
    if target is not None and getattr(target, "loc", None) is not None:
        target.loc = int(target.loc) + lines


def product_layer_total(product_features: Iterable[Any], developer_features: Iterable[Any]) -> dict[str, int]:
    """Lines of product features, lines of developer features owned by no
    living product feature, and their sum."""
    features = list(product_features)
    alive = {f.name for f in features}
    product = sum(_lines(f) for f in features)
    unowned = sum(
        _lines(d) for d in developer_features if getattr(d, "product_feature_id", None) not in alive
    )
    return {"product_lines": product, "unowned_lines": unowned, "total": product + unowned}


def conservation_report(
    before: dict[str, int], after: dict[str, int], *,
    journeys: tuple[int, int], flows: tuple[int, int], ruler_gap: int = 0,
) -> dict[str, Any]:
    """What a pass conserved. ``ruler_gap`` is the part of the line change
    explained by removed features whose own count differed from their
    developer features' counts."""
    change = after["total"] - before["total"]
    return {
        "product_lines_before": before["product_lines"], "product_lines_after": after["product_lines"],
        "unowned_lines_before": before["unowned_lines"], "unowned_lines_after": after["unowned_lines"],
        "total_before": before["total"], "total_after": after["total"],
        "ruler_gap": ruler_gap,
        "journeys_before": journeys[0], "journeys_after": journeys[1],
        "flows_before": flows[0], "flows_after": flows[1],
        "conserved": change == ruler_gap and journeys[0] == journeys[1] and flows[0] == flows[1],
    }


def sync_lane_rows(lane_rows: list[dict[str, Any]] | None, features: Iterable[Any], product_features: Iterable[Any]) -> dict[str, int]:
    """Make the platform lane say what its developer features say now.

    Lane rows are written once, mid-phase. A developer feature that later
    gives files to a carved one, or gains an owner, left its row with the old
    numbers, and its lines were counted twice."""
    report = {"rows_updated": 0, "rows_removed": 0, "lines_removed": 0}
    if not lane_rows:
        return report
    alive = {f.name for f in product_features}
    by_name = {f.name: f for f in features if getattr(f, "layer", None) != "product"}
    kept: list[dict[str, Any]] = []
    for row in lane_rows:
        dev = by_name.get(row.get("name"))
        if dev is None:
            kept.append(row)
            continue
        if getattr(dev, "product_feature_id", None) in alive:
            report["rows_removed"] += 1
            report["lines_removed"] += int(row.get("loc") or 0)
            continue
        fresh = {
            "paths": list(dev.paths or []), "loc": getattr(dev, "loc", None),
            "loc_shared": getattr(dev, "loc_shared", None), "flows": len(getattr(dev, "flows", None) or []),
        }
        if any(row.get(key) != value for key, value in fresh.items()):
            report["lines_removed"] += int(row.get("loc") or 0) - int(fresh["loc"] or 0)
            report["rows_updated"] += 1
            row.update(fresh)
        kept.append(row)
    lane_rows[:] = kept
    return report
