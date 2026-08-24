"""nav_parent — B78 Seg G: display-layer nav-parent grouping (deterministic).

THE PROBLEM (B78 forensics-canon, 2026-07-21): the post-rescue "next
layer" hygiene — homes/names are fixed, but the board is a FLAT list of
product features while the repo itself DECLARES a nav hierarchy. RefApp
``module-registry.ts`` + ``app-nav-config.ts`` group 24/52 PFs under 6
nav categories (one per product area) with 3
live categories carrying no PF at all; twenty's
``useSettingsNavigationItems`` files ``Billing`` / ``Members`` /
``Data model`` under ``Workspace``, and its ``objects`` + ``data-model``
PFs are two views of ONE nav position.

THE FIX (display-layer ONLY): a deterministic nav-tree extractor reads
the STATIC exported nav registries (the same legal JSX/TS author-intent
class ``product_strings`` already trusts — NOT a dictionary of file
names, NEVER an i18n VALUE) and attaches a nullable ``nav_parent`` =
``{parent_label, parent_id, source_file, line, via}`` to a PF whose
anchor route matches a nav SUB-item (``via="route"``) — or, for a
route-LESS sub-item only (enum/const-referenced destinations), whose
tokens exactly equal the sub's label (``via="label"``) / enum path
member (``via="path"``). A route-bearing sub-item is judged by the
route channel alone — a bare token guess against it never attaches
(B78-it2 Goal 3, the RefApp ``api`` → 'Mssp' slug-guess class).
Product features are NEVER merged or moved — the
engineering grain is untouched; only the display field + the
``scan_meta.nav_tree`` telemetry (categories, sub-items, matched /
unmatched / unrepresented / duplicates) are added. Live nav categories
with no PF are reported in ``nav_tree.unrepresented`` and NEVER minted.

MECHANISM (grammar in ``stacks/nav-tree.yaml``, not per-repo constants):
a nav CATEGORY is an exported array/object of nav ITEMS
(``{path|route|href} + {label|title|name|labelKey|…} (+icon)``), with
optional ``children|items|sub|pages`` nesting; the category label comes
from a literal field, else a humanized i18n KEY / ``id`` / const name;
a flat exported array (``SETTINGS_SIDEBAR_ITEMS``) is a category named
by its const, and a ``[{label, items:[…]}]`` return array is one
category per element. Consumption prior (like the ``spa_router``
precedent): only nav-registry files are read, and an item must carry a
label/icon — a random config array of ``{path, size}`` is never a nav
tree.

Flag ``WYSTAN_NAV_PARENT`` — default **ON** since the 2026-07-22
flip-pack №4 (KEY_SCHEMA 36). Explicit ``0`` → the pass is never entered:
``nav_parent`` stays ``None`` (omitted from dumps — see
``Feature._omit_unset_spine_fields``) and no ``scan_meta.nav_tree`` key
is written, so the scan is byte-identical to the pre-Seg-G engine. A
nav-less repo (no readable registry) is likewise byte-identical
(inertness — ``nav_parent`` stays a nullable display-only field).
Registered in ``scan_result_cache.ENV_OUTPUT_FLAGS``.

Deterministic, $0 LLM, no network, read-only over tracked files.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from wystan.pipeline_v2.data import load_stack_yaml
from wystan.pipeline_v2.nav_taxonomy import _singular, _tokens
from wystan.pipeline_v2.product_strings import normalize_href, route_path_for_file

if TYPE_CHECKING:  # pragma: no cover
    from wystan.pipeline_v2.stage_0_intake import ScanContext

__all__ = [
    "NAV_CATEGORY_DEMOTE_ENV",
    "NAV_PARENT_ENV",
    "VUE_NAV_KEYS_ENV",
    "NavCategory",
    "NavSubItem",
    "build_nav_tree",
    "is_section_landing_pf",
    "nav_category_demote_enabled",
    "nav_keys_by_workspace",
    "nav_keys_from_nav_tree",
    "nav_parent_enabled",
    "run_nav_category_demote",
    "run_nav_parent",
    "split_nav_key_channels",
    "vue_nav_keys_enabled",
]

NAV_PARENT_ENV = "WYSTAN_NAV_PARENT"
NAV_CATEGORY_DEMOTE_ENV = "WYSTAN_NAV_CATEGORY_DEMOTE"
VUE_NAV_KEYS_ENV = "WYSTAN_VUE_NAV_KEYS"

#: Bounded per-file read — nav registries are small; the cap only guards
#: pathological blobs (mirrors ``spa_router._MAX_BYTES``).
_MAX_BYTES = 1_500_000
#: Code file extensions a nav registry may live in.
_CODE_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte")


def nav_parent_enabled() -> bool:
    """Default **ON** since the 2026-07-22 flip-pack №4 (KEY_SCHEMA 36;
    RefApp 23-32/PF parents verified vs the module-registry). Unset ≡ explicit
    ``1``: the display-grouping pass arms. Explicit ``0`` / anything else in
    the falsy set keeps it inert (no field, no ``scan_meta`` key →
    byte-identical to the pre-Seg-G engine; kill-switch forever)."""
    return os.environ.get(NAV_PARENT_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def vue_nav_keys_enabled() -> bool:
    """WYSTAN_VUE_NAV_KEYS — default **ON** since the 2026-07-31
    flip-pack №13 (KEY_SCHEMA 48; keyed proof hoppscotch — vue-nav
    un-abstain + nav-lane demote green). Unset ≡ explicit ``"1"``: the Vue
    nav-key derivation arms — the parser lift (``vue=True`` mode) reads
    Vue/SFC nav forms — HoppSmartLink ``target``, ``to: t('inbox_view')``
    call-expr destinations, ``:to="{name:…}"`` template bindings,
    ``label: t('metrics.dashboard')`` i18n-macro labels, dotted i18n-KEY
    label values, and ``defineModule({id,name,routes})`` module
    registries — and ``nav_keys_from_nav_tree`` unions them into the
    board's nav_keys. Explicit ``"0"`` (or anything outside the truthy
    set) ⇒ the vue=True parse path is never entered and the nav_keys
    wiring is a no-op ⇒ byte-identical to the pre-flag engine
    (kill-switch forever; the strong ``nav_parent``/``nav_seam_keys``
    path always parses in the unchanged ``vue=False`` mode). The truthy
    set stays the WIDE ``{"1","true","yes","on"}`` (preserved LITERALLY
    across the flip; only the get-default moved ``"0"`` → ``"1"``)."""
    return os.environ.get(VUE_NAV_KEYS_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def nav_category_demote_enabled() -> bool:
    """B93 nav-category demote — default **ON** since flip-pack №9 (KEY_SCHEMA
    42; 2026-07-28; exhibit-gate PASS — RefApp 'Feature Studio' keyless OFF 1 hit
    → ON 0 hits). Unset ≡ explicit ``1``: the section-landing demote arms.
    Explicit ``0`` / ``false`` / ``off`` / ``no`` (anything outside the truthy
    set) keeps the pass inert — it returns ``None`` before any mutation and
    writes no ``scan_meta`` key ⇒ byte-identical to the pre-B93 engine
    (kill-switch forever; inverted-kill-switch unit: unset ≡ explicit ``1``)."""
    return os.environ.get(NAV_CATEGORY_DEMOTE_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


# ── grammar config ───────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _cfg() -> dict:
    return load_stack_yaml("nav-tree")


@lru_cache(maxsize=1)
def _label_keys() -> frozenset[str]:
    return frozenset(str(s) for s in (_cfg().get("label_keys") or ()))


@lru_cache(maxsize=1)
def _i18n_label_keys() -> frozenset[str]:
    return frozenset(str(s) for s in (_cfg().get("i18n_label_keys") or ()))


@lru_cache(maxsize=1)
def _href_keys() -> frozenset[str]:
    return frozenset(str(s) for s in (_cfg().get("href_keys") or ()))


@lru_cache(maxsize=1)
def _id_keys() -> tuple[str, ...]:
    return tuple(str(s) for s in (_cfg().get("id_keys") or ()))


@lru_cache(maxsize=1)
def _nest_keys() -> frozenset[str]:
    return frozenset(str(s) for s in (_cfg().get("nest_keys") or ()))


@lru_cache(maxsize=1)
def _section_landing_segments() -> frozenset[str]:
    """Structural section-index directory/file segments (``overview``/
    ``index``/``landing``/``home``) — a nav-child whose EVERY anchor member
    file lives under one of these is a section-landing shell, not a feature.
    Data (``nav-tree.yaml``), never hardcoded — the devgrain-vocab precedent."""
    return frozenset(
        str(s).strip().lower()
        for s in (_cfg().get("section_landing_segments") or ())
        if str(s).strip()
    )


@lru_cache(maxsize=1)
def _icon_keys() -> frozenset[str]:
    return frozenset(str(s) for s in (_cfg().get("icon_keys") or ()))


@lru_cache(maxsize=1)
def _const_suffixes() -> tuple[str, ...]:
    # Longest-first so ``_SIDEBAR_ITEMS`` strips before ``_ITEMS``.
    return tuple(sorted(
        (str(s) for s in (_cfg().get("const_name_suffixes") or ())),
        key=len, reverse=True,
    ))


@lru_cache(maxsize=1)
def _i18n_trailing_generic() -> frozenset[str]:
    return frozenset(str(s).lower() for s in (_cfg().get("i18n_trailing_generic") or ()))


@lru_cache(maxsize=1)
def _nav_basename_markers() -> tuple[str, ...]:
    return tuple(str(s).lower() for s in (_cfg().get("nav_basename_markers") or ()))


@lru_cache(maxsize=1)
def _nav_content_markers() -> tuple[str, ...]:
    return tuple(str(s) for s in (_cfg().get("nav_content_markers") or ()))


# ── vue-mode extra grammar (read ONLY under WYSTAN_VUE_NAV_KEYS) ───────────


@lru_cache(maxsize=1)
def _vue_href_keys() -> frozenset[str]:
    """href_keys ∪ the vue-only destination fields (``target``)."""
    return _href_keys() | frozenset(
        str(s) for s in (_cfg().get("vue_href_keys") or ()))


@lru_cache(maxsize=1)
def _vue_nav_content_markers() -> tuple[str, ...]:
    """nav_content_markers ∪ the vue-only render markers (``defineModule`` …)."""
    return _nav_content_markers() + tuple(
        str(s) for s in (_cfg().get("vue_nav_content_markers") or ()))


@lru_cache(maxsize=1)
def _module_registry_calls() -> tuple[str, ...]:
    return tuple(str(s) for s in (_cfg().get("module_registry_calls") or ()))


def _href_keys_for(vue: bool) -> frozenset[str]:
    return _vue_href_keys() if vue else _href_keys()


# A label VALUE that is really an i18n KEY (a code identifier), never human
# copy: a bare dotted identifier (``navigation.rest`` / ``SIDEBAR.INBOX``) with
# NO whitespace. This is the SAME discriminator ``product_strings._is_human_string``
# uses (a dotted token with no space is a path-like/dotted identifier, not copy)
# — so ``"v1.2 Release"`` (a space) is NOT an i18n key and stays a literal label.
_I18N_DOTTED_RE = re.compile(r"^[\w$]+(?:\.[\w$]+)+$")
#: ``$t:content`` (Directus/vue-i18n inline-key convention) — the label VALUE
#: is a literal i18n KEY behind a ``$t:`` sentinel; only the KEY is read.
_I18N_DOLLAR_T_RE = re.compile(r"^\$t:(.+)$")


def _i18n_key_of_label_value(val: str) -> str | None:
    """When a label VALUE is actually an i18n KEY (never human copy), return
    that dotted KEY (for :func:`_humanize_i18n_key`); else ``None``. The i18n
    VALUE is NEVER read (README law) — only the KEY, a code identifier."""
    v = val.strip()
    if not v:
        return None
    m = _I18N_DOLLAR_T_RE.match(v)
    if m:
        return m.group(1).strip()
    if " " not in v and _I18N_DOTTED_RE.match(v):
        return v
    return None


def _route_name_shaped(arg: str) -> bool:
    """A named-route / route-name token: a bare identifier (``inbox_view`` /
    ``users-active`` / ``agent_reports_index``) — a letter-led ``\\w . - ``
    string with NO whitespace and NO slash. NOT a URL path (``/x``), NOT human
    copy (has a space)."""
    a = arg.strip()
    return bool(a) and " " not in a and "/" not in a and bool(
        re.match(r"^[A-Za-z][\w.-]*$", a))


def _route_name_leaf_key(route_name: str) -> str:
    """First meaningful token of a route-name (``inbox_view`` → ``inbox``;
    ``agent_reports_index`` → ``agent``) — the destination noun, dropping the
    trailing action step (``_view`` / ``_index`` / ``_show``)."""
    spaced = _CAMEL_RE.sub(" ", route_name)
    for w in _SPLIT_RE.split(spaced):
        if w:
            return w.lower()
    return ""


# ── humanization / tokenization ──────────────────────────────────────────────

_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_SPLIT_RE = re.compile(r"[^A-Za-z0-9]+")


def _humanize(raw: str) -> str:
    """Title-case display label from a code identifier (``detectionsStudio``
    / ``media-library`` / ``MEDIA_LIBRARY`` → ``Media Studio`` /
    ``Media Library``). Pure structure — never an i18n value."""
    spaced = _CAMEL_RE.sub(" ", raw)
    words = [w for w in _SPLIT_RE.split(spaced) if w]
    out: list[str] = []
    for w in words:
        # An ALL-CAPS const-stem word (GLOBAL / SETTINGS) title-cases; a
        # mixed word keeps its interior casing (apiKeys already split).
        w = w.lower() if w.isupper() and len(w) > 1 else w
        out.append(w[:1].upper() + w[1:] if w else w)
    return " ".join(out)


def _humanize_i18n_key(dotted: str) -> str:
    """Humanize the meaningful leaf of a dotted i18n KEY, stripping a
    trailing generic segment (``modules.detectionsStudio.name`` →
    ``Media Studio``). The KEY is a code identifier (legal); the
    VALUE is never read."""
    segs = [s for s in dotted.split(".") if s]
    while len(segs) > 1 and segs[-1].lower() in _i18n_trailing_generic():
        segs.pop()
    return _humanize(segs[-1]) if segs else ""


def _label_slug_tokens(label: str) -> frozenset[str]:
    return _tokens(label)


def _member_token_of_ref(ref: str) -> str:
    """Last dotted member of an enum/const reference (``SettingsPath.Objects``
    → ``Objects``); the whole ident when there is no dot."""
    return ref.rsplit(".", 1)[-1]


# ── nav-file detection (consumption prior) ───────────────────────────────────


def _looks_like_nav_file(path: str, text: str, vue: bool = False) -> bool:
    base = path.rsplit("/", 1)[-1].lower()
    stem = base.rsplit(".", 1)[0]
    if any(mk in stem for mk in _nav_basename_markers()):
        return True
    markers = _vue_nav_content_markers() if vue else _nav_content_markers()
    return any(mk in text for mk in markers)


# ── object-literal parser (bounded, comment/string-aware) ────────────────────


@dataclass
class _Obj:
    """A parsed object literal: scalar fields + nested object-arrays."""

    line: int
    fields: dict[str, tuple[str, str]] = field(default_factory=dict)  # key -> (kind, value)
    arrays: dict[str, list["_Obj"]] = field(default_factory=dict)      # key -> [obj, ...]
    array_refs: dict[str, list[str]] = field(default_factory=dict)     # key -> [ident, ...]
    child_obj: dict[str, "_Obj"] = field(default_factory=dict)         # key -> single object value


def _skip_ws_comments(s: str, i: int) -> int:
    n = len(s)
    while i < n:
        c = s[i]
        if c in " \t\r\n":
            i += 1
            continue
        if s.startswith("//", i):
            j = s.find("\n", i)
            i = n if j < 0 else j + 1
            continue
        if s.startswith("/*", i):
            j = s.find("*/", i)
            i = n if j < 0 else j + 2
            continue
        break
    return i


def _read_string(s: str, i: int) -> tuple[str, int]:
    """``s[i]`` is a quote; return (content, index past the closing quote).
    No escape unescaping — nav literals never embed escaped quotes."""
    q = s[i]
    j = s.find(q, i + 1)
    if j < 0:
        return s[i + 1:], len(s)
    return s[i + 1:j], j + 1


def _read_ident(s: str, i: int) -> tuple[str, int]:
    n = len(s)
    j = i
    while j < n and (s[j].isalnum() or s[j] in "_$"):
        j += 1
    return s[i:j], j


def _scan_balanced(s: str, i: int) -> int:
    """From the start of a scalar expression, return the index of the
    depth-0 terminator (``,`` / ``}`` / ``]``) — respecting nested
    ()[]{} and strings. Handles arrow bodies, ternaries, calls."""
    n = len(s)
    depth = 0
    while i < n:
        c = s[i]
        if c in "\"'`":
            _, i = _read_string(s, i)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return i
            depth -= 1
        elif c == "," and depth == 0:
            return i
        i += 1
    return n


def _first_string_arg(s: str, i: int) -> str:
    """``s[i] == '('``. Return the first string-literal argument inside the
    balanced call (``t('metrics.dashboard')`` → ``metrics.dashboard``;
    ``accountScopedRoute('inbox_view', {...})`` → ``inbox_view``), else ``""``.
    Depth-aware over nested ()[]{} — only a top-level (arg-position) string
    counts, not a string nested inside a further call/object."""
    n = len(s)
    depth = 0
    while i < n:
        c = s[i]
        if c in "\"'":
            content, _ = _read_string(s, i)
            if depth == 1:            # a direct argument of THIS call
                return content
            i = _read_string(s, i)[1]
            continue
        if c == "`":
            content, j = _read_string(s, i)
            if depth == 1 and "${" not in content:
                return content
            i = j
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return ""
        i += 1
    return ""


def _read_value(
    s: str, i: int, line_of: Any, vue: bool = False,
) -> tuple[str, Any, int]:
    """Parse the value at ``s[i]`` → ``(kind, node, next_i)``.

    kind: ``obj`` (node=_Obj) | ``array`` (node=list[(kind,node)]) |
    ``str`` (node=text) | ``template`` (node=static text or "") |
    ``ref`` (node=dotted ident) | ``call`` (node=first-string-arg, vue mode
    only) | ``other`` (node="")."""
    i = _skip_ws_comments(s, i)
    if i >= len(s):
        return "other", "", i
    c = s[i]
    if c == "{":
        obj, i = _parse_object(s, i, line_of, vue)
        return "obj", obj, i
    if c == "[":
        elems, i = _parse_array(s, i, line_of, vue)
        return "array", elems, i
    if c in "\"'":
        content, i = _read_string(s, i)
        return "str", content, i
    if c == "`":
        content, i = _read_string(s, i)
        return ("template", "" if "${" in content else content, i)
    if c.isalpha() or c in "_$":
        ident, j = _read_ident(s, i)
        k = _skip_ws_comments(s, j)
        # tagged template: ``t`User` `` / ``msg`Documents` ``
        if k < len(s) and s[k] == "`":
            content, k = _read_string(s, k)
            return ("template", "" if "${" in content else content, k)
        # dotted member chain: ``SettingsPath.Objects``
        dotted = ident
        while j < len(s) and s[j] == ".":
            nxt, j = _read_ident(s, j + 1)
            if not nxt:
                break
            dotted += "." + nxt
        # a call / spread / index after the ident → treat as opaque expr
        end = _scan_balanced(s, j)
        tail = s[j:end].strip()
        if tail == "":
            return "ref", dotted, j
        # vue mode: a call ``fn('arg')`` / ``t('key')`` keeps its FIRST string
        # literal (route-name destination or i18n-key label) instead of being
        # dropped as opaque — the sole extra shape the lift captures.
        if vue and tail.startswith("("):
            arg = _first_string_arg(s, s.index("(", j))
            if arg:
                return "call", arg, end
        return "other", "", end
    # number / spread / anything else — scan to the terminator
    end = _scan_balanced(s, i)
    return "other", "", end


def _read_key(s: str, i: int) -> tuple[str, int]:
    """Parse an object key at ``s[i]`` (identifier, quoted, or ``[expr]``
    computed). Returns ("", i) when no key is present."""
    i = _skip_ws_comments(s, i)
    if i >= len(s):
        return "", i
    c = s[i]
    if c in "\"'":
        key, i = _read_string(s, i)
        return key, i
    if c == "[":
        # computed key — skip the bracket balanced, no usable key
        depth = 0
        n = len(s)
        while i < n:
            ch = s[i]
            if ch in "\"'`":
                _, i = _read_string(s, i)
                continue
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    i += 1
                    break
            i += 1
        return "", i
    if c.isalpha() or c in "_$":
        key, i = _read_ident(s, i)
        return key, i
    return "", i


def _parse_object(
    s: str, i: int, line_of: Any, vue: bool = False,
) -> tuple[_Obj, int]:
    """``s[i] == '{'``. Parse one object literal (top-level members only)."""
    obj = _Obj(line=line_of(i))
    i += 1
    n = len(s)
    _scalar_kinds = ("str", "template", "ref", "call") if vue else (
        "str", "template", "ref")
    while i < n:
        i = _skip_ws_comments(s, i)
        if i >= n or s[i] == "}":
            i += 1 if i < n else 0
            break
        if s[i] == ",":
            i += 1
            continue
        key, i = _read_key(s, i)
        i = _skip_ws_comments(s, i)
        if i < n and s[i] == ":":
            kind, node, i = _read_value(s, i + 1, line_of, vue)
            if key:
                if kind == "array":
                    child_objs = [nd for (k, nd) in node if k == "obj"]
                    child_ids = [nd for (k, nd) in node if k == "ref"]
                    if child_objs:
                        obj.arrays[key] = child_objs
                    if child_ids:
                        obj.array_refs[key] = child_ids
                elif kind == "obj":
                    obj.child_obj[key] = node
                elif kind in _scalar_kinds:
                    obj.fields[key] = (kind, node)
        elif i < n and s[i] in ",}":
            # shorthand field — no value; ignore
            continue
        else:
            # method / getter / malformed — skip its value region. Guarantee
            # forward progress: a stray depth-0 close bracket makes
            # ``_scan_balanced`` return ``i`` unchanged; step over it rather
            # than spin (a no-op on well-formed input — it always advances).
            ni = _scan_balanced(s, i)
            i = ni + 1 if ni <= i else ni
        i = _skip_ws_comments(s, i)
        if i < n and s[i] == ",":
            i += 1
    return obj, i


def _parse_array(
    s: str, i: int, line_of: Any, vue: bool = False,
) -> tuple[list[tuple[str, Any]], int]:
    """``s[i] == '['``. Parse an array's element (kind, node) list."""
    out: list[tuple[str, Any]] = []
    i += 1
    n = len(s)
    while i < n:
        i = _skip_ws_comments(s, i)
        if i >= n or s[i] == "]":
            i += 1 if i < n else 0
            break
        if s[i] == ",":
            i += 1
            continue
        # spread ``...NAME`` — resolve as a ref to the spread source array
        if s.startswith("...", i):
            ident, j = _read_ident(s, _skip_ws_comments(s, i + 3))
            if ident:
                out.append(("spread", ident))
                i = j
                continue
        _start = i
        kind, node, i = _read_value(s, i, line_of, vue)
        out.append((kind, node))
        if i <= _start:
            # ``_read_value`` could not advance (a stray depth-0 close bracket
            # left by a preceding complex value/method region) — step over it
            # so the element scan always terminates (no-op on well-formed input).
            i = _start + 1
        i = _skip_ws_comments(s, i)
        if i < n and s[i] == ",":
            i += 1
    return out, i


