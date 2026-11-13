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
    FlowMove,
    MoveCycle,
    close_flow_moves,
)

if TYPE_CHECKING:
    from wystan.models.types import Feature

# Stage 8.9 counters one evaluated row adds to; an undone split takes back
# what it and every row under it added.
_COUNTERS = (
    "oversized_total", "features_split", "subfeatures_created", "paths_moved",
    "members_deowned", "route_group_splits", "route_group_capped",
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
    moves: list[FlowMove] = field(default_factory=list)


class RouteSplitLedger:
    """The stage's route-group splits and the flow moves they made."""

    def __init__(self) -> None:
        self._splits: list[_RouteSplit] = []
        self._moves: dict[str, FlowMove] = {}
        self._children: dict[int, list["Feature"]] = {}
        self._added: dict[int, _Added] = {}

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
            close_flow_moves({**self._moves, **{m.old_id: m for m in moves}})
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

    def record_moves(self, split: _RouteSplit, moves: list[FlowMove]) -> None:
        split.moves.extend(moves)
        for move in moves:
            self._moves[move.old_id] = move

    # ── at the end of the stage ─────────────────────────────────────────

    def settle(self, features: list["Feature"], result: Any) -> dict[str, FlowMove]:
        """The stage's moves, closed, once no final id dangles.

        The invariant: every id an edge or copy will be rewritten to is the
        id of a flow some row holds. While a split breaks it, that split is
        undone as a whole and recorded."""
        while True:
            closed = close_flow_moves(self._moves)
            broken = self._first_dangling(closed, features)
            if broken is None:
                return closed
            self._undo(broken, features, result)

    def _first_dangling(
        self, closed: dict[str, FlowMove], features: list["Feature"],
    ) -> _RouteSplit | None:
        held = {
            getattr(flow, "id", None)
            for row in features for flow in getattr(row, "flows", None) or []
        }
        for split in self._splits:
            if any(closed[m.old_id].new_id not in held for m in split.moves):
                return split
        return None

    def _undo(
        self, split: _RouteSplit, features: list["Feature"], result: Any,
    ) -> None:
        """Put *split* back with every split made under it."""
        under = self._rows_under(split)
        undone = [s for s in self._splits
                  if s is split or id(s.source) in under]
        for later in reversed(undone):
            self._restore(later)
        features[:] = [f for f in features if id(f) not in under]
        # Without the split the parent is still an oversized row the stage
        # evaluated; every other count it and the rows under it added goes.
        self._take_back(id(split.source), result, keep=_STILL_EVALUATED)
        for key in under:
            self._take_back(key, result)
        self._splits = [s for s in self._splits if s not in undone]
        dropped = {m.old_id for s in undone for m in s.moves}
        self._moves = {k: m for k, m in self._moves.items() if k not in dropped}
        result.route_group_skipped.append({
            "row": split.source.name,
            "reason": SKIP_DANGLING_REFERENCE,
            "files": split.files,
            "route_sites": split.route_sites,
        })

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


__all__ = ["RouteSplitLedger"]
