# Changelog

All notable changes to **Wystan** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This is a curated history of how Wystan evolved from a single-file CLI into a
deterministic-first, two-layer feature-mapping engine with an AI-agent toolkit.

## [Unreleased]

### Removed
- `wystan.yaml` product-feature override. Stage 6.5 no longer reads
  `<repo>/wystan.yaml`, and Stage 8 no longer short-circuits on a customer
  mapping. A `wystan.yaml` in a scanned repository is ignored.
  `scan_meta.product_clusterer_votes_cast` no longer has a `customer-yaml`
  key, and `KEY_SCHEMA_VERSION` is 82. Every profile digest in
  `snapshots.lock.json` is stale until regenerated with
  `python -m wystan.tools.snapshot_gate --update` on a machine that has the
  pinned clones.
- `wystan suggest-config` and the `.wystan.yaml` repository config
  (`wystan/analyzer/repo_config.py`, `wystan/analyzer/auto_alias_discoverer.py`).
  The scan pipeline never read that file.

### Changed
- **API products get a product layer from their schema.** New adapters read
  GraphQL operations composed in code (`entry_points/graphql_schema.py`,
  graphene: root type, group classes, operations, with descriptions from a
  shipped `schema.graphql`) and UI action registries
  (`entry_points/actions.py`). Each group of two or more operations becomes a
  product feature named by the schema ("Checkout", "Gift Card"), taking the
  unowned module that implements its operations, the unowned code its flows
  reach, and the parentless user flows that start there
  (`entry_group_features.py`). A package that registers UI actions is no
  longer barred as `headless_internal_package`.
- **A page-less feature with an API keeps its place.** In a product with
  pages, a feature is removed for having no page only when its own code
  serves fewer than two API operations.
- **Navigation labels are read through the UI catalog.** A row holding a
  catalog key (`event_types_page_title`) is resolved to its text; a key with
  no entry is not used as a name. Catalog files are read up to 8 MB.
- A product feature is no longer renamed into a name a sibling already has.
  `KEY_SCHEMA_VERSION` is 91.
- **Entry points, and command-line tools get a product layer.** A new
  `entry_points` package records what a user can address (a page, a command)
  with the name its author gave it and its declared parent;
  `scan_meta.entry_points` reports them by kind. For command-line tools: a Go
  binary owns the commands its main package imports (the `cmd/<bin>` +
  `pkg/cmd` layout was rejected before); a `cli-tool` unit with detected
  commands keeps its user flows; each command group becomes a product feature
  under the binary's, named by its own description ("Manage pull requests"),
  with `parent_product_feature_id` pointing at the binary's feature; the
  binary's feature takes the root command's description. Names an author
  wrote are no longer judged or removed by the code-name laws.
  `KEY_SCHEMA_VERSION` is 88.
- **A product feature is named by the product, and has a page.** The name
  of a product feature is read from its top page (`authored_names.py`): the
  navigation label that links to it, then the page title, then the first
  heading, then the URL's own word. Directory, package and framework names
  are never used ("Remix" for the share pages is now "Share"). In a product
  that has pages, a feature with no page (an API endpoint, an internal
  package) is removed from `product_features`; its code joins the feature it
  lives under by name or becomes unowned with
  `shared_reason: "unnameable_product_feature"` (`unnameable_demote.py`). A
  user flow with no product-language name is removed from `user_flows`; its
  code flows stay. Counts are in `scan_meta.unnameable_features_removed` and
  `scan_meta.product_language_names.flows_removed`. `KEY_SCHEMA_VERSION` is
  87.
- **The default Sonnet is `claude-sonnet-5-5`.** The `sonnet` alias and every
  stage default (analyst, journey abstraction, adjudicator, splitter,
  discovery, symbol attribution, evolve) moved from `claude-sonnet-4-6`.
  Requests to it send `thinking: {"type": "between_tools"}` and no
  `temperature`; responses are read by block type. Pricing is $2 / $10 per
  million tokens.
- **A flow's entry point is code that does something.** Stage 3 classifies
  every exported TS/JS symbol as behaviour or declaration
  (`analyzer/symbol_behaviour.py`): a type, interface, enum, or a `const`
  whose initializer has no function body is a declaration. Declarations are
  not offered to the LLM as flow candidates, do not count towards the export
  floor, and cannot be an entry point; a flow that lists only declarations is
  dropped with a note. A `const` that wraps a function defined in the same
  file stays a candidate. Other languages are unchanged.
  `KEY_SCHEMA_VERSION` is 86.
