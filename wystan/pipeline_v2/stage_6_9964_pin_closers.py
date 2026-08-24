"""Stage 6.9964 — B90 pin-closers: transport-donor PF lane + api-root-stub demote.

Two independent post-UF masquerader classes, each closing a pinned operator
exhibit (canon: pf-product-grain-prompt §7 — the exhibit gate; pins
``cal-trpc-pf-visible`` "why am I seeing tRPC again" and
``cal-link-api-route-stub`` "Link — I keep seeing odd product features"):

Seg A — ``WYSTAN_TRANSPORT_PF_LANE`` (default OFF): a PF whose anchor is a
TRANSPORT-DONOR workspace package (source of truth = the B88
:class:`~wystan.pipeline_v2.ws_blob_domain_drain.TransportDonorResolver` —
``server/routers`` tree or a ``@trpc/*`` dependency, a MECHANISM, never a
name) does not render as a product feature: transport is a delivery layer the
journeys only PASS THROUGH (canon §"Transport/wiring"). The PF row converts
to a platform-infrastructure lane resident by the 6.985 handoff mechanics
(devs → instrument lane residents, flowful devs carry the B52
``FLOWFUL_LANE_ANCHOR`` provenance marker); its REAL member journeys become
B52 lane-row references (``product_feature_id=None`` + ``lane_ref`` +
``surface_scope='platform_infrastructure'``) that the DOWNSTREAM Stage 6.9965
token re-home either moves to their entity PF or leaves honestly laned —
nothing real is dropped. SYNTH backstop journeys (artifacts of the PF's own
existence — ``uncovered_product_feature_backstop``) drop with named
telemetry, the devgrain precedent. Why the 6.985 handoff missed the class:
the B48 detector emits fdir-shaped ``transport_candidates`` only — a
ws-anchored donor PF (cal.com ``ws:packages/trpc``, world-39: 18.6K LOC,
0 UFs) never entered that channel (VERIFIED, world-39 keyed telemetry).

Seg B — ``WYSTAN_API_STUB_DEMOTE`` (default OFF): a ``route:``-anchored PF
mounted DIRECTLY at an ``api`` path segment (parent segment == ``api`` — the
api-ROOT-leaf shape; canon §"Route stub") with ZERO product evidence — no
``nav_parent``, no authored view component among its member paths (the
mint's ``api_only_surface``-lift prongs re-checked at post-UF grain) — AND a
MICRO journey profile: ≤ 1 held member journey, every member with
``member_count`` ≤ 3 (the devgrain count-grain constant, imported not
copied) — is not a product feature. The micro profile is the
CHANNEL-ROBUST form (GATE-0 v2): on the keyed channel the stub's only
journey is a synthesized backstop; on the keyless channel it is a
non-synthesized mc=1 route-echo template ("Browse & filter API links") —
a real-UF-count prong would be keyed-only and leave the keyless census
diseased. A substantive journey set always vetoes (cal ``custom-inputs``
mc=8, ``selected-calendars`` held=2, midday ``health`` mc=9 — the B33
twenty-Onboarding lesson at this class's grain).

Demote = the devgrain mechanics: PF row removed, SYNTH member journeys drop
with named telemetry, REAL (non-synthesized) member journeys are NEVER
dropped — they move to ``product_feature_id=None`` + ``residual=True``
(honest labeled debt, B77 contract; named in telemetry) and the DOWNSTREAM
6.9965 token re-home either moves them to their entity PF or leaves them
residual — the mandate's "an honest residual is ok" ruling for exactly this UF
class. Devs re-point to the nearest surviving ancestor PF by anchor-prefix
containment (else the I9 rider / unowned path). The api-ROOT scope is
load-bearing: a deep api route (``api/<provider>/<leaf>`` — midday
``gocardless/reconnect``, ``enablebanking/session``, ``webhook/registered``)
lives in a provider/domain scope and is OUT of this class (GATE-0 named
anti-cases); a real api product (papermark ``Links`` — held=2 + authored
view) and a non-api route (twenty ``File Upload``) never trip the predicate.

WHY THIS SLOT (wall-order, B74-B law): after the whole homing family
(6.99/6.99b/6.995/6.996/6.997) so the journey layer is final when evidence is
judged, and BEFORE the 6.9965 token re-home, so a laned donor's real journeys
are token-re-homed (or honestly laned) in the same scan — and before 6.998
metrics-recompute / terminal classification, which must see the final board.

Deterministic, $0 LLM, scale-invariant (structural predicates + count-grain
zero-tests only). Both flags flip to default **ON** in flip-pack №7
(KEY_SCHEMA 40, 2026-07-24, operator-ratified): Seg A (``TRANSPORT_PF_LANE``)
in the pack's FIRST flip commit that carries the bump, Seg B
(``API_STUB_DEMOTE``) in the pack's SECOND flip commit. Explicit
``0``/``false``/``off``/``no`` stays a kill-switch forever (unset ≡
explicit ``"1"``, byte-identical to the pre-B90 pipeline).

B91 H4 — ``WYSTAN_API_CONTAINER_DEMOTE`` (default OFF): the
api-container discriminator, an EXTENSION of the Seg B demote family at
the same seam (ruling: not a new stage). A CONTAINER-anchored PF
(``dev:``/``fdir:``/``ws:``/``pypkg:`` — the shapes B90 Seg B never
judged; ``route:`` is out of scope by the binding B91 ruling — nothing
Seg B judged or spared on route evidence is re-litigated; ``hub:`` is out
by the integration doctrine, integration = its own PF) demotes ⇔ ALL FIVE
conjuncts hold (2026-07-24 probe: perfect separation 10/10 containers /
0 false-demotes on 19 must-survive; every axis alone over-kills):

    plumb_frac ≥ 0.8       # ≥80 % of member files in route-handler /
                           # transport / dto / plumbing shapes (existing
                           # classifiers only: profile FileRole,
                           # analyzer infra test, authored data-shape
                           # vocab via the B26 normalize mechanism)
  ∧ authored_view == 0     # no authored client view member (the mint's
                           # _VIEW_COMPONENT_EXTS, single source)
  ∧ ¬nav_evidence          # no nav_parent (the author's IA word)
  ∧ ¬journey_evidence      # JOURNEY VETO: no REAL (non-synthesized)
                           # member UF — a synth backstop is an artifact
                           # of the PF's own existence, never a defense
  ∧ ¬B48_sacred_veto       # SDK / integration / embed / published-CLI
                           # families (the mint's OWN tech-instrument
                           # verdicts read back from scan_meta —
                           # feishucalendar-class protection)

Demote = the Seg B house mechanics verbatim (PF row removed, synth
members drop with named telemetry, real members would become honest
residuals — vacuous by the journey veto, kept for conservation
symmetry; devs fold to the surviving anchor-ancestor / I9 rider /
honest unowned). Closes the operator pin ``refapp-api-dev-container``
("'API' (dev:api) is a delivery layer, not a product capability").
"""

from __future__ import annotations

import os
from collections import Counter
from typing import TYPE_CHECKING, Any

from wystan.pipeline_v2.overturn_ledger import propose_pf_now

if TYPE_CHECKING:  # pragma: no cover — typing only
    from wystan.models.types import Feature

__all__ = [
    "API_CONTAINER_DEMOTE_ENV",
    "API_STUB_DEMOTE_ENV",
    "ROUTE_RENDER_UTIL_DEMOTE_ENV",
    "TRANSPORT_PF_LANE_ENV",
    "api_container_demote_enabled",
    "api_root_stub_leaf",
    "api_stub_demote_enabled",
    "b48_sacred_units",
    "container_anchor_path",
    "container_plumb_frac",
    "has_api_stub_product_evidence",
    "is_phantom_page_render_util",
    "is_plumbing_shape_file",
    "nav_seam_keys",
    "route_render_anchor_tail",
    "route_render_util_demote_enabled",
    "run_api_container_demote",
    "run_api_stub_demote",
    "run_route_render_util_demote",
    "run_transport_pf_lane",
    "transport_pf_lane_enabled",
]

TRANSPORT_PF_LANE_ENV = "WYSTAN_TRANSPORT_PF_LANE"
API_STUB_DEMOTE_ENV = "WYSTAN_API_STUB_DEMOTE"
API_CONTAINER_DEMOTE_ENV = "WYSTAN_API_CONTAINER_DEMOTE"
ROUTE_RENDER_UTIL_DEMOTE_ENV = "WYSTAN_ROUTE_RENDER_UTIL_DEMOTE"

