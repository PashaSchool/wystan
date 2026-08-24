"""Product-Spine Wave 2a — product-surface taxonomy (spec §4.2, Stage 6.85).

Kills rootcause RC4 / evidence class C3: the engine had no product-surface
taxonomy, so any route container could become a product feature — 39
info-page PFs on the 10-scan board (26 in supabase alone: "Marketing Site
Pages" 1090 files, "Docs Site & API Reference", Blog, Brand Assets…), each
padded with exactly one journey. The one structural signal separating
marketing from product surfaces (Next route-groups) was stripped at Stage 1
(now carried — see ``extractors/route.route_groups_of``).

Two wiring points in ``phase_finalize``:

**Layer-1 tagging** (:func:`tag_layer1`) — right after Stage 6.8 lineage +
Stage 6.8b system-route classification: stamps ``surface_scope`` on every
``routes_index`` entry and every developer feature. Stage 6.7d consumes the
dev tags (tier-3 route-surface promotion skips non-product devs; the
container-page guard consumes the ``shell`` tag).

**Emission lane** (:func:`apply_emission_taxonomy`) — after Stage 6.97 LOC +
the flowless-shell resolution, before emission integrity:

  1. re-stamps dev tags (paths moved through strips/carves) and tags every
     user flow + product feature;
  2. **non-product lane** (spec §4.2 consequence a): product features whose
     evidence majority is marketing / docs / legal / dev_tooling / shell
     leave ``product_features[]`` into the additive
     ``non_product_surfaces[]`` output lane, taking their journeys with
     them — non-product surfaces never mint PFs in the product list
     (validator I20);
  3. **info-page dissolution** (consequence b): a marketing/legal-scope
     journey over single info PAGES (contact / about / imprint / faq /
     terms class) attached to a PRODUCT feature dissolves — its member
     flows become plain dev-flows of the hosting UF (same product feature,
     max entry-path overlap) — info pages are never their own UF/PF;
  4. **dev lane re-bind**: a shared-platform dev whose surface is
     non-product re-binds to the lane surface claiming its paths — info
     pages are never Shared Platform residents;
  5. **shared-resident reasons** (validator I22): every dev feature still
     bound to the shared bucket carries a machine-readable
     ``shared_reason`` (no_anchor_lineage | genuinely_shared_infra |
     facet_view | awaiting_wave2_mint | non_product_surface).

``surface_scope`` vocabulary (spec §4.2):
``product | marketing | docs | legal | system | dev_tooling | shell``.

Signals: route-groups (author's own surface declaration), workspace class
(apps/www, apps/docs), URL-segment lexicon, Stage 6.8b system triggers,
container identity. Patterns live in ``surface-scope-patterns.yaml``
(authoring copy ``eval/surface-scope-patterns.yaml``, drift-guarded) —
structural web conventions only, never a repo-specific path. ``system``
scope comes ONLY from Stage 6.8b verdicts (never lexicon-derived — /webhooks
and /cron segments appear in product settings pages; measured on the
recorded Lane-C claim table).

Ambiguous / no-signal → ``product`` (conservative: never hide a product
journey). Aggregation is strict-majority/argmax over path evidence —
scale-invariant, no tuned constants (rule-no-magic-tuning). Adapted from the
parked ``agent/scope-filter`` classifier (Lane C, 2026-07-05), extended to
route/dev/PF grain + legal/shell scopes + the wired consequences.

Deterministic, $0 LLM, no network. Kill-switches (default ON):
``WYSTAN_SURFACE_TAXONOMY=0`` disables tagging AND every consequence;
``WYSTAN_SURFACE_LANE=0`` keeps tags but disables the emission-lane
moves (2-4); ``WYSTAN_SHARED_REASONS=0`` disables the I22 stamping.

fixb140 — LANE-DELETION (operator ruling 2026-08-10, variant A)
---------------------------------------------------------------
The lane transfer (2) has always removed the journey row from
``user_flows[]`` and re-homed the FULL ``model_dump()`` into
``non_product_surfaces[].user_flows[]``. fixb119 M3 registered that move
as an ID-BOUND lineage channel and left the PRODUCT question open, naming
the affected rows one by one in ``scan_meta.journey_lineage_audit.
lane_moved``: should a laned journey keep living on the board as a
``scope=marketing`` row at all?

Measured world (KS61-KS74 boards, 13 rows: typebot 9 / kan 3 /
core-redplanet 1): EVERY laned row has ``member_absorbed == 0.00`` — not
one of its member flows survives anywhere in the journey layer. The row
that remains is therefore a SHELL: a journey name with a member list that
points at nothing the board still calls a journey.

Operator ruling — **remove it**. A member-less journey shell is the
hollow-rows disease (the same class B68/B23 spent cycles killing); the
permanent record of the row lives in this stage's ``lane_deleted`` /
``lane_deleted_ids`` channels — COMPLETE, never capped: id AND name for
every deleted row (lead ruling 2026-08-10) — plus
``scan_meta.journey_lineage_audit.lane_moved``, whose 20-row display
sample stays a sample. So NOTHING vanishes silently: the death stays
id-bound and the marketing CODE stays fully visible in its own board
section (the ``non_product_surfaces[]`` entry keeps its paths, member devs
and LOC; only the hollow journey row inside it goes).

Flag ``WYSTAN_LANE_MOVED_DELETE`` — default **ON** since flip-pack №41
(KEY_SCHEMA 74 -> 75, 2026-08-10); explicit ``0``/``false``/``off``/``no``
restores the keep-world and is a kill-switch forever. Only rows with
``member_absorbed == 0.00`` are deleted: a PARTIALLY absorbed row (some
member still alive in the journey layer) is a different, unmeasured shape
and is left standing — including the world's single ``== 1.00`` row
(better-auth ``UF-034``), spec-literal by lead ruling.

Measured blast at the flip: 31 of 55 cold boards carry laned journeys,
360 rows, 356 deleted / 4 held by the anti-case.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Any, Iterable, Mapping

from wystan.pipeline_v2.data import load_yaml
from wystan.pipeline_v2.journey_lineage_audit import report_journey_kill
from wystan.pipeline_v2.ws_anchor_identity import (
    cli_identity_for_anchor,
    ws_anchor_identity_enabled,
)

if TYPE_CHECKING:  # pragma: no cover — typing only
    from wystan.models.types import Feature, Flow, UserFlow

__all__ = [
    "SURFACE_TAXONOMY_ENV",
    "SURFACE_LANE_ENV",
    "SHARED_REASONS_ENV",
    "NONPRODUCT_SCOPE_ENV",
    "DOCS_REANCHOR_ENV",
    "SURFACE_SCOPE_RECALL_ENV",
    "LANE_MOVED_DELETE_ENV",
    "PUBLISHED_ARTIFACT_VETO_ENV",
    "SHELL_NAME_CORROBORATION_ENV",
    "ADJUDICATOR_DEP_GUARD_ENV",
    "RELEASED_DISPLAY_REGISTRY_ENV",
    "ABSTAIN_SCOPE_ROLLBACK_ENV",
    "published_artifact_veto_enabled",
    "shell_name_corroboration_enabled",
    "adjudicator_dep_guard_enabled",
    "released_display_registry_enabled",
    "abstain_scope_rollback_enabled",
    "note_earned_display",
    "earned_displays",
    "reset_earned_displays",
    "is_container_only_display",
    "LANE_DELETE_WRITER",
    "SURFACE_SCOPES",
    "SCOPE_PRODUCT",
    "NON_PRODUCT_PF_SCOPES",
    "taxonomy_enabled",
    "lane_enabled",
    "shared_reasons_enabled",
    "nonproduct_scope_enabled",
    "docs_reanchor_enabled",
    "surface_scope_recall_enabled",
    "lane_moved_delete_enabled",
    "SurfaceScopeClassifier",
    "load_patterns",
    "is_non_product_dev",
    "tag_layer1",
    "apply_emission_taxonomy",
]

SURFACE_TAXONOMY_ENV = "WYSTAN_SURFACE_TAXONOMY"
SURFACE_LANE_ENV = "WYSTAN_SURFACE_LANE"
SHARED_REASONS_ENV = "WYSTAN_SHARED_REASONS"
#: B28 (Shape E) — dev-artifact workspace detection: P-B registry-publisher
#: manifests + P-D hub-fixture marks (Stage 6.86 telemetry) join the
#: emission classifier's instrument-dirs channel behind the R1
#: (journey-isolation strict-minority) + R2 (dominant-app) rails; the S1g
#: types-only prong in ``technology_instruments`` keys on the same flag.
#: Default ON; ``WYSTAN_NONPRODUCT_SCOPE=0`` restores this slice
#: byte-identically.
NONPRODUCT_SCOPE_ENV = "WYSTAN_NONPRODUCT_SCOPE"
#: B28 (Shape D) — a PRODUCT-scoped PF anchored inside a non-product app
#: (supabase ``auth`` @ ``route:apps/docs/app/guides/auth`` whose body is
#: 107/107 ``apps/studio/**``) re-anchors in place to its
#: evidence-majority product surface (majority-dir election, route-lineage
#: preferred). Journeys/uuid/paths untouched — conservation trivial.
#: Default ON; ``WYSTAN_DOCS_REANCHOR=0`` restores this slice
#: byte-identically.
DOCS_REANCHOR_ENV = "WYSTAN_DOCS_REANCHOR"
#: B58 (2026-07-29) — surface-scope RECALL widenings, three additive
#: husk-recall corrections that reuse EXISTING lexicon/data (no new
#: vocabulary): (1) product-name-PREFIXED workspace suffix vs the
#: ``root_dirs`` conservative subset (twenty-docs -> docs); (2) the
#: ``.storybook/`` design-system structural signal gated by a zero-routes
#: guard (plane packages/propel); (3) ``dev_artifact_tokens`` wired to the
#: GENERAL classifier at EXACT workspace/root-dir grain (cal.com
#: apps/templates, supabase examples/). Default ON since flip-pack №12
#: (KEY_SCHEMA 47, 2026-07-29; keyed proof plane 5/5 green, twenty
#: offline suffix-arm): unset ≡ explicit ON; explicit
#: ``WYSTAN_SURFACE_SCOPE_RECALL=0``/false/off/no stays a
#: kill-switch forever (restores the pre-flip world byte-identically up
#: to the ``scan_meta.key_schema`` stamp).
SURFACE_SCOPE_RECALL_ENV = "WYSTAN_SURFACE_SCOPE_RECALL"
#: fixb140 (2026-08-10) — lane-deletion, operator ruling variant A. A
#: journey the lane transfer moved out of ``user_flows[]`` whose member
#: flows left the journey layer ENTIRELY (``member_absorbed == 0.00``) is
#: DELETED instead of being kept as a ``scope=marketing`` shell inside
#: ``non_product_surfaces[].user_flows[]``. Default **OFF** (the flip is a
#: separate decision); explicit ``0``/``false``/``off``/``no`` is a
#: kill-switch forever. See the module docstring for the ruling and the
#: 13-row world census.
LANE_MOVED_DELETE_ENV = "WYSTAN_LANE_MOVED_DELETE"
#: fixb143 (i-a, 2026-08-11) — PUBLISHED-PRODUCT-ARTIFACT veto. Generalises
#: the ``_is_published_cli`` doctrine (operator ruling 2026-07-06, midday
#: review) from a lexicon-rung override into a TOP-PRECEDENCE product vote.
#:
#: The census that motivated it (fixb143 PHASE-1, 294 lane rows / 32 boards):
#: ``_is_published_cli("packages/cli-v3")`` reads **True** on trigger.dev
#: (package name ``trigger.dev``, ``bin`` + ``publishConfig``, not private)
#: while ``classify_path`` returns **None** — the override is unreachable,
#: because it is only consulted at the workspace rung when the LEXICON has
#: already voted ``dev_tooling``, and ``cli-v3`` is not the lexicon token
#: ``cli``. The demotion then arrived from a DIFFERENT channel (B28
#: dev_artifact -> instrument dirs) which never consults the override at
#: all, and the fixb140 lane-deletion removed 8 real CLI journeys ('Deploy
#: tasks via CLI', 'Develop and test tasks locally', ...).
#:
#: PREDICATE (pinned on measured manifests, not vocabulary):
#:   non-empty ``bin`` OR non-empty ``publishConfig``
#:   AND ``private is not True``
#:   AND NOT :meth:`_has_storybook` — the DESIGN-SYSTEM separator.
#: The storybook clause is load-bearing and was pinned by counter-example:
#: ``@teable/ui-lib`` is published (``publishConfig``) AND a Storybook
#: design system; without the clause the veto would un-lane it, violating
#: the operator ruling that component libraries are NOT product features.
#: ``@midday/ui`` and ``@plane/propel`` need no clause at all — both are
#: ``private: true`` — so the design-system anti-cases hold on two
#: independent grounds.
#:
#: Routes-unknown ⇒ the storybook separator cannot be verified ⇒ the veto is
#: SUPPRESSED (same fail-safe direction as :meth:`_has_storybook`). No
#: ``repo_path`` ⇒ no filesystem reads ⇒ inert (keyless / kill-switch
#: byte-identical). Default **ON** since flip-pack №45 (KEY_SCHEMA 80,
#: 2026-08-13; keyed proof trigger.dev round-5 — the round-3 destination
#: precondition ABSTAINS on that board, so ON ≡ OFF byte-identically in
#: every row: 515-dev census, PF 91≡91, UF 149≡149); explicit
#: ``0``/``false``/``off``/``no`` is a kill-switch forever.
PUBLISHED_ARTIFACT_VETO_ENV = "WYSTAN_PUBLISHED_ARTIFACT_VETO"
#: fixb143 (i-c, 2026-08-11) — SHELL-NAME CORROBORATION. The container-name
#: short-circuit in :meth:`classify_feature_with_signals` returns ``shell``
#: from the NAME alone, before a single path is examined. Census exhibits:
#: strapi ``home-page`` (60 paths in ``packages/core``, a workspace owning
#: 334 routes) and outline ``home`` (72 paths) were demoted on the string
#: ``home``, and the lane-deletion then removed 'View and manage home page
#: widgets' (the shipped Strapi admin Home-widgets feature) and 'View
#: pinned and recent documents on home'.
#:
#: PREDICATE: the short-circuit stands only when the row's own path vote
#: contributes ZERO ``product`` weight. This is not a new rule — it is the
#: existing "a real product route blocks a non-product verdict" law
#: (:meth:`member_vote` at journey grain, ``_owns_product_route`` at the
#: adjudicator seam) applied at feature grain. No threshold, no magic
#: number: a single product-voting path is enough, exactly as elsewhere.
#:
#: Measured on the 7 world shell-name lanes: 3 move (strapi ``home-page``
#: product_w=5, outline ``home`` product_w=1, inbox-zero ``home``
#: product_w=1), 4 hold — including the named ANTI-CASE fastapi ``main``
#: (``docs_src/app_testing``, product_w=0). Default **ON** since flip-pack
#: №45 (KEY_SCHEMA 80, 2026-08-13; keyed proof outline ×2 ON draws — the
#: released PF is emitted as 'Home Popular', warden №47's signature lifted
#: row-level, strapi ABSTAIN valid); explicit ``0``/``false``/``off``/``no``
#: is a kill-switch forever.
SHELL_NAME_CORROBORATION_ENV = "WYSTAN_SHELL_NAME_CORROBORATION"
#: fixb143 (i-d, 2026-08-11) — SURFACE-ADJUDICATOR DEPENDENCY GUARD +
#: payload denominator. The W3 §4.7 adjudicator already refuses to flip a
#: journey-rich PF and a PF owning a real product route. The census found
#: the missing third guard: supabase ``pg-meta`` (``@supabase/pg-meta``,
#: 10795 LOC, 60 member devs, 103 paths) had a deterministic verdict of
#: ``product`` — ``{"docs": 2}`` of 103 paths is nowhere near the strict
#: majority — and was flipped to ``docs`` by the Haiku persona, taking the
#: PF off the board and deleting 'Manage queues and queue messages'. The
#: model saw ``signals {"docs": 2}`` WITHOUT a denominator and 5 of 103
#: paths.
#:
#: TWO additive corrections, one flag:
#:  1. GUARD — a PF whose paths are DOMINATED (strict majority, abstains
#:     included — this module's own vote form) by workspaces whose package
#:     name is DECLARED AS A DEPENDENCY by another workspace's manifest
#:     carries product-declared evidence the path lexicon cannot see (the
#:     same "evidence the lexicon undercounts" logic as the W5.1 route
#:     guard). Such PFs are never sent. Manifest-only (no source scanning,
#:     no import graph): one ``package.json`` read per workspace. The
#:     MAJORITY form was pinned by the after-census refuting the any-hit
#:     form — see ``_is_dependency_package``.
#:  2. DENOMINATOR — the item payload gains ``total_paths`` so the ratio
#:     the deterministic vote used is visible to the model.
#:
#: Measured on the 32 world flips: blocks exactly 2 (supabase ``pg-meta``,
#: teable ``formula`` — ``@teable/core`` has 5 manifest dependents incl.
#: ``apps/nestjs-backend`` and ``apps/nextjs-app``). ANTI-CASE: the 30
#: defensible flips still fire — an app workspace is a LEAF in the manifest
#: graph (``@openstatus/web`` has 0 dependents), so openstatus/kan/
#: inbox-zero pricing·terms·privacy·status are untouched. Default **OFF**;
#: explicit ``0``/``false``/``off``/``no`` is a kill-switch forever.
ADJUDICATOR_DEP_GUARD_ENV = "WYSTAN_ADJUDICATOR_DEP_GUARD"
#: fixb143 round-5 (ii-a, 2026-08-13) — EARNED-DISPLAY REGISTRY. Warden №47
#: RESURRECTION. Every hop verified on the redo-ON board
#: (``outline-143r4redoon.json``): the (i-c) rider qualified outline ``home``
#: to ``Home Popular`` (``shell_release_qualified``), the row was emitted
#: displaying ``Home``, and ``Home Popular`` appears in the whole document
#: EXACTLY once — in that telemetry key. The overwriter is
#: ``naming_contract`` Pass 3 (``pm_labeler``, the declared single display
#: writer): it re-validates a persona pick through ``display_law_violations``
#: ONLY, and ``display_law_violations('Home')`` is ``[]`` — I11 (a container
#: page can never be a feature, a BANKED operator invariant) is not a display
#: LAW, so nothing in that seam knows the row had earned its name. The second
#: ON run of the SAME commit drew ``applied=0`` and kept ``Home Popular``:
#: the defect is non-deterministic across labeler draws.
#:
#: MECHANISM (fixb136 precedent — «a promise crossing a filter is not a
#: channel»): the release records ``pf -> earned display`` in a SCAN-SCOPED
#: registry both modules import, and the labeler may overwrite a registered
#: row ONLY with a candidate that is itself non-container under the same
#: container vocabulary + round-4 de-compounder that earned the name. A
#: container-only pick is refused and the earned display stands — under ANY
#: draw. Default **ON** since flip-pack №45 (KEY_SCHEMA 80, 2026-08-13;
#: keyed proof outline, BOTH ON draws: ``labeler_earned_display_held=1``
#: and the registry blocks EXACTLY that record — the same candidate ledger
#: goes applied 1→0 — while the other 13 PFs stay byte-identical to OFF);
#: explicit ``0``/``false``/``off``/``no`` is a kill-switch forever.
RELEASED_DISPLAY_REGISTRY_ENV = "WYSTAN_RELEASED_DISPLAY_REGISTRY"
#: fixb143 round-5 (ii-b, 2026-08-13) — ABSTAIN SCOPE ROLLBACK. Warden №47
#: new-suspect, consumer-visible on three live ON boards. Step 1a stamps
#: EVERY developer row with the ARMED classifier, before the PF loop has
#: decided whether the same flag's release commits; both round-3 riders can
#: abstain, and both abstains restored only the PARENT row:
#:   * ``trigger.dev-143r3on``: 13 dev rows under ``ws:packages/cli-v3``
#:     (cli, commands, deploy, entry-points, executions, indexing, mcp,
#:     rules, runtimes, shims, utilities, trigger-dev-imports,
#:     trigger.dev-imports; all ``pfid='trigger.dev'``) read ``product``
#:     while the PF and its lane row read ``dev_tooling`` —
#:     ``dev_scopes.dev_tooling`` 13 → 0 against a ``veto_destination_
#:     abstained`` verdict of ``restored_scope: dev_tooling``.
#:   * ``strapi-143r4on``: dev ``home`` (``pfid='home-page'``) shell →
#:     product under a ``home-page`` lane row that ABSTAINED.
#:   * ``inbox-zero-143r4redoon``: dev ``landing`` shell → product on a
#:     container name that NO PF-grain qualification ever vouched for (its
#:     home PF ``components`` never entered the release path).
#:
#: THE LAW: a dev-grain scope release by a flag that can abstain is a
#: CONSEQUENCE of its home PF's release, never an independent decision. It
#: stands only when that release COMMITTED on the FINAL (post-adjudicator)
#: scope; otherwise the row returns to its own flag-OFF hand — never-worse
#: by construction, the same shape as the (i-a) abstain. Default **ON**
#: since flip-pack №45 (KEY_SCHEMA 80, 2026-08-13; corpus proof: 15
#: rollback records, each verified ≡ its own OFF hand BY CENSUS — not by
#: telemetry — with rung 2 firing on exactly one record and the outline
#: anti-case clean); explicit ``0``/``false``/``off``/``no`` is a
#: kill-switch forever.
ABSTAIN_SCOPE_ROLLBACK_ENV = "WYSTAN_ABSTAIN_SCOPE_ROLLBACK"

#: fixb121 M6 writer label — ``<module>.<function>`` of the site that makes
#: the lineage record vanish (the ``emission_integrity._drop_anchored_husks``
#: precedent: the label points at the exact code, not at the stage entry).
LANE_DELETE_WRITER = "surface_taxonomy._delete_hollow_lane_rows"

_PATTERNS_FILE = "surface-scope-patterns.yaml"

SCOPE_PRODUCT = "product"
SCOPE_SYSTEM = "system"
SCOPE_SHELL = "shell"

#: Fixed precedence among competing NON-product scopes (most specific /
#: least ambiguous first — documented in the pattern file header).
_NON_PRODUCT_PRECEDENCE = (
    "system", "dev_tooling", "legal", "docs", "marketing", "shell",
)

SURFACE_SCOPES = (SCOPE_PRODUCT,) + _NON_PRODUCT_PRECEDENCE

#: PF scopes that leave the product list for the non-product lane —
#: mirrors the validator's I20 bad-scope set. ``system`` deliberately
#: STAYS in the product list (background-job capabilities are product
#: infrastructure with legitimate journeys; I20 allows it).
NON_PRODUCT_PF_SCOPES = frozenset(
    ("marketing", "docs", "legal", "dev_tooling", "shell"),
)

#: Dev scopes that block the 6.7d tier mints / capability joins and that
#: re-bind from the shared bucket to the lane (shell is handled by the
#: container-page guard instead).
_NON_PRODUCT_DEV_SCOPES = frozenset(("marketing", "docs", "legal", "dev_tooling"))

_SHARED_PF_KEYS = frozenset(("shared-platform", "platform"))

# Path segments that mark the start of URL context in a route file path —
# framework routing roots (Next app/, Next+Astro+Nuxt pages/, Remix/SvelteKit
# routes/). Only segments AFTER the last such marker are matched against the
# url_segments lexicon, so arbitrary source dirs (src/features/blog-model/…)
# never match. (Parked Lane-C rule, kept verbatim.)
_URL_ROOT_MARKERS = frozenset({"app", "pages", "routes"})

# Monorepo workspace container dirs — ``<container>/<name>`` where <name> is
# checked against the workspace_dirs lexicon.
_WORKSPACE_CONTAINERS = frozenset(
    {"apps", "packages", "sites", "websites", "tools"},
)

# Route-file basenames that carry no lexical signal of their own.
_NEUTRAL_STEMS = frozenset(
    {"page", "route", "index", "layout", "_index", "default"},
)

_DYNAMIC_SEG_RE = re.compile(r"^\[.*\]$|^:.+$|^<.+>$|^\{.+\}$|^\*|^\$")

_TRIGGER_INTERACTIVE = "interactive"


def _flag(env: str) -> bool:
    return os.environ.get(env, "1").strip().lower() not in {"0", "false"}


def taxonomy_enabled() -> bool:
    """Master switch — default ON, ``WYSTAN_SURFACE_TAXONOMY=0`` off."""
    return _flag(SURFACE_TAXONOMY_ENV)


def lane_enabled() -> bool:
    """Emission-lane consequences — default ON, ``WYSTAN_SURFACE_LANE=0``
    keeps the tags but moves nothing."""
    return _flag(SURFACE_LANE_ENV)


def shared_reasons_enabled() -> bool:
    """I22 stamping — default ON, ``WYSTAN_SHARED_REASONS=0`` off."""
    return _flag(SHARED_REASONS_ENV)


def nonproduct_scope_enabled() -> bool:
    """B28 Shape E — default ON, ``WYSTAN_NONPRODUCT_SCOPE=0`` off."""
    return _flag(NONPRODUCT_SCOPE_ENV)


def docs_reanchor_enabled() -> bool:
    """B28 Shape D — default ON, ``WYSTAN_DOCS_REANCHOR=0`` off."""
    return _flag(DOCS_REANCHOR_ENV)


def surface_scope_recall_enabled() -> bool:
    """B58 recall widenings — default ON since flip-pack №12 (KEY_SCHEMA
    47, 2026-07-29): unset ≡ explicit ON byte-identically. Explicit
    ``0``/``false``/``off``/``no`` (any non-truthy value) stays a
    kill-switch forever. The truthy set is preserved LITERALLY across
    the flip; only the get-default moved ``"0"`` → ``"1"``."""
    return os.environ.get(SURFACE_SCOPE_RECALL_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def lane_moved_delete_enabled() -> bool:
    """fixb140 lane-deletion — default **ON** since flip-pack №41
    (KEY_SCHEMA 74 -> 75, 2026-08-10): unset ≡ explicit ``1``
    byte-identically. Explicit ``0``/``false``/``off``/``no`` restores the
    pre-flip keep-behavior (the laned row lives on inside
    ``non_product_surfaces[].user_flows[]``) and stays a kill-switch
    forever. The truthy set is preserved LITERALLY across the flip; only
    the get-default moved ``"0"`` → ``"1"``."""
    return os.environ.get(LANE_MOVED_DELETE_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def published_artifact_veto_enabled() -> bool:
    """fixb143 (i-a) published-product-artifact veto — default **ON** since
    flip-pack №45 (KEY_SCHEMA 79 -> 80, 2026-08-13): unset ≡ explicit ``1``
    byte-identically. Explicit ``0``/``false``/``off``/``no`` restores the
    pre-flip lane (a published, non-private, non-Storybook workspace keeps
    losing to the instrument / B28 dev_artifact rungs) and stays a
    kill-switch forever. The truthy set is preserved LITERALLY across the
    flip — only the get-default moved ``"0"`` → ``"1"``.

    Keyed proof (trigger.dev, round-5 pair): the round-3 destination
    precondition ABSTAINS on that board, so the armed hand is byte-identical
    to the OFF hand in every row (515-dev census, PF 91≡91, UF 149≡149) —
    never-worse by construction, and exhibit №45 (nps, 24121 LOC) does not
    resurrect."""
    return os.environ.get(
        PUBLISHED_ARTIFACT_VETO_ENV, "1",
    ).strip().lower() in {"1", "true", "yes", "on"}


def shell_name_corroboration_enabled() -> bool:
    """fixb143 (i-c) shell-name corroboration — default **ON** since
    flip-pack №45 (KEY_SCHEMA 80, 2026-08-13): unset ≡ explicit ``1``
    byte-identically. Explicit ``0``/``false``/``off``/``no`` restores the
    pre-flip short-circuit (a container NAME demotes the row to ``shell``
    before a single path is read) and stays a kill-switch forever. The
    truthy set is preserved LITERALLY across the flip — only the
    get-default moved ``"0"`` → ``"1"``.

    Keyed proof (outline, TWO ON draws): the released PF is emitted as
    'Home Popular' — the earned name survives BOTH draws, which is what
    warden №47's RESURRECTION signature demanded row-level; strapi's
    ABSTAIN is valid (round-5 census == round-4 OFF hand)."""
    return os.environ.get(
        SHELL_NAME_CORROBORATION_ENV, "1",
    ).strip().lower() in {"1", "true", "yes", "on"}


def adjudicator_dep_guard_enabled() -> bool:
    """fixb143 (i-d) adjudicator dependency guard + payload denominator —
    default **OFF**."""
    return os.environ.get(
        ADJUDICATOR_DEP_GUARD_ENV, "0",
    ).strip().lower() in {"1", "true", "yes", "on"}


def released_display_registry_enabled() -> bool:
    """fixb143 round-5 (ii-a) earned-display registry — default **ON** since
    flip-pack №45 (KEY_SCHEMA 80, 2026-08-13): unset ≡ explicit ``1``
    byte-identically. Explicit ``0``/``false``/``off``/``no`` restores the
    pre-flip world (the labeler may overwrite an earned display with a bare
    container word, non-deterministically per draw) and stays a kill-switch
    forever. The truthy set is preserved LITERALLY across the flip — only
    the get-default moved ``"0"`` → ``"1"``.

    Keyed proof (outline, BOTH ON draws): ``labeler_earned_display_held=1``
    and the registry blocks EXACTLY that record — the same candidate ledger
    goes ``applied`` 1→0 — while the other 13 PFs stay byte-identical to the
    OFF hand. Warden №48: CLEAR."""
    return os.environ.get(
        RELEASED_DISPLAY_REGISTRY_ENV, "1",
    ).strip().lower() in {"1", "true", "yes", "on"}


def abstain_scope_rollback_enabled() -> bool:
    """fixb143 round-5 (ii-b) abstain scope rollback — default **ON** since
    flip-pack №45 (KEY_SCHEMA 80, 2026-08-13): unset ≡ explicit ``1``
    byte-identically. Explicit ``0``/``false``/``off``/``no`` restores the
    pre-flip world (a dev row keeps a scope its home PF's release never
    committed) and stays a kill-switch forever. The truthy set is preserved
    LITERALLY across the flip — only the get-default moved ``"0"`` → ``"1"``.

    Corpus proof: 15 rollback records, each verified ≡ its own OFF hand BY
    CENSUS (not by telemetry); rung 2 fires on exactly one record and the
    outline anti-case — a container-named dev row a PF-grain qualification
    DID vouch for — keeps its release. Warden №48: CLEAR-WITH-DEBT (the
    invariant hook does not cover rung 2)."""
    return os.environ.get(
        ABSTAIN_SCOPE_ROLLBACK_ENV, "1",
    ).strip().lower() in {"1", "true", "yes", "on"}


def load_patterns() -> dict[str, Any]:
    """Load the runtime pattern file (``{}`` if absent → classifier no-ops)."""
    try:
        return load_yaml(_PATTERNS_FILE) or {}
    except FileNotFoundError:  # pragma: no cover — packaging bug surface
        return {}


def _invert(block: Mapping[str, Any] | None) -> dict[str, str]:
    """``{scope: [token, …]}`` → ``{token: scope}`` (first scope in
    precedence order wins a duplicate token; ``product`` first)."""
    out: dict[str, str] = {}
    if not block:
        return out
    for scope in (SCOPE_PRODUCT,) + _NON_PRODUCT_PRECEDENCE:
        for tok in block.get(scope) or []:
            out.setdefault(str(tok).lower(), scope)
    return out


def _norm(path: str) -> str:
    return str(path).replace("\\", "/").strip().strip("/")


def _get(obj: Any, name: str, default: Any = None) -> Any:
    """Field access that works for pydantic models AND plain dicts."""
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _has_story_file(root: Any) -> bool:
    """Bounded walk (prunes node_modules/.git/dist/build/…, early-exit on
    the first hit) for a Storybook story file under *root* — the B58
    item-2 corroboration that a ``.storybook/`` config is a live design
    system, not a stray empty config."""
    import os as _os

    _skip = {"node_modules", ".git", "dist", "build", ".next", "coverage",
             ".turbo", "out"}
    for dirpath, dirnames, filenames in _os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _skip]
        for fn in filenames:
            low = fn.lower()
            if ".stories." in low or ".story." in low:
                return True
    return False


class SurfaceScopeClassifier:
    """Deterministic scope classifier over path / route / name evidence.
    Importable standalone (offline re-scoring reads recorded scan
    artifacts directly); the engine wiring lives in :func:`tag_layer1` /
    :func:`apply_emission_taxonomy`.

    ``repo_path`` (optional) enables the ONE filesystem signal: the
    published-CLI override. A ``cli``/``mcp``-named workspace can be a
    PRODUCT shipped CLI (midday's ``packages/cli`` is a published npm
    package with a ``bin`` customers install — its 'Authenticate via CLI'
    journeys are real product journeys), so a dev_tooling workspace-dir
    vote is overridden to PRODUCT when the workspace's ``package.json``
    declares a ``bin`` AND is not ``private: true`` (operator/coordinator
    doctrine, 2026-07-06). No repo_path → no reads → the lexicon verdict
    stands unchanged."""

    def __init__(self, patterns: dict | None = None,
                 repo_path: Any = None,
                 routes_index: Iterable[Mapping[str, Any]] | None = None,
                 instrument_dirs: Iterable[str] | None = None,
                 ) -> None:
        cfg = patterns if patterns is not None else load_patterns()
        self._groups = _invert(cfg.get("route_groups"))
        self._url = _invert(cfg.get("url_segments"))
        self._workspace = _invert(cfg.get("workspace_dirs"))
        self._root_dirs = _invert(cfg.get("root_dirs"))
        self._repo_path = repo_path
        self._published_cache: dict[str, bool] = {}
        # fixb143 (i-a) — read once per workspace; the veto is consulted on
        # every path of every feature, so the manifest read must be cached
        # exactly like ``_published_cache``/``_storybook_cache``.
        self._published_artifact_cache: dict[str, bool] = {}
        self._veto = published_artifact_veto_enabled()
        # W4.2 Fix 1 — mechanism-detected technology-instrument dirs
        # (Stage 6.86 telemetry). A path inside one is a dev_tooling
        # surface signal; product-declared signals still win precedence.
        self._instrument_dirs: tuple[str, ...] = tuple(sorted(
            _norm(str(d)).lower() for d in (instrument_dirs or []) if d
        ))
        self._shell_slugs = frozenset(
            str(s).lower() for s in (cfg.get("shell_slugs") or [])
        )
        self._info_segments = frozenset(
            str(s).lower() for s in (cfg.get("info_page_segments") or [])
        ) | frozenset(
            str(s).lower()
            for s in ((cfg.get("url_segments") or {}).get("legal") or [])
        )
        # ── B58 surface-scope recall (WYSTAN_SURFACE_SCOPE_RECALL,
        # default OFF) — three additive husk-recall widenings, all gated
        # by ``self._recall`` so an OFF/unset scan is byte-identical to
        # main. All three REUSE existing lexicon/data (no new vocabulary):
        #   (1) suffix — a hyphenated workspace segment whose component
        #       equals a ``root_dirs`` (conservative unambiguous-surface)
        #       token inherits its scope: twenty-docs -> docs,
        #       twenty-website -> marketing. root_dirs already EXCLUDES
        #       blog/brand, and cli/mcp are absent from it, so no
        #       product-domain word or published CLI is ever demoted.
        #   (2) ``.storybook/`` design-system signal (see _has_storybook):
        #       zero-routes-guarded so a routed app that merely uses
        #       Storybook (twenty-front, 392 routes) stays product.
        #   (3) ``dev_artifact_tokens`` at EXACT workspace/root grain only
        #       (never a contained token) so 'resume-templates' product
        #       surfaces are never touched.
        # MUST be set before ``_workspace_route_overrides`` below — that
        # pass calls ``classify_path``, which reads ``self._recall``.
        self._recall = surface_scope_recall_enabled()
        self._dev_artifact: frozenset[str] = (
            frozenset(
                str(t).lower() for t in (cfg.get("dev_artifact_tokens") or [])
            )
            if self._recall else frozenset()
        )
        self._routes_known = routes_index is not None
        self._routed_workspaces: frozenset[str] = frozenset()
        if self._recall and routes_index is not None:
            rw: set[str] = set()
            for entry in routes_index:
                f = _norm(str(entry.get("file") or "")).lower()
                segs = [s for s in f.split("/") if s]
                if len(segs) >= 2 and segs[0] in _WORKSPACE_CONTAINERS:
                    rw.add("/".join(segs[:2]))
            self._routed_workspaces = frozenset(rw)
        self._storybook_cache: dict[str, bool] = {}
        # W2b.1 fix (c1) — the STRUCTURAL workspace-class signal: a
        # workspace whose routes are ALL public marketing/info pages IS
        # a marketing surface even when its dir name sits outside the
        # lexicon (typebot apps/landing-page under TanStack: no route
        # groups, so per-file lexicon signals drown in abstentions at
        # feature grain). Built once from the routes_index; empty when
        # the caller has no routes.
        self._ws_scope_overrides: dict[str, str] = {}
        if routes_index is not None:
            self._ws_scope_overrides = self._workspace_route_overrides(
                routes_index)

    def _workspace_route_overrides(
        self, routes_index: Iterable[Mapping[str, Any]],
    ) -> dict[str, str]:
        """``{workspace prefix: scope}`` for workspaces that are WHOLLY a
        public marketing surface, decided structurally from their route
        profile (W2b.1 fix c1):

          * every route is a PAGE (any API-method route disqualifies —
            openstatus apps/web keeps its api/webhook product surface);
          * every route is interactive (no system triggers);
          * ZERO product-declared signals (an authored ``(dashboard)``
            route-group vote wins);
          * ≥ 1 marketing/legal lexicon signal, and marketing + legal +
            info-page signals form a STRICT MAJORITY of the workspace's
            routes (abstains count in the denominator — the same
            conservative ratio rule as feature-grain voting).

        Workspaces the lexicon already classifies (apps/www, apps/docs)
        are skipped — the vocabulary stays authoritative.
        """
        by_ws: dict[str, list[Mapping[str, Any]]] = {}
        for entry in routes_index or []:
            f = _norm(str(entry.get("file") or "")).lower()
            segs = [s for s in f.split("/") if s]
            if len(segs) >= 3 and segs[0] in _WORKSPACE_CONTAINERS:
                by_ws.setdefault("/".join(segs[:2]), []).append(entry)
        out: dict[str, str] = {}
        for ws, entries in sorted(by_ws.items()):
            ws_name = ws.split("/")[1]
            if self._workspace.get(ws_name):
                continue  # lexicon-classified workspace — vocab wins
            if any(str(e.get("method") or "").upper() != "PAGE"
                   for e in entries):
                continue
            if any(str(e.get("trigger") or _TRIGGER_INTERACTIVE)
                   != _TRIGGER_INTERACTIVE for e in entries):
                continue
            n = len(entries)
            mk_legal = 0
            product = 0
            for e in entries:
                pattern = str(e.get("pattern") or "")
                file = str(e.get("file") or "")
                hits: set[str] = set()
                sc_p = self.classify_route_pattern(pattern)
                if sc_p:
                    hits.add(sc_p)
                sc_f = self.classify_path(file)
                if sc_f:
                    hits.add(sc_f)
                if SCOPE_PRODUCT in hits:
                    product += 1
                    continue
                info = self.is_info_page_path(file) or any(
                    s in self._info_segments
                    for s in pattern.lower().split("/")
                )
                if "marketing" in hits or "legal" in hits or info:
                    mk_legal += 1
            if product == 0 and mk_legal >= 1 and mk_legal * 2 > n:
                out[ws] = "marketing"
        return out

    # ── path / route / name signals ─────────────────────────────────

    def classify_path(self, path: str) -> str | None:
        """Scope signal of one file path (``None`` = no signal).

        Signal sources, all collected then resolved by precedence
        (product first — the author's ``(dashboard)`` declaration beats a
        stray lexicon hit):

        1. Next route-groups — valid anywhere in the path;
        2. URL-context segments after the LAST routing-root marker;
        3. workspace dirs (``apps/docs``, ``packages/cli`` …);
        4. repo-ROOT surface dirs (``docs/…``, ``website/…`` — the
           conservative ``root_dirs`` subset).
        """
        if not path:
            return None
        segs = [s for s in _norm(path).lower().split("/") if s]
        hits: set[str] = set()
        for seg in segs:
            if seg.startswith("(") and seg.endswith(")") and len(seg) > 2:
                inner = seg[1:-1]
                if inner.startswith("."):
                    continue  # intercepting-route marker, not a group
                sc = self._groups.get(inner) or self._url.get(inner)
                if sc:
                    hits.add(sc)
        root_idx = -1
        for i, seg in enumerate(segs):
            if seg in _URL_ROOT_MARKERS:
                root_idx = i
        if root_idx >= 0:
            url_segs = [
                s for s in segs[root_idx + 1:]
                if not (s.startswith("(") and s.endswith(")"))
            ]
            if url_segs:
                # filename → stem (``blog.tsx`` → ``blog``); neutral drop
                stem = url_segs[-1].rsplit(".", 1)[0]
                url_segs = url_segs[:-1] + (
                    [] if stem in _NEUTRAL_STEMS else [stem]
                )
            for s in url_segs:
                sc = self._url.get(s)
                if sc:
                    hits.add(sc)
        for i, seg in enumerate(segs[:-1]):
            if seg in _WORKSPACE_CONTAINERS:
                # fixb143 (i-a) — the published-product-artifact veto runs
                # BEFORE the lexicon lookup and returns immediately, so it
                # beats every later rung including the instrument /
                # dev_artifact prong below. That precedence IS the fix: the
                # census proved the demotion arrives from the instrument
                # channel, not from the lexicon, so a veto expressed as
                # "one more hit in the set" would be out-voted and change
                # nothing.
                if self._veto and self._is_published_artifact(
                    "/".join(segs[: i + 2]),
                ):
                    return SCOPE_PRODUCT
                sc = self._workspace.get(segs[i + 1])
                if sc == "dev_tooling" and self._is_published_cli(
                    "/".join(segs[: i + 2]),
                ):
                    sc = SCOPE_PRODUCT  # shipped product CLI, not tooling
                if sc is None and self._recall:
                    sc = self._recall_workspace_scope(
                        segs[i + 1], "/".join(segs[: i + 2]),
                    )
                if sc:
                    hits.add(sc)
        if len(segs) > 1:
            sc = self._root_dirs.get(segs[0])
            if sc is None and self._recall and segs[0] in self._dev_artifact:
                sc = "dev_tooling"  # B58 item-3: EXACT dev-artifact root dir
            if sc:
                hits.add(sc)
        if len(segs) >= 2 and self._ws_scope_overrides:
            sc = self._ws_scope_overrides.get("/".join(segs[:2]))
            if sc:
                hits.add(sc)
        if self._instrument_dirs:
            joined = "/".join(segs)
            if any(joined == d or joined.startswith(d + "/")
                   for d in self._instrument_dirs):
                hits.add("dev_tooling")
        if SCOPE_PRODUCT in hits:
            return SCOPE_PRODUCT
        for sc in _NON_PRODUCT_PRECEDENCE:
            if sc in hits:
                return sc
        return None

    def _is_published_cli(self, workspace_dir: str) -> bool:
        """Published-product override for a dev_tooling-named workspace.

        Deterministic signal (coordinator doctrine, 2026-07-06, from the
        midday review): the workspace's ``package.json`` declares a
        non-empty ``bin`` AND is not ``private: true`` ⇒ customers
        install and drive it ⇒ PRODUCT surface. Unreadable / absent
        manifest, no ``bin``, or ``private: true`` ⇒ the lexicon's
        dev_tooling verdict stands. No repo_path ⇒ never reads ⇒ False.
        """
        if self._repo_path is None:
            return False
        cached = self._published_cache.get(workspace_dir)
        if cached is not None:
            return cached
        verdict = False
        try:
            import json as _json
            from pathlib import Path as _Path

            pj = _Path(self._repo_path) / workspace_dir / "package.json"
            if pj.is_file():
                doc = _json.loads(pj.read_text(encoding="utf-8"))
                if isinstance(doc, dict):
                    verdict = bool(doc.get("bin")) and doc.get("private") is not True
        except (OSError, ValueError):  # unreadable manifest → no override
            verdict = False
        self._published_cache[workspace_dir] = verdict
        return verdict

    def _is_published_artifact(self, workspace_dir: str) -> bool:
        """fixb143 (i-a) — is this workspace a SHIPPED PRODUCT ARTIFACT?

        ``package.json`` declares a non-empty ``bin`` (a CLI customers run)
        OR a non-empty ``publishConfig`` (a package customers install /
        embed), AND is not ``private: true`` — the manifest's own statement
        that the thing leaves the repo. Generalises the ``bin``-only
        :meth:`_is_published_cli` doctrine to the SDK/widget shape the
        census found (novu ``@novu/js`` — the Inbox component customers
        embed for THEIR end users; operator ruling 2026-08-11).

        DESIGN-SYSTEM SEPARATOR (load-bearing, pinned by counter-example):
        a published workspace that is a Storybook design system is a
        component library, not a product surface — ``@teable/ui-lib`` is
        published AND storybooked, and must stay laned (PF doctrine: a
        component library is a dev construct). Reuses :meth:`_has_storybook`
        verbatim, including its zero-routes guard.

        FAIL-SAFE: :meth:`_has_storybook` returns ``False`` when routes are
        unknown (cannot verify), which would silently turn the separator
        off; so when routes are unknown the whole veto is suppressed
        instead. No ``repo_path`` ⇒ no reads ⇒ ``False`` (the keyless /
        kill-switch path stays byte-identical).
        """
        if self._repo_path is None or not self._routes_known:
            return False
        cached = self._published_artifact_cache.get(workspace_dir)
        if cached is not None:
            return cached
        verdict = False
        try:
            import json as _json
            from pathlib import Path as _Path

            pj = _Path(self._repo_path) / workspace_dir / "package.json"
            if pj.is_file():
                doc = _json.loads(pj.read_text(encoding="utf-8"))
                if isinstance(doc, dict):
                    verdict = (
                        (bool(doc.get("bin")) or bool(doc.get("publishConfig")))
                        and doc.get("private") is not True
                    )
        except (OSError, ValueError):  # unreadable manifest → no veto
            verdict = False
        if verdict and self._has_storybook(workspace_dir):
            verdict = False  # published design system → component library
        self._published_artifact_cache[workspace_dir] = verdict
        return verdict

    def _recall_workspace_scope(
        self, name: str, workspace_dir: str,
    ) -> str | None:
        """B58 recall (flag-gated) verdict for a workspace segment the
        lexicon did NOT match exactly. Order:

        1. **product-name-prefixed purpose suffix** — a hyphenated segment
           (``twenty-docs``) whose hyphen-delimited component EQUALS a
           ``root_dirs`` token (``docs`` -> docs, ``website`` -> marketing).
           Split-equality (never substring) so ``twenty-docker`` never
           reads as ``docs``; restricted to the ``root_dirs`` conservative
           subset (www/website/docs/documentation) so product-domain words
           (blog/brand) and dev CLIs (cli/mcp) are untouched.
        2. **dev-artifact EXACT name** — a workspace whose exact name is a
           ``dev_artifact_tokens`` word (``templates`` / ``examples`` /
           ``fixtures`` …). EXACT only: 'resume-templates' never matches.
        3. **.storybook design-system** — zero-routes-guarded (see
           :meth:`_has_storybook`).

        ``None`` = no recall signal (conservative: stays product)."""
        parts = name.split("-")
        if len(parts) > 1:
            for part in parts:
                sc = self._root_dirs.get(part)
                if sc:
                    return sc
        if name in self._dev_artifact:
            return "dev_tooling"
        if self._has_storybook(workspace_dir):
            return "dev_tooling"
        return None

    def _has_storybook(self, workspace_dir: str) -> bool:
        """B58 item-2 — a workspace is a design-system / component library
        (dev_tooling, not product) when it ships a Storybook config
        (``.storybook/`` dir) + at least one story file AND owns ZERO
        product routes.

        The zero-routes guard is LOAD-BEARING: a routed app that merely
        uses Storybook for its own components (twenty ``packages/
        twenty-front``, 392 routes) must stay product — presence of
        ``.storybook`` alone would demote the whole product frontend. When
        routes are unknown (caller passed no routes_index) the signal is
        suppressed (fail-safe: cannot verify no-routes → do not demote).
        No repo_path → no filesystem reads → False (keyless / kill-switch
        byte-identical)."""
        if self._repo_path is None or not self._routes_known:
            return False
        if workspace_dir in self._routed_workspaces:
            return False
        cached = self._storybook_cache.get(workspace_dir)
        if cached is not None:
            return cached
        verdict = False
        try:
            from pathlib import Path as _Path

            root = _Path(self._repo_path) / workspace_dir
            if (root / ".storybook").is_dir():
                verdict = _has_story_file(root)
        except OSError:  # unreadable tree → no override
            verdict = False
        self._storybook_cache[workspace_dir] = verdict
        return verdict

    def classify_route_pattern(self, route_pattern: str) -> str | None:
        """Scope signal of one URL route pattern (``None`` = no signal)."""
        if not route_pattern:
            return None
        segs = [
            s for s in route_pattern.lower().split("/")
            if s and not _DYNAMIC_SEG_RE.match(s)
        ]
        hits = {self._url[s] for s in segs if s in self._url}
        if SCOPE_PRODUCT in hits:
            return SCOPE_PRODUCT
        for sc in _NON_PRODUCT_PRECEDENCE:
            if sc in hits:
                return sc
        return None

    def is_shell_name(self, *names: str | None) -> bool:
        """Container-page identity: the kebab slug is a shell slug,
        optionally with a ``-page`` suffix (mirrors the 6.7d container
        guard / validator I11 vocabulary — the guard consumes this tag)."""
        for raw in names:
            if not raw:
                continue
            slug = re.sub(r"[^a-z0-9]+", "-", str(raw).lower()).strip("-")
            if slug in self._shell_slugs:
                return True
            if slug.endswith("-page") and slug[:-5] in self._shell_slugs:
                return True
        return False

    def is_info_page_path(self, path: str | None) -> bool:
        """True when the path's URL-context segments hit the info-page
        class (contact / about / imprint / faq / legal pages)."""
        if not path:
            return False
        segs = [s for s in _norm(path).lower().split("/") if s]
        root_idx = -1
        for i, seg in enumerate(segs):
            if seg in _URL_ROOT_MARKERS:
                root_idx = i
        if root_idx < 0:
            return False
        url_segs = [
            s for s in segs[root_idx + 1:]
            if not (s.startswith("(") and s.endswith(")"))
        ]
        if url_segs:
            stem = url_segs[-1].rsplit(".", 1)[0]
            url_segs = url_segs[:-1] + ([] if stem in _NEUTRAL_STEMS else [stem])
        return any(s in self._info_segments for s in url_segs)

    # ── route-entry grain ────────────────────────────────────────────

    def classify_route_entry(self, entry: Mapping[str, Any]) -> str:
        """Scope of one ``routes_index`` entry.

        Stage 6.8b's ``trigger`` verdict wins (system routes are system
        surfaces); then lexicon signals from the pattern and the file
        path; an unmatched real route is PRODUCT surface (conservative).
        The bare root pattern (``/``) with no other signal is the app
        shell.
        """
        trig = str(entry.get("trigger") or _TRIGGER_INTERACTIVE)
        if trig != _TRIGGER_INTERACTIVE:
            return SCOPE_SYSTEM
        hits: set[str] = set()
        sc_p = self.classify_route_pattern(str(entry.get("pattern") or ""))
        if sc_p:
            hits.add(sc_p)
        sc_f = self.classify_path(str(entry.get("file") or ""))
        if sc_f:
            hits.add(sc_f)
        if SCOPE_PRODUCT in hits:
            return SCOPE_PRODUCT
        for sc in _NON_PRODUCT_PRECEDENCE:
            if sc in hits:
                return sc
        pattern = _norm(str(entry.get("pattern") or ""))
        if pattern in ("", "/"):
            return SCOPE_SHELL
        return SCOPE_PRODUCT

    # ── feature grain (developer features AND product features) ─────

    def classify_feature(
        self,
        feature: Any,
        route_by_file: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> str:
        """Scope of one feature row from its own evidence.

        1. Container identity (name is a shell slug) → ``shell``.
        2. Weighted vote over owned paths: each path contributes its
           :meth:`classify_path` signal; a path that IS a route file
           contributes the route entry's scope instead (system trigger /
           pattern lexicon / product default). No-signal paths abstain
           but COUNT in the denominator.
        3. Verdict: a non-product scope wins ONLY on a strict majority of
           ALL owned paths (abstains included) that also beats the
           product weight — a feature is a non-product surface when its
           evidence dominates its whole footprint, never on a stray
           lexicon hit. Everything else → ``product`` (conservative:
           never hide a product capability). No paths → ``product``.
        """
        scope, _ambiguous, _weights = self.classify_feature_with_signals(
            feature, route_by_file,
        )
        return scope

    def classify_feature_with_signals(
        self,
        feature: Any,
        route_by_file: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> tuple[str, bool, dict[str, int]]:
        """:meth:`classify_feature` + the W3 §4.7 ambiguity channel.

        Returns ``(scope, ambiguous, signal_weights)``. The verdict is
        BYTE-IDENTICAL to :meth:`classify_feature` (same rules — this is
        the same computation, annotated). ``ambiguous`` is the NARROW
        "conflicting signals" notion the Surface Adjudicator consumes:

        * a non-product signal AND a product signal are both present
          (direct conflict), OR
        * a non-product signal is present but the verdict fell to the
          conservative ``product`` default only because abstaining
          paths denied it the strict majority.

        Shell-named containers and no-signal features are NOT ambiguous
        (nothing to adjudicate — no conflicting evidence exists).
        """
        shell_named = self.is_shell_name(_get(feature, "name"),
                                         _get(feature, "display_name"))
        # fixb143 (i-c) — under the flag the NAME no longer short-circuits
        # blindly: the vote is computed FIRST and the shell verdict stands
        # only if the row's own paths raise no product signal. OFF (or a
        # name that is not a shell slug) keeps the original early return
        # byte-for-byte, so the vote below is never even reached.
        if shell_named and not shell_name_corroboration_enabled():
            return SCOPE_SHELL, False, {SCOPE_SHELL: 1}
        weights: dict[str, int] = {}
        total = 0
        rbf = route_by_file or {}
        for p in _get(feature, "paths") or []:
            key = _norm(str(p))
            total += 1
            entry = rbf.get(key)
            if entry is not None:
                sc: str | None = self.classify_route_entry(entry)
            else:
                sc = self.classify_path(key)
            if sc:
                weights[sc] = weights.get(sc, 0) + 1
        if shell_named:
            # Corroboration verdict. ZERO product weight ⇒ nothing in the
            # row contradicts the container reading ⇒ the name stands, and
            # the returned triple is IDENTICAL to the OFF hand (same scope,
            # same ambiguity, same weights) so a held row cannot be told
            # apart from a pre-flag one. One product-voting path is enough
            # to release it — the same "a real product route blocks a
            # non-product verdict" law used at journey grain, no threshold.
            if not weights.get(SCOPE_PRODUCT, 0):
                return SCOPE_SHELL, False, {SCOPE_SHELL: 1}
        if not weights or not total:
            return SCOPE_PRODUCT, False, weights
        product_w = weights.get(SCOPE_PRODUCT, 0)
        best_np = None
        for sc in _NON_PRODUCT_PRECEDENCE:
            w = weights.get(sc, 0)
            if w and (best_np is None or w > weights.get(best_np, 0)):
                best_np = sc
        ambiguous = best_np is not None and (
            product_w > 0 or weights[best_np] * 2 <= total
        )
        if (
            best_np is None
            or weights[best_np] * 2 <= total
            or product_w >= weights[best_np]
        ):
            return SCOPE_PRODUCT, ambiguous, weights
        return best_np, ambiguous, weights

    # ── user-flow grain (parked Lane-C aggregation, extended) ───────

    def member_vote(
        self,
        entry_file: str | None,
        paths: Iterable[str] = (),
        entry_is_route: bool = False,
    ) -> str | None:
        """One member flow's scope vote (``None`` = abstain)."""
        sc = self.classify_path(entry_file or "")
        if sc:
            return sc
        if entry_is_route:
            return SCOPE_PRODUCT  # real product route — blocks non-product
        path_votes = {v for v in (self.classify_path(p) for p in paths) if v}
        if len(path_votes) == 1:
            return next(iter(path_votes))
        return None

    def classify_user_flow(
        self,
        member_votes: Iterable[str | None],
        uf_routes: Iterable[str] = (),
        uf_category: str | None = None,
    ) -> str:
        """Aggregate member votes + UF route patterns into one scope.

        ``category == "system"`` (Stage 6.8b) is authoritative; any
        product vote blocks a non-product verdict (parked Lane-C rule);
        ``shell`` votes abstain at journey grain (a journey is never "the
        app shell"); otherwise majority with fixed precedence.
        """
        if uf_category == SCOPE_SYSTEM:
            return SCOPE_SYSTEM
        votes = [
            v for v in member_votes if v is not None and v != SCOPE_SHELL
        ]
        for r in uf_routes:
            # An unmatched route pattern is product surface (conservative).
            votes.append(self.classify_route_pattern(r) or SCOPE_PRODUCT)
        if not votes or SCOPE_PRODUCT in votes:
            return SCOPE_PRODUCT
        counts: dict[str, int] = {}
        for v in votes:
            counts[v] = counts.get(v, 0) + 1
        return max(
            counts,
            key=lambda s: (counts[s], -_NON_PRODUCT_PRECEDENCE.index(s)),
        )


