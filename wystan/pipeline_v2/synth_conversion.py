"""fixb145 — synth CONVERSION: the single writer of ``UserFlow.synthesized``
after the journey layer has settled.

THE CLASS (world census, KS77 world 9bf82df, 55 boards / 4011 UF): **653**
rows carry ``synthesized: true``; the operator ruling excludes them from the
official journey metric on BOTH sides of the fraction. The census asked which
of them hide a REAL journey and found that the tag, not the row, is the
defect:

  * every surviving row is member-FUL and grounded (member-less coverage
    seeds are already demoted to ``scan_meta.system_flow_seeds`` by
    :mod:`synth_quality`) — 0/639 live rows are hollow;
  * the 6.7d backstop's arm-1 reassign refuses in 781/799 world cases at
    ``arm1_no_majority_uf`` — no journey ANYWHERE on the board is
    majority-owned by the PF's flows, because 45.7% of dev features and
    54.3% of routes never reached the 6.7d Call-1 digest at all. The
    backstop is doing its job; the material was never offered to the draw;
  * the rows are stamped ``low`` + ``['synthesized']`` by the B78-it2 cap
    (:mod:`naming_contract`) BEFORE Law C ever grades them. Measured on the
    infisical / langfuse / teable cap OFF-vs-ON replay pair (200
    board-aligned rows, $0, same channel): **171 (85.5%) earn ``high`` on
    their own Law-C evidence**, with ZERO name drift between arms and ZERO
    drift on the 282 non-synthesized rows.

This module owns the FIELD FLIP only. The GRADING decision lives where the
evidence is (:func:`naming_contract._apply_uf_name_laws`); the apply is here,
mirroring the ``spray_absorption`` precedent — the naming module's §4.8
identity law forbids identity writes inside it, and ``synthesized`` is an
identity claim, not a display.

SEAM (load-bearing): both lanes run at the PRE-OUTPUT seam of Stage 7, after
``emission_hard_gate`` (counts NON-synthesized journeys per PF) and
``emission_integrity`` (drops a homeless SYNTHESIZED journey but is BLOCKED
by a homeless real one). Flipping the field earlier would move husk folds and
coverage counts — a structural change neither lane is scoped to make. Run
here, the lanes change the emitted field and nothing else.

Lanes
-----
(1) ``unsynth_authored_cli`` — an AUTHOR-DECLARED CLI command journey is not
    a coverage claim. Its name is the maintainer's own sentence read out of
    the command's registration site (cobra ``Short:`` / commander
    ``.description()``), which is why :mod:`naming_contract` already carves
    it out of the confidence cap (fixb128 NS-2) and why 27 of the 31 such
    rows in the world already read ``high``. Keeping ``synthesized: true`` on
    them was the sole cause of a +0.80pp inflation in the journey-denominator
    ruler (their ``high`` counted in the numerator while the rows were
    excluded from the denominator). TEMPLATE-named CLI rows
    (``cli-template`` — the author declared no summary, so the ENGINE
    composed ``<Verb> <bin>``) are deliberately NOT converted: the engine's
    own doctrine says such a row "ADMITS the engine composed the name" and
    stays fair game for the naming laws.

(2) ``apply_synth_conversion`` — un-synthesize the rows
    :mod:`naming_contract` graded ``high`` under BOTH ratified guards
    (PF-echo refusal + per-PF quota). The guard verdicts are computed at the
    Law-C seam and handed here as ids; this module never re-derives them.

Flags (registered in ``scan_result_cache.ENV_OUTPUT_FLAGS`` — append only,
no KEY_SCHEMA bump; the bump rides the operator's flip commit):
  * ``WYSTAN_CLI_JOURNEY_UNSYNTH``       — lane 1 (default ON, №44)
  * ``WYSTAN_SYNTH_CONVERSION``          — lane 2 (default ON, №44)
  * ``WYSTAN_UNSYNTH_SIBLING_DUP_GUARD`` — lane 1's fixb147 duplicate
    guard (default ON, №46)
  * ``WYSTAN_CLI_BIND_GATE``             — lane 1's fixb148 bind gate
    (V2∨V4 over no-handler CLI rows) (default ON, №46)
Unset/``0`` ⇒ the lane returns ``None`` before any mutation ⇒ no
``scan_meta`` key ⇒ serialized output byte-identical.

ORDER inside lane 1 (load-bearing, and the two suppressions are disjoint on
the measured board): the fixb147 SIBLING-DUP guard runs FIRST, the fixb148
BIND gate SECOND, and a row is counted by exactly ONE of them — first
verdict wins. On trigger.dev the dup guard removes the 2 CORRECTLY-bound
duplicates (UF-162/163, whose members merged into flows real siblings own)
and the bind gate removes the 3 MISBOUND rows (UF-164/165/166); running the
gate first would still leave the same net, but the counters would attribute
the wrong cause, and a counter that misattributes is a forensics lie.
"""

from __future__ import annotations

import os
import re
from typing import Any

