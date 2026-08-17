from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from threading import Lock
from time import monotonic

from core.source_inventory import CANONICAL_SOURCES


SOURCE_EVENT_METRICS_CACHE_TTL_SECONDS = max(
    int(os.getenv("SOURCE_EVENT_METRICS_CACHE_TTL_SECONDS", "300")), 1
)
SOURCE_EVENT_METRICS_STATEMENT_TIMEOUT_MS = min(
    max(int(os.getenv("SOURCE_EVENT_METRICS_STATEMENT_TIMEOUT_MS", "5000")), 100),
    10_000,
)

SOURCE_EVENT_METRICS_SQL = """
    SELECT
        source,
        COUNT(*) FILTER (WHERE created_at >= %s) AS events_last_hour,
        COUNT(*) FILTER (WHERE created_at >= %s) AS events_today,
        COUNT(*) AS total_events
    FROM events
    WHERE source = ANY(%s)
      AND created_at <= %s
    GROUP BY source
"""

_cache_lock = Lock()
_cached_metrics: dict | None = None
_cached_until = 0.0


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    return value.astimezone(timezone.utc)


def _get_cached_metrics(now: float) -> dict | None:
    with _cache_lock:
        if _cached_metrics is not None and now < _cached_until:
            return _cached_metrics
    return None


def _store_cached_metrics(payload: dict, now: float) -> None:
    global _cached_metrics, _cached_until
    with _cache_lock:
        _cached_metrics = payload
        _cached_until = now + SOURCE_EVENT_METRICS_CACHE_TTL_SECONDS


def clear_source_event_metrics_cache() -> None:
    """Clear process-local metrics state for tests and explicit maintenance."""
    global _cached_metrics, _cached_until
    with _cache_lock:
        _cached_metrics = None
        _cached_until = 0.0


def aggregate_source_event_metrics(
    conn,
    *,
    generated_at: datetime | None = None,
    use_cache: bool = True,
) -> dict:
    """Return historical event counts independently of source-health evaluation."""
    cache_now = monotonic()
    if use_cache:
        cached = _get_cached_metrics(cache_now)
        if cached is not None:
            return cached

    observation_time = _as_utc(generated_at or datetime.now(timezone.utc))
    last_hour_start = observation_time - timedelta(hours=1)
    today_start = observation_time.replace(hour=0, minute=0, second=0, microsecond=0)

    cur = conn.cursor()
    try:
        cur.execute(
            f"SET LOCAL statement_timeout = {SOURCE_EVENT_METRICS_STATEMENT_TIMEOUT_MS}"
        )
        cur.execute(
            SOURCE_EVENT_METRICS_SQL,
            (
                last_hour_start,
                today_start,
                [item.source for item in CANONICAL_SOURCES],
                observation_time,
            ),
        )
        rows_by_source = {
            row[0]: {
                "events_last_hour": int(row[1]),
                "events_today": int(row[2]),
                "total_events": int(row[3]),
            }
            for row in cur.fetchall()
        }
    finally:
        cur.close()

    payload = {
        "generated_at": observation_time.isoformat(),
        "cache_ttl_seconds": SOURCE_EVENT_METRICS_CACHE_TTL_SECONDS,
        "windows": {
            "last_hour_start": last_hour_start.isoformat(),
            "today_start": today_start.isoformat(),
            "timezone": "UTC",
        },
        "sources": [
            {
                "source": definition.source,
                **rows_by_source.get(
                    definition.source,
                    {"events_last_hour": 0, "events_today": 0, "total_events": 0},
                ),
            }
            for definition in CANONICAL_SOURCES
        ],
    }
    if use_cache:
        _store_cached_metrics(payload, cache_now)
    return payload
