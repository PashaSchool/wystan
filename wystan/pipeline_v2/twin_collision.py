"""B92 — same-slug twin collision (two rungs, both SAME-PF guarded).

Operator exhibit (2026-07-25, ``refapp-filter-inventory-twin-flow``): two
same-slug developer features ``inventory`` / ``inventory-2`` (the ``-N``
collision suffix minted at ``post_process.py:719-725``) map to ONE product
feature ``inventory`` and each mint a homonym flow ``filter-inventory-flow``
(genuinely different surfaces — ``InventoryFilterPanel`` 204 LOC vs
``EntityFilterBar`` 177 LOC). Read in the PF view the pair reads as a
duplicate.

The probe (``/private/tmp/b92-work/probe_verdict.md``, $0 cached census over
19 boards) proved the operator's ONE exhibit sits atop TWO separable
diseases in the SAME-PF flow-collision class (29 groups):

  * DUP_EXTRACTION (one PF **and** path-Jaccard ≥ ~0.3): the same dir
    extracted twice under one PF. Cure = MERGE the twin features.
  * DISJOINT-FACET (one PF, path-Jaccard < ~0.3; 21 groups / 97 collisions,
    75% of the symptom): two GENUINELY distinct sub-features under one PF
    minting homonym flows. Merging would DESTROY real facets. Cure =
    NAME-QUALIFY only.

Both rungs guard on ``product_feature_id`` agreement — the NEW safety signal
the refuted bare path-set merge (memory 2026-06-01) lacked. Path-overlap
ALONE is re-refuted here: 29 MULTIPF_OVERLAP groups (cal.com ``components``
J=1.00 across 5+ PFs) would be wrongly collapsed by overlap without the PF
guard; the SAME-PF guard excludes every one of them structurally.

Rung D — ``WYSTAN_TWIN_FLOW_DECOLLIDE`` (lead shoulder): PF-namespace
flow-name de-collision. Extends the ``flow_name_v2`` collision ladder
(which is PF-blind and only de-collides *proposed* renames, never two
HONEST LLM names). De-collides ALL flows sharing a ``product_feature_id``
by a deterministic entry-component qualifier. Heals all 29 one-PF
flow-collision groups incl. the 21 disjoint facets that Rung B must NOT
touch. Runs at the finalize name seam (after ``flow_name_v2``).

Rung B — ``WYSTAN_TWIN_FEATURE_MERGE`` (structural completion): merges
the ~22 real DUP_EXTRACTION twin features (same PF + collision-suffix +
path-Jaccard ≥ θ), unions their paths/flows, dedups the true-duplicate
flows by ``(name, entry file:line)`` (reusing the Stage-5.5 primitive),
absorbs the B85 fold-husk siblings, and re-projects the bipartite store so
``flows[]`` / ``feature_flow_edges[]`` / ``flow.id`` stay coherent. Runs
post-6.86 mint (PF exists) and BEFORE the 6.7 UF rollup so the journey
layer forms over the deduped set — no UF re-pointing needed. Husk-only
groups (no real canonical — twenty ``components``, cal.com ``libraries``,
tracecat ``executor``) are B85 residue, OUT of scope, left untouched.

Rung B husk-canonical rescue — ``WYSTAN_TWIN_HUSK_CANONICAL`` (default
OFF, 2026-07-31 operator exhibit ``refapp-ticketing-twin-fragmentation``):
the SAME-PF guard skips a family FOREVER when the base ``X`` is a SHELL husk
(``pf=None``, ``shell_lineage_only``) that LOST the 6.86 anchor competition
to its live twin, which then took a ``-N`` suffix (RefApp ``ticketing``:
spa-page husk + ``ticketing-2`` route:ticketing loc68 + ``ticketing-3`` B85
carve loc1 — 3 rows, one real feature). When EXACTLY ONE real (non-husk)
member of a guard-tripped family carries a non-None pf, and every other
member is a husk homed to None or that same pf, the rescue promotes the real
member to canonical, absorbs the husk base (+ same-pf fold-husk siblings),
and frees the base name (the ``-N`` disappears; Fix-D suffix hygiene). ≥2
real-pf members, a real member with no pf, or a husk homed to a DIFFERENT pf
= genuine cross-PF ambiguity where the guard STILL holds (RefApp ``api`` /
``components`` / ``frontend-src`` stay skipped). loc is conservation-safe:
the delegated closure lines the husk carried stay owned by their real
feature via the 6.97 primary-owner election (0 flows, losing slug).

Both flags default **OFF**; unset / ``0`` / ``false`` ⇒ every entry point
returns before any mutation ⇒ byte-identical to the pre-B92 engine (the KS
4-way kill-switch law, forever). Different flip maturity (B82 precedent):
Rung D is the higher-confidence, broader-coverage, lower-risk lead; Rung B
is the correctness completion for the dup-extraction subset. No KEY_SCHEMA
bump — the bump rides the separate later flip commit.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any

from wystan.models.types import FeatureFlowEdge
from wystan.pipeline_v2.flow_name_v2 import (
    _QUALIFIER_STOP_TOKENS,
    _entry_file_of,
    _name_key,
    _slugify,
    _strip_flow_suffix,
)
from wystan.pipeline_v2.stage_5_5_bipartite import (
    _dedup_identical_flows,
    _flow_id,
)

__all__ = [
    "TWIN_FLOW_DECOLLIDE_ENV",
    "TWIN_FEATURE_MERGE_ENV",
    "TWIN_HUSK_CANONICAL_ENV",
    "twin_flow_decollide_enabled",
    "twin_feature_merge_enabled",
    "twin_husk_canonical_enabled",
    "apply_flow_pf_decollide",
    "apply_twin_feature_merge",
    "pf_dup_flow_names",
]

TWIN_FLOW_DECOLLIDE_ENV = "WYSTAN_TWIN_FLOW_DECOLLIDE"
TWIN_FEATURE_MERGE_ENV = "WYSTAN_TWIN_FEATURE_MERGE"
TWIN_HUSK_CANONICAL_ENV = "WYSTAN_TWIN_HUSK_CANONICAL"

_OFF_VALUES = {"0", "false", "False", "off", "no", ""}


def twin_flow_decollide_enabled() -> bool:
    """Rung D. Default **ON** since the 2026-07-27 flip-pack №8 flip
    (KEY_SCHEMA 41; keyed RefApp proof: same-slug twin flow-name collisions
    de-collided). Unset now arms Rung D; explicit ``0`` / ``false`` / ``off``
    / ``no`` / ``""`` ⇒ no-op (byte-identical; kill-switch forever). Only the
    ``os.environ.get`` default moved ``""`` -> ``"1"`` (unset ≡ explicit
    ``"1"``); the ``_OFF_VALUES`` kill-switch set is preserved LITERALLY."""
    return os.environ.get(TWIN_FLOW_DECOLLIDE_ENV, "1").strip() not in _OFF_VALUES


def twin_feature_merge_enabled() -> bool:
    """Rung B. Default **ON** since the 2026-07-27 flip-pack №8 flip
    (KEY_SCHEMA 41; keyed RefApp proof: dup-extraction twin dev features merged
    at the θ=0.3 plateau, all 8 must-merge caught / all 8 anti-case facets
    protected). Unset now arms Rung B; explicit ``0`` / ``false`` / ``off`` /
    ``no`` / ``""`` ⇒ no-op (byte-identical; kill-switch forever). Only the
    ``os.environ.get`` default moved ``""`` -> ``"1"`` (unset ≡ explicit
    ``"1"``); the ``_OFF_VALUES`` kill-switch set is preserved LITERALLY."""
    return os.environ.get(TWIN_FEATURE_MERGE_ENV, "1").strip() not in _OFF_VALUES


def twin_husk_canonical_enabled() -> bool:
    """Rung B husk-canonical rescue + the T5 b85 carve-absorb (operator
    exhibit ``refapp-ticketing-twin-fragmentation``). Default **ON** since the
    2026-07-31 flip-pack №14 flip (KEY_SCHEMA 49; keyed RefApp proof: ticketing
    3→1, loc=69). Unset now arms the rescue + carve-absorb; explicit ``0`` /
    ``false`` / ``off`` / ``no`` / ``""`` ⇒ neither branch is ever entered ⇒
    byte-identical to the pre-rescue world (the SAME-PF guard keeps skipping
    every None-PF family; the b85 carve mints suffixed rows as before) —
    kill-switch forever. Only the ``os.environ.get`` default moved ``""`` ->
    ``"1"`` (unset ≡ explicit ``"1"``); the ``_OFF_VALUES`` kill-switch set is
    preserved LITERALLY."""
    return os.environ.get(TWIN_HUSK_CANONICAL_ENV, "1").strip() not in _OFF_VALUES


# ── shared mechanics (structural, not vocabularies) ─────────────────────

#: Collision-suffix pattern minted by ``post_process.py::_slugify_names``
#: (``X`` kept verbatim, later collisions get ``X-2`` / ``X-3`` …). Mirror of
#: ``stage_5_postprocess._SUFFIX_RE``.
_SUFFIX_RE = re.compile(r"^(?P<base>.+?)-(?P<n>\d+)$")

#: Overlap-ratio threshold for the Rung-B feature merge — path Jaccard.
#: SWEEP on the probe census (135 one-PF twin groups, ``census.json``): the J
#: distribution has a clean BIMODAL GAP — the disjoint facets top out at
#: ``0.273`` (twenty ``auth``, 14 collisions) and the dup-extractions bottom
#: at ``0.33`` (RefApp ``gen-ai-visibility``, novu ``environments``, cal.com
#: ``sms``). Every θ in the PLATEAU ``[0.28, 0.33]`` yields the IDENTICAL
#: partition — 25 merge / 110 keep — with ALL 8 named must-merge groups caught
#: AND ALL 8 named anti-case facets protected (verified by sweep at
#: 0.28/0.30/0.31/0.33). ``0.3`` is the plateau centre, a round non-tuned
#: coordinate: range-insensitive by construction (θ=0.27 wrongly pulls in
#: twenty ``auth``; θ=0.34 wrongly drops the 0.33 dups). NOT a per-repo magic
#: number — a scale-invariant ratio separating a corpus-wide empirical gap
#: (rule-no-magic-tuning).
_OVERLAP_JACCARD = 0.3


def _jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a or ()), set(b or ())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _suffix_ordinal(name: str) -> int:
    m = _SUFFIX_RE.match(name or "")
    if not m:
        return 0
    try:
        return int(m.group("n"))
    except ValueError:
        return 0


def _is_fold_husk(feat: Any) -> bool:
    """A B85 fold-demote husk: a ``fold:`` anchor, a ``split_from`` origin,
    ZERO flows and a tiny path footprint (≤ 2). The census's ``inventory-3``
    (``fold:b85_fold_demote-home->compliance``, loc=1, 0 flows, 1 path) is the
    canonical shape. ``loc`` is NOT a discriminator (a husk can carry the
    folded-away loc — twenty ``components`` husks read loc=837). Anti-case: a
    real feature (any flow) never trips (the ``not flows`` conjunct)."""
    anchor = str(getattr(feat, "anchor_id", "") or "")
    if not anchor.startswith("fold:"):
        return False
    if getattr(feat, "split_from", None) is None:
        return False
    if getattr(feat, "flows", None):
        return False
    return len(getattr(feat, "paths", None) or []) <= 2


#: Shared-residency reasons (Product-Spine §4.3 ``shared_reason`` vocabulary)
#: that mark a SHELL husk — a dev feature that LOST the Stage-6.86 anchor
#: competition to a same-slug twin and was parked in the shared/platform
#: bucket with ``product_feature_id`` None. Mirror of ``stage_6_86``'s
#: ``_SHARED_REASON_SHELL`` + the ``no_anchor_lineage`` sibling class.
_SHELL_HUSK_REASONS = frozenset({"shell_lineage_only", "no_anchor_lineage"})


def _is_shell_husk(feat: Any) -> bool:
    """A B92-scope SHELL husk: a dev feature that lost the Stage-6.86 anchor
    competition to its same-slug live twin and was parked shared —
    ``product_feature_id`` None, ``shared_reason`` in the shell set, ZERO
    flows. The RefApp spa-page ``ticketing`` base (pf=None, anchor=None,
    ``shared_reason='shell_lineage_only'``, 0 flows, 3 delegated paths) is the
    canonical shape. Unlike ``_is_fold_husk`` (a B85 ``fold:`` carve), a shell
    husk carries its delegated surface as members but never a pf and never a
    flow — so absorbing it into its live twin is journey-conservation-trivial.
    ``loc`` is NOT a discriminator (recomputed at 6.97 from the unioned
    members via the primary-owner election, which keeps the delegated
    closure lines owned by their real feature). Anti-case: a real feature
    (any flow) or a genuinely homed orphan (non-None pf) never trips."""
    if getattr(feat, "product_feature_id", None) is not None:
        return False
    if getattr(feat, "flows", None):
        return False
    reason = str(getattr(feat, "shared_reason", "") or "")
    return reason in _SHELL_HUSK_REASONS


# ── Rung D — PF-namespace flow-name de-collision ────────────────────────


def _entry_qualifier(core: str, flow: Any) -> str | None:
    """``<core>-<entry-component-tokens>-flow`` or ``None``.

    The qualifier tokens come from the flow's ENTRY-COMPONENT file stem — the
    deepest, most distinctive path segment — minus the tokens already in
    ``core`` and the generic stop-tokens (mirror of ``flow_name_v2``'s
    ``_feature_qualified``, but sourced from the entry component instead of
    the dev-feature name so two flows under ONE feature — post-Rung-B — still
    separate). ``filter-inventory`` @ ``InventoryFilterPanel.tsx`` →
    ``filter-inventory-panel-flow`` (``inventory`` / ``filter`` already in
    core, ``panel`` kept). Structural, never a word list."""
    entry = _entry_file_of(flow)
    if not entry:
        return None
    stem = PurePosixPath(entry).stem
    toks = [
        t for t in _slugify(stem).split("-")
        if t and t not in _QUALIFIER_STOP_TOKENS
    ]
    base_toks = set(core.split("-"))
    kept = [t for t in toks if t not in base_toks]
    if not kept:
        return None
    return f"{core}-{'-'.join(kept)}-flow"


def _apply_rename(flow: Any, candidate: str, tele: dict[str, Any], pf: str,
                  arm: str) -> None:
    """Mutate ``flow.name`` (+ the display / short-label kebab mirrors) IN
    PLACE. NEVER touches ``flow.id`` / ``flow.uuid`` (the UF-member + edge
    join keys). Mirrors ``flow_name_v2.apply_flow_name_v2``'s mutation."""
    old = flow.name
    flow.name = candidate
    if not flow.display_name or flow.display_name == old:
        flow.display_name = candidate
    old_short = _strip_flow_suffix(old)
    if flow.short_label in (old, old_short, ""):
        flow.short_label = _strip_flow_suffix(candidate)
    tele[f"decollided_{arm}"] += 1
    if len(tele["samples"]) < 20:
        tele["samples"].append({"pf": pf, "from": old, "to": candidate})


