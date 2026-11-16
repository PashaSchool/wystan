"""File watcher + debounced refresh loop.

Uses the watchdog library to observe a repo for file changes and runs
the incremental refresh pipeline after a configurable debounce window
(default 30 seconds of silence).

Ignores:
  - .git/, node_modules/, __pycache__/, .venv/, dist/, build/
  - Any path matching a .gitignore-style excluded pattern
  - Binary files (not .py/.ts/.js/etc)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import signal
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

# Imported when the module loads, not when the watcher runs out of
# descriptors: an import then needs a descriptor to open its file.
from wystan.analyzer.descriptor_limit import EXIT_OUT_OF_DESCRIPTORS, out_of_descriptors_message
from wystan.analyzer.repo_held_dirs import release_idle
from wystan.analyzer.repo_open import DescriptorsExhausted

logger = logging.getLogger(__name__)

_DEFAULT_DEBOUNCE_SECONDS = 30.0
_DEFAULT_MAP_DIR = Path.home() / ".wystan"
_PID_DIR = Path.home() / ".wystan" / "watchers"
#: What the failure file says when even the message could not be built.
_FALLBACK_MESSAGE = "wystan: the watcher ran out of file descriptors and stopped"

_IGNORED_DIR_NAMES = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".turbo", ".cache", ".pytest_cache",
    ".mypy_cache", "target", "vendor",
}

_INTERESTING_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".go", ".rs", ".rb", ".java", ".kt", ".swift",
    ".c", ".h", ".cpp", ".hpp", ".cc",
}


@dataclass
class WatcherStatus:
    running: bool
    pid: int | None = None
    repo_path: str | None = None
    started_at: float | None = None


def _slug(repo_path: str) -> str:
    return hashlib.sha256(str(Path(repo_path).resolve()).encode()).hexdigest()[:12]


def _pid_file(repo_path: str) -> Path:
    _PID_DIR.mkdir(parents=True, exist_ok=True)
    return _PID_DIR / f"{_slug(repo_path)}.pid"


def _write_pid(repo_path: str, pid: int) -> None:
    _pid_file(repo_path).write_text(json.dumps({
        "pid": pid,
        "repo_path": str(Path(repo_path).resolve()),
        "started_at": time.time(),
    }))


def _read_pid(repo_path: str) -> dict | None:
    path = _pid_file(repo_path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _clear_pid(repo_path: str) -> None:
    path = _pid_file(repo_path)
    try:
        path.unlink()
    except OSError:
        pass


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError, OSError):
        return False
    return True


def watcher_status(repo_path: str) -> WatcherStatus:
    info = _read_pid(repo_path)
    if not info:
        return WatcherStatus(running=False)
    pid = info.get("pid")
    if not pid or not _pid_alive(pid):
        _clear_pid(repo_path)
        return WatcherStatus(running=False)
    return WatcherStatus(
        running=True,
        pid=pid,
        repo_path=info.get("repo_path"),
        started_at=info.get("started_at"),
    )


def stop_daemon(repo_path: str) -> bool:
    """Send SIGTERM to the daemon for this repo. Returns True if stopped."""
    status = watcher_status(repo_path)
    if not status.running or not status.pid:
        return False
    try:
        os.kill(status.pid, signal.SIGTERM)
    except OSError:
        return False
    _clear_pid(repo_path)
    return True


def start_daemon(
    repo_path: str,
    *,
    debounce_seconds: float = _DEFAULT_DEBOUNCE_SECONDS,
    map_path: str | None = None,
) -> int:
    """Fork a background watcher process. Returns the child PID.

    On Unix/macOS uses os.fork(). On Windows falls back to
    subprocess.Popen with detached flags.
    """
    existing = watcher_status(repo_path)
    if existing.running:
        raise RuntimeError(
            f"Watcher already running for {repo_path} (pid {existing.pid}). "
            f"Stop it first with `wystan watch-stop`."
        )

    if sys.platform == "win32":
        return _start_daemon_windows(repo_path, debounce_seconds, map_path)

    pid = os.fork()
    if pid > 0:
        # Parent — return child pid
        return pid

    # Child process. Everything up to ``os._exit`` is inside the ``try``: an
    # exception escaping here would return the child into the caller's code.
    status = 0
    try:
        # Detach from the terminal.
        os.setsid()
        null = os.open(os.devnull, os.O_RDWR)
        os.dup2(null, 0)
        os.dup2(null, 1)
        os.dup2(null, 2)
        exhausted = _watch(repo_path, debounce_seconds, map_path)
        if exhausted is not None:
            # The status first: the report needs descriptors the process may
            # not have, and whatever it does, the watcher stopped for want of them.
            status = EXIT_OUT_OF_DESCRIPTORS
            _report_out_of_descriptors(repo_path, exhausted)
    finally:
        _best_effort(_clear_pid, repo_path)
        os._exit(status)


def _failure_name(repo_path: str) -> Path:
    return _PID_DIR / f"{_slug(repo_path)}.error"


def _failure_file(repo_path: str) -> Path:
    """Where a detached watcher leaves the reason it stopped (its stderr is
    the null device)."""
    _PID_DIR.mkdir(parents=True, exist_ok=True)
    return _failure_name(repo_path)


def last_failure(repo_path: str) -> str | None:
    """The line the last watcher of this repository stopped with, or
    ``None`` when none stopped on a failure since one last started."""
    try:
        lines = _failure_name(repo_path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    return lines[-1] if lines else None


def _clear_failure(repo_path: str) -> None:
    """A watcher that started removes the reason an earlier one stopped, so
    ``watch-status`` never shows a stale one."""
    try:
        _failure_name(repo_path).unlink(missing_ok=True)
    except OSError:
        logger.warning("wystan watch: could not remove the failure file of %s", repo_path)


def _watch(repo_path: str, debounce_seconds: float, map_path: str | None) -> DescriptorsExhausted | None:
    """Run the detached watcher; the ``DescriptorsExhausted`` it stopped
    with, or ``None``. Nothing is reported here: reporting needs descriptors."""
    try:
        run_watcher(repo_path=repo_path, debounce_seconds=debounce_seconds, map_path=map_path, pid_tracking=True)
    except DescriptorsExhausted as exc:
        return exc
    return None


def _best_effort(action: Callable[..., object], *args: object) -> None:
    """Run ``action`` on the exit path of a process that may have no
    descriptor left: a failure is dropped (there is nowhere left to say it),
    so the exit status already set stands."""
    try:
        action(*args)
    except Exception:  # noqa: BLE001 - the exit path must not raise
        pass


def _write_failure(repo_path: str, message: str) -> None:
    _failure_file(repo_path).write_text(message + "\n", encoding="utf-8")


def _print_to_stderr(message: str) -> None:
    print(message, file=sys.stderr)


def _report_out_of_descriptors(repo_path: str, exc: DescriptorsExhausted) -> None:
    """Say, as far as the process still can, that the watcher ran out of
    file descriptors: the log, stderr and the failure file (shown by
    ``watch-status``). The reader's idle descriptors are closed first so the
    write has one; each report is best effort and none raises."""
    _best_effort(release_idle)
    message = _FALLBACK_MESSAGE
    try:
        message = out_of_descriptors_message(exc)
    except Exception:  # noqa: BLE001 - the exit path must not raise
        pass
    _best_effort(logger.error, message)
    _best_effort(_print_to_stderr, message)
    _best_effort(_write_failure, repo_path, message)


def _start_daemon_windows(
    repo_path: str,
    debounce_seconds: float,
    map_path: str | None,
) -> int:
    import subprocess
    cmd = [
        sys.executable, "-m", "wystan.watch",
        "--repo", repo_path,
        "--debounce", str(debounce_seconds),
    ]
    if map_path:
        cmd.extend(["--map", map_path])
    creationflags = 0x00000008  # DETACHED_PROCESS on Windows
    p = subprocess.Popen(cmd, creationflags=creationflags)
    _write_pid(repo_path, p.pid)
    return p.pid


def run_watcher(
    repo_path: str,
    *,
    debounce_seconds: float = _DEFAULT_DEBOUNCE_SECONDS,
    map_path: str | None = None,
    pid_tracking: bool = False,
    verbose: bool = False,
) -> None:
    """Foreground watcher loop. Ctrl-C to stop.

    Args:
        repo_path: Directory to watch.
        debounce_seconds: Wait this many seconds of silence before refresh.
        map_path: Explicit feature-map JSON. Defaults to latest in ~/.wystan/.
        pid_tracking: If True, write a pid file (used when forked as daemon).
        verbose: Print refresh events to stdout.
    """
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        raise RuntimeError(
            "watchdog not installed. Run: pip install 'wystan[watch]'"
        )

    resolved_map = _resolve_map_path(map_path, repo_path)
    if resolved_map is None:
        raise RuntimeError(
            f"No feature map found in {_DEFAULT_MAP_DIR}. "
            f"Run `wystan scan {repo_path}` first."
        )

    if pid_tracking:
        _write_pid(repo_path, os.getpid())

    state = _WatcherState(
        last_event_time=0.0,
        pending=False,
        lock=threading.Lock(),
    )

    class _Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            if event.is_directory:
                return
            src = getattr(event, "src_path", "")
            if not _interesting_path(src):
                return
            with state.lock:
                state.last_event_time = time.time()
                state.pending = True

    handler = _Handler()
    observer = Observer()
    observer.schedule(handler, repo_path, recursive=True)
    observer.start()
    # The watcher is running: an earlier watcher's failure no longer holds.
    _clear_failure(repo_path)

    if verbose:
        print(f"wystan watch: monitoring {repo_path} (debounce {debounce_seconds}s)")

    try:
        while True:
            time.sleep(1.0)
            with state.lock:
                if not state.pending:
                    continue
                if time.time() - state.last_event_time < debounce_seconds:
                    continue
                state.pending = False

            # Debounce window elapsed — run refresh
            _run_refresh(resolved_map, repo_path, verbose=verbose)
    except KeyboardInterrupt:
        if verbose:
            print("\nwystan watch: stopped")
    finally:
        observer.stop()
        observer.join()
        if pid_tracking:
            _clear_pid(repo_path)


def _interesting_path(path: str) -> bool:
    """Skip ignored directories and non-source files."""
    p = Path(path)
    for part in p.parts:
        if part in _IGNORED_DIR_NAMES:
            return False
    if p.suffix.lower() in _INTERESTING_EXTENSIONS:
        return True
    # Treat files without extension (like Makefile) as boring
    return False


def _resolve_map_path(explicit: str | None, repo_path: str) -> Path | None:
    if explicit:
        p = Path(explicit).expanduser()
        return p if p.exists() else None
    _DEFAULT_MAP_DIR.mkdir(parents=True, exist_ok=True)
    candidates = sorted(_DEFAULT_MAP_DIR.glob("feature-map-*.json"))
    return candidates[-1] if candidates else None


@dataclass
class _WatcherState:
    last_event_time: float
    pending: bool
    lock: threading.Lock


def _run_refresh(map_path: Path, repo_path: str, *, verbose: bool = False) -> None:
    try:
        from wystan.cache.refresh import refresh_feature_map
        from wystan.models.types import FeatureMap
        from wystan.output.writer import write_feature_map

        fm = FeatureMap.model_validate_json(map_path.read_text())
        result = refresh_feature_map(fm, repo_path)

        if not result.freshness_before.is_stale:
            return

        write_feature_map(result.updated_map, str(map_path))
        if verbose:
            ts = time.strftime("%H:%M:%S")
            print(
                f"[{ts}] refreshed: {result.freshness_before.commits_behind} commits, "
                f"{result.files_truly_modified} modified, {result.files_added} added"
            )
    except Exception as exc:
        logger.warning("watcher refresh failed: %s", exc)


# CLI entry point for Windows subprocess fallback
def _main_for_subprocess() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--debounce", type=float, default=_DEFAULT_DEBOUNCE_SECONDS)
    ap.add_argument("--map", default=None)
    args = ap.parse_args()
    sys.exit(_watch_or_report(args.repo, args.debounce, args.map))


if __name__ == "__main__":
    _main_for_subprocess()
