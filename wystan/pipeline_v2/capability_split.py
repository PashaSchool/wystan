"""Split a product feature that holds most of the product into capabilities.

Where developer features are cut by layer, one product feature ends up
parenting most journeys ("Chat": 78 of 89, 97 % of the lines) and the
capabilities inside it are never minted. No field of the map partitions such
a feature on every repository (labels echo the host, synonyms do not merge,
names are code tokens), so the grouping is a model's judgement, bounded on
both sides by code: which journeys are asked about, and which answers count.

Per pool (a mega feature's journeys, or the parentless journeys whose code no
product feature owns) one request returns groups of journey ids. A group that
passes validation becomes a product feature that owns code, not only
journeys: the member flows of its journeys and the files only those flows use
are carved out of the host's developer features into developer features of
its own. Files other flows use stay where they are, so every file is in one
developer feature before and after and no line is counted twice.

The host is never removed and keeps whatever was not carved. Without a model
(no key, a failed call, a reply that fails validation as a whole) nothing is
split and the telemetry says why. The reply is cached by the pool's own
content, so a second scan of the same commit reproduces the first.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from wystan.pipeline_v2.personas import _default_client_factory, _persona_batch
from wystan.pipeline_v2.product_name_laws import LAW_CONTAINER_NAME, LAW_VERB_LED

__all__ = [
    "EVIDENCE_CAPABILITY_SPLIT",
    "MODEL_ID",
    "Pool",
    "find_pools",
    "run_capability_split",
    "validate_reply",
]

ROLE = "capability_split"
# The one call in the engine that needs the larger tier: on the same pools the
# small one duplicated and dropped journey ids and invented feature names in
# five of eight calls; this one failed validation in none.
MODEL_ID = "claude-sonnet-5-5"
EVIDENCE_CAPABILITY_SPLIT = "model:capability-split"
ANCHOR_PREFIX = "journeys:"
CARVE_NOTE = "fold:capability-split"
UNOWNED_POOL = "(unowned)"

KIND_NEW = "new_capability"
KIND_EXISTING = "existing_feature"
KIND_NOT_PRODUCT = "not_product"
_KINDS = frozenset({KIND_NEW, KIND_EXISTING, KIND_NOT_PRODUCT})

# A feature is "mega" when it parents this many journeys and holds this share
# of all journeys or of all product-feature lines. Measured on seven corpus
# repositories: seven such features, none on the repository whose product
# layer is healthy.
MEGA_MIN_JOURNEYS = 15
MEGA_JOURNEY_SHARE = 0.25
MEGA_LOC_SHARE = 0.30
# Below this a group of two cannot be told from noise.
UNOWNED_MIN_JOURNEYS = 4
# One journey is a feature only when the product itself states the name.
MIN_GROUP_JOURNEYS = 2
# A group holding more than half of a mega pool is the host under a new name.
MAX_GROUP_SHARE = 0.5
# Characters of journey lines per request (about 12k input tokens); a pool
# that does not fit after shortening is not asked about.
MAX_PROMPT_CHARS = 38_000
ROUTES_PER_JOURNEY = 3
EXISTING_FEATURES_MAX = 60
SYSTEM_CATEGORY = "system"
_NAME_WORD = re.compile(r"[a-z][a-z0-9]*")

SYSTEM_PROMPT = """You are a product owner who knows this product from the user's side. You are given journeys (things a user does in the product) that an automatic scan could not sort into product capabilities. Group them into the capabilities a user of this product would name.

Rules:
1. Each group gets a short product name of 2 to 4 words: what a product owner would call the capability in the product's navigation, documentation or pricing page. Not a file, not a component, not a route, not a verb, not a layer ("API", "Backend", "Frontend").
2. A journey that is plumbing and not something a user would name (error handling, middleware, internal sync, health checks, build or developer tooling, test fixtures, generic UI components) goes into one group with kind "not_product" and name "not_product".
3. A journey that fits one of the EXISTING product features goes into a group with kind "existing_feature" whose name is that feature's name exactly as listed. Do not create a new capability that duplicates an existing feature.
4. Every other journey goes into a group with kind "new_capability". Merge synonyms and parts of one capability (for example the list, the editor and the settings of the same thing) into one group; split journeys that only share a technical word.
5. Do not invent journeys. Use only the journey ids given. Every journey id appears exactly once across all groups.
6. Group names are unique.

