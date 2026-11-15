"""Command groups of a command-line tool are its product features.

The mint gives a command-line tool one product feature per shipped binary.
The tool itself declares finer structure: its command tree. A group command
(``gh pr``, described by its author as "Manage pull requests") is a product
feature; the commands under it (``gh pr create``) are its user flows.

This pass reads the command entry points and, for each group that owns code:

  * creates a product feature named by the group's own description, with the
    binary's feature as parent;
  * moves to it the developer features whose files are the group's, and the
    user flows whose code starts in the group's files.

The binary's feature takes the root command's description ("GitHub CLI").
A group that owns no developer feature is left inside the binary's feature.
No directory name is interpreted: a group's code is the tree its own command
declarations sit in.
"""

from __future__ import annotations

import re
from typing import Any

from wystan.pipeline_v2.cli_commands import detect_cli_clusters_cached
from wystan.pipeline_v2.entry_points.commands import command_entries
from wystan.pipeline_v2.entry_points.record import EntryPoint
from wystan.pipeline_v2.nav_taxonomy import aggregate_product_feature

__all__ = ["EVIDENCE_COMMAND_DESCRIPTION", "split_command_groups"]

EVIDENCE_COMMAND_DESCRIPTION = "authored:description"


def _directory(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else ""


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _descendants(entry: EntryPoint, children: dict[str, list[EntryPoint]]) -> list[EntryPoint]:
    found, queue = [], [entry]
    while queue:
        current = queue.pop()
        found.append(current)
        queue.extend(children.get(current.address, []))
    return found


def _evidence_tree(entries: list[EntryPoint]) -> str:
    """The directory every file that declares one of ``entries`` is under:
    the group's own code tree, read from where its commands are declared.
    Empty when the declarations share no directory."""
    parts = [_directory(entry.file).split("/") for entry in entries if entry.file]
    if not parts:
        return ""
    common = parts[0]
    for other in parts[1:]:
        size = 0
        while size < min(len(common), len(other)) and common[size] == other[size]:
            size += 1
        common = common[:size]
    return "/".join(common)


def _mostly_in(paths: list[str], tree: str) -> bool:
    if not paths or not tree:
        return False
    inside = sum(1 for path in paths if path.startswith(tree + "/"))
    return inside * 2 > len(paths)


def _name_with(feature: Any, entry: EntryPoint) -> None:
    if entry.label:
        feature.display_name = entry.label.rstrip(".")
        feature.name_confidence = "high"
        feature.name_evidence = [EVIDENCE_COMMAND_DESCRIPTION]


def _flow_entry_files(user_flow: Any, flows_by_id: dict[str, Any]) -> list[str]:
    files = []
    for member in user_flow.member_flow_ids or []:
        flow = flows_by_id.get(member)
        if flow is not None and flow.entry_point_file:
            files.append(flow.entry_point_file)
    return files


def split_command_groups(
    ctx: Any,
    product_features: list[Any],
    developer_features: list[Any],
    user_flows: list[Any],
    flows: list[Any],
) -> dict[str, Any]:
    """Split each binary's product feature by its command groups, in place."""
    telemetry: dict[str, Any] = {"binaries": 0, "groups_seen": 0, "features_created": [], "left_in_binary": []}
    homes = {
        pf.anchor_id: pf for pf in product_features
        if getattr(pf, "anchor_id", None) in {c.canonical_id for c in detect_cli_clusters_cached(ctx)}
    }
    if not homes:
        return telemetry
    entries = command_entries(ctx)
    by_address = {entry.address: entry for entry in entries}
    children: dict[str, list[EntryPoint]] = {}
    for entry in entries:
        if entry.parent in by_address:
            children.setdefault(entry.parent, []).append(entry)
    roots = sorted(
        (e for e in entries if e.parent not in by_address and children.get(e.address)),
        key=lambda e: (-len(children[e.address]), e.address),
    )
    if not roots:
        return telemetry
    flows_by_id = {(flow.uuid or flow.name): flow for flow in flows}
    taken = {pf.name for pf in product_features}
    # One shipped binary per scan unit is the supported case: its root
    # command is the one with the most children.
    root, home = roots[0], sorted(homes.values(), key=lambda pf: pf.name)[0]
    telemetry["binaries"] = 1
    _name_with(home, root)
    groups = [g for g in sorted(children[root.address], key=lambda e: e.address) if children.get(g.address)]
    trees = {g.address: _evidence_tree(_descendants(g, children)) for g in groups}
    for group in groups:
        telemetry["groups_seen"] += 1
        directories = trees[group.address]
        # A tree that contains another group's tree is not this group's own.
        shared = any(
            other != group.address and (tree == directories or tree.startswith(directories + "/"))
            for other, tree in trees.items()
        )
        devs = [] if shared else [
            dev for dev in developer_features
            if dev.product_feature_id == home.name and _mostly_in(list(dev.paths or []), directories)
        ]
        slug = _slug(group.address)
        if not devs or slug in taken:
            telemetry["left_in_binary"].append(group.address)
            continue
        feature = aggregate_product_feature(
            name=slug, display_name=group.address,
            description=group.label or group.address, contrib=devs,
        )
        feature.layer = "product"
        feature.anchor_id = f"{home.anchor_id}#{group.address}"
        feature.parent_product_feature_id = home.name
        _name_with(feature, group)
        product_features.append(feature)
        taken.add(slug)
        moved_paths = set(feature.paths or [])
        home.paths = [path for path in (home.paths or []) if path not in moved_paths]
        for dev in devs:
            dev.product_feature_id = slug
        moved_flows = 0
        for user_flow in user_flows:
            if user_flow.product_feature_id != home.name:
                continue
            files = _flow_entry_files(user_flow, flows_by_id)
            if files and _mostly_in(files, directories):
                user_flow.product_feature_id = slug
                moved_flows += 1
        telemetry["features_created"].append({
            "feature": slug, "name": feature.display_name,
            "developer_features": len(devs), "user_flows": moved_flows,
        })
    return telemetry
