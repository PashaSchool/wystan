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
section's ``excludesFile`` key and follows no ``include``: an excludes
setting reached only through an include is not honoured (logged once).
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
_INCLUDE_SECTIONS = frozenset({"include", "includeif"})
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


def excludes_setting(text: str) -> tuple[str | None, bool]:
    """``(core.excludesFile value or None, whether the file has an include)``."""
    section, found, has_include = "", None, False
    for line in text.splitlines():
        header = _SECTION.match(line)
        if header:
            section = header.group(1).lower()
            has_include = has_include or section in _INCLUDE_SECTIONS
            line = header.group(2)
            if not line.strip():
                continue
        entry = _KEY.match(line)
        if entry and section == _CORE and entry.group(1).lower() == _EXCLUDES_KEY and entry.group(2):
            found = _value(entry.group(2))
    return found, has_include


def _expand(value: str, home: str) -> str:
    if value == "~":
        return home
    if value.startswith("~/"):
        return os.path.join(home, value[2:])
    return value


@functools.lru_cache(maxsize=4)
def _user_excludes(home: str, xdg: str) -> str | None:
    config_home = xdg or os.path.join(home, ".config")
    found, includes = None, False
    for path in (os.path.join(config_home, "git", "config"), os.path.join(home, ".gitconfig")):
        text = _read_user_file(path)
        if text is None:
            continue
        value, has_include = excludes_setting(text)
        found = value or found
        includes = includes or has_include
    if includes:
        logger.info("git: the user's global config has an include; an excludesFile set only there is not honoured")
    if found:
        return _expand(found, home)
    default = os.path.join(config_home, "git", "ignore")
    return default if os.path.isfile(default) else None


def user_excludes_file() -> str | None:
    """The user's global ignore file, resolved once per home. The runner
    passes it to commands that list untracked files; nothing else of the
    user's configuration is honoured."""
    home = os.environ.get("HOME", "")
    return _user_excludes(home, os.environ.get("XDG_CONFIG_HOME", "")) if home else None
