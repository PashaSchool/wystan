"""A row born by the route-group split keeps its route group as its anchor
(Stage 6.86).

Stage 8.9 cuts a flat handler row by the route group each file handles. On a
repository that registers every route in one file, the route anchor of a
group (``route:user``) covers that registering file only: a handler file
enters it solely through a same-stem file under a models directory, merged
by key (``spine_anchors._merge_anchors``). A born row without such a file
matched no anchor, had no candidate in ``_classify_dev`` and, holding no
flows yet at the mint, was laned (``no_anchor_lineage``).

The split already resolved each route of the group to the file that defines
its handler. So a born row's files join the route anchor of the group it was
cut along (Stage 8.9's record, :func:`route_group_split.born_route_groups`,
keyed by row name; a row's text is never read), exactly as
a same-stem models file joins it: same membership, same rungs, same
refusals. Only that one group: other segments whose routes resolved to the
same file add nothing. No route anchor for the group, or no born row: the
anchors are returned as they are, the same list object.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Callable, Iterable, Mapping

if TYPE_CHECKING:
    from wystan.pipeline_v2.spine_anchors import SpineAnchor

#: The source class of an anchor built from registered routes.
_ROUTE_SOURCE = "route"


def with_born_row_files(
    anchors: list["SpineAnchor"],
    rows: Iterable[Any],
    owned_of: Callable[[Any], list[str]],
    born: Mapping[str, str],
) -> tuple[list["SpineAnchor"], int]:
    """*anchors* with each born row's owned files added to its group's route
    anchor (*born*: ``{row name: group}``), and how many born rows were
    given one."""
    added: dict[str, set[str]] = defaultdict(set)
    rows_given = 0
    for row in rows if born else ():
        group = born.get(getattr(row, "name", None) or "")
        anchor = _group_anchor(anchors, group) if group else None
        owned = owned_of(row) if anchor is not None else []
        if anchor is None or not owned:
            continue
        added[anchor.canonical_id].update(owned)
        rows_given += 1
    if not added:
        return anchors, 0
    return [
        replace(a, files=a.files | frozenset(added[a.canonical_id]))
        if a.canonical_id in added else a
        for a in anchors
    ], rows_given


def _group_anchor(
    anchors: list["SpineAnchor"], group: str,
) -> "SpineAnchor | None":
    """The route anchor the engine built for *group*: the one named after
    the key (``route:<key>``) when it exists, else the first by id among the
    route anchors of that key."""
    found = [a for a in anchors
             if a.key == group and _ROUTE_SOURCE in (a.sources or {a.source})]
    if not found:
        return None
    return min(found, key=lambda a: (a.canonical_id != f"route:{group}",
                                     a.canonical_id))


__all__ = ["with_born_row_files"]