def apply_flow_pf_decollide(
    features: list[Any], flows: list[Any],
) -> dict[str, Any]:
    """Rung D — de-collide flow names that repeat WITHIN one product feature.

    Groups every flow by its owning dev feature's ``product_feature_id`` (the
    exact key the external ``product_right_gate`` uses:
    ``feat_to_pf[flow.primary_feature]``). Within a PF namespace, each set of
    ≥2 flows sharing a name is de-collided: the first (deterministic order)
    keeps the bare name; the rest take an entry-component qualifier, then a
    stable ordinal. Cross-PF homonyms are left ALONE (disambiguated by their
    PF context). Flows with no PF (``product_feature_id is None``) carry no PF
    namespace and are skipped. Mutates only the name channel.
    """
    tele: dict[str, Any] = {
        "flows_total": len(flows),
        "pf_groups_scanned": 0,
        "collision_groups": 0,
        "decollided_entry_qualified": 0,
        "decollided_ordinal": 0,
        "samples": [],
    }
    feat_to_pf = {
        f.name: getattr(f, "product_feature_id", None) for f in features
    }
    by_pf: dict[str, list[Any]] = defaultdict(list)
    for fl in flows:
        pid = feat_to_pf.get(getattr(fl, "primary_feature", None))
        if not pid:  # None / missing → no PF namespace to de-collide within
            continue
        if not getattr(fl, "name", None) or not (getattr(fl, "uuid", "") or ""):
            continue  # uuid is the join key — never risk a nameless/uuidless flow
        by_pf[pid].append(fl)

    for pid, group in by_pf.items():
        tele["pf_groups_scanned"] += 1
        by_name: dict[str, list[Any]] = defaultdict(list)
        for fl in group:
            by_name[_name_key(fl.name)].append(fl)
        # ``taken`` reserves EVERY current name in the PF so a qualifier never
        # collides with an unrelated sibling.
        taken: set[str] = {_name_key(fl.name) for fl in group}
        for _key, colliding in sorted(by_name.items()):
            if len(colliding) < 2:
                continue
            tele["collision_groups"] += 1
            # Deterministic order: entry file, entry line, uuid. The first
            # keeps its bare name (canonical); the rest are qualified.
            colliding.sort(key=lambda f: (
                _entry_file_of(f), f.entry_point_line or 0, f.uuid,
            ))
            for flow in colliding[1:]:
                core = _strip_flow_suffix(flow.name)
                candidate = _entry_qualifier(core, flow)
                if candidate is None or _name_key(candidate) in taken:
                    ordinal = 2
                    candidate = f"{core}-{ordinal}-flow"
                    while _name_key(candidate) in taken:
                        ordinal += 1
                        candidate = f"{core}-{ordinal}-flow"
                    arm = "ordinal"
                else:
                    arm = "entry_qualified"
                taken.add(_name_key(candidate))
                _apply_rename(flow, candidate, tele, str(pid), arm)

    tele["decollided_total"] = (
        tele["decollided_entry_qualified"] + tele["decollided_ordinal"]
    )
    return tele


