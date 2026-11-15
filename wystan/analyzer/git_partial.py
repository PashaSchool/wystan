"""History of a partial clone, read with what the object store holds.

The engine never fetches (the runner refuses every transport), so in a
blobless (``--filter=blob:none``) or treeless (``tree:0``) clone whatever
is not local is absent. The normal history read (``log --name-only`` with
rename detection) fails there as soon as rename detection needs a blob.
This reads the same history without it, then restores ``dev``'s answer
wherever the objects exist:

1. ``log --no-renames --name-status`` needs trees only. A commit's list
   can differ from the rename-detected one only when it has both an added
   and a deleted path (a rename pair); every other commit's list is
   already ``dev``'s.
2. Each commit with such a pair is re-read with ``diff-tree -M`` against
   its first parent (same pathspec): when its blobs are local this is
   exactly ``dev``'s list; when they are not, the no-rename list stays and
   the commit is counted.
3. When even trees are missing (treeless), commits are read without file
   lists.

The caller records what was degraded (``scan_meta.partial_clone``).
"""

from __future__ import annotations

from wystan.analyzer.git_history import FIELD_END, split_records
from wystan.analyzer.git_runner import GitError, object_name, run_git

#: ``%H %P %ct %an %B``, each NUL-terminated.
_FORMAT = "".join(f"{field}{FIELD_END}" for field in ("%H", "%P", "%ct", "%an", "%B"))
_FIELDS = 5
_ADDED, _DELETED = "A", "D"
HISTORY_COMPLETE = "complete"
HISTORY_RENAMES_PARTLY_UNDETECTED = "renames not detected where blobs are absent"
HISTORY_WITHOUT_FILES = "file lists unavailable (trees absent)"

Record = tuple[str, str, str, str, list[str]]  # sha, committed, author, body, names


def partial_clone_filter(root: str) -> str | None:
    """The clone's partial-clone filter (``blob:none``, ``tree:0``...), or
    ``None`` for a full clone. Read as data from the clone's config: a
    promisor remote's ``partialclonefilter`` (git 2.39 writes no
    ``extensions.partialClone`` for a plain filtered clone), else the
    extension alone."""
    try:
        listing = run_git(root, "config", "--null", "--get-regexp", r"^remote\..*\.(partialclonefilter|promisor)$",
                          check=False).text
        extension = run_git(root, "config", "--get", "extensions.partialclone", check=False).text.strip()
    except GitError:
        return None
    entries = [entry.split("\n", 1) for entry in listing.split("\0") if entry]
    filters = sorted(value for key, *rest in entries for value in rest if key.endswith(".partialclonefilter"))
    if filters:
        return filters[0]
    return "unknown" if extension or entries else None


def _log(root: str, max_commits: int, days: int, pathspec: list[str], names: list[str]) -> str | None:
    args = ["log", f"--max-count={int(max_commits)}", f"--since={int(days)}.days.ago",
            f"--pretty=format:{_FORMAT}", *names, "-z", *pathspec]
    result = run_git(root, *args, check=False)
    return result.universal_text if result.returncode == 0 else None


def _pairs(tokens: list[str]) -> list[tuple[str, str]]:
    return list(zip(tokens[0::2], tokens[1::2]))


def _renamed_list(root: str, sha: str, parent: str, pathspec: list[str]) -> list[str] | None:
    """``dev``'s rename-detected file list for one commit, or ``None`` when
    a blob it needs is not in the object store."""
    result = run_git(root, "diff-tree", "-r", "-M", "--name-only", "-z", object_name(parent), object_name(sha),
                     *pathspec, check=False)
    if result.returncode != 0:
        return None
    return [name for name in result.universal_text.split("\0") if name]


def _records_with_names(raw: str, root: str, pathspec: list[str]) -> tuple[list[Record], int]:
    records: list[Record] = []
    unresolved = 0
    for (sha, parents, committed, author, body), tokens in split_records(raw, _FIELDS, with_files=True):
        entries = _pairs(tokens)
        names = [path for _status, path in entries]
        statuses = {status for status, _path in entries}
        if {_ADDED, _DELETED} <= statuses and parents.split():
            renamed = _renamed_list(root, sha, parents.split()[0], pathspec)
            if renamed is None:
                unresolved += 1
            else:
                names = renamed
        records.append((sha, committed, author, body, names))
    return records, unresolved


def history_offline(root: str, max_commits: int, days: int, norm_src: str | None) -> tuple[list[Record], dict]:
    """The commit records of a partial clone and what could not be read."""
    pathspec = ["--", f":(top){norm_src}"] if norm_src is not None else []
    raw = _log(root, max_commits, days, pathspec, ["--no-renames", "--name-status"])
    if raw is not None:
        records, unresolved = _records_with_names(raw, root, pathspec)
        form = HISTORY_RENAMES_PARTLY_UNDETECTED if unresolved else HISTORY_COMPLETE
        return records, {"history": form, "commits_without_rename_detection": unresolved}
    raw = _log(root, max_commits, days, [], []) if norm_src is None else None
    if raw is None:
        return [], {"history": HISTORY_WITHOUT_FILES, "commits": 0}
    records = [(sha, committed, author, body, []) for (sha, _p, committed, author, body), _t
               in split_records(raw, _FIELDS)]
    return records, {"history": HISTORY_WITHOUT_FILES}
