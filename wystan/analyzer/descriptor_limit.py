"""What a process that ran out of file descriptors tells its user.

The guarded reader raises ``repo_open.DescriptorsExhausted`` when a read
cannot get a descriptor even after releasing its own and waiting; the scan
must then fail, visibly. The CLI and the watch daemon end with
``EXIT_OUT_OF_DESCRIPTORS`` and ``out_of_descriptors_message``: what happened,
the limit in force, and how to raise it.
"""

from __future__ import annotations

__all__ = ["EXIT_OUT_OF_DESCRIPTORS", "out_of_descriptors_message", "soft_descriptor_limit"]

#: ``EX_TEMPFAIL`` (sysexits.h): a temporary failure, the run can be retried
#: once the limit is raised.
EXIT_OUT_OF_DESCRIPTORS = 75
#: The limit suggested to the user: sixteen times the macOS default of 256.
SUGGESTED_LIMIT = 4096


def soft_descriptor_limit() -> int | None:
    """The soft ``RLIMIT_NOFILE`` of this process, ``None`` where unknown."""
    try:
        import resource

        return int(resource.getrlimit(resource.RLIMIT_NOFILE)[0])
    except (ImportError, OSError, ValueError):
        return None


def out_of_descriptors_message(exc: BaseException) -> str:
    """One line: what happened, the limit, how to raise it."""
    limit = soft_descriptor_limit()
    shown = "unknown" if limit is None else str(limit)
    return (f"wystan: the scan ran out of file descriptors (limit {shown} open files) and stopped without "
            f"writing a map ({exc}); raise the limit, e.g. `ulimit -n {SUGGESTED_LIMIT}`, and run again")
