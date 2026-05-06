import pytest

from core.ip_helpers import _compute_idempotency_key, enqueue_response_action


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
