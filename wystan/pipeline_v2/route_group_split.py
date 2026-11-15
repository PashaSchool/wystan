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
* a registration resolves to a row file only when every function reference
  on its line names that one file (handler and middleware cannot be told
  apart on the line); a qualified reference is read with its qualifier,
  from the registering file's imports and declarations
  (:mod:`route_group_scope`), and an inline function is a handler of the
  registering file;
* a file joins the group its own name states when it handles a route of it,
  else the group holding more than half of the routes it handles, else none;
* a group is a row when it has two routes and at least the median lines of
  the repository's other rows, and two such groups exist.

Files that handle no route, or routes of several groups with no majority,
stay on the parent row and stay its own. Per row the plan is all or nothing:
a bound reached or a needed line not read stops it, and says why. Nothing is
read and nothing changes unless the row is flat. Deterministic, no model
call.
"""

from __future__ import annotations

import os
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, NamedTuple

from wystan.analyzer.safe_read import path_within_repo
from wystan.pipeline_v2.route_group_scope import (
    ROW,
    FileScope,
    file_scope,
    package_clause,
)
from wystan.pipeline_v2.journey_lattice import (
    _CRUD_LEAF_SEGS as GENERIC_ROUTE_SEGMENTS,
)
from wystan.pipeline_v2.journey_lattice import (
    _TIER_SEGS as ACCESS_TIER_SEGMENTS,
)
from wystan.pipeline_v2.spine_anchors import (
    _pattern_key_chain,
    _split_tokens,
    load_spine_vocab,
    normalize_anchor_key,
)
from wystan.pipeline_v2.stage_6_9_test_strip import is_test_path
from wystan.pipeline_v2.stage_6_97_feature_loc import (
    _is_excluded_name,
    count_file_loc,
)
from wystan.pipeline_v2.stage_6_9b_generated_strip import is_generated_path

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
# ``route_group_recall`` uses for "a group"). A route is a distinct
# ``(method, pattern)``: GET and POST on one URL are two things a user does.
MIN_GROUP_ROUTES = 2
# Fewer than two promoted groups is the row itself, not a split.
MIN_GROUPS = 2
# A file whose routes spread over groups with none above half is a route
# table or a shared module: it has no single group to follow.
FILE_GROUP_MAJORITY = 0.5

# ── Bounds for untrusted repositories ───────────────────────────────────────
# Beyond a byte or count cap the planner does nothing for the row, and says
# why (``SKIP_*`` below): a plan built from a truncated view could move files
# on partial evidence. Files are read head-first, line by line, and nothing
# read is kept after the row.
MAX_ROUTE_SITES = 20_000       # largest measured route table: 558
MAX_FILES_READ = 2_000         # row files + registration files, per row
FILE_HEAD_BYTES = 262_144      # bytes read from the start of one file
MAX_ROW_BYTES = 16_777_216     # bytes read for one row
MAX_SCAN_BYTES = 67_108_864    # bytes read by this planner in one scan
MAX_LINE_CHARS = 2_000         # a longer line is not read
MAX_CALL_DEPTH = 8             # wrappers unwrapped around one handler
# A row name is a URL segment a person reads in a table.
MAX_NAME_CHARS = 40

# Why a row the planner was consulted for is not split (Stage 8.9 telemetry).
#: a count or byte bound above was reached
SKIP_OVER_BUDGET = "over_budget"
#: a route needs a line the planner did not read (past a file's head, or a
#: line over ``MAX_LINE_CHARS``), so the route's file cannot be known
SKIP_TRUNCATED_DEFINITION = "truncated_definition"
#: the row's flow moves would chain back onto an id they started from, so
#: no final id exists for them
SKIP_MOVE_CYCLE = "move_cycle"
#: at the end of the stage a moved flow's final id is held by no flow, so an
#: edge or copy rewritten to it would name nothing; the split is put back
SKIP_DANGLING_REFERENCE = "dangling_reference"
#: an undone split's parent lacks, after the undo, a file, member or flow it
#: had before the split (recorded beside ``dangling_reference``, with counts)
SKIP_UNDO_INCOMPLETE = "undo_incomplete"

# Prefixes the domain key of a route-group row in the text of its
# description (``sub-domain 'route-group/<group key>' of feature '<parent>'``),
# which also feeds the row's uuid. The text is never read back: which rows
# were born, and for which group, is the stage's own record below.
ROUTE_GROUP_DOMAIN_PREFIX = "route-group/"
# Where that record travels: Stage 8.9's telemetry in ``scan_meta``, the
# stage output every later stage of the scan (and every replay capture of
# Stage 6.86 and after) already receives. ``{row name: route group key}``,
# present only when the split bore a row.
STAGE_8_9_META_KEY = "stage_8_9_subdecompose"
BORN_ROWS_KEY = "route_group_born"

# String literals are blanked (same length, so offsets hold) before a
# registration line is parsed: a permission string such as
# ``"subscribers:get"`` must not read as code.
_STRING_LITERAL_RE = re.compile(r'"[^"\n]*"|\'[^\'\n]*\'|`[^`\n]*`')
_DOTTED_NAME_RE = re.compile(r"[&*]?([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)")
# An inline function as an argument: Go ``func(``, JS ``function`` /
# ``async`` / arrow, Python ``lambda``, Rust ``|x|``. Matched from the
# argument's start; each alternative is linear.
_INLINE_FUNCTION_RE = re.compile(
    r"func[ \t]*\(|function\b|async\b|lambda\b|\|[^|]*\||"
    r"\([^()]*\)[ \t]*=>|[A-Za-z_$][\w$]*[ \t]*=>")
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
# Generic URL segments are the engine's own list, not a new one:
# ``journey_lattice._CRUD_LEAF_SEGS`` (``new``, ``edit``, ``index``, ``list``,
# ``detail``...), the segments it never takes for an object, imported above
# as ``GENERIC_ROUTE_SEGMENTS``. Matched against the segment as written, so
# ``lists`` (an object) is a name where ``list`` (an action) is not.
# Access tiers are the engine's own list too: ``journey_lattice._TIER_SEGS``
# (``public``, ``internal``, ``management``, ``client``), the segments it
# reads as an architecture split, not an object, imported above as
# ``ACCESS_TIER_SEGMENTS``. A group behind one is an audience of the
# product, not a capability, so it names no row. Matched as written, like
# the generic segments (``clients``, an object, stays a name).
# A segment that is a number, a date or a version says nothing a row could be
# called (``2024``, ``2024-01``, ``v1``, ``v2beta``).
_UNNAMEABLE_SEGMENT_RE = re.compile(r"^(?:[\d._-]+|v\d+[a-z0-9]*)$")


class _NotSplit(Exception):
    """The row is not split, for the reason the subclass names. Per row the
    split is all or nothing: a plan of the routes that could be read would
    move files on part of the evidence."""

    reason = ""


class _OverBudget(_NotSplit):
    """The row would need more reading than the bounds allow."""

    reason = SKIP_OVER_BUDGET


class _TruncatedDefinition(_NotSplit):
    """A route needs a line that lies beyond what was read."""

    reason = SKIP_TRUNCATED_DEFINITION


@dataclass
class ReadBudget:
    """Bytes this planner has read in the current scan, and the lines of the
    files it has counted (a file's lines are counted once per scan)."""

    scan_bytes: int = 0
    file_lines: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class RouteSplitInput:
    """What the route-group planner needs beside the row itself."""

    route_sites: list[dict[str, Any]]
    repo_root: Path
    budget: ReadBudget = field(default_factory=ReadBudget, compare=False)


class RoutePlan(NamedTuple):
    """The planner's answer for one row."""

    domains: dict[str, list[str]]  # row name -> files, empty when no split
    residual: list[str]            # files that stay with the parent
    groups_capped: int = 0         # groups left in the residual by the cap
    skip_reason: str | None = None  # SKIP_* when a bound stopped the plan
    # row name -> the route group key it was promoted for (``user`` for the
    # row ``users``, ``auth`` for ``cmd-auth``); ``None`` when no split
    groups: dict[str, str] | None = None


@dataclass(frozen=True)
class _Resolved:
    """One route attributed to the row file that handles it."""

    file: str
    group: str
    segment: str  # the URL segment as written, for the row name
    route: tuple[str, str]  # (method, pattern): GET and POST are two routes


@dataclass(frozen=True)
class _Group:
    """The files a route group takes, the routes they handle, their lines."""

    files: list[str]
    routes: frozenset[tuple[str, str]]
    lines: int = 0


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
    ``{"pattern", "method", "file", "line", "kind"}``. Sorted and
    de-duplicated so the stage input is stable. Sites of an extractor that
    declares nothing are left out: nobody has said what their file and line
    mean."""
    kinds = declared_route_site_kinds() if kinds is None else kinds
    sites: set[tuple[str, str, str, int, str]] = set()
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
        {"pattern": p, "method": m, "file": f, "line": n, "kind": k}
        for p, m, f, n, k in sorted(sites)
    ]


def _site_of(entry: Any, kind: str) -> tuple[str, str, str, int, str] | None:
    """``(pattern, method, file, line, kind)`` of one extractor route tuple
    ``(pattern, method, file, ...)``."""
    try:
        pattern, method = str(entry[0] or ""), str(entry[1] or "").upper()
        file_path = str(entry[2] or "")
    except (IndexError, TypeError):
        return None
    if not pattern or not _is_repo_relative(file_path):
        return None
    line = 0
    if kind == ROUTE_SITE_REGISTRATION:
        line = entry[3] if len(entry) > 3 and isinstance(entry[3], int) else 0
        if line <= 0:
            return None  # a registration site without its line locates nothing
    return pattern, method, file_path, line, kind


def _is_repo_relative(path: str) -> bool:
    parts = path.split("/")
    return bool(path) and not path.startswith("/") and ".." not in parts


def born_route_groups(scan_meta: Any) -> dict[str, str]:
    """``{row name: route group key}`` of the rows Stage 8.9 bore in this
    scan, from its record in *scan_meta*; empty when it bore none."""
    stage = (scan_meta or {}).get(STAGE_8_9_META_KEY) if isinstance(
        scan_meta, dict) else None
    born = (stage or {}).get(BORN_ROWS_KEY) if isinstance(stage, dict) else None
    if not isinstance(born, dict):
        return {}
    return {str(name): str(group) for name, group in born.items()}


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
    other_rows: Iterable[list[str]] = (),
    max_domains: int | None = None,
) -> RoutePlan:
    """Partition a flat row into ``{row name: [files]}`` + residual.

    The domains are empty when the rule does not apply. Every input file is
    in exactly one output bucket. *other_rows* are the files of every other
    developer row of the repository: a group whose files have fewer lines
    than the median of those rows is not a row. Names promoted here are
    added to *used_names*.
    """
    nothing = RoutePlan({}, list(owned))
    sites = split_input.route_sites or []
    if not sites or not is_flat(owned):
        return nothing
    try:
        if len(sites) > MAX_ROUTE_SITES:
            raise _OverBudget
        resolved = _resolve_handlers(sorted(owned), sites, split_input)
        groups = _group_files(resolved)
        if len(groups) >= MIN_GROUPS:  # lines are counted only when needed
            groups = _at_line_floor(groups, list(other_rows), split_input)
    except _NotSplit as stop:
        return nothing._replace(skip_reason=stop.reason)
    if len(groups) < MIN_GROUPS:
        return nothing
    ranked, capped = _rank_and_cap(groups, max_domains)
    named, group_of_name = _name_groups(ranked, resolved, parent_name, used_names)
    if len(named) < MIN_GROUPS:
        return nothing
    used_names.update(named)
    moved = {f for files in named.values() for f in files}
    return RoutePlan(named, [p for p in owned if p not in moved], capped,
                     groups=group_of_name)


def _rank_and_cap(
    groups: dict[str, _Group], max_domains: int | None,
) -> tuple[list[tuple[str, _Group]], int]:
    """Groups by size, largest first, cut to the stage's anti-shatter cap.

    Size is lines, then routes, then the key, so the groups kept when the
    cap bites are the largest pieces of the product and the order never
    depends on the order of the files. Returns the kept groups and how many
    the cap left in the residual."""
    ranked = sorted(
        groups.items(),
        key=lambda kv: (-kv[1].lines, -len(kv[1].routes), kv[0]),
    )
    if max_domains is None:
        return ranked, 0
    keep = max(MIN_GROUPS, max_domains)
    return ranked[:keep], max(0, len(ranked) - keep)


# ── Bounded reading ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _FileView:
    """The lines read of one file. ``None`` stands for a line that was not
    read (longer than ``MAX_LINE_CHARS``); *is_cut* says the file goes on
    past the head, so a line beyond the last one read is unknown too."""

    lines: list[str | None]
    is_cut: bool = False

    def line(self, number: int) -> str | None:
        """Line *number* (1-based); ``""`` past the end of a whole file,
        ``None`` when it was not read."""
        if 0 < number <= len(self.lines):
            return self.lines[number - 1]
        return None if self.is_cut else ""

    @property
    def has_unread(self) -> bool:
        return self.is_cut or any(ln is None for ln in self.lines)


class _Reader:
    """Reads the head of a file once, inside the repository, counting every
    byte against the row's and the scan's budget. Keeps nothing."""

    def __init__(self, split_input: RouteSplitInput) -> None:
        self._root = Path(split_input.repo_root)
        self._budget = split_input.budget
        self._row_bytes = 0
        self._files = 0

    def view(self, rel_path: str) -> _FileView:
        """The file's head. Its last line is dropped when the file goes on:
        that line is cut and could name anything."""
        self._files += 1
        if self._files > MAX_FILES_READ:
            raise _OverBudget
        path = self._root / rel_path
        if not _is_repo_relative(rel_path) or not path_within_repo(path, self._root):
            return _FileView([])
        try:
            with open(path, "rb") as handle:
                head = handle.read(FILE_HEAD_BYTES + 1)
        except OSError:
            return _FileView([])
        is_cut = len(head) > FILE_HEAD_BYTES
        head = head[:FILE_HEAD_BYTES]
        self._charge(len(head))
        lines = head.decode("utf-8", errors="replace").split("\n")
        if is_cut:
            lines.pop()
        return _FileView(
            [ln if len(ln) <= MAX_LINE_CHARS else None for ln in lines], is_cut)

    def _charge(self, size: int) -> None:
        self._row_bytes += size
        self._budget.scan_bytes += size
        if (self._row_bytes > MAX_ROW_BYTES
                or self._budget.scan_bytes > MAX_SCAN_BYTES):
            raise _OverBudget


class _RowDefinitions(NamedTuple):
    """What the row's files define, as read."""

    names: dict[str, set[str]]  # identifier -> row files defining it
    has_unread: bool            # a row file holds lines that were not read
    packages: frozenset[str | None]  # the row files' package clauses


def _definers(owned: list[str], reader: _Reader) -> _RowDefinitions:
    """``identifier -> row files that define a function of that name``,
    whether any row file holds lines that were not read (a definition may
    stand there), and the package clauses of the row's files."""
    out: dict[str, set[str]] = defaultdict(set)
    has_unread = False
    packages: set[str | None] = set()
    for path in owned:
        view = reader.view(path)
        has_unread = has_unread or view.has_unread
        packages.add(package_clause(path, view.lines))
        for line in view.lines:
            if not line:
                continue
            for definition_re in _DEFINITION_RES:
                match = definition_re.match(line)
                if match:
                    out[match.group(1)].add(path)
    return _RowDefinitions(out, has_unread, frozenset(packages))


# ── Handler resolution ──────────────────────────────────────────────────────


def _resolve_handlers(
    owned: list[str], sites: list[dict[str, Any]], split_input: RouteSplitInput,
) -> list[_Resolved]:
    """Attribute each route to the row file that handles it."""
    owned_set = set(owned)
    out: list[_Resolved] = []
    by_registration: dict[str, list[tuple[int, str, tuple[str, str], str]]] = (
        defaultdict(list))
    for site in sites:
        pattern = str(site.get("pattern") or "")
        group = _group_of_pattern(pattern)
        if group is None:
            continue
        route = (str(site.get("method") or ""), pattern)
        file_path, kind = str(site.get("file") or ""), site.get("kind")
        if kind == ROUTE_SITE_HANDLER and file_path in owned_set:
            out.append(_Resolved(file_path, *group, route))
        elif kind == ROUTE_SITE_REGISTRATION:
            by_registration[file_path].append(
                (int(site.get("line") or 0), pattern, group, route[0]))
    if not by_registration:
        return out
    reader = _Reader(split_input)
    definers, row_has_unread, row_packages = _definers(owned, reader)
    row_dir = os.path.dirname(owned[0]) if owned else ""
    for file_path in sorted(by_registration):
        view = reader.view(file_path)
        scope = file_scope(file_path, view.lines, (row_dir, row_packages))
        for number, pattern, group, method in sorted(by_registration[file_path]):
            line = _Line(number, _references_read(view.line(number), pattern))
            _stop_on_unread(line, _ReadState(definers, scope, view, row_has_unread))
            handler_file = _handler_file(line, definers, scope)
            if handler_file in owned_set:
                out.append(_Resolved(handler_file, *group, (method, pattern)))
    return out


class _Line(NamedTuple):
    """A registration line: its number and the references after its route."""

    number: int
    references: list[_Reference]


class _ReadState(NamedTuple):
    """What was read for one registration file and the row."""

    definers: dict[str, set[str]]
    scope: FileScope
    view: _FileView
    row_has_unread: bool


def _stop_on_unread(line: _Line, state: _ReadState) -> None:
    """Stop the row when a line not read could decide a reference: a row
    function's definition (the row has unread lines) or the declaration of
    a qualifier (the registering file has unread lines above the route)."""
    unread_above = any(ln is None for ln in state.view.lines[:line.number - 1])
    for ref in line.references:
        if ref.is_inline:
            continue
        kind = (state.scope.classify(ref.qualifier, line.number)
                if ref.qualifier else state.scope.bare_kind())
        if kind is None and unread_above:
            raise _TruncatedDefinition
        if kind == ROW and state.row_has_unread and not state.definers.get(ref.name):
            raise _TruncatedDefinition


def _references_read(line: str | None, pattern: str) -> list[str]:
    """The references of a registration line, which must have been read."""
    if line is None:
        raise _TruncatedDefinition
    return _line_references(line, pattern)


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


def _line_references(line: str, pattern: str) -> list[_Reference]:
    """The functions a registration line passes after its route literal.

    Each top-level argument is unwrapped through the calls around its first
    argument (``guard(h.List, "perm")`` -> ``h.List``). A literal (string,
    number) is no reference and is left out; an inline function is one, to
    the file that registers it. A row function passed deeper (a later
    argument of a wrapper) is not a handler position and is not read."""
    at = line.find(pattern) if pattern else -1
    if at < 0:
        return []
    masked = _STRING_LITERAL_RE.sub(lambda m: " " * len(m.group()), line)
    arguments = _split_arguments(masked[at:])[1:]  # [0] is the route literal
    return [ref for ref in map(_reference, arguments) if ref]


def _handler_file(
    line: _Line, definers: dict[str, set[str]], scope: FileScope,
) -> str | None:
    """The file that handles a route, or ``None``.

    The line cannot say which of its references is the handler and which is
    middleware, so it resolves only when ALL of them point at one file. A
    reference whose qualifier is another package, or that the registering
    file does not explain, or a name defined outside the row or in two row
    files, may be the handler: then the route resolves to nothing rather
    than to the file of whatever row function stands beside it. An inline
    function is a handler defined in the registering file."""
    files: set[str] = set()
    for ref in line.references:
        owners = _owners(ref, definers, scope, line.number)
        if len(owners) != 1:
            return None
        files |= owners
    return next(iter(files)) if len(files) == 1 else None


def _owners(
    ref: _Reference, definers: dict[str, set[str]], scope: FileScope, number: int,
) -> set[str]:
    """The files that may define what *ref* stands for."""
    if ref.is_inline:
        return {scope.path}
    kind = (scope.classify(ref.qualifier, number) if ref.qualifier
            else scope.bare_kind())
    if kind != ROW:
        return set()  # another package's, or not known: no row file
    return definers.get(ref.name, set())


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


class _Reference(NamedTuple):
    """A function a registration line passes: ``qualifier.name`` as written
    (``qualifier`` empty for a bare name), or an inline function."""

    qualifier: str
    name: str
    is_inline: bool = False


# An inline function written in the registration call.
_INLINE = _Reference("", "", is_inline=True)


def _reference(argument: str) -> _Reference | None:
    """The function an argument stands for: itself when it is a name or an
    inline function, the first argument (recursively) when it is a call with
    arguments, the callee when the call has none (a factory)."""
    for _ in range(MAX_CALL_DEPTH):
        argument = argument.strip()
        if _INLINE_FUNCTION_RE.match(argument):
            return _INLINE
        match = _DOTTED_NAME_RE.match(argument)
        if not match:
            return None
        rest = argument[match.end():].lstrip()
        if not rest:
            return _as_reference(match.group(1))
        if not rest.startswith("("):
            return None
        first = _split_arguments(rest[1:])[0].strip()
        if not first:
            return _as_reference(match.group(1))
        argument = first
    return None


def _as_reference(dotted: str) -> _Reference:
    qualifier, _dot, name = dotted.rpartition(".")
    return _Reference(qualifier, name)


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


def _group_files(resolved: Iterable[_Resolved]) -> dict[str, _Group]:
    """``group -> its files and the routes they handle of it`` for the groups
    that reach :data:`MIN_GROUP_ROUTES`. A route is a distinct ``(method,
    pattern)``: the same route registered twice counts once."""
    by_file: dict[str, dict[str, set[tuple[str, str]]]] = defaultdict(
        lambda: defaultdict(set))
    for r in resolved:
        by_file[r.file][r.group].add(r.route)
    files: dict[str, list[str]] = defaultdict(list)
    routes: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for path in sorted(by_file):
        handled = Counter({g: len(rs) for g, rs in by_file[path].items()})
        group = _group_of_file(path, handled)
        if group is not None:
            files[group].append(path)
            routes[group] |= by_file[path][group]
    return {
        g: _Group(files[g], frozenset(routes[g])) for g in files
        if len(routes[g]) >= MIN_GROUP_ROUTES
    }


# ── The lines floor ─────────────────────────────────────────────────────────


def _at_line_floor(
    groups: dict[str, _Group], other_rows: list[list[str]],
    split_input: RouteSplitInput,
) -> dict[str, _Group]:
    """The groups whose files hold at least the median lines of the other
    developer rows: a group smaller than a typical row of this repository is
    not a row. The median is the repository's own, unclamped, so the floor
    has no cliff between a repository of one-file rows and one of two-file
    rows. No other row, no ruler: the floor is zero."""
    counter = _LineCounter(split_input)
    totals = [sum(map(counter.lines, row)) for row in other_rows]
    floor = statistics.median(totals) if totals else 0
    sized = {
        key: replace(group, lines=sum(map(counter.lines, group.files)))
        for key, group in groups.items()
    }
    return {key: group for key, group in sized.items() if group.lines >= floor}


class _LineCounter:
    """A file's lines by the engine's own count (executable lines; tests,
    generated files, lockfiles and binaries count 0), once per scan. Lines
    are not on the rows yet at this stage (Stage 6.97 stamps them), so they
    are counted here; every byte opened is charged to the scan budget by
    the file's size before it is opened."""

    def __init__(self, split_input: RouteSplitInput) -> None:
        self._root = Path(split_input.repo_root)
        self._budget = split_input.budget

    def lines(self, rel_path: str) -> int:
        known = self._budget.file_lines.get(rel_path)
        if known is None:
            known = self._count(rel_path)
            self._budget.file_lines[rel_path] = known
        return known

    def _count(self, rel_path: str) -> int:
        path = self._root / rel_path
        if not _is_repo_relative(rel_path) or not path_within_repo(path, self._root):
            return 0
        if _counted_without_reading(rel_path):
            return 0
        try:
            size = path.stat().st_size
        except OSError:
            return 0
        self._budget.scan_bytes += size
        if self._budget.scan_bytes > MAX_SCAN_BYTES:
            raise _OverBudget
        return count_file_loc(self._root, rel_path)


def _counted_without_reading(rel_path: str) -> bool:
    """The files ``count_file_loc`` answers 0 for by their path alone: they
    are never opened, so they cost the budget nothing."""
    return (is_test_path(rel_path) or is_generated_path(rel_path)
            or _is_excluded_name(rel_path))


def _slug(segment: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", segment.lower()).strip("-")


def _lawful_name(base: str, parent: str, taken: set[str]) -> str | None:
    """The row name for a group whose URL segment slugs to *base*, or
    ``None`` when it has none: a number, a date or a version is not a name,
    nor is a segment the engine already treats as naming no object
    (``new``, ``index``) or as an access tier (``public``); the parent's own
    name stays with the parent (never ``orders-orders``); a name another row
    has is qualified by the parent, once, never numbered, and not when the
    parent already says it (``orders-api-orders``)."""
    if (not base or base == parent or _UNNAMEABLE_SEGMENT_RE.match(base)
            or base in GENERIC_ROUTE_SEGMENTS or base in ACCESS_TIER_SEGMENTS):
        return None
    if base not in taken:
        name = base
    elif _repeats(parent, base):
        return None
    else:
        name = f"{parent}-{base}"
    if name in taken or len(name) > MAX_NAME_CHARS:
        return None
    return name


def _repeats(parent: str, base: str) -> bool:
    """Every word of *base* is already a word of *parent* (singular or
    plural alike), so ``parent-base`` would say one word twice."""
    def words(slug: str) -> set[str]:
        return {normalize_anchor_key(word) for word in slug.split("-") if word}

    return words(base) <= words(parent)


def _name_groups(
    ranked: list[tuple[str, _Group]],
    resolved: list[_Resolved],
    parent_name: str,
    used_names: set[str],
) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Row name per group: the URL segment as its routes write it. A group
    that cannot get a lawful name is not promoted (its files stay). Also
    returns each name's group key."""
    group_of_file = {f: key for key, group in ranked for f in group.files}
    written: dict[str, Counter] = defaultdict(Counter)
    for r in resolved:
        if group_of_file.get(r.file) == r.group:
            written[r.group][_slug(r.segment)] += 1
    taken = set(used_names)
    named: dict[str, list[str]] = {}
    group_of_name: dict[str, str] = {}
    for group, members in ranked:
        files = members.files
        base = min(written[group].items(), key=lambda kv: (-kv[1], kv[0]))[0]
        name = _lawful_name(base, _slug(parent_name), taken)
        if name is None:
            continue
        taken.add(name)
        named[name] = files
        group_of_name[name] = group
    return named, group_of_name


# ── Flows follow their entry files ──────────────────────────────────────────


@dataclass(frozen=True)
class FlowMove:
    """Where one flow went. ``id`` is derived from the row that holds the
    flow, so it changes with the row and every reference to ``old_id`` must
    follow.

    A move is keyed by ``(old_id, entry_file)`` (:func:`move_key`). Stage
    8.9 runs before any flow has a ``uuid`` (Stage 6.8 stamps it later, from
    the name, and the move does not touch it), so the old id and the entry
    file are what tell one flow from another here: the entry file is what
    the move is decided on, so two flows sharing both always go to the same
    place, and a flow that only shares the old id is never taken for the
    one that moved."""

    row: str
    old_id: str
    new_id: str
    entry_file: str = ""


#: ``(old id, entry file)``: the key of a move and of a flow it applies to.
MoveKey = tuple[str, str]


def move_key(flow: Any) -> MoveKey:
    """The key a move of *flow* is stored under."""
    return (str(getattr(flow, "id", "") or ""),
            str(getattr(flow, "entry_point_file", "") or ""))


class MoveCycle(ValueError):
    """Flow moves that lead back to an id they started from."""


def close_flow_moves(
    flow_moves: dict[MoveKey, FlowMove],
) -> dict[MoveKey, FlowMove]:
    """Every move followed to where the flow ends.

    A row born in this stage can split again, so one flow can move twice
    (``srv::f -> orders::f -> refunds::f``). An edge or a copy recorded
    before the stage names the first id, and a rewrite that follows one hop
    would leave it on ``orders::f``, which no flow holds. Closed, every key
    maps to the last row and id: a reference is rewritten once, from the id
    it names to the final one. A move onto its own id ends there. Raises
    :class:`MoveCycle` when the moves lead back to an id already passed."""
    return {key: _final_move(key, flow_moves) for key in flow_moves}


def _final_move(key: MoveKey, flow_moves: dict[MoveKey, FlowMove]) -> FlowMove:
    move = flow_moves[key]
    passed = {key}
    while move.new_id != move.old_id:
        following = (move.new_id, move.entry_file)
        if following not in flow_moves:
            break
        if following in passed:
            raise MoveCycle(key)
        passed.add(following)
        move = flow_moves[following]
    return FlowMove(move.row, key[0], move.new_id, key[1])


def has_flow_identity(flow: Any) -> bool:
    """A flow can be moved only when it has an id: the move and its edges
    are found by it, and an empty id would match every other flow that
    lacks one."""
    return bool(getattr(flow, "id", ""))


def apply_flow_moves(
    flows: Iterable[Any], edges: Iterable[Any],
    flow_moves: dict[MoveKey, FlowMove],
) -> None:
    """Make a flow store agree with the rows after Stage 8.9 moved flows.

    A copy of a moved flow (same old id AND same entry file) takes the row
    and the id the move derived; a flow that only shares the old id keeps
    both. An edge carries only the id, so it follows a move only when the id
    stands for that one move: no flow given here still holds the id unmoved,
    and every move of that id ends at the same row and id. A primary edge
    then names the new row. One hop is followed, so *flow_moves* must be
    closed (:func:`close_flow_moves`; Stage 8.9 hands it over closed). An
    empty id matches nothing. Applying twice is the same as once."""
    if not flow_moves:
        return
    flows = list(flows or ())
    edge_moves = _edge_moves(flow_moves, _held_unmoved(flows, flow_moves))
    for flow in flows:
        key = move_key(flow)
        move = flow_moves.get(key) if key[0] else None
        if move is not None:
            flow.primary_feature = move.row
            flow.id = move.new_id
    for edge in edges or ():
        move = edge_moves.get(str(getattr(edge, "flow_id", "") or ""))
        if move is None:
            continue
        edge.flow_id = move.new_id
        if getattr(edge, "type", None) == "primary":
            edge.feature = move.row


def _held_unmoved(
    flows: list[Any], flow_moves: dict[MoveKey, FlowMove],
) -> set[str]:
    """Ids held by a flow no move applies to: an edge naming one is that
    flow's edge as much as any moved flow's. A flow that already carries
    where its move took it (the live pipeline shares the row's object) is
    not such a flow."""
    arrived = {(m.new_id, m.entry_file) for m in flow_moves.values()}
    return {key[0] for key in map(move_key, flows)
            if key[0] and key not in flow_moves and key not in arrived}


def _edge_moves(
    flow_moves: dict[MoveKey, FlowMove], held: set[str],
) -> dict[str, FlowMove]:
    """``old id -> move`` for the old ids an edge can follow."""
    ends: dict[str, set[tuple[str, str]]] = defaultdict(set)
    first: dict[str, FlowMove] = {}
    for (old_id, _entry), move in flow_moves.items():
        if old_id:
            ends[old_id].add((move.row, move.new_id))
            first.setdefault(old_id, move)
    return {old_id: first[old_id] for old_id, end in ends.items()
            if len(end) == 1 and old_id not in held}


def flows_with_product_copies(
    flows: Iterable[Any], product_features: Iterable[Any] | None,
) -> list[Any]:
    """The flow store plus the flows product features list. The live
    pipeline shares one object per flow, but a recorded stage input holds a
    copy in each list, and every copy must carry the moved flow's id."""
    out = list(flows or ())
    for product in product_features or ():
        out.extend(getattr(product, "flows", None) or ())
    return out


__all__ = [
    "FlowMove",
    "MIN_GROUPS",
    "MoveCycle",
    "MoveKey",
    "MIN_GROUP_ROUTES",
    "ROUTE_GROUP_DOMAIN_PREFIX",
    "ROUTE_SITE_HANDLER",
    "ROUTE_SITE_REGISTRATION",
    "ReadBudget",
    "RoutePlan",
    "RouteSplitInput",
    "SKIP_DANGLING_REFERENCE",
    "SKIP_MOVE_CYCLE",
    "SKIP_OVER_BUDGET",
    "SKIP_TRUNCATED_DEFINITION",
    "SKIP_UNDO_INCOMPLETE",
    "BORN_ROWS_KEY",
    "STAGE_8_9_META_KEY",
    "apply_flow_moves",
    "born_route_groups",
    "close_flow_moves",
    "collect_route_sites",
    "declared_route_site_kinds",
    "flows_with_product_copies",
    "has_flow_identity",
    "is_flat",
    "move_key",
    "plan_route_group_split",
]
