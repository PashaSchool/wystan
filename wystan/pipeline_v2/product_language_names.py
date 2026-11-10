"""Product-language names for product features and user flows.

Runs after the naming contract, on the final product layer. Developer
features and code flows keep their code-derived names; this pass rewrites
only ``Feature.display_name`` of product features and ``UserFlow.name``.

Ladder, per item:

  1. Keyed scan: the writer proposes a name from the item's user-visible
     text. It is accepted when it passes the product-language laws, every
     content word is supported by the item's evidence, and no sibling
     already has it. One retry with the broken rule stated.
  2. Otherwise the current name stays when it passes the laws.
  3. Otherwise the best user-visible label of the item that passes the laws
     and shares a word with the item's identity.
  4. Otherwise the name stays, ``name_confidence`` becomes ``"low"`` and
     ``name_evidence`` records ``unnameable:<law>``.

Identity (slugs, ids, anchors, membership) is never touched.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from wystan.pipeline_v2.naming_contract import _verb_class_tokens, load_naming_vocab
from wystan.pipeline_v2.naming_validator import EvidenceBundle, tokenize_name, validate_name
from wystan.pipeline_v2.product_name_laws import (
    KIND_FEATURE,
    KIND_FLOW,
    LawContext,
    product_name_violations,
)
from wystan.pipeline_v2.product_strings import _read_text
from wystan.pipeline_v2.product_name_writer import NameWriter, build_name_writer
from wystan.pipeline_v2.spine_anchors import load_spine_vocab
from wystan.pipeline_v2.ui_text import UiLabel, UiTextIndex, collect_ui_text

__all__ = [
    "EVIDENCE_UI_TEXT",
    "UNNAMEABLE_PREFIX",
    "NameTarget",
    "name_product_layer",
    "run_product_language_names",
]

EVIDENCE_UI_TEXT = "ui-text"
EVIDENCE_UI_LABEL = "ui-label"
UNNAMEABLE_PREFIX = "unnameable:"

_MAX_PROMPT_LABELS = 30
_MAX_PROMPT_ROUTES = 8
_MAX_PROMPT_MEMBERS = 12
_TITLE_SEPARATOR = re.compile(r"\s+[-|·–—]\s+")
_FEATURE_LABEL_KINDS = ("title", "heading")
_MIN_STEM = 4


@dataclass
class NameTarget:
    """One product feature or user flow to name."""

    key: str
    kind: str
    current: str
    group: str
    """Siblings share a group; names are unique inside it."""
    labels: list[UiLabel]
    identity_words: frozenset[str]
    """Words of the item's slug (feature) or resource (flow)."""
    routes: list[str] = field(default_factory=list)
    members: list[str] = field(default_factory=list)
    """Names of the code units inside the item."""
    apply: Callable[[str, str, list[str]], None] = lambda name, confidence, evidence: None

    def prompt_row(self, parent: str | None, note: str | None = None) -> dict[str, Any]:
        row: dict[str, Any] = {
            "id": self.key,
            "kind": self.kind,
            "current": self.current,
            "ui_text": [f"{label.kind}: {label.text}" for label in self.labels[:_MAX_PROMPT_LABELS]],
            "urls": self.routes[:_MAX_PROMPT_ROUTES],
            "code_units": self.members[:_MAX_PROMPT_MEMBERS],
        }
        if parent:
            row["feature"] = parent
        if note:
            row["rejected"] = note
        return row

    def own_words(self) -> frozenset[str]:
        """Words that identify this item in the code: its slug or resource,
        its current name, its URLs and its code units."""
        return _words(" ".join([self.current, *self.identity_words, *self.routes, *self.members]))

    def bundle(self, goal_verbs: Iterable[str]) -> EvidenceBundle:
        bundle = EvidenceBundle()
        bundle.add_global(self.current, *self.routes, *self.members)
        bundle.add_global(*(label.text for label in self.labels))
        if self.kind == KIND_FLOW:
            bundle.add_global(*goal_verbs)
        return bundle


def _words(text: str) -> frozenset[str]:
    return frozenset(tokenize_name(text))


