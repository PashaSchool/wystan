"""fixb132 — authored COMPONENT-NAME de-glue for journey (UF) displays.

THE CLASS
=========
Next.js / React repos name their page components ``AdminTeamPage``,
``CohortsPage``, ``PixelShareForm`` — and the journey layer ships that raw
identifier as the journey's NAME. Measured on the umami KS68 board (58 UFs,
63.8% high):

* **Sub-class A — PascalCase glue (19 rows, all medium).** UF-001
  'AdminTeamPage', UF-003 'AdminWebsitesPage', UF-006 'AttributionPage',
  UF-009 'BoardDesignPage', UF-010 'BoardViewPage', UF-011 'BreakdownPage',
  UF-017 'CohortsPage', UF-019 'ComparePage', UF-023 'DashboardViewPage',
  UF-025 'PixelShareForm', UF-026 'EventsPage', UF-028 'FunnelsPage',
  UF-029 'GoalsPage', UF-030 'HeatmapsPage', UF-031 'JourneysPage',
  UF-034 'PerformancePage', UF-039 'ReplayPlayback', UF-041
  'RetentionPage', UF-044 'SessionProfile'. Eighteen of them ARE the whole
  ``shape:raw-identifier`` (C4) census class of that board: Law C graded
  them ``high`` on their own evidence and the R5-5 cap then took the grade
  away — correctly, because the NAME is unreadable. The cap is the honest
  half of the cure; this module is the other half.
* **Sub-class B — '<X> Page' suffix at high (8 rows).** UF-036
  'Preferences Page', UF-037 'Profile Page', UF-043 'Segments Page',
  UF-045 'Sessions Page', UF-046 'Website Settings Page', UF-050 'Teams
  Page', UF-051 'Test Console Page' (the standing B16-P1b exhibit),
  UF-053 'Users Page'. These wear NO shape stamp (no case boundary
  survives the space split) and ship ``high`` with a dev-grain word in the
  display.

THE DOCTRINE LINE (draw it explicitly — this is the load-bearing argument)
=========================================================================
NS-D ("the author's high is sacred") protects the author's PRODUCT
vocabulary: nav labels, marketing phrasing, the words a customer reads.
A CODE IDENTIFIER is NOT product vocabulary — ``AdminTeamPage`` is
implementation naming with exactly the legal status of a route segment,
and the engine already de-glues route segments without anyone calling it
a violation (``uf_name_deglue``, ``route_group_recall._humanize``,
``_strip_uf_devgrain_suffix``'s case rung). So de-gluing an
identifier-shaped journey name does not touch NS-D.

But the DE-GLUED WORDS are authored evidence and are used as such: they
are the row's own declaration of what its surface is about
(``admin/team/page`` -> scope 'admin', resource 'team'), and they feed the
EXISTING rungs — nothing here invents a word the identifier did not carry.

Two guards keep the lane on the right side of the line:

* **identifier-shape FIRST** — only a name that IS an identifier enters.
  A nav-phrased or Title-Case product name ('View webhook', 'Sign up for a
  new account') never reaches the mechanism at all.
* **NS-guard** — a name that matches the authored nav/product phrasing of
  its own PF (``nav_labels_for_pfs`` channels), or that is a canonical
  brand token this module's own casing polish mints
  (``_brand_cased_idents`` — the fixb107 source of truth), is untouchable
  whatever its shape.

MECHANISM (vocab-free where it can be; no new dictionaries)
===========================================================
1. :func:`glued_identifier_shape` / :func:`devgrain_suffix_shape` — the
   two entry shapes.
2. :func:`deglue_display_words` — the SOURCE's own boundaries, read with
   ``uf_name_deglue.deglue_words`` (the one tokenizer the de-glue stack
   already shares) + :func:`strip_lane_devgrain_tail` +
   ``naming_wave_r5.trim_stranded_connective``.
3. Re-derivation through the existing name ladder happens at the CALL
   SITE (``naming_contract._apply_uf_name_laws``), because that is where
   the verb-arm guard, the resource phrase, the view-lead pin and Law C
   live. This module stays pure: no ctx, no I/O, no LLM.

CONFIDENCE
==========
Nothing here writes ``name_confidence``. The lane runs BEFORE Law C
(the B50-deparam / R5-3 precedent), so the row is graded on the name it
actually carries: a de-glued row that grounds both channels earns
``high`` through the ordinary rubric, and a row that grounds only its
resource stays an honest ``medium`` — with a readable name. A row may
legally stay medium; the readable name is the win either way.
"""

