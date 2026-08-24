"""Stage 6.997a — invariant **I-EXISTS**: every ``member_flow_ids`` entry
resolves to a live ``flows[].uuid`` (B102).

THE BUG (VERIFIED on fresh keyed boards, both hands)
====================================================
``apply_flow_grain`` (T3 containment / T4 fanout — ``flow_grain.py:299``,
called from ``stage_6_7_user_flows.py:1637``) folds a victim flow into a
survivor: the survivor unions the victim's ``paths`` / ``line_ranges`` and
records the victim uuid in ``merged_from`` (``flow_grain.py:291-296``),
then the TOP-LEVEL store is reshaped (``flows[:] = plan.survivors(flows)``).

The reshape touches only the list it is handed (``bipartite.flows``). The
legacy containment view (``developer_features[].flows[]``) keeps the victim
rows — documenso: 736 top-level uuids vs 862 in the union, i.e. **126
containment-only victims**. Journey minters that run after the 6.7 mint and
read the containment view therefore mint ``member_flow_ids`` entries whose
uuid is absent from ``flows[]``.

The symptom is silent, because every member-derived consumer skips what it
cannot resolve (``stage_6_97b_uf_loc.py:158`` ``if fl is None: continue``;
``stage_6_97d_uf_metrics.py:131``): the row keeps ``member_count>0`` and
renders ``loc=0`` — a HOLLOW row. Named exhibits (fresh keyed, 2026-08-04):

* documenso ON — ``UF-041`` 'Manage direct template' (mc=2, loc=0): both
  members are victims; ``582ecf38…`` folded into ``6019110a…``
  'sign-document-flow', ``bd7e66cb…`` into ``721c0f94…`` 'multisign-page-flow'.
* documenso ON — ``UF-L-92a08861d6`` 'Browse embed', ``UF-L-a44419e313``
  'Create embed', ``UF-L-6fe2053c8f`` 'Manage embed' (all mc>0, loc=0).
* infisical ON — ``UF-046`` 'Configure tokens and auth methods',
  name_confidence=**high**, mc=1, loc=0: its only member ``58d8a40b…``
  folded into ``01cb41b0…`` 'manage-email-domain-flow'.

Scale (fresh keyed): infisical ON 143 dangling / 49 rows (== validator I5's
49), OFF 164 / 34; documenso ON 9 / 4, OFF 3 / 1; plane ON 7 / 7. Standing
on BOTH hands ⇒ not a flag artifact.

WHY FLAGLESS
============
This restores an ALREADY-CONTRACTED invariant rather than adding behavior:
``eval/validate_scan.py:1767-1769`` has long failed the board with
``"{n}/{m} member ids dangling"`` (**I5**). A dangling member id is not a
product decision — it is a broken ``(file,line) -> flow -> UF -> PF``
reverse-lookup, the "lines are coordinates" contract. Precedent: B101's
``and not uf_suppressed`` guard shipped flagless on the same grounds.
Inertness keeps the blast radius honest: a board with ZERO dangling members
returns ``None`` before any mutation, so no ``scan_meta`` key appears and
the emission stays byte-identical (the B84 inertness precedent).

THE LAW (deterministic, no vocabulary, no LLM)
==============================================
Per row, in emission order, over ``member_flow_ids`` in list order:

1. member resolves in ``flows[]`` -> KEEP (de-duplicated, first occurrence
   wins so ordering is stable).
2. member does NOT resolve -> follow the ``merged_from`` lineage to its
   surviving flow (transitively; depth-capped and cycle-guarded), then:
   a. no lineage at all            -> DROP  (``dropped_untraceable``)
   b. survivor already in this row -> DROP  (``collapsed_onto_survivor``)
   c. survivor claimed by ANOTHER row -> DROP (``dropped_owned_elsewhere``)
   d. otherwise                    -> ADOPT (``remapped``)

Rung (c) is deliberate and self-contained. UF member lists are strictly
disjoint in the emitted world (measured: 0 flows claimed by 2+ UFs on
documenso ON and OFF) and Stage 6.997 ``reconcile_member_disjoint`` enforces
that as I-DISJOINT. Adopting a survivor that another row already owns would
mint the first-ever double claim and DOUBLE-COUNT its LOC across two
journeys. Deferring that to B84's pass instead would silently couple this
bug-fix to B84's kill-switch, so the guard lives here.

Semantics of a DROP: the victim's coordinates are NOT lost — ``_union_into``
already folded them into the survivor, which some row owns (rung c) or which
is emitted unowned. The row honestly stops claiming material it no longer
holds; ``member_count`` is resynced so ``mc``/``loc`` agree.

CONSERVATION — the would-empty abstain
======================================
If applying the law would leave a previously non-empty row with ZERO
members, the row is RESTORED untouched and counted in
``rows_abstained_would_empty``. Whole-UF disappearance on an untouched repo
blocks NOW (the B33 conservation law), so this pass never dissolves a
journey; it is a pointer repair, not a journey judge. Measured 0 on
documenso ON/OFF and plane ON — the rung is a guard, not a live path.

THE REVERSE POINTER — I14 (fixb103)
===================================
``member_flow_ids`` is only one half of the join; ``flows[].user_flow_id``
is the other, and validator **I14** contracts that it resolve to a live UF.
The engine already owns that law — ``emission_integrity``'s Pass 3
``_rewrite_flow_backpointers`` re-derives every backpointer from the FINAL
membership (first owning UF in emission order wins; an unowned flow gets
``None``) — but it runs at phase_finalize:3096, and SIX membership-moving
passes run after it: the 6.7e adjudicator, ``uf_cases_split``,
``spray_absorption``, 6.99b ``post_uf_rehome``, this pass, and the
container rehomes. Two of them (``spray_absorption``, ``uf_cases_split``)
carry their OWN "I14 — repoint, never dangle" hook; the rest do not.

MEASURED (fresh keyed rebattery boards, 2026-08-04) — the residue is
entirely post-3096, and it is entirely REPOINTABLE:

===================  ==========  =========================  =====================
board                I14 stale   of which resolvable to a   backpointer ``None``
                                 live UF that LISTS them    on a LISTED flow
===================  ==========  =========================  =====================
infisical ON                222                    222/222                     45
infisical OFF                45                      45/45                     32
documenso ON                  1                        1/1                      1
documenso OFF                 3                        3/3                      2
===================  ==========  =========================  =====================

Zero rows in ANY hand needed a null (``points-at-live-UF-that-does-not-
list-them`` measured 0 across all four): the emitted world is a pure
re-point. At the 07-naming_contract input capture — i.e. immediately after
Pass 3 — the same board reads 0/0/0, which pins the whole residue to the
window this seam sits in.

:func:`reconcile_flow_backpointers` re-runs the EXISTING law (it imports
``emission_integrity``'s own ``_flow_key`` so identity can never drift into
a second spelling). Flagless for the same reason the member repair is: it
restores a contracted invariant, not a product decision. Inert by
construction — a board whose backpointers already agree with membership
returns ``None`` and writes nothing.

SEAM OF THE BACKPOINTER PASS — deliberately NOT inside
:func:`run_uf_member_exists`. Stage 6.997 ``reconcile_member_disjoint``
(B84) runs immediately after the member repair, elects an owner per
double-claimed uuid, and its election READS the current back-ref ("the
flow's own back-ref if it is a claimer, else the emission-first claimer").
Re-deriving backpointers before it would rewrite B84's own input — 80
double-claim uuids on infisical ON, 141 OFF — and silently move an
ownership decision this sprint was not asked to touch. So the
re-derivation is wired AFTER B84 instead, where it also picks up B84's own
membership changes (16 dissolved rows, 80-235 refs removed per hand).

SEAM
====
Stage 6.997a, immediately BEFORE ``reconcile_member_disjoint`` and therefore
before 6.998 metrics-recompute, 6.97b ``uf_loc``, 6.97c ``flow_loc``, 6.97d
``uf_metrics`` and terminal classification — all of which run over the FINAL
membership and so recompute NATURALLY off the repaired rows (the B85/B76
seam doctrine; no in-pass LOC recompute is needed or wanted).
"""