# ── Rung B — dup-extraction twin-feature merge ──────────────────────────


def _union_paths(canonical: Any, other: Any) -> None:
    seen = set(canonical.paths)
    for p in other.paths:
        if p not in seen:
            canonical.paths.append(p)
            seen.add(p)


def _union_member_files(canonical: Any, other: Any) -> None:
    existing = {
        (getattr(m, "path", None), getattr(m, "role", None))
        for m in (getattr(canonical, "member_files", None) or [])
    }
    for m in getattr(other, "member_files", None) or []:
        key = (getattr(m, "path", None), getattr(m, "role", None))
        if key not in existing:
            canonical.member_files.append(m)
            existing.add(key)


def _absorb_husk(canonical: Any, husk: Any) -> None:
    """Fold a fold-husk sibling into the canonical: paths + member_files only
    (a husk carries ZERO flows by definition — conservation is trivial)."""
    _union_paths(canonical, husk)
    _union_member_files(canonical, husk)


def _absorb_feature(canonical: Any, sib: Any) -> None:
    """Fold a real twin sibling into the canonical IN PLACE (preserving the
    canonical's uuid / identity). Union paths, concat flows (re-stamped +
    deduped by the caller), union authors + member_files, combine numerics."""
    _union_paths(canonical, sib)
    seen_authors = set(canonical.authors)
    for a in sib.authors:
        if a not in seen_authors:
            canonical.authors.append(a)
            seen_authors.add(a)
    canonical.flows = list(canonical.flows) + list(sib.flows)
    canonical.bug_fix_prs = list(canonical.bug_fix_prs) + list(sib.bug_fix_prs)
    canonical.shared_attributions = (
        list(canonical.shared_attributions) + list(sib.shared_attributions)
    )
    canonical.participants = (
        list(canonical.participants) + list(sib.participants)
    )
    canonical.shared_participants = (
        list(canonical.shared_participants) + list(sib.shared_participants)
    )
    _union_member_files(canonical, sib)
    canonical.total_commits = (canonical.total_commits or 0) + (sib.total_commits or 0)
    canonical.bug_fixes = (canonical.bug_fixes or 0) + (sib.bug_fixes or 0)
    canonical.bug_fix_ratio = round(
        (canonical.bug_fixes / canonical.total_commits)
        if canonical.total_commits > 0 else 0.0,
        4,
    )
    canonical.last_modified = max(canonical.last_modified, sib.last_modified)
    canonical.health_score = max(
        canonical.health_score or 0.0, sib.health_score or 0.0,
    )
    if canonical.coverage_pct is None:
        canonical.coverage_pct = sib.coverage_pct