from __future__ import annotations

import re
from typing import Iterable, Mapping

from wystan.pipeline_v2.naming_contract import (
    UF_COMPONENT_NAME_DEGLUE_ENV,
    _PF_DEVGRAIN_SUFFIX_TOKENS,
    uf_component_name_deglue_enabled,
)
from wystan.pipeline_v2.uf_name_deglue import deglue_words

#: The flag itself lives beside every other naming flag in
#: ``naming_contract`` (one discoverable registry of env knobs for this
#: stack); it is re-exported here so a caller or a test reads the whole
#: mechanism — predicates AND gate — off a single surface.
__all__ = [
    "UF_COMPONENT_NAME_DEGLUE_ENV",
    "uf_component_name_deglue_enabled",
    "LANE_DEVGRAIN_TOKENS",
    "glued_identifier_shape",
    "identifier_phrase_shape",
    "devgrain_suffix_shape",
    "strip_lane_devgrain_tail",
    "deglue_display_words",
    "nav_phrase_protected",
    "deglue_telemetry_keys",
    "note_renamed_in_scan",
    "renamed_in_scan",
    "reset_renamed_in_scan",
]

#: fixb136 — the SCAN-SCOPED registry of rows THIS SCAN's naming lane
#: renamed. The fold reads it to keep them out of ``fold_exempt_ids``'s
#: blind spot; nothing else may write it.
#:
#: WHY A REGISTRY AND NOT TELEMETRY. The first design shipped the ids as
#: a telemetry key and the keyed channel ate four journeys because of it:
#: on a keyed scan the lane defers to the 6.7e rescore seam, that seam's
#: telemetry reaches ``scan_meta`` through
#: ``stage_6_7e_adjudicator._rescore_tele_view``, and that view copies
#: only ``isinstance(v, (int, float, str, bool))`` — so a LIST of ids was
#: dropped in silence while every sibling counter survived. ``synth_quality``
#: then planned the fold with an EMPTY exemption while the lane's oracle
#: had already released nine rows ON THE PROMISE of that exemption. A
#: promise crossing a filter is not a channel; a module-scoped set that
#: both sides import is.
#:
#: LIFECYCLE (deterministic, single-scan process): cleared once per scan
#: at ``run_naming_contract`` entry — which runs BEFORE every pass that
#: can rename (primary, then the 6.7e rescore seam, then the post-mint
#: hooks) — and read at the fold. Tests clear it explicitly.
_RENAMED_IN_SCAN: set[str] = set()


def note_renamed_in_scan(uf_ids: Iterable[str]) -> None:
    """Record ids a naming lane renamed in this scan (see the registry)."""
    _RENAMED_IN_SCAN.update(str(i) for i in uf_ids if str(i))


def renamed_in_scan() -> frozenset[str]:
    """The ids recorded so far this scan. Empty ⇒ nothing to exempt."""
    return frozenset(_RENAMED_IN_SCAN)


def reset_renamed_in_scan() -> None:
    """Clear the registry — called once per scan by the naming contract."""
    _RENAMED_IN_SCAN.clear()