def is_non_product_dev(dev: Any) -> bool:
    """True when *dev* carries a non-product (non-shell) surface tag —
    consumed by the 6.7d residual ladder (tier mints / capability joins
    must not promote marketing/docs/legal/dev_tooling surfaces). Reads the
    stamped field only; absent tag (taxonomy off / pre-W2a scans) → False,
    so every consumer no-ops under the kill-switch."""
    return str(_get(dev, "surface_scope") or "") in _NON_PRODUCT_DEV_SCOPES


# ── wiring helpers ──────────────────────────────────────────────────────


def _route_by_file(
    routes_index: Iterable[Mapping[str, Any]] | None,
) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for entry in routes_index or []:
        f = _norm(str(entry.get("file") or ""))
        if f:
            out.setdefault(f, entry)
    return out


def _stamp(obj: Any, field: str, value: Any) -> None:
    if isinstance(obj, dict):
        obj[field] = value
    else:
        setattr(obj, field, value)


def tag_layer1(
    developer_features: list["Feature"],
    routes_index: list[dict[str, Any]] | None,
    patterns: dict | None = None,
    repo_path: Any = None,
) -> dict[str, Any]:
    """Stage 6.85 Layer-1 tagging — stamp ``surface_scope`` on every
    ``routes_index`` entry and every developer feature, in place.

    Runs right after Stage 6.8b (so route ``trigger`` verdicts exist).
    ``repo_path`` enables the published-CLI product override.
    Returns telemetry ``{route_scopes: {...}, dev_scopes: {...}}``.
    """
    tele: dict[str, Any] = {"enabled": taxonomy_enabled()}
    if not taxonomy_enabled():
        return tele
    clf = SurfaceScopeClassifier(patterns, repo_path=repo_path,
                                 routes_index=routes_index)
    route_counts: dict[str, int] = {}
    for entry in routes_index or []:
        sc = clf.classify_route_entry(entry)
        entry["surface_scope"] = sc
        route_counts[sc] = route_counts.get(sc, 0) + 1
    rbf = _route_by_file(routes_index)
    dev_counts: dict[str, int] = {}
    for dev in developer_features:
        if getattr(dev, "layer", "developer") != "developer":
            continue
        sc = clf.classify_feature(dev, rbf)
        dev.surface_scope = sc
        dev_counts[sc] = dev_counts.get(sc, 0) + 1
    tele["route_scopes"] = route_counts
    tele["dev_scopes"] = dev_counts
    return tele


