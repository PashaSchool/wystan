"""B81 — agent-surface: the tool/skill registry as a capability surface.

The real capabilities of an agent product are reachable THROUGH the agent
(create-label via chat, build-detector via chat), but that surface is
invisible on the board: a repo's 64 tools + 16 capability skills collapse into
two generic dev buckets and one ``chat-with-agent`` flow. This module makes the
tool/skill registry legible.

Seg A — registry-census detector (this module's first half, ``$0`` LLM,
deterministic): reads a repo's PYTHON tool/skill registry in two forms and
emits a :class:`RegistryCensus` (tool, domain, handler ``file:line``, skill
back-refs, role).

  * **Form A — declarative tool-schema table**: a NAMED list/collection whose
    elements co-present ``name`` + ``description`` + a parameter-schema key
    (RefApp ``TOOL_DEFINITIONS`` list-of-dicts, authority ``ALL_TOOL_NAMES``, 64).
  * **Form B — registered class / decorated function**: a ``Tool`` subclass
    collected by a registry MAP (onyx ``BUILT_IN_TOOL_MAP``, 9) OR a
    ``@<x>.register(...)`` decorator carrying ``description=`` (tracecat
    ``@registry.register``, 256).

Seg B/C — the post-UF stage (``run_agent_surface``): tags/re-homes the
existing agent-entry journeys (Seg B, ``kind="entry"``) and mints ≈1-per-domain
``via:agent`` capability journeys homed in the real capability PFs (Seg C,
``kind="mint"``), keyed by the partition, over REAL member handler-flows
(conservation — no mint-time bars).

Scope: the shipped PYTHON forms (default ON) PLUS, since B81-it2, the ANCHORED
TypeScript Form A behind the ``WYSTAN_AGENT_SURFACE_TS`` sub-flag (default
OFF) — langfuse ``defineTool`` (SHIP carrier, 60 tools / 11 domains, agent_root
``web/src/features/mcp`` via the ``McpFeatureModule`` bootstrap) and lobe-chat
``BuiltinToolManifest`` (census-only: a distributed per-package registry has no
bootstrap, so agent_root stays None and the stage never reshapes the board —
"mint only langfuse-class"). See the B81-it2 TS section below. STILL deferred
(probe-refuted this iteration): n8n ``INodeType`` (532 workflow nodes, NOT an
agent surface — the genuine surface is a narrow ``usableAsTool`` subset, a
separate charter) and windmill (Rust dynamic generator — one bridge record).
With the sub-flag OFF, a TS-only registry stays inert (byte-identical
armed-vs-OFF).

Ranked domain signal (mechanisms, never a product-word dictionary):
  1. explicit partition module (RefApp ``tool_groups.py`` — frozensets that
     partition the tool set) — strongest, but a cross-cutting catch-all
     category (``core``/``common``/``shared``) is refined by (3);
  2. handler package/dir (onyx ``tool_implementations/<domain>/``, tracecat
     namespace);
  3. ``REQUIRED_TOOLS`` skill back-reference (RefApp capability skills — filename
     = domain, ``REQUIRED_TOOLS`` links skill→tool→domain);
  4. tool-name prefix — CORROBORATION only.

Anti-cases (each a named unit — ``tests/test_agent_surface.py``):
  1 disabled/commented tools (RefApp ``create_task``) never counted;
  2 bare ``"name":`` data rows (``report_tools.py`` ``row.name``) fail
    co-presence;
  3 fake/mock dirs (onyx ``fake_tools/``) excluded;
  4 persona skills (``REQUIRED_TOOLS == set()``) never project a domain;
  5 runtime-infra tools (onyx ``BashTool``/``PythonTool``) excluded by role;
  6 dynamic wrappers (onyx ``MCPTool``/``CustomTool``) collapse to ONE bridge
    record — never one row per absent remote instance.

Registered in ``scan_result_cache.ENV_OUTPUT_FLAGS``.
``WYSTAN_AGENT_SURFACE`` default ON since the 2026-07-23 flip-pack №5
(KEY_SCHEMA 38); explicit ``=0`` / ``false`` / ``off`` / ``no`` ⇒ detector +
stage inert, byte-identical to the pre-B81 world (KS 4-way kill-switch).
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Iterator, cast

from wystan.pipeline_v2.data import load_yaml

if TYPE_CHECKING:
    from wystan.models.types import Feature, Flow, UserFlow

# ── flag ─────────────────────────────────────────────────────────────────

ENV_AGENT_SURFACE = "WYSTAN_AGENT_SURFACE"


def agent_surface_enabled() -> bool:
    """Default **ON** since the 2026-07-23 flip-pack №5 flip (KEY_SCHEMA 38;
    KB3 + panel USEFUL + composition CLEAR).

    Unset now arms the agent surface (unset ≡ explicit ``1``). Explicit
    ``0`` / ``false`` / ``off`` / ``no`` is the kill-switch forever — the
    detector + stage go inert and the board is byte-identical to the pre-B81
    world. The pre-flip truthy set ``("1","true","on","yes")`` is preserved
    LITERALLY — only the ``os.environ.get`` default moved ``""`` -> ``"1"``.
    """
    return os.environ.get(ENV_AGENT_SURFACE, "1").strip().lower() in (
        "1", "true", "on", "yes",
    )


ENV_AGENT_SURFACE_TS = "WYSTAN_AGENT_SURFACE_TS"


def agent_surface_ts_enabled() -> bool:
    """B81-it2 — the ANCHORED TypeScript Form A detector (langfuse
    ``defineTool`` / lobe-chat ``BuiltinToolManifest`` / langfuse
    ``McpFeatureModule`` two-tier registry).

    Default **ON** since the 2026-07-27 flip-pack №8 flip (KEY_SCHEMA 41;
    keyed langfuse proof: the TS ``defineTool`` / ``McpFeatureModule`` two-tier
    registry mints agent-surface flows). Unset now arms the TS forms; explicit
    ``0``/``false``/``off``/``no`` keeps the detector Python-only (kill-switch
    forever — byte-identical to the pre-flip TS-off world). Only the
    ``os.environ.get`` default moved ``""`` -> ``"1"`` (unset ≡ explicit
    ``"1"``); the ``{"1","true","on","yes"}`` truthy set is preserved LITERALLY.
    Gated separately from the main ``WYSTAN_AGENT_SURFACE`` (also ON) so the
    two arms flip on independent maturity.
    """
    return os.environ.get(ENV_AGENT_SURFACE_TS, "1").strip().lower() in (
        "1", "true", "on", "yes",
    )


ENV_AGENT_MOUNT_ATTRIBUTION = "WYSTAN_AGENT_MOUNT_ATTRIBUTION"


def agent_mount_attribution_enabled() -> bool:
    """Phase-1 registry-MOUNT attribution (the carrier primitive, §3).

    The consumer→tool edge in an agent product is a DYNAMIC dispatch through a
    registry (the chat loop looks a tool up by name at runtime), so the Stage-3
    flow graph never reaches the tool leaves and neither file-overlap nor the
    static call graph bridges it — 8/11 RefApp domains and 7/11 langfuse domains
    show up ``0-candidates`` on the B81 board. This arm SYNTHESISES the edge
    from the registry + the CONSUMER mount-site instead: it parses the mount
    call (Anthropic ``system=``+``tools=`` / pydantic-ai ``Agent(instructions=,
    tools=)`` / langfuse ``toolRegistry.register(<x>Feature)``), resolves which
    registry domains that consumer mounts (reproducing the conditional
    selection — commented/disabled registrations, per-consumer registry
    choice), and records those domains as the mounted anatomy of the consumer
    journey (``agent_surface.mounts`` — a pure display tag) so the starved
    domains are attributed to the consumer that uses them rather than reported
    ``0-candidates``.

    Default **ON** since the 2026-07-29 agent-anatomy flip (KEY_SCHEMA 44;
    operator-ratified; offline-keyed RefApp proof — the anatomy on the Chat
    journey, collision-guard, conservation). Unset now arms it (unset ≡ explicit
    ``1``). Explicit ``0`` / ``false`` / ``off`` / ``no`` (and explicit ``""``)
    is the kill-switch forever — the pass goes inert and the board is
    byte-identical to the B81 world. The truthy set ``("1","true","on","yes")``
    is preserved LITERALLY — only the ``os.environ.get`` default moved
    ``""`` → ``"1"``.
    """
    return os.environ.get(ENV_AGENT_MOUNT_ATTRIBUTION, "1").strip().lower() in (
        "1", "true", "on", "yes",
    )


ENV_AGENT_SYSTEM_PROMPT = "WYSTAN_AGENT_SYSTEM_PROMPT"


def agent_system_prompt_enabled() -> bool:
    """Phase-2 agent SYSTEM-PROMPT detection (anatomy layer §4).

    The agent's system prompt is detected by CONSUMPTION, not by the token
    ``prompt`` (§6.3 collision guard — langfuse ``prompts`` is a user-facing CRUD
    product feature, NEVER the agent's system prompt). Three anchor classes:
    (1) the LLM call-site kwarg ``system=`` (Anthropic) / ``instructions=``
    (pydantic-ai ``Agent(...)``) / ``{"role":"system"}`` (OpenAI/LiteLLM) — the
    SAME call-site the Phase-1 mount-parser reads ``tools=`` on; (2) a named
    ``*-system-prompt.txt`` / ``*system_prompt*.{md,py}`` file; (3) a strongly
    named const (``SYSTEM_PROMPT`` / ``DEFAULT_SYSTEM_PROMPT`` / ``SKILL_TEXT``)
    or any const consumed at an agent call-site. Scoped to the agent machinery
    (a call-site under ``agent_root`` OR co-located with ``tools=``) so repo-wide
    utility LLM calls (translation, summarisation) are excluded.

    Default **ON** since the 2026-07-29 agent-anatomy flip (KEY_SCHEMA 44;
    operator-ratified; offline-keyed RefApp proof). Unset ≡ explicit ``1``;
    explicit ``0`` / ``false`` / ``off`` / ``no`` (and explicit ``""``) is the
    kill-switch forever (byte-identical). Independent of the mount flag. The
    truthy set is preserved LITERALLY — only the default moved ``""`` → ``"1"``.
    """
    return os.environ.get(ENV_AGENT_SYSTEM_PROMPT, "1").strip().lower() in (
        "1", "true", "on", "yes",
    )


ENV_AGENT_SKILLS = "WYSTAN_AGENT_SKILLS"


def agent_skills_enabled() -> bool:
    """Phase-3 agent SKILL-layer detection (anatomy layer §4).

    Skills are the LEAST standardised anatomy layer — in the probe corpus only
    the RefApp code-convention exists (a named module under a ``skills/`` dir that
    exports ``REQUIRED_TOOLS`` + ``ALWAYS_LOADED`` — 16 capability + 12 persona,
    each ``REQUIRED_TOOLS`` linking the skill to the product tool registry). The
    other repos have NO code-skills layer (prompt+tools only) and honestly emit
    zero — no over-mint. This arm completes that convention (exposes the
    skill→tools link + attaches the capability-skill layer to the agent
    consumer) and generalises the PATTERN (any repo adopting the
    ``REQUIRED_TOOLS`` module convention gets it — mechanism, not a RefApp
    dictionary).

    A cross-vendor ``.claude/skills/*/SKILL.md`` is detected too but CLASSIFIED
    dev-time by its structural path (under ``.claude/`` — the Claude Code
    dev-tooling home, markdown instructions for a CODING assistant, not wired to
    product tools) and NEVER attached to a product consumer (§6.3 — mechanism of
    distinction, not a name list).

    Default **ON** since the 2026-07-29 agent-anatomy flip (KEY_SCHEMA 44;
    operator-ratified; offline-keyed RefApp proof — 16 capability + 12 persona
    skills, dev-time ``.claude`` classified, not attached). Unset ≡ explicit
    ``1``; explicit ``0`` / ``false`` / ``off`` / ``no`` (and explicit ``""``)
    is the kill-switch forever (byte-identical). Independent of the mount /
    system-prompt flags. The truthy set is preserved LITERALLY — only the
    default moved ``""`` → ``"1"``.
    """
    return os.environ.get(ENV_AGENT_SKILLS, "1").strip().lower() in (
        "1", "true", "on", "yes",
    )


ENV_AGENT_ANATOMY_ROWS = "WYSTAN_AGENT_ANATOMY_ROWS"


def agent_anatomy_rows_enabled() -> bool:
    """Phase-4 — board-visible anatomy manifestation (the culmination §5).

    Phases 1-3 detect the anatomy (tools / prompt / skills) and attach it to a
    consumer journey the flow graph identifies — but the flow graph NEVER links
    the consumer journey to the mount-site (dynamic dispatch: the 34 member-flows
    of the Chat UF touch 0 of ``core.py``). The IMPORT-BRIDGE synthesises that
    edge from the STATIC import the flow graph misses: the chat endpoint
    statically imports the agent CONSUMER module (``from agent.core import
    AgentCore``). So a user-flow whose member-flow ENTERS in a file that
    statically imports a mount-consumer module is an agent-consumer journey, and
    the mounted anatomy (tools with per-tool LOC spans, skills, prompt) attaches
    to it as shared-member anatomy — making ``attached_to_ufs`` non-empty on a
    real board. Not flow-overlap, not the call graph (both broken by the dynamic
    dispatch) — the static endpoint→consumer import that DOES exist.

    Turning this arm on implies the Phase 1-3 detection (it needs the full
    anatomy to attach). Default **ON** since the 2026-07-29 agent-anatomy flip
    (KEY_SCHEMA 44; operator-ratified; offline-keyed RefApp proof — 7 consumer
    journeys incl. the Chat journey, 68 tools + 28 skills + 13 prompts, LOC
    spans real 68/68, product surfaces kept separate). Unset ≡ explicit ``1``;
    explicit ``0`` / ``false`` / ``off`` / ``no`` (and explicit ``""``) is the
    kill-switch forever (byte-identical). The truthy set is preserved LITERALLY
    — only the default moved ``""`` → ``"1"``.
    """
    return os.environ.get(ENV_AGENT_ANATOMY_ROWS, "1").strip().lower() in (
        "1", "true", "on", "yes",
    )


# ── scale-invariant role vocabulary (packaged YAML, mechanisms not magic) ──

_ROLES_FILE = "agent-surface-roles.yaml"


def _roles() -> dict[str, list[str]]:
    data = load_yaml(_ROLES_FILE)
    return data if isinstance(data, dict) else {}


def _schema_keys() -> frozenset[str]:
    return frozenset(_roles().get("schema_keys", ()))


def _registry_map_tokens() -> tuple[str, ...]:
    return tuple(_roles().get("registry_map_name_tokens", ()))


def _decorator_attrs() -> frozenset[str]:
    return frozenset(_roles().get("decorator_attrs", ()))


def _runtime_infra_roles() -> frozenset[str]:
    return frozenset(str(x).lower() for x in _roles().get("runtime_infra_roles", ()))


def _bridge_families() -> frozenset[str]:
    return frozenset(str(x).lower() for x in _roles().get("bridge_families", ()))


def _fake_dir_segments() -> frozenset[str]:
    return frozenset(str(x).lower() for x in _roles().get("fake_dir_segments", ()))


def _transport_machinery_domain_tokens() -> frozenset[str]:
    return frozenset(
        str(x).lower() for x in _roles().get("transport_machinery_domain_tokens", ()))


def _runtime_infra_domain_tokens() -> frozenset[str]:
    return frozenset(
        str(x).lower() for x in _roles().get("runtime_infra_domain_tokens", ()))


def _domain_role(domain: str | None) -> str:
    """Classify a DOMAIN slug: ``capability`` (mints) / ``transport`` /
    ``runtime-infra`` (do NOT mint). Whole-token match on the hyphen/underscore
    segments of the slug — never a substring of a product word. Empty / None ->
    capability (the caller decides mint-eligibility on other grounds)."""
    if not domain:
        return "capability"
    toks = {t for t in re.split(r"[-_]+", domain.lower()) if t}
    if toks & _runtime_infra_domain_tokens():
        return "runtime-infra"
    if toks & _transport_machinery_domain_tokens():
        return "transport"
    return "capability"


# Dirs never worth walking (mirror scan_result_cache._NONGIT_SKIP_DIRS intent).
# ``.claude`` holds nested agent worktrees (duplicate/divergent copies of the
# same registry) — walking it double-counts the census, so it is skipped like
# any other VCS/tooling tree.
_SKIP_DIRS = frozenset({
    ".git", ".claude", ".hg", ".svn", "node_modules", ".venv", "venv",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".next", "dist", "build",
    "target", ".turbo", "vendor", ".idea", ".vscode", "coverage", ".ruff_cache",
})

# A catch-all partition category (``CORE_ANALYSIS_TOOLS`` etc.) is not a
# product domain — it is refined by the skill back-reference. Scale-invariant
# role words, not a per-repo list.
_CATCHALL_DOMAIN_TOKENS = frozenset({
    "core", "common", "shared", "base", "misc", "other", "general",
    "analysis", "chat", "ux", "default", "all",
})

_MAX_FILE_BYTES = 2 * 1024 * 1024


# ── census data shapes ───────────────────────────────────────────────────


@dataclass(frozen=True)
class ToolEntry:
    """One registered tool in the census.

    ``domain`` is the ranked-signal capability domain slug (``None`` when no
    signal resolves — the tool is real but un-homed). ``handler_file`` /
    ``handler_line`` point at the definition site (the dict, the class def, or
    the decorated function). ``role`` partitions the surface: ``capability``
    (projects a journey), ``runtime-infra`` (excluded, anti-case 5), or
    ``bridge`` (collapsed dynamic wrapper, anti-case 6).
    """

    tool: str
    form: str  # "A" | "B" | "A-ts"
    handler_file: str
    handler_line: int
    domain: str | None = None
    domain_signal: str = "none"  # partition | skill-backref | package-dir | name-prefix | none
    role: str = "capability"     # capability | runtime-infra | bridge
    skill_backrefs: tuple[str, ...] = ()
    #: B81-it2 — where the tool object was parsed FROM. ``py`` (the shipped
    #: Python forms) or ``ts`` (the anchored TypeScript Form A, sub-flagged).
    #: Pure-Python repos carry only ``py`` entries, so the TS telemetry keys
    #: below never appear — the default-world board stays byte-identical.
    source: str = "py"           # py | ts
    #: The anchor that admitted a TS tool (``defineTool`` / ``BuiltinToolManifest``)
    #: — never a bare name+description+schema object. Empty for ``py``.
    ts_anchor: str = ""


@dataclass(frozen=True)
class MountConsumer:
    """A CONSUMER mount-site (Phase-1 registry-mount attribution, armed-only).

    A consumer is a call that hands a tool registry to an agent runtime — an
    Anthropic-shaped ``messages.create/.stream(system=…, tools=<registry>)``,
    a pydantic-ai ``Agent(instructions=…, tools=<registry>)`` constructor, or a
    langfuse ``toolRegistry.register(<x>Feature)`` MCP mount. ``domains`` are the
    census capability domains the consumer mounts (after conditional selection);
    ``tools`` the census tool names; ``excluded`` the domains a statically
    resolvable selection dropped (commented/disabled registration). ``site`` is
    ``file:line``; ``registries`` names the resolved registry symbol(s) for
    provenance. SYNTHESISED from registry + mount — never harvested from Stage-3
    flows (§6.1).
    """

    site: str
    kind: str  # "anthropic-call" | "agent-ctor" | "registry-register"
    domains: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    excluded: tuple[str, ...] = ()
    registries: tuple[str, ...] = ()


@dataclass(frozen=True)
class SystemPromptAnchor:
    """A detected agent SYSTEM PROMPT (Phase-2, armed-only).

    ``anchor_class`` — ``call-site`` (system=/instructions=/role:system at an
    agent LLM call), ``prompt-file`` (a ``*-system-prompt.txt`` named file), or
    ``named-const`` (a strongly named / agent-consumed string const).
    ``source_kind`` — how the prompt text is supplied: ``const`` (a named const),
    ``file`` (loaded from disk), ``builder`` (assembled by a function),
    ``inline`` (a literal string), ``dynamic`` (a runtime param/attr — the agent
    HAS a prompt but its text is config/DB-driven). ``source_ref`` names the
    const / file / builder. ``consumer_site`` is the agent call-site this
    attaches to (``file:line``), empty for a standalone file/const anchor.
    Detected by CONSUMPTION, never by the token ``prompt`` (§6.3).
    """

    site: str
    anchor_class: str  # "call-site" | "prompt-file" | "named-const"
    kwarg: str = ""    # system | instructions | role:system | ""
    source_kind: str = ""   # const | file | builder | inline | dynamic
    source_ref: str = ""
    consumer_site: str = ""


@dataclass(frozen=True)
class SkillAnchor:
    """A detected agent SKILL (Phase-3, armed-only).

    ``role`` — ``capability`` (a ``skills/`` module exporting a NON-empty
    ``REQUIRED_TOOLS`` set that links it to the product tool registry — a real
    product-agent capability), ``persona`` (a skills module with
    ``REQUIRED_TOOLS == set()`` — a voice/style skill, no tool link), or
    ``dev-time`` (a cross-vendor ``.claude/skills/*/SKILL.md`` — markdown
    instructions for a CODING assistant, classified dev-time by its structural
    path and NEVER product-anatomy). ``required_tools`` is the skill→tools link
    (empty for persona / dev-time). ``source`` — ``code-skill`` vs
    ``claude-skill``. Distinguished by MECHANISM (the ``REQUIRED_TOOLS`` tool
    wiring + the ``.claude/`` path), never by a skill-name dictionary (§6.3).
    """

    name: str
    file: str
    role: str      # "capability" | "persona" | "dev-time"
    source: str    # "code-skill" | "claude-skill"
    required_tools: tuple[str, ...] = ()
    always_loaded: bool = False


@dataclass(frozen=True)
class RegistryCensus:
    """Deterministic Seg-A artifact for one repo."""

    tools: tuple[ToolEntry, ...] = ()
    capability_skills: tuple[str, ...] = ()   # skill files w/ non-empty REQUIRED_TOOLS
    persona_skills: tuple[str, ...] = ()      # REQUIRED_TOOLS == set()
    bridges: tuple[str, ...] = ()             # dynamic-wrapper families (one each)
    excluded_disabled: tuple[str, ...] = ()   # anti-case 1 signals seen
    excluded_runtime_infra: tuple[str, ...] = ()  # anti-case 5
    partition_module: str | None = None       # path of the partition module (signal 1)
    partition_tool_count: int = 0             # tools covered by the partition (RefApp ALL_TOOL_NAMES=64)
    agent_root: str | None = None             # common dir of the registry (RefApp backend/agent)
    # it4 (panel polish №1): capability tools DETECTED but OUTSIDE the
    # partition — a secondary registry's tools (RefApp insights sub-agent:
    # query_environment_signals / query_security_data / submit_insights).
    # Named explicitly so the census total (67) reconciles against the
    # partition total (64) by inspection. Detect-only; empty when the repo
    # has no partition (nothing to be outside of).
    extra_tools: tuple[str, ...] = ()
    # ── B81-it2 (TS Form A, sub-flagged) — armed-only provenance ──
    #: the anchor helpers/interfaces that admitted TS tools this run
    #: (``defineTool`` / ``BuiltinToolManifest`` / ``McpFeatureModule``). Empty
    #: when TS detection is OFF or the repo has no TS registry — so a
    #: pure-Python census is byte-identical.
    ts_anchors: tuple[str, ...] = ()
    #: disabled/commented domain registrations (langfuse ``// tracesFeature``)
    #: — anti-case 1 at the DOMAIN grain (the domain never counts / mints).
    disabled_domains: tuple[str, ...] = ()
    #: Phase-1 (WYSTAN_AGENT_MOUNT_ATTRIBUTION, default OFF) — the CONSUMER
    #: mount-sites detected this run. Empty tuple when the flag is OFF or no
    #: consumer parses, so a flag-OFF census is byte-identical (armed-only).
    mount_consumers: tuple[MountConsumer, ...] = ()
    #: Phase-2 (WYSTAN_AGENT_SYSTEM_PROMPT, default OFF) — the agent system
    #: prompts detected this run. Empty when the flag is OFF (armed-only).
    system_prompts: tuple[SystemPromptAnchor, ...] = ()
    #: Phase-3 (WYSTAN_AGENT_SKILLS, default OFF) — the agent skill layer
    #: (code-skills capability/persona + dev-time .claude skills), armed-only.
    skill_layer: tuple[SkillAnchor, ...] = ()
    #: Phase-4 (WYSTAN_AGENT_ANATOMY_ROWS, default OFF) — repo files that
    #: statically import a mount-CONSUMER module (the import-bridge signal).
    #: A user-flow entering in one of these files is an agent-consumer journey.
    #: Empty when the flag is OFF (armed-only).
    consumer_importer_files: tuple[str, ...] = ()

    @property
    def present(self) -> bool:
        """A tool registry was actually found — the detector may act."""
        return bool(self.capability_tools)

    @property
    def capability_tools(self) -> tuple[ToolEntry, ...]:
        return tuple(t for t in self.tools if t.role == "capability")

    def domains(self) -> tuple[str, ...]:
        seen: list[str] = []
        for t in self.capability_tools:
            if t.domain and t.domain not in seen:
                seen.append(t.domain)
        return tuple(sorted(seen))

    def tools_by_domain(self) -> dict[str, list[ToolEntry]]:
        out: dict[str, list[ToolEntry]] = {}
        for t in self.capability_tools:
            if t.domain:
                out.setdefault(t.domain, []).append(t)
        return out

    def telemetry(self) -> dict[str, object]:
        # sorted everywhere — the census telemetry must be byte-deterministic
        # across runs (det x2 gate) regardless of file-walk order.
        by_dom = {
            d: sorted(t.tool for t in ts)
            for d, ts in sorted(self.tools_by_domain().items())
        }
        out: dict[str, object] = {
            "present": self.present,
            "tool_count": len(self.capability_tools),
            "total_detected": len(self.tools),
            "domain_count": len(self.domains()),
            "domains": list(self.domains()),
            "capability_skill_count": len(self.capability_skills),
            "persona_skill_count": len(self.persona_skills),
            "bridge_count": len(self.bridges),
            "bridges": list(self.bridges),
            "excluded_runtime_infra": list(self.excluded_runtime_infra),
            "excluded_disabled": list(self.excluded_disabled),
            "partition_module": self.partition_module,
            "partition_tool_count": self.partition_tool_count,
            "extra_tools": list(self.extra_tools),
            "tools_by_domain": by_dom,
        }
        # B89-hook / stamp extension — ARMED-ONLY: the ``ts_*`` keys appear only
        # when the anchored TS Form A actually contributed tools this run. A
        # pure-Python census (or a TS census with the sub-flag OFF) never emits
        # them, so the default-world board stays byte-identical.
        ts_tools = [t for t in self.capability_tools if t.source == "ts"]
        if ts_tools or self.ts_anchors:
            out["ts_anchors"] = list(self.ts_anchors)
            out["ts_tool_count"] = len(ts_tools)
            if self.disabled_domains:
                out["disabled_domains"] = list(self.disabled_domains)
        return out


# ── file walk + parse ────────────────────────────────────────────────────


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _is_fake_path(rel_posix: str, fake_segments: frozenset[str]) -> bool:
    segs = rel_posix.lower().split("/")
    base = segs[-1] if segs else ""
    if any(s in fake_segments for s in segs[:-1]):
        return True
    # basename fake_x.py / mock_x.py
    stem = base[:-3] if base.endswith(".py") else base
    return stem.startswith("fake_") or stem.startswith("mock_") or stem in (
        "fake", "mock", "conftest",
    )


def _iter_py_files(root: Path, *, include_fake: bool = False) -> Iterator[Path]:
    fake = _fake_dir_segments()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            p = Path(dirpath) / fn
            rel = _rel(p, root)
            if not include_fake and _is_fake_path(rel, fake):
                continue
            try:
                if p.stat().st_size > _MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield p


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return None


def _dict_str_keys(node: ast.Dict) -> set[str]:
    return {
        k.value for k in node.keys
        if isinstance(k, ast.Constant) and isinstance(k.value, str)
    }


def _dict_name(node: ast.Dict) -> str | None:
    for k, v in zip(node.keys, node.values):
        if isinstance(k, ast.Constant) and k.value == "name" and isinstance(v, ast.Constant):
            if isinstance(v.value, str):
                return v.value
    return None


def _iter_list_elts(value: ast.expr) -> list[ast.expr]:
    """List elements, following ``A + [b, c]`` BinOp registry extensions."""
    if isinstance(value, (ast.List, ast.Tuple)):
        return list(value.elts)
    if isinstance(value, ast.BinOp) and isinstance(value.op, ast.Add):
        return _iter_list_elts(value.left) + _iter_list_elts(value.right)
    return []


# ── Form A — declarative tool-schema tables ──────────────────────────────


def _detect_form_a(
    root: Path, files: list[Path],
) -> tuple[list[ToolEntry], list[str]]:
    """Named list literals whose elements co-present name+description+schema.

    Anti-case 1 (disabled/commented) is free: ``ast`` never sees commented
    dicts. Anti-case 2 (bare ``"name":`` data rows) is enforced by requiring
    ALL THREE of name+description+schema in the SAME dict.
    """
    schema_keys = _schema_keys()
    entries: list[ToolEntry] = []
    disabled_signals: list[str] = []

    def _tool_dict(d: ast.Dict) -> str | None:
        keys = _dict_str_keys(d)
        if "name" in keys and "description" in keys and keys & schema_keys:
            return _dict_name(d)
        return None

    for path in files:
        tree = _parse(path)
        if tree is None:
            continue
        rel = _rel(path, root)
        # module-level NAME = {dict} — tool dicts assigned to a name so a
        # registry list can reference them (RefApp _UPDATE_DETECTION_TOOL). Only
        # dicts that co-present the triad qualify.
        named_dicts: dict[str, ast.Dict] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        named_dicts[t.id] = node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                    and isinstance(node.value, ast.Dict):
                named_dicts[node.target.id] = node.value

        for node in ast.walk(tree):
            targets: list[ast.expr] = []
            value: ast.expr | None = None
            if isinstance(node, ast.Assign):
                targets = node.targets
                value = node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets = [node.target]
                value = node.value
            else:
                continue
            if value is None:
                continue
            if not any(isinstance(t, ast.Name) for t in targets):
                continue
            elts = _iter_list_elts(value)
            if not elts:
                continue
            local: list[ToolEntry] = []
            for e in elts:
                d: ast.Dict | None = None
                if isinstance(e, ast.Dict):
                    d = e
                elif isinstance(e, ast.Name) and e.id in named_dicts:
                    d = named_dicts[e.id]
                if d is None:
                    continue
                nm = _tool_dict(d)
                if nm:
                    local.append(ToolEntry(
                        tool=nm, form="A", handler_file=rel, handler_line=d.lineno,
                    ))
            # A registry collection has >= 2 tool-dicts OR extends a known
            # registry (BinOp). A single incidental dict is not a registry.
            if len(local) == 1 and not isinstance(value, ast.BinOp):
                continue
            entries.extend(local)
        # note a nearby "DISABLED"/"deprecated" comment marker as anti-case-1
        # provenance (telemetry only — never a tool).
        try:
            txt = path.read_text(encoding="utf-8")
        except OSError:
            txt = ""
        for m in re.finditer(r"#.*\b(DISABLED|deprecated|not exposed)\b", txt, re.I):
            disabled_signals.append(rel)
            break
    return entries, disabled_signals


# ── Form B — registered classes / decorated functions ────────────────────


def _module_to_file(root: Path, module: str, py_files: list[Path]) -> Path | None:
    """Reverse-resolve a dotted import to a repo file by path-suffix match."""
    suffix = module.replace(".", "/")
    cand_a = suffix + ".py"
    cand_b = suffix + "/__init__.py"
    for p in py_files:
        rp = p.as_posix()
        if rp.endswith(cand_a) or rp.endswith(cand_b):
            return p
    return None


def _collect_imports(tree: ast.Module) -> dict[str, str]:
    """Map imported NAME -> its dotted module path (for handler resolution)."""
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                local = alias.asname or alias.name
                out[local] = f"{node.module}.{alias.name}"
    return out


def _role_for_stem(stem: str) -> str:
    low = stem.lower()
    if low in _runtime_infra_roles() or any(
        low == r or low.startswith(r) and low[len(r):] in ("tool", "node")
        for r in _runtime_infra_roles()
    ):
        return "runtime-infra"
    if low in _bridge_families() or any(
        low == b or (low.endswith("tool") and low[:-4] in _bridge_families())
        for b in _bridge_families()
    ):
        return "bridge"
    return "capability"


def _class_stem(class_name: str) -> str:
    stem = class_name
    for suf in ("Tool", "Node", "Skill"):
        if stem.endswith(suf) and len(stem) > len(suf):
            stem = stem[: -len(suf)]
            break
    return stem


# Container segments that group tool packages but are not themselves a domain.
_DIR_CONTAINERS = frozenset({
    "tool_implementations", "tools", "toolset", "tool", "impl",
    "implementations", "builtin", "built_in", "src", "backend", "app",
})


def _domain_dir(hfile: str) -> str | None:
    """Domain slug from a handler path: the segment INSIDE the tool container.

    ``.../tool_implementations/search/search_tool.py`` -> ``search``. Skips
    container words (``tools``/``tool_implementations``) so the domain is the
    real per-tool package, and drops catch-all package names.
    """
    parts = hfile.split("/")
    if len(parts) < 2:
        return None
    file_dir = parts[-2]
    # walk up: the first non-container segment above the file is the domain
    for seg in reversed(parts[:-1]):
        if seg in _DIR_CONTAINERS:
            continue
        cand = _slug(seg)
        if cand in _CATCHALL_DOMAIN_TOKENS:
            return None
        return cand
    _ = file_dir
    return None


def _detect_form_b_map(
    root: Path, files: list[Path], py_files: list[Path],
) -> tuple[list[ToolEntry], list[str], list[str]]:
    """Registry MAP: ``NAME_MAP: dict = { X.__name__: X, ... }`` (onyx)."""
    tokens = _registry_map_tokens()
    entries: list[ToolEntry] = []
    bridges: list[str] = []
    runtime_infra: list[str] = []
    seen_class: set[str] = set()
    for path in files:
        tree = _parse(path)
        if tree is None:
            continue
        rel = _rel(path, root)
        imports = _collect_imports(tree)
        for node in ast.walk(tree):
            name = None
            value: ast.expr | None = None
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                name, value = node.target.id, node.value
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        name, value = t.id, node.value
            if not name or value is None:
                continue
            if not any(tok in name.lower() for tok in tokens):
                continue
            # collect referenced classes from dict values or list elements
            class_names: list[str] = []
            if isinstance(value, ast.Dict):
                for v in value.values:
                    if isinstance(v, ast.Name):
                        class_names.append(v.id)
            for e in _iter_list_elts(value):
                if isinstance(e, ast.Name):
                    class_names.append(e.id)
            if len(class_names) < 2:
                continue
            for cn in class_names:
                if cn in seen_class:
                    continue
                seen_class.add(cn)
                stem = _class_stem(cn)
                role = _role_for_stem(cn)
                # resolve handler file + domain-dir from the import
                hfile, hline, dom = rel, getattr(node, "lineno", 1), None
                mod = imports.get(cn)
                if mod:
                    # strip the trailing class segment to get the module
                    modpath = mod.rsplit(".", 1)[0]
                    resolved = _module_to_file(root, modpath, py_files)
                    if resolved is not None:
                        hfile = _rel(resolved, root)
                        # B81-it2 fix: was hardcoded ``hline = 1`` — resolve the
                        # class def line in the reverse-resolved module so the
                        # handler span is the real symbol, not the file head.
                        hline = _class_def_line(resolved, cn)
                        dom = _domain_dir(hfile)
                if role == "bridge":
                    fam = _class_stem(cn).lower()
                    if fam not in bridges:
                        bridges.append(fam)
                    continue
                if role == "runtime-infra":
                    runtime_infra.append(stem.lower())
                    entries.append(ToolEntry(
                        tool=_slug(stem), form="B", handler_file=hfile,
                        handler_line=hline, domain=dom,
                        domain_signal="package-dir" if dom else "none",
                        role="runtime-infra",
                    ))
                    continue
                entries.append(ToolEntry(
                    tool=_slug(stem), form="B", handler_file=hfile,
                    handler_line=hline, domain=dom,
                    domain_signal="package-dir" if dom else "none",
                ))
    return entries, bridges, runtime_infra


def _class_def_line(path: Path, class_name: str) -> int:
    """Line of ``class <class_name>`` in ``path`` (else 1).

    B81-it2 hline fix: when a registry-map handler class is reverse-resolved to
    a SEPARATE module file, the def-site line lives in that file — parse it and
    return the ``ClassDef.lineno`` for the symbol. The ``1`` fallback survives
    for an unparseable / renamed file (a symbolic span, never a whole-file
    guess). Exhibit: onyx 8/8 capability tools carried ``handler_line==1``
    (search_tool.py, image_generation_tool.py, …) before this fix.
    """
    tree = _parse(path)
    if tree is None:
        return 1
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node.lineno
    return 1


def _base_names(cls: ast.ClassDef) -> list[str]:
    out: list[str] = []
    for b in cls.bases:
        node: ast.expr = b
        if isinstance(node, ast.Subscript):
            node = node.value
        if isinstance(node, ast.Attribute):
            out.append(node.attr)
        elif isinstance(node, ast.Name):
            out.append(node.id)
    return out


def _detect_bridges(root: Path, files: list[Path]) -> list[str]:
    """Anti-case 6: dynamic-wrapper Tool subclasses -> ONE bridge per family.

    A ``class MCPTool(Tool[...])`` / ``class CustomTool(Tool[...])`` is a
    per-instance wrapper (a remote MCP server / a user OpenAPI spec), NOT a
    fixed capability. Collapse the whole family to a single ``mcp`` / ``custom``
    bridge record — never enumerate the absent remote instances. Only classes
    that subclass a ``*Tool`` base qualify (so an unrelated ``CustomThing``
    never trips it).
    """
    fams: list[str] = []
    for path in files:
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = _base_names(node)
            if not any(b == "Tool" or b.endswith("Tool") for b in bases):
                continue
            stem = _class_stem(node.name).lower()
            if stem in _bridge_families() and stem not in fams:
                fams.append(stem)
    return fams


def _decorator_call(dec: ast.expr) -> ast.Call | None:
    """A ``@<x>.register(...)`` / ``@register(...)`` decorator call, else None."""
    if not isinstance(dec, ast.Call):
        return None
    fn = dec.func
    attr = None
    if isinstance(fn, ast.Attribute):
        attr = fn.attr
    elif isinstance(fn, ast.Name):
        attr = fn.id
    if attr and attr.lower() in {a.lower() for a in _decorator_attrs()}:
        return dec
    return None


def _kw(call: ast.Call, name: str) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _detect_form_b_decorator(
    root: Path, files: list[Path],
) -> list[ToolEntry]:
    """Decorator registry: ``@registry.register(description=..., namespace=..)``.

    A registered UDF/tool iff the decorator call carries ``description=`` (the
    co-presence tell for the decorated form). ``include_in_schema=False`` or a
    truthy ``deprecated=`` skips it (anti-case-1 analog).
    """
    entries: list[ToolEntry] = []
    for path in files:
        tree = _parse(path)
        if tree is None:
            continue
        rel = _rel(path, root)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            for dec in node.decorator_list:
                call = _decorator_call(dec)
                if call is None:
                    continue
                if _kw(call, "description") is None:
                    continue  # no co-present description -> not a tool
                # anti-case-1 analog: hidden / deprecated
                inc = _kw(call, "include_in_schema")
                if isinstance(inc, ast.Constant) and inc.value is False:
                    continue
                dep = _kw(call, "deprecated")
                if dep is not None and not (
                    isinstance(dep, ast.Constant) and dep.value in (None, "", False)
                ):
                    continue
                ns = _kw(call, "namespace")
                dom, ns_val = None, ""
                if isinstance(ns, ast.Constant) and isinstance(ns.value, str):
                    ns_val = ns.value
                    # dotted namespace ``ai.skill`` -> ``ai``; a catch-all head
                    # is refined later.
                    head = ns_val.split(".")[0]
                    dom = _slug(head)
                role = _role_for_stem(node.name)
                # the registry key is namespace-qualified (tracecat builds
                # ``f"{namespace}.{fn.__name__}"``); qualify so two distinct
                # UDFs of the same function name in different namespaces do not
                # collapse under name dedup.
                key = f"{ns_val}.{node.name}" if ns_val else node.name
                entries.append(ToolEntry(
                    tool=key, form="B", handler_file=rel,
                    handler_line=node.lineno, domain=dom,
                    domain_signal="package-dir" if dom else "none",
                    role=role,
                ))
                break
    return entries


# ═════════════════════════════════════════════════════════════════════════
# B81-it2 — ANCHORED TypeScript Form A (sub-flagged, default OFF)
# ═════════════════════════════════════════════════════════════════════════
#
# The engine has no TS AST — this is a regex-grade parser. Two laws make it
# safe (probe-canon 2026-07-25, hoppscotch anti-case):
#   1 ANCHOR-FIRST: a tool object is admitted ONLY through a registry
#     helper/interface (``defineTool(`` call, ``BuiltinToolManifest`` typed
#     manifest, ``McpFeatureModule`` domain module) — NEVER a bare
#     name+description+schema object matcher. hoppscotch carries 3 files with
#     loose name+description+schema tokens (OpenAPI/Insomnia export schemas)
#     that have NO anchor -> the detector stays silent on them.
#   2 CO-PRESENCE-IN-ONE-OBJECT: name+description+schema must co-present at the
#     IMMEDIATE top level of a SINGLE object literal. A brace/bracket/string/
#     comment-aware scan counts keys only at object-depth 1 — so a nested
#     JSON-schema ``description:`` (lobe-chat inflates a naive count 203 -> 1006)
#     is never a tool.

_TS_EXTS = (".ts", ".tsx")
# Test scaffolding for TS — mirror the Python fake-dir intent; ``__tests__`` and
# ``*.test.ts`` / ``*.spec.ts`` / ``*.servertest.ts`` are never a live registry.
_TS_TEST_DIRS = frozenset({"__tests__", "__mocks__", "e2e", "cypress"})
_TS_TEST_SUFFIXES = (
    ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx",
    ".servertest.ts", ".stories.ts", ".stories.tsx", ".d.ts",
)


def _is_ts_test(rel_posix: str, fake_segments: frozenset[str]) -> bool:
    segs = rel_posix.lower().split("/")
    base = segs[-1]
    if any(s in _TS_TEST_DIRS or s in fake_segments for s in segs[:-1]):
        return True
    return any(base.endswith(suf) for suf in _TS_TEST_SUFFIXES)


def _iter_ts_files(root: Path) -> Iterator[Path]:
    fake = _fake_dir_segments()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if not fn.endswith(_TS_EXTS):
                continue
            p = Path(dirpath) / fn
            rel = _rel(p, root)
            if _is_ts_test(rel, fake):
                continue
            try:
                if p.stat().st_size > _MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield p


def _ts_mask(text: str) -> str:
    """Blank string / template / comment INTERIORS (keep delimiters + newlines).

    Structural scanning (brace matching, key detection) runs on the masked
    copy so a ``:`` / ``{`` / ``description`` inside a string or comment can
    never be mistaken for structure. Indices are preserved 1:1 with the
    original — key/value TEXT is read from the original at the matched offset.
    Template ``${...}`` braces are blanked with the rest of the template body,
    which keeps brace matching balanced (we never recurse into interpolations).
    """
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in ("'", '"', '`'):
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == c:
                    break
                j += 1
            for k in range(i + 1, min(j, n)):
                if out[k] != "\n":
                    out[k] = " "
            i = j + 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = i
            while j < n and text[j] != "\n":
                out[j] = " "
                j += 1
            i = j
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            out[i] = out[i + 1] = " "
            j = i + 2
            while j < n and not (text[j - 1] == "*" and text[j] == "/"):
                if text[j] != "\n":
                    out[j] = " "
                j += 1
            if j < n:
                out[j] = " "
            i = j + 1
            continue
        i += 1
    return "".join(out)


_TS_IDENT = re.compile(r"[A-Za-z_$][\w$]*")
#: A ``name:`` value is a string literal (``"createComment"``) OR a member /
#: enum reference (lobe-chat ``CalculatorApiName.calculate``) — capture either;
#: a member expression is homed by its LAST dotted segment.
_TS_NAME_VAL = re.compile(
    r"""\s*(?:"([^"]*)"|'([^']*)'|([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*))""")


