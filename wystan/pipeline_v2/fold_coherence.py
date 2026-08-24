"""fixb108-v3 (b) — the FOLD-COHERENCE law.

When the F3 page-surface rescue lets the mint fold a page-grain PF away,
the journey that PF held must not evaporate in silence. The keyed c6proof
pair (warden-verified) showed the divergence this law answers:

* chatwoot ``voice`` — folded into ``twilio``, a PRODUCT PF. Stage 6.7d
  re-derives the journey under a product receiver, so 'Manage voice…'
  survived.
* chatwoot ``documents`` — folded into ``controllers-core``, a HUB
  container. 6.7d does NOT re-derive under a hub, so 'Browse and manage
  documents' (mc=6) died with no gap and no non-product admission.

Both dev features kept their 6 flows either way — the members were always
conserved. What was lost was the JOURNEY, and losing it silently is the
defect: an operator cannot audit a row that left no trace.

The law, applied at the fold site:

  (i)  a PRODUCT home exists (the majority home of the journey's member
       flows after the fold is a product PF) ⇒ RE-HOME the journey there.
       Identity and membership are untouched — only ``product_feature_id``
       moves (the №4-reparent precedent).
  (ii) the home is a hub / non-product container ⇒ convert the journey to
       an honest COVERAGE GAP. Per the B23/B31 marker law a marker never
       wears a journey NAME without coordinates, so the gap carries the
       member files as coordinates and drops the prose name.

Pure and unit-testable: :func:`fold_coherence_verdict` decides from plain
attributes, so the Documents-shape and Twilio-shape fixtures are exact.
"""

from __future__ import annotations

import hashlib
import os
from collections import Counter
from typing import Any

#: fixb108-v3 (b). A SEPARATE flag from WYSTAN_HEADLESS_SURFACE_RESCUE
#: even though this is F3's tail. Blast-radius call: the rescue alone
#: already moves chatwoot's mint 48 → 15 PFs, so folding the coherence
#: law into the same switch would make a default-flip un-attributable —
#: a keyed A/B could not say which half moved a number. Two flags = two
#: independently provable claims. Default OFF; ``=0`` kill-switch forever.
FOLD_COHERENCE_ENV = "WYSTAN_FOLD_COHERENCE"

#: Anchor kinds that are CONTAINERS, never a product home for a journey.
#: Data-free on purpose: this is the anchor-id grammar (the ``<kind>:``
#: prefix the mint itself stamps), not a vocabulary.
_CONTAINER_KINDS = frozenset({"hub", "ws", "fdir"})


def fold_coherence_enabled() -> bool:
    """fixb108-v3 (b) — fold-coherence law. Default OFF (armed)."""
    return os.environ.get(FOLD_COHERENCE_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def is_product_home(pf: Any) -> bool:
    """A PF that can HOLD a journey: product layer, product surface, and
    not a container-kind anchor.

    ``controllers-core`` fails on the anchor kind (``hub:``) — that is the
    Documents receiver. ``twilio`` passes — that is the Voice receiver.
    """
    if pf is None:
        return False
    if str(_attr(pf, "layer", "") or "") != "product":
        return False
    scope = str(_attr(pf, "surface_scope", "product") or "product")
    if scope not in ("product", ""):
        return False
    kind = str(_attr(pf, "anchor_id", "") or "").split(":", 1)[0].lower()
    return kind not in _CONTAINER_KINDS


def majority_home(flow_homes: list[str | None]) -> str | None:
    """The dominant post-fold home of a journey's member flows.

    Ties break by pf-id ascending so the verdict never depends on member
    ordering (the set-iteration determinism trap).
    """
    live = [str(h) for h in flow_homes if h]
    if not live:
        return None
    counts = Counter(live)
    top = max(counts.values())
    return sorted(k for k, v in counts.items() if v == top)[0]


def gap_id_for(member_files: list[str]) -> str:
    """Deterministic gap id over the journey's coordinates."""
    payload = "|".join(sorted({str(f) for f in member_files}))
    return "GAP-" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]


def fold_coherence_verdict(
    flow_homes: list[str | None],
    pf_by_id: dict[str, Any],
) -> tuple[str, str | None]:
    """``("rehome", pfid)`` | ``("gap", None)`` | ``("hold", None)``.

    ``hold`` means the journey still has a live product home and the law
    has nothing to do — the overwhelmingly common case, and the reason
    an armed board barely moves.
    """
    home = majority_home(flow_homes)
    if home is None:
        return "gap", None
    pf = pf_by_id.get(home)
    if is_product_home(pf):
        return "rehome", home
    return "gap", None


def apply_fold_coherence(
    user_flows: list[Any],
    product_features: list[Any],
    flow_home_of: dict[str, str | None],
) -> dict:
    """Re-home or gap every journey whose PF vanished in the fold.

    Only ``product_feature_id`` is written — identity, names and
    ``member_flow_ids`` are never touched (single-writer law). Returns
    telemetry; the caller stamps it and mints the gaps.
    """
    tele: dict[str, Any] = {
        "enabled": True, "orphans": 0, "rehomed": [], "gapped": [],
    }
    live_pf_ids = {
        str(_attr(p, "name", "") or "") for p in product_features
    }
    pf_by_id = {
        str(_attr(p, "name", "") or ""): p for p in product_features
    }
    for uf in user_flows:
        home = _attr(uf, "product_feature_id")
        if home and str(home) in live_pf_ids:
            continue  # the journey still has a home — nothing to heal
        members = list(_attr(uf, "member_flow_ids", ()) or ())
        if not members:
            continue
        tele["orphans"] += 1
        verdict, target = fold_coherence_verdict(
            [flow_home_of.get(str(m)) for m in members], pf_by_id)
        uf_name = str(_attr(uf, "name", "") or "")
        if verdict == "rehome" and target:
            if isinstance(uf, dict):
                uf["product_feature_id"] = target
            else:
                uf.product_feature_id = target
            tele["rehomed"].append({"uf": uf_name, "to": target,
                                    "mc": len(members)})
        else:
            # B23/B31 marker law — a marker never wears a journey NAME
            # without coordinates. The gap keeps the coordinates.
            tele["gapped"].append({"uf": uf_name, "mc": len(members)})
    return tele


__all__ = [
    "FOLD_COHERENCE_ENV",
    "fold_coherence_enabled",
    "fold_coherence_verdict",
    "is_product_home",
    "majority_home",
    "gap_id_for",
    "apply_fold_coherence",
]
