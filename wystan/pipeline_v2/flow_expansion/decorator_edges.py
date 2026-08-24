"""Decorator-support call-graph edges (flag-gated, Python-only, no LLM).

The gap (VERIFIED — see ``eval/BUG_LEDGER.md`` "DECORATOR-EDGE GAP OPEN")
=============================================================================
The T1 call graph has NO edge ``decorated method → decorator implementation``.
A cross-module user-space decorator (``@require_scope`` / ``@retry`` /
``@cached`` / ``@audit_log``) whose logic lives in a utils module never
becomes a node of the flows it wraps, so that shared logic is invisible to
fan-in / shared-demote — contrary to the model contract
(shared-component = ``shared_with_flows``).

The fix (deterministic)
=======================
For a decorated ``def`` / ``class``, parse its AST ``decorator_list``, resolve
each decorator name to its implementation's SYMBOLIC body span (the def-range
from the target file's ``symbol_ranges``, NEVER the whole file — the B82-B
anti-over-count law), and emit a SUPPORT edge
``decorated-node → decorator-impl-node``. The recovered nodes enter the graph
as symbol nodes (the expander gives any symbol node ``role="called"``) and
demote to ``role="shared"`` at the STRUCTURAL FLOOR (``fan_in >= 2``) exactly
like B82 Form B — a decorator used by >= 2 flows is cross-cutting
infrastructure by default, a stricter gate than the ratio outlier.

Structural exclusions (no name dictionary; the *mechanism* decides)
-------------------------------------------------------------------
* builtin decorators (``@property`` / ``@staticmethod`` / ``@classmethod``) —
  the base name is a Python *builtin*, no user-space body.
* stdlib decorators (``@dataclass`` / ``@abstractmethod`` / ``@lru_cache`` /
  ``@wraps`` / ``@abc.abstractmethod`` …) — the base name (or an attribute's
  base name) resolves to an import from a module in
  ``sys.stdlib_module_names``.
* route decorators (``@app.get`` / ``@router.post`` …) — an ATTRIBUTE
  decorator whose method is an HTTP verb; already the entry extractor's
  mechanism, never a support edge.
* registry / instance decorators (``@registry.register`` / ``@limiter.limit``
  …) — an ATTRIBUTE decorator whose base name is NOT an ``import module``
  binding (it is an instance/variable), so it exposes no module-level def to
  edge to.
* external-package decorators (``@field_validator`` from pydantic,
  ``@activity.defn`` from temporalio …) — the base name resolves to an import
  from a package that is NOT in-repo.
* unresolvable / non-multiline / class-bodied decorator impls — honest skip
  with named telemetry (a tight under-count beats a whole-file over-count).

Resolvable forms (the target mass, census-named)
------------------------------------------------
* bare name via ``from <userspace_module> import deco`` → the module file's
  def ``deco`` (or the ``as``-original). Census: tracecat ``require_scope``
  (696), ``audit_log`` (102), ``requires_entitlement`` (72); onyx
  ``log_function_time`` (52), ``retry_builder`` (51), ``rate_limit_builder``
  (11).
* bare name that is a LOCAL def in the SAME file (same-file support node).
* ``@module.deco`` where ``module`` was bound by ``import module`` (a real
  in-repo module) → the module file's def ``deco``.

Scope: Python only (``.py``). TS/JS decorators are a named future gap
(Angular / NestJS ``@Injectable`` etc. are a different resolution model).

Flag topology
-------------
``WYSTAN_DECORATOR_SUPPORT_EDGES`` — default **OFF**; appended to
``scan_result_cache.ENV_OUTPUT_FLAGS`` WITHOUT a ``KEY_SCHEMA`` bump (the bump
rides a separate future flip commit). Explicit ``0`` / ``false`` / ``off`` /
``no`` / unset ⇒ no-op (kill-switch; unset ≡ explicit ``0`` byte-identical).
"""

from __future__ import annotations

import ast
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from wystan.pipeline_v2.flow_reach import _resolve_python_module

if TYPE_CHECKING:  # pragma: no cover — typing only
    from wystan.analyzer.ast_extractor import FileSignature
    from wystan.pipeline_v2.flow_reach import ReachContext

