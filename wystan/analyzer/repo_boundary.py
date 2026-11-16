"""The boundary of a guarded repository read: the root the scan runs on.

One boundary per scan, the same at every call site: the root a reader is given,
which for every read of a scan is the scan's root (``ctx.repo_path``) or, for a
workspace or unit sub-root, the scan's root passed explicitly
(``detect_stack(..., scan_root=...)``). The boundary depends only on the path
of that root: no object, attribute or process state can widen it, and nothing
above the root is ever consulted, so an untrusted tree unpacked inside some
other repository (a home directory kept in git, a monorepo checkout) can link
only within itself.

Differences from ``dev``, accepted:

* A ``--subpath`` scan runs on the subtree, so its boundary is the subtree: a
  link from it into the rest of the repository (``apps/web/src/shared.ts ->
  ../../../lib/x.ts``) is refused, where ``dev`` read it.
* A subtree scanned directly as the root is likewise its own boundary.

Every such refusal is reported in ``scan_meta.repository_reads`` under
``outside_repository``, once per path.

The resolved form of a boundary is computed once per process and boundary.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

__all__ = ["Boundary", "boundary_of"]

#: Distinct boundaries whose resolved form is remembered per process; a scan
#: has one, a long-lived process scans few repositories at a time.
_BOUNDARIES_REMEMBERED = 1024


@dataclass(frozen=True)
class Boundary:
    """The tree a read must stay in: ``lexical`` is its absolute path as the
    caller spells it, ``real`` the same directory resolved."""

    lexical: str
    real: str


@lru_cache(maxsize=_BOUNDARIES_REMEMBERED)
def _resolved(top: str) -> Boundary:
    return Boundary(lexical=top, real=os.path.realpath(top))


def boundary_of(root: os.PathLike[str] | str) -> Boundary:
    """The boundary of reads under ``root``: ``root`` itself, by its path
    alone (module doc)."""
    raw = os.fspath(root)
    return _resolved(raw if os.path.isabs(raw) and os.path.normpath(raw) == raw else os.path.abspath(raw))
