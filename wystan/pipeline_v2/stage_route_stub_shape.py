"""Stage 6.987b — Pin-cycle-3 M3: module-shape route-stub demote
(nav-INDEPENDENT companion to 6.987 ``devgrain_demote``).

THE DISEASE (grounded, pin-cycle-3 exhibit 3): ``pages/enter-redirect.ts`` is a
17-LOC PURE FUNCTION ``getSafeRedirectUrl()`` — an open-redirect safety
validator that renders NOTHING (no template, no component). The route-file
extractor mapped it to a route purely by the ``pages/*`` filesystem convention,
so a ``route:enter-redirect`` PF was born and the journey-namer hallucinated
``Redirect after login entry`` on top of it. 6.987 ``devgrain_demote`` WOULD
demote it (its vocab lists ``redirect``) but ABSTAINS board-wide because
hoppscotch is a Vue SPA with empty ``nav_keys`` — the nav-exemption signal is
unreadable. The durable fix is a signal that does NOT depend on nav.

THE MECHANISM (pure SHAPE — no name vocabulary, no nav dependency):
  * eligible: a ``route:``/``fdir:``-anchored PF whose source member module(s)
    render NO component. File-routed frameworks (Next.js pages, Remix routes,
    Vue ``pages/``, Nuxt) require a DEFAULT-exported page component (or an SFC);
    a ``.ts``/``.js`` in a routes dir that exports only NAMED helpers — no SFC,
    no ``defineComponent``, no ``export default``, no JSX — is a co-located
    plumbing helper the router picked up by filename, not a product surface.
  * ∧ tiny LOC (``TINY_LOC_CEIL`` — count-grain plumbing ceiling, the widget-
    micro precedent) ∧ a MICRO journey profile (<= 1 UF, every member_count
    <= 1). A rich journey set or a component-rendering member vetoes the demote
    (the nav-declared onboardings — cal.com/twenty/plane/novu — RENDER
    components and carry rich wizard journeys; module-shape never touches them).

CONSERVATION: the demoted PF's hallucinated journey is marked HONEST-RESIDUAL
(``pfid=None, residual=True`` — labeled debt, NOT dropped: auth is not
represented as a tile on this board, so the journey is never force-homed); its
devs re-point to the nearest surviving ancestor PF by anchor-prefix containment
(else stay L1/unowned exactly as a never-minted anchor's devs would); its member
files union onto that ancestor when one exists — 0 orphan.

Gated by ``WYSTAN_ROUTE_STUB_SHAPE`` (default **OFF**). Unset ≡ explicit
``0``/``false``/``off``/``no`` ⇒ pure no-op (byte-identical OFF-world forever;
kill-switch). No LLM, deterministic, scale-invariant. No KEY_SCHEMA bump.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover — typing only
    from wystan.models.types import Feature, UserFlow

ROUTE_STUB_SHAPE_ENV = "WYSTAN_ROUTE_STUB_SHAPE"
_TRUTHY = frozenset({"1", "true", "yes", "on"})

#: count-grain plumbing ceiling (the widget-micro precedent; NOT per-repo
#: tuning) — a route stub is tiny by construction.
TINY_LOC_CEIL = 60
#: a stub is a co-located single (rarely two) helper file — NOT a package. A
#: PF carrying many source files is a real module even if none renders a
#: component (novu ``@novu/stateless`` — a 25-file notification library
#: mis-anchored ``route:stateless`` with a stale loc=0 — the false-positive
#: this guard closes).
_MAX_STUB_MEMBERS = 2
_MICRO_UFS = 1
_MICRO_MEMBER_COUNT = 1

_SFC_EXTS = (".vue", ".svelte")
_JSX_EXTS = (".tsx", ".jsx")
_SOURCE_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte")
_NON_SURFACE_SUFFIXES = (".d.ts", ".spec.ts", ".spec.tsx", ".test.ts",
                         ".test.tsx", ".spec.js", ".test.js")


def _ondisk_loc(paths: list[str], repo: "Path") -> int:
    """True line-count of the source members on disk (robust against a stale
    board ``loc`` metric — the novu stateless loc=0 trap)."""
    total = 0
    for p in paths:
        try:
            total += len((repo / p).read_text(encoding="utf-8",
                                              errors="ignore").splitlines())
        except OSError:
            continue
    return total


def route_stub_shape_enabled() -> bool:
    """Default **ON** since the 2026-07-29 flip-pack №11 (KEY_SCHEMA 46; keyed
    exhibit-gate hoppscotch 8/8 green — Enter Redirect gone, journey honest-
    residual, UF conserved). Unset ≡ explicit ``"1"``; explicit ``0``/
    ``false``/``off``/``no`` is the byte-identical no-op OFF-world — a
    kill-switch forever. The pre-flip truthy set is preserved LITERALLY —
    only the ``os.environ.get`` default moved ``"0"`` → ``"1"``."""
    return os.environ.get(ROUTE_STUB_SHAPE_ENV, "1").strip().lower() in _TRUTHY


def _repo_root(ctx: Any) -> "Path | None":
    from wystan.pipeline_v2.transport_handoff import _attr
    rp = _attr(ctx, "repo_path", None)
    if rp and Path(str(rp)).is_dir():
        return Path(str(rp))
    return None


def _renders_component(path: str, repo: "Path | None") -> bool:
    """True iff the route module renders a UI component. Conservative: any
    doubt (unreadable, no live tree, non-source anchor) → True (do NOT demote).
    A named-exports-only ``.ts``/``.js`` with no default export / defineComponent
    / JSX is the ONLY non-component (stub) shape."""
    p = path.lower()
    if p.endswith(_SFC_EXTS) or p.endswith(_JSX_EXTS):
        return True  # SFC / JSX-enabled extension = component by convention
    if not p.endswith(_SOURCE_EXTS):
        return True  # non-source anchor — not our target
    if repo is None:
        return True  # no live tree (synthetic) — vacuously "renders"
    try:
        text = (repo / path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return True
    if re.search(r"\bdefineComponent\b", text):
        return True
    if re.search(r"\bexport\s+default\b", text):
        return True  # default export in a route module = the page component
    if re.search(r"return\s*<|=>\s*<|</[A-Za-z]", text):
        return True  # inline JSX
    return False  # named-exports-only helper → non-component stub


def _anchor_kind_and_tail(aid: str) -> tuple[str, str]:
    kind, _, tail = aid.partition(":")
    return kind, tail.strip("/")


def _is_module_shape_stub(
    pf: "Feature", ufs: list["UserFlow"], repo: "Path | None",
) -> tuple[bool, dict]:
    aid = str(getattr(pf, "anchor_id", None) or "")
    kind, _tail = _anchor_kind_and_tail(aid)
    if kind not in ("route", "fdir"):
        return False, {"reason": "not-route-anchored"}
    # G2 (twins-forensics, self-protecting bloat): the module-size test
    # counts OWNED members only — annexed role="shared" import-fan-in mass
    # never counts. The keyed RefApp phantom `frameworks` carried 2 anchor
    # files + 31 generic closure/fan-in files (n_src=67 with duplicates),
    # so the "not-single-helper" skip protected the phantom with its own
    # annexation bloat. A real multi-file module (novu @novu/stateless)
    # OWNS its files (role != shared) and still skips.
    src = []
    n_shared = 0
    for m in (getattr(pf, "member_files", None) or []):
        role = m.get("role") if isinstance(m, dict) else getattr(m, "role", None)
        p = str(m.get("path") if isinstance(m, dict)
                else getattr(m, "path", None))
        if not (p.lower().endswith(_SOURCE_EXTS)
                and not p.lower().endswith(_NON_SURFACE_SUFFIXES)):
            continue
        if role == "shared":
            n_shared += 1
            continue
        src.append(p)
    if not src:
        return False, {"reason": "no-source-members"}
    if len(src) > _MAX_STUB_MEMBERS:
        # a multi-file package is a real module, never a co-located stub.
        return False, {"reason": "not-single-helper", "n_src": len(src),
                       "n_shared": n_shared}
    if any(_renders_component(p, repo) for p in src):
        return False, {"reason": "renders-component"}
    # true on-disk LOC (never the stale board metric); off-tree we never reach
    # here (renders_component is vacuously True with no channel).
    loc = _ondisk_loc(src, repo) if repo is not None \
        else int(getattr(pf, "loc", 0) or 0)
    if loc > TINY_LOC_CEIL:
        return False, {"reason": "loc-over-ceil", "loc": loc}
    if loc <= 0:
        # a real stub renders SOME source; loc 0 with members on disk is a
        # metric/mis-anchor artifact, not a plumbing helper.
        return False, {"reason": "zero-loc", "loc": loc}
    if len(ufs) > _MICRO_UFS or any(
            (getattr(u, "member_count", 0) or 0) > _MICRO_MEMBER_COUNT
            for u in ufs):
        return False, {"reason": "rich-journey", "ufs": len(ufs)}
    return True, {"reason": "module-shape-stub", "loc": loc, "src": src}


def run_route_stub_shape(
    product_features: list["Feature"],
    user_flows: list["UserFlow"],
    developer_features: list["Feature"],
    ctx: Any,
) -> dict[str, Any]:
    """Demote module-shape route-stub PFs. Mutates in place; returns telemetry
    for ``scan_meta.route_stub_shape``."""
    from wystan.pipeline_v2.overturn_ledger import propose_pf_now

    tele: dict[str, Any] = {
        "enabled": True, "applied": False, "eligible": 0,
        "demoted": [], "skipped": [], "residual_journeys": 0,
        "devs_repointed": 0, "devs_unowned": 0,
    }
    if not route_stub_shape_enabled():
        tele["enabled"] = False
        return tele

    repo = _repo_root(ctx)
    tele["has_channel"] = repo is not None

    ufs_by_pf: dict[str, list["UserFlow"]] = {}
    for uf in user_flows:
        h = getattr(uf, "product_feature_id", None)
        if h:
            ufs_by_pf.setdefault(str(h), []).append(uf)

    # Phase 1 — decide against the SAME pre-pass board (sorted; deterministic).
    demote: list["Feature"] = []
    for pf in sorted(product_features,
                     key=lambda p: str(getattr(p, "name", "") or "")):
        key = str(getattr(pf, "name", "") or "")
        stub, det = _is_module_shape_stub(pf, ufs_by_pf.get(key, []), repo)
        aid = str(getattr(pf, "anchor_id", None) or "")
        kind, _ = _anchor_kind_and_tail(aid)
        if kind in ("route", "fdir"):
            tele["eligible"] += 1
        if stub:
            demote.append(pf)
        elif det.get("reason") not in ("not-route-anchored", "no-source-members"):
            tele["skipped"].append({"pf": key, **det})
    if not demote:
        return tele

    demote_keys = {str(getattr(pf, "name", "") or "") for pf in demote}

    def _anchor_path(pf: "Feature") -> str | None:
        aid = str(getattr(pf, "anchor_id", None) or "")
        if ":" not in aid:
            return None
        return aid.split(":", 1)[1].strip("/") or None

    def _ancestor_target(tail: str) -> "Feature | None":
        """Nearest SURVIVING ancestor PF by anchor-prefix containment (longest
        enclosing path-anchored capability; tie → name)."""
        best: tuple[int, str, "Feature"] | None = None
        for other in product_features:
            okey = str(getattr(other, "name", "") or "")
            if okey in demote_keys:
                continue
            opath = _anchor_path(other)
            if not opath:
                continue
            if tail.startswith(opath + "/"):
                cand = (len(opath), okey, other)
                if best is None or (cand[0], cand[1]) > (best[0], best[1]):
                    best = cand
        return best[2] if best else None

    devs_by_pf: dict[str, list["Feature"]] = {}
    for f in developer_features:
        pfid = getattr(f, "product_feature_id", None)
        if pfid:
            devs_by_pf.setdefault(str(pfid), []).append(f)

    # Phase 2 — apply (sorted; conservation by construction).
    for pf in sorted(demote, key=lambda p: str(getattr(p, "name", "") or "")):
        key = str(getattr(pf, "name", "") or "")
        aid = str(getattr(pf, "anchor_id", None) or "")
        _kind, tail = _anchor_kind_and_tail(aid)
        target = _ancestor_target(tail)
        # journeys → HONEST-RESIDUAL (never dropped; never force-homed).
        for uf in ufs_by_pf.get(key, []):
            propose_pf_now(uf, None, rung="route-stub-shape")
            uf.residual = True
            tele["residual_journeys"] += 1
        # devs → nearest surviving ancestor, else L1/unowned.
        for m in sorted(devs_by_pf.get(key, ()),
                        key=lambda d: str(getattr(d, "name", "") or "")):
            if target is not None:
                m.product_feature_id = str(getattr(target, "name", "") or "")
                if getattr(m, "shared_reason", None):
                    m.shared_reason = None
                tele["devs_repointed"] += 1
            else:
                # No surviving ancestor — L1/unowned, exactly as a never-minted
                # anchor's devs would be. The ``sub_mint_bar_surface`` stamp is
                # the established lane reason (6.86/6.987/6.9964 precedent,
                # ``lane_rehome._LANE_REASONS``) so the dev becomes an ACCOUNTED
                # platform-lane resident, never an I22 unaccounted resident
                # (the commerce ``revalidate`` gauntlet catch, flip-pack №11).
                m.product_feature_id = None
                m.shared_reason = "sub_mint_bar_surface"
                tele["devs_unowned"] += 1
        # union member_files + paths onto the ancestor (if any).
        if target is not None:
            seen_p = set(getattr(target, "paths", None) or [])
            merged_p = list(getattr(target, "paths", None) or [])
            for p in (getattr(pf, "paths", None) or []):
                if p not in seen_p:
                    seen_p.add(p)
                    merged_p.append(p)
            target.paths = merged_p
            seen_mf = {
                (mf.get("path") if isinstance(mf, dict)
                 else getattr(mf, "path", None))
                for mf in (getattr(target, "member_files", None) or [])
            }
            for mf in (getattr(pf, "member_files", None) or []):
                mfp = (mf.get("path") if isinstance(mf, dict)
                       else getattr(mf, "path", None))
                if mfp and mfp not in seen_mf:
                    seen_mf.add(mfp)
                    target.member_files.append(mf)
        tele["demoted"].append({
            "pf": key, "anchor": aid,
            "into": (str(getattr(target, "name", "") or "")
                     if target is not None else None),
            "residual_journeys": len(ufs_by_pf.get(key, [])),
        })

    product_features[:] = [
        pf for pf in product_features
        if str(getattr(pf, "name", "") or "") not in demote_keys
    ]
    tele["applied"] = bool(tele["demoted"])
    return tele


__all__ = [
    "ROUTE_STUB_SHAPE_ENV",
    "route_stub_shape_enabled",
    "run_route_stub_shape",
    "TINY_LOC_CEIL",
]
