"""Entry points: what a user can address in a product."""

from wystan.pipeline_v2.entry_points.collect import collect_entry_points, entry_report
from wystan.pipeline_v2.entry_points.record import (
    KIND_ACTION,
    KIND_COMMAND,
    KIND_OPERATION,
    KIND_PAGE,
    EntryPoint,
)

__all__ = [
    "KIND_ACTION",
    "KIND_COMMAND",
    "KIND_OPERATION",
    "KIND_PAGE",
    "EntryPoint",
    "collect_entry_points",
    "entry_report",
]
