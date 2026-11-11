"""Adapter: pages.

A page is a route a user can open. The routing extractors already produce
the route index; this adapter turns its page rows into entry points and
adds what the product calls each page: the navigation label that links to
it, its title, or its first heading. A page's parent is the nearest page
whose URL is a prefix of its own.
"""

from __future__ import annotations

from typing import Any, Iterable

from wystan.pipeline_v2.authored_names import (
    SOURCE_HEADING,
    SOURCE_NAV,
    SOURCE_TITLE,
    authored_names,
    page_rows,
)
from wystan.pipeline_v2.entry_points.record import (
    KIND_PAGE,
    LABEL_HEADING,
    LABEL_NAV,
    LABEL_TITLE,
    EntryPoint,
)
from wystan.pipeline_v2.ui_text import UiTextIndex

__all__ = ["ADAPTER", "page_entries"]

ADAPTER = "pages"
_LABEL_SOURCE = {SOURCE_NAV: LABEL_NAV, SOURCE_TITLE: LABEL_TITLE, SOURCE_HEADING: LABEL_HEADING}


def _parent(address: str, addresses: set[str]) -> str | None:
    segments = [s for s in address.split("/") if s]
    for size in range(len(segments) - 1, 0, -1):
        candidate = "/" + "/".join(segments[:size])
        if candidate in addresses:
            return candidate
    return None


def page_entries(
    routes_index: Iterable[dict[str, Any]],
    index: UiTextIndex,
    nav_pairs: Iterable[tuple[str, str | None]],
    *,
    structural_words: frozenset[str],
    brand_words: frozenset[str],
    scope_words: frozenset[str],
    files_without_ui: frozenset[str] = frozenset(),
) -> list[EntryPoint]:
    """Page entry points with the label the product gives each one."""
    pages = page_rows(routes_index, structural_words, files_without_ui)
    nav = list(nav_pairs)
    addresses = {page.pattern for page in pages}
    entries: dict[str, EntryPoint] = {}
    for page in sorted(pages, key=lambda p: (p.pattern, p.file)):
        stated = [
            name for name in authored_names(
                page, index, nav, brand_words=brand_words, scope_words=scope_words,
            ) if name.source in _LABEL_SOURCE
        ]
        entries.setdefault(page.pattern, EntryPoint(
            kind=KIND_PAGE,
            address=page.pattern,
            file=page.file,
            label=stated[0].text if stated else None,
            label_source=_LABEL_SOURCE[stated[0].source] if stated else None,
            parent=_parent(page.pattern, addresses),
            adapter=ADAPTER,
        ))
    return list(entries.values())
