"""What Stage 8.9's route-group splits did, so a split can be put back whole.

A route-group split moves flows (:mod:`route_group_split`), and a row born
by it can split again, so one flow can move several times in the stage. The
ledger keeps the moves as they were made, hands the stage the moves closed
(every old id to the id of the row that holds the flow at the end), and
checks at the end of the stage that every final id is held by a flow. When
one is not, the split that first moved that flow is undone as a whole: its
parent gets back what it had, every row born under it leaves, every flow
gets back its row and id, and the counts those splits added are taken out.
Rows the route planner never touched are not read.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterator

from wystan.pipeline_v2.route_group_split import (
    SKIP_DANGLING_REFERENCE,
    SKIP_UNDO_INCOMPLETE,
    FlowMove,
    MoveCycle,
    MoveKey,
    close_flow_moves,
)

if TYPE_CHECKING:
    from wystan.models.types import Feature

# Stage 8.9 counters one evaluated row adds to; an undone split takes back
# what it and every row under it added.
_COUNTERS = (
    "oversized_total", "features_split", "subfeatures_created", "paths_moved",
    "members_deowned", "route_group_splits", "route_group_capped",
    "route_group_flows_unmoved",
)
_LISTS = ("split_sample", "route_group_skipped")
# What a row the planner split adds whether or not the split stands.
_STILL_EVALUATED = ("oversized_total",)


@dataclass
class _Added:
    """What one row's evaluation added to the stage's telemetry."""

    counters: dict[str, int]
    items: dict[str, list[Any]]
    floors: list[str]


@dataclass
class _RouteSplit:
    """One route-group split: the parent as it was, its flows' row and id
    before the move, the rows it bore and the moves it made."""

    source: "Feature"
    before: "Feature"
    flow_states: list[tuple[Any, Any, Any]]
    files: int        # owned files of the parent, for the record
    route_sites: int  # route sites the planner read, for the record
    born: list["Feature"] = field(default_factory=list)
    groups: dict[int, str] = field(default_factory=dict)  # id(born) -> group
    moves: list[FlowMove] = field(default_factory=list)


class RouteSplitLedger:
    """The stage's route-group splits and the flow moves they made."""

    def __init__(self, features: list["Feature"]) -> None:
        self._splits: list[_RouteSplit] = []
        self._moves: dict[MoveKey, FlowMove] = {}
        self._children: dict[int, list["Feature"]] = {}
        self._added: dict[int, _Added] = {}
        # Where each stage-start row stood, so an undone parent that a later
        # step removed goes back to its place.
        self._order = {id(f): i for i, f in enumerate(features)}

    # ── during the stage ────────────────────────────────────────────────

    @contextmanager
    def evaluating(self, source: "Feature", result: Any) -> Iterator[None]:
        """Note what evaluating *source* adds to *result*'s telemetry."""
        counters = {name: getattr(result, name) for name in _COUNTERS}
        lengths = {name: len(getattr(result, name)) for name in _LISTS}
        floors = set(result.floor_by_feature)
        yield
        self._added[id(source)] = _Added(
            {name: getattr(result, name) - counters[name] for name in _COUNTERS},
            {name: getattr(result, name)[lengths[name]:] for name in _LISTS},
            [key for key in result.floor_by_feature if key not in floors],
        )

    def note_children(self, source: "Feature", minted: list["Feature"]) -> None:
        """Rows *source* split into, by either planner."""
        self._children[id(source)] = list(minted)

    def would_cycle(self, moves: list[FlowMove]) -> bool:
        """The stage's moves with *moves* added lead back to an id passed."""
        try:
            close_flow_moves({**self._moves, **{_key(m): m for m in moves}})
        except MoveCycle:
            return True
        return False

    def open_split(
        self, source: "Feature", *, files: int, route_sites: int,
    ) -> _RouteSplit:
        """Remember *source* as it is, before a route-group split changes
        it. Its ledgers are replaced, never edited in place, by the split,
        so a shallow copy keeps them."""
        split = _RouteSplit(
            source=source,
            before=source.model_copy(),
            flow_states=[
                (flow, getattr(flow, "id", None),
                 getattr(flow, "primary_feature", None))
                for flow in getattr(source, "flows", None) or []
            ],
            files=files,
            route_sites=route_sites,
        )
        self._splits.append(split)
        return split

    def is_held_parent(self, row: "Feature") -> bool:
        """*row* is the parent of a route-group split and still holds a file
        (owned or not) or a flow: husk cleanup must not drop it."""
        if not any(s.source is row for s in self._splits):
            return False
        return bool(getattr(row, "paths", None) or getattr(row, "member_files", None)
                    or getattr(row, "flows", None))

    def record_born(
        self, split: _RouteSplit, row: "Feature", group: str,
    ) -> None:
        """*row* was born by *split* for the route group *group*."""
        split.born.append(row)
        split.groups[id(row)] = group

    def born_groups(self, features: list["Feature"]) -> dict[str, str]:
        """``{row name: group}`` of the born rows the stage ends with: the
        record later stages read to know a born row (never its text)."""
        group_of = {key: g for s in self._splits for key, g in s.groups.items()}
        return dict(sorted(
            (row.name, group_of[id(row)])
            for row in features if id(row) in group_of))

    def parent_names(self, features: list["Feature"]) -> list[str]:
        """Names of the residual parents of the splits the stage ends with
        (a born row that split again is one too)."""
        present = {id(f) for f in features}
        return sorted({s.source.name for s in self._splits
                       if id(s.source) in present})

    def record_moves(self, split: _RouteSplit, moves: list[FlowMove]) -> None:
        split.moves.extend(moves)
        for move in moves:
            self._moves[_key(move)] = move

    # ── at the end of the stage ─────────────────────────────────────────

    def settle(
        self, features: list["Feature"], result: Any, used_names: set[str],
    ) -> dict[MoveKey, FlowMove]:
        """The stage's moves, closed, once no reference can dangle.

        The invariant: every id an edge or copy will be rewritten to is the
        id of a flow some row holds, and an old id an edge cannot follow
        (flows sharing it went to different rows) is still held by a flow.
        While a split breaks it, that split is undone as a whole and
        recorded."""
        while True:
            closed = close_flow_moves(self._moves)
            broken = self._first_dangling(closed, features)
            if broken is None:
                return closed
            self._undo(broken, features, _UndoContext(result, used_names))

    def _first_dangling(
        self, closed: dict[MoveKey, FlowMove], features: list["Feature"],
    ) -> _RouteSplit | None:
        held = {
            getattr(flow, "id", None)
            for row in features for flow in getattr(row, "flows", None) or []
        }
        ends: dict[str, set[str]] = {}
        for (old_id, _entry), move in closed.items():
            ends.setdefault(old_id, set()).add(move.new_id)
        for split in self._splits:
            if any(closed[_key(m)].new_id not in held
                   or (len(ends[m.old_id]) > 1 and m.old_id not in held)
                   for m in split.moves):
                return split
        return None

    def _undo(
        self, split: _RouteSplit, features: list["Feature"], ctx: "_UndoContext",
    ) -> None:
        """Put *split* back with every split made under it: the parent as
        it was, in the feature list, and every name the splits reserved
        free again."""
        result = ctx.result
        under = self._rows_under(split)
        undone = [s for s in self._splits
                  if s is split or id(s.source) in under]
        for later in reversed(undone):
            self._restore(later)
        ctx.used_names.difference_update(
            row.name for s in undone for row in s.born)
        features[:] = [f for f in features if id(f) not in under]
        self._put_back(split.source, features)
        # Without the split the parent is still an oversized row the stage
        # evaluated; every other count it and the rows under it added goes.
        self._take_back(id(split.source), result, keep=_STILL_EVALUATED)
        for key in under:
            self._take_back(key, result)
        self._splits = [s for s in self._splits if s not in undone]
        dropped = {_key(m) for s in undone for m in s.moves}
        self._moves = {k: m for k, m in self._moves.items() if k not in dropped}
        result.route_group_skipped.append({
            "row": split.source.name,
            "reason": SKIP_DANGLING_REFERENCE,
            "files": split.files,
            "route_sites": split.route_sites,
        })
        missing = _missing_after_undo(split)
        if missing:
            result.route_group_skipped.append({
                "row": split.source.name, "reason": SKIP_UNDO_INCOMPLETE,
                **missing})

    def _put_back(self, parent: "Feature", features: list["Feature"]) -> None:
        """Insert *parent* where it stood when a later step removed it."""
        if any(f is parent for f in features):
            return
        place = self._order.get(id(parent), len(features))
        at = sum(1 for f in features if self._order.get(id(f), place + 1) < place)
        features.insert(at, parent)

    def _rows_under(self, split: _RouteSplit) -> set[int]:
        """Ids of every row born by *split* or by a split under it."""
        under: set[int] = set()
        stack = list(split.born)
        while stack:
            row = stack.pop()
            if id(row) in under:
                continue
            under.add(id(row))
            stack.extend(self._children.get(id(row), ()))
        return under

    @staticmethod
    def _restore(split: _RouteSplit) -> None:
        for name in type(split.before).model_fields:
            setattr(split.source, name, getattr(split.before, name))
        for flow, flow_id, primary in split.flow_states:
            flow.id = flow_id
            flow.primary_feature = primary

    def _take_back(
        self, key: int, result: Any, keep: tuple[str, ...] = (),
    ) -> None:
        added = self._added.pop(key, None)
        if added is None:
            return
        for name, amount in added.counters.items():
            if name not in keep:
                setattr(result, name, getattr(result, name) - amount)
        for name, items in added.items.items():
            kept = [x for x in getattr(result, name)
                    if not any(x is item for item in items)]
            setattr(result, name, kept)
        for floor_key in added.floors:
            result.floor_by_feature.pop(floor_key, None)


@dataclass(frozen=True)
class _UndoContext:
    result: Any
    used_names: set[str]


def _missing_after_undo(split: _RouteSplit) -> dict[str, int]:
    """Counts of what the restored parent lacks against itself before the
    split (files listed, members, flow ids); empty when it is whole."""
    now, then = split.source, split.before
    flow_ids = [flow_id for _flow, flow_id, _primary in split.flow_states]
    missing = {
        "files_missing": len(set(then.paths or []) - set(now.paths or [])),
        "members_missing": len(
            {m.path for m in then.member_files or []}
            - {m.path for m in now.member_files or []}),
        "flows_missing": len(
            set(flow_ids) - {getattr(f, "id", None) for f in now.flows or []}),
    }
    return missing if any(missing.values()) else {}


def _key(move: FlowMove) -> MoveKey:
    return (move.old_id, move.entry_file)


__all__ = ["RouteSplitLedger"]
