"""What each finalize pass reads and writes, and a check of their order.

``phase_finalize.run_finalize_phase`` runs its passes in the order of its
lines. Nothing in that function says which pass still changes a journey's
parent after a given point, and three defects came from exactly that: a pass
read a fact that a later pass rewrote. This module states, per pass, the
facets of the product layer it reads and writes, and checks the declared
order for a read that a later pass makes stale.

It runs nothing. ``FINALIZE_PASSES`` mirrors the call order in
``phase_finalize.py`` (a test compares the two) and the checker is a set of
pure functions over it. A runner that executes the list is a later step.

How the descriptors were obtained: for every pass the function it calls and
the same-module functions that function reaches were scanned, comments and
docstrings removed, for assignments to and uses of the fields behind each
facet. Writes of ``product_feature_id`` were compared with the writers the
overturn ledger recorded on 19 corpus scans. Where the scan could not tell a
developer feature from a journey the descriptor says so in a comment. A read
means "the pass's code uses the field", which over-reports: a use in a log
line counts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping

__all__ = [
    "FINALIZE_PASSES",
    "Facet",
    "FinalizePass",
    "StaleRead",
    "final_writers",
    "stale_reads",
    "unread_writes",
]


class Facet(str, Enum):
    """A property of the product layer that passes agree or disagree about."""

    FEATURE_SET = "feature.set"
    """Which developer and product features exist."""
    FEATURE_FILES = "feature.files"
    """A feature's ``paths`` and ``member_files``: ownership is voted by file."""
    FEATURE_OWNERSHIP = "feature.ownership"
    """``product_feature_id`` of developer features."""
    FLOW_SET = "flow.set"
    """Which flows exist."""
    FLOW_OWNERSHIP = "flow.ownership"
    """A flow's developer feature (``primary_feature``, ``Feature.flows``)."""
    JOURNEY_SET = "journey.set"
    """Which user flows exist."""
    JOURNEY_MEMBERSHIP = "journey.membership"
    """``member_flow_ids`` and its mirror ``Flow.user_flow_id``."""
    JOURNEY_PARENT = "journey.parent"
    """A user flow's ``product_feature_id``."""
    NAMES_PRODUCT = "names.product"
    """Display names, name confidence and evidence of features and journeys."""
    METRICS_LOC = "metrics.loc"
    """Line counts on any entity."""
    METRICS_HISTORY = "metrics.history"
    """Commit-derived metrics."""


@dataclass(frozen=True)
class FinalizePass:
    """One call in the finalize phase."""

    name: str
    """Unique label: the function name, ``#n`` for its n-th call."""
    call: str
    """``module.function`` under ``wystan.pipeline_v2`` that the phase calls."""
    reads: frozenset[Facet]
    writes: frozenset[Facet]
    calls_model: bool = False
    """Set by hand: the passes ``phase_finalize`` hands a model client or a
    model-backed callable."""
    early_reads: Mapping[Facet, str] = field(default_factory=dict)
    """Facet -> why reading it before its last writer is intended."""


@dataclass(frozen=True)
class StaleRead:
    """``reader`` reads ``facet`` and passes after it still write it."""

    reader: str
    facet: Facet
    later_writers: tuple[str, ...]

    @property
    def last_writer(self) -> str:
        return self.later_writers[-1]


def _pass(
    name: str,
    call: str,
    *,
    reads: Iterable[Facet],
    writes: Iterable[Facet],
    calls_model: bool = False,
    early_reads: Mapping[Facet, str] | None = None,
) -> FinalizePass:
    return FinalizePass(
        name=name, call=call, reads=frozenset(reads), writes=frozenset(writes),
        calls_model=calls_model, early_reads=dict(early_reads or {}),
    )


