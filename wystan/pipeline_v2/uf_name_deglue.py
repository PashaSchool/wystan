"""B102 Seg B — de-glue a leaked code identifier into product words, and
strip the dev-grain tail, at the UF-name producers that bypass the naming
contract (``uf_cases_split`` children, ``route_group_recall`` re-mints).

THE BUG
=======
Both producers compose a display name from a directory/component basename
without any word-splitting:

* ``uf_cases_split._child_key`` tokenizes with ``_TOKEN_RE.split(last.lower())``
  — it lowercases BEFORE splitting and ``_TOKEN_RE`` only breaks on
  non-alphanumerics, so ``IpAllowlistPage`` collapses to the single glued
  token ``ipallowlistpage``. The camelCase boundary — the repo's OWN word
  evidence — is destroyed before any splitter could read it. Exhibits
  (infisical ON): 'Manage ipallowlistpage' (name_confidence **high**),
  'Manage nativeintegrationstab', 'Manage accessapprovalrequest',
  'Manage approvalpolicylist', 'Manage compareenvironments',
  'Manage environmentsection', 'Manage secretdropzone', 'Manage
  secretlistview', 'Manage secretoverviewtablerow', 'Manage secretsearchinput',
  'Manage secretsyncdestinationcol', 'Manage secrettablerow',
  'Manage workflowintegrationsection' — 78 of 87 CS rows in the ON hand.
* ``route_group_recall._humanize`` only maps ``[-_]+`` to spaces, so a
  PascalCase group dir ships verbatim: 'Browse & manage
  AccountRecoveryResetPage', 'Browse & manage AlertingPage', and — after the
  contract's casing polish — UF-185 'Manage resource overview page' with no
  dev-grain strip (PF 'Overview Page').

WHY THE EXISTING HELPERS DO NOT REACH
=====================================
``naming_contract._strip_uf_devgrain_suffix`` is ANCHOR-FORM gated: it fires
only when the home PF's route anchor's terminal dir segment ends ``-<word>``
('policy-page' -> 'Policy'). These producers' anchors are PascalCase
component dirs with no hyphen ('…/ResourceOverviewPage'), so the gate never
opens. ``naming_wave_r5.derive_split_display`` IS the repo-own-evidence
splitter, but its separator-ratio rule deliberately refuses to split
non-verb-led camel-only tokens (the Deepseek / Hitpay / Qrcode anti-cases) —
correct for ITS lane (splitting an already-emitted single token with no
case evidence), wrong for ours, where the ORIGINAL segment still carries the
case boundary and we simply must not throw it away.

MECHANISM (vocab-free)
======================
:func:`deglue_words` reads the SOURCE segment's own boundaries — camelCase,
PascalCase, ALL-CAPS runs, digits, ``-``/``_`` — and returns lowercase words.
It invents nothing: if the segment carries no boundary (a genuinely flat
``ipallowlistpage`` directory) it returns the token unchanged, and the row is
then capped by the R5 glued-identifier rung rather than relabeled.

The dev-grain tail strip reuses ``naming_contract._PF_DEVGRAIN_SUFFIX_TOKENS``
(the SAME fixed 4-word set — one source of truth, no second vocabulary) and
mirrors the UF law's ≥3-word rule: the phrase keeps at least one object word
so a strip can never leave a bare verb.

Everything here is a pure function of its arguments — no ctx, no I/O, no LLM.

B102 SEG-B RESIDUE — WHAT v2 ADDS (fixb103)
===========================================
The warden's re-judge (2026-08-04) measured the Seg-B landing on the fresh
keyed infisical ON board: tail-glue 78/87 -> 30/71, glued-high 15/16 -> 6.
The two survivors both live OUTSIDE the tail the v1 helpers reach:

* **LEAD position.** ``uf_cases_split._child_verb_word`` falls back to
  *the parent's own leading word* when no action family reaches a strict
  majority — and its docstring's premise ("it already ships law-clean on
  the board") is FALSE when the parent itself wears a glued identifier.
  infisical ON parent ``UF-204`` is literally named
  ``'settingspage component projectsshtabs'``, so 36 children inherited
  the glued lead ``Settingspage`` — SIX of them ``high``
  (``UF-CS-b7ae62d4de`` 'Settingspage pam account policies',
  ``UF-CS-3accdbf16b`` 'Settingspage pam sessions', ``UF-CS-40cf5e85d8``
  'Settingspage projects', ``UF-CS-d138c16bef`` 'Settingspage SSH cas',
  ``UF-CS-2fee33e795`` 'Settingspage SSH certs', ``UF-CS-d9f62e134b``
  'Settingspage SSH host group details by'). :func:`deglue_lead_word`
  recovers the boundary from the members' own entry PATHS (the case
  survives there: ``.../organization/SettingsPage/...``) — the same
  "read the source's own boundaries, invent nothing" mechanism, just
  pointed at the path evidence instead of a single leaf segment.
* **Stranded connective.** The de-glued phrase legitimately ends
  ``... details by id``; ``naming_contract._drop_standalone_addr``
  (Seg2) then drops the standalone addressing token ``id`` and leaves the
  connective ``by`` hanging: 'Settingspage SSH host group details by'
  (high), 'Manage installation details by', 'Manage pki subscriber
  details by'. :func:`trim_stranded_connective` trims it, reusing
  ``naming_wave_r5._CONNECTORS`` — the EXISTING connective vocabulary,
  never a second list.

Both v2 rungs ride ``WYSTAN_UF_POSTMINT_RESCORE`` (the pack flips as
one unit — a regraded row wearing a glued name is the exhibit); the
callers own the gate, these helpers stay pure.
"""

