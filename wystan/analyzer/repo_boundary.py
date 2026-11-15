"""The boundary of a guarded repository read: the tree the user asked to scan.

Containment is checked against the top-level path the user passed to the scan
(the repository argument), never against anything discovered above it and
never against process state: the boundary travels with the root a reader is
given.

* A scan with one root: the boundary is that root. A reader is given the root
  it reads under, and a plain path is its own boundary.
* Workspace and unit sub-roots inside one scan: their callers pass the scan's
  root as the reader's root (``detect_stack(..., scan_root=...)``), so a link
  from one workspace into another part of the scanned tree reads as on ``dev``.
* A ``--subpath`` scan: the user passes the repository and a subpath. The scan
  context holds both (``ScanContext.repository_root`` beside ``repo_path``),
  and its ``repo_path`` is a ``ScopedRoot``: the subtree's path that also
  names the repository (``scoped_root``). A reader given it as its root is
  bounded by the repository. A path derived from it (``root / rel``,
  ``Path(root)``, ``str(root)``) is a plain path again, so a reader given such
  a derived root is bounded by the subtree: narrower, never wider. A captured
  context that lacks the field (captured before it existed) reads the same
  narrower way; such refusals are counted in ``scan_meta.repository_reads``.
* A subtree scanned directly as the root (no ``--subpath``) is its own
  boundary: a link from it into the rest of the enclosing repository is
  refused, unlike ``dev``, and counted as ``outside_repository``.

The resolved form of a boundary is computed once per process and boundary.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

__all__ = ["Boundary", "ScopedRoot", "boundary_of", "repository_of", "scoped_root"]

#: Distinct boundaries whose resolved form is remembered per process; a scan
#: has one, a long-lived process scans few repositories at a time.
_BOUNDARIES_REMEMBERED = 1024


@dataclass(frozen=True)
class Boundary:
    """The tree a read must stay in: ``lexical`` is its absolute path as the
    caller spells it, ``real`` the same directory resolved."""

    lexical: str
    real: str


class ScopedRoot(type(Path())):  # type: ignore[misc]  # the platform's concrete Path class
    """The root of a ``--subpath`` scan: the subtree's path (it compares,
    hashes and prints as that path) that also names the repository the user
    passed (``repository_root``), the boundary of reads under it."""

    repository_root: Path

    def __reduce__(self):
        # Copies (the stage boundary deep-copies its inputs) keep the
        # repository; pathlib's own reduction would drop it. A path derived
        # from a scoped root (``root / rel``) names no repository and copies
        # as a plain path.
        repository = repository_of(self)
        if repository is None:
            return Path, (str(self),)
        return _scoped, (str(self), str(repository))


def _scoped(subtree: str, repository: str) -> ScopedRoot:
    root = ScopedRoot(subtree)
    root.repository_root = Path(repository)
    return root


def _absolute(path: os.PathLike[str] | str) -> str:
    return os.path.abspath(os.fspath(path))


def scoped_root(subtree: os.PathLike[str] | str, repository: os.PathLike[str] | str) -> Path:
    """``subtree`` as the root of a scan bounded by ``repository`` (the path
    the user passed); a plain path when the two are one directory. Refuses a
    subtree that is not inside the repository."""
    inner, outer = _absolute(subtree), _absolute(repository)
    if inner == outer:
        return Path(subtree)
    if not inner.startswith(outer.rstrip(os.sep) + os.sep):
        raise ValueError(f"{inner} is not inside the scanned repository {outer}")
    return _scoped(os.fspath(subtree), outer)


def repository_of(root: os.PathLike[str] | str) -> Path | None:
    """The repository a ``ScopedRoot`` names, ``None`` for any other root."""
    return getattr(root, "repository_root", None)


@lru_cache(maxsize=_BOUNDARIES_REMEMBERED)
def _resolved(top: str) -> Boundary:
    return Boundary(lexical=top, real=os.path.realpath(top))


def boundary_of(root: os.PathLike[str] | str) -> Boundary:
    """The boundary of reads under ``root``: the repository a ``ScopedRoot``
    names, or ``root`` itself (module doc)."""
    top = repository_of(root)
    raw = os.fspath(root if top is None else top)
    return _resolved(raw if os.path.isabs(raw) and os.path.normpath(raw) == raw else _absolute(raw))
