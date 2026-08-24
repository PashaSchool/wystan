"""Stage 6.9965 — B87 rung-2 (bullet 3) token-grain journey re-home.

THE DISEASE (census class E + F, H2-refutation, probe-canon E2 2026-07-23):
the mint fold ladder homes a journey by its member flows' CONSUMER / IMPORT
files, NOT by the journey's own resource / name tokens. So a journey lands
in a maskerader home — a killed / laned / structural-container PF — while a
DIFFERENT existing PF names the journey's actual entity. The probe refuted
"the mint ladder will resolve it itself" (midday dev:r folded onto the
neighbour route ``/(public)/r`` and still rode to ``invoices`` while the
real ``reports`` PF existed): the fold votes by files, so a post-mint
token rung is REQUIRED.

WHY POST-UF (B33 / B85 6.996+ doctrine): a mint-time re-home cascades
through the seed-plurality and hole-detection machinery and redraws the
board. This rail runs AFTER the whole homing family (6.99 / 6.99b organic
rehome, 6.996 member-disjoint, 6.997 agent-surface) and BEFORE 6.998
metrics-recompute, so the ONLY rows that change are the journeys it
explicitly moves (surgical blast radius; post-UF surgery conserves).

THE RULER (mechanism, not dictionary — rule-no-magic-tuning):
* SOURCE eligibility — only journeys whose current home LACKS product
  right: killed (``product_feature_id`` names no live PF), laned
  (``product_feature_id is None``), or a structural-container home
  (``dev:``/``ws:`` anchor, or a name in the structural stoplist, or a
  ≤2-char name). A journey correctly homed in a real-domain PF is never
  moved (no churn on healthy boards).
* TARGET eligibility — a real-domain PF (NOT a structural-container home,
  NOT a residual bucket). Never re-home INTO another maskerader.
* MATCH — normalized resource+name tokens (camel-split, stopword-drop,
  singular/plural fold). A killed/laned journey re-homes to the
  best-token-overlap target (≥1 shared token); a container-homed journey
  re-homes only when a real target ties-or-beats the container's overlap
  (move away from the container to the entity).
* HONEST FALLBACK — a killed/laned journey with NO token target keeps its
  honest residual state (``product_feature_id=None``, ``residual=True``);
  never an invented home. The structurally-blind single-letter-resource
  class (midday ``resource='r'``/``'i'``) lands here by construction.

DISPLACEMENT CONTRACT: every moved / fallback journey is named in the
telemetry ``displacements`` / ``fallbacks`` tables (id, name, from, to,
tokens, reason). Conservation is by-construction — member_flow_ids are
never touched; only ``product_feature_id`` (+ ``lane_ref`` clear on move,
``residual`` set on fallback) changes.

Gated by ``WYSTAN_PRODUCT_RIGHT_GATE`` (the single B87 gate, default
**ON** since flip-pack №6, KEY_SCHEMA 39). Explicit ``0``/``false``/``off``/
``no`` ⇒ the stage is a pure no-op (byte-identical; kill-switch forever).

THE DONOR GUARD (fixb109, probe P9 2026-08-05) — ``WYSTAN_TJR_DONOR_GUARD``,
default **OFF**. P9 proved this rail is the biggest single producer of the
``ws_anchor_no_uf`` ratchet class: 30 of 88 structural displacements leave the
DONOR with zero real journeys (23 unique PFs across 13 boards), while the
sibling law one family over — the 6.7d backstop arm-1 — has carried the
abstain since B13::

    if donor and donor in flowful and covered.get(donor, 0) <= 1:
        continue  # would uncover the donor — no violation trades

Two shipped laws thus contradict each other (the P7 "brand self-contradiction"
shape): 6.9965 carries a journey OUT of a ``ws:`` PF by law, and the
product-right ratchet blocks the board because that PF ends up journey-less.
Nothing re-covers a donor after this stage (last backstop = phase_finalize
:3080; this rail = :4302). The guard mirrors the sibling and adds the three
sub-defects P9 named:

* **M1** donor-uncovering abstain — never carry a LIVE structural donor's LAST
  REAL journey away. NARROW by construction (P9 risk 1): the donor must be
  flow-ful (it owns code that needs covering) and the moved row must be real;
  killed/laned homes keep the shipped behaviour (nothing to uncover).
* **D2** double-duty stop — ``_STRUCTURAL_STOPLIST`` does double duty: it makes
  a PF a legal DONOR *and* (via ``_MATCH_STOPWORDS``) strips that very token
  from the match, so a workspace package literally named ``import`` can never
  hold its own import journey. A journey whose ACTION token is the donor
  package's own name is home (the leading token of a journey name IS its
  action — the shipped ``journey-action-families`` mechanism).
* **D3** verb leakage — ``generate``/``connect`` were missing from
  ``_VERB_STOPWORDS``, so a VERB drove the move (supabase UF-099 → route echo
  ``generate-attachment-url``; midday UF-039 → ``inbox-accounts.connect``).
* **D6** synth-seed hold — the rail also displaced the backstop's OWN
  synthesized I8 seeds (midday UF-001), undoing the cover minted at :3080.
  Every PF is I8-covered when this stage starts, so holding a seed on a live
  home can never open a hole — only moving it can.
"""
from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover — typing only
    from wystan.models.types import Feature, UserFlow

