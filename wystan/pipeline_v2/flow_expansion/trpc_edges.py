"""tRPC procedure edges for flow expansion.

A tRPC client call is not an import: a page calls
``trpc.document.inbox.find.useQuery(...)`` and never imports the file that
implements the procedure, so the import-driven call graph stops at the client
wrapper. This module resolves such calls to the procedure's defining symbol so
the flow can include the server code it runs.

Two steps, both deterministic and LLM-free:

  * :func:`build_procedure_table` parses every router definition
    (``router({...})`` / ``createTRPCRouter({...})`` / ``t.router({...})``)
    into ``dotted.path -> Procedure``. A key may hold an inline procedure, a
    nested router or plain object, or an identifier that refers to a router or
    a procedure defined in the same or an imported file.
  * :func:`find_procedure_calls` returns the procedures called from a slice of
    source.

Scope: TypeScript and JavaScript. Routers composed with a spread
(``...otherRouter``) are not followed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from wystan.framework_linkers.trpc_procedure import (
    _CALL_SITE as CALL_SITE_PATTERN,
    _find_matching_brace,
    _split_top_level_object,
)
from wystan.pipeline_v2.flow_expansion.span_recovery import (
    _resolve_module,
    _symbol_range_obj,
)

if TYPE_CHECKING:
    from wystan.pipeline_v2.flow_reach import ReachContext

__all__ = ["Procedure", "build_procedure_table", "find_procedure_calls"]

_TS_JS_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mts", ".mjs")
_IDENT = r"[A-Za-z_$][\w$]*"
_ROUTER_CALL = r"(?:createTRPCRouter|t\.router|router)"
_ROUTER_DEF = re.compile(
    rf"(?:export\s+)?(?:const|let|var)\s+({_IDENT})\s*=\s*{_ROUTER_CALL}\s*\(\s*\{{",
)
_INLINE_ROUTER = re.compile(rf"^{_ROUTER_CALL}\s*\(\s*\{{")
_IDENT_ONLY = re.compile(rf"^{_IDENT}$")
_NAMED_IMPORT = re.compile(
    rf"import\s+(?:type\s+)?(?:{_IDENT}\s*,\s*)?\{{([^}}]*)\}}\s*from\s*['\"]([^'\"]+)['\"]",
)
_ROUTER_HINTS = ("createTRPCRouter", "router(")
_MAX_NESTING = 12

RouterKey = tuple[str, str]  # (file, router variable name)


@dataclass(frozen=True)
class Procedure:
    """One tRPC procedure: where its code is."""

    path: str
    file: str
    symbol: str | None
    lines: tuple[int, int]


@dataclass(frozen=True)
class _Ref:
    """An identifier used as a router value, with the file it was written in."""

    file: str
    name: str


@dataclass(frozen=True)
class _Inline:
    """An inline procedure expression inside a router file."""

    file: str
    lines: tuple[int, int]


_Value = "_Ref | _Inline | dict[str, _Value]"


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, max(offset, 0)) + 1


def _parse_object(file: str, text: str, body: str, body_offset: int) -> dict:
    """Parse one router object body into ``key -> _Ref | _Inline | dict``."""
    tree: dict = {}
    cursor = 0
    for key, raw in _split_top_level_object(body):
        value = (raw or "").strip()
        if not key or key.startswith("..."):
            continue
        found = body.find(value, cursor) if value else -1
        if found >= 0:
            cursor = found + len(value)
        value_offset = body_offset + max(found, 0)
        if not value or value == key:
            tree[key] = _Ref(file, key)
        elif _IDENT_ONLY.match(value):
            tree[key] = _Ref(file, value)
        elif _INLINE_ROUTER.match(value) or value.startswith("{"):
            open_idx = value.index("{")
            close_idx = _find_matching_brace(value, open_idx)
            inner = value[open_idx + 1: close_idx - 1] if close_idx > open_idx else ""
            tree[key] = _parse_object(file, text, inner, value_offset + open_idx + 1)
        else:
            start = _line_of(text, value_offset)
            tree[key] = _Inline(file, (start, start + value.count("\n")))
    return tree


def _router_definitions(rctx: "ReachContext") -> dict[RouterKey, dict]:
    """Every router variable in the repository with its parsed object tree."""
    routers: dict[RouterKey, dict] = {}
    for file in sorted(rctx.signatures):
        if not file.endswith(_TS_JS_SUFFIXES):
            continue
        text = rctx.signatures[file].source or ""
        if not any(hint in text for hint in _ROUTER_HINTS):
            continue
        for match in _ROUTER_DEF.finditer(text):
            open_idx = match.end() - 1
            close_idx = _find_matching_brace(text, open_idx)
            if close_idx <= open_idx:
                continue
            body = text[open_idx + 1: close_idx - 1]
            routers[(file, match.group(1))] = _parse_object(file, text, body, open_idx + 1)
    return routers


def _import_bindings(rctx: "ReachContext", file: str) -> dict[str, tuple[str, str]]:
    """``local name -> (target file, original name)`` for a file's named imports."""
    text = rctx.signatures[file].source or ""
    bindings: dict[str, tuple[str, str]] = {}
    for match in _NAMED_IMPORT.finditer(text):
        target = _resolve_module(rctx, file, match.group(2))
        if target is None:
            continue
        for token in match.group(1).split(","):
            name = token.strip().removeprefix("type ").strip()
            if not name:
                continue
            original, _, local = name.partition(" as ")
            bindings[(local or original).strip()] = (target, original.strip())
    return bindings


