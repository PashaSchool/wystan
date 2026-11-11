"""Attach RPC router code to the product features that call it.

A tRPC router package is laned as transport plumbing, and its developer
features (``document-router``, ``template-router`` …) end up outside the
product. They are the server half of the product's capabilities: a page flow
calls ``trpc.template.create.useMutation()`` and the procedure in
``template-router`` runs.

Flow expansion records those calls as ``rpc`` edges
(:mod:`wystan.pipeline_v2.flow_expansion.trpc_edges`). This pass uses them as
ownership evidence: a developer feature without a product feature is attached
to the product feature whose flows hold a strict plurality of the ``rpc``
edges into its files. No edge, or a tie, leaves the feature where it is.

Deterministic, no LLM. Runs after the transport handoff, before LoC
accounting, so the moved membership is counted by the normal passes.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import TYPE_CHECKING, Any

from wystan.pipeline_v2.overturn_ledger import propose_pf

if TYPE_CHECKING:  # pragma: no cover
    from wystan.models.types import Feature, Flow

__all__ = ["RPC_CALLER_NOTE", "rehome_rpc_called_devs"]

#: Provenance note stamped on re-homed features (``Feature.anchor_id``).
RPC_CALLER_NOTE = "fold:rpc-callers"
_RPC_EDGE_KIND = "rpc"
_SAMPLE_LIMIT = 20


def _file_of(node_id: str) -> str:
    return node_id.split("#", 1)[0]


def _rpc_votes(
    flows: list["Flow"],
    owner_of_file: dict[str, str],
    pf_of_feature: dict[str, str | None],
) -> dict[str, Counter]:
    """``unowned feature -> Counter(product feature -> rpc edges)``."""
    votes: dict[str, Counter] = defaultdict(Counter)
    for flow in flows:
        caller_pf = pf_of_feature.get(flow.primary_feature or "")
        if not caller_pf:
            continue
        for edge in flow.edges or []:
            if edge.kind != _RPC_EDGE_KIND:
                continue
            target_feature = owner_of_file.get(_file_of(edge.to))
            if target_feature is not None:
                votes[target_feature][caller_pf] += 1
    return votes


def rehome_rpc_called_devs(
    features: list["Feature"],
    product_features: list["Feature"],
    flows: list["Flow"],
) -> dict[str, Any]:
    """Attach unowned developer features to the product feature that calls
    their RPC procedures. Mutates ``product_feature_id`` / ``anchor_id`` /
    ``shared_reason`` in place and returns telemetry."""
    tele: dict[str, Any] = {"checked": 0, "rehomed": 0, "tied": 0, "sample": []}
    known_pfs = {pf.name for pf in product_features}
    unowned = {f.name: f for f in features if not f.product_feature_id}
    owner_of_file = {
        path: name for name, feature in sorted(unowned.items()) for path in feature.paths
    }
    pf_of_feature = {f.name: f.product_feature_id for f in features}
    votes = _rpc_votes(flows, owner_of_file, pf_of_feature)
    for name in sorted(votes):
        ranked = sorted(votes[name].items(), key=lambda kv: (-kv[1], kv[0]))
        ranked = [(pf, count) for pf, count in ranked if pf in known_pfs]
        if not ranked:
            continue
        tele["checked"] += 1
        if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
            tele["tied"] += 1
            continue
        target, count = ranked[0]
        feature = unowned[name]
        propose_pf(feature, target, rung="rpc_router_rehome")
        feature.anchor_id = RPC_CALLER_NOTE
        feature.shared_reason = None
        tele["rehomed"] += 1
        if len(tele["sample"]) < _SAMPLE_LIMIT:
            tele["sample"].append({
                "dev": name, "pf": target, "rpc_edges": count,
                "total_edges": sum(votes[name].values()),
            })
    return tele
