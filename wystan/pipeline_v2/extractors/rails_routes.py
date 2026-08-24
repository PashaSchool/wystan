"""RailsRoutesExtractor — parse ``config/routes.rb`` for declared routes.

Rails route declarations are the most authoritative feature signal in
a Rails app: every customer-facing URL transit passes through this
file. We use a regex-based reader (NOT a Ruby AST) because we cannot
assume the user has a Ruby toolchain installed, and the four idioms
below cover the vast majority of real-world routes.rb files.

Patterns are loaded from ``eval/stacks/rails-app.yaml``; this module
just iterates them and emits anchors. Activation is gated by
:func:`is_rails_app` — no work happens on non-Rails repos.

B108 route SUPPLY (``WYSTAN_RAILS_ROUTES_SUPPLY``, default OFF)
=================================================================
The slug patterns above answer "which features exist"; they never
answered "which HTTP methods land on which file". ``emit()`` returned
``paths=('config/routes.rb',)`` with ``routes=()``, and
``build_routes_index`` Pass A skips any candidate whose ``routes`` is
empty — so on a Rails board NO route row ever reached ``routes_index``
(P8 forensics; the mint says so itself at
``stage_6_86_anchored_mint.py``: "no route channel reached the
routes_index at all"). Every verb-fact consumer downstream
(``route_verb_indexes`` → ``verb:route-method`` /
``structural:verb-composition``, the 6.7e adjudicator rung, UF
domain-attribution, e2e journey stitching) was therefore starved on
Rails.

The supply pass resolves each declaration to the controller file that
HANDLES it, using the Rails routing convention declared in
``rails-app.yaml`` under ``routes.supply``. Two laws it obeys:

* **A1 — a declaration file is not a member file.** Rows carry the
  resolved controller path, never ``config/routes.rb``: every consumer
  keys on ``routes_index[].file`` being a MEMBER path, so a row naming
  the declaration would move a counter and ground nothing.
* **A3 — an unresolvable declaration is an honest hole.** A controller
  reference that no tracked file satisfies under the convention (a
  Rails ENGINE root that redeclares its own module chain, a
  ``mount``ed rack app, a bare ``redirect``) emits NOTHING. Guessing
  would manufacture false grounding; the gap is reported to the
  composition-completeness guard (R2) instead.

``build_routes_index`` Pass A already accepts explicit ``routes`` from
EVERY extractor source, so the delivery rail needs no change — the
cargo was simply empty. The display layer arms its R1/R2 snap guards on
EVIDENCE (:func:`is_rails_handler_path` rows present in ``routes_index``)
rather than on the env flag, so a board the Rails channel did not supply
is untouched even when the flag is armed.

No LLM. No network. Read-only.
"""

from __future__ import annotations

import logging
import os
import re
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from wystan.pipeline_v2.extractors._rails import (
    RailsPatternExtractor,
    load_rails_config,
    pluralize,
    singularize,
)
from wystan.pipeline_v2.extractors._util import (
    is_noise,
    posix,
    read_text,
    slugify,
)
from wystan.pipeline_v2.extractors.base import AnchorCandidate

if TYPE_CHECKING:
    from wystan.pipeline_v2.stage_0_intake import ScanContext


logger = logging.getLogger(__name__)

#: B108 — arms the route-supply pass. Default **OFF** (armed);
#: registered in ``scan_result_cache.ENV_OUTPUT_FLAGS``. Unset / ``"0"``
#: leaves ``AnchorCandidate.routes`` empty ⇒ Pass A skips ⇒ every board
#: is byte-identical (kill-switch law).
RAILS_ROUTES_SUPPLY_ENV = "WYSTAN_RAILS_ROUTES_SUPPLY"


