"""Top-level scan-result cache — full-pipeline reproducibility short-circuit.

Why this exists
=``temperature=0`` on Anthropic is **not** bit-exact: the same prompt can
produce a slightly different completion run-to-run. Several LLM stages of
``pipeline_v2`` (Stage 3 flow detection, the 6.7b/6.7c user-flow stages,
and the Stage 8 product clusterer) are therefore non-deterministic across
runs even on an *unchanged* repo — a "fresh" re-scan of fastapi drifts
(48 vs 53 user-flows, 14 vs 16 product-features) although the deterministic
Layer 1 developer features are identical.

Rather than cache every LLM stage individually, this module caches the
**final FeatureMap** keyed on everything that determines it:

  * **repo content identity** — ``git rev-parse HEAD`` plus a hash of any
    dirty/uncommitted state (``git status --porcelain=v1`` + the diff of
    modified tracked files). A clean checkout at commit *X* hashes to *X*;
    a dirty tree hashes distinctly. Non-git dirs fall back to hashing the
    tree's source files.
  * **engine version** — pyproject / installed-distribution version.
  * **scan config signature** — model, days, subpath, max_tree_depth,
    llm_reconcile, feature_history, and the Stage-6.7d abstraction flags.
    Everything that changes output; NOTHING that varies per run
    (``run_id``, timestamps, output path, org/thread identity, cost).

Same ``(repo-state, engine-version, config)`` → the orchestrator replays
the **byte-identical** stored FeatureMap ($0, instant) and skips the whole
pipeline. Because the key excludes per-run values, it is a deterministic
reproducibility cache — not per-repo memory — and is ``rule-cold-scan`` safe.

Design contract
========  * **Opt-in.** ``WYSTAN_SCAN_CACHE`` (default OFF). When off, the
    orchestrator never takes the cache path and behaviour is byte-identical
    to today.
  * **Bypass.** ``WYSTAN_SCAN_CACHE_BYPASS=1`` forces a fresh scan (skip
    the HIT read) while STILL storing the fresh result — a cheap "refresh".
  * **Byte-exact.** We store and replay the *raw bytes* of the written
    FeatureMap file, never a re-serialised dict, so a HIT reproduces run A
    exactly (including run A's ``scan_meta`` timestamps).
  * **Robust.** Every read/write fault is swallowed (log + fall through to a
    normal scan). A corrupt / unparseable / partial entry is treated as a
    MISS. Writes are atomic (temp file + ``os.replace``) so a crashed write
    never leaves a partial entry that could be served. NEVER crashes a scan.

No LLM. No network. Pure local-disk + git.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from wystan.cache.backend import CacheKind, _safe_component
from wystan.cache.paths import wystan_base_dir

logger = logging.getLogger(__name__)

#: Opt-in gate. Empty / ``"0"`` → cache disabled (default). Any other value
#: (typically ``"1"``) → enabled.
ENV_ENABLE = "WYSTAN_SCAN_CACHE"
#: Force a fresh scan: skip the HIT read but STILL store the result.
ENV_BYPASS = "WYSTAN_SCAN_CACHE_BYPASS"
#: Stage-6.7d abstraction env flags — output-affecting, so part of the key.
ENV_6_7D_ABSTRACTION = "WYSTAN_STAGE_6_7D_LLM_ABSTRACTION"
ENV_6_7D_ABSTRACTION_MODEL = "WYSTAN_STAGE_6_7D_ABSTRACTION_MODEL"

# Every env flag that gates a pipeline stage on/off and thus materially changes
# product_features[] / user_flows[]. Any of these toggled between two scans of
# the same tree MUST miss the cache (audit Bug 2 — else a toggle-and-rescan, the
# exact eval workflow the stale-cache rule forbids, serves a stale result). We
# store the RAW env value for each (unset vs "0" vs "1" all distinct) — safe
# over-invalidation beats a stale serve.
ENV_OUTPUT_FLAGS = (
    "WYSTAN_SEED_SYSTEM_UFS",
    "WYSTAN_STAGE_6_3_MEMBER_BACKFILL",
    "WYSTAN_STAGE_8_6_NONSOURCE_DROP",
    "WYSTAN_STAGE_8_6_5_SCAFFOLD_FILTER",
    "WYSTAN_STAGE_8_6_7_DI_ATTRIBUTION",
    "WYSTAN_STAGE_8_7_DESINK",
    "WYSTAN_STAGE_8_8_SHARED_MEMBERS",
    "WYSTAN_STAGE_8_9_SUBDECOMPOSE",
    "WYSTAN_PF_ANCHOR_NAME_GUARD",
    "WYSTAN_STAGE_8_9_5_LLM_COMPONENT_SPLIT",
    "WYSTAN_STAGE_6_7D_PF_UF_BACKSTOP",
    "WYSTAN_STAGE_6_7D_RESIDUAL_GUARD",
    "WYSTAN_STAGE_6_7D_UF_RESHARE",
    "WYSTAN_STAGE_6_7D_SHELL_ABSORB",
    # Wave 3 — naming contract + keeper + personas (§4.7/§4.8): each
    # shapes the emitted display layer / surface lanes, so cached scan
    # results must key on them like every other output-shaping flag.
    "WYSTAN_NAMING_CONTRACT",
    "WYSTAN_KEEPER",
    "WYSTAN_PERSONA_LABELER",
    "WYSTAN_PERSONA_LABELER_MODEL",
    "WYSTAN_PERSONA_ADJUDICATOR",
    "WYSTAN_PERSONA_VERIFIER",
    "WYSTAN_PERSONA_ESCALATION_MODEL",
    # Wave 5 — journey lattice (catch-all partition + subset-dup merge):
    # reshapes the emitted user_flows[] layer.
    "WYSTAN_JOURNEY_LATTICE",
    # Wave 5.1 — lattice thin-child fold-back + LOC-worthy PF backstop:
    # both reshape the emitted user_flows[] layer.
    "WYSTAN_LATTICE_THIN_FOLD",
    "WYSTAN_LOC_WORTHY_BACKSTOP",
    # B4 (2026-07-08) — synthesized-journey quality: demotes member-less
    # system_flow_recall seeds out of user_flows[] and regrounds single-member
    # backstop journey names. Reshapes the emitted user_flows[] layer.
    "WYSTAN_SYNTH_QUALITY",
    # B13 (2026-07-09) — backstop own-entry cover: the synthesize arm bundles
    # only own-entry flows (else a member-less seed) and every member-less
    # I8-cover seed carries an honest coverage-marker name + flag. Reshapes
    # the emitted user_flows[] layer.
    "WYSTAN_BACKSTOP_OWNED_COVER",
    # NS-D / fixb129 (2026-08-08) — the backstop's re-claim fallback may not
    # take member flows already held by a REAL journey under an EARNED
    # name_confidence="high" name (authored word is sacred); such a PF gets
    # the member-less honest coverage seed instead. Reshapes user_flows[]
    # membership on boards where synth rows cannibalised authored journeys.
    "WYSTAN_BACKSTOP_HIGH_OWNERSHIP",
    # fixb129 addendum (2026-08-08, C2-verb probe) — DEFAULT OFF, awaiting an
    # operator ruling: a row Law B NARROWED ('Create X' over read-only
    # members -> 'Browse X', the verb taken FROM the member families) is
    # scored by the ordinary Law C rubric instead of a hard low +
    # ['missing:verb'] stamp that contradicted the surviving name. Arming it
    # overturns the banked NARROWED-FLOOR doctrine (b57 floors + R0/fixb106
    # jsonhero UF-004 / novu UF-056 "demotes honestly"), so it ships armed
    # and measured rather than flipped. Reshapes user_flows[].name_confidence
    # / .name_evidence when ON.
    "WYSTAN_NARROWED_NORMAL_RUBRIC",
    # fixb142 Part 2 — DEFAULT **ON** (flip-pack #42, 2026-08-11,
    # KEY_SCHEMA 77). Makes the rubric above reachable from the NON-primary
    # Law C seams (postmint_uf_rescore / 6.7e), where it was scoped out by
    # fixb130 item (6) and where the FINAL grade is actually written —
    # seven world rows sat frozen on the contradicted hard stamp from KS66
    # to KS75 because of it. Pairs the rubric with a no-climb ceiling so
    # the demote channel stays open — a narrowed row falls at least one
    # step, and only the REASON changes. Proof: jsonhero-web UF-004 flips
    # low['missing:verb'] -> low['missing:resource'] (true reason, no
    # uplift); serialized-board A/B on 4 boards shows no row appearing or
    # disappearing. ``=0`` is the kill-switch forever.
    # Reshapes user_flows[].name_confidence / .name_evidence.
    "WYSTAN_NARROWED_RUBRIC_RESCORE",
    # fixb142 Part 1 (2026-08-11) — DEFAULT OFF. Composite-head repair on
    # the DISPLAY channel: a journey named '<V1> and <V2> <resource>' whose
    # LEAD family no member witnesses drops its unwitnessed conjuncts
    # ('Create and edit analytics' -> 'Edit analytics'). Reshapes
    # user_flows[].name (and, downstream of Law C, .name_confidence /
    # .name_evidence) when ON.
    "WYSTAN_UF_COMPOSITE_HEAD_REPAIR",
    # fixb142 Part 3 (2026-08-11) — DEFAULT OFF. The naming vocab's
    # flow_verb_classes table as one more OR-source to Law C's
    # verb_grounded, over the same member lead-token channel base_verb
    # already reads. Reshapes user_flows[].name_confidence / .name_evidence.
    "WYSTAN_UF_FLOW_VERB_CLASS",
    # B15 (2026-07-09) — shared-leaf role consistency: high-cross-PF-fan-in,
    # no-surface, already-shared member files are forced role="shared"
    # everywhere. Reshapes member_files[].role (the I23 anchor-body view).
    "WYSTAN_SHARED_LEAF_CONSISTENCY",
    # B15b (2026-07-09) — data-file shared-leaf rail: large pure-data blobs
    # (locale packs) consumed by >=2 PFs, no surface, are forced role="shared".
    # Reshapes member_files[].role.
    "WYSTAN_DATA_LEAF",
    # B16 (2026-07-10) — PF dev-grain suffix law: a route-dir-naming leak
    # ('policy-page' -> 'Policy Page') is stripped to the capability
    # ('Policy') at the display channel. Reshapes product_features[].display_name.
    "WYSTAN_PF_NAME_LAW",
    # B16 Part 1b (2026-07-10) — UF-level dev-grain suffix law: strips
    # "View detections page" -> "View detections". Reshapes user_flows[].name.
    "WYSTAN_UF_DEVGRAIN_NAME",
    # B16 Part 2 (2026-07-10) — sibling-anchor unification: co-identity sibling
    # route PFs (investigation / investigations-page / investigation-flow)
    # collapse to one. Reshapes product_features[] + developer/user-flow
    # product_feature_id links.
    "WYSTAN_PF_SIBLING_UNIFY",
    # B19 (2026-07-10) — transport-package lane: a ws-package named after its
    # own external dependency family (packages/trpc -> @trpc/*) with no product
    # surface lanes as a technology_instrument. Reshapes product_features[] +
    # the platform_infrastructure lane. (Sibling tech-instrument flags were an
    # unkeyed cache-correctness gap — registering this one per the B4 precedent.)
    "WYSTAN_TECH_TRANSPORT_LANE",
    # B20 (2026-07-10) — path_index-aware I16 journey re-home: a majority-foreign
    # UF re-homes to its strict-majority entry-owner PF. Reshapes
    # user_flows[].product_feature_id.
    "WYSTAN_I16_REHOME_B20",
    # B22a (2026-07-10) — cross-app fold guard: the mint's ancestor-walk rung
    # may not annex a dev across a workspace-unit boundary (documenso trpc
    # annexation). Reshapes developer_features[].product_feature_id +
    # path_index ownership + the platform_infrastructure lane.
    "WYSTAN_FOLD_CROSSAPP_GUARD",
    # B58 (2026-07-13) — container-anchor annexation guard: Seg A fences the
    # mint's entry/span/walk rescue rungs by the target's CANONICAL unit (a
    # unit-coherent flowful dev never force-binds across a workspace unit —
    # plane Issue i18n 125K, cal.com Bookings/apps/api/v2); Seg B bars
    # dev-artifact-UNIT anchors from minting (novu playground Notifications).
    # Reshapes product_features[] + developer_features[].product_feature_id +
    # the platform_infrastructure lane. Appended WITHOUT a KEY_SCHEMA bump —
    # reconciled at merge.
    "WYSTAN_ANNEXATION_GUARD",
    # B58-v2 (2026-07-14) — same-unit domain-dir cap: Seg A extends the
    # B53 drain with donor class 2 (a container-anchor PF sheds member
    # files annexed from SAME-unit foreign domain-dirs whose name
    # echo-matches exactly ONE existing PF; nav-only matches are
    # telemetry, never a move); Seg B adds the page-surface
    # canonical-unit rung to the B58 fence (a multi-unit route anchor
    # resolves to its PAGE unit — plane route:space). Reshapes
    # developer_features[] (carve devs + donor path surgery) +
    # product_features[] member ownership + path_index + downstream
    # user_flows[] homes (I16). Appended WITHOUT a KEY_SCHEMA bump —
    # reconciled at merge.
    "WYSTAN_SAMEUNIT_DOMAIN_CAP",
    # B22 (2026-07-10) — transport-lane journey-conservation handoff (Stage
    # 6.985): the transport prong marks candidates at 6.86 and the handoff
    # re-homes their journeys/devs post-journey-layer before laning the PF
    # (all-or-nothing conservation gate). Reshapes product_features[] +
    # user_flows[].product_feature_id + the platform lane when candidates
    # exist. Sub-flag of the plurality rung keys alongside it.
    "WYSTAN_TRANSPORT_LANE_HANDOFF",
    "WYSTAN_TRANSPORT_HANDOFF_PLURALITY",
    # B23 (2026-07-10) — marker surface coordinates: member-less coverage
    # markers carry their uncovered trigger surface as whole-file spans
    # (user_flows[].surface_files, honest loc>0 via 6.97b) and Track-C e2e
    # markers keep their maintainer-authored labels instead of the
    # 'Uncovered: <PF> routes' rename. Reshapes the emitted user_flows[]
    # layer. Sub-flag of WYSTAN_BACKSTOP_OWNED_COVER (lock-step: spans
    # exist only where the B13 marker flag exists).
    "WYSTAN_MARKER_SURFACE_COORDS",
    # B24 (2026-07-10) — Stage 6.986 mega-PF nav-area re-home + floor-gated
    # mint: a board-dominating umbrella PF's journeys re-home onto their
    # nav-area sibling PFs (attach-floor / all-rung-I16-rail gated) and an
    # above-floor area with no sibling mints its own PF (supabase
    # 'projects' -> 'database'). Reshapes user_flows[].product_feature_id
    # + product_features[] + developer_features[] carve chunks. Default
    # OFF.
    "WYSTAN_MEGA_PF_NAV_REHOME",
    # B26 (2026-07-10) — hub plumbing child: the dir-per-vendor child
    # filter tests the segment against the plumbing/stop vocabularies
    # NORMALIZED (underscore-stripped, singularized; vendor-beats-
    # plumbing guard), and the 6.86 mint bar backstops with
    # ``hub_plumbing_child`` — a shared-helper dir inside a connector hub
    # (cal.com ``app-store/_utils``) never mints a PF; its devs fold to
    # the enclosing package / hub core. Reshapes product_features[] +
    # developer_features[].product_feature_id on affected repos.
    "WYSTAN_HUB_PLUMBING_CHILD",
    # B27 (2026-07-10) — package-manifest PF display names: a package-dir-
    # anchored PF (hub:-vendor / ws:) takes its display from the package's
    # OWN declared metadata (config.json "name" / metadata-module name /
    # package.json displayName / authored name), with a mechanical
    # letter/digit word-split of the dir slug as the rung below. Reshapes
    # product_features[].display_name (+ the UF display templates derived
    # from it).
    "WYSTAN_PF_MANIFEST_NAME",
    # B30 (2026-07-10) — deterministic verb+resource flow naming: route-slug
    # path-echo flow names (``api-account-passkeys-flow``) are renamed to
    # verb+resource (``manage-account-passkeys-flow``) at the very end of the
    # finalize phase. Reshapes flows[].name/display_name/short_label (the
    # operator-visible name channel). Default ON.
    "WYSTAN_FLOW_NAME_V2",
    # B31 (2026-07-10) — distinct recall-row display names: every synthesized
    # recall row (e2e / route-group / backstop) in a display-name collision
    # group is re-derived from its own (authored label | intent+resource |
    # route-terminal) evidence at Stage 6.98 — per-board uniqueness by
    # construction. Reshapes user_flows[].name.
    "WYSTAN_RECALL_ROW_NAMES",
    # B34 (2026-07-10) — lazy-import edges (Tier 1, artifact side-channel)
    # + dispatch-registry system-flow seeds (Tier 2, appends flows[] rows
    # for uncovered string-dispatched connectors). Tier 2 reshapes
    # flows[] / developer_features[].flows[] and, transitively, the UF
    # recall layer (flowless-PF markers dissolve). Both default OFF.
    "WYSTAN_LAZY_IMPORT_EDGES",
    "WYSTAN_DISPATCH_REGISTRY_FLOWS",
    # B28 (2026-07-10) — non-product app scope (Shape E lane + S1g types-only
    # prong; journeys ride to non_product_surfaces). Default ON.
    "WYSTAN_NONPRODUCT_SCOPE",
    # B28 (2026-07-10) — Shape D docs re-anchor (majority-dir election).
    # Reshapes product_features[].anchor_id only. Default ON.
    "WYSTAN_DOCS_REANCHOR",
    # B25 (2026-07-10) — journey-lattice verifier-revert slot release: a pf
    # whose split plan the Draft Verifier fully reverted re-runs the
    # Phase-2b action detection once (one extra verifier batch, hard-capped
    # at one release per pf per scan). Reshapes the emitted user_flows[]
    # layer on keyed scans (keyless is unreachable — no verifier, no
    # reverts).
    "WYSTAN_JOURNEY_LATTICE_B25",
    # B38 (2026-07-11) — marker coordinate integrity: member-less coverage
    # markers with zero attached surface spans are suppressed from
    # user_flows[] (gap claims with no evidence; wave15 breach cal.com 20 /
    # midday 1 / typebot 1). Default OFF. Appended WITHOUT a KEY_SCHEMA
    # bump per wave convention — reconciled at merge.
    "WYSTAN_MARKER_COORDS_REQUIRED",
    # B41 (2026-07-11) — pages-surface named-export fallback: react-router
    # trees under src/pages with NAMED-export components get real
    # (symbol, line) anchors instead of symbol-less hollow seeds (novu:
    # 54% of flows hollow). Default ON; inert on Next trees (default
    # exports always match first). Appended WITHOUT a KEY_SCHEMA bump —
    # reconciled at merge.
    "WYSTAN_PAGES_NAMED_EXPORT_FALLBACK",
    # B43 (2026-07-11) — routed-seed anchor completeness: HOC default
    # exports unwrap to the page component; range-less symbols anchor at
    # the extractor 'default' range, else line 1 — hollow page seeds
    # (supabase keyless 91) get real anchors. Default ON. Appended
    # WITHOUT a KEY_SCHEMA bump — reconciled at merge.
    "WYSTAN_PAGES_ANCHOR_FALLBACK",
    # B33 v2 (2026-07-11) — post-UF devgrain-leaf demote (Stage 6.987): a
    # route:/fdir:-anchored PF whose leaf normalizes to a plumbing/
    # journey-step token (welcome, getting-started, access-denied,
    # redirect-*, *-callback, *-onboarding), is NOT nav-declared, and whose
    # final journey profile is micro (<=2 UFs, member_count <=3) demotes —
    # PF row removed, micro-UFs dropped, devs re-pointed to the nearest
    # surviving ancestor. Rich journey sets veto (conservation); board-wide
    # abstain when the nav parse is unreadable. Reshapes product_features[]
    # + user_flows[] + developer_features[].product_feature_id on affected
    # repos. Default ON (flipped 2026-07-12 after the keyed proof on
    # papermark — Welcome demoted, I9=0 via the B37-ph2 homing rider,
    # platform lane 43->42; KEY_SCHEMA v28, coupled with
    # WYSTAN_DISPATCH_HOMING_B37P2 — without the rider the demote
    # re-creates I9). =0 restores the pre-B33 board byte-identically.
    "WYSTAN_FDIR_DEVGRAIN_GATE",
    # B45 (2026-07-11) — coverage_gaps[] gap channel: member-less I8-cover
    # markers leave user_flows[] for a dedicated top-level ``coverage_gaps``
    # array. Default FULL (flipped 2026-07-12 after the keyed proof on
    # papermark + cal.com; KEY_SCHEMA v27): unset = gaps emitted and the
    # marker rows REMOVED from user_flows[]; dual = gaps emitted AND the
    # marker rows stay (bijection instrument); explicit off ("off"/"0"/
    # "false") restores the pre-B45 byte-identical output (key absent).
    # Reshapes user_flows[] (full) + adds the coverage_gaps[] key (dual/full).
    "WYSTAN_COVERAGE_GAP_CHANNEL",
    # B40 (2026-07-11) — provenance-graded name_confidence + name_evidence[]
    # audit trail. Arms the nav / registry / structural-route rungs in Law C
    # and the singular-folded multi-member agreement in synth_quality; stamps
    # UserFlow.name_evidence. Default ON (flipped 2026-07-12 after the keyed
    # proof on papermark + cal.com; KEY_SCHEMA v27): may raise name_confidence
    # and adds name_evidence[] — UF NAMES stay byte-stable either way. =0
    # restores the pre-B40 rubric + serialized output byte-identically
    # (name_evidence key absent).
    "WYSTAN_NAME_EVIDENCE_RUNGS",
    # B46 (2026-07-11) — UF-name hygiene: kills the garbage-name sources —
    # the doubled route/file-stem token concat ('settings accounts settings
    # accounts', root in flow_name_v2._resource_tokens), the GLUED plain-slug
    # seed echo on the UF-label side, the bare pluralized dir-stem leaf on an
    # ungrounded 'other'-intent slot ('onboardings' -> 'Manage onboarding'),
    # and an inherited Stage-5.5 ordinal on a UF label ('… action 3').
    # Default ON (flipped 2026-07-12 after the keyed proof on papermark +
    # cal.com; KEY_SCHEMA v27): reshapes flow.name (concat root) +
    # user_flows[].name (garbage rows only). =0 restores the pre-B46 flow/UF
    # names byte-identically.
    "WYSTAN_UF_NAME_HYGIENE",
    # B37-ph2 (2026-07-12) — dispatch-mint homing: a predominantly-dispatch
    # user flow re-homes to the PF that OWNS the mint's target file
    # (path_index dev→PF first — the i16 ruler — anchor-chain fallback for
    # unowned targets; never the dev-of-first-attribution), AFTER the final
    # path_index refresh + flowless-PF backstops and BEFORE the
    # synth_quality gap arbitration; the same target-owner machinery homes
    # a demoted PF's FLOWFUL devs in the Stage 6.987 devgrain I9 rider
    # (flowful → owner, never the platform lane). Reshapes
    # user_flows[].product_feature_id (+ developer_features[].
    # product_feature_id under the devgrain gate). Default ON (flipped
    # 2026-07-12, coupled with WYSTAN_FDIR_DEVGRAIN_GATE; keyed papermark
    # proof I9=0 + keyless byte-identical no-op supabase/midday; KEY_SCHEMA
    # v28). =0 restores the pre-B37-ph2 homes byte-identically.
    "WYSTAN_DISPATCH_HOMING_B37P2",
    # B47 Arm B (2026-07-12) — keyless journey recall: attaches route-matched
    # LIVE flows as members to a groundable e2e orphan journey, graduating it
    # from a member-less coverage_gaps[] marker to a real member-ful journey
    # (name = authored_label; name_confidence low→medium on route grounding).
    # Honest-gap law: an orphan with no covering flow stays member-less.
    # Default OFF; when ON reshapes user_flows[] (member_flow_ids/member_count
    # /name_confidence on e2e_journey_recall rows) + removes those rows from
    # coverage_gaps[]. =0/unset restores byte-identical output. No KEY_SCHEMA
    # bump (flip is a separate later commit per flip-protocol).
    "WYSTAN_KEYLESS_JOURNEY_RECALL",
    # B44 (2026-07-12) — Stage-3 keyless surface blind spot, part 1: a
    # React-Router-framework / Remix workspace (``react-router.config.*`` +
    # ``app/routes/**``, the Remix successor stack) is route-EXTRACTED
    # (routes_index populated) but wins the DefaultProfile, which emits no
    # ``flow_entries`` — so its live routes never seed keyless flows
    # (documenso apps/remix: 121 routes, 0 flows). Registers a deterministic
    # ``react-router-fw`` profile that seeds one flow per ``app/routes/**``
    # entry (default-export symbol → real (file,line) anchor, B41/B43 chain).
    # Default OFF; when ON a react-router-framework unit re-homes from
    # ``default`` to ``react-router-fw`` (composite name gains the arm) and
    # its route files seed flows (feeds the B47 arm-B e2e-orphan bridge).
    # =0/unset leaves the profile unregistered → byte-identical. No
    # KEY_SCHEMA bump (flip is a separate later commit per flip-protocol).
    "WYSTAN_REACT_ROUTER_FW_PROFILE",
    # B44 (2026-07-12) — Stage-3 keyless surface blind spot, part 2: the
    # react-router-SPA extractor resolves ``@/`` / ``~/`` import aliases only
    # against a hard-coded ``src/`` root, so a Vite SPA that maps ``~/`` →
    # ``app/`` (tsconfig ``paths`` / vite ``resolve.alias``) resolves NO
    # mounted page components → 0 route buckets → empty board (outline:
    # ``~/*`` → ``./app/*``, react-router in ``app/routes/*``, 0 PF/UF/flows).
    # When ON the SPA index reads the workspace's real alias map from
    # ``tsconfig.json`` ``compilerOptions.paths`` and resolves aliases against
    # their true roots, AND the SPA extractor stamps ``AnchorCandidate.routes``
    # so its branches populate ``routes_index``. =0/unset restores the
    # ``src/``-only resolution + route-less anchors byte-identically. No
    # KEY_SCHEMA bump.
    "WYSTAN_ROUTER_ALIAS_RESOLVE",
    # B48 (2026-07-12) — ws-library / name-dep transport lane: a
    # broadly-imported zero-surface (no route/page, not nav-confirmed)
    # ws-package that imports <=1 in-repo unit (S2 library) OR is named
    # after its own external dependency family (S1 name-dep transport)
    # lanes as a technology instrument — the corroboration-free extension
    # of the S2 prong (compound/generic names: twenty-ui, novu dal/
    # framework, documenso/cal.com trpc). Rides the B19/B22
    # transport-handoff channel for journey conservation (never mint-time
    # laning). Reshapes product_features[] (laned rows leave) +
    # user_flows[].product_feature_id (re-homed journeys) + the platform
    # lane when candidates exist. Default OFF; =0/unset byte-identical.
    # No KEY_SCHEMA bump (flip is a separate later commit per flip-protocol).
    "WYSTAN_WS_LIBRARY_LANE",
    # B50 Seg1-2 (2026-07-12) — UF/PF display de-grime: kills adjacent-token
    # echoes ('Ingest ingest', 'case case ids', 'chat chatids') and glyph-less
    # route-param leaks ('teamurl documents', PF 'URL') at the display JOINER.
    # DISPLAY-ONLY (uf.name / pf.display_name); identity / membership /
    # product_feature_id / paths / cluster keys / the resource field / lineage
    # untouched. Default OFF; =0/unset ⇒ serialized output byte-identical. No
    # KEY_SCHEMA bump (flip is a separate later commit per flip-protocol).
    "WYSTAN_UF_NAME_DEGRIME",
    # B50 Seg3 (2026-07-12) — earned resource rung: a low UF carrying
    # missing:resource (verb grounded) earns resource-grounding ONLY from a
    # real evidence rung (member-file domain noun / param-free route segment /
    # mapped test-file noun), each stamping a distinct name_evidence entry.
    # Adds OR-sources to Law C's res_grounded (bar UNCHANGED, no lowered
    # threshold, never invents missing:verb grounding). CONFIDENCE channel
    # only. Default OFF; =0/unset ⇒ confidence + serialized output
    # byte-identical. No KEY_SCHEMA bump (flip is a separate later commit).
    "WYSTAN_UF_RESOURCE_RUNG",
    # B49 (2026-07-12) — transport namespace-echo (r2.6 rung): an in-lane
    # tRPC router seed that abstains at r2 (typed-proxy consumption → no
    # product consumers → zero_product_votes) votes its span mass for the
    # EXISTING product PF whose anchor-identity its namespace token echoes
    # (``normalize_anchor_key`` — the same normalization as the S3-nav
    # echo: ``apiKeys`` → ``api-key`` → the ``API Keys`` PF). Unique match
    # only; ambiguous / generic (``viewer``/``utils``) abstains; NEVER
    # mints (re-homes onto existing PFs only, conservation judge
    # untouched). Reshapes user_flows[].product_feature_id + which
    # transport candidates clear the all-or-nothing gate to lane. Default
    # OFF; =0/unset byte-identical. No KEY_SCHEMA bump (flip is a separate
    # later commit per flip-protocol).
    "WYSTAN_TRANSPORT_NAMESPACE_ECHO",
    # B51 (2026-07-13) — transport router-mega decomposition: a FLOW-BEARING
    # transport candidate (a dev whose flows I9 forbids laning — cal.com
    # `trpc`: 66 flows) is decomposed per tRPC sub-router. Each sub-router
    # group whose namespace token echoes an EXISTING product PF (the SAME
    # `NamespaceEcho` matcher as r2.6: eventTypes→`event-types`,
    # apiKeys→`api-keys`, webhook→`webhooks`) has its flows + routers-tree
    # files carved into a product-owned chunk re-homed to that PF (I22
    # marker), BEFORE the conservation gate; the carved files are LIFTED out
    # of the lane so the existing r1 ladder drains their journeys (no new
    # rung). Residue (unmatched sub-routers + non-routers `[trpc].ts`
    # handler / middleware flows) stays flowful and keeps a REDUCED tile —
    # an honest abstain, never forced onto a product surface. Conserves
    # flows/journeys (moved, never dropped or minted). Reshapes
    # developer_features[] (carved chunks) + product_features[] (a fully
    # drained candidate lanes) + user_flows[].product_feature_id (drained
    # journeys). Default OFF; =0/unset byte-identical. No KEY_SCHEMA bump
    # (flip is a separate later commit per flip-protocol).
    "WYSTAN_TRANSPORT_ROUTER_DECOMP",
    # B52 (2026-07-13) — flow-bearing transport lane (Option A; the operator
    # 'trpc A' mandate: the trpc tile disappears ENTIRELY). The ONE cycle
    # switch (it also drives the B51 decomposition pass, in drain-then-lane
    # mode + the (c) `api/trpc/<domain>/` handler grain): a ws-anchored
    # transport candidate ALWAYS leaves product_features[]. Matched groups
    # re-home onto EXISTING PFs WITH their journeys (r1 over the post-drain
    # state; a receiver that would end journey-less pulls its carve back —
    # the B51 I8 exhibit's structural fix); the flowful RESIDUE lanes (the
    # validator I9 ws:-anchor exemption, engine-aligned); transport-
    # intrinsic journeys stay in user_flows[] with product_feature_id=None
    # + lane_ref=<lane-row uuid> + surface_scope='platform_infrastructure',
    # and the lane row carries flow_ids[] + journeys[] (additive, non-empty
    # only). Conservation: Σflows == product-homed + lane flow_ids, ΣUF ==
    # product-homed + lane_ref rows — nothing dropped, nothing minted.
    # Reshapes product_features[] / developer_features[] / user_flows[] /
    # platform_infrastructure[]. Default OFF; =0/unset byte-identical. No
    # KEY_SCHEMA bump (flip is a separate later commit per flip-protocol).
    "WYSTAN_FLOWFUL_TRANSPORT_LANE",
    # B53 (2026-07-13) — ws-app blob domain drain. Seg A re-attributes a
    # ws-blob donor's internal domain-dir members (``<pkg>/<container>/
    # <domain>/**``) onto the EXISTING PF whose identity the domain name
    # echoes (same NamespaceEcho matcher; NO mints), moving them at the dev
    # level so Stage 6.97 owned-LOC + the path_index rebuild + Stage 6.99
    # I16 journey re-home follow for free. Seg B lanes dev-artifact ws-
    # packages (docs-content / devDependency-only tooling / scaffolder) off
    # the product layer via the dev_artifact_units channel. ONE flag gates
    # BOTH segments. Reshapes product_features[] membership/LOC +
    # user_flows[].product_feature_id. Default OFF; =0/unset byte-identical.
    # No KEY_SCHEMA bump (flip is a separate later commit per flip-protocol).
    "WYSTAN_WS_BLOB_DOMAIN_DRAIN",
    # B56 (2026-07-13) — full-name display law for abbreviations: a shape-
    # flagged abbreviation display tile ('Pbac', 'Sso', 'Ooo', 'I18n', 'Wp')
    # takes its repo-grounded full form ('Single Sign-On (SSO)', 'Out of
    # Office (OOO)') from an ALLOWED source (code identifiers, i18n KEY names,
    # JSX labels, package manifest, route segments — NEVER locale values, NEVER
    # comments/README); shape-flagged-but-no-evidence keeps its display and is
    # honest debt (missing:expansion, measured not invented). UF names inherit
    # the same expansion. DISPLAY CHANNEL ONLY (product_features[].display_name
    # + user_flows[].name); no identity field moves. Default OFF; =0/unset is
    # byte-identical. No KEY_SCHEMA bump (flip is a separate later commit per
    # flip-protocol).
    "WYSTAN_PF_FULLNAME_LAW",
    # B57 Seg1 (2026-07-13) — Law C rung-source expansion: four additional
    # deterministic evidence sources for the existing resource/verb rungs —
    # (a) nav-cluster (ALL authored nav labels voted onto the owning PF),
    # (b) i18n KEYS referenced in member source files (keys only; translated
    # VALUES are a forbidden source — operator rule 2026-07-13), (c) member
    # routes' declared HTTP method → verb family, (d) assertion labels inside
    # MAPPED member test files. Same Law C bar — extra OR-sources, each with
    # a provenance tag in name_evidence. Reshapes user_flows[].
    # name_confidence / name_evidence only (UF NAMES byte-stable — B40 law).
    # Default OFF; =0/unset byte-identical. No KEY_SCHEMA bump (flip is a
    # separate later commit per flip-protocol).
    "WYSTAN_UF_RUNG_SOURCES_V2",
    # B57 Seg2 (2026-07-13) — Stage 6.7e journey-evidence adjudicator
    # (keyed-only; Sonnet batch): selects non-high UFs + same-PF dup
    # candidates after Law C v1, collects a deterministic evidence package
    # (member files+spans, routes, nav-cluster labels, i18n KEYS — never
    # translated VALUES, neighbors), and applies ONLY deterministically
    # VERIFIED verdicts — rung_evidence (Law C re-score via
    # rescore_uf_confidence; adjudicated:* tags), rename (cited
    # identifier-shaped strings only; B50 degrime + collision-safe chain),
    # merge (identical / strict-subset member sets on the SAME non-None PF;
    # union + lineage), demote (row → typed coverage_gaps[]
    # kind="adjudicated_noise"; never a silent drop). Fake / foreign-file /
    # locale-VALUE citations are rejected. Keyless (no client) ⇒ hard no-op
    # byte-identity. Reshapes user_flows[] (confidence/evidence/names/
    # membership) + coverage_gaps[] on keyed scans. The model env keys
    # alongside (raw value) per the persona-model precedent. Default OFF;
    # =0/unset byte-identical. No KEY_SCHEMA bump (flip is a separate later
    # commit per flip-protocol).
    "WYSTAN_STAGE_6_7E_ADJUDICATOR",
    "WYSTAN_STAGE_6_7E_MODEL",
    # B61 Seg1 (2026-07-13) — evidence-born verb-snap: a deterministic
    # post-pass that REPLACES a UF display's leading verb when its
    # action-family is absent from the member verb-composition (B57
    # member_verb_composition — HTTP-methods / page-kinds), snapping it to
    # the canonical verb of the composition's dominant family (mutation
    # outranks read). The FIRST flag permitted to change a UF NAME; carries
    # its own kill-switch so the B40 UF-NAMES byte-stable law under the
    # rung/adjudicator flags is preserved. Reshapes user_flows[].name (and,
    # via Law C's structural:verb-composition rung, name_confidence/
    # name_evidence). Default OFF; =0/unset byte-identical. No KEY_SCHEMA
    # bump (flip is a separate later commit per flip-protocol).
    "WYSTAN_UF_VERB_SNAP",
    # B59 (2026-07-13) — artifact-ink accounting drain. Stage 6.97 reclassifies
    # a feature's OWNED non-authorial "ink" LOC (locale catalogs / generated
    # schemas / test data / dev seeders) OUT of product ``loc`` into a separate
    # ``artifact_ink_loc`` field + a ``scan_meta.artifact_ink`` lane aggregate,
    # so ``loc`` reads as an HONEST product-code size. ACCOUNTING ONLY —
    # membership / path_index / line coordinates / flows / user_flows are
    # untouched (journeys I15/I16 provably unchanged). Default OFF; =0/unset is
    # byte-identical. Appended WITHOUT a KEY_SCHEMA bump — the bump rides the
    # separate later flip commit only (flip-protocol).
    "WYSTAN_ARTIFACT_INK_LANE",
    # B64 — dynamic-dispatch resolver. Additively resolves (a) lazy dynamic
    # imports (`const X = lazy(() => import("./Y"))`) into the Stage 6.3
    # import-tree traversal so lazily-loaded route sub-trees (outline's
    # `lazy(() => import("./authenticated"))` — ~87% of the product) become
    # reachable; (b) one-level const-folds pure literal-returning route
    # helpers/consts (`draftsPath()` → "/drafts", `{path: ROUTES.home}`) so
    # react-router SPA routes whose path is a helper call/const resolve into
    # routes_index; (c) object/Map registries ({key: Component}) in a
    # route-binding file → one route/import edge per Component. Free vars /
    # conditionals / non-literal returns → honest skip (B63 metric measures
    # the residual). Default ON since flip-pack №8 (2026-07-27, KEY_SCHEMA 41;
    # keyless outline proof — the forgotten-flip: lazy-import route sub-trees
    # [~87% of outline] reachable, dispatch routes born). The bump rode the
    # pack's FIRST flip commit (ROUTE_RENDER_UTIL_DEMOTE). unset ≡ explicit "1"
    # byte-identical; "0"/"false"/"no"/"off" restores the pre-B64 world
    # (inverted kill-switch forever), so cached entries must key on it.
    "WYSTAN_DISPATCH_RESOLVER",
    # B67 — background-job / cron entry extractor. Emits routes_index entries
    # (synthetic JOB/CRON method) for background handlers (@Processor/BullMQ
    # Worker/node-cron TS/JS, celery/APScheduler/rq Python, vercel/actions/k8s
    # manifest-cron) so their flows/journeys mint. Default OFF; =0/unset is
    # byte-identical. Appended WITHOUT a KEY_SCHEMA bump — the bump rides the
    # separate later flip commit only (flip-protocol).
    "WYSTAN_JOBS_ENTRIES",
    # B68 — terminal 4-way classification of the coverage-gap band (Stage
    # 6.995, operator doctrine 2026-07-14: the gap channel is an internal
    # state, never a final board category). Each gap row decomposes BY
    # MEMBERS into (1) not-a-feature e2e/test labels (audit trace, off the
    # board), (2) part-of-existing-PF (NamespaceEcho / live-flow owner —
    # claim dissolves), (3) own-PF worthiness evaluation (records only —
    # member-less mints stay forbidden, B23/B33), (4) dev-infrastructure
    # (existing predicates: dev_artifact_units / instruments / test /
    # generated / artifact-ink / lane / shared-leaf); the ONLY legal
    # residue is (5) a row stamped ``why_unresolved`` naming a known lexer
    # hole (data/terminal-classification.yaml). Reshapes coverage_gaps[]
    # (rows removed / trimmed / stamped) + scan_meta. Default ON since the
    # 2026-07-16 horizon-1 flip (KEY_SCHEMA 30; keyed proof documenso + plane
    # green, B68 — gap rows typed, zero unmapped-silence). ``=0``/false/off
    # restores the pre-B68 byte-identical board (kill-switch).
    "WYSTAN_TERMINAL_CLASSIFICATION",
    # B69-v2 (2026-07-15) — PF-homing hygiene family, FINAL composition
    # (re-convoy ruling): Stage 6.99b post-UF rehome rail (anchor-breadth
    # ruler; rename-on-rehome for synthesized rows; fold-into-existing;
    # home-tie guards) + B31 pf-display echo-guard + 6.7e Law-A telemetry
    # preservation. Reshapes user_flows[] homes/names + scan_meta
    # telemetry. Default ON since the 2026-07-16 horizon-1 flip (KEY_SCHEMA
    # 30; keyed proof papermark + cal green, B69-v2 — pm churn=1 fold, cal
    # no-op). ``=0`` restores the pre-B69-v2 byte-identical board
    # (kill-switch). Read in TWO modules (naming_contract + stage_6_86); both
    # defaults flip in lock-step.
    "WYSTAN_HOMING_HYGIENE",
    # B69-v2 SPLIT ruling (2026-07-15) — seed-birth hygiene pair, banked
    # for its OWN cycle: same-(pf,resource) route-group seed coalescence +
    # method-derived seed intent (route_group_recall). Board-wide blast
    # radius at seeding (the keyed A/B showed the pair driving churn on
    # both repos while the 6.99b rail was exactly-one-action) — hence its
    # own flag, own seed-grain gates, own keyed A/B. Reshapes user_flows[]
    # (seed rows / names / intents). Default OFF; =0/unset byte-identical.
    # Appended WITHOUT a KEY_SCHEMA bump — flip-protocol.
    "WYSTAN_SEED_HYGIENE",
    # B88 (2026-07-23) — transport-donor seed guard (route_group_recall).
    # A route group that is transport wiring (files wholly under a TRANSPORT-
    # shaped ws-blob donor package — cal.com packages/trpc) never homes a
    # synthetic recall seed onto the donor PF: form 1 resolves it to its
    # DESTINATION domain PF (the drain's matched-dirs echo-match) or an honest
    # skip; form 2 excludes the donor PF from the seed home plurality. Reshapes
    # user_flows[] (seed homes / drops) when armed; every donor-less board is
    # byte-identical (finalize passes transport_resolver=None). Default ON
    # since flip-pack №6 (2026-07-23, KEY_SCHEMA 39; proof: live keyed 32→0 +
    # composition cal_A4 transport_masquerade=0). The bump rode the pack's
    # FIRST flip commit (PRODUCT_RIGHT_GATE). unset ≡ explicit "1"
    # byte-identical; "0"/"false"/"off"/"no" restores the pre-B88 world
    # (inverted kill-switch forever), so cached entries must key on it.
    "WYSTAN_RECALL_TRANSPORT_SKIP",
    # B69-v2 THIRD split (2026-07-15) — the bare-verb/dev-grain-token
    # display law, BANKED for the B70 member-evidence redesign: the
    # vocabulary-driven implementation false-positives on verb-homonym
    # resources ('Manage download', 'Browse webhook') and misses
    # evidence-less tokens ('View mupdf'); each ban cascades into retries/
    # collisions/B31 parentheticals (the keyed pair's entire off-rail
    # churn). B70 member-evidence redesign landed. Reshapes UF display names
    # when armed. Default ON since the 2026-07-16 horizon-1 flip (KEY_SCHEMA
    # 30; keyed proof papermark + cal green, B70 — law-attributed churn, zero
    # bare names). ``=0`` restores the pre-B70 byte-identical law list
    # (kill-switch).
    "WYSTAN_NAMING_LAW",
    # B66 — code-first server API-entry extractor. Emits routes_index entries
    # (real HTTP methods for NestJS/koa/hono; synthetic QUERY/MUTATION/
    # SUBSCRIPTION for GraphQL/tRPC) for decorator-/DSL-routed backends whose
    # URL lives in code, not the filesystem (NestJS controllers, GraphQL
    # code-first resolvers, tRPC procedures, koa/hono routers) so their
    # flows/journeys mint. Default ON since the 2026-07-16 horizon-1 flip
    # (KEY_SCHEMA 30; keyed proof twenty + hoppscotch (meter) + cal (trpc)
    # green, B66 — nestjs/graphql/trpc/koa meter ~0). ``=0``/false/off keeps
    # the extractor inert AND unregistered, byte-identical to pre-B66
    # (kill-switch).
    "WYSTAN_SERVER_API_ENTRIES",
    # B70 (2026-07-15) — capitalize the B31 route-terminal parenthetical
    # qualifier ('Manage links (general)' -> '(General)') so it matches the
    # proper-cased PF-display qualifier on the same recall row. The B31
    # recall-row naming (WYSTAN_RECALL_ROW_NAMES) is itself default ON, so
    # this display-casing fix is gated separately. Default ON since the
    # 2026-07-16 horizon-1 flip (KEY_SCHEMA 30; keyed proof documenso + rallly
    # green, B70 — '(term)'->'(Term)' only). ``=0`` keeps the lowercase
    # qualifier byte-identical (kill-switch).
    "WYSTAN_RECALL_QUAL_CASING",
    # B58-v3 (2026-07-15) — grain wave, ONE flag gates both segments (the
    # B53 precedent): Seg C Stage 6.9c schema-monolith member strip (a
    # whole-DB schema file + its package's plumbing leave every
    # FOREIGN-anchored claimant's ledgers — documenso team.verify 84%
    # prisma) + Seg A fdir internal-lib candidacy in the B48 ws-library
    # lane (broadly-imported zero-surface feature-dir modules —
    # twenty-front src/modules/apollo, cal.com apps/web/modules/data-table
    # — ride the SAME 6.985 transport-handoff conservation channel; the
    # handoff resolves fdir: anchors for grain-wave candidates). Reshapes
    # developer_features[] ledgers + product_features[] membership/LOC +
    # the platform lane + user_flows[].product_feature_id when candidates
    # exist. Default ON since the 2026-07-16 horizon-1 flip (KEY_SCHEMA 30;
    # keyed proof documenso green, B58-v3 — team.verify ~200 LOC, fdir-lane).
    # ``=0`` restores the pre-B58-v3 byte-identical board (kill-switch).
    "WYSTAN_GRAIN_WAVE",
    # B66-v2 (2026-07-16) — ownership/LOC-truth + dispatch tails, ONE flag
    # gates four segments (the B58-v3 precedent). Seg A: an entry-mint
    # (server-api-entry / jobs-entry source) exclusively owns its module
    # subtree at the loc-attribution pass — a route-anchor dev whose members
    # collapsed to loc=0 under primary-owner fan-in (hoppscotch 27 resolvers
    # -> one 'team' uuid, 0 LOC, mis-parented) recovers its owned LOC without
    # touching membership or journeys (attribution layer). Seg B: a static
    # asset/data member (json/svg/lottie) reaching a dev feature only through
    # import fan-in neither credits membership nor inflates the file count
    # (genuine shared CODE survives — the documenso packages/lib anti-case).
    # Seg C: a python-module dispatch extractor (registry/handler-map dicts,
    # entry_points, __main__ CLI, celery tasks) emits routes_index kind
    # py-dispatch so python entry surfaces stop reading as perpetual
    # Uncovered. Seg D: the tRPC collector resolves lazy handler-cache
    # routers (UNSTABLE_HANDLER_CACHE / getHandler + a relatively-imported
    # ``router``) that the @trpc/server import gate skipped. Default ON since
    # the 2026-07-16 horizon-1 flip (KEY_SCHEMA 30; keyed proof hoppscotch +
    # cal green, B66-v2 — ghost 0-LOC drop, team owned>0). ``=0`` keeps every
    # segment inert, byte-identical to the merged B66+B67 world (kill-switch).
    "WYSTAN_OWNERSHIP_V2",
    # B71 Seg D (2026-07-16) — flow-grain laws T1-T4. Re-grains the flow store
    # to the journey grain at the Stage 6.7 rollup boundary (before UF, so grain
    # disease is not amplified onto user_flows[]): T1 drops empty-span flows
    # (reverse-lookup contract break), T2 re-anchors barrel/re-export entries
    # onto their definition site, T3 folds a flow whose span-set is a subset of a
    # same-entry sibling's (RefApp cases.py / hopp kernel index.ts twins), T4 folds
    # a same-entry fanout that shares an identical dominant span (documenso
    # rate-limits.ts x14). Folds union the loser's spans/paths into the winner
    # (conservation, merged_from lineage). Reshapes flows[] + feature_flow_edges[]
    # + user_flows[] membership. Default ON since the 2026-07-16 horizon-1 flip
    # (KEY_SCHEMA 30; keyed proof documenso + novu green, B71 — loc=0 flows -> 0).
    # ``=0`` keeps the flow store byte-identical (the block never runs;
    # kill-switch).
    "WYSTAN_FLOW_GRAIN",
    # B71 Seg A-C (2026-07-16) — the naming pack: L-A1/L-A2 PF display route-
    # grammar + provenance-tier, L-B1 leaf-collision qualification, L-C1..L-C4 UF
    # synth echo-fold / verb-phrase integrity / same-noun-head families / board
    # name uniqueness, and the degraded-scan confidence scoping (auth-fail no
    # longer blanket-downgrades cache-validated UF domains). DISPLAY + confidence
    # channels (pf.display_name / uf.name / name_confidence / name_evidence /
    # name_provenance telemetry); identity/membership/paths untouched. Default
    # ON since the 2026-07-16 horizon-1 flip (KEY_SCHEMA 30; keyed proof
    # documenso + novu green, B71 — echo-fold in the rich boards, anti-cases
    # live). ``=0`` restores the pre-B71 byte-identical naming channels
    # (kill-switch).
    "WYSTAN_NAMING_PACK",
    # B65-v3 (2026-07-16) — SPA router extraction, ONE flag gates both
    # segments (the B66 precedent): Seg A vue file-based pages
    # (vite-plugin-pages / unplugin-vue-router ``pages/**/*.vue`` in a
    # non-Nuxt Vue SPA — hoppscotch routes_index=1 at 33 real vue pages)
    # + Seg B react-router code config (JSX ``<Route path=...>`` trees +
    # ``createBrowserRouter`` object arrays; lazy-import target = entry —
    # RefApp App.tsx 60+ routes invisible). Emits routes_index rows
    # method=PAGE kind=spa-page, so flows/journeys mint and the B65
    # partition surface-detect sees SPA product surfaces. Registration is
    # flag-gated at the registry (extractor_hits key parity, B67 lesson).
    # Default **ON** since the B65-v4 re-flip (2026-07-18, KEY_SCHEMA 31;
    # first flip v30 was R1-reverted at f6bd5d6 — route-page anchors won
    # mint/ownership off feature-dirs; re-landed with the mint-priority
    # fix chain: authored-subtree fence+floor predicate, spa-born mass
    # fence, member-twin bar, barrel-hop, template-literal honest skip.
    # Proof: full convoy2 on f38760e + operator panel PASS 2026-07-18).
    # Explicit =0 restores pre-B65-v3 byte-identically (kill-switch
    # forever); unset ≡ explicit "1".
    "WYSTAN_SPA_ROUTER_ENTRIES",
    # S1 (2026-07-18) — owner-oracle: ONE deterministic file→owner election
    # (owner_oracle.elect_primary_owners — the Stage 6.97 rule: module-subtree
    # > non-facet > dir-count > flows > slug) replaces the two ORDER-SENSITIVE
    # first-claimant owner resolutions (indexes.build_path_index R1 by
    # features-list order + conservation.build_file_pf_owner R2 by dev-path
    # order). The census probe measured their split at PF grain 0.85%
    # documenso / 1.23% cal / 3.08% novu (dev grain 6.47/2.55/19.14) — the
    # inter-version "spilling" a feature insert/reorder caused with no change
    # in evidence. The oracle is computed ONCE post-devgrain (before the
    # emission path_index rebuild) and consumed by the path_index refresh (R1),
    # the terminal-home conservation votes (R2), and transitively i16 / dispatch
    # (they read the refreshed path_index). Facet/shared exclusion survives as
    # a COVERAGE VIEW over the election — same owner, filtered visibility, not
    # a separate rule. The oracle NEVER moves membership (READ-resolution only;
    # conservation ladder untouched). Reshapes path_index[].feature_uuid on
    # contested files + the UF homes those owners drive. Default ON (flipped
    # 2026-07-19, S*-pack, KEY_SCHEMA 32 — census-disagreement 0, UF-057
    # rehome, keyed A/B novu, panel ON >= OFF strict); =0/false/off restores
    # the first-claimant resolutions byte-identically — explicit off stays a
    # valid kill-switch forever.
    "WYSTAN_OWNER_ORACLE",
    # S2 Seg D (2026-07-18) — degradation-honesty stamp: a scan that finished in
    # a visibly-degraded LLM state (the refiner's whole fresh batch failing at
    # cost==0 = a dead key mid-scan, or the 6.7d journey abstraction leaving
    # applied=False with real candidates) records typed records in
    # scan_meta.degradations[] with severity="failed" so validate_scan /
    # keyed_proof FAIL the proof gate instead of scoring a fail-open board that
    # self-reports healthy (264->78 RefApp fail-open, probe 2026-07-18). Default
    # ON (flipped 2026-07-19, S*-pack, KEY_SCHEMA 32 — telemetry-only, 4-stage
    # live-fire stamp proof); =0/false/off appends nothing → degradations[]
    # byte-identical — explicit off stays a valid kill-switch forever.
    "WYSTAN_DEGRADATION_STAMP",
    # S2 Seg B' (2026-07-18) — uf_refiner per-UF output-token budget: the fixed
    # 1500-token DEFAULT truncates a large domain's structured JSON response
    # mid-object -> json_parse_failed -> the whole domain keeps deterministic
    # names (RefApp 13:25Z: the 3 degraded domains were EXACTLY the 3 largest —
    # network 26 / service 18 / detector 17 UFs; next-largest admin 11 refined
    # cleanly). ON scales max_tokens by a structural per-UF allowance floored at
    # DEFAULT so large domains parse. Reshapes user_flows[].name/description/
    # intent/ui_tier/acceptance on the previously-degraded (largest) domains
    # only. Default ON (flipped 2026-07-19, S*-pack, KEY_SCHEMA 32 — 3 domains
    # refine clean, no truncation); =0/false/off -> max_tokens==DEFAULT + cache
    # key unchanged -> byte-identical — explicit off stays a valid kill-switch
    # forever.
    "WYSTAN_UF_REFINE_TOKEN_SCALE",
    # S2 Seg A (2026-07-18) — deterministic UF pre-clustering: journey STRUCTURE
    # is computed deterministically (Stage 6.7a: one conservation-complete
    # cluster per rollup domain) and the LLM layer only NAMES it (6.7b refiner);
    # the structural LLM stages (6.7c mega-split, 6.7d journey rewrite) are
    # skipped. UF-COUNT becomes invariant to LLM death (fail-open 264-vs-78
    # class) and to resampling (−26% whole-batch class) — probe 2026-07-18.
    # Reshapes user_flows[] (membership/grain/ids) + downstream homes.
    # Default ON since the 2026-07-21 pack-3 flip (KEY_SCHEMA 34) — the
    # S2-A RETURN: flipped ON in the 2026-07-19 S*-pack (KEY_SCHEMA 32),
    # UN-flipped the same day (corpus regression audit 4x WORSE — the
    # det-cluster naming layer emitted bare 'Manage <plural>' bins
    # corpus-wide: twenty 143 / midday 29 / documenso 'Manage os/ts' /
    # novu 61% bare), and RE-flipped after the R5 corpus naming wave +
    # spray-generalization cured the collapse (ledger §S2-A-V3: twenty
    # spray 17→0, settings-PF 36→22, conservation 328==328, 0 false, I14
    # dangling 0; pair flag WYSTAN_SPRAY_GENERALIZED flips together).
    # ``=0``/false/off restores the LLM-structured path byte-identically —
    # explicit off stays a valid kill-switch forever (unset ≡ explicit
    # "1").
    "WYSTAN_UF_DET_AGGREGATION",
    # S2 Seg C (2026-07-18) — canonical LLM batch composition: volatile pure
    # counts leave the 6.7d prompt canon (digest n_dev_features; Call-2 per-row
    # n_files) and the digest's UF ordering uses log2 weight-buckets instead of
    # raw member_count, so a count-only drift (the 1-of-980 resample trigger)
    # no longer flips the whole-batch cache key; real content changes still do.
    # Adds the flag-gated scan_meta.llm_batch_canon hit-rate telemetry.
    # Reshapes the 6.7d prompts (hence keyed user_flows[]/product_features[]
    # composition on cache-miss worlds). Default ON (flipped 2026-07-19,
    # S*-pack, KEY_SCHEMA 32 — cache-hit-rate on the 1/980 drift); =0/false/
    # off keeps digest, prompts and keys byte-identical — explicit off stays
    # a valid kill-switch forever.
    "WYSTAN_LLM_BATCH_CANON",
    # S5a (2026-07-18) — mega-PF decomposition ARMING, ONE flag gates the
    # three ship-grade grain segments (the B53/B58-v3 precedent). Seg A: the
    # B24 TargetGrainIndex derives ADDITIONAL route roots from the
    # routes_index population (a non-dialect central/backend router file —
    # RefApp backend/routers/admin.py — contributes its parent dir as a root
    # when >=2 distinct product route files cluster there; the flat-leaf
    # stem rule keys each nav group). Seg B: a route-GROUP target with no
    # exact-anchor PF resolves to the SIBLING PF whose core-identity token
    # it UNIQUELY echoes (compliance group -> compliance-page) instead of
    # minting a twin. Seg C: the Stage 6.99b organic re-home candidates
    # (telemetry-only under B69-v2) become B24-class moves routed through
    # the S3 overturn ledger (rung mega). Reshapes user_flows[].
    # product_feature_id + product_features[] (mints/feeds) +
    # developer_features[] carve chunks on repos where B24 fires. Default
    # ON (flipped 2026-07-19, S*-pack, KEY_SCHEMA 32 — healthy novu pair +
    # re-panel after the K2 final); =0/false/off -> both grain params False
    # + the 6.99b organic branch stays a continue -> byte-identical —
    # explicit off stays a valid kill-switch forever. (The trigger-shape
    # Seg D/E ride a separate mandate.)
    "WYSTAN_MEGA_DECOMP_ARM",
    # S5a-it2 (2026-07-18) — generated-code CONTENT-marker probe inside the
    # existing Stage 6.9b channel (the module docstring's promised
    # follow-up): a file whose head banner carries the universal codegen
    # markers (Go-spec "Code generated … DO NOT EDIT" line class /
    # @generated marker / generated-declaration + do-not-edit admonition
    # pair — Speakeasy/orval/openapi-generator/graphql-codegen classes)
    # strips like a filename-convention match. Kills the novu
    # libs/internal-sdk react-query client (923 hand-named .ts, ~107K LOC)
    # at the SOURCE: its flows/UF garbage never survive 6.9b. Reshapes
    # developer_features[]/flows[]/user_flows[] on repos vendoring codegen
    # output. Default ON (flipped 2026-07-19, S*-pack, KEY_SCHEMA 32 —
    # healthy novu pair + re-panel); =0/false/off -> filename-only
    # predicate, byte-identical — explicit off stays a valid kill-switch
    # forever.
    "WYSTAN_GENERATED_CONTENT_MARKER",
    # S4-a (2026-07-18) — App-Router keyless route extractor: emits
    # routes_index entries for app/**/page.tsx + app/**/route.ts trees whose
    # scope is not cleanly next-app-router-tagged (the monorepo residue where
    # the composite replaced the stock route source — cal apps/web 0/939 — and
    # the polyglot leftover scanned with the js-generic root tag — onyx
    # web/src/app 0/114). Keys on the App-Router CONVENTION (page/route leaf
    # under an app/ or src/app/ root run, matched anywhere) via its own source
    # name (route-approuter), so Stage-1 replace-by-name never narrows it and
    # the js-generic leftover tag never suppresses it. Contained: emits ONLY
    # explicit routes_index rows (the App-Router profile already anchors the
    # files' features/flows via the same first-segment slug — same-slug merge,
    # no twin); build_routes_index folds them LAST so a clean next-app-router
    # repo's stock rows win the dedup byte-identically. Default ON (flipped
    # 2026-07-19, S*-pack, KEY_SCHEMA 32 — cal 0->249 / onyx 0->106 routes,
    # conservation 0; KS-sets of both class forms + wave-17); =0/false/off
    # keeps the extractor unregistered (extractor_hits byte-identical — the
    # B67 kill-switch lesson) — explicit off stays a valid kill-switch
    # forever.
    "WYSTAN_APPROUTER_KEYLESS",
    # S4b (2026-07-18) — Go extraction repair. On real Go repos the shipped
    # go-router extractor mints HTTP-header names and JSON/struct keys as
    # "features": the chi/gin/echo ``route_call`` patterns match any bare
    # ``.Get("s")`` / ``.Set("s")`` and Go code is saturated with
    # ``req.Header.Get("Content-Type")`` etc. (traefik VERIFIED: 19/19
    # go-router anchors were header garbage, 0 real routes), while its actual
    # ``/api/**`` + ``/debug/**`` surface — registered via the gorilla/mux
    # fluent chain ``router.Methods(..).Path("/x").HandlerFunc(..)`` — is
    # invisible (no gorilla signature). Armed, the extractor (a) adds the
    # gorilla/mux registration signature and (b) requires every matched string
    # to be a URL PATH (``route_must_be_path``: starts with ``/`` or a
    # method-prefixed ``"GET /x"`` ServeMux pattern), dropping the header/key
    # false positives with no per-repo vocabulary, plus excludes testdata/
    # example fixtures (dev-artifact law). Reshapes go-router anchors only —
    # go-package directory anchors are untouched. Default ON (flipped
    # 2026-07-19, S*-pack, KEY_SCHEMA 32 — traefik 0->1 PF/51 routes,
    # ollama 0->2/76); the flag is read at collect time so the cached
    # pattern bundle serves OFF and ON alike — =0/false/off restores the
    # shipped board byte-identically — explicit off stays a valid
    # kill-switch forever.
    "WYSTAN_GO_EXTRACTION",
    # S5b (2026-07-19) — leaf-route dissolution + platform promotion, ONE
    # arbiter wave (the S5a precedent). Seg B re-homes a route:-leaf black
    # hole's annexed member devs to real siblings (novu duplicate-workflow
    # 315/2 -> subscribers/analytics/domains/…; unhomed devs lane, freeing
    # their pages); Seg C promotes buried product surfaces — platform-lane
    # residents with PAGE evidence (a-lite mirror; P1 page-cohort ∪ P2
    # lane-token↔freed-page bridge) — by birth (S5a birth-law) or
    # merge-into-sibling (the notifications class). Reshapes
    # developer_features[].product_feature_id + product_features[]
    # (births/merges/leaf-shed) on repos where a leaf hole or a buried
    # surface exists. Default OFF; =0/unset keeps the stage un-entered,
    # byte-identical. Appended WITHOUT a KEY_SCHEMA bump — the bump rides
    # the separate flip commit (flip-protocol).
    "WYSTAN_LEAFROUTE_PROMOTION",
    # display-cross gate (2026-07-19) — B71 provenance-ladder consumer. Armed,
    # the nav authored label feeding a PF's display is kept only on identity
    # evidence (tokens intersect the PF name/anchor OR its member-dominant path
    # tokens); a foreign label (cal ``insights`` display 'Bookings',
    # ``organization`` -> 'directory_sync') is reverted to the honest basename,
    # equal-vote ties prefer the PF's own anchor-page self-link, and the
    # survivor is title-cased. Reshapes product_features[].display_name +
    # scan_meta.naming_contract.pf_display_provenance only. Default ON since
    # the 2026-07-21 pack-2 flip (KEY_SCHEMA 33; keyed proof cal + novu green
    # — sim==engine 7/21 exact, cal 5→0 false displays, novu footprint exactly
    # 1 row; ledger display-cross pack 2026-07-19). ``=0``/false/off restores
    # the shipped display byte-identically — explicit off stays a valid
    # kill-switch forever (unset ≡ explicit "1").
    "WYSTAN_PF_DISPLAY_EVIDENCE_GATE",
    # workspace UNION gate (2026-07-19, onyx shape) — when the declared
    # workspaces span a strict MINORITY of tracked files (scale-invariant
    # covered*2 < total), they are unioned with the non-overlapping
    # synthesise_workspaces results so the undeclared product bulk (onyx
    # web/ Next app + cli/ Python) scopes to its own stack instead of
    # dissolving into the js-generic leftover pass. Reshapes the Stage-1
    # workspace partition and therefore every downstream layer on
    # minority-declared repos; high-coverage declared monorepos
    # (langfuse/supabase/typebot) are ratio-gate inert. Default ON since
    # the 2026-07-21 pack-2 flip (KEY_SCHEMA 33; keyed A/B onyx green —
    # fallback 57.1→36.5%, web-residual 2114→0; anti-cases langfuse/
    # typebot byte-ident even armed; ledger onyx union-gate cycle).
    # ``=0``/false/off restores the pre-gate Stage 1 byte-identically —
    # explicit off stays a valid kill-switch forever (unset ≡ explicit
    # "1"). NOTE: registered at flip time — the add-cycle omitted the
    # ENV_OUTPUT_FLAGS registration (cache-keying gap found at the flip
    # audit; the v33 bump invalidates every entry cached under the gap).
    "WYSTAN_WORKSPACE_UNION",
    # B73 organic-move (2026-07-19, fork-A ruling) — the ratified
    # strict+gated organic UF re-home rule at the 6.99b rail: armed, it
    # REPLACES the S5a mega-organic handling of the rail's candidates with
    # home_share==0.0 ∧ rival_share>=0.8 (inclusive) + the product→dev
    # direction-gate; PURE arbiter moves (rung organic-move), no renames,
    # no folds, no I8 orphan-guard (explicit ruling — sole-UF from-PFs are
    # the disease). Reshapes user_flows[].product_feature_id on repos with
    # strict candidates. Default ON since the 2026-07-21 pack-2 flip
    # (KEY_SCHEMA 33; keyed proof RefApp green — moved=0, UF-051 blocked
    # reason='prior-hold' hold='cross_app_target', conservation
    # 399→399/0/0; typebot keyed-evidence trio byte-inert, KS ON == it1
    # digest; ledger §B73-IT2). ``=0``/false/off keeps the branch
    # un-entered, byte-identical (including the mega-armed path) —
    # explicit off stays a valid kill-switch forever (unset ≡ explicit
    # "1").
    "WYSTAN_ORGANIC_MOVE",
    # R5 corpus naming-wave master (2026-07-19) — one flag gates the five R5
    # naming segments' NEW display-channel behaviors: identity-parity
    # reject/qualify (a PF display folding to ANOTHER live PF's canonical slug),
    # own-resource echo-hub templating, member-evidence dir-token humanization,
    # the compose-joint qualifier normalizer, and the negative confidence rungs
    # (census-shape name_confidence caps + name_evidence stamps). Reshapes
    # product_features[].display_name + user_flows[].name/name_confidence/
    # name_evidence + scan_meta.naming_contract telemetry only — canonical
    # identity untouched. Default ON since the 2026-07-21 pack-2 flip
    # (KEY_SCHEMA 33; keyed A/B twenty + papermark green — phase-1 cures
    # hold paren-high 17→0 / dups 3→0, brand-echo stamps ×5, measured
    # demote high 101→92, keyed PF layer only 2 medium = no over-demotion;
    # ledger §R5-PHASE2). ``=0``/false/off restores the pre-R5 emission
    # byte-identically — explicit off stays a valid kill-switch forever
    # (unset ≡ explicit "1").
    "WYSTAN_NAMING_WAVE_R5",
    # S2-A-v3 (2026-07-19) — spray-generalization: the generalized R5-2 spray
    # predicate over the UNPARENTHESIZED tech-dir-suffix form the
    # det-aggregation regrain channel mints ('Manage setting AI components/
    # constants/…' — twenty-b exhibit): >=3 same-PF siblings sharing a
    # >=2-token prefix (G1) whose tail token names the members' own leaf
    # directory (singular(tail)==singular(leaf-dir) on >=50% member paths)
    # collapse — whole group, structural misses ride along — into ONE
    # own-resource parent row ('Manage AI settings' form; member-union
    # conservation, I14 repoint). Paren-tail rows are R5-2's class and are
    # never touched (G0). Reshapes user_flows[] (row count/names/membership)
    # + the scan_meta.spray_generalized telemetry on armed worlds only.
    # Default ON since the 2026-07-21 pack-3 flip (KEY_SCHEMA 34; census
    # twenty (R5+DET_AGG world) — spray 17→0, parents 'Manage AI settings'
    # mc38 / 'Manage application settings' mc52 / 'Manage data model
    # settings' mc25, settings-PF 36→22, conservation 328==328, 0 false,
    # I14 dangling 0; KS byte-ident typebot+openstatus; flips together
    # with its pair WYSTAN_UF_DET_AGGREGATION — ledger §S2-A-V3).
    # ``=0``/false/off keeps the pass un-entered, byte-identical —
    # explicit off stays a valid kill-switch forever (unset ≡ explicit
    # "1").
    "WYSTAN_SPRAY_GENERALIZED",
    # B74 Seg C (2026-07-19, probe-canon tune-first) — home-pure container
    # inherit: a journey member whose HOME PF is a monorepo ws-pkg CONTAINER
    # (anchored-mint ``anchor_id`` "ws:" marker — Form A only; mass/ratio
    # forms refuted) is inheritable like lane/unowned on the CITED channels
    # (Pass-1 from_flows + Pass-2a cited devs). The 2b whole-pool rescue and
    # the route backfill stay home-STRICT. Reshapes user_flows[] membership
    # (twenty: 'Sign in and authenticate' 0->11 members) + the 6.7d
    # uf_home_filtered telemetry on ws-container repos only. Default ON
    # since the 2026-07-21 pack-3 flip (KEY_SCHEMA 34; keyed proof twenty
    # green — 'Sign in and authenticate' mints 14 members on the live
    # channel, filter 24,226→2,081, dropped exactly {blocklist by-design,
    # SSO}, members 561→801 (+240 rescue), husks 0, degradations 0;
    # ledger §B74 SEG C). ``=0``/false/off keeps the strict filter
    # byte-identical — explicit off stays a valid kill-switch forever
    # (unset ≡ explicit "1"); armed on a repo WITHOUT ws-containers is
    # inert (KS: openstatus).
    "WYSTAN_HOME_PURE_CONTAINER_INHERIT",
    # B74 Seg A (2026-07-20) — SPA route-table extraction: exported enum /
    # flat-const route tables (twenty AppPath/SettingsPath, novu ROUTES)
    # consumed in path-position by a router file emit their URL patterns
    # (method=PAGE, kind=spa-page) + owner-page anchor evidence, so
    # capability journeys mint on SPA repos whose routes live in tables.
    # Reshapes routes_index + spa-page candidates on armed worlds only.
    # Default ON since the 2026-07-21 pack-3 flip (KEY_SCHEMA 34; keyed
    # proof twenty + novu green — twenty routes_index +114 PAGE
    # (AppPath/SettingsPath consumption-primary canon), novu +86 incl.
    # /auth/sign-in; 0/2,042 false candidates; container-PF guard holds
    # — 'twenty-shared' 13.8K phantom dead; ledger §B74 SEG A).
    # ``=0``/false/off keeps the arm un-entered, byte-identical —
    # explicit off stays a valid kill-switch forever (unset ≡ explicit
    # "1").
    "WYSTAN_SPA_ROUTE_TABLE",
    # B74 Seg B (2026-07-20, F3′ re-entry probe SHIP/high) — post-grain
    # flow re-derivation at Stage 6.865: stage-8-born / re-membered dev
    # features (non-test path-set ≠ the stage-3 unit; removal-only
    # deltas excluded) re-run the EXISTING Stage-3 flow machinery
    # between the 6.86 mint window and the Stage 6.7 UF family — the
    # single existing mint sees the new flows naturally (no new mint
    # channel). Healthy flow-density is a secondary EXCLUDE-only filter
    # (< repo flowful median / _OVERSIZED_MEDIAN_MULT); chunk
    # eligibility is ratio-triggered (exports/paths prompt caps)
    # independent of the global oversized cut; locale-births die on the
    # existing MIN_EXPORTS gate. Reshapes flows[] /
    # developer_features[].flows[] / feature_flow_edges[] and,
    # transitively, the minted user_flows[] layer on repos with
    # post-stage-3 grain changes; armed no-fire boards are
    # byte-identical (telemetry key only on fire — Seg C inertness
    # law). Default ON since the 2026-07-21 pack-3 flip (KEY_SCHEMA 34;
    # keyed proof twenty green — 894 live calls, +3,712 flows
    # (1400→3673), UF 120→169, members 561→1211; golden targets taken:
    # tasks 34m, workflows 44m (was 2-loc), AI-assistant 13m,
    # calendar/data-model/marketplace/auth-tokens; husks 0,
    # degradations 0; ledger §B74 SEG B; the UF-giant blocker resolved
    # by B75 cases-split — same pack). ``=0``/false/off keeps the stage
    # un-entered, byte-identical — explicit off stays a valid
    # kill-switch forever (unset ≡ explicit "1").
    "WYSTAN_FLOW_REDERIVE_POSTGRAIN",
    # S5b Seg H (2026-07-21, probe-canon tune-first) — digest stratification:
    # the 6.7d Call-1 digest stops starving the page surface under the caps.
    # M1-ADDITIVE appends page-anchored UFs BEYOND the mass-sorted UF cap
    # (reservation append — displacement=0; the fixed-cap form starved 5/67
    # cached proposals and was refuted); M2-HYGIENE-QUOTA reserves half the
    # route budget for the hygienic page stream under route pressure
    # (storybook/dev-artifact paths + filename-echo pseudo-routes demoted
    # out of the quota only). Digest/prompt/cache-key change on pressured
    # repos → user_flows[] + product_features[] reshape via Call-1. No-
    # pressure repos are byte-identical (inertness law). Default ON since
    # the 2026-07-21 pack-3 flip (KEY_SCHEMA 34; keyed proof novu green —
    # 'Sign in to existing account' mints (3m; 0/12 draws for 8 days
    # before), 'View analytics and activity charts' 1→5m, UF 88→92,
    # members 472→565, degradations 0; telemetry 46 page-anchored/35
    # appended/73 page-routes; ledger §S5b-H). ``=0``/false/off keeps
    # both cuts byte-identical — explicit off stays a valid kill-switch
    # forever (unset ≡ explicit "1").
    "WYSTAN_DIGEST_STRATIFICATION",
    # B76 (2026-07-21) — metrics recompute-on-emission: re-runs the Stage-6
    # commit-metric sweep over the FINAL membership after the last
    # membership-mutating finalize stage (mint-time metric zeroing class:
    # tc=0 rows wearing inherited authors/health; PF sum-over-contributors
    # both losing zeroed mass and double-counting shared commits — Alerts
    # 5 vs ~63). PF metrics recompute from each PF's OWN path-set with
    # per-commit dedup; the four mint factories stamp an honest null-state
    # instead of deep-copying identity. Reshapes total_commits/bug_fixes/
    # bug_fix_ratio/authors/last_modified/health_score/health_confidence
    # on developer_features[] + product_features[] (metric channel only —
    # membership and hotspot_files untouched). Default ON since the
    # 2026-07-21 pack-3 flip (KEY_SCHEMA 34; census ×3 repos on the
    # 7-flag battery, same-world — "impossible" tc=0∧authors>0 rows
    # 60+17/162+42/84+9 → 0+0 on ALL, hotspots byte-ident (full join 0
    # diffs), dedup law dev-sum ≤ repo commits; both mechanism halves
    # load-bearing; ledger §B76). ``=0``/false/off keeps the pass
    # un-entered and the factory inheritance byte-identical — explicit
    # off stays a valid kill-switch forever (unset ≡ explicit "1").
    "WYSTAN_METRICS_RECOMPUTE",
    # B77 (2026-07-21, forensics-canon §FORENSICS 502M) — residual
    # citability: the 6.7c mega-split RESIDUAL bucket is marked
    # structurally (``UserFlow.residual``) and stops being a wholesale
    # Pass-1 ``from_flows`` inherit source (its members stay in the
    # bucket / the token-gated grounding channels — no-orphan); Pass-1
    # container-inherit gains Pass-2a's own ``& utok`` content-token
    # affinity gate; a built UF majority-voting for >1 real PF home with
    # no common majority is carved per home (mint-side, existing
    # member_votes mechanism); a ws-container PF is not a valid
    # conservation resettle target. Reshapes user_flows[] membership on
    # armed composite worlds (the class lives ONLY on the FLOW_REDERIVE ×
    # CONTAINER_INHERIT interaction: twenty 502m/278m/216m mass-transfer
    # giants). Default ON since the 2026-07-21 pack-3 flip (KEY_SCHEMA
    # 34; replay census on the twenty capture — 502-class 542→7 (target),
    # AI-agents 216→7, marketplace 278→25; buckets keep members as honest
    # residual rows — 0/2211 losses (the OFF world LOST 957); anti-cases
    # 23/26/6 intact; KS byte-ident both worlds; ledger §B77).
    # ``=0``/false/off keeps 6.7c/6.7d/conservation byte-identical —
    # explicit off stays a valid kill-switch forever (unset ≡ explicit
    # "1").
    "WYSTAN_RESIDUAL_CITABILITY",
    # B75 (2026-07-21, probe-canon supports/tune-first) — UF-giant
    # cases-split: giant catch-all journeys (mc >= the census band edge
    # 30) re-grain into >= K dir-tree surface cases + a residual that
    # keeps the parent row (survivor-id law); vendored-dir guard (S3
    # no-product-surface ∧ S1 dependency-family echo) rejects technical
    # children BEFORE extraction (tracecat tiptap/ai exhibit). Reshapes
    # the emitted user_flows[] layer + flow backpointers on boards that
    # carry giants; 0-giant boards are byte-identical (inertness law).
    # Default ON since the 2026-07-21 pack-3 flip (KEY_SCHEMA 34;
    # sim-canon on the composite keyed twenty world — 209m 'Browse object
    # record' → 10 children / 131m → 11 (settings names), 86m golden
    # 'Create and edit records' = 4 recognizable cases + residual
    # lineage, 502m/220m honestly KEPT (B77's class — division of labor
    # proven by simulation); keyless inertness ×3 topologies byte-ident;
    # suite² failset-diff empty; ledger §B75). ``=0``/false/off keeps
    # the seam un-entered, byte-identical — explicit off stays a valid
    # kill-switch forever (unset ≡ explicit "1").
    "WYSTAN_UF_CASES_SPLIT",
    # B78 Seg G (2026-07-21) — nav-parent display grouping. A deterministic
    # nav-tree extractor reads the repo's STATIC exported nav registries
    # (module-registry / sidebar nav-config / settings-navigation hooks) and
    # attaches a nullable ``product_features[].nav_parent`` = {parent_label,
    # parent_id, source_file, line, via} to a PF whose anchor route (or
    # enum-referenced nav slug) matches a nav SUB-item, plus the
    # ``scan_meta.nav_tree`` telemetry (categories / sub-items / matched /
    # unrepresented / duplicates). DISPLAY ONLY — PFs are never merged,
    # moved, or minted; live nav categories with no PF are reported in
    # nav_tree.unrepresented, never minted. Default ON since the 2026-07-22
    # flip-pack №4 (KEY_SCHEMA 36); explicit ``=0`` ⇒ no field and no
    # scan_meta key ⇒ serialized output byte-identical to pre-Seg-G
    # (kill-switch forever).
    "WYSTAN_NAV_PARENT",
    # B79 Seg A — robust truncated-response salvage for Stage 6.7d Call-1. On a
    # giant repo (cal-com) the abstraction response truncates at the token
    # ceiling (output_tokens==16000) → whole journey layer degrades. When ON,
    # salvage the complete prefix of the two arrays (product_features + a
    # user_flows prefix) and apply a PARTIAL abstraction (severity="partial"
    # stamp; salvaged results never cached). Default ON since the 2026-07-22
    # flip-pack №4 (KEY_SCHEMA 36); explicit ``=0``/false ⇒ _draw is
    # byte-identical to the flagless engine (salvage branch + telemetry never
    # run — kill-switch forever).
    "WYSTAN_67D_ROBUST_PARSE",
    # B78 Seg H (2026-07-21) — dominant-evidence naming: presence → RATIO
    # at the three UF-display compose sites (refiner accept-gate, lattice
    # _deterministic_name, own-resource/generic template). A content token
    # enters a composed journey display only with member support >= 0.34
    # (the validator's I15 attach floor, reused); side-effect flow
    # families (audit-write/telemetry/cache/log — vocab corroboration)
    # never gift words. Reshapes user_flows[].name. Default ON since the
    # 2026-07-22 flip-pack №4 (KEY_SCHEMA 36); explicit ``=0`` ⇒ every
    # consumer byte-identical (kill-switch forever).
    "WYSTAN_DOMINANT_EVIDENCE_NAMING",
    # B78 Seg A (2026-07-21, probe-canon supports/tune-first) —
    # walk-evidence gate on the Stage 6.86 terminal ancestor-walk fold: a
    # ``fold:walk`` whose target anchor holds NO behavioral claim on the
    # folded dev's flow ENTRY files (RefApp: 0/35 walk-folds had one — the
    # ``cases``/``media-library`` vacuum-PF disease) re-disposes by
    # the dev's own entry evidence instead: best evidence-claiming anchor
    # (R1 exact-file tiebreak: file-stem route convention, then the
    # file's route-share), standalone mint-on-demand at >=2 distinct
    # entry files OR >=2 flows, single-flow devs fold into the nearest
    # evidence-claiming minted PF (R2), and a flowful dev is never laned
    # by the gate (R3). Reshapes developer_features[].product_feature_id
    # + product_features[] (entry-evidence mints) + downstream journey
    # homes on walk-fold-bearing boards; lineage / fold:entry /
    # api-parent channels untouched. Default ON since the 2026-07-22
    # flip-pack №4 (KEY_SCHEMA 36); explicit =0 ⇒ byte-identical to the
    # ungated walk (kill-switch forever).
    "WYSTAN_FOLD_EVIDENCE_WEIGHT",
    # B78 Seg F (2026-07-22) — plumbing-UF reclassification (Stage 6.996): a
    # UF whose NAME reads as a data-access/infra helper (plumbing verb +
    # tech-object, closed YAML vocab), whose profile is micro (member_count
    # <=2), and which carries no product surface (routeless + no member PAGE)
    # reclassifies to category="system" (+ surface_scope="system"). Reshapes
    # the emitted user_flows[] category/scope layer; membership untouched.
    # Default ON since the 2026-07-22 flip-pack №4 (KEY_SCHEMA 36); explicit
    # ``=0`` ⇒ no field change and no scan_meta key ⇒ serialized output
    # byte-identical to pre-Seg-F (kill-switch forever).
    "WYSTAN_PLUMBING_UF_RECLASS",
    # B78 (2026-07-21) — home-fidelity homing pack (Seg B/C/D, ONE system):
    # (B) conservation home-affinity gate re-homes ``tok0`` journeys with a
    # deterministic better-home via an S3 ``affinity-rehome`` proposal;
    # (C) 6.99b organic-move v3 — prior-hold narrowed to same-target +
    # rival name-affinity sanity (the 'Manage admins'→chat refutation);
    # (D) mega vacuum census — a top1/share>=0.25 home ranks its wrong-home
    # journeys (tok0 + better-home) into re-home proposals. Reshapes
    # user_flows[].product_feature_id on boards that carry the class;
    # class-free boards are byte-identical (inertness). Default ON since
    # the 2026-07-22 flip-pack №4 (KEY_SCHEMA 36); explicit ``=0`` / false ⇒
    # all three segments inert, byte-identical to main (KS 4-way kill-switch
    # forever).
    "WYSTAN_HOME_AFFINITY_GATE",
    # B80 (2026-07-22) — transport-donor domain drain (trpc-lane). Extends the
    # B53 ws-blob drain for TRANSPORT-shaped donors only (a package holding a
    # ``server/routers`` tree OR a ``@trpc/*`` dependency — mechanism, not a
    # name): ``routers``/``router`` become domain-dir containers with a
    # bounded scope-skip (``routers/<scope>/<domain>`` cal.com ``viewer/`` /
    # flat ``router/<domain>``), and the B22a cross-unit guard is lifted for
    # the transport donor (a trpc package routes to PFs owning no code in it).
    # Non-transport blobs (app-store / embeds / twenty-shared) fail the shape
    # test and stay under B22a — the anti-sink law. Reshapes
    # product_features[] membership/LOC + user_flows[].product_feature_id on
    # boards carrying a transport-shaped blob donor; every other board is
    # byte-identical (inertness). Default ON since flip-pack №5 (2026-07-23,
    # KEY_SCHEMA 38; proof: keyed cal calibration DECISIVE-PASS + composition
    # probe CLEAR on RefApp/documenso). The bump rides the pack's FIRST flip
    # commit (this one). unset ≡ explicit "1" byte-identical; "0"/"false"/
    # "off"/"no" restores the pre-B80 world (inverted kill-switch forever), so
    # cached entries must key on it.
    "WYSTAN_TRANSPORT_DOMAIN_DRAIN",
    # B85 (2026-07-22) — the B22a-resurrection fence: the Stage 6.996
    # post-fold domain-foreignness demote (it2 placement — after the last
    # homing writer) that sheds a PF's foreign member mass to its natural
    # home PF / the cross-unit lane. Default ON (armed inside the EVW world), so it
    # reshapes product_features[] membership/LOC + the platform_infrastructure
    # lane in the UNSET default world — hence the KEY_SCHEMA rides 36→37 with
    # its commit (world 36 unpublished, clean bump). unset ≡ explicit "1"
    # byte-identical; "0"/"false"/"off"/"no" restores the EVW-only world
    # (inverted kill-switch), so cached entries must key on it.
    "WYSTAN_FOLD_EVIDENCE_DEMOTE",
    # B84 (2026-07-22) — terminal member-disjoint reconciliation (Stage
    # 6.997): a flows[].uuid double-claimed by >1 UF's member_flow_ids
    # gets ONE authoritative owner (back-ref-if-claimer, else emission-
    # first claimer with the back-ref repointed); the uuid is stripped
    # from every other claimer, member_count re-synced, and any UF left
    # memberless dissolves (the 6.7d I7-drop twin semantics). Reshapes
    # user_flows[] membership/count + the repointed flows[].user_flow_id
    # on boards carrying a double-claim; class-free boards (RefApp) are
    # byte-identical (inertness). Default ON since flip-pack №5 (2026-07-23,
    # KEY_SCHEMA 38; proof: keyed documenso 9 dissolved / conservation exact
    # + keyless 10/10). The bump rode the pack's FIRST flip commit
    # (TRANSPORT_DOMAIN_DRAIN). unset ≡ explicit "1" byte-identical;
    # "0"/"false"/"off"/"no" restores the pre-B84 world (inverted kill-switch
    # forever), so cached entries must key on it.
    "WYSTAN_MEMBER_DISJOINT_RECONCILE",
    # B81 (2026-07-23) — agent-surface: the tool/skill registry becomes a
    # capability surface. A deterministic ($0 LLM) registry-census detector
    # (Seg A) reads the repo's tool/skill registry in two forms (declarative
    # name+description+schema tool tables; registered Tool subclasses /
    # @register decorators) and the post-UF stage tags/re-homes the existing
    # agent-entry journeys (Seg B) and mints ~1-per-domain ``via:agent``
    # capability journeys homed in the real capability PFs (Seg C). Reshapes
    # user_flows[] (new ``agent_surface`` tag + journey homes/mints) on boards
    # that carry a tool registry; every registry-less board (langfuse and the
    # rest of the corpus) is byte-identical — the detector stays silent
    # (inertness). Default ON since flip-pack №5 (2026-07-23, KEY_SCHEMA 38;
    # proof: KB3 + panel USEFUL + composition CLEAR). The bump rode the pack's
    # FIRST flip commit (TRANSPORT_DOMAIN_DRAIN). unset ≡ explicit "1"
    # byte-identical; "0"/"false"/"off"/"no" restores the pre-B81 world
    # (inverted kill-switch forever), so cached entries must key on it.
    "WYSTAN_AGENT_SURFACE",
    # B81-it2 (2026-07-25) — agent-surface ANCHORED TypeScript Form A. Extends
    # the registry-census detector to read a repo's TS tool registry through a
    # registry HELPER/INTERFACE anchor (langfuse ``defineTool`` /
    # lobe-chat ``BuiltinToolManifest`` / langfuse ``McpFeatureModule``) — never
    # a bare name+description+schema matcher — with a co-presence-in-one-object
    # guard (regex-grade TS parse). Reshapes user_flows[] (new agent_surface
    # tag + mints) ONLY on boards whose registry is TypeScript (langfuse,
    # lobe-chat); every other board is byte-identical. Default ON since
    # flip-pack №8 (2026-07-27, KEY_SCHEMA 41; keyed langfuse proof: the TS
    # two-tier registry mints agent-surface flows). The bump rode the pack's
    # FIRST flip commit (ROUTE_RENDER_UTIL_DEMOTE). unset ≡ explicit "1"
    # byte-identical; "0"/"false"/"off"/"no" keeps the detector Python-only
    # (inverted kill-switch forever), so cached entries must key on it.
    "WYSTAN_AGENT_SURFACE_TS",
    # Phase-1 agent-anatomy (2026-07-29) — registry-MOUNT attribution. Parses
    # the CONSUMER mount-sites (Anthropic ``system=``+``tools=`` / pydantic-ai
    # ``Agent(instructions=,tools=)`` / langfuse ``toolRegistry.register``),
    # resolves which registry domains each consumer mounts, and re-classifies
    # the entry-true-STARVED domains (``0-candidates``/``below-floor``) as
    # mount-attributed shared-member anatomy of the consumer journey
    # (``agent_surface.mounts`` + ``scan_meta.agent_surface.mount_attribution``).
    # Default ON since the agent-anatomy flip (2026-07-29, KEY_SCHEMA 44;
    # operator-ratified; offline-keyed RefApp proof — anatomy on the Chat journey,
    # collision-guard, conservation). Unset ≡ explicit "1"; explicit
    # "0"/"false"/"off"/"no" is the inverted kill-switch (census carries no
    # mount_consumers, byte-identical to the B81 world), so cached entries must
    # key on it (an unset-ON run must not collide with an explicit-OFF entry).
    "WYSTAN_AGENT_MOUNT_ATTRIBUTION",
    # Phase-2 agent-anatomy (2026-07-29) — agent SYSTEM-PROMPT detection. Parses
    # the CONSUMER call-site (system=/instructions=/{role:system}, the SAME site
    # Phase-1 reads tools= on) + named `*-system-prompt.txt` files + strongly
    # named consts, scoped to the agent machinery (under agent_root OR
    # tools=-co-located) so utility LLM calls are excluded, and attaches the
    # detected prompt to the consumer journey (agent_surface.system_prompts +
    # scan_meta.agent_surface.system_prompt). Detected by CONSUMPTION not the
    # token `prompt` — the langfuse `prompts` CRUD feature is never flagged.
    # Default ON since the agent-anatomy flip (2026-07-29, KEY_SCHEMA 44;
    # operator-ratified; offline-keyed RefApp proof). Unset ≡ explicit "1";
    # explicit "0"/"false"/"off"/"no" is the inverted kill-switch (census carries
    # no system_prompts, byte-identical), so cached entries must key on it.
    "WYSTAN_AGENT_SYSTEM_PROMPT",
    # Phase-3 agent-anatomy (2026-07-29) — agent SKILL-layer detection. Completes
    # the RefApp code-skills convention (a `skills/` module exporting
    # REQUIRED_TOOLS + ALWAYS_LOADED — the REQUIRED_TOOLS set links skill→tools)
    # and attaches the capability-skill layer to the consumer journey; detects a
    # cross-vendor `.claude/skills/*/SKILL.md` but classifies it DEV-TIME by path
    # and never attaches it to a product consumer (agent_surface.skills +
    # scan_meta.agent_surface.skill_layer). Most repos have no skill layer — an
    # honest zero. Default ON since the agent-anatomy flip (2026-07-29,
    # KEY_SCHEMA 44; operator-ratified; offline-keyed RefApp proof — 16 capability
    # + 12 persona skills, dev-time .claude classified not attached). Unset ≡
    # explicit "1"; explicit "0"/"false"/"off"/"no" is the inverted kill-switch
    # (census carries no skill_layer, byte-identical), so cached entries key on it.
    "WYSTAN_AGENT_SKILLS",
    # Phase-4 agent-anatomy (2026-07-29) — board-visible anatomy manifestation.
    # The static IMPORT-BRIDGE (repo files importing a mount-consumer module —
    # the endpoint→consumer edge the dynamic-dispatch flow graph misses) marks a
    # user-flow entering through an agent-invoking endpoint as an agent-consumer
    # journey and attaches the mounted anatomy (tools w/ per-tool LOC spans,
    # skills, prompt) as shared-member anatomy (agent_surface.anatomy +
    # scan_meta.agent_surface.anatomy_rows), 3-way labelled, product surfaces
    # kept separate. Turning it on implies the Phase 1-3 detection. Default ON
    # since the agent-anatomy flip (2026-07-29, KEY_SCHEMA 44; operator-ratified;
    # offline-keyed RefApp proof — 7 consumer journeys incl. the Chat journey, 68
    # tools + 28 skills + 13 prompts, LOC 68/68, surfaces kept separate). Unset ≡
    # explicit "1"; explicit "0"/"false"/"off"/"no" is the inverted kill-switch
    # (census carries no consumer_importer_files, byte-identical), so cached
    # entries must key on it.
    "WYSTAN_AGENT_ANATOMY_ROWS",
    # B87 rung-2 (2026-07-23) — product-right gate. Three mechanical
    # extensions of existing mint bars: (1) dev-standalone mint candidates
    # pass a NARROW bar (single_letter | version_dir | technology_instrument |
    # micro-LOC<100 demote — api_only_surface excluded); (2) the
    # fdir/ws-pkg/pypkg page fiat requires real evidence (UF ∨ nav ∨
    # page/authored-view-component ∨ flow); (3) a post-mint token-grain
    # journey re-home (stage 6.9965). Reshapes product_features[] (barred
    # maskeraders) + user_flows[] (re-homed journeys). Default ON since
    # flip-pack №6 (2026-07-23, KEY_SCHEMA 39; proof: keyless SAFETY B87 +
    # composition mid_A4 class-A kills named + re-home confirmed). The bump
    # rides the pack's FIRST flip commit (this one). unset ≡ explicit "1"
    # byte-identical; "0"/"false"/"off"/"no" restores the pre-B87 world
    # (inverted kill-switch forever), so cached entries must key on it.
    "WYSTAN_PRODUCT_RIGHT_GATE",
    # B89 rung (2026-07-23) — invariant stage-hooks. Pure sentinels that STAMP
    # scan_meta.invariant_hooks[] + a terminal scan_meta.product_right_census
    # when a known bug-class is present on its producer stage (a critical hook
    # also stamps a severity="failed" degradation). Additive telemetry only —
    # no product_features[] / user_flows[] reshape. Default ON since flip-pack
    # №6 (2026-07-23, KEY_SCHEMA 39; proof: byte-additivity [stripped==OFF
    # byte-ident] + 1:1 census-parity on 3 keyed boards). The bump rode the
    # pack's FIRST flip commit (PRODUCT_RIGHT_GATE). unset ≡ explicit "1"
    # byte-identical; "0"/"false"/"off"/"no"/"" restores the pre-B89 world
    # (inverted kill-switch forever), so cached entries must key on it.
    "WYSTAN_INVARIANT_HOOKS",
    # B90 Seg A (2026-07-24) — transport-donor PF lane: a PF whose anchor is
    # a TRANSPORT-shaped ws-package (the B88 TransportDonorResolver mechanism
    # — server/routers tree or @trpc/* dep) converts to a platform-
    # infrastructure lane resident post-UF; its real journeys become B52
    # lane-row references the 6.9965 token re-home resolves, synth backstops
    # drop named. Reshapes product_features[] + user_flows[] + the platform
    # lane on donor-carrying boards (cal.com ws:packages/trpc); donor-less
    # boards are byte-identical. Default ON since flip-pack №7 (2026-07-24,
    # KEY_SCHEMA 40; live keyed cal: PF tRPC ABSENT, 0 journeys in trpc,
    # conservation 139→139 named; KS byte-ident). The bump rode the pack's
    # FIRST flip commit (this TRANSPORT_PF_LANE commit). unset ≡ explicit "1"
    # byte-identical; "0"/"false"/"off"/"no" restores the pre-B90 world
    # (inverted kill-switch forever, NARROW {"1","true"} truthy set), so cached
    # entries must key on it.
    "WYSTAN_TRANSPORT_PF_LANE",
    # B90 Seg B (2026-07-24) — api-root-stub PF demote: a route: PF mounted
    # DIRECTLY at an api path segment (…/api/<leaf>) with zero product
    # evidence (no nav_parent, no authored view member — the mint's
    # api_only_surface-lift prongs re-checked at post-UF grain) AND a micro
    # journey profile (held <= 1, every member mc <= 3 — channel-robust:
    # keyed synth backstop OR keyless mc=1 route-echo) demotes by the
    # devgrain mechanics (PF removed, synth UFs drop named, REAL UFs ->
    # honest residual resolved by the 6.9965 token re-home,
    # devs fold to the surviving ancestor / I9 rider). Deep api routes
    # (api/<provider>/<leaf>) and evidenced api products never trip.
    # Reshapes product_features[] + user_flows[]. Default ON since flip-pack
    # №7 (2026-07-24, KEY_SCHEMA 40; live keyed cal: PF Link ABSENT, C6 micro-
    # profile channel-robust, anti-cases named [papermark Links / twenty File
    # Upload / midday Session-family alive], SACRED B48 intact). The bump rode
    # the pack's FIRST flip commit (TRANSPORT_PF_LANE); this flag flips in the
    # pack's SECOND commit. unset ≡ explicit "1" byte-identical;
    # "0"/"false"/"off"/"no" restores the pre-B90 world (inverted kill-switch
    # forever, NARROW {"1","true"} truthy set), so cached entries must key on it.
    "WYSTAN_API_STUB_DEMOTE",
    # B91 H4 (2026-07-25) — api-container discriminator: a CONTAINER-anchored
    # PF (dev:/fdir:/ws:/pypkg: — the shapes B90 Seg B never judged; route:
    # out of scope by the binding B91 ruling, hub: out by the integration
    # doctrine) demotes when ALL FIVE conjuncts hold: plumb_frac >= 0.8
    # (member files in route-handler/transport/dto/plumbing shapes — profile
    # FileRole + analyzer infra test + authored data-shape vocab), zero
    # authored view members, no nav_parent, no REAL member journey (synth
    # backstops never defend), and no B48 sacred protection (the mint's own
    # tech-instrument verdicts). Demote = the Seg B house mechanics (PF row
    # removed, synth UFs drop named, devs fold to ancestor / I9 / honest
    # unowned). Closes the operator pin refapp-api-dev-container. Reshapes
    # product_features[] + user_flows[] on diseased boards. Default ON since
    # flip-pack №8 (2026-07-27, KEY_SCHEMA 41; keyed novu proof: the dev:api
    # Dto container PF ABSENT, journey + B48 sacred vetoes protect 19
    # must-survive). The bump rode the pack's FIRST flip commit
    # (ROUTE_RENDER_UTIL_DEMOTE). unset ≡ explicit "1" byte-identical;
    # "0"/"false"/"off"/"no" restores the pre-B91 world (inverted kill-switch
    # forever, NARROW {"1","true"} truthy set), so cached entries must key on it.
    "WYSTAN_API_CONTAINER_DEMOTE",
    # B93 (2026-07-27) — route-render-util discriminator: a route:-anchored PF
    # whose PAGE surface is a BACKEND render helper (a non-view *page.{ts,js}
    # NON-marker leaf that falsely tripped the keyless App-Router page-suffix
    # gate — the exact FP that mints route:…/shared/html "HTML" on novu) is a
    # phantom product page, not a product feature. Demotes ⇔ route: anchor ∧
    # NOT an api-root-stub-leaf (B90 Seg B territory, binding B91 ruling) ∧ a
    # phantom-PAGE render-util member ∧ authored_view == 0 (LOAD-BEARING — a
    # real page HAS a view) ∧ no nav_parent/nav-key ∧ no substantive journey
    # (channel-robust micro-profile veto) ∧ no B48 sacred. Demote = the Seg B
    # / H4 house mechanics (PF removed, synth UFs drop named, real UFs ->
    # honest residual resolved by the 6.9965 token re-home, devs fold to the
    # surviving ancestor / I9 rider). Anti-cases (authored_view / journey
    # veto): plane Core (14 .tsx views), reactive-resume HTML/PDF export (real
    # journey), langfuse Batch Exports (dev: container, never eligible), any
    # real frontend page-route. Closes the operator pin novu-html-route-markup.
    # Reshapes product_features[] + user_flows[] on diseased boards. Default ON
    # since flip-pack №8 (2026-07-27, KEY_SCHEMA 41; keyless novu proof: the
    # phantom route:…/shared/html "HTML" PF ABSENT, HTML exhibit §7 CLOSED,
    # anti-cases survive). The bump RIDES this pack's FIRST flip commit (this
    # one). unset ≡ explicit "1" byte-identical; "0"/"false"/"off"/"no"
    # restores the pre-B93 world (inverted kill-switch forever, NARROW
    # {"1","true"} truthy set), so cached entries must key on it.
    "WYSTAN_ROUTE_RENDER_UTIL_DEMOTE",
    # B82 (2026-07-25) — Stage-3.5 span recovery for 1-LOC placeholder flows.
    # Form A (re-export follow-through) redirects a barrel-entry flow's graph
    # seed to the re-export target's REAL body; Form B (named-import callee
    # span recovery) replaces a null-span import file-node with the SPECIFIC
    # imported symbol's body range (never whole-file). Both mutate flow.nodes
    # → reshape flows[].nodes/line_ranges/loc + user_flows[] owned LOC on
    # affected boards. Master + two isolation sub-flags (different flip-
    # maturity: Form A ship-ready, Form B needs a keyed footprint proof).
    # Default OFF; =0/unset byte-identical (kill-switch pair). No KEY_SCHEMA
    # bump (a default flip is a separate later commit per flip-protocol).
    "WYSTAN_FLOW_SPAN_RECOVERY",
    "WYSTAN_FLOW_SPAN_RECOVERY_REEXPORT",
    "WYSTAN_FLOW_SPAN_RECOVERY_CALLEE",
    # Decorator-support call-graph edges (decorated method → decorator impl,
    # Python-only). Default ON since flip-pack №8 (2026-07-27, KEY_SCHEMA 41;
    # keyless tracecat proof: decorated method → decorator-impl edges
    # resolved). The bump rode the pack's FIRST flip commit
    # (ROUTE_RENDER_UTIL_DEMOTE). unset ≡ explicit "1" byte-identical;
    # "0"/"false"/"off"/"no" restores the pre-flip world (inverted kill-switch
    # forever), so cached entries must key on it.
    "WYSTAN_DECORATOR_SUPPORT_EDGES",
    # B92 (2026-07-25) — same-slug twin collision (two SAME-PF-guarded rungs).
    # Rung D (FLOW_DECOLLIDE): PF-namespace flow-name de-collision — reshapes
    # flows[].name/display_name/short_label (the operator-visible name channel).
    # Rung B (FEATURE_MERGE): merges dup-extraction twin dev features + dedups
    # flows by entry + absorbs fold-husks — reshapes developer_features[],
    # flows[], feature_flow_edges[] and, transitively, user_flows[]. Two
    # isolation flags (different flip maturity — Rung D leads; the B82
    # precedent). Default ON since flip-pack №8 (2026-07-27, KEY_SCHEMA 41;
    # keyed RefApp proof: Rung D de-collides same-slug flow names, Rung B merges
    # dup-extraction twins at θ=0.3 [8/8 must-merge caught, 8/8 anti-case
    # facets protected]). The bump rode the pack's FIRST flip commit
    # (ROUTE_RENDER_UTIL_DEMOTE). unset ≡ explicit "1" byte-identical;
    # "0"/"false"/"off"/"no"/"" restores the pre-B92 world (inverted
    # kill-switch forever), so cached entries must key on it.
    "WYSTAN_TWIN_FLOW_DECOLLIDE",
    "WYSTAN_TWIN_FEATURE_MERGE",
    # Rung B husk-canonical rescue + T5 b85 carve-absorb (operator exhibit
    # refapp-ticketing-twin-fragmentation): when Rung B's SAME-PF guard skips a
    # collision-suffix family because the base is a SHELL husk (pf=None) that
    # lost the 6.86 anchor competition, and EXACTLY ONE real sibling carries a
    # non-None pf, that sibling is promoted to canonical, the husk base +
    # same-pf fold-husks absorbed, and the base name freed (the -N suffix
    # disappears); the T5 leg makes the 6.996 b85 home-carve absorb into an
    # existing same-stem+pf dev instead of minting a suffixed row — reshapes
    # developer_features[], flows[], feature_flow_edges[] and, transitively,
    # user_flows[]. Default ON since flip-pack №14 (KEY_SCHEMA 49, 2026-07-31;
    # keyed proof RefApp — ticketing 3→1, loc=69). unset ≡ explicit ON; explicit
    # "0"/"false"/"off"/"no"/"" stays a kill-switch forever (inverted-
    # kill-switch unit) — the pre-fix world. Toggling it between two scans of
    # one tree must miss the cache, hence this entry.
    "WYSTAN_TWIN_HUSK_CANONICAL",
    # Security hardening (2026-07-26) — untrusted-repo input, two HIGH fixes.
    # Both default ON (unset ≡ armed). They are output-affecting ONLY on
    # MALICIOUS inputs — a repo committing an escaping symlink (H2) or a
    # homepage/repository.url that resolves to an internal address (H1). On
    # legitimate repos the walk/reads (H2) and the marketing fetch decisions
    # (H1) are byte-identical whether armed or off, so the default-ON flip is
    # output-neutral; registering them keeps a cached result from being
    # served across a kill-switch toggle. Appended WITHOUT a KEY_SCHEMA bump.
    #   H2 — wystan.analyzer.safe_read: skip symlinks whose target escapes
    #        the clone root (worker-secret read via a 120000 symlink).
    "WYSTAN_SYMLINK_CONTAINMENT",
    #   H1 — wystan.analyzer.marketing_fetcher: reject Stage-8 marketing
    #        fetches whose host resolves to a private/loopback/link-local/ULA
    #        /reserved IP (SSRF / cloud-metadata exfil); redirects re-validated.
    "WYSTAN_SSRF_GUARD",
    # B93 (2026-07-27) — nav section-landing demote: a nav-child PF that is a
    # section OVERVIEW/landing shell (nav_parent, non-self-ref, 0 real
    # journeys, ALL anchor files under a section-index segment — RefApp
    # 'Feature Studio') is demoted from the peer-feature tile; its member
    # devs re-home (ancestor → L1/unowned), held UFs drop. Reshapes
    # product_features[] + developer_features[].product_feature_id +
    # user_flows[]. Default ON since flip-pack №9 (KEY_SCHEMA 42, 2026-07-28;
    # exhibit-gate PASS — RefApp keyless 'Feature Studio' OFF 1 hit → ON 0 hits).
    # unset ≡ explicit ON; explicit 0/false/off/no stays a kill-switch forever
    # (inverted-kill-switch unit).
    "WYSTAN_NAV_CATEGORY_DEMOTE",
    # B94 (2026-07-28) — settings-frame demote: a top-level PF named after a
    # generic settings-frame TAB (general/settings/preferences/advanced/misc)
    # with 0-1 real journeys whose EVERY anchor file sits under a settings-
    # context ancestor (settings/account/preferences/admin — 'General' on
    # cal/papermark/plane/rallly) is demoted from the peer-feature tile; member
    # devs re-home (ancestor → L1/unowned), synthesized shell-UFs drop, a real
    # held journey re-homes to the ancestor. Reshapes product_features[] +
    # developer_features[].product_feature_id + user_flows[]. Default ON since
    # flip-pack №9 (KEY_SCHEMA 42, 2026-07-28; exhibit-gate PASS — 'General'
    # papermark OFF 1→ON 0 and plane OFF 1→ON 0). unset ≡ explicit ON; explicit
    # 0/false/off/no stays a kill-switch forever (inverted-kill-switch unit).
    "WYSTAN_SETTINGS_FRAME_DEMOTE",
    # B95 (2026-07-28) — capability SHARED-re-home: a top-level PF for a shared
    # MECHANISM (human-verify / file upload / search / notification — 'Captcha' /
    # 'File Upload' on twenty) with 0-low own journeys, a thin member set, NO own
    # product-surface (no nav entry), a route:/fdir: (non-ws:, non-SDK) anchor,
    # and low cross-feature fan-in is a capability, not a feature (operator
    # exhibit twenty-capability-as-pf). It is demoted from the peer-feature tile;
    # its flows become type=secondary members of consumer features' journeys via
    # feature_flow_edges, its member devs stay in developer_features as honest
    # residual (product_feature_id=None, files kept) — conservation by
    # construction. Reshapes product_features[] + developer_features[].
    # product_feature_id + flows[] + feature_flow_edges[] + user_flows[]. Default
    # ON since flip-pack №9 (KEY_SCHEMA 42, 2026-07-28; exhibit-gate PASS —
    # twenty OFF ['Captcha']→ON 0 hits, PF 52→50). unset ≡ explicit ON; explicit
    # 0/false/off/no stays a kill-switch forever (inverted-kill-switch unit).
    "WYSTAN_CAPABILITY_SHARED_REHOME",
    # B container-journey-rehome (Stage 6.9966): mints absent domain-PFs from
    # code-dirs and re-homes cross-domain journeys stuck on a structural
    # container (ws:/generic-bucket) by name; dissolves aggregates; demotes the
    # emptied husk product→dev; leaves the rest honest-residual. Reshapes
    # product_features[] + user_flows[].product_feature_id + member_files[].
    # Default ON since the 2026-07-29 flip (KEY_SCHEMA 42→43; keyed proof green
    # — hoppscotch Common + documenso General + twenty-server demoted, 0 orphan,
    # conservation whole). unset ≡ explicit ON; explicit 0/false/off/no stays a
    # kill-switch forever (inverted-kill-switch unit). Toggling it between two
    # scans of one tree must miss the cache, hence this entry.
    "WYSTAN_CONTAINER_JOURNEY_REHOME",
    # Seg E — TanStack file-based routes: the ``createFileRoute(
    # "/path")`` string literal in each route's own source file emits its URL
    # pattern (method=PAGE, kind=spa-page) into the ``spa-page`` source, so
    # capability journeys mint on TanStack SPAs whose paths live in code (not
    # a filesystem convention the stack tag would trigger). Repo-wide +
    # dep-corroborated via the shared ``_manifests`` shallow scan, so a
    # polyglot TanStack frontend that is not a detected workspace still
    # activates. Reshapes routes_index + spa-page candidates on armed worlds
    # only (infisical route-miss 293→0; 251 slugged routes). Default ON since
    # flip-pack №10 (KEY_SCHEMA 45, 2026-07-29; keyed proof — reactive-resume
    # TanStack PF + journeys born). unset ≡ explicit ON; explicit
    # 0/false/off/no keeps the arm un-entered, byte-identical — a kill-switch
    # forever (inverted-kill-switch unit; the family kill-switch
    # ``WYSTAN_SPA_ROUTER_ENTRIES=0`` dominates). Registered here so
    # toggling it between two scans of one tree misses the cache.
    "WYSTAN_DECLARATIVE_ROUTE_SCOPING",
    # B58 surface-scope recall: three additive husk-recall widenings of
    # the Stage-6.85/6.97 surface taxonomy — product-name-prefixed
    # workspace suffix (twenty-docs -> docs), the .storybook
    # design-system signal (plane packages/propel), and dev_artifact_tokens
    # wired to the general classifier at exact workspace/root grain. Moves
    # non-product husks out of product_features[] into
    # non_product_surfaces[] (journeys ride along), so cached scans must
    # key on it. Default ON since flip-pack №12 (KEY_SCHEMA 47,
    # 2026-07-29; keyed proof plane 5/5: Propel→non_product, 9 fake
    # per-widget journeys gone, States/Webhooks anchor-guarded; twenty
    # offline-proof suffix-arm — keyed run memory-blocked). unset ≡
    # explicit ON; explicit 0/false/off/no stays a kill-switch forever
    # (inverted-kill-switch unit). Toggling it between two scans of one
    # tree must miss the cache, hence this entry.
    "WYSTAN_SURFACE_SCOPE_RECALL",
    # C-track vue-flow-support — ``.vue`` SFC flow-candidate extraction
    # (wystan/analyzer/ast_extractor.py::_parse_vue_file). A ``.vue``
    # file was in NO accepted extension set, so it skipped before Stage 3
    # → 0 exports → the MIN_EXPORTS_FOR_FLOW_DETECTION short-circuit
    # guaranteed ``flows=[]`` on every Vue-front feature (hoppscotch
    # mockServer/collections/http/graphql; directus admin modules;
    # chatwoot front-end). With the flag ON the SFC ``<script setup>`` /
    # Options-API methods / template handlers become exports so those
    # features seed flows. Additive (more flows). Default ON since
    # flip-pack №10 (KEY_SCHEMA 45, 2026-07-29; keyed proof — hoppscotch
    # 295 vue-flows + graphql born). unset ≡ explicit ON; explicit
    # 0/false/off/no stays a kill-switch forever (inverted-kill-switch
    # unit; ``.vue`` unaccepted when OFF, byte-identical). Toggling it
    # between two scans of one tree must miss the cache, hence this entry.
    "WYSTAN_VUE_SFC_FLOWS",
    # Pin-cycle-3 M1 — capability mint-guard (Stage 6.9966 mint-gate leg): a
    # container-carved domain candidate is a CAPABILITY-MECHANISM, not a product
    # domain, and FAILs promotion (journey → honest-residual, never a peer tile)
    # when it owns no state-entity (no state-convention module named after it)
    # AND no structured schema sub-tree AND its core module is imported by the
    # request/transport machinery of another domain (inbound consumption-
    # direction fan-in). Reshapes product_features[] (a would-be minted PF is
    # absent) + user_flows[].product_feature_id/residual. Default ON since
    # flip-pack №11 (KEY_SCHEMA 46, 2026-07-29; keyed exhibit-gate hoppscotch
    # 8/8 green — Cookies gone, UF conserved). unset ≡ explicit ON; explicit
    # 0/false/off/no stays a kill-switch forever (inverted-kill-switch unit).
    # Toggling it between two scans of one tree must miss the cache, hence
    # this entry.
    "WYSTAN_CAPABILITY_MINT_GUARD",
    # Pin-cycle-3 M2 — ws-containment fold (Stage 6.9967): a ws:-anchored PF
    # whose anchor path is a STRICT directory-descendant of another ws:-anchored
    # PF's anchor path folds into the enclosing package PF — but only when every
    # journey it carries is REDUNDANT with the enclosing package's own scope (a
    # host/shell sub-component); a descendant contributing a DISTINCT product-
    # wide capability (journey-guard) is never folded. Members/paths/journeys
    # move to the enclosing PF (0 orphan). Reshapes product_features[] +
    # user_flows[].product_feature_id + member_files[]. Default ON since
    # flip-pack №11 (KEY_SCHEMA 46, 2026-07-29; keyed exhibit-gate hoppscotch
    # 8/8 green — Src Tauri gone, Hoppscotch Desktop born, UF conserved).
    # unset ≡ explicit ON; explicit 0/false/off/no stays a kill-switch forever
    # (inverted-kill-switch unit). Toggling it between two scans of one tree
    # must miss the cache, hence this entry.
    "WYSTAN_WS_CONTAINMENT_FOLD",
    # Draw-variance cure (Stage 6.9967 host-shell branch): a ws-descendant whose
    # member files are ~100% non-product-surface (ZERO web/app-source files — the
    # tauri src-tauri native shell) folds REGARDLESS of drawn journeys, curing
    # the src-tauri kept/folded flicker across keyed draws (the journey-guard
    # reads the draw-noisy UF layer). Default ON since flip-pack №14
    # (KEY_SCHEMA 49, 2026-07-31; keyed proof hoppscotch — src-tauri folded
    # stably on both draws). unset ≡ explicit ON; explicit 0/false/off/no
    # stays a kill-switch forever (inverted-kill-switch unit) ⇒ byte-identical
    # journey-guard-only world. Toggling it between two scans of one tree must
    # miss the cache, hence this entry.
    "WYSTAN_FOLD_HOST_SHELL",
    # Common Tier-2 draw-variance cure (Stage 6.9966-FM, file-sourced container
    # minting): an 8.9.5-eligible single-generic-components-blob container
    # (hoppscotch ``common``) decomposes into its file-domain PFs
    # DETERMINISTICALLY from the prompt-hash-CACHED 8.9.5 labels (byte-identical
    # across draws), curing the journey-driven decompose/skip flicker (K1 5
    # mints + demote vs K2 79 301-LOC blob survives). Mints one domain-PF per
    # component sub-domain leaf that passes the 6.9966 product-right + capability
    # guards AND the scale-invariant median-LOC floor (owned LOC >= the median
    # over ALL candidate label-domains; the sub-median tail stays residual on the
    # demoted husk), attaches held journeys by name, demotes the file-emptied
    # container.
    # Reshapes product_features[] + user_flows[].product_feature_id/residual +
    # developer_features[].product_feature_id + member_files[]. Runs BEFORE
    # 6.9966. Default ON since flip-pack №15 (KEY_SCHEMA 50, 2026-07-31; keyed
    # 2-draw closing proof hoppscotch — mint-set identical d1==d2 (PF 20==20,
    # diff ∅), Common demoted on both draws, 10 domains stable incl. history).
    # unset ≡ explicit ON; explicit 0/false/off/no stays a kill-switch forever
    # (inverted-kill-switch unit) ⇒ byte-identical pre-flip OFF-world. Toggling
    # it between two scans of one tree must miss the cache, hence this entry.
    "WYSTAN_CONTAINER_FILE_MINT",
    # Pin-cycle-3 M3 — module-shape route-stub demote (Stage 6.987b, nav-
    # independent): a route/fdir-anchored PF whose source module renders NO
    # component (a non-component .ts/.js exporting only helpers — no SFC, no
    # defineComponent, no default-exported page component, no JSX) with tiny LOC
    # and a micro journey profile (≤1 UF, member_count ≤1) is a plumbing route,
    # not a product surface — demote; its hallucinated journey → honest-residual
    # (never lost); devs re-point to the nearest surviving ancestor PF. Fires
    # even when nav_keys is empty (the Vue/keyless blind spot 6.987 abstains on).
    # Reshapes product_features[] + user_flows[].residual/product_feature_id.
    # Default ON since flip-pack №11 (KEY_SCHEMA 46, 2026-07-29; keyed
    # exhibit-gate hoppscotch 8/8 green — Enter Redirect gone, journey
    # honest-residual, UF conserved). unset ≡ explicit ON; explicit
    # 0/false/off/no stays a kill-switch forever (inverted-kill-switch unit).
    # Toggling it between two scans of one tree must miss the cache, hence
    # this entry.
    "WYSTAN_ROUTE_STUB_SHAPE",
    # Coverage-gaps Mechanism A (2026-07-29) — orphan-flow ATTACH (Stage
    # 6.9945): folds each unambiguous orphan-UI cohort into the single
    # co-located journey that owns its feature-dir, so build_orphan_flow_gaps
    # never stamps it. Reshapes user_flows[].member_flow_ids / member_count +
    # flows[].user_flow_id (and thus the emitted coverage_gaps[]). Default ON
    # since flip-pack №13 (KEY_SCHEMA 48, 2026-07-31; keyed proof RefApp —
    # 6 cohorts / 40 flows attached live, guardrails held). unset ≡ explicit
    # ON; explicit 0/false stays a kill-switch forever (inverted-kill-switch
    # unit). Toggling it between two scans of one tree must miss the cache,
    # hence this entry.
    "WYSTAN_ORPHAN_FLOW_ATTACH",
    # Coverage-gaps Mechanism B-v2 (2026-07-29, lead ruling) — loc_worthy
    # FILE-OWNER rescue in terminal classification: a loc_worthy gap row
    # whose residue resolves via the dev-ledger path ownership to EXACTLY
    # ONE real non-hollow PF dissolves into it (routes = corroboration
    # only; hollow-PF guard binding). Reshapes coverage_gaps[] + the
    # scan_meta.terminal_classification trace. Default ON since flip-pack
    # №13 (KEY_SCHEMA 48, 2026-07-31; units + offline proof — the RefApp
    # live world resolves to an honest exactly-one abstain, arm inert
    # there by its own guardrail). unset ≡ explicit ON; explicit 0/false
    # stays a kill-switch forever (inverted-kill-switch unit). Toggling
    # between two scans of one tree must miss the cache, hence this entry.
    "WYSTAN_ROUTE_JOURNEY_BACKSTOP",
    # Vue nav-key lift (nav_parent vue=True parse → nav_keys_from_nav_tree): the
    # nav_keys derivation unions the author's declared Vue/SFC nav tree
    # (HoppSmartLink target, ``to: fn('inbox_view')`` call-expr, ``:to="{name:…}"``
    # bindings, i18n-macro / dotted-key labels, ``defineModule`` registries) into
    # the board's nav_keys, so the 6.987 devgrain + api-stub demotes STOP
    # board-wide abstaining on Vue boards (whose weak-regex nav_pairs were empty).
    # Reshapes product_features[] / user_flows[] (via the un-abstained demotes) +
    # scan_meta.vue_nav_keys telemetry. Default ON since flip-pack №13
    # (KEY_SCHEMA 48, 2026-07-31; keyed proof hoppscotch — vue-nav un-abstain +
    # nav-lane demote green). unset ≡ explicit ON; explicit 0 (or anything
    # outside the wide truthy set) stays a kill-switch forever
    # (inverted-kill-switch unit): the vue=True parse is never entered and the
    # wiring is a no-op ⇒ byte-identical to the pre-flag engine. Toggling it
    # between two scans of one tree must miss the cache, hence this entry.
    "WYSTAN_VUE_NAV_KEYS",
    # Stage 6.97d (2026-07-31) — journey-level engineering metrics: stamps
    # the Feature-mirror metric family (total_commits/bug_fixes/
    # bug_fix_ratio/authors/health_score/health_confidence/health_basis)
    # on user_flows[] via proportional span-credit (owned lines / file
    # total lines). Default ON since flip-pack №14 (KEY_SCHEMA 49,
    # 2026-07-31; keyed proof RefApp — UF-metrics 86/86 journeys stamped).
    # unset ≡ explicit ON; explicit 0/false stays a kill-switch forever
    # (inverted-kill-switch unit) ⇒ inert, byte-identical user_flows[].
    # Toggling it between two scans of one tree must miss the cache —
    # hence this entry.
    "WYSTAN_UF_METRICS",
    # Stage 6.97e (2026-07-31) — PF-level owned-LOC rollup backstop: recomputes
    # ``loc`` for FALSY-``loc`` product features from the authoritative
    # one-owner-per-file path_index (owner dev's PF ⇒ owned LOC), curing the
    # member-ful-hollow "loc=0" trust-bug (RefApp ``findings`` 0 → real owned).
    # Default ON since flip-pack №14 (KEY_SCHEMA 49, 2026-07-31; keyed proof
    # RefApp — findings loc 0→6225, dashboards 0→7109). unset ≡ explicit ON;
    # explicit 0/false stays a kill-switch forever (inverted-kill-switch
    # unit) ⇒ byte-identical pre-stage loc. Toggling it between two scans of
    # one tree must miss the cache — hence this entry.
    "WYSTAN_PF_LOC_ROLLUP_FIX",
    # B96/B97 (flip-pack #16, 2026-08-02) + B98 (armed-only) — all three
    # shape the emitted product_features/user_flows/scan_meta layer
    # (post-UF husk-demote / emission hard gate / headless spine), so
    # cached results must be keyed on them like on any other
    # output-shaping flag.
    "WYSTAN_GENERIC_CONTAINER_DEMOTE",
    "WYSTAN_EMISSION_HARD_GATE",
    "WYSTAN_HEADLESS_PRODUCT_SPINE",
    # #3A (2026-08-03, default OFF — an append with no bump, per the law):
    # last-chance path-attach of None journeys; shapes user_flows[].pfid.
    "WYSTAN_ORPHAN_UF_PATH_ATTACH",
    # #3B-B1 (2026-08-03, default OFF — append with no bump): a synth-arm
    # final close for flow-rich 0-UF PFs; shapes user_flows[].
    "WYSTAN_FLOWFUL_FINAL_COVER",
    # #4 (2026-08-03, default OFF — append with no bump): tier-2 journey
    # re-parent; shapes user_flows[].product_feature_id.
    "WYSTAN_TIER2_JOURNEY_REPARENT",
    # B100 (2026-08-04, default OFF — append with no bump): a post-mint Law C
    # regrade of rows minted/renamed AFTER naming_contract
    # (uf_cases_split / agent_surface); shapes user_flows[].name_confidence
    # + name_evidence (+ scan_meta.postmint_rescore).
    "WYSTAN_UF_POSTMINT_RESCORE",
    # W1/C-A (2026-08-03, default OFF — append with no bump): the Law C
    # verb:member-lead-echo rung — the UF display's LEAD token echoing a
    # member flow name's LEAD token grounds the verb channel without the
    # 99-word action-family vocabulary. Shapes user_flows[].
    # name_confidence + name_evidence (UF NAMES byte-stable — B40 law).
    "WYSTAN_UF_MEMBER_LEAD_ECHO",
    # W2/E6 (2026-08-04, default OFF — append with no bump): routes_index
    # declaration-grammar arbitration — under a governed file-route root a
    # blanket Pass-B PAGE row survives only if the file declares a route
    # itself. Shapes routes_index[] + scan_meta.routes_decl_arbitration.
    "WYSTAN_ROUTES_DECL_ARBITRATION",
    # fixb103 (2026-08-04, default OFF — append with no bump): terminal
    # accounting for post-lane detachments — I12 re-match-else-null, a lane
    # row for a resident unbound by a late demote, a report on homeless UFs.
    # Shapes user_flows[].product_feature_id + platform_infrastructure[]
    # + features[].shared_reason (+ scan_meta.detach_accounting).
    "WYSTAN_DETACH_ACCOUNTING",
    # B105 FIX-2 (2026-08-04, default OFF — append with no bump): an honest
    # ``applied`` stamp for 6.86 on a ZERO mint of a product-app unit (all
    # anchors barred) — the deterministic cluster product layer survives
    # instead of finalize replacing it with []; library/cli-tool/
    # infra-daemon/framework stay applied=True (an empty product layer is
    # honest there). Shapes product_features[] + user_flows[] (6.7d goes
    # free-gen instead of anchored) on boards with pf_minted==0.
    "WYSTAN_MINT_EMPTY_HONEST",
    # C-B / fixb106 (2026-08-04, default OFF — append with no bump): the Law C
    # verb:repo-umbrella-lead rung — a generic (out-of-family) UF lead
    # grounded by the repo's OWN flow-name LEAD lexicon at a
    # scale-invariant floor max(2, ceil(0.025·|flows|)). Shapes
    # user_flows[].name_confidence + name_evidence (UF NAMES byte-stable —
    # B40 law) + scan_meta naming telemetry.
    "WYSTAN_UF_UMBRELLA_FLOOR",
    # fixb107 M1 (2026-08-05, default OFF — append with no bump): a
    # brand-canonical exemption for the R5-5 ``raw-identifier`` rung — a camel
    # boundary inside a token that polish_display_casing ITSELF mints from
    # brand_casing/known_acronyms YAML is no longer read as an identifier
    # leak (token-scoped, fall-through). Shapes user_flows[].name_confidence +
    # name_evidence (UF NAMES byte-stable — B40 law).
    "WYSTAN_BRAND_SHAPE_EXEMPT",
    # fixb107 M2 (2026-08-05, default OFF — append with no bump): a
    # paren-qualifier admit D1(PF corroboration)^D2(residue guard)^D3(base
    # clean) for the R5-5 ``paren-qualifier`` rung — a disambiguating qualifier
    # that Law-B uniqueness MINTED itself is no longer punished as a disease.
    # Shapes user_flows[].name_confidence + name_evidence (UF NAMES stable).
    "WYSTAN_PAREN_QUALIFIER_ADMIT",
    # fixb109 (2026-08-05, default OFF — append with no bump): a
    # donor-uncovering abstain in 6.9965 token_journey_rehome — a mirror of
    # the shipped 6.7d backstop guard (M1 last-real-journey; D2 double-duty
    # stop; D3 stop-verbs generate/connect; D6 synth-seed hold). Shapes
    # user_flows[].product_feature_id + scan_meta.token_journey_rehome.
    "WYSTAN_TJR_DONOR_GUARD",
    # fixb108 (2026-08-05, default OFF — append with no bump): Rails
    # route SUPPLY — ``rails-routes`` candidates carry explicit
    # (pattern, method, resolved_controller_file, line, handler) tuples,
    # so build_routes_index Pass A fills routes_index on a Rails board for
    # the first time (previously 0 Rails rows — the channel never arrived).
    # Shapes routes_index[] and all its consumers (verb:route-method,
    # structural:verb-composition, the 6.7e adjudicator, domain attribution,
    # the e2e seam). Riding with it are the R1/R2 verb-SNAP guards, armed by
    # the PRESENCE of handler rows (not by a flag) — a board with no Rails
    # supply is byte-identical at any value.
    "WYSTAN_RAILS_ROUTES_SUPPLY",
    # fixb108-v2 (2026-08-05, all default OFF — append with no bump).
    # Fix-3: the B98 headless majority counts FILES on BOTH sides (v4 counted
    # anchors against files, so route-anchor DENSITY from supply 31→269
    # wrongly judged chatwoot headless → api_stub/api_container_demote into
    # NULL + a ``headless_internal_package`` bar on dev:documents/dev:voice).
    # Shapes scan_meta.stage_6_86_anchored_mint.repo_has_pages.
    "WYSTAN_HEADLESS_SURFACE_RESCUE",
    # Fix-4: a class-token strip in journey names ('Receive webhooks
    # controller' → 'Receive webhooks'). Shapes user_flows[].name.
    "WYSTAN_CLASS_TOKEN_STRIP",
    # Fix-2: a meaningful qualifier instead of a numeral on a PF display
    # collision (kind×scope: 'Webhooks 2' → 'Webhooks (API)'). Shapes
    # product_features[].name/display_name in the B24 nav-rehome mint.
    "WYSTAN_PF_COLLISION_QUALIFIER",
    # v3(b): fold coherence — the journey of a folded page-grain PF either
    # re-homes into the receiving product or becomes an honest coverage_gap.
    # Shapes user_flows[].product_feature_id + coverage_gaps[].
    "WYSTAN_FOLD_COHERENCE",
    # B111: dissolution conservation — a dev whose own PF tile the 6.86 mint
    # folded, and whose flow cohort was left with no coherent journey, becomes
    # a typed coverage_gap (kind="dissolved_journey") + an invariant hook.
    # Shapes coverage_gaps[] + scan_meta.fold_conservation/invariant_hooks.
    "WYSTAN_FOLD_CONSERVATION",
    # B112: emission of an adjudicator-demote gap — an admission carve in the
    # B68 ladder (the row is judged and STAYS) + a coordinate gate on the
    # demote itself (with no spans the demote refuses and the row stays a UF).
    # Shapes coverage_gaps[] + user_flows[] + scan_meta.adjudicator_6_7e.
    "WYSTAN_DEMOTE_GAP_EMISSION",
    # fixb114 / P12-M1: a two-way re-rollup of pf.loc on FINAL membership
    # (Stage 6.9975) — a replay of the 6.97 law over the ledger 6.97 removed.
    # Shapes product_features[].loc/loc_shared/loc_flow/artifact_ink_loc,
    # features[] product duplicates + scan_meta.loc_accounting.sum_pf_owned.
    "WYSTAN_PF_LOC_REROLL",
    # fixb114 / P12-M2: a coordinate lineage rung in 6.997a (the B102 family)
    # — a victim with no ``merged_from`` resolves by an IDENTICAL span set (or
    # a single container) among live flows + named abstain accounting.
    # Shapes user_flows[].member_flow_ids/member_count (⇒ loc/metrics,
    # I14 backpointers) + scan_meta.uf_member_exists.
    "WYSTAN_UF_MEMBER_COORD_LINEAGE",
    # B113 (fixb113, 2026-08-06, both default OFF — append with no bump).
    # The headless-rescue class gate: the flow-evidence rung (flip #24)
    # inverted the B98 spine on a NON-product-app class (ollama infra-daemon:
    # 2 webview-satellite page files against 43 route anchors → repo_has_pages
    # =True → every anchor barred api_only_surface + suppression never lifted
    # → 0 PF/0 UF silently). Armed — the rescue is a product-app rung ONLY.
    # Shapes scan_meta.stage_6_86_anchored_mint.repo_has_pages/
    # headless_majority ⇒ product_features[] + user_flows[].
    "WYSTAN_HEADLESS_RESCUE_CLASS_GATE",
    # The silent-emptiness sentinel: a mint that CLAIMED a product universe
    # (applied) on route-anchor material and minted ZERO PFs with no
    # degradation at all. Shapes scan_meta.invariant_hooks[].
    "WYSTAN_MINT_SILENT_EMPTY_SENTINEL",
    # fixb115 / M3a (P13): in the Stage 3.5 degrade branch (stacks outside
    # _T1_SUPPORTED_SUFFIXES — .rb/.vue) a point anchor (entry,entry) is
    # widened to the body of the enclosing method/function via the engine's
    # D1 helper. Shapes flows[].nodes[].lines + flows[].entry → flow LOC,
    # UFs and path_index derivatives.
    "WYSTAN_SPAN_WIDEN_DEGRADE",
    # fixb115 (data side): .rb symbol_ranges are computed by keyword-depth
    # end matching (ruby_def_spans, precedent go_func_spans) instead of the
    # heuristic "end = next_symbol − 1". Shapes symbol_ranges for
    # .rb → flow spans, Stage 3 start lines and symbol hashes.
    "WYSTAN_RUBY_DEF_SPANS",
    # fixb118: the B78 Seg B landing (rung ``affinity-rehome``) becomes
    # BINDING for later writers. (a) ``tier2_journey_reparent`` abstains when
    # it pulls a journey OFF a Seg B landing (its channel is the
    # ``dev.product_feature_id`` owner map that B78 calls a poisoned
    # annexation); (b) forced demote moves are not blocked but classified by
    # the emit-time landing audit. Shapes
    # user_flows[].product_feature_id on boards carrying the class, and adds
    # scan_meta.landing_audit. Unset ⇒ registry None ⇒ both branches
    # dead ⇒ byte-identical (KS 4-way kill-switch forever).
    "WYSTAN_SEGB_LANDING_BINDING",
    # fixb119 M1: the journey-lineage audit. A snapshot of ``user_flows[]`` at
    # the seam IMMEDIATELY AFTER ``journey_lattice`` + an emit-time
    # reconciliation of every dead row against KNOWN deletion channels
    # (id tier, then name tier), netting RE-IDs and abstains. The board does
    # not change — only ``scan_meta.journey_lineage_audit`` + a WARN record in
    # ``invariant_hooks[]`` are added. Unset ⇒ registry None ⇒ no snapshot, no
    # reconciliation, no key ⇒ byte-identical (KS 4-way kill-switch forever).
    "WYSTAN_JOURNEY_LINEAGE_AUDIT",
    # fixb122 (A): AR associations/scopes (``has_many :foo``, ``scope :recent``)
    # live in ``sig.exports`` but had NO ``symbol_range`` at all — neither in
    # the legacy branch nor in ``ruby_def_spans`` — so Stage 3 defaulted their
    # start line to 1. Mints a 1-line range ONLY for a name with NO existing
    # range (a real def always wins: anti-cases
    # budget_category.rb ``category`` 44 vs belongs_to:5 and
    # rule/condition.rb ``rule`` 14 vs belongs_to:2). Shapes
    # symbol_ranges for .rb → flow entry lines (9 rows on the capture).
    "WYSTAN_RUBY_ASSOC_RANGES",
    # fixb122 (B1): if the LLM's ``symbols[0]`` resolved to a CONTAINER
    # (class/module), the flow anchor moves to the first SAME-FILE callable
    # symbol in the list (the class is the fallback). The file never changes
    # (``symbol_to_loc`` is a global per-feature map: ``perform`` exists in
    # 271 chatwoot files). Shapes flows[].entry_point_line → nodes[].lines
    # via degrade-widen → LOC. Identity where the anchor is already on a body
    # (626/626 real-def) and outside class-symbol stacks (0/5952 TS/Vue).
    "WYSTAN_FLOW_ANCHOR_METHOD_PREF",
    # fixb124 (E1): an ownership gate on a metric's evidence basis. A row
    # whose owned files (``path_index`` — one owner per file) produced no
    # commit emits its metrics as null + ``metrics_abstained`` instead of the
    # history tuple of SOMEONE ELSE'S file (ollama: 7 husk PFs sharing one
    # 82.0/63.0/94) or an unearned 100 at commits=0 (maybe 47/47).
    # Shapes the metric family of product_features[]/developer_features[]/
    # features[] + scan_meta.metrics_ownership_gate.
    "WYSTAN_METRICS_OWNERSHIP_GATE",
    # fixb125: CLI anchor supply. A cluster of CLI commands passing gate
    # G1 (P0 import-binding ∧ P1-strict declared-bin-resolves-into-
    # cluster) supplies command anchors (registration file:line + command
    # name) into its dev unit's lineage at four exits of the 6.86 ladder
    # (span-annex / walk-annex / the B22a lane / the no_anchor_lineage
    # lane). The unit moves from platform_infrastructure onto the product
    # map (+1 PF per CLUSTER): caddy cmd, ollama cmd+launch, tracecat
    # tracecat-admin, lobe-chat cli, unkey api. Shapes
    # product_features[] + features[].product_feature_id/shared_reason
    # + scan_meta.stage_6_86_anchored_mint.cli_anchor_supply.
    "WYSTAN_CLI_ANCHOR_SUPPLY",
    # fixb127 (E1-flow): the flow layer of the same gate. A flow's git family
    # was NEVER measured (29460/29460 rows on 34 boards carry a constructor
    # tuple: ``health_score=80.0`` as a LITERAL with total_commits=0/authors=[]/
    # last_modified=epoch — a flow equivalent of ``_finalize_feature_metrics``
    # exists), so the ownership predicate is trivially true and the row
    # abstains WITHOUT counting ownership: total_commits/bug_fixes/
    # bug_fix_ratio/last_modified/health_score → null +
    # ``metrics_abstained='no_basis'`` in BOTH views (flows[] and
    # features[].flows[]). coverage_pct/loc/hotspots untouched. Shapes the
    # flows[]/features[].flows[] metric family + its key. Nested under parent.
    "WYSTAN_METRICS_OWNERSHIP_GATE_FLOWS",
    # fixb130 NS-E / NS-2-JS (2026-08-08, default OFF — append with no bump):
    # synth display hygiene. A synth row takes its name from pf.display_name /
    # a route-group label VERBATIM, so it carries shapes banned everywhere
    # else: a phrase echo ('Browse & manage server (server)', 'Access billing
    # portal portal'), a bracket opened on a space ('( Project)'), and raw
    # PascalCase identifiers ('AuthResponse', 'View ApiTokens ListView',
    # 'Auth page Layout') that do not even EARN the
    # ``shape:raw-identifier`` stamp, so the R5-5 cap never reaches them. The
    # echo law is ONLY the adjacent-echo segment of the degrime (the full
    # degrime was measured on KS66: 6 repairs and 1 DAMAGE — langfuse UF-152
    # loses 'URL'). Paren-space is pure whitespace normalisation, so it runs
    # on ALL rows. Shapes user_flows[].name + user_flows[].name_evidence.
    "WYSTAN_SYNTH_DISPLAY_HYGIENE",
    # fixb130 bonus pin (2026-08-08, default OFF — append with no bump):
    # Law-B narrowing writes 'View <res>' instead of 'Browse <res>' when EVERY
    # member leads with a literal ``view`` (the vocab folds view→browse with no
    # id marker, so novu/jsonhero got 'Browse' over all-view membership).
    # Shapes user_flows[].name.
    "WYSTAN_UF_VIEW_LEAD_PIN",
    # fixb131 Seg A (2026-08-08, default OFF — append with no bump): the
    # VERB arm of law L-C2 (``uf_synth_fold.has_verb_stutter``) only asked "is
    # the second word in the template-verb vocabulary", and English writes most
    # product nouns as verbs — so the arm ate noun MODIFIERS
    # ('Track search analytics' -> 'Track analytics'; reactive-resume lost
    # 'resume' on 8/36 journeys; 'Bulk delete links' -> 'Bulk links' = the root
    # of the 'Bulk Records' class). Measured on 31 KS66 captures: 36 firings, 0
    # correct. The guard = three banked questions (the lead's provenance; does
    # THIS repo name the token as an action in its own flow names; is the token
    # not the row's resource). Shapes user_flows[].name.
    "WYSTAN_UF_VERB_ARM_MODIFIER_GUARD",
    # fixb133 M1 (2026-08-08 armed; default ON since flip-pack #35 2026-08-09,
    # KEY_SCHEMA 68 — warden #38 GO): route-MARKER
    # display sanitize. Router markers no rung stripped were reaching the
    # DISPLAY channel: intercepting `(.)sessions`, the parallel slot `@modal`,
    # escaped literals `robots[.]txt` / `[.]well-known`, the regex residue
    # `[-htmltopdf]+`; plus a veto on an organisational route group as a
    # qualifier ('Auth (Use Page Wrapper)'). Shapes pf[].display_name.
    "WYSTAN_ROUTE_MARKER_DISPLAY_SANITIZE",
    # fixb133 M2 (2026-08-08 armed; default ON since flip-pack #35 2026-08-09,
    # KEY_SCHEMA 68 — warden #38 GO): the rung
    # `static-route-qualified` in the B71 ladder — a one-word base whose sense
    # lives in its parent gets its OWN anchor evidence ('shares' under
    # `boards/[boardId]` -> "Board Shares"; 'performance' under `(reports)` ->
    # "Performance Report"), + N7 stutter dedup at the hub-compose site
    # ("App Store — App Store — Attio"). Shapes pf[].display_name.
    "WYSTAN_PF_ROUTE_QUALIFIER_RUNG",
    # fixb133 M3 (2026-08-08 armed; default ON since flip-pack #35 2026-08-09,
    # KEY_SCHEMA 68 — warden #38 GO): a universal
    # display lexicon (data/display-lexicon.yaml) — a whole cleaned base that
    # IS an opaque abbreviation or deictic expands ('sso' -> "Single
    # Sign-On", 'me' -> "My Account"), and an initialism inside a phrase renders
    # upper-case ('SSO' vs 'Utm'). A WHOLE segment, never a substring ('API Key'
    # survives). Shapes product_features[].display_name.
    "WYSTAN_PF_DISPLAY_LEXICON",
    # fixb134 M4a (2026-08-09 armed; default ON since flip-pack #36
    # 2026-08-09, KEY_SCHEMA 69 — warden #40 GO): the mint-time
    # collision qualifier NEVER composes a self-repeating pair again
    # ('Alby (alby)' in the display AND in the slug). Instead: a distinguishing
    # ancestor ('Alby (Integrations)'), otherwise the existing uniqueness ladder.
    # Shapes product_features[].name + .display_name at mint time.
    "WYSTAN_MINT_QUALIFIER_NO_SELF",
    # fixb134 M4b (2026-08-09 armed; default ON since flip-pack #36
    # 2026-08-09, KEY_SCHEMA 69 — warden #40 GO): an emission-stage
    # migration of dirty pf.name values (marker residue in the JOIN ID:
    # '(.)sessions', '@slot', 'robots[.]txt', '[-htmltopdf]+',
    # 'alby-(alby)'). Rename + a dev/uf product_feature_id re-stamp in the SAME
    # pass (law E3a); anchor_id untouched. Shapes
    # product_features[].name and both product_feature_id channels.
    "WYSTAN_PF_SLUG_SANITIZE",
    # fixb134 M4c (2026-08-09 armed; default ON since flip-pack #36
    # 2026-08-09, KEY_SCHEMA 69 — warden #40 GO): the R5-1
    # identity-parity REPAIR no longer returns a self-repeating display.
    # The repair's first rung is the humanised OWN slug, so while the slug is
    # still dirty ('alby-(alby)'; M4b migrates the id at emission, i.e. LATER),
    # the repair handed the stutter straight back. Armed, it refuses such a
    # candidate and repairs from the DISTINGUISHING ancestor
    # ('Alby (Integrations)'), whose fold != the sibling's slug, so parity is
    # SATISFIED, not weakened. Shapes product_features[].display_name.
    "WYSTAN_R5_REPAIR_NO_SELF",
    # fixb132 (2026-08-09, default OFF — append with NO bump): authored
    # component-name de-glue on the UF layer. A journey whose display IS a code
    # identifier ('AdminTeamPage', 'PixelShareForm') or a Title-Case phrase
    # with a dev-grain tail ('Teams Page', 'Test Console Page') is re-derived
    # from the WORDS that identifier itself declares, BEFORE
    # Law C — so the row is scored by the name it really carries (verb ∧
    # resource ⇒ high; resource only ⇒ an honest medium with a readable
    # name). A verb is never invented: rung (a) takes the identifier's own
    # lead only under the #34 modifier guard + member grounding, and
    # rung (b) writes a READ verb only when the member composition already
    # grounds it, otherwise the phrase goes verbless. NS guard: a display that
    # matches its PF's authored nav phrasing is untouched.
    # Shapes user_flows[].name and (through Law C) .name_confidence /
    # .name_evidence. The PF layer is untouched.
    "WYSTAN_UF_COMPONENT_NAME_DEGLUE",
    # fixb135 (2026-08-10 armed; default ON since flip-pack #38
    # 2026-08-10, KEY_SCHEMA 71 — warden #42 GO): owner-ledger
    # reconciliation. flow_span_split writes file→PF ownership onto a flow
    # (shared_paths.owner_product_feature/owner_display) in the MIDDLE of the
    # pipeline; later renames/demotes leave it stale (world:
    # 15 repos nonzero — umami 309 'settings', cal 161+, highlight/strapi/
    # plane in the thousands). A pass at emission rebuilds the map from the
    # FINAL rows and re-resolves every owner; the unresolvable are counted honestly.
    # Shapes flows[].shared_paths[].owner_product_feature + owner_display.
    "WYSTAN_OWNER_LEDGER_RECONCILE",
    # fixb136 (2026-08-10 armed; default ON since flip-pack #39 2026-08-10,
    # KEY_SCHEMA 72 — warden #43 GO): the L-C1/L-C3 canonical
    # choice of the fold asks the VERB CLASS first, not the name's richness.
    # Write/manage (create/update/delete/act) > read (browse/view); on an
    # equal class, the banked rich tiebreak byte-for-byte. The class is read
    # from the row's ORIGINAL name: a rename may not crown itself.
    # The cause was measured by the fixb132 executor: a de-glued READ row
    # ('Browse admin websites') outweighed the WRITE journey beside it
    # ('Create & edit websites') and ate it — five journeys on one umami pair.
    # Shapes user_flows[] (who survives the fold) and, through the member
    # union, the winner's member_flow_ids.
    "WYSTAN_FOLD_CANONICAL_VERB_PRIORITY",
    # fixb138 / NS-43b Half 1 (2026-08-10, default OFF — and it STAYS OFF
    # INDEFINITELY): a VERBLESS journey name does not carry 'high'.
    # Warden #43: umami UF-025 'Pixel share' sits at high on
    # ['structural-route','resource:route'] — with no verb:* stamp at all.
    # Root: `base_verb = (lead in mfams) or (lead is None and
    # len(mfams) >= 1)`, and the `lead is None` hand does NOT DISTINGUISH a
    # "generalised verb" (Manage/Overview — it abstracts, it does not
    # over-promise) from "there is NO verb at all" ('Pixel' — a noun).
    # MECHANISM (positive proof, not absence from a list): the lead token IS
    # the row's OWN resource noun (the pools base_res itself reads —
    # _toks(_res(uf)) | _toks(_pfd(uf))). The verb table remains ONLY
    # corroboration: a hit short-circuits to verb-led, a miss asserts
    # nothing.
    # WHY NOT FLIPPED: a cold triage census of 52 boards — 20 firings,
    # 8 correct (the UF-025 class), 12 residual (5 × the PF display is itself
    # a verb phrase and donates a verb into the pool; 7 × a resource noun
    # that verbs: chat/scan/tag/launch/push, which the table does not know).
    # 8 correct against 12 wrong is a NET LOSS of honesty on the honesty
    # lane. The mechanism stays ARMED (and is observed eval-side as a
    # TRACK detector), the census is banked in the predicate's docstring.
    # It also holds the round-1 net (a cap lift ≠ proof) in postmint_rescore.
    # Shapes user_flows[].name_confidence (UF NAMES byte-stable — B40).
    "WYSTAN_VERBLESS_NO_HIGH",
    # fixb138 / NS-43b Half 2 (flip-pack #40, 2026-08-10, default **ON**,
    # KEY_SCHEMA 73 -> 74): EVIDENCE HONESTY. A verb-led journey name whose
    # name_evidence carries NO verb:* tag at all receives 'verb:name-lead'.
    # This is not a new score but a correction of an UNDERSTATEMENT: Law C
    # grounded the row through the coarse 'structural-route' rung
    # (base_res ∧ base_verb) and simply never minted the granular tag.
    # CORROBORATION-ONLY: the stamp rides a HIT in the engine's own verb
    # table (r5_vocab_sets(...)['verbs'], the same _fold as in
    # unresolved_dir_token) — on a word the table does not know it cannot
    # fire. GRADE-INERT: it NEVER moves name_confidence; a verb-led 'low' is
    # stamped and stays 'low'. Abstains when B40 rungs are off (vacuum).
    # MEASURED: 2136 stamps on 52 boards, zero grades moved.
    # An explicit "0" is a kill-switch FOREVER (evidence byte-identical).
    # Shapes user_flows[].name_evidence.
    "WYSTAN_VERB_NAME_LEAD_STAMP",
    # fixb140 (flip-pack #41, 2026-08-10, default **ON**, KEY_SCHEMA
    # 74 -> 75) — LANE DELETION, operator ruling option A. A journey the
    # lane move took out of ``user_flows[]`` and whose member flows left
    # the journey layer ENTIRELY (``member_absorbed 0.00``) is DELETED
    # rather than left as a ``scope=marketing`` shell in
    # ``non_product_surfaces[].user_flows[]``: a member-less shell is the
    # hollow-rows disease. The permanent trace is id-tier and FULL, uncapped
    # (lead ruling 2026-08-10): ``surface_taxonomy_emission.lane_deleted_ids``
    # + the neighbouring ``lane_deleted`` with the NAMES of every deleted
    # row, plus ``journey_lineage_audit.lane_moved[].row_deleted``
    # (+ the M6 per-writer self-report), so the death stays ``id_bound``
    # rather than a silent vanishing; the marketing CODE stays visible in
    # its own board section (the lane row keeps paths/member_devs/loc).
    # MEASURED WORLD (a fresh census of 55 cold boards, NOT the spec 13 =
    # a subset of the 8-pair gate): 31 boards / 360 lane rows, 356 deleted,
    # 4 kept. ANTI-CASE: a partially absorbed row (``member_absorbed > 0``)
    # is NOT deleted — including the world's only ``== 1.00`` (better-auth
    # UF-034), a spec literal per the ruling. Shapes
    # ``non_product_surfaces[].user_flows[]`` ⇒ the cache must key on it.
    # An explicit "0"/false/off/no is a kill-switch FOREVER (the lane
    # payload is byte-identical to the pre-flip one).
    "WYSTAN_LANE_MOVED_DELETE",
    # fixb145 lane 1 (2026-08-11) — un-synthesize AUTHOR-DECLARED CLI command
    # journeys at the pre-output seam. A cobra ``Short:`` / commander
    # ``.description()`` sentence is a scan FACT read out of the command's own
    # registration site, not a coverage claim: ``naming_contract`` already
    # carves these rows out of the B78-it2 confidence cap (fixb128 NS-2) and
    # 27 of the 31 in the world already read ``high``. Keeping
    # ``synthesized: true`` on them was the sole cause of the +0.80pp
    # journey-denominator inflation (their ``high`` sat in the numerator while
    # the rows were excluded from the denominator). ``synthesis_reason`` is
    # KEPT — provenance survives, the claim does not. ANTI-CASE: a
    # ``cli-template`` row (author declared NO summary ⇒ the ENGINE composed
    # ``<Verb> <bin>``) is NEVER converted — novu 'Sync novu' / 'Connect novu'
    # / 'View dev' / 'Manage wizard' (telemetry ``named_template: 4``) stay
    # synthesized. Shapes ``user_flows[].synthesized`` ⇒ the cache must key on
    # it. Default OFF; unset/"0" ⇒ byte-identical.
    "WYSTAN_CLI_JOURNEY_UNSYNTH",
    # fixb145 — the B78-it2 synth confidence cap, split off its Seg-A rider.
    # UNSET ⇒ reads WYSTAN_FOLD_EVIDENCE_WEIGHT (byte-identical to
    # pre-fixb145 in BOTH of that flag's states); explicit "0" is the cap's
    # own kill-switch and disarms ONLY the cap, leaving the 6.86
    # walk-evidence gate as configured. Shapes user_flows[].name_confidence
    # / name_evidence ⇒ the cache must key on it.
    "WYSTAN_SYNTH_CONF_CAP",
    # fixb145 lane 2 (2026-08-11) — guarded synth CONVERSION. Armed, a
    # synthesized row is graded by the ordinary Law C rubric instead of being
    # hard-stamped low+['synthesized'], and drops ``synthesized`` when it
    # earns ``high`` AND clears BOTH ratified guards: (1) NS-43a PF-echo
    # refusal via the engine's own uf_synth_fold.is_pf_echo oracle; (2) per-PF
    # quota — converted <= max(1, real journeys the PF already holds),
    # scale-invariant. MEASURED (cap OFF/ON replay pairs, infisical+langfuse+
    # teable, 200 board-aligned rows): 171 (85.5%) earn high on their own
    # evidence, 0 name drift, 0 drift on the 282 non-synth rows; guard 1
    # refuses 55, guard 2 collapses infisical's 36-row one-PF spray.
    # ANTI-CASE: langfuse 'Receive encryption' / teable 'Manage field' (PF
    # echo) and cal.com UF-015 'Manage booking references' (echo) are NEVER
    # converted by this lane — the rename lane for those is PARKED.
    # Shapes user_flows[].synthesized + name_confidence ⇒ cache keys on it.
    # Default OFF; unset/"0" ⇒ byte-identical.
    "WYSTAN_SYNTH_CONVERSION",
    # fixb146 (2026-08-11, default **OFF** — append with NO bump): the ARMED
    # half of the M3 lexicon. `WYSTAN_PF_DISPLAY_LEXICON` is already default
    # ON, so a new entry placed straight into `expansions:` would move
    # displays on EVERY board while the cache key stayed the same — that key
    # hashes KEY_SCHEMA + repo identity + engine version + the VALUES of
    # these flags, and NEVER the bytes of the YAML itself (a warm cache hit
    # would hand back a pre-edit board on a post-edit engine — the
    # audit-Bug-2 form). KEY_SCHEMA moves only in a flip commit, so the
    # honest carrier for an ADDITION to the lexicon is its own flag:
    # `armed_expansions:` merge over `expansions:` only while it is
    # truthy. MEASURED WORLD (census world-77, 54 boards): the single armed
    # entry `ui: User Interface` touches 3 PFs on 3 boards (dub 'UI'
    # ws:packages/ui, twenty 'Ui' container-rehome:ws:.../ui, unkey 'UI'
    # ws:web/internal/ui) — the canon class `short_name` (alnum <= 2).
    # ANTI-CASES: 'API Key' / 'UI Kit' stay whole (the WHOLE-segment law),
    # authored nav/manifest labels untouched (route-derived tiers only).
    # An explicit "0"/unset is a kill-switch FOREVER (the lexicon = the
    # pre-fixb146 table byte-for-byte). Shapes pf[].display_name.
    # FLIP-PACK #43 (2026-08-11, KEY_SCHEMA 77 -> 78): the `ui` entry was
    # PROMOTED into `expansions:`; the carrier remains for the next addition
    # and is empty for now — the flag governs NOTHING (the merge is a no-op).
    # The entry's own kill-switch is now WYSTAN_PF_DISPLAY_LEXICON=0.
    "WYSTAN_PF_LEXICON_ARMED",
    # fixb146 Row 2 (2026-08-11, default **OFF** — append with NO bump):
    # a PRODUCT-EVIDENCE discriminator for the canon class `ws_anchor_no_uf`.
    # The class was written to catch a STRUCTURAL CONTAINER posing as a
    # product, but the predicate ("a ws: anchor AND zero unsynthesised
    # journeys") also condemns a REAL product surface whose journeys the
    # engine honestly backstopped. Live exhibit (onyx KS77):
    # `onyx-chat-widget` (ws:widget) holds UF-087 — synthesized, but with 5
    # member flows; the binding canon of product grain says a genuine feature
    # with no journeys is MARKED with an honest gap, not deleted. Operator
    # ruling 2026-08-11 (option 2): spare a ws-PF with positive PRODUCT
    # EVIDENCE by reusing the prongs of the neighbouring seed hook
    # `check_pf_ws_container_no_uf` — ONE shared helper
    # `has_product_evidence`, so the two cannot drift apart.
    # DELIBERATELY not cased on the `synthesized` tag: the fixb145 lane makes
    # it DYNAMIC (converted rows drop it), and the class would re-trigger by
    # accident as conversions land.
    # THE GRAIN LAW: on the BOARD `pf.flows` is ALWAYS empty — flows live on
    # the developer layer, so the flow prong is read through membership
    # (developer_features[].product_feature_id). Reading `pf.flows` here would
    # make the discriminator a no-op on its own exhibit (onyx: 0 pf.flows,
    # 7 flows through 5 member dev features).
    # MEASURED (dub KS77): 3 ws rows -> 1; `ui` (468 paths, authored .tsx)
    # and `com.example.dub` (views/AppSettings.tsx) are spared;
    # `dub-cli` REMAINS (0 authored views, 0 flows, 0 nav) — the class still
    # works, this is not an amnesty.
    # Shapes scan_meta.product_right_census + invariant_hooks[].
    # FLIP-PACK #43 (2026-08-11): default **ON**, KEY_SCHEMA 77 -> 78.
    # An explicit "0" is a kill-switch FOREVER (pre-fixb146 predicate exact).
    "WYSTAN_WS_EVIDENCE_DISCRIMINATOR",
    # fixb143 (i-a) — published-product-artifact PRODUCT veto. A workspace
    # whose manifest declares ``bin`` OR ``publishConfig`` and is NOT
    # ``private: true``, and which is NOT a Storybook design system, is a
    # shipped artifact customers install/embed ⇒ its paths vote PRODUCT at
    # top precedence, beating the instrument / B28 dev_artifact rungs (the
    # channel that laned trigger.dev ``packages/cli-v3`` — package name
    # ``trigger.dev``, bin+publishConfig — and deleted its 8 CLI journeys).
    # Measured TRUE A/B over the 294-row world lane census: 3 lanes move
    # (trigger.dev, novu js, novu react = 39341 LOC / 11 journeys), 291
    # unchanged. Shapes ``non_product_surfaces[]`` + ``product_features[]``
    # ⇒ must key the cache. Explicit "0"/false/off/no = kill-switch.
    # FLIP-PACK #45 (2026-08-13): default **ON**, KEY_SCHEMA 79 -> 80.
    # PROOF (keyed trigger.dev, round-5 pair): the round-3 destination
    # precondition ABSTAINS on this board, so ON ≡ OFF byte-for-byte in EVERY
    # row — a 515-dev census, PF 91≡91, UF 149≡149; exhibit #45 (nps, 24121
    # LOC) did NOT come back. Warden #48: CLEAR (vacuously net). An explicit
    # "0" is a kill-switch FOREVER.
    "WYSTAN_PUBLISHED_ARTIFACT_VETO",
    # fixb143 (i-c) — the container-NAME short-circuit may not overrule the
    # row's own product evidence. ``is_shell_name`` returns ``shell`` before
    # a single path is read; with this flag the short-circuit additionally
    # requires the row's path vote to contribute ZERO product weight.
    # Mirrors the existing "a real product route blocks non-product" law
    # (``member_vote``) at feature grain. Measured: 3 of 7 world shell-name
    # lanes move (strapi ``home-page`` @ packages/core, outline ``home``,
    # inbox-zero ``home``); ANTI-CASE fastapi ``main`` holds (product_w==0).
    # FLIP-PACK #45 (2026-08-13): default **ON** under the KEY_SCHEMA 80 bump
    # (the bump rides commit (i-a) — the first in the pack).
    # PROOF (keyed outline, TWO ON draws): the freed PF is emitted as
    # 'Home Popular' — the earned name survives BOTH draws, i.e. warden #47's
    # signature is lifted ROW-LEVEL, not "on average";
    # the strapi ABSTAIN is valid (round-5 census == the round-4 OFF hand).
    # DEBT NS-48 (does not block the flip, named by court #48): the qualifier
    # is taken from ``uf.resource`` with no product-noun test
    # ('Home Popular' <- resource='popular') — queued for naming.
    # An explicit "0" is a kill-switch FOREVER.
    "WYSTAN_SHELL_NAME_CORROBORATION",
    # fixb143 (i-d) — Surface-Adjudicator dependency guard + payload
    # denominator. Third guard beside the journey-guard and route-guard: a
    # PF whose paths are DOMINATED (strict majority, abstains included) by
    # workspace packages DECLARED AS A DEPENDENCY by another workspace is
    # product-evidenced by the manifest graph and is never sent for a
    # non-product flip. The majority form was pinned by the after-census:
    # the any-hit form over-blocked 4 of 32 flips on MIXED lanes (midday
    # `chat` 4/12, typebot `templates` 4/15). Also adds ``total_paths`` to the
    # item payload so the model sees ``{"docs": 2}`` against 103 rather
    # than in a vacuum. Measured: blocks exactly 2 of 32 world flips
    # (supabase ``pg-meta`` 10795 LOC / 60 devs, teable ``formula`` 6726
    # LOC); the 30 defensible flips still fire (app workspaces have 0
    # manifest dependents). Changes the LLM payload ⇒ cache-keyed.
    "WYSTAN_ADJUDICATOR_DEP_GUARD",
    # fixb146 (2026-08-11, default **OFF** — append with NO bump): the ARMED
    # half of the M3 lexicon. `WYSTAN_PF_DISPLAY_LEXICON` is already default
    # ON, so a new entry placed straight into `expansions:` would move
    # displays on EVERY board while the cache key stayed the same — that key
    # hashes KEY_SCHEMA + repo identity + engine version + the VALUES of
    # these flags, and NEVER the bytes of the YAML itself (a warm cache hit
    # would hand back a pre-edit board on a post-edit engine — the
    # audit-Bug-2 form). KEY_SCHEMA moves only in a flip commit, so the
    # honest carrier for an ADDITION to the lexicon is its own flag:
    # `armed_expansions:` merge over `expansions:` only while it is
    # truthy. MEASURED WORLD (census world-77, 54 boards): the single armed
    # entry `ui: User Interface` touches 3 PFs on 3 boards (dub 'UI'
    # ws:packages/ui, twenty 'Ui' container-rehome:ws:.../ui, unkey 'UI'
    # ws:web/internal/ui) — the canon class `short_name` (alnum <= 2).
    # ANTI-CASES: 'API Key' / 'UI Kit' stay whole (the WHOLE-segment law),
    # authored nav/manifest labels untouched (route-derived tiers only).
    # An explicit "0"/unset is a kill-switch FOREVER (the lexicon = the
    # pre-fixb146 table byte-for-byte). Shapes pf[].display_name.
    # FLIP-PACK #43 (2026-08-11, KEY_SCHEMA 77 -> 78): the `ui` entry was
    # PROMOTED into `expansions:`; the carrier remains for the next addition
    # and is empty for now — the flag governs NOTHING (the merge is a no-op).
    # The entry's own kill-switch is now WYSTAN_PF_DISPLAY_LEXICON=0.
    "WYSTAN_PF_LEXICON_ARMED",
    # fixb146 Row 2 (2026-08-11, default **OFF** — append with NO bump):
    # a PRODUCT-EVIDENCE discriminator for the canon class `ws_anchor_no_uf`.
    # The class was written to catch a STRUCTURAL CONTAINER posing as a
    # product, but the predicate ("a ws: anchor AND zero unsynthesised
    # journeys") also condemns a REAL product surface whose journeys the
    # engine honestly backstopped. Live exhibit (onyx KS77):
    # `onyx-chat-widget` (ws:widget) holds UF-087 — synthesized, but with 5
    # member flows; the binding canon of product grain says a genuine feature
    # with no journeys is MARKED with an honest gap, not deleted. Operator
    # ruling 2026-08-11 (option 2): spare a ws-PF with positive PRODUCT
    # EVIDENCE by reusing the prongs of the neighbouring seed hook
    # `check_pf_ws_container_no_uf` — ONE shared helper
    # `has_product_evidence`, so the two cannot drift apart.
    # DELIBERATELY not cased on the `synthesized` tag: the fixb145 lane makes
    # it DYNAMIC (converted rows drop it), and the class would re-trigger by
    # accident as conversions land.
    # THE GRAIN LAW: on the BOARD `pf.flows` is ALWAYS empty — flows live on
    # the developer layer, so the flow prong is read through membership
    # (developer_features[].product_feature_id). Reading `pf.flows` here would
    # make the discriminator a no-op on its own exhibit (onyx: 0 pf.flows,
    # 7 flows through 5 member dev features).
    # MEASURED (dub KS77): 3 ws rows -> 1; `ui` (468 paths, authored .tsx)
    # and `com.example.dub` (views/AppSettings.tsx) are spared;
    # `dub-cli` REMAINS (0 authored views, 0 flows, 0 nav) — the class still
    # works, this is not an amnesty.
    # Shapes scan_meta.product_right_census + invariant_hooks[].
    # FLIP-PACK #43 (2026-08-11): default **ON**, KEY_SCHEMA 77 -> 78.
    # An explicit "0" is a kill-switch FOREVER (pre-fixb146 predicate exact).
    "WYSTAN_WS_EVIDENCE_DISCRIMINATOR",
    # fixb143 round-5 (ii-a, 2026-08-13) — EARNED-DISPLAY REGISTRY. Warden #47 RESURRECTION: 6.85 qualified
    # outline `home` -> 'Home Popular' (`shell_release_qualified`), yet the
    # row was emitted as 'Home' — 'Home Popular' appears in the WHOLE document
    # exactly once, in telemetry. The overwriter is `naming_contract` Pass 3
    # (`pm_labeler`, "the single display writer"): its re-check is ONLY
    # `display_law_violations`, and I11 (the banked operator invariant
    # "a home page cannot be a feature") does not live there, so the 'Home'
    # pick passed the laws. A SECOND ON run of THE SAME commit gave applied=0
    # and kept 'Home Popular' — the defect is non-deterministic across draws.
    # MECHANISM (fixb136 precedent, "a promise through a filter is no channel"):
    # the release writes pf -> earned display into a SCAN-SCOPED registry that
    # both modules import; the labeler overwrites a protected row ONLY with a
    # non-container candidate (the same container dictionary + round-4
    # de-compounder that earned the name). Shapes product_features[].
    # display_name ⇒ must key the cache.
    # FLIP-PACK #45 (2026-08-13): default **ON** under the KEY_SCHEMA 80 bump
    # (the bump rides commit (i-a) — the first in the pack).
    # PROOF (keyed outline, BOTH ON draws): `labeler_earned_display_held=1`,
    # and the registry blocks EXACTLY that write — the same candidate goes
    # applied 1 -> 0 — while the other 13 PFs are byte-identical to the OFF
    # hand. So the protection is row-addressed, not "on average". Warden #48: CLEAR.
    # An explicit "0" is a kill-switch FOREVER.
    "WYSTAN_RELEASED_DISPLAY_REGISTRY",
    # fixb143 round-5 (ii-b, 2026-08-13) — ABSTAIN SCOPE ROLLBACK. Warden #47 new-suspect, consumer-visible on
    # three live ON boards: step 1a stamps EVERY dev row with the armed
    # classifier BEFORE the PF loop decides whether the release of that same
    # flag commits, and both round-3 riders can abstain —
    # rolling back only the PARENT. trigger.dev: 13 dev rows under
    # `ws:packages/cli-v3` (pfid='trigger.dev') read `product`, while the PF and
    # its lane row read `dev_tooling` (dev_scopes.dev_tooling 13 -> 0) against
    # the verdict `veto_destination_abstained.restored_scope: dev_tooling`;
    # strapi: dev `home` shell -> product under a lane row `home-page` that
    # ABSTAINED; inbox-zero: dev `landing` shell -> product on a
    # container name that NO PF qualification ever vouched for.
    # THE LAW: a dev-grain release of a flag that can abstain is a CONSEQUENCE
    # of its PF's verdict, not an independent decision; it stands only if the
    # release committed on the FINAL (post-adjudicator) scope, otherwise the
    # row returns to its own flag-OFF hand (never-worse by construction, form (i-a)).
    # Shapes features[].surface_scope + scan_meta.dev_scopes ⇒ keys the cache.
    # FLIP-PACK #45 (2026-08-13): default **ON** under the KEY_SCHEMA 80 bump
    # (the bump rides commit (i-a) — the first in the pack).
    # PROOF (corpus-wide, BY CENSUS rather than telemetry): 15 rollback records,
    # each ≡ that row's own OFF hand; rung 2 fires on exactly ONE
    # record; the outline anti-case is clean (a container-named dev row that
    # PF-grain qualification VOUCHED for keeps its release).
    # Warden #48: CLEAR-WITH-DEBT — the invariant hook for abstain mutations
    # does not cover rung 2 (coverage 0 on rung-2 boards); the debt is in the ledger.
    # An explicit "0" is a kill-switch FOREVER.
    "WYSTAN_ABSTAIN_SCOPE_ROLLBACK",
    # fixb147 (2026-08-13) — WS ANCHOR IDENTITY, both rungs under ONE
    # flag. Rung A: a row that fixb143 (i-a) is about to ABSTAIN
    # (a bare ``ws:`` anchor above the journey floor) first asks its OWN
    # manifest — a workspace that declares a bin is a product command
    # surface, and its identity = fixb125 ``cli:<dir>`` + the display
    # '<bin> CLI' (npm naming semantics via ``cli_commands._p1_node``:
    # a string bin ⇒ the command is the package name, never a path stem). Both
    # predicates (``_destination_survives``, ``_is_structural_home``)
    # flip BY THEMSELVES, with no change to their code. The scope is STRICT —
    # only the abstaining row: a mass re-anchor of published packages was
    # measured and rejected (5 trigger.dev rows quietly leave
    # ``_is_structural_home`` — the source domain of 6.9965/6.9966 — and the
    # census class ``ws_anchor_no_uf``).
    # Rung B: the B27 rung-4 authored test accepts an npm SCOPE as identity
    # when the bare remainder is DEGENERATE (alnum <= 2 — exactly the gate's
    # short_name class): '@novu/js' -> 'Novu JS'. Non-degenerate remainders are
    # NOT touched (anti repo-echo: 'Trigger.dev Rsc' — a measured regression).
    # Shapes product_features[].anchor_id + display_name ⇒ keys the cache.
    # FLIP-PACK #46 (2026-08-14): default **ON** under the KEY_SCHEMA 81 bump
    # (the bump rides THIS, the pack's first commit). PROOF (keyed trigger.dev
    # ×3 batteries + novu): the abstaining row COMMITS as a product — PF 'Trigger
    # CLI' (``cli:packages/cli-v3``, 24121 LOC) on a live board in ALL
    # three batteries; novu 'Js' -> 'Novu JS', the product-right gate CLEAN
    # (short_name=0 — world80's install blocker lifted); I22 dangling dev pfid
    # 14 -> 0 along the way. Wardens #50 NO-RESURRECTION / #51 CLEAR / #52 CLEAR.
    # RIDING WITH THE BUMP is the promotion of 'js'/'rsc' from ``armed_acronyms``
    # into ``known_acronyms`` (naming-contract-vocab.yaml): that table is read
    # by EVERY display path, while the cache key hashes KEY_SCHEMA +
    # ENV_OUTPUT_FLAGS, NOT the YAML bytes — so the promotion is legal exactly
    # when it rides a bump. It is NOT behind the flag: an explicit "0" removes
    # the identity rungs, but the global acronym table stays promoted.
    # An explicit "0"/"false"/"off"/"no"/"" is a kill-switch FOREVER.
    "WYSTAN_WS_ANCHOR_IDENTITY",
    # fixb147 / NS-50a-b (warden #50, 2026-08-14) — the SIBLING-DUP guard of
    # the ``cli_journey_unsynth`` lane. THE LAW court #50 handed down: a fix that
    # RESCUES a row (one another hand DELETES) imports the rescued row's LATENT
    # defects onto a fresh tile. The lane fired for the FIRST time on
    # trigger.dev (converted 0->5) and 2 of the 5 outputs were hollow +
    # substantive duplicates: the member uuid is PRE-MERGE, living in a
    # ``flows[].merged_from`` flow that on the SAME PF already holds a REAL
    # sibling journey (UF-163 -> deploy-application-flow -> UF-072 mc=6
    # loc=1076; UF-162 -> analyze-project-flow -> UF-073). Both detectors are
    # blind: check_hollow_rows nets them via ``abstained_row_ids`` (flip
    # #26), and uf-dup-names is string-based — the duplicate wears an AUTHORED sentence.
    # THE GUARD (in the PRODUCER, the stage-hooks law): resolve EVERY member
    # through the merge map; if ALL resolved flows already belong to REAL
    # (non-synth) siblings of the SAME PF, the conversion does NOT run, the row
    # stays ``synthesized`` (⇒ outside the journey ratio on both sides), and it
    # is counted in ``scan_meta.cli_journey_unsynth.unsynth_suppressed_dup`` with
    # the uuid + owner. It deletes no rows and touches no membership — the seam
    # changes only the emitted field. Measured on capture 20260813T220045Z: 2
    # suppressions (UF-162/163), 3 legitimate outputs SURVIVED (UF-164/165/166).
    # Shapes user_flows[].synthesized ⇒ keys the cache.
    # FLIP-PACK #46 (2026-08-14): default **ON**; the KEY_SCHEMA 81 bump rode
    # commit (i) — WS_ANCHOR_IDENTITY, the first in the pack. PROOF (keyed
    # trigger.dev + inbox-zero): 3 suppressions, ALL verified true
    # sibling duplicates (tdev UF-162/163, ibz UF-111); the board trace is ONLY
    # the ``synthesized`` field (no row deleted, no membership moved);
    # inert on novu/ollama. Wardens #51 CLEAR / #52 CLEAR.
    # An explicit "0"/"false"/"off"/"no"/"" is a kill-switch FOREVER.
    "WYSTAN_UNSYNTH_SIBLING_DUP_GUARD",
    # fixb148 (iteration-2 probe verdict, 2026-08-14) — the BIND gate of the
    # ``cli_journey_unsynth`` lane. THE CLASS: the CLI journey mint has TWO
    # member-binding rungs. The handler rung (NS-3) is exact by construction — a
    # flow entering the SYMBOL named by the registration site. The second rung is
    # TOKEN OVERLAP with the flow NAME, and one shared token is not enough:
    # across 28 handler-null rows on 8 boards, manual judging gave 11 CORRECT /
    # 16 MISBOUND / 1 PHANTOM ('Display the current logged in user…' over
    # ``commands/logout.ts``; 'Manage environment variables…' over
    # ``commands/init.ts``). Lane 1 CONVERTS such rows — i.e. it lifts a
    # false binding out of the synthesized exclusion into the journey ratio under
    # an authored high name.
    # THE GATE (scoped STRICTLY to handler==null, i.e. binding_confidence != "high"):
    # V2 — the command's declaring file (the mint STAMP ``declarant_files``) is
    # the member's entry_point_file; V4 — the command token is a segment (or a
    # file stem) of the member's path. EITHER passing ⇒ conversion; both failing ⇒
    # the row stays ``synthesized`` (outside the ratio on both sides) and is
    # counted in ``scan_meta.cli_journey_unsynth.unsynth_misbind_suppressed``.
    # Lane precision 40.7% -> 91.7%; it deletes no rows, touches no membership,
    # and does not touch the 9 handler-ful controls. A known miss (do NOT tune):
    # ollama 'launch' survives via the directory token collision ``cmd/launch/``.
    # Order: the dup guard (fixb147) FIRST, the bind gate SECOND.
    # Shapes user_flows[].synthesized AND adds user_flows[].declarant_files
    # ⇒ keys the cache.
    # FLIP-PACK #46 (2026-08-14): default **ON**; the KEY_SCHEMA 81 bump rode
    # commit (i) — WS_ANCHOR_IDENTITY, the first in the pack. PROOF (battery 40):
    # lane precision 40.7% -> 91.7%; 6 suppressed = 6/6 MISBOUND BY NAME
    # under manual judging, the converted = CORRECT, the 9 handler-ful
    # ollama controls untouched; floor inertness proven (the release is live
    # at 5 suppressed). Warden #52 CLEAR.
    # CAVEAT NS-52a (coordinator ruling — KEEP it and NAME it): the V2 hand
    # (declarant==entry) is VACUOUS on every measured live population
    # (V2 ⊆ V4 in the corpus, 0/12 live V2 decisions). It stays as
    # defense-in-depth against the MEASURED cross-cluster token blindness of V4
    # (lobe-chat inspect/list ×2 clusters). Any future tuning of the gate is
    # OBLIGED to carry the ledger label "V2 unwitnessed".
    # An explicit "0"/"false"/"off"/"no"/"" is a kill-switch FOREVER (it removes
    # BOTH halves: the mint stamp and the gate ⇒ the field is not serialised).
    "WYSTAN_CLI_BIND_GATE",
)

#: Bump when the KEY composition changes so old entries can't be served
#: against a new key layout (they simply won't match — silent invalidation).
#: v3 (W5.1): added WYSTAN_LATTICE_THIN_FOLD + WYSTAN_LOC_WORTHY_BACKSTOP.
#: v4 (B4): added WYSTAN_SYNTH_QUALITY.
#: v5 (B13): added WYSTAN_BACKSTOP_OWNED_COVER.
#: v6 (B15): added WYSTAN_SHARED_LEAF_CONSISTENCY.
#: v7 (B15b): added WYSTAN_DATA_LEAF.
#: v8 (B16): added WYSTAN_PF_NAME_LAW.
#: v9 (B16 Part 2): added WYSTAN_PF_SIBLING_UNIFY.
#: v10 (B19): added WYSTAN_TECH_TRANSPORT_LANE.
#: v11 (B20): added WYSTAN_I16_REHOME_B20.
#: v12 (B22a): added WYSTAN_FOLD_CROSSAPP_GUARD.
#: v13 (B22): added WYSTAN_TRANSPORT_LANE_HANDOFF + WYSTAN_TRANSPORT_HANDOFF_PLURALITY.
#: v14 (B23): added WYSTAN_MARKER_SURFACE_COORDS.
#: v15 (B24): added WYSTAN_MEGA_PF_NAV_REHOME.
#: v16 (B24 flip): WYSTAN_MEGA_PF_NAV_REHOME default OFF -> ON — the
#: default flip changes what "unset" means, so cached entries keyed under
#: unset must not be served across it (B4 precedent).
#: v17 (B26+B27): added WYSTAN_HUB_PLUMBING_CHILD + WYSTAN_PF_MANIFEST_NAME.
#: v18 (B30): added WYSTAN_FLOW_NAME_V2.
#: v19 (B31): added WYSTAN_RECALL_ROW_NAMES.
#: v20 (B34): added WYSTAN_LAZY_IMPORT_EDGES + WYSTAN_DISPATCH_REGISTRY_FLOWS.
#: v21 (B34 flip): both B34 flags default OFF -> ON — the default flip changes
#: what "unset" means, so cached entries keyed under unset must not be served
#: across it (B4/B24 precedent).
#: v22 (B25): added WYSTAN_JOURNEY_LATTICE_B25.
#: v23 (B34 dispatch revert): WYSTAN_DISPATCH_REGISTRY_FLOWS default ON -> OFF
#: (supabase 328 hollow UI-demo mints; re-flip after B34-b rails + keyed proof).
#: v24 (B28): added WYSTAN_NONPRODUCT_SCOPE + WYSTAN_DOCS_REANCHOR.
#: v25 (B34-b re-flip): WYSTAN_DISPATCH_REGISTRY_FLOWS default OFF -> ON
#: (rails merged; hollow=0 proof on keyed supabase + RefApp).
#: v26 (B38): added WYSTAN_MARKER_COORDS_REQUIRED + default flip ON at merge.
#: v27 (B45+B40+B46 flip): WYSTAN_COVERAGE_GAP_CHANNEL default off -> full,
#: WYSTAN_NAME_EVIDENCE_RUNGS default OFF -> ON, WYSTAN_UF_NAME_HYGIENE
#: default OFF -> ON — default flips change what "unset" means, so cached
#: entries keyed under unset must not be served across them (v16/v21/v25
#: precedent). Keyed proof: papermark + cal.com green (2026-07-12).
#: v28 (B33+B37-ph2 flip): WYSTAN_FDIR_DEVGRAIN_GATE default OFF -> ON +
#: WYSTAN_DISPATCH_HOMING_B37P2 default OFF -> ON — COUPLED: B33's 6.987
#: demote is only I9-safe with the homing rider (flowful demoted devs home
#: to their target-owner PF instead of the platform lane). Default flips
#: change what "unset" means, so cached entries keyed under unset must not
#: be served across them (v16/v21/v25/v27 precedent). Keyed proof:
#: papermark green (Welcome demoted, I9=0, lane 43->42, 2026-07-12).
#: v29 (B62 flip): the proven campaign set flips default OFF -> ON in ONE
#: commit (14 flags): WYSTAN_REACT_ROUTER_FW_PROFILE, _ROUTER_ALIAS_RESOLVE,
#: _KEYLESS_JOURNEY_RECALL, _WS_LIBRARY_LANE, _UF_NAME_DEGRIME,
#: _UF_RESOURCE_RUNG, _FLOWFUL_TRANSPORT_LANE, _WS_BLOB_DOMAIN_DRAIN,
#: _PF_FULLNAME_LAW, _UF_RUNG_SOURCES_V2, _STAGE_6_7E_ADJUDICATOR,
#: _ANNEXATION_GUARD, _ARTIFACT_INK_LANE, _UF_VERB_SNAP. Default flips change
#: what "unset" means, so cached entries keyed under unset must not be served
#: across them (v16/v21/v25/v27/v28 precedent). Every flag keeps its X=0
#: kill-switch (explicit "0"/"false"/"off" still disables — inverted-
#: kill-switch unit per flag). B49/B51 transport flags stay OFF (superseded
#: by B52 FLOWFUL_TRANSPORT_LANE). DISPATCH_RESOLVER (B64) NOT in this flip.
#: scan_meta.key_schema=29 emitted so downstream rulers gate new-world logic.
#: v30 (horizon-1 flip, 2026-07-16 — plan docs/anchor-arc/flip-pack-20260716.md):
#: the horizon-1 pack flips 10 previously-default-OFF flags to default ON, each
#: in its own commit (per flip-protocol), the bump riding this final commit:
#: WYSTAN_TERMINAL_CLASSIFICATION (B68), _SERVER_API_ENTRIES (B66),
#: _HOMING_HYGIENE (B69-v2), _NAMING_LAW (B70), _RECALL_QUAL_CASING (B70),
#: _GRAIN_WAVE (B58-v3), _OWNERSHIP_V2 (B66-v2), _SPA_ROUTER_ENTRIES (B65-v3),
#: _NAMING_PACK (B71), _FLOW_GRAIN (B71). Default flips change what "unset"
#: means, so cached entries keyed under unset must not be served across them
#: (v16/v21/v25/v27/v28/v29 precedent). Every flag keeps its X=0 kill-switch
#: (explicit "0"/"false"/"off" still disables — inverted-kill-switch unit per
#: flag). NOT flipped (stay OFF): WYSTAN_JOBS_ENTRIES (awaits B24 PF-assembly
#: guard), _SEED_HYGIENE (no own gates), _BLOB_PARTITION (parked). B49/B51
#: transport flags stay OFF (superseded). scan_meta.key_schema=30 emitted so
#: downstream rulers gate new-world logic.
#: v31 (B65-v4 re-flip, 2026-07-18): WYSTAN_SPA_ROUTER_ENTRIES default
#: OFF -> ON again — the R1 revert (f6bd5d6) had returned its unset
#: semantics to OFF under schema 30, so 21 cold boards are cached with
#: unset=OFF; the re-flip changes what "unset" means and cached entries
#: keyed under it must not be served across (v16/v21/v25/v27/v28/v29/v30
#: precedent). Re-land proof: B65-v4 mint-priority fix chain (authored-
#: subtree fence+floor predicate, spa-born mass fence, member-twin bar,
#: barrel-hop, template-literal honest skip), full convoy2 on f38760e +
#: operator panel PASS (2026-07-18). Explicit "0"/"false"/"off" stays a
#: valid kill-switch forever (inverted-kill-switch unit: unset ≡
#: explicit "1" byte-identical).
#: v32 (S*-pack flip, 2026-07-19 — plan
#: docs/anchor-arc/flip-pack-s-strategy-20260718.md, operator-ratified):
#: the S* strategy pack flips 10 previously-default-OFF flags to default ON,
#: each flag/group in its own commit (per flip-protocol), the ONE bump riding
#: the FIRST commit of the pack: WYSTAN_DEGRADATION_STAMP (S2-D,
#: telemetry-only, safest first), _OWNER_ORACLE (S1, panel ON >= OFF strict),
#: _UF_DET_AGGREGATION + _UF_REFINE_TOKEN_SCALE + _LLM_BATCH_CANON (S2
#: quartet — designed as a stack; keyless obstacle baselines re-recorded for
#: the S2 regrain 141->85 class), _OVERTURN_ARBITER (S3 — byte-ident x3
#: pre-flip, the flip is the overturns telemetry), _APPROUTER_KEYLESS (S4a,
#: cal 0->249 / onyx 0->106), _GO_EXTRACTION (S4b, traefik 0->1 PF/51
#: routes, ollama 0->2/76), _MEGA_DECOMP_ARM + _GENERATED_CONTENT_MARKER
#: (S5a, healthy novu pair + re-panel). Default flips change what "unset"
#: means, so cached entries keyed under unset must not be served across them
#: (v16/v21/v25/v27/v28/v29/v30/v31 precedent). Every flag keeps its X=0
#: kill-switch (explicit "0"/"false"/"off" still disables — inverted-
#: kill-switch unit per flag: unset ≡ explicit "1" byte-identical). NOT
#: flipped (stay OFF): S4c (precondition: the shards-orphan rule) and S4d
#: (precondition: its own keyed UF-proof) — each rides a later cycle.
#: scan_meta.key_schema=32 emitted so downstream rulers gate new-world logic.
#: v32 amendment (same day, it2): WYSTAN_UF_DET_AGGREGATION UN-flipped
#: back to default OFF — the mandatory corpus regression audit (7 pairs)
#: came back 1 BETTER / 2 MIXED / 4 WORSE with the single root corpus-wide
#: in the A-flip: the det-cluster naming layer (regrain it3-it6) was
#: panel-hardened only on RefApp/novu and emits bare 'Manage <plural>' bins
#: elsewhere (twenty 143, midday 29 bins, documenso 'Manage os/ts', novu
#: 61% bare + paren 0->33). The other 9 pack flags STAY ON (their wins are
#: real: agents 187K->80K, twenty-front 88K->40K, RefApp BETTER). KEY_SCHEMA
#: stays 32 — unset semantics changed twice within one unreleased schema
#: generation; the naming layer returns via R5 corpus hardening in its own
#: cycle with its own flip.
#: v33 (flip-pack №2, 2026-07-21 — plan docs/anchor-arc/flip-pack-2-20260719.md,
#: operator-ratified 2026-07-21): the pack flips 4 previously-default-OFF flags
#: to default ON, each in its own commit (per flip-protocol), the ONE bump
#: riding the pack's FIRST commit: WYSTAN_PF_DISPLAY_EVIDENCE_GATE
#: (display-cross; keyed proof cal + novu — sim==engine 7/21 exact, cal 5→0
#: false displays, novu footprint 1 row), _WORKSPACE_UNION (onyx union-gate;
#: keyed A/B onyx fallback 57.1→36.5%, web-residual 2114→0; anti-cases
#: langfuse/typebot byte-ident even armed), _NAMING_WAVE_R5 (phase2 merged;
#: keyed A/B twenty+papermark — paren-high 17→0, dup 3→0, brand-echo ×5,
#: measured demote 101→92 high), _ORGANIC_MOVE (B73-it2; keyed RefApp moved=0,
#: UF-051 prior-hold, conservation 399→399; typebot evidence-trio byte-inert).
#: Default flips change what "unset" means, so cached entries keyed under
#: unset must not be served across them (v16/v21/v25/v27/v28/v29/v30/v31/v32
#: precedent). Every flag keeps its X=0 kill-switch (explicit "0"/"false"/
#: "off" still disables — inverted-kill-switch unit per flag: unset ≡
#: explicit "1" byte-identical). scan_meta.key_schema=33 emitted so
#: downstream rulers gate new-world logic.
#: v34 (flip-pack #3, 2026-07-21 — ledger "PACK #3 FULLY ASSEMBLED" /
#: "PACK #3 COMPLETE", operator-ratified 2026-07-21): the pack flips 9
#: previously-default-OFF flags to default ON, each in its own commit (per
#: flip-protocol), the ONE bump riding the pack's FIRST commit:
#: WYSTAN_HOME_PURE_CONTAINER_INHERIT (B74-C; keyed twenty — 'Sign in
#: and authenticate' 14m, filter 24,226→2,081, +240 rescue),
#: _SPA_ROUTE_TABLE (B74-A; twenty +114 PAGE / novu +86, 0/2,042 false),
#: _FLOW_REDERIVE_POSTGRAIN (B74-B; keyed twenty 894 live calls, +3,712
#: flows, golden tasks/workflows/AI taken), _DIGEST_STRATIFICATION
#: (S5b-H; keyed novu 'Sign in to existing account' mints, UF 88→92),
#: _UF_CASES_SPLIT (B75; sim-canon 209→10/131→11 children, composite
#: keyed twenty target), _RESIDUAL_CITABILITY (B77; replay census 502-class
#: 542→7, no-orphan 0/2211), _METRICS_RECOMPUTE (B76; impossible metric
#: rows →0 ×3 repos, hotspots byte-ident), and the S2-A return pair
#: _UF_DET_AGGREGATION + _SPRAY_GENERALIZED (the 04cf47f un-flip REVERSED:
#: the naming collapse is cured by R5 + spray-generalization — ledger
#: §S2-A-V3: twenty spray 17→0, settings-PF 36→22, conservation 328==328,
#: 0 false, I14 dangling 0). Default flips change what "unset" means, so
#: cached entries keyed under unset must not be served across them
#: (v16/v21/v25/v27/v28/v29/v30/v31/v32/v33 precedent). Every flag keeps
#: its X=0 kill-switch (explicit "0"/"false"/"off" still disables —
#: inverted-kill-switch unit per flag: unset ≡ explicit "1"
#: byte-identical). scan_meta.key_schema=34 emitted so downstream rulers
#: gate new-world logic.
# v35 (2026-07-21): UN-flip WYSTAN_UF_DET_AGGREGATION (default OFF again) —
#   det-agg ON skips the 6.7d rewrite on the keyed channel, neutralizing the
#   6.7d-family pack-3 defaults + B74-C wins; det×6.7d composition = open cycle.
#: v36 (flip-pack №4, 2026-07-22 — plan docs/anchor-arc/flip-pack-4-20260722.md,
#: operator-ratified 2026-07-22): the pack flips 6 previously-default-OFF flags
#: to default ON, each in its own commit (per flip-protocol), the ONE bump
#: riding the pack's FIRST commit (this FOLD_EVIDENCE_WEIGHT commit):
#: WYSTAN_FOLD_EVIDENCE_WEIGHT (B78-A + it2 synth-cap + Goal-2a
#: D-discriminator; keyed 6.7d RefApp media-library 10→1 / cases →2,
#: walk-folds evidence-void 35→0, D 6/6 exhibits, protected live, CF-final
#: clean), _HOME_AFFINITY_GATE (B78-B/C/D + it2 orphan-stamp; keyless tok0
#: 50.7→36.8%, better-home 34→7, 12 honest orphan-stamps),
#: _NAV_PARENT (B78-G + it2; RefApp 23-32/PF parents verified vs module-registry),
#: _PLUMBING_UF_RECLASS (B78-F; cal keyless 79/80 reclassified, abstain
#: anti-case live), _DOMINANT_EVIDENCE_NAMING (B78-H; ratio 0.34 on 4 sites,
#: 'audit' 1/11 unit-law), _67D_ROBUST_PARSE (B79; salvage 179 journeys +
#: honest partial-stamp, severity-aware guard). Confound-free same-cache keyed
#: A/B RefApp (2026-07-22): fatal 0 both hands, 'org-members regress' = PROVEN
#: LLM-confound (journey live both hands same-cache), stack clean, panel 4/5
#: operator complaints VERIFIED-cured. Default flips change what "unset" means,
#: so cached entries keyed under unset must not be served across them
#: (v16/v21/v25/v27/v28/v29/v30/v31/v32/v33/v34 precedent). Every flag keeps
#: its X=0 kill-switch (explicit "0"/"false"/"off" still disables — inverted-
#: kill-switch unit per flag: unset ≡ explicit "1" byte-identical).
#: scan_meta.key_schema=36 emitted so downstream rulers gate new-world logic.
#: v37 (B85, 2026-07-22 — the B22a-resurrection fence): added
#: WYSTAN_FOLD_EVIDENCE_DEMOTE. UNLIKE a normal default-OFF flag (which
#: appends WITHOUT a bump — the TRANSPORT_DOMAIN_DRAIN precedent one line up),
#: this flag is default ON *inside the EVW world*, so it changes what the
#: UNSET default world emits (a minted PF sheds its foreign member mass to the
#: cross-unit lane) — cached v36 entries keyed under the pre-demote unset world
#: must not be served across it. World 36 was never published, so the bump is
#: clean (probe-canon B85, 4 probes VERIFIED). Every flag keeps its X=0
#: kill-switch (inverted-kill-switch unit: unset ≡ explicit "1" byte-identical;
#: "0"/"false"/"off"/"no" restores the EVW-only pre-demote world).
#: v38 (flip-pack №5, 2026-07-23 — operator-ratified in-session; keyed proofs
#: per flag + composition probe CLEAR on RefApp/documenso + multi-topology):
#: the pack flips 3 previously-default-OFF flags to default ON, each in its own
#: commit (per flip-protocol), the ONE bump riding the pack's FIRST commit
#: (this TRANSPORT_DOMAIN_DRAIN commit):
#: WYSTAN_TRANSPORT_DOMAIN_DRAIN (B80 trpc-lane; keyed cal calibration
#: DECISIVE-PASS — transport-donor router grain + B22a cross-unit exemption),
#: WYSTAN_MEMBER_DISJOINT_RECONCILE (B84 terminal reconcile; keyed documenso
#: 9 dissolved / conservation exact + keyless 10/10), and WYSTAN_AGENT_SURFACE
#: (B81 agent-surface; KB3 + panel USEFUL + composition CLEAR). Default flips
#: change what "unset" means, so cached entries keyed under unset must not be
#: served across them (v16/v21/v25/v27/v28/v29/v30/v31/v32/v33/v34/v36/v37
#: precedent). Every flag keeps its X=0 kill-switch (explicit "0"/"false"/
#: "off"/"no" still disables — inverted-kill-switch unit per flag: unset ≡
#: explicit "1" byte-identical). scan_meta.key_schema=38 emitted so downstream
#: rulers gate new-world logic.
#: v39 (flip-pack №6, 2026-07-23 — operator-ratified in-session; keyed proofs
#: per flag + composition probe CLEAR on mid_A4/cal_A4 + multi-topology; B48
#: DROPPED from the pack — already default ON via KS29/B62): the pack flips 3
#: previously-default-OFF flags to default ON, each in its own commit (per
#: flip-protocol), the ONE bump riding the pack's FIRST commit (this
#: PRODUCT_RIGHT_GATE commit):
#: WYSTAN_PRODUCT_RIGHT_GATE (B87 rung-2; keyless SAFETY B87 + composition
#: mid_A4 class-A kills named + re-home confirmed),
#: WYSTAN_RECALL_TRANSPORT_SKIP (B88 transport-donor seed guard; live keyed
#: 32→0 + composition cal_A4 transport_masquerade=0), and
#: WYSTAN_INVARIANT_HOOKS (B89 invariant stage-hooks; byte-additivity +
#: 1:1 census-parity on 3 keyed boards). Default flips change what "unset"
#: means, so cached entries keyed under unset must not be served across them
#: (v16/…/v37/v38 precedent). Every flag keeps its X=0 kill-switch (explicit
#: "0"/"false"/"off"/"no" still disables — inverted-kill-switch unit per flag:
#: unset ≡ explicit "1" byte-identical). scan_meta.key_schema=39 emitted so
#: downstream rulers gate new-world logic.
#: v40 (flip-pack №7, 2026-07-24 — operator-ratified; plan
#: docs/anchor-arc/flip-pack-7-20260724.md; closes the operator pins tRPC +
#: Link): the pack flips 2 previously-default-OFF flags to default ON, each in
#: its own commit (per flip-protocol), the ONE bump riding the pack's FIRST
#: commit (this TRANSPORT_PF_LANE commit):
#: WYSTAN_TRANSPORT_PF_LANE (B90 Seg A — transport-donor PF lane; live keyed
#: cal: PF tRPC ABSENT, 0 journeys in trpc, conservation 139→139 named; KS
#: byte-ident) and WYSTAN_API_STUB_DEMOTE (B90 Seg B — api-root-stub demote;
#: live keyed cal: PF Link ABSENT, C6 micro-profile channel-robust, anti-cases
#: named [papermark Links / twenty File Upload / midday Session-family alive],
#: SACRED B48 intact). Default flips change what "unset" means, so cached
#: entries keyed under unset must not be served across them
#: (v16/…/v38/v39 precedent). Each flag keeps its X=0 kill-switch (explicit
#: "0"/"false"/"off"/"no" still disables — inverted-kill-switch unit per flag:
#: unset ≡ explicit "1" byte-identical). The B90 flags' pre-flip truthy set is
#: the NARROW {"1","true"} (preserved LITERALLY across the flip — "false"/"off"/
#: "no" were never truthy there and stay kill-switch aliases).
#: scan_meta.key_schema=40 emitted so downstream rulers gate new-world logic.
#: v41 (flip-pack №8, 2026-07-27 — operator-ratified; keyed/keyless proofs per
#: flag + composition all-armed probe CLEAR on novu/RefApp/outline/langfuse/cal +
#: multi-topology): the pack flips 7 previously-default-OFF product-right/quality
#: flags to default ON, each in its own commit (per flip-protocol), the ONE bump
#: riding the pack's FIRST commit (this ROUTE_RENDER_UTIL_DEMOTE commit):
#: WYSTAN_ROUTE_RENDER_UTIL_DEMOTE (B93 phantom render-util page demote;
#: keyless novu HTML exhibit §7 CLOSED), WYSTAN_TWIN_FLOW_DECOLLIDE (B92
#: Rung D same-slug flow-name de-collision; keyed RefApp),
#: WYSTAN_TWIN_FEATURE_MERGE (B92 Rung B dup-extraction twin merge; keyed
#: RefApp), WYSTAN_DECORATOR_SUPPORT_EDGES (decorated method → decorator-impl
#: support edges; keyless tracecat), WYSTAN_DISPATCH_RESOLVER (B64 dynamic-
#: dispatch resolver — the forgotten-flip; keyless outline lazy-import routes),
#: WYSTAN_API_CONTAINER_DEMOTE (B91 H4 api-container discriminator; keyed
#: novu Dto), and WYSTAN_AGENT_SURFACE_TS (B81-it2 anchored TS Form A;
#: keyed langfuse). Default flips change what "unset" means, so cached entries
#: keyed under unset must not be served across them (v16/…/v39/v40 precedent).
#: Every flag keeps its X=0 kill-switch (explicit "0"/"false"/"off"/"no"/"" [for
#: the empty-default flags] still disables — inverted-kill-switch unit per flag:
#: unset ≡ explicit "1" byte-identical). The narrow-truthy flags
#: (ROUTE_RENDER_UTIL_DEMOTE / API_CONTAINER_DEMOTE {"1","true"}) preserve their
#: truthy set LITERALLY across the flip. FLOW_SPAN_RECOVERY_* stays OFF (barrel
#: over-count, tune-first — EXCLUDED from the pack).
#: scan_meta.key_schema=41 emitted so downstream rulers gate new-world logic.
#: v42 (flip-pack №9, 2026-07-28 — operator-ratified in-session; each of the 3
#: mechanisms merged default OFF with its exhibit-gate PASS, then flipped here):
#: the pack flips 3 previously-default-OFF product-grain demote flags to default
#: ON, each in its own commit (per flip-protocol), the ONE bump riding the pack's
#: FIRST commit (this NAV_CATEGORY_DEMOTE commit):
#: WYSTAN_NAV_CATEGORY_DEMOTE (B93 nav section-landing demote; exhibit-gate
#: PASS — RefApp keyless 'Feature Studio' OFF 1 hit → ON 0 hits, gate exit-3→
#: exit-0; anti-cases Reporting-Core self-ref / Detectors / API-Keys / Cases-
#: Unified alive; PF 54→53),
#: WYSTAN_SETTINGS_FRAME_DEMOTE (B94 settings-frame demote; exhibit-gate PASS
#: — 'General' papermark OFF 1→ON 0 and plane OFF 1→ON 0; honest-residual trade
#: ratified; documenso D3 blob out of scope; conservation papermark dev 906==906
#: / plane 4545==4545), and
#: WYSTAN_CAPABILITY_SHARED_REHOME (B95 capability SHARED-re-home; exhibit-gate
#: PASS — twenty OFF ['Captcha']→ON 0 hits, PF 52→50; MAX_REAL_UF==0 control-gate;
#: notification-preferences 1-UF protected; conservation dev 508==508 / paths
#: 23782==23782). Default flips change what "unset" means, so cached entries keyed
#: under unset must not be served across them (v16/v21/v25/v27/v28/v29/v30/v31/
#: v32/v33/v34/v36/v37/v38/v39/v40/v41 precedent). Every flag keeps its X=0
#: kill-switch (explicit "0"/"false"/"off"/"no" still disables — inverted-
#: kill-switch unit per flag: unset ≡ explicit "1" byte-identical). The truthy
#: set stays the WIDE {"1","true","yes","on"} (preserved LITERALLY across the
#: flip; default "1" is in-set). scan_meta.key_schema=42 emitted so downstream
#: rulers gate new-world logic.
#: v43 (mechanism B flip, 2026-07-29 — operator-ratified in-session): flips
#: WYSTAN_CONTAINER_JOURNEY_REHOME (Stage 6.9966 container journey-rehome +
#: husk-demote) to default ON. Keyed proof green — hoppscotch Common (7 journeys
#: → 5 domain-PFs born: Collections/Environments/Realtime/Share/Cookies, Common
#: demoted product→dev) + documenso General (3 journeys → Direct Template/
#: Document Signing/Envelope Editor, General demoted via was-rehome-source) +
#: twenty-server demoted, 0 orphan, conservation whole, REST/auth honest-
#: residual. The flip changes what "unset" means (unset → ON), so cached entries
#: keyed under unset must not be served across it. Kill-switch preserved
#: (explicit "0"/"false"/"off"/"no" still disables — inverted-kill-switch unit:
#: unset ≡ explicit "1" byte-identical); WIDE truthy set preserved LITERALLY
#: (default "1" is in-set). scan_meta.key_schema=43 emitted so downstream rulers
#: gate new-world logic.
#: v44 (agent-anatomy flip, 2026-07-29 — operator-ratified in-session): flips the
#: agent-anatomy pack — WYSTAN_AGENT_MOUNT_ATTRIBUTION (Phase-1 registry-mount
#: attribution), WYSTAN_AGENT_SYSTEM_PROMPT (Phase-2 system-prompt detection),
#: WYSTAN_AGENT_SKILLS (Phase-3 skill-layer detection), WYSTAN_AGENT_ANATOMY_ROWS
#: (Phase-4 board-visible import-bridge) — all to default ON in ONE flip-commit,
#: the ONE bump riding it. Each phase merged default OFF with its own gate; the
#: lead ratified the pack. Offline-keyed RefApp proof: 7 agent-consumer journeys
#: incl. UF-AGENT-002 'Agent conversation & tools' (the Chat journey) carry the
#: anatomy — 68 tools + 28 skills + 13 prompts, per-tool LOC spans real 68/68 (no
#: 0-LOC blob); collision-guard holds ('Detectors'/route:detector,
#: 'Prompts'/route:prompt kept SEPARATE — never absorbed); conservation whole (no
#: member surgery — only the agent_surface display tag). The flip changes what
#: "unset" means for all 4 flags (unset → ON), so cached entries keyed under
#: unset must not be served across it. Kill-switch preserved (explicit
#: "0"/"false"/"off"/"no"/"" still disables — inverted-kill-switch unit per flag:
#: unset ≡ explicit "1" byte-identical); the truthy set ("1","true","on","yes")
#: preserved LITERALLY (only the get-default moved ""→"1"). agent-anatomy is
#: INERT on non-agent repos (no tool registry ⇒ census absent ⇒ no reshape), so
#: the flip is byte-identical there. scan_meta.key_schema=44 emitted so
#: downstream rulers gate new-world logic.
#: v45 (flip-pack №10, 2026-07-29 — operator-ratified in-session): flips 2
#: previously-default-OFF flags to default ON in ONE flip-commit, the ONE bump
#: riding it:
#: WYSTAN_VUE_SFC_FLOWS (.vue SFC flow-candidate extraction —
#: ast_extractor._parse_vue_file turns <script setup> top-level bindings /
#: Options-API methods / template @handlers into exports so Vue-front features
#: clear the Stage-3 MIN_EXPORTS gate; keyed proof green — hoppscotch 295
#: vue-flows + graphql born), and
#: WYSTAN_DECLARATIVE_ROUTE_SCOPING (spa-router Seg E TanStack
#: createFileRoute file-routes — URL patterns from code literals into the
#: spa-page source; keyed proof green — reactive-resume TanStack PF + journeys
#: born). Default flips change what "unset" means, so cached entries keyed
#: under unset must not be served across them (v16..v44 precedent). Every flag
#: keeps its X=0 kill-switch (explicit "0"/"false"/"off"/"no"/"" still
#: disables — inverted-kill-switch unit per flag: unset ≡ explicit "1"
#: byte-identical). Both truthy sets stay the WIDE {"1","true","yes","on"}
#: (preserved LITERALLY across the flip; only the get-defaults moved ""→"1"
#: and "0"→"1"). Both arms are INERT on non-Vue / non-TanStack repos (no .vue
#: file ⇒ no new signature; no createFileRoute+dep ⇒ no new candidate), so the
#: flip is byte-identical there. NOT in this pack: WYSTAN_SURFACE_SCOPE_RECALL
#: stays armed-OFF (→ pack №11). scan_meta.key_schema=45 emitted so downstream
#: rulers gate new-world logic.
#: v46 (flip-pack №11, 2026-07-29 — operator-ratified in-session): flips the 3
#: pin-cycle-3 flags to default ON in ONE flip-commit, the ONE bump riding it:
#: WYSTAN_CAPABILITY_MINT_GUARD (Stage 6.9966 mint-gate capability leg — a
#: container-carved domain owning no state-entity/schema and consumed BY the
#: request transport fails promotion → honest-residual, never a peer tile),
#: WYSTAN_WS_CONTAINMENT_FOLD (Stage 6.9967 — a ws: PF strictly nested
#: inside another ws: PF folds into the enclosing package when its journeys
#: are redundant with the enclosing scope; distinct-capability descendants
#: kept), and WYSTAN_ROUTE_STUB_SHAPE (Stage 6.987b — a route/fdir PF whose
#: module renders no component, tiny LOC, micro journey demotes; nav-
#: independent). Proof: keyed hoppscotch exhibit-gate 8/8 green — Cookies /
#: Src Tauri / Enter Redirect disappeared, Hoppscotch Desktop born, UF 31
#: conserved. Default flips change what "unset" means, so cached entries keyed
#: under unset must not be served across them (v16..v45 precedent). Every flag
#: keeps its X=0 kill-switch (explicit "0"/"false"/"off"/"no" still disables —
#: inverted-kill-switch unit per flag: unset ≡ explicit "1" byte-identical).
#: All 3 truthy sets stay the WIDE {"1","true","yes","on"} (preserved
#: LITERALLY across the flip; only the get-defaults moved "0"→"1"). The arms
#: are INERT on repos with no capability-mint candidates / no nested ws
#: anchors / no non-component route stubs (commerce live-KS proof), so the
#: flip is byte-identical there. NOT in this pack: WYSTAN_SURFACE_SCOPE_RECALL
#: stays armed-OFF (awaits twenty/plane keyed proof). scan_meta.key_schema=46
#: emitted so downstream rulers gate new-world logic.
#: v47 (flip-pack №12, 2026-07-29 — operator-ratified in-session): flips 1
#: previously-default-OFF flag to default ON, the ONE bump riding this commit:
#: WYSTAN_SURFACE_SCOPE_RECALL (B58 — three additive husk-recall widenings
#: of the Stage-6.85/6.97 surface taxonomy: product-name-prefixed workspace
#: suffix vs the root_dirs conservative subset (twenty-docs -> docs,
#: twenty-website -> marketing), the .storybook design-system structural
#: signal behind the zero-routes guard (plane packages/propel; routed apps
#: like twenty-front stay product), and dev_artifact_tokens wired to the
#: general classifier at EXACT workspace/root grain — plus the emission-lane
#: anchor-guard that keeps product-anchored PFs off the lane on borrowed
#: shared design-system evidence). Proof: plane keyed 5/5 green —
#: Propel→non_product with its 9 fake per-widget journeys gone,
#: States/Webhooks anchor-guarded in place; twenty offline-proof for the
#: suffix arm (8 husk PFs incl. twenty-docs 3048p / twenty-website 1105p;
#: keyed run memory-blocked). Default flips change what "unset" means, so
#: cached entries keyed under unset must not be served across them
#: (v16..v46 precedent). The flag keeps its X=0 kill-switch (explicit
#: "0"/"false"/"off"/"no" still disables — inverted-kill-switch unit: unset
#: ≡ explicit "1" byte-identical). The truthy set stays the WIDE
#: {"1","true","yes","on"} (preserved LITERALLY across the flip; only the
#: get-default moved "0"→"1"). The arm is INERT on repos with no
#: name-prefixed surface workspaces / no route-less .storybook packages /
#: no exact dev-artifact dirs (commerce live-KS proof), so the flip is
#: byte-identical there. scan_meta.key_schema=47 emitted so downstream
#: rulers gate new-world logic.
#: v48 (flip-pack №13, 2026-07-31 — operator autonomous mandate, Telegram
#: trail): flips 3 previously-default-OFF flags to default ON in ONE
#: flip-commit, the ONE bump riding it: WYSTAN_ORPHAN_FLOW_ATTACH
#: (Stage 6.9945 — the inverse of build_orphan_flow_gaps: an unambiguous
#: orphan-UI cohort folds into the single co-located journey — or the
#: same-PF dominant rival — instead of stamping a coverage_gaps[] row;
#: cross-PF rivalry and no-home cohorts stay honest orphans),
#: WYSTAN_ROUTE_JOURNEY_BACKSTOP (terminal-classification loc_worthy
#: FILE-OWNER rescue — a row whose residue resolves via dev-ledger path
#: ownership to EXACTLY ONE real non-hollow PF dissolves into it; routes
#: corroboration-only; hollow-PF guard binding), and
#: WYSTAN_VUE_NAV_KEYS (nav_parent vue=True parser lift + nav_keys
#: union — Vue/SFC boards stop board-wide abstaining in the 6.987
#: demotes). Proof: RefApp keyed attach 6 cohorts / 40 flows live,
#: guardrails held; hoppscotch keyed vue-nav un-abstain + nav-lane
#: demote; backstop units + offline (live = honest exactly-one abstain of
#: this drawing). Default flips change what "unset" means, so cached
#: entries keyed under unset must not be served across them (v16..v47
#: precedent). Every flag keeps its X=0 kill-switch (explicit "0"/"false"
#: still disables — inverted-kill-switch unit per flag: unset ≡ explicit
#: "1" byte-identical). Truthy sets preserved LITERALLY across the flip
#: (attach + backstop stay the narrow {"1","true"}; vue-nav stays the
#: WIDE {"1","true","yes","on"}); only the get-defaults moved to "1".
#: The arms are INERT on repos with no orphan-UI cohorts / no unmapped
#: loc_worthy rows / no Vue nav registries (commerce live-KS proof), so
#: the flip is byte-identical there. scan_meta.key_schema=48 emitted so
#: downstream rulers gate new-world logic.
#: v49 (flip-pack №14, 2026-07-31 — operator autonomous night mandate,
#: Telegram trail): flips 4 previously-default-OFF flags to default ON in
#: ONE flip-commit, the ONE bump riding it: WYSTAN_TWIN_HUSK_CANONICAL
#: (B92 Rung-B husk-canonical rescue — a guard-tripped collision-suffix
#: family with EXACTLY ONE real-pf member promotes it to canonical, absorbs
#: the shell/fold husks and frees the base name — plus the T5 b85
#: carve-absorb: a home-carve whose content stem names an existing
#: same-stem+pf dev absorbs into it instead of minting a Fix-D suffixed
#: row), WYSTAN_FOLD_HOST_SHELL (Stage 6.9967 host-shell branch — a
#: ws-descendant with ZERO product-surface files folds regardless of drawn
#: journeys, curing the src-tauri kept/folded draw flicker),
#: WYSTAN_PF_LOC_ROLLUP_FIX (Stage 6.97e — FALSY-loc PFs recompute owned
#: LOC from the authoritative path_index, curing member-ful-hollow loc=0),
#: and WYSTAN_UF_METRICS (Stage 6.97d — the Feature-mirror engineering
#: metric family stamped on user_flows[] via proportional span-credit).
#: Proof: keyed RefApp/hoppscotch 4/4: ticketing 3→1, findings 6225,
#: UF-metrics 86/86, src-tauri folded. Default flips change what "unset"
#: means, so cached entries keyed under unset must not be served across
#: them (v16..v48 precedent). Every flag keeps its X=0 kill-switch
#: (explicit "0"/"false" still disables — inverted-kill-switch unit per
#: flag: unset ≡ explicit "1" byte-identical). Truthy/off sets preserved
#: LITERALLY across the flip (twin-husk keeps the _OFF_VALUES set;
#: fold-host-shell stays the WIDE {"1","true","yes","on"}; 6.97d/6.97e keep
#: the narrow off-set {"0","false","False",""}); only the get-defaults
#: moved to "1". Live-KS proof on commerce: unset ≡ ALL-four-explicit-"1"
#: byte-identical (the inverted-KS pair), and ALL-four-explicit-"0" ≡ the
#: pre-flip unset world modulo the scan_meta.key_schema stamp (the 1-field
#: diff precedent). scan_meta.key_schema=49 emitted so downstream rulers
#: gate new-world logic.
#: v50 (flip-pack №15, 2026-07-31 — night mandate; lead keyed 2-draw closing
#: proof): flips WYSTAN_CONTAINER_FILE_MINT (Stage 6.9966-FM file-sourced
#: container minting — an 8.9.5-eligible single-generic-components-blob
#: container decomposes into its file-domain PFs DETERMINISTICALLY from the
#: prompt-hash-CACHED 8.9.5 labels + the median-LOC floor; journeys attach by
#: name; the file-emptied container husk-demotes) to default ON, the ONE bump
#: riding this flip commit. Proof: keyed 2-draw hoppscotch — mint-set
#: identical d1==d2 (PF 20==20, diff ∅), Common demoted on both draws, 10
#: domains stable (history KEPT, no flicker). Default flips change what
#: "unset" means, so cached entries keyed under unset must not be served
#: across them (v16..v49 precedent). The flag keeps its X=0 kill-switch
#: (explicit "0"/"false"/"off"/"no" still disables — inverted-kill-switch
#: unit: unset ≡ explicit "1" byte-identical). The truthy set is preserved
#: LITERALLY (the WIDE {"1","true","yes","on"}); only the get-default moved
#: "0" → "1". The arm is INERT on repos with no 8.9.5-decomposed container
#: (commerce live-KS proof: unset ≡ explicit-"1" byte-identical, and
#: explicit-"0" ≡ the pre-flip unset world modulo the scan_meta.key_schema
#: stamp — the 1-field diff precedent). scan_meta.key_schema=50 emitted so
#: downstream rulers gate new-world logic.
#: v51 (flip-pack #16, 2026-08-02 — operator mandate "the first scan is
#: self-sufficient"): flips WYSTAN_GENERIC_CONTAINER_DEMOTE (B96
#: technical-husk PF demote, Stage 6.9969 post-UF: a 0-real-UF PF with a
#: transport/stoplist/repo-slug name is demoted; members → the anchor
#: ancestor or an honest residual; board-abstain on UF-starved boards) and
#: WYSTAN_EMISSION_HARD_GATE (B97 — the last barrier before Stage 7:
#: E1 LOC recompute/demote, E2 zero-member shells, E3a paren strip with
#: join-key propagation, E3b route-param monsters; journey holders
#: kept+named — the gate never orphans a journey) to default ON — ONE
#: bump for both (a shared proof pack). Proofs: (a) keyed A/B hoppscotch
#: OFF≡ON — 12=12 PF, 68=68 UF, validator net delta ∅ (a no-op CLEAR:
#: the class is no longer minted on the KS50 line — the gates are a pure
#: backstop); (b) the offline effect on a real KS48 board (the demote is
#: EXACTLY {http,graphql,realtime,mockserver}; supabase {static}, the
#: realtime/database/storage anti-case survived) + fresh keyless: directus
#: {components,routes,utils}, highlight {internal,utils}, strapi
#: {utils}; (c) B97 conservation: langfuse datasets/evals paren strip,
#: cal.com routing-forms-2 (a collision suffix), UF sets byte-identical
#: throughout; (d) a simultaneous kill-switch pair on kan, unset≡explicit-0
#: byte-identical (the pre-flip law) + inverted units (unset ≡
#: explicit "1"). Both flags keep X=0 as a kill-switch forever;
#: the truthy sets are preserved literally; only the get defaults "0" → "1".
#: WYSTAN_HEADLESS_PRODUCT_SPINE (B98) is NOT flipped (armed-only:
#: rung-3 route-table decompose + the I1/I13/I8 debts are open).
#: scan_meta.key_schema=51 emitted so downstream rulers gate new-world.
#: v52 (flip-pack #17, 2026-08-03): flips WYSTAN_HEADLESS_PRODUCT_SPINE
#: (the B98 headless-product spine: a v4 page-file mass majority; a
#: route-table decompose into span families via go_func_spans; the
#: api-demote/taxonomy/UF-suppression vetoes — all verdict-gated) to
#: default ON. Dossier: ollama keyed (12 tiles / 14 journeys / span_devs=30,
#: 29→1 violations), traefik (headless+families+lifted), the v4 poles dub
#: PF 115→98 and reactive-resume (over-fire cured), gin/chi library
#: anti-cases (suppressed=framework, lifted=None — the veto lives only with
#: a verdict), cal.com = the same dub form (it self-corrects on the first
#: post-flip scan — recorded explicitly). Kill-switch X=0 forever; the
#: truthy set literally; only the get default "0"→"1".
#: v53 (flip-pack #18, 2026-08-04 — the operator's "flip approved"): flips
#: WYSTAN_ORPHAN_UF_PATH_ATTACH (#3A orphan path-attach), WYSTAN_
#: FLOWFUL_FINAL_COVER (#3B-B1 final-close synth-arm) and WYSTAN_
#: TIER2_JOURNEY_REPARENT (#4 entry-truth move of techno-PF journeys) to
#: default ON — ONE bump for the trio. Dossier: live hoppscotch/unkey/
#: teable; offline world breadth: #4 = 8 moves / 4 boards (0.91-1.0),
#: 3A = 18 attaches / 7 boards, no flooding; the chain
#: attach→reparent→B96-demote proven on a real teable board. Kill-switch
#: X=0 forever; inverted units unset ≡ "1"; the live kan pair identical.
#: v62 (flip #27, 2026-08-06): flips WYSTAN_JOURNEY_LINEAGE_AUDIT
#: (fixb119: a telemetry audit of journey deaths at the post_journey_
#: lattice seam — every death is either ID-BOUND in a named channel
#: (adjudicator demote_map / B84 dissolved_ids / a lane with an id match),
#: or BY NAME in unaccounted + a WARN hook; the board does NOT change) to
#: default ON. Dossier: warden CLEAR-WITH-DEBT #27 — the c12 keyed pair
#: chatwoot (56→53: 7 deaths, 5 id-bound, all 4 demote gaps exist in
#: coverage_gaps[], 1 dissolved_into with a named survivor, unaccounted
#: 2 = the M6 debt) + maybe (56→56, an honest zero); the board is
#: set-identical OFF↔ON on both repos, the only scan_meta delta being the
#: stamp itself. Kill-switch X=0 forever; only the get default "0"→"1".
#: v63 (flip #28, 2026-08-06): flips WYSTAN_RUBY_ASSOC_RANGES
#: (fixb122-A: a fallback-only range for AR assoc/scope — the range is
#: minted ONLY for names with no existing range; an existing method range
#: WINS) + WYSTAN_FLOW_ANCHOR_METHOD_PREF (fixb122-B1: a callable
#: preference for the anchor with a file pin and a universal container
#: gate) to default ON. Dossier: warden CLEAR #28 on the same-draw pair
#: c14/c15 (all hands $0/0, determinism ×2 byte-exact, independent warden
#: hashes with entry_point_line): real-def 0/515+0/142 unmoved on the FULL
#: shared set; line-1 cure 50/61+58/71; class-header cure 47/64+60/73;
#: the population delta (675→733/217→289 flows) is deterministic effect A
#: (stage-3 cost=0, more symbols resolve → more flows survive validation);
#: OFF⊂ON modulo 2 named twin collapses (the S7-B dedup is right) + 3
#: suffix renames.
#: Kill-switch X=0 forever; inverted units unset ≡ "1".
#: v64 (flip #29, 2026-08-06): flips WYSTAN_METRICS_OWNERSHIP_GATE
#: (fixb124 E1: a metric ships ONLY if it was measured on the row's own
#: property — owned_commits==0 ⇒ the whole family null + history/impact
#: null + an abstain stamp; the predicate is equality to zero, ownership
#: is the emitted path_index, no threshold anywhere). Dossier: warden
#: CLEAR #29 on c16/c17 (the structural substrate 889a1c1e1 identical
#: across ALL 4 hands — the gate moves neither a row, nor an anchor, nor
#: LOC; exhibit gate: 8/8 ollama clone tiles abstained by name, 0
#: (94,*,*) groups left; 36 rows of health=100 on zero evidence cured;
#: null-without-a-label = 0 both ways; 3 ratified legitimate collisions
#: untouched). Next wave's exhibit check: novu-188 foreign dev rows.
#: Kill-switch explicit 0 forever; the inverted unit unset ≡ "1".
#: v65 (flip #31, 2026-08-07): flips WYSTAN_CLI_ANCHOR_SUPPLY
#: (fixb125+126: the G1 gate P0∧P1-strict, an anchor supplier that
#: promotes an existing unit at the annex/lane exits of 6.86, command
#: journeys AFTER 6.7d, a rehome-sink guard over the tree of registration
#: sites, a husk veto). Dossier: warden CLEAR-WITH-DEBT #30-bis on the
#: same-draw c22 ($0×6 hands) + structural determinism c22≡c23 6/6; both
#: #30 stops lifted live (api-tags 0.43→0.26; the lambda magnet cured,
#: lh-cli 13168); the B24 line calibrated by the coherent-surface
#: exemption (ratified, the anti-case fires); ollama CLEAR on both hands;
#: 3 lobe-FAIL classes are pre-arc (the KS54 board verbatim). DEBTS:
#: NS-1 the evaporation of ollama journey membership (Σmember 83→57, 40
#: orphans with no acknowledgement; the LLM layer is NOT an authority on
#: count drift) — a re-measure with a fresh keyed run + a
#: journey-conservation detector BEFORE the next flip; NS-2 'Manage cp'
#: raw tokens over declared names (a downstream rename + a demote loop);
#: NS-3 a command↔handler mismatch in the exemption's blind spot; the
#: husk veto never fired; changelog-185 transport-handoff.
#: Kill-switch explicit 0 forever; the inverted unit unset ≡ "1".
#: v66 (flip #33, 2026-08-07): flips WYSTAN_METRICS_OWNERSHIP_GATE_
#: FLOWS (fixb127 E1-flow: the NEVER-measured git family of the flow
#: layer — 80.0 is a literal at stage_5:201 — becomes null +
#: metrics_abstained in both views; coverage/loc/hotspots stay sacred).
#: Dossier: warden CLEAR-WITH-DEBT #32 — c25 both hands $0 on the FIRST
#: try (the gate is post-LLM), 290×80.0 → 290/290 abstained, key-walk:
#: exactly 6 git fields + the label, sacred 0 violations, every other
#: section byte-identical; c26 full-digest determinism ×2; I27 zero
#: (vacuous by construction in the OFF hand — live everywhere after this
#: flip); the NS-1 condition of #30-bis is CLOSED by a fresh measurement
#: (inversion +79%, the default hand stable at 57..59, SUPPLY=0 wandering
#: 33..83). DEBTS: NS-4 "exemption through degeneracy" AGAINST flip #31
#: (fresh c24: ollama-cli magnets an mc=10 journey with 10/10 FOREIGN
#: middleware members → B24 rightly FAILs; the warm exemption held only
#: on mc=1 singletons carrying NS-2 names) — a ribbon BEFORE the next
#: flip; the Q3 fence kept_measured is un-exercised corpus-wide; the view
#: asymmetry is 106/16. Kill-switch explicit 0 forever; the inverted
#: units read unset ≡ "1" (nesting: the parent kill-switch wins).
#: v67 (flip-pack #34, 2026-08-08): flips WYSTAN_UF_VERB_ARM_MODIFIER_
#: GUARD + WYSTAN_SYNTH_DISPLAY_HYGIENE + WYSTAN_UF_VIEW_LEAD_PIN +
#: WYSTAN_NARROWED_NORMAL_RUBRIC (the fixb129-131 naming cycle) default ON.
#: Dossier: warden #36 partial (verb-arm CLEAR-WITH-DEBT: 23 verified
#: renames, 'resume' 4→10, zero structural collateral on rr; the other 3 =
#: an evidentiary HOLD lifted by carriers c32/c33 under the warden's "no
#: new trial" condition): view-pin jsonhero+novu Browse→View live; hygiene
#: langfuse paren_space 2→0; narrowed core-redplanet UF-009 low[missing:
#: verb]→high[structural-route,resource:route] (the jsonhero stays-low
#: anti-case holds). Re-declared per the rulings: the narrowed-floor
#: pair (test_law_b_narrowed_floor_unchanged, test_read_only_over_claim_
#: narrowed) + the View-vs-Browse doctrine. DEBTS: NS-1 the zero-LOC tile
#: (e1_kept), NS-2 the 6.7e apply-time verdict channel (a key WITHOUT
#: KEY_SCHEMA — a bump does NOT mitigate it, a separate decision), NS-3 a
#: verb modifier after a Manage lead (2 rows). Kill-switch explicit 0
#: forever; inverted units unset ≡ "1".
#: v68 (flip-pack #35, 2026-08-09): flips WYSTAN_ROUTE_MARKER_DISPLAY_
#: SANITIZE + WYSTAN_PF_ROUTE_QUALIFIER_RUNG + WYSTAN_PF_DISPLAY_
#: LEXICON (fixb133 PF display doctrine ×3) default ON. Dossier: warden #38
#: GO after three rounds. Live exhibits: umami 11/11 ('(.)sessions'→
#: Sessions, 'me'→My Account, 'shares'→Board Shares, 'sso'→Single Sign-On,
#: 'utm'→UTM Campaigns, 'performance'→Performance Report, 'settings/
#: profile'→Settings Profile); cal.com zero stutter / zero junk parens,
#: 'Setup'→App Setup. The anti-cases hold: Boards/Websites/Teams,
#: 'API Key', 'Social Providers — Apple', 'CalDav (Beta)', 'Enterprise+',
#: '<bin> CLI'. Three warden blockers closed in round 4: (1)
#: qualifier-token magnetism — M2 REGISTERS the injected tokens
#: (Feature.display_qualifier_tokens, Field(exclude=True), purely
#: intra-run), and token_journey_rehome / home_affinity_gate /
#: invariant_hooks / uf_synth_fold SUBTRACT them (UF-046 stays on
#: websites); (2) the junk veto no longer leaves bare generics — a rank
#: replacement via the resource-collection rule (a segment that directly
#: parents a dynamic parameter is a collection) + a categorical route group
#: must pass the same domain-noun test (this kills '(org-admin-only)'); (3)
#: dressing NEVER touches the confidence channels — the R5-3 dir-token lane
#: judges the UNDRESSED base, so 'playground' stays medium +
#: shape:unresolved-dir-token. pf.name does NOT move (display channel
#: only); dirty slugs ('alby-(alby)') are the name-migration queue, a
#: separate operator decision. Kill-switch explicit 0 forever; inverted
#: units unset ≡ "1".
#: v69 (flip-pack #36, 2026-08-09): flips WYSTAN_MINT_QUALIFIER_NO_SELF
#: + WYSTAN_PF_SLUG_SANITIZE + WYSTAN_R5_REPAIR_NO_SELF (fixb134
#: slug-migration ×3) default ON. Dossier: warden #40 GO after four
#: rounds. THE ID CHANNEL is closed: umami '(.)sessions'→'sessions',
#: '(.)replays'→'replays' (devs/ufs re-stamped, zero dangling);
#: cal's self-repeating slugs are gone; documenso/epic-stack escape residue
#: zero; the world law — zero pf.name with marker residue. M4b migrates ALL
#: FOUR declared PF-key channels (types.py :942 product_feature_id,
#: :347 owner_product_feature+owner_display, :1207 cross_links, :1511
#: CoverageGap.product_feature_id) in the SAME pass — law E3a; the
#: stage_8_6_compactor landmine (a re-slug with no propagation) was NOT
#: copied. M4a sits on the REAL producers (lane_excavation:634 +
#: transport_handoff:2785 — there the qualifier is the same terminal
#: segment the display was made from, i.e. a self-repeat BY CONSTRUCTION),
#: with an m4a_prevented counter + row-traceable exhibits.
#: M4c: the R5-1 repair no longer returns a self-repeat — 'Alby (alby)' →
#: 'Alby (Integrations)', parity SATISFIED (not weakened); on an empty
#: walk it is never-worse and never bare. anchor_id and display_name are
#: untouched by the lane; pf.name moves ONLY at emission. OPEN: the owner
#: channel's split-brain has a SECOND producer (the demote lane does not
#: re-stamp shared_paths) — a named finding, a separate cycle. Kill-switch
#: explicit 0 forever; inverted units unset ≡ "1".
#: v70 (flip-pack #37, 2026-08-09): flips WYSTAN_UF_COMPONENT_NAME_DEGLUE
#: (fixb132 authored component-name de-glue, the UF layer) default ON.
#: Dossier: warden #41 GO. THE CLASS: Next/React repos call their page
#: components 'AdminTeamPage', and the journey layer carried the raw
#: identifier AS THE NAME — on umami KS68 that is 19 PascalCase rows (18 =
#: the WHOLE C4 shape:raw-identifier class of that board) + 8 '<X> Page'
#: rows at high. Law C gave them high on their own evidence and the R5-5
#: cap took the score away: the cap is the honest HALF of the cure, the
#: pack is the other. The doctrine line: NS-D protects the AUTHOR'S
#: PRODUCT vocabulary, and a code identifier is not that (the same legal
#: status as a route segment, which the engine de-glues everywhere);
#: the shape test runs FIRST, nav phrasing is untouched.
#: Measured (keyless, a same-world umami replay pair): 18 rows, %high
#: 50.0→79.3, folds 7==7 identical, members/homes/PF/flows identical,
#: 0 demotes, obstacle_course OFF==ON. The keyed convoy pair: 16/22 rows
#: perfect, B16-P1b 'Test Console Page'→'Browse test console' resolved
#: LIVE, conservation UF 58==58 / PF 30==30 / 0 member diffs.
#: THREE LAWS bought by the cade pair: (1) FOLD-NEUTRALITY — de-glue opens
#: a head noun, uf_synth_fold merges rows on the strength of the name this
#: very pass just wrote (7→12 folds, five journeys, a write journey eaten
#: by a read row), so a candidate participating in a fold REFUSES — re-cutting
#: a duplicate family is a MEMBERSHIP question (the B16-P1b ruling verbatim);
#: (2) TRANSACTIONALITY — a refusal is a byte no-op BY CONSTRUCTION
#: (snapshot/restore), the home is CHECKED, never written (a grep guard sank the draft);
#: (3) CHANNEL-CONDITIONAL SEQUENCING — the lane retreats to the
#: post-adjudicator rescore seam when 6.7e is the scan's LIVE writer, and
#: keeps the pre-Law-C slot when it is not. Det-authority is the authority
#: of the VERDICT, not the right to write first: starving the cached LLM
#: stage broke its cache ($0→$0.1006), injected draw variance and cost
#: token_journey_rehome the token 'website' (UF-046 → residual). The
#: deferred order: the adjudicator names first (the cache stays warm), the
#: seam de-glues the RICHER name — 'Website Settings Page' → 'Browse
#: website settings' KEEPS the home token.
#: Plus rung C (welded identifiers 'AdminWebsitesPage WebsitesPage' — a
#: class the adjudicator itself writes), the acronym boundary [A-Z]{2,}[a-z]
#: ('UTMPage', ruling: the spec regex was too narrow) and acronym casing
#: 'Browse utm'→'Browse UTM' via the ALREADY SHIPPED
#: pf_display_doctrine.uppercase_acronyms (one universal lexicon, not a
#: second dictionary). Kill-switch explicit 0 forever; units unset ≡ "1".
#: v71 (flip-pack #38, 2026-08-10): flips WYSTAN_OWNER_LEDGER_RECONCILE
#: (fixb135 owner-ledger reconcile) default ON. Dossier: warden #42 GO.
#: The SECOND split-brain producer is closed: flow_span_split writes
#: file→PF ownership in the MIDDLE of the pipeline, and later
#: renames/demotes left it stale (world: 15 repos nonzero — umami 309,
#: cal 161+). A pass at emission (after pf_slug_sanitize, so it sees the
#: FINAL names) rebuilds the map with the same semantics as
#: flow_span_split._owner_map and re-resolves every owner. Live proof:
#: umami reconciled=15, cal=97, conservation perfect (UF/PF
#: byte-identical, ONLY owner fields moved). Ghosts (no-final-owner: the
#: key names NO live PF) are CLEARED to None — umami 105, cal 85: an
#: unattributed span as "ownerless" is honest, a dead row pointing at a
#: ghost is a lie (the LOC-real doctrine). An unbacked but LIVE key stays
#: and is counted separately. The causal taxonomy discriminates by PF
#: LIVENESS (warden #42: a name can be both a dev and a PF — umami filed
#: 15 "demotes" where there were none). Exhibits dedup by (old,new,path);
#: anchor_id/display_name/pf.name untouched. Kill-switch explicit 0 forever.
#: v72 (flip-pack #39, 2026-08-10 — the arc's LAST flip): flips
#: WYSTAN_FOLD_CANONICAL_VERB_PRIORITY (fixb136 fold-canonical
#: verb-priority + the completion of component de-glue) default ON.
#: Dossier: warden #43 GO.
#: THE DISEASE: uf_synth_fold chose WHO survives a fold by the richness of
#: the name, so the moment any lane made a name richer, the de-glued READ
#: row 'Browse admin websites' outweighed the WRITE journey 'Create & edit
#: websites' and ATE it (five journeys on one umami pair; this is exactly
#: where fixb132's fold-neutrality guard with its nine refused rows came from).
#: MECHANISM: the fold's first question is what the journey DOES.
#: Write/manage (create/update/delete/act) > read (browse/view); on an
#: equal class, the banked rich tiebreak byte-for-byte. The class is read
#: from the ORIGINAL name (a rename does not crown itself) and from the
#: WHOLE phrase, but only a CONJUNCTION extends the claim: 'Browse and
#: manage pixels' is a manage claim, while 'Browse create topic' is an
#: L-C2 stutter, not coordination. 'manage' is absent from
#: journey-action-families.yaml, so the class is also read from the
#: inversion of _ACTION_FAMILY_WORD — the table the engine ITSELF uses to
#: write 'Manage' for the act family (the YAML is untouched: it feeds
#: mfams to Law C).
#: THE LINK: verb-priority alone unblocked only 3 of the 9 rows — L-C3
#: merges every sibling of the same noun head with shared spans, and L-C1
#: merges an echo under a richer canonical, whoever that is. So a row the
#: naming lane renamed IN THIS SCAN is exempt as a FOLD SOURCE (the same
#: fold_exempt_ids the lattice rows already carry; sources only — a
#: de-glued row may WIN a fold and inherit members).
#: A journey must not die of a RENAME.
#: TRANSPORT (bought by battery 15 and four dead journeys): the ids travel
#: through a scan-scoped REGISTRY both sides import, not through
#: telemetry — on the keyed channel the lane diverts into the 6.7e rescore
#: seam, and _rescore_tele_view copies only scalars and SILENTLY dropped
#: the list; the fold planned with an empty exempt set while the oracle
#: had already released rows on that promise. The oracle now plans against
#: THE SAME set.
#: QUALITY: a verbless candidate whose token set already sits in its own
#: PF's display refuses — a bare 'Board' under the PF 'Boards' names no
#: capability, and an honest identifier at medium is better (B46, doctrine
#: law 1). UF-053 stays a residual under the B31 twins law — correct
#: machinery, not a bug.
#: MEASURED (a deterministic umami pair, the same world): 25 rows
#: de-glued, folds 7 == 7 with an IDENTICAL loser set, homes identical,
#: census 79.3% -> 91.4% high. Fresh keyless umami: UF 62 -> 64 (two
#: SAVED journeys), PF 32 == 32. Kill-switch 0 forever; units unset ≡ "1".
#: v73 (2026-08-10): fixb135 rider bugfix — @slot display producer #2.
#: R5-1 identity-parity repair re-read the still-dirty SLUG ('@chat') and
#: overwrote the display the B71 ladder had already cleaned to 'Chat'
#: (live KS72 keyed tracecat disproved the №38 dossier's claim). The
#: repair's candidates now run through the one marker sanitizer.
#: v74 (flip-pack #40, 2026-08-10): flips WYSTAN_VERB_NAME_LEAD_STAMP —
#: unset ≡ "1", an explicit "0" is a kill-switch FOREVER.
#: THE DISEASE. Warden #43: umami UF-025 'Pixel share' at high on
#: ['structural-route','resource:route'] — with no verb:* stamp. The
#: dissection showed something wider than the exhibit: "no verb:* stamp"
#: does NOT mean "not grounded by a verb". Law C takes base_verb =
#: (lead in mfams) or (lead is None and len(mfams) >= 1) and on a generic
#: lead mints ONLY the coarse 'structural-route' (from base_res ∧
#: base_verb) — i.e. the evidence UNDERSTATES the correct grade. On
#: umami there are EXACTLY 8 such rows out of 55 high: SEVEN verb-led
#: ('Create & edit websites', 'Create and edit teams', 'Connect links',
#: 'Export website data', 'Verify subscription and auth tokens', 'Manage
#: queries', 'Create users') and ONE noun-led (UF-025).
#: MECHANISM. A post-pass in the rescore_uf_confidence seam — precisely
#: there because the postmint seam does not see the delta on the keyed
#: channel (round 1 guarded the wrong seam): a verb-led lead + 0 verb:*
#: stamps ⇒ append 'verb:name-lead'.
#: CORROBORATION-ONLY — the stamp rides a HIT in the engine's own table
#: (r5_vocab_sets(...)['verbs'], the same _fold as in
#: unresolved_dir_token); a miss asserts NOTHING. No new dictionary.
#: Lead position matters: 'Pixel share' is not verb-led though 'share' IS listed.
#: GRADE-INERT. The flag NEVER moves name_confidence — it only adds one
#: tag; a verb-led 'low' is stamped and stays 'low'. It abstains entirely
#: when the B40 rungs are off: "no stamp" on a dark channel is a vacuum, not data.
#: LIVE PROOF (keyless umami, its own out-dir, scrubbed before the run):
#:   A unset vs B explicit "1"  digests IDENTICAL sha256:8103d89e8
#:   A vs C explicit "0"        DIFFERENT (9df961274) — kill-switch lives
#:   conservation A vs C        UF 63==63, PF 30==30, flows 202==202
#:   grades moved 0, names moved 0; EXACTLY 2 rows differ, and both
#:   differ only by a trailing 'verb:name-lead'
#: CENSUS: 2136 stamps on 52 cold boards, ZERO grades moved.
#: THE SECOND HALF IS NOT FLIPPED, deliberately. WYSTAN_VERBLESS_NO_HIGH
#: (demoting noun-led high on POSITIVE evidence — the lead IS the row's
#: own resource noun) stays default OFF INDEFINITELY: the same cold
#: triage gave 20 firings with 8 correct, and 12 wrong against 8 correct
#: is a NET LOSS of honesty on the honesty lane. The mechanism is armed,
#: both residual classes are banked in the _resource_noun_lead docstring,
#: and the observation moved eval-side into a TRACK detector.
#: The lane's first attempt read the COMPLEMENT of the verb table as
#: evidence of verblessness — 126 firings, 100 of them (79%) on names
#: whose lead is a verb the 131-word table simply does not carry
#: (authenticate, deploy, navigate, handle, initialize, chat) — the same
#: inversion W1/C-A cured. So corroboration now only short-circuits, and
#: the demote has its own positive evidence.
#: v75 (flip-pack #41, 2026-08-10): flips WYSTAN_LANE_MOVED_DELETE —
#: unset ≡ "1", an explicit "0" is a kill-switch FOREVER. The first flip
#: whose DECISION was made by the operator rather than a warden: fixb119
#: M3 deliberately left the product question open and named the moves BY
#: NAME in ``lane_moved`` so the decision could be made row by row.
#: THE DISEASE. The surface_taxonomy lane move takes a journey out of
#: ``user_flows[]`` and puts a full ``model_dump()`` into
#: ``non_product_surfaces[].user_flows[]``. But the member flows leave the
#: journey layer ENTIRELY with the move: on ALL measured rows
#: ``member_absorbed == 0.00`` — not one member is held by any surviving
#: journey. What remains on the board is a row with a name and a member
#: list pointing at nothing: the hollow-rows disease (class B68/B23).
#: The operator, 2026-08-10, option A: "remove it".
#: MECHANISM. A pass immediately AFTER the move — exactly where
#: ``member_absorbed`` is first known (``user_flows`` is already ==
#: kept_ufs): live = the union of member_flow_ids of surviving journeys;
#: a row with absorbed == 0.00 leaves the lane payload. The member/flow/PF
#: layers are NOT touched (members left with the move), and the lane row
#: keeps paths/member_devs/loc — marketing CODE stays visible. No magic.
#: THE DEATH STAYS ID-BOUND. The deletion removes EXACTLY the id-tier
#: record by which M3 accounted for the row (the physical row in the
#: lane), so the producer stamps two replacements of the same tier:
#: ``lane_deleted_ids`` (a flat id list, audit channel
#: 'surface_taxonomy.lane_deleted') + ``lane_deleted`` with the NAMES —
#: BOTH FULL, uncapped (lead ruling: a capped record is not permanent;
#: the audit's ``lane_moved`` stays a 20-row DISPLAY sample) — plus the
#: M6 per-writer self-report (``writer:surface_taxonomy.
#: _delete_hollow_lane_rows``). The row goes into ``lane_moved`` with an
#: additive ``row_deleted: true`` and is counted in ``lane_deleted``
#: instead of ``lane_retained``. Anti-laundering: physical presence in the
#: lane is ground truth (a claim about a row that IS in the lane yields
#: retained), and an id MATCH is mandatory (the fixb119 law, re-tested).
#: THE MEASURED WORLD — A BLAST OF 356/31, not 13. The spec carried "13
#: rows (typebot 9 / kan 3 / core-redplanet 1)" — that is a subset of
#: fixb119's 8-pair gate, NOT the world. A fresh census of 55 cold boards:
#: 31 boards carry lane journeys, 360 rows in total, of which 356 have
#: ``member_absorbed 0.00`` (deleted) and 4 are partially absorbed (kept).
#: The largest: supabase 80, rybbit 53, midday 39, twenty 37, openstatus
#: 21, better-auth 18, hydrogen 17, plane 15, rallly 10. The sum of
#: ``lane_retained`` across armed boards = 321; the delta to 356 is rows
#: minted AFTER the post-lattice seam, which the audit never
#: snapshotted: the producer channel names them, so they are not silent.
#: The 13 named rows were checked AT THE SEAM, not only at emission: a
#: reconstruction from ``06-stage-feature_loc-input`` captures gave
#: seam-time absorbed 0.00 on all 13 (capture-live ⊇ emission-live).
#: WHAT IS DELIBERATELY NOT DELETED (lead ruling, spec literal): a row
#: with ``member_absorbed == 1.00`` — better-auth ``UF-034`` 'Expose MCP
#: OAuth-protected resource endpoint' (m=5), the ONLY one in the world. It
#: is fully absorbed, so the "dedup shell" argument applies to it, BUT
#: that is a different predicate: absorbed-elsewhere ≠ vanished. Scope
#: creep on an n=1 ruling is how packs rot; the class is under a ratchet.
#: A LIVE INVERTED KILL-SWITCH (keyless epic-stack, scrubbed before every
#: run, output into its own out-dir — the boards untouched):
#:   A unset vs B explicit "1"  digests IDENTICAL sha256:485b8368b
#:   A vs C explicit "0"        DIFFERENT (5943950fe) — kill-switch lives
#:   conservation A vs C        UF 18==18, PF 16==16, flows 39==39
#:   the difference is EXACTLY in the lane payload: nps_uf_rows 0 vs 3;
#:   deaths stayed id_bound 3==3, unaccounted 0==0, conservation_ok both
#:   kan keyless — a VACUUM (0 laned PF without a key): the flag is inert
#: WARDEN: obstacle_course CLEAR 26 PASS / 2 TRACK / 0 FAIL and the
#: validate_scan verdict IDENTICAL between hands (no new class).
#: v76 (2026-08-11): fixb141 — owner-ledger reconcile bugfix. The pack-№38
#: pass shipped calling ``run_owner_ledger_reconcile(product_features,
#: features)`` — the ``flows`` argument omitted on the premise that the
#: bipartite top-level array is a pure alias of the containment views. The
#: fixb141 census disproved it: the array is a SUPERSET (orphan flows —
#: documenso 212, growthbook 242, twenty 239, hoppscotch 188, hydrogen 43),
#: and 47 dead owner keys world-wide lived only behind it, permanently
#: invisible to the mechanism. Restores the pass's OWN claimed coverage —
#: no new flag, same kill-switch. BLAST, engine-derived (the real pass run
#: twice over rehydrated boards, both arms, 7 boards affected):
#:   newly-visible ledger rows 108 -> 63 CHANGED, 0 regressions (B ⊇ A)
#:   41 cleared  (directus 15 'system-data', growthbook 11, hydrogen 10
#:                'hydrogen', strapi 5 'components')
#:   21 reconciled (hoppscotch 15 'selfhost-web'->'collections' — a LIVE
#:                but wrong owner, growthbook 6), 1 display, 8 kept
#: Decomposition: all 47 census-dead rows resolved (41 cleared + 6
#: reconciled); the other 16 are live-key attribution repairs.
#: An offline simulation of the same delta predicted 21 -> 46 reconciled;
#: the engine arm is the authority (sims over-promise) and the number here
#: is the engine's. The fixb135 dossier's coverage claim was wrong, so per
#: protocol honesty this bugfix carries its own bump: 75 -> 76.
#: v77 (2026-08-11): FLIP-PACK #42 — flips WYSTAN_NARROWED_RUBRIC_RESCORE
#: (fixb142 Part 2) and NOTHING else. The pack is deliberately ONE flag.
#:
#: WHAT IT FIXES. fixb129's narrowed-normal rubric has been default-ON
#: since pack #34, but fixb130 item (6) scoped it to ``primary_pass`` — and
#: the FINAL grade is written by the post-mint rescore seams, which are not
#: the primary pass. Result: SEVEN world rows carried ``low`` +
#: ``['missing:verb']`` while ``lead in mfams``, i.e. the engine asserted a
#: verb was missing on rows whose verb its own evidence witnessed. The
#: class was byte-identical at KS66 and at KS75 — the cure never reached
#: the seam that decides. Live exhibit jsonhero-web UF-004:
#: ``naming_contract`` telemetry ends ``{high: 11, medium: 0, low: 0}`` and
#: ``postmint_rescore.flow_name_v2`` (``rows_down: 1``) re-stamps it.
#: ON ⇒ ``low['missing:verb']`` -> ``low['missing:resource']`` — the row
#: still falls, with the TRUE reason. No free uplift.
#: DIRECTION PRESERVED, REASON REPAIRED. The rubric ships paired with a
#: STRICT DEMOTE: a narrowed row is forced at least one step BELOW the
#: confidence it carried into the hook. A mere ceiling was tried first and
#: the full suite refuted it — it lets a narrowed row STAY when the
#: rewritten name re-grounds, silently overturning the R0/fixb106 doctrine
#: (test_jsonhero_uf004_create_item_demotes_honestly /
#: test_novu_uf056_edit_context_demotes_honestly), which fixb129's own
#: docstring named as doctrine rather than stale fixtures. So the code
#: moved, not the tests: Law B rewriting a name in a rescore only happens
#: when the evidence moved, so the row falls — what Part 2 changes is the
#: REASON (ordinary rubric) not the DIRECTION (the old hardcoded ``low`` +
#: ``['missing:verb']`` lied whenever the verb was witnessed).
#:
#: DETECTOR TRAP (measure this class correctly): pack #40 appends
#: ``verb:name-lead`` to the hard-stamped rows, so the naive predicate
#: ``name_evidence == ['missing:verb']`` now matches ZERO of them and reads
#: "cured". Strip the stamp before counting.
#:
#: ARMED, NOT FLIPPED IN THIS PACK — both named with their census reasons:
#:   WYSTAN_UF_COMPOSITE_HEAD_REPAIR (Part 1). Honest yield 8 rows, and
#:     6 of the 8 sit on meilisearch, a DG1-degraded witness (pf_total 0) —
#:     2 non-degraded rows is below the flag bar (fixb139 NO-BUILD
#:     precedent at 6). Two guards ship armed with it: NS-44a (any member
#:     lead absent from journey-action-families ⇒ abstain; unknown !=
#:     unwitnessed, the fixb138 Half-1 inversion — census: 34 candidates,
#:     13 fire with the guard, 21 withheld = 62%) and NS-44b (never rewrite
#:     an already-high row — five world exhibits all read WORSE repaired).
#:     KNOWN DEBT: NS-44b's gate sits BEFORE Law C writes the grade (rows
#:     enter with ``name_confidence = None``), so it abstains on the first
#:     grading and over-suppresses — measured +6 instead of the intended
#:     +8, typebot UF-052 among the casualties. Cure = repair AFTER Law C
#:     with a re-grade; unscoped, deliberately not attempted under a flip.
#:     UNLOCK: the 'manage' table lane (fixb144) — 'manage' is the engine's
#:     OWN canonical flow-name lead (rule-flow-naming: manage-X-flow) and
#:     is absent from its own action-family table, the single largest
#:     source of NS-44a abstentions (8 of 21).
#:   WYSTAN_UF_FLOW_VERB_CLASS (Part 3). 12 net-new rows at ~92%, but
#:     the 2026-08-08 C2-verb probe made the "generic verb vs NO verb"
#:     guard a PRECONDITION for any echo-branch extension, and that guard
#:     does not exist. Precondition unmet ⇒ stays armed. One measured false
#:     positive banked, not tuned: midday 'Run prompts' <-
#:     ``build-invoice-components-flow`` ('build' is a real ``run``-class
#:     member; no scale-invariant discriminant separates it from the 8
#:     true 'Run X' <- ``process-X-flow`` rows).
#: ── v79 (flip-pack №44, fixb145 — the synth-conversion arc) ────────────
#: TWO flags ON: WYSTAN_CLI_JOURNEY_UNSYNTH + WYSTAN_SYNTH_CONVERSION.
#: WYSTAN_SYNTH_CONF_CAP stays UNSET-LEGACY — deliberately: unset reads
#: WYSTAN_FOLD_EVIDENCE_WEIGHT, so a board with that flag's kill-switch in
#: force does NOT quietly get a re-armed cap; an explicit "0" disarms only the cap.
#:
#: CENSUS (55 boards / 4011 UF / 653 synth, KS77): the placeholder row turned
#: out NOT to be a phantom. 0/639 live rows are member-less; the backstop's
#: arm-1 refuses in 781/799 world cases on ``arm1_no_majority_uf`` — NOBODY
#: holds the journey, because 45.7% of dev features and 54.3% of roots never
#: reach the 6.7d digest. The B78-it2 cap stamped these rows ``low`` BEFORE
#: Law C could score them: measured with replay pairs (infisical/langfuse/
#: teable, 200 board-aligned) **171 = 85.5% earn high on their own evidence,
#: with ZERO name changes**. The tag, not the row, was the defect.
#: THREE GUARDS: NS-43a PF-echo (the engine's own is_pf_echo oracle) · a
#: per-PF quota converted <= max(1, the PF's real journeys) · a
#: display-doctrine threshold (residual shape:* + structural_segments; NOT
#: "contains a token" — a measured false refusal on 'digital ocean APP
#: platform'). Survival 50/52 = 96.2%.
#: CHANNEL-A KILL: 6.7e runs AFTER Stage-07 and selects on
#: ``name_confidence != high`` — grading before it bought fresh paid draws
#: (adj_calls 0→12). Keyed defers to a post-6.7e seam; keyless unchanged.
#: NS-46a: a scan-scoped verdict registry (the cap does not re-stamp) + a
#: count of the voided. NS-46d: a 5-bucket ledger (converted / voided /
#: rows_gone / already_unsynthesized / cli_declared_left) + ``sum_ok`` —
#: drift can no longer be silent.
#: CLI probe (keyed, a symmetric ruler): ollama 45.5→71.4 (+25.9pp),
#: lobe-chat 91.6→**89.6 (−2.0pp, recorded honestly)**, tracecat flat.
#: TELEMETRY: lane 1 → scan_meta.cli_journey_unsynth (TOP LEVEL, NOT
#: naming_contract.*); lane 2 → scan_meta.synth_conversion (guards, from 6.7e)
#: + scan_meta.synth_conversion_applied (the ledger).
#: ── v80 (flip-pack #45, fixb143 — mis-laned product code) ──────────────
#: FOUR flags ON under ONE bump (pack ratified 2026-08-13):
#: WYSTAN_PUBLISHED_ARTIFACT_VETO (i-a) · WYSTAN_SHELL_NAME_
#: CORROBORATION (i-c) · WYSTAN_RELEASED_DISPLAY_REGISTRY (r.5 ii-a) ·
#: WYSTAN_ABSTAIN_SCOPE_ROLLBACK (r.5 ii-b). Topological breadth: 4 repos
#: / 4 forms — outline (route shell-release), trigger.dev (monorepo ws
#: dev-scope), strapi (fdir CMS), inbox-zero (Next marketing lanes); keyed
#: on all, the keyless kill-switch 4-way byte-identical in round 5.
#: WYSTAN_ADJUDICATOR_DEP_GUARD (i-d) IS NOT IN THE PACK and stays
#: ARMED — its output changes the adjudicator's LLM payload, and the
#: population drift (ambiguous 27→28→29 on inbox-zero) is still open;
#: unset ≡ "0".
#: PACK FORM: one flag = one commit, the bump rides the FIRST; EVERY flip
#: commit appends its OWN ``flips <FLAG>`` note below, so history bisects —
#: at any commit of the pack the note list equals the list of flipped flags.
#:
#: v80 flips WYSTAN_PUBLISHED_ARTIFACT_VETO — unset ≡ "1", an explicit
#: "0"/false/off/no is a kill-switch FOREVER.
#: THE DISEASE (census fixb143 PHASE-1, 294 lane rows / 32 boards): a
#: published artefact (``bin`` OR ``publishConfig``, NOT ``private``, NOT
#: Storybook) is what a client installs; but ``_is_published_cli`` was
#: consulted only on the ws rung after the lexicon voted ``dev_tooling``, so
#: trigger.dev ``packages/cli-v3`` (package name ``trigger.dev``,
#: bin+publishConfig) read True while ``classify_path`` returned
#: None — the override was UNREACHABLE, and the demote arrived from a
#: DIFFERENT channel (B28 dev_artifact -> instrument dirs) that never asks
#: the override at all. fixb140 lane-deletion then removed 8 real CLI journeys.
#: MECHANISM: a predicate over MEASURED manifests (not a dictionary) votes
#: PRODUCT at TOP precedence; the Storybook clause is the design-system
#: separator, pinned by the counter-example ``@teable/ui-lib`` (published +
#: Storybook = NOT a product). routes-unknown ⇒ the separator is unverifiable
#: ⇒ the veto is SUPPRESSED (fail-safe); with no ``repo_path`` it is inert
#: (keyless byte-identical).
#: ROUND-3 DESTINATION PRECONDITION (warden #45): the veto frees a lane ONLY
#: if the freed material has a HOME — otherwise 6.9966 dissolves the
#: container, 17 anonymous lane rows absorb the body, and I13 conservation
#: falls 0.6% -> 5.6%. An abstain returns the row's OWN flag-OFF hand
#: (never-worse by construction).
#: LIVE PROOF (keyed trigger.dev, the round-5 pair): the precondition
#: ABSTAINS on this board ⇒ ON ≡ OFF byte-for-byte in EVERY row — a 515-dev
#: census, PF 91≡91, UF 149≡149; exhibit #45 (nps, 24121 LOC) did NOT return.
#: Warden #48: CLEAR (vacuously net).
#:
#: v80 flips WYSTAN_SHELL_NAME_CORROBORATION — unset ≡ "1", an explicit
#: "0"/false/off/no is a kill-switch FOREVER.
#: THE DISEASE. The container short-circuit in
#: ``classify_feature_with_signals`` returns ``shell`` from the NAME, before
#: a single path has been read. Live exhibits: strapi ``home-page`` (60
#: paths in ``packages/core``, a workspace of 334 roots) and outline ``home``
#: (72 paths) were demoted on the string ``home``, after which lane-deletion
#: removed 'View and manage home page widgets' (a shipped Strapi admin
#: feature) and 'View pinned and recent documents on home'.
#: MECHANISM. This is NOT a new rule: the standing law "a real product root
#: blocks a non-product verdict" (``member_vote`` on the journey grain,
#: ``_owns_product_route`` at the adjudicator seam) is applied on the FEATURE
#: GRAIN — the short-circuit stands only if the row's own path vote yields
#: ZERO product weight. No threshold and no magic number: one product path
#: is enough, exactly as everywhere else.
#: MEASURED across the 7 world shell-name lanes: 3 move (strapi
#: ``home-page`` product_w=5, outline ``home`` product_w=1, inbox-zero
#: ``home`` product_w=1), 4 hold — including the NAMED anti-case
#: fastapi ``main`` (``docs_src/app_testing``, product_w=0).
#: LIVE PROOF (keyed outline, TWO ON draws): the freed PF is emitted as
#: 'Home Popular' in BOTH draws — warden #47's signature is lifted ROW-LEVEL
#: (not "on average"); the strapi ABSTAIN is valid (r.5 census == r.4 OFF).
#: DEBT NS-48 (named, not blocking): ``_resource_qualification`` takes the
#: qualifier from ``uf.resource`` with no product-noun test —
#: 'Home Popular' <- resource='popular'; queued for naming together with
#: the echo-rename.
#:
#: v80 flips WYSTAN_RELEASED_DISPLAY_REGISTRY — unset ≡ "1", an explicit
#: "0"/false/off/no is a kill-switch FOREVER.
#: THE DISEASE (warden #47 RESURRECTION, every hop checked on the ON board
#: ``outline-143r4redoon.json``): rider (i-c) qualified outline ``home``
#: to 'Home Popular' (``shell_release_qualified``), the row was EMITTED as
#: 'Home', and 'Home Popular' occurred in the WHOLE document exactly once — in
#: that telemetry key. The overwriter is ``naming_contract`` Pass 3
#: (``pm_labeler``, the declared SINGLE display writer): it re-validates the
#: persona pick ONLY through ``display_law_violations``, and
#: ``display_law_violations('Home')`` is empty — I11 ("a container page
#: cannot be a feature", a BANKED operator invariant) is not a display LAW,
#: so at that seam nobody knows the row EARNED its name.
#: A SECOND ON run of THE SAME commit gave ``applied=0`` and kept 'Home
#: Popular': the defect is NON-DETERMINISTIC across draws — which is why
#: telemetry could not be the exhibit, but a census could.
#: MECHANISM (fixb136 precedent, "a promise through a filter is no channel"):
#: the release writes ``pf -> earned display`` into a SCAN-SCOPED registry
#: imported by both modules, and the labeler overwrites a protected row ONLY
#: with a candidate that is itself non-container by THE SAME container
#: dictionary + round-4 de-compounder that earned the name (one source of
#: truth — drift is impossible). A container-only pick refuses and the earned
#: name stands — under ANY draw. The registry is scan-scoped and cleared by
#: the producer on entry, so a long-lived worker cannot hand one scan's
#: promise to the next.
#: LIVE PROOF (keyed outline, BOTH ON draws): ``labeler_earned_display_
#: held=1``, the registry blocks EXACTLY that write (the same candidate goes
#: applied 1 -> 0), and the other 13 PFs are byte-identical to the OFF hand.
#:
#: v80 flips WYSTAN_ABSTAIN_SCOPE_ROLLBACK — unset ≡ "1", an explicit
#: "0"/false/off/no is a kill-switch FOREVER.
#: THE DISEASE (warden #47 new-suspect, consumer-visible on THREE live
#: ON boards). Step 1a stamps EVERY developer row with the ARMED
#: classifier — BEFORE the PF loop decides whether that same flag's release
#: commits; both round-3 riders can abstain, and both abstains rolled back
#: only the PARENT:
#:   * trigger.dev-143r3on: 13 dev rows under ``ws:packages/cli-v3`` (cli,
#:     commands, deploy, entry-points, executions, indexing, mcp, rules,
#:     runtimes, shims, utilities, trigger-dev-imports, trigger.dev-imports;
#:     all pfid='trigger.dev') read ``product``, while the PF and its
#:     lane row read ``dev_tooling`` — ``dev_scopes.dev_tooling`` 13 -> 0
#:     against the verdict ``veto_destination_abstained.restored_scope:
#:     dev_tooling``.
#:   * strapi-143r4on: dev ``home`` (pfid='home-page') shell -> product under
#:     a lane row ``home-page`` that ABSTAINED.
#:   * inbox-zero-143r4redoon: dev ``landing`` shell -> product on a
#:     container name that NO PF-grain qualification vouched for (its home PF
#:     ``components`` was not on the release path) — the same law, second rung.
#: THE LAW: a dev-grain scope release by a flag that CAN abstain is a
#: CONSEQUENCE of its home PF's verdict, never an independent decision. It
#: stands only when that release COMMITTED on the FINAL (post-adjudicator)
#: scope; otherwise the row returns to its own flag-OFF hand — never-worse by
#: construction, the same form as the (i-a) abstain.
#: LIVE PROOF (corpus-wide, BY CENSUS rather than telemetry — telemetry ≠
#: exhibit): 15 rollback records, each ≡ its own OFF hand; rung 2 exactly
#: 1 record; the outline anti-case clean. Warden #48: CLEAR-WITH-DEBT — the
#: invariant hook for abstain mutations does not cover rung 2.
#:
#: v81 flips WYSTAN_WS_ANCHOR_IDENTITY — unset ≡ "1", an explicit
#: "0"/false/off/no/"" is a kill-switch FOREVER.
#: THE DISEASE (fixb147 round 1). fixb143 (i-a) frees a published artefact
#: from the dev-tooling lane, and then has to ABSTAIN on the one form the
#: product side cannot shelter: a bare ``ws:`` anchor above
#: ``FLOOR_JOURNEYS`` journeys (``_destination_survives`` — a bare workspace
#: anchor IS a structural container, and 6.9966 dissolves those). The
#: abstain is never-worse, but it is not an ANSWER: on trigger.dev that row
#: IS the shipped ``trigger`` CLI (8 journeys deploy/dev/init), and it settles
#: into the lane under the repository's name. The defect is IDENTITY, not
#: classification: the row is anchored on the workspace DIRECTORY, while the
#: product it names is the COMMAND surface the manifest declares.
#: MECHANISM: rung A supplies ``cli:<ws-dir>`` (the fixb125
#: ``CliCluster.canonical_id`` form) + the display '<bin> CLI' — and BOTH
#: predicates (``_destination_survives``, ``_is_structural_home``)
#: flip BY THEMSELVES, with no edit to their code. The binary name is npm
#: semantics via ``cli_commands._p1_node``, never a path stem. Rung
#: B: an npm SCOPE becomes identity when the scope-stripped remainder is
#: DEGENERATE (alnum <= 2 — exactly the short_name class of the product-right
#: gate): '@novu/js' -> 'Novu JS'. The scope is STRICT — only the abstaining
#: row; a mass re-anchor of published packages was measured and REJECTED (5
#: trigger.dev rows quietly leave the 6.9965/6.9966 domain).
#: LIVE PROOF (keyed trigger.dev ×3 batteries + novu): abstain -> commit, PF
#: 'Trigger CLI' (cli:packages/cli-v3, 24121 LOC) on a live board in ALL
#: three batteries; novu 'Js' -> 'Novu JS' and the product-right gate CLEAN
#: (``short_name=0`` — world80's install blocker lifted); I22 dangling dev
#: ``product_feature_id`` 14 -> 0. Wardens #50 NO-RESURRECTION / #51
#: CLEAR / #52 CLEAR.
#: RIDING ALONG (not behind the flag, and therefore exactly here): 'js'/'rsc'
#: are promoted from ``armed_acronyms`` into ``known_acronyms``. That table is
#: read by EVERY display path, while the key hashes KEY_SCHEMA +
#: ENV_OUTPUT_FLAGS and NOT the YAML bytes — a promotion without a bump would
#: serve pre-promotion names from the cache under an unchanged key.
#: ``armed_acronyms`` stays alive: its rung walks ``[A-Za-z0-9]+`` while the
#: global lane walks ``[A-Za-z0-9][A-Za-z0-9.\-]*`` (dotted displays = ONE
#: word), so the rung reaches a token after a dot.
#:
#: v81 flips WYSTAN_UNSYNTH_SIBLING_DUP_GUARD — unset ≡ "1", an explicit
#: "0"/false/off/no/"" is a kill-switch FOREVER.
#: THE DISEASE (warden #50, the keyed trigger.dev ON hand). The court's LAW:
#: a fix that RESCUES a row another hand DELETES imports the rescued row's
#: LATENT defects onto a fresh tile. The ``cli_journey_unsynth`` lane fired
#: for the FIRST time on trigger.dev (converted 0 -> 5, because (i) had just
#: freed that tile) — and 2 of the 5 outputs were hollow + substantive
#: duplicates: UF-163 'Deploy your Trigger.dev project to the cloud' (mc=1,
#: loc=0), whose ONLY member does not resolve to a live flow (it is in
#: ``flows[].merged_from`` deploy-application-flow, already owned on the SAME
#: PF by UF-072 'Deploy tasks via CLI', mc=6 loc=1076), and UF-162 over the
#: pre-merge uuid analyze-project-flow belonging to UF-073. BOTH detectors
#: are blind — which is what makes the class worth a flag:
#: ``check_hollow_rows`` nets them via ``abstained_row_ids`` (flip #26), and
#: the uf-dup-names check is STRING-based, so a duplicate wearing its OWN
#: authored sentence read clean.
#: MECHANISM (in the PRODUCER, the stage-hooks law): resolve EVERY member
#: through the merge map; if ALL resolved flows already belong to REAL
#: (non-synth) siblings of the SAME PF, the conversion does not run, the row
#: stays ``synthesized`` (outside the journey ratio on BOTH sides), and the
#: record is id-BOUND with uuid and owner. It deletes no rows and touches no
#: membership.
#: LIVE PROOF (keyed trigger.dev + inbox-zero): 3 suppressions, ALL
#: verified true sibling duplicates (tdev UF-162/163, ibz UF-111); 3
#: legitimate outputs SURVIVED (UF-164/165/166, loc 87/29/87); inert on
#: novu/ollama. Wardens #51 CLEAR / #52 CLEAR.
#:
#: v81 flips WYSTAN_CLI_BIND_GATE — unset ≡ "1", an explicit
#: "0"/false/off/no/"" is a kill-switch FOREVER (it removes BOTH halves: the
#: mint stamp ``declarant_files`` AND the gate ⇒ the field is not serialised).
#: THE DISEASE (iteration-2 probe verdict, 57 minted CLI journeys on 8
#: boards). The CLI journey mint has TWO member-binding rungs. The handler
#: rung (fixb128 NS-3) is exact BY CONSTRUCTION — a flow entering the SYMBOL
#: named by the registration site. The second rung is TOKEN OVERLAP with the
#: flow NAME, and one shared token is not enough: across 28 handler-null rows
#: manual judging gave 11 CORRECT / 16 MISBOUND / 1 PHANTOM —
#: an authored sentence over SOMEONE ELSE'S code ('Display the current logged
#: in user and project details' over ``commands/logout.ts``; 'Manage
#: environment variables…' over ``commands/init.ts``). Lane 1 CONVERTS such
#: rows, i.e. it lifts a false binding out of the synthesized exclusion into
#: the journey ratio under an authored high name.
#: MECHANISM (scoped STRICTLY to handler==null, i.e. binding_confidence !=
#: "high"): V2 — the command's declaring file (the mint STAMP
#: ``declarant_files``) is the member's ``entry_point_file``; V4 — the command
#: token is a segment (or a file stem) of the member's path. EITHER passing ⇒
#: conversion; both failing ⇒ the row stays ``synthesized`` and is counted
#: id-BOUND in ``misbind_suppressed``. The 9 handler-ful rows are out of scope
#: DELIBERATELY: the measured price of ignoring scope is that the V4 hand
#: alone would have killed all 9.
#: LIVE PROOF (battery 40): lane precision 40.7% -> 91.7%; 6
#: suppressed = 6/6 MISBOUND BY NAME, the converted = CORRECT, the 9
#: handler-ful ollama controls untouched; floor inertness proven
#: (the release is live at 5 suppressed). Warden #52 CLEAR.
#: CAVEAT NS-52a (coordinator ruling — KEEP it and NAME it): the V2 hand is
#: VACUOUS on every measured live population (V2 ⊆ V4 in the corpus, 0/12
#: live V2 decisions). It stays as defense-in-depth against the MEASURED
#: cross-cluster token blindness of V4 (lobe-chat inspect/list ×2 clusters).
#: Any future tuning of the gate is OBLIGED to carry the label
#: "V2 unwitnessed".
#: A KNOWN MISS (do NOT tune): ollama 'launch' survives via the directory
#: token collision ``cmd/launch/``.
#: THE ORDER in lane 1 (load-bearing): the dup guard FIRST, the bind gate
#: SECOND — the net is the same either way, but the counters would attribute
#: the cause to the wrong gate, and a counter that lies about a cause is a
#: forensic lie.
#:
#: PACK #46 CLOSED: 3 flipped flags under ONE KS81 bump + the promotion of
#: 'js'/'rsc' into known_acronyms (the pack's only rider outside a kill-switch).
KEY_SCHEMA_VERSION = 81

#: Directory / file-size guards for the non-git tree-hash fallback. Kept
#: scale-invariant (not tuned to any one repo) — they only bound work.
_NONGIT_SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".next", "dist", "build", "target", ".turbo", "vendor",
    ".idea", ".vscode", "coverage", ".ruff_cache",
}
_NONGIT_MAX_FILE_BYTES = 2 * 1024 * 1024  # skip files larger than 2 MiB


# ── gate helpers ─────────────────────────────────────────────────────────


def _flag(env: str) -> bool:
    return os.environ.get(env, "0").strip() not in ("", "0")


def is_enabled() -> bool:
    """``True`` when the operator opted into the scan-result cache."""
    return _flag(ENV_ENABLE)


def is_bypassed() -> bool:
    """``True`` when a forced-fresh scan was requested (still stores)."""
    return _flag(ENV_BYPASS)


# ── engine version ───────────────────────────────────────────────────────


def _pyproject_version() -> str:
    """Version from the nearest ``pyproject.toml`` (walk up from this file).

    Reflects the *code* version (the value hatch reads from
    ``wystan/__init__.py`` via ``pyproject.toml``) even when the installed
    dist metadata is stale. Empty string on any failure.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "pyproject.toml"
        if candidate.is_file():
            try:
                data = tomllib.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, tomllib.TOMLDecodeError):
                return ""
            proj = data.get("project")
            if isinstance(proj, dict):
                v = proj.get("version")
                if isinstance(v, str) and v:
                    return v
            return _hatch_dynamic_version(data, candidate.parent)
    return ""