def _ts_name_from(orig: str, colon_idx: int) -> str | None:
    m = _TS_NAME_VAL.match(orig, colon_idx + 1)
    if not m:
        return None
    if m.group(1) is not None:
        return m.group(1)
    if m.group(2) is not None:
        return m.group(2)
    ref = m.group(3)
    return ref.rsplit(".", 1)[-1] if ref else None


def _ts_object_keys(
    masked: str, orig: str, open_idx: int,
) -> tuple[frozenset[str], int, str | None]:
    """Top-level keys of the object literal opening at ``open_idx`` (``{``).

    Returns ``(top_level_keys, close_index, name_string_value)``. Keys are
    collected ONLY at object-depth 1 (immediately inside this ``{``) — nested
    objects/arrays are skipped wholesale via a bracket stack. Handles both
    ``key: value`` and shorthand ``key,`` / ``key}`` properties. ``name`` is
    returned as a string only when its value is a plain string literal (a
    ``name`` shorthand or computed value -> ``None``, homed by filename).
    """
    n = len(masked)
    if open_idx >= n or masked[open_idx] != "{":
        return frozenset(), open_idx, None
    stack = ["{"]
    i = open_idx + 1
    keys: set[str] = set()
    name_val: str | None = None
    expecting_key = True
    while i < n and stack:
        c = masked[i]
        if c in "{[(":
            stack.append(c)
            expecting_key = False
            i += 1
            continue
        if c in "}])":
            stack.pop()
            i += 1
            if not stack:
                break
            continue
        if len(stack) == 1:  # directly inside THIS object
            if c == ",":
                expecting_key = True
                i += 1
                continue
            if c.isspace():
                i += 1
                continue
            if expecting_key:
                m = _TS_IDENT.match(masked, i)
                key: str | None = None
                if m:
                    key = m.group(0)
                    j = m.end()
                elif orig[i] in ("'", '"'):
                    q = orig[i]
                    e = orig.find(q, i + 1)
                    if e != -1:
                        key = orig[i + 1:e]
                        j = e + 1
                    else:
                        j = i + 1
                else:
                    expecting_key = False
                    i += 1
                    continue
                # skip whitespace to see : (property) vs , / } (shorthand)
                k = j
                while k < n and masked[k].isspace():
                    k += 1
                if key is not None and k < n and masked[k] == ":":
                    keys.add(key)
                    if key == "name":
                        name_val = _ts_name_from(orig, k)
                    expecting_key = False
                    i = k + 1
                    continue
                if key is not None and k < n and masked[k] in ",}":
                    keys.add(key)  # shorthand property (name, description, …)
                    i = k
                    continue
                expecting_key = False
                i = j
                continue
        i += 1
    return frozenset(keys), i, name_val