from __future__ import annotations

import os
from typing import Any

#: Depth cap for victim -> survivor chain walking. A fold chain deeper than
#: this is pathological; the walk gives up and the member is accounted as
#: untraceable rather than looping.
_MAX_CHAIN_DEPTH = 8

#: fixb114 / P12-M2 — the COORDINATE lineage rung (default OFF, armed).
COORD_LINEAGE_ENV_FLAG = "WYSTAN_UF_MEMBER_COORD_LINEAGE"


def coord_lineage_enabled() -> bool:
    """fixb114 — arm the coordinate-lineage rung + its per-row abstain
    accounting. Unset (≡ ``"0"``) / ``0`` / ``false`` / ``False`` / empty
    leaves the pass exactly as B102 shipped it ⇒ byte-identical."""
    return os.environ.get(COORD_LINEAGE_ENV_FLAG, "1").strip() not in {
        "0", "false", "False", "",
    }


def _uid(uf: Any) -> str:
    return str(getattr(uf, "id", None) or getattr(uf, "uuid", None) or "")


def build_survivor_map(flows: Any) -> dict[str, str]:
    """``victim uuid -> survivor uuid`` from ``flows[].merged_from``.

    Deterministic on ambiguity: if two survivors both claim a victim, the
    lexicographically lowest survivor uuid wins (set/dict iteration order
    is never allowed to decide an output — the determinism-gate trap).
    """
    survivor_map: dict[str, str] = {}
    for fl in flows or ():
        u = getattr(fl, "uuid", None)
        if not u:
            continue
        us = str(u)
        for victim in (getattr(fl, "merged_from", None) or ()):
            vs = str(victim)
            if not vs or vs == us:
                continue
            cur = survivor_map.get(vs)
            if cur is None or us < cur:
                survivor_map[vs] = us
    return survivor_map


