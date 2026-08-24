"""fixb126 — CLI **command journeys**: the journey half of the CLI
anchor supply (``WYSTAN_CLI_ANCHOR_SUPPLY``, default OFF).

THE HOLE CLASS (measured, ollama c19/c20 keyed pair): fixb125 put the
shipped command surface on the product map — ``ollama CLI``, ``lh CLI``,
``tracecat-admin`` — and every one of those tiles arrived MUTE. The
board carried 17 (ollama) / 35 (lobe-chat) author-declared commands in
``scan_meta`` telemetry and ZERO journeys on the tile they belong to.
The 6.7 deterministic rollup DOES form CLI journeys (replay of the
ollama capture: 5 of them, 37 member flows) — the 6.7d LLM abstraction
then rewrites the journey set and its grounding pass drops the CLI rows
as ungrounded ("Run ollama CLI commands", "Create and manage models via
CLI" appear verbatim in ``uf_dropped_names``), while the PF-UF backstop
can only offer a MEMBER-LESS seed (``no_own_entry_flow``) that later
member-ful gates strip. Net: a tile with 9521 LOC of commands and no
journey a PM can read.

THE RULE (deterministic, $0, zero LLM, author-declared):

  * a command is a JOURNEY. ``ollama pull`` is not an implementation
    detail of a tile — it is the thing the user does. The command's
    NAME comes from the declaration itself: cobra ``Short:`` /
    commander ``.description()`` — product prose that lives in CODE
    (never README, never an i18n VALUE). No summary declared ⇒ the
    ``<Verb> <bin>`` template from the command token.
  * a command journey EXISTS only with a MEMBER: the handler flow is
    resolved by anchor-match — the flow must enter the cluster's own
    evidence tree AND share a content token with the command's declared
    name/summary. A command whose handler no flow reached ABSTAINS
    (telemetry, never a member-less phantom row — validator I7).
  * one flow, one journey: a member already claimed by an existing
    journey is never restated (the 6.7-rollup world keeps its rows).

Output-only and tagged like every other post-draw journey mint
(``synthesized: true`` + ``synthesis_reason: "cli_command"``) so eval
and the surfaced tier can exclude them by tag — board completeness,
never silent recall inflation.

Runs in the 6.7d tail, immediately after the journey abstraction that
was dropping these rows and beside the route-group recall seeds (W3.1
D6) whose slot and conventions this mirrors. Flag OFF ⇒ never called,
no ``scan_meta`` key, board byte-identical.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Literal

from wystan.pipeline_v2.cli_commands import (
    CliCluster,
    cli_anchor_supply_enabled,
    cluster_of_paths,
    detect_cli_clusters_cached,
)

__all__ = [
    "CLI_COMMAND_JOURNEY_REASON",
    "CLI_DECLARED_EVIDENCE",
    "CLI_TEMPLATE_EVIDENCE",
    "declarant_files_of",
    "fence_cli_foreign_journeys",
    "is_cli_declared",
    "mint_cli_command_journeys",
]

#: Tag every row this module appends (eval / surfaced-tier exclusion).
CLI_COMMAND_JOURNEY_REASON = "cli_command"

#: fixb128 (NS-2) — ``name_evidence`` stamp of a journey whose display name
#: is the command's OWN author-declared summary (cobra ``Short:``). This is
#: NOT synthesized prose: the maintainer literally wrote this sentence next
#: to the command, in CODE. It therefore joins the AUTHORED class that the
#: naming laws and the 6.7e adjudicator already honour, rather than the
#: synthesized class whose template they are entitled to overwrite.
CLI_DECLARED_EVIDENCE = "cli-declared"

#: fixb128 addendum — ``name_evidence`` of a CLI command journey named by the
#: ``<Verb> <bin>`` TEMPLATE because its author declared no summary. It must
#: never be confused with :data:`CLI_DECLARED_EVIDENCE`: that tag claims the
#: maintainer's own sentence, this one ADMITS the engine composed the name,
#: so such a row stays fair game for the naming laws. Previously these rows
#: carried ``None`` — silent, and in forensics indistinguishable from a row
#: whose evidence was simply never written.
CLI_TEMPLATE_EVIDENCE = "cli-template"


def is_cli_declared(uf: Any) -> bool:
    """True for a CLI command journey wearing its AUTHOR-DECLARED name.

    The measured defect this predicate closes (ollama c22/c24 keyed pair,
    ledger NS-2): the mint emitted 12 declared names ('Copy a model',
    'List running models') and the downstream naming laws re-worded 6 of
    them into ``Manage <raw-token>`` ('Manage cp' — a name no PM can
    read), because a ``synthesized=True`` row is fair game for the
    generic template. The confidence cap then forced every such row to
    ``low``, which is precisely the 6.7e adjudicator's selection
    criterion — so the corrupted rows were demoted for wearing the name
    the pipeline itself gave them. One stamp breaks the whole loop.

    Template-named rows (no declared summary) are deliberately NOT
    covered: they carry no authored word to protect.
    """
    if str(getattr(uf, "synthesis_reason", "") or "") != CLI_COMMAND_JOURNEY_REASON:
        return False
    return CLI_DECLARED_EVIDENCE in (getattr(uf, "name_evidence", None) or ())

#: Content-free words: they carry no discriminating meaning, so they may
#: never be the SOLE reason a flow is bound to a command. Universal
#: English function words + the flow-store's own structural suffixes —
#: not a product vocabulary and not per-repo tuning.
_STOP = frozenset({
    "a", "an", "the", "and", "or", "of", "to", "from", "for", "with",
    "in", "on", "at", "by", "into", "via", "as", "is", "are", "be",
    "this", "that", "it", "its", "your", "you", "all", "any", "new",
    "flow", "cmd", "cli", "command", "commands", "handler", "handlers",
})

#: Verb → intent, the SAME fixed semantic table Stage 6.7 rolls up with
#: (``INTENT`` there). Imported rather than restated so the two layers
#: can never drift apart.


def _intent_of(verb: str) -> str:
    from wystan.pipeline_v2.stage_6_7_user_flows import INTENT
    return INTENT.get(verb.lower(), "other")


def _tokens(*parts: str | None) -> frozenset[str]:
    """Content tokens of the given strings (lowercased, stop-stripped)."""
    out: set[str] = set()
    for p in parts:
        if not p:
            continue
        for tok in re.split(r"[^A-Za-z0-9]+", str(p).lower()):
            if len(tok) > 2 and tok not in _STOP:
                out.add(tok)
    return frozenset(out)


def _command_token(raw: str | None) -> str:
    """The bare command word — ``"completion [shell]"`` → ``completion``."""
    if not raw:
        return ""
    return str(raw).strip().split()[0].strip() if str(raw).strip() else ""


def declarant_files_of(cluster: CliCluster, command: str) -> list[str]:
    """fixb148 — every file in *cluster* that REGISTERS *command*, sorted.

    The mint's declarant evidence, computed where the sites already live so
    the pre-output bind gate never has to re-detect the cluster (a re-detect
    over the live tree drifts from the capture the board was minted on —
    measured 23 vs 24 sites on the trigger.dev probe).

    Per-CLUSTER by construction: a sibling cluster that declares the same
    token is a different binary and says nothing about this one (lobe-chat
    registers ``inspect``/``list`` in BOTH ``agent-tracing`` and
    ``llm-generation-tracing``). A LIST because ``_command_token`` collapses
    a namespace — tracecat's ``orgs create`` and ``tiers create`` are one
    token with two honest declaration sites (that flattening is its own
    debt, out of this lane's scope); keeping all of them can only REDUCE
    false suppressions.
    """
    return sorted({
        str(site.file).replace("\\", "/") for site in cluster.sites
        if site.file and _command_token(site.command) == command
    })


def _member_id(flow: Any) -> str:
    """uuid-else-name — the Stage 6.7 ``_flow_key`` id space."""
    return getattr(flow, "uuid", "") or getattr(flow, "name", "") or ""


def _entry_of(flow: Any) -> str:
    ep = str(getattr(flow, "entry_point_file", "") or "")
    if ep:
        return ep.replace("\\", "/")
    paths = list(getattr(flow, "paths", None) or ())
    return str(paths[0]).replace("\\", "/") if paths else ""


def _entry_symbol(flow: Any) -> str:
    """fixb128 (NS-3) — the SYMBOL a flow enters through.

    The flow store records it twice (``entry.symbol`` and the
    ``role='entry'`` node); read the scalar first and fall back to the
    node so a flow shape that carries only one of them still resolves.
    """
    entry = getattr(flow, "entry", None)
    if isinstance(entry, dict):
        sym = str(entry.get("symbol") or "").strip()
        if sym:
            return sym
    for node in (getattr(flow, "nodes", None) or ()):
        if not isinstance(node, dict):
            node = getattr(node, "__dict__", {}) or {}
        if str(node.get("role") or node.get("kind") or "") == "entry":
            sym = str(node.get("symbol") or "").strip()
            if sym:
                return sym
    return ""


def _under(path: str, tree: str) -> bool:
    if not tree:
        return bool(path)
    return path == tree or path.startswith(tree + "/")


def _journey_name(
    summary: str | None, verb: str, bin_name: str,
) -> tuple[str, Literal["high", "medium", "low"]]:
    """``(name, confidence)`` — the declared summary wins.

    A declaration like cobra's ``Short: "Pull a model from a registry"``
    IS the journey label a PM would write; it needs sentence hygiene
    (collapse whitespace, drop a trailing period, capitalize the lead),
    never invention. Without one, the ``<Verb> <bin>`` template is an
    honest LOW-confidence name — the same contract every template-named
    journey carries.
    """
    if summary:
        text = re.sub(r"\s+", " ", str(summary)).strip().rstrip(".")
        if text:
            return (text[0].upper() + text[1:], "high")
    verb_disp = verb.replace("-", " ").replace("_", " ").strip()
    verb_disp = verb_disp[:1].upper() + verb_disp[1:]
    return ((f"{verb_disp} {bin_name}".strip() if bin_name else verb_disp),
            "low")


def _cluster_home(
    cluster: CliCluster, features: list[Any],
) -> tuple[str | None, list[Any]]:
    """``(pf_slug, devs)`` — the product feature the cluster's OWN
    site-owning devs landed on, and every dev homed there.

    The CLI tile is whatever the 6.86 supply rung produced; this module
    never invents a home (validator I12: a journey's
    ``product_feature_id`` is always a REAL key).
    """
    votes: dict[str, int] = defaultdict(int)
    for dev in features:
        paths = [str(p).replace("\\", "/") for p in (getattr(dev, "paths", None) or ())]
        if cluster_of_paths((cluster,), paths) is None:
            continue
        pfid = getattr(dev, "product_feature_id", None)
        if pfid:
            votes[str(pfid)] += 1
    if not votes:
        return None, []
    home = sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    devs = [d for d in features
            if str(getattr(d, "product_feature_id", "") or "") == home]
    return home, devs


def mint_cli_command_journeys(
    ctx: Any,
    user_flows: list[Any],
    features: list[Any],
    product_features: list[Any],
) -> dict[str, Any]:
    """Append one tagged journey per author-declared command that a flow
    actually implements. Mutates *user_flows* in place; returns
    telemetry. ``{}`` when the flag is OFF (no ``scan_meta`` key at all).
    """
    if not cli_anchor_supply_enabled():
        return {}
    clusters = detect_cli_clusters_cached(ctx)
    if not clusters:
        return {"clusters": 0, "minted": 0}

    from wystan.models.types import UserFlow

    # fixb148 — the declarant stamp's flag lives with the gate that reads it
    # (``synth_conversion`` owns the bind POLICY, this module owns the mint).
    # Imported lazily, mirroring the reverse import that module already does.
    from wystan.pipeline_v2.synth_conversion import cli_bind_gate_enabled

    tele: dict[str, Any] = {
        "clusters": len(clusters), "commands_seen": 0, "minted": 0,
        "abstained_root": 0, "abstained_no_member": 0,
        "abstained_no_home": 0, "abstained_claimed_only": 0,
        # fixb128 (NS-3) — the command DECLARED a handler symbol and no
        # flow entered it: an honest hole, counted so the abstain rate is
        # auditable instead of silently becoming a foreign binding.
        "abstained_no_handler": 0,
        "named_declared": 0, "named_template": 0,
        "journeys": [],
    }
    pf_names = {str(getattr(pf, "name", "") or "") for pf in product_features}

    #: every member id an EXISTING journey already owns — one flow, one
    #: journey (the 6.7 rollup / 6.7d draw keep everything they hold).
    claimed: set[str] = set()
    for uf in user_flows:
        claimed.update(str(m) for m in (getattr(uf, "member_flow_ids", None) or ()))
    existing_names = {str(getattr(uf, "name", "") or "").strip().lower()
                      for uf in user_flows}

    minted: list[Any] = []
    for cluster in sorted(clusters, key=lambda c: c.canonical_id):
        home, home_devs = _cluster_home(cluster, features)
        if not home or home not in pf_names:
            tele["abstained_no_home"] += 1
            continue
        tree = cluster.site_tree
        site_files = {s.file for s in cluster.sites}

        # Candidate members: flows of the tile's OWN devs that enter the
        # cluster's evidence tree (or a registration site outright).
        cand: list[tuple[str, Any]] = []
        seen_ids: set[str] = set()
        for dev in sorted(home_devs, key=lambda d: str(getattr(d, "name", ""))):
            for fl in (getattr(dev, "flows", None) or ()):
                mid = _member_id(fl)
                entry = _entry_of(fl)
                if not mid or mid in seen_ids:
                    continue
                if not (entry in site_files or _under(entry, tree)):
                    continue
                seen_ids.add(mid)
                cand.append((mid, fl))
        if not cand:
            continue

        bin_name = str(cluster.bin_name or "").strip()
        # fixb128 (NS-3) — the cluster's handler index: entry symbol →
        # member id. A command's OWN handler is the flow entering through
        # the symbol its registration site names, so the lookup is exact
        # and needs no token guessing. Deterministic on collision (two
        # flows entering one symbol) by member id.
        by_entry_symbol: dict[str, str] = {}
        for mid, fl in cand:
            sym = _entry_symbol(fl)
            if not sym:
                continue
            prev = by_entry_symbol.get(sym)
            if prev is None or mid < prev:
                by_entry_symbol[sym] = mid

        # One entry per declared command (a command may be registered in
        # several files; sorted for determinism). A later site may only
        # FILL a field the first one left empty — never overwrite it.
        by_cmd: dict[str, tuple[str | None, str | None]] = {}
        for site in sorted(cluster.sites, key=lambda s: (s.file, s.line)):
            tok = _command_token(site.command)
            if not tok:
                continue
            prev_sum, prev_hnd = by_cmd.get(tok, (None, None))
            if tok not in by_cmd:
                by_cmd[tok] = (site.summary, site.handler)
                continue
            by_cmd[tok] = (prev_sum if prev_sum else site.summary,
                           prev_hnd if prev_hnd else site.handler)

        for verb in sorted(by_cmd):
            summary, handler_sym = by_cmd[verb]
            tele["commands_seen"] += 1
            if verb.startswith("_") or (bin_name and verb == bin_name):
                # the ROOT command (or a hidden completion helper) is the
                # binary itself, not a journey inside it.
                tele["abstained_root"] += 1
                continue
            best_mid = ""
            if handler_sym:
                # ── NS-3 rung — the command takes its OWN handler ──────
                # The registration site NAMES the handler; the flow
                # entering that symbol IS this command's implementation.
                # No token guessing, so no chance of the measured defect
                # (ollama: 'ps'/"List running models" scored one shared
                # token against SEVEN cluster flows and the UUID
                # tie-break handed it config.go's model-manager — 'Manage
                # ps' pointing at a stranger). A declared handler no flow
                # reached is an honest HOLE, never a foreign member: the
                # abstain contract fixb126 pinned.
                mid = by_entry_symbol.get(handler_sym, "")
                if not mid:
                    tele["abstained_no_handler"] += 1
                    continue
                if mid in claimed:
                    tele["abstained_claimed_only"] += 1
                    continue
                best_mid = mid
            else:
                # No handler convention for this framework (or an inlined
                # closure): the pre-fixb128 token-overlap binding stands
                # UNCHANGED — this rung is why click/typer/clap clusters
                # keep byte-identical output.
                want = _tokens(verb, summary)
                if not want:
                    tele["abstained_no_member"] += 1
                    continue
                best: tuple[int, str] | None = None
                hit_claimed = False
                for mid, fl in cand:
                    overlap = len(
                        want & _tokens(str(getattr(fl, "name", "") or "")))
                    if not overlap:
                        continue
                    if mid in claimed:
                        hit_claimed = True
                        continue
                    key = (-overlap, mid)
                    if best is None or key < best:
                        best, best_mid = key, mid
                if best is None:
                    tele["abstained_claimed_only" if hit_claimed
                         else "abstained_no_member"] += 1
                    continue
            # ── fixb148 — the DECLARANT stamp (WYSTAN_CLI_BIND_GATE) ──
            # The mint is the only place that holds the cluster's own
            # registration sites, so it is the only place that can record
            # WHERE the author declared this command without a second
            # detection pass. The pre-output bind gate reads the stamp; a
            # re-detect over the live tree drifts from the capture the board
            # was minted on (probe: 23 vs 24 sites on trigger.dev), and a
            # verdict computed from a drifting re-parse is not a verdict
            # about this board.
            #
            # Scope is the mint's own no-handler rung: a command whose
            # registration site NAMES its handler is bound exactly (NS-3)
            # and carries no stamp — the gate must never see it. Per-CLUSTER
            # sites, never a cross-cluster union: a sibling cluster that
            # happens to declare the same token says nothing about this
            # cluster's binding.
            declarant_files: list[str] | None = None
            if not handler_sym and cli_bind_gate_enabled():
                declarant_files = declarant_files_of(cluster, verb)
            name, conf = _journey_name(summary, verb, bin_name)
            if name.strip().lower() in existing_names:
                tele["abstained_claimed_only"] += 1
                continue
            existing_names.add(name.strip().lower())
            tele["named_declared" if conf == "high" else "named_template"] += 1
            claimed.add(best_mid)
            minted.append(UserFlow(
                id="UF-000",  # provisional — renumbered below
                name=name,
                resource=verb,
                domain=None,
                product_feature_id=home,
                intent=_intent_of(verb),
                member_flow_ids=[best_mid],
                member_count=1,
                routes=[],
                refined=True,
                name_confidence=conf,
                # fixb128 (NS-2) — an AUTHOR-DECLARED name is authored
                # evidence, not a synthesized template; a TEMPLATE-named
                # row says so out loud (addendum) instead of shipping a
                # silent ``None`` that forensics cannot tell apart from
                # "evidence never written".
                name_evidence=([CLI_DECLARED_EVIDENCE] if conf == "high"
                               else [CLI_TEMPLATE_EVIDENCE]),
                # fixb128 (NS-3) — the member is now the handler the
                # registration site NAMES, so the binding is exact.
                binding_confidence=("high" if handler_sym else "low"),
                synthesized=True,
                synthesis_reason=CLI_COMMAND_JOURNEY_REASON,
                # fixb148 — ``None`` unless WYSTAN_CLI_BIND_GATE armed
                # the stamp ⇒ the field is omitted from the dump ⇒ an
                # unarmed board is byte-identical to fixb147.
                declarant_files=declarant_files,
            ))
            if len(tele["journeys"]) < 40:
                tele["journeys"].append({
                    "pf": home, "command": verb, "name": name,
                    "member": best_mid, "declared": bool(summary),
                    "handler": handler_sym or None,
                })

    if not minted:
        return tele
    max_id = 0
    for uf in user_flows:
        raw = str(getattr(uf, "id", "") or "")
        if raw.startswith("UF-") and raw[3:].isdigit():
            max_id = max(max_id, int(raw[3:]))
    minted.sort(key=lambda u: ((u.name or "").lower(), str(u.resource or "")))
    for i, uf in enumerate(minted, start=1):
        uf.id = f"UF-{max_id + i:03d}"
    user_flows.extend(minted)
    tele["minted"] = len(minted)
    return tele


def fence_cli_foreign_journeys(
    ctx: Any,
    user_flows: list[Any],
    features: list[Any],
    flows: list[Any],
) -> dict[str, Any]:
    """fixb128 (NS-4) — a CLI tile only homes journeys of its OWN code.

    THE MEASURED DEFECT (ollama c24 keyed, ledger NS-4): the tile
    ``ollama-cli`` (registration sites all under ``cmd/``) drew the
    journey 'Run CLI commands and manage models' with member_count=10 and
    10/10 FOREIGN members — ``middleware/anthropic.go``,
    ``middleware/openai.go``, ``api/client.go`` — and NOT ONE path under
    ``cmd/``. B24 rightly failed the tile at 0.42. The inverted incentive
    the ledger named: the CLI exemption is easiest to pass on the most
    degenerate journey layer.

    THE ROOT is the 6.7d home gate's lane clause: a flow whose owning dev
    is a LANE RESIDENT carries ``home is None``, which that gate reads as
    "no evidence of foreignness — inheritable by any journey". For an
    ordinary PF that is a sane default; for an ANCHORED CLI tile it is
    exactly backwards, because the tile's whole identity IS its
    registration site-tree.

    THE FENCE: a journey may hold a CLI home only if AT LEAST ONE member
    flow enters that cluster's own evidence tree — the SAME containment
    basis as the fixb126 sink-guard (:func:`supplied_tile_admits`),
    applied at journey grain instead of dev grain.

    WHY HERE and not inside the 6.7d mint (measured, not assumed): at the
    6.7d ``_finish`` seam the journeys' ``member_flow_ids`` cannot be
    resolved to flow objects at all — on the c24 capture the middleware
    devs carry ZERO ``.flows`` and none of the journey's member uuids
    appear in ``developer_features[].flows`` (0 of 11 resolved). A fence
    that cannot see members would be judging on absence of evidence.
    Beside the mint the bipartite flow list IS the member id-space, the
    devs already carry their re-stamped ``product_feature_id``, and the
    cluster→tile lineage is the very :func:`_cluster_home` the mint uses.

    A fenced journey is REHOMED, never demoted and never nulled: it is a
    real journey about real code that simply does not live on the CLI
    tile. The new home is the member-evidence argmax over the devs that
    actually own its files. When nothing real owns them, the incumbent is
    KEPT — never a null home (shipped boards carry zero of those).

    ANTI-CASE: a legitimate CLI journey with MIXED members (some under
    ``cmd/**``, some shared utilities) clears the fence on its first
    own-tree member and is left completely alone.
    """
    if not cli_anchor_supply_enabled():
        return {}
    clusters = detect_cli_clusters_cached(ctx)
    if not clusters or not user_flows:
        return {}

    tele: dict[str, Any] = {"tiles": 0, "checked": 0, "rehomed": 0,
                            "kept_no_target": 0, "moves": []}

    by_mid: dict[str, Any] = {}
    for fl in flows or ():
        for key in (getattr(fl, "uuid", None), getattr(fl, "name", None)):
            if key and key not in by_mid:
                by_mid[key] = fl

    # file → owning PF (real homes only; the CLI tile itself is excluded
    # per-cluster below so a fenced row can never "move" onto its own
    # illegitimate home).
    file_owner: dict[str, str] = {}
    for dev in features:
        pfid = str(getattr(dev, "product_feature_id", "") or "")
        if not pfid:
            continue  # lane resident — owns nothing on the product map
        for p in (getattr(dev, "paths", None) or ()):
            file_owner.setdefault(str(p).replace("\\", "/"), pfid)

    for cluster in sorted(clusters, key=lambda c: c.canonical_id):
        home, _devs = _cluster_home(cluster, features)
        if not home:
            continue
        tele["tiles"] += 1
        tree = cluster.site_tree
        site_files = {s.file for s in cluster.sites}

        for uf in user_flows:
            if str(getattr(uf, "product_feature_id", "") or "") != home:
                continue
            mids = list(getattr(uf, "member_flow_ids", None) or ())
            members = [by_mid[m] for m in mids if m in by_mid]
            if not members:
                # No resolvable evidence ⇒ no verdict. Absence of proof is
                # not proof of foreignness (the trap that made an earlier
                # cut of this fence act on 0 of 11 members).
                continue
            tele["checked"] += 1

            own = False
            paths_all: list[str] = []
            for m in members:
                mp = [str(p).replace("\\", "/")
                      for p in (getattr(m, "paths", None) or ())]
                entry = _entry_of(m)
                if entry:
                    mp.append(entry)
                paths_all.extend(mp)
                if any(p in site_files or _under(p, tree) for p in mp):
                    own = True
            if own:
                continue  # legitimate CLI journey (incl. mixed members)

            votes: dict[str, int] = {}
            for p in paths_all:
                owner = file_owner.get(p)
                if owner and owner != home:
                    votes[owner] = votes.get(owner, 0) + 1
            if not votes:
                tele["kept_no_target"] += 1
                continue
            target = sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
            if len(tele["moves"]) < 40:
                tele["moves"].append({
                    "uf": str(getattr(uf, "id", "") or ""),
                    "name": str(getattr(uf, "name", "") or ""),
                    "from": home, "to": target, "members": len(mids),
                })
            uf.product_feature_id = target
            tele["rehomed"] += 1

    return tele
