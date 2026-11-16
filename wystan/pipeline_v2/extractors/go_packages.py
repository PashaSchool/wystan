"""GoPackageExtractor — Go directory conventions → structural anchors.

The Go ecosystem encodes feature boundaries in the directory layout,
not in decorators or manifests. The de-facto "standard project layout"
gives us a deterministic map of the codebase:

  * ``cmd/<name>/...``      — one binary / entry-point per first-level dir.
  * ``internal/<name>/...`` — private application/library packages.
  * ``pkg/<name>/...``      — public library packages.
  * ``modules/<name>/...``  — plugin-style module groupings (caddy).
  * ``apps/<name>/...``     — app groupings in some monorepos.
  * top-level packages      — any repo-root directory that DIRECTLY
                              holds ≥1 non-test ``.go`` file and isn't
                              already covered above.

``GoRouterExtractor`` only sees the HTTP-route surface, so the bulk of a
Go repo (``cmd/``, ``internal/``, ``pkg/``, top-level packages) falls to
the Stage-4 LLM residual path — pushing Go ``llm_fallback_pct`` to ~50%.
This extractor closes that gap with ZERO LLM cost by emitting one anchor
per Go "feature unit" derived purely from directory structure.

Path-ownership rule (documented choice):
  * For the convention prefixes (``cmd``/``internal``/``pkg``/
    ``modules``/``apps``) we group at the FIRST level under the prefix
    and claim every ``.go`` file RECURSIVELY beneath that first-level
    dir. This keeps deep package trees (e.g. ``internal/auth/oauth/...``)
    coherent under a single ``auth`` anchor rather than exploding into
    micro-anchors.
  * For top-level repo-root packages we claim only the directory's OWN
    ``.go`` files (non-recursive). A repo-root dir is a Go package in
    its own right; its subdirectories are independent packages that, if
    they matter, surface as their own top-level/convention anchors. This
    bounds the anchor count and keeps each anchor a single coherent
    package.

Module roots (why the layout is not read from the repository root only):
  * The conventions above are written relative to the root of a Go
    MODULE, the directory holding ``go.mod``. A repository whose Go code
    is one module in a subdirectory (``<dir>/go.mod`` beside a front
    end), or that holds several modules, has no file whose
    repository-relative path starts with ``cmd``/``internal``/…; read
    from the repository root alone, such a module gets no anchor at all.
  * So there are two rules. The REPOSITORY-ROOT rule is the historical
    one, untouched: same gate, same buckets, same names, same order, and
    its anchors carry ``scope == ""``. The NESTED rule is the addition:
    a file the root rule did not bucket is offered to every directory
    below the repository root that holds a tracked ``go.mod`` and
    encloses it, outermost first; the first whose layout gives it a
    bucket owns it, and the anchor carries that directory as ``scope``.
    ``scope != ""`` therefore means exactly "a unit this extractor did
    not emit before nested modules were read", which is what later
    stages need to leave every older row as it was (``module_scope``).
  * A top-level directory that holds a ``go.mod`` and Go files is the
    root rule's "top-level package" on a Go repository, as before, and
    shares its unit with ``cmd/<same name>`` as before.
  * A nested module's own root package (``<module>/main.go``), where the
    root rule does not apply, anchors under the module directory's name.
  * Names. A unit of the root rule keeps its bare slug. A unit of the
    nested rule keeps its bare slug too when no other unit of this
    extractor has it; when two units share a slug (two modules each
    with ``internal/auth``), every nested one is qualified with its
    module: ``<module dir name>-<unit>``, then ``<module path>-<unit>``,
    then a number — the first that is free. Units of different modules
    are never merged into one anchor.
  * Discovery reads only the tracked-file list (see ``_module_roots``).

Noise exclusion: ``vendor/``, ``testdata/``, ``examples/`` / ``example/``,
``docs/``, ``.git/``, ``third_party/``, ``node_modules/`` are dropped, as
are directories whose ONLY ``.go`` files are ``*_test.go`` (test-only) or
generated (``*.pb.go`` / ``*_gen.go``).

Activation gate, one per rule. The repository-root rule fires on
Go-shaped repos only (same stack check as ``go_router``): a ``go.mod`` at
the repository root is not a second way in, so a repository without a
nested module gets exactly what it got before. The nested rule fires for
every tracked ``go.mod`` below the repository root and outside the noise
directories and the test and fixture trees (``validation.is_test_file``)
— that manifest is the proof that a Go module lives there,
whatever the repository's primary stack is. With neither, ``[]`` — never
raises for the "doesn't apply" case.

No LLM. No network. Pure file-system index walk + path arithmetic.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Iterable
from typing import TYPE_CHECKING

from wystan.analyzer.validation import is_test_file
from wystan.pipeline_v2.extractors._module_roots import (
    REPOSITORY_ROOT,
    ModuleLocator,
    first_free_name,
    manifest_dirs,
    qualified_unit_names,
)
from wystan.pipeline_v2.extractors._util import is_any_stack, posix, slugify
from wystan.pipeline_v2.extractors.base import AnchorCandidate

if TYPE_CHECKING:
    from wystan.pipeline_v2.stage_0_intake import ScanContext


logger = logging.getLogger(__name__)


# ── Tunables ────────────────────────────────────────────────────────────────

# Structural anchors carry medium confidence — they reflect a real Go
# convention but, unlike a parsed route, no in-file signal confirms the
# directory is a coherent feature.
_STRUCTURAL_CONFIDENCE = 0.7

# Directory-name prefixes that group at their FIRST level. Order matters
# only for the rationale label; ownership is unambiguous (a file lives
# under exactly one prefix).
_CONVENTION_PREFIXES: tuple[tuple[str, str], ...] = (
    ("cmd", "go cmd/ binary"),
    ("internal", "go internal package"),
    ("pkg", "go pkg/ package"),
    ("modules", "go module group"),
    ("apps", "go app group"),
)

# The manifest that marks the root of a Go module. Its directory, not
# the repository root, is what the layout conventions are relative to.
_MODULE_MANIFEST = "go.mod"

# Rationale of the anchor for a nested module's own root package.
_MODULE_ROOT_RATIONALE = "go module root package"

# Above this many anchors the extractor is probably over-splitting; it
# only warns. 60 is roughly twice the unit count of the largest
# single-module Go repository in the regression corpus.
_OVERSPLIT_WARN_THRESHOLD = 60

# A file of a top-level package is exactly ``<dir>/<file>.go``.
_TOP_LEVEL_PACKAGE_PARTS = 2

# Path segments that mark a directory as noise — never a feature.
_EXCLUDED_SEGMENTS = frozenset({
    "vendor",
    "testdata",
    "examples",
    "example",
    "docs",
    ".git",
    "third_party",
    "node_modules",
})


# ── Activation gate (mirrors go_router._is_go_repo) ─────────────────────────


def _is_go_repo(ctx: "ScanContext") -> bool:
    """``True`` if any signal indicates this repo is Go-shaped."""
    if is_any_stack(ctx, "go"):
        return True
    if (ctx.audited_stack or "").lower().startswith("go-"):
        return True
    secondaries = tuple(s.lower() for s in (ctx.secondary_stacks or ()))
    return any(s.startswith("go-") for s in secondaries)


# ── Path classification ─────────────────────────────────────────────────────


def _is_excluded_path(parts: tuple[str, ...]) -> bool:
    """``True`` if any path segment marks the file as noise."""
    return any(seg in _EXCLUDED_SEGMENTS for seg in parts)


def _is_test_file(leaf: str) -> bool:
    """``True`` for Go test files (``*_test.go``)."""
    return leaf.endswith("_test.go")


def _is_generated_file(leaf: str) -> bool:
    """``True`` for common generated Go files (protobuf / codegen)."""
    return leaf.endswith(".pb.go") or leaf.endswith("_gen.go")


def _bucket_key(parts: tuple[str, ...]) -> tuple[str, str, str] | None:
    """Classify a ``.go`` file path into ``(slug, leaf_name, rationale)``.

    ``parts`` is the POSIX-split repo-relative path (``("internal",
    "auth", "oauth", "x.go")``). Returns ``None`` when the path holds no
    coherent package directory (e.g. a bare repo-root ``.go`` file, which
    is handled by the caller's root bucket rule — see below).
    """
    if len(parts) < 2:
        # Repo-root ``.go`` file — no directory. Handled separately so it
        # never silently vanishes; the caller maps it to ``root``.
        return None

    head = parts[0]
    for prefix, rationale in _CONVENTION_PREFIXES:
        if head == prefix and len(parts) >= 3:
            # cmd/<name>/.../file.go → group on <name>, recursive.
            leaf = parts[1]
            return slugify(leaf), leaf, rationale

    # Top-level repo-root package: own files only (non-recursive). Such a
    # file has exactly two parts: ("<dir>", "file.go").
    if len(parts) == _TOP_LEVEL_PACKAGE_PARTS:
        leaf = parts[0]
        return slugify(leaf), leaf, "go top-level package"

    # Deeper file under a non-convention top-level dir — owned by the
    # nested package, which surfaces (if at all) via its own top-level
    # entry. We intentionally do NOT claim it to keep anchors coherent.
    return None


def _is_product_file(path: str, leaf: str, *, is_nested: bool) -> bool:
    """``True`` for a file that makes its unit a feature unit.

    A unit holding only test or generated files is never emitted. For
    the repository-root rule "test" stays what it was (``*_test.go``),
    so that rule emits what it emitted. The nested rule is new and
    takes the engine's one definition (``validation.is_test_file``),
    which also knows test and fixture TREES: ``<module>/mocks/*.go``
    is not a unit of the product.
    """
    if _is_generated_file(leaf):
        return False
    return not (is_test_file(path) if is_nested else _is_test_file(leaf))


# ── Module-relative classification ──────────────────────────────────────────

# A unit is identified by the root it was bucketed under and its slug, so
# equal slugs in different modules stay different units.
_UnitKey = tuple[str, str]


def _module_bucket(
    parts: tuple[str, ...], module_root: str,
) -> tuple[str, str, str] | None:
    """Classify a file relative to the nested module root that encloses it.

    The same layout rule as :func:`_bucket_key`, applied to the path
    below ``module_root``. A file directly in the module directory is
    the module's root package: it anchors under the directory's name.
    """
    root_parts = tuple(module_root.split("/"))
    below = parts[len(root_parts):]
    if len(below) == 1:
        leaf = root_parts[-1]
        return slugify(leaf), leaf, _MODULE_ROOT_RATIONALE
    return _bucket_key(below)


def _place(
    parts: tuple[str, ...], locator: ModuleLocator, root_rule_active: bool,
) -> tuple[str, tuple[str, str, str]] | None:
    """``(root, bucket)``: the rule and root that bucket a file.

    The repository-root rule is tried first and its answer is final, so
    every file it claims is claimed exactly as before nested modules
    were read (``root`` is then :data:`REPOSITORY_ROOT`, also for a
    top-level directory that holds a ``go.mod``: that unit existed
    before, under that name, and may share it with ``cmd/<name>``).
    Only a file the root rule leaves — or every file, when the root rule
    is off because the repository is not Go-shaped — goes to the nested
    modules that enclose it, outermost first.
    """
    if root_rule_active:
        key = _bucket_key(parts)
        if key is not None:
            return REPOSITORY_ROOT, key
    for module_root in locator.enclosing("/".join(parts[:-1])):
        key = _module_bucket(parts, module_root)
        if key is not None:
            return module_root, key
    return None


def _anchor_names(keys: list[_UnitKey]) -> dict[_UnitKey, str]:
    """Anchor name per unit; equal slugs of different modules stay apart.

    Repository-root units always keep their bare slug (that is what the
    extractor emitted before modules were considered). A nested unit
    keeps its bare slug when it is the only unit with it; otherwise it
    is qualified with its module. ``keys`` is processed in sorted order
    so the outcome does not depend on the order files were listed in.
    """
    shared = Counter(slug for _root, slug in keys)
    names: dict[_UnitKey, str] = {}
    contested: list[_UnitKey] = []
    for key in sorted(keys):
        root, slug = key
        if root == REPOSITORY_ROOT or shared[slug] == 1:
            names[key] = slug
        else:
            contested.append(key)
    taken = set(names.values())
    next_ordinal: dict[str, int] = {}
    for key in contested:
        name = first_free_name(qualified_unit_names(*key), taken, next_ordinal)
        names[key] = name
        taken.add(name)
    return names


def nested_module_roots(tracked_files: "Iterable[str]") -> frozenset[str]:
    """Directories below the repository root that hold a Go module.

    The roots the nested rule reads a layout from. The repository root
    is never one of them: a module there is read by the root rule.
    """
    roots = manifest_dirs(tracked_files, _MODULE_MANIFEST, _is_not_a_module)
    return roots - {REPOSITORY_ROOT}


def _is_not_a_module(manifest_parts: tuple[str, ...]) -> bool:
    """``True`` for a manifest that does not open a module of the product.

    A ``go.mod`` in a vendored, example or documentation tree
    (:data:`_EXCLUDED_SEGMENTS`) or in a test or fixture tree is input
    of a build or of a test, not a module the repository ships. "Test
    tree" is the engine's one definition, ``validation.is_test_file``
    (the one the ``route`` extractor filters Stage 1 with), not a list
    kept here.
    """
    return _is_excluded_path(manifest_parts) or is_test_file(
        "/".join(manifest_parts),
    )


# ── Extractor ───────────────────────────────────────────────────────────────


class GoPackageExtractor:
    """Go directory-convention parser. One anchor per Go feature unit.

    Implements the :class:`AnchorExtractor` Protocol. Emits structural
    anchors for ``cmd/``, ``internal/``, ``pkg/``, ``modules/``,
    ``apps/`` first-level dirs plus top-level packages, read from the
    repository root and from every enclosing Go module root. Pure
    structure — no file contents are read, no LLM, no network.
    """

    name = "go-package"

    def extract(self, ctx: "ScanContext") -> list[AnchorCandidate]:
        # Two gates, one per rule (see the module docstring). A manifest
        # at the repository root opens neither: the root rule keeps its
        # historical stack gate, the nested rule needs a module below
        # the root.
        root_rule_active = _is_go_repo(ctx)
        nested_roots = nested_module_roots(ctx.tracked_files)
        if not root_rule_active and not nested_roots:
            return []

        units = self._collect_units(
            ctx.tracked_files, ModuleLocator(nested_roots), root_rule_active,
        )
        out = self._build_anchors(units)

        if len(out) > _OVERSPLIT_WARN_THRESHOLD:
            logger.warning(
                "go-package emitted %d anchors (>%d) — possible over-split",
                len(out),
                _OVERSPLIT_WARN_THRESHOLD,
            )
        return out

    @staticmethod
    def _collect_units(
        tracked_files: list[str], locator: ModuleLocator,
        root_rule_active: bool,
    ) -> dict[_UnitKey, dict]:
        """Group ``.go`` files into units keyed by ``(root, slug)``.

        ``real`` flips True once a unit holds a non-test, non-generated
        file (:func:`_is_product_file`), so test-only / codegen-only
        directories are dropped later.
        """
        units: dict[_UnitKey, dict] = {}
        for rel_path in tracked_files:
            if not rel_path.endswith(".go"):
                continue
            norm = posix(rel_path)
            parts = tuple(norm.split("/"))
            if _is_excluded_path(parts):
                continue
            placed = _place(parts, locator, root_rule_active)
            if placed is None:
                continue
            root, (slug, _leaf, rationale) = placed
            if not slug:
                continue
            unit = units.setdefault(
                (root, slug),
                {"paths": set(), "rationale": rationale, "real": False},
            )
            unit["paths"].add(norm)
            unit["rationale"] = rationale
            if _is_product_file(norm, parts[-1], is_nested=bool(root)):
                unit["real"] = True
        return units

    def _build_anchors(
        self, units: dict[_UnitKey, dict],
    ) -> list[AnchorCandidate]:
        """One anchor per real unit; repository-root units come first.

        A unit whose only ``.go`` files are tests or generated is never
        a feature, and is left out before names are decided so it cannot
        force a real unit to be qualified.
        """
        real = {key: unit for key, unit in units.items() if unit["real"]}
        names = _anchor_names(list(real))
        # Units of the repository-root rule keep their historical
        # (first-seen) order; the others follow, sorted, so the list is
        # stable.
        ordered = [key for key in real if key[0] == REPOSITORY_ROOT]
        ordered += sorted(key for key in real if key[0] != REPOSITORY_ROOT)
        out: list[AnchorCandidate] = []
        for key in ordered:
            unit = real[key]
            out.append(
                AnchorCandidate(
                    name=names[key],
                    paths=tuple(sorted(unit["paths"])),
                    source=self.name,
                    confidence_self=_STRUCTURAL_CONFIDENCE,
                    rationale=unit["rationale"],
                    # The root the layout was read from: later stages
                    # treat the name as unique inside it only.
                    scope=key[0],
                ),
            )
        return out


__all__ = ["GoPackageExtractor", "nested_module_roots"]