# ── emission lane ───────────────────────────────────────────────────────


def _pf_key(pf: Any) -> str:
    return str(_get(pf, "id", None) or _get(pf, "name", "") or "")


def _destination_survives(pf: Any, journeys: int) -> bool:
    """fixb143 round-3 (i-a) DESTINATION PRECONDITION — warden №45.

    Un-lane only what the product side can actually HOME. The warden ran
    the veto live and measured the missing half: freeing trigger.dev's
    ``packages/cli-v3`` produced no destination — 6.9966 dissolved the
    container, 17 anonymous lane rows absorbed the body, the parent dev
    row went ``uuid=''`` + ``pfid=null`` (I22), 4 null-pfid journeys
    appeared, I13 conservation went 0.6% -> 5.6%.

    FORENSICS — why fixb125 G1 "does not fire": it fires correctly and
    then abstains BY DESIGN. G1 DETECTION passes on trigger.dev
    (``cli:packages/cli-v3``, framework ``commander``, bin ``trigger``,
    24 sites, commands deploy/dev/init/install-mcp… — exactly the 8
    deleted journeys; the board's own ``cli_anchor_supply`` telemetry
    carries the cluster). But ``_cli_supply`` is a FOLD-LADDER FALLBACK:
    it runs only for a dev that reached the fold rungs WITHOUT a home,
    and the three CLI devs (``commands``, ``mcp``, ``trigger-dev``) were
    already homed on ``ws:packages/cli-v3``. Its docstring states the
    rule verbatim — "every unit whose CLI is already ON the product map
    resolves EARLIER and never reaches this rung". There is nothing to
    wire: the PF exists at 6.86 and is healthy.

    THE REAL DEFECT is downstream and is a property of the ANCHOR, not of
    the CLI machinery: a PF anchored on a BARE ``ws:`` workspace IS a
    structural container, and once the veto returns it to the product
    side Stage 6.9966 dissolves any structural container hoarding
    ``FLOOR_JOURNEYS`` or more journeys. That is precisely what the
    warden watched happen.

    So the precondition is exactly the shape 6.9966 destroys — the floor
    IMPORTED, never re-derived, so the two cannot drift:

        bare ``ws:`` anchor  AND  journeys >= FLOOR_JOURNEYS  =>  ABSTAIN

    MEASURED on the three veto-freed lanes: trigger.dev ABSTAINS (bare
    ``ws:packages/cli-v3``, 8 journeys); novu ``js`` and novu ``react``
    COMMIT — their anchors carry real mint provenance
    (``mint:entry-evidence->ws:packages/js``) so they are not bare
    containers, and at 2 and 1 journeys they sit under the floor anyway.
    Never-worse AND not vacuous.
    """
    from wystan.pipeline_v2.stage_6_9966_container_journey_rehome import (
        FLOOR_JOURNEYS,
    )

    aid = str(_get(pf, "anchor_id") or "")
    # A BARE workspace anchor: ``ws:<dir>`` with no mint/fold provenance
    # prefix. ``mint:entry-evidence->ws:…`` / ``fold:span->ws:…`` are NOT
    # bare — something already elected that unit on its own evidence.
    return not (aid.startswith("ws:") and journeys >= FLOOR_JOURNEYS)


