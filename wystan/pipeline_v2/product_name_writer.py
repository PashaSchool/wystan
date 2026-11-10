"""LLM writer for product-language names.

Proposes a product-language name for each product feature and user flow from
the text the product shows its users. The writer only proposes: the caller
checks every proposal against the product-language laws and the evidence, and
discards what fails. Keyless scans have no writer.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from wystan.pipeline_v2.personas import _default_client_factory, _persona_batch

__all__ = ["NameWriter", "build_name_writer"]

NameWriter = Callable[[list[dict[str, Any]]], dict[str, str]]

ROLE = "product_name_writer"
_BATCH_SIZE = 40

_SYSTEM = """You name the product features and user flows of a software product
for its product owner. You are given, per item, the text the product shows its
users in the screens that belong to the item, the URLs of those screens, and
the names of the code units inside it.

Write the name a product owner would use.

- kind "feature": a noun phrase for a capability, 1 to 4 words
  ("Document templates", "Team members", "Signing certificate").
- kind "flow": a user goal that starts with a verb, 2 to 7 words
  ("Send a document for signature", "Invite a team member").
- Use the product's own words from "ui_text". Do not use a word that is not
  in the item's evidence.
- Never use: URL parameters or their leftovers ("Id", "Token"), file or
  directory names, words written together ("Htmltopdf"), package names,
  framework or protocol names (Remix, tRPC, CORS, HTTP), or verbs that describe
  what the code does (handle, validate, resolve, render, parse, process).
- Sibling items must get different names.
- If the evidence does not show something a user sees or does, answer null
  for that item. Do not guess.
- Keep "current" when it already follows these rules.

Output STRICT JSON only: {"names": {"<item id>": "<name>" or null}}"""


def _batches(items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    return [items[i:i + _BATCH_SIZE] for i in range(0, len(items), _BATCH_SIZE)]


def build_name_writer(
    *,
    model_id: str,
    cost_tracker: Any = None,
    cache: Any = None,
    llm_health: Any = None,
    client_factory: Callable[[], Any | None] = _default_client_factory,
) -> NameWriter | None:
    """A writer callable, or ``None`` on a keyless scan."""
    client = client_factory()
    if client is None:
        return None

    def write(items: list[dict[str, Any]]) -> dict[str, str]:
        names: dict[str, str] = {}
        for batch in _batches(items):
            user = "Items:\n" + json.dumps(batch, ensure_ascii=False) + "\n\nEmit the JSON now."
            parsed, _ = _persona_batch(
                role=ROLE, client=client, model=model_id, system=_SYSTEM, user=user,
                cost_tracker=cost_tracker, cache=cache, llm_health=llm_health,
                candidates_for_log=[item["id"] for item in batch],
            )
            proposed = (parsed or {}).get("names")
            if not isinstance(proposed, dict):
                continue
            known = {item["id"] for item in batch}
            names.update({
                key: value.strip() for key, value in proposed.items()
                if key in known and isinstance(value, str) and value.strip()
            })
        return names

    return write