def _shares_stem(left: Iterable[str], right: Iterable[str]) -> bool:
    right_words = list(right)
    for a in left:
        for b in right_words:
            if a == b or (min(len(a), len(b)) >= _MIN_STEM and (a.startswith(b) or b.startswith(a))):
                return True
    return False


def _same_words(words: Iterable[str], identity: frozenset[str]) -> bool:
    """True when ``words`` and ``identity`` name the same thing: each side's
    words are covered by the other's, or they are one word written apart
    ("sign in" and ``signin``)."""
    listed = list(words)
    if not listed or not identity:
        return False
    if "".join(listed) == "".join(sorted(identity, key="".join(listed).find)):
        return True
    return all(_shares_stem([w], identity) for w in listed) and all(
        _shares_stem([w], listed) for w in identity
    )


def build_law_context(index: UiTextIndex, brand_words: Iterable[str]) -> LawContext:
    """Laws context for one repository: its own UI words and action verbs."""
    vocab = load_naming_vocab()
    action_leads = {
        label.text.split()[0].lower()
        for labels in index.by_file.values() for label in labels
        if label.kind == "action" and label.text.split()[0].isalpha()
    }
    structural = set(load_spine_vocab().get("structural_stoplist") or [])
    structural.update(vocab.get("structural_segments") or [])
    return LawContext(
        ui_vocabulary=index.vocabulary(),
        goal_verbs=frozenset(_verb_class_tokens(vocab) | action_leads),
        vocabulary_verbs=frozenset(_verb_class_tokens(vocab)),
        brand_words=frozenset(word.lower() for word in brand_words),
        structural_words=frozenset(str(word).lower() for word in structural),
        vocab=vocab,
    )