Output STRICT JSON only:
{"groups": [{"name": "<group name>", "kind": "new_capability" | "existing_feature" | "not_product", "journey_ids": ["<id>", ...]}]}"""


@dataclass
class Pool:
    """The journeys of one request."""

    key: str
    """The host feature's slug, or ``UNOWNED_POOL``."""
    display: str
    journeys: list[Any] = field(default_factory=list)

    @property
    def is_unowned(self) -> bool:
        return self.key == UNOWNED_POOL


@dataclass
class Group:
    kind: str
    name: str
    journey_ids: list[str]


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _has_members(journey: Any) -> bool:
    return bool(getattr(journey, "member_flow_ids", None))


def _flow_index(flows: Iterable[Any]) -> dict[str, Any]:
    """Member ids are a flow's uuid or its name."""
    index: dict[str, Any] = {}
    for flow in flows:
        for key in (getattr(flow, "uuid", None), getattr(flow, "name", None)):
            if key:
                index.setdefault(str(key), flow)
    return index


def _flow_keys(flow: Any) -> set[str]:
    return {str(k) for k in (getattr(flow, "uuid", None), getattr(flow, "name", None)) if k}


def _members(journey: Any, flow_index: dict[str, Any]) -> list[Any]:
    found = [flow_index.get(str(mid)) for mid in getattr(journey, "member_flow_ids", None) or []]
    return [flow for flow in found if flow is not None]


def _is_product(feature: Any) -> bool:
    return getattr(feature, "layer", None) == "product"


def _developer_features(features: Iterable[Any]) -> list[Any]:
    return [f for f in features if not _is_product(f)]


def find_pools(
    product_features: list[Any], user_flows: list[Any], flows: list[Any], features: list[Any],
) -> list[Pool]:
    """Mega features in slug order, then the unowned pool."""
    journeys = [j for j in user_flows if _has_members(j)]
    by_parent: dict[str, list[Any]] = {}
    for journey in journeys:
        by_parent.setdefault(str(journey.product_feature_id or ""), []).append(journey)
    developers = _developer_features(features)
    lines: dict[str, int] = {}
    for dev in developers:
        home = getattr(dev, "product_feature_id", None)
        if home:
            lines[home] = lines.get(home, 0) + int(getattr(dev, "loc", None) or 0)
    total_lines = sum(lines.values())
    pools: list[Pool] = []
    for pf in sorted(product_features, key=lambda f: f.name):
        held = by_parent.get(pf.name, [])
        journey_share = len(held) / len(journeys) if journeys else 0.0
        loc_share = lines.get(pf.name, 0) / total_lines if total_lines else 0.0
        if len(held) >= MEGA_MIN_JOURNEYS and (
            journey_share >= MEGA_JOURNEY_SHARE or loc_share >= MEGA_LOC_SHARE
        ):
            pools.append(Pool(pf.name, pf.display_name or pf.name, held))
    unowned = _unowned_journeys(by_parent.get("", []), flows, developers)
    if len(unowned) >= UNOWNED_MIN_JOURNEYS:
        pools.append(Pool(UNOWNED_POOL, UNOWNED_POOL, unowned))
    return pools


def _unowned_journeys(parentless: list[Any], flows: list[Any], developers: list[Any]) -> list[Any]:
    """Parentless journeys none of whose member flows belongs to a product
    feature."""
    owner = {dev.name: getattr(dev, "product_feature_id", None) for dev in developers}
    flow_index = _flow_index(flows)
    return [
        journey for journey in parentless
        if not any(
            owner.get(str(getattr(flow, "primary_feature", "") or ""))
            for flow in _members(journey, flow_index)
        )
    ]


def _first_sentence(text: str | None) -> str:
    return re.split(r"(?<=[.!?])\s", (text or "").strip(), maxsplit=1)[0]