# ── nav tree assembly ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NavSubItem:
    """One navigable leaf under a category."""

    route: str | None            # normalized literal href, else None
    label: str                   # display label (may be "")
    label_tokens: frozenset[str]
    path_tokens: frozenset[str]  # tokens of an enum-referenced path member
    source_file: str
    line: int
    #: vue-mode only: a named-route destination (``inbox_view`` /
    #: ``users-active``) from a ``to: fn('inbox_view')`` call-expr or a
    #: ``:to="{name:'…'}"`` template binding. Default ``None`` ⇒ the field is
    #: absent from every ``vue=False`` NavSubItem (byte-identical nav_parent).
    route_name: str | None = None


@dataclass(frozen=True)
class NavCategory:
    """One vendor-declared nav area (the display parent)."""

    id: str
    label: str
    source_file: str
    line: int
    sub_items: tuple[NavSubItem, ...]


_DECL_RE = re.compile(
    r"(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*"
    r"(?::[^=;]+?)?=\s*(?=[\[{])",
)
_RETURN_RE = re.compile(r"\breturn\s*(?=[\[{])")


def _line_of_factory(text: str) -> Any:
    starts = [0]
    for m in re.finditer(r"\n", text):
        starts.append(m.end())

    def line_of(idx: int) -> int:
        lo, hi = 0, len(starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if starts[mid] <= idx:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    return line_of


def _field_str(obj: _Obj, keys: frozenset[str]) -> str | None:
    for key, (kind, val) in obj.fields.items():
        if key in keys and kind in ("str", "template") and val.strip():
            return val.strip()
    return None


def _field_ref_or_str(obj: _Obj, keys: frozenset[str]) -> tuple[str, str] | None:
    """First (kind, value) among ``keys`` that is a str/template/ref."""
    for key, (kind, val) in obj.fields.items():
        if key in keys and val.strip():
            return kind, val.strip()
    return None


def _obj_id(obj: _Obj) -> str | None:
    for key in _id_keys():
        got = obj.fields.get(key)
        if got and got[0] in ("str", "template") and got[1].strip():
            return got[1].strip()
    return None


def _category_label(
    obj: _Obj | None, const_name: str | None, vue: bool = False,
) -> str:
    """Category display label: literal label → i18n-key humanized → id
    humanized → const-name humanized (nav suffixes stripped)."""
    if obj is not None:
        if vue:
            vl = _vue_item_label(obj)
            if vl:
                return vl
        lit = _field_str(obj, _label_keys())
        if lit:
            return lit
        i18n = _field_str(obj, _i18n_label_keys())
        if i18n:
            hz = _humanize_i18n_key(i18n)
            if hz:
                return hz
        oid = _obj_id(obj)
        if oid:
            return _humanize(oid)
    if const_name:
        stem = const_name
        for suf in _const_suffixes():
            if stem.upper().endswith(suf):
                stem = stem[: len(stem) - len(suf)]
                break
        return _humanize(stem)
    return ""


def _category_id(obj: _Obj | None, const_name: str | None, label: str) -> str:
    if obj is not None:
        oid = _obj_id(obj)
        if oid:
            return oid
    if const_name:
        return _slug(const_name)
    return _slug(label)


def _slug(raw: str) -> str:
    spaced = _CAMEL_RE.sub(" ", raw)
    return "-".join(w.lower() for w in _SPLIT_RE.split(spaced) if w)


def _item_href(obj: _Obj) -> tuple[str | None, frozenset[str]]:
    """(normalized literal route | None, path-member tokens). A literal
    ``/x`` normalizes to a route; an enum ref (``SettingsPath.Objects``)
    yields no route but its member token feeds the slug channel."""
    for key, (kind, val) in obj.fields.items():
        if key not in _href_keys():
            continue
        if kind in ("str", "template") and val:
            route = normalize_href(val)
            if route:
                return route, frozenset()
        if kind == "ref" and val:
            member = _member_token_of_ref(val)
            toks = frozenset(
                t for t in (_singular(w.lower()) for w in _SPLIT_RE.split(
                    _CAMEL_RE.sub(" ", member)))
                if len(t) >= 2 and not t.isdigit()
            )
            return None, toks
    return None, frozenset()


def _item_dest(obj: _Obj) -> tuple[str | None, frozenset[str], str | None]:
    """VUE-MODE destination of a nav item → ``(route, path_tokens,
    route_name)``. Superset of :func:`_item_href`: also reads the ``target``
    prop (via ``vue_href_keys``) and a ``to: fn('inbox_view')`` call-expr —
    whose FIRST string arg, when route-name-shaped, is the named-route
    destination (never a URL path, never human copy). An enum ref still feeds
    the path-member channel. Returns ``(None, frozenset(), None)`` for a
    non-destination item."""
    for key, (kind, val) in obj.fields.items():
        if key not in _vue_href_keys():
            continue
        v = (val or "").strip()
        if not v:
            continue
        if kind in ("str", "template"):
            route = normalize_href(v)
            if route:
                return route, frozenset(), None
            if _route_name_shaped(v):
                return None, frozenset(), v
        elif kind == "call" and _route_name_shaped(v):
            return None, frozenset(), v
        elif kind == "ref":
            member = _member_token_of_ref(v)
            toks = frozenset(
                t for t in (_singular(w.lower()) for w in _SPLIT_RE.split(
                    _CAMEL_RE.sub(" ", member)))
                if len(t) >= 2 and not t.isdigit()
            )
            if toks:
                return None, toks, None
    return None, frozenset(), None


def _vue_item_label(obj: _Obj) -> str:
    """VUE-MODE display label. A literal label_keys value is used verbatim
    UNLESS it is really an i18n KEY (dotted identifier / ``$t:`` sentinel /
    ``t('…')`` macro call) — then the humanized meaningful KEY leaf is the
    label and the i18n VALUE is NEVER read (README law). Falls back to an
    explicit i18n_label_keys field."""
    for key, (kind, val) in obj.fields.items():
        if key not in _label_keys():
            continue
        v = (val or "").strip()
        if not v:
            continue
        if kind == "call":
            return _humanize_i18n_key(v)  # v = the macro's first string arg
        ik = _i18n_key_of_label_value(v)
        if ik is not None:
            return _humanize_i18n_key(ik)
        if kind in ("str", "template"):
            return v
    i18n = _field_str(obj, _i18n_label_keys())
    return _humanize_i18n_key(i18n) if i18n else ""


def _is_nav_item(obj: _Obj, vue: bool = False) -> bool:
    """An item is nav-consumed when it carries a real navigation
    DESTINATION *and* a label/icon (the structural 'rendered by
    navigation' proxy). The destination must be an INTERNAL route
    (``/x``) or an enum/const route reference (``SettingsPath.Objects``):
    a bare relative file path (``src/objects/rocket.object.ts`` — a
    terminal-demo file tree) or an external URL (``https://docs…`` — a
    marketing link, off-surface like a README) is NOT a product nav
    destination and never mints a category. The label/icon CONJUNCT is the
    anti-noise gate (a ``{minWidth, applyStyles}`` v-menu prop object or a
    ``{key,label}`` table-column has no destination and never ingests) —
    vue mode keeps it verbatim, only widening the destination shapes."""
    if vue:
        route, ptoks, rname = _item_dest(obj)
        if route is None and not ptoks and rname is None:
            return False
    else:
        route, ptoks = _item_href(obj)
        if route is None and not ptoks:
            return False
    has_label = any(
        k in _label_keys() or k in _i18n_label_keys() for k in obj.fields
    )
    has_icon = any(
        k in _icon_keys() for k in obj.fields
    ) or any(k in _icon_keys() for k in obj.child_obj)
    return has_label or has_icon


def _collect_sub_items(
    obj: _Obj, source_file: str, vue: bool = False,
) -> list[NavSubItem]:
    """Every nav leaf under ``obj`` — its own nesting arrays, flattened
    (deep ``subItems`` land on the top category), deterministic order."""
    out: list[NavSubItem] = []
    seen: set[tuple[str | None, str, int]] = set()

    def _walk(node: _Obj) -> None:
        # nested arrays first (deterministic key order)
        for key in sorted(node.arrays):
            if key in _nest_keys():
                for child in node.arrays[key]:
                    if _is_nav_item(child, vue):
                        _emit(child)
                    _walk(child)
        for key in sorted(node.child_obj):
            if key in _nest_keys():
                child = node.child_obj[key]
                if _is_nav_item(child, vue):
                    _emit(child)
                _walk(child)

    def _emit(item: _Obj) -> None:
        if vue:
            route, ptoks, rname = _item_dest(item)
            label = _vue_item_label(item)
        else:
            route, ptoks = _item_href(item)
            rname = None
            label = (
                _field_str(item, _label_keys())
                or _humanize_i18n_key(_field_str(item, _i18n_label_keys()) or "")
            )
        key = (route, label, item.line)
        if key in seen:
            return
        seen.add(key)
        out.append(NavSubItem(
            route=route,
            label=label,
            label_tokens=_label_slug_tokens(label),
            path_tokens=ptoks,
            source_file=source_file,
            line=item.line,
            route_name=rname,
        ))

    _walk(obj)
    return out


def _has_nested_nav_array(obj: _Obj, vue: bool = False) -> bool:
    for key in _nest_keys():
        for child in obj.arrays.get(key, []):
            if _is_nav_item(child, vue):
                return True
        c = obj.child_obj.get(key)
        if c is not None and _is_nav_item(c, vue):
            return True
    return False


#: vue-mode: a ``<VListItem :to="{ name: 'users-active' }">`` router-link
#: template binding — the named-route destination (never a URL path). The
#: enclosing file already passed the nav-registry gate; a ``:to``/``:href``
#: binding to a ``{name:…}`` object IS a navigation destination by definition.
_TEMPLATE_TO_NAME_RE = re.compile(
    r""":(?:to|href)\s*=\s*(["'])\s*\{[^{}]*?\bname\s*:\s*"""
    r"""(?:"([^"]+)"|'([^']+)')""",
)


def _module_registry_category(obj: _Obj, path: str) -> NavCategory | None:
    """A ``defineModule({id,name,routes})`` object → ONE nav category named by
    the module, carrying a single self-leaf whose destination token is the
    module ``id`` (the module route base) — ``id:'content'`` → token
    ``content``. The internal ``routes`` are NOT descended (they are param /
    index sub-routes, not top-level nav); the module id is the destination."""
    oid = _obj_id(obj)
    label = _vue_item_label(obj)
    if not oid and not label:
        return None
    disp = label or _humanize(oid or "")
    if not disp.strip():
        return None
    id_toks: frozenset[str] = frozenset()
    if oid:
        id_toks = frozenset(
            t for t in (_singular(w.lower()) for w in _SPLIT_RE.split(
                _CAMEL_RE.sub(" ", oid)))
            if len(t) >= 2 and not t.isdigit()
        )
    self_leaf = NavSubItem(
        route=None, label=disp, label_tokens=_label_slug_tokens(disp),
        path_tokens=id_toks, source_file=path, line=obj.line, route_name=None,
    )
    return NavCategory(
        id=oid or _slug(disp), label=disp, source_file=path, line=obj.line,
        sub_items=(self_leaf,),
    )


def _template_binding_category(path: str, text: str) -> NavCategory | None:
    """vue-mode: harvest ``:to="{name:'X'}"`` router-link bindings from an SFC
    ``<template>`` into ONE per-file category (named by the file stem). Each is
    a named-route destination; the file already passed the nav-registry gate."""
    line_of = _line_of_factory(text)
    subs: list[NavSubItem] = []
    seen: set[str] = set()
    for m in _TEMPLATE_TO_NAME_RE.finditer(text):
        rname = (m.group(2) or m.group(3) or "").strip()
        if not rname or not _route_name_shaped(rname) or rname in seen:
            continue
        seen.add(rname)
        subs.append(NavSubItem(
            route=None, label="", label_tokens=frozenset(),
            path_tokens=frozenset(), source_file=path,
            line=line_of(m.start()), route_name=rname,
        ))
    if not subs:
        return None
    stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    label = _humanize(stem) or "Navigation"
    return NavCategory(
        id=_slug(stem) or "navigation", label=label, source_file=path,
        line=subs[0].line, sub_items=tuple(subs),
    )


def _parse_nav_file(
    path: str, text: str, vue: bool = False,
) -> list[NavCategory]:
    line_of = _line_of_factory(text)

    # const-name -> parsed value node (object) or element list (array),
    # for ref / spread resolution.
    const_obj: dict[str, _Obj] = {}
    const_arr: dict[str, list[tuple[str, Any]]] = {}
    roots: list[tuple[str | None, str, Any, int]] = []  # (name, kind, node, decl_line)

    for m in _DECL_RE.finditer(text):
        name = m.group(1)
        decl_line = line_of(m.start())
        kind, node, _ = _read_value(text, m.end(), line_of, vue)
        if kind == "obj":
            const_obj[name] = node
            roots.append((name, "obj", node, decl_line))
        elif kind == "array":
            const_arr[name] = node
            roots.append((name, "array", node, decl_line))
    for m in _RETURN_RE.finditer(text):
        decl_line = line_of(m.start())
        kind, node, _ = _read_value(text, m.end(), line_of, vue)
        if kind in ("obj", "array"):
            roots.append((None, kind, node, decl_line))

    def _resolve_ref(ident: str) -> _Obj | None:
        return const_obj.get(ident)

    def _array_elems(node: list[tuple[str, Any]]) -> list[tuple[str, Any]]:
        """Flatten spreads (``...MODULES``) one level into element list."""
        out: list[tuple[str, Any]] = []
        for kind, nd in node:
            if kind == "spread" and isinstance(nd, str) and nd in const_arr:
                out.extend(const_arr[nd])
            else:
                out.append((kind, nd))
        return out

    cats: list[NavCategory] = []

    def _add_category(obj: _Obj | None, const_name: str | None,
                      sub_source: _Obj, source_file: str, line: int) -> None:
        subs = _collect_sub_items(sub_source, source_file, vue)
        if not subs:
            return
        label = _category_label(obj, const_name, vue)
        if not label.strip():
            if vue:
                # nav_keys-derivation lane: an anonymous ``return [...]``
                # array's flat leaves (chatwoot ``menuItems = computed(() =>
                # ({ return [{name:'Inbox', to:…}] }))``) are still
                # author-declared nav destinations — name the bucket by the
                # file so their keys are not lost. (The display-grouping lane,
                # ``vue=False``, still drops them to avoid an empty '' category
                # — the twenty marketing-Menu class — so nav_parent is
                # byte-identical.)
                stem = source_file.rsplit("/", 1)[-1].rsplit(".", 1)[0]
                label = _humanize(stem) or "Navigation"
            else:
                # A nav area must have a NAME. An anonymous ``return [...]``
                # array's top-level flat leaves (no object label, no const
                # name) are not a category — dropping them avoids the empty
                # '' bucket (twenty marketing Menu return-array leaves).
                return
        cid = _category_id(obj, const_name, label)
        cats.append(NavCategory(
            id=cid, label=label, source_file=source_file, line=line,
            sub_items=tuple(subs),
        ))

    for const_name, kind, node, decl_line in roots:
        if kind == "obj":
            obj: _Obj = node
            if _has_nested_nav_array(obj, vue):
                _add_category(obj, const_name, obj, path, obj.line)
            # A bare single nav-item object (no nesting, not an array —
            # e.g. ADMIN_SIDEBAR_ITEM) is a top-level sidebar ENTRY, not a
            # category/group; it never synthesizes a self-parent category
            # (a nav_parent is for a SUB-item under a real area).
        else:  # array
            elems = _array_elems(node)
            direct_objs = [nd for (k, nd) in elems if k == "obj"]
            ref_names = [nd for (k, nd) in elems if k == "ref"]
            # (a) elements are categories themselves (nested nav arrays)
            elem_cats = [o for o in direct_objs if _has_nested_nav_array(o, vue)]
            if elem_cats:
                for o in elem_cats:
                    _add_category(o, None, o, path, o.line)
            # (b) elements are flat nav leaves → the CONST is the category
            #     (declared at ``decl_line`` — never a synthetic line 1).
            flat_leaves = [
                o for o in direct_objs
                if _is_nav_item(o, vue) and not _has_nested_nav_array(o, vue)
            ]
            if flat_leaves:
                synthetic = _Obj(line=decl_line)
                synthetic.arrays["items"] = flat_leaves
                _add_category(None, const_name, synthetic, path, decl_line)
            # (c) elements are refs to category-defining consts
            for ident in ref_names:
                ref_obj = _resolve_ref(ident)
                if ref_obj is not None and _has_nested_nav_array(ref_obj, vue):
                    _add_category(ref_obj, ident, ref_obj, path, ref_obj.line)

    # vue-mode: module-registry (``defineModule({...})``) roots + SFC
    # ``:to="{name:…}"`` template bindings — the two Vue-only shapes the JS
    # const/return root-finder cannot reach. Off in the default parse.
    if vue:
        for call in _module_registry_calls():
            for m in re.finditer(re.escape(call) + r"\s*\(\s*(?=\{)", text):
                mkind, mnode, _ = _read_value(text, m.end(), line_of, True)
                if mkind == "obj":
                    mc = _module_registry_category(mnode, path)
                    if mc is not None:
                        cats.append(mc)
        tpl = _template_binding_category(path, text)
        if tpl is not None:
            cats.append(tpl)

    # Dedupe categories by (source_file, line, id) — a def reachable via
    # several arrays (MODULES + ALL_MODULES spread) yields ONE category.
    deduped: dict[tuple[str, int, str], NavCategory] = {}
    for c in cats:
        deduped.setdefault((c.source_file, c.line, c.id), c)
    return sorted(deduped.values(), key=lambda c: (c.source_file, c.line, c.id))


def build_nav_tree(
    ctx: "ScanContext", vue: bool = False,
) -> list[NavCategory]:
    """Every nav category the repo declares, across its nav-registry files.
    Deterministic (sorted tracked order). Empty when the repo has no
    readable nav registry — the inertness path.

    ``vue`` (default False) engages the WYSTAN_VUE_NAV_KEYS parser lift:
    the extra Vue/SFC nav shapes (``target`` prop, ``to: fn('inbox_view')``
    call-expr, ``:to="{name:…}"`` bindings, i18n-macro / dotted-key labels,
    ``defineModule`` module registries). The lift is PER-FILE scoped to the
    Vue surface itself — a ``.vue`` SFC, or a file calling a
    ``module_registry_calls`` wrapper (``defineModule`` — Vue-ecosystem by
    definition). Every other file (the JSX/TSX world) parses with the
    default grammar even under ``vue=True``, so a non-Vue board's nav_keys
    are UNCHANGED by the flag (the inertness law; the twenty marketing-Menu
    ``return [...]`` class stays dropped). The default False parse — the
    live ``nav_parent`` / ``nav_seam_keys`` consumers — is byte-identical
    to the pre-flag engine."""
    repo_root = Path(ctx.repo_path)
    registry_calls = _module_registry_calls() if vue else ()
    cats: list[NavCategory] = []
    for rel in sorted(str(p).replace("\\", "/") for p in ctx.tracked_files):
        if not rel.endswith(_CODE_EXTS):
            continue
        try:
            text = (repo_root / rel).read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeError):
            continue
        if not text or len(text) > _MAX_BYTES:
            continue
        lift = vue and (
            rel.lower().endswith(".vue")
            or any(call + "(" in text for call in registry_calls)
        )
        if not _looks_like_nav_file(rel, text, lift):
            continue
        cats.extend(_parse_nav_file(rel, text, lift))
    return cats