- **Product features and user flows are named in product language.** A new
  last pass (`product_language_names`) renames `display_name` of product
  features and `name` of user flows from the text the product shows its
  users: page titles, headings, button labels and translated copy, including
  Lingui `msg` / `<Trans>` and catalog keys (`ui_text.py`). Names must pass
  the product-language laws (`product_name_laws.py`): no route parameters or
  their residue, no glued identifiers, no bare package, directory, framework
  or protocol names; a user flow starts with a user-goal verb. On keyed scans
  an LLM writer proposes names; a proposal is kept only when it passes the
  laws, every word is in the item's evidence, and it shares a word with the
  item's own URLs and code units. A name that breaks a law and cannot be
  replaced keeps its text, gets `name_confidence: "low"` and
  `name_evidence: ["unnameable:<law>"]`; counts are in
  `scan_meta.product_language_names`. Developer feature and code flow names,
  slugs, ids and anchors are unchanged. `KEY_SCHEMA_VERSION` is 85.
- **Every flow node is measured.** Flow expansion no longer emits file nodes
  without a line span. An imported file is represented by the symbols the
  caller references, each with its own span; an import the caller never
  references adds nothing; a reference that cannot be tied to a symbol adds
  one whole-file span with `confidence: "low"`. The
  `WYSTAN_FLOW_SPAN_RECOVERY*` flags are retired (always on). Flow `loc`,
  `line_ranges` and user-flow `loc` grow accordingly. `KEY_SCHEMA_VERSION` 83.
- **Flat-file routes are read as URLs.** A Remix / React Router / TanStack
  route file such as `t.$teamUrl+/documents.$id.edit.tsx` now yields the
  pattern `/t/:teamUrl/documents/:id/edit` (it was the file path). The Stage 1
  route extractor names the feature after the first capability segment
  (`documents`), and a single-letter or scope-word segment before a parameter
  is treated as addressing. `KEY_SCHEMA_VERSION` 84.
- **Code containers do not mint product features.** A directory route anchor
  with a structural name (`components`) and a route under a directory marked
  internal (`_internal+`, `[__x]+`) are barred.
- **RPC routers join the product.** A developer feature without a product
  feature is attached to the product feature whose flows hold a strict
  plurality of `rpc` edges into it (`rpc_router_rehome.py`); the cross-unit
  demote no longer strips such a feature.
- **tRPC calls reach the procedure.** A flow whose code calls
  `trpc.<path>.<verb>()` now includes the procedure's defining symbol and its
  direct callees, linked by a new `FlowEdge.kind` value `rpc`. Routers that
  register procedures through imported identifiers and nested routers are
  resolved (`flow_expansion/trpc_edges.py`).

### Added
- `WYSTAN_SINGLE_PRIMARY_OWNER` (default OFF). When several features keep the
  same file through Stage 2 zero-path protection, only the conflict winner
  keeps `MemberFile.primary=True` for it; the others keep the path with
  `primary=False` and an `evidence` naming the winner.

### Fixed
- `metrics_ownership_gate` docstrings said `history` survives an abstain; the
  code nulls it with the metric family.

## [0.0.2] – 2026-10-30

### Fixed
- `engine_version()` (scan-result cache key) could never read the hatch-dynamic
  version from `pyproject.toml` and silently fell back to installed-dist
  metadata; it now follows `[tool.hatch.version].path` to `__version__`.
- ~40 stale docstrings and comments brought back in line with the code
  (finalize pass list, flags documented "default OFF" after being flipped ON,
  health-curve centre 55%, content-derived lineage ids, four framework
  linkers, every LLM-bearing stage listed in `wystan scan --help`).
- CHANGELOG and `uv.lock` aligned with the 0.0.x version line.

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

## [0.0.1] – 2026-08-24

First release published under the **`wystan`** name. The package was
re-released on PyPI after the rebrand (faultline → dynvo → wystan) and the
public repository was re-initialised, so the version line starts over at
0.0.1: `wystan/__init__.py` is the single source of truth for the version
(`[tool.hatch.version]`), and git tag `v0.0.1` marks this release.

---

## Pre-rebrand history

The entries below record how the engine evolved before it was published as
`wystan`. Those versions shipped under the previous package names and were
never released to PyPI as `wystan`, so they carry no PyPI links.

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

[Unreleased]: https://github.com/PashaSchool/wystan/compare/v0.0.2...HEAD
[0.0.2]: https://pypi.org/project/wystan/0.0.2/
[0.0.1]: https://pypi.org/project/wystan/0.0.1/
