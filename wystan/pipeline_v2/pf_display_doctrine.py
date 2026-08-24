"""fixb133 — PF display-name doctrine (M2 qualifier rung · M3 lexicon · N7
stutter dedupe).

The PF naming doctrine (``pf-naming-doctrine.md``) rules what a product
feature is CALLED. Three defect classes had no mechanism at all:

* **N2 context-stripped segment** — ``shares`` under ``boards/[boardId]``
  loses its meaning the moment the anchor is hidden; **N4 dev-vocabulary
  collision** — ``performance`` under ``(reports)`` reads as a profiler.
  Cure: the M2 ``static-route-qualified`` rung, which composes the
  anchor's OWN evidence (parent resource / route-group category) onto the
  base — never a dictionary, never an invention.
* **N3 opaque abbreviation** / **N6 deictic** — ``sso``, ``utm``, ``me``.
  Cure: the M3 lexicon, a corroborative UNIVERSAL spelling table applied
  only when the WHOLE cleaned base equals a key.
* **N7 stutter** — ``App Store — App Store — Attio``. Cure: one dedupe
  helper used at every compose site this pack touches.

Honesty floor (doctrine law 7): every rule here DRESSES existing evidence.
When the anchor supplies no qualifier the clean Title-Cased base stands —
"Boards" beats an invented "Analytics Board Management". Authored
vocabulary is sacred: the M2 rung sits BELOW nav / package-manifest /
schema-domain in the B71 ladder and only ever runs on a display the
ladder already graded defective (route residue or bare dir basename).

Display channel ONLY. Nothing here writes ``pf.name`` / slugs / identity /
membership.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from wystan.pipeline_v2.data import load_yaml
from wystan.pipeline_v2.extractors._route_markers import (
    has_marker_residue,
    is_dynamic_segment,
    is_junk_route_group,
    is_parallel_slot,
    is_private_folder,
    is_route_group,
    route_group_inner,
)

__all__ = [
    "acronym_tokens",
    "apply_lexicon_display",
    "dedupe_stutter",
    "dev_vocab",
    "display_qualifier_stops",
    "collision_qualifier_no_self",
    "polish_qualifier_word",
    "distinguishing_ancestor",
    "is_category_group",
    "is_lexicon_base",
    "lexicon_key",
    "load_display_lexicon",
    "plural_only_nouns",
    "qualifier_tokens",
    "route_qualified_display",
    "same_phrase",
    "strip_qualifier_tokens",
    "uppercase_acronyms",
]

_LEXICON_FILE = "display-lexicon.yaml"
_lexicon_cache: dict[str, Any] | None = None

_KEY_SPLIT = re.compile(r"[^a-z0-9]+")
_WORD_RE = re.compile(r"[A-Za-z0-9]+")
_HUB_SEP = " — "

#: ``<Base> (<Qualifier>)`` — the parenthetical compose form the engine's
#: candidate builder / uniqueness fallback emit.
_PAREN_TAIL_RE = re.compile(r"^(?P<base>.+?)\s*\((?P<qual>[^()]+)\)\s*$")

#: Bare code-location words — never a useful DISAMBIGUATOR for a human
#: ('Alby (Src)' distinguishes nothing). Universal layout conventions.
_CODE_LOCATION_WORDS = frozenset({
    "src", "app", "apps", "packages", "pages", "routes", "lib", "libs",
    "web", "www", "server", "backend", "frontend", "index", "modules",
    "components", "crates", "internal", "core",
})


def load_display_lexicon() -> dict[str, Any]:
    """The packaged universal display lexicon (cached — pure data)."""
    global _lexicon_cache
    if _lexicon_cache is None:
        _lexicon_cache = load_yaml(_LEXICON_FILE)
    return _lexicon_cache


def lexicon_key(text: str) -> str:
    """Fold a display/segment to its lookup key (``API Key`` -> ``api-key``,
    ``Two Factor`` -> ``two-factor``)."""
    toks = [t for t in _KEY_SPLIT.split((text or "").lower()) if t]
    return "-".join(toks)


def _expansions() -> dict[str, str]:
    """The shipped expansion table, plus the ARMED rows when fixb146's flag
    is truthy.

    Kept as a per-call merge (never cached) so the flag stays a live
    kill-switch: unset/``0`` returns exactly the ``expansions:`` block, so
    every consumer — M3's ``apply_lexicon_display`` and the
    flag-independent ``is_lexicon_base`` that M2 abstains on — sees the
    pre-fixb146 table byte for byte."""
    lex = load_display_lexicon()
    raw = dict(lex.get("expansions") or {})
    from wystan.pipeline_v2.naming_contract import pf_lexicon_armed_enabled

    if pf_lexicon_armed_enabled():
        raw.update(lex.get("armed_expansions") or {})
    return {lexicon_key(str(k)): str(v) for k, v in raw.items() if k and v}


def _deictics() -> dict[str, str]:
    raw = load_display_lexicon().get("deictics") or {}
    return {lexicon_key(str(k)): str(v) for k, v in raw.items() if k and v}


def dev_vocab() -> frozenset[str]:
    """Bases that read as an engineering concern until qualified (M2
    trigger c). A LIST in the lexicon file, never a hardcoded set."""
    return frozenset(
        lexicon_key(str(w))
        for w in (load_display_lexicon().get("dev_vocab") or [])
        if str(w).strip()
    )


def plural_only_nouns() -> frozenset[str]:
    """English nouns with NO product-readable singular ('settings',
    'analytics', 'news'). Kept verbatim when used as a qualifier — naive
    ``-s`` stripping there is what produced "Setting Profile"."""
    return frozenset(
        lexicon_key(str(w))
        for w in (load_display_lexicon().get("plural_only") or [])
        if str(w).strip()
    )


def acronym_tokens() -> frozenset[str]:
    """Initialism tokens that render UPPERCASE inside a phrase (M3.3)."""
    return frozenset(
        str(w).strip().lower()
        for w in (load_display_lexicon().get("acronyms") or [])
        if str(w).strip()
    )


def is_lexicon_base(text: str) -> bool:
    """True when the WHOLE base is a lexicon key — expansion or deictic.

    The M2 rung abstains on these: the lexicon already owns the phrase
    ("Single Sign-On" needs no parent resource glued to it), and this test
    is flag-INDEPENDENT so M2's behaviour does not change with M3's state.
    """
    k = lexicon_key(text)
    if not k:
        return False
    return k in _expansions() or k in _deictics()


# ── M3: lexicon application (display channel, whole-segment only) ───────────


def apply_lexicon_display(display: str) -> tuple[str, str]:
    """``(display, rule)`` — expand a whole-base abbreviation / deictic.

    ``rule`` is ``"expansion"`` / ``"deictic"`` / ``""`` (untouched). The
    whole-segment law is why ``API Key`` survives: its key is ``api-key``,
    not ``api``. A composed display (carrying the hub ``" — "`` joint or a
    paren tail) is never a bare base and is left alone.
    """
    cur = (display or "").strip()
    if not cur or _HUB_SEP in cur or "(" in cur:
        return cur, ""
    key = lexicon_key(cur)
    if not key:
        return cur, ""
    exp = _expansions().get(key)
    if exp:
        return exp, "expansion"
    dei = _deictics().get(key)
    if dei:
        return dei, "deictic"
    return cur, ""


def uppercase_acronyms(display: str) -> str:
    """M3.3 — an initialism that SURVIVES inside a phrase renders uppercase.

    Kills the ``SSO`` vs ``Utm`` casing split without touching the shared
    ``known_acronyms`` casing table (which would change output with every
    flag off). Word-wise, exact token match only.
    """
    cur = display or ""
    if not cur:
        return cur
    acros = acronym_tokens()
    if not acros:
        return cur

    def _sub(m: "re.Match[str]") -> str:
        w = m.group(0)
        return w.upper() if w.lower() in acros else w

    return _WORD_RE.sub(_sub, cur)


# ── N7: stutter dedupe (one helper, every compose site) ────────────────────


def _join_fold(text: str) -> str:
    """Formatting-insensitive fold: lowercase, every non-alnum dropped.

    'PayPal' / 'Pay Pal' / 'pay-pal' all fold to ``paypal`` — the
    comparison the self-qualification defect needs (cal.com app-store dirs
    nest a same-name segment, so base and qualifier are the SAME word
    wearing two spellings)."""
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def same_phrase(a: str, b: str) -> bool:
    """THE shared dedupe predicate — case- and formatting-insensitive
    equality. One predicate for both compose forms (the ``—`` chain and
    the ``Base (Qualifier)`` parenthetical)."""
    fa, fb = _join_fold(a), _join_fold(b)
    return bool(fa) and fa == fb


def _fold(word: str) -> str:
    from wystan.pipeline_v2.naming_validator import _singular

    return _singular(_join_fold(word))


def dedupe_stutter(display: str) -> str:
    """Collapse a repeated qualifier in a composed display.

    Three shapes, all measured on live boards:

    * hub-joint repetition — ``App Store — App Store — Attio`` ->
      ``App Store — Attio`` (a composer read an ALREADY composed display
      as its vendor word);
    * **self-qualification in the paren form** — ``Alby (alby)`` ->
      ``Alby``, ``PayPal (PayPal)`` -> ``PayPal``, ``Pay Pal (PayPal)``
      -> ``Pay Pal`` (cal.com app-store dirs nest a same-name segment, so
      the anchor yields base == qualifier modulo case/formatting). A
      qualifier that restates its base carries ZERO information;
      ``Edit (Admin)`` — a qualifier that genuinely differs — is kept.
    * adjacent word repetition — ``Board Boards`` -> ``Boards``,
      ``Session Sessions`` -> ``Sessions`` (singular/plural folded, so the
      inflected echo is caught too).

    Case- and formatting-insensitive via :func:`same_phrase`; the FIRST
    spelling of a duplicated part wins so the result stays deterministic.
    """
    cur = (display or "").strip()
    if not cur:
        return cur
    m = _PAREN_TAIL_RE.match(cur)
    if m and same_phrase(m.group("base"), m.group("qual")):
        cur = m.group("base").strip()
    parts: list[str] = []
    seen_parts: set[str] = set()
    for part in cur.split(_HUB_SEP):
        p = part.strip()
        if not p:
            continue
        k = p.lower()
        if k in seen_parts:
            continue
        seen_parts.add(k)
        parts.append(p)
    out_parts: list[str] = []
    for p in parts:
        words = p.split()
        kept: list[str] = []
        for w in words:
            if kept and _fold(kept[-1]) and _fold(kept[-1]) == _fold(w):
                # Adjacent echo — keep the LONGER spelling (the plural the
                # author wrote) so 'Board Boards' reads 'Boards'.
                if len(w) > len(kept[-1]):
                    kept[-1] = w
                continue
            kept.append(w)
        out_parts.append(" ".join(kept))
    return _HUB_SEP.join(out_parts)


# ── M2: the static-route-qualified rung ────────────────────────────────────


def _singular_word(word: str) -> str:
    """Singularize a display word, preserving its casing shape.

    PLURAL-ONLY GUARD (live-fire defect, umami
    ``route:src/app/(main)/settings/profile``): a noun with no
    product-readable singular is returned verbatim — the naive ``-s``
    strip produced "Setting Profile" / would produce "New" from 'news'.
    The guard is a property of the NOUN, so it applies to both
    composition shapes (parent resource and route-group category).
    """
    from wystan.pipeline_v2.naming_validator import _singular

    w = (word or "").strip()
    if not w or w.isupper():
        return w
    if lexicon_key(w) in plural_only_nouns():
        return w
    sing = _singular(w.lower())
    if sing == w.lower():
        return w
    return sing[:1].upper() + sing[1:] if w[:1].isupper() else sing


def is_category_group(
    inner: str, is_transparent: Callable[[str], bool],
) -> bool:
    """True when a route group names an author CATEGORY that may legally
    decorate a display (warden №37 blocker 2).

    A category is a NOUN, so it must survive the SAME domain-noun test the
    parent-resource walk applies, plus be a single word:

    * not an organisational convention (``(main)``, ``(use-page-wrapper)``);
    * not transparent (``(api)``, ``(v1)``, ``(src)``, ``(providers)``);
    * a SINGLE token — a multi-word group is a PREDICATE describing a
      condition or a wrapper, never a product category. This is what
      disqualifies the access-control class (``(org-admin-only)`` ->
      'Attributes Org Admin Only') and it is a mechanism, not a list:
      ``(reports)`` / ``(dashboard)`` / ``(marketing)`` pass, every
      ``a-b-c`` predicate fails.
    """
    word = (inner or "").strip()
    if not word or is_junk_route_group(word):
        return False
    if is_transparent(word):
        return False
    return len([t for t in _KEY_SPLIT.split(word.lower()) if t]) == 1


def _parent_resource(segs: list[str], is_transparent: Callable[[str], bool]) -> str | None:
    """The nearest ANCESTOR segment that names a domain resource, or None.

    Walk semantics (this is the mechanism, and it is what separates the
    two umami exhibits):

    * a dynamic param is TRANSPARENT — ``boards/[boardId]/shares`` is the
      REST nested-resource shape, and the collection above the id is the
      real parent ("Board Shares");
    * a parallel slot / private folder / route group STOPS the walk — a
      slot is a layout hole, not a resource, so an intercepting overlay
      under ``@modal`` has NO parent resource and keeps its honest base
      ("Sessions", not "Website Sessions"); a route group is an author
      CATEGORY, handled by the category trigger instead;
    * an api / version / structural / container segment stops it too —
      those are not domain nouns (spec: "non-api/app/src") — UNLESS it
      directly parents a dynamic param (see below).

    RESOURCE-COLLECTION rule (warden №37 blocker 2): a segment immediately
    followed by a dynamic param is a resource COLLECTION even when its
    word lives in the structural vocabulary — nobody puts an instance id
    under a code-location directory. ``apps/[slug]/setup`` therefore
    yields the parent 'apps' -> "App Setup", while the monorepo
    ``apps/web/app/...`` (a NAMED child, no param) keeps 'apps'
    transparent. One rule, no path literals.

    WORKSPACE-UNIT rule (flip-pack §35 wave): a segment whose IMMEDIATE
    parent is a structural container (``apps/dashboard``,
    ``packages/banking``) names a WORKSPACE UNIT, not a domain resource —
    the app IS the product, so gluing its name onto every route inside it
    is noise on every monorepo at once ('Settings' -> "Dashboard
    Settings"). The ratified ``(main)/admin/websites`` class is untouched:
    there ``admin``'s parent is a route GROUP, so it is a real route
    segment. The resource-collection rule still wins over this one.
    """
    saw_param = False
    for i in range(len(segs) - 2, -1, -1):
        seg = segs[i]
        if is_dynamic_segment(seg):
            saw_param = True
            continue
        if is_route_group(seg) or is_parallel_slot(seg) or is_private_folder(seg):
            return None
        if seg.startswith("("):        # intercepting marker — not a resource
            return None
        if is_transparent(seg):
            return seg if saw_param else None
        if not saw_param and i > 0 and is_transparent(segs[i - 1]):
            return None                # workspace unit, not a resource
        return seg
    return None


def _category_group(
    segs: list[str], is_transparent: Callable[[str], bool],
) -> str | None:
    """The nearest route-group ancestor that is a legal CATEGORY, or None."""
    for seg in reversed(segs[:-1]):
        inner = route_group_inner(seg)
        if inner is None:
            continue
        if not is_category_group(inner, is_transparent):
            continue
        return inner
    return None


def route_qualified_display(
    anchor_id: str,
    base_display: str,
    *,
    word_of: Callable[[str], str],
    is_transparent: Callable[[str], bool],
) -> tuple[str, str, str] | None:
    """``(display, reason, qualifier)`` for the M2 rung, or ``None``.

    Returns ``(display, reason, qualifier)`` — the qualifier is returned so
    the caller can RECORD the tokens this rung injected
    (``Feature.display_qualifier_tokens``); the attribution consumers
    subtract them, because a qualifier the engine wrote is not evidence
    about the PF's domain (warden №37 blocker 1).

    ``word_of`` turns a raw path segment into its display word (the naming
    contract's ``_display_word``); ``is_transparent`` answers "is this
    segment api / version / structural / a hub container?".

    Gate (a): the base is a SINGLE word — a multi-word base already reads
    as a phrase ("API Key" is complete). Gate (b): at least one trigger —
    a parent resource, a category route-group, or a dev-vocabulary
    collision. Composition shapes, deterministic and singularized:
    ``<SingularParent> <Base>`` ("Board Shares") and ``<Base>
    <SingularGroup>`` ("Performance Report"). Stutter is deduped.
    """
    src, _, path = (anchor_id or "").partition(":")
    if src != "route":
        return None
    base = (base_display or "").strip()
    if not base or len(base.split()) != 1:
        return None
    if has_marker_residue(base):
        return None            # M1's job; never compose onto marker residue
    if is_lexicon_base(base):
        return None            # the lexicon owns this base
    segs = [s for s in (path or "").split("/") if s]
    if len(segs) < 2:
        return None
    parent = _parent_resource(segs, is_transparent)
    group = _category_group(segs, is_transparent)
    dev_collision = lexicon_key(base) in dev_vocab()
    if not (parent or group or dev_collision):
        return None
    if parent:
        qual = _singular_word(word_of(parent))
        if not qual or _fold(qual) == _fold(base):
            return None
        composed, reason = f"{qual} {base}", "parent-resource"
    elif group:
        qual = _singular_word(word_of(group))
        if not qual or _fold(qual) == _fold(base):
            return None
        composed, reason = f"{base} {qual}", "route-group"
    else:
        # dev-vocabulary collision with NO evidence to qualify from: the
        # honesty floor wins — dress, never invent (doctrine law 7).
        return None
    composed = dedupe_stutter(composed)
    if not composed or composed.strip().lower() == base.strip().lower():
        return None
    return composed, reason, qual


def distinguishing_ancestor(anchor_id: str, base: str) -> str | None:
    """The nearest ancestor segment that DISTINGUISHES this anchor from a
    same-named sibling, or ``None`` (fixb134 M4a).

    Deliberately more permissive than :func:`_parent_resource`: that walk
    answers "what makes a better PRODUCT NAME" (strict — a hub container
    or an api dir is refused); this one answers "what makes this id
    UNIQUE", so any real ancestor word qualifies. ``integrations/alby``
    therefore yields 'integrations' -> 'Alby (Integrations)' where the
    product walk correctly abstains.

    Refused: organisational segments (param / group / marker / slot /
    private), a word that RESTATES the base (the whole point), and bare
    code-location words — 'Alby (Src)' distinguishes nothing a human can
    use, so the caller falls through to the existing uniqueness ladder.
    """
    _src, _, path = (anchor_id or "").partition(":")
    segs = [x for x in (path or "").split("/") if x]
    if len(segs) < 2:
        return None
    for seg in reversed(segs[:-1]):
        if is_dynamic_segment(seg) or is_parallel_slot(seg):
            continue
        if is_private_folder(seg) or seg.startswith("("):
            continue
        if same_phrase(seg, base):
            continue
        if lexicon_key(seg) in _CODE_LOCATION_WORDS:
            continue
        return seg
    return None


def collision_qualifier_no_self(
    display: str, qualifier: str, anchor_id: str = "",
) -> tuple[str | None, bool]:
    """``(qualifier_to_use, replaced)`` for a slug/display collision rung
    (fixb134 M4a). ``None`` means "this rung says nothing — go to the next
    ladder rung".

    Warden §39 root-cause: the guard originally sat on the anchored-mint
    collision branch, which is NOT where the live cal.com ids are born.
    The real producers compose ``<display> (<terminal key>)`` — and since
    the display IS derived from that same terminal segment, those rungs are
    self-restating BY CONSTRUCTION, not occasionally: every collision they
    resolve mints an 'alby-(alby)'. Armed, such a rung reaches for a
    DISTINGUISHING ancestor and otherwise abstains so the next rung (the
    cid tail / numeral) answers instead.
    """
    if not qualifier or not same_phrase(display, qualifier):
        return qualifier or None, False
    alt = distinguishing_ancestor(anchor_id, display) if anchor_id else None
    if not alt:
        return None, True
    # Warden §40 rider — a mint-born qualifier reaches the display raw, so
    # it shipped lower-case next to the board's own 'Org (Router)'-style
    # rows ('Alby (integrations)', 'Hitpay (app Store)' — world-first
    # mixed case). Route it through the SAME casing polish every other
    # display word gets, so the paren tail renders like its siblings.
    return polish_qualifier_word(alt), True


def polish_qualifier_word(word: str) -> str:
    """A raw path segment rendered as a display qualifier.

    Word-splits the segment (kebab/snake/camel) and applies the shared
    ``polish_display_casing`` vocabulary, so acronyms and brands keep
    their canonical spelling: 'integrations' -> 'Integrations',
    'app-store' -> 'App Store', 'api' -> 'API'.
    """
    from wystan.pipeline_v2.naming_contract import (
        load_naming_vocab,
        polish_display_casing,
    )

    raw = re.sub(r"[^A-Za-z0-9]+", " ", str(word or "")).strip()
    if not raw:
        return ""
    titled = " ".join(
        (w[:1].upper() + w[1:]) if (w and w[0].islower()) else w
        for w in raw.split()
    )
    return polish_display_casing(titled, load_naming_vocab()) or titled


def qualifier_tokens(qualifier: str) -> list[str]:
    """The tokens a qualifier contributes to a display — the record the
    attribution consumers subtract.

    BOTH the raw token and its singular fold are recorded, because the
    consumers do not share a tokenizer: the token re-home and the affinity
    gate singularize ('settings' -> 'setting') while ``invariant_hooks``
    and the fold planner do not. Recording one form only would silently
    leak a plural qualifier ('Settings Profile') past half of them.
    """
    toks: set[str] = set()
    for t in _KEY_SPLIT.split((qualifier or "").lower()):
        if not t:
            continue
        toks.add(t)
        folded = _fold(t)
        if folded:
            toks.add(folded)
    return sorted(toks)


def display_qualifier_stops(pf: Any) -> frozenset[str]:
    """Tokens M2 injected into ``pf.display_name`` — the set the token
    journey re-home, the home-affinity gate, the uf_synth_fold PF-echo and
    the R5-3 dir-token cap must NOT read as evidence about this PF.

    Empty (⇒ every consumer byte-identical) whenever the rung is off or
    the PF was never dressed, so the exclusion is inert on the OFF path
    without any consumer needing its own flag check.
    """
    from wystan.pipeline_v2.naming_contract import (
        pf_route_qualifier_rung_enabled,
    )

    if not pf_route_qualifier_rung_enabled():
        return frozenset()
    return frozenset(
        str(t).strip().lower()
        for t in (getattr(pf, "display_qualifier_tokens", None) or [])
        if str(t).strip()
    )


def strip_qualifier_tokens(display: str, stops: frozenset[str]) -> str:
    """``display`` with M2's injected qualifier WORDS removed — the
    undressed base. Used by the R5-3 confidence lane so dressing can never
    shadow a shape verdict (warden №37 blocker 3)."""
    cur = (display or "").strip()
    if not cur or not stops:
        return cur
    kept = [w for w in cur.split() if _fold(w) not in stops]
    return " ".join(kept).strip() or cur
