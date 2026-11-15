"""One source file as an adapter sees it."""

from __future__ import annotations

from dataclasses import dataclass

from wystan.pipeline_v2.agents.record import AgentUnit
from wystan.pipeline_v2.agents.text import line_of

__all__ = ["PY_SUFFIXES", "SCRIPT_SUFFIXES", "SourceFile"]

SCRIPT_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
PY_SUFFIXES = (".py",)


@dataclass(frozen=True)
class SourceFile:
    """A repository file with its text and the scope its units take."""

    rel: str
    text: str
    scope: str

    @property
    def is_script(self) -> bool:
        return self.rel.endswith(SCRIPT_SUFFIXES)

    @property
    def is_python(self) -> bool:
        return self.rel.endswith(PY_SUFFIXES)

    def unit(self, kind: str, start: int, end: int, adapter: str, **fields: object) -> AgentUnit:
        """A unit declared between two offsets of this file."""
        return AgentUnit(
            kind=kind, file=self.rel, line=line_of(self.text, start),
            end_line=line_of(self.text, max(start, end - 1)), scope=self.scope, adapter=adapter,
            **fields,  # type: ignore[arg-type]
        )
