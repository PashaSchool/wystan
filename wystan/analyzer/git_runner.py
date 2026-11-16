"""Run git on an untrusted clone without letting the clone choose the program.

Every git call of the engine goes through :func:`run_git`. Ported from
``wystan/index/git_runner.py`` (branch ``rebuild/p1-symbol-index``); the
public names are the same so the index can import this module instead.

Which git runs, and the child's environment, are decided in
``git_resolution`` (only the scanned repository's whole working tree is
untrusted; the current directory is not).

The child runs with a fixed minimal environment: no ``GIT_*`` variable of
the caller reaches it, the user's and the system's configuration are not
read, and everything in the clone's own configuration that runs a program
(hooks, the fsmonitor, pagers, external diff and textconv drivers, clean
and smudge filters, transports) is switched off on the command line. Only
an allowlist of built-in subcommands runs (git never lets an alias shadow a
built-in), each with a timeout and an output cap. Nothing in the allowlist
checks out or writes the scanned clone: file contents at a commit are read
as raw blobs (``cat-file --batch`` applies no filter or conversion).

Nothing derived from the clone is spliced into a ``-c`` argument: the
clean/smudge filters a clone defines are emptied through
``GIT_CONFIG_COUNT`` (key and value passed apart), and a driver name that is
not a plain token makes the command refuse instead of run.
"""

from __future__ import annotations

import functools
import logging
import os
import re
import tempfile
from typing import BinaryIO, Callable, TypeVar

from wystan.analyzer.git_arguments import FORMS, refusal
from wystan.analyzer.git_index import index_refusal
from wystan.analyzer.git_process import GitError, GitFailed, GitResult, GitTimeout, run_bounded, run_streaming
from wystan.analyzer.git_resolution import (
    SAFE_OPTIONS,
    UnsafeGit,
    child_environment,
    git_executable,
    ceiling_environment,
    safe_search_path,
)
from wystan.analyzer.git_user_config import user_excludes_file

__all__ = [
    "ALLOWED_SUBCOMMANDS", "DEFAULT_MAX_OUTPUT_BYTES", "DEFAULT_TIMEOUT_SEC", "GitAnswerUnavailable",
    "GitError", "GitFailed", "GitResult", "SAFE_OPTIONS", "UnsafeArgument",
    "UnsafeGit", "child_environment", "git_command", "git_executable",
    "object_name", "revision", "run_git", "safe_search_path",
]

#: The built-in subcommands the engine runs, and nothing else.
ALLOWED_SUBCOMMANDS = frozenset(FORMS)
#: Diff-producing commands never run an external diff or textconv driver
#: and show a submodule only as a commit pointer; the two that look at the
#: working tree (diff-index, status) never look inside a submodule at all
#: (its own configuration and filters would apply there; the engine reads a
#: submodule's HEAD as a file instead, see scan_result_cache). Forced here,
#: so no call site can forget them. Tree-to-tree diffs (diff-tree, log)
#: keep submodule pointer changes, as dev's `git diff A B` did. Porcelain
#: `git diff` is not allowed: it refreshes the clone's index.
_FORCED_FLAGS = {
    "diff-index": ("--no-ext-diff", "--no-textconv", "--submodule=short", "--ignore-submodules=all"),
    "diff-tree": ("--no-ext-diff", "--no-textconv", "--submodule=short"),
    "log": ("--no-ext-diff", "--no-textconv", "--submodule=short"),
    "status": ("--ignore-submodules=all",),
}
#: Commands that hash working-tree files, where git runs the clean filters
#: the clone's configuration defines.
_FILTERING_SUBCOMMANDS = frozenset({"diff-index", "status"})
#: The only commands that read the clone's index; every other one runs
#: with an index path that does not exist (see :func:`_no_index`).
_READS_INDEX = frozenset({"diff-index", "ls-files", "status"})
#: Commands whose output lists untracked files.
_LISTS_UNTRACKED = frozenset({"status"})
_FILTER_KEYS = ("clean", "smudge", "process")
#: A filter driver name the engine will neutralise; anything else refuses.
_PLAIN_DRIVER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
#: ``GIT_CONFIG_COUNT`` (configuration through the environment) exists from
#: git 2.31; an older git cannot have its filters emptied and refuses.
_ENV_CONFIG_SINCE = (2, 31)
_VERSION = re.compile(r"git version (\d+)\.(\d+)")