__all__ = [
    "CLI_BIND_GATE_ENV",
    "CLI_UNSYNTH_ENV",
    "SYNTH_CONF_CAP_ENV",
    "SYNTH_CONVERSION_ENV",
    "UNSYNTH_DUP_GUARD_ENV",
    "apply_synth_conversion",
    "cli_bind_arm",
    "cli_bind_gate_enabled",
    "cli_unsynth_enabled",
    "conversion_verdict_ids",
    "doctrine_refusal",
    "record_conversion_verdict",
    "reset_conversion_registry",
    "synth_conf_cap_enabled",
    "synth_conversion_enabled",
    "unsynth_authored_cli",
    "unsynth_dup_guard_enabled",
]

CLI_UNSYNTH_ENV = "WYSTAN_CLI_JOURNEY_UNSYNTH"

#: fixb148 — lane 1's BIND gate (V2∨V4), on its OWN flag. Default **ON**
#: since flip-pack №46 (KEY_SCHEMA 81); explicit
#: ``0``/``false``/``off``/``no``/``""`` is the kill-switch forever and
#: removes BOTH halves — the mint stamp and the gate.
CLI_BIND_GATE_ENV = "WYSTAN_CLI_BIND_GATE"

#: fixb147 / NS-50a-b — lane 1's SIBLING-DUPLICATE guard, on its OWN flag.
#: Default **ON** since flip-pack №46 (KEY_SCHEMA 81); explicit
#: ``0``/``false``/``off``/``no``/``""`` is the kill-switch forever and
#: leaves lane 1 byte-identical to KS80.
UNSYNTH_DUP_GUARD_ENV = "WYSTAN_UNSYNTH_SIBLING_DUP_GUARD"

#: fixb145 — the B78-it2 synth confidence cap, split off its Seg-A RIDER.
#: Until now the cap that hard-stamps every ``synthesized`` row ``low`` +
#: ``['synthesized']`` (``naming_contract``) read
#: ``WYSTAN_FOLD_EVIDENCE_WEIGHT`` — a flag whose documented job is the
#: 6.86 walk-evidence gate. One env could not arm the mint gate and disarm
#: the naming cap independently, so the cap had no kill-switch of its own.
SYNTH_CONF_CAP_ENV = "WYSTAN_SYNTH_CONF_CAP"

#: fixb145 lane 2 — the guarded conversion behavior. Default OFF.
SYNTH_CONVERSION_ENV = "WYSTAN_SYNTH_CONVERSION"

#: Bound on the telemetry row sample (forensics, never a behavior knob).
_TELE_CAP = 60

_TRUTHY = {"1", "true", "yes", "on"}

# ── NS-46a — the SCAN-SCOPED conversion-verdict registry ──────────────────
# MEASURED (warden №46, keyed infisical): the post-6.7e PRODUCER hooks
# (``flow_name_v2`` phase_finalize:5124, ``agent_surface`` :4236) re-enter
# ``_apply_uf_name_laws`` with ``post_adjudicator=False``. The Channel-A
# defer predicate then reads ``will_run()`` = True, disarms the lane, and the
# B78 cap — which no longer sees an admitted set — RE-STAMPS the touched rows
# back to ``low`` + ``['synthesized']``. The pre-output apply, reading the
# state invariant, then skips them: 29 lifted, **8 silently voided, zero
# counters**. Exactly the silent-loss disease this arc keeps finding.
#
# The cure is the fixb136 scan-scoped registry precedent: A PROMISE MUST NOT
# CROSS A FILTER — and here, must not cross a RE-ENTRY either. A row that has
# earned a conversion verdict at the post-adjudicator seam is recorded here;
# the cap consults the registry on every later re-entry and never re-stamps a
# row that holds one. Legitimate downstream QUALITY demotes (fixb138 verbless,
# R5 conf-drop) still apply — they write confidence through their own laws,
# not through the cap — and any verdict they void is COUNTED at the apply
# seam, never lost in silence.
#
# Scan-scoped: reset once per scan at ``run_naming_contract`` entry (the
# single primary seam). Module state is the same shape fixb136 uses; a scan is
# single-threaded through the finalize phase.
_VERDICT_IDS: set[str] = set()


def reset_conversion_registry() -> None:
    """Clear the registry — called once per scan at the primary naming seam."""
    _VERDICT_IDS.clear()


def record_conversion_verdict(ids: Any) -> None:
    """Record rows that earned a conversion verdict (guards + rubric)."""
    for i in ids or ():
        _VERDICT_IDS.add(str(i))


def conversion_verdict_ids() -> frozenset[str]:
    """Rows holding a standing conversion verdict this scan."""
    return frozenset(_VERDICT_IDS)


def cli_unsynth_enabled() -> bool:
    """fixb145 lane 1 — default **ON** since flip-pack №44 (KEY_SCHEMA 79).

    Unset ≡ explicit ``"1"``: an AUTHOR-DECLARED CLI command journey stops
    wearing ``synthesized``. Explicit ``0``/``false``/``off``/``no`` is the
    kill-switch FOREVER (output byte-identical to pre-fixb145).

    Keyed probe (symmetric ruler, warden №46): ollama 45.5 -> 71.4 (+25.9pp,
    10 rows all-high), lobe-chat 91.6 -> 89.6 (-2.0pp — the 3 template-named
    mediums honestly counted), tracecat flat. The negative is RECORDED, not
    hidden: the synth tag on a registration-site FACT was wrong regardless of
    the grade it carries, and truth that lowers a number does not block it."""
    return os.environ.get(CLI_UNSYNTH_ENV, "1").strip().lower() \
        not in {"0", "false", "off", "no"}


