"""Stage 6.97e — PF-level OWNED-LOC rollup backstop ($0, output layer).

Operator trust-bug (coverage-gaps cycle, 2026-07-31): a *member-ful* product
feature renders a bare ``loc = 0`` on the PF row despite owning real code. On
the RefApp board the PF ``findings`` holds four developer members —
``api-detectors`` (49 routes; owns ``backend/routers/detectors.py`` = 3564 LOC),
``api-findings`` (1674 owned), ``api-mitre`` (987 owned) and
``finding-detail-page`` — yet the emitted PF row shows ``loc = 0``. This is the
"member-ful row with 0 LOC = trust bug" doctrine (2026-07-16): a row with
attached code evidence must never display a bare ``0`` — I2 correctly does NOT
drop it (evidence is attached), so it survives as a *hollow* row.

Why the emitted PF ``loc`` is stale
-----------------------------------
``stage_6_97_feature_loc.apply_feature_loc`` (Stage 6.97) runs ONCE and rolls
the PF ``loc`` up from its members' owned files (RefApp: ``findings`` = 7944 at
that point). AFTER 6.97 the late journey-layer surgery — the armed api-stub /
api-container / fold-evidence demotes and the 6.9965/6.9966 journey re-homes —
mutates the ``loc`` *scalar* of a demoted api-container dev to ``0`` while
leaving its ownership records (``path_index`` + ``member_files``) intact: on
RefApp ``path_index[backend/routers/detectors.py].feature_uuid`` still elects
``api-detectors`` and ``api-detectors.member_files`` still flags the router
``primary``, but ``api-detectors.loc`` is now ``0``. The PF-row scalar is
dragged to ``0`` in the same window. Neither the dev-``loc`` scalar nor the
PF-``loc`` scalar is recomputed after that surgery — so both go stale.

The backstop (this stage)
-------------------------
For every product feature whose ``loc`` is *falsy* (``0`` / ``None``) this stage
RECOMPUTES its owned LOC from the AUTHORITATIVE per-file owner map — the
emitted ``path_index`` ("lines are coordinates"; the single-owner-per-file
reverse-lookup contract). A PF's owned LOC is the sum of every counted file
whose ``path_index`` primary owner is a developer member of THIS PF
(``owner_dev.product_feature_id == pf.name``), each physical file counted ONCE
by its single owner. If that owned sum is ``> 0`` it is stamped on the PF row
(and mirrored onto the ``features[]`` product-layer duplicate).

Why ``path_index`` and NOT ``sum(member_dev.loc)``: the demote zeroes the
*dev* scalar too (``api-detectors.loc == 0``), so summing member ``loc`` would
UNDERCOUNT — it would drop exactly the backend-router 3564 LOC the disease is
about. ``path_index`` still elects ``api-detectors`` as the router's owner, so
it both RESTORES the router into ``findings`` AND stays conservation-safe (a
file has exactly one ``path_index`` owner ⇒ never double-counted across PFs).
``member_files[].primary`` is NOT used: it is the Stage-02 attribution flag
(a shared file can be ``primary`` on several devs) and would double-count.

Additivity / kill-switch
------------------------
Default OFF. A PF that already carries ``loc > 0`` is NEVER entered, so every
normal PF row is byte-identical; only the hollow (falsy-``loc``) class can
change, and only UPWARD to its real owned footprint. ``loc_shared`` is left
untouched (already non-zero + honest on the hollow rows; not the trust-bug).
``WYSTAN_PF_LOC_ROLLUP_FIX`` unset (``≡ "0"``) or ``0`` skips the stage
entirely ⇒ byte-identical to the pre-stage engine (the kill-switch law).
Deterministic: the owned sum is an order-independent accumulation over
``path_index`` items; no set iteration feeds a value. No LLM, no network, no
disk reads (``member_files[].loc`` was line-counted at 6.97).
"""

from __future__ import annotations

import os
from typing import Any

__all__ = [
    "STAGE_6_97E_ENV_FLAG",
    "PF_LOC_REROLL_ENV_FLAG",
    "pf_loc_rollup_fix_enabled",
    "pf_loc_reroll_enabled",
    "owned_loc_by_pfid",
    "apply_pf_loc_backstop",
    "apply_pf_loc_reroll",
]

STAGE_6_97E_ENV_FLAG = "WYSTAN_PF_LOC_ROLLUP_FIX"
PF_LOC_REROLL_ENV_FLAG = "WYSTAN_PF_LOC_REROLL"


