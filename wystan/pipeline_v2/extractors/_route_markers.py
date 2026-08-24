"""fixb133 M1 — the shared router-MARKER vocabulary + the display-channel
segment sanitizer built on it.

Framework knowledge about file-system routing markers already lived in
``profiles/next_app_router._is_skipped_segment`` (route groups ``(area)``,
private folders ``_folder``, parallel slots ``@slot``, intercepting routes
``(.)`` / ``(..)`` / ``(...)``, dynamic segments ``[x]``), but the NAMING
path could not reach it — so a PF display kept the marker verbatim
(umami ``(.)sessions``, ``[.]well-known``, ``robots[.]txt``). This module
is that vocabulary FACTORED OUT (the profile now delegates to it — one
definition, two consumers) plus the two things the profile never needed:

* :func:`sanitize_segment` — a path segment reduced to its human word for
  the DISPLAY channel (``(.)sessions`` -> ``sessions``, ``robots[.]txt``
  -> ``robots.txt``, ``[.]well-known`` -> ``well-known``,
  ``[-htmltopdf]+`` -> ``htmltopdf``), with ``None`` for segments that are
  purely organisational (a parallel slot names no capability).
* :func:`has_marker_residue` — the DETECTION half: does a finished
  display still carry marker machinery? Deliberately NOT "any paren":
  an authored paren tail (``CalDav (Beta)``, ``Enterprise+``) is product
  vocabulary, so only marker SHAPES fire — an intercepting marker, an
  ``@slot`` word, or unbalanced parens.

Pure syntax, zero vocabulary, zero per-repo knowledge: every rule here is
a published framework convention (Next.js App Router / Remix flat routes /
SvelteKit / Nuxt), which is why the same predicates serve the profile and
the naming contract. The junk-route-group predicate
(:func:`is_junk_route_group`) is the one judgement call and it is a
universal ORGANISATIONAL-convention test, not a dictionary of names.
"""

from __future__ import annotations

import re

__all__ = [
    "INTERCEPT_PREFIX_RE",
    "has_marker_residue",
    "is_dynamic_segment",
    "is_intercepting_marker",
    "is_junk_route_group",
    "is_organizational_segment",
    "is_parallel_slot",
    "is_private_folder",
    "is_route_group",
    "route_group_inner",
    "sanitize_display_text",
    "sanitize_segment",
]

#: Next.js intercepting-route marker PREFIX — ``(.)folder`` (same level),
#: ``(..)folder`` (one up), ``(...)folder`` (root). The marker is transport
#: (which router level renders the overlay); the routed name follows it.
INTERCEPT_PREFIX_RE = re.compile(r"^\(\.{1,3}\)")

#: Route group ``(area)`` — an author-declared organisational folder that
#: does NOT appear in the URL. ``len(seg) > 2`` keeps ``()`` out.
_GROUP_RE = re.compile(r"^\((?P<inner>[^()]+)\)$")

#: A bracket pair INSIDE a segment (never spanning the whole segment) is an
#: escaped literal, not a dynamic param: in every dialect a dynamic segment
#: occupies the WHOLE segment (``[id]`` / ``[...slug]`` / ``[[...slug]]``),
#: so ``robots[.]txt`` / ``[.]well-known`` / ``[-htmltopdf]+`` are escapes.
_ESCAPE_RE = re.compile(r"\[([^\[\]]*)\]")

#: Edge punctuation a sanitized segment never keeps (Remix flat-route ``+``
#: nesting, leading escape dot, kebab/snake edges).
_EDGE_PUNCT = "+-_. "

#: Marker residue inside a FINISHED display: an intercepting marker in any
#: of the forms a downstream humanizer may leave it (``(.)`` verbatim, or
#: ``( )`` / ``()`` after a dot-splitting pass).
_INTERCEPT_TEXT_RE = re.compile(r"\(\s*\.{0,3}\s*\)")

