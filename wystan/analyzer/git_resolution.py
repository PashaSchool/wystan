"""Which git the runner may start for a scanned path, and its environment.

Only the scanned repository is untrusted, and all of it: a scan may name a
subdirectory (``--subpath``, a workspace), so search locations are excluded
for the whole working tree it belongs to (for exclusion, a wider root is the
safe direction). Resolution, cached per (path, ``PATH``):

1. Exclusion roots without running anything: the given path, plus the
   working tree found by walking up to the nearest ``.git`` (directory, or
   a ``.git`` file's ``gitdir:``) and its git and common directories.
2. git on the caller's ``PATH`` with empty, ``.`` and relative entries
   dropped (they make the current directory a search location) and every
   entry inside a root dropped, by file identity; a result inside a root is
   refused.
3. That git, with the runner's options and environment, confirms the roots
   (``rev-parse --show-toplevel --absolute-git-dir --git-common-dir``);
   when it names a root step 1 did not, the search is redone over the
   union and its answer replaces the first.

An absolute entry under the current directory is kept: a service whose cwd
is ``/`` must find ``/usr/bin/git``. On Windows
``NoDefaultCurrentDirectoryInExePath`` keeps the system from searching the
current directory, and the lookup here never adds it.
"""

from __future__ import annotations

import functools
import os

from wystan.analyzer.git_process import GitError, run_bounded
from wystan.analyzer.path_identity import is_within

#: Options that switch off what a clone's configuration could make git run,
#: and pin the few settings the engine's parsers depend on.
SAFE_OPTIONS = (
    "--no-pager",
    "-c", "core.fsmonitor=false",
    "-c", f"core.hooksPath={os.devnull}",
    "-c", "core.pager=cat",
    "-c", "core.untrackedCache=false",
    "-c", f"core.attributesFile={os.devnull}",
    "-c", "diff.external=",
    # The engine never fetches; a promisor remote or a submodule must not
    # make a read command open a connection (or run core.sshCommand).
    "-c", "protocol.allow=never",
    "-c", "protocol.file.allow=never",
    # A submodule's own configuration (hooks, filters) must never apply.
    "-c", "submodule.recurse=false",
    # A signature check runs gpg and prints into ``git log`` output.
    "-c", "log.showSignature=false",
    # The parsers read C-quoted names (git's default); a clone setting it
    # false would change their input.
    "-c", "core.quotepath=true",
    "-c", "color.ui=false",
)

_WINDOWS = os.name == "nt"
#: A ``.git`` file or ``commondir`` file is one short line; read no more.
_POINTER_FILE_BYTES = 4096
_GITDIR_PREFIX = "gitdir:"
_DISCOVERY_TIMEOUT_SEC = 10.0
_DISCOVERY_OUTPUT_BYTES = 1 << 16
#: Ownership is not a question for this read-only probe (every option above
#: applies); the scan's own calls name only the scanned root.
_DISCOVERY_SAFE_DIRECTORY = "safe.directory=*"


class UnsafeGit(GitError):
    """No git outside the scanned repository was found."""


