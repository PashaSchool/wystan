"""Commit history read through the runner, for the slow fallback walk.

These reproduce what GitPython returned for ``repo.iter_commits`` and
``commit.stats.files``: the same commits in the same order, and the file
keys of ``git diff --numstat --no-renames`` against the first parent (or
``git diff-tree --root`` for a root commit), so the fallback answers what
it answered before without GitPython. Parents are read from the raw commit
object, as GitPython read them: ``%P`` follows shallow grafts, so a
shallow clone's boundary commit would otherwise look like a root. That
boundary commit (raw parents, none of them in the clone) is flagged; the
caller diffs it as git's shallow view does (as a root, which is what the
fast ``git log --name-only`` path reports for it) instead of failing on
the missing parent, as GitPython did.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from wystan.analyzer.git_formats import COMMIT_RECORD, FIELD_END  # FIELD_END: re-exported
from wystan.analyzer.git_runner import GitError, GitFailed, object_name, run_git

# Every field of a pretty format ends in NUL (``%x00``, git_formats) and
# ``-z`` puts a NUL between commits: no commit field can hold a NUL, so a
# message with any other control character (``\x1e``, ``\x1f``) is read whole.
_RECORD_FORMAT = COMMIT_RECORD
_RECORD_FIELDS = 5
#: Objects read per ``cat-file --batch`` call: bounds what one call holds in
#: memory (the runner's output cap applies per call).
OBJECTS_PER_BATCH = 2000
_PARENT_HEADER = b"parent "


@dataclass(frozen=True)
class CommitRecord:
    sha: str
    parents: tuple[str, ...]
    committed: int
    author: str
    message: str
    #: Raw parents exist but the shallow clone holds none of them.
    shallow_boundary: bool = False


def split_records(text: str, fields: int, with_files: bool = False) -> list[tuple[list[str], list[str]]]:
    """``git log -z --pretty=format:<fields, each ending %x00>`` output as
    ``(fields, files)`` per commit. With ``--name-only`` the file names
    follow the fields (the first after a newline), each NUL-terminated; an
    empty token ends the commit."""
    tokens = text.split("\0")
    records: list[tuple[list[str], list[str]]] = []
    index = 0
    while index + fields <= len(tokens):
        head = tokens[index:index + fields]
        index += fields
        files: list[str] = []
        while with_files and index < len(tokens) and tokens[index] != "":
            files.append(tokens[index].lstrip("\n") if not files else tokens[index])
            index += 1
        index += 1  # the empty token between commits
        if head[0].lstrip("\n"):
            records.append(([head[0].lstrip("\n"), *head[1:]], files))
    return records


def _parse_records(text: str) -> list[CommitRecord]:
    return [
        CommitRecord(sha, tuple(parents.split()), int(committed), author, message)
        for (sha, parents, committed, author, message), _files in split_records(text, _RECORD_FIELDS)
    ]


def _read_batch(root: str, oids: list[bytes], kind: bytes) -> list[bytes]:
    out = run_git(root, "cat-file", "--batch", stdin=b"".join(o + b"\n" for o in oids)).stdout
    contents, offset = [], 0
    for oid in oids:
        header_end = out.index(b"\n", offset)
        header = out[offset:header_end].split(b" ")
        if len(header) != 3 or header[0] != oid or header[1] != kind:
            raise GitError(f"cat-file did not return {kind.decode()} {oid.decode()}: {header!r}")
        start = header_end + 1
        size = int(header[2])
        contents.append(out[start:start + size])
        offset = start + size + 1  # the newline after each object
    return contents


def read_objects(root: str, oids: list[bytes], kind: bytes) -> list[bytes]:
    """Raw contents of ``oids`` (all of type ``kind``), in order; a missing
    object fails. ``cat-file --batch`` applies no filter or conversion."""
    contents: list[bytes] = []
    for start in range(0, len(oids), OBJECTS_PER_BATCH):
        contents += _read_batch(root, oids[start:start + OBJECTS_PER_BATCH], kind)
    return contents


def object_sizes(root: str, oids: list[bytes]) -> list[int | None]:
    """Size of each object, ``None`` when it is not in the object store
    (``cat-file --batch-check``; no content is read and, under the runner,
    nothing is fetched)."""
    sizes: list[int | None] = []
    for start in range(0, len(oids), OBJECTS_PER_BATCH):
        batch = oids[start:start + OBJECTS_PER_BATCH]
        try:
            out = run_git(root, "cat-file", "--batch-check", stdin=b"".join(o + b"\n" for o in batch)).stdout
        except GitFailed:
            # git < 2.45 tries to fetch an object a promisor clone lacks, and
            # the runner refuses: the batch holds an absent object. Ask one
            # by one, so the present ones keep their sizes.
            sizes += [_single_size(root, oid) for oid in batch]
            continue
        for line in out.splitlines():
            parts = line.split(b" ")
            sizes.append(int(parts[2]) if len(parts) == 3 and parts[1] != b"missing" else None)
    if len(sizes) != len(oids):
        raise GitError(f"cat-file --batch-check answered {len(sizes)} of {len(oids)} objects")
    return sizes


def _single_size(root: str, oid: bytes) -> int | None:
    try:
        line = run_git(root, "cat-file", "--batch-check", stdin=oid + b"\n").stdout.split(b" ")
    except GitFailed:
        return None
    return int(line[2]) if len(line) == 3 and line[1] != b"missing" else None


def absent_objects(root: str, sha: str) -> set[bytes]:
    """Objects of ``sha``'s tree the object store lacks, listed without
    fetching (``rev-list --objects --missing=print``)."""
    out = run_git(root, "rev-list", "--objects", "--no-walk", "--missing=print", object_name(sha)).stdout
    return {line[1:].split(b" ")[0] for line in out.splitlines() if line.startswith(b"?")}


def raw_parents(root: str, shas: list[str]) -> list[tuple[str, ...]]:
    """The ``parent`` headers of each commit object, grafts not applied."""
    objects = read_objects(root, [object_name(s).encode() for s in shas], b"commit")
    parents = []
    for raw in objects:
        headers = raw.split(b"\n\n", 1)[0].split(b"\n")
        parents.append(tuple(h[len(_PARENT_HEADER):].decode() for h in headers if h.startswith(_PARENT_HEADER)))
    return parents


def head_commits(root: str, max_count: int) -> list[CommitRecord]:
    """The newest ``max_count`` commits reachable from HEAD, newest first
    (``rev-list --max-count`` order, what ``iter_commits`` walked)."""
    out = run_git(
        root, "log", f"--max-count={int(max_count)}", f"--pretty=format:{_RECORD_FORMAT}", "-z", "HEAD", "--",
    )
    records = _parse_records(out.text)
    parents = raw_parents(root, [r.sha for r in records])
    # %P is the grafted view: empty where raw parents exist means the
    # commit sits on the shallow boundary.
    grafted = [bool(p) and not r.parents for r, p in zip(records, parents)]
    # A boundary commit whose first parent object is in the clone anyway is
    # diffed against it, as GitPython did; only a missing parent makes it a
    # root.
    first = [p[0].encode() for p, g in zip(parents, grafted) if g]
    present = iter(size is not None for size in object_sizes(root, first)) if first else iter(())
    boundary = [g and not next(present) for g in grafted]
    return [replace(r, parents=p, shallow_boundary=b) for r, p, b in zip(records, parents, boundary)]


def count_commits_since(root: str, since: str) -> int:
    """``git rev-list --count --since=<since> HEAD``."""
    return int(run_git(root, "rev-list", "--count", f"--since={since}", "HEAD").text.strip())


def numstat_file_keys(root: str, sha: str, parents: tuple[str, ...]) -> list[str]:
    """The keys of GitPython's ``commit.stats.files``, in its order: the
    numstat half of a ``--raw --numstat`` diff against the first parent."""
    if parents:
        # diff-tree prints what GitPython's `git diff <p0> <sha>` printed for
        # two commits, and never refreshes the clone's index.
        out = run_git(
            root, "diff-tree", "-r", "--numstat", "--no-renames", "--raw",
            object_name(parents[0]), object_name(sha), "--",
        ).text
        lines = out.splitlines()
    else:
        out = run_git(root, "diff-tree", "--numstat", "--no-renames", "--root", "--raw", object_name(sha), "--").text
        lines = out.splitlines()[1:]  # the first line names the commit
    keys: dict[str, None] = {}
    for _raw, numstat in zip(lines, lines[len(lines) // 2:]):
        _insertions, _deletions, filename = numstat.split("\t")
        keys[filename.strip()] = None
    return list(keys)
