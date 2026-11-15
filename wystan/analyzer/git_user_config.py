"""The one piece of the user's own git configuration the engine honours.

The user's configuration is trusted; the clone's is not. The runner reads
no global config (``GIT_CONFIG_GLOBAL`` is the null device), which also
dropped the user's global ignore file, so the content identity started to
follow files the user's own git ignores (``.DS_Store``). The ignore file's
path is resolved once per home, outside any repository, and passed to the
commands that list untracked files; nothing else is taken over.
"""

from __future__ import annotations

import functools
import os
import tempfile

from wystan.analyzer.git_process import GitError, run_bounded
from wystan.analyzer.git_resolution import UnsafeGit, git_executable

_OUTPUT_BYTES = 1 << 16

#: Where git looks for the user's ignore file when core.excludesFile is unset.
_XDG_IGNORE = ("git", "ignore")
_USER_CONFIG_TIMEOUT_SEC = 10.0


def _user_excludes_from_config(git: str, home: str, xdg: str) -> str | None:
    """``core.excludesFile`` from the user's own global config (trusted: the
    user's, not the clone's), read outside any repository."""
    neutral = tempfile.gettempdir()
    env = {"PATH": os.path.dirname(git), "HOME": home, "GIT_CONFIG_NOSYSTEM": "1", "LC_ALL": "C",
           "GIT_CEILING_DIRECTORIES": os.path.dirname(os.path.realpath(neutral))}
    if xdg:
        env["XDG_CONFIG_HOME"] = xdg
    argv = [git, "-C", neutral, "config", "--global", "--path", "--get", "core.excludesFile"]
    try:
        result = run_bounded(argv, env, _USER_CONFIG_TIMEOUT_SEC, _OUTPUT_BYTES)
    except GitError:
        return None
    value = result.text.strip()
    return value if result.returncode == 0 and value else None


@functools.lru_cache(maxsize=4)
def _user_excludes(home: str, xdg: str) -> str | None:
    try:
        git = git_executable(None)
    except UnsafeGit:
        return None
    configured = _user_excludes_from_config(git, home, xdg)
    if configured:
        return configured
    default = os.path.join(xdg or os.path.join(home, ".config"), *_XDG_IGNORE)
    return default if os.path.isfile(default) else None


def user_excludes_file() -> str | None:
    """The user's global ignore file (``core.excludesFile`` of their global
    config, else git's XDG default), resolved once per home. The runner
    passes it to commands that list untracked files, so the content
    identity ignores what the user's git ignores; nothing else of the
    user's configuration is honoured."""
    home = os.environ.get("HOME", "")
    return _user_excludes(home, os.environ.get("XDG_CONFIG_HOME", "")) if home else None
