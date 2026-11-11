"""Adapter: skills and agents written as instruction files.

A skill is a ``SKILL.md`` with a name and a description in its front matter;
an agent file is a Markdown file in an ``agents`` directory of a coding tool
(``.claude/agents/reviewer.md``) or one named ``*.agent.md``.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from wystan.pipeline_v2.agents.record import KIND_AGENT, KIND_SKILL, AgentUnit

__all__ = ["ADAPTER", "instruction_kind", "instruction_unit"]

ADAPTER = "instruction-file"
_AGENT_FILE = re.compile(r"(?:^|/)\.[\w-]+/agents/[^/]+\.md$|\.agent\.md$")
_FRONT_MATTER = re.compile(r"\A---\s*\n(?P<body>.*?)\n---\s*(?:\n|\Z)", re.S)
_FIELD = r"^{key}\s*:\s*(?P<value>.+?)\s*$"


def instruction_kind(rel: str) -> str | None:
    """``skill`` or ``agent`` when ``rel`` is an instruction file."""
    if PurePosixPath(rel).name == "SKILL.md":
        return KIND_SKILL
    if _AGENT_FILE.search(rel):
        return KIND_AGENT
    return None


def _field(front: str, key: str) -> str | None:
    match = re.search(_FIELD.format(key=key), front, re.M)
    if match is None:
        return None
    value = match.group("value").strip().strip("'\"")
    return " ".join(value.split()) or None if value not in (">", "|", ">-", "|-") else None


def instruction_unit(rel: str, text: str, scope: str) -> AgentUnit | None:
    """The skill or agent an instruction file declares."""
    kind = instruction_kind(rel)
    if kind is None:
        return None
    front = _FRONT_MATTER.match(text)
    body = front.group("body") if front else ""
    path = PurePosixPath(rel)
    fallback = path.parent.name if kind == KIND_SKILL else path.name.removesuffix(".md").removesuffix(".agent")
    return AgentUnit(
        kind=kind, file=rel, line=1, end_line=text.count("\n") + 1,
        name=_field(body, "name") or fallback, description=_field(body, "description"),
        scope=scope, adapter=ADAPTER, model=_field(body, "model"),
    )
