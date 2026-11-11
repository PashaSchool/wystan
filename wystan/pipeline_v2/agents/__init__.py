"""Agent units: what a model can address in a repository."""

from wystan.pipeline_v2.agents.collect import agent_report, collect_agent_units
from wystan.pipeline_v2.agents.record import (
    KIND_AGENT,
    KIND_MCP_SERVER,
    KIND_PROMPT,
    KIND_SKILL,
    KIND_SUBAGENT,
    KIND_TOOL,
    SCOPE_PRODUCT,
    SCOPE_WORKSPACE,
    AgentUnit,
)

__all__ = [
    "KIND_AGENT",
    "KIND_MCP_SERVER",
    "KIND_PROMPT",
    "KIND_SKILL",
    "KIND_SUBAGENT",
    "KIND_TOOL",
    "SCOPE_PRODUCT",
    "SCOPE_WORKSPACE",
    "AgentUnit",
    "agent_report",
    "collect_agent_units",
]
