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
* the handler file of a route comes only from extractors that DECLARE what
  their route site locates (``route_site`` on the extractor class, see
  :data:`ROUTE_SITE_REGISTRATION` / :data:`ROUTE_SITE_HANDLER`); a site of
  any other extractor is not read;
* a file joins the group its own name states when it handles a route of it,
  else the group holding more than half of the routes it handles, else none.

Files that handle no route, or routes of several groups with no majority,
stay on the parent row and stay its own. Nothing is read and nothing changes
unless the row is flat. Deterministic, no model call.
"""

from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from wystan.analyzer.safe_read import path_within_repo
from wystan.pipeline_v2.spine_anchors import (
    _pattern_key_chain,
    _split_tokens,
    load_spine_vocab,
    normalize_anchor_key,
)

# ── What a route site locates (the extractor's declaration) ─────────────────
# An extractor that sets ``route_site`` on its class promises what the
# ``file`` and ``line`` of its route tuples mean. Without the promise a site
# is not evidence: one extractor emits the controller file with a line number
# of the route table, and reading that line in the controller names whatever
# happens to stand there.
#: ``file`` + ``line`` locate the registration statement (the router call);
#: the handler is named on that line.
ROUTE_SITE_REGISTRATION = "registration"
#: ``file`` is the file that defines the handler (the route is declared on
#: the handler itself); ``line`` is not read.
ROUTE_SITE_HANDLER = "handler"
_ROUTE_SITE_KINDS = (ROUTE_SITE_REGISTRATION, ROUTE_SITE_HANDLER)

# ── Floors ──────────────────────────────────────────────────────────────────
# One route is an endpoint, not a route group (the same floor
# ``route_group_recall`` uses for "a group").
MIN_GROUP_ROUTES = 2
# Fewer than two promoted groups is the row itself, not a split.
MIN_GROUPS = 2
# A file whose routes spread over groups with none above half is a route
# table or a shared module: it has no single group to follow.
FILE_GROUP_MAJORITY = 0.5

# ── Bounds for untrusted repositories ───────────────────────────────────────
# Beyond a byte or count cap the planner does nothing for the row: a plan
# built from a truncated view could move files on partial evidence. Files are
# read head-first, line by line, and nothing read is kept after the row.
MAX_ROUTE_SITES = 20_000       # largest measured route table: 558
MAX_FILES_READ = 2_000         # row files + registration files, per row
FILE_HEAD_BYTES = 262_144      # bytes read from the start of one file
MAX_ROW_BYTES = 16_777_216     # bytes read for one row
MAX_SCAN_BYTES = 67_108_864    # bytes read by this planner in one scan
MAX_LINE_CHARS = 2_000         # a longer line is not matched at all
MAX_CALL_DEPTH = 8             # wrappers unwrapped around one handler
# A row name is a URL segment a person reads in a table.
MAX_NAME_CHARS = 40

# Marks the domain key of a route-group row, so a reader can tell it from a
# directory domain (the key is not a path that exists).
ROUTE_GROUP_DOMAIN_PREFIX = "route-group/"

# String literals are blanked (same length, so offsets hold) before a
# registration line is parsed: a permission string such as
# ``"subscribers:get"`` must not read as code.
_STRING_LITERAL_RE = re.compile(r'"[^"\n]*"|\'[^\'\n]*\'|`[^`\n]*`')
_DOTTED_NAME_RE = re.compile(r"[&*]?([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)")
# Top-level function definitions, language-blind. Each is matched against ONE
# line of at most MAX_LINE_CHARS, from the line start, and no two adjacent
# parts of a pattern can match the same character, so matching is linear. A
# local list instead of ``ast_extractor.extract_signatures`` because that one
# lists exported Go names only and reads files of any size.
_DEFINITION_RES: tuple[re.Pattern[str], ...] = (
    # Go: ``func Name(`` / ``func (r *Recv) Name(`` / generic ``Name[T any](``
    re.compile(r"func[ \t]+(?:\([^)]*\)[ \t]*)?([A-Za-z_]\w*)[ \t]*[(\[]"),
    # Python / Ruby: ``def name`` / ``async def name``
    re.compile(r"[ \t]*(?:async[ \t]+)?def[ \t]+([A-Za-z_]\w*)"),
    # JS / TS: ``function name`` / ``function* name`` and ``const name =``
    re.compile(
        r"[ \t]*(?:export[ \t]+)?(?:default[ \t]+)?(?:async[ \t]+)?"
        r"function[ \t*]*([A-Za-z_$][\w$]*)"),
    re.compile(
        r"[ \t]*(?:export[ \t]+)?(?:const|let|var)[ \t]+([A-Za-z_$][\w$]*)[ \t]*="),
    # Rust: ``fn name`` / ``pub async fn name``
    re.compile(
        r"[ \t]*(?:pub(?:\([^)]*\))?[ \t]+)?(?:async[ \t]+)?fn[ \t]+([A-Za-z_]\w*)"),
)
# A segment that is a number, a date or a version says nothing a row could be
# called (``2024``, ``2024-01``, ``v1``, ``v2beta``).
_UNNAMEABLE_SEGMENT_RE = re.compile(r"^(?:[\d._-]+|v\d+[a-z0-9]*)$")


class _OverBudget(Exception):
    """The row would need more reading than the bounds allow."""


@dataclass
class ReadBudget:
    """Bytes this planner has read in the current scan."""

    scan_bytes: int = 0


@dataclass(frozen=True)
class RouteSplitInput:
    """What the route-group planner needs beside the row itself."""

    route_sites: list[dict[str, Any]]
    repo_root: Path
    budget: ReadBudget = field(default_factory=ReadBudget, compare=False)


@dataclass(frozen=True)
class _Resolved:
    """One route attributed to the row file that handles it."""

    file: str
    group: str
    segment: str  # the URL segment as written, for the row name


# ── Route sites from the extractors ─────────────────────────────────────────


def declared_route_site_kinds() -> dict[str, str]:
    """``extractor name -> what its route sites locate`` for the registered
    extractors that declare it."""
    from wystan.pipeline_v2.stage_1_extractors import _discover_extractors

    kinds: dict[str, str] = {}
    for extractor in _discover_extractors():
        kind = getattr(extractor, "route_site", None)
        if kind in _ROUTE_SITE_KINDS:
            kinds[str(getattr(extractor, "name", ""))] = kind
    return kinds


def collect_route_sites(
    extractor_signals: dict[str, Any] | None,
    kinds: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Route sites of the declaring extractors, as plain dicts
    ``{"pattern", "file", "line", "kind"}``. Sorted and de-duplicated so the
    stage input is stable. Sites of an extractor that declares nothing are
    left out: nobody has said what their file and line mean."""
    kinds = declared_route_site_kinds() if kinds is None else kinds
    sites: set[tuple[str, str, int, str]] = set()
    for name, candidates in (extractor_signals or {}).items():
        kind = kinds.get(name)
        if kind is None or not isinstance(candidates, (list, tuple)):
            continue
        for cand in candidates:
            for entry in getattr(cand, "routes", None) or ():
                site = _site_of(entry, kind)
                if site:
                    sites.add(site)
    return [
        {"pattern": p, "file": f, "line": n, "kind": k}
        for p, f, n, k in sorted(sites)
    ]


