from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.source_inventory import CANONICAL_SOURCES


SOURCE_HEALTH_AGGREGATION_SQL = """
    SELECT
        source,
        MAX(created_at) AS last_event_at,
        COUNT(*) FILTER (WHERE created_at >= %s) AS events_last_hour,
        COUNT(*) FILTER (WHERE created_at >= %s) AS events_today,
        COUNT(*) AS total_events
    FROM events
    WHERE source = ANY(%s)
      AND created_at <= %s
    GROUP BY source
"""


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    return value.astimezone(timezone.utc)


def _serialize_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _as_utc(value).isoformat()


def aggregate_source_health(conn, *, generated_at: datetime | None = None) -> dict:
    observation_time = _as_utc(generated_at or datetime.now(timezone.utc))
    last_hour_start = observation_time - timedelta(hours=1)
    today_start = observation_time.replace(hour=0, minute=0, second=0, microsecond=0)

    cur = conn.cursor()
    try:
        cur.execute(
            SOURCE_HEALTH_AGGREGATION_SQL,
            (
                last_hour_start,
                today_start,
                [item.source for item in CANONICAL_SOURCES],
                observation_time,
            ),
        )
        rows_by_source = {
            row[0]: {
                "last_event_at": row[1],
                "events_last_hour": int(row[2]),
                "events_today": int(row[3]),
                "total_events": int(row[4]),
            }
            for row in cur.fetchall()
        }
    finally:
        cur.close()

    sources = []
    for definition in CANONICAL_SOURCES:
        aggregate = rows_by_source.get(definition.source)
        total_events = aggregate["total_events"] if aggregate else 0
        sources.append(
            {
                "source": definition.source,
                "source_type": definition.source_type,
                "display_label": definition.display_label,
                "last_event_at": _serialize_timestamp(
                    aggregate["last_event_at"] if aggregate else None
                ),
                "events_last_hour": aggregate["events_last_hour"] if aggregate else 0,
                "events_today": aggregate["events_today"] if aggregate else 0,
                "total_events": total_events,
                "ever_seen": total_events > 0,
            }
        )

    return {
        "generated_at": observation_time.isoformat(),
        "windows": {
            "last_hour_start": last_hour_start.isoformat(),
            "today_start": today_start.isoformat(),
            "timezone": "UTC",
        },
        "sources": sources,
    }

