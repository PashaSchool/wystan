"""A second opinion before a product feature is removed for having no name.

The naming pass removes a product feature when no page can be tied to it or
no name of it passes the laws. Measured on nine repositories, 53 of 130
features removed that way are capabilities the product's own description
lists: they live in server code or behind another screen. No rule over the
map separates them from the UI parts and infrastructure removed beside them,
so the question goes to a model, once per feature.

Verdict per candidate:

  * ``capability``: the feature stays, with its developer features and its
    journeys, under a name that passes the laws (the one it has, else its
    slug written as words). With no lawful name it is removed as before.
  * ``part_of:<slug>``: it is a piece of another feature on the list; the
    existing join moves it there.
  * ``plumbing``: removed as before.

The verdict is remembered per candidate, keyed by the candidate's own
evidence: a second scan asks nothing, and a change in one feature does not
re-ask the others. Without a model (no key, a failed call, a reply that
breaks the task) every candidate is removed as before and the telemetry says
why.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable, Iterable

from wystan.cache.backend import CacheKind
from wystan.pipeline_v2.module_scope import ModuleScopes
from wystan.pipeline_v2.personas import _default_client_factory, _persona_batch
from wystan.pipeline_v2.request_scopes import (
    REPOSITORY_ROOT,
    feature_scopes,
    group_by_scope,
    scope_label,
    scope_lookup,
)
from wystan.pipeline_v2.stage_6_9_test_strip import is_test_path
from wystan.pipeline_v2.unnameable_demote import PLUMBING_NOTE

__all__ = [
    "EVIDENCE_MODEL_CAPABILITY",
    "MODEL_ID",
    "VERDICT_CAPABILITY",
    "VERDICT_PART_OF",
    "VERDICT_PLUMBING",
    "merge_counts",
    "run_demotion_veto",
]

ROLE = "demotion_veto"
# The larger tier, for this call and the capability split only: the small one
# called eight real capabilities plumbing on the measured set.
MODEL_ID = "claude-sonnet-5-5"
EVIDENCE_MODEL_CAPABILITY = "model:capability"
VERDICT_CAPABILITY = "capability"
VERDICT_PLUMBING = "plumbing"
VERDICT_PART_OF = "part_of"
_VERDICTS = frozenset({VERDICT_CAPABILITY, VERDICT_PLUMBING, VERDICT_PART_OF})
# Bump when the prompt or the meaning of a stored verdict changes.
_CACHE_VERSION = 1
_BATCH_SIZE = 60
MAX_JOURNEYS = 8
MAX_ROUTES = 6
MAX_KEPT_LISTED = 80
_UI_EXTENSIONS = frozenset({".tsx", ".jsx", ".vue", ".svelte", ".html", ".css", ".scss"})
_SERVER_EXTENSIONS = frozenset({
    ".py", ".go", ".rb", ".rs", ".java", ".kt", ".php", ".cs", ".ex", ".exs",
})
_OTHER_CODE_EXTENSIONS = frozenset({".ts", ".js", ".mjs", ".cjs"})

SYSTEM_PROMPT = """You review the feature list of a software product that was derived from its source code.

Some candidate features are about to be removed from the list because no page of the product could be tied to them. Some of them are real capabilities of the product that happen to live in server code or behind another screen; others are not features at all. Decide for each candidate which it is.

Give each candidate exactly one verdict:

- capability: something the product does that a user, an administrator or an integrating developer of this product would name when listing what the product offers (for example "Two-factor authentication", "Scheduled reports", "Data import", "Team invitations", "Browser extension"). It has behaviour of its own: things a person can create, configure, run or look at. It stays a capability even when all of its code is server code and even when it is reached from inside a settings screen.
- plumbing: not something a person would list. This covers parts of the UI kit or design system (button, dropdown, modal, spinner, colour tokens, layout or page shell), framework and infrastructure code (database layer, middleware, route guards, serializers, shared utilities, build tooling), test and mock tooling, and containers that only hold unrelated leftovers.
- part_of: a real piece of the product, but only one page, step, sub-resource or internal half of ANOTHER capability in the lists you are given (the kept features or another candidate). Name that capability's slug in `part_of`. Use this when a person would name the parent, not this piece (for example one payment provider's return handler is part of billing; a "default workspace" preference is part of settings).

How to read the evidence. The journeys are user flows the engine built from the candidate's code; junk candidates have junk journeys, so a journey that only repeats the candidate's name is no evidence, while several journeys that create, configure and browse the same named thing are. File kinds say where the code lives: only UI component files with no behaviour of their own suggests a UI part; server files with create/edit/browse journeys suggest a capability. Size alone decides nothing. Judge only from what is given; do not assume a capability exists because products of this kind usually have it.

Answer with one verdict per candidate, in the order given, using the candidate's slug exactly.