def _site_of(entry: Any, kind: str) -> tuple[str, str, int, str] | None:
    """``(pattern, file, line, kind)`` of one extractor route tuple."""
    try:
        pattern, file_path = str(entry[0] or ""), str(entry[2] or "")
    except (IndexError, TypeError):
        return None
    if not pattern or not _is_repo_relative(file_path):
        return None
    line = 0
    if kind == ROUTE_SITE_REGISTRATION:
        line = entry[3] if len(entry) > 3 and isinstance(entry[3], int) else 0
        if line <= 0:
            return None  # a registration site without its line locates nothing
    return pattern, file_path, line, kind


def _is_repo_relative(path: str) -> bool:
    parts = path.split("/")
    return bool(path) and not path.startswith("/") and ".." not in parts


def is_flat(owned: list[str]) -> bool:
    """All files sit directly in one directory."""
    return len({os.path.dirname(p) for p in owned}) == 1


# ── The plan ────────────────────────────────────────────────────────────────


def plan_route_group_split(
    owned: list[str],
    split_input: RouteSplitInput,
    *,
    parent_name: str,
    used_names: set[str],
    min_files: int = 1,
    max_domains: int | None = None,
) -> tuple[dict[str, list[str]], list[str]]:
    """Partition a flat row into ``{row name: [files]}`` + residual.

    Returns ``({}, owned)`` when the rule does not apply. Every input file is
    in exactly one output bucket. *min_files* is the stage's grain floor: a
    group with fewer files is not a row. Names promoted here are added to
    *used_names*.
    """
    nothing: tuple[dict[str, list[str]], list[str]] = ({}, list(owned))
    sites = split_input.route_sites or []
    if not sites or len(sites) > MAX_ROUTE_SITES or not is_flat(owned):
        return nothing
    try:
        resolved = _resolve_handlers(sorted(owned), sites, split_input)
    except _OverBudget:
        return nothing
    groups = {
        g: fr for g, fr in _group_files(resolved).items()
        if len(fr[0]) >= min_files
    }
    ranked = sorted(groups.items(), key=lambda kv: (-kv[1][1], kv[0]))
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


