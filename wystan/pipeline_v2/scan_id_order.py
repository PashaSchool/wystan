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

Known limit: the place is all that tells equal items apart, so it moves when
the set of equals itself changes. See :func:`places_among_equals`.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Hashable, Iterable

__all__ = ["places_among_equals", "scan_id_order"]

# ASCII digits only: ``\d`` and ``str.isdigit`` also accept characters such
# as "²" or "٣", which are not decimal numbers an id is counted with.
_DIGIT_RUN = re.compile(r"([0-9]+)")
# Sort tags: a run of digits sorts before text, so chunks of different kinds
# are never compared with each other.
_NUMBER, _TEXT = 0, 1

_Chunk = tuple[int, int, str]


def _number_chunk(digits: str) -> _Chunk:
    """A digit run ordered by its value without converting it.

    Of two runs without leading zeros the longer is the larger and runs of
    one length order as text. ``int()`` is not used: it refuses runs longer
    than the interpreter's digit limit, and no id may raise here.
    """
    significant = digits.lstrip("0")
    return (_NUMBER, len(significant), significant)


def scan_id_order(item_id: Any) -> tuple[tuple[_Chunk, ...], str]:
    """Sort key of an id, its digit runs read as numbers. Never raises.

    As text "UF-10" sorts before "UF-9", so two journeys numbered 9 and 10
    would swap places the day they become 10 and 11.

    The raw id is the last element: ids whose runs differ only by leading
    zeros ("a01b1", "a1b01") read as the same numbers, and without it their
    order would be whatever order the caller happened to hold them in.
    """
    raw = str(item_id)
    # ``split`` with one capturing group puts the digit runs at odd indices.
    chunks = tuple(
        _number_chunk(chunk) if index % 2 else (_TEXT, 0, chunk)
        for index, chunk in enumerate(_DIGIT_RUN.split(raw)) if chunk
    )
    return chunks, raw


def places_among_equals(
    ids: Iterable[str], content_of: Callable[[str], Hashable],
) -> dict[str, int]:
    """``{id: place}``: 0 for the first of the items with that content.

    An item that has no equal is at place 0.

    Known limit, by design: a place is counted among the equals present in
    this scan. When one of several equal items disappears, the equals after
    it move one place down; when a new equal item gets a lower id than the
    old ones, they move one place up. In both cases the remaining items
    answer for the places they now hold, so they take each other's
    remembered answers with no model call, and only a place nobody held
    before is asked. Nothing in equal evidence says which answer was whose,
    so every answer still fits the item it lands on.
    """
    seen: dict[Hashable, int] = {}
    places: dict[str, int] = {}
    for item_id in sorted(set(ids), key=scan_id_order):
        content = content_of(item_id)
        places[item_id] = seen.get(content, 0)
        seen[content] = places[item_id] + 1
    return places