from __future__ import annotations

import re
from typing import Iterable

from wystan.pipeline_v2.naming_contract import _PF_DEVGRAIN_SUFFIX_TOKENS
#: Re-exported so the de-glue callers read the trim from this module's own
#: surface; the primitive lives beside ``_CONNECTORS`` in ``naming_wave_r5``
#: (one connective vocabulary, and ``naming_contract`` — which also needs it
#: at the Seg2 seam — must not import back into this module).
from wystan.pipeline_v2.naming_wave_r5 import trim_stranded_connective

#: Word boundaries a source identifier declares about ITSELF: an ALL-CAPS run
#: not followed by lowercase (``API``), a capitalised word (``Allowlist``),
#: or a lowercase/digit run. Mirrors ``naming_wave_r5._WORD_RE`` — the same
#: tokenizer the R5 evidence engine uses (anti-drift: one grammar, not two).
_WORD_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+")


def deglue_words(segment: str) -> list[str]:
    """Lowercase product words declared by ``segment``'s own case/separator
    boundaries. Returns ``[]`` for empty input; returns a single word when the
    segment declares no boundary (nothing is invented)."""
    return [w.lower() for w in _WORD_RE.findall(str(segment or "")) if w]


def is_glued(segment: str) -> bool:
    """True when ``segment`` is a single alphabetic run of some length that
    declares NO internal boundary — the shape that cannot be de-glued from
    the source alone ('ipallowlistpage'). Scale-invariant: no per-repo list,
    no length tuned to a corpus — a one-word segment either carries a
    boundary or it does not."""
    words = deglue_words(segment)
    return len(words) == 1 and str(segment or "").strip().isalpha()


def deglue_key_token(token: str, source_segment: str) -> list[str]:
    """De-glue one KEY token using the original segment that produced it.

    The key is identity (it seeds the child's id / domain / grouping) and is
    NEVER rewritten. Only the DISPLAY is recovered: the token is located
    case-insensitively inside ``source_segment`` and that slice — which still
    carries its case boundaries — is split. Falls back to the token itself
    when the segment does not contain it.
    """
    tok = str(token or "")
    seg = str(source_segment or "")
    if not tok:
        return []
    idx = seg.lower().find(tok.lower())
    if idx < 0:
        return [tok.lower()]
    return deglue_words(seg[idx:idx + len(tok)]) or [tok.lower()]


def strip_devgrain_tail(words: list[str]) -> list[str]:
    """Drop ONE trailing dev-grain noun (page/screen/view/flow) when at least
    one object word survives — the phrase-level mirror of the UF devgrain law
    (which requires verb+object+devgrain, i.e. an object must remain so the
    composed name is never a bare verb). Never touches a dev-grain word that
    is not final ('Landing Page Builder' is safe by construction)."""
    if len(words) >= 2 and words[-1] in _PF_DEVGRAIN_SUFFIX_TOKENS:
        return words[:-1]
    return words


def deglue_lead_word(word: str, sources: Iterable[str]) -> str:
    """Recover a glued LEAD word's product words from the first ``sources``
    entry that still carries the case boundary.

    ``uf_cases_split._child_verb_word`` returns the PARENT's leading word
    when no action family holds a majority; when that parent word is itself
    a lowercased code identifier ('settingspage'), the child inherits it.
    The boundary is not lost — it survives in the members' entry PATHS
    (``.../organization/SettingsPage/PamAccountPoliciesPage.tsx``) — so the
    word is located case-insensitively inside each source's path SEGMENTS
    and that slice is split by :func:`deglue_words`.

    ``('settingspage', ['frontend/src/pages/organization/SettingsPage/x.tsx'])``
    -> ``'settings page'``; a word no source can resolve is returned
    unchanged (nothing invented — the R5 glued-lead cap then judges it).
    Segments are matched WHOLE (a segment that merely contains the word as
    a substring, e.g. ``SettingsPageHeader``, still yields the word's own
    slice; a source with no such segment contributes nothing)."""
    tok = str(word or "").strip()
    if not tok or not tok.isalpha():
        return str(word or "")
    low = tok.lower()
    for src in sources or ():
        for seg in re.split(r"[/\\]", str(src or "")):
            seg = seg.split(".", 1)[0]
            if not seg or low not in seg.lower():
                continue
            words = deglue_key_token(tok, seg)
            if len(words) > 1:
                return " ".join(words)
    return tok


def deglue_phrase(key: str, source_segment: str) -> str:
    """Display phrase for a ``-``-joined identity key, recovered from the
    source segment and stripped of its dev-grain tail.

    ``('ipallowlistpage', 'IpAllowlistPage')`` -> ``'ip allowlist'``
    ``('nativeintegrationstab', 'NativeIntegrationsTab')`` -> ``'native integrations tab'``
    ``('ipallowlistpage', 'ipallowlistpage')`` -> ``'ipallowlistpage'`` (no
    boundary to read — the R5 glued rung caps the row instead of relabeling).
    """
    words: list[str] = []
    for tok in str(key or "").split("-"):
        if tok:
            words.extend(deglue_key_token(tok, source_segment))
    return " ".join(
        trim_stranded_connective(strip_devgrain_tail(words)))


def humanize_group_noun(noun: str) -> str:
    """``route_group_recall`` display noun: de-glue + dev-grain strip.

    ``'AccountRecoveryResetPage'`` -> ``'account recovery reset'``
    ``'resource-overview-page'``   -> ``'resource overview'``
    """
    return " ".join(
        trim_stranded_connective(strip_devgrain_tail(deglue_words(noun))))
