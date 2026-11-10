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
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from wystan.pipeline_v2.authored_names import (
    SOURCE_URL,
    AuthoredName,
    authored_names,
    page_rows,
    top_page,
)
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
    "build_ui_index",
    "is_unnameable",
    "name_product_layer",
    "route_files_without_ui",
    "run_product_language_names",
]

EVIDENCE_UI_TEXT = "ui-text"
EVIDENCE_UI_LABEL = "ui-label"
EVIDENCE_NOT_AUTHORED = "not-authored"
UNNAMEABLE_PREFIX = "unnameable:"
NO_USER_SURFACE = "no_user_surface"

_MAX_PROMPT_LABELS = 30
_MAX_PROMPT_ROUTES = 8
_MAX_PROMPT_MEMBERS = 12
_TITLE_SEPARATOR = re.compile(r"\s+[-|·–—]\s+")
_FEATURE_LABEL_KINDS = ("title", "heading")
_MIN_STEM = 4
# An entry group is a node of its own when it has children: two or more.
_MIN_GROUP_ENTRIES = 2


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
    slug: str = ""
    authored: list[AuthoredName] = field(default_factory=list)
    """What the product calls the feature's top page, most trusted first."""
    url_name: str = ""
    """The top page's URL word, when it is the only name and a bare verb."""
    has_no_surface: bool = False
    """The product has pages and this feature has none."""
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
    """True when a word on each side has the same stem: equal, or a common
    prefix that covers all but the last letter of the shorter word
    ("share" and "sharing", "sign" and "signing")."""
    right_words = list(right)
    for a in left:
        for b in right_words:
            shorter = min(len(a), len(b))
            common = len(os.path.commonprefix([a, b]))
            if a == b or (shorter >= _MIN_STEM and common >= max(_MIN_STEM, shorter - 1)):
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
        self._current: dict[tuple[str, str], str] = {}
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
        holder = self._current.get((target.group, name.lower()))
        if holder is not None and holder != target.key:
            return "a sibling is already called this"
        return None

    def reserve(self, group: str, names: Iterable[str]) -> None:
        """Names already in use that this namer must not hand out again."""
        self._taken.setdefault(group, set()).update(name.lower() for name in names)

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

    def _identity_candidate(self, target: NameTarget) -> str | None:
        """A feature's own slug written as words ("share" to "Share"), when
        that passes the laws. The slug comes from the feature's route or
        package, so it is about the feature even when the display name the
        earlier passes chose is not ("Remix")."""
        if target.kind != KIND_FEATURE or not target.slug:
            return None
        text = " ".join(part.capitalize() for part in re.split(r"[-_\s]+", target.slug) if part)
        return text if text and self._rejection(target, text) is None else None

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
        if target.url_name:
            self._take(target, target.url_name)
            self.telemetry["kept"] += 1
            target.apply(target.url_name, "low", [SOURCE_URL, "bare-verb"])
            return
        broken = self._violations(target, target.current)
        if not broken:
            self.telemetry["kept"] += 1
            self._take(target, target.current)
            return
        label = self._label_candidate(target) or self._identity_candidate(target)
        if label is not None:
            self.telemetry["from_label"] += 1
            self._take(target, label)
            target.apply(label, "medium", [EVIDENCE_UI_LABEL])
            return
        self.telemetry["unnameable"] += 1
        by_law = self.telemetry["unnameable_by_law"]
        by_law[broken[0]] = by_law.get(broken[0], 0) + 1
        target.apply(target.current, "low", [UNNAMEABLE_PREFIX + law for law in broken])

    def _reads_as_fragment(self, target: NameTarget, text: str) -> bool:
        """True for a one-word name that another feature's name starts with
        ("Sign" beside "Sign In" and "Sign Up")."""
        word = text.lower()
        if " " in word:
            return False
        return any(
            other.startswith(word + " ") for other in self._taken.get(target.group, set())
        )

    def _settle_feature(self, target: NameTarget) -> bool:
        """Name a product feature from its top page. True when settled.

        A feature is never sent to the writer: its name is either stated by
        the product or it has none."""
        if target.kind != KIND_FEATURE or not (target.authored or target.has_no_surface):
            return False
        for candidate in target.authored:
            if product_name_violations(candidate.text, KIND_FEATURE, self._ctx, is_shown=True):
                continue
            if candidate.text.lower() in self._taken.get(target.group, set()):
                continue
            if candidate.source == SOURCE_URL and self._reads_as_fragment(target, candidate.text):
                # ``/sign/:token`` gives "Sign", which reads as a fragment
                # next to "Sign In". The writer may phrase it from the
                # page's own text; without one the URL word stands.
                target.url_name = candidate.text
                return False
            self._take(target, candidate.text)
            confidence = "medium" if candidate.source == SOURCE_URL else "high"
            self.telemetry["authored"] = self.telemetry.get("authored", 0) + 1
            target.apply(candidate.text, confidence, [candidate.source])
            return True
        if not target.has_no_surface and not self._violations(target, target.current):
            # It has a page; the product just does not label it. The current
            # name stands, marked as not authored.
            self._take(target, target.current)
            self.telemetry["kept"] += 1
            target.apply(target.current, "low", [EVIDENCE_NOT_AUTHORED])
            return True
        law = NO_USER_SURFACE if target.has_no_surface else "no_lawful_page_name"
        self.telemetry["unnameable"] += 1
        by_law = self.telemetry["unnameable_by_law"]
        by_law[law] = by_law.get(law, 0) + 1
        target.apply(target.current, "low", [UNNAMEABLE_PREFIX + law])
        return True

    def run(self, targets: list[NameTarget], parents: dict[str, str]) -> None:
        ordered = sorted(targets, key=lambda target: target.key)
        self.telemetry["total"] += len(ordered)
        # The name an item wears now is spoken for: nobody else is renamed
        # into it.
        for target in ordered:
            self._current.setdefault((target.group, target.current.lower()), target.key)
        # Features with a stated name first, so a URL word is judged against
        # the names its siblings really have.
        ordered.sort(key=lambda t: (not any(c.source != SOURCE_URL for c in t.authored), t.key))
        ordered = [target for target in ordered if not self._settle_feature(target)]
        accepted = self._propose(ordered, parents)
        for target in ordered:
            name = accepted.get(target.key)
            if name is None:
                self._settle(target)
            elif name != target.current:
                self.telemetry["written"] += 1
                # A written feature name is grounded, not stated by the
                # product: it never carries full confidence.
                confidence = "medium" if target.kind == KIND_FEATURE else "high"
                target.apply(name, confidence, [EVIDENCE_UI_TEXT])
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
        slug=feature.name,
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
    nav_pairs: Iterable[tuple[str, str | None]] = (),
    files_without_ui: Iterable[str] = (),
    writer: NameWriter | None = None,
) -> dict[str, Any]:
    """Rename product features and user flows in place; returns telemetry."""
    nav_pairs = list(nav_pairs)
    # A name the author wrote (a command's description) is not ours to judge
    # or replace: the laws exist to catch names derived from code.
    authored_features = [f for f in product_features if _is_author_named(f)]
    product_features = [f for f in product_features if not _is_author_named(f)]
    authored_flows = [u for u in user_flows if _is_author_named(u)]
    user_flows = [u for u in user_flows if not _is_author_named(u)]
    ctx = build_law_context(index, brand_words)
    routes_by_file = {
        str(row.get("file")): str(row.get("pattern"))
        for row in routes_index if row.get("file") and row.get("pattern")
    }
    feature_targets = [_feature_target(f, index, routes_by_file) for f in product_features]
    pages = page_rows(routes_index, ctx.structural_words, frozenset(files_without_ui))
    scope_words = ctx.listed("tenant_scope_segments")
    operations_by_file: dict[str, set[str]] = {}
    for row in routes_index:
        if row.get("method") != "PAGE" and row.get("file") and row.get("pattern"):
            operations_by_file.setdefault(str(row["file"]), set()).add(str(row["pattern"]))
    for target, feature in zip(feature_targets, product_features):
        page = top_page(feature.paths or [], target.identity_words, pages)
        if page is None:
            # No page. The feature still has a surface when its own code
            # serves a group of API operations: an API is something a user
            # addresses too. One lone endpoint is a leaf, not a feature. In a
            # product with no pages at all the lack of a page says nothing.
            operations = set().union(*(operations_by_file.get(p, set()) for p in feature.paths or []))
            target.has_no_surface = bool(pages) and len(operations) < _MIN_GROUP_ENTRIES
            continue
        target.authored = authored_names(
            page, index, nav_pairs,
            brand_words=ctx.brand_words, scope_words=scope_words,
        )
        # Evidence for the writer is the feature's own pages, not every
        # shared component its code reaches.
        page_files = {p.file for p in pages} & set(feature.paths or [])
        target.labels = index.labels_for(page_files)
        target.routes = sorted({p.pattern for p in pages if p.file in page_files})
    members_of: dict[str, list[str]] = {}
    for dev in developer_features:
        if dev.product_feature_id:
            members_of.setdefault(dev.product_feature_id, []).append(dev.name)
    for target, feature in zip(feature_targets, product_features):
        target.members = sorted(members_of.get(feature.name, []))

    feature_namer = _Namer(ctx, writer)
    feature_namer.reserve("pf", (f.display_name or f.name for f in authored_features))
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
        "author_named": {"product_features": len(authored_features), "user_flows": len(authored_flows)},
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
    name_flows: bool = True,
) -> dict[str, Any]:
    """Pipeline entry: collect user-visible text, build the writer (keyed
    scans), run the ladder, and remove what stayed unnameable.

    Called twice by finalize. The first call, with ``name_flows`` off, runs before
    the line-count rollups so a removed product feature's code is counted
    where it went. The second call is the last pass before output."""
    from wystan.pipeline_v2.unnameable_demote import (
        demote_unnameable_features,
        drop_unnameable_flows,
    )

    index = build_ui_index(features, product_features, flows, ctx)
    developer = [f for f in features if getattr(f, "layer", None) != "product"]
    telemetry = run_product_language_names(
        product_features, user_flows if name_flows else [], flows,
        index=index, routes_index=routes_index, developer_features=developer,
        brand_words=_brand_words(ctx.repo_path), nav_pairs=_nav_pairs(ctx, index),
        files_without_ui=route_files_without_ui(ctx.repo_path, routes_index),
        writer=build_name_writer(**llm),
    )
    telemetry["entry_points"] = _entry_point_report(ctx, routes_index, index)
    # What has no product-language name is not shown as product.
    telemetry["features_removed"] = demote_unnameable_features(
        product_features, developer, user_flows, flows,
    )
    if name_flows:
        telemetry["flows_removed"] = drop_unnameable_flows(user_flows, flows)
    return telemetry


