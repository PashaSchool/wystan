"""Stage 6.996 — B85 post-fold domain-foreignness demote (B22a-resurrection
fence).

THE CLASS (probe-canon B85, 4 probes VERIFIED; warden exhibits RefApp
'Admin'/'Conversations'): the 6.86 fold ladder lets a contributing dev carry
FOREIGN mass into a minted PF — a backend-Da route PF ends up owning the
frontend feature family (RefApp ``route:conversation`` 60 frontend files,
``route:erp-detection`` 62), resurrecting the B22a annexation class through
the fold channel the guards don't fence.

THE PASS (deterministic, $0): for each on-board product PF whose anchor is in
the mint's registry side-channel, recover the STATIC canonical domain Da
(rungs R1 id-path → R2 ENTRY/api unanimity → R3 page unanimity → R4 evidence
unanimity; ``None`` ⇒ inert — all static evidence, zero post-fold mass, the
circularity guard). Then per contributing dev, per file: mass OUTSIDE the
anchor's static containment AND across the domain/unit edge from Da is
FOREIGN and sheds. Each shed file re-homes to its natural home — the
most-specific OTHER on-board PF whose anchor's OWN static evidence claims it
(identity containment; exact-file beats prefix, longer prefix beats shorter —
never a vote, never annexation); homeless mass (shared infra — RefApp
``frontend/src/api``) lanes as ``cross_unit_isolation``. A fully-foreign dev
moves WHOLE (uuid + flows + loc ride — path_index stays valid by
construction); a mixed dev keeps its Da-side files + flows and sheds via
flowless carve devs (loc-stamped; path_index entries re-pointed). Demote ≠
delete: stripped == re-homed ∪ laned, 0 orphans.

PLACEMENT (it2 ruling — option (b), the B78-B/C/D 6.995 precedent): AFTER the
last homing writer (6.995 home-affinity gate; i16 + 6.99b behind it) and
BEFORE Stage 6.998 metrics-recompute — so (1) every downstream membership
filler has already populated the natural homes (the mint-time cut stranded
mass whose home anchor was mint-barred ``no_winning_devs`` and dissolved
supabase 'Security'/'Login' — the it1 refutation), (2) the settled journey
layer is never re-judged (B33 law), and (3) metrics/uf-loc/flow-loc/terminal
classification all consume the FINAL membership. Conflict census: every later
pass is display/LOC/telemetry (the 6.998 ledger-proven doctrine); the S3
arbiter applies only UF-home proposals; nav-parent is display-only — nothing
downstream re-annexes or reverts a strip.

SURVIVAL: a PF whose entire membership would leave pulls the whole anchor
back (I8-pullback shape — refusal is success); re-homing only ADDS members to
EXISTING PFs, so PF count is invariant by construction.

Kill-switch: armed ONLY when ``fold_evidence_weight_enabled()`` AND
``fold_evidence_demote_enabled()`` (unset ≡ 1; explicit 0/false/off/no ⇒ the
pass returns ``None`` before any mutation — no scan_meta key, byte-identical
EVW-only world).
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from wystan.pipeline_v2.spine_anchors import owned_paths_of
from wystan.pipeline_v2.stage_6_86_anchored_mint import (
    _carve_content_slug,
    _demote_anchor_inside,
    _demote_canonical_domain,
    _demote_is_foreign,
    _DEMOTE_MARKER,
    _make_demote_lane_dev,
    _demote_strip_dev,
    _SHARED_REASON_CROSS_UNIT,
    _workspace_unit_roots,
    build_platform_infrastructure_lane,
    fold_evidence_demote_enabled,
    fold_evidence_weight_enabled,
)

if TYPE_CHECKING:  # pragma: no cover — typing only
    from wystan.pipeline_v2.spine_anchors import SpineAnchor

__all__ = ["run_fold_evidence_demote"]


def _attr(o: Any, name: str, default: Any = None) -> Any:
    return o.get(name, default) if isinstance(o, dict) else getattr(o, name, default)


def _containment_spec(path: str, anchor: "SpineAnchor") -> tuple[int, int]:
    """Specificity of the anchor's static-identity claim on *path*:
    ``(2, 0)`` exact evidence file > ``(1, len)`` longest matching prefix >
    ``(0, 0)`` no claim. Structural, never a vote."""
    if (path in anchor.files or path in anchor.api_route_files
            or path in anchor.page_route_files):
        return (2, 0)
    best = 0
    for pre in anchor.prefixes:
        if (path == pre or path.startswith(pre + "/")) and len(pre) > best:
            best = len(pre)
    return (1, best) if best else (0, 0)


def _file_loc(repo_root: Path, rel: str, cache: dict[str, int]) -> int:
    """6.97-mirrored per-file LOC (same counter + exclusions) — best-effort,
    an unreadable file counts 0."""
    if rel not in cache:
        from wystan.pipeline_v2.stage_6_97_feature_loc import count_file_loc
        try:
            cache[rel] = count_file_loc(repo_root / rel, rel)
        except Exception:  # noqa: BLE001 — LOC is additive, never breaks
            cache[rel] = 0
    return cache[rel]


def _adjust_loc(row: Any, delta: int) -> None:
    """Shift an int ``loc`` by *delta* (clamped ≥ 0); ``None`` stays honest
    ``None`` (the row predates 6.97 or LOC degraded — never invent one)."""
    cur = _attr(row, "loc")
    if isinstance(cur, int):
        row.loc = max(0, cur + delta)


def run_fold_evidence_demote(
    developer_features: list[Any],
    product_features: list[Any],
    user_flows: list[Any],
    ctx: Any,
    anchor_registry: dict[str, Any] | None,
    path_index: Any = None,
    platform_infrastructure: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Run the Stage 6.996 demote. Mutates ``developer_features`` /
    ``product_features`` / ``path_index`` / ``platform_infrastructure`` in
    place; ``user_flows`` are READ-ONLY (no journey mover — B52). Returns
    telemetry for ``scan_meta.fold_evidence_demote``, or ``None`` when
    disarmed (no key ⇒ byte-identical)."""
    if not (fold_evidence_weight_enabled() and fold_evidence_demote_enabled()):
        return None
    tele: dict[str, Any] = {
        "enabled": True, "pfs_touched": 0, "devs_rehomed": 0,
        "devs_relaned": 0, "carve_home": 0, "carve_lane": 0,
        "files_rehomed": 0, "files_laned": 0, "loc_rehomed": 0,
        "loc_laned": 0, "pulled_back_pfs": 0, "uf_cross_citations": 0,
        "samples": [],
    }
    registry = anchor_registry or {}
    unit_roots = _workspace_unit_roots(ctx)
    if not registry or not unit_roots:
        tele["inert_reason"] = ("no_anchor_registry" if not registry
                                else "no_workspace_units")
        return tele

    from wystan.pipeline_v2.spine_hygiene import is_facet

    # ── board indexes ────────────────────────────────────────────────────
    pf_rows: dict[str, Any] = {}          # pf key (dev-facing) → PF row
    anchor_of_pf: dict[str, Any] = {}     # pf key → SpineAnchor
    for pf in product_features:
        key = _attr(pf, "name")
        aid = _attr(pf, "anchor_id")
        if not key or not aid:
            continue
        a = registry.get(str(aid))
        if a is None:
            continue
        pf_rows[str(key)] = pf
        anchor_of_pf[str(key)] = a

    devs_by_pf: dict[str, list[Any]] = defaultdict(list)
    for d in developer_features:
        if _attr(d, "layer", "developer") != "developer" or is_facet(d):
            continue
        pid = _attr(d, "product_feature_id")
        if pid:
            devs_by_pf[str(pid)].append(d)

    # Da per PF, computed once (form: R1-R4, unchanged from the probe canon).
    da_of_pf: dict[str, str | None] = {
        key: _demote_canonical_domain(anchor_of_pf[key], unit_roots)[0]
        for key in pf_rows
    }

    def _home_key(path: str, src_key: str) -> str | None:
        """The shed file's natural home: the most-specific OTHER on-board PF
        whose anchor's own static evidence claims *path* (exact file > longest
        prefix; tie → alpha-min key). ``None`` ⇒ homeless (lane)."""
        best_key: str | None = None
        best_spec = (0, 0)
        for key in sorted(pf_rows):
            if key == src_key:
                continue
            spec = _containment_spec(path, anchor_of_pf[key])
            if spec > best_spec:
                best_spec, best_key = spec, key
        return best_key

    # UF-citation index (READ-ONLY honesty counter): flows on devs we move.
    flow_home: dict[str, str] = {}
    for uf in user_flows or []:
        h = _attr(uf, "product_feature_id")
        if not h:
            continue
        for fid in (_attr(uf, "member_flow_ids") or []):
            flow_home[str(fid)] = str(h)

    repo_root = Path(str(_attr(ctx, "repo_path", ".") or "."))
    loc_cache: dict[str, int] = {}
    used_names: set[str] = {
        str(_attr(d, "name")) for d in developer_features if _attr(d, "name")}
    new_devs: list[Any] = []
    new_lane_devs: list[Any] = []

    # ── T5 carve-absorb (WYSTAN_TWIN_HUSK_CANONICAL, default OFF) ─────
    # Operator exhibit refapp-ticketing-twin-fragmentation, follow-up ruling:
    # a home-carve whose CONTENT STEM names an EXISTING dev on the SAME
    # target pf (RefApp: carve stem 'ticketing' → the B92-healed dev
    # 'ticketing', pf=ticketing) must ABSORB into that dev — paths/members/
    # loc ride, path_index re-points — instead of minting a Fix-D suffixed
    # row ('ticketing-2'/'-3'). GUARD: EXACT stem + EXACT pf match only;
    # cross-pf or no-match keeps the mint EXACTLY as before (never steal
    # across PFs). Same flag as the B92 Rung-B husk-canonical rescue — one
    # coherent husk/carve hygiene switch, one kill-switch byte-identity.
    # The ``carve_absorbed`` tele key is added ONLY when armed (normalize
    # does not scrub per-stage counters — a bare :0 would break OFF==main).
    from wystan.pipeline_v2.twin_collision import (
        twin_husk_canonical_enabled,
    )
    husk_canonical_on = twin_husk_canonical_enabled()
    absorb_index: dict[str, Any] = {}
    if husk_canonical_on:
        tele["carve_absorbed"] = 0
        for d0 in developer_features:
            if _attr(d0, "layer", "developer") != "developer" or is_facet(d0):
                continue
            nm = str(_attr(d0, "name") or "")
            if nm and nm not in absorb_index:
                absorb_index[nm] = d0

    def _dev_widen(dev: Any, files: list[str]) -> None:
        """Union *files* into an absorbing dev row (paths + member_files) —
        the carve-absorb twin of ``_pf_widen``. The dev keeps its own name /
        uuid / anchor / description; the carve provenance rides in the member
        evidence (structured, non-display — the B86 ruling)."""
        seen = set(str(p) for p in (_attr(dev, "paths") or []))
        dev.paths = list(_attr(dev, "paths") or []) + [
            p for p in files if p not in seen]
        mf_out = list(_attr(dev, "member_files") or [])
        seen_mf = {
            (m.get("path") if isinstance(m, dict) else getattr(m, "path", None))
            for m in mf_out}
        evidence = f"{_DEMOTE_MARKER}: carve absorbed into same-stem dev"
        from wystan.models.types import MemberFile
        for p in sorted(files):
            if p in seen_mf:
                continue
            seen_mf.add(p)
            if mf_out and isinstance(mf_out[0], dict):
                mf_out.append({"path": p, "role": "anchor", "confidence": 1.0,
                               "primary": True, "evidence": evidence})
            else:
                mf_out.append(MemberFile(
                    path=p, role="anchor", confidence=1.0, primary=True,
                    evidence=evidence))
        dev.member_files = mf_out

    def _pf_shrink(pf: Any, moved: set[str]) -> None:
        pf.paths = [p for p in (_attr(pf, "paths") or []) if str(p) not in moved]
        kept = []
        for m in (_attr(pf, "member_files") or []):
            p = m.get("path") if isinstance(m, dict) else getattr(m, "path", None)
            if p not in moved:
                kept.append(m)
        pf.member_files = kept

    def _pf_widen(pf: Any, files: list[str]) -> None:
        seen = set(str(p) for p in (_attr(pf, "paths") or []))
        pf.paths = list(_attr(pf, "paths") or []) + [
            p for p in files if p not in seen]
        mf_out = list(_attr(pf, "member_files") or [])
        seen_mf = {
            (m.get("path") if isinstance(m, dict) else getattr(m, "path", None))
            for m in mf_out}
        evidence = f"{_DEMOTE_MARKER}: re-homed to natural home"
        from wystan.models.types import MemberFile
        for p in sorted(files):
            if p in seen_mf:
                continue
            seen_mf.add(p)
            if mf_out and isinstance(mf_out[0], dict):
                mf_out.append({"path": p, "role": "anchor", "confidence": 1.0,
                               "primary": True, "evidence": evidence})
            else:
                mf_out.append(MemberFile(
                    path=p, role="anchor", confidence=1.0, primary=True,
                    evidence=evidence))
        pf.member_files = mf_out

    def _pi_repoint(files: list[str], new_uuid: str) -> None:
        if not isinstance(path_index, dict):
            return
        for p in files:
            e = path_index.get(p)
            if isinstance(e, dict) and "feature_uuid" in e:
                e["feature_uuid"] = new_uuid

    # ── the demote, sorted per PF anchor (deterministic) ─────────────────
    for src_key in sorted(pf_rows, key=lambda k: str(anchor_of_pf[k].canonical_id)):
        a = anchor_of_pf[src_key]
        da = da_of_pf[src_key]
        if da is None:
            continue  # genuinely cross-unit — inert for this PF
        contribs = sorted(devs_by_pf.get(src_key, []),
                          key=lambda x: str(_attr(x, "name") or ""))
        if not contribs:
            continue
        plan: dict[str, frozenset[str]] = {}
        owned_of: dict[str, list[str]] = {}
        for d in contribs:
            dn = str(_attr(d, "name"))
            owned = owned_paths_of(d)
            owned_of[dn] = owned
            frn = frozenset(
                p for p in owned
                if not _demote_anchor_inside(p, a)
                and _demote_is_foreign(p, da, unit_roots))
            if frn:
                plan[dn] = frn
        if not plan:
            continue
        # PF-survival pull-back (I8 shape): never empty a live PF row.
        remaining = sum(
            len(set(owned_of[str(_attr(d, "name"))])
                - plan.get(str(_attr(d, "name")), frozenset()))
            for d in contribs)
        if remaining == 0:
            tele["pulled_back_pfs"] += 1
            continue
        tele["pfs_touched"] += 1
        src_pf = pf_rows[src_key]
        for d in contribs:
            dn = str(_attr(d, "name"))
            frn = plan.get(dn, frozenset())
            if not frn:
                continue
            owned = owned_of[dn]
            by_home: dict[str | None, list[str]] = defaultdict(list)
            for p in sorted(frn):
                by_home[_home_key(p, src_key)].append(p)
            moved_loc = {p: _file_loc(repo_root, p, loc_cache) for p in frn}
            # cited-UF honesty counter (READ-ONLY): flows riding this dev
            # while UFs cite them from the source PF.
            for fl in (_attr(d, "flows") or []):
                fu = _attr(fl, "uuid")
                if fu and flow_home.get(str(fu)) == src_key:
                    tele["uf_cross_citations"] += 1
            if frn >= set(owned):
                # fully foreign — the WHOLE dev re-homes (uuid + flows + loc
                # ride; path_index stays valid: entries map to the dev uuid).
                homes = [h for h in by_home if h is not None]
                if homes:
                    n_best = max(len(by_home[h]) for h in homes)
                    tgt_key = min(h for h in homes if len(by_home[h]) == n_best)
                    d.product_feature_id = tgt_key
                    d.anchor_id = f"fold:{_DEMOTE_MARKER}-home->{src_key}"
                    if _attr(d, "shared_reason", None):
                        d.shared_reason = None
                    _pf_widen(pf_rows[tgt_key], sorted(frn))
                    _adjust_loc(pf_rows[tgt_key], sum(moved_loc.values()))
                    tele["devs_rehomed"] += 1
                    tele["files_rehomed"] += len(frn)
                    tele["loc_rehomed"] += sum(moved_loc.values())
                else:
                    d.product_feature_id = None
                    d.anchor_id = f"fold:{_DEMOTE_MARKER}-lane->{src_key}"
                    d.shared_reason = _SHARED_REASON_CROSS_UNIT
                    new_lane_devs.append(d)
                    tele["devs_relaned"] += 1
                    tele["files_laned"] += len(frn)
                    tele["loc_laned"] += sum(moved_loc.values())
                _pf_shrink(src_pf, set(frn))
                _adjust_loc(src_pf, -sum(moved_loc.values()))
            else:
                # mixed — strip in place; carve per natural home + one lane
                # carve for the homeless residue. Flows + Da-side files stay.
                _demote_strip_dev(d, frn)
                _adjust_loc(d, -sum(moved_loc.values()))
                for home in sorted(by_home, key=lambda h: (h is None, h or "")):
                    files = sorted(by_home[home])
                    files_loc = sum(moved_loc[p] for p in files)
                    if home is not None and husk_canonical_on:
                        # T5 carve-absorb: the stem the carve WOULD take
                        # (identical derivation to _make_demote_lane_dev).
                        stem = _carve_content_slug(files, donor=dn)
                        tgt = absorb_index.get(stem)
                        if (tgt is not None and tgt is not d
                                and str(_attr(tgt, "product_feature_id")
                                        or "") == str(home)):
                            _dev_widen(tgt, files)
                            _adjust_loc(tgt, files_loc)
                            _pi_repoint(files, str(_attr(tgt, "uuid") or ""))
                            _pf_widen(pf_rows[home], files)
                            _adjust_loc(pf_rows[home], files_loc)
                            tele["carve_absorbed"] += 1
                            tele["files_rehomed"] += len(files)
                            tele["loc_rehomed"] += files_loc
                            continue
                    carve = _make_demote_lane_dev(d, files, used_names)
                    used_names.add(str(_attr(carve, "name")))
                    if isinstance(_attr(carve, "loc", "absent"), (int, type(None))):
                        carve.loc = files_loc
                    new_devs.append(carve)
                    _pi_repoint(files, str(_attr(carve, "uuid") or ""))
                    if home is not None:
                        carve.product_feature_id = home
                        carve.shared_reason = None
                        carve.anchor_id = (
                            f"fold:{_DEMOTE_MARKER}-home->{src_key}")
                        # B86 ruling: description is a DISPLAY surface —
                        # human prose, no raw marker (anchor_id + member
                        # evidence keep the structured marker).
                        carve.description = (
                            f"Re-homed to natural home '{home}' "
                            "(fold-evidence demote).")
                        _pf_widen(pf_rows[home], files)
                        _adjust_loc(pf_rows[home], files_loc)
                        tele["carve_home"] += 1
                        tele["files_rehomed"] += len(files)
                        tele["loc_rehomed"] += files_loc
                        if husk_canonical_on:
                            # T5: a freshly minted home-carve becomes an
                            # absorb target for a LATER same-stem+pf carve
                            # in this run (dedups sibling carves that would
                            # otherwise take -2/-3 Fix-D suffixes).
                            absorb_index.setdefault(
                                str(_attr(carve, "name") or ""), carve)
                    else:
                        new_lane_devs.append(carve)
                        tele["carve_lane"] += 1
                        tele["files_laned"] += len(files)
                        tele["loc_laned"] += files_loc
                _pf_shrink(src_pf, set(frn))
                _adjust_loc(src_pf, -sum(moved_loc.values()))
            if len(tele["samples"]) < 20:
                tele["samples"].append({
                    "pf": a.canonical_id, "Da": da, "dev": dn,
                    "foreign": len(frn),
                    "homes": sorted(h for h in by_home if h)[:4]})

    if new_devs:
        developer_features.extend(new_devs)
    # Post-3231 lane residents still get their explainability rows (the lane
    # list was assembled earlier in the phase) — zero-loss, I22-visible.
    if new_lane_devs and platform_infrastructure is not None:
        try:
            platform_infrastructure.extend(
                build_platform_infrastructure_lane(
                    new_lane_devs, user_flows=user_flows))
        except Exception:  # noqa: BLE001 — lane rows are additive telemetry
            pass
    return tele
