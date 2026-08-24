"""B84 — terminal member-disjoint reconciliation (Stage 6.997, flag-gated).

Forensics class: MEMBER DOUBLE-CLAIM (census 2026-07-22, byte-exact over
the world-37 cold corpus). After the last membership mutators
(``spray_absorption`` / ``uf_cases_split`` and the whole Layer-2 surgery
above them), a single ``flows[].uuid`` can still sit in the
``member_flow_ids`` of MORE THAN ONE ``user_flows[]`` row — 581 distinct
double-claimed flow uuids across 21 of 55 boards (cal.com 57 / linkwarden
96 / documenso 39 …), 739 redundant member instances. A flow is authored
once; two journeys both "containing" it is dup inflation — the
subset-twin pathology the journey layer never fully collapses (documenso
'View team' ⊇ 'View team settings'; typebot 'Manage repository' ⊂
'Manage forge repository').

Mechanism (probe canon: ``simulate.py`` digest
6b05949c784861be0aaa44d35dd7780ea1d0ceb8ee5bf1402f2038d17719682d):

  For each flow-uuid claimed by > 1 UF (member_flow_ids disjointness
  violation), pick ONE authoritative owner and strip the uuid from
  every other claimer:

    1. exactly_one — the flow's own back-ref ``flows[].user_flow_id``
       is AMONG the claimers → owner = the back-ref (the flow already
       names its home; 412/581).
    2. zero — a back-ref exists but is NOT a claimer (stale home;
       165/581) → owner = the first claimer in EMISSION order
       (``user_flows[]`` doc order); the back-ref is REPOINTED to it.
    3. no_backref — no uuid-keyed flow record / null back-ref (4/581) →
       owner = the first claimer in emission order; a flow record, if
       present, is repointed.

  ``member_count`` is re-synced to ``len(member_flow_ids)`` on every
  touched row (the mutator invariant; conservation:
  ``Σ member_count`` drops by exactly ``Σ (distinct_claimers − 1)`` ==
  refs stripped == 739).

CO-SHIP — terminal I7-drop. A UF the pass leaves memberless (its members
were all double-claimed and re-homed to owners) is a memberless twin of
already-claimed flows: it DISSOLVES, reusing the Stage-6.7d
``uf_dropped_memberless`` semantics (a code-less journey name is exactly
the 0-LOC defect the trustworthy-core mission forbids). 94 UFs across the
corpus (documenso 15, cal.com 27) — poimenno in ``dissolved_names``.
No route-backfill: a terminal loser's flows are, by construction,
already claimed by their owner (backfill would only re-mint the
double-claim). By construction a dissolved UF owns NO flow back-ref (it
would then be the exactly_one owner and keep the member), so the drop
strands nothing — asserted at runtime.

DEPENDENT METRICS — the seam is 6.997, immediately BEFORE Stage 6.998
metrics-recompute + Stage 6.97b/6.97c UF/flow LOC + terminal
classification (all of which run over the FINAL membership). Those
member-derived aggregates therefore recompute NATURALLY off the
reconciled rows — no in-pass recompute is needed (the B85/B76 seam
doctrine). This pass touches ONLY ``member_flow_ids`` / ``member_count``
and the repointed ``flows[].user_flow_id`` back-refs.

Invariant I-DISJOINT: after the pass every ``flows[].uuid`` appears in
``member_flow_ids`` of AT MOST ONE surviving UF — checked at runtime
(armed only) and pinned as a suite unit.

fixb119 M2 — LINEAGE ID-BOUND (FLAGLESS, rationale). Probe P15 showed:
``dissolved_ids`` and the per-member ``owner_id`` ARE COMPUTED here and
THROWN AWAY — only ``dissolved_names`` (cap 30) went into the return. So
exhibit ``UF-L-77f54626fe`` (infisical) had a NAME-ONLY tier, and
``landing_audit`` saw its death (``_REASON_UF_GONE``) but had no channel
to attribute it. Now we emit ``dissolved_ids`` +
``dissolved_into {loser_id: [survivor_id, …]}`` + ``dissolved_names_
truncated``.

WHY NO FLAG OF ITS OWN: this is a purely ADDITIVE extension of the
telemetry of the ALREADY existing ``scan_meta.member_disjoint_reconcile``
key, which is written exactly when, and only when, the pass does work.
There are no new computations, no new traversals, and NO board mutation
at all (``user_flows`` / ``flows`` / ``member_*`` are untouched by this
commit) — so a second flag would guard behaviour that does not exist and
would breed KS combinatorics. This code is still fully disabled by the
ALREADY present kill-switch ``WYSTAN_MEMBER_DISJOINT_RECONCILE=0`` (return
``None`` before any read ⇒ no key ⇒ the pre-B84 world byte-identical), as
is the inertness path "zero double-claim ⇒ ``None``". The precedent is the
flagless part of the M3d repair (e91ce47): an honest additive fix.

Kill-switch: ``WYSTAN_MEMBER_DISJOINT_RECONCILE`` (default **ON** since
the 2026-07-23 flip-pack №5, KEY_SCHEMA 38). Explicit ``0`` / ``false`` /
``off`` / ``no`` ⇒ :func:`run_member_disjoint_reconcile`
returns ``None`` BEFORE any read or mutation ⇒ the caller writes no
scan_meta key ⇒ byte-identical to the pre-B84 world (the KS 4-way gate).
A board with zero double-claims (RefApp) also returns ``None`` — nothing
was read or written (the inertness law). Appended to
``scan_result_cache.ENV_OUTPUT_FLAGS`` WITHOUT a KEY_SCHEMA bump (the
bump rides the separate flip commit per flip-protocol).

No LLM. No network. Deterministic (a pure function of ``user_flows[]``
doc order × the uuid-keyed flow back-refs).
"""