def resolve_survivor(
    victim: str,
    survivor_map: dict[str, str],
    live: set[str],
    max_depth: int = _MAX_CHAIN_DEPTH,
) -> str | None:
    """Walk ``victim`` to the live flow that absorbed it, or ``None``.

    Handles fold chains (a survivor later folded into another survivor) and
    is cycle-guarded, so a malformed lineage can never hang the pass.
    """
    seen: set[str] = set()
    cur = str(victim)
    for _ in range(max_depth):
        if cur in live:
            return cur
        if cur in seen:
            return None
        seen.add(cur)
        nxt = survivor_map.get(cur)
        if nxt is None:
            return None
        cur = nxt
    return cur if cur in live else None


# ─────────────────────────────────────────────────────────────────────────
# fixb114 / P12-M2 — the COORDINATE lineage rung
# ─────────────────────────────────────────────────────────────────────────
#
# WHAT THE CENSUS FOUND (FRESH KS60 world, 20 boards / 1359 journeys)
# ------------------------------------------------------------------
# 21 rows still read ``member_count > 0`` with ZERO resolvable members (49
# dangling refs; infisical 10 rows, core-redplanet 3, documenso 3, dokploy 2,
# better-auth 1, kan 1, tracecat 1). The first question was "why did those 49
# get past ``members_dropped_untraceable``?" — and the honest answer is that
# they did NOT get past it: the 21 rows are EXACTLY the
# ``rows_abstained_would_empty`` set (21/21 identity against
# ``abstained_row_ids`` on all seven boards). The would-empty conservation
# abstain above (B33 — never dissolve a journey) restores the row with its
# stale pointers intact, so the drop is never applied and ``member_count``
# keeps advertising material the row cannot show.
#
# WHY THE LINEAGE WALK MISSES THEM (the actual gap)
# -------------------------------------------------
# :func:`resolve_survivor` follows ``merged_from`` only. All 49 victims live
# in the LEGACY CONTAINMENT VIEW (``developer_features[].flows[]``) with full
# ``line_ranges`` — 49/49 found, every one carrying spans — and 48/49 carry
# an EMPTY ``merged_from``: they were never folded by ``apply_flow_grain``,
# so the fold ledger has nothing to say about them and rung (a) fires.
#
# But their MATERIAL is not lost, and measurably so: 15643 of 15643 span
# lines (100.0%, all seven boards) are already covered by a LIVE top-level
# flow, and every victim has a coordinate twin — 38/49 an EXACT span-set
# match, 11/49 a strict-superset container. So the correct lineage edge
# exists; it is written in coordinates instead of in ``merged_from``.
# ("Lines are coordinates" — the (file,line) -> flow reverse-lookup is the
# contract, so a coordinate identity is a lineage fact, not a heuristic.)
#
# THE RUNG (deterministic, no vocabulary, no names, no LLM)
# --------------------------------------------------------
# When ``merged_from`` yields nothing, look the victim up by its span set:
#   1. EXACT — a live flow with the identical ``{(path, start, end)}`` set
#      is the survivor (lowest uuid wins a tie: set iteration may never
#      decide an output).
#   2. UNIQUE CONTAINER — else, if EXACTLY ONE live flow's span set is a
#      strict superset of the victim's, that flow absorbed it. Two or more
#      candidates ⇒ ambiguous ⇒ NO survivor (the pass abstains rather than
#      guessing; measured: 1 member of 49 is ambiguous, dokploy UF-090).
#   3. A victim with no spans has no coordinates and therefore no claim —
#      it stays untraceable (the B45/B23-B31 "no coordinates, no row" law).
# Then rungs (b)/(c)/(d) of the existing law apply VERBATIM — which for this
# class means mostly rung (c): 33 of the 38 exact twins are already owned by
# ANOTHER journey, so the row honestly stops claiming a duplicate of someone
# else's material; only 5 twins are unowned and get ADOPTED, giving their
# rows real members and a real ``loc``.
#
# WHY THIS IS NOT A LOC FIX BY ANOTHER NAME — the refused shortcut
# ---------------------------------------------------------------
# The tempting move is to let ``uf_loc`` resolve members through the
# containment view and hand the hollow rows the victims' spans directly.
# That is REFUTED by the same 100.0% coverage number: those lines are
# already carried by live flows, so crediting them again double-counts
# exactly the amount the row was missing. The membership contract, not the
# LOC formula, is what is broken here (P12 §5 M2), and it is repaired here.
#
# FLAG (not flagless, unlike B102 itself)
# ---------------------------------------
# B102 shipped flagless because a dangling id violates an ALREADY-CONTRACTED
# invariant (validator I5). This rung is different in kind: adopting a
# coordinate twin CHANGES membership — ``member_flow_ids`` / ``member_count``
# / the derived ``loc`` / the I14 backpointer all move on the board — and a
# membership decision is a product decision (the B112 ruling, 2026-08-05:
# "an output change = a flag law"). ``WYSTAN_UF_MEMBER_COORD_LINEAGE`` unset
# ⇒ every branch below is skipped and the pass behaves exactly as B102
# shipped it.


