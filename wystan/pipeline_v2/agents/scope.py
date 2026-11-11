"""Which population a unit belongs to, and which files are never read.

Two rules, both about the path and nothing else:

* a file under a dot-directory (``.claude/``, ``.agents/``, ``.github/``…)
  configures a contributor's tools, so its units are workspace units;
* an instruction file (a skill or agent written as Markdown) that no shipped
  package contains is a workspace unit too.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from wystan.analyzer.validation import is_documentation_file, is_test_file
from wystan.pipeline_v2.agents.record import SCOPE_PRODUCT, SCOPE_WORKSPACE

__all__ = ["is_excluded", "scope_of"]

_EXAMPLE_SEGMENTS = frozenset({"example", "examples", "sample", "samples", "demo", "demos", "playground"})
_VENDORED_SEGMENTS = frozenset({"node_modules", "vendor", "dist", "build", ".next", "site-packages"})
_MANIFESTS = ("package.json", "pyproject.toml", "setup.py", "go.mod", "Cargo.toml")


def is_excluded(rel: str) -> str | None:
    """Why ``rel`` is not read for product code units, or ``None``."""
    segments = set(PurePosixPath(rel).parts[:-1])
    if segments & _VENDORED_SEGMENTS:
        return "vendored"
    if is_test_file(rel):
        return "test"
    if segments & _EXAMPLE_SEGMENTS or is_documentation_file(rel):
        return "example"
    return None


def _in_dot_directory(rel: str) -> bool:
    return any(part.startswith(".") and part not in (".", "..") for part in PurePosixPath(rel).parts[:-1])


def scope_of(rel: str, tracked: frozenset[str], *, instruction_file: bool = False) -> str:
    """``workspace`` or ``product`` for a unit declared in ``rel``."""
    if _in_dot_directory(rel):
        return SCOPE_WORKSPACE
    if not instruction_file:
        return SCOPE_PRODUCT
    # An instruction file ships only when a package below the root holds it.
    for parent in list(PurePosixPath(rel).parents)[:-2]:
        if any(f"{parent}/{manifest}" in tracked for manifest in _MANIFESTS):
            return SCOPE_PRODUCT
    return SCOPE_WORKSPACE