# ── Bounded reading ─────────────────────────────────────────────────────────


class _Reader:
    """Reads the head of a file once, inside the repository, counting every
    byte against the row's and the scan's budget. Keeps nothing."""

    def __init__(self, split_input: RouteSplitInput) -> None:
        self._root = Path(split_input.repo_root)
        self._budget = split_input.budget
        self._row_bytes = 0
        self._files = 0

    def lines(self, rel_path: str) -> list[str]:
        """Lines of the file's head; a line over the bound is emptied."""
        self._files += 1
        if self._files > MAX_FILES_READ:
            raise _OverBudget
        path = self._root / rel_path
        if not _is_repo_relative(rel_path) or not path_within_repo(path, self._root):
            return []
        try:
            with open(path, "rb") as handle:
                head = handle.read(FILE_HEAD_BYTES)
        except OSError:
            return []
        self._row_bytes += len(head)
        self._budget.scan_bytes += len(head)
        if (self._row_bytes > MAX_ROW_BYTES
                or self._budget.scan_bytes > MAX_SCAN_BYTES):
            raise _OverBudget
        text = head.decode("utf-8", errors="replace")
        return [ln if len(ln) <= MAX_LINE_CHARS else "" for ln in text.split("\n")]


def _definers(owned: list[str], reader: _Reader) -> dict[str, set[str]]:
    """``identifier -> row files that define a function of that name``."""
    out: dict[str, set[str]] = defaultdict(set)
    for path in owned:
        for line in reader.lines(path):
            for definition_re in _DEFINITION_RES:
                match = definition_re.match(line)
                if match:
                    out[match.group(1)].add(path)
    return out


# ── Handler resolution ──────────────────────────────────────────────────────


def _resolve_handlers(
    owned: list[str], sites: list[dict[str, Any]], split_input: RouteSplitInput,
) -> list[_Resolved]:
    """Attribute each route to the row file that handles it."""
    owned_set = set(owned)
    out: list[_Resolved] = []
    by_registration: dict[str, list[tuple[int, str, tuple[str, str]]]] = defaultdict(list)
    for site in sites:
        group = _group_of_pattern(str(site.get("pattern") or ""))
        if group is None:
            continue
        file_path, kind = str(site.get("file") or ""), site.get("kind")
        if kind == ROUTE_SITE_HANDLER and file_path in owned_set:
            out.append(_Resolved(file_path, *group))
        elif kind == ROUTE_SITE_REGISTRATION:
            by_registration[file_path].append(
                (int(site.get("line") or 0), str(site["pattern"]), group))
    if not by_registration:
        return out
    reader = _Reader(split_input)
    definers = _definers(owned, reader)
    for file_path in sorted(by_registration):
        lines = reader.lines(file_path)
        for number, pattern, group in sorted(by_registration[file_path]):
            line = lines[number - 1] if 0 < number <= len(lines) else ""
            handler_file = _handler_file(line, pattern, definers)
            if handler_file:
                out.append(_Resolved(handler_file, *group))
    return out


def _group_of_pattern(pattern: str) -> tuple[str, str] | None:
    """``(group key, URL segment as written)`` of a route, or ``None`` when
    the URL has no meaningful segment (``/``, ``/:id``, ``/api``)."""
    vocab = load_spine_vocab()
    version_re = re.compile(vocab.get("version_segment_pattern") or r"^v\d+$")
    chain = _pattern_key_chain(pattern, vocab, version_re)
    if not chain:
        return None
    key = normalize_anchor_key(chain[0])
    return (key, chain[0]) if key else None