def _span_key(flow: Any) -> frozenset[tuple[str, int, int]]:
    """The flow's coordinate identity — its ``{(path, start, end)}`` set.
    Empty when the flow carries no resolved ranges (⇒ no claim)."""
    out: set[tuple[str, int, int]] = set()
    for rec in (getattr(flow, "line_ranges", None) or ()):
        p = str(getattr(rec, "path", "") or "")
        s = int(getattr(rec, "start_line", 0) or 0)
        e = int(getattr(rec, "end_line", 0) or 0)
        if p and s and e >= s:
            out.add((p, s, e))
    return frozenset(out)


def build_coord_index(
    flows: Any,
) -> tuple[dict[frozenset[tuple[str, int, int]], str],
           list[tuple[frozenset[tuple[str, int, int]], str]]]:
    """``(exact index, container list)`` over the LIVE flows.

    The exact index maps a span set to the lowest-uuid live flow carrying
    it; the container list is the same (span set, uuid) pairs sorted by
    uuid, walked for the strict-superset rung. Deterministic: ties and scan
    order are both decided by the uuid string, never by set iteration.
    """
    exact: dict[frozenset[tuple[str, int, int]], str] = {}
    pairs: list[tuple[frozenset[tuple[str, int, int]], str]] = []
    for fl in (flows or ()):
        u = getattr(fl, "uuid", None)
        if not u:
            continue
        key = _span_key(fl)
        if not key:
            continue
        us = str(u)
        pairs.append((key, us))
        cur = exact.get(key)
        if cur is None or us < cur:
            exact[key] = us
    pairs.sort(key=lambda kv: kv[1])
    return exact, pairs


def resolve_by_coordinates(
    victim: Any,
    exact: dict[frozenset[tuple[str, int, int]], str],
    containers: list[tuple[frozenset[tuple[str, int, int]], str]],
) -> str | None:
    """The coordinate lineage edge for one victim flow object, or ``None``.

    Rung 1 exact span-set identity; rung 2 the UNIQUE strict-superset
    container. Ambiguity (2+ containers) and spanlessness both return
    ``None`` — this rung never guesses.
    """
    key = _span_key(victim)
    if not key:
        return None
    hit = exact.get(key)
    if hit is not None:
        return hit
    found: str | None = None
    for cand_key, uid in containers:
        if key < cand_key:
            if found is not None:
                return None  # ambiguous — two live flows contain it
            found = uid
    return found


# ─────────────────────────────────────────────────────────────────────────
# fixb116 / HOLD-№26 blocker 3 — the ADOPT PLAUSIBILITY conjunct
# ─────────────────────────────────────────────────────────────────────────
#
# WHAT THE PROOF PAIR SHOWED (infisical, KS60 + the 6-flag convoy)
# ----------------------------------------------------------------
# infisical is the one clean pair in the c9 battery: BOTH hands enter this
# pass with an IDENTICAL pre-repair membership (``member_count_before`` 2974
# / ``survivor_map_size`` 1128 on both), so the ON-minus-OFF membership diff
# IS the coordinate rung's effect, exactly. Measured: **6 adopted refs over
# 4 rows** (and 9 dropped refs, which this conjunct does not touch):
#
# ====================  ===============================  ==========
# row (PF)              adopted survivor                 verdict
# ====================  ===============================  ==========
# UF-180 secret-folder  view-secret-dependency-tree      plausible
# UF-184 secret-folder  register-certificate-authority   IMPLAUSIBLE
# UF-184 secret-folder  configure-certificate-authority- IMPLAUSIBLE
#                       routing
# UF-224 aws-parameter- manage-audit-logs                IMPLAUSIBLE
#        store-…-page
# UF-224 aws-parameter- check-secret-access              plausible
#        store-…-page
# UF-L-a55da9a8be       register-admin                   plausible
#        org-admin
# ====================  ===============================  ==========
#
# The operator's exhibit: UF-184 'Organize secrets into folders' rendered
# loc=145 of CERTIFICATE-AUTHORITY router code. A coordinate twin is a
# lineage FACT about where the lines went, but "these lines are yours" is a
# separate claim, and a span-set identity alone never made it.
#
# WHY THE OBVIOUS RULER IS REFUTED (measured, not reasoned)
# ---------------------------------------------------------
# The first candidate was the validator's own I15 attach ruler (PF-scope
# overlap, floor 0.34 — ``journey_lattice._I15_ATTACH_FLOOR``). It is
# REFUTED by its own anti-case: on this board it scores **0.000 for the
# GOOD adopt too** (UF-L-a55da9a8be's ``register-admin-flow`` has 68 files,
# 0 of them inside ``org-admin``'s 3-file scope). A conjunct built on it
# would have killed all 6 refs, i.e. destroyed the M2 repair it is meant to
# discipline. PF-scope affinity cannot separate this class.
#
# THE RULER THAT DOES (existing mechanisms, no vocabulary, no prose)
# ------------------------------------------------------------------
# Token affinity between two CODE-DERIVED identities, over the engine's own
# ``structural_stoplist`` (spine-anchor-vocab.yaml — the same data
# ``mega_pf_nav_rehome._s5a_stoplist`` reads, and the same "tok0 = shares
# zero content tokens" line the B78 Seg D vacuum census already ranks on):
#
# * ROW identity  = tokens(``uf.resource``) ∪ tokens(PF name / anchor
#   terminal).  ``resource`` is the 6.7 mint's deterministic noun and the PF
#   key is an anchor slug — BOTH code-derived. ``uf.name`` is deliberately
#   NOT read: it is LLM prose, and English function words ("and", "into")
#   would bridge unrelated domains.
# * SURVIVOR identity = tokens(``flow.name``) minus the canonical trailing
#   ``-flow`` suffix (the engine's own flow-naming contract, ``manage-X-
#   flow`` — a structural fact, not a stopword).
# * PATH-OWNERSHIP disjunct = the survivor's files intersect the row's PF
#   scope (``union(pf.paths, member devs' paths)`` — the validator I15
#   numerator, file identity so no token can bridge). Measured 0/6 on this
#   pair: it admits nothing here, it exists so a differently-NAMED flow
#   sitting literally inside the PF's own files is never refused.
#
# Verdict on the 6: blocks exactly the 3 implausible refs, keeps exactly
# the 3 plausible ones. 6/6.
#
# SCOPE — the ADOPT rung ONLY
# ---------------------------
# The conjunct gates rung (d) and ONLY when the survivor came from the
# COORDINATE rung. It never gates rungs (a)/(b)/(c) and never gates a
# ``merged_from`` lineage: those are DROPS (the row stops claiming material
# it does not hold) or exact fold-ledger facts, and 52 of infisical's
# coordinate resolutions end in a drop. Disciplining a drop would resurrect
# the hollow rows this family exists to kill.
#
# A refused adopt falls through to ``dropped_implausible`` and, if it leaves
# the row empty, into the SAME would-empty conservation abstain as any other
# unresolvable row (B33) — accounted, never silent. On this pair that returns
# UF-184 to a hollow-but-ACCOUNTED row: the honest state, since its only
# claim on live material was the cert-authority mis-adopt.
#
# FLAG: rides ``WYSTAN_UF_MEMBER_COORD_LINEAGE`` — it constrains a branch
# that flag introduced, so the OFF hand is byte-identical by construction and
# this is a bug-fix to an armed flag, not a new mechanism (the fixb116 rule).


