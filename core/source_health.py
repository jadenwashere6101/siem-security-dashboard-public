from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.source_inventory import (
    CANONICAL_SOURCES,
    INGESTION_MODE_CHECKPOINT,
    INGESTION_MODE_PUSH,
)


SOURCE_HEALTH_STATE_SQL = """
    SELECT
        source,
        latest_event_at,
        latest_qualifying_real_ingestion_at,
        historical_backfill_complete,
        backfill_high_water_event_id,
        backfill_last_processed_event_id,
        total_events,
        total_events_initialized,
        updated_at
    FROM source_ingestion_health_state
    WHERE source = ANY(%s)
"""

SOURCE_HEALTH_CHECKPOINT_SQL = """
    SELECT
        connector_name,
        last_processed_at,
        last_poll_status,
        last_poll_counts,
        updated_at
    FROM ingestion_checkpoints
    WHERE connector_name = ANY(%s)
"""


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    return value.astimezone(timezone.utc)


def _serialize_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _as_utc(value).isoformat()


def _age_seconds(observation_time: datetime, timestamp: datetime | None) -> int | None:
    if timestamp is None:
        return None
    age = int((observation_time - _as_utc(timestamp)).total_seconds())
    return age if age >= 0 else None


def _checkpoint_connector_status(last_poll_status: str | None) -> str:
    return (
        "healthy" if last_poll_status == "success"
        else "degraded" if last_poll_status == "partial"
        else "failed" if last_poll_status == "failure"
        else "unknown"
    )


def _resolve_push_health(
    state: dict | None,
    *,
    observation_time: datetime,
    freshness_threshold_seconds: int,
) -> tuple[str, str, int | None]:
    latest_ingestion = (
        state.get("latest_qualifying_real_ingestion_at") if state else None
    )
    age_seconds = _age_seconds(observation_time, latest_ingestion)
    if age_seconds is None:
        if not state or not state.get("historical_backfill_complete"):
            return "unknown", "historical_backfill_incomplete", None
        return "unknown", "no_qualifying_ingestion", None
    if age_seconds <= freshness_threshold_seconds:
        return "healthy", "recent_qualifying_ingestion", age_seconds
    return "degraded", "qualifying_ingestion_stale", age_seconds


def _resolve_checkpoint_health(
    checkpoint: dict | None,
    *,
    observation_time: datetime,
    freshness_threshold_seconds: int,
) -> tuple[str, str, int | None]:
    if checkpoint is None:
        return "unknown", "checkpoint_missing", None
    poll_status = checkpoint.get("last_poll_status")
    if poll_status in {"partial", "failure"}:
        return "degraded", f"checkpoint_{poll_status}", _age_seconds(
            observation_time, checkpoint.get("updated_at")
        )
    if poll_status != "success":
        return "unknown", "checkpoint_status_unknown", _age_seconds(
            observation_time, checkpoint.get("updated_at")
        )
    age_seconds = _age_seconds(observation_time, checkpoint.get("updated_at"))
    if age_seconds is None:
        return "unknown", "checkpoint_time_unavailable", None
    if age_seconds <= freshness_threshold_seconds:
        return "healthy", "checkpoint_success_fresh", age_seconds
    return "degraded", "checkpoint_stale", age_seconds


