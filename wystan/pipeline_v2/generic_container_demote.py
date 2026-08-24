"""generic_container_demote — B96: technical-husk PF demote (Stage 6.9969).

THE PROBLEM (operator exhibits 2026-08-02, hoppscotch KS48 board): the
Layer-2 output carries top-level Product Features named after TRANSPORT
PROTOCOLS / GENERIC CONTAINERS / DEV CONSTRUCTS — ``http`` (44 files),
``graphql`` (38), ``realtime`` (15), ``mockserver`` (10), all
``container-rehome:ws:packages/hoppscotch-common/<leaf>`` mints holding
ZERO journeys; plus the stale-board census class of anchor-less ``core``
(strapi, 3133 files) / ``app`` / ``api`` / ``test`` (directus). A user
cannot recognise "http" as a product capability ("features like feature —
user doesn't know what https is"); one such row makes the reader distrust
every row. The engine's own read-only census already NAMES this shape
(``canon_classes`` ``ws_anchor_no_uf`` / ``dev_anchor_no_uf``) — B96 is
the missing ACTOR for the same signature.

WHY EVERY SIBLING GATE IS BLIND (trace 2026-08-02 @ ece2801f): each
vocab×UF gate hard-codes an anchor-kind subset of ``{route:, fdir:, ws:,
dev:, pypkg:}`` — none matches ``container-rehome:`` (the ``_mint_pf``
stamp, stage_6_9966:545) or an ABSENT anchor_id; B95's mechanism vocab is
SaaS-mechanism words; devgrain's is journey-step words; the engine's own
husk doctrine (``_mint_ok`` no_husk) is LOC==0 — a code-bearing
journey-less technical PF is intentionally kept. B96 adds the orthogonal
journey axis with the widest anchor scope.

THE DISCRIMINATOR — structural, vocab = corroboration only (mechanisms,
not dictionaries). A PF demotes iff ALL hold:

  (a) ``real_uf == 0`` — zero own NON-SYNTHESIZED journeys (held
      synthesized shells are artifacts, mirroring B95). The supabase
      anti-case (``realtime``/``database``/``storage`` hold 4-26 real
      journeys — marketed products) survives on this leg alone.
  (b) NAME-VOCAB corroboration — the normalized full name (never a
      substring) ∈ ``structural_stoplist`` (app/api/core/components/
      types/utils/test/…, spine-anchor-vocab.yaml) ∪ the new
      ``transport_protocol_tokens`` (http/graphql/realtime/mockserver/…).
      ANY anchor kind qualifies — including ``container-rehome:`` and
      anchor-less — the widening that makes the class reachable at all.
  (c) NO OWN PRODUCT-SURFACE — no ``nav_parent`` entry at all (a
      technical-named PF the author placed in the product IA survives).
  (d) NOT B48-SACRED — the anchor unit is not a technology-instrument
      sacred unit (published SDK packages etc., read back from the
      6.86 mint's own vetoed map — the exact H4 channel).

  BOARD-ABSTAIN (keyless/degraded guard): when the WHOLE board holds
  zero real journeys (``sum(real_uf) == 0``), a 0-UF read means "the UF
  layer is starved", not "this PF is empty" — the stage abstains as a
  no-op with named telemetry (the devgrain nav-abstain discipline).

  NO SIZE CEILING — deliberately no member-count cap (B95's ≤40 would
  wrongly exempt strapi ``core`` at 3133 files; rule-no-magic-tuning).

THE ACTION (conservation by construction): the PF leaves
``product_features``. Member devs re-home to (1) the surviving PF owning
the mint's ORIGIN container anchor (``container-rehome:X/leaf`` → the PF
anchored at ``X`` or its prefix-ancestor), else (2) the nearest surviving
ancestor by anchor-path containment, else (3) honest Layer-1 residual
(``product_feature_id=None`` + ``shared_reason=generic_container_demote``,
files/LOC kept — the LOC-real law). Journeys never move (real_uf==0);
held SYNTHESIZED shells drop with named telemetry (B95/devgrain
precedent). Flows stay on their primary devs; the bipartite store is
untouched.

Flag ``WYSTAN_GENERIC_CONTAINER_DEMOTE`` default **OFF** (armed-only;
KEY_SCHEMA bump rides the flip commit, the flag-addition law). OFF /
unset ⇒ ``None`` before any mutation, no ``scan_meta`` key ⇒
byte-identical (kill-switch). Deterministic, $0 LLM, no network.
"""

