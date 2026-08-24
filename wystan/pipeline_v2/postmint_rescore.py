"""postmint_rescore — B100: a Law C regrade of rows minted AFTER the contract.

THE CLASS (world census 2026-08-03, 54 boards of the KS51 era): UF rows
born or renamed AFTER ``run_naming_contract`` (Law C) carry a
``name_confidence`` with NO ``name_evidence`` and are never regraded —
confidence from the producer's head, not from a rung. Live exhibits:
infisical ``UF-CS-c8e3fc3fd5`` "Layouts addmcpservermodal" (+11 UF-CS on
the board), highlight ×3 UF-CS (``uf_cases_split``), langfuse
``UF-AGENT-001`` (``agent_surface``) — all ``medium`` / evidence None.

MECHANISM (deterministic, $0): the ``rescore_uf_confidence`` seam in
``naming_contract`` (B57 Seg2) already re-applies Law C idempotently over
the CURRENT rows — the 6.7e adjudicator uses it too. Here that same seam
is hung as a HOOK on the producer stages (the stage-hooks law: a hook
lives at its producer), with the same argument set as the 6.7e site.

ROW-SCOPE (why not a bare full re-run): the late seams live AFTER the
6.7e adjudicator and 6.98 ``synth_quality``. A bare full re-run of Law C
there WOULD ERASE other people's honest grades — the verified
``adjudicated:*`` rungs of 6.7e and the B40 lift ``["member-agreement"]``
(a synth row under the synth cap would fall back to ``low``) — i.e. it
would LOWER the confidence of rows whose rungs fired earlier, and break
the seam's idempotence. Hence: EXACTLY the set the producer just minted,
renamed, or whose membership it rewrote is regraded (a diff of ``id`` /
``name`` / ``member_flow_ids`` before and after — LOCAL to the producer);
every other row is restored verbatim. This is not a rubric override (the
Law C verdict over touched rows stands) — it is the law of inertia.

THE THIRD CHANNEL (fixb106/R0): a producer may rewrite not the row but
the NAMES OF ITS MEMBERS — and then the Law C evidence goes stale just
the same, though neither ``name`` nor ``member_flow_ids`` changed. Live
seam: ``apply_flow_name_v2`` (``phase_finalize.py:4822``) mints verb-led
flow names 1500 rows AFTER Law C (``:3289``) scored those same rows by
their OLD (path-echo) names — the Law C verb channel reads exactly the
member NAMES (``naming_contract.py:3182-3187``). So the snapshot
optionally carries the member-name tuple as a third element (``None`` =
the producer did not arm the channel ⇒ the old three hooks are identical).

HONESTY: confidence is written EXCLUSIVELY by Law C. This module has no
thresholds of its own, no rungs of its own, and lifts nothing itself; a
synthesized row stays ``low`` with ``["synthesized"]`` (B78-it2 Goal 2b
inside Law C). Identity / membership / ``product_feature_id`` untouched.
The regrade is BIDIRECTIONAL: a row whose ``high`` rested on names that
no longer exist honestly falls to ``medium`` — a rescore that only lifts
would not be a rescore (P4: 61 UP / 8 DOWN on the KS54 world).

VERIFIED CITATIONS SURVIVE THE REGRADE: the 6.7e adjudicator rungs
(``adjudicated:*``) are verdicts of a deterministic verifier over
citations from the code, not a function of member names; they are
restored from the row's own ``name_evidence`` and passed back into Law C
as ``adjudicated_sources``, otherwise a late hook would erase someone
else's honest grade (the same inertia law, inside a touched row).

Flag ``WYSTAN_UF_POSTMINT_RESCORE`` default ON (flip-pack #19, KS54;
R0 channel KS55). ``=0`` ⇒ no reads, no mutation, no key in
``scan_meta`` ⇒ the board is byte-identical.
"""

from __future__ import annotations

import os
from typing import Any, Mapping

__all__ = [
    "POSTMINT_RESCORE_ENV",
    "VERBLESS_NO_HIGH_ENV",
    "postmint_rescore_enabled",
    "postmint_uf_rescore",
    "snapshot_uf_state",
    "verbless_no_high_enabled",
]

POSTMINT_RESCORE_ENV = "WYSTAN_UF_POSTMINT_RESCORE"


