"""B82 — Stage-3.5 span-recovery for 1-LOC placeholder flows (flag-gated).

Two deterministic, no-LLM arms that recover the REAL body span of a flow
whose Stage-3.5 call graph collapsed to a single 1-line placeholder node
(the ``entry_range = (entry_line, entry_line)`` fallback in
:func:`call_graph.build_call_graph`, or an import edge that resolved only
to a file and so carried ``lines=None``).

Form A — re-export follow-through (SHIP arm)
--------------------------------------------
A barrel ``index.ts`` whose only content is ``export { X } from './Y'``
lines has NO import statements (``export … from`` is not an ``import``),
so :func:`flow_reach._file_edges` returns nothing and the flow renders as
its 1-line re-export placeholder. Form A parses the re-export statements,
resolves ``./Y`` to a real file, and REDIRECTS the entry seed to the
target symbol's real multi-line body — the cross-file analogue of D1
(``_entry_range_containing_line``). The redirected seed keeps depth 0, so
its own callees still fan out at the depth-1 cross-file budget (a flow is
entry + direct callees). ``flow.entry_point_file`` (the legacy scalar) is
NOT changed — only the graph seed moves — so flow identity is preserved.

Covered forms (each with its own unit + telemetry sub-class):
  * ``export { X } from './Y'`` / ``export { X as Z } from './Y'`` — named.
  * ``export { default as X } from './Y'`` — named-default.
  * ``export * from './Y'`` — star, resolved ONLY when the flow carries a
    real re-exported entry symbol name that lands in exactly one star
    target; an ambiguous star (multiple ``export *`` sources, or a
    ``<file>``/no-symbol entry) is an HONEST SKIP with a named sub-class,
    never a silent whole-file grab.

Form B — named-import callee span recovery (TUNED arm)
------------------------------------------------------
An import edge that resolved only to a file (``lines=None``) is replaced
by the specific IMPORTED SYMBOL's real body range — never the whole file
(the anti-over-count law). The recovered callees carry a marker so the
expander's Pass-2 fan-in gate can demote them at the STRUCTURAL FLOOR
(``fan_in >= 2``) rather than the ratio-outlier threshold: a symbol that
is merely imported (not directly called in a recovered body) and shared
by >= 2 flows is infrastructure by default — a stricter shared-demote than
a genuine call edge earns. Classes / types / re-exports / 1-line symbols
never attribute (tight under-count beats whole-file/whole-class).

Scope: TS/JS only (``export … from`` / ``import { … } from`` barrels are
the census's named exhibits; Python ``__init__`` re-exports are a named
future gap). Both arms are OFF by default (see the flag topology below).

Flag topology (documented per the B82 mandate)
----------------------------------------------
Two arms with DIFFERENT flip-maturity (Form A is surgical / ship-ready;
Form B carries a corpus over-count risk that needs a keyed footprint
proof before any default flip) is the weighty reason to split, so each
arm is independently armable:

  * ``WYSTAN_FLOW_SPAN_RECOVERY``          — master; arms BOTH arms.
  * ``WYSTAN_FLOW_SPAN_RECOVERY_REEXPORT`` — Form A only (isolation).
  * ``WYSTAN_FLOW_SPAN_RECOVERY_CALLEE``   — Form B only (isolation).

Form A fires ⟺ master OR reexport-sub; Form B fires ⟺ master OR
callee-sub. All three default OFF; appended to
``scan_result_cache.ENV_OUTPUT_FLAGS`` WITHOUT a KEY_SCHEMA bump (the bump
rides a separate future flip commit). Explicit ``0``/``false``/``off``/
``no`` is the kill-switch (unset ≡ explicit ``0`` byte-identical).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from wystan.analyzer.import_graph import _resolve_import
from wystan.analyzer.safe_read import path_within_repo

if TYPE_CHECKING:
    from wystan.analyzer.ast_extractor import FileSignature
    from wystan.pipeline_v2.flow_reach import ReachContext

__all__ = [
    "FLOW_SPAN_RECOVERY_ENV",
    "FLOW_SPAN_RECOVERY_REEXPORT_ENV",
    "FLOW_SPAN_RECOVERY_CALLEE_ENV",
    "SpanRecoveryConfig",
    "reexport_recovery_enabled",
    "callee_recovery_enabled",
    "ReExport",
    "ReexportResolution",
    "parse_reexports",
    "resolve_reexport_entry",
    "recover_callee_symbols",
    "ImportedSpan",
    "resolve_import_spans",
    "whole_file_lines",
]

FLOW_SPAN_RECOVERY_ENV = "WYSTAN_FLOW_SPAN_RECOVERY"
FLOW_SPAN_RECOVERY_REEXPORT_ENV = "WYSTAN_FLOW_SPAN_RECOVERY_REEXPORT"
FLOW_SPAN_RECOVERY_CALLEE_ENV = "WYSTAN_FLOW_SPAN_RECOVERY_CALLEE"

#: Suffixes the barrel / named-import recovery understands. ``export … from``
#: and ``import { … } from`` re-export/import forms are a TS/JS idiom; the
#: resolver (``_resolve_import``) is the TS/JS resolver.
_TS_JS_SUFFIXES = frozenset({
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
})

#: The Stage-3 sentinel for a whole-file entry (no resolved symbol). Treated
#: like ``None`` when deciding whether the entry carries a real symbol name.
_FILE_ENTRY_SENTINEL = "<file>"


def reexport_recovery_enabled() -> bool:
    """Form A is always on. The ``WYSTAN_FLOW_SPAN_RECOVERY*`` flags are
    retired: every flow node must carry a measured line span."""
    return True


def callee_recovery_enabled() -> bool:
    """Import-span resolution is always on (see :func:`resolve_import_spans`)."""
    return True


@dataclass(frozen=True)
class SpanRecoveryConfig:
    """Span-recovery arming. Both arms are unconditional; the class stays so
    tests can switch one arm off in isolation."""

    reexport: bool = True
    callee: bool = True

    @classmethod
    def from_env(cls) -> "SpanRecoveryConfig":
        return cls()

    @property
    def any(self) -> bool:
        return self.reexport or self.callee


# ── Re-export parsing (Form A) ───────────────────────────────────────────

# ``export { A, B as C, default as D } from './mod'`` — named re-export WITH a
# source module. The plain ``_RE_REEXPORT`` in ast_extractor drops the ``from``
# clause; we need it to follow through, so this pattern captures both.
_RE_REEXPORT_FROM = re.compile(
    r"export\s+(?:type\s+)?\{([^}]*)\}\s*from\s*['\"]([^'\"]+)['\"]",
)
# ``export * from './mod'`` and ``export * as NS from './mod'``.
_RE_EXPORT_STAR_FROM = re.compile(
    r"export\s*\*\s*(?:as\s+([A-Za-z_$][\w$]*)\s+)?from\s*['\"]([^'\"]+)['\"]",
)
# A NAMED default export in the TARGET module: ``export default function foo``
# / ``export default class Foo`` — the real symbol name a ``default as X``
# re-export forwards. An anonymous default (``export default () => …``) has no
# name here, so a ``default`` re-export of it is an honest skip.
_RE_TARGET_NAMED_DEFAULT = re.compile(
    r"export\s+default\s+(?:async\s+)?(?:function\s*\*?|class)\s+([A-Za-z_$][\w$]*)",
)


@dataclass(frozen=True)
class ReExport:
    """One ``export … from`` statement parsed off a barrel file's source.

    ``kind`` is ``"named"`` (``names`` holds ``(exposed, original)`` pairs) or
    ``"star"`` (``names`` empty; ``ns`` is the namespace alias, if any).
    """

    line: int
    kind: str
    module: str
    names: tuple[tuple[str, str], ...] = ()
    ns: str | None = None


def parse_reexports(source: str) -> list[ReExport]:
    """Parse every ``export … from`` re-export in ``source`` (source order)."""
    if not source or "from" not in source:
        return []
    out: list[ReExport] = []
    for m in _RE_REEXPORT_FROM.finditer(source):
        line = source[: m.start()].count("\n") + 1
        names: list[tuple[str, str]] = []
        for token in m.group(1).split(","):
            tok = token.strip()
            if not tok:
                continue
            if tok.startswith("type "):
                tok = tok[len("type "):].strip()
            parts = [p.strip() for p in tok.split(" as ")]
            if len(parts) == 2:
                original, exposed = parts[0], parts[1]
            else:
                original = exposed = parts[0]
            if exposed:
                names.append((exposed, original))
        if names:
            out.append(ReExport(
                line=line, kind="named", module=m.group(2),
                names=tuple(names),
            ))
    for m in _RE_EXPORT_STAR_FROM.finditer(source):
        line = source[: m.start()].count("\n") + 1
        out.append(ReExport(
            line=line, kind="star", module=m.group(2), ns=m.group(1) or None,
        ))
    out.sort(key=lambda r: r.line)
    return out


@dataclass(frozen=True)
class ReexportResolution:
    """Outcome of Form-A follow-through for one flow entry.

    ``target_file`` / ``target_symbol`` / ``lines`` are set on success;
    ``skip_subclass`` names the reason on an honest skip (both are never
    populated together)."""

    target_file: str | None = None
    target_symbol: str | None = None
    lines: tuple[int, int] | None = None
    skip_subclass: str | None = None

    @property
    def resolved(self) -> bool:
        return self.target_file is not None and self.lines is not None


def _symbol_range_obj(sig: "FileSignature | None", symbol: str):
    """First top-level (non method/constructor) ``SymbolRange`` named ``symbol``."""
    if sig is None:
        return None
    for rng in sig.symbol_ranges:
        if rng.name == symbol and rng.kind not in ("method", "constructor"):
            return rng
    return None


def _resolve_module(rctx: "ReachContext", importer: str, module: str) -> str | None:
    resolved = _resolve_import(
        importer, module, rctx.file_set,
        alias_map=rctx.alias_map,
        monorepo_packages=rctx.monorepo_packages,
        workspace_package_map=rctx.workspace_package_map,
        repo_root=str(rctx.repo_path),
        alias_entries=getattr(rctx, "alias_entries", None),
    )
    if resolved and resolved != importer:
        return resolved
    return None


def _real_body_range(sig: "FileSignature | None", symbol: str):
    """The ``(start, end)`` of ``symbol``'s REAL multi-line body in ``sig``.

    Returns ``None`` (caller keeps the placeholder — graceful degrade) when the
    symbol is absent, is itself a re-export / type (no runnable body), a whole
    class (never grabbed whole), or is a 1-line symbol (nothing recovered)."""
    rng = _symbol_range_obj(sig, symbol)
    if rng is None:
        return None
    if rng.kind in ("reexport", "type", "enum", "class"):
        return None
    if rng.end_line <= rng.start_line:
        return None
    return (rng.start_line, rng.end_line)


def resolve_reexport_entry(
    rctx: "ReachContext",
    entry_file: str,
    entry_symbol: str | None,
    entry_line: int | None,
    entry_sig: "FileSignature | None",
) -> ReexportResolution | None:
    """Form A. Follow a barrel re-export at the flow's entry to the real
    target symbol body. Returns ``None`` when the entry is not a barrel
    forward at all (so the caller's existing path is byte-untouched); returns
    a :class:`ReexportResolution` carrying either a resolved target OR a named
    skip sub-class when it IS a barrel but couldn't be followed safely."""
    if entry_sig is None or not entry_sig.source:
        return None
    if Path(entry_file).suffix.lower() not in _TS_JS_SUFFIXES:
        return None
    reexports = parse_reexports(entry_sig.source)
    if not reexports:
        return None

    real_symbol = (
        entry_symbol
        if entry_symbol and entry_symbol != _FILE_ENTRY_SENTINEL
        else None
    )

    # 1) Prefer the named re-export that EXPOSES the flow's real entry symbol.
    if real_symbol is not None:
        for re_ in reexports:
            if re_.kind != "named":
                continue
            for exposed, original in re_.names:
                if exposed == real_symbol:
                    return _follow_named(rctx, entry_file, re_.module, original)
        # 1b) A star re-export can forward the symbol; resolve ONLY when
        # exactly one star target actually defines it (else ambiguous skip).
        star_hits: list[tuple[str, tuple[int, int]]] = []
        for re_ in reexports:
            if re_.kind != "star" or re_.ns is not None:
                continue
            tgt = _resolve_module(rctx, entry_file, re_.module)
            if tgt is None:
                continue
            body = _real_body_range(rctx.signatures.get(tgt), real_symbol)
            if body is not None:
                star_hits.append((tgt, body))
        if len(star_hits) == 1:
            tgt, body = star_hits[0]
            return ReexportResolution(
                target_file=tgt, target_symbol=real_symbol, lines=body,
            )
        if star_hits:
            return ReexportResolution(skip_subclass="star_ambiguous")

    # 2) Sentinel / no real symbol: use entry_line to pick the re-export line.
    if entry_line is not None:
        on_line = [r for r in reexports if r.line == entry_line]
        named_on_line = [r for r in on_line if r.kind == "named"]
        if len(named_on_line) == 1:
            re_ = named_on_line[0]
            # deterministic: first re-exported original symbol on the line.
            _exposed, original = re_.names[0]
            return _follow_named(rctx, entry_file, re_.module, original)
        if any(r.kind == "star" for r in on_line):
            return ReexportResolution(skip_subclass="star_no_entry_symbol")

    return None


def _follow_named(
    rctx: "ReachContext",
    entry_file: str,
    module: str,
    original: str,
) -> ReexportResolution:
    tgt = _resolve_module(rctx, entry_file, module)
    if tgt is None:
        return ReexportResolution(skip_subclass="module_unresolved")
    tsig = rctx.signatures.get(tgt)
    if original == "default":
        # ``export { default as X } from './Y'`` — resolve the target's NAMED
        # default (``export default function foo`` / ``class Foo``). An
        # ANONYMOUS default (``export default () => …``) has no symbol name to
        # bind to → honest skip with a named sub-class (never a whole-file grab).
        named = None
        if tsig is not None and tsig.source:
            m = _RE_TARGET_NAMED_DEFAULT.search(tsig.source)
            named = m.group(1) if m else None
        if named is None:
            return ReexportResolution(skip_subclass="default_reexport_anon")
        original = named
    body = _real_body_range(tsig, original)
    if body is None:
        return ReexportResolution(skip_subclass="target_not_multiline")
    return ReexportResolution(target_file=tgt, target_symbol=original, lines=body)


# ── Named-import callee recovery (Form B) ────────────────────────────────

# ``import { A, B as C } from './mod'`` — named-import bindings + source module.
_RE_NAMED_IMPORT_FROM = re.compile(
    r"import\s+(?:type\s+)?\{([^}]*)\}\s*from\s*['\"]([^'\"]+)['\"]",
)


@dataclass
class _ImportIndex:
    """Cache of a file's parsed named imports, keyed by resolved target file."""

    by_target: dict[str, list[str]] = field(default_factory=dict)


def _parse_named_imports(source: str) -> list[tuple[str, list[str]]]:
    """``[(module, [original_names...]), ...]`` for every named import."""
    if not source or "import" not in source:
        return []
    out: list[tuple[str, list[str]]] = []
    for m in _RE_NAMED_IMPORT_FROM.finditer(source):
        originals: list[str] = []
        for token in m.group(1).split(","):
            tok = token.strip()
            if not tok:
                continue
            if tok.startswith("type "):
                continue  # type-only binding — no runnable body
            original = tok.split(" as ")[0].strip()
            if original:
                originals.append(original)
        if originals:
            out.append((m.group(2), originals))
    return out


def recover_callee_symbols(
    rctx: "ReachContext",
    current_file: str,
    current_sig: "FileSignature | None",
    target_file: str,
) -> list[tuple[str, tuple[int, int]]]:
    """Form B. For the import edge ``current_file -> target_file`` that resolved
    only to a file, return the SPECIFIC imported symbols' real body ranges
    ``[(symbol, (start, end)), ...]`` — never the whole file. Empty when no
    named binding from ``current_file`` to ``target_file`` resolves to a real
    multi-line, non-class, non-reexport symbol (caller keeps its file-node
    fallback: the flag never deletes the fallback path)."""
    if current_sig is None or not current_sig.source:
        return []
    if Path(current_file).suffix.lower() not in _TS_JS_SUFFIXES:
        return []
    tsig = rctx.signatures.get(target_file)
    if tsig is None:
        return []
    out: list[tuple[str, tuple[int, int]]] = []
    seen: set[str] = set()
    for module, originals in _parse_named_imports(current_sig.source):
        if _resolve_module(rctx, current_file, module) != target_file:
            continue
        for original in originals:
            if original in seen:
                continue
            body = _real_body_range(tsig, original)
            if body is None:
                continue
            seen.add(original)
            out.append((original, body))
    return out


# ── Import-span resolution (every imported file is measured) ─────────────

_IDENT = r"[A-Za-z_$][\w$]*"
# ``import D, { a, b as c } from 'm'`` / ``import { a } from 'm'`` (multi-line ok).
_RE_IMPORT_NAMED = re.compile(
    rf"import\s+(?:type\s+)?(?:{_IDENT}\s*,\s*)?\{{([^}}]*)\}}\s*from\s*['\"]([^'\"]+)['\"]",
)
# ``import D from 'm'`` / ``import D, { a } from 'm'``.
_RE_IMPORT_DEFAULT = re.compile(
    rf"import\s+(?:type\s+)?({_IDENT})\s*(?:,\s*\{{[^}}]*\}})?\s*from\s*['\"]([^'\"]+)['\"]",
)
# ``import * as NS from 'm'``.
_RE_IMPORT_NAMESPACE = re.compile(
    rf"import\s+(?:type\s+)?\*\s+as\s+({_IDENT})\s+from\s*['\"]([^'\"]+)['\"]",
)
_NON_TOP_LEVEL_KINDS = ("method", "constructor")
_CONFIDENCE_SYMBOL = "medium"
_CONFIDENCE_COARSE = "low"


@dataclass(frozen=True)
class ImportedSpan:
    """One measured piece of an imported file used by a caller.

    ``symbol`` is ``None`` for a whole-file span: the caller references the
    import but the reference cannot be tied to one symbol."""

    symbol: str | None
    lines: tuple[int, int]
    confidence: str


@dataclass(frozen=True)
class _Binding:
    kind: str        # "named" | "default" | "namespace"
    original: str
    local: str


def _bindings_to(
    rctx: "ReachContext", importer: str, source: str, target_file: str,
) -> list[_Binding]:
    """Every TS/JS import binding in ``source`` that resolves to ``target_file``."""
    out: list[_Binding] = []
    for m in _RE_IMPORT_NAMED.finditer(source):
        if _resolve_module(rctx, importer, m.group(2)) != target_file:
            continue
        for token in m.group(1).split(","):
            tok = token.strip()
            if tok.startswith("type "):
                tok = tok[len("type "):].strip()
            if not tok:
                continue
            original, _, local = tok.partition(" as ")
            out.append(_Binding("named", original.strip(), (local or original).strip()))
    for m in _RE_IMPORT_NAMESPACE.finditer(source):
        if _resolve_module(rctx, importer, m.group(2)) == target_file:
            out.append(_Binding("namespace", m.group(1), m.group(1)))
    for m in _RE_IMPORT_DEFAULT.finditer(source):
        if _resolve_module(rctx, importer, m.group(2)) == target_file:
            out.append(_Binding("default", m.group(1), m.group(1)))
    return out


def _is_referenced(name: str, body: str) -> bool:
    return re.search(rf"(?<![\w$.]){re.escape(name)}(?![\w$])", body) is not None


def _span_of(rng) -> ImportedSpan | None:
    """Span for a referenced top-level symbol; ``None`` when nothing to add."""
    if rng.kind == "class":
        # A class is never attributed whole: its constructor and the methods
        # the caller invokes are resolved as their own nodes by the call graph.
        return None
    return ImportedSpan(rng.name, (rng.start_line, rng.end_line), _CONFIDENCE_SYMBOL)


_MAX_WHOLE_FILE_BYTES = 2_000_000


def whole_file_lines(rctx: "ReachContext", rel_path: str) -> tuple[int, int] | None:
    """``(1, line_count)`` of a repository file, or ``None`` when unreadable.

    Uses the parsed signature when there is one; a file without a signature
    (no exported symbol was extracted) is read from disk."""
    sig = rctx.signatures.get(rel_path)
    text = (sig.source if sig is not None else None) or ""
    if not text:
        path = Path(str(rctx.repo_path)) / rel_path
        # A symlink that leaves the repository is never read.
        if not path_within_repo(path, rctx.repo_path):
            return None
        try:
            if not path.is_file() or path.stat().st_size > _MAX_WHOLE_FILE_BYTES:
                return None
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None
    if not text:
        return None
    return (1, len(text.splitlines()) or 1)


def _whole_file(rctx: "ReachContext", target_file: str) -> list[ImportedSpan]:
    lines = whole_file_lines(rctx, target_file)
    return [] if lines is None else [ImportedSpan(None, lines, _CONFIDENCE_COARSE)]


def _top_level_ranges(tsig: "FileSignature") -> list:
    return [r for r in tsig.symbol_ranges if r.kind not in _NON_TOP_LEVEL_KINDS]


def _resolve_binding(binding: _Binding, tsig: "FileSignature", body: str) -> list:
    """Symbol ranges of ``tsig`` that ``binding`` refers to in ``body``."""
    if binding.kind == "named":
        rng = _symbol_range_obj(tsig, binding.original)
        return [rng] if rng is not None and rng.kind != "reexport" else []
    if binding.kind == "namespace":
        members = set(re.findall(
            rf"(?<![\w$.]){re.escape(binding.local)}\.({_IDENT})", body,
        ))
        found = [_symbol_range_obj(tsig, m) for m in sorted(members)]
        return [r for r in found if r is not None and r.kind != "reexport"]
    by_name = _symbol_range_obj(tsig, binding.local)
    if by_name is not None:
        return [by_name]
    bodies = [r for r in _top_level_ranges(tsig) if r.kind not in ("type", "reexport")]
    return bodies if len(bodies) == 1 else []


def resolve_import_spans(
    rctx: "ReachContext",
    current_file: str,
    current_sig: "FileSignature | None",
    body: str,
    target_file: str,
    taken: set[str],
) -> list[ImportedSpan]:
    """Measured spans of ``target_file`` that the caller ``body`` uses.

    ``taken`` holds symbol labels of ``target_file`` already attributed through
    call edges; they are not returned again. The result is empty when the
    caller does not reference the import, and a single whole-file span when it
    does but no symbol can be identified. A node without lines is never
    produced."""
    tsig = rctx.signatures.get(target_file)
    if current_sig is None:
        return []
    is_ts_js = Path(current_file).suffix.lower() in _TS_JS_SUFFIXES
    if tsig is None and not is_ts_js:
        return []
    ranges: list = []
    referenced_unresolved = False
    if is_ts_js:
        for binding in _bindings_to(rctx, current_file, current_sig.source or "", target_file):
            if not _is_referenced(binding.local, body):
                continue
            # A target without a signature has no extracted symbols to bind to.
            resolved = _resolve_binding(binding, tsig, body) if tsig is not None else []
            if resolved:
                ranges.extend(resolved)
            else:
                referenced_unresolved = True
    else:
        ranges = [r for r in _top_level_ranges(tsig) if _is_referenced(r.name, body)]
    spans: list[ImportedSpan] = []
    seen: set[str] = set(taken)
    for rng in ranges:
        if rng.name in seen:
            continue
        seen.add(rng.name)
        span = _span_of(rng)
        if span is not None:
            spans.append(span)
    if spans or not referenced_unresolved:
        return spans
    if taken:
        return []
    return _whole_file(rctx, target_file)