#: The dev-grain nouns this LANE strips from a trailing position. It is the
#: frozen PF set (``page`` / ``screen`` / ``view`` / ``flow`` — one source of
#: truth, the PF law's own vocabulary, untouched here) plus ``form``, the
#: fourth component-kind suffix the spec names ('PixelShareForm'). The
#: delta is deliberately declared HERE and not pushed into
#: ``_PF_DEVGRAIN_SUFFIX_TOKENS``: that set is read by the PF display laws,
#: and the PF layer is read-only for this pack. Scale-invariant, fixed,
#: universal component vocabulary — corroboration of a shape the case
#: boundary already proved, never a per-repo list.
LANE_DEVGRAIN_TOKENS = frozenset(_PF_DEVGRAIN_SUFFIX_TOKENS | {"form"})

#: The B46 census's ``raw_identifier`` boundary — a lowercase letter
#: immediately followed by an uppercase one, i.e. a code identifier's own
#: word boundary. Same grammar as ``naming_contract._R5_CAMEL_BOUNDARY``
#: (which is what stamps ``shape:raw-identifier``).
_CAMEL_BOUNDARY = re.compile(r"[a-z][A-Z]")

#: ACRONYM boundary (operator ruling, 2026-08-09) — an all-caps run of two
#: or more immediately followed by a capitalised word: ``UTMPage``,
#: ``APIKeysPage``, ``SSOSettingsPage``. umami UF-054 'UTMPage' ships
#: ``high`` and IS the doctrine class, but it carries no ``[a-z][A-Z]``
#: boundary anywhere, so the spec's regex — and therefore the R5-5 rung
#: that stamps ``shape:raw-identifier`` — never saw it. The ruling widens
#: the LANE's detector past the stamping rung deliberately: the shape test
#: decides what is an identifier, and a leading acronym does not make a
#: component name less of one.
#:
#: The trailing lowercase is REQUIRED, so a bare acronym is not
#: identifier-shaped: 'SSO', 'API', 'UTM', 'IoT' declare one word and stay
#: whole. ``uf_name_deglue._WORD_RE`` already reads the same boundary, so
#: the recovery side needed no change at all ('UTMPage' -> utm | page).
_ACRONYM_BOUNDARY = re.compile(r"[A-Z]{2,}[a-z]")

#: A single identifier token: letters/digits only, no separator, no space.
#: ``ReplayPlayback`` matches; ``Test Console Page`` does not (rung B's
#: business); ``robots[.]txt`` does not (route residue is another lane's).
_SINGLE_IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")


def _fold(text: str) -> str:
    """Case/separator-insensitive identity fold ('Ip Allowlist' ==
    'ipallowlist'). Mirrors ``naming_contract._ident_fold``; kept local so
    this module imports one private name from the contract, not two."""
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


def glued_identifier_shape(
    name: str, *, brands: Iterable[str] = (),
) -> bool:
    """Sub-class A — the display IS a single glued code identifier.

    Three conjuncts, each of them load-bearing:

    * **single token** — no whitespace, letters/digits only. A multi-word
      display is a phrase; whatever is wrong with it belongs to the phrase
      rungs (R5-3 split-core, the brand-echo cap), not here. This is also
      what keeps the lane away from 'Browse & manage CircleCI authorize':
      a camel boundary inside ONE word of a real phrase is the fixb107
      brand class, and this rung never sees it.
    * **a case boundary** — camel (``[a-z][A-Z]``) or acronym
      (``[A-Z]{2,}[a-z]``, the 2026-08-09 ruling): the identifier declares
      its own words. A flat ``ipallowlistpage`` declares none, so there is
      nothing to recover and the R5 glued-identifier cap keeps judging it
      (invent nothing).
    * **not a brand token** — a name whose fold is a canonical vendor
      casing this module's own polish mints ('GitHub', 'PostgreSQL',
      'ClickHouse') is product vocabulary, not a leak. Same one-source-of-
      truth vocabulary the fixb107 shape exemption reads.
    """
    text = str(name or "").strip()
    if not text or not _SINGLE_IDENT.match(text):
        return False
    if not (_CAMEL_BOUNDARY.search(text) or _ACRONYM_BOUNDARY.search(text)):
        return False
    if len(deglue_words(text)) < 2:
        return False
    return _fold(text) not in {_fold(b) for b in brands}