def doctrine_refusal(
    name: str,
    name_evidence: Any,
    verbs: Any,
    structural_segments: Any,
) -> str | None:
    """GUARD 3 — the display-doctrine floor. Refusal reason, or ``None``.

    Lives here (not inside ``naming_contract``) so the conversion POLICY has
    one owner and is directly testable against the measured exhibits;
    ``naming_contract`` supplies the vocabulary it has already loaded and
    calls this at the cap-decision point.

    (a) RESIDUAL ``shape:*`` evidence — the R5 shape lanes have already
        judged this display defective (``shape:raw-identifier`` /
        ``shape:unresolved-dir-token``). A conversion never overrules a
        standing shape verdict. Same tag family ``postmint_rescore`` reads.
    (b) The RESOURCE PART — the name minus its leading template verbs via
        ``uf_synth_fold.noun_phrase``, the SAME helper ``is_pf_echo`` uses
        in guard 1, so both guards read ONE ruler — restates the BUILD
        LAYOUT instead of a capability. Vocabulary is the shipped
        ``structural_segments`` YAML list (app/apps/backend/frontend/index/
        lib/packages/pages/routes/server/src/web/www), already consumed by
        ``synth_quality``'s noun-lead set. Nothing new is invented.

    (b) is deliberately NOT "contains a structural token": MEASURED false
    refusal on infisical UF-201 'Browse & manage digital ocean app platform
    authorize', where ``app`` is the vendor's own product noun (DigitalOcean
    App Platform). One build word inside a multi-word product phrase is
    legitimate English. Two shapes are not:

      * SOLE-STRUCTURAL   the whole resource part IS one build word
                          ('Manage src' — infisical UF-227);
      * STRUCTURAL-CHAIN  >= 2 of them, i.e. the name restates a PATH
                          ('Manage project frontend src pages project' —
                          infisical UF-221, the de-slugged anchor
                          ``project-route-frontend-src-pages-project``).

    NOT covered, and stated rather than papered over: a VERBLESS
    noun-phrase name ('Related Resources', infisical UF-134). Its in-tree
    owner is the fixb138/NS-43b lane, which demands POSITIVE proof of
    verblessness (the lead token IS the row's own resource noun) precisely
    because reading the verb table's COMPLEMENT as proof was REFUTED on a
    52-board census — 126 firings, 79% of them on plainly verb-led names.
    Re-running that refuted inversion here is not an option; the gap is an
    operator ruling, not an improvisation.
    """
    for e in (name_evidence or ()):
        if str(e).startswith("shape:"):
            return f"residual-{e}"
    segs = {str(t).strip().lower() for t in (structural_segments or ())
            if str(t).strip()}
    if not segs:
        return None
    from wystan.pipeline_v2.uf_synth_fold import noun_phrase

    verb_set = verbs if isinstance(verbs, frozenset) else frozenset(
        str(v).lower() for v in (verbs or ()))
    res = [t for t in re.split(
        r"[^a-z0-9]+", noun_phrase(str(name or ""), verb_set).lower()) if t]
    if not res:
        return None
    hits = [t for t in res if t in segs]
    if len(res) == 1 and hits:
        return "sole-structural-segment"
    if len(hits) >= 2:
        return "structural-segment-chain"
    return None


def synth_conf_cap_enabled() -> bool:
    """The B78-it2 synth confidence cap, on its OWN flag.

    DEFAULT PRESERVES BOTH HISTORICAL STATES EXACTLY: unset ⇒ fall back to
    ``fold_evidence_weight_enabled()``, which is what the cap read before
    fixb145. A board running the pre-existing ``WYSTAN_FOLD_EVIDENCE_WEIGHT
    =0`` kill-switch therefore keeps its uncapped naming, and every other
    board keeps the cap — no silent re-arming (the trap a naive
    "new flag defaults ON" split would have sprung).

    Explicit ``WYSTAN_SYNTH_CONF_CAP=0`` is the cap's own kill-switch
    forever, and it disarms ONLY the cap — the 6.86 walk-evidence gate the
    old flag also controls stays exactly as configured.
    """
    raw = os.environ.get(SYNTH_CONF_CAP_ENV)
    if raw is None or not raw.strip():
        from wystan.pipeline_v2.stage_6_86_anchored_mint import (
            fold_evidence_weight_enabled,
        )
        return fold_evidence_weight_enabled()
    return raw.strip().lower() in _TRUTHY


