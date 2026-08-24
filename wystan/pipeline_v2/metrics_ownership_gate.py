"""fixb124 / E1 — ownership gate on the emitted metric family (pre-Stage-7).

FORENSICS (VERIFIED on the KS63 world, 13 boards)
-------------------------------------------------
Two shapes of the SAME lie ship on every board today:

  * CLONE — ollama: SEVEN husk PFs (``api-ps`` / ``api-pull`` /
    ``api-push`` / ``api-user-keys-encoded-key`` / ``api-version`` /
    ``v1-models-model`` / ``v1-responses``, owned LOC 46/57/54/32/2/19/7
    of ONE 2300-line file) each wear the IDENTICAL tuple
    ``health=82.0 / coverage=63.0 / commits=94 / last_modified=
    2026-04-29`` — plus ``api-signout`` as an eighth husk on the same
    file. The tuple is ``server/routes.go``'s FILE history:
    :func:`~wystan.pipeline_v2.metrics_recompute._attach_pf_commit_metrics`
    credits EVERY PF that claims a path with every commit that touched
    it (the own-path-set law), and file-claiming is not owning. The
    interlayer tell is decisive: on the developer layer the same file
    carries 29 rows at ``commits=0`` and exactly ONE at 94 — the dev
    sweep's file→feature index is last-writer-wins
    (``stage_6_metrics._build_file_to_feature_index``), so the dev layer
    hands the history to a single row while the PF layer hands it to
    every claimant.

  * VACUUM — maybe 47/47 PFs, skateshop 22/22, peppermint 12/12,
    highlight 22 rows: ``health_score=100.0`` at ``total_commits=0``.
    Same producer family: ``_finalize_feature_metrics`` stamps the
    back-compat ``100.0`` placeholder whenever a row attributes no
    commits (and ``metrics_recompute.mint_null_state`` mirrors it for
    mint births). The display layer already mutes it (app 0ca7207
    ``honestHealth``); the DATA still says 100.

THE RULE (ratified 2026-08-06)
------------------------------
The gate is OWNERSHIP OF THE EVIDENCE BASIS — a metric may ship only
if it was measured on lines/commits the row OWNS — and NEVER tuple
collision. Three named collisions are LEGAL and must survive
untouched: dokploy's 3 PFs on ``db/constants.ts`` (owned 708/752/764 —
honest rows whose tuples merely coincide), novu's 6 PFs on
``base.provider.ts`` at ``commits=2`` (a short history collides
cheaply), fastapi's 4 PFs on ``fastapi/__init__.py`` (143 commits — on
a single-package library the package root IS every feature's file).

MECHANISM (threshold-free; no vocabulary, no magic number)
----------------------------------------------------------
Ownership is not re-invented here: it is read from the engine's own
one-owner-per-file authority, the emitted ``path_index``
("lines are coordinates" reverse-lookup contract, the same map Stage
6.97e already rolls PF LOC up from).

    owned_files(dev D)  = { f : path_index[f].feature_uuid == D.uuid }
    owned_files(PF P)   = { f : owner_dev(f).product_feature_id == P.name }
    owned_commits(row)  = |{ c ∈ commits : c touches ≥1 owned file }|

    ABSTAIN  ⇔  owned_commits(row) == 0

        reason ``"foreign_basis"`` — the row wears commits > 0 that were
            every one of them measured on somebody else's file (CLONE);
        reason ``"no_basis"`` — the row wears no commits at all, so the
            100.0 is a placeholder, not a measurement (VACUUM).

An abstained row emits ``None`` for the whole measured family
(``total_commits`` / ``bug_fixes`` / ``bug_fix_ratio`` /
``last_modified`` / ``health_score`` / ``coverage_pct`` /
``symbol_health_score`` / ``history``), an empty ``authors`` list,
``health_confidence="insufficient"`` and a machine-readable
``metrics_abstained`` reason. NOTHING is re-measured: a row with even
one owned commit keeps its numbers byte-identical — which is why all
three legal collisions (and cal.com's 9/7/5-row groups, linkwarden's,
typebot's, trigger.dev's 7-row storybook group) survive the gate
unchanged.

TELEMETRY CONTRACT (``scan_meta["metrics_ownership_gate"]``) — the pair
a validator must accept as legal, keyed exactly:

    {"enabled": true,
     "dev_rows": int, "pf_rows": int,
     "abstained_dev": int, "abstained_pf": int,
     "by_reason": {"foreign_basis": int, "no_basis": int},
     "abstained": [{"row": "<Feature.name>", "uuid": "<Feature.uuid — key ABSENT when the uuid is empty (warden #29)>",
                    "layer": "product"|"developer",
                    "reason": "foreign_basis"|"no_basis",
                    "owned_files": int,
                    "was": {"health_score": float|null,
                            "coverage_pct": float|null,
                            "total_commits": int|null,
                            "last_modified": "<iso>"|null,
                            "history_weeks": int, "impact_points": int}}],
     "ledger_truncated": bool}

The ledger is sorted by ``(layer, row)`` and capped at 60 entries
(``ledger_truncated`` says so); the COUNTS are always exact. A row whose
name appears there carries ``metrics_abstained`` with the same reason —
that is the join key: NULL METRICS + STAMP is the legal pair; a null
metric WITHOUT ``metrics_abstained`` (or without a ledger row) is a
defect, not an abstain.

SACRED: display/metric fields only. Membership (``paths`` /
``member_files`` / ``flows`` / UF homes), ``loc``, ``hotspot_files``
and the ``history`` series are never touched — the gate decides
whether a NUMBER may ship, never who owns what.

Kill-switch: ``WYSTAN_METRICS_OWNERSHIP_GATE`` — default **ON**
(flip #29, 2026-08-06, warden CLEAR #29 on c16/c17, KS 64; unset ≡
explicit ``1``). Explicit ``0`` / ``false`` / ``False`` / empty skips
the pass entirely ⇒ no ``scan_meta`` key, no ``metrics_abstained`` field, output
byte-identical to the pre-gate engine.

No LLM. No network. Deterministic and idempotent (a pure function of
rows × path_index × commits; the sweep accumulates into name-keyed
counters, never set-iteration-ordered values).
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from wystan.models.types import Commit, Feature

logger = logging.getLogger(__name__)

#: Kill-switch — default ON (flip #29, KS 64). Registered in ``ENV_OUTPUT_FLAGS``.
METRICS_OWNERSHIP_GATE_ENV = "WYSTAN_METRICS_OWNERSHIP_GATE"

#: fixb127 / E1-flow — the FLOW-layer completion of the same mechanism, on its
#: OWN armed-OFF sub-flag (default OFF; the default flip is an operator act).
#: NESTED under the parent: the parent's explicit ``0`` kill-switch must keep
#: producing a byte-identical pre-gate board, so the flow pass never runs while
#: the parent is off. Registered in ``ENV_OUTPUT_FLAGS``.
METRICS_OWNERSHIP_GATE_FLOWS_ENV = "WYSTAN_METRICS_OWNERSHIP_GATE_FLOWS"

#: Fields nulled on an abstained row (the MEASURED family only).
#:
#: ``history`` (fixb124 addendum, ruling 2026-08-06) carries the SAME
#: foreign evidence one level down — ``EntityHistory`` is birth_week +
#: weekly[] + events[] + test_efficacy + history_confidence + impact[] +
#: impact_trend, every one of them derived from the very commit
#: attribution the gate just refused. Leaving it would tell two stories
#: from one tile: the ollama husks published an IDENTICAL 35-week
#: sparkline (birth 2025-W32 ×8) belonging to ``server/routes.go``
#: milliseconds after honestly abstaining from its tuple.
ABSTAINED_NULL_FIELDS = (
    "total_commits",
    "bug_fixes",
    "bug_fix_ratio",
    "last_modified",
    "health_score",
    "coverage_pct",
    "symbol_health_score",
    "history",
)

#: fixb127 / E1-flow — the family nulled on an abstained FLOW row.
#:
#: DELIBERATELY SHORTER than :data:`ABSTAINED_NULL_FIELDS`. The probe measured
#: each field on 29460 flow rows / 34 boards before this list was written:
#:
#:   * ``coverage_pct`` is EXCLUDED — it is genuinely measured on the flow
#:     layer (100% of rows carry a real per-flow figure from the coverage
#:     stage; cal.com's 25 atoms-flows sharing 28.8 are a LEGAL collision on
#:     genuinely shared files, not a clone). Nulling it would destroy a
#:     measurement, which is the mirror-image of the lie we are removing.
#:   * ``loc`` / ``loc_shared`` are EXCLUDED — LOC law ("a member-ful row
#:     never renders a bare 0"), and they are span-derived, not commit-derived.
#:   * ``hotspot_files`` / ``hotspot_files_detail`` / ``test_file_count`` /
#:     ``test_files`` are EXCLUDED — file-grain git evidence that IS honestly
#:     computed (cal.com's validate-user-admin-access-flow carries
#:     ``getServerSession.ts`` at 8 commits / 7 bug-fixes in the very row whose
#:     roll-up says 0: the evidence exists, only the roll-up is missing).
#:   * ``health_trend`` / ``bus_factor`` / ``weekly_points`` are the same dead
#:     git family (0% populated) and ARE nulled/emptied — see
#:     :func:`_apply_flow_abstain`; they are handled separately because their
#:     honest empty state is ``[]`` / ``None``, not a nulled scalar.
FLOW_ABSTAINED_NULL_FIELDS = (
    "total_commits",
    "bug_fixes",
    "bug_fix_ratio",
    "last_modified",
    "health_score",
)

#: fixb127 — the ONE reason a flow row can carry. Unlike the feature layer
#: there is no ``foreign_basis`` case: the flow layer never attributes commits
#: at all, so there is no foreign attribution to catch — the family is a
#: constructor placeholder on every row.
FLOW_ABSTAIN_REASON = "no_basis"

#: Cap for the named-row ledger in ``scan_meta`` (telemetry stays bounded;
#: the counts are always exact).
_LEDGER_CAP = 60

__all__ = [
    "METRICS_OWNERSHIP_GATE_ENV",
    "METRICS_OWNERSHIP_GATE_FLOWS_ENV",
    "ABSTAINED_NULL_FIELDS",
    "FLOW_ABSTAINED_NULL_FIELDS",
    "FLOW_ABSTAIN_REASON",
    "metrics_ownership_gate_enabled",
    "flow_metrics_gate_enabled",
    "flow_has_git_evidence",
    "owned_files_by_row",
    "owned_commit_counts",
    "run_metrics_ownership_gate",
    "run_flow_metrics_abstain",
]


def metrics_ownership_gate_enabled() -> bool:
    """fixb124 / E1 — default **ON** (flip #29, KS 64). Explicit ``0`` / ``false`` /
    ``False`` / empty skips the pass entirely ⇒ byte-identical to the
    pre-gate engine (the kill-switch law); the default flips only in its
    own flip commit, which carries the KEY_SCHEMA bump."""
    return os.environ.get(METRICS_OWNERSHIP_GATE_ENV, "1").strip() not in {
        "0", "false", "False", "",
    }


def flow_metrics_gate_enabled() -> bool:
    """fixb127 / E1-flow — default **OFF** (armed), NESTED under the parent.

    The parent kill-switch wins: with ``WYSTAN_METRICS_OWNERSHIP_GATE=0``
    the whole E1 mechanism is off and the board must be byte-identical to the
    pre-gate engine, flow layer included. The sub-flag's own default flips only
    in its own flip commit (which carries the KEY_SCHEMA bump).
    """
    if not metrics_ownership_gate_enabled():
        return False
    # Flip #33 (2026-08-07, warden CLEAR-WITH-DEBT #32, KS 66):
    # default ON; unset ≡ "1"; explicit 0/false = kill-switch forever.
    return os.environ.get(METRICS_OWNERSHIP_GATE_FLOWS_ENV, "1").strip() in {
        "1", "true", "True", "on",
    }


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    """Read ``name`` from a pydantic/dataclass-ish object OR a plain dict."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _set_attr(obj: Any, name: str, value: Any) -> None:
    if isinstance(obj, dict):
        obj[name] = value
    else:
        setattr(obj, name, value)


def _owner_uuid(entry: Any) -> str:
    """``path_index`` entry ⇒ elected primary-owner feature uuid (``""``
    for an orphan route)."""
    return str(_attr(entry, "feature_uuid", "") or "")


def owned_files_by_row(
    features: list[Any],
    path_index: Any,
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """``(dev_name -> owned files, pf_name -> owned files)`` from ``path_index``.

    A file contributes to EXACTLY one developer feature (its elected
    ``feature_uuid``) and, transitively, to the ONE product feature that
    dev homes into — the same conservation-safe walk Stage 6.97e uses for
    owned LOC. Product-layer duplicates carried in ``features[]`` are
    skipped: they alias their members' paths and would forge ownership.
    Pure function — unit-testable without a live checkout.
    """
    dev_owned: dict[str, set[str]] = {}
    pf_owned: dict[str, set[str]] = {}
    if not path_index:
        return dev_owned, pf_owned

    by_uuid: dict[str, Any] = {}
    for f in features or []:
        if _attr(f, "layer", "developer") == "product":
            continue
        uuid = _attr(f, "uuid")
        if uuid:
            by_uuid[str(uuid)] = f

    items = path_index.items() if hasattr(path_index, "items") else path_index
    for path, entry in items:
        dev = by_uuid.get(_owner_uuid(entry))
        if dev is None:
            continue
        p = str(path)
        dev_owned.setdefault(str(_attr(dev, "name", "")), set()).add(p)
        pfid = _attr(dev, "product_feature_id")
        if pfid:
            pf_owned.setdefault(str(pfid), set()).add(p)
    return dev_owned, pf_owned


def owned_commit_counts(
    owned: dict[str, set[str]],
    commits: list["Commit"],
) -> dict[str, int]:
    """``row name -> #commits touching at least one file the row OWNS``.

    One sweep over the commit list through an inverted file→owners map;
    a commit counts ONCE per row no matter how many of its owned files it
    touched (the same per-commit dedup the B76 PF sweep uses).
    """
    file_owners: dict[str, list[str]] = {}
    for name, paths in owned.items():
        for p in paths:
            file_owners.setdefault(p, []).append(name)
    for owners in file_owners.values():
        owners.sort()  # deterministic; a file has 1 dev / 1 PF owner anyway

    counts: dict[str, int] = {}
    for commit in commits or []:
        touched: set[str] = set()
        for fp in _attr(commit, "files_changed", ()) or ():
            names = file_owners.get(fp)
            if names:
                touched.update(names)
        for name in touched:
            counts[name] = counts.get(name, 0) + 1
    return counts


def _abstain_reason(row: Any, owned_commits: int) -> str | None:
    """``None`` when the row keeps its numbers, else the reason token.

    Idempotence: a row that already carries a verdict keeps it. Without
    this the second pass would read its own nulled ``total_commits`` and
    re-label a ``foreign_basis`` clone as ``no_basis`` — the pass must be
    a pure function of the INPUT world, not of its own output.
    """
    if owned_commits > 0:
        return None
    prior = _attr(row, "metrics_abstained")
    if prior:
        return str(prior)
    return "no_basis" if not (_attr(row, "total_commits", 0) or 0) else (
        "foreign_basis"
    )


def _was(row: Any) -> dict[str, Any]:
    """The evidence the row wore before the gate (telemetry).

    Carries the tuple AND the size of the dropped history series, so a
    validator can see WHAT was refused without re-deriving it.
    """
    lm = _attr(row, "last_modified")
    hist = _attr(row, "history")
    return {
        "health_score": _attr(row, "health_score"),
        "coverage_pct": _attr(row, "coverage_pct"),
        "total_commits": _attr(row, "total_commits"),
        "last_modified": (lm.isoformat() if hasattr(lm, "isoformat")
                          else lm),
        "history_weeks": len(_attr(hist, "weekly", None) or ()) if hist
                         else 0,
        "impact_points": len(_attr(hist, "impact", None) or ()) if hist
                         else 0,
    }


def _apply_abstain(row: Any, reason: str) -> None:
    """Null the measured family IN PLACE + stamp the machine-readable reason.

    Membership, ``loc``, ``hotspot_files`` and ``history`` are untouched
    by construction — this function only writes the metric fields.
    """
    for field in ABSTAINED_NULL_FIELDS:
        _set_attr(row, field, None)
    _set_attr(row, "authors", [])
    _set_attr(row, "health_confidence", "insufficient")
    _set_attr(row, "metrics_abstained", reason)


def run_metrics_ownership_gate(
    features: list["Feature"],
    product_features: list["Feature"],
    commits: list["Commit"],
    path_index: Any,
) -> dict[str, Any]:
    """Abstain every row whose metric evidence basis it does not own.

    Runs after the LAST membership writer and before Stage 7, so the
    ownership it reads is exactly the ``path_index`` that ships. Returns
    deterministic content-derived telemetry (counts are exact; the named
    ledger is capped and sorted).
    """
    tele: dict[str, Any] = {
        "enabled": True,
        "dev_rows": 0,
        "pf_rows": 0,
        "abstained_dev": 0,
        "abstained_pf": 0,
        "by_reason": {"foreign_basis": 0, "no_basis": 0},
        "abstained": [],
    }
    if not path_index:
        tele["inert_reason"] = "no_path_index"
        return tele

    dev_rows = [f for f in (features or [])
                if _attr(f, "layer", "developer") != "product"]
    pf_dupes = [f for f in (features or [])
                if _attr(f, "layer", "developer") == "product"]
    pfs = list(product_features or [])
    tele["dev_rows"] = len(dev_rows)
    tele["pf_rows"] = len(pfs)

    dev_owned, pf_owned = owned_files_by_row(features or [], path_index)
    dev_counts = owned_commit_counts(dev_owned, commits or [])
    pf_counts = owned_commit_counts(pf_owned, commits or [])

    ledger: list[dict[str, Any]] = []
    abstained_pf_names: dict[str, str] = {}

    for row in pfs:
        name = str(_attr(row, "name", "") or "")
        reason = _abstain_reason(row, pf_counts.get(name, 0))
        if reason is None:
            continue
        # Warden #29: this world's PF rows carry uuid="" — an empty key in
        # the ledger = 12 false matches for any join-by-uuid consumer.
        # An empty uuid is NOT emitted (the join then goes by row+layer).
        entry = {"row": name, "layer": "product", "reason": reason,
                 "owned_files": len(pf_owned.get(name, ())),
                 "was": _was(row)}
        _uuid = str(_attr(row, "uuid", "") or "")
        if _uuid:
            entry["uuid"] = _uuid
        ledger.append(entry)
        _apply_abstain(row, reason)
        abstained_pf_names[name] = reason
        tele["abstained_pf"] += 1
        tele["by_reason"][reason] += 1

    for row in dev_rows:
        name = str(_attr(row, "name", "") or "")
        reason = _abstain_reason(row, dev_counts.get(name, 0))
        if reason is None:
            continue
        entry = {"row": name, "layer": "developer", "reason": reason,
                 "owned_files": len(dev_owned.get(name, ())),
                 "was": _was(row)}
        _uuid = str(_attr(row, "uuid", "") or "")
        if _uuid:
            entry["uuid"] = _uuid
        ledger.append(entry)
        _apply_abstain(row, reason)
        tele["abstained_dev"] += 1
        tele["by_reason"][reason] += 1

    # Mirror onto the product-layer duplicates carried in ``features[]``
    # (the emitted layer + validator I2 read those rows, not the PF list).
    for dupe in pf_dupes:
        reason = abstained_pf_names.get(str(_attr(dupe, "name", "") or ""))
        if reason is not None:
            _apply_abstain(dupe, reason)

    ledger.sort(key=lambda e: (e["layer"], e["row"]))
    tele["abstained"] = ledger[:_LEDGER_CAP]
    tele["ledger_truncated"] = len(ledger) > _LEDGER_CAP
    logger.info(
        "metrics_ownership_gate: pf %d/%d abstained, dev %d/%d abstained "
        "(foreign_basis %d, no_basis %d)",
        tele["abstained_pf"], tele["pf_rows"],
        tele["abstained_dev"], tele["dev_rows"],
        tele["by_reason"]["foreign_basis"], tele["by_reason"]["no_basis"],
    )
    return tele


# ── fixb127 / E1-flow — the FLOW layer of the same mechanism ────────────
#
# FORENSICS (VERIFIED, probe 2026-08-06: 29460/29460 flow rows, 34 boards)
# -----------------------------------------------------------------------
# The flow layer was NEVER MEASURED. ``stage_5_postprocess._flow_spec_to_flow``
# constructs every Flow with ``health_score=80.0`` as a HAND-WRITTEN LITERAL
# beside ``total_commits=0`` / ``bug_fixes=0`` / ``bug_fix_ratio=0.0`` /
# ``authors=[]`` / ``last_modified=epoch(0)``. No formula produces 80: the
# engine's own ``_calculate_health(total_commits=0)`` returns 100.0, and the
# "100" family is what a placeholder looks like AFTER a measuring pass ran.
# The literal survives to emission because there is NO flow equivalent of
# ``_finalize_feature_metrics``: neither ``metrics_recompute`` (6.998) nor the
# feature/PF ownership gate above accepts flow rows. Measured breadth on
# cal.com: authors 0%, weekly_points 0%, health_trend 0%, last_modified=epoch
# 100% — over 1456 flows.
#
# THE INTERLAYER CONTRADICTION this closes (ollama c16): 41 E1-abstained
# parents honestly publish null, while their 61 CHILD FLOWS keep publishing
# 80.0 in the same tile — one board telling two stories about the same code.
#
# MECHANISM (ruling 2026-08-06 — deliberately NOT the parent's mechanism)
# ----------------------------------------------------------------------
# The parent gate computes ownership from ``path_index`` because a feature row
# can own SOME of its evidence. A flow cannot: ``path_index[f].flow_uuids`` is
# a LIST (up to 417 claimants on one file), so there is no one-owner-per-file
# authority to read and porting the parent's predicate would MANUFACTURE a
# clone-shaped verdict out of a claim list. The ownership predicate is instead
# TRIVIALLY TRUE — every flow row's whole git family is a constructor
# placeholder — so the pass abstains WITHOUT counting ownership, with reason
# ``"no_basis"`` on every row.
#
# THE ONE FENCE: a flow that actually carries git evidence (any commits, any
# authors, a real timestamp) is LEFT ALONE and counted in ``kept_measured``.
# On today's world this fires 0 times (that is the census assertion, not an
# assumption) — it exists so that the day someone DOES build the flow-metrics
# roll-up, this pass degrades to a no-op instead of deleting their work.
#
# SACRED (anti-cases banked by the probe): ``coverage_pct`` is genuinely
# measured and is NOT touched (cal.com's 25 atoms-flows legally sharing 28.8
# keep it); ``loc``/``loc_shared`` are untouched (LOC law — all-shared flows
# with loc=0/loc_shared>0, up to 19.9% of a board, get exactly the same
# treatment as every other row and nothing worse); ``hotspot_files*`` /
# ``test_file*`` / ``paths`` / ``line_ranges`` / identity / membership are
# untouched. The pass decides whether a NUMBER may ship, never who owns what.
#
# PARKED (named, not improvised): windowed history — a flow whose commits fall
# outside the 365-day scan window is "out-of-window", which is NOT the same
# claim as "no_basis". That token belongs to the feature layer's future work.


def flow_has_git_evidence(flow: Any) -> bool:
    """True when this flow row carries an actual git measurement.

    The fence described above. Deliberately generous — ANY of: a nonzero
    commit count, a nonzero bug-fix count, a non-empty author list, a
    non-empty weekly series, or a ``last_modified`` past the epoch sentinel
    ``_flow_spec_to_flow`` stamps. Reads only; never writes.
    """
    if (_attr(flow, "total_commits", 0) or 0) > 0:
        return True
    if (_attr(flow, "bug_fixes", 0) or 0) > 0:
        return True
    if _attr(flow, "authors", None):
        return True
    if _attr(flow, "weekly_points", None):
        return True
    lm = _attr(flow, "last_modified")
    if lm is None:
        return False
    ts = getattr(lm, "timestamp", None)
    if callable(ts):
        try:
            return float(ts()) > 0.0
        except (OSError, OverflowError, ValueError):  # pragma: no cover
            return True
    # Serialized (dict) form: the epoch sentinel is "1970-01-01T00:00:00Z".
    return not str(lm).startswith("1970-01-01T00:00:00")


def _apply_flow_abstain(flow: Any) -> None:
    """Null the dead git family on ONE flow row + stamp the reason.

    ``coverage_pct`` / ``loc`` / ``loc_shared`` / ``hotspot_files*`` /
    ``test_file*`` / membership / identity are untouched BY CONSTRUCTION —
    this function writes exactly the fields listed here and nothing else.
    """
    for field in FLOW_ABSTAINED_NULL_FIELDS:
        _set_attr(flow, field, None)
    # The rest of the same dead family, in its honest empty shape.
    _set_attr(flow, "authors", [])
    _set_attr(flow, "weekly_points", [])
    _set_attr(flow, "health_trend", None)
    _set_attr(flow, "metrics_abstained", FLOW_ABSTAIN_REASON)


def _flow_key(flow: Any) -> str:
    """Stable row label for telemetry: ``Flow.id`` else uuid else name."""
    for field in ("id", "uuid", "name"):
        value = _attr(flow, field)
        if value:
            return str(value)
    return "?"


def run_flow_metrics_abstain(
    flows: list[Any] | None,
    features: list[Any] | None = None,
    product_features: list[Any] | None = None,
) -> dict[str, Any]:
    """Null the never-measured git family on EVERY flow row, in BOTH views.

    ``flows`` is the top-level bipartite store; ``features`` /
    ``product_features`` carry the containment projection
    (``Feature.flows[]``). Stage 5.5 builds the two views over the SAME Flow
    objects, but later passes rebuild one of them (the probe caught the two
    views disagreeing field-by-field on ollama c16) — so all three surfaces
    are swept explicitly and the pass is idempotent: re-nulling an already
    nulled row is a no-op, and the row counters below are per-VIEW while
    ``rows_distinct`` counts objects once.

    Pure, deterministic, no LLM, no network. Works on pydantic Flow objects
    and on plain dicts alike (the ``_attr``/``_set_attr`` pair), which is what
    lets a captured board be projected through the very same code.
    """
    tele: dict[str, Any] = {
        "enabled": True,
        "reason": FLOW_ABSTAIN_REASON,
        "flows_top_level": 0,
        "flows_containment_dev": 0,
        "flows_containment_pf": 0,
        "abstained_top_level": 0,
        "abstained_containment_dev": 0,
        "abstained_containment_pf": 0,
        "rows_distinct": 0,
        "abstained_distinct": 0,
        "kept_measured": 0,
        "kept_measured_rows": [],
    }

    seen: set[int] = set()
    kept_named: list[str] = []

    def _sweep(rows: list[Any] | None, count_key: str, abstain_key: str) -> None:
        for flow in rows or []:
            tele[count_key] += 1
            oid = id(flow)
            first_time = oid not in seen
            if first_time:
                seen.add(oid)
                tele["rows_distinct"] += 1
            if flow_has_git_evidence(flow):
                # The fence: a genuinely measured flow keeps every number.
                if first_time:
                    tele["kept_measured"] += 1
                    if len(kept_named) < _LEDGER_CAP:
                        kept_named.append(_flow_key(flow))
                continue
            _apply_flow_abstain(flow)
            tele[abstain_key] += 1
            if first_time:
                tele["abstained_distinct"] += 1

    _sweep(flows, "flows_top_level", "abstained_top_level")
    # ``features`` carries BOTH layers (the emitted board's product rows are
    # mirrors inside the same list) — bucket each row by its own ``layer`` so
    # the counters mean what they say, exactly like the parent gate does.
    for feat in features or []:
        if _attr(feat, "layer", "developer") == "product":
            _sweep(_attr(feat, "flows", None),
                   "flows_containment_pf", "abstained_containment_pf")
        else:
            _sweep(_attr(feat, "flows", None),
                   "flows_containment_dev", "abstained_containment_dev")
    for pf in product_features or []:
        _sweep(_attr(pf, "flows", None),
               "flows_containment_pf", "abstained_containment_pf")

    tele["kept_measured_rows"] = sorted(kept_named)
    logger.info(
        "flow_metrics_abstain: %d/%d distinct flow rows abstained "
        "(top-level %d/%d, containment dev %d/%d, pf %d/%d, kept measured %d)",
        tele["abstained_distinct"], tele["rows_distinct"],
        tele["abstained_top_level"], tele["flows_top_level"],
        tele["abstained_containment_dev"], tele["flows_containment_dev"],
        tele["abstained_containment_pf"], tele["flows_containment_pf"],
        tele["kept_measured"],
    )
    return tele
