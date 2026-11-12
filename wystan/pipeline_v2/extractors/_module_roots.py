"""Module roots — where a language's modules sit inside a repository.

A layout convention (``cmd/``, ``internal/``, ``src/`` …) is written
relative to the root of a MODULE, the directory that holds the
language's manifest (``go.mod``, ``Cargo.toml`` …), not relative to the
repository root. The two coincide only when the repository is one
module. An extractor that tests the first segment of the
repository-relative path therefore sees nothing in a module that sits
in a subdirectory.

This helper answers one question for such extractors: "which module
roots enclose this directory?". It reads nothing from disk: the roots
come from the tracked-file list the extractor already holds, so the
work is bounded by that list and cannot leave it (the engine scans
untrusted repositories).

Private (``_module_roots``): not part of the public extractor contract.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from wystan.pipeline_v2.extractors._util import posix

# The repository root as a directory path. Module roots are stored as
# POSIX directory paths without a trailing slash, so the root is "".
REPOSITORY_ROOT = ""

# How many enclosing module roots are reported for one directory,
# counted from the outermost. Real repositories nest modules one or two
# deep (a tools module inside an application module); the cap exists
# only so a hostile tree with a manifest at every level of a very deep
# path costs a constant per file instead of the path depth.
MAX_ENCLOSING_MODULES = 8


def _parent_dir(path: str) -> str:
    """Directory part of a POSIX path (``""`` for a top-level entry)."""
    cut = path.rfind("/")
    return path[:cut] if cut >= 0 else REPOSITORY_ROOT


def manifest_dirs(
    tracked_files: Iterable[str],
    manifest_name: str,
    is_excluded: Callable[[tuple[str, ...]], bool] | None = None,
) -> frozenset[str]:
    """Directories that directly hold a tracked ``manifest_name`` file.

    One pass over ``tracked_files``; nothing is read from disk.
    ``is_excluded`` receives the split path of a manifest and returns
    ``True`` when the manifest must not count (a vendored or fixture
    module is not a module of this repository).
    """
    suffix = "/" + manifest_name
    out: set[str] = set()
    for raw in tracked_files:
        # Cheap reject before any normalisation: most files are not a
        # manifest, and this loop runs over the whole repository.
        if not raw.endswith(manifest_name):
            continue
        path = posix(raw)
        if path != manifest_name and not path.endswith(suffix):
            continue
        if is_excluded is not None and is_excluded(tuple(path.split("/"))):
            continue
        out.add(_parent_dir(path))
    return frozenset(out)


class ModuleLocator:
    """Answers "which module roots enclose this directory?".

    Each directory is resolved once and remembered, and a directory's
    answer is built from its parent's, so resolving every directory of
    a file list costs time linear in the number of distinct directories
    (times the small cap above).
    """

    def __init__(self, roots: Iterable[str]) -> None:
        self._roots = frozenset(roots)
        self._enclosing: dict[str, tuple[str, ...]] = {}

    def _own(self, directory: str) -> tuple[str, ...]:
        return (directory,) if directory in self._roots else ()

    def enclosing(self, directory: str) -> tuple[str, ...]:
        """Module roots at or above ``directory``, outermost first.

        At most :data:`MAX_ENCLOSING_MODULES` roots are returned. The
        repository root is reported only when it is itself a root.
        """
        known = self._enclosing.get(directory)
        if known is not None:
            return known

        # Walk up to the nearest directory already resolved (or the
        # repository root), then fill the answers on the way back down.
        # Iterative on purpose: a hostile path can be thousands of
        # segments deep, which would overflow a recursive walk.
        pending: list[str] = []
        current = directory
        while current not in self._enclosing:
            pending.append(current)
            if current == REPOSITORY_ROOT:
                break
            current = _parent_dir(current)

        if pending[-1] == REPOSITORY_ROOT:
            chain = self._own(pending.pop())
            self._enclosing[REPOSITORY_ROOT] = chain
        else:
            chain = self._enclosing[current]
        for step in reversed(pending):
            if len(chain) < MAX_ENCLOSING_MODULES:
                chain = chain + self._own(step)
            self._enclosing[step] = chain
        return chain


__all__ = [
    "MAX_ENCLOSING_MODULES",
    "REPOSITORY_ROOT",
    "ModuleLocator",
    "manifest_dirs",
]