# ── WYSTAN_VUE_NAV_KEYS — nav_keys derivation from the lifted tree ─────────


def _sub_nav_keys(sub: NavSubItem) -> set[str]:
    """The normalized nav keys ONE lifted sub-item contributes (change (d)
    per-NavSubItem union): the first meaningful URL segment of a literal
    route; the destination noun of a named-route (``inbox_view`` → ``inbox``);
    each enum/module path-member token; and the i18n-KEY label leaf tokens
    (``navigation.rest`` → ``rest``). All through ``normalize_anchor_key`` —
    the SAME normalizer the mint href-echo uses."""
    from wystan.pipeline_v2.spine_anchors import normalize_anchor_key
    keys: set[str] = set()
    if sub.route:
        for seg in str(sub.route).strip("/").split("/"):
            if seg and not seg.startswith(":"):
                keys.add(normalize_anchor_key(seg))
                break
    if sub.route_name:
        leaf = _route_name_leaf_key(sub.route_name)
        if leaf:
            keys.add(normalize_anchor_key(leaf))
    for tok in (sub.path_tokens or ()):
        keys.add(normalize_anchor_key(tok))
    for tok in (sub.label_tokens or ()):
        keys.add(normalize_anchor_key(tok))
    return {k for k in keys if k}


def _ws_paths_of(ctx: Any) -> list[str]:
    """Workspace package roots (``packages/hoppscotch-common``), longest-first
    so the most specific package wins a prefix contest."""
    paths = [
        str(getattr(w, "path", "") or "").replace("\\", "/").strip("/")
        for w in (getattr(ctx, "workspaces", None) or [])
    ]
    return sorted((p for p in paths if p), key=len, reverse=True)


