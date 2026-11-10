"""Adapter: UI action registries.

An application that is one screen (an editor, a canvas) has no pages to
tell its features apart. What the user can do is declared in a registry of
actions, each with an id and a label:

    export const actionAlignTop = register({
      name: "alignTop",
      label: "labels.alignTop",
      perform: ...
    })

This adapter reads those registrations. A label is resolved through the
default-locale catalog when it is a key; an action whose label cannot be
resolved is reported without one.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from wystan.pipeline_v2.entry_points.record import KIND_ACTION, EntryPoint
from wystan.pipeline_v2.product_strings import _read_text
from wystan.pipeline_v2.ui_text import _load_catalog

__all__ = ["ADAPTER", "action_entries"]

ADAPTER = "ui-actions"
_SCRIPT_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".vue", ".svelte")
# A registration: a call whose object literal declares both an id and
# something to run.
_REGISTRATION = re.compile(
    r"\bregister\w*\(\s*\{(?P<body>.{0,600}?)\b(?:perform|execute|handler|run|callback)\b\s*[:(]",
    re.S,
)
_ID = re.compile(r"""\b(?:name|id)\s*:\s*['"]([\w.\-]{2,60})['"]""")
_LABEL = re.compile(r"""\b(?:label|title)\s*:\s*(?:\([^)]*\)\s*=>\s*)?(?:t\(\s*)?['"]([^'"\n]{2,80})['"]""")
_MAX_ACTIONS = 5_000


def _label(raw: str | None, catalog: dict[str, str]) -> str | None:
    if raw is None:
        return None
    if raw in catalog:
        return catalog[raw]
    return raw if " " in raw or raw[:1].isupper() else None


def action_entries(ctx: Any) -> list[EntryPoint]:
    """Actions the application registers for its users."""
    repo_path = Path(getattr(ctx, "repo_path", "."))
    files = sorted(getattr(ctx, "tracked_files", None) or [])
    catalog: dict[str, str] | None = None
    entries: dict[str, EntryPoint] = {}
    for rel in files:
        if not rel.endswith(_SCRIPT_SUFFIXES):
            continue
        text = _read_text(repo_path, rel) or ""
        if "register" not in text:
            continue
        for match in _REGISTRATION.finditer(text):
            identifier = _ID.search(match.group("body"))
            if identifier is None or len(entries) >= _MAX_ACTIONS:
                continue
            if catalog is None:
                catalog = _load_catalog(repo_path, files)
            raw = _LABEL.search(match.group("body"))
            label = _label(raw.group(1) if raw else None, catalog)
            entries.setdefault(identifier.group(1), EntryPoint(
                kind=KIND_ACTION, address=identifier.group(1), file=rel, label=label,
                label_source="catalog" if label else None, adapter=ADAPTER,
            ))
    return list(entries.values())
