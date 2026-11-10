"""User-visible text of a repository, keyed by the file that shows it.

The product layer is named from the words the product shows its users, not
from where the code lives. This module reads those words out of UI source
files: page titles, headings, dialog and card titles, button text, form
labels, and any other translated copy.

Text is recognised in three written forms:

  * plain JSX / template text (``<h1>Team members</h1>``);
  * inline translation macros, where the English text is in the source
    (``<Trans>Team members</Trans>``, ``msg`Team members```, ``t`Save```);
  * catalog keys (``t("team.members.title")``), resolved against the
    repository's default-locale catalog.

Scope: TS/JS/JSX/Vue/Svelte sources. Deterministic, no LLM, and no prose
documentation: README and docs are never read here.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from wystan.pipeline_v2.product_strings import (
    _is_human_string,
    _is_i18n_catalog,
    _read_text,
)

__all__ = ["KIND_RANK", "UiLabel", "UiTextIndex", "collect_ui_text", "extract_ui_labels"]

#: Label kinds, most name-worthy first.
KIND_RANK = {"title": 0, "heading": 1, "section": 2, "action": 3, "label": 4, "text": 5}

_UI_EXTENSIONS = (".tsx", ".jsx", ".ts", ".js", ".mjs", ".vue", ".svelte")
_MAX_LABELS_PER_FILE = 60
_MAX_INNER_CHARS = 240

_MACRO = r"(?:msg|t|defineMessage)"
_QUOTED = r"""(?:`([^`$]{2,120})`|'([^'\n]{2,120})'|"([^"\n]{2,120})")"""
_TITLE_CALL = re.compile(
    rf"\b\w*(?:[Mm]eta|[Tt]itle)\w*\(\s*(?:_\(\s*)?{_MACRO}?\s*\(?\s*{_QUOTED}",
)
_TITLE_TAG = re.compile(r"<title[^>]*>(.{2,%d}?)</title>" % _MAX_INNER_CHARS, re.DOTALL)
_HEADING_TAG = re.compile(r"<h([1-3])\b[^>]*>(.{2,%d}?)</h\1>" % _MAX_INNER_CHARS, re.DOTALL)
_NAMED_TAG = re.compile(
    r"<(\w*(?:Title|Heading|Button|Label))\b[^>]*?(?<!/)>(.{2,%d}?)</\1>" % _MAX_INNER_CHARS,
    re.DOTALL,
)
_PROP = re.compile(
    rf"\b(title|heading|label|placeholder|aria-label)\s*[=:]\s*\{{?\s*(?:_\(\s*)?{_MACRO}?\s*\(?\s*{_QUOTED}",
)
_TRANS_TAG = re.compile(r"<Trans\b[^>]*>(.{2,%d}?)</Trans>" % _MAX_INNER_CHARS, re.DOTALL)
_MACRO_CALL = re.compile(rf"\b{_MACRO}\s*\(?\s*`([^`$]{{2,120}})`")
_KEY_CALL = re.compile(r"""(?<![\w.])\$?t\(\s*['"]([\w.:\-]{3,120})['"]""")
_INNER_MACRO = re.compile(rf"\{{\s*(?:_\(\s*)?{_MACRO}?\s*\(?\s*{_QUOTED}[^}}]*\}}")
_INNER_KEY = re.compile(r"""\{\{?\s*\$?t\(\s*['"]([\w.:\-]{3,120})['"][^}]*\}\}?""")
_INNER_EXPR = re.compile(r"\{[^{}]*\}")
_INNER_TAG = re.compile(r"<[^>]+>")
_PROP_KINDS = {"title": "section", "heading": "section"}
# Source code that survived the cleaning (an arrow function inside a tag, a
# chained call): never user-visible text.
_CODE_FRAGMENT = re.compile(r"[=<>{}]|\w\(|\)\s*[.;]|^\.")


@dataclass(frozen=True)
class UiLabel:
    """One piece of user-visible text and the kind of place it is shown."""

    text: str
    kind: str
    file: str


@dataclass
class UiTextIndex:
    """User-visible labels per file."""

    by_file: dict[str, list[UiLabel]] = field(default_factory=dict)

    def labels_for(self, paths: Iterable[str]) -> list[UiLabel]:
        """Labels of ``paths``, best kind first, de-duplicated by text."""
        rows = [label for path in sorted(set(paths)) for label in self.by_file.get(path, [])]
        rows.sort(key=lambda label: (KIND_RANK[label.kind], label.file, label.text))
        seen: set[str] = set()
        unique: list[UiLabel] = []
        for label in rows:
            if label.text.lower() not in seen:
                seen.add(label.text.lower())
                unique.append(label)
        return unique

    def vocabulary(self) -> frozenset[str]:
        """Every lowercase word the product shows anywhere."""
        words: set[str] = set()
        for labels in self.by_file.values():
            for label in labels:
                words.update(re.findall(r"[a-z]+", label.text.lower()))
        return frozenset(words)


def _first_group(match: re.Match[str], start: int) -> str:
    return next((g for g in match.groups()[start:] if g), "")


def _clean_inner(inner: str, catalog: dict[str, str]) -> str:
    """JSX inner content reduced to the text a user reads."""
    # Catalog keys first: ``t('billing.title')`` also has the shape of an
    # inline macro, and its key is not text.
    text = _INNER_KEY.sub(lambda m: catalog.get(m.group(1), m.group(0)), inner)
    text = _INNER_MACRO.sub(lambda m: _first_group(m, 0), text)
    text = _INNER_TAG.sub(" ", _INNER_EXPR.sub(" ", text))
    return re.sub(r"\s+", " ", text).strip()


def _named_kind(tag: str) -> str:
    if tag.endswith("Button"):
        return "action"
    if tag.endswith("Label"):
        return "label"
    return "section"


def _raw_labels(text: str, catalog: dict[str, str]) -> list[tuple[str, str]]:
    """``(kind, text)`` candidates of one source file, unfiltered."""
    found: list[tuple[str, str]] = []
    found += [("title", _first_group(m, 0)) for m in _TITLE_CALL.finditer(text)]
    found += [("title", _clean_inner(m.group(1), catalog)) for m in _TITLE_TAG.finditer(text)]
    for match in _HEADING_TAG.finditer(text):
        kind = "heading" if match.group(1) == "1" else "section"
        found.append((kind, _clean_inner(match.group(2), catalog)))
    for match in _NAMED_TAG.finditer(text):
        found.append((_named_kind(match.group(1)), _clean_inner(match.group(2), catalog)))
    for match in _PROP.finditer(text):
        kind = _PROP_KINDS.get(match.group(1), "label")
        found.append((kind, _first_group(match, 1)))
    found += [("text", _clean_inner(m.group(1), catalog)) for m in _TRANS_TAG.finditer(text)]
    found += [("text", m.group(1)) for m in _MACRO_CALL.finditer(text)]
    found += [("text", catalog.get(m.group(1), "")) for m in _KEY_CALL.finditer(text)]
    return found


def extract_ui_labels(path: str, text: str, catalog: dict[str, str] | None = None) -> list[UiLabel]:
    """User-visible labels of one source file. A text keeps its best kind."""
    best: dict[str, tuple[int, str, str]] = {}
    for kind, raw in _raw_labels(text, catalog or {}):
        label = raw.strip()
        if not _is_human_string(label) or _CODE_FRAGMENT.search(label):
            continue
        key = label.lower()
        if key not in best or KIND_RANK[kind] < best[key][0]:
            best[key] = (KIND_RANK[kind], kind, label)
    ranked = sorted(best.values(), key=lambda row: (row[0], row[2]))
    return [UiLabel(label, kind, path) for _, kind, label in ranked[:_MAX_LABELS_PER_FILE]]


def _flatten_catalog(node: object, prefix: str, out: dict[str, str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            _flatten_catalog(value, f"{prefix}.{key}" if prefix else str(key), out)
    elif isinstance(node, str) and _is_human_string(node):
        out.setdefault(prefix, node)


def _load_catalog(repo_path: Path, all_files: Iterable[str]) -> dict[str, str]:
    """``dotted.key -> English text`` from the default-locale JSON catalogs."""
    catalog: dict[str, str] = {}
    for rel in sorted(set(all_files)):
        if not rel.lower().endswith(".json") or not _is_i18n_catalog(rel):
            continue
        raw = _read_text(repo_path, rel)
        try:
            parsed = json.loads(raw) if raw else None
        except ValueError:
            continue
        _flatten_catalog(parsed, "", catalog)
        # A namespace file (``locales/en/billing.json``) is addressed as
        # ``billing:key`` or ``billing.key`` by the common i18n libraries.
        namespace = rel.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        scoped: dict[str, str] = {}
        _flatten_catalog(parsed, "", scoped)
        for key, value in scoped.items():
            catalog.setdefault(f"{namespace}.{key}", value)
            catalog.setdefault(f"{namespace}:{key}", value)
    return catalog


def collect_ui_text(
    repo_path: Path, candidate_paths: Iterable[str], all_files: Iterable[str] = (),
) -> UiTextIndex:
    """Collect user-visible labels from ``candidate_paths`` (repo-relative).

    ``all_files`` is where translation catalogs are looked for; without it
    catalog keys stay unresolved and only inline text is read."""
    catalog = _load_catalog(repo_path, all_files)
    index = UiTextIndex()
    for rel in sorted(set(candidate_paths)):
        if not rel.endswith(_UI_EXTENSIONS):
            continue
        text = _read_text(repo_path, rel)
        if not text:
            continue
        labels = extract_ui_labels(rel, text, catalog)
        if labels:
            index.by_file[rel] = labels
    return index