def _workspace_of(source_file: str, ws_paths: list[str]) -> str:
    """The workspace-package key owning ``source_file`` (its package root),
    else ``""`` (repo root / single-app) — the per-workspace scoping key."""
    p = str(source_file or "").replace("\\", "/").strip("/")
    for wp in ws_paths:
        if p == wp or p.startswith(wp + "/"):
            return wp
    return ""


def nav_keys_by_workspace(ctx: Any) -> dict[str, frozenset[str]]:
    """The author-declared nav keys of the lifted (vue-mode) tree, SCOPED per
    workspace package (change (d) per-workspace scoping). A key from one
    package's nav registry lands ONLY in that package's bucket, so an admin
    route declared in ``packages/sh-admin`` never exempts a plumbing leaf in
    ``packages/common`` (the diagnosis anti-case). Repo-root / single-app nav
    files bucket under ``""``. Pure function of ``ctx`` — the WYSTAN_VUE_NAV_KEYS
    gate lives at the wiring call site."""
    cats = build_nav_tree(ctx, vue=True)
    ws_paths = _ws_paths_of(ctx)
    out: dict[str, set[str]] = defaultdict(set)
    for c in cats:
        ws = _workspace_of(c.source_file, ws_paths)
        for sub in c.sub_items:
            out[ws] |= _sub_nav_keys(sub)
    return {k: frozenset(v) for k, v in out.items() if v}


