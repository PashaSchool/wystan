"""The one piece of the user's own git configuration the engine honours.

The user's configuration is trusted; the clone's is not. The runner reads
no global config (``GIT_CONFIG_GLOBAL`` is the null device), which also
dropped the user's global ignore file, so the content identity started to
follow files the user's own git ignores (``.DS_Store``). The ignore file's
path is found here without starting git (a git started without the scanned
root could be one planted in the scanned tree): ``core.excludesFile`` is
read from the user's global config files, ``$XDG_CONFIG_HOME/git/config``
(else ``~/.config/git/config``) then ``~/.gitconfig``, the last one wins,
with ``~`` expanded; when unset, git's default ``$XDG_CONFIG_HOME/git/ignore``
(else ``~/.config/git/ignore``). The parser reads only the ``[core]``
section's ``excludesFile`` key, follows ``[include] path`` one level (the
user's own files), and follows no ``includeIf`` (an excludes setting there
is not honoured; logged once). An empty ``excludesFile =`` means no ignore
file, as in git.
"""

from __future__ import annotations

import functools
import logging
import os
import re

logger = logging.getLogger(__name__)

#: A user's git config is small; read no more of it.
_CONFIG_READ_BYTES = 1 << 20
_SECTION = re.compile(r"^\s*\[\s*([A-Za-z0-9.-]+)\s*(?:\"[^\"]*\")?\s*\]\s*(.*)$")
_KEY = re.compile(r"^\s*([A-Za-z][A-Za-z0-9-]*)\s*(?:=\s*(.*))?$")
_EXCLUDES_KEY = "excludesfile"
_CORE = "core"
_INCLUDE, _CONDITIONAL_INCLUDE, _PATH_KEY = "include", "includeif", "path"
#: The user's own files are trusted; their includes are followed one level.
_INCLUDE_DEPTH = 1
_ESCAPES = {"n": "\n", "t": "\t"}


def _read_user_file(path: str) -> str | None:
    """A file of the user's own (trusted, but bounded and regular-only)."""
    try:
        if not os.path.isfile(path):
            return None
        with open(path, "rb") as fh:
            return fh.read(_CONFIG_READ_BYTES).decode("utf-8", "replace")
    except OSError:
        return None


def _value(raw: str) -> str:
    """A config value: quotes removed, escapes resolved, a comment outside
    quotes dropped."""
    out, quoted, index = [], False, 0
    while index < len(raw):
        char = raw[index]
        if char == "\\" and index + 1 < len(raw):
            out.append(_ESCAPES.get(raw[index + 1], raw[index + 1]))
            index += 2
            continue
        if char == '"':
            quoted = not quoted
        elif char in "#;" and not quoted:
            break
        else:
            out.append(char)
        index += 1
    return "".join(out).strip()


def settings(text: str) -> tuple[list[tuple[str, str]], bool]:
    """In file order: ``("excludes", value)`` for each ``core.excludesFile``
    (an empty value included) and ``("include", path)`` for each
    ``[include] path``; plus whether an ``includeIf`` (not followed) is there."""
    section, events, conditional = "", [], False
    for line in text.splitlines():
        header = _SECTION.match(line)
        if header:
            section = header.group(1).lower()
            conditional = conditional or section == _CONDITIONAL_INCLUDE
            line = header.group(2)
            if not line.strip():
                continue
        entry = _KEY.match(line)
        if not entry or entry.group(2) is None:
            continue
        key = entry.group(1).lower()
        if section == _CORE and key == _EXCLUDES_KEY:
            events.append(("excludes", _value(entry.group(2))))
        elif section == _INCLUDE and key == _PATH_KEY:
            events.append(("include", _value(entry.group(2))))
    return events, conditional


def excludes_setting(text: str) -> tuple[str | None, bool]:
    """``(the last core.excludesFile value or None, whether the file has an
    include of any kind)`` for one file, includes not followed."""
    events, conditional = settings(text)
    values = [value for kind, value in events if kind == "excludes"]
    return (values[-1] if values else None), conditional or any(kind == "include" for kind, _v in events)


def _expand(value: str, home: str) -> str:
    if value == "~":
        return home
    if value.startswith("~/"):
        return os.path.join(home, value[2:])
    return value


def _file_values(path: str, home: str, depth: int) -> tuple[list[str], bool]:
    """``core.excludesFile`` values of one user config file in order, its
    ``[include] path`` files followed ``depth`` levels (relative to the
    including file's directory, ``~`` expanded)."""
    text = _read_user_file(path)
    if text is None:
        return [], False
    events, conditional = settings(text)
    values: list[str] = []
    for kind, value in events:
        if kind == "excludes":
            values.append(value)
        elif depth > 0 and value:
            included = os.path.join(os.path.dirname(path), _expand(value, home))
            nested, nested_conditional = _file_values(included, home, depth - 1)
            values += nested
            conditional = conditional or nested_conditional
    return values, conditional


@functools.lru_cache(maxsize=4)
def _user_excludes(home: str, xdg: str) -> str | None:
    config_home = xdg or os.path.join(home, ".config")
    values, conditional = [], False
    for path in (os.path.join(config_home, "git", "config"), os.path.join(home, ".gitconfig")):
        found, has_conditional = _file_values(path, home, _INCLUDE_DEPTH)
        values += found
        conditional = conditional or has_conditional
    if conditional:
        logger.info("git: the user's global config has an includeIf; an excludesFile set only there is not honoured")
    if values:
        # The last setting wins; an empty one means "no ignore file", as in git.
        return _expand(values[-1], home) if values[-1] else None
    default = os.path.join(config_home, "git", "ignore")
    return default if os.path.isfile(default) else None


def user_excludes_file() -> str | None:
    """The user's global ignore file, resolved once per home. The runner
    passes it to commands that list untracked files; nothing else of the
    user's configuration is honoured."""
    home = os.environ.get("HOME", "")
    return _user_excludes(home, os.environ.get("XDG_CONFIG_HOME", "")) if home else None
