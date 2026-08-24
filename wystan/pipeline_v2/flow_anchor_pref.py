"""fixb122 (B1) — callable-preference for a flow's entry anchor.

Root cause (probe M3d-3, VERIFIED on the chatwoot+maybe capture): Stage 3
anchors a flow at ``symbol_to_loc[symbols[0]]`` — the LLM's FIRST listed
symbol, unconditionally. On class-oriented stacks the LLM habitually
lists the container first (``["AccountableSparklinesController", "show"]``,
``["ActionCableBroadcastJob", "perform", ...]``), so the resolver honestly
returns the **class header** and the flow anchors at ``class …`` — a
one-line point span pointing at a declaration, not at the behaviour the
flow is named after. 127 of the 145 residual mis-placed anchors on the
capture are this exact shape (89% of the class).

The mechanism: when — and only when — the resolved symbol is a CONTAINER,
scan ``symbols[]`` in the LLM's own order for the first symbol that
resolves to a CALLABLE **in the same file**, and take its line.

Three properties, each measured before the code was written:

1. **File-pinned by construction.** Only candidates whose
   ``symbol_to_loc`` file equals the already-chosen ``entry_file`` may
   move the line; the file itself NEVER changes. This is not caution, it
   is the difference between a fix and a catastrophe: Stage 3's
   ``symbol_to_loc`` is a per-feature GLOBAL map (first file to declare a
   name wins), and the preferred names are Rails-ubiquitous — ``perform``
   is declared by 271 chatwoot files, ``index`` by 67. Unpinned, 73 of 99
   moves would have re-anchored the flow into a DIFFERENT FILE.

2. **Identity for every flow already anchored on a callable.** The gate
   is the resolved symbol's kind, so a flow whose ``symbols[0]`` is
   already a method/function never enters the branch: 0 of 626 real-def
   rows on the capture move (the regression control).

3. **Inert outside class-symbol stacks.** Measured upper bound on the
   non-Ruby world — a flow can only be touched if a class/module range
   STARTS at its anchor: **0 of 5952** anchors across directus (879),
   lobe-chat (1441) and twenty (3632) qualify. The law is stated
   universally (a container is not a body — the same law
   ``degrade_span.WIDEN_ALLOWED_KINDS`` already encodes for spans) and
   costs nothing where it does not apply; no per-stack branch, no
   per-repo constant, no threshold.

Measured effect when armed (capture, both repos): 99 of 127 class-form
anchors move onto a real ``def`` (chatwoot 46 / maybe 53); the remaining
28 keep their honest class header because the LLM listed no callable.
Flow LOC follows for free — once the anchor sits on a ``def``, the
already-default ``degrade_span`` widening accepts it and stamps the real
body: +582 LOC (chatwoot +282 / maybe +300) with no container ever
swallowed.

Flag: ``WYSTAN_FLOW_ANCHOR_METHOD_PREF``, default **OFF** (armed),
appended to ``scan_result_cache.ENV_OUTPUT_FLAGS`` WITHOUT a KEY_SCHEMA
bump — the bump rides the separate flip commit. Unset ≡ explicit
``0``/``false``/``off``/``no`` ≡ byte-identical to the pre-fix world.

KNOWN, NAMED consequence for whoever composes the flip (measured, not a
surprise): tightening an anchor can reveal that two LLM-named flows are
twins on one method, and Stage 3's own S7-B entry-point dedup then
collapses them. Exactly 2 such pairs exist on the capture —
``chatwoot app/jobs/mutex_application_job.rb:17`` (``acquire-mutex-lock-flow``
survives, ``execute-protected-job-flow`` collapses) and
``maybe app/controllers/transfer_matches_controller.rb:4``
(``create-transfer-match-flow`` survives, ``initialize-transfer-match-flow``
collapses). Both pairs genuinely describe one method. This module does
NOT special-case them: suppressing a correct dedup to protect a row count
would trade truth for a number.
"""

from __future__ import annotations

import os

__all__ = [
    "ANCHOR_METHOD_PREF_ENV",
    "CALLABLE_KINDS",
    "CONTAINER_KINDS",
    "anchor_method_pref_enabled",
    "prefer_callable_entry_line",
]

ANCHOR_METHOD_PREF_ENV = "WYSTAN_FLOW_ANCHOR_METHOD_PREF"

#: Kinds that declare a scope rather than perform work. Only an anchor
#: resolved to one of these may be re-pointed.
CONTAINER_KINDS: frozenset[str] = frozenset({"class", "module"})

#: Kinds that carry behaviour — the Ruby ``def`` grain (``method``) and the
#: TS/JS/Vue/Python grain (``function``). Deliberately excludes the fixb122
#: (A) assoc/scope kinds: a ``has_many`` is a declaration, not a body.
CALLABLE_KINDS: frozenset[str] = frozenset({"method", "function"})


def anchor_method_pref_enabled() -> bool:
    """Default **ON** (flip #28, KS 63). Unset ≡ explicit ``1``;
    explicit ``0`` = kill-switch forever."""
    return os.environ.get(ANCHOR_METHOD_PREF_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def prefer_callable_entry_line(
    symbols: list[str],
    symbol_to_loc: dict[str, tuple[str, int]],
    symbol_kinds: dict[str, str] | None,
    entry_file: str,
    entry_line: int,
) -> int:
    """Return the tightened entry line, or *entry_line* unchanged.

    Args:
        symbols: the LLM's surviving symbol list, in ITS order — the LLM's
            own ranking is the tie-breaker, we only skip containers.
        symbol_to_loc: Stage 3's resolved ``symbol → (file, line)`` map.
        symbol_kinds: the parallel ``symbol → SymbolRange.kind`` map; when
            ``None`` (caller did not collect kinds) the function is a
            no-op, so every existing call path stays byte-identical.
        entry_file: the file already chosen from ``symbols[0]``.
        entry_line: the line already chosen from ``symbols[0]``.

    Returns:
        The line of the first same-file callable symbol when the current
        anchor resolved to a container; otherwise ``entry_line``.
    """
    if not symbols or not symbol_kinds:
        return entry_line
    if symbol_kinds.get(symbols[0]) not in CONTAINER_KINDS:
        return entry_line          # already on a body — never touched
    for symbol in symbols:
        located = symbol_to_loc.get(symbol)
        if located is None or located[0] != entry_file:
            continue               # file-pinned: never cross a file boundary
        if symbol_kinds.get(symbol) in CALLABLE_KINDS:
            return located[1]
    return entry_line              # no callable listed — honest header
