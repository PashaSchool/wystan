"""The name the product itself gives a product feature.

A product feature is something a user can open. So its name is read from the
place the user opens: the feature's top page.

  1. Find the feature's top page: the shallowest page route among its files,
     preferring a route whose URL carries the feature's own word.
  2. Read what the product calls that page, in this order: the navigation
     label that links to it, the page title, the page's first heading.
  3. With a page but no such text, the name is the URL's own word
     (``/share/:slug`` gives "Share"): the user sees it in the address bar.
  4. With no page at all, the feature has no user surface. In a product that
     has pages, that makes it code, not a product feature.

Nothing here is derived from a directory, a package or a framework name, and
nothing is guessed. Pure functions over the route index and collected text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from wystan.pipeline_v2.indexes import is_addressing_segment
from wystan.pipeline_v2.ui_text import UiTextIndex

__all__ = [
    "SOURCE_HEADING",
    "SOURCE_NAV",
    "SOURCE_TITLE",
    "SOURCE_URL",
    "AuthoredName",
    "TopPage",
    "authored_names",
    "page_rows",
    "top_page",
]

SOURCE_NAV = "authored:nav"
SOURCE_TITLE = "authored:title"
SOURCE_HEADING = "authored:heading"
SOURCE_URL = "url"

_PAGE_METHOD = "PAGE"
_API_SEGMENTS = frozenset({"api", "trpc", "graphql", "rpc"})
_INTERNAL_PREFIX = "__"
_TITLE_SEPARATOR = re.compile(r"\s+[-|·–—:]\s+")
_MIN_STEM = 4


@dataclass(frozen=True)
class TopPage:
    """A feature's top page: its URL pattern and the file that renders it."""

    pattern: str
    file: str

    def static_segments(self) -> list[str]:
        return [s for s in self.pattern.split("/") if s and not s.startswith((":", "*"))]


@dataclass(frozen=True)
class AuthoredName:
    """One name candidate and where the product states it."""

    text: str
    source: str


def _same_stem(left: str, right: str) -> bool:
    left, right = left.lower(), right.lower()
    if left == right:
        return True
    return min(len(left), len(right)) >= _MIN_STEM and (
        left.startswith(right) or right.startswith(left)
    )


def page_rows(
    routes_index: Iterable[dict[str, Any]],
    structural: frozenset[str],
    files_without_ui: frozenset[str] = frozenset(),
) -> list[TopPage]:
    """Routes a user can open: pages, not API endpoints, not route files
    that render nothing, and not component files a router scan mistook for
    pages."""
    pages: list[TopPage] = []
    for row in routes_index:
        pattern, file = str(row.get("pattern") or ""), str(row.get("file") or "")
        if row.get("method") != _PAGE_METHOD or not pattern or not file:
            continue
        if file in files_without_ui:
            continue
        segments = [s for s in pattern.split("/") if s]
        if any(s in _API_SEGMENTS for s in segments):
            continue
        if segments and segments[0].lower() in structural:
            continue
        pages.append(TopPage(pattern, file))
    return pages


def top_page(paths: Iterable[str], slug_words: Iterable[str], pages: list[TopPage]) -> TopPage | None:
    """The shallowest page among ``paths``; a page whose URL carries one of
    the feature's own words wins over one that does not."""
    owned = set(paths)
    words = list(slug_words)

    def rank(page: TopPage) -> tuple[int, int, int, int, str]:
        statics = page.static_segments()
        carries = any(_same_stem(seg, word) for seg in statics for word in words)
        # A render-only route (``/__htmltopdf/...``) is a page of last resort.
        internal = any(seg.startswith(_INTERNAL_PREFIX) for seg in statics)
        return (int(internal), 0 if carries else 1, len(statics), len(page.pattern), page.pattern)

    candidates = sorted((page for page in pages if page.file in owned), key=rank)
    return candidates[0] if candidates else None


def _capability_segments(page: TopPage, scope_words: frozenset[str]) -> list[str]:
    segments = [s for s in page.pattern.split("/") if s]
    return [
        seg for i, seg in enumerate(segments)
        if not seg.startswith((":", "*", _INTERNAL_PREFIX))
        and not is_addressing_segment(segments, i, scope_words)
    ]


def _nav_labels(
    page: TopPage, nav_pairs: Iterable[tuple[str, str | None]], scope_words: frozenset[str],
) -> list[str]:
    """Navigation labels whose link leads to ``page``, shortest first."""
    target = _capability_segments(page, scope_words)
    if not target:
        return []
    found: set[str] = set()
    for label, href in nav_pairs:
        if not href or not href.startswith("/"):
            continue
        clean = href.split("?", 1)[0].split("#", 1)[0]
        segments = [s for s in clean.split("/") if s]
        statics = [
            seg for i, seg in enumerate(segments)
            if "$" not in seg and "{" not in seg and not seg.startswith(":")
            and not (len(seg) == 1 and i + 1 < len(segments))
            and seg.lower() not in scope_words
        ]
        if [s.lower() for s in statics] == [s.lower() for s in target]:
            found.add(label.strip())
    return sorted(found, key=lambda text: (len(text.split()), len(text), text))


def _without_brand(text: str, brand_words: frozenset[str]) -> str:
    """A page title without its site suffix ("Documents - Acme" gives
    "Documents")."""
    parts = [part.strip() for part in _TITLE_SEPARATOR.split(text) if part.strip()]
    kept = [
        part for part in parts
        if not all(word.lower() in brand_words for word in re.findall(r"[A-Za-z]+", part))
    ]
    return kept[0] if kept else ""


def _about_url(text: str, url_words: list[str]) -> bool:
    words = re.findall(r"[A-Za-z]+", text)
    joined = "".join(words).lower()
    return any(
        _same_stem(word, url) or _same_stem(joined, url)
        for word in words for url in url_words
    )


def authored_names(
    page: TopPage,
    index: UiTextIndex,
    nav_pairs: Iterable[tuple[str, str | None]],
    *,
    brand_words: frozenset[str],
    scope_words: frozenset[str],
) -> list[AuthoredName]:
    """Name candidates for the feature that owns ``page``, most trusted first."""
    names = [AuthoredName(label, SOURCE_NAV) for label in _nav_labels(page, nav_pairs, scope_words)]
    capability = _capability_segments(page, scope_words)
    url_words = [w for seg in capability for w in re.split(r"[-_.\s]+", seg) if w]
    # A title names the feature only on the feature's root page. The title
    # of ``/team/verify/email/:token`` names that one sub-page, not the
    # feature that owns it.
    is_root_page = len(capability) == 1
    for kind, source in (("title", SOURCE_TITLE), ("heading", SOURCE_HEADING)):
        for label in index.by_file.get(page.file, []) if is_root_page else []:
            text = _without_brand(label.text, brand_words) if label.kind == kind else ""
            # A page also shows headings for its states ("Invalid link",
            # "Email sent!"). The page's name shares a word with its URL.
            if text and _about_url(text, url_words):
                names.append(AuthoredName(text, source))
    if capability:
        words = [w.capitalize() for w in re.split(r"[-_.\s]+", capability[-1]) if w]
        names.append(AuthoredName(" ".join(words), SOURCE_URL))
    return names
