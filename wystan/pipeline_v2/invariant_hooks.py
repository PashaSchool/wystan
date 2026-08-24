"""B89 — invariant stage-hooks (``WYSTAN_INVARIANT_HOOKS``, default ON
since flip-pack №6, KEY_SCHEMA 39).

Operator law (2026-07-23, ``docs/anchor-arc/pf-product-grain-prompt.md`` +
the stage-hooks memory): every bug-class ships (a) a deterministic fix AND
(b) a *stage-hook* on the class's PRODUCER stage that STAMPS a structured
record whenever the class is present — a standing sentinel so a killed
disease that resurfaces (kill-switched fix, upstream regression) is caught
at birth, machine-readably, instead of silently re-flowing to the board.

A hook is a PURE function over the structures ALREADY PRESENT at its seam
(zero new traversals of big data where avoidable). It appends one record to
``scan_meta.invariant_hooks[]``::

    {"class": str, "stage": str, "count": int,
     "exhibits": [str, ...][:20], "severity": "info"|"warn"|"critical"}

A ``critical`` hook that fires (count > 0) ALSO appends a
``severity="failed"`` degradation to ``scan_meta.degradations[]`` — the
severity-aware install / ``validate_scan`` guard already blocks a board on
a ``failed`` degradation, so a critical invariant physically stops install.

DETERMINISM: exhibits are sorted + de-duplicated + capped at 20; ``count``
is the FULL distinct-exhibit count (never capped). Hook execution order is
registration order; the record list is append-only. Everything is a pure
function of the stage structures ⇒ byte-stable across a det ×2 rerun.

FLAG: ``WYSTAN_INVARIANT_HOOKS`` default **ON** since flip-pack №6
(KEY_SCHEMA 39; the bump rode the pack's FIRST flip commit,
PRODUCT_RIGHT_GATE). Explicit ``0``/``false``/``off``/``no``/``""`` ⇒ every
entry point returns BEFORE any read/append ⇒ no ``invariant_hooks`` /
``product_right_census`` key, no degradation ⇒ byte-identical to the pre-B89
world (the KS 4-way law, kill-switch forever). Unset ≡ explicit ``"1"``.

No LLM. No network. Reads only in-memory ``product_features`` (``Feature``
rows, ``layer="product"``) and ``user_flows`` (``UserFlow`` rows).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from collections.abc import Iterable
from typing import Any, Callable

__all__ = [
    "INVARIANT_HOOKS_ENV",
    "MINT_SILENT_EMPTY_SENTINEL_ENV",
    "mint_silent_empty_sentinel_enabled",
    "SEVERITY_INFO",
    "SEVERITY_WARN",
    "SEVERITY_CRITICAL",
    "EXHIBIT_CAP",
    "invariant_hooks_enabled",
    "InvariantHook",
    "register",
    "run_stage",
    "run_product_right_census",
    "canon_classes",
    "has_product_evidence",
    "pf_flow_owner_names",
    "ws_evidence_discriminator_enabled",
    "CANON_CLASS_IDS",
]

INVARIANT_HOOKS_ENV = "WYSTAN_INVARIANT_HOOKS"

#: B113 (fixb113) — the silent-empty-board sentinel's own arm. The
#: ``mint_silent_empty`` hook lives on its OWN seam key
#: ("6.86_mint_universe") which phase_finalize fires only when this flag is
#: armed, so the default world never gains an ``invariant_hooks[]`` record
#: (byte-identity; the B91/B112 own-key precedent). Default OFF; explicit
#: ``0`` is a kill-switch forever. Subordinate to
#: :func:`invariant_hooks_enabled` — the master kill-switch still silences it.
MINT_SILENT_EMPTY_SENTINEL_ENV = "WYSTAN_MINT_SILENT_EMPTY_SENTINEL"


def mint_silent_empty_sentinel_enabled() -> bool:
    """B113 — the silent-empty sentinel arm. Default **OFF**."""
    return os.environ.get(
        MINT_SILENT_EMPTY_SENTINEL_ENV, "1",
    ).strip().lower() in {"1", "true", "yes", "on"}


#: fixb146 Row 2 — the ``ws_anchor_no_uf`` PRODUCT-EVIDENCE discriminator,
#: default **OFF**. The class was written to catch a STRUCTURAL CONTAINER
#: masquerading as product, but its predicate is "ws: anchor AND zero
#: non-synthesized journeys", which also convicts a REAL product surface
#: whose journeys the engine has honestly backstopped. Live exhibit
#: (onyx, KS77): ``onyx-chat-widget`` (``ws:widget``) holds UF-087 'Send
#: onyx chat widget' — synthesized, but carrying 5 member flows — and the
#: binding product-grain canon says a real feature without journeys is
#: MARKED with an honest gap, never deleted. Cure (operator ruling
#: 2026-08-11, option 2): spare a ws-PF that carries positive product
#: evidence, reusing the prongs the sibling seed-hook
#: ``check_pf_ws_container_no_uf`` already uses — one shared helper,
#: :func:`has_product_evidence`, so the two can never drift.
#: Deliberately NOT keyed on the ``synthesized`` tag: the fixb145
#: confidence-cap lane makes that tag DYNAMIC (converted rows drop it),
#: which would make the class re-trip at random as conversions land.
#: Default **ON** since flip-pack №43 (2026-08-11, KEY_SCHEMA 78) —
#: measured: onyx ws_anchor_no_uf 1 -> 0 (gate VERDICT CLEAN), dub 3 -> 1
#: ('dub-cli' still convicted, so the class keeps working). Explicit
#: ``0``/``false``/``off``/``no`` ⇒ the pre-fixb146 predicate,
#: byte-identical (kill-switch forever); unset ≡ explicit ``1``.
WS_EVIDENCE_DISCRIMINATOR_ENV = "WYSTAN_WS_EVIDENCE_DISCRIMINATOR"


def ws_evidence_discriminator_enabled() -> bool:
    """fixb146 Row 2 — product-evidence discriminator on ``ws_anchor_no_uf``.
    Default **ON** since the 2026-08-11 flip-pack №43 (KEY_SCHEMA 78).
    Explicit ``0``/``false``/``off``/``no`` is a kill-switch forever; unset
    ≡ explicit ``1``. The truthy set is preserved LITERALLY — only the
    ``os.environ.get`` default moved ``"0"`` -> ``"1"``."""
    return os.environ.get(
        WS_EVIDENCE_DISCRIMINATOR_ENV, "1",
    ).strip().lower() in {"1", "true", "yes", "on"}


SEVERITY_INFO = "info"
SEVERITY_WARN = "warn"
SEVERITY_CRITICAL = "critical"

#: scan_meta size bound for a hook's exhibit list (mirrors the
#: ``uf_dropped_names`` / ``dissolved_names`` bounds elsewhere).
EXHIBIT_CAP = 20


def invariant_hooks_enabled() -> bool:
    """Default **ON** since the 2026-07-23 flip-pack №6 flip (KEY_SCHEMA 39;
    byte-additivity + 1:1 census-parity on 3 keyed boards). Unset now arms
    the sentinels. Explicit ``0`` / ``false`` / ``off`` / ``no`` / ``""`` ⇒
    every hook entry point is a pure no-op (byte-identical; kill-switch
    forever). The pre-flip truthy set ``{"1","true","yes","on"}`` is preserved
    LITERALLY — only the ``os.environ.get`` default moved ``"0"`` -> ``"1"``
    (unset ≡ explicit ``"1"``)."""
    return os.environ.get(INVARIANT_HOOKS_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


# ── record + registry ───────────────────────────────────────────────────
CheckFn = Callable[[dict[str, Any]], "list[str]"]


@dataclass(frozen=True)
class InvariantHook:
    """One registered sentinel: a bug ``cls`` on producer ``stage`` with a
    ``severity`` and a pure ``check`` returning its offending-row exhibits."""

    cls: str
    stage: str
    severity: str
    check: CheckFn


#: stage id -> hooks (registration order preserved ⇒ deterministic).
_REGISTRY: dict[str, list[InvariantHook]] = {}


def register(cls: str, stage: str, severity: str, check: CheckFn) -> CheckFn:
    """Register a sentinel. Returns ``check`` so it can double as a
    decorator. Idempotent per (cls, stage) — a duplicate registration
    (e.g. a module re-import) replaces rather than appends."""
    hooks = _REGISTRY.setdefault(stage, [])
    hook = InvariantHook(cls=cls, stage=stage, severity=severity, check=check)
    for i, existing in enumerate(hooks):
        if existing.cls == cls:
            hooks[i] = hook
            return check
    hooks.append(hook)
    return check


def _make_record(hook: InvariantHook, exhibits: "list[str]") -> dict[str, Any]:
    ids = sorted({str(e) for e in exhibits})
    return {
        "class": hook.cls,
        "stage": hook.stage,
        "count": len(ids),
        "exhibits": ids[:EXHIBIT_CAP],
        "severity": hook.severity,
    }


def _append_record(scan_meta: dict[str, Any], rec: dict[str, Any]) -> None:
    scan_meta.setdefault("invariant_hooks", []).append(rec)
    if rec["severity"] == SEVERITY_CRITICAL and rec["count"] > 0:
        # critical → severity="failed" degradation so the install /
        # validate_scan guard blocks the board (it already keys off
        # severity=="failed"). Additive; only ever reached under the flag.
        from wystan.pipeline_v2.degradations import make as _make, SEVERITY_FAILED
        scan_meta.setdefault("degradations", []).append(_make(
            "invariant_violation",
            stage=rec["stage"],
            severity=SEVERITY_FAILED,
            detail=(
                f"invariant hook '{rec['class']}' fired at stage "
                f"{rec['stage']}: {rec['count']} offending row(s)"
            ),
            invariant=rec["class"],
            count=rec["count"],
            exhibits=list(rec["exhibits"]),
        ))


def run_stage(scan_meta: dict[str, Any], stage: str, **data: Any) -> "list[dict[str, Any]]":
    """Fire every sentinel registered for ``stage`` over ``data`` and stamp
    their records. No-op (returns ``[]``, mutates nothing) when the flag is
    off. A check that raises is swallowed (a sentinel must never break a
    scan) and stamped as count 0."""
    if not invariant_hooks_enabled():
        return []
    out: list[dict[str, Any]] = []
    for hook in _REGISTRY.get(stage, ()):  # registration order — deterministic
        try:
            exhibits = list(hook.check(data) or [])
        except Exception:  # noqa: BLE001 — a sentinel never breaks a scan
            exhibits = []
        rec = _make_record(hook, exhibits)
        _append_record(scan_meta, rec)
        out.append(rec)
    return out


# ── canonical predicates (mirror eval/product_right_gate.py; mechanism, ──
#    not vocabulary — the terminal census reproduces the external gate 1:1)
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_SPLIT_RE = re.compile(r"[^A-Za-z0-9]+")
_ALNUM_RE = re.compile(r"[^A-Za-z0-9]+")

#: bare transport-delivery tokens (a package whose NAME is one of these and
#: that HOARDS journeys is a transport masquerader, canon §"Transport").
TRANSPORT_TOKENS = frozenset({
    "trpc", "orpc", "grpc", "rpc", "graphql", "transport", "websocket",
})
TRANSPORT_HELD_MIN = 3  # a transport PF HOLDING > N journeys is a hoard

#: PF-anchor prefixes that denote a structural / dev container (never a
#: route surface) — the anchors a transport hoard can wear.
_CONTAINER_ANCHOR_PREFIXES = ("ws:", "dev:", "fdir:")

CANON_CLASS_IDS = (
    "dev_anchor_no_uf",       # dev:* anchor, 0 real UF, no nav_parent
    "short_name",             # PF display/name alnum length <= 2
    "ws_anchor_no_uf",        # ws:* anchor, 0 real UF (structural container)
    "transport_masquerade",   # transport package promoted, hoarding journeys
    "uf_orphan_no_lane",      # UF product_feature_id is None AND no lane_ref
)


def _tokenize(s: Any) -> set[str]:
    if not s:
        return set()
    spaced = _CAMEL_RE.sub(" ", str(s))
    return {w.lower() for w in _SPLIT_RE.split(spaced) if w}


def _display_toks(pf: Any) -> set[str]:
    """Display tokens MINUS the qualifier the fixb133 M2 rung injected
    (warden §37 blocker 1) — an engine-written word must not decide a
    transport-container verdict. Identity when the rung is off."""
    from wystan.pipeline_v2.pf_display_doctrine import (
        display_qualifier_stops,
    )

    return _tokenize(getattr(pf, "display_name", None)) - set(
        display_qualifier_stops(pf))


def _alnum_len(s: Any) -> int:
    return len(_ALNUM_RE.sub("", str(s or "")))


def _pf_name(pf: Any) -> str:
    return str(getattr(pf, "name", "") or "")


def _pf_ident(pf: Any) -> str:
    """The display identifier the length / masquerade rules judge — the
    display name if present, else the canonical name (external-gate order)."""
    return str(getattr(pf, "display_name", None) or getattr(pf, "name", "") or "")


def _pf_anchor(pf: Any) -> str:
    return str(getattr(pf, "anchor_id", "") or "")


def _is_product_pf(pf: Any) -> bool:
    return str(getattr(pf, "layer", "product") or "product") == "product"


def _uf_home(uf: Any) -> Any:
    return getattr(uf, "product_feature_id", None)


def index_board(
    product_features: "list[Any]", user_flows: "list[Any]",
) -> dict[str, dict[str, int]]:
    """Per-PF-name journey indices keyed by ``Feature.name`` (== the JSON
    ``product_feature_id`` a UF homes onto). ``real`` = non-synthesized
    member UFs (a backstop/seed synthesized UF is NOT a real journey — the
    external gate's FIELD TRUTH)."""
    held: dict[str, int] = {}
    real: dict[str, int] = {}
    homed: dict[Any, list[Any]] = {}
    for uf in user_flows:
        homed.setdefault(_uf_home(uf), []).append(uf)
    for pf in product_features:
        name = _pf_name(pf)
        members = homed.get(name, [])
        held[name] = len(members)
        real[name] = sum(1 for m in members if not getattr(m, "synthesized", False))
    return {"real_uf_count": real, "held_uf_count": held}


def _is_transport_masquerader(pf: Any, held_count: int, n: int = TRANSPORT_HELD_MIN) -> bool:
    """A transport DELIVERY package promoted to a PF that HOARDS the
    journeys of many domains passing through it. Precise (mirrors the
    external gate): a ``route:`` handler is a legit surface (excluded);
    only a package/module-level container anchor (ws:/dev:/fdir:) whose
    NAME is a bare transport token AND whose anchor carries a transport
    token AND that holds > N journeys trips."""
    anchor = _pf_anchor(pf)
    if anchor.startswith("route:"):
        return False
    name_toks = _tokenize(_pf_name(pf)) | _display_toks(pf)
    if not (name_toks & TRANSPORT_TOKENS):
        return False
    al = anchor.lower()
    if not any(al.startswith(p) for p in _CONTAINER_ANCHOR_PREFIXES):
        return False
    if not any(t in al for t in TRANSPORT_TOKENS):
        return False
    return held_count > n


def canon_classes(
    product_features: "list[Any]", user_flows: "list[Any]",
    developer_features: "list[Any] | None" = None,
) -> dict[str, "list[str]"]:
    """The five mechanical masquerader classes, computed 1:1 with
    ``eval/product_right_gate.py::canon_classes`` over the in-memory board.
    Returns ``{class_id: [sorted distinct exhibit ids]}`` — exhibit id is
    the PF ``name`` for PF classes, the UF ``id`` for ``uf_orphan_no_lane``.

    ``developer_features`` feeds the BOARD-grain flow prong of the fixb146
    ``ws_anchor_no_uf`` discriminator (flows live on the developer layer).
    Omitted / ``None`` ⇒ the prong falls back to ``pf.flows``, which is how
    an in-memory mint-grain caller supplies it.
    """
    idx = index_board(product_features, user_flows)
    real = idx["real_uf_count"]
    held = idx["held_uf_count"]
    ws_discriminate = ws_evidence_discriminator_enabled()
    flow_owners = pf_flow_owner_names(developer_features)
    out: dict[str, set[str]] = {k: set() for k in CANON_CLASS_IDS}

    for pf in product_features:
        if not _is_product_pf(pf):
            continue
        name = _pf_name(pf)
        anchor = _pf_anchor(pf)
        ident = _pf_ident(pf)
        rn = real.get(name, 0)
        hn = held.get(name, 0)
        if anchor.startswith("dev:") and rn == 0 and not getattr(pf, "nav_parent", None):
            out["dev_anchor_no_uf"].add(name)
        if _alnum_len(ident) <= 2:
            out["short_name"].add(name)
        if anchor.startswith("ws:") and rn == 0:
            # fixb146 Row 2 — a ws-PF carrying positive PRODUCT EVIDENCE is
            # not a structural container, which is the only thing this
            # class was written to catch. Flag OFF ⇒ the bare predicate.
            if not (ws_discriminate and has_product_evidence(
                has_flow=(name in flow_owners
                          or bool(getattr(pf, "flows", None))),
                nav_parent=getattr(pf, "nav_parent", None),
                paths=_feature_paths(pf),
            )):
                out["ws_anchor_no_uf"].add(name)
        if _is_transport_masquerader(pf, hn):
            out["transport_masquerade"].add(name)

    for uf in user_flows:
        # residual=True rows are LABELED DEBT (B77 contract; the 6.9965
        # honest-fallback / B90 stub-demote shape) — not orphans. Ruling
        # 2026-07-24 (B90): the class counts only UNLABELED homeless rows.
        if (_uf_home(uf) is None and not getattr(uf, "lane_ref", None)
                and not getattr(uf, "residual", False)):
            out["uf_orphan_no_lane"].add(str(getattr(uf, "id", "") or ""))

    return {k: sorted(v) for k, v in out.items()}


# ── seed-hook check functions (today's classes on their producer stages) ─
def _feature_paths(feature: Any) -> "list[str]":
    """All membership paths of a Feature — its ``paths`` plus its
    ``member_files[].path`` (the mint-grain evidence surface)."""
    paths = [str(p) for p in (getattr(feature, "paths", None) or [])]
    for mf in getattr(feature, "member_files", None) or []:
        p = getattr(mf, "path", None)
        if p:
            paths.append(str(p))
    return paths


def has_product_evidence(
    *, has_flow: bool, nav_parent: Any, paths: "Iterable[str]",
) -> bool:
    """THE B87 rung-2 product-evidence prongs — ONE decision, BOTH grains.

    Three prongs, any of which is positive product evidence: the thing
    owns a flow, it is mentioned in nav, or its subtree contains an
    authored client view component. Reuses the mint's
    ``_VIEW_COMPONENT_EXTS`` (single source of truth — never a copied
    list).

    Callers supply the prong VALUES because the prongs live on different
    channels at different grains, and that difference is exactly where a
    silent drift would hide:

    * MINT grain (a ``Feature`` at post-6.86) — flows live on
      ``feature.flows``; see :func:`_feature_has_product_evidence`.
    * BOARD grain (a product feature at terminal) — ``pf.flows`` is
      ALWAYS EMPTY by construction (flows live on the developer layer),
      so the flow prong MUST be read through membership: a PF owns a
      flow when a developer feature homed on it owns one. Reading
      ``pf.flows`` here would make the discriminator a no-op on its own
      exhibit — onyx's ``onyx-chat-widget`` has 0 ``pf.flows`` and 7
      flows through its 5 member developer features.

    Keeping the DECISION here (and only the accessors at the call sites)
    is what makes the seed-hook and the terminal census provably agree.
    """
    from wystan.pipeline_v2.stage_6_86_anchored_mint import _VIEW_COMPONENT_EXTS
    if has_flow:
        return True
    if nav_parent:
        return True
    return any(str(p).endswith(_VIEW_COMPONENT_EXTS) for p in paths)


def _feature_has_product_evidence(feature: Any) -> bool:
    """MINT-grain binding of :func:`has_product_evidence` (post-6.86, where
    UF and nav_parent are stamped LATER so only these three signals exist).
    Behaviour is unchanged from before the helper was extracted."""
    return has_product_evidence(
        has_flow=bool(getattr(feature, "flows", None)),
        nav_parent=getattr(feature, "nav_parent", None),
        paths=_feature_paths(feature),
    )


def pf_flow_owner_names(developer_features: "list[Any] | None") -> "set[str]":
    """BOARD-grain flow channel: the set of ``product_feature_id`` values
    that own >= 1 flow through a member developer feature.

    This is the board's answer to "does this PF own a flow" — the
    developer layer is where flows live (``pf.flows`` reads 0 for every
    PF on every board)."""
    owners: set[str] = set()
    for df in developer_features or []:
        if not getattr(df, "flows", None):
            continue
        pid = getattr(df, "product_feature_id", None)
        if pid:
            owners.add(str(pid))
    return owners


def check_pf_short_name(data: dict[str, Any]) -> "list[str]":
    """post-6.86 — a minted PF whose display/name is <= 2 alnum chars
    (single-letter 'R'/'I', 'v2', …). Anti-case: a real feature with a
    3+ char name never trips."""
    return [
        _pf_name(pf)
        for pf in (data.get("product_features") or [])
        if _is_product_pf(pf) and _alnum_len(_pf_ident(pf)) <= 2
    ]


def check_pf_dev_anchor_no_evidence(data: dict[str, Any]) -> "list[str]":
    """post-6.86 — a dev-standalone-minted PF (``anchor_id`` == ``dev:*``)
    carrying NO product-right evidence (no authored view, no flow, no nav).
    The B87 rung-2 disease at birth. Anti-case: a dev anchor that DOES own
    an authored view component / flow survives (real UI feature-dir)."""
    return [
        _pf_name(pf)
        for pf in (data.get("product_features") or [])
        if _is_product_pf(pf)
        and _pf_anchor(pf).startswith("dev:")
        and not _feature_has_product_evidence(pf)
    ]


def check_pf_ws_container_no_uf(data: dict[str, Any]) -> "list[str]":
    """post-6.86 — a workspace/package-anchored PF (``anchor_id`` == ``ws:*``)
    that is a bare structural container: no authored view, no flow, no nav
    evidence at mint. Anti-case: a ws-package that owns a page/flow surface
    (a real product app) survives."""
    return [
        _pf_name(pf)
        for pf in (data.get("product_features") or [])
        if _is_product_pf(pf)
        and _pf_anchor(pf).startswith("ws:")
        and not _feature_has_product_evidence(pf)
    ]


_SEED_REASON = "route_group_recall"


def _pf_transport_donor_keys(product_features: "list[Any]") -> set[str]:
    """PF ``name`` set for transport-DONOR packages — a container anchor
    (ws:/dev:/fdir:) whose name AND anchor carry a bare transport token.
    Mechanism-shared with :func:`_is_transport_masquerader` (minus the
    held-count hoard test — a donor is a transport package regardless of how
    many seeds landed on it)."""
    keys: set[str] = set()
    for pf in product_features:
        if not _is_product_pf(pf):
            continue
        anchor = _pf_anchor(pf)
        if anchor.startswith("route:"):
            continue
        al = anchor.lower()
        if not any(al.startswith(p) for p in _CONTAINER_ANCHOR_PREFIXES):
            continue
        if not any(t in al for t in TRANSPORT_TOKENS):
            continue
        name_toks = _tokenize(_pf_name(pf)) | _display_toks(pf)
        if name_toks & TRANSPORT_TOKENS:
            keys.add(_pf_name(pf))
    return keys


def check_synthetic_seed_transport_home(data: dict[str, Any]) -> "list[str]":
    """post-route_group_recall — a synthetic recall seed
    (``synthesis_reason == 'route_group_recall'``) homed onto a
    transport-donor PF (the B88 class). Stays a standing guard even with the
    B88 fix armed. Anti-case: a seed homed on its real DOMAIN PF, or an
    honest hole (``product_feature_id is None``), never trips; a real
    (non-synthesized) journey on a transport PF is a different class
    (transport_masquerade) and is NOT counted here."""
    pfs = data.get("product_features") or []
    donor_keys = _pf_transport_donor_keys(pfs)
    if not donor_keys:
        return []
    return [
        str(getattr(uf, "id", "") or "")
        for uf in (data.get("user_flows") or [])
        if getattr(uf, "synthesized", False)
        and str(getattr(uf, "synthesis_reason", "") or "") == _SEED_REASON
        and _uf_home(uf) in donor_keys
    ]


def check_carve_marker_in_display(data: dict[str, Any]) -> "list[str]":
    """post-6.996 — the B86 carve-marker leak: a fold-demote provenance
    marker (``b85_fold_demote`` / its lane-anchor form / the generic
    ``fold_demote`` shorthand) surfacing in a DISPLAY field
    (``name`` / ``display_name`` of a PF, ``name`` of a UF). B86 routed the
    marker to ``carve_provenance`` / ``anchor_id`` (structured, never
    display); this sentinel catches any regression back into display.
    Anti-case: a legitimate label that merely CONTAINS 'fold' (e.g. 'Folder
    manager') does NOT trip — only the exact internal marker substring
    does. Reuses the mint's ``_DEMOTE_MARKER`` constant (not a copy)."""
    from wystan.pipeline_v2.stage_6_86_anchored_mint import _DEMOTE_MARKER
    markers = (_DEMOTE_MARKER, "fold_demote")

    def _hit(text: Any) -> bool:
        low = str(text or "").lower()
        return any(m in low for m in markers)

    out: list[str] = []
    for pf in (data.get("product_features") or []):
        if _hit(getattr(pf, "display_name", None)) or _hit(getattr(pf, "name", None)):
            out.append(_pf_name(pf))
    for uf in (data.get("user_flows") or []):
        if _hit(getattr(uf, "name", None)):
            out.append(str(getattr(uf, "id", "") or ""))
    return out


def check_member_disjoint(data: dict[str, Any]) -> "list[str]":
    """post-6.997 — the I-DISJOINT invariant as a hook-stamp: a single
    ``flows[].uuid`` sitting in the ``member_flow_ids`` of MORE THAN ONE UF
    (the B84 double-claim class, subset-twin dup inflation). Wraps the
    existing runtime assert (``_assert_member_disjoint``) — reuses the same
    claim-detection mechanism (``_emission_claimers``, not a copy) but
    stamps instead of raising. Critical: a violation surviving to emission
    means the B84 reconcile was killed / regressed. Anti-case: a board whose
    every member id is claimed once is silent."""
    from wystan.pipeline_v2.member_disjoint_reconcile import _emission_claimers
    ufs = data.get("user_flows") or []
    claimers = _emission_claimers(ufs)
    return [m for m, cs in claimers.items() if len(cs) > 1]


def check_flow_backpointer_live(data: dict[str, Any]) -> "list[str]":
    """post-6.997 — the I14 invariant as a hook-stamp (fixb103): a
    ``flows[].user_flow_id`` that names NO live ``user_flows[].id``.

    The mirror of :func:`check_member_exists` on the reverse edge. A stale
    backpointer breaks the same ``(file,line) -> flow -> UF -> PF``
    reverse-lookup contract from the other direction, and it is exactly the
    class ``eval/validate_scan.py``'s I14 has always failed the board on
    ("user_flow_id backpointers reference nonexistent UFs" — 222/3740 on
    infisical ON, 45 OFF, before the 6.997 re-derivation).

    A violation surviving to this seam means the re-derivation was
    regressed, or a NEW UF-dissolving producer landed after it without the
    "I14 — repoint, never dangle" hook its siblings (``spray_absorption``,
    ``uf_cases_split``) carry.

    Vacuously silent when the stage passed no ``flows`` or no
    ``user_flows`` (a caller without both stores cannot be judged). A
    ``user_flow_id`` of ``None`` is NOT a violation — it is the contracted
    value for a flow no journey claims.
    """
    flows = data.get("flows")
    user_flows = data.get("user_flows")
    if not flows or not user_flows:
        return []
    live = {
        str(u) for u in (
            getattr(uf, "id", None) or (
                uf.get("id") if isinstance(uf, dict) else None
            )
            for uf in user_flows
        ) if u
    }
    if not live:
        return []
    bad: list[str] = []
    for fl in flows:
        ref = (getattr(fl, "user_flow_id", None)
               if not isinstance(fl, dict) else fl.get("user_flow_id"))
        if not ref or str(ref) in live:
            continue
        key = (getattr(fl, "uuid", None)
               if not isinstance(fl, dict) else fl.get("uuid"))
        bad.append(f"{key or '?'}:{ref}")
    return bad


def check_member_exists(data: dict[str, Any]) -> "list[str]":
    """post-6.997 — the I-EXISTS invariant as a hook-stamp (B102): a
    ``member_flow_ids`` entry that resolves to NO ``flows[].uuid``. Such a
    pointer is silently skipped by every member-derived consumer
    (``stage_6_97b_uf_loc``, ``stage_6_97d_uf_metrics``), so the row keeps
    ``member_count>0`` and renders ``loc=0`` — the hollow row. A violation
    surviving to emission means the 6.997a repair was regressed or a NEW
    post-mint flow-merge producer landed after the seam.

    Vacuously silent when the stage passed no ``flows`` (callers that do not
    supply the flow store cannot be judged). Anti-cases: a member id that
    resolves — including one the repair REMAPPED onto its merge survivor —
    is never counted; and a row the repair deliberately ABSTAINED on
    (``member_exists_accounted`` — dropping its last member would have
    dissolved the journey, B33) is accounted, not a violation. The invariant
    is "absent from ``flows[].uuid`` ∪ unresolvable-ACCOUNTED".
    """
    flows = data.get("flows")
    if not flows:
        return []
    accounted = {str(x) for x in (data.get("member_exists_accounted") or ())}
    live = {
        str(u) for u in (
            getattr(fl, "uuid", None) or (
                fl.get("uuid") if isinstance(fl, dict) else None
            )
            for fl in flows
        ) if u
    }
    if not live:
        return []
    bad: list[str] = []
    for uf in (data.get("user_flows") or []):
        uid = str(getattr(uf, "id", None) or getattr(uf, "uuid", None) or "")
        if uid in accounted:
            continue
        for m in (getattr(uf, "member_flow_ids", None) or ()):
            if str(m) not in live:
                bad.append(f"{uid}:{m}")
    return bad


def check_member_exists_abstained(data: dict[str, Any]) -> "list[str]":
    """post-6.997 (fixb116) — the DANGLING refs the 6.997a repair
    deliberately ABSTAINED on, counted independently of that ruling.

    THE BUG THIS CLOSES (VERIFIED, ollama + directus fresh keyed 2026-08-06):
    :func:`check_member_exists` skips an accounted row WHOLE
    (``if uid in accounted: continue``), so a board carrying a live dangling
    uuid reported ``member_exists`` count **0**. The abstain is a legitimate
    B33 conservation ruling — it must not fail the board — but "we decided
    to keep it" is not the same statement as "there is nothing there", and
    the emitted row still advertises ``member_count>0`` while rendering
    ``loc=0``. Named exhibits, each ON-only and each already inside
    ``uf_member_exists.abstained_rows`` (so this was never a bypass of the
    accounting — it was a bypass of the SENTINEL):

    * directus ``UF-049`` 'Scaffold Directus extension' — mc=1, loc=0; its
      only member folded into ``connect-to-database-flow``, which
      ``UF-013`` 'Configure database dialects and connections' owns.
    * ollama ``UF-001`` 'Authenticate and manage account' — mc=1, loc=0; its
      only member folded into ``authenticate-and-manage-account-flow``,
      which ``UF-003`` 'Connect API tags' owns.
    * infisical ``UF-226`` 'Manage Auth integration (move)' — mc=2, loc=0,
      both members untraceable.

    WARN, not CRITICAL, and deliberately a SEPARATE class from
    ``member_exists``: a conservation abstain is labeled debt (the B77
    residual doctrine), not a broken invariant, so it is counted and
    exhibited without stamping the ``failed`` degradation that blocks a
    board. The CRITICAL sibling keeps its exact semantics — an UNACCOUNTED
    dangling ref still fails.

    Anti-cases: a resolving member (including one the repair REMAPPED onto
    its merge survivor) is never counted; a row with NO dangling ref is
    never counted even if it appears in ``member_exists_accounted``; a seam
    that passes no ``flows`` stays vacuously silent, exactly as its sibling.
    """
    flows = data.get("flows")
    if not flows:
        return []
    accounted = {str(x) for x in (data.get("member_exists_accounted") or ())}
    if not accounted:
        return []
    live = {
        str(u) for u in (
            getattr(fl, "uuid", None) or (
                fl.get("uuid") if isinstance(fl, dict) else None
            )
            for fl in flows
        ) if u
    }
    if not live:
        return []
    bad: list[str] = []
    for uf in (data.get("user_flows") or []):
        uid = str(getattr(uf, "id", None) or getattr(uf, "uuid", None) or "")
        if uid not in accounted:
            continue
        for m in (getattr(uf, "member_flow_ids", None) or ()):
            if str(m) not in live:
                bad.append(f"{uid}:{m}")
    return bad


def check_pf_transport_donor_renders(data: dict[str, Any]) -> "list[str]":
    """post-6.9964 (B90 Seg A) — a transport-DONOR PF (a key the stage's B88
    resolver named in ``transport_donor_keys``) still rendering in
    ``product_features`` after the lane pass: the laned class resurrected.
    Vacuously silent when the stage passed no donor keys (flag off / no
    donor on the board). Anti-case: a non-donor ws-package PF (app-store,
    embeds — the anti-sink boundary) is never counted."""
    donor_keys = {str(k) for k in (data.get("transport_donor_keys") or ())}
    if not donor_keys:
        return []
    return [
        _pf_name(pf)
        for pf in (data.get("product_features") or [])
        if _is_product_pf(pf) and _pf_name(pf) in donor_keys
    ]


def check_pf_api_root_stub_no_evidence(data: dict[str, Any]) -> "list[str]":
    """post-6.9964 (B90 Seg B) — a ``route:`` PF mounted directly at an
    ``api`` path segment with ZERO product evidence (no ``nav_parent``, no
    authored view member) AND a micro journey profile (held ≤ 1, every
    member mc ≤ 3) still rendering after the demote pass. Reuses the
    stage's own predicates (mechanism, not a copy). Anti-cases: a deep api
    route (``api/<provider>/<leaf>``), an evidenced api product (nav /
    authored view / substantive journey set) never trip."""
    from wystan.pipeline_v2.stage_6_9964_pin_closers import (
        api_root_stub_leaf,
        has_api_stub_product_evidence,
        is_micro_profile,
    )
    members: dict[str, list[Any]] = {}
    for uf in (data.get("user_flows") or []):
        pid = _uf_home(uf)
        if pid:
            members.setdefault(str(pid), []).append(uf)
    return [
        _pf_name(pf)
        for pf in (data.get("product_features") or [])
        if _is_product_pf(pf)
        and api_root_stub_leaf(_pf_anchor(pf)) is not None
        and not has_api_stub_product_evidence(pf)
        and is_micro_profile(members.get(_pf_name(pf), []))
    ]


def check_pf_api_container_renders(data: dict[str, Any]) -> "list[str]":
    """post-6.9964 (B91 H4) — an api-container PF the stage's own
    phase-1 predicate DEMOTED (a key in ``api_container_demoted_keys``)
    still rendering in ``product_features`` after the pass: the demoted
    class resurrected (kill-switched fix / upstream regression).
    Vacuously silent when the stage demoted nothing. Anti-case: an
    abstained container (saved by a NAMED conjunct — journey veto,
    authored view, nav, sacred, mass) is never in the key set, so it is
    never counted. Mirrors the Seg A ``pf_transport_donor_renders``
    keys-passed pattern (the stage names the class, the hook guards
    rendering)."""
    demoted_keys = {
        str(k) for k in (data.get("api_container_demoted_keys") or ())
    }
    if not demoted_keys:
        return []
    return [
        _pf_name(pf)
        for pf in (data.get("product_features") or [])
        if _is_product_pf(pf) and _pf_name(pf) in demoted_keys
    ]


def check_pf_route_render_util_renders(data: dict[str, Any]) -> "list[str]":
    """post-6.9964 (B93 route-render-util) — a ``route:`` render-util PF the
    stage's own phase-1 predicate DEMOTED (a key in
    ``route_render_util_demoted_keys``) still rendering in
    ``product_features`` after the pass: the demoted class resurrected
    (kill-switched fix / upstream regression). Vacuously silent when the
    stage demoted nothing — a NO-OP in the default (arm OFF) world,
    byte-identical to the pre-B93 pipeline (fired ONLY under the flag, the
    B91/B82 own-key precedent). Anti-case: an abstained PF (saved by a NAMED
    conjunct — authored view, nav, substantive journey, sacred) is never in
    the key set, so it is never counted. Mirrors the H4
    ``pf_api_container_renders`` keys-passed pattern (the stage names the
    class, the hook guards rendering)."""
    demoted_keys = {
        str(k) for k in (data.get("route_render_util_demoted_keys") or ())
    }
    if not demoted_keys:
        return []
    return [
        _pf_name(pf)
        for pf in (data.get("product_features") or [])
        if _is_product_pf(pf) and _pf_name(pf) in demoted_keys
    ]


def check_flow_barrel_placeholder(data: dict[str, Any]) -> "list[str]":
    """post-3.5 (B82) — a flow whose entry is a 1-LINE placeholder while its
    entry file is a re-export barrel (``export { X } from './Y'``) STILL
    rendering after the Stage-3.5 span-recovery pass: the Form-A follow-through
    failed to redirect it (kill-switched arm / an unresolvable barrel /
    upstream regression). ``data["barrel_entry_files"]`` names the barrel
    files still standing as a flow entry at the seam; a flow entered from one
    of them with a collapsed ``(n, n)`` span is the residual class. Vacuously
    silent when the producer passed no barrels (arm off / no barrels) — so it
    is a NO-OP in the default (span-recovery OFF) world, byte-identical to the
    pre-B82 pipeline (fired ONLY under the flag, the B91 own-key precedent).
    A RECOVERED flow's entry file is the target (not a barrel), so it never
    trips — the sentinel measures exactly the un-recovered remainder."""
    barrels = {str(f) for f in (data.get("barrel_entry_files") or ())}
    if not barrels:
        return []
    out: list[str] = []
    for fl in (data.get("flows") or []):
        entry = getattr(fl, "entry", None)
        if not isinstance(entry, dict):
            continue
        ef = entry.get("file")
        lines = entry.get("lines")
        if (
            ef in barrels
            and isinstance(lines, (list, tuple))
            and len(lines) == 2
            and lines[0] == lines[1]
        ):
            out.append(str(getattr(fl, "name", "") or getattr(fl, "uuid", "")))
    return out


def check_pf_dup_flow_name(data: dict[str, Any]) -> "list[str]":
    """post-flow-name-seam (B92) — a product feature STILL holding ≥2 flows
    that share a name after the twin-collision rungs ran: the operator's
    ``dup_name_within_pf`` class (RefApp ``inventory`` minting
    ``filter-inventory-flow`` twice). Reuses the twin_collision predicate
    (mechanism, not a copy — 1:1 with ``eval/product_right_gate``'s matcher).
    Vacuously silent unless a B92 arm passed ``features`` + ``flows`` at the
    seam — a NO-OP in the default (both arms OFF) world, byte-identical to the
    pre-B92 pipeline (fired ONLY under the flag, the B82/B91 own-key
    precedent). Measures the RESIDUAL: 0 when Rung D held, fires on a
    kill-switched / regressed arm. Anti-case: a board whose every (PF, name)
    pair is unique is silent."""
    features = data.get("features")
    flows = data.get("flows")
    if not features or not flows:
        return []
    from wystan.pipeline_v2.twin_collision import pf_dup_flow_names
    return pf_dup_flow_names(features, flows)


def check_flow_decorator_support(data: dict[str, Any]) -> "list[str]":
    """post-3.5 (decorator-edge) — a flow whose decorated ENTRY carries a
    resolvable cross-module user-space (or same-file) decorator but whose graph
    is MISSING that decorator's SUPPORT node after the Stage-3.5 expansion: the
    ``decorated method → decorator implementation`` edge was dropped (kill-
    switched arm / node cap / upstream regression). ``data["decorator_expected"]``
    maps a flow uuid to the decorator-impl node ids ("<file>#<symbol>") it SHOULD
    carry — re-derived independently of the expander by the same resolver; a flow
    whose node set lacks one is the residual class. Vacuously silent when the
    producer passed no expected map (arm off / no decorated entries) — a NO-OP in
    the default (decorator-edges OFF) world, byte-identical to the pre-fix
    pipeline (fired ONLY under the flag, the B91/B82 own-key precedent). A flow
    that attached the node never trips — the sentinel measures exactly the
    un-attached remainder."""
    expected = data.get("decorator_expected") or {}
    if not expected:
        return []
    out: list[str] = []
    for fl in (data.get("flows") or []):
        key = str(getattr(fl, "uuid", "") or "")
        want = expected.get(key)
        if not want:
            continue
        node_ids = {
            getattr(n, "id", None) for n in (getattr(fl, "nodes", None) or [])
        }
        if any(t not in node_ids for t in want):
            out.append(str(getattr(fl, "name", "") or key))
    return out


def check_container_rehome_husk(data: dict[str, Any]) -> "list[str]":
    """B (container-journey-rehome) stage-producer sentinel — the over-mint
    residual: a domain-PF the stage MINTED (``container_rehome_tele['minted']``)
    that carries NO real owned body (0 member_files OR 0 LOC) is exactly the
    husk the §6.4 mint-gate must forbid (I2 phantom-guard). Measures the
    RESIDUAL: 0 when the no-husk gate held; fires on a regressed / kill-
    switched gate. Vacuously silent when the arm passed no telemetry (OFF
    world) — a NO-OP in the default world, byte-identical (the B91 own-key
    precedent). A minted PF with real owned LOC never trips."""
    tele = data.get("container_rehome_tele") or {}
    minted = {m.get("pf") for m in (tele.get("minted") or [])}
    if not minted:
        return []
    out: list[str] = []
    for pf in (data.get("product_features") or []):
        nm = str(getattr(pf, "name", "") or "")
        if nm not in minted:
            continue
        members = getattr(pf, "member_files", None) or []
        loc = int(getattr(pf, "loc", 0) or 0)
        owned_loc = sum(
            int((m.get("loc") if isinstance(m, dict) else getattr(m, "loc", 0)) or 0)
            for m in members
        )
        if not members or (loc <= 0 and owned_loc <= 0):
            out.append(nm)
    return out


def check_dissolved_dev_journey(data: dict[str, Any]) -> "list[str]":
    """B111 (6.9945 fold-conservation) stage-producer sentinel — a developer
    feature whose own PF tile the 6.86 mint DISSOLVED and whose journey
    material then failed the coherence ruler: no strict-majority journey
    home over its flows AND at least one flow no journey claims. The keyed
    c7proof exhibit is chatwoot ``documents`` (``UF-011`` 'Browse and manage
    documents', mc=6/high on the OFF board) — gone on the ON board with
    ``fold_coherence.orphans == 0`` and both lineage maps silent, so nothing
    in the scan recorded the loss.

    Reads the stamp's OWN telemetry (``fold_conservation_tele['rows']``) —
    the sentinel measures exactly the residual the stamp admitted, so a
    kill-switched / regressed stamp cannot hide the class. Vacuously silent
    when the arm passed no telemetry (OFF world) — a NO-OP in the default
    world, byte-identical (the B91 own-key precedent). A dev whose cohort
    stayed under one journey (chatwoot ``voice`` → ``UF-017``, 6/6) never
    trips."""
    tele = data.get("fold_conservation_tele") or {}
    return [
        str(r.get("dev") or "")
        for r in (tele.get("rows") or [])
        if r.get("dev")
    ]


def check_demote_gap_emitted(data: dict[str, Any]) -> "list[str]":
    """B112 (terminal gap-channel seam) sentinel — the Stage 6.7e demote
    law says a journey row leaves ``user_flows[]`` ONLY into a typed
    ``coverage_gaps[]`` entry ("a silent drop is forbidden"). The
    residual this measures is every ``demote_map[].gap_id`` the
    adjudicator CLAIMED that no emitted gap carries.

    The class it guards: the B68 terminal ladder's ``live_flow_owner``
    rung dissolved adjudicated rows tautologically — the demoted
    journey's own member flows own those files by construction — so
    chatwoot shipped 5 demotes with 5 claimed ids and ``coverage_gaps:
    []`` (midday: ``GAP-1257b9ae63``). Vacuously silent when the seam
    passed no demote map (OFF world / keyless / adjudicator inert) — a
    NO-OP in the default world, byte-identical (the B91 own-key
    precedent)."""
    demotes = data.get("demote_map") or []
    if not demotes:
        return []
    emitted = {
        str((g.get("id") if isinstance(g, dict) else getattr(g, "id", ""))
            or "")
        for g in (data.get("coverage_gaps") or [])
    }
    return [
        str(d.get("gap_id") or "")
        for d in demotes
        if d.get("gap_id") and str(d.get("gap_id")) not in emitted
    ]


def check_mint_silent_empty(data: dict[str, Any]) -> "list[str]":
    """B113 (6.86 mint seam) sentinel — the SILENT EMPTY BOARD.

    Operator law behind the class: an empty product layer must be either
    HONEST (the unit is a library / CLI / daemon with no product surface to
    find) or DEGRADED (something stamped a reason). ollama KS60 was neither:
    45 ``route`` anchors reached the mint, every one of them was barred
    ``api_only_surface``, ``applied=True`` handed phase_finalize ``[]``, and
    the board shipped 0 PF / 0 UF / 0 degradations — the KS57 board for the
    SAME commit carried 12 tiles and 11 journeys.

    The residual measured here is exactly that shape, and it is stated over
    the mint's OWN telemetry so a kill-switched or regressed rung cannot hide
    the class: the mint CLAIMED the product universe (``applied``), it had
    route-anchor material in hand (``anchors_by_source['route'] >= 1`` — the
    thing a library/CLI genuinely does NOT have), and it minted ZERO PFs.
    Exhibits are ``<anchor>|<bar>`` pairs — the coordinates of what was
    thrown away, per the "deletions land on the board with coordinates" law.

    The class-honest prong is the ROUTE-ANCHOR count, deliberately NOT the
    ``repo_class`` verdict the ledger's draft proposed: ollama IS an
    ``infra-daemon``, so a ``product-app``-only sentinel would have stayed
    silent on its own exhibit. Measured over 41 cold boards + the 20-repo
    world-60 sample: axios (library, 0 route anchors), caddy (cli-tool, 0)
    and fastapi (framework, 73 route anchors but 14 PFs) are all silent;
    ollama KS60 is the only firing unit in either world.

    Vacuously silent when the seam passed no mint telemetry, and silent when
    the board already carries a degradation (the emptiness is then explained,
    not silent)."""
    if data.get("degraded"):
        return []
    tele = data.get("mint_tele") or {}
    if not tele.get("applied"):
        return []
    if int(tele.get("pf_minted") or 0) > 0:
        return []
    by_source = tele.get("anchors_by_source") or {}
    if int(by_source.get("route") or 0) < 1:
        return []
    bars = [
        f"{d.get('anchor')}|{d.get('bar')}"
        for d in (tele.get("bar_decisions") or [])
        if isinstance(d, dict) and d.get("anchor")
    ]
    return bars or [f"route_anchors:{int(by_source.get('route') or 0)}"]


# ── registrations (order == invariant_hooks[] record order per seam) ─────
register("pf_short_name", "6.86", SEVERITY_WARN, check_pf_short_name)
register("pf_dev_anchor_no_evidence", "6.86", SEVERITY_WARN,
         check_pf_dev_anchor_no_evidence)
register("pf_ws_container_no_uf", "6.86", SEVERITY_WARN,
         check_pf_ws_container_no_uf)
register("synthetic_seed_transport_home", "route_group_recall", SEVERITY_WARN,
         check_synthetic_seed_transport_home)
register("carve_marker_in_display", "6.996", SEVERITY_CRITICAL,
         check_carve_marker_in_display)
register("member_disjoint", "6.997", SEVERITY_CRITICAL, check_member_disjoint)
# B102 — I-EXISTS at the same 6.997 seam. Critical for the same reason as
# its I-DISJOINT sibling: a surviving violation breaks the
# (file,line) -> flow -> UF -> PF reverse-lookup contract. Silent unless the
# seam passes ``flows`` (callers without the flow store cannot judge).
register("member_exists", "6.997", SEVERITY_CRITICAL, check_member_exists)
# fixb103 — I14 at the same 6.997 seam, the reverse edge of I-EXISTS. Same
# severity for the same reason: a stale backpointer breaks the
# (file,line) -> flow -> UF -> PF contract from the flow side.
register("flow_backpointer_live", "6.997", SEVERITY_CRITICAL,
         check_flow_backpointer_live)
# fixb116 — OWN registry key ("6.997_member_abstain"), never "6.997": the
# abstain sentinel rides WYSTAN_UF_MEMBER_COORD_LINEAGE (armed OFF), so a
# third record on the "6.997" key would change every DEFAULT board's
# invariant_hooks[] and break the flag's unset ≡ OFF byte-identity. The B91
# precedent: phase_finalize fires this key ONLY when the flag is armed.
register("member_exists_abstained", "6.997_member_abstain", SEVERITY_WARN,
         check_member_exists_abstained)
register("pf_transport_donor_renders", "6.9964", SEVERITY_WARN,
         check_pf_transport_donor_renders)
register("pf_api_root_stub_no_evidence", "6.9964", SEVERITY_WARN,
         check_pf_api_root_stub_no_evidence)
# B91 — OWN registry key (never "6.9964"): the Seg A/B seam fires in the
# default world since flip-pack №7, and a third record there would break
# the B91 unset ≡ OFF byte-identity. phase_finalize fires this key ONLY
# under WYSTAN_API_CONTAINER_DEMOTE.
register("pf_api_container_renders", "6.9964_api_container", SEVERITY_WARN,
         check_pf_api_container_renders)
# B93 — OWN registry key ("6.9964_route_render_util"): the route-render-util
# arm is default OFF, so phase_finalize fires this key ONLY when armed
# (route_render_util_demoted_keys passed at the seam), keeping the default
# world byte-identical (the B91 own-key precedent).
register("pf_route_render_util_renders", "6.9964_route_render_util",
         SEVERITY_WARN, check_pf_route_render_util_renders)
# B82 — OWN registry key ("3.5_span_recovery"): the span-recovery arms are
# default OFF, so phase_finalize fires this key ONLY when an arm is armed
# (barrel_entry_files non-empty), keeping the default world byte-identical.
register("flow_barrel_placeholder", "3.5_span_recovery", SEVERITY_WARN,
         check_flow_barrel_placeholder)
# Decorator-edge — OWN registry key ("3.5_decorator_edges"): the arm is default
# OFF, so phase_finalize fires this key ONLY when armed (decorator_expected
# non-empty), keeping the default world byte-identical.
register("flow_decorator_support", "3.5_decorator_edges", SEVERITY_WARN,
         check_flow_decorator_support)
# B92 — OWN registry key ("twin_collision"): the twin-collision rungs are
# default OFF, so phase_finalize fires this key ONLY when a B92 arm is armed
# (features + flows passed at the flow-name seam), keeping the default world
# byte-identical. The sentinel measures the RESIDUAL after Rung D/B.
register("pf_dup_flow_name", "twin_collision", SEVERITY_WARN,
         check_pf_dup_flow_name)
# B (container-journey-rehome) — OWN registry key
# ("6.9966_container_journey_rehome"): the arm is default OFF, so
# phase_finalize fires this key ONLY when armed (container_rehome_tele passed
# at the 6.9966 seam), keeping the default world byte-identical (the B91
# own-key precedent). The sentinel measures the over-mint husk RESIDUAL.
register("container_rehome_husk", "6.9966_container_journey_rehome",
         SEVERITY_WARN, check_container_rehome_husk)
# B111 — OWN registry key ("6.9945_fold_conservation"): the stamp is default
# OFF, so phase_finalize fires this key ONLY when armed (fold_conservation
# telemetry passed at the seam), keeping the default world byte-identical
# (the B91 own-key precedent). WARN, not CRITICAL: the class is standing
# debt present on BOTH arms of the keyed pair (chatwoot OFF 7 rows / ON 8),
# so a critical severity would append a ``failed`` degradation and block
# install on boards the sentinel merely DESCRIBES. Escalation to critical is
# a lead ruling once the class is driven to zero.
register("dissolved_dev_journey", "6.9945_fold_conservation", SEVERITY_WARN,
         check_dissolved_dev_journey)
# B112 — OWN registry key ("6.995_demote_gap_emission"): the emission fix is
# default OFF, so phase_finalize fires this key ONLY when armed (demote_map
# passed at the terminal gap seam), keeping the default world byte-identical.
# The sentinel measures the RESIDUAL after the admission carve: 0 claimed-
# but-unemitted gap ids is the contract.
register("demote_gap_emitted", "6.995_demote_gap_emission", SEVERITY_CRITICAL,
         check_demote_gap_emitted)
# B113 — OWN registry key ("6.86_mint_universe"), NOT the shared "6.86" seam:
# that seam fires on every scan, so registering there would append a record to
# ``invariant_hooks[]`` for every repo in the default world. phase_finalize
# fires this key only under WYSTAN_MINT_SILENT_EMPTY_SENTINEL ⇒ OFF is
# byte-identical (the B91/B112 own-key precedent). WARN, not critical: the
# class is a DIAGNOSIS of an upstream inversion, and a critical would append a
# ``failed`` degradation that blocks install on a board whose emptiness may yet
# be correct. Escalation is a lead ruling once the class is driven to zero.
register("mint_silent_empty", "6.86_mint_universe", SEVERITY_WARN,
         check_mint_silent_empty)


def check_journey_lineage_unaccounted(data: dict[str, Any]) -> "list[str]":
    """fixb119 M1 (emission seam) sentinel — the UNACCOUNTED JOURNEY DEATH.

    A journey row alive at the post-``journey_lattice`` seam that is NOT on
    the emitted board, NOT re-minted (RE-ID), NOT an abstain, and named by
    NO removal channel — neither id-tier nor name-tier. Probe P15 measured
    71/154 such deaths (46%) across 8 boards: the consumer cannot tell
    "dropped honestly" from "dropped silently".

    Vacuously silent when the audit passed no ids (OFF world — the flag
    gates the whole seam, so no key and no record ⇒ byte-identical; the
    B91/B112 own-key precedent).

    WARN, not critical: the audit CHANGES NOTHING on the board, and most
    deaths conserve their material (55/97 terminal deaths have
    ``member_absorbed == 1.00`` — dedup, not coverage loss). A critical
    would append a ``failed`` degradation and block install on boards whose
    journeys are honestly deduped. Escalation to critical is a lead ruling
    once the class is driven toward zero by the per-writer registry (M6)."""
    return [str(u) for u in (data.get("unaccounted_ids") or []) if u]


register("journey_lineage_unaccounted", "journey_lineage_audit", SEVERITY_WARN,
         check_journey_lineage_unaccounted)


def check_journey_lineage_conservation(data: dict[str, Any]) -> "list[str]":
    """fixb121 (emission seam) — the two-sided conservation loop.

    ``snapshot + births − deaths == emitted``. NOT a tautology: ``deaths``
    is the SUM OF THE BUCKETS, so a missing ``continue`` (a row landing in
    two buckets) or a bucket left out of the sum breaks the equality while
    every individual count still looks plausible. Fires ONE record naming
    the four terms, so the arithmetic of a stamp can be checked from the
    board instead of re-derived by hand.

    Vacuously silent when the audit is OFF (no ids passed ⇒ no key ⇒
    byte-identical) and when the loop closes."""
    if data.get("conservation_ok", True):
        return []
    return [
        "snapshot=%s births=%s deaths=%s emitted=%s" % (
            data.get("snapshot"), data.get("births_count"),
            data.get("deaths"), data.get("emitted"),
        ),
    ]


register("journey_lineage_conservation", "journey_lineage_audit",
         SEVERITY_WARN, check_journey_lineage_conservation)


# ── terminal product-right census ────────────────────────────────────────
def run_product_right_census(
    scan_meta: dict[str, Any],
    product_features: "list[Any]",
    user_flows: "list[Any]",
    developer_features: "list[Any] | None" = None,
) -> dict[str, Any] | None:
    """Terminal (pre-emission) — compute the five canon masquerader classes
    1:1 with ``eval/product_right_gate.py`` and stamp them so the board
    CARRIES ITS OWN CENSUS: the external gate reads
    ``scan_meta.product_right_census`` as its FIRST source (its own recount
    stays a fallback). Also appends one ``info`` record per class to
    ``scan_meta.invariant_hooks[]`` for a uniform audit trail. No-op / no
    key when the flag is off (byte-identical)."""
    if not invariant_hooks_enabled():
        return None
    classes = canon_classes(
        product_features or [], user_flows or [], developer_features or [])
    census = {
        "class_ids": list(CANON_CLASS_IDS),
        "classes": {
            cls: {
                "count": len(classes[cls]),
                "exhibits": classes[cls][:EXHIBIT_CAP],
            }
            for cls in CANON_CLASS_IDS
        },
    }
    scan_meta["product_right_census"] = census
    for cls in CANON_CLASS_IDS:
        rec = _make_record(
            InvariantHook(cls=cls, stage="terminal", severity=SEVERITY_INFO,
                          check=lambda _d: []),
            classes[cls],
        )
        _append_record(scan_meta, rec)
    return census