__all__ = [
    "DECORATOR_SUPPORT_EDGES_ENV",
    "decorator_support_edges_enabled",
    "DecoratorEdgeConfig",
    "DecoratorSupport",
    "decorator_supports_for_symbol",
    "entry_decorator_target_ids",
    "BUILTIN_DECORATORS",
    "ROUTE_METHOD_NAMES",
]

DECORATOR_SUPPORT_EDGES_ENV = "WYSTAN_DECORATOR_SUPPORT_EDGES"

_PYTHON_SUFFIX = ".py"

#: Only ``.py`` files carry Python decorators the resolver understands.
#: Names that are Python *builtins* usable as decorators — no user-space body.
#: STRUCTURAL: these live in the ``builtins`` module (no source file to edge to),
#: not an ad-hoc allow-list of decorator names.
BUILTIN_DECORATORS = frozenset({"property", "staticmethod", "classmethod"})

#: HTTP-verb / entry method names an ATTRIBUTE decorator carries when it is a
#: route registration (``@app.get`` / ``@router.post`` / ``@router.websocket``).
#: These are the entry extractor's mechanism — never a support edge. STRUCTURAL:
#: matched on the attribute's *method* position, not on the object's name.
ROUTE_METHOD_NAMES = frozenset({
    "get", "post", "put", "delete", "patch", "head", "options",
    "websocket", "route", "api_route", "websocket_route", "add_api_route",
    "middleware", "exception_handler", "on_event", "endpoint",
})

#: stdlib module names (structural — the builtin/stdlib set, not a dictionary of
#: decorator names). Populated from the interpreter when available.
_STDLIB_MODULES = frozenset(getattr(sys, "stdlib_module_names", frozenset()))


def _truthy(env: str, default: str = "0") -> bool:
    return os.environ.get(env, default).strip().lower() in {"1", "true", "yes", "on"}


def decorator_support_edges_enabled() -> bool:
    """Default **ON** since the 2026-07-27 flip-pack №8 flip (KEY_SCHEMA 41;
    keyless tracecat proof: decorated method → decorator-impl support edges
    resolved). ``WYSTAN_DECORATOR_SUPPORT_EDGES`` truthy arms; unset now
    arms too. Explicit ``0`` / ``false`` / ``off`` / ``no`` ⇒ no-op
    (kill-switch forever; byte-identical to the pre-flip pipeline). Only this
    flag's read default moved ``"0"`` -> ``"1"`` (unset ≡ explicit ``"1"``);
    the shared ``_truthy`` keeps its OFF default for any other caller."""
    return _truthy(DECORATOR_SUPPORT_EDGES_ENV, "1")


@dataclass(frozen=True)
class DecoratorSupport:
    """One resolved decorator-support edge target.

    ``target_file`` / ``symbol`` / ``lines`` identify the decorator
    implementation's SYMBOLIC body span (never whole-file). ``decorator`` is the
    display token (for exhibits/telemetry) and ``same_file`` records whether the
    impl lives in the decorated symbol's own module.
    """

    decorator: str
    target_file: str
    symbol: str
    lines: tuple[int, int]
    same_file: bool


@dataclass(frozen=True)
class _DecoratedDef:
    """A decorated def/class with the line span of its WHOLE statement (topmost
    decorator line .. end of body) — used to resolve the entry-line-anchored
    decorated symbol DETERMINISTICALLY (independent of any LLM-derived entry
    symbol), so the mechanism fires on a keyless scan."""

    name: str
    parent: str | None
    stmt_start: int  # topmost decorator line (py_ast DefSpan _stmt_start rule)
    end_line: int
    decorators: tuple[ast.expr, ...]


@dataclass
class _FileIndex:
    """Parsed decorator/import state for one Python file (cached per scan)."""

    by_symbol: dict[tuple[str, str | None], list[ast.expr]]
    binds: dict[str, tuple[str, str, str]]  # name -> ("from"|"mod", module, orig)
    local_defs: set[str]
    decorated: tuple[_DecoratedDef, ...]  # for entry-line resolution


