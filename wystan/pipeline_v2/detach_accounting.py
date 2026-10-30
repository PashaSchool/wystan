"""Stage 6.9971 — terminal accounting for POST-LANE detachments (fixb103).

THE CLASS (traced on the fresh keyed rebattery boards, 2026-08-04)
=================================================================
The warden's re-judge named three residues and asked whether they were
B102 member-remap side-effects. They are NOT — the trace refutes that
hypothesis and lands on a different, single mechanism:

**a PF dies AFTER the passes that account for its dependents have already
run, and nothing gives the survivors a terminal state.**

The dependents are of two kinds, and today they are handled
INCONSISTENTLY — one gets nulled, the other keeps a dead pointer:

* ``I12`` — infisical ON ``UF-208`` 'Connect steps' still points at
  ``product_feature_id='steps'``. ``emission_hard_gate`` (phase_finalize,
  the LAST structural pass before output) demoted that PF
  (``e1_demoted: ['steps']``); ``emission_integrity``'s I12 pass had run
  ~2100 lines earlier, so the reference was live when it was checked and
  dead when it shipped.
* ``I21`` — infisical ON ``UF-182`` 'Ingest server v1 routes' carries
  ``product_feature_id=None``. Its home ``server-v1-routes`` was demoted by
  ``container_journey_rehome``, which DID account for it:
  ``{uf: UF-182, from: server-v1-routes, to: null, verdict: 'aggregate'}``.
  That row is therefore already at its honest terminal state — a deliberate,
  named, null-homed journey. This pass STAMPS it as accounted and changes
  nothing about it (re-homing a row another pass deliberately detached
  would overturn that pass's verdict, which this sprint was not asked to
  do).
* ``I22`` — the same PF deaths unbind their DEV features. Both producers
  already COUNT the casualties (``container_journey_rehome``
  ``demote_devs_unowned: 9``, ``emission_hard_gate`` ``devs_unowned: 1``),
  but the ``platform_infrastructure`` lane — the contractual explainability
  surface I22 reads — is built at phase_finalize:3600, long BEFORE either.
  So the devs fall out of every bucket: no PF home, no lane row, not a
  facet, not a non-product member. Measured unaccounted residents:
  infisical **OFF 3** ('error-page', 'not-found-page', 'redirects') vs
  **ON 11** ('signup', 'sso', 'webhooks', 'redirects', 'ai-routes',
  'server-v2-routes', 'server-v3-routes', 'steps', 'v1-2', 'user-2',
  'server-v1-routes') — the two demoted PF names are literally in the ON
  list.

THE LAW — B58-v5 dissolution accounting, applied at the terminal seam
=====================================================================
``generic_container_demote``'s doctrine is the precedent this follows
verbatim: when a container dies, its members land on an explicit rung —
re-home to a surviving owner, else **honest Layer-1 residual**
(``product_feature_id=None`` + ``shared_reason=<pass>``, files and LOC
kept — the LOC-real law). This pass adds the piece that doctrine assumes
but the late demoters cannot provide: the lane row that makes such a
resident VISIBLE, plus the I12 reference repair, at a seam after the last
PF-killer.

Per row, deterministic, $0, no vocabulary:

1. **UF -> PF (I12)** — a ``product_feature_id`` that is not an emitted PF
   key is canonically re-matched against the surviving key-set
   (``emission_integrity.canonical_slug`` — the SAME matcher Pass 2 uses,
   so the two seams cannot disagree) and, failing that, nulled. Every
   decision is named in telemetry: no silent drop.
2. **dev -> lane (I22)** — a developer feature with no PF home, not a
   facet, not a ``non_product_surfaces`` member and with no lane row gets
   one, built by the SAME row shape as
   ``build_platform_infrastructure_lane`` and carrying
   ``shared_reason=`` :data:`DETACH_REASON` on both the lane row and its
   ``features[]`` entry (I22 checks both sides).
3. **UF with no home (I21)** — reported, never mutated. A row another pass
   deliberately detached is already accounted; a row that arrives here
   homeless with NO upstream verdict is the honest finding this telemetry
   surfaces.
4. **backpointers (I14)** — the idempotent
   ``uf_member_exists.reconcile_flow_backpointers`` runs last, so a
   reference repaired here can never leave the reverse pointer behind.

CONSERVATION: nothing is deleted. No feature, journey, flow or path
leaves the board; the pass only ADDS lane rows and REPAIRS scalar
cross-references. A journey is never re-homed (that is a product decision
owned by the rehome family, not by an accountant).

Flag ``WYSTAN_DETACH_ACCOUNTING`` default **ON** (flip-pack #19, KS54;
unset ≡ ``1``). Explicit ``0`` ⇒ ``None`` before any read or mutation ⇒
no ``scan_meta`` key ⇒ byte-identical.
"""

