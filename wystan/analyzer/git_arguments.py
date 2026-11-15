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

#: subcommand -> (allowed options, most positional arguments before ``--``).
#: ``None`` means any number. Options ending in ``=`` are prefixes.
FORMS: dict[str, tuple[frozenset[str], int | None]] = {
    "cat-file": (frozenset({"--batch", "--batch-check"}), 0),
    "config": (frozenset({"--get", "--get-regexp", "--null", "--name-only"}), 1),
    "diff": (frozenset({"--name-only", "--numstat", "--no-renames", "--raw", "-z"}), 2),
    "diff-tree": (frozenset({"--numstat", "--no-renames", "--root", "--raw", "-r", "--abbrev=",
                             "--full-index", "-M", "-z", "--no-color", "--name-only"}), 2),
    "log": (frozenset({"--max-count=", "--since=", "--until=", "--pretty=", "--name-only", "-z",
                       "--no-renames", "--first-parent"}), None),
    "ls-files": (frozenset({"-z"}), 0),
    "ls-tree": (frozenset({"-r", "-t", "-z", "--full-tree", "--name-only"}), 1),
    "rev-list": (frozenset({"--count", "--since="}), None),
    "rev-parse": (frozenset({"--show-cdup", "--absolute-git-dir", "--verify", "--quiet",
                             "--is-inside-work-tree", "--show-toplevel", "--git-common-dir",
                             "--is-bare-repository", "--is-shallow-repository"}), None),
    "status": (frozenset({"--porcelain=v1", "--untracked-files=all", "-z"}), 0),
    "symbolic-ref": (frozenset({"--quiet"}), 1),
}
#: The one ref ``symbolic-ref`` may read (a second argument would write it).
_SYMBOLIC_REF_TARGET = "HEAD"
#: Actions ``config`` and ``cat-file`` must name (each subcommand writes or
#: changes mode without one).
REQUIRED_ACTIONS = {
    "cat-file": frozenset({"--batch", "--batch-check"}),
    "config": frozenset({"--get", "--get-regexp"}),
}


def _option_allowed(option: str, allowed: frozenset[str]) -> bool:
    if option in allowed:
        return True
    head, sep, _value = option.partition("=")
    return bool(sep) and f"{head}=" in allowed


def refusal(subcommand: str, args: tuple[str, ...]) -> str | None:
    """Why ``git <subcommand> <args>`` is not an engine form, or ``None``."""
    if subcommand not in FORMS:
        return "subcommand not allowed"
    allowed, most_positional = FORMS[subcommand]
    positional: list[str] = []
    for arg in args:
        if arg == "--":
            break
        if arg.startswith("-"):
            if not _option_allowed(arg, allowed):
                return f"option not allowed: {arg!r}"
        else:
            positional.append(arg)
    if most_positional is not None and len(positional) > most_positional:
        return f"too many arguments: {positional!r}"
    required = REQUIRED_ACTIONS.get(subcommand)
    if required is not None and not required.intersection(args):
        return "a read action is required"
    if subcommand == "symbolic-ref" and positional != [_SYMBOLIC_REF_TARGET]:
        return "only `symbolic-ref HEAD` is read"
    return None
