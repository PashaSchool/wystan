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
from typing import BinaryIO, Callable, TypeVar

T = TypeVar("T")

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
        """stdout as UTF-8, line endings untouched (what GitPython returned)."""
        return self.stdout.decode("utf-8", "replace")

    @property
    def universal_text(self) -> str:
        """stdout as ``subprocess.run(text=True)`` returned it: universal
        newlines, so ``\\r\\n`` and a lone ``\\r`` read as ``\\n`` (a commit
        message written on Windows keeps its byte-identical parse)."""
        return self.text.replace("\r\n", "\n").replace("\r", "\n")

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


def _feed(proc: subprocess.Popen[bytes], data: bytes) -> threading.Thread:
    """Write ``data`` to the child's stdin from a thread, so a child that
    prints while it reads cannot deadlock against us."""

    def _write() -> None:
        assert proc.stdin is not None
        try:
            proc.stdin.write(data)
        except (BrokenPipeError, OSError):
            pass  # the child exited or was killed; its exit status says why
        finally:
            proc.stdin.close()

    writer = threading.Thread(target=_write, daemon=True)
    writer.start()
    return writer


def run_bounded(
    argv: list[str], env: dict[str, str], timeout: float, max_output: int, stdin: bytes | None = None,
) -> GitResult:
    """Run ``argv`` with ``env`` only, ``stdin`` (if any) as its input; kill
    it at ``timeout`` seconds or past ``max_output`` bytes of stdout."""
    expired = threading.Event()
    with tempfile.TemporaryFile() as err_file:
        try:
            proc = subprocess.Popen(
                argv, stdin=subprocess.DEVNULL if stdin is None else subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=err_file, env=env,
            )
        except OSError as exc:
            raise GitError(f"cannot start git: {exc}") from exc
        writer = None if stdin is None else _feed(proc, stdin)

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
            if writer is not None:
                writer.join()
            if proc.stdout is not None:
                proc.stdout.close()
        err_file.seek(0)
        err = err_file.read(_STDERR_KEPT_BYTES)
    if expired.is_set():
        raise GitTimeout(f"git timed out after {timeout}s: {argv[-3:]!r}")
    if out is None:
        raise GitOutputTooLarge(f"git printed more than {max_output} bytes: {argv[-3:]!r}")
    return GitResult(returncode, out, err)


def run_streaming(
    argv: list[str], env: dict[str, str], timeout: float, stdin: bytes | None,
    consume: Callable[[BinaryIO], T],
) -> T:
    """Run ``argv`` and hand its stdout, as a stream, to ``consume`` (which
    bounds what it reads); kill the child at ``timeout`` seconds. A non-zero
    exit or an exception in ``consume`` fails the call."""
    expired = threading.Event()
    with tempfile.TemporaryFile() as err_file:
        try:
            proc = subprocess.Popen(
                argv, stdin=subprocess.DEVNULL if stdin is None else subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=err_file, env=env,
            )
        except OSError as exc:
            raise GitError(f"cannot start git: {exc}") from exc
        writer = None if stdin is None else _feed(proc, stdin)

        def _expire() -> None:
            expired.set()
            proc.kill()

        timer = threading.Timer(timeout, _expire)
        timer.start()
        try:
            assert proc.stdout is not None
            result = consume(proc.stdout)
        except BaseException:
            proc.kill()
            raise
        finally:
            timer.cancel()
            if writer is not None:
                writer.join()
            returncode = proc.wait()
            if proc.stdout is not None:
                proc.stdout.close()
        err_file.seek(0)
        err = err_file.read(_STDERR_KEPT_BYTES)
    if expired.is_set():
        raise GitTimeout(f"git timed out after {timeout}s: {argv[-3:]!r}")
    if returncode != 0:
        raise GitFailed("(streamed)", GitResult(returncode, b"", err))
    return result
