"""
Regex-based signature extractor for TypeScript and JavaScript files.

Extracts exports, route definitions, and imports from each file
without any external AST dependencies. This "skeleton" is then
fed to an LLM to identify user-facing flows within each feature.

Supported patterns:
  - Named exports:     export function Foo / export const Foo / export class Foo
  - Default exports:   export default function Foo / export default class Foo
  - Re-exports:        export { Foo, Bar }
  - Next.js routes:    export async function GET/POST/PUT/DELETE/PATCH (App Router)
  - Next.js pages:     getServerSideProps, getStaticProps (Pages Router)
  - Express routes:    router.get('/path', ...) / app.post('/path', ...)
  - ES imports:        import X from 'Y'
"""
import ast
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from wystan.analyzer.safe_read import safe_read_text
from wystan.models.types import SymbolRange


_TS_JS_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
_PYTHON_EXTENSIONS = {".py"}
_GO_EXTENSIONS = {".go"}
_RUST_EXTENSIONS = {".rs"}
_RUBY_EXTENSIONS = {".rb", ".rake"}
# Vue Single-File Components. GATED — a ``.vue`` file is only ever parsed
# when WYSTAN_VUE_SFC_FLOWS is enabled (see ``_vue_sfc_flows_enabled``;
# default ON since the 2026-07-29 flip-pack №10, KEY_SCHEMA 45). With the
# flag explicitly OFF ``.vue`` is in NONE of the accepted sets, so it
# ``continue``-skips exactly as before this feature shipped (kill-switch
# is byte-identical). This set is intentionally kept SEPARATE from the
# unconditional-skip guard for that reason.
_VUE_EXTENSIONS = {".vue"}


def _vue_sfc_flows_enabled() -> bool:
    """Whether ``.vue`` SFC flow-candidate extraction is turned on.

    Default **ON** since the 2026-07-29 flip-pack №10 (KEY_SCHEMA 45;
    keyed proof green — hoppscotch 295 vue-flows + graphql born). Unset
    ≡ explicit ``1`` — ``.vue`` files parse into flow-candidates.
    Explicit ``0``/``false``/``no``/``off`` (or empty) keeps ``.vue`` in
    NO accepted extension set, restoring the pre-vue-flow scan
    byte-identically — explicit off stays a valid kill-switch forever.
    The truthy set is preserved LITERALLY across the flip (only the
    get-default moved ``""`` → ``"1"``). Registered in
    ``scan_result_cache.ENV_OUTPUT_FLAGS`` so cached scan results key on
    it like every other output-shaping flag.
    """
    return os.environ.get("WYSTAN_VUE_SFC_FLOWS", "1").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _ruby_def_spans_enabled() -> bool:
    """Whether ``.rb`` symbol ranges use real ``def``…``end`` boundaries.

    Default **ON** (flip-pack #26 KS61; P14: the first flip landed on the
    dead reader ruby_def_spans_enabled — the LIVE gate is here). The law +
    measurement live in
    :mod:`wystan.pipeline_v2.ruby_def_spans`; this local reader exists
    so the hot per-file path does not import pipeline_v2 just to check a
    flag. Unset ≡ explicit ``0`` — the pre-fix "end = next symbol's start
    − 1" heuristic, byte-identical. Registered in
    ``scan_result_cache.ENV_OUTPUT_FLAGS``.
    """
    return os.environ.get("WYSTAN_RUBY_DEF_SPANS", "1").strip().lower() in (
        "1", "true", "yes", "on",
    )


RUBY_ASSOC_RANGES_ENV = "WYSTAN_RUBY_ASSOC_RANGES"


def _ruby_assoc_ranges_enabled() -> bool:
    """fixb122 (A) — FALLBACK-ONLY line ranges for AR assoc/scope exports.

    Default **ON** (flip #28, 2026-08-06, warden CLEAR on the c14/c15
    same-draw pair, KS 63); unset ≡ explicit ``1``; explicit ``0`` =
    kill-switch forever. Registered in
    ``scan_result_cache.ENV_OUTPUT_FLAGS``.

    Root cause (probe M3d-3, VERIFIED in code): ``_parse_ruby_file`` puts
    ``has_many :foo`` / ``scope :recent`` names into ``sig.exports`` but
    NEVER into ``symbol_ranges`` — neither the legacy ``raw_symbols`` path
    nor :mod:`pipeline_v2.ruby_def_spans` (which emits only
    ``class``/``module``/``method``/``constant``). Stage 3 resolves an
    export's line with ``next((sr.start_line for sr in sig.symbol_ranges
    if sr.name == sym), 1)`` — so every association-named flow silently
    anchors at **line 1**.

    This is the SINGLE reader for the flag (the P14 lesson: a second,
    unreachable reader is how flip-pack №26 landed on a dead gate). The
    live call site is :func:`_parse_ruby_file`, pinned by a parity unit.
    """
    return os.environ.get(RUBY_ASSOC_RANGES_ENV, "1").strip().lower() in (
        "1", "true", "yes", "on",
    )


# Named function/class/const exports
_RE_NAMED_EXPORT = re.compile(
    r"export\s+(?:async\s+)?(?:function\s*\*?\s*|class\s+|const\s+|let\s+|var\s+)(\w+)"
)
# Default function/class exports with a name
_RE_DEFAULT_EXPORT = re.compile(
    r"export\s+default\s+(?:async\s+)?(?:function|class)\s+(\w+)"
)
# Re-export block: export { Foo, Bar as Baz }
_RE_REEXPORT = re.compile(r"export\s*\{([^}]+)\}")

# Next.js App Router HTTP method handlers
_RE_NEXTJS_ROUTE = re.compile(
    r"export\s+(?:async\s+)?function\s+(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\b"
)
# Next.js Pages Router data fetchers
_RE_NEXTJS_PAGE = re.compile(
    r"export\s+(?:async\s+)?function\s+(getServerSideProps|getStaticProps|getStaticPaths)\b"
)
# Express/Fastify route definitions: router.get('/path', ...) or app.post('/path')
_RE_EXPRESS_ROUTE = re.compile(
    r"\b(?:router|app|server)\s*\.\s*(get|post|put|delete|patch|head)\s*\(\s*['\"]([^'\"]+)['\"]"
)
# ES6 import paths
_RE_IMPORT = re.compile(r"import\s+.*?from\s+['\"]([^'\"]+)['\"]")

# Top-level LOCAL (non-exported) function/arrow declarations in TS/JS.
# These are NOT exports — they never enter ``FileSignature.exports`` and
# therefore never become feature anchors. They are recorded ONLY in
# ``symbol_ranges`` so the call-graph tracer can resolve same-file
# handler references such as ``const POST = wrap(postHandler)`` where the
# real body lives in a local ``postHandler`` symbol. Anchored to line
# start (MULTILINE) to avoid matching nested / inline closures.
#   function foo(  /  async function foo(
_RE_LOCAL_FUNC_DECL = re.compile(
    r"^(?:async\s+)?function\s*\*?\s*(\w+)\s*[(<]",
    re.MULTILINE,
)
#   const foo = (  /  const foo = async (  /  let foo = function  / arrow
_RE_LOCAL_ARROW_DECL = re.compile(
    r"^(?:const|let|var)\s+(\w+)\s*=\s*"
    r"(?:async\s+)?(?:function\b|\([^)]*\)\s*(?::[^=]+)?=>|[A-Za-z_$][\w$]*\s*=>)",
    re.MULTILINE,
)

