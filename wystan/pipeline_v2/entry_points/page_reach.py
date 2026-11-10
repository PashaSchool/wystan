"""Which code a page reaches through its imports.

A page file is small: it renders components that live elsewhere. A feature
made of those components has no page file of its own, yet a user opens it
through that page. This module follows a page's imports a short distance so
such a feature can be tied to the pages that show it.

It reports reach; it decides nothing. A package every page imports (a UI
kit, a translation layer) is reached from everywhere, and the caller tells
that apart from a feature reached from one part of the product.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Iterable

from wystan.pipeline_v2.flow_expansion.span_recovery import _resolve_module

if TYPE_CHECKING:
    from wystan.pipeline_v2.flow_reach import ReachContext

__all__ = ["files_reached_from"]

_IMPORT_SPEC = re.compile(
    r"""(?:\bfrom\s+|\bimport\s*\(\s*|\brequire\s*\(\s*|^\s*import\s+)['"]([^'"\n]+)['"]""", re.M,
)
# Deep enough to see who really shares a package. Measured on plane: two hops
# found one importing page for a state package and called it that page's own;
# five hops found it under settings (19 pages) and projects (16), which is
# what it is: shared.
_MAX_HOPS = 5
_MAX_FILES_PER_PAGE = 3000


def _imports(rctx: "ReachContext", file: str) -> list[str]:
    signature = rctx.signatures.get(file)
    source = (signature.source if signature is not None else "") or ""
    found = []
    for spec in sorted(set(_IMPORT_SPEC.findall(source))):
        target = _resolve_module(rctx, file, spec)
        if target:
            found.append(target)
    return found


def files_reached_from(rctx: "ReachContext", pages: Iterable[str]) -> dict[str, frozenset[str]]:
    """``page file -> files it imports``, directly or through a few files in
    between. Bounded per page."""
    reached: dict[str, frozenset[str]] = {}
    cache: dict[str, list[str]] = {}
    for page in sorted(set(pages)):
        seen: set[str] = set()
        frontier = [page]
        for _ in range(_MAX_HOPS):
            following: list[str] = []
            for file in frontier:
                if file not in cache:
                    cache[file] = _imports(rctx, file)
                for target in cache[file]:
                    if target not in seen and target != page and len(seen) < _MAX_FILES_PER_PAGE:
                        seen.add(target)
                        following.append(target)
            frontier = following
        reached[page] = frozenset(seen)
    return reached
