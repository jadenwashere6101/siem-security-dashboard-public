from datetime import datetime, timedelta

import pytest
from psycopg2.extras import Json

from core import dead_letter_store, playbook_store
from core.playbook_store import _utc_naive
from scripts import run_playbook_executor_once


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


def _make_expired_running_execution(conn, cur, *, playbook_id="pb_stale", now=None):
    execution_id = _create_pending_execution(conn, cur, playbook_id=playbook_id)
    start = now or datetime(2026, 5, 16, 12, 0, 0)
    playbook_store.acquire_execution_lease(
        conn, execution_id, "stale-worker", lease_duration_seconds=1, now=start
    )
    conn.commit()
    return execution_id, start + timedelta(seconds=10)


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
def test_claim_next_pending_execution_allows_one_worker_only(utc_db):
    conn, cur = utc_db
    execution_id = _create_pending_execution(conn, cur)
    now = datetime(2026, 5, 16, 12, 0, 0)

    first = playbook_store.claim_next_pending_playbook_execution_with_lease(
        conn,
        "worker-a",
        lease_duration_seconds=120,
        now=now,
    )
    conn.commit()
    second = playbook_store.claim_next_pending_playbook_execution_with_lease(
        conn,
        "worker-b",
        lease_duration_seconds=120,
        now=now,
    )
    conn.commit()

    assert first is not None
    assert first["id"] == execution_id
    assert first["status"] == "running"
    assert first["lease_owner"] == "worker-a"
    assert second is None

    row = playbook_store.get_playbook_execution(conn, execution_id)
    assert row["status"] == "running"
    assert row["lease_owner"] == "worker-a"


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
def test_finalize_updates_require_matching_lease_owner(utc_db):
    conn, cur = utc_db
    execution_id = _create_pending_execution(conn, cur)
    start = datetime(2026, 5, 16, 12, 0, 0)

    playbook_store.acquire_execution_lease(
        conn,
        execution_id,
        "worker-a",
        lease_duration_seconds=120,
        now=start,
    )
    conn.commit()

    stale_steps = [{"step_index": 0, "action": "monitor", "status": "success"}]
    failed_steps = [{"step_index": 0, "action": "monitor", "status": "failed"}]

    stale_success = playbook_store.set_playbook_execution_success(
        conn,
        execution_id,
        stale_steps,
        last_completed_step=0,
        now=start + timedelta(seconds=5),
        lease_owner="worker-b",
    )
    stale_failure = playbook_store.set_playbook_execution_failed(
        conn,
        execution_id,
        failed_steps,
        last_completed_step=None,
        now=start + timedelta(seconds=6),
        lease_owner="worker-b",
    )
    conn.commit()

    row = playbook_store.get_playbook_execution(conn, execution_id)
    assert stale_success is None
    assert stale_failure is None
    assert row["status"] == "running"
    assert row["lease_owner"] == "worker-a"
    assert row["steps_log"] == []


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
def test_awaiting_approval_resume_lease_allows_one_worker_only(utc_db):
    conn, cur = utc_db
    execution_id = _create_pending_execution(conn, cur, playbook_id="pb_resume_race")
    steps_log = [
        {
            "step_index": 0,
            "action": "require_approval",
            "status": "awaiting_approval",
            "event": "approval_requested",
        }
    ]
    now = datetime(2026, 5, 16, 12, 0, 0)
    cur.execute(
        """
        UPDATE playbook_executions
        SET status = 'awaiting_approval',
            steps_log = %s,
            last_completed_step = 0,
            lease_owner = NULL,
            lease_acquired_at = NULL,
            lease_heartbeat_at = NULL,
            lease_expires_at = NULL
        WHERE id = %s
        """,
        (Json(steps_log), execution_id),
    )
    conn.commit()

    first = playbook_store.acquire_awaiting_approval_resume_lease(
        conn,
        execution_id,
        "worker-a",
        steps_log,
        0,
        lease_duration_seconds=120,
        now=now,
    )
    conn.commit()
    second = playbook_store.acquire_awaiting_approval_resume_lease(
        conn,
        execution_id,
        "worker-b",
        steps_log,
        0,
        lease_duration_seconds=120,
        now=now,
    )
    conn.commit()

    assert first is not None
    assert first["status"] == "running"
    assert first["lease_owner"] == "worker-a"
    assert second is None


