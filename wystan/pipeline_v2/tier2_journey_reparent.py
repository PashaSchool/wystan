"""tier2_journey_reparent — #4: a journey leaves a techno-named PF for its real home.

THE CLASS (fresh census 2026-08-03, 30 specimens → probe): journeys on a
PF with a techno name (B96 vocab) whose ENTRY owners are ≥80% ONE OTHER
product PF — live exhibit teable ``base``: 2 real UFs with 100% entry
ownership by ``share``. Origins of the class: late mints/folds nailed the
journey to a structural container while the evidence lives next door.

DELIBERATELY OUT OF SCOPE (the probe proved these are other diseases):
SELF-owned journeys of a techno PF (documenso ``api+`` ×22 — the naming
domain); no-evidence journeys (infisical component-name noise — 6.7d
quality, pinned); mega-containers (the decomposition family).

Discriminator (structural; vocab only narrows candidates, the B96
doctrine): a PF with a techno name ∧ no nav ∧ a real UF ∧ UF entry owners
≥``_FOREIGN_SHARE`` on one OTHER product PF → the journey moves there.
The emptied techno PF is then honestly demoted by B96 (the
attach→reparent→demote order in finalize).

Flag ``WYSTAN_TIER2_JOURNEY_REPARENT`` default ON since flip-pack #18
(KEY_SCHEMA 53; unset ≡ ``1``). Explicit ``0`` ⇒ byte-identical. $0,
deterministic.
"""

from __future__ import annotations

import os
from collections import Counter
from typing import Any

__all__ = [
    "TIER2_JOURNEY_REPARENT_ENV",
    "tier2_journey_reparent_enabled",
    "run_tier2_journey_reparent",
]

TIER2_JOURNEY_REPARENT_ENV = "WYSTAN_TIER2_JOURNEY_REPARENT"

#: Strict threshold for foreign entry ownership (teable exhibits = 100%;
#: inbox-zero's 42% self honestly stays — the boundary is unambiguous).
_FOREIGN_SHARE = 0.8


def tier2_journey_reparent_enabled() -> bool:
    """#4 — default **ON** since flip-pack #18 (KEY_SCHEMA 53, 2026-08-04):
    offline breadth of 8 moves / 4 boards (share 0.91-1.0, all sensible:
    teable base→share, documenso api+→settings+/share.$slug, highlight
    components→workspace-team/player, plane api/app) + the offline teable
    chain reparent→B96-demote. Unset ≡ explicit ``1``; explicit ``0`` =
    kill-switch forever."""
    return os.environ.get(TIER2_JOURNEY_REPARENT_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def run_tier2_journey_reparent(
    product_features: list[Any],
    developer_features: list[Any] | None,
    user_flows: list[Any] | None,
    flows: list[Any] | None,
) -> dict[str, Any] | None:
    """Re-parent journeys of techno-named PFs by strict foreign entry
    ownership (in place); telemetry for
    ``scan_meta.tier2_journey_reparent``; ``None`` when the flag is off."""
    if not tier2_journey_reparent_enabled():
        return None
    from wystan.pipeline_v2.generic_container_demote import (
        _husk_vocab,
        _vocab_hit,
    )
    from wystan.pipeline_v2.segb_landing_binding import (
        note_bound_abstain,
        segb_landing_target,
    )
    tele: dict[str, Any] = {
        "enabled": True,
        "reparented": {},
        "self_kept": [],
        "no_evidence_kept": [],
        "considered_pfs": 0,
    }
    vocab = _husk_vocab()
    products = {
        str(getattr(p, "name", "") or ""): p
        for p in (product_features or [])
        if getattr(p, "layer", "product") == "product"
    }
    if not products:
        return tele
    # techno-named candidates with no nav surface of their own
    cand_names = {
        n for n, p in products.items()
        if not getattr(p, "nav_parent", None) and _vocab_hit(p, vocab)
    }
    if not cand_names:
        return tele
    file2pf: dict[str, str] = {}
    for f in (developer_features or []):
        pf = str(getattr(f, "product_feature_id", "") or "")
        if pf in products:
            for pth in (getattr(f, "paths", None) or ()):
                file2pf.setdefault(str(pth), pf)
    flow_by_id: dict[str, Any] = {}
    for fl in (flows or []):
        for key in (getattr(fl, "id", None), getattr(fl, "uuid", None),
                    getattr(fl, "name", None)):
            if key:
                flow_by_id.setdefault(str(key), fl)
    seen_pfs: set[str] = set()
    for uf in sorted(
        (u for u in (user_flows or [])
         if not getattr(u, "synthesized", False)),
        key=lambda u: str(getattr(u, "name", "") or ""),
    ):
        home = str(getattr(uf, "product_feature_id", "") or "")
        if home not in cand_names:
            continue
        seen_pfs.add(home)
        owners: Counter[str] = Counter()
        for mid in (getattr(uf, "member_flow_ids", None) or ()):
            fl = flow_by_id.get(str(mid))
            if fl is None:
                continue
            e = str(getattr(fl, "entry_point_file", "") or "")
            own = file2pf.get(e)
            if own:
                owners[own] += 1
        if not owners:
            tele["no_evidence_kept"].append(str(getattr(uf, "name", "") or ""))
            continue
        top, n = owners.most_common(1)[0]
        share = n / sum(owners.values())
        if top != home and share >= _FOREIGN_SHARE:
            # fixb118 case "a" — a Seg B landing is binding. Our channel
            # (``file2pf`` from ``dev.product_feature_id``) is EXACTLY the
            # owner map B78 calls a poisoned annexation: a PF that stole the
            # files legitimately "owns" the journey's entry points, so we
            # would hand it back to the thief. Seg B judged on an
            # unpoisonable channel (name × name), so when a journey SITS
            # where Seg B put it and we pull it elsewhere — we abstain and
            # record. Live exhibit: ollama UF-004 'Configure app settings'
            # app→api-tags share 1.0. Flag OFF ⇒ ``bound`` is always None ⇒
            # the branch is dead ⇒ byte-identical.
            bound = segb_landing_target(uf)
            if bound is not None and bound == home and bound != top:
                note_bound_abstain(uf, home, top, writer="tier2-reparent")
                tele.setdefault("segb_landing_bound", []).append({
                    "uf": str(getattr(uf, "name", "") or ""),
                    "kept": home, "refused": top, "share": round(share, 2),
                })
                continue
            uf.product_feature_id = top
            tele["reparented"].setdefault(home, []).append(
                {"uf": str(getattr(uf, "name", "") or ""), "to": top,
                 "share": round(share, 2)})
        else:
            tele["self_kept"].append(str(getattr(uf, "name", "") or ""))
    tele["considered_pfs"] = len(seen_pfs)
    return tele
