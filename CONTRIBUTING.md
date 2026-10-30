# Contributing to Wystan

Thanks for helping Wystan map codebases better. Bug reports about a stack it
mis-reads are as valuable as code: open an issue with the repo (or a minimal
reproduction), the `wystan` version and the `scan_meta` block from the output.

## Set up

```bash
git clone git@github.com:PashaSchool/wystan.git
cd wystan
uv sync --all-extras          # or: pip install -e '.[ast,watch]'
pre-commit install            # ruff, gitleaks, detect-secrets, hygiene hooks
```

Python 3.11+ is required. `uv` is the supported workflow; the lockfile is
committed.

## Run a scan while developing

```bash
uv run wystan /path/to/some/repo --run-id baseline
```

Every stage writes its output artifact, a JSONL decision log and its exact
input to `~/.wystan/logs/<slug>/<run_id>/`. Without an `ANTHROPIC_API_KEY`
the scan is fully deterministic and costs nothing, which is the right mode
for most pipeline work.

## Iterate on a single stage

Re-run one stage (or the downstream chain) from the recorded artifacts with
your edited code instead of rescanning:

```bash
uv run wystan replay --run <slug>/baseline --stage anchored_mint --through output
```

See [wystan/replay/README.md](wystan/replay/README.md) for the full workflow,
including `--fresh-llm` cache busting and how to diff two runs.

## House rules the code follows

- **Deterministic first.** Membership of files in features comes from code
  conventions and git history. An LLM may name things or classify the
  unclaimed residual, never move membership.
- **No README reads.** Prose is never an input to detection.
- **No magic tuning.** Thresholds are ratios or percentiles of the repo's own
  distribution, not constants tuned to one repository. Never hard-code a
  repo-specific path.
- **Kill switch for every behaviour change.** New behaviour ships behind a
  `WYSTAN_*` flag defaulting OFF, is measured, then flips ON in a numbered
  flip-pack that bumps `KEY_SCHEMA_VERSION` in
  `wystan/pipeline_v2/scan_result_cache.py`. With the flag explicitly `0`
  the output must stay byte-identical to the engine without the feature.
- **Byte-identical output.** Iterate sets in sorted order, derive ids from
  content, collect parallel results in submission order.
- **Docstrings are the changelog.** Keep the sprint/bug tags, and when you
  change behaviour update the docstring in the same commit.

## Pull requests

- Branch from `main`: `feature/…`, `fix/…`, `docs/…`, `chore/…`.
- Conventional commits: `type(scope): subject`, imperative, lowercase.
- One logical change per PR. Explain the motivation and how you verified it;
  for pipeline changes, include before/after numbers from a real scan.
- `pre-commit run --all-files` must pass.

## Releasing

`wystan/__init__.py` is the single source of the version. Bump it, add a
CHANGELOG entry, tag `vX.Y.Z` on `main` and publish a GitHub Release; the
`publish` workflow builds the wheel and uploads it to PyPI through Trusted
Publishing.

## License

By contributing you agree that your contribution is licensed under the
[Functional Source License, v1.1, Apache-2.0 future](LICENSE).