#: Longest a git call may run; a repository that needs longer is treated as
#: a failed call (every caller already has a fallback for that).
DEFAULT_TIMEOUT_SEC = 120.0
#: Largest stdout accepted; the largest corpus output measured is far below
#: (see .claude/lab/experiments/hardened-git-calls.md).
DEFAULT_MAX_OUTPUT_BYTES = 512 * 1024 * 1024
_CONFIG_TIMEOUT_SEC = 10.0

logger = logging.getLogger(__name__)
T = TypeVar("T")

_HEX_NAME = re.compile(r"[0-9a-fA-F]{4,64}")
_FORBIDDEN_IN_REVISION = ("\0", "\n", "\r")


class GitAnswerUnavailable(GitError):
    """A git answer the caller needs could not be read (refused or failed).
    Never the same as an empty answer: a caller must not read it as "no
    files" or "nothing changed"."""


class UnsafeArgument(GitError, ValueError):
    """A repository-controlled string would be read by git as an option."""


def unavailable_reason(exc: GitAnswerUnavailable) -> str:
    """Why an answer was unavailable, for the scan's record: ``timeout``,
    ``refused`` (the runner would not run it) or ``failed``."""
    cause = exc.__cause__
    if isinstance(cause, GitTimeout):
        return "timeout"
    if isinstance(cause, (UnsafeArgument, UnsafeGit)):
        return "refused"
    return "failed"


def git_command(repo_root: str, *args: str) -> list[str]:
    """``argv`` of a git command on ``repo_root``, ``argv[0]`` absolute.
    ``safe.directory`` names exactly the path the caller passed (command-line
    scope is honoured for it), never a repository found above it: the root
    the user named scans even when another user owns it; an enclosing
    repository the user did not name keeps git's own ownership check."""
    trusted = os.path.realpath(repo_root)
    return [
        git_executable(repo_root), *SAFE_OPTIONS, "-c", f"safe.directory={trusted}",
        "-C", repo_root, *args,
    ]


def object_name(value: str) -> str:
    """``value`` if it is a (possibly abbreviated) hexadecimal object name."""
    if not isinstance(value, str) or not _HEX_NAME.fullmatch(value):
        raise UnsafeArgument(f"not an object name: {value!r}")
    return value


def revision(value: str) -> str:
    """``value`` if git cannot read it as an option (no leading dash, no
    line break or NUL); a ref name never starts with a dash."""
    if not isinstance(value, str) or not value or value.startswith("-"):
        raise UnsafeArgument(f"refusing revision {value!r}")
    if any(ch in value for ch in _FORBIDDEN_IN_REVISION):
        raise UnsafeArgument(f"refusing revision {value!r}")
    return value


def _check_subcommand(args: tuple[str, ...]) -> str:
    """``args[0]`` if ``args`` is one of the engine's command forms
    (``git_arguments.FORMS``); anything else, e.g. ``log --output=F``, is
    refused before git starts."""
    if not args or args[0] not in ALLOWED_SUBCOMMANDS:
        raise UnsafeArgument(f"git subcommand not allowed: {args[:1]!r}")
    why = refusal(args[0], args[1:])
    if why:
        raise UnsafeArgument(f"git {args[0]}: {why}")
    return args[0]


@functools.lru_cache(maxsize=8)
def _git_version(executable: str) -> tuple[int, int]:
    found = _VERSION.search(run_bounded([executable, "version"], {}, _CONFIG_TIMEOUT_SEC, 1 << 10).text)
    return (int(found.group(1)), int(found.group(2))) if found else (0, 0)


#: ``git config --get-regexp`` exit codes that are answers: found, none.
_CONFIG_LISTED = (0, 1)


def _defined_filter_drivers(repo_root: str) -> list[str]:
    """Filter driver names the clone's configuration (with its includes, in
    this working tree's own context) defines, sorted."""
    listing = run_bounded(
        git_command(repo_root, "config", "--null", "--name-only", "--get-regexp", r"^filter\."),
        child_environment(repo_root), _CONFIG_TIMEOUT_SEC, DEFAULT_MAX_OUTPUT_BYTES,
    )
    # 0: drivers listed, 1: none defined. Anything else (an unreadable
    # config) is not "no filters": the read that needed them is refused.
    if listing.returncode not in _CONFIG_LISTED:
        raise UnsafeArgument(f"cannot list the clone's filter drivers (git config exited {listing.returncode})")
    return sorted({
        name[len("filter."):name.rindex(".")]
        for name in listing.text.split("\0")
        if name.count(".") >= 2
    })