def _read_pointer(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read(_POINTER_FILE_BYTES).strip()
    except OSError:
        return None


def _common_dir(git_dir: str) -> str:
    pointer = _read_pointer(os.path.join(git_dir, "commondir"))
    return os.path.normpath(os.path.join(git_dir, pointer)) if pointer else git_dir


def discovered_roots(start: str) -> tuple[str, ...]:
    """Working tree, git directory and common directory of the nearest
    ``.git`` at or above ``start``, from the file system alone."""
    current = os.path.realpath(start)
    while True:
        dot_git = os.path.join(current, ".git")
        if os.path.isdir(dot_git):
            return (current, dot_git, _common_dir(dot_git))
        pointer = _read_pointer(dot_git) if os.path.isfile(dot_git) else None
        if pointer and pointer.startswith(_GITDIR_PREFIX):
            git_dir = os.path.normpath(os.path.join(current, pointer[len(_GITDIR_PREFIX):].strip()))
            return (current, git_dir, _common_dir(git_dir))
        parent = os.path.dirname(current)
        if parent == current:
            return ()
        current = parent


def _absolute_entries(path: str | None) -> list[str]:
    entries = (os.environ.get("PATH", os.defpath) if path is None else path).split(os.pathsep)
    return [e for e in entries if e and e != "." and os.path.isabs(e)]


def _outside(entries: list[str], roots: tuple[str, ...]) -> str:
    return os.pathsep.join(e for e in entries if not any(is_within(e, r) for r in roots))


def _executable_names() -> tuple[str, ...]:
    if not _WINDOWS:
        return ("git",)
    extensions = os.environ.get("PATHEXT", ".EXE").split(os.pathsep)
    return tuple(f"git{ext.lower()}" for ext in extensions if ext)


@functools.lru_cache(maxsize=8)
def _which(search_path: str) -> str | None:
    # Not shutil.which: on Windows before Python 3.12 it searches the current
    # directory first even when given an explicit path.
    for entry in search_path.split(os.pathsep):
        for name in _executable_names():
            candidate = os.path.join(entry, name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return os.path.realpath(candidate)
    return None


def base_environment(search_path: str) -> dict[str, str]:
    """The whole environment of a git child. ``HOME`` is the null device so
    nothing of the user's home (XDG config, ignore and attributes files,
    ``~`` in an include path) is read."""
    env = {
        "PATH": search_path, "HOME": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull, "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C",
    }
    if _WINDOWS:
        env["NoDefaultCurrentDirectoryInExePath"] = "1"
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
    return env


def _pick(entries: list[str], roots: tuple[str, ...]) -> str:
    found = _which(_outside(entries, roots))
    if found is None:
        raise UnsafeGit("git not found on the sanitised search path")
    if any(is_within(found, r) for r in roots):
        raise UnsafeGit(f"refusing git inside the scanned repository: {found}")
    return found


def _confirmed_roots(git: str, root: str, search_path: str) -> tuple[str, ...]:
    argv = [git, *SAFE_OPTIONS, "-c", _DISCOVERY_SAFE_DIRECTORY, "-C", root,
            "rev-parse", "--show-toplevel", "--absolute-git-dir", "--git-common-dir"]
    try:
        result = run_bounded(argv, base_environment(search_path), _DISCOVERY_TIMEOUT_SEC, _DISCOVERY_OUTPUT_BYTES)
    except GitError:
        return ()
    lines = result.text.splitlines()
    if result.returncode != 0 or len(lines) != 3:
        return ()  # not in a working tree: the given root stands
    return tuple(os.path.realpath(os.path.join(root, line)) for line in lines)


@functools.lru_cache(maxsize=32)
def _resolution(root: str, path: str | None) -> tuple[str, tuple[str, ...]]:
    entries = _absolute_entries(path)
    roots = tuple(dict.fromkeys((root, *discovered_roots(root))))
    found = _pick(entries, roots)
    confirmed = _confirmed_roots(found, root, _outside(entries, roots))
    wider = tuple(dict.fromkeys(roots + confirmed))
    if wider != roots:
        return _pick(entries, wider), wider
    return found, roots


def _resolve(repo_root: str | None, path: str | None = None) -> tuple[str, tuple[str, ...]]:
    current = os.environ.get("PATH", os.defpath) if path is None else path
    return _resolution(os.path.realpath(repo_root), current)


def safe_search_path(repo_root: str | None = None, path: str | None = None) -> str:
    """The search path without the entries that make the current directory
    a search location and without any entry inside the scanned repository's
    working tree or git directories, by identity."""
    entries = _absolute_entries(path)
    if not repo_root:
        return os.pathsep.join(entries)
    try:
        roots = _resolve(repo_root, path)[1]
    except UnsafeGit:
        roots = tuple(dict.fromkeys((os.path.realpath(repo_root), *discovered_roots(repo_root))))
    return _outside(entries, roots)


def git_executable(repo_root: str | None) -> str:
    """Absolute path of the git to run on ``repo_root``."""
    if not repo_root:
        return _pick(_absolute_entries(None), ())
    return _resolve(repo_root)[0]


def child_environment(repo_root: str | None = None) -> dict[str, str]:
    """The whole environment of the git child; nothing else is passed."""
    return base_environment(safe_search_path(repo_root))
