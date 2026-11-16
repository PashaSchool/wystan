"""The exact git command forms the engine may run.

An allowlist, not a refusal list: every allowed subcommand accepts options
that write files (``log --output=F``, ``diff --output=F``), re-enable what
the runner switched off (``--ext-diff``, ``--textconv``) or change state
(``symbolic-ref HEAD <ref>``, ``config <key> <value>``), and git adds new
ones over time; a refusal list would have to know them all. The engine's
own forms are few and fixed, so each subcommand lists the options it may
take (exact, or a prefix ending in ``=``) and how many positional
arguments; anything else is refused. Positional arguments are revisions or
names the callers validate (``git_runner.revision``/``object_name``);
everything after ``--`` is a path and is data.
"""

from __future__ import annotations

from wystan.analyzer.git_formats import PRETTY_ARGUMENTS

#: subcommand -> (allowed options, most positional arguments before ``--``,
#: whether paths may follow ``--``). Options ending in ``=`` are prefixes.
#: Positionals are revisions or config names the callers validate
#: (``git_runner.revision``/``object_name``); only log and diff-tree take
#: paths, and for every other subcommand a ``--`` is refused, so nothing
#: after it can reach git as an argument (``symbolic-ref HEAD -- <ref>``
#: wrote HEAD; symbolic-ref is no longer allowed at all).
FORMS: dict[str, tuple[frozenset[str], int, bool]] = {
    "cat-file": (frozenset({"--batch", "--batch-check"}), 0, False),
    "config": (frozenset({"--get", "--get-regexp", "--null", "--name-only"}), 1, False),
    "diff-index": (frozenset({"-p", "-M"}), 1, False),
    "diff-tree": (frozenset({"--numstat", "--no-renames", "--root", "--raw", "-r", "--abbrev=",
                             "--full-index", "-M", "-z", "--no-color", "--name-only"}), 2, True),
    "log": (frozenset({"--max-count=", "--since=", "--until=", "--name-only", "--name-status",
                       "-z", "--no-renames", "--first-parent"}), 1, True),
    "ls-files": (frozenset({"-z", "-s"}), 0, False),
    "ls-tree": (frozenset({"-r", "-t", "-z", "--full-tree", "--name-only"}), 1, False),
    "rev-list": (frozenset({"--count", "--since=", "--objects", "--no-walk", "--missing="}), 1, False),
    "rev-parse": (frozenset({"--show-cdup", "--absolute-git-dir", "--verify", "--quiet",
                             "--is-inside-work-tree", "--show-toplevel", "--git-common-dir",
                             "--is-bare-repository", "--is-shallow-repository", "--symbolic-full-name"}), 1, False),
    "status": (frozenset({"--porcelain=v1", "--untracked-files=all", "-z"}), 0, False),
}
#: Actions ``config`` and ``cat-file`` must name (each subcommand writes or
#: changes mode without one).
REQUIRED_ACTIONS = {
    "cat-file": frozenset({"--batch", "--batch-check"}),
    "config": frozenset({"--get", "--get-regexp"}),
}
_SEPARATOR = "--"
_PRETTY = "--pretty="


def _option_allowed(option: str, allowed: frozenset[str]) -> bool:
    if option.startswith(_PRETTY):
        # Only the engine's own formats (git_formats): a free format could
        # ask for %G? (runs gpg) or another executing placeholder.
        return option in PRETTY_ARGUMENTS
    if option in allowed:
        return True
    head, sep, _value = option.partition("=")
    return bool(sep) and f"{head}=" in allowed


def _split(args: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...] | None]:
    if _SEPARATOR not in args:
        return args, None
    index = args.index(_SEPARATOR)
    return args[:index], args[index + 1:]


def refusal(subcommand: str, args: tuple[str, ...]) -> str | None:
    """Why ``git <subcommand> <args>`` is not an engine form, or ``None``."""
    if subcommand not in FORMS:
        return "subcommand not allowed"
    allowed, most_positional, takes_paths = FORMS[subcommand]
    head, paths = _split(args)
    if paths is not None and not takes_paths:
        return f"`git {subcommand}` takes no paths: nothing may follow `--`"
    positional = [arg for arg in head if not arg.startswith("-")]
    for arg in head:
        if arg.startswith("-") and not _option_allowed(arg, allowed):
            return f"option not allowed: {arg!r}"
    if len(positional) > most_positional:
        return f"too many arguments: {positional!r}"
    if any(not arg for arg in positional):
        return "an empty argument"
    required = REQUIRED_ACTIONS.get(subcommand)
    if required is not None and not required.intersection(head):
        return "a read action is required"
    return None
