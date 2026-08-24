"""Replay v2 — per-stage input persistence + isolated stage re-execution.

See ``wystan/replay/README.md`` for the workflow and
:mod:`wystan.replay.runner` for the executor semantics.

The package ``__init__`` stays import-light on purpose: the pipeline
orchestrator imports :mod:`wystan.replay.capture` on its hot path,
and the registry/runner (which import many pipeline stage modules)
must not load then. ``replay`` / ``ReplayReport`` / ``resolve_run_dir``
are exposed lazily.
"""

from typing import Any

from wystan.replay.capture import (
    MissingStageInputError,
    load_stage_input,
    write_stage_input,
)

__all__ = [
    "MissingStageInputError",
    "ReplayReport",
    "load_stage_input",
    "replay",
    "resolve_run_dir",
    "write_stage_input",
]


def __getattr__(name: str) -> Any:
    if name in {"ReplayReport", "replay", "resolve_run_dir"}:
        from wystan.replay import runner as _runner
        return getattr(_runner, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
