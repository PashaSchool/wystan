"""settings_frame_demote — B94: demote a contentless settings-FRAME PF.

THE PROBLEM (operator exhibit ``settings-general-container``, canon
``pf-product-grain-prompt.md`` class 'navigation category /
settings-as-container'): the engine mints a top-level Product Feature
named after a generic settings-frame TAB — ``General`` recurs across ≥4
boards (cal.com / papermark / plane / rallly). A settings tab called
"General" is not a product capability; the journeys of an entity's settings
belong under THAT entity, not under a shared settings folder. One such row
on the board makes a reader distrust every row.

THE FIX (JSON-level; a display badge can not fix wrong data — the external
``eval/product_right_gate.py`` reads ``product_features[]`` and matches the
name, so the row must actually LEAVE the peer-feature list): a settings-frame
PF is DEMOTED from ``product_features``. Its member developer features re-home
to the nearest surviving route-ancestor PF (else L1/unowned — files always
kept); its held synthesized shell-UFs drop as artifacts; a real held journey
(the 0-1 case) is RE-HOMED to that ancestor, never deleted — and if there is
no ancestor to receive a real journey the frame is left in place (conservation
over demotion). Nothing is lost: every member file keeps a home in
``developer_features``.

THE DISCRIMINATOR — structural, NOT the bare name 'General' (the
``rule-no-magic-tuning`` / 'mechanisms, not dictionaries' law). A PF is a settings
frame iff ALL hold:

  1. its name (or display name) is a generic settings-frame WORD
     (``general`` / ``settings`` / ``preferences`` / ``advanced`` / ``misc``)
     — CORROBORATION that narrows the candidate set to names that are never a
     product entity; never the decision on its own;
  2. it carries ≤ 1 REAL (non-synthesized) journey — a settings tab with real
     journeys IS a feature (``API Keys`` / ``Security``: protected);
  3. it is NOT a nav self-reference (a category that is also its own feature);
  4. STRUCTURAL settings-home: EVERY anchor member file sits under a
     settings-context ancestor directory (``settings`` / ``account`` /
     ``my-account`` / ``preferences`` / ``admin``), OR its ``nav_parent``
     points at a settings branch. This is the load-bearing structural test —
     a ``general`` code FOLDER that is NOT under a settings ancestor
     (documenso ``components/general/``, the D3 code-folder blob — OUT of
     this mechanism's scope) fails it and is left untouched.

Vocab lives in ``stacks/nav-tree.yaml`` (data, not code — the section-landing
precedent). Flag ``WYSTAN_SETTINGS_FRAME_DEMOTE`` default OFF (armed-only;
the KEY_SCHEMA bump rides a later flip). OFF / unset ⇒ returns ``None`` before
any mutation, no ``scan_meta`` key ⇒ byte-identical to the pre-B94 engine
(kill-switch). Depends on ``run_nav_parent`` having run first only for the
optional nav-branch signal; the route-anchor signal needs nothing upstream.

Deterministic, $0 LLM, no network, read-only over the settled PF/UF/dev lists.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from functools import lru_cache
from typing import Any

from wystan.pipeline_v2.data import load_stack_yaml

__all__ = [
    "SETTINGS_FRAME_DEMOTE_ENV",
    "is_settings_frame_pf",
    "run_settings_frame_demote",
    "settings_frame_demote_enabled",
]

SETTINGS_FRAME_DEMOTE_ENV = "WYSTAN_SETTINGS_FRAME_DEMOTE"

#: ``shared_reason`` stamped on a demoted frame's re-homed devs when no
#: surviving ancestor exists (mirrors the nav-landing / devgrain demote).
_SHARED_REASON = "settings_frame_demote"

_TOKEN_RE = re.compile(r"[^a-z0-9]+")


def settings_frame_demote_enabled() -> bool:
    """B94 settings-frame demote — default **ON** since flip-pack №9 (KEY_SCHEMA
    42; 2026-07-28; exhibit-gate PASS — 'General' papermark keyless OFF 1 → ON 0
    and plane OFF 1 → ON 0). Unset ≡ explicit ``1``: the settings-frame demote
    arms. Explicit ``0`` / ``false`` / ``off`` / ``no`` (anything outside the
    truthy set) ⇒ the pass returns ``None`` before any mutation and writes no
    ``scan_meta`` key ⇒ byte-identical to the pre-B94 engine (kill-switch
    forever; inverted-kill-switch unit: unset ≡ explicit ``1``)."""
    return os.environ.get(SETTINGS_FRAME_DEMOTE_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


@lru_cache(maxsize=1)
def _cfg() -> dict:
    return load_stack_yaml("nav-tree")


@lru_cache(maxsize=1)
def _frame_name_vocab() -> frozenset[str]:
    """Generic settings-frame words (``general``/``settings``/…) — a candidate
    narrower / corroboration, never the decision. Data (``nav-tree.yaml``)."""
    return frozenset(
        str(s).strip().lower()
        for s in (_cfg().get("settings_frame_name_vocab") or ())
        if str(s).strip()
    )


@lru_cache(maxsize=1)
def _context_segments() -> frozenset[str]:
    """Universal settings-ancestor directory conventions (``settings``/
    ``account``/…) — the structural-home test. Data (``nav-tree.yaml``)."""
    return frozenset(
        str(s).strip().lower()
        for s in (_cfg().get("settings_frame_context_segments") or ())
        if str(s).strip()
    )


def _tokenize(raw: str) -> frozenset[str]:
    return frozenset(t for t in _TOKEN_RE.split(str(raw or "").lower()) if t)


def _pf_slug(pf: Any) -> str:
    return str(getattr(pf, "name", "") or "").strip().lower()


def _pf_names(pf: Any) -> frozenset[str]:
    """The name AND display-name (lowercased) — the exhibit matcher tests both,
    so the vocab narrower must too (a ``name='general'`` /
    ``display_name='General'`` split still matches)."""
    return frozenset(
        s for s in (
            str(getattr(pf, "name", "") or "").strip().lower(),
            str(getattr(pf, "display_name", "") or "").strip().lower(),
        ) if s
    )


def _pf_anchor_paths(pf: Any) -> list[str]:
    """A PF's ANCHOR member-file paths (role=='anchor'); else its ``paths``
    (member_files may be dicts or objects — mirror the house accessors)."""
    out: list[str] = []
    for mf in (getattr(pf, "member_files", None) or []):
        if isinstance(mf, dict):
            role, path = mf.get("role"), mf.get("path")
        else:
            role, path = getattr(mf, "role", None), getattr(mf, "path", None)
        if role == "anchor" and path:
            out.append(str(path))
    if out:
        return out
    return [str(p) for p in (getattr(pf, "paths", None) or []) if p]


def _dir_segments(path: str) -> list[str]:
    """The DIRECTORY segments of a path (basename dropped), lowercased, Next
    route-group parens stripped (``(dashboard)`` → ``dashboard``). The basename
    is excluded so a lone file literally named ``settings.tsx`` is not read as
    'under settings'."""
    p = str(path or "").replace("\\", "/").strip().lower()
    parts = [seg for seg in p.split("/") if seg]
    dirs = parts[:-1]  # drop basename
    out: list[str] = []
    for seg in dirs:
        s = seg.strip("()").strip()
        if s:
            out.append(s)
    return out


def _under_settings_context(path: str, segments: frozenset[str]) -> bool:
    return any(seg in segments for seg in _dir_segments(path))


def _nav_parent_is_settings(pf: Any, segments: frozenset[str]) -> bool:
    """The nav-branch signal: ``nav_parent`` (parent_id/label) tokens intersect
    the settings-context vocab (cal.com 'General' → parent 'my-account')."""
    np = getattr(pf, "nav_parent", None)
    if not isinstance(np, dict) or not np:
        return False
    toks: set[str] = set()
    for key in ("parent_id", "parent_label"):
        v = np.get(key)
        if v:
            toks |= _tokenize(str(v))
    return bool(toks & segments)


def is_settings_frame_pf(
    pf: Any, real_uf: int, name_vocab: frozenset[str],
    segments: frozenset[str],
) -> bool:
    """See the module header — the demote discriminator. Pure, no mutation;
    returns True ONLY for a contentless settings-frame PF (frame-word name,
    ≤1 real journey, non-self-ref, structural settings-home)."""
    if not (_pf_names(pf) & name_vocab):          # (1) frame-word corroboration
        return False
    if real_uf > 1:                               # (2) low-journey (0-1)
        return False
    np = getattr(pf, "nav_parent", None)          # (3) not a nav self-ref
    if isinstance(np, dict) and np:
        parent_id = str(np.get("parent_id") or "").strip().lower()
        if parent_id and parent_id == _pf_slug(pf):
            return False
    anchor_paths = _pf_anchor_paths(pf)
    if not anchor_paths:
        return False
    # (4) structural settings-home: every anchor under a settings ancestor …
    if all(_under_settings_context(p, segments) for p in anchor_paths):
        return True
    # … OR the nav_parent points at a settings branch.
    return _nav_parent_is_settings(pf, segments)


def _nav_anchor_tail(pf: Any) -> str | None:
    aid = str(getattr(pf, "anchor_id", None) or "")
    if ":" not in aid:
        return None
    return aid.split(":", 1)[1].strip("/") or None


def run_settings_frame_demote(
    product_features: list[Any],
    developer_features: list[Any] | None,
    user_flows: list[Any] | None,
) -> dict[str, Any] | None:
    """Demote settings-frame shells (in place) and return the
    ``scan_meta.settings_frame_demote`` telemetry. Returns ``None`` — no
    mutation, no key — when the flag is off (byte-identical inertness).

    Only ``product_features`` rows are removed; member devs re-home (route
    ancestor → L1/unowned, files kept); held synthesized shell-UFs drop; a real
    held journey re-homes to the ancestor if one exists, else it becomes
    ``product_feature_id=None`` + ``residual=True`` — honest labeled debt (the
    B77 / stage-6.9964 demote contract), NEVER dropped. Every file is conserved
    in ``developer_features``; every real journey survives (homed or residual)."""
    if not settings_frame_demote_enabled():
        return None
    tele: dict[str, Any] = {
        "enabled": True, "demoted": [], "abstained_not_settings": [],
        "self_ref_skipped": [], "has_journeys_skipped": [],
        "devs_repointed": 0, "devs_unowned": 0,
        "dropped_ufs": {}, "rehomed_ufs": {}, "residual_ufs": {},
    }
    products = [
        pf for pf in (product_features or [])
        if getattr(pf, "layer", "product") == "product"
    ]
    if not products:
        return tele

    name_vocab = _frame_name_vocab()
    segments = _context_segments()
    if not name_vocab or not segments:  # unconfigured data ⇒ inert
        return tele

    real_uf: dict[str, int] = {}
    held: dict[str, list[Any]] = defaultdict(list)
    for uf in (user_flows or []):
        pid = getattr(uf, "product_feature_id", None)
        if not pid:
            continue
        held[str(pid)].append(uf)
        if not getattr(uf, "synthesized", False):
            real_uf[str(pid)] = real_uf.get(str(pid), 0) + 1

    # Phase 1 — decide against the same pre-pass board (sorted → deterministic).
    candidates: list[Any] = []
    for pf in sorted(products, key=lambda p: str(getattr(p, "name", "") or "")):
        name = str(getattr(pf, "name", "") or "")
        if not (_pf_names(pf) & name_vocab):
            continue
        np = getattr(pf, "nav_parent", None)
        if isinstance(np, dict) and np:
            parent_id = str(np.get("parent_id") or "").strip().lower()
            if parent_id and parent_id == name.strip().lower():
                tele["self_ref_skipped"].append(name)
                continue
        if real_uf.get(name, 0) > 1:
            tele["has_journeys_skipped"].append(name)
            continue
        if is_settings_frame_pf(pf, real_uf.get(name, 0), name_vocab, segments):
            candidates.append(pf)
        else:
            # frame-word name that FAILED the structural settings-home gate —
            # a code-folder blob (documenso 'General') or an unrelated PF:
            # protected, never demoted on the name alone.
            tele["abstained_not_settings"].append(name)
    if not candidates:
        return tele

    cand_keys = {str(getattr(pf, "name", "") or "") for pf in candidates}
    devs_by_pf: dict[str, list[Any]] = defaultdict(list)
    for f in (developer_features or []):
        pid = getattr(f, "product_feature_id", None)
        if pid:
            devs_by_pf[str(pid)].append(f)

    surviving = [
        pf for pf in product_features
        if str(getattr(pf, "name", "") or "") not in cand_keys
    ]

    def _ancestor(tail: str | None) -> Any:
        if not tail:
            return None
        best: tuple[int, str, Any] | None = None
        for other in surviving:
            opath = _nav_anchor_tail(other)
            if not opath:
                continue
            if tail.startswith(opath + "/"):
                okey = str(getattr(other, "name", "") or "")
                cand = (len(opath), okey, other)
                if best is None or (cand[0], cand[1]) > (best[0], best[1]):
                    best = cand
        return best[2] if best else None

    # Phase 2 — apply (sorted). Every candidate demotes; a real journey with no
    # ancestor becomes honest residual debt (never dropped, never orphaned).
    dropped_uf_ids: set[int] = set()
    demoted_keys: set[str] = set()
    for pf in sorted(candidates, key=lambda p: str(getattr(p, "name", "") or "")):
        name = str(getattr(pf, "name", "") or "")
        aid = str(getattr(pf, "anchor_id", None) or "")
        target = _ancestor(_nav_anchor_tail(pf))
        held_ufs = held.get(name, [])
        real_held = [u for u in held_ufs if not getattr(u, "synthesized", False)]
        synth_held = [u for u in held_ufs if getattr(u, "synthesized", False)]

        demoted_keys.add(name)
        for m in sorted(devs_by_pf.get(name, ()),
                        key=lambda d: str(getattr(d, "name", "") or "")):
            if target is not None:
                m.product_feature_id = str(getattr(target, "name", "") or "")
                m.anchor_id = f"fold:settings-frame->{aid}"
                if getattr(m, "shared_reason", None):
                    m.shared_reason = None
                tele["devs_repointed"] += 1
            else:
                m.product_feature_id = None
                m.anchor_id = None
                m.shared_reason = _SHARED_REASON
                tele["devs_unowned"] += 1

        if synth_held:
            tele["dropped_ufs"][name] = sorted(
                str(getattr(u, "name", "") or "") for u in synth_held)
            dropped_uf_ids.update(id(u) for u in synth_held)
        if real_held:
            into = str(getattr(target, "name", "") or "") if target is not None else None
            if into is not None:
                tele["rehomed_ufs"][name] = {
                    "into": into,
                    "ufs": sorted(str(getattr(u, "name", "") or "") for u in real_held),
                }
                for u in real_held:
                    u.product_feature_id = into
            else:
                # no ancestor to receive them → honest labeled debt: kept, not
                # dropped, and NOT an orphan (residual=True is excluded from the
                # uf_orphan_no_lane census — the B77 / 6.9964 contract).
                tele["residual_ufs"][name] = sorted(
                    str(getattr(u, "name", "") or "") for u in real_held)
                for u in real_held:
                    u.product_feature_id = None
                    u.residual = True

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
            "pf": name, "anchor": aid,
            "into": (str(getattr(target, "name", "") or "")
                     if target is not None else None),
            "members": len(getattr(pf, "member_files", None) or []),
            "real_ufs_rehomed": (len(real_held) if target is not None else 0),
            "real_ufs_residual": (len(real_held) if target is None else 0),
            "synth_ufs_dropped": len(synth_held),
        })

    if not demoted_keys:
        return tele
    product_features[:] = [
        pf for pf in product_features
        if str(getattr(pf, "name", "") or "") not in demoted_keys
    ]
    if dropped_uf_ids and user_flows is not None:
        user_flows[:] = [u for u in user_flows if id(u) not in dropped_uf_ids]
    return tele