PRODUCT_RIGHT_GATE_ENV = "WYSTAN_PRODUCT_RIGHT_GATE"
DONOR_GUARD_ENV = "WYSTAN_TJR_DONOR_GUARD"

#: Structural-container names that carry no product right of their own — a
#: journey homed here is mis-homed (the entity's own PF is the real home).
#: Corroboration vocabulary only (the mechanism is the anchor shape); kept
#: minimal and scale-free.
_STRUCTURAL_STOPLIST = frozenset({
    "settings", "sidebar", "common", "api", "import", "export", "core",
    "app", "misc", "utils", "shared", "main", "config", "src", "index",
    "lib", "helpers", "components", "hooks", "types", "constants",
})

#: Token stopwords — journey verbs + articles carry no entity signal.
_VERB_STOPWORDS = frozenset({
    "view", "manage", "create", "edit", "update", "delete", "list",
    "browse", "run", "import", "export", "and", "the", "a", "an", "or",
    "your", "of", "for", "to", "in", "on", "new", "add", "remove",
    "authorize", "exchange", "from", "with", "settings", "setting",
})

#: Match-token stopwords = verbs ∪ STRUCTURAL/generic terms. A journey must
#: re-home on its ENTITY tokens (banking, inbox, transaction, oauth,
#: notification), never on structural/layout/marketplace noise (sidebar,
#: app, store, common, api) — those produced spurious moves in
#: measurement ('View chat Conversation' → 'upgrade' on 'sidebar';
#: 'View app store' → 'cal' on 'app'/'store').
_MATCH_STOPWORDS = _VERB_STOPWORDS | _STRUCTURAL_STOPLIST | frozenset({
    "store", "marketplace",
})

#: D3 (fixb109) — verbs that leaked into the ENTITY match and drove a move.
#: ``generate`` is corroborated data-side: it is already a canonical action
#: verb in the shipped ``journey-action-families.yaml`` (create family), i.e.
#: the engine ALREADY rules it an action, not an entity. ``connect`` is the
#: midday UF-039 exhibit. Guard-gated, so the default world is untouched.
_D3_VERB_STOPWORDS = frozenset({"generate", "connect"})

_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_SPLIT_RE = re.compile(r"[^A-Za-z0-9]+")