# Python patterns
_RE_PYTHON_CLASS = re.compile(r"^class\s+(\w+)", re.MULTILINE)
_RE_PYTHON_FUNC = re.compile(r"^(?:async\s+)?def\s+([a-zA-Z]\w*)", re.MULTILINE)
_RE_PYTHON_ROUTE = re.compile(
    r"@\w*(?:router|app|blueprint|bp|api)\s*\.\s*(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)

# Go: top-level capitalized symbols are exported (idiomatic Go).
# Match func, type, var, const, struct decls.
_RE_GO_FUNC = re.compile(
    r"^func\s+(?:\([^)]*\)\s+)?([A-Z]\w*)\s*\(",
    re.MULTILINE,
)
_RE_GO_TYPE = re.compile(
    r"^type\s+([A-Z]\w*)\b",
    re.MULTILINE,
)
_RE_GO_VAR = re.compile(
    r"^(?:var|const)\s+([A-Z]\w*)\b",
    re.MULTILINE,
)
# Rust: ``pub`` items at any visibility level (we conservatively
# accept ``pub``, ``pub(crate)``, ``pub(super)``).
_RE_RUST_PUB = re.compile(
    r"^[ \t]*pub(?:\([^)]+\))?\s+(?:async\s+)?(?:unsafe\s+)?"
    r"(?:fn|struct|enum|trait|type|const|static|mod)\s+([a-zA-Z_]\w*)",
    re.MULTILINE,
)

# Ruby patterns. Stage 3 only needs symbol *names* (not semantics), so a
# regex parser mirroring _parse_python_file is sufficient — no tree-sitter
# dependency. Without these, every .rb file returns 0 exports and Rails
# repos hit the Stage 3 short-circuit at MIN_EXPORTS_FOR_FLOW_DETECTION=3
# → zero flows emitted (verified on maybe corpus repo).
_RE_RUBY_CLASS = re.compile(r"^[ \t]*class\s+([A-Z]\w*)", re.MULTILINE)
_RE_RUBY_MODULE = re.compile(r"^[ \t]*module\s+([A-Z]\w*)", re.MULTILINE)
_RE_RUBY_DEF = re.compile(
    r"^[ \t]*def\s+(?:self\.)?([a-z_][\w?!=]*)", re.MULTILINE,
)
_RE_RUBY_CONST = re.compile(r"^[ \t]*([A-Z][A-Z0-9_]+)\s*=", re.MULTILINE)
# ActiveRecord / Rails domain declarations — surface as "exports" so
# Stage 3 sees enough symbols and the LLM has Rails-shaped vocabulary.
_RE_RUBY_AR_ASSOC = re.compile(
    r"^[ \t]*(?:has_many|has_one|belongs_to|has_and_belongs_to_many)\s+:(\w+)",
    re.MULTILINE,
)
_RE_RUBY_AR_SCOPE = re.compile(r"^[ \t]*scope\s+:(\w+)", re.MULTILINE)
#: fixb122 (A) — kinds stamped on the FALLBACK-ONLY assoc/scope ranges.
#: Deliberately NOT ``method``: an association is a declaration, not a
#: body, so it must never satisfy the ``degrade_span`` widen whitelist nor
#: the Stage-3 callable preference (``flow_anchor_pref.CALLABLE_KINDS``).
_RUBY_ASSOC_KIND = "ar_assoc"
_RUBY_SCOPE_KIND = "ar_scope"
# Rails routes.rb DSL — get '/path' => 'controller#action' etc.
_RE_RUBY_ROUTE = re.compile(
    r"^\s*(get|post|put|patch|delete)\s+['\"]([^'\"]+)['\"]",
    re.MULTILINE | re.IGNORECASE,
)


# ── Vue Single-File Component (SFC) patterns ────────────────────────────
# An SFC is HTML-ish: one or more ``<script>`` blocks (modern form is
# ``<script setup>``), a ``<template>``, and ``<style>``. Only script +
# template carry behaviour. These match the block bodies so decl regexes
# run over SCRIPT text only (never template/style noise).
_RE_VUE_SCRIPT_BLOCK = re.compile(
    r"<script\b[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE,
)
_RE_VUE_TEMPLATE_BLOCK = re.compile(
    r"<template\b[^>]*>(.*?)</template>", re.DOTALL | re.IGNORECASE,
)
# Options-API ``methods: {`` opener (body span recovered by brace match).
_RE_VUE_METHODS = re.compile(r"\bmethods\s*:\s*\{")
# Template event binding whose value names a handler symbol —
# ``@click="save"`` / ``v-on:submit="onSubmit(...)"``. Only a bare
# identifier optionally followed by ``(`` is taken (``@click="count++"``
# and other inline expressions are NOT handler declarations). ``@`` and
# ``v-on:`` are Vue template GRAMMAR (fixed by the framework), so they are
# hardcoded here — unlike the tunable reactivity vocab, which lives in
# ``stacks/vue.yaml``.
_RE_VUE_TEMPLATE_HANDLER = re.compile(
    r'(?:@|v-on:)[\w.:\-\[\]]*\s*=\s*"\s*([A-Za-z_$][\w$]*)\s*(?:\(|")'
)

# Fallback Vue reactivity/lifecycle vocab if ``stacks/vue.yaml`` is
# unavailable. A top-level ``const x = ref(0)`` is STATE, not a handler —
# but such bindings never match the arrow/function decl regexes anyway
# (the initializer is a call, not ``=>``/``function``); this set only
# guards the rare case where one of these names is itself declared as a
# function and the template-handler pass.
_VUE_DEFAULT_REACTIVITY = frozenset({
    "ref", "reactive", "computed", "watch", "watchEffect", "watchPostEffect",
    "shallowRef", "shallowReactive", "toRef", "toRefs", "readonly",
    "defineProps", "defineEmits", "defineExpose", "withDefaults",
})

_VUE_CONV_CACHE: dict | None = None


def _vue_conventions() -> dict:
    """Vue SFC stack conventions from ``stacks/vue.yaml`` (cached).

    Data, not code: the tunable reactivity/lifecycle vocab lives in the
    packaged YAML (mirrored at authoring-time to ``eval/stacks/vue.yaml``).
    Degrades to built-in defaults if the data file is missing so a parse
    never hard-fails on a packaging gap (the fallback law).
    """
    global _VUE_CONV_CACHE
    if _VUE_CONV_CACHE is None:
        data: dict = {}
        try:  # lazy import — analyzer stays decoupled from pipeline_v2
            from wystan.pipeline_v2.data import load_stack_yaml
            data = load_stack_yaml("vue") or {}
        except Exception:  # noqa: BLE001 — fallback law
            data = {}
        reactivity = data.get("reactivity_primitives")
        _VUE_CONV_CACHE = {
            "reactivity_primitives": (
                frozenset(reactivity) if reactivity else _VUE_DEFAULT_REACTIVITY
            ),
            "composable_prefix": data.get("composable_prefix", "use"),
        }
    return _VUE_CONV_CACHE


# Named import destructuring: import { FOO, BAR as Baz } from './path'
_RE_NAMED_IMPORT = re.compile(
    r"import\s*(?:type\s+)?\{([^}]+)\}\s*from\s*['\"]([^'\"]+)['\"]"
)
# Namespace import: import * as X from './path'
_RE_NAMESPACE_IMPORT = re.compile(
    r"import\s*\*\s*as\s+\w+\s+from\s*['\"]([^'\"]+)['\"]"
)

# TS type/interface/enum exports
_RE_TYPE_EXPORT = re.compile(
    r"export\s+(?:declare\s+)?(?:type|interface|enum)\s+(\w+)"
)

# TS/JS class declaration (named). Group 1 = class name. Matches both
# ``export class Foo`` and bare ``class Foo`` (and ``export default class
# Foo``). Used to locate class bodies for METHOD-LEVEL indexing so a member
# call ``obj.method()`` resolves to the specific method body, not the whole
# class. Anchored at a word boundary; the body span is then recovered by a
# brace-matching scan (regex alone can't balance braces).
_RE_TS_CLASS_DECL = re.compile(
    r"\bclass\s+([A-Za-z_$][\w$]*)\b",
)

# A method / class-field declaration on its OWN line inside a class body.
# Group 1 = method name. Covers:
#   foo(           async foo(        static foo(      *foo(
#   public foo(    private foo(      protected foo(   get foo(   set foo(
#   foo = (args) => {     foo = async (args) => {     (arrow class fields)
# Leading whitespace required (class members are indented). The trailing
# ``(`` or ``=`` is what distinguishes a method/arrow-field from a plain
# data field. STRUCTURAL — no per-repo names. Control-flow keywords that
# could masquerade as a call (``if (``, ``for (`` …) are filtered by the
# caller via _TS_NON_METHOD_KEYWORDS.
_RE_TS_METHOD = re.compile(
    r"^\s+(?:public\s+|private\s+|protected\s+|readonly\s+|static\s+|"
    r"abstract\s+|override\s+|async\s+|get\s+|set\s+|\*\s*)*"
    r"([A-Za-z_$#][\w$]*)\s*"
    r"(?:[(<]|=\s*(?:async\s+)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*(?::[^=]+)?=>)",
)
# Tokens that _RE_TS_METHOD would otherwise capture as a "method" because
# they are followed by ``(`` — these are control-flow / operators, never
# real callable members. Excluding them keeps phantom method symbols out.
_TS_NON_METHOD_KEYWORDS = frozenset({
    "if", "for", "while", "switch", "catch", "return", "await", "yield",
    "typeof", "instanceof", "in", "of", "new", "do", "else", "case",
    "function", "constructor",  # constructor handled separately
})


@dataclass
class FileSignature:
    path: str
    exports: list[str] = field(default_factory=list)
    routes: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    symbol_ranges: list[SymbolRange] = field(default_factory=list)
    source: str = field(default="", repr=False)

    def is_empty(self) -> bool:
        return not self.exports and not self.routes and not self.imports

    def to_prompt_line(self) -> str:
        """Formats the signature as a single line for LLM prompts."""
        parts = []
        if self.exports:
            parts.append(f"exports: {', '.join(self.exports[:8])}")
        if self.routes:
            parts.append(f"routes: {', '.join(self.routes[:5])}")
        if not parts:
            return ""
        return f"  {self.path} → {' | '.join(parts)}"


def extract_signatures(
    files: list[str],
    repo_path: str,
) -> dict[str, FileSignature]:
    """
    Extracts function/route/import signatures from TypeScript and JavaScript files.

    Args:
        files: List of relative file paths (relative to repo_path).
        repo_path: Absolute path to the repository root.

    Returns:
        Dict mapping relative file path → FileSignature.
        Non-TS/JS files are skipped and not included in the result.
    """
    result: dict[str, FileSignature] = {}
    root = Path(repo_path)
    # ``.vue`` is opt-in: only accepted when the flag is ON. With the flag
    # OFF (default) ``vue_on`` is False → ``.vue`` matches no accepted set
    # → skipped exactly as before (kill-switch byte-identical).
    vue_on = _vue_sfc_flows_enabled()

    for rel_path in files:
        suffix = Path(rel_path).suffix.lower()
        is_vue = vue_on and suffix in _VUE_EXTENSIONS
        if (
            suffix not in _TS_JS_EXTENSIONS
            and suffix not in _PYTHON_EXTENSIONS
            and suffix not in _GO_EXTENSIONS
            and suffix not in _RUST_EXTENSIONS
            and suffix not in _RUBY_EXTENSIONS
            and not is_vue
        ):
            continue
        abs_path = root / rel_path
        # H2: skip a symlink whose target escapes the repo root (worker-secret
        # read via a committed 120000 symlink). Internal symlinks + regular
        # files read exactly as before (byte-identical on legit repos).
        source = safe_read_text(abs_path, root, encoding="utf-8", errors="ignore")
        if source is None:
            continue

        if suffix in _PYTHON_EXTENSIONS:
            sig = _parse_python_file(rel_path, source)
        elif suffix in _GO_EXTENSIONS:
            sig = _parse_go_file(rel_path, source)
        elif suffix in _RUST_EXTENSIONS:
            sig = _parse_rust_file(rel_path, source)
        elif suffix in _RUBY_EXTENSIONS:
            sig = _parse_ruby_file(rel_path, source)
        elif is_vue:
            # Vue SFC — regex parse of the ``<script>`` blocks + template
            # handlers. Its script is TS/JS, but the file as a whole is
            # HTML-ish, so it must NOT go through the TS AST-span upgrade
            # (which would try to parse ``<template>`` as TS and fail).
            sig = _parse_vue_file(rel_path, source)
        else:
            sig = _parse_file(rel_path, source)
            sig.symbol_ranges = extract_symbol_ranges(source)
            if os.environ.get("WYSTAN_TS_AST", "1").strip().lower() \
                    not in ("0", "false", "no", "off"):
                try:  # W6-AST Hook A (M4): AST def-spans; None → keep regex
                    from wystan.pipeline_v2.ts_ast import adapter as _tsa
                    upgraded = _tsa.ast_symbol_ranges(
                        repo_path, rel_path, source, sig.symbol_ranges)
                    if upgraded is not None:
                        sig.symbol_ranges = upgraded
                except Exception:  # noqa: BLE001 — fallback law
                    pass

        # The T1 call-graph (flow_expansion/call_graph.py) scans a
        # symbol's body for callee identifiers via ``sig.source``. This
        # was previously populated ONLY for TS/JS, so every Python / Go /
        # Rust / Ruby flow collapsed to a single entry node (0 edges).
        # Populate it for every language so same-file + imported callees
        # resolve uniformly.
        sig.source = source

        if not sig.is_empty():
            result[rel_path] = sig

    return result


def _parse_go_file(rel_path: str, source: str) -> FileSignature:
    """Extract exports + symbol ranges from a Go source file.

    Go convention: identifiers starting with an uppercase letter are
    package-exported. Receiver methods on exported types
    (``func (s *Server) HandleX(...)``) count too.
    """
    sig = FileSignature(path=rel_path)
    seen: set[str] = set()
    raw: list[tuple[int, str, str]] = []  # (start_line, name, kind)

    for match in _RE_GO_FUNC.finditer(source):
        name = match.group(1)
        if name in seen:
            continue
        seen.add(name)
        sig.exports.append(name)
        line = source.count("\n", 0, match.start()) + 1
        raw.append((line, name, "function"))

    for match in _RE_GO_TYPE.finditer(source):
        name = match.group(1)
        if name in seen:
            continue
        seen.add(name)
        sig.exports.append(name)
        line = source.count("\n", 0, match.start()) + 1
        raw.append((line, name, "class"))

    for match in _RE_GO_VAR.finditer(source):
        name = match.group(1)
        if name in seen:
            continue
        seen.add(name)
        sig.exports.append(name)
        line = source.count("\n", 0, match.start()) + 1
        raw.append((line, name, "const"))

    sig.symbol_ranges = _ranges_from_raw(raw, source)
    return sig


def _parse_rust_file(rel_path: str, source: str) -> FileSignature:
    """Extract ``pub`` items and their line ranges from a Rust source file."""
    sig = FileSignature(path=rel_path)
    seen: set[str] = set()
    raw: list[tuple[int, str, str]] = []

    for match in _RE_RUST_PUB.finditer(source):
        name = match.group(1)
        if name in seen:
            continue
        seen.add(name)
        sig.exports.append(name)
        line = source.count("\n", 0, match.start()) + 1
        # Crude kind detection from the matched item keyword
        text = match.group(0)
        if "fn " in text:
            kind = "function"
        elif "struct " in text or "enum " in text or "trait " in text:
            kind = "class"
        elif "type " in text:
            kind = "type"
        else:
            kind = "const"
        raw.append((line, name, kind))

    sig.symbol_ranges = _ranges_from_raw(raw, source)
    return sig


def _ranges_from_raw(
    raw: list[tuple[int, str, str]], source: str,
) -> list[SymbolRange]:
    """Convert (start_line, name, kind) tuples to ``SymbolRange`` with end_line.

    End-of-symbol heuristic: extends until the start of the next top-
    level symbol (or EOF). Good enough for symbol-scoped queries
    where exact boundaries matter less than catching the right
    function body.
    """
    if not raw:
        return []
    raw_sorted = sorted(raw, key=lambda x: x[0])
    total_lines = source.count("\n") + 1
    out: list[SymbolRange] = []
    for i, (line, name, kind) in enumerate(raw_sorted):
        end_line = (
            raw_sorted[i + 1][0] - 1
            if i + 1 < len(raw_sorted)
            else total_lines
        )
        if end_line < line:
            end_line = line
        out.append(SymbolRange(
            name=name, start_line=line, end_line=end_line, kind=kind,
        ))
    return out


def _parse_file(rel_path: str, source: str) -> FileSignature:
    sig = FileSignature(path=rel_path)

    # Collect named exports
    seen_exports: set[str] = set()

    for match in _RE_NAMED_EXPORT.finditer(source):
        name = match.group(1)
        if name not in seen_exports:
            seen_exports.add(name)
            sig.exports.append(name)

    for match in _RE_DEFAULT_EXPORT.finditer(source):
        name = match.group(1)
        if name not in seen_exports:
            seen_exports.add(name)
            sig.exports.append(name)

    for match in _RE_REEXPORT.finditer(source):
        for token in match.group(1).split(","):
            # Handle "Foo as Bar" → take the exported name "Bar"
            parts = token.strip().split(" as ")
            name = parts[-1].strip()
            if name and name not in seen_exports:
                seen_exports.add(name)
                sig.exports.append(name)

    # Collect route definitions
    for match in _RE_NEXTJS_ROUTE.finditer(source):
        method = match.group(1)
        # Infer path from the file path for App Router (files live at the route path)
        route_path = _infer_nextjs_route_path(rel_path)
        sig.routes.append(f"{method} {route_path}")

    for match in _RE_NEXTJS_PAGE.finditer(source):
        sig.routes.append(match.group(1))

    for match in _RE_EXPRESS_ROUTE.finditer(source):
        method = match.group(1).upper()
        path = match.group(2)
        sig.routes.append(f"{method} {path}")

    # Collect imports. We keep:
    #   * relative ('./x', '../x') and builtin aliases ('@/x', '~/x', '#/x')
    #     — always internal;
    #   * SCOPED bare specifiers ('@scope/pkg[/subpath]') — these are the
    #     workspace cross-package imports ('@calcom/lib', '@calcom/features/…')
    #     that the downstream resolver maps to real files via the
    #     package.json#name → dir map. A scoped specifier that is genuinely
    #     third-party (e.g. '@sentry/node') simply fails resolution and adds
    #     no edge, so retaining it here is safe — the resolver is the single
    #     gate. (Previously these were dropped at parse time, which made the
    #     cross-package callee bodies unreachable for flow tracing.)
    # We still skip UNSCOPED bare specifiers ('react', 'next/server') to keep
    # the import list lean; unscoped workspace package names are far rarer and
    # the directory-name monorepo resolver already covers the common case.
    for match in _RE_IMPORT.finditer(source):
        src = match.group(1)
        if (
            src.startswith(".")
            or src.startswith("@/")
            or src.startswith("~/")
            or src.startswith("#/")
            or src.startswith("@")  # scoped workspace/3p — resolver gates it
        ):
            sig.imports.append(src)

    return sig


def _parse_python_file(rel_path: str, source: str) -> FileSignature:
    """Extract exports, routes, and symbol ranges from a Python file.

    Prefers the stdlib :mod:`ast` module for symbol ranges: it gives
    EXACT ``(node.lineno, node.end_lineno)`` boundaries for every
    ``def`` / ``async def`` / ``class`` — including nested methods —
    which the regex heuristic (next-symbol-start-minus-one) could only
    approximate. Precise ranges matter for the T1 call graph, which
    scans a symbol's body line-slice for callee identifiers: a too-wide
    range pulls in sibling functions' calls (over-attribution), a
    too-narrow one misses real callees.

    ``exports`` keeps MODULE-LEVEL names only (unchanged contract for
    Stage 3's MIN_EXPORTS_FOR_FLOW_DETECTION gate). Nested methods get
    symbol *ranges* (so same-file ``self._helper()`` callees resolve)
    but are NOT added to ``exports`` — that would inflate the export
    list with private internals and shift flow-detection vocabulary.

    Falls back to the regex scanner when the source is not valid Python
    (partial files, syntax errors, templating) so we never regress to
    zero symbols on a parse failure.
    """
    sig = FileSignature(path=rel_path)

    # Routes are regex-derived in both paths (decorators are awkward to
    # match structurally and the regex already generalises across
    # FastAPI / Flask / blueprint styles via the stack-agnostic pattern).
    for match in _RE_PYTHON_ROUTE.finditer(source):
        method = match.group(1).upper()
        path = match.group(2)
        sig.routes.append(f"{method} {path}")

    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        _python_symbols_via_regex(sig, source)
        return sig

    total_lines = source.count("\n") + 1
    seen_exports: set[str] = set()
    seen_range_keys: set[tuple[str, int]] = set()

    # Class-aware walk: a ``def`` whose nearest enclosing scope is a
    # ``class`` is a METHOD (tag kind="method"/"constructor" + parent) so a
    # cross-file member call ``instance.find_by_id()`` resolves to that
    # method's OWN exact range, never the whole class. Module-level ``def``
    # stays ``function``; classes stay ``class`` (kept for anchoring).
    # ``__init__`` is tagged ``constructor`` to mirror the TS path (so a
    # ``Class(...)`` construction attributes the initialiser body only).
    def _walk(node: ast.AST, parent_class: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                start = child.lineno
                end = getattr(child, "end_lineno", None) or start
                key = (child.name, start)
                if key not in seen_range_keys:
                    seen_range_keys.add(key)
                    sig.symbol_ranges.append(SymbolRange(
                        name=child.name, start_line=start,
                        end_line=max(start, end), kind="class",
                    ))
                _walk(child, child.name)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = child.lineno
                end = getattr(child, "end_lineno", None) or start
                if parent_class is not None:
                    kind = (
                        "constructor"
                        if child.name == "__init__"
                        else "method"
                    )
                else:
                    kind = "function"
                key = (child.name, start)
                if key not in seen_range_keys:
                    seen_range_keys.add(key)
                    sig.symbol_ranges.append(SymbolRange(
                        name=child.name, start_line=start,
                        end_line=max(start, end), kind=kind,
                        parent=parent_class,
                    ))
                # Recurse into the function body too (nested defs / closures
                # keep kind="function"; nested classes get their own parent).
                _walk(child, None)
            else:
                _walk(child, parent_class)

    _walk(tree, None)

    # Module-level names → exports (stable Stage-3 contract).
    for node in tree.body:
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ):
            if node.name not in seen_exports:
                seen_exports.add(node.name)
                sig.exports.append(node.name)

    if not sig.symbol_ranges and total_lines:
        # No defs/classes at all (e.g. a script of bare statements) —
        # nothing to attribute; leave ranges empty.
        pass

    return sig


def _python_symbols_via_regex(sig: FileSignature, source: str) -> None:
    """Regex fallback for Python files that don't parse via ``ast``.

    Module-level ``class`` / ``def`` only (the ``^`` anchors require
    column-0). End-of-symbol = next symbol's start - 1 (EOF for last).
    """
    seen: set[str] = set()
    raw_symbols: list[tuple[int, str, str]] = []

    for match in _RE_PYTHON_CLASS.finditer(source):
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            sig.exports.append(name)
            line = source.count("\n", 0, match.start()) + 1
            raw_symbols.append((line, name, "class"))

    for match in _RE_PYTHON_FUNC.finditer(source):
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            sig.exports.append(name)
            line = source.count("\n", 0, match.start()) + 1
            raw_symbols.append((line, name, "function"))

    raw_symbols.sort(key=lambda x: x[0])
    total_lines = source.count("\n") + 1
    for i, (start, name, kind) in enumerate(raw_symbols):
        end = (
            raw_symbols[i + 1][0] - 1
            if i + 1 < len(raw_symbols) else total_lines
        )
        sig.symbol_ranges.append(SymbolRange(
            name=name, start_line=start, end_line=max(start, end),
            kind=kind,
        ))


def _attach_ruby_assoc_ranges(sig: FileSignature, source: str) -> None:
    """fixb122 (A) — mint 1-line ranges for assoc/scope exports, FALLBACK-ONLY.

    A name is given a range **only when it has none already**. That guard
    is the whole mechanism, not a nicety: the naive form (mint
    unconditionally) hijacks two live exhibits measured on the capture —
    ``maybe app/models/budget_category.rb`` where the METHOD ``category``
    (line 44) would be overridden by ``belongs_to :category`` (line 5),
    and ``maybe app/models/rule/condition.rb`` where the METHOD ``rule``
    (line 14) would be overridden by ``belongs_to :rule`` (line 2). A real
    definition always outranks a declaration; both are named anti-cases.

    Repo-wide blast of the fallback-only form, measured before the code
    (probe ``m3d3_blast.py``): chatwoot 395 / 9403 exports gain a line,
    **0** collide with an existing range; maybe 172 / 2958 gain a line, 2
    collide — and those 2 are exactly the exhibits above, which this guard
    leaves untouched.

    The minted spans are one line wide *by construction*, so they can
    never become a flow body: ``call_graph._entry_range_containing_line``
    only considers ranges with ``end_line > start_line`` (VERIFIED), and
    ``degrade_span.WIDEN_ALLOWED_KINDS`` does not contain the assoc kinds.
    An association IS one line — that is the honest span for it.

    Determinism: a name declared twice keeps its EARLIEST declaration, and
    the appended ranges are sorted by ``(start_line, name)``.
    """
    if not _ruby_assoc_ranges_enabled():
        return
    taken = {r.name for r in sig.symbol_ranges}
    minted: dict[str, SymbolRange] = {}
    for regex, kind in (
        (_RE_RUBY_AR_ASSOC, _RUBY_ASSOC_KIND),
        (_RE_RUBY_AR_SCOPE, _RUBY_SCOPE_KIND),
    ):
        for match in regex.finditer(source):
            name = match.group(1)
            if name in taken:
                continue          # real definition wins — the anti-cases
            line = source.count("\n", 0, match.start()) + 1
            previous = minted.get(name)
            if previous is None or line < previous.start_line:
                minted[name] = SymbolRange(
                    name=name, start_line=line, end_line=line, kind=kind,
                )
    sig.symbol_ranges.extend(
        sorted(minted.values(), key=lambda r: (r.start_line, r.name)),
    )


def _parse_ruby_file(rel_path: str, source: str) -> FileSignature:
    """Extract exports + symbol ranges from a Ruby source file.

    Treats classes, modules, top-level methods, and uppercase constants
    as "exports" — enough for Stage 3's MIN_EXPORTS_FOR_FLOW_DETECTION
    gate. Also surfaces ActiveRecord associations (``has_many :foos``)
    and scopes (``scope :recent``) as exports because in a Rails domain
    these ARE the user-visible vocabulary; surfacing them gives the
    flow-detection LLM richer ground to name flows.

    Routes (``get '/path' => 'controller#action'`` in config/routes.rb)
    populate ``sig.routes``.
    """
    sig = FileSignature(path=rel_path)
    seen: set[str] = set()
    raw_symbols: list[tuple[int, str, str]] = []

    for match in _RE_RUBY_CLASS.finditer(source):
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            sig.exports.append(name)
            line = source.count("\n", 0, match.start()) + 1
            raw_symbols.append((line, name, "class"))

    for match in _RE_RUBY_MODULE.finditer(source):
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            sig.exports.append(name)
            line = source.count("\n", 0, match.start()) + 1
            raw_symbols.append((line, name, "module"))

    for match in _RE_RUBY_DEF.finditer(source):
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            sig.exports.append(name)
            line = source.count("\n", 0, match.start()) + 1
            raw_symbols.append((line, name, "method"))

    for match in _RE_RUBY_CONST.finditer(source):
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            sig.exports.append(name)
            line = source.count("\n", 0, match.start()) + 1
            raw_symbols.append((line, name, "constant"))

    for match in _RE_RUBY_AR_ASSOC.finditer(source):
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            sig.exports.append(name)

    for match in _RE_RUBY_AR_SCOPE.finditer(source):
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            sig.exports.append(name)

    for match in _RE_RUBY_ROUTE.finditer(source):
        method = match.group(1).upper()
        path = match.group(2)
        sig.routes.append(f"{method} {path}")

    # fixb115 Hook (armed, default OFF) — real ``def``…``end`` boundaries
    # from :mod:`pipeline_v2.ruby_def_spans` (keyword-depth matching, the
    # go_func_spans precedent) replace the "end = next symbol's start − 1"
    # heuristic below. Measured against the ruby interpreter's own AST:
    # exact method spans 4.5% → 99.5% (chatwoot, 7101 methods) and
    # 11.0% → 99.4% (maybe, 2180). ``sig.exports`` is deliberately NOT
    # touched — only the BOUNDARIES move, never the name vocabulary.
    # Empty result (or an unparsable file) falls back to the heuristic.
    if _ruby_def_spans_enabled():
        try:
            from wystan.pipeline_v2.ruby_def_spans import symbol_ranges_for
            upgraded = symbol_ranges_for(source)
        except Exception:  # noqa: BLE001 — fallback law
            upgraded = []
        if upgraded:
            sig.symbol_ranges.extend(
                SymbolRange(
                    name=s.name, start_line=s.start_line,
                    end_line=s.end_line, kind=s.kind,
                )
                for s in upgraded
            )
            _attach_ruby_assoc_ranges(sig, source)
            return sig

    raw_symbols.sort(key=lambda x: x[0])
    total_lines = source.count("\n") + 1
    for i, (start, name, kind) in enumerate(raw_symbols):
        end = (
            raw_symbols[i + 1][0] - 1
            if i + 1 < len(raw_symbols) else total_lines
        )
        sig.symbol_ranges.append(SymbolRange(
            name=name, start_line=start, end_line=max(start, end),
            kind=kind,
        ))

    # fixb122 (A) — BOTH exit paths get the fallback-only assoc ranges: the
    # def-spans branch above returns early, and neither branch ever gave an
    # association a range. Attaching in one place only would make the flag
    # inert in the live world (the P14 dead-reader class, one layer down).
    _attach_ruby_assoc_ranges(sig, source)
    return sig


def _parse_vue_file(rel_path: str, source: str) -> FileSignature:
    """Extract flow-candidates from a Vue Single-File Component (``.vue``).

    GRAIN — mirrors the TS/JS extractor's *exposed-surface* contract. In a
    ``<script setup>`` block EVERY top-level binding is auto-exposed to the
    template (there is no ``export`` keyword), so a top-level
    ``const save = () => …`` / ``function onSubmit() …`` IS the Vue
    analogue of a TS ``export``. Options-API ``methods: { … }`` entries,
    ``export``-marked names in a plain ``<script>`` block, and template
    ``@event="handler"`` bindings are handlers too. All become ``exports``
    so a feature built from ``.vue`` files clears Stage 3's
    ``MIN_EXPORTS_FOR_FLOW_DETECTION`` gate.

    Before this parser existed every ``.vue`` file skipped → 0 exports →
    the Stage-3 short-circuit guaranteed ``flows=[]`` on Vue-front
    features (hoppscotch mockServer / collections / http / graphql; the
    directus admin modules; the whole chatwoot front-end).

    Deterministic (regex only — no LLM, no tree-sitter), same discipline
    as :func:`_parse_ruby_file`. The caller gates invocation behind
    ``WYSTAN_VUE_SFC_FLOWS``.
    """
    sig = FileSignature(path=rel_path)
    conv = _vue_conventions()
    reactivity = conv["reactivity_primitives"]

    scripts = list(_RE_VUE_SCRIPT_BLOCK.finditer(source))
    if not scripts and not _RE_VUE_TEMPLATE_BLOCK.search(source):
        return sig  # empty / malformed SFC — nothing to attribute

    seen: set[str] = set()
    raw: list[tuple[int, str, str]] = []

    def _add(name: str, line: int, kind: str) -> None:
        if (
            not name
            or name in seen
            or name in _TS_NON_METHOD_KEYWORDS
            or name in reactivity
        ):
            return
        seen.add(name)
        sig.exports.append(name)
        raw.append((line, name, kind))

    for sm in scripts:
        block = sm.group(1)
        # Newlines before the block body → absolute line of block line 1.
        base = source.count("\n", 0, sm.start(1))

        # <script setup> top-level (col-0) function + arrow-const decls.
        for match in _RE_LOCAL_FUNC_DECL.finditer(block):
            _add(match.group(1),
                 base + block.count("\n", 0, match.start()) + 1, "function")
        for match in _RE_LOCAL_ARROW_DECL.finditer(block):
            _add(match.group(1),
                 base + block.count("\n", 0, match.start()) + 1, "function")
        # Plain <script> named / default exports (non-setup components).
        for match in _RE_NAMED_EXPORT.finditer(block):
            _add(match.group(1),
                 base + block.count("\n", 0, match.start()) + 1, "function")
        for match in _RE_DEFAULT_EXPORT.finditer(block):
            _add(match.group(1),
                 base + block.count("\n", 0, match.start()) + 1, "class")
        # Options-API ``methods: { … }`` member names. The methods object
        # behaves like a class body, so reuse the depth-1 member indexer
        # (handles nested calls / arrow-field members correctly).
        for mm in _RE_VUE_METHODS.finditer(block):
            span = _find_class_body_span(block, mm.start())
            if span is None:
                continue
            for mr in _extract_class_methods(block, "methods", span[0], span[1]):
                _add(mr.name, base + mr.start_line, mr.kind)

    # Template handler references — catches a handler destructured from a
    # composable (``const { save } = useThing()``) that the decl regexes
    # miss. No reliable source line for a template ref → no symbol range.
    for tm in _RE_VUE_TEMPLATE_BLOCK.finditer(source):
        for hm in _RE_VUE_TEMPLATE_HANDLER.finditer(tm.group(1)):
            name = hm.group(1)
            if (
                name
                and not name.startswith("$")  # Vue built-ins ($emit/$refs/…)
                and name not in seen
                and name not in _TS_NON_METHOD_KEYWORDS
                and name not in reactivity
            ):
                seen.add(name)
                sig.exports.append(name)

    # Imports for the T1 call graph (same filter as :func:`_parse_file`).
    for match in _RE_IMPORT.finditer(source):
        src = match.group(1)
        if (
            src.startswith(".")
            or src.startswith("@/")
            or src.startswith("~/")
            or src.startswith("#/")
            or src.startswith("@")
        ):
            sig.imports.append(src)

    sig.symbol_ranges = _ranges_from_raw(raw, source)
    return sig


def _infer_nextjs_route_path(rel_path: str) -> str:
    """
    Infers the Next.js API route path from the file's relative path.

    Examples:
        app/api/auth/login/route.ts → /api/auth/login
        pages/api/auth.ts           → /api/auth
        src/app/api/users/route.ts  → /api/users
    """
    p = Path(rel_path)
    parts = p.parts

    # Drop leading src/, app/ wrappers
    skip = {"src", "app"}
    start = 0
    for i, part in enumerate(parts):
        if part not in skip:
            start = i
            break

    trimmed = parts[start:]

    # Drop trailing "route.ts" filename
    if trimmed and Path(trimmed[-1]).stem == "route":
        trimmed = trimmed[:-1]
    else:
        # Drop the filename extension for pages/api style
        trimmed = trimmed[:-1] + (Path(trimmed[-1]).stem,) if trimmed else trimmed

    return "/" + "/".join(trimmed) if trimmed else "/"


def _find_class_body_span(
    source: str, class_decl_offset: int,
) -> tuple[int, int] | None:
    """Return ``(body_open_offset, body_close_offset)`` for a class body.

    Starting at the class declaration char offset, find the first ``{``
    (the class body open brace) and scan forward tracking brace depth
    (skipping braces inside strings / template literals / line + block
    comments) until the matching close brace. Returns char offsets of the
    open and close brace, or ``None`` if unbalanced (truncated / malformed
    source) — the caller then simply skips method indexing for that class
    and keeps the whole-class symbol as before (graceful degrade).
    """
    n = len(source)
    i = source.find("{", class_decl_offset)
    if i < 0:
        return None
    open_off = i
    depth = 0
    in_str: str | None = None       # current string/template delimiter
    in_line_comment = False
    in_block_comment = False
    while i < n:
        c = source[i]
        nxt = source[i + 1] if i + 1 < n else ""
        if in_line_comment:
            if c == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if c == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if in_str is not None:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
            i += 1
            continue
        # not in string/comment
        if c == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if c == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        if c in ("'", '"', "`"):
            in_str = c
            i += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return (open_off, i)
        i += 1
    return None


def _extract_class_methods(
    source: str,
    class_name: str,
    body_open_off: int,
    body_close_off: int,
) -> list[SymbolRange]:
    """Index each method / arrow-field of a class body as its own symbol.

    The method body span is approximated the same scale-invariant way the
    top-level extractor uses: a method runs until the NEXT method's start
    line minus one (or the class body close for the last one). This gives a
    tight per-method line range so a member call resolves to ONE method's
    lines, not the whole 1800-line class. Constructors are tagged
    ``kind="constructor"`` so the call-graph resolver can attribute them on
    ``new Class()`` separately.

    Only DIRECT members of THIS class body are indexed — declarations that
    live in a nested block (deeper brace depth than the class body) are
    skipped, so inner-function locals never masquerade as methods.
    """
    # Identify the line numbers spanned by the class body.
    body_open_line = source.count("\n", 0, body_open_off) + 1
    body_close_line = source.count("\n", 0, body_close_off) + 1
    lines = source.splitlines()

    # Pre-compute, per line index, the brace depth RELATIVE to the class
    # body open, so we only accept method declarations at the body's
    # immediate level (depth 1 inside the class). Track string/comment
    # state across lines to avoid counting braces in literals.
    raw: list[tuple[int, str, str]] = []  # (start_line, name, kind)
    depth = 0
    in_str: str | None = None
    in_block_comment = False
    # Walk char-by-char from body_open_off to body_close_off, but record a
    # candidate only when we are exactly at depth 1 (immediate member) and
    # at the START of a line's first significant token.
    # Simpler + robust: iterate lines, maintain depth at line START.
    # Compute depth at the start of each line by scanning the body once.
    line_start_depth: dict[int, int] = {}
    i = body_open_off
    cur_line = body_open_line
    line_start_depth[cur_line] = 0
    n = body_close_off
    while i <= n:
        c = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""
        if c == "\n":
            cur_line += 1
            line_start_depth[cur_line] = depth
            i += 1
            continue
        if in_block_comment:
            if c == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if in_str is not None:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
            i += 1
            continue
        if c == "/" and nxt == "/":
            # line comment — skip to EOL
            j = source.find("\n", i)
            if j < 0:
                break
            i = j
            continue
        if c == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        if c in ("'", '"', "`"):
            in_str = c
            i += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1

    seen: set[str] = set()
    for ln in range(body_open_line, body_close_line + 1):
        idx = ln - 1
        if idx < 0 or idx >= len(lines):
            continue
        # Only immediate members: the line must START at class-body depth 1.
        if line_start_depth.get(ln, 99) != 1:
            continue
        line_txt = lines[idx]
        stripped = line_txt.strip()
        if stripped.startswith("constructor"):
            if "constructor" not in seen and re.match(
                r"constructor\s*\(", stripped,
            ):
                seen.add("constructor")
                raw.append((ln, "constructor", "constructor"))
            continue
        m = _RE_TS_METHOD.match(line_txt)
        if not m:
            continue
        name = m.group(1)
        if name in _TS_NON_METHOD_KEYWORDS or name in seen:
            continue
        seen.add(name)
        raw.append((ln, name, "method"))

    if not raw:
        return []
    raw.sort(key=lambda x: x[0])
    out: list[SymbolRange] = []
    for k, (start, name, kind) in enumerate(raw):
        end = (
            raw[k + 1][0] - 1
            if k + 1 < len(raw)
            else body_close_line
        )
        out.append(SymbolRange(
            name=name,
            start_line=start,
            end_line=max(start, end),
            kind=kind,
            parent=class_name,
        ))
    return out


def _extract_all_class_methods(source: str) -> list[SymbolRange]:
    """Index methods for EVERY class declared in a TS/JS source file."""
    out: list[SymbolRange] = []
    for m in _RE_TS_CLASS_DECL.finditer(source):
        class_name = m.group(1)
        span = _find_class_body_span(source, m.start())
        if span is None:
            continue
        out.extend(
            _extract_class_methods(source, class_name, span[0], span[1])
        )
    return out


def extract_symbol_ranges(source: str) -> list[SymbolRange]:
    """Extracts line ranges for each exported symbol in TS/JS source.

    MVP heuristic: each export's end_line = next export's start_line - 1,
    or EOF for the last export. This avoids complex brace-balancing but
    gives reasonable line attribution for most files.

    Additionally indexes class METHODS / constructors / arrow class-fields
    as their own ``SymbolRange`` (kind ``method`` / ``constructor``,
    ``parent`` = class name) so a member call ``obj.findById()`` resolves
    to the specific method body rather than the whole enclosing class. The
    class symbol itself is KEPT (feature anchoring depends on it).
    """
    total_lines = source.count("\n") + 1
    # Collect all export positions with their symbol names and kinds
    exports: list[tuple[int, str, str]] = []  # (start_line, name, kind)

    for match in _RE_NAMED_EXPORT.finditer(source):
        line = source[:match.start()].count("\n") + 1
        name = match.group(1)
        # Determine kind from the keyword before the name
        text = source[match.start():match.end()]
        if "function" in text:
            kind = "function"
        elif "class" in text:
            kind = "class"
        else:
            kind = "const"
        exports.append((line, name, kind))

    for match in _RE_DEFAULT_EXPORT.finditer(source):
        line = source[:match.start()].count("\n") + 1
        name = match.group(1)
        text = source[match.start():match.end()]
        kind = "class" if "class" in text else "function"
        exports.append((line, name, kind))

    for match in _RE_TYPE_EXPORT.finditer(source):
        line = source[:match.start()].count("\n") + 1
        name = match.group(1)
        text = source[match.start():match.end()]
        if "enum" in text:
            kind = "enum"
        elif "interface" in text:
            kind = "type"
        else:
            kind = "type"
        exports.append((line, name, kind))

    for match in _RE_REEXPORT.finditer(source):
        line = source[:match.start()].count("\n") + 1
        for token in match.group(1).split(","):
            parts = token.strip().split(" as ")
            name = parts[-1].strip()
            if name:
                exports.append((line, name, "reexport"))

    # Top-level LOCAL function / arrow declarations. Recorded with
    # kind="local" so callers can tell them apart from exports. They are
    # appended AFTER exports so that a name which is BOTH exported and
    # locally declared keeps its export kind (first-occurrence dedup
    # below). This is what lets the call-graph tracer resolve handler
    # references like ``const POST = wrap(postHandler)`` whose body lives
    # in a non-exported ``postHandler`` symbol. STRUCTURAL + stack-neutral
    # (no hardcoded wrapper or handler names).
    for match in _RE_LOCAL_FUNC_DECL.finditer(source):
        line = source[:match.start()].count("\n") + 1
        exports.append((line, match.group(1), "local"))
    for match in _RE_LOCAL_ARROW_DECL.finditer(source):
        line = source[:match.start()].count("\n") + 1
        exports.append((line, match.group(1), "local"))

    # Class METHODS / constructors as their own tight ranges (computed by a
    # brace-balanced scan, independent of the top-level next-export
    # heuristic). Appended below AFTER top-level dedup so a method named the
    # same as a top-level symbol never shadows the top-level one — methods
    # are namespaced by ``parent`` and resolved member-aware downstream.
    method_ranges = _extract_all_class_methods(source)

    if not exports and not method_ranges:
        return []

    # Sort by start_line, deduplicate by name (keep first occurrence so an
    # exported symbol's kind wins over a later same-name local match).
    exports.sort(key=lambda x: x[0])
    seen: set[str] = set()
    unique: list[tuple[int, str, str]] = []
    for start, name, kind in exports:
        if name not in seen:
            seen.add(name)
            unique.append((start, name, kind))

    # Assign end_line: next export's start_line - 1, or EOF for last
    ranges = []
    for i, (start, name, kind) in enumerate(unique):
        if i + 1 < len(unique):
            end = unique[i + 1][0] - 1
        else:
            end = total_lines
        ranges.append(SymbolRange(
            name=name, start_line=start, end_line=max(start, end), kind=kind,
        ))

    # Append method-level symbols (kept distinct from top-level symbols via
    # their ``parent`` field; a member call resolves to these tight ranges).
    ranges.extend(method_ranges)

    return ranges


def get_symbol_range(
    rel_path: str,
    source: str,
    symbol_name: str,
) -> SymbolRange | None:
    """Return the line range of a single named symbol in ``source``.

    Sprint 12 Day 4 — used by the per-flow symbol picker to resolve
    a Haiku-selected ``(file, symbol)`` pair into a concrete
    ``SymbolRange`` with start_line / end_line. Returns ``None`` if
    the symbol cannot be located.

    Routes through the appropriate language extractor based on file
    extension:
        - ``.py`` → Python class / function regex
        - ``.ts`` / ``.tsx`` / ``.js`` / ``.jsx`` / ``.mts`` / ``.cts``
          → TS/JS export regex
        - other → ``None`` (not yet supported)
    """
    if not symbol_name:
        return None
    ext = ""
    dot = rel_path.rfind(".")
    if dot >= 0:
        ext = rel_path[dot:].lower()

    if ext == ".py":
        sig = _parse_python_file(rel_path, source)
        ranges = sig.symbol_ranges
    elif ext in _RUBY_EXTENSIONS:
        sig = _parse_ruby_file(rel_path, source)
        ranges = sig.symbol_ranges
    elif ext in {".ts", ".tsx", ".js", ".jsx", ".mts", ".cts"}:
        ranges = extract_symbol_ranges(source)
    else:
        return None

    for r in ranges:
        if r.name == symbol_name:
            return r
    return None


def list_exported_symbols(rel_path: str, source: str) -> list[SymbolRange]:
    """All exported / top-level symbols in a file with their ranges.

    Sprint 12 Day 4 — used by the symbol picker to feed the candidate
    list into Haiku. Empty list when language is unsupported or the
    file has no symbols.
    """
    ext = ""
    dot = rel_path.rfind(".")
    if dot >= 0:
        ext = rel_path[dot:].lower()
    if ext == ".py":
        return _parse_python_file(rel_path, source).symbol_ranges
    if ext in _RUBY_EXTENSIONS:
        return _parse_ruby_file(rel_path, source).symbol_ranges
    if ext in {".ts", ".tsx", ".js", ".jsx", ".mts", ".cts"}:
        return extract_symbol_ranges(source)
    return []


def extract_named_imports(source: str) -> dict[str, set[str]]:
    """Extracts named imports from TS/JS source.

    Returns:
        Dict mapping module path → set of imported symbol names.
        For namespace imports (import * as X), returns {"*"} as the symbol set.
    """
    result: dict[str, set[str]] = {}

    # NO module-prefix filter here: the old ``./`` / ``@/`` / ``~/``
    # guard dropped workspace-scoped modules (``@scope/pkg/...``) and
    # custom aliases before resolution ever ran (WS3 oracle, 2026-07-03).
    # Callers resolve each module against the tracked file set — external
    # packages simply resolve to ``None`` and stay silent.
    for match in _RE_NAMED_IMPORT.finditer(source):
        names_str = match.group(1)
        module = match.group(2)
        names = set()
        for token in names_str.split(","):
            parts = token.strip().split(" as ")
            original = parts[0].strip()
            # Inline type modifier: ``import { type Foo, Bar } from …``.
            if original.startswith("type "):
                original = original[len("type "):].strip()
            if original:
                names.add(original)
        if names:
            result.setdefault(module, set()).update(names)

    for match in _RE_NAMESPACE_IMPORT.finditer(source):
        module = match.group(1)
        result.setdefault(module, set()).add("*")

    return result