def _journey_line(journey: Any, level: int) -> str:
    """One journey as a compact line; a higher ``level`` drops more."""
    parts = [f"id={journey.id}", f"name={journey.name!r}"]
    if level < 1:
        parts.append(f"does={_first_sentence(getattr(journey, 'description', None))!r}")
    parts += [
        f"intent={getattr(journey, 'intent', None)}",
        f"resource={getattr(journey, 'resource', None)}",
        f"domain={getattr(journey, 'domain', None)}",
    ]
    routes = sorted(str(r) for r in getattr(journey, "routes", None) or [])[:ROUTES_PER_JOURNEY]
    if routes and level < 2:
        parts.append(f"routes={','.join(routes)}")
    return "- " + " | ".join(parts)


def build_user_prompt(product: str, existing: list[str], pool: Pool) -> str | None:
    """The request for one pool, shortened until it fits; ``None`` when it
    cannot fit."""
    if pool.is_unowned:
        where = "These journeys currently belong to no product feature."
    else:
        where = (
            f'These journeys currently all sit under the existing feature "{pool.display}", '
            f'which has become a catch-all. A journey that really is "{pool.display}" stays '
            f'there (kind existing_feature, name "{pool.display}").'
        )
    ordered = sorted(pool.journeys, key=lambda j: str(j.id))
    for level in range(3):
        lines = [_journey_line(journey, level) for journey in ordered]
        if sum(len(line) for line in lines) <= MAX_PROMPT_CHARS:
            break
    else:
        return None
    return "\n".join([
        f"Product: {product}",
        f"EXISTING product features: {', '.join(sorted(existing)[:EXISTING_FEATURES_MAX])}",
        "",
        where,
        f"Journeys ({len(lines)}); fields: id | name | does (description) | intent | resource | "
        "domain | routes:",
        *lines,
        "",
        "Return the grouping. Every journey id above exactly once.",
    ])


def _parse_groups(reply: dict[str, Any] | None) -> list[Group] | None:
    raw = (reply or {}).get("groups")
    if not isinstance(raw, list):
        return None
    groups: list[Group] = []
    for row in raw:
        if not isinstance(row, dict) or row.get("kind") not in _KINDS:
            return None
        ids = row.get("journey_ids")
        if not isinstance(row.get("name"), str) or not isinstance(ids, list):
            return None
        groups.append(Group(row["kind"], row["name"].strip(), [str(i) for i in ids]))
    return groups


def validate_reply(pool: Pool, existing: Iterable[str], reply: dict[str, Any] | None) -> tuple[list[Group], str | None]:
    """(groups, failure). A reply is used whole or not at all: an unknown,
    repeated or missing journey id, a repeated group name, or an existing
    feature that does not exist means the model did not follow the task, and
    nothing it says about this pool is trusted."""
    groups = _parse_groups(reply)
    if groups is None:
        return [], "unparsable"
    known = {str(journey.id) for journey in pool.journeys}
    seen: list[str] = [jid for group in groups for jid in group.journey_ids]
    if set(seen) - known:
        return [], "unknown_journey_id"
    if len(seen) != len(set(seen)):
        return [], "repeated_journey_id"
    if known - set(seen):
        return [], "missing_journey_id"
    names = [group.name.lower() for group in groups if group.kind != KIND_NOT_PRODUCT]
    if len(names) != len(set(names)):
        return [], "repeated_group_name"
    offered = {name.lower() for name in existing}
    if any(g.kind == KIND_EXISTING and g.name.lower() not in offered for g in groups):
        return [], "unknown_existing_feature"
    return groups, None


def _subject_words(members: list[Any]) -> set[str]:
    """The nouns the group's journeys are about, singular and plural."""
    words: set[str] = set()
    for journey in members:
        for word in _NAME_WORD.findall(str(getattr(journey, "resource", "") or "").lower()):
            words.update({word, word + "s", word.rstrip("s")})
    return words


