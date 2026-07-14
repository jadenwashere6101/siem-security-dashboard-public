from datetime import datetime, timedelta, timezone

from core.worker_heartbeat_store import (
    PLAYBOOK_WORKER_NAME,
    get_worker_heartbeat,
    summarize_worker_health,
    upsert_worker_heartbeat,
)


def test_upsert_and_get_worker_heartbeat(postgres_db):
    conn, _cur = postgres_db
    started_at = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    heartbeat_at = started_at + timedelta(seconds=15)

    upsert_worker_heartbeat(
        conn,
        worker_name=PLAYBOOK_WORKER_NAME,
        worker_instance_id="worker-alpha",
        build_version="abc123",
        started_at=started_at,
        last_heartbeat_at=heartbeat_at,
    )
    conn.commit()

    row = get_worker_heartbeat(conn, worker_name=PLAYBOOK_WORKER_NAME)
    assert row is not None
    assert row["worker_name"] == PLAYBOOK_WORKER_NAME
    assert row["worker_instance_id"] == "worker-alpha"
    assert row["build_version"] == "abc123"
    assert row["started_at"] == started_at
    assert row["last_heartbeat_at"] == heartbeat_at


def test_upsert_overwrites_same_logical_worker_row(postgres_db):
    conn, _cur = postgres_db
    first_started = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    second_started = first_started + timedelta(minutes=5)

    upsert_worker_heartbeat(
        conn,
        worker_name=PLAYBOOK_WORKER_NAME,
        worker_instance_id="worker-alpha",
        build_version="abc123",
        started_at=first_started,
        last_heartbeat_at=first_started,
    )
    upsert_worker_heartbeat(
        conn,
        worker_name=PLAYBOOK_WORKER_NAME,
        worker_instance_id="worker-beta",
        build_version="def456",
        started_at=second_started,
        last_heartbeat_at=second_started,
    )
    conn.commit()

    row = get_worker_heartbeat(conn, worker_name=PLAYBOOK_WORKER_NAME)
    assert row["worker_instance_id"] == "worker-beta"
    assert row["build_version"] == "def456"
    assert row["started_at"] == second_started


def test_summarize_worker_health_unknown():
    summary = summarize_worker_health(None, now=datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc))
    assert summary["status"] == "unknown"
    assert summary["worker_heartbeat_available"] is False
    assert summary["started_at"] is None
    assert summary["last_heartbeat_at"] is None
    assert summary["uptime_seconds"] is None


def test_summarize_worker_health_transitions():
    started_at = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    row = {
        "worker_name": PLAYBOOK_WORKER_NAME,
        "worker_instance_id": "worker-alpha",
        "build_version": "abc123",
        "started_at": started_at,
        "last_heartbeat_at": started_at,
    }

    healthy = summarize_worker_health(row, now=started_at + timedelta(seconds=45))
    degraded = summarize_worker_health(row, now=started_at + timedelta(seconds=46))
    offline = summarize_worker_health(row, now=started_at + timedelta(seconds=121))

    assert healthy["status"] == "healthy"
    assert healthy["uptime_seconds"] == 45
    assert degraded["status"] == "degraded"
    assert offline["status"] == "offline"
