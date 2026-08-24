"""segb_landing_binding — fixb118: a Seg B landing becomes BINDING.

THE CLASS (fixb118 forensics, measured on the c9proof pair KS60): B78 Seg B
(``apply_home_affinity_gate``, Stage 6.995) moves a ``tok0`` journey to a
deterministic better-home THROUGH the S3 arbiter — and journals its ruling.
But ``finalize_arbiter`` hands in its census at phase_finalize:5263, while
EIGHT post-arbiter passes run AFTER it. A late writer that overturns a
just-landed placement reaches neither ``overturn_conflicts`` nor
``overturns`` — the journal sees it, the payload is already rendered.
A silent overturn.

LIVE EXHIBIT (ollama, KS60): Seg B landed UF-004 'Configure app
settings' ``api-tags``→``app`` (journaled, rung ``affinity-rehome``);
``tier2_journey_reparent`` sent it back ``app``→``api-tags`` (share 1.0)
and the board emitted ``api-tags``. The conflict is NOT accidental: tier2
builds ``file2pf`` from ``dev.product_feature_id`` — EXACTLY the
``path_index → dev → pfid`` owner map that Seg B's docstring calls a
poisoned annexation (precisely why Seg B moved from 6.9855 to 6.995).
tier2 arrived in flip-pack #18 AFTER B78 and wired that channel downstream.

THE LAW (fixb118 ruling, item 2), per writer by semantics:

* **(a) loses the conflict** — a writer that re-homes a journey BETWEEN
  LIVE PFs over the poisoned channel (entry ownership) may not overturn a
  Seg B landing: Seg B judges on an UNPOISONABLE channel (journey name ×
  PF name). Applied to ``tier2_journey_reparent``.
* **(b) wins, but is RECORDED** — when the landing PF has stopped being a
  peer feature (demoted/dissolved), moving the journey is HONEST and
  structurally forced: blocking it would leave the journey on a dead home.
  Live exhibit: tracecat ``settings``→``registry`` (B94
  ``settings_frame_demote`` demoted the whole ``settings`` PF). Such an
  overturn is not blocked — it is CLASSIFIED in the landing audit.

INVARIANT: ``silent`` == 0. Every overturn of a landing is either
forbidden or carries a recorded reason.

Flag ``WYSTAN_SEGB_LANDING_BINDING`` default OFF (armed-only).
Unset ⇒ the registry is empty ⇒ the guard is inert AND the audit stamp is
absent ⇒ byte-identical. $0, deterministic.
"""

from __future__ import annotations

import os
import threading
from typing import Any

__all__ = [
    "SEGB_LANDING_BINDING_ENV",
    "segb_landing_binding_enabled",
    "install_landing_registry",
    "uninstall_landing_registry",
    "record_segb_landing",
    "note_bound_abstain",
    "segb_landing_target",
    "run_landing_audit",
]

SEGB_LANDING_BINDING_ENV = "WYSTAN_SEGB_LANDING_BINDING"

#: Reasons an overturn of a landing is RECOGNISED as honest (case "b").
_REASON_TARGET_GONE = "target-demoted"
_REASON_UF_GONE = "journey-dropped"
_REASON_SILENT = "silent-overturn"


def segb_landing_binding_enabled() -> bool:
    """fixb118 — default **OFF** (armed-only).

    Unset ⇒ no registry, no guard, no ``scan_meta.landing_audit`` ⇒ the
    board is byte-identical to main. Explicit ``0``/false/off/no remains
    a kill-switch forever.
    """
    return os.environ.get(SEGB_LANDING_BINDING_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


class _LandingRegistry:
    """Scan-scoped registry of Seg B landings.

    The key is the stable UF id (the same one Seg B reports ``moves`` by),
    not ``id(obj)``: post-arbiter passes may rebuild the journey list, and
    CPython reuses ``id()`` after GC (the overturn-ledger lesson).
    """

    def __init__(self) -> None:
        self.landings: dict[str, str] = {}
        self.abstained: list[dict[str, Any]] = []


_active = threading.local()


def _registry() -> _LandingRegistry | None:
    return getattr(_active, "registry", None)


def install_landing_registry() -> None:
    """Activate the registry for the current thread.

    ALWAYS reassigns (not only when ON): the worker reuses threads between
    scans, so a leftover registry would bind the NEXT scan with the
    previous one's landings. OFF ⇒ an explicit ``None``, not leftovers.
    """
    _active.registry = (
        _LandingRegistry() if segb_landing_binding_enabled() else None
    )


def uninstall_landing_registry() -> None:
    _active.registry = None


def _uf_key(uf: Any) -> str:
    return str(getattr(uf, "id", None) or getattr(uf, "name", "") or "")


def record_segb_landing(uf: Any, target: str) -> None:
    """Record ONE Seg B landing — at the move site.

    Deliberately NOT from ``tele["moves"]``: that telemetry is truncated at
    40 rows (``if len(tele["moves"]) < 40``) while infisical yields 58
    moves — 18 landings would be left unprotected. Behaviour does not
    depend on a display cap.
    """
    reg = _registry()
    if reg is None:
        return
    key = _uf_key(uf)
    if key and target:
        reg.landings[key] = str(target)


def segb_landing_target(uf: Any) -> str | None:
    """The home Seg B landed this journey on (``None`` — not landed / OFF)."""
    reg = _registry()
    if reg is None:
        return None
    return reg.landings.get(_uf_key(uf))


def note_bound_abstain(
    uf: Any, home: str, wanted: str, writer: str,
) -> None:
    """Record a late writer's REFUSAL to overturn a landing (case "a")."""
    reg = _registry()
    if reg is None:
        return
    reg.abstained.append({
        "uf": _uf_key(uf),
        "name": str(getattr(uf, "name", "") or ""),
        "home": home, "wanted": wanted, "writer": writer,
    })


def run_landing_audit(
    user_flows: list[Any] | None,
    product_features: list[Any] | None,
) -> dict[str, Any] | None:
    """Q5 — emit-time reconciliation of journaled landings vs emitted homes.

    The class becomes SELF-REPORTING: every Seg B landing either survived
    or was overturned with a NAMED reason. ``None`` when the flag is off
    (no key in ``scan_meta`` ⇒ byte-identical).
    """
    reg = _registry()
    if reg is None:
        return None
    by_key = {
        _uf_key(u): u for u in (user_flows or ()) if _uf_key(u)
    }
    live_pfs = {
        str(getattr(p, "name", "") or "")
        for p in (product_features or ())
        if getattr(p, "layer", "product") == "product"
    }
    survived = 0
    overturned: list[dict[str, Any]] = []
    for uid, target in sorted(reg.landings.items()):
        uf = by_key.get(uid)
        if uf is None:
            overturned.append({
                "uf": uid, "to": target, "emitted": None,
                "reason": _REASON_UF_GONE,
            })
            continue
        emitted = str(getattr(uf, "product_feature_id", "") or "") or None
        if emitted == target:
            survived += 1
            continue
        # Case "b": the landing PF stopped being a peer feature — the move
        # is structurally forced, hence HONEST (recorded, not blocked).
        reason = (
            _REASON_TARGET_GONE if target not in live_pfs else _REASON_SILENT
        )
        overturned.append({
            "uf": uid,
            "name": str(getattr(uf, "name", "") or ""),
            "to": target, "emitted": emitted, "reason": reason,
        })
    return {
        "enabled": True,
        "landings": len(reg.landings),
        "survived": survived,
        "overturned": overturned,
        "silent": sum(
            1 for r in overturned if r["reason"] == _REASON_SILENT
        ),
        "bound_abstains": list(reg.abstained),
    }
