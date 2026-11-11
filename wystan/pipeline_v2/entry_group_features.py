"""Groups of declared operations are product features.

An API product declares what it offers as operations composed into groups
(a GraphQL schema: ``Checkout`` holds ``checkoutCreate``,
``checkoutComplete``). A group is a product feature; nothing about it is
read from a directory name.

For each group that owns code this pass creates a product feature named by
the group, and gives it:

  * the unowned developer features whose files sit in the group's own tree
    (where its operations are implemented);
  * the unowned developer features that the group's flows reach more than
    any other group's (the domain code behind the operations);
  * the parentless user flows whose code starts in the group's tree.

It only takes what nobody owns: a developer feature already in a product
feature stays there.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Callable

from wystan.pipeline_v2.cli_command_groups import _evidence_tree, _mostly_in
from wystan.pipeline_v2.entry_points.record import EntryPoint
from wystan.pipeline_v2.nav_taxonomy import aggregate_product_feature

__all__ = ["EVIDENCE_SCHEMA_GROUP", "mint_entry_group_features"]

EVIDENCE_SCHEMA_GROUP = "authored:schema"
_MIN_GROUP_ENTRIES = 2
_MIN_REACH_VOTES = 2


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _group_of(path: str, trees: dict[str, str]) -> str | None:
    owners = [group for group, tree in trees.items() if tree and path.startswith(tree + "/")]
    return max(owners, key=lambda g: len(trees[g])) if owners else None


def _reach_votes(
    developer: Any, flows: list[Any], trees: dict[str, str],
) -> Counter[str]:
    files = set(developer.paths or [])
    votes: Counter[str] = Counter()
    for flow in flows:
        group = _group_of(flow.entry_point_file or "", trees)
        if group and files.intersection(flow.paths or []):
            votes[group] += 1
    return votes


def _operation_holders(
    groups: list[EntryPoint], children: dict[str, list[EntryPoint]], developers: list[Any],
) -> dict[str, Any]:
    """For each group, the developer feature that holds most of the files its
    operations are implemented in. A domain module that carries its own API
    code next to models and migrations is found this way."""
    owner_of = {path: dev for dev in developers for path in dev.paths or []}
    holders: dict[str, Any] = {}
    for group in groups:
        files = {entry.file for entry in children[group.address]}
        votes = Counter(id(owner_of[f]) for f in files if f in owner_of)
        if not votes:
            continue
        winner, count = votes.most_common(1)[0]
        if count * 2 > len(files):
            holders[group.address] = next(dev for dev in developers if id(dev) == winner)
    return holders


def mint_entry_group_features(
    entries: list[EntryPoint],
    product_features: list[Any],
    developer_features: list[Any],
    user_flows: list[Any],
    flows: list[Any],
) -> dict[str, Any]:
    """Create one product feature per operation group, in place."""
    telemetry: dict[str, Any] = {"groups": 0, "features_created": [], "skipped": []}
    children: dict[str, list[EntryPoint]] = {}
    for entry in entries:
        if entry.parent:
            children.setdefault(entry.parent, []).append(entry)
    groups = sorted(
        (e for e in entries if not e.parent and len(children.get(e.address, [])) >= _MIN_GROUP_ENTRIES),
        key=lambda e: e.address,
    )
    telemetry["groups"] = len(groups)
    if not groups:
        return telemetry
    trees = {g.address: _evidence_tree(children[g.address]) for g in groups}
    for address, tree in list(trees.items()):
        # A tree that contains another group's tree is not this group's own.
        if not tree or any(o != address and (t == tree or t.startswith(tree + "/")) for o, t in trees.items()):
            trees[address] = ""
    unowned = [d for d in developer_features if not d.product_feature_id]
    members: dict[str, list[Any]] = {g.address: [] for g in groups}
    holders = _operation_holders(groups, children, unowned)
    for developer in sorted(unowned, key=lambda d: d.name):
        direct = [g for g, tree in trees.items() if _mostly_in(list(developer.paths or []), tree)]
        direct += [g for g, holder in holders.items() if holder is developer and g not in direct]
        if len(direct) == 1:
            members[direct[0]].append(developer)
            continue
        if len(direct) > 1:
            # It implements several groups (a catch-all API module): it is
            # none of them in particular.
            continue
        ranked = _reach_votes(developer, flows, trees).most_common(2)
        if ranked and ranked[0][1] >= _MIN_REACH_VOTES and (len(ranked) == 1 or ranked[0][1] > ranked[1][1]):
            members[ranked[0][0]].append(developer)
    taken = {pf.name for pf in product_features}
    flows_by_id = {(flow.uuid or flow.name): flow for flow in flows}
    for group in groups:
        slug = _slug(group.address)
        if not members[group.address] or slug in taken:
            telemetry["skipped"].append(group.address)
            continue
        feature = aggregate_product_feature(
            name=slug, display_name=group.label or group.address,
            description=f"{len(children[group.address])} operations the schema groups as {group.address}.",
            contrib=members[group.address],
        )
        feature.layer = "product"
        feature.anchor_id = f"entry:{group.kind}:{group.address}"
        feature.name_confidence = "high"
        feature.name_evidence = [EVIDENCE_SCHEMA_GROUP]
        product_features.append(feature)
        taken.add(slug)
        owned = set(feature.paths or [])
        for developer in members[group.address]:
            developer.product_feature_id = slug
            developer.shared_reason = None
        moved = _adopt_user_flows(user_flows, flows_by_id, slug, trees[group.address], owned)
        telemetry["features_created"].append({
            "feature": slug, "operations": len(children[group.address]),
            "developer_features": len(members[group.address]), "user_flows": moved,
        })
    return telemetry


def _adopt_user_flows(
    user_flows: list[Any], flows_by_id: dict[str, Any], slug: str, tree: str, owned: set[str],
) -> int:
    """Give parentless user flows that start in the group's code to it."""
    in_group: Callable[[str], bool] = lambda path: bool(tree and path.startswith(tree + "/")) or path in owned
    moved = 0
    for user_flow in user_flows:
        if user_flow.product_feature_id:
            continue
        starts = [
            flows_by_id[m].entry_point_file for m in (user_flow.member_flow_ids or [])
            if m in flows_by_id and flows_by_id[m].entry_point_file
        ]
        if starts and sum(1 for path in starts if in_group(path)) * 2 > len(starts):
            user_flow.product_feature_id = slug
            moved += 1
    return moved
