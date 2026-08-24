"""Stage 6.97d — deterministic User-Flow engineering metrics ($0, output layer).

Operator gap (2026-07-31): product features carry the full engineering
metric family (``health_score`` / ``health_confidence`` / ``bug_fix_ratio``
/ ``bug_fixes`` / ``total_commits`` / ``authors``) but journeys carry ONLY
``loc`` (Stage 6.97b) + ``coverage_pct`` — "why don't I see metrics for
user flows?". This stage stamps the SAME metric family onto every eligible
``UserFlow``, mirroring the ``Feature`` field names for UI consistency.

PROPORTIONAL SPAN-CREDIT (the lead-ruled mechanism)
---------------------------------------------------
The $0 prototype (RefApp, 81 journeys) refuted naive whole-file credit: a
member flow that owns a 30-line sliver of a 4000-line shared-infra file
(``backend/database.py``, 236 commits) inherited the file's ENTIRE commit
history — 34/80 journeys exceeded their home PF's commit count, the median
journey had 77% of its credit from one file, and 45% of journeys converged
into one indistinct health band. The cure is proportional ownership credit:

    weight(uf, file) = owned_lines(uf, file) / total_lines(file)   (cap 1.0)
    total_commits(uf) = round( Σ_file file_commits × weight )
    bug_fixes(uf)     = round( Σ_file file_bug_commits × weight )
    bug_fix_ratio     = Σ bug_commits×w / Σ commits×w   (unrounded operands)

``owned_lines`` is the per-file UNION of the journey's member-flow OWNED
spans — exactly Stage 6.97b's selection (:func:`flow_owned_spans` +
:func:`union_span_len` are imported, not re-derived), so the LOC a journey
displays and the churn it is charged for come from the SAME span ledger.
The denominator is the file's TOTAL line count on disk (the scan checkout)
— deliberately NOT the union of all journeys' claimed lines: normalizing by
claimed lines hands a file's sole claimant 100% of a mega-file's churn
(measured: it left all 34/80 subset violations standing, while the
total-lines denominator cut them to 13/80 with small, explainable
residuals). Scale-invariant, no thresholds, no magic numbers.

Shared spans stay credited to EVERY journey that owns them (the
flow-feature-concept sharing canon) — proportionally to each journey's
ownership share, never as a double full count. ``health_basis`` is stamped
``"span-weighted"`` on every metric-carrying row so the display layer can
label the mechanism honestly (the canon's "file-level fallback must be
labelled" clause, upgraded to the weighted mechanism).

Health / confidence
-------------------
``health_score`` reuses :func:`wystan.analyzer.features._calculate_health`
(the sigmoid the features use) over the weighted inputs, with ``commits=None``
— the age-decay arm needs whole unweighted commit lists, which would smuggle
whole-file credit back into the ratio. ``health_confidence`` reuses
:func:`wystan.pipeline_v2.stage_6_metrics._health_confidence_floor`
(P25 of nonzero weighted counts — scale-invariant) with the same
insufficient/low/high ladder as ``_finalize_feature_metrics``. A journey
whose weighted credit rounds to 0 gets the exact mint-null convention
(``total_commits=0`` / ``bug_fixes=0`` / ``ratio=0.0`` / ``health=100.0`` /
``"insufficient"`` / ``authors=[]``) — never the "impossible row"
``tc=0 ∧ authors>0`` pattern the metrics-recompute syncs.

``authors`` on credit-bearing rows is the plain union of commit authors
over the journey's weight>0 files (the lead's ruling: the author LIST needs
no quantitative weighting), sorted for determinism.

Honest None, three ways
-----------------------
- ``is_coverage_marker`` rows: a coverage placeholder must never wear
  synthetic health — every metric field stays ``None`` (serializer omits).
- Journeys without ``member_flow_ids``: no span ledger → ``None``.
- Journeys whose members resolve to zero owned spans: ``None``.

Performance guard
-----------------
No git subprocess runs here: churn comes from the ONE pre-loaded
``ctx.commits`` list (Stage 0) swept ONCE, and file line counts are read
from disk ONCE per distinct file (an in-scan cache dict), aggregated across
all journeys. Telemetry carries ``duration_ms`` + counter fields.

Additivity / kill-switch
------------------------
``WYSTAN_UF_METRICS`` default **OFF**: unset / ``0`` / ``false`` skips
the stage entirely — every new field stays ``None`` and the serializer
omits it, byte-identical to the pre-stage engine. Registered in
``ENV_OUTPUT_FLAGS`` (no KEY_SCHEMA bump — that rides a flip commit only).
Deterministic: list-ordered UF iteration, sorted file/author iteration, no
set iteration on any counted path. No LLM, no network.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from wystan.analyzer.features import _calculate_health
from wystan.pipeline_v2.stage_6_97b_uf_loc import (
    flow_owned_spans,
    union_span_len,
)
from wystan.pipeline_v2.stage_6_metrics import _health_confidence_floor

if TYPE_CHECKING:
    from wystan.models.types import Commit

__all__ = [
    "STAGE_6_97D_ENV_FLAG",
    "HEALTH_BASIS_LABEL",
    "uf_metrics_enabled",
    "uf_owned_lines_by_file",
    "count_file_lines",
    "apply_uf_metrics",
]

STAGE_6_97D_ENV_FLAG = "WYSTAN_UF_METRICS"

# The honest mechanism label stamped on every metric-carrying journey —
# display layers surface it verbatim ("span-weighted" churn credit).
HEALTH_BASIS_LABEL = "span-weighted"


def uf_metrics_enabled() -> bool:
    """Default **ON** since the 2026-07-31 flip-pack №14 flip (KEY_SCHEMA 49;
    keyed proof: RefApp UF-metrics 86/86 journeys stamped).

    Unset now arms the stage; explicit ``0`` (or ``false``/``False``/empty)
    stays a kill-switch forever — inert, byte-identical output. Only the
    ``os.environ.get`` default moved ``"0"`` -> ``"1"``; the off-set
    {"0","false","False",""} is preserved LITERALLY.
    """
    return os.environ.get(STAGE_6_97D_ENV_FLAG, "1").strip() not in {
        "0", "false", "False", "",
    }


def uf_owned_lines_by_file(
    uf: Any,
    flow_by_key: dict[str, Any],
) -> dict[str, int]:
    """Per-file OWNED line counts for one journey.

    The per-file UNION of the journey's member flows' owned spans —
    Stage 6.97b's exact selection (``flow_owned_spans`` excludes
    ``role="interior"`` nodes + ``shared_paths``-ledger files; overlapping
    member spans merge, never double-count). Empty dict when nothing
    resolves (member-less / span-less journeys).
    """
    spans_by_file: dict[str, list[tuple[int, int]]] = {}
    for mid in (getattr(uf, "member_flow_ids", None) or []):
        fl = flow_by_key.get(mid)
        if fl is None:
            continue
        for path, s, e in flow_owned_spans(fl):
            spans_by_file.setdefault(path, []).append((s, e))
    return {p: union_span_len(spans_by_file[p]) for p in sorted(spans_by_file)}


def count_file_lines(repo_path: Path, rel_path: str) -> int | None:
    """Total line count of ``rel_path`` under ``repo_path``; ``None`` when
    the file is unreadable/absent (deleted since the flow ledger was built).
    Binary-safe (counts ``\\n``), no decode."""
    try:
        with open(repo_path / rel_path, "rb") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return None


def _null_state_fields() -> dict[str, Any]:
    """The zero-evidence stamp for a journey whose weighted credit rounds
    to 0 — mirrors ``metrics_recompute.mint_null_state`` / the
    ``_finalize_feature_metrics`` zero-commit convention (and never mints
    the impossible ``tc=0 ∧ authors>0`` row)."""
    return {
        "total_commits": 0,
        "bug_fixes": 0,
        "bug_fix_ratio": 0.0,
        "authors": [],
        "health_score": 100.0,
        "health_confidence": "insufficient",
    }


def apply_uf_metrics(
    user_flows: list[Any] | None,
    flows: list[Any] | None,
    commits: list["Commit"] | None,
    repo_path: Path,
) -> dict[str, Any]:
    """Stamp the engineering-metric family on every eligible UserFlow
    IN PLACE; return telemetry.

    ``flows`` are keyed by BOTH ``uuid`` and ``name`` (``member_flow_ids``
    may carry either), mirroring Stage 6.97b.
    """
    t0 = time.monotonic()

    flow_by_key: dict[str, Any] = {}
    for fl in (flows or []):
        for key in (getattr(fl, "uuid", None), getattr(fl, "name", None)):
            if key and key not in flow_by_key:
                flow_by_key[key] = fl

    # ── Pass 1: resolve every journey's owned-line ledger ───────────────
    ledgers: list[tuple[Any, dict[str, int]]] = []  # (uf, {file: owned})
    skipped_markers = 0
    skipped_memberless = 0
    skipped_no_spans = 0
    for uf in (user_flows or []):
        if getattr(uf, "is_coverage_marker", False):
            skipped_markers += 1        # honest None — no synthetic health
            continue
        if not (getattr(uf, "member_flow_ids", None) or []):
            skipped_memberless += 1     # honest None — no span ledger
            continue
        owned = uf_owned_lines_by_file(uf, flow_by_key)
        if not owned:
            skipped_no_spans += 1       # honest None — nothing resolved
            continue
        ledgers.append((uf, owned))

    # ── Pass 2: file denominators (ONE disk read per distinct file) ─────
    file_lines: dict[str, int | None] = {}
    for _uf, owned in ledgers:
        for p in owned:
            if p not in file_lines:
                file_lines[p] = count_file_lines(repo_path, p)
    files_missing = sum(1 for v in file_lines.values() if not v)

    # ── Pass 3: per-file commit aggregates (ONE sweep of ctx.commits) ───
    f_total: dict[str, int] = {}
    f_bugs: dict[str, int] = {}
    f_authors: dict[str, set[str]] = {}
    wanted = {p for p, v in file_lines.items() if v}
    for c in (commits or []):
        seen_in_commit: set[str] = set()
        for fp in c.files_changed:
            if fp in wanted and fp not in seen_in_commit:
                seen_in_commit.add(fp)
                f_total[fp] = f_total.get(fp, 0) + 1
                if c.is_bug_fix:
                    f_bugs[fp] = f_bugs.get(fp, 0) + 1
                f_authors.setdefault(fp, set()).add(c.author)

    # ── Pass 4: weighted rollup per journey ─────────────────────────────
    computed: list[tuple[Any, float, float, list[str]]] = []
    for uf, owned in ledgers:
        cw = 0.0
        bw = 0.0
        author_set: set[str] = set()
        for p in sorted(owned):        # sorted: deterministic float sums
            lines = file_lines.get(p)
            if not lines:
                continue               # unreadable/empty file — no credit
            w = min(1.0, owned[p] / lines)
            cw += f_total.get(p, 0) * w
            bw += f_bugs.get(p, 0) * w
            author_set |= f_authors.get(p, set())
        computed.append((uf, cw, bw, sorted(author_set)))

    # Scale-invariant confidence floor over the WEIGHTED population —
    # the same P25 mechanism features use.
    floor = _health_confidence_floor([round(cw) for _uf, cw, _bw, _a in computed])

    stamped = 0
    nonzero = 0
    zero_credit = 0
    for uf, cw, bw, authors in computed:
        total = round(cw)
        if total <= 0:
            for k, v in _null_state_fields().items():
                setattr(uf, k, v)
            zero_credit += 1
        else:
            ratio = bw / cw            # unrounded operands (honest ratio)
            uf.total_commits = total
            uf.bug_fixes = round(bw)
            uf.bug_fix_ratio = round(ratio, 3)
            uf.authors = authors
            uf.health_score = _calculate_health(ratio, total, None)
            uf.health_confidence = "low" if total < floor else "high"
            nonzero += 1
        uf.health_basis = HEALTH_BASIS_LABEL
        stamped += 1

    return {
        "enabled": True,
        "user_flows_total": len(user_flows or []),
        "stamped": stamped,
        "stamped_nonzero": nonzero,
        "zero_credit_rows": zero_credit,
        "skipped_markers": skipped_markers,
        "skipped_memberless": skipped_memberless,
        "skipped_no_spans": skipped_no_spans,
        "files_line_counted": len(file_lines),
        "files_missing_on_disk": files_missing,
        "confidence_floor": floor,
        "duration_ms": int((time.monotonic() - t0) * 1000),
    }