def _excused(law: str, name: str, members: list[Any]) -> bool:
    """Two laws judge a word by a list: "verb-led" (the first word is also a
    verb: "Access Tokens", "Read Replicas") and "container" (the word is also
    a layer: "Models"). When that word is what the group's own journeys are
    about, it is the capability's noun and the law does not apply."""
    words = _NAME_WORD.findall(name.lower())
    subject = _subject_words(members)
    if law == LAW_VERB_LED:
        return bool(words) and words[0] in subject
    if law == LAW_CONTAINER_NAME:
        return bool(words) and all(word in subject for word in words)
    return False


def _refusal(
    group: Group, pool: Pool, journeys: dict[str, Any], taken: set[str],
    violations: Callable[[str], list[str]], stated: Callable[[], frozenset[str]],
) -> str | None:
    """Why a new group is not minted; its journeys then stay where they are."""
    members = [journeys[jid] for jid in group.journey_ids]
    broken = [law for law in violations(group.name) if not _excused(law, group.name, members)]
    if broken:
        return "unlawful_name:" + broken[0]
    if group.name.lower() in taken or _slug(group.name) in taken:
        return "name_taken"
    if len(group.journey_ids) < MIN_GROUP_JOURNEYS and group.name.lower() not in stated():
        return "single_journey"
    if not pool.is_unowned and len(group.journey_ids) > MAX_GROUP_SHARE * len(pool.journeys):
        return "most_of_the_host"
    # Jobs the system starts are not something a user addresses.
    if all(getattr(journeys[jid], "category", None) == SYSTEM_CATEGORY for jid in group.journey_ids):
        return "system_only"
    return None


class _Carver:
    """Moves a group's flows and the files only they use into developer
    features of their own."""

    def __init__(self, features: list[Any], flows: list[Any], edges: list[Any]) -> None:
        self._features = features
        self._flow_index = _flow_index(flows)
        self._by_name = {f.name: f for f in _developer_features(features)}
        self._edges: dict[str, list[Any]] = {}
        for edge in edges:
            self._edges.setdefault(str(getattr(edge, "flow_id", "")), []).append(edge)
        self.files_moved = 0

    def _exclusive_files(self, dev: Any, moving: list[Any]) -> list[str]:
        own = set(dev.paths or [])
        moving_ids = {id(flow) for flow in moving}
        kept: set[str] = set()
        for flow in dev.flows or []:
            if id(flow) not in moving_ids:
                kept.update(flow.paths or [])
        used = {path for flow in moving for path in flow.paths or []}
        return sorted((used & own) - kept)

    def _move_flow(self, chunk: Any, flow: Any) -> None:
        old_id = getattr(flow, "id", None)
        new_id = f"{chunk.name}::{flow.name}"
        chunk.flows.append(flow)
        # The feature's copy of a flow and the flow layer's may be two
        # objects: both must name the new developer feature.
        twin = next((self._flow_index[k] for k in sorted(_flow_keys(flow)) if k in self._flow_index), flow)
        for row in (flow, twin):
            row.primary_feature = chunk.name
            row.id = new_id
        for edge in self._edges.pop(str(old_id or ""), []):
            if getattr(edge, "type", None) == "primary":
                edge.feature = chunk.name
            edge.flow_id = new_id
            self._edges.setdefault(new_id, []).append(edge)

    def carve(self, journeys: list[Any], slug: str, target: str, donors: set[str | None]) -> list[Any]:
        """Carved developer features, owned by ``target``. Only developer
        features whose product feature is in ``donors`` give code."""
        from wystan.pipeline_v2.lane_excavation import _make_excav_dev, _remove_files_from_shell

        by_dev: dict[str, list[Any]] = {}
        for journey in journeys:
            for flow in _members(journey, self._flow_index):
                by_dev.setdefault(str(getattr(flow, "primary_feature", "") or ""), []).append(flow)
        carved: list[Any] = []
        for dev_name in sorted(by_dev):
            dev = self._by_name.get(dev_name)
            if dev is None or getattr(dev, "product_feature_id", None) not in donors:
                continue
            wanted = set().union(*(_flow_keys(flow) for flow in by_dev[dev_name]))
            moving = [flow for flow in dev.flows or [] if _flow_keys(flow) & wanted]
            if not moving:
                continue
            files = self._exclusive_files(dev, moving)
            chunk = _make_excav_dev(dev, slug, files, self._free_name(f"{dev.name}-{slug}"))
            chunk.product_feature_id = target
            chunk.anchor_id = CARVE_NOTE
            dev.flows = [flow for flow in dev.flows if not any(flow is m for m in moving)]
            for flow in moving:
                self._move_flow(chunk, flow)
            _remove_files_from_shell(dev, set(files))
            self._features.append(chunk)
            self._by_name[chunk.name] = chunk
            self.files_moved += len(files)
            carved.append(chunk)
        return carved

    def _free_name(self, wanted: str) -> str:
        name, n = wanted, 2
        taken = {f.name for f in self._features}
        while name in taken:
            name, n = f"{wanted}-{n}", n + 1
        return name