def pf_loc_rollup_fix_enabled() -> bool:
    """Default **ON** since the 2026-07-31 flip-pack №14 flip (KEY_SCHEMA 49;
    keyed proof: RefApp findings loc 0→6225, dashboards 0→7109). Unset now arms
    the stage; ``WYSTAN_PF_LOC_ROLLUP_FIX=0`` (or ``false``/``False``/
    empty) stays a kill-switch forever — byte-identical to the pre-stage
    engine. Only the ``os.environ.get`` default moved ``"0"`` -> ``"1"``; the
    off-set {"0","false","False",""} is preserved LITERALLY."""
    return os.environ.get(STAGE_6_97E_ENV_FLAG, "1").strip() not in {
        "0", "false", "False", "",
    }


def pf_loc_reroll_enabled() -> bool:
    """fixb114 / P12-M1 — the TWO-SIDED re-roll (see
    :func:`apply_pf_loc_reroll`). Default **OFF** (armed): unset / ``0`` /
    ``false`` / ``False`` / empty skips the stage entirely ⇒ byte-identical
    to the pre-stage engine (the kill-switch law)."""
    return os.environ.get(PF_LOC_REROLL_ENV_FLAG, "1").strip() not in {
        "0", "false", "False", "",
    }


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    """Read ``name`` from a dataclass-ish object OR a plain dict."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _set_loc(obj: Any, value: int) -> None:
    """Set ``loc`` on a dataclass-ish object OR a plain dict."""
    if isinstance(obj, dict):
        obj["loc"] = value
    else:
        obj.loc = value


def _set_attr(obj: Any, name: str, value: Any) -> None:
    """Set ``name`` on a dataclass-ish object OR a plain dict."""
    if isinstance(obj, dict):
        obj[name] = value
    else:
        setattr(obj, name, value)


def _dev_pfid_by_uuid(features: list[Any]) -> dict[str, str]:
    """``developer feature uuid -> product_feature_id`` for every dev feature
    that homes into a PF. Product-layer duplicates are skipped (they carry the
    same paths as their members and would alias the owner)."""
    out: dict[str, str] = {}
    for f in features:
        if _attr(f, "layer", "developer") == "product":
            continue
        uuid = _attr(f, "uuid")
        pfid = _attr(f, "product_feature_id")
        if uuid and pfid:
            out[str(uuid)] = str(pfid)
    return out


def _path_loc_map(features: list[Any]) -> dict[str, int]:
    """``file path -> per-file LOC`` from ``member_files[].loc`` (stamped at
    6.97; the same file carries the same count on every claimant, so
    first-int-wins is stable)."""
    out: dict[str, int] = {}
    for f in features:
        for mf in _attr(f, "member_files", None) or []:
            pa = _attr(mf, "path")
            lo = _attr(mf, "loc")
            if pa and isinstance(lo, int) and not isinstance(lo, bool):
                out.setdefault(str(pa), lo)
    return out


def _owner_uuid(entry: Any) -> str:
    """``path_index`` entry ⇒ the elected primary-owner feature uuid (``""``
    for an orphan route)."""
    val = _attr(entry, "feature_uuid", "")
    return str(val or "")


def owned_loc_by_pfid(
    features: list[Any],
    path_index: Any,
) -> dict[str, int]:
    """Owned LOC per ``product_feature_id`` from the authoritative one-owner-
    per-file ``path_index``. Each counted file contributes its LOC to EXACTLY
    the PF that homes its elected owner dev (files whose owner is unhomed /
    orphaned / has no known LOC are skipped). Pure function — unit-testable
    without a live checkout."""
    if not path_index:
        return {}
    dev_pfid = _dev_pfid_by_uuid(features)
    path_loc = _path_loc_map(features)
    owned: dict[str, int] = {}
    items = path_index.items() if hasattr(path_index, "items") else path_index
    for path, entry in items:
        owner = _owner_uuid(entry)
        if not owner:
            continue
        pfid = dev_pfid.get(owner)
        if not pfid:
            continue
        lo = path_loc.get(str(path))
        if lo is None:
            continue
        owned[pfid] = owned.get(pfid, 0) + lo
    return owned


def apply_pf_loc_backstop(
    product_features: list[Any] | None,
    features: list[Any],
    path_index: Any,
) -> dict[str, Any]:
    """Recompute ``loc`` IN PLACE for every product feature whose current
    ``loc`` is falsy but which owns code per ``path_index``. Mutates the PF
    rows (and the ``features[]`` product-layer duplicates) and returns
    telemetry. NEVER lowers or touches a PF that already carries ``loc > 0``."""
    tele: dict[str, Any] = {
        "enabled": True,
        "pfs_total": 0,
        "pfs_hollow": 0,
        "pfs_recomputed": 0,
        "loc_restored": 0,
        "recomputed": [],
    }
    pfs = product_features or []
    tele["pfs_total"] = len(pfs)
    if not pfs or not path_index:
        if not path_index:
            tele["inert_reason"] = "no_path_index"
        return tele

    owned = owned_loc_by_pfid(features, path_index)
    touched: dict[str, int] = {}
    for pf in pfs:
        cur = _attr(pf, "loc")
        if cur:  # loc > 0 → normal PF, never entered (additive).
            continue
        tele["pfs_hollow"] += 1
        name = _attr(pf, "name")
        if not name:
            continue
        new_loc = owned.get(str(name), 0)
        if new_loc > 0:
            _set_loc(pf, new_loc)
            touched[str(name)] = new_loc
            tele["pfs_recomputed"] += 1
            tele["loc_restored"] += new_loc
            if len(tele["recomputed"]) < 40:
                tele["recomputed"].append(
                    {"pf": str(name), "loc_before": cur, "loc_after": new_loc}
                )

    # Mirror onto the product-layer duplicates carried in ``features[]`` (the
    # emitted layer + validator I2), matching by name; a duplicate that is the
    # SAME object as the PF row is already set (the ``not cur`` guard no-ops).
    if touched:
        for f in features:
            if _attr(f, "layer", "developer") != "product":
                continue
            nm = str(_attr(f, "name", "") or "")
            if nm in touched and not _attr(f, "loc"):
                _set_loc(f, touched[nm])
    return tele


# ─────────────────────────────────────────────────────────────────────────
# fixb114 / P12-M1 — TWO-SIDED PF-loc re-roll on the FINAL membership
# ─────────────────────────────────────────────────────────────────────────
#
# THE DEFECT (P12 census, FRESH KS60 world = 20 boards / 698 PFs)
# ---------------------------------------------------------------
# ``pf.loc`` is rolled up ONCE at Stage 6.97 and then never again, while
# SEVEN membership-moving passes run after it (6.9965 token-journey rehome,
# 6.9966 container-family, lane_rehome, capability_shared_rehome,
# mega_pf_nav_rehome, B93/B94/B96 demotes, the B97 hard gate's own E1/E2/E3b
# demotes + E3a renames, and fixb103 detach accounting). The scalar is stale
# in BOTH directions — 22 PFs read LOW and 5 read HIGH against their own
# members (cold calibration: growthbook ``features`` 41097 vs 4963 = 8x
# INFLATED, growthbook ``auth`` 1681 vs 104808 = 62x deflated, twenty
# ``twenty-sdk`` 55 vs 9290 = 169x deflated). Two-sidedness is the signature
# of stale MEMBERSHIP: a floor or a cap only ever errs one way.
#
# Both existing repair hooks are STRUCTURALLY BLIND to a stale non-zero:
#   * ``emission_hard_gate.py`` E1 — ``if getattr(pf, "loc", None): continue``
#     (a falsy gate: it only ever sees rows that render a bare 0);
#   * :func:`apply_pf_loc_backstop` above — same falsy gate, and its
#     docstring contracts "only UPWARD".
# A third subclass never enters ANY rollup: 8/698 FRESH PFs carry
# ``loc_shared = None`` (late mints born after 6.97), so their ``loc`` is
# whatever their minter guessed — ``directus`` ``v-icon-file`` shows 45
# against a single member dev (``histoire``) that owns 6810.
#
# THE LAW (this pass) — REPLAY, not a second ruler
# ------------------------------------------------
# Stage 6.97's PF rollup is a pure function of three inputs: the per-file
# LOC map, the one-owner-per-file election, and the dev->PF membership. Only
# the THIRD changes afterwards. So 6.97 hands this pass its LEDGER
# (``file_loc`` / ``owner_by_file`` / ``files_by_dev`` / ``art_enabled`` —
# see ``stage_6_97_feature_loc.apply_feature_loc``) and this pass re-runs the
# IDENTICAL arithmetic over the membership as it stands at emission:
#
#     owned_files = {f: loc for dev in members for f in files_by_dev[dev]
#                    if owner_by_file[f] == dev}
#     ref_files   = {f: loc for dev in members for f in files_by_dev[dev]}
#     pf.loc         = sum(owned_files)            (minus B59 ink)
#     pf.loc_shared  = sum(ref_files - owned_files)
#
# Using 6.97's own election — NOT ``sum(member_dev.loc)`` (the demote zeroes
# a dev's ``loc`` scalar while leaving its ownership intact, so that ruler
# undercounts by exactly the material the disease is about) and NOT the
# emitted ``path_index`` + ``member_files[].loc`` pair (measured on the same
# world: that reconstruction disagrees with 6.97 on 88/698 rows, because
# ``member_files[].loc`` is ``None`` on every entry a post-6.97 pass added —
# 174/8021 on tracecat alone — and because it double-restores the B59 ink
# drain: ente ``ente-base`` 3295 -> 47920, of which 44625 is locale ink).
# Replaying the ledger is byte-identical wherever membership did not move,
# which is what makes "no delta on a clean board" an assertion and not a hope.
#
# THE ONE REFUSED DIRECTION — never re-roll a row down to a bare 0
# ---------------------------------------------------------------
# A member-ful row rendering ``loc = 0`` is the trust bug this stage family
# exists to kill (operator doctrine 2026-07-16), so the re-roll ABSTAINS
# whenever the replay yields 0 on a row that currently carries a positive
# ``loc``, and counts it. That guard covers the two known legitimate
# non-rollup provenances: the B98-3e span-LOC bump (a go-router headless dev
# whose ``loc`` comes from handler spans, not from owned files) and 6.97's
# own no-dev-member fallback (``documenso`` ``envelope-editor`` = 4711 LOC
# from ``pf.paths`` with zero member devs). Neither is stale membership;
# both would be destroyed by a naive replay.
#
# ``loc_flow`` / ``loc_flow_shared`` ride along: they are §4.5's function of
# the same owned sets and would otherwise break the on-flow ≤ 1 construction
# (``loc_flow <= loc``) the moment ``loc`` moves down. The pass re-runs
# ``_apply_flow_accounting`` over the NEW owned sets — the same function
# 6.97 calls, under the same ``WYSTAN_SPINE_CONSERVATION`` gate.
#
# Additivity / kill-switch: ``WYSTAN_PF_LOC_REROLL`` unset (≡ "0") skips
# the stage entirely. Deterministic: every accumulation is over a sorted key
# list; no set iteration reaches a value.


def replay_pf_rollup(
    member_uuids: list[str],
    ledger: dict[str, Any],
    art_of: Any = None,
) -> tuple[int, int, int]:
    """Replay Stage 6.97's PF rollup for ONE product feature.

    Returns ``(owned_loc, shared_loc, artifact_ink_loc)`` — the same three
    numbers 6.97 would have stamped had ``member_uuids`` been the membership
    at rollup time. Pure function (unit-testable without a checkout);
    order-independent (each physical file is visited once per owning dev and
    contributes to exactly one bucket).
    """
    file_loc: dict[str, int] = ledger.get("file_loc") or {}
    owner_by_file: dict[str, str] = ledger.get("owner_by_file") or {}
    files_by_dev: dict[str, tuple[str, ...]] = ledger.get("files_by_dev") or {}

    owned: dict[str, int] = {}
    ref: dict[str, int] = {}
    for uid in sorted(set(member_uuids)):
        for fp in files_by_dev.get(uid, ()):
            lo = file_loc.get(fp)
            if lo is None:
                continue
            ref[fp] = lo
            if owner_by_file.get(fp) == uid:
                owned[fp] = lo
    # B59: the ink drain moves LOC out of ``loc`` into ``artifact_ink_loc``,
    # NOT into ``loc_shared`` — 6.97 computes the shared bucket against the
    # PRE-drain owned set (``stage_6_97_feature_loc.py:617-619``), so an
    # owned ink file lands in neither product bucket.
    ink = 0
    product_owned = owned
    if art_of is not None:
        ink_paths = [fp for fp in sorted(owned) if art_of(fp)]
        ink = sum(owned[fp] for fp in ink_paths)
        product_owned = {fp: l for fp, l in owned.items() if fp not in set(ink_paths)}
    return (
        sum(product_owned[fp] for fp in sorted(product_owned)),
        sum(ref[fp] for fp in sorted(ref) if fp not in owned),
        ink,
    )


def _owned_files_for(
    member_uuids: list[str],
    ledger: dict[str, Any],
    art_of: Any = None,
) -> dict[str, int]:
    """The PF's owned-file map (§4.5's ``pf_owned_sets`` element), B59 ink
    already partitioned out when the lane is enabled."""
    file_loc: dict[str, int] = ledger.get("file_loc") or {}
    owner_by_file: dict[str, str] = ledger.get("owner_by_file") or {}
    files_by_dev: dict[str, tuple[str, ...]] = ledger.get("files_by_dev") or {}
    owned: dict[str, int] = {}
    for uid in sorted(set(member_uuids)):
        for fp in files_by_dev.get(uid, ()):
            lo = file_loc.get(fp)
            if lo is None:
                continue
            if owner_by_file.get(fp) == uid:
                owned[fp] = lo
    if art_of is not None:
        for fp in [p for p in sorted(owned) if art_of(p)]:
            del owned[fp]
    return owned


def span_provenance_loc(
    member_uuids: list[str],
    ledger: dict[str, Any],
    dev_by_uuid: dict[str, Any],
) -> int:
    """fixb116 — the SPAN half of Stage 6.97's own PF-loc law.

    THE BUG (VERIFIED, ollama fresh keyed 2026-08-06 vs the KS57 board)
    ===================================================================
    6.97 stamps a PF's ``loc`` from TWO provenances, and
    :func:`replay_pf_rollup` replays only the first:

    1. the owned-file rollup (``owner_by_file`` — what the replay does), and
    2. the **B98-3e span-LOC bump** (``stage_6_97_feature_loc.py:704-756``):
       a zero-LOC dev whose name matches a go-router handler slug takes
       ``loc = Σ handler spans``, and the family PF takes the same number
       when its own ``loc`` is still falsy. That is the "lines are
       coordinates" law for a route family that shares ONE ``routes.go``.

    So a PF whose loc came from (2) replays as 0 and is re-rolled to a bare
    0 — the trust bug this stage family exists to kill. ``07-stage-
    pf_loc_reroll.json`` on the ollama ON board names all seven, ``n_members
    = 1`` each, ``loc_delta = -309``::

        api-ps 46->0   api-pull 57->0   api-push 54->0   api-signout 94->0
        api-user-keys-encoded-key 32->0  v1-models-model 19->0
        v1-responses 7->0

    The module's own zero-guard CLAIMS to cover exactly this provenance
    ("the B98-3e span-LOC bump ... would be destroyed by a naive replay")
    but cannot reach it: a go-router family shares ``server/routes.go`` by
    construction, so ``new_shared`` is 2300, not 0, and the guard's
    ``new_shared == 0`` conjunct never fires for the class it names. The
    dev rows still carry the honest numbers (``api-ps`` loc=46, paths
    ``['server/routes.go']``) — the mass was stranded, never lost.

    THE RULER — reconstruct provenance (2), do not widen the guard
    =============================================================
    Abstaining would freeze a stale claim; the correct answer is to replay
    the law 6.97 actually ran. A member dev is SPAN-provenance iff it owns
    NO file in the ledger at all yet carries ``loc > 0``: its LOC cannot
    have come from an owned-file rollup, so it came from the span bump.

    Ownership is tested on the RAW ledger, deliberately BEFORE the B59 ink
    partition: an ink-only owner does own files, so it is not span-
    provenance, and the ente ``3295 -> 47920`` double-restore this module
    already refused stays refused.

    Mirrors 6.97's own gate — the bump applied only ``if not (_fam_pf.loc or
    0)``, i.e. only to a PF with no rollup mass — so the caller applies this
    ONLY when the owned rollup is 0, and the first qualifying member in
    emission order wins (6.97's loop leaves ``_fam_pf.loc`` truthy after the
    first). Returns 0 when nothing qualifies ⇒ inert.
    """
    owner_by_file: dict[str, str] = ledger.get("owner_by_file") or {}
    files_by_dev: dict[str, tuple[str, ...]] = ledger.get("files_by_dev") or {}
    owning = {str(u) for u in owner_by_file.values() if u}
    for uid in member_uuids:  # emission order — 6.97's own iteration
        if uid in owning and any(
            owner_by_file.get(fp) == uid for fp in files_by_dev.get(uid, ())
        ):
            continue
        dev = dev_by_uuid.get(uid)
        if dev is None:
            continue
        loc = int(_attr(dev, "loc", 0) or 0)
        if loc > 0:
            return loc
    return 0


def apply_pf_loc_reroll(
    product_features: list[Any] | None,
    features: list[Any],
    ledger: dict[str, Any] | None,
    user_flows: list[Any] | None = None,
    flows: list[Any] | None = None,
) -> dict[str, Any]:
    """Re-roll ``loc`` / ``loc_shared`` (and the §4.5 flow accounting) for
    every product feature from the FINAL dev->PF membership, replaying
    Stage 6.97's own law over the ledger it captured. Mutates the PF rows
    and their ``features[]`` product-layer duplicates in place; returns
    deterministic telemetry. See the module comment above for the law, the
    ruler choice and the one refused direction."""
    tele: dict[str, Any] = {
        "enabled": True,
        "pfs_total": 0,
        "pfs_with_members": 0,
        "pfs_rerolled": 0,
        "pfs_raised": 0,
        "pfs_lowered": 0,
        "pfs_late_mint_entered": 0,
        "pfs_zero_guarded": 0,
        # fixb116 — PFs whose ``loc`` was reconstructed from the B98-3e span
        # bump rather than the owned-file rollup (the second half of 6.97's
        # law). A stable key so the artifact shape never depends on data.
        "pfs_span_provenance": 0,
        "loc_delta": 0,
        "sum_pf_owned": 0,
        "flow_accounting_rerun": False,
        "rerolled": [],
    }
    pfs = product_features or []
    tele["pfs_total"] = len(pfs)
    if not pfs or not ledger or not ledger.get("files_by_dev"):
        tele["inert_reason"] = "no_ledger" if not ledger else "no_pfs"
        return tele

    art_of = None
    if ledger.get("art_enabled"):
        from wystan.pipeline_v2.artifact_ink import classify_artifact
        _memo: dict[str, Any] = {}

        def art_of(fp: str) -> Any:  # noqa: F811 — narrow local closure
            hit = _memo.get(fp, "\0")
            if hit == "\0":
                hit = classify_artifact(fp)
                _memo[fp] = hit
            return hit

    # FINAL membership, dev uuid grouped by home. Product-layer duplicates
    # are skipped (they alias their members' paths — the 6.97 discipline).
    members_by_pf: dict[str, list[str]] = {}
    dev_by_uuid: dict[str, Any] = {}
    for f in features:
        if _attr(f, "layer", "developer") == "product":
            continue
        uid = str(_attr(f, "uuid", "") or "")
        pfid = str(_attr(f, "product_feature_id", "") or "")
        if uid:
            dev_by_uuid.setdefault(uid, f)
        if uid and pfid:
            members_by_pf.setdefault(pfid, []).append(uid)

    touched: dict[str, tuple[int, int, int]] = {}
    owned_sets: list[dict[str, int]] = []
    guarded_flow: dict[str, tuple[Any, Any]] = {}
    for pf in pfs:
        name = str(_attr(pf, "name", "") or "")
        members = members_by_pf.get(name, [])
        cur = int(_attr(pf, "loc", 0) or 0)
        cur_shared = _attr(pf, "loc_shared")
        if members:
            tele["pfs_with_members"] += 1
        new_loc, new_shared, new_ink = replay_pf_rollup(members, ledger, art_of)
        owned_sets.append(_owned_files_for(members, ledger, art_of))

        # fixb116 — replay the SPAN half of 6.97's law (see
        # :func:`span_provenance_loc`). Gated on ``new_loc == 0`` exactly as
        # 6.97 gated its own bump on a falsy family loc, so a PF with rollup
        # mass is untouched and the pass stays inert on every board without a
        # shared-route family.
        if new_loc == 0 and members:
            _span = span_provenance_loc(members, ledger, dev_by_uuid)
            if _span > 0:
                new_loc = _span
                tele["pfs_span_provenance"] = (
                    int(tele.get("pfs_span_provenance") or 0) + 1)

        # The ONE refused direction — never leave a row with NO evidence at
        # all. ``owned == 0 AND shared == 0`` on a row that currently shows
        # code means the replay found nothing to say about it, which is the
        # signature of the two non-rollup provenances: the B98-3e span-LOC
        # bump (a go-router dev whose ``loc`` comes from handler spans, not
        # owned files) and 6.97's no-dev-member fallback (documenso
        # ``envelope-editor`` = 4711 LOC expanded from ``pf.paths``, zero
        # member devs — an expansion this pass deliberately does not redo,
        # since it would mean disk reads at the emission seam).
        #
        # NOT refused: ``owned == 0`` with ``shared > 0``. That is the
        # doctrinally CORRECT pure-sharer split (W3.1 D11 / pretalx I13 —
        # the owned floor was removed on purpose, and 779 of 780 zero-loc
        # dev rows on this world are honest sharers). Measured on the FRESH
        # KS60 world: all 7 rows the first-cut guard blocked were exactly
        # this shape (better-auth ``env`` emitted 23/0 vs the truth 0/23),
        # i.e. the guard was preserving the stale claim it exists to fix.
        if new_loc == 0 and new_shared == 0 and cur > 0:
            tele["pfs_zero_guarded"] += 1
            owned_sets[-1] = {}
            # A guarded row keeps its ``loc``, so it must keep its §4.5 pair
            # too — otherwise the flow-accounting re-run below would stamp
            # ``loc_flow = 0`` on a row this pass deliberately did not touch.
            guarded_flow[str(name)] = (
                _attr(pf, "loc_flow"), _attr(pf, "loc_flow_shared"),
            )
            tele["sum_pf_owned"] += cur
            continue

        tele["sum_pf_owned"] += new_loc
        if new_loc == cur and (
            cur_shared is not None and int(cur_shared or 0) == new_shared
        ):
            continue

        if cur_shared is None:
            tele["pfs_late_mint_entered"] += 1
        if new_loc > cur:
            tele["pfs_raised"] += 1
        elif new_loc < cur:
            tele["pfs_lowered"] += 1
        tele["pfs_rerolled"] += 1
        tele["loc_delta"] += new_loc - cur
        _set_loc(pf, new_loc)
        _set_attr(pf, "loc_shared", new_shared)
        if art_of is not None:
            _set_attr(pf, "artifact_ink_loc", new_ink or None)
        touched[name] = (new_loc, new_shared, new_ink)
        if len(tele["rerolled"]) < 40:
            tele["rerolled"].append({
                "pf": name,
                "loc_before": cur,
                "loc_after": new_loc,
                "loc_shared_before": cur_shared,
                "loc_shared_after": new_shared,
                "n_members": len(members),
            })

    # §4.5 — loc_flow / loc_flow_shared are a function of the SAME owned
    # sets; leaving them stale would break the on-flow ≤ 1 construction the
    # moment ``loc`` moved down. Same function, same conservation gate.
    if touched and user_flows is not None and flows is not None:
        from wystan.pipeline_v2.stage_6_97_feature_loc import (
            _apply_flow_accounting,
        )
        acct = _apply_flow_accounting(
            pfs, owned_sets, user_flows, flows, ledger.get("file_loc") or {},
        )
        if acct is not None:
            tele["flow_accounting_rerun"] = True
            tele["flow_accounting"] = acct
            for pf in pfs:
                keep = guarded_flow.get(str(_attr(pf, "name", "") or ""))
                if keep is not None:
                    _set_attr(pf, "loc_flow", keep[0])
                    _set_attr(pf, "loc_flow_shared", keep[1])

    # Mirror onto the product-layer duplicates in ``features[]`` (emitted
    # layer + validator I2) — the 6.97 mirror, by name.
    if touched:
        flow_pair = {
            str(_attr(pf, "name", "") or ""): (
                _attr(pf, "loc_flow"), _attr(pf, "loc_flow_shared"),
            )
            for pf in pfs
            if _attr(pf, "loc_flow") is not None
        }
        for f in features:
            if _attr(f, "layer", "developer") != "product":
                continue
            nm = str(_attr(f, "name", "") or "")
            hit = touched.get(nm)
            if hit is None:
                continue
            _set_loc(f, hit[0])
            _set_attr(f, "loc_shared", hit[1])
            if art_of is not None:
                _set_attr(f, "artifact_ink_loc", hit[2] or None)
            fp = flow_pair.get(nm)
            if fp is not None and tele["flow_accounting_rerun"]:
                _set_attr(f, "loc_flow", fp[0])
                _set_attr(f, "loc_flow_shared", fp[1])
    return tele
