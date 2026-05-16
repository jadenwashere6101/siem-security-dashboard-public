from datetime import datetime, timedelta

import pytest

from core import playbook_store
from core.playbook_store import _utc_naive


@pytest.fixture
def utc_db(postgres_db):
    conn, cur = postgres_db
    cur.execute("SET TIME ZONE 'UTC'")
    conn.commit()
    return conn, cur


def _valid_steps():
    return [{"action": "monitor", "params": {}}]


def _ensure_playbook(conn, playbook_id="pb_lease"):
    if playbook_store.get_playbook_definition(conn, playbook_id) is None:
        playbook_store.create_playbook_definition(
            conn,
            playbook_id,
            "Lease tests",
            steps=_valid_steps(),
        )


def _insert_alert(cur, source_ip="10.0.0.50"):
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message)
        VALUES ('test_alert', 'LOW', %s::inet, 'lease-msg')
        RETURNING id
        """,
        (source_ip,),
    )
    return cur.fetchone()[0]


def _create_pending_execution(conn, cur, *, playbook_id="pb_lease", alert_id=None):
    _ensure_playbook(conn, playbook_id)
    if alert_id is None:
        alert_id = _insert_alert(cur)
    return playbook_store.create_playbook_execution(
        conn, playbook_id, alert_id=alert_id, incident_id=None
    )


@pytest.mark.usefixtures("postgres_db", "utc_db")
def test_acquire_execution_lease_on_pending_execution(utc_db):
    conn, cur = utc_db
    execution_id = _create_pending_execution(conn, cur)
    now = datetime(2026, 5, 16, 12, 0, 0)

    leased = playbook_store.acquire_execution_lease(
        conn, execution_id, "worker-a", lease_duration_seconds=60, now=now
    )
    conn.commit()

    assert leased is not None
    assert leased["status"] == "running"
    assert leased["lease_owner"] == "worker-a"
    assert _utc_naive(leased["lease_acquired_at"]) == now
    assert _utc_naive(leased["lease_heartbeat_at"]) == now
    assert _utc_naive(leased["lease_expires_at"]) == now + timedelta(seconds=60)
    assert leased["recovery_count"] == 0


@pytest.mark.usefixtures("postgres_db", "utc_db")
def test_cannot_acquire_already_leased_non_expired_execution(utc_db):
    conn, cur = utc_db
    execution_id = _create_pending_execution(conn, cur)
    now = datetime(2026, 5, 16, 12, 0, 0)

    assert (
        playbook_store.acquire_execution_lease(
            conn, execution_id, "worker-a", lease_duration_seconds=120, now=now
        )
        is not None
    )
    conn.commit()

    second = playbook_store.acquire_execution_lease(
        conn, execution_id, "worker-b", lease_duration_seconds=120, now=now
    )
    conn.commit()

    assert second is None


@pytest.mark.usefixtures("postgres_db", "utc_db")
def test_heartbeat_only_works_for_matching_owner(utc_db):
    conn, cur = utc_db
    execution_id = _create_pending_execution(conn, cur)
    start = datetime(2026, 5, 16, 12, 0, 0)

    playbook_store.acquire_execution_lease(
        conn, execution_id, "worker-a", lease_duration_seconds=30, now=start
    )
    conn.commit()

    heartbeat_at = start + timedelta(seconds=10)
    ok = playbook_store.heartbeat_execution_lease(
        conn,
        execution_id,
        "worker-a",
        lease_duration_seconds=60,
        now=heartbeat_at,
    )
    denied = playbook_store.heartbeat_execution_lease(
        conn,
        execution_id,
        "worker-b",
        lease_duration_seconds=60,
        now=heartbeat_at,
    )
    conn.commit()

    assert ok is not None
    assert _utc_naive(ok["lease_heartbeat_at"]) == heartbeat_at
    assert _utc_naive(ok["lease_expires_at"]) == heartbeat_at + timedelta(seconds=60)
    assert denied is None


@pytest.mark.usefixtures("postgres_db", "utc_db")
def test_release_only_works_for_matching_owner(utc_db):
    conn, cur = utc_db
    execution_id = _create_pending_execution(conn, cur)
    now = datetime(2026, 5, 16, 12, 0, 0)

    playbook_store.acquire_execution_lease(
        conn, execution_id, "worker-a", lease_duration_seconds=60, now=now
    )
    conn.commit()

    denied = playbook_store.release_execution_lease(conn, execution_id, "worker-b")
    allowed = playbook_store.release_execution_lease(conn, execution_id, "worker-a")
    conn.commit()

    assert denied is None
    assert allowed is not None
    assert allowed["lease_owner"] is None
    assert allowed["lease_expires_at"] is None


@pytest.mark.usefixtures("postgres_db", "utc_db")
def test_stale_running_execution_can_be_marked_for_recovery(utc_db):
    conn, cur = utc_db
    execution_id = _create_pending_execution(conn, cur)
    start = datetime(2026, 5, 16, 12, 0, 0)

    playbook_store.acquire_execution_lease(
        conn, execution_id, "worker-a", lease_duration_seconds=5, now=start
    )
    conn.commit()

    after_expiry = start + timedelta(seconds=30)
    stale_rows = playbook_store.list_stale_running_executions(conn, now=after_expiry)
    assert [row["id"] for row in stale_rows] == [execution_id]

    recovered = playbook_store.mark_stale_execution_for_recovery(
        conn, execution_id, now=after_expiry
    )
    conn.commit()

    assert recovered is not None
    assert recovered["status"] == "pending"
    assert recovered["recovery_count"] == 1
    assert recovered["failure_reason"] == "stale lease recovered for retry"
    assert recovered["lease_owner"] is None


@pytest.mark.usefixtures("postgres_db", "utc_db")
def test_awaiting_approval_is_not_treated_as_stale_running(utc_db):
    conn, cur = utc_db
    execution_id = _create_pending_execution(conn, cur)
    expired = datetime(2026, 5, 16, 12, 0, 0)

    cur.execute(
        """
        UPDATE playbook_executions
        SET status = 'awaiting_approval',
            lease_owner = 'worker-a',
            lease_acquired_at = %s,
            lease_heartbeat_at = %s,
            lease_expires_at = %s
        WHERE id = %s
        """,
        (expired, expired, expired, execution_id),
    )
    conn.commit()

    stale_rows = playbook_store.list_stale_running_executions(
        conn, now=expired + timedelta(minutes=5)
    )
    recovered = playbook_store.mark_stale_execution_for_recovery(
        conn, execution_id, now=expired + timedelta(minutes=5)
    )
    conn.commit()

    assert stale_rows == []
    assert recovered is None


@pytest.mark.usefixtures("postgres_db", "utc_db")
def test_recovery_count_increments_on_recovery(utc_db):
    conn, cur = utc_db
    execution_id = _create_pending_execution(conn, cur)
    start = datetime(2026, 5, 16, 12, 0, 0)

    playbook_store.acquire_execution_lease(
        conn, execution_id, "worker-a", lease_duration_seconds=1, now=start
    )
    conn.commit()

    first = playbook_store.mark_stale_execution_for_recovery(
        conn, execution_id, now=start + timedelta(seconds=10)
    )
    conn.commit()
    assert first is not None
    assert first["recovery_count"] == 1
    assert first["status"] == "pending"

    playbook_store.acquire_execution_lease(
        conn, execution_id, "worker-b", lease_duration_seconds=1, now=start + timedelta(seconds=20)
    )
    conn.commit()

    second = playbook_store.mark_stale_execution_for_recovery(
        conn, execution_id, now=start + timedelta(seconds=40)
    )
    conn.commit()
    assert second is not None
    assert second["recovery_count"] == 2
