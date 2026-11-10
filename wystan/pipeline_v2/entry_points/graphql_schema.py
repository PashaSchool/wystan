"""Adapter: GraphQL operations declared in code.

A GraphQL API has one HTTP route, so routes say nothing about what it
offers. The schema does. In a code-first schema the root types are composed
from group classes, and each group lists its operations:

    class Mutation(AccountMutations, CheckoutMutations, ...): ...
    class CheckoutMutations(graphene.ObjectType):
        checkout_create = CheckoutCreate.Field()

That is a declared tree: root type, group, operation. This adapter reads it.
An operation's label is its description in the schema file when the
repository ships one (``schema.graphql``), and its file is the file of the
class that implements it. The group's name is the group class's name with
the root type's word removed (``CheckoutMutations`` gives "Checkout").

Grammar: graphene (Python). A repository with another schema grammar gets
no entries from this adapter.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from wystan.pipeline_v2.entry_points.record import KIND_OPERATION, LABEL_DESCRIPTION, EntryPoint
from wystan.pipeline_v2.product_strings import _read_text

__all__ = ["ADAPTER", "graphql_entries"]

ADAPTER = "graphql-schema"
_ROOT_WORDS = {"Query": ("Queries", "Query"), "Mutation": ("Mutations", "Mutation"),
               "Subscription": ("Subscriptions", "Subscription")}
_CLASS = re.compile(r"^class\s+(\w+)\s*\(([^)]*)\)\s*:", re.M | re.S)
_FIELD = re.compile(r"^    (\w+)\s*=\s*([\w.]+?)(?:\.Field)?\(", re.M)
_SDL_ROOT = re.compile(r"^(?:extend\s+)?type\s+(Query|Mutation|Subscription)\b[^{]*\{(.*?)^\}", re.M | re.S)
# A field's own description sits at the field's indent, directly above it.
# Argument descriptions are indented deeper and are not the field's.
_SDL_FIELD = re.compile(r'^  """(.*?)"""[ \t]*\n  (\w+)\s*[(:]', re.M | re.S)
_MAX_FILE_BYTES = 8_000_000
_MAX_OPERATIONS = 5_000


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.capitalize() for part in rest)


def _first_sentence(text: str) -> str:
    line = " ".join(text.split())
    return re.split(r"(?<=[.!?])\s", line, maxsplit=1)[0].rstrip(".")[:140]


def _sdl_descriptions(repo_path: Path, files: list[str]) -> dict[str, str]:
    """``Root.field -> description`` from schema files in the repository."""
    found: dict[str, str] = {}
    for rel in files:
        if not rel.endswith((".graphql", ".gql")):
            continue
        path = repo_path / rel
        try:
            if path.is_symlink() or path.stat().st_size > _MAX_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for root in _SDL_ROOT.finditer(text):
            for field in _SDL_FIELD.finditer(root.group(2)):
                if field.group(1):
                    found.setdefault(f"{root.group(1)}.{field.group(2)}", _first_sentence(field.group(1)))
    return found


def _group_name(class_name: str, root: str) -> str:
    for suffix in _ROOT_WORDS[root]:
        if class_name.endswith(suffix) and len(class_name) > len(suffix):
            return class_name[: -len(suffix)]
    return class_name


def _spaced(name: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)


def graphql_entries(ctx: Any) -> list[EntryPoint]:
    """Operations of a code-first GraphQL schema, grouped as the schema
    composes them."""
    repo_path = Path(getattr(ctx, "repo_path", "."))
    files = sorted(getattr(ctx, "tracked_files", None) or [])
    classes: dict[str, tuple[str, str, str]] = {}  # name -> (file, bases, body)
    for rel in files:
        if not rel.endswith(".py"):
            continue
        text = _read_text(repo_path, rel) or ""
        if "class " not in text:
            continue
        matches = list(_CLASS.finditer(text))
        for i, match in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            classes.setdefault(match.group(1), (rel, match.group(2), text[match.end():end]))
    roots = {name: classes[name] for name in _ROOT_WORDS if name in classes}
    if not roots:
        return []
    descriptions = _sdl_descriptions(repo_path, files)
    entries: dict[tuple[str, str], EntryPoint] = {}
    for root, (_, bases, _) in sorted(roots.items()):
        for base in (b.strip().split(".")[-1] for b in bases.split(",")):
            if base not in classes:
                continue
            group_file, _, body = classes[base]
            group = _spaced(_group_name(base, root))
            entries.setdefault((KIND_OPERATION, group), EntryPoint(
                kind=KIND_OPERATION, address=group, file=group_file, label=group,
                label_source="schema", adapter=ADAPTER,
            ))
            for field, target in _FIELD.findall(body):
                if len(entries) >= _MAX_OPERATIONS:
                    break
                address = f"{root}.{_camel(field)}"
                implementation = classes.get(target.split(".")[-1])
                label = descriptions.get(address)
                entries.setdefault((KIND_OPERATION, address), EntryPoint(
                    kind=KIND_OPERATION, address=address,
                    file=implementation[0] if implementation else group_file,
                    label=label, label_source=LABEL_DESCRIPTION if label else None,
                    parent=group, symbol=target.split(".")[-1] if implementation else f"resolve_{field}",
                    adapter=ADAPTER,
                ))
    with_operations = {entry.parent for entry in entries.values() if entry.parent}
    return [
        entry for entry in entries.values()
        if entry.parent or entry.address in with_operations
    ]