def nav_keys_from_nav_tree(ctx: Any) -> frozenset[str]:
    """Flat union of the per-workspace lifted nav keys (change (d) wiring). The
    board-wide signal the DEMOTE consumers read: non-empty ⇒ the nav lane is
    readable and the 6.987 / api-stub passes STOP board-wide abstaining.
    Pure function of ``ctx``; the caller gates on WYSTAN_VUE_NAV_KEYS."""
    flat: set[str] = set()
    for keys in nav_keys_by_workspace(ctx).values():
        flat |= keys
    return frozenset(flat)


def split_nav_key_channels(
    ctx: Any, weak_keys: Any,
) -> tuple[frozenset[str], frozenset[str], dict[str, frozenset[str]], list[str]]:
    """Fix A (RefApp phantom regression, 2026-07-31) — the MINT/DEMOTE nav-key
    channel split: ``(mint_keys, demote_keys, demote_keys_by_ws, ws_paths)``.

    * ``mint_keys``  — EXACTLY the weak product_strings collector echo the
      caller passed, untouched. The mint confirmer (Stage 6.86 anchor
      confirmation) and its mint-coupled telemetry rungs read THIS set — the
      vue/nav-tree lift NEVER reaches them. The strong nav-tree parser reads
      JSX too (B78), so unioning it into the mint channel let sidebar tokens
      (RefApp ``mitre``/``framework``) CONFIRM route-segment anchors the weak
      echo never saw ⇒ phantom PFs born + members stolen.
    * ``demote_keys`` — weak echo ∪ the vue-lift per-workspace union. Read
      ONLY by the post-UF demote layer, where nav evidence EXEMPTS a PF or
      un-abstains a pass — it can protect, never mint.
    * ``demote_keys_by_ws`` / ``ws_paths`` — the per-workspace scoping for
      the devgrain per-leaf exemption (empty dict when the lift is off).

    Flag OFF (kill-switch) ⇒ both sets are the same weak echo and the map is
    empty ⇒ byte-identical to the pre-flag engine. Never raises."""
    mint = frozenset(str(k) for k in (weak_keys or ()))
    if not vue_nav_keys_enabled():
        return mint, mint, {}, []
    try:
        by_ws = nav_keys_by_workspace(ctx)
        ws_paths = _ws_paths_of(ctx)
    except Exception:  # noqa: BLE001 — the lift never breaks a scan
        return mint, mint, {}, []
    demote = set(mint)
    for keys in by_ws.values():
        demote |= keys
    return mint, frozenset(demote), by_ws, ws_paths