def synth_conversion_enabled() -> bool:
    """fixb145 lane 2 — default **ON** since flip-pack №44 (KEY_SCHEMA 79).

    Unset ≡ explicit ``"1"``: a synthesized row that earns ``high`` on its own
    Law-C evidence AND clears all three guards (NS-43a PF-echo refusal,
    per-PF quota, display-doctrine floor) drops ``synthesized``. Explicit
    ``0``/``false``/``off``/``no`` is the kill-switch FOREVER — the guards
    never run, no verdict is published, nothing is un-synthesized.

    On KEYED boards the conversion defers to the post-6.7e seam (Channel-A
    kill); on keyless it runs at the primary seam. Every verdict is
    accounted in the 5-bucket ledger with ``sum_ok``."""
    return os.environ.get(SYNTH_CONVERSION_ENV, "1").strip().lower() \
        not in {"0", "false", "off", "no"}


def unsynth_dup_guard_enabled() -> bool:
    """fixb147 / NS-50a-b — lane 1's SIBLING-DUPLICATE guard, default **ON**
    since flip-pack №46 (KEY_SCHEMA 80 -> 81, 2026-08-14).

    Unset ≡ explicit ``1`` byte-identically. Explicit
    ``0``/``false``/``off``/``no`` (and explicit ``""``) restores
    KEY_SCHEMA 80 exactly — no resolution, no suppression, no new
    telemetry keys ⇒ byte-identical board — and stays a kill-switch
    FOREVER. The truthy set is preserved LITERALLY across the flip; only
    the get-default moved ``""`` → ``"1"``.

    Keyed proof (trigger.dev + inbox-zero): 3 suppressions, ALL verified
    true sibling duplicates (trigger.dev UF-162/163, inbox-zero UF-111),
    and the board's ONLY trace is the ``synthesized`` field — no row is
    deleted, no membership moves. Inert on novu and ollama. Wardens №51
    CLEAR / №52 CLEAR.

    THE DEFECT (warden №50, keyed trigger.dev ON-arm): a fix that RESCUES a
    row another hand deletes imports that row's LATENT defects onto the
    freed tile. Lane ``cli_journey_unsynth`` fired for the FIRST time on
    trigger.dev (converted 0 -> 5) and 2 of its 5 outputs were hollow +
    substantive duplicates — UF-163 'Deploy your Trigger.dev project to the
    cloud' (mc=1, loc=0) whose SOLE member ``eea9ba0e…`` does not resolve to
    any live flow because it sits in ``flows[].merged_from`` of
    ``deploy-application-flow``, which UF-072 'Deploy tasks via CLI'
    (mc=6, loc=1076) ALREADY owns on the SAME PF; and UF-162 'Analyze your
    build output' over the pre-merge uuid of ``analyze-project-flow``, owned
    by UF-073. Both detectors were blind: ``check_hollow_rows`` nets them
    against ``abstained_row_ids`` (flip №26) and the uf-dup-names check is
    string-shaped, so a duplicate wearing the author's own sentence reads
    clean."""
    return os.environ.get(
        UNSYNTH_DUP_GUARD_ENV, "1").strip().lower() in _TRUTHY


def cli_bind_gate_enabled() -> bool:
    """fixb148 — lane 1's BIND gate (V2∨V4), default **ON** since flip-pack
    №46 (KEY_SCHEMA 80 -> 81, 2026-08-14).

    Unset ≡ explicit ``1`` byte-identically — both halves (the mint's
    ``declarant_files`` stamp and the gate itself) are live. Explicit
    ``0``/``false``/``off``/``no`` (and explicit ``""``) restores fixb147
    exactly — neither the stamp nor the gate exists, so the field never
    serializes — and stays a kill-switch FOREVER. The truthy set is
    preserved LITERALLY across the flip; only the get-default moved
    ``""`` → ``"1"``.

    Keyed proof (battery 40): lane precision 40.7% -> 91.7%; the 6
    suppressed rows are 6/6 MISBOUND by name under hand adjudication, the
    converted rows are CORRECT, and ollama's 9 handler-ful controls are
    untouched. Floor-inertness proved — the release stays live with 5 rows
    suppressed. Warden №52 CLEAR.

    CAVEAT NS-52a (coordinator's ruling — KEEP and NAME it): the V2 arm
    (declarant == entry) is VACUOUS on every live population measured
    (V2 ⊆ V4 in the corpus, 0/12 live V2 decisions). It is kept as
    defense-in-depth against the MEASURED cross-cluster token blindness of
    V4 (lobe-chat inspect/list across two clusters). Any future tuning of
    this gate MUST carry the ledger mark "V2 unwitnessed" — the arm
    becomes load-bearing only if V4 is ever narrowed.

    THE DEFECT (probe iteration-2, 57 minted CLI command journeys across 8
    boards): the mint's NO-HANDLER rung binds a command to its member by
    TOKEN OVERLAP against the flow's NAME (``cli_command_journeys``, the
    ``else`` branch), and a one-token agreement is not a binding. Measured
    on hand-adjudicated ground truth over the 28 handler-null rows: 11
    CORRECT, 16 MISBOUND, 1 PHANTOM — the author's own sentence pointing at
    a stranger's code ('Display the current logged in user and project
    details' over ``commands/logout.ts``; 'Manage environment variables …'
    over ``commands/init.ts``). Lane 1 then CONVERTS those rows, so a
    misbinding is promoted out of the ``synthesized`` exclusion and into the
    journey ruler wearing a high-confidence authored name.

    The 9 handler-FUL rows are NOT in scope: their member is the flow
    entering the symbol the registration site NAMES (fixb128 NS-3), which is
    exact by construction. Measured cost of ignoring that scope: the V4 arm
    alone would kill all 9."""
    return os.environ.get(CLI_BIND_GATE_ENV, "1").strip().lower() in _TRUTHY


