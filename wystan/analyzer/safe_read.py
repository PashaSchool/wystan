"""Symlink-containment guard for untrusted-repo reads (H2 hardening).

A scanned repository is UNTRUSTED input. Nothing stops a repo from
committing a symlink (git mode ``120000``) whose target escapes the
clone root — ``/etc/passwd``, ``/proc/self/environ`` (holds
``ANTHROPIC_API_KEY`` / ``WYSTAN_WORKER_TOKEN`` / ``DATABASE_URL``),
``../../.env``, ``~/.ssh/id_rsa``. Following such a symlink while
walking or reading a repo lifts worker secrets off disk and can feed
them to the LLM.

This module is the SINGLE containment predicate every pipeline read
routes through, so the check lives in exactly one place
(``scan_result_cache._hash_nongit_tree`` already skips symlinks
deliberately — this generalises that discipline to every read site).

Gate: env ``WYSTAN_SYMLINK_CONTAINMENT``, **default ON** (security —
OFF leaves the hole open). Explicit ``0`` / ``false`` / ``off`` / ``no``
/ ``""`` makes every helper here byte-identical to raw
``Path.read_text`` / ``rglob`` walking (kill-switch forever).

Output-neutrality contract: a symlink that fully resolves INSIDE
``repo_root`` is read exactly as before; only an ESCAPING symlink (or a
broken / looping one) is skipped. On a legitimate repo with no escaping
symlink, the file walk and every read are identical whether the guard
is on or off — which is what the byte-identical keyless A/B proves.
"""

from __future__ import annotations

import os
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

SYMLINK_CONTAINMENT_ENV = "WYSTAN_SYMLINK_CONTAINMENT"

__all__ = [
    "MAX_FILE_BYTES",
    "REFUSED_BINARY",
    "REFUSED_MISSING",
    "REFUSED_NOT_REGULAR",
    "REFUSED_OUTSIDE",
    "REFUSED_OVER_CAP",
    "SNIFF_BYTES",
    "SYMLINK_CONTAINMENT_ENV",
    "FileBytes",
    "iter_repo_files",
    "open_repo_file",
    "path_within_repo",
    "read_repo_bytes",
    "repo_root_of",
    "safe_read_text",
    "symlink_containment_enabled",
]

#: Largest file a counting reader opens. The largest tracked text file on
#: the ten corpus clones is 10.7 MB (a bundled script); six times that keeps
#: every file the map has ever counted and bounds what a crafted file costs.
MAX_FILE_BYTES = 64 * 1024 * 1024
#: Head inspected for a NUL byte before a file is read on (the line count's
#: binary sniff has always read this much).
SNIFF_BYTES = 8192
#: Why a bounded read returned no bytes.
REFUSED_MISSING = "missing_on_disk"
REFUSED_OUTSIDE = "symlink_outside_repo"
REFUSED_NOT_REGULAR = "not_regular_file"
REFUSED_OVER_CAP = "over_read_cap"
REFUSED_BINARY = "binary_content"
_READ_CHUNK = 1 << 20
_OPEN_FLAGS = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
_NO_FOLLOW = getattr(os, "O_NOFOLLOW", 0)