def _reproject_bipartite(features: list[Any], bipartite: Any) -> None:
    """Rebuild the bipartite store from the post-merge containment so the
    emitted ``flows[]`` / ``feature_flow_edges[]`` / per-flow ``id`` /
    ``primary_feature`` / ``secondary_features`` stay coherent after a
    feature merge.

    Pure re-derivation (mirrors Stage-5.5 Steps 1-5, WITHOUT the name
    disambiguation — Rung D owns that at the finalize name seam). Every flow's
    ``uuid`` (the UF-member join key) is untouched.
    """
    # Step 1 — path → owning feature names.
    path_to_features: dict[str, set[str]] = defaultdict(set)
    for feat in features:
        for p in feat.paths or []:
            path_to_features[p].add(feat.name)

    # Step 2 — re-stamp per-flow identity + cross-cutting attachments.
    all_flows: list[Any] = []
    for feat in features:
        primary = feat.name
        for flow in feat.flows:
            flow.primary_feature = primary
            flow.id = _flow_id(primary, flow.name)
            secondaries = {
                owner
                for p in (flow.paths or [])
                for owner in path_to_features.get(p, ())
                if owner != primary
            }
            flow.secondary_features = sorted(secondaries)
            flow.shared_with_features_count = len(secondaries)
            flow.cross_cutting = bool(secondaries)
            all_flows.append(flow)

    # Step 3 — blast-radius shared-flow counters (pairwise path share).
    path_sets = [set(fl.paths or []) for fl in all_flows]
    for i, paths_i in enumerate(path_sets):
        if not paths_i:
            all_flows[i].shared_with_flows_count = 0
            continue
        all_flows[i].shared_with_flows_count = sum(
            1 for j, pj in enumerate(path_sets) if j != i and (paths_i & pj)
        )

    # Step 4 — edges (one primary per flow + secondary per attachment).
    edges: list[FeatureFlowEdge] = []
    for flow in all_flows:
        edges.append(FeatureFlowEdge(
            feature=flow.primary_feature, flow_id=flow.id,
            type="primary", reason=None,
        ))
        for sec in flow.secondary_features:
            edges.append(FeatureFlowEdge(
                feature=sec, flow_id=flow.id,
                type="secondary", reason="path-overlap",
            ))

    # Step 5 — top-level projection (stable order by id).
    bipartite.flows = sorted(all_flows, key=lambda f: f.id or "")
    bipartite.edges = edges