def _path_segments(path: str) -> frozenset[str]:
    """Path segments of *path*, each also without its file extension.

    ``packages/novu/src/commands/sync.ts`` ⇒ {packages, novu, src, commands,
    sync.ts, sync}. Lowercased; the stem is added beside the segment rather
    than instead of it so a directory named ``sync`` and a file named
    ``sync.ts`` are both reachable by the same token.
    """
    out: set[str] = set()
    for seg in str(path or "").replace("\\", "/").split("/"):
        s = seg.strip().lower()
        if not s:
            continue
        out.add(s)
        if "." in s:
            stem = s.rsplit(".", 1)[0].strip()
            if stem:
                out.add(stem)
    return frozenset(out)


def _command_alts(command: str) -> frozenset[str]:
    """The command token and its separator variants (``-`` ⇄ ``_``).

    ``setup-terraform`` and ``setup_terraform`` are the same author intent
    spelled by two file-naming conventions; nothing else is invented (no
    stemming, no plurals — a vocabulary is not a mechanism).
    """
    c = str(command or "").strip().lower()
    if not c:
        return frozenset()
    return frozenset({c, c.replace("-", "_"), c.replace("_", "-")})


def cli_bind_arm(
    command: str,
    declarant_files: Any,
    member_entry: str,
) -> str:
    """Which arm binds *command* to *member_entry* — ``"v2"``/``"v4"``/``""``.

    Two INDEPENDENT structural facts, either of which is proof that the flow
    the mint chose really is the command's implementation:

      * **V2 — the declaration site IS the member.** The command is
        registered in the very file the member flow enters through
        (lobe-chat ``commands/agent.ts``, trigger.dev ``commands/deploy.ts``,
        unkey ``cmd/api/analytics/root.go``). Read from the mint's own stamp,
        never re-detected.
      * **V4 — the command token is on the member's path.** The author filed
        the implementation under the command's own name (novu
        ``commands/sync.ts``, inbox-zero ``api/src/config.ts``). Directory
        OR file stem: shape-A repos file a command as a leaf module, shape-B
        repos as a directory, and a rule that reads only the file stem
        (``V4f``) costs 2 CORRECT rows on the measured corpus.

    Either arm passing is enough — they cover disjoint author conventions.
    Measured on the probe corpus (28 handler-null rows, hand-adjudicated):
    V2∨V4 keeps 11/11 CORRECT and kills 15/16 MISBOUND.

    Empty *member_entry* ⇒ ``""`` is NOT a verdict, and the caller must not
    read it as one: absence of a resolvable member is absence of evidence.
    """
    entry = str(member_entry or "").replace("\\", "/").strip()
    if not entry:
        return ""
    if entry in {str(f).replace("\\", "/").strip()
                 for f in (declarant_files or ())}:
        return "v2"
    if _command_alts(command) & _path_segments(entry):
        return "v4"
    return ""


def _merge_resolution(flows: Any) -> tuple[set[str], dict[str, str]]:
    """LIVE flow uuids + the pre-merge ``uuid -> surviving uuid`` map.

    Built from the emitted flow rows themselves (``flows[].merged_from``) —
    the same channel the board publishes, so the guard reads the merge
    history the reader will read, not a private copy of it. First writer
    wins on a collision and iteration is over the caller's order, which is
    the deterministic flow order the seam already holds.
    """
    live: set[str] = set()
    merged: dict[str, str] = {}
    for fl in (flows or ()):
        uuid = str(getattr(fl, "uuid", "") or "")
        if uuid:
            live.add(uuid)
    for fl in (flows or ()):
        uuid = str(getattr(fl, "uuid", "") or "")
        if not uuid:
            continue
        for src in (getattr(fl, "merged_from", None) or ()):
            key = str(src)
            if key and key not in live:
                merged.setdefault(key, uuid)
    return live, merged


def _entry_index(flows: Any) -> dict[str, str]:
    """``flow uuid -> entry_point_file`` (``paths[0]`` when the flow has no
    declared entry — the SAME fallback ``cli_command_journeys._entry_of``
    uses, so the gate reads a member's entry exactly as the mint did).

    Keyed by uuid only: the caller resolves a member through the merge map
    first, and that map speaks uuids.
    """
    out: dict[str, str] = {}
    for fl in (flows or ()):
        uuid = str(getattr(fl, "uuid", "") or "")
        if not uuid or uuid in out:
            continue
        entry = str(getattr(fl, "entry_point_file", "") or "").strip()
        if not entry:
            paths = list(getattr(fl, "paths", None) or ())
            entry = str(paths[0]) if paths else ""
        if entry:
            out[uuid] = entry.replace("\\", "/")
    return out


