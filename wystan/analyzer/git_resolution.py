"""Which git the runner may start for a scanned path, and its environment.

Only the scanned repository is untrusted, and all of it: a scan may name a
subdirectory (``--subpath``, a workspace), so search locations are excluded
for the whole working tree it belongs to (for exclusion, a wider root is the
safe direction). Resolution, cached per (path, ``PATH``, ``WYSTAN_GIT``):

1. Exclusion roots without running anything (``git_discovery``): the
   given path, every ancestor holding a ``.git`` entry of any kind, and
   every git directory those entries name. No git runs before this set is
   complete.
2. git: the absolute path in ``WYSTAN_GIT`` when set (the user's explicit
   choice; refused if relative, not an executable regular file, or inside
   the scanned path itself), else the first git on the caller's ``PATH``
   with empty, ``.`` and relative entries dropped (they make the current
   directory a search location) and every entry inside a root dropped, by
   file identity; a result inside a root is refused. When the exclusion
   leaves no git, the error names the excluded ancestor and ``WYSTAN_GIT``.
3. That git, with the runner's options and environment, confirms the roots
   (``rev-parse --show-toplevel --absolute-git-dir --git-common-dir``). A
   root outside the set (git's discovery wider than step 1) is not
   re-searched: it fails closed with ``UnsafeGit`` naming the root.

An absolute entry under the current directory is kept: a service whose cwd
is ``/`` must find ``/usr/bin/git``. On Windows
``NoDefaultCurrentDirectoryInExePath`` keeps the system from searching the
current directory, and the lookup here never adds it.
"""

from __future__ import annotations

import functools
import os

from wystan.analyzer.git_dir_discovery import one_value
from wystan.analyzer.git_discovery import exclusion_roots, read_pointer, topmost_repository_ancestor
from wystan.analyzer.git_process import GitError, run_bounded
from wystan.analyzer.path_identity import is_within

#: Settings that change what git prints, pinned to git's defaults (the
#: output of a machine with no configuration), whatever the user's or the
#: clone's config says. git 2.39 defaults, from git-config(1).
OUTPUT_PINS = (
    "-c", "core.quotepath=true",            # C-quoted names, as the parsers expect
    "-c", "core.abbrev=auto",               # `index a..b` length in diff-index -p (dirty hash)
    "-c", "core.precomposeunicode=true",    # macOS only; what `git init` writes there
    "-c", "core.autocrlf=false",            # working tree compared byte for byte
    "-c", "diff.renames=true",              # log/diff rename detection on (default)
    "-c", "diff.renameLimit=1000",          # default since git 2.33
    "-c", "diff.relative=false",
    "-c", f"diff.orderFile={os.devnull}",   # no reordering of file lists
    "-c", "diff.noprefix=false",
    "-c", "diff.mnemonicPrefix=false",
    "-c", "diff.algorithm=myers",
    "-c", "diff.context=3",
    "-c", "diff.interHunkContext=0",
    "-c", "diff.suppressBlankEmpty=false",
    "-c", "log.showRoot=true",              # the root commit lists its files
    "-c", "log.follow=false",
    # %an is the raw name either way; nothing reads a clone-chosen mailmap.
    "-c", "log.mailmap=false",
    "-c", f"mailmap.file={os.devnull}",
    "-c", "mailmap.blob=",
    "-c", "i18n.logOutputEncoding=UTF-8",   # messages decoded as UTF-8
    "-c", "i18n.commitEncoding=UTF-8",
)