def _resolve_husk_canonical(members: list[Any]) -> tuple[Any, Any] | None:
    """Husk-canonical rescue selector for a collision-suffix family that
    tripped the SAME-PF guard (``len(pf_ids) != 1 or None in pf_ids``).

    Returns ``(canonical, real_pf)`` when the family is the healable shape —
    EXACTLY ONE real (non-husk) member carries a non-None pf, and EVERY other
    member is a husk (shell- or fold-) homed to None or that SAME pf — else
    ``None`` (the guard genuinely holds). By construction there is exactly one
    real pf, so the mandate's "≥2 real-pf siblings with DIFFERENT pf → skip"
    is satisfied structurally, and the RefApp anti-cases stay skipped:

      * ``api`` — base pf=None but NOT a shell husk (plumbing scatter), and 9
        fold-husks homed to 9 different pfs ⇒ ``reals`` empty ⇒ ``None``.
      * ``components`` — one real (``mitre-framework``) + 3 fold-husks homed to
        ``detectors`` ⇒ a husk homed elsewhere ⇒ ``None``.
      * ``frontend-src`` / ``investigation-playbook`` — ≥2 real members ⇒
        ``None``.

    The single healable RefApp family is ``ticketing`` (shell-husk base +
    ``ticketing-2`` real pf=ticketing + ``ticketing-3`` fold-husk pf=ticketing).
    """
    reals = [
        m for m in members
        if not _is_shell_husk(m) and not _is_fold_husk(m)
        and getattr(m, "product_feature_id", None) is not None
    ]
    if len(reals) != 1:
        return None
    canonical = reals[0]
    real_pf = getattr(canonical, "product_feature_id", None)
    for m in members:
        if m is canonical:
            continue
        if not (_is_shell_husk(m) or _is_fold_husk(m)):
            return None  # a second real (non-husk) member — genuine facet/twin
        pf = getattr(m, "product_feature_id", None)
        if pf is not None and pf != real_pf:
            return None  # husk homed to a DIFFERENT pf — hold the guard
    return canonical, real_pf


