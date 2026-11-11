"""Name or reject: a product owner's reading of the features nobody named.

A product feature whose name the product does not state was named from a
URL segment, a directory or an identifier. A reader of five repositories
called 109 of 275 such names wrong, and most of the wrong ones are not
misnamed capabilities but things that are not capabilities at all: a single
page of another feature, UI chrome, an adapter. No law over a name tells
those apart, so the question goes to a model, per feature:

  * ``keep``: nothing changes.
  * ``rename``: a name of one to four words, every word taken from the
    feature's own evidence. The rule is checked here, not trusted.
  * ``not_a_capability``: the feature leaves the product layer, joining the
    feature it belongs to when one is named. Only a small feature can be
    rejected: a large one is left as it is and counted.

The model is asked twice and only an answer given both times is acted on.
The agreed answer (or the fact of disagreement) is remembered per feature by
the feature's own evidence, so a second scan asks nothing. Without a model
every name stays as it is.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable, Iterable

from wystan.cache.backend import CacheKind
from wystan.pipeline_v2.personas import _default_client_factory, _persona_batch
from wystan.pipeline_v2.unnameable_demote import demote_unnameable_features

__all__ = [
    "EVIDENCE_MODEL_NAME",
    "MAX_REJECT_JOURNEYS",
    "MAX_REJECT_LOC",
    "MODEL_ID",
    "is_supported_name",
    "run_feature_names",
]

ROLE = "feature_names"
MODEL_ID = "claude-sonnet-5-5"
EVIDENCE_MODEL_NAME = "model:name"
NOT_A_CAPABILITY_NOTE = "unnameable:not_a_capability"
DECISION_KEEP = "keep"
DECISION_RENAME = "rename"
DECISION_REJECT = "not_a_capability"
DECISION_DISAGREED = "disagreed"
_DECISIONS = frozenset({DECISION_KEEP, DECISION_RENAME, DECISION_REJECT})
# Two readings; an answer counts when both give it.
READINGS = 2
# A feature above either bound is never rejected by this pass. Measured on
# the prototype's 57 rejections: every one a reader disputed had at least 17
# journeys or 8,204 lines (107,450 at the top); every undisputed one had at
# most 9 journeys and 7,121 lines.
MAX_REJECT_JOURNEYS = 10
MAX_REJECT_LOC = 8_000
MAX_NAME_WORDS = 4
# The product states these itself, in its navigation or its command line:
# such a feature is a capability by the product's own word and is not asked
# about at all.
_STATED_BY_PRODUCT = frozenset({"authored:nav", "cli-declared"})
_AUTHORED_PREFIX = "authored:"
_CACHE_VERSION = 1
_BATCH_SIZE = 80
MAX_JOURNEYS = 10
MAX_ROUTES = 8
MAX_PATH_SEGMENTS = 3
_MIN_ABBREVIATION = 3
_MIN_ACRONYM = 2
_WORD = re.compile(r"[a-z0-9]+")
_JOINING_WORDS = frozenset({"and", "of", "for", "the", "to", "in"})

SYSTEM_PROMPT = """You are the product owner of a software product. An automatic scan of its source code produced a list of product features. Some features carry a name the product itself states (a navigation label or a page title); those are marked "authored" and are not yours to change. The others, the candidates, were named mechanically from a URL segment, a directory or an internal identifier, and many of those names are wrong: an acronym of a path ("Pat"), half of a route ("Sets"), a protocol step ("Callback"), a component ("Sidebarbundles"), a third-party library, or a label taken from an unrelated sub-page.

For each candidate decide exactly one of:

- keep: the current name is already what a product owner would call this capability in the navigation, the documentation or the pricing page.
- rename: the candidate is a real capability but the name is not the product's word for it. Give a name of 1 to 4 words. Every word of the new name MUST come from the candidate's own evidence: its journey names, their resources, its route segments, its anchor, its path segments, its slug or its current name. You may change singular to plural, and you may expand an acronym or abbreviation that appears in the evidence into the words it stands for ("pat" -> "Personal Access Tokens", "org" -> "Organizations"); you may split a glued identifier into its words. Nothing else: no synonyms, no words from your knowledge of this or similar products, no brand of the product itself as a prefix. If the evidence does not contain the words for a better name, answer keep. A candidate marked "authored": true may not be renamed.
- not_a_capability: the candidate is not something a product owner would list: a single page or a step of another feature (a sign-up confirmation, an OAuth callback), UI chrome or a design-system component, a documentation or marketing page, an adapter for a third-party library or service, an internal developer tool, or a leftover container. If it belongs to a feature in the list, give that feature's slug in `belongs_to`; otherwise leave `belongs_to` empty.

Rules:
1. Names stay distinct: a new name must not equal the name of any other feature in the list, authored or not.
2. Match the style of the authored names of this product (title case, plural for collections, no "Management" or "System" suffix unless the product uses it).
3. A name is a noun phrase for a capability. Not a verb, not a file, not a layer ("API", "Backend"), not a route.
4. Judge only from what is given. Journeys were built by the same scan and can be wrong; a journey that only repeats the candidate's name is weak evidence.
5. Answer every candidate exactly once, in the order given, using its slug exactly. `name` is empty unless the decision is rename. `reason` is at most twelve words.

