# Security policy

## Supported versions

Only the latest release on PyPI receives security fixes.

## Reporting a vulnerability

Please do not open a public issue for security problems. Use GitHub's private
vulnerability reporting for this repository:

https://github.com/PashaSchool/wystan/security/advisories/new

Include the `wystan` version, a reproduction and the impact you see. You will
get an acknowledgement within 7 days.

## What Wystan does with your code and keys

- Scans run locally. Source code never leaves your machine unless you opt in
  to the hosted service at wystan.ai.
- With `ANTHROPIC_API_KEY` set, the default stages send structural metadata
  to the Anthropic API: file paths, exported symbol names, route patterns,
  flow names, dependency names and short commit subjects. The opt-in
  journey adjudicator (`WYSTAN_STAGE_6_7E_ADJUDICATOR`, default OFF) also
  sends capped source excerpts as citation evidence. README and other prose
  are never read.
- The LLM decision log under `~/.wystan/training/` stores prompts only as
  SHA-256 hashes. API keys are redacted from every stored artifact.
- Marketing-taxonomy fetches (Stage 8) are guarded against SSRF and only
  follow the homepage declared in `package.json`.