def _handler_file(
    line: str, pattern: str, definers: dict[str, set[str]],
) -> str | None:
    """The row file that defines the handler named on a registration line.

    Only the handler POSITION counts: each argument after the route literal,
    unwrapped through the calls around its first argument
    (``guard(h.List, "perm")`` -> ``List``). A row function that is merely
    passed along (a second argument of a wrapper) is not a handler. When two
    arguments name functions of two row files the handler cannot be told
    from the middleware, and the route resolves to nothing."""
    at = line.find(pattern) if pattern else -1
    if at < 0:
        return None
    masked = _STRING_LITERAL_RE.sub(lambda m: " " * len(m.group()), line)
    arguments = _split_arguments(masked[at:])[1:]  # [0] is the route literal
    files: set[str] = set()
    for argument in arguments:
        name = _handler_name(argument)
        if name and len(definers.get(name, ())) == 1:
            files |= definers[name]
    return next(iter(files)) if len(files) == 1 else None


def _split_arguments(text: str) -> list[str]:
    """Top-level comma-separated pieces of *text*, up to the bracket that
    closes the call *text* starts inside."""
    pieces, depth, start = [], 0, 0
    for index, char in enumerate(text):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if depth < 0:
                pieces.append(text[start:index])
                return pieces
        elif char == "," and depth == 0:
            pieces.append(text[start:index])
            start = index + 1
    pieces.append(text[start:])
    return pieces


def _handler_name(argument: str) -> str | None:
    """The function an argument stands for: itself when it is a name, the
    first argument (recursively) when it is a call with arguments, the callee
    when the call has none (a factory)."""
    for _ in range(MAX_CALL_DEPTH):
        argument = argument.strip()
        match = _DOTTED_NAME_RE.match(argument)
        if not match:
            return None
        name = match.group(1).rsplit(".", 1)[-1]
        rest = argument[match.end():].lstrip()
        if not rest:
            return name
        if not rest.startswith("("):
            return None
        first = _split_arguments(rest[1:])[0].strip()
        if not first:
            return name
        argument = first
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


def _lawful_name(base: str, parent: str, taken: set[str]) -> str | None:
    """The row name for a group whose URL segment slugs to *base*, or
    ``None`` when it has none: a number, a date or a version is not a name;
    the parent's own name stays with the parent (never ``orders-orders``); a
    name another row has is qualified by the parent, once, never numbered."""
    if not base or base == parent or _UNNAMEABLE_SEGMENT_RE.match(base):
        return None
    name = base if base not in taken else f"{parent}-{base}"
    if name in taken or len(name) > MAX_NAME_CHARS:
        return None
    return name


def _name_groups(
    ranked: list[tuple[str, tuple[list[str], int]]],
    resolved: list[_Resolved],
    parent_name: str,
    used_names: set[str],
) -> dict[str, list[str]]:
    """Row name per group: the URL segment as its routes write it. A group
    that cannot get a lawful name is not promoted (its files stay)."""
    group_of_file = {f: g for g, (files, _n) in ranked for f in files}
    written: dict[str, Counter] = defaultdict(Counter)
    for r in resolved:
        if group_of_file.get(r.file) == r.group:
            written[r.group][_slug(r.segment)] += 1
    taken = set(used_names)
    named: dict[str, list[str]] = {}
    for group, (files, _routes) in ranked:
        base = min(written[group].items(), key=lambda kv: (-kv[1], kv[0]))[0]
        name = _lawful_name(base, _slug(parent_name), taken)
        if name is None:
            continue
        taken.add(name)
        named[name] = files
    return named


# ── Flows follow their entry files ──────────────────────────────────────────


def apply_flow_moves(
    flows: Iterable[Any], edges: Iterable[Any], flow_moves: dict[str, str],
) -> None:
    """Make the flow store agree with the rows after Stage 8.9 moved flows:
    each moved flow's ``primary_feature`` and primary edge name the row that
    lists it now. Id, uuid and name are untouched; applying twice is the same
    as once."""
    if not flow_moves:
        return
    for flow in flows or ():
        target = flow_moves.get(str(getattr(flow, "id", "") or ""))
        if target:
            flow.primary_feature = target
    for edge in edges or ():
        target = flow_moves.get(str(getattr(edge, "flow_id", "") or ""))
        if target and getattr(edge, "type", None) == "primary":
            edge.feature = target


__all__ = [
    "MIN_GROUPS",
    "MIN_GROUP_ROUTES",
    "ROUTE_GROUP_DOMAIN_PREFIX",
    "ROUTE_SITE_HANDLER",
    "ROUTE_SITE_REGISTRATION",
    "ReadBudget",
    "RouteSplitInput",
    "collect_route_sites",
    "declared_route_site_kinds",
    "is_flat",
    "apply_flow_moves",
    "plan_route_group_split",
]