@pytest.mark.usefixtures("postgres_db", "utc_db")
def test_retry_execution_pending_row_is_not_double_claimed(utc_db):
    conn, cur = utc_db
    source_execution_id = _create_pending_execution(conn, cur, playbook_id="pb_retry_claim")
    failed_steps = [{"step_index": 0, "action": "monitor", "status": "failed"}]
    playbook_store.set_playbook_execution_failed(
        conn,
        source_execution_id,
        failed_steps,
        last_completed_step=None,
        now=datetime(2026, 5, 16, 12, 0, 0),
    )
    retry_execution_id = playbook_store.create_retry_execution(conn, source_execution_id)
    conn.commit()

    claimed = playbook_store.claim_next_pending_playbook_execution_with_lease(
        conn,
        "worker-a",
        lease_duration_seconds=120,
        now=datetime(2026, 5, 16, 12, 1, 0),
    )
    conn.commit()
    duplicate = playbook_store.claim_next_pending_playbook_execution_with_lease(
        conn,
        "worker-b",
        lease_duration_seconds=120,
        now=datetime(2026, 5, 16, 12, 1, 0),
    )
    conn.commit()

    assert claimed is not None
    assert claimed["id"] == retry_execution_id
    assert claimed["status"] == "running"
    assert claimed["lease_owner"] == "worker-a"
    assert duplicate is None


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


@pytest.mark.usefixtures("postgres_db", "utc_db")
def test_stale_recovery_dry_run_does_not_mutate(utc_db):
    conn, cur = utc_db
    execution_id, after_expiry = _make_expired_running_execution(
        conn, cur, playbook_id="pb_stale_dry"
    )

    result = run_playbook_executor_once.recover_stale_playbook_executions(
        conn,
        limit=10,
        dry_run=True,
        now=after_expiry,
    )
    conn.rollback()

    row = playbook_store.get_playbook_execution(conn, execution_id)
    assert result["dry_run"] is True
    assert result["scanned"] == 1
    assert result["recovered"] == 0
    assert row["status"] == "running"
    assert row["lease_owner"] == "stale-worker"
    assert row["recovery_count"] == 0


@pytest.mark.usefixtures("postgres_db", "utc_db")
def test_manual_stale_recovery_marks_expired_running_pending(utc_db, caplog):
    conn, cur = utc_db
    execution_id, after_expiry = _make_expired_running_execution(
        conn, cur, playbook_id="pb_stale_pending"
    )

    caplog.set_level("INFO")
    result = run_playbook_executor_once.recover_stale_playbook_executions(
        conn,
        limit=10,
        dry_run=False,
        now=after_expiry,
    )
    conn.commit()

    row = playbook_store.get_playbook_execution(conn, execution_id)
    assert result["dry_run"] is False
    assert result["scanned"] == 1
    assert result["recovered"] == 1
    assert result["pending"] == 1
    assert row["status"] == "pending"
    assert row["lease_owner"] is None
    assert row["lease_expires_at"] is None
    assert row["recovery_count"] == 1
    assert "playbook stale recovery applied" in caplog.text
    assert f"execution_id={execution_id}" in caplog.text


