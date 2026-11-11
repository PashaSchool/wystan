"""Collect agent units from every adapter and report them."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from wystan.pipeline_v2.agents.ai_sdk import ai_sdk_units
from wystan.pipeline_v2.agents.api_schema import api_schema_units
from wystan.pipeline_v2.agents.frameworks import framework_units
from wystan.pipeline_v2.agents.instruction_files import instruction_kind, instruction_unit
from wystan.pipeline_v2.agents.mcp_server import mcp_units
from wystan.pipeline_v2.agents.record import KIND_TOOL, AgentUnit
from wystan.pipeline_v2.agents.scope import is_excluded, scope_of
from wystan.pipeline_v2.agents.source import PY_SUFFIXES, SCRIPT_SUFFIXES, SourceFile
from wystan.pipeline_v2.product_strings import _read_text

__all__ = ["agent_report", "collect_agent_units"]

_ADAPTERS: tuple[Callable[[SourceFile], list[AgentUnit]], ...] = (
    ai_sdk_units, mcp_units, framework_units, api_schema_units,
)
# Cheap pre-check: a file with none of these words declares no unit.
_HINT = re.compile(r"tool|Tool|gent|input_schema|generateText|streamText")
_MODEL_CALL = re.compile(
    r"\b(?:generateText|streamText|generateObject|streamObject)\(|\.messages\.(?:create|stream)\(|"
    r"\.chat\.completions\.create\(|\.responses\.create\(",
)
_MAX_UNITS = 5_000
_SAMPLE = 12


def collect_agent_units(ctx: Any) -> tuple[list[AgentUnit], dict[str, Any]]:
    """Agent units the repository declares, one per identity, and the facts
    about the collection that are not units: files left out, names missing,
    bare model calls, adapter errors."""
    repo_path = Path(getattr(ctx, "repo_path", "."))
    files = sorted(getattr(ctx, "tracked_files", None) or [])
    tracked = frozenset(files)
    merged: dict[tuple[str, str, str], AgentUnit] = {}
    facts: dict[str, Any] = {"excluded": Counter(), "unnamed_tools": 0, "model_calls": 0, "adapter_errors": []}

    def keep(unit: AgentUnit) -> None:
        if unit.kind == KIND_TOOL and not unit.name:
            facts["unnamed_tools"] += 1           # a tool is never given a name it does not have
        elif len(merged) < _MAX_UNITS:
            merged.setdefault(unit.identity, unit)

    for rel in files:
        if instruction_kind(rel):
            text = _read_text(repo_path, rel)
            unit = instruction_unit(rel, text, scope_of(rel, tracked, instruction_file=True)) if text else None
            if unit:
                keep(unit)
            continue
        if not rel.endswith(SCRIPT_SUFFIXES + PY_SUFFIXES):
            continue
        reason = is_excluded(rel)
        if reason:
            facts["excluded"][reason] += 1
            continue
        text = _read_text(repo_path, rel)
        if not text or not _HINT.search(text):
            continue
        facts["model_calls"] += len(_MODEL_CALL.findall(text))
        source = SourceFile(rel=rel, text=text, scope=scope_of(rel, tracked))
        for adapter in _ADAPTERS:
            try:
                for unit in adapter(source):
                    keep(unit)
            except Exception as exc:  # noqa: BLE001 — one file never stops a scan
                facts["adapter_errors"].append(f"{adapter.__name__}: {rel}: {exc}"[:200])
    facts["excluded"] = dict(facts["excluded"])
    ordered = sorted(merged.values(), key=lambda u: (u.kind, u.file, u.line))
    return ordered, facts


def agent_report(units: list[AgentUnit], facts: dict[str, Any]) -> dict[str, Any]:
    """Counts for ``scan_meta.agents``. A report only."""
    by_kind: dict[str, list[AgentUnit]] = {}
    for unit in units:
        by_kind.setdefault(unit.kind, []).append(unit)
    kinds = {
        kind: {
            "total": len(rows),
            "by_scope": dict(Counter(row.scope for row in rows)),
            "by_adapter": dict(Counter(row.adapter for row in rows)),
            "described": sum(1 for row in rows if row.description),
            "tools_unresolved": sum(1 for row in rows if not row.tools_resolved),
            "sample": [{"name": row.name, "file": row.file, "line": row.line, "scope": row.scope} for row in rows[:_SAMPLE]],
        }
        for kind, rows in sorted(by_kind.items())
    }
    return {"total": len(units), "kinds": kinds, **facts}
