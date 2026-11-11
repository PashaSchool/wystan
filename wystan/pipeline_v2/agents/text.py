"""Small source-text helpers shared by the agent adapters.

Adapters read declarations with regular expressions, like the entry-point
adapters do. These helpers keep the reading bounded and string-aware.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator

__all__ = ["balanced", "closed_spans", "first_string", "line_of", "shallow", "string_value"]

_MAX_SPAN = 40_000
# Scanned files are untrusted. A file is read for at most this many
# declarations of one shape, and is left alone once this many of them turn
# out not to close: each unclosed one costs a full ``_MAX_SPAN`` scan.
_MAX_MATCHES = 1_000
_MAX_UNCLOSED = 12
_PAIRS = {"{": "}", "(": ")", "[": "]"}
_QUOTES = "'\"`"
_STRING = re.compile(
    r"""(?P<q>'''|\"\"\"|['"`])(?P<body>(?:\\.|(?!(?P=q)).)*)(?P=q)""", re.S,
)


def line_of(text: str, offset: int) -> int:
    """1-indexed line of ``offset`` in ``text``."""
    return text.count("\n", 0, offset) + 1


def balanced(text: str, start: int, *, limit: int = _MAX_SPAN) -> int | None:
    """Offset just past the bracket that closes the one at ``start``.

    Brackets inside string literals are ignored. ``None`` when the span is not
    closed within ``limit`` characters (at most ``_MAX_SPAN``), so a malformed
    file costs a bounded amount of work."""
    opener = text[start]
    closer = _PAIRS.get(opener)
    if closer is None:
        return None
    depth, cursor, limit = 0, start, min(len(text), start + min(limit, _MAX_SPAN))
    quote: str | None = None
    while cursor < limit:
        char = text[cursor]
        if quote is not None:
            if char == "\\":
                cursor += 2
                continue
            if text.startswith(quote, cursor):
                cursor += len(quote)
                quote = None
                continue
        elif char in _QUOTES:
            triple = text[cursor:cursor + 3]
            quote = triple if triple in ("'''", '"""') else char
            cursor += len(quote)
            continue
        elif char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return cursor + 1
        cursor += 1
    return None


def first_string(text: str) -> str | None:
    """The first string literal in ``text``, unquoted and whitespace-folded."""
    match = _STRING.search(text)
    if match is None:
        return None
    return " ".join(match.group("body").split()) or None


def string_value(body: str, key: str) -> str | None:
    """Value of ``key`` in an object literal or keyword list, when it is a
    string literal: ``key: "…"``, ``"key": "…"``, ``key = "…"``.

    A value split over adjacent literals (``"a" + "b"``, or two literals on
    consecutive lines) reads as the first one."""
    pattern = re.compile(rf"""(?<![\w.])['"]?{re.escape(key)}['"]?\s*(?::(?!:)|=(?!=))\s*(?:str\s*=\s*)?""")
    for match in pattern.finditer(body):
        rest = body[match.end():match.end() + 2_000].lstrip("( \n\t")
        if rest[:1] in _QUOTES or rest[:2] in ("f'", 'f"'):
            return first_string(rest)
    return None


def shallow(body: str, *, keep_strings: bool = True) -> str:
    """``body`` with everything inside nested brackets blanked out, so a key
    is only found where it belongs to the outermost object or argument list.

    ``body`` is the text between a pair of brackets, without them. With
    ``keep_strings=False`` the contents of string literals are blanked too:
    a prompt that says "tools:" is then not mistaken for a ``tools`` key."""
    out: list[str] = []
    cursor, limit = 0, min(len(body), _MAX_SPAN)
    while cursor < limit:
        char = body[cursor]
        if char in _PAIRS:
            end = balanced(body, cursor) or limit
            out.append(char + " " * max(0, end - cursor - 2) + (_PAIRS[char] if end - cursor >= 2 else ""))
            cursor = end
        elif char in _QUOTES:
            match = _STRING.match(body, cursor)
            end = match.end() if match else cursor + 1
            literal = body[cursor:end]
            out.append(literal if keep_strings else literal[0] + " " * max(0, len(literal) - 2) + literal[-1:])
            cursor = end
        else:
            out.append(char)
            cursor += 1
    return "".join(out)


def closed_spans(
    pattern: re.Pattern[str], text: str, opener: Callable[[re.Match[str]], int],
) -> Iterator[tuple[re.Match[str], int]]:
    """Each match of ``pattern`` whose bracket at ``opener(match)`` closes,
    with the offset just past the closing bracket.

    The work per file is bounded: see ``_MAX_MATCHES`` and ``_MAX_UNCLOSED``."""
    unclosed = 0
    for seen, match in enumerate(pattern.finditer(text)):
        if seen >= _MAX_MATCHES or unclosed >= _MAX_UNCLOSED:
            return
        start = opener(match)
        end = balanced(text, start) if 0 <= start < len(text) else None
        if end is None:
            unclosed += 1
            continue
        yield match, end
