"""go_func_spans — B98-3e (B2): a deterministic resolver of Go function spans.

The "Ruby AST gap" class for Go, closed the same way as TS: regex +
brace matching, no tree-sitter. Yields ``{func_name: (start_line,
end_line)}`` per file — the material for span ownership of table families
(server/routes.go: handler functions ChatHandler/GenerateHandler/… share
one file; each family owns ITS OWN rows — the law "Rulers = coordinates").

Receiver methods (``func (s *Server) ChatHandler(``) resolve to the bare
name (registration says ``s.ChatHandler`` — matched on the last segment).
Braces are counted outside quotes/backticks/comment lines — an honest
deterministic approximation (no full lexer; anti-cases in the units:
nested func literals inside a body do NOT start new spans — only a
top-level ``^func`` matches).

$0, no network; cached on (file, mtime bytes) per process.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

__all__ = ["func_spans", "handler_span", "resolve_handler_loc"]

#: top-level functions/methods: ``func Name(`` / ``func (recv T) Name(``.
_FUNC_RE = re.compile(
    r"^func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\(", re.MULTILINE)

_LINE_COMMENT = "//"


def _brace_end_line(text: str, open_pos: int) -> int:
    """The line of the closing brace of the block opened by '{' at ``open_pos``.
    Skips string literals ("…", `…`, '…') and //-comments."""
    depth = 0
    i = open_pos
    n = len(text)
    in_str: str | None = None
    while i < n:
        ch = text[i]
        if in_str:
            if in_str != "`" and ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
        elif ch in ('"', "'", "`"):
            in_str = ch
        elif ch == "/" and text.startswith(_LINE_COMMENT, i):
            nl = text.find("\n", i)
            i = n if nl < 0 else nl
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text.count("\n", 0, i) + 1
        i += 1
    return text.count("\n") + 1  # unclosed block — to EOF (honestly)


def func_spans(text: str) -> dict[str, tuple[int, int]]:
    """``{name: (start_line, end_line)}`` for the file's top-level funcs.
    Duplicate names (Go has no overloading, but build tags can produce a
    repeat) — the first one wins (deterministically)."""
    out: dict[str, tuple[int, int]] = {}
    for m in _FUNC_RE.finditer(text):
        name = m.group(1)
        if name in out:
            continue
        brace = text.find("{", m.end() - 1)
        if brace < 0:
            continue
        start = text.count("\n", 0, m.start()) + 1
        out[name] = (start, _brace_end_line(text, brace))
    return out


@lru_cache(maxsize=256)
def _file_spans(abs_path: str) -> dict[str, tuple[int, int]]:
    try:
        text = Path(abs_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    return func_spans(text)


@lru_cache(maxsize=64)
def _package_files(abs_dir: str) -> tuple[str, ...]:
    try:
        return tuple(sorted(
            str(p) for p in Path(abs_dir).iterdir()
            if p.suffix == ".go" and not p.name.endswith("_test.go")))
    except OSError:
        return ()


def handler_span(
    repo_path: Path, rel_file: str, handler_ref: str,
) -> tuple[str, int, int] | None:
    """The handler span by its registration reference (``s.ChatHandler``
    → last segment). First the registration file, then NEIGHBOURING .go
    files of the same package (Go handlers often live in separate files of
    the directory) — the first match in sorted order (deterministic). Returns
    ``(rel_or_abs_file, start, end)``."""
    leaf = str(handler_ref or "").rsplit(".", 1)[-1].strip()
    if not leaf:
        return None
    reg_abs = Path(repo_path) / rel_file
    sp = _file_spans(str(reg_abs)).get(leaf)
    if sp:
        return (str(rel_file), sp[0], sp[1])
    for sib in _package_files(str(reg_abs.parent)):
        if sib == str(reg_abs):
            continue
        sp = _file_spans(sib).get(leaf)
        if sp:
            return (sib, sp[0], sp[1])
    return None


def resolve_handler_loc(
    repo_path: Path,
    rows: list[dict],
) -> int:
    """Σ LOC of handler spans for one family's routes_index rows (the rows
    carry ``file`` + ``handler``; a row with no handler/span counts 0,
    honestly). Dedup by (file, span) — one handler serving several methods
    counts once."""
    seen: set[tuple[str, int, int]] = set()
    total = 0
    for r in rows:
        f = str(r.get("file") or "")
        h = str(r.get("handler") or "")
        if not f or not h:
            continue
        sp = handler_span(repo_path, f, h)
        if not sp:
            continue
        if sp in seen:
            continue
        seen.add(sp)
        total += sp[2] - sp[1] + 1
    return total