# ── PF ↔ nav matching ────────────────────────────────────────────────────────


def _pf_routes(pf: Any, routes_by_file: dict[str, set[str]]) -> set[str]:
    """Normalized routes a PF serves — anchor-file routes (routes_index +
    file-system routing)."""
    out: set[str] = set()
    anchors = [
        str(mf.path) for mf in (getattr(pf, "member_files", None) or [])
        if getattr(mf, "role", None) == "anchor"
    ]
    paths = anchors or [str(p) for p in (getattr(pf, "paths", None) or [])]
    for p in paths:
        p = p.replace("\\", "/")
        for r in routes_by_file.get(p, ()):  # routes_index patterns
            nr = normalize_href(r)
            if nr:
                out.add(nr)
        fsr = route_path_for_file(p)
        if fsr and fsr != "/":
            out.add(fsr.lower())
    return out


def _pf_tokens(pf: Any) -> frozenset[str]:
    toks = set(_tokens(str(getattr(pf, "name", "") or "")))
    dn = getattr(pf, "display_name", None)
    if dn:
        toks |= set(_tokens(str(dn)))
    return frozenset(toks)


def _route_match(pf_routes: set[str], sub: NavSubItem) -> int:
    """Route-match strength of a PF against a nav SUB-item:
      ``2`` — an EXACT route (a PF route equals the sub destination);
      ``1`` — NESTED-under (a PF route is a deeper page below the sub);
      ``0`` — no match.
    The broad direction (a PF ABOVE the sub — an umbrella route claiming a
    specific child leaf) is deliberately NOT a match. Exact beats nested so
    a PF that serves several routes homes on its OWN nav position, not the
    longest ancestor (the ``findings`` vs ``mitre-framework`` trap)."""
    if not sub.route or not pf_routes:
        return 0
    sr = sub.route
    if sr in pf_routes:
        return 2
    if any(r.startswith(sr + "/") for r in pf_routes):
        return 1
    return 0


def _token_match(pf_tokens: frozenset[str], sub: NavSubItem) -> str | None:
    """B78-it2 (Goal 3) — the token-identity channel, legal ONLY for a
    route-LESS nav sub-item. An enum/const-referenced destination (the
    twenty ``SettingsPath.Objects`` class) has no literal href to
    route-match, so exact token identity against its label / enum member
    is the honest remaining evidence. A sub-item that DECLARES a literal
    route is judged by the route channel alone: a PF that does not serve
    that route may not token-guess its way under the area (the RefApp
    ``api`` → 'Mssp' exhibit — the PF's ``{api}`` token equalled the
    humanized i18n label of ``/tenants/api``, a route the PF never
    serves). Returns the honest via channel (``"label"`` when the match
    is the sub-item's display label, ``"path"`` when it is the enum path
    member) or ``None``."""
    if not pf_tokens or sub.route is not None:
        return None
    if sub.label_tokens and pf_tokens == sub.label_tokens:
        return "label"
    if sub.path_tokens and pf_tokens == sub.path_tokens:
        return "path"
    return None


def _routes_by_file(routes_index: list[dict[str, Any]] | None) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for e in routes_index or ():
        if not isinstance(e, dict):
            continue
        fpath = str(e.get("file") or "").replace("\\", "/")
        pat = str(e.get("pattern") or "")
        if fpath and pat:
            out.setdefault(fpath, set()).add(pat)
    return out