#: An ``@slot`` word anywhere in a display (start of string or after a
#: separator) — the parallel-route slot leaked into prose.
_SLOT_TEXT_RE = re.compile(r"(?:^|[\s—/])@\w")

#: Universal ORGANISATIONAL route-group conventions — a group whose name
#: describes the wrapper rather than the product area. Such a group is never
#: a display qualifier (cal.com ``(use-page-wrapper)`` -> 'Auth (Use Page
#: Wrapper)'). Token-wise, never substring, so 'apple' / 'mainstream' /
#: 'roots' are untouched. Scale-invariant: no counts, no per-repo names.
_JUNK_GROUP_PREFIXES = ("use-",)
_JUNK_GROUP_TOKENS = frozenset({
    "wrapper", "layout", "shell", "main", "app", "root", "default",
})

_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def is_route_group(seg: str) -> bool:
    """``(area)`` — a route group (NOT an intercepting marker)."""
    m = _GROUP_RE.match((seg or "").strip())
    return bool(m and not m.group("inner").startswith("."))


def route_group_inner(seg: str) -> str | None:
    """The group's own word (``(reports)`` -> ``reports``), else ``None``."""
    m = _GROUP_RE.match((seg or "").strip())
    if not m or m.group("inner").startswith("."):
        return None
    return m.group("inner").strip() or None


def is_intercepting_marker(seg: str) -> bool:
    """``(.)x`` / ``(..)x`` / ``(...)x`` — an intercepting-route overlay."""
    return bool(INTERCEPT_PREFIX_RE.match((seg or "").strip()))


def is_parallel_slot(seg: str) -> bool:
    """``@slot`` — a parallel-route slot (renders INTO a layout)."""
    return (seg or "").strip().startswith("@")


def is_private_folder(seg: str) -> bool:
    """``_folder`` — a private / pathless folder."""
    return (seg or "").strip().startswith("_")


def is_dynamic_segment(seg: str) -> bool:
    """``[id]`` / ``[...slug]`` / ``[[...slug]]`` — a whole-segment param."""
    s = (seg or "").strip()
    return s.startswith("[") and s.endswith("]")


def is_organizational_segment(seg: str) -> bool:
    """True when the segment is routing organisation, never a URL word.

    The exact predicate ``profiles/next_app_router._is_skipped_segment``
    used before fixb133 (minus its stack-noise vocabulary check, which
    stays with the profile): empty, any ``(``-leading segment (route group
    OR intercepting marker), ``_private``, ``@slot``, ``[dynamic]``.
    """
    s = seg or ""
    if not s:
        return True
    if s.startswith("("):        # route group OR intercepting marker
        return True
    if s.startswith("_"):        # private folder
        return True
    if s.startswith("@"):        # parallel-route slot
        return True
    return s.startswith("[") and s.endswith("]")


def is_junk_route_group(name: str) -> bool:
    """True when a route-group name describes ORGANISATION, not a product
    area — so it may never decorate a display.

    Universal conventions only: a ``use-`` prefixed group (a hook-named
    wrapper folder) or a group carrying a wrapper/layout/shell/main/app/
    root/default TOKEN. Token equality (never substring) keeps real
    product words safe.
    """
    n = (name or "").strip().lower()
    if not n:
        return True
    if any(n.startswith(p) for p in _JUNK_GROUP_PREFIXES):
        return True
    toks = {t for t in _TOKEN_SPLIT.split(n) if t}
    return bool(toks & _JUNK_GROUP_TOKENS)


