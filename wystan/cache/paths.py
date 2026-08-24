"""Base-directory resolution for engine-local state.

The engine writes scan artifacts, run logs, and (for the default
filesystem cache backend) cache files under a single base directory.

Historically this was hardcoded to ``Path.home() / ".wystan"``.
On scale-to-zero hosted workers ``$HOME`` is shared / ephemeral and
per-tenant state on a shared host is a hazard, so the base dir is now
resolved from the ``WYSTAN_RUN_DIR`` environment variable when the
worker sets it (typically ``tempfile.mkdtemp()`` per job), falling back
to ``~/.wystan`` only when the env is absent (dev / CLI / OSS).

This is the single source of truth — output writers, run-dir helpers,
and the filesystem cache backend all call ``wystan_base_dir()`` so
"where does the engine write" is decided in exactly one place.

No LLM. No network. Pure path resolution.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Env var the hosted worker sets to a job-scoped temp dir so nothing
#: lands under ``$HOME``. Absent in dev → fall back to ``~/.wystan``.
RUN_DIR_ENV = "WYSTAN_RUN_DIR"


def wystan_base_dir() -> Path:
    """Return the engine's base state directory.

    ``$WYSTAN_RUN_DIR`` when set + non-empty, else
    ``~/.wystan``. The directory is NOT created here — callers
    create the specific subpaths they need.
    """
    override = os.environ.get(RUN_DIR_ENV, "").strip()
    if override:
        return Path(override)
    return Path.home() / ".wystan"


__all__ = ["RUN_DIR_ENV", "wystan_base_dir"]
