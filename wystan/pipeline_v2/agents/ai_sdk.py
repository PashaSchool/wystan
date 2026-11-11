"""Adapter: the AI SDK (``ai``, ``@ai-sdk/*``).

A tool is an object passed to ``tool``::

    const searchDocs = tool({
      description: "Search the documentation",
      inputSchema: z.object({ query: z.string() }),
      execute: async ({ query }) => …,
    })

and an agent is a model call that is given tools::

    streamText({ model: openai("gpt-5"), system, tools: { searchDocs, ...mcpTools } })

A model call with no ``tools`` is not an agent and produces nothing here.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from functools import lru_cache

from wystan.pipeline_v2.agents.record import KIND_AGENT, KIND_TOOL, AgentUnit
from wystan.pipeline_v2.agents.source import SourceFile
from wystan.pipeline_v2.agents.text import balanced, closed_spans, shallow, string_value

__all__ = ["ADAPTER", "ai_sdk_units", "enclosing_symbol", "tool_refs"]

ADAPTER = "ai-sdk"
_IMPORT = re.compile(r"""from\s+['"](?:ai|@ai-sdk/[\w-]+)['"]|require\(\s*['"](?:ai|@ai-sdk/[\w-]+)['"]""")
# `const name = tool({`  or a property `name: tool({`
# `const name = tool({`, a property `name: tool({`, or a factory that returns
# the tool: `const name = ({ session }) => tool({`.
_TOOL = re.compile(
    r"(?:\b(?:const|let|var)\s+(?P<bound>\w+)\s*(?::[^=]{0,80})?=\s*"
    r"(?:(?:async\s*)?(?:\([^()]{0,300}\)|\w+)\s*(?::[^=]{0,80})?=>\s*(?:\{\s*return\s+)?)?"
    r"|\b(?P<key>\w+)\s*:\s*)tool\(\s*(?=\{)",
)
_CALL = re.compile(r"\b(?:generateText|streamText|generateObject|streamObject)\(\s*(?=\{)")
_AGENT_CLASS = re.compile(r"(?:\b(?:const|let|var)\s+(?P<bound>\w+)\s*=\s*)?new\s+(?:Experimental_Agent|ToolLoopAgent|Agent)\(\s*(?=\{)")
_TOOLS_KEY = re.compile(r"(?<![\w.])tools\s*(?P<sep>[:,}])")
_MODEL = re.compile(r"""\bmodel\s*:\s*[\w.]+\(\s*['"]([\w.:/\-]+)['"]""")
_FUNCTION = re.compile(
    r"\b(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(\w+)\s*\(|\b(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?(?:\([^)]{0,200}\)|\w+)\s*=>",
)
_SHORTHAND = re.compile(r"\{\s*([A-Za-z_$][\w$]*(?:\s*,\s*[A-Za-z_$][\w$]*)*)\s*,?\s*\}")
_REF = re.compile(r"(?P<spread>\.\.\.)?\s*(?P<name>[A-Za-z_$][\w$]*)\s*(?P<colon>:)?")


@lru_cache(maxsize=4)
def _function_offsets(text: str) -> tuple[tuple[int, ...], tuple[str, ...]]:
    """Where each function of a file starts, and its name: one pass per file."""
    found = [(m.start(), m.group(1) or m.group(2)) for m in _FUNCTION.finditer(text)]
    return tuple(offset for offset, _ in found), tuple(name for _, name in found)


def enclosing_symbol(text: str, offset: int) -> str | None:
    """Name of the last function declared before ``offset``."""
    offsets, names = _function_offsets(text)
    index = bisect_right(offsets, offset) - 1
    return names[index] if index >= 0 else None


def tool_refs(body: str) -> tuple[tuple[str, ...], bool, bool]:
    """Names listed under ``tools`` in a call's options, whether every one of
    them is written out, and whether the call has tools at all."""
    # Look for the key on the options object itself: not in a nested object,
    # and not in the text of a prompt.
    key = _TOOLS_KEY.search(shallow(body, keep_strings=False))
    if key is None:
        return (), True, False
    if key.group("sep") != ":":
        return (), False, True                    # shorthand `tools,`: built elsewhere
    rest = body[key.end():].lstrip()
    if rest[:1] not in "{[":
        return (), False, True                    # `tools: someVariable`
    end = balanced(rest, 0)
    if end is None:
        return (), False, True
    names: list[str] = []
    resolved = True
    depth = 0
    inner = rest[1:end - 1]
    cursor = 0
    while cursor < len(inner):
        char = inner[cursor]
        if char in "{[(":
            skip = balanced(inner, cursor) or len(inner)
            if inner[max(0, cursor - 3):cursor] == "...":
                # `...(cond ? { markAsDone } : {})`: sometimes present, still named.
                resolved = False
                for group in _SHORTHAND.findall(inner[cursor:skip]):
                    names.extend(part.strip() for part in group.split(",") if part.strip())
            cursor = skip
            continue
        match = _REF.match(inner, cursor) if depth == 0 and (char == "." or char.isalpha() or char in "_$") else None
        if match is None:
            cursor += 1
            continue
        if match.group("spread"):
            resolved = False                      # `...mcpTools`
        else:
            names.append(match.group("name"))
        cursor = match.end()
        if match.group("colon"):                  # `key: value` — skip the value
            comma = inner.find(",", cursor)
            brace = min((i for i in (inner.find("{", cursor), inner.find("(", cursor)) if i != -1), default=-1)
            if brace != -1 and (comma == -1 or brace < comma):
                skip = balanced(inner, brace)
                cursor = skip if skip else len(inner)
            else:
                cursor = comma if comma != -1 else len(inner)
    return tuple(dict.fromkeys(names)), resolved, True


def _tools(source: SourceFile) -> list[AgentUnit]:
    units = []
    for match, end in closed_spans(_TOOL, source.text, lambda m: m.end()):
        body = shallow(source.text[match.end() + 1:end - 1])
        if not re.search(r"\b(?:description|inputSchema|parameters|execute)\s*[:(]", body):
            continue
        units.append(source.unit(
            KIND_TOOL, match.start(), end, ADAPTER,
            name=match.group("bound") or match.group("key"),
            description=string_value(body, "description"),
            symbol=enclosing_symbol(source.text, match.start()),
            has_handler=bool(re.search(r"\bexecute\b\s*[:(]", body)),
        ))
    return units


def _agents(source: SourceFile) -> list[AgentUnit]:
    units = []
    for pattern in (_CALL, _AGENT_CLASS):
        for match, end in closed_spans(pattern, source.text, lambda m: m.end()):
            body = source.text[match.end() + 1:end - 1]
            refs, resolved, has_tools = tool_refs(body)
            if not has_tools:
                continue                          # a model call alone is not an agent
            model = _MODEL.search(body)
            bound = match.groupdict().get("bound")
            units.append(source.unit(
                KIND_AGENT, match.start(), end, ADAPTER,
                name=string_value(shallow(body), "name"),
                symbol=bound or enclosing_symbol(source.text, match.start()),
                has_handler=True, model=model.group(1) if model else None,
                tool_refs=refs, tools_resolved=resolved,
            ))
    return units


def ai_sdk_units(source: SourceFile) -> list[AgentUnit]:
    """Tools and agents a script declares with the AI SDK."""
    if not source.is_script or not _IMPORT.search(source.text):
        return []
    return _tools(source) + _agents(source)
