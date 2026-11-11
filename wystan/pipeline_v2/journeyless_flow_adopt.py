"""Flows no journey claimed join the journey their neighbours are in.

The user-flow family builds journeys from the flows it can place and leaves
the rest out. Most of what is left is small (a helper, a hook), but part of it
is the body of a screen: a 800-line panel whose smaller neighbours all sit in
one journey while it sits in none. Its code is then counted under the product
feature and shown under no journey, so the feature reads as larger than
everything inside it (2026-11-11 corpus: 2,673 of 12,450 flows in no journey;
473 of them of 100 lines or more).

Rule, per unclaimed flow of at least ``MIN_ADOPT_LOC`` owned lines:

  * look at the journeys that already hold a flow of the same developer
    feature whose entry file is in the same directory, then one and two
    directories up;
  * at the first level where such journeys exist, the one holding the most
    such flows adopts it; a tie adopts nothing.

No journey is created and no flow moves between journeys. Deterministic,
no model call. Runs before journey line counts are stamped, so the counts
include what was adopted.
"""

from __future__ import annotations

from collections import Counter
from posixpath import dirname
from typing import Any

from wystan.pipeline_v2.stage_6_97b_uf_loc import flow_owned_spans, union_span_len
from wystan.pipeline_v2.stage_6_9_test_strip import is_test_path

__all__ = ["MAX_LEVELS_UP", "MIN_ADOPT_LOC", "adopt_journeyless_flows"]

# Below this a flow is a helper: adopting it would only add a step nobody
# would name. At or above it the flow is a piece of a screen.
MIN_ADOPT_LOC = 100
# The directory itself, its parent and its grandparent.
MAX_LEVELS_UP = 2
_SAMPLE_SIZE = 20


def _owned_loc(flow: Any) -> int:
    by_file: dict[str, list[tuple[int, int]]] = {}
    for path, start, end in flow_owned_spans(flow):
        by_file.setdefault(path, []).append((start, end))
    return sum(union_span_len(by_file[path]) for path in sorted(by_file))


def _keys(flow: Any) -> list[str]:
    return [key for key in (getattr(flow, "uuid", None), getattr(flow, "name", None)) if key]


def _ancestors(directory: str) -> list[str]:
    """``directory`` and up to ``MAX_LEVELS_UP`` parents, nearest first."""
    levels = [directory]
    while len(levels) <= MAX_LEVELS_UP and dirname(levels[-1]) not in ("", levels[-1]):
        levels.append(dirname(levels[-1]))
    return levels


def _member_key(journey: Any, flow: Any, flow_by_key: dict[str, Any]) -> str:
    """The id to store: a uuid when the journey's members are uuids."""
    uuid, name = getattr(flow, "uuid", None), getattr(flow, "name", None)
    for member in getattr(journey, "member_flow_ids", None) or []:
        known = flow_by_key.get(member)
        if known is not None:
            return (uuid or name) if member == getattr(known, "uuid", None) else (name or uuid)
    return uuid or name


def adopt_journeyless_flows(user_flows: list[Any] | None, flows: list[Any] | None) -> dict[str, Any]:
    """Attach unclaimed flows to a neighbouring journey in place; telemetry."""
    telemetry: dict[str, Any] = {
        "unclaimed": 0, "considered": 0, "adopted": 0, "adopted_loc": 0,
        "no_neighbour": 0, "tie": 0, "sample": [],
    }
    journeys = list(user_flows or [])
    flow_by_key: dict[str, Any] = {}
    for flow in flows or []:
        for key in _keys(flow):
            flow_by_key.setdefault(key, flow)

    journey_of: dict[int, Any] = {}
    # (developer feature, directory) -> journey id -> how many of its flows sit there
    neighbours: dict[tuple[str, str], Counter[str]] = {}
    by_id = {str(getattr(journey, "id", "")): journey for journey in journeys}
    for journey in journeys:
        for member in getattr(journey, "member_flow_ids", None) or []:
            flow = flow_by_key.get(member)
            if flow is None or id(flow) in journey_of:
                continue
            journey_of[id(flow)] = journey
            entry = getattr(flow, "entry_point_file", None)
            if not entry:
                continue
            owner = str(getattr(flow, "primary_feature", "") or "")
            for level in _ancestors(dirname(entry)):
                neighbours.setdefault((owner, level), Counter())[str(journey.id)] += 1

    seen: set[int] = set()
    unclaimed = []
    for flow in flows or []:
        if id(flow) in seen or id(flow) in journey_of:
            continue
        seen.add(id(flow))
        unclaimed.append(flow)
    telemetry["unclaimed"] = len(unclaimed)

    for flow in sorted(unclaimed, key=lambda f: (str(getattr(f, "name", "")), str(getattr(f, "uuid", "")))):
        entry = getattr(flow, "entry_point_file", None)
        if not entry or is_test_path(entry):
            continue
        loc = _owned_loc(flow)
        if loc < MIN_ADOPT_LOC:
            continue
        telemetry["considered"] += 1
        owner = str(getattr(flow, "primary_feature", "") or "")
        votes = next(
            (neighbours[(owner, level)] for level in _ancestors(dirname(entry)) if neighbours.get((owner, level))),
            None,
        )
        if votes is None:
            telemetry["no_neighbour"] += 1
            continue
        ranked = sorted(votes.items(), key=lambda item: (-item[1], item[0]))
        if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
            telemetry["tie"] += 1
            continue
        journey = by_id[ranked[0][0]]
        journey.member_flow_ids = [*(journey.member_flow_ids or []), _member_key(journey, flow, flow_by_key)]
        if getattr(journey, "member_count", None) is not None:
            journey.member_count = len(journey.member_flow_ids)
        flow.user_flow_id = journey.id
        telemetry["adopted"] += 1
        telemetry["adopted_loc"] += loc
        if len(telemetry["sample"]) < _SAMPLE_SIZE:
            telemetry["sample"].append({"flow": str(getattr(flow, "name", "")), "loc": loc, "journey": str(journey.id)})
    return telemetry
