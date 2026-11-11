"""Adapter: MCP servers and the tools they serve.

TypeScript::

    const server = new McpServer({ name: "polar", version: "1.0.0" })
    server.registerTool("search_docs", { description: "Search the docs", inputSchema }, handler)

Python::

    mcp = FastMCP("billing")

    @mcp.tool()
    def create_invoice(customer_id: str) -> str:
        \"\"\"Create an invoice for a customer.\"\"\"
"""

from __future__ import annotations

import re

from wystan.pipeline_v2.agents.record import KIND_MCP_SERVER, KIND_TOOL, AgentUnit
from wystan.pipeline_v2.agents.source import SourceFile
from wystan.pipeline_v2.agents.text import balanced, first_string, shallow, string_value

__all__ = ["ADAPTER", "mcp_units", "python_docstring"]

ADAPTER = "mcp-server"
_MENTIONS_MCP = re.compile(r"modelcontextprotocol|McpServer|FastMCP|\bfastmcp\b|\bmcp\b", re.I)
_REGISTER = re.compile(r"""\b(?P<server>\w+)\.(?:registerTool|tool)\(\s*['"`](?P<name>[\w.\-/]{2,80})['"`]\s*,""")
_SERVER_JS = re.compile(r"(?:\b(?:const|let|var)\s+(?P<bound>\w+)\s*=\s*)?new\s+(?:McpServer|Server)\(\s*(?=\{)")
_SERVER_PY = re.compile(r"""^(?P<bound>\w+)\s*=\s*(?:FastMCP|Server)\(\s*(?:name\s*=\s*)?['"](?P<name>[^'"\n]{1,80})['"]""", re.M)
_TOOL_PY = re.compile(
    r"^[ \t]*@(?P<server>\w+)\.tool\([^\n]*\)[ \t]*\n(?:[ \t]*@[^\n]*\n)*[ \t]*(?:async[ \t]+)?def[ \t]+(?P<name>\w+)\(",
    re.M,
)
_DOCSTRING = re.compile(r"""\)\s*(?:->[^:\n]+)?:\s*\n\s*(?:[rRuU]?)(\"\"\"|''')(?P<doc>.*?)\1""", re.S)


def python_docstring(text: str, def_offset: int) -> tuple[str | None, int]:
    """First paragraph of the docstring of the function at ``def_offset`` and
    the offset where the function's header and docstring end."""
    match = _DOCSTRING.search(text, def_offset, def_offset + 4_000)
    if match is None:
        return None, text.find("\n", def_offset) + 1
    paragraph = match.group("doc").strip().split("\n\n")[0]
    return " ".join(paragraph.split()) or None, match.end()


def _config_object(arguments: str) -> str:
    """The top level of the first object literal among a call's arguments."""
    start = shallow(arguments).find("{")
    end = balanced(arguments, start) if start != -1 else None
    return shallow(arguments[start + 1:end - 1]) if end else ""


def _script_units(source: SourceFile) -> list[AgentUnit]:
    units = []
    for match in _SERVER_JS.finditer(source.text):
        end = balanced(source.text, match.end())
        name = string_value(shallow(source.text[match.end() + 1:end - 1]), "name") if end else None
        if end and name:
            units.append(source.unit(KIND_MCP_SERVER, match.start(), end, ADAPTER, name=name, symbol=match.group("bound")))
    for match in _REGISTER.finditer(source.text):
        open_paren = source.text.find("(", match.start())
        end = balanced(source.text, open_paren)
        if end is None:
            continue
        rest = source.text[match.end():end - 1]
        config = _config_object(rest)
        # The author's own words for the tool: its description, else its title.
        description = string_value(config, "description") or string_value(config, "title")
        if description is None and rest.lstrip()[:1] in "'\"`":
            description = first_string(rest)      # positional description
        units.append(source.unit(
            KIND_TOOL, match.start(), end, ADAPTER, name=match.group("name"),
            description=description, owner=match.group("server"), has_handler=True,
        ))
    return units


def _python_units(source: SourceFile) -> list[AgentUnit]:
    units = []
    for match in _SERVER_PY.finditer(source.text):
        units.append(source.unit(
            KIND_MCP_SERVER, match.start(), match.end(), ADAPTER,
            name=match.group("name"), symbol=match.group("bound"),
        ))
    for match in _TOOL_PY.finditer(source.text):
        description, end = python_docstring(source.text, match.end() - 1)
        units.append(source.unit(
            KIND_TOOL, match.start(), end, ADAPTER, name=match.group("name"),
            description=description, symbol=match.group("name"), owner=match.group("server"), has_handler=True,
        ))
    return units


def mcp_units(source: SourceFile) -> list[AgentUnit]:
    """MCP servers and the tools registered on them."""
    if not _MENTIONS_MCP.search(source.text):
        return []
    if source.is_script:
        return _script_units(source)
    if source.is_python:
        return _python_units(source)
    return []
