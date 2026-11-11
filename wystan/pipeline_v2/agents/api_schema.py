"""Adapter: tools written as the model API's own schema.

    tools = [{
        "name": "get_weather",
        "description": "Get the current weather for a city",
        "input_schema": {"type": "object", "properties": {…}},
    }]

The whole shape is required: an object that has ``input_schema`` or
``parameters`` but no ``name`` and ``description`` beside it is not a tool.
"""

from __future__ import annotations

import re

from wystan.pipeline_v2.agents.ai_sdk import enclosing_symbol
from wystan.pipeline_v2.agents.record import KIND_TOOL, AgentUnit
from wystan.pipeline_v2.agents.source import SourceFile
from wystan.pipeline_v2.agents.text import balanced, shallow, string_value

__all__ = ["ADAPTER", "api_schema_units"]

ADAPTER = "api-schema"
_SCHEMA_KEY = re.compile(r"""['"]?(?:input_schema|inputSchema|parameters)['"]?\s*:\s*(?=\{)""")
_MODEL_API = re.compile(r"anthropic|openai|messages\.create|chat\.completions|responses\.create|bedrock|genai|\btools\b", re.I)
_LOOK_BACK = 1_500
_MAX_OPENERS = 8
_MAX_TOOL_SPAN = 12_000
# After this many schema keys that turn out not to be tools, the file is left alone.
_MAX_MISSES = 30
# Schema keys read per file: a generated file with thousands of them is not a tool list.
_MAX_SCHEMAS = 200
_TOOL_NAME = re.compile(r"[\w.\-]{2,64}")


def _enclosing_object(text: str, offset: int) -> tuple[int, int] | None:
    """The innermost ``{…}`` that contains ``offset``.

    Scanned files are untrusted, so the work is bounded twice: the search
    looks back ``_LOOK_BACK`` characters, and tries ``_MAX_OPENERS`` braces."""
    cursor = offset
    floor = max(0, offset - _LOOK_BACK)
    for _ in range(_MAX_OPENERS):
        cursor = text.rfind("{", floor, cursor)
        if cursor == -1:
            return None
        end = balanced(text, cursor, limit=_MAX_TOOL_SPAN)
        if end is not None and end > offset:
            return cursor, end
    return None


def api_schema_units(source: SourceFile) -> list[AgentUnit]:
    """Tools declared as plain objects in the model API's schema."""
    if not (source.is_script or source.is_python) or not _MODEL_API.search(source.text):
        return []
    units: dict[int, AgentUnit] = {}
    misses = 0
    for seen, match in enumerate(_SCHEMA_KEY.finditer(source.text)):
        if seen >= _MAX_SCHEMAS or misses >= _MAX_MISSES:
            break
        span = _enclosing_object(source.text, match.start())
        if span is None:
            misses += 1
            continue
        if span[0] in units:
            continue
        schema_end = balanced(source.text, match.end()) or match.end()
        # Read the object without its schema, whose properties also carry
        # `name` and `description` keys.
        body = shallow(source.text[span[0] + 1:match.start()] + source.text[schema_end:span[1] - 1])
        name, description = string_value(body, "name"), string_value(body, "description")
        if not name or not description or not _TOOL_NAME.fullmatch(name):
            misses += 1
            continue
        units[span[0]] = source.unit(
            KIND_TOOL, span[0], span[1], ADAPTER, name=name, description=description,
            symbol=enclosing_symbol(source.text, span[0]),
        )
    return list(units.values())