class _AnchorProbe:
    """fixb147 — the smallest object :func:`_destination_survives` can be
    asked about: a candidate ``anchor_id`` and nothing else.

    The rung-A supply must know whether the identity it is about to
    stamp actually clears the precondition BEFORE it mutates the PF —
    otherwise a supply that failed would leave a row both re-anchored
    and laned. Asking the real predicate against a probe keeps its code
    untouched (the fix is the identity, never the test)."""

    __slots__ = ("anchor_id",)

    def __init__(self, anchor_id: str) -> None:
        self.anchor_id = anchor_id


#: fixb143 round-3 (i-c) — tokens that may never carry a released PF's
#: identity. Page/site glue that would re-assert the I11 violation from
#: the other side; the container words themselves come from the
#: taxonomy's own ``shell_slugs``, never a second vocabulary.
_CONTAINER_QUALIFY_STOP = frozenset({
    "page", "pages", "site", "view", "views", "screen", "screens",
})


#: fixb143 round-4 — the shortest part a de-compounded container word may
#: contribute. Three characters is the shortest word in the container
#: vocabulary itself, so this is the vocabulary's own floor, not a tuned
#: number: it is what stops 'homer' folding as 'home' + 'r'.
_FUSED_PART_MIN = 3


def _is_container_token(token: str, vocab: frozenset[str] | set[str]) -> bool:
    """fixb143 round-4 (warden battery 34) — is *token* ENTIRELY made of
    container words, including FUSED forms?

    THE DEFECT this closes: strapi's live held journey carries the resource
    ``homepage`` as ONE token. The round-3 strip compared whole tokens
    against the container vocabulary ('home', 'page'), so the fused form
    passed straight through and the rider emitted
    ``{from: 'Home Page', to: 'Home Homepage'}`` — a stuttering name that
    technically escapes the I11 regex (two words) while being semantically
    exactly what I11 forbids.

    MECHANISM, NOT A COMPOUND LIST (the standing doctrine): the token is
    segmented greedily against the container vocabulary the taxonomy
    ALREADY owns (``shell_slugs`` + the page/site glue), and it folds only
    when the segmentation covers the token COMPLETELY. 'homepage' =
    home+page folds; 'homescreen', 'mainpage', 'landingpage', 'indexpage',
    'rootpage', 'mainscreen', 'homeview' fold by the same rule with no new
    vocabulary. A leftover that is not itself a container word keeps the
    token: 'homer' (home + 'r'), 'homework' (home + 'work'), 'mainframe',
    'screenshot', 'rootkit', 'indexer', 'landingzone', 'pagination',
    'viewer' all survive.

    MEASURED over every live UF ``resource`` token in the world census
    (1383 distinct, 6205 occurrences): exactly 10 tokens fold, and all ten
    are BARE container words that the round-3 strip already removed
    (page 44, view 27, index 10, site 6, pages 4, main 2, home 2, screen 1,
    landing 1, root 1). ZERO product-meaningful tokens fold — the
    de-compounder adds fused coverage without widening the blast radius.
    """
    if not token:
        return False
    if token in vocab:
        return True
    # A fused compound needs at least two parts, each >= the vocabulary's
    # own shortest word.
    if len(token) < 2 * _FUSED_PART_MIN:
        return False
    for word in sorted(vocab):           # sorted: never set-iteration order
        if len(word) < _FUSED_PART_MIN or not token.startswith(word):
            continue
        rest = token[len(word):]
        if rest in vocab or _is_container_token(rest, vocab):
            return True
    return False


