"""Benchmark harness — quantify detection quality against ground truth.

Public surface:

  - :func:`wystan.benchmark.loader.load_expected_features`
  - :func:`wystan.benchmark.loader.load_expected_flows`
  - :func:`wystan.benchmark.loader.load_expected_attribution`

  - :func:`wystan.benchmark.metrics.feature_recall`
  - :func:`wystan.benchmark.metrics.feature_precision`
  - :func:`wystan.benchmark.metrics.flow_recall`
  - :func:`wystan.benchmark.metrics.attribution_accuracy`
  - :func:`wystan.benchmark.metrics.generic_name_rate`

  - :func:`wystan.benchmark.report.render_markdown`

See ``SPRINT_6_PLAN.md`` for design decisions and YAML schema.
"""

from .loader import (
    ExpectedAttribution,
    ExpectedFeature,
    ExpectedFlow,
    load_expected_attribution,
    load_expected_features,
    load_expected_flows,
)
from .metrics import (
    GENERIC_NAME_BLOCKLIST,
    attribution_accuracy,
    feature_precision,
    feature_recall,
    flow_recall,
    generic_name_rate,
)
from .report import render_markdown

__all__ = [
    "ExpectedAttribution",
    "ExpectedFeature",
    "ExpectedFlow",
    "GENERIC_NAME_BLOCKLIST",
    "attribution_accuracy",
    "feature_precision",
    "feature_recall",
    "flow_recall",
    "generic_name_rate",
    "load_expected_attribution",
    "load_expected_features",
    "load_expected_flows",
    "render_markdown",
]
