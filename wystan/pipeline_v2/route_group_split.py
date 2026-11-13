"""Route-group plan for a flat oversized row (Stage 8.9, second planner).

Stage 8.9 splits an oversized row along its directories. A row whose files
all sit directly in ONE directory has no directory to split along, so the
directory planner returns nothing and the row stays whole whatever it holds
(a flat handler package serving a dozen URL groups becomes one row, and the
whole row takes the name of whichever capability its few flows vote for).

This planner is consulted only then. It groups the row's files by the ROUTE
GROUP whose handlers they define:

* the route group of a route is the first meaningful segment of its URL
  (:func:`spine_anchors._pattern_key_chain`: parameters, ``api``-like
  prefixes and version prefixes are transparent);
* the handler file of a route is the row file that defines an identifier
  named on the route's registration line, or the route's own file when the
  extractor records no registration line (decorator-style routers declare
  the route on the handler);
* a file joins the group its own name states when it handles a route of it,
  else the group holding more than half of the routes it handles, else none.

Files that handle no route, or routes of several groups with no majority,
stay on the parent row. Nothing is read and nothing changes unless the row is
flat, and no split happens with fewer than two groups of two routes each.
Deterministic, no model call.
"""

from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from wystan.analyzer.safe_read import safe_read_text
from wystan.pipeline_v2.spine_anchors import (
    _is_version_seg,
    _pattern_key_chain,
    _split_tokens,
    load_spine_vocab,
    normalize_anchor_key,
)

# One route is an endpoint, not a route group (the same floor
# ``route_group_recall`` uses for "a group").
MIN_GROUP_ROUTES = 2
# Fewer than two promoted groups is the row itself, not a split.
MIN_GROUPS = 2
# A file whose routes spread over groups with none above half is a route
# table or a shared module: it has no single group to follow.
FILE_GROUP_MAJORITY = 0.5
# An identifier named on the registration lines of two different route
# groups wraps handlers (permission check, id guard); it is not a handler of
# either group and is skipped when the handler file is resolved.
WRAPPER_MIN_GROUPS = 2

# ── Bounds for untrusted repositories ───────────────────────────────────────
# Beyond any of the first three the planner does nothing: a plan built from a
# truncated view of the routes or of the row could move files on partial
# evidence. The values are far above any measured repository (the largest
# recorded row has 593 files, the largest route table 450 routes) and only
# cap the work one hostile row can demand.
MAX_ROUTE_SITES = 20_000
MAX_FILES_READ = 2_000        # row files + registration files, per row
MAX_SOURCE_BYTES = 1_000_000  # a larger file is skipped (generated or data)
MAX_LINE_CHARS = 2_000        # registration line prefix that is tokenised
MAX_LINE_IDENTIFIERS = 16     # identifiers of one line that are looked up

# Marks the domain key of a route-group row, so a reader can tell it from a
# directory domain (the key is not a path that exists).
ROUTE_GROUP_DOMAIN_PREFIX = "route-group/"

_IDENTIFIER_RE = re.compile(r"[A-Za-z_$][\w$]*")
# String literals are blanked (same length, so offsets hold) before a
# registration line is tokenised: a permission string such as
# ``"subscribers:get"`` must not read as the identifiers ``subscribers``/``get``.
_STRING_LITERAL_RE = re.compile(r'"[^"\n]*"|\'[^\'\n]*\'|`[^`\n]*`')
# Top-level function definitions, language-blind: each alternative is anchored
# at a line start and has no nested quantifier, so matching is linear. A
# local list instead of ``ast_extractor.extract_signatures`` because that one
# lists exported Go names only and reads files of any size.
_DEFINITION_RES: tuple[re.Pattern[str], ...] = (
    # Go: ``func Name(`` / ``func (r *Recv) Name(`` / generic ``Name[T any](``
    re.compile(r"^func[ \t]+(?:\([^)\n]*\)[ \t]*)?([A-Za-z_]\w*)[ \t]*[(\[]", re.M),
    # Python / Ruby: ``def name`` / ``async def name``
    re.compile(r"^[ \t]*(?:async[ \t]+)?def[ \t]+([A-Za-z_]\w*)", re.M),
    # JS / TS: ``function name`` and ``const name =``
    re.compile(
        r"^[ \t]*(?:export[ \t]+)?(?:default[ \t]+)?(?:async[ \t]+)?"
        r"function[ \t]*\*?[ \t]*([A-Za-z_$][\w$]*)", re.M),
    re.compile(
        r"^[ \t]*(?:export[ \t]+)?(?:const|let|var)[ \t]+([A-Za-z_$][\w$]*)[ \t]*=",
        re.M),
    # Rust: ``fn name`` / ``pub async fn name``
    re.compile(
        r"^[ \t]*(?:pub(?:\([^)\n]*\))?[ \t]+)?(?:async[ \t]+)?fn[ \t]+([A-Za-z_]\w*)",
        re.M),
)


