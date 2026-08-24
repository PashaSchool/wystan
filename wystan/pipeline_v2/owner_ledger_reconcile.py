"""fixb135 — owner-ledger reconciliation (``WYSTAN_OWNER_LEDGER_RECONCILE``).

THE SECOND SPLIT-BRAIN PRODUCER. ``flow_span_split`` writes a per-file
ownership ledger onto every flow —
``Flow.shared_paths[].owner_product_feature`` (+ ``owner_display``) — and
that ledger is a CONTRACT ("lines are coordinates": a span's ownership is
what the reverse lookup ``(file,line) -> flow -> UF -> PF`` resolves
through). But it is written MID-pipeline, and several later passes rename
or demote the row it points at without restamping it:

    stage_6_86_anchored_mint.py:1201      ws_blob_domain_drain.py:1090
    transport_handoff.py:1658             stage_6_9966_…:921
    (+ the collision-ladder renames)

World census (PF-only key-space, the ruling from warden §39): 15 repos
nonzero — umami 309 ('settings'), cal 161+ ('embed-core', 'data-table',
'filters'), highlight/strapi/plane in the thousands.

MECHANISM — one reconciliation pass, not per-site patches. At emission
(right after ``pf_slug_sanitize``, once every rename/demote has settled)
the file→owner map is REBUILT from the FINAL rows with exactly the
semantics ``flow_span_split._owner_map`` had at its own stage, then every
``owner_product_feature`` is re-resolved against it. Drift is rewritten,
``owner_display`` re-rendered from the final PF (the M4b precedent), and
anything genuinely unresolvable is COUNTED rather than guessed at.

Why a backstop beats inline patches: the four demote sites are not the
only writers (collision ladders rename too), and any future mover would
silently re-open the class. Reconciling from final state is closed by
construction. Inline fixes stay optional and are NOT taken here — see the
sprint verdict for the reasoning.

Channel discipline: only ``owner_product_feature`` / ``owner_display``
are ever written. ``pf.name``, ``product_feature_id``, ``anchor_id``,
``display_name``, paths, spans and membership are untouched.
"""

from __future__ import annotations

import os
from typing import Any

__all__ = [
    "OWNER_LEDGER_RECONCILE_ENV",
    "owner_ledger_reconcile_enabled",
    "run_owner_ledger_reconcile",
]

OWNER_LEDGER_RECONCILE_ENV = "WYSTAN_OWNER_LEDGER_RECONCILE"


def owner_ledger_reconcile_enabled() -> bool:
    """Default **ON** since the 2026-08-10 pack-№38 flip (KEY_SCHEMA 71;
    warden №42 GO — umami reconciled=15, cal=97, conservation perfect:
    UF/PF byte-identical, only owner fields moved; ghosts cleared 105/85).
    Unset ≡ explicit ``1``; explicit ``0``/``false`` ⇒ no ledger write, no
    ``scan_meta`` key ⇒ byte-identical (kill-switch forever). The truthy
    set is preserved LITERALLY — only the default moved ``"0"`` -> ``"1"``."""
    return os.environ.get(
        OWNER_LEDGER_RECONCILE_ENV, "1"
    ).strip().lower() in {"1", "true"}


def _final_owner_map(developer_features: list[Any]) -> dict[str, str | None]:
    """file → owning dev's ``product_feature_id``, from the FINAL rows.

    Deliberately the same population rule as
    ``flow_span_split._owner_map``: developer-layer rows only, primary
    ``owned_paths_of`` claims, first writer wins on a duplicate claim. The
    ONLY difference is WHEN it is built — after every rename/demote has
    settled — which is precisely the drift this pass repairs.
    """
    from wystan.pipeline_v2.spine_anchors import owned_paths_of

    owner: dict[str, str | None] = {}
    for f in developer_features:
        if getattr(f, "layer", "developer") != "developer":
            continue
        pfid = getattr(f, "product_feature_id", None)
        for p in owned_paths_of(f):
            owner.setdefault(p, pfid)
    return owner


def _iter_flows(
    product_features: list[Any],
    developer_features: list[Any] | None,
    flows: list[Any] | None,
) -> list[Any]:
    """Every distinct Flow object, de-duplicated on ``id()`` (the M4b walk —
    the containment views and the bipartite array share objects)."""
    seen: set[int] = set()
    out: list[Any] = []
    for holder in (list(product_features or [])
                   + list(developer_features or [])):
        for fl in (getattr(holder, "flows", None) or []):
            if id(fl) not in seen:
                seen.add(id(fl))
                out.append(fl)
    for fl in (flows or []):
        if id(fl) not in seen:
            seen.add(id(fl))
            out.append(fl)
    return out