def _ts_next_object(masked: str, from_idx: int) -> int:
    """Index of the next ``{`` at or after ``from_idx`` on the masked text."""
    return masked.find("{", from_idx)


def _ts_domain(rel: str) -> str | None:
    """Structural domain slug for a TS tool file.

    Two universal conventions (path structure, not a product dictionary):
      * ``…/<domain>/tools/<tool>.ts``           (langfuse mcp features tree);
      * ``…/builtin-tool-<domain>/…``            (lobe-chat package convention).
    Falls back to the first non-container directory segment. Catch-all package
    names collapse to ``None`` (un-homed).
    """
    parts = rel.split("/")
    for seg in parts:
        low = seg.lower()
        for pref in ("builtin-tool-", "builtin_tool_", "tool-", "mcp-tool-"):
            if low.startswith(pref) and len(low) > len(pref):
                cand = _slug(low[len(pref):])
                return None if cand in _CATCHALL_DOMAIN_TOKENS else cand
    # ``…/<domain>/tools/<file>`` — the segment ABOVE a ``tools`` container
    if "tools" in [p.lower() for p in parts[:-1]]:
        idx = max(i for i, p in enumerate(parts[:-1]) if p.lower() == "tools")
        for seg in reversed(parts[:idx]):
            if seg.lower() in _DIR_CONTAINERS:
                continue
            cand = _slug(seg)
            return None if cand in _CATCHALL_DOMAIN_TOKENS else cand
    # generic: nearest non-container dir above the file
    for seg in reversed(parts[:-1]):
        if seg.lower() in _DIR_CONTAINERS:
            continue
        cand = _slug(seg)
        return None if cand in _CATCHALL_DOMAIN_TOKENS else cand
    return None


def _line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def _detect_ts_define_tool(
    root: Path, files: list[Path],
) -> list[ToolEntry]:
    """Anchor ``defineTool(`` — langfuse. One call = one tool.

    The object literal is the CALL ARGUMENT of ``defineTool(``; a bare object
    with the same keys but no ``defineTool`` anchor is never admitted. The
    definition site (``export function defineTool(config: …)``) has ``(``
    followed by an identifier, not ``{`` — so it is skipped by the ``{``
    requirement.
    """
    schema_keys = _schema_keys()
    entries: list[ToolEntry] = []
    anchor = re.compile(r"\bdefineTool\s*\(")
    for path in files:
        try:
            orig = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "defineTool" not in orig:
            continue
        masked = _ts_mask(orig)
        rel = _rel(path, root)
        for m in anchor.finditer(masked):
            # the '(' then the first non-space must be '{'
            k = m.end()
            while k < len(masked) and masked[k].isspace():
                k += 1
            if k >= len(masked) or masked[k] != "{":
                continue
            keys, _end, name_val = _ts_object_keys(masked, orig, k)
            if "name" in keys and "description" in keys and keys & schema_keys:
                nm = name_val or path.stem
                entries.append(ToolEntry(
                    tool=_slug(nm), form="A-ts", handler_file=rel,
                    handler_line=_line_of(orig, m.start()),
                    domain=_ts_domain(rel),
                    domain_signal="ts-path" if _ts_domain(rel) else "none",
                    source="ts", ts_anchor="defineTool",
                ))
    return entries


