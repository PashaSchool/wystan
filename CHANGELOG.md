# Changelog

All notable changes to **Wystan** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This is a curated history of how Wystan evolved from a single-file CLI into a
deterministic-first, two-layer feature-mapping engine with an AI-agent toolkit.

## [Unreleased]

### Changed
- **Flip-pack №46 (KEY_SCHEMA 81) — a published workspace gets to say what
  it is, and a CLI journey has to prove it points at its own code.** Three
  flags default ON under one bump: `WYSTAN_WS_ANCHOR_IDENTITY`,
  `WYSTAN_UNSYNTH_SIBLING_DUP_GUARD` and `WYSTAN_CLI_BIND_GATE`.
  A workspace that ships a binary is a *command surface*, so it is now
  identified by that surface instead of by the directory it happens to sit
  in — the row that used to abstain into the tooling lane wearing the
  repository's own name is emitted as the product it is (trigger.dev's
  `packages/cli-v3` becomes the "Trigger CLI" feature, and 24121 LOC of
  deploy and dev commands come with it), and an npm scope becomes the
  identity when stripping it would leave nothing a customer could read
  (`@novu/js` reads "Novu JS", not "Js"). A rescued CLI journey no longer
  arrives as a duplicate: a row whose only member resolves into a flow
  that a real sibling journey already owns on the same feature stays out
  of the ruler instead of being promoted beside it. And a journey's
  binding now has to hold — a command tied to its member by a single
  shared token is no longer promoted out of the synthesized exclusion, so
  an author's own sentence stops landing over a stranger's file ("Display
  the current logged in user…" over `commands/logout.ts`).
  Command-journey binding precision measured 40.7% → 91.7%. `js` and `rsc`
  are promoted into the shipped acronym table under the same bump.
  Explicit `0` remains the kill-switch for each flag forever.
- **Flip-pack №45 (KEY_SCHEMA 80) — product code stops being filed as
  tooling.** Four flags default ON under one bump:
  `WYSTAN_PUBLISHED_ARTIFACT_VETO`,
  `WYSTAN_SHELL_NAME_CORROBORATION`,
  `WYSTAN_RELEASED_DISPLAY_REGISTRY` and
  `WYSTAN_ABSTAIN_SCOPE_ROLLBACK`. A workspace the maintainer actually
  publishes — `bin` or `publishConfig`, not private, not a Storybook design
  system — is something customers install, so its code now votes *product*
  ahead of the dev-tooling rungs that used to bury it (and delete its CLI
  journeys with it). A feature is no longer demoted to a shell on the
  strength of its NAME alone: when the row owns a real product route the
  container-name short-circuit stands down — the same law the journey layer
  has always applied, now at feature grain. A display name a feature EARNED
  that way can no longer be silently overwritten by a later naming pass
  offering a bare container word, and a scope release that a guard
  ultimately declined to commit now rolls its child rows back to their own
  flag-off verdict instead of leaving them stranded. Explicit `0` remains
  the kill-switch for each flag forever.
- **Flip-pack №44 (KEY_SCHEMA 79) — synthesized journeys stop lying about
  themselves.** `WYSTAN_CLI_JOURNEY_UNSYNTH` and
  `WYSTAN_SYNTH_CONVERSION` now default ON. A world census (55 boards,
  653 `synthesized` rows) showed the rows were not phantoms — every live one
  is member-ful and grounded, and 85.5% earn `high` on their own evidence
  once the B78 confidence cap stops hard-stamping them `low` before Law C
  grades them. Author-declared CLI command journeys (a cobra `Short:` read
  out of the command's own registration site) drop the `synthesized` tag
  outright; every other row must clear three guards — PF-echo refusal, a
  per-PF quota, and a display-doctrine floor — and its verdict is tracked in
  a five-bucket ledger that publishes `sum_ok`. `synthesis_reason` is kept
  throughout: provenance survives, the coverage claim does not.
  Explicit `0` remains the kill-switch for both flags forever.

## [1.0.0] – 2026-06-01

First stable release. The engine and the AI-agent MCP server are now separate,
independently versioned packages.

### Changed
- **Monorepo split.** The repository is now a [uv workspace](https://docs.astral.sh/uv/concepts/workspaces/)
  with two independently published packages: the `wystan` engine and the
  standalone `wystan-mcp` server.
- **MCP extracted to its own engine-free package.** `wystan-mcp` no longer
  depends on the engine — it reads only the feature-map JSON, so a local install
  stays small and fast. The engine **no longer ships the MCP SDK** (the
  `wystan[mcp]` extra is gone; `pip install wystan-mcp` instead).

### Added
- Native `hotspot_files` emitted on every feature, flow and product feature.
- Rewritten project README and this changelog.

### Removed
- Legacy `benchmarks/` harness.

## [0.11.0]

### Changed
- Pinned the LLM analyst to `claude-sonnet-4-6` across the pipeline for stable,
  reproducible naming and flow detection.

### Fixed
- Hermetic runtime-data loading via `importlib.resources` (no more reliance on
  the working directory at scan time).
- Stage 1 now always merges built-in extractors with entry-point plugins, so a
  stale `entry_points.txt` can never silently drop a built-in extractor.

## [0.10.0]

### Added
- **Stage 8.5 — deterministic path-overlap member backfill.** Attaches files to
  the features they belong to by path overlap, lifting attachment coverage
  substantially without an LLM call.
- **Stage 6.9 — test-file output strip.** Test files are detected (token-based
  predicate, catches `*.e2e-spec.ts`, `*.spec`, etc.) and stripped from the
  feature output tree while still feeding coverage.

### Fixed
- FastAPI route extraction and a Django false-positive in Stage 0/1.

## [0.9.0] – [0.9.1]

### Added
- **Stack-aware extraction.** Per-stack pattern library (`eval/stacks/*.yaml`)
  drives route / MVC / schema / package extractors so detection adapts to
  Next.js, Rails, Django, FastAPI, Express, Spring, Laravel, Phoenix and more.
- Flow `short_label` (kebab name without the `-flow` suffix).

### Fixed
- Sonnet model alias corrected to a valid id (was a 404-ing placeholder).

## [0.8.0]

### Added
- **`pipeline_v2` — the two-layer rebuild.** Output now carries
  `developer_features[]` (code-grounded) and `product_features[]`
  (marketing-grounded clusters), plus a top-level `flows[]` array and typed
  feature↔flow edges.
- Deterministic-first staged architecture: intake → parallel extractors →
  anchor reconciliation → flow detection → LLM fallback (residual only) →
  post-process → metrics → output.

## [0.7.0]

### Added
- Scanner flow-detection upgrades: app-layer catch-all splitting, flow dedup,
  noise dropping, CRUD-gap detection and explicit entry-point handling.
- Health, bug-fix-ratio, churn, impact, behavioral coverage and
  ownership / bus-factor metrics wired into the scan output.

## [0.6.0]

### Added
- CLI surface: `--symbols`, `--push`, `refresh`, the human-readable reporter,
  coverage output and the first CI workflow.

## [0.5.0]

### Added
- Infrastructure modules: content-hash LLM cache, change-impact / blast-radius,
  the first MCP server, cloud/replay registry and `--watch` mode.

## [0.4.0]

### Added
- **Symbol-level attribution.** Flows are attributed down to functions and
  classes with line ranges and deterministic role classification
  (handler / validator / type / …), with CRUD-gap enrichment.

## [0.3.0]

### Added
- New Sonnet-based detection pipeline, library (importable) mode and parallel
  workspace scanning.

## [0.2.0] – [0.2.1]

### Added
- Improved feature and flow detection.
- First test suite.

## [0.1.0]

### Added
- Initial Wystan CLI: map features in any codebase from git history alone.

---

[Unreleased]: https://github.com/PashaSchool/wystan/compare/main...HEAD
[1.0.0]: https://pypi.org/project/wystan/1.0.0/
[0.11.0]: https://pypi.org/project/wystan/0.11.0/
[0.10.0]: https://pypi.org/project/wystan/0.10.0/
[0.9.1]: https://pypi.org/project/wystan/0.9.1/
[0.9.0]: https://pypi.org/project/wystan/0.9.0/
[0.8.0]: https://pypi.org/project/wystan/0.8.0/
[0.7.0]: https://pypi.org/project/wystan/0.7.0/
[0.6.0]: https://pypi.org/project/wystan/0.6.0/
[0.5.0]: https://pypi.org/project/wystan/0.5.0/
[0.4.0]: https://pypi.org/project/wystan/0.4.0/
[0.3.0]: https://pypi.org/project/wystan/0.3.0/
[0.2.1]: https://pypi.org/project/wystan/0.2.1/
[0.2.0]: https://pypi.org/project/wystan/0.2.0/
[0.1.0]: https://pypi.org/project/wystan/0.1.0/