def rails_routes_supply_enabled() -> bool:
    """B108 Rails route-supply. Default **OFF** (armed):
    ``WYSTAN_RAILS_ROUTES_SUPPLY=1`` makes ``rails-routes`` candidates
    carry explicit ``(pattern, method, handler_file, line, handler)``
    tuples for ``build_routes_index`` Pass A. OFF ⇒ ``routes=()`` ⇒
    ``routes_index`` + every downstream board byte-identical."""
    return os.environ.get(RAILS_ROUTES_SUPPLY_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _supply_cfg(config: dict | None = None) -> dict:
    """The ``routes.supply`` convention block (YAML — never hardcoded)."""
    cfg = config if config is not None else load_rails_config()
    routes_cfg = (cfg or {}).get("routes") or {}
    if not isinstance(routes_cfg, dict):
        return {}
    sup = routes_cfg.get("supply") or {}
    return sup if isinstance(sup, dict) else {}


def is_rails_handler_path(path: str, config: dict | None = None) -> bool:
    """True iff ``path`` is a Rails route-HANDLER file by convention —
    i.e. a ``*_controller.rb`` under any ``app/controllers/`` root
    (engines included). Convention values come from ``rails-app.yaml``;
    this is a pure path predicate with no filesystem access.

    Consumed by the R2 composition-completeness guard to tell a member
    file the route channel SHOULD have covered (a controller that failed
    to resolve — anti-case A3) from one it never could (a model /
    service / job — anti-case A4)."""
    sup = _supply_cfg(config)
    marker = str(sup.get("controller_dir_marker") or "")
    suffix = str(sup.get("controller_suffix") or "")
    if not marker or not suffix:
        return False
    p = str(path or "")
    return bool(p.endswith(suffix) and marker in p)


# ── Route-supply parser ────────────────────────────────────────────────


class _SupplyRules:
    """Compiled ``routes.supply`` convention. All values come from YAML."""

    __slots__ = (
        "ok", "marker", "suffix", "namespace_re", "scope_module_re",
        "scope_path_re", "to_re", "fat_arrow_re", "controller_kw_re",
        "module_kw_re", "resource_re", "verb_re", "member_re",
        "collection_re", "block_open_re", "only_re", "except_re",
        "path_kw_re", "bare_re", "action_symbol_re", "skip_res",
        "rest_actions",
        "plural_actions", "singular_actions", "member_actions",
        "action_suffix", "match_methods", "id_seg", "nested_id_suffix",
    )

    def __init__(self, config: dict) -> None:
        sup = _supply_cfg(config)
        self.marker = str(sup.get("controller_dir_marker") or "")
        self.suffix = str(sup.get("controller_suffix") or "")
        scopes = sup.get("scope_patterns") or {}
        handlers = sup.get("handler_patterns") or {}

        def _rx(raw: Any) -> re.Pattern[str] | None:
            if not isinstance(raw, str) or not raw:
                return None
            try:
                return re.compile(raw)
            except re.error as exc:
                logger.warning("rails_routes.supply: bad regex %r: %s",
                               raw, exc)
                return None

        self.namespace_re = _rx(scopes.get("namespace"))
        self.scope_module_re = _rx(scopes.get("scope_module"))
        self.scope_path_re = _rx(scopes.get("scope_path"))
        self.to_re = _rx(handlers.get("to_kw"))
        self.fat_arrow_re = _rx(handlers.get("fat_arrow"))
        self.controller_kw_re = _rx(handlers.get("controller_kw"))
        self.module_kw_re = _rx(handlers.get("module_kw"))
        self.resource_re = _rx(sup.get("resource_pattern"))
        self.verb_re = _rx(sup.get("verb_pattern"))
        self.member_re = _rx(sup.get("member_block"))
        self.collection_re = _rx(sup.get("collection_block"))
        self.block_open_re = _rx(sup.get("block_open"))
        self.only_re = _rx(sup.get("only_pattern"))
        self.except_re = _rx(sup.get("except_pattern"))
        self.path_kw_re = _rx(sup.get("path_kw_pattern"))
        self.action_symbol_re = _rx(sup.get("action_symbol"))
        self.bare_re = _rx(sup.get("bare_target"))
        self.skip_res = tuple(
            r for r in (_rx(s) for s in (sup.get("skip_patterns") or []))
            if r is not None
        )
        raw_actions = sup.get("rest_actions") or {}
        self.rest_actions: dict[str, tuple[str, ...]] = {
            str(k): tuple(str(m).upper() for m in (v or []))
            for k, v in raw_actions.items()
        }
        self.plural_actions = tuple(
            str(a) for a in (sup.get("plural_actions") or ()))
        self.singular_actions = tuple(
            str(a) for a in (sup.get("singular_actions") or ()))
        self.member_actions = frozenset(
            str(a) for a in (sup.get("member_actions") or ()))
        self.action_suffix = {
            str(k): str(v) for k, v in (sup.get("action_suffix") or {}).items()
        }
        self.match_methods = tuple(
            str(m).upper() for m in (sup.get("match_methods") or ()))
        self.id_seg = str(sup.get("member_id_segment") or ":id")
        self.nested_id_suffix = str(sup.get("nested_id_suffix") or "_id")
        self.ok = bool(
            self.marker and self.suffix and self.resource_re
            and self.verb_re and self.rest_actions,
        )


class _Frame:
    """One open ``do … end`` block in ``config/routes.rb``."""

    __slots__ = ("indent", "modules", "path", "controller", "member_base",
                 "collection_base", "kind")

    def __init__(self, indent: int, modules: tuple[str, ...], path: str,
                 controller: str | None, member_base: str | None,
                 collection_base: str | None, kind: str) -> None:
        self.indent = indent
        self.modules = modules
        self.path = path
        self.controller = controller
        self.member_base = member_base
        self.collection_base = collection_base
        self.kind = kind


def build_controller_index(
    tracked_files: list[str] | tuple[str, ...], rules: _SupplyRules,
) -> dict[str, str]:
    """``"webhooks/stripe" → "app/controllers/webhooks/stripe_controller.rb"``.

    Keyed by the module chain BELOW the ``app/controllers/`` marker, so a
    Rails ENGINE root (``<engine>/app/controllers/<engine>/x_controller.rb``)
    is indexed under the chain it actually declares — never guessed onto a
    shorter chain (anti-case A3). Ties (the same chain under two roots)
    resolve first-by-sorted-path: deterministic, and the duplicate is a
    genuine Ruby autoload collision either way."""
    index: dict[str, str] = {}
    if not rules.ok:
        return index
    for raw in sorted(str(f) for f in (tracked_files or ())):
        p = posix(raw)
        if not p.endswith(rules.suffix) or rules.marker not in p:
            continue
        key = p.rsplit(rules.marker, 1)[1][: -len(rules.suffix)]
        if key:
            index.setdefault(key, p)
    return index


def _norm_url(*parts: str) -> str:
    segs: list[str] = []
    for part in parts:
        for seg in str(part or "").strip("/").split("/"):
            if seg:
                segs.append(seg)
    return "/" + "/".join(segs)


def _actions_from(raw: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z_]+", raw or ""))


def parse_route_supply(
    text: str, controller_index: dict[str, str], rules: _SupplyRules,
) -> tuple[list[tuple[str, str, str, int, str]], dict[str, int]]:
    """``config/routes.rb`` → ``[(pattern, METHOD, handler_file, line,
    "controller#action")]`` + telemetry.

    Pure: every controller reference is resolved against
    ``controller_index`` (tracked files), never against the filesystem,
    and an unresolved reference is DROPPED (A3) rather than guessed."""
    rows: list[tuple[str, str, str, int, str]] = []
    tele = {"decls": 0, "resolved": 0, "unresolved": 0, "skipped": 0}
    # ``rules.ok`` already implies both grammar patterns compiled; bind them
    # to locals so the narrowing is explicit to a reader and a type checker.
    resource_re, verb_re = rules.resource_re, rules.verb_re
    if not rules.ok or resource_re is None or verb_re is None or not text:
        return rows, tele

    stack: list[_Frame] = []

    def _resolve(modules: tuple[str, ...], stem: str) -> str | None:
        if not stem:
            return None
        chained = "/".join([m for m in modules if m] + [stem])
        hit = controller_index.get(chained)
        if hit is not None:
            return hit
        # A controller reference that already carries its own module
        # chain (``to: "admin/users#index"``) may sit at the root.
        if "/" in stem:
            return controller_index.get(stem)
        return None

    def _add(pattern: str, method: str, file_str: str, line_no: int,
             handler: str) -> None:
        rows.append((pattern, method.upper(), file_str, line_no, handler))

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        # Strip a trailing Ruby comment but keep ``"ctrl#action"`` strings.
        code = re.sub(r"\s+#\s.*$", "", raw_line)
        if not code.strip():
            continue
        indent = len(code) - len(code.lstrip())
        while stack and indent <= stack[-1].indent:
            stack.pop()
        top = stack[-1] if stack else None
        modules: tuple[str, ...] = top.modules if top else ()
        prefix: str = top.path if top else ""
        opens = bool(rules.block_open_re and rules.block_open_re.search(code))

        if any(rx.search(code) for rx in rules.skip_res):
            tele["skipped"] += 1
            if opens:
                stack.append(_Frame(indent, modules, prefix, None, None,
                                    None, "skip"))
            continue

        m = rules.namespace_re.match(code) if rules.namespace_re else None
        if m:
            seg = m.group(1)
            stack.append(_Frame(indent, (*modules, seg),
                                _norm_url(prefix, seg), None, None, None,
                                "ns"))
            continue
        m = rules.scope_module_re.match(code) if rules.scope_module_re else None
        if m:
            stack.append(_Frame(indent, (*modules, m.group(1)), prefix,
                                None, None, None, "scope"))
            continue
        if rules.member_re and rules.member_re.match(code):
            stack.append(_Frame(indent, modules,
                                (top.member_base if top else prefix) or prefix,
                                top.controller if top else None, None, None,
                                "member"))
            continue
        if rules.collection_re and rules.collection_re.match(code):
            stack.append(_Frame(
                indent, modules,
                (top.collection_base if top else prefix) or prefix,
                top.controller if top else None, None, None, "collection"))
            continue

        m = resource_re.match(code)
        if m:
            kind, name, rest = m.group(1), m.group(2), m.group(3) or ""
            tele["decls"] += 1
            plural = kind == "resources"
            ck = rules.controller_kw_re.search(rest) \
                if rules.controller_kw_re else None
            stem = ck.group(1) if ck else (name if plural else pluralize(name))
            mk = rules.module_kw_re.search(rest) if rules.module_kw_re else None
            local_mods = (*modules, mk.group(1)) if mk else modules
            handler_file = _resolve(local_mods, stem)
            if handler_file is None and not plural and not ck:
                # ``resource :mfa`` may live in a SINGULAR controller file.
                handler_file = _resolve(local_mods, name)
            pk = rules.path_kw_re.search(rest) if rules.path_kw_re else None
            url_seg = pk.group(1) if pk else name
            base = _norm_url(prefix, url_seg)
            member_base = _norm_url(base, rules.id_seg) if plural else base
            if handler_file is None:
                tele["unresolved"] += 1
            else:
                tele["resolved"] += 1
                actions = list(rules.plural_actions if plural
                               else rules.singular_actions)
                only = rules.only_re.search(rest) if rules.only_re else None
                exc = rules.except_re.search(rest) if rules.except_re else None
                if only:
                    keep = _actions_from(only.group(1))
                    actions = [a for a in actions if a in keep]
                elif exc:
                    drop = _actions_from(exc.group(1))
                    actions = [a for a in actions if a not in drop]
                for action in actions:
                    root = member_base if action in rules.member_actions \
                        else base
                    # fixb108-v2 Fix-1 (rules №23) — a RESTful FORM action
                    # ('new'/'edit') is a sub-view of its resource, never a
                    # capability of its own. Emitting '/api_key/new' made
                    # every such leaf collapse onto ONE cross-resource
                    # 'new' segment downstream, minting `route:new` as a PF
                    # ('Onboarding' read as 'trial', 'Sign up' as 'new').
                    # The action survives in the handler (`stem#action`);
                    # only the URL folds to the resource root.
                    pattern = root
                    for method in rules.rest_actions.get(action, ()):
                        _add(pattern, method, handler_file, line_no,
                             f"{stem}#{action}")
            if opens:
                # Rails names a nested parent's id after the SINGULAR
                # resource (`resources :accounts` → `:account_id`).
                nested = _norm_url(
                    base,
                    f":{singularize(name)}{rules.nested_id_suffix}",
                ) if plural else base
                stack.append(_Frame(indent, local_mods, nested, handler_file,
                                    member_base, base, "res"))
            continue

        m = verb_re.match(code)
        if m:
            verb, rest = m.group(1).upper(), m.group(2) or ""
            tele["decls"] += 1
            handler = (rules.to_re.search(rest) if rules.to_re else None) or (
                rules.fat_arrow_re.search(rest) if rules.fat_arrow_re else None)
            action = ""
            if handler:
                ctrl = handler.group(1)
                action = handler.group(2)
                handler_file = _resolve(
                    () if "/" in ctrl else modules, ctrl) or _resolve((), ctrl)
                stem = ctrl
            else:
                # ``get :verify`` inside a resource block → the enclosing
                # resource's controller.
                handler_file = next(
                    (f.controller for f in reversed(stack) if f.controller),
                    None)
                stem = ""
            if handler_file is None:
                tele["unresolved"] += 1
                continue
            tele["resolved"] += 1
            bare = rules.bare_re.match(rest.strip()) if rules.bare_re else None
            target = bare.group(1) if bare else ""
            # fixb108-v2 Fix-1 (rules №23) — an ACTION-SYMBOL verb line
            # (`get :trial` inside a member/collection block) names an
            # action of the enclosing resource, NOT a URL of its own. The
            # `bare_target` grammar swallows the leading ':' and so could
            # not tell `get :trial` (action) from `get 'news'` (path) —
            # that lost distinction is what minted `route:trial` as a PF.
            # Symbol form ⇒ fold to the resource's own URL; the action
            # stays in the handler tuple. A real `resources :news` never
            # reaches here (it parses in the resource branch), so a
            # token collision with an action name is harmless.
            act_sym = (rules.action_symbol_re.match(rest.strip())
                       if rules.action_symbol_re else None)
            if act_sym is not None and handler is None:
                action = act_sym.group(1)
                pattern = _norm_url(prefix)
            elif target:
                pattern = _norm_url(prefix, target)
            else:
                pattern = _norm_url(prefix)
            methods = rules.match_methods if verb == "MATCH" else (verb,)
            for method in methods:
                _add(pattern, method, handler_file, line_no,
                     f"{stem}#{action}" if stem or action else target)
            continue

        if opens:
            stack.append(_Frame(indent, modules, prefix,
                                top.controller if top else None, None, None,
                                "other"))
    return rows, tele


def _compile_patterns(cfg_patterns: dict) -> dict[str, re.Pattern[str]]:
    """Compile YAML-declared regex patterns. Bad patterns are dropped
    with a warning so a typo in YAML never kills the extractor."""
    out: dict[str, re.Pattern[str]] = {}
    if not isinstance(cfg_patterns, dict):
        return out
    for key, raw in cfg_patterns.items():
        if not isinstance(raw, str):
            continue
        try:
            out[key] = re.compile(raw)
        except re.error as exc:
            logger.warning(
                "rails_routes: bad regex for %s (%s): %s", key, raw, exc,
            )
    return out


class _Compiled:
    """Compiled patterns + scalar config for one rails-app.yaml dict."""

    __slots__ = ("route_file", "patterns", "confidence", "supply")

    def __init__(self, config: dict) -> None:
        routes_cfg = config.get("routes") or {}
        if not isinstance(routes_cfg, dict):
            routes_cfg = {}
            self.patterns: dict[str, re.Pattern[str]] = {}
        else:
            self.patterns = _compile_patterns(routes_cfg.get("patterns") or {})
        self.route_file = routes_cfg.get("file") or "config/routes.rb"
        self.confidence = float(routes_cfg.get("confidence") or 0.95)
        self.supply = _SupplyRules(config)


class RailsRoutesExtractor(RailsPatternExtractor):
    """Parse ``config/routes.rb`` → one anchor per declared resource/path."""

    name = "rails-routes"

    def compile_patterns(self, config: dict) -> _Compiled:
        return _Compiled(config)

    def collect(
        self, ctx: "ScanContext", compiled: _Compiled,
    ) -> dict[str, dict]:
        if not compiled.patterns:
            return {}

        full_path = ctx.repo_path / compiled.route_file
        text = read_text(full_path)
        if not text:
            return {}

        # Bucket: slug → {"keys": pattern keys that fired (rationale),
        #                 "routes": explicit route tuples (armed only)}.
        buckets: dict[str, dict] = defaultdict(
            lambda: {"keys": set(), "routes": set()},
        )

        for line in text.splitlines():
            # Skip Ruby comments.
            stripped = line.split("#", 1)[0]
            if not stripped.strip():
                continue
            for key, pattern in compiled.patterns.items():
                for m in pattern.finditer(stripped):
                    if not m.groups():
                        continue
                    raw = m.group(1)
                    if not raw:
                        continue
                    # For paths like "/admin/users" take the FIRST
                    # segment after the leading slash — that's the
                    # feature root.
                    head = raw.lstrip("/").split("/", 1)[0]
                    slug = slugify(head)
                    if not slug or is_noise(slug):
                        continue
                    buckets[slug]["keys"].add(key)

        # ── B108 supply pass (armed only) ────────────────────────────────
        # Read at COLLECT time (not compile time) so the cached compiled
        # bundle is shared across OFF/ON with no staleness — the go-router
        # precedent. OFF leaves every ``routes`` set empty ⇒ Pass A skips
        # ⇒ byte-identical board.
        if not buckets or not rails_routes_supply_enabled():
            return dict(buckets)
        index = build_controller_index(ctx.tracked_files, compiled.supply)
        if not index:
            return dict(buckets)
        rows, tele = parse_route_supply(text, index, compiled.supply)
        if not rows:
            return dict(buckets)
        logger.debug(
            "rails_routes supply: %d rows (%d/%d declarations resolved, "
            "%d skipped)", len(rows), tele["resolved"], tele["decls"],
            tele["skipped"],
        )
        # Carrier choice is a DELIVERY detail, not a semantic claim:
        # ``build_routes_index`` Pass A is owner-agnostic (it maps
        # row.file → feature through ``path_index``, never through the
        # candidate that carried the row). Rows land on the slug bucket
        # their URL head already produced; rows whose head was
        # noise-filtered ride the first bucket in sorted order so no row
        # is silently dropped.
        fallback = sorted(buckets)[0]
        for row in rows:
            head = str(row[0]).lstrip("/").split("/", 1)[0]
            slug = slugify(head)
            target = slug if (slug and slug in buckets) else fallback
            buckets[target]["routes"].add(row)
        return dict(buckets)

    def emit(
        self,
        ctx: "ScanContext",
        key: str,
        bucket: dict,
        compiled: _Compiled,
    ) -> AnchorCandidate:
        route_file = compiled.route_file
        return AnchorCandidate(
            name=key,
            paths=(posix(route_file),),
            source=self.name,
            confidence_self=compiled.confidence,
            rationale=(
                f"Rails route {key!r} declared in {route_file} "
                f"via {sorted(bucket['keys'])}"
            ),
            # Armed-only (empty set OFF): sorted for determinism.
            routes=tuple(sorted(bucket["routes"])),
        )


__all__ = [
    "RAILS_ROUTES_SUPPLY_ENV",
    "RailsRoutesExtractor",
    "build_controller_index",
    "is_rails_handler_path",
    "parse_route_supply",
    "rails_routes_supply_enabled",
]
