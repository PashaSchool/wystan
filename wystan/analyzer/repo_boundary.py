"""The boundary of a guarded repository read: the tree the user asked to scan.

Containment is checked against the top-level path the user passed to the scan
(the repository argument), never against anything discovered above it: an
untrusted tree unpacked inside some other repository (a home directory kept in
git, a monorepo checkout) can link only within itself.

* A scan with one root: the boundary is that root. A reader is given the root
  it reads under, and the root is its own boundary.
* Workspace and unit sub-roots inside one scan: their callers pass the scan's
  root as the reader's root (``detect_stack(..., scan_root=...)``), so a link
  from one workspace into another part of the scanned tree reads as on ``dev``.
* A ``--subpath`` scan: the user passes the repository and a subpath; Stage 0
  declares the subtree as part of that repository
  (``declare_subtree(subtree, repository)``), and a read under the subtree is
  bounded by the repository the user passed. The declaration is explicit
  (both paths come from the user), keyed by the exact subtree, and lasts for
  the process: a later scan of exactly that subtree in the same process reads
  links into the repository its user named. Nothing is looked up above a root.
* A subtree scanned directly as the root (no ``--subpath``) is its own
  boundary: a link from it into the rest of the enclosing repository is
  refused, unlike ``dev``, and counted as ``outside_repository`` in
  ``scan_meta.repository_reads``.

The resolved form of a boundary is computed once per process and boundary.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from functools import lru_cache

__all__ = ["Boundary", "boundary_of", "declare_subtree"]

#: Distinct boundaries whose resolved form is remembered per process; a scan
#: has one, a long-lived process scans few repositories at a time.
_BOUNDARIES_REMEMBERED = 1024

_declared: dict[str, str] = {}
_declared_lock = threading.Lock()


@dataclass(frozen=True)
class Boundary:
    """The tree a read must stay in: ``lexical`` is its absolute path as the
    caller spells it, ``real`` the same directory resolved."""

    lexical: str
    real: str


def _absolute(path: os.PathLike[str] | str) -> str:
    return os.path.abspath(os.fspath(path))


def declare_subtree(subtree: os.PathLike[str] | str, repository: os.PathLike[str] | str) -> None:
    """Declare that reads under ``subtree`` (the root of a ``--subpath``
    scan) are bounded by ``repository``, the path the user passed. Refuses a
    subtree that is not inside the repository."""
    inner, outer = _absolute(subtree), _absolute(repository)
    if inner != outer and not inner.startswith(outer.rstrip(os.sep) + os.sep):
        raise ValueError(f"{inner} is not inside the scanned repository {outer}")
    with _declared_lock:
        _declared[inner] = outer


@lru_cache(maxsize=_BOUNDARIES_REMEMBERED)
def _resolved(top: str) -> Boundary:
    return Boundary(lexical=top, real=os.path.realpath(top))


def boundary_of(root: os.PathLike[str] | str) -> Boundary:
    """The boundary of reads under ``root``: the repository declared for it,
    or ``root`` itself (module doc)."""
    absolute = _absolute(root)
    return _resolved(_declared.get(absolute, absolute))
