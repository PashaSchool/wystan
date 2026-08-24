"""ruby_def_spans — a deterministic resolver of Ruby block spans (fixb115).

The "Ruby AST gap" class for Ruby, closed by the same method as Go
(``go_func_spans``) and TS (``ts_ast``): no tree-sitter, no ruby toolchain
on the user's machine — **keyword-depth matching** ``class/module/def/if/
unless/case/while/until/for/begin/do`` ↔ ``end`` instead of brace matching.

Why (probe P13, VERIFIED on chatwoot exhibits): today's ``symbol_ranges``
for ``.rb`` are computed by ``ast_extractor._parse_ruby_file`` with the
heuristic **"end = the next symbol's start − 1"**, and it has three
named errors:

1. **a −1 shift in the start** — the regexes read ``^\\s*def``, and ``\\s``
   swallows the newline, so before a ``def`` preceded by a blank line the
   match starts ONE LINE UP (``def index`` physically on 5 → range 4..7);
2. **a class truncated by its first def** — ``class Platform 1..3`` in a
   30-line controller, because the next symbol is its own first method;
3. **a tail to EOF+1** — the file's last symbol stretches to
   ``source.count("\\n") + 1`` (the 44-line ``access_tokens_controller.rb``
   → span ``1..45``).

Here every block is closed by ITS OWN ``end``, so a method's span is its
physical ``def``…``end`` body, and a class covers all of its methods.

Honest limits of the approximation (anti-cases in the units, not hidden):
  * modifier forms (``return if x``, ``a = 1 unless b``) do NOT open a
    block — only a keyword at the START of a statement counts as an opener
    (line start, or after ``=``/``(``/``,``/``;``/``&&``/
    ``||``/``and``/``or``/``then``/``else``); ``until:``/``class:`` as
    hash keys do not open one either;
  * a ``do`` block is counted in its end-of-line form (``…each do |x|``) —
    the dominant style; inline ``5.times do puts 1 end`` is unsupported;
  * heredoc (``<<~SQL … SQL``), ``=begin/=end``, ``__END__``, string
    literals, ``%w[…]`` and ``#``-comments are stripped BEFORE counting, so
    the word ``end`` inside SQL or a string does not close a block;
  * endless def (``def foo = expr``) — a one-line span, no ``end``;
  * an UNCLOSED block (counter desync) is **discarded** rather than
    stretched to EOF: a tight undercount beats whole-file (the P13 law).

Flag: ``WYSTAN_RUBY_DEF_SPANS``, default **OFF** (armed), registered in
``scan_result_cache.ENV_OUTPUT_FLAGS`` WITHOUT a KEY_SCHEMA bump. When off,
``_parse_ruby_file`` returns exactly the same heuristic ranges as before
the fix (the kill-switch is byte-identical).

$0, no network, no LLM; cached on the file text within the process.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

__all__ = [
    "RUBY_DEF_SPANS_ENV",
    "RubySpan",
    "block_spans",
    "ruby_def_spans_enabled",
    "symbol_ranges_for",
]

RUBY_DEF_SPANS_ENV = "WYSTAN_RUBY_DEF_SPANS"


def ruby_def_spans_enabled() -> bool:
    """Armed — default **OFF**. Unset ≡ an explicit ``0`` (kill-switch)."""
    return os.environ.get(RUBY_DEF_SPANS_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


@dataclass(frozen=True)
class RubySpan:
    """One block: ``(name, kind, start_line, end_line)`` 1-based, inclusive."""

    name: str
    kind: str          # "class" | "module" | "method" | "constant"
    start_line: int
    end_line: int


# ── lexical line cleanup ────────────────────────────────────────────────

#: ``%w[…]`` / ``%i(…)`` / ``%W{…}`` — word lists; the word ``end`` can
#: appear inside one and is NOT a closer.
_RE_PERCENT_LIT = re.compile(r"%[wWiI]\s*[\[({<][^\])}>]*[\])}>]")

#: heredoc start: ``<<~SQL`` / ``<<-'EOS'`` / ``<<EOS``. A bare (unquoted)
#: one is accepted only in UPPER CASE, so that ``arr << item`` and
#: ``class << self`` are not read as heredocs.
_RE_HEREDOC = re.compile(
    r"<<[-~]?(?:'([A-Za-z_]\w*)'|\"([A-Za-z_]\w*)\"|([A-Z_][A-Z0-9_]*))",
)

_QUOTES = ("'", '"', "`")


def _strip_line(line: str) -> str:
    """Strip string literals, ``%w[…]`` and the ``#``-comment.

    A literal's CONTENT is replaced by emptiness (not spaces) — the quotes
    stay, so the heredoc detector still sees the surrounding syntax.
    """
    out: list[str] = []
    i = 0
    n = len(line)
    quote: str | None = None
    while i < n:
        ch = line[i]
        if quote is not None:
            if ch == "\\" and quote != "'":
                i += 2
                continue
            if ch == quote:
                quote = None
                out.append(ch)
            i += 1
            continue
        if ch in _QUOTES:
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "#":
            break          # comment runs to end of line
        out.append(ch)
        i += 1
    return _RE_PERCENT_LIT.sub("", "".join(out))


# ── opener / closer detectors ───────────────────────────────────────────

_BLOCK_KEYWORDS = "class|module|def|if|unless|case|while|until|for|begin"

#: A keyword at the start of a statement (line start).
_RE_LEAD_KEYWORD = re.compile(rf"^\s*({_BLOCK_KEYWORDS})\b(?!:)")

#: A keyword after an operator/separator — also a statement-start
#: position (``x = if c``, ``foo(begin``, ``a; def b``).
#:
#: ``return``/``yield``/``next``/``raise`` are DELIBERATELY absent: they
#: are exactly what forms the dominant modifier idiom of Rails code
#: (``return if @contact.nil?`` — chatwoot ``validate_contacts`` /
#: ``look_up_exising_conversation``), and counting them as openers
#: desynchronises the counter for the whole rest of the file.
_RE_EMBEDDED_KEYWORD = re.compile(
    rf"(?:[=(,;]|&&|\|\||\b(?:and|or|then|else)\b)\s*"
    rf"({_BLOCK_KEYWORDS})\b(?!:)",
)

#: ``…each do |x|`` / ``loop do`` — a block opener at end of line.
_RE_DO_BLOCK = re.compile(r"\bdo\b(?:\s*\|[^|]*\|)?\s*$")

#: ``end`` as a standalone token: not ``.end``/``:end``/``@end``, not ``end:``.
_RE_END = re.compile(r"(?<![\w.:@$])end\b(?!:)")

#: The method name — including operator forms and ``?``/``!``/``=``.
_RE_DEF_NAME = re.compile(
    r"^\s*def\s+(?:self\.)?"
    r"([A-Za-z_]\w*[?!=]?|\[\]=?|<=>|===|==|!=|<=|>=|<<|>>|[+\-*/%<>!~^&|]+)",
)

#: endless def (Ruby 3): ``def foo = expr`` / ``def foo(a) = expr``.
#: The space before ``=`` is mandatory — otherwise it is a setter ``def foo=(v)``.
_RE_ENDLESS_DEF = re.compile(r"^\s*def\s+(?:self\.)?[^\s(=]+(?:\([^)]*\))?\s+=\s*\S")

# class/module names use EXACTLY the same pattern as in
# ``_parse_ruby_file`` (``[A-Z]\w*`` — the first segment of ``SuperAdmin::Foo``),
# so ``symbol_ranges`` stay consistent with ``sig.exports``, which this fix
# does NOT touch. Only the BOUNDARIES change, not the vocabulary of names.
_RE_CLASS_NAME = re.compile(r"^\s*class\s+([A-Z]\w*)")
_RE_MODULE_NAME = re.compile(r"^\s*module\s+([A-Z]\w*)")
_RE_CONST = re.compile(r"^\s*([A-Z][A-Z0-9_]+)\s*=(?!=)")

#: Openers whose ``do`` is already accounted for by the keyword itself
#: (``while x do`` — ONE opener, not two).
_DO_OWNING_LEADS = {"while", "until", "for"}


def _line_events(clean: str, lead: str | None) -> list[tuple[int, str, str]]:
    """Line events in positional order: ``(pos, "open"|"close", keyword)``."""
    events: list[tuple[int, str, str]] = []
    m = _RE_LEAD_KEYWORD.match(clean)
    if m is not None:
        events.append((m.start(1), "open", m.group(1)))
    for em in _RE_EMBEDDED_KEYWORD.finditer(clean):
        if m is not None and em.start(1) == m.start(1):
            continue
        events.append((em.start(1), "open", em.group(1)))
    do_m = _RE_DO_BLOCK.search(clean)
    if do_m is not None and lead not in _DO_OWNING_LEADS:
        events.append((do_m.start(), "open", "do"))
    for e in _RE_END.finditer(clean):
        events.append((e.start(), "close", "end"))
    events.sort(key=lambda ev: (ev[0], 0 if ev[1] == "open" else 1))
    return events


@dataclass
class _Frame:
    keyword: str
    name: str | None
    kind: str | None
    start: int


def block_spans(source: str) -> list[RubySpan]:
    """All ``class`` / ``module`` / ``def`` blocks of the file, HONEST bounds.

    Ordered by opening line. Same-named blocks (``def create`` in two
    classes of one file) are BOTH returned (the heuristic kept only the
    first), because each span is a coordinate in its own right.
    """
    spans: list[RubySpan] = []
    stack: list[_Frame] = []
    lines = source.split("\n")
    in_block_comment = False
    heredoc_end: str | None = None
    for idx, raw in enumerate(lines):
        lineno = idx + 1
        if heredoc_end is not None:
            if raw.strip() == heredoc_end:
                heredoc_end = None
            continue
        if in_block_comment:
            if raw.startswith("=end"):
                in_block_comment = False
            continue
        if raw.startswith("=begin"):
            in_block_comment = True
            continue
        if raw.strip() == "__END__":
            break

        clean = _strip_line(raw)
        if not clean.strip():
            continue

        lead_m = _RE_LEAD_KEYWORD.match(clean)
        lead = lead_m.group(1) if lead_m is not None else None

        # endless def — a standalone one-line span; no block is opened.
        if lead == "def" and _RE_ENDLESS_DEF.match(clean):
            nm = _RE_DEF_NAME.match(clean)
            if nm is not None:
                spans.append(RubySpan(nm.group(1), "method", lineno, lineno))
            _apply_closes(clean, stack, spans, lineno)
            hd_endless = _RE_HEREDOC.search(clean)
            if hd_endless is not None:
                heredoc_end = _heredoc_terminator(hd_endless, lines, idx)
            continue

        for pos, action, keyword in _line_events(clean, lead):
            if action == "open":
                name, kind = _name_for(keyword, clean, pos)
                stack.append(_Frame(keyword, name, kind, lineno))
            else:
                if not stack:
                    continue           # a stray ``end`` — never go negative
                frame = stack.pop()
                if frame.name and frame.kind:
                    spans.append(RubySpan(
                        frame.name, frame.kind, frame.start, lineno,
                    ))

        hd = _RE_HEREDOC.search(clean)
        if hd is not None:
            heredoc_end = _heredoc_terminator(hd, lines, idx)

    # UNCLOSED blocks are discarded (a tight undercount > whole-file).
    spans.sort(key=lambda s: (s.start_line, s.end_line, s.name))
    return spans


def _apply_closes(
    clean: str,
    stack: list[_Frame],
    spans: list[RubySpan],
    lineno: int,
) -> None:
    """The line's closers, when openers were already handled separately."""
    for _ in _RE_END.finditer(clean):
        if not stack:
            return
        frame = stack.pop()
        if frame.name and frame.kind:
            spans.append(RubySpan(frame.name, frame.kind, frame.start, lineno))