from __future__ import annotations

import os
from collections import defaultdict
from functools import lru_cache
from typing import Any

from wystan.pipeline_v2.spine_anchors import (
    load_spine_vocab,
    normalize_anchor_key,
)
from wystan.pipeline_v2.stage_6_9964_pin_closers import b48_sacred_units

__all__ = [
    "GENERIC_CONTAINER_DEMOTE_ENV",
    "generic_container_demote_enabled",
    "is_technical_husk_pf",
    "run_generic_container_demote",
]

GENERIC_CONTAINER_DEMOTE_ENV = "WYSTAN_GENERIC_CONTAINER_DEMOTE"

#: ``shared_reason`` stamped on residual member devs (sibling convention).
_SHARED_REASON = "generic_container_demote"


def generic_container_demote_enabled() -> bool:
    """B96 technical-husk demote — default **ON** since flip-pack #16
    (KEY_SCHEMA 51, 2026-08-02): keyed A/B hoppscotch net delta ∅ +
    offline exhibit gates (KS48 EXACTLY {http,graphql,realtime,mockserver};
    supabase {static}, the anti-case survived; directus/highlight/strapi
    fresh keyless). Unset ≡ explicit ``1`` (inverted kill-switch unit).
    Explicit ``0``/``false``/``off``/``no`` ⇒ ``None`` before any
    mutation, with no ``scan_meta`` key ⇒ kill-switch forever."""
    return os.environ.get(GENERIC_CONTAINER_DEMOTE_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


@lru_cache(maxsize=1)
def _husk_vocab() -> frozenset[str]:
    """``structural_stoplist`` ∪ ``transport_protocol_tokens`` from the spine
    vocab, each entry normalized through the SAME normalizer the matcher uses
    (so plural/camel entries can never silently miss). Data, never code."""
    vocab = load_spine_vocab()
    raw = list(vocab.get("structural_stoplist") or ()) + list(
        vocab.get("transport_protocol_tokens") or ()
    )
    return frozenset(
        normalize_anchor_key(str(s)) for s in raw if str(s).strip()
    )


def _pf_name(pf: Any) -> str:
    return str(getattr(pf, "name", "") or "").strip()


def _anchor_id(pf: Any) -> str:
    return str(getattr(pf, "anchor_id", None) or "")


def _anchor_leaf(aid: str) -> str:
    """Last path segment of the anchor's path part (``…/http`` → ``http``);
    empty for anchor-less rows."""
    if not aid:
        return ""
    path = aid.rsplit(":", 1)[-1]
    return path.rstrip("/").rsplit("/", 1)[-1]


def _vocab_hit(pf: Any, vocab: frozenset[str]) -> str | None:
    """The matched vocab key, or None. FULL normalized identity on the PF
    name and on the anchor leaf — never a substring, never a token subset
    (``api-keys`` → ``api-key`` ∉ vocab → survives; the compound-name law)."""
    for raw in (_pf_name(pf), _anchor_leaf(_anchor_id(pf))):
        if not raw:
            continue
        key = normalize_anchor_key(raw)
        if key in vocab:
            return key
    return None


def _anchor_path(pf: Any) -> str:
    """The path part of the anchor (kind prefixes stripped, including the
    compound ``container-rehome:ws:…`` double prefix)."""
    aid = _anchor_id(pf)
    return aid.rsplit(":", 1)[-1].strip("/") if aid else ""


def is_technical_husk_pf(
    pf: Any,
    real_uf: int,
    vocab: frozenset[str],
    sacred_units: frozenset[str],
) -> bool:
    """The pure B96 discriminator (no mutation). True ONLY when every leg
    holds: 0 real journeys, a vocab-corroborated technical name, no own nav
    surface, not B48-sacred. Anchor kind is deliberately UNCHECKED — the
    widening that lets ``container-rehome:``/anchor-less rows be seen."""
    if real_uf > 0:
        return False
    # fixb125 — a DECLARED COMMAND SURFACE is not a technical husk. The
    # ``real_uf == 0`` leg is a PROXY for "no product evidence"; a
    # ``cli:`` PF carries the evidence directly — registration sites in
    # an author-declared binary (gate G1 = import-binding ∧ a manifest
    # bin that resolves into the cluster). Without this the repo-echo
    # token demotes exactly the CLIs whose binary IS the product name
    # (measured on unkey: PF ``unkey``, 2 556 LOC, 73 commands, killed
    # by ``vocab_key=unkey``). Inert unless WYSTAN_CLI_ANCHOR_SUPPLY
    # is armed — no ``cli:`` anchor exists otherwise.
    if str(_anchor_id(pf)).startswith("cli:"):
        return False
    if _vocab_hit(pf, vocab) is None:
        return False
    if getattr(pf, "nav_parent", None):
        return False
    apath = _anchor_path(pf)
    if apath and any(
        apath == s or apath.startswith(s + "/") for s in sacred_units
    ):
        return False
    return True


def run_generic_container_demote(
    product_features: list[Any],
    developer_features: list[Any] | None,
    user_flows: list[Any] | None,
    scan_meta: dict[str, Any] | None = None,
    extra_husk_tokens: frozenset[str] | None = None,
) -> dict[str, Any] | None:
    """Demote technical-husk PFs (in place) and return the
    ``scan_meta.generic_container_demote`` telemetry; ``None`` (no mutation,
    no key) when the flag is off. Runs post-UF ("last word" slot, after B95,
    before the B89 census + Stage 7) — ``user_flows[].product_feature_id``
    is final, so a 0-held read is trustworthy for the scan's whole life."""
    if not generic_container_demote_enabled():
        return None
    tele: dict[str, Any] = {
        "enabled": True,
        "demoted": [],
        "has_journeys_skipped": [],
        "has_surface_skipped": [],
        "sacred_veto_skipped": [],
        "dropped_ufs": {},
        "devs_rehomed": {},
        "devs_unowned": 0,
        "abstained": None,
    }
    products = [
        pf for pf in (product_features or [])
        if getattr(pf, "layer", "product") == "product"
    ]
    if not products:
        return tele

    vocab = _husk_vocab()
    if not vocab:  # unconfigured data ⇒ inert
        return tele
    if extra_husk_tokens:
        # DYNAMIC tokens from the scan context (the repo's own slug — a PF
        # wearing the repo name with zero journeys is a self-titled husk,
        # operator exhibits ``directus``/``better-auth``/``trigger-dev-2``).
        # A mechanism, never a dictionary: the token comes from ctx, so it
        # is correct for every repo without any vocab edit.
        vocab = vocab | frozenset(
            normalize_anchor_key(t) for t in extra_husk_tokens if t)
    sacred = b48_sacred_units(scan_meta or {})

    # Held journeys + real (non-synthesized) counts, per PF name.
    real_uf: dict[str, int] = defaultdict(int)
    held: dict[str, list[Any]] = defaultdict(list)
    for uf in (user_flows or []):
        pid = getattr(uf, "product_feature_id", None)
        if not pid:
            continue
        held[str(pid)].append(uf)
        if not getattr(uf, "synthesized", False):
            real_uf[str(pid)] += 1

    # BOARD-ABSTAIN — a board with zero real journeys anywhere carries no
    # usable journey signal (keyless / degraded scan): 0-UF would be true of
    # every PF, so the discriminator abstains rather than mass-demote.
    if sum(real_uf.values()) == 0:
        tele["abstained"] = "uf-starved-board"
        return tele

    devs_by_pf: dict[str, list[Any]] = defaultdict(list)
    for f in (developer_features or []):
        pid = getattr(f, "product_feature_id", None)
        if pid:
            devs_by_pf[str(pid)].append(f)

    # Phase 1 — decide against the same pre-pass board (sorted, deterministic).
    candidates: list[Any] = []
    for pf in sorted(products, key=_pf_name):
        name = _pf_name(pf)
        hit = _vocab_hit(pf, vocab)
        if hit is None:
            continue  # not a technical name — silent.
        if real_uf.get(name, 0) > 0:
            tele["has_journeys_skipped"].append(name)
            continue
        if getattr(pf, "nav_parent", None):
            tele["has_surface_skipped"].append(name)
            continue
        apath = _anchor_path(pf)
        if apath and any(
            apath == s or apath.startswith(s + "/") for s in sacred
        ):
            tele["sacred_veto_skipped"].append(name)
            continue
        if is_technical_husk_pf(pf, real_uf.get(name, 0), vocab, sacred):
            candidates.append((pf, hit))
    if not candidates:
        return tele

    surviving = [
        pf for pf in products
        if _pf_name(pf) not in {_pf_name(p) for p, _ in candidates}
    ]

    def _rehome_target(pf: Any) -> Any:
        """Origin-container owner first (``container-rehome:X/leaf`` → the
        surviving PF whose anchor path is a strict prefix of ours), else the
        longest surviving anchor-path ancestor, else None. Deterministic:
        longest path wins, name breaks ties."""
        apath = _anchor_path(pf)
        if not apath:
            return None
        best: tuple[int, str, Any] | None = None
        for other in surviving:
            opath = _anchor_path(other)
            if not opath:
                continue
            if apath == opath or apath.startswith(opath + "/"):
                cand = (len(opath), _pf_name(other), other)
                if best is None or (cand[0], cand[1]) > (best[0], best[1]):
                    best = cand
        return best[2] if best else None

    # Phase 2 — apply (sorted, deterministic).
    for pf, hit in sorted(candidates, key=lambda t: _pf_name(t[0])):
        name = _pf_name(pf)
        target = _rehome_target(pf)
        target_name = _pf_name(target) if target is not None else None

        # (1) Member devs → the ancestor PF where structurally determinable,
        #     else honest Layer-1 residual (files/LOC always kept).
        rehomed: list[str] = []
        for m in sorted(devs_by_pf.get(name, ()),
                        key=lambda d: str(getattr(d, "name", "") or "")):
            if target_name:
                m.product_feature_id = target_name
                rehomed.append(str(getattr(m, "name", "") or ""))
            else:
                m.product_feature_id = None
                m.shared_reason = _SHARED_REASON
                tele["devs_unowned"] += 1
        if rehomed:
            tele["devs_rehomed"][name] = {"into": target_name, "devs": rehomed}

        # (2) Held UFs are all SYNTHESIZED shells here (real_uf==0 gate) —
        #     drop with named telemetry (B95/devgrain precedent); the
        #     defensive real-UF branch is unreachable by construction.
        held_ufs = held.get(name, [])
        synth_held = [u for u in held_ufs if getattr(u, "synthesized", False)]
        if synth_held and user_flows is not None:
            tele["dropped_ufs"][name] = sorted(
                str(getattr(u, "name", "") or "") for u in synth_held)
            # fixb121 M6 — ``dropped_ufs`` writes the NAME, which the naming
            # contract already changed after the audit snapshot (chatwoot
            # UF-011: snapshot 'Components', here 'Connect components'), so a
            # name-tier record will not match. Self-report by id: it never drifts.
            from wystan.pipeline_v2.journey_lineage_audit import (
                report_journey_kill as _report_kill,
            )
            _report_kill(
                "generic_container_demote.run_generic_container_demote",
                [str(getattr(u, "id", "") or "") for u in synth_held],
            )
            dropped_ids = {id(x) for x in synth_held}
            user_flows[:] = [u for u in user_flows
                             if id(u) not in dropped_ids]

        # (3) The PF leaves the product list.
        product_features.remove(pf)
        tele["demoted"].append({
            "pf": name,
            "vocab_key": hit,
            "anchor_id": _anchor_id(pf) or None,
            "rehome_to": target_name,
        })

    return tele