Output STRICT JSON only:
{"verdicts": [{"slug": "<slug>", "verdict": "capability" | "plumbing" | "part_of", "part_of": "<slug of the parent, else empty>", "reason": "<at most twelve words>"}]}"""


def _file_kinds(paths: Iterable[str]) -> dict[str, int]:
    kinds = {"server": 0, "ui": 0, "other_code": 0, "non_code": 0, "test": 0}
    for path in paths:
        suffix = ("." + path.rsplit(".", 1)[-1].lower()) if "." in path.rsplit("/", 1)[-1] else ""
        if is_test_path(path):
            kinds["test"] += 1
        elif suffix in _UI_EXTENSIONS:
            kinds["ui"] += 1
        elif suffix in _SERVER_EXTENSIONS:
            kinds["server"] += 1
        elif suffix in _OTHER_CODE_EXTENSIONS:
            kinds["other_code"] += 1
        else:
            kinds["non_code"] += 1
    return kinds


def _candidate_row(feature: Any, developers: list[Any], journeys: list[Any]) -> dict[str, Any]:
    """What the model is shown of one candidate: only its own evidence."""
    paths = list(dict.fromkeys([*(feature.paths or []), *(p for d in developers for p in d.paths or [])]))
    routes = sorted({str(r) for j in journeys for r in getattr(j, "routes", None) or []})
    return {
        "slug": feature.name,
        "display_name": feature.display_name or feature.name,
        "lines_of_code": sum(int(getattr(d, "loc", None) or 0) for d in developers),
        "flows": sum(len(getattr(d, "flows", None) or []) for d in developers),
        "journeys": sorted(str(j.name) for j in journeys)[:MAX_JOURNEYS],
        "routes": routes[:MAX_ROUTES],
        "file_kinds": _file_kinds(paths),
    }


def _cache_key(row: dict[str, Any], scope: str = REPOSITORY_ROOT) -> str:
    payload = {
        "v": _CACHE_VERSION, "role": ROLE, "model": MODEL_ID, "system": SYSTEM_PROMPT, "row": row,
    }
    if scope != REPOSITORY_ROOT:
        # A module's verdict was given beside the module's features only; it
        # is never read for a repository feature with the same evidence (nor
        # the reverse). A repository feature's key is the one it always had.
        payload["module_scope"] = scope
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _remembered(cache: Any, key: str) -> tuple[str, str] | None:
    if cache is None:
        return None
    try:
        stored = cache.get(CacheKind.LLM_PERSONA.value, key)
    except Exception:  # noqa: BLE001 - a cache fault degrades to a live call
        return None
    if not isinstance(stored, dict) or stored.get("v") != _CACHE_VERSION:
        return None
    if stored.get("verdict") not in _VERDICTS:
        return None
    return str(stored["verdict"]), str(stored.get("part_of") or "")


def _remember(cache: Any, key: str, verdict: tuple[str, str]) -> None:
    if cache is None:
        return
    try:
        cache.set(CacheKind.LLM_PERSONA.value, key, {
            "v": _CACHE_VERSION, "verdict": verdict[0], "part_of": verdict[1],
        })
    except Exception:  # noqa: BLE001 - a cache write fault never aborts a scan
        pass


def _user_prompt(kept: list[Any], rows: list[dict[str, Any]]) -> str:
    listed = [
        {"slug": f.name, "display_name": f.display_name or f.name}
        for f in sorted(kept, key=lambda f: f.name)[:MAX_KEPT_LISTED]
    ]
    return (
        "Kept features of this product (already on the list):\n"
        + json.dumps(listed, ensure_ascii=False)
        + "\n\nCandidates about to be removed (file_kinds counts the candidate's files: "
        "server, ui, other_code, non_code, test):\n"
        + "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    )


def _read_reply(reply: dict[str, Any] | None, asked: set[str]) -> dict[str, tuple[str, str]] | None:
    """Verdicts by slug, or ``None`` when the reply breaks the task: not the
    agreed shape, a slug that was not asked about, or a slug answered twice."""
    rows = (reply or {}).get("verdicts")
    if not isinstance(rows, list):
        return None
    verdicts: dict[str, tuple[str, str]] = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("verdict") not in _VERDICTS:
            return None
        slug = str(row.get("slug") or "")
        if slug not in asked or slug in verdicts:
            return None
        verdicts[slug] = (row["verdict"], str(row.get("part_of") or "").strip())
    return verdicts


def _ask(
    rows: dict[str, dict[str, Any]], kept: list[Any], llm: dict[str, Any], client: Any,
    telemetry: dict[str, Any],
) -> dict[str, tuple[str, str]]:
    """Verdicts for the candidates no verdict is remembered for."""
    verdicts: dict[str, tuple[str, str]] = {}
    slugs = sorted(rows)
    for start in range(0, len(slugs), _BATCH_SIZE):
        batch = slugs[start:start + _BATCH_SIZE]
        # The whole-request cache is not used: the answer is kept per candidate.
        reply, call = _persona_batch(
            role=ROLE, client=client, model=MODEL_ID, system=SYSTEM_PROMPT,
            user=_user_prompt(kept, [rows[slug] for slug in batch]),
            cost_tracker=llm.get("cost_tracker"), cache=None,
            llm_health=llm.get("llm_health"), candidates_for_log=batch,
        )
        telemetry["llm_calls"] += int(call.get("llm_calls", 0))
        telemetry["input_tokens"] += int(call.get("input_tokens", 0))
        telemetry["output_tokens"] += int(call.get("output_tokens", 0))
        read = _read_reply(reply, set(batch))
        if read is None:
            telemetry["invalid_replies"] += 1
            continue
        verdicts.update(read)
    return verdicts


def _ask_per_scope(
    rows: dict[str, dict[str, Any]], kept: list[Any], scope_of: Callable[[str], str],
    ask: Callable[[dict[str, dict[str, Any]], list[Any]], dict[str, tuple[str, str]]],
    telemetry: dict[str, Any],
) -> dict[str, tuple[str, str]]:
    """Verdicts asked per module scope (``request_scopes``, rule S1).

    The candidates of one scope are asked beside the kept features of the
    same scope only: a module feature asked beside the repository's was
    judged against them, and the repository's beside the module's. The
    root scope's requests are the ones composed when no module exists.
    With one scope this is one ``ask`` over everything, as before.
    """
    groups = group_by_scope(sorted(rows), scope_of)
    verdicts: dict[str, tuple[str, str]] = {}
    for scope, slugs in groups:
        kept_here = [f for f in kept if scope_of(f.name) == scope]
        verdicts.update(ask({slug: rows[slug] for slug in slugs}, kept_here))
    if len(groups) > 1:
        # Written only when a request was split, so a scan without a nested
        # module keeps its telemetry as it was.
        telemetry["asked_by_scope"] = {scope_label(scope): len(slugs) for scope, slugs in groups}
    return verdicts


def _lawful_name(feature: Any, taken: set[str], violations: Callable[[str], list[str]]) -> str | None:
    """The name a kept feature wears: the one it has when that passes the
    laws, else its slug written as words; ``None`` when neither does."""
    slug_words = " ".join(part.capitalize() for part in re.split(r"[-_\s]+", feature.name) if part)
    for name in (feature.display_name or "", slug_words):
        if name and not violations(name) and name.lower() not in taken:
            return name
    return None


def _apply(
    feature: Any, verdict: tuple[str, str], targets: set[str], taken: set[str],
    violations: Callable[[str], list[str]], joins_prefix: str, telemetry: dict[str, Any],
) -> None:
    kind, parent = verdict
    if kind == VERDICT_PLUMBING:
        telemetry["plumbing"].append(feature.name)
        feature.name_evidence = [*(feature.name_evidence or []), PLUMBING_NOTE]
    elif kind == VERDICT_PART_OF:
        if parent in targets and parent != feature.name:
            notes = [n for n in feature.name_evidence or [] if not str(n).startswith(joins_prefix)]
            feature.name_evidence = [*notes, joins_prefix + parent]
            telemetry["part_of"].append([feature.name, parent])
        else:
            telemetry["part_of_unknown_target"].append([feature.name, parent])
    else:
        name = _lawful_name(feature, taken, violations)
        if name is None:
            telemetry["no_lawful_name"].append(feature.name)
            return
        feature.display_name = name
        feature.name_evidence = [EVIDENCE_MODEL_CAPABILITY]
        feature.name_confidence = "medium"
        taken.add(name.lower())
        telemetry["kept"].append({"pf": feature.name, "name": name})


def run_demotion_veto(
    product_features: list[Any],
    developer_features: list[Any],
    user_flows: list[Any],
    *,
    is_candidate: Callable[[Any], bool],
    violations: Callable[[str], list[str]],
    joins_prefix: str,
    llm: dict[str, Any] | None = None,
    client_factory: Callable[[], Any | None] = _default_client_factory,
    module_scopes: ModuleScopes | None = None,
) -> dict[str, Any]:
    """Judge the features about to be removed, in place; returns telemetry.

    A ``capability`` loses its unnameable note and so is not removed; a
    ``part_of`` gains the join note the removal already honours.
    ``module_scopes`` is the scan's record of nested modules: the
    candidates of each module are asked in requests of their own."""
    llm = llm or {}
    telemetry: dict[str, Any] = {
        "applied": False, "reason": None, "model": MODEL_ID, "candidates": 0, "asked": 0,
        "not_asked_empty": [], "kept": [], "part_of": [], "part_of_unknown_target": [],
        "plumbing": [], "no_lawful_name": [], "unanswered": [],
        "cache_hits": 0, "llm_calls": 0, "invalid_replies": 0,
        "input_tokens": 0, "output_tokens": 0,
    }
    candidates = sorted((f for f in product_features if is_candidate(f)), key=lambda f: f.name)
    telemetry["candidates"] = len(candidates)
    if not candidates:
        telemetry["reason"] = "no_candidate"
        return telemetry
    rows = _rows(candidates, developer_features, user_flows, telemetry)
    cache = llm.get("cache")
    scope_of = scope_lookup(feature_scopes(product_features, developer_features, module_scopes))
    verdicts: dict[str, tuple[str, str]] = {}
    for slug, row in rows.items():
        known = _remembered(cache, _cache_key(row, scope_of(slug)))
        if known is not None:
            verdicts[slug] = known
            telemetry["cache_hits"] += 1
    unknown = {slug: row for slug, row in rows.items() if slug not in verdicts}
    if unknown:
        client = client_factory()
        if client is None:
            telemetry["reason"] = "no_key"
        else:
            kept = [f for f in product_features if not is_candidate(f)]
            telemetry["asked"] = len(unknown)
            fresh = _ask_per_scope(
                unknown, kept, scope_of,
                lambda batch, kept_here: _ask(batch, kept_here, llm, client, telemetry),
                telemetry,
            )
            for slug, verdict in fresh.items():
                _remember(cache, _cache_key(rows[slug], scope_of(slug)), verdict)
            verdicts.update(fresh)
    _apply_all(candidates, verdicts, product_features, is_candidate, violations, joins_prefix, telemetry)
    telemetry["unanswered"] = sorted(set(rows) - set(verdicts))
    telemetry["applied"] = bool(telemetry["kept"] or telemetry["part_of"])
    if not telemetry["applied"] and telemetry["reason"] is None:
        telemetry["reason"] = "invalid_reply" if telemetry["invalid_replies"] else "nothing_kept"
    return telemetry


def _rows(
    candidates: list[Any], developer_features: list[Any], user_flows: list[Any],
    telemetry: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Rows of the candidates worth asking about. A candidate with no code
    and no journey has nothing to be a capability of and is not asked about."""
    rows: dict[str, dict[str, Any]] = {}
    for feature in candidates:
        developers = [d for d in developer_features if d.product_feature_id == feature.name]
        journeys = [j for j in user_flows if j.product_feature_id == feature.name]
        has_code = bool(feature.paths) or any(d.paths for d in developers)
        if not has_code and not journeys:
            telemetry["not_asked_empty"].append(feature.name)
            continue
        rows[feature.name] = _candidate_row(feature, developers, journeys)
    return rows


