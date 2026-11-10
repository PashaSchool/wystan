"""Collect entry points from every adapter and report them."""

from __future__ import annotations

from collections import Counter
from typing import Any, Callable

from wystan.pipeline_v2.entry_points.record import EntryPoint

__all__ = ["collect_entry_points", "entry_report"]

_SAMPLE = 12
_MAX_DEPTH = 16


def collect_entry_points(
    adapters: list[Callable[[], list[EntryPoint]]],
) -> tuple[list[EntryPoint], list[str]]:
    """Entry points of every adapter, one per identity, and adapter errors.

    An adapter that fails contributes nothing and is named in the errors;
    it never stops the others."""
    merged: dict[tuple[str, str], EntryPoint] = {}
    errors: list[str] = []
    for adapter in adapters:
        try:
            produced = adapter()
        except Exception as exc:  # noqa: BLE001 — one adapter never stops a scan
            errors.append(f"{getattr(adapter, '__name__', 'adapter')}: {exc}"[:200])
            continue
        for entry in produced:
            merged.setdefault(entry.identity, entry)
    ordered = sorted(merged.values(), key=lambda e: (e.kind, e.address))
    return ordered, errors


def _depth(entry: EntryPoint, by_address: dict[str, EntryPoint]) -> int:
    depth, cursor = 0, entry
    while cursor.parent and cursor.parent in by_address and depth < _MAX_DEPTH:
        cursor = by_address[cursor.parent]
        depth += 1
    return depth


def entry_report(entries: list[EntryPoint], errors: list[str] = ()) -> dict[str, Any]:
    """Counts by kind for ``scan_meta.entry_points``."""
    by_kind: dict[str, list[EntryPoint]] = {}
    for entry in entries:
        by_kind.setdefault(entry.kind, []).append(entry)
    kinds: dict[str, Any] = {}
    for kind, rows in sorted(by_kind.items()):
        by_address = {row.address: row for row in rows}
        children = Counter(row.parent for row in rows if row.parent in by_address)
        kinds[kind] = {
            "total": len(rows),
            "labelled": sum(1 for row in rows if row.label),
            "roots": sum(1 for row in rows if row.parent not in by_address),
            "groups": len(children),
            "max_depth": max((_depth(row, by_address) for row in rows), default=0),
            "label_sources": dict(Counter(row.label_source for row in rows if row.label_source)),
            "sample": [
                {"address": row.address, "label": row.label, "parent": row.parent}
                for row in rows[:_SAMPLE]
            ],
        }
    return {"total": len(entries), "kinds": kinds, "adapter_errors": list(errors)}
