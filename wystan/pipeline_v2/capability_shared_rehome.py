"""capability_shared_rehome — B95: SHARED-re-home a capability-mechanism PF.

THE PROBLEM (operator exhibit ``twenty-capability-as-pf``, canon
``pf-product-grain-prompt.md`` class 'Capability (a shared ability)'): the
engine mints a top-level Product Feature for a shared MECHANISM — twenty
``Captcha`` (``fdir:…/modules/captcha``, 244 LOC / 14 files / 0 real journeys)
and ``File Upload`` (``route:file-upload``, 114 LOC / 4 files / 0 UF). Human
verification and file upload are not the product of a CRM; they are mechanisms
the journeys of MANY real features (auth, records, messages) pass through.
A capability wearing its own feature tile fails the demo test ("can you tell a
customer 'we do captcha' and they nod?" — no) and one such row makes the reader
distrust every row.

THE FIX — SHARED-re-home, NEVER delete (JSON-level; a display badge can not fix
wrong data — the external ``eval/product_right_gate.py`` reads
``product_features[]`` and matches the name, so the row must actually LEAVE the
peer-feature list): the capability PF is DEMOTED from ``product_features``. Its
flows become type=``secondary`` members of the journeys of the features that
CONSUME it (``feature_flow_edges`` — the bipartite model supports shared flows
natively); its member developer features stay in ``developer_features`` as
honest Layer-1 residual (``product_feature_id=None`` +
``shared_reason=capability_shared_rehome`` — files always kept). When no
consumer is structurally determinable (a flowless husk, or the B1 bipartite
cross-feature limitation — captcha/file-upload on the keyless twenty board) the
member files/flows stay as honest residual, exactly like the settings-frame
demote's no-ancestor case — conservation over invention, nothing lost.

THE DISCRIMINATOR — product-relative, STRUCTURAL, NOT the bare mechanism name
(the ``rule-no-magic-tuning`` / 'mechanisms, not dictionaries' law; the probe REFUTED
the xref-percentile leg — capabilities rank LOW in cross-feature usage, the
high-xref bucket is shared-infra). A PF is a demotable capability iff ALL hold:

  (a) MICRO JOURNEY PROFILE — ``real_uf == 0`` (ZERO own journeys: the twenty
      exhibits captcha/file/file-upload are all 0-UF; a mechanism-vocab row that
      carries EVEN ONE real journey is a reachable product surface, not a pure
      capability — the papermark ``notification-preferences`` control anti-case,
      a real settings page with 1 real UF that ``MAX_REAL_UF=1`` wrongly
      demoted) AND ``member_count <= MICRO_CAPABILITY_MAX_MEMBERS`` (a thin
      mechanism module; a mechanism-NAMED real product — photo storage,
      search-as-product — is large: twenty ``object-metadata`` 184 files,
      ``activities`` 261). Count-grain constants (widget-micro precedent),
      identical for every repo.
  (b) NO OWN PRODUCT-SURFACE — the structural demo-test EVIDENCE: no dedicated
      nav entry (``nav_parent`` absent / not a nav self-reference). A capability
      that the author placed in the product IA (ente ``Photos``/``Albums`` nav)
      HAS a surface and survives — the product-relative guard the probe's
      ente anti-case demands. (The 'no pricing/marketing page' + 'no
      user-reachable route-entry of its own' evidences are corroborated by
      leg (a)'s journey profile + leg (d)'s anchor kind — see the module note.)
  (c) MECHANISM-VOCAB CORROBORATION — the name/display TOKENS intersect the
      curated capability vocab (``captcha``/``upload``/``file``/``search``/
      ``notification``/``auth-verify`` in ``stacks/nav-tree.yaml``). Data, never
      the decision on its own — a vocab hit with a real journey set OR a product
      surface survives.
  (d) NOT B48/SDK VETO — the anchor kind is ``route:``/``fdir:`` ONLY (a
      published ``ws:`` workspace package is B48-sacred — twenty ``Twenty SDK``
      ``ws:packages/twenty-sdk`` is vetoed structurally), AND the name has no
      SDK/integration/embed veto token.

  NEGATIVE GUARD (xref) — a capability whose flows carry HIGH cross-feature
  consumer fan-in is shared-INFRA (renderer / server), routed to the B48/B53
  lane, NOT capability-demoted → abstain. On current real scans the bipartite
  cross-feature signal is empty (the B1 ``Flow.paths``-single-file limitation),
  so this guard is inert there; the named shared-infra rows are ``ws:`` (leg d)
  and non-vocab (leg c) anyway. Kept as the probe-mandated negative leg,
  unit-verified on a synthetic high-fan-in fixture.

Flag ``WYSTAN_CAPABILITY_SHARED_REHOME`` default OFF (armed-only; the
KEY_SCHEMA bump rides a later flip). OFF / unset ⇒ returns ``None`` before any
mutation, writes no ``scan_meta`` key ⇒ byte-identical to the pre-B95 engine
(kill-switch). Deterministic, $0 LLM, no network, read-only over the settled
PF / UF / dev / bipartite lists (mutating in place only for demoted rows).
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from functools import lru_cache
from typing import Any

from wystan.pipeline_v2.data import load_stack_yaml

__all__ = [
    "CAPABILITY_SHARED_REHOME_ENV",
    "capability_shared_rehome_enabled",
    "is_capability_pf",
    "run_capability_shared_rehome",
]

CAPABILITY_SHARED_REHOME_ENV = "WYSTAN_CAPABILITY_SHARED_REHOME"

#: ``shared_reason`` stamped on a demoted capability's member devs (mirrors the
#: settings-frame / nav-category / devgrain demote residual reasons).
_SHARED_REASON = "capability_shared_rehome"

#: ``reason`` stamped on the secondary edges minted for a re-homed flow.
_EDGE_REASON = "capability_shared_rehome"

#: Demote floors / ceilings — count-grain constants (widget-micro precedent,
#: no per-repo tuning; identical for every repo):
#:   * a capability carries ZERO OWN journeys — even ONE real journey means a
#:     user reaches and operates the row (a product surface, e.g. papermark
#:     ``notification-preferences``), never a pure shared mechanism;
#:   * a capability MECHANISM is a thin module — a mechanism-NAMED real product
#:     is large (twenty object-metadata 184 files, activities 261) and survives;
#:   * a capability serves a HANDFUL of consumers — HIGH cross-feature fan-in is
#:     shared-infra (routed to the B48/B53 lane, not capability-demoted).
_MAX_REAL_UF = 0
_MICRO_CAPABILITY_MAX_MEMBERS = 40
_XREF_SHARED_INFRA_MIN_CONSUMERS = 8

_TOKEN_RE = re.compile(r"[^a-z0-9]+")


def capability_shared_rehome_enabled() -> bool:
    """B95 capability SHARED-re-home — default **ON** since flip-pack №9
    (KEY_SCHEMA 42; 2026-07-28; exhibit-gate PASS — twenty keyless OFF
    ['Captcha'] → ON 0 hits, PF 52→50). Unset ≡ explicit ``1``: the demote arms.
    Explicit ``0`` / ``false`` / ``off`` / ``no`` (anything outside the truthy
    set) ⇒ the pass returns ``None`` before any mutation and writes no
    ``scan_meta`` key ⇒ byte-identical to the pre-B95 engine (kill-switch
    forever; inverted-kill-switch unit: unset ≡ explicit ``1``)."""
    return os.environ.get(CAPABILITY_SHARED_REHOME_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


@lru_cache(maxsize=1)
def _cfg() -> dict:
    return load_stack_yaml("nav-tree")


@lru_cache(maxsize=1)
def _mechanism_vocab() -> frozenset[str]:
    """Capability mechanism tokens (``captcha``/``upload``/…) — corroboration
    that narrows the candidate set, never the decision. Data (``nav-tree.yaml``,
    the settings-frame data-not-code precedent)."""
    return frozenset(
        str(s).strip().lower()
        for s in (_cfg().get("capability_mechanism_vocab") or ())
        if str(s).strip()
    )


@lru_cache(maxsize=1)
def _sdk_veto_vocab() -> frozenset[str]:
    """SDK / integration / embed VETO tokens — a B48-sacred published SDK or an
    integration/embed never demotes even on a mechanism-vocab name hit. Data."""
    return frozenset(
        str(s).strip().lower()
        for s in (_cfg().get("capability_sdk_veto_vocab") or ())
        if str(s).strip()
    )


def _tokenize(raw: str) -> frozenset[str]:
    return frozenset(t for t in _TOKEN_RE.split(str(raw or "").lower()) if t)


def _pf_slug(pf: Any) -> str:
    return str(getattr(pf, "name", "") or "").strip().lower()


def _pf_name_tokens(pf: Any) -> frozenset[str]:
    """The name AND display-name tokens (the exhibit matcher tests both, so the
    vocab narrower must too — ``name='file-upload'`` / ``display='File Upload'``
    both tokenize to ``{file, upload}``)."""
    return _tokenize(str(getattr(pf, "name", "") or "")) | _tokenize(
        str(getattr(pf, "display_name", "") or "")
    )


def _anchor_kind(pf: Any) -> str:
    aid = str(getattr(pf, "anchor_id", None) or "")
    return aid.split(":", 1)[0] if ":" in aid else ""


def _pf_member_count(pf: Any) -> int:
    mf = getattr(pf, "member_files", None) or []
    if mf:
        return len(mf)
    return len(getattr(pf, "paths", None) or [])


def _is_nav_self_ref(pf: Any) -> bool:
    np = getattr(pf, "nav_parent", None)
    if isinstance(np, dict) and np:
        parent_id = str(np.get("parent_id") or "").strip().lower()
        return bool(parent_id) and parent_id == _pf_slug(pf)
    return False


def is_capability_pf(
    pf: Any,
    real_uf: int,
    consumer_fan_in: int,
    mechanism_vocab: frozenset[str],
    sdk_veto_vocab: frozenset[str],
) -> bool:
    """See the module header — the demote discriminator. Pure, no mutation.
    Returns True ONLY for a demotable capability-mechanism PF (all four legs
    hold and the xref negative guard does not fire)."""
    name_toks = _pf_name_tokens(pf)
    # (c) mechanism-vocab corroboration — narrows the candidate set first.
    if not (name_toks & mechanism_vocab):
        return False
    # (d) B48 / SDK veto — a published ws: package or an SDK/integration/embed
    #     name is never a demote target.
    if _anchor_kind(pf) not in {"route", "fdir"}:
        return False
    if name_toks & sdk_veto_vocab:
        return False
    # (a) micro journey profile — 0-low OWN journeys AND thin member set.
    if real_uf > _MAX_REAL_UF:
        return False
    if _pf_member_count(pf) > _MICRO_CAPABILITY_MAX_MEMBERS:
        return False
    # (b) no own product-surface — no dedicated nav entry (nor a nav category
    #     self-reference). The product-relative demo-test evidence.
    if getattr(pf, "nav_parent", None) and not _is_nav_self_ref(pf):
        return False
    if _is_nav_self_ref(pf):
        return False
    # NEGATIVE guard — HIGH cross-feature consumer fan-in ⇒ shared-infra, route
    #     to the B48/B53 lane, not a capability-demote.
    if consumer_fan_in >= _XREF_SHARED_INFRA_MIN_CONSUMERS:
        return False
    return True


def _member_dev_names(product_feature_name: str, devs_by_pf: dict[str, list[Any]]) -> set[str]:
    return {
        str(getattr(d, "name", "") or "")
        for d in devs_by_pf.get(product_feature_name, ())
    }


def run_capability_shared_rehome(
    product_features: list[Any],
    developer_features: list[Any] | None,
    user_flows: list[Any] | None,
    flows: list[Any] | None = None,
    feature_flow_edges: list[Any] | None = None,
) -> dict[str, Any] | None:
    """Demote capability-mechanism PFs (in place) and return the
    ``scan_meta.capability_shared_rehome`` telemetry. Returns ``None`` — no
    mutation, no key — when the flag is off (byte-identical inertness).

    Only ``product_features`` rows are removed; member devs stay in
    ``developer_features`` as honest residual (``product_feature_id=None`` +
    ``shared_reason=capability_shared_rehome``, files kept); the capability's
    flows become type=``secondary`` members of consumer features' journeys via
    ``feature_flow_edges`` where consumers are structurally determinable, else
    they stay as honest residual (never dropped). A real held journey (the
    0-``_MAX_REAL_UF`` case) re-homes to a consumer if one exists, else becomes
    ``product_feature_id=None`` + ``residual=True`` — labeled debt, never an
    orphan. Conservation by construction: every file keeps a home in
    ``developer_features``; every flow keeps a home in ``flows``."""
    if not capability_shared_rehome_enabled():
        return None
    tele: dict[str, Any] = {
        "enabled": True,
        "demoted": [],
        "abstained_not_capability": [],
        "abstained_high_xref": [],
        "sdk_veto_skipped": [],
        "has_surface_skipped": [],
        "has_journeys_skipped": [],
        "too_large_skipped": [],
        "devs_unowned": 0,
        "flow_edges_minted": 0,
        "flows_shared": {},
        "residual_flows": {},
        "dropped_ufs": {},
        "rehomed_ufs": {},
        "residual_ufs": {},
    }
    products = [
        pf for pf in (product_features or [])
        if getattr(pf, "layer", "product") == "product"
    ]
    if not products:
        return tele

    mechanism_vocab = _mechanism_vocab()
    sdk_veto_vocab = _sdk_veto_vocab()
    if not mechanism_vocab:  # unconfigured data ⇒ inert
        return tele

    # Real (non-synthesized) journey counts + held journeys, per PF name.
    real_uf: dict[str, int] = defaultdict(int)
    held: dict[str, list[Any]] = defaultdict(list)
    for uf in (user_flows or []):
        pid = getattr(uf, "product_feature_id", None)
        if not pid:
            continue
        held[str(pid)].append(uf)
        if not getattr(uf, "synthesized", False):
            real_uf[str(pid)] += 1

    devs_by_pf: dict[str, list[Any]] = defaultdict(list)
    for f in (developer_features or []):
        pid = getattr(f, "product_feature_id", None)
        if pid:
            devs_by_pf[str(pid)].append(f)

    # Bipartite: flows by their code-grain primary owner (a dev name), and the
    # secondary-edge fan-in into a flow (distinct OTHER consumer features).
    flows_by_primary: dict[str, list[Any]] = defaultdict(list)
    for fl in (flows or []):
        flows_by_primary[str(getattr(fl, "primary_feature", "") or "")].append(fl)
    sec_consumers_by_flow: dict[str, set[str]] = defaultdict(set)
    for e in (feature_flow_edges or []):
        if str(getattr(e, "type", "") or "") == "secondary":
            sec_consumers_by_flow[str(getattr(e, "flow_id", "") or "")].add(
                str(getattr(e, "feature", "") or "")
            )

    def _capability_flows(pf_name: str) -> list[Any]:
        names = _member_dev_names(pf_name, devs_by_pf) or {pf_name}
        return [fl for n in names for fl in flows_by_primary.get(n, ())]

    def _flow_consumers(fl: Any, member_names: set[str]) -> set[str]:
        """Distinct OTHER features that consume this capability flow — the union
        of its bipartite secondary edges (stage 5.5) and its
        ``secondary_features`` list. Excludes the capability's own devs."""
        fid = str(getattr(fl, "id", "") or "")
        c = set(sec_consumers_by_flow.get(fid, set()))
        c |= {str(x) for x in (getattr(fl, "secondary_features", None) or []) if x}
        return c - member_names

    def _consumer_fan_in(pf_name: str) -> int:
        member_names = _member_dev_names(pf_name, devs_by_pf) or {pf_name}
        consumers: set[str] = set()
        for fl in _capability_flows(pf_name):
            consumers |= _flow_consumers(fl, member_names)
        return len(consumers)

    # Phase 1 — decide against the same pre-pass board (sorted → deterministic).
    candidates: list[Any] = []
    for pf in sorted(products, key=lambda p: str(getattr(p, "name", "") or "")):
        name = str(getattr(pf, "name", "") or "")
        name_toks = _pf_name_tokens(pf)
        if not (name_toks & mechanism_vocab):
            continue  # not even a mechanism-vocab candidate — silent.
        if _anchor_kind(pf) not in {"route", "fdir"} or (name_toks & sdk_veto_vocab):
            tele["sdk_veto_skipped"].append(name)
            continue
        if real_uf.get(name, 0) > _MAX_REAL_UF:
            tele["has_journeys_skipped"].append(name)
            continue
        if _pf_member_count(pf) > _MICRO_CAPABILITY_MAX_MEMBERS:
            tele["too_large_skipped"].append(name)
            continue
        if (getattr(pf, "nav_parent", None) and not _is_nav_self_ref(pf)) or _is_nav_self_ref(pf):
            tele["has_surface_skipped"].append(name)
            continue
        if _consumer_fan_in(name) >= _XREF_SHARED_INFRA_MIN_CONSUMERS:
            tele["abstained_high_xref"].append(name)
            continue
        # Belt-and-suspenders: the pure predicate agrees (all legs).
        if is_capability_pf(pf, real_uf.get(name, 0), _consumer_fan_in(name),
                            mechanism_vocab, sdk_veto_vocab):
            candidates.append(pf)
        else:  # pragma: no cover — the leg checks above are exhaustive.
            tele["abstained_not_capability"].append(name)
    if not candidates:
        return tele

    cand_keys = {str(getattr(pf, "name", "") or "") for pf in candidates}

    # Phase 2 — apply (sorted; deterministic). Every candidate demotes.
    demoted_keys: set[str] = set()
    dropped_uf_ids: set[int] = set()
    for pf in sorted(candidates, key=lambda p: str(getattr(p, "name", "") or "")):
        name = str(getattr(pf, "name", "") or "")
        aid = str(getattr(pf, "anchor_id", None) or "")
        member_names = _member_dev_names(name, devs_by_pf) or {name}
        cap_flows = _capability_flows(name)

        # Determine consumer features for this capability (distinct OTHER
        # features attached as SECONDARY to its flows — edges ∪ secondary_features).
        consumers: set[str] = set()
        for fl in cap_flows:
            consumers |= _flow_consumers(fl, member_names)

        demoted_keys.add(name)

        # (1) Flows → SHARED (secondary) members of consumer features' journeys.
        #     The flow keeps its code-grain primary; each consumer gets a
        #     secondary edge (minted if the stage-5.5 signal named it only on
        #     the flow) so the flow field and the edge list agree. When no
        #     consumer exists the flow stays as honest residual (its primary dev
        #     survives in developer_features — nothing lost).
        shared_flow_names: list[str] = []
        residual_flow_names: list[str] = []
        for fl in cap_flows:
            fid = str(getattr(fl, "id", "") or "")
            fl_name = str(getattr(fl, "name", "") or fid)
            fl_consumers = sorted(_flow_consumers(fl, member_names))
            if fl_consumers:
                if feature_flow_edges is not None:
                    existing = {
                        (str(getattr(e, "feature", "") or ""),
                         str(getattr(e, "flow_id", "") or ""))
                        for e in feature_flow_edges
                    }
                    for c in fl_consumers:
                        if (c, fid) not in existing:
                            from wystan.models.types import FeatureFlowEdge
                            feature_flow_edges.append(FeatureFlowEdge(
                                feature=c, flow_id=fid, type="secondary",
                                reason=_EDGE_REASON))
                            tele["flow_edges_minted"] += 1
                sec = list(getattr(fl, "secondary_features", None) or [])
                for c in fl_consumers:
                    if c not in sec:
                        sec.append(c)
                if hasattr(fl, "secondary_features"):
                    fl.secondary_features = sec
                if hasattr(fl, "cross_cutting"):
                    fl.cross_cutting = True
                shared_flow_names.append(fl_name)
            else:
                residual_flow_names.append(fl_name)
        if shared_flow_names:
            tele["flows_shared"][name] = sorted(shared_flow_names)
        if residual_flow_names:
            tele["residual_flows"][name] = sorted(residual_flow_names)

        # (2) Member devs → honest Layer-1 residual (files kept; no product
        #     tile). Their flows now carry the SHARED semantics via edges.
        for m in sorted(devs_by_pf.get(name, ()),
                        key=lambda d: str(getattr(d, "name", "") or "")):
            m.product_feature_id = None
            m.anchor_id = None
            m.shared_reason = _SHARED_REASON
            tele["devs_unowned"] += 1

        # (3) Held UFs: a demoted capability carries 0 real journeys (the
        #     real_uf==0 gate), so every held UF is a SYNTHESIZED shell — an
        #     artifact of the PF's existence, not recall. Drop it (mirrors the
        #     devgrain / settings-frame shell-UF drop) so no UF is left orphaned
        #     at the removed PF. A non-synthesized held UF cannot occur here
        #     (real_uf==0); the defensive branch re-homes it to a consumer, else
        #     honest residual — never dropped, never orphaned.
        held_ufs = held.get(name, [])
        synth_held = [u for u in held_ufs if getattr(u, "synthesized", False)]
        real_held = [u for u in held_ufs if not getattr(u, "synthesized", False)]
        if synth_held:
            tele["dropped_ufs"][name] = sorted(
                str(getattr(u, "name", "") or "") for u in synth_held)
            dropped_uf_ids.update(id(u) for u in synth_held)
        into = sorted(consumers)[0] if consumers else None
        if real_held:  # pragma: no cover — real_uf==0 gate makes this unreachable.
            if into is not None:
                tele["rehomed_ufs"][name] = {
                    "into": into,
                    "ufs": sorted(str(getattr(u, "name", "") or "") for u in real_held),
                }
                for u in real_held:
                    u.product_feature_id = into
            else:
                tele["residual_ufs"][name] = sorted(
                    str(getattr(u, "name", "") or "") for u in real_held)
                for u in real_held:
                    u.product_feature_id = None
                    u.residual = True

        tele["demoted"].append({
            "pf": name,
            "anchor": aid,
            "members": len(getattr(pf, "member_files", None) or []),
            "flows": len(cap_flows),
            "consumers": sorted(consumers),
            "flows_shared": len(shared_flow_names),
            "flows_residual": len(residual_flow_names),
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