def sanitize_segment(seg: str) -> tuple[str | None, bool]:
    """``(word, literal_dot)`` for the DISPLAY channel, or ``(None, False)``
    when the segment is purely organisational.

    * intercepting marker stripped — ``(.)sessions`` -> ``sessions``;
      a bare ``(.)`` / ``(..)`` names nothing -> ``None``;
    * parallel slot dropped — ``@modal`` renders a layout hole, it is not
      a capability;
    * a WHOLE-segment dynamic param is returned untouched (the caller's
      dialect rules already resolve or drop it);
    * escaped literals unwrapped — ``robots[.]txt`` -> ``robots.txt``,
      ``[.]well-known`` -> ``well-known``, ``[-htmltopdf]+`` ->
      ``htmltopdf``; every remaining edge ``+ - _ .`` is peeled.

    ``literal_dot`` is True when an escape unwrap left a dot INSIDE the
    word: that dot is an escaped literal (``[.]`` means "a real dot"), so
    the caller must not read it as a Remix path separator.
    """
    s = (seg or "").strip()
    if not s:
        return None, False
    m = INTERCEPT_PREFIX_RE.match(s)
    if m:
        s = s[m.end():].strip()
        if not s:
            return None, False
    if is_parallel_slot(s):
        return None, False
    if is_dynamic_segment(s):
        return s, False
    if not _ESCAPE_RE.search(s):
        return s, False
    unwrapped = _ESCAPE_RE.sub(lambda mm: mm.group(1), s).strip(_EDGE_PUNCT)
    if not unwrapped:
        return None, False
    return unwrapped, "." in unwrapped


def sanitize_display_text(text: str) -> str:
    """Marker scrub over a FINISHED display string (the M1 filter).

    Word-wise :func:`sanitize_segment` over an already-composed display —
    the last line of defence when a marker reached the display through a
    path this module does not own. Separators (spaces) survive; a word that
    sanitizes to nothing is dropped. Casing/polish is the caller's job.

    Nothing beyond MARKER machinery is touched: a trailing ``+`` on a
    non-escape word is prose on ``ws:``/``fdir:``/``hub:`` anchors
    ('Enterprise+' — the horizon-1 named anti-case), so only
    :func:`sanitize_segment`'s own escape path peels edge punctuation.
    """
    raw = (text or "").strip()
    if not raw:
        return raw
    # A dot-splitting humanizer may already have turned ``(.)`` into
    # ``( )`` / ``()`` — collapse those to nothing before word splitting.
    raw = _INTERCEPT_TEXT_RE.sub("", raw)
    out: list[str] = []
    for word in raw.split(" "):
        w = word.strip()
        if not w:
            continue
        if is_parallel_slot(w) and "/" in w:
            # npm SCOPE ('@types/node', '@scope/pkg') — that ``@`` is
            # package vocabulary, not a router marker. Kept VERBATIM.
            out.append(w)
            continue
        cleaned, _literal = sanitize_segment(w)
        if cleaned is None and is_parallel_slot(w):
            # fixb135 rider — in a DISPLAY string (not a path walk) an
            # ``@slot`` word is the only carrier of meaning, so PEEL the
            # marker instead of dropping it. Dropping is right for the walk
            # (the slot names no capability and a sibling segment carries
            # the name) but on a leaked display it annihilated the row and
            # the raw token survived as the world's last route-token
            # (tracecat PF display '@chat').
            peeled = w.lstrip("@").strip()
            if peeled:
                out.append(peeled)
                continue
        if cleaned:
            out.append(cleaned)
    return " ".join(out).strip()


def has_marker_residue(text: str) -> bool:
    """True when a display still carries ROUTER-MARKER machinery.

    Deliberately narrower than "contains a paren": an authored paren tail
    is product vocabulary (``CalDav (Beta)``) and the doctrine keeps it.
    Three marker SHAPES fire:

    * an intercepting marker (``(.)``, ``( )``, ``()`` — any humanizer
      residue of ``(.)``);
    * an ``@slot`` word;
    * unbalanced parens (a marker was chopped mid-token).
    """
    t = text or ""
    if not t:
        return False
    if _INTERCEPT_TEXT_RE.search(t):
        return True
    if _SLOT_TEXT_RE.search(t):
        return True
    return t.count("(") != t.count(")")