def container_vocabulary(clf: "SurfaceScopeClassifier") -> frozenset[str]:
    """The container vocabulary the I11 rider judges names against — the
    classifier's own shell slugs plus the page/site glue. ONE source of
    truth, so the labeler guard (round 5) and the qualification that earned
    the name (round 3) can never disagree about what a container word is."""
    return frozenset(set(clf._shell_slugs) | _CONTAINER_QUALIFY_STOP)


def is_container_only_display(
    text: str, vocab: frozenset[str] | set[str],
) -> bool:
    """fixb143 round-5 (ii-a) — is *text* made ENTIRELY of container words?

    The I11 predicate at DISPLAY grain, reusing the round-4 de-compounder
    token by token, so a fused form is judged exactly as the qualification
    judged it: 'Home' → True, 'Home Page' → True, 'Homepage' → True,
    'Home Popular' → False, 'Popular Documents' → False.

    An empty / glyph-less string carries no non-container evidence, so it
    reads True (the labeler already rejects blank picks upstream; this
    branch only keeps the guard total).
    """
    tokens = [t for t in re.split(r"[^a-z0-9]+", str(text or "").lower()) if t]
    if not tokens:
        return True
    return all(_is_container_token(t, vocab) for t in tokens)


#: fixb143 round-5 (ii-a) — the SCAN-SCOPED registry of PF rows whose
#: container-name release EARNED a non-container display THIS SCAN, keyed by
#: every alias a downstream consumer might hold (``_pf_key`` and the row's
#: ``name`` slug — ``naming_contract`` keys its pending items by ``name``).
#: The value carries the earned display AND the container vocabulary that
#: earned it, so the guard never has to rebuild a classifier.
#:
#: WHY A REGISTRY AND NOT TELEMETRY — the fixb136 law, paid for a second
#: time. ``shell_release_qualified`` IS in ``scan_meta``, and the warden
#: could read 'Home Popular' there while the emitted row said 'Home': a
#: promise crossing a filter is not a channel. Telemetry is a record for
#: humans; a module-scoped dict both sides import is a contract between
#: stages.
#:
#: LIFECYCLE (deterministic, single-scan process): cleared once per scan at
#: ``apply_emission_taxonomy`` entry — the 6.85 producer, which runs before
#: Stage 7 naming — and read by the labeler guard. Tests clear it
#: explicitly.
_EARNED_DISPLAY: dict[str, tuple[str, frozenset[str]]] = {}


def note_earned_display(
    keys: Iterable[str], display: str, vocab: frozenset[str] | set[str],
) -> None:
    """Record that *display* was EARNED by the row addressed by *keys*."""
    frozen = frozenset(vocab)
    for k in keys:
        if str(k):
            _EARNED_DISPLAY[str(k)] = (str(display), frozen)


def earned_displays() -> Mapping[str, tuple[str, frozenset[str]]]:
    """The earned displays recorded so far this scan (read-only view)."""
    return dict(_EARNED_DISPLAY)


def reset_earned_displays() -> None:
    """Clear the registry — called once per scan by the 6.85 producer."""
    _EARNED_DISPLAY.clear()


def _resource_qualification(
    pf: Any, held: Iterable[Any], clf: "SurfaceScopeClassifier",
) -> str | None:
    """fixb143 round-3 (i-c) CONTAINER-NAME RIDER — warden №45 / I11.

    Operator invariant I11 ("a home page can never be a feature a priori") is
    BANKED and the corroboration release does not overturn it: a released
    PF must never land displaying 'Home'. It has to EARN a non-container
    identity from the journeys it actually holds, or the release abstains.

    Evidence is the journey's STRUCTURED ``resource`` field — not a parse
    of its display name. strapi's held journey ('View and manage home page
    widgets') supplies the resource that yields the 'Home Widgets' class.
    Container words are stripped on BOTH sides, so the result can never
    re-assert the container ('home' + 'home page widgets' -> 'Home
    Widgets', never 'Home Home Page Widgets').

    Returns the qualified display, or ``None`` = NO resource evidence =>
    the caller ABSTAINS and the row stays laned. Never mint what I11
    forbids.
    """
    base = str(_get(pf, "display_name") or _get(pf, "name") or "").strip()
    base_tokens = [t for t in re.split(r"[^a-z0-9]+", base.lower()) if t]
    # The DE-COMPOUND vocabulary is the container vocabulary ONLY — never
    # the PF's own base tokens. Folding against arbitrary product words in
    # the display name would let a product noun eat a resource token.
    container = container_vocabulary(clf)
    stop = set(base_tokens) | set(container)
    counts: dict[str, int] = {}
    order: list[str] = []
    for uf in held:
        res = str(_get(uf, "resource") or "").strip().lower()
        for tok in (t for t in re.split(r"[^a-z0-9]+", res) if t):
            if tok in stop or _is_container_token(tok, container):
                continue
            if tok not in counts:
                order.append(tok)
            counts[tok] = counts.get(tok, 0) + 1
    if not counts:
        # Nothing meaningful survived the strip => there is no evidence for
        # a non-container identity => the caller ABSTAINS and the row stays
        # laned. This is the I11-safe floor: never mint 'Home Homepage'.
        return None
    # Deterministic: mass first, then FIRST-SEEN order (never set order).
    best = sorted(order, key=lambda t: (-counts[t], order.index(t)))[:2]
    qualifier = " ".join(t.capitalize() for t in best)
    # The HEAD keeps only the container IDENTITY word(s); page/site glue is
    # dropped, so strapi reads 'Home Widgets' and never 'Home Page Widgets'
    # — carrying 'Page' forward would re-import the noun I11 objects to.
    head_tokens = [t for t in base_tokens
                   if t not in _CONTAINER_QUALIFY_STOP
                   and not _is_container_token(t, _CONTAINER_QUALIFY_STOP)]
    head = " ".join(t.capitalize() for t in head_tokens) or "Surface"
    return f"{head} {qualifier}".strip()