class _Namer:
    """Applies the ladder to a list of targets."""

    def __init__(self, ctx: LawContext, writer: NameWriter | None) -> None:
        self._ctx = ctx
        self._writer = writer
        self._taken: dict[str, set[str]] = {}
        self.telemetry = {
            "total": 0, "written": 0, "kept": 0, "from_label": 0,
            "unnameable": 0, "declined_by_writer": 0, "rejected_proposals": 0,
            "unnameable_by_law": {},
        }

    def _violations(self, target: NameTarget, name: str) -> list[str]:
        shown = any(
            label.text.lower() == name.lower() and label.kind in _FEATURE_LABEL_KINDS
            for label in target.labels
        )
        subject = target.identity_words if target.kind == KIND_FLOW else frozenset()
        return product_name_violations(
            name, target.kind, self._ctx, is_shown=shown, subject=subject,
        )

    def _verb_noise(self, target: NameTarget) -> frozenset[str]:
        """Verbs that say nothing about what an item is. A verb that is also
        the item's own word ("webhook", "template") is not noise."""
        if target.kind != KIND_FLOW:
            return frozenset()
        return self._ctx.goal_verbs - target.identity_words

    def _subject(self, target: NameTarget, name: str) -> list[str]:
        """Content words of ``name`` that say what it is about."""
        noise = self._verb_noise(target)
        return [word for word in tokenize_name(name) if word not in noise]

    def _rejection(self, target: NameTarget, name: str) -> str | None:
        """Why ``name`` cannot be used for ``target``; ``None`` when it can."""
        broken = self._violations(target, name)
        if broken:
            return "breaks: " + ", ".join(broken)
        if not _shares_stem(self._subject(target, name), target.own_words() - self._verb_noise(target)):
            return "is about something else than this item's urls and code units"
        check = validate_name(name, target.bundle(self._ctx.goal_verbs))
        if not check.ok:
            return "words not in the evidence: " + ", ".join(check.all_violations)
        if name.lower() in self._taken.get(target.group, set()):
            return "a sibling already has this name"
        return None

    def _take(self, target: NameTarget, name: str) -> None:
        self._taken.setdefault(target.group, set()).add(name.lower())

    def _label_candidate(self, target: NameTarget) -> str | None:
        """The item's own name as the product writes it, or ``None``.

        A label qualifies only when it says the same thing as the item's
        identity words, so a neighbouring screen's text is never borrowed. A
        feature takes a title or heading ("Sign In" for ``signin``). A flow
        takes a button label made of one verb plus its resource, and only when
        every such button uses the same verb."""
        is_flow = target.kind == KIND_FLOW
        kinds = ("action",) if is_flow else _FEATURE_LABEL_KINDS
        matches: dict[str, str] = {}
        for label in target.labels:
            if label.kind not in kinds:
                continue
            for part in _TITLE_SEPARATOR.split(label.text):
                text = part.strip()
                subject = self._subject(target, text)
                if _same_words(subject, target.identity_words) and self._rejection(target, text) is None:
                    matches.setdefault(text.split()[0].lower() if is_flow else "", text)
        return next(iter(matches.values())) if len(matches) == 1 else None

    def _propose(self, targets: list[NameTarget], parents: dict[str, str]) -> dict[str, str]:
        """Accepted writer proposals by target key, after one retry."""
        accepted: dict[str, str] = {}
        if self._writer is None:
            return accepted
        notes: dict[str, str | None] = {target.key: None for target in targets}
        pending = list(targets)
        for attempt in range(2):
            rows = [t.prompt_row(parents.get(t.group), notes[t.key]) for t in pending]
            proposed = self._writer(rows) if rows else {}
            retry: list[NameTarget] = []
            for target in pending:
                name = proposed.get(target.key)
                if not name:
                    if attempt == 0:
                        self.telemetry["declined_by_writer"] += 1
                    continue
                reason = self._rejection(target, name)
                if reason is None:
                    accepted[target.key] = name
                    self._take(target, name)
                    continue
                self.telemetry["rejected_proposals"] += 1
                notes[target.key] = f'"{name}" {reason}'
                retry.append(target)
            pending = retry
        return accepted

    def _settle(self, target: NameTarget) -> None:
        """Rungs 2 to 4 for a target the writer did not name."""
        broken = self._violations(target, target.current)
        if not broken:
            self.telemetry["kept"] += 1
            self._take(target, target.current)
            return
        label = self._label_candidate(target)
        if label is not None:
            self.telemetry["from_label"] += 1
            self._take(target, label)
            target.apply(label, "medium", [EVIDENCE_UI_LABEL])
            return
        self.telemetry["unnameable"] += 1
        by_law = self.telemetry["unnameable_by_law"]
        by_law[broken[0]] = by_law.get(broken[0], 0) + 1
        target.apply(target.current, "low", [UNNAMEABLE_PREFIX + law for law in broken])

    def run(self, targets: list[NameTarget], parents: dict[str, str]) -> None:
        ordered = sorted(targets, key=lambda target: target.key)
        self.telemetry["total"] += len(ordered)
        accepted = self._propose(ordered, parents)
        for target in ordered:
            name = accepted.get(target.key)
            if name is None:
                self._settle(target)
            elif name != target.current:
                self.telemetry["written"] += 1
                target.apply(name, "high", [EVIDENCE_UI_TEXT])
            else:
                self.telemetry["kept"] += 1


def _feature_target(feature: Any, index: UiTextIndex, routes_by_file: dict[str, str]) -> NameTarget:
    paths = list(feature.paths or [])

    def apply(name: str, confidence: str, evidence: list[str]) -> None:
        feature.display_name = name
        feature.name_confidence = confidence
        feature.name_evidence = evidence

    return NameTarget(
        key=f"pf:{feature.name}", kind=KIND_FEATURE,
        current=feature.display_name or feature.name, group="pf",
        labels=index.labels_for(paths),
        identity_words=_words(feature.name),
        routes=sorted({routes_by_file[path] for path in paths if path in routes_by_file}),
        apply=apply,
    )


def _flow_target(
    user_flow: Any, members: list[Any], index: UiTextIndex, shared_paths: frozenset[str],
) -> NameTarget:
    """A flow is named from the screens it starts on and the files only it
    uses. Files it shares with other flows show other flows' text."""
    paths: set[str] = set()
    for flow in members:
        paths.update(path for path in (flow.paths or []) if path not in shared_paths)
        if flow.entry_point_file:
            paths.add(flow.entry_point_file)

    def apply(name: str, confidence: str, evidence: list[str]) -> None:
        user_flow.name = name
        user_flow.name_confidence = confidence
        user_flow.name_evidence = evidence

    return NameTarget(
        key=f"uf:{user_flow.id}", kind=KIND_FLOW, current=user_flow.name,
        group=f"uf:{user_flow.product_feature_id}",
        labels=index.labels_for(paths),
        identity_words=_words(user_flow.resource),
        routes=[route for route in (user_flow.routes or []) if route.startswith("/")],
        members=sorted(flow.name for flow in members),
        apply=apply,
    )