@dataclass
class DecoratorEdgeConfig:
    """Per-scan arming + a file-index cache, read ONCE from the environment.

    The cache keys parsed decorator/import indexes by file path so the AST parse
    of a file's source happens at most once per scan (the flag is Python-only
    and OFF by default, so the whole thing is inert in the default world)."""

    enabled: bool = False
    _cache: dict[str, "_FileIndex | None"] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "DecoratorEdgeConfig":
        return cls(enabled=decorator_support_edges_enabled())


# ── AST decorator head resolution ────────────────────────────────────────


def _deco_head(dec: ast.expr) -> tuple[str, str | None, str | None]:
    """Classify a decorator expression.

    Returns ``(kind, base, method)`` where ``kind`` ∈ {``name``, ``attr``,
    ``other``}. For ``name`` the ``base`` is the identifier (``@deco`` /
    ``@deco(...)``). For ``attr`` the ``base`` is the leftmost ``Name`` id and
    ``method`` the *last* attribute (``@mod.deco`` → base ``mod``, method
    ``deco``; ``@a.b.c`` → base ``a``, method ``c``)."""
    node: ast.expr = dec
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Name):
        return ("name", node.id, None)
    if isinstance(node, ast.Attribute):
        method = node.attr
        base: ast.expr = node.value
        depth = 1
        while isinstance(base, ast.Attribute):
            base = base.value
            depth += 1
        if isinstance(base, ast.Name):
            # Only a single-level ``base.method`` chain is resolvable to a module
            # def; deeper chains (``a.b.c``) are an honest skip (attr_chain).
            return ("attr", base.id, method if depth == 1 else None)
        return ("attr", None, None)
    return ("other", None, None)


def _deco_display(dec: ast.expr) -> str:
    kind, base, method = _deco_head(dec)
    if kind == "name":
        return base or "<expr>"
    if kind == "attr" and base is not None:
        return f"{base}.{method}" if method else f"{base}.*"
    return "<expr>"


def _build_imports(tree: ast.Module) -> dict[str, tuple[str, str, str]]:
    """``name -> ("from", module, original) | ("mod", module, module)``.

    ``from a.b import x as y`` → ``y -> ("from", "a.b", "x")``.
    ``import a.b`` → ``a -> ("mod", "a", "a")`` (top binding).
    ``import a.b as c`` → ``c -> ("mod", "a.b", "a.b")``.
    Relative modules keep their leading dots for PEP-328 resolution.
    """
    binds: dict[str, tuple[str, str, str]] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            module = ("." * (n.level or 0)) + (n.module or "")
            for a in n.names:
                if a.name == "*":
                    continue
                binds[a.asname or a.name] = ("from", module, a.name)
        elif isinstance(n, ast.Import):
            for a in n.names:
                if a.asname:
                    binds[a.asname] = ("mod", a.name, a.name)
                else:
                    top = a.name.split(".")[0]
                    binds.setdefault(top, ("mod", top, top))
    return binds