def _hatch_dynamic_version(data: dict, root: Path) -> str:
    """Resolve a hatch-dynamic version: ``[tool.hatch.version].path``.

    Reads ``__version__ = "..."`` from the file hatch points at (today
    ``wystan/__init__.py``). Empty string when the key or literal is absent.
    """
    tool = data.get("tool")
    hatch = tool.get("hatch") if isinstance(tool, dict) else None
    cfg = hatch.get("version") if isinstance(hatch, dict) else None
    rel = cfg.get("path") if isinstance(cfg, dict) else None
    if not isinstance(rel, str) or not rel:
        return ""
    try:
        src = (root / rel).read_text(encoding="utf-8")
    except OSError:
        return ""
    m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', src, re.M)
    return m.group(1) if m else ""


def engine_version() -> str:
    """Best-effort engine version for the cache key.

    Prefers pyproject (source-of-truth code version), then installed-dist
    metadata, then the module ``__version__``. Returns ``"0"`` only when
    everything fails — the key stays stable, it just loses version
    granularity (never crashes).
    """
    v = _pyproject_version()
    if v:
        return v
    try:
        import importlib.metadata as md

        for dist in ("wystan", "wystan", "wystan"):
            try:
                return md.version(dist)
            except md.PackageNotFoundError:
                continue
    except Exception:  # noqa: BLE001 — metadata is best-effort
        pass
    try:
        from wystan import __version__

        return __version__ or "0"
    except Exception:  # noqa: BLE001
        return "0"


