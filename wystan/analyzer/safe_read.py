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
from pathlib import Path
from typing import Iterator

SYMLINK_CONTAINMENT_ENV = "WYSTAN_SYMLINK_CONTAINMENT"

__all__ = [
    "SYMLINK_CONTAINMENT_ENV",
    "symlink_containment_enabled",
    "path_within_repo",
    "safe_read_text",
    "iter_repo_files",
]


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