from __future__ import annotations

import os
from typing import Any, Iterable

__all__ = [
    "MEMBER_DISJOINT_RECONCILE_ENV",
    "member_disjoint_reconcile_enabled",
    "reconcile_member_disjoint",
    "run_member_disjoint_reconcile",
]

#: Kill-switch — default ON since flip-pack №5 (2026-07-23, KEY_SCHEMA 38;
#: B84). Unset ≡ explicit ``1``/``true`` (arms the pass); explicit ``0`` /
#: ``false`` / ``off`` / ``no`` keeps the pre-B84 world byte-identical.
MEMBER_DISJOINT_RECONCILE_ENV = "WYSTAN_MEMBER_DISJOINT_RECONCILE"

#: scan_meta size bound for the dissolved-name exhibit list (mirrors the
#: Stage-6.7d ``uf_dropped_names`` bound).
_DISSOLVED_NAMES_CAP = 30


def member_disjoint_reconcile_enabled() -> bool:
    """B84 — default **ON** since the 2026-07-23 flip-pack №5 flip
    (KEY_SCHEMA 38; keyed documenso 9 dissolved / conservation exact +
    keyless 10/10). Unset now arms the terminal reconciliation
    (unset ≡ explicit ``1``). Explicit ``0``/``false``/``off``/``no`` is the
    kill-switch forever (byte-identical to the pre-B84 world). The pre-flip
    truthy set ``{"1","true"}`` is preserved LITERALLY — only the
    ``os.environ.get`` default moved ``"0"`` -> ``"1"``."""
    return os.environ.get(
        MEMBER_DISJOINT_RECONCILE_ENV, "1"
    ).strip().lower() in {"1", "true"}


def _uid(obj: Any) -> str:
    """The row's stable scan id as a string ("UF-001")."""
    return str(getattr(obj, "id", "") or "")


