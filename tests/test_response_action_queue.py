import pytest
import psycopg2
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from core.approval_store import approve_request, create_approval_request, deny_request
from core.response_action_queue_store import (
    QueueTransitionError,
    claim_next_approved_awaiting_action,
    claim_next_pending_action,
    get_queue_action,
    get_queue_status_counts,
    mark_action_awaiting_approval,
    mark_action_failed,
    mark_action_skipped,
    mark_action_success,
    mark_awaiting_approval_skipped,
    record_action_failure,
    recover_stale_running_actions,
    set_queue_linkage,
    sweep_terminal_approval_queue_rows,
)
from core.ip_helpers import _compute_idempotency_key, enqueue_response_action
from core.ip_helpers import execute_response_action
from engines.soar_action_worker import _append_running_outcome_event, process_next_action
from engines.soar_errors import RetryableActionError, SkippedAction
from engines.soar_executor import SimulationExecutor
import siem_backend


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


def fetch_action_logs(cur, alert_id=None):
    if alert_id is None:
        cur.execute(
            """
            SELECT alert_id, source_ip::text, action, status, details
            FROM response_actions_log
            ORDER BY id
            """
        )
    else:
        cur.execute(
            """
            SELECT alert_id, source_ip::text, action, status, details
            FROM response_actions_log
            WHERE alert_id = %s
            ORDER BY id
            """,
            (alert_id,),
        )
    return cur.fetchall()


def fetch_action_logs_with_links(cur, alert_id=None):
    if alert_id is None:
        cur.execute(
            """
            SELECT id, alert_id, source_ip::text, action, status, details,
                   decision_id, soar_correlation_id
            FROM response_actions_log
            ORDER BY id
            """
        )
    else:
        cur.execute(
            """
            SELECT id, alert_id, source_ip::text, action, status, details,
                   decision_id, soar_correlation_id
            FROM response_actions_log
            WHERE alert_id = %s
            ORDER BY id
            """,
            (alert_id,),
        )
    return cur.fetchall()


def fetch_outcome_events(cur, queue_id):
    cur.execute(
        """
        SELECT event_type, execution_mode, execution_state, simulated,
               external_executed, tracking_recorded, execution_actor,
               reason_code, idempotency_key
        FROM soar_response_outcome_events
        WHERE queue_id = %s
        ORDER BY id
        """,
        (queue_id,),
    )
    return cur.fetchall()


def fetch_detailed_outcome_events(cur, queue_id):
    cur.execute(
        """
        SELECT event_type, execution_state, reason_code, idempotency_key,
               response_action_log_id, approval_request_id, outcome_summary,
               simulated, external_executed, tracking_recorded
        FROM soar_response_outcome_events
        WHERE queue_id = %s
        ORDER BY id
        """,
        (queue_id,),
    )
    return cur.fetchall()


def count_approval_requests(cur, queue_id):
    cur.execute(
        "SELECT COUNT(*) FROM approval_requests WHERE queue_id = %s",
        (queue_id,),
    )
    return cur.fetchone()[0]


def insert_user(cur, username="approver", role="super_admin"):
    cur.execute(
        """
        INSERT INTO users (username, password_hash, role)
        VALUES (%s, 'hash', %s)
        RETURNING id
        """,
        (username, role),
    )
    return cur.fetchone()[0]


def set_queue_status(cur, row_id, status, retry_count=None):
    if retry_count is None:
        cur.execute(
            "UPDATE response_actions_queue SET status = %s WHERE id = %s",
            (status, row_id),
        )
    else:
        cur.execute(
            """
            UPDATE response_actions_queue
            SET status = %s, retry_count = %s
            WHERE id = %s
            """,
            (status, retry_count, row_id),
        )


def insert_queue_approval(cur, queue_id, action="block_ip", status="expired"):
    cur.execute(
        """
        INSERT INTO approval_requests (
            queue_id, action, status, expires_at, decided_at
        )
        VALUES (
            %s,
            %s,
            %s,
            NOW() - INTERVAL '1 minute',
            CASE WHEN %s = 'pending' THEN NULL ELSE NOW() END
        )
        RETURNING id
        """,
        (queue_id, action, status, status),
    )
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


