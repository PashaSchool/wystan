"""The entry-point record.

An entry point is something a user can address in a product: a page, a
command, a UI action, an API operation. Stack adapters produce these
records from what the repository declares. Everything that decides what a
product feature is, and what it is called, reads the records and never a
path, a directory name or a framework convention.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "KIND_ACTION",
    "KIND_COMMAND",
    "KIND_OPERATION",
    "KIND_PAGE",
    "LABEL_DESCRIPTION",
    "LABEL_HEADING",
    "LABEL_NAV",
    "LABEL_TITLE",
    "EntryPoint",
]

KIND_PAGE = "page"
KIND_COMMAND = "command"
KIND_ACTION = "action"
KIND_OPERATION = "operation"

LABEL_NAV = "nav"
LABEL_TITLE = "title"
LABEL_HEADING = "heading"
LABEL_DESCRIPTION = "description"


@dataclass(frozen=True)
class EntryPoint:
    """One thing a user can address, as the repository declares it."""

    kind: str
    address: str
    """How a user reaches it: ``/settings/webhooks``, ``gh pr create``."""
    file: str
    """Repository file that implements the entry."""
    label: str | None = None
    """The name the author wrote, or ``None``."""
    label_source: str | None = None
    parent: str | None = None
    """Address of the parent entry, from what the product declares."""
    symbol: str | None = None
    """Handler symbol in ``file``, when the adapter knows it."""
    adapter: str = ""

    @property
    def identity(self) -> tuple[str, str]:
        return (self.kind, self.address)