def build_ui_index(
    features: list[Any], product_features: list[Any], flows: list[Any], ctx: Any,
) -> UiTextIndex:
    """User-visible text of every file a feature or flow owns."""
    candidates: set[str] = set()
    for feature in list(features) + list(product_features):
        candidates.update(feature.paths or [])
    for flow in flows:
        candidates.update(flow.paths or [])
        if flow.entry_point_file:
            candidates.add(flow.entry_point_file)
    return collect_ui_text(ctx.repo_path, candidates, ctx.tracked_files)


def is_unnameable(item: Any) -> bool:
    """True when the ladder found no product-language name for ``item``."""
    return any(
        str(note).startswith(UNNAMEABLE_PREFIX)
        for note in (getattr(item, "name_evidence", None) or [])
    )


def _nav_pairs(ctx: Any, index: UiTextIndex) -> list[tuple[str, str | None]]:
    """``(label, href)`` pairs of the product's navigation files."""
    from wystan.pipeline_v2.product_strings import collect_product_strings

    from wystan.pipeline_v2.ui_text import _load_catalog

    strings = collect_product_strings(ctx.repo_path, sorted(index.by_file))
    catalog = _load_catalog(ctx.repo_path, ctx.tracked_files)
    pairs: set[tuple[str, str | None]] = set()
    for found in strings.nav_pairs_by_file.values():
        for label, href in found:
            text = _stated_label(label, catalog)
            if text:
                pairs.add((text, href))
    return sorted(pairs, key=lambda pair: (pair[0], pair[1] or ""))