def _resolve_member(uuid: str, live: set[str], merged: dict[str, str]) -> str:
    """Walk a member uuid through the merge map to the flow that survived.

    A pre-merge uuid can chain (A merged into B, B merged into C); the walk
    follows it with a visited set so a cyclic (corrupt) map terminates
    instead of hanging a scan. A uuid that is already live, or that leads
    nowhere, is returned unchanged — the caller then finds no owner for it
    and the row is left alone.
    """
    cur = str(uuid)
    seen: set[str] = set()
    while cur not in live and cur in merged and cur not in seen:
        seen.add(cur)
        cur = merged[cur]
    return cur


def _incumbent_owner_map(
    user_flows: list[Any],
    live: set[str],
    merged: dict[str, str],
) -> dict[Any, dict[str, str]]:
    """``PF -> {resolved flow uuid: id of the REAL journey holding it}``.

    Three properties, each paid for by a measured hazard:

    * SAME-PF only. A flow held by a journey on another tile says nothing
      about this row's standing on THIS tile, and cross-tile comparison is
      not a channel this lane may open.
    * INCUMBENTS only — a row is an owner if it was ALREADY a real journey
      when the lane started (``synthesized`` falsey at entry). That is the
      literal reading of "the flow already belongs to an existing UF".
    * SNAPSHOT — built ONCE, before the first conversion, so a row this pass
      converts can never become the owner that suppresses a later one. Taken
      per-candidate instead, the verdict would depend on id order and would
      have eaten a NAMED SURVIVOR: give UF-163 a second member and UF-164
      (loc=87, legitimate) is suppressed by the row processed one index
      earlier. Cannibalising a survivor to remove a duplicate is the trade
      this arc has already paid for once.

    Cost of the snapshot, stated rather than hidden: two candidates that
    resolve onto the SAME flow with no real incumbent both convert. That
    shape is not the measured defect (which is always incumbent-vs-newcomer)
    and lives in the ledger, not in an improvised second rule.
    """
    owners: dict[Any, dict[str, str]] = {}
    for uf in sorted(user_flows, key=lambda u: str(getattr(u, "id", ""))):
        if getattr(uf, "synthesized", False):
            continue
        pf = getattr(uf, "product_feature_id", None)
        bucket = owners.setdefault(pf, {})
        for m in (getattr(uf, "member_flow_ids", None) or ()):
            bucket.setdefault(
                _resolve_member(str(m), live, merged),
                str(getattr(uf, "id", "")),
            )
    return owners


def _row(uf: Any) -> dict[str, Any]:
    return {
        "id": getattr(uf, "id", None),
        "name": getattr(uf, "name", None),
        "pf": getattr(uf, "product_feature_id", None),
        "confidence": getattr(uf, "name_confidence", None),
    }