def _affinity_stoplist() -> frozenset[str]:
    """The engine's canonical structural / plumbing vocabulary (data, not
    code — ``spine-anchor-vocab.yaml``). Same source of truth
    ``mega_pf_nav_rehome._s5a_stoplist`` reads."""
    from wystan.pipeline_v2.spine_anchors import load_spine_vocab

    return frozenset(
        str(s) for s in (load_spine_vocab().get("structural_stoplist") or ())
    )


def _content_tokens(text: Any, stoplist: frozenset[str]) -> set[str]:
    """Lower-cased content words of an identifier — camel/`-`/`_`/space
    split, structural stoplist removed. Deterministic and order-free."""
    import re as _re

    spaced = _re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(text or ""))
    return {
        w for w in (
            t.lower() for t in _re.split(r"[^A-Za-z0-9]+", spaced) if t
        ) if w and w not in stoplist
    }


#: The engine's flow-naming contract suffix (``rule-flow-naming``:
#: ``manage-X-flow``). Structural, present on every generated flow name —
#: stripped so it can never bridge two identities.
_FLOW_NAME_SUFFIX = "flow"


def flow_identity_tokens(flow: Any, stoplist: frozenset[str]) -> set[str]:
    """Content tokens of a live flow's NAME, canonical ``-flow`` suffix
    removed."""
    toks = _content_tokens(getattr(flow, "name", None), stoplist)
    toks.discard(_FLOW_NAME_SUFFIX)
    return toks


def row_identity_tokens(
    uf: Any, pf_identity: str, stoplist: frozenset[str],
) -> set[str]:
    """Content tokens of a journey row's CODE-DERIVED identity:
    ``uf.resource`` (the 6.7 mint's deterministic noun) plus its product
    feature's key/anchor terminal. ``uf.name`` is deliberately excluded —
    LLM prose bridges on function words."""
    toks = _content_tokens(getattr(uf, "resource", None), stoplist)
    toks |= _content_tokens(pf_identity, stoplist)
    return toks


def flow_files(flow: Any) -> set[str]:
    """The validator's ``_spine_flow_files`` ruler — ``paths`` first, the
    entry-point file as the fallback."""
    ps = [str(p) for p in (getattr(flow, "paths", None) or ()) if p]
    if not ps:
        ep = getattr(flow, "entry_point_file", None)
        ps = [str(ep)] if ep else []
    return set(ps)


def adopt_is_judgeable(
    survivor: Any,
    row_tokens: set[str],
    pf_scope: set[str],
    stoplist: frozenset[str],
) -> bool:
    """Can this adopt be ruled on at all? Both sides must carry an identity
    signal — the row a code-derived token set or a PF scope, the survivor a
    name or files. When either side is mute the pass does NOT rule: a
    refusal invented from absent data is a guess, and this rung never
    guesses (the caller counts these as ``adopts_unjudged`` and lets the
    adopt through, preserving the pre-conjunct behavior exactly)."""
    if not row_tokens and not pf_scope:
        return False
    return bool(flow_identity_tokens(survivor, stoplist) or flow_files(survivor))