def identifier_phrase_shape(
    name: str, *, brands: Iterable[str] = (),
) -> bool:
    """Sub-class C — EVERY whitespace token is a glued code identifier
    ('AdminWebsitesPage WebsitesPage', 'SessionsPage SessionProfile',
    'AdminTeamPage TeamsSettingsPage', 'UsersPage UserPage').

    Measured on the keyed umami OFF/ON pair (2026-08-09): the Stage 6.7e
    LLM adjudicator is a SECOND writer of this same class, and on the ON
    arm — where this pack had already repaired 17 rows, so the
    adjudicator's low-confidence SELECTION shrank 34 -> 17, its batching
    3 -> 2, its cache went 3 hits -> 0 and it drew two fresh completions —
    its rename verdicts composed member component names into the four
    displays above. They are not this lane's output (the lane's own
    telemetry names exactly the 17 rows it renamed), but they ARE this
    lane's class, and a pack that cleans glue only where it happens to
    appear first is not a mechanism.

    The rung is the strict conjunction of rung A over every token, so it
    cannot reach a real phrase: 'Browse & manage CircleCI authorize' fails
    on 'Browse' (no camel boundary), on '&' (not an identifier) and on
    'authorize'. One non-identifier word anywhere shuts the rung.
    """
    tokens = str(name or "").split()
    if len(tokens) < 2:
        return False
    return all(glued_identifier_shape(t, brands=brands) for t in tokens)


def devgrain_suffix_shape(
    name: str, *, lead_is_verb: bool, resource_tokens: Iterable[str] = (),
    pf_display: str = "",
) -> bool:
    """Sub-class B — a Title-Case phrase whose TRAILING word is a dev-grain
    component kind echoing the row's own surface ('Teams Page', 'Test
    Console Page', 'Website Settings Page').

    Guards:

    * **>= 2 words and >= 1 survivor** — 'Page' alone is not a name, and a
      strip may never leave an empty display.
    * **not verb-led** — a verb-led 'View detections page' is the banked
      ``_strip_uf_devgrain_suffix`` law's row (anchor-form gated) and the
      'Publish page' anti-case's row. This lane does not relitigate either;
      it takes only the noun-phrase shape that law cannot reach.
    * **surface echo** — the surviving words must overlap the row's OWN
      resource phrase. That is the spec's "echoing its entry component /
      route" clause made mechanical: a trailing 'Page' on a phrase whose
      remainder names something else is not a component-name leak, it is
      somebody else's noun and this lane has no business in it.
    * **the author did not name it that** — when the row's HOME PF display
      itself ends in the same word ('Status Page', 'Share Secret Page' —
      the infisical anti-cases the B16-P1b law protects), 'Page' is the
      product's own vocabulary, not a component leak. NS-D outranks the
      shape: the strip is refused.
    """
    words = str(name or "").split()
    if len(words) < 2 or lead_is_verb:
        return False
    tail = words[-1].strip().lower()
    if tail not in LANE_DEVGRAIN_TOKENS:
        return False
    pf_words = str(pf_display or "").split()
    if pf_words and pf_words[-1].strip().lower() == tail:
        return False
    survivors = words[:-1]
    if not survivors:
        return False
    res = {str(t).lower() for t in resource_tokens if t}
    if not res:
        return False
    surv = {re.sub(r"[^a-z0-9]+", "", w.lower()) for w in survivors}
    surv = {w for w in surv if w}
    return bool(surv & res) or bool(
        {w[:-1] for w in surv if w.endswith("s") and len(w) > 3} & res)