#: The never-minted semantic for devs left with no surviving ancestor PF —
#: mirrors stage_6_86's / devgrain's ``_SHARED_REASON_BAR``.
_SHARED_REASON_BAR = "sub_mint_bar_surface"


def transport_pf_lane_enabled() -> bool:
    """B90 Seg A — default **ON** since the 2026-07-24 flip-pack №7 flip
    (KEY_SCHEMA 40; live keyed cal proof: the ``ws:packages/trpc`` donor PF is
    ABSENT, 0 journeys in trpc, conservation 139→139 named; KS byte-ident).
    Unset now arms the transport-donor PF lane. Explicit ``0``/``false``/
    ``off``/``no`` is the kill-switch forever (byte-identical to the pre-B90
    pipeline). The pre-flip truthy set ``{"1", "true"}`` is preserved
    LITERALLY — only the ``os.environ.get`` default moved ``"0"`` -> ``"1"``
    (unset ≡ explicit ``"1"``)."""
    return os.environ.get(TRANSPORT_PF_LANE_ENV, "1").strip().lower() in {
        "1", "true",
    }


def api_stub_demote_enabled() -> bool:
    """B90 Seg B — default **ON** since the 2026-07-24 flip-pack №7 flip
    (KEY_SCHEMA 40; live keyed cal proof: the ``route:…/api/link`` stub PF is
    ABSENT, C6 micro-profile channel-robust, anti-cases named [papermark
    Links / twenty File Upload / midday Session-family alive], SACRED B48
    intact). Unset now arms the api-root-stub PF demote. Explicit ``0``/
    ``false``/``off``/``no`` is the kill-switch forever (byte-identical to the
    pre-B90 pipeline). The pre-flip truthy set ``{"1", "true"}`` is preserved
    LITERALLY — only the ``os.environ.get`` default moved ``"0"`` -> ``"1"``
    (unset ≡ explicit ``"1"``)."""
    return os.environ.get(API_STUB_DEMOTE_ENV, "1").strip().lower() in {
        "1", "true",
    }


def api_container_demote_enabled() -> bool:
    """B91 H4 — api-container discriminator. Default **ON** since the
    2026-07-27 flip-pack №8 flip (KEY_SCHEMA 41; keyed novu proof: the
    ``dev:api`` Dto container PF is ABSENT, journey veto + B48 sacred veto
    protect the 19 must-survive). A container-anchored PF (``dev:``/``fdir:``/
    ``ws:``/``pypkg:``) that is ≥ 80 % plumbing mass with ZERO authored views,
    no nav declaration, no REAL member journey and no B48 sacred protection is
    a delivery-layer container, not a product feature (canon §"Transport/
    wiring" + §"Structural container"; closes the operator pin
    ``refapp-api-dev-container``). Unset now arms the demote. Explicit ``0``/
    ``false``/``off``/``no`` is the kill-switch forever (byte-identical to the
    pre-B91 pipeline). The pre-flip truthy set ``{"1", "true"}`` is preserved
    LITERALLY — only the ``os.environ.get`` default moved ``"0"`` -> ``"1"``
    (unset ≡ explicit ``"1"``)."""
    return os.environ.get(API_CONTAINER_DEMOTE_ENV, "1").strip().lower() in {
        "1", "true",
    }


def route_render_util_demote_enabled() -> bool:
    """B93 — route-render-util discriminator. Default **ON** since the
    2026-07-27 flip-pack №8 flip (KEY_SCHEMA 41; keyless novu proof: the
    phantom ``route:…/shared/html`` "HTML" PF is ABSENT, HTML exhibit §7
    CLOSED, anti-cases survive [plane Core 14 .tsx views, reactive-resume
    HTML/PDF export, langfuse Batch Exports]). A ``route:``-anchored PF whose
    PAGE surface is a BACKEND render-util file (a non-view ``*page.{ts,js}``
    file that FALSELY tripped the App-Router page-suffix gate — no authored
    view, no nav, no substantive journey) is a phantom product page, not a
    product feature (canon §"Route stub" + §"Infra utility"; closes the
    operator pin ``novu-html-route-markup``). Unset now arms the demote.
    Explicit ``0``/``false``/``off``/``no`` is the kill-switch forever
    (byte-identical to the pre-B93 pipeline). The pre-flip truthy set
    ``{"1", "true"}`` is preserved LITERALLY — only the ``os.environ.get``
    default moved ``"0"`` -> ``"1"`` (unset ≡ explicit ``"1"``)."""
    return os.environ.get(
        ROUTE_RENDER_UTIL_DEMOTE_ENV, "1").strip().lower() in {"1", "true"}


def _attr(o: Any, name: str, default: Any = None) -> Any:
    return o.get(name, default) if isinstance(o, dict) else getattr(o, name, default)


def _pf_key(pf: Any) -> str:
    return str(_attr(pf, "id") or _attr(pf, "name") or "")


def _feature_paths(feature: Any) -> "list[str]":
    """All membership paths of a Feature — ``paths`` plus
    ``member_files[].path`` (the invariant_hooks evidence-surface shape)."""
    paths = [str(p) for p in (_attr(feature, "paths") or [])]
    for mf in _attr(feature, "member_files") or []:
        p = mf.get("path") if isinstance(mf, dict) else getattr(mf, "path", None)
        if p:
            paths.append(str(p))
    return paths


# ── Seg B predicates (shared with the 6.9964 invariant hooks) ────────────


def api_root_stub_leaf(anchor_id: str) -> str | None:
    """The leaf segment when *anchor_id* is a ``route:`` anchor mounted
    DIRECTLY at an ``api`` path segment (``…/api/<leaf>``), else ``None``.
    Structural position, not a name test: ``api/link`` trips;
    ``api/gocardless/reconnect`` (provider scope) and ``file-upload``
    (no api segment) do not."""
    kind, _, tail = str(anchor_id or "").partition(":")
    if kind != "route":
        return None
    segs = [s for s in tail.strip("/").split("/") if s]
    if len(segs) >= 2 and segs[-2].lower() == "api":
        return segs[-1]
    return None


def has_api_stub_product_evidence(pf: Any) -> bool:
    """The mint's ``api_only_surface``-lift evidence prongs at POST-UF grain:
    a stamped ``nav_parent`` (the author's IA word) or an authored view
    component among the member paths. Flows are DELIBERATELY not a prong
    (every minted route PF owns flows — the prong would be vacuous; the
    mint's own api_only_surface lift excludes them too). Journey evidence is
    a SEPARATE, channel-robust micro-profile test (:func:`is_micro_profile`).
    Reuses the mint's ``_VIEW_COMPONENT_EXTS`` (single source of truth)."""
    from wystan.pipeline_v2.stage_6_86_anchored_mint import (
        _VIEW_COMPONENT_EXTS,
    )
    if _attr(pf, "nav_parent"):
        return True
    return any(p.endswith(_VIEW_COMPONENT_EXTS) for p in _feature_paths(pf))


def is_micro_profile(members: list[Any]) -> bool:
    """The stub journey profile — ≤ 1 held member journey AND every member
    ``member_count`` ≤ the devgrain count-grain constant (imported, not a
    new number). Channel-robust: catches both the keyed synth backstop and
    the keyless mc=1 route-echo template; any substantive journey set
    (held > 1 or a member with mc > 3) vetoes."""
    from wystan.pipeline_v2.devgrain_demote import (
        _MAX_PROFILE_MEMBER_COUNT,
    )
    if len(members) > 1:
        return False
    return all(
        (_attr(u, "member_count") or 0) <= _MAX_PROFILE_MEMBER_COUNT
        for u in members
    )


# ── Seg A — transport-donor PF lane ──────────────────────────────────────