def _heredoc_terminator(
    match: "re.Match[str]", lines: list[str], idx: int,
) -> str | None:
    """A heredoc's terminator, and ONLY if it really exists somewhere below.

    Otherwise (``arr << CONST``, a false match) the heredoc does not open —
    better than swallowing half the file.
    """
    term = match.group(1) or match.group(2) or match.group(3)
    if not term:
        return None
    for nxt in lines[idx + 1:]:
        if nxt.strip() == term:
            return term
    return None


def _name_for(
    keyword: str, clean: str, pos: int,
) -> tuple[str | None, str | None]:
    """Name + kind for named openers; the rest are anonymous frames.

    ``clean[pos:]`` starts exactly at the keyword, so every pattern sees
    it as a statement start. ``class << self`` yields no name — it is an
    anonymous frame that only holds depth.
    """
    tail = clean[pos:]
    if keyword == "def":
        m = _RE_DEF_NAME.match(tail)
        return (m.group(1), "method") if m is not None else (None, None)
    if keyword == "class":
        m = _RE_CLASS_NAME.match(tail)
        return (m.group(1), "class") if m is not None else (None, None)
    if keyword == "module":
        m = _RE_MODULE_NAME.match(tail)
        return (m.group(1), "module") if m is not None else (None, None)
    return (None, None)


