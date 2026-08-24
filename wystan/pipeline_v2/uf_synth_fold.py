"""Seg C — UF synth quality laws L-C1..L-C4 (B71, ``WYSTAN_NAMING_PACK``, OFF).

Census class C (67 echo/dup UF families): the synthesizer stamps ``verb + noun``
per cluster with no board name-census, so it echoes PF names, splits multiword
verbs, and duplicates same-noun-head families. Four laws, mechanism over the
engine's OWN template-verb vocab (never a new dictionary):

* **L-C1 echo-fold** — a UF whose noun-phrase equals its PF name (verb from the
  template set) is a bare echo; it FOLDS into the RICH canonical UF of the same
  PF (documenso ``User`` -> ``Manage users``, ``Teams`` -> ``Manage teams``;
  plane ``View propel``; cal ``Manage di``). Direction is fixed: the echo dies,
  the rich journey survives (census §4 anti-case-direction) — and a PF whose
  ONLY journey is the echo keeps it (never kill the last journey).
* **L-C2 verb-phrase integrity** — a multiword verb (``Set up``) is never split;
  a STUTTER (the second token is itself a verb — ``Manage create topic`` — or a
  broken particle splice — ``Browse up Slack`` / ``Create up inbox``) is repaired
  by dropping the stray token. Known multiword verbs (``set up``, ``sign in``…)
  are protected.
* **L-C3 same-noun-head families** — same-PF UFs sharing a noun-head (cal routing
  forms x5, novu topics x3) fold ONLY when their member span-sets overlap
  (coordinates decide, not the name).
* **L-C4 board uniqueness** — duplicate UF names on one board (cal ``Org`` x2)
  are collisions: folded (same PF + overlapping spans) or flagged to qualify.

fixb131 — three defects of this one zone, measured on the 31 KS66 stage
captures:

* **Seg A** (``WYSTAN_UF_VERB_ARM_MODIFIER_GUARD``, default OFF) — L-C2's
  VERB arm ate noun MODIFIERS written as template verbs: 36 plan-eligible
  firings, **zero** of them a real stutter. See :func:`has_verb_stutter`.
* **Seg B** — the fold is a producer that rewrites membership and names AFTER
  Law C, so the B100 post-mint rescore hook now hangs on it (the hook lives
  at the seam in ``synth_quality``, where the caller's Law C bundle is).
* **Seg C** — the fold computed a full id-tier lineage (``plan.fold``) and
  threw it away; ``folded[]`` now ships in the telemetry, the telemetry now
  reaches ``scan_meta.synth_quality.uf_synth_fold``, and the journey-lineage
  audit reads it as an ID-BOUND channel.

PURE plan (no mutation); ``apply_uf_synth_fold`` applies it behind
``naming_pack_enabled`` — OFF/unset never runs, so UF names/membership are
byte-identical (the B40 byte-stable-name law holds when the flag is off; this is
a NAMING_PACK-gated, sanctioned name change when on). Folds union members
(conservation). The ON-path effect on user_flows[] conservation + the name-census
fall is the operator's keyed A/B to certify.
"""

from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Mapping

from wystan.pipeline_v2.census_join import flow_span_records, index_flows_by_uf

__all__ = [
    "MULTIWORD_VERBS",
    "PARTICLES",
    "VERB_ARM_MODIFIER_GUARD_ENV",
    "verb_arm_modifier_guard_enabled",
    "FOLD_CANONICAL_VERB_PRIORITY_ENV",
    "fold_canonical_verb_priority_enabled",
    "canonical_verb_rank",
    "VerbArmGuard",
    "build_verb_arm_guard",
    "noun_phrase",
    "is_pf_echo",
    "has_verb_stutter",
    "repair_stutter",
    "name_richness",
    "noun_head",
    "meaning_tokens",
    "is_malformed_phrase",
    "spans_overlap",
    "UfSynthPlan",
    "plan_uf_synth",
    "apply_uf_synth_fold",
]

#: Protected multiword verbs — ``(lead, particle)`` pairs that are ONE verb and
#: must never read as a stutter. Small, universal English phrasal-verb set (not a
#: per-repo list); corroborates the "don't split a multiword verb" law.
MULTIWORD_VERBS = frozenset({
    ("set", "up"), ("sign", "in"), ("sign", "out"), ("log", "in"),
    ("log", "out"), ("opt", "in"), ("opt", "out"), ("back", "up"),
    ("check", "in"), ("check", "out"), ("roll", "back"), ("lock", "in"),
})

#: Verb particles that only appear mid-phrase — a leading verb followed by one of
#: these (that is NOT a protected multiword verb) is a broken splice.
PARTICLES = frozenset({"up", "in", "out", "on", "off", "down"})

#: fixb131 Seg A — the VERB arm's modifier guard (default **OFF**; flip-scale,
#: 37 live renames). See :func:`has_verb_stutter`.
VERB_ARM_MODIFIER_GUARD_ENV = "WYSTAN_UF_VERB_ARM_MODIFIER_GUARD"

