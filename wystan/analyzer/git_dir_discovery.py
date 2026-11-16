"""Which git directory, and which object format, git will use for a
working tree: found from the file system, without running git.

The index inspection (``git_index``) must look at the very index git will
read. git's answer alone is not enough: a path holding a newline shifts a
line-split answer, and a malformed answer must never read as "nothing to
refuse". So the engine finds the git directory the way git's discovery
does (from the scan root upward, the first ``.git`` directory or
``gitdir:`` file naming a valid git directory, else the directory itself
when it is a bare one, never across a file-system boundary), reads
``extensions.objectFormat`` from the repository's config, and uses git's
answers only to confirm. Pointer and config reads are bounded
(``git_discovery.read_git_metadata``).
"""

from __future__ import annotations

import os
import stat

from wystan.analyzer.git_discovery import read_git_metadata

_DOT_GIT = ".git"
_GITDIR_PREFIX = "gitdir:"
_COMMONDIR = "commondir"
#: A repository config is small; a larger one is not read (the index is
#: then refused: its object format is unknown).
CONFIG_READ_BYTES = 1 << 20
DEFAULT_OBJECT_FORMAT = "sha1"
#: Characters no git directory path the engine accepts may hold: each could
#: make one answer read as two.
UNSAFE_PATH_CHARACTERS = ("\n", "\r", "\0")


def has_unsafe_characters(path: str) -> bool:
    return any(ch in path for ch in UNSAFE_PATH_CHARACTERS)


def one_value(stdout: bytes, allow_empty: bool = False) -> str | None:
    """git's answer to a one-value query (``rev-parse <flag>``): exactly one
    line ending in a newline, holding no other line break and no NUL;
    ``None`` for anything else. A multi-value query split on newlines would
    let a path holding a newline shift every value after it."""
    text = stdout.decode("utf-8", "surrogateescape")
    if not text.endswith("\n"):
        return None
    value = text[:-1]
    if has_unsafe_characters(value) or (not value and not allow_empty):
        return None
    return value


def common_dir(git_dir: str, start: str) -> str:
    """The common directory a linked git directory names, else itself."""
    named = read_git_metadata(os.path.join(git_dir, _COMMONDIR), start)
    return os.path.normpath(os.path.join(git_dir, named)) if named else git_dir


def _is_git_dir(path: str, start: str) -> bool:
    """git's ``is_git_directory``: a HEAD, and objects and refs in the
    common directory."""
    common = common_dir(path, start)
    return (os.path.lexists(os.path.join(path, "HEAD")) and os.path.isdir(os.path.join(common, "objects"))
            and os.path.isdir(os.path.join(common, "refs")))


def _dot_git_target(directory: str, start: str) -> str | None:
    """What ``directory/.git`` names: itself (a valid git directory, or a
    link to one), the target of a ``gitdir:`` file, or ``None``. git walks
    past a ``.git`` directory that is not a git directory, and stops (it
    fails) at a ``.git`` file whatever it names."""
    dot_git = os.path.join(directory, _DOT_GIT)
    if os.path.isdir(dot_git):
        return dot_git if _is_git_dir(dot_git, start) else None
    if not os.path.isfile(dot_git):
        return None
    pointer = read_git_metadata(dot_git, start)
    if not pointer or not pointer.startswith(_GITDIR_PREFIX):
        return None
    return os.path.normpath(os.path.join(directory, pointer[len(_GITDIR_PREFIX):].strip()))


def discovered_git_dir(start: str) -> str | None:
    """The git directory git's discovery finds from ``start``, or ``None``
    when there is none."""
    current = os.path.realpath(start)
    device = os.stat(current).st_dev
    while True:
        target = _dot_git_target(current, start)
        if target is not None:
            # git stops at a .git it cannot use too (it fails there).
            return target
        if _is_git_dir(current, start):
            return current
        parent = os.path.dirname(current)
        if parent == current or os.stat(parent).st_dev != device:
            return None
        current = parent


def is_plain_directory(path: str) -> bool:
    try:
        return stat.S_ISDIR(os.lstat(os.path.realpath(path)).st_mode)
    except OSError:
        return False


def _config_value(text: str, section_wanted: str, key_wanted: str) -> str | None:
    section, found = "", None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            section = stripped.strip("[]").strip().lower()
        elif section == section_wanted and "=" in stripped:
            key, _, value = stripped.partition("=")
            if key.strip().lower() == key_wanted:
                found = value.split("#")[0].split(";")[0].strip().strip('"').lower()
    return found


def configured_object_format(git_dir: str, start: str) -> str | None:
    """``extensions.objectFormat`` of the repository's config (``sha1`` when
    unset); ``None`` when the config cannot be read."""
    config = os.path.join(common_dir(git_dir, start), "config")
    text = read_git_metadata(config, start, CONFIG_READ_BYTES)
    if text is None:
        return None
    return _config_value(text, "extensions", "objectformat") or DEFAULT_OBJECT_FORMAT