def _paths_shared_between_user_flows(flows_of: dict[str, list[Any]]) -> frozenset[str]:
    owners: dict[str, set[str]] = {}
    for user_flow_id, members in flows_of.items():
        for flow in members:
            for path in flow.paths or []:
                owners.setdefault(path, set()).add(user_flow_id)
    return frozenset(path for path, ids in owners.items() if len(ids) > 1)


def run_product_language_names(
    product_features: list[Any],
    user_flows: list[Any],
    flows: list[Any],
    *,
    index: UiTextIndex,
    routes_index: list[dict[str, Any]],
    developer_features: list[Any] = (),
    brand_words: Iterable[str] = (),
    writer: NameWriter | None = None,
) -> dict[str, Any]:
    """Rename product features and user flows in place; returns telemetry."""
    ctx = build_law_context(index, brand_words)
    routes_by_file = {
        str(row.get("file")): str(row.get("pattern"))
        for row in routes_index if row.get("file") and row.get("pattern")
    }
    feature_targets = [_feature_target(f, index, routes_by_file) for f in product_features]
    members_of: dict[str, list[str]] = {}
    for dev in developer_features:
        if dev.product_feature_id:
            members_of.setdefault(dev.product_feature_id, []).append(dev.name)
    for target, feature in zip(feature_targets, product_features):
        target.members = sorted(members_of.get(feature.name, []))

    feature_namer = _Namer(ctx, writer)
    feature_namer.run(feature_targets, {})

    flows_of: dict[str, list[Any]] = {}
    for flow in flows:
        if flow.user_flow_id:
            flows_of.setdefault(flow.user_flow_id, []).append(flow)
    parents = {
        f"uf:{feature.name}": feature.display_name or feature.name
        for feature in product_features
    }
    flow_namer = _Namer(ctx, writer)
    shared = _paths_shared_between_user_flows(flows_of)
    flow_namer.run(
        [_flow_target(uf, flows_of.get(uf.id, []), index, shared) for uf in user_flows],
        parents,
    )
    return {
        "keyed": writer is not None,
        "ui_text_files": len(index.by_file),
        "product_features": feature_namer.telemetry,
        "user_flows": flow_namer.telemetry,
    }


def _brand_words(repo_path: Any) -> list[str]:
    """The product's own name: the repository directory and the root
    package's name and scope."""
    words = set(tokenize_name(repo_path.name))
    # Size-capped and never through a symlink that leaves the repository.
    raw = _read_text(repo_path, "package.json")
    try:
        declared = (json.loads(raw).get("name") or "") if raw else ""
    except (ValueError, AttributeError):
        declared = ""
    words.update(tokenize_name(str(declared).replace("@", " ").replace("/", " ")))
    return sorted(words)


def name_product_layer(
    features: list[Any],
    product_features: list[Any],
    user_flows: list[Any],
    flows: list[Any],
    *,
    ctx: Any,
    routes_index: list[dict[str, Any]],
    llm: dict[str, Any],
) -> dict[str, Any]:
    """Pipeline entry: collect user-visible text, build the writer (keyed
    scans), and run the ladder over the emitted product layer."""
    candidates: set[str] = set()
    for feature in list(features) + list(product_features):
        candidates.update(feature.paths or [])
    for flow in flows:
        candidates.update(flow.paths or [])
        if flow.entry_point_file:
            candidates.add(flow.entry_point_file)
    index = collect_ui_text(ctx.repo_path, candidates, ctx.tracked_files)
    developer = [f for f in features if getattr(f, "layer", None) != "product"]
    return run_product_language_names(
        product_features, user_flows, flows,
        index=index, routes_index=routes_index, developer_features=developer,
        brand_words=_brand_words(ctx.repo_path), writer=build_name_writer(**llm),
    )