from __future__ import annotations

import os
from typing import Any

from wystan.pipeline_v2.emission_integrity import canonical_slug

DETACH_ACCOUNTING_ENV = "WYSTAN_DETACH_ACCOUNTING"

#: The ``shared_reason`` a terminally-detached resident wears. Distinct
#: from every mint-time reason so the lane stays readable as provenance:
#: this resident was unbound by a LATE demote, not laned at mint.
DETACH_REASON = "detach_accounting"


def detach_accounting_enabled() -> bool:
    """Default **ON** (flip-pack #19, KS54). ``=0`` disables: no hook, no
    key, board byte-identical."""
    return os.environ.get(DETACH_ACCOUNTING_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _pf_key(pf: Any) -> str:
    return str(getattr(pf, "id", None) or getattr(pf, "name", "") or "")


def _name(obj: Any) -> str:
    return str(getattr(obj, "name", "") or "")


def reconcile_detachments(
    features: list[Any],
    product_features: list[Any],
    user_flows: list[Any],
    flows: Any,
    platform_infrastructure: list[dict[str, Any]] | None,
    non_product_surfaces: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Give every post-lane detachment its honest terminal state.

    Mutates ``user_flows`` (scalar ``product_feature_id`` only),
    ``features`` (``shared_reason`` stamp only) and appends to
    ``platform_infrastructure`` in place. Returns ``None`` when the board
    is already fully accounted (inertness ⇒ no scan_meta key), else
    deterministic telemetry naming EVERY decision.
    """
    pf_keys = {_pf_key(pf) for pf in product_features if _pf_key(pf)}
    canon_to_key: dict[str, str] = {}
    for key in sorted(pf_keys):
        canon_to_key.setdefault(canonical_slug(key), key)

    # ---- 1. I12 — UF -> PF referential repair ----
    relinked: list[dict[str, str]] = []
    nulled: list[dict[str, str]] = []
    for uf in user_flows:
        ref = getattr(uf, "product_feature_id", None)
        if not ref or str(ref) in pf_keys:
            continue
        target = canon_to_key.get(canonical_slug(str(ref)))
        if target is not None:
            uf.product_feature_id = target
            relinked.append({"uf": _name(uf), "from": str(ref), "to": target})
        else:
            uf.product_feature_id = None
            nulled.append({"uf": _name(uf), "from": str(ref)})

    # ---- 2. I22 — unaccounted resident -> lane row ----
    lane_rows = list(platform_infrastructure or ())
    lane_uuids = {
        str(r.get("uuid") or "") for r in lane_rows if r.get("uuid")}
    # Read the non-product membership from the EMITTED channel — the same
    # ``non_product_surfaces[].member_devs`` list the I22 gate reads — never
    # from a re-derived proxy: a dev the taxonomy already claimed is that
    # pass's resident, not this one's.
    nps_names: set[str] = set()
    for nps_row in (non_product_surfaces or ()):
        if isinstance(nps_row, dict):
            nps_names.update(
                str(m) for m in (nps_row.get("member_devs") or ())
                if isinstance(m, str))

    laned: list[dict[str, Any]] = []
    # No lane channel on this board (the anchored mint did not run, so
    # ``platform_infrastructure`` is None and the emitted JSON omits the
    # key): the I22 LANE schema is not active, and minting rows into a
    # local list would stamp reasons the board never ships — telemetry
    # claiming residents nobody can see. Rung 2 abstains, honestly.
    for f in (features if platform_infrastructure is not None else ()):
        if getattr(f, "layer", "developer") != "developer":
            continue
        if getattr(f, "product_feature_id", None) is not None:
            continue
        if getattr(f, "role", None) == "facet":
            continue
        uuid = str(getattr(f, "uuid", "") or "")
        if uuid and uuid in lane_uuids:
            # Already a resident — it only needs the reason the contract
            # requires on the features[] side.
            if not getattr(f, "shared_reason", None):
                f.shared_reason = DETACH_REASON
                laned.append({"dev": _name(f), "action": "reason_stamped"})
            continue
        if _name(f) in nps_names:
            continue
        if not getattr(f, "shared_reason", None):
            f.shared_reason = DETACH_REASON
        row: dict[str, Any] = {
            "name": _name(f),
            "display_name": (
                getattr(f, "display_name", None) or _name(f)),
            "shared_reason": str(getattr(f, "shared_reason", None)
                                 or DETACH_REASON),
            "uuid": uuid,
            "paths": list(getattr(f, "paths", None) or []),
            "loc": getattr(f, "loc", None),
            "loc_shared": getattr(f, "loc_shared", None),
            "flows": len(getattr(f, "flows", None) or []),
        }
        lane_rows.append(row)
        laned.append({
            "dev": _name(f),
            "action": "lane_row_minted",
            "loc": row["loc"],
            "paths": len(row["paths"]),
        })

    # ---- 3. I21 — homeless journeys, reported not moved ----
    homeless = sorted(
        _name(uf) for uf in user_flows
        if not getattr(uf, "product_feature_id", None))

    # ---- 4. I14 — the reverse pointer follows any repair above ----
    from wystan.pipeline_v2.uf_member_exists import (
        reconcile_flow_backpointers,
    )

    bp_tele = reconcile_flow_backpointers(user_flows, flows)

    if not (relinked or nulled or laned or bp_tele):
        return None

    if laned and platform_infrastructure is not None:
        lane_rows.sort(key=lambda r: str(r.get("name") or ""))
        platform_infrastructure[:] = lane_rows

    tele: dict[str, Any] = {
        "enabled": True,
        "uf_pf_refs_relinked": len(relinked),
        "uf_pf_refs_nulled": len(nulled),
        "lane_rows_minted": sum(
            1 for r in laned if r["action"] == "lane_row_minted"),
        "lane_reasons_stamped": sum(
            1 for r in laned if r["action"] == "reason_stamped"),
        "homeless_journeys": len(homeless),
    }
    # Complete records — the no-silent-drop law.
    if relinked:
        tele["relinked"] = relinked
    if nulled:
        tele["nulled"] = nulled
    if laned:
        tele["laned"] = laned
    if homeless:
        tele["homeless_journey_names"] = homeless
    if bp_tele:
        tele["backpointers"] = bp_tele
    return tele


def run_detach_accounting(
    features: list[Any],
    product_features: list[Any],
    user_flows: list[Any],
    flows: Any,
    platform_infrastructure: list[dict[str, Any]] | None,
    non_product_surfaces: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Flag-gated stage entry. OFF/unset ⇒ ``None`` BEFORE any read or
    mutation (kill-switch / byte-identity law)."""
    if not detach_accounting_enabled():
        return None
    return reconcile_detachments(
        features, product_features, user_flows, flows,
        platform_infrastructure, non_product_surfaces,
    )


__all__ = [
    "DETACH_ACCOUNTING_ENV",
    "DETACH_REASON",
    "detach_accounting_enabled",
    "reconcile_detachments",
    "run_detach_accounting",
]