def filter_environment(repo_root: str) -> dict[str, str]:
    """``GIT_CONFIG_*`` entries emptying every clean/smudge/process filter
    the clone defines. Refuses (``UnsafeArgument``) a driver name that is not
    a plain token, or a git too old to take configuration this way."""
    drivers = _defined_filter_drivers(repo_root)
    if not drivers:
        return {}
    odd = [d for d in drivers if not _PLAIN_DRIVER.fullmatch(d)]
    if odd or _git_version(git_executable(repo_root)) < _ENV_CONFIG_SINCE:
        logger.warning("git: refusing a working-tree read of %s (filter drivers %r)", repo_root, drivers)
        raise UnsafeArgument(f"cannot neutralise filter drivers {drivers!r}")
    entries = [(f"filter.{d}.{key}", "") for d in drivers for key in _FILTER_KEYS]
    entries += [(f"filter.{d}.required", "false") for d in drivers]
    env = {"GIT_CONFIG_COUNT": str(len(entries))}
    for index, (key, value) in enumerate(entries):
        env[f"GIT_CONFIG_KEY_{index}"] = key
        env[f"GIT_CONFIG_VALUE_{index}"] = value
    return env


def _user_options(subcommand: str) -> tuple[str, ...]:
    """The one piece of the user's own configuration the engine honours:
    their global ignore file, for the command that lists untracked files."""
    excludes = user_excludes_file() if subcommand in _LISTS_UNTRACKED else None
    return ("-c", f"core.excludesFile={excludes}") if excludes else ()


@functools.lru_cache(maxsize=1)
def _no_index() -> str:
    """An index path inside a private 0700 directory, never created: git
    reads it as an empty index and writes nothing for a read command."""
    return os.path.join(tempfile.mkdtemp(prefix="wystan-no-index-"), "index")


def _prepared(root: str, args: tuple[str, ...], stay_inside: bool) -> tuple[str, list[str], dict[str, str]]:
    """(subcommand, argv, environment) of an allowed command on ``root``."""
    subcommand = _check_subcommand(args)
    if subcommand in _READS_INDEX:
        why = index_refusal(root)
        if why:
            raise UnsafeArgument(f"the clone's index is not read: {why}")
    env = child_environment(root)
    if subcommand not in _READS_INDEX:
        # Reading an index can write the clone (a split index's shared file
        # is re-dated, a sparse index expanded into objects); a command that
        # needs no index gets none of the clone's.
        env["GIT_INDEX_FILE"] = _no_index()
    # ``stay_inside``: this path only, never an enclosing repository.
    env.update(ceiling_environment(root, stay_inside))
    if subcommand in _FILTERING_SUBCOMMANDS:
        env.update(filter_environment(root))
    argv = git_command(root, *_user_options(subcommand), subcommand, *_FORCED_FLAGS.get(subcommand, ()), *args[1:])
    return subcommand, argv, env


def stream_git(
    repo_root: str | os.PathLike[str], *args: str, consume: Callable[[BinaryIO], T],
    stdin: bytes | None = None, timeout: float = DEFAULT_TIMEOUT_SEC,
) -> T:
    """Like :func:`run_git`, but stdout goes to ``consume`` as a stream
    (for output too large to hold, e.g. blob contents)."""
    _subcommand, argv, env = _prepared(os.fspath(repo_root), args, False)
    return run_streaming(argv, env, timeout, stdin, consume)


def run_git(
    repo_root: str | os.PathLike[str],
    *args: str,
    timeout: float = DEFAULT_TIMEOUT_SEC,
    max_output: int = DEFAULT_MAX_OUTPUT_BYTES,
    check: bool = True,
    stdin: bytes | None = None,
    stay_inside: bool = False,
) -> GitResult:
    """Run ``git <args>`` on ``repo_root`` through the hardened runner.
    Raises :class:`GitError` (``GitFailed`` for a non-zero exit when
    ``check``); ``args[0]`` must be an allowed subcommand."""
    subcommand, argv, env = _prepared(os.fspath(repo_root), args, stay_inside)
    result = run_bounded(argv, env, timeout, max_output, stdin)
    if check and result.returncode != 0:
        raise GitFailed(subcommand, result)
    return result
