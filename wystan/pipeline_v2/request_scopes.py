"""Rule S1: a model request never mixes module scopes.

A nested module is a separate program. A model asked about several items
at once judges each item beside the others: measured on a repository with
three nested modules, the journey name writer declined 41..43 % of the
journeys outside the modules when they shared batches with module
journeys, against 7..19 % without, and the demotion veto changed its
verdict on outside features asked beside 27..29 module features.

So every request that lists or judges several items is composed per
module scope: the items of the repository (the root scope) in requests
of their own, composed exactly as they were before any nested module was
read (same items, same order, same batch boundaries, a context list of
root items only), and the items of each nested module in requests of
their own. Nothing here decides anything about an item; it only says
which request an item is asked in.

An item belongs to the scope of the files it is made of
(:func:`module_scope.grain_scopes`: every file inside one module, at least
one of them a file of that module's new rows, none a file of an older
row). An item whose files span scopes, or that has no file, belongs to the
root scope. With no nested module every item is in the root scope and
each request is the request the engine sent before this rule.

Pure: no file is read, no model is called.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, TypeVar

from wystan.pipeline_v2.extractors._module_roots import REPOSITORY_ROOT
from wystan.pipeline_v2.module_scope import ModuleScopes, grain_scopes

ItemT = TypeVar("ItemT")

# How telemetry writes the root scope ("" is the record's own value, which
# reads as nothing in a report).
ROOT_SCOPE_LABEL = "(root)"

__all__ = [
    "REPOSITORY_ROOT",
    "ROOT_SCOPE_LABEL",
    "feature_scopes",
    "group_by_scope",
    "scope_lookup",
    "scope_label",
    "scope_of_files",
    "scoped_product_name",
]


def scope_of_files(
    paths: Iterable[str], module_scopes: ModuleScopes | None,
) -> str:
    """The module scope of an item made of ``paths``; ``""`` for the root."""
    if not module_scopes:
        return REPOSITORY_ROOT
    return grain_scopes([list(dict.fromkeys(paths))], module_scopes)[0]


def feature_scopes(
    product_features: Iterable[Any],
    developer_features: Iterable[Any],
    module_scopes: ModuleScopes | None,
) -> dict[str, str]:
    """``{product feature slug: scope}``.

    A product feature is made of its own files and the files of the
    developer features under it: the same files the requests about it
    show the model (``demotion_veto._candidate_row``, ``feature_names._row``).
    """
    features = list(product_features)
    if not module_scopes:
        return {f.name: REPOSITORY_ROOT for f in features}
    files: dict[str, list[str]] = {f.name: list(f.paths or []) for f in features}
    for dev in developer_features:
        home = getattr(dev, "product_feature_id", None)
        if home in files:
            files[home].extend(dev.paths or [])
    return {name: scope_of_files(paths, module_scopes) for name, paths in files.items()}


def group_by_scope(
    items: Sequence[ItemT], scope_of: Callable[[ItemT], str],
) -> list[tuple[str, list[ItemT]]]:
    """``[(scope, items of that scope in their given order)]``.

    The root scope comes first, then the nested modules by path, so the
    root requests are sent first as they were before. Scopes with no item
    are left out; no items give ``[]``.
    """
    groups: dict[str, list[ItemT]] = {}
    for item in items:
        groups.setdefault(scope_of(item), []).append(item)
    return [(scope, groups[scope]) for scope in sorted(groups)]


def scoped_product_name(product: str, scope: str) -> str:
    """What a request calls the product: the product, and for a nested
    module's request also the module (its root path, as the scope record
    holds it). The root scope keeps the product's name unchanged."""
    if scope == REPOSITORY_ROOT:
        return product
    return f"{product}, module {scope}"


def scope_lookup(
    scopes: Mapping[str, str],
) -> Callable[[str], str]:
    """``scopes.get`` with the root scope for an unknown key."""
    return lambda key: scopes.get(key, REPOSITORY_ROOT)


def scope_label(scope: str) -> str:
    """The scope as telemetry writes it."""
    return scope or ROOT_SCOPE_LABEL
