"""Stage 6.86 — Anchored PF minting (Product-Spine §4.3, Wave 2b).

THE CORE INVARIANT: a product feature is a named node over an existing
L1 subtree; dev→PF membership derives DETERMINISTICALLY from anchor
lineage. No LLM may move membership (6.7d Call-2, the per-item
classification oracle with the Shared-Platform sink — rootcause RC1 —
is retired behind this stage's flag).

Lineage classification (calibration verdict 2026-07-06, GO):
  * population — every developer feature (``role != facet``); owned
    files = primary ``member_files`` (fallback ``paths``);
  * share(dev, anchor) = |owned ∩ subtree| / |owned|; majority set at
    **θ = 0.5**;
  * SPECIFICITY REDUCTION — a majority anchor whose per-dev matched set
    strictly contains another majority anchor's matched set is dropped
    (route beats enclosing workspace); identical matched sets merge
    (keep the higher-ranked source);
  * UNIQUE when one candidate remains or the top beats the runner-up by
    > 10 pp; near-ties resolve by the fixed ``SOURCE_RANK`` order with
    nav-confirmation as the first tie-break (nav is a ranking confirmer,
    never a subtree source);
  * NONE → the residual ladder (below).

Mint bar (which winning anchors become product features):
  * shells (``ws-app``) never mint — rider R1;
  * ``single_letter`` / ``version_dir`` keys never mint (midday i/p/r/s,
    linkwarden v1/v2) — their devs FOLD;
  * service-dir–only anchors never standalone-mint (operator case:
    RefApp ``panel-query``);
  * PAGE-SURFACE RULE — in a repo that has ≥ 1 PAGE route, an anchor
    whose only surface evidence is API routes / router files / schema
    matches is an implementation surface, not a product capability
    (operator case: RefApp ``api-context-items`` family, supabase
    ``get-utc-time``/``parse-query``); it folds. Repos with no page
    surface at all (pure-API products) keep API anchors mintable;
  * SINGLE-CONTAINER RULE — an unmerged non-authored anchor whose whole
    evidence is ONE file never mints (stray leaf-file class);
  * hub-vendor children mint iff ≥ 1 flow lands in the child (owned or
    entry-file) OR the child owns ≥ 1 source-code file (the amendment's
    stub rule: a single STATIC file — the supabase FDW-wrapper class —
    never mints); hub cores mint iff ≥ 1 sibling vendor minted.

Fold ladder for devs whose winner cannot mint (and the NONE class):
  1. UNION-PLURALITY (rider R2, single-app class) — accept the top
     capability-grain plurality anchor when its share ≥ 0.34 (the
     E-report random-tail bound, the same constant validator I15 gates
     on) AND the anchor is multi-source-confirmed;
  2. PARENT FOLD — version-dir / collection-descend children fold into
     the nearest minting ancestor anchor (``v1`` → its API surface);
  3. IMPORT FOLD — the dev's owned files' OUTGOING imports (workspace-
     aware TS resolver + the python module resolver, the same machinery
     Stage 8.8 uses) majority-target ONE minting capability's dev-owned
     files (midday ``i`` page → invoice components → Invoices);
  4. PLATFORM-INFRASTRUCTURE LANE — the second operator amendment
     (2026-07-06, final): **"Shared Platform" as a product feature no
     longer exists.** Unresolved devs keep ``product_feature_id=None``,
     carry a machine-readable ``shared_reason`` (``no_anchor_lineage`` |
     ``sub_mint_bar_surface`` | ``shell_lineage_only``) and are emitted
     in the top-level ``platform_infrastructure[]`` lane (sibling of
     ``non_product_surfaces[]``); their genuinely-shared files surface
     as ``role="shared"`` members on every consuming feature (the Stage
     8.8 mechanism, extended over the lane residents' files).

Deterministic, $0 LLM, scale-invariant, zero repo-tuned rules.
Kill-switch: ``WYSTAN_SPINE_ANCHORED_MINT=0`` restores the old
Stage 6.5/8 → 6.7d Call-2 path byte-identically (the A/B baseline).
"""

from __future__ import annotations

import hashlib
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from wystan.pipeline_v2.cli_commands import (  # noqa: F401 — re-export
    CLI_ANCHOR_SUPPLY_ENV,
    CliCluster,
    cli_anchor_supply_enabled,
    cluster_of_paths,
    detect_cli_clusters,
    detect_cli_clusters_cached,
    supplied_tile_admits,
)
from wystan.pipeline_v2.spine_anchors import (
    SOURCE_RANK,
    SpineAnchor,
    _bar_reason,
    _display_of,
    build_spine_anchors,
    hub_child_is_plumbing,
    hub_plumbing_child_enabled,
    load_spine_vocab,
    normalize_anchor_key,
    owned_paths_of,
)

if TYPE_CHECKING:  # pragma: no cover — typing only
    from wystan.models.types import Feature

__all__ = [
    "ANCHORED_MINT_ENV",
    "MINT_DOMAIN_FOLD_ENV",
    "FOLD_CROSSAPP_GUARD_ENV",
    "ANNEXATION_GUARD_ENV",
    "SAMEUNIT_DOMAIN_CAP_ENV",
    "FOLD_EVIDENCE_WEIGHT_ENV",
    "FOLD_EVIDENCE_DEMOTE_ENV",
    "mint_domain_fold_enabled",
    "fold_crossapp_guard_enabled",
    "annexation_guard_enabled",
    "sameunit_domain_cap_enabled",
    "fold_evidence_weight_enabled",
    "fold_evidence_demote_enabled",
    "anchored_mint_enabled",
    "run_anchored_mint",
    "build_platform_infrastructure_lane",
    "enforce_hub_family_parity",
    "fold_unreferenced_vendor_husks",
    "husk_post_uf_fold_enabled",
    "HEADLESS_SURFACE_RESCUE_ENV",
    "headless_surface_rescue_enabled",
    "HEADLESS_RESCUE_CLASS_GATE_ENV",
    "headless_rescue_class_gate_enabled",
    "headless_rescue_applies",
    "headless_repo_pages",
    "headless_majority_census",
    "CLI_ANCHOR_SUPPLY_ENV",
    "cli_anchor_supply_enabled",
]

ANCHORED_MINT_ENV = "WYSTAN_SPINE_ANCHORED_MINT"

#: B8c (2026-07-09) — mint-time domain-fold rail. A flowful router dev that
#: the fold ladder folds into a DISTINCT-domain plurality host PF re-homes to
#: its OWN ``<domain>-page`` surface PF when that surface already exists (the
#: webhook exhibit: ``api-webhooks`` + ``webhook-detail-page`` reunite on
#: ``webhooks-page`` so the "Create and manage webhooks" journey re-forms
#: own-PF, I16-clean). Binds ONLY to surfaces that already receive ≥1 dev, so
#: PF count cannot rise (over-decomposition = 0 by construction); same-domain
#: and surface-less routers stay folded exactly as before. Kill-switch:
#: ``WYSTAN_MINT_DOMAIN_FOLD_V2=0`` restores the byte-identical pre-B8c fold.
MINT_DOMAIN_FOLD_ENV = "WYSTAN_MINT_DOMAIN_FOLD_V2"

#: B22a (2026-07-10) — cross-app fold guard. The terminal ancestor-walk rung
#: (``fold:walk``) votes by plurality of ALL assigned files at the first
#: populated ancestor level; a dev whose own workspace unit holds no minted
#: anchor escalates to repo root, where the repo's BIGGEST anchor annexes it
#: across the workspace boundary (documenso forensic: the ``ws:packages/trpc``
#: PF annexed ~90 product files / 11,783 journey span-lines outside
#: ``packages/trpc`` — embed/o/sign-token/d-token from ``apps/remix``, plus
#: ``apps/docs`` and ``apps/openpage-api`` devs — poisoning every downstream
#: owner-map ruler). The guard voids walk votes for anchors whose evidence
#: sits wholly in a FOREIGN workspace unit (a unit holding none of the dev's
#: own files). Unit roots come from the repo's OWN manifests (Stage-0
#: ``detect_workspace``: pnpm-workspace.yaml globs, package.json
#: "workspaces", turbo/nx/lerna/cargo/go; fallback: top-level dirs with their
#: own unit manifest) — mechanisms, not vocabularies; no thresholds.
#: Kill-switch: ``WYSTAN_FOLD_CROSSAPP_GUARD=0`` restores the unguarded
#: walk byte-identically.
FOLD_CROSSAPP_GUARD_ENV = "WYSTAN_FOLD_CROSSAPP_GUARD"

#: B58 (2026-07-13) — container-anchor annexation guard. Two closed holes
#: over B22a (plane ``Issue`` 174K/53% board, novu ``Notifications``
#: 120K/52%, cal.com ``Bookings``+apps/api/v2 — keyed forensics):
#:
#: * Seg A — the B22a guard judged a host FOREIGN by unit-UNANIMITY over
#:   its full evidence union (``prefixes + files``); a same-key MERGE
#:   (plane: svc:issue + issue-named dirs in packages/types/constants)
#:   makes a central host multi-unit ⇒ ``None`` ⇒ never foreign ⇒ it may
#:   annex every cross-unit flowful dev (the i18n 125K exhibit). The
#:   guard now derives the host's unit from its CANONICAL identity (the
#:   anchor-id-embedded path, then route-file unanimity, then evidence
#:   unanimity) and covers the ENTRY and SPAN rescue rungs, which B22a
#:   never wrapped (the cal.com fold:entry->ws:apps/api/v2 exhibit). A
#:   unit-coherent flowful dev is never force-bound across a workspace
#:   boundary — it lanes with its own unit (B22a's honest refusal).
#: * Seg B — an anchor wholly inside a workspace unit whose unit-ROOT
#:   path carries a dev-artifact segment (``playground/*`` — the novu
#:   example apps the repo's own pnpm-workspace.yaml declares) never
#:   mints (bar ``dev_artifact_unit``). Unit-root grain only: cal.com's
#:   product admin PAGE named ``playground`` (a route leaf inside
#:   apps/web) can never fire — the Lane-C "measured out" verdict on
#:   page-grain tokens is preserved. Tokens live in
#:   ``spine-anchor-vocab.yaml:unit_root_artifact_tokens`` (data).
#:
#: Default OFF; ``WYSTAN_ANNEXATION_GUARD=1`` arms both segments.
ANNEXATION_GUARD_ENV = "WYSTAN_ANNEXATION_GUARD"

#: B58-v2 (2026-07-14) — same-unit domain-dir cap. The B58 residual: the
#: guard above judges CROSS-unit force-binds only, so a container anchor
#: still annexes its OWN unit's sibling domains. Two segments, one flag:
#:
#: * Seg A (drain-side, ``ws_blob_domain_drain`` donor class 2) — a
#:   container-anchor PF (``fdir:``/path-tailed ``route:``) sheds member
#:   files that live in a SAME-unit foreign domain-dir (a child of a
#:   ``domain_dir_containers`` segment + the cap-only ``components``
#:   extension) when the domain name echo-matches exactly ONE existing
#:   PF (NamespaceEcho v1 laws: full normalized match, ambiguous → skip,
#:   generic tokens → skip; nav-key-only matches are TELEMETRY, never a
#:   move — no receiver, no conservation hole). Census (keyed boards
#:   2026-07-14, B58-OFF): RefApp ``Media Library``
#:   (fdir:frontend/src/modules/media-library) = 103,796 LOC = 38.6%
#:   of the board over 418 files, of which own-subtree = 148 files
#:   (35.4% files / 17.2% LOC), same-unit foreign ``features/*`` = 15
#:   dirs / 55 files (~20K LOC — 13 of the 15 domain names have an
#:   existing PF receiver: cases/detectors/investigations/integrations/
#:   labels/token-usage/bulletins/inline-suggestions/organization-
#:   members/findings/insights/detections/event-routing), plus
#:   ``components/*`` = 13 dirs / 121 files (29% of the PF's files;
#:   ``components/api-keys`` has NO PF on the annexed board — nav-only
#:   class). NO numeric thresholds: the operator ruling (2026-07-14)
#:   replaced the draft X%/N-dirs fractional cap with the echo gate —
#:   the cap fires exactly where the board itself proves a competing
#:   owner exists (rule-no-magic-tuning: zero constants).
#: * Seg B (mint-side, ``_canonical_anchor_unit`` rung 2.5) — a route
#:   anchor whose full-surface unit test is NON-unanimous (multi-unit
#:   evidence ⇒ canonical unit ``None`` ⇒ "never foreign" ⇒ the B58
#:   fence is blind to it) resolves by unit unanimity over its PAGE
#:   surface only. Census: plane ``spaces`` (route:space) = 75,978 LOC =
#:   39.1% of the board over 575 paths — 451 files annexed from
#:   apps/api (db 177 / app 110 / api 47 — the api's SHARED core) vs
#:   124 own apps/space files; its page routes live wholly in
#:   ``apps/space/app/**`` while api routes live in apps/api, so the
#:   page-surface rung restores the fence. Full-stack lineage binds are
#:   untouched (RefApp route:detection carries 28 backend/routers files
#:   via LINEAGE — the fence guards rescue rungs only). Api-only
#:   multi-unit anchors still resolve ``None`` (conservative). Seg B is
#:   live only while the B58 guard itself is armed (the fence machinery
#:   it feeds is Seg-A-of-B58 property).
#:
#: Default OFF; ``WYSTAN_SAMEUNIT_DOMAIN_CAP=1`` arms both segments.
#: OFF is byte-identical to the pre-B58-v2 pipeline.
SAMEUNIT_DOMAIN_CAP_ENV = "WYSTAN_SAMEUNIT_DOMAIN_CAP"

#: B98 — headless-product spine (operator exhibit ollama 2026-08-02): a
#: SINGLE flowless page-bearing satellite anchor (the desktop-webview
#: ``app/ui/app``, 2 spa-page files) flipped ``repo_has_pages`` for the
#: whole repo and barred its ENTIRE product surface (45 go-router API
#: anchors) as ``api_only_surface`` — an API/CLI product emitted 0 PFs.
#: The rule is page-DOMINANCE, not page-EXISTENCE: with the flag armed, a
#: repo whose page evidence is exactly ONE anchor with NO flow evidence in
#: its subtree is judged HEADLESS (the API surface IS the product; the
#: count-grain constant 1 follows the widget-micro precedent; a real
#: single-page web app carries flows in its page subtree and stays paged).
#: Default OFF (armed-only; flip rides its own commit + keyed proof).
HEADLESS_PRODUCT_SPINE_ENV = "WYSTAN_HEADLESS_PRODUCT_SPINE"

#: fixb108-v2 Fix-3 — the page-surface FLOW-EVIDENCE rescue rung.
#:
#: :func:`headless_repo_pages` documents three rescues for a real web
#: app — "pages spanning multiple top trees (common root ≈ repo root), a
#: nav-confirmed page anchor, or **flow evidence inside the surface**" —
#: and B98's own rationale rests on the last one ("a real single-page web
#: app carries flows in its page subtree and stays paged"; ollama's
#: satellite is "flowless, nav-less"). The first rescue is implemented;
#: the flow-evidence rescue never was. ``flow_entries`` is accepted as a
#: parameter and never referenced in the body — a DEAD parameter.
#:
#: Nothing exposed the gap while route anchors were extractor-sparse.
#: B108's Rails route-supply lands 238 API anchors over 202 controller
#: files outside chatwoot's Vue dashboard, against 35 page-route files,
#: so the majority flips a repo with a full product UI to headless in
#: EITHER grain (anchors 238>35, distinct files 202>35 — the file-grain
#: hypothesis was measured and REFUTED before this rung was written).
#:
#: The blast radius of that false verdict is the whole demote family:
#: ``api_stub_demote`` / ``api_container_demote`` carry an explicit
#: ``not _headless_repo`` precondition (phase_finalize), so both stages
#: go NULL — the guard stops running — and the mint additionally bars
#: every non-route structural anchor as ``headless_internal_package``
#: (chatwoot ``dev:documents``, ``dev:voice``).
#:
#: Armed, a page surface carrying ≥1 flow entry point keeps the repo
#: paged regardless of API mass. Mechanism, not vocabulary: presence of
#: product behaviour in the page subtree, no constants, no repo names.
#: OFF ⇒ byte-identical.
HEADLESS_SURFACE_RESCUE_ENV = "WYSTAN_HEADLESS_SURFACE_RESCUE"

#: B113 (fixb113) — the headless-rescue CLASS gate. Operator exhibit: ollama
#: KS60 = 0 PF / 0 UF / 0 degradations SILENTLY (KS57 board: 12 tiles /
#: 11 journeys), the flip-№24 rescue INVERTING B98 on the very class B98 was
#: built for.
#:
#: The measured chain (world-60 artifacts + 6.86 replay captures, VERIFIED):
#: ollama's page surface is ``app/ui/app/src/routes`` — the desktop-webview
#: satellite, 2 page files against 43 API anchors, so the v4 majority calls
#: the repo headless. The rescue then reads TWO flow entry points inside that
#: surface (``__root.tsx`` — the TanStack layout shell — and ``settings.tsx``
#: — a page-route file the majority ALREADY counted) and overturns the
#: verdict. ``repo_has_pages`` flips True ⇒ (a) every route anchor is barred
#: ``api_only_surface`` (``pf_minted`` 12 → 0) and (b) the B98 spine never
#: stamps ``headless_product_spine``, so phase_finalize never LIFTS the
#: ``repo_class:infra-daemon`` UF suppression (``uf_suppression_lifted`` →
#: ``uf_suppressed_reason``). An API/CLI product emits an empty board with no
#: degradation to explain it.
#:
#: The cure is NOT an evidence-quality tweak — three of those were measured
#: and REFUTED on the live captures before this gate was written:
#:
#: * "flow entries that are not themselves page files" — chatwoot has ZERO
#:   (20/20 of its rescue evidence ARE page-route files), so the prong that
#:   kills ollama kills the rescue's own reason to exist;
#: * "a nav-confirmed page anchor" (the rescue this docstring family also
#:   promises) — chatwoot 0/31 and ente 0/25 nav-confirmed page anchors,
#:   dokploy 1/53; nav would kill two of the three product-app survivors;
#: * "page-file grain" — already measured+refuted by fixb108-v2 itself.
#:
#: The real defect is CLASS-BLINDNESS: the rescue and the B98 spine own
#: DIFFERENT populations. B98 exists so that a unit whose Stage-0.7 verdict is
#: ``library`` / ``cli-tool`` / ``infra-daemon`` / ``framework`` — where the
#: API/CLI *is* the product — gets a product layer at all (the headless
#: verdict is what lifts UF suppression). The rescue exists so that a
#: ``product-app`` with a heavy API surface keeps its page UI. Letting a
#: 2-file webview satellite overturn the majority on a non-product-app unit
#: contradicts the engine's OWN class verdict — the same doctrine (and the
#: same ``_scan_unit_repo_class`` rail) that B105 FIX-2 already applies to the
#: empty-mint stamp: "no thresholds, no per-repo constants: the gate is the
#: existing repo-class verdict".
#:
#: Armed, the rescue rung is a PRODUCT-APP rung. A ``None`` class (un-
#: classifiable ctx) keeps the status quo — the conservative direction, B105's
#: precedent. Blast radius measured on every repo with a 6.86 capture: the
#: rescue OVERTURNS the v4 majority on exactly four units — chatwoot, dokploy,
#: ente (all ``product-app``, untouched) and ollama (``infra-daemon``, cured).
#: Default OFF ⇒ no branch, no new tele key, byte-identical.
HEADLESS_RESCUE_CLASS_GATE_ENV = "WYSTAN_HEADLESS_RESCUE_CLASS_GATE"


