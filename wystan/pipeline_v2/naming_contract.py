"""Stage 6.87 — display-name contract (Product-Spine §4.8, Wave 3).

SELECTION-not-generation: every product-feature / user-flow display name
is one of

  (a) a PIN from the previous scan (keeper channel — content-derived
      join by ``anchor_id`` / canonical slug; production rescans only,
      ``WYSTAN_KEEPER=0`` restores cold-scan purity for eval),
  (b) a ranked DETERMINISTIC candidate (authored nav labels, hub
      composition "<Family> — <Vendor>", humanized anchor segments,
      journey templates from flow-verb evidence, the current display),
  (c) a PM-Labeler pick from that candidate set (keyed scans only,
      Wave-3 persona) — validated against the documented grammar +
      token evidence and falling back to (b) on reject.

Identity ≠ display (hard law): this stage writes ONLY the display
channel — ``Feature.display_name`` on product features and
``UserFlow.name`` (the UF display channel) — plus telemetry. Canonical
identity — ``Feature.name`` slugs, ``anchor_id``, ``product_feature_id``,
UF ``id``/``uuid``/``resource``/``intent``, flow linkage — is NEVER
touched (fixture-equality + static grep-guard tests). Names are never
join keys downstream of this stage: it runs at the very end of finalize,
after 6.7d/hub-parity/emission-taxonomy, immediately before the
platform-infrastructure lane assembly and the Stage-7 output write.

Display-name laws (each deterministic, each with a fixture test):

  * ``single_letter`` — no 1-character display / 1-letter content word;
  * ``param`` — no route-param glyphs (``$ : { } [ ] < > *``);
  * ``file_stem`` — no ``schema.json``-class names (extension tokens);
  * ``pf_uf_twin`` — a UF display never exactly equals its own PF's
    display (journey phrasing: verb-led, from the journey grammar);
  * ``acronym_case`` — known acronyms render UPPERCASE (ERP, CLI, MCP)
    and known brands in canonical casing (GoCardless, tRPC) — vendor /
    dictionary aware, applied as a universal casing polish;
  * ``display_collision`` — two product PFs never share a case-folded
    display (the qualified form "<Base> (<Qualifier>)" disambiguates).

Kill-switch: ``WYSTAN_NAMING_CONTRACT=0`` (default ON) restores the
pre-W3 displays byte-identically. Vocabulary is data
(``data/naming-contract-vocab.yaml``; authoring copy ``eval/…``,
drift-guarded). Keyless scans take the deterministic top-choice path —
no LLM, byte-stable across runs (snapshot-gate property).
"""

from __future__ import annotations

import logging
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

from wystan.pipeline_v2.data import load_yaml
from wystan.pipeline_v2.fullname_expand import (
    apply_fullname_expansion,
    pf_fullname_law_enabled,
)
from wystan.pipeline_v2.manifest_display import (
    manifest_display_name,
    package_dir_of_anchor,
    pf_manifest_name_enabled,
    scope_identity_slug,
    word_split_slug,
)
from wystan.pipeline_v2.naming_wave_r5 import (
    MemberEvidence,
    brand_echo_pkg,
    build_board_evidence,
    canonicalize_compose,
    derive_split_display,
    glued_identifier,
    glued_lead_identifier,
    paren_qualifier_corroborated,
    pf_display_pool,
    plural_rename,
    r5_vocab_sets,
    trim_stranded_connective,
    unresolved_dir_token,
)
# fixb138 — the module-private fold is imported DELIBERATELY (not
# re-implemented): the verbless predicate must ask the verb table the exact
# same question ``unresolved_dir_token`` asks it (``_fold(toks[0]) in
# sets["verbs"]``). A local copy of the fold would be free to drift from the
# table's own key convention, and a predicate that folds differently from the
# table it queries is a silent false-negative generator.
from wystan.pipeline_v2.naming_wave_r5 import _fold as _r5_fold
from wystan.pipeline_v2.postmint_rescore import (
    postmint_rescore_enabled,
    verbless_no_high_enabled,
)
from wystan.pipeline_v2.ws_anchor_identity import (
    ws_anchor_identity_enabled,
)

logger = logging.getLogger(__name__)

__all__ = [
    "NAMING_CONTRACT_ENV",
    "NAMING_PACK_ENV",
    "NAMING_WAVE_R5_ENV",
    "SPRAY_GENERALIZED_ENV",
    "naming_wave_r5_enabled",
    "spray_generalized_enabled",
    "naming_pack_enabled",
    "HUMANIZE_ROUTE_NAMES_ENV",
    "PF_NAME_LAW_ENV",
    "UF_DEVGRAIN_NAME_ENV",
    "UF_NAME_DEGRIME_ENV",
    "UF_RESOURCE_RUNG_ENV",
    "UF_RUNG_SOURCES_V2_ENV",
    "UF_VERB_SNAP_ENV",
    "VERB_NAME_LEAD_STAMP_ENV",
    "verb_name_lead_stamp_enabled",
    "UF_COMPOSITE_HEAD_REPAIR_ENV",
    "NARROWED_RUBRIC_RESCORE_ENV",
    "UF_FLOW_VERB_CLASS_ENV",
    "uf_composite_head_repair_enabled",
    "narrowed_rubric_rescore_enabled",
    "uf_flow_verb_class_enabled",
    "composite_head_repair",
    "flow_verb_class_agreement",
    "naming_contract_enabled",
    "humanize_route_names_enabled",
    "pf_name_law_enabled",
    "uf_devgrain_name_enabled",
    "uf_name_degrime_enabled",
    "uf_resource_rung_enabled",
    "uf_rung_sources_v2_enabled",
    "uf_verb_snap_enabled",
    "homing_hygiene_enabled",
    "naming_law_enabled",
    "load_naming_vocab",
    "polish_display_casing",
    "display_law_violations",
    "degrime_rename_plan",
    "build_pf_candidates",
    "build_uf_candidates",
    "hub_composition_display",
    "humanize_anchor_display",
    "nav_labels_for_pfs",
    "nav_label_sets_for_pfs",
    "gated_nav_labels_for_pfs",
    "route_verb_indexes",
    "member_verb_composition",
    "run_naming_contract",
    "rescore_uf_confidence",
]

NAMING_CONTRACT_ENV = "WYSTAN_NAMING_CONTRACT"

#: B71 Seg A-C naming pack (default OFF). One flag gates the display-channel
#: laws (PF route-grammar + provenance, leaf-collision qualification, UF echo/
#: verb/family/uniqueness synth) and the degraded-scan confidence scoping.
NAMING_PACK_ENV = "WYSTAN_NAMING_PACK"

#: Display-cross evidence gate (B71 provenance-ladder consumer; default OFF).
#: A foreign authored nav label — one whose tokens are absent from BOTH the
#: PF's own name/anchor identity AND its member-dominant path tokens (cal
#: ``insights`` display 'Bookings', ``organization`` -> 'directory_sync') is
#: reverted so the ladder falls through to the honest basename; the surviving
#: label wins an anchor-page tie-break before alpha and is title-cased. DISPLAY
#: channel only — feeds ``ProvenanceSources.nav``; the B40 nav-pinning rung and
#: the B57 nav-cluster rung read the ungated votes and are untouched.
PF_DISPLAY_EVIDENCE_GATE_ENV = "WYSTAN_PF_DISPLAY_EVIDENCE_GATE"

#: R5 corpus naming-wave master flag (default ON since the 2026-07-21
#: pack-2 flip, KEY_SCHEMA 33; explicit =0 stays the kill-switch). One flag
#: gates the five R5 segments' NEW display-channel behaviors as one wave:
#:   * R5-1 identity-parity — a PF display that folds to ANOTHER live PF's
#:     canonical slug (or shares a folded display) is reject/qualified at the
#:     existing display-collision gate (the ``general`` -> 'Settings' remnant
#:     the merged display-cross-gate leaves grounded);
#:   * R5-2 own-resource templating (echo-hub siblings);
#:   * R5-3 member-evidence display derivation (dir-token humanization);
#:   * R5-4 compose-joint qualifier normalizer (all paren sites);
#:   * R5-5 negative confidence rungs (census-shape caps).
#: Segments may read their own sub-flags, but all fold under this master.
#: Unset/``0`` restores the pre-R5 emission byte-identically (KS 4-way gate).
#: Appended to ENV_OUTPUT_FLAGS WITHOUT a KEY_SCHEMA bump — the bump rides the
#: separate flip commit (flip-protocol).
NAMING_WAVE_R5_ENV = "WYSTAN_NAMING_WAVE_R5"

#: S2-A-v3 spray-generalization (default ON since the 2026-07-21 pack-3
#: flip, KEY_SCHEMA 34; explicit =0 stays the kill-switch). Generalizes
#: the R5-2 spray
#: predicate to the UNPARENTHESIZED tech-dir-suffix form the det-aggregation
#: regrain channel mints ('Manage setting AI components/constants/graphqls/
#: hooks/types/utils' — twenty-b exhibit, settings-PF 36 rows): same-PF
#: siblings sharing a >=2-token name prefix (G1) whose TAIL token names the
#: member paths' own leaf DIRECTORY (singular(tail) == singular(leaf-dir) on
#: >=50% member paths) are a dir-listing spray, not journeys. >=3 tail-matching
#: siblings fire the whole (PF, prefix) group — group-absorption also carries
#: the structural misses (graphqls/news) — into ONE own-resource parent row
#: ('Manage AI settings' form: intent + shared-subdir tokens + pluralized
#: root-dir token, never the bare prefix). Conservation by member union
#: (zero flow loss; I14 backpointer repoint). Class boundary: a paren-tail row
#: is R5-2's qualifier-spray class and is NEVER touched here (G0).
#: THIS module hosts the flag + the PREDICATE + the parent-name derivation
#: (beside the R5-2 machinery the G0 boundary fences); the STRUCTURAL apply
#: (member union, row drops, I14 repoints) lives in ``spray_absorption`` and
#: is wired in ``phase_finalize`` right AFTER the naming contract — the §4.8
#: identity law forbids identity writes inside the naming module.
#: Unset/``0`` keeps the pass un-entered ⇒ user_flows[] + telemetry
#: byte-identical (KS 4-way gate). Appended to ENV_OUTPUT_FLAGS WITHOUT a
#: KEY_SCHEMA bump — the bump rides the separate flip commit (flip-protocol).
SPRAY_GENERALIZED_ENV = "WYSTAN_SPRAY_GENERALIZED"

_VOCAB_FILE = "naming-contract-vocab.yaml"
_vocab_cache: dict[str, Any] | None = None

#: Route-param / template glyphs forbidden in any display name.
_PARAM_GLYPHS = re.compile(r"[$:{}\[\]<>*]")

#: Word split for casing polish — keeps separators so the display's
#: punctuation (spaces, " — ", parens) survives token replacement.
_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.\-]*")

#: Dynamic route-segment forms (mirrors spine_anchors._DYNAMIC_RE — all
#: dialects: ``[x]`` ``$x`` ``:x`` ``{x}`` ``<x>`` ``*x``).
_DYNAMIC_SEG = re.compile(r"^(\[+|[$:{<*])")

#: Route-group segment ``(marketing)`` — author-authored grouping word.
_GROUP_SEG = re.compile(r"^\((.+)\)$")

#: API-class transparent segments for humanization (same spirit as the
#: spine vocab's api transparency; bounded, universal).
_API_SEGS = frozenset({"api", "trpc", "rest", "graphql", "rpc"})

#: Version-dir segments (v1/v2 class) — never display words.
_VERSION_SEG = re.compile(r"^v\d+$", re.IGNORECASE)

#: Kill-switch for the route-template humanizer (B2). Default ON; ``=0``
#: restores the pre-B2 anchor humanization byte-identically (a route
#: display keeps whatever the legacy ``_meaningful_segments`` produced).
HUMANIZE_ROUTE_NAMES_ENV = "WYSTAN_HUMANIZE_ROUTE_NAMES"

#: B9 UF name laws kill-switch (default ON). ``=0`` restores base UF display
#: names + name_confidence byte-identically.
UF_NAME_LAWS_ENV = "WYSTAN_UF_NAME_LAWS"

#: B16 PF dev-grain suffix law kill-switch (default ON). ``=0`` restores the
#: pre-B16 PF display names byte-identically (a route-dir leak like
#: 'policy-page' keeps its "Policy Page" display).
PF_NAME_LAW_ENV = "WYSTAN_PF_NAME_LAW"

#: B16 Part-1b — UF-level dev-grain suffix law kill-switch (default ON). ``=0``
#: restores UserFlow.name to the pre-Part-1b output byte-identically (independent
#: of the merged PF law so each has its own clean kill-switch).
UF_DEVGRAIN_NAME_ENV = "WYSTAN_UF_DEVGRAIN_NAME"

#: B50 Seg1-2 — UF/PF display de-grime kill-switch (default **OFF**). At the
#: display JOINER it kills adjacent-token echoes ('Ingest ingest', 'View
#: views', 'case case ids', 'chat chatids' — Seg1) and glyph-less route-param
#: leaks ('teamurl documents', PF 'URL' — Seg2) in ``UserFlow.name`` /
#: ``Feature.display_name``. Display channel ONLY — identity / membership /
#: ``product_feature_id`` / paths / cluster keys / the ``resource`` field /
#: lineage are untouched. ``=1``/``true`` opts in; unset ⇒ display
#: byte-identical to pre-B50.
UF_NAME_DEGRIME_ENV = "WYSTAN_UF_NAME_DEGRIME"

#: B50 Seg3 — earned resource-grounding rung kill-switch (default **OFF**).
#: A low UF carrying ``missing:resource`` (verb IS grounded) earns
#: resource-grounding ONLY from a REAL evidence rung (member-file domain
#: noun / param-free route segment / mapped test-file noun), each stamping a
#: distinct ``name_evidence`` entry ('resource:member-noun' …). The Law-C
#: rubric bar is UNCHANGED — this ADDS OR-sources to ``res_grounded``, never
#: lowers a threshold, never invents ``missing:verb`` grounding.
#: ``CONFIDENCE`` channel only. Unset ⇒ confidence + serialized output
#: byte-identical.
UF_RESOURCE_RUNG_ENV = "WYSTAN_UF_RESOURCE_RUNG"

#: B57 Seg1 — deterministic rung-source expansion kill-switch (default
#: **OFF**). Four ADDITIONAL evidence sources for Law C's existing
#: resource/verb rungs, each a telemetered provenance-tagged OR-source
#: (the B50 Seg3 precedent — bar UNCHANGED, never a lowered threshold):
#:   (a) nav-cluster — ALL authored nav labels voted onto the UF's owning
#:       PF (not just the one top-voted label) may ground the resource;
#:   (b) i18n-key — i18n KEYS referenced in member SOURCE files
#:       (``t('billing_overview')`` / ``i18nKey=`` / ``getTranslation(``)
#:       ground the resource. KEYS ONLY: a key is identifier-shaped (no
#:       spaces); translated VALUES are a FORBIDDEN source (operator rule
#:       2026-07-13 — translations may live outside the repo; not
#:       structural truth), so anything space-broken is skipped and the
#:       ``product_strings`` VALUE channel is never consulted;
#:   (c) route-method — a member route's declared HTTP method grounds a
#:       matching verb-family lead (GET→browse/view, POST→create,
#:       PUT/PATCH→update, DELETE→delete — structural HTTP semantics,
#:       module-level frozen, not a repo vocabulary);
#:   (d) test-assert — assertion labels inside MAPPED member test files
#:       (``flow.test_files``, B36 member-overlap already holds) ground
#:       resource (non-verb token overlap) and/or verb (lead-verb family
#:       agreement).
#: CONFIDENCE/EVIDENCE channel only — UF NAMES are byte-stable either way
#: (the B40 law). Unset ⇒ confidence + serialized output byte-identical.
UF_RUNG_SOURCES_V2_ENV = "WYSTAN_UF_RUNG_SOURCES_V2"

#: B61 Seg1 — evidence-born verb-snap kill-switch (default **OFF**). A
#: deterministic post-pass that REPLACES a UF display's LEADING verb when
#: its action-family is ABSENT from the member VERB-COMPOSITION (B57
#: :func:`member_verb_composition` — the HTTP-methods / page-kinds the
#: member flows structurally imply). The lead verb is snapped to the
#: canonical verb of the composition's DOMINANT family (mutation families
#: outrank read — a mutation is the stronger claim the code makes); the
#: resource remainder, membership, identity, and lineage are untouched.
#:
#: This is the DISPLAY channel — and, unlike every rung/adjudicator flag,
#: it is the FIRST feature permitted to CHANGE a UF NAME. It therefore
#: carries its OWN kill-switch so the B40 "UF NAMES byte-stable" law under
#: ``WYSTAN_UF_RUNG_SOURCES_V2`` / ``WYSTAN_STAGE_6_7E_ADJUDICATOR``
#: is preserved intact: those flags STILL never change a name; only THIS
#: flag legally extends the law to a name-changing, still-deterministic,
#: still-$0 post-pass. NAME_CONFIDENCE is never written here — Law C scores
#: the snapped name via its existing ``structural:verb-composition`` rung
#: (so an earned high requires ``WYSTAN_UF_RUNG_SOURCES_V2`` co-armed,
#: as the keyed battery runs it). Iter2 rider (same flag): a GENERIC /
#: editorial lead with NO action family ('Manage …', 'Confirm …') is
#: verb-grounded by a NON-EMPTY member verb-composition — the exact mirror
#: of Law C's own generic clause (``lead is None and mfams >= 1``) with
#: route-structural facts as one more OR-source at the SAME bar (evidence
#: tag ``structural:verb-composition-generic``); such names are NEVER
#: snapped (no family conflict — nothing lies). SACRED: an EMPTY composition leaves the
#: name UNCHANGED (no facts → no claim → honest ``missing:verb``); a
#: mutation verb is assigned ONLY over a mutation composition (a GET-only
#: journey never earns a create/delete name); authored/pinned rows are
#: exempt; the snap is COLLISION-SAFE (B31 twin-protection — two rows
#: never snap to one name). Unset ⇒ names + confidence + serialized output
#: byte-identical.
UF_VERB_SNAP_ENV = "WYSTAN_UF_VERB_SNAP"

#: W1/C-A (2026-08-03) — ``verb:member-lead-echo``, ONE more OR-source for
#: Law C's verb channel (default **OFF**; the B50 Seg3 / B57 Seg1 precedent
#: — bar UNCHANGED, never a lowered threshold).
#:
#: The bug it repairs is an INVERSION, not a missing signal. A generated
#: flow name is verb-led BY CONTRACT (``flow_name_v2`` — "a flow name must
#: be a verb-led capability label (``manage-X-flow``), never a dir echo"),
#: and ``journey-action-families.yaml`` says of its own 99 verbs that they
#: are CORROBORATION ("the leading token of a generated flow name IS its
#: action (mechanism); the lists merely bucket that verb into a coarse
#: family"). Law C's base rubric nonetheless reads that list as an
#: EXISTENCE GATE: ``_flow_action_family`` returns ``None`` for any lead
#: outside the 99 words, so ``mfams`` comes back EMPTY (measured: 233/265
#: = 87.9% of the ``medium`` ∧ ``missing:verb`` rows on the plane / twenty
#: / supabase / cal.com boards) and ``base_verb`` cannot fire — 'Manage
#: sessions' over the member flow ``manage-session-flow`` scores
#: ``medium`` because ``manage`` is not in the vocabulary.
#:
#: This rung consumes the MECHANISM instead of the corroboration table:
#: the UF display's LEAD token, singular-folded by Law C's own ``_sing``,
#: equal to the LEAD token of at least one member flow name. Lead position
#: on BOTH sides is the whole discriminator — it is strictly STRONGER than
#: the family agreement ``base_verb`` already accepts (exact token identity
#: cannot cross families), so it can never over-claim: 'Run slugs' over
#: ``generate-slug-flow`` does NOT fire and stays honest ``missing:verb``.
#: Guarded against noun echoes — a token that is also a RESOURCE-phrase
#: token is a noun, never verb evidence (the mirror of
#: ``_grounds_resource``'s "a verb echo must never stand in for resource
#: evidence"). Vocabulary-free by construction: fixing this by adding
#: verbs to the YAML is the path the 2026-07-07 mechanisms-over-
#: vocabularies law forbids, and would silently re-partition the
#: ``journey_lattice`` ACTION axis (that file's primary consumer).
#:
#: CONFIDENCE/EVIDENCE channel only — UF NAMES are byte-stable either way
#: (the B40 law); no downgrade is reachable (an OR-source can only ADD a
#: grounding), and the synthesized cap (B78-it2) is evaluated BEFORE the
#: grading branches, so a backstop row still caps ``low``. The evidence
#: tag ``verb:member-lead-echo`` is stamped ONLY when this rung is the
#: NET-NEW verb grounding, so every row that was already ``high`` keeps a
#: byte-identical ``name_evidence``. Unset/=0 ⇒ confidence + evidence +
#: serialized output byte-identical. No KEY_SCHEMA bump (the flip is a
#: separate later commit per flip-protocol).
UF_MEMBER_LEAD_ECHO_ENV = "WYSTAN_UF_MEMBER_LEAD_ECHO"

#: C-B / fixb106 (2026-08-04) — ``verb:repo-umbrella-lead``, ONE more
#: OR-source for Law C's verb channel (default **OFF**; bar UNCHANGED).
#:
#: Law C's base rubric already has a generic clause — ``lead is None and
#: len(mfams) >= 1``: a lead that claims NO CRUD family ('Manage …') is an
#: UMBRELLA, it abstracts over whatever the members do instead of
#: over-claiming a specific verb, so ANY member action grounds it. That
#: clause dies on exactly the population W1 exposed: when the members'
#: own action verbs are OUT of the 99-word vocabulary, ``mfams`` is EMPTY
#: and the umbrella has nothing to abstract over — even though every
#: member IS verb-led by the flow-naming contract.
#:
#: This rung asks the one question that separates an umbrella from an
#: over-claim, and asks the REPO instead of a word list: is the UF's lead
#: token one this repository itself uses as an umbrella? The mechanism is
#: a repo-mined LEAD lexicon — the leading token of every flow name in
#: THIS repo, singular-folded by Law C's own ``_sing`` — and the floor is
#: scale-invariant:
#:
#:     ``lex[lead_tok] >= max(2, ceil(0.025 * len(flows)))``
#:
#: The absolute floor of 2 makes a one-off impossible; the 2.5% share
#: makes the rule read the SAME on a 90-flow repo and a 1600-flow one
#: (measured: ``manage`` = 10.1% on better-auth / 467 flows and 15.2% on
#: cal.com / 1456 flows — same verdict). At that floor the admitted set on
#: the KS54 world collapses to exactly ONE token, ``manage``, on 23
#: boards, and every over-claim is excluded BY THE MECHANISM, not by a
#: blocklist: 'Process mobile billing notifications' (``proces`` 5/560 =
#: 0.9%), 'Deploy databases' (``deploy`` 17/823 = 2.1%), ``monitor``,
#: ``select``, ``connect``, ``onboard``. Those six leads are out-of-family
#: too — the FLOOR is what excludes them, and it is the only thing that
#: does; a row whose lead DOES claim a CRUD family never reaches the rung
#: at all (the base rubric already demands a member perform that verb).
#: The same noun-echo guard as W1 applies: a lead token that is also a
#: RESOURCE-phrase token is the resource echoing itself, never an action
#: ('Track clicks…' ← resource ``track``).
#:
#: CONFIDENCE/EVIDENCE channel only — UF NAMES are byte-stable either way
#: (the B40 law), an OR-source can only ADD a grounding, and the
#: synthesized cap (B78-it2) is evaluated BEFORE the grading branches. The
#: tag ``verb:repo-umbrella-lead`` is stamped ONLY when this rung is the
#: NET-NEW verb grounding, so an already-``high`` row keeps a
#: byte-identical ``name_evidence``. Unset/=0 ⇒ confidence + evidence +
#: serialized output byte-identical. No KEY_SCHEMA bump (the flip is a
#: separate later commit per flip-protocol).
UF_UMBRELLA_FLOOR_ENV = "WYSTAN_UF_UMBRELLA_FLOOR"

#: The repo-mined umbrella floor's relative share (2.5% of the repo's flow
#: count). NOT a per-repo magic number: it is the knee measured on the
#: whole KS54 world (share 0.010 admits 7 lead tokens incl. three named
#: false positives, 0.020 still admits ``deploy``/``proces``, 0.025 and
#: 0.030 both collapse to ``manage``) and it is applied as a RATIO, so no
#: repository is special-cased. Paired with an absolute floor of 2.
#: Expressed PER MILLE so the floor is exact integer arithmetic — a float
#: literal would put a rounding surface under a threshold comparison.
_UMBRELLA_LEAD_PERMILLE = 25          # = 2.5 %
_UMBRELLA_LEAD_MIN = 2

#: fixb130 NS-E / NS-2-JS (2026-08-08) — SYNTH DISPLAY HYGIENE (default
#: **OFF**; ``=1`` arms it). Three shape laws every AUTHORED display already
#: passes, applied to the rows the mint writes verbatim.
#:
#: A synthesized journey takes its name from a PF display or a route-group
#: label with no display pass in between, so it ships shapes the contract
#: forbids everywhere else: 'Browse & manage server (server)' and 'Access
#: billing portal portal' (the phrase echo), 'Browse & manage scores
#: ( Project)' (a parenthetical opened on whitespace), and raw PascalCase
#: identifiers — 'AuthResponse' (strapi UF-003), 'View ApiTokens ListView'
#: (UF-044), 'Auth page Layout' (rallly UF-004) — which never even earn the
#: ``shape:raw-identifier`` stamp an authored row would wear, so the R5-5
#: cap cannot reach them.
#:
#: The echo law is the ADJACENT-ECHO segment of the de-grime, NOT the whole
#: of it. Measured on the KS66 world, full :func:`_degrime_display` over the
#: synth population repairs 6 rows and DAMAGES one — 'Unauthenticated user
#: should be redirected to target URL after login' (langfuse UF-152) loses
#: 'URL' to the standalone-addressing drop, and the same drop eats 'a UUID'
#: and 'controllers' on authored rows. The echo segment alone produces every
#: one of the 6 repairs and damages nothing.
#:
#: The paren-space law is whitespace only ('( Project)' -> '(Project)') and
#: therefore runs over EVERY row, synthesized or not — a space after an open
#: bracket cannot carry meaning. Unset/=0 ⇒ every display byte-identical.
SYNTH_DISPLAY_HYGIENE_ENV = "WYSTAN_SYNTH_DISPLAY_HYGIENE"

#: fixb130 / warden verdict #35 bonus pin (2026-08-08) — VIEW-LEAD PIN for
#: Law B's narrowing word (default **OFF**; ``=1`` arms it).
#:
#: ``journey-action-families.yaml`` folds 'view' into the ``browse`` family
#: unless an id-marker is present, so a cohort whose every member is
#: literally ``view-*-flow`` reaches the narrowing as ``mfams == {'browse'}``
#: and the rewrite says 'Browse <res>' over members that all say View
#: (novu / jsonhero). The members' own LEAD TOKEN is the mechanism those
#: families merely bucket — the W1 argument verbatim — so a unanimous 'view'
#: lead writes View.
#:
#: ARMED, not flagless: the change overturns a BANKED doctrine carrying
#: named tests (``test_read_only_over_claim_narrowed`` plus the fixb129
#: kill-switch / default-arm pair, all asserting 'Browse webhook' over
#: ``view-webhooks-flow``), and the fixb129 ruling is explicit that such a
#: change is a flip event and not a bugfix rider. Unset/=0 ⇒ every display
#: byte-identical.
UF_VIEW_LEAD_PIN_ENV = "WYSTAN_UF_VIEW_LEAD_PIN"

#: fixb132 (2026-08-09) — AUTHORED COMPONENT-NAME DE-GLUE at the UF layer
#: (default **ON** since flip-pack №37, KEY_SCHEMA 70; ``=0`` kills it).
#:
#: Next.js / React repos name their page components ``AdminTeamPage``, and
#: the journey layer ships the raw identifier as the journey NAME. Measured
#: on the umami KS68 board (58 UFs, 63.8% high): 19 PascalCase-glue rows —
#: 18 of them the ENTIRE ``shape:raw-identifier`` (C4) census class of that
#: board, every one graded ``high`` by Law C on its own evidence and then
#: capped to ``medium`` by the R5-5 sweep — plus 8 '<X> Page' rows shipping
#: ``high`` with a dev-grain word in the display. The cap is the honest
#: HALF of the cure (an unreadable name may not wear high); this flag arms
#: the other half — make the name readable, then let the ordinary rubric
#: grade it.
#:
#: DOCTRINE LINE (the load-bearing argument, drawn in full in
#: :mod:`wystan.pipeline_v2.uf_component_deglue`): NS-D ("the author's
#: high is sacred") protects the author's PRODUCT vocabulary — nav labels,
#: marketing phrasing. A CODE IDENTIFIER is not product vocabulary; it is
#: implementation naming with the legal status of a route segment, which
#: this engine already de-glues everywhere else (``uf_name_deglue``,
#: ``route_group_recall._humanize``, the ``_strip_uf_devgrain_suffix`` case
#: rung). The identifier-shape test runs FIRST, so only identifier-shaped
#: names enter the lane, and a display matching its PF's authored nav
#: phrasing is untouchable whatever its shape (NS-guard).
#:
#: NAME channel + the confidence Law C then derives FROM that name. The
#: lane itself never writes ``name_confidence``: it sits with the B50
#: deparam / R5-3 split-core lanes, i.e. the last rename before Law C, so
#: the row is graded on the name it ships (verb ∧ resource ⇒ high;
#: resource only ⇒ an honest ``medium`` with a readable name — a row may
#: legally stay medium). Verbs are never invented: rung (a) takes the
#: identifier's OWN lead word only when the fixb131 №34 modifier guard
#: says this repo writes it as an action AND the members ground that
#: family; rung (b) writes a READ verb only when the member composition
#: already grounds one; otherwise the phrase ships verbless — exactly the
#: lead-``None`` shape the identifier had. Unset/``0`` ⇒ every UF name,
#: confidence, evidence and telemetry key byte-identical (the kill-switch
#: law forever). Appended to ``ENV_OUTPUT_FLAGS`` WITHOUT a KEY_SCHEMA
#: bump — the bump rides the separate flip commit (flip-protocol).
UF_COMPONENT_NAME_DEGLUE_ENV = "WYSTAN_UF_COMPONENT_NAME_DEGLUE"

#: fixb107 Mechanism 1 (2026-08-05) — BRAND-CANONICAL EXEMPTION for the
#: R5-5 ``raw-identifier`` rung (default **OFF**; ``=1`` arms it).
#:
#: The class is a self-contradiction between two SHIPPED functions of THIS
#: module. :func:`polish_display_casing` mints the canonical vendor casing
#: from the ``brand_casing`` / ``known_acronyms`` YAML — 'connect github
#: for deployments' -> 'Connect GitHub for deployments' — and
#: :func:`_name_disease_shape` then reads the camel boundary the polish
#: just created as a leaked code identifier and caps the row to 'medium'.
#: The P7 census measured 32 such rows across the KS54 world, every one of
#: them a clean product name ('Deploy and manage PostgreSQL instances',
#: 'Send and inspect GraphQL requests', 'Query ClickHouse analytics').
#:
#: The exemption is TOKEN-SCOPED and reads the SAME vocabulary the polish
#: writes (one source of truth — never a second brand list): a camel/snake
#: boundary inside a token whose fold is a ``brand_casing`` key, a
#: ``brand_casing`` canonical value, or a ``known_acronyms`` member does
#: not count as a leak; a boundary anywhere else still does ('Authorize
#: GitHub IpAllowlist' stays capped on ``IpAllowlist``). It is a
#: FALL-THROUGH, not a rung skip: an exempted row keeps walking the
#: dir-token / glued / glued-lead / brand-echo rungs below, so a name whose
#: real disease is a glued lowercase compound is still caught by its own
#: rung. Unset/=0 ⇒ shape verdicts + confidence + serialized output
#: byte-identical. No KEY_SCHEMA bump (the flip is a separate later commit
#: per flip-protocol).
BRAND_SHAPE_EXEMPT_ENV = "WYSTAN_BRAND_SHAPE_EXEMPT"

#: fixb107 Mechanism 2 (2026-08-05) — PAREN-QUALIFIER ADMIT for the R5-5
#: ``paren-qualifier`` rung (default **OFF**; ``=1`` arms it).
#:
#: Law-B's uniqueness step MINTS parentheticals to disambiguate colliding
#: bases, and the R5-5 shape rung then caps every parenthesised display —
#: the engine punishing its own disambiguation. The census measured the
#: split: 0/72 capped rows are tautological echoes (B50-degrime already
#: killed that class), 58/72 carry a LIVE base collision on their board,
#: and 18/72 carry route/path/compose residue inside the bracket. Three
#: conjuncts admit the first population and keep the second capped:
#:
#: * **D1** product corroboration and **D2** residue guard —
#:   :func:`naming_wave_r5.paren_qualifier_corroborated` (41 rows, the
#:   census-exact set);
#: * **D3** base cleanliness — the BASE the qualifier disambiguates must
#:   itself be clean: no :func:`display_law_violations`, no raw-identifier
#:   shape, and no echo of the repository's own slug in its post-lead
#:   remainder. D3 is what keeps the four measured leaks capped (cal.com
#:   UF-051 'Manage new (webhooks)' and dub UF-112 'Connect register
#:   (domains)' — ``bare_verb`` bases; dub UF-L-f589b690f4 'View app dub
#:   co (Integration)' and onyx UF-L-9e78eecf51 'Manage onyx (Query And
#:   Chat)' — repo-slug echo bases). Their disease is the BASE, and a row
#:   whose base names nothing may not be promoted on the strength of a
#:   good qualifier.
#:
#: Admitting is a FALL-THROUGH: the row keeps walking every rung below, so
#: an admitted qualifier never rescues a name that is also glued, dir-token
#: or brand-echoing. NAME is never touched (display laws own it); only the
#: confidence grade + audit trail move. Unset/=0 ⇒ shape verdicts +
#: confidence + serialized output byte-identical. No KEY_SCHEMA bump (the
#: flip is a separate later commit per flip-protocol).
PAREN_QUALIFIER_ADMIT_ENV = "WYSTAN_PAREN_QUALIFIER_ADMIT"

#: B69-v2 — PF-homing hygiene family, FINAL composition (re-convoy
#: forensics ruling): the Stage 6.99b post-UF rehome rail (A′ + C′ rename +
#: home-tie guards) + the B31 pf-display echo-guard + the 6.7e Law-A
#: telemetry preservation. Default OFF; OFF ⇒ every consumer is skipped
#: and the serialized output is byte-identical to pre-B69-v2. SPLIT
#: rulings: the seed-birth pair lives under ``WYSTAN_SEED_HYGIENE``
#: (route_group_recall); the bare-verb/dev-grain-token display law lives
#: under ``WYSTAN_NAMING_LAW`` (banked — see its note below).
HOMING_HYGIENE_ENV = "WYSTAN_HOMING_HYGIENE"

#: B69-v2 third split → B70 member-evidence redesign — the bare-verb /
#: dev-grain-token display law. The keyed re-convoy proved the ORIGINAL
#: vocabulary-driven implementation violated the mechanisms-over-
#: vocabularies law: verb-class token lists banned healthy product resources
#: ('Manage download', 'Browse webhook', 'Connect auth' — download /
#: webhook / auth / verify / register all live in verb classes) while
#: MISSING the true exhibit ('View mupdf' — mupdf is in no vocabulary);
#: each ban cascaded retry → new names → collisions → B31 parentheticals
#: (= the entire off-rail churn of the keyed pair). B70 redesign (landed in
#: :func:`display_law_violations`): the strip STOPS at a token a row member
#: grounds (``member_tokens``) — a grounded verb-homonym is the resource,
#: not the action — and a nominal remainder no member backs is flagged
#: ``evidence_absent`` ('View mupdf' caught by evidence ABSENCE; 'Manage
#: download' lives by its route evidence). No member context at a call site
#: ⇒ the banked vocabulary behavior, unchanged. Default OFF ⇒ the law list
#: is byte-identical.
NAMING_LAW_ENV = "WYSTAN_NAMING_LAW"

#: Dev-grain surface nouns that must never TRAIL a product-feature display
#: when the route anchor's terminal dir segment leaked them (operator
#: doctrine: 'there is no such thing as a page in product features'). Anchor-
#: form-gated in :func:`_strip_pf_devgrain_suffix` — a display word here is
#: stripped ONLY when the anchor dir ends '-<word>' ('policy-page' ->
#: 'Policy'; 'investigation-flow' -> 'Investigation'). A capability that
#: merely CONTAINS one ('Landing Page Builder', anchor '*-builder') is never
#: touched. Fixed, scale-invariant vocabulary — corroboration, not tuning.
_PF_DEVGRAIN_SUFFIX_TOKENS = frozenset({"page", "screen", "view", "flow"})

#: Deterministic display word per action family (the labeler's lossy collapse
#: — two distinct action-family children both "Configure X" — is undone here).
_ACTION_FAMILY_WORD = {
    "browse": "Browse", "view": "View", "create": "Create",
    "update": "Update", "delete": "Delete", "act": "Manage",
}
#: Write families a name may not claim without a member performing that action.
_WRITE_FAMILIES = frozenset({"create", "update", "delete"})
#: Read families (collection vs member reads).
_READ_FAMILIES = frozenset({"browse", "view"})
#: Packaged action-family vocab file (same authoring copy the lattice uses;
#: loaded directly to avoid a circular import with journey_lattice).
_ACTION_FAMILIES_VOCAB_FILE = "journey-action-families.yaml"

#: A word-adjacent ``+`` (Remix flat-route folder nesting marker) or a
#: leading ``_`` word (pathless/layout prefix) that leaked into a display.
_TRAILING_PLUS_RE = re.compile(r"\w\+")

#: fixb133 M1 — route-MARKER display sanitize (N1 + N8), default **OFF**.
#: The router markers that no other rung ever stripped reach the DISPLAY
#: channel: intercepting routes ``(.)sessions``, parallel slots ``@modal``,
#: escaped literals ``robots[.]txt`` / ``[.]well-known``, regex-ish residue
#: ``[-htmltopdf]+``. Arms three things: (1) the residue DETECTOR also
#: grades marker shapes (so the B71 ladder stops calling ``(.)sessions`` a
#: clean basename), (2) the segment sanitizer in the display walk
#: (``route_markers.sanitize_segment``), (3) the junk-route-group veto —
#: an organisational group (``(use-page-wrapper)``, ``(main)``) is never a
#: display qualifier. DISPLAY channel only: ``pf.name`` / slugs / identity
#: / membership / ``route_groups_of`` metadata are untouched. Unset/``0``
#: ⇒ every display + telemetry byte-identical (explicit off stays a valid
#: kill-switch forever). Appended to ENV_OUTPUT_FLAGS WITHOUT a KEY_SCHEMA
#: bump — the bump rides the separate flip commit (flip-protocol).
ROUTE_MARKER_DISPLAY_SANITIZE_ENV = "WYSTAN_ROUTE_MARKER_DISPLAY_SANITIZE"

#: fixb133 M2 — the ``static-route-qualified`` B71 rung (N2 + N4 + N7),
#: default **OFF**. A single-word base whose meaning lives in its parent
#: gets the anchor's OWN evidence composed onto it: ``shares`` under
#: ``boards/[boardId]`` -> "Board Shares"; ``performance`` under
#: ``(reports)`` -> "Performance Report". Also arms the N7 stutter dedupe
#: at the hub compose site ("App Store — App Store — Attio" -> "App Store —
#: Attio"). The rung sits BELOW nav / package-manifest / schema-domain
#: (authored vocabulary is sacred) and only ever runs on a display the
#: ladder already graded defective. Unset/``0`` ⇒ byte-identical.
PF_ROUTE_QUALIFIER_RUNG_ENV = "WYSTAN_PF_ROUTE_QUALIFIER_RUNG"

#: fixb134 M4c — R5-1's identity-parity REPAIR may never return a
#: self-restating display, default **OFF**. The repair's first rung is the
#: humanized OWN slug, so on a row whose slug is still dirty
#: ('alby-(alby)' — M4b's emission migration runs LATER) it handed the
#: stutter straight back: this is the display the fixb133 R5-1 blocker
#: documented and that neither M4a (the stutter is not born at the mint on
#: this topology) nor M4b (wrong stage) can reach. Armed, a stuttering
#: candidate is refused and the row is repaired from a DISTINGUISHING
#: ancestor instead ('Alby (Integrations)'), which folds to
#: 'albyintegrations' != the sibling slug 'alby' — so identity-parity is
#: SATISFIED rather than weakened. Unset/``0`` ⇒ byte-identical.
R5_REPAIR_NO_SELF_ENV = "WYSTAN_R5_REPAIR_NO_SELF"

#: fixb133 M3 — the universal display lexicon (N3 + N6), default **OFF**.
#: A whole cleaned base that IS an opaque abbreviation or a deictic is
#: spelled out from ``data/display-lexicon.yaml`` (``sso`` -> "Single
#: Sign-On", ``me`` -> "My Account"), and a surviving initialism inside a
#: phrase renders uppercase (the ``SSO`` vs ``Utm`` split). WHOLE-segment
#: only, never substring — ``API Key`` keeps its name. Applied on
#: route-derived tiers only, so an authored nav/manifest label is never
#: rewritten. Unset/``0`` ⇒ byte-identical.
PF_DISPLAY_LEXICON_ENV = "WYSTAN_PF_DISPLAY_LEXICON"

#: fixb146 — the ARMED half of the display lexicon, default **OFF**.
#: The M3 lexicon (above) is already default ON, so a new row dropped
#: straight into ``expansions:`` would change shipped displays with NO
#: cache-key movement: ``compute_scan_cache_key`` hashes KEY_SCHEMA +
#: repo identity + engine version + the ENV_OUTPUT_FLAGS values, and the
#: lexicon FILE CONTENT is not among them (a warm cache would serve the
#: pre-edit board for a post-edit engine — the audit-Bug-2 poisoning
#: shape). KEY_SCHEMA may only move in a flip commit, so the honest
#: carrier for a lexicon ADDITION is its own flag: ``armed_expansions:``
#: rows are merged over ``expansions:`` only while this is truthy.
#: Unset/``0`` ⇒ the lexicon is exactly the pre-fixb146 table ⇒ every
#: display byte-identical. The flip commit promotes the armed rows into
#: ``expansions:`` and carries the KEY_SCHEMA bump.
PF_LEXICON_ARMED_ENV = "WYSTAN_PF_LEXICON_ARMED"


def naming_contract_enabled() -> bool:
    """Default ON; ``WYSTAN_NAMING_CONTRACT=0`` restores pre-W3 output."""
    return os.environ.get(NAMING_CONTRACT_ENV, "1").strip().lower() not in {
        "0", "false",
    }


def naming_pack_enabled() -> bool:
    """B71 Seg A-C naming pack. Default **ON** since the 2026-07-16 horizon-1
    flip (KEY_SCHEMA 30; keyed proof documenso + novu green — echo-fold in the
    rich boards, anti-cases live). Arms the display + confidence laws.
    ``WYSTAN_NAMING_PACK=0`` keeps every naming channel byte-identical (the
    kill-switch law forever; unset ≡ explicit ``1``)."""
    return os.environ.get(NAMING_PACK_ENV, "1").strip().lower() in {"1", "true"}


def pf_display_evidence_gate_enabled() -> bool:
    """Display-cross evidence gate over the PF provenance ladder's nav
    channel (B71 consumer). Default **ON** since the 2026-07-21 pack-2
    flip (KEY_SCHEMA 33; keyed proof cal + novu green — sim==engine 7/21
    exact, cal 5→0 false displays, novu footprint exactly 1 row): an
    authored nav label only becomes a PF display when its tokens intersect
    the PF's name/anchor-terminal identity OR its member-dominant path
    tokens; equal-vote ties prefer the label whose href lands on the PF's
    own anchor page before alpha; the surviving label is title-cased.
    Unset ≡ explicit ``1``; explicit ``=0``/``false`` keeps
    ``ProvenanceSources.nav`` — and therefore the emitted display — byte
    identical (explicit off stays a valid kill-switch forever)."""
    return os.environ.get(
        PF_DISPLAY_EVIDENCE_GATE_ENV, "1"
    ).strip().lower() in {"1", "true"}


def naming_wave_r5_enabled() -> bool:
    """R5 corpus naming-wave master. Default **ON** since the 2026-07-21
    pack-2 flip (KEY_SCHEMA 33; keyed A/B twenty + papermark green —
    phase-1 cures hold: paren-high 17→0, dups 3→0; brand-echo stamps ×5,
    measured demote high 101→92, no over-demotion on the keyed PF layer).
    Unset ≡ explicit ``1`` — every R5 segment armed; explicit ``0``/
    ``false``/``off`` keeps each segment inert ⇒ display + telemetry
    byte-identical to pre-R5 (explicit off stays a valid kill-switch
    forever)."""
    return os.environ.get(
        NAMING_WAVE_R5_ENV, "1"
    ).strip().lower() in {"1", "true"}


def brand_shape_exempt_enabled() -> bool:
    """fixb107 Mechanism 1 — brand-canonical exemption for the R5-5
    ``raw-identifier`` rung. Default **OFF**; ``=1``/``true`` arms it.
    Unset/=0 ⇒ every shape verdict, confidence and serialized output
    byte-identical (explicit off stays a valid kill-switch forever)."""
    return os.environ.get(BRAND_SHAPE_EXEMPT_ENV, "1").strip().lower() in {
        "1", "true",
    }


def paren_qualifier_admit_enabled() -> bool:
    """fixb107 Mechanism 2 — D1^D2^D3 admit for the R5-5
    ``paren-qualifier`` rung. Default **OFF**; ``=1``/``true`` arms it.
    Unset/=0 ⇒ every shape verdict, confidence and serialized output
    byte-identical (explicit off stays a valid kill-switch forever)."""
    return os.environ.get(PAREN_QUALIFIER_ADMIT_ENV, "1").strip().lower() in {
        "1", "true",
    }


def route_marker_display_sanitize_enabled() -> bool:
    """fixb133 M1 — route-marker display sanitize. Default **ON** since the
    2026-08-09 pack-№35 flip (KEY_SCHEMA 68; warden №38 GO — umami 11/11
    green incl. 'Settings Profile', cal.com zero junk-paren, 'CalDav
    (Beta)' and 'Social Providers — Apple' alive). Unset ≡ explicit ``1``;
    explicit ``0``/``false`` keeps every display and telemetry
    byte-identical to the pre-fixb133 engine (the kill-switch law
    forever). The truthy set is preserved LITERALLY — only the
    ``os.environ.get`` default moved ``"0"`` -> ``"1"``."""
    return os.environ.get(
        ROUTE_MARKER_DISPLAY_SANITIZE_ENV, "1"
    ).strip().lower() in {"1", "true"}


def pf_route_qualifier_rung_enabled() -> bool:
    """fixb133 M2 — the ``static-route-qualified`` rung, the N7 stutter
    dedupe, and the qualifier-token isolation the attribution consumers
    read. Default **ON** since the 2026-08-09 pack-№35 flip (KEY_SCHEMA 68;
    warden №38 GO — 'Board Shares' / 'Performance Report' / 'App Setup'
    live, UF-046 stays on websites, 'Attributes' gains no access-control
    group). Unset ≡ explicit ``1``; explicit ``0``/``false`` keeps every
    display, every consumer token set and all telemetry byte-identical to
    the pre-fixb133 engine (the kill-switch law forever). The truthy set is
    preserved LITERALLY — only the default moved ``"0"`` -> ``"1"``."""
    return os.environ.get(
        PF_ROUTE_QUALIFIER_RUNG_ENV, "1"
    ).strip().lower() in {"1", "true"}


def r5_repair_no_self_enabled() -> bool:
    """fixb134 M4c gate — see :data:`R5_REPAIR_NO_SELF_ENV`. Default **ON**
    since the 2026-08-09 pack-№36 flip (KEY_SCHEMA 69; warden №40 GO —
    cal.com 'Alby (alby)' -> 'Alby (Integrations)', parity satisfied not
    weakened). Unset ≡ explicit ``1``; explicit ``0``/``false`` ⇒ every
    identity-parity repair byte-identical (kill-switch forever). The truthy
    set is preserved LITERALLY — only the default moved ``"0"`` -> ``"1"``."""
    return os.environ.get(
        R5_REPAIR_NO_SELF_ENV, "1"
    ).strip().lower() in {"1", "true"}


def pf_display_lexicon_enabled() -> bool:
    """fixb133 M3 — the universal display lexicon + acronym-casing unify.
    Default **ON** since the 2026-08-09 pack-№35 flip (KEY_SCHEMA 68;
    warden №38 GO — 'Single Sign-On' / 'UTM Campaigns' / 'My Account' live,
    'API Key' byte-identical, authored nav labels untouched). Unset ≡
    explicit ``1``; explicit ``0``/``false`` keeps every display
    byte-identical to the pre-fixb133 engine (the kill-switch law
    forever). The truthy set is preserved LITERALLY — only the default
    moved ``"0"`` -> ``"1"``."""
    return os.environ.get(
        PF_DISPLAY_LEXICON_ENV, "1"
    ).strip().lower() in {"1", "true"}


def pf_lexicon_armed_enabled() -> bool:
    """fixb146 — merge ``armed_expansions:`` into the M3 lexicon table.

    Default **OFF**: an addition to a table whose applier already ships ON
    would otherwise move displays with a STILL-IDENTICAL cache key (the
    lexicon file is not hashed into ``compute_scan_cache_key``), and the
    KEY_SCHEMA bump that would honestly invalidate those caches belongs to
    the flip commit alone. Unset/``0`` ⇒ ``_expansions()`` is exactly the
    pre-fixb146 table ⇒ every display byte-identical. Truthy set matches
    every other flag in this module (``1``/``true``)."""
    return os.environ.get(
        PF_LEXICON_ARMED_ENV, "0"
    ).strip().lower() in {"1", "true"}


def spray_generalized_enabled() -> bool:
    """S2-A-v3 spray-generalization — default **ON** since the 2026-07-21
    pack-3 flip (KEY_SCHEMA 34; census twenty (R5+DET_AGG world) — spray
    17→0, parents 'Manage AI settings' mc38 / 'Manage application
    settings' mc52 / 'Manage data model settings' mc25, settings-PF
    36→22, conservation 328==328, 0 false, I14 dangling 0; KS byte-ident
    typebot+openstatus; the pair flag of WYSTAN_UF_DET_AGGREGATION —
    ledger §S2-A-V3). Unset ≡ explicit ``1``; explicit ``0``/``false``/
    ``off`` keeps the pass un-entered ⇒ user_flows[] + telemetry
    byte-identical (explicit off stays a valid kill-switch forever)."""
    return os.environ.get(
        SPRAY_GENERALIZED_ENV, "1"
    ).strip().lower() in {"1", "true"}


def uf_name_laws_enabled() -> bool:
    """UF name laws (B9): name-claim narrowing + UF-vs-UF display uniqueness +
    evidence-derived name_confidence, applied over FINAL members at emission.
    Default ON; ``WYSTAN_UF_NAME_LAWS=0`` restores the base display names +
    name_confidence byte-identically."""
    return os.environ.get(UF_NAME_LAWS_ENV, "1").strip().lower() not in {
        "0", "false",
    }


#: B40 name-evidence rungs kill-switch (default ON — flipped 2026-07-12 after
#: the keyed proof on papermark + cal.com; KEY_SCHEMA v27). Arms the
#: provenance ladder (nav / registry / structural-route corroboration +
#: singular-folded multi-member agreement) in Law C + synth_quality and stamps
#: ``UserFlow.name_evidence``. ``=0`` restores the pre-B40 confidence rubric
#: AND serialized output byte-identically (only name_confidence/name_evidence
#: may ever differ under ON — UF NAMES are byte-stable either way).
NAME_EVIDENCE_RUNGS_ENV = "WYSTAN_NAME_EVIDENCE_RUNGS"

#: fixb138 / NS-43b Half 2 — the ``verb:name-lead`` evidence-honesty stamp.
#: Default **ON** (flip-pack #40, KEY_SCHEMA 74). A verb-LED journey name
#: whose evidence carries no ``verb:*`` tag gets one: Law C's ``base_verb``
#: grounded the row through the coarse ``structural-route`` rung and never
#: minted a granular tag, so the evidence UNDERSTATED a correct grade.
#: CORROBORATION-ONLY by construction — the stamp rides a HIT in the
#: engine's own verb table, so it can never fire on a word the table does
#: not know. Grade-independent (a verb-led ``low`` is stamped and stays
#: ``low``) and grade-INERT: this flag never moves a confidence, it only
#: ever appends one evidence tag. ``=0`` is the kill-switch forever and
#: restores the pre-flip ``name_evidence`` byte-identically.
VERB_NAME_LEAD_STAMP_ENV = "WYSTAN_VERB_NAME_LEAD_STAMP"


def verb_name_lead_stamp_enabled() -> bool:
    """fixb138 Half 2 — see :data:`VERB_NAME_LEAD_STAMP_ENV`."""
    return os.environ.get(
        VERB_NAME_LEAD_STAMP_ENV, "1"
    ).strip().lower() not in {"0", "false"}


#: fixb142 Part 1 — composite-head repair (DISPLAY channel). Default **OFF**.
#: A journey named '<V1> and <V2> <resource>' whose LEAD family no member
#: witnesses, while a head-adjacent conjunct's family IS witnessed, has its
#: unwitnessed conjuncts dropped ('Create and edit analytics' → 'Edit
#: analytics'). Law B doctrine, applied to the composite shape the existing
#: narrowing does not reach. ``=0`` is the kill-switch forever: names +
#: confidence + evidence + serialized output byte-identical.
UF_COMPOSITE_HEAD_REPAIR_ENV = "WYSTAN_UF_COMPOSITE_HEAD_REPAIR"

#: fixb142 Part 2 — make the fixb129 narrowed-normal rubric reachable from
#: the NON-primary Law C seams. Default **ON** (flip-pack #42, KEY_SCHEMA
#: 77). See :func:`narrowed_rubric_rescore_enabled` for why this is not
#: simply deleting ``and primary_pass``. ``=0`` is the kill-switch forever.
NARROWED_RUBRIC_RESCORE_ENV = "WYSTAN_NARROWED_RUBRIC_RESCORE"

#: fixb142 Part 3 — the ``flow_verb_classes`` second axis as one more
#: OR-source to Law C's ``verb_grounded``. Default **OFF**. Bar UNCHANGED
#: (an added source, never a lowered threshold); ``=0`` ⇒ confidence +
#: evidence + serialized output byte-identical.
UF_FLOW_VERB_CLASS_ENV = "WYSTAN_UF_FLOW_VERB_CLASS"


def uf_composite_head_repair_enabled() -> bool:
    """fixb142 Part 1 — see :data:`UF_COMPOSITE_HEAD_REPAIR_ENV`."""
    return os.environ.get(
        UF_COMPOSITE_HEAD_REPAIR_ENV, "0"
    ).strip().lower() in {"1", "true", "on"}


def narrowed_rubric_rescore_enabled() -> bool:
    """fixb142 Part 2 — default **ON** (flip-pack #42, KEY_SCHEMA 77).
    Extends the fixb129 rubric past the primary pass, WITHOUT reopening
    what fixb130 item (6) closed.

    THE DEFECT. ``_apply_uf_name_laws`` runs in the primary naming pass and
    again in every post-mint rescore seam (``postmint_uf_rescore`` /
    6.7e). fixb130 scoped the fixb129 cure to ``primary_pass`` only, so in
    a rescore the narrowed row falls back to the hard ``low`` +
    ``['missing:verb']`` stamp. Measured 2026-08-11 on the KS75 world:
    SEVEN rows carry that stamp while ``lead in mfams`` — i.e. the engine
    asserts a verb is missing on rows whose verb its own evidence
    witnesses. The class is byte-identical to the KS66 measurement (7 → 7)
    even though the fixb129 flag has been default-ON since pack #34: the
    cure never reached the seam that writes the FINAL grade. jsonhero
    ``UF-004`` is the live exhibit — ``naming_contract`` telemetry ends at
    ``{high: 11, medium: 0, low: 0}`` and ``postmint_rescore.flow_name_v2``
    (``rows_down: 1``) then re-stamps it ``low``.

    WHY NOT JUST DROP ``and primary_pass``. fixb130's argument is sound and
    stays honoured: a rescore hook exists to REPORT what a producer's
    membership change did, and a hook that only ever upgrades is dishonest
    (banked by ``test_jsonhero_uf004_create_item_demotes_honestly`` /
    ``test_novu_uf056_edit_context_demotes_honestly``). So this flag pairs
    the rubric with a NO-CLIMB clamp: outside the primary pass a narrowed
    row is scored by the ordinary rubric — which is the only way to stop
    lying about the verb — but its result is clamped to at most the
    confidence it CARRIED INTO the hook. It can fall, it can stay, it can
    never climb. That is verbatim the contract fixb130's own comment
    states; the pre-fixb142 code implemented it as a ``low`` FLOOR instead,
    which is a different (and false) statement.

    ``=0`` is the kill-switch forever — confidence + evidence + serialized
    output byte-identical to the pre-fixb142 seam behaviour.
    """
    return os.environ.get(
        NARROWED_RUBRIC_RESCORE_ENV, "1"
    ).strip().lower() in {"1", "true", "on"}


def uf_flow_verb_class_enabled() -> bool:
    """fixb142 Part 3 — see :data:`UF_FLOW_VERB_CLASS_ENV`."""
    return os.environ.get(
        UF_FLOW_VERB_CLASS_ENV, "0"
    ).strip().lower() in {"1", "true", "on"}


def humanize_route_names_enabled() -> bool:
    """Default ON; ``WYSTAN_HUMANIZE_ROUTE_NAMES=0`` restores the pre-B2
    anchor humanization (byte-identical route display names)."""
    return os.environ.get(HUMANIZE_ROUTE_NAMES_ENV, "1").strip().lower() not in {
        "0", "false",
    }


def name_evidence_rungs_enabled() -> bool:
    """B40 provenance-graded confidence + ``name_evidence`` audit trail.
    Default ON (flipped 2026-07-12 after the keyed proof on papermark +
    cal.com; KEY_SCHEMA v27): unset arms the nav / registry / structural-route
    rungs (Law C) and the singular-folded member-agreement widening
    (synth_quality). ``WYSTAN_NAME_EVIDENCE_RUNGS=0`` restores the pre-B40
    rubric + serialized output byte-identically (``name_evidence`` stays
    ``None`` everywhere)."""
    return os.environ.get(NAME_EVIDENCE_RUNGS_ENV, "1").strip().lower() not in {
        "0", "false",
    }


def pf_name_law_enabled() -> bool:
    """PF dev-grain suffix law (B16): a route-dir-naming leak
    ('policy-page' -> 'Policy Page') is stripped to the capability
    ('Policy') at the display channel. Default ON;
    ``WYSTAN_PF_NAME_LAW=0`` restores the pre-B16 PF displays
    byte-identically."""
    return os.environ.get(PF_NAME_LAW_ENV, "1").strip().lower() not in {
        "0", "false",
    }


def uf_devgrain_name_enabled() -> bool:
    """B16 Part-1b — strip a dev-grain suffix from ``UserFlow.name`` ("View
    detections page" -> "View detections") when the journey's home PF anchor
    is a route:*-page leak. Default ON; ``WYSTAN_UF_DEVGRAIN_NAME=0``
    restores the pre-Part-1b UF names byte-identically."""
    return os.environ.get(UF_DEVGRAIN_NAME_ENV, "1").strip().lower() not in {
        "0", "false",
    }


def uf_view_lead_pin_enabled() -> bool:
    """fixb130 Law-B view-lead pin. Default **OFF** (armed):
    ``WYSTAN_UF_VIEW_LEAD_PIN=1`` lets a unanimous ``view-*`` member
    cohort write 'View <res>' instead of 'Browse <res>'. Unset/``0`` ⇒
    byte-identical."""
    return os.environ.get(
        UF_VIEW_LEAD_PIN_ENV, "1").strip().lower() in {"1", "true"}


def _dg_fold_oracle_refuse(
    proposals: Mapping[str, str],
    ordered: list[Any],
    eligible: list[Any],
    product_features: list[Any],
    flows: list[Any],
    verbs: frozenset[str],
    tele: dict[str, Any],
    *,
    max_rounds: int = 8,
) -> set[str]:
    """fixb136 — the EXACT fold-neutrality oracle: which of ``proposals``
    would ADD a ``uf_synth_fold`` fold that the current names do not have?

    Asks the fold's own planner twice (current names, then proposed names)
    and attributes every NEW ``loser -> winner`` pair back to a proposal:
    the LOSER's rename first (its name is what made it foldable), else the
    WINNER's (its name is what made it an attractor). Iterates because
    dropping one proposal can change the plan again; bounded, and on an
    unconverged board it refuses EVERY remaining proposal — a lost rename
    is a cosmetic miss, a lost journey is a conservation stop.

    Restores every name it borrowed, in a ``finally`` — this function must
    leave the board exactly as it found it.
    """
    from wystan.pipeline_v2.uf_synth_fold import plan_uf_synth

    by_id = {str(getattr(u, "id", "") or ""): u for u in ordered}
    saved = {uid: getattr(u, "name", None) for uid, u in by_id.items()}

    def _fold_pairs(active: Mapping[str, str]) -> set[tuple[str, str]]:
        try:
            for uid, name in active.items():
                if uid in by_id:
                    by_id[uid].name = name
            # The oracle plans against the SAME exemption the fold will
            # actually hold — one source, never a promise: the rows this
            # scan already registered PLUS the ones under test.
            from wystan.pipeline_v2.uf_component_deglue import (
                renamed_in_scan,
            )
            plan = plan_uf_synth(
                list(eligible), list(flows), list(product_features), verbs,
                fold_exempt_ids=frozenset(active) | renamed_in_scan())
            return {(str(a), str(b)) for a, b in plan.fold.items()}
        finally:
            for uid, saved_name in saved.items():
                by_id[uid].name = saved_name

    base = _fold_pairs({})
    live = dict(proposals)
    refused: set[str] = set()
    rounds = 0
    while live:
        rounds += 1
        new = _fold_pairs(live) - base
        if not new:
            break
        if rounds > max_rounds:                     # pragma: no cover
            tele["uf_component_deglue_oracle_bailout"] = len(live)
            refused.update(live)
            break
        blamed: set[str] = set()
        for loser, winner in sorted(new):
            if loser in live:
                blamed.add(loser)
            elif winner in live:
                blamed.add(winner)
        if not blamed:
            # a new fold no proposal can be blamed for — refuse them all
            # rather than ship a journey deletion we cannot attribute.
            tele["uf_component_deglue_oracle_unattributed"] = len(new)
            refused.update(live)
            break
        refused |= blamed
        for uid in blamed:
            live.pop(uid, None)
    tele["uf_component_deglue_oracle_rounds"] = rounds
    return refused


def _uppercase_lexicon_acronyms(text: str) -> str:
    """Whole-token UPPERCASE for the universal initialisms shipped in
    ``data/display-lexicon.yaml`` — the fixb132 rider (warden §41 smell 3).

    Thin seam over fixb133's OWN ``pf_display_doctrine.uppercase_acronyms``
    (word-wise, exact token match): one acronym list for the engine, and
    the UF channel borrows the LIST, never a PF display convention. Lazy
    import — house style, and it keeps the module edge one-way. A missing
    or empty lexicon degrades to identity."""
    try:
        from wystan.pipeline_v2.pf_display_doctrine import (
            uppercase_acronyms,
        )
    except Exception:  # noqa: BLE001 — corroborative data is optional
        return text
    return uppercase_acronyms(text)


def uf_component_name_deglue_enabled() -> bool:
    """fixb132 authored component-name de-glue. Default **ON** since the
    2026-08-09 flip-pack №37 (KEY_SCHEMA 70; warden №41 GO): an
    identifier-shaped journey display ('AdminTeamPage', 'Teams Page',
    'AdminWebsitesPage WebsitesPage') is re-derived from the words the
    identifier itself declares, before Law C grades it — deferring to the
    post-adjudicator rescore seam whenever Stage 6.7e is a live writer.
    ``WYSTAN_UF_COMPONENT_NAME_DEGLUE=0`` restores the pre-fixb132
    emission byte for byte (the kill-switch law forever; unset ≡ ``1``)."""
    return os.environ.get(
        UF_COMPONENT_NAME_DEGLUE_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def synth_display_hygiene_enabled() -> bool:
    """fixb130 NS-E / NS-2-JS synth display hygiene. Default **OFF**
    (armed): ``WYSTAN_SYNTH_DISPLAY_HYGIENE=1`` runs the paren-space law
    over every UF display and the echo + de-glue laws over SYNTHESIZED rows.
    Unset/``0`` ⇒ every display byte-identical."""
    return os.environ.get(
        SYNTH_DISPLAY_HYGIENE_ENV, "1").strip().lower() in {"1", "true"}


def uf_name_degrime_enabled() -> bool:
    """B50 Seg1-2 display de-grime. Default **ON** (flipped B62, KEY_SCHEMA
    29): the adjacent-echo discriminator + glyph-less deparam run at the
    display JOINER. ``WYSTAN_UF_NAME_DEGRIME=0`` disables (byte-identical)."""
    return os.environ.get(UF_NAME_DEGRIME_ENV, "1").strip().lower() in {
        "1", "true",
    }


def uf_resource_rung_enabled() -> bool:
    """B50 Seg3 earned resource rung. Default **ON** (flipped B62,
    KEY_SCHEMA 29): the member-noun / route / test grounding rungs run in
    Law C (adds OR-sources to ``res_grounded``, bar unchanged).
    ``WYSTAN_UF_RESOURCE_RUNG=0`` disables (confidence + serialized
    output byte-identical)."""
    return os.environ.get(UF_RESOURCE_RUNG_ENV, "1").strip().lower() in {
        "1", "true",
    }


NARROWED_NORMAL_RUBRIC_ENV = "WYSTAN_NARROWED_NORMAL_RUBRIC"


def narrowed_normal_rubric_enabled() -> bool:
    """fixb129 addendum (C2-verb probe) — default **ON** (flip-pack #34,
    KEY_SCHEMA 67; the ruling this docstring once awaited was given, and
    the "default OFF, awaiting an operator ruling" wording it carried until
    fixb142 was stale — the code has returned ``"1"`` since the flip).
    A row Law B NARROWED is scored by the ordinary Law C rubric instead of
    being hard-stamped ``low`` + ``['missing:verb']``.

    SCOPE, and it is the whole of fixb142 Part 2: this flag only reaches
    the PRIMARY naming pass (fixb130 item 6). Every post-mint rescore seam
    re-applies the hard stamp, and those seams write the FINAL grade — so
    a world measurement of this class reads the SAME seven rows at KS66 and
    at KS75 despite the flag being on. See
    :func:`narrowed_rubric_rescore_enabled`.

    Law B rewrites the name to "<Browse|View> <resource>" picking the verb
    FROM the member families, so the surviving name's lead is member-grounded
    by construction — the old stamp punished the row for the pipeline's own
    correction and asserted a verb was missing when it was witnessed.

    WHY DEFAULT OFF (not the usual bugfix default-ON): turning this on
    overturns the NARROWED-FLOOR doctrine two earlier cycles banked by name
    — ``test_b57_rung_sources.TestFloorsUntouched
    .test_law_b_narrowed_floor_unchanged`` (an explicit floor invariant) and
    the R0/fixb106 pair ``test_jsonhero_uf004_create_item_demotes_honestly``
    / ``test_novu_uf056_edit_context_demotes_honestly`` (whose stated
    rationale is that a final member rescore which only ever UPGRADES is
    dishonest). Those are doctrine, not stale fixtures, and the same
    jsonhero UF-004 row is the named exhibit on BOTH sides. The mechanism
    ships armed and measured so the ruling can be a one-line flip; it does
    not re-curate a banked law on its own authority."""
    return os.environ.get(NARROWED_NORMAL_RUBRIC_ENV, "1").strip().lower() \
        in {"1", "true", "on"}


def uf_rung_sources_v2_enabled() -> bool:
    """B57 Seg1 rung-source expansion. Default **ON** (flipped B62,
    KEY_SCHEMA 29): the nav-cluster / i18n-key / route-method / test-assert
    grounding rungs run in Law C (adds OR-sources to ``res_grounded`` /
    ``verb_grounded``, bar unchanged). ``WYSTAN_UF_RUNG_SOURCES_V2=0``
    disables (confidence + serialized output byte-identical)."""
    return os.environ.get(UF_RUNG_SOURCES_V2_ENV, "1").strip().lower() in {
        "1", "true",
    }


def uf_verb_snap_enabled() -> bool:
    """B61 Seg1 evidence-born verb-snap. Default **ON** (flipped B62,
    KEY_SCHEMA 29): the deterministic lead-verb snap runs (replace a lying
    lead verb with the canonical verb of the member verb-composition's
    dominant family). DISPLAY channel; the ONLY UF-name-changing flag.
    ``WYSTAN_UF_VERB_SNAP=0`` disables (names + confidence + serialized
    output byte-identical)."""
    return os.environ.get(UF_VERB_SNAP_ENV, "1").strip().lower() in {
        "1", "true",
    }


def uf_member_lead_echo_enabled() -> bool:
    """W1/C-A ``verb:member-lead-echo`` rung. Default **OFF** (armed):
    ``WYSTAN_UF_MEMBER_LEAD_ECHO=1`` adds the member-flow lead-token
    echo as one more OR-source to Law C's ``verb_grounded`` (bar
    unchanged). Default **ON** (flip-pack #19, KS54); ``=0`` ⇒ confidence +
    evidence + serialized output byte-identical."""
    return os.environ.get(UF_MEMBER_LEAD_ECHO_ENV, "1").strip().lower() in {
        "1", "true",
    }


def uf_umbrella_floor_enabled() -> bool:
    """C-B / fixb106 ``verb:repo-umbrella-lead`` rung. Default **ON**
    (flip-pack #20, KS56; warden CLEAR on the keyed infisical pair: +14
    rows, 0 demotions, I24 holes 32→3): a repo-mined umbrella lead as one
    more OR-source in Law C's ``verb_grounded`` (bar unchanged). ``=0`` ⇒
    confidence + evidence + serialized output byte-identical."""
    return os.environ.get(UF_UMBRELLA_FLOOR_ENV, "1").strip().lower() in {
        "1", "true",
    }


def homing_hygiene_enabled() -> bool:
    """B69-v2 — default **ON** since the 2026-07-16 horizon-1 flip
    (KEY_SCHEMA 30; keyed proof papermark + cal green — pm churn=1 fold,
    cal no-op). Arms the PF-homing hygiene family, FINAL composition
    (Stage 6.99b post-UF rehome rail + rename-on-rehome + the B31
    pf-display echo-guard + the 6.7e Law-A telemetry preservation).
    ``WYSTAN_HOMING_HYGIENE=0`` ⇒ byte-identical pre-B69-v2 output
    (kill-switch forever; unset ≡ explicit ``1``). Split rulings: the
    seed-birth pair = ``WYSTAN_SEED_HYGIENE`` (unflipped); the display
    law = ``WYSTAN_NAMING_LAW``."""
    return os.environ.get(HOMING_HYGIENE_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def naming_law_enabled() -> bool:
    """B70 member-evidence redesign — default **ON** since the 2026-07-16
    horizon-1 flip (KEY_SCHEMA 30; keyed proof papermark + cal green —
    law-attributed churn, zero bare names). Arms the bare-verb/dev-grain-
    token display law (member-evidence redesign; see :data:`NAMING_LAW_ENV`).
    ``WYSTAN_NAMING_LAW=0`` ⇒ the law list is byte-identical to pre-B70
    (kill-switch forever; unset ≡ explicit ``1``). Independent of the HOMING
    and SEED flags."""
    return os.environ.get(NAMING_LAW_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


# ── B50 display de-grime (Seg1 echo discriminator; Seg2 raw-param) ──────
#
# Structural, vocabulary-free token surgery applied at the display JOINER
# (never a post-filter over arbitrary finished strings): the same
# singular-fold + explicit-glued-suffix rule the B46 discriminator uses,
# lifted to work on already-split display tokens. Seg1 removes adjacent
# echoes; Seg2 (extended below) additionally reduces glyph-less route-param
# slugs to their noun core and drops standalone addressing identifiers.


def _degrime_sing(t: str) -> str:
    """Singular-fold one token (mirrors the B46 ``sing``): drop a trailing
    's' only when >3 chars remain, so 'views'->'view' but 'ids'->'ids'."""
    return t[:-1] if (t.endswith("s") and len(t) > 3) else t


#: Explicit glued tail-echo suffixes (B46 law: EXACT singular-folded
#: equality OR one of these glued suffixes — NEVER a partial char prefix,
#: so 'auth-authorize' is safe).
_DEGRIME_ECHO_SUFFIXES = ("id", "ids", "uuid", "s")


def _deglue_echo_tokens(tokens: list[str]) -> list[str]:
    """Drop an adjacent echo token: (a) a singular-folded duplicate of the
    previous token (core >=3 chars), or (b) the previous token glued with an
    explicit id/ids/uuid/s addressing suffix ('chat'+'ids'='chatids').

    NEVER strips a partial character prefix — 'auth authorize' /
    'auth authorizes' both survive (B46 SACRED anti-case)."""
    out: list[str] = []
    for t in tokens:
        if out:
            prev = out[-1]
            pl, tl = prev.lower(), t.lower()
            ps, ts = _degrime_sing(pl), _degrime_sing(tl)
            # (a) adjacent noun dup, singular-folded, core >= 3.
            if ts == ps and len(ps) >= 3:
                continue
            # (b) glued tail-echo: t == prev(+sing) + explicit suffix.
            if len(pl) >= 3 and any(
                tl == base + suf
                for base in (pl, ps)
                for suf in _DEGRIME_ECHO_SUFFIXES
            ):
                continue
        out.append(t)
    return out


#: Seg2 — FROZEN unambiguous identifier tokens (executor ruling, B46 lesson:
#: linguistic ≠ structural). Used for BOTH the glyph-less glued deparam
#: ('teamurl'→'team', 'boardid'→'board') and the standalone addressing drop
#: ('case id'→'case'). Deliberately NARROWER than the vocab's
#: ``route_addressing_suffixes`` (which the GLYPHED ``_param_noun`` path
#: keeps using unchanged): vocab suffixes like 'name'/'code'/'key'/'ref'/
#: 'hash'/'handle' are real word-endings — gluing on them is meaningful-word
#: loss ('username'→'user', 'barcode'→'bar').
_STANDALONE_ADDR = frozenset({
    "id", "ids", "url", "uuid", "guid", "slug", "pk",
})


def _drop_standalone_addr(words: list[str]) -> list[str]:
    """Seg2 — drop a standalone pure-addressing token ('id', 'ids', 'url', …)
    that FOLLOWS a non-addressing noun ('case id' -> 'case'); a leading or
    solitary addressing token is kept (it is handled by the pure-param
    display replacement, not silently deleted)."""
    out: list[str] = []
    for w in words:
        wl = w.lower()
        if out and wl in _STANDALONE_ADDR and out[-1].lower() not in _STANDALONE_ADDR:
            continue
        out.append(w)
    return out


#: fixb108-v2 Fix-4 — framework CLASS-token strip (journey/display names).
#: The Rails route-supply names journeys off controller classes, shipping
#: 'Receive webhooks controller' — the implementation class leaks into the
#: product noun. Default OFF (armed); ``=0`` kill-switch forever.
CLASS_TOKEN_STRIP_ENV = "WYSTAN_CLASS_TOKEN_STRIP"


def class_token_strip_enabled() -> bool:
    """fixb108-v2 Fix-4 — trailing framework class-token strip. Default
    OFF (armed): unset keeps every display byte-identical."""
    return os.environ.get(CLASS_TOKEN_STRIP_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _class_suffix_tokens() -> frozenset[str]:
    """The data-side class-token list (YAML — never hardcoded).

    Deliberately NARROW, and the narrowness is the mechanism: a token
    qualifies only when it names a FRAMEWORK CLASS ROLE that no product
    surface is ever called. Measured anti-cases keep 'policy'/'policies'
    and 'job'/'jobs' OUT — chatwoot's ``AgentCapacityPolicy`` is a real
    product resource ('Manage agent capacity policies' is a correct
    journey, live on BOTH arms of the c5proof pair) and a job board's
    'jobs' is a product noun. Same law as ``_STANDALONE_ADDR``: linguistic
    ≠ structural, so the list is frozen by evidence, not by intuition.
    """
    vocab = load_naming_vocab()
    raw = vocab.get("class_suffix_tokens") or ()
    return frozenset(str(t).strip().lower() for t in raw if str(t).strip())


def _devgrain_tail_tokens() -> tuple[frozenset[str], frozenset[str]]:
    """``(tail_tokens, compound_guard)`` — data-side, like every vocab."""
    vocab = load_naming_vocab()
    tails = frozenset(
        str(t).strip().lower()
        for t in (vocab.get("devgrain_tail_tokens") or ())
        if str(t).strip())
    guard = frozenset(
        str(t).strip().lower()
        for t in (vocab.get("devgrain_tail_compound_guard") or ())
        if str(t).strip())
    return tails, guard


def _drop_devgrain_tail(words: list[str], floor: int = 2) -> list[str]:
    """fixb108-v3 (a) — drop a tautological DEVGRAIN tail from a journey
    name ('Complete onboarding flow' -> 'Complete onboarding').

    Every journey IS a flow, so the trailing token carries grain, not
    product meaning. Two guards keep real product nouns whole:

    * TOKEN BOUNDARY, never substring — 'Manage workflow' is one token
      and is therefore invisible here (the resurrection this fix answers
      came from substring thinking).
    * COMPOUND GUARD — 'Approve cash flow' keeps its object because
      'cash flow' is a domain noun (maybe is a finance product). Same
      for 'work flow' / 'data flow'.
    """
    if len(words) <= floor:
        return words
    tails, guard = _devgrain_tail_tokens()
    if words[-1].lower() not in tails:
        return words
    if len(words) >= 2 and words[-2].lower() in guard:
        return words
    return words[:-1]


def _drop_trailing_class_token(words: list[str], floor: int = 2) -> list[str]:
    """Seg4 — drop ONE trailing framework class token ('Receive webhooks
    controller' -> 'Receive webhooks').

    TRAILING-only and DROP-only (the result stays a subsequence, so
    :func:`_degrime_display` span-mapping stays valid). Floored at
    ``floor`` surviving words for the same reason Seg3 is: a 2-word
    display whose tail is the class token has no product noun left behind
    ('Controllers core' must not become 'core'), and a mid-phrase
    occurrence is never touched ('View controllers core' keeps its shape —
    stripping inside would mint 'View core', which is worse than the
    smell it cures).
    """
    if len(words) <= floor:
        return words
    if words[-1].lower() in _class_suffix_tokens():
        return words[:-1]
    return words


def _degrime_words(words: list[str]) -> list[str]:
    """Casing-preserving DROP-only de-grime of a display-word list: Seg1
    adjacent-echo removal + Seg2 standalone addressing-token drop. No
    mutation (glyph-less deparam lives in :func:`_deparam_word`), so the
    result is always a subsequence of the input — span-mapping in
    :func:`_degrime_display` stays valid.

    fixb103 — Seg3 STRANDED-CONNECTIVE trim. The Seg2 addressing drop
    deletes the object a connective governed ('ssh host group details by
    id' -> '… details by'), shipping a name that ends mid-preposition:
    'Settingspage SSH host group details by' (HIGH), 'Manage installation
    details by', 'Manage pki subscriber details by' on infisical ON. The
    trim is DROP-only too (subsequence preserved) and reuses the R5
    connective vocabulary.

    fixb104 — the trim is now FLAGLESS (it rode
    ``WYSTAN_UF_POSTMINT_RESCORE`` in fixb103). The final keyed pair
    proved the pack gate wrong on both counts: the strand is NOT a
    de-glue artefact (the pre-contract capture of the ON run carries ZERO
    stranded names — every one of the 10 is minted by the addressing drop
    inside this contract) and it reaches the OFF arm too ('Manage role
    details by', 'Manage SSH ca by' — both **high** on infisical OFF,
    where the pack is off by definition). A name that ends
    mid-preposition is a broken display invariant in EVERY arm, so it is
    repaired like one (Law-B class; B102 member-remap / fixb103 I14
    re-derivation precedent) — and floored at TWO surviving words, see
    :func:`_trim_stranded_tail`."""
    out = _trim_stranded_tail(
        _drop_standalone_addr(_deglue_echo_tokens(words)))
    if class_token_strip_enabled():
        # fixb108-v2 Seg4 — runs LAST so the class token is judged against
        # the already-degrimed tail (an echo/addressing drop can expose it).
        # fixb108-v3 (a) — peel to a fixed point: a devgrain tail can HIDE
        # a class token ('Receive webhooks controller flow'), so one
        # ordered pass strips only the outer one. Bounded by the word
        # count and DROP-only, so it always terminates and the result
        # stays a subsequence.
        for _ in range(len(out)):
            peeled = _drop_devgrain_tail(_drop_trailing_class_token(out))
            if peeled == out:
                break
            out = peeled
    return out


def _trim_stranded_tail(words: list[str], floor: int = 2) -> list[str]:
    """Drop trailing connectives ONE at a time while the shipped primitive
    still calls the tail stranded, never below ``floor`` surviving words.

    The floor is the PHRASAL-VERB guard, and it is arity — not a second
    vocabulary. A 2-word display whose last word is a connective has no
    deleted object to mourn: it IS the verb ('Sign in', 'Log in', 'Opt
    in'), and the R5 split rename that mints exactly that shape
    ('Signin' -> 'Sign in') must not be refused. A stranded object always
    leaves >= 3 words behind ('Manage details by' is the shortest of the
    twelve warden exhibits), so nothing real is lost. One connective
    vocabulary still — the verdict is always
    ``naming_wave_r5.trim_stranded_connective``'s.

    fixb130 / NS-C second producer — the arity floor was the RIGHT law
    scoped to the WRONG unit. "It IS the verb" does not stop being true at
    three words: the KS66 world ships 'Sign up and log' (formbricks UF-073)
    and 'Complete onboarding after first sign' (epic-stack UF-008), both
    minted here by trimming a phrasal verb's particle, and a fourth-word
    phrase 'Register and log in' (postiz-app UF-036) is one addressing drop
    away from the same fate. So the guard is restated over the unit the law
    is actually about: a trailing connective that is a verb PARTICLE
    (``uf_synth_fold.PARTICLES`` — one particle vocabulary for the stack,
    re-used, never a second list) governs no object and therefore cannot be
    stranded. The strand producer this law was built for deletes the
    addressing NOUN a PREPOSITION governed ('… details by id' -> '… details
    by'); every one of the twelve warden exhibits ends in 'by', not one in a
    particle, so the class the law exists for is untouched by construction.
    ``_CONNECTORS`` ∩ ``PARTICLES`` = {'in', 'on'} — the whole reach of this
    guard."""
    from wystan.pipeline_v2.uf_synth_fold import PARTICLES

    out = list(words)
    while len(out) > floor and trim_stranded_connective(out) != out:
        if str(out[-1]).strip().lower() in PARTICLES:
            break                          # a verb's particle, never a strand
        out = out[:-1]
    return out


_DEGRIME_WORD_RE = re.compile(r"[A-Za-z0-9]+")


def _degrime_display(text: str) -> str:
    """DROP-only de-grime over a finished display string, preserving every
    non-word separator (spaces, '&', '—', parens) of the surviving words.

    Used at the two producer seams that emit a joined string — the journey
    TEMPLATE ('Ingest ingest'->'Ingest') and the current-name echo
    discriminator. Only removes word tokens the de-grime rule marks as
    echoes; it never mutates a surviving token (mutation lives in the
    token-level renderer :func:`_resource_phrase`)."""
    matches = list(_DEGRIME_WORD_RE.finditer(text or ""))
    if len(matches) < 2:
        return text
    low = [m.group(0).lower() for m in matches]
    kept = _degrime_words(low)
    if kept == low:
        return text
    keptq = list(kept)
    drop_spans: list[tuple[int, int]] = []
    for m in matches:
        wl = m.group(0).lower()
        if keptq and wl == keptq[0]:
            keptq.pop(0)
        else:
            drop_spans.append((m.start(), m.end()))
    if not drop_spans:
        return text
    res: list[str] = []
    last = 0
    for s, e in drop_spans:
        res.append(text[last:s])
        last = e
    res.append(text[last:])
    out = "".join(res)
    out = re.sub(r"\(\s*\)", "", out)          # empty parens after a drop
    out = re.sub(r"\s+([)\]])", r"\1", out)     # space before a close bracket
    out = re.sub(r"\s{2,}", " ", out).strip(" -–—&")
    return out or text


#: Confidence ordering — the ONE rank map the naming laws compare with.
_CONF_RANK = {"low": 0, "medium": 1, "high": 2}

_PAREN_OPEN_SPACE_RE = re.compile(r"\(\s+")


def _paren_space_display(text: str) -> str:
    """fixb130 NS-E — collapse a parenthetical opened on whitespace
    ('Browse & manage scores ( Project)' -> '… (Project)').

    Whitespace only: no token is added, dropped or mutated, so it is safe on
    every row and cannot interact with any span mapping."""
    if not text or "(" not in text:
        return text
    out = _PAREN_OPEN_SPACE_RE.sub("(", text)
    return re.sub(r"\s{2,}", " ", out).strip() or text


def _degrime_echo_display(text: str) -> str:
    """fixb130 — the ADJACENT-ECHO segment of :func:`_degrime_display`, alone.

    Same DROP-only reassembly discipline (the result is a subsequence, every
    separator of the surviving words preserved), but only
    :func:`_deglue_echo_tokens` votes. The standalone-addressing drop, the
    stranded-connective trim and the class-token strip are deliberately NOT
    run: measured over the KS66 synth population they take 'URL' out of
    langfuse UF-152 while adding no repair the echo segment does not already
    make."""
    matches = list(_DEGRIME_WORD_RE.finditer(text or ""))
    if len(matches) < 2:
        return text
    low = [m.group(0).lower() for m in matches]
    kept = _deglue_echo_tokens(low)
    if kept == low:
        return text
    keptq = list(kept)
    drop_spans: list[tuple[int, int]] = []
    for m in matches:
        wl = m.group(0).lower()
        if keptq and wl == keptq[0]:
            keptq.pop(0)
        else:
            drop_spans.append((m.start(), m.end()))
    if not drop_spans:
        return text
    res: list[str] = []
    last = 0
    for s, e in drop_spans:
        res.append(text[last:s])
        last = e
    res.append(text[last:])
    out = "".join(res)
    out = re.sub(r"\(\s*\)", "", out)
    out = re.sub(r"\s+([)\]])", r"\1", out)
    out = re.sub(r"\s{2,}", " ", out).strip(" -–—&")
    return out or text


def _trim_stranded_display(text: str) -> str:
    """fixb104 — the ``stranded_connective`` law's REMEDY over a finished
    display string: drop the trailing connectives, keep every separator of
    the surviving words.

    Always available (the primitive is DROP-only and floored at one word),
    which is what lets the law be a repair rather than a rejection: a
    producer whose candidate strands never has to fall back to a worse
    name — and, crucially, never has to skip the mint (a display law that
    could delete a row would move MEMBERSHIP, which the single-writer law
    forbids to this module)."""
    matches = list(_DEGRIME_WORD_RE.finditer(text or ""))
    if len(matches) < 3:
        return text
    low = [m.group(0).lower() for m in matches]
    kept = _trim_stranded_tail(low)
    if len(kept) == len(low):
        return text
    # Same reassembly discipline as :func:`_degrime_display`: the surviving
    # prefix plus the tail AFTER the last word, so a closing bracket the
    # trimmed word sat inside is never orphaned ('… (details by)' ->
    # '… (details)').
    out = text[:matches[len(kept) - 1].end()] + text[matches[-1].end():]
    out = re.sub(r"\(\s*\)", "", out)
    out = re.sub(r"\s+([)\]])", r"\1", out)
    out = re.sub(r"\s{2,}", " ", out).strip(" -–—&")
    return out or text


#: R5-5 census-shape detectors — a camelCase boundary or a snake_case
#: boundary inside a displayed token means a code identifier leaked into the
#: display (C4 / C1raw / C8pf). Mechanistic (no dictionary — the census used
#: /usr/share/dict/words as an INSTRUMENT only; a fix may not).
_R5_CAMEL_BOUNDARY = re.compile(r"[a-z][A-Z]")
_R5_SNAKE_BOUNDARY = re.compile(r"[A-Za-z0-9]_[A-Za-z0-9]")
#: Identifier-shaped run (a camel boundary can only ever live INSIDE one,
#: a snake boundary carries its underscore) — the token scope the fixb107
#: brand exemption is evaluated over.
_R5_IDENT_RUN = re.compile(r"[A-Za-z0-9_]+")


def _brand_cased_idents(vocab: Mapping[str, Any]) -> frozenset[str]:
    """Folded forms of every token :func:`polish_display_casing` can MINT —
    each ``brand_casing`` key, each ``brand_casing`` canonical value, and
    each ``known_acronyms`` member.

    fixb107 — ONE source of truth for the brand channel: the exemption
    reads exactly the vocabulary the casing polish writes, so the two can
    never disagree again. (A second, exemption-only brand list would be the
    dictionary this codebase forbids.)"""
    out: set[str] = set()
    for key, val in (vocab.get("brand_casing") or {}).items():
        out.add(_ident_fold(str(key)))
        out.add(_ident_fold(str(val)))
    for acr in (vocab.get("known_acronyms") or []):
        out.add(_ident_fold(str(acr)))
    out.discard("")
    return frozenset(out)


def _name_disease_shape(
    name: str, vocab: Mapping[str, Any] | None = None,
) -> str | None:
    """R5-5 — the census disease shape a display name exhibits, or ``None``.

    Conservative + mechanistic (no dictionary, no per-repo list):
      * ``paren-qualifier`` — a ``(…)`` qualifier tail (C5);
      * ``raw-identifier`` — a camelCase / snake_case boundary, i.e. a code
        identifier leaked into display (C4 / C1raw / C8pf).

    A healthy verb-led journey phrase ('Analyze cohort retention', 'Manage
    API keys') carries NEITHER shape and is never flagged — the census
    false-positive lesson.

    ``vocab`` (fixb107, and only with ``WYSTAN_BRAND_SHAPE_EXEMPT=1``)
    arms the BRAND-CANONICAL exemption: a camel/snake boundary that lies
    inside a token this module's own casing vocabulary mints
    (:func:`_brand_cased_idents`) is the polish's OWN output, not a leaked
    identifier. Token-scoped by construction — every other run of the
    display is still judged, so 'Authorize GitHub IpAllowlist' keeps its
    ``raw-identifier`` verdict on ``IpAllowlist``. Vocab omitted or flag
    off ⇒ the banked behaviour, byte-identical."""
    if not name:
        return None
    if "(" in name or ")" in name:
        return "paren-qualifier"
    if _R5_CAMEL_BOUNDARY.search(name) or _R5_SNAKE_BOUNDARY.search(name):
        if vocab is None or not brand_shape_exempt_enabled():
            return "raw-identifier"
        brands = _brand_cased_idents(vocab)
        for run in _R5_IDENT_RUN.findall(name):
            if not (_R5_CAMEL_BOUNDARY.search(run)
                    or _R5_SNAKE_BOUNDARY.search(run)):
                continue
            if _ident_fold(run) in brands:
                continue          # the casing polish minted this boundary
            return "raw-identifier"
        return None               # FALL-THROUGH to the rungs below
    return None


def _qualifier_echoes_base(base: str, qual: str) -> bool:
    """True when EVERY singular-folded token of a candidate qualifier is
    already present (singular-folded) in the base display — the tautological
    '(Team)' on 'Teams', '(link)' on 'Manage links', '(Settings)' on 'Manage
    settings' class. A distinguishing qualifier ('(file)', '(API keys)')
    shares no folded token and is kept."""
    b = {_degrime_sing(t) for t in re.split(r"[^a-z0-9]+", (base or "").lower()) if t}
    q = [_degrime_sing(t) for t in re.split(r"[^a-z0-9]+", (qual or "").lower()) if t]
    return bool(q) and all(t in b for t in q)


def _deparam_word(word: str) -> str:
    """Seg2 — a glyph-less route-param slug ``<noun><addr-suffix>`` (the
    ``$teamUrl`` → 'teamurl', ``boardId`` → 'boardid' class that bypassed
    ``_param_noun`` because it carried no ``$``/``:`` glyph) reduces to its
    noun core: 'teamurl'->'team', 'boardid'->'board', 'chatids'->'chat'.

    Suffix source is the FROZEN :data:`_STANDALONE_ADDR` subset — NEVER the
    full vocab ``route_addressing_suffixes`` (executor ruling: 'username'/
    'filename'/'barcode' must survive; the glyphed ``_param_noun`` path keeps
    the full vocab set as today). A pure-addressing token ('url', 'id',
    'ids') is left as-is (the standalone-drop / pure-param replacement
    handle it). Requires a noun core of >=3 chars that is not itself
    pure-addressing, so nothing meaningful is truncated."""
    wl = word.lower()
    if wl in _STANDALONE_ADDR:
        return word
    best: str | None = None
    for suf in _STANDALONE_ADDR:
        for tail in (suf, suf + "s"):
            if wl.endswith(tail) and len(wl) > len(tail):
                core = wl[: -len(tail)]
                if len(core) >= 3 and core not in _STANDALONE_ADDR:
                    # Longest matching suffix wins (prefer 'ids' over 'id').
                    if best is None or (len(wl) - len(core)) > (len(wl) - len(best)):
                        best = core
    return best if best is not None else word


def _degrime_resource_words(
    words: list[str], vocab: Mapping[str, Any],
) -> list[str]:
    """Full de-grime of a rendered resource phrase token stream: Seg2
    glyph-less deparam (mutate ``<noun><addr>`` → core) composed with Seg1
    adjacent-echo removal + standalone addressing drop. 'teamurl document'
    -> 'team document'; 'case caseid' -> 'case case' -> 'case'.

    ``vocab`` is accepted for signature stability with the Seg1-committed
    mint-side caller (``_slot_consistent_label``); the deparam subset is
    FROZEN (executor ruling), so vocab is not consulted here."""
    del vocab  # frozen subset; see _deparam_word
    deparamed = [_deparam_word(w) for w in words]
    return _degrime_words(deparamed)


def _deparam_display(text: str) -> str:
    """Seg2 raw-param DISPLAY LAW over a finished display string: mutate each
    glyph-less param slug to its noun core, drop standalone addressing
    identifiers, collapse the resulting adjacent echoes — preserving every
    non-word separator ('&', '—', parens). 'teamurl documents' -> 'team
    documents'; 'boardid card cardids' -> 'board card'.

    fixb104 Seg A — THE STRAND'S LIVE PRODUCER. This pass re-implements the
    drop rules inline (span-preserving), so the ``_degrime_words`` trim
    never reached it: 'Manage member details by id' shipped as 'Manage
    member details by' on infisical ON, 'Manage SSH ca by' (high) on OFF.
    After the drops are decided, trailing connectives left governing
    nothing are dropped too — same DROP-only discipline (the result stays
    a subsequence, so the span reassembly below stays valid), same single
    connective vocabulary, floored at one surviving word. The trim also
    fires when the INPUT already ends mid-preposition, which makes this
    pass idempotently strand-free for every row that reaches it — whatever
    minted the row."""
    matches = list(_DEGRIME_WORD_RE.finditer(text or ""))
    if not matches:
        return text
    mutated = [_deparam_word(m.group(0)) for m in matches]
    keep = [True] * len(mutated)
    prev_low: str | None = None
    for i, w in enumerate(mutated):
        wl = w.lower()
        if prev_low is not None:
            # standalone addressing token after a noun → drop.
            if wl in _STANDALONE_ADDR and prev_low not in _STANDALONE_ADDR:
                keep[i] = False
                continue
            ps, ts = _degrime_sing(prev_low), _degrime_sing(wl)
            dup = ts == ps and len(ps) >= 3
            glued = len(prev_low) >= 3 and any(
                wl == base + suf
                for base in (prev_low, ps)
                for suf in _DEGRIME_ECHO_SUFFIXES
            )
            if dup or glued:
                keep[i] = False
                continue
        prev_low = wl
    # fixb104 Seg A — trim connectives the drops above left stranded
    # (floored at two surviving words: the phrasal-verb guard).
    _kept_idx = [i for i, k in enumerate(keep) if k]
    if len(_kept_idx) >= 3:
        _kept_low = [mutated[i].lower() for i in _kept_idx]
        _trimmed = _trim_stranded_tail(_kept_low)
        for _i in _kept_idx[len(_trimmed):]:
            keep[_i] = False
    if all(keep) and mutated == [m.group(0) for m in matches]:
        return text
    out: list[str] = []
    last = 0
    for i, m in enumerate(matches):
        sep = text[last:m.start()]
        if keep[i]:
            out.append(sep)
            out.append(mutated[i])
        elif sep.strip():
            out.append(sep)     # keep a punctuation separator ('&'), drop bare spaces
        last = m.end()
    out.append(text[last:])
    res = "".join(out)
    res = re.sub(r"\(\s*\)", "", res)
    res = re.sub(r"\s+([)\]])", r"\1", res)
    res = re.sub(r"\s{2,}", " ", res).strip(" -–—&")
    return res or text


def _is_pure_param_display(display: str) -> bool:
    """True when a display is nothing but addressing identifiers ('URL',
    'ID', 'Slug') — it names no domain object and must be replaced."""
    toks = [t for t in re.split(r"[^a-z0-9]+", (display or "").lower()) if t]
    return bool(toks) and all(t in _STANDALONE_ADDR for t in toks)


def _resolve_param_display(
    anchor_id: str,
    nav_label: str | None,
    paths: Iterable[str],
    vocab: Mapping[str, Any],
) -> str | None:
    """Seg2 — resolve a domain noun for a display that would be a pure param
    ('/p/$url' PF → 'URL'). Ladder: (a) the anchor segment WITHOUT the param,
    (b) the nav-cluster label, (c) the member-file dominant domain noun via
    :func:`domain_noun.extract_domain_noun`. NEVER the route letter 'p' /
    another pure param — each rung is rejected unless it names something."""
    # (a) anchor segment without the param.
    base, _qual = humanize_anchor_display(anchor_id, vocab)
    if (base and not _is_pure_param_display(base)
            and len(base.replace(" ", "")) > 1
            and not display_law_violations(base, vocab)):
        return base
    # (b) nav-cluster label.
    if nav_label:
        nl = polish_display_casing(nav_label, vocab)
        if (nl and not _is_pure_param_display(nl)
                and not display_law_violations(nl, vocab)):
            return nl
    # (c) member-file / member-component dominant domain noun.
    try:
        from wystan.pipeline_v2.domain_noun import extract_domain_noun
        dn = extract_domain_noun(list(paths), "")
    except Exception:  # noqa: BLE001 — optional structural resolver
        dn = None
    if dn and dn.label and not _is_pure_param_display(dn.label):
        cand = polish_display_casing(dn.label, vocab)
        if cand and not display_law_violations(cand, vocab):
            return cand
    return None


def degrime_rename_plan(
    current_names: Mapping[str, str],
    proposals: Mapping[str, str],
) -> set[str]:
    """B50 collision-safe rename plan (kan forensics; B16 precedent:
    "strip … collision-safe"). Compute targets FIRST over all rows, then
    apply only non-colliding renames.

    A proposed rename is REJECTED (row keeps its original name) when its
    case-folded target (a) already exists as ANOTHER row's current name —
    conservative: even when that row is itself being renamed away — or
    (b) is the target of TWO OR MORE proposals (skip BOTH; the kan
    'boardids'/'boardslugs' → 'Manage boards' ×2 class stays as honest
    distinct grime rather than a flag-created display collision).

    Pure function of the two maps ⇒ deterministic and independent of
    iteration / application / input order. Returns the uids whose rename
    may be applied."""
    cnt = Counter((n or "").strip().lower() for n in current_names.values())
    tcnt = Counter((v or "").strip().lower() for v in proposals.values())
    applied: set[str] = set()
    for uid in sorted(proposals):
        tgt = (proposals[uid] or "").strip().lower()
        cur = (current_names.get(uid) or "").strip().lower()
        exists_other = cnt.get(tgt, 0) - (1 if tgt == cur else 0) > 0
        if exists_other or tcnt[tgt] >= 2:
            continue
        applied.add(uid)
    return applied


# ── Route-template humanization (B2 — router-family aware) ──────────────
#
# File-system routers encode structure IN the path/filename with dialect
# glyphs that are dev machinery, never product words: trailing ``+``
# (folder nesting), ``$param`` / ``:param`` / ``{param}`` (dynamic),
# ``_layout`` (pathless), ``[escaped]`` (literal escape), ``.`` (path
# separator inside one folder name), ``[param]`` (dynamic — DROP),
# ``(group)`` (route group — unwrap). ``[..]`` means the OPPOSITE thing
# across dialects (escape vs dynamic), so a dialect is read from the
# path's own STRUCTURAL markers (never a stack NAME — trunk-purity G3)
# into capability flags that drive the per-segment rule. Every rule is
# generic to the marker — never a repo-specific literal.


@dataclass(frozen=True)
class _RouteDialect:
    """Structural capabilities of a filesystem router, inferred from a
    path's own glyphs (not a stack name):

    * ``flat_nesting`` — a trailing ``+`` on a folder groups nested
      routes (flat-routes convention) and is not a display word.
    * ``bracket_escape`` — ``[x]`` is a LITERAL escape (keep the inner
      text) rather than a dynamic-param placeholder (drop it). The two
      readings are mutually exclusive per router; a router that addresses
      params with ``$`` never uses brackets for params.
    """

    flat_nesting: bool
    bracket_escape: bool


def _route_dialect(path: str) -> _RouteDialect:
    """Read a path's router capabilities from its structural markers."""
    segs = [s for s in (path or "").split("/") if s]
    low = {s.lower() for s in segs}
    dollar_params = any("$" in s for s in segs)
    plus_folders = any(len(s) > 1 and s.endswith("+") for s in segs)
    routes_root = "routes" in low and ("app" in low or "src" in low)
    dotted_layout = any(s.startswith("_") and "." in s for s in segs)
    flat = plus_folders or dollar_params or routes_root or dotted_layout
    return _RouteDialect(flat_nesting=flat, bracket_escape=dollar_params or flat)


def _param_noun(seg: str, vocab: Mapping[str, Any]) -> str | None:
    """The human NOUN of a dynamic route param, or ``None`` for pure
    addressing. ``$teamUrl`` → ``"team"`` (the ``Url`` addressing suffix
    drops), ``$documentId`` → ``"document"``, ``$id``/``$slug``/``$token``
    → ``None`` (an opaque identifier names nothing)."""
    raw = (seg or "").strip()
    raw = raw.lstrip("$:{<*[").rstrip("}>]").strip("[]")
    raw = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", raw)
    words = [w.lower() for w in re.split(r"[-_\s]+", raw) if w]
    addr = {str(a).lower() for a in (vocab.get("route_addressing_suffixes") or [])}
    core = [w for w in words if w not in addr]
    return " ".join(core) if core else None


def _normalize_route_segment(
    seg: str, dialect: _RouteDialect, vocab: Mapping[str, Any],
) -> str | None:
    """One path segment → a human display token (space-joined for
    dot-notation), or ``None`` to drop (layout prefix, dynamic param,
    empty). Router-template glyphs are removed per the path's dialect.

    fixb133 M1 (default OFF) pre-cleans the MARKER classes no dialect rule
    ever covered — intercepting routes, parallel slots, escaped literals —
    using the vocabulary factored out of the Next App Router profile. An
    unwrapped escape (``robots[.]txt``) keeps its dot as a LITERAL, so the
    Remix dot-separator split below must not read it as a path separator.
    Flag unset/``0`` ⇒ this block never runs ⇒ byte-identical."""
    s = (seg or "").strip()
    if not s:
        return None
    if route_marker_display_sanitize_enabled():
        from wystan.pipeline_v2.extractors._route_markers import (
            sanitize_segment,
        )

        cleaned, literal_dot = sanitize_segment(s)
        if cleaned is None:
            return None
        if literal_dot:
            return cleaned
        s = cleaned
    if dialect.flat_nesting:
        stripped = s.rstrip("+")           # flat-route folder nesting marker
        if stripped:
            s = stripped
    if s.startswith("_"):
        return None                        # pathless / layout — organises files
    g = _GROUP_SEG.match(s)
    if g:                                  # route group "(marketing)" → word
        s = g.group(1).strip()
        if not s:
            return None
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if dialect.bracket_escape:         # escaped LITERAL → unwrap
            inner = inner.strip("._")
            if not inner:
                return None
            s = inner
        else:
            return None                    # bracket-dynamic param → drop
    if "." in s:                           # Remix dot = URL separator
        parts: list[str] = []
        for p in s.split("."):
            p = p.strip()
            if not p:
                continue
            if _DYNAMIC_SEG.match(p) or p[0] in "$:{":
                noun = _param_noun(p, vocab)
                if noun:
                    parts.append(noun)
                continue
            if p.startswith("_"):
                continue
            if len(p) == 1 and p.isalpha():
                continue                   # single-char URL scaffold ("/p/")
            parts.append(p)
        return " ".join(parts) if parts else None
    if _DYNAMIC_SEG.match(s):
        return _param_noun(s, vocab)
    return s


#: The only two one-letter WORDS in English ("a", "I"). Universal grammar,
#: not a product vocabulary and not per-repo tuning.
_ONE_LETTER_WORDS = frozenset({"a", "i"})


def _is_interior_article(words: list[str], i: int) -> bool:
    """fixb128 addendum — is ``words[i]`` a legitimate one-letter WORD sitting
    INSIDE a phrase?

    The ``single_letter`` law is documented (module docstring) as "no
    1-character display / 1-letter **content** word", and its own repair
    function :func:`_peel_edge_single_letters` states that "interior single
    letters ... are left intact" — it only ever peels EDGES, because the
    defect class is router-template residue ("/p/$url" → "P URL"). The law
    itself never agreed with either: it flagged ANY one-letter word, so the
    English article in ordinary prose made a name unlawful.

    Measured cost (live keyed ollama c27, `laws_fixed: {'single_letter': 5}`):
    the author-declared journey names 'Copy a model', 'Remove a model',
    'Stop a running model', 'Push a model to a registry' were each judged
    law-dirty ON THE ARTICLE, so the maintainer's own sentence was dropped
    from the candidate ranking and the generic template shipped instead —
    'Manage cp', 'Manage rm', 'Manage stop', 'Ingest push'. Every other
    guard in this sprint held; the row simply had no lawful candidate left.

    An article at an EDGE ("Copy a") is still broken prose and still fires,
    which is exactly the set :func:`_peel_edge_single_letters` can repair.
    """
    if not (0 < i < len(words) - 1):
        return False
    return words[i].casefold() in _ONE_LETTER_WORDS


def _peel_edge_single_letters(text: str | None) -> str | None:
    """Repair a display carrying edge single-letter words (the ``/p/$url``
    → "P URL" class): drop leading/trailing 1-char alpha words so the
    single_letter law passes ("P URL" → "URL"). Interior single letters
    and all-single-letter strings are left intact."""
    if not text:
        return text
    words = text.split(" ")
    if len(words) <= 1 or not any(
        len(w) == 1 and w.isalpha() for w in words
    ):
        return text
    while len(words) > 1 and len(words[0]) == 1 and words[0].isalpha():
        words = words[1:]
    while len(words) > 1 and len(words[-1]) == 1 and words[-1].isalpha():
        words = words[:-1]
    return " ".join(words)


def _has_route_template_residue(text: str, *, route_anchor: bool = True) -> bool:
    """True when a display still carries router-template machinery: a
    param glyph (``$ : { } [ ] < > *``), a word-adjacent ``+`` (Remix
    nesting), or a leading-underscore word (layout prefix).

    Horizon-1 ruling (2026-07-16, escalation #3): the trailing-``+`` rung
    fires ONLY for ``route:``-anchored displays — in route slugs ``+`` is
    Remix flat-route syntax, but on ``ws:``/``fdir:``/``hub:`` anchors it
    is a legitimate name character ('Enterprise+' lives; the older
    humanize law's named anti-case). Callers grading a NON-route anchor
    pass ``route_anchor=False``; the glyph and underscore rungs stay
    text-based for every anchor kind (those glyphs are never prose).
    Default True == the pre-ruling behaviour for text-only call sites.

    fixb133 M1 (default OFF) adds a WIDENED rung: router MARKER shapes —
    an intercepting marker ``(.)`` / ``( )``, an ``@slot`` word, or
    unbalanced parens. Deliberately not "any paren": an authored paren
    tail ('CalDav (Beta)') is product vocabulary the doctrine keeps, so
    only marker shapes fire. Flag unset/``0`` ⇒ this rung never runs and
    the verdict is byte-identical."""
    t = text or ""
    if _PARAM_GLYPHS.search(t):
        return True
    if route_anchor and _TRAILING_PLUS_RE.search(t):
        return True
    if any(w.startswith("_") for w in t.split(" ") if w):
        return True
    if route_marker_display_sanitize_enabled():
        from wystan.pipeline_v2.extractors._route_markers import (
            has_marker_residue,
        )

        return has_marker_residue(t)
    return False


def _strip_display_residue(text: str, vocab: Mapping[str, Any]) -> str | None:
    """Last-resort string scrub of route-template residue from a display
    (used only when no clean anchor word is available). Removes param
    glyphs, trailing ``+``, leading-underscore words, then peels edge
    single letters + re-polishes. May return ``None`` when nothing human
    remains."""
    t = _PARAM_GLYPHS.sub("", text or "")
    t = re.sub(r"\+", "", t)
    words = [w for w in t.split(" ") if w and not w.startswith("_")]
    out = _peel_edge_single_letters(" ".join(words))
    out = polish_display_casing((out or "").strip(), vocab)
    return out or None


def load_naming_vocab() -> dict[str, Any]:
    """Packaged vocabulary (cached — pure data, read once per process)."""
    global _vocab_cache
    if _vocab_cache is None:
        _vocab_cache = load_yaml(_VOCAB_FILE)
    return _vocab_cache


# ── Casing polish (acronym / brand aware — law ``acronym_case``) ────────


def polish_display_casing(text: str, vocab: Mapping[str, Any] | None = None) -> str:
    """Render known acronyms UPPERCASE and known brands in canonical
    casing, word by word; every other word (and all separators) is kept
    byte-identical. Vendor identity wins over acronym reading (a token
    present in ``brand_casing`` never uppercases via ``known_acronyms``).
    Idempotent — polishing a polished display is a no-op."""
    v = vocab or load_naming_vocab()
    acronyms = {str(a).lower() for a in (v.get("known_acronyms") or [])}
    brands = {str(k).lower(): str(val)
              for k, val in (v.get("brand_casing") or {}).items()}

    def _one(m: re.Match[str]) -> str:
        word = m.group(0)
        low = word.lower()
        if low in brands:
            return brands[low]
        if low in acronyms:
            return word.upper()
        return word

    return _WORD_RE.sub(_one, text or "")


# ── Display-name laws ───────────────────────────────────────────────────


def _verb_class_tokens(vocab: Mapping[str, Any]) -> frozenset[str]:
    """Verb-class tokens derived from the vocab's OWN data — the journey
    templates' lead words, every ``flow_verb_classes`` member, and the
    action-family verbs (a mechanism over the curated YAML, never a new
    hardcoded list). Consumers: the B69-v2 bare-verb/dev-grain-token
    display law and the Stage 6.99b rename-on-rehome resource guard."""
    out: set[str] = set()
    templates: Mapping[str, Any] = vocab.get("journey_templates") or {}
    for group in templates.values():
        for t in (group or {}).values():
            lead = str(t or "").split(None, 1)[0].strip().lower() if t else ""
            if lead:
                out.add(lead)
    for verbs in (vocab.get("flow_verb_classes") or {}).values():
        out.update(str(v).lower() for v in (verbs or []))
    out.update(_action_family_index(vocab)["verb2fam"].keys())
    return frozenset(out)


def display_law_violations(
    text: str,
    vocab: Mapping[str, Any] | None = None,
    *,
    pf_display: str | None = None,
    member_tokens: frozenset[str] | None = None,
) -> list[str]:
    """Deterministic law check for one display name. Returns the list of
    violated law ids (empty == clean). ``pf_display`` (UF checks only)
    arms the ``pf_uf_twin`` law against the journey's own capability.

    ``member_tokens`` (B70) is the set of resource tokens a row's own
    members actually anchor (singular-folded). It arms the member-evidence
    branch of the banked ``WYSTAN_NAMING_LAW`` display law: a
    verb-homonym resource that a member grounds ('download', 'webhook') is
    the THING, not the action, and a nominal remainder no member backs
    ('View mupdf') names nothing real. ``None`` (no member context at the
    call site) ⇒ the banked vocabulary behavior, byte-identical."""
    v = vocab or load_naming_vocab()
    out: list[str] = []
    t = (text or "").strip()
    if not t or len(t.replace(" ", "")) <= 1:
        out.append("single_letter")
    else:
        words = _WORD_RE.findall(t)
        if any(len(w) == 1 and w.isalpha() and not _is_interior_article(words, i)
               for i, w in enumerate(words)):
            out.append("single_letter")
    # W3.1 rider (fb3 '2025' class): a display with no letter at all —
    # bare years, error codes, counters — names nothing; candidates/pins
    # carrying it are law-dirty and fall through to the anchor-derived
    # fallback.
    if t and not any(c.isalpha() for c in t):
        out.append("digit_only")
    if _PARAM_GLYPHS.search(t):
        out.append("param")
    exts = {str(e).lower() for e in (v.get("file_extensions") or [])}
    for w in _WORD_RE.findall(t):
        m = re.search(r"\.([A-Za-z0-9]{1,5})$", w)
        if m and m.group(1).lower() in exts:
            out.append("file_stem")
            break
    # fixb104 Law-B — a display that TERMINATES in a grammatical connective
    # ('Manage member details by', 'View shared secret by', 'Manage SSH ca
    # by') names nothing: the object the connective governed was deleted by
    # a later drop rule. Codified HERE — in the law family every producer
    # already consults — because the shape is minted through THREE distinct
    # paths on the founding pair (uf_cases_split children x7,
    # route_group_recall seeds x2, an organic 6.7 row x1) and a per-producer
    # trim provably cannot cover them all (fixb103 shipped one and 10 rows
    # survived). The detector IS the shipped trim primitive — one connective
    # vocabulary (``naming_wave_r5._CONNECTORS``), never a second list — and
    # needs >= 2 words, so a solitary connective stays the business of the
    # bare-verb / single-letter laws. FLAGLESS: the OFF arm carries the
    # class too (two HIGH rows), and a mid-preposition name is a broken
    # invariant in every arm, not a behaviour choice. The law fires
    # EXACTLY when the remedy would act (:func:`_trim_stranded_tail`), so
    # a phrasal verb ('Sign in' — the R5 split's own rename target) is
    # never called dirty and no producer is ever left without a repair.
    _lows_all = [w.lower() for w in _WORD_RE.findall(t)]
    if _trim_stranded_tail(_lows_all) != _lows_all:
        out.append("stranded_connective")
    # B56-family codification, armed by WYSTAN_NAMING_LAW: a display that
    # names an ACTION without a thing ('Manage', 'Browse & manage') or whose
    # only "thing" is a dev-grain transport token ('View API', 'Manage tRPC',
    # bare 'API') is not a journey name. Strip the LEADING verb-class tokens
    # (vocab-derived — template leads + flow_verb_classes + action-family
    # verbs) and connectors; an empty remainder is ``bare_verb``, a remainder
    # made ONLY of dev-grain segments is ``devgrain_token``.
    #
    # B70 member-evidence redesign (mechanisms-over-vocabularies): the pure
    # vocabulary mechanism false-positived on verb-homonym resources
    # ('Manage download', 'Browse webhook' — download/webhook/auth all live
    # in verb classes so the strip ate them → bare) and MISSED the true
    # exhibit ('View mupdf' — mupdf is in no vocabulary). When ``member_tokens``
    # is supplied (a row's own member evidence), the strip STOPS at a token a
    # member grounds — so a grounded verb-homonym is kept as the resource — and
    # a nominal remainder no member grounds is flagged ``evidence_absent``.
    # ``member_tokens is None`` (no member context) ⇒ the banked behavior,
    # byte-identical. Armed ONLY by the banked flag; OFF ⇒ the law list is
    # byte-identical.
    if naming_law_enabled() and t:
        lows = [w.lower() for w in _WORD_RE.findall(t)]
        verb_toks = _verb_class_tokens(v)

        def _grounded(w: str) -> bool:
            if member_tokens is None:
                return False
            return w in member_tokens or _degrime_sing(w) in member_tokens

        i = 0
        while i < len(lows) and (
                (lows[i] in verb_toks and not _grounded(lows[i]))
                or lows[i] == "and"):
            i += 1
        rest = lows[i:]
        if lows and i and not rest:
            out.append("bare_verb")
        elif rest and all(w in _API_SEGS for w in rest):
            out.append("devgrain_token")
        elif (member_tokens is not None and rest
                and not any(_grounded(w) for w in rest)):
            out.append("evidence_absent")
    if pf_display is not None and t and (
        t.strip().lower() == (pf_display or "").strip().lower()
    ):
        out.append("pf_uf_twin")
    return out


def _inherit_fullname(name: str, fullname_map: Mapping[str, str]) -> str:
    """B56 §5 — replace each PF abbreviation token in a UF name with its
    ``Full Name (ABBR)`` expansion (whole word, case-insensitive, once per
    abbreviation). Never rewrites an ``(ABBR)`` already inside parentheses, and
    skips an abbreviation whose expansion the name already carries — so a
    second application is a no-op. Deterministic (abbreviations sorted)."""
    text = name
    for abbr in sorted(fullname_map):
        value = fullname_map[abbr]
        if value in text:
            continue
        pat = re.compile(
            rf"(?<![\w(]){re.escape(abbr)}(?![\w)])", re.IGNORECASE)
        m = pat.search(text)
        if m:
            text = text[:m.start()] + value + text[m.end():]
    return text


# ── Anchor-id humanization (candidate source) ───────────────────────────


def _display_word(seg: str, vocab: Mapping[str, Any]) -> str:
    """Titleized display form of one path segment (camel/kebab/snake
    split; acronym/brand cased)."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", seg)
    words = [w for w in re.split(r"[-_\s]+", spaced) if w]
    raw = " ".join(
        w if (w.isupper() and len(w) > 1) else w.capitalize() for w in words
    )
    return polish_display_casing(raw, vocab)


def _armed_acronyms_upper(display: str, vocab: Mapping[str, Any]) -> str:
    """fixb147 — whole-token UPPERCASE for the ARMED initialism lane.

    HISTORY: 'js' and 'rsc' could not be added straight to the shipped
    ``known_acronyms`` table while the fixb147 flag was armed, because
    that table is read by EVERY display path while the scan cache key
    hashes ``KEY_SCHEMA`` + ``ENV_OUTPUT_FLAGS`` values, never this
    file's bytes — displays would have moved on every board under an
    unchanged key (the hazard ``display-lexicon.yaml``'s
    ``armed_expansions`` lane documents). So the addition staged in
    ``armed_acronyms``, applied by THIS rung only. **Flip-pack №46
    (KEY_SCHEMA 81, 2026-08-14) promoted both into ``known_acronyms``**
    under the bump, so the global lane casts them now too.

    This rung SURVIVES the promotion rather than becoming dead code: the
    two lanes read different word boundaries. ``polish_display_casing``
    walks ``_WORD_RE`` (``[A-Za-z0-9][A-Za-z0-9.\\-]*``), so a dotted or
    hyphenated display is ONE word to it; this rung walks
    ``[A-Za-z0-9]+`` and still reaches a token behind that punctuation.
    Narrowing it to a no-op is therefore a behaviour change, not cleanup.

    Word-wise, exact token match only — the same rule
    ``pf_display_doctrine.uppercase_acronyms`` uses, so 'JavaScript'
    can never be shouted at by a 'js' entry."""
    toks = {
        str(w).strip().lower()
        for w in (vocab.get("armed_acronyms") or []) if str(w).strip()
    }
    if not toks or not display:
        return display
    return re.sub(
        r"[A-Za-z0-9]+",
        lambda m: m.group(0).upper() if m.group(0).lower() in toks
        else m.group(0),
        display,
    )


def _meaningful_segments(path: str, vocab: Mapping[str, Any]) -> list[str]:
    """Author-meaningful display words of an anchor-id path: route groups
    unwrap to their word; params, api/version segments, and structural
    code-location segments drop.

    With ``WYSTAN_HUMANIZE_ROUTE_NAMES`` on (B2, default) the walk is
    router-template aware — Remix ``+``/``$``/``_layout``/``[escape]``/dot
    notation is normalized (see ``_route_meaningful_segments``). ``=0``
    restores this legacy body byte-identically."""
    if humanize_route_names_enabled():
        return _route_meaningful_segments(path, vocab)
    structural = {str(s).lower() for s in (vocab.get("structural_segments") or [])}
    hub_containers = {str(s).lower()
                      for s in (vocab.get("hub_container_segments") or [])}
    exts = {str(e).lower() for e in (vocab.get("file_extensions") or [])}
    out: list[str] = []
    for seg in (path or "").split("/"):
        s = seg.strip()
        if not s:
            continue
        g = _GROUP_SEG.match(s)
        if g:
            s = g.group(1).strip()
            if not s:
                continue
        if _DYNAMIC_SEG.match(s) or _VERSION_SEG.match(s):
            continue
        # File-anchor leaf segments carry an extension ("schema.json") —
        # the display word is the stem (the file_stem law forbids the
        # extension in any display).
        m = re.match(r"^(.+)\.([A-Za-z0-9]{1,5})$", s)
        if m and m.group(2).lower() in exts:
            s = m.group(1)
        low = s.lower()
        if low in structural or low in hub_containers or low in _API_SEGS:
            continue
        out.append(s)
    return out


def _route_meaningful_segments(
    path: str, vocab: Mapping[str, Any],
) -> list[str]:
    """Router-template-aware meaningful segments (B2). Each ``/``-segment
    is normalized per the detected router family; structural / hub /
    extension leaves drop; api / version / tenant-scope tokens are
    TRANSPARENT only when a deeper meaningful token exists (mirrors
    ``spine_anchors._pattern_key_chain`` — ``/workspaces/{id}/tables`` →
    "Tables", but a terminal ``/api`` or ``/t/$teamUrl`` still keys its
    own surface). Never returns empty when any token survives."""
    structural = {str(s).lower() for s in (vocab.get("structural_segments") or [])}
    hub_containers = {str(s).lower()
                      for s in (vocab.get("hub_container_segments") or [])}
    exts = {str(e).lower() for e in (vocab.get("file_extensions") or [])}
    tenant_scope = {
        str(s).lower() for s in (vocab.get("tenant_scope_segments") or [])
    }
    dialect = _route_dialect(path)

    tokens: list[str] = []
    for seg in (path or "").split("/"):
        tok = _normalize_route_segment(seg, dialect, vocab)
        if tok is None:
            continue
        # File-anchor leaf extension ("schema.json") → stem (file_stem law).
        m = re.match(r"^(.+)\.([A-Za-z0-9]{1,5})$", tok)
        if m and m.group(2).lower() in exts:
            tok = m.group(1)
        low = tok.lower()
        if low in structural or low in hub_containers:
            continue
        tokens.append(tok)

    def _transparent(i: int) -> bool:
        low = tokens[i].lower()
        if not (low in _API_SEGS or _VERSION_SEG.match(low)
                or low in tenant_scope):
            return False
        # transparent only if a deeper NON-transparent token follows.
        for j in range(i + 1, len(tokens)):
            lj = tokens[j].lower()
            if not (lj in _API_SEGS or _VERSION_SEG.match(lj)
                    or lj in tenant_scope):
                return True
        return False

    out = [t for i, t in enumerate(tokens) if not _transparent(i)]
    if not out and tokens:
        out = [tokens[-1]]
    return out


def _anchor_path(anchor_id: str) -> tuple[str, str]:
    """``(source, path)`` of a canonical anchor id (``route:apps/x`` →
    ``("route", "apps/x")``). Unknown shapes → ``("", anchor_id)``."""
    aid = anchor_id or ""
    if ":" in aid:
        src, _, rest = aid.partition(":")
        return src, rest
    return "", aid


def humanize_anchor_display(
    anchor_id: str, vocab: Mapping[str, Any],
) -> tuple[str | None, str | None]:
    """``(base, qualifier)`` display words derived from an anchor id.

    ``base`` is the last author-meaningful segment ("Discord" for
    ``route:apps/web/src/app/(landing)/(redirect)/discord``); ``qualifier``
    is the nearest meaningful ancestor ("Redirect") — used only when the
    bare base would collide with another display. ``(None, None)`` when
    the id yields no meaningful words (fallback = current display).

    fixb133 M1.3 (default OFF) vetoes a qualifier that came from an
    ORGANISATIONAL route group: ``(use-page-wrapper)`` names the wrapper,
    not the product area, so 'Auth (Use Page Wrapper)' loses its
    decoration and the honest 'Auth' stands (doctrine law 7). The veto is
    display-only — ``route_groups_of`` metadata is untouched."""
    src, path = _anchor_path(anchor_id)
    if not src:
        return None, None
    segs = _meaningful_segments(path, vocab)
    if not segs:
        return None, None
    base = _display_word(segs[-1], vocab)
    qual = _display_word(segs[-2], vocab) if len(segs) >= 2 else None
    if humanize_route_names_enabled():
        base = _peel_edge_single_letters(base) or ""
        qual = _peel_edge_single_letters(qual)
    if (qual and route_marker_display_sanitize_enabled()
            and _is_junk_group_word(qual, path, vocab)):
        qual = None
    if qual and base and pf_route_qualifier_rung_enabled():
        # fixb133 N7, self-qualification arm (live-fire defect 2026-08-09,
        # cal.com app-store): a nested same-name segment
        # (``…/alby/api/alby``, ``…/paypal/lib/PayPal``) makes the nearest
        # ancestor RESTATE the base, and every ``<Base> (<Qualifier>)``
        # compose site downstream then emitted 'Alby (alby)' /
        # 'PayPal (PayPal)'. A qualifier that restates its base carries
        # zero information, so it is dropped HERE — one predicate covers
        # all five compose sites. Case- and formatting-insensitive, so the
        # camel-vs-lower spelling pair is caught; 'Edit (Admin)' — a
        # qualifier that genuinely differs — is untouched.
        from wystan.pipeline_v2.pf_display_doctrine import same_phrase

        if same_phrase(base, qual):
            qual = None
    return (base or None), (qual or None)


def _is_junk_group_word(qual: str, path: str, vocab: Mapping[str, Any]) -> bool:
    """True when ``qual`` is the display word of a route group that may NOT
    decorate a display (fixb133 M1.3). Group-scoped: a plain directory that
    happens to be called 'main' is not vetoed — only an author-declared
    ``(group)`` segment is.

    Warden №37 blocker 2: the test is now the SAME domain-noun test the M2
    parent walk applies (:func:`pf_display_doctrine.is_category_group`), so
    the access-control class is vetoed by mechanism rather than by a list —
    ``(org-admin-only)`` is a multi-word PREDICATE, not a category, and can
    no longer produce 'Attributes Org Admin Only'."""
    from wystan.pipeline_v2.extractors._route_markers import route_group_inner
    from wystan.pipeline_v2.pf_display_doctrine import is_category_group

    folded = (qual or "").strip().lower()
    if not folded:
        return False
    for seg in (path or "").split("/"):
        inner = route_group_inner(seg.strip())
        if inner is None:
            continue
        if _display_word(inner, vocab).strip().lower() != folded:
            continue
        if not is_category_group(
            inner, lambda s: _is_transparent_ancestor(s, vocab),
        ):
            return True
    return False


def _route_qualified_candidate(
    anchor_id: str, vocab: Mapping[str, Any],
) -> tuple[str, str]:
    """fixb133 M2 — ``(display, qualifier)`` for the ``static-route-qualified``
    ladder candidate, or ``("", "")`` (flag off / non-route / no evidence).

    The qualifier travels with the candidate so the ladder can RECORD which
    tokens the rung injected — the attribution consumers subtract them
    (warden №37 blocker 1).

    The base comes from :func:`humanize_anchor_display` (which already
    carries the M1 sanitize when THAT flag is armed); the qualifier is the
    anchor's own parent resource or category route-group. When the anchor
    supplies neither, the honest base stands — this returns ``""`` and the
    ladder falls through (doctrine law 7)."""
    if not pf_route_qualifier_rung_enabled():
        return "", ""
    from wystan.pipeline_v2.pf_display_doctrine import route_qualified_display

    base, _qual = humanize_anchor_display(anchor_id, vocab)
    if not base:
        return "", ""
    verdict = route_qualified_display(
        anchor_id, base,
        word_of=lambda seg: _display_word(seg, vocab),
        is_transparent=lambda seg: _is_transparent_ancestor(seg, vocab),
    )
    return (verdict[0], verdict[2]) if verdict else ("", "")


def _undressed_base(pf: Any, display: str) -> str:
    """``display`` with the M2 rung's INJECTED qualifier words removed.

    The confidence / evidence channels must judge the PF's own word, not a
    word the engine wrote (warden №37 blocker 3). Identity when the rung is
    off or the row was never dressed."""
    from wystan.pipeline_v2.pf_display_doctrine import (
        display_qualifier_stops,
        strip_qualifier_tokens,
    )

    stops = display_qualifier_stops(pf)
    return strip_qualifier_tokens(display, stops) if stops else display


def _is_transparent_ancestor(seg: str, vocab: Mapping[str, Any]) -> bool:
    """True when a path segment names no DOMAIN resource — api/rpc class, a
    version dir, a structural code-location word (``src``/``app``/
    ``packages``), or a hub container (``providers``/``plugins``).

    Tenant-scope words (``team``/``workspace``/``org``) are deliberately
    NOT transparent here: they are real domain nouns and make a legitimate
    parent qualifier ("Team Members"). Used by the fixb133 M2 rung.
    """
    low = (seg or "").strip().lower()
    if not low:
        return True
    if low in _API_SEGS or _VERSION_SEG.match(low):
        return True
    structural = {str(s).lower() for s in (vocab.get("structural_segments") or [])}
    hub_containers = {
        str(s).lower() for s in (vocab.get("hub_container_segments") or [])
    }
    return low in structural or low in hub_containers


def hub_composition_display(
    anchor_id: str, current_display: str, vocab: Mapping[str, Any],
    *,
    vendor_display: str | None = None,
) -> str | None:
    """"<Family> — <Vendor>" for a ``hub:<dir>/<vendor>`` anchor
    (Product-Spine §4.8 hub composition). ``None`` for non-hub anchors
    and hub CORE anchors (whose family display already carries "Core").

    ``vendor_display`` (B27) — the vendor word from the package's OWN
    declared metadata; when supplied it replaces the current-display
    vendor word so the family decoration keeps composing
    ("App Store — Stripe"). ``None`` (the default) is byte-identical to
    the pre-B27 composition.

    fixb133 N7 (``WYSTAN_PF_ROUTE_QUALIFIER_RUNG``, default OFF) — THE
    stutter compose site. When ``current_display`` is itself ALREADY a
    composition ("App Store — Attio", from an earlier display pass), this
    function re-composed it into "App Store — App Store — Attio". The
    dedupe collapses the repeated family part; flag unset/``0`` reproduces
    the stuttering composition byte for byte."""
    src, path = _anchor_path(anchor_id)
    if src != "hub":
        return None
    segs = [s for s in (path or "").split("/") if s]
    if len(segs) < 2:
        return None
    family_segs = _meaningful_segments("/".join(segs[:-1]), vocab)
    if not family_segs:
        return None
    family = _display_word(family_segs[-1], vocab)
    vendor = vendor_display or polish_display_casing(current_display, vocab)
    if not family or not vendor:
        return None
    if vendor.strip().lower() == family.strip().lower():
        return None  # degenerate (vendor dir == family dir)
    composed = f"{family} — {vendor}"
    if pf_route_qualifier_rung_enabled():
        from wystan.pipeline_v2.pf_display_doctrine import dedupe_stutter

        composed = dedupe_stutter(composed)
    return composed


def _package_manifest_display(
    anchor_id: str, vocab: Mapping[str, Any], repo_root: Any,
    current_display: str = "",
) -> tuple[str | None, str]:
    """B27 — ``(display, source)`` for a package-dir-anchored PF from the
    package's OWN declared metadata; ``(None, "")`` when the flag is off,
    no repo root is available, the anchor is not a package dir, or no
    rung yields a name.

    ``source`` is ``"manifest"`` (an authored metadata name — used
    verbatim, casing-polished) or ``"wordsplit"`` (the mechanical
    letter/digit split of the dir slug — strictly the rung below).

    A hub CORE (designed "<Family> Core" display — same convention
    :func:`build_uf_candidates` keys on) never takes a manifest name:
    the family dir's own metadata names the FAMILY package, not the
    core capability."""
    if repo_root is None or not pf_manifest_name_enabled():
        return None, ""
    src, _path = _anchor_path(anchor_id)
    if src == "hub" and " Core" in (current_display or ""):
        return None, ""
    pkg_dir = package_dir_of_anchor(anchor_id)
    if not pkg_dir:
        return None, ""
    authored = manifest_display_name(repo_root, pkg_dir)
    if authored:
        if authored == authored.lower() and " " not in authored:
            # A slug-cased authored name ("report-studio") is authored
            # NAMING, not authored CASING — titleize it like any path
            # word; an intentionally-cased name (WipeMyCal, Close.com)
            # ships verbatim (casing-polished).
            return _display_word(authored, vocab), "manifest"
        return polish_display_casing(authored, vocab), "manifest"
    # fixb147 rung B — the npm SCOPE as identity when the scope-stripped
    # remainder is DEGENERATE (``@novu/js`` at ``packages/js``: rung 4
    # rightly refuses "the path spelled twice", and 'Js' is not a
    # product name either). Manifest-derived, so it ranks with the
    # manifest rungs and strictly ABOVE the mechanical word split.
    # Non-degenerate remainders are untouched — the anti-repo-echo
    # boundary. Flag OFF ⇒ no read ⇒ byte-identical.
    if ws_anchor_identity_enabled():
        scoped = scope_identity_slug(repo_root, pkg_dir)
        if scoped:
            return (_armed_acronyms_upper(_display_word(scoped, vocab), vocab),
                    "manifest")
    split = word_split_slug(pkg_dir.rsplit("/", 1)[-1])
    if split:
        return _display_word(split, vocab), "wordsplit"
    return None, ""


# ── PF dev-grain suffix law (B16 — display channel only) ────────────────


def _anchor_terminal_segment(anchor_id: str) -> str | None:
    """Last author-meaningful dir segment of a ``route:`` anchor
    ('policy-page' for 'route:policy-page'); ``None`` for non-route anchors
    or when only params remain. Route groups unwrap ('(dashboard)' ->
    'dashboard'); param/dynamic segments ('[id]', '$teamUrl') are skipped."""
    src, path = _anchor_path(anchor_id)
    if src != "route":
        return None
    for seg in reversed((path or "").split("/")):
        s = seg.strip()
        if not s:
            continue
        if _DYNAMIC_SEG.match(s):
            continue
        g = _GROUP_SEG.match(s)
        if g:
            s = g.group(1).strip()
            if not s:
                continue
        return s
    return None


def _strip_pf_devgrain_suffix(
    display: str, anchor_id: str, vocab: Mapping[str, Any],
) -> str | None:
    """The dev-grain-suffix-stripped display, or ``None`` if nothing to
    strip.

    Anchor-form-driven (never token-blind): the display's TRAILING word W
    (one of :data:`_PF_DEVGRAIN_SUFFIX_TOKENS`) is stripped ONLY when the
    route anchor's terminal dir segment ENDS with ``-W`` — i.e. the token is
    a repo-dir-naming leak ('policy-page' -> 'Policy Page' -> 'Policy';
    'investigation-flow' -> 'Investigation Flow' -> 'Investigation'). 'flow'
    is therefore stripped ONLY behind a ``route:*-flow`` anchor (the
    capability "Investigation Flow" vs a flow-suffix leak is decided by the
    anchor form, per operator brief). Guards: 'Landing Page Builder' (anchor
    '*-builder', trailing word 'Builder') is untouched; a bare "Page" (single
    word, or a strip that would leave nothing / a single letter) is kept."""
    terminal = _anchor_terminal_segment(anchor_id)
    if not terminal:
        return None
    tl = terminal.lower()
    tok = next(
        (w for w in sorted(_PF_DEVGRAIN_SUFFIX_TOKENS) if tl.endswith("-" + w)),
        None,
    )
    if tok is None:
        return None
    words = (display or "").split()
    if len(words) < 2 or words[-1].lower() != tok:
        return None
    stripped = " ".join(words[:-1]).strip()
    if not stripped or len(stripped.replace(" ", "")) <= 1:
        return None
    if display_law_violations(stripped, vocab):
        return None
    polished = polish_display_casing(stripped, vocab)
    return polished if polished.strip().lower() != (display or "").strip().lower() else None


def _apply_pf_devgrain_law(
    chosen: str,
    anchor_id: str,
    slug: str,
    vocab: Mapping[str, Any],
    taken: Mapping[str, str],
    tele: dict[str, Any],
) -> tuple[str, bool]:
    """Return ``(display, stripped?)`` after the PF dev-grain suffix law.

    A clean strip fires when the stripped capability name is still UNIQUE.
    On a post-strip COLLISION — the stripped name is already claimed by a
    sibling PF (a fragmented capability: 'Detections Page' -> 'Detections'
    == existing route:detection) — the current display is kept UNCHANGED
    (never a duplicate, never a qualifier) and recorded as the Part-2
    unification signal. Doctrine: LAW > PIN; display channel only; the
    existing PF-vs-PF uniqueness law (``taken``) decides the collision."""
    stripped = _strip_pf_devgrain_suffix(chosen, anchor_id, vocab)
    if not stripped:
        return chosen, False
    folded = stripped.strip().lower()
    if folded in taken:
        tele["pf_devgrain_collision"] = tele.get("pf_devgrain_collision", 0) + 1
        tele.setdefault("pf_devgrain_collision_samples", []).append({
            "slug": slug,
            "anchor_id": anchor_id,
            "kept": chosen,
            "would_be": stripped,
            "collides_with": taken.get(folded),
        })
        return chosen, False
    tele["pf_devgrain_stripped"] = tele.get("pf_devgrain_stripped", 0) + 1
    return stripped, True


def _ident_fold(s: str) -> str:
    """Identity fold used by the R5-1 parity law: lowercase + drop every
    non-alphanumeric glyph, so a display ('Status Pages') and a canonical
    slug ('status-pages') compare equal ('statuspages'). Distinct from the
    ``taken`` display fold (which keeps internal spaces) — this axis is
    identity, not display uniqueness."""
    return re.sub(r"[^a-z0-9]+", "", (s or "").strip().lower())


def _identity_parity_repair(
    chosen: str,
    anchor_id: str,
    slug: str,
    vocab: Mapping[str, Any],
    taken: Mapping[str, str],
    pf_slug_idents: set[str],
) -> str | None:
    """R5-1 — replace an identity-parity-colliding PF display with a lawful,
    non-colliding one.

    A PF display whose identity-fold equals ANOTHER live PF's canonical slug
    ('Settings' on the ``general`` PF == the ``settings`` PF's identity) or a
    display already claimed by an earlier PF wears another feature's identity
    — trust-breaking. The repair prefers the humanized OWN-slug word (the
    honest identity — always non-colliding since slugs are unique), then the
    anchor ``"<Base> (<Qualifier>)"`` form, then the bare anchor base. Returns
    ``None`` when no lawful non-colliding repair exists (caller keeps the
    current as never-worse debt). Display channel only.

    fixb134 M4c (``WYSTAN_R5_REPAIR_NO_SELF``, default OFF): the
    own-slug rung reads the row's SLUG, so while that slug still carries
    the mint's self-qualifier ('alby-(alby)' — M4b migrates ids at
    EMISSION, i.e. after this pass) the repair handed the stutter back as
    a "lawful" display. Armed, a self-restating candidate is refused and a
    DISTINGUISHING-ancestor rung is inserted: 'Alby (Integrations)' folds
    to 'albyintegrations', which is not the sibling's slug, so
    identity-parity is SATISFIED — the law is not weakened, it is served
    by a better candidate. Walk empty ⇒ the remaining rungs run exactly as
    before (bare 'Alby' still fails parity against the sibling slug, so it
    is never the answer)."""
    own = _ident_fold(slug)
    _no_self = r5_repair_no_self_enabled()

    def _stutters(cand: str) -> bool:
        from wystan.pipeline_v2.pf_display_doctrine import dedupe_stutter

        return dedupe_stutter(cand) != cand

    def _demarker(cand: str | None) -> str | None:
        """fixb137 — the repair's own-slug rung reads the SLUG, so while
        that slug still carries a router marker ('@chat'; M4b migrates ids
        at EMISSION, i.e. LATER) the repair handed the marker straight back
        onto the display. That is producer #2 of the @slot-display class:
        the B71 ladder had already cleaned it to 'Chat' and this pass
        overwrote it. Reuses the ONE sanitizer (no duplication)."""
        if not cand or not route_marker_display_sanitize_enabled():
            return cand
        from wystan.pipeline_v2.extractors._route_markers import (
            has_marker_residue,
            sanitize_display_text,
        )

        if not has_marker_residue(cand):
            return cand
        scrubbed = sanitize_display_text(cand)
        if not scrubbed:
            return None
        # Titlecase the peeled word before polish, exactly as
        # clean_route_grammar_display does — a slug-derived word arrives
        # lowercase ('@chat' -> 'chat') and polish alone does not case it.
        titled = " ".join(
            (w[:1].upper() + w[1:]) if (w and w[0].islower()) else w
            for w in scrubbed.split()
        )
        return polish_display_casing(titled, vocab)

    def _ok(cand: str | None, *, no_self: bool = False) -> bool:
        if not cand or display_law_violations(cand, vocab):
            return False
        if no_self and _stutters(cand):
            return False
        low = cand.strip().lower()
        if low in taken and taken.get(low) != slug:
            return False
        ci = _ident_fold(cand)
        return not (bool(ci) and ci != own and ci in pf_slug_idents)

    def _ladder(*, no_self: bool) -> str | None:
        from_slug = _demarker(_display_word(slug, vocab) if slug else None)
        if _ok(from_slug, no_self=no_self):
            return from_slug
        base, qual = humanize_anchor_display(anchor_id, vocab)
        if no_self and base:
            # fixb134 M4c — the DISTINGUISHING-ancestor rung. It repairs
            # parity with a candidate that also satisfies the stutter law:
            # 'Alby (Integrations)' folds to 'albyintegrations', which is
            # not the sibling's 'alby'. Parity is SERVED, never weakened.
            from wystan.pipeline_v2.pf_display_doctrine import (
                distinguishing_ancestor,
            )

            alt = distinguishing_ancestor(anchor_id, base)
            if alt:
                altw = re.sub(r"[^A-Za-z0-9]+", " ", alt).strip().title()
                cand = f"{base} ({altw})" if altw else None
                if _ok(cand, no_self=no_self):
                    return cand
        bq = _demarker(f"{base} ({qual})" if base and qual else None)
        if _ok(bq, no_self=no_self):
            return bq
        base = _demarker(base)
        if _ok(base, no_self=no_self):
            return base
        return None

    if _no_self:
        # PREFERENCE, not an absolute ban: run the whole ladder with the
        # stutter law armed first. If NOTHING lawful survives it, fall back
        # to the unfiltered ladder — never-worse. Banning outright made the
        # walk-empty corner land on a BARE display that wears the sibling's
        # identity, i.e. it traded a doctrine defect for a parity defect.
        repaired = _ladder(no_self=True)
        if repaired is not None:
            return repaired
    return _ladder(no_self=False)


def _strip_devgrain_words(words: list[str]) -> list[str]:
    """Drop EVERY trailing dev-grain word ('Overview Page' -> 'Overview').

    Comparison-side helper for the B16-P1b echo prong: both sides of the
    echo test are folded the same way, so 'Overview Page' and 'overview'
    meet. Distinct from ``uf_name_deglue.strip_devgrain_tail`` (which drops
    exactly ONE word and floors the phrase) — that one BUILDS a display,
    this one only normalises for a comparison and never reaches a name."""
    out = list(words)
    while out and str(out[-1]).strip().lower() in _PF_DEVGRAIN_SUFFIX_TOKENS:
        out = out[:-1]
    return out


def _uf_devgrain_pf_echo(name: str, pf_display: str) -> bool:
    """B16-P1b echo prong — the journey name (minus its LEAD verb, minus
    dev-grain words) IS its home PF's display (minus dev-grain words),
    ±plural.

    This is the discriminator that separates a repo-dir leak from a real
    product noun: 'Manage overview page' on PF 'Overview Page' says the
    same thing twice, while 'Send secret page' on PF 'Share Secret Page'
    (infisical OFF, **high**) and 'Unsubscribe from status page' on PF
    'Status Page' name a THING the product ships. Identity-folded through
    the existing :func:`_ident_fold` — no second normaliser."""
    words = (name or "").split()
    if len(words) < 2:
        return False
    rest = _ident_fold(" ".join(_strip_devgrain_words(words[1:])))
    pfn = _ident_fold(" ".join(_strip_devgrain_words((pf_display or "").split())))
    if not rest or not pfn:
        return False
    return rest == pfn or rest + "s" == pfn or rest == pfn + "s"


def _fold_canonical_verb_priority_on() -> bool:
    """fixb136 flag, read through a lazy import (``uf_synth_fold`` imports
    this module's siblings, so the edge stays one-way at import time)."""
    from wystan.pipeline_v2.uf_synth_fold import (
        fold_canonical_verb_priority_enabled,
    )
    return fold_canonical_verb_priority_enabled()


def _strip_uf_devgrain_suffix(
    name: str, home_anchor: str, vocab: Mapping[str, Any],
    *, pf_display: str | None = None,
    taken: Mapping[str, str] | None = None,
    uf_id: str | None = None,
) -> str | None:
    """B16 Part-1b — the dev-grain-suffix-stripped UF name, or ``None``.

    Mirrors the PF law for ``UserFlow.name``: strip the TRAILING dev-grain
    word W (page/screen/view/flow) from a journey name ("View detections
    page" -> "View detections") ONLY when the journey's HOME PF anchor's
    terminal route dir ends ``-W`` — i.e. the token is the same route-dir
    leak the PF carried. Guard (the "Publish page" anti-case): the strip
    must leave a verb+object phrase (>= 2 words), so a 2-word "Publish page"
    (whose home is a page-builder PF, not ``route:*-page``, and which would
    strip to a bare verb) is never mutilated — anchor-form AND arity gated.

    fixb104 — CASE-BOUNDARY rung. A dir segment declares its own words in
    one of TWO forms, and this law read only one of them: 'policy-page'
    (separator) opened the gate, 'OverviewPage' (case) never did — so
    'Manage overview page' on PF 'Overview Page'
    (``route:frontend/src/pages/kms/OverviewPage``) and 'View resource
    overview page' on PF 'Resource Overview' shipped the leak on infisical
    ON. The second rung reads the terminal segment's OWN case boundaries
    (``uf_name_deglue.deglue_words`` — the same "invent nothing" tokenizer
    the de-glue uses, so a genuinely flat 'overviewpage' declares ONE word
    and the gate stays shut) and, because it is the NEW evidence form,
    additionally requires the PF echo (:func:`_uf_devgrain_pf_echo`). The
    banked separator rung is untouched and needs no echo. ``pf_display``
    unset ⇒ the case rung cannot fire ⇒ byte-identical for callers that do
    not pass it.

    ``taken`` (``{folded display: uf id}``) is consulted by the CASE rung
    ONLY, and it is the reason that rung cannot manufacture a duplicate:
    infisical ON carries UF-200 'View resource overview' beside UF-208
    'View resource overview page' on the SAME PF, so the strip would have
    collapsed two live rows onto one display (uf-dup-names 1 -> 2). The PF
    sibling law's ruling applies verbatim — on a post-strip collision the
    CURRENT display is kept and the collision is recorded as the Part-2
    unification signal; a duplicate display is never minted, and the
    fragmentation is a MEMBERSHIP question this module may not answer."""
    terminal = _anchor_terminal_segment(home_anchor)
    if not terminal:
        return None
    tl = terminal.lower()
    tok = next(
        (w for w in sorted(_PF_DEVGRAIN_SUFFIX_TOKENS) if tl.endswith("-" + w)),
        None,
    )
    case_rung = False
    # ── fixb136 RIDER — the ECHO rung (verb-led '<verb> <pf-noun> page') ──
    # World residue the two banked rungs cannot reach: both are gated on
    # the HOME ANCHOR's terminal segment (separator 'policy-page', or a
    # PascalCase 'OverviewPage' dir), so a journey whose PF is anchored
    # somewhere else keeps the leak. Live exhibits: infisical 'Manage
    # overview page' on PF 'Overview Page', linkwarden 'View preserved
    # page' on 'Preserved', strapi 'View no content type page' on 'No
    # Content Type'.
    #
    # The discriminator is the one the B16-P1b law already trusts and
    # already ships — :func:`_uf_devgrain_pf_echo`: the name minus its
    # LEAD VERB and minus dev-grain words must BE the PF display (±plural).
    # That is what separates a repo-dir leak from a product noun, and it
    # is why openstatus 'Unsubscribe from status page' survives untouched
    # ('from status' is not the PF 'Status Page'). Verb-led only, so the
    # bare-noun shapes stay with the de-glue lane, and the >=3-word arity
    # floor below still guarantees a verb+object remainder. Post-strip
    # collision keeps the CURRENT display (the sibling ruling, verbatim).
    # Rides this pack's flag; unset/0 ⇒ the rung never opens.
    if (tok is None and pf_display
            and _fold_canonical_verb_priority_on()):
        _echo_words = (name or "").split()
        if (len(_echo_words) >= 3
                and _echo_words[-1].lower() in _PF_DEVGRAIN_SUFFIX_TOKENS
                and _lead_token(name) in _verb_class_tokens(vocab)
                and _uf_devgrain_pf_echo(name, pf_display)):
            tok = _echo_words[-1].lower()
            case_rung = True          # shares the collision guard
    if tok is None and pf_display:
        # Local import: ``uf_name_deglue`` imports this module's frozen
        # dev-grain token set, so the edge must stay one-way at import time.
        from wystan.pipeline_v2.uf_name_deglue import deglue_words
        declared = deglue_words(terminal)
        if (len(declared) >= 2
                and declared[-1] in _PF_DEVGRAIN_SUFFIX_TOKENS
                and _uf_devgrain_pf_echo(name, pf_display)):
            tok = declared[-1]
            case_rung = True
    if tok is None:
        return None
    words = (name or "").split()
    if len(words) < 3 or words[-1].lower() != tok:
        return None   # need verb + object + devgrain (>=3) -> leaves >=2
    stripped = " ".join(words[:-1]).strip()
    if display_law_violations(stripped, vocab):
        return None
    polished = polish_display_casing(stripped, vocab)
    if case_rung and taken is not None:
        owner = taken.get(polished.strip().lower())
        if owner is not None and owner != (uf_id or ""):
            return None   # post-strip collision — keep the current display
    return polished if polished.strip().lower() != (name or "").strip().lower() else None


# ── Nav-label channel (authored labels; product_strings nav pairs) ──────


def _nav_label_votes(
    product_features: Iterable[Any],
    product_strings: Any,
    routes_index: Iterable[Mapping[str, Any]] | None,
) -> dict[str, dict[str, int]]:
    """``{pf_slug: {authored nav label: votes}}`` — a nav pair (label,
    href) votes for the PF that owns the route FILE its normalized href
    resolves to. Shared vote machinery for :func:`nav_labels_for_pfs`
    (one top label per PF — the B40 nav rung) and
    :func:`nav_label_sets_for_pfs` (ALL voted labels per PF — the B57
    nav-cluster rung). Empty on scans without a product-string index
    (keyless suppressed paths) — the channel is optional by
    construction."""
    pairs_by_file: Mapping[str, list[tuple[str, str | None]]] = (
        getattr(product_strings, "nav_pairs_by_file", None) or {}
    )
    if not pairs_by_file or not routes_index:
        return {}
    try:
        from wystan.pipeline_v2.product_strings import normalize_href
    except ImportError:  # pragma: no cover — same package
        return {}

    file_by_pattern: dict[str, str] = {}
    for r in routes_index:
        pat = str(r.get("pattern") or "").strip()
        f = str(r.get("file") or "").strip()
        if pat and f and pat not in file_by_pattern:
            file_by_pattern[pat] = f

    pf_by_path: dict[str, str] = {}
    for pf in product_features:
        slug = str(getattr(pf, "name", "") or "")
        for p in (getattr(pf, "paths", None) or []):
            pf_by_path.setdefault(str(p), slug)

    # Shell words never name anything (§4.2 — HomePage doctrine): a nav
    # label that is itself a shell slug ("Home", "Dashboard") is not an
    # authored capability label. Best-effort — classifier faults skip
    # the guard, never the channel.
    _shell_check = None
    try:
        from wystan.pipeline_v2.surface_taxonomy import (
            SurfaceScopeClassifier,
        )
        _shell_check = SurfaceScopeClassifier().is_shell_name
    except Exception:  # noqa: BLE001 — optional guard
        _shell_check = None

    votes: dict[str, dict[str, int]] = {}
    for pairs in pairs_by_file.values():
        for label, href in pairs:
            if not label or not href:
                continue
            lab = " ".join(str(label).split())
            if not (1 <= len(lab.split()) <= 4) or len(lab) > 40:
                continue
            if _shell_check is not None and _shell_check(lab):
                continue
            norm = normalize_href(str(href)) or ""
            if not norm:
                continue
            route_file = file_by_pattern.get(norm)
            if not route_file:
                continue
            owner_slug = pf_by_path.get(route_file)
            if not owner_slug:
                continue
            votes.setdefault(owner_slug, {})
            votes[owner_slug][lab] = votes[owner_slug].get(lab, 0) + 1
    return votes


def nav_labels_for_pfs(
    product_features: Iterable[Any],
    product_strings: Any,
    routes_index: Iterable[Mapping[str, Any]] | None,
) -> dict[str, str]:
    """``{pf_slug: authored nav label}`` — one deterministic label per
    PF: most votes → shortest → alpha (see :func:`_nav_label_votes`)."""
    votes = _nav_label_votes(product_features, product_strings, routes_index)
    out: dict[str, str] = {}
    for slug, labs in votes.items():
        best = sorted(
            labs.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]),
        )[0][0]
        out[slug] = best
    return out


def nav_label_sets_for_pfs(
    product_features: Iterable[Any],
    product_strings: Any,
    routes_index: Iterable[Mapping[str, Any]] | None,
) -> dict[str, list[str]]:
    """B57 Seg1 (a) — ``{pf_slug: ALL voted authored nav labels}``,
    sorted for determinism. The existing B40 nav rung consumes only the
    one top-voted label per PF (:func:`nav_labels_for_pfs`); the
    nav-cluster rung lets EVERY label the authors voted onto the PF
    ground a UF resource — same votes, same guards (shell filter, length
    bounds), wider read. New function beside the old one — the B40
    channel is untouched."""
    votes = _nav_label_votes(product_features, product_strings, routes_index)
    return {slug: sorted(labs) for slug, labs in sorted(votes.items())}


# ── Display-cross evidence gate (B71 provenance-ladder consumer) ────────
#
# A NEW consumer of the SAME ungated ``_nav_label_votes`` machinery — the
# B40 nav-pinning rung (:func:`nav_labels_for_pfs`) and the B57 nav-cluster
# rung (:func:`nav_label_sets_for_pfs`) are untouched. Gated behind
# ``WYSTAN_PF_DISPLAY_EVIDENCE_GATE`` (default ON since the 2026-07-21
# pack-2 flip, KEY_SCHEMA 33; explicit =0 stays the kill-switch): the raw
# top-voted
# label can be a FOREIGN capability (a nav link whose href first-come-owns a
# borrowed route file — cal ``insights`` display 'Bookings'), which the
# provenance ladder then installs as the PF display. The gate keeps a label
# only on identity evidence, tie-breaks equal votes toward the PF's own
# anchor page, and title-cases the survivor.

_GATE_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_GATE_SPLIT = re.compile(r"[^A-Za-z0-9]+")


def _gate_stem(token: str) -> str:
    """Light plural stem ('features'->'featur', 'apps'->'app') — the census
    predicate's stem, so the gate and the forensic agree token-for-token."""
    t = token.lower()
    if len(t) > 3 and t.endswith("es"):
        return t[:-2]
    if len(t) > 2 and t.endswith("s"):
        return t[:-1]
    return t


def _gate_tokens(text: str) -> set[str]:
    """Stemmed identity tokens of a string: camelCase + non-alnum split,
    len>=2, no pure-digit tokens. The evidence unit of the display-cross
    gate (matches the forensic census tokenizer)."""
    out: set[str] = set()
    for seg in _GATE_SPLIT.split(text or ""):
        for word in _GATE_CAMEL.sub(" ", seg).split():
            if len(word) >= 2 and not word.isdigit():
                out.add(_gate_stem(word))
    return out


def _member_dominant_tokens(
    paths: Iterable[str], ratio: float = 0.5,
) -> set[str]:
    """Path tokens present in >= ``ratio`` of the PF's member file paths —
    the member-majoritarian evidence that legitimizes an authored label
    even when it is absent from the slug (cal ``flags`` PF, label
    'features', member files under ``.../flags/`` and the feature-flag
    lib)."""
    files = [str(p) for p in (paths or [])]
    n = len(files)
    if n == 0:
        return set()
    counts: dict[str, int] = {}
    for f in files:
        for tok in _gate_tokens(f):
            counts[tok] = counts.get(tok, 0) + 1
    need = ratio * n
    return {tok for tok, k in counts.items() if k >= need}


def _nav_anchor_page_labels(
    product_features: Iterable[Any],
    product_strings: Any,
    routes_index: Iterable[Mapping[str, Any]] | None,
) -> dict[str, set[str]]:
    """``{pf_slug: {labels whose href lands on the PF's OWN anchor page}}``.

    The tie-break signal: for a ``route:<dir>`` anchored PF, the anchor
    INDEX page is ``<dir>/page.<ext>``; a nav pair whose normalized href
    resolves to that exact file is the PF's canonical self-link (cal
    ``insights``: 'Insights' -> ``.../insights/page.tsx``), which must beat
    a child-tab collision ('Bookings') that merely first-come-owns a
    sub-route file. Empty on keyless-suppressed / route-less scans."""
    pairs_by_file: Mapping[str, list[tuple[str, str | None]]] = (
        getattr(product_strings, "nav_pairs_by_file", None) or {}
    )
    if not pairs_by_file or not routes_index:
        return {}
    try:
        from wystan.pipeline_v2.product_strings import normalize_href
    except ImportError:  # pragma: no cover — same package
        return {}

    file_by_pattern: dict[str, str] = {}
    for r in routes_index:
        pat = str(r.get("pattern") or "").strip()
        f = str(r.get("file") or "").strip()
        if pat and f and pat not in file_by_pattern:
            file_by_pattern[pat] = f

    # anchor index page file -> owning PF slug (first-come, list order)
    slug_by_anchor_page: dict[str, str] = {}
    for pf in product_features:
        slug = str(getattr(pf, "name", "") or "")
        src, path = _anchor_path(str(getattr(pf, "anchor_id", None) or ""))
        if src != "route" or not path:
            continue
        prefix = path.rstrip("/") + "/page."
        for f in file_by_pattern.values():
            if f.startswith(prefix) and "/" not in f[len(prefix):]:
                slug_by_anchor_page.setdefault(f, slug)
    if not slug_by_anchor_page:
        return {}

    out: dict[str, set[str]] = {}
    for pairs in pairs_by_file.values():
        for label, href in pairs:
            if not label or not href:
                continue
            lab = " ".join(str(label).split())
            norm = normalize_href(str(href)) or ""
            if not norm:
                continue
            route_file = file_by_pattern.get(norm)
            owner = slug_by_anchor_page.get(route_file) if route_file else None
            if owner:
                out.setdefault(owner, set()).add(lab)
    return out


def _hub_composite_recompose(
    anchor_id: str, cur: str, pick: str, vocab: Mapping[str, Any],
) -> str | None:
    """Display-cross it3/it4 composite-KEEP for one labeler PF pick.

    ``None`` — the pick is NOT the information-loss class (apply it
    verbatim). Otherwise the canonical ``<Family> — <Vendor>``
    recomposition: equal to ``cur`` for a pure keep, different when it
    also REPAIRS a degrimed composition (novu it4 calibration: at Pass-3
    sendgrid's live display was 'Email — sendgr' — an upstream degrime
    truncation — so a cur-string compare missed the flatten; the anchor's
    OWN vendor segment is the mangle-proof ground).

    The flatten test is a JOIN-FOLD compare (concatenated alnum words,
    lowered) — camelCase ('msTeams'), separators and brand casing
    ('SendGrid') all fold away — against the hub anchor's vendor segment,
    the current leaf, and the whole current composition. A pick with any
    OTHER word content is a real correction and applies untouched."""
    src, path = _anchor_path(anchor_id or "")
    if src != "hub" or " — " not in (cur or ""):
        return None

    def _j(text: str) -> str:
        return "".join(w for w in _GATE_SPLIT.split((text or "").lower()) if w)

    _head, _sep, leaf = cur.rpartition(" — ")
    vendor_seg = (path or "").rstrip("/").rsplit("/", 1)[-1]
    if _j(pick) not in {_j(vendor_seg), _j(leaf), _j(cur)}:
        return None
    comp = hub_composition_display(anchor_id, pick, vocab)
    if not comp:
        return cur  # malformed hub id — plain keep
    # Family-echo strip: composing vendor 'Chat Webhook' under family
    # 'Chat' yields 'Chat — Chat Webhook' — the echo word drops.
    fam, sep2, vend = comp.partition(" — ")
    vwords = vend.split()
    if len(vwords) > 1 and vwords[0].lower() == fam.strip().lower():
        comp = f"{fam}{sep2}{' '.join(vwords[1:])}"
    return comp


def gated_nav_labels_for_pfs(
    product_features: Iterable[Any],
    product_strings: Any,
    routes_index: Iterable[Mapping[str, Any]] | None,
    vocab: Mapping[str, Any],
) -> dict[str, str]:
    """``{pf_slug: display-ready nav label}`` — the display-cross gate's
    replacement for :func:`nav_labels_for_pfs` on the gated provenance path
    ONLY (``WYSTAN_PF_DISPLAY_EVIDENCE_GATE``). Three additive laws over
    the SAME ungated votes:

    * **tie-break** — equal-vote labels are ordered anchor-page-first
      before ``len``/alpha, so a PF's own self-link beats a child-tab href
      collision (cal ``insights``: 'Insights' over 'Bookings');
    * **gate** — the top label survives only when its tokens intersect the
      PF's name/anchor-terminal identity OR its member-dominant path tokens;
      a foreign label is dropped (omitted from the map) so the ladder falls
      through to the honest basename;
    * **casing** — the surviving raw authored label / i18n key is
      title-cased (``directory_sync`` -> 'Directory Sync'; ``features`` ->
      'Features').

    Omitting a slug (no surviving label) is the revert: the caller reads
    ``get(slug, "")`` and the ladder uses manifest/basename instead.
    """
    pfs = list(product_features)
    votes = _nav_label_votes(pfs, product_strings, routes_index)
    if not votes:
        return {}
    anchor_labels = _nav_anchor_page_labels(pfs, product_strings, routes_index)
    pf_by_slug = {str(getattr(p, "name", "") or ""): p for p in pfs}
    out: dict[str, str] = {}
    for slug, labs in votes.items():
        pf = pf_by_slug.get(slug)
        if pf is None:
            continue
        anchor_hits = anchor_labels.get(slug, set())
        # Anchor-page preference is inserted BEFORE alpha but AFTER the vote
        # plurality — it only ever changes the winner at a vote TIE, so a
        # label the authors clearly favored is never overridden.
        best = sorted(
            labs.items(),
            key=lambda kv: (-kv[1], 0 if kv[0] in anchor_hits else 1,
                            len(kv[0]), kv[0]),
        )[0][0]
        aid = str(getattr(pf, "anchor_id", None) or "")
        identity = _gate_tokens(str(getattr(pf, "name", "") or "")) | _gate_tokens(
            _anchor_terminal_segment(aid) or "")
        toks = _gate_tokens(best)
        if toks & identity or toks & _member_dominant_tokens(
            getattr(pf, "paths", None) or []
        ):
            out[slug] = _display_word(best, vocab)
    return out


# ── B57 Seg1 rung-source extractors (flag-gated; Law C consumers) ───────
#
# Pure text→evidence extractors for the WYSTAN_UF_RUNG_SOURCES_V2
# rungs. Deterministic, $0, NO README, no LLM. File reads are bounded
# (size cap mirrors product_strings._MAX_FILE_BYTES; per-UF file-count
# cap) — the caps only bound work, they are not tuned to any repo.

#: i18n-KEY reference patterns in member SOURCE files: ``t('key')`` /
#: ``t("key")`` (Vue ``$t('key')`` included — the hoppscotch-class
#: canonical reference form), ``i18nKey="key"`` (JSX ``{'key'}`` form
#: included), and ``getTranslation('key')``. The KEY (group 1) is the
#: evidence — the identifier the author wrote in CODE. The lookbehind on
#: ``$?t(`` keeps word-tails out (``format(`` / ``at(`` / ``foo$t(``
#: never match; ``i18n.t(`` / ``this.$t(`` / ``{{ $t( }}`` do).
_I18N_KEY_REFS = (
    re.compile(r"(?<![\w$])\$?t\(\s*['\"]([^'\"\n]+)['\"]"),
    re.compile(r"i18nKey\s*=\s*\{?\s*['\"]([^'\"\n]+)['\"]"),
    re.compile(r"getTranslation\(\s*['\"]([^'\"\n]+)['\"]"),
)

#: Structural i18n-KEY discriminator: identifier-shaped — word chars plus
#: the namespace glyphs ``. : $ -`` and NO whitespace. Anything
#: space-broken is human copy (a translated VALUE — the FORBIDDEN
#: source), never a key.
_I18N_IDENT_RE = re.compile(r"[\w.:$\-]+\Z")

#: camelCase boundary for key tokenization (``profileTitle`` → profile
#: title); composes with the ``[._:$-]`` namespace split.
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

#: Test-assertion label patterns: ``it('…')`` / ``test('…')`` /
#: ``describe('…')`` (modifier chains ``it.only(`` / ``describe.skip(``
#: included; ' " ` quotes) + python ``def test_*`` names.
_TEST_LABEL_RE = re.compile(
    r"\b(?:it|test|describe)(?:\.\w+)*\(\s*['\"`]([^'\"`\n]+)['\"`]")
_PY_TEST_DEF_RE = re.compile(r"^\s*def\s+test_(\w+)", re.MULTILINE)

#: HTTP method → verb family (B57 Seg1 (c)). STRUCTURAL semantics of the
#: HTTP verb itself (RFC 9110 method → CRUD family), not a repo
#: vocabulary — module-level frozen. Filesystem "PAGE" pseudo-methods
#: deliberately absent from the METHOD map — a page route declares no
#: author action verb; its READ nature feeds the b57-iter2 composition
#: rung via :data:`_PAGE_VERB_FAMILIES` instead.
_HTTP_METHOD_VERB_FAMILIES: Mapping[str, frozenset[str]] = {
    "GET": frozenset({"browse", "view"}),
    "POST": frozenset({"create"}),
    "PUT": frozenset({"update"}),
    "PATCH": frozenset({"update"}),
    "DELETE": frozenset({"delete"}),
}

#: b57-iter2 — a PAGE surface (filesystem-routed page / page-kind flow
#: entry) is a READ surface: navigating to it views/browses, it mutates
#: nothing. Structural navigation semantics, not a repo vocabulary.
_PAGE_VERB_FAMILIES = frozenset({"browse", "view"})

#: Flow-entry kinds that mark a page/navigation-class flow. ``Flow`` has
#: no dedicated kind field — Stage 3 stamps ``description = entry.route
#: or entry.kind``, so a NON-routed page entry carries its kind here
#: (routed pages are covered by the routes_index ``PAGE`` rows instead).
_PAGE_FLOW_KINDS = frozenset({"page"})


def route_verb_indexes(
    routes_index: Iterable[Mapping[str, Any]] | None,
) -> tuple[dict[str, set[str]], set[str]]:
    """``(method_families_by_file, page_files)`` — the per-file verb-fact
    indexes of ``routes_index``: declared HTTP methods fold to verb
    families via :data:`_HTTP_METHOD_VERB_FAMILIES`; filesystem ``PAGE``
    rows collect into a page-surface file set. Shared by Law C's B57
    Seg1 rungs and the Stage 6.7e adjudicator (one builder, no dup)."""
    method_fams: dict[str, set[str]] = {}
    page_files: set[str] = set()
    for r in (routes_index or ()):
        rf = str(r.get("file") or "")
        if not rf:
            continue
        meth = str(r.get("method") or "").strip().upper()
        fams = _HTTP_METHOD_VERB_FAMILIES.get(meth)
        if fams:
            method_fams.setdefault(rf, set()).update(fams)
        elif meth == "PAGE":
            page_files.add(rf)
    return method_fams, page_files


def member_verb_composition(
    uf: Any,
    flow_by_id: Mapping[str, Any],
    method_fams_by_file: Mapping[str, set[str]],
    page_files: set[str] | frozenset[str],
) -> set[str]:
    """b57-iter2 — the verb families a journey's MEMBER COMPOSITION
    implies (scan facts, $0): (a) member routes' declared HTTP methods
    (via :func:`route_verb_indexes`), (b) page-surface members — a PAGE
    route file or a page-kind flow entry — imply the read families. An
    EMPTY result means the composition asserts NOTHING about verbs (no
    facts — no claim; the honest ``missing:verb`` stays)."""
    fams: set[str] = set()
    for m in (getattr(uf, "member_flow_ids", None) or []):
        fl = flow_by_id.get(str(m))
        if fl is None:
            continue
        paths = {str(p) for p in (getattr(fl, "paths", None) or []) if p}
        ep = getattr(fl, "entry_point_file", None)
        if ep:
            paths.add(str(ep))
        for p in sorted(paths):
            fams |= method_fams_by_file.get(p, set())
            if p in page_files:
                fams |= _PAGE_VERB_FAMILIES
        if str(getattr(fl, "description", "") or "") in _PAGE_FLOW_KINDS:
            fams |= _PAGE_VERB_FAMILIES
    return fams


# ── B108 R1/R2 — verb-snap guards for a DSL-supplied route channel ──────
# The Rails route-supply (``WYSTAN_RAILS_ROUTES_SUPPLY``) lands the
# first route rows a Rails board has ever had, which ARMS the default-ON
# verb-snap on a channel it was never calibrated against. P8 measured the
# harm on real captures — two chatwoot journeys would be renamed into
# high-confidence LIES ('Configure and process webhooks' -> 'Create ...',
# 'Create and manage inboxes' -> 'Browse ...'). Both guards are armed by
# EVIDENCE (supplied handler rows present), not by the env flag, so a
# board the channel never supplied is byte-identical either way.


def _uf_member_files(uf: Any, flow_by_id: Mapping[str, Any]) -> set[str]:
    """The member flows' source files (same walk as
    :func:`member_verb_composition`, without the family fold)."""
    out: set[str] = set()
    for m in (getattr(uf, "member_flow_ids", None) or []):
        fl = flow_by_id.get(str(m))
        if fl is None:
            continue
        out |= {str(p) for p in (getattr(fl, "paths", None) or []) if p}
        ep = getattr(fl, "entry_point_file", None)
        if ep:
            out.add(str(ep))
    return out


def supplied_handler_files(
    routes_index: Iterable[Mapping[str, Any]] | None,
) -> set[str]:
    """Route rows whose ``file`` is a DSL route-HANDLER file by stack
    convention (today: Rails ``*_controller.rb`` under ``app/controllers/``,
    engines included). Non-empty ⇔ the handler-supply channel reached this
    board ⇔ the R1/R2 snap guards arm."""
    from wystan.pipeline_v2.extractors.rails_routes import (
        is_rails_handler_path,
    )

    out: set[str] = set()
    for r in (routes_index or ()):
        rf = str(r.get("file") or "")
        if rf and is_rails_handler_path(rf):
            out.add(rf)
    return out


def _verb_polarity(fam: str | None) -> str | None:
    """``"write"`` / ``"read"`` / ``None`` (a family outside both, e.g.
    ``act``, makes no polarity claim)."""
    if fam in _WRITE_FAMILIES:
        return "write"
    if fam in _READ_FAMILIES:
        return "read"
    return None


def snap_crosses_polarity(lead: str | None, target: str | None) -> bool:
    """R1 — a snap may REFINE a claim inside its polarity (create ↔ update
    ↔ delete, browse ↔ view) but never FLIP it.

    Both directions are barred, for one reason each:

    * write lead → read target: the composition under-represents
      mutations whenever a handler failed to resolve or the action lives
      off the route table, so a read verb would make a true name lie
      (the engine already says as much at the b61-iter3 never-worse
      guard — which cannot fire here because it reads member FLOW-NAME
      families, and those are EMPTY for the exhibit it needs to save).
    * read/config lead → write target: an inbound receiver surface is
      POST-dominant while the user configures rather than creates
      ('Configure and process webhooks'); HTTP-method dominance is not
      authority to overwrite an authored read/config claim.

    Unknown polarity on either side (``act``) never blocks — no claim,
    no contradiction."""
    lp, tp = _verb_polarity(lead), _verb_polarity(target)
    return bool(lp and tp and lp != tp)


def snap_composition_complete(
    uf: Any,
    flow_by_id: Mapping[str, Any],
    method_fams_by_file: Mapping[str, set[str]],
) -> bool:
    """R2 — a PARTIAL composition does not claim truth.

    Every member file the route channel SHOULD cover (a handler file by
    stack convention) must actually carry route rows. A member the
    channel could never cover — a model, a job, a service object
    (anti-case A4) — is not routable and never blocks; a UF with no
    routable members at all is vacuously complete (its composition came
    from the page channel, not from handler supply).

    This is the guard that saves 'Configure and process webhooks': 7 of
    its 9 controller members resolve, the 2 that don't sit under a Rails
    ENGINE root the resolver honestly refuses to guess (A3), and a 7/9
    view of the verbs is not evidence enough to rename the journey."""
    from wystan.pipeline_v2.extractors.rails_routes import (
        is_rails_handler_path,
    )

    return all(
        p in method_fams_by_file
        for p in _uf_member_files(uf, flow_by_id)
        if is_rails_handler_path(p)
    )


#: Work bounds for the file-reading rungs (i18n-key / test-assert). Size
#: cap mirrors ``product_strings._MAX_FILE_BYTES``; the per-UF file cap
#: bounds pathological member fan-outs. Bounds-of-work only.
_RUNG_SOURCE_MAX_FILE_BYTES = 256 * 1024
_RUNG_SOURCE_MAX_FILES = 32


def _i18n_keys_from_text(text: str) -> list[str]:
    """Identifier-shaped i18n KEYS referenced in one source file, in
    document order. VALUES (anything with whitespace) are structurally
    rejected — the operator rule 2026-07-13: translations may live
    outside the repo; only the key names are code-ground truth."""
    out: list[str] = []
    for rx in _I18N_KEY_REFS:
        for m in rx.finditer(text):
            key = m.group(1).strip()
            if key and _I18N_IDENT_RE.fullmatch(key):
                out.append(key)
    return out


def _test_assertion_labels(text: str) -> list[str]:
    """Assertion labels authored inside one MAPPED test file, in document
    order: JS/TS ``it/test/describe('…')`` strings + python ``def
    test_*`` names (underscores → spaces so both tokenize alike)."""
    labels = [m.group(1) for m in _TEST_LABEL_RE.finditer(text)]
    labels.extend(
        m.group(1).replace("_", " ") for m in _PY_TEST_DEF_RE.finditer(text))
    return labels


# ── Candidate builders ──────────────────────────────────────────────────


def build_pf_candidates(
    pf: Any,
    vocab: Mapping[str, Any],
    *,
    nav_label: str | None = None,
    repo_root: Any = None,
) -> list[str]:
    """Ranked display candidates for one product feature (dedup, order-
    preserving). The CURRENT display (casing-polished) is always present
    — the contract can never invent from nothing (never-worse).

    ``repo_root`` (B27) arms the package-manifest channel: a package-dir-
    anchored PF (``hub:``-vendor / ``ws:``) leads with the display name
    the package DECLARES in its own metadata (config.json name /
    metadata-module name / package.json displayName / authored name),
    composing with the existing hub decoration ("App Store — Stripe"); a
    mechanical letter/digit word-split of the dir slug is the rung below
    ("Exchange 2013 Calendar"). ``None`` (the default) or
    ``WYSTAN_PF_MANIFEST_NAME=0`` is byte-identical to pre-B27."""
    slug = str(getattr(pf, "name", "") or "")
    current = str(
        getattr(pf, "display_name", None)
        or (_display_word(slug, vocab) if slug else "")
    )
    anchor_id = str(getattr(pf, "anchor_id", None) or "")
    out: list[str] = []

    def _add(c: str | None) -> None:
        if c and c.strip() and c not in out:
            out.append(c.strip())

    if nav_label:
        _add(polish_display_casing(nav_label, vocab))
    # B50 Seg2 — a PF display that would BE a pure route param ('/p/$url' ->
    # 'URL') names no domain object: resolve a domain noun from the anchor
    # (minus the param) / nav-cluster / member-file dominant domain noun and
    # lead with it. Never the route letter 'p'. Flag OFF ⇒ byte-identical.
    if uf_name_degrime_enabled() and _is_pure_param_display(
            polish_display_casing(current, vocab)):
        _add(_resolve_param_display(
            anchor_id, nav_label, getattr(pf, "paths", None) or [], vocab))
    pkg_display, _pkg_src = _package_manifest_display(
        anchor_id, vocab, repo_root, current)
    if pkg_display:
        _add(hub_composition_display(
            anchor_id, current, vocab, vendor_display=pkg_display))
    _add(hub_composition_display(anchor_id, current, vocab))
    src, _p = _anchor_path(anchor_id)
    if pkg_display and src != "hub":
        _add(pkg_display)  # bare manifest name for a ws package anchor
    polished_current = polish_display_casing(current, vocab)
    # The collision-qualified verbose class ("Discord (Route Apps Web
    # Src App Landing Redirect Discord)") or a law-dirty current display
    # yields to the humanized anchor words; a law-clean, non-verbose
    # display outranks them (no churn of good names). Never for hub
    # anchors: vendor children carry the composition above, and a hub
    # CORE's designed "<Family> Core" must not degrade to the bare
    # family word.
    qual_match = re.search(r"\(([^)]{2,})\)\s*$", polished_current)
    verbose_qualified = bool(
        qual_match and len(qual_match.group(1).split()) >= 3
    )
    current_dirty = bool(display_law_violations(polished_current, vocab))
    # B2: a route display carrying template residue ('Admin+', 'API+',
    # 'Internal+', 'P.$URL') is dirty even when the param LAW misses the
    # '+'/'_'-prefix class — yield to the humanized anchor word.
    if (humanize_route_names_enabled() and src == "route"
            and _has_route_template_residue(polished_current)):
        current_dirty = True
    base, qual = (None, None) if src == "hub" else humanize_anchor_display(
        anchor_id, vocab)
    if pkg_display and base:
        # B27 — the manifest word replaces the dir-slug base so the
        # existing "(Qualifier)" decoration keeps composing
        # ("Stripe (App Store)" instead of "Stripepayment (App Store)").
        base = pkg_display
    if current_dirty or verbose_qualified:
        if base:
            _add(base)
            if qual:
                _add(f"{base} ({qual})")
        _add(polished_current)
    else:
        _add(polished_current)
        if base:
            _add(base)
            if qual:
                _add(f"{base} ({qual})")
    return out


def _flow_verb_verdict(
    member_flow_names: Iterable[str], vocab: Mapping[str, Any],
) -> str:
    """Journey intent verdict from member-flow verb evidence — first
    matching class in the vocab's documented order wins; ``manage`` is
    the fallback."""
    classes: Mapping[str, Any] = vocab.get("flow_verb_classes") or {}
    tokens: list[str] = []
    for nm in member_flow_names:
        tokens.extend(re.split(r"[^a-z0-9]+", str(nm or "").lower()))
    tokset = {t for t in tokens if t}
    for verdict in ("connect", "ingest", "send", "receive", "run", "view"):
        verbs = {str(x).lower() for x in (classes.get(verdict) or [])}
        if tokset & verbs:
            return verdict
    return "manage"


def _resource_phrase(pf_display: str, vocab: Mapping[str, Any]) -> str:
    """Lower-cased resource phrase of a PF display for journey templates
    ("Status Reports" → "status reports"); acronyms/brands keep their
    canonical casing ("ERP Core" → "ERP core")."""
    v = vocab
    acronyms = {str(a).lower() for a in (v.get("known_acronyms") or [])}
    brands = {str(k).lower(): str(val)
              for k, val in (v.get("brand_casing") or {}).items()}
    words = []
    for w in (pf_display or "").split(" "):
        low = w.lower()
        if low in brands:
            words.append(brands[low])
        elif low in acronyms:
            words.append(w.upper())
        else:
            words.append(w.lower())
    words = [x for x in words if x]
    # B50 — the canonical resource renderer is the JOINER for every UF-name
    # template + Law-A/C resource phrase; de-grime its token stream so an
    # echoed ('case case ids') or param-glued resource never composes into a
    # display. Flag OFF ⇒ byte-identical.
    if uf_name_degrime_enabled():
        words = _degrime_resource_words(words, v)
    return " ".join(x for x in words if x)


def build_uf_candidates(
    uf: Any,
    pf: Any | None,
    vocab: Mapping[str, Any],
    member_flow_names: Iterable[str] = (),
    authored: Iterable[str] = (),
    own_resource: bool = False,
    member_evidence: Sequence[tuple[str, str]] | None = None,
) -> list[str]:
    """Ranked display candidates for one user flow. Journey templates
    (verb-led, actor+intent+outcome shape) lead when the current name is
    a twin of its PF or the UF is backstop-synthesized; a law-clean
    existing name leads otherwise (no churn of good journey names).

    ``authored`` (Track C) — MAINTAINER-authored journey labels from e2e
    specs. When supplied they lead ALL other candidates: the maintainer
    literally named this journey, which outranks any derived template. Each
    is still polished + law-gated by the caller like any candidate, so an
    unlawful authored string simply falls through to the derived set.
    Empty (the default) ⇒ byte-identical to the pre-Track-C ranking.

    ``own_resource`` (R5-2 echo-hub, ``WYSTAN_NAMING_WAVE_R5``) — the
    generic template joins on the UF's OWN resource instead of the PF
    display. The D9 system-seed hand (below) already does this for
    flow-less SYSTEM seeds; R5-2 extends it to ORGANIC siblings when ≥2
    UFs of one PF would otherwise mint the identical "<verb> <PF-display>"
    row (twenty ``twenty-server`` -> 'Manage twenty server' ×24). The
    caller sets it only for those hub members; False (the default) ⇒
    byte-identical to the pre-R5-2 template.

    ``member_evidence`` (B78 Seg H, ``WYSTAN_DOMINANT_EVIDENCE_NAMING``)
    — ``(flow-name, entry-file)`` pairs of the UF's members for the
    dominant-evidence ratio gate on the generic template's ``{r}`` join.
    ``None`` (the default) or flag OFF ⇒ byte-identical."""
    current = str(getattr(uf, "name", "") or "")
    pf_display = (
        str(getattr(pf, "display_name", None) or getattr(pf, "name", "") or "")
        if pf is not None else ""
    )
    anchor_id = str(getattr(pf, "anchor_id", None) or "") if pf is not None else ""
    synthesized = bool(getattr(uf, "synthesized", False))
    twin = bool(current) and pf_display and (
        current.strip().lower() == pf_display.strip().lower()
    )

    templates: Mapping[str, Any] = vocab.get("journey_templates") or {}
    verdict = _flow_verb_verdict(member_flow_names, vocab)
    src, _path = _anchor_path(anchor_id)
    is_vendor_pf = src == "hub" and " Core" not in pf_display
    # W3.2 D9 — a synthesized SYSTEM journey (flow-less job/route seed)
    # is named by its OWN job resource, never the PF display: the seed
    # exists to surface the JOB's identity; the PF is only its terminal
    # home. The PF-display template collapsed every job under one hub
    # into identical rows (RefApp: 11 inngest seeds → "Manage
    # integrations" ×11 after terminal-home binding — a verifier cannot
    # review that). Background executions template on the "run" verb.
    is_system_seed = (
        synthesized
        and str(getattr(uf, "category", "") or "") == "system"
        and bool(getattr(uf, "resource", None))
    )
    if is_system_seed:
        tmpl = (templates.get("generic") or {}).get("run") or "Run {r}"
        own = re.sub(r"[-_]+", " ", str(uf.resource)).strip()
        template_name = tmpl.replace("{r}", _resource_phrase(own, vocab))
    elif is_vendor_pf:
        tmpl = (templates.get("vendor") or {}).get(verdict) or "Manage {v}"
        vendor_disp = polish_display_casing(pf_display, vocab)
        # A composed "<Family> — <Vendor>" display templates on the
        # VENDOR half (the journey subject), never the family prefix.
        if " — " in vendor_disp:
            vendor_disp = vendor_disp.split(" — ", 1)[1]
        template_name = tmpl.replace("{v}", vendor_disp)
    else:
        tmpl = (templates.get("generic") or {}).get(verdict) or "Manage {r}"
        # R5-2 — an echo-hub organic sibling joins on its OWN resource so the
        # row surfaces the job's identity, not the shared PF home (kills the
        # 'Manage twenty server' ×24 echo + its qualifier-spray). Falls back
        # to the PF-display join when the UF has no distinct resource.
        _r_src = pf_display or current
        if own_resource and getattr(uf, "resource", None):
            _own = re.sub(r"[-_]+", " ", str(uf.resource)).strip()
            if _own:
                _r_src = _own
        _join_phrase = _resource_phrase(_r_src, vocab)
        # B78 Seg H (WYSTAN_DOMINANT_EVIDENCE_NAMING) — a multi-resource
        # {r} join (a PF display like 'Knowledges, Orgs & Files') gifts
        # EVERY one of its resources to a journey about one of them. Ratio
        # gate over member evidence: drop under-supported content tokens
        # (own-resource tokens are exempt — identity, not a gift); an
        # emptied phrase keeps the original (reject ⇒ unchanged channel).
        # ``member_evidence is None`` / flag OFF ⇒ byte-identical.
        if member_evidence is not None and _join_phrase:
            from wystan.pipeline_v2.dominant_evidence import (
                dominant_evidence_naming_enabled,
                strip_display_tokens,
                unsupported_display_tokens,
            )
            if dominant_evidence_naming_enabled():
                _drop = unsupported_display_tokens(
                    _join_phrase, member_evidence,
                    resource=str(getattr(uf, "resource", "") or ""),
                    vocab=vocab,
                )
                if _drop:
                    _stripped = strip_display_tokens(
                        _join_phrase, _drop, vocab)
                    if _stripped:
                        _join_phrase = _stripped
        template_name = tmpl.replace("{r}", _join_phrase)

    # B50 Seg1 — a template whose verb duplicates the leading resource token
    # ('Ingest ingest', 'View views', 'Send send test email') collapses at
    # the joiner. Flag OFF ⇒ byte-identical.
    if uf_name_degrime_enabled():
        template_name = _degrime_display(template_name)

    out: list[str] = []

    def _add(c: str | None) -> None:
        if c and c.strip() and c not in out:
            out.append(c.strip())

    # Track C — maintainer-authored labels lead (highest authority below LAW).
    for a in authored:
        _add(polish_display_casing(str(a), vocab))

    polished_current = polish_display_casing(current, vocab)
    current_clean = not display_law_violations(
        polished_current, vocab, pf_display=pf_display)
    # B50 Seg1 — an adjacent-echo current name ('Manage API case case ids')
    # passes the display laws yet must yield to the now-clean template: mark
    # it UNCLEAN so the template leads and the echo is re-derived away.
    if uf_name_degrime_enabled() and current_clean and (
        _degrime_display(polished_current) != polished_current
    ):
        current_clean = False
    if (synthesized or twin) or not current_clean:
        _add(template_name)
        _add(polished_current)
    else:
        _add(polished_current)
        _add(template_name)
    return out


def _uf_member_count(uf: Any) -> int:
    """Member count of a UF row (``member_count`` else the id list)."""
    mc = getattr(uf, "member_count", None)
    if mc is None:
        mc = len(getattr(uf, "member_flow_ids", None) or [])
    try:
        return int(mc or 0)
    except (TypeError, ValueError):  # pragma: no cover — defensive
        return 0


def _echo_own_resource_uf_ids(
    user_flows: Iterable[Any],
    pf_by_slug: Mapping[str, Any],
) -> set[str]:
    """R5-2 — the UF ids that must template on their OWN resource because
    their PF is a multi-resource hub whose PF-display template would
    collapse them into one echoed row.

    A UF qualifies when: it is ORGANIC (``category != 'system'`` — the D9
    hand already owns system seeds), THIN (``member_count`` ≤ 2 — a
    many-member aggregate like twenty 'Connect twenty server' ×8 carries
    real breadth and keeps its PF-display name; keyed-refutation iter-2
    anti-case), carries a ``resource`` DISTINCT from its PF's identity,
    and shares that PF with ≥2 such UFs spanning ≥2 distinct resources
    (twenty ``twenty-server`` hosts 22+). Scale-invariant (a ratio-free
    ≥2/≥2 shape rule, no per-repo numbers); a single-resource PF or a PF
    whose UFs echo its own identity is never touched."""
    from collections import defaultdict

    by_pf: dict[str, list[Any]] = defaultdict(list)
    for uf in user_flows:
        if str(getattr(uf, "category", "") or "") == "system":
            continue
        if not str(getattr(uf, "resource", "") or "").strip():
            continue
        if _uf_member_count(uf) > 2:
            continue
        by_pf[str(getattr(uf, "product_feature_id", "") or "")].append(uf)
    out: set[str] = set()
    for pfid, ufs in by_pf.items():
        pf = pf_by_slug.get(pfid)
        pf_ident = _ident_fold(
            str(getattr(pf, "display_name", None) or getattr(pf, "name", "") or "")
        ) if pf is not None else ""
        distinct = [
            u for u in ufs
            if _ident_fold(str(getattr(u, "resource", "") or ""))
            not in ("", pf_ident)
        ]
        res_idents = {
            _ident_fold(str(getattr(u, "resource", "") or "")) for u in distinct
        }
        res_idents.discard("")
        if len(distinct) >= 2 and len(res_idents) >= 2:
            for u in distinct:
                out.add(str(getattr(u, "id", "") or ""))
    return out


def _spray_sibling_uf_ids(
    user_flows: Iterable[Any],
    pf_by_slug: Mapping[str, Any],
) -> set[str]:
    """R5-2 iter-2 — qualifier-SPRAY ids: same-PF siblings whose
    paren-stripped folded BASE is identical across ≥2 THIN rows
    (``member_count`` ≤ 2, non-empty resource) AND wears the PF's own
    identity ('Manage twenty server (billing)/(dpa)/…' ×22 — the base
    names the HOME, not the job; the fresh-keyed live disease form).

    These rows must ADOPT the own-resource template even though the
    sprayed current name is law-clean (the ranking otherwise keeps it).
    A base that names a real resource ('Manage invoices (drafts)' /
    '(sent)') does NOT wear the PF identity and is never flagged —
    the qualifier there is legit disambiguation."""
    from collections import defaultdict

    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for uf in user_flows:
        if str(getattr(uf, "category", "") or "") == "system":
            continue
        if not str(getattr(uf, "resource", "") or "").strip():
            continue
        if _uf_member_count(uf) > 2:
            continue
        nm = str(getattr(uf, "name", "") or "")
        base = re.sub(r"\s*\([^)]*\)+\s*$", "", nm).strip()
        base = re.sub(r"\s*\([^)]*\)+\s*$", "", base).strip()
        if not base:
            continue
        pfid = str(getattr(uf, "product_feature_id", "") or "")
        pf = pf_by_slug.get(pfid)
        pf_ident = _ident_fold(
            str(getattr(pf, "display_name", None)
                or getattr(pf, "name", "") or "")
        ) if pf is not None else ""
        if not pf_ident or pf_ident not in _ident_fold(base):
            continue
        groups[(pfid, base.lower())].append(str(getattr(uf, "id", "") or ""))
    out: set[str] = set()
    for _key, ids in groups.items():
        if len(ids) >= 2:
            out.update(ids)
    return out


def _r5_sibling_name_dup(
    uf: Any, cand: str, user_flows: Iterable[Any],
) -> bool:
    """R5-2 iter-2 no-new-dup guard — True when ANOTHER live UF of the
    SAME PF already wears ``cand`` (case-folded). No R5 rename may mint a
    name identical to a live sibling (the keyed-refutation collateral:
    'Manage twenty server (application development)' -> bare 'Manage
    twenty server' duplicating an existing row); the caller keeps the old
    name instead — a kept diseased name is then demoted by the R5-5
    shape cap, never duplicated."""
    fld = (cand or "").strip().lower()
    if not fld:
        return False
    uid = str(getattr(uf, "id", "") or "")
    pfid = str(getattr(uf, "product_feature_id", "") or "")
    for other in user_flows:
        if str(getattr(other, "id", "") or "") == uid:
            continue
        if str(getattr(other, "product_feature_id", "") or "") != pfid:
            continue
        if str(getattr(other, "name", "") or "").strip().lower() == fld:
            return True
    return False


# ── S2-A-v3 spray-generalization (WYSTAN_SPRAY_GENERALIZED, default
# ON since the 2026-07-21 pack-3 flip) ──────────────────────────────────
#
# The generalized R5-2 spray predicate over the UNPARENTHESIZED form (probe
# canon, 2026-07-19: 15/17 direct + 17/17 with group-absorption on the
# twenty-b exhibit; 0/55 boards false at K=2 AND K=3):
#
#   G0  paren-tail -> R5-2's qualifier-spray class, skip (class boundary —
#       without it the predicate annexes the paren families R5-2 owns).
#   G1  prefix >= 2 tokens (kills healthy bare 'Manage billing/members/
#       security' families structurally — their prefix is the intent alone).
#   Match  singular(tail) == singular(leaf-dir) on >= _SPRAY_LEAF_RATIO of
#       the row's member paths (the row lists a DIRECTORY, not a journey).
#   Fire  >= _SPRAY_MIN_SIBLINGS matching siblings on one (PF, prefix)
#       group -> the WHOLE group collapses (group-absorption: the
#       structural misses — twenty 'graphqls'/'news' — ride along) into one
#       minted own-resource parent row. NO member-count clause: the spray
#       carries 2-23 members; the discriminator is tail==leaf-dir, never
#       member count (probe ruling — the R5-2 thin-row clause REFUTED here).

#: Probe-canon scale-invariant thresholds (ratio + sibling count — shape
#: rules, no per-repo numbers).
_SPRAY_LEAF_RATIO = 0.5
_SPRAY_MIN_SIBLINGS = 3


def _spray_sing(tok: str) -> str:
    """Probe-canon singular fold: alnum-only lowercase, trailing 's'
    stripped past 3 chars ('components' -> 'component', 'AI' -> 'ai')."""
    t = re.sub(r"[^a-z0-9]", "", (tok or "").lower())
    if len(t) > 3 and t.endswith("s"):
        t = t[:-1]
    return t


def _spray_leaf_dir(path: str) -> str:
    """Last directory segment of a member file path ('' when root-level)."""
    parts = str(path or "").replace("\\", "/").split("/")
    if len(parts) < 2:
        return ""
    return parts[-2]


def _spray_plural(tok: str) -> str:
    """Display plural for the parent's root-dir token (the det-aggregation
    ``_plural`` rule: 'setting' -> 'settings', 'policy' -> 'policies')."""
    if not tok or tok.endswith("s"):
        return tok
    if tok.endswith("y") and len(tok) > 2 and tok[-2] not in "aeiou":
        return tok[:-1] + "ies"
    return tok + "s"


def _spray_display_sing(tok: str) -> str:
    """Display-channel singular for a shared-subdir token — casing kept
    ('applications' -> 'application', 'AI' -> 'AI', 'data' -> 'data')."""
    if tok and len(tok) > 3 and tok.lower().endswith("s"):
        return tok[:-1]
    return tok


def _spray_row_eligible(uf: Any) -> bool:
    """Organic member-ful journey rows only — channel rows (markers,
    synthesized recall seeds, system seeds) keep their identity verbatim
    (the det-aggregation Class-1 law)."""
    if str(getattr(uf, "category", "") or "") == "system":
        return False
    if getattr(uf, "synthesized", False) or getattr(uf, "synthesis_reason", None):
        return False
    if getattr(uf, "is_coverage_marker", False):
        return False
    return bool(getattr(uf, "member_flow_ids", None) or [])


def _spray_member_paths(uf: Any, flow_by_id: Mapping[str, Any]) -> list[str]:
    """Every member flow's file paths (the leaf-dir evidence universe)."""
    out: list[str] = []
    for mid in getattr(uf, "member_flow_ids", None) or []:
        fl = flow_by_id.get(str(mid))
        if fl is not None:
            out.extend(str(p) for p in (getattr(fl, "paths", None) or []))
    return out


def _spray_tail_match(uf: Any, flow_by_id: Mapping[str, Any]) -> bool:
    """True when the row's tail token names its members' own leaf directory
    (singular fold) on >= _SPRAY_LEAF_RATIO of the member paths."""
    toks = str(getattr(uf, "name", "") or "").split()
    if len(toks) < 3:
        return False
    tail = _spray_sing(toks[-1])
    if not tail:
        return False
    paths = _spray_member_paths(uf, flow_by_id)
    if not paths:
        return False
    hits = sum(1 for p in paths if _spray_sing(_spray_leaf_dir(p)) == tail)
    return (hits / len(paths)) >= _SPRAY_LEAF_RATIO


def _spray_fired_groups(
    user_flows: Iterable[Any],
    flow_by_id: Mapping[str, Any],
) -> list[tuple[tuple[str, tuple[str, ...]], list[Any]]]:
    """The (PF, prefix) groups the predicate fires on, deterministic order.

    Each returned group carries EVERY eligible sibling of the fired prefix
    (group-absorption), not only the tail-matching ones. Paren-tail rows
    (G0) never enter a group; a 1-token prefix (G1) never forms one."""
    from collections import defaultdict

    groups: dict[tuple[str, tuple[str, ...]], list[Any]] = defaultdict(list)
    for uf in user_flows:
        if not _spray_row_eligible(uf):
            continue
        toks = str(getattr(uf, "name", "") or "").split()
        if len(toks) < 3:            # G1 — prefix must extend past the intent
            continue
        if "(" in toks[-1] or ")" in toks[-1]:
            continue                 # G0 — paren-tail is R5-2's class
        pfid = str(getattr(uf, "product_feature_id", "") or "")
        groups[(pfid, tuple(toks[:-1]))].append(uf)

    fired: list[tuple[tuple[str, tuple[str, ...]], list[Any]]] = []
    for key in sorted(groups, key=lambda k: (k[0], k[1])):
        rows = sorted(groups[key], key=lambda u: str(getattr(u, "id", "") or ""))
        matched = [u for u in rows if _spray_tail_match(u, flow_by_id)]
        if len(matched) >= _SPRAY_MIN_SIBLINGS:
            fired.append((key, rows))
    return fired


def _spray_parent_name(prefix: tuple[str, ...], vocab: Mapping[str, Any]) -> str:
    """The minted parent's own-resource display from the group's shared
    dir-chain tokens (the det-agg prefix IS that chain: intent + root-dir
    singular + subdir tokens at split depth): intent + shared-subdir tokens
    (display-singular) + PLURALIZED root-dir token — 'Manage AI settings' /
    'Manage application settings' / 'Manage data model settings', never the
    bare prefix."""
    intent = prefix[0]
    root = prefix[1]
    subs = [_spray_display_sing(t) for t in prefix[2:]]
    parts = [intent] + [t for t in subs if t] + [_spray_plural(root.lower())]
    return polish_display_casing(" ".join(p for p in parts if p), vocab)


def _spray_parent_resource(prefix: tuple[str, ...]) -> str:
    """The parent's own-resource noun (lowercase singular) for the caller
    that owns the STRUCTURAL apply (``spray_absorption`` — the §4.8
    identity law forbids identity writes inside this module)."""
    return " ".join(
        [_spray_display_sing(t).lower() for t in prefix[2:] if t]
        + [_spray_sing(prefix[1])]
    ).strip()


# ── Pin channel (keeper — content-derived prev-scan join) ───────────────


def _prev_pf_displays(prev_scan: Mapping[str, Any] | None) -> tuple[
    dict[str, str], dict[str, str],
]:
    """(by_anchor_id, by_slug) display maps from an explicit prev scan."""
    by_anchor: dict[str, str] = {}
    by_slug: dict[str, str] = {}
    for row in ((prev_scan or {}).get("product_features") or []):
        if not isinstance(row, dict):
            continue
        disp = str(row.get("display_name") or row.get("name") or "").strip()
        if not disp:
            continue
        aid = str(row.get("anchor_id") or "").strip()
        slug = str(row.get("name") or row.get("id") or "").strip()
        if aid and aid not in by_anchor:
            by_anchor[aid] = disp
        if slug and slug not in by_slug:
            by_slug[slug] = disp
    return by_anchor, by_slug


# ── Stage runner ────────────────────────────────────────────────────────


@dataclass
class _PendingItem:
    """One display decision forwarded to the PM Labeler (keyed scans)."""

    kind: str                 # "pf" | "uf"
    key: str                  # pf slug / uf id (stable within the scan)
    current: str
    candidates: list[str]
    context: dict[str, Any] = field(default_factory=dict)
    obj: Any = None
    pf_display: str | None = None  # UF items: the owning PF display


_action_families_cache: dict[str, Any] | None = None


def _action_family_index(vocab: Mapping[str, Any]) -> dict[str, Any]:
    """Reverse verb→family index + id-markers from the packaged action-family
    vocab (browse/read/create/update/delete/act). Cached; loaded directly to
    avoid a circular import with journey_lattice."""
    global _action_families_cache
    if _action_families_cache is None:
        try:
            av = load_yaml(_ACTION_FAMILIES_VOCAB_FILE)
        except Exception:  # noqa: BLE001 — vocab optional; laws degrade to no-op
            av = {}
        verb2fam: dict[str, str] = {}
        for fam in ("browse", "read", "create", "update", "delete", "act"):
            for v in (av.get(fam) or ()):
                verb2fam[str(v).lower()] = fam
        _action_families_cache = {
            "verb2fam": verb2fam,
            "id_markers": {str(m).lower() for m in (av.get("id_markers") or ("id",))},
        }
    return _action_families_cache


def _name_tokens(text: str) -> list[str]:
    """The ONE tokenizer Law C's lead readers share: ordered, lower-cased,
    alphanumeric-run tokens of a flow name or a UF display name.

    Extracted verbatim from ``_flow_action_family`` / ``_name_lead_family``
    (their two patterns — ``[^a-z0-9]+`` and ``[^A-Za-z0-9]+`` — are
    equivalent once the string is lower-cased first, which both did). Every
    consumer of a LEAD token goes through here: two tokenizers over the same
    grain is a drift bug class, so the W1/C-A echo rung reuses this instead
    of inventing its own."""
    return [t for t in re.split(r"[^a-z0-9]+", str(text or "").lower()) if t]


def _lead_token(text: str) -> str:
    """The LEADING token of a flow name / UF display ('' when nameless).

    Per the flow-naming contract (``flow_name_v2``: "a flow name must be a
    verb-led capability label (``manage-X-flow``), never a dir echo") this
    token IS the flow's declared action — the mechanism the coarse
    action-family vocabulary merely buckets."""
    toks = _name_tokens(text)
    return toks[0] if toks else ""


def _flow_action_family(name: str, idx: Mapping[str, Any]) -> str | None:
    """Coarse CRUD family of a flow name's LEADING verb (mirrors the lattice's
    ``_action_family``: GET-class reads split by an id marker). Returns
    ``None`` for any lead outside the 99-word vocabulary — which is why the
    W1/C-A rung reads the raw lead token instead of this family."""
    toks = _name_tokens(name)
    if not toks:
        return None
    fam = idx["verb2fam"].get(toks[0])
    if fam == "read":
        return "view" if (idx["id_markers"] & set(toks)) else "browse"
    return fam


def _name_lead_family(display: str, idx: Mapping[str, Any]) -> str | None:
    """The CRUD family a UF DISPLAY name's leading word claims ('Create and
    manage webhooks' → 'create'). Reads never over-claim, so map read→its
    write-less family only when unambiguous."""
    toks = _name_tokens(display)
    if not toks:
        return None
    fam = idx["verb2fam"].get(toks[0])
    if fam == "read":
        return "view" if "id" in toks else "browse"
    return fam


#: fixb142 Part 1 — the separators a display's HEAD conjunct-list may use.
#: Position-bound BY DESIGN: two verbs are only a conjunct-list when a
#: conjunction JOINS them. 'Share view or base publicly' (teable UF-065)
#: puts a resource NOUN in the second slot with no separator after the
#: lead, so it never parses as a list — the named anti-case.
_HEAD_CONJUNCTIONS = frozenset({"and", "or", "&", ","})


def _split_head_conjuncts(
    display: str, idx: Mapping[str, Any],
) -> tuple[list[str], str] | None:
    """``(head_verbs, tail)`` for a display shaped ``V1[, V2]… <conj> Vn
    <resource phrase>`` — else ``None``.

    The parse is STRICTLY positional and left-anchored, and both properties
    are load-bearing:

    * every head token must be a verb the ENGINE'S OWN action-family vocab
      knows (``journey-action-families.yaml`` — no new dictionary), and
    * consecutive head verbs must be JOINED by a conjunction.

    The second rule is what makes this a mechanism rather than a token
    scan. 'Share view or base publicly' leads with a verb and its second
    token is also in the verb table ('view'), but nothing joins them —
    'view' is teable's own resource NOUN. The parse stops at the lead, the
    list is length 1, and the caller refuses. Symmetrically, a verb inside
    the TAIL is never a candidate: 'Review and approve secret change
    requests' folds 'change' to the update family, but 'change' sits in the
    resource phrase and this parser never reaches it.

    Returns ``None`` (not an empty list) whenever fewer than two head verbs
    parse, so the caller has a single refusal path.
    """
    raw = str(display or "")
    # Tokenize keeping SOURCE casing (the repaired name is rebuilt from
    # these) and keeping ',' as its own token so it can act as a separator.
    toks = [t for t in re.split(r"(,)|\s+", raw) if t]
    verbs: list[str] = []
    i = 0
    expect_verb = True
    while i < len(toks):
        t = toks[i]
        low = re.sub(r"[^a-z0-9]+", "", t.lower())
        if expect_verb:
            if not low or low not in idx["verb2fam"]:
                break
            verbs.append(t)
            expect_verb = False
            i += 1
            continue
        # separator position: ',' / 'and' / 'or' / '&' (',' may be followed
        # by 'and' — the Oxford comma — which is consumed as one separator)
        sep = t.lower().strip()
        if sep not in _HEAD_CONJUNCTIONS:
            break
        i += 1
        if sep == "," and i < len(toks) and toks[i].lower().strip() in (
                "and", "or"):
            i += 1
        expect_verb = True
    if len(verbs) < 2:
        return None
    # A trailing separator with no verb after it (the loop ended mid-list)
    # is not a conjunct-list either — the tail must start at a NON-separator.
    tail_toks = toks[i:]
    if tail_toks and tail_toks[0].lower().strip() in _HEAD_CONJUNCTIONS:
        return None
    if not tail_toks:
        return None  # verbs only, no resource phrase — nothing to keep
    tail = " ".join(tail_toks).replace(" ,", ",").strip()
    return verbs, tail


def composite_head_repair(
    display: str, member_names: Iterable[str], idx: Mapping[str, Any],
) -> str | None:
    """fixb142 Part 1 — drop the UNWITNESSED conjuncts from a composite head.

    'Create and edit analytics' over members ``configure-analytics-flow``
    claims a create the evidence never witnesses, while the 'edit' half IS
    witnessed (``configure`` folds to the update family). The repaired name
    states only what the code channel shows: 'Edit analytics'.

    This is Law B's own doctrine — an unsupported claim is narrowed, and
    the surviving name's lead is member-grounded BY CONSTRUCTION, so Law
    C's ``base_verb`` then grounds it without a new rung, a new
    vocabulary, or a lowered bar. The DISPLAY channel is the cure precisely
    because the CONFIDENCE channel must not be: grading the row high while
    its head still reads 'Create' is the banned any-conjunct rung (the row
    would wear a high over a verb nothing performs — the 2026-08-08
    C2-verb probe named that the NS-C machine and forbade it).

    ★ NS-44a — THE COVERAGE GUARD (warden §44, ratified). ★
    The law takes MEMBER NAMES, not a pre-computed family set, and that is
    load-bearing: dropping a conjunct asserts "no member performs this",
    which the family set CANNOT support when some member's lead verb is
    simply absent from the 99-word table. ``initialize-analytics-flow``
    folds to ``None`` — not to "no create" — yet 'initialize' is exactly
    how a create reads in a Rust codebase. The first cut treated that
    silence as evidence and deleted 'Create' from meilisearch UF-001 /
    UF-017 while their create-witness sat right there in the membership.

    That is the same UNKNOWN != UNWITNESSED inversion that killed fixb138
    Half-1 ("reading the table's complement as proof" — a 131-word
    corroboration set can only ever short-circuit TO grounded). So: if ANY
    member's lead token is outside the table, the witness set is INCOMPLETE
    and the law abstains entirely. Absence of evidence is not evidence of
    absence, and this law only ever acts on a fully-read membership.

    Returns the repaired display, or ``None`` when the law abstains:
      * ANY member flow lead is absent from the action-family table
        (NS-44a — the witness set is incomplete, so nothing may be dropped);
      * the row has no members at all (same reason, degenerate case);
      * the head is not a conjunct-list of >= 2 known verbs
        (anti-case: teable UF-065 'Share view or base publicly');
      * the LEAD's family IS witnessed — the name does not over-claim;
      * NO head verb's family is witnessed — nothing to keep, and
        inventing a head is not this law's job (Law C stamps an honest
        ``missing:verb`` and the row stays medium);
      * EVERY head verb is witnessed — the name is already true (no-op).
    """
    names = [str(n) for n in (member_names or ())]
    if not names:
        return None
    mfams: set[str] = set()
    for n in names:
        fam = _flow_action_family(n, idx)
        if fam is None:
            # NS-44a — a lead the table does not carry. The membership is
            # only PARTIALLY readable, so no conjunct can be proven absent.
            return None
        mfams.add(fam)
    parsed = _split_head_conjuncts(display, idx)
    if parsed is None:
        return None
    verbs, tail = parsed
    fams = []
    for v in verbs:
        low = re.sub(r"[^a-z0-9]+", "", v.lower())
        fam = idx["verb2fam"].get(low)
        # A head read-verb folds to 'browse' here (never 'view'): the id
        # marker that would pick 'view' lives in the TAIL, which this law
        # does not read. Both fold into _READ_FAMILIES, so a read-family
        # witness matches either way.
        fams.append("browse" if fam == "read" else fam)
    if fams[0] in mfams:
        return None  # lead is witnessed — no over-claim to repair
    keep = [v for v, f in zip(verbs, fams) if f in mfams]
    if not keep or len(keep) == len(verbs):
        return None  # nothing witnessed, or nothing to drop
    if len(keep) == 1:
        head = keep[0]
    elif len(keep) == 2:
        head = f"{keep[0]} and {keep[1]}"
    else:
        head = f"{', '.join(keep[:-1])}, and {keep[-1]}"
    # Restore the sentence capital the dropped lead was carrying.
    # ``polish_display_casing`` does not do this (the sibling narrowing
    # feeds it an already-capitalized '<Browse|View>' literal), and a
    # promoted conjunct arrives lower-cased from the source string:
    # 'Create and edit analytics' -> keep ['edit'] -> 'Edit analytics'.
    # Idempotent — 'Create and Edit GitHub Syncs' keeps 'Edit' untouched.
    if head and str(display or "")[:1].isupper():
        head = head[0].upper() + head[1:]
    return f"{head} {tail}".strip()


def flow_verb_class_agreement(
    display: str, member_names: Iterable[str], vocab: Mapping[str, Any],
) -> bool:
    """fixb142 Part 3 — the ``flow_verb_classes`` SECOND AXIS.

    True when the display's LEAD token and at least one MEMBER FLOW NAME's
    LEAD token fall in the same ``flow_verb_classes`` class.

    THE SAME CHANNEL, A SECOND TABLE. Law C's ``base_verb`` already trusts
    the member flow name's lead token — the flow-naming contract defines it
    as that flow's declared action. It buckets that token through ONE table
    (``journey-action-families.yaml``, the CRUD axis). The engine already
    ships a SECOND bucketing of the very same token
    (``naming-contract-vocab.yaml: flow_verb_classes`` — an action-DOMAIN
    axis: connect / ingest / send / receive / run / view), built for the
    synthesized-journey verdict, and Law C simply never reads it. 'Run
    batches' over ``process-batch-flow`` is invisible on the CRUD axis
    ('process' is in no CRUD family, so ``mfams`` is empty and ``base_verb``
    is structurally blind) and obvious on the domain axis (both 'run' and
    'process' are the ``run`` class).

    No new vocabulary, no new channel, no lowered bar — one more OR-source,
    exactly like the B50/B57 rungs. The ``manage`` fallback class is NOT
    consulted: it is the vocab's documented catch-all, so agreement there
    would assert nothing.

    MEASURED FALSE POSITIVE, banked not tuned: midday ``UF-L-6750c96446``
    'Run prompts' over ``build-invoice-components-flow`` — 'build' is a
    genuine member of the ``run`` class, so the rung fires on a row whose
    donor builds invoice components rather than running prompts. 1 of 12
    on the KS75 world. No scale-invariant discriminant separates it from
    the 8 true 'Run X' ← ``process-X-flow`` rows (resource-overlap kills 3
    true positives to kill this 1; a >=2-donor floor kills 3 more), and
    ``rule-no-magic-tuning`` forbids a per-repo one. The cost is measured,
    named, and pinned by ``test_midday_build_in_run_class_false_positive``.
    """
    classes: Mapping[str, Any] = vocab.get("flow_verb_classes") or {}
    if not classes:
        return False
    lead = _lead_token(display)
    if not lead:
        return False
    lead_cls = None
    for cls, verbs in classes.items():
        if cls == "manage":
            continue  # documented FALLBACK class — agreement proves nothing
        if lead in {str(v).lower() for v in (verbs or ())}:
            lead_cls = cls
            break
    if lead_cls is None:
        return False
    members = {str(v).lower() for v in (classes.get(lead_cls) or ())}
    return any(_lead_token(n) in members for n in member_names)


def _lead_is_modifier(
    lead: str,
    donor: str,
    lex: Mapping[str, int],
    flow_count: int,
    fold: Callable[[str], str],
) -> bool:
    """fixb130 — True when the echoed ``lead`` is a MODIFIER of the donor's
    real action rather than the action itself ('bulk' in
    ``bulk-delete-links-flow``).

    The echo rung's whole premise is the flow-naming contract: the lead
    token of a generated flow name IS that flow's declared action. Some
    generated names carry a QUALIFIER in front of the verb, and then the
    premise is simply false — the row 'Bulk links' (linkwarden UF-011,
    **high**) is grounded by a noun, exactly the class the twenty exhibit
    'Bulk Records' named. The discriminant asks the REPO, with the lexicon
    and the scale-invariant floor the C-B umbrella rung already banked
    (``max(2, ceil(0.025 * flows))`` — no new constant, no new list):

      * this repo does NOT use ``lead`` as an action (below the floor), AND
      * it DOES use the token immediately after it in the donor's own name.

    Both halves are needed. Dropping the first would refuse
    'Handle and run dump errors' (meilisearch UF-039) whose donor
    ``handle-parse-errors-flow`` merely happens to carry a second attested
    lead — 'handle' is itself attested 16 times there and IS the action.
    Dropping the second would refuse every legitimately rare verb the rung
    exists to ground ('crawl', 'upsert', 'summarise'), which is the
    2026-08-03 inversion this rung repaired. Measured on the KS66 world:
    the conjunction fires on 1 row of 3913, the one lying high."""
    if not lead or not donor:
        return False
    n = max(0, int(flow_count))
    floor = max(_UMBRELLA_LEAD_MIN, -(-_UMBRELLA_LEAD_PERMILLE * n // 1000))
    if int(lex.get(lead, 0)) >= floor:
        return False                       # the repo calls this an action
    toks = [t for t in _name_tokens(donor) if t != "flow"]
    if len(toks) < 2:
        return False
    return int(lex.get(fold(toks[1]), 0)) >= floor


def member_lead_echo_token(
    display: str,
    member_names: Iterable[str],
    resource_tokens: set[str] | frozenset[str],
    fold: Callable[[str], str],
    lex: Mapping[str, int] | None = None,
    flow_count: int = 0,
) -> str:
    """W1/C-A — the member-flow lead token a UF display's own LEAD token
    echoes, or ``''`` when nothing echoes.

    Both sides are read with :func:`_lead_token` (one tokenizer) and folded
    with the CALLER's singular-fold — Law C passes its live ``_sing``, so no
    second stemmer can drift from the one the rest of the rubric uses. No
    vocabulary is consulted: an out-of-vocab verb ('reset', 'accept',
    'authenticate', 'sync', 'monitor') grounds exactly like an in-vocab one.

    Two structural guards make this evidence and not a coincidence:

    * LEAD POSITION on BOTH sides — a token echoed from the middle of a
      member name ('billing' in ``sync-billing-flow``) is not the member's
      declared action and never grounds a verb;
    * NOUN-ECHO GUARD — a lead token that is also a RESOURCE-phrase token
      ('Sessions overview' ← ``session-list-flow``) is the resource echoing
      itself, not an action. The exact mirror of ``_grounds_resource``'s
      law that a verb echo may never stand in for resource evidence.
    * MODIFIER-LEAD GUARD (fixb130) — the echoed token must be the donor's
      ACTION, not a qualifier standing in front of it ('Bulk links' ←
      ``bulk-delete-links-flow``). See :func:`_lead_is_modifier`; it needs
      the repo lead lexicon, so passing no ``lex`` leaves the rung exactly
      as it behaved before (the guard cannot fire on an empty lexicon —
      every count is 0 and the second half of its conjunction fails).

    Exact token identity is STRICTLY STRONGER than the family agreement
    ``base_verb`` already accepts, so the rung cannot manufacture a claim
    the members do not make.
    """
    lead = fold(_lead_token(display))
    if not lead or lead in resource_tokens:
        return ""
    _lex = lex or {}
    for name in member_names:
        if lead == fold(_lead_token(name)):
            if _lead_is_modifier(lead, name, _lex, flow_count, fold):
                continue                   # a qualifier, not this flow's action
            return lead
    return ""


def repo_lead_lexicon(
    flow_names: Iterable[str], fold: Callable[[str], str],
) -> Counter:
    """C-B — LEAD-token frequency over the flow names of THIS repository.

    A MECHANISM, not a vocabulary: the corpus is the repo's own generated
    flow names, read with the same :func:`_lead_token` + caller fold as
    every other lead-token channel, so nothing here can drift from the
    rubric. One entry per FLOW (the caller must pass distinct flows — the
    ``flow_name_by_id`` map is keyed by both uuid and name and would
    double-count)."""
    lex: Counter = Counter()
    for name in flow_names:
        lead = fold(_lead_token(str(name or "")))
        if lead:
            lex[lead] += 1
    return lex


def umbrella_lead_token(
    display: str,
    lex: Mapping[str, int],
    flow_count: int,
    resource_tokens: set[str] | frozenset[str],
    fold: Callable[[str], str],
) -> str:
    """C-B — the UF display's LEAD token when the REPO'S OWN flow names
    declare it an umbrella, or ``''``.

    ``lex[lead] >= max(2, ceil(0.025 * flow_count))`` — an absolute floor
    (a token used once is an accident, never a repo's umbrella) plus a
    scale-invariant share so the rule reads the same on a 90-flow repo and
    a 1600-flow one. The ceiling is exact integer arithmetic (no float
    rounding surface); it agrees with ``math.ceil(0.025 * n)`` for every
    flow count a repo can carry.

    The noun-echo guard is W1's, verbatim: a lead token that is also a
    RESOURCE-phrase token is the resource echoing itself, never an action.
    The CALLER owns the ``lead is None`` (out-of-family) entry condition —
    a lead that DOES claim a CRUD family is a specific verb and must be
    performed by a member, never abstracted over."""
    lead = fold(_lead_token(display))
    if not lead or lead in resource_tokens:
        return ""
    n = max(0, int(flow_count))
    floor = max(_UMBRELLA_LEAD_MIN, -(-_UMBRELLA_LEAD_PERMILLE * n // 1000))
    return lead if int(lex.get(lead, 0)) >= floor else ""


#: B61 — deterministic dominant-family priority for a member verb-composition.
#: Mutation families outrank read (a WRITE is the stronger claim the code
#: makes — SACRED: mutation name only over a mutation composition); ties break
#: by this frozen CRUD order. The composition families a journey can ever imply
#: are exactly ``member_verb_composition``'s range — the HTTP-method families
#: (:data:`_HTTP_METHOD_VERB_FAMILIES`) ∪ the page-read families
#: (:data:`_PAGE_VERB_FAMILIES`) = {browse, view, create, update, delete}; no
#: "act"/"read" bucket ever appears, so every family here has a canonical
#: display verb in :data:`_ACTION_FAMILY_WORD`.
_SNAP_MUTATION_ORDER: tuple[str, ...] = ("create", "update", "delete")
_SNAP_READ_ORDER: tuple[str, ...] = ("browse", "view")


def _dominant_comp_family(comp: Iterable[str]) -> str | None:
    """The family whose canonical verb a verb-snap adopts: the first present
    mutation family (create → update → delete) when the composition mutates,
    else the first present read family (browse → view). ``None`` when the
    composition names no snap-eligible family (defensive; e.g. an empty set —
    the caller must already have skipped it)."""
    fams = set(comp)
    for fam in _SNAP_MUTATION_ORDER:
        if fam in fams:
            return fam
    for fam in _SNAP_READ_ORDER:
        if fam in fams:
            return fam
    return None


def _snap_lead_verb(
    name: str, target_fam: str, vocab: Mapping[str, Any],
) -> str:
    """Replace a UF display's LEADING word (the verb that lies) with the
    canonical verb of ``target_fam`` (:data:`_ACTION_FAMILY_WORD` — the
    engine's frozen per-family display verb; for the composition families it
    IS the family's canonical head verb, e.g. create → "Create"), preserving
    the resource remainder VERBATIM, then run the FULL B50 chain (degrime echo
    collapse + casing polish). 'Manage webhooks' + create → 'Create webhooks';
    'Handle incoming events' + delete → 'Delete incoming events'. ONLY the
    single leading token is replaced (the resource part is SACRED — spec B61)."""
    verb = _ACTION_FAMILY_WORD.get(target_fam)
    if not verb:
        return name
    parts = (name or "").strip().split(None, 1)
    remainder = parts[1] if len(parts) == 2 else ""
    snapped = f"{verb} {remainder}".strip() if remainder else verb
    if uf_name_degrime_enabled():
        snapped = _degrime_display(snapped)
    return polish_display_casing(snapped, vocab)


def _action_family_from_domain(domain: str) -> str | None:
    """``lattice:action:<res>-<fam>`` → ``<fam>`` (the labeler-collapsed
    action child's true family)."""
    d = str(domain or "")
    if not d.startswith("lattice:action:"):
        return None
    key = d.split("lattice:action:", 1)[1]
    fam = key.rsplit("-", 1)[-1] if "-" in key else ""
    return fam if fam in _ACTION_FAMILY_WORD else None


def _with_cli_declared(
    uf_authored_names: Mapping[str, Iterable[str]] | None,
    user_flows: Iterable[Any],
) -> dict[str, list[str]]:
    """fixb128 addendum — CLI author-declared rows JOIN the authored map.

    THE MEASURED LEAK (live keyed ollama c27, the board fixb128 shipped
    against): the mint emitted all 10 names from the author's own
    ``Short:`` (``named_declared: 10, named_template: 0`` — VERIFIED in
    that board's own telemetry) and the board still shipped 'Manage cp',
    'Manage rm', 'Manage stop', 'Ingest push', 'Browse & filter models',
    'View model information'. ``uf_synth_named: 7``.

    The first cut of this fix protected the wrong door. It taught
    :func:`_uf_protected` the ``cli-declared`` stamp — and that guards the
    LAWS — while the row was actually being re-worded by the SYNTH-NAMING
    path, whose authored check is ``_authored_for(uf)``: a lookup in the
    id-keyed ``uf_authored_names`` map that a CLI row was never in. Two
    doors, one guarded.

    So the stamp is translated ONCE into the authored channel itself, and
    every consumer that already honours maintainer-authored journeys —
    ``_authored_for`` (candidate lead + synth-naming skip), ``authored_ids``
    (:func:`_uf_protected`), and the 6.7e adjudicator downstream — covers
    CLI rows uniformly, with no per-call-site patching left to forget.

    Template-named CLI rows are deliberately NOT included: they wear
    ``cli-template`` and carry no author's word to defend.
    """
    from wystan.pipeline_v2.cli_command_journeys import is_cli_declared

    out: dict[str, list[str]] = {
        str(k): list(v or ()) for k, v in (uf_authored_names or {}).items()
    }
    for uf in (user_flows or ()):
        if not is_cli_declared(uf):
            continue
        uid = str(getattr(uf, "id", "") or "")
        name = str(getattr(uf, "name", "") or "").strip()
        if uid and name:
            out.setdefault(uid, [name])
    return out


def _uf_protected(uf: Any, authored_ids: set[str], keeper_on: bool) -> bool:
    """Maintainer-authored or pinned journeys are never re-worded by the laws."""
    if str(getattr(uf, "id", "") or "") in authored_ids:
        return True
    # fixb128 (NS-2) — a CLI command journey wearing the summary its author
    # declared beside the command (cobra ``Short: "Copy a model"``) is
    # maintainer-authored prose living in CODE. It joins the authored class
    # by STAMP rather than by id, so it survives every renumbering between
    # the 6.7d-tail mint and this stage. Measured: without it the generic
    # R5-2 own-resource template re-worded 'Copy a model' → 'Manage cp'.
    from wystan.pipeline_v2.cli_command_journeys import is_cli_declared
    if is_cli_declared(uf):
        return True
    return bool(
        keeper_on and isinstance(getattr(uf, "identity", None), dict)
        and (uf.identity or {}).get("pinned_from")
    )


def _conf_hist(user_flows: Iterable[Any]) -> dict[str, int]:
    h = {"high": 0, "medium": 0, "low": 0}
    for u in user_flows:
        c = str(getattr(u, "name_confidence", "") or "low")
        h[c] = h.get(c, 0) + 1
    return h


def _apply_uf_name_laws(
    user_flows: list[Any],
    pf_by_slug: Mapping[str, Any],
    vocab: Mapping[str, Any],
    flow_name_by_id: Mapping[str, str],
    tele: dict[str, Any],
    *,
    authored_ids: set[str],
    keeper_on: bool,
    nav_labels: Mapping[str, str] | None = None,
    flow_origin_by_id: Mapping[str, str] | None = None,
    flow_by_id: Mapping[str, Any] | None = None,
    nav_label_sets: Mapping[str, list[str]] | None = None,
    routes_index: Iterable[Mapping[str, Any]] | None = None,
    repo_root: Any = None,
    adjudicated_sources: Mapping[str, Mapping[str, Iterable[str]]] | None = None,
    r5_evidence: tuple[
        MemberEvidence, Mapping[str, MemberEvidence],
        Mapping[str, MemberEvidence]] | None = None,
    primary_pass: bool = True,
    post_adjudicator: bool = False,
) -> None:
    """B9 — three deterministic UF display laws over FINAL members/names, run
    AFTER the labeler so labeler-introduced collisions/over-claims are caught.
    Mutates ONLY ``uf.name`` / ``uf.name_confidence`` — identity, membership,
    product_feature_id, paths untouched (I12/I14/I15/I16-neutral)."""
    from collections import defaultdict

    idx = _action_family_index(vocab)

    # ── R5 phase-2 (WYSTAN_NAMING_WAVE_R5, default ON since 2026-07-21) — member-evidence
    # pool + vocab sets for the rename/plural/conf-drop/brand-echo lanes.
    # ``r5_evidence`` is threaded by run_naming_contract (built once); the
    # 6.7e rescore seam rebuilds it here so BOTH passes apply the SAME laws
    # (idempotent: a healed name re-derives to itself). OFF ⇒ None ⇒ every
    # R5 phase-2 block below is a no-op ⇒ byte-identical.
    _r5_on = naming_wave_r5_enabled()
    _r5_sets: Mapping[str, Any] | None = None
    _r5_repo_ev: MemberEvidence | None = None
    _r5_uf_ev: Mapping[str, MemberEvidence] = {}
    if _r5_on:
        _r5_sets = r5_vocab_sets(vocab)
        if r5_evidence is None:
            r5_evidence = build_board_evidence(
                user_flows, list(pf_by_slug.values()), flow_by_id or {},
                repo_root)
        _r5_repo_ev, _r5_uf_ev_m, _ = r5_evidence
        _r5_uf_ev = _r5_uf_ev_m

    def _members(uf: Any) -> list[str]:
        return [flow_name_by_id.get(str(m), str(m))
                for m in (getattr(uf, "member_flow_ids", None) or [])]

    def _mfams(names: list[str]) -> set[str]:
        return {f for f in (_flow_action_family(n, idx) for n in names) if f}

    def _pfd(uf: Any) -> str:
        pf = pf_by_slug.get(str(getattr(uf, "product_feature_id", None) or ""))
        return (str(getattr(pf, "display_name", None) or getattr(pf, "name", "") or "")
                if pf is not None else "")

    def _res(uf: Any) -> str:
        base = str(getattr(uf, "resource", "") or "") or _pfd(uf)
        base = re.sub(r"[-_]+", " ", base).strip()
        return _resource_phrase(base, vocab) or base

    def _uf_member_evidence(uf: Any) -> frozenset[str]:
        """B70 — resource tokens the UF's OWN evidence grounds (member flow
        names + resource + resource-phrase), singular-folded. Arms the
        WYSTAN_NAMING_LAW member-evidence display law so a grounded
        verb-homonym resource survives and an evidence-less remainder is
        flagged. Only consulted when that flag is armed (OFF ⇒ ignored, so
        threading it here is byte-identical when the flag is off)."""
        toks: set[str] = set()
        srcs = list(_members(uf))
        srcs.append(str(getattr(uf, "resource", "") or ""))
        srcs.append(_res(uf))
        for src in srcs:
            for tok in re.split(r"[^a-z0-9]+", (src or "").lower()):
                if tok:
                    toks.add(_degrime_sing(tok))
        return frozenset(toks)

    def _folded(uf: Any) -> str:
        return str(getattr(uf, "name", "") or "").strip().lower()

    def _is_lattice(uf: Any) -> bool:
        return (str(getattr(uf, "domain", "") or "").startswith("lattice")
                or str(getattr(uf, "id", "") or "").startswith("UF-L-"))

    ordered = sorted(user_flows, key=lambda u: str(getattr(u, "id", "") or ""))
    narrowed: set[str] = set()
    qualified: set[str] = set()

    # ── Law B — name-claim narrowing (ORGANIC journeys only) ─────────
    # A name that LEADS with a write family (create/update/delete) while EVERY
    # member is a read (browse/view) claims an action absent from the evidence
    # → narrow to the strictly-narrower read name "<Browse|View> <resource>"
    # (never widen to the generic "Manage" fallback). Mixed-member over-claims
    # (some act/write member) are left named but flagged low by Law C, and
    # justified wide names (a real write member) are untouched entirely.
    # Lattice action children are EXEMPT — their canonical "<Family>
    # <resource>" identity is authored by Law A, not a false claim.
    for uf in ordered:
        if _uf_protected(uf, authored_ids, keeper_on) or _is_lattice(uf):
            continue
        names = _members(uf)
        if not names:
            continue
        mfams = _mfams(names)
        lead = _name_lead_family(str(getattr(uf, "name", "") or ""), idx)
        if (lead in _WRITE_FAMILIES and mfams and mfams <= _READ_FAMILIES
                and lead not in mfams):
            # fixb130 / warden #35 bonus pin — the action-family vocabulary
            # folds 'view' INTO the browse family unless an id-marker is
            # present, so a cohort whose every member is literally
            # ``view-*-flow`` arrives here as ``mfams == {'browse'}`` and the
            # narrowing writes 'Browse …' over members that all say View
            # (novu / jsonhero). The members' own LEAD TOKEN is the mechanism
            # the families merely bucket (the W1 argument, verbatim): when it
            # is unanimously 'view', the display says View.
            # ARMED (default OFF): the pin overturns a BANKED doctrine with
            # named tests (test_read_only_over_claim_narrowed and the
            # fixb129 kill-switch / default-arm pair all assert 'Browse
            # webhook' over ``view-webhooks-flow``), and the fixb129 ruling
            # is explicit that such a change is a flip event, not a bugfix
            # rider. Unset ⇒ 'Browse' exactly as banked.
            _leads = {_lead_token(n) for n in names}
            word = ("View" if ("view" in mfams
                               or (uf_view_lead_pin_enabled()
                                   and _leads == {"view"}))
                    else "Browse")
            cand = polish_display_casing(f"{word} {_res(uf)}".strip(), vocab)
            if (cand and cand.strip().lower() != _folded(uf)
                    and not display_law_violations(
                        cand, vocab, pf_display=_pfd(uf) or None,
                        member_tokens=_uf_member_evidence(uf))):
                uf.name = cand
                narrowed.add(str(getattr(uf, "id", "") or ""))
                tele["uf_claim_narrowed"] = tele.get("uf_claim_narrowed", 0) + 1

    # ── Law B′ — composite-head repair (fixb142 Part 1) ───────────────
    # The sibling of the narrowing above for the COMPOSITE shape it cannot
    # reach: 'Create and edit analytics' does not satisfy ``mfams <=
    # _READ_FAMILIES`` (its members are update-family), so the narrowing
    # never looks at it, and the unwitnessed 'Create' head survives to be
    # stamped ``missing:verb`` by Law C. Repair = drop the unwitnessed
    # conjuncts, keep the witnessed ones in their original order.
    #
    # A SEPARATE loop on purpose: the narrowing loop above stays diff-free
    # so its kill-switch parity is provable by inspection, and rows the
    # narrowing already rewrote are skipped outright (``uid in narrowed``)
    # — a narrowed name is '<Browse|View> <resource>' and has no conjuncts
    # left to repair.
    #
    # ★ LOAD-BEARING — repaired uids are NOT added to ``narrowed``. ★
    # ``narrowed`` is the input to the hard ``low`` + ``['missing:verb']``
    # stamp that fires whenever the fixb129 rubric is out of scope (see
    # ``narrowed_rubric_rescore_enabled``). Registering a repaired row
    # there would hard-``low`` all of them in the very next post-mint
    # rescore — the exact trap that froze seven rows since KS66. The
    # repaired name needs no bookkeeping: its lead is member-grounded BY
    # CONSTRUCTION, so Law C's ordinary ``base_verb`` grounds it.
    #
    # Guards are the narrowing's own, reused verbatim: authored/pinned and
    # lattice rows are exempt (organic journeys only), the candidate must
    # actually change the name, and it must be law-clean
    # (``display_law_violations`` — collision safety, Law A uniqueness runs
    # after). Flag OFF ⇒ no row is visited ⇒ names / confidence / evidence
    # / telemetry / serialized output byte-identical.
    if uf_composite_head_repair_enabled():
        _chr_rows: list[str] = []
        # COLLISION SAFETY (B31 lesson, and the reason this is not merely
        # ``display_law_violations``): that guard grades a name in
        # isolation and knows nothing about the board's OTHER rows. Two
        # composites over the same resource ('Create and edit analytics' /
        # 'Add and edit analytics') both repair to 'Edit analytics', and
        # Law A below can only separate them when a distinct qualifier
        # exists — identical resource + identical PF leaves it with an
        # empty ``quals`` list and the duplicate stands. So the repair
        # claims a display up-front and refuses to land on one already
        # taken. ``ordered`` is id-sorted, so which row wins is
        # deterministic; the loser keeps its composite name and its honest
        # medium, i.e. exactly the OFF behaviour.
        _taken_disp: dict[str, str] = {}
        for uf in ordered:
            _fold = _folded(uf)
            if _fold:
                _taken_disp.setdefault(_fold, str(getattr(uf, "id", "") or ""))
        for uf in ordered:
            uid = str(getattr(uf, "id", "") or "")
            if uid in narrowed:
                continue
            if _uf_protected(uf, authored_ids, keeper_on) or _is_lattice(uf):
                continue
            # ── NS-44b — a repair must BUY something (warden §44, ruled) ──
            # The law's justification is that an unwitnessed head costs the
            # row its grade. A row already at ``high`` is by definition
            # grounded, so the rewrite buys nothing and only ever spends:
            # the world census found all five already-high fires read WORSE
            # after repair — 'Browse and edit fraud settings' -> 'Edit fraud
            # settings' on a settings surface that plainly browses, and the
            # same shape on highlight / tracecat / trigger.dev / webstudio.
            # Every one of them is a `Browse|View and <write>` display whose
            # read half the 99-word table simply cannot witness.
            #
            # So the gate is: repair only where the grade is actually being
            # withheld. Scale-invariant, no vocabulary, no per-repo number —
            # it reads the row's OWN grade. World effect: 13 fires -> 8.
            if str(getattr(uf, "name_confidence", "") or "high") == "high":
                tele["uf_composite_head_high_skipped"] = tele.get(
                    "uf_composite_head_high_skipped", 0) + 1
                continue
            names = _members(uf)
            if not names:
                continue
            # Own variable (not the narrowing loop's ``cand``) — this one is
            # Optional by contract, the narrowing's is not. MEMBER NAMES go
            # in, not ``_mfams(names)``: the NS-44a coverage guard has to see
            # the table MISSES, and a family set has already thrown them away.
            _repaired = composite_head_repair(
                str(getattr(uf, "name", "") or ""), names, idx)
            if not _repaired:
                continue
            _repaired = polish_display_casing(_repaired, vocab)
            _cand_fold = _repaired.strip().lower()
            _owner = _taken_disp.get(_cand_fold)
            if _owner is not None and _owner != uid:
                tele["uf_composite_head_collision_refused"] = tele.get(
                    "uf_composite_head_collision_refused", 0) + 1
                continue
            if (_repaired and _cand_fold != _folded(uf)
                    and not display_law_violations(
                        _repaired, vocab, pf_display=_pfd(uf) or None,
                        member_tokens=_uf_member_evidence(uf))):
                _chr_rows.append(
                    f"{uid}: {getattr(uf, 'name', '')!r} -> {_repaired!r}")
                _taken_disp.pop(_folded(uf), None)
                _taken_disp[_cand_fold] = uid
                uf.name = _repaired
        # Emitted ONLY when non-empty so a board the law does not move keeps
        # a byte-identical telemetry block (the fixb138 idiom). Carries the
        # NAMES of every moved row (the fixb140 permanent-record law).
        if _chr_rows:
            tele["uf_composite_head_repaired"] = sorted(_chr_rows)

    # ── Law A — UF-vs-UF display uniqueness (never a numeric suffix) ──
    # step 1: undo the labeler's lossy collapse — a colliding lattice action
    # child reverts to its deterministic "<Family> <resource>" name.
    # B50 (degrime ON only): the re-derived cand carries a DEGRIMED resource
    # phrase, so it can newly collide with a third row — apply step-1 renames
    # collision-safely (targets computed first, then only non-colliding
    # renames land; skip-both on duplicate targets). Flag OFF ⇒ the original
    # immediate-apply path, byte-identical.
    _lawa_two_phase = uf_name_degrime_enabled()
    _lawa_proposals: dict[str, str] = {}
    groups: dict[str, list[Any]] = defaultdict(list)
    for uf in ordered:
        groups[_folded(uf)].append(uf)
    for _f, grp in sorted(groups.items()):
        if len(grp) < 2:
            continue
        for uf in grp:
            if _uf_protected(uf, authored_ids, keeper_on):
                continue
            fam = _action_family_from_domain(str(getattr(uf, "domain", "") or ""))
            if not fam:
                continue
            cand = polish_display_casing(
                f"{_ACTION_FAMILY_WORD[fam]} {_res(uf)}".strip(), vocab)
            if (cand and cand.strip().lower() != _folded(uf)
                    and not display_law_violations(
                        cand, vocab, pf_display=_pfd(uf) or None,
                        member_tokens=_uf_member_evidence(uf))):
                if _lawa_two_phase:
                    _lawa_proposals[str(getattr(uf, "id", "") or "")] = cand
                else:
                    uf.name = cand
    if _lawa_proposals:
        _cur = {str(getattr(u, "id", "") or ""): str(getattr(u, "name", "") or "")
                for u in ordered}
        _by_id = {str(getattr(u, "id", "") or ""): u for u in ordered}
        for _uid in sorted(degrime_rename_plan(_cur, _lawa_proposals)):
            _by_id[_uid].name = _lawa_proposals[_uid]
    # step 2: qualify any residual collision from distinguishing evidence.
    taken: dict[str, str] = {}
    for uf in ordered:
        taken.setdefault(_folded(uf), str(getattr(uf, "id", "") or ""))
    groups = defaultdict(list)
    for uf in ordered:
        groups[_folded(uf)].append(uf)
    for _f, grp in sorted(groups.items()):
        if len(grp) < 2:
            continue
        keep = grp[0]  # smallest id keeps the base display
        for uf in grp[1:]:
            if _uf_protected(uf, authored_ids, keeper_on):
                continue
            base = str(getattr(uf, "name", "") or "")
            quals: list[str] = []
            # distinct resource, then owning PF, then route/domain tail
            r = str(getattr(uf, "resource", "") or "")
            if r and r.strip().lower() != str(getattr(keep, "resource", "") or "").strip().lower():
                quals.append(_resource_phrase(r, vocab) or r)
            pfd = _pfd(uf)
            if pfd and pfd.strip().lower() != _pfd(keep).strip().lower():
                quals.append(pfd)
            fam = _action_family_from_domain(str(getattr(uf, "domain", "") or ""))
            if fam:
                quals.append(_ACTION_FAMILY_WORD[fam].lower())
            for q in quals:
                # B50 Seg1 — never append a qualifier that merely restates a
                # word already in the base ('Teams (Team)', 'Manage links
                # (link)', 'Manage settings (Settings)', 'Manage tRPC (tRPC)').
                if uf_name_degrime_enabled() and _qualifier_echoes_base(base, q):
                    continue
                cand_raw = f"{base} ({q})"
                if _r5_on and _r5_sets is not None:
                    # R5-4 — compose site 1/3: canonical joint before polish.
                    cand_raw, _r5_rule = canonicalize_compose(cand_raw, _r5_sets)
                    if _r5_rule:
                        tele["r5_compose_canonicalized"] = (
                            tele.get("r5_compose_canonicalized", 0) + 1)
                cand = polish_display_casing(cand_raw, vocab)
                fld = cand.strip().lower()
                if (fld not in taken
                        and not display_law_violations(
                            cand, vocab, pf_display=pfd or None,
                            member_tokens=_uf_member_evidence(uf))):
                    uf.name = cand
                    taken[fld] = str(getattr(uf, "id", "") or "")
                    qualified.add(str(getattr(uf, "id", "") or ""))
                    tele["uf_uniqueness_qualified"] = tele.get("uf_uniqueness_qualified", 0) + 1
                    break

    # ── Law C — evidence-derived name_confidence (one rubric, all sources) ──
    # B40 (provenance rungs, WYSTAN_NAME_EVIDENCE_RUNGS): the base rubric is
    # unchanged; when the flag is ON two extra grounding rungs may fire — a
    # nav-label token match (resource-grounding) and an all-dispatch-member
    # registry provenance (verb-grounding for Run/act leads) — and EVERY arm
    # stamps ``name_evidence`` (fired rungs, or ``missing:*`` for a low). The
    # flag NEVER changes a UF NAME; with it OFF the confidence values and the
    # serialized output are byte-identical to pre-B40 (name_evidence stays None).
    # ── B50 Seg2: raw-param display law over the FINAL UF name (mutate a
    # glyph-less route-param slug to its noun core, drop standalone
    # addressing tokens) — applied before Law C so confidence is scored on
    # the clean name. DISPLAY-ONLY; protected (authored/pinned) journeys are
    # never re-worded. COLLISION-SAFE (kan forensics): targets are computed
    # first over sorted UFs, then only non-colliding renames apply — two
    # rows deparaming to the same name ('boardids'/'boardslugs' → 'board')
    # BOTH keep their original names. Flag OFF ⇒ byte-identical.
    if uf_name_degrime_enabled():
        dep_proposals: dict[str, str] = {}
        for uf in ordered:
            if _uf_protected(uf, authored_ids, keeper_on):
                continue
            cur = str(getattr(uf, "name", "") or "")
            deparamed = _deparam_display(cur)
            if (deparamed and deparamed != cur
                    and not display_law_violations(
                        deparamed, vocab, pf_display=_pfd(uf) or None,
                        member_tokens=_uf_member_evidence(uf))):
                dep_proposals[str(getattr(uf, "id", "") or "")] = deparamed
        if dep_proposals:
            cur_names = {
                str(getattr(u, "id", "") or ""): str(getattr(u, "name", "") or "")
                for u in ordered
            }
            allowed = degrime_rename_plan(cur_names, dep_proposals)
            by_id = {str(getattr(u, "id", "") or ""): u for u in ordered}
            for uid in sorted(allowed):
                by_id[uid].name = dep_proposals[uid]
                tele["uf_name_degrimed"] = tele.get("uf_name_degrimed", 0) + 1
            skipped = len(dep_proposals) - len(allowed)
            if skipped:
                tele["uf_degrime_collision_skipped"] = (
                    tele.get("uf_degrime_collision_skipped", 0) + skipped)

    # ── fixb104 — the ``stranded_connective`` law's REPAIR sweep ─────────
    # The law above is consulted by every producer that mints a name; this
    # is the seam that heals a name that STRANDED AFTER its mint. It runs
    # over the CURRENT rows inside ``_apply_uf_name_laws``, so it covers
    # BOTH invocations of this body — the contract pass (organic 6.7 rows,
    # route_group_recall seeds, 6.7d backstop seeds, journey-lattice rows)
    # and the ``postmint_uf_rescore`` hook (uf_cases_split children,
    # spray survivors) — i.e. every producer, independent of its mint
    # path. Placed BEFORE Law C so the confidence is scored on the clean
    # name (the B50 Seg2 precedent three blocks up), and DROP-only, so no
    # row can gain a word it did not earn. Protected (authored / pinned)
    # journeys are exempt like every other display law, and the rename is
    # collision-safe through the SAME plan the degrime pass uses. Flagless
    # (Law-B): the OFF arm carries the class too.
    _st_proposals: dict[str, str] = {}
    for uf in ordered:
        if _uf_protected(uf, authored_ids, keeper_on):
            continue
        _cur_st = str(getattr(uf, "name", "") or "")
        if "stranded_connective" not in display_law_violations(_cur_st, vocab):
            continue
        _fixed_st = _trim_stranded_display(_cur_st)
        if _fixed_st and _fixed_st != _cur_st and not display_law_violations(
                _fixed_st, vocab, pf_display=_pfd(uf) or None,
                member_tokens=_uf_member_evidence(uf)):
            _st_proposals[str(getattr(uf, "id", "") or "")] = _fixed_st
    if _st_proposals:
        _st_cur = {
            str(getattr(u, "id", "") or ""): str(getattr(u, "name", "") or "")
            for u in ordered
        }
        _st_by_id = {str(getattr(u, "id", "") or ""): u for u in ordered}
        _st_allowed = degrime_rename_plan(_st_cur, _st_proposals)
        for _uid_st in sorted(_st_allowed):
            _st_by_id[_uid_st].name = _st_proposals[_uid_st]
            tele["uf_stranded_trimmed"] = tele.get("uf_stranded_trimmed", 0) + 1
        _st_skipped = len(_st_proposals) - len(_st_allowed)
        if _st_skipped:
            tele["uf_stranded_collision_skipped"] = (
                tele.get("uf_stranded_collision_skipped", 0) + _st_skipped)

    # ── B61 Seg1 — evidence-born verb-snap (WYSTAN_UF_VERB_SNAP) ──
    # A UF display whose LEAD-verb family is ABSENT from the member
    # verb-composition (the name's verb lies about the code) has that lead
    # verb REPLACED by the canonical verb of the composition's DOMINANT
    # family (mutation outranks read). The resource remainder, membership,
    # identity, and lineage are untouched; authored/pinned rows are exempt;
    # an EMPTY composition leaves the name UNCHANGED (no facts → no claim →
    # honest missing:verb below). Runs BEFORE Law C so the snapped name is
    # scored by the existing structural:verb-composition rung (earned high
    # at $0, requires WYSTAN_UF_RUNG_SOURCES_V2 co-armed). COLLISION-SAFE
    # (B31): targets computed first, two rows never snap to one name. This
    # body — inside _apply_uf_name_laws — runs identically in the initial
    # contract pass and the B57 Seg2 rescore seam; it is IDEMPOTENT (once
    # lead ∈ comp the snap never refires). Flag OFF ⇒ names/confidence/
    # serialized output byte-identical (the ONLY UF-name-changing flag).
    _snap_on = uf_verb_snap_enabled()
    _snap_mf: dict[str, set[str]] = {}
    _snap_pf: set[str] = set()
    _snap_fbi: Mapping[str, Any] = flow_by_id or {}
    _snap_tele: dict[str, Any] = {}
    if _snap_on:
        _snap_tele = tele.setdefault("uf_verb_snap", {
            "snapped": 0, "families": {}, "skipped_empty": 0,
            "skipped_authored": 0, "skipped_collision": 0,
            "generic_grounded": 0,
        })
        _snap_mf, _snap_pf = route_verb_indexes(routes_index)
        # B108 R1/R2 — armed by EVIDENCE (handler rows on the board), not
        # by the supply env flag: a board the handler channel never
        # supplied keeps byte-identical snap behaviour with the flag
        # armed. Empty set ⇒ both guards are dead code for that board.
        _snap_guards = bool(supplied_handler_files(routes_index))
        _snap_proposals: dict[str, str] = {}
        _snap_fam: dict[str, str] = {}
        for uf in ordered:
            if _uf_protected(uf, authored_ids, keeper_on):
                _snap_tele["skipped_authored"] += 1
                continue
            cur = str(getattr(uf, "name", "") or "")
            lead = _name_lead_family(cur, idx)
            if lead is None:
                continue  # no recognized lead verb — nothing to fold (honest)
            comp = member_verb_composition(uf, _snap_fbi, _snap_mf, _snap_pf)
            if not comp:
                _snap_tele["skipped_empty"] += 1
                continue  # SACRED — empty composition, name unchanged
            if lead in comp:
                continue  # verb already grounded by composition — no change
            # b61-iter3 NEVER-WORSE guard (real keyed samples caught it):
            # a lead the member FLOW-NAME families already witness (Law
            # C's base ``lead in mfams`` source) is TRUE — page-only
            # compositions under-represent mutations (server actions are
            # invisible to routes_index), so overwriting a member-named
            # Create/Verify/Run lead with a read verb would make the name
            # LIE and could demote an already-high row ('Create and
            # manage data rooms' -> 'Browse ...' harm class). Snap fires
            # ONLY for rows whose lead no verb source grounds — the
            # would-be missing:verb residue.
            if lead in _mfams(_members(uf)):
                _snap_tele["skipped_member_named"] = (
                    _snap_tele.get("skipped_member_named", 0) + 1)
                continue
            # ── B108 R2 — partial composition claims no truth ──────────
            if _snap_guards and not snap_composition_complete(
                    uf, _snap_fbi, _snap_mf):
                _snap_tele["skipped_incomplete"] = (
                    _snap_tele.get("skipped_incomplete", 0) + 1)
                continue
            target = _dominant_comp_family(comp)
            if target is None:
                continue
            # ── B108 R1 — a snap refines a claim, never flips it ───────
            if _snap_guards and snap_crosses_polarity(lead, target):
                _snap_tele["skipped_polarity"] = (
                    _snap_tele.get("skipped_polarity", 0) + 1)
                continue
            snapped = _snap_lead_verb(cur, target, vocab)
            # Defense in depth: only commit when the snapped lead verb truly
            # folds back INTO the composition (earned-high by construction)
            # and the result is law-clean (no pf_uf_twin / param / etc.).
            if (snapped and snapped.strip().lower() != cur.strip().lower()
                    and _name_lead_family(snapped, idx) in comp
                    and not display_law_violations(
                        snapped, vocab, pf_display=_pfd(uf) or None,
                        member_tokens=_uf_member_evidence(uf))):
                _uid = str(getattr(uf, "id", "") or "")
                _snap_proposals[_uid] = snapped
                _snap_fam[_uid] = target
        if _snap_proposals:
            _snap_cur = {
                str(getattr(u, "id", "") or ""): str(getattr(u, "name", "") or "")
                for u in ordered
            }
            _snap_by_id = {str(getattr(u, "id", "") or ""): u for u in ordered}
            _snap_allowed = degrime_rename_plan(_snap_cur, _snap_proposals)
            for _uid in sorted(_snap_allowed):
                _snap_by_id[_uid].name = _snap_proposals[_uid]
                _snap_tele["snapped"] += 1
                _fam = _snap_fam[_uid]
                _snap_tele["families"][_fam] = (
                    _snap_tele["families"].get(_fam, 0) + 1)
            _snap_tele["skipped_collision"] += (
                len(_snap_proposals) - len(_snap_allowed))

    # ── R5-3 (WYSTAN_NAMING_WAVE_R5) — member-evidence display derivation
    # over the FINAL UF names, before Law C so confidence is scored on the
    # healed name (the B50-deparam precedent). Two rungs, both COLLISION-SAFE
    # via degrime_rename_plan and law-checked, protected journeys exempt:
    #   1. split-core rename ('Manage pagelayouts' -> 'Manage page layouts',
    #      'Manage signup' -> 'Manage sign up', 'Connect api_keys' ->
    #      'Connect API keys' after casing polish);
    #   2. plural rung ('Manage account setting' -> '... settings' on >= 3x
    #      member evidence, anchor-source segment excluded).
    # Idempotent: a healed name re-derives to itself in the 6.7e rescore.
    if _r5_on and _r5_sets is not None and _r5_repo_ev is not None:
        _r5_empty = MemberEvidence()
        _r5_split_props: dict[str, str] = {}
        for uf in ordered:
            if _uf_protected(uf, authored_ids, keeper_on):
                continue
            _uid = str(getattr(uf, "id", "") or "")
            cur = str(getattr(uf, "name", "") or "")
            healed, _r5_srcs = derive_split_display(
                cur, _r5_uf_ev.get(_uid) or _r5_empty, _r5_repo_ev, _r5_sets)
            if _r5_srcs and healed != cur:
                healed = polish_display_casing(healed, vocab)
            if (healed != cur
                    and not display_law_violations(
                        healed, vocab, pf_display=_pfd(uf) or None,
                        member_tokens=_uf_member_evidence(uf))):
                _r5_split_props[_uid] = healed
        if _r5_split_props:
            _r5_cur = {
                str(getattr(u, "id", "") or ""): str(getattr(u, "name", "") or "")
                for u in ordered
            }
            _r5_by_id = {str(getattr(u, "id", "") or ""): u for u in ordered}
            for _uid in sorted(degrime_rename_plan(_r5_cur, _r5_split_props)):
                _r5_by_id[_uid].name = _r5_split_props[_uid]
                tele["r5_split_renamed"] = tele.get("r5_split_renamed", 0) + 1
        _r5_plural_props: dict[str, str] = {}
        for uf in ordered:
            if _uf_protected(uf, authored_ids, keeper_on):
                continue
            _uid = str(getattr(uf, "id", "") or "")
            cur = str(getattr(uf, "name", "") or "")
            plur = plural_rename(
                cur, _r5_uf_ev.get(_uid) or _r5_empty, _r5_sets)
            if (plur is not None and plur != cur
                    and not display_law_violations(
                        plur, vocab, pf_display=_pfd(uf) or None,
                        member_tokens=_uf_member_evidence(uf))):
                _r5_plural_props[_uid] = plur
        if _r5_plural_props:
            _r5_cur = {
                str(getattr(u, "id", "") or ""): str(getattr(u, "name", "") or "")
                for u in ordered
            }
            _r5_by_id = {str(getattr(u, "id", "") or ""): u for u in ordered}
            for _uid in sorted(degrime_rename_plan(_r5_cur, _r5_plural_props)):
                _r5_by_id[_uid].name = _r5_plural_props[_uid]
                tele["r5_plural_renamed"] = tele.get("r5_plural_renamed", 0) + 1

    # ── fixb132 — AUTHORED COMPONENT-NAME DE-GLUE (default OFF) ─────────
    # A journey whose display IS a code identifier ('AdminTeamPage',
    # 'PixelShareForm') or a Title-Case phrase with a dev-grain component
    # tail ('Teams Page', 'Test Console Page') is re-derived from the words
    # that identifier itself declares. See ``uf_component_deglue`` for the
    # doctrine line: NS-D protects the author's PRODUCT vocabulary, and a
    # code identifier is not product vocabulary — it is implementation
    # naming with the legal status of a route segment, which this engine
    # already de-glues everywhere else.
    #
    # Placed HERE — the last rename lane before Law C — for the same reason
    # the B50 deparam and the R5-3 split-core lanes sit here: the row must
    # be GRADED ON THE NAME IT SHIPS. Nothing in this block writes
    # ``name_confidence``; Law C below re-derives it from the de-glued
    # name's own grounding (verb ∧ resource ⇒ high, resource only ⇒ honest
    # medium with a readable name), and the R5-5 sweep at the end of Law C
    # stops capping a row whose identifier shape is gone. Every mutation is
    # collision-safe through the SAME ``degrime_rename_plan`` the sibling
    # lanes use, and law-checked with ``display_law_violations``.
    #
    # NEVER invents a verb: a verb is written only when (a) the identifier
    # ITSELF leads with one the repo's own flow names declare an action
    # (the fixb131 №34 modifier guard — a token this repo writes as a
    # qualifier is a modifier, not an action, so 'Test Console Page' does
    # not become 'Test console'), or (b) the member composition already
    # grounds a READ family, in which case the Law-B word rule (with the
    # fixb130 view-lead pin) supplies 'View'/'Browse'. No grounding ⇒ the
    # phrase ships verbless, which is exactly what the pre-de-glue
    # identifier was (lead ``None``) — so the lane can never demote a row
    # by adding a claim its members do not perform.
    # ── CHANNEL GATE (operator ruling, 2026-08-09) ─────────────────────
    # The lane DEFERS to the post-adjudicator rescore seam whenever Stage
    # 6.7e is a LIVE writer on this scan, and keeps this pre-Law-C slot
    # when it is not.
    #
    # Det-authority doctrine means the deterministic layer is the VERDICT
    # authority, NOT that it must write first. The keyed umami pair
    # measured what writing first costs against an established cached LLM
    # stage: this lane repaired 17 rows, so the adjudicator's
    # low-confidence SELECTION fell 34 -> 17, its batching 3 -> 2, its
    # cache 3 hits -> 0, and it drew two fresh completions ($0 ->
    # $0.1006) whose verdicts welded member component names into displays
    # ('AdminWebsitesPage WebsitesPage'). It also cost UF-046 its home: on
    # the OFF arm the adjudicator's rename put the token 'website' into
    # the name and ``token_journey_rehome`` moved the row 'settings' ->
    # 'websites' on exactly that token; pre-empted, the token never
    # existed, the row stayed under a demoted frame, and
    # ``settings_frame_demote`` filed it as residual debt.
    #
    # Deferred, the order inverts and both writers win: the adjudicator
    # sees its usual selection (cache warm, $0, no draw variance), and the
    # rescore seam — THIS SAME BODY with ``primary_pass=False`` — then
    # de-glues whatever glue survived, including the adjudicator's own
    # output, working on the RICHER name ('Website Settings Page' ->
    # 'Browse website settings' KEEPS the 'website' token, so the rehome
    # still fires). A keyless board has no live adjudicator and no rescore
    # seam behind it (6.7e hard-no-ops before it), so it keeps the full
    # de-glue right here — byte-identical to the pre-ruling behaviour.
    _dg_defer = False
    if uf_component_name_deglue_enabled() and primary_pass:
        from wystan.pipeline_v2.stage_6_7e_adjudicator import (
            adjudicator_6_7e_will_run,
        )
        _dg_defer = adjudicator_6_7e_will_run()
        if _dg_defer:
            tele["uf_component_deglue_deferred"] = 1
    if uf_component_name_deglue_enabled() and not _dg_defer:
        from wystan.pipeline_v2.uf_component_deglue import (
            deglue_display_words,
            deglue_telemetry_keys,
            devgrain_suffix_shape,
            glued_identifier_shape,
            identifier_phrase_shape,
            nav_phrase_protected,
        )
        from wystan.pipeline_v2.uf_synth_fold import (
            VerbArmGuard,
            build_verb_arm_guard,
        )

        for _dg_k, _dg_v in deglue_telemetry_keys().items():
            tele.setdefault(_dg_k, _dg_v)
        _dg_brands = _brand_cased_idents(vocab)
        _dg_nav_sets: Mapping[str, list[str]] = nav_label_sets or {}
        _dg_nav_one = nav_labels or {}
        # The repo's OWN action/modifier census — the fixb131 Seg A guard,
        # built ONCE over the DISTINCT flows (``flow_by_id`` is keyed by
        # uuid AND name; double-counting would halve its floor).
        _dg_seen: set[int] = set()
        _dg_flows: list[Any] = []
        for _dg_fl in (flow_by_id or {}).values():
            if id(_dg_fl) in _dg_seen:
                continue
            _dg_seen.add(id(_dg_fl))
            _dg_flows.append(_dg_fl)
        _dg_guard: VerbArmGuard = build_verb_arm_guard(_dg_flows)
        _dg_mf, _dg_pages = route_verb_indexes(routes_index)

        def _dg_sing(t: str) -> str:
            return t[:-1] if (t.endswith("s") and len(t) > 3) else t

        def _dg_res_tokens(uf: Any) -> set[str]:
            out: set[str] = set()
            for src in (str(getattr(uf, "resource", "") or ""), _res(uf)):
                for tok in re.split(r"[^a-z0-9]+", (src or "").lower()):
                    if tok:
                        out.add(tok)
                        out.add(_dg_sing(tok))
            return out

        def _dg_attested(uf: Any) -> set[str]:
            """Words the row's OWN evidence attests: its resource phrase,
            its member flow names, and its member PATH segments read with
            the de-glue tokenizer (a ``.../compare/page.tsx`` segment
            attests 'compare'; a ``.../ResourceOverviewPage`` segment
            attests 'resource', 'overview', 'page').

            This is the spec's "echoing its entry component / route"
            clause, and it is what keeps the lane from splitting a vendor
            name the casing vocabulary does not carry: 'DigitalOcean' with
            no 'digital'/'ocean' anywhere in its own evidence is left
            alone (the fixb130 blast-census lesson — a blind run-level
            de-glue damaged exactly that class)."""
            from wystan.pipeline_v2.uf_name_deglue import (
                deglue_words as _dgw,
            )
            out: set[str] = set()

            def _add(text: str) -> None:
                for tok in re.split(r"[^a-z0-9]+", (text or "").lower()):
                    if tok:
                        out.add(tok)
                        out.add(_dg_sing(tok))

            _add(str(getattr(uf, "resource", "") or ""))
            _add(_res(uf))
            for _nm in _members(uf):
                _add(_nm)
            for _mid in (getattr(uf, "member_flow_ids", None) or ()):
                _fl = (flow_by_id or {}).get(str(_mid))
                if _fl is None:
                    continue
                _srcs = [str(p) for p in (getattr(_fl, "paths", None) or ())]
                _ep = getattr(_fl, "entry_point_file", None)
                if _ep:
                    _srcs.append(str(_ep))
                for _src in _srcs:
                    for _seg in re.split(r"[/\\]", _src):
                        _seg = _seg.split(".", 1)[0]
                        for _w in _dgw(_seg):
                            out.add(_w)
                            out.add(_dg_sing(_w))
            return out

        def _dg_nav_for(uf: Any) -> list[str]:
            pfid = str(getattr(uf, "product_feature_id", None) or "")
            labels = [str(x) for x in (_dg_nav_sets.get(pfid, ()) or ())]
            one = _dg_nav_one.get(pfid)
            if one:
                labels.append(str(one))
            return labels

        # ── TRANSACTION (keyed-pair ruling, 2026-08-09) ─────────────────
        # The lane opens by snapshotting the four fields a journey row may
        # NOT lose to a naming pass, and closes by restoring every row it
        # did not commit. Evaluation below is read-only, so the restore is
        # belt AND braces — but "the refusal path is a byte no-op" is a
        # promise this pack now keeps BY CONSTRUCTION rather than by
        # inspection, which is what the keyed convoy asked for. The
        # ``product_feature_id`` slot is restored for EVERY row, committed
        # or not: a naming module never writes identity or membership, and
        # after this block that is enforced, not merely intended.
        _dg_snap: dict[str, tuple[Any, Any, Any, Any]] = {
            str(getattr(u, "id", "") or ""): (
                getattr(u, "name", None),
                getattr(u, "name_confidence", None),
                getattr(u, "name_evidence", None),
                getattr(u, "product_feature_id", None),
            )
            for u in ordered
        }
        _dg_props: dict[str, str] = {}
        _dg_shape: dict[str, str] = {}
        for uf in ordered:
            cur = str(getattr(uf, "name", "") or "")
            if not cur:
                continue
            _dg_res = _dg_res_tokens(uf)
            _dg_lead_fam = _name_lead_family(cur, idx)
            _dg_glued = glued_identifier_shape(cur, brands=_dg_brands)
            # Rung C — an ALL-identifier phrase. Every whitespace token is
            # itself rung-A glue, so the display is two or more component
            # names welded together. See ``identifier_phrase_shape`` for
            # the measured producer (the Stage 6.7e LLM adjudicator's fresh
            # draws on the keyed ON arm) and why chasing it is in-class.
            _dg_phrase = (not _dg_glued) and identifier_phrase_shape(
                cur, brands=_dg_brands)
            _dg_devgrain = (not _dg_glued and not _dg_phrase
                            and devgrain_suffix_shape(
                                cur, lead_is_verb=_dg_lead_fam is not None,
                                resource_tokens=_dg_res,
                                pf_display=_pfd(uf)))
            if not (_dg_glued or _dg_phrase or _dg_devgrain):
                continue
            # NS-guard — authored nav/product phrasing is untouchable
            # whatever its shape (the identifier-shape test runs first, so
            # this only ever fires where the two genuinely collide).
            if nav_phrase_protected(cur, _dg_nav_for(uf)):
                tele["uf_component_deglue_nav_protected"] += 1
                continue
            _dg_words = deglue_display_words(
                cur, camel_split=_dg_glued or _dg_phrase,
                per_token=_dg_phrase)
            if not _dg_words:
                continue
            # WORD CORROBORATION — at least one recovered word must be
            # attested by the row's own evidence. Nothing is invented, and
            # a boundary the repo never writes anywhere else is not a
            # boundary this lane may act on.
            if not (set(_dg_words) & _dg_attested(uf)):
                tele["uf_component_deglue_unattested"] += 1
                continue
            # Verb rung (a) — the identifier's OWN declared action, gated by
            # the fixb131 №34 modifier guard AND by member grounding.
            _dg_comp = member_verb_composition(
                uf, flow_by_id or {}, _dg_mf, _dg_pages)
            _dg_mfams = _mfams(_members(uf))
            _dg_ground = _dg_comp | _dg_mfams
            _dg_verb: str | None = None
            _dg_obj = list(_dg_words)
            _dg_own_fam = idx["verb2fam"].get(_dg_words[0])
            if _dg_own_fam == "read":
                _dg_own_fam = "browse"
            if (len(_dg_words) >= 2 and _dg_own_fam is not None
                    and _dg_own_fam in _dg_ground
                    and _dg_guard.is_repo_action(_dg_sing(_dg_words[0]))):
                _dg_verb, _dg_obj = _dg_words[0], _dg_words[1:]
                tele["uf_component_deglue_verb_authored"] += 1
            # Verb rung (b) — a member-grounded READ verb, chosen by the
            # Law-B word rule + the fixb130 view-lead pin. READ ONLY: this
            # lane may never mint a write claim (Law B itself only ever
            # NARROWS to a read), and it fires only when the object phrase
            # does not already lead with an action of its own.
            _dg_read = _dg_ground & _READ_FAMILIES
            if (_dg_verb is None and _dg_obj
                    and idx["verb2fam"].get(_dg_obj[0]) is None
                    and _dg_read):
                _dg_leads = {_lead_token(n) for n in _members(uf)}
                # 'View' when the members say view (Law B's own rule + the
                # fixb130 pin) — or when 'view' is the ONLY read family the
                # evidence carries, because writing the other word would
                # hand Law C a verb its own rungs cannot ground and the
                # lane would DEMOTE the row it came to repair.
                _dg_verb = ("view" if ("view" in _dg_mfams
                                       or _dg_read == {"view"}
                                       or (uf_view_lead_pin_enabled()
                                           and _dg_leads == {"view"}))
                            else "browse")
                tele["uf_component_deglue_verb_member"] += 1
            if _dg_verb is None:
                tele["uf_component_deglue_verbless"] += 1
            # NB: NOT ``_dg_phrase`` — that name holds the rung-C shape
            # verdict for this row, and reusing it here silently retagged
            # every committed row as a phrase row in the telemetry.
            _dg_text = " ".join(
                ([_dg_verb] if _dg_verb else []) + _dg_obj).strip()
            if not _dg_text:
                continue
            _dg_cand = polish_display_casing(
                _dg_text[:1].upper() + _dg_text[1:], vocab)
            # ACRONYM CASING (warden №41 smell 3, operator ruling): a
            # universal initialism the de-glue recovered renders UPPERCASE
            # — 'Browse utm' -> 'Browse UTM'. The mechanism is fixb133's
            # OWN shipped one (``pf_display_doctrine.uppercase_acronyms``
            # over ``data/display-lexicon.yaml``): word-wise, exact token
            # match, never a substring. REUSED, never re-implemented — a
            # second acronym list is precisely the dictionary this codebase
            # forbids. Only the LIST crosses over, not a PF convention: the
            # lexicon's ``expansions`` (which would make 'utm' into "UTM
            # Campaigns") is a PF-NAME law and is deliberately not
            # consulted on a journey display. Rides this lane's flag by
            # construction — it is inside the block.
            _dg_cand = _uppercase_lexicon_acronyms(_dg_cand)
            if (not _dg_cand
                    or _dg_cand.strip().lower() == cur.strip().lower()):
                continue
            # Never hand back a name that re-enters this lane's own shape.
            if (glued_identifier_shape(_dg_cand, brands=_dg_brands)
                    or identifier_phrase_shape(_dg_cand, brands=_dg_brands)):
                tele["uf_component_deglue_law_refused"] += 1
                continue
            if display_law_violations(
                    _dg_cand, vocab, pf_display=_pfd(uf) or None,
                    member_tokens=_uf_member_evidence(uf)):
                tele["uf_component_deglue_law_refused"] += 1
                continue
            # ── BARE PF-ECHO REFUSAL (operator ruling, 2026-08-10) ──────
            # A VERBLESS candidate whose whole token set is already inside
            # its home PF's display states no capability — it just says the
            # PF again, one grammatical notch worse. umami UF-010
            # 'BoardViewPage' de-glues (board | view | page -> the whole
            # dev-grain tail goes) to a bare 'Board' under PF 'Boards', and
            # the ruling is that the honest identifier at ``medium`` beats
            # a bare noun: B46 bare-noun adjacency, and doctrine law 1 — a
            # name must state a CAPABILITY. Refused, so the row stays
            # byte-identical to the flag-off arm.
            #
            # VERBLESS is the whole discriminator: 'Browse sessions' is
            # also a token-subset of PF 'Sessions', and it SHIPS — the verb
            # is the capability. Only the shape that says nothing is
            # refused.
            #
            # Rides the fixb136 flag, not fixb132's: this is new behaviour
            # and new behaviour lands behind an OFF flag. It is also only
            # REACHABLE there — with fixb136 off, the fold-neutrality arms
            # already refuse this row for their own (conservation) reason,
            # so the shipped default emission does not move.
            # (module-level reader — the name is imported further down in
            # this function, which would otherwise make it a local here)
            if _dg_verb is None and _fold_canonical_verb_priority_on():
                _dg_pf_toks = {
                    _dg_sing(t) for t in
                    re.split(r"[^a-z0-9]+", (_pfd(uf) or "").lower()) if t
                }
                _dg_cand_toks = {
                    _dg_sing(t) for t in
                    re.split(r"[^a-z0-9]+", _dg_cand.lower()) if t
                }
                if (_dg_pf_toks and _dg_cand_toks
                        and _dg_cand_toks <= _dg_pf_toks):
                    tele["uf_component_deglue_bare_echo_refused"] = (
                        tele.get(
                            "uf_component_deglue_bare_echo_refused", 0) + 1)
                    continue
            _dg_props[str(getattr(uf, "id", "") or "")] = _dg_cand
            _dg_shape[str(getattr(uf, "id", "") or "")] = (
                "glued" if _dg_glued
                else "phrase" if _dg_phrase else "devgrain")
        # ── FOLD-NEUTRALITY (the single-writer law, measured) ───────────
        # A naming module may never write identity or membership. This
        # lane's FIRST replay pair proved it can do so INDIRECTLY: an
        # identifier hides the row's head noun, so de-gluing it reveals a
        # noun family, and the LATER ``uf_synth_fold`` pass (L-C1 PF-echo /
        # L-C3 same-noun-head, ON by default since KEY_SCHEMA 30) then
        # merges rows on the strength of a name THIS PASS just wrote. On
        # the umami capture it cost five whole journeys — and the fold's
        # richest-name canonical made the de-glued READ row eat the write
        # journey beside it ('Create & edit websites' -> 'Browse admin
        # websites'). Members were unioned, so nothing leaked; but a whole
        # journey disappearing is a conservation stop, and re-cutting a
        # duplicate family is a MEMBERSHIP question this module may not
        # answer (the verbatim B16-P1b ruling on post-strip collisions).
        #
        # So a candidate that would newly make its row a fold participant
        # is REFUSED — the row keeps its identifier and its honest medium,
        # and the duplicate it revealed stays visible as two rows instead
        # of being silently merged. Three arms, each reading
        # ``uf_synth_fold``'s OWN predicates (one grammar, never a second
        # copy of the fold's law), each comparing the CANDIDATE against the
        # CURRENT name so a family that already exists in the OFF hand is
        # not blamed on this lane:
        #   1. the candidate becomes an L-C1 PF echo (and the PF is not
        #      down to its last journey, which L-C1 itself protects);
        #   2. the candidate joins an L-C3 same-noun-head family on its own
        #      PF;
        #   3. the candidate becomes a SUPERSET of a same-PF echo row — the
        #      L-C1 family/canonical attraction that folded 'Manage boards'
        #      into a freshly de-glued sibling.
        if _dg_props:
            from wystan.pipeline_v2.uf_synth_fold import (
                _undressed_pf_display,
                fold_canonical_verb_priority_enabled,
                is_pf_echo,
                meaning_tokens,
                noun_head,
            )

            _dg_verbs = _verb_class_tokens(vocab)
            _dg_elig = [
                u for u in ordered
                if not getattr(u, "is_coverage_marker", False)
                and not getattr(u, "synthesized", False)
            ]
            # ── fixb136 LINK — the EXACT oracle replaces the three
            # structural arms once canonical verb-priority is armed.
            #
            # The arms are a conservative APPROXIMATION of "would this
            # rename create a fold": they read shape (echo / same head /
            # superset-of-an-echo) but not L-C3's span gate, not L-C1's
            # family+richness conditions, and not the new canonical order.
            # Measured on umami they refuse NINE rows while the fold would
            # actually fire on only some of them. With verb-priority armed
            # the fold's own answer CHANGES, so approximating it a second
            # time here would be guessing about a moving target — the lane
            # asks the planner instead, over the very names it proposes,
            # and refuses only the proposals that add a fold the OFF hand
            # does not have. Same module edge the arms already use (lazy),
            # no new coupling.
            #
            # Conservative by construction in one respect, named honestly:
            # the oracle plans WITHOUT ``fold_exempt_ids`` (the lattice-born
            # set that ``synth_quality`` passes when det-aggregation is on),
            # so it can predict a fold the live pass would exempt — that
            # direction only ever costs a rename, never a journey.
            if fold_canonical_verb_priority_enabled():
                _dg_oracle_refused = _dg_fold_oracle_refuse(
                    _dg_props, ordered, _dg_elig, list(pf_by_slug.values()),
                    _dg_flows, _dg_verbs, tele)
                for _uid in sorted(_dg_oracle_refused):
                    _dg_props.pop(_uid, None)
                    tele["uf_component_deglue_fold_refused"] += 1
                # the three structural arms are the OFF-hand path; the
                # oracle has already answered the same question exactly.
                _dg_elig = []
            _dg_eff = {
                str(getattr(u, "id", "") or ""): _dg_props.get(
                    str(getattr(u, "id", "") or ""),
                    str(getattr(u, "name", "") or ""))
                for u in _dg_elig
            }
            _dg_by_pf: dict[str, list[Any]] = defaultdict(list)
            for u in _dg_elig:
                _pfk = str(getattr(u, "product_feature_id", "") or "")
                if _pfk:
                    _dg_by_pf[_pfk].append(u)

            def _dg_pf_display(uf: Any) -> str:
                key = str(getattr(uf, "product_feature_id", "") or "")
                pf = pf_by_slug.get(key)
                return _undressed_pf_display(pf, key) if pf is not None else ""

            for _uid in sorted(list(_dg_props)):
                uf = next((u for u in ordered
                           if str(getattr(u, "id", "") or "") == _uid), None)
                if uf is None or uf not in _dg_elig:
                    continue
                _dg_c = _dg_props[_uid]
                _dg_u = str(getattr(uf, "name", "") or "")
                _dg_pfk = str(getattr(uf, "product_feature_id", "") or "")
                _dg_sibs = [s for s in _dg_by_pf.get(_dg_pfk, ())
                         if str(getattr(s, "id", "") or "") != _uid]
                if not _dg_sibs:
                    continue        # a PF's only journey folds nowhere
                _dg_pfd_u = _dg_pf_display(uf)
                _dg_refuse = False
                # arm 1 — becomes a PF echo
                if (is_pf_echo(_dg_c, _dg_pfd_u, _dg_verbs)
                        and not is_pf_echo(_dg_u, _dg_pfd_u, _dg_verbs)):
                    _dg_refuse = True
                # arm 2 — joins a same-noun-head family
                _dg_h_c = noun_head(_dg_c, _dg_verbs)
                _dg_h_u = noun_head(_dg_u, _dg_verbs)
                if not _dg_refuse and _dg_h_c and _dg_h_c != _dg_h_u:
                    for s in _dg_sibs:
                        _dg_sid = str(getattr(s, "id", "") or "")
                        if noun_head(_dg_eff.get(_dg_sid, ""), _dg_verbs) == _dg_h_c:
                            _dg_refuse = True
                            break
                # arm 3 — becomes a superset of a same-PF echo row
                if not _dg_refuse:
                    _dg_mt_c = meaning_tokens(_dg_c, _dg_verbs)
                    _dg_mt_u = meaning_tokens(_dg_u, _dg_verbs)
                    for s in _dg_sibs:
                        _dg_sid = str(getattr(s, "id", "") or "")
                        _dg_sname = _dg_eff.get(_dg_sid, "")
                        if not is_pf_echo(_dg_sname, _dg_pf_display(s), _dg_verbs):
                            continue
                        _dg_mt_s = meaning_tokens(_dg_sname, _dg_verbs)
                        if _dg_mt_s and _dg_mt_s <= _dg_mt_c and not _dg_mt_s <= _dg_mt_u:
                            _dg_refuse = True
                            break
                if _dg_refuse:
                    _dg_props.pop(_uid, None)
                    _dg_eff[_uid] = _dg_u
                    tele["uf_component_deglue_fold_refused"] += 1
        if _dg_props:
            _dg_cur = {
                str(getattr(u, "id", "") or ""): str(getattr(u, "name", "") or "")
                for u in ordered
            }
            _dg_by_id = {str(getattr(u, "id", "") or ""): u for u in ordered}
            # The B31 twin law: two rows never share a display, so a
            # candidate another row already carries is dropped and the row
            # keeps its identifier. RATIFIED AS RESIDUE (operator, fixb136
            # round): umami UF-053 'UsersPage' is the last un-de-glued row
            # on that board because its candidate 'View users' is already
            # the lattice row UF-L-c175eedaf9's display. That is correct
            # machinery doing its job — the two rows are a MEMBERSHIP
            # question, not a naming one — so no lattice rename is made to
            # free the string.
            _dg_allowed = degrime_rename_plan(_dg_cur, _dg_props)
            for _uid in sorted(_dg_allowed):
                _dg_by_id[_uid].name = _dg_props[_uid]
                tele["uf_component_deglued"] += 1
                tele["uf_component_deglue_" + _dg_shape.get(_uid, "glued")] += 1
            if fold_canonical_verb_priority_enabled():
                # fixb136 LINK — a row THIS PASS just renamed is not a fold
                # SOURCE. Measured: verb-priority alone released only 3 of
                # the 9 rows, because L-C3 merges every overlapping
                # same-head sibling and L-C1 merges an echo under a richer
                # canonical whoever that is — priority changes WHO
                # survives, never WHETHER the merge happens. The de-glue
                # did not discover a duplicate; it made one legible, and a
                # journey may not die of a rename. Rides the SAME flag and
                # the SAME plumbing the lattice rows already use
                # (``fold_exempt_ids``); sources only, so a de-glued row
                # can still WIN a fold and inherit members.
                #
                # LOAD-BEARING transport is the module-scoped registry that
                # this lane and the fold BOTH import. The telemetry key
                # below is observability only: on the keyed channel it
                # crosses ``_rescore_tele_view``, which copies scalars and
                # drops lists in silence — that is exactly how battery 15
                # lost four journeys while every sibling counter arrived.
                from wystan.pipeline_v2.uf_component_deglue import (
                    note_renamed_in_scan,
                )
                note_renamed_in_scan(_dg_allowed)
                tele["uf_component_deglue_renamed_ids"] = sorted(
                    set(tele.get("uf_component_deglue_renamed_ids") or [])
                    | set(_dg_allowed))
            tele["uf_component_deglue_collision_skipped"] += (
                len(_dg_props) - len(_dg_allowed))
        else:
            _dg_allowed = set()
        # ── TRANSACTION CLOSE — restore every UNCOMMITTED row ───────────
        # A row this lane did not commit leaves it byte-identical to the
        # flag-off arm: same name, same confidence, same evidence LIST
        # OBJECT (a restored ``None`` stays ``None``, never becomes an
        # empty list — that alone would be an emission diff).
        #
        # The HOME is CHECKED, never written. The first draft of this close
        # RESTORED ``product_feature_id`` as well, and the suite's own grep
        # guard (``test_grep_guard_naming_module_never_writes_identity``)
        # failed it on the spot — correctly: a naming module that repairs
        # identity is still a module that writes identity, and the guard
        # reads the SOURCE, not the intent. So the promise is kept the only
        # legal way — the lane never assigns the field at all, and a drift
        # (which could only mean a future edit inside this block started
        # writing identity) is COUNTED, loudly, never silently healed.
        for uf in ordered:
            _uid = str(getattr(uf, "id", "") or "")
            _snap = _dg_snap.get(_uid)
            if _snap is None:
                continue
            _s_name, _s_conf, _s_ev, _s_home = _snap
            if getattr(uf, "product_feature_id", None) != _s_home:
                tele["uf_component_deglue_home_drift"] = (
                    tele.get("uf_component_deglue_home_drift", 0) + 1)
            if _uid in _dg_allowed:
                continue
            if getattr(uf, "name", None) != _s_name:
                uf.name = _s_name
            if getattr(uf, "name_confidence", None) != _s_conf:
                uf.name_confidence = _s_conf
            if getattr(uf, "name_evidence", None) is not _s_ev:
                uf.name_evidence = _s_ev

    rungs_on = name_evidence_rungs_enabled()
    _nav = nav_labels or {}
    _origin = flow_origin_by_id or {}
    tele["confidence_before"] = _conf_hist(user_flows)

    def _sing(t: str) -> str:
        return t[:-1] if (t.endswith("s") and len(t) > 3) else t

    def _toks(text: str) -> set[str]:
        return {_sing(t) for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if t}

    # ── B50 Seg3 — earned resource rung (WYSTAN_UF_RESOURCE_RUNG) ──
    # A low ``missing:resource`` UF (verb grounded, resource not) earns
    # resource-grounding ONLY from a REAL evidence rung. Bar UNCHANGED — these
    # are extra OR-sources to ``res_grounded``, never a lowered threshold. Flag
    # OFF ⇒ every hit below is False ⇒ res_grounded / confidence / name_evidence
    # byte-identical.
    rung_on = uf_resource_rung_enabled()
    _flow_by_id = flow_by_id or {}
    _extract_domain_noun = None
    if rung_on:
        try:
            from wystan.pipeline_v2.domain_noun import extract_domain_noun
            _extract_domain_noun = extract_domain_noun
        except Exception:  # noqa: BLE001 — optional structural resolver
            _extract_domain_noun = None
        tele["resource_rung_fired"] = {"member-noun": 0, "route": 0, "test": 0}

    def _member_paths(u: Any) -> list[str]:
        """Union of the member flows' entry_point_file + paths."""
        out: set[str] = set()
        for m in (getattr(u, "member_flow_ids", None) or []):
            fl = _flow_by_id.get(str(m))
            if fl is None:
                continue
            for p in (getattr(fl, "paths", None) or []):
                if p:
                    out.add(str(p))
            ep = getattr(fl, "entry_point_file", None)
            if ep:
                out.add(str(ep))
        return sorted(out)

    def _member_test_nouns(u: Any) -> set[str]:
        """Singular-folded nouns from a member flow's MAPPED test files (B36 —
        flow_test_mapper only maps a test whose member-overlap already holds)."""
        nouns: set[str] = set()
        for m in (getattr(u, "member_flow_ids", None) or []):
            fl = _flow_by_id.get(str(m))
            if fl is None:
                continue
            for tf in (getattr(fl, "test_files", None) or []):
                base = str(tf).rsplit("/", 1)[-1]
                stem = re.split(
                    r"\.(?:test|spec|e2e|stories|cy)\b", base, maxsplit=1,
                    flags=re.IGNORECASE)[0]
                if "." in stem:
                    stem = stem.rsplit(".", 1)[0]
                nouns |= _toks(re.sub(r"[-_.]+", " ", stem))
        return nouns

    # ── B57 Seg1 — rung-source expansion (WYSTAN_UF_RUNG_SOURCES_V2) ──
    # Four extra OR-sources for the SAME Law C bar (B50 Seg3 precedent):
    # nav-cluster / i18n-key ground the resource, route-method grounds the
    # verb, test-assert grounds either. Flag OFF ⇒ every hit below is
    # False and no telemetry key is added ⇒ confidence / name_evidence /
    # serialized output byte-identical.
    v2_on = uf_rung_sources_v2_enabled()
    _nav_sets: Mapping[str, list[str]] = nav_label_sets or {}
    # B57 Seg2 — adjudicated rung evidence (Stage 6.7e): per-UF VERIFIED
    # citation rungs act as extra OR-sources at the SAME bar, per channel
    # (``{uf_id: {"resource": [rungs], "verb": [rungs]}}`` — the verb
    # channel is the b57-seg2-iter ruling). Confidence is only ever
    # written HERE — the adjudicator hands Law C its verified evidence
    # and Law C judges. Absent map ⇒ byte-identical.
    _adjudicated: Mapping[str, Mapping[str, Iterable[str]]] = (
        adjudicated_sources or {})
    _v2_repo: Any = None
    _v2_read_cache: dict[str, str] = {}
    _method_fams_by_file: dict[str, set[str]] = {}
    _page_files: set[str] = set()
    if v2_on:
        tele["rung_sources_v2_fired"] = {
            "nav-cluster": 0, "i18n-key": 0, "route-verb": 0,
            "test-assert": 0, "verb-composition": 0,
        }
        _method_fams_by_file, _page_files = route_verb_indexes(routes_index)
        if repo_root is not None:
            try:
                from pathlib import Path
                _v2_repo = Path(str(repo_root))
            except (TypeError, ValueError):  # pragma: no cover — defensive
                _v2_repo = None

    def _v2_read(rel: str) -> str:
        """Capped, cached member-file read (bounds-of-work only)."""
        if rel in _v2_read_cache:
            return _v2_read_cache[rel]
        text = ""
        if _v2_repo is not None:
            try:
                fp = _v2_repo / rel
                if (fp.is_file()
                        and fp.stat().st_size <= _RUNG_SOURCE_MAX_FILE_BYTES):
                    text = fp.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                text = ""
        _v2_read_cache[rel] = text
        return text

    def _member_test_files(u: Any) -> list[str]:
        """MAPPED test files of the member flows (``flow.test_files`` —
        flow_test_mapper already guarantees member-overlap; the rung never
        reads an unmapped test file)."""
        files: set[str] = set()
        for m in (getattr(u, "member_flow_ids", None) or []):
            fl = _flow_by_id.get(str(m))
            if fl is None:
                continue
            files.update(str(tf) for tf in (getattr(fl, "test_files", None) or []) if tf)
        return sorted(files)

    def _is_verb_tok(t: str) -> bool:
        return t in idx["verb2fam"] or _sing(t) in idx["verb2fam"]

    def _grounds_resource(src_toks: set[str], res_toks: set[str],
                          name_toks: set[str]) -> bool:
        """Resource-grounding overlap for prose/identifier sources: a
        resource-phrase token always grounds; a NAME token grounds only
        when it is not an action verb (a verb echo — 'manages'/'delete_'
        — must never stand in for resource evidence; the verb channel
        judges verbs)."""
        if src_toks & res_toks:
            return True
        return bool({t for t in src_toks if not _is_verb_tok(t)} & name_toks)

    def _fold_read(fam: str | None) -> str | None:
        """browse/view collapse to 'read' for family agreement — the
        split is an id-marker display heuristic, not an evidence line."""
        return "read" if fam in ("browse", "view") else fam

    def _label_lead_family(label: str) -> str | None:
        """Leading-verb family of an assertion label, singular-folded so
        prose thirds ('creates …', 'renders …') resolve like base verbs."""
        toks_l = [t for t in re.split(r"[^a-z0-9]+", label.lower()) if t]
        if not toks_l:
            return None
        fam = (idx["verb2fam"].get(toks_l[0])
               or idx["verb2fam"].get(_sing(toks_l[0])))
        if fam == "read":
            return "view" if (idx["id_markers"] & set(toks_l)) else "browse"
        return fam

    # ── B78-it2 Goal 2b (rider on WYSTAN_FOLD_EVIDENCE_WEIGHT) ──
    # A SYNTHESIZED backstop row is a coverage instrument, not an observed
    # journey: its resource/verb rungs ground the TEMPLATE the backstop
    # itself composed (name == PF display == resource — the RefApp UF-005
    # 'API' exhibit rode that circle to ``high``). Armed, the promotion
    # chain below SKIPS synthesized rows: confidence caps at ``low`` and
    # ``name_evidence`` carries the honest ``synthesized`` stamp. Gated by
    # the Seg A flag WITH REASON — the uncovered-PF backstop row only
    # exists because the Seg A walk-evidence gate minted its PF. Lazy
    # import (house style — no module-level cross-import).
    # fixb145 — the cap now reads its OWN flag. Default preserves BOTH
    # historical states exactly: unset ``WYSTAN_SYNTH_CONF_CAP`` falls
    # back to ``fold_evidence_weight_enabled()``, so a board running today's
    # ``WYSTAN_FOLD_EVIDENCE_WEIGHT=0`` kill-switch keeps its uncapped
    # behavior and every other board keeps the cap. The new flag gets its own
    # kill-switch on top (``=0`` ⇒ no cap, walk-evidence gate untouched).
    from wystan.pipeline_v2.synth_conversion import (
        synth_conf_cap_enabled as _synth_cap_enabled,
        synth_conversion_enabled as _synth_conversion_enabled,
    )
    _synth_conf_cap = _synth_cap_enabled()
    # fixb128 (NS-2) — authored-CLI carve on the cap below. Lazy import
    # (house style — no module-level cross-import).
    from wystan.pipeline_v2.cli_command_journeys import (
        CLI_DECLARED_EVIDENCE as _CLI_DECLARED_EVIDENCE,
        is_cli_declared as _is_cli_declared,
    )

    # ── fixb145 lane 2 — guarded synth CONVERSION (default OFF) ─────────
    # MEASURED (cap OFF/ON `wystan replay` pairs, infisical + langfuse +
    # teable, 200 board-aligned rows, $0, same channel): 171 (85.5%) of the
    # capped rows earn ``high`` on their OWN Law-C evidence, with ZERO name
    # drift between arms and ZERO drift on the 282 non-synthesized rows —
    # i.e. the cap is a STAMP, not a naming correction. Armed, a synthesized
    # row is graded by the ordinary rubric instead of being hard-stamped,
    # and is marked for un-synthesizing when it earns ``high`` AND clears
    # both ratified guards. The apply lives in ``synth_conversion`` (§4.8:
    # this module never writes identity).
    #
    # GUARD 1 — NS-43a PF-echo refusal. The engine's OWN oracle
    # (``uf_synth_fold.is_pf_echo``, the same ruler the lc1 fold uses — one
    # ruler, never a second): a name whose noun-phrase equals its PF display
    # carries no own content token, and un-capping it would resurrect the
    # TRACKed NS-43a class at world scale (measured: 55 of the 171 lifts are
    # this shape — langfuse 24/48, teable 29/37).
    # GUARD 2 — per-PF quota, ratified as engine law: converted rows <=
    # ``max(1, real journeys the PF already holds)``. Scale-invariant (a
    # ratio against the PF's own journey population, no magic number) and
    # the exact form the ratified sizing was measured with. The ``max(1,·)``
    # floor is load-bearing: an uncovered PF holds ZERO real journeys by
    # construction — that is WHY the backstop fired — so a bare ``<= real``
    # would convert nothing on the very population this lane targets, while
    # ``max(1,·)`` admits its single highest-mass row and never a spray
    # (measured: it kills infisical's 36-row 'Browse & manage <vendor>'
    # spray on one PF down to that PF's quota).
    # Admission is ranked ONCE, before the grading loop, by
    # ``(-member_count, id)`` within each PF — so a row's admission depends
    # only on its own rank among its PF's synthesized rows, never on loop
    # order (order-independent + deterministic), and a high-ranked row that
    # then FAILS Law C simply spends its slot (conservative direction).
    # ── fixb145 Channel-A kill: defer to the POST-6.7e seam on keyed ────
    # MEASURED (battery 28): lane 2 writes ``name_confidence``, and the 6.7e
    # adjudicator — which runs AFTER Stage-07 naming (phase_finalize:3389 vs
    # :3620, one function) — SELECTS on ``name_confidence != high``
    # (stage_6_7e_adjudicator:514). Grading synth rows before it therefore
    # changed its selection, missed its cache and bought fresh paid draws
    # (infisical adj_calls 0->12, teable 0->4, monotone with 68/6 conversions)
    # whose renames/homes churned downstream. Identical disease to the fixb132
    # umami pair, and the SAME cure: the det layer is the VERDICT authority,
    # not necessarily the FIRST writer.
    #
    # Deferred, both writers win: the adjudicator sees its usual selection of
    # ORIGINAL lows (cache warm, $0, no draw variance), and this same body
    # re-enters from ``rescore_uf_confidence`` INSIDE 6.7e
    # (stage_6_7e_adjudicator:1403 — board-wide, post-verdict) with
    # ``post_adjudicator=True``, where the lane converts on the FINAL state.
    # That is also the more honest order: 6.7e's quality filter runs first, so
    # a row it demotes or renames is judged on the form it will ship.
    #
    # KEYLESS keeps the current seam byte-identically: ``will_run()`` is False
    # without a live client, so Channel A is structurally impossible there.
    # CONSERVATIVE EDGE: on a keyed board whose adjudicator produced NO
    # verdicts, 6.7e never calls the re-score seam, so the lane simply does
    # not convert on that board — no conversion beats a pre-adjudicator one.
    _sc_on = _synth_conversion_enabled()
    # NS-46a — rows holding a STANDING conversion verdict from the
    # post-adjudicator seam. Read regardless of ``_sc_on``/defer: the whole
    # point is that a LATER re-entry (producer hooks, lane disarmed) must not
    # re-stamp them. A promise must not cross a re-entry.
    _sc_verdicts: frozenset[str] = frozenset()
    if _sc_on:
        from wystan.pipeline_v2.synth_conversion import (
            conversion_verdict_ids as _sc_verdict_ids_fn,
        )
        _sc_verdicts = _sc_verdict_ids_fn()
    _sc_defer = False
    if _sc_on and not post_adjudicator:
        from wystan.pipeline_v2.stage_6_7e_adjudicator import (
            adjudicator_6_7e_will_run,
        )
        _sc_defer = adjudicator_6_7e_will_run()
    if _sc_defer:
        tele["synth_conversion_deferred"] = 1
        _sc_on = False
    _sc_admitted: set[str] = set()
    _sc_converted: set[str] = set()
    _sc_tele: dict[str, Any] = {
        "armed": _sc_on, "eligible": 0, "echo_refused": 0,
        "quota_refused": 0, "converted": 0,
    }
    _sc_verbs: frozenset[str] = frozenset()
    _sc_struct: frozenset[str] = frozenset()

    if _sc_on:
        from wystan.pipeline_v2.uf_synth_fold import (
            _undressed_pf_display as _sc_pf_disp_of,
            is_pf_echo as _sc_is_pf_echo,
        )

        _sc_verbs = _verb_class_tokens(vocab)
        _sc_struct = frozenset(
            str(t).strip().lower()
            for t in (vocab.get("structural_segments") or ())
            if str(t).strip()
        )
        _sc_real_by_pf: dict[str, int] = defaultdict(int)
        _sc_synth_by_pf: dict[str, list[Any]] = defaultdict(list)
        for _u in ordered:
            _pk = str(getattr(_u, "product_feature_id", "") or "")
            if getattr(_u, "synthesized", False):
                _sc_synth_by_pf[_pk].append(_u)
            else:
                _sc_real_by_pf[_pk] += 1

        def _sc_display(uf: Any) -> str:
            key = str(getattr(uf, "product_feature_id", "") or "")
            pf = pf_by_slug.get(key)
            return _sc_pf_disp_of(pf, key) if pf is not None else ""

        for _pk, _rows in sorted(_sc_synth_by_pf.items()):
            _quota = max(1, _sc_real_by_pf.get(_pk, 0))
            # Guard 1 FIRST — an echo row is never converted, so it must not
            # spend a quota slot (this is the exact order the ratified
            # sizing was measured with).
            _clean = [
                _u for _u in _rows
                if not _sc_is_pf_echo(str(getattr(_u, "name", "") or ""),
                                      _sc_display(_u), _sc_verbs)
            ]
            _sc_tele["echo_refused"] += len(_rows) - len(_clean)
            _ranked = sorted(
                _clean,
                key=lambda u: (-int(getattr(u, "member_count", 0) or 0),
                               str(getattr(u, "id", "") or "")),
            )
            _sc_tele["quota_refused"] += max(0, len(_ranked) - _quota)
            for _u in _ranked[:_quota]:
                _sc_admitted.add(str(getattr(_u, "id", "") or ""))
        _sc_tele["eligible"] = len(_sc_admitted)
        # The quota verdict is auditable per row (forensics: which row won a
        # PF's slot), bounded like every other telemetry sample.
        _sc_tele["admitted_ids"] = sorted(_sc_admitted)[:60]

    def _sc_guard3_ok(uf: Any) -> bool:
        """GUARD 3 (ruling 4) — the display-doctrine floor, evaluated at the
        CAP DECISION point, i.e. on the name the board will actually SHIP:
        the R5 rename lanes can rewrite a synth row's display mid-loop, so
        judging it at admission time would judge a name that never ships.

        The predicate itself lives in ``synth_conversion.doctrine_refusal``
        (one owner for the conversion policy, directly testable against the
        measured exhibits); this seam only supplies the vocabulary it has
        already loaded and books the telemetry."""
        from wystan.pipeline_v2.synth_conversion import doctrine_refusal
        reason = doctrine_refusal(
            str(getattr(uf, "name", "") or ""),
            getattr(uf, "name_evidence", None),
            _sc_verbs, _sc_struct)
        if reason is None:
            return True
        _sc_tele["doctrine_refused"] = _sc_tele.get("doctrine_refused", 0) + 1
        _reasons = _sc_tele.setdefault("doctrine_reasons", {})
        _reasons[reason] = _reasons.get(reason, 0) + 1
        return False

    # ── W1/C-A — verb:member-lead-echo (WYSTAN_UF_MEMBER_LEAD_ECHO) ──
    # One more OR-source at the UNCHANGED Law C bar: the UF display's LEAD
    # token equals the LEAD token of a member flow's name, which the
    # flow-naming contract defines as that flow's declared action. Reads no
    # vocabulary — ``journey-action-families.yaml`` documents its 99 verbs
    # as CORROBORATION of exactly this token, and Law C's base rubric
    # mis-reads them as an existence gate (``mfams`` empty ⇒ ``base_verb``
    # blind on 87.9% of the medium ∧ missing:verb population). Index-only,
    # no IO, $0. Flag OFF ⇒ hit is always False and no telemetry key is
    # added ⇒ confidence / name_evidence / serialized output byte-identical.
    _echo_on = uf_member_lead_echo_enabled()
    if _echo_on:
        tele["member_lead_echo_fired"] = 0

    # ── fixb142 Part 3 — verb:flow-verb-class (WYSTAN_UF_FLOW_VERB_CLASS)
    # The SECOND bucketing of the member lead token Law C already trusts
    # (see ``flow_verb_class_agreement``). Index-only, no IO, $0. OFF ⇒ no
    # telemetry key and the hit is always False ⇒ byte-identical.
    _fvc_on = uf_flow_verb_class_enabled()
    if _fvc_on:
        tele["flow_verb_class_fired"] = 0

    # ── C-B — verb:repo-umbrella-lead (WYSTAN_UF_UMBRELLA_FLOOR) ────
    # The repo-mined LEAD lexicon, built ONCE per pass over the DISTINCT
    # flows (``flow_by_id`` is keyed by uuid AND name — its values must be
    # de-duplicated by object identity or every flow counts twice and the
    # floor halves). OFF ⇒ empty lexicon, no telemetry key, hit always
    # False ⇒ byte-identical.
    # fixb130 — the SAME lexicon is the echo rung's modifier-lead guard
    # (see ``member_lead_echo_token``), so it is built whenever EITHER rung
    # is armed. With both off it stays empty and neither rung runs.
    _umb_on = uf_umbrella_floor_enabled()
    _umb_lex: Mapping[str, int] = {}
    _umb_flow_count = 0
    if _umb_on or _echo_on:
        _seen_flows: set[int] = set()
        _distinct_names: list[str] = []
        for _fl in (flow_by_id or {}).values():
            if id(_fl) in _seen_flows:
                continue
            _seen_flows.add(id(_fl))
            _distinct_names.append(str(getattr(_fl, "name", "") or ""))
        _umb_flow_count = len(_distinct_names)
        _umb_lex = repo_lead_lexicon(_distinct_names, _sing)
    if _umb_on:
        tele["umbrella_lead_fired"] = 0
    if _echo_on:
        tele["member_lead_echo_modifier_refused"] = 0

    # fixb130 / warden verdict #35 item (6) — R0 SCOPING of the fixb129
    # narrowed-normal rubric. The rubric's whole argument is about the
    # PRIMARY naming pass: Law B has just rewritten the name to a
    # member-grounded '<Browse|View> <resource>', so stamping
    # ``missing:verb`` on it there is a lie about a verb that IS present.
    # In a RE-SCORE hook the argument does not hold. The hook exists to
    # report what a producer's membership/evidence change did to a row, and
    # the narrowing IS that report — grading the narrowed row through the
    # ordinary rubric silences it (the warden measured ``rows_down`` 1 -> 0
    # with the flag ON, i.e. the evidence-drift demote channel went mute).
    # So outside the primary pass the narrowed row keeps the pre-fixb129
    # hard stamp: it can fall, it can never climb past the confidence it
    # carried into the hook.
    #
    # fixb142 Part 2 — that last sentence is the CONTRACT, and the hard
    # stamp is not it. "Never climb past the confidence it carried in" is a
    # CEILING; ``low`` + ``['missing:verb']`` is a FLOOR, and on a narrowed
    # row it is also a false statement (Law B took the surviving lead FROM
    # ``mfams``, so the verb is witnessed by construction). Seven rows on
    # the KS75 world sat frozen on that stamp — unchanged since KS66 even
    # though the fixb129 flag is default-ON — because every post-mint
    # rescore seam re-applies it. With the Part-2 flag armed the row is
    # scored by the ordinary rubric in EVERY pass and the ceiling is
    # enforced explicitly, so the demote channel fixb130 protected stays
    # open (a row may still fall) while the lie is gone. Flag OFF ⇒
    # ``_rubric_on`` collapses to the fixb130 expression and ``_conf_cap``
    # is never consulted ⇒ byte-identical.
    _rescore_rubric_on = narrowed_rubric_rescore_enabled()
    _rubric_on = narrowed_normal_rubric_enabled() and (
        primary_pass or _rescore_rubric_on)
    #: uid → confidence the row CARRIED INTO this pass (the no-climb
    #: ceiling). Only populated outside the primary pass, and only for
    #: narrowed rows — the rows whose ceiling the fixb130 contract names.
    _conf_cap: dict[str, str] = {}
    if _rescore_rubric_on and not primary_pass:
        for uf in ordered:
            _uid = str(getattr(uf, "id", "") or "")
            if _uid in narrowed:
                _conf_cap[_uid] = str(
                    getattr(uf, "name_confidence", "") or "high")

    for uf in ordered:
        uid = str(getattr(uf, "id", "") or "")
        names = _members(uf)
        if not names:
            uf.name_confidence = "low"
            # A member-less row can never uplift (the rubric floor) — its low
            # is honest: there is no member evidence to ground a name.
            if rungs_on:
                uf.name_evidence = ["missing:members"]
            continue
        if uid in narrowed and not _rubric_on:
            uf.name_confidence = "low"
            # Law B narrowed an unsupported write claim → the claimed verb had
            # no member evidence; low is honest.
            if rungs_on:
                uf.name_evidence = ["missing:verb"]
            continue
        # fixb129 addendum (C2-verb probe): the hard-stamp above punished the
        # row for the PIPELINE'S OWN correction. Law B does not merely delete a
        # false claim — it REWRITES the name to "<Browse|View> <resource>" with
        # the verb taken FROM ``mfams`` (see the Law B loop: ``word = "View" if
        # "view" in mfams else "Browse"``), so the SURVIVING name's lead is
        # member-grounded BY CONSTRUCTION and ``missing:verb`` is a factually
        # FALSE stamp — the verb is present and witnessed. Scoring the name the
        # row ACTUALLY carries, through the ordinary rubric below, is the honest
        # reading. It is not a privilege: the resource must still ground on its
        # own merits exactly as for every other row, so a narrowed row whose
        # resource is ungrounded still lands low — with the TRUE reason stamped
        # ('missing:resource') instead of a lie about the verb.
        mfams = _mfams(names)
        lead = _name_lead_family(str(getattr(uf, "name", "") or ""), idx)

        # resource-grounded: the name's resource phrase overlaps the PF display
        # (member-grounded) or a member flow name — singular/plural-robust so
        # "webhook" grounds against "webhooks".
        res_toks = _toks(_res(uf))
        member_toks = set().union(*(_toks(n) for n in names)) if names else set()
        base_res = bool(res_toks & member_toks) or bool(res_toks & _toks(_pfd(uf)))
        # A specific verb must be performed by a member; a generic lead
        # (Manage/Overview — not in any CRUD family) is grounded by any member
        # action (it abstracts, it does not over-claim a specific verb).
        base_verb = (lead in mfams) or (lead is None and len(mfams) >= 1)

        # ── B40 rungs (flag-gated corroboration — NEVER a name change) ──
        # nav rung: the author's own nav label for this UF's PF shares a token
        # with the UF name (INGEST doctrine — author's vocabulary) ⇒ the
        # resource is grounded even when the code-derived resource missed it.
        name_toks = _toks(str(getattr(uf, "name", "") or ""))
        nav_label = _nav.get(str(getattr(uf, "product_feature_id", None) or ""))
        nav_hit = bool(rungs_on and nav_label and (_toks(nav_label) & name_toks))
        # registry rung: every member flow is a maintainer-declared dispatch
        # mint (B34 — the author's own key + exported symbol). That provenance
        # is verb-grounding for a Run/act-family lead (the 'Run X' template).
        member_ids = [str(m) for m in (getattr(uf, "member_flow_ids", None) or [])]
        registry_all = bool(
            rungs_on and member_ids
            and all(_origin.get(m) == "dispatch" for m in member_ids)
        )
        registry_hit = bool(registry_all and lead == "act")

        # ── B50 Seg3 rungs (flag-gated; each grounds RESOURCE only) ──
        # (a) member-file domain noun, (b) param-free route segment, (c) mapped
        # test-file noun — each overlapping the UF name or its resource phrase.
        member_noun_hit = route_hit = test_hit = False
        if rung_on:
            mpaths = _member_paths(uf)
            if mpaths:
                if _extract_domain_noun is not None:
                    dn = _extract_domain_noun(mpaths, "")
                    if dn is not None:
                        dn_toks = _toks(dn.label) | {_sing(dn.token)}
                        member_noun_hit = bool(
                            dn_toks & name_toks) or bool(dn_toks & res_toks)
                route_toks: set[str] = set()
                for p in mpaths:
                    for seg in _route_meaningful_segments(p, vocab):
                        route_toks |= _toks(seg)
                route_hit = bool(
                    route_toks & name_toks) or bool(route_toks & res_toks)
            tnouns = _member_test_nouns(uf)
            test_hit = bool(tnouns & name_toks) or bool(tnouns & res_toks)
            # Telemetry — count each NEW grounding (the low the rung uplifts).
            if not base_res and not nav_hit:
                if member_noun_hit:
                    tele["resource_rung_fired"]["member-noun"] += 1
                if route_hit:
                    tele["resource_rung_fired"]["route"] += 1
                if test_hit:
                    tele["resource_rung_fired"]["test"] += 1

        # ── B57 Seg1 rungs (flag-gated; SAME bar, extra OR-sources) ──
        nav_cluster_hit = i18n_hit = route_verb_hit = False
        ta_res_hit = ta_verb_hit = verb_composition_hit = False
        if v2_on:
            _res_pre = (base_res or nav_hit or member_noun_hit or route_hit
                        or test_hit)
            _verb_pre = base_verb or registry_hit
            # (a) nav-cluster — ANY authored label the nav voted onto the
            # owning PF (not just the one top-voted B40 label) may ground
            # the resource. Labels arrive pre-sorted (determinism).
            for lab in _nav_sets.get(
                    str(getattr(uf, "product_feature_id", None) or ""), ()):
                if _grounds_resource(_toks(lab), res_toks, name_toks):
                    nav_cluster_hit = True
                    break
            # (c) route-method — a member route's declared HTTP method
            # grounds a matching verb-family lead (GET never grounds a
            # 'Delete X' lead — families must agree). Index-only, no IO.
            if lead is not None and _method_fams_by_file:
                for p in _member_paths(uf):
                    if lead in _method_fams_by_file.get(p, ()):
                        route_verb_hit = True
                        break
            # (e) structural:verb-composition (b57-iter2) — the verb
            # families the member COMPOSITION implies (member routes'
            # HTTP methods + page-surface members → read families; the
            # cal.com ceiling: UI-composite journeys whose verb exists
            # nowhere in code as a citable string). A lead whose family
            # the composition implies is verb-grounded; a mutation lead
            # over a read-only composition is NOT (family must be
            # PRESENT — mixed GET+POST grounds only browse/view/create).
            # Index-only, no IO. Empty composition asserts nothing.
            if lead is not None and (_method_fams_by_file or _page_files
                                     or _flow_by_id):
                verb_composition_hit = lead in member_verb_composition(
                    uf, _flow_by_id, _method_fams_by_file, _page_files)
            # (b) i18n-key — KEYS referenced in member SOURCE files.
            # Bounded IO, non-high candidates only: read ONLY when the
            # resource is still ungrounded by every cheaper source.
            if not _res_pre and not nav_cluster_hit:
                ktoks: set[str] = set()
                for p in _member_paths(uf)[:_RUNG_SOURCE_MAX_FILES]:
                    for key in _i18n_keys_from_text(_v2_read(p)):
                        ktoks |= _toks(
                            _CAMEL_BOUNDARY_RE.sub(" ", key))
                i18n_hit = _grounds_resource(ktoks, res_toks, name_toks)
            # (d) test-assert — assertion labels inside MAPPED member
            # test files (flow.test_files only — the B36 member-overlap
            # mapping; an unmapped test file is never read). Bounded IO,
            # read only when a channel is still ungrounded.
            _need_res = not (_res_pre or nav_cluster_hit or i18n_hit)
            _need_verb = not (_verb_pre or route_verb_hit
                              or verb_composition_hit)
            if _need_res or _need_verb:
                for tf in _member_test_files(uf)[:_RUNG_SOURCE_MAX_FILES]:
                    for label in _test_assertion_labels(_v2_read(tf)):
                        if _need_res and not ta_res_hit and _grounds_resource(
                                _toks(label), res_toks, name_toks):
                            ta_res_hit = True
                        if (_need_verb and not ta_verb_hit and lead is not None
                                and _fold_read(_label_lead_family(label))
                                == _fold_read(lead)):
                            ta_verb_hit = True
                    if ((ta_res_hit or not _need_res)
                            and (ta_verb_hit or not _need_verb)):
                        break
            # Telemetry — count each NEW grounding (the row the rung
            # uplifts); test-assert counts each channel it newly grounds.
            _v2_tele = tele["rung_sources_v2_fired"]
            if not _res_pre:
                if nav_cluster_hit:
                    _v2_tele["nav-cluster"] += 1
                if i18n_hit:
                    _v2_tele["i18n-key"] += 1
                if ta_res_hit:
                    _v2_tele["test-assert"] += 1
            if not _verb_pre:
                if route_verb_hit:
                    _v2_tele["route-verb"] += 1
                if ta_verb_hit:
                    _v2_tele["test-assert"] += 1
                if verb_composition_hit:
                    _v2_tele["verb-composition"] += 1

        # ── B61 iter2 — generic-lead composition grounding (same
        # WYSTAN_UF_VERB_SNAP flag). The exact mirror of the base
        # rubric's generic clause (``lead is None and len(mfams) >= 1`` —
        # "it abstracts, it does not over-claim"): a generic/editorial
        # lead with NO action family ('Manage …', 'Complete …',
        # 'Confirm …') is verb-grounded by the member VERB-COMPOSITION —
        # route-declared HTTP methods / page surfaces are a STRONGER
        # evidence class than the flow-name-derived ``mfams`` the base
        # clause accepts. Same bar, one more OR-source (B50 Seg3 / B57
        # Seg1 precedent); names are NEVER touched here (a generic lead
        # has no family conflict — nothing lies, nothing snaps). EMPTY
        # composition stays honest ``missing:verb``. Flag OFF ⇒ False ⇒
        # byte-identical.
        generic_comp_hit = False
        if _snap_on and lead is None:
            generic_comp_hit = bool(member_verb_composition(
                uf, _snap_fbi, _snap_mf, _snap_pf))
            if generic_comp_hit and not (base_verb or registry_hit
                                         or route_verb_hit or ta_verb_hit
                                         or verb_composition_hit):
                _snap_tele["generic_grounded"] += 1

        # ── B57 Seg2 — adjudicated rungs (verified citations; TWO
        # channels since b57-seg2-iter: resource + verb — each verb
        # citation was family-matched against this UF's lead verb by the
        # adjudicator's deterministic verifier before reaching the map) ──
        _adj_entry: Mapping[str, Iterable[str]] = (
            (_adjudicated.get(uid) or {}) if _adjudicated else {})
        adj_res_rungs = sorted(
            {str(a) for a in (_adj_entry.get("resource") or ())})
        adj_verb_rungs = sorted(
            {str(a) for a in (_adj_entry.get("verb") or ())})
        adj_hit = bool(adj_res_rungs)
        adj_verb_hit = bool(adj_verb_rungs)

        # ── W1/C-A — verb:member-lead-echo (see the flag note) ──
        # Evaluated LAST among the verb sources so ``_echo_new`` is a true
        # NET-NEW grounding: it is the tag condition AND the telemetry
        # condition, which is what keeps every already-``high`` row's
        # ``name_evidence`` byte-identical under ON. ``res_toks`` is the
        # SAME ``_sing``-folded resource-phrase set the resource channel
        # judges with, and ``_sing`` itself is threaded as the fold — one
        # tokenizer, one stemmer, no drift surface.
        lead_echo_hit = False
        if _echo_on:
            _echo_name = str(getattr(uf, "name", "") or "")
            lead_echo_hit = bool(member_lead_echo_token(
                _echo_name, names, res_toks, _sing,
                _umb_lex, _umb_flow_count))
            # fixb130 telemetry — the rows the modifier-lead guard REFUSED
            # (they would have echo-grounded under the pre-guard rung).
            if not lead_echo_hit and member_lead_echo_token(
                    _echo_name, names, res_toks, _sing):
                tele["member_lead_echo_modifier_refused"] += 1
        _echo_new = lead_echo_hit and not (
            base_verb or registry_hit or route_verb_hit or ta_verb_hit
            or verb_composition_hit or generic_comp_hit or adj_verb_hit)

        # ── C-B — verb:repo-umbrella-lead (see the flag note) ──
        # ENTRY CONDITION: ``lead is None`` — the UF claims NO CRUD family,
        # so its lead is either an umbrella or editorial. A lead that DOES
        # claim a family ('Deploy databases') is a specific verb and is
        # never reachable here: it must be performed by a member, which is
        # exactly what the base rubric already tests.
        umbrella_hit = False
        if _umb_on and lead is None:
            umbrella_hit = bool(umbrella_lead_token(
                str(getattr(uf, "name", "") or ""), _umb_lex,
                _umb_flow_count, res_toks, _sing))
        _umb_new = umbrella_hit and not (
            base_verb or registry_hit or route_verb_hit or ta_verb_hit
            or verb_composition_hit or generic_comp_hit or adj_verb_hit
            or lead_echo_hit)
        if _umb_new and not (_synth_conf_cap
                             and getattr(uf, "synthesized", False)):
            tele["umbrella_lead_fired"] += 1
        # Count the rows the rung actually MOVED: a synthesized backstop is
        # capped ``low`` below regardless, so counting it would overstate.
        if _echo_new and not (_synth_conf_cap
                              and getattr(uf, "synthesized", False)):
            tele["member_lead_echo_fired"] += 1

        # ── fixb142 Part 3 — verb:flow-verb-class (second axis) ──────────
        # One more OR-source at the UNCHANGED bar, over the SAME member
        # lead-token channel ``base_verb`` already trusts, bucketed by the
        # second table the engine already ships. Flag OFF ⇒ always False ⇒
        # no telemetry key, confidence / evidence / output byte-identical.
        fvc_hit = False
        if _fvc_on:
            fvc_hit = flow_verb_class_agreement(
                str(getattr(uf, "name", "") or ""), names, vocab)
        _fvc_new = fvc_hit and not (
            base_verb or registry_hit or route_verb_hit or ta_verb_hit
            or verb_composition_hit or generic_comp_hit or adj_verb_hit
            or lead_echo_hit or umbrella_hit)
        if _fvc_new and not (_synth_conf_cap
                             and getattr(uf, "synthesized", False)):
            tele["flow_verb_class_fired"] += 1

        res_grounded = (base_res or nav_hit or member_noun_hit or route_hit
                        or test_hit or nav_cluster_hit or i18n_hit
                        or ta_res_hit or adj_hit)
        verb_grounded = (base_verb or registry_hit or route_verb_hit
                         or ta_verb_hit or verb_composition_hit
                         or generic_comp_hit or adj_verb_hit
                         or lead_echo_hit or umbrella_hit or fvc_hit)

        def _rung_fired() -> list[str]:
            r: list[str] = []
            if member_noun_hit:
                r.append("resource:member-noun")
            if route_hit:
                r.append("resource:route")
            if test_hit:
                r.append("resource:test")
            if nav_cluster_hit:
                r.append("resource:nav-cluster")
            if i18n_hit:
                r.append("resource:i18n-key")
            if ta_res_hit:
                r.append("resource:test-assert")
            r.extend(f"adjudicated:{a}" for a in adj_res_rungs)
            return r

        if _is_cli_declared(uf):
            # fixb128 (NS-2) — AUTHOR-DECLARED CLI name. The rubric below
            # grades TEMPLATES the pipeline composed; this sentence is a
            # scan FACT read out of the command's own registration site,
            # and (NS-3) its member is the handler that site names. It
            # keeps the mint's confidence and wears its authored stamp,
            # which must stay STABLE here: the 6.7e adjudicator runs after
            # this stage and reads the stamp to know the row is authored.
            #
            # This is the cut that breaks the measured demote LOOP — the
            # B78-it2 cap below forced every synthesized row to ``low``,
            # and ``low`` is precisely the adjudicator's selection
            # criterion (ollama c24: 8 of 12 CLI journeys demoted,
            # including 'Pull a model from a registry', whose name was
            # never corrupted at all).
            if rungs_on:
                uf.name_evidence = [_CLI_DECLARED_EVIDENCE]
        elif (_synth_conf_cap and getattr(uf, "synthesized", False)
                and uid not in _sc_verdicts
                and not (uid in _sc_admitted
                         and res_grounded and verb_grounded
                         and uid not in qualified
                         and _sc_guard3_ok(uf))):
            # B78-it2 Goal 2b — a synthesized backstop never wears high
            # (or medium) confidence: the row is a coverage claim, not an
            # observed journey, and its rungs echo its own template.
            #
            # fixb145 lane 2 — UNLESS the row was admitted by BOTH guards
            # AND would earn ``high`` on its own evidence anyway. Such a row
            # falls through to the ordinary branch below and is recorded for
            # un-synthesizing at the pre-output seam. An admitted row that
            # does NOT clear the rubric is still capped here — admission is
            # a licence to be graded, never a grade.
            uf.name_confidence = "low"
            if rungs_on:
                uf.name_evidence = ["synthesized"]
        elif res_grounded and verb_grounded and uid not in qualified:
            if _sc_on and getattr(uf, "synthesized", False):
                _sc_converted.add(uid)
            uf.name_confidence = "high"
            if rungs_on:
                fired: list[str] = []
                if base_res and base_verb:
                    fired.append("structural-route")
                if nav_hit:
                    fired.append("nav")
                if registry_hit:
                    fired.append("registry")
                fired.extend(_rung_fired())
                if route_verb_hit:
                    fired.append("verb:route-method")
                if ta_verb_hit:
                    fired.append("verb:test-assert")
                if verb_composition_hit:
                    fired.append("structural:verb-composition")
                if generic_comp_hit:
                    fired.append("structural:verb-composition-generic")
                if _echo_new:
                    # NET-NEW only — a row that was already verb-grounded by
                    # any other source keeps its evidence list byte-identical
                    # under ON, so arming this flag can never churn an
                    # existing ``high``. (Deliberately narrower than the
                    # sibling ``verb:route-method`` tag, which stamps on
                    # already-grounded rows too: 50 stamps vs 13 net-new on
                    # the four W1 boards.)
                    fired.append("verb:member-lead-echo")
                if _umb_new:
                    # NET-NEW only, exactly like the sibling echo tag: a row
                    # already verb-grounded elsewhere keeps a byte-identical
                    # ``name_evidence`` under ON.
                    fired.append("verb:repo-umbrella-lead")
                if _fvc_new:
                    # NET-NEW only (the echo/umbrella idiom) — a row already
                    # verb-grounded by any other source keeps its evidence
                    # list byte-identical under ON.
                    fired.append("verb:flow-verb-class")
                fired.extend(f"adjudicated:{a}" for a in adj_verb_rungs)
                uf.name_evidence = fired or ["structural-route"]
        elif res_grounded:
            uf.name_confidence = "medium"
            if rungs_on:
                fired = []
                if base_res:
                    fired.append("resource")
                if nav_hit:
                    fired.append("nav")
                fired.extend(_rung_fired())
                fired.append("missing:verb")
                uf.name_evidence = fired
        else:
            uf.name_confidence = "low"
            if rungs_on:
                miss = ["missing:resource"]
                if not verb_grounded:
                    miss.append("missing:verb")
                uf.name_evidence = miss

        # fixb142 Part 2 — the NO-CLIMB ceiling. Outside the primary pass a
        # narrowed row may fall or stay but never rise above the confidence
        # it carried into the hook (the fixb130 contract, enforced as the
        # ceiling it is worded as). The EVIDENCE is deliberately left as the
        # rubric wrote it: capping the grade is the fixb130 promise, but
        # re-stamping ``missing:verb`` over a witnessed verb was the lie
        # this part exists to remove — a capped row therefore reads e.g.
        # ``medium`` with the TRUE reason attached. ``_conf_cap`` is empty
        # unless the Part-2 flag is armed AND this is a rescore pass, so the
        # OFF arm never reaches this block.
        _cap = _conf_cap.get(uid)
        if _cap is not None:
            # STRICTLY BELOW, not merely "no higher" — and the full-suite
            # run is what forced the distinction. A first cut capped at the
            # incoming confidence, which lets a narrowed row STAY high when
            # the rewritten name happens to re-ground ('Create item' ->
            # 'View item' over ``view-new-flow`` with PF 'Items' grounding
            # the resource). That silently overturns the R0/fixb106
            # doctrine banked by name — ``test_jsonhero_uf004_create_item_
            # demotes_honestly`` / ``test_novu_uf056_edit_context_demotes_
            # honestly`` — whose whole point is that a rescore in which the
            # membership evidence CHANGED must be able to report a fall,
            # and a hook that only ever holds-or-upgrades is dishonest.
            # fixb129's own docstring flagged those two tests as doctrine,
            # not stale fixtures, so they are honoured rather than re-pinned.
            #
            # The narrowing IS the report: Law B rewrote the name in THIS
            # pass, which only happens when the evidence moved under the
            # row. So the row falls by at least one step. What fixb142 Part
            # 2 changes is the REASON, never the direction — the ordinary
            # rubric supplies the true evidence instead of the hardcoded
            # ``['missing:verb']`` lie.
            _rank = {"low": 0, "medium": 1, "high": 2}
            _floorless = ["low", "medium", "high"]
            _ceiling = max(0, _rank.get(_cap, 0) - 1)
            if _rank.get(str(uf.name_confidence), 0) > _ceiling:
                uf.name_confidence = _floorless[_ceiling]
                tele["narrowed_rescore_capped"] = sorted(
                    {*tele.get("narrowed_rescore_capped", ()), uid})
    # R5-5 — cap census-shape 'high' rows to 'medium' over the FULL set (both
    # this pass and the adjudicator's rescore re-run it; OFF ⇒ no-op).
    # Phase-2 threads the member-evidence pool so the unresolved-dir-token
    # and brand-echo rungs fire in BOTH passes too. fixb107 threads the vocab
    # (brand exemption) + the board's PF-display pool (D1 corroboration) so
    # both exemptions run in BOTH passes as well — an exemption only one pass
    # knows about would be re-capped by the other.
    _apply_r5_confidence_caps(
        user_flows, tele, rungs_on=rungs_on,
        repo_ev=_r5_repo_ev, sets=_r5_sets,
        flow_by_id=flow_by_id, repo_root=repo_root,
        vocab=vocab,
        pf_pool=(
            pf_display_pool(
                str(getattr(pf, "display_name", None) or "")
                for pf in pf_by_slug.values()
            ) if paren_qualifier_admit_enabled() else None
        ))
    # ⚠ STAGE-LOCAL RULER — NOT the board's confidence distribution. ⚠
    # (warden §44, the "+1 telemetry-vs-rows" trace.) This histogram is
    # taken over the in-memory rows THIS pass holds, and several passes run
    # after it and still move grades — the post-mint rescore seams
    # (``postmint_uf_rescore`` / 6.7e, which re-enter these very laws with
    # ``primary_pass=False``) and the synth-fold / terminal lanes, which can
    # also drop a row. Measured on jsonhero-web: this key reads
    # ``{high: 11, medium: 0, low: 0}`` while the SERIALIZED board for the
    # same run reads ``{high: 10, low: 1}`` over the same 11 rows — the
    # missing row is UF-004, re-graded by ``flow_name_v2``'s rescore hook
    # (the exact class fixb142 Part 2 addresses).
    #
    # It is deliberately NOT "fixed" to read serialized truth: this stage
    # runs ~10 passes before serialization and CANNOT see it, and a
    # stage-local telemetry key that honestly reports what the stage did is
    # the right artifact for stage forensics. What must not happen is
    # QUOTING it as a world/board number.
    # AUTHORITATIVE BOARD RULER: ``eval/uf_confidence_census.py`` over the
    # serialized board (``~/.wystan/cold/<slug>.json``), or a replay
    # chained ``--through output`` and counted off ``feature-map-replay.json``.
    tele["confidence_after"] = _conf_hist(user_flows)

    # fixb145 lane 2 — FORENSIC telemetry for the guard verdicts. These laws
    # run from TWO entry points (``run_naming_contract`` and the
    # ``primary_pass=False`` rescore seam) with SEPARATE ``tele`` dicts, so
    # this key describes THIS PASS only and is deliberately NOT the apply
    # contract: the apply reads the state invariant instead (synthesized ∧
    # high ⟺ admitted ∧ earned — see ``synth_conversion``). Publishing an id
    # list as the contract is what lost 18 of infisical's 68 lifted rows.
    # Flag OFF ⇒ ``_sc_on`` False ⇒ no key ⇒ telemetry byte-identical.
    if _sc_on:
        _sc_tele["converted_this_pass"] = sorted(_sc_converted)[:60]
        _sc_tele["converted"] = len(_sc_converted)
        _sc_tele["primary_pass"] = bool(primary_pass)
        _sc_tele["post_adjudicator"] = bool(post_adjudicator)
        tele["synth_conversion"] = _sc_tele
        # NS-46a — bank the verdict so no later re-entry can silently undo it.
        from wystan.pipeline_v2.synth_conversion import (
            record_conversion_verdict,
        )
        record_conversion_verdict(_sc_converted)


def _uf_flow_maps(
    flows: Iterable[Any],
) -> tuple[dict[str, str], dict[str, str], dict[str, Any]]:
    """``(flow_name_by_id, flow_origin_by_id, flow_by_id)`` — the member-id
    lookup maps Law C consumes, keyed by BOTH uuid and name id-forms so
    ``member_flow_ids`` resolve identically everywhere (run_naming_contract
    + the B57 Seg2 ``rescore_uf_confidence`` seam share this builder)."""
    flow_name_by_id: dict[str, str] = {}
    flow_origin_by_id: dict[str, str] = {}
    flow_by_id: dict[str, Any] = {}
    for fl in flows or ():
        _origin_tag = (
            "dispatch"
            if str(getattr(fl, "description", "") or "").startswith(
                "dispatch registry ")
            else ""
        )
        for key in (getattr(fl, "uuid", None), getattr(fl, "name", None)):
            if key:
                flow_name_by_id.setdefault(str(key), str(getattr(fl, "name", "") or ""))
                flow_by_id.setdefault(str(key), fl)
                if _origin_tag:
                    flow_origin_by_id.setdefault(str(key), _origin_tag)
    return flow_name_by_id, flow_origin_by_id, flow_by_id


def run_naming_contract(
    product_features: list[Any],
    user_flows: list[Any],
    flows: Iterable[Any] = (),
    *,
    prev_scan: Mapping[str, Any] | None = None,
    keeper_on: bool = True,
    product_strings: Any = None,
    routes_index: Iterable[Mapping[str, Any]] | None = None,
    thesis_tokens: Iterable[str] = (),
    uf_authored_names: Mapping[str, Iterable[str]] | None = None,
    labeler: Callable[[list[_PendingItem]], dict[str, Any]] | None = None,
    verifier: Callable[[list[dict[str, Any]]], dict[str, bool]] | None = None,
    repo_root: Any = None,
) -> dict[str, Any]:
    """Apply the display-name contract in place; return telemetry.

    Order of authority per display: LAW > PIN > candidate rank. The
    ``labeler`` seam (Wave-3 persona, keyed scans) receives the pending
    items and returns ``{item_key: telemetry-dict}`` decisions — it is
    injected by the caller so this module stays LLM-free and fully
    unit-testable (keyless scans pass ``labeler=None`` and take the
    deterministic top choice everywhere).

    ``repo_root`` (B27) arms the package-manifest display channel for
    package-dir-anchored PFs (see :func:`build_pf_candidates`). ``None``
    (the default) or ``WYSTAN_PF_MANIFEST_NAME=0`` keeps the emission
    byte-identical to pre-B27.
    """
    # fixb136 — the rename registry is scan-scoped and THIS is the scan's
    # first naming pass, so it is cleared here and appended to by every
    # later pass (the 6.7e rescore seam, the post-mint hooks). See
    # ``uf_component_deglue`` for why the ids do not travel as telemetry.
    from wystan.pipeline_v2.uf_component_deglue import (
        reset_renamed_in_scan as _reset_renamed,
    )
    _reset_renamed()
    # NS-46a — the conversion-verdict registry is SCAN-scoped; this is the
    # single primary seam, so it is the honest reset point.
    from wystan.pipeline_v2.synth_conversion import (
        reset_conversion_registry as _sc_reset,
    )
    _sc_reset()
    vocab = load_naming_vocab()
    tele: dict[str, Any] = {
        "enabled": True,
        "pf_total": len(product_features),
        "uf_total": len(user_flows),
        "pf_renamed": 0,
        "pf_pinned": 0,
        "pf_pin_rejected_law": 0,
        "uf_renamed": 0,
        "uf_twins_resolved": 0,
        "uf_synth_named": 0,
        "uf_pin_overridden_by_law": 0,
        "laws_fixed": {},
        "display_collisions_qualified": 0,
        "casing_polished": 0,
    }
    # B16 PF dev-grain law telemetry — added ONLY when the law is ON so a
    # ``WYSTAN_PF_NAME_LAW=0`` scan_meta.naming_contract is byte-identical
    # to the pre-B16 emission.
    if pf_name_law_enabled():
        tele["pf_devgrain_stripped"] = 0
        tele["pf_devgrain_collision"] = 0
    if uf_devgrain_name_enabled():
        tele["uf_devgrain_stripped"] = 0   # B16 Part-1b
    # B27 package-manifest telemetry — added ONLY when the channel is
    # armed (flag ON + repo root available) so a
    # ``WYSTAN_PF_MANIFEST_NAME=0`` scan_meta.naming_contract is
    # byte-identical to the pre-B27 emission.
    manifest_channel_on = repo_root is not None and pf_manifest_name_enabled()
    if manifest_channel_on:
        tele["pf_manifest_named"] = 0
        tele["pf_wordsplit_named"] = 0
    # B56 full-name display telemetry — added ONLY when the law is ON so a
    # ``WYSTAN_PF_FULLNAME_LAW=0`` scan_meta.naming_contract is
    # byte-identical to the pre-B56 emission.
    fullname_law_on = pf_fullname_law_enabled()
    if fullname_law_on:
        tele["pf_fullname_expanded"] = 0
        tele["pf_fullname_missing"] = 0
        tele["uf_fullname_inherited"] = 0
    #: abbr(lower) -> composed "Full Name (ABBR)" for the LEAD token, recorded
    #: during PF Pass 1 and replayed onto UF names (§5). Empty when the law is
    #: OFF ⇒ the final UF pass is a no-op ⇒ byte-identical.
    fullname_map: dict[str, str] = {}

    def _law_fix(law: str) -> None:
        tele["laws_fixed"][law] = tele["laws_fixed"].get(law, 0) + 1

    _authored_map: Mapping[str, Iterable[str]] = _with_cli_declared(
        uf_authored_names, user_flows)

    def _authored_for(uf: Any) -> list[str]:
        return list(_authored_map.get(str(getattr(uf, "id", "") or ""), ()) or ())

    # Flow display names by member id (verb evidence for UF templates).
    # B40 — ``flow_origin_by_id`` tags each flow's provenance for Law C's
    # registry rung: a dispatch-registry mint (dispatch_registry.py) carries a
    # ``description`` that begins ``"dispatch registry "`` (the maintainer's own
    # declared key + exported symbol). Keyed by the same id forms as the name
    # map so ``member_flow_ids`` resolve identically.
    flow_name_by_id, flow_origin_by_id, flow_by_id = _uf_flow_maps(flows)

    # B78 Seg H — member evidence for the dominant-evidence ratio gate on
    # the generic {r} template join (built per UF only when the flag is
    # armed; ``None`` ⇒ every build_uf_candidates call is byte-identical).
    from wystan.pipeline_v2.dominant_evidence import (
        dominant_evidence_naming_enabled as _dom_naming_on_fn,
        member_evidence_pairs as _dom_member_pairs,
    )
    _dom_naming_on = _dom_naming_on_fn()

    def _seg_h_evidence(uf: Any) -> list[tuple[str, str]] | None:
        if not _dom_naming_on:
            return None
        return _dom_member_pairs([
            flow_by_id[str(m)]
            for m in (getattr(uf, "member_flow_ids", None) or [])
            if str(m) in flow_by_id
        ])

    # B57 Seg1 — materialize once (three consumers may iterate) and build
    # the ALL-voted-labels view only when the rung flag is armed (OFF ⇒
    # zero extra work, byte-identical emission).
    routes_index = list(routes_index) if routes_index is not None else None
    nav_labels = nav_labels_for_pfs(
        product_features, product_strings, routes_index)
    nav_label_sets = (
        nav_label_sets_for_pfs(product_features, product_strings, routes_index)
        if uf_rung_sources_v2_enabled() else {}
    )
    # Display-cross evidence gate (default OFF): the DISPLAY channel's three
    # nav consumers (Pass-1 candidate rank, keyed labeler context, the B71
    # provenance ladder) read the GATED label map — foreign labels reverted,
    # anchor-page tie-break, title-cased. Law C (B40 nav rung) and the B57
    # nav-cluster rung keep reading the RAW votes below — untouched. OFF ⇒
    # empty map + raw reads everywhere ⇒ byte-identical.
    display_gate_on = pf_display_evidence_gate_enabled()
    gated_nav_labels = (
        gated_nav_labels_for_pfs(
            product_features, product_strings, routes_index, vocab)
        if display_gate_on else {}
    )

    def _display_nav_label(slug: str) -> str | None:
        if display_gate_on:
            return gated_nav_labels.get(slug) or None
        return nav_labels.get(slug)

    prev_by_anchor, prev_by_slug = (
        _prev_pf_displays(prev_scan) if (keeper_on and prev_scan) else ({}, {})
    )

    pending: list[_PendingItem] = []

    # ── Pass 1: product features (pin > candidates; laws gate both) ──
    taken: dict[str, str] = {}  # case-folded display -> pf slug
    pf_by_slug: dict[str, Any] = {}
    # R5-1 identity-parity (WYSTAN_NAMING_WAVE_R5, default ON since 2026-07-21) — the
    # identity-fold of EVERY live PF slug, computed once so the guard is
    # order-independent (a display grabbing a not-yet-processed PF's identity
    # is caught). Empty work when the wave is off ⇒ byte-identical.
    _wave_r5 = naming_wave_r5_enabled()
    _pf_slug_idents: set[str] = (
        {_ident_fold(str(getattr(p, "name", "") or "")) for p in product_features}
        - {""}
        if _wave_r5 else set()
    )
    if _wave_r5:
        tele["pf_identity_parity_qualified"] = 0
    # R5 phase-2 — vocab sets for the compose canonicalizer + display
    # derivation lanes (cached; zero work when the wave is off).
    _r5_sets: Mapping[str, Any] | None = r5_vocab_sets(vocab) if _wave_r5 else None
    for pf in sorted(product_features,
                     key=lambda p: str(getattr(p, "name", "") or "")):
        slug = str(getattr(pf, "name", "") or "")
        pf_by_slug[slug] = pf
        current = str(
            getattr(pf, "display_name", None)
            or (_display_word(slug, vocab) if slug else "")
        )
        anchor_id = str(getattr(pf, "anchor_id", None) or "")
        candidates = build_pf_candidates(
            pf, vocab, nav_label=_display_nav_label(slug), repo_root=repo_root)
        # B27 — the package's own declared display word (None when the
        # channel is off / not a package-dir anchor). Cached read.
        pkg_display, pkg_src = (
            _package_manifest_display(anchor_id, vocab, repo_root, current)
            if manifest_channel_on else (None, "")
        )

        chosen: str | None = None
        pinned = False
        pin = (prev_by_anchor.get(anchor_id) if anchor_id else None) or (
            prev_by_slug.get(slug) if slug else None)
        if pin:
            pin_polished = polish_display_casing(pin, vocab)
            folded = pin_polished.strip().lower()
            if display_law_violations(pin_polished, vocab):
                tele["pf_pin_rejected_law"] += 1
            elif folded in taken:
                tele["pf_pin_rejected_law"] += 1
            else:
                chosen, pinned = pin_polished, True

        if chosen is None:
            for cand in candidates:
                folded = cand.strip().lower()
                if display_law_violations(cand, vocab):
                    continue
                if folded in taken:
                    continue
                chosen = cand
                break
        if chosen is None:
            # Every candidate law-dirty or colliding: qualify with the
            # anchor qualifier (uniqueness law), else derive a lawful
            # display from the SLUG's words (param/extension glyphs
            # cannot survive canonical_slug), else keep the polished
            # current verbatim (never-worse; mint guaranteed uniqueness).
            base, qual = humanize_anchor_display(anchor_id, vocab)
            if pkg_display:
                # B27 — the manifest word replaces the dir-slug base so
                # the "(Qualifier)" decoration keeps composing.
                base = pkg_display
            fallback = polish_display_casing(current, vocab)
            bq = f"{base} ({qual})" if base and qual else None
            if bq and _wave_r5 and _r5_sets is not None:
                # R5-4 — compose site 2/3: canonical joint on the qualified
                # PF fallback ('New (Studio)' class inverts to noun-lead).
                bq, _r5_bq_rule = canonicalize_compose(bq, _r5_sets)
                if _r5_bq_rule:
                    tele["r5_compose_canonicalized"] = (
                        tele.get("r5_compose_canonicalized", 0) + 1)
            if humanize_route_names_enabled():
                # B2: the qualified fallback must be LAW-clean AND free of
                # route-template residue (the pre-B2 path emitted
                # "T.$team URL+ (Authenticated+)" here without checking).
                if (bq and not display_law_violations(bq, vocab)
                        and not _has_route_template_residue(bq)
                        and bq.strip().lower() not in taken):
                    fallback = bq
                    tele["display_collisions_qualified"] += 1
                elif (base and not display_law_violations(base, vocab)
                        and not _has_route_template_residue(base)
                        and base.strip().lower() not in taken):
                    fallback = base
                elif (display_law_violations(fallback, vocab)
                        or _has_route_template_residue(fallback)):
                    scrubbed = _strip_display_residue(fallback, vocab)
                    from_slug = _display_word(slug, vocab) if slug else None
                    if (scrubbed and not display_law_violations(scrubbed, vocab)
                            and scrubbed.strip().lower() not in taken):
                        fallback = scrubbed
                    elif (from_slug
                            and not display_law_violations(from_slug, vocab)
                            and from_slug.strip().lower() not in taken):
                        fallback = from_slug
            elif bq and bq.strip().lower() not in taken:
                fallback = bq
                tele["display_collisions_qualified"] += 1
            elif display_law_violations(fallback, vocab) and slug:
                from_slug = _display_word(slug, vocab)
                if (from_slug
                        and not display_law_violations(from_slug, vocab)
                        and from_slug.strip().lower() not in taken):
                    fallback = from_slug
            chosen = fallback

        # ── B16: PF dev-grain suffix law (LAW > PIN, display channel) ──
        # A route-dir leak ('Policy Page' from route:policy-page) strips to
        # the capability ('Policy'); a strip that collides with a sibling PF
        # is kept as-is (the Part-2 unification signal). Runs after the
        # existing selection so it also overrides a stale pin.
        if pf_name_law_enabled():
            new_chosen, stripped_law = _apply_pf_devgrain_law(
                chosen, anchor_id, slug, vocab, taken, tele)
            if stripped_law:
                chosen, pinned = new_chosen, False

        # ── B50 Seg2: raw-param display law (a glyph-less route-param token
        # never appears in a PF display: 'teamurl documents' -> 'team
        # documents'). Runs last so it also cleans a stale pin. Flag OFF ⇒
        # byte-identical.
        if uf_name_degrime_enabled():
            deparamed = _deparam_display(chosen)
            if (deparamed and deparamed != chosen
                    and not display_law_violations(deparamed, vocab)
                    and deparamed.strip().lower() not in taken):
                chosen, pinned = deparamed, False
                tele["pf_display_degrimed"] = (
                    tele.get("pf_display_degrimed", 0) + 1)

        # ── B56: full-name display law (abbreviation → 'Full Name (ABBR)').
        # A shape-flagged abbreviation display ('Sso', 'Pbac', 'Wp') takes its
        # repo-grounded full form; shape-flagged-but-no-evidence is honest debt
        # (display unchanged + missing telemetry, never invented). Runs last so
        # it also expands a de-grimed/manifest choice. Flag OFF ⇒ no map, no
        # keys, no change ⇒ byte-identical.
        if fullname_law_on:
            fn = apply_fullname_expansion(chosen, pf, repo_root, vocab)
            if (fn.display and fn.display != chosen
                    and not display_law_violations(fn.display, vocab)
                    and fn.display.strip().lower() not in taken):
                if fn.abbr and fn.composed_lead:
                    fullname_map[fn.abbr] = fn.composed_lead
                chosen, pinned = fn.display, False
                tele["pf_fullname_expanded"] += 1
            elif fn.source == "missing:expansion":
                tele["pf_fullname_missing"] += 1

        taken[chosen.strip().lower()] = slug
        if pinned:
            tele["pf_pinned"] += 1
        if chosen != current:
            for law in display_law_violations(current, vocab):
                _law_fix(law)
            if chosen == polish_display_casing(current, vocab):
                tele["casing_polished"] += 1
            else:
                tele["pf_renamed"] += 1
            pf.display_name = chosen
        elif getattr(pf, "display_name", None) != chosen:
            pf.display_name = chosen
        # B27 telemetry — the committed display carries the package's
        # own declared word (bare, hub-composed, or "(Qualifier)"-form).
        if (pkg_display and not pinned and chosen != current and (
                chosen == pkg_display
                or chosen.endswith(f"— {pkg_display}")
                or chosen.startswith(f"{pkg_display} ("))):
            tele[f"pf_{pkg_src}_named"] += 1
        if not pinned and len(candidates) > 1 and labeler is not None:
            pending.append(_PendingItem(
                kind="pf", key=slug, current=chosen,
                candidates=[c for c in candidates
                            if not display_law_violations(c, vocab)
                            # B16: never offer the persona a dev-grain-leak
                            # candidate (would re-introduce "Page").
                            and not (pf_name_law_enabled()
                                     and _strip_pf_devgrain_suffix(
                                         c, anchor_id, vocab))],
                context={
                    "anchor_id": anchor_id,
                    "nav_label": _display_nav_label(slug),
                },
                obj=pf,
            ))

    # ── Pass 2: user flows (pins respected; twins/synths templated) ──
    # B50 (degrime ON only) — a template adoption caused SOLELY by the
    # Seg1 echo discriminator (law-clean current name, marked unclean by
    # _degrime_display) is DEFERRED and applied collision-safely after the
    # pass: targets first, then only non-colliding renames land (a template
    # already worn by a sibling never duplicates). Flag OFF ⇒ byte-identical.
    degrime_p2_proposals: dict[str, str] = {}
    # R5-2 echo-hub members that template on their own resource (empty set
    # when the wave is off ⇒ every build_uf_candidates call keeps
    # own_resource=False ⇒ byte-identical).
    _echo_own_res_ids: set[str] = (
        _echo_own_resource_uf_ids(user_flows, pf_by_slug) if _wave_r5 else set()
    )
    # R5-2 iter-2 — spray-form ids (identical PF-identity base + paren qual
    # across ≥2 thin siblings): these adopt the own-resource template even
    # over a law-clean sprayed current. Empty when the wave is off.
    _spray_ids: set[str] = (
        _spray_sibling_uf_ids(user_flows, pf_by_slug) if _wave_r5 else set()
    )
    if _wave_r5:
        tele["uf_own_resource_templated"] = len(_echo_own_res_ids)
        tele["uf_spray_retemplated"] = len(_spray_ids & _echo_own_res_ids)
    # fixb104 — display owners for the dev-grain CASE rung's collision guard
    # (the PF sibling law's ``taken``, at UF grain). Snapshot of the names
    # entering the pass: order-independent, so the rung's verdict does not
    # depend on where the colliding row sits in the list.
    _uf_taken: dict[str, str] = {}
    for _u in user_flows:
        _uf_taken.setdefault(
            str(getattr(_u, "name", "") or "").strip().lower(),
            str(getattr(_u, "id", "") or ""))
    for uf in user_flows:
        pf = pf_by_slug.get(str(getattr(uf, "product_feature_id", None) or ""))
        pf_display = (
            str(getattr(pf, "display_name", None) or getattr(pf, "name", ""))
            if pf is not None else ""
        )
        current = str(getattr(uf, "name", "") or "")
        member_names = [
            flow_name_by_id.get(str(m), str(m))
            for m in (getattr(uf, "member_flow_ids", None) or [])
        ]
        _uid = str(getattr(uf, "id", "") or "")
        _own_res = _uid in _echo_own_res_ids
        candidates = build_uf_candidates(
            uf, pf, vocab, member_names, authored=_authored_for(uf),
            own_resource=_own_res, member_evidence=_seg_h_evidence(uf))
        violations = display_law_violations(
            polish_display_casing(current, vocab), vocab,
            pf_display=pf_display or None)
        # R5-2 iter-2 — ranking within a flagged hub member is decided by
        # whether the CURRENT base wears the PF's identity:
        #   * spray/echo form ('Manage twenty server (billing)', bare
        #     'Manage twenty server') — the base names the HOME, not the
        #     job: the own-resource template must lead even over a
        #     law-clean current (move polished current to the END);
        #   * a healthy job-named current ('Manage invoices (drafts)',
        #     'Browse & manage billing') — the base names a real resource:
        #     the current leads even for a synthesized row (move it to the
        #     FRONT; no churn of good names onto their bare resource).
        if _own_res:
            _pc = polish_display_casing(current, vocab)
            _base_cur = re.sub(r"\s*\([^)]*\)+\s*$", "", current).strip()
            _base_cur = re.sub(r"\s*\([^)]*\)+\s*$", "", _base_cur).strip()
            _pf_ident = _ident_fold(pf_display)
            _wears_pf = bool(_pf_ident) and _pf_ident in _ident_fold(_base_cur)
            if _uid in _spray_ids or _wears_pf:
                _rest = [c for c in candidates if c != _pc]
                if _rest:
                    candidates = _rest + (
                        [_pc] if _pc in candidates else [])
            elif not violations and _pc in candidates:
                candidates = [_pc] + [c for c in candidates if c != _pc]
        pinned = bool(
            keeper_on and isinstance(getattr(uf, "identity", None), dict)
            and (uf.identity or {}).get("pinned_from")
        )
        if pinned and not violations:
            continue  # stability wins — pinned, law-clean
        if pinned and violations:
            tele["uf_pin_overridden_by_law"] += 1

        chosen = None
        for cand in candidates:
            if not display_law_violations(cand, vocab, pf_display=pf_display or None):
                chosen = cand
                break
        if chosen is None:
            chosen = polish_display_casing(current, vocab)

        # R5-2 iter-2 no-new-dup guard — an own-resource-influenced rename
        # never mints a name a live same-PF sibling already wears; keep the
        # old name instead (a kept diseased name is demoted by the R5-5
        # shape cap, never duplicated). OFF ⇒ _own_res is always False.
        if (_own_res and chosen
                and chosen != polish_display_casing(current, vocab)
                and _r5_sibling_name_dup(uf, chosen, user_flows)):
            chosen = polish_display_casing(current, vocab)
            tele["uf_r5_dup_blocked"] = tele.get("uf_r5_dup_blocked", 0) + 1

        # B50 — pure degrime-induced adoption (no law violation, organic
        # journey, no authored label, current only unclean via the echo
        # mark): defer the template; keep the pre-B50 choice (the law-clean
        # polished current) for this pass.
        polished_cur = polish_display_casing(current, vocab)
        if (uf_name_degrime_enabled() and not violations
                and not getattr(uf, "synthesized", False)
                and not _authored_for(uf)
                and chosen != polished_cur
                and _degrime_display(polished_cur) != polished_cur):
            degrime_p2_proposals[str(getattr(uf, "id", "") or "")] = chosen
            chosen = polished_cur

        # ── B16 Part-1b: UF dev-grain suffix law (mirror the PF law) ──
        # "View detections page" -> "View detections" when the home PF anchor
        # is a route:*-page leak. Display channel (uf.name) only.
        if uf_devgrain_name_enabled() and pf is not None:
            uf_stripped = _strip_uf_devgrain_suffix(
                chosen, str(getattr(pf, "anchor_id", None) or ""), vocab,
                # fixb104 — arms the case-boundary rung's echo prong and its
                # post-strip collision guard (both case-rung only).
                pf_display=pf_display or None,
                taken=_uf_taken, uf_id=_uid)
            if uf_stripped:
                chosen = uf_stripped
                tele["uf_devgrain_stripped"] = (
                    tele.get("uf_devgrain_stripped", 0) + 1)

        if chosen != current:
            for law in violations:
                _law_fix(law)
            if "pf_uf_twin" in violations:
                tele["uf_twins_resolved"] += 1
            if getattr(uf, "synthesized", False):
                tele["uf_synth_named"] += 1
            if chosen == polish_display_casing(current, vocab) and not violations:
                tele["casing_polished"] += 1
            else:
                tele["uf_renamed"] += 1
            uf.name = chosen
        if (labeler is not None and not pinned
                and (violations or getattr(uf, "synthesized", False))):
            pending.append(_PendingItem(
                kind="uf", key=str(getattr(uf, "id", "") or ""),
                current=chosen or current,
                candidates=[
                    c for c in candidates
                    if not display_law_violations(
                        c, vocab, pf_display=pf_display or None)
                ],
                context={
                    "pf_display": pf_display,
                    "synthesized": bool(getattr(uf, "synthesized", False)),
                    "member_flows": member_names[:8],
                },
                obj=uf,
                pf_display=pf_display or None,
            ))

    # B50 — apply the deferred degrime template adoptions collision-safely
    # (targets computed over the final Pass-2 names; two rows proposing the
    # same template BOTH keep their names; a template already worn by any
    # row never duplicates). Runs before the labeler so Pass 3 sees final
    # names. Flag OFF ⇒ degrime_p2_proposals is empty ⇒ byte-identical.
    if degrime_p2_proposals:
        _p2_cur = {
            str(getattr(u, "id", "") or ""): str(getattr(u, "name", "") or "")
            for u in user_flows
        }
        _p2_by_id = {str(getattr(u, "id", "") or ""): u for u in user_flows}
        _p2_allowed = degrime_rename_plan(_p2_cur, degrime_p2_proposals)
        for _uid in sorted(_p2_allowed):
            _p2_by_id[_uid].name = degrime_p2_proposals[_uid]
            tele["uf_renamed"] += 1
        _p2_skipped = len(degrime_p2_proposals) - len(_p2_allowed)
        if _p2_skipped:
            tele["uf_degrime_collision_skipped"] = (
                tele.get("uf_degrime_collision_skipped", 0) + _p2_skipped)

    # ── Pass 3: PM Labeler (keyed persona seam — Wave 3 §4.7) ────────
    # The persona returns VALIDATED picks; this stage stays the single
    # display writer and re-checks the laws before applying (defense in
    # depth — a persona bug can never ship a law-violating display).
    if labeler is not None and pending:
        try:
            lab_result = dict(labeler(pending) or {})
        except Exception as exc:  # noqa: BLE001 — persona must never break a scan
            lab_result = {"error": str(exc)}
        choices = lab_result.pop("choices", None) or {}
        applied = 0
        # fixb138 rider — the labeler applied 280 renames across 38 boards
        # with NO ledger, so up to 9.6% of the clean training set was
        # UNATTRIBUTABLE (data-factory finding). Record WHICH rows it
        # actually renamed, mirroring the adjudicator's renames-ledger
        # convention. Pure observability: no pick changes, no display
        # changes, and the key is emitted only when non-empty, so a board
        # the labeler did not touch stays byte-identical.
        applied_ids: list[str] = []

        def _stamp(item: "_PendingItem") -> None:
            rid = str(
                getattr(item.obj, "id", None)
                or getattr(item.obj, "name", None)
                or item.key
            )
            if rid and rid not in applied_ids:
                applied_ids.append(rid)

        # ── fixb143 round-5 (ii-a) EARNED-DISPLAY GUARD ─────────────────
        # WARDEN №47 RESURRECTION. This pass is the declared SINGLE DISPLAY
        # WRITER, and its whole re-check is ``display_law_violations`` — a
        # set that does not contain I11, the banked operator invariant that
        # a container page can never be a feature. So when 6.85's
        # corroboration release had QUALIFIED outline ``home`` to 'Home
        # Popular', a persona pick of 'Home' passed the laws (violations ==
        # []) and overwrote an earned name; the OTHER ON run of the same
        # commit drew ``applied=0`` and kept it. The row's display depended
        # on an LLM draw.
        #
        # The registry (``surface_taxonomy``, scan-scoped, written at the
        # release site) carries the earned display AND the container
        # vocabulary that earned it. A registered row accepts a pick ONLY
        # when the pick is itself non-container under that vocabulary — a
        # genuinely better name ('Popular Documents') still lands, while
        # 'Home' / 'Home Page' / 'Homepage' are refused and the earned name
        # stands under EVERY draw. Flag OFF ⇒ the registry is empty ⇒ the
        # map is empty ⇒ byte-identical.
        _earned_map: Mapping[str, tuple[str, frozenset[str]]] = {}
        _container_only = None
        try:
            from wystan.pipeline_v2.surface_taxonomy import (
                earned_displays,
                is_container_only_display,
                released_display_registry_enabled,
            )
            if released_display_registry_enabled():
                _earned_map = earned_displays()
                _container_only = is_container_only_display
        except Exception:  # noqa: BLE001 — the guard is never a scan risk
            _earned_map, _container_only = {}, None

        def _earned_blocks(item: "_PendingItem", value: str) -> bool:
            """True when *value* would put a container-only display on a
            row whose release EARNED its name this scan."""
            if _container_only is None or not _earned_map:
                return False
            prot = _earned_map.get(str(item.key))
            if prot is None:
                prot = _earned_map.get(
                    str(getattr(item.obj, "name", "") or ""))
            if prot is None:
                return False
            return bool(_container_only(value, prot[1]))

        # PF picks first — UF twin checks below must see the LIVE
        # (post-pick) capability displays, or a PF pick could re-create
        # the very twin the UF pick was validated against.
        for item in pending:
            pick = choices.get(item.key)
            if (item.kind != "pf" or not isinstance(pick, str)
                    or not pick.strip()):
                continue
            pick = " ".join(pick.split())
            if display_law_violations(pick, vocab):
                continue
            cur = str(getattr(item.obj, "display_name", "") or "")
            # Display-cross it3/it4 composite-KEEP (same flag): a
            # hub-family composition's channel prefix ("Chat — Discord",
            # "Email — Mailgun") is evidenced structure — the family word
            # IS the hub dir the vendor package lives under. A persona
            # pick that is just the vendor word (prefix-drop / dash-
            # flatten, join-fold compared against the ANCHOR's vendor
            # segment — mangle- and camelCase-proof) never flattens the
            # composite; instead the family prefix is RE-COMPOSED over
            # the persona's vendor word, which also repairs a degrimed
            # composition ('Email — sendgr' -> 'Email — SendGrid', novu
            # it4). Real corrections (other word content) still apply.
            # OFF path never enters — byte-identical.
            if display_gate_on and cur:
                recomposed = _hub_composite_recompose(
                    str(getattr(item.obj, "anchor_id", None) or ""),
                    cur, pick, vocab)
                if recomposed is not None:
                    tele["labeler_composite_keep"] = (
                        tele.get("labeler_composite_keep", 0) + 1)
                    if (recomposed != cur
                            and not display_law_violations(recomposed, vocab)):
                        if _earned_blocks(item, recomposed):
                            tele["labeler_earned_display_held"] = (
                                tele.get("labeler_earned_display_held", 0) + 1)
                        else:
                            item.obj.display_name = recomposed
                            applied += 1
                            _stamp(item)
                    continue
            if pick != cur:
                # fixb143 round-5 (ii-a) — checked on the value ACTUALLY
                # written, at every write site in this pass.
                if _earned_blocks(item, pick):
                    tele["labeler_earned_display_held"] = (
                        tele.get("labeler_earned_display_held", 0) + 1)
                    continue
                item.obj.display_name = pick
                applied += 1
                _stamp(item)
        for item in pending:
            pick = choices.get(item.key)
            if (item.kind != "uf" or not isinstance(pick, str)
                    or not pick.strip()):
                continue
            pick = " ".join(pick.split())
            uf_obj = item.obj  # UF display channel is ``name``
            live_pf = pf_by_slug.get(
                str(getattr(uf_obj, "product_feature_id", None) or ""))
            live_pf_display = (
                str(getattr(live_pf, "display_name", None)
                    or getattr(live_pf, "name", "") or "")
                if live_pf is not None else (item.pf_display or "")
            )
            if display_law_violations(
                pick, vocab, pf_display=live_pf_display or None,
            ):
                continue
            if pick != str(getattr(uf_obj, "name", "") or ""):
                uf_obj.name = pick
                applied += 1
                _stamp(item)
        lab_result["applied"] = applied
        if applied_ids:
            # Emitted ONLY when the labeler actually renamed something, so
            # every board it left alone keeps a byte-identical scan_meta.
            lab_result["applied_ids"] = applied_ids
        tele["labeler"] = lab_result

        # Final twin sweep against the LIVE displays: a PF pick can twin
        # an untouched UF name ("GoCardless" PF pick vs a "GoCardless"
        # journey the labeler never saw). Law > pick: re-template.
        for uf in user_flows:
            live_pf = pf_by_slug.get(
                str(getattr(uf, "product_feature_id", None) or ""))
            if live_pf is None:
                continue
            live_disp = str(
                getattr(live_pf, "display_name", None)
                or getattr(live_pf, "name", "") or "")
            if not live_disp or (
                str(getattr(uf, "name", "") or "").strip().lower()
                != live_disp.strip().lower()
            ):
                continue
            member_names = [
                flow_name_by_id.get(str(m), str(m))
                for m in (getattr(uf, "member_flow_ids", None) or [])
            ]
            # R5-2 iter-2 — same own-resource threading + no-new-dup guard
            # as the verifier re-derive (OFF ⇒ byte-identical).
            _t_own = str(getattr(uf, "id", "") or "") in _echo_own_res_ids
            for cand in build_uf_candidates(
                    uf, live_pf, vocab, member_names,
                    authored=_authored_for(uf), own_resource=_t_own,
                    member_evidence=_seg_h_evidence(uf)):
                if display_law_violations(
                    cand, vocab, pf_display=live_disp,
                ):
                    continue
                if _wave_r5 and _r5_sibling_name_dup(uf, cand, user_flows):
                    continue
                uf.name = cand
                tele["uf_twins_resolved"] += 1
                _law_fix("pf_uf_twin")
                break

    # ── Pass 4: Draft Verifier over backstop-synthesized UFs (§4.7) ──
    # The chain4 'schema.json'-class guard: a synthesized journey whose
    # draft (post-laws, post-labeler) still fails the persona's honesty
    # review reverts to the deterministic journey TEMPLATE (fold is
    # structurally impossible for a backstop synth — it exists only
    # because no sibling journey covers its PF; dropping would re-arm
    # I8). Rejects never block; keyless (verifier=None) skips.
    if verifier is not None:
        synth_ufs = [u for u in user_flows if getattr(u, "synthesized", False)]
        if synth_ufs:
            drafts = []
            for uf in synth_ufs:
                pf = pf_by_slug.get(
                    str(getattr(uf, "product_feature_id", None) or ""))
                drafts.append({
                    "id": str(getattr(uf, "id", "") or ""),
                    "kind": "synth_uf",
                    "draft": str(getattr(uf, "name", "") or ""),
                    "pf_display": (
                        str(getattr(pf, "display_name", None)
                            or getattr(pf, "name", "") or "")
                        if pf is not None else ""
                    ),
                    "member_flows": [
                        flow_name_by_id.get(str(m), str(m))
                        for m in (getattr(uf, "member_flow_ids", None) or [])
                    ][:8],
                    "synthesis_reason": str(
                        getattr(uf, "synthesis_reason", None) or ""),
                })
            try:
                verdicts = verifier(drafts) or {}
            except Exception as exc:  # noqa: BLE001 — persona never breaks a scan
                verdicts = {}
                tele["verifier_error"] = str(exc)
            rejected = 0
            for uf in synth_ufs:
                if verdicts.get(str(getattr(uf, "id", "") or "")) is not False:
                    continue  # accept (explicit or default) — keep draft
                rejected += 1
                pf = pf_by_slug.get(
                    str(getattr(uf, "product_feature_id", None) or ""))
                pf_display = (
                    str(getattr(pf, "display_name", None)
                        or getattr(pf, "name", "") or "")
                    if pf is not None else ""
                )
                member_names = [
                    flow_name_by_id.get(str(m), str(m))
                    for m in (getattr(uf, "member_flow_ids", None) or [])
                ]
                # R5-2 iter-2 — the reject re-derive threads the SAME
                # own-resource membership as Pass 2 (the keyed-refutation
                # leak: 52 rejects re-derived WITHOUT it, minting 'Manage
                # twenty server' ×22 that Law A spray-qualified back), and
                # the no-new-dup guard skips a candidate a live sibling
                # already wears. OFF ⇒ set empty + guard never consulted ⇒
                # byte-identical.
                _v_own = str(getattr(uf, "id", "") or "") in _echo_own_res_ids
                for cand in build_uf_candidates(
                        uf, pf, vocab, member_names, own_resource=_v_own,
                        member_evidence=_seg_h_evidence(uf)):
                    if display_law_violations(
                        cand, vocab, pf_display=pf_display or None,
                    ):
                        continue
                    if _wave_r5 and _r5_sibling_name_dup(
                            uf, cand, user_flows):
                        continue
                    uf.name = cand
                    break
            tele["verifier_synth_reviewed"] = len(drafts)
            tele["verifier_synth_rejected"] = rejected

    # Post-labeler uniqueness re-check (a labeler pick could collide):
    # first-come (slug-sorted) keeps its display, later duplicates revert
    # to their pre-labeler display recorded in ``taken``.
    seen: dict[str, str] = {}
    for pf in sorted(product_features,
                     key=lambda p: str(getattr(p, "name", "") or "")):
        disp = str(getattr(pf, "display_name", None) or "")
        folded = disp.strip().lower()
        if not folded:
            continue
        if folded in seen:
            base, qual = humanize_anchor_display(
                str(getattr(pf, "anchor_id", None) or ""), vocab)
            slug = str(getattr(pf, "name", "") or "")
            requalified = (
                f"{base} ({qual})" if base and qual
                else polish_display_casing(slug.replace("-", " ").title(), vocab)
            )
            pf.display_name = requalified
            tele["display_collisions_qualified"] += 1
        else:
            seen[folded] = str(getattr(pf, "name", "") or "")

    # ── B9 UF name laws (post-labeler, evaluated over FINAL members) ──
    # Runs AFTER the labeler so labeler-introduced collisions/over-claims are
    # caught; composes with membership fixes (evaluates ACTUAL members).
    # R5 phase-2 — build the member-evidence pool ONCE (UF laws + the PF
    # display lane below share it). ``None`` when the wave is off ⇒ the UF
    # law body skips every phase-2 block ⇒ byte-identical.
    _r5_evidence = (
        build_board_evidence(
            user_flows, product_features, flow_by_id, repo_root)
        if _wave_r5 else None
    )
    if uf_name_laws_enabled():
        _apply_uf_name_laws(
            user_flows, pf_by_slug, vocab, flow_name_by_id, tele,
            authored_ids={str(k) for k in _authored_map.keys()},
            keeper_on=keeper_on,
            nav_labels=nav_labels,
            flow_origin_by_id=flow_origin_by_id,
            flow_by_id=flow_by_id,
            # B57 Seg1 — rung-source collectors (inert dict/None when the
            # WYSTAN_UF_RUNG_SOURCES_V2 flag is OFF).
            nav_label_sets=nav_label_sets,
            routes_index=routes_index,
            repo_root=repo_root,
            r5_evidence=_r5_evidence,
        )

    # ── B56 final pass: UF names inherit the PF abbreviation expansions ──
    # A journey whose name carries an expanded PF's abbreviation renders with
    # the SAME full form (same proof). Runs after every UF name pass. Flag OFF
    # ⇒ ``fullname_map`` is empty ⇒ no-op ⇒ byte-identical.
    if fullname_map:
        for uf in user_flows:
            name = str(getattr(uf, "name", "") or "")
            if not name:
                continue
            new_name = _inherit_fullname(name, fullname_map)
            if new_name != name:
                uf.name = new_name
                tele["uf_fullname_inherited"] += 1

    # ── fixb130 NS-E / NS-2-JS — SYNTH DISPLAY HYGIENE (armed, default OFF)
    # Three shape laws every AUTHORED display already passes, applied to the
    # rows the mint writes verbatim from a PF display / route-group label.
    # Runs LAST over the final UF names so it also cleans a name an earlier
    # lane just chose. See ``SYNTH_DISPLAY_HYGIENE_ENV`` for the measured
    # reason the ECHO segment is used instead of the whole de-grime.
    if synth_display_hygiene_enabled():
        tele["synth_hygiene_paren_space"] = 0
        tele["synth_hygiene_echo"] = 0
        tele["synth_hygiene_shape_stamped"] = 0
        _hyg_rungs_on = name_evidence_rungs_enabled()
        _taken_uf = {
            str(getattr(u, "name", "") or "").strip().lower()
            for u in user_flows
        }

        def _accept(uf: Any, cand: str, cur: str) -> bool:
            """A hygiene rewrite must leave the board strictly no worse: no
            display-law violation it did not already have, and never a
            collision with another row's name (the B31 twin law)."""
            if not cand or cand == cur:
                return False
            low = cand.strip().lower()
            if low != cur.strip().lower() and low in _taken_uf:
                return False
            if (display_law_violations(cand, vocab)
                    and not display_law_violations(cur, vocab)):
                return False
            _taken_uf.discard(cur.strip().lower())
            _taken_uf.add(low)
            return True

        for uf in user_flows:
            cur = str(getattr(uf, "name", "") or "")
            if not cur:
                continue
            # (a) paren-space — whitespace only, EVERY row.
            cand = _paren_space_display(cur)
            if _accept(uf, cand, cur):
                uf.name = cur = cand
                tele["synth_hygiene_paren_space"] += 1
            if not getattr(uf, "synthesized", False):
                continue
            # (b) adjacent phrase echo — synthesized rows only.
            cand = _degrime_echo_display(cur)
            if _accept(uf, cand, cur):
                uf.name = cur = cand
                tele["synth_hygiene_echo"] += 1
            # (c) raw identifier — stamp the R5-5 evidence an AUTHORED row
            # would wear, so the shipped cap reaches the row instead of
            # silently letting it pass ('AuthResponse' strapi UF-003, 'View
            # ApiTokens ListView' UF-044 — both carried only ['synthesized']).
            #
            # Stamp, NOT a blind de-glue: "on par with authored" is exactly
            # this. An authored row is not blindly de-glued either — its
            # R5-5 rename lane demands member corroboration
            # (``glued_lead_identifier``) before it rewrites anything. The
            # KS66 blast census showed why the shortcut is wrong: a blind
            # run-level de-glue turns 'Browse & manage CircleCI authorize'
            # into '… circle CI …' and 'DigitalOcean' into 'digital ocean',
            # because the brand channel that would exempt them is fixb107's
            # own armed flag and those two vendors are not in the casing
            # vocabulary at all. Four cosmetic regressions on already-``low``
            # rows to repair five is not a trade; the cap is the honest half.
            if (_hyg_rungs_on
                    and _name_disease_shape(cur, vocab) == "raw-identifier"):
                _ev = list(getattr(uf, "name_evidence", None) or [])
                if "shape:raw-identifier" not in _ev:
                    uf.name_evidence = [*_ev, "shape:raw-identifier"]
                    tele["synth_hygiene_shape_stamped"] += 1

    # ── B71 Seg A — PF display route-grammar (L-A1) + provenance ladder
    # (L-A2) (WYSTAN_NAMING_PACK, default OFF). Runs over the FINAL PF
    # displays: cleans router-template residue and upgrades a defective
    # (route-residue / bare-basename) display to the highest available
    # higher-provenance source (nav > manifest > basename). OFF/unset never
    # enters this block -> serialized output byte-identical.
    if naming_pack_enabled():
        from wystan.pipeline_v2.pf_display_provenance import (
            ProvenanceSources,
            apply_pf_display_provenance,
        )

        # Display-cross evidence gate (default OFF): when armed, the nav
        # channel feeding the provenance ladder is the GATED map (foreign
        # labels reverted, anchor-page tie-break, title-cased — the same
        # ``_display_nav_label`` view Pass 1 consumed) instead of the raw
        # top-vote label. OFF/unset reproduces the pre-gate ``nav`` byte
        # for byte.

        def _pf_sources(pf: Any) -> ProvenanceSources:
            pslug = str(getattr(pf, "name", "") or "")
            aid = str(getattr(pf, "anchor_id", None) or "")
            cur = str(getattr(pf, "display_name", None)
                      or getattr(pf, "name", "") or "")
            manifest = ""
            if repo_root is not None:
                pkg, pkg_src = _package_manifest_display(aid, vocab, repo_root, cur)
                if pkg and pkg_src == "manifest":
                    manifest = pkg
            _rq_disp, _rq_word = _route_qualified_candidate(aid, vocab)
            return ProvenanceSources(
                nav=_display_nav_label(pslug) or "",
                manifest=manifest,
                basename=_anchor_terminal_segment(aid) or "",
                route_qualified=_rq_disp,
                route_qualifier_word=_rq_word,
                # Horizon-1 ruling (2026-07-16): anchor-kind scopes the
                # trailing-'+' residue rung (route: only).
                anchor_source=_anchor_path(aid)[0],
            )

        tele["pf_display_provenance"] = apply_pf_display_provenance(
            product_features, _pf_sources, vocab)

    # ── R5-3 phase-2: PF display derivation (WYSTAN_NAMING_WAVE_R5) ──
    # The split-core rename lane over PF displays ('Signin' -> 'Sign in',
    # 'Blobstorage' -> 'Blob storage') + the unresolved-dir-token conf-drop
    # ('Htmltopdf' / 'Bgtasks' keep their name, cap high -> medium and stamp
    # ``shape:unresolved-dir-token``). Collision-safe (folded-display map);
    # identity-folds are INVARIANT under a space split, so R5-1 parity below
    # judges the same identities. Flag OFF ⇒ skipped ⇒ byte-identical.
    if _wave_r5 and _r5_sets is not None and _r5_evidence is not None:
        _r5_repo_ev, _, _r5_pf_ev = _r5_evidence
        _r5_pf_empty = MemberEvidence()
        _pf_cur: dict[str, str] = {}
        _pf_props: dict[str, str] = {}
        for pf in sorted(product_features,
                         key=lambda p: str(getattr(p, "name", "") or "")):
            slug = str(getattr(pf, "name", "") or "")
            disp = str(getattr(pf, "display_name", None) or "")
            _pf_cur[slug] = disp
            if not disp or "(" in disp:
                continue
            healed, _srcs = derive_split_display(
                disp, _r5_pf_ev.get(slug) or _r5_pf_empty, _r5_repo_ev,
                _r5_sets)
            if _srcs and healed != disp:
                healed = polish_display_casing(healed, vocab)
            if healed != disp and not display_law_violations(healed, vocab):
                _pf_props[slug] = healed
        if _pf_props:
            _pf_by_slug_l = {
                str(getattr(p, "name", "") or ""): p for p in product_features
            }
            for slug in sorted(degrime_rename_plan(_pf_cur, _pf_props)):
                _pf_by_slug_l[slug].display_name = _pf_props[slug]
                tele["r5_pf_split_renamed"] = (
                    tele.get("r5_pf_split_renamed", 0) + 1)
        _r5_repo_ev2 = _r5_evidence[0]
        _rungs_on = name_evidence_rungs_enabled()
        for pf in sorted(product_features,
                         key=lambda p: str(getattr(p, "name", "") or "")):
            if str(getattr(pf, "name_confidence", "") or "") != "high":
                continue
            disp = str(getattr(pf, "display_name", None) or "")
            # fixb133 / warden §37 blocker 3 — DRESSING MUST NEVER TOUCH A
            # CONFIDENCE CHANNEL. This lane is SHAPE-BOUNDED (a 1-token
            # display, or '<Verb> <lower-plural>'), so an M2 qualifier
            # silently took cal.com 'Playground'/'Troubleshoot' out of
            # shape: the cap never fired, the row kept 'high' and lost its
            # ``shape:unresolved-dir-token`` evidence. Judge the UNDRESSED
            # base — the tokens the rung injected are subtracted first, so
            # a dressed row caps exactly as its bare self would. Inert when
            # M2 is off (no tokens recorded ⇒ identity).
            disp = _undressed_base(pf, disp)
            if unresolved_dir_token(disp, _r5_repo_ev2, _r5_sets) is None:
                continue
            pf.name_confidence = "medium"
            if _rungs_on:
                _ev = list(getattr(pf, "name_evidence", None) or [])
                if "shape:unresolved-dir-token" not in _ev:
                    _ev.append("shape:unresolved-dir-token")
                pf.name_evidence = _ev
            tele["r5_pf_dirtoken_capped"] = (
                tele.get("r5_pf_dirtoken_capped", 0) + 1)

    # ── R5-1: identity-parity law (WYSTAN_NAMING_WAVE_R5, default ON) ──
    # THE authoritative last word on PF displays. The B71 provenance ladder
    # (above) re-derives each display independently from the RAW nav channel
    # with no cross-PF check, so it re-introduces the identity-parity remnant
    # the merged display-cross-gate leaves grounded: a display whose
    # identity-fold equals ANOTHER live PF's canonical slug ('Monitors' on
    # ``checker`` == the ``monitors`` PF; openstatus ``general`` -> 'Settings'
    # == the ``settings`` PF) — trust-breaking, a feature wearing another
    # feature's identity. Runs AFTER every prior PF-display pass (Pass-1,
    # labeler, uniqueness re-check, provenance ladder) so nothing reverts it;
    # repairs to the honest own-slug word (else the anchor qualifier) and also
    # closes a residual shared-display twin. Flag OFF ⇒ the whole block is
    # skipped ⇒ byte-identical.
    if _wave_r5:
        _seen_ident: dict[str, str] = {}
        for pf in sorted(product_features,
                         key=lambda p: str(getattr(p, "name", "") or "")):
            disp = str(getattr(pf, "display_name", None) or "")
            folded = disp.strip().lower()
            if not folded:
                continue
            slug = str(getattr(pf, "name", "") or "")
            ci = _ident_fold(disp)
            foreign_slug = (
                bool(ci) and ci != _ident_fold(slug) and ci in _pf_slug_idents
            )
            twin = folded in _seen_ident and _seen_ident.get(folded) != slug
            if foreign_slug or twin:
                repaired = _identity_parity_repair(
                    disp, str(getattr(pf, "anchor_id", None) or ""),
                    slug, vocab, _seen_ident, _pf_slug_idents)
                if repaired is not None and repaired != disp:
                    pf.display_name = repaired
                    tele["pf_identity_parity_qualified"] += 1
                    _seen_ident[repaired.strip().lower()] = slug
                    continue
            _seen_ident.setdefault(folded, slug)

    tele["labeler_pending"] = len(pending)
    return tele


def _repo_slug_echo(base: str, repo_root: Any) -> bool:
    """fixb107 D3b — the display base's POST-LEAD remainder carries the
    repository's own slug token ('Manage onyx' on onyx, 'View app dub co'
    on dub).

    The test is :func:`naming_wave_r5.brand_echo_pkg`'s slug-token test —
    token equality against the repo-root basename, never substring, so
    ``status-page`` on openstatus stays clean — read at the display base
    instead of at a workspace-package dir. That rung structurally cannot
    see these rows: it refuses any name containing '(' and demands the
    remainder BE a ``packages|apps|libs|crates`` dir, while the measured
    exhibits live under ``apps/web/**`` (dub) and ``backend/**`` (onyx).
    A base that restates the repository names no capability, and a good
    qualifier may not promote it."""
    root = os.path.basename(os.path.normpath(str(repo_root or "")))
    slug_toks = {t for t in re.split(r"[^a-z0-9]+", root.lower()) if t}
    if not slug_toks:
        return False
    words = [w for w in re.split(r"[^A-Za-z0-9]+", str(base or "")) if w]
    rest = {w.lower() for w in words[1:]}
    return bool(slug_toks & rest)


def _paren_base_clean(
    base: str, vocab: Mapping[str, Any] | None, repo_root: Any,
) -> bool:
    """fixb107 D3 — the base a qualifier disambiguates is itself healthy.

    Three refusals, each a SHIPPED predicate read at the base:
    :func:`display_law_violations` (bare_verb / stranded_connective /
    param / file_stem / …), the ``raw-identifier`` shape, and the
    repo-slug echo (:func:`_repo_slug_echo`). Measured on the 41
    D1^D2-admitted census rows: 5 refusals, and they are exactly the four
    named leaks plus dub UF-057 'Browse group' (``bare_verb`` — an honest
    base disease the law already knew about)."""
    text = str(base or "").strip()
    if not text:
        return False
    if display_law_violations(text, vocab):
        return False
    if _name_disease_shape(text, vocab) is not None:
        return False
    return not _repo_slug_echo(text, repo_root)


def _apply_r5_confidence_caps(
    user_flows: Iterable[Any], tele: dict[str, Any], *, rungs_on: bool,
    repo_ev: MemberEvidence | None = None,
    sets: Mapping[str, Any] | None = None,
    flow_by_id: Mapping[str, Any] | None = None,
    repo_root: Any = None,
    vocab: Mapping[str, Any] | None = None,
    pf_pool: frozenset[str] | None = None,
) -> None:
    """R5-5 negative confidence rungs (``WYSTAN_NAMING_WAVE_R5``, default
    ON since the 2026-07-21 pack-2 flip). A FINAL sweep over EVERY user
    flow — placed inside
    :func:`_apply_uf_name_laws` so BOTH the naming-contract pass AND the
    6.7e adjudicator's ``rescore_uf_confidence`` re-run it (else the
    adjudicator re-grades a capped row back to 'high'). The Law C rubric
    only re-grades the ``ordered`` subset; a UF graded 'high' upstream
    (stage 6.7b refiner / 6.7d journey abstraction) never reaches it.

    A census disease shape (paren qualifier, raw camel/snake identifier)
    caps a 'high' grade to 'medium' and stamps a ``shape:<class>`` evidence
    tag — 87% of the census-flagged rows shipped 'high', blinding the
    boards. NAME is never touched (display laws own it); only the
    confidence grade + audit trail move. Flag OFF ⇒ no-op ⇒ byte-identical.

    fixb107 threads two EXEMPTIONS into the first two rungs — the brand
    canonical casing this module itself minted
    (``WYSTAN_BRAND_SHAPE_EXEMPT``, via ``vocab``) and the
    product-corroborated paren qualifier Law-B itself minted
    (``WYSTAN_PAREN_QUALIFIER_ADMIT``, via ``pf_pool``). Both are
    FALL-THROUGHs: an exempted row keeps walking every rung below, so its
    real disease — if it has one — is still diagnosed by the rung that owns
    it. Both flags OFF (the default) ⇒ this sweep is byte-identical."""
    if not naming_wave_r5_enabled():
        return
    _paren_admit = paren_qualifier_admit_enabled() and pf_pool is not None
    _brand_exempt = brand_shape_exempt_enabled() and vocab is not None
    capped = 0
    for uf in user_flows:
        if str(getattr(uf, "name_confidence", "") or "") != "high":
            continue
        name = str(getattr(uf, "name", "") or "")
        shape = _name_disease_shape(name, vocab)
        if shape is None and _brand_exempt and _name_disease_shape(name) == (
                "raw-identifier"):
            # Telemetry only — the verdict already fell through above.
            tele["uf_brand_shape_exempt"] = (
                tele.get("uf_brand_shape_exempt", 0) + 1)
        if shape == "paren-qualifier" and _paren_admit:
            # fixb107 D1^D2 (qualifier is product-corroborated + residue
            # free) ^ D3 (the base it disambiguates is itself clean).
            _qual = paren_qualifier_corroborated(name, pf_pool or frozenset())
            if _qual is not None and _paren_base_clean(
                    name[:name.find("(")], vocab, repo_root):
                shape = None
                tele["uf_paren_admitted"] = (
                    tele.get("uf_paren_admitted", 0) + 1)
        if not shape and sets is not None:
            # R5-5-ext brand-echo — a bare '<verb> <pkg>' journey whose
            # remainder restates a brand-echoing workspace package from
            # its OWN member paths never ships 'high' (probe r55: ANY
            # member count; healthy product-word packages untouched).
            # Checked BEFORE the dir-token rung — it is the more specific
            # diagnosis when a brand token also lacks symbol-singles
            # ('Manage hoppscotch desktop' stamps brand-echo).
            _paths: list[str] = []
            for _mid in (getattr(uf, "member_flow_ids", None) or ()):
                _fl = (flow_by_id or {}).get(str(_mid))
                if _fl is not None:
                    _paths.extend(
                        str(p) for p in (getattr(_fl, "paths", None) or ()))
            if brand_echo_pkg(name, _paths, repo_root, sets) is not None:
                shape = "brand-echo"
                tele["uf_brand_echo_capped"] = (
                    tele.get("uf_brand_echo_capped", 0) + 1)
        if not shape and repo_ev is not None and sets is not None:
            # R5-3 phase-2 conf-drop — an UNRESOLVED dir-token keeps its
            # name but never ships 'high' (Htmltopdf / Bgtasks class:
            # zero const-guarded symbol-singles, split-core found no
            # evidence either — this runs after the rename lane).
            if unresolved_dir_token(name, repo_ev, sets) is not None:
                shape = "unresolved-dir-token"
                tele["uf_dirtoken_capped"] = (
                    tele.get("uf_dirtoken_capped", 0) + 1)
        if not shape and repo_ev is not None and sets is not None:
            # R5-5-ext glued-identifier (B102) — a producer lowercased a
            # PascalCase basename BEFORE tokenizing, so the camel boundary
            # the raw-identifier rung looks for is already gone
            # ('Manage ipallowlistpage' wore HIGH on infisical ON). Capped,
            # never relabeled: the row keeps its identifier and carries
            # shape:glued-identifier as its audit trail. Rides the same flag
            # as the rest of the pack via the postmint rescore that re-runs
            # this sweep over the CS children.
            if glued_identifier(name, repo_ev, sets) is not None:
                shape = "glued-identifier"
                tele["uf_glued_capped"] = (
                    tele.get("uf_glued_capped", 0) + 1)
        if not shape and repo_ev is not None and sets is not None \
                and postmint_rescore_enabled():
            # R5-5-ext glued-LEAD (fixb103) — the mirror of the rung above
            # at the FIRST token: uf_cases_split's no-majority fallback
            # copies the parent's own leading word into the verb slot, so a
            # glued identifier lands at LEAD ('Settingspage pam account
            # policies' — six such rows wore HIGH on infisical ON, invisible
            # to the trailing-token rung). Explicitly flag-gated: the tail
            # rung ships under the R5 flag, this one rides the postmint pack
            # so the OFF arm stays byte-identical.
            if glued_lead_identifier(name, repo_ev, sets) is not None:
                shape = "glued-lead-identifier"
                tele["uf_glued_lead_capped"] = (
                    tele.get("uf_glued_lead_capped", 0) + 1)
        if not shape:
            continue
        uf.name_confidence = "medium"
        if rungs_on:
            ev = list(getattr(uf, "name_evidence", None) or [])
            if f"shape:{shape}" not in ev:
                ev.append(f"shape:{shape}")
            uf.name_evidence = ev
        capped += 1
    tele["uf_shape_capped"] = tele.get("uf_shape_capped", 0) + capped


#: fixb138 / NS-43b — the evidence-honesty stamp: the row's verb channel is
#: grounded by its own display LEAD, which the base rubric grounded through
#: ``base_verb`` without ever minting a granular ``verb:*`` tag for it.
VERB_NAME_LEAD_EVIDENCE = "verb:name-lead"


def _has_verb_stamp(ev: Iterable[Any] | None) -> bool:
    """True when the row ALREADY carries a verb-channel stamp of any kind.

    The union of every tag Law C mints into the verb channel:
    ``verb`` / ``verb:<rung>`` / ``verb-<rung>`` /
    ``structural:verb-composition[-generic]``.
    """
    for e in (ev or ()):
        t = str(e)
        if (t == "verb" or t.startswith("verb:") or t.startswith("verb-")
                or t.startswith("structural:verb-composition")):
            return True
    return False


def _verb_led_name(name: str, sets: Mapping[str, Any] | None) -> bool:
    """True when the display's LEAD token is a verb per the ENGINE'S OWN
    table — ``r5_vocab_sets(...)["verbs"]``, the same set (and the same
    fold) ``unresolved_dir_token`` queries. NO new vocabulary is minted
    here; the mechanism is entirely "ask the table we already ship".

    CORROBORATION ONLY, and the direction is load-bearing: a hit
    SHORT-CIRCUITS to verb-led, a miss asserts NOTHING. The table is a
    131-word corroboration set, so reading its complement as proof of
    verblessness is the same inversion W1/C-A was written to repair
    ('journey-action-families.yaml documents its verbs as CORROBORATION;
    Law C's base rubric reads them as an EXISTENCE GATE'). Verblessness
    gets its own POSITIVE proof — see :func:`_resource_noun_lead`.

    LEAD position only, exactly like every other verb rung in this module:
    'Pixel share' is not verb-led even though 'share' is in the table,
    because the sentence's subject is a noun and its action is not stated.
    """
    if not sets:
        return False
    toks = str(name or "").split()
    if not toks:
        return False
    return _r5_fold(toks[0]) in sets["verbs"]


def _uf_sing(t: str) -> str:
    """``_apply_uf_name_laws``'s own singular fold, verbatim."""
    return t[:-1] if (t.endswith("s") and len(t) > 3) else t


def _uf_toks(text: str) -> set[str]:
    """``_apply_uf_name_laws``'s own token fold, verbatim."""
    return {
        _uf_sing(t)
        for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if t
    }


def _resource_grounding_tokens(
    uf: Any,
    pf_by_slug: Mapping[str, Any],
    vocab: Mapping[str, Any],
) -> set[str]:
    """The NOUNS this row's resource channel is grounded on, singular-folded.

    Exactly the two token pools Law C's own ``base_res`` reads —
    ``_toks(_res(uf))`` and ``_toks(_pfd(uf))`` — reproduced at module
    level because the originals are nested inside ``_apply_uf_name_laws``.

    Member FLOW-NAME tokens are DELIBERATELY excluded even though
    ``base_res`` unions them in: a flow name carries its own action verb
    ('create-pixel-flow'), so admitting that pool would make 'Create
    users' read as noun-led. This pool must hold resource NOUNS only.
    """
    pf = pf_by_slug.get(str(getattr(uf, "product_feature_id", None) or ""))
    pfd = (
        str(getattr(pf, "display_name", None)
            or getattr(pf, "name", "") or "")
        if pf is not None else ""
    )
    base = str(getattr(uf, "resource", "") or "") or pfd
    base = re.sub(r"[-_]+", " ", base).strip()
    res = _resource_phrase(base, vocab) or base
    return _uf_toks(res) | _uf_toks(pfd)


def _resource_noun_lead(
    uf: Any,
    pf_by_slug: Mapping[str, Any],
    vocab: Mapping[str, Any],
) -> bool:
    """POSITIVE proof that the display is NOUN-led: its LEAD token IS the
    row's own resource noun.

    This is the evidence a demotion needs, and it is a claim the row makes
    about ITSELF rather than an absence from a word list. 'Pixel share'
    leads with 'pixel', which is literally its ``resource`` and its PF
    display ('Pixels') — the sentence restates its own subject and never
    states an action. 'Authenticate With SSO' leads with a token that is
    nobody's resource noun, so it is protected whether or not the verb
    table has ever heard of 'authenticate'.

    KNOWN IMPRECISION — banked here because it is the likeliest future
    narrowing signal, not a defect to be silently lived with.

    RESIDUAL A (5 of the 20 world hits): a PF DISPLAY is sometimes itself
    a VERB PHRASE — 'Accept Invitation', 'Compare Models', 'Compose
    (Deploy)', 'Run Streams' — so the ``_pfd`` pool injects that verb and
    a row leading with it reads as noun-led ('Deploy and manage MongoDB
    instances' under PF 'Compose (Deploy)'). Dropping the ``_pfd`` pool is
    NOT the cure: it is the ONLY pool grounding the correct 'Availability'
    / 'privileges' / 'Applications' demotions, and resource-only was
    MEASURED at 12 hits / 5 correct — no better. The narrowing to reach
    for is a LEAD-POSITION or verb-phrase test ON THE PF DISPLAY, so a PF
    named for an action stops donating its verb to this pool.

    RESIDUAL B (7 of 20): a resource noun that also verbs — 'chat',
    'scan', 'tag', 'launch', 'push'. The verb-table short-circuit is meant
    to protect exactly these and cannot, because none of those words is in
    the 131-word table.

    Cold triage census, 52 boards: 20 hits, 8 correct. 8 right against 12
    wrong is a net honesty LOSS on an honesty lane — which is why the
    demote lane ships ARMED BUT OFF (WYSTAN_VERBLESS_NO_HIGH), while
    the corroboration-only stamp lane flipped ON at pack #40.
    """
    toks = str(getattr(uf, "name", "") or "").split()
    if not toks:
        return False
    lead = _uf_sing(re.sub(r"[^a-z0-9]+", "", toks[0].lower()))
    if not lead:
        return False
    return lead in _resource_grounding_tokens(uf, pf_by_slug, vocab)


def rescore_uf_confidence(
    product_features: list[Any],
    user_flows: list[Any],
    flows: Iterable[Any] = (),
    *,
    product_strings: Any = None,
    routes_index: Iterable[Mapping[str, Any]] | None = None,
    uf_authored_names: Mapping[str, Iterable[str]] | None = None,
    keeper_on: bool = True,
    repo_root: Any = None,
    adjudicated_sources: Mapping[str, Mapping[str, Iterable[str]]] | None = None,
    post_adjudicator: bool = False,
) -> dict[str, Any]:
    """B57 Seg2 — the Law C RE-SCORE seam for the Stage 6.7e adjudicator.

    Re-applies the UF name laws (the same ``_apply_uf_name_laws`` body the
    contract runs, over the CURRENT rows) with the adjudicator's VERIFIED
    citation rungs threaded as extra OR-sources per channel
    (``adjudicated_sources``: ``{uf_id: {"resource": [rung, ...],
    "verb": [rung, ...]}}`` — each stamps an ``adjudicated:<rung>``
    evidence tag; the verb channel is the b57-seg2-iter ruling, its
    citations family-matched by the adjudicator's verifier). The bar is
    UNCHANGED; confidence and evidence are only ever written by Law C —
    the adjudicator itself NEVER touches ``name_confidence``. Idempotent
    over an unchanged board (laws A/B are stable fixed points); no-ops
    (telemetry-only) when the naming contract or the UF name laws are
    switched off."""
    tele: dict[str, Any] = {}
    if not (naming_contract_enabled() and uf_name_laws_enabled()):
        tele["skipped"] = "naming-laws-off"
        return tele
    vocab = load_naming_vocab()
    flow_name_by_id, flow_origin_by_id, flow_by_id = _uf_flow_maps(flows)
    routes_index = list(routes_index) if routes_index is not None else None
    nav_labels = nav_labels_for_pfs(
        product_features, product_strings, routes_index)
    nav_label_sets = (
        nav_label_sets_for_pfs(product_features, product_strings, routes_index)
        if uf_rung_sources_v2_enabled() else {}
    )
    pf_by_slug = {
        str(getattr(pf, "name", "") or ""): pf for pf in product_features
    }
    _authored: Mapping[str, Iterable[str]] = _with_cli_declared(
        uf_authored_names, user_flows)
    _apply_uf_name_laws(
        user_flows, pf_by_slug, vocab, flow_name_by_id, tele,
        authored_ids={str(k) for k in _authored.keys()},
        keeper_on=keeper_on,
        nav_labels=nav_labels,
        flow_origin_by_id=flow_origin_by_id,
        flow_by_id=flow_by_id,
        nav_label_sets=nav_label_sets,
        routes_index=routes_index,
        repo_root=repo_root,
        adjudicated_sources=adjudicated_sources,
        # fixb130 item (6) — this seam is NOT the primary naming pass, so the
        # fixb129 narrowed-normal rubric may only demote here.
        primary_pass=False,
        # fixb145 — True ONLY from the 6.7e site: the lane-2 conversion runs
        # here, on the post-adjudicator state (Channel-A kill).
        post_adjudicator=post_adjudicator,
    )
    # ── fixb138 / NS-43b — a VERBLESS journey name never ships 'high' ─────
    # Warden §43 exhibit: umami UF-025 'Pixel share' sits at HIGH on
    # ['structural-route', 'resource:route'] — no verb:* stamp anywhere.
    #
    # ROOT CAUSE (the base rubric, ~line 5745):
    #     base_verb = (lead in mfams) or (lead is None and len(mfams) >= 1)
    # The ``lead is None`` arm exists so a GENERIC verb lead ('Manage',
    # 'Overview' — in no CRUD family) is grounded by any member action:
    # it abstracts, it does not over-claim a specific verb. But ``lead is
    # None`` is ALSO what a name with NO VERB AT ALL returns ('Pixel'),
    # so the arm cannot tell "generic verb" from "noun". Both land on
    # base_verb=True, which is why the row wears high while carrying only
    # the coarse 'structural-route' stamp that base_res∧base_verb mints.
    #
    # Both halves ride ONE guard — a row that already carries a verb:*
    # stamp is out of scope for either, which is simultaneously the
    # earned-high guard (Half 1) and the double-stamp guard (Half 2).
    #
    # Half 1  NOUN-LED (positively proven) ∧ no verb stamp ∧ high
    #         ⇒ demote to medium.
    # Half 2  verb-led (table corroboration) ∧ no verb stamp
    #         ⇒ stamp 'verb:name-lead'. Evidence honesty ONLY — the grade
    #         is never touched: these rows ARE verb-led, their high is
    #         correct, it was merely under-evidenced. Measured on umami:
    #         7 of the 8 unstamped highs are this class.
    #
    # ASYMMETRY, and it is the whole design. The verb table is a 131-word
    # CORROBORATION set, so it may only ever short-circuit TO verb-led; a
    # miss asserts nothing. Round 2's first cut read the table's
    # complement as proof of verblessness and a cold triage census over
    # 52 boards caught it firing 126 times, 100 of them (79%) on names
    # whose lead is plainly a verb the table just does not carry
    # (authenticate, deploy, navigate, handle, initialize, chat ...) —
    # the exact inversion W1/C-A was written to repair. So verblessness
    # now carries its OWN positive proof: the lead token IS the row's own
    # resource noun, a claim the row makes about itself. 'Pixel share'
    # leads with its own resource ('pixel', PF 'Pixels') and is demoted;
    # 'Authenticate With SSO' leads with nobody's resource noun and is
    # protected whether or not the table knows the word.
    #
    # SPLIT FLAGS (ruling on the census). The two halves ship on opposite
    # defaults, so they carry separate switches:
    #   WYSTAN_VERB_NAME_LEAD_STAMP  Half 2 — default ON (pack #40).
    #       Corroboration-only, grade-INERT, 2136 stamps world-wide.
    #   WYSTAN_VERBLESS_NO_HIGH      Half 1 — default OFF indefinitely.
    #       Armed mechanism, census banked: 20 world hits at 8 correct is
    #       a net honesty LOSS on an honesty lane. Kept armed (and watched
    #       eval-side as a TRACK detector) rather than deleted.
    # The SHORT-CIRCUIT is shared and must stay shared: a verb-led row is
    # out of the demote lane's scope even when the stamp lane is OFF, so
    # killing the stamp can never widen the demote.
    #
    # Both gated on the B40 rung flag as well: with rungs OFF the engine
    # writes no name_evidence at all, so 'no verb stamp' is not an
    # observation but a VACUUM — it would read true for every row and
    # demote every noun-led high on a channel that is switched off. A
    # predicate whose input channel is dark abstains.
    _stamp_on = verb_name_lead_stamp_enabled()
    _demote_on = verbless_no_high_enabled()
    if (_stamp_on or _demote_on) and name_evidence_rungs_enabled():
        _vsets = r5_vocab_sets(vocab)
        _verbless_demoted: list[str] = []
        _lead_stamped: list[str] = []
        for uf in user_flows:
            if _has_verb_stamp(getattr(uf, "name_evidence", None)):
                continue
            if _verb_led_name(str(getattr(uf, "name", "") or ""), _vsets):
                # verb-led: the demote lane may never touch it, stamped or
                # not — the short-circuit is unconditional.
                if _stamp_on:
                    uf.name_evidence = [
                        *(getattr(uf, "name_evidence", None) or ()),
                        VERB_NAME_LEAD_EVIDENCE,
                    ]
                    _lead_stamped.append(str(getattr(uf, "id", "") or ""))
            elif (_demote_on
                    and str(getattr(uf, "name_confidence", "") or "") == "high"
                    and _resource_noun_lead(uf, pf_by_slug, vocab)):
                uf.name_confidence = "medium"
                _verbless_demoted.append(str(getattr(uf, "id", "") or ""))
        # Emitted ONLY when non-empty, so a board the pass does not move
        # keeps a byte-identical telemetry block.
        if _verbless_demoted:
            tele["verbless_no_high"] = sorted(_verbless_demoted)
        if _lead_stamped:
            tele["verb_name_lead_stamped"] = sorted(_lead_stamped)
    return tele