def test_status_transition_to_awaiting_approval(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.0.0.7", "block_ip")
    conn.commit()

    cur.execute(
        "UPDATE response_actions_queue SET status = 'awaiting_approval', updated_at = NOW() WHERE id = %s",
        (row_id,),
    )
    conn.commit()

    row = fetch_queue_row(cur, row_id)
    assert row[4] == "awaiting_approval"


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


def test_running_action_can_transition_to_awaiting_approval(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.5.0.61", "block_ip")
    conn.commit()
    claim_next_pending_action(conn)
    conn.commit()

    updated = mark_action_awaiting_approval(conn, row_id, "approval required")
    conn.commit()

    assert updated["status"] == "awaiting_approval"
    assert updated["retry_count"] == 0
    assert updated["last_error"] == "approval required"


def test_non_running_action_rejects_awaiting_approval_transition(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.5.0.62", "block_ip")
    conn.commit()

    with pytest.raises(QueueTransitionError):
        mark_action_awaiting_approval(conn, row_id, "approval required")


def test_awaiting_approval_can_transition_to_skipped(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.5.0.63", "block_ip")
    conn.commit()
    claim_next_pending_action(conn)
    mark_action_awaiting_approval(conn, row_id, "approval required")
    conn.commit()

    updated = mark_awaiting_approval_skipped(conn, row_id, "approval denied")
    conn.commit()

    assert updated["status"] == "skipped"
    assert updated["retry_count"] == 0
    assert updated["last_error"] == "approval denied"


def test_claim_next_approved_awaiting_action_only_claims_approved(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    approved_row_id = enqueue_response_action(cur, alert_id, "8.8.8.8", "block_ip")
    pending_row_id = enqueue_response_action(cur, alert_id, "1.1.1.1", "block_ip")
    conn.commit()
    for row_id in (approved_row_id, pending_row_id):
        claim_next_pending_action(conn)
        mark_action_awaiting_approval(conn, row_id, "approval required")
        conn.commit()

    user_id = insert_user(cur)
    approval = create_approval_request(conn, queue_id=approved_row_id, action="block_ip")
    approve_request(conn, approval["id"], actor_user_id=user_id)
    create_approval_request(conn, queue_id=pending_row_id, action="block_ip")
    conn.commit()

    claimed = claim_next_approved_awaiting_action(conn)
    conn.commit()

    assert claimed["id"] == approved_row_id
    assert claimed["status"] == "running"
    assert fetch_queue_row(cur, pending_row_id)[4] == "awaiting_approval"


def test_sweep_terminal_approval_queue_rows_empty_queue_returns_empty_list(postgres_db):
    conn, _cur = postgres_db

    assert sweep_terminal_approval_queue_rows(conn) == []


def test_sweep_terminal_approval_queue_rows_ignores_non_awaiting_row(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "8.8.4.1", "block_ip")
    insert_queue_approval(cur, row_id, status="expired")
    conn.commit()

    swept = sweep_terminal_approval_queue_rows(conn)
    conn.commit()

    assert swept == []
    assert fetch_queue_row(cur, row_id)[4] == "pending"


def test_sweep_terminal_approval_queue_rows_ignores_approved_approval(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "8.8.4.2", "block_ip")
    set_queue_status(cur, row_id, "awaiting_approval")
    user_id = insert_user(cur)
    approval = create_approval_request(conn, queue_id=row_id, action="block_ip")
    approve_request(conn, approval["id"], actor_user_id=user_id)
    conn.commit()

    swept = sweep_terminal_approval_queue_rows(conn)
    conn.commit()

    assert swept == []
    assert fetch_queue_row(cur, row_id)[4] == "awaiting_approval"


def test_sweep_terminal_approval_queue_rows_skips_expired_approval(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "8.8.4.3", "block_ip")
    set_queue_status(cur, row_id, "awaiting_approval")
    insert_queue_approval(cur, row_id, status="expired")
    conn.commit()

    swept = sweep_terminal_approval_queue_rows(conn)
    conn.commit()

    assert len(swept) == 1
    assert swept[0]["id"] == row_id
    assert swept[0]["status"] == "skipped"
    assert swept[0]["approval_status"] == "expired"
    assert swept[0]["last_error"] == "approval expired"
    assert fetch_queue_row(cur, row_id)[4] == "skipped"


def test_sweep_terminal_approval_queue_rows_skips_denied_approval(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "8.8.4.4", "block_ip")
    set_queue_status(cur, row_id, "awaiting_approval")
    insert_queue_approval(cur, row_id, status="denied")
    conn.commit()

    swept = sweep_terminal_approval_queue_rows(conn)
    conn.commit()

    assert len(swept) == 1
    assert swept[0]["id"] == row_id
    assert swept[0]["status"] == "skipped"
    assert swept[0]["approval_status"] == "denied"
    assert swept[0]["last_error"] == "approval denied"
    assert fetch_queue_row(cur, row_id)[4] == "skipped"


def test_sweep_terminal_approval_queue_rows_does_not_increment_retry_count(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "8.8.4.5", "block_ip")
    set_queue_status(cur, row_id, "awaiting_approval", retry_count=1)
    insert_queue_approval(cur, row_id, status="expired")
    conn.commit()

    swept = sweep_terminal_approval_queue_rows(conn)
    conn.commit()

    assert swept[0]["retry_count"] == 1
    assert fetch_queue_row(cur, row_id)[5] == 1


def test_sweep_terminal_approval_queue_rows_sweeps_multiple_rows(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_ids = []
    for index in range(3):
        row_id = enqueue_response_action(cur, alert_id, f"8.8.5.{index + 1}", "block_ip")
        set_queue_status(cur, row_id, "awaiting_approval")
        insert_queue_approval(cur, row_id, status="expired")
        row_ids.append(row_id)
    conn.commit()

    swept = sweep_terminal_approval_queue_rows(conn)
    conn.commit()

    assert [row["id"] for row in swept] == row_ids
    assert all(row["status"] == "skipped" for row in swept)


def test_sweep_terminal_approval_queue_rows_respects_limit(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_ids = []
    for index in range(5):
        row_id = enqueue_response_action(cur, alert_id, f"8.8.6.{index + 1}", "block_ip")
        set_queue_status(cur, row_id, "awaiting_approval")
        insert_queue_approval(cur, row_id, status="expired")
        row_ids.append(row_id)
    conn.commit()

    swept = sweep_terminal_approval_queue_rows(conn, limit=2)
    conn.commit()

    assert [row["id"] for row in swept] == row_ids[:2]
    remaining = [fetch_queue_row(cur, row_id)[4] for row_id in row_ids]
    assert remaining.count("skipped") == 2
    assert remaining.count("awaiting_approval") == 3


def test_sweep_terminal_approval_queue_rows_only_sweeps_terminal_approvals(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    expired_row_id = enqueue_response_action(cur, alert_id, "8.8.7.1", "block_ip")
    approved_row_id = enqueue_response_action(cur, alert_id, "8.8.7.2", "block_ip")
    set_queue_status(cur, expired_row_id, "awaiting_approval")
    set_queue_status(cur, approved_row_id, "awaiting_approval")
    insert_queue_approval(cur, expired_row_id, status="expired")
    user_id = insert_user(cur)
    approval = create_approval_request(conn, queue_id=approved_row_id, action="block_ip")
    approve_request(conn, approval["id"], actor_user_id=user_id)
    conn.commit()

    swept = sweep_terminal_approval_queue_rows(conn)
    conn.commit()

    assert [row["id"] for row in swept] == [expired_row_id]
    assert fetch_queue_row(cur, expired_row_id)[4] == "skipped"
    assert fetch_queue_row(cur, approved_row_id)[4] == "awaiting_approval"


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


def test_process_next_action_default_simulation_executor_logs_executed(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "8.8.8.8", "monitor")
    conn.commit()

    result = process_next_action(conn)

    assert result["queue_id"] == row_id
    assert result["outcome"] == "success"
    assert result["new_status"] == "success"
    assert result["message"] == f"Monitoring only - no action taken for queue_id={row_id}"
    logs = fetch_action_logs(cur, alert_id)
    assert len(logs) == 1
    assert logs[0][3] == "executed"
    assert logs[0][4] == f"Monitoring only - no action taken for queue_id={row_id}"


def test_process_next_action_writes_running_event_for_linked_queue_row(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "8.8.8.8", "monitor")
    decision_id = insert_minimal_decision(cur, "soar-running-linked-001")
    conn.commit()
    set_queue_linkage(
        conn,
        row_id,
        decision_id=decision_id,
        soar_correlation_id="soar-running-linked-001",
    )
    conn.commit()

    result = process_next_action(conn, executor=SimulationExecutor())

    assert result["queue_id"] == row_id
    assert result["outcome"] == "success"
    events = fetch_outcome_events(cur, row_id)
    assert events[:1] == [
        (
            "running",
            "simulation",
            "running",
            True,
            False,
            False,
            "queue_worker",
            "simulation_mode",
            f"queue-running-{row_id}-0",
        )
    ]
    assert events[1][0:3] == ("succeeded", "simulation", "succeeded")


def test_running_event_idempotency_prevents_duplicate_for_same_attempt(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "8.8.8.8", "monitor")
    decision_id = insert_minimal_decision(cur, "soar-running-idempotent-001")
    conn.commit()
    set_queue_linkage(
        conn,
        row_id,
        decision_id=decision_id,
        soar_correlation_id="soar-running-idempotent-001",
    )
    conn.commit()
    claimed = claim_next_pending_action(conn)

    first = _append_running_outcome_event(conn, claimed)
    second = _append_running_outcome_event(conn, claimed)
    conn.commit()

    assert first["id"] == second["id"]
    events = fetch_outcome_events(cur, row_id)
    assert len(events) == 1
    assert events[0][8] == f"queue-running-{row_id}-0"


def test_running_event_retry_count_distinguishes_retry_attempt(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "8.8.8.8", "monitor", max_retries=2)
    decision_id = insert_minimal_decision(cur, "soar-running-retry-001")
    conn.commit()
    set_queue_linkage(
        conn,
        row_id,
        decision_id=decision_id,
        soar_correlation_id="soar-running-retry-001",
    )
    conn.commit()
    first_claim = claim_next_pending_action(conn)
    _append_running_outcome_event(conn, first_claim)
    record_action_failure(conn, row_id, "temporary failure", retryable=True)
    conn.commit()

    second_claim = claim_next_pending_action(conn)
    _append_running_outcome_event(conn, second_claim)
    conn.commit()

    events = fetch_outcome_events(cur, row_id)
    assert [event[8] for event in events] == [
        f"queue-running-{row_id}-0",
        f"queue-running-{row_id}-1",
    ]


def test_unlinked_legacy_queue_row_processes_without_running_event(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "8.8.8.8", "monitor")
    conn.commit()

    result = process_next_action(conn, executor=SimulationExecutor())

    assert result["queue_id"] == row_id
    assert result["outcome"] == "success"
    assert fetch_queue_row(cur, row_id)[4] == "success"
    assert fetch_outcome_events(cur, row_id) == []


def test_running_event_write_failure_does_not_break_legacy_worker(
    postgres_db, monkeypatch, caplog
):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "8.8.8.8", "monitor")
    decision_id = insert_minimal_decision(cur, "soar-running-failure-001")
    conn.commit()
    set_queue_linkage(
        conn,
        row_id,
        decision_id=decision_id,
        soar_correlation_id="soar-running-failure-001",
    )
    conn.commit()

    def fail_append(*_args, **_kwargs):
        raise RuntimeError("canonical writer unavailable")

    monkeypatch.setattr("engines.soar_action_worker.append_outcome_event", fail_append)

    with caplog.at_level("ERROR"):
        result = process_next_action(conn, executor=SimulationExecutor())

    assert result["queue_id"] == row_id
    assert result["outcome"] == "success"
    assert fetch_queue_row(cur, row_id)[4] == "success"
    assert len(fetch_action_logs(cur, alert_id)) == 1
    assert fetch_outcome_events(cur, row_id) == []
    assert "Failed to append canonical running outcome" in caplog.text


def test_process_next_action_success_writes_linked_log_and_succeeded_event(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "8.8.8.8", "monitor")
    decision_id = link_queue_to_decision(
        conn, cur, row_id, "soar-worker-success-linked-001"
    )

    result = process_next_action(conn, executor=SimulationExecutor())

    assert result["outcome"] == "success"
    logs = fetch_action_logs_with_links(cur, alert_id)
    assert len(logs) == 1
    log_id = logs[0][0]
    assert logs[0][4] == "executed"
    assert logs[0][6] == decision_id
    assert logs[0][7] == "soar-worker-success-linked-001"
    events = fetch_detailed_outcome_events(cur, row_id)
    assert [event[0] for event in events] == ["running", "succeeded"]
    succeeded = events[1]
    assert succeeded[1:6] == (
        "succeeded",
        "simulation_mode",
        f"queue-succeeded-{row_id}-0",
        log_id,
        None,
    )
    assert succeeded[7:] == (True, False, False)


def test_process_next_action_skipped_writes_skipped_event(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.5.0.11", "monitor")
    link_queue_to_decision(conn, cur, row_id, "soar-worker-skipped-001")

    def skip(_row):
        raise SkippedAction("policy disabled", code="policy_disabled")

    result = process_next_action(conn, executor=skip)

    assert result["outcome"] == "skipped"
    log_id = fetch_action_logs_with_links(cur, alert_id)[0][0]
    events = fetch_detailed_outcome_events(cur, row_id)
    assert [event[0] for event in events] == ["running", "skipped"]
    skipped = events[1]
    assert skipped[1:5] == (
        "skipped",
        "policy_blocked",
        f"queue-skipped-{row_id}-0",
        log_id,
    )


def test_process_next_action_failed_writes_failed_event(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "8.8.8.8", "monitor")
    link_queue_to_decision(conn, cur, row_id, "soar-worker-failed-001")

    def fail(_row):
        raise Exception("unexpected failure token=secret-value")

    result = process_next_action(conn, executor=fail)

    assert result["outcome"] == "failed"
    log_id = fetch_action_logs_with_links(cur, alert_id)[0][0]
    events = fetch_detailed_outcome_events(cur, row_id)
    assert [event[0] for event in events] == ["running", "failed"]
    failed = events[1]
    assert failed[1:5] == (
        "failed",
        "provider_error",
        f"queue-failed-{row_id}-1",
        log_id,
    )
    assert "secret-value" not in failed[6]


def test_process_next_action_retry_writes_failed_attempt_and_requeued_events(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.5.0.10", "monitor", max_retries=2)
    link_queue_to_decision(conn, cur, row_id, "soar-worker-retry-001")

    def fail_retryable(_row):
        raise RetryableActionError("adapter unavailable", code="adapter_unavailable")

    result = process_next_action(conn, executor=fail_retryable)

    assert result["outcome"] == "requeued"
    assert fetch_action_logs(cur, alert_id) == []
    events = fetch_detailed_outcome_events(cur, row_id)
    assert [event[0] for event in events] == [
        "running",
        "failed_attempt",
        "requeued",
    ]
    assert events[1][1:4] == (
        "failed",
        "adapter_unavailable",
        f"queue-failed_attempt-{row_id}-1",
    )
    assert events[2][1:4] == (
        "queued",
        "adapter_unavailable",
        f"queue-requeued-{row_id}-1",
    )


def test_process_next_action_awaiting_approval_writes_awaiting_event(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "8.8.8.8", "block_ip")
    link_queue_to_decision(conn, cur, row_id, "soar-worker-awaiting-001")
    executor = Mock(return_value={"code": "ok", "message": "should not run"})

    result = process_next_action(conn, executor=executor)

    assert result["outcome"] == "awaiting_approval"
    events = fetch_detailed_outcome_events(cur, row_id)
    assert [event[0] for event in events] == ["running", "awaiting_approval"]
    awaiting = events[1]
    assert awaiting[1:4] == (
        "awaiting_approval",
        "approval_required",
        f"queue-awaiting_approval-{row_id}-0",
    )
    assert awaiting[5] is not None
    assert awaiting[7:] == (False, False, False)
    executor.assert_not_called()


def test_process_next_action_denied_approval_writes_blocked_event(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "8.8.8.8", "block_ip")
    link_queue_to_decision(conn, cur, row_id, "soar-worker-blocked-001")
    user_id = insert_user(cur)
    approval = create_approval_request(conn, queue_id=row_id, action="block_ip")
    deny_request(conn, approval["id"], actor_user_id=user_id, decision_comment="too risky")
    conn.commit()
    executor = Mock(return_value={"code": "ok", "message": "should not run"})

    result = process_next_action(conn, executor=executor)

    assert result["outcome"] == "skipped"
    log_id = fetch_action_logs_with_links(cur, alert_id)[0][0]
    events = fetch_detailed_outcome_events(cur, row_id)
    assert [event[0] for event in events] == ["running", "blocked"]
    blocked = events[1]
    assert blocked[1:6] == (
        "blocked",
        "approval_denied",
        f"queue-blocked-{row_id}-0",
        log_id,
        approval["id"],
    )
    assert blocked[7:] == (False, False, False)
    executor.assert_not_called()


def test_process_next_action_block_ip_creates_approval_and_waits(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "8.8.8.8", "block_ip")
    conn.commit()
    executor = Mock(return_value={"code": "ok", "message": "should not run"})

    result = process_next_action(conn, executor=executor)

    assert result["queue_id"] == row_id
    assert result["outcome"] == "awaiting_approval"
    assert result["new_status"] == "awaiting_approval"
    assert result["retry_count"] == 0
    assert fetch_queue_row(cur, row_id)[4] == "awaiting_approval"
    assert count_approval_requests(cur, row_id) == 1
    executor.assert_not_called()
    assert fetch_action_logs(cur, alert_id) == []


def test_process_next_action_protected_exact_block_ip_skips_without_approval(
    postgres_db, monkeypatch
):
    conn, cur = postgres_db
    monkeypatch.setenv("SOAR_PROTECTED_IPS", "8.8.8.8")
    alert_id = insert_minimal_alert(cur, source_ip="8.8.8.8")
    row_id = enqueue_response_action(cur, alert_id, "8.8.8.8", "block_ip")
    conn.commit()
    executor = Mock(return_value={"code": "ok", "message": "should not run"})

    result = process_next_action(conn, executor=executor)

    assert result["queue_id"] == row_id
    assert result["outcome"] == "skipped"
    assert result["new_status"] == "skipped"
    assert result["error_code"] == "protected_target"
    assert result["retry_count"] == 0
    assert count_approval_requests(cur, row_id) == 0
    assert fetch_queue_row(cur, row_id)[4] == "skipped"
    executor.assert_not_called()


def test_process_next_action_protected_cidr_block_ip_skips_without_approval(
    postgres_db, monkeypatch
):
    conn, cur = postgres_db
    monkeypatch.setenv("SOAR_PROTECTED_IPS", "8.8.8.0/24")
    alert_id = insert_minimal_alert(cur, source_ip="8.8.8.9")
    row_id = enqueue_response_action(cur, alert_id, "8.8.8.9", "block_ip")
    conn.commit()
    executor = Mock(return_value={"code": "ok", "message": "should not run"})

    result = process_next_action(conn, executor=executor)

    assert result["queue_id"] == row_id
    assert result["outcome"] == "skipped"
    assert result["new_status"] == "skipped"
    assert result["error_code"] == "protected_target"
    assert result["retry_count"] == 0
    assert count_approval_requests(cur, row_id) == 0
    assert fetch_queue_row(cur, row_id)[4] == "skipped"
    executor.assert_not_called()


def test_process_next_action_invalid_protected_config_skips_safely(
    postgres_db, monkeypatch
):
    conn, cur = postgres_db
    monkeypatch.setenv("SOAR_PROTECTED_IPS", "not-an-ip")
    alert_id = insert_minimal_alert(cur, source_ip="8.8.8.8")
    row_id = enqueue_response_action(cur, alert_id, "8.8.8.8", "block_ip")
    conn.commit()
    executor = Mock(return_value={"code": "ok", "message": "should not run"})

    result = process_next_action(conn, executor=executor)

    assert result["queue_id"] == row_id
    assert result["outcome"] == "skipped"
    assert result["new_status"] == "skipped"
    assert result["error_code"] == "protected_target_config_invalid"
    assert result["retry_count"] == 0
    assert count_approval_requests(cur, row_id) == 0
    assert fetch_queue_row(cur, row_id)[4] == "skipped"
    executor.assert_not_called()


def test_process_next_action_non_protected_block_ip_still_creates_approval(
    postgres_db, monkeypatch
):
    conn, cur = postgres_db
    monkeypatch.setenv("SOAR_PROTECTED_IPS", "1.1.1.1")
    alert_id = insert_minimal_alert(cur, source_ip="8.8.8.8")
    row_id = enqueue_response_action(cur, alert_id, "8.8.8.8", "block_ip")
    conn.commit()
    executor = Mock(return_value={"code": "ok", "message": "should not run"})

    result = process_next_action(conn, executor=executor)

    assert result["queue_id"] == row_id
    assert result["outcome"] == "awaiting_approval"
    assert result["new_status"] == "awaiting_approval"
    assert result["retry_count"] == 0
    assert count_approval_requests(cur, row_id) == 1
    assert fetch_queue_row(cur, row_id)[4] == "awaiting_approval"
    executor.assert_not_called()


def test_process_next_action_non_block_action_unchanged_with_protected_targets(
    postgres_db, monkeypatch
):
    conn, cur = postgres_db
    monkeypatch.setenv("SOAR_PROTECTED_IPS", "8.8.8.8,8.8.8.0/24")
    alert_id = insert_minimal_alert(cur, source_ip="9.9.9.9")
    row_id = enqueue_response_action(cur, alert_id, "9.9.9.9", "monitor")
    conn.commit()

    result = process_next_action(conn, executor=SimulationExecutor())

    assert result["queue_id"] == row_id
    assert result["outcome"] == "success"
    assert result["new_status"] == "success"
    assert count_approval_requests(cur, row_id) == 0
    assert fetch_queue_row(cur, row_id)[4] == "success"


def test_process_next_action_awaiting_approval_does_not_duplicate_request(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "8.8.8.8", "block_ip")
    conn.commit()

    first = process_next_action(conn, executor=Mock())
    second = process_next_action(conn, executor=Mock())

    assert first["outcome"] == "awaiting_approval"
    assert second is None
    assert count_approval_requests(cur, row_id) == 1
    assert fetch_queue_row(cur, row_id)[4] == "awaiting_approval"


def test_active_queue_action_approval_requests_are_unique(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "8.8.8.8", "block_ip")
    conn.commit()

    create_approval_request(conn, queue_id=row_id, action="block_ip")
    with pytest.raises(psycopg2.errors.UniqueViolation):
        create_approval_request(conn, queue_id=row_id, action="block_ip")
    conn.rollback()


def test_process_next_action_approved_block_ip_executes(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "8.8.8.8", "block_ip")
    user_id = insert_user(cur)
    approval = create_approval_request(conn, queue_id=row_id, action="block_ip")
    approve_request(conn, approval["id"], actor_user_id=user_id)
    conn.commit()

    result = process_next_action(conn, executor=SimulationExecutor())

    assert result["queue_id"] == row_id
    assert result["outcome"] == "success"
    assert result["new_status"] == "success"
    assert fetch_queue_row(cur, row_id)[4] == "success"
    assert fetch_action_logs(cur, alert_id)[0][3] == "executed"


def test_process_next_action_denied_block_ip_skips_without_executor(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "8.8.8.8", "block_ip")
    user_id = insert_user(cur)
    approval = create_approval_request(conn, queue_id=row_id, action="block_ip")
    deny_request(conn, approval["id"], actor_user_id=user_id, decision_comment="too risky")
    conn.commit()
    executor = Mock(return_value={"code": "ok", "message": "should not run"})

    result = process_next_action(conn, executor=executor)

    assert result["outcome"] == "skipped"
    assert result["new_status"] == "skipped"
    assert result["error_code"] == "approval_denied"
    assert result["retry_count"] == 0
    assert fetch_queue_row(cur, row_id)[4] == "skipped"
    executor.assert_not_called()


def test_process_next_action_expired_block_ip_skips_without_executor(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "8.8.8.8", "block_ip")
    create_approval_request(
        conn,
        queue_id=row_id,
        action="block_ip",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    conn.commit()
    executor = Mock(return_value={"code": "ok", "message": "should not run"})

    result = process_next_action(conn, executor=executor)

    assert result["outcome"] == "skipped"
    assert result["new_status"] == "skipped"
    assert result["error_code"] == "approval_expired"
    assert result["retry_count"] == 0
    assert fetch_queue_row(cur, row_id)[4] == "skipped"
    executor.assert_not_called()


def test_process_next_action_retryable_executor_requeues(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.5.0.10", "monitor", max_retries=2)
    conn.commit()

    def fail_retryable(_row):
        raise RetryableActionError("adapter unavailable", code="adapter_unavailable")

    result = process_next_action(conn, executor=fail_retryable)

    assert result["queue_id"] == row_id
    assert result["outcome"] == "requeued"
    assert result["new_status"] == "pending"
    assert result["retryable"] is True
    assert result["retry_count"] == 1
    assert fetch_action_logs(cur, alert_id) == []


def test_process_next_action_skip_executor_marks_skipped(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.5.0.11", "monitor")
    conn.commit()

    def skip(_row):
        raise SkippedAction("policy disabled", code="policy_disabled")

    result = process_next_action(conn, executor=skip)

    assert result["queue_id"] == row_id
    assert result["outcome"] == "skipped"
    assert result["new_status"] == "skipped"
    assert result["error_code"] == "policy_disabled"
    logs = fetch_action_logs(cur, alert_id)
    assert len(logs) == 1
    assert logs[0][3] == "skipped"
    assert logs[0][4] == "policy disabled"


def test_process_next_action_non_retryable_failure_logs_failed(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "8.8.8.8", "monitor")
    conn.commit()

    def fail(_row):
        raise Exception("unexpected failure")

    result = process_next_action(conn, executor=fail)

    assert result["queue_id"] == row_id
    assert result["outcome"] == "failed"
    assert result["new_status"] == "failed"
    logs = fetch_action_logs(cur, alert_id)
    assert len(logs) == 1
    assert logs[0][3] == "failed"
    assert logs[0][4] == "unexpected failure"


def test_process_next_action_retryable_failure_exhausted_logs_failed(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "8.8.8.8", "monitor", max_retries=1)
    conn.commit()

    def fail_retryable(_row):
        raise RetryableActionError("adapter timeout", code="adapter_timeout")

    result = process_next_action(conn, executor=fail_retryable)

    assert result["queue_id"] == row_id
    assert result["outcome"] == "failed"
    assert result["new_status"] == "failed"
    assert result["retryable"] is False
    logs = fetch_action_logs(cur, alert_id)
    assert len(logs) == 1
    assert logs[0][3] == "failed"
    assert logs[0][4] == "adapter timeout"


def test_process_next_action_single_terminal_execution_writes_one_log_row(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "8.8.8.8", "monitor")
    conn.commit()

    result = process_next_action(conn, executor=SimulationExecutor())
    second_result = process_next_action(conn, executor=SimulationExecutor())

    assert result["queue_id"] == row_id
    assert result["outcome"] == "success"
    assert second_result is None
    assert len(fetch_action_logs(cur, alert_id)) == 1


def test_manual_execute_response_action_logging_unaffected_by_worker_logging(postgres_db):
    conn, cur = postgres_db
    manual_alert_id = insert_minimal_alert(cur, source_ip="8.8.8.8")
    worker_alert_id = insert_minimal_alert(cur, source_ip="8.8.4.4")

    with siem_backend.app.app_context():
        execute_response_action(cur, manual_alert_id, "8.8.8.8", "monitor")
    conn.commit()

    row_id = enqueue_response_action(cur, worker_alert_id, "8.8.4.4", "monitor")
    conn.commit()

    result = process_next_action(conn, executor=SimulationExecutor())

    assert result["queue_id"] == row_id
    assert len(fetch_action_logs(cur, manual_alert_id)) == 1
    assert len(fetch_action_logs(cur, worker_alert_id)) == 1
    assert fetch_action_logs(cur, manual_alert_id)[0][3] == "executed"
    assert fetch_action_logs(cur, worker_alert_id)[0][3] == "executed"


def test_process_next_action_deleted_alert_logs_null_alert_id(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur, source_ip="8.8.8.8")
    row_id = enqueue_response_action(cur, alert_id, "8.8.8.8", "monitor")
    conn.commit()
    cur.execute("DELETE FROM alerts WHERE id = %s", (alert_id,))
    conn.commit()

    result = process_next_action(conn, executor=SimulationExecutor())

    assert result["queue_id"] == row_id
    assert result["outcome"] == "success"
    logs = fetch_action_logs(cur)
    assert len(logs) == 1
    assert logs[0][0] is None
    assert logs[0][3] == "executed"


def test_process_next_action_simulation_executor_block_ip_success(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "1.1.1.1", "block_ip")
    user_id = insert_user(cur, "block-approver")
    approval = create_approval_request(conn, queue_id=row_id, action="block_ip")
    approve_request(conn, approval["id"], actor_user_id=user_id)
    conn.commit()

    result = process_next_action(conn, executor=SimulationExecutor())

    assert result["queue_id"] == row_id
    assert result["outcome"] == "success"
    assert fetch_queue_row(cur, row_id)[4] == "success"


def test_process_next_action_simulation_executor_flag_high_priority_success(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.5.0.12", "flag_high_priority")
    conn.commit()

    result = process_next_action(conn, executor=SimulationExecutor())

    assert result["queue_id"] == row_id
    assert result["outcome"] == "success"
    assert fetch_queue_row(cur, row_id)[4] == "success"


def test_process_next_action_simulation_executor_monitor_success(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.5.0.13", "monitor")
    conn.commit()

    result = process_next_action(conn, executor=SimulationExecutor())

    assert result["queue_id"] == row_id
    assert result["outcome"] == "success"
    assert fetch_queue_row(cur, row_id)[4] == "success"


def test_process_next_action_simulation_executor_private_block_ip_skipped(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.5.0.14", "block_ip")
    user_id = insert_user(cur, "private-block-approver")
    approval = create_approval_request(conn, queue_id=row_id, action="block_ip")
    approve_request(conn, approval["id"], actor_user_id=user_id)
    conn.commit()

    result = process_next_action(conn, executor=SimulationExecutor())

    assert result["queue_id"] == row_id
    assert result["outcome"] == "skipped"
    assert result["new_status"] == "skipped"
    assert result["error_code"] == "validation_private_ip"
    assert fetch_queue_row(cur, row_id)[4] == "skipped"


def test_process_next_action_simulation_executor_unknown_action_skipped(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "8.8.4.4", "unknown_action")
    conn.commit()

    result = process_next_action(conn, executor=SimulationExecutor())

    assert result["queue_id"] == row_id
    assert result["outcome"] == "skipped"
    assert result["error_code"] == "unsupported_action"
    assert fetch_queue_row(cur, row_id)[4] == "skipped"


@pytest.mark.parametrize(
    "executor_result",
    [
        {},
        {"code": "missing_message"},
        {"message": "missing code"},
        {"code": "", "message": "empty code"},
        {"code": "empty_message", "message": ""},
    ],
)
def test_process_next_action_invalid_executor_result_fails_terminally(postgres_db, executor_result):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.5.0.15", "monitor")
    conn.commit()

    result = process_next_action(conn, executor=lambda _row: executor_result)

    assert result["queue_id"] == row_id
    assert result["outcome"] == "failed"
    assert result["new_status"] == "failed"
    assert result["retryable"] is False
    assert fetch_queue_row(cur, row_id)[4] == "failed"


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


def test_get_queue_status_counts_empty_queue_returns_empty_dict(postgres_db):
    conn, _cur = postgres_db
    assert get_queue_status_counts(conn) == {}


def test_get_queue_status_counts_pending_only(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur, source_ip="8.8.8.8")
    enqueue_response_action(cur, alert_id, "8.8.8.8", "block_ip")
    enqueue_response_action(cur, alert_id, "8.8.8.8", "monitor")
    conn.commit()

    counts = get_queue_status_counts(conn)
    assert counts == {"pending": 2}


def test_get_queue_status_counts_mixed_statuses_without_mutation(postgres_db):
    conn, cur = postgres_db
    a1 = insert_minimal_alert(cur, source_ip="8.8.8.8")
    a2 = insert_minimal_alert(cur, source_ip="1.1.1.1")
    a3 = insert_minimal_alert(cur, source_ip="9.9.9.9")
    q1 = enqueue_response_action(cur, a1, "8.8.8.8", "block_ip")
    q2 = enqueue_response_action(cur, a2, "1.1.1.1", "block_ip")
    q3 = enqueue_response_action(cur, a3, "9.9.9.9", "block_ip")
    conn.commit()

    cur.execute(
        "UPDATE response_actions_queue SET status = 'success' WHERE id = %s",
        (q2,),
    )
    cur.execute("UPDATE response_actions_queue SET status = 'failed' WHERE id = %s", (q3,))
    cur.execute("UPDATE response_actions_queue SET status = 'awaiting_approval' WHERE id = %s", (q1,))
    conn.commit()
    cur.execute("SELECT id, status FROM response_actions_queue ORDER BY id")
    before = cur.fetchall()

    counts = get_queue_status_counts(conn)
    cur.execute("SELECT id, status FROM response_actions_queue ORDER BY id")
    after = cur.fetchall()

    assert counts == {"awaiting_approval": 1, "success": 1, "failed": 1}
    assert before == after


# ---------------------------------------------------------------------------
# Phase 4 Slice 2: canonical linkage field tests
# ---------------------------------------------------------------------------

def insert_minimal_decision(cur, correlation_id="soar-test-001"):
    cur.execute(
        """
        INSERT INTO soar_response_decisions (
            soar_correlation_id, selected_action, decision_source, outcome_summary
        )
        VALUES (%s, 'block_ip', 'detection_default', 'test decision')
        RETURNING id
        """,
        (correlation_id,),
    )
    return cur.fetchone()[0]


def link_queue_to_decision(conn, cur, row_id, correlation_id):
    decision_id = insert_minimal_decision(cur, correlation_id)
    conn.commit()
    set_queue_linkage(
        conn,
        row_id,
        decision_id=decision_id,
        soar_correlation_id=correlation_id,
    )
    conn.commit()
    return decision_id


def test_queue_row_returns_null_linkage_by_default(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.10.0.1", "block_ip")
    conn.commit()

    row = get_queue_action(conn, row_id)

    assert row["decision_id"] is None
    assert row["soar_correlation_id"] is None


def test_claim_next_pending_action_returns_linkage_fields(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    enqueue_response_action(cur, alert_id, "10.10.0.2", "monitor")
    conn.commit()

    claimed = claim_next_pending_action(conn)
    conn.commit()

    assert "decision_id" in claimed
    assert "soar_correlation_id" in claimed
    assert claimed["decision_id"] is None
    assert claimed["soar_correlation_id"] is None


def test_set_queue_linkage_persists_decision_id_and_correlation_id(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.10.0.3", "monitor")
    decision_id = insert_minimal_decision(cur, "soar-linkage-test-001")
    conn.commit()

    updated = set_queue_linkage(
        conn,
        row_id,
        decision_id=decision_id,
        soar_correlation_id="soar-linkage-test-001",
    )
    conn.commit()

    assert updated["id"] == row_id
    assert updated["decision_id"] == decision_id
    assert updated["soar_correlation_id"] == "soar-linkage-test-001"
    assert updated["status"] == "pending"


def test_set_queue_linkage_partial_update_correlation_id_only(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.10.0.4", "monitor")
    conn.commit()

    updated = set_queue_linkage(conn, row_id, soar_correlation_id="soar-partial-001")
    conn.commit()

    assert updated["soar_correlation_id"] == "soar-partial-001"
    assert updated["decision_id"] is None
    assert updated["status"] == "pending"


def test_set_queue_linkage_partial_update_decision_id_only(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.10.0.5", "monitor")
    decision_id = insert_minimal_decision(cur, "soar-partial-dec-001")
    conn.commit()

    updated = set_queue_linkage(conn, row_id, decision_id=decision_id)
    conn.commit()

    assert updated["decision_id"] == decision_id
    assert updated["soar_correlation_id"] is None
    assert updated["status"] == "pending"


def test_set_queue_linkage_no_args_returns_row_unchanged(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.10.0.6", "monitor")
    conn.commit()

    result = set_queue_linkage(conn, row_id)

    assert result["id"] == row_id
    assert result["decision_id"] is None
    assert result["soar_correlation_id"] is None


def test_set_queue_linkage_does_not_change_status(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    row_id = enqueue_response_action(cur, alert_id, "10.10.0.7", "monitor")
    conn.commit()
    claim_next_pending_action(conn)
    conn.commit()

    updated = set_queue_linkage(conn, row_id, soar_correlation_id="soar-status-check-001")
    conn.commit()

    assert updated["status"] == "running"
    assert updated["soar_correlation_id"] == "soar-status-check-001"


def test_duplicate_enqueue_unaffected_by_linkage(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    decision_id = insert_minimal_decision(cur, "soar-dup-test-001")

    first_id = enqueue_response_action(cur, alert_id, "10.10.0.8", "block_ip")
    set_queue_linkage(conn, first_id, decision_id=decision_id, soar_correlation_id="soar-dup-test-001")
    conn.commit()

    duplicate_id = enqueue_response_action(cur, alert_id, "10.10.0.8", "block_ip")
    conn.commit()

    assert first_id is not None
    assert duplicate_id is None
    assert count_queue_rows(cur) == 1

    row = get_queue_action(conn, first_id)
    assert row["decision_id"] == decision_id
    assert row["soar_correlation_id"] == "soar-dup-test-001"