#: Options that switch off what a clone's configuration could make git run,
#: and pin the few settings the engine's parsers depend on.
SAFE_OPTIONS = (
    "--no-pager",
    "-c", "core.fsmonitor=false",
    "-c", f"core.hooksPath={os.devnull}",
    "-c", "core.pager=cat",
    "-c", "core.untrackedCache=false",
    # Threaded loading takes the extensions from where the clone's EOIE says
    # and the entries from IEOT, not from walking the entries as the
    # engine's index inspection does (measured, git 2.39: an EOIE naming a
    # hidden extension is followed at index.threads=4, not at 1).
    "-c", "index.threads=1",
    "-c", f"core.attributesFile={os.devnull}",
    "-c", "diff.external=",
    # The engine never fetches; a promisor remote or a submodule must not
    # make a read command open a connection (or run core.sshCommand).
    "-c", "protocol.allow=never",
    "-c", "protocol.file.allow=never",
    # A submodule's own configuration (hooks, filters, diff drivers) must
    # never apply: no recursion, and no submodule diff or summary (both run
    # git inside the submodule).
    "-c", "submodule.recurse=false",
    "-c", "diff.submodule=short",
    "-c", "status.submoduleSummary=false",
    # A signature check runs gpg and prints into ``git log`` output; the
    # gpg programs point at a path that cannot run, in depth.
    "-c", "log.showSignature=false",
    "-c", f"gpg.program={os.devnull}",
    "-c", f"gpg.ssh.program={os.devnull}",
    "-c", f"gpg.x509.program={os.devnull}",
    # color.diff/color.status beat color.ui: all three, or a clone's
    # color.diff=always colours `git diff HEAD`.
    "-c", "color.ui=false",
    "-c", "color.diff=false",
    "-c", "color.status=false",
    "-c", "status.renames=true",            # porcelain v1 shows staged renames (default)
    *OUTPUT_PINS,
)

_WINDOWS = os.name == "nt"
#: The user's explicit git, for a machine where every git on PATH lies in
#: an excluded ancestor (a home directory that is itself a working tree).
EXPLICIT_GIT_ENV = "WYSTAN_GIT"
#: A protocol name git does not know: ``GIT_ALLOW_PROTOCOL`` then allows none.
_NO_PROTOCOL = "none"
_DISCOVERY_TIMEOUT_SEC = 10.0
_DISCOVERY_OUTPUT_BYTES = 1 << 16


class UnsafeGit(GitError):
    """No git outside the scanned repository was found."""


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
        # An empty or relative entry would make the lookup relative to the
        # current directory; an empty search path therefore means "no git".
        if not entry or not os.path.isabs(entry):
            continue
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
        # The engine never uses the network. A clone's own
        # ``protocol.<name>.allow=always`` beats ``protocol.allow=never``;
        # this list (git >= 2.6.1) beats every config and names no protocol.
        "GIT_ALLOW_PROTOCOL": _NO_PROTOCOL,
        # A promisor clone must not even try to fetch a missing object
        # (git >= 2.45; older gits fail the attempt on the line above).
        "GIT_NO_LAZY_FETCH": "1",
    }
    if _WINDOWS:
        env["NoDefaultCurrentDirectoryInExePath"] = "1"
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
    return env


def _pick(entries: list[str], roots: tuple[str, ...]) -> str:
    found = _which(_outside(entries, roots))
    if found is None:
        ancestor = topmost_repository_ancestor(roots[0]) if roots else None
        where = f" (every git on PATH lies in or under the excluded {ancestor})" if ancestor else ""
        raise UnsafeGit(f"git not found on the sanitised search path{where}; "
                        f"set {EXPLICIT_GIT_ENV} to the absolute path of a trusted git")
    if any(is_within(found, r) for r in roots):
        raise UnsafeGit(f"refusing git inside the scanned repository: {found}")
    return found


def _explicit_git(value: str, scanned: str) -> str:
    """``WYSTAN_GIT``: absolute, an executable regular file, not inside the
    scanned path (the user named it, so other excluded roots do not apply)."""
    if not os.path.isabs(value):
        raise UnsafeGit(f"{EXPLICIT_GIT_ENV} must be an absolute path: {value!r}")
    real = os.path.realpath(value)
    if not os.path.isfile(real) or not os.access(real, os.X_OK):
        raise UnsafeGit(f"{EXPLICIT_GIT_ENV} is not an executable file: {value!r}")
    if is_within(real, scanned):
        raise UnsafeGit(f"refusing {EXPLICIT_GIT_ENV} inside the scanned path: {real}")
    return real


#: What git is asked to confirm, one value per call (``one_value``).
_CONFIRMED_LOCATIONS = ("--show-toplevel", "--absolute-git-dir", "--git-common-dir")


