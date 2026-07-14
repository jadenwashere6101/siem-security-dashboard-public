from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

PLAYBOOK_WORKER_NAME = "playbook_worker"
WORKER_HEARTBEAT_INTERVAL_SECONDS = 15
WORKER_HEALTHY_THRESHOLD_SECONDS = 45
WORKER_OFFLINE_THRESHOLD_SECONDS = 120


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def upsert_worker_heartbeat(
    conn,
    *,
    worker_name: str,
    worker_instance_id: str,
    started_at: datetime,
    last_heartbeat_at: datetime | None = None,
    build_version: str | None = None,
) -> dict[str, Any]:
    heartbeat_at = _as_utc(last_heartbeat_at) or _utc_now()
    started = _as_utc(started_at) or heartbeat_at
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO soar_worker_heartbeats (
                worker_name,
                worker_instance_id,
                build_version,
                started_at,
                last_heartbeat_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (worker_name) DO UPDATE
            SET worker_instance_id = EXCLUDED.worker_instance_id,
                build_version = EXCLUDED.build_version,
                started_at = EXCLUDED.started_at,
                last_heartbeat_at = EXCLUDED.last_heartbeat_at,
                updated_at = EXCLUDED.updated_at
            RETURNING
                worker_name,
                worker_instance_id,
                build_version,
                started_at,
                last_heartbeat_at,
                updated_at
            """,
            (
                worker_name,
                worker_instance_id,
                build_version,
                started,
                heartbeat_at,
                heartbeat_at,
            ),
        )
        row = cur.fetchone()
    return {
        "worker_name": row[0],
        "worker_instance_id": row[1],
        "build_version": row[2],
        "started_at": row[3],
        "last_heartbeat_at": row[4],
        "updated_at": row[5],
    }


def get_worker_heartbeat(conn, *, worker_name: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                worker_name,
                worker_instance_id,
                build_version,
                started_at,
                last_heartbeat_at,
                updated_at
            FROM soar_worker_heartbeats
            WHERE worker_name = %s
            """,
            (worker_name,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return {
        "worker_name": row[0],
        "worker_instance_id": row[1],
        "build_version": row[2],
        "started_at": row[3],
        "last_heartbeat_at": row[4],
        "updated_at": row[5],
    }


def summarize_worker_health(
    row: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _as_utc(now) or _utc_now()
    if row is None:
        return {
            "status": "unknown",
            "source": "daemon_heartbeat",
            "worker_name": PLAYBOOK_WORKER_NAME,
            "worker_heartbeat_available": False,
            "worker_instance_id": None,
            "build_version": None,
            "started_at": None,
            "last_heartbeat_at": None,
            "uptime_seconds": None,
            "message": "Worker heartbeat has never been recorded.",
        }

    started_at = _as_utc(row.get("started_at"))
    last_heartbeat_at = _as_utc(row.get("last_heartbeat_at"))
    heartbeat_age_seconds = None
    if last_heartbeat_at is not None:
        heartbeat_age_seconds = max(0, int((current - last_heartbeat_at).total_seconds()))
    uptime_seconds = None
    if started_at is not None:
        uptime_seconds = max(0, int((current - started_at).total_seconds()))

    if heartbeat_age_seconds is None:
        status = "unknown"
        message = "Worker heartbeat has never been recorded."
    elif heartbeat_age_seconds <= WORKER_HEALTHY_THRESHOLD_SECONDS:
        status = "healthy"
        message = "Worker heartbeat is recent."
    elif heartbeat_age_seconds <= WORKER_OFFLINE_THRESHOLD_SECONDS:
        status = "degraded"
        message = "Worker heartbeat is late but still within the stale window."
    else:
        status = "offline"
        message = "Worker heartbeat exceeded the offline timeout."

    return {
        "status": status,
        "source": "daemon_heartbeat",
        "worker_name": row.get("worker_name") or PLAYBOOK_WORKER_NAME,
        "worker_heartbeat_available": last_heartbeat_at is not None,
        "worker_instance_id": row.get("worker_instance_id"),
        "build_version": row.get("build_version"),
        "started_at": _iso(started_at),
        "last_heartbeat_at": _iso(last_heartbeat_at),
        "uptime_seconds": uptime_seconds,
        "message": message,
    }