def unsynth_authored_cli(
    user_flows: list[Any] | None,
    flows: list[Any] | None = None,
) -> dict[str, Any] | None:
    """Drop ``synthesized`` from AUTHOR-DECLARED CLI command journeys.

    ``synthesis_reason`` is KEPT — provenance survives, the coverage claim
    does not (a ``synthesized=False`` row omits the field from the dump
    entirely, so the emitted row reads ``synthesis_reason: "cli_command"``
    with no ``synthesized`` key). Nothing else is touched: name,
    ``name_confidence``, ``name_evidence``, members, home and routes are
    read-only here.

    ``flows`` (fixb147, NS-50a-b) is the emitted flow layer, read by BOTH
    post-fixb147 guards — the sibling-duplicate guard
    (:func:`unsynth_dup_guard_enabled`) and the fixb148 BIND gate
    (:func:`cli_bind_gate_enabled`), which resolves each member to the flow
    that survived the merge and then reads its ``entry_point_file``. The
    CONTRACT the guard enforces on this lane's output:

      * no row this lane emits has ALL of its members resolving into flows
        already owned by REAL same-PF sibling journeys;
      * no ``member_count > 0 ∧ loc == 0`` row leaves this lane (a hollow
        row is the visible half of the same defect: the member is a
        PRE-MERGE uuid, so the LOC doctrine finds no live flow to measure).

    The guard SUPPRESSES the conversion; it never deletes a row and never
    touches membership. That boundary is the seam's own law — this lane
    changes the emitted field and nothing else — and it is sufficient: a row
    left wearing ``synthesized`` is excluded from the journey ruler on both
    sides of the fraction, so the duplicate stops being a journey without a
    structural move this lane has no mandate to make.

    Returns bounded telemetry, or ``None`` when the flag is off (no
    ``scan_meta`` key ⇒ byte-identical output).
    """
    if not cli_unsynth_enabled():
        return None
    from wystan.pipeline_v2.cli_command_journeys import is_cli_declared

    tele: dict[str, Any] = {
        "converted": 0,
        "skipped_template": 0,
        "rows": [],
        "by_confidence": {},
    }
    conf: dict[str, int] = {}
    guard_on = unsynth_dup_guard_enabled()
    gate_on = cli_bind_gate_enabled()
    rows = list(user_flows or [])
    live: set[str] = set()
    merged: dict[str, str] = {}
    owners_by_pf: dict[Any, dict[str, str]] = {}
    entry_of: dict[str, str] = {}
    if guard_on or gate_on:
        live, merged = _merge_resolution(flows)
    if guard_on:
        # Telemetry keys appear ONLY when the guard is armed — an unset
        # environment must not move a single byte of ``scan_meta``.
        tele["unsynth_suppressed_dup"] = 0
        tele["suppressed"] = []
        owners_by_pf = _incumbent_owner_map(rows, live, merged)
    if gate_on:
        # Same law for the gate's keys: armed ⇒ published, unset ⇒ absent.
        tele["unsynth_misbind_suppressed"] = 0
        tele["misbind_suppressed"] = []
        tele["misbind_unstamped"] = 0
        entry_of = _entry_index(flows)
    # Sorted by id — deterministic iteration, no wall-clock, no randomness.
    for uf in sorted(rows, key=lambda u: str(getattr(u, "id", ""))):
        if not getattr(uf, "synthesized", False):
            continue
        if not is_cli_declared(uf):
            # A CLI row whose name the ENGINE composed (``cli-template``)
            # keeps its honest tag — the author declared no summary, so
            # there is no authored word to promote. Every other synthesis
            # reason is out of this lane's scope entirely.
            from wystan.pipeline_v2.cli_command_journeys import (
                CLI_COMMAND_JOURNEY_REASON,
            )
            if str(getattr(uf, "synthesis_reason", "") or "") == \
                    CLI_COMMAND_JOURNEY_REASON:
                tele["skipped_template"] += 1
            continue
        if guard_on:
            members = [str(m) for m in
                       (getattr(uf, "member_flow_ids", None) or ())]
            if members:
                owners = owners_by_pf.get(
                    getattr(uf, "product_feature_id", None), {})
                hits = [(m, _resolve_member(m, live, merged)) for m in members]
                if all(r in owners for _, r in hits):
                    tele["unsynth_suppressed_dup"] += 1
                    if len(tele["suppressed"]) < _TELE_CAP:
                        tele["suppressed"].append({
                            **_row(uf),
                            "members": [{
                                "member_uuid": m,
                                "resolved_uuid": r,
                                "pre_merge": m != r,
                                "owner_uf_id": owners[r],
                            } for m, r in hits],
                        })
                    continue
        if gate_on and str(getattr(uf, "binding_confidence", "") or "") \
                != "high":
            # SCOPE — the no-handler binding rung ONLY. The mint writes
            # ``binding_confidence = "high" if handler_sym else "low"``
            # (cli_command_journeys:414), so this reads the registration
            # site's handler declaration off the row itself, on every board
            # and every capture, without a second detection channel.
            # VERIFIED on three shipped boards (ollama / trigger.dev /
            # lobe-chat): every handler-ful CLI row carries "high", every
            # handler-null row "low". The 9 ollama controls are therefore
            # untouched — the anti-case that would otherwise cost this gate
            # 9 correct journeys.
            command = str(getattr(uf, "resource", "") or "")
            decl = [str(f) for f in
                    (getattr(uf, "declarant_files", None) or ())]
            if not decl:
                # The V2 arm is BLIND on this row: either the mint ran under
                # an engine that predates the stamp (a replayed pre-fixb148
                # capture) or the flag was armed after the mint. Counted,
                # never silent — V4 then decides alone, which is the whole
                # verdict on the measured corpus (V4 ⊇ V2 across all 28
                # handler-null rows) but is NOT guaranteed on a board we
                # have not measured.
                tele["misbind_unstamped"] += 1
            evidence: list[tuple[str, str]] = []
            for m in (getattr(uf, "member_flow_ids", None) or ()):
                entry = entry_of.get(_resolve_member(str(m), live, merged), "")
                if entry:
                    evidence.append((str(m), entry))
            if evidence and not any(
                    cli_bind_arm(command, decl, e) for _, e in evidence):
                # Every resolvable member fails BOTH arms ⇒ the mint bound
                # this command to a stranger. Suppress the CONVERSION only:
                # the row keeps its name, members and home and simply stays
                # ``synthesized``, i.e. out of the journey ruler on both
                # sides of the fraction. Same boundary the fixb147 guard
                # holds — this lane changes the emitted field and nothing
                # else.
                tele["unsynth_misbind_suppressed"] += 1
                if len(tele["misbind_suppressed"]) < _TELE_CAP:
                    tele["misbind_suppressed"].append({
                        "uf": str(getattr(uf, "id", "") or ""),
                        "command": command,
                        "declarant": list(decl),
                        "member_entry": [e for _, e in evidence],
                    })
                continue
        uf.synthesized = False
        tele["converted"] += 1
        c = str(getattr(uf, "name_confidence", "") or "")
        conf[c] = conf.get(c, 0) + 1
        if len(tele["rows"]) < _TELE_CAP:
            tele["rows"].append(_row(uf))
    tele["by_confidence"] = dict(sorted(conf.items()))
    return tele