def _detect_ts_builtin_manifest(
    root: Path, files: list[Path],
) -> list[ToolEntry]:
    """Anchor ``BuiltinToolManifest`` — lobe-chat. A typed manifest whose
    ``api:`` array elements each co-present name+description+parameters.

    The manifest is admitted only through the ``BuiltinToolManifest`` type
    anchor; each ``api:`` array element object is a tool. Nested JSON-schema
    ``description``/``name`` keys live DEEPER than the element's top level, so
    the co-presence-in-one-object rule never counts them (203 real, not 1006).
    """
    schema_keys = _schema_keys()
    entries: list[ToolEntry] = []
    anchor = re.compile(r"\bBuiltinToolManifest\b")
    for path in files:
        try:
            orig = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "BuiltinToolManifest" not in orig:
            continue
        masked = _ts_mask(orig)
        rel = _rel(path, root)
        dom = _ts_domain(rel)
        for am in anchor.finditer(masked):
            # find the manifest object ``= { … }`` after the anchor
            eq = masked.find("=", am.end())
            if eq == -1:
                continue
            obj = _ts_next_object(masked, eq)
            if obj == -1:
                continue
            keys, mclose, _nv = _ts_object_keys(masked, orig, obj)
            if "api" not in keys:
                continue
            # locate the ``api:`` array within the manifest object
            api_arr = _ts_api_array(masked, obj, mclose)
            if api_arr == -1:
                continue
            for eobj, ename in _ts_array_objects(masked, orig, api_arr):
                ekeys, _e2, nv = _ts_object_keys(masked, orig, eobj)
                if "name" in ekeys and "description" in ekeys and ekeys & schema_keys:
                    nm = nv or ename or f"{dom or path.stem}-tool"
                    entries.append(ToolEntry(
                        tool=_slug(nm), form="A-ts", handler_file=rel,
                        handler_line=_line_of(orig, eobj),
                        domain=dom, domain_signal="ts-path" if dom else "none",
                        source="ts", ts_anchor="BuiltinToolManifest",
                    ))
            break  # one manifest per file
    return entries


def _ts_api_array(masked: str, obj_open: int, obj_close: int) -> int:
    """Index of the ``[`` value of the top-level ``api:`` key in ``[obj]``."""
    stack = ["{"]
    i = obj_open + 1
    n = min(obj_close + 1, len(masked))
    expecting_key = True
    while i < n and stack:
        c = masked[i]
        if c in "{[(":
            stack.append(c)
            expecting_key = False
            i += 1
            continue
        if c in "}])":
            stack.pop()
            i += 1
            continue
        if len(stack) == 1:
            if c == ",":
                expecting_key = True
                i += 1
                continue
            if c.isspace():
                i += 1
                continue
            if expecting_key:
                m = _TS_IDENT.match(masked, i)
                if m and m.group(0) == "api":
                    k = m.end()
                    while k < n and masked[k].isspace():
                        k += 1
                    if k < n and masked[k] == ":":
                        k += 1
                        while k < n and masked[k].isspace():
                            k += 1
                        return k if (k < n and masked[k] == "[") else -1
                expecting_key = False
                i = m.end() if m else i + 1
                continue
        i += 1
    return -1


def _ts_array_objects(
    masked: str, orig: str, arr_open: int,
) -> Iterator[tuple[int, str | None]]:
    """Yield ``(open_index, None)`` for each top-level object element of the
    array opening at ``arr_open`` (``[``)."""
    n = len(masked)
    stack = ["["]
    i = arr_open + 1
    while i < n and stack:
        c = masked[i]
        if c == "{" and len(stack) == 1:
            yield i, None
            # skip to the matching close of this element object
            _keys, close, _nv = _ts_object_keys(masked, orig, i)
            i = close + 1
            continue
        if c in "{[(":
            stack.append(c)
            i += 1
            continue
        if c in "}])":
            stack.pop()
            i += 1
            continue
        i += 1


def _detect_ts_mcp_feature_module(
    root: Path, files: list[Path],
) -> tuple[list[str], list[str], str | None]:
    """Anchor ``McpFeatureModule`` — langfuse two-tier domain registry.

    Returns ``(registered_domains, disabled_domains, agent_root)``. The domain
    registry lives in a bootstrap module (``toolRegistry.register(<x>Feature)``
    live calls; ``// toolRegistry.register(tracesFeature)`` commented = a
    DISABLED domain, anti-case 1 at the domain grain). ``agent_root`` = the
    parent of the registry dir (``…/mcp/server`` -> ``…/mcp``) so the stage
    gates entry-true flows to the mcp feature tree, not all of ``web/src``.
    """
    reg = re.compile(r"(\w+)Feature\b")
    live_reg = re.compile(r"\btoolRegistry\s*\.\s*register\s*\(\s*(\w+)Feature\b")
    for path in files:
        try:
            orig = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "McpFeatureModule" not in orig and "toolRegistry" not in orig:
            continue
        if "register(" not in orig.replace(" ", ""):
            continue
        rel = _rel(path, root)
        masked = _ts_mask(orig)
        live: list[str] = []
        for m in live_reg.finditer(masked):
            live.append(_slug(m.group(1)))
        if not live:
            continue
        # disabled = a ``<x>Feature`` mentioned ONLY in a comment (masked out),
        # i.e. present in the original but absent from the live (masked) text.
        orig_domains = {_slug(m.group(1)) for m in reg.finditer(orig)}
        masked_domains = {_slug(m.group(1)) for m in reg.finditer(masked)}
        disabled = sorted(orig_domains - masked_domains)
        reg_dir = rel.rsplit("/", 1)[0] if "/" in rel else ""
        agent_root = reg_dir.rsplit("/", 1)[0] if "/" in reg_dir else reg_dir
        return sorted(set(live)), disabled, (agent_root or None)
    return [], [], None


# ── partition module + skill back-references (domain signals 1 & 3) ───────


def _slug(text: str) -> str:
    s = re.sub(r"[_\s]+", "-", str(text).strip())
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", s)
    return re.sub(r"-+", "-", s).strip("-").lower()


def _pluralize(token: str) -> str:
    if not token:
        return token
    if token.endswith("s"):
        return token
    if token.endswith("y"):
        return token[:-1] + "ies"
    return token + "s"


def _detect_partition(
    root: Path, files: list[Path], tool_names: frozenset[str],
) -> tuple[dict[str, str], dict[str, str], str | None]:
    """Explicit partition module (signal 1): frozenset/set of tool-name strings.

    Returns ``(tool -> head-domain-slug, tool -> full-category-slug, module
    path)``. The head slug ("labels" from LABEL_TOOLS) is the mintable domain;
    the full-category slug ("core-analysis" from CORE_ANALYSIS_TOOLS) is the
    it3 census BUCKET a catch-all category falls back to when no skill
    refines it — so ``tools_by_domain`` always sums to the partition total
    (panel fix №3: 12/64 tools were invisible to every domain bucket).
    """
    best: dict[str, str] = {}
    best_full: dict[str, str] = {}
    best_module: str | None = None
    best_cover = 0
    # skill modules also assign string-sets (REQUIRED_TOOLS) — those are signal
    # 3, NOT a partition; scanning them here would mint a bogus "requireds"
    # domain. Skip skill files and the skill vars.
    _skill_vars = {"REQUIRED_TOOLS", "ALWAYS_LOADED"}
    for path in files:
        rel = _rel(path, root)
        if "/skills/" in ("/" + rel) or "/skills/" in rel:
            continue
        tree = _parse(path)
        if tree is None:
            continue
        local: dict[str, str] = {}
        local_full: dict[str, str] = {}
        cover: set[str] = set()
        for node in ast.walk(tree):
            var = None
            value: ast.expr | None = None
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                var, value = node.target.id, node.value
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        var, value = t.id, node.value
            if not var or value is None or var in _skill_vars:
                continue
            names = _string_members(value)
            # a category = a collection of >=2 strings that are (mostly) tools
            if len(names) < 2:
                continue
            hit = names & tool_names
            if len(hit) < 2 or len(hit) < len(names) * 0.6:
                continue
            head = var.lower().split("_")[0]
            dom = _pluralize(_slug(head))
            # full-category bucket slug: CORE_ANALYSIS_TOOLS -> core-analysis
            full_var = var
            for suf in ("_TOOLS", "_TOOL", "_SET", "_NAMES"):
                if full_var.upper().endswith(suf):
                    full_var = full_var[: -len(suf)]
                    break
            full_slug = _slug(full_var.lower().replace("_", "-"))
            for tn in hit:
                local.setdefault(tn, dom)
                local_full.setdefault(tn, full_slug)
                cover.add(tn)
        if len(cover) > best_cover:
            best, best_full, best_cover, best_module = (
                local, local_full, len(cover), rel)
    return best, best_full, best_module


def _string_members(value: ast.expr) -> frozenset[str]:
    """String-literal members of a set/frozenset/list/tuple/dict-keys/call."""
    out: set[str] = set()

    def _walk(v: ast.expr) -> None:
        if isinstance(v, (ast.Set, ast.List, ast.Tuple)):
            for e in v.elts:
                if isinstance(e, ast.Constant) and isinstance(e.value, str):
                    out.add(e.value)
        elif isinstance(v, ast.Dict):
            for k in v.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    out.add(k.value)
        elif isinstance(v, ast.Call):
            for a in v.args:
                _walk(a)
        elif isinstance(v, ast.BinOp) and isinstance(v.op, (ast.BitOr, ast.Add)):
            _walk(v.left)
            _walk(v.right)

    _walk(value)
    return frozenset(out)


@dataclass
class _SkillInfo:
    module: str          # filename stem, e.g. "tag_management"
    file: str            # repo-relative path
    required_tools: frozenset[str]
    always_loaded: bool


def _detect_skills(root: Path) -> tuple[list[_SkillInfo], list[str], list[str]]:
    """Skill back-references (signal 3) + persona split (anti-case 4).

    A skill module exports ``REQUIRED_TOOLS`` (a set of tool names) and
    ``ALWAYS_LOADED``. A capability skill has non-empty REQUIRED_TOOLS; a
    persona skill has ``REQUIRED_TOOLS == set()``.
    """
    caps: list[_SkillInfo] = []
    cap_files: list[str] = []
    persona_files: list[str] = []
    for skills_dir in _find_skills_dirs(root):
        for path in sorted(skills_dir.glob("*.py")):
            if path.name == "__init__.py":
                continue
            tree = _parse(path)
            if tree is None:
                continue
            req: frozenset[str] | None = None
            always = False
            for node in ast.walk(tree):
                var = None
                value: ast.expr | None = None
                if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    var, value = node.target.id, node.value
                elif isinstance(node, ast.Assign):
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            var, value = t.id, node.value
                if var == "REQUIRED_TOOLS" and value is not None:
                    req = _string_members(value)
                elif var == "ALWAYS_LOADED" and isinstance(value, ast.Constant):
                    always = bool(value.value)
            if req is None:
                continue  # not a skill module
            rel = _rel(path, root)
            stem = path.stem
            if req:
                caps.append(_SkillInfo(stem, rel, req, always))
                cap_files.append(rel)
            else:
                persona_files.append(rel)
    return caps, cap_files, persona_files


def _find_skills_dirs(root: Path) -> list[Path]:
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        base = os.path.basename(dirpath)
        if base == "skills" and "__init__.py" in filenames:
            out.append(Path(dirpath))
    return out


# ── domain resolution + census assembly ──────────────────────────────────


def _skill_domain(skill: _SkillInfo, pf_names: Iterable[str]) -> str:
    """Resolve a capability skill to a domain slug.

    Prefer a token match against an existing PF display name (so the mint homes
    cleanly); else the skill filename's leading token. Mechanism, not a
    product dictionary — the match is structural token overlap.
    """
    tokens = [t for t in re.split(r"[_-]+", skill.module) if t]
    generic = {"management", "integration", "creation", "refinement", "rag",
               "query", "dsl", "terminology", "profile", "sdk", "vulnerability"}
    meaningful = [t for t in tokens if t not in generic] or tokens
    cand_set = {c for t in meaningful for c in (t, _pluralize(t))}
    # best PF by token overlap (Jaccard), ties broken by the SHORTEST PF name
    # (most specific) — so ``report_intel`` picks "Bulletins" over "Data
    # Feed Parsers", and ``report_creation`` picks "Reports" over "Report
    # Suggestions".
    best_pf: str | None = None
    best_score = 0.0
    for n in pf_names:
        toks = set(re.split(r"[\s_-]+", n.lower()))
        overlap = len(cand_set & toks)
        if overlap == 0:
            continue
        jacc = overlap / len(cand_set | toks)
        if jacc > best_score or (jacc == best_score and best_pf
                                 and len(n) < len(best_pf)):
            best_pf, best_score = n, jacc
    if best_pf is not None:
        return _slug(best_pf)
    return _pluralize(_slug(meaningful[0]))


# ── Phase-1 — CONSUMER mount-site parsing (registry-mount attribution) ─────
#
# The carrier primitive (§3): the consumer→tool edge is a DYNAMIC dispatch, so
# it is never in the flow graph — it must be SYNTHESISED from the registry +
# the mount-site (§6.1: synthesise, do NOT harvest Stage-3 flows). We resolve
# WHICH registry each consumer hands the agent runtime, then map that registry
# to the census domains it mounts. Precise (registry→tool-names→census-domain),
# never "all domains", so a narrow sub-agent registry (RefApp insights
# ``_TOOL_DEFINITIONS`` = 3 tools) attributes only its own domains — the
# over-attribution guard (§6.3).


def _reg_referenced_names(v: ast.expr) -> set[str]:
    """All bare ``Name`` ids referenced anywhere in an expression."""
    return {n.id for n in ast.walk(v) if isinstance(n, ast.Name)}


def _binop_operand_names(v: ast.expr) -> set[str]:
    """Registry names combined by ``A + [..]`` / ``[*A, x]`` extension — the
    base registries a derived list is built from (lost by ``_iter_list_elts``)."""
    out: set[str] = set()
    if isinstance(v, ast.BinOp) and isinstance(v.op, ast.Add):
        for side in (v.left, v.right):
            if isinstance(side, ast.Name):
                out.add(side.id)
            else:
                out |= _binop_operand_names(side)
    for e in _iter_list_elts(v):
        if isinstance(e, ast.Starred) and isinstance(e.value, ast.Name):
            out.add(e.value.id)  # ``[*TOOL_DEFINITIONS, finish]``
    return out


def _registry_tool_names(
    files: list[Path], root: Path,
) -> dict[str, frozenset[str]]:
    """``registry-constant NAME -> {tool names it lists}`` across the repo.

    Follows ``NAME = A + [..]`` / ``[*A, b]`` registry extensions transitively
    and module-level ``T = {name:..}`` element references so a consumer's
    ``tools=<registry>`` resolves to the exact census tool set it mounts.
    """
    direct: dict[str, set[str]] = {}
    refs: dict[str, set[str]] = {}
    for p in files:
        tree = _parse(p)
        if tree is None:
            continue
        named_dicts: dict[str, ast.Dict] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        named_dicts[t.id] = node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                    and isinstance(node.value, ast.Dict):
                named_dicts[node.target.id] = node.value
        for node in ast.walk(tree):
            targets: list[ast.expr] = []
            value: ast.expr | None = None
            if isinstance(node, ast.Assign):
                targets, value = node.targets, node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets, value = [node.target], node.value
            else:
                continue
            name_ts = [t.id for t in targets if isinstance(t, ast.Name)]
            if not name_ts or value is None:
                continue
            elts = _iter_list_elts(value)
            base_names = _binop_operand_names(value)
            if not elts and not base_names:
                continue
            toolnames: set[str] = set()
            for e in elts:
                d: ast.Dict | None = None
                if isinstance(e, ast.Dict):
                    d = e
                elif isinstance(e, ast.Name) and e.id in named_dicts:
                    d = named_dicts[e.id]
                if d is not None:
                    nm = _dict_name(d)
                    if nm:
                        toolnames.add(nm)
            if toolnames or base_names:
                for nm in name_ts:
                    direct.setdefault(nm, set()).update(toolnames)
                    refs.setdefault(nm, set()).update(base_names)
    # transitive close over registry extensions (bounded)
    resolved: dict[str, set[str]] = {}

    def _resolve(name: str, seen: set[str]) -> set[str]:
        if name in resolved:
            return resolved[name]
        if name in seen:
            return set(direct.get(name, ()))
        seen.add(name)
        acc = set(direct.get(name, ()))
        for r in refs.get(name, ()):
            acc |= _resolve(r, seen)
        resolved[name] = acc
        return acc

    return {n: frozenset(_resolve(n, set())) for n in set(direct) | set(refs)}


_MOUNT_CALL_ATTRS = frozenset({"create", "stream"})