def stale_reads(passes: Iterable[FinalizePass]) -> list[StaleRead]:
    """Every read of a facet that a later pass writes, unless the reader
    declares the read early by design. One row per reader and facet, with the
    later writers in order. A pass that writes the facet it reads is still
    reported when someone writes it after: its own write is not the last."""
    ordered = list(passes)
    found: list[StaleRead] = []
    for index, reader in enumerate(ordered):
        for facet in sorted(reader.reads - set(reader.early_reads), key=lambda f: f.value):
            later = tuple(p.name for p in ordered[index + 1:] if facet in p.writes)
            if later:
                found.append(StaleRead(reader.name, facet, later))
    return found


def final_writers(passes: Iterable[FinalizePass]) -> dict[Facet, str]:
    """For each facet, the last pass that writes it: the point after which
    the facet is final."""
    last: dict[Facet, str] = {}
    for item in passes:
        for facet in item.writes:
            last[facet] = item.name
    return dict(sorted(last.items(), key=lambda pair: pair[0].value))


def unread_writes(
    passes: Iterable[FinalizePass], output_facets: Iterable[Facet] = tuple(Facet),
) -> list[tuple[str, Facet]]:
    """(pass, facet) for a write nothing later reads and that is not part of
    the output. Every facet is emitted in the map today, so the default
    reports nothing; the parameter is for a facet that is internal."""
    ordered = list(passes)
    emitted = set(output_facets)
    unread: list[tuple[str, Facet]] = []
    for index, writer in enumerate(ordered):
        for facet in sorted(writer.writes - emitted, key=lambda f: f.value):
            if not any(facet in later.reads for later in ordered[index + 1:]):
                unread.append((writer.name, facet))
    return unread


F = Facet
# The first naming call exists so the split sees removals in the same scan;
# what later passes change is judged by the second and the final call.
_JUDGED_AGAIN_LATER = (
    "removals must be known before the capability split; the two later calls "
    "judge again on what the passes in between produce"
)
# The split must run before anything is counted; the late demotion and naming
# passes then refine a layer that already has its capabilities.
_SPLIT_BEFORE_COUNTS = (
    "must precede the metric and line-count passes; the late demotes and the "
    "naming passes refine the split layer afterwards"
)

