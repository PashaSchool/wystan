"""The one place an Anthropic client is built.

Every model call in a scan goes through a client made here, so every call has
the same hard limit on how long it may wait. The SDK's own default is ten
minutes per attempt with two retries: a provider that stops answering could
hold a scan for half an hour with nothing running (seen on a corpus scan,
2026-11-11). A call that times out raises ``anthropic.APITimeoutError``, which
the callers already treat like any other failed call: the stage falls back to
its deterministic path.
"""

from __future__ import annotations

from typing import Any

__all__ = ["LLM_CALL_TIMEOUT_SEC", "LLM_CONNECT_TIMEOUT_SEC", "LLM_MAX_RETRIES", "build_client"]

# Whole-call limit. The longest calls a scan makes (a flow batch on the
# larger model) finish well inside it; anything slower is a stalled call.
LLM_CALL_TIMEOUT_SEC = 240.0
LLM_CONNECT_TIMEOUT_SEC = 15.0
# One retry: with the limit above a call can hold a stage for eight minutes at
# most, instead of thirty.
LLM_MAX_RETRIES = 1


def build_client(api_key: str | None = None) -> Any:
    """An Anthropic client with the scan's timeout and retry budget.

    ``api_key`` of ``None`` lets the SDK read its own environment, as a bare
    ``Anthropic()`` does. Raises ``ImportError`` when the SDK is missing.
    """
    import anthropic
    import httpx

    options: dict[str, Any] = {
        "timeout": httpx.Timeout(LLM_CALL_TIMEOUT_SEC, connect=LLM_CONNECT_TIMEOUT_SEC),
        "max_retries": LLM_MAX_RETRIES,
    }
    if api_key:
        options["api_key"] = api_key
    return anthropic.Anthropic(**options)
