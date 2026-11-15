"""What the qualifier of a handler reference names, read from the file that
registers the route (Stage 8.9 route-group planner).

A registration line passes ``reports.List`` or ``h.List``. The planner used
to keep only ``List`` and look it up among the row's definitions, so a
handler of another package (``reports.List``) was taken for the row's own
``List`` beside it. A qualifier is now read as written, from the
registering file's own imports and declarations:

* an import of another package, or a value of one: the reference is outside
  the row (``OUTSIDE``);
* the row's own package, a receiver or a value of it: the name is looked up
  among the row's definitions (``ROW``);
* anything the file does not say (a field of a value, a name declared in
  another file, a declaration this reader does not parse): ``None``, and the
  route is unresolved.

A bare name refers to the registering file's own package (:meth:`FileScope.
bare_kind`): the row's only when that file shares the row's directory and
package clause, or dot-imports the row's package.

Read for Go, the only language whose extractor declares registration sites
(``go_router.route_site``); in a file of any other language every qualifier
is ``None``. Lines are matched one at a time, each bounded by the planner's
``MAX_LINE_CHARS``, with patterns that run in linear time.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, NamedTuple

#: the qualifier is the row's own package, a receiver or a value of it
ROW = "row"
#: the qualifier names another package or a value of one
OUTSIDE = "outside"

_GO_SUFFIX = ".go"
# ``package name``: the package a Go file belongs to (with its directory).
_GO_PACKAGE_RE = re.compile(r"[ \t]*package[ \t]+([A-Za-z_]\w*)")
# ``import "p"`` / ``import alias "p"``, and a spec line inside ``import (``.
_GO_IMPORT_RE = re.compile(r'[ \t]*import[ \t]+(?:([A-Za-z_.]\w*)[ \t]+)?"([^"]+)"')
_GO_IMPORT_BLOCK_RE = re.compile(r"[ \t]*import[ \t]*\([ \t]*$")
_GO_IMPORT_SPEC_RE = re.compile(r'[ \t]*(?:([A-Za-z_.]\w*)[ \t]+)?"([^"]+)"')
# The default name of an imported package is its last path element without
# a major-version element (``echo/v5`` is ``echo``) or suffix (``yaml.v3``),
# and without a ``go-`` style prefix (``go-redis`` is ``redis``).
_GO_VERSION_ELEMENT_RE = re.compile(r"^v\d+$")
_GO_VERSION_SUFFIX_RE = re.compile(r"\.v\d+$")
# ``func (recv *T) Name(params)`` / ``func Name[T any](params)``: the
# receiver and the parameters on the signature line.
_GO_FUNC_RE = re.compile(
    r"func[ \t]*(?:\(([^()]*)\)[ \t]*)?[A-Za-z_]\w*[ \t]*(?:\[[^\]]*\][ \t]*)?\(([^()]*)\)")
# ``q := expr`` / ``q, err := expr``.
_GO_SHORT_VAR_RE = re.compile(r"[ \t]*([A-Za-z_]\w*)(?:[ \t]*,[ \t]*[A-Za-z_]\w*)*[ \t]*:=(.*)")
# ``var q T`` / ``var q = expr`` / ``var q T = expr``.
_GO_VAR_RE = re.compile(r"[ \t]*var[ \t]+([A-Za-z_]\w*)[ \t]+([^=]*)(?:=(.*))?$")
_DOTTED_RE = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*")
# What may stand before the type a declaration names: pointer, slice,
# variadic and address-of marks.
_TYPE_MARKS = "*&[]. \t"
# Go type keywords: a value of such a type has no package.
_GO_UNNAMED_TYPES = frozenset({"map", "chan", "func", "interface", "struct"})


class _Head(NamedTuple):
    """What a declaration says its value is: a type or a call, by name and
    package qualifier."""

    qualifier: str
    name: str
    is_call: bool


@dataclass
class FileScope:
    """The imports and declarations of one registering file."""

    path: str
    is_in_row: bool
    imports: dict[str, bool] = field(default_factory=dict)  # name -> is the row
    package: str | None = None              # this file's package clause
    row_packages: frozenset[str | None] = frozenset()  # the row files' clauses
    dot_imports_row: bool = False           # ``import . "<row package>"``

    def bare_kind(self) -> str:
        """What a bare name on a registration line refers to: this file's
        own package, which is the row's only when this file sits in the
        row's directory with the row's package clause, or when it
        dot-imports the row's package."""
        if self.dot_imports_row:
            return ROW
        if self.is_in_row and self.package in self.row_packages:
            return ROW
        return OUTSIDE
    declarations: dict[str, list[tuple[int, _Head]]] = field(
        default_factory=lambda: defaultdict(list))

    def classify(self, qualifier: str, line_number: int) -> str | None:
        """:data:`ROW`, :data:`OUTSIDE` or ``None`` for the qualifier of a
        reference on line *line_number*."""
        first = qualifier.split(".", 1)[0]
        if first in self.imports:
            return ROW if self.imports[first] else OUTSIDE
        if "." in qualifier:
            return None  # a field of a value: its type is not written here
        head = self._nearest(qualifier, line_number)
        return None if head is None else self._of_head(head)

    def _nearest(self, name: str, line_number: int) -> _Head | None:
        """The last declaration of *name* at or before the line: the one in
        scope there, as far as one line at a time can tell."""
        found = None
        for number, head in self.declarations.get(name, ()):
            if number <= line_number:
                found = head
        return found

    def _of_head(self, head: _Head) -> str | None:
        if head.qualifier:
            first = head.qualifier.split(".", 1)[0]
            if first in self.imports:
                return ROW if self.imports[first] else OUTSIDE
            return None
        if head.is_call:
            # a function of this file's own package made the value: the
            # row's when this file is in the row, unknown otherwise
            return ROW if self.is_in_row else None
        return ROW if self.is_in_row else OUTSIDE


