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

from wystan.analyzer.git_arguments import FORMS, refusal
from wystan.analyzer.git_process import GitError, GitFailed, GitResult, run_bounded
from wystan.analyzer.git_resolution import (
    SAFE_OPTIONS,
    UnsafeGit,
    child_environment,
    git_executable,
    safe_search_path,
    trusted_directory,
)

__all__ = [
    "ALLOWED_SUBCOMMANDS", "DEFAULT_MAX_OUTPUT_BYTES", "DEFAULT_TIMEOUT_SEC",
    "GitError", "GitFailed", "GitResult", "SAFE_OPTIONS", "UnsafeArgument",
    "UnsafeGit", "child_environment", "git_command", "git_executable",
    "object_name", "revision", "run_git", "safe_search_path",
]

#: The built-in subcommands the engine runs, and nothing else.
ALLOWED_SUBCOMMANDS = frozenset(FORMS)
#: Diff-producing commands never run an external diff or textconv driver
#: and show a submodule only as a commit pointer; diff and status never look
#: inside a submodule at all (its own configuration and filters would apply
#: there). Forced here, so no call site can forget them. Consequence: a
#: `git diff` file list omits submodule pointer bumps (gitlinks, which the
#: engine never tracks as files); `log` and `diff-tree` keep them.
_FORCED_FLAGS = {
    "diff": ("--no-ext-diff", "--no-textconv", "--submodule=short", "--ignore-submodules=all"),
    "diff-tree": ("--no-ext-diff", "--no-textconv", "--submodule=short"),
    "log": ("--no-ext-diff", "--no-textconv", "--submodule=short"),
    "status": ("--ignore-submodules=all",),
}
#: Commands that hash working-tree files, where git runs the clean filters
#: the clone's configuration defines.
_FILTERING_SUBCOMMANDS = frozenset({"diff", "status"})
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

_HEX_NAME = re.compile(r"[0-9a-fA-F]{4,64}")
_FORBIDDEN_IN_REVISION = ("\0", "\n", "\r")


class UnsafeArgument(GitError, ValueError):
    """A repository-controlled string would be read by git as an option."""


def git_command(repo_root: str, *args: str) -> list[str]:
    """``argv`` of a git command on ``repo_root``, ``argv[0]`` absolute.
    ``safe.directory`` names this repository's top level only (command-line
    scope is honoured for it), so a clone owned by another user still scans,
    from its top or a subdirectory, without the user's global configuration."""
    trusted = trusted_directory(repo_root)
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


def _defined_filter_drivers(repo_root: str) -> list[str]:
    """Filter driver names the clone's configuration (with its includes, in
    this working tree's own context) defines, sorted."""
    listing = run_bounded(
        git_command(repo_root, "config", "--null", "--name-only", "--get-regexp", r"^filter\."),
        child_environment(repo_root), _CONFIG_TIMEOUT_SEC, DEFAULT_MAX_OUTPUT_BYTES,
    )
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


def run_git(
    repo_root: str | os.PathLike[str],
    *args: str,
    timeout: float = DEFAULT_TIMEOUT_SEC,
    max_output: int = DEFAULT_MAX_OUTPUT_BYTES,
    check: bool = True,
    stdin: bytes | None = None,
) -> GitResult:
    """Run ``git <args>`` on ``repo_root`` through the hardened runner.
    Raises :class:`GitError` (``GitFailed`` for a non-zero exit when
    ``check``); ``args[0]`` must be an allowed subcommand."""
    root = os.fspath(repo_root)
    subcommand = _check_subcommand(args)
    env = child_environment(root)
    if subcommand in _FILTERING_SUBCOMMANDS:
        env.update(filter_environment(root))
    argv = git_command(root, subcommand, *_FORCED_FLAGS.get(subcommand, ()), *args[1:])
    result = run_bounded(argv, env, timeout, max_output, stdin)
    if check and result.returncode != 0:
        raise GitFailed(subcommand, result)
    return result