# In the order ``run_finalize_phase`` calls them. Registered: every pass that
# reads or writes journey membership, journey parent or feature ownership, and
# the passes that change the flow or feature set around them. Not registered
# yet: flow expansion, page interior, lineage, impact, monorepo assembly,
# dual evidence, the file-lane passes, the audits and the output stage.
FINALIZE_PASSES: tuple[FinalizePass, ...] = (
    _pass(
        "strip_test_paths", "stage_6_9_test_strip.strip_test_paths",
        reads=set(),
        writes={F.FEATURE_SET, F.FLOW_SET},
    ),
    _pass(
        "strip_generated_paths", "stage_6_9b_generated_strip.strip_generated_paths",
        reads={F.FEATURE_FILES},
        writes={F.FEATURE_FILES, F.FEATURE_SET, F.FLOW_SET},
    ),
    _pass(
        "strip_schema_monolith_members", "schema_member_strip.strip_schema_monolith_members",
        reads={F.FEATURE_FILES, F.FEATURE_SET},
        writes={F.FEATURE_SET},
    ),
    _pass(
        "drop_phantom_product_features", "stage_8_6_nonsource_drop.drop_phantom_product_features",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET},
        writes=set(),
    ),
    _pass(
        "run_anchored_mint", "stage_6_86_anchored_mint.run_anchored_mint",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.NAMES_PRODUCT},
        writes={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET},
    ),
    # Developer feature assumed: the written object is not named.
    _pass(
        "run_lane_excavation", "lane_excavation.run_lane_excavation",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.FLOW_OWNERSHIP, F.NAMES_PRODUCT},
        writes={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.FLOW_OWNERSHIP},
    ),
    _pass(
        "split_cross_pf_flow_attribution", "flow_span_split.split_cross_pf_flow_attribution",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.NAMES_PRODUCT},
        writes={F.FEATURE_FILES},
    ),
    _pass(
        "apply_twin_feature_merge", "twin_collision.apply_twin_feature_merge",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FLOW_OWNERSHIP, F.NAMES_PRODUCT},
        writes={F.FEATURE_FILES, F.FEATURE_SET, F.FLOW_OWNERSHIP, F.FLOW_SET, F.NAMES_PRODUCT},
    ),
    _pass(
        "run_flow_rederive", "flow_rederive.run_flow_rederive",
        reads={F.FEATURE_FILES, F.FLOW_OWNERSHIP},
        writes={F.FLOW_OWNERSHIP},
    ),
    _pass(
        "run_user_flow_rollup", "stage_6_7_user_flows.run_user_flow_rollup",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FLOW_OWNERSHIP, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET},
    ),
    _pass(
        "aggregate_user_flows", "stage_6_7a_det_aggregation.aggregate_user_flows",
        reads={F.FEATURE_OWNERSHIP, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET},
    ),
    _pass(
        "split_mega_user_flows", "stage_6_7c_uf_splitter.split_mega_user_flows",
        reads={F.FEATURE_OWNERSHIP, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET},
        calls_model=True,
    ),
    _pass(
        "refine_user_flows", "stage_6_7b_uf_refiner.refine_user_flows",
        reads={F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.NAMES_PRODUCT},
        calls_model=True,
    ),
    _pass(
        "apply_uf_conservation", "conservation.apply_uf_conservation",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET},
        writes={F.JOURNEY_PARENT},
    ),
    _pass(
        "run_journey_abstraction", "stage_6_7d_llm_journey_abstraction.run_journey_abstraction",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.FEATURE_FILES, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET},
        calls_model=True,
    ),
    _pass(
        "enforce_hub_family_parity", "stage_6_86_anchored_mint.enforce_hub_family_parity",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET},
        writes={F.FEATURE_FILES, F.FEATURE_OWNERSHIP},
    ),
    # Developer feature assumed: the written object is not named.
    _pass(
        "apply_hub_pf_binding", "hub_relation.apply_hub_pf_binding",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.NAMES_PRODUCT},
        writes={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET},
    ),
    _pass(
        "rehome_shared_flowful_devs", "conservation.rehome_shared_flowful_devs",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET},
        writes={F.FEATURE_OWNERSHIP},
    ),
    _pass(
        "apply_uf_conservation#2", "conservation.apply_uf_conservation",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET},
        writes={F.JOURNEY_PARENT},
    ),
    _pass(
        "apply_uf_conservation#3", "conservation.apply_uf_conservation",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET},
        writes={F.JOURNEY_PARENT},
    ),
    _pass(
        "split_cross_pf_flow_attribution#2", "flow_span_split.split_cross_pf_flow_attribution",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.NAMES_PRODUCT},
        writes={F.FEATURE_FILES},
    ),
    _pass(
        "mint_cli_command_journeys", "cli_command_journeys.mint_cli_command_journeys",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET},
    ),
    _pass(
        "fence_cli_foreign_journeys", "cli_command_journeys.fence_cli_foreign_journeys",
        reads={F.FEATURE_OWNERSHIP, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET},
        writes={F.JOURNEY_PARENT},
    ),
    _pass(
        "split_command_groups", "cli_command_groups.split_command_groups",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT, F.NAMES_PRODUCT},
    ),
    # Developer feature assumed: the written object is not named.
    _pass(
        "mint_entry_group_features", "entry_group_features.mint_entry_group_features",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT, F.NAMES_PRODUCT},
    ),
    _pass(
        "seed_route_group_journeys", "route_group_recall.seed_route_group_journeys",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET},
    ),
    # Developer feature assumed: the written object is not named.
    _pass(
        "rehome_uf_cited_lane_devs", "lane_rehome.rehome_uf_cited_lane_devs",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET},
        writes={F.FEATURE_OWNERSHIP},
    ),
    # Applies product_feature_id writes other passes proposed, for either kind.
    _pass(
        "flush_pending", "overturn_ledger.flush_pending",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT, F.JOURNEY_SET},
        writes={F.FEATURE_OWNERSHIP, F.JOURNEY_PARENT},
    ),
    _pass(
        "run_provenance_rehome", "provenance_rehome.run_provenance_rehome",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.FEATURE_FILES, F.FEATURE_SET},
    ),
    # Developer feature assumed: the written object is not named.
    _pass(
        "unify_sibling_anchors", "stage_6_88_sibling_unify.unify_sibling_anchors",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT, F.JOURNEY_SET},
        writes={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT},
    ),
    # Applies product_feature_id writes other passes proposed, for either kind.
    _pass(
        "flush_pending#2", "overturn_ledger.flush_pending",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT, F.JOURNEY_SET},
        writes={F.FEATURE_OWNERSHIP, F.JOURNEY_PARENT},
    ),
    _pass(
        "resynthesize_system_ufs", "stage_6_7_user_flows.resynthesize_system_ufs",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET},
    ),
    # Developer feature assumed: the written object is not named.
    _pass(
        "fold_unreferenced_vendor_husks", "stage_6_86_anchored_mint.fold_unreferenced_vendor_husks",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_SET},
        writes={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET},
    ),
    # Developer feature assumed: the written object is not named.
    _pass(
        "run_ws_blob_domain_drain", "ws_blob_domain_drain.run_ws_blob_domain_drain",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.FLOW_OWNERSHIP, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.FLOW_OWNERSHIP, F.NAMES_PRODUCT},
    ),
    _pass(
        "run_journey_lattice", "journey_lattice.run_journey_lattice",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET, F.METRICS_LOC, F.NAMES_PRODUCT},
        writes={F.FLOW_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET},
        calls_model=True,
    ),
    _pass(
        "apply_uf_conservation#4", "conservation.apply_uf_conservation",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET},
        writes={F.JOURNEY_PARENT},
    ),
    _pass(
        "dedup_lattice_journeys", "journey_lattice.dedup_lattice_journeys",
        reads={F.FEATURE_OWNERSHIP, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET},
        writes={F.FLOW_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET},
    ),
    _pass(
        "fold_thin_lattice_children", "journey_lattice.fold_thin_lattice_children",
        reads={F.FEATURE_OWNERSHIP, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET},
        writes={F.FLOW_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET},
    ),
    _pass(
        "readability_regrain", "stage_6_7a_det_aggregation.readability_regrain",
        reads={F.FEATURE_OWNERSHIP, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET},
        writes={F.FLOW_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET, F.NAMES_PRODUCT},
    ),
    _pass(
        "synthesize_orphan_journeys", "e2e_truth.synthesize_orphan_journeys",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET},
    ),
    # Developer feature assumed: the written object is not named.
    _pass(
        "run_transport_handoff", "transport_handoff.run_transport_handoff",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.FLOW_OWNERSHIP, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.FLOW_OWNERSHIP, F.JOURNEY_PARENT, F.NAMES_PRODUCT},
    ),
    # Developer feature assumed: the written object is not named.
    _pass(
        "rehome_rpc_called_devs", "rpc_router_rehome.rehome_rpc_called_devs",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.FLOW_OWNERSHIP},
        writes={F.FEATURE_OWNERSHIP},
    ),
    # Developer feature assumed: the written object is not named.
    _pass(
        "run_mega_pf_nav_rehome", "mega_pf_nav_rehome.run_mega_pf_nav_rehome",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT},
    ),
    # Developer feature assumed: the written object is not named.
    _pass(
        "run_devgrain_demote", "devgrain_demote.run_devgrain_demote",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_SET},
        writes={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.FLOW_SET, F.JOURNEY_SET},
    ),
    # Developer feature assumed: the written object is not named.
    _pass(
        "run_route_stub_shape", "stage_route_stub_shape.run_route_stub_shape",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT, F.JOURNEY_SET},
        writes={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT},
    ),
    # Applies product_feature_id writes other passes proposed, for either kind.
    _pass(
        "flush_pending#3", "overturn_ledger.flush_pending",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT, F.JOURNEY_SET},
        writes={F.FEATURE_OWNERSHIP, F.JOURNEY_PARENT},
    ),
    _pass(
        "stage_6_95_history", "stage_6_95_history.stage_6_95_history",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.FLOW_OWNERSHIP, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET},
        writes={F.METRICS_HISTORY},
    ),
    _pass(
        "apply_identity_keeper", "uf_identity_keeper.apply_identity_keeper",
        reads={F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET},
        writes={F.JOURNEY_MEMBERSHIP, F.NAMES_PRODUCT},
    ),
    _pass(
        "apply_feature_loc", "stage_6_97_feature_loc.apply_feature_loc",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET, F.METRICS_LOC},
        writes={F.METRICS_LOC},
    ),
    _pass(
        "resolve_flowless_shells", "stage_6_7d_llm_journey_abstraction.resolve_flowless_shells",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.NAMES_PRODUCT},
        writes={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET},
    ),
    _pass(
        "apply_emission_taxonomy", "surface_taxonomy.apply_emission_taxonomy",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.FLOW_SET, F.JOURNEY_SET},
        calls_model=True,
    ),
    # Developer feature assumed: the written object is not named.
    _pass(
        "run_leafroute_promotion", "leafroute_promotion.run_leafroute_promotion",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET},
    ),
    # Developer feature assumed: the written object is not named.
    _pass(
        "enforce_emission_integrity", "emission_integrity.enforce_emission_integrity",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.FLOW_OWNERSHIP, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.FEATURE_OWNERSHIP, F.FLOW_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET},
    ),
    _pass(
        "assign_terminal_homes", "uf_terminal_home.assign_terminal_homes",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET},
        writes={F.JOURNEY_PARENT},
    ),
    # Applies product_feature_id writes other passes proposed, for either kind.
    _pass(
        "flush_pending#4", "overturn_ledger.flush_pending",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT, F.JOURNEY_SET},
        writes={F.FEATURE_OWNERSHIP, F.JOURNEY_PARENT},
    ),
    _pass(
        "run_naming_contract", "naming_contract.run_naming_contract",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.NAMES_PRODUCT},
        calls_model=True,
    ),
    _pass(
        "run_spray_generalization", "spray_absorption.run_spray_generalization",
        reads={F.FEATURE_OWNERSHIP, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET},
        writes={F.FLOW_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET},
    ),
    _pass(
        "postmint_uf_rescore", "postmint_rescore.postmint_uf_rescore",
        reads={F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.NAMES_PRODUCT},
    ),
    _pass(
        "run_uf_cases_split", "uf_cases_split.run_uf_cases_split",
        reads={F.FEATURE_OWNERSHIP, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET},
    ),
    _pass(
        "postmint_uf_rescore#2", "postmint_rescore.postmint_uf_rescore",
        reads={F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.NAMES_PRODUCT},
    ),
    _pass(
        "apply_fold_coherence", "fold_coherence.apply_fold_coherence",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET},
        writes={F.JOURNEY_PARENT},
    ),
    _pass(
        "run_stage_6_7e", "stage_6_7e_adjudicator.run_stage_6_7e",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.FLOW_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET, F.NAMES_PRODUCT},
        calls_model=True,
    ),
    _pass(
        "home_dispatch_mints", "dispatch_homing.home_dispatch_mints",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET},
        writes={F.JOURNEY_PARENT},
    ),
    # Applies product_feature_id writes other passes proposed, for either kind.
    _pass(
        "flush_pending#5", "overturn_ledger.flush_pending",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT, F.JOURNEY_SET},
        writes={F.FEATURE_OWNERSHIP, F.JOURNEY_PARENT},
    ),
    _pass(
        "run_synth_quality", "synth_quality.run_synth_quality",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.FLOW_SET, F.JOURNEY_SET},
    ),
    _pass(
        "build_platform_infrastructure_lane", "stage_6_86_anchored_mint.build_platform_infrastructure_lane",
        reads={F.FEATURE_OWNERSHIP, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes=set(),
    ),
    _pass(
        "rehome_foreign_entry_ufs", "stage_6_99_i16_rehome.rehome_foreign_entry_ufs",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET},
        writes={F.JOURNEY_PARENT},
    ),
    # Applies product_feature_id writes other passes proposed, for either kind.
    _pass(
        "flush_pending#6", "overturn_ledger.flush_pending",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT, F.JOURNEY_SET},
        writes={F.FEATURE_OWNERSHIP, F.JOURNEY_PARENT},
    ),
    _pass(
        "run_post_uf_rehome", "stage_6_99b_post_uf_rehome.run_post_uf_rehome",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET, F.NAMES_PRODUCT},
    ),
    _pass(
        "attach_orphan_flows", "conservation.attach_orphan_flows",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET},
        writes=set(),
    ),
    _pass(
        "apply_home_affinity_gate", "conservation.apply_home_affinity_gate",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.JOURNEY_PARENT},
    ),
    _pass(
        "build_orphan_flow_gaps", "conservation.build_orphan_flow_gaps",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET},
        writes=set(),
    ),
    # Developer feature assumed: the written object is not named.
    _pass(
        "run_fold_evidence_demote", "fold_evidence_demote.run_fold_evidence_demote",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET, F.METRICS_LOC},
        writes={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.METRICS_LOC},
    ),
    _pass(
        "run_uf_member_exists", "uf_member_exists.run_uf_member_exists",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET},
        writes={F.JOURNEY_MEMBERSHIP},
    ),
    _pass(
        "run_member_disjoint_reconcile", "member_disjoint_reconcile.run_member_disjoint_reconcile",
        reads={F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET},
        writes={F.FLOW_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET},
    ),
    _pass(
        "reconcile_flow_backpointers", "uf_member_exists.reconcile_flow_backpointers",
        reads={F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET},
        writes={F.JOURNEY_MEMBERSHIP},
    ),
    _pass(
        "run_agent_surface", "agent_surface.run_agent_surface",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET},
    ),
    _pass(
        "postmint_uf_rescore#3", "postmint_rescore.postmint_uf_rescore",
        reads={F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.NAMES_PRODUCT},
    ),
    # Developer feature assumed: the written object is not named.
    _pass(
        "run_transport_pf_lane", "stage_6_9964_pin_closers.run_transport_pf_lane",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET},
        writes={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.FLOW_SET, F.JOURNEY_PARENT, F.JOURNEY_SET},
    ),
    # Developer feature assumed: the written object is not named.
    _pass(
        "run_api_stub_demote", "stage_6_9964_pin_closers.run_api_stub_demote",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT, F.JOURNEY_SET},
        writes={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.FLOW_SET, F.JOURNEY_PARENT, F.JOURNEY_SET},
    ),
    # Developer feature assumed: the written object is not named.
    _pass(
        "run_api_container_demote", "stage_6_9964_pin_closers.run_api_container_demote",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT, F.JOURNEY_SET},
        writes={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.FLOW_SET, F.JOURNEY_PARENT, F.JOURNEY_SET},
    ),
    # Developer feature assumed: the written object is not named.
    _pass(
        "run_route_render_util_demote", "stage_6_9964_pin_closers.run_route_render_util_demote",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT, F.JOURNEY_SET},
        writes={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.FLOW_SET, F.JOURNEY_PARENT, F.JOURNEY_SET},
    ),
    _pass(
        "run_token_journey_rehome", "stage_6_9965_token_journey_rehome.run_token_journey_rehome",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.JOURNEY_PARENT},
    ),
    # Developer feature assumed: the written object is not named.
    _pass(
        "run_container_file_mint", "stage_6_9966_container_journey_rehome.run_container_file_mint",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET, F.METRICS_LOC, F.NAMES_PRODUCT},
        writes={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT, F.METRICS_LOC},
    ),
    # Developer feature assumed: the written object is not named.
    _pass(
        "run_container_journey_rehome", "stage_6_9966_container_journey_rehome.run_container_journey_rehome",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET, F.METRICS_LOC, F.NAMES_PRODUCT},
        writes={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT, F.METRICS_LOC},
    ),
    _pass(
        "run_ws_containment_fold", "stage_ws_containment_fold.run_ws_containment_fold",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT},
    ),
    # The first of three calls, placed before the capability split so the
    # split sees which features stay (demotion veto) and which journeys lose
    # their parent. Features only; the two later calls judge what the passes
    # in between produce.
    _pass(
        "name_product_layer", "product_language_names.name_product_layer",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT, F.NAMES_PRODUCT},
        calls_model=True,
        early_reads={
            facet: _JUDGED_AGAIN_LATER
            for facet in (
                F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP,
                F.JOURNEY_PARENT, F.JOURNEY_SET, F.NAMES_PRODUCT,
            )
        },
    ),
    # Written by hand. Placed after the last structural writer of journey
    # parent and feature ownership before the metric passes, so nothing is
    # counted on the unsplit layer. Journeys it marks "not product" stay in
    # the host, so it does not write the journey set.
    _pass(
        "run_capability_split", "capability_split.run_capability_split",
        reads={
            F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.FLOW_OWNERSHIP,
            F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET, F.METRICS_LOC, F.NAMES_PRODUCT,
        },
        # It moves the lines of the files it carves between developer features
        # (and keeps the line-count ledger true), so it writes line counts.
        writes={
            F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.FLOW_OWNERSHIP,
            F.JOURNEY_PARENT, F.METRICS_LOC, F.NAMES_PRODUCT,
        },
        calls_model=True,
        early_reads={
            F.FEATURE_FILES: _SPLIT_BEFORE_COUNTS,
            F.FEATURE_OWNERSHIP: _SPLIT_BEFORE_COUNTS,
            F.FEATURE_SET: _SPLIT_BEFORE_COUNTS,
            F.JOURNEY_MEMBERSHIP: _SPLIT_BEFORE_COUNTS,
            F.JOURNEY_PARENT: _SPLIT_BEFORE_COUNTS,
            F.JOURNEY_SET: _SPLIT_BEFORE_COUNTS,
            F.NAMES_PRODUCT: "journey names before the product-language pass are "
                             "deterministic, which the reply cache needs",
            F.METRICS_LOC: "developer-feature line counts only decide which feature "
                           "is large enough to split; the final counts are stamped after",
        },
    ),
    _pass(
        "apply_uf_loc", "stage_6_97b_uf_loc.apply_uf_loc",
        reads={F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET, F.METRICS_LOC},
        writes={F.METRICS_LOC},
    ),
    _pass(
        "apply_flow_loc", "stage_6_97c_flow_loc.apply_flow_loc",
        reads={F.METRICS_LOC},
        writes={F.METRICS_LOC},
    ),
    _pass(
        "apply_pf_loc_backstop", "stage_6_97e_pf_loc.apply_pf_loc_backstop",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.METRICS_LOC},
        writes={F.METRICS_LOC},
    ),
    _pass(
        "apply_uf_metrics", "stage_6_97d_uf_metrics.apply_uf_metrics",
        reads={F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET},
        writes=set(),
    ),
    # Reads which developer features were carved from which, to name a
    # carved flow as part of its donor.
    _pass(
        "apply_flow_name_v2", "flow_name_v2.apply_flow_name_v2",
        reads={F.FLOW_OWNERSHIP, F.NAMES_PRODUCT, F.FEATURE_SET},
        writes={F.NAMES_PRODUCT},
    ),
    _pass(
        "apply_flow_pf_decollide", "twin_collision.apply_flow_pf_decollide",
        reads={F.FEATURE_OWNERSHIP, F.FLOW_OWNERSHIP, F.NAMES_PRODUCT},
        writes={F.NAMES_PRODUCT},
    ),
    _pass(
        "postmint_uf_rescore#4", "postmint_rescore.postmint_uf_rescore",
        reads={F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.NAMES_PRODUCT},
    ),
    _pass(
        "build_dissolved_dev_gaps", "conservation.build_dissolved_dev_gaps",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes=set(),
    ),
    _pass(
        "run_terminal_classification", "terminal_classification.run_terminal_classification",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET},
        writes=set(),
    ),
    _pass(
        "run_plumbing_uf_reclass", "plumbing_uf_reclass.run_plumbing_uf_reclass",
        reads={F.JOURNEY_MEMBERSHIP, F.JOURNEY_SET},
        writes=set(),
    ),
    # Applies product_feature_id writes other passes proposed, for either kind.
    _pass(
        "finalize_arbiter", "overturn_ledger.finalize_arbiter",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT, F.JOURNEY_SET},
        writes={F.FEATURE_OWNERSHIP, F.JOURNEY_PARENT},
    ),
    # Developer feature assumed: the written object is not named.
    _pass(
        "run_nav_category_demote", "nav_parent.run_nav_category_demote",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_SET},
        writes={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.FLOW_SET, F.JOURNEY_SET},
    ),
    # Developer feature assumed: the written object is not named.
    _pass(
        "run_settings_frame_demote", "settings_frame_demote.run_settings_frame_demote",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.FLOW_SET, F.JOURNEY_PARENT, F.JOURNEY_SET},
    ),
    # Developer feature assumed: the written object is not named.
    _pass(
        "run_capability_shared_rehome", "capability_shared_rehome.run_capability_shared_rehome",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.FLOW_OWNERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.FLOW_SET, F.JOURNEY_PARENT, F.JOURNEY_SET},
    ),
    _pass(
        "run_orphan_uf_path_attach", "orphan_uf_path_attach.run_orphan_uf_path_attach",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET},
        writes={F.JOURNEY_PARENT},
    ),
    _pass(
        "run_tier2_journey_reparent", "tier2_journey_reparent.run_tier2_journey_reparent",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET},
        writes={F.JOURNEY_PARENT},
    ),
    # Developer feature assumed: the written object is not named.
    _pass(
        "run_generic_container_demote", "generic_container_demote.run_generic_container_demote",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_SET},
        writes={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.FLOW_SET, F.JOURNEY_SET},
    ),
    # Also runs demote_unnameable_features: re-homes developer features and journeys.
    _pass(
        "name_product_layer#2", "product_language_names.name_product_layer",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT, F.NAMES_PRODUCT},
        calls_model=True,
    ),
    _pass(
        "run_emission_hard_gate", "emission_hard_gate.run_emission_hard_gate",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT, F.JOURNEY_SET, F.METRICS_LOC, F.NAMES_PRODUCT},
        writes={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT, F.METRICS_LOC, F.NAMES_PRODUCT},
    ),
    # Developer feature assumed: the written object is not named.
    _pass(
        "run_pf_slug_sanitize", "pf_slug_sanitize.run_pf_slug_sanitize",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.FEATURE_OWNERSHIP, F.JOURNEY_PARENT},
    ),
    _pass(
        "run_detach_accounting", "detach_accounting.run_detach_accounting",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_PARENT, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.JOURNEY_PARENT},
    ),
    _pass(
        "apply_pf_loc_reroll", "stage_6_97e_pf_loc.apply_pf_loc_reroll",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_SET, F.METRICS_LOC},
        writes={F.METRICS_LOC},
    ),
    _pass(
        "run_metrics_ownership_gate", "metrics_ownership_gate.run_metrics_ownership_gate",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET},
        writes=set(),
    ),
    # Also runs demote_unnameable_features: re-homes developer features and journeys; the final call also drops unnameable journeys.
    _pass(
        "name_product_layer#3", "product_language_names.name_product_layer",
        reads={F.FEATURE_FILES, F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET, F.NAMES_PRODUCT},
        writes={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET, F.NAMES_PRODUCT},
        calls_model=True,
    ),
    _pass(
        "run_orphan_uf_owner_attach", "orphan_uf_path_attach.run_orphan_uf_owner_attach",
        reads={F.FEATURE_OWNERSHIP, F.FEATURE_SET, F.FLOW_OWNERSHIP, F.JOURNEY_MEMBERSHIP, F.JOURNEY_PARENT, F.JOURNEY_SET},
        writes={F.JOURNEY_PARENT},
    ),
)