class _Resolver:
    """Flattens router trees into dotted procedure paths."""

    def __init__(self, rctx: "ReachContext", routers: dict[RouterKey, dict]) -> None:
        self._rctx = rctx
        self._routers = routers
        self._bindings: dict[str, dict[str, tuple[str, str]]] = {}
        self.referenced: set[RouterKey] = set()

    def _locate(self, ref: _Ref) -> tuple[str, str]:
        """The file and name where ``ref`` is defined (itself when local)."""
        if (ref.file, ref.name) in self._routers:
            return ref.file, ref.name
        if ref.file not in self._bindings:
            self._bindings[ref.file] = _import_bindings(self._rctx, ref.file)
        return self._bindings[ref.file].get(ref.name, (ref.file, ref.name))

    def flatten(self, tree: dict, prefix: str, depth: int, out: dict[str, Procedure]) -> None:
        if depth > _MAX_NESTING:
            return
        for key in sorted(tree):
            value = tree[key]
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                self.flatten(value, path, depth + 1, out)
            elif isinstance(value, _Inline):
                out.setdefault(path, Procedure(path, value.file, None, value.lines))
            else:
                self._flatten_ref(value, path, depth, out)

    def _flatten_ref(self, ref: _Ref, path: str, depth: int, out: dict[str, Procedure]) -> None:
        file, name = self._locate(ref)
        nested = self._routers.get((file, name))
        if nested is not None:
            self.referenced.add((file, name))
            self.flatten(nested, path, depth + 1, out)
            return
        rng = _symbol_range_obj(self._rctx.signatures.get(file), name)
        if rng is not None:
            out.setdefault(path, Procedure(path, file, name, (rng.start_line, rng.end_line)))


def build_procedure_table(rctx: "ReachContext") -> dict[str, Procedure]:
    """``dotted.path -> Procedure`` for every tRPC procedure in the repository.

    Paths are keyed from each ROOT router (a router no other router refers
    to), which is how client code addresses them. Empty when the repository
    defines no router."""
    routers = _router_definitions(rctx)
    if not routers:
        return {}
    resolver = _Resolver(rctx, routers)
    per_router: dict[RouterKey, dict[str, Procedure]] = {}
    for key in sorted(routers):
        flat: dict[str, Procedure] = {}
        resolver.flatten(routers[key], "", 0, flat)
        per_router[key] = flat
    table: dict[str, Procedure] = {}
    roots = [key for key in sorted(routers) if key not in resolver.referenced]
    for key in roots or sorted(routers):
        for path, procedure in per_router[key].items():
            table.setdefault(path, procedure)
    return table


def find_procedure_calls(source_slice: str, table: dict[str, Procedure]) -> list[Procedure]:
    """Procedures called as ``<client>.<path>.<verb>(`` in ``source_slice``.

    Unknown paths are ignored. Each procedure is returned once, in order of
    first appearance."""
    if not table or not source_slice:
        return []
    found: list[Procedure] = []
    seen: set[str] = set()
    for match in CALL_SITE_PATTERN.finditer(source_slice):
        procedure = table.get(match.group(2))
        if procedure is None or procedure.path in seen:
            continue
        seen.add(procedure.path)
        found.append(procedure)
    return found