def _apply_all(
    candidates: list[Any], verdicts: dict[str, tuple[str, str]], product_features: list[Any],
    is_candidate: Callable[[Any], bool], violations: Callable[[str], list[str]],
    joins_prefix: str, telemetry: dict[str, Any],
) -> None:
    """Capabilities first: a feature kept now is a valid parent for a
    ``part_of`` verdict on another candidate."""
    taken = {(f.display_name or f.name).lower() for f in product_features if not is_candidate(f)}
    ordered = sorted(candidates, key=lambda f: (verdicts.get(f.name, ("", ""))[0] != VERDICT_CAPABILITY, f.name))
    for feature in ordered:
        verdict = verdicts.get(feature.name)
        if verdict is None:
            continue
        targets = {f.name for f in product_features if not is_candidate(f)}
        _apply(feature, verdict, targets, taken, violations, joins_prefix, telemetry)


def merge_counts(first: dict[str, Any] | None, later: dict[str, Any] | None) -> dict[str, Any]:
    """Telemetry of two calls of one pass as one report: lists joined,
    numbers added, nested reports merged; of anything else the later value."""
    merged: dict[str, Any] = dict(first or {})
    for key, value in (later or {}).items():
        earlier = merged.get(key)
        if isinstance(value, bool) and isinstance(earlier, bool):
            merged[key] = earlier or value
        elif isinstance(value, list) and isinstance(earlier, list):
            merged[key] = [*earlier, *value]
        elif isinstance(value, (int, float)) and isinstance(earlier, (int, float)) and not isinstance(value, bool):
            merged[key] = earlier + value
        elif isinstance(value, dict) and isinstance(earlier, dict):
            merged[key] = merge_counts(earlier, value)
        elif value is not None or key not in merged:
            merged[key] = value
    if "reason" in merged and "applied" in merged:
        # Why nothing was done is a statement about all the calls: none when
        # one of them did something, else the first reason given.
        first_reason = (first or {}).get("reason")
        merged["reason"] = None if merged["applied"] else (first_reason or merged["reason"])
    return merged
