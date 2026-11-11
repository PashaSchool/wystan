"""Behaviour or declaration: what kind of code an exported symbol is.

A flow starts at code that does something. A validation schema, a type alias
or a constant table is offered by a file's exports exactly like a route
handler, but it has no behaviour to follow, so it cannot be a flow's entry.

Rule, for TypeScript and JavaScript:

  * a type, interface or enum is a **declaration**;
  * a function, method or class is **behaviour**;
  * a ``const`` is behaviour when its initializer contains a function
    expression or an arrow function, and a declaration otherwise.
    ``authenticatedProcedure.input(...).query(async (...) => ...)`` is
    behaviour; ``z.enum(STATUSES)`` is a declaration;
  * a ``const`` built by a validation library, or by combining another
    schema, is a declaration even when it carries a callback:
    ``z.object({ name: z.string().refine((v) => ...) })`` and
    ``ZBase.extend({...})`` describe data, they do not run a use case.

The rule reads the symbol's source lines, so it gives the same answer whether
the symbol range came from tree-sitter or from the regex extractor. Other
languages are not classified yet: every symbol counts as behaviour.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wystan.models.types import SymbolRange

__all__ = ["BEHAVIOUR", "DECLARATION", "classify_symbol"]

BEHAVIOUR = "behaviour"
DECLARATION = "declaration"

_TS_JS_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs")
_DECLARATION_KINDS = frozenset({"type", "enum", "interface"})
_BEHAVIOUR_KINDS = frozenset({"function", "class", "method", "constructor", "reexport"})
_FUNCTION_BODY = re.compile(r"=>|\bfunction\b")
_STRING_OR_COMMENT = re.compile(
    r"//[^\n]*|/\*.*?\*/|'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\"|`(?:\\.|[^`\\])*`",
    re.DOTALL,
)
# Namespaces the common validation libraries are imported as (zod, yup, joi,
# valibot, io-ts, superstruct, typebox, effect schema).
_SCHEMA_ROOTS = frozenset({"z", "zod", "yup", "Yup", "joi", "Joi", "v", "t", "s", "S", "Type", "Schema"})
# Methods that derive a schema from another schema.
_SCHEMA_COMBINATORS = frozenset({
    "extend", "merge", "pick", "omit", "partial", "required", "refine",
    "superRefine", "transform", "and", "or", "optional", "nullable", "array",
})
_CHAIN_HEAD = re.compile(r"^\s*([A-Za-z_$][\w$]*)\s*\.\s*([A-Za-z_$][\w$]*)\s*\(")
# ``const handler: (req: Request) => Response = ...`` — the arrow in the type
# annotation is not a function body.
_TYPE_ANNOTATION = re.compile(r"^[^=]*?\bconst\s+[\w$]+\s*:\s*[^=]*?(?:=>[^=]*?)?=(?!>)", re.DOTALL)


def classify_symbol(path: str, source: str, symbol: "SymbolRange | None") -> str:
    """``BEHAVIOUR`` or ``DECLARATION`` for one exported symbol.

    A symbol with no known range, or in a language without a rule, is
    behaviour: the classification only ever removes a candidate it can see."""
    if symbol is None or not path.endswith(_TS_JS_SUFFIXES):
        return BEHAVIOUR
    if symbol.kind in _DECLARATION_KINDS:
        return DECLARATION
    if symbol.kind in _BEHAVIOUR_KINDS:
        return BEHAVIOUR
    lines = source.splitlines()[symbol.start_line - 1:symbol.end_line]
    if not lines:
        return BEHAVIOUR
    text = _STRING_OR_COMMENT.sub("''", "\n".join(lines))
    initializer = _TYPE_ANNOTATION.sub("", text, count=1)
    if not _FUNCTION_BODY.search(initializer):
        return DECLARATION
    return DECLARATION if _is_schema_chain(initializer) else BEHAVIOUR


def _is_schema_chain(initializer: str) -> bool:
    """True when the initializer starts as ``<library>.<builder>(`` or as
    ``<Schema>.<combinator>(``."""
    head = _CHAIN_HEAD.match(initializer.partition("=")[2] if "const" in initializer.split("=")[0] else initializer)
    if head is None:
        return False
    return head.group(1) in _SCHEMA_ROOTS or head.group(2) in _SCHEMA_COMBINATORS