def _detect_py_mount_consumers(
    files: list[Path], root: Path,
    reg_tool_names: dict[str, frozenset[str]],
    tool_domain: dict[str, str | None],
) -> list[MountConsumer]:
    """Anthropic-shaped ``messages.create/.stream(system=…, tools=<registry>)``
    and pydantic-ai ``Agent(instructions=…, tools=<registry>)`` consumers.

    The ``tools=`` argument is resolved by a BOUNDED def-use walk (local var
    assignment, self-method return, ``filter_and_cache_tools(tool_definitions=)``
    keyword) back to the registry constant(s) it references, then to census
    domains via ``reg_tool_names`` × ``tool_domain``. A ``disabled_tools=<literal
    set>`` narrows the mount deterministically (conditional selection, §6.2);
    a non-literal (function-call) disabled set is left at the schema level and
    noted, never guessed.
    """
    reg_names = set(reg_tool_names)
    out: list[MountConsumer] = []
    for p in files:
        tree = _parse(p)
        if tree is None:
            continue
        rel = _rel(p, root)
        func_assigns: dict[int, dict[str, ast.expr]] = {}
        method_returns: dict[str, ast.expr] = {}
        parent_fn: dict[int, ast.AST] = {}
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                amap: dict[str, ast.expr] = {}
                for n in ast.walk(fn):
                    if isinstance(n, ast.Assign):
                        for t in n.targets:
                            if isinstance(t, ast.Name):
                                amap[t.id] = n.value
                    elif isinstance(n, ast.AnnAssign) and n.value is not None \
                            and isinstance(n.target, ast.Name):
                        amap[n.target.id] = n.value
                    if isinstance(n, ast.Return) and n.value is not None:
                        method_returns.setdefault(fn.name, n.value)
                func_assigns[id(fn)] = amap
                for n in ast.walk(fn):
                    parent_fn.setdefault(id(n), fn)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fnode = node.func
            is_msg = isinstance(fnode, ast.Attribute) and fnode.attr in _MOUNT_CALL_ATTRS
            is_agent = isinstance(fnode, ast.Name) and fnode.id in ("Agent", "AsyncAgent")
            if not (is_msg or is_agent):
                continue
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            if not (("system" in kw or "instructions" in kw) and "tools" in kw):
                continue
            hit_regs = _resolve_tools_registries(
                kw["tools"], node, parent_fn, func_assigns, method_returns, reg_names,
            )
            if not hit_regs:
                continue  # a consumer whose registry did not resolve — honest skip
            tool_names: set[str] = set()
            for r in hit_regs:
                tool_names |= reg_tool_names.get(r, frozenset())
            excluded_names = _static_disabled_tools(kw.get("disabled_tools"))
            live_names = {t for t in tool_names if t not in excluded_names}
            domains = sorted({
                dom for t in live_names if (dom := tool_domain.get(t))
            })
            excl_domains = sorted({
                dom for t in excluded_names
                if t in tool_names and (dom := tool_domain.get(t))
                and dom not in domains
            })
            if not domains:
                continue
            out.append(MountConsumer(
                site=f"{rel}:{node.lineno}",
                kind="agent-ctor" if is_agent else "anthropic-call",
                domains=tuple(domains),
                tools=tuple(sorted(live_names)),
                excluded=tuple(excl_domains),
                registries=tuple(sorted(hit_regs)),
            ))
    return out


def _resolve_tools_registries(
    tools_expr: ast.expr, call: ast.Call,
    parent_fn: dict[int, ast.AST], func_assigns: dict[int, dict[str, ast.expr]],
    method_returns: dict[str, ast.expr], reg_names: set[str],
) -> set[str]:
    """Bounded def-use resolution of a ``tools=`` argument to registry NAMES."""
    hit: set[str] = set()
    work: list[ast.expr] = [tools_expr]
    steps = 0
    fn = parent_fn.get(id(call))
    amap = func_assigns.get(id(fn), {}) if fn else {}
    while work and steps < 60:
        e = work.pop()
        steps += 1
        names = _reg_referenced_names(e)
        hit |= names & reg_names
        for nm in list(names):
            if nm in amap:
                work.append(amap[nm])
        for c in ast.walk(e):
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute):
                m = c.func.attr
                if m in method_returns:
                    work.append(method_returns[m])
            if isinstance(c, ast.Call):
                for k in c.keywords:
                    if k.arg in ("tool_definitions", "tools"):
                        work.append(k.value)
    return hit


def _static_disabled_tools(expr: ast.expr | None) -> frozenset[str]:
    """Tool names a ``disabled_tools=`` argument statically removes — only when
    the argument is a literal set/list/tuple of string constants. A non-literal
    (function call, name) is dispatch-time gating that keeps the SCHEMA mount
    cross-org identical, so it removes nothing here (honest, not guessed)."""
    if expr is None:
        return frozenset()
    if isinstance(expr, (ast.Set, ast.List, ast.Tuple)):
        return frozenset(
            el.value for el in expr.elts
            if isinstance(el, ast.Constant) and isinstance(el.value, str)
        )
    return frozenset()


_TS_REGISTER_RE = re.compile(
    r"^(?P<indent>\s*)(?P<comment>//\s*|/\*\s*)?[\w.]*[Rr]egistry\.register\(\s*(?P<feat>\w+)")


def _detect_ts_register_consumers(
    root: Path, census_domains: frozenset[str],
    domain_tools: dict[str, list[str]],
) -> list[MountConsumer]:
    """langfuse-style ``toolRegistry.register(<x>Feature)`` MCP mount bootstrap.

    Each register call mounts one DOMAIN; a commented/disabled register is the
    conditional-selection anti-case (langfuse ``// tracesFeature``) and is
    excluded, not mounted. Domain slugs are matched tolerantly onto the census
    domain slugs so the mount and the census agree. The consumer's ``tools`` are
    the census tools of its mounted domains (the register mounts the whole
    domain), so tool-grain provenance agrees with the domain-grain mount.
    """
    out: list[MountConsumer] = []
    for p in sorted(root.rglob("*.ts")):
        if any(s in p.parts for s in _SKIP_DIRS) or "__tests__" in p.parts \
                or p.name.endswith((".test.ts", ".servertest.ts", ".spec.ts")):
            continue
        try:
            txt = p.read_text(encoding="utf-8")
        except OSError:
            continue
        if "egistry.register(" not in txt:
            continue
        live: set[str] = set()
        disabled: set[str] = set()
        line0 = 0
        for i, line in enumerate(txt.splitlines(), 1):
            m = _TS_REGISTER_RE.match(line)
            if not m:
                continue
            if not line0:
                line0 = i
            dom = _ts_feature_to_domain(m.group("feat"))
            (disabled if m.group("comment") else live).add(dom)
        live_c = _match_domains(live, census_domains)
        disabled_c = _match_domains(disabled, census_domains) - live_c
        if live_c:
            _tools = sorted(
                t for d in live_c for t in domain_tools.get(d, ()))
            out.append(MountConsumer(
                site=f"{_rel(p, root)}:{line0}",
                kind="registry-register",
                domains=tuple(sorted(live_c)),
                tools=tuple(_tools),
                excluded=tuple(sorted(disabled_c)),
                registries=("toolRegistry",),
            ))
    return out


def _ts_feature_to_domain(feat: str) -> str:
    s = re.sub(r"Feature$", "", feat)
    s = re.sub(r"(?<!^)(?=[A-Z])", "-", s).lower()
    return s


def _match_domains(slugs: set[str], census_domains: frozenset[str]) -> set[str]:
    """Map register-derived slugs onto census domain slugs by token overlap."""
    out: set[str] = set()
    for cd in census_domains:
        ctok = set(cd.split("-"))
        for s in slugs:
            stok = set(s.split("-"))
            if ctok & stok or cd in s or s in cd:
                out.add(cd)
                break
    return out


def _detect_mount_consumers(
    root: Path, py_files: list[Path], resolved: list[ToolEntry],
    *, disabled_domains: tuple[str, ...], include_ts: bool,
) -> tuple[MountConsumer, ...]:
    """Orchestrate consumer detection over both surfaces; deterministic order."""
    tool_domain = {t.tool: t.domain for t in resolved if t.role == "capability"}
    census_domains = frozenset(
        t.domain for t in resolved if t.role == "capability" and t.domain)
    domain_tools: dict[str, list[str]] = {}
    for t in resolved:
        if t.role == "capability" and t.domain:
            domain_tools.setdefault(t.domain, []).append(t.tool)
    consumers: list[MountConsumer] = []
    # Python (Anthropic / pydantic-ai) consumers
    reg_tool_names = _registry_tool_names(py_files, root)
    consumers.extend(_detect_py_mount_consumers(
        py_files, root, reg_tool_names, tool_domain))
    # TS register consumers (langfuse) — only when the TS census armed them
    if include_ts:
        consumers.extend(_detect_ts_register_consumers(
            root, census_domains, domain_tools))
    return tuple(sorted(consumers, key=lambda c: c.site))


# ── Phase-2 — agent SYSTEM-PROMPT detection (3 anchor classes) ─────────────
#
# Detected by CONSUMPTION, never by the token ``prompt`` (§6.3): a system prompt
# is the value handed to an agent LLM call as ``system=`` / ``instructions=`` /
# ``{"role":"system"}``, a ``*-system-prompt.txt`` named file, or a strongly
# named / agent-consumed string const. Scoped to the agent machinery (under
# ``agent_root`` OR co-located with ``tools=``) so repo-wide UTILITY LLM calls
# (translation, summarisation, query-rephrase) are excluded — the RefApp probe
# has 41 ``system=`` call-sites but only 9 are the agent's (32 are utility).

_SYS_KWARGS = ("system", "instructions", "system_prompt")
_MOUNT_CALL_ATTRS_SP = frozenset({"create", "stream"})
_FILE_LOADER_FUNCS = frozenset({
    "read_text", "read", "load_prompt", "get_prompt", "open", "read_file",
    "load", "load_text", "get_system_prompt",
})
#: exact strong const names that stand alone as an agent system prompt even
#: without a traced consumer (the canonical cross-framework conventions). Any
#: OTHER const is an anchor ONLY when consumed at an agent call-site — so the
#: repo's many UTILITY ``*_SYSTEM_PROMPT`` consts (onyx image-summarisation /
#: query-rephrase) never spray.
_CANONICAL_PROMPT_CONSTS = frozenset({
    "SYSTEM_PROMPT", "DEFAULT_SYSTEM_PROMPT", "SKILL_TEXT",
    "AGENT_INSTRUCTIONS", "DEFAULT_INSTRUCTIONS", "DEFAULT_AGENT_PROMPT",
    "AGENT_SYSTEM_PROMPT",
})
#: path segments that disqualify a ``*system-prompt*`` file from being an agent
#: prompt (a DB migration / test fixture is not the running agent's prompt).
_PROMPT_FILE_EXCLUDE = frozenset({
    "migrations", "versions", "alembic", "test", "tests", "__tests__",
    "node_modules", ".venv", "fixtures", "snapshots", "__snapshots__",
})


def _module_prompt_consts(tree: ast.Module) -> dict[str, int]:
    """module-level ``NAME = <str/f-str/wrapper-call>`` where NAME reads like a
    prompt/instruction const (UPPER, carries a SYSTEM/PROMPT/SKILL/INSTRUCTION
    token). NAME→lineno. The name is corroboration, never the decision — a
    non-canonical const only becomes an anchor once consumed (see caller)."""
    out: dict[str, int] = {}
    for node in tree.body:
        tgts: list[ast.expr] = []
        val: ast.expr | None = None
        if isinstance(node, ast.Assign):
            tgts, val = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            tgts, val = [node.target], node.value
        if val is None:
            continue
        strish = isinstance(val, (ast.Constant, ast.JoinedStr, ast.Call, ast.BinOp))
        for t in tgts:
            if isinstance(t, ast.Name) and t.id.isupper() and strish and any(
                tok in t.id for tok in ("SYSTEM", "PROMPT", "SKILL", "INSTRUCT")
            ):
                out.setdefault(t.id, node.lineno)
    return out


def _openai_system_content(call: ast.Call) -> ast.expr | None:
    """``messages=[{"role":"system","content":X}]`` → X (OpenAI/LiteLLM form)."""
    for k in call.keywords:
        if k.arg != "messages":
            continue
        for el in getattr(k.value, "elts", []):
            if not isinstance(el, ast.Dict):
                continue
            role = content = None
            for kk, vv in zip(el.keys, el.values):
                if isinstance(kk, ast.Constant) and kk.value == "role" \
                        and isinstance(vv, ast.Constant):
                    role = vv.value
                if isinstance(kk, ast.Constant) and kk.value == "content":
                    content = vv
            if role == "system" and content is not None:
                return content
    return None


def _resolve_system_source(
    expr: ast.expr, consts: dict[str, int],
    amap: dict[str, ast.expr], method_returns: dict[str, ast.expr],
) -> tuple[str, str]:
    """(source_kind, source_ref) for a ``system=`` value — bounded def-use."""
    seen = 0
    cur = expr
    while seen < 40:
        seen += 1
        if isinstance(cur, ast.Constant) and isinstance(cur.value, str):
            return "inline", "<inline-string>"
        if isinstance(cur, ast.JoinedStr):
            return "inline", "<f-string>"
        if isinstance(cur, ast.Name):
            if cur.id in consts:
                return "const", cur.id
            if cur.id in amap:
                cur = amap[cur.id]
                continue
            return "dynamic", cur.id  # param / unresolved local
        if isinstance(cur, ast.Attribute):
            return "dynamic", cur.attr  # config.instructions / self.prompt
        if isinstance(cur, ast.Call):
            fn = cur.func
            fname = fn.attr if isinstance(fn, ast.Attribute) else (
                fn.id if isinstance(fn, ast.Name) else "?")
            # a wrapped named const: system_with_cache(ANALYSIS_SYSTEM)
            for a in list(cur.args) + [k.value for k in cur.keywords]:
                if isinstance(a, ast.Name) and a.id in consts:
                    return "const", a.id
            if fname in _FILE_LOADER_FUNCS:
                for a in cur.args:
                    if isinstance(a, ast.Constant) and isinstance(a.value, str):
                        return "file", a.value
                return "file", fname
            if fname in method_returns:
                cur = method_returns[fname]
                continue
            return "builder", fname
        return "other", type(cur).__name__
    return "other", "<deep>"