def postmint_rescore_enabled() -> bool:
    """B100 — default **ON** (flip-pack #19, KS54). ``=0`` disables: no
    hook, no key, the board byte-identical."""
    return os.environ.get(POSTMINT_RESCORE_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _uid(uf: Any) -> str:
    return str(getattr(uf, "id", "") or "")


def _name(uf: Any) -> str:
    return str(getattr(uf, "name", "") or "")


def _conf(uf: Any) -> str:
    return str(getattr(uf, "name_confidence", "") or "")


def _evidence(uf: Any) -> list[str] | None:
    ev = getattr(uf, "name_evidence", None)
    return None if ev is None else [str(e) for e in ev]


def _members(uf: Any) -> tuple[str, ...]:
    return tuple(str(m) for m in (getattr(uf, "member_flow_ids", None) or ()))


#: One row's snapshot: ``(name, member_flow_ids, member_names | None)`` —
#: exactly the channels whose change makes Law C evidence stale (the name —
#: a different name was scored; membership — resource/verb rungs derive
#: from members; member NAMES — the Law C verb channel reads them). A third
#: element of ``None`` ⇒ the producer did not arm it ⇒ channel unobserved.
UFState = tuple[str, tuple[str, ...], tuple[str, ...] | None]


def _member_name_index(flows: Any) -> dict[str, str]:
    """``{member_id: flow_name}`` by EXACTLY the builder Law C uses
    (``naming_contract._uf_flow_maps`` — keyed by both ``uuid`` and ``name``),
    so member-name resolution in hook and rubric cannot diverge."""
    from wystan.pipeline_v2.naming_contract import _uf_flow_maps

    flow_name_by_id, _origin, _by_id = _uf_flow_maps(flows or ())
    return flow_name_by_id


def _member_names(uf: Any, idx: Mapping[str, str]) -> tuple[str, ...]:
    """Member names as Law C reads them (``_members`` —
    ``naming_contract.py:3182-3184``): an unresolved id stands for itself."""
    return tuple(idx.get(m, m) for m in _members(uf))


def snapshot_uf_state(
    user_flows: list[Any] | None, *, flows: Any = None,
) -> dict[str, UFState] | None:
    """``{uf_id: (name, member_flow_ids, member_names)}`` — the snapshot
    BEFORE the producer, the input for the touched-row diff. ``flows`` arms
    the third channel (member NAMES) — passed ONLY by producers that rewrite
    those names (``flow_name_v2``); without it the third element is ``None``
    and hook behaviour is byte-identical to fixb106. ``None`` when the flag
    is off (the hook then never runs: the OFF path costs one env read)."""
    if not postmint_rescore_enabled():
        return None
    idx = _member_name_index(flows) if flows is not None else None
    return {
        _uid(uf): (
            _name(uf), _members(uf),
            None if idx is None else _member_names(uf, idx),
        )
        for uf in (user_flows or [])
    }


def _touched_ids(
    user_flows: list[Any],
    before: Mapping[str, UFState],
    name_idx: Mapping[str, str] | None = None,
) -> set[str]:
    """Rows THIS producer MINTED (a new ``id`` that did not exist before
    it), RENAMED, whose MEMBER SET it changed, or whose MEMBER NAMES it
    rewrote (the diff is local to the producer — not a global
    member-watch): a residual cases-split parent keeps its name but hands
    its members to the children, so its rungs (resource/verb from members)
    now describe a set that no longer exists; and ``flow_name_v2`` leaves
    both the row and its membership untouched while rewriting exactly the
    name rows Law C derived the verb channel from.

    Re-parent / attach / drop never enter the set — they touch neither the
    name, nor the membership, nor the member names."""
    touched: set[str] = set()
    for uf in user_flows:
        uid = _uid(uf)
        if not uid:
            continue
        prev = before.get(uid)
        if prev is None:
            touched.add(uid)
            continue
        prev_name, prev_members, prev_mnames = prev
        if prev_name != _name(uf) or prev_members != _members(uf):
            touched.add(uid)
            continue
        # The third channel is observed only when the producer armed it.
        if prev_mnames is not None and name_idx is not None:
            if prev_mnames != _member_names(uf, name_idx):
                touched.add(uid)
    return touched


def _adjudicated_from_evidence(
    user_flows: list[Any],
) -> dict[str, dict[str, list[str]]]:
    """Restore ``{uf_id: {"resource": [...], "verb": [...]}}`` from the
    ``adjudicated:<rung>`` tags Law C already put in ``name_evidence``.

    This is NOT a new evidence source: a rung reaches the tag only after
    the deterministic 6.7e verifier accepted the citation
    (``stage_6_7e_adjudicator``:777-794), and the rung's channel is its own
    frozen constant. Without this a late hook would erase verified
    citations on touched rows because ``rescore_uf_confidence`` cannot.
    """
    from wystan.pipeline_v2.stage_6_7e_adjudicator import (
        _VERB_CITATION_RUNGS,
    )

    out: dict[str, dict[str, list[str]]] = {}
    for uf in user_flows:
        uid = _uid(uf)
        if not uid:
            continue
        for tag in (_evidence(uf) or ()):
            if not tag.startswith("adjudicated:"):
                continue
            rung = tag.split(":", 1)[1]
            if not rung:
                continue
            channel = "verb" if rung in _VERB_CITATION_RUNGS else "resource"
            entry = out.setdefault(uid, {"resource": [], "verb": []})
            if rung not in entry[channel]:
                entry[channel].append(rung)
    return out



#: fixb138 / NS-43b — a VERBLESS journey name never ships ``high``.
#: Default **OFF**; ``=1``/``true`` arms it. Unset/``0``/``false`` ⇒ every
#: grade byte-identical (kill-switch forever).
#:
#: The flag arms TWO nets over the same hole, in two seams:
#:   1. ``naming_contract.rescore_uf_confidence`` post-pass (round 2 — the
#:      PRODUCER seam): the verbless-no-high demote + the ``verb:name-lead``
#:      evidence-honesty stamp. This is where the keyed path actually
#:      grades UF-025.
#:   2. the Law-C rescore delta below (round 1 — a second net): a cap LIFT
#:      is not evidence, so a row that goes UP only because a ``shape:*``
#:      ceiling was removed re-derives from what it ACTUALLY carries.
#: Round 1 was measured to see NO delta on the keyed path (the producer
#: seam had already settled the grade); it is retained as a harmless
#: belt-and-suspenders arm rather than deleted, since it guards a
#: genuinely different entry (a lift, not a name shape).
VERBLESS_NO_HIGH_ENV = "WYSTAN_VERBLESS_NO_HIGH"


def verbless_no_high_enabled() -> bool:
    """fixb138 gate — see :data:`VERBLESS_NO_HIGH_ENV`."""
    import os as _os

    return _os.environ.get(
        VERBLESS_NO_HIGH_ENV, "0"
    ).strip().lower() in {"1", "true"}


def _shape_tags(ev: "list[str] | None") -> set:
    return {e for e in (ev or []) if str(e).startswith("shape:")}


def _law_c_supports_high(ev: "list[str] | None") -> bool:
    """Law C's own bar: ``verb_grounded ∧ res_grounded``.

    Read off the evidence the row actually carries. A ``resource*`` /
    ``verb*`` entry is a grounding stamp; ``missing:*`` is its negation.
    ``structural-route`` alone is a SHAPE fact, not verb grounding — that
    is precisely the UF-025 hole: 'Pixel share' is verbless.
    """
    toks = [str(e) for e in (ev or [])]
    if any(t.startswith("missing:") for t in toks):
        return False
    res = any(t == "resource" or t.startswith("resource:") for t in toks)
    verb = any(
        t == "verb" or t.startswith("verb:") or t.startswith("verb-")
        or t.startswith("structural:verb-composition")
        for t in toks
    )
    return res and verb


def postmint_uf_rescore(
    producer: str,
    user_flows: list[Any] | None,
    before: Mapping[str, UFState] | None,
    *,
    product_features: list[Any],
    flows: list[Any] | None = None,
    product_strings: Any = None,
    routes_index: Any = None,
    uf_authored_names: Mapping[str, Any] | None = None,
    keeper_on: bool = True,
    repo_root: Any = None,
    scan_meta: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """A Law C regrade over the rows ``producer`` just minted, renamed or
    whose membership it rewrote (in place). The argument binding is the
    same as at the 6.7e site (``rescore_uf_confidence``).

    ``None`` (and NO key in ``scan_meta``) when: the flag is OFF, there is
    no snapshot, the producer did none of those things, or the regrade
    moved nothing — an inert board stays byte-identical.
    """
    if before is None or not postmint_rescore_enabled():
        return None
    rows = list(user_flows or [])
    if not rows:
        return None
    # The third channel costs one pass over the flows — and only when the
    # producer armed it in the snapshot (otherwise no row compares it).
    name_idx = (
        _member_name_index(flows)
        if any(st[2] is not None for st in before.values()) else None
    )
    touched = _touched_ids(rows, before, name_idx)
    if not touched:
        return None

    # Snapshot of ALL rows (positional — Law C mutates fields in place and
    # never adds or removes rows), so untouched ones can be restored.
    saved = [(_name(uf), _conf(uf), _evidence(uf)) for uf in rows]
    # The verified 6.7e citations return to the rubric with the row.
    adjudicated = _adjudicated_from_evidence(rows)

    from wystan.pipeline_v2.naming_contract import rescore_uf_confidence

    rescore_uf_confidence(
        product_features,
        rows,
        list(flows or []),
        product_strings=product_strings,
        routes_index=routes_index,
        uf_authored_names=uf_authored_names,
        keeper_on=keeper_on,
        repo_root=repo_root,
        adjudicated_sources=adjudicated or None,
    )

    rows_regraded = 0
    rows_renamed = 0
    evidence_written = 0
    # Bidirectional accounting — a rescore that only lifts is no rescore.
    _rank = {"low": 0, "medium": 1, "high": 2}
    rows_up = 0
    rows_down = 0
    tele_cap_lift_held: list = []
    for uf, (old_name, old_conf, old_ev) in zip(rows, saved):
        if _uid(uf) not in touched:
            # The law of inertia: another's row leaves the seam exactly
            # as the producer left it (no stripping of anyone else's
            # adjudicated:* / member-agreement grades).
            uf.name = old_name
            uf.name_confidence = old_conf
            uf.name_evidence = None if old_ev is None else list(old_ev)
            continue
        new_ev = _evidence(uf)
        if _name(uf) != old_name:
            rows_renamed += 1
        if _conf(uf) != old_conf or new_ev != old_ev:
            rows_regraded += 1
        if not old_ev and new_ev:
            evidence_written += 1
        _delta = _rank.get(_conf(uf), -1) - _rank.get(old_conf, -1)
        # ── fixb138 / NS-43b — a cap LIFT is not evidence ─────────────
        # Warden §43 exhibit UF-025 'PixelShareForm' -> 'Pixel share':
        # promoted medium -> high while name_evidence went 3 -> 2
        # (gained=[], lost=['shape:raw-identifier']). The ONLY change was
        # the shape cap lifting, and the SURVIVING evidence
        # (structural-route + resource:route, verbless) never supported
        # high on its own. Lifting a ceiling removes a limit; it does not
        # add a reason. The row re-derives from what it actually carries.
        if (_delta > 0 and verbless_no_high_enabled()
                and _shape_tags(old_ev) - _shape_tags(new_ev)
                and not (set(map(str, new_ev or ())) - set(map(str, old_ev or ())))
                and not _law_c_supports_high(new_ev)):
            uf.name_confidence = old_conf
            tele_cap_lift_held.append(_uid(uf))
            _delta = 0
        if _delta > 0:
            rows_up += 1
        elif _delta < 0:
            rows_down += 1

    if not (rows_regraded or rows_renamed):
        return None
    tele: dict[str, Any] = {
        "rows_touched": len(touched),
        "rows_regraded": rows_regraded,
        "rows_renamed": rows_renamed,
        "evidence_written": evidence_written,
    }
    if name_idx is not None:
        # Only for producers that armed the member-name channel (R0):
        # two-way accounting is that channel's GATE, not general telemetry,
        # so the keys do not appear in the three pre-fixb106 hooks (their
        # scan_meta.postmint_rescore stays byte-identical).
        tele["rows_up"] = rows_up
        tele["rows_down"] = rows_down
    if tele_cap_lift_held:
        # Only appears when the rule actually held a row, so every
        # pre-fixb138 telemetry block stays byte-identical.
        tele["cap_lift_held"] = sorted(tele_cap_lift_held)
    if scan_meta is not None:
        scan_meta.setdefault("postmint_rescore", {})[producer] = tele
    return tele