def headless_surface_rescue_enabled() -> bool:
    """fixb108-v2 Fix-3 — page-surface flow-evidence rescue. Default OFF
    (armed): unset keeps the v4 majority byte-identical. ``=1`` arms;
    explicit ``=0`` is a kill-switch forever."""
    return os.environ.get(HEADLESS_SURFACE_RESCUE_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def headless_rescue_class_gate_enabled() -> bool:
    """B113 — the headless-rescue class gate. Default **OFF**: unset keeps
    the flip-№24 world byte-identical. ``=1`` arms; explicit ``=0`` is a
    kill-switch forever."""
    return os.environ.get(
        HEADLESS_RESCUE_CLASS_GATE_ENV, "1",
    ).strip().lower() in {"1", "true", "yes", "on"}


def headless_rescue_applies(repo_class: "str | None") -> bool:
    """Does the flow-evidence rescue rung own THIS scan unit? (B113)

    Gate OFF ⇒ always ``True`` — the rung is class-blind exactly as
    flip-№24 shipped it (byte-identity). Gate ON ⇒ the rung is a
    ``product-app`` rung; an unclassifiable unit (``None``) keeps the
    status quo. Pure, unit-testable, zero constants.
    """
    if not headless_rescue_class_gate_enabled():
        return True
    if repo_class is None:
        return True
    from wystan.pipeline_v2.stage_0_7_repo_class import (
        REPO_CLASS_PRODUCT_APP,
    )
    return repo_class == REPO_CLASS_PRODUCT_APP


def headless_product_spine_enabled() -> bool:
    """B98 headless-product spine — default **ON** since flip-pack #17
    (KEY_SCHEMA 52, 2026-08-03). Dossier: ollama keyed 12 tiles/14 journeys
    (I8 veto + span families), traefik headless+families+lifted, dub/
    reactive-resume v4 poles (over-fire cured by page-file mass),
    gin/chi library anti-cases (framework suppression is NOT lifted without
    a verdict), rust honestly out of scope (no route material). Unset ≡
    explicit ``1`` (the inverted kill-switch unit); explicit ``0`` ⇒
    kill-switch forever."""
    return os.environ.get(HEADLESS_PRODUCT_SPINE_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _headless_page_surface(
    anchors: "list[SpineAnchor]",
) -> "tuple[str | None, list, int]":
    """``(common_page_dir, api_anchors_outside, total_page_files)``.

    The shared arithmetic behind the B98 verdict and its census stamp —
    ONE code path so the telemetry can never disagree with the decision
    it reports. ``common_page_dir`` is ``None`` when the majority never
    applies (no page evidence, or pages span the repo root).
    """
    page_anchors = [a for a in anchors if a.page_route_files]
    if not page_anchors:
        return None, [], 0
    dirs = [os.path.dirname(str(f)) or "." for a in page_anchors
            for f in a.page_route_files]
    try:
        common = os.path.commonpath(dirs)
    except ValueError:  # mixed abs/rel — refuse the verdict, stay paged
        return None, [], 0
    if common in ("", ".", "/"):
        return None, [], 0
    prefix = common.rstrip("/") + "/"
    outside = [
        a for a in anchors
        if a.source == "route" and not a.page_route_files
        and not any(str(f).startswith(prefix) for f in (a.files or ()))
    ]
    total_page_files = sum(len(a.page_route_files) for a in page_anchors)
    return common, outside, total_page_files


def _page_surface_flow_evidence(
    common: str | None,
    flow_entries: dict[str, list[str]],
) -> int:
    """How many flow ENTRY POINTS live inside the page surface ``common``.

    The B98 rescue signal: a real web app's page subtree carries product
    behaviour; a desktop-webview satellite (ollama) carries none.
    """
    if not common:
        return 0
    prefix = common.rstrip("/") + "/"
    return sum(1 for ep in flow_entries if str(ep).startswith(prefix))


def headless_majority_census(
    anchors: "list[SpineAnchor]",
    flow_entries: dict[str, list[str]] | None = None,
    repo_class: "str | None" = None,
) -> dict:
    """fixb108-v2 Fix-3 — the headless verdict's inputs, stamped.

    Makes the verdict auditable from the artifact: the anchor-side count
    (what v4 compares) next to the distinct-FILE count (the file-grain
    hypothesis this sprint measured and refuted), the page-file mass, and
    the flow-evidence rescue signal that actually decides it.

    B113: under the class gate the stamp also carries the class verdict and
    whether it withheld the rung — so "why is this repo paged/headless" is
    answerable from the artifact alone. Gate OFF ⇒ the two keys are absent
    ⇒ byte-identical to the flip-№24 stamp.
    """
    common, outside, total_page_files = _headless_page_surface(anchors)
    api_files = {str(f) for a in outside for f in (a.files or ())}
    census = {
        "page_satellite": common,
        "api_anchors_outside": len(outside),
        "api_files_outside": len(api_files),
        "total_page_files": total_page_files,
        "page_surface_flows": _page_surface_flow_evidence(
            common, flow_entries or {}),
        "rescue_armed": headless_surface_rescue_enabled(),
    }
    if headless_rescue_class_gate_enabled():
        census["rescue_repo_class"] = repo_class
        census["rescue_class_withheld"] = not headless_rescue_applies(
            repo_class)
    return census


def headless_repo_pages(
    anchors: "list[SpineAnchor]",
    flow_entries: dict[str, list[str]],
    repo_class: "str | None" = None,
) -> "tuple[bool, str | None]":
    """The B98 page-dominance verdict: ``(repo_has_pages, satellite_dir)``.

    Page-DOMINANCE, not page-existence (iter-2 after the exhibit refute:
    ollama's 2 webview pages ride TWO route anchors, so an anchor-count
    grain misses). The unit is the page-SURFACE: the deepest common dir of
    ALL page files. One flowless, nav-less proper-subtree surface (the
    desktop-webview satellite) does not make an API-product repo "paged";
    a real web app is saved by ANY of: pages spanning multiple top trees
    (common root ≈ repo root), a nav-confirmed page anchor, or flow
    evidence inside the surface. Pure, unit-testable."""
    if not [a for a in anchors if a.page_route_files]:
        return False, None
    if not headless_product_spine_enabled():
        return True, None
    common, outside, total_page_files = _headless_page_surface(anchors)
    if common is None:
        return True, None  # pages span the repo — a real web product
    # v4 (the world aggregate refuted the v3 anchor majority: tRPC-heavy web
    # monorepos — cal.com/dub/inbox-zero — have MORE api anchors than page
    # ANCHORS and were wrongly judged headless). Majority by page FILES:
    # surface mass is files, not anchors (ollama 45 api > 2 page files →
    # headless; dub: api ~60 < hundreds of apps/web page files → paged).
    if (headless_surface_rescue_enabled()
            and headless_rescue_applies(repo_class)
            and _page_surface_flow_evidence(common, flow_entries)):
        # fixb108-v2 Fix-3 — the rescue this function's own docstring
        # promises but never implemented (``flow_entries`` was a dead
        # parameter). A page surface that carries product behaviour is a
        # product UI: API mass outside it cannot make the repo headless.
        #
        # B113 REFUTES this rung's own ollama claim ("ollama's flowless
        # webview satellite is unaffected — it has no flow entry points in
        # its subtree"): the live 6.86 capture shows TWO — the TanStack
        # ``__root.tsx`` layout shell and the already-counted ``settings.tsx``
        # page file. The rung is sound for a ``product-app``; on a unit the
        # engine already classed library/CLI/infra/framework it inverts the
        # B98 spine that class depends on, so ``headless_rescue_applies``
        # withholds it there (gate OFF ⇒ always True ⇒ byte-identical).
        return True, None
    if len(outside) > total_page_files:
        return False, common
    return True, None

#: B69-v2 — PF-homing hygiene family. The mint's ONLY duty under this flag
#: is exporting its anchor registry to the Stage 6.99b post-UF rehome rail
#: (``tele["homing_hygiene_anchor_registry"]`` — popped by the finalize
#: caller BEFORE the tele reaches scan_meta / the stage artifact, so the
#: serialized output never carries it). The mint's fold ladder itself is
#: UNTOUCHED (the mint-time Seg A of the banked fix/b69-pf-homing branch
#: was refuted for redraw collateral — re-seed plurality + touched-set
#: coupling in route_group_recall; the v2 cure is post-UF). Default OFF;
#: OFF ⇒ the tele key is never attached ⇒ byte-identical.
HOMING_HYGIENE_ENV = "WYSTAN_HOMING_HYGIENE"

#: B78 Seg A (2026-07-21) — walk-evidence gate. The terminal ancestor-walk
#: rung folds by PLURALITY OF FILES at the first populated ancestor level —
#: a ruler with zero behavioral content: on RefApp, 0/35 ``fold:walk`` targets
#: held ANY claim on the folded dev's flow ENTRY files (api-admin: 43 flows
#: enter ``backend/routers/admin.py``, yet the frontend file majority folded
#: the dev into ``media-library``; the ``cases``/``media-library``
#: vacuum PFs are this rung's product). LAW under the flag: an ancestor-walk
#: fold is VALID only when the walk target has a behavioral claim on the
#: dev's entry files; an evidence-VOID fold re-disposes by the dev's own
#: entry evidence instead (probe canon 2026-07-21 + Fable rulings R1-R3):
#:
#: * The dev's entry files elect the best evidence-claiming anchor —
#:   most-specific match (exact file > longest prefix), R1 tiebreak on
#:   exact-file ties: the route-convention anchor named by the entry
#:   file's OWN stem, else the anchor holding the larger share of the
#:   file's routes (without R1, api-admin mints as 'webhook-dispatcher').
#: * R2 mint-vs-fold: >=2 distinct entry files OR >=2 flows => standalone
#:   mint of that anchor (on-demand; entry evidence IS the behavioral
#:   proof, so an api_only_surface bar yields — structural bars and
#:   shells never mint); exactly 1 flow => fold into the nearest
#:   evidence-claiming MINTED PF (most-specific minted claimant of the
#:   entry file), minting only when no such PF exists.
#: * R3: a flowful dev is NEVER laned by this gate (lane stays flow-less
#:   only); a dev with no evidence-claiming anchor at all keeps its void
#:   walk fold honestly (tele ``walk_evidence_void_kept``).
#:
#: The entry/span/import/api-parent rungs, lineage binds and the B22a
#: guard-isolated lane are UNTOUCHED (the api-parent lateral channel was
#: probed and REFUTED — already ancestry-guarded, 0 firings). Default OFF;
#: Default ON since the 2026-07-22 flip-pack №4 (KEY_SCHEMA 36); explicit
#: ``=0`` restores the ungated walk byte-identically (kill-switch forever).
FOLD_EVIDENCE_WEIGHT_ENV = "WYSTAN_FOLD_EVIDENCE_WEIGHT"

#: B85 (2026-07-22) — the B22a-resurrection FENCE: the Stage 6.996 post-fold
#: domain-foreignness demote (``fold_evidence_demote.py``; it2 ruling —
#: relocated from the mint tail to AFTER the last homing writer, the B78-B/C/D
#: 6.995 precedent: the mint-time cut stranded mass whose natural home is a
#: mint-barred anchor populated only downstream, dissolving supabase
#: Security/Login). For each on-board PF it recovers the anchor's STATIC
#: canonical domain Da by four rungs (all zero post-fold mass — the
#: circularity guard):
#:
#:   R1  id-embedded path unit        (``route:frontend/src/pages/mssp`` →
#:                                     the ``_unit_of`` of the id tail)
#:   R2  ENTRY(api)-surface unanimity (the P4 tune: entry BEFORE page — the
#:                                     anchor is minted from its entry evidence,
#:                                     the entry IS the identity; without this
#:                                     only 1/5 RefApp canonical annexers heal)
#:   R3  page-surface unanimity       (engine rung-2.5 shape)
#:   R4  evidence unanimity           (files ∪ api ∪ page ∪ prefixes)
#:   None ⇒ genuinely cross-unit — the gate is INERT for that PF.
#:
#: Then a PER-DEV, PER-FILE strip: each contributing dev sheds ONLY its
#: FOREIGN-outside mass (outside the anchor's static containment AND on the
#: far side of the domain/unit edge from Da). Inside + same-domain-outside
#: files are UNTOUCHED (ratio + plurality were both probed and REFUTED — the
#: supabase self-mass anti-cases die under either). Each shed file RE-HOMES to
#: its natural home — the most-specific OTHER on-board PF whose anchor's own
#: static evidence claims it (identity containment, never annexation); only
#: homeless mass (shared infra) falls to the B22a ``cross_unit_isolation``
#: lane. Demote ≠ delete — conservation: stripped == re-homed, 0 orphans,
#: flows on demoted devs preserved. RULING side-effect-3: a file outside ALL
#: units via the top-level fallback (a repo-root file, no ``/`` — RefApp
#: WIDGET_LIBRARY.md) is NEVER foreign (``outside-unit does not veto``);
#: Dashboards heals on the remaining frontend mass.
#:
#: Armed ONLY inside the EVW world (``fold_evidence_weight_enabled``); default
#: ON since world 37 (this changes what the UNSET default world emits, so the
#: KEY_SCHEMA rides 36→37 with this commit — world 36 was never published, so
#: the bump is clean). Inverted kill-switch: unset ≡ explicit ``1``
#: byte-identical; explicit ``0``/``false``/``off``/``no`` restores the
#: EVW-only (pre-demote) world forever.
FOLD_EVIDENCE_DEMOTE_ENV = "WYSTAN_FOLD_EVIDENCE_DEMOTE"

#: B87 rung-2 (product-right gate; default OFF, KEY_SCHEMA neutral —
#: append to ``ENV_OUTPUT_FLAGS`` only). Arms three mechanical
#: extensions of existing bars (probe-canon E2, 2026-07-23): (1) a
#: dev-standalone mint candidate passes a NARROW bar — single_letter |
#: version_dir | technology_instrument | micro-LOC(<100)-demote — with
#: ``api_only_surface`` DELIBERATELY EXCLUDED (it fires on 100 % of
#: standalone anchors by construction, over-killing live surfaces:
#: plane magic-sign-up / novu channels / RefApp home+activity); (2) the
#: fdir/ws page fiat requires real evidence (UF ∨ nav ∨ page ∨ flow);
#: (3) a post-mint token-grain journey re-home (stage 6.9965). Default ON
#: since flip-pack №6 (KEY_SCHEMA 39); explicit ``0``/``false``/``off``/``no``
#: ⇒ byte-identical to pre-B87 (kill-switch forever).
PRODUCT_RIGHT_GATE_ENV = "WYSTAN_PRODUCT_RIGHT_GATE"

#: B105 FIX-2 — ``applied`` must mean "the spine DECIDED the product
#: universe", not "the mint ran". Today :func:`run_anchored_mint` stamps
#: ``applied=True`` UNCONDITIONALLY at its tail, so a mint whose bars
#: barred 100 % of the anchors (``pf_minted == 0``) still tells
#: phase_finalize "adopt my answer" — and finalize then DISCARDS the
#: deterministic clusterer's product layer in favour of ``[]`` (maybe:
#: 7 PFs thrown away; meilisearch: 3). Armed, the stamp becomes
#: ``bool(product_features)`` — but ONLY for a ``product-app`` scan unit
#: (the class the engine already computes at Stage 0.7). On a
#: ``library`` / ``cli-tool`` / ``infra-daemon`` / ``framework`` unit an
#: EMPTY product layer is the CORRECT answer (PF = user-usable doctrine —
#: axios would otherwise regain 4 phantom PFs, caddy 9), so those keep
#: the unconditional stamp. No thresholds, no per-repo constants: the
#: gate is the existing repo-class verdict. Default OFF ⇒ byte-identical.
MINT_EMPTY_HONEST_ENV = "WYSTAN_MINT_EMPTY_HONEST"

#: Micro-LOC floor for the standalone dev-demote prong (probe-canon E2:
#: ``<100``). Scale-invariant absolute-code-line floor, same doctrine as
#: ``_HUB_HUSK_LOC_FLOOR`` — a body this small carries no product right.
_STANDALONE_MICRO_LOC_FLOOR = 100

#: θ — the majority threshold (calibration §F: U-cap is monotonically
#: decreasing in θ; 0.5 is the conservation-law dual of §4.5).
_THETA = 0.5
#: near-tie band (calibration: ties within 10 pp resolve by source rank).
_NEAR_TIE_PP = 0.10
#: union-plurality floor (rider R2) — the E-report random-tail bound,
#: the SAME constant validator I15 gates on (a plurality at or below the
#: random-collection tail is noise, above it is signal).
_UNION_FLOOR = 0.34

_SHARED_REASON_NONE = "no_anchor_lineage"
_SHARED_REASON_BAR = "sub_mint_bar_surface"
_SHARED_REASON_SHELL = "shell_lineage_only"
#: W4.2 Fix 1 — devs of a technology-instrument anchor (packages/ui,
#: packages/prisma …) lane directly under this reason; the fold ladder
#: never routes instrument code into a product capability.
_SHARED_REASON_INSTRUMENT = "technology_instrument"
#: FILELANE (2026-07-08) — a FILE-level shared-infra resident: an unowned
#: file with high import fan-in across DISTINCT product features and no
#: product surface (``wystan.pipeline_v2.file_lane``). The lane's file
#: mirror of the instrument reason (package-level); both are neutral
#: ground the validator I15 denominator excludes.
_SHARED_REASON_INFRA_FANIN = "shared_infra_fanin"
#: B22a — a flowful dev ISOLATED in a workspace unit that holds no minted
#: anchor: every target the ancestor-walk could reach sits across a
#: workspace-unit boundary, so annexing it would poison the owner map (the
#: documenso apps/docs / apps/openpage-api class). It lanes WITH its unit
#: (the unit's shell is already a lane resident) instead of riding a foreign
#: PF; counted as ``fold_walk_crossunit_laned``, never as a law breach.
_SHARED_REASON_CROSS_UNIT = "cross_unit_isolation"
#: B58 v3 — a flowful dev laned by the annexation guard whose OWN home
#: unit is a dev-artifact unit (playground/examples/demo/sample): a
#: DISTINCT lane reason so downstream layers can tell "sample-app code"
#: from the generic B22a cross-unit refusal. The keyless novu warden
#: run proved why: artifact devs laned as ``cross_unit_isolation`` kept
#: seeding journeys, which re-homed onto the nearest real PF
#: (agent-toolkit 20/59 UFs = B24 resurrection + a B31 dup-group). The
#: UF rollup keys its seeding guard on THIS reason (same vocabulary as
#: the ``dev_artifact_unit`` mint bar).
_SHARED_REASON_DEV_ARTIFACT = "dev_artifact_unit"

#: W3.1 D4 — vendor-husk floor: a hub child with NO flow evidence must
#: own at least this many LOC of code to mint (else it folds under the
#: hub core / enclosing package as a dev-child). 150 is the valsem4 H9
#: calibration bound (2026-07-07): 13-scan sweep showed zero false
#: positives at 150 — midday's 27 app-store husks (logo.tsx + config.ts,
#: 27-34 LOC) and the comp `-(integration)` 0-LOC twins die, while
#: real-code 0-flow connectors (tracecat google 286 / microsoft 557,
#: RefApp freshdesk 1,258) stay minted.
_HUB_HUSK_LOC_FLOOR = 150

#: B65-v4 Seg A — the STRONG spine source classes that own a real
#: subtree ("feature-dir/fdir/hub" in the spec). A spa-paged anchor
#: whose ``sources`` intersect this set is NOT spa-only: the authored
#: class owns the subtree and the spa page only adds a route row +
#: journey seed, so the spa-mint containment fence never restricts its
#: authored mass. Refinement layers (``interior``/``excav``) are absent
#: on purpose — a page-component family with no authored backer stays
#: fenced (no annexation).
_SPA_AUTHORED_SOURCES = frozenset({
    "fdir", "hub-vendor", "hub-core", "ws-pkg", "ws-app",
    "schema", "pypkg", "svc",
})

#: B26 — bar reason for a hub child whose segment normalizes into the
#: plumbing/stop vocabulary (cal.com ``app-store/_utils`` shape): the
#: family's shared plumbing may not mint even with flow evidence; its
#: winners take the ordinary fold_hub_parent path.
_BAR_HUB_PLUMBING_CHILD = "hub_plumbing_child"


def _hub_child_segment(anchor: SpineAnchor) -> str:
    """The child-naming terminal segment of a hub-vendor anchor's
    canonical id (``hub:packages/app-store/_utils`` → ``_utils``)."""
    cid = anchor.canonical_id or ""
    if ":" not in cid:
        return ""
    tail = cid.split(":", 1)[1].rstrip("/")
    return tail.rsplit("/", 1)[-1] if tail else ""

#: W3.2 I9 fix — the lane carve-out fires ONLY for the app-shell /
#: shared-package class the law's own ruler (validator I9) exempts.
#: Universal monorepo conventions, mirrored from the ruler verbatim
#: (rule-no-repo-specific-paths: these are ecosystem tiers, not repos):
#: a structural shell NAME, or a path-majority under shared-package
#: roots / the dev's own ``apps/<name>`` shell. The W3.1 blanket
#: ws-anchor carve-out over-fired on typebot `user` (a small, coherent,
#: flowful account dev whose ws package held only 7/20 of its files) —
#: the one core I9 regression of wave31. A flowful ws-anchor dev that
#: FAILS this test is product code and must ride the rescue ladder
#: (span-vote → walk) like every other flowful dev.
_LANE_SHELL_NAME_HINTS = (
    "backend", "frontend", "main", "mock", "scripts", "infra", "platform",
)
_LANE_SHARED_PKG_ROOTS = (
    "packages/", "libs/", "internal/", "tooling/", "config/",
)


def _lane_shell_exempt(f: "Feature") -> bool:
    """``True`` when laning flowful *f* is exempt under I9's own rules."""
    name = (getattr(f, "name", "") or "").lower()
    if any(h in name for h in _LANE_SHELL_NAME_HINTS):
        return True
    paths = [str(p) for p in (getattr(f, "paths", None) or [])]
    if not paths:
        return False
    hits = sum(
        1 for p in paths
        if any(p.startswith(r) for r in _LANE_SHARED_PKG_ROOTS)
        or p.startswith(f"apps/{name}/")
    )
    return hits >= max(1, len(paths) // 2)


def anchored_mint_enabled() -> bool:
    """Default ON; ``WYSTAN_SPINE_ANCHORED_MINT=0`` restores the old
    PF path (Stage 6.5/8 survivorship + 6.7d Call-2) for A/B."""
    return os.environ.get(ANCHORED_MINT_ENV, "1").strip().lower() not in {
        "0", "false",
    }


def mint_domain_fold_enabled() -> bool:
    """Default ON; ``WYSTAN_MINT_DOMAIN_FOLD_V2=0`` restores the
    byte-identical pre-B8c fold (a distinct-domain router stays folded into
    its plurality host instead of re-homing to its own surface PF)."""
    return os.environ.get(MINT_DOMAIN_FOLD_ENV, "1").strip().lower() not in {
        "0", "false",
    }


def fold_crossapp_guard_enabled() -> bool:
    """Default ON; ``WYSTAN_FOLD_CROSSAPP_GUARD=0`` restores the
    unguarded ancestor-walk (pre-B22a cross-app annexation) byte-identically
    for A/B."""
    return os.environ.get(FOLD_CROSSAPP_GUARD_ENV, "1").strip().lower() not in {
        "0", "false",
    }


def annexation_guard_enabled() -> bool:
    """B58 — default ON (flipped B62, KEY_SCHEMA 29): the container-anchor
    annexation guard runs (Seg A canonical-unit fencing on the
    entry/span/walk rescue rungs + Seg B dev-artifact-unit mint bar).
    ``WYSTAN_ANNEXATION_GUARD`` in ``{0, false, off}`` disables —
    byte-identical to the pre-B58 pipeline."""
    return os.environ.get(ANNEXATION_GUARD_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def sameunit_domain_cap_enabled() -> bool:
    """B58-v2 — default OFF; ``WYSTAN_SAMEUNIT_DOMAIN_CAP=1`` arms the
    same-unit domain-dir cap (Seg A drain donor class 2 + Seg B
    page-surface canonical-unit rung). OFF is byte-identical to the
    pre-B58-v2 pipeline."""
    return os.environ.get(SAMEUNIT_DOMAIN_CAP_ENV, "0").strip().lower() in {
        "1", "true", "yes", "on",
    }


def mint_empty_honest_enabled() -> bool:
    """B105 FIX-2 — default OFF; ``WYSTAN_MINT_EMPTY_HONEST=1`` arms the
    honest ``applied`` stamp on a ZERO-mint product-app unit (see
    :data:`MINT_EMPTY_HONEST_ENV`). OFF (unset / anything but a truthy
    token) is byte-identical to the pre-B105 pipeline — the branch is never
    entered and no telemetry key is added."""
    return os.environ.get(MINT_EMPTY_HONEST_ENV, "0").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _scan_unit_repo_class(ctx: Any) -> str | None:
    """The Stage 0.7 ``repo_class`` for this scan unit, re-derived from
    ``ctx`` when the caller did not thread the intake verdict.

    Stage 0.7 is a PURE, deterministic, LLM-free function of ``ctx``, so the
    re-derivation equals the intake verdict — which is what keeps the
    ``wystan replay`` path (whose ``06-stage-anchored_mint-input`` capture
    carries no verdict) at parity with the live site. Never raises: an
    un-classifiable ctx returns ``None`` and the caller keeps the status-quo
    stamp (the conservative direction — a fix that cannot prove the unit is
    a product app does not change the unit's behaviour).
    """
    try:
        from wystan.pipeline_v2.stage_0_7_repo_class import (
            classify_repo_class_per_unit,
        )
        return classify_repo_class_per_unit(ctx).repo_class
    except Exception:  # noqa: BLE001 — classification must never fail a scan
        return None


def homing_hygiene_enabled() -> bool:
    """B69-v2 — default **ON** since the 2026-07-16 horizon-1 flip
    (KEY_SCHEMA 30; keyed proof papermark + cal green). Makes the mint
    export its anchor registry for the Stage 6.99b post-UF rehome rail
    (a tele side-channel the caller pops; never serialized).
    ``WYSTAN_HOMING_HYGIENE=0`` ⇒ the key is never attached ⇒
    byte-identical (kill-switch; unset ≡ explicit ``1``). (Deliberate
    local duplicate of
    :func:`wystan.pipeline_v2.naming_contract.homing_hygiene_enabled`
    — the mint stays import-light, banked-branch precedent; both read the
    same env so their defaults flip in lock-step.)"""
    return os.environ.get(HOMING_HYGIENE_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def fold_evidence_weight_enabled() -> bool:
    """B78 Seg A — default **ON** since the 2026-07-22 flip-pack №4
    (KEY_SCHEMA 36; keyed proof RefApp CF-final green — media-library
    vacuum 10→1 / cases →2, walk-folds evidence-void 35→0, D 6/6 exhibits,
    protected live, twenty/langfuse 0-collateral). Unset ≡ explicit ``1``:
    the walk-evidence gate arms (an ancestor-walk fold is valid only when
    the target holds a behavioral claim on the dev's flow entry files;
    void folds re-dispose by entry evidence per rulings R1-R3). Explicit
    ``=0``/``false`` ⇒ byte-identical to the ungated walk (kill-switch
    forever)."""
    return os.environ.get(FOLD_EVIDENCE_WEIGHT_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def fold_evidence_demote_enabled() -> bool:
    """B85 — default **ON** since world 37 (KEY_SCHEMA 37; the
    B22a-resurrection fence). Unset ≡ explicit ``1``: the post-fold
    domain-foreignness demote runs (armed ONLY when
    :func:`fold_evidence_weight_enabled` is also on — the fence lives inside
    the EVW world). Explicit ``0``/``false``/``off``/``no`` ⇒ the EVW-only
    (pre-demote) world, byte-identical (inverted kill-switch forever)."""
    return os.environ.get(FOLD_EVIDENCE_DEMOTE_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def product_right_gate_enabled() -> bool:
    """B87 rung-2 — default **ON** since the 2026-07-23 flip-pack №6 flip
    (KEY_SCHEMA 39; keyed keyless SAFETY B87 + composition mid_A4 class-A
    kills named + re-home confirmed). Unset now arms the product-right gate
    (probe-canon E2 form: bullet 1 narrow standalone bar + bullet 2 fdir/ws
    page fiat closure; the bullet-3 token journey re-home rides its own stage
    6.9965 twin flag-check). Explicit ``0``/``false``/``off``/``no`` is the
    kill-switch forever (byte-identical to the pre-B87 pipeline). The pre-flip
    truthy set ``{"1","true","yes","on"}`` is preserved LITERALLY — only the
    ``os.environ.get`` default moved ``"0"`` -> ``"1"`` (unset ≡ explicit
    ``"1"``)."""
    return os.environ.get(PRODUCT_RIGHT_GATE_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


#: fixb134 M4a — the collision-qualifier self-restatement guard, shared by
#: the anchored mint, lane_excavation and transport_handoff. Default **ON**
#: since the 2026-08-09 pack-№36 flip (KEY_SCHEMA 69; warden №40 GO).
#: Unset ≡ explicit ``1``; explicit ``0``/``false`` keeps every minted slug,
#: display and telemetry byte-identical (kill-switch forever). The truthy
#: set is preserved LITERALLY — only the default moved ``"0"`` -> ``"1"``.
MINT_QUALIFIER_NO_SELF_ENV = "WYSTAN_MINT_QUALIFIER_NO_SELF"


def _mint_qualifier_no_self_enabled() -> bool:
    """fixb134 M4a gate — see :data:`MINT_QUALIFIER_NO_SELF_ENV`."""
    return os.environ.get(
        MINT_QUALIFIER_NO_SELF_ENV, "1"
    ).strip().lower() in {"1", "true"}


def _r5_canonical_compose(display: str) -> str:
    """R5-4 (``WYSTAN_NAMING_WAVE_R5``, default ON since the 2026-07-21 pack-2 flip) — compose site 3/3.

    The anchored-mint ``"<display> (<qualifier>)"`` joint runs through the
    ONE compose canonicalizer (whitespace residue, internal parens, double
    joints, scaffold-verb inversion ``Edit (Monitors)`` -> ``Monitors —
    Edit``). The slug still derives from the (canonical) display verbatim,
    so canonical_slug parity holds. Flag OFF ⇒ passthrough ⇒ byte-identical.
    Imports are lazy — this stage stays import-light and the wave check
    costs one cached env read per call."""
    from wystan.pipeline_v2.naming_contract import (
        load_naming_vocab,
        naming_wave_r5_enabled,
    )
    from wystan.pipeline_v2.naming_wave_r5 import (
        canonicalize_compose,
        r5_vocab_sets,
    )
    if not naming_wave_r5_enabled():
        return display
    return canonicalize_compose(display, r5_vocab_sets(load_naming_vocab()))[0]


#: fixb125 addendum (lead ruling 2026-08-06) — the SURFACE TOKEN of a
#: command-line product feature. Precedent: the ``-page`` surface suffix
#: (``_SURFACE_PAGE_SUFFIX``) — one structural word naming the surface
#: class, never a dictionary.
_CLI_SURFACE_TOKEN = "CLI"


def cli_pf_display(bin_name: str) -> str:
    """Display label of a CLI product feature: ``"<declared bin> CLI"``.

    PRODUCT-RIGHT (lead ruling): a PF name must read to a PM. The bare
    declared binary does not — ``ollama`` on the Ollama board is a
    repo-echo, ``lh`` is opaque — while ``ollama CLI`` / ``lh CLI`` do.
    The single exception is a binary literally named ``cli``: the class
    IS the name there, so the label is just ``CLI`` (never ``cli CLI``).

    The author's token survives as the PF ``name``/slug — only the
    DISPLAY composes. One rule, no vocabulary, no per-repo branch.
    """
    raw = (bin_name or "").strip()
    if not raw:
        return _CLI_SURFACE_TOKEN
    if normalize_anchor_key(raw) == _CLI_SURFACE_TOKEN.lower():
        return _CLI_SURFACE_TOKEN
    return "%s %s" % (raw, _CLI_SURFACE_TOKEN)


def _cli_display(bin_name: str) -> str:
    return cli_pf_display(bin_name)


def _workspace_unit_roots(ctx: Any) -> tuple[str, ...]:
    """Workspace-unit roots (an app or a workspace package), derived from
    the repo's OWN manifests — never from directory-name vocabulary.

    Primary: ``ctx.workspaces`` (Stage-0 ``detect_workspace`` output —
    pnpm-workspace.yaml globs, package.json "workspaces", turbo / nx /
    lerna / cargo / go). Fallback for non-workspace repos: a TOP-LEVEL dir
    carrying its own unit manifest (the spine-anchor
    ``unit_manifest_files`` convention — the RefApp backend/ + frontend/
    class). Sorted longest-first so nested units resolve to the most
    specific root. Empty on single-unit repos → the guard is inert.
    """
    roots: set[str] = set()
    for w in (getattr(ctx, "workspaces", None) or []):
        p = str(getattr(w, "path", "") or "").replace("\\", "/").strip("/")
        if p:
            roots.add(p)
    if not roots:
        manifests = set(load_spine_vocab().get("unit_manifest_files") or [])
        for t in (getattr(ctx, "tracked_files", None) or []):
            segs = str(t).split("/")
            if len(segs) == 2 and segs[1] in manifests:
                roots.add(segs[0])
    return tuple(sorted(roots, key=lambda r: (-len(r), r)))


def _unit_of(path: str, unit_roots: tuple[str, ...]) -> str | None:
    """The most specific workspace unit holding *path* (longest-prefix
    match over ``unit_roots``), or ``None`` outside every unit."""
    for r in unit_roots:
        if path == r or path.startswith(r + "/"):
            return r
    return None


# ── B85 — post-fold domain-foreignness demote (the B22a-resurrection fence) ─
# Pure, testable classification helpers. The DOMAIN grain is the workspace
# unit, else the TOP-LEVEL dir (RefApp backend/ + frontend/ are units via the
# unit-manifest fallback; a repo-root file's fallback "domain" is itself — the
# ruling's spurious singleton). Everything reads STATIC anchor evidence only
# (no post-fold mass — the circularity guard the probe pinned).


def _demote_domain_of(path: str, unit_roots: tuple[str, ...]) -> str:
    """The engine's domain grain of *path*: its workspace unit, else its
    top-level dir (mirror of ``_artifact_scope``'s ``u if u is not None else
    split('/', 1)[0]``)."""
    u = _unit_of(path, unit_roots)
    return u if u is not None else path.split("/", 1)[0]


def _demote_anchor_inside(path: str, anchor: SpineAnchor) -> bool:
    """B22a static containment — *path* is inside the anchor's OWN static
    evidence (exact files ∪ api-route ∪ page-route ∪ dir prefixes). This is
    the probe's ``inside`` (excludes are NOT consulted — containment here is
    "does the anchor's identity evidence claim this file", not the mint's
    membership ``matches``)."""
    if (path in anchor.files or path in anchor.api_route_files
            or path in anchor.page_route_files):
        return True
    return any(path == pre or path.startswith(pre + "/")
               for pre in anchor.prefixes)


def _demote_is_foreign(
    path: str, canonical_domain: str | None, unit_roots: tuple[str, ...],
) -> bool:
    """``True`` when *path* sits on the FAR side of the domain/unit edge from
    the anchor's canonical domain. RULING side-effect-3: a repo-root file
    outside ALL units (no ``/`` AND ``_unit_of`` None — its fallback domain is
    the spurious per-file singleton) is NEVER foreign (``outside-unit does not
    veto``). ``canonical_domain is None`` ⇒ never foreign (gate inert)."""
    if canonical_domain is None:
        return False
    if _unit_of(path, unit_roots) is None and "/" not in path:
        return False
    return _demote_domain_of(path, unit_roots) != canonical_domain


def _demote_canonical_domain(
    anchor: SpineAnchor, unit_roots: tuple[str, ...],
) -> tuple[str | None, str]:
    """The anchor's STATIC canonical domain ``(domain, rung)`` for the B85
    fence — the probe's four-rung ladder (distinct from the B58
    ``_canonical_anchor_unit``: R2 tests the ENTRY/api surface ALONE and
    BEFORE the page surface, the P4 tune, and the grain is unit-OR-top-dir):

      R1  the anchor-id-embedded path unit (id tail with a ``/``);
      R2  unanimity over the api-route (ENTRY) surface alone;
      R3  unanimity over the page-route surface alone;
      R4  unanimity over the whole static evidence set;
      None ⇒ genuinely cross-unit (the gate is inert for this anchor).
    """
    cid = anchor.canonical_id
    tail = cid.split(":", 1)[1] if ":" in cid else cid
    if "/" in tail:
        u = _unit_of(tail, unit_roots)
        if u is not None:
            return u, "R1-idpath"
    api_u = {_demote_domain_of(p, unit_roots) for p in anchor.api_route_files}
    if len(api_u) == 1:
        return next(iter(api_u)), "R2-entry"
    pg_u = {_demote_domain_of(p, unit_roots) for p in anchor.page_route_files}
    if len(pg_u) == 1:
        return next(iter(pg_u)), "R3-page"
    ev = (list(anchor.files) + list(anchor.api_route_files)
          + list(anchor.page_route_files) + list(anchor.prefixes))
    ev_u = {_demote_domain_of(str(p), unit_roots) for p in ev}
    if len(ev_u) == 1:
        return next(iter(ev_u)), "R4-evidence"
    return None, "none-crossunit"


#: B85 structured provenance for a demote carve dev (the flowless lane
#: resident holding a mixed dev's shed foreign mass). Distinct from the B53
#: drain marker so no downstream husk/organic-mass predicate confuses them.
_DEMOTE_MARKER = "b85_fold_demote"
_DEMOTE_LANE_ANCHOR = f"fold:{_DEMOTE_MARKER}->{_SHARED_REASON_CROSS_UNIT}"


def _demote_strip_dev(dev: Any, foreign: frozenset[str]) -> None:
    """Drop *foreign* paths from a MIXED donor dev's ``member_files`` +
    ``paths`` (its Da-side files stay; flows are untouched — they ride the
    surviving dev). Foreign entries are explicit leaf files by construction,
    so an exact-path removal is a no-contest surgery (mirror of
    ``ws_blob_domain_drain._shrink_pf`` at dev grain)."""
    mfs = getattr(dev, "member_files", None) or []
    kept = [
        m for m in mfs
        if ((m.get("path") if isinstance(m, dict)
             else getattr(m, "path", None)) not in foreign)
    ]
    dev.member_files = kept
    dev.paths = [
        p for p in (getattr(dev, "paths", None) or []) if str(p) not in foreign
    ]


def _carve_content_slug(files: list[str], donor: str = "") -> str:
    """Deterministic CONTENT name for a demote carve dev (B86) — the leaf
    segment of the carved set's DEEPEST COMMON DIRECTORY, slugified with the
    one normalizer. When the set scatters across top-level dirs (no shared
    parent chain) the DOMINANT dir-family instead — the immediate parent
    directory owning the most files, ties broken by the lexicographically
    smallest parent path (a pure content signal, NOT an ordinal shard index).

    B86 it2 (ruling opt-b): when the leaf slug is a BARE STRUCTURAL
    CONTAINER — judged by the engine's own name-based package-node-blob
    predicate (``is_container_name``, the structural_audit detector; single
    source of truth, not a copied list) — the display falls back to the FULL
    dir-path slug (``frontend/src`` → ``frontend-src``), which escapes the
    fingerprint. If even that is container-tagged (a depth-1 container dir
    like ``src/``), the donor-lineage prefix (``{donor}-{path}``) breaks the
    tie — always marker-free. Empty / root-only sets fall back to
    ``"carve"``. The caller applies the -2/-3 collision convention (Fix D).
    Order-independent: same file SET ⇒ same slug."""
    from wystan.pipeline_v2.emission_integrity import (
        canonical_slug,
        is_container_name,
    )

    parents = [
        norm.rsplit("/", 1)[0]
        for norm in (f.replace("\\", "/") for f in files if f)
        if "/" in norm
    ]
    dir_path = ""
    if parents:
        seg_lists = [p.split("/") for p in parents]
        first = seg_lists[0]
        k = len(first)
        for other in seg_lists[1:]:
            j = 0
            while j < min(k, len(other)) and other[j] == first[j]:
                j += 1
            k = j
        if k >= 1:
            dir_path = "/".join(first[:k])  # deepest common directory
        else:
            # scatter — dominant dir-family (most files; alpha-min on tie).
            counts = Counter(parents)
            dir_path = min(counts, key=lambda p: (-counts[p], p))
    if not dir_path:
        return "carve"
    segs = dir_path.split("/")
    top = segs[0]
    leaf_slug = canonical_slug(segs[-1])
    if leaf_slug and not is_container_name(leaf_slug, top):
        return leaf_slug
    # container leaf → full common-dir path slug (canonical_slug collapses
    # '/' runs to '-': 'frontend/src' → 'frontend-src').
    path_slug = canonical_slug(dir_path)
    if path_slug and not is_container_name(path_slug, top):
        return path_slug
    # depth-1 container dir — donor-lineage prefix (still marker-free).
    return canonical_slug(f"{donor}-{path_slug}") or "carve"


def _make_demote_lane_dev(
    shell: Any, files: list[str], used_names: set[str],
) -> Any:
    """A flowless CROSS-UNIT lane resident carved from a mixed donor's shed
    foreign mass: ``product_feature_id=None`` + ``shared_reason=
    cross_unit_isolation`` (the B22a lane), an explicit primary file list, a
    content-addressed uuid + ``split_from`` lineage, no flows. Mirrors
    ``ws_blob_domain_drain._make_drain_dev`` but lands in the lane, not a PF.
    Supports pydantic ``Feature`` and lightweight stubs.

    B86: the display ``name`` derives from the carved set's CONTENT (see
    ``_carve_content_slug``) — never from the internal ``_DEMOTE_MARKER`` —
    and the marker relocates to the structured, non-display
    ``carve_provenance`` field so forensics/warden enumerate carve-devs by a
    query, not by grepping the display name. The ``description`` is human
    prose (display surface — ruling); ``anchor_id`` / member ``evidence``
    keep the structured marker."""
    base = _carve_content_slug(files, donor=str(getattr(shell, "name", "") or ""))
    name = base
    n = 2
    while name in used_names:
        name = f"{base}-{n}"  # Fix-D -2/-3 collision convention
        n += 1
    uuid = hashlib.sha256(
        f"{_DEMOTE_MARKER}|{shell.name}|{'|'.join(sorted(files))}".encode(
            "utf-8")).hexdigest()[:32]
    evidence = f"{_DEMOTE_MARKER}: demoted foreign mass to the cross-unit lane"

    if hasattr(shell, "model_copy"):
        from wystan.models.types import MemberFile
        members = [
            MemberFile(path=p, role="anchor", confidence=1.0, primary=True,
                       evidence=evidence)
            for p in sorted(files)
        ]
        return shell.model_copy(deep=True, update={
            "name": name, "display_name": name,
            "paths": sorted(files), "member_files": members,
            "product_feature_id": None, "shared_reason": _SHARED_REASON_CROSS_UNIT,
            "description": "Carved to the cross-unit lane "
                           "(fold-evidence demote).",
            "carve_provenance": _DEMOTE_MARKER,
            "uuid": uuid, "split_from": getattr(shell, "uuid", None),
            "anchor_id": _DEMOTE_LANE_ANCHOR,
            "previous_names": [], "merged_from": [],
            "flows": [], "shared_participants": [], "shared_attributions": [],
            "symbol_attributions": [], "hotspot_files": [], "participants": [],
            "history": None,
        })

    from types import SimpleNamespace
    ch: Any = SimpleNamespace()
    ch.layer = "developer"
    ch.name = name
    ch.display_name = name
    ch.uuid = uuid
    ch.paths = sorted(files)
    ch.member_files = [
        {"path": p, "role": "anchor", "confidence": 1.0, "primary": True,
         "evidence": evidence}
        for p in sorted(files)
    ]
    ch.flows = []
    ch.product_feature_id = None
    ch.anchor_id = _DEMOTE_LANE_ANCHOR
    ch.shared_reason = _SHARED_REASON_CROSS_UNIT
    ch.split_from = getattr(shell, "uuid", None)
    ch.carve_provenance = _DEMOTE_MARKER
    return ch


def _artifact_unit_anchor(
    a: SpineAnchor,
    unit_roots: tuple[str, ...],
    tokens: frozenset[str],
) -> bool:
    """B58 Seg B — ``True`` when *a* is a dev-artifact-unit anchor: its
    home is a workspace unit whose ROOT path carries a segment from
    ``unit_root_artifact_tokens`` (novu ``playground/nextjs`` — the
    repo's own pnpm-workspace.yaml declares the playground apps). The
    token test runs at UNIT-ROOT grain only — for paths outside every
    unit, only the TOP-LEVEL dir counts — so a product page merely NAMED
    ``playground`` (cal.com admin page, a route leaf inside apps/web)
    can never fire.

    Two rungs, canonical-first (v2 — the novu kill-switch census caught
    the v1 hole: the ``notifications`` playground anchor escaped the
    evidence rule because a same-KEY merge unioned real
    ``libs/notifications`` evidence into it, then the surviving tile
    absorbed all 16 barred siblings, 611→17,631 LOC):

    1. the anchor-id-embedded path (``route:playground/nextjs/…``) —
       the anchor's name-giving identity; merged foreign evidence can
       never rescue an artifact-anchored tile;
    2. no id path ⇒ all-or-nothing over the evidence: one non-artifact
       evidence unit vetoes the bar (conservative — never bar a mixed
       surface on evidence alone)."""
    if not tokens:
        return False

    def _artifact_scope(path: str) -> bool:
        u = _unit_of(path, unit_roots)
        scope = u if u is not None else path.split("/", 1)[0]
        return any(seg in tokens for seg in scope.lower().split("/"))

    cid = a.canonical_id
    tail = cid.split(":", 1)[1] if ":" in cid else cid
    if "/" in tail:
        return _artifact_scope(tail)
    evs = list(a.prefixes) + sorted(a.files)
    if not evs:
        return False
    return all(_artifact_scope(str(ev)) for ev in evs)


#: The surface token stripped to recover a route anchor's DOMAIN family. Only
#: ``-page`` appears as a surface-PF suffix in practice (``webhooks-page``,
#: ``settings-page``); the api-side domain anchors (``webhook``, ``setting``)
#: carry no surface token, so a single suffix is sufficient and scale-invariant.
_SURFACE_PAGE_SUFFIX = "-page"


def _domain_family(key: str) -> str:
    """Route-family DOMAIN of an anchor key: strip a trailing ``-page``
    surface token, then singularise the remaining stem with the SAME guarded
    house singularizer every anchor key already uses (``normalize_anchor_key``
    only singularises the LAST token, so ``webhooks-page`` keeps ``webhooks``
    plural — this collapses it).

    ``webhooks-page`` → ``webhook``; ``webhook`` → ``webhook``;
    ``detection`` → ``detection``; ``settings-page`` → ``setting``.
    A degenerate/empty stem falls back to the input key unchanged.
    """
    stem = key
    if stem.endswith(_SURFACE_PAGE_SUFFIX) and len(stem) > len(_SURFACE_PAGE_SUFFIX):
        stem = stem[: -len(_SURFACE_PAGE_SUFFIX)]
    return normalize_anchor_key(stem) or key


def _mint_domain_fold_rebinds(
    assignment: dict[str, tuple[str, str]],
    winner_by_dev: dict[str, "SpineAnchor | None"],
    anchor_by_id: dict[str, SpineAnchor],
    dev_by_name: dict[str, "Feature"],
) -> list[tuple[str, str, str]]:
    """B8c rail — re-home flowful devs FOLDED into a distinct-domain host
    onto their own EXISTING ``<domain>-page`` surface PF.

    Returns a deterministically-ordered list of
    ``(dev_name, surface_cid, provenance)`` rebinds; the caller applies them.
    Pure (no mutation, no I/O). The two structural rails, no magic counts:

    * **distinct-from-host** — the dev's route-family domain differs from the
      host PF's own route domain (a same-domain router — a ``detection`` router
      folding into ``detections`` — is NOT distinct → stays folded).
    * **existing surface PF** — a genuine ``<domain>-page`` page-route anchor
      that ALREADY receives ≥1 dev in *assignment*. Because the target already
      mints, PF count cannot rise and no product-judgment "should this domain
      be a PF?" call is made — the engine already decided by minting the page.
      A surface-less domain (admin/compliance/slack: no page PF) never
      qualifies → stays folded.
    """
    # Index existing page-surface PFs by domain family. A candidate is a route
    # anchor whose cid ends ``-page``, that carries ≥1 page_route_file (a real
    # frontend surface, not an api-only route), AND that already receives a dev
    # (so it is an EXISTING PF — the rail never mints). Deterministic: iterate
    # sorted cids and keep the alpha-min on the (rare) same-family collision.
    existing_targets = {cid for cid, _prov in assignment.values()}
    surface_by_family: dict[str, str] = {}
    for cid in sorted(existing_targets):
        a = anchor_by_id.get(cid)
        if a is None or a.source != "route":
            continue
        if not a.canonical_id.endswith(_SURFACE_PAGE_SUFFIX):
            continue
        if not a.page_route_files:
            continue
        surface_by_family.setdefault(_domain_family(a.key), cid)
    if not surface_by_family:
        return []

    rebinds: list[tuple[str, str, str]] = []
    for name in sorted(assignment):
        host_cid, prov = assignment[name]
        if not prov.startswith("fold:"):
            continue  # only re-home FOLDED devs — lineage / mint stay put
        f = dev_by_name.get(name)
        if f is None or not getattr(f, "flows", None):
            continue  # flowful devs only (the fold LAW's own population)
        w = winner_by_dev.get(name)
        if w is None or not w.canonical_id.startswith("route:"):
            continue  # route-family domain only
        dev_fam = _domain_family(w.key)
        host_a = anchor_by_id.get(host_cid)
        host_fam = (
            _domain_family(host_a.key)
            if host_a is not None and host_a.canonical_id.startswith("route:")
            else None
        )
        if host_fam == dev_fam:
            continue  # same domain → still folds (anti-case preserved)
        surf_cid = surface_by_family.get(dev_fam)
        if surf_cid is None or surf_cid == host_cid:
            continue  # surface-less, or already home
        rebinds.append((name, surf_cid, f"fold:surface->route:{dev_fam}"))
    return rebinds


# ── Per-dev classification ───────────────────────────────────────────────


def _classify_dev(
    owned: list[str],
    anchors: list[SpineAnchor],
) -> tuple[SpineAnchor | None, float, str, list[tuple[SpineAnchor, float]]]:
    """One dev's lineage: ``(winner, share, verdict, plurality_top)``.

    verdict ∈ {"unique", "near_tie", "none"}. ``plurality_top`` is the
    ranked sub-θ candidate list (capability-grain fold evidence).
    """
    n = len(owned)
    if n == 0:
        return None, 0.0, "none", []
    scored: list[tuple[SpineAnchor, float, frozenset[str]]] = []
    for a in anchors:
        matched = a.matched_set(owned)
        if matched:
            scored.append((a, len(matched) / n, matched))
    if not scored:
        return None, 0.0, "none", []
    majority = [(a, s, m) for a, s, m in scored if s >= _THETA]
    if not majority:
        top = sorted(scored, key=lambda t: (-t[1], t[0].rank, t[0].canonical_id))
        return None, 0.0, "none", [(a, s) for a, s, _ in top[:5]]

    # SPECIFICITY REDUCTION — drop anchors whose matched set strictly
    # contains another majority anchor's matched set; identical matched
    # sets merge. Identical-set preference (fastapi-template + supabase
    # smokes, 2026-07-06): source rank, then the MOST SPECIFIC subtree
    # (longest matching dir prefix — the mega-segment carve:
    # ``project/[ref]/integrations`` beats ``project``), then the key
    # that names the matched FILE itself (a central-router file carries
    # several URL keys — login.py = /login + /password-recovery — and
    # the stem names the surface), then the stable id.
    def _ident_key(a: SpineAnchor, m: frozenset[str]) -> tuple:
        from wystan.pipeline_v2.spine_anchors import (
            normalize_anchor_key as _nk,
        )
        longest_prefix = 0
        for p in m:
            for pre in a.prefixes:
                if p.startswith(pre + "/") or p == pre:
                    longest_prefix = max(longest_prefix, len(pre))
        stem_match = 0
        if len(m) == 1:
            f = next(iter(m))
            stem = f.rsplit("/", 1)[-1]
            stem = stem[: stem.rfind(".")] if "." in stem else stem
            stem_match = 0 if _nk(stem) == a.key else 1
        return (a.rank, -longest_prefix, stem_match, a.canonical_id)

    reduced: list[tuple[SpineAnchor, float, frozenset[str]]] = []
    for a, s, m in majority:
        dominated = False
        for b, _sb, mb in majority:
            if a is b:
                continue
            # Strict matched-subset AND structural nesting (W2b.1 fix a):
            # b is "more specific" only when its own subtree nests inside
            # a's. Bare set-containment inverted on cross-app MERGED
            # anchors — openstatus `login`: ws:apps/dashboard matched 6 of
            # the 10 login files (a strict subset of route:login's 10) and
            # the shell dropped the route anchor; the shell's subtree is
            # NOT inside the route subtree, so it may not dominate it.
            if mb < m and b.subtree_inside(a):
                dominated = True
                break
            if mb == m and _ident_key(b, mb) < _ident_key(a, m):
                dominated = True
                break
        if not dominated:
            reduced.append((a, s, m))
    reduced.sort(key=lambda t: (-t[1], t[0].rank, t[0].canonical_id))
    winner, share, _ = reduced[0]
    if len(reduced) == 1 or share - reduced[1][1] > _NEAR_TIE_PP:
        return winner, share, "unique", []
    # Near-tie: nav confirmation first (ranking confirmer), then the
    # fixed source rank, then the stable id. B1 (twins-forensics): the nav
    # vote counts ONLY for a page/view-corroborated anchor — a bare
    # nav-key hit on a backend route-segment (RefApp route:framework vs
    # route:compliance over compliance.py) never wins the tie.
    tied = [(a, s) for a, s, _ in reduced if share - s <= _NEAR_TIE_PP]
    tied.sort(key=lambda t: (
        not (t[0].nav_confirmed and _nav_vote_corroborated(t[0], owned)),
        t[0].rank, t[0].canonical_id))
    return tied[0][0], tied[0][1], "near_tie", []


# ── Mint bar ─────────────────────────────────────────────────────────────


def _flow_evidence_index(
    developer_features: list["Feature"],
) -> tuple[dict[str, list[str]], set[str]]:
    """``entry-file → [flow names]`` over EVERY dev's flows (a hub
    child's flow evidence often lives on the parent dev — RefApp erp) +
    the set of devs' names having ≥1 flow."""
    entries: dict[str, list[str]] = defaultdict(list)
    flowful_devs: set[str] = set()
    for f in developer_features:
        flows = getattr(f, "flows", None) or []
        if flows:
            flowful_devs.add(getattr(f, "name", "") or "")
        for fl in flows:
            ep = getattr(fl, "entry_point_file", None)
            if ep:
                entries[str(ep)].append(getattr(fl, "name", "") or "")
    return entries, flowful_devs


def _anchor_flow_evidence(
    anchor: SpineAnchor,
    winners: list["Feature"],
    flow_entries: dict[str, list[str]],
) -> bool:
    """≥1 flow lands in the anchor's subtree: a winner dev has flows, or
    ANY flow's entry file matches the subtree (parent-held flows)."""
    for dev in winners:
        if getattr(dev, "flows", None):
            return True
    for ep in flow_entries:
        if anchor.matches(ep):
            return True
    return False


def _is_code(path: str, code_exts: tuple[str, ...]) -> bool:
    return path.lower().endswith(code_exts)


# ── B1 invariant (2026-07-31 twins-forensics, RefApp phantom) ──────────────
#
# nav evidence (``nav_confirmed``) may LIFT the api_only_surface bar or
# VOTE in a near-tie ONLY when the anchor carries its OWN page/flow
# corroboration — a real page surface, a flow landing in its subtree, or
# an authored view component. A bare nav-key hit on a BACKEND
# route-segment anchor (RefApp ``route:mitre`` / ``route:framework`` — 0
# pages, 0 own flows) is ranking evidence at most, never a mint license:
# "Nav labels CONFIRM anchors, never create subtrees"
# (spine_anchors:1404). Keyed KS44→KS47 exhibit: nav-evidence growth on
# backend anchors flipped three gates at once — the api_only_surface bar
# lifted on route:mitre/route:article, route:framework won the compliance.py
# near-tie, and phantom PFs (frameworks/mitre/api) were born.


def _nav_lift_corroborated(
    anchor: SpineAnchor,
    winners: list["Feature"],
    flow_entries: dict[str, list[str]],
) -> bool:
    """Full-context B1 predicate (mint-bar seam): page files ∨ flow
    evidence in the anchor's subtree ∨ authored view component."""
    return (
        bool(anchor.page_route_files)
        or _anchor_flow_evidence(anchor, winners, flow_entries)
        or _has_authored_view_component(anchor, winners)
    )


def _nav_vote_corroborated(anchor: SpineAnchor, owned: list[str]) -> bool:
    """Anchor-intrinsic B1 predicate (near-tie seam — no flow index in
    scope there): page files ∨ authored view component among the anchor's
    own/matched files. A backend .py route-segment anchor has neither."""
    if anchor.page_route_files:
        return True
    evidence: set[str] = set(anchor.files) | anchor.matched_set(owned)
    return any(p.endswith(_VIEW_COMPONENT_EXTS) for p in evidence)


#: Authored client view-component file extensions (B87 rung-2 bullet 2).
#: A file of this kind IS a page surface even when the route extractor
#: missed the wiring (SPA / Vue extraction gap) — used to keep a real UI
#: feature-dir from the fdir-fiat closure. Not a name dictionary: the
#: signal is the authored view-component file TYPE.
_VIEW_COMPONENT_EXTS = (".tsx", ".jsx", ".vue", ".svelte", ".astro")


def _has_authored_view_component(
    anchor: SpineAnchor, winners: list["Feature"],
) -> bool:
    """B87 rung-2 bullet 2 — the anchor's subtree owns ≥1 authored client
    view component. Such a feature-dir declares a page surface even when
    the route extractor produced no ``page_route_files`` (the RefApp
    feature-studio SPA gap: 13 authored components, zero route-wired
    pages). The canon forbids deleting a real feature — this keeps UI
    feature-dirs product while pure back-end infra containers
    (Captcha/Di/Common, codemods, mixins, enterprise service packages),
    which own no view components, stay barred."""
    evidence: set[str] = set(anchor.files)
    for w in winners:
        evidence.update(anchor.matched_set(owned_paths_of(w)))
    return any(p.endswith(_VIEW_COMPONENT_EXTS) for p in evidence)


def _files_loc(
    repo_root: Path,
    rel_paths: list[str],
    cache: dict[str, int],
) -> int:
    """Summed LOC of *rel_paths* per the engine's Stage-6.97 counting
    convention (tests / generated / binary / missing count 0). Cached
    per path; called only for flowless hub children (a handful of small
    files per repo), so the IO is bounded."""
    from wystan.pipeline_v2.stage_6_97_feature_loc import count_file_loc

    total = 0
    for rel in rel_paths:
        if rel not in cache:
            cache[rel] = count_file_loc(repo_root / rel, rel)
        total += cache[rel]
    return total


def _anchor_in_instrument_dirs(
    anchor: SpineAnchor,
    instrument_dirs: frozenset[str],
) -> bool:
    """Every membership unit of *anchor* (prefixes; files when it has no
    prefixes) sits inside a technology-instrument dir. Page evidence or a
    nav mention keeps the anchor product (S3 belt at anchor grain)."""
    if not instrument_dirs:
        return False
    if anchor.page_route_files or anchor.nav_confirmed:
        return False

    def _inside(p: str) -> bool:
        return any(p == d or p.startswith(d + "/") for d in instrument_dirs)

    units: list[str] = list(anchor.prefixes or ())
    if not units:
        units = sorted(anchor.files)
    return bool(units) and all(_inside(u) for u in units)


def _mint_bar(
    anchor: SpineAnchor,
    winners: list["Feature"],
    flow_entries: dict[str, list[str]],
    repo_has_pages: bool,
    code_exts: tuple[str, ...],
    repo_root: Path,
    loc_cache: dict[str, int],
    instrument_dirs: frozenset[str] = frozenset(),
    plumbing_keys: frozenset[str] = frozenset(),
    product_right_gate: bool = False,
    sacred_dirs: frozenset[str] = frozenset(),
) -> str | None:
    """``None`` when the anchor may mint, else the bar reason."""
    if not winners:
        return "no_winning_devs"
    if anchor.shell:
        return "shell"
    if anchor.barred:
        return anchor.barred  # single_letter | version_dir
    # W4.2 Fix 1 — technology instruments (dev tooling by mechanism, not
    # dictionary: manifest grounding / import asymmetry / no product
    # surfaces, >=2 signals in technology_instruments.py) never mint.
    if _anchor_in_instrument_dirs(anchor, instrument_dirs):
        return "technology_instrument"
    if anchor.sources == frozenset({"svc"}):
        return "service_dir_only"
    if anchor.source == "hub-vendor":
        # B26 backstop — a hub child whose segment NORMALIZES into the
        # plumbing/stop vocabulary (and names no vendor) is the family's
        # shared plumbing: it may not mint EVEN WITH flow evidence (a
        # helper dir is always somebody's call-chain entry, so the flow
        # bar can never stop this class). Its winners take the existing
        # fold_hub_parent path to the enclosing package / hub core. The
        # spine filter (Fix A) already blocks the dir-per-vendor shape;
        # this rung covers every other path an anchor can reach the bar
        # (file-per-vendor token sets, cross-family merges).
        if (plumbing_keys and hub_plumbing_child_enabled()
                and hub_child_is_plumbing(
                    _hub_child_segment(anchor), plumbing_keys)):
            return _BAR_HUB_PLUMBING_CHILD
        if _anchor_flow_evidence(anchor, winners, flow_entries):
            return None
        if anchor.hub_parent_generic:
            # Generic-container family (backend/routers, backend/models):
            # a vendor-named file with NO flow is not an integration PF.
            return "hub_child_no_flow"
        child_files: set[str] = set(anchor.files)
        for w in winners:
            child_files.update(anchor.matched_set(owned_paths_of(w)))
        code_files = [p for p in sorted(child_files)
                      if _is_code(p, code_exts)]
        if not code_files:
            return "hub_stub_child"  # single static file class (FDW wrappers)
        # W3.1 D4 (fb3 dossier, valsem4 H9): a flowless child needs a
        # BODY, not just a code file — the old any-code prong let
        # logo.tsx + config.ts marketplace husks mint (midday app-store
        # ×27; comp `aws` + `aws-(integration)` 0-LOC dup twins). Under
        # the floor the husk folds under its hub core / enclosing
        # package as a dev-child; the same-vendor dup-pair class dies
        # with it (the husk twin never mints, so no pair exists).
        if _files_loc(repo_root, code_files, loc_cache) < _HUB_HUSK_LOC_FLOOR:
            return "hub_husk_child"
        return None
    if anchor.source == "hub-core":
        return None  # gated on sibling mints by the caller
    # PAGE-SURFACE RULE (only in repos that have a page surface at all).
    # Authored capability declarations (feature-dirs, workspace packages,
    # python domain packages) are product evidence of their own.
    if repo_has_pages:
        _fiat_src = bool(anchor.sources & {"fdir", "ws-pkg", "pypkg"})
        if product_right_gate and _fiat_src:
            # B87 rung-2 bullet 2 — close the fdir/ws-pkg/pypkg page fiat.
            # A feature-dir / workspace-package / python-package anchor is
            # product evidence ONLY with REAL evidence — a page surface, an
            # author nav mention, or a flow/UF landing in it — never by
            # structure alone (the Captcha/Di/Common progeny class). The
            # SACRED B48 families (shipped SDK / integration / embed
            # subtrees, detector-vetoed) keep the fiat: they survive without
            # a page surface by doctrine (twenty-sdk, cal hitpay/embeds).
            # SCOPED strictly to fiat-sourced anchors — a route:/hub:/schema:
            # anchor keeps the pre-B87 (page ∨ fiat-source ∨ nav) bar so the
            # gate never lifts api_only_surface for a non-fiat surface.
            has_page_evidence = (
                bool(anchor.page_route_files)
                # B1: nav_confirmed lifts ONLY page/flow-corroborated —
                # here the corroborating prongs are already disjuncts, so
                # the nav conjunct is spelled for auditability.
                or (anchor.nav_confirmed and _nav_lift_corroborated(
                    anchor, winners, flow_entries))
                or _anchor_flow_evidence(anchor, winners, flow_entries)
                or _has_authored_view_component(anchor, winners)
                or (bool(sacred_dirs)
                    and _anchor_in_instrument_dirs(anchor, sacred_dirs))
            )
        else:
            has_page_evidence = (
                bool(anchor.page_route_files)
                or _fiat_src
                # B1 (twins-forensics): a bare nav-key hit no longer lifts
                # the bar for a route:/hub:/schema: anchor — the keyed RefApp
                # exhibit (route:mitre / route:article, 0 pages 0 own
                # flows) MUST stay barred; a nav-declared anchor with
                # page/flow corroboration lifts as before.
                or (anchor.nav_confirmed and _nav_lift_corroborated(
                    anchor, winners, flow_entries))
            )
        if not has_page_evidence:
            return "api_only_surface"
    elif headless_product_spine_enabled():
        # B98 v4 (a keyed exhibit refuted the v3 breadth: without the page
        # rule the B87 fiat closure vanished too — kvcache/envconfig/convert
        # minted as PFs). On a HEADLESS repo the route surface IS the product
        # (rungs 1-2), but STRUCTURAL fiat (ws-pkg/fdir/pypkg/go-pkg) stays
        # engineering innards until it carries flow evidence.
        # v5: flow evidence is vacuous when keyed (Stage 3 hands flows to
        # everyone) — the discriminator is the ROUTE-ness of the surface
        # itself. A structural anchor with no route/page file on a headless
        # repo is innards; a CLI surface is its own rung (an honest scope).
        if anchor.source != "route" and not anchor.page_route_files:
            return "headless_internal_package"
    # PYPKG THINNESS (W2b.1 fix b): a package-domain anchor with no flow
    # evidence and fewer than two code files is structure, not a
    # capability (onyx `redis`/`httpx` wrapper-package class).
    if anchor.sources == frozenset({"pypkg"}):
        pk_evidence: set[str] = set(anchor.files)
        for w in winners:
            pk_evidence.update(anchor.matched_set(owned_paths_of(w)))
        code_files = [p for p in pk_evidence if _is_code(p, code_exts)]
        if (len(code_files) < 2
                and not _anchor_flow_evidence(anchor, winners, flow_entries)):
            return "pypkg_thin_surface"
    # SINGLE-CONTAINER RULE — an unmerged, non-authored anchor whose
    # entire evidence is one file AND no flow lands in it (a flowful
    # single-page capability — a real login/pricing page — is legal;
    # a flow-less stray leaf file is not).
    if len(anchor.sources) == 1 and anchor.source == "route":
        evidence: set[str] = set(anchor.files)
        for w in winners:
            evidence.update(anchor.matched_set(owned_paths_of(w)))
        # B98 rung 2+3 — a HEADLESS repo's route TABLE (one registration
        # file carrying the whole API surface, ≥2 winner devs — the
        # ollama server/routes.go exhibit) IS the product surface, but
        # NOT as a single 'routes' tile: rung-3 decomposes — the table
        # anchor gets its own bar and its winner devs become standalone
        # family tiles in the disposition ladder. INDEPENDENTLY of flow
        # evidence (the keyed refutation: live flows made the table a
        # "flowful single-page capability" and it minted whole).
        if (headless_product_spine_enabled() and not repo_has_pages
                and len(evidence) <= 1 and not anchor.prefixes
                and len(winners) >= 2):
            # rung-3e UNPARKED: span LOC for families is live (B1 go-router
            # line+handler 5-tuples → B2 go_func_spans → B3 the 6.97 span
            # branch) — a loc=0 husk-drop no longer eats the families.
            return "headless_route_table"
        if (len(evidence) <= 1 and not anchor.prefixes
                and not _anchor_flow_evidence(anchor, winners, flow_entries)):
            return "single_file_surface"
    return None


# ── Import fold (ladder rung 3) ──────────────────────────────────────────


def _import_fold_targets(
    dev_owned: list[str],
    repo_path: Path,
    tracked: frozenset[str],
    cache: Any,
    alias_map: Any,
) -> list[str]:
    """Resolved OUTGOING import targets of the dev's owned files (repo
    files only), excluding self-owned targets. Reuses the Stage 6.3/8.8
    source cache + workspace-aware resolvers."""
    from wystan.pipeline_v2.stage_6_3_import_tree import (
        _PY_EXTS,
        _TS_EXTS,
        _is_vendor_or_test,
        _suffix,
    )
    from wystan.pipeline_v2.stage_8_8_shared_members import _resolve_one

    own = set(dev_owned)
    out: list[str] = []
    for rel in sorted(own):
        if _suffix(rel) not in (_TS_EXTS | _PY_EXTS) or _is_vendor_or_test(rel):
            continue
        try:
            specs = cache.imports(rel).values()
        except Exception:  # noqa: BLE001 — unreadable file → no imports
            continue
        for spec in specs:
            tgt = _resolve_one(rel, spec, alias_map, tracked)
            if tgt is not None and tgt not in own:
                out.append(tgt)
    return out


# ── Public entrypoint ────────────────────────────────────────────────────


def run_anchored_mint(
    developer_features: list["Feature"],
    routes_index: list[dict[str, Any]] | None,
    ctx: Any,
    extractor_signals: dict[str, list[Any]] | None = None,
    nav_keys: frozenset[str] = frozenset(),
    repo_class: str | None = None,
) -> tuple[list["Feature"], dict[str, Any]]:
    """Derive dev→PF from anchor lineage; REPLACE the product layer.

    Mutates dev features in place (``product_feature_id`` /
    ``anchor_id`` / ``shared_reason``); returns the anchored
    ``product_features`` list + telemetry. The caller swaps its PF
    array for the returned one.

    ``repo_class`` (B105 FIX-2) is the Stage 0.7 verdict for this scan unit.
    It is consulted ONLY under :func:`mint_empty_honest_enabled` and ONLY on
    a ZERO-PF mint, to decide whether an empty product layer is the honest
    answer (library / CLI / infra / framework) or a lost one (product-app).
    ``None`` ⇒ re-derived from ``ctx`` (Stage 0.7 is pure) so replay matches
    the live site.
    """
    from wystan.pipeline_v2.nav_taxonomy import aggregate_product_feature
    from wystan.pipeline_v2.spine_hygiene import is_facet

    vocab = load_spine_vocab()
    code_exts = tuple(vocab.get("code_extensions") or [])
    # B26 — the authored plumbing/stop vocabulary union for the
    # hub_plumbing_child mint-bar backstop (data, not code).
    plumbing_keys = frozenset(
        vocab.get("hub_plumbing_segments") or []
    ) | frozenset(vocab.get("structural_stoplist") or [])

    tele: dict[str, Any] = {
        "enabled": True, "applied": False,
        "anchors_by_source": {}, "anchors_total": 0,
        "devs_total": 0, "devs_in_scope": 0,
        "unique": 0, "unique_capability": 0, "unique_shell": 0,
        "near_tie": 0, "none": 0,
        "fold_union_plurality": 0, "fold_parent": 0, "fold_import": 0,
        "infra_lane": 0, "infra_reasons": {},
        "pf_minted": 0, "bar_decisions": [],
        "churn_devs": 0, "hub_families": [],
    }

    devs = [
        f for f in developer_features
        if getattr(f, "layer", "developer") == "developer"
        and getattr(f, "name", None)
    ]
    tele["devs_total"] = len(devs)
    in_scope = [f for f in devs if not is_facet(f)]
    tele["devs_in_scope"] = len(in_scope)
    if not in_scope:
        return [], tele

    anchors = build_spine_anchors(
        in_scope, routes_index, ctx, extractor_signals, nav_keys)
    tele["anchors_total"] = len(anchors)

    # ── B65-v3 iter-2 — SPA-mint containment fence ────────────────────────
    # A client-side SPA page row (routes_index kind="spa-page") gives its
    # route: anchor PAGE evidence — which lifted api_only_surface bars and
    # let broad mixed devs annex module mass through the fold rungs
    # (RefApp wave refutation: 'Admin'/'Compliance'/'Settings' route: PFs,
    # 100% member LOC outside the anchor subtree; ANNEXATION_GUARD +
    # SAMEUNIT_CAP armed did NOT kill — different channel than the B58
    # unit fence). LAW: a PF minted off spa-page evidence takes members
    # ONLY from the page's own module subtree (page file + the co-located
    # dir sharing its stem, + the page dir for index leaves) plus the
    # anchor's NON-spa evidence files (server routes untouched). A dev
    # with mass outside that universe never binds to the anchor — the
    # mass stays with its otherwise-resolved owner. Inert when no
    # spa-page rows exist (flag OFF ⇒ byte-identical, kill-switch law).
    from wystan.pipeline_v2.extractors.spa_router import SPA_PAGE_KIND

    spa_files: frozenset[str] = frozenset(
        str(r.get("file") or "") for r in (routes_index or [])
        if isinstance(r, dict)
        and str(r.get("kind") or "") == SPA_PAGE_KIND
    ) - frozenset({""})
    #: B98 v6 — route corroboration for the headless standalone-tile prong.
    _route_index_files: frozenset[str] = frozenset(
        str(r.get("file") or "") for r in (routes_index or [])
        if isinstance(r, dict)
    ) - frozenset({""})

    def _spa_pages_of(a: SpineAnchor) -> frozenset[str]:
        return (a.page_route_files & spa_files) if spa_files else frozenset()

    def _spa_module_prefixes(pages: frozenset[str]) -> tuple[str, ...]:
        prefs: list[str] = []
        for pf_ in sorted(pages):
            stem = pf_.rsplit(".", 1)[0]
            prefs.append(stem + "/")
            base = pf_.rsplit("/", 1)[-1]
            if base.split(".")[0] == "index" and "/" in pf_:
                prefs.append(pf_.rsplit("/", 1)[0] + "/")
        return tuple(prefs)

    def _spa_only_anchor(a: SpineAnchor) -> bool:
        """True when the anchor's ONLY evidence is spa-page rows — no
        authored source (fdir/hub/ws/schema/pypkg) and no non-spa
        route/api file claims its subtree.

        B65-v4 Seg A — a spa page that MERGED into an authored anchor
        (``route:detector`` ∪ ``fdir:…/detectors``) is NOT spa-only: the
        feature-dir/hub owns the subtree and the spa page only ADDS a
        route row + journey seed. Such an anchor is never spa-fenced, so
        its authored mass binds exactly as it did with the flag OFF (the
        RefApp Detectors husk root: the merged anchor was spa-fenced and
        orphaned its own 16.8K fdir subtree). Only a PURELY spa anchor
        (a page with no authored backer) stays fenced — it mints its own
        PF solely when no other anchor-class claims the subtree.

        "Authored" is exactly the STRONG spine classes that own a real
        DIR SUBTREE — ``fdir``/``hub-*``/``ws-*``/``schema``/``pypkg``/
        ``svc`` (the spec's "feature-dir/fdir/hub") — AND the merged
        anchor must actually CARRY ≥1 dir prefix (iter-3, the RefApp
        Compliance annexation exhibit): a bare schema/model FILE that
        merged by key (``route:compliance`` = spa page + backend
        ``models/compliance.py``, prefixes=()) names a resource, not a
        subtree — the spec's literal "a feature whose SUBTREE covers a
        page" demands a subtree, so a prefix-less anchor stays
        spa-only and fenced (the wave-17 route:compliance 14.5K
        100%-outside mass rode exactly this hole through the guarded
        fold rungs). A bare non-spa server route/api FILE does not lift
        the fence either: it names a URL, not a subtree (the RefApp
        ``route:admin`` anti-annexation exhibit). The refinement layers
        (``interior``/``excav``) never lift the fence — a page-component
        family with no authored backer stays spa-only and fenced."""
        return not (a.sources & _SPA_AUTHORED_SOURCES and a.prefixes)

    def _spa_contained(a: SpineAnchor, owned: list[str]) -> bool:
        """True when every dev-owned file sits inside the fence universe
        of a spa-paged anchor. Anchors with no spa pages — or spa pages
        that merged into an AUTHORED anchor (Seg A) — are never fenced
        (server-route / feature-dir behaviour byte-identical)."""
        pages = _spa_pages_of(a)
        if not pages:
            return True
        if not _spa_only_anchor(a):
            return True
        allowed = (
            a.files | a.api_route_files | a.page_route_files
        ) - spa_files
        prefs = _spa_module_prefixes(pages)
        for p in owned:
            if p in pages or p in allowed:
                continue
            if any(p.startswith(pre) for pre in prefs):
                continue
            # Module-OWNER page rule: an owned file that is ITSELF a spa
            # page whose stem-dir covers one of this anchor's spa pages
            # is the module's owner page (``settings.vue`` for the
            # ``settings/profile.vue`` prefix-slot anchor) — same module
            # family, never annexed mass.
            if p in spa_files:
                stem_pre = p.rsplit(".", 1)[0] + "/"
                if any(pg.startswith(stem_pre) for pg in pages):
                    continue
            return False
        return True

    def _spa_universe_contained(a: SpineAnchor, owned: list[str]) -> bool:
        """B65-v4 iter-3 — the MASS-fence universe test: every dev-owned
        file sits inside the anchor's OWN claim area — its spa pages +
        their module dirs + its non-spa evidence files + its dir-subtree
        PREFIXES (an authored subtree is legitimate ownership, unlike
        the Seg-A fence universe which guards spa-only anchors). Used by
        the spa-BORN plurality-rung fence, never by Pass-1."""
        pages = _spa_pages_of(a)
        allowed = (
            a.files | a.api_route_files | a.page_route_files
        ) - spa_files
        prefs = _spa_module_prefixes(pages) + tuple(
            pr.rstrip("/") + "/" for pr in a.prefixes)
        for p in owned:
            if p in pages or p in allowed:
                continue
            if any(p.startswith(pre) for pre in prefs):
                continue
            return False
        return True
    by_src: Counter[str] = Counter(a.source for a in anchors)
    tele["anchors_by_source"] = dict(sorted(by_src.items()))

    flow_entries, _flowful = _flow_evidence_index(in_scope)
    # B113 — the Stage-0.7 verdict for this scan unit, resolved ONLY under the
    # class gate (OFF ⇒ zero extra work AND byte-identity). The live site
    # threads the intake verdict; replay passes ``None`` and the pure
    # re-derivation reproduces it (the ``_scan_unit_repo_class`` parity rail).
    _headless_repo_class: str | None = None
    if headless_rescue_class_gate_enabled():
        _headless_repo_class = (
            repo_class if repo_class is not None
            else _scan_unit_repo_class(ctx)
        )
    repo_has_pages, _headless_satellite = headless_repo_pages(
        anchors, flow_entries, _headless_repo_class)
    tele["repo_has_pages"] = repo_has_pages
    if headless_product_spine_enabled():
        # B98 tele — ONLY under the armed flag: an unconditional key broke
        # the 6.86 replay identity against pre-flag baselines (the
        # additivity law; caught by the formbricks identity gate).
        tele["page_anchor_census"] = sorted(
            a.canonical_id for a in anchors if a.page_route_files)[:12]
    if _headless_satellite is not None:
        tele["headless_product_spine"] = {
            "page_satellite": _headless_satellite}
    if headless_surface_rescue_enabled():
        # fixb108-v2 Fix-3 tele — armed-only (the B98 additivity law above:
        # an unconditional key breaks 6.86 replay-identity against
        # pre-flag baselines). Both sides of the majority, so the verdict
        # is auditable from the artifact instead of re-derived.
        tele["headless_majority"] = headless_majority_census(
            anchors, flow_entries, _headless_repo_class)

    # W4.2 Fix 1 — technology-instrument detection (operator principle:
    # mechanisms, not dictionaries). Runs ONCE per scan, here — the mint
    # is the earliest consumer, and suppression must happen AT the mint
    # (the 6.7d PF-backstop would otherwise seed journeys onto the fake
    # capability — the typebot "Run prisma" exhibit).
    from wystan.pipeline_v2.technology_instruments import (
        detect_technology_instruments,
        tech_instruments_enabled,
    )

    instrument_dirs: frozenset[str] = frozenset()
    if tech_instruments_enabled():
        fdir_units = sorted({
            p for a in anchors if "fdir" in a.sources for p in a.prefixes
        })
        hub_dirs = sorted({a.hub_dir for a in anchors if a.hub_dir})
        # B48 S3 (nav) — the author's nav-declared anchor subtrees; a
        # candidate covered by one is a product area, never a lane.
        nav_prefixes = sorted({
            p for a in anchors if getattr(a, "nav_confirmed", False)
            for p in a.prefixes
        })
        try:
            # R4 — hand the detector the ctx-shared source cache (it has
            # no ctx of its own; ``None`` → it constructs locally).
            from wystan.pipeline_v2.shared_source import (
                shared_source_cache as _shared_src,
            )
            ti_tele = detect_technology_instruments(
                Path(getattr(ctx, "repo_path", ".")),
                [str(p) for p in (getattr(ctx, "tracked_files", None) or [])],
                routes_index,
                fdir_units=fdir_units,
                hub_dirs=hub_dirs,
                source_cache=_shared_src(
                    ctx, Path(getattr(ctx, "repo_path", "."))),
                nav_prefixes=nav_prefixes,
            )
            instrument_dirs = frozenset(ti_tele.get("dirs") or [])
            tele["technology_instruments"] = ti_tele
        except Exception as exc:  # noqa: BLE001 — detector never breaks a scan
            tele["technology_instruments"] = {"enabled": True,
                                              "error": str(exc)}

    # ── B87 rung-2 (bullet 1) — product-right narrow standalone bar ───────
    # Closure setup for _dev_standalone_mint. All three signals are reused
    # mechanisms (no new dictionary): the single_letter/version_dir
    # calibration-trap classifier, the technology-instrument detector, and
    # the husk LOC-floor. The SACRED veto-set (B48 doctrine: SDK /
    # integration / embed families survive) is INHERITED for the micro-LOC
    # prong from (a) nav-declared subtrees and (b) the technology-instrument
    # detector's PRODUCT vetoes (route_surface / published_cli /
    # nested_family / hosts_hub_family — every shipped-SDK/embed family
    # lands here, so the census's twenty-sdk dictionary false-positive can
    # never be micro-demoted). Flag OFF ⇒ these are never consulted.
    _pr_gate_on = product_right_gate_enabled()
    _std_version_re = re.compile(
        vocab.get("version_segment_pattern") or r"^v\d+$")
    # The B48 SACRED families the micro-LOC demote must not touch: the
    # technology-instrument detector's own PRODUCT-veto verdicts for shipped
    # SDK / integration / embed / published-CLI families (``nested_family``
    # = packages/embeds/js & packages/framework/*; ``published_cli`` =
    # packages/add-inbox; ``hosts_hub_family`` = the integration hub). These
    # are structural verdicts of the detector, not a name dictionary.
    # ``route_surface`` is DELIBERATELY excluded — a route-bearing app is a
    # product area, but a micro helper inside it carries no product right of
    # its own unless the author's nav declares it (the nav-subtree union).
    _sacred_veto_reasons = frozenset(
        {"published_cli", "nested_family", "hosts_hub_family"})
    _sacred_dirs: frozenset[str] = frozenset(
        str(u).strip("/")
        for u, reason in (
            (tele.get("technology_instruments") or {}).get("vetoed") or {}
        ).items()
        if reason in _sacred_veto_reasons
    )
    _nav_dirs: frozenset[str] = frozenset(
        p for a in anchors if getattr(a, "nav_confirmed", False)
        for p in a.prefixes
    )
    # micro-LOC (bullet 1) protection = nav-declared ∪ SACRED families;
    # the fdir/ws fiat exemption (bullet 2) = SACRED families only (a
    # nav-declared fdir anchor already carries its own ``nav_confirmed``).
    _std_protect_dirs: frozenset[str] = _nav_dirs | _sacred_dirs

    # Pass 1 — classify every in-scope dev.
    owned_by_dev: dict[str, list[str]] = {}
    winner_by_dev: dict[str, SpineAnchor | None] = {}
    verdicts: dict[str, str] = {}
    plurality_by_dev: dict[str, list[tuple[SpineAnchor, float]]] = {}
    prev_stamp = {f.name: getattr(f, "product_feature_id", None) for f in in_scope}
    for f in sorted(in_scope, key=lambda x: x.name):
        owned = owned_paths_of(f)
        owned_by_dev[f.name] = owned
        winner, share, verdict, plur = _classify_dev(owned, anchors)
        # B65-v3 iter-2 — containment fence at the lineage rung: an
        # uncontained dev never WINS a spa-paged anchor (and never rides
        # it as a union-plurality candidate). It reclassifies as "none"
        # and resolves through the ordinary ladder to its real owner.
        # Strictly inert without spa rows (kill-switch byte-identity).
        if spa_files:
            if winner is not None and not _spa_contained(winner, owned):
                tele["spa_fence_blocked"] = (
                    tele.get("spa_fence_blocked", 0) + 1)
                winner, share, verdict = None, 0.0, "none"
            plur = [(c, s) for c, s in plur if _spa_contained(c, owned)]
        winner_by_dev[f.name] = winner
        verdicts[f.name] = verdict
        plurality_by_dev[f.name] = plur
        if verdict == "unique":
            tele["unique"] += 1
            if winner is not None and winner.shell:
                tele["unique_shell"] += 1
            else:
                tele["unique_capability"] += 1
        elif verdict == "near_tie":
            tele["near_tie"] += 1
        else:
            tele["none"] += 1

    # ── fixb125 — CLI anchor supply (G1 clusters → dev map) ───────────
    # Deterministic, $0. Detection is skipped entirely while the flag is
    # OFF, so an unarmed scan never reads a source file for this and the
    # board stays byte-identical.
    _cli_on: bool = cli_anchor_supply_enabled()
    _cli_clusters: tuple[CliCluster, ...] = (
        detect_cli_clusters_cached(ctx) if _cli_on else ())
    _cli_by_dev: dict[str, CliCluster] = {}
    #: fixb126 — supplied cid → the cluster it came from, the
    #: containment basis of the supplied-tile fence (see
    #: ``_cli_supplied_foreign``). Filled at supply time alongside
    #: ``_cli_pending``.
    _cli_supplied_cluster: dict[str, CliCluster] = {}
    #: cids supplied by the CLI rung. They join ``mintable`` only AFTER
    #: the whole ladder has run: a supplied anchor must promote its OWN
    #: unit and nothing else. Adding it live would flip the
    #: ``if flowful and mintable`` rescue gate for every OTHER dev on a
    #: zero-mint board (measured on caddy: 0 → 4 PFs, three of them
    #: collateral) — the fix would then be buying unrelated mints.
    _cli_pending: set[str] = set()
    if _cli_clusters:
        for _n, _o in sorted(owned_by_dev.items()):
            _c = cluster_of_paths(_cli_clusters, _o)
            if _c is not None:
                _cli_by_dev[_n] = _c
        tele["cli_anchor_supply"] = {
            "clusters": [
                {"id": c.canonical_id, "framework": c.framework,
                 "lang": c.lang, "manifest": c.manifest, "bin": c.bin_name,
                 "files": len(c.files), "sites": len(c.sites),
                 "commands": sorted({s.command for s in c.sites if s.command})[:24],
                 "evidence": list(c.evidence)}
                for c in _cli_clusters
            ],
            "site_owning_devs": sorted(_cli_by_dev),
            "supplied_devs": [], "supplied_anchors": [],
            "abstained_devs": [],
        }

    # Pass 2 — mint bar over anchors that won ≥ 1 dev.
    winners_by_anchor: dict[str, list["Feature"]] = defaultdict(list)
    for f in sorted(in_scope, key=lambda x: x.name):
        w = winner_by_dev[f.name]
        if w is not None:
            winners_by_anchor[w.canonical_id].append(f)
    anchor_by_id = {a.canonical_id: a for a in anchors}
    mint_repo_root = Path(getattr(ctx, "repo_path", "."))
    loc_cache: dict[str, int] = {}

    def _spa_fence_veto(cid: str | None, dev_name: str) -> bool:
        """B65-v3 iter-2 — fold-rung fence: ``True`` when *cid* is a
        spa-paged anchor the (uncontained) dev must not bind to. The
        rung then behaves as unresolved and falls through the ladder.
        Inert without spa rows (byte-identity)."""
        if not spa_files or cid is None:
            return False
        a = anchor_by_id.get(cid)
        if a is None:
            return False
        if _spa_contained(a, owned_by_dev.get(dev_name) or []):
            return False
        tele["spa_fence_blocked"] = tele.get("spa_fence_blocked", 0) + 1
        return True
    # Workspace-unit roots, computed ONCE — consumed by the B22a walk
    # guard below and by the B58 annexation guard (Seg A fencing + Seg B
    # dev-artifact-unit bar). Empty tuple on single-unit repos.
    _ws_unit_roots: tuple[str, ...] = _workspace_unit_roots(ctx)
    _annex_on: bool = annexation_guard_enabled()
    # B58-v2 Seg B — the page-surface canonical-unit rung feeds the B58
    # fence, so it is live only while that fence itself is armed.
    _sameunit_cap_on: bool = _annex_on and sameunit_domain_cap_enabled()
    _art_tokens: frozenset[str] = frozenset(
        str(t).strip().lower()
        for t in (vocab.get("unit_root_artifact_tokens") or ())
        if str(t).strip()) if _annex_on else frozenset()
    bar_by_anchor: dict[str, str | None] = {}
    for cid in sorted(winners_by_anchor):
        a = anchor_by_id[cid]
        bar_by_anchor[cid] = _mint_bar(
            a, winners_by_anchor[cid], flow_entries, repo_has_pages,
            code_exts, mint_repo_root, loc_cache,
            instrument_dirs=instrument_dirs, plumbing_keys=plumbing_keys,
            product_right_gate=_pr_gate_on, sacred_dirs=_sacred_dirs)
    # Hub cores mint only when ≥ 1 sibling vendor minted (amendment §2:
    # a core exists relative to its children).
    minted_vendor_hubs = {
        anchor_by_id[cid].hub_dir
        for cid, bar in bar_by_anchor.items()
        if bar is None and anchor_by_id[cid].source == "hub-vendor"
    }
    for cid in sorted(bar_by_anchor):
        a = anchor_by_id[cid]
        if a.source == "hub-core" and bar_by_anchor[cid] is None:
            if a.hub_dir not in minted_vendor_hubs:
                bar_by_anchor[cid] = "hub_core_without_children"
    # B58 Seg B — dev-artifact-unit mint bar: an anchor wholly inside a
    # workspace unit whose unit-ROOT path carries an artifact segment
    # (playground/examples/demo/sample — data:
    # spine-anchor-vocab.yaml:unit_root_artifact_tokens) never mints.
    # The novu route:playground/nextjs/... Notifications exhibit; the
    # cal.com product PAGE named `playground` (route leaf inside
    # apps/web) is structurally out of reach (unit-root grain).
    if _annex_on:
        for cid in sorted(bar_by_anchor):
            if bar_by_anchor[cid] is None and _artifact_unit_anchor(
                    anchor_by_id[cid], _ws_unit_roots, _art_tokens):
                bar_by_anchor[cid] = "dev_artifact_unit"
                tele["mint_bar_dev_artifact_unit"] = (
                    tele.get("mint_bar_dev_artifact_unit", 0) + 1)
    # B65-v3 iter-2 — SPA page-module mint floor (reuses the W3.1 D4 husk
    # floor mechanism: _files_loc + _HUB_HUSK_LOC_FLOOR): a spa-paged
    # anchor whose contained winner mass is below the floor never mints a
    # PF — the page keeps its routes_index row (journey seed + partition
    # surface; the Seg C value), just no PF (hoppscotch 'Enter' 96 LOC
    # class). Winners here are contained by the Pass-1 fence, so the LOC
    # sum IS the page-module mass.
    #
    # B65-v4 iter-2 — the floor is gated by the SAME _spa_only_anchor
    # predicate as the Seg A fence (symmetry law): an AUTHORED anchor
    # (fdir/hub/ws/schema/pypkg/svc) with a coincident spa page is never
    # floor-barred — the flag-OFF world minted it at any mass, and the
    # spa page only ADDS a route row (the RefApp Ticketing exhibit: the
    # merged route:ticketing = fdir 68 LOC < 150 floor died and BOTH its
    # devs laned as sub_mint_bar_surface, one a 0-LOC spa-echo husk).
    # A purely-spa thin page (hoppscotch 'Enter') still floors.
    if spa_files:
        for cid in sorted(bar_by_anchor):
            if bar_by_anchor[cid] is not None:
                continue
            a = anchor_by_id[cid]
            if not _spa_pages_of(a):
                continue
            if not _spa_only_anchor(a):
                continue
            member_files = sorted({
                p for f in winners_by_anchor[cid]
                for p in owned_by_dev[f.name]})
            code_files = [p for p in member_files if _is_code(p, code_exts)]
            if _files_loc(
                    mint_repo_root, code_files, loc_cache,
            ) < _HUB_HUSK_LOC_FLOOR:
                bar_by_anchor[cid] = "spa_page_floor"
                tele["mint_bar_spa_page_floor"] = (
                    tele.get("mint_bar_spa_page_floor", 0) + 1)
    # B65-v4 iter-4 — spa MEMBER-TWIN mint bar (panel exhibit 'Apipage'
    # re-claiming API Keys' components/api-keys/* members): a spa-only
    # anchor whose winner member-set MAJORITARILY overlaps another
    # minting anchor's member-set is a TWIN of that PF, not a new
    # surface — per Seg A(1) the spa page may only ADD a route row /
    # journey seed to the owner (the routes_index row survives
    # untouched; only the duplicate mint dies). Overlap share is
    # scale-invariant (|∩| / |spa members|, majority threshold), the
    # comparison universe includes the counterpart's anchor-matched
    # files. Coincidence-by-SUBTREE (Ticketing) is the Seg A authored
    # path and never reaches here; coincidence-by-MEMBERS is this bar.
    if spa_files:
        _owned_union: dict[str, set[str]] = {}
        for cid in sorted(bar_by_anchor):
            if bar_by_anchor[cid] is None:
                _owned_union[cid] = {
                    p for f in winners_by_anchor[cid]
                    for p in owned_by_dev[f.name]}
        for cid in sorted(_owned_union):
            a = anchor_by_id[cid]
            if not _spa_pages_of(a) or not _spa_only_anchor(a):
                continue
            mine = _owned_union[cid]
            if not mine:
                continue
            for cid2 in sorted(_owned_union):
                if cid2 == cid or bar_by_anchor[cid2] is not None:
                    continue
                other = _owned_union[cid2] | set(
                    anchor_by_id[cid2].matched_set(sorted(mine)))
                share = len(mine & other) / len(mine)
                if share > 0.5:
                    bar_by_anchor[cid] = "spa_member_twin"
                    tele["mint_bar_spa_member_twin"] = (
                        tele.get("mint_bar_spa_member_twin", 0) + 1)
                    break
    for cid in sorted(bar_by_anchor):
        if bar_by_anchor[cid] and len(tele["bar_decisions"]) < 50:
            tele["bar_decisions"].append(
                {"anchor": cid, "bar": bar_by_anchor[cid],
                 "devs": [f.name for f in winners_by_anchor[cid][:5]]})

    mintable = {cid for cid, bar in bar_by_anchor.items() if bar is None}

    # B65-v4 iter-3 — SPA-BORN mint census (the wave-17 'Compliance'
    # 14.5K/100%-outside annexation family, reborn as 'findings' after
    # the compliance fence): a minted anchor is SPA-BORN when no winner
    # dev would keep its θ-majority against the anchor STRIPPED of its
    # spa-page evidence — i.e. the mint exists only because of the spa
    # page rows (the flag-OFF world never minted it). Terminal PLURALITY
    # rungs (span-vote / ancestor-walk) are neighborhood votes with no
    # per-dev evidence link, so they may never pour an uncontained dev
    # into a spa-born PF — the walk RE-VOTES without the fenced target
    # (landing the dev on its flag-OFF-world plurality home) instead of
    # laning it. Entry/import folds carry a real evidence link (flow
    # entry files / resolved imports — the mandate's "an explicit
    # evidence link") and stay open. Empty without spa rows (kill-switch
    # byte-identity).
    spa_born: frozenset[str] = frozenset()
    if spa_files:
        import dataclasses as _dc

        # The counterfactual anchor FIELD: every anchor stripped of its
        # spa-page evidence (files + page rows). Winner FORMATION is the
        # honest test (the RefApp api-findings exhibit: OFF-world its
        # winner was the ws:frontend shell — the spa pages flipped the
        # specificity/dominance outcome, not a θ-retention).
        _cf_anchors = [
            _dc.replace(
                a,
                files=a.files - spa_files,
                page_route_files=a.page_route_files - spa_files,
            ) if (a.files & spa_files or a.page_route_files & spa_files)
            else a
            for a in anchors
        ]
        _born: set[str] = set()
        for cid in sorted(mintable):
            a = anchor_by_id[cid]
            if not _spa_pages_of(a):
                continue
            keeps = False
            for _wdev in winners_by_anchor.get(cid) or []:
                owned_w = owned_by_dev.get(_wdev.name) or []
                if not owned_w:
                    continue
                cf_w, _cs, _cv, _cp = _classify_dev(owned_w, _cf_anchors)
                if cf_w is not None and cf_w.canonical_id == cid:
                    keeps = True
                    break
            if not keeps:
                _born.add(cid)
        spa_born = frozenset(_born)
        if spa_born:
            tele["spa_born_anchors"] = sorted(spa_born)

    # Pass 3 — assignment + fold ladder.
    #   assignment: dev name → (anchor canonical_id, provenance)
    assignment: dict[str, tuple[str, str]] = {}
    infra: dict[str, str] = {}  # dev name → shared_reason

    def _parent_fold(a: SpineAnchor) -> str | None:
        """Nearest MINTING ancestor by prefix containment (version-dir /
        collection-descend children fold into their API surface). File
        anchors (api leaves) locate through their files' dirs — the
        W2b.1 api-leaf-fold rung (fix d2) rides this."""
        units = list(a.prefixes or ())
        units.extend(f.rsplit("/", 1)[0] for f in sorted(a.files) if "/" in f)
        best: tuple[int, str] | None = None
        for cid in mintable:
            m = anchor_by_id[cid]
            for mp in m.prefixes:
                for ap in units:
                    if ap.startswith(mp + "/") or ap == mp:
                        cand = (len(mp), cid)
                        if best is None or cand > best:
                            best = cand
        return best[1] if best else None

    def _entry_fold(f: "Feature") -> str | None:
        """The minting anchor holding the MAJORITY of the dev's flow
        entry files — the strongest behavioral fold signal (validator
        I16's own ruler): a dev whose journeys enter through one
        capability's surface belongs to it (supabase FDW wrappers class:
        the dev's flow enters via the integrations page).

        W3.1 D1/D6 DEFER RULE: when the entries ALSO majority-sit inside
        a MORE SPECIFIC unminted route anchor carrying >= 2 page routes
        (a real capability surface, the I24 grain), the fold DEFERS to
        the pending ladder — rung L1 mints that anchor on demand.
        Without it a workspace-scoped app router (tracecat: everything
        under /workspaces/[id]/...) entry-folds tables/integrations/
        settings into the coarse minted `Workspaces` PF (46K LOC — the
        fb3 D1 sink shape at the entry rung). A single-page sub-surface
        (supabase FDW wrappers, 1 page) still folds under its hosting
        capability — the operator amendment case 5d grain."""
        entries = [str(ep) for fl in (getattr(f, "flows", None) or [])
                   if (ep := getattr(fl, "entry_point_file", None))]
        if not entries:
            return None
        votes: Counter[str] = Counter()
        for ep in entries:
            best_cid: str | None = None
            best_spec: tuple[int, int, str] | None = None
            for cid in sorted(mintable):
                a = anchor_by_id[cid]
                if not a.matches(ep):
                    continue
                # Most specific match wins: exact file > longest prefix.
                spec = (
                    1 if ep in a.files else 0,
                    max((len(p) for p in a.prefixes
                         if ep.startswith(p + "/") or ep == p), default=0),
                    cid,
                )
                if best_spec is None or spec > best_spec:
                    best_cid, best_spec = cid, spec
            if best_cid is not None:
                votes[best_cid] += 1
        if not votes:
            return None
        (best, n), = votes.most_common(1)
        tied = sorted(c for c, v in votes.items() if v == n)
        best = tied[0]
        if votes[best] * 2 <= len(entries):
            return None
        # Defer to L1 when a finer >=2-page route anchor holds the
        # entry majority (deterministic: sorted candidates, first hit).
        route_votes: Counter[str] = Counter()
        for ep in entries:
            fine_cid: str | None = None
            fine_spec: tuple[int, int, str] | None = None
            for a in anchors:
                if (a.source != "route" or a.canonical_id in mintable
                        or a.shell or a.barred or not a.matches(ep)):
                    continue
                spec = (
                    1 if ep in a.files else 0,
                    max((len(p) for p in a.prefixes
                         if ep.startswith(p + "/") or ep == p), default=0),
                    a.canonical_id,
                )
                if fine_spec is None or spec > fine_spec:
                    fine_cid, fine_spec = a.canonical_id, spec
            if fine_cid is not None:
                route_votes[fine_cid] += 1
        if route_votes:
            (fine, fn), = route_votes.most_common(1)
            fine_tied = sorted(c for c, v in route_votes.items() if v == fn)
            fine = fine_tied[0]
            fa = anchor_by_id.get(fine)
            if (fa is not None
                    and route_votes[fine] * 2 > len(entries)
                    and len(fa.page_route_files) >= 2
                    and fa.subtree_inside(anchor_by_id[best])):
                tele["entry_fold_deferred_to_l1"] = (
                    tele.get("entry_fold_deferred_to_l1", 0) + 1)
                return None
        return best

    def _anchor_of_target(t: str) -> str | None:
        """The most specific MINTING anchor covering one file (exact
        file > longest prefix). Shared by the import-fold and the
        span-vote law rungs."""
        best_cid: str | None = None
        best_spec: tuple[int, int] | None = None
        for cid in sorted(mintable):
            a = anchor_by_id[cid]
            if not a.matches(t):
                continue
            spec = (
                1 if t in a.files else 0,
                max((len(p) for p in a.prefixes
                     if t.startswith(p + "/") or t == p), default=0),
            )
            if best_spec is None or spec > best_spec:
                best_cid, best_spec = cid, spec
        return best_cid

    def _file_owner_map() -> dict[str, str]:
        """file → first ASSIGNED dev primary-owning it (ownership
        fallback channel of the vote rungs)."""
        out: dict[str, str] = {}
        for name in sorted(assignment):
            for p in owned_by_dev.get(name, ()):
                out.setdefault(p, name)
        return out

    def _entry_route_mint(f: "Feature") -> str | None:
        """W2b.1 law rung L1 — entry-file ROUTE lineage: a flowful dev
        whose flow entry files majority-sit inside ONE route anchor gets
        that anchor MINTED ON DEMAND (openstatus login class: the dev's
        journeys enter through a real page surface, so the surface is a
        product feature even when lineage dilution starved the anchor of
        winners). The on-demand anchor passes the FULL mint bar — an
        api-only or param-barred surface never mints this way (those
        fold via the api-leaf/span rungs instead)."""
        entries = [str(ep) for fl in (getattr(f, "flows", None) or [])
                   if (ep := getattr(fl, "entry_point_file", None))]
        if not entries:
            return None
        votes: Counter[str] = Counter()
        for ep in entries:
            best_cid: str | None = None
            best_spec: tuple[int, int, str] | None = None
            for a in anchors:
                if a.source != "route" or not a.matches(ep):
                    continue
                spec = (
                    1 if ep in a.files else 0,
                    max((len(p) for p in a.prefixes
                         if ep.startswith(p + "/") or ep == p), default=0),
                    a.canonical_id,
                )
                if best_spec is None or spec > best_spec:
                    best_cid, best_spec = a.canonical_id, spec
            if best_cid is not None:
                votes[best_cid] += 1
        if not votes:
            return None
        (_best, n), = votes.most_common(1)
        tied = sorted(c for c, v in votes.items() if v == n)
        best = tied[0]
        if votes[best] * 2 <= len(entries):
            return None
        # B58 Seg A — L1 is an entry-shaped rung the B22a guard never
        # wrapped: a unit-coherent dev never entry-mints across a
        # workspace unit (the ladder falls through to span/walk, which
        # lane it honestly when every target is foreign).
        if _annex_foreign(f, best):
            tele["annex_guard_entry_blocked"] = (
                tele.get("annex_guard_entry_blocked", 0) + 1)
            return None
        if best in mintable:
            return best
        a = anchor_by_id[best]
        if a.shell:
            return None
        bar = _mint_bar(a, [f], flow_entries, repo_has_pages, code_exts,
                        mint_repo_root, loc_cache,
                        instrument_dirs=instrument_dirs,
                        plumbing_keys=plumbing_keys,
                        product_right_gate=_pr_gate_on, sacred_dirs=_sacred_dirs)
        if bar is not None:
            return None
        # B58 Seg B — the on-demand mint honours the dev-artifact-unit
        # bar (the Seg B pass runs over anchors with WINNERS; an anchor
        # first reached here would otherwise mint through the bypass —
        # the novu playground Notifications door).
        if _annex_on and _artifact_unit_anchor(a, _ws_unit_roots,
                                               _art_tokens):
            tele["mint_bar_dev_artifact_unit"] = (
                tele.get("mint_bar_dev_artifact_unit", 0) + 1)
            return None
        mintable.add(best)
        bar_by_anchor[best] = None
        return best

    def _span_vote(f: "Feature") -> str | None:
        """W2b.1 law rung L2 — the dev's flows' file SPANS vote for the
        minting anchor (or assigned owner) holding them; PLURALITY wins
        (terminal-rung semantics — a flowful dev must land in a real
        capability, the binding is recorded in the provenance note).

        W3.1 D1 COHERENCE GUARD: the winning target must account for at
        least ``_UNION_FLOOR`` of the dev's DISTINCT span files — the
        same random-tail bound every other plurality rung uses, with the
        honest denominator (unresolvable span mass counts AGAINST the
        bind). Without it a giant dev whose span resolves only through a
        tiny sliver was force-bound to that sliver's PF (comp
        `mcp-server` 34.5K LOC → the 3-file `security` route PF — the
        fb3 D1 sink class)."""
        file_owner = _file_owner_map()
        votes: Counter[str] = Counter()
        span_files: set[str] = set()
        matched_files: dict[str, set[str]] = defaultdict(set)
        for fl in (getattr(f, "flows", None) or []):
            span = [str(p) for p in (getattr(fl, "paths", None) or [])]
            ep = getattr(fl, "entry_point_file", None)
            if not span and ep:
                span = [str(ep)]
            for p in span:
                span_files.add(p)
                cid = _anchor_of_target(p)
                if cid is None:
                    owner = file_owner.get(p)
                    if owner is not None:
                        cid = assignment[owner][0]
                if cid is not None:
                    votes[cid] += 1
                    matched_files[cid].add(p)
        if not votes:
            return None
        (_best, n), = votes.most_common(1)
        tied = sorted(c for c, v in votes.items() if v == n)
        best = tied[0]
        if span_files and (
                len(matched_files[best]) / len(span_files) < _UNION_FLOOR):
            return None
        return best

    # ── B22a — cross-app fold guard state (walk rung only) ───────────
    # Unit roots from the repo's own manifests; empty tuple ⇒ guard inert
    # (single-unit repos, or kill-switch WYSTAN_FOLD_CROSSAPP_GUARD=0).
    _fold_guard_units: tuple[str, ...] = (
        _ws_unit_roots if fold_crossapp_guard_enabled() else ())
    _anchor_unit_cache: dict[str, str | None] = {}

    def _anchor_unit(cid: str) -> str | None:
        """The single workspace unit holding the anchor's evidence, or
        ``None`` when the evidence spans ≥2 units or sits wholly outside
        every unit (a genuinely cross-unit / non-unit anchor is never
        foreign — the guard cannot call it an annexation). Evidence
        OUTSIDE any unit (root-level files) does not veto a single-unit
        anchor — a ``packages/email`` anchor with a stray root manifest
        is still a packages/email anchor (documenso keyless
        calibration: ``route:email`` must stay foreign to
        ``apps/openpage-api`` devs)."""
        if cid not in _anchor_unit_cache:
            a = anchor_by_id.get(cid)
            unit: str | None = None
            if a is not None:
                units = {
                    u for ev in list(a.prefixes) + sorted(a.files)
                    if (u := _unit_of(str(ev), _fold_guard_units)) is not None
                }
                if len(units) == 1:
                    unit = next(iter(units))
            _anchor_unit_cache[cid] = unit
        return _anchor_unit_cache[cid]

    # ── B58 Seg A — canonical anchor unit + all-rung fencing ─────────
    _canon_unit_cache: dict[str, str | None] = {}

    def _canonical_anchor_unit(cid: str) -> str | None:
        """The workspace unit of the anchor's CANONICAL identity — not
        its post-merge evidence union. Rungs, most-canonical first:

        1. the anchor-id-embedded path (``svc:apps/web/core/services/
           issue`` → apps/web; ws:/fdir:/pypkg:/hub:/route:<prefix> all
           embed their own subtree) — a same-key merge widens evidence
           but never rewrites the head's id;
        2. unit UNANIMITY over the anchor's OWN route surface files
           (page + api) — a key-only route anchor (``route:space``) is
           identified by where its routes live;
        2.5. B58-v2 Seg B (``WYSTAN_SAMEUNIT_DOMAIN_CAP=1`` only) —
           when rung 2 is NON-unanimous, unit unanimity over the PAGE
           surface alone: a full-stack anchor whose pages all live in
           one dedicated app (plane ``route:space`` — pages wholly in
           apps/space, api views in apps/api) is canonically THAT app;
           its api evidence widens ownership, not identity. Multi-unit
           PAGE surfaces and api-only anchors still fall through
           (conservative — never called foreign);
        3. the B22a evidence-unanimity fallback (``_anchor_unit``).

        ``None`` ⇒ genuinely cross-unit — never called foreign."""
        if cid not in _canon_unit_cache:
            unit: str | None = None
            a = anchor_by_id.get(cid)
            if a is not None:
                tail = cid.split(":", 1)[1] if ":" in cid else cid
                if "/" in tail:
                    unit = _unit_of(tail, _ws_unit_roots)
                if unit is None:
                    surface = sorted(a.page_route_files | a.api_route_files)
                    units = {
                        u for p in surface
                        if (u := _unit_of(str(p), _ws_unit_roots)) is not None
                    }
                    if len(units) == 1:
                        unit = next(iter(units))
                    elif len(units) > 1 and _sameunit_cap_on:
                        page_units = {
                            u for p in sorted(a.page_route_files)
                            if (u := _unit_of(str(p), _ws_unit_roots))
                            is not None
                        }
                        if len(page_units) == 1:
                            unit = next(iter(page_units))
                            tele["cap_page_surface_unit"] = (
                                tele.get("cap_page_surface_unit", 0) + 1)
                if unit is None:
                    unit = _anchor_unit(cid)
            _canon_unit_cache[cid] = unit
        return _canon_unit_cache[cid]

    def _dev_home_unit(f: "Feature") -> str | None:
        """The single workspace unit holding the dev's own files, or
        ``None`` when they span units / sit outside every unit (a
        non-coherent dev is never fenced — B22a semantics)."""
        owned = owned_by_dev.get(f.name) or []
        units = {
            u for p in owned
            if (u := _unit_of(p, _ws_unit_roots)) is not None
        }
        return next(iter(units)) if len(units) == 1 else None

    def _annex_foreign(f: "Feature", target_cid: str) -> bool:
        """B58 Seg A predicate — ``True`` when force-binding *f* onto
        *target_cid* would cross a workspace-unit boundary: the dev is
        unit-coherent AND the target's canonical unit is a DIFFERENT
        unit. Either side unresolved ⇒ never foreign (conservative)."""
        if not (_annex_on and _ws_unit_roots):
            return False
        home = _dev_home_unit(f)
        if home is None:
            return False
        tgt = _canonical_anchor_unit(target_cid)
        return tgt is not None and tgt != home

    def _ancestor_walk(
        f: "Feature", skip_cids: frozenset[str] = frozenset(),
    ) -> tuple[str | None, bool]:
        """W2b.1 law rung L3 — nearest-ancestor plurality: walk UP from
        the dev's owned files' common dir; the first level where ANY
        assigned dev owns files decides by plurality of their anchors.

        ``skip_cids`` (B65-v4 iter-3) — spa-born anchors this dev may
        not fold into: the walk RE-VOTES without them, landing the dev
        on the plurality target the flag-OFF world would have chosen.
        Total whenever ≥1 dev is assigned (the repo-root level sees
        every assigned file).

        B22a cross-app fold guard (default ON): a vote for an anchor
        whose evidence sits wholly inside a FOREIGN workspace unit — a
        unit holding none of the dev's own files — is void; the walk may
        never annex a dev across the workspace boundary (the documenso
        ``ws:packages/trpc`` exhibit). Same-unit folds and a package
        folding within its own subtree are untouched. Returns
        ``(target, guard_isolated)``: ``guard_isolated`` is True only
        when the guard voided EVERY target the unguarded walk would have
        reached (the caller lanes the dev with its own unit instead of
        recording a law breach)."""
        owned = owned_by_dev.get(f.name) or []
        dirs = [p.rsplit("/", 1)[0] if "/" in p else "" for p in owned]
        if dirs:
            first = dirs[0].split("/") if dirs[0] else []
            k = len(first)
            for other_str in dirs[1:]:
                other = other_str.split("/") if other_str else []
                j = 0
                while j < min(k, len(other)) and other[j] == first[j]:
                    j += 1
                k = j
            common = "/".join(first[:k])
        else:
            common = ""
        assigned_file_cid = {
            p: assignment[name][0]
            for name in sorted(assignment)
            for p in owned_by_dev.get(name, ())
        }

        def _walk(skip: frozenset[str]) -> str | None:
            level = common
            while True:
                votes: Counter[str] = Counter()
                for p, cid in assigned_file_cid.items():
                    if cid in skip:
                        continue
                    if not level or p.startswith(level + "/"):
                        votes[cid] += 1
                if votes:
                    (_best, n), = votes.most_common(1)
                    tied = sorted(c for c, v in votes.items() if v == n)
                    return tied[0]
                if not level:
                    return None
                level = level.rsplit("/", 1)[0] if "/" in level else ""

        # B58 Seg A: with the annexation guard armed the walk fences by
        # the target's CANONICAL unit (closing the multi-unit-evidence
        # host hole) and stays armed even when the B22a flag alone is
        # kill-switched. OFF ⇒ byte-identical B22a behaviour.
        guard_units = _fold_guard_units or (
            _ws_unit_roots if _annex_on else ())
        if not guard_units:
            return _walk(skip_cids), False
        dev_units = frozenset(
            u for p in owned
            if (u := _unit_of(p, guard_units)) is not None)
        if not dev_units:
            return _walk(skip_cids), False
        unit_fn = _canonical_anchor_unit if _annex_on else _anchor_unit
        foreign = frozenset(
            cid for cid in set(assigned_file_cid.values())
            if (au := unit_fn(cid)) is not None and au not in dev_units)
        if not foreign:
            return _walk(skip_cids), False
        guarded = _walk(foreign | skip_cids)
        if os.environ.get("WYSTAN_MINT_DEBUG") == "1":
            tele.setdefault("fold_debug", []).append({
                "dev": f.name, "rung": "walk-guard",
                "dev_units": sorted(dev_units),
                "foreign": sorted(foreign)[:8],
                "guarded": guarded,
                "guarded_unit": (_anchor_unit(guarded)
                                 if guarded is not None else None),
            })
        if guarded is not None:
            if guarded != _walk(skip_cids):
                # the annexation fix: the dev re-homes inside a unit it
                # actually lives in instead of the foreign plurality.
                tele["fold_walk_crossunit_rehomed"] = (
                    tele.get("fold_walk_crossunit_rehomed", 0) + 1)
            return guarded, False
        # every reachable target is cross-unit ⇒ the dev is ISOLATED in
        # a unit with no minted anchor; annexing it is the B22a disease.
        return None, _walk(skip_cids) is not None

    # ── B78 Seg A — walk-evidence gate (WYSTAN_FOLD_EVIDENCE_WEIGHT) ──
    # The ancestor-walk votes by FILE plurality — zero behavioral content.
    # Armed, a walk fold whose target holds NO claim on the dev's flow
    # entry files re-disposes by the dev's own entry evidence (module
    # docstring at FOLD_EVIDENCE_WEIGHT_ENV; rulings R1-R3). The claim is
    # judged on the target ANCHOR's subtree only — the owner map is
    # itself poisoned by the annexation being cured (the B69-v2 lesson).
    _evw_on = fold_evidence_weight_enabled()

    def _entry_files_of(f: "Feature") -> list[str]:
        return [str(ep) for fl in (getattr(f, "flows", None) or [])
                if (ep := getattr(fl, "entry_point_file", None))]

    _file_route_keys_cache: dict[str, Counter[str]] = {}

    def _file_route_keys(ep: str) -> Counter[str]:
        """R1(b) ruler — how many of ONE file's route rows carry each
        anchor key ('the anchor with the larger share of the file's
        routes'). Derived from the same ``routes_index`` chain the
        route-anchor builder consumes; scale-invariant (shares, not
        counts, decide — and only WITHIN one file's exact-claim tie)."""
        if ep not in _file_route_keys_cache:
            from wystan.pipeline_v2.spine_anchors import (
                _route_chain,
                normalize_anchor_key,
            )
            version_re = re.compile(
                vocab.get("version_segment_pattern") or r"^v\d+$")
            votes: Counter[str] = Counter()
            for entry in routes_index or []:
                if not isinstance(entry, dict):
                    continue
                if str(entry.get("file") or "") != ep:
                    continue
                keys = {
                    normalize_anchor_key(seg)
                    for seg, _pre, _dep in _route_chain(
                        ep, str(entry.get("pattern") or ""), vocab,
                        version_re)
                }
                for k in sorted(keys):
                    if k:
                        votes[k] += 1
            _file_route_keys_cache[ep] = votes
        return _file_route_keys_cache[ep]

    def _evidence_anchor_for_entry(ep: str, dev_name: str) -> str | None:
        """The best evidence-claiming anchor of ONE entry file:
        exact-file claimants first (R1 tiebreak: the route-convention
        anchor named by the file's own stem, else the larger share of
        the file's routes, else source rank), then the longest-prefix
        claimant. Shells, structurally-barred keys (version_dir /
        single_letter / param_leaf) and spa-fenced targets never
        qualify — an api_only_surface mint bar does NOT disqualify
        (entry evidence is exactly the behavioral proof it lacked)."""
        exact: list[SpineAnchor] = []
        prefix_best: tuple[int, int, str] | None = None
        for a in anchors:
            if a.shell or a.barred is not None:
                continue
            if not a.matches(ep):
                continue
            cid = a.canonical_id
            # Spa containment law at the evidence grain: a claim through
            # the anchor's NON-spa evidence file (server route / api
            # file — the law's own "server routes untouched" universe)
            # is behavioral and stands; any other claim on a spa-paged
            # anchor keeps the B65 fence (prefix claims are subtree
            # claims — the annexation channel the fence exists for).
            _non_spa_claim = ep in (
                (a.files | a.api_route_files | a.page_route_files)
                - spa_files)
            if not _non_spa_claim and _spa_fence_veto(cid, dev_name):
                continue
            if ep in a.files:
                exact.append(a)
                continue
            plen = max((len(p) for p in a.prefixes
                        if ep.startswith(p + "/") or ep == p), default=-1)
            if plen < 0:
                continue
            cand = (-plen, a.rank, cid)
            if prefix_best is None or cand < prefix_best:
                prefix_best = cand
        if exact:
            if len(exact) == 1:
                return exact[0].canonical_id
            # R1 (a) — the route-convention anchor named by the entry
            # file's OWN stem (api-admin: backend/routers/admin.py names
            # the admins family, not 'webhook-dispatcher').
            from wystan.pipeline_v2.spine_anchors import (
                normalize_anchor_key as _nk,
            )
            stem = ep.rsplit("/", 1)[-1]
            stem = stem[: stem.rfind(".")] if "." in stem else stem
            stem_key = _nk(stem)
            named = sorted(
                (a for a in exact
                 if a.key == stem_key
                 and "route" in (a.sources or {a.source})),
                key=lambda a: a.canonical_id)
            if named:
                tele["walk_evidence_r1_stem"] = (
                    tele.get("walk_evidence_r1_stem", 0) + 1)
                return named[0].canonical_id
            # R1 (b) — the anchor holding the larger share of the file's
            # own routes; residual ties by source rank then stable id.
            shares = _file_route_keys(ep)
            ranked = sorted(
                exact,
                key=lambda a: (-shares.get(a.key, 0), a.rank,
                               a.canonical_id))
            if shares.get(ranked[0].key, 0):
                tele["walk_evidence_r1_route_share"] = (
                    tele.get("walk_evidence_r1_route_share", 0) + 1)
            return ranked[0].canonical_id
        return prefix_best[2] if prefix_best is not None else None

    # ── B78-it2 Goal 2a — dead-router discriminator D (probe canon) ──────
    # The R2/R3 mint rungs below also mint DEAD-ROUTER shapes: a backend
    # router in a shared dir whose frontend client is bootstrap-wired but
    # consumed by nobody (RefApp audit-events), or consumed only by a
    # FOREIGN domain's surface (audit → ActivityLogPage, network-mock →
    # query0). D = scope-guard + (C1 stem-consumption ∨ C2 stem-UI) +
    # fold-else re-judges exactly that shape before a mint lands:
    # confirmed mints keep their channel; consumed-by-foreign FOLDS into
    # the anchor owning the consumer (dir-attribution — probe risk 2
    # forbids board membership as the owner ruler); zero consumers
    # DEMOTES (the caller keeps the pre-gate disposition). Out-of-scope
    # devs (dedicated domain dir / own UI / >3 members / unverifiable
    # shared-dir) are untouched — the twenty/langfuse zero-UI PFs and
    # the R3 standalone law live outside D by construction.
    _d_cache: dict[str, tuple[str, str] | None] = {}
    _d_text_cache: dict[str, str | None] = {}
    _D_DEMOTE: tuple[str, str] = ("", "d-demote")  # identity sentinel

    def _d_read(rel: str) -> str | None:
        if rel not in _d_text_cache:
            try:
                p = Path(getattr(ctx, "repo_path", ".")) / rel
                if p.stat().st_size > 1_500_000:  # nav_parent's read cap
                    _d_text_cache[rel] = None
                else:
                    _d_text_cache[rel] = p.read_text(
                        encoding="utf-8", errors="ignore")
            except OSError:
                _d_text_cache[rel] = None
        return _d_text_cache[rel]

    def _d_override(
        f: "Feature", best_cid: str | None = None,
    ) -> tuple[str, str] | None:
        """``None`` — keep the caller's mint (out-of-scope or C1/C2
        confirmed); ``_D_DEMOTE`` (identity) — suppress it; anything
        else — ``(target_cid, "fold:consumer-evidence")``.

        The DOMAIN identity D matches against is the WOULD-BE PF's name:
        ``slug(anchor.display)`` when the mint channel elected an
        evidence anchor (the PF is named by the anchor — the census
        lesson: real dev names carry ``api-`` prefixes and suffixes
        (``api-context-items``, ``api-trial-status``) that no consumed
        symbol or UI basename ever matches), else the dev's own name
        (the standalone channel names the PF from it)."""
        if f.name in _d_cache:
            return _d_cache[f.name]
        from wystan.pipeline_v2.dev_mint_discriminator import (
            discriminate_dev_mint,
        )
        domain = (_slug(anchor_by_id[best_cid].display)
                  if best_cid is not None else f.name)
        owned = sorted(owned_by_dev.get(f.name) or ())
        owned_set = frozenset(owned)
        patterns = [
            str(r.get("pattern") or "") for r in (routes_index or [])
            if isinstance(r, dict) and str(r.get("file") or "") in owned_set
        ]
        tracked = [str(p) for p in (getattr(ctx, "tracked_files", None) or [])]
        v = discriminate_dev_mint(
            domain, owned, patterns, tracked, _d_read, code_exts)
        result: tuple[str, str] | None
        row: dict[str, Any] = {"dev": f.name, "domain": domain,
                               "verdict": v.kind, "via": v.via}
        if v.kind == "out-of-scope":
            result = None
        elif v.kind == "mint":
            key = ("walk_evidence_d_mint_c1"
                   if (v.via or "").startswith("c1:")
                   else "walk_evidence_d_mint_c2")
            tele[key] = tele.get(key, 0) + 1
            result = None
        elif v.kind == "fold":
            votes: Counter[str] = Counter()
            for cf in v.consumer_files:
                cid = _anchor_of_target(cf)
                if cid is not None:
                    votes[cid] += 1
            result = _D_DEMOTE
            if votes:
                (_best, n), = votes.most_common(1)
                best = sorted(c for c, vn in votes.items() if vn == n)[0]
                if not _annex_foreign(f, best):
                    tele["walk_evidence_d_fold"] = (
                        tele.get("walk_evidence_d_fold", 0) + 1)
                    row["target"] = best
                    result = (best, "fold:consumer-evidence")
            if result is _D_DEMOTE:
                # Consumers exist but no minted anchor claims any of
                # them (or the elected owner is unit-foreign) — the
                # honest residue is demotion, tracked apart.
                tele["walk_evidence_d_fold_unresolved"] = (
                    tele.get("walk_evidence_d_fold_unresolved", 0) + 1)
                row["verdict"] = "demote"
        else:  # demote
            tele["walk_evidence_d_demote"] = (
                tele.get("walk_evidence_d_demote", 0) + 1)
            result = _D_DEMOTE
        if v.kind != "out-of-scope":
            tele["walk_evidence_d_candidates"] = (
                tele.get("walk_evidence_d_candidates", 0) + 1)
            tele.setdefault("walk_evidence_d_rows", []).append(row)
        if os.environ.get("WYSTAN_MINT_DEBUG") == "1":
            tele.setdefault("fold_debug", []).append({
                "dev": f.name, "rung": "d-discriminator",
                "verdict": row.get("verdict", v.kind), "via": v.via,
                "consumers": list(v.consumer_files)[:8],
                "target": row.get("target"),
            })
        _d_cache[f.name] = result
        return result

    def _standalone_protected(anchor: SpineAnchor) -> bool:
        """B48 SACRED veto inheritance (B87 rung-2 bullet 1) — a standalone
        anchor is protected from the micro-LOC demote when it is
        nav-declared / page-bearing OR when its every code file sits under a
        nav-declared or technology-instrument PRODUCT-vetoed subtree (the
        shipped SDK / integration / embed families the census flagged as
        dictionary false-positives, e.g. twenty-sdk)."""
        if getattr(anchor, "nav_confirmed", False) or anchor.page_route_files:
            return True
        if not _std_protect_dirs:
            return False
        code_files = [p for p in anchor.files if _is_code(p, code_exts)]
        return bool(code_files) and all(
            any(p == d or p.startswith(d + "/") for d in _std_protect_dirs)
            for p in code_files)

    def _standalone_narrow_bar(
        f: "Feature", anchor: SpineAnchor,
    ) -> tuple[str | None, int]:
        """B87 rung-2 bullet 1 — the NARROW product-right bar for a
        dev-standalone mint candidate. Returns ``(bar_reason | None, loc)``.

        Prongs (all reused mechanisms, no new dictionary): single_letter /
        version_dir (the calibration-trap key classes), technology_instrument
        (mechanism-detected dev tooling), micro-LOC<100 demote (a body this
        small carries no product right, unless SACRED-protected).
        ``api_only_surface`` is DELIBERATELY NOT a prong — it fires on 100 %
        of standalone anchors (no page_route_files by construction) and
        over-kills the live magic-sign-up / channels / home / activity
        surfaces (probe-canon E2)."""
        code_files = [p for p in sorted(anchor.files)
                      if _is_code(p, code_exts)]
        loc = _files_loc(mint_repo_root, code_files, loc_cache)
        br = _bar_reason(f.name, _std_version_re)
        if br in ("single_letter", "version_dir"):
            return br, loc
        if instrument_dirs and _anchor_in_instrument_dirs(
                anchor, instrument_dirs):
            return "technology_instrument", loc
        if (0 < loc < _STANDALONE_MICRO_LOC_FLOOR
                and not _standalone_protected(anchor)):
            # loc == 0 is DELIBERATELY excluded — a 0-LOC row is a separate
            # LOC-truth display defect (B66-v2), not a genuine micro helper;
            # conflating it here would demote a real feature on a LOC bug.
            return "micro_dev", loc
        return None, loc

    def _dev_standalone_mint(f: "Feature") -> tuple[str, str] | None:
        """R2/R3 last rung — the dev STANDS ALONE as its own PF when no
        evidence-claiming anchor can take it (no claimant at all, or the
        elected one sits across a workspace unit): >=2 distinct entry
        files / >=2 flows is capability-grade behavioral proof and R3
        forbids laning it, so the honest disposition is a visible
        standalone PF over the dev's own files (unit-local — no
        annexation by construction), never a silent vacuum fold.

        B87 rung-2 (bullet 1) — under ``WYSTAN_PRODUCT_RIGHT_GATE`` the
        candidate first passes the narrow product-right bar. A barred
        candidate is DENIED the standalone tile and returns ``None`` — the
        caller keeps the honest ladder disposition (the walk fold / lane),
        never a silent deletion; its journeys are re-homed by the stage
        6.9965 token rung. Flag OFF ⇒ the ``None`` path is unreachable
        (byte-identical)."""
        cid = f"dev:{f.name}"
        if cid not in anchor_by_id:
            display = (getattr(f, "display_name", None) or "").strip()
            if not display:
                display = " ".join(
                    w.capitalize()
                    for w in re.split(r"[-_\s]+", f.name) if w) or f.name
            anchor_by_id[cid] = SpineAnchor(
                canonical_id=cid,
                key=normalize_anchor_key(f.name),
                source="dev-standalone",
                display=display,
                files=frozenset(owned_by_dev.get(f.name) or ()),
                sources=frozenset({"dev-standalone"}),
            )
        anchor = anchor_by_id[cid]
        if _pr_gate_on:
            _bar, _loc = _standalone_narrow_bar(f, anchor)
            if len(tele.setdefault("product_right_probe_rows", [])) < 200:
                tele["product_right_probe_rows"].append({
                    "dev": f.name, "key": anchor.key, "bar": _bar,
                    "loc": _loc, "n_flows": len(getattr(f, "flows", None) or []),
                    "nav_confirmed": getattr(anchor, "nav_confirmed", False),
                })
            if _bar is not None:
                tele["product_right_denied"] = (
                    tele.get("product_right_denied", 0) + 1)
                tele.setdefault("product_right_bars", {})[f.name] = _bar
                return None
        # B98 v6 — headless repo: a standalone tile only for route-corroborated
        # devs (files ∩ routes_index). Go packages kvcache/envconfig/convert
        # with flows (keyed Stage 3 hands them to all) are innards, not tiles.
        if (headless_product_spine_enabled() and not repo_has_pages
                and not (set(anchor.files) & _route_index_files)):
            tele["headless_standalone_denied"] = (
                tele.get("headless_standalone_denied", 0) + 1)
            return None
        mintable.add(cid)
        bar_by_anchor[cid] = None
        tele["walk_evidence_dev_mint"] = (
            tele.get("walk_evidence_dev_mint", 0) + 1)
        return cid, "mint:dev-standalone"

    def _cli_foreign(f: "Feature", target_cid: str | None) -> bool:
        """fixb125 — CLUSTER-CONTAINMENT fence (the B58 ``_annex_foreign``
        shape, keyed on the CLI cluster instead of the workspace unit).

        A unit that IS a shipped CLI may bind only to an anchor whose own
        evidence reaches INSIDE that CLI's module. Measured pair:

        * ente ``cli`` → ``schema:admin``: the anchor's files include
          ``cli/cmd/admin.go`` — same module, a legitimate home (this is
          the positive control the ledger recorded as ``cli→admin``);
        * lobe-chat ``cli`` → ``agent``: every ``agent`` anchor lives in
          ``packages/*`` / ``src/server`` — annexing 79 files of
          ``apps/cli`` into a chat capability.

        A ROOT-module cluster (``cli:.``) contains everything, so the
        fence is inert there by construction — those units are protected
        by the annex exits instead.
        """
        c = _cli_by_dev.get(f.name)
        if c is None or target_cid is None or target_cid == c.canonical_id:
            return False
        base = c.module
        if base in ("", "."):
            return False
        a = anchor_by_id.get(target_cid)
        if a is None:
            return True
        for ev in list(a.prefixes) + sorted(a.files):
            p = str(ev)
            if p == base or p.startswith(base + "/"):
                return False
        return True

    def _cli_supplied_foreign(cid: str | None, dev_name: str) -> bool:
        """fixb126 — the SUPPLIED-TILE fence (the mirror of
        ``_cli_foreign``): ``True`` when *dev_name* is a unit the freshly
        supplied CLI tile *cid* must not absorb.

        MEASURED DEFECT (lobe-chat, c19/c20 keyed pair, reproduced by
        replay of the 6.86 capture): the CLI rung inserts its anchor into
        ``anchor_by_id`` mid-ladder and stamps its own unit into
        ``assignment``. Both plurality rungs — span and ancestor-walk —
        vote over ALREADY-ASSIGNED files, so the 78 freshly-assigned
        files of ``apps/cli`` became the biggest non-foreign vote block
        at the repo-root walk level and the tile annexed ``lambda``
        (17664 LOC of tRPC routers, ``lambda.healthcheck`` on the OFF
        side) plus, downstream, ``changelog`` and ``memory`` via the
        transport handoff that follows a PF. A tile the ladder minted
        one dev ago has no standing to out-vote anchors that carried
        their devs all scan.

        THE LAW: a supplied tile admits ONLY its own cluster —
        (a) a unit that OWNS registration sites of THAT cluster
        (``cluster_of_paths`` authority: ollama ``cmd`` + ``launch``),
        or (b) a unit that lives WHOLLY inside the cluster's own
        evidence tree (``CliCluster.site_tree``: ollama ``cmd/config``,
        ``cmd/tui``, ``cmd/internal`` — the CLI's own subtree, which the
        module-keyed ``_cli_foreign`` fence cannot see because ollama's
        manifest is at the repo ROOT). Everything else keeps the
        disposition the flag-OFF world gave it.

        Inert by construction while the rung has supplied nothing
        (``_cli_pending`` empty ⇒ every call returns ``False``), so the
        OFF board is byte-identical.
        """
        if cid is None or cid not in _cli_pending:
            return False
        cluster = _cli_supplied_cluster.get(cid)
        if cluster is None:
            return False
        return not supplied_tile_admits(
            cluster, owned_by_dev.get(dev_name) or ())

    def _cli_supply(f: "Feature") -> tuple[str, str] | None:
        """fixb125 — the CLI **anchor-supply** rung.

        A dev unit that OWNS the registration sites of a G1-passing CLI
        entry cluster (:mod:`wystan.pipeline_v2.cli_commands`) is the
        repo's shipped command surface. The cluster supplies its command
        anchors — the registration ``file:line`` + declared command name
        — as that unit's lineage, and the unit takes the ordinary mint
        path over its OWN files (unit-local by construction: no
        prefixes, no annexation, exactly the ``_dev_standalone_mint``
        shape). ONE anchor per CLUSTER, so sibling units of the same CLI
        (ollama ``cmd`` + ``launch``) join ONE product feature rather
        than minting a tile each.

        DOUBLE-MINT GUARD (measured, ledger 2026-08-06): the rung is
        consulted ONLY at the ladder's annex/lane exits — i.e. only for a
        unit that is otherwise bound for ``platform_infrastructure`` and
        carries no ``product_feature_id``. Every unit whose CLI is
        already ON the product map resolves EARLIER (ente ``cli`` at
        ``mint:entry-evidence``, onyx ``cli`` at ``mint:dev-standalone``,
        hydrogen/meilisearch/novu/twenty/hoppscotch at ``lineage``) and
        never reaches this rung — those boards stay byte-identical.

        Returns ``(cid, provenance)`` or ``None`` (caller keeps its own
        honest disposition — the rung never deletes a fallback path).
        """
        c = _cli_by_dev.get(f.name)
        if c is None:
            return None
        if f.name in assignment:  # already homed — never double-mint
            _t = tele.setdefault("cli_anchor_supply", {})
            _t.setdefault("abstained_devs", []).append(f.name)
            return None
        cid = c.canonical_id
        owned = frozenset(owned_by_dev.get(f.name) or ())
        anchor = anchor_by_id.get(cid)
        base = (c.bin_name or (c.module.rsplit("/", 1)[-1]
                               if c.module not in ("", ".") else "")
                or f.name)
        if anchor is None:
            anchor_by_id[cid] = SpineAnchor(
                canonical_id=cid,
                key=normalize_anchor_key(base),
                source="cli",
                display=_cli_display(base),
                files=owned,
                sources=frozenset({"cli"}),
            )
        else:
            # widen the cluster anchor with this sibling unit's files
            anchor.files = anchor.files | owned
        _cli_pending.add(cid)
        _cli_supplied_cluster[cid] = c
        _t = tele.setdefault("cli_anchor_supply", {})
        _t.setdefault("supplied_devs", []).append(f.name)
        if cid not in (_t.get("supplied_anchors") or []):
            _t.setdefault("supplied_anchors", []).append(cid)
        tele["cli_anchor_supply_devs"] = (
            tele.get("cli_anchor_supply_devs", 0) + 1)
        return cid, "mint:cli-anchor"

    def _walk_evidence_dispose(
        f: "Feature", entries: list[str],
    ) -> tuple[str, str] | None:
        """R2/R3 disposition of an evidence-VOID walk fold — returns
        ``(target_cid, prov_family)`` or ``None`` (caller keeps the void
        fold honestly; a flowful dev is NEVER laned by this gate)."""
        n_flows = len(getattr(f, "flows", None) or [])
        r2_mint = len(set(entries)) >= 2 or n_flows >= 2
        votes: Counter[str] = Counter()
        for ep in entries:
            cid = _evidence_anchor_for_entry(ep, f.name)
            if cid is not None:
                votes[cid] += 1
        if os.environ.get("WYSTAN_MINT_DEBUG") == "1":
            tele.setdefault("fold_debug", []).append({
                "dev": f.name, "rung": "walk-evidence",
                "entries": entries[:8],
                "votes": dict(votes.most_common(8)),
            })
        if not votes:
            # No evidence-claiming anchor exists anywhere (unextracted
            # routers — the RefApp 'api'/'network-mock' shape).
            if not r2_mint:
                return None
            _dd = _d_override(f)
            if _dd is _D_DEMOTE:
                return None
            if _dd is not None:
                return _dd
            return _dev_standalone_mint(f)
        (_best, n), = votes.most_common(1)
        tied = sorted(c for c, v in votes.items() if v == n)
        best = tied[0]
        # B58 law — a unit-coherent dev never evidence-binds across a
        # workspace unit (same fence as the entry/L1 rungs).
        # fixb125 — …and a CLI unit never binds outside its own cluster.
        _cli_blocked = _cli_foreign(f, best)
        if _cli_blocked:
            tele["cli_supply_evidence_blocked"] = (
                tele.get("cli_supply_evidence_blocked", 0) + 1)
        if _annex_foreign(f, best) or _cli_blocked:
            tele["walk_evidence_annex_blocked"] = (
                tele.get("walk_evidence_annex_blocked", 0) + 1)
            if not r2_mint:
                return _cli_supply(f)
            _dd = _d_override(f)
            if _dd is _D_DEMOTE:
                return _cli_supply(f)
            if _dd is not None:
                return _dd
            return _cli_supply(f) or _dev_standalone_mint(f)
        if best in mintable:
            # fixb125 — a CLI unit may MINT its own evidence anchor, but
            # it never FOLDS INTO someone else's already-live capability.
            # The measured pair separates exactly here: ente ``cli``
            # MINTS ``schema:admin`` on demand (``mint:entry-evidence``,
            # untouched), while lobe-chat ``cli`` folded 79 files of
            # ``apps/cli`` into the already-minted chat capability
            # ``agent`` — a name-match coincidence on one command file
            # (``commands/agent.ts``), not a home.
            _cli = _cli_supply(f)
            if _cli is not None:
                tele["cli_supply_livefold_blocked"] = (
                    tele.get("cli_supply_livefold_blocked", 0) + 1)
                return _cli
            # The dev's evidence points at a LIVE capability — fold in.
            return best, "fold:entry-evidence"
        if r2_mint:
            # R2/R3 — standalone mint on demand: >=2 distinct entry
            # files or >=2 flows is capability-grade behavioral proof.
            _dd = _d_override(f, best)
            if _dd is _D_DEMOTE:
                return None
            if _dd is not None:
                return _dd
            mintable.add(best)
            bar_by_anchor[best] = None
            tele["walk_evidence_mint_on_demand"] = (
                tele.get("walk_evidence_mint_on_demand", 0) + 1)
            return best, "mint:entry-evidence"
        # R2 single-flow brake — prefer the nearest MINTED claimant of
        # the entry file over a fresh standalone PF; mint only when no
        # evidence-claiming PF exists at all.
        near = _anchor_of_target(entries[0])
        if (near is not None and not _spa_fence_veto(near, f.name)
                and not _annex_foreign(f, near)):
            tele["walk_evidence_single_flow_fold"] = (
                tele.get("walk_evidence_single_flow_fold", 0) + 1)
            return near, "fold:entry-evidence"
        _dd = _d_override(f, best)
        if _dd is _D_DEMOTE:
            return None
        if _dd is not None:
            return _dd
        mintable.add(best)
        bar_by_anchor[best] = None
        tele["walk_evidence_single_flow_mint"] = (
            tele.get("walk_evidence_single_flow_mint", 0) + 1)
        return best, "mint:entry-evidence"

    fold_pending: list[tuple["Feature", SpineAnchor | None, str]] = []
    for f in sorted(in_scope, key=lambda x: x.name):
        w = winner_by_dev[f.name]
        if w is not None and w.canonical_id in mintable:
            assignment[f.name] = (w.canonical_id, "lineage")
            continue
        if w is None:
            # NONE → rider R2 union-plurality first.
            accepted = False
            for cand, share in plurality_by_dev[f.name]:
                if (cand.canonical_id in mintable and share >= _UNION_FLOOR
                        and len(cand.sources) >= 2):
                    assignment[f.name] = (cand.canonical_id, "union_plurality")
                    tele["fold_union_plurality"] += 1
                    accepted = True
                    break
            if not accepted:
                ef = _entry_fold(f)
                # B58 Seg A — the entry rung was never B22a-guarded (the
                # cal.com fold:entry->ws:apps/api/v2 annexation): a
                # unit-coherent dev never entry-folds across a unit.
                if ef is not None and _annex_foreign(f, ef):
                    tele["annex_guard_entry_blocked"] = (
                        tele.get("annex_guard_entry_blocked", 0) + 1)
                    ef = None
                # B65-v3 iter-2 — spa containment fence on the entry rung.
                if ef is not None and _spa_fence_veto(ef, f.name):
                    ef = None
                if ef is not None:
                    assignment[f.name] = (ef, "fold:entry->none")
                    tele["fold_entry"] = tele.get("fold_entry", 0) + 1
                else:
                    fold_pending.append((f, None, _SHARED_REASON_NONE))
            continue
        # W4.2 Fix 1 — an instrument anchor's devs NEVER fold into a
        # product capability (attributing the UI kit / ORM package to a
        # random importing feature is exactly the mis-attribution the
        # lane exists for). Flowless devs lane under
        # ``technology_instrument``; a flowful dev still rides the LAW
        # rescue (span-vote → walk) below — the lane law holds.
        if bar_by_anchor.get(w.canonical_id) == "technology_instrument":
            tele["instrument_devs"] = tele.get("instrument_devs", 0) + 1
            fold_pending.append((f, w, _SHARED_REASON_INSTRUMENT))
            continue
        # Winner exists but cannot mint → parent fold, entry fold,
        # api-leaf fold, then import fold.
        parent = _parent_fold(w)
        # B65-v3 iter-2 — spa containment fence on every parent-fold use.
        if parent is not None and _spa_fence_veto(parent, f.name):
            parent = None
        if parent is not None and w.barred in {"version_dir", "single_letter",
                                               "param_leaf"}:
            assignment[f.name] = (parent, f"fold:parent->{w.canonical_id}")
            tele["fold_parent"] += 1
            continue
        ef = _entry_fold(f)
        # B58 Seg A — entry-rung fence (see the none-winner site above).
        if ef is not None and _annex_foreign(f, ef):
            tele["annex_guard_entry_blocked"] = (
                tele.get("annex_guard_entry_blocked", 0) + 1)
            ef = None
        # B65-v3 iter-2 — spa containment fence on the entry rung.
        if ef is not None and _spa_fence_veto(ef, f.name):
            ef = None
        if ef is not None:
            assignment[f.name] = (ef, f"fold:entry->{w.canonical_id}")
            tele["fold_entry"] = tele.get("fold_entry", 0) + 1
            continue
        # API-LEAF FOLD (W2b.1 fix d2): a dev whose winner is an
        # api-only-barred surface folds into the nearest MINTING
        # ancestor capability (supabase pages/api singles were meant to
        # die by this class; the parent rung above only served the
        # barred-KEY classes).
        if (bar_by_anchor.get(w.canonical_id) == "api_only_surface"
                and parent is not None):
            assignment[f.name] = (parent, f"fold:api-parent->{w.canonical_id}")
            tele["fold_api_parent"] = tele.get("fold_api_parent", 0) + 1
            continue
        # HUSK FOLD (W3.1 D4): a vendor-husk child folds under its hub
        # core / enclosing package as a dev-child — the fb3 amendment
        # rule ("flowful OR >= 150 owned LOC, else fold into the parent
        # integrations PF"). B26: a plumbing-named child
        # (hub_plumbing_child) takes the same hub-parent path — its
        # flowful devs usually resolve one rung earlier via the entry
        # fold (entries sit in the enclosing package's subtree); this
        # rung catches the flowless / entry-miss residue.
        if (bar_by_anchor.get(w.canonical_id)
                in {"hub_husk_child", _BAR_HUB_PLUMBING_CHILD}
                and parent is not None):
            assignment[f.name] = (parent, f"fold:hub-parent->{w.canonical_id}")
            tele["fold_hub_parent"] = tele.get("fold_hub_parent", 0) + 1
            continue
        # B98 rung-3 — headless route-TABLE decompose: the winner devs of a
        # table anchor become product tiles of their own (ollama
        # api-chat/generate/pull/push families; the v6 standalone-mint prong
        # skips them — files ∩ routes_index). Those refused by the narrow bar
        # honestly fall into the lane, as before.
        if bar_by_anchor.get(w.canonical_id) == "headless_route_table":
            # The "/" route (slug root) is a home registration, not a
            # capability (I11 exhibit 'Root'): an honest residual, not a tile.
            _got = (None if str(getattr(f, "name", "") or "") == "root"
                    else _dev_standalone_mint(f))
            if _got is not None:
                assignment[f.name] = _got
                tele["headless_table_family_mint"] = (
                    tele.get("headless_table_family_mint", 0) + 1)
                continue
        reason = (_SHARED_REASON_SHELL if w.shell else _SHARED_REASON_BAR)
        fold_pending.append((f, w, reason))

    # LAW RUNG L1 (W2b.1 fix a) — entry-route lineage BEFORE the import
    # fold (task order: entry-file route lineage → import-fold →
    # span-vote). Mint-on-demand may EXTEND ``mintable`` — iteration is
    # name-sorted, so the extension is deterministic.
    still_pending: list[tuple["Feature", SpineAnchor | None, str]] = []
    for f, w, reason in fold_pending:
        if getattr(f, "flows", None):
            target = _entry_route_mint(f)
            if os.environ.get("WYSTAN_MINT_DEBUG") == "1":
                tele.setdefault("fold_debug", []).append({
                    "dev": f.name, "rung": "L1-entry-route",
                    "target": target,
                    "entries": [str(ep) for fl in (getattr(f, "flows", None) or [])
                                if (ep := getattr(fl, "entry_point_file", None))][:8],
                })
            # B65-v3 iter-2 — spa containment fence on the L1 rung: an
            # uncontained dev never entry-route-mints a spa-paged anchor
            # (the RefApp 'Admin' page-entry annexation channel).
            if target is not None and _spa_fence_veto(target, f.name):
                target = None
            # fixb125 — cluster-containment fence on the L1 rung.
            if target is not None and _cli_foreign(f, target):
                tele["cli_supply_entryroute_blocked"] = (
                    tele.get("cli_supply_entryroute_blocked", 0) + 1)
                target = None
            if target is not None:
                src = w.canonical_id if w is not None else "none"
                assignment[f.name] = (target, f"mint:entry-route->{src}")
                tele["mint_entry_route"] = tele.get("mint_entry_route", 0) + 1
                continue
        still_pending.append((f, w, reason))
    fold_pending = still_pending

    # Import fold — one deterministic round over the pass-3 residue.
    if fold_pending:
        from wystan.analyzer.tsconfig_paths import build_path_alias_map
        from wystan.pipeline_v2.stage_6_3_import_tree import _SourceCache

        repo_path = Path(getattr(ctx, "repo_path", "."))
        tracked = frozenset(str(p) for p in (getattr(ctx, "tracked_files", None) or []))
        # R4 — adopt the ctx-shared source cache (fallback: local).
        from wystan.pipeline_v2.shared_source import shared_source_cache
        src_cache = (shared_source_cache(ctx, repo_path)
                     or _SourceCache(repo_path))
        try:
            alias_map = build_path_alias_map(repo_path)
        except Exception:  # noqa: BLE001 — resolver is best-effort
            alias_map = None
        # Vote by MINTING-ANCHOR SUBTREE membership of the import targets
        # (spine-true: anchors are the membership units; dev-ownership is
        # derived). The midday acceptance run showed the dev-ownership
        # vote misses workspace-package imports whose files nobody
        # primary-owns (`@midday/invoice/templates` → packages/invoice
        # inside the MERGED `invoices` anchor). Per target: the most
        # specific matching minting anchor (exact file > longest prefix).
        file_owner = _file_owner_map()
        still_pending = []
        for f, w, reason in fold_pending:
            if reason == _SHARED_REASON_INSTRUMENT:
                # Fix 1: instrument code is DEPENDED ON by everything —
                # the import vote is exactly backwards for it.
                still_pending.append((f, w, reason))
                continue
            owned = owned_by_dev[f.name]
            targets = _import_fold_targets(
                owned, repo_path, tracked, src_cache, alias_map)
            votes: Counter[str] = Counter()
            for t in targets:
                target_cid = _anchor_of_target(t)
                if target_cid is None:
                    owner = file_owner.get(t)
                    if owner is not None:
                        target_cid = assignment[owner][0]
                if target_cid is not None:
                    votes[target_cid] += 1
            resolved = False
            if os.environ.get("WYSTAN_MINT_DEBUG") == "1":
                tele.setdefault("fold_debug", []).append({
                    "dev": f.name, "rung": "import",
                    "targets_total": len(targets),
                    "votes": dict(votes.most_common(8)),
                })
            if votes:
                total = sum(votes.values())
                (best_cid, best_n), = votes.most_common(1)
                # strict majority of anchor-covered targets, tie → alpha
                tied = sorted(c for c, n in votes.items() if n == best_n)
                best_cid = tied[0]
                # W3.1 D1 SELF-EVIDENCE GUARD: imports point at what the
                # dev DEPENDS ON, not what it IS — on every app-shaped
                # repo the import majority lands on the shared component
                # library (documenso: 11 route devs → ws:packages/ui at
                # 60-90% majorities; tracecat: 21 frontend clusters →
                # the `status` PF; supabase: `studio` 99.5K → the 2.7K
                # `claim-project` page). A fold may follow imports only
                # when the target also holds >= _UNION_FLOOR of the
                # dev's OWN files (near-lineage confirmation), or the
                # dev is a <= 3-file stub whose only content IS the
                # import surface (the midday `i` page class W2b built
                # this rung for).
                # B65-v3 iter-2 — spa containment fence on the import
                # rung (the annexation class the wave named): imports
                # pointing INTO a spa page never annex the importer.
                # fixb125 — cluster-containment fence on the import rung.
                if _cli_foreign(f, best_cid):
                    tele["cli_supply_import_blocked"] = (
                        tele.get("cli_supply_import_blocked", 0) + 1)
                elif (votes[best_cid] * 2 > total
                        and not _spa_fence_veto(best_cid, f.name)):
                    target_anchor = anchor_by_id[best_cid]
                    own_inside = sum(
                        1 for p in owned if target_anchor.matches(p))
                    self_evident = (
                        len(owned) <= 3
                        or (len(owned) > 0
                            and own_inside / len(owned) >= _UNION_FLOOR)
                    )
                    if self_evident:
                        src = w.canonical_id if w is not None else "none"
                        assignment[f.name] = (best_cid, f"fold:import->{src}")
                        tele["fold_import"] += 1
                        resolved = True
                    else:
                        tele["fold_import_guard_blocked"] = (
                            tele.get("fold_import_guard_blocked", 0) + 1)
            if not resolved:
                still_pending.append((f, w, reason))
        fold_pending = still_pending

    # LAW (W2b.1 fix a — operator): a dev with ≥1 flow must NEVER land
    # in the platform_infrastructure lane. Terminal rungs: span-vote
    # (flow-path plurality, rung L2) then ancestor-walk plurality
    # (rung L3, total whenever ≥1 dev is assigned). The lane is for
    # genuinely FLOWLESS plumbing only; the binding is low-confidence by
    # construction and carries a provenance note (``fold:span->…`` /
    # ``fold:walk->…``). Degenerate scans (zero mintable anchors) keep
    # the honest lane — there is no capability to bind to.
    #
    # W3.1 D1 CARVE-OUT — the law's own ruler (validator I9) EXEMPTS
    # workspace-anchor devs from the flowful-in-lane class, and
    # conservation.py's dev-rehome states why: "anchors never move —
    # their flow sample spans the whole workspace, not one capability".
    # Force-binding them was the single biggest sink source (supabase
    # `studio` 99.5K LOC / 478 flows → the `claim-project` page PF).
    # They lane honestly (flows stay visible on the lane row; their
    # files ride role="shared" members on every importing feature).
    #
    # W3.2 NARROWING — the ws-anchor MARKER alone over-fires: it also
    # tags small coherent capability devs (typebot `user`: 8 account
    # flows, 20 files split packages/user + builder features/user) whose
    # laning the ruler does NOT exempt → wave31's one core I9 breach.
    # The carve-out now additionally requires the SHELL SHAPE the ruler
    # itself exempts (``_lane_shell_exempt``); ws-marker devs that fail
    # it ride the same guarded rescue ladder (span-vote → walk) as every
    # other flowful dev — the law holds for every flowful dev regardless
    # of anchor family, lane only if truly flowless.
    from wystan.pipeline_v2.stage_8_7_anchor_desink import (
        _is_workspace_anchor,
    )

    for f, w, reason in fold_pending:
        flowful = bool(getattr(f, "flows", None))
        if flowful and _is_workspace_anchor(f) and f.name in _cli_by_dev:
            # fixb125 exit 5/5 — WS-ANCHOR SHELL CARVE-OUT. The W3.1 D1
            # carve-out lanes a workspace-anchor dev because "its flow
            # sample spans the whole workspace, not one capability". A
            # workspace whose manifest declares a BINARY is the
            # counter-example the carve-out never had: the package IS one
            # deliverable, so its flow sample spans exactly that
            # deliverable (tracecat ``packages/tracecat-admin``,
            # lobe-chat ``apps/cli``).
            #
            # The exemption RELEASES the dev to the ordinary ladder — it
            # does NOT supply the anchor here. Supplying at this seam
            # would preempt the walk-evidence rungs and steal units the
            # ladder already homes correctly (measured: ente ``cli`` →
            # ``admin`` and meilisearch's four barred crates changed).
            # Released devs land on exits 1/2/4 or on a real evidence
            # rung, whichever the ladder decides.
            tele["cli_supply_wsshell_released"] = (
                tele.get("cli_supply_wsshell_released", 0) + 1)
        elif flowful and _is_workspace_anchor(f):
            if _lane_shell_exempt(f):
                tele["law_ws_anchor_laned"] = (
                    tele.get("law_ws_anchor_laned", 0) + 1)
                infra[f.name] = (
                    _SHARED_REASON_SHELL if w is not None and w.shell
                    else reason)
                continue
            # marker present but shape says product code — released to
            # the ladder (tracked for the smoke gates).
            tele["law_ws_anchor_released"] = (
                tele.get("law_ws_anchor_released", 0) + 1)
        if flowful and mintable:
            src = w.canonical_id if w is not None else "none"
            target = _span_vote(f)
            # B58 Seg A — the span rung was never B22a-guarded (novu
            # fold:span->ws:packages/js): a unit-coherent dev never
            # span-binds across a workspace unit; it falls through to
            # the guarded walk (and lanes when every target is foreign).
            if target is not None and _annex_foreign(f, target):
                tele["annex_guard_span_blocked"] = (
                    tele.get("annex_guard_span_blocked", 0) + 1)
                target = None
            # B65-v3 iter-2 — spa containment fence on the span rung.
            if target is not None and _spa_fence_veto(target, f.name):
                target = None
            # B65-v4 iter-3 — spa-born mass fence: a plurality vote never
            # binds an uncontained dev to a spa-born PF; the dev falls
            # through to the guarded walk (which re-votes without it).
            if (target is not None and target in spa_born
                    and not _spa_universe_contained(
                        anchor_by_id[target],
                        owned_by_dev.get(f.name) or [])):
                tele["spa_born_span_blocked"] = (
                    tele.get("spa_born_span_blocked", 0) + 1)
                target = None
            # fixb126 — supplied-tile fence on the span rung (same shape
            # as the spa-born mass fence above): a freshly supplied CLI
            # tile never wins a plurality over a FOREIGN unit; the dev
            # falls through to the guarded walk, which re-votes without
            # it and lands where the flag-OFF world put it.
            if target is not None and _cli_supplied_foreign(target, f.name):
                tele["cli_supply_span_magnet_blocked"] = (
                    tele.get("cli_supply_span_magnet_blocked", 0) + 1)
                target = None
            if os.environ.get("WYSTAN_MINT_DEBUG") == "1":
                tele.setdefault("fold_debug", []).append({
                    "dev": f.name, "rung": "span", "target": target,
                })
            if target is not None:
                # fixb125 exit 1/4 — SPAN ANNEX. A unit that owns a
                # declared command surface is never absorbed by a
                # span-plurality host (ollama ``launch`` → ``app``, which
                # 6.996 later strips as foreign anyway).
                _cli = _cli_supply(f) if _cli_by_dev else None
                if _cli is not None:
                    assignment[f.name] = _cli
                    tele["cli_supply_span_blocked"] = (
                        tele.get("cli_supply_span_blocked", 0) + 1)
                    continue
                assignment[f.name] = (target, f"fold:span->{src}")
                tele["fold_span_vote"] = tele.get("fold_span_vote", 0) + 1
                continue
            _walk_skips = frozenset(
                cid for cid in spa_born
                if not _spa_universe_contained(
                    anchor_by_id[cid], owned_by_dev.get(f.name) or []))
            if _walk_skips:
                tele["spa_born_walk_skips"] = (
                    tele.get("spa_born_walk_skips", 0) + 1)
            # fixb126 — supplied-tile fence on the WALK rung, expressed
            # in the walk's own vocabulary: the skipped cid makes the
            # walk RE-VOTE without the fresh tile instead of vetoing the
            # fold outright, so the dev keeps a real home (lobe-chat
            # ``lambda`` → ``route:lambda-healthcheck``, its OFF home)
            # rather than falling to the lane.
            _cli_skips = frozenset(
                cid for cid in _cli_pending
                if _cli_supplied_foreign(cid, f.name))
            if _cli_skips:
                tele["cli_supply_walk_magnet_blocked"] = (
                    tele.get("cli_supply_walk_magnet_blocked", 0) + 1)
                _walk_skips = _walk_skips | _cli_skips
            target, guard_isolated = _ancestor_walk(f, _walk_skips)
            # B65-v3 iter-2 — spa containment fence on the walk rung.
            if target is not None and _spa_fence_veto(target, f.name):
                target = None
            if target is not None:
                # B78 Seg A — walk-evidence gate: the fold is valid only
                # when the target anchor claims >=1 of the dev's flow
                # entry files; a VOID fold re-disposes by the dev's own
                # entry evidence (R1-R3). Flag OFF ⇒ byte-identical.
                if _evw_on:
                    _entries = _entry_files_of(f)
                    if _entries and not any(
                            anchor_by_id[target].matches(ep)
                            for ep in _entries):
                        tele["walk_evidence_void"] = (
                            tele.get("walk_evidence_void", 0) + 1)
                        _disp = _walk_evidence_dispose(f, _entries)
                        if _disp is not None:
                            _ev_cid, _ev_prov = _disp
                            assignment[f.name] = (
                                _ev_cid, f"{_ev_prov}->{src}")
                            tele["walk_evidence_redisposed"] = (
                                tele.get("walk_evidence_redisposed", 0) + 1)
                            continue
                        # R3 — never lane a flowful dev here: with no
                        # evidence-claiming anchor anywhere, the void
                        # fold stays (visible, counted).
                        tele["walk_evidence_void_kept"] = (
                            tele.get("walk_evidence_void_kept", 0) + 1)
                # fixb125 exit 2/4 — WALK ANNEX. Consulted AFTER the
                # walk-evidence disposal above, so a CLI unit that the
                # existing rungs already home (ente ``cli`` →
                # ``mint:entry-evidence``, onyx ``cli`` →
                # ``mint:dev-standalone``) never reaches it; only the
                # ancestor-annex class does (ollama ``cmd`` → ``app``,
                # unkey ``api`` → ``callback``, both later unbound by
                # 6.996 / 6.9971).
                _cli = _cli_supply(f) if _cli_by_dev else None
                if _cli is not None:
                    assignment[f.name] = _cli
                    tele["cli_supply_walk_blocked"] = (
                        tele.get("cli_supply_walk_blocked", 0) + 1)
                    continue
                assignment[f.name] = (target, f"fold:walk->{src}")
                tele["fold_ancestor_walk"] = (
                    tele.get("fold_ancestor_walk", 0) + 1)
                continue
            if guard_isolated:
                # fixb125 exit 3/4 — B22a CROSS-UNIT LANE. The guard is
                # right that no FOREIGN unit may take this dev; a
                # declared command surface means the dev has a product
                # right of its OWN, so it mints unit-locally instead of
                # laning (``cross_unit_isolation`` producer).
                _cli = _cli_supply(f) if _cli_by_dev else None
                if _cli is not None:
                    assignment[f.name] = _cli
                    tele["cli_supply_crossunit_blocked"] = (
                        tele.get("cli_supply_crossunit_blocked", 0) + 1)
                    continue
                # B22a — every walk target sits across a workspace-unit
                # boundary: the dev lanes WITH its own unit (whose shell
                # is already a lane resident) instead of poisoning a
                # foreign PF's owner map. Deliberately NOT counted as
                # ``law_flowful_in_lane`` — this is the guard's honest
                # refusal, not an assignment-less degenerate scan.
                tele["fold_walk_crossunit_laned"] = (
                    tele.get("fold_walk_crossunit_laned", 0) + 1)
                # B58 v3 — an artifact-homed dev lanes under its own
                # DISTINCT reason (the UF rollup's seeding guard keys on
                # it; generic B22a refusals keep the legacy reason).
                _home = _dev_home_unit(f) if _annex_on else None
                if (_home is not None and _art_tokens and any(
                        seg in _art_tokens
                        for seg in _home.lower().split("/"))):
                    infra[f.name] = _SHARED_REASON_DEV_ARTIFACT
                else:
                    infra[f.name] = _SHARED_REASON_CROSS_UNIT
                continue
        # fixb125 exit 4/4 — LANE FALLTHROUGH, restricted to the
        # ``no_anchor_lineage`` class (caddy ``cmd``, tracecat
        # ``tracecat-admin``, lobe-chat ``cli``): the unit has NO anchor
        # lineage at all and the command anchors are exactly the missing
        # lineage. A unit laned because an anchor claimed it and the
        # MINT BAR refused (``sub_mint_bar_surface`` — unkey
        # ``gha-fetch-digest``), or laned as a shell / instrument, is NOT
        # rescued here: this rung supplies lineage, it never overturns a
        # bar (which is what kept the CI-helper FP off the board).
        if reason == _SHARED_REASON_NONE and _cli_by_dev:
            _cli = _cli_supply(f)
            if _cli is not None:
                assignment[f.name] = _cli
                tele["cli_supply_lane_blocked"] = (
                    tele.get("cli_supply_lane_blocked", 0) + 1)
                continue
        if flowful:
            # Reachable ONLY on degenerate scans (zero mintable anchors,
            # or an assignment-less walk) — tracked so the smoke gates
            # can assert the law held (0 on every real product scan).
            tele["law_flowful_in_lane"] = (
                tele.get("law_flowful_in_lane", 0) + 1)
        infra[f.name] = reason

    # fixb125 — the supplied CLI anchors become mintable only NOW, after
    # every other dev's disposition is already decided (see
    # ``_cli_pending``): the rung promotes its own unit, never the board.
    for _cid in sorted(_cli_pending):
        mintable.add(_cid)
        bar_by_anchor[_cid] = None

    # fixb126 — supplied-tile LEAK CENSUS. The fence guards the two
    # plurality rungs the lobe-chat forensics measured (span + walk);
    # this counts what nonetheless ended up on a supplied tile through
    # some OTHER rung, so a residual channel is VISIBLE in telemetry
    # instead of silently re-growing the magnet. Bounded exhibit list.
    if _cli_pending:
        _leaks = sorted(
            (n, cid, prov) for n, (cid, prov) in assignment.items()
            if cid in _cli_pending and not str(prov).startswith("mint:cli-anchor")
            and _cli_supplied_foreign(cid, n)
        )
        if _leaks:
            _t = tele.setdefault("cli_anchor_supply", {})
            _t["magnet_leaks"] = [
                {"dev": n, "cid": cid, "prov": prov} for n, cid, prov in _leaks[:10]
            ]
            tele["cli_supply_magnet_leaked"] = len(_leaks)

    # B8c domain-fold rail (mint-time) — re-home flowful devs that folded
    # into a DISTINCT-domain host onto their own EXISTING <domain>-page
    # surface PF (the webhook 1→18 unification). Binds only to surfaces that
    # already receive a dev, so PF count cannot rise; same-domain and
    # surface-less routers stay folded. Runs AFTER the whole fold ladder so
    # every fold provenance (walk / import / span / …) is visible, and BEFORE
    # Pass 4 so the re-homed devs mint under the surface PF. Kill-switch
    # ``WYSTAN_MINT_DOMAIN_FOLD_V2=0`` skips it entirely (byte-identical).
    if mint_domain_fold_enabled():
        _rebind_dev_by_name = {f.name: f for f in in_scope}
        for _name, _surf_cid, _prov in _mint_domain_fold_rebinds(
                assignment, winner_by_dev, anchor_by_id, _rebind_dev_by_name):
            assignment[_name] = (_surf_cid, _prov)
            tele["mint_domain_fold_rebind"] = (
                tele.get("mint_domain_fold_rebind", 0) + 1)

    # Pass 4 — build the anchored product features.
    devs_by_anchor: dict[str, list["Feature"]] = defaultdict(list)
    dev_by_name = {f.name: f for f in in_scope}
    for name in sorted(assignment):
        cid, _prov = assignment[name]
        devs_by_anchor[cid].append(dev_by_name[name])

    product_features: list["Feature"] = []
    slug_by_anchor: dict[str, str] = {}
    # RESERVED legacy keys (W2b.1): every _SHARED_PF_KEYS consumer
    # (validator I9, surface-taxonomy shared-bucket exemptions, dashboard
    # lanes) treats a PF keyed ``platform``/``shared-platform`` as the
    # ABOLISHED shared bucket. A real anchor honestly named "platform"
    # (supabase docs) must therefore mint under a QUALIFIED slug — the
    # display keeps the author's word, the key stays out of the legacy
    # namespace.
    used_slugs: set[str] = {"platform", "shared-platform"}
    # B65-v4 iter-4 — spa slug sanitation (panel 'teams-(integration)'
    # exhibit): (a) a spa-paged anchor never STEALS the bare slug from a
    # same-display authored anchor — it sorts AFTER it (the tuple is
    # identical to the legacy key when no spa rows exist: byte-safe);
    # (b) when the QUALIFIED side of a display collision is spa-paged,
    # the qualifier joins WITHOUT parens ("Teams Pages", slug
    # ``teams-pages``) — canonical_slug parity holds (slug is still
    # derived from the display verbatim), no literal parens in a
    # spa-born name.
    for cid in sorted(
        devs_by_anchor,
        key=lambda c: (anchor_by_id[c].display.lower(),
                       bool(_spa_pages_of(anchor_by_id[c])), c),
    ):
        a = anchor_by_id[cid]
        contrib = devs_by_anchor[cid]
        # fixb125 addendum — a CLI PF's DISPLAY composes the surface token
        # ("<bin> CLI"), but its identity stays the AUTHOR's token: the
        # slug comes from the anchor key (the declared binary), not from
        # the composed label. Keeps ids stable across the addendum
        # (``ollama``/``lh``/``ods``, never ``ollama-cli``) and keeps the
        # 6.7d capability key aligned with the anchor.
        slug = _slug(a.key) if a.source == "cli" else _slug(a.display)
        display = a.display
        if slug in used_slugs:
            # Same display from two anchors (cross-FAMILY vendor clash —
            # RefApp airtable under both erp and iot_ot): qualify the
            # DISPLAY (dev_map / the 6.7d rebuild key capabilities by
            # display, so two live PFs sharing one display would
            # silently merge downstream) and derive the slug FROM the
            # qualified display via the SAME canonical_slug the 6.7d
            # rebuild uses (review F3: a hand-rolled `airtable-iot-ot`
            # diverged from canonical_slug("Airtable (Iot Ot)") =
            # `airtable-(iot-ot)`, voiding hub parity for exactly this
            # class and forking keyless-vs-keyed slugs).
            fam = getattr(a, "family_key", "") or ""
            qual = (fam.replace("-", " ").title() if fam
                    else re.sub(r"[^A-Za-z0-9]+", " ", cid).strip().title())
            # fixb134 M4a (WYSTAN_MINT_QUALIFIER_NO_SELF, default OFF) —
            # NEVER compose a self-restating pair. cal.com's app-store /
            # integrations dirs nest a same-name segment, so the derived
            # qualifier EQUALLED the base and the mint baked 'Alby (alby)'
            # into the display AND the slug (the join id). A qualifier that
            # restates its base disambiguates nothing; take a DISTINGUISHING
            # ancestor instead, else leave ``qual`` alone and let the
            # existing uniqueness ladder below do its job.
            if _mint_qualifier_no_self_enabled():
                from wystan.pipeline_v2.pf_display_doctrine import (
                    distinguishing_ancestor,
                    same_phrase,
                )

                if same_phrase(a.display, qual):
                    from wystan.pipeline_v2.lane_excavation import (
                        _m4a_record,
                    )
                    from wystan.pipeline_v2.pf_display_doctrine import (
                        polish_qualifier_word,
                    )

                    _alt = distinguishing_ancestor(cid, a.display)
                    _old_qual = qual
                    qual = polish_qualifier_word(_alt) if _alt else ""
                    _m4a_record(tele, "anchored_mint", a.display,
                                _old_qual, qual or None)
            if not qual:
                # No distinguishing ancestor — the uniqueness ladder owns it.
                display = _r5_canonical_compose(
                    f"{a.display} "
                    f"({re.sub(r'[^A-Za-z0-9]+', ' ', cid).strip().title()})")
                slug = _slug(display)
            elif _spa_pages_of(a):
                # iter-4 (b) — paren-free qualifier for spa-paged anchors
                display = f"{a.display} {qual}"
                slug = _slug(display)
                if slug in used_slugs:
                    display = (f"{a.display} "
                               f"{re.sub(r'[^A-Za-z0-9]+', ' ', cid).strip().title()}")
                    slug = _slug(display)
            else:
                display = _r5_canonical_compose(f"{a.display} ({qual})")
                slug = _slug(display)
                if slug in used_slugs:  # same qualified display twice — cid tail
                    display = _r5_canonical_compose(
                        f"{a.display} "
                        f"({re.sub(r'[^A-Za-z0-9]+', ' ', cid).strip().title()})")
                    slug = _slug(display)
        used_slugs.add(slug)
        slug_by_anchor[cid] = slug
        desc = (
            f"Capability anchored at {cid} "
            f"(sources: {', '.join(sorted(a.sources))}; "
            f"{len(contrib)} developer feature(s))."
        )
        pf = aggregate_product_feature(
            name=slug, display_name=display, description=desc,
            contrib=contrib,
        )
        pf.layer = "product"
        pf.anchor_id = cid
        # Carry the richer member_files ledger (dedup by path).
        seen_mf: set[str] = set()
        merged_mf: list[Any] = []
        for c in contrib:
            for mf in (getattr(c, "member_files", None) or []):
                mfp = (mf.get("path") if isinstance(mf, dict)
                       else getattr(mf, "path", None))
                if mfp and mfp not in seen_mf:
                    seen_mf.add(mfp)
                    merged_mf.append(mf)
        if merged_mf:
            pf.member_files = merged_mf
        product_features.append(pf)
    tele["pf_minted"] = len(product_features)

    # Pass 5 — stamp devs.
    for f in sorted(in_scope, key=lambda x: x.name):
        if f.name in assignment:
            cid, prov = assignment[f.name]
            f.product_feature_id = slug_by_anchor[cid]
            f.anchor_id = cid if prov == "lineage" else f"{prov}"
            if getattr(f, "shared_reason", None):
                f.shared_reason = None
        else:
            reason = infra.get(f.name, _SHARED_REASON_NONE)
            f.product_feature_id = None
            f.anchor_id = None
            f.shared_reason = reason
            tele["infra_lane"] += 1
            tele["infra_reasons"][reason] = tele["infra_reasons"].get(reason, 0) + 1
        if prev_stamp.get(f.name) != f.product_feature_id:
            tele["churn_devs"] += 1
    tele["churn_pct"] = round(tele["churn_devs"] / max(len(in_scope), 1), 4)

    # Hub-family stamps (sibling parity is re-asserted post-6.7d).
    fam_stamp: dict[str, str] = {}
    for cid in sorted(devs_by_anchor):
        a = anchor_by_id[cid]
        if a.source in {"hub-vendor", "hub-core"}:
            for f in devs_by_anchor[cid]:
                fam_stamp[f.name] = slug_by_anchor[cid]
    tele["hub_family_stamps"] = dict(sorted(fam_stamp.items()))
    fams: dict[str, dict[str, Any]] = {}
    for cid in sorted(devs_by_anchor):
        a = anchor_by_id[cid]
        if a.source == "hub-vendor" and a.hub_dir:
            fams.setdefault(a.hub_dir, {"vendors": [], "core": None})
            fams[a.hub_dir]["vendors"].append(a.vendor or a.key)
        elif a.source == "hub-core" and a.hub_dir:
            fams.setdefault(a.hub_dir, {"vendors": [], "core": None})
            fams[a.hub_dir]["core"] = slug_by_anchor[cid]
    tele["hub_families"] = [
        {"hub_dir": d, **v} for d, v in sorted(fams.items())
    ][:20]

    # Shared-consumer pass (amendment §2): the infra residents' files
    # surface as role="shared" members on every feature whose own code
    # imports them — the Stage 8.8 mechanism over the lane's file set.
    infra_devs = [dev_by_name[n] for n in sorted(infra)]
    if infra_devs:
        tele["shared_consumers"] = _attach_shared_consumers(
            ctx, in_scope, infra_devs, owned_by_dev)

    # B69-v2 — anchor-registry side-channel for the Stage 6.99b post-UF
    # rehome rail. The rail judges a journey's TRUE structural home by
    # anchor prefix breadth (mint-time truth), because the path_index →
    # dev → PF owner map the I16 rail uses is itself poisoned by the very
    # annexation being cured (papermark: dev 'datarooms' fold:entry into
    # the 'faq' anchor makes the annexed pages LOOK faqs-owned). Live
    # ``SpineAnchor`` objects — the finalize caller MUST pop this key
    # before tele reaches scan_meta / the stage artifact. Flag OFF ⇒ the
    # key is never attached ⇒ byte-identical.
    # B85 rider — the Stage 6.996 fold-evidence demote consumes the SAME
    # side-channel (static anchor evidence is its classification ground), so
    # the registry also attaches when the demote is armed with homing
    # hygiene off. Kill (either flag chain =0) restores the exact pre-rider
    # condition; the key is popped by the finalize caller either way (never
    # serialized) — byte-identity holds in every off-world.
    if homing_hygiene_enabled() or (
            fold_evidence_weight_enabled() and fold_evidence_demote_enabled()):
        tele["homing_hygiene_anchor_registry"] = dict(anchor_by_id)

    tele["applied"] = True
    # ── B105 FIX-2 — ``applied`` means the spine DECIDED the universe ──────
    # The bars can bar 100 % of the anchors (maybe: 35/35 schema: anchors,
    # meilisearch: 24/24 ws-* anchors — no route channel reached the
    # routes_index at all). The stage still ran, but it decided NOTHING: an
    # unconditional ``applied=True`` makes phase_finalize:714 swap the
    # deterministic clusterer's product layer for ``[]`` and hand 6.7d a
    # zero-entry ANCHORED capability list. Armed, an EMPTY mint on a
    # ``product-app`` unit reports the truth so the caller keeps the layer
    # it already had. Library / CLI / infra / framework units keep the
    # unconditional stamp — an empty product layer is the CORRECT answer
    # there (PF = user-usable doctrine), and the fail-open ``None`` class
    # keeps the status quo too. Flag OFF ⇒ no branch, no key, byte-identical.
    if mint_empty_honest_enabled() and not product_features:
        from wystan.pipeline_v2.stage_0_7_repo_class import (
            REPO_CLASS_PRODUCT_APP,
        )
        rc = repo_class if repo_class is not None else _scan_unit_repo_class(ctx)
        tele["mint_empty"] = True
        tele["mint_empty_repo_class"] = rc
        if rc == REPO_CLASS_PRODUCT_APP:
            tele["applied"] = False
            tele["mint_empty_anchors_barred"] = int(tele.get("anchors_total") or 0)
    return product_features, tele


def _slug(name: str) -> str:
    from wystan.pipeline_v2.emission_integrity import canonical_slug
    return canonical_slug(name)


# ── Shared-consumer attachment (8.8 mechanism over the infra lane) ───────


def _attach_shared_consumers(
    ctx: Any,
    in_scope: list["Feature"],
    infra_devs: list["Feature"],
    owned_by_dev: dict[str, list[str]],
) -> dict[str, int]:
    """Attach infra residents' files as ``role="shared"`` member_files on
    the features whose OWN code directly imports them. Reuses the Stage
    8.8 resolvers + its fan-out conduit guard; additive (member_files
    only), flow-immune."""
    from wystan.analyzer.tsconfig_paths import build_path_alias_map
    from wystan.models.types import MemberFile
    from wystan.pipeline_v2.stage_6_3_import_tree import (
        _PY_EXTS,
        _SourceCache,
        _TS_EXTS,
        _is_vendor_or_test,
        _suffix,
    )
    from wystan.pipeline_v2.stage_8_8_shared_members import (
        _fanout_cap,
        _resolve_one,
    )

    stats = {"files": 0, "edges": 0, "conduits": 0}
    residual: set[str] = set()
    for d in infra_devs:
        residual.update(owned_by_dev.get(d.name, ()))
    if not residual:
        return stats
    stats["files"] = len(residual)

    repo_path = Path(getattr(ctx, "repo_path", "."))
    tracked = frozenset(str(p) for p in (getattr(ctx, "tracked_files", None) or []))
    # R4 — adopt the ctx-shared source cache (fallback: local).
    from wystan.pipeline_v2.shared_source import shared_source_cache
    cache = shared_source_cache(ctx, repo_path) or _SourceCache(repo_path)
    try:
        alias_map = build_path_alias_map(repo_path)
    except Exception:  # noqa: BLE001
        alias_map = None

    infra_names = {d.name for d in infra_devs}
    consumers = [f for f in in_scope if f.name not in infra_names]
    imports_by_feature: dict[str, set[str]] = defaultdict(set)
    importers_by_file: dict[str, set[str]] = defaultdict(set)
    for f in consumers:
        for rel in owned_by_dev.get(f.name, ()):
            if _suffix(rel) not in (_TS_EXTS | _PY_EXTS) or _is_vendor_or_test(rel):
                continue
            try:
                specs = cache.imports(rel).values()
            except Exception:  # noqa: BLE001
                continue
            for spec in specs:
                tgt = _resolve_one(rel, spec, alias_map, tracked)
                if tgt is not None and tgt in residual:
                    imports_by_feature[f.name].add(tgt)
                    importers_by_file[tgt].add(f.name)

    cap = _fanout_cap([len(v) for v in importers_by_file.values()],
                      len(in_scope))
    conduits = {fp for fp, imp in importers_by_file.items() if len(imp) >= cap}
    stats["conduits"] = len(conduits)
    feat_by_name = {f.name: f for f in consumers}
    for fname in sorted(imports_by_feature):
        feat = feat_by_name[fname]
        existing = {
            (m.get("path") if isinstance(m, dict) else getattr(m, "path", None))
            for m in (feat.member_files or [])
        }
        for fp in sorted(imports_by_feature[fname]):
            if fp in conduits or fp in existing:
                continue
            feat.member_files.append(MemberFile(
                path=fp, role="shared", primary=False,
                confidence=0.5,
                evidence="spine-w2b: platform-infrastructure file "
                         "directly imported by this feature",
            ))
            stats["edges"] += 1
    return stats


# ── platform_infrastructure[] lane (amendment §3) ────────────────────────


def build_platform_infrastructure_lane(
    developer_features: list["Feature"],
    user_flows: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """Emission-time lane rows for the anchored residual: one entry PER
    resident dev (name, files, loc, reason). Zero-loss: residents stay
    in ``features[]`` (Layer-1 truth) with ``product_feature_id=None``;
    the lane is the explainability surface (I22 reads it post-W2b).

    B52 (``WYSTAN_FLOWFUL_TRANSPORT_LANE``): a FLOW-BEARING lane row
    (laned transport residue) additionally carries ``flow_ids[]`` (the
    resident's flow uuids, list order) and ``journeys[]`` (``{id, name}``
    of the ``user_flows[]`` rows whose ``lane_ref`` points at this row's
    uuid) — ADDITIVE, emitted ONLY when the flag is ON and the list is
    non-empty, so every existing board (including flowless documenso
    trpc) stays byte-identical."""
    from wystan.pipeline_v2.emission_integrity import ANCHORED_HUSK_REASON
    from wystan.pipeline_v2.transport_handoff import (
        FLOWFUL_LANE_ANCHOR,
        flowful_transport_lane_enabled,
    )

    flowful_lane = flowful_transport_lane_enabled()
    journeys_by_ref: dict[str, list[dict[str, Any]]] = {}
    if flowful_lane:
        for uf in (user_flows or []):
            ref = getattr(uf, "lane_ref", None)
            if ref:
                journeys_by_ref.setdefault(str(ref), []).append({
                    "id": getattr(uf, "id", None),
                    "name": getattr(uf, "name", None),
                })

    rows: list[dict[str, Any]] = []
    # The three amendment reasons the MINT stamps + the W4.2 additions:
    # the anchored-husk shell reason (emission_integrity unbinds a
    # dropped husk's 0-owned / 0-flow devs into this lane — zero-loss,
    # I22-visible) and the technology-instrument reason (Fix 1: dev
    # tooling lanes, never mints).
    lane_reasons = {_SHARED_REASON_NONE, _SHARED_REASON_BAR,
                    _SHARED_REASON_SHELL, ANCHORED_HUSK_REASON,
                    _SHARED_REASON_INSTRUMENT, _SHARED_REASON_INFRA_FANIN,
                    _SHARED_REASON_CROSS_UNIT,
                    # B58 debt (I22 dev-orphans): a pfid=None dev tagged
                    # ``dev_artifact_unit`` by the annexation guard's Seg-B
                    # bar is a lane resident, not an invisible orphan —
                    # emit its row. Byte-inert unless WYSTAN_ANNEXATION_
                    # GUARD is ON (the only tagger), so the all-OFF world
                    # is unchanged.
                    _SHARED_REASON_DEV_ARTIFACT}
    for f in developer_features:
        if getattr(f, "layer", "developer") != "developer":
            continue
        if getattr(f, "product_feature_id", None) is not None:
            continue
        reason = getattr(f, "shared_reason", None)
        # ONLY the reasons in the accepted set above (review F4): a
        # pfid=None dev some other stage tagged with a different reason
        # (non_product_surface / genuinely_shared_infra / facet_view) is
        # that stage's concern, never a lane resident.
        if reason not in lane_reasons:
            continue
        row: dict[str, Any] = {
            "name": f.name,
            "display_name": getattr(f, "display_name", None) or f.name,
            "shared_reason": reason,
            "uuid": getattr(f, "uuid", "") or "",
            "paths": list(getattr(f, "paths", None) or []),
            "loc": getattr(f, "loc", None),
            "loc_shared": getattr(f, "loc_shared", None),
            "flows": len(getattr(f, "flows", None) or []),
        }
        if flowful_lane:
            # B52 flow-bearing lane representation (additive; flow_ids
            # ONLY on rows whose dev the flowful-lane branch itself
            # laned — the provenance anchor — so a pre-existing flowful
            # resident (documenso openpage-api) stays byte-identical
            # under the flag, and flowless rows never change).
            if getattr(f, "anchor_id", None) == FLOWFUL_LANE_ANCHOR:
                fids = [str(getattr(fl, "uuid", "") or "")
                        for fl in (getattr(f, "flows", None) or [])]
                fids = [x for x in fids if x]
                if fids:
                    row["flow_ids"] = fids
            js = journeys_by_ref.get(row["uuid"])
            if js:
                row["journeys"] = js
        rows.append(row)
    rows.sort(key=lambda r: r["name"])
    return rows


# ── W4.2 — post-UF vendor-husk fold (D4's missing journey ruler) ─────────

_HUSK_POST_UF_ENV = "WYSTAN_HUSK_POST_UF_FOLD"


def husk_post_uf_fold_enabled() -> bool:
    """Default ON; ``WYSTAN_HUSK_POST_UF_FOLD=0`` disables."""
    return os.environ.get(_HUSK_POST_UF_ENV, "1").strip().lower() not in {
        "0", "false",
    }


def fold_unreferenced_vendor_husks(
    developer_features: list["Feature"],
    product_features: list["Feature"],
    user_flows: list[Any],
) -> dict[str, Any]:
    """W4.2 (operator exhibit: midday ``Enable Banking`` I8) — the D4
    vendor-husk rule gains the ruler it could not see at mint time: the
    JOURNEY layer.

    At Stage 6.86 the flowless hub-vendor floor is LOC-only (``≥ 150``
    mints — the valsem4 H9 bound; enablebanking's 1,162 real LOC passed
    it legitimately, no floor slip). But a flowless vendor child that the
    settled journey layer ALSO never cites is the operator's "a feature with
    no user flows" anomaly (validator I8's journeys-worthy prong): real
    code, no behavioral evidence, no journey — a standalone PF row tells
    a PM nothing its hub cannot. Post-UF (after 6.7d + every seed
    channel), such a child folds under its hub core sibling — or, when
    the family minted no core (midday's providers hub), the nearest
    enclosing minted capability (``Banking``) — exactly where D4 sends
    sub-floor husks at mint time. Runs BEFORE Stage 6.97, so dual-LOC
    accounting re-truths itself.

    Journey-cited children (midday ``gocardless``) and flow-evidenced
    children are untouched. Deterministic, $0. Kill-switch:
    ``WYSTAN_HUSK_POST_UF_FOLD=0``.
    """
    from wystan.pipeline_v2.hub_relation import HUB_PARENT_SEGMENTS

    tele: dict[str, Any] = {"enabled": True, "checked": 0, "folded": [],
                            "no_target": 0}
    if not husk_post_uf_fold_enabled():
        tele["enabled"] = False
        return tele

    uf_refs: Counter[str] = Counter()
    for uf in user_flows:
        ref = getattr(uf, "product_feature_id", None)
        if ref:
            uf_refs[str(ref)] += 1

    devs_by_pf: dict[str, list["Feature"]] = defaultdict(list)
    for f in developer_features:
        if getattr(f, "layer", "developer") != "developer":
            continue
        pfid = getattr(f, "product_feature_id", None)
        if pfid:
            devs_by_pf[str(pfid)].append(f)

    def _anchor_path(pf: "Feature") -> str | None:
        aid = str(getattr(pf, "anchor_id", None) or "")
        if ":" not in aid:
            return None
        return aid.split(":", 1)[1] or None

    def _seg_stem(seg: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", seg.lower())

    # Vendor-child candidates: hub: anchors whose PARENT dir basename is a
    # hub container segment (providers / integrations / connectors …) —
    # hub COREs (anchored at the container itself) never qualify.
    candidates: list["Feature"] = []
    for pf in sorted(product_features,
                     key=lambda p: str(getattr(p, "name", "") or "")):
        aid = str(getattr(pf, "anchor_id", None) or "")
        if not aid.startswith("hub:"):
            continue
        path = aid[4:]
        if "/" not in path:
            continue
        parent = path.rsplit("/", 1)[0]
        if _seg_stem(parent.rsplit("/", 1)[-1]) not in {
            _seg_stem(s) for s in HUB_PARENT_SEGMENTS
        }:
            continue
        tele["checked"] += 1
        key = str(getattr(pf, "name", "") or "")
        if uf_refs.get(key):
            continue  # journey-cited — a real board row
        members = devs_by_pf.get(key, [])
        if (getattr(pf, "flows", None) or []) or any(
            getattr(m, "flows", None) for m in members
        ):
            continue  # flow-evidenced — D4's mint-time verdict stands
        candidates.append(pf)
    if not candidates:
        return tele

    husk_keys = {str(getattr(pf, "name", "") or "") for pf in candidates}
    pf_by_key = {
        str(getattr(pf, "name", "") or ""): pf for pf in product_features
    }

    def _fold_target(pf: "Feature") -> "Feature | None":
        path = _anchor_path(pf) or ""
        parent = path.rsplit("/", 1)[0]
        # 1. the hub core sibling (anchored at the container itself);
        # 2. the LONGEST enclosing path-anchored capability (ws-pkg /
        #    fdir / pypkg subtree strictly containing the child).
        best: tuple[int, str] | None = None
        for other in product_features:
            okey = str(getattr(other, "name", "") or "")
            if okey in husk_keys or okey.strip().lower() in (
                "platform", "shared-platform",
            ):
                continue
            opath = _anchor_path(other)
            if not opath:
                continue
            if opath == parent or path.startswith(opath + "/"):
                cand = (len(opath), okey)
                if best is None or cand > best:
                    best = cand
        return pf_by_key.get(best[1]) if best else None

    folded_keys: set[str] = set()
    for pf in candidates:
        key = str(getattr(pf, "name", "") or "")
        target = _fold_target(pf)
        if target is None:
            tele["no_target"] += 1
            continue
        tkey = str(getattr(target, "name", "") or "")
        aid = str(getattr(pf, "anchor_id", None) or "")
        for m in devs_by_pf.get(key, []):
            m.product_feature_id = tkey
            m.anchor_id = f"fold:husk-post-uf->{aid}"
            if getattr(m, "shared_reason", None):
                m.shared_reason = None
        # paths + member_files union onto the target (dedup, stable order).
        seen_p = set(getattr(target, "paths", None) or [])
        merged_p = list(getattr(target, "paths", None) or [])
        for p in (getattr(pf, "paths", None) or []):
            if p not in seen_p:
                seen_p.add(p)
                merged_p.append(p)
        target.paths = merged_p
        seen_mf = {
            (mf.get("path") if isinstance(mf, dict)
             else getattr(mf, "path", None))
            for mf in (getattr(target, "member_files", None) or [])
        }
        for mf in (getattr(pf, "member_files", None) or []):
            mfp = (mf.get("path") if isinstance(mf, dict)
                   else getattr(mf, "path", None))
            if mfp and mfp not in seen_mf:
                seen_mf.add(mfp)
                target.member_files.append(mf)
        folded_keys.add(key)
        if len(tele["folded"]) < 25:
            tele["folded"].append({"pf": key, "into": tkey, "anchor": aid})

    if folded_keys:
        product_features[:] = [
            pf for pf in product_features
            if str(getattr(pf, "name", "") or "") not in folded_keys
        ]
    return tele


# ── Hub sibling parity (post-6.7d re-assert; replaces W1 inherit rule) ───


def enforce_hub_family_parity(
    developer_features: list["Feature"],
    product_features: list["Feature"],
    family_stamps: dict[str, str],
) -> dict[str, Any]:
    """Amendment §4: children of one hub are sibling PFs under a common
    parent, NEVER shared/scattered. The mint's family stamps are
    construction law — any later ladder that moved a family dev is
    re-stamped, and affected PF path unions are re-derived."""
    tele = {"checked": len(family_stamps), "restamped": 0}
    if not family_stamps:
        return tele
    pf_by_key: dict[str, "Feature"] = {}
    for pf in product_features:
        key = getattr(pf, "name", None) or ""
        if key:
            pf_by_key.setdefault(key, pf)
    affected: set[str] = set()
    for f in developer_features:
        want = family_stamps.get(getattr(f, "name", "") or "")
        if want is None or want not in pf_by_key:
            continue
        have = getattr(f, "product_feature_id", None)
        if have != want:
            if have and have in pf_by_key:
                affected.add(have)
            f.product_feature_id = want
            f.shared_reason = None
            affected.add(want)
            tele["restamped"] += 1
    if affected:
        members_by_pf: dict[str, list["Feature"]] = defaultdict(list)
        for f in developer_features:
            pid = getattr(f, "product_feature_id", None)
            if (pid and pid in affected
                    and getattr(f, "layer", "developer") == "developer"):
                members_by_pf[str(pid)].append(f)
        for key in sorted(affected):
            target_pf = pf_by_key.get(key)
            if target_pf is None:
                continue
            merged: list[str] = []
            seen: set[str] = set()
            for m in members_by_pf.get(key, []):
                for p in (getattr(m, "paths", None) or []):
                    if p not in seen:
                        seen.add(p)
                        merged.append(p)
            target_pf.paths = merged
    return tele