def adopt_is_plausible(
    survivor: Any,
    row_tokens: set[str],
    pf_scope: set[str],
    stoplist: frozenset[str],
) -> bool:
    """Is adopting ``survivor`` into a row with ``row_tokens`` / ``pf_scope``
    a plausible attribution? TOKEN affinity (shared content token between the
    survivor's flow name and the row's code-derived identity) OR PATH
    ownership (the survivor's files intersect the row's PF scope). Neither ⇒
    the coordinate twin is a lineage fact about foreign material and the
    adopt is refused."""
    if row_tokens and (flow_identity_tokens(survivor, stoplist) & row_tokens):
        return True
    return bool(pf_scope and (flow_files(survivor) & pf_scope))


def build_pf_affinity_index(
    product_features: Any, features: Any,
) -> tuple[dict[str, str], dict[str, set[str]]]:
    """``(pf key -> identity string, pf key -> scope files)``.

    Identity = the PF's own key/name plus its anchor's terminal segment
    (``_core_identity``'s rail, spelled here without importing the mega
    module). Scope = ``union(pf.paths, member devs' paths)`` — the validator
    I15 numerator, verbatim. Keyed by BOTH ``name`` and ``product_feature_id``
    so a row's home resolves whichever spelling it carries.
    """
    ident: dict[str, str] = {}
    scope: dict[str, set[str]] = {}
    dev_paths: dict[str, set[str]] = {}
    for d in (features or ()):
        if str(getattr(d, "layer", "developer") or "developer") == "product":
            continue
        pid = str(getattr(d, "product_feature_id", "") or "")
        if not pid:
            continue
        dev_paths.setdefault(pid, set()).update(
            str(p) for p in (getattr(d, "paths", None) or ()) if p)
    for pf in (product_features or ()):
        name = str(getattr(pf, "name", "") or "")
        keys = [k for k in (
            name, str(getattr(pf, "product_feature_id", "") or ""),
            str(getattr(pf, "id", "") or ""),
        ) if k]
        if not keys:
            continue
        anchor = str(getattr(pf, "anchor_id", "") or "")
        terminal = anchor.split(":", 1)[1].rsplit("/", 1)[-1] if ":" in anchor else ""
        sc = {str(p) for p in (getattr(pf, "paths", None) or ()) if p}
        for k in keys:
            sc |= dev_paths.get(k, set())
        for k in keys:
            ident.setdefault(k, f"{name} {terminal}".strip())
            scope.setdefault(k, set()).update(sc)
    return ident, scope


def _containment_index(containment_flows: Any) -> dict[str, Any]:
    """``uuid -> flow object`` over the legacy containment view, so a victim
    id that is absent from the top-level store can still be looked up for
    its coordinates. First occurrence wins (emission order)."""
    out: dict[str, Any] = {}
    for fl in (containment_flows or ()):
        u = getattr(fl, "uuid", None)
        if u:
            out.setdefault(str(u), fl)
    return out


