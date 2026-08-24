"""M3a — span widening for the unsupported-stack DEGRADE branch (fixb115).

Root cause (probe P13, VERIFIED over 20 fresh KS60 boards):
:mod:`expander` stamps a **one-line** span for every flow whose entry file
suffix is outside ``_T1_SUPPORTED_SUFFIXES`` (``.rb`` / ``.vue`` / ``.php``
/ ``.java`` …)::

    lines = (entry_line, entry_line)   # expander.py, degrade branch

That is 977 of the world's 1652 point-anchor flows (59.1%, class A —
chatwoot 675 + directus 302); the remaining 40.9% (class B) are HONEST T1
abstains where the supported-stack D1 recovery already ran and correctly
found nothing (documenso 0/39, core-redplanet 0/131). Class B is NOT this
module's business — the degrade branch is unreachable for T1 suffixes, so
those flows stay byte-identical by construction.

The fix reuses the engine's OWN span machinery rather than inventing a
convention: :func:`call_graph._entry_range_containing_line` — the same
"innermost symbol range that brackets ``entry_line``" contract T1 stacks
get from D1 — over ``rctx.signatures``, which ``build_reach_context``
already populates for ``.rb`` (``_parse_ruby_file``) and ``.vue``
(``_parse_vue_file``). No new data source, no threshold, no multiplier, no
per-repo constant.

Three guards, each a NAMED probe finding (P13 §4 tuning parameters):

1. **kind whitelist** — only ``method`` / ``function`` ranges may widen a
   point span. A ``class`` / ``module`` range is a container, not a
   handler body: chatwoot ``create-access-token-flow`` anchors at line 1 of
   a controller whose every ``def`` is commented out, so the only
   bracketing range is the class itself and the flow would swallow the
   WHOLE 44-line file. Abstaining there costs 49 of 648 chatwoot
   recoveries and buys back the degenerate exhibit.
2. **re-export distrust** — ``kind == "reexport"`` is excluded explicitly.
   :func:`call_graph.build_call_graph` already treats a re-export range as
   FAKE (its ``entry_resolved_real`` guard) because the MVP range
   heuristic gives ``export { X } from './Y'`` an end of
   *next-export-start − 1*, spanning unrelated gaps; the shared helper
   itself carries no such guard. The whitelist in (1) already excludes it —
   the explicit set states the law so a future whitelist widening cannot
   silently re-admit it (webstudio ``navigate-tabs-src-4-flow`` barrel
   anti-case).
3. **fallback = the status quo** — when no range brackets the line, or the
   bracketing range is a rejected kind, or the file has no signature, the
   caller keeps its existing ``(entry_line, entry_line)`` point span. Every
   abstain is counted under a named sub-class, never a silent whole-file
   grab.

Flag: ``WYSTAN_SPAN_WIDEN_DEGRADE``, default **OFF** (armed), appended
to ``scan_result_cache.ENV_OUTPUT_FLAGS`` WITHOUT a KEY_SCHEMA bump (the
bump rides a separate flip commit). Explicit ``0``/``false``/``off``/``no``
≡ unset ≡ byte-identical to the pre-fix world.

Measured coupling with ``WYSTAN_RUBY_DEF_SPANS`` (fixb115 item 2) —
IMPORTANT for whoever composes the flip pack
--------------------------------------------------------------------
The widened span is only as honest as the ``symbol_ranges`` it reads. On
``.rb`` the LEGACY ranges ("end = next symbol's start − 1") are exact for
just 4.52% of methods (measured against the ruby interpreter's own AST on
chatwoot, 7101 methods): starts sit one line ABOVE the ``def`` and the
last symbol of each file runs past EOF. Arming this flag ALONE therefore
widens a lot (chatwoot 599 of 675 class-A flows, sum owned LOC 675 →
5357, replay-VERIFIED) but stamps boundaries that are mostly off by a
line at each end.

Arming ``WYSTAN_RUBY_DEF_SPANS`` too makes both the SPAN and the
ANCHOR honest (Stage 3 derives a routed entry's line from the same
``symbol_ranges``), and the chatwoot recovery projects to 560 flows with
physically correct bodies. On a board minted BEFORE the ruby flag (stale
anchors one line above the real ``def``) the same arming recovers only
113 — the anchors no longer bracket anything. Practical consequence:
these two flags belong in the SAME flip wave, and the wave's proof scan
must be a fresh scan, not a replay over pre-flip anchors. ``.vue``
(directus: 274/274 recoveries, kind=function) is unaffected — its parser
already produced real bodies.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from wystan.pipeline_v2.flow_expansion.call_graph import (
    _entry_range_containing_line,
)

if TYPE_CHECKING:
    from wystan.analyzer.ast_extractor import FileSignature

__all__ = [
    "SPAN_WIDEN_DEGRADE_ENV",
    "WIDEN_ALLOWED_KINDS",
    "WIDEN_DISTRUSTED_KINDS",
    "DegradeWidenConfig",
    "WidenResult",
    "degrade_widen_enabled",
    "kind_accepted",
    "widen_entry_span",
]

SPAN_WIDEN_DEGRADE_ENV = "WYSTAN_SPAN_WIDEN_DEGRADE"

#: Guard (1) — symbol kinds that may carry a flow's body span. ``method``
#: is the Ruby ``def`` grain, ``function`` the Vue ``<script setup>`` /
#: options-API handler grain: together 599/648 of the chatwoot recoveries
#: and 274/274 of the directus ones. Containers (``class`` / ``module``)
#: and data (``const`` / ``local`` / ``type``) never widen.
WIDEN_ALLOWED_KINDS: frozenset[str] = frozenset({"method", "function"})

#: Guard (2) — kinds the engine already treats as FAKE ranges (the
#: ``entry_resolved_real`` law in :func:`call_graph.build_call_graph`).
#: Redundant with the whitelist by construction; stated so it survives any
#: future whitelist change.
WIDEN_DISTRUSTED_KINDS: frozenset[str] = frozenset({"reexport"})

#: Named abstain sub-classes (telemetry; an abstain is always an honest
#: keep-the-point-span, never a whole-file grab).
SKIP_NO_SIGNATURE = "no_signature"
SKIP_NO_BRACKETING_RANGE = "no_bracketing_range"
SKIP_KIND_REJECTED = "kind_rejected"


def _truthy(env: str) -> bool:
    # Flip-pack #26 (KS61): unset ≡ ON; an explicit off = kill-switch.
    return os.environ.get(env, "1").strip().lower() in {"1", "true", "yes", "on"}


def degrade_widen_enabled() -> bool:
    """Widening armed — default **OFF**.

    ``WYSTAN_SPAN_WIDEN_DEGRADE`` truthy arms it; unset / explicit
    ``0``/``false``/``off``/``no`` is the kill-switch (unset ≡ explicit
    ``0``, byte-identical).
    """
    return _truthy(SPAN_WIDEN_DEGRADE_ENV)


@dataclass(frozen=True)
class DegradeWidenConfig:
    """Per-scan arming for the degrade-branch widening, read ONCE."""

    enabled: bool = False

    @classmethod
    def from_env(cls) -> "DegradeWidenConfig":
        return cls(enabled=degrade_widen_enabled())


@dataclass(frozen=True)
class WidenResult:
    """Outcome of one widening attempt.

    ``lines`` is the widened span, or ``None`` when the caller must keep
    its point span; ``skip`` names the abstain sub-class (``None`` on a
    successful widen).
    """

    lines: tuple[int, int] | None = None
    skip: str | None = None


def kind_accepted(kind: str | None) -> bool:
    """Guards (1)+(2) as one predicate over a ``SymbolRange.kind``.

    Distrusted kinds are rejected FIRST (so the law reads in the order the
    probe stated it), then the whitelist decides.
    """
    if kind in WIDEN_DISTRUSTED_KINDS:
        return False
    return kind in WIDEN_ALLOWED_KINDS


def widen_entry_span(
    sig: "FileSignature | None",
    entry_line: int | None,
) -> WidenResult:
    """Widen a degrade-branch point anchor to its enclosing body span.

    Returns a :class:`WidenResult` whose ``lines`` is the innermost
    ``method``/``function`` range bracketing ``entry_line``, or a named
    abstain. Deterministic: no LLM, no IO (the signature is already built
    by ``build_reach_context``), no repo-specific path.
    """
    if entry_line is None:
        return WidenResult(skip=SKIP_NO_BRACKETING_RANGE)
    if sig is None:
        return WidenResult(skip=SKIP_NO_SIGNATURE)
    lines = _entry_range_containing_line(sig, entry_line, kind_ok=kind_accepted)
    if lines is not None:
        return WidenResult(lines=lines)
    # Abstain classification (telemetry only, off the hot path): was there
    # a bracketing range at all, or did the kind guards reject it?
    unguarded = _entry_range_containing_line(sig, entry_line)
    return WidenResult(
        skip=SKIP_KIND_REJECTED if unguarded is not None
        else SKIP_NO_BRACKETING_RANGE,
    )