def product_right_gate_enabled() -> bool:
    """The single B87 gate — default **ON** since the 2026-07-23 flip-pack №6
    flip (KEY_SCHEMA 39; see the stage_6_86 twin helper). Unset ≡ explicit
    ``"1"``; explicit ``0``/``false``/``off``/``no`` is the kill-switch
    forever. The pre-flip truthy set is preserved LITERALLY — only the
    ``os.environ.get`` default moved ``"0"`` -> ``"1"``."""
    return os.environ.get(PRODUCT_RIGHT_GATE_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def donor_guard_enabled() -> bool:
    """fixb109 donor guard (M1 + D2 + D3 + D6) — default **OFF** (armed).
    Unset ≡ ``"0"``; the truthy set mirrors the B87 gate helper literally, so
    the flip commit only moves the ``os.environ.get`` default."""
    return os.environ.get(DONOR_GUARD_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _singular(tok: str) -> str:
    if tok.endswith("ies") and len(tok) > 4:
        return tok[:-3] + "y"
    if tok.endswith("ses") and len(tok) > 4:
        return tok[:-2]
    if tok.endswith("s") and not tok.endswith("ss") and len(tok) > 3:
        return tok[:-1]
    return tok


def _qualifier_stops(pf: Any) -> frozenset[str]:
    """Display tokens the fixb133 M2 rung injected into this PF — excluded
    from its display-derived token set. Empty (⇒ byte-identical) when the
    rung is off or the PF was never dressed."""
    from wystan.pipeline_v2.pf_display_doctrine import (
        display_qualifier_stops,
    )

    return display_qualifier_stops(pf)


def _tokens(*parts: str | None,
            extra_stops: frozenset[str] = frozenset()) -> frozenset[str]:
    """Entity tokens. ``extra_stops`` is the D3 rider — empty (and therefore
    byte-identical to the shipped behaviour) unless the donor guard is on."""
    out: set[str] = set()
    stops = _MATCH_STOPWORDS | extra_stops if extra_stops else _MATCH_STOPWORDS
    for part in parts:
        if not part:
            continue
        spaced = _CAMEL_RE.sub(" ", str(part))
        for w in _SPLIT_RE.split(spaced):
            wl = w.lower()
            if len(wl) >= 2 and wl not in stops:
                out.add(_singular(wl))
    return frozenset(out)


def _raw_tokens(*parts: str | None) -> tuple[str, ...]:
    """Ordered tokens with NO stopword drop — D2's instrument. The stoplist is
    exactly what hides a donor package's own name from the match, so the
    double-duty test has to look at the unfiltered stream."""
    out: list[str] = []
    for part in parts:
        if not part:
            continue
        spaced = _CAMEL_RE.sub(" ", str(part))
        for w in _SPLIT_RE.split(spaced):
            wl = w.lower()
            if wl:
                out.append(_singular(wl))
    return tuple(out)


def _is_double_duty_home(uf: "UserFlow", donor: str) -> bool:
    """D2 — the journey's ACTION token IS the donor package's own name.

    ``import``-the-package holding the ``Import from HTML or DOCX`` journey is
    not a masquerader: it is the journey's home, and only the stoplist's double
    duty hides that. Uses the LEADING token of the journey name — the shipped
    ``journey-action-families`` mechanism ("the leading token of a generated
    flow name IS its action"), which is what keeps this narrow: a trailing
    noun (``Manage inbox and developer settings`` on a ``settings`` donor) is
    NOT a self-match and still moves."""
    lead = _raw_tokens(getattr(uf, "name", None))
    if not lead:
        return False
    return lead[0] in set(_raw_tokens(donor))


def _is_container_anchor(pf: "Feature | None") -> bool:
    """fixb109 — the donor guard's NARROWING conjunct: a structural container
    by ANCHOR (``ws:``/``dev:``), i.e. a workspace package / dev grain that
    owns code. This is deliberately stricter than ``_is_structural_home``,
    which also admits a stoplist NAME on any anchor: a ``route:``-anchored PF
    that merely happens to be called ``settings`` is a real route surface, and
    the shipped anti-case ('Manage inbox settings' on a
    ``route:app/inbox/settings`` home moves to ``inbox``) must keep working
    with the guard armed. It is also exactly the shape of the ratchet classes
    this guard exists to clear (``ws_anchor_no_uf`` / ``dev_anchor_no_uf``)."""
    anchor = str(getattr(pf, "anchor_id", None) or "")
    return anchor.startswith(("dev:", "ws:"))


def _is_structural_home(pf: "Feature") -> bool:
    """A PF that carries no product right of its own — a structural
    container (``dev:``/``ws:`` anchor), a stoplist name, or a ≤2-char
    name. Such a home is a valid RE-HOME SOURCE and never a target."""
    anchor = (getattr(pf, "anchor_id", None) or "")
    if anchor.startswith(("dev:", "ws:")):
        return True
    name = (getattr(pf, "name", None) or "").lower()
    if name in _STRUCTURAL_STOPLIST:
        return True
    return len(name.replace("-", "")) <= 2


def run_token_journey_rehome(
    product_features: list["Feature"],
    user_flows: list["UserFlow"],
    developer_features: list["Feature"] | None = None,
) -> dict[str, Any]:
    """Re-home mis-homed journeys by resource/name token match. Mutates
    ``UserFlow.product_feature_id`` (+ ``lane_ref``/``residual``) in place;
    returns telemetry with the displacement + fallback tables.

    ``developer_features`` feeds the donor guard's flow-ful test (the sibling's
    ``pf_flows`` construction: dev stamp → PF slug → owned flows). ``None``
    keeps the pre-fixb109 call contract; the guard then cannot fire."""
    tele: dict[str, Any] = {
        "enabled": True, "applied": False,
        "candidates": 0, "rehomed": 0, "fallbacks": 0,
        "displacements": [], "fallbacks_table": [],
    }
    guard_on = donor_guard_enabled()
    # D3 rider — empty unless the guard is armed (OFF ⇒ byte-identical).
    _stops = _D3_VERB_STOPWORDS if guard_on else frozenset()
    # M1 — flow-ful donors only (mirror of the sibling's ``flowful`` set) and a
    # running REAL-journey census (mirror of its ``covered`` Counter). "Real" =
    # ``synthesized`` falsy: the ratchet class counts exactly those, and a
    # synthesized seed can never clear it (P9 §0.2).
    pf_flow_count: dict[str, int] = {}
    real_cover: dict[str, int] = {}
    if guard_on:
        for dev in developer_features or ():
            if getattr(dev, "layer", "developer") != "developer":
                continue
            pid = getattr(dev, "product_feature_id", None)
            if not pid:
                continue
            pf_flow_count[str(pid)] = (pf_flow_count.get(str(pid), 0)
                                       + len(getattr(dev, "flows", None) or []))
        for _uf in user_flows:
            if getattr(_uf, "synthesized", False):
                continue
            _pid = getattr(_uf, "product_feature_id", None)
            if _pid:
                real_cover[str(_pid)] = real_cover.get(str(_pid), 0) + 1
        tele["donor_guard"] = {
            "enabled": True, "abstained": 0, "abstentions": [],
            "flowful_donors": sum(1 for v in pf_flow_count.values() if v > 0),
        }
    pf_by_name: dict[str, "Feature"] = {}
    for pf in product_features:
        nm = getattr(pf, "name", None)
        if nm:
            pf_by_name[nm] = pf
    # Pre-computed target token index (real-domain PFs only).
    target_toks: list[tuple["Feature", frozenset[str]]] = []
    for pf in product_features:
        if _is_structural_home(pf):
            continue
        # fixb133 / warden §37 blocker 1 — a qualifier the M2 rung INJECTED
        # into the display ('board' in "Board Shares") is not evidence about
        # this PF's domain; letting it vote is self-fulfilling affinity
        # (measured: UF-046 dragged websites->cohorts by 'Website Cohorts').
        # Subtract it from the DISPLAY-derived half only; the name half and
        # every undressed PF are untouched, so the rung off ⇒ identical set.
        _q = _qualifier_stops(pf)
        toks = _tokens(getattr(pf, "name", None), extra_stops=_stops) | _tokens(
            getattr(pf, "display_name", None), extra_stops=_stops | _q)
        if toks:
            target_toks.append((pf, toks))

    for uf in user_flows:
        pfid = getattr(uf, "product_feature_id", None)
        home = pf_by_name.get(pfid) if pfid else None
        home_missing = pfid is not None and home is None
        home_laned = pfid is None
        home_struct = home is not None and _is_structural_home(home)
        if not (home_missing or home_laned or home_struct):
            continue  # healthy real-domain home — never touched
        uf_toks = _tokens(getattr(uf, "resource", None),
                          getattr(uf, "name", None), extra_stops=_stops)
        if not uf_toks:
            # nothing to match on; a killed/laned row stays honest residual
            if home_missing:
                _mark_residual(uf, tele, reason="no_tokens")
            continue
        tele["candidates"] += 1
        home_toks = _tokens(getattr(home, "name", None),
                           getattr(home, "display_name", None),
                           extra_stops=_stops) if home else frozenset()
        home_overlap = len(uf_toks & home_toks)
        best_pf: "Feature | None" = None
        best_overlap = 0
        for pf, toks in target_toks:
            if pf is home:
                continue
            ov = len(uf_toks & toks)
            if ov > best_overlap or (
                    ov == best_overlap and ov > 0 and best_pf is not None
                    and getattr(pf, "name", "") < getattr(best_pf, "name", "")):
                best_overlap, best_pf = ov, pf
        # decision: killed/laned re-homes on any token match; a live
        # structural container re-homes only when the real target ties or
        # beats it (move away from the container to the entity).
        move = False
        if best_pf is not None and best_overlap >= 1:
            if home_missing or home_laned:
                move = True
            elif home_struct and best_overlap >= max(1, home_overlap):
                move = True
        # ── fixb109 donor guard (armed only) ───────────────────────────
        # Runs AFTER the shipped decision so the OFF path is untouched: the
        # guard can only ever turn a move into a stay, never the reverse.
        if guard_on and move and best_pf is not None:
            reason = _guard_abstain_reason(
                uf, home, pfid, home_struct,
                pf_flow_count=pf_flow_count, real_cover=real_cover,
            )
            if reason is not None:
                _g = tele["donor_guard"]
                _g["abstained"] += 1
                _g["abstentions"].append({
                    "uf_id": getattr(uf, "id", None),
                    "uf_name": getattr(uf, "name", None),
                    "resource": getattr(uf, "resource", None),
                    "donor": pfid,
                    "would_have_gone_to": getattr(best_pf, "name", None),
                    "overlap": best_overlap,
                    "synthesized": bool(getattr(uf, "synthesized", False)),
                    "reason": reason,
                })
                continue  # journey stays home — donor keeps its cover
        if move and best_pf is not None:
            if guard_on and not getattr(uf, "synthesized", False):
                # keep the running REAL census honest for later donors
                # (mirror of the sibling's ``covered[donor] -= 1``)
                if pfid:
                    real_cover[str(pfid)] = max(
                        0, real_cover.get(str(pfid), 0) - 1)
                _to = getattr(best_pf, "name", None)
                if _to:
                    real_cover[str(_to)] = real_cover.get(str(_to), 0) + 1
            tele["displacements"].append({
                "uf_id": getattr(uf, "id", None),
                "uf_name": getattr(uf, "name", None),
                "resource": getattr(uf, "resource", None),
                "from": pfid,
                "from_state": ("killed" if home_missing else
                               "laned" if home_laned else "structural"),
                "to": getattr(best_pf, "name", None),
                "tokens": sorted(uf_toks & _tokens(
                    getattr(best_pf, "name", None),
                    getattr(best_pf, "display_name", None))),
                "overlap": best_overlap,
            })
            uf.product_feature_id = getattr(best_pf, "name", None)
            if getattr(uf, "lane_ref", None) is not None:
                uf.lane_ref = None
            if getattr(uf, "residual", False):
                uf.residual = False
            tele["rehomed"] += 1
        elif home_missing:
            # a KILLED home with no token target → honest residual. A
            # laned row with no target stays honestly laned (already labeled
            # debt); a healthy-but-structural home stays put (no invention).
            _mark_residual(uf, tele, reason="no_token_target")

    tele["applied"] = tele["rehomed"] > 0 or tele["fallbacks"] > 0
    return tele


def _guard_abstain_reason(
    uf: "UserFlow",
    home: "Feature | None",
    pfid: str | None,
    home_struct: bool,
    *,
    pf_flow_count: dict[str, int],
    real_cover: dict[str, int],
) -> str | None:
    """The donor guard's verdict for ONE would-be move: a reason string to
    abstain, or ``None`` to let the shipped law stand.

    Deliberately silent on killed (``home_missing``) and laned homes: there is
    no donor to uncover, so those rows keep the shipped behaviour exactly."""
    # NARROW by anchor (P9 risk 1): only a ws:/dev: container donor is in
    # scope. Killed / laned / route-anchored homes keep the shipped law
    # EXACTLY — there is no donor to uncover in the first two, and the third
    # is a real surface the rail is right to move a journey off.
    if not home_struct or home is None or not pfid:
        return None
    if not _is_container_anchor(home):
        return None
    synth = bool(getattr(uf, "synthesized", False))
    # D6 — a backstop's own I8 seed never travels off a LIVE container home.
    # Every PF is covered when this stage starts (last backstop :3080), so
    # holding a seed cannot open a hole; moving it demonstrably does
    # (midday UF-001 app-store → notification-settings).
    if synth:
        return "synth_seed_hold"
    donor = str(pfid)
    # D2 — the donor package's own name IS this journey's action.
    if _is_double_duty_home(uf, donor):
        return "donor_name_is_journey_action"
    # M1 — never carry a flow-ful donor's LAST REAL journey away.
    if pf_flow_count.get(donor, 0) > 0 and real_cover.get(donor, 0) <= 1:
        return "donor_last_real_journey"
    return None


def _mark_residual(uf: "UserFlow", tele: dict[str, Any], reason: str) -> None:
    """Honest fallback — a killed/laned journey with no token target keeps
    its residual state (no invented home). Never drops the row."""
    uf.product_feature_id = None
    uf.residual = True
    tele["fallbacks"] += 1
    tele["fallbacks_table"].append({
        "uf_id": getattr(uf, "id", None),
        "uf_name": getattr(uf, "name", None),
        "resource": getattr(uf, "resource", None),
        "reason": reason,
    })