def strip_lane_devgrain_tail(words: list[str]) -> list[str]:
    """Drop EVERY trailing dev-grain noun while at least one word survives,
    over this lane's token set (see :data:`LANE_DEVGRAIN_TOKENS`). Never
    touches a dev-grain word that is not final ('Landing Page Builder' is
    safe by construction).

    EVERY, not one — measured. ``uf_name_deglue.strip_devgrain_tail`` drops
    a single word because its callers compose from a route/dir segment that
    carries at most one; a COMPONENT identifier stacks them
    ('DashboardViewPage' -> dashboard/view/page), and a one-word strip
    shipped 'Browse dashboard view', which the B16-P1b obstacle-course row
    flagged on the ON board — this lane resurrecting the very class it
    exists to kill. The comparison-side ``naming_contract._strip_devgrain_
    words`` already folds the whole tail; this is that same fold with the
    phrase floor kept."""
    out = list(words)
    while len(out) >= 2 and str(out[-1]).lower() in LANE_DEVGRAIN_TOKENS:
        out = out[:-1]
    return out


def deglue_display_words(
    name: str, *, camel_split: bool, per_token: bool = False,
) -> list[str]:
    """Lowercase evidence words of an identifier-shaped display.

    ``camel_split`` (rung A) reads the token's OWN case boundaries through
    ``uf_name_deglue.deglue_words`` — the single tokenizer the de-glue
    stack shares. Rung B passes ``False``: its words are already separate,
    and camel-splitting them would damage a vendor casing standing INSIDE
    the phrase ('CircleCI' -> 'circle ci'), which is precisely the harm the
    fixb130 blast census measured and refused.

    ``per_token`` (rung C) treats EACH whitespace token as its own
    identifier — de-glued and dev-grain-stripped on its own — before the
    words are joined. That is what the shape means: 'SessionsPage
    SessionProfile' is two components, so its dev-grain word is interior to
    the phrase and a tail-only strip would ship 'sessions page session
    profile'. Per token it reads sessions | session profile, and the
    adjacent-echo fold below collapses the restatement.

    Every rung then takes the dev-grain strip, the adjacent-echo fold
    (``naming_contract._deglue_echo_tokens`` — the SAME singular-folded
    dup/tail-echo primitive the display de-grime uses, never a second copy)
    and the stranded-connective trim.
    """
    from wystan.pipeline_v2.naming_contract import _deglue_echo_tokens
    from wystan.pipeline_v2.naming_wave_r5 import trim_stranded_connective

    if per_token:
        words: list[str] = []
        for part in str(name or "").split():
            words.extend(strip_lane_devgrain_tail(deglue_words(part)))
    elif camel_split:
        words = deglue_words(name)
    else:
        words = [
            w for w in (
                re.sub(r"[^A-Za-z0-9]+", "", part).lower()
                for part in str(name or "").split()
            ) if w
        ]
    return trim_stranded_connective(
        strip_lane_devgrain_tail(_deglue_echo_tokens(words)))


def nav_phrase_protected(
    name: str, nav_labels: Iterable[str],
) -> bool:
    """NS-guard — the display echoes an AUTHORED nav/product label of its
    own PF, so it is the maintainer's vocabulary whatever its shape.

    Folded comparison in both directions (a label 'Websites' protects a
    display 'websites'), and containment-safe: a nav label that CONTAINS
    the whole display ('Admin — Teams' vs 'Teams') is still the author
    naming this surface. Empty label set ⇒ never protected."""
    folded = _fold(name)
    if not folded:
        return False
    for lab in nav_labels or ():
        lf = _fold(lab)
        if not lf:
            continue
        if lf == folded or folded in lf or lf in folded:
            return True
    return False


def deglue_telemetry_keys() -> Mapping[str, int]:
    """The telemetry block this lane owns (declared in one place so the
    ARMED hand's keys can never drift from the OFF hand's absence)."""
    return {
        "uf_component_deglued": 0,
        "uf_component_deglue_glued": 0,
        "uf_component_deglue_devgrain": 0,
        "uf_component_deglue_phrase": 0,
        "uf_component_deglue_verb_authored": 0,
        "uf_component_deglue_verb_member": 0,
        "uf_component_deglue_verbless": 0,
        "uf_component_deglue_nav_protected": 0,
        "uf_component_deglue_collision_skipped": 0,
        "uf_component_deglue_law_refused": 0,
        "uf_component_deglue_fold_refused": 0,
        "uf_component_deglue_unattested": 0,
    }
