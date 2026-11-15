"""Rule S2: nothing is re-homed across module scopes.

A nested module is a separate program. A pass that moves a journey from
one product feature to another by evidence that is not the journey's own
code (name tokens, path shares, similarity) reads every product feature
of the scan as a possible home. Measured on a repository with three
nested modules: such passes moved 13..19 journeys per scan between a
feature of the repository and a feature of a module (and back, and
between two modules), because a module feature named ``agent`` shares a
word with the repository's agent journeys. The repository row they left
was then judged without them.

So such a pass takes as targets only the product features of the moved
journey's own scope. For a repository journey the pass then decides
exactly as it would if no nested module had been read: same candidates,
same scores, same tie-breaks, same order. A journey with no target left
in its scope stays where it is, as when the pass finds no target.

Scopes are those of rule S1 (:mod:`request_scopes`): a journey is in the
scope of the files of its member flows, a product feature in the scope of
its own files and its developer rows' files, a developer row in the scope
of its files; anything spanning scopes, or with no file, is in the root
scope. With no nested module every item is in the root scope and every
function here gives the pass its input unchanged.

Pure: no file is read, no model is called.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, TypeVar

from wystan.pipeline_v2.module_scope import ModuleScopes
from wystan.pipeline_v2.request_scopes import (
    REPOSITORY_ROOT,
    feature_scopes,
    scopes_of_items,
)

ValueT = TypeVar("ValueT")

__all__ = [
    "REPOSITORY_ROOT",
    "flow_files",
    "journey_scopes",
    "product_feature_scopes",
    "row_scopes",
    "targets_in_scope",
]


def flow_files(flow: Any) -> list[str]:
    """Every file a flow touches: its paths and its entry file.

    The same files the name writer reads a journey's scope from
    (``product_language_names._member_files``), so a journey is in one
    scope for the requests about it and for the passes that move it.
    """
    files = list(getattr(flow, "paths", None) or [])
    entry = getattr(flow, "entry_point_file", None)
    if entry:
        files.append(str(entry))
    return files


def journey_scopes(
    user_flows: Sequence[Any],
    flow_by_id: Mapping[str, Any],
    module_scopes: ModuleScopes | None,
) -> dict[int, str]:
    """``{id(journey): scope}`` from the files of the journey's member flows.

    Keyed by object identity: journey ids are unique in a finished map,
    but a pass may run while two drafts still share one.
    """
    if not module_scopes:
        return {id(uf): REPOSITORY_ROOT for uf in user_flows}
    files_per_journey = [
        [path for member in (getattr(uf, "member_flow_ids", None) or [])
         if (flow := flow_by_id.get(member)) is not None
         for path in flow_files(flow)]
        for uf in user_flows
    ]
    scopes = scopes_of_items(files_per_journey, module_scopes)
    return {id(uf): scope for uf, scope in zip(user_flows, scopes)}


def product_feature_scopes(
    product_features: Iterable[Any],
    developer_features: Iterable[Any],
    module_scopes: ModuleScopes | None,
) -> dict[str, str]:
    """``{product feature name: scope}`` (rule S1's :func:`feature_scopes`)."""
    developers = [
        d for d in developer_features
        if getattr(d, "layer", "developer") == "developer"
    ]
    return feature_scopes(product_features, developers, module_scopes)


def row_scopes(
    developer_features: Sequence[Any], module_scopes: ModuleScopes | None,
) -> dict[int, str]:
    """``{id(developer row): scope}`` from the files each row owns."""
    scopes = scopes_of_items(
        [list(getattr(d, "paths", None) or []) for d in developer_features],
        module_scopes,
    )
    return {id(d): scope for d, scope in zip(developer_features, scopes)}


def targets_in_scope(
    targets: Mapping[str, ValueT], scope_of_target: Callable[[str], str], scope: str,
) -> Mapping[str, ValueT]:
    """The targets of one scope, in their given order.

    Returns ``targets`` itself when every target is in ``scope`` (always so
    without a nested module), so a pass with nothing to leave out reads the
    very mapping it read before this rule.
    """
    kept = {key: value for key, value in targets.items() if scope_of_target(key) == scope}
    if len(kept) == len(targets):
        return targets
    return kept