#: fixb136 — CANONICAL VERB-PRIORITY for the L-C1 / L-C3 fold (default
#: **ON** since flip-pack №39, KEY_SCHEMA 72; explicit ``0`` is the
#: kill-switch forever).
#:
#: The fold picks a survivor, and it picked by NAME RICHNESS alone. The
#: fixb132 executor measured what that costs the moment any lane makes a
#: name richer: a de-glued READ row ('Browse admin websites', meaning
#: tokens {admin, websites}) outranked the WRITE journey beside it
#: ('Create & edit websites', {website}) and the board LOST the write
#: journey — five of them on one umami pair, which is why that pack had
#: to grow a fold-neutrality guard and leave nine rows un-de-glued.
#:
#: A journey's CLASS is the more important question than its adjective
#: count: what the user does there. Write/manage (create / update /
#: delete / act) outranks read (browse / view); inside a class the banked
#: rich-tiebreak decides exactly as before. Unset/``0`` ⇒ every fold
#: decision, every telemetry key and the serialized output byte-identical.
#: Appended to ``ENV_OUTPUT_FLAGS`` WITHOUT a KEY_SCHEMA bump — the bump
#: rides the separate flip commit (flip-protocol).
FOLD_CANONICAL_VERB_PRIORITY_ENV = "WYSTAN_FOLD_CANONICAL_VERB_PRIORITY"

#: Action families that constitute a WRITE/MANAGE claim. ``act`` is the
#: 'Manage'/'Configure' umbrella — the spec names configure and manage
#: beside create/edit/delete, and this engine buckets all of them here.
#: Read from ``journey-action-families.yaml`` through the naming
#: contract's own index — one family vocabulary for the stack.
_CANONICAL_WRITE_FAMILIES = frozenset({"create", "update", "delete", "act"})

_WS = re.compile(r"\s+")
_SPLIT = re.compile(r"[^a-z0-9]+")