def reconcile_member_exists(
    user_flows: list[Any],
    flows: Any,
    containment_flows: Any = None,
    product_features: Any = None,
    features: Any = None,
) -> dict[str, Any] | None:
    """Repair dangling ``member_flow_ids`` in place. Returns ``None`` when
    every member already resolves (inertness — nothing read or written, so
    the caller stamps no ``scan_meta`` key and the board stays
    byte-identical), else deterministic telemetry.
    """
    live: set[str] = {
        str(u) for u in (
            getattr(fl, "uuid", None) for fl in (flows or ())
        ) if u
    }

    # Cheap pre-scan: is anything actually dangling? (inertness gate)
    if not any(
        str(m) not in live
        for uf in user_flows
        for m in (getattr(uf, "member_flow_ids", None) or ())
    ):
        return None

    survivor_map = build_survivor_map(flows)

    # fixb114 — the coordinate lineage rung (armed-only). Built ONCE; the
    # containment view is read-only here (we borrow a victim's coordinates,
    # we never re-admit it into the store).
    coord_on = coord_lineage_enabled()
    coord_exact: dict[frozenset[tuple[str, int, int]], str] = {}
    coord_containers: list[tuple[frozenset[tuple[str, int, int]], str]] = []
    victims_by_uuid: dict[str, Any] = {}
    live_by_uuid: dict[str, Any] = {}
    pf_ident: dict[str, str] = {}
    pf_scope: dict[str, set[str]] = {}
    stoplist: frozenset[str] = frozenset()
    if coord_on:
        coord_exact, coord_containers = build_coord_index(flows)
        victims_by_uuid = _containment_index(containment_flows)
        # fixb116 — the adopt-plausibility conjunct's read-only indices.
        live_by_uuid = {
            str(getattr(fl, "uuid", "") or ""): fl for fl in (flows or ())
            if getattr(fl, "uuid", None)
        }
        stoplist = _affinity_stoplist()
        pf_ident, pf_scope = build_pf_affinity_index(
            product_features, features)

    # Ownership over the CURRENT (pre-repair) membership, emission order:
    # first claimer of a live id owns it. Adoptions extend this map as the
    # pass walks rows, so two rows can never adopt the same survivor.
    owner: dict[str, str] = {}
    for uf in user_flows:
        uid = _uid(uf)
        for m in (getattr(uf, "member_flow_ids", None) or ()):
            ms = str(m)
            if ms in live:
                owner.setdefault(ms, uid)

    remapped = 0
    collapsed = 0
    dropped_untraceable = 0
    dropped_owned_elsewhere = 0
    coord_resolved = 0
    dropped_implausible = 0
    adopts_unjudged = 0
    implausible_exhibits: list[dict[str, Any]] = []
    rows_touched = 0
    rows_abstained = 0
    abstained_ids: list[str] = []
    abstained_rows: list[dict[str, Any]] = []
    mc_before = 0
    mc_after = 0
    exhibits: list[str] = []

    for uf in user_flows:
        uid = _uid(uf)
        members = list(getattr(uf, "member_flow_ids", None) or [])
        mc_before += len(members)
        if not members:
            continue

        kept: list[str] = []
        r_remap = r_collapse = r_untrace = r_owned = r_coord = 0
        r_implausible = r_unjudged = 0
        row_toks: set[str] | None = None
        row_scope: set[str] = set()
        if coord_on:
            home = str(getattr(uf, "product_feature_id", "") or "")
            row_toks = row_identity_tokens(
                uf, pf_ident.get(home, home), stoplist)
            row_scope = pf_scope.get(home, set())
        for m in members:
            ms = str(m)
            if ms in live:
                if ms not in kept:
                    kept.append(ms)
                continue
            survivor = resolve_survivor(ms, survivor_map, live)
            by_coord = False
            if survivor is None and coord_on:
                # No fold ledger — ask the coordinates. The victim object
                # lives on in the containment view with its line ranges.
                victim = victims_by_uuid.get(ms)
                if victim is not None:
                    survivor = resolve_by_coordinates(
                        victim, coord_exact, coord_containers)
                    if survivor is not None:
                        r_coord += 1
                        by_coord = True
            if survivor is None:
                r_untrace += 1
                continue
            if survivor in kept:
                r_collapse += 1
                continue
            held_by = owner.get(survivor)
            if held_by is not None and held_by != uid:
                r_owned += 1
                continue
            # fixb116 — the ADOPT plausibility conjunct. Gated to the
            # COORDINATE provenance only: a ``merged_from`` remap is an exact
            # fold-ledger fact and is never second-guessed, and the drop rungs
            # above are already past. A coordinate twin says WHERE the lines
            # went; it does not by itself say "these lines are yours".
            if by_coord:
                surv_flow = live_by_uuid.get(survivor)
                if surv_flow is None or not adopt_is_judgeable(
                        surv_flow, row_toks or set(), row_scope, stoplist):
                    r_unjudged += 1
                elif not adopt_is_plausible(
                        surv_flow, row_toks or set(), row_scope, stoplist):
                    r_implausible += 1
                    if len(implausible_exhibits) < 25:
                        implausible_exhibits.append({
                            "uf": uid,
                            "survivor": str(
                                getattr(surv_flow, "name", "") or survivor),
                            "home": str(
                                getattr(uf, "product_feature_id", "") or ""),
                        })
                    continue

            kept.append(survivor)
            owner.setdefault(survivor, uid)
            r_remap += 1

        changed = (r_remap or r_collapse or r_untrace or r_owned
                   or r_implausible)
        if not changed:
            mc_after += len(members)
            continue
        coord_resolved += r_coord

        # Conservation: never empty a row that had members (B33). The row
        # keeps its stale pointers and is ACCOUNTED — the I-EXISTS sentinel
        # reads the accounted set and stays silent on it ("absent from
        # flows[].uuid ∪ unresolvable-accounted"), so a deliberate
        # conservation abstain never masquerades as an unnoticed violation.
        if not kept:
            rows_abstained += 1
            abstained_ids.append(uid)
            mc_after += len(members)
            # fixb114 — the abstain is a RULING, so it must carry its
            # reasons. Without this the board shows a row advertising
            # member_count=N whose every pointer is stale, and the only
            # trace is an id in a list. "owned_elsewhere" says the row is a
            # duplicate of live material another journey holds;
            # "untraceable" says the material genuinely has no coordinates.
            if coord_on:
                abstained_rows.append({
                    "id": uid,
                    "member_count": len(members),
                    "coord_resolved": r_coord,
                    "owned_elsewhere": r_owned,
                    "collapsed": r_collapse,
                    "untraceable": r_untrace,
                    # fixb116 — a row whose only live claim was an
                    # IMPLAUSIBLE coordinate adopt abstains here. The reason
                    # must ride the ruling: "implausible" says the material
                    # exists but belongs to another domain (infisical UF-184
                    # cert-authority vs secret-folders), which is a different
                    # fact from "owned_elsewhere" / "untraceable".
                    "implausible": r_implausible,
                })
            dropped_implausible += r_implausible
            adopts_unjudged += r_unjudged
            continue

        uf.member_flow_ids = kept
        uf.member_count = len(kept)
        rows_touched += 1
        remapped += r_remap
        collapsed += r_collapse
        dropped_untraceable += r_untrace
        dropped_owned_elsewhere += r_owned
        dropped_implausible += r_implausible
        adopts_unjudged += r_unjudged
        mc_after += len(kept)
        if len(exhibits) < 25:
            exhibits.append(
                f"{uid}: {len(members)}->{len(kept)} members "
                f"(remapped={r_remap} collapsed={r_collapse} "
                f"untraceable={r_untrace} owned_elsewhere={r_owned}"
                + (f" implausible={r_implausible}" if r_implausible else "")
                + ")"
            )

    if not rows_touched and not rows_abstained:
        return None

    out: dict[str, Any] = {
        "rows_touched": rows_touched,
        "rows_abstained_would_empty": rows_abstained,
        "abstained_row_ids": sorted(abstained_ids),
        "members_remapped": remapped,
        "members_collapsed_onto_survivor": collapsed,
        "members_dropped_untraceable": dropped_untraceable,
        "members_dropped_owned_elsewhere": dropped_owned_elsewhere,
        "member_count_before": mc_before,
        "member_count_after": mc_after,
        "survivor_map_size": len(survivor_map),
        "exhibits": exhibits,
    }
    if coord_on:
        out["members_resolved_by_coordinates"] = coord_resolved
        out["coord_index_size"] = len(coord_exact)
        out["containment_index_size"] = len(victims_by_uuid)
        out["abstained_rows"] = sorted(
            abstained_rows, key=lambda r: str(r["id"]))
        # fixb116 — the adopt-plausibility ledger. A refused adopt is a
        # RULING about attribution, so it is named, counted and exhibited;
        # ``adopts_unjudged`` is the fail-open rung (survivor absent from the
        # live index — impossible at the live seam, honest if it ever fires).
        out["adopts_dropped_implausible"] = dropped_implausible
        out["adopts_unjudged"] = adopts_unjudged
        out["implausible_exhibits"] = sorted(
            implausible_exhibits,
            key=lambda r: (str(r["uf"]), str(r["survivor"])))
        out["pf_affinity_index_size"] = len(pf_ident)
    return out


