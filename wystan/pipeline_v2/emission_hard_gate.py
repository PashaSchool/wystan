"""emission_hard_gate — B97: the LAST barrier before Stage 7 output.

OPERATOR MANDATE (2026-08-02, verbatim): "emission-hard-gate — add it" after
finding, on stale boards, defect classes the engine had long fixed but that
kept resurfacing at review: PFs with no LOC, PFs with zero files, raw
route-syntax names. The recurring-circle root cause: every fix is a
stage-local gate, so a future regression in ANY stage can re-emit an old
class silently. This stage generalizes the stage-hooks law to the whole
board: **a trust-law violation physically cannot leave the engine** — it is
repaired, demoted, or (when repair would orphan a journey) kept but named
in telemetry. Every scan — including the very FIRST scan of a repo — is
policed at output; board hygiene no longer depends on which stage regressed.

Distinct from ``emission_integrity`` (Stage 7 phantom-drop): that pass runs
MID-finalize (phase_finalize:3025), so every later mint (6.86 anchored,
6.9966 container family, the B9x demote tail) escapes it. B97 runs after
EVERYTHING — post-B96, pre-census/output.

THE CHECKS (exhibit-grounded, deterministic, $0):

  E1 LOC-REAL (law 2026-07-16 "LOC must be real everywhere"): a PF with
     live members but ``loc`` in {None, 0} first RECOMPUTES from its member
     devs' loc; if the recompute lands >0 the row is repaired in place.
     Unrecoverable + 0 real journeys → demoted to dev-layer residual.
     Unrecoverable + real journeys → KEPT, named in telemetry (the gate
     never orphans a journey — conservation over cosmetics).
  E2 ZERO-MEMBER (unsend ``usesend-js`` exhibit: 0 files, anchor=None): a
     PF with no member devs AND no member_files is a shell. 0 real
     journeys → removed. Real journeys → kept + named (upstream bug, do
     not bury it by orphaning the journeys).
  E3a PAREN-ROUTE TAIL (cal.com ``routing-forms-(route-apps-web-app-…)``,
     langfuse ``datasets-(route-…)`` — the B69 paren family): the
     ``-(route-…)`` disambiguator tail is stripped to the base name;
     collisions resolve with ``-2``/``-3`` suffixes; the rename PROPAGATES
     to dev.product_feature_id and uf.product_feature_id (name is the join
     key — a rename that does not propagate corrupts the board).
  E3b ROUTE-PARAM MONSTER (trigger.dev ``resources-orgs-organization-slug-
     projects-project-param-…-spans-span-param``): a name carrying ≥2
     route-param markers (``-param``/``-slug``) or ≥10 hyphen segments is a
     raw route file, not a product name. 0 real journeys → demoted to
     dev-layer residual. Real journeys → kept + named (renaming would mean
     INVENTING a name deterministically — refused; the violation is loud).

Flag ``WYSTAN_EMISSION_HARD_GATE`` default **ON** since flip-pack #16
(KEY_SCHEMA 51, 2026-08-02; unset ≡ explicit ``1``). Explicit ``0`` ⇒
``None`` before any mutation, no ``scan_meta`` key ⇒ byte-identical
(kill-switch forever).
Deterministic, no LLM, no network; sorted iteration everywhere.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from typing import Any

__all__ = [
    "EMISSION_HARD_GATE_ENV",
    "emission_hard_gate_enabled",
    "run_emission_hard_gate",
]

EMISSION_HARD_GATE_ENV = "WYSTAN_EMISSION_HARD_GATE"

#: shared_reason stamped on residual member devs (sibling convention).
_REASON = "emission_hard_gate"

#: E3a — the paren-route disambiguator tail: ``<base>-(route-…)`` (also
#: ``dir-``/``ws-`` variants of the same disambiguator family).
_PAREN_TAIL_RE = re.compile(r"^(?P<base>.+?)-\((?:route|dir|ws)-[^)]*\)$")

#: E3b — route-param markers a product name never carries.
_PARAM_MARKER_RE = re.compile(r"-(?:param|slug)(?:-|$)")
_MONSTER_MIN_MARKERS = 2
_MONSTER_MIN_SEGMENTS = 10


def emission_hard_gate_enabled() -> bool:
    """B97 — default **ON** since flip-pack #16 (KEY_SCHEMA 51,
    2026-08-02): conservation proofs on 5 real boards (langfuse
    paren-strip datasets/evals, cal.com routing-forms-2, UF sets
    byte-identical throughout) + keyed net delta ∅. Unset ≡ explicit ``1``
    (the inverted kill-switch unit). Explicit ``0`` ⇒ ``None`` before any
    mutation, with no ``scan_meta`` key ⇒ kill-switch forever."""
    return os.environ.get(EMISSION_HARD_GATE_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _name(pf: Any) -> str:
    return str(getattr(pf, "name", "") or "").strip()


def _is_monster(name: str) -> bool:
    markers = len(_PARAM_MARKER_RE.findall(name))
    return markers >= _MONSTER_MIN_MARKERS or (
        name.count("-") + 1 >= _MONSTER_MIN_SEGMENTS and markers >= 1
    )


def run_emission_hard_gate(
    product_features: list[Any],
    developer_features: list[Any] | None,
    user_flows: list[Any] | None,
) -> dict[str, Any] | None:
    """Enforce the emission trust laws (in place); return the
    ``scan_meta.emission_hard_gate`` telemetry, or ``None`` (no mutation,
    no key) when the flag is off. Runs LAST — after B96, before the
    product-right census + Stage 7 — so nothing minted or renamed later
    can bypass it."""
    if not emission_hard_gate_enabled():
        return None
    tele: dict[str, Any] = {
        "enabled": True,
        "e1_loc_recomputed": {},
        "e1_demoted": [],
        "e1_kept_violations": [],
        "e2_removed": [],
        "e2_kept_violations": [],
        "e3a_renamed": {},
        "e3b_demoted": [],
        "e3b_kept_violations": [],
        "devs_unowned": 0,
    }
    products = [
        pf for pf in (product_features or [])
        if getattr(pf, "layer", "product") == "product"
    ]
    if not products:
        return tele

    devs_by_pf: dict[str, list[Any]] = defaultdict(list)
    for f in (developer_features or []):
        pid = getattr(f, "product_feature_id", None)
        if pid:
            devs_by_pf[str(pid)].append(f)

    real_uf: dict[str, int] = defaultdict(int)
    for uf in (user_flows or []):
        pid = getattr(uf, "product_feature_id", None)
        if pid and not getattr(uf, "synthesized", False):
            real_uf[str(pid)] += 1

    taken = {_name(pf) for pf in products}

    # ── E3a — paren-route tail strip + rename propagation (FIRST: later
    # checks and the join keys must see the final names). Sorted order. ──
    for pf in sorted(products, key=_name):
        name = _name(pf)
        m = _PAREN_TAIL_RE.match(name)
        if not m:
            continue
        base = m.group("base")
        new = base
        i = 2
        while new in taken:
            new = f"{base}-{i}"
            i += 1
        taken.discard(name)
        taken.add(new)
        pf.name = new
        disp = str(getattr(pf, "display_name", "") or "")
        if not disp or "(" in disp:
            pf.display_name = new.replace("-", " ").title()
        for d in devs_by_pf.pop(name, []):
            d.product_feature_id = new
            devs_by_pf[new].append(d)
        for uf in (user_flows or []):
            if str(getattr(uf, "product_feature_id", "") or "") == name:
                uf.product_feature_id = new
        if name in real_uf:
            real_uf[new] = real_uf.pop(name)
        tele["e3a_renamed"][name] = new

    def _demote(pf: Any, bucket: str) -> None:
        name = _name(pf)
        for d in sorted(devs_by_pf.get(name, ()),
                        key=lambda x: str(getattr(x, "name", "") or "")):
            # E1b (ollama ``api-v1-cloud`` exhibit): a member dev that is
            # ALREADY a shell — zero owned paths AND zero loc — must not
            # survive as a residual row (a 0-path dev is I1 by
            # construction; the last-word gate may not emit one). Dropped
            # loudly, never silently; its file refs live on via the
            # sibling owners (conservation: no owned path is lost — the
            # shell owns none).
            if (not (getattr(d, "paths", None) or ())
                    and not int(getattr(d, "loc", 0) or 0)
                    and developer_features is not None):
                developer_features.remove(d)
                tele.setdefault("dropped_shell_devs", []).append(
                    str(getattr(d, "name", "") or ""))
                continue
            d.product_feature_id = None
            d.shared_reason = _REASON
            tele["devs_unowned"] += 1
        product_features.remove(pf)
        tele[bucket].append(name)

    # ── E3b — route-param monsters ──────────────────────────────────────
    for pf in sorted(list(products), key=_name):
        name = _name(pf)
        if pf not in product_features or not _is_monster(name):
            continue
        if real_uf.get(name, 0) > 0:
            tele["e3b_kept_violations"].append(name)
            continue
        _demote(pf, "e3b_demoted")

    # ── E2 — zero-member shells ─────────────────────────────────────────
    for pf in sorted(list(products), key=_name):
        name = _name(pf)
        if pf not in product_features:
            continue
        members = devs_by_pf.get(name, [])
        mf = getattr(pf, "member_files", None) or getattr(pf, "paths", None) or []
        if members or mf:
            continue
        if real_uf.get(name, 0) > 0:
            tele["e2_kept_violations"].append(name)
            continue
        _demote(pf, "e2_removed")

    # ── E1 — LOC-real (repair first, demote only when honest) ──────────
    for pf in sorted(list(products), key=_name):
        name = _name(pf)
        if pf not in product_features:
            continue
        members = devs_by_pf.get(name, [])
        mf = getattr(pf, "member_files", None) or getattr(pf, "paths", None) or []
        if not (members or mf):
            continue
        if getattr(pf, "loc", None):
            continue
        recomputed = sum(int(getattr(d, "loc", 0) or 0) for d in members)
        if recomputed > 0:
            pf.loc = recomputed
            tele["e1_loc_recomputed"][name] = recomputed
            continue
        if real_uf.get(name, 0) > 0:
            tele["e1_kept_violations"].append(name)
            continue
        _demote(pf, "e1_demoted")

    return tele