def verb_arm_modifier_guard_enabled() -> bool:
    """fixb131 Seg A — default **OFF**. Unset/``0`` ⇒ the verb arm asks its
    pre-fixb131 question and every UF name/telemetry key is byte-identical."""
    return os.environ.get(VERB_ARM_MODIFIER_GUARD_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def fold_canonical_verb_priority_enabled() -> bool:
    """fixb136 — default **ON** since the 2026-08-10 flip-pack №39
    (KEY_SCHEMA 72; warden №43 GO): the L-C1/L-C3 canonical asks the verb
    CLASS first, a row a naming lane renamed this scan is not a fold
    SOURCE, and the de-glue lane's bare-PF-echo refusal is live.
    ``WYSTAN_FOLD_CANONICAL_VERB_PRIORITY=0`` restores the banked
    richest-name fold order byte for byte (the kill-switch law forever;
    unset ≡ ``1``)."""
    return os.environ.get(
        FOLD_CANONICAL_VERB_PRIORITY_ENV, "1",
    ).strip().lower() in {"1", "true", "yes", "on"}


def canonical_verb_rank(
    name: str, verbs: frozenset[str] | None = None,
) -> int:
    """0 when the name's LEADING VERB PHRASE makes a write/manage claim,
    1 otherwise. Lower wins.

    The whole coordinated phrase, not just the first token — measured. A
    lead-only reading ranked 'Browse and manage pixels' (17 members, the
    board's real pixels journey) BELOW 'Create pixels' and the fold ate
    the better row: the journey manages pixels, and the claim lives in the
    second conjunct. So the walk consumes the leading run of template
    verbs JOINED BY CONJUNCTIONS and answers 0 if any of them writes. It
    stops at the first non-verb word, so a resource that happens to be a
    verb homonym further along ('Browse admin team') can never promote a
    read — and a bare ADJACENT verb does not extend the claim either,
    because that shape is L-C2's stutter ('Browse create topic' is a
    broken splice this module repairs, not a coordination), which is also
    how the spec's "a rename never gains priority" clause is honoured at
    the token level.

    Deliberately TWO buckets, not three. The ruling is "write/manage
    outranks read"; it says nothing about where a lead OUTSIDE the family
    vocabulary belongs ('Analyze revenue performance', 'Track clicks'), so
    inventing a third rank would silently re-order canonicals the spec
    never spoke about. Unknown leads share rank 1 with reads and are then
    separated by the banked rich-tiebreak, exactly as today.

    Reads the family index the naming contract already owns — one
    vocabulary for the stack, never a second verb list here. Lazy import:
    ``naming_contract`` imports this module's siblings, so the edge stays
    one-way at import time (the ``floor()`` precedent in this file).

    TWO readers, because one of them has a hole: ``journey-action-families
    .yaml`` maps 'configure'/'edit'/'delete' but NOT ``manage`` — measured,
    ``verb2fam['manage'] is None`` — while ``_ACTION_FAMILY_WORD`` is the
    table the engine uses to WRITE 'Manage' as the ``act`` family's own
    display word. So the engine mints a lead its family index cannot read
    back, and 'Manage boards' would have tied with 'Browse boards' — the
    exact inversion this pack exists to stop, on the most common
    engine-minted name there is. The inverse of that shipped table closes
    it: a lead the engine ITSELF writes for family F is family F. No new
    vocabulary, and the YAML is left alone (it feeds Law C's ``mfams``,
    which is not this pack's channel)."""
    from wystan.pipeline_v2.naming_contract import (
        _ACTION_FAMILY_WORD,
        _action_family_index,
        _verb_class_tokens,
        load_naming_vocab,
    )
    vocab = load_naming_vocab()
    idx = _action_family_index(vocab)
    lex = verbs if verbs is not None else _verb_class_tokens(vocab)
    word2fam = {w.lower(): f for f, w in _ACTION_FAMILY_WORD.items()}

    def _fam(tok: str) -> str | None:
        fam = idx["verb2fam"].get(tok)
        if fam == "read":
            fam = "browse"
        return fam or word2fam.get(tok)

    toks = _toks(name)
    i, joined = 0, True
    while i < len(toks):
        tok = toks[i]
        if tok in _CONJ:
            joined = True                 # 'and'/'or' coordinates the claim
            i += 1
            continue
        if not joined or (tok not in lex and _fam(tok) is None):
            break                         # the verb phrase ended
        if _fam(tok) in _CANONICAL_WRITE_FAMILIES:
            return 0
        joined = False                    # a NEXT verb needs a conjunction
        i += 1
    return 1


def _norm(text: str) -> str:
    return _WS.sub(" ", (text or "").strip()).lower()


def _toks(text: str) -> list[str]:
    return [t for t in _SPLIT.split((text or "").lower()) if t]


def _stem(tok: str) -> str:
    return tok[:-1] if len(tok) > 3 and tok.endswith("s") else tok


def _tokset_stemmed(text: str) -> set[str]:
    return {_stem(t) for t in _toks(text)}


@dataclass(frozen=True)
class VerbArmGuard:
    """fixb131 Seg A — THIS REPO's own action/modifier census over its own
    generated flow names. A mechanism, not a vocabulary: the corpus is the
    repo's flow-name list, read with this module's one tokenizer + ``_stem``
    fold, and the floor is the C-B umbrella rung's already-banked
    scale-invariant bar (``max(2, ceil(0.025 * flows))`` — no new constant).

    ``action_lex`` counts a token at the LEAD position of a flow name;
    ``modifier_lex`` counts the SAME token at every other position of the
    same corpus. The flow-naming contract (``flow_name_v2``: "a flow name is
    a verb-led capability label") is what makes the split meaningful — a
    token this repo overwhelmingly writes AFTER the lead is a qualifier here,
    whatever an English dictionary thinks of it.
    """

    action_lex: Mapping[str, int]
    modifier_lex: Mapping[str, int]
    flow_count: int

    def floor(self) -> int:
        from wystan.pipeline_v2.naming_contract import (
            _UMBRELLA_LEAD_MIN,
            _UMBRELLA_LEAD_PERMILLE,
        )
        n = max(0, int(self.flow_count))
        return max(_UMBRELLA_LEAD_MIN,
                   -(-_UMBRELLA_LEAD_PERMILLE * n // 1000))

    def is_repo_action(self, token: str) -> bool:
        """True when this repo declares ``token`` an ACTION: attested at or
        above the banked floor AND written as a lead strictly more often than
        as a qualifier. Both halves are load-bearing — the floor alone
        blessed kentcdodds ``search`` (7 leads, exactly at floor, against 13
        qualifier uses: 'search results' is a compound, not a stray verb),
        and the majority alone blessed jsonhero ``new`` (1 lead, 0 qualifier
        uses — a single accident is never a repo's action)."""
        if not token:
            return False
        lead_n = int(self.action_lex.get(token, 0))
        return lead_n >= self.floor() and lead_n > int(
            self.modifier_lex.get(token, 0))


def build_verb_arm_guard(flows: Any) -> VerbArmGuard:
    """Build :class:`VerbArmGuard` from the repo's flow names. The LEAD side
    reuses ``naming_contract.repo_lead_lexicon`` verbatim (one lead reader
    for the stack — the C-B mechanism, not a copy); the qualifier side is the
    same corpus at every non-lead position, minus the ``flow`` suffix the
    naming contract appends to every generated name."""
    from wystan.pipeline_v2.naming_contract import repo_lead_lexicon

    names = [str(getattr(f, "name", "") or "") for f in (flows or ())]
    modifier: Counter = Counter()
    for nm in names:
        for tok in [_stem(t) for t in _toks(nm)][1:]:
            if tok != "flow":
                modifier[tok] += 1
    return VerbArmGuard(
        action_lex=dict(repo_lead_lexicon(names, _stem)),
        modifier_lex=dict(modifier),
        flow_count=len(names),
    )


def noun_phrase(name: str, verbs: frozenset[str]) -> str:
    """The name with leading template-verb tokens stripped: ``Manage users`` ->
    ``users``, ``View propel`` -> ``propel``, ``User`` -> ``user`` (no verb)."""
    words = name.split()
    i = 0
    while i < len(words) and _norm(words[i]) in verbs:
        i += 1
    return " ".join(words[i:]) if i < len(words) else " ".join(words)


def is_pf_echo(name: str, pf_display: str, verbs: frozenset[str]) -> bool:
    """True when ``name`` is a bare echo of its PF IDENTITY: its noun-phrase
    (verb from the template set, or a bare noun) equals the PF display
    (stem-tolerant). Carries no own content token.

    NEVER compared against the UF's OWN ``resource`` field — the live-documenso
    refutation (2026-07-16): resource is derived from the UF's own name, so the
    own-resource comparison made EVERY well-formed 'Manage <noun>' row an "echo"
    of itself ('Manage users' res='user') and the fold inverted — 9 rich
    canonicals died under PFs ('Admin'/'Settings') their names never echoed."""
    if not name:
        return False
    np = _tokset_stemmed(noun_phrase(name, verbs))
    if not np:
        return False
    pf = _tokset_stemmed(pf_display)
    return bool(pf) and np == pf


def has_verb_stutter(
    name: str,
    verbs: frozenset[str],
    *,
    guard: VerbArmGuard | None = None,
    resource_tokens: frozenset[str] | set[str] = frozenset(),
) -> bool:
    """True when the second LITERAL word is a stray verb/particle — a multiword
    verb was split and recombined (``Browse up Slack``, ``Manage create topic``).

    Operates on the literal space-split words, NOT the alnum tokenizer — the
    live-documenso refutation (2026-07-16): tokenizing dropped '&' so ``Browse &
    filter GitHub forks`` read as (browse, filter, ...) -> "stutter" -> the
    repair ate the literal '&' word (x5 mutations). A coordinated verb phrase
    (``Browse & filter``, ``Create and edit``) is VERBATIM by law: a non-alpha
    joiner or a conjunction as the second word is never a stutter. Protected
    multiword verbs (``set up``…) are NOT stutters either.

    fixb130 / NS-C — the PARTICLE arm asks one more question: WHO wrote the
    lead? A splice happens when the synthesizer's own TEMPLATE verb replaced
    the author's lead and stranded its particle ('Set up Slack' -> 'Browse up
    Slack'): the lead is then a template verb BY CONSTRUCTION, because the
    template is the thing that overwrote it. When the lead is NOT one of the
    engine's template verbs, nothing was substituted — the phrasal verb is
    authored end to end and the particle belongs to it. Measured on the KS66
    world: 'Sign up for a new account' shipped as 'Sign for a new account' on
    9 boards (cal.com UF-217, ente UF-056, infisical UF-207, kan UF-026,
    karakeep UF-048, lobe-chat UF-108, novu UF-119, supabase UF-157, unsend
    UF-047), each wearing ``high`` — a LYING high, since the composition
    rungs then grounded a verb the row no longer spelled. The eleven holders
    escaped only by accident of shape (a conjunction third word, a comma
    glued to the particle, or 'sign in' being one of the twelve entries in
    ``MULTIWORD_VERBS``), which is what proves the pair list is the wrong
    instrument: extending it would also have to carry 'turn on', 'fill in',
    'roll out' — the 2026-07-07 mechanisms-over-vocabularies law forbids
    exactly that. The provenance question needs no list at all, and it leaves
    the VERB arm ('Manage create topic') untouched.

    fixb131 / Seg A — and the VERB arm is where the same disease lived. Its
    only question was "is the second word in the template verb vocabulary?",
    and English writes most product nouns as verbs, so the arm ate NOUN
    MODIFIERS: measured over the 31 KS66 stage captures it fired 37 times and
    was right **zero** times ('Track search analytics' -> 'Track analytics',
    'Export resume as DOCX' -> 'Export as DOCX' — reactive-resume lost the
    word 'resume' on 8 of its 36 journeys; 'Manage access tokens' -> 'Manage
    tokens'; 'Create new item' -> 'Create item', the root of the jsonhero
    fixb129 exhibit; 'Bulk delete links' -> 'Bulk links', the damaged name
    behind the twenty 'Bulk Records' class). Every one wore ``high``.

    ``guard`` arms three questions, each mirroring a law already banked
    elsewhere, and ALL THREE must say "stutter" for the arm to fire:

    * **provenance** — the lead must be a TEMPLATE verb (the exact mirror of
      the particle arm above: only the template that overwrote an author's
      lead can have stranded the token behind it). Saves 15/37, among them
      'Bulk delete links', whose lead is a qualifier no template ever wrote.
    * **repo action** — the second token must be one THIS repo declares an
      action in its own flow names (:meth:`VerbArmGuard.is_repo_action`).
      Saves 'Create new item' ('new' leads one flow of 78) and 'Browse search
      results' ('search' leads 7 but qualifies 13).
    * **not the object** — the second token must not be a token of the row's
      OWN resource phrase. The mirror of ``member_lead_echo_token``'s
      NOUN-ECHO guard ("a resource token is the resource echoing itself, not
      an action"); saves 'Manage access tokens' (resource ``access-token``).

    Together: 37/37 live rows keep their modifier, and a genuine double verb
    ('Manage create topic', 'Manage manage tokens') still repairs — its
    second word is a repo action and never its resource. ``guard=None``
    (flag OFF/unset) ⇒ the pre-fixb131 question, byte for byte."""
    words = (name or "").split()
    if len(words) < 2:
        return False
    lead, second = words[0].lower(), words[1].lower()
    if not words[1].isalpha() or second in {"and", "or"}:
        return False                       # coordinated verb phrase — verbatim
    if (lead, second) in MULTIWORD_VERBS:
        return False
    # Coordinated VERB LIST ('Browse filter and Stripe events' ~ 'Browse,
    # filter, and ...'): the second verb is conjoined by the THIRD word — not a
    # stutter. The keyed-documenso refutation (2026-07-16): repairing it dropped
    # the middle verb and left a dangling 'and' ('Browse and Stripe events').
    if len(words) >= 3 and (
        not words[2].isalpha() or words[2].lower() in _CONJ
    ):
        return False
    if second in verbs:
        if guard is None:
            return True
        # VERB arm, fixb131 — provenance, then the repo's own action census,
        # then the noun-echo mirror. Any "no" means the second word is a
        # modifier of the head noun and the name is already correct.
        if lead not in verbs:
            return False
        stem2 = _stem(second)
        if stem2 in resource_tokens:
            return False
        return guard.is_repo_action(stem2)
    # PARTICLE arm — only a TEMPLATE-minted lead can have stranded one.
    return second in PARTICLES and lead in verbs


def repair_stutter(name: str, verbs: frozenset[str]) -> str:
    """Drop the stray second token: ``Browse up Slack`` -> ``Browse Slack``,
    ``Manage create topic`` -> ``Manage topic``, ``Create up inbox`` ->
    ``Create inbox``. Casing of the surviving words is preserved."""
    words = name.split()
    if len(words) < 2:
        return name
    repaired = [words[0]] + words[2:]
    return " ".join(repaired) if len(repaired) > 1 else name


def name_richness(name: str, pf_display: str, verbs: frozenset[str]) -> int:
    """Count of the name's OWN content tokens — noun-phrase tokens that are not in
    the PF display. Zero => a bare echo; higher => a specialized journey."""
    np = _tokset_stemmed(noun_phrase(name, verbs))
    return len(np - _tokset_stemmed(pf_display))


def noun_head(name: str, verbs: frozenset[str]) -> str:
    """The stemmed head noun (last noun-phrase token) — the L-C3 family key."""
    toks = [_stem(t) for t in _toks(noun_phrase(name, verbs))]
    return toks[-1] if toks else ""


_CONJ = frozenset({"and", "or"})


def meaning_tokens(name: str, verbs: frozenset[str]) -> set[str]:
    """The name's meaningful (non-verb, non-particle, non-conjunction) stemmed
    tokens — the canonical-rank currency ('meaningful tokens beyond verb+noun')."""
    return {
        _stem(t) for t in _toks(name)
        if t not in verbs and t not in PARTICLES and t not in _CONJ
    }


_CONJ_WORDS = frozenset({"and", "or", "&"})


def is_malformed_phrase(name: str, verbs: frozenset[str]) -> bool:
    """Structural phrase-integrity check (mechanism, no brand dictionary) — the
    keyed-documenso sanitary law (2026-07-16). Malformed shapes:

    * a leading or trailing coordinating conjunction;
    * doubled conjunctions (``and and``, ``and &``);
    * broken lead-verb coordination: ``<template-verb> and <Proper-noun> ...`` —
      a coordinating conjunction directly after the lead verb must conjoin
      another verb; a CAPITALIZED non-verb in that slot ('Browse and Stripe
      events') means the verb was eaten. Lowercase third words pass ('Browse
      and enforce server limits' — 'enforce' may simply be outside the vocab).
    """
    words = (name or "").split()
    if not words:
        return False
    low = [w.lower() for w in words]
    if low[0] in _CONJ_WORDS or low[-1] in _CONJ_WORDS:
        return True
    for a, b in zip(low, low[1:]):
        if a in _CONJ_WORDS and b in _CONJ_WORDS:
            return True
    if (
        len(words) >= 3
        and low[0] in verbs
        and low[1] in _CONJ_WORDS
        and low[2] not in verbs
        and words[2][:1].isupper()
    ):
        return True
    return False


def spans_overlap(a: Any, b: Any) -> bool:
    """True when two flows'/UFs' member span-sets share any covered line in a
    common path (coordinates decide L-C3 family folds, not the name)."""
    ra, rb = flow_span_records(a), flow_span_records(b)
    for path, aranges in ra.items():
        for bs, be in rb.get(path, []):
            for as_, ae in aranges:
                if as_ <= be and bs <= ae:
                    return True
    return False


# ── plan ──────────────────────────────────────────────────────────────────────


@dataclass
class UfSynthPlan:
    rename: dict[str, str] = field(default_factory=dict)     # L-C2
    fold: dict[str, str] = field(default_factory=dict)       # L-C1 / L-C3 loser->winner
    collisions: list[tuple[str, str]] = field(default_factory=list)  # L-C4
    reasons: dict[str, str] = field(default_factory=dict)
    #: fixb131 Seg A — verb-arm firings the modifier guard refused (0 when
    #: the guard is not armed: nothing is asked, so nothing is refused).
    modifier_refused: int = 0

    def survivors(self, ufs: list[Any]) -> list[Any]:
        gone = set(self.fold)
        return [u for u in ufs if str(getattr(u, "id", "")) not in gone]


def _uf_id(uf: Any) -> str:
    return str(getattr(uf, "id", "") or "")


def _uf_name(uf: Any, plan: "UfSynthPlan") -> str:
    """The effective name for the echo test — the L-C2 repair if one applies."""
    return plan.rename.get(_uf_id(uf), str(getattr(uf, "name", "") or ""))



def _undressed_pf_display(pf: Any, key: str) -> str:
    """The PF display MINUS the qualifier words the fixb133 M2 rung
    injected (warden §37 blocker 1).

    ``lc1_pf_echo`` folds a journey whose name echoes its PF display, and
    the collision-qualifier lane borrows that display for UF NAMES — so an
    engine-written qualifier would both manufacture echoes and leak into
    journey names. Identity when the rung is off or the row is undressed.
    """
    from wystan.pipeline_v2.pf_display_doctrine import (
        display_qualifier_stops,
        strip_qualifier_tokens,
    )

    disp = str(getattr(pf, "display_name", None) or key)
    stops = display_qualifier_stops(pf)
    return strip_qualifier_tokens(disp, stops) if stops else disp


def plan_uf_synth(
    user_flows: list[Any],
    flows: list[Any],
    product_features: list[Any],
    verbs: frozenset[str],
    fold_exempt_ids: frozenset[str] = frozenset(),
) -> UfSynthPlan:
    """Compute the L-C1..L-C4 plan. Deterministic (input order + stable winner
    tiebreaks). Applies at most one fold per UF.

    ``fold_exempt_ids`` (S2 Seg A rider, wave-gauntlet Class 2 2026-07-18):
    rows that must never be FOLD SOURCES (they can still be fold TARGETS and
    L-C2 rename-repaired). The caller passes the lattice-born partition rows
    when det-aggregation is armed: the lattice's verifier-approved action
    children ('Browse findings' / 'View findings' / 'Create findings') are a
    SANCTIONED same-noun-head family over the same files — exactly the shape
    L-C3's span gate reads as a dup family. Without the exemption the fold
    quietly UNDOES the lattice split and re-mints the giant catch-all
    (RefApp UF-022 7 -> 47, giant-catchall 2 -> 5). Empty set (every caller
    outside the Seg A world) = byte-identical planning.
    """
    plan = UfSynthPlan()
    pf_disp: dict[str, str] = {}
    for pf in product_features:
        key = str(getattr(pf, "name", "") or "")
        pf_disp[key] = _undressed_pf_display(pf, key)
    # Only REAL journeys are eligible — synthesized coverage markers / backstops
    # carry generated names + I8-cover semantics and must never fold/rename here.
    eligible = [
        u for u in user_flows
        if not getattr(u, "is_coverage_marker", False)
        and not getattr(u, "synthesized", False)
    ]
    members = index_flows_by_uf(eligible, flows)

    # fixb131 Seg A — the repo's own action/modifier census, built ONCE per
    # plan (never per row) and only when the guard is armed; unarmed the
    # guard is ``None``, ``has_verb_stutter`` asks its pre-fixb131 question
    # and not a single flow name is read.
    guard = build_verb_arm_guard(flows) if verb_arm_modifier_guard_enabled() \
        else None

    def _res_tokens(uf: Any) -> frozenset[str]:
        """The row's OWN resource phrase, folded with THIS module's stemmer
        (one fold for the whole file). PF display is the fallback exactly as
        Law C's ``_res`` reads it — a row with no resource of its own is
        described by its home."""
        base = str(getattr(uf, "resource", "") or "")
        if not base:
            base = pf_disp.get(
                str(getattr(uf, "product_feature_id", "") or ""), "")
        return frozenset(_tokset_stemmed(base))

    # L-C2 — verb-phrase integrity (rename; feeds the echo test's effective
    # name). A repair whose RESULT is structurally malformed is never adopted
    # (the sanitary guard — a rename must not eat a middle token and leave a
    # dangling conjunction).
    for uf in eligible:
        nm = str(getattr(uf, "name", "") or "")
        stutters = has_verb_stutter(nm, verbs)
        if stutters and guard is not None:
            stutters = has_verb_stutter(
                nm, verbs, guard=guard, resource_tokens=_res_tokens(uf))
            if not stutters:
                plan.modifier_refused += 1
        if stutters:
            fixed = repair_stutter(nm, verbs)
            if (
                fixed and _norm(fixed) != _norm(nm)
                and not is_malformed_phrase(fixed, verbs)
            ):
                plan.rename[_uf_id(uf)] = fixed
                plan.reasons[_uf_id(uf)] = "lc2_verb_stutter"

    by_pf: dict[str, list[Any]] = defaultdict(list)
    for uf in eligible:
        pfid = str(getattr(uf, "product_feature_id", "") or "")
        if pfid:  # a UF with no PF binding cannot echo a PF
            by_pf[pfid].append(uf)

    def _has_lead_verb(name: str) -> bool:
        toks = _toks(name)
        return bool(toks) and toks[0] in verbs

    def _canonical_of(family: list[Any]) -> Any:
        """The live-documenso MANDATE (2026-07-16): canonical = the row with the
        RICHEST name (most meaningful tokens beyond verb+noun; tie-break member
        count, then name length, then id) — and a BARE row (no leading template
        verb) is NEVER canonical while a verbful rival is alive ('User' never
        beats 'Manage users', whatever the member counts).

        fixb136 (``WYSTAN_FOLD_CANONICAL_VERB_PRIORITY``, default OFF) —
        richness alone is the WRONG first question, and it was measured
        costing journeys: a de-glued READ row ('Browse admin websites', 2
        meaning tokens) outranked the WRITE journey beside it ('Create &
        edit websites', 1) and ATE it. The survivor of a fold is the row a
        board keeps, so the first question is what the journey DOES — a
        write/manage claim (create / update / delete / act families)
        outranks a read one (browse / view). Equal class falls through to
        the banked rich-tiebreak byte for byte, and nothing else in the
        key moves.

        The class is read from the row's ORIGINAL name, never from
        :func:`_uf_name`: a rename may not hand its own row the crown
        (the spec's "freshly-renamed" clause). Flag OFF ⇒ the banked
        4-tuple ⇒ every fold decision byte-identical."""
        pool = [u for u in family if _has_lead_verb(_uf_name(u, plan))] or family
        if not fold_canonical_verb_priority_enabled():
            return min(pool, key=lambda u: (
                -len(meaning_tokens(_uf_name(u, plan), verbs)),
                -len(members.get(_uf_id(u), [])),
                -len(_uf_name(u, plan)),
                _uf_id(u),
            ))
        return min(pool, key=lambda u: (
            canonical_verb_rank(str(getattr(u, "name", "") or ""), verbs),
            -len(meaning_tokens(_uf_name(u, plan), verbs)),
            -len(members.get(_uf_id(u), [])),
            -len(_uf_name(u, plan)),
            _uf_id(u),
        ))

    for pf_id, ufs in by_pf.items():
        disp = pf_disp.get(pf_id, "")

        # L-C1 — fold a PF-IDENTITY echo (noun-phrase == PF display, never the
        # row's own resource) into the canonical of its NOUN FAMILY: the rows of
        # the same PF whose noun-phrases contain the echo's nouns ('User' ->
        # {'User','Manage users'}; 'View propel' -> {'View propel','Configure
        # propel pipeline'}). Fold ALWAYS lands on the canonical (richest-name
        # mandate) and fires ONLY when the echo is genuinely barer: the canonical
        # is STRICTLY richer (proper noun-superset) or the echo is bare against a
        # verbful canonical. Same-richness DISTINCT-VERB echo families ('Create /
        # Edit / Delete routing form' under PF 'Routing Forms') are legitimate
        # distinct journeys — they defer to L-C3's span gate, never fold by name.
        # A lone echo (family of 1) is kept — never kill a PF's last journey.
        echoes = [u for u in ufs if is_pf_echo(_uf_name(u, plan), disp, verbs)]
        for e in echoes:
            eid = _uf_id(e)
            if eid in plan.fold or eid in fold_exempt_ids:
                continue
            e_nouns = meaning_tokens(_uf_name(e, plan), verbs)
            family = [
                u for u in ufs
                if _uf_id(u) not in plan.fold
                and e_nouns <= meaning_tokens(_uf_name(u, plan), verbs)
            ]
            if len(family) < 2:
                continue
            canonical = _canonical_of(family)
            wid = _uf_id(canonical)
            if wid == eid:
                continue
            c_nouns = meaning_tokens(_uf_name(canonical, plan), verbs)
            strictly_richer = e_nouns < c_nouns
            bare_vs_verbful = (
                not _has_lead_verb(_uf_name(e, plan))
                and _has_lead_verb(_uf_name(canonical, plan))
            )
            if strictly_richer or bare_vs_verbful:
                plan.fold[eid] = wid
                plan.reasons.setdefault(eid, "lc1_pf_echo")

        # L-C3 — same-noun-head family fold, GATED by member span overlap. The
        # anchor is the family CANONICAL (richest-name mandate — never min-id):
        # the bare twin ('GitHub forks') folds INTO 'Browse & filter GitHub
        # forks', never the reverse.
        live = [u for u in ufs if _uf_id(u) not in plan.fold]
        heads: dict[str, list[Any]] = defaultdict(list)
        for u in live:
            heads[noun_head(_uf_name(u, plan), verbs)].append(u)
        for head, group in heads.items():
            if not head or len(group) < 2:
                continue
            anchor = _canonical_of(group)
            am = members.get(_uf_id(anchor), [])
            for u in group:
                if (u is anchor or _uf_id(u) in plan.fold
                        or _uf_id(u) in fold_exempt_ids):
                    continue
                um = members.get(_uf_id(u), [])
                if any(spans_overlap(a, b) for a in am for b in um):
                    plan.fold[_uf_id(u)] = _uf_id(anchor)
                    plan.reasons.setdefault(_uf_id(u), "lc3_family_overlap")

    # L-C4 — board-wide duplicate names (post-fold surviving real journeys).
    seen: dict[str, str] = {}
    for u in eligible:
        if _uf_id(u) in plan.fold:
            continue
        key = _norm(_uf_name(u, plan))
        if key in seen:
            plan.collisions.append((seen[key], _uf_id(u)))
        else:
            seen[key] = _uf_id(u)
    return plan


def apply_uf_synth_fold(
    user_flows: list[Any],
    flows: list[Any],
    product_features: list[Any],
    verbs: frozenset[str],
    fold_exempt_ids: frozenset[str] = frozenset(),
    max_winner_members: int | None = None,
) -> dict[str, Any]:
    """Apply the plan IN PLACE: rename (L-C2), fold echoes/families into the
    winner (union member_flow_ids — conservation), drop folded rows. Only ever
    called behind ``naming_pack_enabled`` -> OFF path never runs -> byte-identical.
    ``fold_exempt_ids`` — see :func:`plan_uf_synth` (never fold sources).
    ``max_winner_members`` (S2 Seg A it5-1a): a fold whose union would push
    the winner OVER this bar is REFUSED — the it4 panel refutation: UF-058
    was a readable 19 at regrain time, then bar-blind folds grew it to an
    unreadable 32 AFTER the split pass had already run. ``None`` (every
    caller outside the Seg A world) = unlimited, byte-identical behavior.
    Returns telemetry."""
    plan = plan_uf_synth(
        user_flows, flows, product_features, verbs,
        fold_exempt_ids=fold_exempt_ids,
    )
    by_id = {_uf_id(u): u for u in user_flows}
    folds_refused_bar = 0
    if max_winner_members is not None and plan.fold:
        # Readability-bar guard: refuse (drop from the plan) every fold whose
        # member union would exceed the bar; the loser row simply survives.
        # Winner unions are evaluated incrementally in the deterministic plan
        # order so chained folds onto one winner respect the bar cumulatively.
        union_sizes: dict[str, set[str]] = {}
        kept_folds: dict[str, str] = {}
        for loser_id, winner_id in plan.fold.items():
            loser, winner = by_id.get(loser_id), by_id.get(winner_id)
            if loser is None or winner is None:
                kept_folds[loser_id] = winner_id
                continue
            acc = union_sizes.setdefault(
                winner_id, set(getattr(winner, "member_flow_ids", None) or []),
            )
            lm = set(getattr(loser, "member_flow_ids", None) or [])
            if len(acc | lm) > max_winner_members:
                folds_refused_bar += 1
                plan.reasons.pop(loser_id, None)
                continue
            acc |= lm
            kept_folds[loser_id] = winner_id
        plan.fold = kept_folds
    for uid, new_name in plan.rename.items():
        u = by_id.get(uid)
        if u is not None and _uf_id(u) not in plan.fold:
            u.name = new_name
    for loser_id, winner_id in plan.fold.items():
        loser, winner = by_id.get(loser_id), by_id.get(winner_id)
        if loser is None or winner is None:
            continue
        wm = list(getattr(winner, "member_flow_ids", None) or [])
        for m in getattr(loser, "member_flow_ids", None) or []:
            if m not in wm:
                wm.append(m)
        if hasattr(winner, "member_flow_ids"):
            winner.member_flow_ids = wm
            if hasattr(winner, "member_count"):
                winner.member_count = len(wm)
        prev = list(getattr(winner, "previous_names", None) or []) \
            if hasattr(winner, "previous_names") else None
        if prev is not None:
            ln = str(getattr(loser, "name", "") or "")
            if ln and ln not in prev:
                prev.append(ln)
                winner.previous_names = prev
    # fixb121 M6 — self-report BEFORE the mutation. This site was the
    # quietest journey killer on the 8-pair gate (12 of 39 unaccounted): the
    # id-tier lineage ``plan.fold`` IS computed here but thrown away — the
    # telemetry returns only the ``total_folded`` counter, and even that
    # ``phase_finalize`` never stamps. We declare exactly the ids that leave.
    from wystan.pipeline_v2.journey_lineage_audit import (
        report_journey_kill as _report_kill,
    )
    _report_kill(
        "uf_synth_fold.apply_uf_synth_fold",
        [uid for uid in (_uf_id(u) for u in user_flows) if uid in plan.fold],
    )
    user_flows[:] = plan.survivors(user_flows)

    # ── L-C4 FINAL pass — board uniqueness AFTER every pack fold/rename (the
    # wave refutation, 2026-07-16: a fold/rename may land on a name an existing
    # row already carries — twenty 'Manage profile' x2, openstatus 'locale
    # tokens' x2). A collision is resolved by QUALIFICATION with the minimally
    # distinguishing context in parens (PF display > domain > resource > id —
    # the existing qualifier mechanism), NEVER a cross-PF fold. Only pack-
    # eligible rows are ever renamed; markers/synthesized rows are untouchable
    # (when one is in the collision, the real row takes the qualifier).
    pf_disp: dict[str, str] = {}
    for pf in product_features:
        key = str(getattr(pf, "name", "") or "")
        pf_disp[key] = _undressed_pf_display(pf, key)

    def _editable(u: Any) -> bool:
        return (
            not getattr(u, "is_coverage_marker", False)
            and not getattr(u, "synthesized", False)
        )

    def _cap(text: str) -> str:
        t = (text or "").strip()
        return (t[:1].upper() + t[1:]) if t else t

    def _qual_candidates(u: Any) -> list[str]:
        out: list[str] = []
        pfid = str(getattr(u, "product_feature_id", "") or "")
        disp = pf_disp.get(pfid, "")
        if disp:
            out.append(_cap(disp))
        dom = str(getattr(u, "domain", "") or "")
        if dom:
            out.append(_cap(dom))
        res = str(getattr(u, "resource", "") or "")
        if res:
            out.append(_cap(res))
        out.append(str(getattr(u, "id", "") or ""))   # guaranteed-unique terminal
        return [q for q in out if q]

    groups: dict[str, list[Any]] = defaultdict(list)
    for u in user_flows:
        groups[_norm(str(getattr(u, "name", "") or ""))].append(u)
    taken = {k for k, g in groups.items() if g}
    lc4_qualified = 0
    for key, group in sorted(groups.items()):
        if len(group) < 2 or not key:
            continue
        editable = [u for u in group if _editable(u)]
        if not editable:
            continue                     # collision not pack-addressable
        untouchable = [u for u in group if not _editable(u)]
        if untouchable:
            keep = untouchable[0]        # the untouchable row keeps the bare name
        else:
            keep = min(group, key=lambda u: (
                -len(meaning_tokens(str(getattr(u, "name", "") or ""), verbs)),
                -int(getattr(u, "member_count", 0) or 0),
                -len(str(getattr(u, "name", "") or "")),
                str(getattr(u, "id", "") or ""),
            ))
        for u in group:
            if u is keep or not _editable(u):
                continue
            base = str(getattr(u, "name", "") or "")
            for qual in _qual_candidates(u):
                cand = f"{base} ({qual})"
                nk = _norm(cand)
                if nk not in taken:
                    u.name = cand
                    taken.add(nk)
                    lc4_qualified += 1
                    break

    reasons = plan.reasons
    tele: dict[str, Any] = {
        "lc1_echo_folded": sum(1 for r in reasons.values() if r == "lc1_pf_echo"),
        "lc2_stutter_repaired": len(plan.rename),
        "lc3_family_folded": sum(1 for r in reasons.values() if r == "lc3_family_overlap"),
        "lc4_collisions": len(plan.collisions),
        "lc4_qualified": lc4_qualified,
        "total_folded": len(plan.fold),
        "folds_refused_readability_bar": folds_refused_bar,
        # fixb131 Seg C — the id-tier lineage this site has always COMPUTED
        # and thrown away (the fixb121 M6 note names it the worst subclass:
        # 13 of the 8-board gate's rows die here). ``plan.fold`` is exactly
        # ``loser -> winner``; emitting it turns the fold from a count-only
        # writer into an ID-BOUND lineage channel. Sorted by loser id — the
        # set-iteration determinism trap.
        "folded": [
            {"id": lid, "winner": wid,
             "reason": str(reasons.get(lid, "") or "")}
            for lid, wid in sorted(plan.fold.items())
        ],
    }
    # fixb131 Seg A — additive ONLY when the guard is armed, so the OFF hand
    # keeps this dict key-for-key identical (the kill-switch byte-identity
    # gate reads it through scan_meta now that Seg C delivers it).
    if verb_arm_modifier_guard_enabled():
        tele["verb_arm_modifier_refused"] = plan.modifier_refused
    return tele
