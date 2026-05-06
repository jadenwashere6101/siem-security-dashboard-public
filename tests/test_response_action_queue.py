import pytest
from datetime import datetime, timedelta, timezone

from core.response_action_queue_store import (
    QueueTransitionError,
    claim_next_pending_action,
    mark_action_failed,
    mark_action_skipped,
    mark_action_success,
    record_action_failure,
    recover_stale_running_actions,
)
from core.ip_helpers import _compute_idempotency_key, enqueue_response_action
from engines.soar_action_worker import RetryableActionError, SkippedAction, process_next_action


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def insert_minimal_alert(cur, source_ip="10.0.0.1"):
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message)
        VALUES ('test_alert', 'low', %s, 'test alert for queue tests')
        RETURNING id
        """,
        (source_ip,),
    )
    return cur.fetchone()[0]


def fetch_queue_row(cur, row_id):
    cur.execute(
        """
        SELECT id, alert_id, source_ip::text, action, status,
               retry_count, max_retries, last_error,
               idempotency_key, created_at, updated_at
        FROM response_actions_queue
        WHERE id = %s
        """,
        (row_id,),
    )
    return cur.fetchone()


def count_queue_rows(cur):
    cur.execute("SELECT COUNT(*) FROM response_actions_queue")
    return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Schema default tests (task 3.2)
# ---------------------------------------------------------------------------

def test_queue_row_defaults_on_insert(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)

    row_id = enqueue_response_action(cur, alert_id, "10.0.0.1", "block_ip")
    conn.commit()

    row = fetch_queue_row(cur, row_id)
    _id, _alert_id, source_ip, action, status, retry_count, max_retries, last_error, ikey, created_at, updated_at = row

    assert status == "pending"
    assert retry_count == 0
    assert max_retries == 3
    assert last_error is None
    assert created_at is not None
    assert updated_at is not None
    assert ikey is not None and len(ikey) == 64  # SHA-256 hex digest


def test_queue_row_custom_max_retries(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)

    row_id = enqueue_response_action(cur, alert_id, "10.0.0.1", "flag_high_priority", max_retries=5)
    conn.commit()

    row = fetch_queue_row(cur, row_id)
    assert row[6] == 5


# ---------------------------------------------------------------------------
# Status transition tests (task 3.2)
# ---------------------------------------------------------------------------

def test_status_transition_to_running(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.0.0.2", "block_ip")
    conn.commit()

    cur.execute(
        "UPDATE response_actions_queue SET status = 'running', updated_at = NOW() WHERE id = %s",
        (row_id,),
    )
    conn.commit()

    row = fetch_queue_row(cur, row_id)
    assert row[4] == "running"


def test_status_transition_to_success(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.0.0.3", "block_ip")
    conn.commit()

    cur.execute(
        "UPDATE response_actions_queue SET status = 'success', updated_at = NOW() WHERE id = %s",
        (row_id,),
    )
    conn.commit()

    row = fetch_queue_row(cur, row_id)
    assert row[4] == "success"


def test_status_transition_to_failed_with_retry_metadata(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.0.0.4", "block_ip")
    conn.commit()

    cur.execute(
        """
        UPDATE response_actions_queue
        SET status = 'failed',
            retry_count = retry_count + 1,
            last_error = 'connection timeout',
            updated_at = NOW()
        WHERE id = %s
        """,
        (row_id,),
    )
    conn.commit()

    row = fetch_queue_row(cur, row_id)
    assert row[4] == "failed"
    assert row[5] == 1         # retry_count
    assert row[7] == "connection timeout"  # last_error


def test_status_transition_to_skipped(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.0.0.5", "monitor")
    conn.commit()

    cur.execute(
        "UPDATE response_actions_queue SET status = 'skipped', updated_at = NOW() WHERE id = %s",
        (row_id,),
    )
    conn.commit()

    row = fetch_queue_row(cur, row_id)
    assert row[4] == "skipped"


def test_invalid_status_rejected(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.0.0.6", "block_ip")
    conn.commit()

    import psycopg2
    with pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            "UPDATE response_actions_queue SET status = 'unknown_status' WHERE id = %s",
            (row_id,),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Idempotency key tests (task 3.2)
# ---------------------------------------------------------------------------

def test_idempotency_key_is_deterministic():
    key1 = _compute_idempotency_key(42, "192.168.1.1", "block_ip")
    key2 = _compute_idempotency_key(42, "192.168.1.1", "block_ip")
    assert key1 == key2


def test_idempotency_key_differs_by_action():
    key_block = _compute_idempotency_key(42, "192.168.1.1", "block_ip")
    key_flag = _compute_idempotency_key(42, "192.168.1.1", "flag_high_priority")
    assert key_block != key_flag


def test_idempotency_key_differs_by_ip():
    key1 = _compute_idempotency_key(42, "192.168.1.1", "block_ip")
    key2 = _compute_idempotency_key(42, "10.0.0.1", "block_ip")
    assert key1 != key2


def test_idempotency_key_differs_by_alert_id():
    key1 = _compute_idempotency_key(1, "192.168.1.1", "block_ip")
    key2 = _compute_idempotency_key(2, "192.168.1.1", "block_ip")
    assert key1 != key2


def test_duplicate_enqueue_returns_none(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)

    first_id = enqueue_response_action(cur, alert_id, "10.1.0.1", "block_ip")
    conn.commit()

    duplicate_id = enqueue_response_action(cur, alert_id, "10.1.0.1", "block_ip")
    conn.commit()

    assert first_id is not None
    assert duplicate_id is None
    assert count_queue_rows(cur) == 1


def test_duplicate_enqueue_does_not_create_second_row(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)

    for _ in range(3):
        enqueue_response_action(cur, alert_id, "10.2.0.1", "monitor")
        conn.commit()

    assert count_queue_rows(cur) == 1


def test_different_actions_create_separate_rows(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)

    id1 = enqueue_response_action(cur, alert_id, "10.3.0.1", "block_ip")
    conn.commit()
    id2 = enqueue_response_action(cur, alert_id, "10.3.0.1", "monitor")
    conn.commit()

    assert id1 is not None
    assert id2 is not None
    assert id1 != id2
    assert count_queue_rows(cur) == 2


# ---------------------------------------------------------------------------
# Nullable alert_id (design: queue can evolve beyond alert-driven actions)
# ---------------------------------------------------------------------------

def test_queue_row_with_null_alert_id(postgres_db):
    conn, cur = postgres_db

    row_id = enqueue_response_action(cur, None, "10.4.0.1", "block_ip")
    conn.commit()

    row = fetch_queue_row(cur, row_id)
    assert row[1] is None   # alert_id is null
    assert row[4] == "pending"


# ---------------------------------------------------------------------------
# Worker foundation claim/transition tests
# ---------------------------------------------------------------------------

def test_claim_next_pending_action_marks_row_running(postgres_db):
    conn, cur = postgres_db
    now = datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc)
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.5.0.1", "block_ip")
    conn.commit()

    claimed = claim_next_pending_action(conn, now=now)
    conn.commit()

    assert claimed["id"] == row_id
    assert claimed["status"] == "running"
    row = fetch_queue_row(cur, row_id)
    assert row[4] == "running"
    assert row[10] == now


def test_claim_next_pending_action_does_not_claim_running_row(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.5.0.2", "block_ip")
    conn.commit()

    first_claim = claim_next_pending_action(conn)
    conn.commit()
    second_claim = claim_next_pending_action(conn)
    conn.commit()

    assert first_claim["id"] == row_id
    assert second_claim is None


def test_running_action_can_transition_to_success(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.5.0.3", "block_ip")
    conn.commit()
    claim_next_pending_action(conn)
    conn.commit()

    updated = mark_action_success(conn, row_id)
    conn.commit()

    assert updated["status"] == "success"
    assert fetch_queue_row(cur, row_id)[4] == "success"


def test_non_running_action_rejects_success_transition(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.5.0.4", "block_ip")
    conn.commit()

    with pytest.raises(QueueTransitionError):
        mark_action_success(conn, row_id)


def test_running_action_can_transition_to_failed(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.5.0.5", "block_ip")
    conn.commit()
    claim_next_pending_action(conn)
    conn.commit()

    updated = mark_action_failed(conn, row_id, "temporary failure")
    conn.commit()

    assert updated["status"] == "failed"
    assert updated["retry_count"] == 1
    assert updated["last_error"] == "temporary failure"


def test_running_action_can_transition_to_skipped(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.5.0.6", "monitor")
    conn.commit()
    claim_next_pending_action(conn)
    conn.commit()

    updated = mark_action_skipped(conn, row_id, "safety validation skipped action")
    conn.commit()

    assert updated["status"] == "skipped"
    assert updated["last_error"] == "safety validation skipped action"


def test_retryable_failure_requeues_when_attempts_remain(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.5.0.7", "block_ip", max_retries=2)
    conn.commit()
    claim_next_pending_action(conn)
    conn.commit()

    updated = record_action_failure(conn, row_id, "transient timeout", retryable=True)
    conn.commit()

    assert updated["status"] == "pending"
    assert updated["retry_count"] == 1
    assert updated["last_error"] == "transient timeout"


def test_retryable_failure_stays_failed_when_retries_exhausted(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.5.0.8", "block_ip", max_retries=1)
    conn.commit()
    claim_next_pending_action(conn)
    conn.commit()

    updated = record_action_failure(conn, row_id, "still failing", retryable=True)
    conn.commit()

    assert updated["status"] == "failed"
    assert updated["retry_count"] == 1


def test_process_next_action_success_uses_placeholder_without_response_log(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.5.0.9", "block_ip")
    conn.commit()

    result = process_next_action(conn)

    assert result["queue_id"] == row_id
    assert result["outcome"] == "success"
    assert result["new_status"] == "success"
    cur.execute("SELECT COUNT(*) FROM response_actions_log")
    assert cur.fetchone()[0] == 0


def test_process_next_action_retryable_executor_requeues(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.5.0.10", "block_ip", max_retries=2)
    conn.commit()

    def fail_retryable(_row):
        raise RetryableActionError("adapter unavailable", code="adapter_unavailable")

    result = process_next_action(conn, executor=fail_retryable)

    assert result["queue_id"] == row_id
    assert result["outcome"] == "requeued"
    assert result["new_status"] == "pending"
    assert result["retryable"] is True
    assert result["retry_count"] == 1


def test_process_next_action_skip_executor_marks_skipped(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.5.0.11", "block_ip")
    conn.commit()

    def skip(_row):
        raise SkippedAction("policy disabled", code="policy_disabled")

    result = process_next_action(conn, executor=skip)

    assert result["queue_id"] == row_id
    assert result["outcome"] == "skipped"
    assert result["new_status"] == "skipped"
    assert result["error_code"] == "policy_disabled"


def test_stale_running_recovery_requeues_when_retries_remain(postgres_db):
    conn, cur = postgres_db
    now = datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc)
    stale_time = now - timedelta(minutes=16)
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.5.0.12", "block_ip", max_retries=3)
    conn.commit()
    claim_next_pending_action(conn, now=stale_time)
    conn.commit()

    recovered = recover_stale_running_actions(conn, now=now)
    conn.commit()

    assert [row["id"] for row in recovered] == [row_id]
    assert recovered[0]["status"] == "pending"


def test_stale_running_recovery_fails_when_retries_exhausted(postgres_db):
    conn, cur = postgres_db
    now = datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc)
    stale_time = now - timedelta(minutes=16)
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.5.0.13", "block_ip", max_retries=1)
    conn.commit()
    claim_next_pending_action(conn, now=stale_time)
    conn.commit()
    cur.execute(
        """
        UPDATE response_actions_queue
        SET retry_count = 1,
            updated_at = %s
        WHERE id = %s
        """,
        (stale_time, row_id),
    )
    conn.commit()

    recovered = recover_stale_running_actions(conn, now=now)
    conn.commit()

    assert [row["id"] for row in recovered] == [row_id]
    assert recovered[0]["status"] == "failed"


def test_stale_running_recovery_ignores_fresh_running_row(postgres_db):
    conn, cur = postgres_db
    now = datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc)
    fresh_time = now - timedelta(minutes=14)
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.5.0.14", "block_ip")
    conn.commit()
    claim_next_pending_action(conn, now=fresh_time)
    conn.commit()

    recovered = recover_stale_running_actions(conn, now=now)
    conn.commit()

    assert recovered == []
    assert fetch_queue_row(cur, row_id)[4] == "running"