def run_member_disjoint_reconcile(
    user_flows: list[Any],
    flows: Iterable[Any] = (),
) -> dict[str, Any] | None:
    """Flag-gated stage entry ``phase_finalize`` wires at Stage 6.997.

    OFF/unset ⇒ ``None`` BEFORE any read or mutation (the caller then
    writes no scan_meta key — the byte-identity law). A board with no
    double-claim ALSO returns ``None`` (inertness) so an armed clean
    board stays byte-identical to the OFF world.
    """
    if not member_disjoint_reconcile_enabled():
        return None
    # uuid-keyed back-ref map — mirrors the census pass-2 keying exactly
    # (a member id resolves to its home only through the flow's OWN uuid,
    # never the name id-form), so the engine reproduces the probe digest.
    flow_by_uuid: dict[str, Any] = {}
    for fl in flows or ():
        u = getattr(fl, "uuid", None)
        if u:
            flow_by_uuid.setdefault(str(u), fl)
    return reconcile_member_disjoint(user_flows, flow_by_uuid)


def _emission_claimers(user_flows: list[Any]) -> dict[str, list[Any]]:
    """``member_id -> [claimer UF, …]`` in EMISSION (doc) order, DISTINCT
    per UF (a UF listing a member twice claims it once)."""
    claimers: dict[str, list[Any]] = {}
    for uf in user_flows:
        seen_here: set[str] = set()
        for m in getattr(uf, "member_flow_ids", None) or []:
            ms = str(m)
            if ms in seen_here:
                continue
            seen_here.add(ms)
            claimers.setdefault(ms, []).append(uf)
    return claimers


