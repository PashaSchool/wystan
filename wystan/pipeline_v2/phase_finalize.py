"""Per-tree pipeline phase — lineage, late flow passes, output.

Extracted from ``run.py`` (refactor/run-decomposition) as straight-line
code — same stage order, same StageLogger stage indexes/names, same
artifact filenames, same lazy (function-local) imports.

  - Stage 6.8  — lineage + indexes (UUID stamping, path/routes index)
  - Incremental scan bookkeeping (head SHA + metric carry-forward)
  - Stage 3.5  — flow expansion (deterministic call-graph)
  - Stage 6.9  — test-file output-tree strip
  - Stage 6.7  — User-Flow rollup ($0 LLM)
  - Stage 6.7c — Mega-UF semantic split (additive Sonnet)
  - Stage 6.7b — User-Flow LLM refiner (additive Haiku)
  - Stage 7    — output (FeatureMap assembly + writer)

``scan_meta`` is updated IN PLACE (lineage stats, incremental meta,
per-stage telemetry) exactly as the inline code did.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from wystan.llm.cost import CostTracker
from wystan.pipeline_v2.llm_health import LlmHealth, stamp_llm_degraded
from wystan.pipeline_v2.incremental_wiring import (
    apply_incremental_bookkeeping,
    plan_uf_domain_allowlist,
)
from wystan.pipeline_v2.run_logger import StageLogger
from wystan.pipeline_v2 import invariant_hooks
from wystan.replay.capture import write_stage_input
from wystan.pipeline_v2.stage_7_output import (
    stage_7_output,
    write_stage_artifact,
)
from wystan.pipeline_v2.overturn_ledger import (
    flush_pending as _arb_flush,
)


def _recover_uncovered_donors(
    user_flows: list[Any],
    features: list[Any],
    product_features: list[Any],
    *,
    loc_only: bool = False,
    flowful_synth: bool = False,
) -> dict[str, Any] | None:
    """W1.1 donor re-cover — the post-finalize-conservation backstop run.

    The finalize conservation pass resettles by span-LOC majority and can
    leave a flowful PF with zero journeys (the in-6.7d backstop ran
    BEFORE it); W1 §E predicted the class and the 2026-07-06 validation
    wave shipped it (supabase ×4, midday 'Support' — validator I8).
    Re-runs the 6.7d backstop over the STAMPED dev→PF state: its
    reassign arm is conservation-compatible since W1.1 (same ruler as
    the recheck the caller runs after this), its synthesize arm mints
    ``synthesized``-tagged journeys the conservation ladder exempts —
    so the follow-up recheck can only confirm, never undo (fixpoint in
    one pass, deterministic). Returns telemetry, or ``None`` when the
    backstop kill-switch is off.
    """
    from wystan.pipeline_v2.stage_6_7d_llm_journey_abstraction import (
        _backstop_uncovered_pfs,
        _pf_uf_backstop_enabled,
    )

    if not _pf_uf_backstop_enabled():
        return None
    stamped_map = {
        f.name: (f.product_feature_id,)
        for f in features
        if getattr(f, "layer", "developer") == "developer"
        and getattr(f, "name", None)
        and getattr(f, "product_feature_id", None)
    }
    bs_tele = _backstop_uncovered_pfs(
        user_flows, product_features, stamped_map, features, set(),
        loc_only=loc_only, flowful_synth=flowful_synth,
    )
    # Provisional ids → continue the stable numbering (content-sorted
    # among the new synths, appended after the existing UF-xxx block).
    max_id = 0
    for uf in user_flows:
        m = re.match(r"^UF-(\d+)$", str(uf.id or ""))
        if m:
            max_id = max(max_id, int(m.group(1)))
    fresh = [u for u in user_flows if u.id == "UF-000"]
    fresh.sort(key=lambda u: ((u.name or "").lower(),
                              str(u.resource or "")))
    for i, uf in enumerate(fresh, start=1):
        uf.id = f"UF-{max_id + i:03d}"
    return {
        "uncovered": bs_tele.get("pf_backstop_uncovered", 0),
        "reassigned_ufs": bs_tele.get("pf_backstop_reassigned_ufs", 0),
        "synthesized": bs_tele.get("pf_backstop_synthesized", 0),
        "locworthy": bs_tele.get("pf_backstop_locworthy", 0),
        "resolutions": bs_tele.get("pf_backstop_resolutions", []),
    }


def run_finalize_phase(
    *,
    repo_path: Path,
    ctx: Any,
    features: list[Any],
    bipartite: Any,
    product_features: list[Any],
    stage1_out: dict[str, Any],
    scan_meta: dict[str, Any],
    run_dir: Path,
    model_id: str,
    tracker: CostTracker,
    since: str | None,
    base_scan_path: Path | str | None,
    lineage_jaccard_threshold: float | None,
    incremental_base_scan: dict[str, Any] | None,
    incremental_gate_meta: dict[str, Any],
    out_path: Path | None,
    days: int,
    feature_history: bool = True,
    llm_health: LlmHealth | None = None,
    repo_class_result: Any = None,
    prev_scan_json: dict[str, Any] | None = None,
    # B74 Seg B — the Stage-3 unit snapshot (name → sorted owned paths
    # at flow-derivation time) for the post-grain re-derivation cohort
    # selector. ``None`` (legacy callers / replay of older captures)
    # keeps Stage 6.865 un-entered.
    stage3_unit_snapshot: dict[str, list[str]] | None = None,
) -> Path:
    """Run Stage 6.8 → 3.5 → 6.9 → 6.7/6.7c/6.7b → 6.95 → 7 and write output.

    Body moved verbatim from ``run_pipeline_v2``. Returns the written
    FeatureMap path.
    """
    # ── Stage 6.8 — lineage + indexes (Sprint 1, 2026-05-23) ──────
    # Pure post-pass: stamps stable UUIDs on every Feature + Flow,
    # builds path_index + routes_index. NEVER affects scan-quality
    # decisions. When ``base_scan_path`` is provided we match against
    # the previous scan for cross-scan UUID stability; otherwise every
    # feature/flow gets a fresh uuid4 (cold-scan default).
    from wystan.pipeline_v2.incremental import (
        load_base_scan as _load_base_scan,
    )
    from wystan.pipeline_v2.lineage import (
        RELATED_THRESHOLD as _RELATED_THRESHOLD,
        RENAME_THRESHOLD as _RENAME_THRESHOLD,
    )
    from wystan.pipeline_v2.stage_6_8_lineage import run_stage_6_8

    rename_threshold = (
        float(lineage_jaccard_threshold)
        if lineage_jaccard_threshold is not None
        else _RENAME_THRESHOLD
    )

    # Reuse the base scan already loaded by the Stage 2.5 incremental
    # gate (avoids re-parsing a large JSON). Falls back to a fresh load
    # for callers that pass ``base_scan_path`` for lineage WITHOUT
    # ``--since`` (full scan with lineage stamping).
    base_scan_dict: dict[str, Any] | None = incremental_base_scan
    if base_scan_dict is None and base_scan_path is not None:
        base_scan_dict = _load_base_scan(base_scan_path)

    # Replay v2 — input-only capture for the lineage connector (Stage 6.8
    # writes no output artifact; the replay chain needs its input to
    # re-stamp UUIDs + rebuild indexes when chaining into the finalize
    # stages). ``base_scan`` is captured as a PATH reference, not inline.
    write_stage_input(run_dir, 6, "lineage", {
        "features": features,
        "bipartite_flows": list(bipartite.flows),
        "stage1_out": stage1_out,
        "scan_meta": scan_meta,
        "base_scan_path": str(base_scan_path) if base_scan_path else None,
        "lineage_jaccard_threshold": rename_threshold,
        "since": since,
        "repo_path": str(repo_path),
    })
    lineage_result = run_stage_6_8(
        features,
        list(bipartite.flows),
        base_scan=base_scan_dict,
        extractor_signals=stage1_out,
        rename_threshold=rename_threshold,
        related_threshold=_RELATED_THRESHOLD,
        repo_path=str(repo_path),
    )
    # W2/E6 — declaration-grammar arbitration telemetry. Stamped ONLY on a
    # board the arbiter actually touched (inertness law); a flag-off run and
    # an untouched board both carry no key at all.
    if lineage_result.route_decl_arbitration:
        scan_meta["routes_decl_arbitration"] = (
            lineage_result.route_decl_arbitration
        )

    # ── Stage 6.8b — system/background-flow classification (deterministic) ──
    # Tag every route's ``trigger`` (scheduled|queue|webhook|interactive) from
    # eval/system-flow-patterns.yaml: framework cron manifests + path-segment
    # conventions + job-library markers. Lets Stage 6.7 separate background jobs
    # (cron / queue / webhook) from interactive user journeys. No LLM; reads only
    # the cloned repo. SELF-DETECTING — a repo with no jobs tags everything
    # ``interactive`` (a clean no-op), so non-job repos are byte-identical.
    from wystan.pipeline_v2.system_flows import classify_routes
    scan_meta["system_flow_routes"] = classify_routes(
        lineage_result.routes_index, repo_path,
    )

    # ── Stage 6.85 — product-surface taxonomy, Layer-1 tagging ─────────
    # Product-Spine §4.2 (Wave 2a): stamp ``surface_scope`` on every
    # routes_index entry + developer feature (product | marketing | docs |
    # legal | system | dev_tooling | shell). Runs AFTER 6.8b so the system
    # trigger verdicts exist; BEFORE the UF/PF stages so 6.7d's residual
    # ladder + container guard can consume the dev tags. Deterministic,
    # $0 LLM. Kill-switch WYSTAN_SURFACE_TAXONOMY=0 (tags absent →
    # every consumer no-ops; the omit-unset serializers keep output
    # byte-identical to pre-W2a engines).
    from wystan.pipeline_v2.surface_taxonomy import tag_layer1
    scan_meta["surface_taxonomy"] = tag_layer1(
        features, lineage_result.routes_index, repo_path=repo_path,
    )

    # ── Stage 6.55 — page-interior structure (Product-Spine §4.6, W4) ──
    # Tree-sitter parse of PAGE route files into their interior render
    # tree (product components vs design-system primitives, labels,
    # definition spans). Runs AFTER 6.8 (needs routes_index), BEFORE
    # Stage 3.5 so the refined ``role="interior"`` attributions ride the
    # expansion. Deterministic, $0 LLM, content-hash cached; inactive
    # (byte-identical scans) when tree-sitter isn't installed.
    # Kill-switch WYSTAN_STAGE_6_55=0.
    from wystan.pipeline_v2.stage_6_55_page_interior import (
        degenerate_span_stats,
        inject_interior_nodes,
        refine_flow_spans,
        run_stage_6_55,
    )
    write_stage_input(run_dir, 6, "page_interior", {
        "routes_index": lineage_result.routes_index,
        "ctx": ctx,
    })
    with StageLogger(run_dir, 6, "page_interior") as log6_55:
        interior_result = run_stage_6_55(
            ctx, lineage_result.routes_index, log6_55,
        )
        interior_telemetry: dict[str, Any] = {
            "active": interior_result.active,
        }
        if interior_result.active:
            interior_telemetry.update(interior_result.telemetry)
            interior_telemetry["degenerate_spans_before"] = (
                degenerate_span_stats(features)
            )
            interior_telemetry["span_refine"] = refine_flow_spans(
                features, interior_result,
            )
        else:
            interior_telemetry["reason"] = interior_result.reason
        write_stage_artifact(
            ctx.repo_path,
            stage_index=6,
            stage_name="page_interior",
            payload=interior_telemetry,
            run_dir=run_dir,
        )

    # ── Incremental scan bookkeeping ───────────────────────────────
    # Head SHA + Stage 6 metric carry-forward for untouched features —
    # see ``incremental_wiring.apply_incremental_bookkeeping``.
    is_full_scan = since is None
    head, incremental_meta = apply_incremental_bookkeeping(
        repo_path=repo_path,
        since=since,
        is_full_scan=is_full_scan,
        base_scan=base_scan_dict,
        features=features,
    )
    scan_meta["lineage_feature_stats"] = lineage_result.feature_lineage_stats
    scan_meta["lineage_flow_stats"] = lineage_result.flow_lineage_stats
    scan_meta["lineage_rename_threshold"] = rename_threshold
    scan_meta["is_full_scan"] = is_full_scan
    scan_meta.update(incremental_meta)
    # Stage 2.5 LLM-gating telemetry (empty dict on a full scan).
    scan_meta.update(incremental_gate_meta)

    # ── Stage 3.5 — flow expansion (Sprint 2, deterministic) ──────
    # Enriches every Flow with {entry, nodes[], edges[], summary}
    # via T1 (intra-repo call graph) + T2 (cross-stack HTTP boundary
    # matched against the Sprint 1 routes_index). Mutates Flow
    # objects in place under both Feature.flows (containment view)
    # AND the top-level bipartite list. Pure in-memory; no LLM; no
    # persistence — preserves [[rule-cold-scan]]. Legacy fields on
    # Flow (paths, participants, entry_point_file, coverage_pct,
    # flow_symbol_attributions, uuid, all Stage 5.5 bipartite fields)
    # are preserved unchanged.
    #
    # Inserted between Stage 6.8 (lineage / routes_index build) and
    # Stage 7 (output) so:
    #   - routes_index is available for T2 cross-stack matching;
    #   - the expansion lands in the final FeatureMap JSON;
    #   - lineage-stable UUIDs are present on every Flow for the
    #     ``top_level_flows`` mirror pass.
    from wystan.pipeline_v2.flow_expansion import expand_flows
    write_stage_input(run_dir, 3, "flow_expansion", {
        "features": features,
        "ctx": ctx,
        "routes_index": lineage_result.routes_index,
        "bipartite_flows": list(bipartite.flows),
        "scan_meta": scan_meta,
    })
    with StageLogger(run_dir, 3, "flow_expansion") as log3_5:
        # max_depth=1 — a flow's attributed implementation is the entry
        # symbol + its DIRECT callees (same-file AND imported), with no
        # transitive recursion. Deeper walks turn each flow into the
        # whole transitive closure of the import graph and stop being a
        # narrative slice of ONE behaviour (measured: avg 62.5 nodes/flow
        # and 235/447 flows hitting the node cap at depth 4). Cross-file
        # resolution is independently hard-capped at depth 1 inside
        # build_call_graph; this aligns same-file recursion to the same
        # "entry + direct callees" target. Fan-in gating then demotes
        # high-fan-in shared infrastructure to role=shared (excluded
        # from core LOC, still recorded as a shared-dependency badge).
        fx = expand_flows(
            features,
            ctx,
            routes_index=lineage_result.routes_index,
            max_depth=1,
            log=log3_5,
            top_level_flows=list(bipartite.flows),
        )
        log3_5.info(
            f"expansion: flows_expanded={fx.telemetry['flows_expanded']} "
            f"nodes_total={fx.telemetry['nodes_total']} "
            f"edges_total={fx.telemetry['edges_total']} "
            f"cross_stack_hops_total={fx.telemetry['cross_stack_hops_total']} "
            f"deepest_depth={fx.telemetry['deepest_depth_reached']} "
            f"truncated={fx.telemetry['flows_truncated']} "
            f"unsupported_stack={fx.telemetry['flows_unsupported_stack']}",
        )
        write_stage_artifact(
            ctx.repo_path,
            stage_index=3,
            stage_name="flow_expansion",
            payload=fx.telemetry,
            run_dir=run_dir,
        )
    scan_meta["stage_3_5_flow_expansion"] = dict(fx.telemetry)

    # B82 sentinel (warn) — post-3.5 span-recovery residual. Fired ONLY when a
    # span-recovery arm is armed (else no barrel set → byte-identical default
    # world, the B91 own-key precedent). Flags any flow still entered from a
    # re-export barrel with a collapsed 1-line span (Form A did not redirect
    # it). barrel_entry_files is derived from the flows' OWN entry files via
    # the shared signatures already in hand — bounded by #flows, no re-parse.
    from wystan.pipeline_v2.flow_expansion.span_recovery import (
        SpanRecoveryConfig as _SpanRecoveryConfig,
        parse_reexports as _parse_reexports,
    )
    _sr_cfg = _SpanRecoveryConfig.from_env()
    if _sr_cfg.any:
        from wystan.pipeline_v2.shared_source import shared_reach_context
        _rctx = shared_reach_context(ctx)
        _all_flows = [
            fl for feat in features for fl in (feat.flows or [])
        ] + list(bipartite.flows)
        _barrels: set[str] = set()
        if _rctx is not None:
            for _fl in _all_flows:
                _entry = getattr(_fl, "entry", None)
                _ef = _entry.get("file") if isinstance(_entry, dict) else None
                if not _ef or _ef in _barrels:
                    continue
                _sig = _rctx.signatures.get(_ef)
                if _sig is not None and _sig.source and _parse_reexports(_sig.source):
                    _barrels.add(_ef)
        invariant_hooks.run_stage(
            scan_meta, "3.5_span_recovery",
            flows=_all_flows, barrel_entry_files=frozenset(_barrels),
        )

    # Decorator-edge sentinel (warn) — post-3.5 decorator-support residual.
    # Fired ONLY when the decorator arm is armed (else no expected map → byte-
    # identical default world). Re-derives, per flow entry, the decorator-impl
    # node ids that SHOULD be attached (same resolver as the expander) and flags
    # any flow whose graph lost one. Bounded by #flows; the config's own cache
    # AST-parses each entry file at most once.
    from wystan.pipeline_v2.flow_expansion.decorator_edges import (
        DecoratorEdgeConfig as _DecoCfg,
        entry_decorator_target_ids as _deco_targets,
    )
    _deco_cfg = _DecoCfg.from_env()
    if _deco_cfg.enabled:
        from wystan.pipeline_v2.shared_source import shared_reach_context
        _drctx = shared_reach_context(ctx)
        _dflows = [
            fl for feat in features for fl in (feat.flows or [])
        ] + list(bipartite.flows)
        _expected: dict[str, list[str]] = {}
        if _drctx is not None:
            for _fl in _dflows:
                _entry = getattr(_fl, "entry", None)
                if not isinstance(_entry, dict):
                    continue
                _ef = _entry.get("file")
                _es = _entry.get("symbol")
                _elines = _entry.get("lines")
                _eline = (
                    _elines[0]
                    if isinstance(_elines, (list, tuple)) and _elines
                    else None
                )
                _uuid = getattr(_fl, "uuid", None)
                if not _ef or not _uuid:
                    continue
                _parent = _es.rsplit(".", 1)[0] if (_es and "." in _es) else None
                _targets = _deco_targets(
                    _drctx, _ef, _es, _parent, _eline, _deco_cfg)
                if _targets:
                    _expected[str(_uuid)] = _targets
        invariant_hooks.run_stage(
            scan_meta, "3.5_decorator_edges",
            flows=_dflows, decorator_expected=_expected,
        )

    # ── Stage 6.55 (part 2) — interior nodes onto the expanded graph ──
    # The ``role="interior"`` attributions become FlowNodes (so
    # ``line_ranges`` / on-flow LOC accounting see real component spans)
    # and whole-file support nodes covering a resolved component source
    # are TIGHTENED to the definition span. Runs immediately after the
    # Stage 3.5 expansion that built the node graph; re-projects the
    # Phase-5 LOC views (idempotent). No-op when 6.55 was inactive.
    if interior_result.active:
        interior_telemetry["node_inject"] = inject_interior_nodes(
            features, interior_result,
        )
        interior_telemetry["degenerate_spans_after"] = (
            degenerate_span_stats(features)
        )
    scan_meta["stage_6_55_page_interior"] = dict(interior_telemetry)

    # ── Stage 6.9 — test-file output-tree strip ────────────────────
    # "Post-everything tree hygiene": despite the 6.9 label this is
    # wired to run LAST (after every Stage 6.x metric pass, after Stage
    # 8 analyst + Stage 8.5 backfill, and after Stage 3.5 flow expansion
    # which populates loc_nodes/loc_edges) so it sees the fully-enriched
    # tree and cannot disturb any upstream computation. It removes
    # test-file entries from the OUTPUT TREE only and NEVER recomputes a
    # metric scalar — coverage_pct/health/bug_fix_ratio are computed in
    # Stage 6 WITH the test files on purpose. Disable with
    # WYSTAN_STAGE_6_9_TEST_STRIP=0. See the module docstring.
    from wystan.pipeline_v2.stage_6_9_test_strip import (
        stage_6_9_enabled,
        strip_test_paths,
    )

    test_strip_telemetry: dict[str, int] = {
        "paths_removed": 0,
        "features_dropped": 0,
        "flows_dropped": 0,
        "flow_entries_recomputed": 0,
    }
    write_stage_input(run_dir, 6, "test_strip", {
        "features": features,
        "bipartite_flows": list(bipartite.flows),
        "scan_meta": scan_meta,
    })
    with StageLogger(run_dir, 6, "test_strip") as log6_9:
        if stage_6_9_enabled():
            test_strip_telemetry = strip_test_paths(features, bipartite.flows)
            log6_9.info(
                "test_strip: paths_removed=%d features_dropped=%d "
                "flows_dropped=%d flow_entries_recomputed=%d"
                % (
                    test_strip_telemetry["paths_removed"],
                    test_strip_telemetry["features_dropped"],
                    test_strip_telemetry["flows_dropped"],
                    test_strip_telemetry["flow_entries_recomputed"],
                ),
            )
        else:
            test_strip_telemetry["disabled"] = True
            log6_9.info("test_strip: disabled via %s=0"
                        % "WYSTAN_STAGE_6_9_TEST_STRIP")
        write_stage_artifact(
            ctx.repo_path,
            stage_index=6,
            stage_name="test_strip",
            payload=test_strip_telemetry,
            run_dir=run_dir,
        )
    scan_meta["stage_6_9_test_strip"] = dict(test_strip_telemetry)

    # Stage 6.9b — generated-code strip (sibling of the test-strip): remove
    # machine-generated source (protobuf / sqlc / stringer / k8s-gen / dart …)
    # from the output tree so it never surfaces as a hand-authored product
    # feature. Same invariants (never mutates a metric scalar; drops emptied
    # features/flows). Disable with WYSTAN_STAGE_6_9B_GENERATED_STRIP=0.
    from wystan.pipeline_v2.stage_6_9b_generated_strip import (
        stage_6_9b_enabled,
        strip_generated_paths,
    )

    generated_strip_telemetry: dict[str, int] = {
        "paths_removed": 0,
        "features_dropped": 0,
        "flows_dropped": 0,
    }
    write_stage_input(run_dir, 6, "generated_strip", {
        "features": features,
        "bipartite_flows": list(bipartite.flows),
        "product_features": product_features,
        "scan_meta": scan_meta,
    })
    with StageLogger(run_dir, 6, "generated_strip") as log6_9b:
        if stage_6_9b_enabled():
            generated_strip_telemetry = strip_generated_paths(
                features, bipartite.flows,
                repo_root=getattr(ctx, "repo_path", None),
            )
            log6_9b.info(
                "generated_strip: paths_removed=%d features_dropped=%d "
                "flows_dropped=%d"
                % (
                    generated_strip_telemetry["paths_removed"],
                    generated_strip_telemetry["features_dropped"],
                    generated_strip_telemetry["flows_dropped"],
                ),
            )
        else:
            generated_strip_telemetry["disabled"] = True
            log6_9b.info("generated_strip: disabled via %s=0"
                         % "WYSTAN_STAGE_6_9B_GENERATED_STRIP")
        write_stage_artifact(
            ctx.repo_path,
            stage_index=6,
            stage_name="generated_strip",
            payload=generated_strip_telemetry,
            run_dir=run_dir,
        )
    scan_meta["stage_6_9b_generated_strip"] = dict(generated_strip_telemetry)

    # ── Stage 6.9c — schema-monolith member strip (B58-v3 Seg C) ────────
    # A whole-DB schema monolith (``schema.prisma`` / ``db/schema.rb``)
    # annexed onto a FOREIGN-anchored feature (the stage-2 route,schema
    # join + the 6.97 primary-owner tiebreak dumping the schema package's
    # shared plumbing onto a leaf route — documenso team.verify 1,202 LOC
    # where 152 exist) is stripped from every foreign claimant; the
    # schema package's own feature (majority-inside) keeps its claims.
    # Runs HERE — after the 6.9/6.9b strips (same output-tree contract),
    # BEFORE the 6.86 mint (PF member_files are carried from dev ledgers,
    # spine anchors read owned_paths_of — PF rows form clean) and BEFORE
    # Stage 6.97 (owned LOC re-truths). Monoliths carry no flows, so the
    # journey layer is structurally unaffected. Kill-switch: the pass
    # only runs under WYSTAN_GRAIN_WAVE=1 (default OFF) — unset/=0 is
    # byte-identical (no scan_meta key, no artifact).
    _sms_dropped = 0
    from wystan.pipeline_v2.schema_member_strip import (
        grain_wave_enabled,
        strip_schema_monolith_members,
    )
    if grain_wave_enabled():
        with StageLogger(run_dir, 6, "schema_member_strip") as log6_9c:
            try:
                sms_tele = strip_schema_monolith_members(
                    features, product_features,
                )
                _sms_dropped = sms_tele.get("features_dropped", 0)
                if sms_tele.get("paths_removed") or sms_tele.get("no_home"):
                    scan_meta["schema_member_strip"] = sms_tele
                log6_9c.info(
                    "schema_member_strip: pkgs=%d paths_removed=%d "
                    "features_stripped=%d dropped=%d no_home=%d" % (
                        len(sms_tele.get("packages", [])),
                        sms_tele.get("paths_removed", 0),
                        sms_tele.get("features_stripped", 0),
                        _sms_dropped,
                        len(sms_tele.get("no_home", [])),
                    ),
                    feature=None,
                )
            except Exception as exc:  # noqa: BLE001 — never break a scan
                log6_9c.info(
                    f"schema_member_strip: FAILED ({exc}) — continuing",
                    feature=None,
                )

    # Reconcile Layer-2 after the strips. A product feature whose only member
    # was a test-only / generated-only developer feature is now empty — the
    # strips dropped that feature here in the finalize phase, AFTER Stage 8.6's
    # phantom drop ran. Re-apply the same deterministic, path-preserving rule now
    # that the developer-feature set is final, so a content-less duplicate row
    # (e.g. an "Integrations" cluster pointing only at e2e/ + tests/ paths) never
    # reaches output. No-op when neither strip dropped a feature.
    if test_strip_telemetry.get("features_dropped") or generated_strip_telemetry.get(
        "features_dropped"
    ) or _sms_dropped:
        from wystan.pipeline_v2.stage_8_6_nonsource_drop import (
            drop_phantom_product_features,
        )
        product_features, pf_phantom_post = drop_phantom_product_features(
            features, product_features,
        )
        scan_meta["stage_6_9_test_strip"]["pf_dropped_phantom"] = pf_phantom_post

    # ── Stage 6.86 — Anchored PF minting (Product-Spine §4.3, Wave 2b) ──
    # THE membership spine: PF candidates come ONLY from ranked anchor
    # sources (route subtrees / workspaces / schema domains / hub
    # families / authored feature-dirs / service-dirs); dev→PF derives
    # deterministically from anchor lineage (θ=0.5 majority +
    # specificity reduction + fixed source-rank near-ties). REPLACES the
    # Stage 6.5/8 product layer wholesale and retires 6.7d Call-2 as the
    # membership oracle. Runs AFTER the 6.9/6.9b strips (final dev
    # membership) and BEFORE the UF stages so 6.7's UF→PF vote, the
    # conservation law, and 6.7d all consume anchored stamps. Residual
    # devs go to the platform_infrastructure[] lane (operator amendment
    # 2026-07-06: the Shared Platform PF no longer exists on this path).
    # Deterministic, $0 LLM. Kill-switch WYSTAN_SPINE_ANCHORED_MINT=0
    # restores the old path byte-identically.
    from wystan.pipeline_v2.stage_6_86_anchored_mint import (
        anchored_mint_enabled,
        run_anchored_mint,
    )

    anchored_mint_applied = False
    anchored_hub_stamps: dict[str, str] = {}
    instrument_dirs: frozenset[str] = frozenset()  # W4.2 Fix 1
    dev_artifact_units: frozenset[str] = frozenset()  # B28 P-D marks
    _hh_anchor_registry: dict[str, Any] | None = None  # B69-v2 (6.99b rail)
    if anchored_mint_enabled():
        write_stage_input(run_dir, 6, "anchored_mint", {
            "features": features,
            "product_features": product_features,
            "routes_index": lineage_result.routes_index,
            "stage1_out": stage1_out,
            "ctx": ctx,
            "scan_meta": scan_meta,
        })
        with StageLogger(run_dir, 6, "anchored_mint") as log_mint:
            try:
                # Nav labels confirm anchors (ranking evidence only) —
                # normalized first meaningful href segments from the
                # deterministic product-string collector's nav pairs.
                _nav_keys: set[str] = set()
                try:
                    from wystan.pipeline_v2.product_strings import (
                        collect_product_strings,
                        normalize_href,
                    )
                    from wystan.pipeline_v2.spine_anchors import (
                        normalize_anchor_key,
                    )
                    _nav_candidates: set[str] = set()
                    for _f in features:
                        _nav_candidates.update(_f.paths or [])
                    _nav_index = collect_product_strings(
                        repo_path, _nav_candidates)
                    for _pairs in _nav_index.nav_pairs_by_file.values():
                        for _label, _href in _pairs:
                            if not _href:
                                continue
                            norm = normalize_href(str(_href)) or ""
                            for seg in norm.strip("/").split("/"):
                                if seg and not seg.startswith(":"):
                                    _nav_keys.add(normalize_anchor_key(seg))
                                    break
                except Exception:  # noqa: BLE001 — confirmers are optional
                    _nav_keys = set()
                # WYSTAN_VUE_NAV_KEYS — MINT/DEMOTE channel split (Fix A,
                # RefApp phantom regression, 2026-07-31). The vue/nav-tree union
                # feeds the DEMOTER layer ONLY:
                #   * ``_nav_keys``      = MINT channel — exactly the weak
                #     product_strings collector echo above, as the pre-pack-13
                #     engine fed run_anchored_mint. The strong nav-tree parser
                #     reads JSX too (B78), so unioning it here let sidebar
                #     tokens (RefApp mitre/framework) CONFIRM route-segment
                #     anchors the weak echo never saw ⇒ phantom PFs born
                #     (frameworks/mitre) + members stolen (compliance.py).
                #     Mint-coupled consumers (the anchored mint confirmer +
                #     the telemetry rungs documented as "the SAME keys the
                #     mint received") stay on this set.
                #   * ``_nav_keys_demote`` = DEMOTER channel — weak echo ∪ the
                #     vue-lift per-workspace union. Read ONLY by the post-UF
                #     demote layer (6.987 devgrain / api-stub / api-container /
                #     route-render-util via nav_seam_keys), where nav evidence
                #     EXEMPTS or un-abstains — it can protect a PF, never mint
                #     one. ``_nav_keys_by_ws`` additionally scopes the devgrain
                #     per-leaf exemption per workspace package.
                # Flag OFF ⇒ the lift is skipped and both sets are the same
                # weak echo ⇒ byte-identical to the pre-flag engine.
                from wystan.pipeline_v2.nav_parent import (
                    split_nav_key_channels,
                )
                (_nav_keys_mint, _nav_keys_demote,
                 _nav_keys_by_ws, _nav_ws_paths) = split_nav_key_channels(
                    ctx, _nav_keys)
                _nav_keys = set(_nav_keys_mint)
                mint_pfs, mint_tele = run_anchored_mint(
                    features,
                    lineage_result.routes_index,
                    ctx,
                    extractor_signals=stage1_out,
                    nav_keys=frozenset(_nav_keys),
                    # B105 FIX-2 — the intake's Stage 0.7 verdict decides
                    # whether a ZERO-PF mint is honest (library/CLI) or a
                    # lost product layer (product-app). Read only under
                    # WYSTAN_MINT_EMPTY_HONEST on an empty mint.
                    repo_class=getattr(
                        repo_class_result, "repo_class", None),
                )
                # B69-v2 — pop the anchor-registry side-channel BEFORE the
                # tele reaches scan_meta / the stage artifact (live
                # SpineAnchor objects, consumed by the Stage 6.99b post-UF
                # rehome rail below; present only under
                # WYSTAN_HOMING_HYGIENE=1).
                _hh_anchor_registry = mint_tele.pop(
                    "homing_hygiene_anchor_registry", None)
                if mint_tele.get("applied"):
                    product_features = mint_pfs
                    anchored_mint_applied = True
                    anchored_hub_stamps = dict(
                        mint_tele.get("hub_family_stamps") or {})
                    # W4.2 Fix 1 — instrument dirs feed the emission
                    # classifier (dev_tooling scope) + the seed guards.
                    instrument_dirs = frozenset(
                        (mint_tele.get("technology_instruments") or {})
                        .get("dirs") or []
                    )
                    # B28 P-D — hub-fixture marks ride the same tele to
                    # the emission taxonomy (mark-only at 6.86; the
                    # R1/R2 rails + lane consumption live emission-side).
                    dev_artifact_units = frozenset(
                        (mint_tele.get("technology_instruments") or {})
                        .get("dev_artifact_units") or ()
                    )
                # Hardening marker (twenty dead-key forensics, REASONED pin):
                # the 6.86 flow-gated decisions (L1-rescue) read flow ABSENCE
                # as evidence absence — on a board with a FATAL stage-3
                # degradation (zero_cost_fresh_fail) those are structural
                # demotes on a blind signal. Behaviour is NOT changed (a DG1
                # board = discard-by-policy; a speculative mint would break
                # conservation) — the tele marker makes the blindness VISIBLE.
                if any(
                    r.get("severity") == "failed"
                    and "flows" in str(r.get("stage") or "")
                    for r in (scan_meta.get("degradations") or [])
                    if isinstance(r, dict)
                ):
                    mint_tele["flow_layer_degraded"] = True
                scan_meta["stage_6_86_anchored_mint"] = {
                    k: v for k, v in mint_tele.items()
                    if k != "hub_family_stamps"
                }
                log_mint.info(
                    "anchored_mint: applied=%s anchors=%d pf=%d "
                    "U=%d(cap=%d shell=%d) tie=%d none=%d folds(u=%d p=%d "
                    "i=%d) infra=%d churn=%.1f%%"
                    % (
                        mint_tele.get("applied"),
                        mint_tele.get("anchors_total", 0),
                        mint_tele.get("pf_minted", 0),
                        mint_tele.get("unique", 0),
                        mint_tele.get("unique_capability", 0),
                        mint_tele.get("unique_shell", 0),
                        mint_tele.get("near_tie", 0),
                        mint_tele.get("none", 0),
                        mint_tele.get("fold_union_plurality", 0),
                        mint_tele.get("fold_parent", 0),
                        mint_tele.get("fold_import", 0),
                        mint_tele.get("infra_lane", 0),
                        100.0 * mint_tele.get("churn_pct", 0.0),
                    ),
                    feature=None,
                )
                write_stage_artifact(
                    ctx.repo_path,
                    stage_index=6,
                    stage_name="anchored_mint",
                    payload={k: v for k, v in mint_tele.items()
                             if k != "hub_family_stamps"},
                    run_dir=run_dir,
                )
            except Exception as exc:  # noqa: BLE001 — never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"anchored-mint failed ({exc}); "
                    f"pre-spine product layer kept"
                )
                log_mint.info(
                    f"anchored_mint: FAILED ({exc}) — old product layer kept",
                    feature=None,
                )

    # B89 invariant stage-hooks — post-6.86 mint sentinels (short-name /
    # dev-anchor-no-evidence / ws-container-no-evidence). Pure over the
    # just-minted product_features; UF + nav_parent are stamped later so
    # these use the mint-grain evidence prongs. No-op when the flag is off.
    invariant_hooks.run_stage(
        scan_meta, "6.86", product_features=product_features)

    # B113 — silent-empty-board sentinel on its OWN seam key, fired only
    # when armed so the default world gains no ``invariant_hooks[]`` record
    # (byte-identity). Reads the mint's own stamped telemetry plus whether
    # anything already explains an empty board; both are in hand here.
    if invariant_hooks.mint_silent_empty_sentinel_enabled():
        invariant_hooks.run_stage(
            scan_meta, "6.86_mint_universe",
            mint_tele=(scan_meta.get("stage_6_86_anchored_mint") or {}),
            degraded=bool(scan_meta.get("degradations")),
        )

    # ── W4.3 — lane excavation (Product-Spine, w43-diagnosis) ──────────
    # With the lane stamped, lift PRODUCT back out of it: app-shell lane
    # groups grow domain-dir candidate anchors from their OWN content,
    # merged with the existing anchor set; every candidate faces the
    # SAME Stage-6.86 mint bar (incl. the W4.2 instrument dirs). Runs
    # BEFORE the flow-span split / UF family so every downstream stage
    # sees the excavated PFs. Kill-switch WYSTAN_LANE_EXCAVATION=0.
    if anchored_mint_applied:
        from wystan.pipeline_v2.lane_excavation import (
            lane_excavation_enabled,
            run_lane_excavation,
        )
        if lane_excavation_enabled():
            with StageLogger(run_dir, 6, "lane_excavation") as log_exc:
                try:
                    exc_tele = run_lane_excavation(
                        features, product_features,
                        lineage_result.routes_index, ctx,
                        extractor_signals=stage1_out,
                        instrument_dirs=instrument_dirs,
                        feature_flow_edges=list(bipartite.edges),
                    )
                    if exc_tele.get("groups"):
                        scan_meta["lane_excavation"] = exc_tele
                    log_exc.info(
                        "lane_excavation: groups=%d candidates=%d "
                        "minted=%d widened=%d moved=%d carved=%d "
                        "chunks=%d flows=%d loc=%d"
                        % (
                            exc_tele.get("groups", 0),
                            exc_tele.get("candidates", 0),
                            exc_tele.get("pfs_minted", 0),
                            exc_tele.get("pfs_widened", 0),
                            exc_tele.get("devs_moved", 0),
                            exc_tele.get("devs_carved", 0),
                            exc_tele.get("chunks", 0),
                            exc_tele.get("flows_excavated", 0),
                            exc_tele.get("loc_excavated", 0),
                        ),
                        feature=None,
                    )
                except Exception as exc:  # noqa: BLE001 — never break a scan
                    scan_meta.setdefault("warnings", []).append(
                        f"lane-excavation failed ({exc}); lane left as-is"
                    )
                    log_exc.info(
                        f"lane_excavation: FAILED ({exc}) — lane left as-is",
                        feature=None,
                    )

    # ── W4 — cross-PF flow-attribution split (Product-Spine §4.6) ──────
    # With the anchored mint's total dev→PF stamps in place, split every
    # flow whose file surface spans multiple PFs' anchors: primary =
    # home-PF files (entry-owner, dev fallback); other PFs' files move
    # to the labeled ``Flow.shared_paths[]`` ledger; foreign whole-file
    # span guesses leave the node surface. Runs BEFORE the UF family so
    # journey attach (I15/I16) and on-flow accounting (I19) consume the
    # split projection. Deterministic, $0 LLM; conservation-counted.
    # Kill-switch WYSTAN_FLOW_SPAN_SPLIT=0; anchored-mint-only.
    from wystan.pipeline_v2.flow_span_split import (
        flow_span_split_enabled,
        split_cross_pf_flow_attribution,
    )
    if anchored_mint_applied and flow_span_split_enabled():
        try:
            scan_meta["flow_span_split"] = split_cross_pf_flow_attribution(
                features, product_features,
            )
        except Exception as exc:  # noqa: BLE001 — never break a scan
            scan_meta.setdefault("warnings", []).append(
                f"flow-span split failed ({exc}); unsplit flow surface kept"
            )

    # ── B92 Rung B — dup-extraction twin-feature merge (SAME-PF) ───────
    # Merges collision-suffix twin dev features (``X`` / ``X-N``) that ALL
    # share ONE product_feature_id and overlap (path-Jaccard ≥ θ) into the
    # canonical, dedups the true-duplicate flows by (name, entry file:line),
    # and absorbs the B85 fold-husk siblings — then re-projects the bipartite
    # store. Runs post-6.86 mint (PF exists = the new safety signal) and
    # BEFORE the 6.7 UF rollup so the journey layer forms over the deduped
    # set (no UF re-pointing; the PF map is unchanged — both twins already
    # home on ONE PF). Multi-PF twin families and disjoint facets (J < θ)
    # are the named anti-cases and are NEVER merged. Kill-switch
    # WYSTAN_TWIN_FEATURE_MERGE (default OFF) → unset/=0 never runs the
    # pass (byte-identity with main). anchored-mint-only.
    from wystan.pipeline_v2.twin_collision import (
        apply_twin_feature_merge,
        twin_feature_merge_enabled,
    )
    if anchored_mint_applied and twin_feature_merge_enabled():
        with StageLogger(run_dir, 6, "twin_feature_merge") as log_tfm:
            try:
                _tfm_tele = apply_twin_feature_merge(features, bipartite)
                if _tfm_tele.get("merges") or _tfm_tele.get("husks_absorbed"):
                    scan_meta["twin_feature_merge"] = _tfm_tele
                log_tfm.info(
                    "twin_feature_merge: %d->%d features (merged=%d "
                    "husks=%d facets-kept=%d flows-deduped=%d)" % (
                        _tfm_tele["features_before"],
                        _tfm_tele.get("features_after", _tfm_tele["features_before"]),
                        _tfm_tele["features_merged"],
                        _tfm_tele["husks_absorbed"],
                        _tfm_tele["facets_kept_separate"],
                        _tfm_tele["flows_deduped"],
                    ),
                    feature=None,
                )
                write_stage_artifact(
                    ctx.repo_path,
                    stage_index=6,
                    stage_name="twin_feature_merge",
                    payload=_tfm_tele,
                    run_dir=run_dir,
                )
            except Exception as exc:  # noqa: BLE001 — never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"twin-feature-merge failed ({exc}); twins left as-is"
                )
                log_tfm.info(
                    f"twin_feature_merge: FAILED ({exc}) — twins left as-is",
                    feature=None,
                )

    # ── Stage 0.7 exit gate — UF-synthesis suppression (Phase C) ────
    # A CONFIDENT non-product repo_class verdict (library / cli-tool /
    # infra-daemon / framework) means this scan unit has no user
    # journeys to synthesize: the whole UF family (6.7 rollup, 6.7c
    # splitter, 6.7b refiner, 6.7d abstraction) is SKIPPED and
    # ``user_flows: []`` is emitted with an explicit
    # ``scan_meta.uf_suppressed_reason``. The developer-feature/flow
    # skeleton above is untouched. Fail-open by construction: ambiguous
    # verdicts classify product-app and never reach here; the
    # ``WYSTAN_REPO_CLASS_GATE=0`` kill-switch disables suppression
    # (the verdict itself is still emitted). Spec: StackProfile Phase C.
    from wystan.pipeline_v2.stage_0_7_repo_class import (
        should_suppress_user_flows,
        suppression_reason,
    )

    uf_suppressed = should_suppress_user_flows(repo_class_result)
    # B98 rung-I8 — a headless-product veto on suppression: a repo with a
    # route-API surface (the 6.86 headless verdict: a single page satellite
    # + route-dominant mass — ollama CLI/API/desktop) is NOT a journey-less
    # daemon; the journeys live on the API/CLI surface (keyed exhibit: 391
    # flows → 0 UF precisely because of repo_class:infra-daemon). The tele
    # key exists ONLY under the armed flag → the unset world is identical.
    if uf_suppressed and bool(
            ((scan_meta.get("stage_6_86_anchored_mint") or {})
             .get("headless_product_spine"))):
        uf_suppressed = False
        scan_meta["uf_suppression_lifted"] = "headless-product-spine"
    if uf_suppressed:
        uf_reason = suppression_reason(repo_class_result)
        scan_meta["uf_suppressed_reason"] = uf_reason
        uf_marker = {"suppressed": True, "reason": uf_reason}
        user_flows: list = []
        product_strings = None  # UF family skipped — no string index built
        with StageLogger(run_dir, 6, "user_flows") as log6_7:
            log6_7.info(
                "user_flows: SUPPRESSED (%s, confidence=%.2f) — "
                "non-product scan unit exits the product funnel; "
                "developer features/flows unaffected"
                % (uf_reason, repo_class_result.confidence),
            )
            write_stage_artifact(
                ctx.repo_path,
                stage_index=6,
                stage_name="user_flows",
                payload={
                    **uf_marker,
                    "repo_class": repo_class_result.repo_class,
                    "confidence": repo_class_result.confidence,
                    "user_flows": [],
                },
                run_dir=run_dir,
            )
        scan_meta["stage_6_7_user_flows"] = dict(uf_marker)
        scan_meta["stage_6_7c_uf_splitter"] = dict(uf_marker)
        scan_meta["stage_6_7b_uf_refiner"] = dict(uf_marker)

    # ── Stage 6.865 — B74 Seg B post-grain flow re-derivation (F3′) ────
    # Stage-8-born / re-membered dev features (path-set ≠ the unit Stage
    # 3 derived flows on — twenty object-record-2 49K loc / activities /
    # workflow-2 with 0 flows) re-run the EXISTING Stage-3 machinery
    # here, BETWEEN the 6.86 mint window and the Stage 6.7 UF family, so
    # the single existing mint sees the flows naturally (F3′ — zero new
    # mint channels). Flows land in feature.flows[] + the bipartite
    # mirror with Stage-3/5.5 writer identity. Full scans only (the
    # snapshot excludes spliced untouched features; cold-scan rule);
    # keyless scans run the deterministic cohort selection + candidate
    # enumeration and report them in scan_meta (honest no-client
    # degrade). Default ON since the 2026-07-21 pack-3 flip
    # (WYSTAN_FLOW_REDERIVE_POSTGRAIN, KEY_SCHEMA 34);
    # explicit =0 keeps the stage un-entered, byte-identical. Telemetry
    # key + artifact only when the causal gate fires (Seg C openstatus
    # inertness law).
    from wystan.pipeline_v2.flow_rederive import (
        flow_rederive_enabled,
        run_flow_rederive,
    )
    if (
        flow_rederive_enabled()
        and not uf_suppressed
        and is_full_scan
        and stage3_unit_snapshot is not None
    ):
        write_stage_input(run_dir, 6, "flow_rederive", {
            "features": features,
            "bipartite_flows": list(bipartite.flows),
            "bipartite_edges": list(bipartite.edges),
            "routes_index": lineage_result.routes_index,
            "scan_meta": scan_meta,
            "ctx": ctx,
            "stage3_unit_snapshot": stage3_unit_snapshot,
            "repo_path": str(repo_path),
            "model_id": model_id,
        })
        with StageLogger(run_dir, 6, "flow_rederive") as log_frd:
            try:
                frd_tele = run_flow_rederive(
                    features, bipartite.flows, bipartite.edges, ctx,
                    stage3_unit_snapshot=stage3_unit_snapshot,
                    model=model_id,
                    routes_index=lineage_result.routes_index,
                    tracker=tracker,
                    llm_health=llm_health,
                    log=log_frd,
                )
                if frd_tele is not None:
                    scan_meta["flow_rederive"] = frd_tele
                    write_stage_artifact(
                        ctx.repo_path,
                        stage_index=6,
                        stage_name="flow_rederive",
                        payload=frd_tele,
                        run_dir=run_dir,
                    )
                else:
                    log_frd.info(
                        "flow_rederive: no causal candidates — inert "
                        "(armed no-fire boards stay byte-identical)",
                        feature=None,
                    )
            except Exception as exc:  # noqa: BLE001 — never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"flow-rederive failed ({exc}); "
                    f"pre-rederive flow store kept"
                )
                log_frd.info(
                    f"flow_rederive: FAILED ({exc}) — flow store kept",
                    feature=None,
                )

    # ── Stage 6.7 — User-Flow rollup (Layer-2-for-flows, $0 LLM) ────
    # Deterministic post-pass: rolls the code-grain flow store up into
    # product-grain user_flows[] and stamps Flow.user_flow_id. Runs
    # after product_features (6.5) + bipartite store + test_strip so
    # domains, cross-links, and the final flow set all exist. Additive —
    # mirrors the developer_feature → product_feature model for flows.
    from wystan.pipeline_v2.product_strings import collect_product_strings
    from wystan.pipeline_v2.stage_6_7_user_flows import run_user_flow_rollup

    # Naming-evidence core (2026-06) — collect the product-string index
    # ONCE over every member file (features + flows) and share it with
    # Stage 6.7 (slot-consistent resource labels) and Stage 6.7b (UF
    # refiner evidence + name validation). Deterministic, $0 LLM,
    # README structurally excluded inside the collector.
    if not uf_suppressed:
        ps_candidates: set[str] = set()
        for f in features:
            ps_candidates.update(f.paths or [])
            ps_candidates.update(mf.path for mf in (f.member_files or []))
        for fl in bipartite.flows:
            ps_candidates.update(fl.paths or [])
            if fl.entry_point_file:
                ps_candidates.add(fl.entry_point_file)
        product_strings = collect_product_strings(repo_path, ps_candidates)

        user_flows: list = []
        write_stage_input(run_dir, 6, "user_flows", {
            "bipartite_flows": list(bipartite.flows),
            "features": features,
            "routes_index": lineage_result.routes_index,
            "scan_meta": scan_meta,
            "repo_path": str(repo_path),
        })
        with StageLogger(run_dir, 6, "user_flows") as log6_7:
            user_flows, uf_telemetry = run_user_flow_rollup(
                bipartite.flows, features,
                routes_index=lineage_result.routes_index,
                product_strings=product_strings,
            )
            log6_7.info(
                "user_flows: %d flows -> %d unique -> %d UF, %d domains, "
                "%d with cross_links (dedup_dropped=%d)"
                % (
                    uf_telemetry["total_flows"],
                    uf_telemetry["unique_flows"],
                    uf_telemetry["user_flows"],
                    uf_telemetry["domains"],
                    uf_telemetry["uf_with_cross_links"],
                    uf_telemetry["dedup_dropped"],
                ),
            )
            write_stage_artifact(
                ctx.repo_path,
                stage_index=6,
                stage_name="user_flows",
                payload={
                    **uf_telemetry,
                    "user_flows": [uf.model_dump() for uf in user_flows],
                },
                run_dir=run_dir,
            )
        scan_meta["stage_6_7_user_flows"] = dict(uf_telemetry)

        # ── Stage 6.7a — deterministic UF pre-clustering (S2 Seg A, OFF) ─
        # Under WYSTAN_UF_DET_AGGREGATION the journey STRUCTURE is folded
        # deterministically (one cluster per rollup domain, conservation-
        # complete member unions) and the LLM layer may ONLY NAME it: the
        # 6.7b refiner still refines presentation per domain (its contract
        # forbids membership changes), while the structural LLM stages —
        # 6.7c mega-split and the 6.7d journey rewrite — are SKIPPED below.
        # Consequence (probe 2026-07-18): UF-COUNT invariant to LLM death
        # (fail-open 264-vs-78 class dies structurally) and to resampling
        # (−26% whole-batch class). Default OFF → byte-identical.
        from wystan.pipeline_v2.stage_6_7a_det_aggregation import (
            aggregate_user_flows as _det_aggregate,
            det_aggregation_enabled as _det_agg_on,
        )
        if _det_agg_on() and user_flows:
            write_stage_input(run_dir, 6, "det_aggregation", {
                "user_flows": user_flows,
                "scan_meta": scan_meta,
            })
            with StageLogger(run_dir, 6, "det_aggregation") as log6_7a:
                user_flows, det_agg_telemetry = _det_aggregate(user_flows)
                log6_7a.info(
                    "det_aggregation: %d rollup UFs -> %d domain clusters "
                    "(%d merged, %d singleton; members %d -> %d; "
                    "scattered=%d)" % (
                        det_agg_telemetry["input_ufs"],
                        det_agg_telemetry["clusters"],
                        det_agg_telemetry["merged_clusters"],
                        det_agg_telemetry["singleton_clusters"],
                        det_agg_telemetry["members_in"],
                        det_agg_telemetry["members_out"],
                        det_agg_telemetry["scattered"],
                    ),
                )
                write_stage_artifact(
                    ctx.repo_path,
                    stage_index=6,
                    stage_name="det_aggregation",
                    payload={
                        **det_agg_telemetry,
                        "user_flows": [uf.model_dump() for uf in user_flows],
                    },
                    run_dir=run_dir,
                )
            # The fate map is per-input-UF detail — artifact-only; scan_meta
            # carries the counters (lean output law).
            scan_meta["stage_6_7a_det_aggregation"] = {
                k: v for k, v in det_agg_telemetry.items() if k != "fate"
            }

        # ── Stage 6.7c — Mega-UF semantic split (additive Sonnet) ──────
        # 6.7's deterministic clusterer over-merges genuinely-distinct journeys
        # into a few mega-UFs (cal.com: one 'availability' UF spanned 33
        # journeys). A handful of LLM calls partition ONLY those mega-mixed UFs
        # into per-journey sub-UFs (recall-safe — unplaced members fall to a
        # residual sub-UF, no flow dropped). Runs BEFORE 6.7b so the refiner
        # names the split UFs. Shared CostTracker; graceful degrade keeps the
        # mega-UF on any LLM failure. Measured F1 64→74 on cal.com vs uf-golden.
        # S2 Seg A: skipped under WYSTAN_UF_DET_AGGREGATION — the split is a
        # STRUCTURAL LLM decision; under det-aggregation the LLM only names.
        from wystan.pipeline_v2.stage_6_7c_uf_splitter import split_mega_user_flows
        # Content-hash LLM cache for the UF-path stages (6.7c split + 6.7b
        # refine): same backend Stage 3 / Stage 8 use (threaded on the scan
        # context by run.py). A warm entry replays the stage's PARSED LLM
        # output byte-identically at $0 on an unchanged repo; ``None`` (or the
        # per-stage env opt-outs) behaves exactly as pre-cache. Best-effort —
        # any cache fault inside the stages degrades to a live call.
        _uf_llm_cache = getattr(ctx, "cache_backend", None)
        if not _det_agg_on():
            write_stage_input(run_dir, 6, "uf_splitter", {
                "user_flows": user_flows,
                "bipartite_flows": list(bipartite.flows),
                "ctx": ctx,
                "scan_meta": scan_meta,
            })
            with StageLogger(run_dir, 6, "uf_splitter") as log6_7c:
                user_flows, uf_split_telemetry = split_mega_user_flows(
                    user_flows,
                    bipartite.flows,
                    cost_tracker=tracker,
                    log=log6_7c,
                    llm_health=llm_health,
                    cache=_uf_llm_cache,
                )
                write_stage_artifact(
                    ctx.repo_path,
                    stage_index=6,
                    stage_name="uf_splitter",
                    payload={
                        **uf_split_telemetry,
                        "user_flows": [uf.model_dump() for uf in user_flows],
                    },
                    run_dir=run_dir,
                )
            scan_meta["stage_6_7c_uf_splitter"] = dict(uf_split_telemetry)

        # ── Stage 6.7b — User-Flow LLM refiner (additive Haiku) ─────────
        # One Haiku call per domain over the deterministic 6.7 UF clusters:
        # journey-grain name/description, resolves intent="other", infers
        # ui_tier from the frontend surface, drafts AC from test-reach.
        # Membership/grain from 6.7 are NOT changed. Graceful per-domain
        # degrade: on any LLM failure the UFs keep their deterministic
        # name/intent. Uses the SAME shared CostTracker + model_id as the
        # rest of the LLM stages; no README, no .ai/specs.
        from wystan.pipeline_v2.stage_6_7b_uf_refiner import refine_user_flows
        write_stage_input(run_dir, 6, "uf_refiner", {
            "user_flows": user_flows,
            "bipartite_flows": list(bipartite.flows),
            "model_id": model_id,
            "ctx": ctx,
            "scan_meta": scan_meta,
            "features": features,
            "repo_path": str(repo_path),
            "is_full_scan": is_full_scan,
        })
        with StageLogger(run_dir, 6, "uf_refiner") as log6_7b:
            # ── Incremental UF-refiner reuse (--since path ONLY) ───────
            # Only domains with a changed UF still get a Haiku call — see
            # ``incremental_wiring.plan_uf_domain_allowlist``. On a full /
            # cold scan ``domain_allowlist`` stays None → every domain is
            # refined, byte-identical to before (cold-scan rule).
            uf_domain_allowlist: set[str | None] | None = None
            if not is_full_scan and incremental_base_scan is not None:
                uf_domain_allowlist = plan_uf_domain_allowlist(
                    user_flows, incremental_base_scan, log6_7b,
                )
            user_flows, uf_refine_telemetry = refine_user_flows(
                user_flows,
                bipartite.flows,
                model=model_id,
                cost_tracker=tracker,
                log=log6_7b,
                domain_allowlist=uf_domain_allowlist,
                llm_health=llm_health,
                product_strings=product_strings,
                cache=_uf_llm_cache,
            )
            write_stage_artifact(
                ctx.repo_path,
                stage_index=6,
                stage_name="uf_refiner",
                payload={
                    **uf_refine_telemetry,
                    "user_flows": [uf.model_dump() for uf in user_flows],
                },
                run_dir=run_dir,
            )
        scan_meta["stage_6_7b_uf_refiner"] = dict(uf_refine_telemetry)

    # ── §4.5 conservation on the ANCHORED KEYLESS path ($0) ─────────
    # With the anchored mint applied and 6.7d disabled (keyless scans),
    # the deterministic UF set must still obey the conservation law
    # against the anchored stamps: member flows' entries + span majority
    # inside the UF's PF closure, violators resettle, and no journey may
    # ride a lane resident (product_feature_id=None devs vote nothing —
    # terminal home binds the leftovers). The keyed path runs the same
    # law inside/after 6.7d, unchanged.
    from wystan.pipeline_v2.stage_6_7d_llm_journey_abstraction import (
        is_enabled as _s67d_enabled_probe,
    )
    from wystan.pipeline_v2.stage_6_7a_det_aggregation import (
        det_aggregation_enabled as _det_agg_probe,
    )
    # S2 Seg A: with det-aggregation ON the 6.7d rewrite is skipped even on
    # the keyed channel, so the §4.5 conservation law must run HERE against
    # the deterministic clusters (same law the keyless path enforces).
    if (anchored_mint_applied and not uf_suppressed
            and (not _s67d_enabled_probe() or _det_agg_probe())
            and user_flows):
        from wystan.pipeline_v2.conservation import apply_uf_conservation
        with StageLogger(run_dir, 6, "spine_conservation") as log_sc:
            try:
                sc_tele = apply_uf_conservation(
                    user_flows, features, product_features,
                    null_shared_without_signal=True,
                )
                scan_meta["spine_conservation_keyless"] = sc_tele
                log_sc.info(
                    "spine_conservation (keyless): %s" % (sc_tele,),
                    feature=None,
                )
            except Exception as exc:  # noqa: BLE001 — never break a scan
                log_sc.info(
                    f"spine_conservation: FAILED ({exc}) — continuing",
                    feature=None,
                )

    # ── Stage 6.7d — LLM product/journey abstraction (opt-in, OFF) ──
    # Crosses the code-grain → product-grain gap the deterministic stages
    # structurally cannot: REWRITES user_flows[] + product_features[] at
    # journey/capability grain via a Sonnet call (abstraction) + a Haiku call
    # (re-attribution) over a code-grounded
    # digest (NO README). Output-layer only — the central flows[] graph is
    # untouched. Default OFF; WYSTAN_STAGE_6_7D_LLM_ABSTRACTION=1. On any
    # LLM failure the deterministic arrays pass through byte-identical.
    from wystan.pipeline_v2.stage_6_7d_llm_journey_abstraction import (
        is_enabled as _s67d_enabled,
        run_journey_abstraction,
    )
    # S2 Seg A: under WYSTAN_UF_DET_AGGREGATION the 6.7d structural rewrite
    # is skipped — the journey structure is the deterministic 6.7a clusters and
    # the LLM layer (6.7b refiner) only NAMES them (fit = output-layer law).
    if _s67d_enabled() and not uf_suppressed and not _det_agg_probe():
        write_stage_input(run_dir, 6, "journey_abstraction", {
            "user_flows": user_flows,
            "product_features": product_features,
            "features": features,
            "routes_index": lineage_result.routes_index,
            "model_id": model_id,
            "scan_meta": scan_meta,
            "repo_path": str(repo_path),
        })
        with StageLogger(run_dir, 6, "journey_abstraction") as log6_7d:
            # A content-hash cache backend makes a re-scan of an unchanged repo
            # byte-identical (same digest + models → same key → replayed LLM
            # answers). Best-effort — a cache fault degrades to a live call.
            from wystan.cache import get_cache_backend
            try:
                _s67d_cache = get_cache_backend()
            except Exception:  # noqa: BLE001 — caching is best-effort, never fatal
                _s67d_cache = None
            # Phase 2 anchor-ingest (OPT-IN): mine deterministic product-capability
            # anchors → clean alignment pool ONLY when align is enabled (default OFF
            # — align degrades stability on noisy pools). Skip the file-walk cost on
            # the default free-gen path; extraction failure must never crash a scan.
            _s67d_anchors = None
            try:
                from wystan.pipeline_v2.stage_6_7d_llm_journey_abstraction import (
                    align_enabled,
                )
                if align_enabled():
                    from wystan.pipeline_v2.anchor_extractors import (
                        build_alignment_pool, extract_raw_anchors,
                    )
                    _s67d_anchors = build_alignment_pool(extract_raw_anchors(repo_path))
            except Exception:  # noqa: BLE001 — anchors are optional; degrade to free-gen
                _s67d_anchors = None
            # W4 §4.6 — page-interior sections extend the constrained
            # Call-1's citation vocabulary (anchored mode only). None
            # when Stage 6.55 was inactive → digest/prompt/cache stay
            # byte-identical to pre-W4.
            _s67d_interior = None
            if anchored_mint_applied and interior_result.active:
                try:
                    from wystan.pipeline_v2.stage_6_55_page_interior import (
                        build_interior_evidence,
                    )
                    _s67d_interior = build_interior_evidence(
                        interior_result, features, product_features,
                    )
                except Exception:  # noqa: BLE001 — evidence is optional
                    _s67d_interior = None
            (
                user_flows,
                product_features,
                s67d_dev_map,
                s67d_telemetry,
            ) = run_journey_abstraction(
                user_flows,
                product_features,
                features,
                lineage_result.routes_index,
                product_anchors=_s67d_anchors,
                model=model_id,
                cost_tracker=tracker,
                cache=_s67d_cache,
                log=log6_7d,
                llm_health=llm_health,
                # Product-Spine §4.3 (Wave 2b): with the anchored mint
                # applied, the PF universe is FIXED (Call-1 constrained
                # to cite it) and dev→PF comes from the lineage stamps —
                # Call-2, the per-item membership oracle (RC1), retires.
                anchored=anchored_mint_applied,
                interior_evidence=_s67d_interior,
            )
            # Re-stamp dev features' product_feature_id so the bipartite /
            # output linkage stays coherent with the rewritten product layer.
            if s67d_dev_map:
                for _dev in features:
                    _slugs = s67d_dev_map.get(getattr(_dev, "name", None))
                    if _slugs:
                        _dev.product_feature_id = _slugs[0]
            # Product-Spine §4.4 — re-enforce the hub/child relation on the
            # REWRITTEN product layer. ANCHORED path (operator amendment
            # 2026-07-06): every integration is its OWN sibling PF — the
            # mint's per-vendor family stamps are construction law, so we
            # re-assert THEM (never the W1 children-inherit-one-PF rule,
            # which would re-collapse the vendor grain). =0 path keeps the
            # W1 binding byte-identically.
            if s67d_telemetry.get("applied") and anchored_mint_applied:
                from wystan.pipeline_v2.stage_6_86_anchored_mint import (
                    enforce_hub_family_parity as _hub_parity,
                )
                _par_tele = _hub_parity(
                    features, product_features, anchored_hub_stamps)
                if _par_tele.get("checked"):
                    s67d_telemetry["hub_family_parity_post_67d"] = _par_tele
            elif s67d_telemetry.get("applied"):
                from wystan.pipeline_v2.hub_relation import (
                    apply_hub_pf_binding as _hub_bind,
                )
                _hub_tele = _hub_bind(features, product_features)
                if _hub_tele.get("hubs"):
                    s67d_telemetry["hub_binding_post_67d"] = _hub_tele
            if s67d_telemetry.get("applied"):
                # W1.1 — §4.5 at DEV grain (validator I9): Call-2 can
                # scatter a small flowful surface dev into the shared
                # bucket even when its flows' spans/entries sit inside ONE
                # real PF (RefApp dev 'api' → labels, 2026-07-06). Re-home
                # on the conservation ACCEPT bar BEFORE the UF pass so the
                # resettles below see the corrected ownership.
                from wystan.pipeline_v2.conservation import (
                    apply_uf_conservation as _apply_cons,
                    rehome_shared_flowful_devs as _rehome,
                )
                _rehome_tele = _rehome(features, product_features)
                if _rehome_tele.get("checked"):
                    s67d_telemetry["dev_rehome_finalize"] = _rehome_tele
                # Product-Spine §4.5 — final conservation pass: the hub
                # binding above moves dev→PF, so UF↔PF closures moved with
                # it; re-settle violators and null any residual
                # Shared-Platform attachment that no real PF's code
                # supports (a UF may never ship attached to shared).
                _cons_tele = _apply_cons(
                    user_flows, features, product_features,
                    null_shared_without_signal=True,
                )
                s67d_telemetry["conservation_finalize"] = _cons_tele
                # W1.1 — donor re-cover (W1 §E residual, predicted): the
                # conservation pass above can leave a flowful PF with zero
                # journeys (it resettles by span-LOC; the in-6.7d backstop
                # ran BEFORE this pass) — the 2026-07-06 validation wave
                # shipped 4 such donors on supabase + 1 on midday (I8).
                # Re-run the backstop AFTER conservation + hub binding,
                # then recheck: fixpoint in one pass (see
                # _recover_uncovered_donors).
                _donor_tele = _recover_uncovered_donors(
                    user_flows, features, product_features,
                )
                if _donor_tele is not None:
                    s67d_telemetry["donor_backstop_finalize"] = _donor_tele
                    # Fixpoint recheck — expected no-op (synthesized
                    # journeys are conservation-exempt; reassignments
                    # passed the same ladder on the same ownership state).
                    _recheck = _apply_cons(
                        user_flows, features, product_features,
                        null_shared_without_signal=True,
                    )
                    s67d_telemetry["conservation_recheck"] = _recheck
                # W4 §4.6 — post-UF span-split second pass: LANE-homed
                # member flows (no ownership evidence at the first pass)
                # adopt their conservation-settled journey's capability
                # as home; other PFs' files leave paths for the labeled
                # shared ledger. Runs AFTER the final conservation /
                # donor recheck so the adopted homes are settled.
                if anchored_mint_applied and flow_span_split_enabled():
                    try:
                        _lane_home: dict[str, str] = {}
                        for _uf in user_flows:
                            _pfid = getattr(_uf, "product_feature_id", None)
                            if not _pfid:
                                continue
                            for _mid in _uf.member_flow_ids or []:
                                _lane_home.setdefault(_mid, _pfid)
                        scan_meta["flow_span_split_post_uf"] = (
                            split_cross_pf_flow_attribution(
                                features, product_features,
                                home_override=_lane_home,
                            )
                        )
                    except Exception as exc:  # noqa: BLE001
                        scan_meta.setdefault("warnings", []).append(
                            f"post-UF flow-span split failed ({exc})"
                        )
            write_stage_artifact(
                ctx.repo_path,
                stage_index=6,
                stage_name="journey_abstraction",
                payload={
                    **s67d_telemetry,
                    "user_flows": [uf.model_dump() for uf in user_flows],
                    "product_features": [
                        {"name": pf.name, "display_name": pf.display_name,
                         "n_paths": len(pf.paths)}
                        for pf in product_features
                    ],
                },
                run_dir=run_dir,
            )
        # ``first_draw_spec`` (mission-92 retry observability) is artifact +
        # llm-cache ONLY — keep it out of scan_meta so the final scan JSON
        # stays lean and byte-unchanged even on keyed runs that retried.
        scan_meta["stage_6_7d_journey_abstraction"] = {
            k: v for k, v in s67d_telemetry.items() if k != "first_draw_spec"
        }

    # ── fixb126 — CLI command journeys (WYSTAN_CLI_ANCHOR_SUPPLY) ────
    # The journey half of the CLI anchor supply: a shipped command
    # surface arrived on the product map MUTE (ollama: 17 declared
    # commands, 0 journeys) because 6.7d's grounding drops the CLI rows
    # its own draw proposed and the PF-UF backstop can only offer a
    # member-less seed. One tagged journey per author-declared command
    # that a real flow implements; commands with no handler flow abstain.
    # Deterministic, $0, no LLM. Flag OFF ⇒ not called, no scan_meta key.
    if not uf_suppressed:
        from wystan.pipeline_v2.cli_command_journeys import (
            mint_cli_command_journeys,
        )
        try:
            _cli_uf_tele = mint_cli_command_journeys(
                ctx, user_flows, features, product_features)
        except Exception as exc:  # noqa: BLE001 — additive mint is best-effort
            _cli_uf_tele = {"error": str(exc)[:200]}
        if _cli_uf_tele:
            scan_meta["cli_command_journeys"] = _cli_uf_tele

        # ── fixb128 NS-4 — CLI home fence (same flag, same cluster) ────
        # A CLI tile may only home journeys of its OWN code: >= 1 member
        # flow must enter the cluster's evidence tree, the SAME
        # containment basis as the fixb126 sink-guard. Measured hole
        # (ollama c24): 'Run CLI commands and manage models' mc=10 with
        # 10/10 members in middleware/*.go and none under cmd/** — B24
        # FAIL 0.42. Runs HERE, not inside the 6.7d mint, because only
        # here do the journeys' member ids resolve against the bipartite
        # flow list (at the 6.7d seam 0 of 11 resolved — a fence that
        # cannot see members would judge on absence of evidence).
        # REHOMES, never demotes and never nulls.
        if not uf_suppressed:
            from wystan.pipeline_v2.cli_command_journeys import (
                fence_cli_foreign_journeys,
            )
            try:
                _cli_fence_tele = fence_cli_foreign_journeys(
                    ctx, user_flows, features, list(bipartite.flows))
            except Exception as exc:  # noqa: BLE001 — fence is best-effort
                _cli_fence_tele = {"error": str(exc)[:200]}
            if _cli_fence_tele:
                scan_meta["cli_home_fence"] = _cli_fence_tele

    # ── W3.1 D6 — route-group journey recall seeds (BOTH paths) ─────────
    # A >= 2-route product group no UF touches (tracecat tables/chat, the
    # comp Auditor class, supabase studio holes — validator I24) gets ONE
    # thin tagged seed journey built from the flows entering its own
    # files. Output-only (user_flows[] append), synthesized + low-
    # confidence tagged, real-PF-home required; groups with no flow
    # evidence or no PF home stay honest holes. Runs on the keyed AND
    # keyless paths — the hole class is path-independent.
    from wystan.pipeline_v2.route_group_recall import (
        route_group_seeds_enabled,
        seed_route_group_journeys,
    )
    # W4.2 Fix 2 — seed surface-guard: one classifier instance serves the
    # D6 + D9 seed channels (home-PF scope + instrument dirs). ``None``
    # under the taxonomy kill-switch → both guards no-op (pre-W4.2 path).
    from wystan.pipeline_v2.surface_taxonomy import (
        SurfaceScopeClassifier as _SeedClf,
        _route_by_file as _seed_rbf_of,
        taxonomy_enabled as _seed_taxonomy_enabled,
    )
    seed_clf = None
    seed_rbf: dict[str, Any] = {}
    if _seed_taxonomy_enabled():
        try:
            seed_clf = _SeedClf(
                repo_path=repo_path,
                routes_index=lineage_result.routes_index,
                instrument_dirs=instrument_dirs,
            )
            seed_rbf = dict(_seed_rbf_of(lineage_result.routes_index))
        except Exception:  # noqa: BLE001 — guard is best-effort
            seed_clf = None
    # B101 — ``and not uf_suppressed`` restores the EXISTING contract this
    # was the only UF-mint call site in finalize to miss (20+ siblings carry
    # it). A suppressed repo class empties user_flows[] above; this recall
    # then refilled it from route groups — fastapi ships
    # uf_suppressed_reason="repo_class:framework" AND 55 journeys seeded off
    # docs_src/** tutorials. Not a flag: an invariant re-asserted.
    # The guard covers the SEEDING work only; the B89 sentinel keeps its
    # own (unchanged) arming condition below — it is a standing board-state
    # guard whose record with zero seeds is an honest 0, and suppressing it
    # too would drop a scan_meta record on EVERY suppressed board, far wider
    # than this bug's class.
    if route_group_seeds_enabled() and not uf_suppressed:
        # B69-v2 SPLIT ruling — the seed-birth hygiene pair (same-
        # (pf,resource) coalescence + method-derived intent) is the
        # SEED_HYGIENE family: board-wide blast radius at seeding, its
        # own flag and its own cycle, independent of the surgical 6.99b
        # HOMING rail (the keyed A/B showed the pair driving board churn
        # on both repos while the rail itself was exactly-one-action).
        from wystan.pipeline_v2.route_group_recall import (
            recall_transport_skip_enabled as _recall_transport_skip,
            seed_hygiene_enabled as _seed_hh,
        )
        # B88 — transport-donor seed guard (WYSTAN_RECALL_TRANSPORT_SKIP,
        # default OFF). This stage runs BEFORE ws_blob_drain, so its
        # matched-dirs telemetry does not yet exist; the resolver recomputes
        # the SAME B80 transport-donor detection + domain echo-match inline
        # (read-only, no mutation). Unset / no transport donor ⇒ None ⇒
        # byte-identical.
        _transport_resolver = None
        if _recall_transport_skip():
            from wystan.pipeline_v2.ws_blob_domain_drain import (
                build_transport_donor_resolver,
            )
            try:
                _transport_resolver = build_transport_donor_resolver(
                    product_features, features, ctx)
            except Exception:  # noqa: BLE001 — guard is best-effort
                _transport_resolver = None
        with StageLogger(run_dir, 6, "route_group_recall") as log_rgr:
            rgr_tele = seed_route_group_journeys(
                user_flows, features, product_features,
                list(bipartite.flows), lineage_result.routes_index,
                scope_classifier=seed_clf, route_by_file=seed_rbf,
                coalesce_same_pf_resource=_seed_hh(),
                derive_seed_intent=_seed_hh(),
                transport_resolver=_transport_resolver,
            )
            if rgr_tele.get("holes") or rgr_tele.get("seeded"):
                scan_meta["route_group_recall"] = rgr_tele
            log_rgr.info(
                f"route-group recall: groups>=2 {rgr_tele.get('groups_ge2')}"
                f" holes {rgr_tele.get('holes')} seeded {rgr_tele.get('seeded')}"
                f" (no-flows {rgr_tele.get('skipped_no_flows')},"
                f" no-pf {rgr_tele.get('skipped_no_pf')},"
                f" non-product {rgr_tele.get('skipped_non_product_home')})",
            )
    # B89 sentinel — a synthetic recall seed homed onto a transport-donor
    # PF (the B88 class); stays a standing guard even with B88 armed. Its
    # arming condition is UNCHANGED by B101 (stage armed ⇒ sentinel fires),
    # so suppressed boards keep the record they always carried.
    if route_group_seeds_enabled():
        invariant_hooks.run_stage(
            scan_meta, "route_group_recall",
            product_features=product_features, user_flows=user_flows)

    # ── W3.2 — UF-evidence lane re-homing (anchored paths, BOTH) ───────
    # The W3.1 sink-kill parked the freed mass in the lane (corpus 85K →
    # 1.94M LOC); the journey-evidenced slice of it (final UFs citing a
    # lane dev's files, one-PF majority, self-evident, capacity-capped)
    # re-homes to the capability its journeys ride, provenance
    # ``fold:uf-evidence``. Runs AFTER 6.7d + route-group seeds (the
    # citations must reflect the FINAL journey layer) and BEFORE 6.97 so
    # loc accounting stamps the moved membership (loc-truth I13).
    # Deterministic, $0. Kill-switch: WYSTAN_SPINE_LANE_REHOME=0.
    if anchored_mint_applied and not uf_suppressed:
        from wystan.pipeline_v2.lane_rehome import (
            lane_rehome_enabled,
            rehome_uf_cited_lane_devs,
        )
        if lane_rehome_enabled():
            with StageLogger(run_dir, 6, "lane_rehome") as log_lr:
                try:
                    lr_tele = rehome_uf_cited_lane_devs(
                        features, product_features, user_flows,
                        list(bipartite.flows), repo_path=repo_path,
                    )
                    scan_meta["lane_rehome"] = lr_tele
                    log_lr.info(
                        "lane_rehome: checked %d rehomed %d (%d LOC) "
                        "blocked conc=%d self=%d target=%d cap=%d" % (
                            lr_tele.get("checked", 0),
                            lr_tele.get("rehomed", 0),
                            lr_tele.get("rehomed_loc", 0),
                            lr_tele.get("blocked_concentration", 0),
                            lr_tele.get("blocked_self_evidence", 0),
                            lr_tele.get("blocked_target", 0),
                            lr_tele.get("blocked_cap", 0),
                        ),
                    )
                except Exception as exc:  # noqa: BLE001 — never break a scan
                    log_lr.info(
                        f"lane_rehome: FAILED ({exc}) — lane left as-is",
                        feature=None,
                    )

    # S3 arbiter — apply deferred proposals at this pass boundary
    # (rung-priority == pass order; no-op when the flag is OFF).
    _arb_flush(product_features, note="post-lane-rehome")

    # ── Track-A A1 — provenance re-home (import-graph channel) ─────────
    # Complements lane_rehome's UF-CITATION channel with the ts_ast
    # IMPORT-GRAPH channel: a lane entry file re-homes to the journey PF it
    # provenance-connects to (imports that PF's first-party domain package)
    # ONLY when the journey layer unanimously agrees (confirmation-gated →
    # can only turn a FOREIGN entry NATIVE, never the reverse). Same window
    # as lane_rehome — AFTER the final journey layer, BEFORE 6.97 loc so the
    # moved membership is loc-stamped. Kill-switch WYSTAN_PROV_ATTACH=0.
    if anchored_mint_applied and not uf_suppressed:
        from wystan.pipeline_v2.provenance_rehome import (
            prov_attach_enabled,
            run_provenance_rehome,
        )
        if prov_attach_enabled():
            with StageLogger(run_dir, 6, "provenance_rehome") as log_prh:
                try:
                    prh_tele = run_provenance_rehome(
                        user_flows, features, product_features, ctx,
                    )
                    if prh_tele.get("entries_rehomed"):
                        scan_meta["provenance_rehome"] = prh_tele
                    log_prh.info(
                        "provenance_rehome: confirmed %d rehomed %d "
                        "pfs_widened %d skip(conflict=%d owned=%d) ties=%d" % (
                            prh_tele.get("entries_confirmed", 0),
                            prh_tele.get("entries_rehomed", 0),
                            prh_tele.get("pfs_widened", 0),
                            prh_tele.get("skipped_journey_conflict", 0),
                            prh_tele.get("skipped_owned", 0),
                            prh_tele.get("abstained_ties", 0),
                        ),
                        feature=None,
                    )
                except Exception as exc:  # noqa: BLE001 — never break a scan
                    log_prh.info(
                        f"provenance_rehome: FAILED ({exc}) — lane left as-is",
                        feature=None,
                    )

    # ── Stage 6.88 — sibling-anchor capability unification (B16 Part 2) ──
    # Collapse co-identity sibling route PFs (RefApp investigation /
    # investigations-page / investigation-flow -> ONE) BEFORE 6.97 so the
    # merged body is loc-stamped / role-lane'd / path_index'd / I23-read as one
    # PF. Anchored path only; kill-switch WYSTAN_PF_SIBLING_UNIFY=0.
    if anchored_mint_applied:
        from wystan.pipeline_v2.stage_6_88_sibling_unify import (
            sibling_unify_enabled,
            unify_sibling_anchors,
        )
        if sibling_unify_enabled():
            try:
                su_tele = unify_sibling_anchors(
                    user_flows, features, product_features)
                if su_tele.get("merged_away"):
                    scan_meta["sibling_unify"] = su_tele
            except Exception as exc:  # noqa: BLE001 — never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"sibling-unify failed ({exc}); PFs left separate")

    # S3 arbiter — apply deferred proposals at this pass boundary
    # (rung-priority == pass order; no-op when the flag is OFF).
    _arb_flush(product_features, note="post-6.88-unify")

    # ── W3.2 D9 — system journeys survive the keyed rewrite (BOTH paths) ──
    # wave31: 6.8b stamped system routes on 6/10 repos yet output carried
    # ZERO system-category UFs — the 6.7d rewrite rebuilds user_flows[]
    # from LLM journey specs and eats the thin member-less system seeds
    # the rollup minted (RefApp's 11 flow-less inngest jobs: matched, minted,
    # dropped). Same post-6.7d slot that keeps the route-group seeds
    # alive: re-mint what the rewrite dropped (dedup-aware — a keyless
    # pipeline that kept the rollup output no-ops) and re-stamp the
    # deterministic trigger verdicts onto rebuilt journeys whose member
    # flows ride system routes (unanimous-evidence bar). Deterministic,
    # $0 LLM. Kill-switch: WYSTAN_SEED_SYSTEM_UFS=0 (shared with the
    # rollup synthesis).
    if not uf_suppressed:
        from wystan.pipeline_v2.stage_6_7_user_flows import (
            restamp_system_triggers,
            resynthesize_system_ufs,
        )
        with StageLogger(run_dir, 6, "system_uf_recall") as log_sys:
            try:
                sys_stamp_tele = restamp_system_triggers(
                    user_flows, list(bipartite.flows),
                    lineage_result.routes_index,
                )
                sys_mint_tele = resynthesize_system_ufs(
                    user_flows, list(bipartite.flows), features,
                    lineage_result.routes_index,
                    instrument_dirs=instrument_dirs,
                    scope_classifier=seed_clf,
                    route_by_file=seed_rbf,
                    product_features=product_features,
                )
                if (sys_mint_tele.get("minted")
                        or sys_mint_tele.get("skipped_existing")
                        or sys_stamp_tele.get("stamped")):
                    scan_meta["system_uf_recall"] = {
                        **sys_mint_tele, **sys_stamp_tele,
                    }
                log_sys.info(
                    "system_uf_recall: minted %d (skipped_existing %d, "
                    "instrument %d, non-product %d), "
                    "triggers re-stamped %d" % (
                        sys_mint_tele.get("minted", 0),
                        sys_mint_tele.get("skipped_existing", 0),
                        sys_mint_tele.get("skipped_instrument", 0),
                        sys_mint_tele.get("skipped_non_product_home", 0),
                        sys_stamp_tele.get("stamped", 0),
                    ),
                )
            except Exception as exc:  # noqa: BLE001 — never break a scan
                log_sys.info(
                    f"system_uf_recall: FAILED ({exc}) — continuing",
                    feature=None,
                )

    # ── W4.2 — post-UF vendor-husk fold (operator exhibit: midday Enable
    # Banking I8). After 6.7d + EVERY seed channel the journey layer is
    # settled — a flowless hub-vendor child no journey cites folds under
    # its hub core / nearest enclosing minted capability (the same place
    # D4 sends sub-floor husks at mint time). Runs BEFORE Stage 6.97 so
    # the dual-LOC accounting re-truths itself. Deterministic, $0.
    # Kill-switch: WYSTAN_HUSK_POST_UF_FOLD=0.
    if anchored_mint_applied and not uf_suppressed:
        from wystan.pipeline_v2.stage_6_86_anchored_mint import (
            fold_unreferenced_vendor_husks,
            husk_post_uf_fold_enabled,
        )
        if husk_post_uf_fold_enabled():
            with StageLogger(run_dir, 6, "husk_post_uf_fold") as log_hf:
                try:
                    hf_tele = fold_unreferenced_vendor_husks(
                        features, product_features, user_flows,
                    )
                    if hf_tele.get("folded") or hf_tele.get("no_target"):
                        scan_meta["husk_post_uf_fold"] = hf_tele
                    log_hf.info(
                        "husk_post_uf_fold: %d folded / %d checked "
                        "(no_target %d)" % (
                            len(hf_tele.get("folded", [])),
                            hf_tele.get("checked", 0),
                            hf_tele.get("no_target", 0),
                        ),
                    )
                except Exception as exc:  # noqa: BLE001 — never break a scan
                    log_hf.info(
                        f"husk_post_uf_fold: FAILED ({exc}) — continuing",
                        feature=None,
                    )

    # ── Stage 6.885b — ws-app blob domain-dir member drain (B53 Seg A) ──
    # Re-attribute a ws-blob donor's internal domain-dir members
    # (``<pkg>/<container>/<domain>/**``) onto the EXISTING PF whose identity
    # the domain name echoes (same NamespaceEcho matcher). Runs HERE — v3:
    # AFTER the post-UF vendor-husk fold above, so the drain's target set ==
    # the OFF-emission PF SURVIVOR set by construction (PF-survival
    # invariance: typebot 'popup' was a foldable flowless husk the v2 drain
    # fattened +203 LOC BEFORE the fold, sparing a PF row that does not
    # exist on the OFF board — the drain must only re-attribute members of
    # PFs that would exist anyway, never change which PFs survive). Still
    # BEFORE the journey lattice / Stage 6.97 LOC (owned-LOC reflects the
    # drain) / the path_index rebuild + Stage 6.99 I16 re-home (which
    # carries the drained journeys onto their real PF via path_index → dev
    # → pfid; NO new journey mover, B52 law). NO mints; the package tile
    # survives (B42 territory). Kill-switch
    # WYSTAN_WS_BLOB_DOMAIN_DRAIN=0 (default) → byte-identical.
    if anchored_mint_applied and not uf_suppressed:
        from wystan.pipeline_v2.stage_6_86_anchored_mint import (
            sameunit_domain_cap_enabled,
        )
        from wystan.pipeline_v2.ws_blob_domain_drain import (
            run_ws_blob_domain_drain,
            ws_blob_domain_drain_enabled,
        )
        # B58-v2: the same pass carries the same-unit domain-dir cap
        # (donor class 2) — either flag alone arms the call; each class
        # runs only under its own switch (independent kill-switches).
        _wbd_on = ws_blob_domain_drain_enabled()
        _cap_on = sameunit_domain_cap_enabled()
        if _wbd_on or _cap_on:
            with StageLogger(run_dir, 6, "ws_blob_drain") as log_wbd:
                try:
                    wbd_tele = run_ws_blob_domain_drain(
                        features, product_features, user_flows,
                        list(bipartite.flows), ctx,
                        # v2: the literal 6.8 index — a file carrying a
                        # NON-donor entry is never touched; ABSENCE is the
                        # unattributed subtree mass that rolls to the blob.
                        path_index=lineage_result.path_index,
                        ws_blob=_wbd_on,
                        sameunit_cap=_cap_on,
                        # B58-v2 nav-only telemetry rung: the SAME
                        # normalized nav keys the mint received (bound
                        # above whenever anchored_mint_applied is True).
                        nav_keys=frozenset(_nav_keys),
                    )
                    if wbd_tele.get("files_moved"):
                        scan_meta["ws_blob_drain"] = wbd_tele
                    log_wbd.info(
                        "ws_blob_drain: donors=%d dirs=%d files=%d loc=%d "
                        "ufs(proj)=%d skip(gen=%d ambig=%d)" % (
                            len(wbd_tele.get("donors", [])),
                            len(wbd_tele.get("matched_dirs", {})),
                            wbd_tele.get("files_moved", 0),
                            wbd_tele.get("loc_moved", 0),
                            wbd_tele.get("ufs_rehomed", 0),
                            wbd_tele.get("skipped_generic", 0),
                            wbd_tele.get("skipped_ambig", 0),
                        ),
                        feature=None,
                    )
                except Exception as exc:  # noqa: BLE001 — never break a scan
                    log_wbd.info(
                        f"ws_blob_drain: FAILED ({exc}) — blob left as-is",
                        feature=None,
                    )

    # ── Stage 6.88 — journey lattice (Product-Spine W5) ────────────────
    # Post-abstraction DETERMINISTIC partition of catch-all journeys +
    # exact subset-duplicate merge (the 6.7d prior is "one journey per
    # capability" — its jpf corrective says so verbatim — so 47-member
    # catch-alls ship unrecognizable; A3 panel SEV-1 class). Runs AFTER
    # 6.7d + every seed channel + the husk fold (the journey layer is
    # settled) and BEFORE dual-evidence / keeper / taxonomy / naming so
    # the new journeys ride every downstream polish (scoping, display
    # laws, the I14 backpointer rewrite). Membership only ever
    # PARTITIONS existing journeys — flows keep their spans/LOC (W1
    # law); the keyed personas only NAME (PM Labeler) and REVIEW a
    # split plan (Draft Verifier; reject → the catch-all survives
    # untouched). Deterministic + $0 keyless. Kill-switch:
    # WYSTAN_JOURNEY_LATTICE=0 (pre-W5 output byte-identical).
    from wystan.pipeline_v2.journey_lattice import (
        dedup_lattice_journeys,
        fold_thin_lattice_children,
        journey_lattice_enabled,
        run_journey_lattice,
    )
    if not uf_suppressed and journey_lattice_enabled():
        write_stage_input(run_dir, 6, "journey_lattice", {
            "user_flows": user_flows,
            "product_features": product_features,
            "scan_meta": scan_meta,
        })
        with StageLogger(run_dir, 6, "journey_lattice") as log_jl:
            try:
                _jl_interior = None
                if interior_result.active:
                    from wystan.pipeline_v2.stage_6_55_page_interior import (
                        build_interior_evidence as _jl_evidence,
                    )
                    try:
                        _jl_interior = _jl_evidence(
                            interior_result, features, product_features,
                        )
                    except Exception:  # noqa: BLE001 — evidence is optional
                        _jl_interior = None
                # Wave-3 personas (keyed scans only; keyless builders
                # return None → deterministic templates, unreviewed
                # splits — the engine is deterministic by construction).
                _jl_labeler = None
                _jl_verifier = None
                try:
                    from wystan.pipeline_v2.personas import (
                        build_draft_verifier as _jl_bdv,
                        build_pm_labeler as _jl_bpl,
                    )
                    _jl_cache = getattr(ctx, "cache_backend", None)
                    _jl_verifier = _jl_bdv(
                        model_id=model_id,
                        cost_tracker=tracker,
                        cache=_jl_cache,
                        llm_health=llm_health,
                        log=log_jl,
                    )
                    _jl_labeler = _jl_bpl(
                        model_id=model_id,
                        cost_tracker=tracker,
                        cache=_jl_cache,
                        llm_health=llm_health,
                        log=log_jl,
                        thesis=scan_meta.get("product_thesis"),
                        verifier=_jl_verifier,
                    )
                except Exception:  # noqa: BLE001 — personas are optional
                    _jl_labeler = None
                    _jl_verifier = None
                jl_tele = run_journey_lattice(
                    user_flows, features, product_features,
                    lineage_result.routes_index,
                    interior_evidence=_jl_interior,
                    labeler=_jl_labeler,
                    verifier=_jl_verifier,
                )
                if jl_tele.get("applied"):
                    # §4.5 — children resettle to the capability their
                    # member spans live in (the same ruler as the 6.7d
                    # finalize pass), then the post-resettle same-key
                    # dedup, then the donor backstop (a dissolved
                    # catch-all must never leave a flowful PF with zero
                    # journeys — I8 stays green by construction).
                    from wystan.pipeline_v2.conservation import (
                        apply_uf_conservation as _jl_cons,
                    )
                    jl_tele["conservation_after"] = _jl_cons(
                        user_flows, features, product_features,
                        null_shared_without_signal=True,
                    )
                    jl_tele["dedup_after"] = dedup_lattice_journeys(
                        user_flows)
                    # W5.1 — a child the resettle/dedup stripped to a single
                    # sub-150-LOC member is a shred; fold it back into a
                    # sibling of the same PF (conservation-safe, never the
                    # PF's only journey).
                    jl_tele["thin_fold_after"] = fold_thin_lattice_children(
                        user_flows, list(bipartite.flows))
                    _jl_donor = _recover_uncovered_donors(
                        user_flows, features, product_features,
                    )
                    if _jl_donor is not None:
                        jl_tele["donor_backstop_after"] = _jl_donor
                scan_meta["journey_lattice"] = jl_tele
                log_jl.info(
                    "journey_lattice: pfs %d, subset_merged %d, "
                    "catchalls %d detected / %d split, +%d journeys "
                    "(%d members), dissolved %d, residual-kept %d, "
                    "verifier_rejects %d" % (
                        jl_tele.get("pfs_scanned", 0),
                        jl_tele.get("subset_merged", 0),
                        jl_tele.get("catchalls_detected", 0),
                        jl_tele.get("catchalls_split", 0),
                        jl_tele.get("journeys_created", 0),
                        jl_tele.get("members_moved", 0),
                        jl_tele.get("parents_dissolved", 0),
                        jl_tele.get("parents_kept_residual", 0),
                        jl_tele.get("verifier_rejects", 0),
                    ),
                    feature=None,
                )
                write_stage_artifact(
                    ctx.repo_path,
                    stage_index=6,
                    stage_name="journey_lattice",
                    payload=dict(jl_tele),
                    run_dir=run_dir,
                )
            except Exception as exc:  # noqa: BLE001 — lattice never breaks a scan
                scan_meta.setdefault("warnings", []).append(
                    f"journey-lattice failed ({exc}); journeys unpartitioned"
                )
                log_jl.info(
                    f"journey_lattice: FAILED ({exc}) — continuing",
                    feature=None,
                )

    # ── fixb119 M1 — journey-layer snapshot for the lineage audit ──────
    # Seam: IMMEDIATELY AFTER the lattice (and outside its if — the snapshot
    # is needed even when the lattice is off/suppressed). Not earlier: the
    # journey_abstraction → journey_lattice window is a LAWFUL wholesale
    # re-derivation of the entire layer (probe P15: 580 "deaths" on 8
    # boards) and the sentinel would drown in that noise (B33 — do not judge
    # the journey layer until it settles). Flag OFF ⇒ registry None ⇒ no reads.
    from wystan.pipeline_v2.journey_lineage_audit import (
        install_journey_lineage_registry as _jla_install,
        snapshot_post_lattice as _jla_snapshot,
    )
    try:
        # install ALWAYS runs right before the snapshot and ALWAYS
        # reassigns: if a previous scan on this thread died before its
        # teardown, its snapshot would otherwise be reconciled against THIS
        # board (the fixb118 class — a registry must not leak between scans).
        _jla_install()
        _jla_snapshot(user_flows)
    except Exception as exc:  # noqa: BLE001 — the audit never breaks a scan
        scan_meta.setdefault("warnings", []).append(
            f"journey-lineage snapshot failed ({exc}); audit disarmed"
        )

    # ── S2 Seg A iter-3 — readability regrain (panel-spot blockers) ─────
    # Deterministic, $0, right after the lattice, ONLY under
    # WYSTAN_UF_DET_AGGREGATION: (B2) lattice ACTION-axis CRUD leaves of
    # one (pf, resource) collapse into 'Manage <resource>' unless a leaf is
    # route-anchored; (B1/B3) any journey over READABILITY_MC_BAR splits by
    # member name-token families, children named from their OWN members (the
    # 'Send cases' mc=33 misname class dies; buried spine families resurface
    # as first-class rows); (B2 display) the raw 'lattice:*' token never
    # ships in the domain field. Unset -> pass never runs -> byte-identical.
    if _det_agg_probe() and user_flows:
        from wystan.pipeline_v2.naming_contract import (
            _verb_class_tokens as _rg_verbs,
            load_naming_vocab as _rg_vocab,
        )
        from wystan.pipeline_v2.stage_6_7a_det_aggregation import (
            readability_regrain,
        )
        with StageLogger(run_dir, 6, "readability_regrain") as log_rg:
            try:
                _rg_tele = readability_regrain(
                    user_flows, list(bipartite.flows), _rg_verbs(_rg_vocab()),
                )
                scan_meta["stage_6_7a_readability_regrain"] = _rg_tele
                log_rg.info(
                    "readability_regrain: crud collapsed %d, %d parents "
                    "split -> %d children (%d members), domains sanitized "
                    "%d, members_lost=%d" % (
                        _rg_tele["crud_collapse"]["collapsed_children"],
                        _rg_tele["oversplit"]["parents_split"],
                        _rg_tele["oversplit"]["children_minted"],
                        _rg_tele["oversplit"]["members_moved"],
                        _rg_tele["domains_sanitized"],
                        _rg_tele["members_lost"],
                    ),
                    feature=None,
                )
            except Exception as exc:  # noqa: BLE001 — regrain never breaks a scan
                log_rg.info(
                    f"readability_regrain: FAILED ({exc}) — continuing",
                    feature=None,
                )

    # ── Phase 3 — DUAL-EVIDENCE + confidence (OPT-IN, deterministic, $0 LLM) ──
    # Attach code + product-source anchor corroboration + a confidence score to
    # the final product features / user flows. Anchors are EVIDENCE here (a match
    # confirms a name), not a naming constraint — safe on noisy pools. Best-effort.
    from wystan.pipeline_v2.dual_evidence import dual_evidence_enabled
    if dual_evidence_enabled():
        write_stage_input(run_dir, 6, "dual_evidence", {
            "product_features": product_features,
            "user_flows": user_flows,
            "scan_meta": scan_meta,
            "repo_path": str(repo_path),
        })
        with StageLogger(run_dir, 6, "dual_evidence") as log_de:
            try:
                from wystan.pipeline_v2.anchor_extractors import (
                    build_alignment_pool, extract_raw_anchors,
                )
                from wystan.pipeline_v2.dual_evidence import attach_dual_evidence
                _de_anchors = build_alignment_pool(extract_raw_anchors(repo_path))
                de_stats = attach_dual_evidence(product_features, user_flows, _de_anchors)
                scan_meta["stage_dual_evidence"] = dict(de_stats)
                log_de.info(
                    "dual_evidence: pf %d/%d, uf %d/%d corroborated" % (
                        de_stats["pf_corroborated"], de_stats["pf"],
                        de_stats["uf_corroborated"], de_stats["uf"]),
                    feature=None)
            except Exception as _de_exc:  # noqa: BLE001 — evidence is best-effort, never fatal
                log_de.info(f"dual_evidence skipped: {_de_exc}", feature=None)

    # ── Stage 6.98 — E2E-journey truth (deterministic, $0 LLM) ──────
    # Maintainer-authored playwright/cypress journeys as UF evidence:
    # matched journeys CONFIRM UFs (uf_e2e_evidence in the stage
    # artifact); journeys no UF claims are NAMED recall holes
    # (orphan_journeys[]). Runs after the journey layer is fully
    # settled (post 6.7d/seeds/husk-fold — same vantage as
    # dual_evidence, BEFORE the 6.97 LOC prefetch below). Repos without
    # e2e specs report e2e_absent, zero impact. Kill-switch
    # WYSTAN_E2E_TRUTH=0 ⇒ byte-identical.
    from wystan.pipeline_v2.e2e_truth import (
        e2e_truth_enabled, matched_authored_names, orphan_uf_enabled,
        run_e2e_truth, scan_meta_view, synthesize_orphan_journeys,
    )
    # Track C — maintainer-authored journey display names ({uf_id: [labels]}),
    # consumed by the naming contract's authored channel at Stage 7 (below).
    _e2e_authored_names: dict[str, list[str]] = {}
    e2e_payload: dict[str, Any] | None = None
    if e2e_truth_enabled():
        with StageLogger(run_dir, 6, "e2e_truth") as log_e2e:
            try:
                e2e_payload = run_e2e_truth(
                    repo_path, user_flows,
                    routes_index=lineage_result.routes_index,
                    flows=list(bipartite.flows),
                )
                scan_meta["e2e_truth"] = scan_meta_view(e2e_payload)
                write_stage_artifact(
                    repo_path, 6, "e2e_truth", e2e_payload,
                    run_dir=run_dir,
                )
                log_e2e.info(
                    "e2e_truth: specs=%d journeys=%d matched=%d "
                    "orphans=%d absent=%s" % (
                        e2e_payload["spec_files"],
                        e2e_payload["journeys"],
                        e2e_payload["counts"]["matched"],
                        e2e_payload["counts"]["orphans"],
                        e2e_payload["e2e_absent"],
                    ),
                    feature=None,
                )
            except Exception as exc:  # noqa: BLE001 — never break a scan
                log_e2e.info(
                    f"e2e_truth: FAILED ({exc}) — continuing", feature=None,
                )

    # ── Stage 6.98b — orphan-journey → UF synthesis (Track C, recall) ──
    # Each groundable orphan journey (maintainer-named recall hole) becomes
    # a tagged, PF-bound member-less UserFlow so the board/panel surfaces it.
    # Deterministic, $0 LLM, additive. Runs immediately after e2e_truth (its
    # payload feeds this). Also captures authored display names for MATCHED
    # UFs (route-evidence only) for the naming contract. Kill-switch
    # WYSTAN_E2E_ORPHAN_UF=0 ⇒ output byte-identical to e2e-truth-only.
    if (e2e_truth_enabled() and orphan_uf_enabled()
            and e2e_payload is not None and not e2e_payload.get("e2e_absent")):
        with StageLogger(run_dir, 6, "e2e_orphan_uf") as log_orph:
            try:
                _synth = synthesize_orphan_journeys(
                    e2e_payload, product_features, features,
                    lineage_result.routes_index, user_flows,
                    flows=list(bipartite.flows),
                )
                minted = _synth["minted"]
                if minted:
                    max_id = 0
                    for uf in user_flows:
                        _m = re.match(r"^UF-(\d+)$", str(uf.id or ""))
                        if _m:
                            max_id = max(max_id, int(_m.group(1)))
                    fresh = [uf for uf, _titles in minted]
                    fresh.sort(key=lambda u: ((u.name or "").lower(),
                                              str(u.resource or "")))
                    for i, uf in enumerate(fresh, start=1):
                        uf.id = f"UF-{max_id + i:03d}"
                    for uf, _titles in minted:
                        user_flows.append(uf)
                        _e2e_authored_names[uf.id] = [uf.name]
                # C2 — authored names for MATCHED UFs (route-evidence only).
                for uid, labels in matched_authored_names(e2e_payload).items():
                    _e2e_authored_names.setdefault(uid, list(labels))
                scan_meta["e2e_orphan_uf"] = _synth["tele"]
                log_orph.info(
                    "e2e_orphan_uf: minted=%d (groups=%d, "
                    "filtered_neg=%d, dropped_no_route=%d, dropped_unbound=%d), "
                    "matched_authored=%d" % (
                        _synth["tele"]["minted"],
                        _synth["tele"]["groups"],
                        _synth["tele"]["filtered_negative"],
                        _synth["tele"]["dropped_no_route_ev"],
                        _synth["tele"]["dropped_unbound_pf"],
                        len(_e2e_authored_names),
                    ),
                    feature=None,
                )
            except Exception as exc:  # noqa: BLE001 — never break a scan
                log_orph.info(
                    f"e2e_orphan_uf: FAILED ({exc}) — continuing", feature=None,
                )

    # ── Stage 6.985 — transport-lane journey-conservation handoff (B22) ──
    # The transport prong (B19, default OFF) no longer lanes at mint —
    # 6.86 emitted candidate MARKS instead — and THIS stage resolves them
    # after the LAST journey producer (6.98b above) and BEFORE the 6.97
    # LOC prefetch (the lane_rehome slot family: loc-truth I13 + the lane
    # accounting below hold with zero extra plumbing; the emission
    # path_index refresh picks the moved devs up automatically). Per
    # candidate PF: every homed journey re-homes to the product PF it
    # serves (strict-majority span vote → deterministic consumer
    # completion → flagged plurality), route-group targets are excavated
    # at the SAME grain the vote used, devs follow, and only then the PF
    # converts to a platform-infrastructure lane resident. CONSERVATION
    # GATE (operator law): ANY unresolved journey → the PF does NOT lane
    # (exact flag-OFF output + blocked telemetry) — no journey is EVER
    # dissolved. Deterministic, $0 LLM; inert (no scan_meta key, no
    # output change) unless candidates exist. Kill-switch
    # WYSTAN_TRANSPORT_LANE_HANDOFF=0 restores B19 mint-time laning.
    from wystan.pipeline_v2.transport_handoff import (
        run_transport_handoff,
        transport_handoff_enabled,
    )
    _transport_candidates = dict(
        ((scan_meta.get("stage_6_86_anchored_mint") or {})
         .get("technology_instruments") or {})
        .get("transport_candidates") or {}
    )
    if transport_handoff_enabled() and _transport_candidates:
        with StageLogger(run_dir, 6, "transport_handoff") as log_th:
            try:
                th_tele = run_transport_handoff(
                    features, product_features, user_flows,
                    list(bipartite.flows), lineage_result.routes_index,
                    ctx, _transport_candidates,
                    extractor_signals=stage1_out,
                    feature_flow_edges=list(bipartite.edges),
                    nav_keys=frozenset(_nav_keys),
                )
                scan_meta["transport_handoff"] = th_tele
                log_th.info(
                    "transport_handoff: candidates=%d laned=%d blocked=%d "
                    "ufs_rehomed=%d devs(rehomed=%d laned=%d) minted=%d"
                    % (
                        len(th_tele.get("candidates") or []),
                        len(th_tele.get("laned") or []),
                        len(th_tele.get("conservation_blocked") or {}),
                        th_tele.get("ufs_rehomed", 0),
                        th_tele.get("devs_rehomed", 0),
                        th_tele.get("devs_laned", 0),
                        th_tele.get("pfs_minted", 0),
                    ),
                    feature=None,
                )
                write_stage_artifact(
                    ctx.repo_path,
                    stage_index=6,
                    stage_name="transport_handoff",
                    payload=dict(th_tele),
                    run_dir=run_dir,
                )
            except Exception as exc:  # noqa: BLE001 — never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"transport-handoff failed ({exc}); "
                    f"candidate PFs left product (no journey touched)"
                )
                log_th.info(
                    f"transport_handoff: FAILED ({exc}) — continuing",
                    feature=None,
                )

    # ── Stage 6.986 — mega-PF nav-area journey re-home + mint (B24) ──
    # A board-dominating umbrella PF (>=25% of homed journeys) whose
    # journeys strict-majority-cluster into >=3 distinct nav-area route
    # groups re-homes those journeys onto their EXISTING sibling PFs
    # (attach-floor + all-rung I16 rail + surface/same-app rails) and
    # mints a group with no sibling ONLY above the lattice floor
    # (>=3 UFs / >=3 flows) — supabase 'projects' class. Runs AFTER
    # 6.985 (journey layer final, transport folds resolved; candidates
    # excluded as sources/targets) and BEFORE the 6.97 LOC prefetch so
    # mint + carve are loc-stamped/path_indexed like any other PF.
    # Conservation: re-home ONLY (unresolved journeys stay; source
    # keeps >=1). Deterministic, $0 LLM; default OFF; inert (no
    # scan_meta key) unless the trigger fires.
    from wystan.pipeline_v2.mega_pf_nav_rehome import (
        mega_pf_nav_rehome_enabled,
        run_mega_pf_nav_rehome,
    )
    if (mega_pf_nav_rehome_enabled() and anchored_mint_applied
            and not uf_suppressed):
        with StageLogger(run_dir, 6, "mega_pf_nav_rehome") as log_b24:
            try:
                b24_tele = run_mega_pf_nav_rehome(
                    features, product_features, user_flows,
                    list(bipartite.flows), lineage_result.routes_index,
                    ctx,
                    extractor_signals=stage1_out,
                    feature_flow_edges=list(bipartite.edges),
                    transport_candidate_units=set(_transport_candidates),
                )
                # S5a: ``armed_sources`` exists only in the ARMED world —
                # emitting the selection census there keeps the unarmed
                # inertness convention byte-identical while making the
                # armed trigger numbers observable even on no-fire boards.
                if b24_tele.get("triggered") or b24_tele.get("armed_sources"):
                    scan_meta["mega_pf_nav_rehome"] = b24_tele
                    write_stage_artifact(
                        ctx.repo_path,
                        stage_index=6,
                        stage_name="mega_pf_nav_rehome",
                        payload=dict(b24_tele),
                        run_dir=run_dir,
                    )
                log_b24.info(
                    "mega_pf_nav_rehome: triggered=%s ufs_rehomed=%d "
                    "minted=%d carved=%d floor_drops=%d qual=%d census=%s"
                    % (
                        ",".join(b24_tele.get("triggered") or []) or "-",
                        b24_tele.get("ufs_rehomed", 0),
                        b24_tele.get("pfs_minted", 0),
                        b24_tele.get("devs_carved", 0),
                        len(b24_tele.get("floor_drops") or []),
                        len(b24_tele.get("qualifying_groups") or []),
                        ";".join(
                            f"{c['pf']}:{c['ufs']}:{c['share']}"
                            for c in (b24_tele.get("census") or [])[:3]),
                    ),
                    feature=None,
                )
            except Exception as exc:  # noqa: BLE001 — never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"mega-pf nav re-home failed ({exc}); "
                    f"journeys left untouched"
                )
                log_b24.info(
                    f"mega_pf_nav_rehome: FAILED ({exc}) — continuing",
                    feature=None,
                )

    # ── Stage 6.987 — devgrain-leaf PF demote (B33 v2) ─────────────────
    # A route:/fdir:-anchored PF whose leaf names a plumbing screen /
    # journey step (closed YAML set), is NOT nav-declared, and whose
    # FINAL journey profile is micro (<=2 UFs, every member_count <=3)
    # demotes: PF row removed, its synthesized micro-UFs drop, devs
    # re-point to the nearest surviving ancestor PF (else stay L1).
    # Runs AFTER the journey layer is final (6.7*/lattice/e2e/6.985/
    # 6.986) so a rich journey set always vetoes the demote
    # (conservation by construction — the twenty Onboarding lesson),
    # and BEFORE the 6.97 LOC prefetch / marker backstops / emission
    # integrity so no marker is synthesized for a demoted PF. Empty
    # nav_keys ⇒ board-wide honest abstain. Deterministic, $0 LLM;
    # default ON since the 2026-07-12 flip (KEY_SCHEMA v28).
    from wystan.pipeline_v2.devgrain_demote import (
        fdir_devgrain_gate_enabled,
        run_devgrain_demote,
    )
    if (fdir_devgrain_gate_enabled() and anchored_mint_applied
            and not uf_suppressed):
        with StageLogger(run_dir, 6, "devgrain_demote") as log_dg:
            try:
                dg_tele = run_devgrain_demote(
                    features, product_features, user_flows,
                    # DEMOTE channel (Fix A): weak echo ∪ vue-lift — nav
                    # evidence here EXEMPTS/un-abstains, never mints.
                    nav_keys=frozenset(_nav_keys_demote),
                    # per-workspace scoping for the per-leaf nav exemption
                    # (empty ⇒ flag OFF ⇒ the flat nav_keys behaviour, byte-id).
                    nav_keys_by_ws=_nav_keys_by_ws or None,
                    nav_ws_paths=_nav_ws_paths,
                )
                scan_meta["devgrain_demote"] = dg_tele
                log_dg.info(
                    "devgrain_demote: eligible=%d demoted=%d abstained=%d "
                    "nav_skipped=%d board_abstain=%s" % (
                        dg_tele.get("eligible", 0),
                        len(dg_tele.get("demoted", [])),
                        len(dg_tele.get("abstained", [])),
                        len(dg_tele.get("nav_declared_skipped", [])),
                        dg_tele.get("journey_step_leaf_abstained", False),
                    ),
                    feature=None,
                )
            except Exception as exc:  # noqa: BLE001 — never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"devgrain demote failed ({exc}); PFs left untouched"
                )
                log_dg.info(
                    f"devgrain_demote: FAILED ({exc}) — continuing",
                    feature=None,
                )

    # ── Stage 6.987b — Pin-cycle-3 M3 module-shape route-stub demote ────
    # NAV-INDEPENDENT companion to 6.987: a route/fdir-anchored PF whose
    # source module renders NO component (a named-exports-only .ts/.js —
    # no SFC/defineComponent/default-export/JSX) with tiny LOC and a micro
    # journey profile is a plumbing route, not a product surface — demote;
    # its hallucinated journey → honest-residual (never lost); devs
    # re-point to the nearest surviving ancestor. Fires even when nav_keys
    # is empty (the Vue/keyless blind spot that board-wide-abstains 6.987).
    # Runs after 6.987 (same post-journey-layer boundary) so the profile is
    # final. Default OFF; unset ≡ 0 ⇒ pure no-op, byte-identical.
    from wystan.pipeline_v2.stage_route_stub_shape import (
        route_stub_shape_enabled,
        run_route_stub_shape,
    )
    if (route_stub_shape_enabled() and anchored_mint_applied
            and not uf_suppressed):
        with StageLogger(run_dir, 6, "route_stub_shape") as log_rss:
            try:
                rss_tele = run_route_stub_shape(
                    product_features, user_flows, features, ctx,
                )
                scan_meta["route_stub_shape"] = rss_tele
                log_rss.info(
                    "route_stub_shape: eligible=%d demoted=%d "
                    "residual_journeys=%d devs_repointed=%d devs_unowned=%d" % (
                        rss_tele.get("eligible", 0),
                        len(rss_tele.get("demoted", [])),
                        rss_tele.get("residual_journeys", 0),
                        rss_tele.get("devs_repointed", 0),
                        rss_tele.get("devs_unowned", 0),
                    ),
                    feature=None,
                )
            except Exception as exc:  # noqa: BLE001 — never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"route_stub_shape failed ({exc}); PFs left untouched"
                )
                log_rss.info(
                    f"route_stub_shape: FAILED ({exc}) — continuing",
                    feature=None,
                )

    # S3 arbiter — apply deferred proposals at this pass boundary
    # (rung-priority == pass order; no-op when the flag is OFF).
    _arb_flush(product_features, note="post-devgrain")

    # ── Perf wave 2 (R5b) — 6.97 LOC prefetch overlaps the 6.95→6.96 chain ──
    # DAG verified at this base: Stage 6.97 feature-LOC reads only
    # {feature/PF paths + member_files + the checked-out tree,
    # uf.product_feature_id, uf.member_flow_ids, flow line_ranges} —
    # none of which 6.95 history / 6.96 impact (entity ``history`` only),
    # the llm-health stamp (scan_meta), 6.6 monorepo assembly (never
    # mutates features) or the uf-identity keeper (uf.id / flow
    # backpointers only) write. A FULL stage relocation is still unsafe:
    # the write_stage_input captures inside this window serialize
    # features / product_features / scan_meta while a sibling thread
    # would be inserting ``history``/``loc`` attributes (dict-changed-
    # during-iteration + nondeterministic capture bytes), and scan_meta
    # key INSERTION ORDER feeds the output JSON. So the concurrency is
    # scoped to 6.97's dominant cost — the pure per-file LOC counting —
    # prefetched here in one worker thread (pure reads: feature paths +
    # disk; no shared-state mutation, no StageLogger events, no scan_meta
    # keys) and consumed at the stage's UNCHANGED canonical position
    # below. Values are pure functions of the tree, so output bytes are
    # identical by construction; on any prefetch failure the stage
    # computes inline exactly as before.
    import threading as _threading

    from wystan.pipeline_v2.stage_6_97_feature_loc import (
        prefetch_loc_cache as _prefetch_loc_cache,
        stage_6_97_enabled as _stage_6_97_enabled_early,
    )

    _loc_prefetch: dict[str, Any] = {}
    _loc_prefetch_thread: Any = None
    if _stage_6_97_enabled_early():
        def _run_loc_prefetch() -> None:
            try:
                _loc_prefetch["cache"] = _prefetch_loc_cache(
                    features, product_features, ctx.repo_path,
                )
            except Exception:  # noqa: BLE001 — prefetch is best-effort
                _loc_prefetch.pop("cache", None)

        _loc_prefetch_thread = _threading.Thread(
            target=_run_loc_prefetch,
            name="wystan-6-97-loc-prefetch",
            daemon=True,
        )
        _loc_prefetch_thread.start()

    # ── Stage 6.95 — per-entity git-history timeline ────────────────
    # Deterministic, pure, $0 LLM. Runs LAST before output by design:
    # product-feature ``paths`` are final (Stage 8 + 8.5) and user-flow
    # membership is final (6.7 + 6.7c). Buckets the IN-MEMORY commit
    # list (no new git calls) into ISO-week series + events + a
    # test-efficacy verdict per product feature / user flow. Additive —
    # only the new ``history`` field is written. ``--no-feature-history``
    # skips the stage entirely (telemetry records the skip).
    from wystan.pipeline_v2.stage_6_95_history import stage_6_95_history
    history_telemetry: dict[str, Any] = {"skipped": True}
    write_stage_input(run_dir, 6, "history", {
        "product_features": product_features,
        "user_flows": user_flows,
        "bipartite_flows": list(bipartite.flows),
        "features": features,
        "ctx": ctx,
        "feature_history": feature_history,
        "scan_meta": scan_meta,
    })
    with StageLogger(run_dir, 6, "history") as log6_95:
        if feature_history:
            history_telemetry = stage_6_95_history(
                product_features,
                user_flows,
                list(bipartite.flows),
                features,
                ctx.commits,
            )
            log6_95.info(
                "history: pf_scored=%d/%d uf_scored=%d/%d "
                "gated(pf=%d uf=%d) verdicts=%s "
                "cross_cut(events=%d entities=%d capped=%d) elapsed=%ss"
                % (
                    history_telemetry["product_features_scored"],
                    history_telemetry["product_features_total"],
                    history_telemetry["user_flows_scored"],
                    history_telemetry["user_flows_total"],
                    history_telemetry["product_features_gated"],
                    history_telemetry["user_flows_gated"],
                    history_telemetry["verdicts"],
                    history_telemetry["cross_cut_events_emitted"],
                    history_telemetry["cross_cut_entities_affected"],
                    history_telemetry["cross_cut_capped_out"],
                    history_telemetry["elapsed_sec"],
                ),
            )
        else:
            log6_95.info("history: skipped via --no-feature-history")
        write_stage_artifact(
            ctx.repo_path,
            stage_index=6,
            stage_name="history",
            payload=history_telemetry,
            run_dir=run_dir,
        )
    scan_meta["stage_6_95"] = dict(history_telemetry)

    # ── Stage 6.96 — impact-over-time (import-graph blast radius) ───
    # Sibling of 6.95, same ``feature_history`` gate (no new CLI flag).
    # Materialises N evenly-spaced historical snapshots via short-lived
    # ``git worktree`` checkouts and records each history-bearing
    # entity's external-importer count per snapshot
    # (``history.impact``), plus coupling_spike / decoupled events and
    # an impact_trend — all scale-invariant, deterministic, $0 LLM.
    # Failure-proof by contract: per-snapshot failures and the wall
    # budget degrade to fewer points, never a failed scan.
    from wystan.pipeline_v2.stage_6_96_impact import stage_6_96_impact
    impact_telemetry: dict[str, Any] = {"skipped": True}
    write_stage_input(run_dir, 6, "impact", {
        "product_features": product_features,
        "user_flows": user_flows,
        "bipartite_flows": list(bipartite.flows),
        "features": features,
        "ctx": ctx,
        "repo_path": str(repo_path),
        "feature_history": feature_history,
        "scan_meta": scan_meta,
    })
    with StageLogger(run_dir, 6, "impact") as log6_96:
        if feature_history:
            impact_telemetry = stage_6_96_impact(
                product_features,
                user_flows,
                list(bipartite.flows),
                features,
                ctx.commits,
                repo_path,
                subpath=getattr(ctx, "subpath", None),
                log=log6_96,
            )
            log6_96.info(
                "impact: snapshots=%s/%s entities=%s/%s "
                "spikes=%s decoupled=%s trends=%s "
                "budget_exceeded=%s elapsed=%ss"
                % (
                    impact_telemetry.get("impact_snapshots", 0),
                    impact_telemetry.get("planned_snapshots", 0),
                    impact_telemetry.get("entities_with_impact", 0),
                    impact_telemetry.get("entities_total", 0),
                    impact_telemetry.get("coupling_spike_events", 0),
                    impact_telemetry.get("decoupled_events", 0),
                    impact_telemetry.get("trends"),
                    impact_telemetry.get("impact_budget_exceeded", False),
                    impact_telemetry.get("elapsed_sec"),
                ),
            )
        else:
            log6_96.info("impact: skipped via --no-feature-history")
        write_stage_artifact(
            ctx.repo_path,
            stage_index=6,
            stage_name="impact",
            payload=impact_telemetry,
            run_dir=run_dir,
        )
    scan_meta["stage_6_96_impact"] = dict(impact_telemetry)

    # ── LLM-health stamp (fail LOUD on auth-dead scans) ────────────
    # Must run AFTER the last LLM-bearing stage (6.7b above) and BEFORE
    # Stage 7 writes the artifact, so ``scan_meta.llm_degraded`` + the
    # warning land in the persisted JSON. Additive — absent on healthy
    # scans. See ``llm_health`` module docstring for the
    # degrade-visibly-never-abort decision.
    if llm_health is not None:
        stamp_llm_degraded(scan_meta, llm_health)

    # ── Stage 6.6 — Monorepo Assembly View ($0, deterministic, additive) ──
    #    Re-project the flat ``features`` into a per-project structure +
    #    cross-project dependency graph. Gated on ``is_monorepo`` (single
    #    repos get the trivial ``{"is_monorepo": False}``). Never mutates
    #    ``features``. Defensive: an assembly failure degrades to ``{}`` +
    #    a warning so it can NEVER break a scan.
    monorepo_view: dict[str, Any] = {}
    write_stage_input(run_dir, 6, "monorepo_assembly", {
        "ctx": ctx,
        "features": features,
        "scan_meta": scan_meta,
    })
    with StageLogger(run_dir, 6, "monorepo_assembly") as log66:
        try:
            from wystan.pipeline_v2.stage_6_6_monorepo_assembly import (
                build_monorepo_assembly,
            )

            monorepo_view = build_monorepo_assembly(ctx, features)
            stats = monorepo_view.get("stats", {})
            log66.info(
                "monorepo=%s projects=%s edges=%s assigned=%.0f%%"
                % (
                    monorepo_view.get("is_monorepo", False),
                    stats.get("project_count", 0),
                    stats.get("edge_count", 0),
                    100.0 * float(stats.get("assigned_pct", 0.0)),
                ),
                feature=None,
            )
            write_stage_artifact(
                ctx.repo_path,
                stage_index=6,
                stage_name="monorepo_assembly",
                payload=monorepo_view,
                run_dir=run_dir,
            )
        except Exception as exc:  # noqa: BLE001 — never fail a scan on the view
            log66.info(f"monorepo assembly skipped ({exc})", feature=None)
            monorepo_view = {}
    if monorepo_view:
        scan_meta["monorepo_assembly"] = {
            k: v for k, v in monorepo_view.get("stats", {}).items()
        }

    # ── UF identity keeper (opt-in, output layer, $0 LLM) ──────────
    # Pins user-flow ``id`` + ``name`` across rescans against an
    # EXPLICITLY provided previous scan artifact (``--prev-scan`` /
    # ``prev_scan_json``). Per ``rule-cold-scan`` there is NO ambient
    # discovery: when the input is absent this block is skipped and the
    # scan output is byte-identical to today. Deterministic matching
    # only (member/route Jaccard + unique (resource,intent) key);
    # disappeared UFs are RETIRED in telemetry, never resurrected.
    # W3 (§4.8): keeper default-ON on the production path (worker passes
    # the prev scan) — ``WYSTAN_KEEPER=0`` disables pinning even with
    # input present (eval scrub-mode; rule-cold-scan stays provable).
    from wystan.pipeline_v2.uf_identity_keeper import (
        keeper_enabled as _keeper_enabled,
    )
    if prev_scan_json is not None and not _keeper_enabled():
        scan_meta["uf_identity"] = {
            "enabled": False, "reason": "WYSTAN_KEEPER=0",
        }
    if prev_scan_json is not None and _keeper_enabled():
        from wystan.pipeline_v2.uf_identity_keeper import (
            apply_identity_keeper,
        )
        write_stage_input(run_dir, 7, "uf_identity", {
            "user_flows": user_flows,
            "bipartite_flows": list(bipartite.flows),
            "prev_scan_json": prev_scan_json,
            "scan_meta": scan_meta,
        })
        with StageLogger(run_dir, 7, "uf_identity") as log_uid:
            try:
                uid_telemetry = apply_identity_keeper(
                    user_flows, list(bipartite.flows), prev_scan_json,
                )
                scan_meta["uf_identity"] = uid_telemetry
                log_uid.info(
                    "uf_identity: pinned %d/%d new UFs (prev %d, "
                    "pin_rate %.2f, renames_prevented %d, retired %d, "
                    "fk_remapped %d, basis %s)"
                    % (
                        uid_telemetry["pinned"],
                        uid_telemetry["new_total"],
                        uid_telemetry["prev_total"],
                        uid_telemetry["pin_rate"],
                        uid_telemetry["renames_prevented"],
                        len(uid_telemetry["retired"]),
                        uid_telemetry["fk_remapped"],
                        uid_telemetry["basis_counts"],
                    ),
                    feature=None,
                )
            except Exception as exc:  # noqa: BLE001 — identity is best-effort, never fatal
                scan_meta["uf_identity"] = {"enabled": False, "error": str(exc)}
                scan_meta.setdefault("warnings", []).append(
                    f"uf-identity-keeper failed ({exc}); scan continued unpinned"
                )
                log_uid.info(
                    f"uf_identity: FAILED ({exc}) — continuing unpinned",
                    feature=None,
                )
            write_stage_artifact(
                ctx.repo_path,
                stage_index=7,
                stage_name="uf_identity",
                payload=dict(scan_meta.get("uf_identity") or {}),
                run_dir=run_dir,
            )

    # ── FILELANE — file-level shared-infrastructure lane ──────────────────
    # Reclassifies unowned high-fan-in shared-infra files into the lane
    # (the dominant I15 SPILL->unowned blocker). Runs HERE — after the
    # membership + user-flow layer settles, BEFORE Stage 6.97 — so the
    # normal feature_loc pass counts the new lane devs' LOC and folds it
    # into repo_loc (conservation holds BY CONSTRUCTION, the same window
    # lane_rehome / provenance_rehome use). The post-emission path_index
    # rebuild then reads the files as lane-owned and
    # build_platform_infrastructure_lane emits them. Strictly additive —
    # only NEW pfid=None lane devs are appended; existing PFs/devs are
    # untouched, and resolve_flowless_shells (pfid-keyed) +
    # emission_integrity (phantom-drop) leave flowless pfid=None lane
    # residents intact (the existing no_anchor_lineage lane proves it).
    # Gated on anchored_mint_applied: no lane schema to extend otherwise.
    # Kill-switch WYSTAN_FILE_LANE=0 → no devs appended → byte-identical.
    from wystan.pipeline_v2.file_lane import (
        data_leaf_enabled,
        enforce_data_leaf_shared,
        enforce_shared_leaf_consistency,
        file_lane_enabled,
        run_file_lane_infra,
        shared_leaf_consistency_enabled,
    )
    if file_lane_enabled() and anchored_mint_applied:
        with StageLogger(run_dir, 6, "file_lane") as log_fl:
            try:
                fl_tele = run_file_lane_infra(
                    features, product_features,
                    lineage_result.routes_index, ctx,
                )
                scan_meta["file_lane"] = fl_tele
                log_fl.info(
                    "file_lane: laned %d files -> %d lane devs (%d LOC), "
                    "threshold %d = ceil(%.3f * %d PFs); blocked "
                    "owned=%d pf_paths=%d surface=%d low_fanin=%d"
                    % (
                        fl_tele.get("laned_files", 0),
                        fl_tele.get("laned_devs", 0),
                        fl_tele.get("laned_loc", 0),
                        fl_tele.get("threshold", 0),
                        fl_tele.get("pct", 0.0),
                        fl_tele.get("num_product_features", 0),
                        fl_tele.get("blocked_owned", 0),
                        fl_tele.get("blocked_pf_paths", 0),
                        fl_tele.get("blocked_surface", 0),
                        fl_tele.get("blocked_low_fanin", 0),
                    ),
                    feature=None,
                )
                write_stage_artifact(
                    ctx.repo_path, stage_index=6, stage_name="file_lane",
                    payload=dict(fl_tele), run_dir=run_dir,
                )
            except Exception as exc:  # noqa: BLE001 — lane must never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"file-lane failed ({exc}); no infra reclassified"
                )
                log_fl.info(
                    f"file_lane: FAILED ({exc}) — continuing", feature=None)

    # ── B15 — shared-leaf role consistency (post file_lane, pre path_index) ──
    #    Force high-cross-PF-fan-in, no-surface, already-shared-somewhere member
    #    files to role="shared" everywhere (the i18n-locale class re-attributed
    #    as closure body). Runs here so the change lands BEFORE the path_index
    #    rebuild + I23 body read. Kill-switch WYSTAN_SHARED_LEAF_CONSISTENCY=0
    #    -> no roles changed -> byte-identical. Never breaks a scan.
    if shared_leaf_consistency_enabled() and anchored_mint_applied:
        try:
            slc_tele = enforce_shared_leaf_consistency(
                features, product_features, lineage_result.routes_index)
            scan_meta["shared_leaf_consistency"] = slc_tele
        except Exception as exc:  # noqa: BLE001 — never break a scan
            scan_meta.setdefault("warnings", []).append(
                f"shared-leaf-consistency failed ({exc}); no roles changed")

    # ── Stage 6.97 — feature-level LOC ($0, deterministic, additive) ──
    #    Flat ``loc`` on every dev feature (sum of owned-file line counts;
    #    test/generated/lockfile/binary files excluded from the count) +
    #    dedup rollup on product features. Output-layer metric: NEVER
    #    mutates paths/flows. Defensive: a failure degrades to loc=None
    #    + a warning so it can NEVER break a scan.
    from wystan.pipeline_v2.stage_6_97_feature_loc import (
        apply_feature_loc,
        stage_6_97_enabled,
    )
    # fixb114/P12-M1 — the rollup ledger (empty ⇒ the re-roll stage below
    # abstains, so a 6.97-disabled scan can never be re-rolled from thin air).
    # Captured ONLY when the re-roll is armed: on the default (OFF) path
    # ``ledger_out`` stays None, so 6.97 does not even build the maps and the
    # unset world pays nothing for a stage it does not run.
    from wystan.pipeline_v2.stage_6_97e_pf_loc import (
        pf_loc_reroll_enabled as _pf_loc_reroll_armed,
    )
    _pf_loc_ledger: dict[str, Any] | None = (
        {} if _pf_loc_reroll_armed() else None
    )
    if stage_6_97_enabled():
        # ``user_flows``/``bipartite_flows`` joined this capture in perf
        # wave 2: the live call threads them into the §4.5 flow
        # accounting, but the capture (and the registry runner) predated
        # that — single-stage replay silently dropped the
        # ``loc_accounting`` flow keys (found by this wave's replay
        # proof; reproduced from a b7351b6-era capture, i.e. pre-existing
        # drift, not introduced here).
        write_stage_input(run_dir, 6, "feature_loc", {
            "ctx": ctx,
            "features": features,
            "product_features": product_features,
            "scan_meta": scan_meta,
            "user_flows": user_flows,
            "bipartite_flows": list(bipartite.flows),
        })
        with StageLogger(run_dir, 6, "feature_loc") as log697:
            try:
                # R5b — adopt the prefetched per-file counts (value
                # source only; key discipline in _PrewarmedCache). The
                # join is here, right before the single consumer.
                _prewarmed_loc = None
                if _loc_prefetch_thread is not None:
                    _loc_prefetch_thread.join()
                    _prewarmed_loc = _loc_prefetch.get("cache")
                loc_telemetry = apply_feature_loc(
                    features, product_features, ctx.repo_path,
                    # §4.5 conservation flow accounting (on-flow ≤ 1 by
                    # construction) — needs the final journey attachments.
                    user_flows=user_flows,
                    flows=list(bipartite.flows),
                    prewarmed_loc=_prewarmed_loc,
                    # B98-3e — span LOC for shared-table devs (go-router
                    # 5-tuples carry line+handler; the branch is B98-gated).
                    routes_index=lineage_result.routes_index,
                    # fixb114/P12-M1 — capture the rollup ledger (per-file
                    # LOC + the one-owner-per-file election) so the
                    # final-membership re-roll below can replay THIS law
                    # instead of inventing a second ruler. Filling the dict
                    # changes nothing here (additivity).
                    ledger_out=_pf_loc_ledger,
                )
                scan_meta["feature_loc"] = loc_telemetry
                if loc_telemetry.get("loc_accounting"):
                    scan_meta["loc_accounting"] = loc_telemetry["loc_accounting"]
                # B59 — artifact-ink lane aggregate (absent when the flag is
                # OFF, so default scan_meta is byte-identical to main).
                if loc_telemetry.get("artifact_ink"):
                    scan_meta["artifact_ink"] = loc_telemetry["artifact_ink"]
                log697.info(
                    "feature_loc: %d/%d dev features with loc>0 "
                    "(%d zero-loc-with-paths), %d files counted"
                    % (
                        loc_telemetry["features_with_loc"],
                        loc_telemetry["features_total"],
                        loc_telemetry["features_zero_loc_with_paths"],
                        loc_telemetry["files_counted"],
                    ),
                    feature=None,
                )
                write_stage_artifact(
                    ctx.repo_path,
                    stage_index=6,
                    stage_name="feature_loc",
                    payload=loc_telemetry,
                    run_dir=run_dir,
                )
            except Exception as exc:  # noqa: BLE001 — metric must never break a scan
                scan_meta["feature_loc"] = {"enabled": False, "error": str(exc)}
                scan_meta.setdefault("warnings", []).append(
                    f"feature-loc stage failed ({exc}); loc fields left unset"
                )
                log697.info(
                    f"feature_loc: FAILED ({exc}) — continuing without loc",
                    feature=None,
                )

    # ── B15b — data-file shared-leaf rail (§4b, runs AFTER 6.97 so repo_loc is
    #    available for the scale-invariant LOC floor; before the path_index
    #    rebuild + I23 body read). Force role="shared" on large shared-DATA leaf
    #    files (i18n locale packs, template JSON) the closure attributed as body.
    #    Kill-switch WYSTAN_DATA_LEAF=0 -> byte-identical. Never breaks a scan.
    if data_leaf_enabled() and anchored_mint_applied:
        try:
            _repo_loc = (scan_meta.get("loc_accounting") or {}).get("repo_loc")
            dl_tele = enforce_data_leaf_shared(
                features, product_features, lineage_result.routes_index,
                _repo_loc)
            scan_meta["data_leaf"] = dl_tele
        except Exception as exc:  # noqa: BLE001 — never break a scan
            scan_meta.setdefault("warnings", []).append(
                f"data-leaf rail failed ({exc}); no roles changed")

    # ── Draw-native flowless-shell resolution (RC2 fix-3 Part B, $0) ──
    # A 6.7d Call-1 draw can emit a capability whose devs own >= 1k LOC but
    # ZERO flows (validator I8 LOC prong). Resettle those shells — absorb a
    # footprint-matched residual dev, JOIN a token-family flowful PF, or DEMOTE
    # to the shared bucket + DROP the shell. Runs HERE (post-feature_loc) because
    # the >= 1k-LOC prong needs owned ``loc`` (Stage 6.97 populates it), and ONLY
    # when 6.7d actually applied — so keyless scans (no draw, no shells) stay
    # byte-inert (snapshot gate). Before emission-integrity so the dropped PF
    # never reaches the referential round-trip.
    from wystan.pipeline_v2.stage_6_7d_llm_journey_abstraction import (
        _shell_absorb_enabled,
        resolve_flowless_shells,
    )
    # NEVER on the ANCHORED path (Wave 2b review F1/F5, 2026-07-06): this
    # ladder is a cure for FREE-GEN draw shells and both of its moving
    # rungs violate the spine — the JOIN re-homes a minted anchor's devs
    # by name-family against their own lineage (F5), and the DEMOTE
    # resurrects the ABOLISHED "Shared Platform" PF via _ensure_shared_pf
    # (F1 — the 18:2x amendment kills that bucket on every code path; the
    # keyed leak survived the keyless gates precisely because this stage
    # is 6.7d-gated). An anchored flowless >=1k-LOC PF is a REAL
    # capability whose flows weren't detected — it stays, and validator
    # I8's LOC prong honestly reports the flow-detection gap.
    if (_shell_absorb_enabled()
            and not anchored_mint_applied
            and (scan_meta.get("stage_6_7d_journey_abstraction") or {}).get("applied")):
        with StageLogger(run_dir, 6, "flowless_shells") as log_shell:
            try:
                product_features, shell_tele = resolve_flowless_shells(
                    features, product_features)
                scan_meta["flowless_shells"] = shell_tele
                log_shell.info(
                    "flowless_shells: absorbed=%d joined=%d demoted=%d"
                    % (shell_tele["shell_absorbed"], shell_tele["shell_joined"],
                       shell_tele["shell_demoted"]),
                    feature=None)
            except Exception as exc:  # noqa: BLE001 — never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"flowless-shell resolution failed ({exc}); shells left as-is")
                log_shell.info(
                    f"flowless_shells: FAILED ({exc}) — continuing", feature=None)

    # ── Stage 6.85 — product-surface taxonomy, emission lane ($0) ──────
    # Product-Spine §4.2 (Wave 2a) consequences on the FINAL arrays:
    # tag UFs + PFs; move marketing/docs/legal/dev_tooling/shell PFs (and
    # their journeys) into the additive non_product_surfaces[] lane
    # (validator I20); dissolve info-page journeys into their hosting UF
    # (consequence b); re-bind non-product shared devs to their lane
    # surface; stamp shared_reason on every shared-bucket resident
    # (validator I22). Runs AFTER 6.97 LOC (lane rows carry loc) and the
    # flowless-shell resolution (final PF set), BEFORE emission integrity
    # (which then reconciles refs against the surviving product list).
    from wystan.pipeline_v2.surface_taxonomy import apply_emission_taxonomy
    non_product_surfaces: list[dict[str, Any]] = []
    with StageLogger(run_dir, 6, "surface_taxonomy") as log_st:
        try:
            # Surface Adjudicator (W3 §4.7): keyed scans resolve the
            # conflicting-signal PF minority; keyless / kill-switch →
            # None → the deterministic verdicts stand byte-identically.
            _st_adjudicator = None
            try:
                from wystan.pipeline_v2.personas import (
                    build_surface_adjudicator,
                )
                _st_adjudicator = build_surface_adjudicator(
                    model_id=model_id,
                    cost_tracker=tracker,
                    cache=getattr(ctx, "cache_backend", None),
                    llm_health=llm_health,
                    log=log_st,
                    thesis=scan_meta.get("product_thesis"),
                )
            except Exception:  # noqa: BLE001 — persona is optional
                _st_adjudicator = None
            st_tele, non_product_surfaces, product_features = (
                apply_emission_taxonomy(
                    features, product_features, user_flows,
                    list(bipartite.flows), lineage_result.routes_index,
                    repo_path=repo_path,
                    adjudicator=_st_adjudicator,
                    instrument_dirs=instrument_dirs,
                    dev_artifact_units=dev_artifact_units,  # B28 P-D
                    # B98: the 6.86 headless VERDICT (not a bare flag — the
                    # I20 lesson from twenty: a paged repo must lane marketing)
                    headless_repo=bool(
                        ((scan_meta.get("stage_6_86_anchored_mint") or {})
                         .get("headless_product_spine"))),
                )
            )
            scan_meta["surface_taxonomy_emission"] = st_tele
            log_st.info(
                "surface_taxonomy: pf_scopes=%s lane=%d ufs_moved=%d "
                "info_dissolved=%d rebound=%d shared_reasons=%s"
                % (
                    st_tele.get("pf_scopes"),
                    st_tele.get("pfs_moved_to_lane", 0),
                    st_tele.get("ufs_moved_to_lane", 0),
                    st_tele.get("info_ufs_dissolved", 0),
                    st_tele.get("devs_rebound_to_lane", 0),
                    st_tele.get("shared_reasons"),
                ),
                feature=None,
            )
            write_stage_artifact(
                ctx.repo_path,
                stage_index=6,
                stage_name="surface_taxonomy",
                payload={**st_tele, "non_product_surfaces": [
                    {k: v for k, v in e.items() if k != "user_flows"}
                    for e in non_product_surfaces
                ]},
                run_dir=run_dir,
            )
        except Exception as exc:  # noqa: BLE001 — taxonomy must never break a scan
            non_product_surfaces = []
            scan_meta.setdefault("warnings", []).append(
                f"surface-taxonomy emission failed ({exc}); "
                f"lane left empty, tags may be partial"
            )
            log_st.info(
                f"surface_taxonomy: FAILED ({exc}) — continuing", feature=None,
            )

    # ── Stage 6.987 — S5b leaf-route dissolution + platform promotion ──
    # ONE arbiter wave (spec fixs5b §PROBE-FORMS): Seg B dissolves a
    # ``route:``-leaf black hole (flat-leaf anchor whose mass >> its own
    # subtree — novu ``duplicate-workflow`` 315/2) by re-homing its foreign
    # member devs to real capability siblings (S5a dev-identity bridge +
    # file-grain majority segment); unhomed devs lane (NOT forced), which
    # FREES their pages. Seg C then promotes buried product surfaces —
    # platform-lane residents carrying PAGE evidence (a-lite mirror; P1
    # page-cohort ∪ P2 lane-token↔freed-page bridge) — by birth (S5a
    # birth-law) or merge-into-sibling. Runs AFTER the emission taxonomy
    # established the lane (pfid=None + shared_reason residents) + 6.97 LOC,
    # BEFORE emission integrity (which reconciles the births' UF refs I12 +
    # drops any phantom) and BEFORE the platform lane is assembled (so
    # promoted residents leave the lane). Every dev/UF move is an
    # overturn-ledger proposal (rung ``leafroute``). Kill-switch
    # WYSTAN_LEAFROUTE_PROMOTION unset/0 → stage not entered →
    # byte-identical.
    from wystan.pipeline_v2.leafroute_promotion import (
        leafroute_promotion_enabled,
        run_leafroute_promotion,
    )
    if leafroute_promotion_enabled():
        with StageLogger(run_dir, 6, "leafroute_promotion") as log_lrp:
            try:
                lrp_tele = run_leafroute_promotion(
                    features, product_features, user_flows,
                    list(bipartite.flows), lineage_result.routes_index, ctx,
                    feature_flow_edges=list(bipartite.edges),
                )
                if (lrp_tele.get("leaf_dissolved") or lrp_tele.get("births")
                        or lrp_tele.get("merged")):
                    scan_meta["leafroute_promotion"] = lrp_tele
                log_lrp.info(
                    "leafroute_promotion: leaf_fired=%d devs_rehomed=%d "
                    "devs_freed=%d pfs_born=%d devs_merged=%d p2_pages=%d"
                    % (
                        len(lrp_tele.get("leaf_fired", [])),
                        lrp_tele.get("devs_rehomed", 0),
                        lrp_tele.get("devs_freed", 0),
                        lrp_tele.get("pfs_born", 0),
                        lrp_tele.get("devs_merged", 0),
                        lrp_tele.get("p2_pages_bridged", 0),
                    ),
                    feature=None,
                )
                write_stage_artifact(
                    ctx.repo_path,
                    stage_index=6,
                    stage_name="leafroute_promotion",
                    payload=lrp_tele,
                    run_dir=run_dir,
                )
            except Exception as exc:  # noqa: BLE001 — never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"leafroute-promotion failed ({exc}); board left as-is")
                log_lrp.info(
                    f"leafroute_promotion: FAILED ({exc}) — continuing",
                    feature=None,
                )

    # ── W5.1 — LOC-worthy PF backstop (final I8 close, $0) ─────────────
    # Excavation (Stage 6.87) mints FLOWLESS high-LOC surfaces (supabase
    # Settings 27.5K, Query Performance, …); the flow-based PF-UF backstop
    # cannot seed them (no member flows). Validator I8 still demands a
    # journey (``pf_loc >= 1000``). This runs HERE — AFTER Stage 6.97 stamps
    # ``loc`` (the LOC arm no-ops before that) and AFTER the emission
    # taxonomy finalised the product list (so it targets the EXACT I8 PF
    # set) — and appends a member-LESS system-seed (the sole I7-exempt cover
    # for a flowless surface). BEFORE emission integrity, which then
    # reconciles the new UF refs (I12) + backpointers (I14). Gated on the
    # journey layer being EXPECTED (``not uf_suppressed``) — NOT on 6.7d
    # abstraction ``applied``: validator I8 scores the raw rollup too (6.7d
    # is LLM-only, degrades keyless), so the close must run in both the
    # abstracted and the degraded/keyless journey layers. Suppressed repos
    # (libraries / CLIs) never get journeys, so they are skipped.
    if not uf_suppressed:
        # #3B-B1 (WYSTAN_FLOWFUL_FINAL_COVER, default OFF): flow-rich PFs
        # stripped by LATE demote/rehome (after the early arms) — unkey
        # ``keys`` 10314 LOC / 2 flows / 0 UF — get a synth-arm (own-entry
        # bundle / member-less seed, honestly synthesized); the arm-1
        # reassign is forbidden (late theft = I16).
        # default ON since flip-pack #18 (KS53): live unkey keys 0→14;
        # synth-only (arm-1 forbidden), the markers law honoured.
        import os as _os_ffc
        _ffc = _os_ffc.environ.get(
            "WYSTAN_FLOWFUL_FINAL_COVER", "1").strip().lower() in {
            "1", "true", "yes", "on"}
        _lw_tele = _recover_uncovered_donors(
            user_flows, features, product_features, loc_only=True,
            flowful_synth=_ffc,
        )
        if _lw_tele is not None:
            scan_meta["loc_worthy_backstop"] = _lw_tele

    # platform_infrastructure[] declared here; ASSEMBLED after emission
    # integrity (the I2 phantom drop must not leave stale lane rows).
    platform_infrastructure: list[dict[str, Any]] | None = None

    # ── Emission integrity — referential round-trip guarantee ($0) ──
    # Runs LAST, after every UF / PF / flow / loc mutation, so the emitted
    # JSON is self-consistent by construction:
    #   * I2  — drop phantom features (marker-only paths, 0 loc/loc_shared,
    #           0 flows); workspace anchors + shared-platform are exempt.
    #   * I12 — every user_flows[].product_feature_id ∈ emitted PF key-set
    #           (canonical re-match else null).
    #   * I14 — flows[].user_flow_id re-derived from final user_flows[]
    #           membership (first owning UF in emit order wins).
    # Deterministic, output-layer only; never touches the flow graph.
    from wystan.pipeline_v2.emission_integrity import (
        enforce_emission_integrity,
    )
    with StageLogger(run_dir, 7, "emission_integrity") as log_ei:
        features, product_features, ei_result = enforce_emission_integrity(
            features, product_features, user_flows, bipartite.flows,
        )
        scan_meta["emission_integrity"] = ei_result.as_dict()
        log_ei.info(
            "emission_integrity: dropped %d dev + %d pf phantoms, "
            "relinked %d / nulled %d uf→pf refs, "
            "rewrote %d / nulled %d flow backpointers"
            % (
                len(ei_result.phantom_features_dropped),
                len(ei_result.phantom_product_features_dropped),
                ei_result.uf_pf_refs_relinked,
                ei_result.uf_pf_refs_nulled,
                ei_result.flow_backpointers_rewritten,
                ei_result.flow_backpointers_nulled,
            ),
            feature=None,
        )
        write_stage_artifact(
            ctx.repo_path,
            stage_index=7,
            stage_name="emission_integrity",
            payload=ei_result.as_dict(),
            run_dir=run_dir,
        )

        # W1.1 — path_index emission refresh. Lineage builds the index at
        # the TOP of this phase, but 6.9 test-strip / 6.9b generated-strip
        # / the 8.9.7 carve legitimately remove paths from features AFTER
        # that, so the shipped index pointed files at features that no
        # longer list them (RefApp validation scan 2026-07-06: 551/2081
        # entries stale, incl. the I18 offender — a stripped __tests__
        # file still "owned" by the shared-resident workspace anchor).
        # Rebuild from the FINAL features + flows: same builder, same
        # first-claimant rule, so live ownership is untouched; entries
        # whose only claimant vanished keep their flow join (flow_uuids)
        # with feature_uuid="" or drop out entirely — path_index is part
        # of the emitted output tree and must obey the same integrity
        # contract as everything else in this block.
        from wystan.pipeline_v2.indexes import build_path_index

        # ── S1 owner-oracle (flag-gated, default OFF) ───────────────────
        # Compute the deterministic owner election ONCE here — post-devgrain,
        # post-emission-integrity, so it runs over the SETTLED final dev
        # membership — and feed it to the path_index refresh (R1) and the
        # terminal-home conservation votes (R2) below. i16 / dispatch read the
        # refreshed path_index, so they inherit the same owner transitively.
        # OFF (unset / ``0``) → ``_owner_election`` is None → every consumer
        # keeps first-claimant → byte-identical.
        from wystan.pipeline_v2.owner_oracle import (
            build_owner_election_from,
            owner_oracle_enabled,
        )
        _owner_election = None
        _owner_file_uuid: dict[str, str] | None = None
        if owner_oracle_enabled():
            try:
                _owner_election = build_owner_election_from(
                    features, ctx.repo_path,
                )
                _owner_file_uuid = _owner_election.file_owner_uuid_map()
                scan_meta["emission_integrity"]["owner_oracle"] = {
                    "enabled": True,
                    "files_elected": len(_owner_file_uuid),
                }
            except Exception as exc:  # noqa: BLE001 — never break a scan
                _owner_election = None
                _owner_file_uuid = None
                scan_meta.setdefault("warnings", []).append(
                    f"owner-oracle election failed ({exc}); "
                    f"first-claimant owners kept"
                )

        _stale_index = lineage_result.path_index
        lineage_result.path_index = build_path_index(
            [{"uuid": f.uuid, "paths": list(f.paths)} for f in features],
            [{"uuid": fl.uuid, "paths": list(fl.paths)}
             for fl in bipartite.flows],
            file_owner=_owner_file_uuid,
        )
        _refresh_stats = {
            "entries_before": len(_stale_index),
            "entries_after": len(lineage_result.path_index),
            "owners_changed": sum(
                1 for p, e in lineage_result.path_index.items()
                if (_stale_index.get(p) or {}).get("feature_uuid")
                != e.get("feature_uuid")
            ),
        }
        scan_meta["emission_integrity"]["path_index_refresh"] = _refresh_stats
        log_ei.info(
            "path_index refresh: %d -> %d entries, %d owners changed"
            % (
                _refresh_stats["entries_before"],
                _refresh_stats["entries_after"],
                _refresh_stats["owners_changed"],
            ),
            feature=None,
        )
        # ── No-signal UF terminal home (Wave 2a, validator I21) ────────
        # Runs AFTER the integrity passes so it binds only SURVIVING
        # product-list keys and nothing downstream can re-null its work:
        # every journey the conservation nulling / I12 repair left orphan
        # gets a deterministic real-PF home (system-scope preference →
        # ownership argmax → nearest-directory argmax), tagged
        # binding_confidence="low". A UF never ships null / shared.
        from wystan.pipeline_v2.uf_terminal_home import (
            assign_terminal_homes,
            terminal_home_enabled,
        )
        if terminal_home_enabled():
            th_tele = assign_terminal_homes(
                user_flows, features, product_features,
                owner_election=_owner_election,
            )
            scan_meta["uf_terminal_home"] = th_tele
            log_ei.info(
                "uf_terminal_home: orphans=%d homed(votes=%d system=%d "
                "dir=%d) unhomed=%d"
                % (
                    th_tele.get("orphans", 0),
                    th_tele.get("homed_votes", 0),
                    th_tele.get("homed_system", 0),
                    th_tele.get("homed_dir", 0),
                    th_tele.get("unhomed", 0),
                ),
                feature=None,
            )

    # S3 arbiter — apply deferred proposals at this pass boundary
    # (rung-priority == pass order; no-op when the flag is OFF).
    _arb_flush(product_features, note="post-terminal-home")

    # ── Stage 6.87 — display-name contract (Product-Spine §4.8, W3) ────
    # SELECTION-not-generation display polish on the FINAL product list:
    # laws (single-letter / param / file-stem / PF==UF twin / acronym
    # casing / display collisions), keeper pin channel (content-derived
    # prev-scan join by anchor_id/slug, WYSTAN_KEEPER-gated), ranked
    # deterministic candidates, and the PM-Labeler persona seam (keyed
    # scans). Runs AFTER emission integrity + terminal home (the PF set
    # is final — no naming spend on phantoms) and BEFORE the platform
    # lane + Stage-7 write. Writes ONLY the display channel
    # (Feature.display_name / UserFlow.name) — identity is untouched.
    # Kill-switch: WYSTAN_NAMING_CONTRACT=0 (pre-W3 output
    # byte-identical).
    from wystan.pipeline_v2.naming_contract import (
        naming_contract_enabled,
        run_naming_contract,
    )
    from wystan.pipeline_v2.uf_identity_keeper import keeper_enabled
    if naming_contract_enabled():
        write_stage_input(run_dir, 7, "naming_contract", {
            "product_features": product_features,
            "user_flows": user_flows,
            "bipartite_flows": list(bipartite.flows),
            "prev_scan_json": prev_scan_json,
            "scan_meta": scan_meta,
        })
        with StageLogger(run_dir, 7, "naming_contract") as log_nc:
            try:
                # PM Labeler + Draft Verifier (Wave-3 personas): keyed
                # scans only — the deterministic top choice is the
                # keyless display path. The thesis feeds NAMES only
                # (the reviewed §4.7 consumer seam of the write-only
                # product_thesis scan_meta key — never membership).
                _nc_labeler = None
                _nc_verifier = None
                try:
                    from wystan.pipeline_v2.personas import (
                        build_draft_verifier,
                        build_pm_labeler,
                    )
                    _nc_cache = getattr(ctx, "cache_backend", None)
                    _nc_verifier = build_draft_verifier(
                        model_id=model_id,
                        cost_tracker=tracker,
                        cache=_nc_cache,
                        llm_health=llm_health,
                        log=log_nc,
                    )
                    _nc_labeler = build_pm_labeler(
                        model_id=model_id,
                        cost_tracker=tracker,
                        cache=_nc_cache,
                        llm_health=llm_health,
                        log=log_nc,
                        thesis=scan_meta.get("product_thesis"),
                        verifier=_nc_verifier,
                    )
                except Exception:  # noqa: BLE001 — persona is optional
                    _nc_labeler = None
                    _nc_verifier = None
                nc_tele = run_naming_contract(
                    product_features,
                    user_flows,
                    list(bipartite.flows),
                    prev_scan=prev_scan_json,
                    keeper_on=keeper_enabled(),
                    product_strings=product_strings,
                    routes_index=lineage_result.routes_index,
                    uf_authored_names=_e2e_authored_names,
                    labeler=_nc_labeler,
                    verifier=_nc_verifier,
                    # B27 — arms the package-manifest display channel: a
                    # package-dir-anchored PF takes the display name the
                    # package DECLARES in its own metadata (config.json /
                    # metadata module / package.json), word-split fallback
                    # below. WYSTAN_PF_MANIFEST_NAME=0 restores pre-B27.
                    repo_root=ctx.repo_path,
                )
                scan_meta["naming_contract"] = nc_tele
                log_nc.info(
                    "naming_contract: pf %d (renamed %d, pinned %d, "
                    "cased %d), uf %d (renamed %d, twins %d, synth %d), "
                    "laws %s, labeler_pending %d"
                    % (
                        nc_tele.get("pf_total", 0),
                        nc_tele.get("pf_renamed", 0),
                        nc_tele.get("pf_pinned", 0),
                        nc_tele.get("casing_polished", 0),
                        nc_tele.get("uf_total", 0),
                        nc_tele.get("uf_renamed", 0),
                        nc_tele.get("uf_twins_resolved", 0),
                        nc_tele.get("uf_synth_named", 0),
                        nc_tele.get("laws_fixed"),
                        nc_tele.get("labeler_pending", 0),
                    ),
                    feature=None,
                )
                write_stage_artifact(
                    ctx.repo_path,
                    stage_index=7,
                    stage_name="naming_contract",
                    payload=dict(nc_tele),
                    run_dir=run_dir,
                )
            except Exception as exc:  # noqa: BLE001 — naming must never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"naming-contract failed ({exc}); displays unpolished"
                )
                log_nc.info(
                    f"naming_contract: FAILED ({exc}) — continuing",
                    feature=None,
                )

    # ── S2-A-v3 spray-generalization (WYSTAN_SPRAY_GENERALIZED,
    # default ON since the 2026-07-21 pack-3 flip) ──────────────────────
    # Structural absorption of the generalized R5-2 tech-dir-suffix spray
    # ('Manage setting AI components/constants/…' — the det-aggregation
    # regrain class) over the FINAL display names the naming contract just
    # emitted (probe canon: the boards it judged carried post-contract
    # names). Predicate + parent-name derivation live in naming_contract
    # (beside R5-2, whose paren class the G0 boundary protects); the apply
    # (member union, row drops, I14 repoints) is this seam — the naming
    # module's §4.8 identity law forbids structure writes inside it.
    # Flag OFF/unset ⇒ run_spray_generalization returns None before any
    # mutation ⇒ no scan_meta key ⇒ byte-identical (KS 4-way gate).
    from wystan.pipeline_v2.postmint_rescore import (
        postmint_uf_rescore,
        snapshot_uf_state,
    )
    _spray_before = snapshot_uf_state(user_flows)
    try:
        from wystan.pipeline_v2.spray_absorption import (
            run_spray_generalization,
        )
        _spray_tele = run_spray_generalization(
            user_flows, list(bipartite.flows))
        if _spray_tele is not None:
            scan_meta["spray_generalized"] = _spray_tele
    except Exception as exc:  # noqa: BLE001 — absorption must never break a scan
        scan_meta.setdefault("warnings", []).append(
            f"spray-generalization failed ({exc}); rows unabsorbed"
        )
    # ── B100 post-mint Law C rescore (WYSTAN_UF_POSTMINT_RESCORE) ────
    # The survivor this stage renames (it takes the generalized parent
    # name and absorbs the group's members) was graded by the contract
    # under its OLD name and OLD member set — same disease class as the
    # two minters below (head ruling on Q1/Q3). Row-scoped: only the
    # survivor is re-graded; the absorbed rows are already gone and every
    # untouched row leaves the hook verbatim.
    try:
        postmint_uf_rescore(
            "spray_generalization", user_flows, _spray_before,
            product_features=product_features,
            flows=list(bipartite.flows),
            product_strings=product_strings,
            routes_index=lineage_result.routes_index,
            uf_authored_names=_e2e_authored_names,
            keeper_on=keeper_enabled(),
            repo_root=ctx.repo_path,
            scan_meta=scan_meta,
        )
    except Exception as exc:  # noqa: BLE001 — rescore must never break a scan
        scan_meta.setdefault("warnings", []).append(
            f"postmint-rescore (spray_generalization) failed ({exc}); "
            f"grades kept"
        )

    # ── B75 — UF-giant cases-split (WYSTAN_UF_CASES_SPLIT, default
    # ON since the 2026-07-21 pack-3 flip) ──────────────────────────────
    # Dir-tree case re-grain of giant catch-all journeys (mc >= census
    # band edge 30): >= K qualified surface cases extract as children;
    # the parent row survives as the residual (survivor-id law). Seam
    # rationale: AFTER the naming contract so the giant predicate + the
    # minted child names judge/mint against FINAL display names (the
    # spray precedent — the probe canon boards carried post-contract
    # names); AFTER spray-generalization so a spray-built union parent
    # is visible to the split (same structural-writer family, single
    # writer at a time); BEFORE 6.7e/dispatch-homing/I16-rehome/
    # synth_quality/6.97b-LOC/6.995 so children are ordinary rows to
    # every downstream hygiene pass (adjudication, homing, honest loc>0
    # from member spans, terminal classification). The stage repoints
    # extracted members' flow backpointers itself (I14) — the global
    # emission-integrity pass already ran above this seam.
    # Flag OFF/unset ⇒ run_uf_cases_split returns None before any
    # mutation ⇒ no scan_meta key ⇒ byte-identical (KS 4-way gate).
    # Armed 0-giant boards write no scan_meta key either (giants_seen ==
    # 0 ⇒ nothing was read or written — the Seg C inertness law; the
    # openstatus byte-ident gate).
    _cs_before = snapshot_uf_state(user_flows)
    try:
        from wystan.pipeline_v2.uf_cases_split import (
            run_uf_cases_split,
        )
        _cs_tele = run_uf_cases_split(
            user_flows, list(bipartite.flows),
            routes_index=lineage_result.routes_index,
            repo_root=ctx.repo_path,
        )
        if _cs_tele is not None and _cs_tele.get("giants_seen"):
            scan_meta["uf_cases_split"] = _cs_tele
    except Exception as exc:  # noqa: BLE001 — split must never break a scan
        scan_meta.setdefault("warnings", []).append(
            f"uf-cases-split failed ({exc}); giants kept"
        )
    # ── B100 post-mint Law C rescore (WYSTAN_UF_POSTMINT_RESCORE) ────
    # The children this stage mints are born with a name_confidence the
    # STAGE chose and NO name_evidence — the naming contract already ran
    # above, so nothing ever re-grades them (infisical UF-CS-c8e3fc3fd5
    # 'Layouts addmcpservermodal' + 11 more; highlight x3). The hook lives
    # at the producer (stage-hooks law) and re-applies Law C over exactly
    # the rows this stage minted/renamed. Flag OFF ⇒ the snapshot is None
    # ⇒ no call, no scan_meta key, byte-identical.
    try:
        postmint_uf_rescore(
            "uf_cases_split", user_flows, _cs_before,
            product_features=product_features,
            flows=list(bipartite.flows),
            product_strings=product_strings,
            routes_index=lineage_result.routes_index,
            uf_authored_names=_e2e_authored_names,
            keeper_on=keeper_enabled(),
            repo_root=ctx.repo_path,
            scan_meta=scan_meta,
        )
    except Exception as exc:  # noqa: BLE001 — rescore must never break a scan
        scan_meta.setdefault("warnings", []).append(
            f"postmint-rescore (uf_cases_split) failed ({exc}); grades kept"
        )

    from wystan.pipeline_v2.fold_coherence import (
        apply_fold_coherence,
        fold_coherence_enabled,
    )
    # ── fixb108-v3 (b) — FOLD-COHERENCE law (F3's tail, own flag) ──────
    # A page-grain PF folded away by the F3 rescue must not take its
    # journey down in silence. Keyed c6proof: chatwoot ``voice`` folded
    # into ``twilio`` (PRODUCT receiver) and 6.7d re-derived its journey;
    # ``documents`` folded into ``controllers-core`` (HUB container),
    # where 6.7d does not re-derive — 'Browse and manage documents'
    # (mc=6) died with no gap and no admission. Members were conserved
    # both times; the JOURNEY was the loss.
    #
    # Slot: after the journey layer + naming contract have settled (the
    # B33 post-UF law — homes are final here) and BEFORE
    # synth_quality/emit_coverage_gaps below, so a gapped journey lands
    # as a typed coverage_gaps[] entry in THIS scan rather than the next.
    # Writes ONLY product_feature_id (the №4-reparent precedent);
    # identity, names and member_flow_ids are never touched.
    if fold_coherence_enabled():
        with StageLogger(run_dir, 6, "fold_coherence") as log_fc:
            try:
                _fc_flow_home: dict[str, str | None] = {}
                for _dev in features:
                    _dev_home = getattr(_dev, "product_feature_id", None)
                    for _fl in (getattr(_dev, "flows", None) or []):
                        _fid = getattr(_fl, "id", None) or getattr(
                            _fl, "flow_id", None)
                        if _fid:
                            _fc_flow_home[str(_fid)] = _dev_home
                _fc_tele = apply_fold_coherence(
                    user_flows, product_features, _fc_flow_home)
                scan_meta["fold_coherence"] = _fc_tele
                log_fc.info(
                    "fold_coherence: orphans=%d rehomed=%d gapped=%d" % (
                        _fc_tele.get("orphans", 0),
                        len(_fc_tele.get("rehomed") or []),
                        len(_fc_tele.get("gapped") or []),
                    ),
                    feature=None,
                )
            except Exception as exc:  # noqa: BLE001 — never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"fold_coherence failed ({exc}); journeys left as-is"
                )

    # ── Stage 6.7e — B57 Seg2 journey-evidence adjudicator (keyed-only) ─
    # Runs immediately AFTER the naming contract (selection needs Law C v1
    # name_confidence) and BEFORE synth_quality/emit_coverage_gaps so an
    # adjudicated demote lands as a typed coverage_gaps[] entry in THIS
    # scan. Keyless (no client) ⇒ hard no-op before any mutation and NO
    # scan_meta key — the byte-identity law. Confidence is re-scored only
    # through Law C (rescore_uf_confidence); the stage itself never writes
    # name_confidence. Kill-switch WYSTAN_STAGE_6_7E_ADJUDICATOR
    # (default OFF).
    from wystan.pipeline_v2.stage_6_7e_adjudicator import (
        adjudicator_6_7e_enabled,
        run_stage_6_7e,
    )
    adjudicated_gaps: list[Any] = []
    if adjudicator_6_7e_enabled():
        try:
            adj_tele, adjudicated_gaps = run_stage_6_7e(
                user_flows,
                list(bipartite.flows),
                product_features,
                repo_root=ctx.repo_path,
                product_strings=product_strings,
                routes_index=lineage_result.routes_index,
                uf_authored_names=_e2e_authored_names,
                keeper_on=keeper_enabled(),
                model_id=model_id,
                cost_tracker=tracker,
                cache=getattr(ctx, "cache_backend", None),
                llm_health=llm_health,
            )
            if adj_tele.get("ran"):
                scan_meta["adjudicator_6_7e"] = adj_tele
        except Exception as exc:  # noqa: BLE001 — never break a scan
            adjudicated_gaps = []
            scan_meta.setdefault("warnings", []).append(
                f"stage-6.7e adjudicator failed ({exc}); journeys unchanged")

    # ── Stage 6.985d — B37-ph2 dispatch-mint homing ($0, default ON) ───
    # Re-home each predominantly-dispatch user flow to the PF that OWNS the
    # mint's target file (path_index dev→PF first, anchor-chain fallback —
    # NOT the dev-of-first-attribution). Runs AFTER the final path_index
    # refresh + the flowless-PF backstops so it reads the same owner i16
    # will (no ping-pong) and a source the move leaves flowless never spawns
    # a NEW marker (the backstop already passed while it was covered); runs
    # BEFORE synth_quality so the target PF's marker demotes (its gap
    # dissolves — cal.com Cal Video). Mutates ONLY user_flows[].
    # product_feature_id. Kill-switch WYSTAN_DISPATCH_HOMING_B37P2=0.
    from wystan.pipeline_v2.dispatch_homing import (
        dispatch_homing_enabled,
        home_dispatch_mints,
    )
    if dispatch_homing_enabled():
        try:
            dh_tele = home_dispatch_mints(
                user_flows, features, product_features,
                path_index=lineage_result.path_index)
            if dh_tele.get("rehomed"):
                scan_meta["dispatch_homing"] = dh_tele
        except Exception as exc:  # noqa: BLE001 — never break a scan
            scan_meta.setdefault("warnings", []).append(
                f"dispatch-homing failed ({exc}); UF homes left as-is")

    # S3 arbiter — apply deferred proposals at this pass boundary
    # (rung-priority == pass order; no-op when the flag is OFF).
    _arb_flush(product_features, note="post-dispatch")

    # ── B4 synthesized-journey quality (Stage 6.98) ────────────────────
    # Runs AFTER the naming contract (so demoted seeds/regrounded backstops
    # carry their final display names) and BEFORE the lane + Stage-7 write.
    # (a) Demote member-less ``system_flow_recall`` seeds out of user_flows[]
    #     into scan_meta["system_flow_seeds"] — a hollow journey (0 members,
    #     0 loc) is not a journey. (b) Reground single-member GENERIC backstop
    #     names from their member flow. OUTPUT-ONLY: mutates user_flows[] in
    #     place + flow backpointers + the display channel; validator-neutral
    #     (I7 tracked-only, I24/I13 untouched, I14 backpointers nulled).
    #     Kill-switch: WYSTAN_SYNTH_QUALITY=0 restores pre-B4 output
    #     byte-identically.
    # B23 (behind WYSTAN_MARKER_SURFACE_COORDS, default ON): the pass
    #     additionally (c) preserves the maintainer-authored labels of
    #     Track-C e2e markers (no more 13-18 identical 'Uncovered: <PF>
    #     routes' rows per board) and (d) attaches REAL surface coordinates
    #     (``surface_files`` whole-file spans) to member-less coverage
    #     markers from the mint-carried resolver files / home-PF member
    #     files — Stage 6.97b (below, runs later) then stamps an honest
    #     loc>0 from those spans. ``developer_features`` feeds the per-file
    #     LOC ledger and stays untouched.
    from wystan.pipeline_v2.synth_quality import (
        run_synth_quality,
        synth_quality_enabled,
    )
    # B45 — the typed coverage-gap channel. None (key absent from the result)
    # unless WYSTAN_COVERAGE_GAP_CHANNEL is dual/full, keeping the off path
    # byte-identical to pre-B45. Threaded into the Stage-7 result below.
    coverage_gaps: list[Any] | None = None
    if synth_quality_enabled():
        try:
            _sq_tele = run_synth_quality(
                user_flows,
                list(bipartite.flows),
                product_features,
                scan_meta,
                developer_features=features,
                # fixb131 Seg B — the Law C bundle for the B100 hook at the
                # uf_synth_fold seam (same binding as the four hooks above).
                rescore_ctx={
                    "product_strings": product_strings,
                    "routes_index": lineage_result.routes_index,
                    "uf_authored_names": _e2e_authored_names,
                    "keeper_on": keeper_enabled(),
                    "repo_root": ctx.repo_path,
                },
            )
            _gaps = _sq_tele.get("coverage_gaps")
            # KEY-PRESENCE contract: the pass returns None in off mode (key
            # absent — byte-identity) and a LIST — possibly EMPTY — in
            # dual/full. A zero-gap board still ships "coverage_gaps": [] so
            # consumers ("coverage_gaps" in scan — warden gap-channel-leak
            # class, flowless-silent gap exemption) can detect the channel.
            if _gaps is not None:
                coverage_gaps = list(_gaps)
        except Exception as exc:  # noqa: BLE001 — quality pass never breaks a scan
            scan_meta.setdefault("warnings", []).append(
                f"synth-quality pass failed ({exc}); journeys unchanged"
            )

    # B57 Seg2 — adjudicated demote gaps join the typed channel. The stage
    # gates demotes on the gap channel being ACTIVE, so a non-empty list
    # here implies dual/full mode; merging AFTER emit keeps the B45
    # bijection telemetry intact, and the union re-sorts to the emit order
    # ((product_feature_id, id) — deterministic). Even if the synth-quality
    # pass faulted, the demoted rows' gaps still ship (no silent drop).
    if adjudicated_gaps:
        coverage_gaps = list(coverage_gaps or []) + list(adjudicated_gaps)
        coverage_gaps.sort(key=lambda g: (
            str(getattr(g, "product_feature_id", "") or ""),
            str(getattr(g, "id", "") or ""),
        ))

    # ── platform_infrastructure[] lane (Wave 2b, operator amendment) ───
    # The anchored path's residual surface: one row per lane resident
    # (product_feature_id=None + shared_reason). Assembled AFTER emission
    # integrity (the I2 phantom drop must not leave stale lane rows) and
    # after 6.97 (rows carry loc). None (omitted from output) when the
    # anchored mint did not run — the =0 A/B path stays byte-identical.
    if anchored_mint_applied:
        from wystan.pipeline_v2.stage_6_86_anchored_mint import (
            build_platform_infrastructure_lane,
        )
        try:
            # B52 — user_flows ride along so a flow-bearing lane row can
            # list its lane_ref journeys (additive; OFF byte-identical).
            platform_infrastructure = build_platform_infrastructure_lane(
                features, user_flows=user_flows)
            scan_meta.setdefault("stage_6_86_anchored_mint", {})[
                "platform_infrastructure_rows"
            ] = len(platform_infrastructure)
        except Exception as exc:  # noqa: BLE001 — lane must never break a scan
            platform_infrastructure = []
            scan_meta.setdefault("warnings", []).append(
                f"platform-infrastructure lane failed ({exc}); lane empty"
            )

    # ── Stage 6.99 — path_index-aware I16 journey re-home (B20) ────────
    # Re-home each majority-foreign UF to its STRICT-MAJORITY entry-owner PF,
    # applying the validator's own I16 ruler AFTER the final path_index (2264)
    # AND the lane (above) exist — so the owner map matches the validator
    # exactly and the strict-majority guarantees I16 clears. Mutates ONLY
    # user_flows[].product_feature_id. Kill-switch WYSTAN_I16_REHOME_B20=0.
    from wystan.pipeline_v2.stage_6_99_i16_rehome import (
        i16_rehome_enabled,
        rehome_foreign_entry_ufs,
    )
    if i16_rehome_enabled():
        try:
            rh_tele = rehome_foreign_entry_ufs(
                user_flows, features, product_features,
                lineage_result.path_index, platform_infrastructure)
            if rh_tele.get("rehomed"):
                scan_meta["i16_rehome"] = rh_tele
        except Exception as exc:  # noqa: BLE001 — never break a scan
            scan_meta.setdefault("warnings", []).append(
                f"i16-rehome failed ({exc}); UF homes left as-is")

    # S3 arbiter — apply deferred proposals at this pass boundary
    # (rung-priority == pass order; no-op when the flag is OFF).
    _arb_flush(product_features, note="post-i16")

    # ── Stage 6.99b — B69-v2 post-UF PF-homing hygiene rehome ──────────
    # Anchor-breadth ruler over member entries (mint-time structural truth,
    # via the 6.86 side-channel) — NOT the path_index owner map, which the
    # annexation being cured has itself poisoned (why 6.99/I16 stays blind
    # to this class). Runs AFTER naming/labeler/B31 so the only rows that
    # change are the rows it touches (surgical; the mint-time variant was
    # refuted for full-board redraw — banked fix/b69-pf-homing). Telemetry
    # is written WHENEVER the flag is armed (the cal.com strict-no-op gate
    # needs proof the rail evaluated and stayed inert). Default OFF ⇒
    # byte-identical.
    from wystan.pipeline_v2.stage_6_99b_post_uf_rehome import (
        homing_hygiene_enabled as _hh_enabled,
        run_post_uf_rehome,
    )
    if _hh_enabled():
        try:
            # B73 it2 guard 2 (prior-hold) — rows the B24 nav-rehome stage
            # already adjudicated (stays[] holds + its own moves); consumed
            # ONLY by the flag-gated organic-move lane, inert otherwise.
            _b24_tele = scan_meta.get("mega_pf_nav_rehome") or {}
            _mega_holds: dict[str, str] = {}
            for _s in (_b24_tele.get("stays") or []):
                if isinstance(_s, dict) and _s.get("uf"):
                    _mega_holds[str(_s["uf"])] = str(_s.get("reason") or "held")
            for _mv in (_b24_tele.get("moves") or []):
                if isinstance(_mv, dict) and _mv.get("uf"):
                    _mega_holds.setdefault(
                        str(_mv["uf"]), f"moved:{_mv.get('to') or ''}")
            _hh_tele = run_post_uf_rehome(
                user_flows, features, product_features, _hh_anchor_registry,
                mega_holds=_mega_holds or None)
            scan_meta["post_uf_rehome"] = _hh_tele
        except Exception as exc:  # noqa: BLE001 — never break a scan
            scan_meta.setdefault("warnings", []).append(
                f"post-uf-rehome failed ({exc}); UF homes left as-is")

    # ── Stage 6.9945 — orphan-flow ATTACH (default OFF) ─────────────────
    # The deterministic INVERSE of build_orphan_flow_gaps: fold each
    # unambiguous orphan-UI cohort into the ONE co-located journey that
    # already owns its feature-dir (sub-component flows the 6.7d journey
    # layer dropped), so the gap below is never emitted. Runs BEFORE the
    # gap builder so the attached flows read as CLAIMED. GUARDRAIL: exactly
    # one co-located journey (>=2 or 0 → cohort stays orphan, honest).
    # Flag unset ⇒ inert (no read/mutation) ⇒ byte-identical to main.
    from wystan.pipeline_v2.conservation import (
        attach_orphan_flows,
        orphan_flow_attach_enabled,
    )
    if orphan_flow_attach_enabled():
        with StageLogger(run_dir, 6, "orphan_flow_attach") as log_ofa:
            try:
                _ofa_tele = attach_orphan_flows(
                    user_flows, features, product_features,
                )
                scan_meta["orphan_flow_attach"] = _ofa_tele
                log_ofa.info(
                    "orphan_flow_attach: attached=%d flows=%d ambiguous=%d"
                    " no_home=%d"
                    % (
                        _ofa_tele.get("attached_cohorts", 0),
                        _ofa_tele.get("attached_flows", 0),
                        _ofa_tele.get("ambiguous", 0),
                        _ofa_tele.get("no_home", 0),
                    ),
                    feature=None,
                )
            except Exception as exc:  # noqa: BLE001 — never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"orphan-flow-attach failed ({exc}); orphans left as-is"
                )
                log_ofa.info(
                    f"orphan_flow_attach: FAILED ({exc}) — continuing",
                    feature=None,
                )

    # ── Stage 6.995 — B78 Seg B home-affinity gate (default OFF) ────────
    # Re-home ``tok0`` journeys (name shares zero content tokens with their
    # home) that carry a deterministic BETTER-HOME onto it, via an S3
    # arbiter proposal (rung ``affinity-rehome``). Placement is
    # LEDGER-PROVEN, not chosen: the first cut ran at 6.9855 (pre-mega) and
    # the S3 conflict census showed Stage 6.99/i16 reverting 13/14 proposals
    # right back onto the poisoned homes — i16 judges by the
    # ``path_index → dev → pfid`` owner map, which the annexation being
    # cured has itself poisoned (the exact blindness the 6.99b docstring
    # documents). So the gate runs HERE, after i16 AND after 6.99b — the
    # LAST homing writer before Stage 6.998 (everything below is display /
    # LOC / telemetry channels): arbiter semantics, rung priority == pass
    # order, no circular rung can silently re-accept the poisoned home.
    # Non-dev channel (journey NAME tokens + PF path breadth) — the vacuum
    # cannot fake either. Flag-gated: unset ⇒ this block never runs ⇒
    # byte-identical to main (KS 4-way).
    from wystan.pipeline_v2.conservation import (
        apply_home_affinity_gate,
        build_orphan_flow_gaps,
        home_affinity_gate_enabled,
    )
    # B78-it2 Goal 1 — orphan-flow gap rows computed at THIS checkpoint
    # (operator ruling 2026-07-22); appended to the B45 channel below,
    # AFTER the B68 terminal ladder. Empty unless the Seg B flag is armed.
    _orphan_gap_rows: list[Any] = []
    if home_affinity_gate_enabled():
        # fixb118 — the Seg B landing registry is installed BEFORE the gate:
        # the gate itself records EVERY landing at the move site (not from
        # ``moves``, truncated at 40 rows — behaviour must not depend on a
        # display cap: infisical yields 58 moves). Flag OFF ⇒ install is a
        # no-op ⇒ registry None ⇒ both the tier2 guard and the audit inert.
        from wystan.pipeline_v2.segb_landing_binding import (
            install_landing_registry,
        )
        install_landing_registry()
        with StageLogger(run_dir, 6, "home_affinity_gate") as log_hag:
            try:
                _hag_tele = apply_home_affinity_gate(
                    user_flows, features, product_features,
                )
                _orphan_gap_rows, _og_tele = build_orphan_flow_gaps(
                    user_flows, features, product_features,
                )
                _hag_tele["orphan_gaps"] = _og_tele
                scan_meta["home_affinity_gate"] = _hag_tele
                log_hag.info(
                    "home_affinity_gate: tok0=%d proposed=%d orphan_guarded=%d"
                    " orphan_gap_cohorts=%d"
                    % (
                        _hag_tele.get("tok0", 0),
                        _hag_tele.get("proposed", 0),
                        _hag_tele.get("orphan_guarded", 0),
                        _og_tele.get("cohorts", 0),
                    ),
                    feature=None,
                )
            except Exception as exc:  # noqa: BLE001 — never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"home-affinity-gate failed ({exc}); UF homes left as-is"
                )
                log_hag.info(
                    f"home_affinity_gate: FAILED ({exc}) — continuing",
                    feature=None,
                )

    # ── Stage 6.996 — B85 post-fold domain-foreignness demote ───────────
    # The B22a-resurrection fence: on-board PFs shed FOREIGN member mass
    # (across the domain edge from the anchor's STATIC canonical domain,
    # rungs R1-R4) to its natural home — the most-specific other PF whose
    # anchor's own identity evidence claims the file (now populated: every
    # downstream membership filler incl. the ex-mint-barred fdir anchors is
    # behind us) — or to the cross-unit lane when homeless. Placement is the
    # it2 ruling (option (b), the 6.995 B78-B/C/D precedent): AFTER the last
    # homing writer (the settled journey layer is never re-judged — B33 law;
    # the mint-time cut dissolved supabase Security/Login by stranding
    # their mass pre-population) and BEFORE 6.998, so metrics-recompute +
    # uf_loc/flow_loc/terminal classification consume the FINAL membership.
    # Downstream conflict census: every later pass is display/LOC/telemetry
    # (the 6.998 doctrine); the S3 arbiter applies only UF-home proposals;
    # nav-parent is display-only — nothing re-annexes or reverts a strip.
    # Kill (either flag chain =0) ⇒ the pass returns None before any
    # mutation ⇒ no scan_meta key ⇒ byte-identical (KS 4-way).
    from wystan.pipeline_v2.fold_evidence_demote import (
        run_fold_evidence_demote,
    )
    with StageLogger(run_dir, 6, "fold_evidence_demote") as log_fed:
        try:
            _fed_tele = run_fold_evidence_demote(
                features, product_features, user_flows, ctx,
                anchor_registry=_hh_anchor_registry,
                path_index=lineage_result.path_index,
                platform_infrastructure=platform_infrastructure,
            )
            if _fed_tele is not None:
                scan_meta["fold_evidence_demote"] = _fed_tele
                log_fed.info(
                    "fold_evidence_demote: pfs=%d rehomed=%d(f%d) "
                    "laned=%d(f%d) carves=%d/%d pulled=%d"
                    % (
                        _fed_tele.get("pfs_touched", 0),
                        _fed_tele.get("devs_rehomed", 0),
                        _fed_tele.get("files_rehomed", 0),
                        _fed_tele.get("devs_relaned", 0),
                        _fed_tele.get("files_laned", 0),
                        _fed_tele.get("carve_home", 0),
                        _fed_tele.get("carve_lane", 0),
                        _fed_tele.get("pulled_back_pfs", 0),
                    ),
                    feature=None,
                )
        except Exception as exc:  # noqa: BLE001 — never break a scan
            scan_meta.setdefault("warnings", []).append(
                f"fold-evidence-demote failed ({exc}); membership left as-is"
            )
            log_fed.info(
                f"fold_evidence_demote: FAILED ({exc}) — continuing",
                feature=None,
            )

    # B89 sentinel (critical) — a B86 carve/fold-demote marker leaking into a
    # display field after the demote pass that mints carve devs.
    invariant_hooks.run_stage(
        scan_meta, "6.996",
        product_features=product_features, user_flows=user_flows)

    # ── Stage 6.997 — B84 terminal member-disjoint reconciliation ──────
    # ── Stage 6.997a — B102 I-EXISTS: no member id may dangle ────────
    # flow_grain (T3/T4) folds victim flows into survivors and reshapes the
    # TOP-LEVEL store, but the legacy containment view keeps the victims
    # (documenso: 126 containment-only uuids); late journey minters that
    # read that view mint member_flow_ids pointing at dead uuids. Every
    # member-derived consumer then SILENTLY skips them (6.97b uf_loc's
    # `if fl is None: continue`), so the row keeps member_count>0 and
    # renders loc=0 — the hollow row (documenso UF-041 / UF-L-92a08861d6,
    # infisical UF-046 high+loc=0). Flagless: this restores the I5 contract
    # (eval/validate_scan.py:1769 "member ids dangling"), it does not add
    # behavior. Runs BEFORE the B84 disjoint reconcile so both repairs land
    # ahead of 6.998/6.97b/6.97c/6.97d, which recompute off final membership.
    # Inert (returns None, no scan_meta key ⇒ byte-identical) on a board
    # whose members all resolve.
    from wystan.pipeline_v2.uf_member_exists import run_uf_member_exists

    _ume_tele: dict | None = None
    try:
        # fixb114/P12-M2 — the legacy containment view is handed in READ-ONLY
        # so a victim id absent from the top-level store can still be looked
        # up for its COORDINATES (49/49 of the world's dangling refs live
        # there with spans, 48 of them with an empty ``merged_from``). Only
        # the armed coordinate rung reads it; nothing is re-admitted.
        _ume_containment = [
            fl for f in features for fl in (getattr(f, "flows", None) or ())
        ]
        # fixb116 — ``product_features`` / ``features`` ride along READ-ONLY
        # for the adopt-plausibility conjunct (the row's code-derived
        # identity + its I15 PF scope). Same armed gate as the coordinate
        # rung itself; nothing is mutated through them.
        _ume_tele = run_uf_member_exists(
            user_flows, list(bipartite.flows), _ume_containment,
            product_features, features)
        if _ume_tele is not None:
            scan_meta["uf_member_exists"] = _ume_tele
            # Honest accounting — a dropped member is never silent. Only an
            # UNTRACEABLE drop is a degradation (no lineage to the material);
            # remap/collapse/owned-elsewhere are exact repairs.
            _ume_lost = int(_ume_tele.get("members_dropped_untraceable") or 0)
            if _ume_lost:
                scan_meta.setdefault("warnings", []).append(
                    f"uf-member-exists: {_ume_lost} member id(s) across "
                    f"{_ume_tele.get('rows_touched')} journey rows had no "
                    f"flow and no merge lineage — dropped (member_count "
                    f"resynced; coordinates unrecoverable)"
                )
    except Exception as exc:  # noqa: BLE001 — a repair must never break a scan
        scan_meta.setdefault("warnings", []).append(
            f"uf-member-exists failed ({exc}); dangling members kept"
        )

    # A single flows[].uuid can still sit in the member_flow_ids of >1 UF
    # after the whole Layer-2 surgery (subset-twin dup inflation the
    # journey layer never fully collapses — 581 uuids / 21 boards). Pick
    # ONE authoritative owner per double-claimed uuid (the flow's own
    # back-ref if it is a claimer, else the emission-first claimer with the
    # back-ref repointed), strip the uuid from every other claimer, re-sync
    # member_count, and DISSOLVE any UF the pass leaves memberless (a
    # memberless twin of already-claimed flows — the Stage-6.7d I7-drop
    # semantics). Placement is the B85/B76 seam doctrine: AFTER the last
    # membership/homing writer (6.996) and BEFORE 6.998 metrics-recompute +
    # 6.97b/6.97c UF/flow LOC + terminal classification, so every
    # member-derived aggregate recomputes off the FINAL reconciled
    # membership. Mutates ONLY member_flow_ids / member_count + the
    # repointed flows[].user_flow_id back-refs. Kill-switch
    # WYSTAN_MEMBER_DISJOINT_RECONCILE (default ON since flip-pack №5,
    # KEY_SCHEMA 38; explicit 0/false/off/no) ⇒ the pass returns
    # None before any read/mutation ⇒ no scan_meta key ⇒ byte-identical;
    # an armed board with 0 double-claims ALSO returns None (inertness).
    from wystan.pipeline_v2.member_disjoint_reconcile import (
        run_member_disjoint_reconcile,
    )
    try:
        _mdr_tele = run_member_disjoint_reconcile(
            user_flows, list(bipartite.flows),
        )
        if _mdr_tele is not None:
            scan_meta["member_disjoint_reconcile"] = _mdr_tele
    except Exception as exc:  # noqa: BLE001 — reconciliation must never break a scan
        scan_meta.setdefault("warnings", []).append(
            f"member-disjoint-reconcile failed ({exc}); double-claims kept"
        )

    # ── I14 — re-derive flows[].user_flow_id from FINAL membership ──────
    # emission_integrity's Pass 3 owns this law but runs at Stage 7 BEFORE
    # the 6.7e adjudicator / uf_cases_split / spray / 6.99b rehome / B102 /
    # B84 all move membership again. Measured on the fresh keyed rebattery
    # boards: 0 stale backpointers at the 07-naming_contract input capture,
    # 222 (infisical ON) / 45 (OFF) / 1 / 3 (documenso) at emission — and
    # 100% of them resolvable to a live UF that DOES list the flow, i.e.
    # pure re-points, no nulls. Placed AFTER B84 (the last membership
    # writer of this neighbourhood) and deliberately not before it: B84's
    # owner election reads the back-ref it would otherwise be handed
    # rewritten. Flagless + inert on an agreeing board (no key ⇒
    # byte-identical), same grounds as the B102 member repair above.
    try:
        from wystan.pipeline_v2.uf_member_exists import (
            reconcile_flow_backpointers,
        )

        _bp_tele = reconcile_flow_backpointers(
            user_flows, list(bipartite.flows))
        if _bp_tele is not None:
            scan_meta["uf_flow_backpointers"] = _bp_tele
    except Exception as exc:  # noqa: BLE001 — a repair must never break a scan
        scan_meta.setdefault("warnings", []).append(
            f"uf-flow-backpointers failed ({exc}); stale backpointers kept"
        )

    # B89 sentinel (critical) — the I-DISJOINT invariant as a stamp: any
    # flow uuid still double-claimed after the B84 reconcile (kill-switched
    # / regressed reconcile). Wraps the existing runtime assert.
    # B102 adds the I-EXISTS sentinel on the same key; it needs the flow
    # store to judge (a caller passing no flows leaves it vacuously silent).
    invariant_hooks.run_stage(
        scan_meta, "6.997", user_flows=user_flows,
        flows=list(bipartite.flows),
        member_exists_accounted=(
            (_ume_tele or {}).get("abstained_row_ids") or []))

    # fixb116 — the abstain sentinel. The CRITICAL I-EXISTS hook above skips
    # an accounted row WHOLE, so a board carrying a live dangling uuid
    # reported count=0 (ollama UF-001 / directus UF-049 / infisical UF-226:
    # each in ``abstained_rows``, each invisible to the sentinel). This WARN
    # class counts those refs INDEPENDENTLY of the abstain ruling — a
    # conservation abstain is labeled debt, not an unnoticed violation, and
    # "zero silent loc=0 journeys" needs the count to exist. OWN stage key,
    # fired only when the coordinate rung is armed, so the default world's
    # ``invariant_hooks[]`` is byte-identical.
    from wystan.pipeline_v2.uf_member_exists import (
        coord_lineage_enabled as _coord_lineage_armed,
    )
    if _coord_lineage_armed():
        invariant_hooks.run_stage(
            scan_meta, "6.997_member_abstain", user_flows=user_flows,
            flows=list(bipartite.flows),
            member_exists_accounted=(
                (_ume_tele or {}).get("abstained_row_ids") or []))

    # ── Stage 6.997 — B81 agent-surface (Seg A detector + Seg B/C stage) ──
    # The tool/skill registry becomes a capability surface. A deterministic
    # ($0 LLM) registry-census detector reads the repo's PYTHON tool registry;
    # if present, the stage tags/re-homes the existing agent-entry journeys
    # (Seg B) and mints ~1-per-domain ``via:agent`` capability journeys homed
    # in the real capability PFs (Seg C). PLACEMENT (it2 — the keyed A/B
    # refutation of the post-devgrain point): AFTER the last journey-reshaping
    # pass (6.7e adjudicator / 6.98 synth-quality / 6.99 + 6.99b rehomes /
    # 6.995 / 6.996 B85 — the settled journey layer is never re-judged, B33
    # law; at the old post-devgrain point the KEYED-only 6.7e adjudicator
    # demoted the 1-member mints to gap rows, orphaning their claimed flows,
    # and the mints' presence in its candidate pool perturbed non-agent
    # batches) and BEFORE 6.998, so metrics-recompute + uf_loc + terminal
    # classification consume the mints as FINAL membership. Conservation is
    # by-construction: no member-less mint (no mint-time bar), no source
    # journey emptied, no PF invented. A registry-less repo (langfuse's TS
    # registry is invisible to the Python detector; and every non-agent repo)
    # leaves the board byte-identical (inertness). Default ON since flip-pack
    # №5 (WYSTAN_AGENT_SURFACE, KEY_SCHEMA 38) — explicit 0/false/off/no inert.
    from wystan.pipeline_v2.agent_surface import (
        agent_anatomy_rows_enabled,
        agent_mount_attribution_enabled,
        agent_skills_enabled,
        agent_surface_enabled,
        agent_surface_ts_enabled,
        agent_system_prompt_enabled,
        detect_registry_census,
        run_agent_surface,
    )
    if (agent_surface_enabled() and anchored_mint_applied
            and not uf_suppressed):
        with StageLogger(run_dir, 6, "agent_surface") as log_as:
            try:
                _pf_names = [
                    str(getattr(p, "display_name", None) or getattr(p, "name", ""))
                    for p in product_features
                    if (getattr(p, "display_name", None) or getattr(p, "name", None))
                ]
                # B81-it2 — anchored TS Form A is gated on its OWN sub-flag
                # (WYSTAN_AGENT_SURFACE_TS, default OFF). When unset the call
                # is Python-only and byte-identical to the shipped world.
                # Phase-1 — CONSUMER mount-site parsing is gated on its OWN flag
                # (WYSTAN_AGENT_MOUNT_ATTRIBUTION, default OFF). When unset the
                # census carries no mount_consumers and the stage is byte-identical.
                _census = detect_registry_census(
                    ctx.repo_path, pf_names=_pf_names,
                    include_ts=agent_surface_ts_enabled(),
                    include_mounts=agent_mount_attribution_enabled(),
                    include_system_prompts=agent_system_prompt_enabled(),
                    include_skills=agent_skills_enabled(),
                    include_anatomy_rows=agent_anatomy_rows_enabled(),
                )
                # INERTNESS CONTRACT: a registry-less repo (langfuse's TS
                # registry is invisible to the Python detector; every non-agent
                # repo) must be byte-identical armed-vs-OFF — so scan_meta is
                # stamped ONLY when a registry is actually present. When absent,
                # the stage is a pure no-op and the board is untouched.
                if _census.present:
                    _as_tele: dict[str, Any] = dict(_census.telemetry())
                    _as_before = snapshot_uf_state(user_flows)
                    _stage_tele: dict[str, Any] = run_agent_surface(
                        _census, product_features, user_flows,
                        list(bipartite.flows),
                    )
                    _as_tele["stage"] = _stage_tele
                    # it3 complete-or-drop (panel fix №2): scan_meta
                    # ``domains`` claims coverage ONLY for domains the stage
                    # actually minted for; the merely-DETECTED remainder is
                    # reported separately and never counts as covered.
                    _as_tele["domains"] = list(
                        _stage_tele.get("domains_minted", []))
                    _as_tele["domain_count"] = len(_as_tele["domains"])
                    _as_tele["domains_detected_unminted"] = list(
                        _stage_tele.get("domains_detected_unminted", []))
                    _as_tele["domain_count_detected"] = len(
                        _census.domains())
                    # Phase-1 (armed-only) — surface mount-attribution at the top
                    # of scan_meta.agent_surface when a consumer mount fired; the
                    # keys are absent on the flag-OFF board (byte-identical).
                    if _stage_tele.get("mount_attribution"):
                        _as_tele["domains_mount_attributed"] = list(
                            _stage_tele.get("domains_mount_attributed", []))
                        _as_tele["mount_attribution"] = _stage_tele[
                            "mount_attribution"]
                    # Phase-2 (armed-only) — surface system-prompt detection.
                    if _stage_tele.get("system_prompt"):
                        _as_tele["system_prompt"] = _stage_tele["system_prompt"]
                    # Phase-3 (armed-only) — surface the skill layer.
                    if _stage_tele.get("skill_layer"):
                        _as_tele["skill_layer"] = _stage_tele["skill_layer"]
                    # Phase-4 (armed-only) — surface the import-bridge anatomy rows.
                    if _stage_tele.get("anatomy_rows"):
                        _as_tele["anatomy_rows"] = _stage_tele["anatomy_rows"]
                    scan_meta["agent_surface"] = _as_tele
                    # ── B100 post-mint Law C rescore ───────────────────
                    # The via:agent capability journeys this stage mints
                    # (langfuse UF-AGENT-001) are born 'medium' with NO
                    # name_evidence — minted long after the naming
                    # contract, never re-graded. Row-scoped by design:
                    # this seam sits AFTER 6.7e and 6.98 synth_quality, so
                    # only the rows THIS stage minted/renamed are
                    # re-graded; every other row leaves the hook verbatim
                    # (adjudicated:* and member-agreement grades stand).
                    # Flag OFF ⇒ snapshot None ⇒ byte-identical.
                    try:
                        postmint_uf_rescore(
                            "agent_surface", user_flows, _as_before,
                            product_features=product_features,
                            flows=list(bipartite.flows),
                            product_strings=product_strings,
                            routes_index=lineage_result.routes_index,
                            uf_authored_names=_e2e_authored_names,
                            keeper_on=keeper_enabled(),
                            repo_root=ctx.repo_path,
                            scan_meta=scan_meta,
                        )
                    except Exception as _exc:  # noqa: BLE001 — never break a scan
                        scan_meta.setdefault("warnings", []).append(
                            f"postmint-rescore (agent_surface) failed "
                            f"({_exc}); grades kept"
                        )
                    log_as.info(
                        "agent_surface: present=True tools=%d domains=%d "
                        "mints=%d entry_tagged=%d conserved=%s" % (
                            _as_tele.get("tool_count", 0),
                            _as_tele.get("domain_count", 0),
                            len(_stage_tele.get("mints", [])),
                            len(_stage_tele.get("entry_tagged", [])),
                            _stage_tele.get("conservation", {}).get(
                                "conserved", True),
                        ),
                        feature=None,
                    )
                else:
                    log_as.info(
                        "agent_surface: no registry — inert (board untouched)",
                        feature=None,
                    )
            except Exception as exc:  # noqa: BLE001 — never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"agent_surface failed ({exc}); board left untouched"
                )
                log_as.info(
                    f"agent_surface: FAILED ({exc}) — continuing", feature=None,
                )

    # ── Stage 6.9965 — B87 rung-2 (bullet 3) token-grain journey re-home ──
    # Post-mint token rung (probe-canon E2 H2-refutation: the fold ladder
    # votes by member files, not resource tokens, so a killed/laned/
    # container-homed journey needs a token-grain rehome). PLACEMENT: in the
    # 6.996+ post-homing family, AFTER 6.997/agent-surface (the settled
    # journey layer is never re-judged, B33/B85 law) and BEFORE 6.998
    # metrics-recompute (so uf_loc + terminal classification consume the
    # final homes). Surgical blast radius — only mis-homed rows move,
    # members are conserved. Gated by WYSTAN_PRODUCT_RIGHT_GATE (default
    # OFF ⇒ pure no-op / byte-identical; kill-switch).
    # ── Stage 6.9964 — B90 pin-closers: transport-donor PF lane (Seg A) +
    # api-root-stub PF demote (Seg B). Both default OFF. Wall-slot: AFTER
    # the whole homing family (6.99/6.99b/6.995/6.996/6.997 — the journey
    # layer is final when evidence is judged; the B33 post-UF law) and
    # BEFORE the 6.9965 token re-home below, so a laned donor's real
    # journeys (pfid=None + lane_ref) are token-re-homed to their entity PF
    # (or stay honestly laned) in the SAME scan, and before 6.998
    # metrics-recompute / terminal classification. Closes the operator pins
    # cal-trpc-pf-visible (Seg A: ws:packages/trpc renders as a PF — the
    # B48 fdir-only transport_candidates channel never carried ws-anchored
    # donors) and cal-link-api-route-stub (Seg B: route:apps/web/app/api/
    # link, zero product evidence). The 6.9964 invariant hooks fire ONLY
    # under the segment flags so the unset world stays byte-identical.
    from wystan.pipeline_v2.stage_6_9964_pin_closers import (
        api_container_demote_enabled,
        api_stub_demote_enabled,
        b48_sacred_units,
        nav_seam_keys,
        route_render_util_demote_enabled,
        run_api_container_demote,
        run_api_stub_demote,
        run_route_render_util_demote,
        run_transport_pf_lane,
        transport_pf_lane_enabled,
    )
    _b90_donor_keys: list[str] = []
    if (transport_pf_lane_enabled() and anchored_mint_applied
            and not uf_suppressed):
        with StageLogger(run_dir, 6, "transport_pf_lane") as log_tpl:
            try:
                _tpl_tele = run_transport_pf_lane(
                    product_features, features, user_flows, ctx)
                scan_meta["transport_pf_lane"] = _tpl_tele
                _b90_donor_keys = list(_tpl_tele.get("donor_keys") or [])
                log_tpl.info(
                    "transport_pf_lane: donors=%d laned=%d ufs_laned=%d "
                    "synth_dropped=%d devs_laned=%d" % (
                        len(_b90_donor_keys),
                        len(_tpl_tele.get("laned") or []),
                        _tpl_tele.get("ufs_laned", 0),
                        sum(len(v) for v in
                            (_tpl_tele.get("ufs_dropped_synth") or {}).values()),
                        _tpl_tele.get("devs_laned", 0),
                    ),
                    feature=None,
                )
            except Exception as exc:  # noqa: BLE001 — never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"transport_pf_lane failed ({exc}); donor PFs left product"
                )
                log_tpl.info(
                    f"transport_pf_lane: FAILED ({exc}) — continuing",
                    feature=None,
                )
    # B98 rung-3b — a headless abstain for the API-demote family: on a
    # headless repo (the 6.86 headless_product_spine verdict in scan_meta —
    # the same channel as b48_sacred) the API surface IS the product; the
    # B90/B91 doctrine "api = plumbing" was written for web apps and ate
    # endpoint families (ollama 33 family mints → 0). The abstain is loud.
    _headless_repo = bool(
        ((scan_meta.get("stage_6_86_anchored_mint") or {})
         .get("headless_product_spine")))
    if _headless_repo:
        scan_meta["api_demote_headless_abstain"] = True
    if (api_stub_demote_enabled() and anchored_mint_applied
            and not uf_suppressed and not _headless_repo):
        with StageLogger(run_dir, 6, "api_stub_demote") as log_asd:
            try:
                _asd_tele = run_api_stub_demote(
                    features, product_features, user_flows,
                    # DEMOTE channel (Fix A): weak echo ∪ vue-lift.
                    nav_keys=frozenset(_nav_keys_demote),
                )
                scan_meta["api_stub_demote"] = _asd_tele
                log_asd.info(
                    "api_stub_demote: eligible=%d demoted=%d abstained=%d "
                    "devs(repointed=%d unowned=%d)" % (
                        _asd_tele.get("eligible", 0),
                        len(_asd_tele.get("demoted") or []),
                        len(_asd_tele.get("abstained") or []),
                        _asd_tele.get("devs_repointed", 0),
                        _asd_tele.get("devs_unowned", 0),
                    ),
                    feature=None,
                )
            except Exception as exc:  # noqa: BLE001 — never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"api_stub_demote failed ({exc}); stub PFs left product"
                )
                log_asd.info(
                    f"api_stub_demote: FAILED ({exc}) — continuing",
                    feature=None,
                )
    # B91 H4 — api-container discriminator (same seam, AFTER the Seg B
    # stub arm so phase-1 judges the post-stub board; before the 6.9965
    # token re-home + 6.998 metrics like the rest of the 6.9964 family).
    _b91_demoted_keys: list[str] = []
    if (api_container_demote_enabled() and anchored_mint_applied
            and not uf_suppressed and not _headless_repo):
        with StageLogger(run_dir, 6, "api_container_demote") as log_acd:
            try:
                _acd_tele = run_api_container_demote(
                    features, product_features, user_flows, ctx,
                    # B91: mint echo ∪ the author's declared nav tree —
                    # the echo alone falsely abstains the pin board
                    # (RefApp). Seg B's own guard stays UNTOUCHED.
                    # DEMOTE channel (Fix A): seeded with the demote set.
                    nav_keys=nav_seam_keys(ctx, _nav_keys_demote),
                    sacred_units=b48_sacred_units(scan_meta),
                )
                scan_meta["api_container_demote"] = _acd_tele
                _b91_demoted_keys = [
                    str(d.get("pf") or "")
                    for d in (_acd_tele.get("demoted") or [])
                ]
                log_acd.info(
                    "api_container_demote: eligible=%d demoted=%d "
                    "abstained=%d devs(repointed=%d unowned=%d)" % (
                        _acd_tele.get("eligible", 0),
                        len(_acd_tele.get("demoted") or []),
                        len(_acd_tele.get("abstained") or []),
                        _acd_tele.get("devs_repointed", 0),
                        _acd_tele.get("devs_unowned", 0),
                    ),
                    feature=None,
                )
            except Exception as exc:  # noqa: BLE001 — never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"api_container_demote failed ({exc}); "
                    "container PFs left product"
                )
                log_acd.info(
                    f"api_container_demote: FAILED ({exc}) — continuing",
                    feature=None,
                )
    # B93 route-render-util demote (same seam, AFTER the H4 container arm so
    # phase-1 judges the post-container board; before the 6.9965 token
    # re-home + 6.998 metrics like the rest of the 6.9964 family). Closes the
    # operator pin novu-html-route-markup (a route: PF whose PAGE surface is a
    # backend *page.{ts,js} render helper with no authored view, no nav, no
    # substantive journey). Default OFF — a pure no-op in the unset world.
    _b93_demoted_keys: list[str] = []
    if (route_render_util_demote_enabled() and anchored_mint_applied
            and not uf_suppressed):
        with StageLogger(run_dir, 6, "route_render_util_demote") as log_rru:
            try:
                _rru_tele = run_route_render_util_demote(
                    features, product_features, user_flows,
                    # DEMOTE channel (Fix A): seeded with the demote set.
                    nav_keys=nav_seam_keys(ctx, _nav_keys_demote),
                    sacred_units=b48_sacred_units(scan_meta),
                )
                scan_meta["route_render_util_demote"] = _rru_tele
                _b93_demoted_keys = [
                    str(d.get("pf") or "")
                    for d in (_rru_tele.get("demoted") or [])
                ]
                log_rru.info(
                    "route_render_util_demote: eligible=%d demoted=%d "
                    "abstained=%d devs(repointed=%d unowned=%d)" % (
                        _rru_tele.get("eligible", 0),
                        len(_rru_tele.get("demoted") or []),
                        len(_rru_tele.get("abstained") or []),
                        _rru_tele.get("devs_repointed", 0),
                        _rru_tele.get("devs_unowned", 0),
                    ),
                    feature=None,
                )
            except Exception as exc:  # noqa: BLE001 — never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"route_render_util_demote failed ({exc}); "
                    "render-util PFs left product"
                )
                log_rru.info(
                    f"route_render_util_demote: FAILED ({exc}) — continuing",
                    feature=None,
                )
    if ((transport_pf_lane_enabled() or api_stub_demote_enabled())
            and anchored_mint_applied and not uf_suppressed):
        invariant_hooks.run_stage(
            scan_meta, "6.9964",
            product_features=product_features, user_flows=user_flows,
            transport_donor_keys=_b90_donor_keys,
        )
    # B91 hook rides its OWN registry key: registering it on "6.9964"
    # would stamp a third record in the DEFAULT world (Seg A/B are
    # default ON since flip-pack №7) and break the unset ≡ OFF
    # byte-identity law. Fires ONLY under the B91 flag.
    if (api_container_demote_enabled() and anchored_mint_applied
            and not uf_suppressed and not _headless_repo):
        invariant_hooks.run_stage(
            scan_meta, "6.9964_api_container",
            product_features=product_features,
            api_container_demoted_keys=_b91_demoted_keys,
        )
    # B93 hook rides its OWN registry key ("6.9964_route_render_util"): the
    # arm is default OFF, so phase_finalize fires this key ONLY when armed —
    # keeping the default world byte-identical (the B91 own-key precedent).
    if (route_render_util_demote_enabled() and anchored_mint_applied
            and not uf_suppressed):
        invariant_hooks.run_stage(
            scan_meta, "6.9964_route_render_util",
            product_features=product_features,
            route_render_util_demoted_keys=_b93_demoted_keys,
        )

    from wystan.pipeline_v2.stage_6_9965_token_journey_rehome import (
        product_right_gate_enabled as _pr_gate_enabled,
        run_token_journey_rehome,
    )
    if _pr_gate_enabled() and anchored_mint_applied and not uf_suppressed:
        with StageLogger(run_dir, 6, "token_journey_rehome") as log_tjr:
            try:
                _tjr_tele = run_token_journey_rehome(
                    product_features, user_flows,
                    # fixb109 donor guard: dev stamps carry the flow-ful test
                    # (mirror of the 6.7d backstop's ``pf_flows``). Ignored
                    # while WYSTAN_TJR_DONOR_GUARD is off.
                    developer_features=features,
                )
                scan_meta["token_journey_rehome"] = _tjr_tele
                log_tjr.info(
                    "token_journey_rehome: candidates=%d rehomed=%d "
                    "fallbacks=%d" % (
                        _tjr_tele.get("candidates", 0),
                        _tjr_tele.get("rehomed", 0),
                        _tjr_tele.get("fallbacks", 0),
                    ),
                    feature=None,
                )
            except Exception as exc:  # noqa: BLE001 — never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"token_journey_rehome failed ({exc}); homes left as-is"
                )
                log_tjr.info(
                    f"token_journey_rehome: FAILED ({exc}) — continuing",
                    feature=None,
                )

    # ── Stage 6.9966-FM — Common Tier-2 file-sourced container minting ──
    # Decouple the container decomposition VERDICT from the journey draw: an
    # 8.9.5-eligible single-generic-components-blob container (hoppscotch
    # ``common``) decomposes into its file-domain PFs DETERMINISTICALLY from
    # the prompt-hash-CACHED 8.9.5 labels (byte-identical across draws), then
    # its journeys attach BY NAME and the file-emptied container demotes. Runs
    # BEFORE 6.9966 so the draw-independent decomposition lands before the
    # draw-dependent journey-rehome ever sees the container (on K1 6.9966 would
    # otherwise journey-mint 5 + demote it first). Default ON since flip-pack
    # №15 (KEY_SCHEMA 50, 2026-07-31; keyed 2-draw proof hoppscotch — mint-set
    # identical, Common demoted both draws, 10 domains stable); explicit
    # 0/false/off/no is the kill-switch (never called, no scan_meta key ⇒
    # byte-identical pre-flip OFF-world).
    from wystan.pipeline_v2.stage_6_9966_container_journey_rehome import (
        container_file_mint_enabled as _cfm_enabled,
        run_container_file_mint,
    )
    if _cfm_enabled() and anchored_mint_applied and not uf_suppressed:
        with StageLogger(run_dir, 6, "container_file_mint") as log_cfm:
            try:
                _cfm_tele = run_container_file_mint(
                    product_features, user_flows, features, ctx,
                    flows=list(bipartite.flows),
                )
                scan_meta["container_file_mint"] = _cfm_tele
                log_cfm.info(
                    "container_file_mint: containers=%d minted=%d rehomed=%d "
                    "residual=%d demoted=%d" % (
                        len(_cfm_tele.get("containers", [])),
                        len(_cfm_tele.get("minted", [])),
                        _cfm_tele.get("rehomed", 0),
                        _cfm_tele.get("residual", 0),
                        len(_cfm_tele.get("demoted", [])),
                    ),
                    feature=None,
                )
            except Exception as exc:  # noqa: BLE001 — never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"container_file_mint failed ({exc}); homes left as-is"
                )
                log_cfm.info(
                    f"container_file_mint: FAILED ({exc}) — continuing",
                    feature=None,
                )

    # ── Stage 6.9966 — B container-journey-rehome ──────────────────────
    # The residual 6.9965 cannot place — a journey homed on a STRUCTURAL
    # container (ws:/generic-bucket) with NO existing domain-PF target —
    # is B's input. B mints the absent domain-PF from the code-dir (no-husk
    # + demo gated), re-homes the journey by NAME, dissolves aggregates, and
    # leaves the rest honest-residual. Runs AFTER 6.9965 (clean composition —
    # only its unplaced residual is inherited) and BEFORE 6.998 (so the
    # minted home is loc-stamped + terminal-classified like any PF, else a
    # B76-class stale-metrics row). Gated like 6.9965; default OFF (unset ≡
    # explicit 0/false/off/no ⇒ pure no-op, byte-identical).
    from wystan.pipeline_v2.stage_6_9966_container_journey_rehome import (
        container_journey_rehome_enabled as _cjr_enabled,
        run_container_journey_rehome,
    )
    if _cjr_enabled() and anchored_mint_applied and not uf_suppressed:
        with StageLogger(run_dir, 6, "container_journey_rehome") as log_cjr:
            try:
                _cjr_tele = run_container_journey_rehome(
                    product_features, user_flows, features, ctx,
                    flows=list(bipartite.flows),
                )
                scan_meta["container_journey_rehome"] = _cjr_tele
                log_cjr.info(
                    "container_journey_rehome: containers=%d minted=%d "
                    "rehomed=%d dissolved=%d residual=%d demoted=%d" % (
                        len(_cjr_tele.get("containers", [])),
                        len(_cjr_tele.get("minted", [])),
                        _cjr_tele.get("rehomed", 0),
                        _cjr_tele.get("dissolved", 0),
                        _cjr_tele.get("residual", 0),
                        len(_cjr_tele.get("demoted", [])),
                    ),
                    feature=None,
                )
                # B89 stage-producer hook — OWN registry key (never a default
                # key): the arm is default OFF, so phase_finalize fires this key
                # ONLY when armed, keeping the default world byte-identical.
                invariant_hooks.run_stage(
                    scan_meta, "6.9966_container_journey_rehome",
                    product_features=product_features, user_flows=user_flows,
                    container_rehome_tele=_cjr_tele,
                )
            except Exception as exc:  # noqa: BLE001 — never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"container_journey_rehome failed ({exc}); homes left as-is"
                )
                log_cjr.info(
                    f"container_journey_rehome: FAILED ({exc}) — continuing",
                    feature=None,
                )

    # ── Stage 6.9967 — Pin-cycle-3 M2 ws-containment fold ──────────────
    # A ws:-anchored PF whose anchor path is a STRICT directory-descendant
    # of another ws:-anchored PF folds into the enclosing package PF when
    # every journey it carries is redundant with the enclosing scope (a
    # host/shell sub-component); a descendant contributing a distinct
    # product-wide capability (relay/plugin-relay transport) is never
    # folded (journey-guard). Members/paths/journeys move to the enclosing
    # PF (0 orphan). Runs AFTER the journey layer is final (so redundancy
    # is measurable) and BEFORE 6.998 (so the enclosing PF's metrics are
    # recomputed over the folded membership). Default OFF; unset ≡ 0 ⇒
    # pure no-op, byte-identical.
    from wystan.pipeline_v2.stage_ws_containment_fold import (
        run_ws_containment_fold,
        ws_containment_fold_enabled,
    )
    if (ws_containment_fold_enabled() and anchored_mint_applied
            and not uf_suppressed):
        with StageLogger(run_dir, 6, "ws_containment_fold") as log_wcf:
            try:
                _wcf_tele = run_ws_containment_fold(
                    product_features, user_flows, features,
                )
                scan_meta["ws_containment_fold"] = _wcf_tele
                log_wcf.info(
                    "ws_containment_fold: ws_pfs=%d folded=%d journeys_moved=%d "
                    "members_moved=%d devs_repointed=%d" % (
                        _wcf_tele.get("ws_pfs", 0),
                        len(_wcf_tele.get("folded", [])),
                        _wcf_tele.get("journeys_moved", 0),
                        _wcf_tele.get("members_moved", 0),
                        _wcf_tele.get("devs_repointed", 0),
                    ),
                    feature=None,
                )
            except Exception as exc:  # noqa: BLE001 — never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"ws_containment_fold failed ({exc}); PFs left untouched"
                )
                log_wcf.info(
                    f"ws_containment_fold: FAILED ({exc}) — continuing",
                    feature=None,
                )

    # ── Stage 6.998 — B76 metrics recompute-on-emission ────────────────
    # Stage 6 stamped commit metrics ONCE, before the whole Layer-2
    # surgery; every post-Stage-6 mint (8.9 subdecompose / 6.87
    # excavation / file-lane / provenance re-home) shipped tc=0 rows
    # wearing inherited authors/health, and the PF layer summed stale
    # contributor numbers (Alerts 5 vs ~63 real). Re-run the SAME
    # deterministic sweep over the FINAL membership here — after the
    # last membership-mutating stage of the phase (emission integrity's
    # phantom drops + path_index refresh, spray absorption, and the
    # 6.99/6.99b journey re-homes are all behind us; everything below
    # is display / LOC / telemetry channels) and before the Stage-7
    # write. PF metrics come from each PF's OWN path-set with
    # per-commit dedup — never sum-over-contributors. Metric fields
    # only: membership and hotspot_files are never touched.
    # Kill-switch WYSTAN_METRICS_RECOMPUTE (default ON since the
    # 2026-07-21 pack-3 flip) — explicit =0
    # never enters the pass ⇒ no scan_meta key ⇒ byte-identical.
    from wystan.pipeline_v2.metrics_recompute import (
        metrics_recompute_enabled,
        run_metrics_recompute,
    )
    if metrics_recompute_enabled():
        with StageLogger(run_dir, 7, "metrics_recompute") as log_mr:
            try:
                mr_tele = run_metrics_recompute(
                    features, product_features, ctx.commits,
                )
                scan_meta["metrics_recompute"] = mr_tele
                log_mr.info(
                    "metrics_recompute: dev %d rows (impossible %d -> %d), "
                    "pf %d rows (impossible %d -> %d)" % (
                        mr_tele["dev_rows"],
                        mr_tele["impossible_dev_before"],
                        mr_tele["impossible_dev_after"],
                        mr_tele["pf_rows"],
                        mr_tele["impossible_pf_before"],
                        mr_tele["impossible_pf_after"],
                    ),
                    feature=None,
                )
                write_stage_artifact(
                    ctx.repo_path,
                    stage_index=7,
                    stage_name="metrics_recompute",
                    payload=dict(mr_tele),
                    run_dir=run_dir,
                )
            except Exception as exc:  # noqa: BLE001 — metrics must never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"metrics-recompute failed ({exc}); metrics left as-is"
                )
                log_mr.info(
                    f"metrics_recompute: FAILED ({exc}) — continuing "
                    f"with Stage-6 values",
                    feature=None,
                )

    # ── W3 rider — full-bill LLM cost refresh (chain4 finding) ─────
    # ``run.py`` snapshots ``cost_usd``/``calls`` into scan_meta BEFORE
    # this phase runs, so every finalize-phase LLM call (6.7c splitter,
    # 6.7b refiner, 6.7d journey abstraction — the ANCHORED Call-1
    # included — and the W3 personas) was invisible to the output JSON,
    # the CLI cost line, and the wave-runner ledger: chain4 measured the
    # CLI reporting $0.0000 while 6.7d telemetry carried cost_usd=0.147.
    # The shared CostTracker records every one of those calls (standing
    # cost law) — re-snapshot it HERE, after the last LLM-bearing stage
    # and before the output writer consumes scan_meta. ``calls`` becomes
    # the tracker's full call count (per-stage detail keys are
    # unchanged); keyless scans stay byte-identical (0 == 0).
    scan_meta["cost_usd"] = round(tracker.total_cost_usd, 4)
    scan_meta["calls"] = tracker.call_count

    # ── S2 Seg D — degradation-honesty stamp (flag-gated, additive) ──────
    # The refiner (6.7b) and journey abstraction (6.7d) telemetry blocks are
    # both in scan_meta by now. A fail-open scan (the whole fresh refiner batch
    # failing at cost==0 = a dead key mid-scan, or 6.7d applied=False with real
    # candidates) currently self-reports healthy (degradations[]==[] in BOTH the
    # good and bad RefApp board — probe 2026-07-18). Under WYSTAN_DEGRADATION_
    # STAMP, append the typed FATAL records so validate_scan / keyed_proof FAIL
    # the proof gate. Default OFF → nothing appended → degradations[] byte-ident.
    from wystan.pipeline_v2.degradations import (
        degradation_stamp_enabled,
        detect_finalize_degradations,
    )
    if degradation_stamp_enabled():
        _stamped = detect_finalize_degradations(
            refiner=scan_meta.get("stage_6_7b_uf_refiner"),
            journey_abstraction=scan_meta.get("stage_6_7d_journey_abstraction"),
            # it3 widening — the generic zero-cost-fresh-fail law over the
            # other finalize LLM stages (the 2026-07-18 credit-400 pair:
            # splitter + 6.7e slipped the stamp).
            llm_stages={
                "stage_6_7c_uf_splitter":
                    scan_meta.get("stage_6_7c_uf_splitter"),
                "adjudicator_6_7e": scan_meta.get("adjudicator_6_7e"),
            },
        )
        if _stamped:
            scan_meta.setdefault("degradations", []).extend(_stamped)

    # ── S2 Seg C — LLM batch-canon cache-hit-rate telemetry (flag-gated) ──
    # One rollup ratio over the finalize-phase LLM batch stages (6.7c split /
    # 6.7b refine / 6.7d abstraction) so the canon's effect — volatile-count
    # drifts no longer invalidating keys — is measurable per scan. Additive
    # key, emitted ONLY under WYSTAN_LLM_BATCH_CANON (OFF → byte-ident).
    from wystan.pipeline_v2.stage_6_7d_llm_journey_abstraction import (
        batch_canon_enabled as _batch_canon_on,
    )
    if _batch_canon_on():
        _r = scan_meta.get("stage_6_7b_uf_refiner") or {}
        _s = scan_meta.get("stage_6_7c_uf_splitter") or {}
        _j = scan_meta.get("stage_6_7d_journey_abstraction") or {}
        _hits = (int(_r.get("cache_hits") or 0) + int(_s.get("cache_hits") or 0)
                 + (1 if _j.get("cache_hit") else 0))
        _calls = (int(_r.get("llm_calls") or 0) + int(_s.get("llm_calls") or 0)
                  + int(_j.get("llm_calls") or 0))
        _total = _hits + _calls
        scan_meta["llm_batch_canon"] = {
            "enabled": True,
            "cache_hits": _hits,
            "llm_calls": _calls,
            "hit_rate": round(_hits / _total, 4) if _total else None,
        }

    # ── Stage 6.97b — journey-level LOC (B3, $0, deterministic, additive) ─
    # Operator bug B3: ``user_flows[].loc`` was ``None`` for EVERY journey
    # (the engine never emitted a UF-level LOC), so the dashboard LOC column
    # was blank for all journeys. Stamp ``UserFlow.loc`` = the UNION of the
    # OWNED line-range spans across the UF's member flows (per-file merged;
    # role="interior" + shared_paths-ledger nodes excluded — mirrors the
    # validator's ``_spine_flow_loc_owned`` selection). Runs LAST — after
    # W5.1's member-less backstop appends, emission integrity, terminal
    # home, and naming — so EVERY surviving journey (including mc=0
    # placeholders → honest ``0``) is stamped from FINAL membership.
    # STRICTLY ADDITIVE: the only output-JSON change is the new
    # ``user_flows[].loc`` key (telemetry stays in the side artifact / log,
    # never scan_meta, so the flag-ON vs flag-OFF diff is exactly ``loc``).
    # Kill-switch WYSTAN_UF_LOC=0 → loc stays None → serializer omits it
    # → byte-identical to the pre-B3 engine. Metric must never break a scan.
    from wystan.pipeline_v2.stage_6_97b_uf_loc import (
        apply_uf_loc,
        uf_loc_enabled,
    )
    if uf_loc_enabled():
        with StageLogger(run_dir, 7, "uf_loc") as log_ufloc:
            try:
                _uf_loc_tele = apply_uf_loc(user_flows, list(bipartite.flows))
                log_ufloc.info(
                    "uf_loc: stamped %d journeys (%d with loc>0, %d zero)"
                    % (
                        _uf_loc_tele["user_flows_total"],
                        _uf_loc_tele["user_flows_with_loc"],
                        _uf_loc_tele["user_flows_zero_loc"],
                    ),
                    feature=None,
                )
                write_stage_artifact(
                    ctx.repo_path,
                    stage_index=7,
                    stage_name="uf_loc",
                    payload=_uf_loc_tele,
                    run_dir=run_dir,
                )
            except Exception as exc:  # noqa: BLE001 — metric must never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"uf-loc stage failed ({exc}); user_flows[].loc left unset"
                )
                log_ufloc.info(
                    f"uf_loc: FAILED ({exc}) — continuing without uf loc",
                    feature=None,
                )

    # ── Stage 6.97c — flow-level OWNED/SHARED LOC (B11, $0, additive) ─
    # Operator bug B11: distinct flows sharing one file rendered an IDENTICAL
    # file-grain LOC (the reactive-resume email trio all read "113"). Stamp
    # ``flows[].loc`` (owned-EXCLUSIVE span lines — the flow's unique story)
    # and ``flows[].loc_shared`` (owned span lines shared with ≥1 sibling flow
    # — blast-radius). By construction ``loc + loc_shared`` equals the flow's
    # ``_spine_flow_loc_owned`` union (the historical "113"), so it is a pure
    # DISPLAY partition: I13 loc-accounting is unmoved and I19's node-derived
    # owned numerator is untouched (additive fields; the node ledger is not
    # mutated). Runs right after 6.97b (UF loc) — spans are final. STRICTLY
    # ADDITIVE: the only output-JSON change is the two new keys (telemetry
    # lives in the side artifact / log, never scan_meta, so the flag-ON vs
    # flag-OFF diff is exactly ``loc``/``loc_shared``). Kill-switch
    # WYSTAN_FLOW_LOC=0 → both stay None → serializer omits → byte-identical
    # to the pre-B11 engine. Metric must never break a scan.
    from wystan.pipeline_v2.stage_6_97c_flow_loc import (
        apply_flow_loc,
        flow_loc_enabled,
    )
    if flow_loc_enabled():
        with StageLogger(run_dir, 7, "flow_loc") as log_flowloc:
            try:
                _flow_loc_tele = apply_flow_loc(list(bipartite.flows))
                log_flowloc.info(
                    "flow_loc: stamped %d flows (%d with shared span, %d "
                    "exclusive-only)" % (
                        _flow_loc_tele["flows_total"],
                        _flow_loc_tele["flows_with_shared"],
                        _flow_loc_tele["flows_exclusive_only"],
                    ),
                    feature=None,
                )
                write_stage_artifact(
                    ctx.repo_path,
                    stage_index=7,
                    stage_name="flow_loc",
                    payload=_flow_loc_tele,
                    run_dir=run_dir,
                )
            except Exception as exc:  # noqa: BLE001 — metric must never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"flow-loc stage failed ({exc}); flows[].loc left unset"
                )
                log_flowloc.info(
                    f"flow_loc: FAILED ({exc}) — continuing without flow loc",
                    feature=None,
                )

    # ── Stage 6.97e — PF-level OWNED-LOC rollup backstop ($0, additive) ──
    # Trust-bug (LOC doctrine 2026-07-16): a member-ful PF renders a bare
    # ``loc = 0`` (RefApp ``findings`` holds api-detectors/api-findings/api-mitre
    # yet shows 0). The 6.97 rollup runs ONCE; the late api-stub/api-container/
    # fold demotes then zero a demoted dev's ``loc`` scalar while leaving its
    # ``path_index`` ownership intact, dragging the PF scalar to 0. This
    # backstop recomputes ``loc`` for FALSY-``loc`` PFs ONLY, from the
    # authoritative one-owner-per-file ``path_index`` (owner dev's PF ⇒ owned
    # LOC), so the backend-router 3564 LOC api-detectors still owns is restored.
    # Runs in the final-membership window (after the demote/rehome surgery, with
    # the refreshed path_index). STRICTLY ADDITIVE: a PF with ``loc > 0`` is
    # never entered ⇒ byte-identical; only hollow rows move, only upward.
    # Kill-switch: WYSTAN_PF_LOC_ROLLUP_FIX unset/0 (the DEFAULT — OFF) skips
    # the stage ⇒ byte-identical to the pre-stage engine. Never breaks a scan.
    from wystan.pipeline_v2.stage_6_97e_pf_loc import (
        apply_pf_loc_backstop,
        pf_loc_rollup_fix_enabled,
    )
    if pf_loc_rollup_fix_enabled():
        with StageLogger(run_dir, 7, "pf_loc_rollup") as log_pfloc:
            try:
                _pf_loc_tele = apply_pf_loc_backstop(
                    product_features,
                    features,
                    lineage_result.path_index,
                )
                # Telemetry lives in the side artifact + log ONLY (never
                # scan_meta) so the flag-ON vs flag-OFF output diff is exactly
                # the recomputed PF ``loc`` — the uf_loc/flow_loc convention.
                log_pfloc.info(
                    "pf_loc_rollup: %d/%d hollow PFs recomputed (%d LOC "
                    "restored)" % (
                        _pf_loc_tele["pfs_recomputed"],
                        _pf_loc_tele["pfs_hollow"],
                        _pf_loc_tele["loc_restored"],
                    ),
                    feature=None,
                )
                write_stage_artifact(
                    ctx.repo_path,
                    stage_index=7,
                    stage_name="pf_loc_rollup",
                    payload=_pf_loc_tele,
                    run_dir=run_dir,
                )
            except Exception as exc:  # noqa: BLE001 — metric must never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"pf-loc-rollup stage failed ({exc}); PF loc left unset"
                )
                log_pfloc.info(
                    f"pf_loc_rollup: FAILED ({exc}) — continuing without fix",
                    feature=None,
                )

    # ── Stage 6.97d — journey-level engineering metrics ($0, additive) ──
    # Operator gap: PFs carry health/bug-fix/churn/authors, journeys carry
    # only loc + coverage_pct. Stamp the MIRROR metric family
    # (total_commits/bug_fixes/bug_fix_ratio/authors/health_score/
    # health_confidence + the honest "span-weighted" health_basis label)
    # on every eligible UserFlow via PROPORTIONAL SPAN-CREDIT: each
    # member-flow-owned file contributes its commit history × the
    # journey's ownership share (owned lines / file total lines) — the
    # $0-prototype-proven cure for whole-file mega-churn credit (RefApp:
    # subset violations 34→13, shared-infra top-credit 28→3 of 81).
    # Runs right after 6.97c (same final-membership window as uf_loc,
    # BEFORE terminal classification / emission); churn comes from the
    # pre-loaded ctx.commits (one sweep, no git subprocess; one disk
    # read per distinct file). STRICTLY ADDITIVE: the only output-JSON
    # change is the new user_flows[] metric keys (telemetry stays in the
    # side artifact / log, never scan_meta). Kill-switch: unset/0 (the
    # DEFAULT — flag is OFF) → fields stay None → serializer omits →
    # byte-identical to the pre-stage engine. Metric must never break a
    # scan.
    from wystan.pipeline_v2.stage_6_97d_uf_metrics import (
        apply_uf_metrics,
        uf_metrics_enabled,
    )
    if uf_metrics_enabled():
        with StageLogger(run_dir, 7, "uf_metrics") as log_ufm:
            try:
                _ufm_tele = apply_uf_metrics(
                    user_flows,
                    list(bipartite.flows),
                    ctx.commits,
                    ctx.repo_path,
                )
                log_ufm.info(
                    "uf_metrics: stamped %d journeys (%d with credit, "
                    "%d zero-credit; skipped %d markers / %d memberless / "
                    "%d span-less; %d files line-counted, %d ms)" % (
                        _ufm_tele["stamped"],
                        _ufm_tele["stamped_nonzero"],
                        _ufm_tele["zero_credit_rows"],
                        _ufm_tele["skipped_markers"],
                        _ufm_tele["skipped_memberless"],
                        _ufm_tele["skipped_no_spans"],
                        _ufm_tele["files_line_counted"],
                        _ufm_tele["duration_ms"],
                    ),
                    feature=None,
                )
                write_stage_artifact(
                    ctx.repo_path,
                    stage_index=7,
                    stage_name="uf_metrics",
                    payload=_ufm_tele,
                    run_dir=run_dir,
                )
            except Exception as exc:  # noqa: BLE001 — metric must never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"uf-metrics stage failed ({exc}); user_flows[] metric "
                    "fields left unset"
                )
                log_ufm.info(
                    f"uf_metrics: FAILED ({exc}) — continuing without "
                    "journey metrics",
                    feature=None,
                )

    # ── B30 — deterministic verb+resource flow naming (name channel) ──
    # Runs LAST (after 6.97c flow-loc, immediately before Stage 7) so
    # every consumer of the old names — UF rollup, lattice, lineage,
    # dedup, ids — already ran: the only output change is
    # ``flows[].name`` + its ``display_name``/``short_label`` kebab
    # mirrors. ``flow.id``/``uuid`` (the join keys) are never touched;
    # the Flow objects are shared with ``developer_features[].flows[]``
    # so one in-place mutation updates both views. Kill-switch
    # WYSTAN_FLOW_NAME_V2=0 skips the stage → byte-identical output.
    # Telemetry lives in the side artifact/log only (never scan_meta),
    # mirroring the 6.97c precedent, so the flag ON/OFF diff is exactly
    # the name fields.
    from wystan.pipeline_v2.flow_name_v2 import (
        apply_flow_name_v2,
        flow_name_v2_enabled,
    )
    # ── fixb106/R0 — snapshot BEFORE the rename seam ─────────────────
    # Law C (``run_naming_contract`` above) grades every UF row against its
    # MEMBER FLOW NAMES; ``flow_name_v2`` is the stage whose whole job is to
    # mint the verb-led names Law C was looking for — 1500 lines too late.
    # ``flows=`` arms the member-name diff channel so the rows whose member
    # names THIS seam rewrites (and only those) get re-graded below.
    _fnv2_before = snapshot_uf_state(user_flows, flows=list(bipartite.flows))
    if flow_name_v2_enabled():
        with StageLogger(run_dir, 7, "flow_name_v2") as log_fnv2:
            try:
                _fnv2_tele = apply_flow_name_v2(
                    list(bipartite.flows),
                    routes_index=lineage_result.routes_index,
                    repo_path=ctx.repo_path,
                )
                log_fnv2.info(
                    "flow_name_v2: renamed %d/%d flows (route=%d symbol=%d "
                    "honest-fallback=%d feature-qualified=%d ordinal=%d)" % (
                        _fnv2_tele["renamed_total"],
                        _fnv2_tele["flows_total"],
                        _fnv2_tele["renamed_route"],
                        _fnv2_tele["renamed_symbol"],
                        _fnv2_tele["kept_honest_fallback"],
                        _fnv2_tele["collision_feature_qualified"],
                        _fnv2_tele["collision_ordinal"],
                    ),
                    feature=None,
                )
                write_stage_artifact(
                    ctx.repo_path,
                    stage_index=7,
                    stage_name="flow_name_v2",
                    payload=_fnv2_tele,
                    run_dir=run_dir,
                )
            except Exception as exc:  # noqa: BLE001 — naming must never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"flow-name-v2 stage failed ({exc}); flow names left as-is"
                )
                log_fnv2.info(
                    f"flow_name_v2: FAILED ({exc}) — continuing with old names",
                    feature=None,
                )

    # ── B92 Rung D — PF-namespace flow-name de-collision ───────────────
    # Extends the (PF-blind) flow_name_v2 collision ladder: de-collides ALL
    # flows sharing a product_feature_id (incl. two HONEST LLM names the
    # ladder only reserves, never compares) by a deterministic entry-component
    # qualifier. Runs AFTER flow_name_v2 (de-collides the FINAL names) so the
    # PF view carries no pair of homonym flows — the operator exhibit
    # ``refapp-filter-inventory-twin-flow``. Heals all 29 one-PF collision
    # groups incl. the 21 disjoint facets Rung B must not touch. Mutates only
    # flows[].name/display_name/short_label (never id/uuid). Kill-switch
    # WYSTAN_TWIN_FLOW_DECOLLIDE (default OFF) → unset/=0 byte-identical.
    from wystan.pipeline_v2.twin_collision import (
        apply_flow_pf_decollide,
        twin_flow_decollide_enabled,
    )
    _twin_armed = twin_flow_decollide_enabled() or twin_feature_merge_enabled()
    if twin_flow_decollide_enabled():
        with StageLogger(run_dir, 7, "twin_flow_decollide") as log_tfd:
            try:
                _tfd_tele = apply_flow_pf_decollide(
                    features, list(bipartite.flows),
                )
                if _tfd_tele.get("decollided_total"):
                    scan_meta["twin_flow_decollide"] = _tfd_tele
                log_tfd.info(
                    "twin_flow_decollide: de-collided %d flows across %d "
                    "collision groups (entry-qualified=%d ordinal=%d)" % (
                        _tfd_tele["decollided_total"],
                        _tfd_tele["collision_groups"],
                        _tfd_tele["decollided_entry_qualified"],
                        _tfd_tele["decollided_ordinal"],
                    ),
                    feature=None,
                )
                write_stage_artifact(
                    ctx.repo_path,
                    stage_index=7,
                    stage_name="twin_flow_decollide",
                    payload=_tfd_tele,
                    run_dir=run_dir,
                )
            except Exception as exc:  # noqa: BLE001 — naming must never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"twin-flow-decollide failed ({exc}); flow names left as-is"
                )
                log_tfd.info(
                    f"twin_flow_decollide: FAILED ({exc}) — names left as-is",
                    feature=None,
                )

    # ── fixb106/R0 — post-rename Law C regrade (WYSTAN_UF_POSTMINT_RESCORE)
    # The 4th B100 hook, on the LAST producer of member flow names: one
    # rescore covers BOTH renamers above (flow_name_v2 + the B92 de-collide),
    # so a row is graded once, against the names Stage 7 will actually emit.
    # Row-scoped as always — only rows whose member names this seam rewrote;
    # every other row leaves the hook verbatim. Bidirectional by
    # construction: a ``high`` standing on names that no longer exist falls
    # to ``medium`` (P4 measured 61 up / 8 honest down on the KS54 world).
    # Flag OFF ⇒ the snapshot is None ⇒ no call, no scan_meta key,
    # byte-identical.
    try:
        postmint_uf_rescore(
            "flow_name_v2", user_flows, _fnv2_before,
            product_features=product_features,
            flows=list(bipartite.flows),
            product_strings=product_strings,
            routes_index=lineage_result.routes_index,
            uf_authored_names=_e2e_authored_names,
            keeper_on=keeper_enabled(),
            repo_root=ctx.repo_path,
            scan_meta=scan_meta,
        )
    except Exception as exc:  # noqa: BLE001 — rescore must never break a scan
        scan_meta.setdefault("warnings", []).append(
            f"postmint-rescore (flow_name_v2) failed ({exc}); grades kept"
        )

    # B89 sentinel — the twin-collision class (a PF still holding same-named
    # flows) at the flow-name seam. Own registry key; fired ONLY when a B92
    # arm is armed → default world byte-identical (B82/B91 own-key precedent).
    if _twin_armed:
        invariant_hooks.run_stage(
            scan_meta, "twin_collision",
            features=features, flows=list(bipartite.flows),
        )

    # ── Stage 6.9945 — B111 dissolved-dev journey conservation ─────────
    # A developer feature whose own PF tile the 6.86 mint DISSOLVED
    # (``anchor_id`` provenance ``fold:*``) and whose flows then failed the
    # coherence ruler leaves NO trace anywhere today: ``fold_coherence``
    # heals orphan JOURNEYS and there is no journey to orphan — the fold
    # happens at 6.86, ABOVE the whole 6.7 journey layer, so the row is
    # never minted rather than dropped (the ruling's option (a), "move
    # fold_coherence above the dissolution", has no journey to move above).
    # demote_map / merge_map are silent by construction: no demoter ran.
    #
    # Slot: the LAST read-only checkpoint before the B68 ladder — the
    # journey layer, membership and backpointers are final here (no
    # ``user_flow_id`` writer runs below), so the cohort ruler judges the
    # exact homes Stage 7 will emit. Pure read: no flow / UF / PF is
    # mutated; the rows join the B45 channel in the post-ladder union
    # below, beside the B78-it2 orphan rows and for the identical reason
    # (their files are LIVE flow ground by construction, so the ladder's
    # ``live_flow_owner`` rung would classify-and-dissolve exactly the
    # admission the stamp exists to make).
    # Flag OFF ⇒ the builder returns before any read ⇒ no rows, no
    # scan_meta key, no hook record — byte-identical (KS 4-way).
    from wystan.pipeline_v2.conservation import (
        build_dissolved_dev_gaps,
        fold_conservation_enabled,
    )
    _dissolved_gap_rows: list[Any] = []
    if fold_conservation_enabled():
        with StageLogger(run_dir, 6, "fold_conservation") as log_fcons:
            try:
                _dissolved_gap_rows, _fcons_tele = build_dissolved_dev_gaps(
                    user_flows, features, product_features,
                )
                scan_meta["fold_conservation"] = _fcons_tele
                invariant_hooks.run_stage(
                    scan_meta, "6.9945_fold_conservation",
                    fold_conservation_tele=_fcons_tele,
                )
                log_fcons.info(
                    "fold_conservation: cohorts=%d flows=%d coherent=%d"
                    " no_spans=%d" % (
                        _fcons_tele.get("cohorts", 0),
                        _fcons_tele.get("flows", 0),
                        _fcons_tele.get("coherent", 0),
                        _fcons_tele.get("skipped_no_spans", 0),
                    ),
                    feature=None,
                )
            except Exception as exc:  # noqa: BLE001 — never break a scan
                _dissolved_gap_rows = []
                scan_meta.setdefault("warnings", []).append(
                    f"fold-conservation failed ({exc}); no gap rows stamped"
                )

    # ── Stage 6.995 — B68 terminal 4-way classification ────────────
    # Operator doctrine 2026-07-14: the gap channel is an INTERNAL state,
    # never a final board category. Runs LAST — after every gap producer
    # (B45 emit + 6.7e adjudicated merge) and every board mutation — so
    # it judges the exact rows Stage 7 would emit. Mutates ONLY
    # coverage_gaps[] (+ the scan_meta audit trace); ownership channels
    # (path_index / features / user_flows) are read-only inputs.
    # Kill-switch WYSTAN_TERMINAL_CLASSIFICATION (default OFF) —
    # unset/=0 never runs the pass (byte-identity with main).
    from wystan.pipeline_v2.terminal_classification import (
        run_terminal_classification,
        terminal_classification_enabled,
    )
    if terminal_classification_enabled() and coverage_gaps is not None:
        try:
            _tc_tele = run_terminal_classification(
                coverage_gaps,
                product_features,
                features,
                scan_meta,
                dev_artifact_units=dev_artifact_units,
                instrument_dirs=instrument_dirs,
                repo_path=repo_path,
                # B-v2 loc_worthy file-owner rescue: routes ride as the
                # CORROBORATION channel only (file-owner wins). Unused
                # unless WYSTAN_ROUTE_JOURNEY_BACKSTOP is armed.
                routes_index=lineage_result.routes_index,
            )
            write_stage_artifact(
                ctx.repo_path,
                stage_index=7,
                stage_name="terminal_classification",
                payload=_tc_tele,
                run_dir=run_dir,
            )
        except Exception as exc:  # noqa: BLE001 — never break a scan
            scan_meta.setdefault("warnings", []).append(
                f"terminal-classification stage failed ({exc}); "
                f"coverage_gaps left as-is"
            )

    # ── B78-it2 Goal 1 (Seg B rider) — orphan-flow gap rows join the
    # typed channel HERE, after the B68 ladder: they are Seg-B-typed
    # journey-debt claims over LIVE flow-owned files — the ladder's
    # ``live_flow_owner`` rehome rung would classify-and-dissolve them,
    # which is exactly the silence the stamp exists to break. Channel-
    # presence law respected: appended ONLY when the B45 channel is
    # active (``coverage_gaps is not None``); the union re-sorts with the
    # channel's own ``(pf, id)`` key — deterministic. Flag OFF ⇒ the rows
    # list is empty ⇒ this block is inert (byte-identity with main).
    # B111 rides the SAME union for the same reason (see the 6.9945 seam):
    # a dissolved dev's unclaimed flows are live flow ground, so the
    # ladder's ``live_flow_owner`` rung would dissolve the admission.
    if (_orphan_gap_rows or _dissolved_gap_rows) and coverage_gaps is not None:
        coverage_gaps = (list(coverage_gaps) + list(_orphan_gap_rows)
                         + list(_dissolved_gap_rows))
        coverage_gaps.sort(key=lambda g: (
            str(getattr(g, "product_feature_id", "") or ""),
            str(getattr(g, "id", "") or ""),
        ))

    # B112 sentinel — the demote-law bijection at the TERMINAL gap seam:
    # every ``demote_map[].gap_id`` the 6.7e adjudicator claimed must be
    # carried by an emitted gap. Fired here because this is the last line
    # at which ``coverage_gaps`` changes. Own registry key; fired ONLY when
    # the emission fix is armed AND the adjudicator produced a demote map →
    # default world byte-identical (the B91 own-key precedent).
    from wystan.pipeline_v2.stage_6_7e_adjudicator import (
        demote_gap_emission_enabled,
    )
    if demote_gap_emission_enabled():
        _demote_map = list(
            (scan_meta.get("adjudicator_6_7e") or {}).get("demote_map") or [])
        if _demote_map:
            invariant_hooks.run_stage(
                scan_meta, "6.995_demote_gap_emission",
                demote_map=_demote_map,
                coverage_gaps=list(coverage_gaps or []),
            )

    # ── Stage 6.996 — B78 Seg F plumbing-UF reclassification ───────────
    # A UF whose NAME reads as a data-access/infra helper (plumbing verb +
    # tech-object, closed YAML vocab), whose profile is micro (member_count
    # <=2), and which carries NO product surface (routeless + no member
    # PAGE) is DEV-GRAIN plumbing, not a user journey: it reclassifies to
    # category="system" (+ surface_scope="system"). No rung upstream reads
    # the shape of a UF (6.987 is PF-grain, 6.8b reads route triggers, B40
    # is a confidence stamp). Runs AFTER Stage 7 naming_contract / flow-name
    # (names frozen — no rename triggered) and after B68 terminal
    # classification, the sibling "demote must reclassify" channel. Membership
    # is READ-ONLY (only category+scope flip; conservation by construction).
    # Deterministic, $0 LLM. Kill-switch WYSTAN_PLUMBING_UF_RECLASS
    # (default ON since flip-pack №4, KEY_SCHEMA 36) — explicit =0 never runs
    # (byte-identity with pre-Seg-F).
    from wystan.pipeline_v2.plumbing_uf_reclass import (
        plumbing_uf_reclass_enabled,
        run_plumbing_uf_reclass,
    )
    if plumbing_uf_reclass_enabled():
        with StageLogger(run_dir, 6, "plumbing_uf_reclass") as log_pur:
            try:
                _flows_by_id: dict[str, Any] = {}
                for _fl in bipartite.flows:
                    for _k in (getattr(_fl, "uuid", None),
                               getattr(_fl, "name", None)):
                        if _k:
                            _flows_by_id.setdefault(str(_k), _fl)
                _page_ri = {
                    str(e.get("file") or "")
                    for e in (lineage_result.routes_index or [])
                    if isinstance(e, dict)
                    and str(e.get("method") or "").upper() == "PAGE"
                    and e.get("file")
                }
                pur_tele = run_plumbing_uf_reclass(
                    user_flows, _flows_by_id, _page_ri)
                scan_meta["plumbing_uf_reclass"] = pur_tele
                log_pur.info(
                    "plumbing_uf_reclass: candidates=%d reclassified=%d "
                    "abstained=%d" % (
                        pur_tele.get("candidates", 0),
                        len(pur_tele.get("reclassified", [])),
                        len(pur_tele.get("abstained", [])),
                    ),
                    feature=None,
                )
            except Exception as exc:  # noqa: BLE001 — never break a scan
                scan_meta.setdefault("warnings", []).append(
                    f"plumbing-uf reclass failed ({exc}); UFs left untouched"
                )
                log_pur.info(
                    f"plumbing_uf_reclass: FAILED ({exc}) — continuing",
                    feature=None,
                )

    # ── S3 arbiter — single application point (before Stage 7 output) ──
    # Every product_feature_id proposal for this scan has now been recorded
    # by the observer. Run the arbiter ONCE: its rung-priority replay ==
    # the current pass order, so it reproduces the cascade byte-for-byte
    # (record order == execution order → last-writer-wins), and it emits
    # the overturn census + the post-freeze conflict census into scan_meta
    # (both keys are stripped by normalize_scan — run-forensics, never
    # content). No-op unless WYSTAN_OVERTURN_ARBITER=1.
    _overturn_ledger = getattr(ctx, "overturn_ledger", None)
    if _overturn_ledger is not None:
        from wystan.pipeline_v2.overturn_ledger import finalize_arbiter
        try:
            finalize_arbiter(
                _overturn_ledger, features, user_flows, scan_meta,
                product_features,
            )
        except Exception as exc:  # noqa: BLE001 — telemetry never breaks a scan
            scan_meta.setdefault("warnings", []).append(
                f"overturn-arbiter failed ({exc}); census skipped"
            )

    # ── B78 Seg G — nav-parent display grouping (WYSTAN_NAV_PARENT,
    # default OFF) ──────────────────────────────────────────────────────
    # Reads the repo's static exported nav registries and stamps a
    # display-only ``product_features[].nav_parent`` on PFs whose anchor
    # route (or enum-referenced nav slug) matches a nav SUB-item, plus the
    # ``scan_meta.nav_tree`` telemetry. Seam rationale: the LAST finalize
    # pass — AFTER the naming contract (parent labels judge against FINAL
    # display names) and every structural writer (homing / rehome / splits),
    # so the settled PF list + routes_index are read once, purely for
    # display. NO structure writes: PFs are never merged, moved, or minted
    # (engineering grain untouched); a live nav category with no PF is
    # reported in nav_tree.unrepresented, never minted. Flag OFF/unset OR a
    # nav-less repo ⇒ run_nav_parent returns None before any mutation ⇒ no
    # nav_parent field, no scan_meta key ⇒ byte-identical (KS 4-way gate).
    try:
        from wystan.pipeline_v2.nav_parent import run_nav_parent
        _nav_tele = run_nav_parent(
            product_features, lineage_result.routes_index, ctx, user_flows)
        if _nav_tele is not None:
            scan_meta["nav_tree"] = _nav_tele
    except Exception as exc:  # noqa: BLE001 — display grouping never breaks a scan
        scan_meta.setdefault("warnings", []).append(
            f"nav-parent failed ({exc}); nav_parent unset"
        )

    # ── B93 — nav section-landing demote (WYSTAN_NAV_CATEGORY_DEMOTE,
    # default ON since flip-pack №9) ─────────────────────────────────────
    # Consumes the nav_parent field just stamped above: a nav-child PF that is
    # a section OVERVIEW/landing shell (non-self-ref, 0 real journeys, every
    # anchor file under a section-index segment — RefApp 'Feature Studio') is
    # demoted from the peer-feature tile so it stops masquerading as a feature
    # (operator exhibit refapp-feature-studio-nav-child). Member devs re-home
    # (ancestor → L1/unowned, files kept); held shell-UFs drop — conservation
    # by construction. Runs AFTER run_nav_parent (needs the field) and BEFORE
    # the product-right census + emission so the census/metrics see the
    # demoted state. Default ON (unset ≡ armed); explicit OFF (0/false/off/no)
    # ⇒ None before any mutation, no scan_meta key ⇒ byte-identical
    # (kill-switch).
    try:
        from wystan.pipeline_v2.nav_parent import run_nav_category_demote
        _navdem_tele = run_nav_category_demote(
            product_features, features, user_flows)
        if _navdem_tele is not None:
            scan_meta["nav_category_demote"] = _navdem_tele
    except Exception as exc:  # noqa: BLE001 — demote never breaks a scan
        scan_meta.setdefault("warnings", []).append(
            f"nav-category demote failed ({exc}); no demote"
        )

    # ── B94 — settings-frame demote (WYSTAN_SETTINGS_FRAME_DEMOTE,
    # default ON since flip-pack №9) ─────────────────────────────────────
    # A top-level PF named after a generic settings-frame TAB (general /
    # settings / preferences / advanced / misc) that carries 0-1 real journeys
    # and whose EVERY anchor file sits under a settings-context ancestor
    # (settings/account/preferences/admin — 'General' on cal/papermark/plane/
    # rallly) is a contentless settings container, not a feature (operator
    # exhibit settings-general-container). It is demoted from the peer-feature
    # tile; member devs re-home (route ancestor → L1/unowned, files kept); a
    # real held journey re-homes to that ancestor, synthesized shell-UFs drop —
    # conservation by construction. Discriminator is STRUCTURAL (frame-word +
    # low-journey + settings-home), NOT the bare name: a 'general' code FOLDER
    # not under a settings ancestor (documenso components/general/, D3 blob) is
    # left untouched. Runs AFTER the nav passes and BEFORE the product-right
    # census + emission so the census/metrics see the demoted state. Default ON
    # (unset ≡ armed); explicit OFF (0/false/off/no) ⇒ None before any mutation,
    # no scan_meta key ⇒ byte-identical.
    try:
        from wystan.pipeline_v2.settings_frame_demote import (
            run_settings_frame_demote,
        )
        _sfd_tele = run_settings_frame_demote(
            product_features, features, user_flows)
        if _sfd_tele is not None:
            scan_meta["settings_frame_demote"] = _sfd_tele
    except Exception as exc:  # noqa: BLE001 — demote never breaks a scan
        scan_meta.setdefault("warnings", []).append(
            f"settings-frame demote failed ({exc}); no demote"
        )

    # ── B95 — capability SHARED-re-home (WYSTAN_CAPABILITY_SHARED_REHOME,
    # default ON since flip-pack №9) ───────────────────────────────────────
    # A top-level PF for a shared MECHANISM (human-verify / file upload / search
    # / notification — 'Captcha' / 'File Upload' on twenty) with 0-low own
    # journeys, a thin member set, no own product-surface (no nav entry), a
    # route:/fdir: (non-ws:, non-SDK) anchor and low cross-feature fan-in is a
    # capability, not a feature (operator exhibit twenty-capability-as-pf, canon
    # class 'Capability'). It is demoted from the peer-feature tile; its flows
    # become type=secondary members of consumer features' journeys via
    # feature_flow_edges, its member devs stay in developer_features as honest
    # residual (product_feature_id=None, files kept) — conservation by
    # construction. Discriminator is PRODUCT-RELATIVE + STRUCTURAL, NOT the bare
    # mechanism name (a mechanism that IS the product — ente file/photo storage
    # — carries real journeys + an own nav surface and survives). Runs AFTER the
    # nav + settings-frame passes and BEFORE the product-right census + emission
    # so the census/metrics see the demoted state. Default ON (unset ≡ armed);
    # explicit OFF (0/false/off/no) ⇒ None before any mutation, no scan_meta key
    # ⇒ byte-identical (kill-switch).
    try:
        from wystan.pipeline_v2.capability_shared_rehome import (
            run_capability_shared_rehome,
        )
        _csr_tele = run_capability_shared_rehome(
            product_features, features, user_flows,
            bipartite.flows, bipartite.edges)
        if _csr_tele is not None:
            scan_meta["capability_shared_rehome"] = _csr_tele
    except Exception as exc:  # noqa: BLE001 — demote never breaks a scan
        scan_meta.setdefault("warnings", []).append(
            f"capability shared-re-home failed ({exc}); no demote"
        )

    # ── #3A — orphan-UF path-attach (WYSTAN_ORPHAN_UF_PATH_ATTACH,
    # default OFF, armed-only) — BEFORE B96: attach-first-then-demote ────
    # None-born real journeys (6.7d with no domain match; hoppscotch ×29,
    # the Common legacy) attach to a PF by strong (≥60%) path ownership of
    # their member flows; weak/zero ones stay honest orphans. A journey
    # that finds a home saves its PF from reading as 0-UF below.
    try:
        from wystan.pipeline_v2.orphan_uf_path_attach import (
            run_orphan_uf_path_attach,
        )
        _oup_tele = run_orphan_uf_path_attach(
            product_features, features, user_flows, list(bipartite.flows))
        if _oup_tele is not None:
            scan_meta["orphan_uf_path_attach"] = _oup_tele
    except Exception as exc:  # noqa: BLE001 — attach never breaks a scan
        scan_meta.setdefault("warnings", []).append(
            f"orphan-uf path-attach failed ({exc}); orphans left"
        )

    # ── #4 — Tier-2 journey re-parent (WYSTAN_TIER2_JOURNEY_REPARENT,
    # default OFF, armed-only) — AFTER the 3A attach, BEFORE B96:
    # attach → reparent → demote. A journey of a techno-named PF with
    # strictly foreign (≥80% one other PF) entry ownership moves to its real
    # home (teable base→share exhibit); the emptied techno PF is B96-demoted.
    try:
        from wystan.pipeline_v2.tier2_journey_reparent import (
            run_tier2_journey_reparent,
        )
        _t2r_tele = run_tier2_journey_reparent(
            product_features, features, user_flows, list(bipartite.flows))
        if _t2r_tele is not None:
            scan_meta["tier2_journey_reparent"] = _t2r_tele
    except Exception as exc:  # noqa: BLE001 — reparent never breaks a scan
        scan_meta.setdefault("warnings", []).append(
            f"tier2 journey re-parent failed ({exc}); journeys left"
        )

    # ── B96 — technical-husk PF demote (WYSTAN_GENERIC_CONTAINER_DEMOTE,
    # default OFF, armed-only) ─────────────────────────────────────────────
    # A top-level PF with a transport/generic-container/dev-construct name
    # (structural_stoplist ∪ transport_protocol_tokens, FULL normalized
    # identity) holding ZERO real journeys is a technical husk, not a product
    # capability (operator exhibits: hoppscotch ``http``/``graphql``/
    # ``realtime``/``mockserver`` — container-rehome mints every sibling gate
    # is anchor-kind-blind to; strapi/directus anchor-less ``core``/``app``).
    # Widest anchor scope of the demote family (any kind incl. absent);
    # journey-holding technical names survive (supabase ``realtime`` uf=4).
    # Board-abstain on UF-starved boards (keyless guard). Runs in the "last
    # word" slot — after every UF-homing mechanism, before the product-right
    # census + emission so the census/metrics see the demoted state. OFF /
    # unset ⇒ None before any mutation, no scan_meta key ⇒ byte-identical.
    try:
        from wystan.pipeline_v2.generic_container_demote import (
            run_generic_container_demote,
        )
        _gcd_slug = __import__("os").path.basename(
            str(getattr(ctx, "repo_path", "") or "").rstrip("/"))
        _gcd_tele = run_generic_container_demote(
            product_features, features, user_flows, scan_meta,
            extra_husk_tokens=frozenset({_gcd_slug} if _gcd_slug else ()))
        if _gcd_tele is not None:
            scan_meta["generic_container_demote"] = _gcd_tele
    except Exception as exc:  # noqa: BLE001 — demote never breaks a scan
        scan_meta.setdefault("warnings", []).append(
            f"generic-container demote failed ({exc}); no demote"
        )

    # ── B97 — emission HARD gate (WYSTAN_EMISSION_HARD_GATE, default
    # OFF, armed-only) — the LAST barrier before census + Stage 7 ─────────
    # Operator mandate 2026-08-02: a trust-law violation physically cannot
    # leave the engine, regardless of which upstream stage regressed. E1
    # LOC-real (recompute → repair, else demote/keep+name), E2 zero-member
    # shells, E3a paren-route tail strip (rename propagates to dev/UF join
    # keys), E3b route-param monster names. The gate NEVER orphans a real
    # journey — journey-holding violations are kept and loudly named in
    # telemetry. Runs after EVERYTHING (post-B96) so no later mint/rename
    # can bypass it. OFF / unset ⇒ None, no scan_meta key ⇒ byte-identical.
    try:
        from wystan.pipeline_v2.emission_hard_gate import (
            run_emission_hard_gate,
        )
        _ehg_tele = run_emission_hard_gate(
            product_features, features, user_flows)
        if _ehg_tele is not None:
            scan_meta["emission_hard_gate"] = _ehg_tele
    except Exception as exc:  # noqa: BLE001 — the gate never breaks a scan
        scan_meta.setdefault("warnings", []).append(
            f"emission hard gate failed ({exc}); gate skipped"
        )

    # ── fixb134 M4b — PF slug-migration lane (WYSTAN_PF_SLUG_SANITIZE) ─
    # fixb133 cleaned the DISPLAY channel and left pf.name alone, so router
    # machinery still lives in the JOIN ID ('(.)sessions', 'alby-(alby)',
    # 'robots[.]txt'). Migrates them here — after the hard gate, so it sees
    # the FINAL names incl. E3a's renames, and at EMISSION rather than in
    # naming_contract (the fixb133 slug-stable law forbids that channel).
    # Every rename re-stamps dev/UF product_feature_id in the SAME pass
    # (the E3a law; the compactor's propagation-less re-slug is the known
    # landmine). anchor_id and display_name are untouched.
    # OFF / unset ⇒ None, no scan_meta key ⇒ byte-identical.
    try:
        from wystan.pipeline_v2.pf_slug_sanitize import (
            run_pf_slug_sanitize,
        )
        # ``flows`` is NOT passed: the bipartite top-level array holds the
        # SAME Flow objects as ``features[].flows[]`` (shared by reference),
        # and that containment view is exactly where flow_span_split writes
        # the shared_paths ledger — so walking the holders covers every
        # object once. ``coverage_gaps`` IS a distinct row set and must be
        # handed over explicitly (bound unconditionally at :3697).
        _pss_tele = run_pf_slug_sanitize(
            product_features, features, user_flows,
            coverage_gaps=coverage_gaps)
        if _pss_tele is not None:
            scan_meta["pf_slug_sanitize"] = _pss_tele
    except Exception as exc:  # noqa: BLE001 — never breaks a scan
        scan_meta.setdefault("warnings", []).append(
            f"pf slug sanitize failed ({exc}); lane skipped"
        )

    # ── fixb135 — owner-ledger reconciliation (the SECOND split-brain
    # producer). flow_span_split writes the per-file ownership ledger
    # mid-pipeline; later renames/demotes (stage_6_86:1201,
    # ws_blob_domain_drain:1090, transport_handoff:1658, 6.9966:921 + the
    # collision ladders) leave it stale. Runs LAST — after the slug
    # migration, so it re-resolves against FINAL names — and rebuilds the
    # file→owner map with flow_span_split's own semantics. Writes ONLY
    # owner_product_feature / owner_display. OFF / unset ⇒ None, no
    # scan_meta key ⇒ byte-identical.
    #
    # fixb141 (KEY_SCHEMA 76) — ``flows`` IS passed. The pass shipped in
    # pack №38 with the argument omitted, on the premise (stated in the
    # pf_slug_sanitize comment above) that the bipartite top-level array is
    # a pure alias of the containment views. The census disproved it: the
    # array is a SUPERSET — flows detached from every holder live only
    # there (documenso 212, growthbook 242, twenty 239, hoppscotch 188,
    # hydrogen 43) and 47 dead owner keys world-wide sat behind them,
    # permanently invisible to the reconcile. ``_iter_flows`` already
    # accepts and de-duplicates this argument on ``id()``, so the shared
    # objects are still visited exactly once — this restores the
    # mechanism's own claimed coverage, it does not add behaviour. Same
    # kill-switch, no new flag.
    try:
        from wystan.pipeline_v2.owner_ledger_reconcile import (
            run_owner_ledger_reconcile,
        )
        _olr_tele = run_owner_ledger_reconcile(
            product_features, features, list(bipartite.flows))
        if _olr_tele is not None:
            scan_meta["owner_ledger_reconcile"] = _olr_tele
    except Exception as exc:  # noqa: BLE001 — never breaks a scan
        scan_meta.setdefault("warnings", []).append(
            f"owner ledger reconcile failed ({exc}); ledger left as-is"
        )

    # ── fixb103 — terminal detachment accounting (Stage 6.9971) ─────────
    # Every PF-killer that runs AFTER the lane build (phase_finalize:3600)
    # and after emission_integrity's I12 pass (:3096) leaves dependents
    # without a terminal state: container_journey_rehome's demote
    # (devs_unowned=9 on infisical ON) and the hard gate's own E1 demote
    # (devs_unowned=1, e1_demoted=['steps']) both COUNT their casualties
    # but cannot lane them — the lane was built ~1600 lines earlier. Result
    # on the fresh keyed ON hand: UF-208 'Connect steps' holds a dangling
    # pfid 'steps' (I12) and unaccounted residents run 3 (OFF) -> 11 (ON),
    # the two demoted PF names among them (I22). This pass gives them the
    # B58-v5 terminal rung — re-match-else-null the reference, lane the
    # resident with a named shared_reason, report (never move) a homeless
    # journey — and re-runs the idempotent I14 backpointer derivation last.
    # Placed after the hard gate so NOTHING can demote behind its back.
    # OFF / unset ⇒ None, no scan_meta key ⇒ byte-identical.
    try:
        from wystan.pipeline_v2.detach_accounting import (
            run_detach_accounting,
        )
        _da_tele = run_detach_accounting(
            features, product_features, user_flows,
            list(bipartite.flows), platform_infrastructure,
            non_product_surfaces,
        )
        if _da_tele is not None:
            scan_meta["detach_accounting"] = _da_tele
    except Exception as exc:  # noqa: BLE001 — accounting never breaks a scan
        scan_meta.setdefault("warnings", []).append(
            f"detach accounting failed ({exc}); detachments unaccounted"
        )

    # ── Stage 6.9975 — fixb114/P12-M1 PF-loc RE-ROLL on final membership ──
    # ``pf.loc`` is rolled up ONCE at 6.97; every re-home / demote / rename
    # after it leaves the scalar stale in BOTH directions (P12 census, FRESH
    # KS60: 22 PFs low + 5 high vs their own members; cold calibration
    # growthbook features 8x inflated / auth 62x deflated, twenty-sdk 169x).
    # Both existing repair hooks are falsy-gated (emission_hard_gate E1 and
    # 6.97e's backstop) so they only ever see a bare 0, and 6.97e is
    # additionally contracted UPWARD-only. This pass replays 6.97's OWN
    # rollup law over the ledger 6.97 captured, against the membership as it
    # stands HERE — after the hard gate and after detach accounting, i.e.
    # nothing can move a dev behind its back. Two-sided by construction; the
    # only refused direction is down-to-zero (the B98-3e span-LOC and
    # no-dev-member-fallback provenances, counted not silently dropped).
    # Kill-switch: WYSTAN_PF_LOC_REROLL unset/0 (the DEFAULT — OFF) skips
    # the stage ⇒ byte-identical. Never breaks a scan.
    from wystan.pipeline_v2.stage_6_97e_pf_loc import (
        apply_pf_loc_reroll,
        pf_loc_reroll_enabled,
    )
    if pf_loc_reroll_enabled():
        with StageLogger(run_dir, 7, "pf_loc_reroll") as log_reroll:
            try:
                _reroll_tele = apply_pf_loc_reroll(
                    product_features,
                    features,
                    _pf_loc_ledger,
                    user_flows=user_flows,
                    flows=list(bipartite.flows),
                )
                # DELIBERATELY NOT touching scan_meta.loc_accounting
                # .sum_pf_owned. Measured on the FRESH KS60 world: 17 of 20
                # boards already carry a gap between that scalar and
                # Σ(emitted pf.loc) — 571715 LOC in total, and it is present
                # on boards this pass does not touch at all (chatwoot 383,
                # inbox-zero 8766, papermark 2135, ollama 1756, all with
                # ZERO re-rolls). It is stale w.r.t. the PF DEMOTIONS that
                # run after 6.97, i.e. a different I13 class with a
                # different cure. Re-stamping it here would ride a 93089-LOC
                # webstudio correction on this flag and conflate two
                # findings; the honest Σ lives in the side artifact
                # (``sum_pf_owned``) so the class stays visible and separately
                # actionable. Telemetry stays out of scan_meta entirely (the
                # uf_loc/flow_loc convention), so the ON-vs-OFF output diff is
                # EXACTLY the re-rolled PF scalars.
                log_reroll.info(
                    "pf_loc_reroll: %d/%d PFs re-rolled (%d up / %d down, "
                    "%d late-mint, %d zero-guarded, net %+d LOC)" % (
                        _reroll_tele["pfs_rerolled"],
                        _reroll_tele["pfs_total"],
                        _reroll_tele["pfs_raised"],
                        _reroll_tele["pfs_lowered"],
                        _reroll_tele["pfs_late_mint_entered"],
                        _reroll_tele["pfs_zero_guarded"],
                        _reroll_tele["loc_delta"],
                    ),
                    feature=None,
                )
                write_stage_artifact(
                    ctx.repo_path,
                    stage_index=7,
                    stage_name="pf_loc_reroll",
                    payload=_reroll_tele,
                    run_dir=run_dir,
                )
            except Exception as exc:  # noqa: BLE001 — metric never breaks a scan
                scan_meta.setdefault("warnings", []).append(
                    f"pf-loc re-roll failed ({exc}); PF loc left as rolled"
                )
                log_reroll.info(
                    f"pf_loc_reroll: FAILED ({exc}) — continuing", feature=None,
                )

    # B89 terminal product-right census — the board carries its own count of
    # the five canon masquerader classes (1:1 with eval/product_right_gate.py)
    # so the external gate reads scan_meta.product_right_census as its first
    # source. Runs AFTER every structural + nav-parent writer, before
    # emission. No-op / no key when the flag is off (byte-identical).
    try:
        invariant_hooks.run_product_right_census(
            scan_meta, product_features, user_flows, features)
    except Exception as exc:  # noqa: BLE001 — census never breaks a scan
        scan_meta.setdefault("warnings", []).append(
            f"product-right census failed ({exc}); census skipped"
        )

    # ── fixb118 Q5 — landing audit (the class becomes self-reporting) ────
    # Emit-time reconciliation of Seg B's journaled landings against the
    # EMITTED homes. Slot: after EVERY homing/demote writer (incl. the
    # post-arbiter eight the overturn census can no longer see, since
    # finalize_arbiter rendered its payload at :5263) and before Stage 7,
    # so what it compares is exactly what ships. Each overturned landing
    # carries a NAMED reason: ``target-demoted`` / ``journey-dropped``
    # (case "b" — structurally forced, honest) vs ``silent-overturn``
    # (case "a" — the bug class; INVARIANT: 0 once the binding is armed).
    # Flag OFF ⇒ registry is None ⇒ returns None ⇒ no scan_meta key ⇒
    # byte-identical.
    from wystan.pipeline_v2.segb_landing_binding import (
        run_landing_audit,
        uninstall_landing_registry,
    )
    try:
        _la_tele = run_landing_audit(user_flows, product_features)
        if _la_tele is not None:
            scan_meta["landing_audit"] = _la_tele
    except Exception as exc:  # noqa: BLE001 — audit never breaks a scan
        scan_meta.setdefault("warnings", []).append(
            f"landing audit failed ({exc}); no landing_audit key"
        )
    finally:
        # The registry is thread-local and the worker reuses threads across
        # scans — a leaked registry would bind the NEXT scan to this scan's
        # landings. Teardown must survive an audit exception.
        uninstall_landing_registry()

    # ── fixb119 M1 — journey-lineage audit (a journey's death gets named) ─
    # The same seam as the landing audit: AFTER every removal writer and
    # BEFORE Stage 7, so exactly what ships is reconciled. Every snapshot
    # row either survived / was re-minted (RE-ID), or abstained, or has a
    # record in a KNOWN channel (id tier, then name tier), or goes BY NAME
    # into ``unaccounted`` + a WARN hook. The audit does NOT change the
    # board — zero touches to the 28 in-place removal sites. Flag OFF ⇒
    # byte-identical.
    from wystan.pipeline_v2.journey_lineage_audit import (
        run_journey_lineage_audit as _run_jla,
        unaccounted_exhibits as _jla_exhibits,
        uninstall_journey_lineage_registry as _jla_uninstall,
    )
    try:
        _jla_tele = _run_jla(user_flows, scan_meta, non_product_surfaces)
        if _jla_tele is not None:
            scan_meta["journey_lineage_audit"] = _jla_tele
            invariant_hooks.run_stage(
                scan_meta, "journey_lineage_audit",
                unaccounted_ids=_jla_exhibits(),
                # fixb121 — the conservation loop is stamped AT THE
                # PRODUCER STAGE (the stage-hooks law): the equality
                # snapshot + births − deaths == emitted is checked where the
                # baskets were just counted.
                conservation_ok=bool(_jla_tele.get("conservation_ok", True)),
                snapshot=_jla_tele.get("snapshot"),
                births_count=_jla_tele.get("births_count"),
                deaths=_jla_tele.get("deaths"),
                emitted=_jla_tele.get("emitted"),
            )
    except Exception as exc:  # noqa: BLE001 — the audit never breaks a scan
        scan_meta.setdefault("warnings", []).append(
            f"journey-lineage audit failed ({exc}); no journey_lineage_audit key"
        )
    finally:
        # The registry is thread-local and the worker reuses threads
        # between scans — a leak would reconcile the NEXT scan with this one.
        _jla_uninstall()

    # ── fixb124 / E1 — metric-ownership gate (no ownership = null metric) ─
    # The clone form (ollama: 7 husk PFs on ONE server/routes.go carry the
    # same tuple 82.0/63.0/94/2026-04-29 — the FILE's history, not their own
    # rows) and the vacuum form (maybe 47/47, skateshop 22/22, peppermint
    # 12/12, highlight 22 — health=100.0 with commits=0) are one disease: a
    # row publishes a number measured on evidence it does not OWN. The gate
    # reads ownership from the EMITTED ``path_index`` (one owner per file)
    # and abstains any row whose owned files produced NO commit at all:
    # metrics → null + ``metrics_abstained`` + health_confidence="insufficient".
    # NOTHING is re-measured — a row with even one commit of its own stays
    # byte-identical, so the three RATIFIED legitimate collisions (dokploy
    # 708/752/764 on constants.ts, novu commits=2 on base.provider.ts,
    # fastapi __init__.py 143) pass the gate untouched.
    # Slot: AFTER every membership/metric writer (6.998 recompute,
    # twin-collision, demotes, hard-gate, detach) and BEFORE Stage 7 — the
    # gate judges exactly what ships, by the same path_index that ships.
    # Flag WYSTAN_METRICS_OWNERSHIP_GATE default OFF (armed): unset/0 ⇒
    # the pass is not entered ⇒ no scan_meta key ⇒ byte-identical.
    from wystan.pipeline_v2.metrics_ownership_gate import (
        metrics_ownership_gate_enabled,
        run_metrics_ownership_gate,
    )
    if metrics_ownership_gate_enabled():
        with StageLogger(run_dir, 7, "metrics_ownership_gate") as log_mog:
            try:
                mog_tele = run_metrics_ownership_gate(
                    features, product_features, ctx.commits,
                    lineage_result.path_index,
                )
                scan_meta["metrics_ownership_gate"] = mog_tele
                log_mog.info(
                    "metrics_ownership_gate: pf %d/%d, dev %d/%d abstained "
                    "(foreign_basis %d, no_basis %d)" % (
                        mog_tele["abstained_pf"], mog_tele["pf_rows"],
                        mog_tele["abstained_dev"], mog_tele["dev_rows"],
                        mog_tele["by_reason"]["foreign_basis"],
                        mog_tele["by_reason"]["no_basis"],
                    ),
                    feature=None,
                )
                write_stage_artifact(
                    ctx.repo_path,
                    stage_index=7,
                    stage_name="metrics_ownership_gate",
                    payload=dict(mog_tele),
                    run_dir=run_dir,
                )
            except Exception as exc:  # noqa: BLE001 — the gate never breaks a scan
                scan_meta.setdefault("warnings", []).append(
                    f"metrics-ownership gate failed ({exc}); metrics left as-is"
                )
                log_mog.info(
                    f"metrics_ownership_gate: FAILED ({exc}) — continuing",
                    feature=None,
                )

    # ── fixb127 / E1-flow — the flow layer of the same disease ─────────────
    # Probe (29460/29460 flow rows across 34 boards): a flow's git family was
    # NEVER MEASURED. ``_flow_spec_to_flow`` sets health_score=80.0 as a
    # HAND-WRITTEN LITERAL next to total_commits=0/authors=[]/epoch, and a
    # flow equivalent of ``_finalize_feature_metrics`` DOES NOT EXIST —
    # neither the 6.998 recompute nor the gate above accepts flow rows. No
    # formula produces 80 (_calculate_health(total=0)=100). The cross-layer
    # contradiction this closes (ollama c16): 41 E1-abstained PARENTS are
    # honestly null while their 61 CHILD FLOWS in the same tile publish 80.0.
    # Mechanism (ruling): the file-based E1 predicate does NOT port —
    # path_index.flow_uuids is a LIST (up to 417 claimants), so porting would
    # manufacture a clone verdict out of a list of claims. The predicate is
    # trivially true ⇒ abstain WITHOUT counting ownership, reason='no_basis'
    # on EVERY row, in BOTH views (top-level flows[] AND containment
    # features[].flows[] — the probe caught field divergence between views).
    # NOT TOUCHED: coverage_pct (genuinely measured, 100% of rows), loc/
    # loc_shared (the LOC law), hotspot_files*/test_file* (honest file grain),
    # membership and identity.
    # Slot: right after the parent gate, BEFORE Stage 7 — exactly what ships
    # is judged. Flag WYSTAN_METRICS_OWNERSHIP_GATE_FLOWS default OFF
    # (armed), nested under the parent: parent 0 ⇒ the pass is not entered ⇒
    # no scan_meta key ⇒ the board is byte-identical to the pre-gate one.
    from wystan.pipeline_v2.metrics_ownership_gate import (
        flow_metrics_gate_enabled,
        run_flow_metrics_abstain,
    )
    if flow_metrics_gate_enabled():
        with StageLogger(run_dir, 7, "flow_metrics_abstain") as log_fma:
            try:
                fma_tele = run_flow_metrics_abstain(
                    list(bipartite.flows), features, product_features,
                )
                scan_meta["metrics_ownership_gate_flows"] = fma_tele
                log_fma.info(
                    "flow_metrics_abstain: %d/%d distinct rows abstained "
                    "(top %d/%d, dev %d/%d, pf %d/%d, kept %d)" % (
                        fma_tele["abstained_distinct"], fma_tele["rows_distinct"],
                        fma_tele["abstained_top_level"],
                        fma_tele["flows_top_level"],
                        fma_tele["abstained_containment_dev"],
                        fma_tele["flows_containment_dev"],
                        fma_tele["abstained_containment_pf"],
                        fma_tele["flows_containment_pf"],
                        fma_tele["kept_measured"],
                    ),
                    feature=None,
                )
                write_stage_artifact(
                    ctx.repo_path,
                    stage_index=7,
                    stage_name="flow_metrics_abstain",
                    payload=dict(fma_tele),
                    run_dir=run_dir,
                )
            except Exception as exc:  # noqa: BLE001 — the gate never breaks a scan
                scan_meta.setdefault("warnings", []).append(
                    f"flow-metrics abstain failed ({exc}); flow metrics left as-is"
                )
                log_fma.info(
                    f"flow_metrics_abstain: FAILED ({exc}) — continuing",
                    feature=None,
                )

    # ── fixb145 — synth conversion (PRE-OUTPUT seam) ───────────────────
    # The single writer of ``UserFlow.synthesized`` after the journey layer
    # has settled. Deliberately LAST: emission_hard_gate counts NON-
    # synthesized journeys per PF (:141) and emission_integrity drops a
    # homeless SYNTHESIZED journey while a homeless REAL one BLOCKS the husk
    # fold (:527) — flipping the field before them would move coverage
    # counts and husk folds, a structural change this lane is not scoped to
    # make. Run here, the lanes change the emitted field and nothing else.
    # Both flags default OFF ⇒ both calls return None ⇒ no scan_meta key ⇒
    # serialized output byte-identical.
    try:
        from wystan.pipeline_v2.synth_conversion import (
            apply_synth_conversion,
            unsynth_authored_cli,
        )
        # fixb147 NS-50a-b — the flow layer rides along so lane 1 can resolve
        # a member uuid through ``flows[].merged_from`` before it mints a
        # journey a same-PF sibling already owns. Read-only: the guard never
        # writes to a flow, and with its own flag unset it never even builds
        # the map.
        _cli_unsynth_tele = unsynth_authored_cli(
            user_flows, list(bipartite.flows))
        if _cli_unsynth_tele is not None:
            scan_meta["cli_journey_unsynth"] = _cli_unsynth_tele
        _sc_tele = apply_synth_conversion(user_flows)
        if _sc_tele is not None:
            scan_meta["synth_conversion_applied"] = _sc_tele
    except Exception as exc:  # noqa: BLE001 — conversion never breaks a scan
        scan_meta.setdefault("warnings", []).append(
            f"synth-conversion failed ({exc}); synthesized tags left as-is"
        )

    # ── Stage 7 — output ───────────────────────────────────────────
    from wystan import __version__ as _engine_version  # late import
    write_stage_input(run_dir, 7, "output", {
        "features": features,
        "ctx": ctx,
        "scan_meta": scan_meta,
        "bipartite_flows": list(bipartite.flows),
        "bipartite_edges": list(bipartite.edges),
        "product_features": product_features,
        "user_flows": user_flows,
        "path_index": lineage_result.path_index,
        "routes_index": lineage_result.routes_index,
        "is_full_scan": is_full_scan,
        "since": since,
        "head": head,
        "days": days,
        "monorepo_view": monorepo_view,
        "non_product_surfaces": non_product_surfaces,
        "platform_infrastructure": platform_infrastructure,
    })
    with StageLogger(run_dir, 7, "output") as log7:
        out = stage_7_output(
            features, ctx, scan_meta, out_path,
            days=days,
            flows=bipartite.flows,
            feature_flow_edges=bipartite.edges,
            product_features=product_features,
            user_flows=user_flows,
            path_index=lineage_result.path_index,
            routes_index=lineage_result.routes_index,
            is_full_scan=is_full_scan,
            base_scan_commit=(since or ""),
            scan_commit=head,
            engine_version=_engine_version,
            monorepo=monorepo_view,
            non_product_surfaces=non_product_surfaces,
            platform_infrastructure=platform_infrastructure,
            # B45 — None (key omitted) unless the gap channel emitted gaps.
            coverage_gaps=coverage_gaps,
        )
        log7.info(f"wrote feature map to {out}", feature=None)

    return out


__all__ = [
    "run_finalize_phase",
]