def package_clause(path: str, lines: Iterable[str | None]) -> str | None:
    """The package clause of a Go file (``None`` for any other language,
    or when it is not among the lines read)."""
    if not path.endswith(_GO_SUFFIX):
        return None
    for line in lines:
        match = _GO_PACKAGE_RE.match(line or "")
        if match:
            return match.group(1)
    return None


def file_scope(
    path: str, lines: list[str | None], row: tuple[str, frozenset[str | None]],
) -> FileScope:
    """Read the imports and declarations of the registering file *path*
    (its lines as read; ``None`` for a line not read). *row* is the row's
    directory and its files' package clauses."""
    row_dir, row_packages = row
    scope = FileScope(path, os.path.dirname(path) == row_dir,
                      package=package_clause(path, lines),
                      row_packages=row_packages)
    if not path.endswith(_GO_SUFFIX):
        return scope
    in_import_block = False
    for number, line in enumerate(lines, start=1):
        if not line:
            continue
        if in_import_block:
            in_import_block = line.strip() != ")"
            _note_go_import(scope, _GO_IMPORT_SPEC_RE.match(line), row_dir)
        elif _GO_IMPORT_BLOCK_RE.match(line):
            in_import_block = True
        elif _GO_IMPORT_RE.match(line):
            _note_go_import(scope, _GO_IMPORT_RE.match(line), row_dir)
        else:
            for name, head in _go_declarations(line):
                scope.declarations[name].append((number, head))
    return scope


def _note_go_import(
    scope: FileScope, match: re.Match[str] | None, row_dir: str,
) -> None:
    if match is None:
        return
    alias, import_path = match.group(1), match.group(2)
    if alias == ".":
        # its names are bare names of this file
        scope.dot_imports_row |= _is_row_package(import_path, row_dir)
        return
    if alias == "_":
        return  # bound to no name
    name = alias or _go_package_name(import_path)
    if name:
        scope.imports[name] = _is_row_package(import_path, row_dir)


def _go_package_name(import_path: str) -> str:
    elements = [e for e in import_path.split("/") if e]
    if len(elements) > 1 and _GO_VERSION_ELEMENT_RE.match(elements[-1]):
        elements.pop()
    last = _GO_VERSION_SUFFIX_RE.sub("", elements[-1]) if elements else ""
    return re.split(r"[-.]", last)[-1]


def _is_row_package(import_path: str, row_dir: str) -> bool:
    """A Go import path names the row's package when it ends with the row's
    directory (the module path before it is not known here)."""
    if not row_dir:
        return False
    return import_path == row_dir or import_path.endswith("/" + row_dir)


def _go_declarations(line: str) -> list[tuple[str, _Head]]:
    """Names a Go line declares, each with what its value is."""
    match = _GO_FUNC_RE.match(line.lstrip())
    if match:
        return [*_go_parameters(match.group(1) or ""),
                *_go_parameters(match.group(2) or "")]
    match = _GO_SHORT_VAR_RE.match(line)
    if match:
        head = _expression_head(match.group(2))
        return [(match.group(1), head)] if head else []
    match = _GO_VAR_RE.match(line)
    if match:
        written_type = match.group(2).strip()
        head = (_type_head(written_type) if written_type
                else _expression_head(match.group(3) or ""))
        return [(match.group(1), head)] if head else []
    return []


def _go_parameters(text: str) -> list[tuple[str, _Head]]:
    """``a, b *T, c pkg.U`` -> each name with its type. A name written
    without a type takes the type of the next one that has it."""
    out: list[tuple[str, _Head]] = []
    waiting: list[str] = []
    for piece in text.split(","):
        words = piece.split(None, 1)
        if not words:
            continue
        if len(words) == 1:
            waiting.append(words[0])
            continue
        head = _type_head(words[1])
        for name in [*waiting, words[0]]:
            if head:
                out.append((name, head))
        waiting = []
    return out


def _type_head(text: str) -> _Head | None:
    match = _DOTTED_RE.match(text.lstrip(_TYPE_MARKS))
    if not match or match.group(0) in _GO_UNNAMED_TYPES:
        return None
    return _head_of(match.group(0), is_call=False)


def _expression_head(text: str) -> _Head | None:
    """The type or call that makes a value: ``&pkg.T{`` / ``T{`` is the
    type, ``pkg.New(`` / ``New(`` the call, ``new(T)`` the type T."""
    text = text.strip().lstrip("&").lstrip()
    match = _DOTTED_RE.match(text)
    if not match:
        return None
    rest = text[match.end():].lstrip()
    if match.group(0) == "new" and rest.startswith("("):
        return _type_head(rest[1:])
    if rest.startswith("{"):
        return _head_of(match.group(0), is_call=False)
    if rest.startswith("("):
        return _head_of(match.group(0), is_call=True)
    return None


def _head_of(dotted: str, *, is_call: bool) -> _Head:
    qualifier, _dot, name = dotted.rpartition(".")
    return _Head(qualifier, name, is_call)


__all__ = ["OUTSIDE", "ROW", "FileScope", "file_scope", "package_clause"]