def _probe(git: str, root: str, search_path: str, flag: str) -> str | None:
    """git's one-value answer, ``None`` when git says this is not a working
    tree; a malformed answer is refused (it would hide where git looks)."""
    # Trust only the path itself: a foreign-owned enclosing repository makes
    # the probe fail (then the file-system roots stand), never trusted.
    argv = [git, *SAFE_OPTIONS, "-c", f"safe.directory={root}", "-C", root, "rev-parse", flag]
    try:
        result = run_bounded(argv, base_environment(search_path), _DISCOVERY_TIMEOUT_SEC, _DISCOVERY_OUTPUT_BYTES)
    except GitError:
        return None
    if result.returncode != 0:
        return None
    value = one_value(result.stdout)
    if value is None:
        raise UnsafeGit(f"git's answer to rev-parse {flag} on {root} is not one line; refusing")
    return value


def _confirmed_roots(git: str, root: str, search_path: str) -> tuple[str, ...]:
    answers = [_probe(git, root, search_path, flag) for flag in _CONFIRMED_LOCATIONS]
    if None in answers:
        return ()  # not in a working tree: the given root stands
    return tuple(os.path.realpath(os.path.join(root, answer)) for answer in answers)


@functools.lru_cache(maxsize=32)
def _resolution(root: str, path: str, explicit: str) -> tuple[str, tuple[str, ...]]:
    """(git, exclusion roots). Discovery only excludes; it never grants trust."""
    entries = _absolute_entries(path)
    roots = exclusion_roots(root)
    found = _explicit_git(explicit, root) if explicit else _pick(entries, roots)
    confirmed = _confirmed_roots(found, root, _outside(entries, roots))
    for named in confirmed:
        if not any(is_within(named, r) for r in roots):
            raise UnsafeGit(f"git places {root} under {named}, outside the excluded locations; refusing")
    return found, roots


def _resolve(repo_root: str, path: str | None = None) -> tuple[str, tuple[str, ...]]:
    current = os.environ.get("PATH", os.defpath) if path is None else path
    return _resolution(os.path.realpath(repo_root), current, os.environ.get(EXPLICIT_GIT_ENV, ""))


def _is_git_dir(path: str) -> bool:
    return os.path.isfile(os.path.join(path, "HEAD")) and os.path.isdir(os.path.join(path, "objects"))


def is_repository_top(path: str) -> bool:
    """``path`` is a working-tree top (a ``.git`` directory that looks like
    a repository, or a ``gitdir:`` file) or a bare git directory. A bogus
    ``.git`` does not count: git walks past it, and so does discovery."""
    real = os.path.realpath(path)
    dot_git = os.path.join(real, ".git")
    if os.path.isdir(dot_git) and not os.path.islink(dot_git):
        return _is_git_dir(dot_git)
    pointer = read_pointer(dot_git, real)
    return bool(pointer and pointer.startswith("gitdir:")) or _is_git_dir(real)


def ceiling_environment(path: str, stay_inside: bool = False) -> dict[str, str]:
    """``GIT_CEILING_DIRECTORIES`` at ``path``'s parent when git must not
    adopt an enclosing repository: the path is itself a repository top (the
    root the user named) or the caller asked for this path only."""
    real = os.path.realpath(path)
    parent = os.path.dirname(real)
    if parent == real or os.pathsep in parent or not (stay_inside or is_repository_top(real)):
        return {}
    return {"GIT_CEILING_DIRECTORIES": parent}


def safe_search_path(repo_root: str, path: str | None = None) -> str:
    """The search path without the entries that make the current directory
    a search location and without any entry inside a location the scanned
    tree could own (see ``git_discovery``), by identity."""
    entries = _absolute_entries(path)
    return _outside(entries, exclusion_roots(os.path.realpath(_require_root(repo_root))))


def _require_root(repo_root: str | None) -> str:
    # git is only ever resolved for a scanned path: without one, none of the
    # exclusions apply and a git planted in the scanned tree could be picked.
    if not repo_root:
        raise UnsafeGit("git is only resolved for a scanned path")
    return repo_root


def git_executable(repo_root: str) -> str:
    """Absolute path of the git to run on ``repo_root``."""
    return _resolve(_require_root(repo_root))[0]


def child_environment(repo_root: str) -> dict[str, str]:
    """The whole environment of the git child; nothing else is passed."""
    env = base_environment(safe_search_path(repo_root))
    env.update(ceiling_environment(repo_root))
    return env