def _mint(group: Group, carved: list[Any], host: str) -> Any:
    from wystan.pipeline_v2.nav_taxonomy import aggregate_product_feature

    slug = _slug(group.name)
    feature = aggregate_product_feature(
        slug, group.name,
        f"Capability split out of {host} ({len(group.journey_ids)} journeys, model-grouped).",
        carved,
    )
    feature.layer = "product"
    feature.anchor_id = ANCHOR_PREFIX + slug
    feature.name_evidence = [EVIDENCE_CAPABILITY_SPLIT]
    feature.name_confidence = "medium"
    return feature


@dataclass
class _Run:
    """What one scan's split works on and reports."""

    product_features: list[Any]
    carver: _Carver
    violations: Callable[[str], list[str]]
    stated: Callable[[], frozenset[str]]
    mega: set[str]
    telemetry: dict[str, Any]

    def _existing(self) -> dict[str, Any]:
        return {(pf.display_name or pf.name).lower(): pf for pf in self.product_features}

    def apply(self, pool: Pool, groups: list[Group]) -> dict[str, Any]:
        journeys = {str(j.id): j for j in pool.journeys}
        row: dict[str, Any] = {
            "pool": pool.key, "journeys_in": len(journeys), "minted": [], "joined": {},
            "left_in_host": 0, "not_product": 0, "rejected": [],
        }
        # Code comes from the host and from developer features nobody owns:
        # journeys parked on a host have their flows in the lane. Another
        # product feature's code is never taken.
        donors: set[str | None] = {None} if pool.is_unowned else {pool.key, None}
        for group in sorted(groups, key=lambda g: (g.kind, g.name.lower())):
            members = [journeys[jid] for jid in group.journey_ids]
            if group.kind == KIND_NOT_PRODUCT:
                row["not_product"] += len(members)
            elif group.kind == KIND_EXISTING:
                self._join(pool, group, members, donors, row)
            else:
                self._new(pool, group, members, donors, journeys, row)
        row["left_in_host"] = row["journeys_in"] - sum(m["journeys"] for m in row["minted"]) - sum(
            row["joined"].values())
        return row

    def _join(self, pool: Pool, group: Group, members: list[Any], donors: set, row: dict) -> None:
        target = self._existing()[group.name.lower()]
        if target.name == pool.key:
            return
        if target.name in self.mega:
            row["rejected"].append({"name": group.name, "reason": "target_is_mega", "journeys": len(members)})
            return
        self.carver.carve(members, _slug(group.name), target.name, donors)
        for journey in members:
            journey.product_feature_id = target.name
        row["joined"][target.name] = row["joined"].get(target.name, 0) + len(members)

    def _new(self, pool: Pool, group: Group, members: list[Any], donors: set, journeys: dict, row: dict) -> None:
        taken = set(self._existing()) | {pf.name for pf in self.product_features}
        reason = _refusal(group, pool, journeys, taken, self.violations, self.stated)
        if reason is None:
            carved = self.carver.carve(members, _slug(group.name), _slug(group.name), donors)
            if not carved:
                # Nothing to own: the feature would only park the journeys.
                reason = "no_code_to_own"
        if reason is not None:
            row["rejected"].append({"name": group.name, "reason": reason, "journeys": len(members)})
            return
        feature = _mint(group, carved, pool.display)
        self.product_features.append(feature)
        for journey in members:
            journey.product_feature_id = feature.name
        row["minted"].append({
            "name": group.name, "pf": feature.name, "journeys": len(members),
            "developer_features": [dev.name for dev in carved],
            "files": sum(len(dev.paths or []) for dev in carved),
        })


