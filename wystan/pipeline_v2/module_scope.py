"""Module scope — what a nested module root means after Stage 1.

A repository can hold a module of a language in a subdirectory (a
manifest such as ``go.mod`` that is not at the repository root). An
extractor that reads that module's layout marks the anchors it could
not have produced from the repository root with the module root
(``AnchorCandidate.scope``). Three rules follow from one fact: a module
is a namespace and a unit of scale of its own.

1. A name is unique inside its module only. Two anchors are joined
   by name when they were read from the same root; a unit of a nested
   module and any other anchor are different things that happen to
   share a word (``<module>/internal/server`` and a web route
   ``server``; the unit ``<module>-auth`` and the module's own root
   package ``<module>``).
2. The nested rule only adds. A file that an anchor read without it
   already claims stays with that anchor, whatever the priorities: the
   nested unit gives the file up, and a unit left with no file is not
   emitted (a unit inside a declared workspace package, a unit whose
   only file is a route file). So Stage 2 builds every row the
   repository had from exactly the anchors, names and files it had.
3. Size and flow names are judged among peers. "Oversized" is measured
   against the other rows of the same module scope, and flow names are
   told apart inside it. The ruler is computed here and nowhere else
   (:func:`grain_rulers`): four stages each held a copy of the formula.

Who is in a scope. Only the rows that exist BECAUSE a nested module was
read: rows Stage 2 built from scoped anchors alone. A row that would be
emitted without the nested rule — the root package of a top-level
module, a route inside a module, anything read from the repository
root — stays with the repository even when every file it owns lies
inside a module directory. That cannot be told from paths, so Stage 2,
which has the anchors, records it (:func:`record_module_scopes`) and
later stages read the record (:class:`ModuleScopes`). A row of the
residual stage is made of files no anchor claimed, so it is a row the
repository had too: the orchestrator adds its files to the record
(:func:`with_older_rows`). The consequence
is the guarantee the rules exist for: the rows a repository had before
its nested module was read keep their ruler, their flow names and so
their flow ids.

With no scoped anchor the record is empty and every function here
returns its input unchanged.

Pure path arithmetic. No file is read, no model is called.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace

from wystan.pipeline_v2.extractors._module_roots import (
    REPOSITORY_ROOT,
    ModuleLocator,
    first_free_name,
    qualified_unit_names,
)
from wystan.pipeline_v2.extractors.base import AnchorCandidate


def _is_under(path: str, directory: str) -> bool:
    """``True`` when ``path`` is ``directory`` or lies below it."""
    return path == directory or path.startswith(directory + "/")


def _parent_dir(path: str) -> str:
    """Directory part of a POSIX path (``""`` for a top-level entry)."""
    return path.rpartition("/")[0]


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
        self.is_active = any(self._scopes)

    def are_apart(self, left: int, right: int) -> bool:
        """``True`` when a shared name says nothing about this pair.

        Names join candidates read from the same root only: two anchors
        of the repository (every pair of a repository without nested
        modules), or two units of one nested module. A nested unit and
        an anchor the repository had before are kept apart even when
        the anchor lies inside the module's directory: joined, the older
        row would grow by the unit's files and stop being the row it
        was (its flows, and so their ids, are made from its files).
        """
        return self._scopes[left] != self._scopes[right]


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
        if shared[names[index]] > 1 and group_scope(group)
    ]
    if not contested:
        return out
    taken = set(names)
    next_ordinal: dict[str, int] = {}
    # Sorted by (module, name) so the outcome does not depend on the
    # order Stage 1 listed the candidates in.
    for index in sorted(
        contested, key=lambda i: (group_scope(groups[i]), names[i]),
    ):
        scope = group_scope(groups[index])
        name = first_free_name(
            qualified_unit_names(scope, names[index]), taken, next_ordinal,
        )
        out[index] = name
        taken.add(name)
    return out


# ── Rule 2: the nested rule only adds ───────────────────────────────────────


def leave_claimed_files(
    candidates: list[AnchorCandidate],
) -> tuple[list[AnchorCandidate], list[str]]:
    """Take from nested-module units the files another anchor claims.

    "Another anchor" is any candidate read without the nested rule
    (``scope == ""``). Returns ``(candidates, names of the units left
    with no file and dropped)``; the input list is returned as is when
    no nested unit shares a file.

    Done before the merge, so that no shared file joins a nested unit
    to an older anchor and no priority moves a file between them.
    """
    if not any(c.scope for c in candidates):
        return candidates, []
    claimed = {path for c in candidates if not c.scope for path in c.paths}
    kept: list[AnchorCandidate] = []
    dropped: list[str] = []
    changed = False
    for cand in candidates:
        own = cand.paths
        if cand.scope:
            own = tuple(path for path in cand.paths if path not in claimed)
        if len(own) == len(cand.paths):
            kept.append(cand)
            continue
        changed = True
        if own:
            kept.append(replace(cand, paths=own))
        else:
            dropped.append(cand.name)
    if not changed:
        return candidates, []
    return kept, sorted(dropped)


# ── Who is in a scope: recorded by Stage 2, read by every later stage ───────


@dataclass(frozen=True)
class ModuleScopes:
    """Which rows of a scan belong to a nested module, as file sets.

    Rows are split, merged and re-homed after Stage 2, so the record is
    kept per file, not per row name.
    """

    # Module root -> files owned, at the end of Stage 2, by the rows
    # built from that module's scoped anchors alone (the new rows).
    new_files: Mapping[str, frozenset[str]] = field(default_factory=dict)
    # Files inside those module roots owned by a row the nested rule
    # did not create: a Stage 2 row read without it, or a row of the
    # residual stage (:func:`with_older_rows`). A row holding one of
    # them is an older row, whatever else it holds.
    old_files: frozenset[str] = frozenset()

    def __bool__(self) -> bool:
        return bool(self.new_files)


NO_MODULE_SCOPES = ModuleScopes()


def group_scope(group: Sequence[AnchorCandidate]) -> str:
    """Module scope of a Stage 2 merge group; ``""`` when it has none.

    A group is a new row only when EVERY anchor in it was read by a
    nested rule. One anchor read from the repository root makes it a
    row the repository had anyway (now holding more files). Scopes
    nested in one another resolve to the outermost.
    """
    if not group or not all(c.scope for c in group):
        return REPOSITORY_ROOT
    return min(c.scope for c in group)


def record_module_scopes(
    rows: Iterable[tuple[str, Sequence[str]]],
    scope_by_name: Mapping[str, str],
) -> ModuleScopes:
    """The scan's :class:`ModuleScopes`, from the final Stage 2 rows.

    ``rows`` are ``(name, owned files)`` of every feature Stage 2
    returns; ``scope_by_name`` gives :func:`group_scope` of the group a
    feature was built from, for the features that have one. A new row
    that ended with a file outside its module is not recorded: it is
    measured with the repository, like any row that spans both.
    """
    if not any(scope_by_name.values()):
        return NO_MODULE_SCOPES
    rows = list(rows)
    new_files: dict[str, set[str]] = {}
    for name, paths in rows:
        scope = scope_by_name.get(name, REPOSITORY_ROOT)
        if scope and paths and all(_is_under(path, scope) for path in paths):
            new_files.setdefault(scope, set()).update(paths)
    if not new_files:
        return NO_MODULE_SCOPES
    scopes = ModuleScopes(
        new_files={root: frozenset(new_files[root]) for root in sorted(new_files)},
    )
    return _add_older_files(scopes, [paths for _name, paths in rows])


def _files_inside_modules(
    owned_paths: Iterable[Sequence[str]], module_scopes: ModuleScopes,
) -> set[str]:
    """The files of ``owned_paths`` that lie under a recorded module root
    and are not a file of a new row.

    Each file's directory is resolved through one :class:`ModuleLocator`
    (an ancestor walk, remembered per directory), so the cost is linear
    in the files and their distinct directories and does not grow with
    the number of modules: a repository with thousands of manifests is
    not files x modules.
    """
    locator = ModuleLocator(module_scopes.new_files)
    recorded = {
        path for files in module_scopes.new_files.values() for path in files
    }
    return {
        path
        for paths in owned_paths for path in paths
        if path not in recorded and locator.enclosing(_parent_dir(path))
    }


def with_older_rows(
    module_scopes: ModuleScopes | None,
    owned_paths: Iterable[Sequence[str]],
) -> ModuleScopes | None:
    """The record, with the files of rows the nested rule did not create.

    ``owned_paths`` are the files of such rows: every Stage 2 row when
    the record is first written (the files of new rows are skipped),
    and later the rows of the residual stage. A residual row is made of
    files no anchor claimed, so the repository had it before nested
    modules were read; without this, merged later with a new row, it
    would pass for a row of the module (it holds a new file and no file
    of an older Stage 2 row) and lose the repository's ruler and flow
    names. An empty record, or rows with no file inside a module, give
    the input back.
    """
    if not module_scopes:
        return module_scopes
    return _add_older_files(module_scopes, owned_paths)


def _add_older_files(
    module_scopes: ModuleScopes, owned_paths: Iterable[Sequence[str]],
) -> ModuleScopes:
    older = _files_inside_modules(owned_paths, module_scopes)
    if older <= module_scopes.old_files:
        return module_scopes
    return replace(module_scopes, old_files=module_scopes.old_files | older)


# ── Rule 3: size is judged among the rows of one module scope ───────────────


def grain_scopes(
    owned_paths: Sequence[Sequence[str]], module_scopes: ModuleScopes | None,
) -> list[str]:
    """Per row: the module scope it belongs to, else ``""``.

    ``owned_paths[i]`` are the files row ``i`` owns. With no record
    (``None`` or empty: no nested module was read) every row gets ``""``.
    """
    if not module_scopes:
        return [REPOSITORY_ROOT] * len(owned_paths)
    # One locator for all rows: it remembers every directory it resolved.
    locator = ModuleLocator(module_scopes.new_files)
    return [_row_scope(paths, module_scopes, locator) for paths in owned_paths]


def _row_scope(
    paths: Sequence[str], module_scopes: ModuleScopes, locator: ModuleLocator,
) -> str:
    """The module scope of a row that owns ``paths``; ``""`` for none.

    A row is in module M when every file it owns lies under M, at least
    one of them is a file of M's new rows, and none is a file of an
    older row. The outermost such module wins. Anything else — a row
    reaching outside the module, an older row inside it, a row that
    owns nothing — is a row of the repository.
    """
    home = _common_dir(paths)
    if home is None:
        return REPOSITORY_ROOT
    if any(path in module_scopes.old_files for path in paths):
        return REPOSITORY_ROOT
    for root in locator.enclosing(home):
        new = module_scopes.new_files[root]
        if any(path in new for path in paths):
            return root
    return REPOSITORY_ROOT


# A row is oversized when it owns more than this share of the files its
# peers own together…
_OVERSIZED_SHARE = 0.15
# …or more than this many times the median row. The same factor says
# when a row is sparse: below the peers' median divided by it.
_OVERSIZED_MEDIAN_MULT = 2
# The median is never taken below this: where most rows own one file,
# a row of two is not twice the grain of anything.
_MIN_MEDIAN_FILES = 2


@dataclass(frozen=True)
class GrainRuler:
    """What "oversized" means among one group of rows."""

    median: int  # median files owned by a row that owns any
    cut: int     # a row owning more files than this is oversized
    peers: int   # rows in the group, including rows that own nothing


def measure_grain(owned_paths: Sequence[Sequence[str]]) -> GrainRuler | None:
    """Ruler of one group of rows; ``None`` when no row owns a file.

    A file two rows both own counts once in the total.
    """
    sizes = [len(paths) for paths in owned_paths if paths]
    if not sizes:
        return None
    median = max(_MIN_MEDIAN_FILES, int(statistics.median(sizes)))
    total_owned = len({path for paths in owned_paths for path in paths})
    cut = max(
        _OVERSIZED_MEDIAN_MULT * median,
        math.ceil(_OVERSIZED_SHARE * total_owned),
    )
    return GrainRuler(median=median, cut=cut, peers=len(owned_paths))


def _measuring_scopes(
    owned_paths: Sequence[Sequence[str]], module_scopes: ModuleScopes | None,
) -> tuple[list[str], list[str]]:
    """``(own scope, scope whose rows are the yardstick)`` per row.

    The two differ for a nested module too small to have a grain of its
    own: one whose files, taken together, would not be an oversized row
    of the repository. Seen from the repository such a module is one
    ordinary row, and a ruler made of its few rows cuts it finer than
    anything around it (a module of 300 files beside 2,600 was split at
    47 files while the repository split at 396). Its rows are therefore
    measured by the repository's ruler. The threshold is the
    repository's own cut, not a new number.

    The repository's ruler is made of the rows outside every module
    scope only — the rows the repository has without its nested
    modules — so no module, small or large, ever moves it.
    """
    scopes = grain_scopes(owned_paths, module_scopes)
    if not any(scopes):
        return scopes, scopes
    files_in: dict[str, set[str]] = {}
    for paths, scope in zip(owned_paths, scopes):
        files_in.setdefault(scope, set()).update(paths)
    repository = measure_grain(
        [p for p, scope in zip(owned_paths, scopes) if scope == REPOSITORY_ROOT],
    )
    if repository is None:
        return scopes, scopes
    yardsticks = [
        REPOSITORY_ROOT if len(files_in[scope]) <= repository.cut else scope
        for scope in scopes
    ]
    return scopes, yardsticks


def grain_rulers(
    owned_paths: Sequence[Sequence[str]], module_scopes: ModuleScopes | None,
) -> list[GrainRuler | None]:
    """Per row: the ruler it is measured by (``None``: nothing to measure).

    ``owned_paths[i]`` are the files row ``i`` owns. Without a module
    scope every row gets the one ruler of the whole list, which is the
    formula each stage used to compute for itself.
    """
    scopes, yardsticks = _measuring_scopes(owned_paths, module_scopes)
    rows_of: dict[str, list[Sequence[str]]] = {}
    for paths, scope in zip(owned_paths, scopes):
        rows_of.setdefault(scope, []).append(paths)
    ruler_of = {scope: measure_grain(rows) for scope, rows in rows_of.items()}
    return [ruler_of[scope] for scope in yardsticks]


def peer_medians(
    values: Sequence[float | None],
    owned_paths: Sequence[Sequence[str]],
    module_scopes: ModuleScopes | None,
) -> list[float]:
    """Per row: the median of ``values`` among the rows it is measured by.

    ``values[i]`` is ``None`` for a row that has no value (it is still
    given its peers' median). ``0.0`` where no peer has a value.
    """
    scopes, yardsticks = _measuring_scopes(owned_paths, module_scopes)
    values_of: dict[str, list[float]] = {}
    for value, scope in zip(values, scopes):
        if value is not None:
            values_of.setdefault(scope, []).append(value)
    median_of = {
        scope: statistics.median(found) for scope, found in values_of.items()
    }
    return [median_of.get(scope, 0.0) for scope in yardsticks]


def sparse_below(peer_median: float) -> float:
    """The value under which a row is sparse beside its peers."""
    return peer_median / _OVERSIZED_MEDIAN_MULT


# ── Rule 3, continued: product breadth is counted among possible users ──────


@dataclass(frozen=True)
class ProductBreadth:
    """How many product features a shared file is measured against.

    "Shared by a fair part of the product" is a share of the product
    features. A feature made only of a nested module's new rows cannot
    use a file outside that module, so it is not part of the product
    such a file is shared across: counted, it raises the bar for every
    other file of the repository by the number of packages the module
    happens to have.
    """

    total: int
    # Module root -> product features whose every row is a new row of it.
    module_only: Mapping[str, int] = field(default_factory=dict)

    # One locator for every file asked about: it remembers each directory
    # it resolved, so the cost does not grow with files x modules.
    _locator: ModuleLocator = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_locator", ModuleLocator(self.module_only))

    def around(self, path: str) -> int:
        """The breadth for the file at ``path``: every product feature
        except those wholly inside a module that does not hold it."""
        if not self.module_only:
            return self.total
        home = set(self._locator.enclosing(_parent_dir(path)))
        elsewhere = sum(
            count for root, count in self.module_only.items() if root not in home
        )
        return self.total - elsewhere


def product_breadth(
    total: int,
    rows_of_feature: Mapping[str, Sequence[Sequence[str]]],
    module_scopes: ModuleScopes | None,
) -> ProductBreadth:
    """The scan's :class:`ProductBreadth`.

    ``total`` is the number of product features; ``rows_of_feature``
    gives, per product feature, the files each of its developer rows
    owns. A feature with no row, or with rows in two scopes, belongs to
    the repository. With no record every file is measured against
    ``total``, as before nested modules were read.
    """
    if not module_scopes:
        return ProductBreadth(total)
    module_only: Counter[str] = Counter()
    for feature in sorted(rows_of_feature):
        scopes = set(grain_scopes(rows_of_feature[feature], module_scopes))
        if len(scopes) == 1 and REPOSITORY_ROOT not in scopes:
            module_only[scopes.pop()] += 1
    return ProductBreadth(total, dict(sorted(module_only.items())))


__all__ = [
    "NO_MODULE_SCOPES",
    "GrainRuler",
    "ModuleScopes",
    "ProductBreadth",
    "ScopeGuard",
    "grain_rulers",
    "grain_scopes",
    "group_scope",
    "leave_claimed_files",
    "measure_grain",
    "peer_medians",
    "product_breadth",
    "qualify_shared_names",
    "record_module_scopes",
    "sparse_below",
    "with_older_rows",
]
