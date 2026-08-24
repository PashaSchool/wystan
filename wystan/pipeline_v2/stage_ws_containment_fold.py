"""Stage 6.9967 — Pin-cycle-3 M2: ws-containment fold.

THE DISEASE (grounded, pin-cycle-3 exhibit 2; census class monorepo/nested-
package topology): a ``pnpm-workspace.yaml`` with a recursive ``packages/**``
glob greedily anchors every nested ``package.json`` as a PEER workspace
package. hoppscotch ``packages/hoppscotch-desktop`` therefore emits FIVE
sibling ``ws:`` PFs that are physically SUB-DIRECTORIES of the desktop package
(``.../src-tauri``, ``.../plugin-workspace/tauri-plugin-appload`` …) — the
tauri native shell + the bundle-loader plugin that MAKE the desktop build.
``Src Tauri`` (0 journeys, 1360 LOC) is the clearest husk: it is literally the
native shell of the package one directory up.

THE MECHANISM (no dictionary; anchor-prefix containment + a journey-guard):
  * SOURCE — a ``ws:``-anchored PF whose anchor path is a STRICT directory-
    descendant of ANOTHER ``ws:``-anchored PF's anchor path (the same
    anchor-prefix-containment logic ``devgrain_demote._ancestor_target``
    already implements, applied across ``ws:`` kinds). Top-level sibling
    packages (``packages/hoppscotch-common``, ``…-backend``, ``…-cli``,
    ``hoppscotch-agent`` — its own top-level dir, NOT nested under desktop)
    are NEVER descendants → never folded.
  * JOURNEY-GUARD (over-fold is the risk — collapsing real journeys into one
    tile) — a descendant folds into its enclosing package ONLY when EVERY
    journey it carries is REDUNDANT with the enclosing package's own scope: a
    host/shell sub-component whose journey merely restates the enclosing app's
    capability (plugin-appload ``Load app bundle in desktop shell`` ≈ desktop
    ``Load and run desktop application``). A descendant contributing a DISTINCT
    product-wide capability — the native request-transport of ``relay`` /
    ``plugin-relay`` (``Configure request authentication schemes``, ``Build
    and relay native HTTP requests``) — is NEVER folded (folding it under
    "Desktop" would MISLOCATE a product-wide transport journey). Redundancy =
    journey-name-token coverage >= ``REDUNDANCY_FLOOR`` against (enclosing
    journeys ∪ enclosing identity ∪ host/shell plumbing corroboration).

CONSERVATION: a fold MOVES the descendant's journeys (pfid → enclosing, via the
overturn-ledger rung), UNIONs its member_files + paths onto the enclosing PF,
and re-points its developer_features — 0 orphan. The enclosing PF's product
NAME already comes from its own ``package.json`` (``hoppscotch-desktop`` →
"Hoppscotch Desktop") so no new naming is minted; the descendant simply stops
existing as a row.

Gated by ``WYSTAN_WS_CONTAINMENT_FOLD`` (default **OFF**). Unset ≡ explicit
``0``/``false``/``off``/``no`` ⇒ pure no-op (byte-identical OFF-world forever;
kill-switch). No KEY_SCHEMA bump (append law; the bump rides the flip commit).

DRAW-VARIANCE CURE (``WYSTAN_FOLD_HOST_SHELL``, default **OFF**): the
journey-guard reads the LLM-drawn UF layer, which is DRAW-NOISY — the tauri
native shell ``…/src-tauri`` (0 product surfaces) flickers between kept and
folded across keyed draws because one draw mints 2-3 zero-coverage noise
journeys onto it, which the guard reads as "distinct-capability" and keeps.
The fold outcome for a host/shell is binary and JOURNEY-INDEPENDENT by nature,
so a STRUCTURAL trigger cures the flicker completely: a ws-descendant whose
member files are ~100% non-product-surface (carry ZERO web/app-source files —
``src-tauri`` is 8/8 ``.rs``; spec option b) is a native host-shell and folds
REGARDLESS of drawn journeys. Composition is deterministic (unlike the UF
layer), so the fold is stable across draws. A descendant WITH product surfaces
(``relay``/``plugin-relay`` carry TS transport SDK files; the cal.com embeds
are TS/React) is NOT a host-shell and falls through to the journey-guard,
UNCHANGED — so the product-wide transport journeys stay protected. Detected by
FILE COMPOSITION only, never a name dictionary. Default OFF ⇒ byte-identical to
the journey-guard-only world; kill-switch forever; no KEY_SCHEMA bump.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from wystan.pipeline_v2.stage_6_9965_token_journey_rehome import (
    _singular,
    _tokens,
)

if TYPE_CHECKING:  # pragma: no cover — typing only
    from wystan.models.types import Feature, UserFlow

WS_CONTAINMENT_FOLD_ENV = "WYSTAN_WS_CONTAINMENT_FOLD"
FOLD_HOST_SHELL_ENV = "WYSTAN_FOLD_HOST_SHELL"
_TRUTHY = frozenset({"1", "true", "yes", "on"})

#: product-surface (web/app source) extension canon — mirrors the codebase's
#: cross-stack ``nav_parent._CODE_EXTS`` (the same set ``conservation`` reuses;
#: NOT a per-repo list). A ws-descendant whose member files contain NONE of
#: these is native host/shell plumbing (native code + config + assets), never a
#: product surface. ``.rs`` (tauri ``src-tauri``) is deliberately absent.
_PRODUCT_SURFACE_EXTS = (
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte",
)

#: Scale-invariant coverage ratio (== the codebase's canonical AFFINITY_FLOOR /
#: DOMINANT_FLOOR): a descendant journey is "redundant" with the enclosing
#: package when >= half its distinctive tokens are already in the enclosing
#: scope. NOT a per-repo magic number.
REDUNDANCY_FLOOR = 0.5

#: host/shell plumbing tokens — corroboration set (scale-invariant, like the
#: sibling stage's ``_UI_PRIMITIVES`` / ``_GENERIC_BUCKET``). A nested package
#: whose journey is only host-shell plumbing of the enclosing app is a
#: sub-component, not a distinct product capability. Corroboration ONLY — the
#: enclosing-scope overlap is the mechanism.
HOST_SHELL_GENERIC = frozenset({
    "shell", "bundle", "host", "window", "tray", "launcher", "boot",
    "splash", "webview", "updater", "installer", "packager",
})


def ws_containment_fold_enabled() -> bool:
    """Default **ON** since the 2026-07-29 flip-pack №11 (KEY_SCHEMA 46; keyed
    exhibit-gate hoppscotch 8/8 green — Src Tauri gone, Desktop born, UF
    conserved). Unset ≡ explicit ``"1"``; explicit ``0``/``false``/``off``/
    ``no`` is the byte-identical no-op OFF-world — a kill-switch forever. The
    pre-flip truthy set is preserved LITERALLY — only the ``os.environ.get``
    default moved ``"0"`` → ``"1"``."""
    return os.environ.get(WS_CONTAINMENT_FOLD_ENV, "1").strip().lower() in _TRUTHY


def fold_host_shell_enabled() -> bool:
    """Structural host-shell fold — the draw-variance cure. Default **ON**
    since the 2026-07-31 flip-pack №14 flip (KEY_SCHEMA 49; keyed proof:
    src-tauri folded stably on both draws). Unset now arms the host-shell
    branch; explicit ``0``/``false``/``off``/``no`` (anything outside the
    truthy set) ⇒ the branch never runs and this stage is byte-identical to
    the journey-guard-only world — kill-switch forever. Only the
    ``os.environ.get`` default moved ``"0"`` -> ``"1"``; the WIDE ``_TRUTHY``
    set {"1","true","yes","on"} is preserved LITERALLY."""
    return os.environ.get(FOLD_HOST_SHELL_ENV, "1").strip().lower() in _TRUTHY


def _member_paths(pf: Any) -> list[str]:
    """Member-file paths of a PF (dict- or attr-shaped ``member_files``)."""
    out: list[str] = []
    for mf in (getattr(pf, "member_files", None) or []):
        p = mf.get("path") if isinstance(mf, dict) else getattr(mf, "path", None)
        if p:
            out.append(str(p))
    return out


def _is_host_shell(pf: Any) -> bool:
    """Structural, journey-INDEPENDENT host-shell test (spec option b): a ws-
    descendant whose member files are ~100% non-product-surface — i.e. carry
    ZERO web/app-source files — is a native host/shell (tauri ``src-tauri``:
    8/8 ``.rs``). Composition is deterministic (unlike the LLM-drawn UF layer),
    so the fold is stable across draws. A descendant with ANY product-surface
    file (``relay``'s TS transport SDK, ``plugin-relay``, the cal.com embeds) is
    NOT a host-shell and defers to the journey-guard. Detected by FILE
    COMPOSITION only — no name dictionary. Empty membership ⇒ no evidence ⇒
    defer to the journey-guard (never fold on absence of data)."""
    members = _member_paths(pf)
    if not members:
        return False
    return not any(p.lower().endswith(_PRODUCT_SURFACE_EXTS) for p in members)


def _ws_path(pf: "Feature") -> str | None:
    a = str(getattr(pf, "anchor_id", None) or "")
    return a[len("ws:"):].strip("/") if a.startswith("ws:") else None


def _j_toks(s: str | None) -> frozenset[str]:
    return frozenset(_singular(t) for t in _tokens(s)) if s else frozenset()


def _name(pf: Any) -> str:
    return str(getattr(pf, "name", "") or "")


def _is_redundant(j_tokens: frozenset[str], scope: frozenset[str]) -> bool:
    if not j_tokens:
        return True
    cov = len(j_tokens & (scope | HOST_SHELL_GENERIC)) / len(j_tokens)
    return cov >= REDUNDANCY_FLOOR


def run_ws_containment_fold(
    product_features: list["Feature"],
    user_flows: list["UserFlow"],
    developer_features: list["Feature"],
) -> dict[str, Any]:
    """Fold host/shell ``ws:`` sub-package PFs into their enclosing package PF.
    Mutates product_features / user_flows / dev stamps in place; returns
    telemetry for ``scan_meta.ws_containment_fold``."""
    from wystan.pipeline_v2.overturn_ledger import propose_pf_now

    tele: dict[str, Any] = {
        "enabled": True, "applied": False,
        "ws_pfs": 0, "descendants": [], "folded": [], "kept": [],
        "journeys_moved": 0, "devs_repointed": 0, "members_moved": 0,
    }

    ws_pfs = [(pf, p) for pf in product_features if (p := _ws_path(pf))]
    tele["ws_pfs"] = len(ws_pfs)
    if len(ws_pfs) < 2:
        return tele

    ufs_by_pf: dict[str, list["UserFlow"]] = {}
    for uf in user_flows:
        h = getattr(uf, "product_feature_id", None)
        if h:
            ufs_by_pf.setdefault(str(h), []).append(uf)

    # descendant → enclosing (longest strict-ancestor ws anchor).
    def _enclosing(path: str) -> "Feature | None":
        best: tuple[int, "Feature"] | None = None
        for opf, opath in ws_pfs:
            if opath == path:
                continue
            if path.startswith(opath + "/"):
                if best is None or len(opath) > best[0]:
                    best = (len(opath), opf)
        return best[1] if best else None

    # Decide every fold against the SAME pre-pass board (deterministic; sorted
    # by anchor path). A descendant folds iff it is a STRUCTURAL host-shell
    # (draw-variance cure, when armed) OR ALL its journeys are redundant with
    # the enclosing package's scope (the journey-guard).
    host_shell_on = fold_host_shell_enabled()
    if host_shell_on:
        tele["host_shell_folds"] = 0
    fold_plan: list[tuple["Feature", "Feature"]] = []
    for pf, path in sorted(ws_pfs, key=lambda t: t[1]):
        enc = _enclosing(path)
        if enc is None:
            continue  # top-level sibling package — never a descendant
        enc_scope: set[str] = set()
        for u in ufs_by_pf.get(_name(enc), []):
            enc_scope |= _j_toks(getattr(u, "name", None))
        enc_scope |= _j_toks(getattr(enc, "display_name", None) or _name(enc))
        ep = _ws_path(enc) or ""
        enc_scope |= _j_toks(ep.rsplit("/", 1)[-1])
        scope = frozenset(enc_scope)
        my_ufs = ufs_by_pf.get(_name(pf), [])
        # STRUCTURAL host-shell test runs BEFORE the journey-guard: a native
        # shell (0 product-surface members) folds regardless of drawn journeys.
        # A descendant with product surfaces defers to the journey-guard,
        # UNCHANGED (relay/plugin-relay transport stays protected). Flag OFF ⇒
        # host_shell is always False ⇒ this branch is inert ⇒ byte-identical.
        host_shell = host_shell_on and _is_host_shell(pf)
        if host_shell:
            redundant = True
        else:
            redundant = all(_is_redundant(_j_toks(getattr(u, "name", None)),
                                          scope)
                            for u in my_ufs)
        cov_det = [
            {"journey": str(getattr(u, "name", "") or ""),
             "cov": round(len(_j_toks(getattr(u, "name", None)) &
                              (scope | HOST_SHELL_GENERIC)) /
                          max(1, len(_j_toks(getattr(u, "name", None)))), 2)}
            for u in my_ufs
        ]
        rec = {"pf": _name(pf), "path": path, "enclosing": _name(enc),
               "journeys": len(my_ufs), "coverage": cov_det, "fold": redundant}
        if host_shell_on:
            rec["host_shell"] = host_shell
        tele["descendants"].append(rec)
        if redundant:
            if host_shell:
                tele["host_shell_folds"] += 1
            fold_plan.append((pf, enc))
        else:
            tele["kept"].append({"pf": _name(pf), "reason": "distinct-capability",
                                 "coverage": cov_det})

    if not fold_plan:
        return tele

    # A descendant never folds into another folding descendant — retarget to the
    # nearest enclosing that is itself NOT folding, so journeys/members always
    # land on a SURVIVING PF (defensive; hoppscotch/cal.com are 2-level so this
    # is a no-op, but keeps deeper nests conservation-safe — 0 orphan).
    fold_keys = {_name(d) for d, _ in fold_plan}
    enc_of = {_name(d): e for d, e in fold_plan}

    def _survivor(enc: "Feature") -> "Feature | None":
        seen: set[str] = set()
        cur = enc
        while _name(cur) in fold_keys:
            if _name(cur) in seen:
                return None  # cycle guard (never happens for a DAG of paths)
            seen.add(_name(cur))
            nxt = enc_of.get(_name(cur))
            if nxt is None:
                return None
            cur = nxt
        return cur

    for descendant, enclosing in fold_plan:
        dkey = _name(descendant)
        target = _survivor(enclosing)
        if target is None:
            tele["kept"].append({"pf": dkey, "reason": "no-surviving-enclosing"})
            continue
        enclosing = target
        ekey = _name(enclosing)
        # move journeys → enclosing (ledger rung; conservation-verified free).
        moved = 0
        for uf in ufs_by_pf.get(dkey, []):
            propose_pf_now(uf, ekey, rung="ws-containment-fold")
            if getattr(uf, "residual", False):
                uf.residual = False
            moved += 1
        tele["journeys_moved"] += moved
        # union member_files + paths onto the enclosing PF (dedup, stable order).
        seen_p = set(getattr(enclosing, "paths", None) or [])
        merged_p = list(getattr(enclosing, "paths", None) or [])
        for p in (getattr(descendant, "paths", None) or []):
            if p not in seen_p:
                seen_p.add(p)
                merged_p.append(p)
        enclosing.paths = merged_p
        seen_mf = {
            (mf.get("path") if isinstance(mf, dict) else getattr(mf, "path", None))
            for mf in (getattr(enclosing, "member_files", None) or [])
        }
        added_mf = 0
        for mf in (getattr(descendant, "member_files", None) or []):
            mfp = (mf.get("path") if isinstance(mf, dict)
                   else getattr(mf, "path", None))
            if mfp and mfp not in seen_mf:
                seen_mf.add(mfp)
                enclosing.member_files.append(mf)
                added_mf += 1
        tele["members_moved"] += added_mf
        # re-point the descendant's dev features to the enclosing package.
        repointed = 0
        for dev in developer_features:
            if str(getattr(dev, "product_feature_id", "") or "") == dkey:
                dev.product_feature_id = ekey
                if getattr(dev, "shared_reason", None):
                    dev.shared_reason = None
                repointed += 1
        tele["devs_repointed"] += repointed
        tele["folded"].append({
            "pf": dkey, "into": ekey, "journeys_moved": moved,
            "members_moved": added_mf, "devs_repointed": repointed,
        })

    # remove folded descendant PFs from the product layer (post-loop so the
    # loop snapshot is intact).
    product_features[:] = [pf for pf in product_features
                           if _name(pf) not in fold_keys]
    tele["applied"] = bool(tele["folded"])
    return tele


__all__ = [
    "WS_CONTAINMENT_FOLD_ENV",
    "FOLD_HOST_SHELL_ENV",
    "ws_containment_fold_enabled",
    "fold_host_shell_enabled",
    "run_ws_containment_fold",
]
