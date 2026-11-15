"""The agent-unit record.

An agent unit is something a model addresses instead of a user: an agent, a
tool it can call, a skill or prompt it is given, an MCP server that serves
tools. Adapters produce these records from what the repository declares.
Units are a layer of their own: they are never product features or flows.
"""

from __future__ import annotations

from dataclasses import dataclass

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
]

KIND_AGENT = "agent"
KIND_SUBAGENT = "subagent"
KIND_TOOL = "tool"
KIND_SKILL = "skill"
KIND_PROMPT = "prompt"
KIND_MCP_SERVER = "mcp_server"

SCOPE_PRODUCT = "product"
"""Ships in the product: a model uses it on behalf of the product's users."""
SCOPE_WORKSPACE = "workspace"
"""Instructs a contributor's coding agent; not part of the product."""


@dataclass(frozen=True)
class AgentUnit:
    """One agent, tool, skill, prompt or MCP server, as the repository declares it."""

    kind: str
    file: str
    line: int
    """1-indexed line where the declaration starts."""
    end_line: int
    """1-indexed line where the declaration ends."""
    name: str | None = None
    """The name the author wrote. Tools and skills always have one; an agent
    declared inline (a model call with tools inside a handler) may not."""
    description: str | None = None
    """The author's description, verbatim."""
    scope: str = SCOPE_PRODUCT
    symbol: str | None = None
    """The binding or function the declaration lives in, when known."""
    owner: str | None = None
    """The server or agent object a tool is registered on, as written
    (``server`` in ``server.registerTool(…)``, ``agent`` in ``@agent.tool``)."""
    has_handler: bool = False
    """True when the declaration carries the code that runs on use."""
    adapter: str = ""
    model: str | None = None
    """Model id, only when it is a literal at the declaration."""
    tool_refs: tuple[str, ...] = ()
    """Names an agent lists as its tools, as written. Resolved by the binder."""
    tools_resolved: bool = True
    """False when part of an agent's tool list is built at run time."""

    @property
    def identity(self) -> tuple[str, str, str]:
        return (self.kind, self.file, self.name or f"@{self.line}")