def _declared_dependency_workspaces(repo_path: Any) -> frozenset[str]:
    """fixb143 (i-d) — workspace dirs whose package NAME is declared as a
    dependency by SOME OTHER workspace's manifest.

    The monorepo's own manifests are the authority ("mechanisms, not
    vocabularies"): if ``apps/studio`` lists ``@supabase/pg-meta`` in its
    dependencies, then ``packages/pg-meta`` is code the product is built
    on — product-declared evidence the path lexicon cannot see. Reading
    manifests only (no source, no import graph) keeps this O(workspaces)
    and deterministic.

    An APP workspace is a LEAF of this graph — nothing depends on
    ``@openstatus/web`` — which is exactly why the guard cannot swallow
    the adjudicator's legitimate marketing/legal flips on app surfaces.

    Returns workspace dirs (``packages/pg-meta``), not package names. No
    ``repo_path`` ⇒ empty ⇒ the guard is inert.
    """
    if repo_path is None:
        return frozenset()
    import json as _json
    from pathlib import Path as _Path

    root = _Path(repo_path)
    by_name: dict[str, str] = {}
    deps_by_ws: dict[str, set[str]] = {}
    try:
        candidates = [
            pj for container in sorted(_WORKSPACE_CONTAINERS)
            if (root / container).is_dir()
            for pj in sorted((root / container).glob("*/package.json"))
        ]
    except OSError:
        return frozenset()
    for pj in candidates:
        ws = _norm(str(pj.parent.relative_to(root)))
        try:
            doc = _json.loads(pj.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(doc, dict):
            continue
        name = doc.get("name")
        if isinstance(name, str) and name:
            by_name[name] = ws
        declared: set[str] = set()
        for block in ("dependencies", "devDependencies", "peerDependencies"):
            val = doc.get(block)
            if isinstance(val, dict):
                declared.update(str(k) for k in val)
        deps_by_ws[ws] = declared
    out: set[str] = set()
    for ws, declared in deps_by_ws.items():
        for dep in declared:
            target = by_name.get(dep)
            if target and target != ws:  # never self-declared
                out.add(target)
    return frozenset(out)


def _anchor_surface_scope(
    pf: Any, clf: "SurfaceScopeClassifier",
) -> str | None:
    """B58 anchor-guard signal — the surface scope of a PF's ANCHOR path.

    A ``route:`` anchor with no non-product lexicon signal is a real
    product route (the conservative-route default), so it reads
    ``product`` and protects the PF from a recall demotion driven by
    borrowed shared (design-system / docs) member paths. ``ws:`` /
    ``fdir:`` anchors with no signal → ``None`` (unknown — the existing
    path-majority vote stands). Short keyed-artifact anchors (no ``/``)
    → ``None``."""
    aid = str(_get(pf, "anchor_id") or "")
    if ":" not in aid:
        return None
    kind, apath = aid.split(":", 1)
    apath = _norm(apath)
    if "/" not in apath:
        return None
    sc = clf.classify_path(apath)
    if sc and sc != SCOPE_PRODUCT:
        return sc
    if kind == "route" or sc == SCOPE_PRODUCT:
        return SCOPE_PRODUCT
    return None


def _is_shared_bucket(pf: Any) -> bool:
    return _pf_key(pf).strip().lower() in _SHARED_PF_KEYS


def _flow_lookup(flows: Iterable[Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for fl in flows:
        for key in (_get(fl, "uuid"), _get(fl, "name")):
            if key and str(key) not in out:
                out[str(key)] = fl
    return out


def _entry_of(flow: Any) -> str | None:
    entry = _get(flow, "entry_point_file")
    if entry:
        return str(entry)
    ep = _get(flow, "entry_point")
    if ep is not None:
        path = ep.get("path") if isinstance(ep, dict) else getattr(ep, "path", None)
        if path:
            return str(path)
    return None


def _uf_entry_files(uf: Any, flow_by_id: Mapping[str, Any]) -> list[str]:
    files: list[str] = []
    for mid in _get(uf, "member_flow_ids") or []:
        fl = flow_by_id.get(str(mid))
        if fl is None:
            continue
        e = _entry_of(fl)
        if e:
            files.append(_norm(e))
        else:
            files.extend(_norm(str(p)) for p in (_get(fl, "paths") or []))
    return files


def _tag_user_flows(
    user_flows: list["UserFlow"],
    flow_by_id: Mapping[str, Any],
    route_files: frozenset[str],
    clf: SurfaceScopeClassifier,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for uf in user_flows:
        # B52 — a transport-lane journey (lane_ref set) already carries
        # its authoritative scope ('platform_infrastructure', stamped by
        # Stage 6.985); the member-vote classifier must not overwrite
        # it. lane_ref exists only under WYSTAN_FLOWFUL_TRANSPORT_LANE
        # → OFF scans are byte-identical (counts included).
        if _get(uf, "lane_ref"):
            sc0 = str(_get(uf, "surface_scope") or "platform_infrastructure")
            counts[sc0] = counts.get(sc0, 0) + 1
            continue
        votes: list[str | None] = []
        for mid in _get(uf, "member_flow_ids") or []:
            fl = flow_by_id.get(str(mid))
            if fl is None:
                continue
            entry = _entry_of(fl) or ""
            votes.append(clf.member_vote(
                entry,
                paths=_get(fl, "paths") or [],
                entry_is_route=_norm(entry) in route_files,
            ))
        sc = clf.classify_user_flow(
            votes,
            uf_routes=_get(uf, "routes") or [],
            uf_category=_get(uf, "category"),
        )
        _stamp(uf, "surface_scope", sc)
        counts[sc] = counts.get(sc, 0) + 1
    return counts


def _lane_entry(
    pf: Any,
    scope: str,
    member_devs: list[Any],
    moved_ufs: list[Any],
) -> dict[str, Any]:
    """One ``non_product_surfaces[]`` row — a compact, self-contained view
    of the surface (NOT a full Feature dump; the dev rows stay in
    ``features[]`` with their ``product_feature_id`` pointing here)."""
    entry: dict[str, Any] = {
        "name": _get(pf, "name"),
        "display_name": _get(pf, "display_name"),
        "surface_scope": scope,
        "description": _get(pf, "description"),
        "uuid": _get(pf, "uuid") or "",
        "paths": list(_get(pf, "paths") or []),
        "loc": _get(pf, "loc"),
        "loc_shared": _get(pf, "loc_shared"),
        "member_devs": sorted(
            str(_get(d, "name") or "") for d in member_devs
        ),
        "reason": "non_product_surface_scope",
    }
    entry["user_flows"] = [
        uf.model_dump() if hasattr(uf, "model_dump") else dict(uf)
        for uf in moved_ufs
    ]
    return entry


def _member_absorbed(row: Any, live_member_ids: frozenset[str]) -> float:
    """Share of a laned journey's member flows that are STILL held by some
    surviving journey — the probe-P15 measure, computed at this seam.

    ``0.00`` means the members left the journey layer entirely, so the row
    is a shell. A member-LESS row (no member ids at all) reads ``0.00`` by
    the same law: there is nothing of it left in the journey layer, which
    is the purest form of the same shell.

    The seam matters: this is the share measured at the LANE TRANSFER, not
    at emission. Downstream passes only re-home or drop journeys, they
    never resurrect a member into a row that lost it, so a seam-time
    ``0.00`` stays ``0.00`` on the board (world census: all 13 laned rows
    read 0.00 at BOTH points). Measuring here — and not from the emitted
    board — is what lets the deletion be decided by the stage that owns
    the move.
    """
    mids = [str(m) for m in (_get(row, "member_flow_ids") or ())]
    if not mids:
        return 0.0
    return len([m for m in mids if m in live_member_ids]) / len(mids)


def _delete_hollow_lane_rows(
    lane: list[dict[str, Any]],
    surviving_ufs: Iterable[Any],
    tele: dict[str, Any],
) -> None:
    """fixb140 — operator ruling variant A: drop the hollow laned journey.

    A row the lane transfer moved out of ``user_flows[]`` whose
    ``member_absorbed`` is ``0.00`` is REMOVED from the lane entry's
    ``user_flows[]`` payload instead of surviving there as a
    ``scope=marketing`` shell. Rationale (the ruling, verbatim in spirit):
    a member-less journey shell is the hollow-rows disease; the permanent
    record lives in the ``lane_deleted`` channel stamped here (id AND name
    for EVERY deleted row) plus ``journey_lineage_audit.lane_moved``, so
    nothing vanishes silently; and the marketing CODE remains visible in
    its own board section (the lane entry keeps its paths / member devs /
    LOC — only the hollow row inside it goes).

    DEATH-ACCOUNTING (id-bound, never a silent disappearance). The row was
    already a "death" for the journey-lineage audit (it is absent from the
    emitted ``user_flows[]``); what deletion removes is its EXISTING
    id-bound channel — the physical ``model_dump()`` in the lane. Two
    replacements are stamped in the same breath, both id-tier:

    * ``scan_meta.surface_taxonomy_emission`` — ``lane_deleted_ids`` (flat
      id list, the channel the audit reads) and ``lane_deleted`` (the same
      rows with their NAMES and destination lane). BOTH ARE COMPLETE: no
      display cap, ever. A capped record is not a permanent record — the
      audit's own ``lane_moved`` sample stops at 20 rows, so on a board
      that deletes 79 (supabase) the name of row 21 would exist nowhere.
      Lead ruling 2026-08-10: the emission channel carries every name.
    * a per-writer self-report (fixb121 M6) under
      :data:`LANE_DELETE_WRITER`, which is a no-op when no registry is
      installed and which cannot launder anything: a claim only becomes a
      channel if the id really was in the post-lattice snapshot and really
      is off the board.

    ANTI-CASE (measured shape, honoured literally): a PARTIALLY absorbed
    row (``member_absorbed > 0``) keeps at least one member alive in the
    journey layer, is therefore not a shell, and is NOT deleted. That
    shape does not occur in the 13-row world census, so the ruling does
    not reach it and neither does this pass.
    """
    live: set[str] = set()
    for uf in surviving_ufs:
        for m in (_get(uf, "member_flow_ids") or ()):
            live.add(str(m))
    live_ids = frozenset(live)

    deleted: list[dict[str, Any]] = []
    for entry in lane:
        rows = entry.get("user_flows") or []
        kept_rows: list[Any] = []
        for row in rows:
            absorbed = _member_absorbed(row, live_ids)
            if absorbed > 0.0:
                kept_rows.append(row)
                continue
            deleted.append({
                "id": str(_get(row, "id") or ""),
                "name": str(_get(row, "name") or ""),
                "pf": str(_get(row, "product_feature_id") or ""),
                "lane": str(entry.get("name") or ""),
                "surface_scope": str(entry.get("surface_scope") or ""),
                "members": len(_get(row, "member_flow_ids") or ()),
                "member_absorbed": round(absorbed, 2),
            })
        if len(kept_rows) != len(rows):
            entry["user_flows"] = kept_rows

    if not deleted:
        return  # nothing deleted ⇒ no keys ⇒ byte-identical to the OFF hand
    deleted.sort(key=lambda r: str(r["id"]))
    ids = [str(r["id"]) for r in deleted if r["id"]]
    tele["lane_rows_deleted"] = len(deleted)
    # NO SLICE on either list — the permanent record is complete by law
    # (lead ruling 2026-08-10). Worst measured board is supabase at 79
    # rows ≈ a few KB; a cap here would be the M2 blindness class wearing
    # a "display sample" costume, on the one channel that must not blink.
    tele["lane_deleted_ids"] = ids
    tele["lane_deleted"] = deleted
    report_journey_kill(LANE_DELETE_WRITER, ids)


def _dissolve_info_ufs(
    user_flows: list["UserFlow"],
    flow_by_id: Mapping[str, Any],
    product_pf_keys: frozenset[str],
    clf: SurfaceScopeClassifier,
    tele: dict[str, Any],
) -> None:
    """Consequence (b): info-page journeys dissolve into the hosting UF.

    A UF qualifies when its scope is marketing/legal, EVERY member flow's
    entry (or paths, when no entry) lands on an info-page URL, and its
    product feature is a real product-lane PF that hosts at least one
    OTHER journey (the host). The member flows join the host as plain
    dev-flows; the info UF row is removed (never a PF, never its own
    journey). No host → left in place, tagged only (honest residual)."""
    by_pf: dict[str, list[Any]] = {}
    for uf in user_flows:
        ref = _get(uf, "product_feature_id")
        if ref:
            by_pf.setdefault(str(ref), []).append(uf)

    dissolved: list[Any] = []
    for uf in list(user_flows):
        if str(_get(uf, "surface_scope") or "") not in ("marketing", "legal"):
            continue
        pfid = str(_get(uf, "product_feature_id") or "")
        if pfid not in product_pf_keys:
            continue  # lane PFs took their journeys already; orphans skip
        entries = _uf_entry_files(uf, flow_by_id)
        if not entries or not all(clf.is_info_page_path(e) for e in entries):
            continue
        hosts = [
            u for u in by_pf.get(pfid, [])
            if u is not uf and u not in dissolved
        ]
        if not hosts:
            continue  # "where one exists" — never orphan a PF's only UF
        uf_files = set(entries)

        def _overlap(host: Any) -> int:
            hfiles = set(_uf_entry_files(host, flow_by_id))
            shared_dirs = 0
            for a in uf_files:
                a_dir = a.rsplit("/", 1)[0]
                for b in hfiles:
                    b_dir = b.rsplit("/", 1)[0]
                    common = 0
                    for sa, sb in zip(a_dir.split("/"), b_dir.split("/")):
                        if sa != sb:
                            break
                        common += 1
                    shared_dirs = max(shared_dirs, common)
            return shared_dirs

        host = sorted(
            hosts,
            key=lambda h: (
                -_overlap(h),
                -len(_get(h, "member_flow_ids") or []),
                str(_get(h, "id") or ""),
            ),
        )[0]
        host_mids = list(_get(host, "member_flow_ids") or [])
        for mid in _get(uf, "member_flow_ids") or []:
            if mid not in host_mids:
                host_mids.append(mid)
        _stamp(host, "member_flow_ids", host_mids)
        _stamp(host, "member_count", len(host_mids))
        host_routes = list(_get(host, "routes") or [])
        for r in _get(uf, "routes") or []:
            if r not in host_routes:
                host_routes.append(r)
        _stamp(host, "routes", host_routes)
        dissolved.append(uf)
        if len(tele.setdefault("info_ufs_dissolved_sample", [])) < 10:
            tele["info_ufs_dissolved_sample"].append({
                "uf": _get(uf, "name"), "host": _get(host, "name"),
                "pf": pfid,
            })

    if dissolved:
        gone = {id(u) for u in dissolved}
        user_flows[:] = [u for u in user_flows if id(u) not in gone]
    tele["info_ufs_dissolved"] = len(dissolved)


def _shared_reason_for(dev: Any, clf: SurfaceScopeClassifier) -> str:
    """Deterministic reason ladder for one shared-bucket resident."""
    from wystan.pipeline_v2.spine_hygiene import is_concern_name
    from wystan.pipeline_v2.stage_8_7_anchor_desink import (
        _is_workspace_anchor,
    )
    from wystan.pipeline_v2.stage_6_7d_llm_journey_abstraction import (
        _STRUCTURE_LEAK_SLUGS,
    )

    scope = str(_get(dev, "surface_scope") or "")
    if scope in _NON_PRODUCT_DEV_SCOPES:
        return "non_product_surface"
    name = str(_get(dev, "name") or "")
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if (
        scope == SCOPE_SHELL
        or slug in _STRUCTURE_LEAK_SLUGS
        or _is_workspace_anchor(dev)
    ):
        return "genuinely_shared_infra"
    if is_concern_name(name):
        return "facet_view"
    has_anchor_claim = any(
        (m.get("role") if isinstance(m, dict) else getattr(m, "role", None))
        == "anchor"
        for m in (_get(dev, "member_files") or [])
    )
    if has_anchor_claim or (_get(dev, "flows") or []):
        return "awaiting_wave2_mint"
    return "no_anchor_lineage"


# ── B28 — dev-artifact workspaces (Shape E) + Shape-D re-anchor ────────


def _workspace_unit(path: str | None) -> str | None:
    """Workspace grain of a path: ``<seg0>/<seg1>`` when two segments
    exist (``apps/docs``, ``blocks/vue``, ``packages/app-store``), else
    the root segment. No container vocabulary — B28 candidacy is decided
    by manifests/marks, never by the container's name."""
    if not path:
        return None
    segs = [s for s in _norm(str(path)).split("/") if s]
    if not segs:
        return None
    return "/".join(segs[:2]) if len(segs) >= 2 else segs[0]


def _is_registry_publisher(repo_path: Any, ws_dir: str) -> bool:
    """B28 P-B — the workspace's own manifests declare a component-registry
    PUBLISHER (the shadcn registry convention): ``components.json`` at the
    workspace root **plus** registry evidence (a ``registry/`` source tree,
    a ``registry.json``, or a ``shadcn build`` script). Mere shadcn
    CONSUMERS carry ``components.json`` alone (measured: papermark,
    openstatus ×3, supabase ``packages/ui``) and never fire."""
    try:
        from pathlib import Path as _Path

        root = _Path(repo_path) / ws_dir
        if not (root / "components.json").is_file():
            return False
        if (root / "registry").is_dir() or (root / "registry.json").is_file():
            return True
        pj = root / "package.json"
        if pj.is_file():
            import json as _json

            doc = _json.loads(pj.read_text(encoding="utf-8"))
            if isinstance(doc, dict):
                scripts = " ".join(
                    str(v) for v in (doc.get("scripts") or {}).values()
                )
                return "shadcn build" in scripts
    except (OSError, ValueError):  # unreadable manifest → no override
        return False
    return False


def _dev_artifact_dirs(
    developer_features: Iterable[Any],
    product_features: Iterable[Any],
    user_flows: Iterable[Any],
    flows: Iterable[Any],
    repo_path: Any,
    marked_units: Iterable[str],
    tele: dict[str, Any],
) -> set[str]:
    """Collect B28 Shape-E candidate workspaces (P-B manifests + the P-D
    marks from Stage 6.86) and gate them behind the two hard rails:

    * **R1 journey-isolation (strict minority)** — entry contributions of
      journeys homed OUTSIDE the workspace must be a strict minority of
      the workspace's entry contributions (zero-tolerance is too brittle:
      one ui-library registry template mirrors a studio route);
    * **R2 dominant-app guard** — never the workspace holding the strict
      majority of the board's member-flow entries (the repo whose
      registry IS the product — shadcn-class).

    Survivors join the classifier's instrument-dirs channel, so the
    EXISTING strict-majority feature vote + emission lane execute the
    demotion — journeys ride along (operator ruling 2026-07-10)."""
    def _under(path: str | None, prefix: str) -> bool:
        return bool(path) and (
            path == prefix or str(path).startswith(prefix + "/"))

    flow_by_id = _flow_lookup(flows)
    pf_anchor_path: dict[str, str] = {}
    for pf in product_features:
        aid = str(_get(pf, "anchor_id") or "")
        if ":" in aid:
            apath = _norm(aid.split(":", 1)[1])
            if "/" in apath:  # short keyed-artifact anchors have no unit
                pf_anchor_path[_pf_key(pf)] = apath

    # Candidates are PF-ANCHORED dirs only — B28's mandate is "PFs
    # anchored inside non-product apps"; a dev-artifact workspace nobody
    # anchors a PF in changes nothing on the product board, so touching
    # it (dev-grain scope shifts) would be pure blast radius. P-D marks
    # keep their own hub-child grain; P-B checks the 2-seg workspace of
    # each anchor.
    cands: dict[str, str] = {}
    for u in marked_units or ():
        nu = _norm(str(u))
        if nu and any(_under(ap, nu) for ap in pf_anchor_path.values()):
            cands[nu] = "P-D:hub-fixture"
    if repo_path is not None:
        checked: set[str] = set()
        for ap in sorted(pf_anchor_path.values()):
            ws = _workspace_unit(ap)
            if not ws or "/" not in ws or ws in cands or ws in checked:
                continue
            checked.add(ws)
            if _is_registry_publisher(repo_path, ws):
                cands[ws] = "P-B:registry-publisher"
    if not cands:
        return set()
    # R1/R2 rails at each candidate's OWN grain (2-seg workspace or
    # hub-child dir): internal = entries under the candidate from
    # journeys whose home PF is anchored under it too; external = entries
    # under it from journeys homed elsewhere.
    entries: list[tuple[str, str | None]] = []  # (entry, home anchor)
    for uf in user_flows:
        home = pf_anchor_path.get(
            str(_get(uf, "product_feature_id") or ""))
        for mid in _get(uf, "member_flow_ids") or []:
            fl = flow_by_id.get(str(mid))
            entry = _entry_of(fl) if fl is not None else None
            if entry:
                entries.append((_norm(entry), home))
    total = len(entries)

    applied: set[str] = set()
    blocked: dict[str, str] = {}
    for cand in sorted(cands):
        i = sum(1 for e, home in entries
                if _under(e, cand) and _under(home, cand))
        x = sum(1 for e, home in entries
                if _under(e, cand) and not _under(home, cand))
        if x and x >= i:
            blocked[cand] = f"R1:external {x} >= internal {i}"
            continue
        if total and (i + x) * 2 > total:
            blocked[cand] = "R2:dominant-app"
            continue
        applied.add(cand)
    tele["candidates"] = dict(sorted(cands.items()))
    tele["applied"] = sorted(applied)
    if blocked:
        tele["blocked"] = blocked
    return applied


_CODE_FILE_EXT_RE = re.compile(
    r"\.(?:tsx?|jsx?|mjs|cjs|mts|cts|vue|svelte|py)$"
)


def _majority_dir(paths: list[str]) -> str | None:
    """Deepest directory reached by descending while ONE child holds a
    strict majority of the ORIGINAL path mass (scale-invariant — the
    B20/B22 strict-majority family at directory grain). Anchoring the
    bar to the original mass stops the walk from compounding relative
    majorities into an over-deep election (midday ``insights``: the
    remaining-mass rule descended to ``…/src/content/prompts``; the
    original-mass rule stops at ``packages/insights/src``)."""
    if not paths:
        return None
    total = len(paths)
    cur = ""
    while True:
        kids: dict[str, int] = {}
        for p in paths:
            if cur and not p.startswith(cur + "/"):
                continue
            rel = p[len(cur):].lstrip("/") if cur else p
            segs = rel.split("/")
            if len(segs) > 1:
                kids[segs[0]] = kids.get(segs[0], 0) + 1
        if not kids:
            return cur or None
        best = max(sorted(kids), key=lambda k: kids[k])
        if kids[best] * 2 <= total:
            return cur or None
        cur = (cur + "/" if cur else "") + best


def _reanchor_mislocated_pfs(
    product_features: list[Any],
    clf: SurfaceScopeClassifier,
    route_files: frozenset[str],
    tele: dict[str, Any],
) -> None:
    """B28 Shape D — a PRODUCT-scoped PF whose anchor sits inside a
    non-product workspace but whose OWN evidence majority lives outside it
    (supabase docs-guides class: ``auth`` anchored at
    ``route:apps/docs/app/guides/auth`` with 107/107 studio paths) keeps
    its journeys and its uuid and re-anchors in place:

    1. ``outside`` = owned paths not under the anchor workspace; a strict
       majority is required (an inside-majority PF is the LANE's case);
    2. elect the majority-dir walk result when it lands strictly deeper
       than the workspace root; else fall back to the common prefix of
       the outside ROUTE files (anchor-lineage law) — extension-stripped
       when it is a single file; else refuse (telemetry, no mutation);
    3. anchor kind: ``route:`` when the elected prefix carries
       routes_index lineage, else ``fdir:``.
    """
    moves: list[dict[str, str]] = []
    refused: dict[str, str] = {}
    stripped_routes = {
        _CODE_FILE_EXT_RE.sub("", rf): rf for rf in route_files
    }
    for pf in product_features:
        if _is_shared_bucket(pf):
            continue
        if str(_get(pf, "surface_scope") or "") != SCOPE_PRODUCT:
            continue
        aid = str(_get(pf, "anchor_id") or "")
        if ":" not in aid:
            continue
        apath = _norm(aid.split(":", 1)[1])
        if "/" not in apath:
            continue  # short keyed-artifact anchor — no workspace unit
        unit = _workspace_unit(apath)
        if not unit:
            continue
        unit_scope = clf.classify_path(unit)
        if unit_scope in (None, SCOPE_PRODUCT):
            continue
        name = str(_get(pf, "display_name") or _get(pf, "name") or "?")
        paths = [_norm(str(p)) for p in (_get(pf, "paths") or [])]
        outside = [p for p in paths if _workspace_unit(p) != unit]
        if not paths or len(outside) * 2 <= len(paths):
            # body majority INSIDE the non-product workspace — the
            # emission lane owns that shape; nothing to re-anchor.
            continue
        unit_depth = len(unit.split("/"))
        elected = _majority_dir(outside)
        if not elected or len(elected.split("/")) <= unit_depth:
            rfiles = [p for p in outside if p in route_files]
            common: str | None = None
            if rfiles:
                segs_list = [p.split("/") for p in rfiles]
                out: list[str] = []
                for segs in zip(*segs_list):
                    if len(set(segs)) == 1:
                        out.append(segs[0])
                    else:
                        break
                common = "/".join(out) or None
                if common and _CODE_FILE_EXT_RE.search(common):
                    common = _CODE_FILE_EXT_RE.sub("", common)
            if common and len(common.split("/")) > unit_depth:
                elected = common
            else:
                refused[name] = "no-deep-majority-dir"
                continue
        has_route = elected in stripped_routes or any(
            rf == elected or rf.startswith(elected + "/")
            for rf in route_files
        )
        new_aid = ("route:" if has_route else "fdir:") + elected
        if new_aid == aid:
            continue
        moves.append({"pf": name, "from": aid, "to": new_aid})
        _stamp(pf, "anchor_id", new_aid)
    if moves:
        tele["reanchored"] = moves
    if refused:
        tele["refused"] = refused


def apply_emission_taxonomy(
    developer_features: list["Feature"],
    product_features: list["Feature"],
    user_flows: list["UserFlow"],
    flows: list["Flow"],
    routes_index: list[dict[str, Any]] | None,
    patterns: dict | None = None,
    repo_path: Any = None,
    adjudicator: Any = None,
    instrument_dirs: Iterable[str] | None = None,
    dev_artifact_units: Iterable[str] = (),
    headless_repo: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]], list["Feature"]]:
    """Emission-time taxonomy: tag UFs/PFs, split the non-product lane,
    dissolve info-page journeys, re-bind non-product shared devs, stamp
    shared-resident reasons.

    Mutates ``developer_features`` / ``user_flows`` in place; returns
    ``(telemetry, non_product_surfaces, product_features)`` — the caller
    rebinds its ``product_features`` list (lane rows are REMOVED from it).
    ``repo_path`` enables the published-CLI product override.

    ``adjudicator`` (W3 §4.7, keyed scans): callable resolving the
    NARROW ambiguous-PF minority (conflicting deterministic signals —
    see :meth:`SurfaceScopeClassifier.classify_feature_with_signals`).
    Its verdict must be a scope the item's own signals support (the
    personas module enforces that contract; re-checked here) — invalid
    or absent verdicts keep the deterministic scope, so the adjudicator
    can never invent a surface. ``None`` (keyless / kill-switch) is the
    deterministic path, byte-identical to pre-W3.
    """
    # fixb143 round-5 (ii-a) — the earned-display registry is SCAN-SCOPED and
    # THIS is the scan's single producer, so the reset belongs at its entry
    # (above the master switch: a taxonomy-off scan must not inherit the
    # previous scan's promises inside a long-lived worker process).
    reset_earned_displays()
    tele: dict[str, Any] = {"enabled": taxonomy_enabled()}
    if not taxonomy_enabled():
        return tele, [], product_features

    # B28 Shape E — P-B/P-D dev-artifact workspaces join the instrument
    # channel behind the R1/R2 rails BEFORE the classifier is built, so
    # the existing strict-majority vote + emission lane execute the
    # demotion with journeys riding along. Flag-OFF (or no survivors)
    # leaves ``instrument_dirs`` byte-identical.
    if nonproduct_scope_enabled():
        dev_tele: dict[str, Any] = {}
        extra = _dev_artifact_dirs(
            developer_features, product_features, user_flows, flows,
            repo_path, dev_artifact_units, dev_tele,
        )
        if extra:
            instrument_dirs = tuple(sorted(
                {_norm(str(d)) for d in (instrument_dirs or []) if d}
                | extra
            ))
        if dev_tele.get("candidates"):
            tele["dev_artifact"] = dev_tele

    clf = SurfaceScopeClassifier(patterns, repo_path=repo_path,
                                 routes_index=routes_index,
                                 instrument_dirs=instrument_dirs)
    # W4.2 Fix 1 rider — PF-grain classification must not second-guess
    # the mint with the instrument prong: a PRODUCT capability whose
    # paths straddle instrument dirs (midday `banking` after the Fix-3
    # provider fold + shared members) would tip dev_tooling and leave
    # the board. The instrument prong applies at PF grain ONLY to PFs
    # whose OWN anchor sits inside an instrument dir; every other PF
    # classifies with the plain (pre-W4.2) signal set. Dev/UF grain
    # keeps the instrument-aware classifier.
    _instr = tuple(sorted(_norm(str(d)).lower()
                          for d in (instrument_dirs or []) if d))
    clf_plain = (SurfaceScopeClassifier(patterns, repo_path=repo_path,
                                        routes_index=routes_index)
                 if _instr else clf)

    def _anchor_in_instruments(pf: Any) -> bool:
        aid = str(_get(pf, "anchor_id", None) or "")
        if ":" not in aid:
            return False
        path = _norm(aid.split(":", 1)[1]).lower()
        return bool(path) and any(
            path == d or path.startswith(d + "/") for d in _instr
        )

    def _pf_clf(pf: Any) -> SurfaceScopeClassifier:
        return clf if _anchor_in_instruments(pf) else clf_plain

    rbf = _route_by_file(routes_index)
    route_files = frozenset(rbf.keys())
    flow_by_id = _flow_lookup(flows)

    # 1a. Re-stamp dev tags — paths moved through 6.9/6.9b strips and the
    # 8.9.x carves since the Layer-1 pass; classification is cheap and
    # idempotent, so recompute from the FINAL ownership.
    dev_counts: dict[str, int] = {}
    for dev in developer_features:
        if getattr(dev, "layer", "developer") != "developer":
            continue
        sc = clf.classify_feature(dev, rbf)
        dev.surface_scope = sc
        dev_counts[sc] = dev_counts.get(sc, 0) + 1
    tele["dev_scopes"] = dev_counts

    # 1b. Tag journeys.
    tele["uf_scopes"] = _tag_user_flows(user_flows, flow_by_id, route_files, clf)

    # 1c. Tag product features. The shared/platform bucket row is a
    # cross-cutting aggregate, not a surface — it stays in the product
    # list by definition (I10/I22 govern it) and carries the neutral
    # ``product`` tag so I20 activation covers every PF row.
    pf_counts: dict[str, int] = {}
    ambiguous_pfs: list[tuple[Any, str, dict[str, int]]] = []
    anchor_guarded = 0
    # fixb143 round-3 — journeys held per PF, needed by BOTH riders (the
    # i-a destination floor and the i-c resource qualification). Built
    # once, before any PF is classified.
    _ufs_by_pf: dict[str, list[Any]] = {}
    for _u in user_flows:
        _ref = str(_get(_u, "product_feature_id") or "")
        if _ref:
            _ufs_by_pf.setdefault(_ref, []).append(_u)
    # A no-veto twin: the ONLY way to know whether the veto is what saved
    # a PF is to ask what its scope would have been without it.
    _veto_on = published_artifact_veto_enabled()
    _nv_instr: SurfaceScopeClassifier = clf
    _nv_plain: SurfaceScopeClassifier = clf_plain
    if _veto_on:
        # TWO twins, mirroring clf / clf_plain exactly — `_pf_clf` picks the
        # instrument-aware classifier for a PF anchored inside an instrument
        # dir, so the counterfactual must be asked in the SAME world or the
        # comparison is against a different classifier, not against the veto.
        _nv_instr = SurfaceScopeClassifier(
            patterns, repo_path=repo_path, routes_index=routes_index,
            instrument_dirs=instrument_dirs)
        _nv_instr._veto = False
        if _instr:
            _nv_plain = SurfaceScopeClassifier(
                patterns, repo_path=repo_path, routes_index=routes_index)
            _nv_plain._veto = False
        else:
            _nv_plain = _nv_instr

    def _pf_clf_noveto(pf: Any) -> "SurfaceScopeClassifier":
        return _nv_instr if _anchor_in_instruments(pf) else _nv_plain
    _veto_abstained: list[dict[str, Any]] = []
    _released: list[dict[str, Any]] = []
    _release_abstained: list[dict[str, Any]] = []
    #: fixb147 rung A — identity supplies, id-bound and UNCAPPED (the
    #: permanent-record law: a row that changed identity is a decision).
    _identity_supplied: list[dict[str, Any]] = []
    for pf in product_features:
        if _is_shared_bucket(pf):
            sc = SCOPE_PRODUCT
        else:
            pf_clf = _pf_clf(pf)
            sc, ambiguous, sig = pf_clf.classify_feature_with_signals(
                pf, rbf)
            # B58 anchor-guard: the recall widenings add shared
            # design-system / docs member PATHS to product PFs (plane
            # 'States' = propel state-icons, 'Webhooks' = propel
            # empty-state illustrations, both anchored on real apps/web
            # routes). A PF ANCHORED in a genuine product surface must not
            # leave the product list on borrowed shared evidence — its
            # journeys would ride along and vanish. Fires only when the
            # recall flag is on AND the anchor reads product; every main
            # (flag-OFF) demotion keeps a non-product anchor (verified on
            # twenty/plane/reactive-resume), so this is inert under the
            # kill-switch.
            if (pf_clf._recall and sc in NON_PRODUCT_PF_SCOPES
                    and _anchor_surface_scope(pf, pf_clf) == SCOPE_PRODUCT):
                sc = SCOPE_PRODUCT
                anchor_guarded += 1
            _held = _ufs_by_pf.get(_pf_key(pf), [])
            # ── fixb143 round-3 (i-a) DESTINATION PRECONDITION ────────
            # If the veto is what saved this PF, it may only commit when
            # a destination survives; otherwise restore the pre-veto
            # scope. Never-worse by construction: the abstain hand IS the
            # flag-OFF hand for that row.
            if _veto_on and sc == SCOPE_PRODUCT:
                sc0, _a0, _w0 = _pf_clf_noveto(
                    pf).classify_feature_with_signals(pf, rbf)
                if sc0 in NON_PRODUCT_PF_SCOPES and not _destination_survives(
                        pf, len(_held)):
                    # ── fixb147 rung A — ANCHOR-IDENTITY SUPPLY ───────
                    # The precondition abstains on ONE shape: a bare
                    # ``ws:`` anchor over the journey floor. Before
                    # laning the row, ask its own manifest what it IS:
                    # a workspace that declares a shipped binary is the
                    # repo's COMMAND SURFACE, and its identity is the
                    # fixb125 ``cli:<dir>`` anchor + "<bin> CLI"
                    # display, not the workspace directory it lives in.
                    # Supplied ONLY when the supplied identity actually
                    # survives the SAME precondition (asked against the
                    # candidate anchor — the predicate's code is
                    # untouched and flips on its own), so the rung can
                    # never stamp an identity AND lane the row. Scope
                    # is the abstaining row and nothing else: every
                    # other published workspace keeps its ``ws:``
                    # anchor, its ``_is_structural_home`` membership and
                    # its census class. Flag OFF ⇒ no manifest read ⇒
                    # byte-identical.
                    _supplied = (
                        cli_identity_for_anchor(
                            repo_path, _get(pf, "anchor_id"))
                        if ws_anchor_identity_enabled() else None)
                    _identity_holds = (
                        _supplied is not None and _destination_survives(
                            _AnchorProbe(_supplied[0]), len(_held)))
                    if _supplied is not None and _identity_holds:
                        _identity_supplied.append({
                            "pf": _pf_key(pf),
                            "from": str(_get(pf, "display_name")
                                        or _get(pf, "name") or ""),
                            "to": _supplied[1],
                            "anchor_from": str(_get(pf, "anchor_id") or ""),
                            "anchor_to": _supplied[0],
                            "journeys": len(_held),
                            "rung": "cli_manifest_binary",
                        })
                        _stamp(pf, "anchor_id", _supplied[0])
                        _stamp(pf, "display_name", _supplied[1])
                    else:
                        sc = sc0
                        _veto_abstained.append({
                            "pf": _pf_key(pf),
                            "name": str(_get(pf, "display_name")
                                        or _get(pf, "name") or ""),
                            "anchor": str(_get(pf, "anchor_id") or ""),
                            "journeys": len(_held),
                            "restored_scope": sc0,
                            "reason": "bare_ws_anchor_over_journey_floor",
                        })
            # ── fixb143 round-3 (i-c) CONTAINER-NAME RIDER (I11) ──────
            # A corroboration-RELEASED container name must earn a
            # non-container display from its held journeys' resources, or
            # the release abstains. I11 is banked; never mint 'Home'.
            if (shell_name_corroboration_enabled() and sc == SCOPE_PRODUCT
                    and pf_clf.is_shell_name(_get(pf, "name"),
                                             _get(pf, "display_name"))):
                qualified = _resource_qualification(pf, _held, pf_clf)
                if qualified is None:
                    sc = SCOPE_SHELL
                    _release_abstained.append({
                        "pf": _pf_key(pf),
                        "name": str(_get(pf, "display_name")
                                    or _get(pf, "name") or ""),
                        "journeys": len(_held),
                        "reason": "no_resource_evidence_I11",
                    })
                else:
                    _released.append({
                        "pf": _pf_key(pf),
                        "from": str(_get(pf, "display_name")
                                    or _get(pf, "name") or ""),
                        "to": qualified,
                        "journeys": len(_held),
                    })
                    _stamp(pf, "display_name", qualified)
                    # ── fixb143 round-5 (ii-a) EARNED-DISPLAY REGISTRY ──
                    # The stamp alone is not a contract: Stage 7's labeler
                    # is the declared single display writer and re-checks
                    # only ``display_law_violations``, where I11 does not
                    # live. Register the earned name (under BOTH keys a
                    # consumer may hold) so the labeler can refuse a
                    # container-only overwrite deterministically.
                    if released_display_registry_enabled():
                        note_earned_display(
                            (_pf_key(pf), str(_get(pf, "name") or "")),
                            qualified, container_vocabulary(pf_clf),
                        )
            if ambiguous:
                ambiguous_pfs.append((pf, sc, sig))
        pf.surface_scope = sc
        pf_counts[sc] = pf_counts.get(sc, 0) + 1
    tele["pf_scopes"] = pf_counts
    if anchor_guarded:
        tele["recall_anchor_guarded"] = anchor_guarded
    # fixb143 round-3 — both riders report id-bound and UNCAPPED, the same
    # permanent-record law fixb140 set for ``lane_deleted``: a row that
    # did not move because of a precondition is as much a decision as a
    # row that did.
    if _identity_supplied:
        _identity_supplied.sort(key=lambda r: str(r["pf"]))
        tele["ws_anchor_identity_supplied"] = _identity_supplied
    if _veto_abstained:
        _veto_abstained.sort(key=lambda r: str(r["pf"]))
        tele["veto_destination_abstained"] = _veto_abstained
    if _released:
        _released.sort(key=lambda r: str(r["pf"]))
        tele["shell_release_qualified"] = _released
    if _release_abstained:
        _release_abstained.sort(key=lambda r: str(r["pf"]))
        tele["shell_release_abstained"] = _release_abstained

    # 1d. Surface Adjudicator (W3 §4.7) — ONLY the conflicting-signal
    # minority; the verdict set per item is bounded to the scopes its
    # own deterministic signals support (∪ product). Runs BEFORE the
    # lane split so a flipped marketing/docs PF leaves the product list
    # like any deterministically-classified one. Deterministic verdicts
    # stand on any failure/reject (never blocks).
    #
    # JOURNEY GUARD (W3 mini-A/B finding, openstatus `notifications`):
    # a PF referenced by >=2 user journeys carries product-declared
    # evidence the path lexicon can't see — the flowful-never-in-lane
    # law (I9) at PF grain, and the same denominator doctrine as the
    # marketing workspace-class override ("zero product-declared
    # signals"). Such PFs are never sent for adjudication; the flip
    # class is journey-thin info/tool surfaces only.
    if adjudicator is not None and ambiguous_pfs:
        uf_refs: dict[str, int] = {}
        for uf in user_flows:
            ref = str(_get(uf, "product_feature_id") or "")
            if ref:
                uf_refs[ref] = uf_refs.get(ref, 0) + 1
        assignable = frozenset(NON_PRODUCT_PF_SCOPES) | {SCOPE_PRODUCT}

        # W5.1 ROUTE GUARD (midday `transactions` regression): a PF that
        # owns a real PRODUCT route file carries product-declared evidence
        # the path lexicon undercounts — the same "real product route blocks
        # non-product" law member_vote applies at journey grain (:602). The
        # marketing website's `.../transactions` page (2 files) merged into
        # the 70-file dashboard `transactions` capability made it ambiguous;
        # a lone LLM flip then hid a core product surface into the lane. A
        # PF anchored on a product route is never sent for a non-product
        # flip. Structural, scale-invariant (no threshold), deterministic.
        def _owns_product_route(pf: Any) -> bool:
            clf_pf = _pf_clf(pf)
            for p in (_get(pf, "paths") or []):
                entry = rbf.get(_norm(str(p)))
                if entry is not None and \
                        clf_pf.classify_route_entry(entry) == SCOPE_PRODUCT:
                    return True
            return False

        # fixb143 (i-d) — manifest dependency graph, built once per scan and
        # only when the guard is armed (an OFF scan performs zero extra
        # filesystem reads, so the kill-switch is byte- AND cost-identical).
        _dep_guard = adjudicator_dep_guard_enabled()
        _dep_ws = (_declared_dependency_workspaces(repo_path)
                   if _dep_guard else frozenset())

        def _is_dependency_package(pf: Any) -> bool:
            """The PF is DOMINATED by workspaces another workspace depends
            on — a STRICT MAJORITY of its owned paths, abstains included.

            FORM PINNED BY GATE, not by taste. The first implementation used
            the any-hit form (mirroring ``_owns_product_route`` just above,
            where one real route is enough). The after-census refuted it:
            any-hit blocks 4 of the 32 recorded world flips, because a MIXED
            lane touches a depended-on package with a minority of its paths
            — midday ``chat`` (4 of 12 paths in ``apps/api``) and typebot
            ``templates`` (4 of 15 in ``packages/templates``) are marketing
            surfaces that SHOULD keep flipping. Strict majority blocks
            exactly 2 (supabase ``pg-meta`` 101/103, teable ``formula``
            29/29) and leaves all 30 defensible flips firing.

            Strict majority is also this module's own convention:
            :meth:`classify_feature_with_signals` demands the same
            ``w * 2 > total`` of ALL owned paths before any non-product
            verdict. A guard against a scope decision should read the
            footprint the same way the scope decision does.
            """
            paths = [str(p) for p in (_get(pf, "paths") or [])]
            if not paths:
                return False
            hits = 0
            for p in paths:
                segs = [s for s in _norm(p).lower().split("/") if s]
                if any(seg in _WORKSPACE_CONTAINERS
                       and "/".join(segs[: i + 2]) in _dep_ws
                       for i, seg in enumerate(segs[:-1])):
                    hits += 1
            return hits * 2 > len(paths)

        items: list[dict[str, Any]] = []
        journey_guarded = 0
        route_guarded = 0
        dependency_guarded = 0
        for pf, sc, sig in ambiguous_pfs:
            allowed = sorted(
                ({SCOPE_PRODUCT} | set(sig)) & assignable
            )
            if len(allowed) < 2:
                continue  # nothing to adjudicate
            if uf_refs.get(_pf_key(pf), 0) >= 2:
                journey_guarded += 1
                continue  # journey-rich ⇒ product-evidenced, never flip
            if _owns_product_route(pf):
                route_guarded += 1
                continue  # owns a real product route ⇒ never flip to lane
            if _dep_guard and _is_dependency_package(pf):
                dependency_guarded += 1
                continue  # the product is BUILT ON it ⇒ never flip to lane
            all_paths = [str(p) for p in (_get(pf, "paths") or [])]
            paths = all_paths[:5]
            item: dict[str, Any] = {
                "id": _pf_key(pf),
                "name": str(
                    _get(pf, "display_name") or _get(pf, "name") or ""),
                "allowed": allowed,
                "signals": {k: v for k, v in sorted(sig.items())},
                "paths": paths,
            }
            if _dep_guard:
                # DENOMINATOR (fixb143 i-d part 2): without it the model
                # reads ``{"docs": 2}`` as "the evidence" instead of "2 of
                # 103 paths, which is why the deterministic verdict was
                # product". Appended last so the OFF payload — and its LLM
                # cache key — stay byte-identical.
                item["total_paths"] = len(all_paths)
            items.append(item)
        verdicts: dict[str, str] = {}
        if items:
            try:
                verdicts = adjudicator(items) or {}
            except Exception:  # noqa: BLE001 — persona must never break a scan
                verdicts = {}
        flips = 0
        by_key = {_pf_key(pf): pf for pf, _sc, _sig in ambiguous_pfs}
        allowed_by_id = {i["id"]: set(i["allowed"]) for i in items}
        item_by_id = {str(i["id"]): i for i in items}
        # fixb143 RECORD-LAW RIDER (no flag — provenance, per the fixb138
        # applied_ids precedent). fixb140 established that a channel which
        # makes rows vanish records EVERY id and name, uncapped, "because a
        # capped record is not a permanent record". The adjudicator moves
        # whole PFs out of ``product_features[]`` — a strictly larger act —
        # and recorded only ``flips: N``. The fixb143 census had to
        # reconstruct by elimination that supabase's single flip was
        # ``pg-meta`` (10795 LOC, 60 devs); that reconstruction must never
        # be necessary again. Written unconditionally: telemetry-only, it
        # cannot change a scope, and it appears only when a flip happened,
        # so a no-flip scan stays key-for-key identical to main.
        flip_detail: list[dict[str, Any]] = []
        for iid, scope in verdicts.items():
            pf_obj = by_key.get(str(iid))
            if pf_obj is None or scope not in (
                allowed_by_id.get(str(iid)) or set()
            ):
                continue
            old = str(_get(pf_obj, "surface_scope") or "")
            if scope != old:
                pf_counts[old] = pf_counts.get(old, 1) - 1
                pf_counts[scope] = pf_counts.get(scope, 0) + 1
                pf_obj.surface_scope = scope
                flips += 1
                _item = item_by_id.get(str(iid)) or {}
                flip_detail.append({
                    "id": str(iid),
                    "name": str(_get(pf_obj, "display_name")
                               or _get(pf_obj, "name") or ""),
                    "from": old,
                    "to": scope,
                    "signals": dict(_item.get("signals") or {}),
                    "total_paths": _item.get(
                        "total_paths", len(_get(pf_obj, "paths") or [])),
                })
        tele["adjudicator"] = {
            "ambiguous": len(ambiguous_pfs),
            "journey_guarded": journey_guarded,
            "route_guarded": route_guarded,
            "sent": len(items),
            "verdicts": len(verdicts),
            "flips": flips,
        }
        if dependency_guarded:
            tele["adjudicator"]["dependency_guarded"] = dependency_guarded
        if flip_detail:
            # NO SLICE, by the same law as ``lane_deleted``.
            flip_detail.sort(key=lambda r: str(r["id"]))
            tele["adjudicator"]["flip_detail"] = flip_detail
        tele["pf_scopes"] = pf_counts

    # ── fixb143 round-5 (ii-b) ABSTAIN SCOPE ROLLBACK ──────────────────
    # Warden №47 new-suspect. Step 1a stamps every dev row with the ARMED
    # classifier, BEFORE the PF loop decides whether the same flag's
    # release commits — so an abstain that restored the PARENT left its
    # children released (trigger.dev 13 rows, strapi ``home``, inbox-zero
    # ``landing``). A dev-grain release by a flag that can abstain is a
    # CONSEQUENCE of the PF-grain verdict, never an independent decision.
    #
    # Runs HERE (post-adjudicator, pre-lane-split) on purpose: the
    # adjudicator can still move an abstained PF's scope, and a row may
    # only be rolled back against its home's FINAL scope. The restore
    # target is the row's own flag-OFF hand, so the pass is never-worse by
    # construction — exactly the (i-a) abstain's shape at dev grain.
    if abstain_scope_rollback_enabled():
        _corr_on = shell_name_corroboration_enabled()
        _abstained_keys = frozenset(
            [str(r["pf"]) for r in _veto_abstained]
            + [str(r["pf"]) for r in _release_abstained]
        )
        _qualified_keys = frozenset(str(r["pf"]) for r in _released)
        _pf_scope_by_key = {
            _pf_key(pf): str(_get(pf, "surface_scope") or "")
            for pf in product_features
        }

        def _off_hand(dev: Any) -> str:
            """The scope this row carries with the round-3 riders OFF.

            For a container-NAMED row that IS the early return the (i-c)
            flag removed (``shell`` from the name alone, before a path is
            read); for everything else it is the no-veto twin's verdict —
            the same classifier step 1a used, minus (i-a). When neither
            flag is armed the twin IS ``clf``, so the value equals the
            armed stamp and nothing can roll back.
            """
            if _corr_on and clf.is_shell_name(_get(dev, "name"),
                                              _get(dev, "display_name")):
                return SCOPE_SHELL
            return _nv_instr.classify_feature(dev, rbf)

        _rolled: list[dict[str, Any]] = []
        for dev in developer_features:
            if getattr(dev, "layer", "developer") != "developer":
                continue
            armed = str(_get(dev, "surface_scope") or "")
            off = _off_hand(dev)
            if off == armed:
                continue          # no flag moved this row — nothing to undo
            home = str(_get(dev, "product_feature_id") or "")
            home_scope = _pf_scope_by_key.get(home)
            if home in _abstained_keys and home_scope != SCOPE_PRODUCT:
                # Rung 1 — the parent's release did NOT commit.
                reason = "abstained_parent"
            elif (_corr_on and armed != SCOPE_SHELL
                    and clf.is_shell_name(_get(dev, "name"),
                                          _get(dev, "display_name"))
                    and not (home in _qualified_keys
                             and home_scope == SCOPE_PRODUCT)):
                # Rung 2 — a container-named row released with NO PF-grain
                # qualification vouching for it anywhere (inbox-zero
                # ``landing`` under a home PF that never entered the
                # release path). I11 is banked: an unqualified container
                # identity is not released at any grain.
                reason = "unvouched_container_name"
            else:
                continue
            dev.surface_scope = off
            _rolled.append({
                "dev": str(_get(dev, "name") or ""),
                "pf": home,
                "from": armed,
                "to": off,
                "reason": reason,
            })
        if _rolled:
            # Id-bound and UNCAPPED, the fixb140 permanent-record law: a
            # row whose scope was undone is as much a decision as one that
            # moved. The 1a census is then RE-DERIVED — telemetry that
            # disagrees with the emitted rows is how this defect hid.
            _rolled.sort(key=lambda r: (str(r["pf"]), str(r["dev"])))
            tele["abstain_scope_rolled_back"] = _rolled
            recount: dict[str, int] = {}
            for dev in developer_features:
                if getattr(dev, "layer", "developer") != "developer":
                    continue
                _s = str(_get(dev, "surface_scope") or "")
                recount[_s] = recount.get(_s, 0) + 1
            tele["dev_scopes"] = recount
        if _abstained_keys:
            # THE INVARIANT HOOK: after the pass, no row homed to an
            # abstained PF may carry a scope its flag-OFF hand did not
            # give it. This number is 0 or the rollback is incomplete.
            tele["abstain_scope_mutations"] = sum(
                1 for dev in developer_features
                if getattr(dev, "layer", "developer") == "developer"
                and str(_get(dev, "product_feature_id") or "")
                in _abstained_keys
                and str(_get(dev, "surface_scope") or "") != _off_hand(dev)
            )

    # B28 Shape D — PRODUCT-scoped PFs anchored inside non-product
    # workspaces re-anchor to their evidence-majority product surface.
    # Runs on FINAL scopes (post-adjudicator) and BEFORE the lane split
    # (a laned PF is Shape E and never re-anchors). No journey, uuid or
    # path mutation — conservation trivial; validator I23 reads the
    # healed anchor.
    if docs_reanchor_enabled():
        reanchor_tele: dict[str, Any] = {}
        _reanchor_mislocated_pfs(
            product_features, clf, route_files, reanchor_tele,
        )
        if reanchor_tele:
            tele["docs_reanchor"] = reanchor_tele

    lane: list[dict[str, Any]] = []
    if lane_enabled():
        # 2. Non-product lane split (consequence a / validator I20).
        # B98 rung-3c (ollama endpoint families): on a HEADLESS repo a
        # route-corroborated PF (member files ∩ routes_index) is a product
        # surface BY DEFINITION — 26 family tiles (api-chat/generate/
        # pull/…) scoped to 'shell' (a shared routes.go = "no separate
        # surface", the web doctrine) and quietly moved into the lane,
        # leaving dangling dev pointers. Same authority channel as the v6 prong.
        # VERDICT gate (the I20 lesson from twenty): the exemption lives
        # ONLY on a headless repo (the 6.86 satellite verdict via the
        # caller), not on a bare flag — on a paged repo route-backed
        # marketing/legal pages must ride into the lane as always.
        _b98_route_files: frozenset[str] = frozenset(
            str(r.get("file") or "") for r in (routes_index or [])
            if isinstance(r, dict)
        ) - frozenset({""}) if headless_repo else frozenset()
        _b98_dev_files: dict[str, set[str]] = {}
        if _b98_route_files:
            # PF rows at this point still have NO member_files (Stage 7
            # builds them) — route corroboration goes through member devs
            # (join by product_feature_id) with PF-own paths as a fallback.
            for _dv in developer_features:
                _ref = str(_get(_dv, "product_feature_id") or "")
                if _ref:
                    _b98_dev_files.setdefault(_ref, set()).update(
                        str(p) for p in (_get(_dv, "paths") or ()))
        def _b98_route_backed(pf: Any) -> bool:
            if not _b98_route_files:
                return False
            files = set(_b98_dev_files.get(_pf_key(pf), ()))
            for x in (_get(pf, "member_files") or _get(pf, "paths") or ()):
                files.add(str(x.get("path") if isinstance(x, dict) else x))
            return bool(files & _b98_route_files)
        keep: list[Any] = []
        moved: list[Any] = []
        for pf in product_features:
            _np_scope = (str(_get(pf, "surface_scope") or "")
                         in NON_PRODUCT_PF_SCOPES)
            if _np_scope and _b98_route_backed(pf):
                # I20 fix: the exemption does not merely keep the row — it
                # CORRECTS the scope (a route-backed surface on a headless
                # repo is a product by routes_index authority; a non-product
                # scope inside the product list is I20 by construction).
                pf.surface_scope = "product"
                keep.append(pf)
                continue
            if not _is_shared_bucket(pf) and _np_scope:
                moved.append(pf)
            else:
                keep.append(pf)
        if moved:
            moved_keys = {_pf_key(pf) for pf in moved}
            ufs_by_pf: dict[str, list[Any]] = {}
            kept_ufs: list[Any] = []
            for uf in user_flows:
                ref = str(_get(uf, "product_feature_id") or "")
                if ref in moved_keys:
                    ufs_by_pf.setdefault(ref, []).append(uf)
                else:
                    kept_ufs.append(uf)
            devs_by_pf: dict[str, list[Any]] = {}
            for dev in developer_features:
                ref = str(_get(dev, "product_feature_id") or "")
                if ref in moved_keys:
                    devs_by_pf.setdefault(ref, []).append(dev)
            for pf in moved:
                key = _pf_key(pf)
                lane.append(_lane_entry(
                    pf,
                    str(_get(pf, "surface_scope")),
                    devs_by_pf.get(key, []),
                    ufs_by_pf.get(key, []),
                ))
            user_flows[:] = kept_ufs
            product_features = keep
        # fixb140 — the transfer count is read BEFORE the deletion pass:
        # ``ufs_moved_to_lane`` means "how many journeys the transfer took",
        # and that is true under both hands (under OFF nothing is deleted,
        # so the two readings coincide byte-for-byte).
        tele["pfs_moved_to_lane"] = len(moved)
        tele["ufs_moved_to_lane"] = sum(
            len(e["user_flows"]) for e in lane
        )
        tele["lane_names"] = [e["name"] for e in lane][:20]
        # fixb140 — lane-deletion (operator ruling variant A). Runs on the
        # SURVIVING journey layer (``user_flows`` is already ``kept_ufs``),
        # which is exactly where ``member_absorbed`` is knowable.
        if lane_moved_delete_enabled():
            _delete_hollow_lane_rows(lane, user_flows, tele)

        # 3. Info-page journey dissolution (consequence b).
        product_pf_keys = frozenset(
            _pf_key(pf) for pf in product_features if not _is_shared_bucket(pf)
        )
        _dissolve_info_ufs(user_flows, flow_by_id, product_pf_keys, clf, tele)

        # 4. Non-product shared devs re-bind to the lane surface claiming
        # their paths (info pages are never Shared Platform residents).
        rebound = 0
        if lane:
            lane_paths = [
                (e["name"], frozenset(_norm(str(p)) for p in e["paths"]))
                for e in lane
            ]
            for dev in developer_features:
                pfid = str(_get(dev, "product_feature_id") or "")
                if pfid.strip().lower() not in _SHARED_PF_KEYS:
                    continue
                if str(_get(dev, "surface_scope") or "") not in _NON_PRODUCT_DEV_SCOPES:
                    continue
                own = frozenset(
                    _norm(str(p)) for p in (_get(dev, "paths") or [])
                )
                best_name, best_hit = None, 0
                for name, lpaths in lane_paths:
                    hit = len(own & lpaths)
                    if hit > best_hit:
                        best_name, best_hit = name, hit
                if best_name:
                    dev.product_feature_id = best_name
                    rebound += 1
        tele["devs_rebound_to_lane"] = rebound

    # 5. Shared-resident reasons (validator I22) — every dev still bound
    # to the shared bucket carries a machine-readable reason.
    if shared_reasons_enabled():
        reason_counts: dict[str, int] = {}
        for dev in developer_features:
            pfid = str(_get(dev, "product_feature_id") or "")
            if pfid.strip().lower() not in _SHARED_PF_KEYS:
                continue
            reason = _shared_reason_for(dev, clf)
            dev.shared_reason = reason
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        tele["shared_reasons"] = reason_counts

    return tele, lane, product_features
