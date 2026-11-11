"""Adapter: agent frameworks (LangChain, LangGraph, OpenAI Agents, CrewAI…).

Tools::

    @tool
    def refund_order(order_id: str) -> str:
        \"\"\"Refund an order in full.\"\"\"

    new DynamicStructuredTool({ name: "refund_order", description: "…", schema, func })
    tool(async ({ id }) => …, { name: "refund_order", description: "…", schema })

Agents::

    support = Agent(name="Support", instructions="…", tools=[refund_order])
    const agent = createReactAgent({ llm, tools: [refundOrder] })

A class the repository itself calls ``Agent`` is implementation, not an
agent: only a construction that passes a name, instructions or tools counts.
"""

from __future__ import annotations

import re

from wystan.pipeline_v2.agents.ai_sdk import enclosing_symbol, tool_refs
from wystan.pipeline_v2.agents.mcp_server import python_docstring
from wystan.pipeline_v2.agents.record import KIND_AGENT, KIND_TOOL, AgentUnit
from wystan.pipeline_v2.agents.source import SourceFile
from wystan.pipeline_v2.agents.text import balanced, shallow, string_value

__all__ = ["ADAPTER", "framework_units"]

ADAPTER = "agent-framework"
_PY_TOOL = re.compile(
    r"^[ \t]*@(?:(?P<owner>\w+)\.)?(?:tool(?:_plain)?|function_tool)\b(?!\.)[^\n]*\n(?:[ \t]*@[^\n]*\n)*[ \t]*(?:async[ \t]+)?def[ \t]+(?P<name>\w+)\(",
    re.M,
)
_PY_TOOL_IMPORT = re.compile(r"^\s*(?:from\s+\S+\s+import\s+[^\n]*\b(?:tool|function_tool)\b|import\s+(?:langchain|agents|crewai|smolagents|llama_index)\b)", re.M)
_PY_TOOL_CLASS = re.compile(r"^class\s+(?P<cls>\w+)\((?:[\w.]+\.)?(?:BaseTool|StructuredTool)\)\s*:", re.M)
_JS_TOOL_CLASS = re.compile(r"\bclass\s+(?P<cls>\w+)\s+extends\s+(?:StructuredTool|DynamicStructuredTool|Tool)\b[^{]*(?=\{)")
_JS_TOOL_NEW = re.compile(r"(?:\b(?:const|let|var)\s+(?P<bound>\w+)\s*=\s*)?new\s+(?:DynamicStructuredTool|DynamicTool)\(\s*(?=\{)")
# LangChain's `tool(fn, { name, description, schema })`: the function comes first.
_JS_TOOL_FN = re.compile(r"(?:\b(?:const|let|var)\s+(?P<bound>\w+)\s*=\s*)?\btool\((?=\s*(?:async\b|\(|function\b))")
_JS_LANGCHAIN = re.compile(r"""['"]@?langchain[\w/@.-]*['"]|['"]@langchain/[\w/.-]+['"]""")
_AGENT_FACTORY = re.compile(
    r"(?:\b(?:const|let|var)\s+)?(?:(?P<bound>\w+)\s*(?::[^=\n]{0,60})?=\s*)?(?:await\s+)?"
    r"\b(?P<factory>createReactAgent|create_react_agent|createAgent|create_agent|createToolCallingAgent|"
    r"create_tool_calling_agent|create_openai_tools_agent|initialize_agent|AgentExecutor|AssistantAgent|Agent)\((?!\s*\))",
)
# `Agent(` is an ordinary word (an HTTP agent, a sales agent): it only counts in
# a file that imports an agent library.
_AGENT_LIBRARY = re.compile(
    r"""(?:from|import|require\()\s*\(?\s*['"]?(?:@openai/agents|@mastra/[\w-]+|@langchain/[\w/-]+|langchain[\w.]*|langgraph[\w.]*|"""
    r"""agents|openai_agents|crewai|autogen[\w.]*|pydantic_ai|llama_index[\w.]*|smolagents|ai|@ai-sdk/[\w-]+|@[\w-]+/agents)\b""",
)
_GENERIC_FACTORIES = frozenset({"Agent", "AssistantAgent"})
_AGENT_KEYS = re.compile(r"(?<![\w.])(?:name|instructions|system_prompt|systemPrompt|tools|role|goal)\s*[:=]")
_MODEL = re.compile(r"""\bmodel\s*[:=]\s*(?:[\w.]+\(\s*)?['"]([\w.:/\-]+)['"]""")
_NAME_ATTR = re.compile(r"""\bname\s*(?::\s*\w+\s*)?=\s*['"]([\w.\- ]{2,80})['"]""")
_CLASS_BODY = 3_000


def _python_tools(source: SourceFile) -> list[AgentUnit]:
    units = []
    imported = bool(_PY_TOOL_IMPORT.search(source.text))
    library = bool(_AGENT_LIBRARY.search(source.text))
    for match in _PY_TOOL.finditer(source.text):
        # `@tool` needs the decorator imported; `@agent.tool` needs an agent library.
        if not (library if match.group("owner") else imported):
            continue
        description, end = python_docstring(source.text, match.end() - 1)
        units.append(source.unit(
            KIND_TOOL, match.start(), end, ADAPTER, name=match.group("name"),
            description=description, symbol=match.group("name"), owner=match.group("owner"), has_handler=True,
        ))
    for match in _PY_TOOL_CLASS.finditer(source.text):
        body = source.text[match.end():match.end() + _CLASS_BODY]
        name = _NAME_ATTR.search(body)
        if name:
            units.append(source.unit(
                KIND_TOOL, match.start(), match.end(), ADAPTER, name=name.group(1),
                description=string_value(body, "description"), symbol=match.group("cls"), has_handler=True,
            ))
    return units