_CATALOG_KEY = re.compile(r"^[a-z0-9]+(?:[_.:\-][a-z0-9]+)*$")


def _stated_label(label: str, catalog: dict[str, str]) -> str | None:
    """The text a navigation row shows. A row often holds a catalog key
    (``event_types_page_title``); the key is resolved, and a key with no
    catalog entry is not a label."""
    if label in catalog:
        return catalog[label]
    # An identifier-shaped label with no catalog entry is a key we could not
    # resolve (``event_types_page_title``, ``users``), not text a user reads.
    if _CATALOG_KEY.match(label):
        return None
    return label


_SCRIPT_ROUTE_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs")
_DEFAULT_EXPORT = re.compile(r"\bexport\s+default\b|\bas\s+default\b")


def route_files_without_ui(repo_path: Any, routes_index: list[dict[str, Any]]) -> list[str]:
    """Route files that render nothing: a TS/JS route module with no default
    export is a resource route (an endpoint, a proxy), not a page."""
    silent: list[str] = []
    for file in sorted({str(row.get("file") or "") for row in routes_index}):
        if not file.endswith(_SCRIPT_ROUTE_SUFFIXES):
            continue
        text = _read_text(repo_path, file)
        if text is not None and not _DEFAULT_EXPORT.search(text):
            silent.append(file)
    return silent


_AUTHOR_EVIDENCE = frozenset({"authored:description", "authored:schema", "cli-declared"})


def _is_author_named(item: Any) -> bool:
    """True when ``item`` already wears a name its author declared in code:
    a command's own description."""
    return bool(_AUTHOR_EVIDENCE & set(getattr(item, "name_evidence", None) or ()))


def _entry_point_report(ctx: Any, routes_index: list[dict[str, Any]], index: UiTextIndex) -> dict[str, Any]:
    """What the product declares a user can address, by kind. A report only:
    nothing here changes the product layer."""
    from wystan.pipeline_v2.entry_points import collect_entry_points, entry_report
    from wystan.pipeline_v2.entry_points.commands import command_entries
    from wystan.pipeline_v2.entry_points.pages import page_entries

    laws = build_law_context(index, _brand_words(ctx.repo_path))

    def pages() -> list[Any]:
        return page_entries(
            routes_index, index, _nav_pairs(ctx, index),
            structural_words=laws.structural_words, brand_words=laws.brand_words,
            scope_words=laws.listed("tenant_scope_segments"),
            files_without_ui=frozenset(route_files_without_ui(ctx.repo_path, routes_index)),
        )

    def commands() -> list[Any]:
        return command_entries(ctx)

    def operations() -> list[Any]:
        from wystan.pipeline_v2.entry_points.graphql_schema import graphql_entries

        return graphql_entries(ctx)

    def actions() -> list[Any]:
        from wystan.pipeline_v2.entry_points.actions import action_entries

        return action_entries(ctx)

    entries, errors = collect_entry_points([pages, commands, operations, actions])
    return entry_report(entries, errors)