def aggregate_source_health(conn, *, generated_at: datetime | None = None) -> dict:
    observation_time = _as_utc(generated_at or datetime.now(timezone.utc))
    last_hour_start = observation_time - timedelta(hours=1)
    today_start = observation_time.replace(hour=0, minute=0, second=0, microsecond=0)

    cur = conn.cursor()
    try:
        cur.execute(
            SOURCE_HEALTH_STATE_SQL,
            ([item.source for item in CANONICAL_SOURCES],),
        )
        state_by_source = {
            row[0]: {
                "last_event_at": row[1],
                "latest_qualifying_real_ingestion_at": row[2],
                "historical_backfill_complete": bool(row[3]),
                "backfill_high_water_event_id": row[4],
                "backfill_last_processed_event_id": int(row[5]),
                "total_events": int(row[6]),
                "total_events_initialized": bool(row[7]),
                "updated_at": row[8],
            }
            for row in cur.fetchall()
        }

        cur.execute(
            SOURCE_HEALTH_CHECKPOINT_SQL,
            ([item.source for item in CANONICAL_SOURCES],),
        )
        checkpoints_by_source = {
            row[0]: {
                "last_processed_at": row[1],
                "last_poll_status": row[2],
                "last_poll_counts": row[3] or {},
                "updated_at": row[4],
            }
            for row in cur.fetchall()
        }
    finally:
        cur.close()

    sources = []
    for definition in CANONICAL_SOURCES:
        state = state_by_source.get(definition.source)
        checkpoint = checkpoints_by_source.get(definition.source)
        if definition.ingestion_mode == INGESTION_MODE_PUSH:
            health_status, health_reason, basis_age_seconds = _resolve_push_health(
                state,
                observation_time=observation_time,
                freshness_threshold_seconds=definition.freshness_threshold_seconds,
            )
            health_basis = "event_ingestion_freshness"
        elif definition.ingestion_mode == INGESTION_MODE_CHECKPOINT:
            health_status, health_reason, basis_age_seconds = _resolve_checkpoint_health(
                checkpoint,
                observation_time=observation_time,
                freshness_threshold_seconds=definition.freshness_threshold_seconds,
            )
            health_basis = "poll_checkpoint"
        else:
            health_status, health_reason, basis_age_seconds = (
                "unknown", "ingestion_mode_unknown", None
            )
            health_basis = "unclassified"
        source_entry = {
            "source": definition.source,
            "source_type": definition.source_type,
            "display_label": definition.display_label,
            "ingestion_mode": definition.ingestion_mode,
            "health_status": health_status,
            "health_basis": health_basis,
            "health_reason": health_reason,
            "freshness_threshold_seconds": definition.freshness_threshold_seconds,
            "health_basis_age_seconds": basis_age_seconds,
            "last_event_at": _serialize_timestamp(
                state["last_event_at"] if state else None
            ),
            "latest_ingestion_at": _serialize_timestamp(
                state["latest_qualifying_real_ingestion_at"] if state else None
            ),
            "ever_seen": (
                bool(state and state["last_event_at"] is not None)
                if definition.ingestion_mode == INGESTION_MODE_PUSH
                else checkpoint is not None
            ),
            "total_events": (
                state["total_events"]
                if state and state["total_events_initialized"]
                else None
            ),
            "historical_backfill_complete": (
                state["historical_backfill_complete"]
                if definition.ingestion_mode == INGESTION_MODE_PUSH and state
                else False
                if definition.ingestion_mode == INGESTION_MODE_PUSH
                else None
            ),
        }
        if checkpoint:
            source_entry["last_poll_status"] = checkpoint["last_poll_status"]
            source_entry["last_poll_at"] = _serialize_timestamp(checkpoint["updated_at"])
            source_entry["last_poll_counts"] = checkpoint["last_poll_counts"]
            source_entry["last_processed_at"] = _serialize_timestamp(
                checkpoint["last_processed_at"]
            )
            if checkpoint["last_processed_at"] is not None:
                source_entry["checkpoint_age_seconds"] = int(
                    (observation_time - _as_utc(checkpoint["last_processed_at"])).total_seconds()
                )
            source_entry["connector_status"] = _checkpoint_connector_status(
                checkpoint["last_poll_status"]
            )
        sources.append(source_entry)

    return {
        "generated_at": observation_time.isoformat(),
        "windows": {
            "last_hour_start": last_hour_start.isoformat(),
            "today_start": today_start.isoformat(),
            "timezone": "UTC",
        },
        "sources": sources,
    }