def reconcile_member_disjoint(
    user_flows: list[Any],
    flow_by_uuid: dict[str, Any],
) -> dict[str, Any] | None:
    """Reconcile member_flow_ids disjointness in place. Returns ``None``
    when there is NO double-claim (nothing read or written — inertness),
    else deterministic telemetry.

    Only ever reached behind :func:`member_disjoint_reconcile_enabled`, so
    the OFF path performs zero work and the ON-but-clean path returns
    ``None`` (no scan_meta key) — both byte-identical to pre-B84.
    """
    claimers = _emission_claimers(user_flows)
    double_claims = {m: cs for m, cs in claimers.items() if len(cs) > 1}
    if not double_claims:
        return None

    mc_before = sum(
        len(getattr(uf, "member_flow_ids", None) or []) for uf in user_flows
    )

    owner_class = {"exactly_one": 0, "zero": 0, "no_backref": 0}
    refs_removed = 0
    repointed = 0
    losers_by_uf: dict[str, list[str]] = {}
    # fixb119 M2 — who TOOK the member from each loser. Computed in the
    # same pass (zero new traversals); makes the record ID-BOUND.
    owners_by_loser: dict[str, set[str]] = {}

    for m, cs in double_claims.items():
        claimer_ids = [_uid(uf) for uf in cs]
        fl = flow_by_uuid.get(m)
        backref = str(getattr(fl, "user_flow_id", "") or "") if fl else ""

        if backref and backref in claimer_ids:
            owner_id = backref
            owner_class["exactly_one"] += 1
        else:
            owner_id = claimer_ids[0]  # emission-first claimer
            owner_class["no_backref" if not backref else "zero"] += 1
            if fl is not None:
                # zero / no_backref with a real flow record: repoint the
                # stale back-ref to the new owner (I14 — never dangle).
                fl.user_flow_id = owner_id
                repointed += 1

        # strip the member id from every NON-owner claimer
        for uf in cs:
            if _uid(uf) == owner_id:
                continue
            mfi = getattr(uf, "member_flow_ids", None) or []
            kept = [x for x in mfi if str(x) != m]
            if len(kept) != len(mfi):
                uf.member_flow_ids = kept
                losers_by_uf.setdefault(_uid(uf), []).append(m)
                owners_by_loser.setdefault(_uid(uf), set()).add(owner_id)
                refs_removed += 1

    # re-sync member_count on every touched row + classify shrink vs dissolve
    dissolved_ids: set[str] = set()
    dissolved_names: list[str] = []
    ufs_shrunk = 0
    for uf in user_flows:
        uid = _uid(uf)
        if uid not in losers_by_uf:
            continue
        mfi = getattr(uf, "member_flow_ids", None) or []
        uf.member_count = len(mfi)
        if not mfi:
            # terminal I7-drop — a memberless twin of already-claimed flows
            dissolved_ids.add(uid)
            if len(dissolved_names) < _DISSOLVED_NAMES_CAP:
                dissolved_names.append(str(getattr(uf, "name", "") or ""))
        else:
            ufs_shrunk += 1

    if dissolved_ids:
        # no-dangle guard: a dissolved UF must own NO flow back-ref (it
        # would then be the exactly_one owner and keep the member). This
        # holds by construction; assert it before removing the rows.
        _assert_no_dangling_backref(flow_by_uuid, dissolved_ids)
        # fixb121 M6 — the self-report DUPLICATES the ``dissolved_ids``
        # telemetry below DELIBERATELY: only a fresh board reads telemetry,
        # while the registry catches the death at the moment of mutation, so
        # no future cap or key rename can push these 13 rows (the largest
        # basket of the 8-pair gate) back into ``unaccounted``. A row named
        # twice stays ONE ``id_bound`` — the baskets are mutually exclusive.
        from wystan.pipeline_v2.journey_lineage_audit import (
            report_journey_kill as _report_kill,
        )
        _report_kill(
            "member_disjoint_reconcile.reconcile_member_disjoint",
            sorted(dissolved_ids),
        )
        user_flows[:] = [u for u in user_flows if _uid(u) not in dissolved_ids]

    mc_after = sum(
        len(getattr(uf, "member_flow_ids", None) or []) for uf in user_flows
    )

    # Invariant I-DISJOINT — runtime assert (armed only), end of pass.
    _assert_member_disjoint(user_flows)

    return {
        "double_claim_uuids": len(double_claims),
        "refs_removed": refs_removed,
        "backref_repointed": repointed,
        "owner_class": owner_class,
        "ufs_shrunk": ufs_shrunk,
        "ufs_dissolved": len(dissolved_ids),
        "dissolved_names": dissolved_names,
        # fixb119 M2 — the record becomes ID-BOUND (the reference form
        # ``adjudicator_6_7e.merge_map``): WHO died (id) and WHO it merged
        # into (survivor id). Both values are already computed above — zero
        # new computations, zero new traversals, zero touches to the board.
        "dissolved_ids": sorted(dissolved_ids),
        "dissolved_into": {
            uid: sorted(owners_by_loser.get(uid, ()))
            for uid in sorted(dissolved_ids)
        },
        # The cap-30 ``dissolved_names`` was INVISIBLE from the board: a
        # consumer could not tell "30 dissolved" from "200 dissolved, 30 shown".
        "dissolved_names_truncated": len(dissolved_ids) > len(dissolved_names),
        "mc_before": mc_before,
        "mc_after": mc_after,
    }


def _assert_no_dangling_backref(
    flow_by_uuid: dict[str, Any],
    dissolved_ids: set[str],
) -> None:
    """No surviving flow back-ref may point at a UF about to dissolve."""
    for fl in flow_by_uuid.values():
        ref = str(getattr(fl, "user_flow_id", "") or "")
        if ref and ref in dissolved_ids:
            raise AssertionError(
                "member_disjoint: flow %r back-refs dissolving UF %r"
                % (str(getattr(fl, "uuid", "") or ""), ref)
            )


def _assert_member_disjoint(user_flows: list[Any]) -> None:
    """I-DISJOINT — every member id appears in at most ONE surviving UF."""
    seen: dict[str, str] = {}
    for uf in user_flows:
        uid = _uid(uf)
        for m in getattr(uf, "member_flow_ids", None) or []:
            ms = str(m)
            prev = seen.get(ms)
            if prev is not None:
                raise AssertionError(
                    "I-DISJOINT violated: member %r claimed by both %r "
                    "and %r after reconciliation" % (ms, prev, uid)
                )
            seen[ms] = uid