# ── repo content identity ────────────────────────────────────────────────


def _git(repo_path: Path, *args: str, binary: bool = False) -> Any | None:
    """Run a git command scoped to ``repo_path``; ``None`` on any failure."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_path), *args],
            capture_output=True,
            check=True,
            timeout=30,
            text=not binary,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        logger.debug("scan_result_cache: git %s failed (%s)", args, exc)
        return None
    return out.stdout


def _is_git_repo(repo_path: Path) -> bool:
    res = _git(repo_path, "rev-parse", "--is-inside-work-tree")
    return isinstance(res, str) and res.strip() == "true"


def _dirty_hash(repo_path: Path) -> str:
    """Hash of uncommitted state; empty string for a clean tree.

    Combines ``git status --porcelain=v1`` (untracked + modified + staged
    status lines) with ``git diff HEAD`` (the actual content diff of tracked
    modifications, staged + unstaged). A clean checkout → both empty → ``""``.
    """
    # ``--untracked-files=all`` expands untracked DIRECTORIES into individual
    # file entries so each new file gets its own ``?? path`` line.
    status = _git(repo_path, "status", "--porcelain=v1", "--untracked-files=all")
    diff = _git(repo_path, "diff", "HEAD")
    status_s = status or ""
    diff_s = diff or ""
    # Untracked NEW files appear as "?? path" in status but contribute NOTHING to
    # ``git diff HEAD`` — so their CONTENT is invisible to the key unless hashed
    # explicitly (audit Bug 1): editing an untracked file would keep the key
    # stable and serve a stale result.
    untracked_s = _untracked_content_hash(repo_path, status_s)
    if not status_s.strip() and not diff_s.strip() and not untracked_s:
        return ""
    h = hashlib.sha256()
    h.update(b"status\0")
    h.update(status_s.encode("utf-8", "replace"))
    h.update(b"\0diff\0")
    h.update(diff_s.encode("utf-8", "replace"))
    h.update(b"\0untracked\0")
    h.update(untracked_s.encode("utf-8"))
    return h.hexdigest()


def _untracked_content_hash(repo_path: Path, status_s: str) -> str:
    """Content hash of untracked (``?? path``) files listed in ``status_s``.
    Deterministic (sorted), bounded (2 MiB/file; huge files hashed by size)."""
    paths: list[str] = []
    for line in status_s.splitlines():
        if line.startswith("?? "):
            rel = line[3:].strip()
            if rel.startswith('"') and rel.endswith('"'):  # git quotes special names
                rel = rel[1:-1]
            paths.append(rel)
    if not paths:
        return ""
    h = hashlib.sha256()
    for rel in sorted(paths):
        h.update(rel.encode("utf-8", "replace"))
        h.update(b"\0")
        fp = repo_path / rel
        try:
            if fp.is_file():
                size = fp.stat().st_size
                if size <= 2 * 1024 * 1024:
                    h.update(fp.read_bytes())
                else:
                    h.update(f"size:{size}".encode())
        except OSError:
            h.update(b"\0unreadable")
        h.update(b"\0")
    return h.hexdigest()


def _nongit_tree_hash(repo_path: Path) -> str:
    """Deterministic hash of a non-git tree's source files.

    Walks regular files (skipping heavy build/vendor dirs and oversized
    files), hashing sorted ``(relpath, sha256(content))`` pairs. Stable for
    an unchanged tree, distinct when any hashed file changes.
    """
    entries: list[tuple[str, str]] = []
    for path in sorted(repo_path.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(repo_path)
        if any(part in _NONGIT_SKIP_DIRS for part in rel.parts):
            continue
        try:
            if path.stat().st_size > _NONGIT_MAX_FILE_BYTES:
                continue
            data = path.read_bytes()
        except OSError:
            continue
        entries.append((rel.as_posix(), hashlib.sha256(data).hexdigest()))
    h = hashlib.sha256()
    for rel, digest in entries:
        h.update(rel.encode("utf-8", "replace"))
        h.update(b"\0")
        h.update(digest.encode("ascii"))
        h.update(b"\0")
    return h.hexdigest()


def repo_content_identity(repo_path: Path | str) -> dict[str, str]:
    """Return a stable identity for the repo's current content.

    Git tree: ``{"vcs": "git", "head": <sha>, "dirty": <hash-or-empty>}`` —
    a clean checkout at commit X always maps to ``(X, "")``. Non-git tree:
    ``{"vcs": "none", "head": "", "dirty": <tree-hash>}``.
    """
    repo_path = Path(repo_path)
    if _is_git_repo(repo_path):
        head = _git(repo_path, "rev-parse", "HEAD")
        return {
            "vcs": "git",
            "head": (head or "").strip(),
            "dirty": _dirty_hash(repo_path),
        }
    return {"vcs": "none", "head": "", "dirty": _nongit_tree_hash(repo_path)}


# ── config signature + key ───────────────────────────────────────────────


def scan_config_signature(
    *,
    model: str,
    days: int,
    subpath: str | None,
    max_tree_depth: int | None,
    llm_reconcile: bool,
    feature_history: bool,
) -> dict[str, Any]:
    """Everything about the run configuration that changes scan output.

    ``model`` should be the RESOLVED model id (so two aliases for the same
    model share a cache entry). The Stage-6.7d abstraction env flags are
    read here — they materially change ``product_features`` / ``user_flows``.
    Deliberately EXCLUDES run-varying values (run_id, out_path, timestamps,
    org_id, thread identity, cost caps).
    """
    return {
        "model": model or "",
        "days": int(days),
        "subpath": subpath or "",
        "max_tree_depth": (
            int(max_tree_depth) if max_tree_depth is not None else None
        ),
        "llm_reconcile": bool(llm_reconcile),
        "feature_history": bool(feature_history),
        "stage_6_7d_abstraction": _flag(ENV_6_7D_ABSTRACTION),
        "stage_6_7d_abstraction_model": os.environ.get(
            ENV_6_7D_ABSTRACTION_MODEL, "",
        ).strip(),
        # All stage-gating env flags (raw values) — see ENV_OUTPUT_FLAGS.
        "stage_flags": {
            f: os.environ.get(f, "").strip() for f in ENV_OUTPUT_FLAGS
        },
    }


def compute_scan_cache_key(
    repo_path: Path | str,
    *,
    engine_version: str,
    config_signature: dict[str, Any],
) -> str:
    """sha256 over repo identity + engine version + config signature.

    Stable for identical inputs; changes when any tracked file, the config,
    or the engine version changes.
    """
    identity = repo_content_identity(repo_path)
    payload = {
        "key_schema": KEY_SCHEMA_VERSION,
        "identity": identity,
        "engine_version": engine_version,
        "config": config_signature,
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ── storage (raw, byte-exact) ────────────────────────────────────────────


def _scan_cache_path(key: str, *, base_dir: Path | None = None) -> Path:
    """Resolve ``<base>/scan-cache/<safe-key>.json`` (matches CacheKind)."""
    base = base_dir if base_dir is not None else wystan_base_dir()
    return Path(base) / "scan-cache" / f"{_safe_component(key)}.json"


def load_cached_scan(key: str, *, base_dir: Path | None = None) -> str | None:
    """Return the raw stored FeatureMap TEXT, or ``None`` on miss/fault.

    A missing file, an OS error, or an unparseable (corrupt / partial) body
    all count as a MISS — we validate the JSON parses before returning so a
    truncated entry is NEVER served. The raw text (not the parsed dict) is
    returned so the caller can reproduce byte-identical output.
    """
    path = _scan_cache_path(key, base_dir=base_dir)
    try:
        if not path.is_file():
            return None
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("scan_result_cache: read failed %s (%s) — miss", path, exc)
        return None
    try:
        json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "scan_result_cache: corrupt entry %s (%s) — treating as miss",
            path, exc,
        )
        return None
    return raw


def store_scan_result(
    key: str, featuremap_path: Path | str, *, base_dir: Path | None = None,
) -> bool:
    """Copy the written FeatureMap file verbatim into the cache.

    Reads the raw bytes of ``featuremap_path`` and writes them atomically
    (temp file + ``os.replace``) so a crashed write never leaves a partial
    entry. Returns ``True`` on success, ``False`` on any fault (never raises).
    """
    dst = _scan_cache_path(key, base_dir=base_dir)
    try:
        raw = Path(featuremap_path).read_bytes()
    except OSError as exc:
        logger.warning(
            "scan_result_cache: cannot read result %s (%s) — not cached",
            featuremap_path, exc,
        )
        return False
    tmp = dst.with_name(f"{dst.name}.tmp-{os.getpid()}")
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(raw)
        os.replace(tmp, dst)
    except OSError as exc:
        logger.warning("scan_result_cache: write failed %s (%s)", dst, exc)
        try:
            tmp.unlink()
        except OSError:
            pass
        return False
    return True


# ── HIT serving ──────────────────────────────────────────────────────────


def _default_out_path(repo_path: Path | str) -> Path:
    """Mirror ``output.writer.write_feature_map``'s default naming."""
    slug = re.sub(r"[^a-z0-9]+", "-", Path(repo_path).name.lower()).strip("-")
    slug = slug or "repo"
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
    return wystan_base_dir() / f"feature-map-{slug}-{ts}.json"