def apply_twin_feature_merge(
    features: list[Any], bipartite: Any,
) -> dict[str, Any]:
    """Rung B — merge dup-extraction twin dev features (SAME-PF guarded).

    For each collision-suffix family (``X`` present + ≥1 ``X-N``) whose members
    ALL share ONE non-None ``product_feature_id`` and whose base ``X`` is a
    REAL feature (not a husk):

      * a fold-husk sibling → absorbed (paths only);
      * a real sibling with ``jaccard(canonical.paths, sib.paths) ≥ θ`` →
        merged (paths + flows unioned);
      * a real sibling below θ → LEFT SEPARATE (a genuine disjoint facet —
        the 21-facet anti-case).

    After each family's absorptions the canonical's flows are deduped by
    ``(name, entry file:line)`` (same entry → true duplicate collapsed; DIFF
    entry → both survive for Rung D). ``features`` is mutated in place and the
    bipartite store re-projected. Runs post-6.86 mint / pre-6.7 UF rollup so
    the journey layer forms over the deduped set (conservation: the PF map is
    unchanged — both twins already homed on ONE PF).
    """
    tele: dict[str, Any] = {
        "features_before": len(features),
        "families_scanned": 0,
        "families_multipf_skipped": 0,
        "families_husk_only_skipped": 0,
        "features_merged": 0,
        "husks_absorbed": 0,
        "facets_kept_separate": 0,
        "flows_deduped": 0,
        "merges": [],
    }
    # The rescue counter is added to the telemetry ONLY when the flag arms it:
    # ``normalize_scan`` does NOT scrub per-stage counters, so a bare ``:0``
    # would leak into the digest and break the OFF==main byte-identity on any
    # board whose standard Rung B emits ``scan_meta.twin_feature_merge``.
    husk_canonical_on = twin_husk_canonical_enabled()
    if husk_canonical_on:
        tele["husk_canonical_rescued"] = 0
    by_name = {f.name: f for f in features}
    families: dict[str, list[Any]] = defaultdict(list)
    for f in features:
        m = _SUFFIX_RE.match(f.name or "")
        base = m.group("base") if m else f.name
        families[base].append(f)

    absorbed_ids: set[int] = set()
    for base, members in families.items():
        has_suffixed = any(
            _SUFFIX_RE.match(m.name or "")
            and _suffix_ordinal(m.name) >= 2
            for m in members
        )
        if len(members) < 2 or not has_suffixed:
            continue
        if base not in by_name:
            continue  # base X absent → the suffix may be intentional (v2, http2)
        tele["families_scanned"] += 1
        # SAME-PF guard — the new safety signal. Multi-PF or None-PF families
        # are anti-cases (256 multi-PF twin groups incl. 29 MULTIPF_OVERLAP);
        # never merged UNLESS the husk-canonical rescue below applies.
        pf_ids = {getattr(m, "product_feature_id", None) for m in members}
        rename_to: str | None = None
        if len(pf_ids) != 1 or None in pf_ids:
            # Husk-canonical rescue (WYSTAN_TWIN_HUSK_CANONICAL, default
            # OFF): the base X is a SHELL husk (pf=None, lost the 6.86 anchor
            # competition to its live twin, which then took a -N suffix), so
            # None ∈ pf_ids skips this family FOREVER. When EXACTLY ONE real
            # (non-husk) member carries a non-None pf, that sibling IS the true
            # feature: promote it to canonical, absorb the husk base (+ same-pf
            # fold-husk siblings), and free the base name so the -N suffix
            # disappears. ≥2 real-pf members / a husk homed elsewhere ⇒ genuine
            # cross-PF ambiguity: the guard STILL holds (skip). Flag OFF ⇒
            # rescue is None ⇒ ``continue`` exactly as before (byte-identical).
            rescue = (
                _resolve_husk_canonical(members)
                if husk_canonical_on else None
            )
            if rescue is None:
                tele["families_multipf_skipped"] += 1
                continue
            canonical, merge_pf = rescue
            if canonical.name != base:
                rename_to = base  # canonical is the suffixed sibling → take base
            tele["husk_canonical_rescued"] += 1
        else:
            merge_pf = next(iter(pf_ids))
            canonical = by_name[base]
            if _is_fold_husk(canonical):
                # Husk-only family (no real canonical — B85 residue). Out of
                # B92 scope; leave untouched (twenty ``components``, cal.com
                # ``libraries``, tracecat ``executor``).
                tele["families_husk_only_skipped"] += 1
                continue
        sibs = sorted(
            (m for m in members if m is not canonical),
            key=lambda m: _suffix_ordinal(m.name),
        )
        absorbed_here: list[str] = []
        for sib in sibs:
            # A shell husk only ever appears in a rescue family (it carries
            # pf=None, impossible in a SAME-PF family) — so ``or
            # _is_shell_husk`` is inert on the standard path (byte-identical).
            if _is_fold_husk(sib) or _is_shell_husk(sib):
                _absorb_husk(canonical, sib)
                absorbed_ids.add(id(sib))
                absorbed_here.append(sib.name)
                tele["husks_absorbed"] += 1
            elif _jaccard(canonical.paths, sib.paths) >= _OVERLAP_JACCARD:
                _absorb_feature(canonical, sib)
                absorbed_ids.add(id(sib))
                absorbed_here.append(sib.name)
                tele["features_merged"] += 1
            else:
                tele["facets_kept_separate"] += 1
        if absorbed_here:
            before = len(canonical.flows)
            _dedup_identical_flows([canonical])
            tele["flows_deduped"] += before - len(canonical.flows)
            if rename_to is not None:
                # Fix-D suffix hygiene: the absorbed shell husk freed the base
                # name; the canonical takes it (deterministic). Mirror the name
                # onto the display channel iff it still shows the raw suffixed
                # slug (leave an author-set display label alone).
                old_name = canonical.name
                canonical.name = rename_to
                if (not canonical.display_name
                        or canonical.display_name == old_name):
                    canonical.display_name = rename_to
            tele["merges"].append({
                "canonical": base,
                "absorbed": absorbed_here,
                "pf": merge_pf,
            })

    if not absorbed_ids:
        tele["features_after"] = len(features)
        return tele

    features[:] = [f for f in features if id(f) not in absorbed_ids]
    tele["features_after"] = len(features)
    _reproject_bipartite(features, bipartite)
    return tele


# ── B89 sentinel — PF with same-named flows (the twin-collision class) ──


def pf_dup_flow_names(
    features: list[Any], flows: list[Any],
) -> list[str]:
    """Every product feature that STILL holds ≥2 flows sharing a name — the
    twin-collision class at its board grain. Exhibit id = ``"<pf>::<name>"``.

    Mirrors the external ``product_right_gate.dup_name_within_pf`` matcher
    1:1 (``feat_to_pf[flow.primary_feature]`` × ``flow.name``), so the hook is
    the in-engine sentinel of the exact operator-gate predicate. Fired ONLY
    when a B92 arm is on (own registry key) — the residual after Rung D/B:
    silent (0) when the fix holds, fires on a kill-switched / regressed arm.
    """
    feat_to_pf = {
        f.name: getattr(f, "product_feature_id", None) for f in features
    }
    counts: dict[tuple[Any, str], int] = defaultdict(int)
    for fl in flows:
        pid = feat_to_pf.get(getattr(fl, "primary_feature", None))
        if pid is None:
            continue
        counts[(pid, getattr(fl, "name", "") or "")] += 1
    return sorted(
        f"{pid}::{name}" for (pid, name), c in counts.items() if c >= 2
    )
