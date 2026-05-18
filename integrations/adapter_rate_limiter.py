"""In-process SOAR adapter rate limiting."""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from typing import Any

DEFAULT_RATE_LIMITS_PER_MINUTE = {
    "slack": 20,
    "teams": 20,
    "email": 10,
    "webhook": 30,
}

_RATE_LIMIT_ENVS = {
    "slack": "SLACK_MAX_SENDS_PER_MINUTE",
    "teams": "TEAMS_MAX_SENDS_PER_MINUTE",
    "email": "EMAIL_MAX_SENDS_PER_MINUTE",
    "webhook": "WEBHOOK_MAX_SENDS_PER_MINUTE",
}
_WINDOW_SECONDS = 60
_attempts: dict[str, deque[float]] = defaultdict(deque)


def reset_adapter_rate_limiters(adapter_name: str | None = None) -> None:
    """Reset in-process rate limiter state. Primarily used by tests."""
    if adapter_name is None:
        _attempts.clear()
        return
    _attempts.pop(_normalize_adapter(adapter_name), None)


def _normalize_adapter(adapter_name: str) -> str:
    return str(adapter_name or "").strip().lower()


def _limit_for_adapter(adapter_name: str) -> int:
    adapter = _normalize_adapter(adapter_name)
    default = DEFAULT_RATE_LIMITS_PER_MINUTE.get(adapter, 10)
    env_name = _RATE_LIMIT_ENVS.get(adapter)
    raw = os.getenv(env_name, str(default)).strip() if env_name else str(default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(1, min(value, 1000))


# spec: SPEC-INTEG-005 / SPEC-UI-004 - real-capable adapters fail closed under flood pressure.
def check_adapter_rate_limit(adapter_name: str, *, now: float | None = None) -> dict[str, Any]:
    """Return allow/block decision for one adapter send attempt."""
    adapter = _normalize_adapter(adapter_name)
    current = time.monotonic() if now is None else float(now)
    limit = _limit_for_adapter(adapter)
    window_start = current - _WINDOW_SECONDS
    bucket = _attempts[adapter]

    while bucket and bucket[0] <= window_start:
        bucket.popleft()

    if len(bucket) >= limit:
        reset_after = max(0.0, _WINDOW_SECONDS - (current - bucket[0])) if bucket else _WINDOW_SECONDS
        return {
            "allowed": False,
            "adapter": adapter,
            "limit": limit,
            "window_seconds": _WINDOW_SECONDS,
            "remaining": 0,
            "reset_after_seconds": int(reset_after) + (1 if reset_after % 1 else 0),
            "failure_classification": "provider_rate_limited",
            "retry_eligible": True,
        }

    bucket.append(current)
    return {
        "allowed": True,
        "adapter": adapter,
        "limit": limit,
        "window_seconds": _WINDOW_SECONDS,
        "remaining": max(0, limit - len(bucket)),
        "reset_after_seconds": 0,
        "failure_classification": None,
        "retry_eligible": False,
    }
