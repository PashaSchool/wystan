"""Which code a page reaches through its imports.

A page file is small: it renders components that live elsewhere. A feature
made of those components has no page file of its own, yet a user opens it
through that page. This module follows a page's imports a short distance so
such a feature can be tied to the pages that show it.

It reports reach; it decides nothing. A package every page imports (a UI
kit, a translation layer) is reached from everywhere, and the caller tells
that apart from a feature reached from one part of the product.

Reach can also be missing: a stack whose imports this module cannot follow
gives every page an empty reach. ``reach_coverage`` measures that, so a
caller can tell "no page shows this code" from "we could not look".
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from wystan.analyzer.import_graph import _try_extensions
from wystan.analyzer.safe_read import safe_read_text
from wystan.pipeline_v2.flow_expansion.span_recovery import _resolve_module

if TYPE_CHECKING:
    from wystan.pipeline_v2.flow_reach import ReachContext

__all__ = ["files_reached_from", "pages_with_nothing_to_follow", "reach_coverage"]

_IMPORT_SPEC = re.compile(
    r"""(?:\bfrom\s+|\bimport\s*\(\s*|\brequire\s*\(\s*|^\s*import\s+)['"]([^'"\n]+)['"]""", re.M,
)
# Deep enough to see who really shares a package. Measured on plane: two hops
# found one importing page for a state package and called it that page's own;
# five hops found it under settings (19 pages) and projects (16), which is
# what it is: shared.
_MAX_HOPS = 5
_MAX_FILES_PER_PAGE = 3000
# A file with no parsed signature is read for its import statements only.
# Hand-written source is far below this; larger files are bundles or data.
_MAX_SOURCE_BYTES = 512 * 1024
# ``$lib/x``, ``~lib/x``: an alias is a directory name behind one sigil.
_SIGIL_ALIAS = re.compile(r"^[$~#@]([A-Za-z][\w-]*)/(.+)$")
_SOURCE_ROOT = "src"
# An import written against the repository itself: a relative path or an
# alias. ``react`` and ``@scope/package`` are somebody else's code.
_OWN_CODE_SPEC = re.compile(r"^(?:\.|[@~#]/|[$~#][A-Za-z])")


def _source_of(rctx: "ReachContext", file: str) -> str:
    """The text of ``file``. Files the signature extractor gives no record
    (a single-file component, a module that only re-exports) still carry
    import statements, and without them every import chain through such a
    file ends there."""
    signature = rctx.signatures.get(file)
    if signature is not None:
        return signature.source or ""
    if file not in rctx.file_set:
        return ""
    text = safe_read_text(
        Path(rctx.repo_path) / file, rctx.repo_path,
        errors="ignore", max_bytes=_MAX_SOURCE_BYTES,
    )
    return text or ""


def _resolve_sigil_alias(rctx: "ReachContext", importer: str, spec: str) -> str | None:
    """Resolve ``<sigil><dir>/<rest>`` against the importer's ancestors.

    Some frameworks declare their aliases in generated configuration that is
    not in the repository. The alias still names a real directory: the
    nearest ancestor of the importer holding ``<dir>/<rest>`` or
    ``src/<dir>/<rest>`` is the target. A framework's virtual module has no
    such directory and stays unresolved."""
    match = _SIGIL_ALIAS.match(spec)
    if match is None:
        return None
    tail = f"{match.group(1)}/{match.group(2)}"
    parts = importer.split("/")[:-1]
    for depth in range(len(parts), -1, -1):
        base = "/".join(parts[:depth])
        for candidate in (f"{base}/{tail}", f"{base}/{_SOURCE_ROOT}/{tail}"):
            found = _try_extensions(candidate.lstrip("/"), rctx.file_set)
            if found and found != importer:
                return found
    return None


def _imports(rctx: "ReachContext", file: str) -> list[str]:
    found = []
    for spec in sorted(set(_IMPORT_SPEC.findall(_source_of(rctx, file)))):
        target = _resolve_module(rctx, file, spec) or _resolve_sigil_alias(rctx, file, spec)
        if target:
            found.append(target)
    return found


def pages_with_nothing_to_follow(rctx: "ReachContext", pages: Iterable[str]) -> frozenset[str]:
    """Pages we could read that import no code of the repository. Their
    empty reach is a fact about the page, not a failure to follow it."""
    quiet: set[str] = set()
    for page in set(pages):
        if page not in rctx.signatures and page not in rctx.file_set:
            continue
        source = _source_of(rctx, page)
        if source and not any(_OWN_CODE_SPEC.match(spec) for spec in _IMPORT_SPEC.findall(source)):
            quiet.add(page)
    return frozenset(quiet)


def reach_coverage(
    reached: dict[str, frozenset[str]],
    pages: Iterable[str],
    nothing_to_follow: Iterable[str] = (),
) -> dict[str, Any]:
    """How many of ``pages`` reach at least one other file.

    ``coverage`` is taken over the pages that had something to follow. A
    page that imports the repository's code and reaches none of it was not
    followed; when that is most pages the reach graph is not evidence.
    ``None`` when no page had anything to follow."""
    files = set(pages)
    with_reach = {file for file in files if reached.get(file)}
    quiet = (files - with_reach) & set(nothing_to_follow)
    judged = len(files) - len(quiet)
    return {
        "pages": len(files),
        "with_reach": len(with_reach),
        "without_reach": judged - len(with_reach),
        "nothing_to_follow": len(quiet),
        "coverage": round(len(with_reach) / judged, 4) if judged else None,
    }


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
