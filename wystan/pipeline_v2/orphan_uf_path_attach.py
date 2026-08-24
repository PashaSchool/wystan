"""orphan_uf_path_attach — #3A: last-chance attach of None journeys by path ownership.

THE CLASS (keyed-world census 2026-08-03): 69 real UFs with
``product_feature_id = None`` — journeys born of the 6.7d abstraction
with NO domain match to any PF (hoppscotch ×29 — legacy of the dissolved
Common). Existing rails are blind: I16-rehome (6.99) cures MIS-homed
(entry-owner mismatch), not None-born; token/container-rehome need mint tele.

MECHANISM (deterministic, $0): for an orphan real UF, collect the owners
of all member-flow files (entry + paths) via a dev→PF join; if ONE PF
holds ≥ ``_STRONG_SHARE`` of the weighted occurrences — attach to it.
Weak/zero ownerships stay honest orphans (conservation over invention;
the residual edge of Common is a separate cycle).

Order: the post-UF family, BEFORE B96 (6.9969) — attach-first-then-demote:
a journey that finds a home saves its PF from reading as 0-UF.

Flag ``WYSTAN_ORPHAN_UF_PATH_ATTACH`` default OFF (armed-only; the flip
rides its own commit per protocol). Unset ≡ 0 byte-identical.
"""

from __future__ import annotations

import os
from collections import Counter
from typing import Any

__all__ = [
    "ORPHAN_UF_PATH_ATTACH_ENV",
    "orphan_uf_path_attach_enabled",
    "run_orphan_uf_path_attach",
]

ORPHAN_UF_PATH_ATTACH_ENV = "WYSTAN_ORPHAN_UF_PATH_ATTACH"

#: Strong ownership: one PF holds ≥60% of a journey's weighted file
#: occurrences (the count-grain threshold of the widget-micro precedent;
#: hoppscotch exhibits resolve at 100%/60%+, weak 50/50 honestly stay).
_STRONG_SHARE = 0.6


def orphan_uf_path_attach_enabled() -> bool:
    """#3A — default **ON** since flip-pack #18 (KEY_SCHEMA 53, 2026-08-04):
    live hoppscotch(6)+unkey(4) + the offline world breadth (18 attaches
    across 7 boards, surgical, weak ones honestly stay). Unset ≡ explicit
    ``1``; explicit ``0`` = kill-switch forever."""
    return os.environ.get(ORPHAN_UF_PATH_ATTACH_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def run_orphan_uf_path_attach(
    product_features: list[Any],
    developer_features: list[Any] | None,
    user_flows: list[Any] | None,
    flows: list[Any] | None,
) -> dict[str, Any] | None:
    """Attach None journeys to a PF by strong path ownership (in place);
    telemetry for ``scan_meta.orphan_uf_path_attach``; ``None`` when the
    flag is off."""
    if not orphan_uf_path_attach_enabled():
        return None
    tele: dict[str, Any] = {
        "enabled": True,
        "attached": {},
        "weak_left": [],
        "unresolvable_left": 0,
        "considered": 0,
    }
    pf_names = {
        str(getattr(p, "name", "") or "")
        for p in (product_features or [])
        if getattr(p, "layer", "product") == "product"
    }
    if not pf_names:
        return tele
    file2pf: dict[str, str] = {}
    for f in (developer_features or []):
        pf = str(getattr(f, "product_feature_id", "") or "")
        if pf in pf_names:
            for p in (getattr(f, "paths", None) or ()):
                file2pf.setdefault(str(p), pf)
    # member_flow_ids = "uuid or name" (models/types:1134); uuids are
    # stamped at the exit — in this rail's slot live mids can be NAMES.
    flow_by_id: dict[str, Any] = {}
    for fl in (flows or []):
        for key in (getattr(fl, "id", None), getattr(fl, "uuid", None),
                    getattr(fl, "name", None)):
            if key:
                flow_by_id.setdefault(str(key), fl)
    for uf in sorted(
        (u for u in (user_flows or [])
         if not getattr(u, "synthesized", False)
         and not getattr(u, "product_feature_id", None)),
        key=lambda u: str(getattr(u, "name", "") or ""),
    ):
        tele["considered"] += 1
        owners: Counter[str] = Counter()
        for mid in (getattr(uf, "member_flow_ids", None) or ()):
            fl = flow_by_id.get(str(mid))
            if fl is None:
                continue
            cand = [getattr(fl, "entry_point_file", None)]
            cand += list(getattr(fl, "paths", None) or ())
            for p in cand:
                own = file2pf.get(str(p or ""))
                if own:
                    owners[own] += 1
        if not owners:
            tele["unresolvable_left"] += 1
            continue
        top, n = owners.most_common(1)[0]
        share = n / max(1, sum(owners.values()))
        if share >= _STRONG_SHARE:
            uf.product_feature_id = top
            tele["attached"].setdefault(top, []).append(
                str(getattr(uf, "name", "") or ""))
        else:
            tele["weak_left"].append(str(getattr(uf, "name", "") or ""))
    return tele