def run_nav_parent(
    product_features: list[Any],
    routes_index: list[dict[str, Any]] | None,
    ctx: Any,
    user_flows: list[Any] | None = None,
) -> dict[str, Any] | None:
    """Attach ``nav_parent`` to product features (in place) and return the
    ``scan_meta.nav_tree`` telemetry. Returns ``None`` — no field, no
    telemetry key — when the flag is off OR the repo declares no nav tree
    (byte-identical inertness). PFs are never merged, moved, or minted."""
    if not nav_parent_enabled():
        return None
    if not product_features:
        return None
    try:
        categories = build_nav_tree(ctx)
    except Exception:  # noqa: BLE001 — extraction never breaks a scan
        categories = []
    if not categories:
        return None

    routes_by_file = _routes_by_file(routes_index)
    # UF routes per PF (union of members' router paths) enrich the route set.
    uf_routes_by_pf: dict[str, set[str]] = {}
    for uf in user_flows or ():
        pid = getattr(uf, "product_feature_id", None)
        if not pid:
            continue
        bucket = uf_routes_by_pf.setdefault(str(pid), set())
        for r in (getattr(uf, "routes", None) or ()):
            nr = normalize_href(str(r))
            if nr:
                bucket.add(nr)

    # Ordered (category, sub, sub-index, identity-tokens) tuples → a stable
    # "nav position" list. The identity tokens (category label + sub label
    # + sub route leaf + enum-member) disambiguate a keyless PF that bundles
    # several routes: among equal route-strength matches it homes on the
    # position it most RESEMBLES, not an arbitrary earliest one.
    positions: list[tuple[NavCategory, NavSubItem, int, frozenset[str]]] = []
    for c in categories:
        ctoks = _tokens(c.label)
        for si, sub in enumerate(c.sub_items):
            leaf_toks: frozenset[str] = frozenset()
            if sub.route:
                leaf_toks = _tokens(sub.route.rsplit("/", 1)[-1])
            ident = ctoks | sub.label_tokens | sub.path_tokens | leaf_toks
            positions.append((c, sub, si, ident))

    # Honest per-channel counters (B78-it2 Goal 3): ``route`` (literal /
    # nested href), ``label`` (route-less sub display label), ``path``
    # (route-less enum path member). The old ``slug`` guess — a token hit
    # against a ROUTE-BEARING sub-item — no longer matches at all.
    matched_by_via: dict[str, int] = {"route": 0, "label": 0, "path": 0}

    def _catkey(c: NavCategory) -> tuple[str, int, str]:
        return (c.source_file, c.line, c.id)

    # nav-position key = (unique category key, sub index) — so two
    # categories that happen to share a decl line + sub index never
    # collide (the flat-const line-1 trap).
    pos_to_pfs: dict[tuple[tuple[str, int, str], int], list[str]] = {}
    pos_meta: dict[tuple[tuple[str, int, str], int], tuple[str, str]] = {}
    cat_matched: dict[tuple[str, int, str], int] = {
        _catkey(c): 0 for c in categories
    }

    products = [
        pf for pf in product_features
        if getattr(pf, "layer", "product") == "product"
    ] or list(product_features)

    for pf in products:
        proutes = _pf_routes(pf, routes_by_file)
        proutes |= uf_routes_by_pf.get(str(getattr(pf, "name", "")), set())
        ptoks = _pf_tokens(pf)
        best: tuple[tuple[int, int, int], NavCategory, NavSubItem, int, str] | None = None
        for pos_idx, (c, sub, si, ident) in enumerate(positions):
            via = ""
            # exact route (10) > nested-under route (5) > route-less token
            # identity (1). Exact beats nested so a multi-route PF homes on
            # its OWN position, not the longest ancestor leaf. The token
            # channel never fires against a route-bearing sub-item (B78-it2
            # Goal 3 — the ``api`` → 'Mssp' slug-guess class).
            rm = _route_match(proutes, sub)
            if rm == 2:
                via, score = "route", 10
            elif rm == 1:
                via, score = "route", 5
            else:
                tv = _token_match(ptoks, sub)
                if tv is None:
                    continue
                via, score = tv, 1
            # tie-break: how much the PF RESEMBLES this position (identity
            # token overlap), then earliest nav order — so a bundled PF's
            # route hit on a foreign area loses to the area it names.
            overlap = len(ptoks & ident) if ptoks else 0
            cand = ((score, overlap, -pos_idx), c, sub, si, via)
            if best is None or cand[0] > best[0]:
                best = cand
        if best is None:
            continue
        _rank, c, sub, si, via = best
        pf.nav_parent = {
            "parent_label": c.label,
            "parent_id": c.id,
            "source_file": c.source_file,
            "line": c.line,
            "via": via,
        }
        matched_by_via[via] += 1
        ck = _catkey(c)
        pos_to_pfs.setdefault((ck, si), []).append(
            str(getattr(pf, "name", "")))
        pos_meta[(ck, si)] = (c.label, sub.label)
        cat_matched[ck] += 1

    sub_total = sum(len(c.sub_items) for c in categories)
    matched_positions = {k for k, pfs in pos_to_pfs.items() if pfs}
    duplicates = [
        {
            "category_id": ck[2], "source_file": ck[0], "line": ck[1],
            "sub_index": si,
            "category_label": pos_meta[(ck, si)][0],
            "sub_label": pos_meta[(ck, si)][1],
            "pfs": sorted(pfs),
        }
        for (ck, si), pfs in sorted(pos_to_pfs.items())
        if len(pfs) > 1
    ]
    unrepresented = [
        {"id": c.id, "label": c.label,
         "source_file": c.source_file, "line": c.line}
        for c in categories
        if cat_matched[_catkey(c)] == 0
    ]

    return {
        "enabled": True,
        "source_files": sorted({c.source_file for c in categories}),
        "category_count": len(categories),
        "sub_item_count": sub_total,
        "categories": [
            {"id": c.id, "label": c.label, "source_file": c.source_file,
             "line": c.line, "sub_items": len(c.sub_items),
             "matched_pfs": cat_matched[(c.source_file, c.line, c.id)]}
            for c in categories
        ],
        "matched": sum(matched_by_via.values()),
        "matched_via": dict(matched_by_via),
        "matched_positions": len(matched_positions),
        "unmatched_sub_items": sub_total - len(matched_positions),
        "unrepresented": unrepresented,
        "duplicates": duplicates,
    }


# ── B93 — nav section-landing demote ─────────────────────────────────────────
#
# THE CLASS (canon docs/anchor-arc/pf-product-grain-prompt.md, "navigation
# category"): a nav menu that GROUPS features renders as a category with
# children, not a peer feature; and the section's OVERVIEW/landing route (the
# category index, 0 journeys) is a UI FRAME, not a feature. RefApp
# ``feature-studio`` (display "Feature Studio", anchor
# ``fdir:frontend/src/modules/feature-studio``, 16 members ALL under
# ``…/overview/**``, 0 UFs) is the landing shell of the ``Media Studio``
# nav category; it renders as a flat peer PF and trips the operator exhibit
# ``refapp-feature-studio-nav-child``.
#
# THE DISCRIMINATOR (mechanism, not name/vocabulary) — a PF is a section
# landing iff ALL hold:
#   * it carries ``nav_parent`` (a matched nav-child); AND
#   * it is NOT self-referential — ``nav_parent.parent_id`` differs from its
#     own slug (a self-ref node is BOTH the category header AND a real feature
#     with its own content — RefApp Media Library / Mssp — NEVER demoted); AND
#   * it holds ZERO real (non-synthesized) journeys (a feature WITH journeys is
#     real — Detectors 3 UF, API Keys 2 UF, Investigations 4 UF — NEVER
#     demoted; a 0-journey real-but-uncovered feature is protected by the
#     shape gate below, not erased); AND
#   * SECTION-LANDING SHAPE: EVERY anchor member file sits under a structural
#     section-index segment (``overview``/``index``/``landing``/``home`` from
#     nav-tree.yaml). This is what separates the overview shell from a real
#     uncovered leaf (Cases Unified — 0 UF, but its anchors are case pages, no
#     landing segment → protected) or a UI-component container (Dialogs).
# 0-journey + ``nav_parent`` ALONE is NOT the key: 25/25 RefApp nav-child PFs
# would be false positives if keyed on ``nav_parent`` alone.
#
# CONSERVATION: the demoted PF's member developer_features re-home to the
# nearest surviving ancestor PF (anchor-prefix containment) — else L1/unowned
# (``shared_reason`` marker, files kept), exactly as a never-minted anchor's
# devs would be (the devgrain-demote 6.987 mechanics). Its held (synthesized)
# UFs drop as shell artifacts (telemetry keeps the names). Nothing is lost:
# every file stays in developer_features.
#
# Flag ``WYSTAN_NAV_CATEGORY_DEMOTE`` — default OFF (armed-only; the
# KEY_SCHEMA bump rides a later flip). OFF ⇒ returns None before any mutation,
# no ``scan_meta`` key ⇒ byte-identical. Deterministic, $0 LLM, read-only over
# the settled PF/UF/dev lists.