def run_owner_ledger_reconcile(
    product_features: list[Any],
    developer_features: list[Any] | None,
    flows: list[Any] | None = None,
) -> dict[str, Any] | None:
    """Re-resolve every shared-path owner against the FINAL rows, in place.

    Returns the ``scan_meta.owner_ledger_reconcile`` telemetry, or ``None``
    when the flag is off (no mutation, no key).
    """
    if not owner_ledger_reconcile_enabled():
        return None
    tele: dict[str, Any] = {
        "enabled": True,
        "owners_seen": 0,
        "owners_reconciled": 0,
        "displays_refreshed": 0,
        "owners_unresolvable": 0,
        "owners_cleared_no_final_owner": 0,
        "owners_kept_unbacked_live_key": 0,
        "by_producer_reason": {},
        "exhibits": [],
    }
    # Warden §42 rider B — the 20-slot forensic budget must cover DISTINCT
    # triples first. umami's 15 slots all held ONE repeated path, so the
    # exhibit list showed a single row 15 times and hid every other class.
    _exhibit_seen: set[tuple[str, str | None, str]] = set()

    def _exhibit(path: str, old: str, new: str | None, reason: str) -> None:
        key = (old, new, path)
        if key in _exhibit_seen:
            return
        _exhibit_seen.add(key)
        if len(tele["exhibits"]) < 20:
            tele["exhibits"].append({
                "path": path, "old_owner": old,
                "new_owner": new, "reason": reason,
            })
    devs = [
        d for d in (developer_features or [])
        if getattr(d, "layer", "developer") == "developer"
    ]
    pf_by_key: dict[str, Any] = {}
    for pf in (product_features or []):
        if getattr(pf, "layer", "product") != "product":
            continue
        key = str(getattr(pf, "name", "") or "")
        if key:
            pf_by_key[key] = pf
    dev_names = {str(getattr(d, "name", "") or "") for d in devs}
    owner_map = _final_owner_map(devs)

    def _reason(old: str, resolved: str | None) -> str:
        """WHY this ledger row was stale — the class, not a guess at which
        pass did it (the census wants producer CLASSES, and several movers
        share each class).

        Warden §42 rider A — the discriminator keys on PF-LIVENESS FIRST.
        It used to ask "is this key a dev name?" before asking "is it a
        live PF?", and a name can legitimately be BOTH (a dev row and a PF
        commonly share a slug). umami therefore filed 15 rows as
        `demoted-to-dev-layer` where ZERO demotions happened — 'websites'
        is a live PF that simply lost the file. A key that still names a
        LIVE PF was never demoted, by definition."""
        if resolved is None:
            return "no-final-owner"          # the file left every dev
        if old in pf_by_key:
            # The old owner is STILL a live PF — nothing was demoted or
            # dropped; the FILE moved to another owner.
            return "reattributed-file"
        if old in dev_names:
            # Dev-resident AND not a live PF ⇒ a genuine demotion.
            return "demoted-to-dev-layer"
        return "renamed-or-dropped-pf"       # the key no longer exists

    for fl in _iter_flows(product_features, devs, flows):
        for sp in (getattr(fl, "shared_paths", None) or []):
            old = str(getattr(sp, "owner_product_feature", "") or "")
            if not old:
                continue
            tele["owners_seen"] += 1
            resolved = owner_map.get(str(getattr(sp, "path", "") or ""))
            if resolved is None:
                # The span's file is owned by NO final dev (or by a dev
                # with no PF), so there is no owner to re-resolve TO.
                if old not in pf_by_key:
                    # …and the key names no live PF either: the string is
                    # a GHOST. Battery-13 ruling (2026-08-10) — keeping it
                    # made every reverse lookup through this span lie
                    # forever (umami 105, cal 85). CLEAR the field: an
                    # unattributed shared span rendering as UNOWNED is
                    # honest; a dead string pointing at a ghost PF is not
                    # (LOC-real doctrine — the display never lies).
                    #
                    # ``None``, not "": the schema declares both fields
                    # ``str | None = None``, so None IS the field's own
                    # default and convention, and every reader already
                    # null-coalesces (``getattr(...) or ""``).
                    sp.owner_product_feature = None
                    sp.owner_display = None
                    tele["owners_unresolvable"] += 1
                    tele["owners_cleared_no_final_owner"] += 1
                    reason = _reason(old, None)
                    tele["by_producer_reason"][reason] = (
                        tele["by_producer_reason"].get(reason, 0) + 1)
                    # The old key is kept in the exhibit so nothing is
                    # lost forensically — only the LEDGER stops lying.
                    _exhibit(str(getattr(sp, "path", "") or ""),
                             old, None, reason)
                else:
                    # The key still names a LIVE PF — the string is not a
                    # ghost, it is merely unbacked by the final owner map.
                    # Not provably wrong, so it stands; counted so the
                    # residue is never invisible.
                    tele["owners_kept_unbacked_live_key"] += 1
                continue
            if resolved == old:
                # Already correct — but the DISPLAY may still be stale if
                # the PF was renamed in place (the M4b channel).
                pf = pf_by_key.get(resolved)
                if pf is not None:
                    want = str(getattr(pf, "display_name", None) or resolved)
                    if str(getattr(sp, "owner_display", "") or "") != want:
                        sp.owner_display = want
                        tele["displays_refreshed"] += 1
                continue
            pf = pf_by_key.get(resolved)
            reason = _reason(old, resolved)
            sp.owner_product_feature = resolved
            sp.owner_display = (
                str(getattr(pf, "display_name", None) or resolved)
                if pf is not None else resolved
            )
            tele["owners_reconciled"] += 1
            tele["by_producer_reason"][reason] = (
                tele["by_producer_reason"].get(reason, 0) + 1)
            _exhibit(str(getattr(sp, "path", "") or ""),
                     old, resolved, reason)
    return tele