def serve_from_cache(
    raw_text: str,
    *,
    key: str,
    repo_path: Path | str,
    out_path: Path | str | None,
) -> dict[str, Any] | None:
    """Write the cached bytes to the requested path and build the return dict.

    Returns the same ``{"path": ..., **scan_meta}`` shape ``run_pipeline_v2``
    yields, with a ``scan_cache`` marker flagging the HIT. Returns ``None`` on
    any fault so the orchestrator falls through to a normal scan.
    """
    try:
        data = json.loads(raw_text)
    except (json.JSONDecodeError, ValueError):
        return None
    target = Path(out_path).resolve() if out_path else _default_out_path(repo_path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        # Byte-exact replay of run A's file.
        target.write_text(raw_text, encoding="utf-8")
    except OSError as exc:
        logger.warning(
            "scan_result_cache: could not write served result to %s (%s) "
            "— falling through to a normal scan", target, exc,
        )
        return None
    meta = dict(data.get("scan_meta") or {})
    meta["scan_cache"] = {
        "enabled": True,
        "served_from_cache": True,
        "stored": False,
        "key": key,
    }
    logger.info(
        "scan_result_cache: HIT — scan served from cache (key=%s) → %s ($0)",
        key[:12], target,
    )
    return {"path": str(target), **meta}


__all__ = [
    "ENV_ENABLE",
    "ENV_BYPASS",
    "KEY_SCHEMA_VERSION",
    "is_enabled",
    "is_bypassed",
    "engine_version",
    "repo_content_identity",
    "scan_config_signature",
    "compute_scan_cache_key",
    "load_cached_scan",
    "store_scan_result",
    "serve_from_cache",
]