Output STRICT JSON only:
{"answers": [{"slug": "<slug>", "decision": "keep" | "rename" | "not_a_capability", "name": "<new name or empty>", "belongs_to": "<slug or empty>", "reason": "<short>"}]}"""


def _evidence(feature: Any) -> set[str]:
    return {str(note) for note in getattr(feature, "name_evidence", None) or ()}


def _is_candidate(feature: Any) -> bool:
    return not (_evidence(feature) & _STATED_BY_PRODUCT)


def _reject_only(feature: Any) -> bool:
    """A name the product wrote on a page (a title, a heading, a
    description) is not ours to change; whether the page is a capability
    still is a question."""
    return any(note.startswith(_AUTHORED_PREFIX) for note in _evidence(feature))


def _row(feature: Any, developers: list[Any], journeys: list[Any]) -> dict[str, Any]:
    paths = list(dict.fromkeys([*(feature.paths or []), *(p for d in developers for p in d.paths or [])]))
    segments = sorted({"/".join(p.split("/")[:3]) for p in paths if "/" in p})
    return {
        "slug": feature.name,
        "name": feature.display_name or feature.name,
        "authored": _reject_only(feature),
        "anchor": str(getattr(feature, "anchor_id", "") or ""),
        "lines": sum(int(getattr(d, "loc", None) or 0) for d in developers),
        "files": len(paths),
        "journey_count": len(journeys),
        "journeys": [
            {"name": str(j.name), "resource": str(getattr(j, "resource", "") or "")}
            for j in sorted(journeys, key=lambda j: str(j.name))[:MAX_JOURNEYS]
        ],
        "routes": sorted({str(r) for j in journeys for r in getattr(j, "routes", None) or []})[:MAX_ROUTES],
        "path_segments": segments[:MAX_PATH_SEGMENTS],
    }


def _evidence_words(row: dict[str, Any]) -> set[str]:
    texts = [row["slug"], row["name"], row["anchor"], *row["routes"], *row["path_segments"]]
    for journey in row["journeys"]:
        texts += [journey["name"], journey["resource"]]
    words: set[str] = set()
    for text in texts:
        # Glued identifiers are split at case changes before lower-casing.
        spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(text))
        words.update(_WORD.findall(spaced.lower()))
    return words


def _same_word(word: str, known: set[str]) -> bool:
    """In the evidence as it is, in another number, or as the abbreviation
    it expands ("org" -> "organizations")."""
    forms = {word, word + "s", word + "es", word.rstrip("s"), re.sub(r"ies$", "y", word), re.sub(r"y$", "ies", word)}
    if forms & known:
        return True
    # An abbreviation is much shorter than what it stands for ("auth" ->
    # "authentication"); "edit" -> "editor" is another word, not an expansion.
    return any(
        len(token) >= _MIN_ABBREVIATION and word.startswith(token) and len(word) >= 2 * len(token)
        for token in known
    )


def is_supported_name(name: str, row: dict[str, Any]) -> bool:
    """True when every word of ``name`` comes from the feature's own
    evidence: present there, a singular or plural of a word there, the
    expansion of an abbreviation there, or one of consecutive words whose
    initials spell an acronym there ("pat" -> "Personal Access Tokens").
    Synonyms and words from knowledge of the product fail: on the measured
    set the rule refused "Two-Factor Authentication" for a feature whose
    evidence says only "totp", and admitted no invented name."""
    words = _WORD.findall(name.lower())
    if not 1 <= len(words) <= MAX_NAME_WORDS:
        return False
    known = _evidence_words(row)
    covered = [word in _JOINING_WORDS or _same_word(word, known) for word in words]
    for start in range(len(words)):
        for end in range(start + _MIN_ACRONYM, len(words) + 1):
            if "".join(w[0] for w in words[start:end]) in known:
                covered[start:end] = [True] * (end - start)
    return all(covered)


def _cache_key(row: dict[str, Any]) -> str:
    payload = {"v": _CACHE_VERSION, "role": ROLE, "model": MODEL_ID, "system": SYSTEM_PROMPT, "row": row}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _remembered(cache: Any, key: str) -> dict[str, str] | None:
    if cache is None:
        return None
    try:
        stored = cache.get(CacheKind.LLM_PERSONA.value, key)
    except Exception:  # noqa: BLE001 - a cache fault degrades to a live call
        return None
    if not isinstance(stored, dict) or stored.get("v") != _CACHE_VERSION:
        return None
    answer = stored.get("answer")
    return answer if isinstance(answer, dict) and answer.get("decision") else None


def _remember(cache: Any, key: str, answer: dict[str, str]) -> None:
    if cache is None:
        return
    try:
        cache.set(CacheKind.LLM_PERSONA.value, key, {"v": _CACHE_VERSION, "answer": answer})
    except Exception:  # noqa: BLE001 - a cache write fault never aborts a scan
        pass


def _user_prompt(product: str, product_features: list[Any], rows: list[dict[str, Any]]) -> str:
    listed = "\n".join(
        f"{f.display_name or f.name} [{f.name}]" + ("" if _is_candidate(f) and not _reject_only(f) else " (authored)")
        for f in sorted(product_features, key=lambda f: f.name)
    )
    return (
        f"Product: {product}\n\nAll product features of this product, as `name [slug]`:\n{listed}\n\n"
        "Candidates:\n" + "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
        + "\n\nAnswer every candidate exactly once."
    )


def _read(reply: dict[str, Any] | None, asked: set[str]) -> dict[str, dict[str, str]] | None:
    """Answers by slug; ``None`` when the reply breaks the task."""
    rows = (reply or {}).get("answers")
    if not isinstance(rows, list):
        return None
    answers: dict[str, dict[str, str]] = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("decision") not in _DECISIONS:
            return None
        slug = str(row.get("slug") or "")
        if slug not in asked or slug in answers:
            return None
        answers[slug] = {
            "decision": row["decision"],
            "name": str(row.get("name") or "").strip(),
            "belongs_to": str(row.get("belongs_to") or "").strip(),
        }
    return answers


def _agreed(first: dict[str, str] | None, second: dict[str, str] | None) -> dict[str, str] | None:
    """The answer both readings gave; ``None`` when one is missing."""
    if first is None or second is None:
        return None
    same = (
        first["decision"] == second["decision"]
        and first["name"].lower() == second["name"].lower()
        and first["belongs_to"] == second["belongs_to"]
    )
    return dict(first) if same else {"decision": DECISION_DISAGREED, "name": "", "belongs_to": ""}


def _ask(
    rows: dict[str, dict[str, Any]], product: str, product_features: list[Any],
    llm: dict[str, Any], client: Any, telemetry: dict[str, Any],
) -> dict[str, dict[str, str]]:
    """Agreed answers for the candidates no answer is remembered for."""
    answers: dict[str, dict[str, str]] = {}
    slugs = sorted(rows)
    for start in range(0, len(slugs), _BATCH_SIZE):
        batch = slugs[start:start + _BATCH_SIZE]
        user = _user_prompt(product, product_features, [rows[slug] for slug in batch])
        readings: list[dict[str, dict[str, str]] | None] = []
        for _ in range(READINGS):
            reply, call = _persona_batch(
                role=ROLE, client=client, model=MODEL_ID, system=SYSTEM_PROMPT, user=user,
                cost_tracker=llm.get("cost_tracker"), cache=None,
                llm_health=llm.get("llm_health"), candidates_for_log=batch,
            )
            for name in ("llm_calls", "input_tokens", "output_tokens"):
                telemetry[name] += int(call.get(name, 0))
            readings.append(_read(reply, set(batch)))
        if any(reading is None for reading in readings):
            telemetry["invalid_replies"] += 1
            continue
        for slug in batch:
            agreed = _agreed(readings[0].get(slug), readings[1].get(slug))
            if agreed is not None:
                answers[slug] = agreed
    return answers


class _Applier:
    """Turns agreed answers into changes, each behind its guard."""

    def __init__(
        self, product_features: list[Any], rows: dict[str, dict[str, Any]],
        violations: Callable[[str], list[str]], joins_prefix: str, telemetry: dict[str, Any],
    ) -> None:
        self._features = {f.name: f for f in product_features}
        self._rows = rows
        self._violations = violations
        self._joins_prefix = joins_prefix
        self._tele = telemetry

    def apply(self, answers: dict[str, dict[str, str]]) -> None:
        leaving = {slug for slug, a in answers.items() if a["decision"] == DECISION_REJECT and self._small(slug)}
        for slug in sorted(answers):
            answer, feature = answers[slug], self._features[slug]
            if answer["decision"] == DECISION_KEEP:
                self._tele["kept"] += 1
            elif answer["decision"] == DECISION_DISAGREED:
                self._tele["disagreed"].append(slug)
            elif answer["decision"] == DECISION_RENAME:
                self._rename(feature, answer["name"])
            else:
                self._reject(feature, answer["belongs_to"], leaving)

    def _small(self, slug: str) -> bool:
        row = self._rows[slug]
        return row["lines"] <= MAX_REJECT_LOC and row["journey_count"] <= MAX_REJECT_JOURNEYS

    def _rename(self, feature: Any, name: str) -> None:
        reason = self._rename_refusal(feature, name)
        if reason is not None:
            self._tele["invalid_renames"].append({"pf": feature.name, "name": name, "reason": reason})
            return
        self._tele["renamed"].append({"pf": feature.name, "old": feature.display_name, "new": name})
        feature.display_name = name
        feature.name_evidence = [EVIDENCE_MODEL_NAME]
        feature.name_confidence = "medium"

    def _rename_refusal(self, feature: Any, name: str) -> str | None:
        if _reject_only(feature):
            return "authored_name"
        if not name or name.lower() == (feature.display_name or "").lower():
            return "same_as_current"
        if not is_supported_name(name, self._rows[feature.name]):
            return "words_not_in_evidence"
        broken = self._violations(name)
        if broken:
            return "unlawful:" + broken[0]
        taken = {(f.display_name or f.name).lower() for f in self._features.values() if f is not feature}
        return "name_taken" if name.lower() in taken else None

    def _reject(self, feature: Any, parent: str, leaving: set[str]) -> None:
        if not self._small(feature.name):
            row = self._rows[feature.name]
            self._tele["too_large_to_reject"].append({
                "pf": feature.name, "lines": row["lines"], "journeys": row["journey_count"]})
            return
        notes = [NOT_A_CAPABILITY_NOTE]
        if parent:
            if parent not in self._features or parent in leaving or parent == feature.name:
                self._tele["unknown_parent"].append([feature.name, parent])
                return
            notes.append(self._joins_prefix + parent)
        feature.name_evidence = notes
        feature.name_confidence = "low"
        self._tele["not_a_capability"].append({"pf": feature.name, "belongs_to": parent or None})


def _census(product_features: list[Any], developers: list[Any], user_flows: list[Any], flows: list[Any]) -> dict[str, int]:
    alive = {f.name for f in product_features}
    owned = sum(int(getattr(d, "loc", None) or 0) for d in developers if d.product_feature_id in alive)
    return {
        "journeys": len(user_flows), "flows": len(flows),
        "developer_lines": sum(int(getattr(d, "loc", None) or 0) for d in developers),
        "owned_lines": owned,
    }


def run_feature_names(
    product_features: list[Any],
    developer_features: list[Any],
    user_flows: list[Any],
    flows: list[Any],
    *,
    product: str,
    violations: Callable[[str], list[str]],
    joins_prefix: str,
    llm: dict[str, Any] | None = None,
    client_factory: Callable[[], Any | None] = _default_client_factory,
) -> dict[str, Any]:
    """Rename or reject non-authored product features in place; telemetry."""
    llm = llm or {}
    telemetry: dict[str, Any] = {
        "applied": False, "reason": None, "model": MODEL_ID, "candidates": 0, "asked": 0,
        "kept": 0, "renamed": [], "not_a_capability": [], "too_large_to_reject": [],
        "disagreed": [], "invalid_renames": [], "unknown_parent": [], "unanswered": [],
        "cache_hits": 0, "llm_calls": 0, "invalid_replies": 0, "input_tokens": 0, "output_tokens": 0,
    }
    rows = _rows(product_features, developer_features, user_flows)
    telemetry["candidates"] = len(rows)
    if not rows:
        telemetry["reason"] = "no_candidate"
        return telemetry
    cache = llm.get("cache")
    answers = {slug: known for slug, row in rows.items() if (known := _remembered(cache, _cache_key(row)))}
    telemetry["cache_hits"] = len(answers)
    unknown = {slug: row for slug, row in rows.items() if slug not in answers}
    if unknown:
        client = client_factory()
        if client is None:
            telemetry["reason"] = "no_key"
        else:
            telemetry["asked"] = len(unknown)
            fresh = _ask(unknown, product, product_features, llm, client, telemetry)
            for slug, answer in fresh.items():
                _remember(cache, _cache_key(rows[slug]), answer)
            answers.update(fresh)
    before = _census(product_features, developer_features, user_flows, flows)
    _Applier(product_features, rows, violations, joins_prefix, telemetry).apply(answers)
    if telemetry["not_a_capability"]:
        telemetry["removal"] = demote_unnameable_features(
            product_features, developer_features, user_flows, flows)
    after = _census(product_features, developer_features, user_flows, flows)
    telemetry["conservation"] = {
        "journeys_before": before["journeys"], "journeys_after": after["journeys"],
        "flows_before": before["flows"], "flows_after": after["flows"],
        "lines_before": before["developer_lines"], "lines_after": after["developer_lines"],
        "conserved": all(before[k] == after[k] for k in ("journeys", "flows", "developer_lines")),
    }
    telemetry["unanswered"] = sorted(set(rows) - set(answers))
    telemetry["applied"] = bool(telemetry["renamed"] or telemetry["not_a_capability"])
    if not telemetry["applied"] and telemetry["reason"] is None:
        telemetry["reason"] = "invalid_reply" if telemetry["invalid_replies"] else "nothing_changed"
    return telemetry


def _rows(product_features: list[Any], developer_features: list[Any], user_flows: list[Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for feature in sorted(product_features, key=lambda f: f.name):
        if not _is_candidate(feature):
            continue
        developers = [d for d in developer_features if d.product_feature_id == feature.name]
        journeys = [j for j in user_flows if j.product_feature_id == feature.name]
        rows[feature.name] = _row(feature, developers, journeys)
    return rows