def reconcile_flow_backpointers(
    user_flows: list[Any],
    flows: Any,
) -> dict[str, Any] | None:
    """I14 — re-derive ``flows[].user_flow_id`` from the CURRENT
    ``user_flows[].member_flow_ids`` ownership. Returns ``None`` when every
    backpointer already agrees (inertness ⇒ no scan_meta key ⇒ the board
    stays byte-identical), else deterministic telemetry.

    The law is ``emission_integrity._rewrite_flow_backpointers`` verbatim —
    first owning UF in emitted order wins; a flow no surviving UF lists gets
    ``None`` — and the flow identity comes from that module's own
    ``_flow_key`` so the two seams can never disagree about what a flow is.

    Ownership is read from the membership as the member repair LEFT it, so a
    member this pass detached stops being cited from the flow side too, and a
    survivor it adopted is claimed from both sides. Deterministic: emission
    order decides every tie; no set iteration reaches the output.
    """
    from wystan.pipeline_v2.emission_integrity import _flow_key

    owner: dict[str, str] = {}
    for uf in user_flows:
        uid = _uid(uf)
        if not uid:
            continue
        for mid in (getattr(uf, "member_flow_ids", None) or ()):
            owner.setdefault(str(mid), uid)

    rewritten = 0
    nulled = 0
    exhibits: list[str] = []
    pending: list[tuple[Any, str | None]] = []
    for fl in (flows or ()):
        new_id = owner.get(_flow_key(fl))
        old_id = getattr(fl, "user_flow_id", None)
        if new_id == old_id:
            continue
        pending.append((fl, new_id))
        if new_id is None:
            nulled += 1
        else:
            rewritten += 1
        if len(exhibits) < 25:
            exhibits.append(
                f"{_flow_key(fl)}: {old_id or 'null'} -> {new_id or 'null'}")

    if not pending:
        return None
    for fl, new_id in pending:
        fl.user_flow_id = new_id

    return {
        "backpointers_rewritten": rewritten,
        "backpointers_nulled": nulled,
        "owned_flow_ids": len(owner),
        "exhibits": exhibits,
    }


def run_uf_member_exists(
    user_flows: list[Any],
    flows: Any,
    containment_flows: Any = None,
    product_features: Any = None,
    features: Any = None,
) -> dict[str, Any] | None:
    """Engine adapter for the 6.997a seam. The B102 member repair itself is
    flagless (a bug-fix restoring the I5 contract) and inert on a clean
    board; the fixb114 coordinate-lineage rung that reads
    ``containment_flows`` is armed by
    ``WYSTAN_UF_MEMBER_COORD_LINEAGE`` and is skipped entirely when
    unset — as is the fixb116 adopt-plausibility conjunct that reads
    ``product_features`` / ``features`` (read-only, for the row's
    code-derived identity and its PF scope)."""
    return reconcile_member_exists(
        user_flows, flows, containment_flows, product_features, features)