def _detect_py_system_prompts(
    files: list[Path], root: Path, agent_root: str | None,
) -> tuple[list[SystemPromptAnchor], set[str]]:
    """Class 1 (call-site) + class 3 (named const) over Python.

    Returns (anchors, agent_consts) — agent_consts is the set of const names a
    call-site under the agent machinery consumed (so a standalone class-3 pass
    can attach them even where the name is non-canonical)."""
    anchors: list[SystemPromptAnchor] = []
    agent_consts: set[str] = set()
    # provenance: const NAME (per file) -> (file, lineno) so a consumed const's
    # ``site`` points at its definition, not the call-site.
    const_site: dict[str, str] = {}
    file_consts: list[tuple[str, dict[str, int]]] = []
    for p in files:
        tree = _parse(p)
        if tree is None:
            continue
        rel = _rel(p, root)
        consts = _module_prompt_consts(tree)
        file_consts.append((rel, consts))
        for nm, ln in consts.items():
            const_site.setdefault(nm, f"{rel}:{ln}")
        func_assigns: dict[int, dict[str, ast.expr]] = {}
        method_returns: dict[str, ast.expr] = {}
        parent_fn: dict[int, ast.AST] = {}
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                m: dict[str, ast.expr] = {}
                for n in ast.walk(fn):
                    if isinstance(n, ast.Assign):
                        for t in n.targets:
                            if isinstance(t, ast.Name):
                                m[t.id] = n.value
                    elif isinstance(n, ast.AnnAssign) and n.value is not None \
                            and isinstance(n.target, ast.Name):
                        m[n.target.id] = n.value
                    if isinstance(n, ast.Return) and n.value is not None:
                        method_returns.setdefault(fn.name, n.value)
                func_assigns[id(fn)] = m
                for n in ast.walk(fn):
                    parent_fn.setdefault(id(n), fn)
        under_agent = agent_root is not None and (
            rel == agent_root or rel.startswith(agent_root + "/"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            is_msg = isinstance(fn, ast.Attribute) and fn.attr in _MOUNT_CALL_ATTRS_SP
            is_agent = isinstance(fn, ast.Name) and fn.id in ("Agent", "AsyncAgent")
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            sys_expr: ast.expr | None = None
            kwarg = ""
            for kn in _SYS_KWARGS:
                if kn in kw:
                    sys_expr, kwarg = kw[kn], kn
                    break
            if sys_expr is None and (is_msg or is_agent):
                oc = _openai_system_content(node)
                if oc is not None:
                    sys_expr, kwarg = oc, "role:system"
            if sys_expr is None:
                continue
            # AGENT SCOPE (§6.3): under agent_root OR co-located with tools=.
            # Excludes repo-wide utility LLM calls (translation, summarisation).
            if not (under_agent or "tools" in kw):
                continue
            _fn = parent_fn.get(id(node))
            amap = func_assigns.get(id(_fn), {}) if _fn else {}
            kind, ref = _resolve_system_source(
                sys_expr, consts, amap, method_returns)
            site = f"{rel}:{node.lineno}"
            asite = const_site.get(ref, site) if kind == "const" else site
            if kind == "const":
                agent_consts.add(ref)
            anchors.append(SystemPromptAnchor(
                site=asite, anchor_class="call-site", kwarg=kwarg,
                source_kind=kind, source_ref=ref, consumer_site=site,
            ))
    # class 3 standalone — a canonical-named const that no call-site consumed is
    # still an agent system prompt (onyx DEFAULT_SYSTEM_PROMPT); a non-canonical
    # const is NOT emitted here (only via the consumed path above) so utility
    # ``*_SYSTEM_PROMPT`` consts never spray.
    seen_const = {a.source_ref for a in anchors if a.source_kind == "const"}
    for rel, consts in file_consts:
        for nm, ln in consts.items():
            if nm in _CANONICAL_PROMPT_CONSTS and nm not in seen_const:
                anchors.append(SystemPromptAnchor(
                    site=f"{rel}:{ln}", anchor_class="named-const",
                    source_kind="const", source_ref=nm, consumer_site="",
                ))
                seen_const.add(nm)
    return anchors, agent_consts


def _detect_prompt_files(root: Path) -> list[SystemPromptAnchor]:
    """Class 2 — ``*-system-prompt.*`` / ``*system_prompt*`` named files. The
    specific system-prompt naming (NOT a bare ``prompts/`` dir) is what keeps
    the langfuse ``prompts`` CRUD feature out (§6.3). Migrations / tests /
    fixtures are excluded — a DB migration named ``*_system_prompt`` is history,
    not the running agent's prompt."""
    out: list[SystemPromptAnchor] = []
    seen: set[str] = set()
    for pat in ("*-system-prompt.*", "*system_prompt*", "*system-prompt*"):
        for f in root.rglob(pat):
            if not f.is_file():
                continue
            rel = _rel(f, root)
            if rel in seen:
                continue
            segs = set(rel.lower().split("/"))
            if segs & _PROMPT_FILE_EXCLUDE:
                continue
            if f.suffix.lower() not in (".txt", ".md", ".py", ".ts", ".tsx",
                                        ".j2", ".jinja", ".jinja2", ".tmpl"):
                continue
            seen.add(rel)
            out.append(SystemPromptAnchor(
                site=rel, anchor_class="prompt-file",
                source_kind="file", source_ref=rel, consumer_site="",
            ))
    return sorted(out, key=lambda a: a.site)


def _detect_system_prompts(
    root: Path, py_files: list[Path], census_agent_root: str | None,
) -> tuple[SystemPromptAnchor, ...]:
    """Orchestrate the 3 anchor classes; deterministic order."""
    anchors, _agent_consts = _detect_py_system_prompts(
        py_files, root, census_agent_root)
    anchors = list(anchors) + _detect_prompt_files(root)
    return tuple(sorted(
        anchors, key=lambda a: (a.anchor_class, a.site, a.source_ref)))


# ── Phase-3 — agent SKILL-layer detection (RefApp convention + .claude guard) ─
#
# The product-agent skill layer is the LEAST standardised anatomy — the probe
# corpus has code-skills in RefApp ONLY (a ``skills/`` module exporting
# ``REQUIRED_TOOLS`` + ``ALWAYS_LOADED``; the REQUIRED_TOOLS set is the
# skill→tools link). The convention generalises (any repo adopting it is
# detected) but coverage is honestly RefApp-only — the others emit zero, never an
# over-mint. A cross-vendor ``.claude/skills/*/SKILL.md`` is detected but
# classified DEV-TIME by its structural path (§6.3) and never attached to a
# product consumer.


def _detect_claude_dev_skills(root: Path) -> list[SkillAnchor]:
    """Cross-vendor ``.claude/skills/*/SKILL.md`` — DEV-TIME by PATH (the
    Claude Code dev-tooling home). A bounded top-level glob (never a deep
    descent) so nested-worktree ``.claude`` copies are not double-counted."""
    out: list[SkillAnchor] = []
    sd = root / ".claude" / "skills"
    if sd.is_dir():
        for md in sorted(sd.glob("*/SKILL.md")):
            out.append(SkillAnchor(
                name=md.parent.name, file=_rel(md, root),
                role="dev-time", source="claude-skill"))
    return out


def _detect_skill_layer(
    root: Path, cap_skills: "list[_SkillInfo]", persona_files: list[str],
) -> tuple[SkillAnchor, ...]:
    """The agent skill layer: product code-skills (capability + persona, reused
    from the B81 ``_detect_skills`` pass) + dev-time ``.claude`` skills. The two
    are distinguished by MECHANISM — a ``REQUIRED_TOOLS`` module wired to the
    product tool registry vs a ``.claude/`` markdown skill — not a dictionary."""
    anchors: list[SkillAnchor] = []
    for sk in cap_skills:
        anchors.append(SkillAnchor(
            name=sk.module, file=sk.file, role="capability", source="code-skill",
            required_tools=tuple(sorted(sk.required_tools)),
            always_loaded=sk.always_loaded))
    for pf in sorted(persona_files):
        anchors.append(SkillAnchor(
            name=Path(pf).stem, file=pf, role="persona", source="code-skill"))
    anchors.extend(_detect_claude_dev_skills(root))
    return tuple(sorted(anchors, key=lambda a: (a.role, a.name, a.file)))


# ── Phase-4 — the IMPORT-BRIDGE (static endpoint→consumer import) ──────────
#
# The consumer→tool edge is a dynamic dispatch the flow graph never sees, but
# the endpoint→CONSUMER edge is a STATIC import that DOES exist (v1_messages.py:
# ``from agent.core import AgentCore``). This bridge lists the repo files that
# statically import a mount-CONSUMER module — importing merely a tool module or
# the registry does NOT qualify (a product surface may use a single tool; only
# importing the consumer means "this journey RUNS the agent").


def _detect_consumer_importers(
    root: Path, py_files: list[Path], agent_root: str | None,
    consumer_files: frozenset[str],
) -> tuple[str, ...]:
    """Repo files that statically import a mount-consumer module or the agent
    skills package. Resolution: ``agent.X`` (package name == agent_root
    basename) → ``agent_root/X`` — mechanism, not a repo dictionary. ``.claude``
    nested-worktree copies are excluded (they poison with duplicate imports)."""
    if not agent_root or not consumer_files:
        return ()
    ar_base = agent_root.rsplit("/", 1)[-1]
    skills_dir = agent_root + "/skills"

    def _hits(module: str) -> bool:
        parts = module.split(".")
        if parts[0] != ar_base:
            return False
        base = agent_root + ("/" + "/".join(parts[1:]) if len(parts) > 1 else "")
        if base + ".py" in consumer_files or base in consumer_files:
            return True
        # the skills package (agent prompt/skill assembly) is a consumer signal
        return base == skills_dir or base.startswith(skills_dir + "/")

    # the mount-consumer files themselves seed the set: a journey ENTERING in
    # the consumer module IS an agent-consumer journey (no import needed).
    importers: set[str] = set(consumer_files)
    for p in py_files:
        rel = _rel(p, root)
        if rel.split("/", 1)[0] == ".claude":
            continue
        tree = _parse(p)
        if tree is None:
            continue
        for n in ast.walk(tree):
            mod: str | None = None
            if isinstance(n, ast.ImportFrom) and n.module:
                mod = n.module
            elif isinstance(n, ast.Import):
                mod = n.names[0].name if n.names else None
            if mod and _hits(mod):
                importers.add(rel)
                break
    return tuple(sorted(importers))


def detect_registry_census(
    repo_path: str | Path, *, pf_names: Iterable[str] = (),
    include_ts: bool = False, include_mounts: bool = False,
    include_system_prompts: bool = False,
    include_skills: bool = False, include_anatomy_rows: bool = False,
) -> RegistryCensus:
    """Detect the tool/skill registry of ``repo_path`` (Seg A). ``$0`` LLM.

    ``pf_names`` (existing product-feature display names) lets skill/partition
    domains resolve to a real capability PF for clean homing; passing ``()``
    still yields structural domain slugs.

    ``include_ts`` (B81-it2, wired to ``WYSTAN_AGENT_SURFACE_TS``, default
    OFF) additionally reads the ANCHORED TypeScript Form A (langfuse
    ``defineTool`` / lobe-chat ``BuiltinToolManifest``). When ``False`` the
    result is byte-identical to the shipped Python-only census.

    ``include_mounts`` (Phase-1, wired to ``WYSTAN_AGENT_MOUNT_ATTRIBUTION``,
    default OFF) additionally parses the CONSUMER mount-sites and stamps
    ``mount_consumers``. When ``False`` the tuple stays empty and the census is
    byte-identical to the pre-Phase-1 world (armed-only).

    ``include_system_prompts`` (Phase-2, wired to
    ``WYSTAN_AGENT_SYSTEM_PROMPT``, default OFF) additionally detects the
    agent system prompts and stamps ``system_prompts`` (armed-only, empty when
    OFF). Independent of ``include_mounts`` for independent testability.

    ``include_skills`` (Phase-3, wired to ``WYSTAN_AGENT_SKILLS``, default
    OFF) additionally detects the agent skill layer (code-skills + dev-time
    ``.claude`` skills) and stamps ``skill_layer`` (armed-only, empty when OFF).

    ``include_anatomy_rows`` (Phase-4, wired to
    ``WYSTAN_AGENT_ANATOMY_ROWS``, default OFF) IMPLIES the Phase 1-3
    detection (it needs the full anatomy to attach) and additionally stamps
    ``consumer_importer_files`` (the static import-bridge). Empty when OFF.
    """
    root = Path(repo_path)
    if not root.is_dir():
        return RegistryCensus()
    py_files = list(_iter_py_files(root, include_fake=False))

    form_a: list[ToolEntry] = []
    disabled: list[str] = []
    map_entries: list[ToolEntry] = []
    map_bridges: list[str] = []
    rt_map: list[str] = []
    dec_entries: list[ToolEntry] = []
    if py_files:
        form_a, disabled = _detect_form_a(root, py_files)
        map_entries, map_bridges, rt_map = _detect_form_b_map(
            root, py_files, py_files)
        dec_entries = _detect_form_b_decorator(root, py_files)

    # B81-it2 — anchored TS Form A (sub-flagged; empty when include_ts=False).
    ts_entries: list[ToolEntry] = []
    ts_anchors: list[str] = []
    disabled_domains: list[str] = []
    ts_agent_root: str | None = None
    if include_ts:
        ts_files = list(_iter_ts_files(root))
        if ts_files:
            ts_entries = (
                _detect_ts_define_tool(root, ts_files)
                + _detect_ts_builtin_manifest(root, ts_files)
            )
            _reg_doms, disabled_domains, ts_agent_root = (
                _detect_ts_mcp_feature_module(root, ts_files))
            # anti-case 1 at the DOMAIN grain: a tool file under a disabled
            # (commented-out) domain never counts (langfuse ``// tracesFeature``).
            if disabled_domains:
                _dset = set(disabled_domains)
                ts_entries = [e for e in ts_entries if e.domain not in _dset]
            ts_anchors = sorted({e.ts_anchor for e in ts_entries if e.ts_anchor})

    # merge + dedup. Python forms dedup by tool NAME (registry-extension union
    # authority — unchanged, byte-identical). TS Form A dedups by
    # (domain, tool) so a bare tool name (``search``/``create``) shared across
    # two packages is not collapsed — distinct domains are distinct tools.
    merged: dict[object, ToolEntry] = {}
    for e in form_a + map_entries + dec_entries:
        merged.setdefault(e.tool, e)
    for e in ts_entries:
        merged.setdefault(("ts", e.domain, e.tool), e)
    all_entries = list(merged.values())
    if not all_entries:
        return RegistryCensus()

    # anti-case 6 — dynamic-wrapper bridges (only meaningful once a registry is
    # present, so an unrelated repo never trips it).
    bridges = list(map_bridges)
    for fam in _detect_bridges(root, py_files):
        if fam not in bridges:
            bridges.append(fam)

    cap_names = frozenset(e.tool for e in all_entries if e.role == "capability")

    # signal 1 — partition module (over the FORM-A tool names, which are the
    # LLM-facing names the partition frozensets enumerate).
    partition, partition_full, partition_module = _detect_partition(
        root, py_files, cap_names)

    # signal 3 — skills
    skills, cap_skill_files, persona_files = _detect_skills(root)
    tool_skill: dict[str, list[str]] = {}
    tool_skill_domain: dict[str, str] = {}
    for sk in skills:
        dom = _skill_domain(sk, pf_names)
        for tn in sk.required_tools:
            tool_skill.setdefault(tn, []).append(sk.module)
            # first capability skill wins the domain (deterministic by sort)
            tool_skill_domain.setdefault(tn, dom)

    # resolve each capability tool's domain by the ranked signal.
    resolved: list[ToolEntry] = []
    for e in all_entries:
        if e.role != "capability":
            resolved.append(e)
            continue
        domain, signal = None, "none"
        part_dom = partition.get(e.tool)
        skill_dom = tool_skill_domain.get(e.tool)
        part_catchall = (part_dom is not None
                         and part_dom.rstrip("s") in _CATCHALL_DOMAIN_TOKENS)
        if part_dom and not part_catchall:
            # signal 1 — a SPECIFIC partition category (labels/detectors/...)
            domain, signal = part_dom, "partition"
        elif skill_dom:
            # signal 3 — a capability skill refines a cross-cutting/absent
            # partition (carves knowledge/bulletins out of CORE_ANALYSIS).
            domain, signal = skill_dom, "skill-backref"
        elif e.domain:  # signal 2 — package-dir from Form B
            domain, signal = e.domain, e.domain_signal
        elif part_dom:
            # it3 census bucket (panel fix №3): a catch-all partition tool
            # with no skill refinement (query_bigquery, present_options) lands
            # in its FULL-category bucket (core-analysis / chat-ux) so
            # ``tools_by_domain`` sums to the partition total. Detect-only:
            # cross-domain primitives never mint (no PF bears the bucket
            # name), but the census is complete.
            domain, signal = partition_full.get(e.tool), "partition-catchall"
        resolved.append(ToolEntry(
            tool=e.tool, form=e.form, handler_file=e.handler_file,
            handler_line=e.handler_line, domain=domain, domain_signal=signal,
            role="capability", skill_backrefs=tuple(sorted(tool_skill.get(e.tool, ()))),
            source=e.source, ts_anchor=e.ts_anchor,
        ))

    # it4 №1 — name the out-of-partition capability tools (secondary
    # registries, e.g. the RefApp insights sub-agent). Only meaningful when a
    # partition exists; without one there is nothing to be "outside of".
    extra_tools: tuple[str, ...] = ()
    if partition:
        extra_tools = tuple(sorted(
            e.tool for e in resolved
            if e.role == "capability" and e.tool not in partition
        ))
    partition_covered = sum(
        1 for e in resolved if e.role == "capability" and e.tool in partition
    )
    # agent_root — the directory of the PRIMARY registry (the partition module
    # dir, RefApp backend/agent). NOT the common dir of every registry: a
    # secondary sub-agent (RefApp backend/services/insights/agent.py) would
    # broaden it to ``backend`` and make every backend flow look agent-reachable.
    agent_root: str | None
    _ts_only = bool(ts_entries) and not (form_a or map_entries or dec_entries)
    if partition_module and "/" in partition_module:
        agent_root = partition_module.rsplit("/", 1)[0]
    elif skills:
        # skills dir's parent (backend/agent/skills -> backend/agent)
        sdir = skills[0].file.rsplit("/", 1)[0]
        agent_root = sdir.rsplit("/", 1)[0] if sdir.endswith("/skills") else sdir
    elif _ts_only and ts_agent_root:
        # B81-it2 — the McpFeatureModule bootstrap dir's parent (``…/mcp/server``
        # -> ``…/mcp``) anchors the TS registry root so the stage gates
        # entry-true flows to the mcp feature tree, not all of ``web/src``
        # (langfuse). A DISTRIBUTED per-package registry (lobe-chat: 27
        # ``builtin-tool-*`` packages siblings under ``packages/``) has NO single
        # bootstrap, so ``agent_root`` stays None -> the stage is CENSUS-ONLY (no
        # Seg B/C reshape). This is the mandate's "mint only langfuse-class": a
        # broad common-dir root (``packages``) would spuriously entry-tag every
        # monorepo flow (model-bank/database/types) — refuted on the lobe-chat
        # keyless A/B (10 unrelated UFs tagged). Detection still ships (census).
        agent_root = ts_agent_root
    elif _ts_only:
        # distributed TS registry, no bootstrap -> CENSUS-ONLY (no reshape).
        agent_root = None
    else:
        # dominant handler dir across capability tools
        from collections import Counter
        dirs = Counter(
            e.handler_file.rsplit("/", 1)[0]
            for e in resolved if e.role == "capability" and "/" in e.handler_file
        )
        agent_root = dirs.most_common(1)[0][0] if dirs else None
    # Phase-4 IMPLIES Phase 1-3 detection (it needs the full anatomy to attach).
    _mounts = include_mounts or include_anatomy_rows
    _sysp = include_system_prompts or include_anatomy_rows
    _skills = include_skills or include_anatomy_rows
    # Phase-1 (armed-only): parse the CONSUMER mount-sites. Gated so a flag-OFF
    # census is byte-identical (empty tuple, no telemetry delta).
    mount_consumers: tuple[MountConsumer, ...] = ()
    if _mounts:
        mount_consumers = _detect_mount_consumers(
            root, py_files, resolved,
            disabled_domains=tuple(sorted(set(disabled_domains))),
            include_ts=include_ts,
        )
    # Phase-2 (armed-only): detect agent system prompts. Gated so a flag-OFF
    # census is byte-identical (empty tuple, no telemetry delta).
    system_prompts: tuple[SystemPromptAnchor, ...] = ()
    if _sysp:
        system_prompts = _detect_system_prompts(root, py_files, agent_root)
    # Phase-3 (armed-only): detect the agent skill layer (reuses the B81
    # code-skills pass + a dev-time .claude scan). Empty when OFF (armed-only).
    skill_layer: tuple[SkillAnchor, ...] = ()
    if _skills:
        skill_layer = _detect_skill_layer(root, skills, persona_files)
    # Phase-4 (armed-only): the static import-bridge — repo files importing a
    # mount-consumer module. Empty when OFF (byte-identical).
    consumer_importer_files: tuple[str, ...] = ()
    if include_anatomy_rows:
        _consumer_files = frozenset(
            mc.site.rsplit(":", 1)[0] for mc in mount_consumers)
        consumer_importer_files = _detect_consumer_importers(
            root, py_files, agent_root, _consumer_files)
    return RegistryCensus(
        tools=tuple(resolved),
        capability_skills=tuple(sorted(cap_skill_files)),
        persona_skills=tuple(sorted(persona_files)),
        bridges=tuple(sorted(bridges)),
        excluded_disabled=tuple(sorted(set(disabled))),
        excluded_runtime_infra=tuple(sorted(set(rt_map))),
        partition_module=partition_module,
        partition_tool_count=partition_covered,
        agent_root=agent_root,
        extra_tools=extra_tools,
        ts_anchors=tuple(ts_anchors),
        disabled_domains=tuple(sorted(set(disabled_domains))),
        mount_consumers=mount_consumers,
        system_prompts=system_prompts,
        skill_layer=skill_layer,
        consumer_importer_files=consumer_importer_files,
    )


def _common_dir(paths: list[str]) -> str | None:
    """Deepest directory that is a prefix of every path (POSIX)."""
    dirs = [p.rsplit("/", 1)[0] if "/" in p else "" for p in paths if p]
    if not dirs:
        return None
    parts = [d.split("/") for d in dirs]
    common: list[str] = []
    for group in zip(*parts):
        if all(g == group[0] for g in group):
            common.append(group[0])
        else:
            break
    return "/".join(common) or None


# ═════════════════════════════════════════════════════════════════════════
# Seg B/C — the post-UF stage (Stage 6.997)
# ═════════════════════════════════════════════════════════════════════════
#
# Runs AFTER the last journey-reshaping pass (6.7e adjudicator / 6.98 / 6.99 /
# 6.99b / 6.995 / 6.996 — the B85 placement doctrine) and BEFORE 6.998 metrics
# recompute, so the journey layer is GENUINELY final and downstream passes are
# display/LOC/telemetry only. It2 lesson (keyed A/B refutation): at the old
# post-devgrain point the KEYED-only 6.7e adjudicator demoted the 1-member
# mints to gap rows (mode=full), orphaning their claimed flows, and the mints'
# presence in its candidate pool perturbed non-agent batch adjudication.
# Conservation is by-construction: the stage never invents members (no
# mint-time bars) and never empties a source journey. It (Seg B) tags the
# existing agent-machinery journeys and (Seg C) mints ≈1-per-domain
# ``via:agent`` capability journeys over REAL agent-reachable member flows,
# homed in the real capability PFs.

_STOPWORDS = frozenset({
    "flow", "flows", "the", "a", "an", "for", "of", "to", "and", "with",
    "get", "list", "run", "agent", "via", "manage", "chat", "message",
    "generation", "stop", "assemble", "select", "common", "skills", "prompt",
    "conversation", "tool", "tools",
    # generic CRUD/action verbs — verb-token overlap is WEAK evidence (a
    # "create-widget-preview-flow" must not match Labels because label tools
    # also say create/preview). Domain attribution rides on NOUN tokens
    # (label, detector, case, erp ...) only.
    "create", "update", "delete", "edit", "view", "browse", "preview",
    "search", "assign", "unassign", "bulk", "refresh", "validate", "save",
    "load", "show", "start", "build", "query", "propose", "retrieve",
    "resolve", "generate", "lookup", "surface", "explore", "extract",
})

#: it3 (panel mandate) — a Seg C domain mint needs at least this many
#: entry-true members; below it the mint brakes (honest no-mint beats a
#: thin blob row). Scale-invariant floor, not a tuned threshold.
_MINT_MEMBER_FLOOR = 2

#: name tokens that mark the agent TRANSPORT machinery itself (the module's
#: own domain — chat / conversation / prompt-assembly), used ONLY to sweep
#: unmatched ORPHANED agent-root flows into the transport journey.
_TRANSPORT_NAME_TOKENS = frozenset({
    "agent", "chat", "conversation", "conversations", "prompt", "prompts",
    "skill", "skills", "message", "messages", "assistant",
})


def _tokens(text: str) -> set[str]:
    return {
        t for t in re.split(r"[^a-z0-9]+", str(text).lower())
        if t and t not in _STOPWORDS and len(t) > 2
    }


def _domain_keywords(census: RegistryCensus) -> dict[str, set[str]]:
    """Per-domain keyword set: the domain slug tokens + its tool-name tokens."""
    kw: dict[str, set[str]] = {}
    for dom, tools in census.tools_by_domain().items():
        toks = set(re.split(r"[^a-z0-9]+", dom.lower()))
        for t in tools:
            toks |= _tokens(t.tool)
        kw[dom] = {t for t in toks if t and len(t) > 2}
    return kw


def _humanize_domain(dom: str) -> str:
    return " ".join(w.capitalize() for w in dom.replace("-", " ").split())


def _match_pf(candidates: tuple[str, ...], pf_names: set) -> str | None:
    """The PF NAME whose tokens best match a candidate token set (else None)."""
    cand = set(candidates)
    best, best_score = None, 0
    for n in pf_names:
        if not n:
            continue
        toks = set(re.split(r"[\s_-]+", str(n).lower()))
        score = len(cand & toks)
        if score > best_score:
            best, best_score = n, score
    return best


def agent_surface_tag(kind: str, domain: str | None, tools: list[str],
                      form: str) -> dict[str, object]:
    """The ``UserFlow.agent_surface`` payload (single source of the shape)."""
    tag: dict[str, object] = {"via": "agent", "kind": kind}
    if domain:
        tag["domain"] = domain
    if tools:
        tag["tools"] = sorted(tools)
    if form:
        tag["form"] = form
    return tag


def run_agent_surface(
    census: RegistryCensus,
    product_features: "list[Feature]",
    user_flows: "list[UserFlow]",
    flows: "list[Flow]",
) -> dict[str, object]:
    """Seg B (tag/re-home entries) + Seg C (mint domain journeys). ``$0`` LLM.

    Conservation contract (self-checked, returned in telemetry):
      * total member-flow count is unchanged (no flow dropped, no member-less
        mint — a domain with zero real agent-reachable members does NOT mint);
      * a flow is only MOVED into an agent journey when it is agent-reachable
        AND not the last member of its source journey (no whole-UF
        disappearance);
      * every mint homes in an EXISTING capability PF (no PF invented).
    """
    entry_tagged: list[dict] = []
    mints: list[dict] = []
    skipped_domains: list[dict] = []
    tele: dict[str, object] = {
        "present": census.present,
        "agent_root": census.agent_root,
        "entry_tagged": entry_tagged,
        "mints": mints,
        "skipped_domains": skipped_domains,
        "conservation": {},
    }
    if not census.present or not census.agent_root:
        tele["reason"] = "no registry / no agent_root"
        return tele

    root = census.agent_root
    pf_names = {getattr(p, "name", None) for p in product_features}
    uf_by_id = {u.id: u for u in user_flows}

    # uuid -> the UFs that currently list it (the board can carry a flow in a
    # member list with user_flow_id=None; we keep membership single-valued).
    from collections import defaultdict as _dd
    uuid_owner: dict[str, "list[UserFlow]"] = _dd(list)
    for u in user_flows:
        for m in u.member_flow_ids:
            uuid_owner[m].append(u)

    def _reassign(f: "Flow", target: "UserFlow") -> None:
        """Move ``f`` to ``target``, preserving single membership everywhere."""
        uid = getattr(f, "uuid")
        for u in list(uuid_owner.get(uid, [])):
            if uid in u.member_flow_ids:
                u.member_flow_ids.remove(uid)
                u.member_count = len(u.member_flow_ids)
        if uid not in target.member_flow_ids:
            target.member_flow_ids.append(uid)
            target.member_count = len(target.member_flow_ids)
        uuid_owner[uid] = [target]
        f.user_flow_id = target.id

    def _entry_file(f: "Flow") -> str:
        return getattr(f, "entry_point_file", None) or (
            (getattr(f, "paths", None) or [""])[0]
        )

    def _entry_in_agent(f: "Flow") -> bool:
        # ONLY flows that ENTER in the agent machinery are agent-surface flows.
        # A frontend flow that merely touches a tool handler as a secondary
        # path is a UI journey — its agent richness surfaces on the keyed
        # symbol-traced scan, never by stealing it here.
        ef = _entry_file(f)
        return ef == root or ef.startswith(root + "/")

    # source-UF member counts (protect against emptying a source journey)
    src_uf_count: dict[str, int] = {}
    for f in flows:
        uid = getattr(f, "user_flow_id", None)
        if uid:
            src_uf_count[uid] = src_uf_count.get(uid, 0) + 1

    # conservation baseline — the membership state BEFORE this stage. The gate
    # measures the DELTA we introduce (a drop / a NEW duplicate), never the
    # board's PRE-EXISTING state: a keyless board can already carry a uuid in
    # two member lists, which is not this stage's doing.
    members_before_list = [m for u in user_flows for m in u.member_flow_ids]
    members_before_set = set(members_before_list)
    dupes_before = len(members_before_list) - len(members_before_set)

    entry_flows = [
        f for f in flows if getattr(f, "uuid", "") and _entry_in_agent(f)
    ]

    # ORPHANED agent-machinery flows: line-level flows that belong to NO
    # journey at all (user_flow_id unset AND not in any member list) AND touch
    # the agent machinery. Claiming them is conservation-FREE — there is no
    # source journey to empty.
    def _agent_path(f: "Flow") -> str | None:
        for p in (getattr(f, "paths", None) or []):
            if p == root or p.startswith(root + "/"):
                return p
        return None

    orphan_pool = [
        f for f in flows
        if getattr(f, "uuid", "")
        and not getattr(f, "user_flow_id", None)
        and getattr(f, "uuid") not in members_before_set
        and _agent_path(f) is not None
    ]

    # ── Seg C first — claim the DOMAIN-specific agent flows ──
    #
    # it3 ENTRY-POINT GATE (panel fix №1, NOT-TRUSTWORTHY verdict on it2b):
    # a flow is a via:agent CAPABILITY member ONLY when its ENTRY POINT lives
    # inside the agent machinery (a tool-implementation module of the domain —
    # report_tools.py / tools.py / the census handler files — or agent-core;
    # all of them live under ``agent_root``). A mere PATH overlap is a
    # shared-helper IMPORT, not agent reachability: on the keyed RefApp board
    # 42/43 members of 'Detectors via agent' were plain REST CRUD flows
    # entering in routers/detectors.py that only imported
    # ``from agent.report_tools``, and all 3 'Integrations via agent'
    # members entered in detector-tuning beam.py. Both classes are dropped by
    # this gate; an honest no-mint beats a blob.
    kw = _domain_keywords(census)
    domain_members: dict[str, list["Flow"]] = {}
    claimed: set[str] = set()

    def _best_domain(f: "Flow", *, path_weight: int) -> tuple[str | None, int]:
        """Best-scoring capability domain for a flow.

        Name-token overlap + ``path_weight`` × ENTRY-file-stem overlap (the
        module a flow ENTERS in is the strongest domain tell: a flow entering
        report_tools.py weighs toward detectors even when the name also
        says "cases"). Deterministic: domains scanned in sorted order,
        strict > to win.
        """
        ftoks = _tokens(getattr(f, "name", ""))
        ap = _entry_file(f)
        stem = ap.rsplit("/", 1)[-1]
        ptoks = _tokens(stem.rsplit(".", 1)[0].replace("_", "-"))
        best_dom, best_score = None, 0
        for dom in sorted(kw):
            if dom not in pf_names:
                continue  # only a domain with a real capability PF may mint
            dkw = kw[dom]
            score = len(ftoks & dkw) + path_weight * len(ptoks & dkw)
            if score > best_score:
                best_dom, best_score = dom, score
        return best_dom, best_score

    for f in entry_flows:
        best_dom, best_score = _best_domain(f, path_weight=1)
        if best_dom and best_score > 0:
            domain_members.setdefault(best_dom, []).append(f)
            claimed.add(getattr(f, "uuid"))

    for f in orphan_pool:
        if getattr(f, "uuid") in claimed:
            continue
        # it3 entry gate: an orphan qualifies for a DOMAIN claim only when it
        # ENTERS inside the agent machinery — path-only overlap is the
        # shared-helper-import false positive the panel refuted.
        if not _entry_in_agent(f):
            continue
        # orphans need name+entry agreement (score >= 2) — an incidental
        # single-token brush must not annex a foreign-machinery flow.
        best_dom, best_score = _best_domain(f, path_weight=2)
        if best_dom and best_score >= 2:
            domain_members.setdefault(best_dom, []).append(f)
            claimed.add(getattr(f, "uuid"))

    existing_names = {u.name.strip().lower() for u in user_flows}
    existing_ids = {u.id for u in user_flows}
    new_ufs: "list[UserFlow]" = []
    moved_total = 0
    transport_rehomed = 0
    _seq = [0]

    def _new_uf_id() -> str:
        while True:
            _seq[0] += 1
            cand = f"UF-AGENT-{_seq[0]:03d}"
            if cand not in existing_ids:
                existing_ids.add(cand)
                return cand

    from wystan.models.types import UserFlow  # local — avoid import cycle
    # B81-it2 role-gate (TS mint-gate, armed-only): a TS-sourced DOMAIN that is
    # agent MACHINERY / TRANSPORT / RUNTIME-INFRA (lobe-chat message / task /
    # *-agent-builder / cloud-sandbox / local-system) does NOT mint a product
    # journey. Scoped to domains whose tools are ALL ts-sourced, so the shipped
    # Python world (RefApp/onyx/tracecat) is byte-identical. Inert on langfuse
    # (datasets/evals/scores/… are none of these role words).
    _ts_domains = {
        d for d, ts in census.tools_by_domain().items()
        if ts and all(t.source == "ts" for t in ts)
    }
    for dom in sorted(domain_members):
        # role-gate first — a gated machinery/transport/infra domain never
        # moves flows (reported as detected-but-unminted with its role reason).
        if dom in _ts_domains:
            role = _domain_role(dom)
            if role != "capability":
                skipped_domains.append({
                    "domain": dom,
                    "reason": f"role-gated ({role}) — machinery/transport not a product capability",
                })
                continue
        # conservation: never take a flow that is the last member of its
        # source journey (would empty it — a whole-UF disappearance).
        def _last_member(f: "Flow") -> bool:
            uid = f.user_flow_id
            return bool(uid) and src_uf_count.get(uid or "", 0) <= 1 and uid in uf_by_id

        safe = [f for f in domain_members[dom] if not _last_member(f)]
        if not safe:
            skipped_domains.append({"domain": dom, "reason": "no conservation-safe member"})
            continue
        # it3 member floor (panel mandate): a mint with fewer than 2
        # entry-true members brakes — an honest no-mint beats a thin blob
        # row. The candidates stay where they were (no move happens).
        if len(safe) < _MINT_MEMBER_FLOOR:
            skipped_domains.append({
                "domain": dom,
                "reason": f"below member floor ({len(safe)}<{_MINT_MEMBER_FLOOR}) — honest no-mint",
            })
            continue
        dom_tools = [t.tool for t in census.tools_by_domain().get(dom, [])]
        forms = {t.form for t in census.tools_by_domain().get(dom, [])}
        form = forms.pop() if len(forms) == 1 else "mixed"
        name = f"{_humanize_domain(dom)} via agent"
        if name.strip().lower() in existing_names:
            name = f"{_humanize_domain(dom)} capabilities via agent"
        existing_names.add(name.strip().lower())
        uf = UserFlow(
            id=_new_uf_id(),
            name=name,
            resource=_humanize_domain(dom),
            domain=None,
            product_feature_id=dom,
            intent="execute",
            member_flow_ids=[],
            member_count=0,
            routes=[],
            refined=True,
            name_confidence="medium",
            binding_confidence="low",
            agent_surface=agent_surface_tag("mint", dom, dom_tools, form),
        )
        uf_by_id[uf.id] = uf
        for f in safe:
            old = getattr(f, "user_flow_id", None)
            if old:
                src_uf_count[old] = src_uf_count.get(old, 0) - 1
            _reassign(f, uf)
            moved_total += 1
        src_uf_count[uf.id] = len(safe)
        new_ufs.append(uf)
        mints.append({
            "domain": dom, "pf": dom, "name": name,
            "members": len(safe), "tools": len(dom_tools), "form": form,
        })
    user_flows.extend(new_ufs)

    # ── Seg B — tag / re-home the REMAINING (transport) agent-entry flows ──
    # Two cases: a transport flow that already has a journey -> TAG it entry;
    # an ORPHANED transport flow (chat-with-agent, assemble-prompt — no UF) is
    # re-homed into ONE transport journey (never deleted). Chat is transport
    # (B80 trpc precedent), so the transport journey homes in the conversation
    # PF when one exists, else stays pf=None (a lane-like residual).
    entry_tagged_ufs: set[str] = set()
    orphan_transport: list["Flow"] = []
    for f in entry_flows:
        if getattr(f, "uuid") in claimed:
            continue
        uid = getattr(f, "user_flow_id", None)
        owner_uf: "UserFlow | None" = uf_by_id.get(uid) if uid else None
        if owner_uf is not None and owner_uf.id not in entry_tagged_ufs \
                and not getattr(owner_uf, "agent_surface", None):
            owner_uf.agent_surface = agent_surface_tag("entry", None, [], "")
            entry_tagged_ufs.add(owner_uf.id)
            entry_tagged.append({"uf": owner_uf.id, "name": owner_uf.name,
                                 "entry": _entry_file(f)})
        elif owner_uf is None:
            orphan_transport.append(f)

    # unmatched ORPHANS whose NAME carries an agent-transport token
    # (run-agent-flow entering via api/v1/messages) join the transport
    # journey too — they are the agent machinery by their own name, just not
    # entry-rooted inside the agent dir.
    transport_uuids = {getattr(f, "uuid") for f in orphan_transport}
    for f in orphan_pool:
        if getattr(f, "uuid") in claimed or getattr(f, "uuid") in transport_uuids:
            continue
        raw = {t for t in re.split(r"[^a-z0-9]+", str(getattr(f, "name", "")).lower()) if t}
        if raw & _TRANSPORT_NAME_TOKENS:
            orphan_transport.append(f)
            transport_uuids.add(getattr(f, "uuid"))

    if orphan_transport:
        transport_pf = _match_pf(
            ("conversation", "conversations", "chat", "assistant", "agent"),
            pf_names,
        )
        name = "Agent conversation & tools"
        # A pf=None journey is illegal without a lane_ref (emission_integrity
        # B52 law), so only re-home the orphaned transport flows when a real
        # conversation/chat PF exists to home them in; otherwise leave them as
        # they were (no regression — they were already orphaned).
        if transport_pf and name.strip().lower() not in existing_names:
            existing_names.add(name.strip().lower())
            t_uf = UserFlow(
                id=_new_uf_id(),
                name=name,
                resource="Agent",
                domain=None,
                product_feature_id=transport_pf,
                intent="execute",
                member_flow_ids=[],
                member_count=0,
                routes=[],
                refined=True,
                name_confidence="medium",
                binding_confidence="low",
                lane_ref=None,
                agent_surface=agent_surface_tag("entry", None, [], ""),
            )
            uf_by_id[t_uf.id] = t_uf
            for f in orphan_transport:
                _reassign(f, t_uf)
                transport_rehomed += 1
            user_flows.append(t_uf)
            entry_tagged_ufs.add(t_uf.id)
            entry_tagged.append({
                "uf": t_uf.id, "name": name,
                "entry": "transport-rehome", "members": len(orphan_transport),
                "pf": transport_pf,
            })

    # ── conservation self-check (DELTA invariant) ──
    members_after_list = [m for u in user_flows for m in u.member_flow_ids]
    members_after_set = set(members_after_list)
    dupes_after = len(members_after_list) - len(members_after_set)
    dropped = sorted(members_before_set - members_after_set)
    # only NEW duplicates we introduced count against us (a board may already
    # carry pre-existing double-listings — not this stage's doing).
    introduced_dupes = max(0, dupes_after - dupes_before)
    # it3 partition complete-or-drop (panel fix №2): a domain counts as
    # COVERED only when the stage actually minted/moved for it. Detected-but-
    # unminted domains are reported separately — honest telemetry, never a
    # coverage claim. it4 №2: each unminted domain carries its EXPLICIT
    # reason — "below-floor(N<2)" (entry-true candidates existed but too few)
    # vs "0-candidates" (no entry-true flow matched at all) vs the
    # conservation guard.
    _minted_domains = sorted({str(m.get("domain")) for m in mints})
    _skip_reason = {s["domain"]: str(s["reason"]) for s in skipped_domains}
    tele["domains_minted"] = _minted_domains

    def _unminted_reason(d: str) -> str:
        if d in _skip_reason:
            r = _skip_reason[d]
            if "below member floor" in r:
                n = len(domain_members.get(d, []))
                return f"below-floor({n}<{_MINT_MEMBER_FLOOR})"
            return r  # conservation-guard reason, verbatim
        return "0-candidates"

    tele["domains_detected_unminted"] = [
        {"domain": d, "reason": _unminted_reason(d)}
        for d in census.domains() if d not in _minted_domains
    ]
    tele["conservation"] = {
        "members_before": len(members_before_set),
        "members_after": len(members_after_set),
        "dropped_members": dropped[:20],
        "dropped_count": len(dropped),
        "pre_existing_duplicates": dupes_before,
        "introduced_duplicates": introduced_dupes,
        "conserved": not dropped and introduced_dupes == 0,
        "moved_to_mints": moved_total,
        "moved_to_transport": transport_rehomed,
        "mints": len(new_ufs),
        "entry_tagged": len(entry_tagged_ufs),
    }

    # ── Phase-1 — registry-MOUNT attribution (armed-only: census.mount_consumers
    # is populated ONLY when WYSTAN_AGENT_MOUNT_ATTRIBUTION is ON, so this
    # whole block is inert / byte-identical when the flag is OFF) ──
    #
    # The consumer→tool edge is a dynamic dispatch never reachable via the flow
    # graph; here we SYNTHESISE it from the parsed mount-sites. A domain the
    # entry-true mint STARVED (``0-candidates`` / ``below-floor``) but which a
    # consumer demonstrably MOUNTS is re-classified as mount-attributed — the
    # tools of that domain are shared-member anatomy of the consumer journey,
    # not an absence. Pure display + telemetry (``agent_surface`` is read by no
    # downstream stage); no member moved, no UF minted, no invariant touched.
    if census.mount_consumers:
        dom_consumers: dict[str, list[str]] = {}
        for mc in census.mount_consumers:
            for d in mc.domains:
                dom_consumers.setdefault(d, []).append(mc.site)
        _unminted = cast("list[dict[str, str]]",
                         tele["domains_detected_unminted"])
        _still = [u for u in _unminted if u["domain"] not in dom_consumers]
        _attributed_rows = [
            {"domain": u["domain"], "prior_reason": u["reason"],
             "consumers": sorted(dom_consumers[u["domain"]])}
            for u in _unminted if u["domain"] in dom_consumers
        ]
        tele["domains_detected_unminted"] = _still
        tele["domains_mount_attributed"] = _attributed_rows

        # conservation — 0 tools lost: the mount enumerates DOMAINS (a consumer
        # mounts a domain's whole tool set), so a capability tool is attributed
        # iff its domain is mounted by >=1 consumer, else it is an honest orphan
        # (its domain — un-homed or unmounted — is reachable by no consumer).
        _attr_domains = set(dom_consumers)
        _cap = list(census.capability_tools)
        _mounted_cap = sorted(t.tool for t in _cap if t.domain in _attr_domains)
        _orphan_tools = sorted(
            t.tool for t in _cap if t.domain not in _attr_domains)
        _all_total = len(_cap)

        _consumer_rows = [
            {"consumer": mc.site, "kind": mc.kind, "domains": list(mc.domains),
             "tool_count": len(mc.tools), "excluded_domains": list(mc.excluded),
             "registries": list(mc.registries)}
            for mc in census.mount_consumers
        ]
        # attach the mounted anatomy to the CONSUMER (entry/transport) journeys —
        # "the agent mounts these domains/tools" as their shared-member surface.
        _attached: list[str] = []
        for u in user_flows:
            _as: dict[str, Any] | None = getattr(u, "agent_surface", None)
            if u.id in entry_tagged_ufs and _as:
                _tag = dict(_as)
                _tag["mounts"] = _consumer_rows
                u.agent_surface = _tag
                _attached.append(u.id)

        tele["mount_attribution"] = {
            "consumers": _consumer_rows,
            "consumer_count": len(_consumer_rows),
            "domains_attributed": sorted(dom_consumers),
            "domains_attributed_count": len(dom_consumers),
            "tools_total": _all_total,
            "tools_mounted": len(_mounted_cap),
            "orphan_tools": _orphan_tools,
            "orphan_tool_count": len(_orphan_tools),
            "tools_lost": _all_total - len(_mounted_cap) - len(_orphan_tools),
            "conserved": len(_mounted_cap) + len(_orphan_tools) == _all_total,
            "attached_to_ufs": sorted(_attached),
        }

    # ── Phase-2 — agent SYSTEM-PROMPT attribution (armed-only: census.system_
    # prompts is populated ONLY when WYSTAN_AGENT_SYSTEM_PROMPT is ON, so this
    # block is inert / byte-identical when the flag is OFF) ──
    if census.system_prompts:
        sp = census.system_prompts
        _by_class: dict[str, int] = {}
        for a in sp:
            _by_class[a.anchor_class] = _by_class.get(a.anchor_class, 0) + 1
        _sp_rows = [{
            "site": a.site, "class": a.anchor_class, "kwarg": a.kwarg,
            "source_kind": a.source_kind, "source_ref": a.source_ref,
            "consumer_site": a.consumer_site,
        } for a in sp]
        _consumed_consts = sorted({
            a.source_ref for a in sp if a.source_kind == "const"})
        _prompt_files = sorted({
            a.source_ref for a in sp if a.source_kind == "file"})
        # attach the detected prompts to the CONSUMER (entry/transport) journeys
        # — "the agent's system prompt is <ref>" as its anatomy (pure display).
        _attached_sp: list[str] = []
        for u in user_flows:
            _as2: dict[str, Any] | None = getattr(u, "agent_surface", None)
            if u.id in entry_tagged_ufs and _as2:
                _tag2 = dict(_as2)
                _tag2["system_prompts"] = _sp_rows
                u.agent_surface = _tag2
                _attached_sp.append(u.id)
        tele["system_prompt"] = {
            "count": len(sp),
            "by_class": _by_class,
            "call_sites": _by_class.get("call-site", 0),
            "prompt_files": _prompt_files,
            "consumed_consts": _consumed_consts,
            "anchors": _sp_rows,
            "attached_to_ufs": sorted(_attached_sp),
        }

    # ── Phase-3 — agent SKILL-layer attribution (armed-only: census.skill_layer
    # is populated ONLY when WYSTAN_AGENT_SKILLS is ON, so this block is inert
    # / byte-identical when the flag is OFF) ──
    #
    # The PRODUCT-agent skill layer (code-skills: capability + persona) attaches
    # to the consumer journey as its skill anatomy. DEV-TIME .claude skills are
    # reported for honest visibility but NEVER attached to a product consumer
    # (§6.3). Most repos have no skill layer at all — an honest zero, no
    # over-mint.
    if census.skill_layer:
        _sk_all = census.skill_layer
        _cap_sk = [a for a in _sk_all if a.role == "capability"]
        _persona_sk = [a for a in _sk_all if a.role == "persona"]
        _dev_sk = [a for a in _sk_all if a.role == "dev-time"]
        _skill_tool_links = {
            a.name: list(a.required_tools) for a in _cap_sk if a.required_tools}
        # the PRODUCT skill layer (code-skills only) is the consumer's anatomy;
        # dev-time .claude skills are excluded from the consumer attach.
        _product_rows = [{
            "name": a.name, "file": a.file, "role": a.role,
            "always_loaded": a.always_loaded,
            "required_tools": list(a.required_tools),
        } for a in _cap_sk + _persona_sk]
        _attached_sk: list[str] = []
        if _product_rows:
            for u in user_flows:
                _as3: dict[str, Any] | None = getattr(u, "agent_surface", None)
                if u.id in entry_tagged_ufs and _as3:
                    _tag3 = dict(_as3)
                    _tag3["skills"] = _product_rows
                    u.agent_surface = _tag3
                    _attached_sk.append(u.id)
        tele["skill_layer"] = {
            "capability_count": len(_cap_sk),
            "persona_count": len(_persona_sk),
            "dev_time_count": len(_dev_sk),
            "capability_skills": sorted(a.name for a in _cap_sk),
            "persona_skills": sorted(a.name for a in _persona_sk),
            "dev_time_skills": sorted(a.name for a in _dev_sk),
            "skill_tool_links": {k: _skill_tool_links[k]
                                 for k in sorted(_skill_tool_links)},
            "attached_to_ufs": sorted(_attached_sk),
        }

    # ── Phase-4 — IMPORT-BRIDGE + board-visible anatomy rows (armed-only:
    # census.consumer_importer_files is populated ONLY when
    # WYSTAN_AGENT_ANATOMY_ROWS is ON, so this block is inert / byte-identical
    # when the flag is OFF) ──
    #
    # The static endpoint→consumer import (which the dynamic-dispatch flow graph
    # misses) identifies the agent-consumer journeys; the mounted anatomy (tools
    # with per-tool LOC spans, skills, prompt) attaches to them as SHARED-member
    # anatomy — making attached_to_ufs non-empty on a real board.
    if census.consumer_importer_files:
        _importers = set(census.consumer_importer_files)
        _flow_by_uuid = {getattr(f, "uuid", ""): f for f in flows}

        def _uf_is_consumer(u: "UserFlow") -> list[str]:
            """import-bridge: a member flow ENTERS in a consumer-importer file
            (entered THROUGH an agent-invoking endpoint — not merely touching
            agent machinery as a deep path member)."""
            hit: set[str] = set()
            for mid in u.member_flow_ids:
                f = _flow_by_uuid.get(mid)
                ef = getattr(f, "entry_point_file", None) if f else None
                if ef and ef in _importers:
                    hit.add(ef)
            return sorted(hit)

        # anatomy payload — per-tool LOC spans (file:line) so a mounted-tool row
        # carries a REAL span, never a 0-LOC blob (canon: member-ful 0-LOC = bug).
        _tool_rows = [{
            "name": t.tool, "domain": t.domain,
            "file": t.handler_file, "line": t.handler_line,
        } for t in sorted(census.capability_tools, key=lambda t: t.tool)]
        _skill_rows = [{
            "name": a.name, "role": a.role,
            "required_tools": list(a.required_tools),
        } for a in census.skill_layer if a.role in ("capability", "persona")]
        _prompt_rows = [{
            "source_ref": a.source_ref, "source_kind": a.source_kind,
            "kwarg": a.kwarg,
        } for a in census.system_prompts]
        _loc_real = sum(1 for t in census.capability_tools
                        if t.handler_line and t.handler_line > 0)

        _anatomy = {
            "via": "agent", "tier": "shared-member",
            "tools": _tool_rows, "skills": _skill_rows,
            "system_prompts": _prompt_rows,
        }
        _bridged: list[dict] = []
        for u in user_flows:
            _hit = _uf_is_consumer(u)
            if not _hit:
                continue
            _pre = bool(getattr(u, "agent_surface", None))
            _tag4 = dict(getattr(u, "agent_surface", None) or {"via": "agent"})
            _tag4["anatomy"] = _anatomy
            u.agent_surface = _tag4
            _bridged.append({"uf": u.id, "name": u.name,
                             "import_bridge": _hit[:3], "pre_tagged": _pre})

        # 3-WAY (§3): shared-member (default — the attach above); standalone-UF
        # (the B81 ≥2-member agent mints already on the board); product-feature
        # (capability-IS-product — an LLM/curation boundary, DEFERRED honestly,
        # never forced deterministically).
        _standalone: list[str] = []
        for u in user_flows:
            _asx = getattr(u, "agent_surface", None)
            if isinstance(_asx, dict) and _asx.get("kind") == "mint":
                _standalone.append(u.id)
        _standalone = sorted(_standalone)
        # COLLISION-GUARD-vs-PF (§6.3 full): a product feature that is a
        # user-facing SURFACE (its own route/schema/nav anchor) sharing a name
        # with an anatomy domain is NOT absorbed — the attach only ever writes a
        # journey's display tag, never a PF, so the surfaces stay separate. Named
        # here for the honest audit.
        _anat_domains = {t.domain for t in census.capability_tools if t.domain}
        _pf_names_l = {
            str(getattr(p, "display_name", None) or getattr(p, "name", "")): p
            for p in product_features}
        _kept_separate = sorted({
            nm for nm in _pf_names_l
            if any(d and (d in nm.lower() or nm.lower() in d)
                   for d in _anat_domains)})

        tele["anatomy_rows"] = {
            "import_bridge_files": len(_importers),
            "consumer_journeys": len(_bridged),
            "attached_to_ufs": sorted(b["uf"] for b in _bridged),
            "bridged": _bridged,
            "anatomy_element_count": (len(_tool_rows) + len(_skill_rows)
                                      + len(_prompt_rows)),
            "loc_spans_real": _loc_real,
            "loc_spans_total": len(_tool_rows),
            "three_way": {
                "shared_member": len(_bridged),
                "standalone_uf": _standalone,
                "product_feature": {
                    "status": "deferred",
                    "reason": ("capability-is-product is an LLM/curation "
                               "boundary (demo test) — not forced "
                               "deterministically"),
                    "candidate_domains": sorted(_anat_domains),
                },
            },
            "product_surfaces_kept_separate": _kept_separate,
        }
    return tele