def _ask(pool: Pool, existing: list[str], product: str, llm: dict[str, Any], client: Any) -> tuple[dict | None, dict, str | None]:
    user = build_user_prompt(product, existing, pool)
    if user is None:
        return None, {}, "pool_too_large"
    reply, call = _persona_batch(
        role=ROLE, client=client, model=MODEL_ID, system=SYSTEM_PROMPT, user=user,
        cost_tracker=llm.get("cost_tracker"), cache=llm.get("cache"),
        llm_health=llm.get("llm_health"),
        candidates_for_log=sorted(str(j.id) for j in pool.journeys),
    )
    return reply, call, None if reply is not None else "no_reply"


def run_capability_split(
    product_features: list[Any],
    user_flows: list[Any],
    features: list[Any],
    flows: list[Any],
    edges: list[Any],
    *,
    product: str,
    violations: Callable[[str], list[str]],
    stated_names: Callable[[], frozenset[str]] = frozenset,
    llm: dict[str, Any] | None = None,
    client_factory: Callable[[], Any | None] = _default_client_factory,
) -> dict[str, Any]:
    """Split mega features and the unowned pool in place; returns telemetry.

    ``violations`` gives the product-feature name laws a name breaks;
    ``stated_names`` the lower-cased names the product itself shows as a
    title, heading or navigation label (read only for a group of one)."""
    llm = llm or {}
    telemetry: dict[str, Any] = {
        "applied": False, "reason": None, "model": MODEL_ID, "pools": [],
        "features_minted": 0, "journeys_moved": 0, "files_carved": 0,
        "llm_calls": 0, "cache_hits": 0, "refused_replies": 0,
        "input_tokens": 0, "output_tokens": 0,
    }
    pools = find_pools(product_features, user_flows, flows, features)
    if not pools:
        telemetry["reason"] = "no_pool"
        return telemetry
    client = client_factory()
    if client is None:
        telemetry["reason"] = "no_key"
        telemetry["pools"] = [{"pool": p.key, "journeys_in": len(p.journeys)} for p in pools]
        return telemetry
    run = _Run(
        product_features, _Carver(features, flows, edges), violations, stated_names,
        {p.key for p in pools if not p.is_unowned}, telemetry,
    )
    for pool in pools:
        # Names minted for an earlier pool are existing features for a later one.
        existing = sorted({pf.display_name or pf.name for pf in product_features})
        reply, call, failure = _ask(pool, existing, product, llm, client)
        telemetry["llm_calls"] += int(call.get("llm_calls", 0))
        telemetry["cache_hits"] += int(bool(call.get("cache_hit")))
        telemetry["input_tokens"] += int(call.get("input_tokens", 0))
        telemetry["output_tokens"] += int(call.get("output_tokens", 0))
        groups: list[Group] = []
        if failure is None:
            groups, failure = validate_reply(pool, existing, reply)
        if failure is not None:
            telemetry["refused_replies"] += 1
            telemetry["pools"].append({"pool": pool.key, "journeys_in": len(pool.journeys), "refused": failure})
            continue
        row = run.apply(pool, groups)
        telemetry["pools"].append(row)
        telemetry["features_minted"] += len(row["minted"])
        telemetry["journeys_moved"] += row["journeys_in"] - row["left_in_host"]
    telemetry["files_carved"] = run.carver.files_moved
    telemetry["applied"] = telemetry["features_minted"] > 0 or telemetry["journeys_moved"] > 0
    if not telemetry["applied"]:
        telemetry["reason"] = "nothing_accepted"
    return telemetry


def product_name_of(repo_path: Any) -> str:
    """What the prompt calls the product: the repository's directory name."""
    return os.path.basename(os.path.normpath(str(repo_path))) or "this product"
