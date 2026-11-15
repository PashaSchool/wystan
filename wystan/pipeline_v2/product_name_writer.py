"""LLM writer for product-language names.

Proposes a product-language name for each product feature and user flow from
the text the product shows its users. The writer only proposes: the caller
checks every proposal against the product-language laws and the evidence, and
discards what fails. Keyless scans have no writer.

The model is asked about items in batches, but its answer is remembered per
item, keyed by that item's own evidence. An item whose evidence did not change
is never asked about again, whatever happened to its neighbours: asked twice,
the model does not answer twice the same, and an item that lost its name that
way lost its place in the product layer.

The item's id is not evidence. A journey's id is its ordinal in the scan
("uf:UF-123"), so one new journey earlier in the list shifts the id of every
later one; with the id in the key all of them were asked again and many came
back renamed. The key therefore leaves the id out. Only the key: the request
sent to the model is unchanged (the items with their ids, in list order), so
a first scan asks what it always asked. Answers stored before that change sit
under the old key (id included) and are still read, so the change itself
renames nothing.

Two items with equal evidence are one question with two answers. They do not
share one key (the second answer would overwrite the first, and the next scan
would give both items the same name): each has the key of its place among its
equals, see :mod:`wystan.pipeline_v2.scan_id_order`.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from wystan.cache.backend import CacheKind

from wystan.pipeline_v2.personas import _default_client_factory, _persona_batch
from wystan.pipeline_v2.scan_id_order import places_among_equals

__all__ = ["NameWriter", "build_name_writer"]

# ``writer(rows)`` asks about items of the repository; ``writer(rows,
# scope=<module root>)`` about items of one nested module (rule S1).
NameWriter = Callable[..., dict[str, str]]

ROLE = "product_name_writer"
_BATCH_SIZE = 40
# Bump when the prompt or the meaning of a stored answer changes.
_ITEM_CACHE_VERSION = 1
_ITEM_ROLE = ROLE + ":item"
# The repository's own scope: its items' keys are the keys they always had.
_ROOT_SCOPE = ""

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


# The prompt-row field that says where the item stands in this scan, not what
# the item is. It is left out of the memory key.
_POSITION_FIELD = "id"


def _key_of(
    model_id: str, item: dict[str, Any], place: int = 0, scope: str = _ROOT_SCOPE,
) -> str:
    payload = {
        "v": _ITEM_CACHE_VERSION, "role": _ITEM_ROLE, "model": model_id,
        "system": _SYSTEM, "item": item,
    }
    if place:
        # Only an item that has an equal before it carries its place, so
        # every other item keeps the key it always had.
        payload["place_among_equals"] = place
    if scope != _ROOT_SCOPE:
        # Places are counted inside one scope's call, so a module item with
        # the evidence of a repository item would get its place and its key:
        # it would read that answer and never be asked. Its module keeps it
        # apart; a repository item's key does not know modules exist.
        payload["module_scope"] = scope
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _item_key(
    model_id: str, item: dict[str, Any], place: int = 0, scope: str = _ROOT_SCOPE,
) -> str:
    """Memory key of one item's answer: its evidence, without its position.

    ``place`` tells apart items whose evidence is equal (0 for the first);
    ``scope`` is the nested module the item belongs to (none: the repository).
    """
    evidence = {k: v for k, v in item.items() if k != _POSITION_FIELD}
    return _key_of(model_id, evidence, place, scope)


def _positional_key(model_id: str, item: dict[str, Any], scope: str = _ROOT_SCOPE) -> str:
    """The key answers were stored under while the id was part of it. A
    module item carries its module here too: no older answer is a module's."""
    return _key_of(model_id, item, scope=scope)


def _item_keys(
    model_id: str, items: list[dict[str, Any]], scope: str = _ROOT_SCOPE,
) -> dict[str, str]:
    """``{item id: memory key}``, one key per item also when evidence is equal."""
    by_id = {item["id"]: item for item in items}
    evidence = {item_id: _item_key(model_id, item) for item_id, item in by_id.items()}
    places = places_among_equals(by_id, evidence.__getitem__)
    return {
        item_id: _item_key(model_id, item, places[item_id], scope)
        for item_id, item in by_id.items()
    }


def _recall(
    cache: Any, key: str, positional_key: str,
) -> tuple[bool, str | None]:
    """(known, name) for an item, from either key.

    An answer found only under the positional key is copied to the item's
    own key, so it survives the next shift of ids.

    The positional key is the only key builds before this one used, so a
    hit is the answer such a build would itself have read for this exact
    row. Neither key holds an engine version: answers of a build that was
    later rejected stay readable on the machine that ran it.
    """
    known, name = _remembered(cache, key)
    if known:
        return True, name
    known, name = _remembered(cache, positional_key)
    if known:
        _remember(cache, key, name)
    return known, name


def _remembered(cache: Any, key: str) -> tuple[bool, str | None]:
    """(known, name): ``name`` is ``None`` when the model declined the item."""
    if cache is None:
        return False, None
    try:
        stored = cache.get(CacheKind.LLM_PERSONA.value, key)
    except Exception:  # noqa: BLE001 - a cache fault degrades to a live call
        return False, None
    if not isinstance(stored, dict) or stored.get("v") != _ITEM_CACHE_VERSION:
        return False, None
    name = stored.get("name")
    return True, name if isinstance(name, str) and name else None


def _remember(cache: Any, key: str, name: str | None) -> None:
    if cache is None:
        return
    try:
        cache.set(CacheKind.LLM_PERSONA.value, key, {"v": _ITEM_CACHE_VERSION, "name": name})
    except Exception:  # noqa: BLE001 - a cache write fault never aborts a scan
        pass


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

    def write(items: list[dict[str, Any]], scope: str = _ROOT_SCOPE) -> dict[str, str]:
        names: dict[str, str] = {}
        keys = _item_keys(model_id, items, scope)
        # The whole-request memory is keyed by the request text only, so a
        # module's request does not use it: its answers are kept per item,
        # under the module's keys, and read from there.
        request_cache = cache if scope == _ROOT_SCOPE else None
        unanswered: list[dict[str, Any]] = []
        for item in items:
            known, name = _recall(
                cache, keys[item["id"]], _positional_key(model_id, item, scope),
            )
            if not known:
                unanswered.append(item)
            elif name:
                names[item["id"]] = name
        for batch in _batches(unanswered):
            user = "Items:\n" + json.dumps(batch, ensure_ascii=False) + "\n\nEmit the JSON now."
            parsed, _ = _persona_batch(
                role=ROLE, client=client, model=model_id, system=_SYSTEM, user=user,
                cost_tracker=cost_tracker, cache=request_cache, llm_health=llm_health,
                candidates_for_log=[item["id"] for item in batch],
            )
            proposed = (parsed or {}).get("names")
            if not isinstance(proposed, dict):
                continue
            for item in batch:
                value = proposed.get(item["id"])
                name = value.strip() if isinstance(value, str) and value.strip() else None
                # A declined item is remembered too: asking again would only
                # give the model a second chance to answer differently.
                _remember(cache, keys[item["id"]], name)
                if name:
                    names[item["id"]] = name
        return names

    return write