def _file_index(source: str) -> "_FileIndex | None":
    """Parse one Python file's source → decorator lists per symbol + imports."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    by_symbol: dict[tuple[str, str | None], list[ast.expr]] = {}
    local_defs: set[str] = set()
    decorated: list[_DecoratedDef] = []

    def _stmt_start(node: ast.AST) -> int:
        line = int(getattr(node, "lineno", 1) or 1)
        for d in getattr(node, "decorator_list", None) or ():
            dl = getattr(d, "lineno", None)
            if dl is not None:
                line = min(line, int(dl))
        return max(1, line)

    def _record(child: ast.AST, name: str, parent: str | None) -> None:
        decos = getattr(child, "decorator_list", None) or ()
        if not decos:
            return
        by_symbol.setdefault((name, parent), []).extend(decos)
        start = _stmt_start(child)
        end = int(getattr(child, "end_lineno", None) or start)
        decorated.append(_DecoratedDef(
            name=name, parent=parent, stmt_start=start,
            end_line=max(start, end), decorators=tuple(decos),
        ))

    def _walk(node: ast.AST, parent: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                local_defs.add(child.name)
                _record(child, child.name, parent)
                _walk(child, child.name)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                local_defs.add(child.name)
                _record(child, child.name, parent)
                _walk(child, None)
            else:
                _walk(child, parent)

    _walk(tree, None)
    return _FileIndex(
        by_symbol=by_symbol,
        binds=_build_imports(tree),
        local_defs=local_defs,
        decorated=tuple(decorated),
    )


def _get_index(cfg: "DecoratorEdgeConfig", file: str, sig: "FileSignature | None") -> "_FileIndex | None":
    if file in cfg._cache:
        return cfg._cache[file]
    idx = _file_index(sig.source) if (sig is not None and sig.source) else None
    cfg._cache[file] = idx
    return idx


def _top_pkg(module: str) -> str:
    m = module.lstrip(".")
    return m.split(".")[0] if m else ""


def _target_body_range(
    sig: "FileSignature | None", symbol: str,
) -> tuple[int, int] | None:
    """The ``(start, end)`` of ``symbol``'s def body in ``sig`` — a FUNCTION /
    method with a real multi-line body. Returns ``None`` (honest skip) when the
    symbol is absent, is a class (never grabbed whole — anti-over-count), or is
    a 1-line symbol (nothing to recover)."""
    if sig is None:
        return None
    best: tuple[int, int] | None = None
    for rng in sig.symbol_ranges:
        if rng.name != symbol:
            continue
        if rng.kind not in ("function", "method"):
            continue
        if rng.end_line <= rng.start_line:
            continue
        # Prefer a module-level function over a same-named method.
        if rng.kind == "function":
            return (rng.start_line, rng.end_line)
        if best is None:
            best = (rng.start_line, rng.end_line)
    return best


def _resolve_one(
    dec: ast.expr,
    binds: dict[str, tuple[str, str, str]],
    local_defs: set[str],
    rctx: "ReachContext",
    current_file: str,
    current_sig: "FileSignature | None",
) -> tuple[DecoratorSupport | None, str]:
    """Resolve one decorator to a support target, or return a skip sub-class.

    Returns ``(DecoratorSupport, "")`` on success, else ``(None, skip_class)``.
    ``skip_class`` ∈ {builtin, stdlib, route, instance_attr, attr_chain,
    external_pkg, unresolved, module_unresolved, target_absent}."""
    kind, base, method = _deco_head(dec)
    if kind == "other" or base is None:
        return None, "unresolved"

    # ── bare-name decorator (@deco / @deco(...)) ──
    if kind == "name":
        if base in BUILTIN_DECORATORS:
            return None, "builtin"
        bind = binds.get(base)
        if bind is not None:
            _bkind, module, original = bind
            if _top_pkg(module) in _STDLIB_MODULES:
                return None, "stdlib"
            tgt = _resolve_python_module(
                current_file, module, rctx.file_set,
                source_roots=rctx.python_source_roots,
            )
            if tgt is None:
                # In-repo user-space would resolve; a miss ⇒ third-party pkg.
                return None, "external_pkg"
            body = _target_body_range(rctx.signatures.get(tgt), original)
            if body is None:
                return None, "target_absent"
            return DecoratorSupport(
                decorator=base, target_file=tgt, symbol=original,
                lines=body, same_file=False,
            ), ""
        if base in local_defs:
            body = _target_body_range(current_sig, base)
            if body is None:
                return None, "target_absent"
            return DecoratorSupport(
                decorator=base, target_file=current_file, symbol=base,
                lines=body, same_file=True,
            ), ""
        return None, "unresolved"

    # ── attribute decorator (@obj.method / @mod.deco) ──
    if method is None:
        return None, "attr_chain"
    if method in ROUTE_METHOD_NAMES:
        return None, "route"
    bind = binds.get(base)
    if bind is None:
        # base is a local variable / instance (app/router/registry/limiter) —
        # exposes no module-level def to edge to.
        return None, "instance_attr"
    _bkind, module, _orig = bind
    if _top_pkg(module) in _STDLIB_MODULES:
        return None, "stdlib"
    if _bkind != "mod":
        # ``from pkg import obj`` then ``@obj.method`` — obj is a value, its
        # ``.method`` is a bound method, not a module def (honest skip).
        return None, "instance_attr"
    tgt = _resolve_python_module(
        current_file, module, rctx.file_set,
        source_roots=rctx.python_source_roots,
    )
    if tgt is None:
        return None, "external_pkg"
    body = _target_body_range(rctx.signatures.get(tgt), method)
    if body is None:
        return None, "target_absent"
    return DecoratorSupport(
        decorator=f"{base}.{method}", target_file=tgt, symbol=method,
        lines=body, same_file=(tgt == current_file),
    ), ""


def _decorated_at_line(idx: "_FileIndex", entry_line: int):
    """The INNERMOST (smallest-span) decorated def whose WHOLE statement
    (topmost decorator .. end of body) brackets ``entry_line``. A flow's
    ``entry_point_line`` points at the handler's decorator block, so this
    recovers the decorated entry symbol WITHOUT any LLM-derived name (keyless-
    observable). ``None`` when no decorated def brackets the line."""
    best: "_DecoratedDef | None" = None
    best_span = -1
    for dd in idx.decorated:
        if dd.stmt_start <= entry_line <= dd.end_line:
            span = dd.end_line - dd.stmt_start
            if best is None or span < best_span:
                best = dd
                best_span = span
    return best


def decorator_supports_for_symbol(
    rctx: "ReachContext",
    current_file: str,
    current_sig: "FileSignature | None",
    symbol: str | None,
    parent: str | None,
    *,
    allow_cross_file: bool,
    cfg: "DecoratorEdgeConfig",
    entry_line: int | None = None,
) -> tuple[list[DecoratorSupport], dict[str, int]]:
    """Resolve every decorator on ``symbol`` (in ``current_file``) to a support
    target. When ``symbol`` does not resolve to a decorated def but ``entry_line``
    is given, the decorated def bracketing that line is used instead — so a flow
    whose entry symbol is not (yet) LLM-resolved still attaches its decorator
    supports (keyless-observable). ``allow_cross_file`` gates CROSS-MODULE
    targets (narrative-slice budget); SAME-FILE supports are always allowed.
    Returns the resolved supports (insertion-ordered, deduped by target node)
    plus a skip-sub-class counter for telemetry."""
    skips: dict[str, int] = {}
    if current_file[-3:].lower() != _PYTHON_SUFFIX:
        return [], skips
    idx = _get_index(cfg, current_file, current_sig)
    if idx is None:
        return [], skips

    decos: "list[ast.expr] | tuple[ast.expr, ...] | None" = None
    if symbol and symbol != "<file>":
        # Match by (name, parent); fall back to the last name component.
        base_name = symbol.split(".")[-1]
        decos = idx.by_symbol.get((base_name, parent))
        if decos is None:
            for (nm, _pt), dl in idx.by_symbol.items():
                if nm == base_name:
                    decos = dl
                    break
    if not decos and entry_line is not None:
        dd = _decorated_at_line(idx, entry_line)
        if dd is not None:
            decos = dd.decorators
    if not decos:
        return [], skips

    out: list[DecoratorSupport] = []
    seen: set[tuple[str, str]] = set()
    for dec in decos:
        support, skip = _resolve_one(
            dec, idx.binds, idx.local_defs, rctx, current_file, current_sig,
        )
        if support is None:
            skips[skip] = skips.get(skip, 0) + 1
            continue
        if not support.same_file and not allow_cross_file:
            skips["depth_gated"] = skips.get("depth_gated", 0) + 1
            continue
        key = (support.target_file, support.symbol)
        if key in seen:
            continue
        seen.add(key)
        out.append(support)
    return out, skips


def entry_decorator_target_ids(
    rctx: "ReachContext",
    entry_file: str,
    entry_symbol: str | None,
    entry_parent: str | None,
    entry_line: int | None,
    cfg: "DecoratorEdgeConfig",
) -> list[str]:
    """The decorator-support node ids the ENTRY of a flow should carry
    (``"<target_file>#<symbol>"``). Used by the post-3.5 invariant sentinel to
    re-derive, independently of the expander, which decorated entries lost their
    support edge. Cross-file targets are always in scope for the entry (depth
    0); the entry-line fallback resolves the decorated symbol keyless."""
    if not cfg.enabled:
        return []
    sig = rctx.signatures.get(entry_file)
    supports, _skips = decorator_supports_for_symbol(
        rctx, entry_file, sig, entry_symbol, entry_parent,
        allow_cross_file=True, cfg=cfg, entry_line=entry_line,
    )
    return [f"{s.target_file}#{s.symbol}" for s in supports]
