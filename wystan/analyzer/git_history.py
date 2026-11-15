"""Commit history read through the runner, for the slow fallback walk.

These reproduce what GitPython returned for ``repo.iter_commits`` and
``commit.stats.files``: the same commits in the same order, and the file
keys of ``git diff --numstat --no-renames`` against the first parent (or
``git diff-tree --root`` for a root commit), so the fallback answers what
it answered before without GitPython. Parents are read from the raw commit
object, as GitPython read them: ``%P`` follows shallow grafts, so a
shallow clone's boundary commit would otherwise look like a root.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from wystan.analyzer.git_runner import GitError, object_name, run_git

# Field and record separators of the pretty format: ASCII unit and record
# separators never occur in commit data (same choice as ``_get_commits_fast``).
_FIELD = "\x1f"
_RECORD = "\x1e"
_RECORD_FORMAT = f"%H{_FIELD}%P{_FIELD}%ct{_FIELD}%an{_FIELD}%B{_RECORD}"
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


def _parse_records(text: str) -> list[CommitRecord]:
    records: list[CommitRecord] = []
    for raw in text.split(_RECORD):
        raw = raw.lstrip("\0\n")
        if not raw:
            continue
        parts = raw.split(_FIELD, _RECORD_FIELDS - 1)
        if len(parts) < _RECORD_FIELDS:
            continue
        sha, parents, committed, author, message = parts
        records.append(CommitRecord(sha, tuple(parents.split()), int(committed), author, message))
    return records


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
    return [replace(r, parents=p) for r, p in zip(records, parents)]


def count_commits_since(root: str, since: str) -> int:
    """``git rev-list --count --since=<since> HEAD``."""
    return int(run_git(root, "rev-list", "--count", f"--since={since}", "HEAD").text.strip())


def numstat_file_keys(root: str, sha: str, parents: tuple[str, ...]) -> list[str]:
    """The keys of GitPython's ``commit.stats.files``, in its order: the
    numstat half of a ``--raw --numstat`` diff against the first parent."""
    if parents:
        out = run_git(
            root, "diff", "--numstat", "--no-renames", "--raw",
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
