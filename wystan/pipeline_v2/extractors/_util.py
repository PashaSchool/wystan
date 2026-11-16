"""Shared helpers for Stage 1 extractors.

Kept private (``_util``) — these helpers are not part of the public
extractor contract. Anything an external extractor needs should be
imported from :mod:`wystan.pipeline_v2.extractors.base` instead.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

from wystan.analyzer.repo_reader import MANIFEST_READ_MAX_BYTES, TEXT_READ_MAX_BYTES, read_repo_text_or_raise

if TYPE_CHECKING:
    from wystan.pipeline_v2.stage_0_intake import ScanContext


# ── slug helpers ────────────────────────────────────────────────────────────

_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_SLUG_TRIM_DASH = re.compile(r"^-+|-+$")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def slugify(value: str) -> str:
    """Turn an arbitrary string into a kebab-case slug.

    Splits camelCase (``UserAuth`` → ``user-auth``) and underscores,
    lowercases, collapses runs of non-alphanumerics into single dashes.
    Empty input yields ``""`` (Stage 5 Fix A drops empty names).
    """
    if not value:
        return ""
    # split CamelCase into pieces first so ``UserAPI`` → ``User-API`` →
    # ``user-api`` (rather than ``userapi``)
    spaced = _CAMEL_BOUNDARY.sub("-", value)
    lowered = spaced.lower()
    dashed = _SLUG_NON_ALNUM.sub("-", lowered)
    return _SLUG_TRIM_DASH.sub("", dashed)


# Universal noise tokens — common framework/scaffolding words that, on
# their own, are NEVER a useful feature name. Filtered by extractors
# that derive names from path segments. Kept small and stack-agnostic;
# stack-specific cleaning happens in Stage 5 post-process.
_NOISE_TOKENS = frozenset({
    "src", "app", "pages", "routes", "api", "lib", "libs",
    "components", "component", "shared", "common", "utils", "util",
    "helpers", "helper", "hooks", "config", "configs",
    "controllers", "controller", "models", "model", "views", "view",
    "services", "service", "handlers", "handler", "middleware",
    "internal", "core", "main", "index", "page", "layout", "route",
    "schemas", "schema", "types", "type",
    "public", "private",
})


def is_noise(token: str) -> bool:
    """``True`` if ``token`` is a scaffolding/framework word on its own."""
    return token.lower() in _NOISE_TOKENS


# ── activation-gate helpers ─────────────────────────────────────────────────
#
# Most Stage 1 extractors gate on the same three context fields — the
# Stage 0.5 auditor's primary tag (``ctx.audited_stack``), the Stage 0
# heuristic tag (``ctx.stack``), and the auditor's secondary tags
# (``ctx.secondary_stacks``). These helpers centralise the exact-match
# checks; prefix-style checks (``startswith("go-")``) stay local to the
# extractors that need them.


def is_audited_stack(ctx: "ScanContext", stack: str) -> bool:
    """``True`` iff the auditor declared ``stack`` (primary OR secondary).

    Exact match only — does not consult the Stage 0 heuristic
    ``ctx.stack`` tag. Use :func:`is_any_stack` when the Stage 0 tag
    should also count.
    """
    wanted = stack.lower()
    if (ctx.audited_stack or "").lower() == wanted:
        return True
    return any(
        s.lower() == wanted for s in (ctx.secondary_stacks or ())
    )


def is_any_stack(ctx: "ScanContext", *stacks: str) -> bool:
    """``True`` iff ANY of ``stacks`` matches the audited primary tag,
    the Stage 0 heuristic tag, or an audited secondary tag (exact,
    case-insensitive)."""
    wanted = {s.lower() for s in stacks}
    if (ctx.audited_stack or "").lower() in wanted:
        return True
    if (ctx.stack or "").lower() in wanted:
        return True
    return any(
        s.lower() in wanted for s in (ctx.secondary_stacks or ())
    )


# ── manifest readers ────────────────────────────────────────────────────────

#: Largest source file an extractor reads (the guarded reader's text cap; no
#: tracked file of the corpus comes near it). Manifests and configs are read
#: with the one manifest cap (``MANIFEST_READ_MAX_BYTES``) at every site.
EXTRACTOR_READ_MAX_BYTES = TEXT_READ_MAX_BYTES


def read_json(path: Path, repo_root: Path) -> dict | list | None:
    """Read a JSON file of the repository at ``repo_root`` or return
    ``None`` on any error. Read through the guarded reader
    (``analyzer.repo_reader``): a symlink out of the repository, a FIFO or
    device, or a file over the cap is ``None``, as an unreadable file is."""
    try:  # every JSON an extractor reads is a manifest or config
        return json.loads(read_repo_text_or_raise(path, repo_root, max_bytes=MANIFEST_READ_MAX_BYTES))
    except (OSError, json.JSONDecodeError):  # a bad encoding still raises, as before
        return None


def read_manifest_text(path: Path, repo_root: Path) -> str | None:
    """:func:`read_text` of a manifest or config (``pyproject.toml``,
    ``Cargo.toml``, ``package.json``): the manifest cap."""
    try:
        return read_repo_text_or_raise(path, repo_root, errors="ignore", max_bytes=MANIFEST_READ_MAX_BYTES)
    except OSError:
        return None


def read_text(path: Path, repo_root: Path) -> str | None:
    """Read a text file of the repository at ``repo_root`` or return
    ``None`` on any error; guarded as :func:`read_json`."""
    try:
        return read_repo_text_or_raise(path, repo_root, errors="ignore", max_bytes=EXTRACTOR_READ_MAX_BYTES)
    except OSError:
        return None


# ── path helpers ────────────────────────────────────────────────────────────

def posix(p: str) -> str:
    """Normalise a path string to POSIX separators (``\\`` → ``/``)."""
    return p.replace("\\", "/")


def has_any_suffix(file_path: str, suffixes: tuple[str, ...]) -> bool:
    """``True`` if ``file_path`` ends with any of ``suffixes``."""
    lower = file_path.lower()
    return any(lower.endswith(s) for s in suffixes)


__all__ = [
    "slugify",
    "is_noise",
    "is_audited_stack",
    "is_any_stack",
    "read_json",
    "read_text",
    "posix",
    "has_any_suffix",
]
