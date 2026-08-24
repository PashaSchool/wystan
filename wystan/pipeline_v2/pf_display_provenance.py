"""Seg A — PF display route-grammar (L-A1) + name-provenance ladder (L-A2)
(B71, ``WYSTAN_NAMING_PACK``, default OFF).

Census classes A (43 raw dir-token PF) + B (57 generic-leaf PF): a PF display is
minted as ``titlecase(basename(dir))`` with no natural-name evidence, so router
grammar (``$token``, ``[...]+``, ``.$``, glued lowercase) and source typos pass
straight through (documenso ``[-htmltopdf]+`` / ``p.$url`` / ``team.verify.email
.$token``; cal ``Btcpayserver`` / ``App Store — Insihts``).

Two dictionary-free laws over the FINAL PF display (DISPLAY CHANNEL ONLY —
``display_name`` + a ``name_provenance`` telemetry tier; identity / membership /
paths untouched):

* **L-A1 route-grammar** — a display carrying router-template glyphs is not a
  name. Its machinery is removed structurally (per the path's own dialect,
  reusing naming_contract's route helpers), leaving the static/human tokens.
* **L-A2 provenance ladder** — a display is graded by where its name came from:
  ``nav label > package manifest > schema domain > static route segment > dir
  basename``. A DEFECTIVE display (route residue, or a bare dir-basename) is
  UPGRADED to the highest available higher-provenance source; a display that is
  already nav/manifest-confirmed is high-provenance and left alone. A bare
  basename with NO higher source is honest debt (kept, tier recorded) — the law
  never BANS a word, so legitimate short/generic names survive on provenance.

Anti-cases (census §4) survive by construction: hoppscotch ``CLI`` / ``Relay``,
novu ``Framework`` / ``Provider`` / ``Preferences``, plane ``API Tokens`` /
``Spaces``, cal ``Settings`` / ``Auth`` / ``Insights`` carry no route glyphs and
are nav/manifest-confirmed (high tier) — untouched. plane ``Propel`` is an exact
name (its defect is a LANE, Seg B L-B2) — not renamed here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from wystan.pipeline_v2.naming_contract import (
    _PARAM_GLYPHS,
    _has_route_template_residue,
    _param_noun,
    _peel_edge_single_letters,
    load_naming_vocab,
    polish_display_casing,
)

__all__ = [
    "ProvenanceSources",
    "ProvenanceVerdict",
    "clean_route_grammar_display",
    "resolve_pf_display",
    "apply_pf_display_provenance",
]

#: Provenance tiers, highest -> lowest (the L-A2 ladder).
#: fixb133 M2 inserts ``static-route-qualified`` between the schema domain
#: and the bare static route: the anchor's OWN parent/route-group evidence
#: outranks the bare terminal segment but never outranks authored
#: vocabulary (nav / package manifest / schema domain).
PROVENANCE_TIERS = ("nav", "package-manifest", "schema-domain",
                    "static-route-qualified", "static-route", "dir-basename")

#: fixb133 M2's own tier — the only one gated by a flag, so the telemetry
#: shape stays byte-identical while the rung is off.
QUALIFIED_TIER = "static-route-qualified"

#: Tiers derived from the ROUTE (not from authored vocabulary). The M3
#: lexicon only ever dresses these — an authored nav/manifest/schema label
#: is the author's own word and is never rewritten (NS-D law).
_ROUTE_DERIVED_TIERS = frozenset({QUALIFIED_TIER, "static-route", "dir-basename"})

_TRAILING_PLUS = re.compile(r"\+(?=\s|$)")
_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class ProvenanceSources:
    """The higher-provenance name candidates for one PF (any may be empty)."""

    nav: str = ""
    manifest: str = ""
    schema: str = ""
    route: str = ""
    basename: str = ""
    #: fixb133 M2 — the ``static-route-qualified`` candidate: the anchor's
    #: base with its OWN parent-resource / route-group-category evidence
    #: composed on ("Board Shares", "Performance Report"). Empty when the
    #: rung flag is off or the anchor supplies no evidence (honesty floor).
    route_qualified: str = ""
    #: The WORD that candidate injected ('Board' / 'Website' / 'Report').
    #: Recorded onto the PF when the rung wins so the attribution consumers
    #: can subtract it — an engine-written qualifier is not evidence about
    #: the PF's domain (warden §37 blocker 1).
    route_qualifier_word: str = ""
    #: Anchor-kind prefix of the PF's canonical anchor id ("route" / "ws" /
    #: "fdir" / "hub" / ""). Horizon-1 ruling (2026-07-16): the trailing-'+'
    #: residue rung arms ONLY for route: anchors — on ws:/fdir:/hub: anchors
    #: '+' is a legitimate name character ('Enterprise+' lives). Empty
    #: (unknown shape) errs to preservation, matching the older humanize
    #: law's route:-scoping.
    anchor_source: str = ""


@dataclass(frozen=True)
class ProvenanceVerdict:
    display: str
    provenance: str          # the tier the final display came from
    changed: bool


def _norm(text: str) -> str:
    return _WS.sub(" ", (text or "").strip()).lower()


def clean_route_grammar_display(text: str, vocab: Any | None = None) -> str:
    """L-A1: strip router-template machinery from a display STRING structurally.

    ``[-htmltopdf]+`` -> ``Htmltopdf``; ``p.$url`` -> ``URL``;
    ``team.verify.email.$token`` -> ``Team Verify Email``. Dot = URL separator
    (Remix), ``$x`` / bracket params resolve to their noun (opaque ids drop),
    edge single letters peel, then casing polish. No dictionaries.

    fixb133 M1 (default OFF): the router MARKER classes are pre-stripped
    first, because the dot-splitting walk below cannot read them —
    ``(.)sessions`` splits into ``(`` + ``)sessions`` and emits
    "( )sessions". Flag unset/``0`` ⇒ the legacy walk runs alone."""
    v = vocab or load_naming_vocab()
    raw = (text or "").strip()
    if not raw:
        return raw
    from wystan.pipeline_v2.naming_contract import (
        route_marker_display_sanitize_enabled,
    )

    if route_marker_display_sanitize_enabled():
        from wystan.pipeline_v2.extractors._route_markers import (
            sanitize_display_text,
        )

        raw = sanitize_display_text(raw) or raw
    # Split on the Remix dot separator so ``a.b.$c`` reads as three tokens.
    words: list[str] = []
    for seg in re.split(r"[.\s]+", raw):
        s = seg.strip()
        if not s:
            continue
        s = _TRAILING_PLUS.sub("", s)          # flat-route nesting marker
        s = s.strip("+")
        if s.startswith("[") and s.endswith("]"):
            s = s[1:-1].strip("._-")           # escaped literal -> unwrap
        if not s:
            continue
        if s[0] in "$:{<*":                    # dynamic param -> its noun (or drop)
            noun = _param_noun(s, v)
            if noun:
                words.append(noun)
            continue
        if s.startswith("_"):                  # layout/pathless prefix
            continue
        s = _PARAM_GLYPHS.sub("", s).strip("-_")
        if s:
            words.append(s)
    joined = _peel_edge_single_letters(" ".join(words)) or ""
    # Titlecase all-lowercase tokens (the mint titlecased the basename); polish
    # then restores known acronyms/brands over the titlecased form.
    titled = " ".join(
        (w[:1].upper() + w[1:]) if (w and w[0].islower()) else w
        for w in joined.split()
    )
    return polish_display_casing(titled.strip(), v)


def _tier_of(display: str, src: ProvenanceSources) -> str:
    """The provenance tier a (clean) display already matches, highest first."""
    n = _norm(display)
    if src.nav and _norm(src.nav) == n:
        return "nav"
    if src.manifest and _norm(src.manifest) == n:
        return "package-manifest"
    if src.schema and _norm(src.schema) == n:
        return "schema-domain"
    if src.route_qualified and _norm(src.route_qualified) == n:
        return QUALIFIED_TIER
    if src.route and _norm(src.route) == n:
        return "static-route"
    return "dir-basename"


def _doctrine_filters(display: str, tier: str, vocab: Any) -> str:
    """fixb133 M1 + M2 + M3 — the FILTERS that run over whatever rung won.

    M1 (``WYSTAN_ROUTE_MARKER_DISPLAY_SANITIZE``): a marker that
    survived every rung is scrubbed structurally, then re-polished.
    M2 (``WYSTAN_PF_ROUTE_QUALIFIER_RUNG``, the N7 stutter arm): a
    display that ALREADY ARRIVED stuttering is deduped here. This is the
    arm that reaches the live cal.com class: 'Alby (alby)' /
    'PayPal (PayPal)' are baked at MINT
    (``stage_6_86_anchored_mint`` collision-qualifier, whose qualifier
    equalled the base), so no naming-contract rung ever re-derives them —
    the ladder grades such a display neither residue nor bare and returns
    it untouched. Dropping the degenerate qualifier at
    ``humanize_anchor_display`` therefore cannot see it; only a filter
    over the FINAL display can. DISPLAY channel only — ``pf.name`` keeps
    its minted ``alby-(alby)`` slug (that garbage belongs to the queued
    name-migration lane, not this cycle).
    M3 (``WYSTAN_PF_DISPLAY_LEXICON``): a whole-base abbreviation /
    deictic is spelled out — route-derived tiers ONLY, so an authored
    label keeps the author's word — and any surviving initialism renders
    uppercase. All flags off ⇒ the display is returned untouched.
    """
    from wystan.pipeline_v2.naming_contract import (
        pf_display_lexicon_enabled,
        pf_route_qualifier_rung_enabled,
        route_marker_display_sanitize_enabled,
    )

    out = (display or "").strip()
    if not out:
        return out
    if pf_route_qualifier_rung_enabled():
        from wystan.pipeline_v2.pf_display_doctrine import dedupe_stutter

        out = dedupe_stutter(out) or out
    if route_marker_display_sanitize_enabled():
        from wystan.pipeline_v2.extractors._route_markers import (
            sanitize_display_text,
        )

        scrubbed = sanitize_display_text(out)
        # Re-polish ONLY when the scrub actually removed machinery: a
        # display the filter did not touch must not gain a casing pass it
        # never had (blast radius stays exactly the marker class).
        if scrubbed and scrubbed != out:
            out = polish_display_casing(scrubbed, vocab)
    if pf_display_lexicon_enabled():
        from wystan.pipeline_v2.pf_display_doctrine import (
            apply_lexicon_display,
            uppercase_acronyms,
        )

        if tier in _ROUTE_DERIVED_TIERS:
            dressed, _rule = apply_lexicon_display(out)
            if dressed:
                out = dressed
        out = uppercase_acronyms(out)
    return out


def resolve_pf_display(
    current: str, src: ProvenanceSources, vocab: Any | None = None,
) -> ProvenanceVerdict:
    """L-A1 + L-A2 verdict for one PF display.

    A display is DEFECTIVE when it carries route residue OR equals the bare
    titlecased dir basename. A defective display is upgraded to the highest
    available higher-provenance source (that is itself residue-free); if none
    exists, its route grammar is cleaned in place (kept otherwise = honest
    debt). A non-defective display is high-provenance and preserved. The law
    never bans a word."""
    v = vocab or load_naming_vocab()
    cur = (current or "").strip()
    # Hub-composed displays ("App Store — Insihts") carry a HEAD + a leaf; the
    # defect lives in the leaf (a raw/typo'd basename), so grade at the leaf.
    head, sep, leaf = cur.rpartition(" — ")
    leaf = leaf.strip()
    # Horizon-1 ruling (2026-07-16): the trailing-'+' rung fires only when
    # this PF is route:-anchored (Remix syntax); non-route '+' is prose.
    is_route = src.anchor_source == "route"
    residue = _has_route_template_residue(cur, route_anchor=is_route)
    basename_disp = _norm(polish_display_casing(
        src.basename.replace("-", " ").replace("_", " "), v)) if src.basename else ""
    bare = bool(basename_disp) and _norm(leaf) == basename_disp

    def _verdict(display: str, tier: str) -> ProvenanceVerdict:
        """Final verdict — the fixb133 filters run over whatever rung won."""
        out = _doctrine_filters(display, tier, v) or display
        return ProvenanceVerdict(out, tier, changed=_norm(out) != _norm(cur))

    if not residue and not bare:
        return _verdict(cur, _tier_of(cur, src))

    def _recompose(name: str) -> str:
        clean = polish_display_casing(name.strip(), v)
        return f"{head}{sep}{clean}" if sep else clean

    for tier, name in (
        ("nav", src.nav), ("package-manifest", src.manifest),
        ("schema-domain", src.schema),
        (QUALIFIED_TIER, src.route_qualified),
        ("static-route", src.route),
    ):
        # Same anchor-kind scoping: a non-route PF's upgrade candidate may
        # legitimately carry '+' (a manifest name like 'Enterprise+').
        if name and not _has_route_template_residue(name, route_anchor=is_route):
            chosen = _recompose(name)
            if chosen.strip():
                return _verdict(chosen, tier)

    cleaned = _recompose(clean_route_grammar_display(leaf, v)) if residue else cur
    return _verdict(cleaned, "dir-basename")


def apply_pf_display_provenance(
    product_features: list[Any],
    sources_for: Any,
    vocab: Any | None = None,
) -> dict[str, Any]:
    """Apply the Seg A laws in place over ``product_features``. ``sources_for`` is
    a callable ``pf -> ProvenanceSources``. Mutates ``display_name`` only (falls
    back to ``name`` when a PF has no ``display_name``). Records the provenance
    tier per PF + rename/tier counts. Only ever called behind
    ``naming_pack_enabled`` — OFF path never runs, so output is byte-identical."""
    from wystan.pipeline_v2.naming_contract import (
        pf_route_qualifier_rung_enabled,
    )

    v = vocab or load_naming_vocab()
    # The M2 tier is listed ONLY while its flag is armed, so the telemetry
    # dict stays byte-identical to pre-fixb133 on the OFF path.
    _tiers = tuple(
        t for t in PROVENANCE_TIERS
        if t != QUALIFIED_TIER or pf_route_qualifier_rung_enabled()
    )
    tele: dict[str, Any] = {
        "pf_route_grammar_cleaned": 0,
        "pf_provenance_upgraded": 0,
        "by_tier": {t: 0 for t in _tiers},
        "name_provenance": {},
    }
    for pf in product_features:
        cur = getattr(pf, "display_name", None) or getattr(pf, "name", "") or ""
        if not cur:
            continue
        src = sources_for(pf)
        verdict = resolve_pf_display(cur, src, v)
        tele["by_tier"][verdict.provenance] = tele["by_tier"].get(verdict.provenance, 0) + 1
        key = str(getattr(pf, "name", None) or getattr(pf, "id", None) or cur)
        tele["name_provenance"][key] = verdict.provenance
        # Record the injected qualifier tokens whenever the M2 rung is the
        # tier that won. INTERNAL channel (Field(exclude=True)) — never
        # serialized; empty/absent on every other tier and with the rung
        # off, so every consumer stays byte-identical.
        if verdict.provenance == QUALIFIED_TIER and src.route_qualifier_word:
            from wystan.pipeline_v2.pf_display_doctrine import (
                qualifier_tokens,
            )

            toks = qualifier_tokens(src.route_qualifier_word)
            if toks and hasattr(pf, "display_qualifier_tokens"):
                pf.display_qualifier_tokens = toks
                tele["pf_qualifier_tokens_recorded"] = (
                    tele.get("pf_qualifier_tokens_recorded", 0) + 1)
        if verdict.changed and verdict.display and _norm(verdict.display) != _norm(cur):
            # Telemetry split mirrors the verdict's anchor-kind scoping.
            if _has_route_template_residue(
                cur, route_anchor=src.anchor_source == "route",
            ) and verdict.provenance == "dir-basename":
                tele["pf_route_grammar_cleaned"] += 1
            else:
                tele["pf_provenance_upgraded"] += 1
            if hasattr(pf, "display_name"):
                pf.display_name = verdict.display
            elif hasattr(pf, "name"):
                pf.name = verdict.display
    return tele
