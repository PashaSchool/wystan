"""journey_lineage_audit — fixb119 M1: a journey's death becomes NAMED.

THE CLASS (probe P15, measured on 8 capture runs of the KS61 world):
between the ``journey_lattice`` seam and emission, **154 rows** of
``user_flows[]`` disappear across 8 boards. The material is mostly
conserved (dedup), but the IDENTITY of the death is not: only 30/154
(19%) carry an id-bound record (``adjudicator_6_7e.demote_map/merge_map``),
53 (34%) carry a name only, and **71 (46%)** carry nothing identifiable.
No board consumer can tell "vanished honestly" from "vanished silently".

The class is NOT "deletion without a record" but **"lineage without
identity"**: three degradation tiers (name-only / count-only / nothing)
coexist across 28 in-place ``user_flows[:] = ...`` sites in 17 modules.

MECHANISM (precedent ``segb_landing_binding``, fixb118 Q5): a scan-scoped
thread-local registry; the snapshot is taken at the producer, the
reconciliation at emission, and the invariant is stamped into
``scan_meta``. **ZERO touches to the 28 deletion sites** — the audit
changes nothing, it NAMES the culprits so that the targeted per-writer
registry (M6) is built on measurement rather than blind.

THE SNAPSHOT SEAM IS IMMEDIATELY AFTER ``journey_lattice``, not earlier.
The ``journey_abstraction → journey_lattice`` window is a LAWFUL wholesale
re-derivation of the whole journey layer (580 "deaths" across 8 boards);
a seam before the lattice would drown the sentinel in noise (lesson B33:
do not judge the journey layer until it has settled).

RECONCILIATION at emission, basket order (first match wins):

1. ``survived``   — the id is on the board.
2. ``re_id``      — the id is gone, but a row with the SAME non-empty
   member set (or the same name) was emitted: a re-mint, **not a loss**.
3. ``abstained``  — the id is in ``uf_member_exists.abstained_row_ids``: an
   abstain, not a death (warden precedent KS61: 9 hollow ≡ 9 abstained =
   accounted policy debt). Netted BEFORE counting unaccounted.
4. ``id_bound``   — the id is named in a deletion channel (the reference
   form) OR in the per-writer registry (fixb121 M6, channel
   ``writer:<module>.<function>``).
5. ``name_only``  — only the name is named in a channel (a degraded tier).
6. ``unaccounted``— nothing. The row goes by name into the stamp + hook.

M6 — THE PER-WRITER REGISTRY (fixb121). Forensics on the 8-pair gate
capture set (``fixb121_writerprobe``: writer sites executed against a
deserialised ``07-stage-naming_contract`` / ``06-stage-feature_loc``
capture, every in-place ``user_flows[:]`` wrapped) named the culprits;
after instrumenting 5 measured sites the 8-pair gate gives
**unaccounted 39 → 7** (the rest by name, see below) with UNCHANGED
``deaths 111 / re_id 23 / lane 13 / overclaim 2``:

===========================================================  ========
writer channel (world-8)                                       rows
===========================================================  ========
``writer:member_disjoint_reconcile.reconcile_member_disjoint``     21
``writer:uf_synth_fold.apply_uf_synth_fold``                       13
``writer:synth_quality.emit_coverage_gaps``                         4
``writer:emission_integrity._drop_anchored_husks``                  3
``writer:generic_container_demote.run_generic_container_demote``    1
===========================================================  ========

The remaining 7 (all infisical 6 / typebot 1: ``UF-159``,
``UF-L-0783889a23``, ``UF-L-716766bb16``, ``UF-L-bd9cee15ce``,
``UF-L-d17c5aa4c1``, ``UF-L-e62fdb7187``, typebot ``UF-011``) are
attributed to NONE of the probed sites — a separate forensic item, not a
silent hole.

THE ROOT OF THE CLASS that M6 cures: these writers mostly do NOT stay
silent — they write a NAME, and the name drifts. ``naming_contract``
renames a row BETWEEN the (post-lattice) snapshot and the deletion, so the
name-tier record and the snapshot are different strings for the same
journey: chatwoot UF-011 is ``'Components'`` in the snapshot while
``generic_container_demote.dropped_ufs['components']`` ==
``['Connect components']``; documenso UF-079 ``'Webhooks'`` →
``dissolved_names`` ``'Manage webhooks'``; infisical UF-201
``'Secret Import'`` → ``'Ingest data from Secret Import'``. An id does not
drift — so the self-report goes by id.

The worst subclass is ``uf_synth_fold``: it COMPUTES the full id-tier
lineage (``plan.fold``: loser_id → winner_id) and THROWS IT AWAY;
``phase_finalize`` does not even stamp the count-only ``uf_synth_fold``
telemetry (it reads only ``coverage_gaps`` from ``_sq_tele``). The same
disease M2 cured in B84.

BIRTHS (fixb121, warden debt #2). The audit was death-only: chatwoot c12
emitted 53 − survived 49 = 4 post-lattice births (``uf_cases_split``
UF-CS-*) had no lineage record at all. The symmetric ``births[]`` basket
+ the conservation invariant ``snapshot + births − deaths == emitted``
close the loop in both directions.

M3-LANE (fixb119 ruling). ``surface_taxonomy`` does NOT lose a row: it
puts the journey's full ``model_dump()`` — including ``id`` — into
``non_product_surfaces[].user_flows[]``. Probe P15 classified this channel
as COUNT-ONLY because it looked only at ``scan_meta`` (which indeed holds
just the ``ufs_moved_to_lane`` counter). The row MOVED with its whole
identity, so an id match in the lane is an ID-tier record, and of the
strongest form: not a mention of the row but the row itself. The channel
is registered as ``surface_taxonomy.non_product_surfaces``; such deaths go
to ``id_bound`` + ``lane_retained``.

The PRODUCT question (whether a lane row stays on the board with
``scope: marketing``) was DECIDED by the operator on 2026-08-10 —
**option A: delete** (fixb140, flag ``WYSTAN_LANE_MOVED_DELETE``, default
**ON** since flip-pack #41, KEY_SCHEMA 75). It was the by-name
``lane_moved`` that made the decision possible ROW BY ROW ("Explore
pricing plans" m=8) rather than by a counter: all 13 world rows (typebot 9
/ kan 3 / core-redplanet 1) have ``member_absorbed 0.00`` — the member
flows leave the journey layer entirely, so the row that remains is a
SHELL (the hollow-rows disease).

M3-LANE-DELETE (fixb140). The deletion removes EXACTLY the id-tier channel
by which M3 accounted for the row (the physical ``model_dump()`` in the
lane). So ``surface_taxonomy`` stamps a replacement of THE SAME TIER:
``surface_taxonomy_emission.lane_deleted_ids`` (channel
``surface_taxonomy.lane_deleted``) + the M6 per-writer self-report. Both
are by ID, and both pass the same anti-laundering reconciliation (a claim
about a live row legalises nothing). The row stays ``id_bound``, goes into
``lane_moved`` with the additive flag ``row_deleted: true`` and is counted
in ``lane_deleted`` instead of ``lane_retained``. The ``lane_deleted`` key
exists ONLY when >0, and ``row_deleted`` only on deleted rows ⇒ a board
with fixb140 off is byte-identical.

Flag ``WYSTAN_JOURNEY_LINEAGE_AUDIT`` default **ON** (flip #27,
2026-08-06, warden CLEAR-WITH-DEBT, KS 62; the first live stamp = the c12
pair chatwoot 56→53 / maybe 56→56, all channels id-bound, the board
set-identical between hands). Explicit ``0``/``false``/``off``/``no`` ⇒
registry ``None`` ⇒ no snapshot, no reconciliation, no
``scan_meta.journey_lineage_audit`` key and no ``invariant_hooks[]``
record ⇒ byte-identical (a kill-switch forever).

$0. No LLM, no network. Deterministic: every basket is sorted and the
member hash is sha1 over the SORTED unique member ids (stable under set
iteration — a determinism TRAP).
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
from typing import Any, Iterable

__all__ = [
    "JOURNEY_LINEAGE_AUDIT_ENV",
    "JOURNEY_LINEAGE_UNACCOUNTED_CLS",
    "JOURNEY_LINEAGE_CONSERVATION_CLS",
    "WRITER_CHANNEL_PREFIX",
    "journey_lineage_audit_enabled",
    "install_journey_lineage_registry",
    "uninstall_journey_lineage_registry",
    "snapshot_post_lattice",
    "report_journey_kill",
    "run_journey_lineage_audit",
    "unaccounted_exhibits",
]

JOURNEY_LINEAGE_AUDIT_ENV = "WYSTAN_JOURNEY_LINEAGE_AUDIT"

#: The invariant-hook class (severity WARN on the first wave — the audit
#: does not change the board, so CRITICAL would block installs for nothing).
JOURNEY_LINEAGE_UNACCOUNTED_CLS = "journey_lineage_unaccounted"

#: fixb121 — the hook class for the conservation loop
#: ``snapshot + births − deaths == emitted``.
JOURNEY_LINEAGE_CONSERVATION_CLS = "journey_lineage_conservation"

#: fixb121 M6 — the channel-label prefix of the per-writer registry. Full label:
#: ``writer:<module>.<function>``.
WRITER_CHANNEL_PREFIX = "writer:"

#: Display cap for the by-name list. The full number is ALWAYS in
#: ``unaccounted_count`` and truncation in ``unaccounted_truncated`` (the M2
#: lesson: a cap-30 with no truncation flag is blindness invisible from the board).
_UNACCOUNTED_CAP = 20

#: The M3-lane channel: the row physically sits in ``non_product_surfaces[]``
#: (``surface_taxonomy`` puts a full ``model_dump()`` there), so an id match
#: is an ID-tier record, not a guess.
_LANE_CHANNEL = "surface_taxonomy.non_product_surfaces"

#: The fixb140 M3-lane-delete channel: the row was DELETED from the lane
#: (operator option A), so there is no physical ``model_dump()`` any more —
#: the producer carries the id-tier record in ``lane_deleted_ids``.
_LANE_DELETED_CHANNEL = "surface_taxonomy.lane_deleted"

_NORM_RE = re.compile(r"[^a-z0-9]+")


def journey_lineage_audit_enabled() -> bool:
    """fixb119 — default **ON** (flip #27, KS 62).

    Unset ≡ explicit ``1``. Explicit ``0``/``false``/``off``/``no`` ⇒ no
    registry, no snapshot, no ``scan_meta.journey_lineage_audit`` ⇒ the board
    is byte-identical to the disabled world — a kill-switch forever.
    """
    return os.environ.get(JOURNEY_LINEAGE_AUDIT_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _norm(s: Any) -> str:
    return _NORM_RE.sub(" ", str(s or "").lower()).strip()


def _uid(obj: Any) -> str:
    return str(_get(obj, "id") or "")


def _get(obj: Any, key: str) -> Any:
    """Rows arrive both as pydantic models and as dicts (capture replay)."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _member_hash(obj: Any) -> str:
    """sha1 over the SORTED unique member ids.

    An empty set ⇒ ``""``: member-less rows have no identity by members, and
    a hash match would glue them all into one RE-ID (a false zero).
    """
    ids = sorted({str(m) for m in (_get(obj, "member_flow_ids") or [])})
    if not ids:
        return ""
    return hashlib.sha1("\x1f".join(ids).encode("utf-8")).hexdigest()


# ── the lineage channel registry (a structural registry of engine keys, ──
#    not a content dictionary: every path is confirmed in producer code)

def _chan_id(scan_meta: dict[str, Any]) -> dict[str, list[str]]:
    """``uf_id -> [channel label, …]`` — the ID-BOUND tier (reference form)."""
    out: dict[str, list[str]] = {}

    def add(uid: Any, label: str) -> None:
        u = str(uid or "")
        if u:
            out.setdefault(u, []).append(label)

    adj = scan_meta.get("adjudicator_6_7e") or {}
    for r in adj.get("demote_map") or []:
        if isinstance(r, dict):
            add(r.get("id"), "adjudicator_6_7e.demote_map")
    for r in adj.get("merge_map") or []:
        if isinstance(r, dict):
            add(r.get("dropped_id"), "adjudicator_6_7e.merge_map")
    for r in (scan_meta.get("synth_quality") or {}).get(
            "suppressed_markers") or []:
        if isinstance(r, dict):
            add(r.get("id"), "synth_quality.suppressed_markers")
    # fixb119 M2 — a new id tier: dissolved B84 twins.
    mdr = scan_meta.get("member_disjoint_reconcile") or {}
    for u in mdr.get("dissolved_ids") or []:
        add(u, "member_disjoint_reconcile.dissolved_ids")
    # fixb131 Seg C — a new id tier: rows eaten by ``uf_synth_fold``. The
    # channel exists precisely because Seg C delivered telemetry into
    # ``scan_meta``: the lineage itself (``plan.fold``: loser -> winner) was
    # ALWAYS computed but written nowhere — this is the "worst subclass"
    # named in M6 above. The writer channel
    # (``writer:uf_synth_fold.apply_uf_synth_fold``) is unchanged; this is its
    # board-visible reference-tier twin, readable without the registry.
    for r in ((scan_meta.get("synth_quality") or {}).get(
            "uf_synth_fold") or {}).get("folded") or []:
        if isinstance(r, dict):
            add(r.get("id"), "synth_quality.uf_synth_fold.folded")
    return out


#: Modules whose telemetry carries ``dropped_ufs`` (dict pf -> [names] or list).
_DROPPED_UFS_KEYS = (
    "devgrain_demote", "generic_container_demote", "api_stub_demote",
    "api_container_demote", "route_render_util_demote", "nav_category_demote",
    "settings_frame_demote", "capability_shared_rehome",
)


def _flat_dropped_ufs(scan_meta: dict[str, Any], key: str) -> list[Any]:
    v = (scan_meta.get(key) or {}).get("dropped_ufs")
    out: list[Any] = []
    if isinstance(v, dict):
        for vv in v.values():
            out.extend(vv if isinstance(vv, list) else [vv])
    elif isinstance(v, list):
        out.extend(v)
    return out


def _chan_name(scan_meta: dict[str, Any]) -> dict[str, list[str]]:
    """``norm(name) -> [channel label, …]`` — the degraded NAME-ONLY tier."""
    out: dict[str, list[str]] = {}

    def add(nm: Any, label: str) -> None:
        n = _norm(nm)
        if n:
            out.setdefault(n, []).append(label)

    for r in (scan_meta.get("journey_lattice") or {}).get(
            "subset_merged_pairs") or []:
        if isinstance(r, dict):
            add(r.get("dropped"), "journey_lattice.subset_merged_pairs")
    for n in (scan_meta.get("member_disjoint_reconcile") or {}).get(
            "dissolved_names") or []:
        add(n, "member_disjoint_reconcile.dissolved_names")
    for n in (scan_meta.get("stage_6_7d_journey_abstraction") or {}).get(
            "uf_dropped_names") or []:
        add(n, "stage_6_7d_journey_abstraction.uf_dropped_names")
    for r in (scan_meta.get("adjudicator_6_7e") or {}).get("merge_map") or []:
        if isinstance(r, dict):
            add(r.get("dropped_name"), "adjudicator_6_7e.merge_map")
    for r in (scan_meta.get("surface_taxonomy_emission") or {}).get(
            "info_ufs_dissolved_sample") or []:
        if isinstance(r, dict):
            add(r.get("uf"), "surface_taxonomy_emission.info_ufs_dissolved")
    for key in _DROPPED_UFS_KEYS:
        for n in _flat_dropped_ufs(scan_meta, key):
            add(n, key + ".dropped_ufs")
    return out


def _abstained(scan_meta: dict[str, Any]) -> set[str]:
    """AN ABSTAIN ≠ a death (anti-case: the KS61 warden precedent)."""
    return {
        str(u) for u in
        ((scan_meta.get("uf_member_exists") or {}).get("abstained_row_ids")
         or [])
        if u
    }


def _lane_ids(non_product_surfaces: Iterable[Any] | None) -> set[str]:
    """ids of journeys PHYSICALLY preserved in the ``non_product_surfaces[]`` lane.

    ``surface_taxonomy`` puts the row's full ``model_dump()`` into
    ``entry["user_flows"]``, so lane membership IS THE ROW ITSELF, not a
    mention of it: the strongest possible lineage record (M3-lane).
    """
    out: set[str] = set()
    for entry in (non_product_surfaces or ()):
        rows = entry.get("user_flows") if isinstance(entry, dict) else None
        for r in rows or []:
            u = str(_get(r, "id") or "")
            if u:
                out.add(u)
    return out


def _lane_deleted_ids(scan_meta: dict[str, Any]) -> set[str]:
    """fixb140 — ids of journeys the lane move DELETED (option A).

    A same-ID-tier replacement for the physical M3 channel: the list is
    written by the PRODUCER itself
    (``surface_taxonomy._delete_hollow_lane_rows``) into
    ``surface_taxonomy_emission.lane_deleted_ids``, and it is NOT capped — a
    capped accounting channel is the M2 blindness class (cap-30). The NAMES
    of deleted rows sit in the neighbouring ``lane_deleted`` (also FULL, lead
    ruling 2026-08-10). That is why ``lane_moved`` here may stay a 20-row
    DISPLAY sample: the permanent record lives on the producer side, not in a
    capped audit basket.

    Empty when fixb140 is off (the key simply is not there) ⇒ no effect on
    the baskets, no new key in the stamp.
    """
    out: set[str] = set()
    for u in ((scan_meta.get("surface_taxonomy_emission") or {})
              .get("lane_deleted_ids") or ()):
        s = str(u or "")
        if s:
            out.add(s)
    return out


# ── the scan-scoped registry ────────────────────────────────────────────

class _LineageRegistry:
    """A snapshot of the journey layer at the post-lattice seam.

    The key is the stable UF id (not ``id(obj)``: post-lattice passes rebuild
    the list and CPython reuses ``id()`` after GC — the lesson of
    overturn-ledger).
    """

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self.seam: str = ""
        #: The FULL (uncapped) list of unaccounted ids for the invariant
        #: hook — ``scan_meta`` carries a display cap, but the hook's
        #: ``count`` must be full (the invariant_hooks law: never cap a count).
        self.unaccounted_ids: list[str] = []
        #: fixb121 M6 — the per-writer registry: ``uf_id -> [writer, …]``.
        #: Written by the WRITER ITSELF at deletion time (an id does not
        #: drift, a name does — see the module docstring).
        self.writer_kills: dict[str, list[str]] = {}


_active = threading.local()


def _registry() -> _LineageRegistry | None:
    return getattr(_active, "journey_lineage", None)


def install_journey_lineage_registry() -> None:
    """Activate the registry for the current thread.

    ALWAYS reassigns (not only when ON): the worker reuses threads between
    scans, so a leftover registry would reconcile the NEXT scan against the
    previous one's snapshot (the fixb118 class — registries must not leak).
    """
    _active.journey_lineage = (
        _LineageRegistry() if journey_lineage_audit_enabled() else None
    )


def uninstall_journey_lineage_registry() -> None:
    _active.journey_lineage = None


def snapshot_post_lattice(
    user_flows: Iterable[Any] | None,
    seam: str = "post_journey_lattice",
) -> int:
    """Take a snapshot of the journey layer. Returns 0 when OFF (no reads).

    Idempotent, FIRST-WINS: a repeat call in the same run does not overwrite
    the snapshot (there is exactly one seam — right after the lattice).
    """
    reg = _registry()
    if reg is None:
        return 0
    if reg.rows:
        return len(reg.rows)
    for uf in (user_flows or ()):
        uid = _uid(uf)
        if not uid:
            continue
        reg.rows[uid] = {
            "name": str(_get(uf, "name") or ""),
            "pf": str(_get(uf, "product_feature_id") or ""),
            "mhash": _member_hash(uf),
            "members": len(_get(uf, "member_flow_ids") or []),
        }
    reg.seam = seam
    return len(reg.rows)


def report_journey_kill(writer: str, ids: Iterable[Any]) -> int:
    """fixb121 M6 — a writer SELF-REPORTS the rows it is removing NOW.

    ``writer`` is the ``"<module>.<function>"`` of the deletion site; ``ids``
    are the UF ids leaving ``user_flows[]``. Returns the number of accepted
    (id, writer) pairs.

    Three properties make the call safe to place anywhere:

    * **a no-op outside a registry.** Registry ``None`` (flag ``0`` / a call
      outside a scan / a unit importing the writer directly) ⇒ 0, WITHOUT an
      exception. A writer never fails because of the audit.
    * **zero touches to the board.** The function mutates nothing but the
      registry.
    * **no laundering.** A record is only a CLAIM. It becomes a channel only
      if, at reconciliation, the id really was in the snapshot AND really
      left the board (the lane-id-match class): reconciliation consults
      ``writer_kills`` in EXACTLY the same basket order as every other
      channel, so a claim about a live (or non-existent) row legalises
      nothing — it merely counts in ``writer_reports_rejected``.

    The ID, not the name, is the cure for this class: name-tier records
    (``dropped_ufs``, ``dissolved_names``) are written AFTER the naming
    contract while the snapshot is taken BEFORE it, so the name in the
    channel and the name in the snapshot are different strings for the same
    journey (chatwoot UF-011 ``'Components'`` in the snapshot vs
    ``generic_container_demote.dropped_ufs['components'] ==
    ['Connect components']``). An id does not drift.
    """
    reg = _registry()
    if reg is None:
        return 0
    w = str(writer or "")
    if not w:
        return 0
    n = 0
    for i in ids or ():
        u = str(i or "")
        if not u:
            continue
        seen = reg.writer_kills.setdefault(u, [])
        if w not in seen:
            seen.append(w)
            n += 1
    return n


def run_journey_lineage_audit(
    user_flows: list[Any] | None,
    scan_meta: dict[str, Any] | None,
    non_product_surfaces: Iterable[Any] | None = None,
) -> dict[str, Any] | None:
    """Emit-time reconciliation of the snapshot against the EMITTED board.

    ``None`` when the flag is off or there is no snapshot ⇒ no key in
    ``scan_meta`` ⇒ byte-identical.
    """
    reg = _registry()
    if reg is None or not reg.rows:
        return None
    meta = scan_meta or {}

    emitted_ids: set[str] = set()
    emitted_hashes: set[str] = set()
    emitted_names: set[str] = set()
    # fixb121 — births: a row that was NOT in the snapshot but IS on the
    # emitted board. The order is stable (by id), like every other basket.
    births: list[dict[str, Any]] = []
    for uf in (user_flows or ()):
        uid = _uid(uf)
        if uid:
            emitted_ids.add(uid)
            if uid not in reg.rows:
                births.append({
                    "id": uid,
                    "name": str(_get(uf, "name") or ""),
                    "pf": str(_get(uf, "product_feature_id") or ""),
                    "members": len(_get(uf, "member_flow_ids") or []),
                })
        h = _member_hash(uf)
        if h:
            emitted_hashes.add(h)
        n = _norm(_get(uf, "name"))
        if n:
            emitted_names.add(n)
    births.sort(key=lambda r: str(r["id"]))

    idc = _chan_id(meta)
    nmc = _chan_name(meta)
    abstained_ids = _abstained(meta)
    # M3-lane (fixb119 ruling): the lane is a FULL id-tier channel. The row
    # is not lost, it MOVED with its whole identity; an id match in
    # ``non_product_surfaces[].user_flows[]`` is the strongest form of record
    # (the row itself, not a mention of it).
    lane_ids = _lane_ids(non_product_surfaces)
    for _lu in sorted(lane_ids):
        idc.setdefault(_lu, []).append(_LANE_CHANNEL)
    # fixb140 — operator option A: the row was DELETED from the lane, so the
    # physical channel above no longer sees it. The producer named it BY ID
    # instead — same tier, same reconciliation. Empty when OFF ⇒ no change.
    lane_deleted_ids = _lane_deleted_ids(meta)
    for _du in sorted(lane_deleted_ids):
        idc.setdefault(_du, []).append(_LANE_DELETED_CHANNEL)
    # fixb121 M6 — per-writer self-reports are one more ID-tier channel.
    # They are added AFTER the scan_meta channels, so a row with both bumps
    # BOTH labels: existing channel counters are unchanged, the writer only
    # adds its own. Labels are sorted — basket determinism.
    writer_reports = 0
    for _wu in sorted(reg.writer_kills):
        for _ws in sorted(set(reg.writer_kills[_wu])):
            writer_reports += 1
            idc.setdefault(_wu, []).append(WRITER_CHANNEL_PREFIX + _ws)

    survived = 0
    reid_members = 0
    reid_name = 0
    abstained = 0
    id_bound: list[str] = []
    name_only: list[str] = []
    unaccounted: list[dict[str, Any]] = []
    lane_retained = 0
    lane_deleted = 0
    lane_moved: list[dict[str, Any]] = []
    channels: dict[str, int] = {}
    writer_reports_bound = 0

    def bump(labels: Iterable[str]) -> None:
        for lb in labels:
            channels[lb] = channels.get(lb, 0) + 1

    for uid in sorted(reg.rows):
        row = reg.rows[uid]
        if uid in emitted_ids:
            survived += 1
            continue
        # ── anti-case: a RE-ID is not a loss (a re-mint of the same row) ──
        mh = str(row.get("mhash") or "")
        if mh and mh in emitted_hashes:
            reid_members += 1
            continue
        nm_norm = _norm(row.get("name"))
        if nm_norm and nm_norm in emitted_names:
            reid_name += 1
            continue
        # ── anti-case: an abstain is netted BEFORE unaccounted ─────────
        if uid in abstained_ids:
            abstained += 1
            continue
        labels = idc.get(uid) or []
        if labels:
            id_bound.append(uid)
            bump(labels)
            writer_reports_bound += len(
                [lb for lb in labels if lb.startswith(WRITER_CHANNEL_PREFIX)])
            # PHYSICAL presence in the lane is the ground truth for
            # "retained"; "deleted" = the producer claimed a deletion AND the
            # row really is absent from the lane payload (the same
            # anti-laundering discipline as in
            # writer_reports_rejected).
            _in_lane = uid in lane_ids
            _deleted = uid in lane_deleted_ids and not _in_lane
            if _in_lane or _deleted:
                if _deleted:
                    lane_deleted += 1
                else:
                    lane_retained += 1
                # Moves are named ROW BY ROW — exactly what made the
                # operator's 2026-08-10 ruling (option A) possible per row
                # rather than per counter; now that same list also carries a
                # VERDICT per row (``row_deleted``, additive: the key exists
                # ONLY on deleted rows ⇒ the OFF board is byte-identical).
                if len(lane_moved) < _UNACCOUNTED_CAP:
                    rec: dict[str, Any] = {
                        "id": uid,
                        "name": row.get("name") or "",
                        "pf": row.get("pf") or "",
                        "members": int(row.get("members") or 0),
                    }
                    if _deleted:
                        rec["row_deleted"] = True
                    lane_moved.append(rec)
            continue
        labels = nmc.get(nm_norm) or []
        if labels:
            name_only.append(uid)
            bump(labels)
            continue
        unaccounted.append({
            "id": uid,
            "name": row.get("name") or "",
            "pf": row.get("pf") or "",
            "members": int(row.get("members") or 0),
        })

    # ── counter-check: a channel that CLAIMED a drop of a row still on the
    # board. P15 (documenso): ``subset_merged_pairs`` contains a 2-cycle A→B
    # AND B→A while BOTH names are emitted — a ledger that lies in BOTH
    # directions (it not only misses deaths, it invents them). Such a record
    # does not make a row dead, so the baskets above never see it — it is
    # caught only by this counter-check. A purely diagnostic counter: the
    # board is unchanged and the hook does not fire (name-tier unreliability,
    # the M4 motive, not a lost row).
    overclaim: list[dict[str, str]] = []
    for nm_norm2 in sorted(nmc):
        if nm_norm2 not in emitted_names:
            continue
        for label in sorted(set(nmc[nm_norm2])):
            overclaim.append({"name": nm_norm2, "channel": label})

    deaths = (
        reid_members + reid_name + abstained
        + len(id_bound) + len(name_only) + len(unaccounted)
    )
    reg.unaccounted_ids = [str(r["id"]) for r in unaccounted]
    # ── the fixb121 conservation loop ───────────────────────────────────
    # ``snapshot + births − deaths == emitted``. NOT a tautology: ``deaths``
    # is the SUM of the baskets rather than ``snapshot − survived``, so a
    # missing ``continue`` (a row in two baskets) or a basket forgotten in
    # the sum breaks the equality. The death-only audit was blind to the
    # right half — chatwoot's 4 post-lattice births (uf_cases_split UF-CS-*)
    # had NO lineage record at all.
    conservation_ok = (
        len(reg.rows) + len(births) - deaths == len(emitted_ids)
    )
    out: dict[str, Any] = {
        "enabled": True,
        "seam": reg.seam,
        "snapshot": len(reg.rows),
        "emitted": len(emitted_ids),
        "deaths": deaths,
        "survived": survived,
        "births_count": len(births),
        "births_truncated": len(births) > _UNACCOUNTED_CAP,
        "births": births[:_UNACCOUNTED_CAP],
        "conservation_ok": conservation_ok,
        "re_id": reid_members + reid_name,
        "re_id_by_members": reid_members,
        "re_id_by_name": reid_name,
        "abstained": abstained,
        "id_bound": len(id_bound),
        "name_only": len(name_only),
        "unaccounted_count": len(unaccounted),
        "unaccounted_truncated": len(unaccounted) > _UNACCOUNTED_CAP,
        "unaccounted": unaccounted[:_UNACCOUNTED_CAP],
        "lane_retained": lane_retained,
        "lane_moved": lane_moved,
        # fixb121 M6 — how many (id, writer) claims arrived and how many
        # BECAME a channel. ``rejected`` > 0 = claims about rows that
        # survived, were re-minted/abstained, or were never in the snapshot:
        # anti-laundering visible from the board, not hidden in code.
        "writer_reports": writer_reports,
        "writer_reports_bound": writer_reports_bound,
        "writer_reports_rejected": writer_reports - writer_reports_bound,
        "channels": dict(sorted(channels.items())),
        "channel_overclaim_count": len(overclaim),
        "channel_overclaim": overclaim[:_UNACCOUNTED_CAP],
    }
    # fixb140 — the key appears ONLY when the lane move really DELETED rows
    # (flag ON and at least one row with member_absorbed 0.00). Otherwise the
    # stamp is byte-identical to the pre-fix one.
    if lane_deleted:
        out["lane_deleted"] = lane_deleted
    return out


def unaccounted_exhibits() -> list[str]:
    """The FULL (uncapped) list of unaccounted ids from the last reconcile.

    Deliberately NOT read from ``scan_meta.journey_lineage_audit.unaccounted``:
    that carries the ``_UNACCOUNTED_CAP`` display cap, while the invariant
    hook's ``count`` must be full (the same blindness class M2 cures in the
    cap-30). An empty list when OFF ⇒ the hook stamps count 0 / never fires.
    """
    reg = _registry()
    return list(reg.unaccounted_ids) if reg is not None else []