#: ``shared_reason`` stamped on a demoted landing PF's re-homed devs when no
#: surviving ancestor exists (mirrors devgrain's ``_SHARED_REASON_BAR``).
_NAV_LANDING_REASON = "nav_section_landing_demote"


def _has_landing_segment(path: str, segments: frozenset[str]) -> bool:
    """A path is section-landing when a DIRECTORY segment is a landing token
    (``…/overview/…``) OR its basename stem is one (``index.tsx``)."""
    p = str(path or "").replace("\\", "/").strip().lower()
    parts = [seg for seg in p.split("/") if seg]
    if not parts:
        return False
    for seg in parts[:-1]:
        if seg in segments:
            return True
    base = parts[-1]
    stem = base.rsplit(".", 1)[0] if "." in base else base
    return stem in segments


def _pf_anchor_paths(pf: Any) -> list[str]:
    """A PF's ANCHOR member-file paths (role=='anchor'); else its ``paths``
    (member_files may be dicts or objects — mirror the house accessors)."""
    out: list[str] = []
    for mf in (getattr(pf, "member_files", None) or []):
        if isinstance(mf, dict):
            role, path = mf.get("role"), mf.get("path")
        else:
            role, path = getattr(mf, "role", None), getattr(mf, "path", None)
        if role == "anchor" and path:
            out.append(str(path))
    if out:
        return out
    return [str(p) for p in (getattr(pf, "paths", None) or []) if p]


def _pf_slug(pf: Any) -> str:
    return str(getattr(pf, "name", "") or "").strip().lower()


def is_section_landing_pf(
    pf: Any, real_uf: int, segments: frozenset[str],
) -> bool:
    """See the module section header — the demote discriminator. Pure, no
    mutation; returns True ONLY for a nav-child section-landing shell."""
    np = getattr(pf, "nav_parent", None)
    if not isinstance(np, dict) or not np:
        return False
    parent_id = str(np.get("parent_id") or "").strip().lower()
    if not parent_id:
        return False
    if parent_id == _pf_slug(pf):          # self-ref = category AND feature
        return False
    if real_uf > 0:                        # real journeys = real feature
        return False
    anchor_paths = _pf_anchor_paths(pf)
    if not anchor_paths:
        return False
    return all(_has_landing_segment(p, segments) for p in anchor_paths)


def _nav_anchor_tail(pf: Any) -> str | None:
    aid = str(getattr(pf, "anchor_id", None) or "")
    if ":" not in aid:
        return None
    return aid.split(":", 1)[1].strip("/") or None


def run_nav_category_demote(
    product_features: list[Any],
    developer_features: list[Any] | None,
    user_flows: list[Any] | None,
) -> dict[str, Any] | None:
    """Demote nav section-landing shells (in place) and return the
    ``scan_meta.nav_category_demote`` telemetry. Returns ``None`` — no
    mutation, no key — when the flag is off (byte-identical inertness).

    Depends on ``run_nav_parent`` having run first (reads ``pf.nav_parent``):
    with NAV_PARENT off no PF carries the field, so nothing demotes. Only
    ``product_features`` rows are removed; member devs re-home (ancestor →
    L1/unowned), held UFs drop — every file is conserved in
    ``developer_features``."""
    if not nav_category_demote_enabled():
        return None
    tele: dict[str, Any] = {
        "enabled": True, "demoted": [], "abstained_no_landing": [],
        "self_ref_skipped": [], "has_journeys_skipped": [],
        "devs_repointed": 0, "devs_unowned": 0, "dropped_ufs": {},
    }
    products = [
        pf for pf in (product_features or [])
        if getattr(pf, "layer", "product") == "product"
    ]
    if not products:
        return tele

    segments = _section_landing_segments()

    real_uf: dict[str, int] = {}
    held: dict[str, list[Any]] = defaultdict(list)
    for uf in (user_flows or []):
        pid = getattr(uf, "product_feature_id", None)
        if not pid:
            continue
        held[str(pid)].append(uf)
        if not getattr(uf, "synthesized", False):
            real_uf[str(pid)] = real_uf.get(str(pid), 0) + 1

    # Phase 1 — decide against the same pre-pass board (sorted → deterministic).
    demote: list[Any] = []
    for pf in sorted(products, key=lambda p: str(getattr(p, "name", "") or "")):
        name = str(getattr(pf, "name", "") or "")
        np = getattr(pf, "nav_parent", None)
        if not isinstance(np, dict) or not np:
            continue
        parent_id = str(np.get("parent_id") or "").strip().lower()
        if parent_id and parent_id == name.strip().lower():
            tele["self_ref_skipped"].append(name)
            continue
        if real_uf.get(name, 0) > 0:
            tele["has_journeys_skipped"].append(name)
            continue
        if is_section_landing_pf(pf, real_uf.get(name, 0), segments):
            demote.append(pf)
        elif parent_id:
            # 0-journey non-self-ref nav-child that FAILED the landing shape —
            # a real-but-uncovered feature or a UI container: protected.
            tele["abstained_no_landing"].append(name)
    if not demote:
        return tele

    demote_keys = {str(getattr(pf, "name", "") or "") for pf in demote}
    devs_by_pf: dict[str, list[Any]] = defaultdict(list)
    for f in (developer_features or []):
        pid = getattr(f, "product_feature_id", None)
        if pid:
            devs_by_pf[str(pid)].append(f)

    surviving = [
        pf for pf in product_features
        if str(getattr(pf, "name", "") or "") not in demote_keys
    ]

    def _ancestor(tail: str | None) -> Any:
        if not tail:
            return None
        best: tuple[int, str, Any] | None = None
        for other in surviving:
            opath = _nav_anchor_tail(other)
            if not opath:
                continue
            if tail.startswith(opath + "/"):
                okey = str(getattr(other, "name", "") or "")
                cand = (len(opath), okey, other)
                if best is None or (cand[0], cand[1]) > (best[0], best[1]):
                    best = cand
        return best[2] if best else None

    # Phase 2 — apply (sorted; the husk-post-uf-fold / devgrain mechanics).
    dropped_uf_ids: set[int] = set()
    for pf in sorted(demote, key=lambda p: str(getattr(p, "name", "") or "")):
        name = str(getattr(pf, "name", "") or "")
        aid = str(getattr(pf, "anchor_id", None) or "")
        target = _ancestor(_nav_anchor_tail(pf))
        held_ufs = held.get(name, [])
        if held_ufs:
            tele["dropped_ufs"][name] = sorted(
                str(getattr(u, "name", "") or "") for u in held_ufs)
            dropped_uf_ids.update(id(u) for u in held_ufs)
        for m in sorted(devs_by_pf.get(name, ()),
                        key=lambda d: str(getattr(d, "name", "") or "")):
            if target is not None:
                m.product_feature_id = str(getattr(target, "name", "") or "")
                m.anchor_id = f"fold:nav-section-landing->{aid}"
                if getattr(m, "shared_reason", None):
                    m.shared_reason = None
                tele["devs_repointed"] += 1
            else:
                # No minting ancestor — L1/unowned, files kept (natural
                # demotion, never a silent deletion).
                m.product_feature_id = None
                m.anchor_id = None
                m.shared_reason = _NAV_LANDING_REASON
                tele["devs_unowned"] += 1
        if target is not None:
            seen_p = set(getattr(target, "paths", None) or [])
            merged_p = list(getattr(target, "paths", None) or [])
            for p in (getattr(pf, "paths", None) or []):
                if p not in seen_p:
                    seen_p.add(p)
                    merged_p.append(p)
            target.paths = merged_p
            seen_mf = {
                (mf.get("path") if isinstance(mf, dict)
                 else getattr(mf, "path", None))
                for mf in (getattr(target, "member_files", None) or [])
            }
            for mf in (getattr(pf, "member_files", None) or []):
                mfp = (mf.get("path") if isinstance(mf, dict)
                       else getattr(mf, "path", None))
                if mfp and mfp not in seen_mf:
                    seen_mf.add(mfp)
                    target.member_files.append(mf)
        tele["demoted"].append({
            "pf": name, "anchor": aid,
            "parent_id": (pf.nav_parent or {}).get("parent_id"),
            "into": (str(getattr(target, "name", "") or "")
                     if target is not None else None),
            "members": len(getattr(pf, "member_files", None) or []),
            "ufs_dropped": len(held_ufs),
        })

    product_features[:] = [
        pf for pf in product_features
        if str(getattr(pf, "name", "") or "") not in demote_keys
    ]
    if dropped_uf_ids and user_flows is not None:
        user_flows[:] = [u for u in user_flows if id(u) not in dropped_uf_ids]
    return tele