@dataclass(frozen=True)
class RouteSplitInput:
    """What the route-group planner needs beside the row itself."""

    route_sites: list[dict[str, Any]]
    repo_root: Path


@dataclass(frozen=True)
class _Resolved:
    """One route attributed to the row file that handles it."""

    file: str
    group: str
    segment: str  # the URL segment as written, for the row name


def collect_route_sites(
    extractor_signals: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Every explicit route an extractor recorded, as plain dicts
    ``{"pattern", "file", "line"}`` (``line`` 0 when the extractor records
    none). Sorted and de-duplicated so the stage input is stable."""
    sites: set[tuple[str, str, int]] = set()
    for name, candidates in (extractor_signals or {}).items():
        if name == "_errors" or not isinstance(candidates, (list, tuple)):
            continue
        for cand in candidates:
            for entry in getattr(cand, "routes", None) or ():
                site = _site_of(entry)
                if site:
                    sites.add(site)
    return [
        {"pattern": p, "file": f, "line": n} for p, f, n in sorted(sites)
    ]


def _site_of(entry: Any) -> tuple[str, str, int] | None:
    """``(pattern, file, line)`` of one extractor route tuple, or ``None``."""
    try:
        pattern, file_path = str(entry[0] or ""), str(entry[2] or "")
    except (IndexError, TypeError):
        return None
    line = entry[3] if len(entry) > 3 and isinstance(entry[3], int) else 0
    if not pattern or not file_path:
        return None
    return pattern, file_path, max(0, line)


def is_flat(owned: list[str]) -> bool:
    """All files sit directly in one directory."""
    return len({os.path.dirname(p) for p in owned}) == 1


def plan_route_group_split(
    owned: list[str],
    split_input: RouteSplitInput,
    *,
    parent_name: str,
    used_names: set[str],
    max_domains: int | None = None,
) -> tuple[dict[str, list[str]], list[str]]:
    """Partition a flat row into ``{row name: [files]}`` + residual.

    Returns ``({}, owned)`` when the rule does not apply. Every input file is
    in exactly one output bucket. Names promoted here are added to
    *used_names*.
    """
    nothing: tuple[dict[str, list[str]], list[str]] = ({}, list(owned))
    sites = split_input.route_sites or []
    if not sites or len(sites) > MAX_ROUTE_SITES or not is_flat(owned):
        return nothing
    resolved = _resolve_handlers(owned, sites, split_input.repo_root)
    if resolved is None:
        return nothing
    groups = _group_files(resolved)
    ranked = sorted(groups.items(), key=lambda kv: (-kv[1][1], kv[0]))
    if len(ranked) < MIN_GROUPS:
        return nothing
    # The stage's anti-shatter cap, unchanged: the groups with most routes
    # survive, the tail stays on the parent.
    if max_domains is not None:
        ranked = ranked[: max(MIN_GROUPS, max_domains)]
    named = _name_groups(ranked, resolved, parent_name, used_names)
    if len(named) < MIN_GROUPS:
        return nothing
    used_names.update(named)
    moved = {f for files in named.values() for f in files}
    return named, [p for p in owned if p not in moved]


# ── Handler resolution ──────────────────────────────────────────────────────


def _resolve_handlers(
    owned: list[str], sites: list[dict[str, Any]], repo_root: Path,
) -> list[_Resolved] | None:
    """Attribute each route to the row file that handles it. ``None`` when
    the work would exceed the read budget."""
    keyed = [(s, _group_of_pattern(str(s.get("pattern") or ""))) for s in sites]
    keyed = [(s, g) for s, g in keyed if g is not None]
    registration_files = {
        str(s.get("file") or "") for s, _ in keyed if s.get("line")
    }
    if len(owned) + len(registration_files - set(owned)) > MAX_FILES_READ:
        return None
    reader = _Reader(repo_root)
    definers = _definers(owned, reader)
    owned_set = set(owned)
    candidates = [
        _line_candidates(s, reader, definers) if s.get("line") else None
        for s, _ in keyed
    ]
    wrappers = _wrappers(candidates, [g for _, g in keyed])
    out: list[_Resolved] = []
    for (site, (group, segment)), names in zip(keyed, candidates):
        handler_file = _handler_file(site, names, wrappers, definers, owned_set)
        if handler_file:
            out.append(_Resolved(handler_file, group, segment))
    return out


def _group_of_pattern(pattern: str) -> tuple[str, str] | None:
    """``(group key, URL segment as written)`` of a route, or ``None`` when
    the URL has no meaningful segment (``/``, ``/:id``, ``/api``, ``/v1``)."""
    vocab = load_spine_vocab()
    version_re = re.compile(vocab.get("version_segment_pattern") or r"^v\d+$")
    chain = _pattern_key_chain(pattern, vocab, version_re)
    if not chain or _is_version_seg(chain[0], version_re):
        return None
    key = normalize_anchor_key(chain[0])
    return (key, chain[0]) if key else None


class _Reader:
    """Reads each file once, inside the repository, under the size bound."""

    def __init__(self, repo_root: Path) -> None:
        self._root = Path(repo_root)
        self._text: dict[str, str] = {}
        self._lines: dict[str, list[str]] = {}

    def text(self, rel_path: str) -> str:
        if rel_path not in self._text:
            self._text[rel_path] = safe_read_text(
                self._root / rel_path, self._root,
                encoding="utf-8", errors="replace", max_bytes=MAX_SOURCE_BYTES,
            ) or ""
        return self._text[rel_path]

    def line(self, rel_path: str, number: int) -> str:
        if rel_path not in self._lines:
            self._lines[rel_path] = self.text(rel_path).split("\n")
        lines = self._lines[rel_path]
        return lines[number - 1] if 0 < number <= len(lines) else ""


def _definers(owned: list[str], reader: _Reader) -> dict[str, set[str]]:
    """``identifier -> row files that define a function of that name``."""
    out: dict[str, set[str]] = defaultdict(set)
    for path in owned:
        text = reader.text(path)
        for definition_re in _DEFINITION_RES:
            for match in definition_re.finditer(text):
                out[match.group(1)].add(path)
    return out


def _line_candidates(
    site: dict[str, Any], reader: _Reader, definers: dict[str, set[str]],
) -> list[str]:
    """Identifiers after the route literal on the registration line that
    exactly one row file defines, in order."""
    raw = reader.line(str(site.get("file") or ""), int(site.get("line") or 0))
    raw = raw[:MAX_LINE_CHARS]
    masked = _STRING_LITERAL_RE.sub(lambda m: " " * len(m.group()), raw)
    at = raw.find(str(site.get("pattern") or ""))
    tail = masked[at:] if at >= 0 else masked
    names = _IDENTIFIER_RE.findall(tail)[:MAX_LINE_IDENTIFIERS]
    return [n for n in names if len(definers.get(n, ())) == 1]


def _wrappers(
    candidates: list[list[str] | None], groups: list[tuple[str, str]],
) -> set[str]:
    """Identifiers named on the registration lines of several route groups."""
    seen: dict[str, set[str]] = defaultdict(set)
    for names, (group, _segment) in zip(candidates, groups):
        for name in names or ():
            seen[name].add(group)
    return {n for n, gs in seen.items() if len(gs) >= WRAPPER_MIN_GROUPS}


def _handler_file(
    site: dict[str, Any],
    names: list[str] | None,
    wrappers: set[str],
    definers: dict[str, set[str]],
    owned: set[str],
) -> str | None:
    """The row file that handles *site*, or ``None``.

    With a registration line: the first identifier on it that one row file
    defines and that is not a wrapper. Without one the extractor recorded the
    declaring file, which is the handler file when it is in the row."""
    if names is None:
        file_path = str(site.get("file") or "")
        return file_path if file_path in owned else None
    for name in names:
        if name not in wrappers:
            return next(iter(definers[name]))
    return None


# ── Grouping and naming ─────────────────────────────────────────────────────


def _stem_keys(path: str) -> list[str]:
    """Group keys a file name states: its stem, then the stem's first word
    (``campaign_analytics`` states ``campaign-analytic``, then ``campaign``)."""
    stem = os.path.basename(path).rsplit(".", 1)[0]
    tokens = _split_tokens(stem)
    keys = [normalize_anchor_key(stem)]
    if len(tokens) > 1:
        keys.append(normalize_anchor_key(tokens[0]))
    return [k for k in keys if k]


def _group_of_file(path: str, handled: Counter) -> str | None:
    """The one group a file follows (see the module docstring), or ``None``."""
    for key in _stem_keys(path):
        if handled.get(key):
            return key
    top_key, top = min(handled.items(), key=lambda kv: (-kv[1], kv[0]))
    if top > FILE_GROUP_MAJORITY * sum(handled.values()):
        return top_key
    return None


def _group_files(
    resolved: Iterable[_Resolved],
) -> dict[str, tuple[list[str], int]]:
    """``group -> (files, routes those files handle of that group)`` for the
    groups that reach :data:`MIN_GROUP_ROUTES`."""
    by_file: dict[str, Counter] = defaultdict(Counter)
    for r in resolved:
        by_file[r.file][r.group] += 1
    files: dict[str, list[str]] = defaultdict(list)
    routes: Counter = Counter()
    for path in sorted(by_file):
        group = _group_of_file(path, by_file[path])
        if group is not None:
            files[group].append(path)
            routes[group] += by_file[path][group]
    return {
        g: (files[g], routes[g]) for g in files
        if routes[g] >= MIN_GROUP_ROUTES
    }


def _slug(segment: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", segment.lower()).strip("-")


def _name_groups(
    ranked: list[tuple[str, tuple[list[str], int]]],
    resolved: list[_Resolved],
    parent_name: str,
    used_names: set[str],
) -> dict[str, list[str]]:
    """Row name per group: the URL segment as the routes write it. A name
    another row already has is qualified by the parent (``<parent>-<name>``);
    if that is taken too the group is not promoted. Never numbered: a
    ``name-2`` row says nothing about what it holds."""
    group_of_file = {f: g for g, (files, _n) in ranked for f in files}
    written: dict[str, Counter] = defaultdict(Counter)
    for r in resolved:
        if group_of_file.get(r.file) == r.group:
            written[r.group][_slug(r.segment)] += 1
    taken = set(used_names)
    named: dict[str, list[str]] = {}
    for group, (files, _routes) in ranked:
        base = min(written[group].items(), key=lambda kv: (-kv[1], kv[0]))[0]
        if not base:
            continue
        name = base if base not in taken else f"{_slug(parent_name)}-{base}"
        if name in taken:
            continue
        taken.add(name)
        named[name] = files
    return named


__all__ = [
    "MIN_GROUPS",
    "MIN_GROUP_ROUTES",
    "ROUTE_GROUP_DOMAIN_PREFIX",
    "RouteSplitInput",
    "collect_route_sites",
    "is_flat",
    "plan_route_group_split",
]