def run_transport_pf_lane(
    product_features: list["Feature"],
    developer_features: list["Feature"],
    user_flows: list[Any],
    ctx: Any,
) -> dict[str, Any]:
    """See module docstring (Seg A). Mutates ``product_features`` /
    ``user_flows`` / dev stamps in place; returns telemetry for
    ``scan_meta.transport_pf_lane``."""
    tele: dict[str, Any] = {
        "enabled": True, "donor_keys": [], "laned": [],
        "ufs_laned": 0, "ufs_dropped_synth": {}, "devs_laned": 0,
    }
    if not transport_pf_lane_enabled():
        tele["enabled"] = False
        return tele
    # B88 resolver = the single source of donor truth (REUSE, never a copy).
    from wystan.pipeline_v2.ws_blob_domain_drain import (
        build_transport_donor_resolver,
    )
    resolver = build_transport_donor_resolver(
        product_features, developer_features, ctx)
    if resolver is None or not resolver.donor_pf_keys:
        return tele  # no transport donor ⇒ byte-inert board
    tele["donor_keys"] = sorted(resolver.donor_pf_keys)

    donors = [
        pf for pf in product_features
        if _pf_key(pf) in resolver.donor_pf_keys
    ]
    if not donors:
        return tele

    from wystan.pipeline_v2.stage_6_86_anchored_mint import (
        _SHARED_REASON_INSTRUMENT,
    )
    from wystan.pipeline_v2.transport_handoff import FLOWFUL_LANE_ANCHOR

    ufs_by_pf: dict[str, list[Any]] = {}
    for u in user_flows:
        pid = _attr(u, "product_feature_id")
        if pid:
            ufs_by_pf.setdefault(str(pid), []).append(u)
    devs_by_pf: dict[str, list[Any]] = {}
    for f in developer_features:
        if _attr(f, "layer", "developer") != "developer":
            continue
        pid = _attr(f, "product_feature_id")
        if pid:
            devs_by_pf.setdefault(str(pid), []).append(f)

    dropped_uf_ids: set[int] = set()
    laned_keys: set[str] = set()
    for pf in sorted(donors, key=_pf_key):
        key = _pf_key(pf)
        members = ufs_by_pf.get(key, [])
        real = [u for u in members if not _attr(u, "synthesized")]
        synth = [u for u in members if _attr(u, "synthesized")]

        # devs → lane residents (the 6.985 handoff mechanics: instrument
        # reason; a FLOWFUL dev carries the B52 provenance marker so the
        # lane builder keys its flow_ids[]).
        cand_devs = sorted(
            devs_by_pf.get(key, ()), key=lambda d: str(_attr(d, "name") or ""))
        flow_owner: dict[str, str] = {}
        for f in cand_devs:
            propose_pf_now(f, None, rung="b90_transport_lane")
            f.shared_reason = _SHARED_REASON_INSTRUMENT
            if _attr(f, "flows") or []:
                f.anchor_id = FLOWFUL_LANE_ANCHOR
            fu = str(_attr(f, "uuid") or "")
            for fl in (_attr(f, "flows") or []):
                fuid = _attr(fl, "uuid")
                if fuid:
                    flow_owner[str(fuid)] = fu
            tele["devs_laned"] += 1
        anchor_default = ""
        if cand_devs:
            anchor_default = str(_attr(sorted(
                cand_devs,
                key=lambda f: (-len(_attr(f, "flows") or []),
                               str(_attr(f, "name") or "")))[0], "uuid") or "")

        # SYNTH backstops drop with named telemetry (artifacts of the PF's
        # existence, never recall — the devgrain precedent).
        if synth:
            tele["ufs_dropped_synth"][key] = sorted(
                str(_attr(u, "name") or "") for u in synth)
            dropped_uf_ids.update(id(u) for u in synth)

        # REAL journeys → B52 lane-row references; the downstream 6.9965
        # token re-home moves them to their entity PF or leaves them
        # honestly laned (labeled debt) — never dropped.
        for u in sorted(real, key=lambda x: str(_attr(x, "id") or "")):
            votes: Counter = Counter()
            for mid in (_attr(u, "member_flow_ids") or []):
                owner = flow_owner.get(str(mid))
                if owner:
                    votes[owner] += 1
            anchor = anchor_default
            if votes:
                top_uuid, ct = sorted(
                    votes.items(), key=lambda kv: (-kv[1], kv[0]))[0]
                if ct * 2 > sum(votes.values()):
                    anchor = str(top_uuid)
            propose_pf_now(u, None, rung="b90_transport_lane")
            u.lane_ref = anchor
            u.surface_scope = "platform_infrastructure"
            tele["ufs_laned"] += 1

        laned_keys.add(key)
        tele["laned"].append({
            "pf": key,
            "anchor": str(_attr(pf, "anchor_id") or ""),
            "loc": _attr(pf, "loc"),
            "ufs_real_laned": len(real),
            "ufs_synth_dropped": len(synth),
            "devs": len(cand_devs),
        })

    # the donor PF rows leave the product layer (→ lane).
    product_features[:] = [
        pf for pf in product_features if _pf_key(pf) not in laned_keys
    ]
    if dropped_uf_ids:
        user_flows[:] = [u for u in user_flows if id(u) not in dropped_uf_ids]
    return tele


# ── Seg B — api-root-stub PF demote ──────────────────────────────────────