def _script_tools(source: SourceFile) -> list[AgentUnit]:
    units = []
    for match in _JS_TOOL_NEW.finditer(source.text):
        end = balanced(source.text, match.end())
        body = shallow(source.text[match.end() + 1:end - 1]) if end else ""
        name = string_value(body, "name")
        if name:
            units.append(source.unit(
                KIND_TOOL, match.start(), end or match.end(), ADAPTER, name=name,
                description=string_value(body, "description"),
                symbol=match.group("bound") or enclosing_symbol(source.text, match.start()), has_handler=True,
            ))
    for match in _JS_TOOL_CLASS.finditer(source.text):
        end = balanced(source.text, match.end())
        body = source.text[match.end():end] if end else ""
        name = _NAME_ATTR.search(body)
        if name:
            units.append(source.unit(
                KIND_TOOL, match.start(), end or match.end(), ADAPTER, name=name.group(1),
                description=string_value(body, "description"), symbol=match.group("cls"), has_handler=True,
            ))
    if _JS_LANGCHAIN.search(source.text):
        for match in _JS_TOOL_FN.finditer(source.text):
            open_paren = source.text.find("(", match.end() - 1)
            end = balanced(source.text, open_paren)
            call = source.text[open_paren + 1:end - 1] if end else ""
            # The options object is the call's last argument.
            top = shallow(call)
            last = top.rfind("{")
            close = balanced(call, last) if last != -1 else None
            options = shallow(call[last + 1:close - 1]) if close else ""
            name = string_value(options, "name")
            if name:
                units.append(source.unit(
                    KIND_TOOL, match.start(), end or match.end(), ADAPTER, name=name,
                    description=string_value(options, "description"),
                    symbol=match.group("bound") or enclosing_symbol(source.text, match.start()), has_handler=True,
                ))
    return units


def _list_refs(arguments: str) -> tuple[tuple[str, ...], bool, bool]:
    """Tool names of a Python ``tools=[a, b]`` keyword, or of a script's ``tools`` key."""
    keyword = re.search(r"(?<![\w.])tools\s*=\s*(?P<open>\[)?", arguments)
    if keyword is None:
        return tool_refs(arguments)
    if not keyword.group("open"):
        return (), False, True
    end = balanced(arguments, keyword.end() - 1)
    inner = arguments[keyword.end():end - 1] if end else ""
    names = [part.strip() for part in inner.split(",") if part.strip()]
    plain = [name for name in names if re.fullmatch(r"[\w.]+", name)]
    return tuple(dict.fromkeys(name.rsplit(".", 1)[-1] for name in plain)), len(plain) == len(names), True


def _agents(source: SourceFile) -> list[AgentUnit]:
    units = []
    library = bool(_AGENT_LIBRARY.search(source.text))
    for match in _AGENT_FACTORY.finditer(source.text):
        if source.text[max(0, match.start() - 6):match.start()].rstrip().endswith(("class", "def", "function")):
            continue                              # a definition, not a construction
        open_paren = source.text.find("(", match.end() - 1)
        end = balanced(source.text, open_paren)
        if end is None:
            continue
        arguments = source.text[open_paren + 1:end - 1]
        # A single options object: read its top level, not the call's.
        if arguments.lstrip()[:1] == "{" and (close := balanced(arguments, arguments.find("{"))):
            arguments = arguments[arguments.find("{") + 1:close - 1]
        if not _AGENT_KEYS.search(shallow(arguments, keep_strings=False)):
            continue
        refs, resolved, has_tools = _list_refs(arguments)
        top = shallow(arguments)
        # Only a name the author gave the agent: a variable called `agent` is not one.
        name = string_value(top, "name")
        if match.group("factory") in _GENERIC_FACTORIES and not (
            library and (has_tools or re.search(r"(?<![\w.])(?:instructions|system_prompt|systemPrompt)\s*[:=]", shallow(arguments, keep_strings=False)))
        ):
            continue
        model = _MODEL.search(arguments)
        units.append(source.unit(
            KIND_AGENT, match.start(), end, ADAPTER, name=name,
            description=string_value(top, "description"),
            symbol=match.group("bound") or enclosing_symbol(source.text, match.start()),
            has_handler=True, model=model.group(1) if model else None,
            tool_refs=refs, tools_resolved=resolved if has_tools else True,
        ))
    return units


def framework_units(source: SourceFile) -> list[AgentUnit]:
    """Tools and agents declared with an agent framework."""
    if not (source.is_script or source.is_python):
        return []
    if "tool" not in source.text and "Tool" not in source.text and "gent" not in source.text:
        return []
    tools = _python_tools(source) if source.is_python else _script_tools(source)
    return tools + _agents(source)
