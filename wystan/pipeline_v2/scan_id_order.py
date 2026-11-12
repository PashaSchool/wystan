"""The order of items the model cannot tell apart.

Two items whose evidence is equal are one question with two answers, and
nothing in the evidence says which answer is whose. The answers are dealt in
the order of the items' ids, so a second scan of the same input deals them
the same way.

The id itself never enters a prompt or a memory key: only "k-th among its
equals" does. That place does not move when unrelated items are added (they
are not among the equals) or when the scan renumbers its items (a renumbering
shifts ids, it does not reorder them among themselves). The list order of
the items is not read at all.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Hashable, Iterable

__all__ = ["places_among_equals", "scan_id_order"]

_DIGIT_RUN = re.compile(r"(\d+)")
# Sort tags: a run of digits sorts before text, so chunks of different kinds
# are never compared with each other.
_NUMBER, _TEXT = 0, 1


def scan_id_order(item_id: Any) -> tuple[tuple[int, int, str], ...]:
    """Sort key of an id, its digit runs read as numbers.

    As text "UF-10" sorts before "UF-9", so two journeys numbered 9 and 10
    would swap places the day they become 10 and 11.
    """
    return tuple(
        (_NUMBER, int(chunk), "") if chunk.isdigit() else (_TEXT, 0, chunk)
        for chunk in _DIGIT_RUN.split(str(item_id)) if chunk
    )


def places_among_equals(
    ids: Iterable[str], content_of: Callable[[str], Hashable],
) -> dict[str, int]:
    """``{id: place}``: 0 for the first of the items with that content.

    An item that has no equal is at place 0.
    """
    seen: dict[Hashable, int] = {}
    places: dict[str, int] = {}
    for item_id in sorted(set(ids), key=scan_id_order):
        content = content_of(item_id)
        places[item_id] = seen.get(content, 0)
        seen[content] = places[item_id] + 1
    return places