def apply_synth_conversion(
    user_flows: list[Any] | None,
) -> dict[str, Any] | None:
    """Lane 2 apply — drop ``synthesized`` from the rows Law C let through.

    THE CONTRACT IS A STATE INVARIANT, NOT AN ID LIST. When the cap is armed
    (which this lane REQUIRES — see below), the only way a synthesized row
    can leave ``naming_contract`` wearing ``high`` is for the cap branch to
    have been bypassed, and the cap is bypassed only for a row that cleared
    BOTH guards and then earned the grade. So::

        synthesized ∧ name_confidence == "high"  ⟺  admitted ∧ earned

    and this seam needs no second copy of the guards. That matters: the UF
    name laws run from TWO entry points (``run_naming_contract`` and the
    ``primary_pass=False`` rescore seam) with SEPARATE telemetry dicts, so
    an id list published by one pass silently loses the other pass's
    verdicts while its confidence writes persist — MEASURED on infisical
    (50 ids published, 68 rows lifted, 18 lifted-but-unpublished). A state
    invariant is immune to the pass count.

    Two exclusions, both load-bearing:
      * ``is_cli_declared`` rows — lane 1's population, converted by
        AUTHORSHIP rather than by grade (a declared CLI row wears its mint
        confidence through the cap's own carve, so it would otherwise be
        swept in here without ever meeting a guard);
      * cap DISARMED — with ``WYSTAN_SYNTH_CONF_CAP=0`` (or the legacy
        ``WYSTAN_FOLD_EVIDENCE_WEIGHT=0``) every synthesized row is graded
        by the ordinary rubric and the invariant above no longer implies the
        guards ran. The lane is then a NO-OP: an unguarded mass conversion
        is exactly the failure this design exists to prevent.

    ``None`` when the lane is off or the cap is disarmed (⇒ no scan_meta
    key ⇒ byte-identical).
    """
    if not synth_conversion_enabled():
        return None
    if not synth_conf_cap_enabled():
        return {"converted": 0, "rows": [],
                "skipped": "cap_disarmed_guards_did_not_run"}
    from wystan.pipeline_v2.cli_command_journeys import is_cli_declared

    # NS-46d (battery 31, infisical UF-054) — the SUM must close. Every id
    # holding a verdict lands in exactly ONE bucket; the residue classes below
    # are the ones the state-invariant rewrite silently dropped.
    tele: dict[str, Any] = {"converted": 0, "cli_declared_left": 0, "rows": [],
                            "conversions_voided": 0, "voided": [],
                            "verdict_rows_gone": 0, "rows_gone": [],
                            "already_unsynthesized": 0}
    verdicts = conversion_verdict_ids()
    seen: set[str] = set()
    for uf in sorted(user_flows or [], key=lambda u: str(getattr(u, "id", ""))):
        uid = str(getattr(uf, "id", ""))
        if uid in verdicts:
            seen.add(uid)
        if not getattr(uf, "synthesized", False):
            # A verdict row already un-synthesized here was converted by lane 1
            # (authorship) before this seam. Legitimate, but it is NOT a lane-2
            # conversion and must not vanish from the ledger.
            if uid in verdicts:
                tele["already_unsynthesized"] += 1
            continue
        if str(getattr(uf, "name_confidence", "") or "") != "high":
            # NS-46a — a row holding a standing conversion verdict that no
            # longer reads ``high`` was VOIDED between the verdict and this
            # seam (a downstream quality demote, or a cap re-stamp the
            # registry failed to block). Counted with its id and final grade;
            # silence is the defect, not the demote.
            if uid in verdicts:
                tele["conversions_voided"] += 1
                if len(tele["voided"]) < _TELE_CAP:
                    tele["voided"].append({
                        **_row(uf),
                        "evidence": list(getattr(uf, "name_evidence", None) or []),
                    })
            continue          # capped, or graded below the bar — honest stub
        if is_cli_declared(uf):
            if uid in verdicts:
                tele["cli_declared_left"] += 1
            continue
        uf.synthesized = False
        tele["converted"] += 1
        if len(tele["rows"]) < _TELE_CAP:
            tele["rows"].append(_row(uf))
    # NS-46d — a verdict id absent from ``user_flows`` was FOLDED/MERGED/
    # DROPPED between the verdict and this seam. MEASURED: infisical UF-054,
    # folded by ``synth_quality.uf_synth_fold`` (6.98) after earning its
    # verdict at the post-6.7e seam — a LEGITIMATE transition (the fold is a
    # quality law and it wins), but the row was leaving the ledger unnamed.
    # The old id-list contract counted this as ``missing``; the state-invariant
    # rewrite dropped it, which is exactly how UF-054 went dark.
    gone = sorted(verdicts - seen)
    tele["verdict_rows_gone"] = len(gone)
    tele["rows_gone"] = gone[:_TELE_CAP]
    # THE SUM INVARIANT — every verdict lands in exactly one bucket.
    tele["verdicts"] = len(verdicts)
    tele["accounted"] = (tele["converted"] + tele["conversions_voided"]
                         + tele["verdict_rows_gone"]
                         + tele["already_unsynthesized"]
                         + tele["cli_declared_left"])
    tele["sum_ok"] = tele["accounted"] == tele["verdicts"]
    return tele
