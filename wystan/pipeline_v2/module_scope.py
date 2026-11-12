"""Module scope — what a nested module root means after Stage 1.

A repository can hold a module of a language in a subdirectory (a
manifest such as ``go.mod`` that is not at the repository root). An
extractor that reads that module's layout marks its anchors with the
module root (``AnchorCandidate.scope``). Three rules follow from one
fact: a module is a namespace and a unit of scale of its own.

1. A name is unique inside its module only. Two anchors with the same
   name are joined by name when they live in the same place; a unit of
   a nested module and an anchor outside that module are different
   things that happen to share a word (``<module>/internal/server``
   and a web route ``server``).
2. A declared package owns its directory. When a manifest-declared
   package (a workspace package, a crate) already claims every file of
   a nested-module unit, the unit is the inside of that package, not a
   feature beside it, and it is not emitted a second time.
3. Size is judged among peers. "Oversized" is measured against the
   other rows of the same nested module, and the rows outside every
   nested module are measured among themselves, so that adding a large
   module never changes what is oversized elsewhere.

Anchors with ``scope == ""`` (everything read from the repository
root) are untouched by all three rules: with no nested module in a
repository every function here returns its input unchanged.

Pure path arithmetic. No file is read, no model is called.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence

from wystan.pipeline_v2.extractors._module_roots import (
    REPOSITORY_ROOT,
    ModuleLocator,
    first_free_name,
    qualified_unit_names,
)
from wystan.pipeline_v2.extractors.base import AnchorCandidate
from wystan.pipeline_v2.extractors.go_packages import (
    nested_module_roots as _go_module_roots,
)

# Every extractor that reads a layout from nested module roots lists
# its root finder here, so the stages that judge size see the same
# modules the extractors named units in.
_NESTED_ROOT_FINDERS = (_go_module_roots,)


def _is_under(path: str, directory: str) -> bool:
    """``True`` when ``path`` is ``directory`` or lies below it."""
    return path == directory or path.startswith(directory + "/")


def _common_dir(paths: Sequence[str]) -> str | None:
    """Deepest directory that holds every path; ``None`` for no paths.

    The lexicographically smallest and largest path bound all others,
    so their shared leading segments are shared by every path.
    """
    if not paths:
        return None
    low, high = min(paths).split("/")[:-1], max(paths).split("/")[:-1]
    shared: list[str] = []
    for left, right in zip(low, high):
        if left != right:
            break
        shared.append(left)
    return "/".join(shared)


# ── Rule 1: names are joined only inside one scope ──────────────────────────


class ScopeGuard:
    """Answers "may these two candidates be joined because of a name?"."""

    def __init__(self, candidates: Sequence[AnchorCandidate]) -> None:
        self._scopes = [c.scope for c in candidates]
        # Computed once per candidate: the pair loop of Stage 2 is
        # quadratic and must stay a few comparisons per pair.
        self._homes = [_common_dir(c.paths) for c in candidates]
        self.is_active = any(self._scopes)

    def _lives_in(self, index: int, scope: str) -> bool:
        own = self._scopes[index]
        if own and _is_under(own, scope):
            return True
        home = self._homes[index]
        return home is not None and _is_under(home, scope)

    def are_apart(self, left: int, right: int) -> bool:
        """``True`` when a shared name says nothing about this pair.

        Candidates of one scope are never apart (that is every pair of
        a repository without nested modules). Otherwise each nested
        scope must contain the other candidate: a route or a declared
        package that lives inside the module is the same thing as the
        module's unit of that name, an anchor elsewhere is not.
        """
        scope_left, scope_right = self._scopes[left], self._scopes[right]
        if scope_left == scope_right:
            return False
        if scope_left and not self._lives_in(right, scope_left):
            return True
        return bool(scope_right) and not self._lives_in(left, scope_right)


def qualify_shared_names(
    groups: Sequence[Sequence[AnchorCandidate]], names: Sequence[str],
) -> list[str]:
    """Feature names with nested-module duplicates told apart.

    Stage 2 feature names must be unique. Groups kept apart by
    :class:`ScopeGuard` can end with one name; every such group that
    consists of nested-module units only takes its module's name in
    front (``<module>-<unit>``, then the module path, then a number).
    A group with an anchor read from the repository root keeps the bare
    name: that is the name it had before nested modules were read.
    """
    shared = Counter(names)
    out = list(names)
    contested = [
        index for index, group in enumerate(groups)
        if shared[names[index]] > 1 and all(c.scope for c in group)
    ]
    if not contested:
        return out
    taken = set(names)
    next_ordinal: dict[str, int] = {}
    # Sorted by (module, name) so the outcome does not depend on the
    # order Stage 1 listed the candidates in.
    for index in sorted(
        contested, key=lambda i: (min(c.scope for c in groups[i]), names[i]),
    ):
        scope = min(c.scope for c in groups[index])
        name = first_free_name(
            qualified_unit_names(scope, names[index]), taken, next_ordinal,
        )
        out[index] = name
        taken.add(name)
    return out


# ── Rule 2: a declared package owns its directory ───────────────────────────


def drop_units_inside_declared_packages(
    candidates: list[AnchorCandidate], declared_sources: frozenset[str],
) -> tuple[list[AnchorCandidate], list[str]]:
    """Remove nested-module units a declared package claims whole.

    ``declared_sources`` are the Stage 1 sources that read a package
    from its manifest. Returns ``(kept, dropped names)``; the input
    list is returned as is when nothing is dropped.

    Only the whole-unit case is handled here. A unit that keeps at
    least one file of its own goes on to Stage 2's ordinary attribution,
    where the declared package wins the shared files by priority.
    """
    if not any(c.scope for c in candidates):
        return candidates, []
    claims = [
        frozenset(c.paths) for c in candidates
        if c.source in declared_sources and not c.scope and c.paths
    ]
    if not claims:
        return candidates, []
    kept: list[AnchorCandidate] = []
    dropped: list[str] = []
    for cand in candidates:
        if cand.scope and cand.paths and any(
            claim.issuperset(cand.paths) for claim in claims
        ):
            dropped.append(cand.name)
        else:
            kept.append(cand)
    if not dropped:
        return candidates, []
    return kept, sorted(dropped)


# ── Rule 3: size is judged among the rows of one module ─────────────────────


def nested_module_roots(tracked_files: Iterable[str]) -> frozenset[str]:
    """Roots of every nested module an extractor reads a layout from."""
    files = list(tracked_files)
    roots: set[str] = set()
    for find in _NESTED_ROOT_FINDERS:
        roots.update(find(files))
    return frozenset(roots)


def grain_scopes(
    owned_paths: Sequence[Sequence[str]], module_roots: Iterable[str],
) -> list[str]:
    """Per row: the nested module that holds all its files, else ``""``.

    ``owned_paths[i]`` are the files row ``i`` owns. A row belongs to a
    nested module only when every file it owns is inside it; a row that
    reaches outside (or owns nothing) is measured with the rest of the
    repository, exactly as before nested modules were read. With no
    nested module every row gets ``""``.
    """
    locator = ModuleLocator(set(module_roots) - {REPOSITORY_ROOT})
    scopes: list[str] = []
    for paths in owned_paths:
        scopes.append(_enclosing_module(paths, locator))
    return scopes


def _enclosing_module(paths: Sequence[str], locator: ModuleLocator) -> str:
    """Outermost nested module root that contains every path."""
    home = _common_dir(paths)
    if home is None:
        return REPOSITORY_ROOT
    chain = locator.enclosing(home)
    return chain[0] if chain else REPOSITORY_ROOT


__all__ = [
    "ScopeGuard",
    "drop_units_inside_declared_packages",
    "grain_scopes",
    "nested_module_roots",
    "qualify_shared_names",
]