def symlink_containment_enabled() -> bool:
    """Default **ON**. Explicit ``0``/``false``/``off``/``no``/``""`` ⇒ every
    helper is a pure pass-through (byte-identical legacy behaviour;
    kill-switch). The truthy set mirrors the ``invariant_hooks`` convention;
    only the ``os.environ.get`` default is ``"1"`` (unset ≡ armed)."""
    return os.environ.get(SYMLINK_CONTAINMENT_ENV, "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def path_within_repo(path: os.PathLike[str] | str, repo_root: os.PathLike[str] | str) -> bool:
    """Return ``True`` when ``path`` is safe to read under the containment rule.

    - guard OFF → always ``True`` (byte-identical legacy behaviour);
    - ``path`` is **not** a symlink → ``True`` (a regular file is never a
      containment risk; no ``resolve`` cost on the hot path);
    - ``path`` is a symlink whose fully-resolved target is inside
      ``repo_root`` → ``True`` (internal symlinks are read as before, so
      legit repos with internal symlinks stay byte-identical);
    - ``path`` is a symlink that escapes ``repo_root``, or is broken /
      looping / unresolvable → ``False`` (skip; never read).

    The full symlink chain is resolved (``Path.resolve`` = ``realpath``),
    so a chain a→b→/etc/passwd is caught, and both sides are resolved so
    path-component symlinks in ``repo_root`` itself (``/var`` →
    ``/private/var`` on macOS) cancel out rather than cause false skips.
    """
    if not symlink_containment_enabled():
        return True
    p = Path(path)
    try:
        if not p.is_symlink():
            return True
    except OSError:
        # lstat failed (race, permission) — treat as unreadable, skip.
        return False
    try:
        root_resolved = Path(repo_root).resolve()
        target = p.resolve()
    except (OSError, RuntimeError, ValueError):
        # RuntimeError: symlink loop (Python 3.11 raises on resolve());
        # OSError: broken target; ValueError: malformed path → skip.
        return False
    try:
        return target.is_relative_to(root_resolved)
    except ValueError:
        return False


def safe_read_text(
    path: os.PathLike[str] | str,
    repo_root: os.PathLike[str] | str,
    *,
    encoding: str = "utf-8",
    errors: str = "strict",
    max_bytes: int | None = None,
) -> str | None:
    """Read text from ``path`` unless a symlink escapes ``repo_root``.

    Returns ``None`` when the path escapes containment (guard on), the read
    fails (``OSError``), or ``max_bytes`` is set and the file exceeds it.
    Otherwise mirrors ``Path.read_text(encoding=..., errors=...)`` exactly,
    so callers that previously did ``try: p.read_text(...); except OSError:
    continue`` keep byte-identical behaviour by treating ``None`` as skip.
    """
    p = Path(path)
    if not path_within_repo(p, repo_root):
        return None
    try:
        if max_bytes is not None and p.stat().st_size > max_bytes:
            return None
        return p.read_text(encoding=encoding, errors=errors)
    except OSError:
        return None


def iter_repo_files(root: os.PathLike[str] | str) -> Iterator[Path]:
    """Yield regular files under ``root`` (same ``rglob('*')`` walk as before)
    EXCEPT symlinks that escape ``root``.

    Mirrors the previous ``for p in root.rglob('*'): if p.is_file()`` loop
    when the guard is off or when no symlink escapes — the only files
    withheld are escaping symlinks, so legit repos walk identically.
    """
    root_p = Path(root)
    for p in root_p.rglob("*"):
        try:
            if not p.is_file():
                continue
        except OSError:
            continue
        if not path_within_repo(p, root_p):
            continue
        yield p


# ── Bounded reads of one file (line counts and samples) ─────────────────


@dataclass(frozen=True)
class FileBytes:
    """The bytes of a file, or why it was not read (``REFUSED_*``)."""

    data: bytes | None
    refused: str | None


def repo_root_of(abs_path: os.PathLike[str] | str, rel_path: str) -> Path:
    """The repository root ``abs_path`` was built from as ``root / rel_path``
    (callers that pass only those two). Falls back to the file's directory,
    the narrowest root, when the two do not line up."""
    text = str(abs_path).replace("\\", "/")
    rel = str(rel_path or "").replace("\\", "/").strip("/")
    if rel and text.endswith("/" + rel):
        return Path(text[: -len(rel) - 1] or "/")
    return Path(abs_path).parent


def _parent_inside(path: Path, repo_root: Path) -> bool:
    """A path reached through a symlinked directory is outside the repository
    even when the file itself is no symlink (git never tracks one; a
    directory walk can reach one)."""
    if not symlink_containment_enabled():
        return True
    try:
        return Path(os.path.realpath(path.parent)).is_relative_to(Path(os.path.realpath(repo_root)))
    except (OSError, ValueError):
        return False


def _target(path: Path, repo_root: Path) -> tuple[os.stat_result | None, str | None, bool]:
    """``(stat of what would be opened, refusal, is a symlink)``: ``lstat``
    first; a symlink is followed only when it stays inside the repository."""
    try:
        link = os.lstat(path)
    except OSError:
        return None, REFUSED_MISSING, False
    is_link = stat.S_ISLNK(link.st_mode)
    if not _parent_inside(path, repo_root) or (is_link and not path_within_repo(path, repo_root)):
        return None, REFUSED_OUTSIDE, is_link
    if not is_link:
        return link, None, False
    try:
        return os.stat(path), None, True
    except OSError:
        return None, REFUSED_OUTSIDE, True


@contextmanager
def open_repo_file(
    path: os.PathLike[str] | str, repo_root: os.PathLike[str] | str, *, max_bytes: int | None = None,
) -> Iterator[tuple[int | None, int, str | None]]:
    """Yield ``(fd, size, refusal)`` for a file of an untrusted repository:
    a descriptor only for a regular file inside the repository of at most
    ``max_bytes``, opened non-blocking (a FIFO swapped in never blocks) and
    without following a symlink that was not one at ``lstat`` time, checked
    again with ``fstat``. ``fd`` is ``None`` with the refusal otherwise."""
    p, root = Path(path), Path(repo_root)
    max_bytes = MAX_FILE_BYTES if max_bytes is None else max_bytes  # read at call time
    target, refused, is_link = _target(p, root)
    fd: int | None = None
    try:
        if refused is None and not stat.S_ISREG(target.st_mode):
            refused = REFUSED_NOT_REGULAR
        elif refused is None and target.st_size > max_bytes:
            refused = REFUSED_OVER_CAP
        if refused is None:
            try:
                fd = os.open(p, _OPEN_FLAGS | (0 if is_link else _NO_FOLLOW))
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    refused = REFUSED_NOT_REGULAR
            except OSError:
                refused = REFUSED_NOT_REGULAR
        yield (None if refused else fd), (target.st_size if target else 0), refused
    finally:
        if fd is not None:
            os.close(fd)


def _read_rest(fd: int, first: bytes, max_bytes: int) -> FileBytes:
    chunks, total = [first], len(first)
    while chunk := os.read(fd, min(_READ_CHUNK, max_bytes + 1 - total)):
        chunks.append(chunk)
        total += len(chunk)
        if total > max_bytes:  # the file grew past the cap after stat
            return FileBytes(None, REFUSED_OVER_CAP)
    return FileBytes(b"".join(chunks), None)


def read_repo_bytes(
    path: os.PathLike[str] | str, repo_root: os.PathLike[str] | str, *,
    max_bytes: int | None = None, stop_at_binary: bool = True,
) -> FileBytes:
    """All bytes of a regular file inside the repository, at most
    ``max_bytes`` (default ``MAX_FILE_BYTES``). With ``stop_at_binary`` a NUL byte in the first
    ``SNIFF_BYTES`` ends the read there (``REFUSED_BINARY``). Never raises."""
    cap = MAX_FILE_BYTES if max_bytes is None else max_bytes
    try:
        with open_repo_file(path, repo_root, max_bytes=cap) as (fd, _size, refused):
            if fd is None:
                return FileBytes(None, refused)
            head = os.read(fd, SNIFF_BYTES)
            if stop_at_binary and b"\x00" in head:
                return FileBytes(None, REFUSED_BINARY)
            return _read_rest(fd, head, cap)
    except OSError:
        return FileBytes(None, REFUSED_NOT_REGULAR)