def run_api_stub_demote(
    developer_features: list["Feature"],
    product_features: list["Feature"],
    user_flows: list[Any],
    nav_keys: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """See module docstring (Seg B). Mutates ``product_features`` /
    ``user_flows`` / dev stamps in place; returns telemetry for
    ``scan_meta.api_stub_demote``. Signature/mechanics mirror
    :func:`~wystan.pipeline_v2.devgrain_demote.run_devgrain_demote`
    (the post-UF demote house pattern)."""
    tele: dict[str, Any] = {
        "enabled": True, "eligible": 0,
        "demoted": [], "abstained": [],
        "dropped_ufs": {}, "residual_ufs": {},
        "devs_repointed": 0, "devs_unowned": 0,
    }
    if not api_stub_demote_enabled():
        tele["enabled"] = False
        return tele
    if not nav_keys:
        # Board-wide honest abstain (the devgrain precedent): the nav
        # evidence prong is unreadable — a nav-declared api-root PF (cal
        # ``logo``) could not defend itself, so the pass acts on nothing.
        tele["nav_abstained"] = True
        return tele

    ufs_by_pf: dict[str, list[Any]] = {}
    for uf in user_flows:
        pid = _attr(uf, "product_feature_id")
        if pid:
            ufs_by_pf.setdefault(str(pid), []).append(uf)

    # Phase 1 — decide every demotion against the SAME pre-pass board
    # (deterministic: sorted by PF name; no order-dependent cascades).
    demote: list["Feature"] = []
    for pf in sorted(product_features,
                     key=lambda p: str(_attr(p, "name") or "")):
        key = str(_attr(pf, "name") or "")
        aid = str(_attr(pf, "anchor_id") or "")
        leaf = api_root_stub_leaf(aid)
        if leaf is None:
            continue
        tele["eligible"] += 1
        members = ufs_by_pf.get(key, [])
        if has_api_stub_product_evidence(pf) or not is_micro_profile(members):
            reasons = []
            if _attr(pf, "nav_parent"):
                reasons.append("nav")
            if len(members) > 1:
                reasons.append(f"held={len(members)}")
            elif members and (_attr(members[0], "member_count") or 0) > 3:
                reasons.append(f"mc={_attr(members[0], 'member_count')}")
            if not reasons:
                reasons.append("authored_view")
            tele["abstained"].append({"pf": key, "evidence": reasons})
            continue
        demote.append(pf)
    if not demote:
        return tele

    demote_keys = {str(_attr(pf, "name") or "") for pf in demote}

    def _anchor_path(pf: "Feature") -> str | None:
        aid = str(_attr(pf, "anchor_id") or "")
        if ":" not in aid:
            return None
        return aid.split(":", 1)[1].strip("/") or None

    def _ancestor_target(tail: str) -> "Feature | None":
        """Nearest SURVIVING ancestor PF by anchor-prefix containment
        (longest enclosing path-anchored capability; tie → name) — the
        devgrain fold semantics."""
        best: tuple[int, str, "Feature"] | None = None
        for other in product_features:
            okey = str(_attr(other, "name") or "")
            if okey in demote_keys or okey.strip().lower() in (
                "platform", "shared-platform",
            ):
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
        if _attr(f, "layer", "developer") != "developer":
            continue
        pid = _attr(f, "product_feature_id")
        if pid:
            devs_by_pf.setdefault(str(pid), []).append(f)

    # I9 rider (the devgrain B37-ph2 mechanics): a demoted PF's FLOWFUL dev
    # must never fall to the platform lane — home it by the dispatch-homing
    # target-owner machinery, else keep it L1/unowned but OUT of the lane.
    from wystan.pipeline_v2.dispatch_homing import (
        build_anchor_owner_resolver,
        dispatch_homing_enabled,
    )
    _i9_on = dispatch_homing_enabled()
    if _i9_on:
        tele["devs_i9_homed"] = 0
        tele["devs_flowful_unowned"] = 0
    _surviving_pfs = [
        pf for pf in product_features
        if str(_attr(pf, "name") or "") not in demote_keys
        and str(_attr(pf, "name") or "").strip().lower()
        not in ("platform", "shared-platform")
    ]
    _surviving_keys = {str(_attr(pf, "name") or "") for pf in _surviving_pfs}
    _owner_resolve = (
        build_anchor_owner_resolver(_surviving_pfs) if _i9_on else None)

    def _flowful_owner_key(dev: "Feature") -> str | None:
        if _owner_resolve is None:
            return None
        owners = [
            k for k in (
                _owner_resolve(_attr(fl, "entry_point_file"))
                for fl in (_attr(dev, "flows") or [])
            ) if k
        ]
        if not owners:
            return None
        top, ct = sorted(
            Counter(owners).items(), key=lambda kv: (-kv[1], kv[0]))[0]
        if ct * 2 <= len(owners) or top not in _surviving_keys:
            return None
        return top

    # Phase 2 — apply (sorted; the devgrain / husk-post-uf-fold mechanics).
    dropped_uf_ids: set[int] = set()
    for pf in sorted(demote, key=lambda p: str(_attr(p, "name") or "")):
        key = str(_attr(pf, "name") or "")
        aid = str(_attr(pf, "anchor_id") or "")
        tail = aid.split(":", 1)[1].strip("/") if ":" in aid else ""
        # SYNTH members (artifacts of the PF's existence) drop with named
        # telemetry; REAL members are NEVER dropped — honest residual
        # (pfid=None + residual=True, named), resolved by the downstream
        # 6.9965 token re-home or left as labeled debt (B77).
        members = ufs_by_pf.get(key, [])
        synth = [u for u in members if _attr(u, "synthesized")]
        real = [u for u in members if not _attr(u, "synthesized")]
        dropped = sorted(str(_attr(u, "name") or "") for u in synth)
        if dropped:
            tele["dropped_ufs"][key] = dropped
            dropped_uf_ids.update(id(u) for u in synth)
        if real:
            tele["residual_ufs"][key] = sorted(
                str(_attr(u, "name") or "") for u in real)
            for u in sorted(real, key=lambda x: str(_attr(x, "id") or "")):
                propose_pf_now(u, None, rung="b90_api_stub")
                u.residual = True
        target = _ancestor_target(tail)
        for m in sorted(devs_by_pf.get(key, ()),
                        key=lambda d: str(_attr(d, "name") or "")):
            if target is not None:
                propose_pf_now(
                    m, str(_attr(target, "name") or ""), rung="b90_api_stub")
                m.anchor_id = f"fold:b90-api-stub->{aid}"
                if _attr(m, "shared_reason"):
                    m.shared_reason = None
                tele["devs_repointed"] += 1
            else:
                owner_key = (
                    _flowful_owner_key(m)
                    if (_i9_on and _attr(m, "flows")) else None)
                if owner_key is not None:
                    propose_pf_now(m, owner_key, rung="b90_api_stub")
                    m.anchor_id = f"fold:b90-api-stub-i9->{aid}"
                    if _attr(m, "shared_reason"):
                        m.shared_reason = None
                    tele["devs_i9_homed"] += 1
                elif _i9_on and _attr(m, "flows"):
                    propose_pf_now(m, None, rung="b90_api_stub")
                    m.anchor_id = None
                    m.shared_reason = None
                    tele["devs_flowful_unowned"] += 1
                else:
                    propose_pf_now(m, None, rung="b90_api_stub")
                    m.anchor_id = None
                    m.shared_reason = _SHARED_REASON_BAR
                    tele["devs_unowned"] += 1
        # paths + member_files union onto the target (dedup, stable order).
        if target is not None:
            seen_p = set(_attr(target, "paths") or [])
            merged_p = list(_attr(target, "paths") or [])
            for p in (_attr(pf, "paths") or []):
                if p not in seen_p:
                    seen_p.add(p)
                    merged_p.append(p)
            target.paths = merged_p
            seen_mf = {
                (mf.get("path") if isinstance(mf, dict)
                 else getattr(mf, "path", None))
                for mf in (_attr(target, "member_files") or [])
            }
            for mf in (_attr(pf, "member_files") or []):
                mfp = (mf.get("path") if isinstance(mf, dict)
                       else getattr(mf, "path", None))
                if mfp and mfp not in seen_mf:
                    seen_mf.add(mfp)
                    target.member_files.append(mf)
        tele["demoted"].append({
            "pf": key, "anchor": aid,
            "into": (str(_attr(target, "name") or "")
                     if target is not None else None),
            "ufs_dropped": len(dropped),
            "ufs_residual": len(real),
        })

    product_features[:] = [
        pf for pf in product_features
        if str(_attr(pf, "name") or "") not in demote_keys
    ]
    if dropped_uf_ids:
        user_flows[:] = [u for u in user_flows if id(u) not in dropped_uf_ids]
    return tele


# ── B91 H4 — api-container discriminator ────────────────────────────────

#: Anchor kinds that denote a STRUCTURAL CONTAINER the developer named for
#: code organisation (canon §"Structural container") — the H4 universe.
#: ``route:`` is EXCLUDED by the binding B91 scope ruling (2026-07-25):
#: whatever the B90 Seg B api-root-stub arm judged — or spared on route
#: evidence — is never re-litigated here. ``hub:`` is EXCLUDED by the
#: integration doctrine (integration = its own PF, a BINDING law): the
#: B91 census showed hub-kind eligibility would sweep real integration
#: units the tech-instrument detector never vetoed (RefApp ERP family).
_CONTAINER_KINDS = frozenset({"dev", "fdir", "ws", "pypkg"})

#: The tech-instrument PRODUCT-veto reasons that mark a unit SACRED —
#: the mint's ``_sacred_veto_reasons`` (B48 doctrine: shipped SDK /
#: integration / embed / published-CLI families survive), mirrored here
#: because the mint builds its set inside the run function. Structural
#: detector verdicts, never a name dictionary.
_SACRED_VETO_REASONS = frozenset(
    {"published_cli", "nested_family", "hosts_hub_family"})

#: H4 plumbing-mass bar — probe-fixed at 0.8; threshold-INSENSITIVE over
#: [0.5, 0.85] on the labeled corpus (2026-07-24 probe), i.e. a structural
#: super-majority test, not a tuned magic number.
_PLUMB_FRAC_MIN = 0.8

#: The framework-profile FileRoles that are delivery/wiring shapes (the
#: profile's OWN handler taxonomy — FileRole is a str enum, so plain
#: string membership compares correctly).
_PLUMB_ROLES = frozenset({"api", "route", "service", "config"})


def b48_sacred_units(scan_meta: Any) -> frozenset[str]:
    """The B48 SACRED unit dirs, read back from the mint's OWN
    technology-instrument verdicts
    (``scan_meta.stage_6_86_anchored_mint.technology_instruments.vetoed``)
    — the exact channel the mint's micro-LOC demote consults, so H4 and
    the mint can never disagree about what is sacred. Empty when the
    mint stamped nothing (flag off / no instruments on the board)."""
    vetoed = ((((scan_meta or {}).get("stage_6_86_anchored_mint") or {})
               .get("technology_instruments") or {}).get("vetoed") or {})
    return frozenset(
        str(u).strip("/") for u, r in vetoed.items()
        if str(r) in _SACRED_VETO_REASONS
    )


def nav_seam_keys(ctx: Any, mint_nav_keys: Any) -> frozenset[str]:
    """The nav evidence READABLE at the 6.9964 seam: the mint's href-echo
    keys UNION the author's declared nav tree
    (:func:`~wystan.pipeline_v2.nav_parent.build_nav_tree` — the SAME
    deterministic extractor the display-side ``nav_parent`` stage trusts,
    normalized the SAME way the mint echo is: first meaningful href
    segment through ``normalize_href`` + ``normalize_anchor_key``).

    B91 finding (VERIFIED, keyed world-40): the mint echo ALONE is
    board-shape-dependent — EMPTY on RefApp whose ``app-nav-config.ts``
    parses into a nav tree that later stamps 28 ``nav_parent`` rows, so
    the pin board would falsely board-wide-abstain (Seg B's
    ``nav_abstained=True`` on BOTH RefApp channels is this exact false
    negative). The union keeps the abstain law for truly nav-less boards
    (outline: echo empty AND no tree ⇒ still abstains) while letting a
    declared tree open the channel."""
    keys: set[str] = {str(k) for k in (mint_nav_keys or ())}
    try:
        from wystan.pipeline_v2.nav_parent import build_nav_tree
        from wystan.pipeline_v2.product_strings import normalize_href
        from wystan.pipeline_v2.spine_anchors import normalize_anchor_key
        for cat in build_nav_tree(ctx) or []:
            for item in getattr(cat, "sub_items", ()) or ():
                href = getattr(item, "route", None)
                if not href:
                    continue
                norm = normalize_href(str(href)) or ""
                for seg in norm.strip("/").split("/"):
                    if seg and not seg.startswith(":"):
                        keys.add(normalize_anchor_key(seg))
                        break
    except Exception:  # noqa: BLE001 — nav extraction never breaks a scan
        pass
    return frozenset(k for k in keys if k)


def container_anchor_path(anchor_id: Any) -> str | None:
    """The anchor tail when *anchor_id* is a container-kind anchor
    (``dev:``/``fdir:``/``ws:``/``pypkg:``), else ``None``. Structural
    position, not a name test: ``route:``-surfaces (B90 Seg B territory)
    and ``hub:`` integration units (integration = own PF) never enter."""
    kind, sep, tail = str(anchor_id or "").partition(":")
    if not sep or kind not in _CONTAINER_KINDS:
        return None
    tail = tail.strip("/")
    return tail or None


def is_plumbing_shape_file(
    path: str,
    role: Any,
    plumb_infix_keys: frozenset[str],
    data_shape_keys: frozenset[str],
) -> bool:
    """Is this member file a route-handler / transport / dto / plumbing
    shape? THREE existing mechanisms, no new decision vocabulary:

    (a) the framework profile's own :class:`FileRole` (api / route /
        service / config — the handler & wiring taxonomy);
    (b) the analyzer's ``_is_infra_file`` (infra dirs, config classes);
    (c) an AUTHORED data-shape declaration: a dotted basename infix
        (``foo.dto.ts``, ``x.interface.ts`` — the author's own per-file
        shape word) matched against the full plumbing vocab, or an
        ancestor directory segment matched against the NARROW
        ``data_shape_segments`` key ONLY — deliberately never the broader
        stoplists, whose ``shared``/``src``/``lib`` ancestors would
        poison every monorepo package (B91 census refutation).

    All vocab matching runs through :func:`hub_child_is_plumbing`
    (normalize + vendor-beats-plumbing shield — the B26 mechanism)."""
    if role is not None and role in _PLUMB_ROLES:
        return True
    from wystan.analyzer.features import _is_infra_file
    try:
        if _is_infra_file(path):
            return True
    except Exception:  # noqa: BLE001 — a weird path never breaks a scan
        pass
    from wystan.pipeline_v2.spine_anchors import hub_child_is_plumbing
    base = path.rsplit("/", 1)[-1]
    toks = base.split(".")
    for t in toks[1:-1]:
        if hub_child_is_plumbing(t, plumb_infix_keys):
            return True
    for seg in path.split("/")[:-1]:
        if hub_child_is_plumbing(seg, data_shape_keys):
            return True
    return False


def container_plumb_frac(
    pf: Any,
    classify: Any,
    plumb_infix_keys: frozenset[str],
    data_shape_keys: frozenset[str],
) -> tuple[float, int]:
    """``(plumb_frac, n_files)`` over the PF's DISTINCT member paths.
    COUNT-based deliberately: ``member_files[].loc`` is absent for
    legacy ``paths``-only members, so LOC-weighting silently
    under-reports (B91 calibration: novu ``dto`` scored 0.29
    LOC-weighted vs 0.87 by count against a hand-verified 68/79
    data-shape membership — count is the honest denominator here)."""
    seen: set[str] = set()
    n = 0
    plumb = 0
    for p in _feature_paths(pf):
        if p in seen:
            continue
        seen.add(p)
        n += 1
        role = None
        if classify is not None:
            try:
                role = classify(p)
            except Exception:  # noqa: BLE001 — profile quirk ≠ scan break
                role = None
        if is_plumbing_shape_file(p, role, plumb_infix_keys, data_shape_keys):
            plumb += 1
    if n == 0:
        return 0.0, 0
    return plumb / n, n


def run_api_container_demote(
    developer_features: list["Feature"],
    product_features: list["Feature"],
    user_flows: list[Any],
    ctx: Any,
    nav_keys: frozenset[str] = frozenset(),
    sacred_units: frozenset[str] = frozenset(),
    classify: Any = None,
) -> dict[str, Any]:
    """See module docstring (B91 H4). Mutates ``product_features`` /
    ``user_flows`` / dev stamps in place; returns telemetry for
    ``scan_meta.api_container_demote``. Mechanics mirror
    :func:`run_api_stub_demote` verbatim (the post-UF demote house
    pattern) with the B91 rung/markers. ``classify`` is a test-injection
    seam; production resolves the scan's own framework profile
    (:func:`select_scan_profile` — the exact selection the scan used)."""
    tele: dict[str, Any] = {
        "enabled": True, "eligible": 0,
        "demoted": [], "abstained": [],
        "dropped_ufs": {}, "residual_ufs": {},
        "devs_repointed": 0, "devs_unowned": 0,
    }
    if not api_container_demote_enabled():
        tele["enabled"] = False
        return tele
    if not nav_keys:
        # Board-wide honest abstain (the devgrain / Seg B precedent): the
        # nav evidence prong is unreadable — a nav-declared container
        # could not defend itself, so the pass acts on nothing.
        tele["nav_abstained"] = True
        return tele
    if classify is None:
        try:
            from wystan.pipeline_v2.profiles._per_unit import (
                select_scan_profile,
            )
            classify = select_scan_profile(ctx).classify_file
        except Exception:  # noqa: BLE001 — no profile ⇒ honest abstain
            # The FileRole prong is unreadable — same abstain law as nav.
            tele["profile_abstained"] = True
            return tele

    from wystan.pipeline_v2.spine_anchors import (
        load_spine_vocab,
        normalize_anchor_key,
    )
    vocab = load_spine_vocab()
    data_shape_keys = frozenset(vocab.get("data_shape_segments") or [])
    plumb_infix_keys = (
        frozenset(vocab.get("hub_plumbing_segments") or [])
        | frozenset(vocab.get("structural_stoplist") or [])
        | data_shape_keys
    )

    ufs_by_pf: dict[str, list[Any]] = {}
    for uf in user_flows:
        pid = _attr(uf, "product_feature_id")
        if pid:
            ufs_by_pf.setdefault(str(pid), []).append(uf)

    # Phase 1 — decide every demotion against the SAME pre-pass board
    # (deterministic: sorted by PF name; no order-dependent cascades).
    demote: list["Feature"] = []
    frac_by_key: dict[str, float] = {}
    for pf in sorted(product_features,
                     key=lambda p: str(_attr(p, "name") or "")):
        key = str(_attr(pf, "name") or "")
        aid = str(_attr(pf, "anchor_id") or "")
        tail = container_anchor_path(aid)
        if tail is None:
            continue
        tele["eligible"] += 1
        members = ufs_by_pf.get(key, [])
        real = [u for u in members if not _attr(u, "synthesized")]
        frac, nfiles = container_plumb_frac(
            pf, classify, plumb_infix_keys, data_shape_keys)
        # every conjunct reports its own NAMED save (probe law: each
        # axis alone over-kills, so each save must be auditable).
        reasons: list[str] = []
        if nfiles == 0 or frac < _PLUMB_FRAC_MIN:
            reasons.append(f"plumb_frac={frac:.2f}")
        if has_api_stub_product_evidence(pf):
            reasons.append(
                "nav" if _attr(pf, "nav_parent") else "authored_view")
        # the author's IA word at SEAM grain: the anchor leaf names a nav
        # entry (nav_parent display stamps land AFTER this seam, so the
        # nav_keys channel — mint echo ∪ declared tree — is the live one).
        # B1 (twins-forensics, RefApp phantom): a bare nav-key hit WITHOUT
        # page/flow corroboration (real UFs or an authored view among the
        # members) never blocks the demote — the keyed exhibit dev:api
        # (plumb_frac=1.0, 0 real UFs, 0 views) abstained on nav_declared
        # alone and the phantom survived. A corroborated nav hit still
        # abstains (and its corroborating evidence abstains by itself).
        _leaf_key = normalize_anchor_key(tail.rsplit("/", 1)[-1])
        if _leaf_key and _leaf_key in nav_keys:
            if real or has_api_stub_product_evidence(pf):
                reasons.append("nav_declared")
            else:
                tele.setdefault(
                    "nav_declared_uncorroborated", []).append(key)
        if real:
            reasons.append(f"real_ufs={len(real)}")
        if sacred_units and any(
            tail == u or tail.startswith(u + "/") for u in sacred_units
        ):
            reasons.append("b48_sacred")
        if reasons:
            tele["abstained"].append({"pf": key, "evidence": reasons})
            continue
        frac_by_key[key] = round(frac, 3)
        demote.append(pf)
    if not demote:
        return tele

    demote_keys = {str(_attr(pf, "name") or "") for pf in demote}

    def _anchor_path(pf: "Feature") -> str | None:
        aid = str(_attr(pf, "anchor_id") or "")
        if ":" not in aid:
            return None
        return aid.split(":", 1)[1].strip("/") or None

    def _ancestor_target(tail: str) -> "Feature | None":
        """Nearest SURVIVING ancestor PF by anchor-prefix containment —
        the devgrain fold semantics (mirrors the Seg B closure)."""
        best: tuple[int, str, "Feature"] | None = None
        for other in product_features:
            okey = str(_attr(other, "name") or "")
            if okey in demote_keys or okey.strip().lower() in (
                "platform", "shared-platform",
            ):
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
        if _attr(f, "layer", "developer") != "developer":
            continue
        pid = _attr(f, "product_feature_id")
        if pid:
            devs_by_pf.setdefault(str(pid), []).append(f)

    # I9 rider (the devgrain B37-ph2 mechanics, mirrored from Seg B): a
    # demoted container's FLOWFUL dev never falls to the platform lane.
    from wystan.pipeline_v2.dispatch_homing import (
        build_anchor_owner_resolver,
        dispatch_homing_enabled,
    )
    _i9_on = dispatch_homing_enabled()
    if _i9_on:
        tele["devs_i9_homed"] = 0
        tele["devs_flowful_unowned"] = 0
    _surviving_pfs = [
        pf for pf in product_features
        if str(_attr(pf, "name") or "") not in demote_keys
        and str(_attr(pf, "name") or "").strip().lower()
        not in ("platform", "shared-platform")
    ]
    _surviving_keys = {str(_attr(pf, "name") or "") for pf in _surviving_pfs}
    _owner_resolve = (
        build_anchor_owner_resolver(_surviving_pfs) if _i9_on else None)

    def _flowful_owner_key(dev: "Feature") -> str | None:
        if _owner_resolve is None:
            return None
        owners = [
            k for k in (
                _owner_resolve(_attr(fl, "entry_point_file"))
                for fl in (_attr(dev, "flows") or [])
            ) if k
        ]
        if not owners:
            return None
        top, ct = sorted(
            Counter(owners).items(), key=lambda kv: (-kv[1], kv[0]))[0]
        if ct * 2 <= len(owners) or top not in _surviving_keys:
            return None
        return top

    # Phase 2 — apply (sorted; the Seg B / devgrain mechanics verbatim,
    # B91 rung + fold markers).
    dropped_uf_ids: set[int] = set()
    for pf in sorted(demote, key=lambda p: str(_attr(p, "name") or "")):
        key = str(_attr(pf, "name") or "")
        aid = str(_attr(pf, "anchor_id") or "")
        tail = aid.split(":", 1)[1].strip("/") if ":" in aid else ""
        members = ufs_by_pf.get(key, [])
        synth = [u for u in members if _attr(u, "synthesized")]
        real = [u for u in members if not _attr(u, "synthesized")]
        dropped = sorted(str(_attr(u, "name") or "") for u in synth)
        if dropped:
            tele["dropped_ufs"][key] = dropped
            dropped_uf_ids.update(id(u) for u in synth)
        if real:
            # vacuous by the journey veto (a real member abstains the PF
            # in phase 1) — kept for conservation symmetry with Seg B.
            tele["residual_ufs"][key] = sorted(
                str(_attr(u, "name") or "") for u in real)
            for u in sorted(real, key=lambda x: str(_attr(x, "id") or "")):
                propose_pf_now(u, None, rung="b91_api_container")
                u.residual = True
        target = _ancestor_target(tail)
        for m in sorted(devs_by_pf.get(key, ()),
                        key=lambda d: str(_attr(d, "name") or "")):
            if target is not None:
                propose_pf_now(
                    m, str(_attr(target, "name") or ""),
                    rung="b91_api_container")
                m.anchor_id = f"fold:b91-api-container->{aid}"
                if _attr(m, "shared_reason"):
                    m.shared_reason = None
                tele["devs_repointed"] += 1
            else:
                owner_key = (
                    _flowful_owner_key(m)
                    if (_i9_on and _attr(m, "flows")) else None)
                if owner_key is not None:
                    propose_pf_now(m, owner_key, rung="b91_api_container")
                    m.anchor_id = f"fold:b91-api-container-i9->{aid}"
                    if _attr(m, "shared_reason"):
                        m.shared_reason = None
                    tele["devs_i9_homed"] += 1
                elif _i9_on and _attr(m, "flows"):
                    propose_pf_now(m, None, rung="b91_api_container")
                    m.anchor_id = None
                    m.shared_reason = None
                    tele["devs_flowful_unowned"] += 1
                else:
                    propose_pf_now(m, None, rung="b91_api_container")
                    m.anchor_id = None
                    m.shared_reason = _SHARED_REASON_BAR
                    tele["devs_unowned"] += 1
        # paths + member_files union onto the target (dedup, stable order).
        if target is not None:
            seen_p = set(_attr(target, "paths") or [])
            merged_p = list(_attr(target, "paths") or [])
            for p in (_attr(pf, "paths") or []):
                if p not in seen_p:
                    seen_p.add(p)
                    merged_p.append(p)
            target.paths = merged_p
            seen_mf = {
                (mf.get("path") if isinstance(mf, dict)
                 else getattr(mf, "path", None))
                for mf in (_attr(target, "member_files") or [])
            }
            for mf in (_attr(pf, "member_files") or []):
                mfp = (mf.get("path") if isinstance(mf, dict)
                       else getattr(mf, "path", None))
                if mfp and mfp not in seen_mf:
                    seen_mf.add(mfp)
                    target.member_files.append(mf)
        tele["demoted"].append({
            "pf": key, "anchor": aid,
            "plumb_frac": frac_by_key.get(key),
            "into": (str(_attr(target, "name") or "")
                     if target is not None else None),
            "ufs_dropped": len(dropped),
            "ufs_residual": len(real),
        })

    product_features[:] = [
        pf for pf in product_features
        if str(_attr(pf, "name") or "") not in demote_keys
    ]
    if dropped_uf_ids:
        user_flows[:] = [u for u in user_flows if id(u) not in dropped_uf_ids]
    return tele


# ── B93 — route-render-util discriminator ────────────────────────────────
#
# The operator pin ``novu-html-route-markup`` ("'HTML' is a delivery layer /
# render utility, not a product capability"). Genesis (VERIFIED, keyless
# novu): the keyless App-Router extractor gates a page on
# ``p.endswith(suffix.lstrip("/"))`` — so the suffix ``/page.ts`` becomes the
# bare ``page.ts``, and a BACKEND render helper
# ``apps/api/src/app/shared/html/connection-result-page.ts`` (a pure
# HTML-string renderer, NO @Controller/@Get, NO authored view) trips it. The
# non-marker stem ``connection-result-page`` is appended to the URL by
# ``_route_from_app_rest`` → a ``{pattern:/shared/html/connection-result-page,
# method:PAGE, surface_scope:product}`` route → the ``route:…/shared/html`` PF
# renders as the product feature "HTML".
#
# WHY A NEW PRONG (not H4, not Seg B): B91 H4 EXCLUDES ``route:`` by the
# binding B91 scope ruling (nothing Seg B judged or spared on route evidence
# is re-litigated); B90 Seg B fires ONLY on the api-ROOT-leaf shape (parent
# segment == ``api``) — here the parent is ``shared`` → out of scope. The
# phantom-PAGE render-util is the uncovered residual BY CONSTRUCTION. This
# arm targets ONLY that gap and explicitly SKIPS any api-root-stub PF (Seg B
# territory), so the B91 ruling is honoured, not re-litigated.
#
# DISCRIMINATOR (structural, no dictionary; every conjunct auditable):
#     route: anchor
#   ∧ NOT an api-root-stub-leaf (Seg B territory — binding B91 ruling)
#   ∧ ≥1 member is a phantom-PAGE render-util file
#       (:func:`is_phantom_page_render_util`: a non-view ``*page.{ts,js}``
#        NON-marker leaf — a real App-Router page is named EXACTLY
#        ``page.{tsx,jsx,ts,js}``; ``connection-result-page.ts`` is a helper)
#   ∧ authored_view == 0        # LOAD-BEARING — a REAL page HAS an authored
#                               # view (.tsx/.jsx/.vue/.svelte/.astro); the
#                               # mint's _VIEW_COMPONENT_EXTS, single source
#   ∧ ¬nav_evidence             # no nav_parent AND anchor leaf not a nav key
#   ∧ ¬substantive_journey      # channel-robust micro-profile veto (held ≤ 1
#                               # AND every member mc ≤ 3): a synth backstop
#                               # OR a keyless mc=1 route-echo never defends;
#                               # a real journey set (held>1 / mc>3) vetoes
#   ∧ ¬B48_sacred_veto          # SDK / integration / embed / published-CLI
#
# The load-bearing conjunct is ``authored_view == 0`` combined with the
# phantom-PAGE file member: TOGETHER they ARE the "render-only shape" the
# operator described (a page implemented as a plain ``.ts`` function with no
# authored view is a render utility by construction — no file-body reading
# needed at the deterministic seam). It saves every named anti-case:
#   * plane ``Core`` (route:…/routes/redirects/core) — 14 ``.tsx`` views →
#     authored_view > 0 → spared;
#   * a real HTML/PDF export feature (reactive-resume) reachable by a real
#     journey → the micro-profile veto spares it;
#   * langfuse ``Batch Exports`` (dev:batch-exports) — a CONTAINER anchor,
#     never a ``route:`` → not even eligible;
#   * any real frontend page-route — has an authored view → spared.
#
# Unlike H4/Seg B there is NO board-wide nav-abstain: the render-util class
# is inherently NON-nav (a render helper file is never a nav destination), so
# "nav unreadable ⇒ can't defend a nav-declared surface" does not apply — nav
# is a per-PF SPARING conjunct only, letting the arm act on nav-blind keyless
# boards. Demote = the Seg B / H4 house mechanics verbatim (PF removed, synth
# UFs drop named, REAL UFs → honest residual [B77] resolved by the 6.9965
# token re-home, devs fold to the surviving ancestor / I9 rider / honest
# unowned). Deterministic, $0 LLM, scale-invariant.


#: Non-view script extensions a phantom-PAGE render-util file carries. A real
#: authored page uses a VIEW extension (``_VIEW_COMPONENT_EXTS``); a backend
#: render helper that falsely trips the ``page.{ts,js}`` suffix gate is a
#: plain ``.ts`` / ``.js`` module.
_RENDER_UTIL_EXTS = ("ts", "js")


def route_render_anchor_tail(anchor_id: Any) -> str | None:
    """The anchor tail when *anchor_id* is a ``route:`` anchor, else
    ``None``. Structural position, not a name test: container kinds
    (``dev:``/``fdir:``/``ws:``/``pypkg:`` — H4 territory) and ``hub:``
    integration units never enter."""
    kind, sep, tail = str(anchor_id or "").partition(":")
    if not sep or kind != "route":
        return None
    tail = tail.strip("/")
    return tail or None


def is_phantom_page_render_util(path: str) -> bool:
    """Is *path* a BACKEND render-util file that FALSELY trips the App-Router
    page-suffix gate?

    The exact FP shape (VERIFIED genesis): the keyless App-Router extractor
    gates on ``p.endswith("page.ts")`` (the YAML suffix ``/page.ts`` after its
    own ``lstrip("/")``), and ``_route_from_app_rest`` stamps ``method=PAGE``.
    A REAL App-Router page is named EXACTLY ``page.{tsx,jsx,ts,js}`` (a marker
    leaf); a render helper like ``connection-result-page.ts`` is a NON-marker
    leaf ending in ``page.ts``. So the structural discriminator is:

      * NOT an authored view (``.tsx``/``.jsx``/``.vue``/``.svelte``/
        ``.astro`` — the mint's ``_VIEW_COMPONENT_EXTS``): a view IS a real
        page surface;
      * a non-view script extension (``.ts``/``.js``);
      * the filename stem ends with ``page`` but is NOT the bare marker
        ``page`` (a prefix ⇒ a render helper, never the canonical page leaf);
      * not a test file.

    This isolates the phantom-PAGE render-util (``*page.ts`` non-marker) from
    every real App-Router page (``page.tsx``/``page.ts`` marker leaf) with no
    name dictionary and no repo-specific path."""
    from wystan.analyzer.validation import is_test_file
    from wystan.pipeline_v2.stage_6_86_anchored_mint import (
        _VIEW_COMPONENT_EXTS,
    )
    p = str(path or "").replace("\\", "/").lower()
    if not p:
        return False
    if p.endswith(_VIEW_COMPONENT_EXTS):
        return False
    if is_test_file(p):
        return False
    base = p.rsplit("/", 1)[-1]
    stem, _dot, ext = base.rpartition(".")
    if ext not in _RENDER_UTIL_EXTS or not stem:
        return False
    if stem == "page":  # canonical marker leaf ⇒ a real page, not a helper
        return False
    return stem.endswith("page")


def _pf_has_authored_view(pf: Any) -> bool:
    """``authored_view > 0`` — any member path is an authored view component
    (reuses the mint's ``_VIEW_COMPONENT_EXTS``, single source)."""
    from wystan.pipeline_v2.stage_6_86_anchored_mint import (
        _VIEW_COMPONENT_EXTS,
    )
    return any(
        str(p).lower().endswith(_VIEW_COMPONENT_EXTS)
        for p in _feature_paths(pf)
    )


def run_route_render_util_demote(
    developer_features: list["Feature"],
    product_features: list["Feature"],
    user_flows: list[Any],
    nav_keys: frozenset[str] = frozenset(),
    sacred_units: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """See the B93 section docstring. Mutates ``product_features`` /
    ``user_flows`` / dev stamps in place; returns telemetry for
    ``scan_meta.route_render_util_demote``. Mechanics mirror
    :func:`run_api_container_demote` / :func:`run_api_stub_demote` verbatim
    (the post-UF demote house pattern) with the B93 rung/markers."""
    from wystan.pipeline_v2.spine_anchors import normalize_anchor_key

    tele: dict[str, Any] = {
        "enabled": True, "eligible": 0,
        "demoted": [], "abstained": [],
        "dropped_ufs": {}, "residual_ufs": {},
        "devs_repointed": 0, "devs_unowned": 0,
    }
    if not route_render_util_demote_enabled():
        tele["enabled"] = False
        return tele

    ufs_by_pf: dict[str, list[Any]] = {}
    for uf in user_flows:
        pid = _attr(uf, "product_feature_id")
        if pid:
            ufs_by_pf.setdefault(str(pid), []).append(uf)

    # Phase 1 — decide every demotion against the SAME pre-pass board
    # (deterministic: sorted by PF name; no order-dependent cascades). Each
    # conjunct reports its own NAMED save (each axis alone over-kills).
    demote: list["Feature"] = []
    for pf in sorted(product_features,
                     key=lambda p: str(_attr(p, "name") or "")):
        key = str(_attr(pf, "name") or "")
        aid = str(_attr(pf, "anchor_id") or "")
        tail = route_render_anchor_tail(aid)
        if tail is None:
            continue
        # BINDING B91 ruling: an api-root-stub PF is B90 Seg B territory —
        # never re-litigated here.
        if api_root_stub_leaf(aid) is not None:
            continue
        # must carry a phantom-PAGE render-util member (the FP trigger).
        if not any(
            is_phantom_page_render_util(p) for p in _feature_paths(pf)
        ):
            continue
        tele["eligible"] += 1
        members = ufs_by_pf.get(key, [])
        real = [u for u in members if not _attr(u, "synthesized")]
        reasons: list[str] = []
        # substantive-journey veto — the micro-profile test applied to the
        # REAL (non-synth) members ONLY. Channel-robust AND synth-proof: a
        # synth backstop (real == []) is vacuously micro → never defends
        # (canon: an artifact of the PF's own existence), and a keyless mc=1
        # route-echo is micro → never defends either; only a SUBSTANTIVE real
        # set (held > 1 OR a real member mc > 3 — reactive-resume export)
        # vetoes. This is why is_micro_profile is applied to ``real``, not to
        # ``members`` (a high-mc synth backstop must NOT save the PF).
        if not is_micro_profile(real):
            if len(real) > 1:
                reasons.append(f"held={len(real)}")
            else:
                reasons.append(f"mc={_attr(real[0], 'member_count')}")
        # authored view / nav_parent (LOAD-BEARING view conjunct).
        if _pf_has_authored_view(pf):
            reasons.append("authored_view")
        if _attr(pf, "nav_parent"):
            reasons.append("nav")
        # the author's IA word at SEAM grain: anchor leaf names a nav entry.
        _leaf_key = normalize_anchor_key(tail.rsplit("/", 1)[-1])
        if _leaf_key and _leaf_key in nav_keys:
            reasons.append("nav_declared")
        if sacred_units and any(
            tail == u or tail.startswith(u + "/") for u in sacred_units
        ):
            reasons.append("b48_sacred")
        if reasons:
            tele["abstained"].append({"pf": key, "evidence": reasons})
            continue
        demote.append(pf)
    if not demote:
        return tele

    demote_keys = {str(_attr(pf, "name") or "") for pf in demote}

    def _anchor_path(pf: "Feature") -> str | None:
        aid = str(_attr(pf, "anchor_id") or "")
        if ":" not in aid:
            return None
        return aid.split(":", 1)[1].strip("/") or None

    def _ancestor_target(tail: str) -> "Feature | None":
        """Nearest SURVIVING ancestor PF by anchor-prefix containment —
        the devgrain fold semantics (mirrors the Seg B / H4 closure)."""
        best: tuple[int, str, "Feature"] | None = None
        for other in product_features:
            okey = str(_attr(other, "name") or "")
            if okey in demote_keys or okey.strip().lower() in (
                "platform", "shared-platform",
            ):
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
        if _attr(f, "layer", "developer") != "developer":
            continue
        pid = _attr(f, "product_feature_id")
        if pid:
            devs_by_pf.setdefault(str(pid), []).append(f)

    # I9 rider (the devgrain B37-ph2 mechanics, mirrored from Seg B / H4): a
    # demoted render-util's FLOWFUL dev never falls to the platform lane.
    from wystan.pipeline_v2.dispatch_homing import (
        build_anchor_owner_resolver,
        dispatch_homing_enabled,
    )
    _i9_on = dispatch_homing_enabled()
    if _i9_on:
        tele["devs_i9_homed"] = 0
        tele["devs_flowful_unowned"] = 0
    _surviving_pfs = [
        pf for pf in product_features
        if str(_attr(pf, "name") or "") not in demote_keys
        and str(_attr(pf, "name") or "").strip().lower()
        not in ("platform", "shared-platform")
    ]
    _surviving_keys = {str(_attr(pf, "name") or "") for pf in _surviving_pfs}
    _owner_resolve = (
        build_anchor_owner_resolver(_surviving_pfs) if _i9_on else None)

    def _flowful_owner_key(dev: "Feature") -> str | None:
        if _owner_resolve is None:
            return None
        owners = [
            k for k in (
                _owner_resolve(_attr(fl, "entry_point_file"))
                for fl in (_attr(dev, "flows") or [])
            ) if k
        ]
        if not owners:
            return None
        top, ct = sorted(
            Counter(owners).items(), key=lambda kv: (-kv[1], kv[0]))[0]
        if ct * 2 <= len(owners) or top not in _surviving_keys:
            return None
        return top

    # Phase 2 — apply (sorted; the Seg B / H4 mechanics verbatim, B93 rung).
    dropped_uf_ids: set[int] = set()
    for pf in sorted(demote, key=lambda p: str(_attr(p, "name") or "")):
        key = str(_attr(pf, "name") or "")
        aid = str(_attr(pf, "anchor_id") or "")
        tail = aid.split(":", 1)[1].strip("/") if ":" in aid else ""
        members = ufs_by_pf.get(key, [])
        synth = [u for u in members if _attr(u, "synthesized")]
        real = [u for u in members if not _attr(u, "synthesized")]
        dropped = sorted(str(_attr(u, "name") or "") for u in synth)
        if dropped:
            tele["dropped_ufs"][key] = dropped
            dropped_uf_ids.update(id(u) for u in synth)
        if real:
            # a substantive real member abstains the PF in phase 1, so a
            # residual here is only a micro-profile route-echo — kept honest
            # (pfid=None + residual=True, named) for the 6.9965 token re-home.
            tele["residual_ufs"][key] = sorted(
                str(_attr(u, "name") or "") for u in real)
            for u in sorted(real, key=lambda x: str(_attr(x, "id") or "")):
                propose_pf_now(u, None, rung="b93_route_render_util")
                u.residual = True
        target = _ancestor_target(tail)
        for m in sorted(devs_by_pf.get(key, ()),
                        key=lambda d: str(_attr(d, "name") or "")):
            if target is not None:
                propose_pf_now(
                    m, str(_attr(target, "name") or ""),
                    rung="b93_route_render_util")
                m.anchor_id = f"fold:b93-route-render-util->{aid}"
                if _attr(m, "shared_reason"):
                    m.shared_reason = None
                tele["devs_repointed"] += 1
            else:
                owner_key = (
                    _flowful_owner_key(m)
                    if (_i9_on and _attr(m, "flows")) else None)
                if owner_key is not None:
                    propose_pf_now(m, owner_key, rung="b93_route_render_util")
                    m.anchor_id = f"fold:b93-route-render-util-i9->{aid}"
                    if _attr(m, "shared_reason"):
                        m.shared_reason = None
                    tele["devs_i9_homed"] += 1
                elif _i9_on and _attr(m, "flows"):
                    propose_pf_now(m, None, rung="b93_route_render_util")
                    m.anchor_id = None
                    m.shared_reason = None
                    tele["devs_flowful_unowned"] += 1
                else:
                    propose_pf_now(m, None, rung="b93_route_render_util")
                    m.anchor_id = None
                    m.shared_reason = _SHARED_REASON_BAR
                    tele["devs_unowned"] += 1
        # paths + member_files union onto the target (dedup, stable order).
        if target is not None:
            seen_p = set(_attr(target, "paths") or [])
            merged_p = list(_attr(target, "paths") or [])
            for p in (_attr(pf, "paths") or []):
                if p not in seen_p:
                    seen_p.add(p)
                    merged_p.append(p)
            target.paths = merged_p
            seen_mf = {
                (mf.get("path") if isinstance(mf, dict)
                 else getattr(mf, "path", None))
                for mf in (_attr(target, "member_files") or [])
            }
            for mf in (_attr(pf, "member_files") or []):
                mfp = (mf.get("path") if isinstance(mf, dict)
                       else getattr(mf, "path", None))
                if mfp and mfp not in seen_mf:
                    seen_mf.add(mfp)
                    target.member_files.append(mf)
        tele["demoted"].append({
            "pf": key, "anchor": aid,
            "into": (str(_attr(target, "name") or "")
                     if target is not None else None),
            "ufs_dropped": len(dropped),
            "ufs_residual": len(real),
        })

    product_features[:] = [
        pf for pf in product_features
        if str(_attr(pf, "name") or "") not in demote_keys
    ]
    if dropped_uf_ids:
        user_flows[:] = [u for u in user_flows if id(u) not in dropped_uf_ids]
    return tele