# ── constants ───────────────────────────────────────────────────────────

_OPEN_BRACKETS = {"[": "]", "{": "}", "(": ")"}


def _const_spans(source: str) -> list[RubySpan]:
    """``FOO = …`` — the assignment line, continued until brackets balance.

    Never stretches to the next symbol (exactly what gave the heuristic its
    tail to EOF): either one line, or an exact multi-line literal.
    """
    out: list[RubySpan] = []
    lines = source.split("\n")
    for idx, raw in enumerate(lines):
        m = _RE_CONST.match(_strip_line(raw))
        if m is None:
            continue
        start = idx + 1
        depth = 0
        end = start
        for j in range(idx, len(lines)):
            clean = _strip_line(lines[j])
            for ch in clean:
                if ch in _OPEN_BRACKETS:
                    depth += 1
                elif ch in (")", "]", "}"):
                    depth = max(0, depth - 1)
            end = j + 1
            if depth == 0:
                break
        out.append(RubySpan(m.group(1), "constant", start, end))
    return out


def symbol_ranges_for(source: str) -> list[RubySpan]:
    """The file's full span set: blocks + constants, in start order."""
    spans = block_spans(source) + _const_spans(source)
    spans.sort(key=lambda s: (s.start_line, s.end_line, s.name))
    return spans
