"""Run one git child with a deadline and a cap on what it may print.

``subprocess.run`` can time out but cannot bound memory: a repository can
make ``git log`` print without end. Here stdout is read in chunks and the
child is killed when the deadline passes or the output exceeds the cap;
stderr goes to an unnamed temporary file so the two pipes cannot deadlock.
"""

from __future__ import annotations

import subprocess
import tempfile
import threading
from dataclasses import dataclass

#: Bytes read from the child per call; large enough that a big ``git log``
#: costs few reads, small enough that the cap is overshot by little.
_READ_CHUNK_BYTES = 1 << 20
#: stderr kept in an error message; git's messages are short.
_STDERR_KEPT_BYTES = 4096


class GitError(RuntimeError):
    """A git call did not produce a usable result."""


class GitTimeout(GitError):
    """The child ran past its deadline and was killed."""


class GitOutputTooLarge(GitError):
    """The child printed more than the cap and was killed."""


@dataclass(frozen=True)
class GitResult:
    returncode: int
    stdout: bytes
    stderr: bytes

    @property
    def text(self) -> str:
        return self.stdout.decode("utf-8", "replace")

    @property
    def stderr_text(self) -> str:
        return self.stderr.decode("utf-8", "replace")


class GitFailed(GitError):
    """git exited with a non-zero status."""

    def __init__(self, subcommand: str, result: GitResult) -> None:
        self.returncode = result.returncode
        self.stderr = result.stderr_text.strip()
        super().__init__(f"git {subcommand} exited {result.returncode}: {self.stderr}")


def _read_capped(proc: subprocess.Popen[bytes], max_output: int) -> bytes | None:
    """All of stdout, or ``None`` once it exceeds ``max_output``."""
    chunks: list[bytes] = []
    size = 0
    assert proc.stdout is not None
    while True:
        chunk = proc.stdout.read(_READ_CHUNK_BYTES)
        if not chunk:
            return b"".join(chunks)
        size += len(chunk)
        if size > max_output:
            return None
        chunks.append(chunk)


def run_bounded(argv: list[str], env: dict[str, str], timeout: float, max_output: int) -> GitResult:
    """Run ``argv`` with ``env`` only; kill it at ``timeout`` seconds or
    past ``max_output`` bytes of stdout."""
    expired = threading.Event()
    with tempfile.TemporaryFile() as err_file:
        try:
            proc = subprocess.Popen(
                argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=err_file, env=env,
            )
        except OSError as exc:
            raise GitError(f"cannot start git: {exc}") from exc

        def _expire() -> None:
            expired.set()
            proc.kill()

        timer = threading.Timer(timeout, _expire)
        timer.start()
        try:
            out = _read_capped(proc, max_output)
            if out is None:
                proc.kill()
            returncode = proc.wait()
        finally:
            timer.cancel()
            if proc.stdout is not None:
                proc.stdout.close()
        err_file.seek(0)
        err = err_file.read(_STDERR_KEPT_BYTES)
    if expired.is_set():
        raise GitTimeout(f"git timed out after {timeout}s: {argv[-3:]!r}")
    if out is None:
        raise GitOutputTooLarge(f"git printed more than {max_output} bytes: {argv[-3:]!r}")
    return GitResult(returncode, out, err)