@pytest.mark.usefixtures("postgres_db", "utc_db")
def test_manual_stale_recovery_ignores_awaiting_approval(utc_db):
    conn, cur = utc_db
    execution_id = _create_pending_execution(conn, cur, playbook_id="pb_stale_approval")
    expired = datetime(2026, 5, 16, 12, 0, 0)
    cur.execute(
        """
        UPDATE playbook_executions
        SET status = 'awaiting_approval',
            lease_owner = 'stale-worker',
            lease_acquired_at = %s,
            lease_heartbeat_at = %s,
            lease_expires_at = %s
        WHERE id = %s
        """,
        (expired, expired, expired, execution_id),
    )
    conn.commit()

    result = run_playbook_executor_once.recover_stale_playbook_executions(
        conn,
        limit=10,
        dry_run=False,
        now=expired + timedelta(minutes=5),
    )
    conn.commit()

    row = playbook_store.get_playbook_execution(conn, execution_id)
    assert result["scanned"] == 0
    assert result["recovered"] == 0
    assert result["skipped_awaiting_approval"] == 1
    assert row["status"] == "awaiting_approval"
    assert row["recovery_count"] == 0


@pytest.mark.usefixtures("postgres_db", "utc_db")
def test_manual_stale_recovery_marks_exhausted_attempts_failed(utc_db):
    conn, cur = utc_db
    execution_id, after_expiry = _make_expired_running_execution(
        conn, cur, playbook_id="pb_stale_exhausted"
    )
    playbook_store.update_playbook_execution_reliability_metadata(
        conn,
        execution_id,
        attempt_count=3,
        max_attempts=3,
    )
    conn.commit()

    result = run_playbook_executor_once.recover_stale_playbook_executions(
        conn,
        limit=10,
        dry_run=False,
        now=after_expiry,
    )
    conn.commit()

    row = playbook_store.get_playbook_execution(conn, execution_id)
    assert result["scanned"] == 1
    assert result["recovered"] == 1
    assert result["failed"] == 1
    assert row["status"] == "failed"
    assert row["lease_owner"] is None
    assert row["recovery_count"] == 1
    assert row["failure_reason"] == "stale lease exceeded max attempts"


@pytest.mark.usefixtures("postgres_db", "utc_db")
def test_manual_stale_recovery_exhaustion_captures_failed_step_dead_letter(utc_db):
    conn, cur = utc_db
    execution_id, after_expiry = _make_expired_running_execution(
        conn, cur, playbook_id="pb_stale_dead_letter"
    )
    failed_steps = [
        {
            "step_index": 0,
            "action": "notify_slack",
            "status": "failed",
            "message": "stale failed delivery https://hooks.slack.com/services/secret",
            "output": {
                "simulated": True,
                "executed": False,
                "adapter_result": {
                    "metadata": {
                        "failure_classification": "timeout",
                        "webhook_url": "https://hooks.slack.com/services/secret",
                    }
                },
            },
            "error": {
                "code": "adapter_simulation_failed",
                "message": "stale failed delivery https://hooks.slack.com/services/secret",
            },
        }
    ]
    cur.execute(
        "UPDATE playbook_executions SET steps_log = %s WHERE id = %s",
        (Json(failed_steps), execution_id),
    )
    playbook_store.update_playbook_execution_reliability_metadata(
        conn,
        execution_id,
        attempt_count=3,
        max_attempts=3,
    )
    conn.commit()

    result = run_playbook_executor_once.recover_stale_playbook_executions(
        conn,
        limit=10,
        dry_run=False,
        now=after_expiry,
    )
    conn.commit()

    assert result["failed"] == 1
    [dead_letter] = dead_letter_store.list_dead_letters(conn, execution_id=execution_id)
    assert dead_letter["source_type"] == "playbook_execution"
    assert dead_letter["source_id"] == execution_id
    assert dead_letter["step_index"] == 0
    assert dead_letter["action_name"] == "notify_slack"
    assert dead_letter["failure_class"] == "timeout"
    assert dead_letter["error_message"] == "stale failed delivery [REDACTED_URL]"
    assert "webhook_url" not in dead_letter["payload_json"]["step"]["output"]["adapter_result"]["metadata"]
