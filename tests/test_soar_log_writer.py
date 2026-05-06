import pytest

from engines.soar_log_writer import log_response_action


def _fetch_log_rows(cur):
    cur.execute(
        """
        SELECT alert_id, host(source_ip), action, status, details, executed_at
        FROM response_actions_log
        ORDER BY id
        """
    )
    return cur.fetchall()


def test_log_response_action_executed_status_writes_row(postgres_db):
    conn, cur = postgres_db
    row = {"alert_id": None, "source_ip": "8.8.8.8", "action": "block_ip"}

    log_response_action(conn, row, "executed", "simulated block")
    conn.commit()

    rows = _fetch_log_rows(cur)
    assert len(rows) == 1
    assert rows[0][0] is None
    assert rows[0][1] == "8.8.8.8"
    assert rows[0][2] == "block_ip"
    assert rows[0][3] == "executed"
    assert rows[0][4] == "simulated block"
    assert rows[0][5] is not None


def test_log_response_action_skipped_status_writes_row(postgres_db):
    conn, cur = postgres_db
    row = {"alert_id": None, "source_ip": "8.8.4.4", "action": "block_ip"}

    log_response_action(conn, row, "skipped", "private IP rejected")
    conn.commit()

    rows = _fetch_log_rows(cur)
    assert len(rows) == 1
    assert rows[0][3] == "skipped"
    assert rows[0][4] == "private IP rejected"


def test_log_response_action_failed_status_writes_row(postgres_db):
    conn, cur = postgres_db
    row = {"alert_id": None, "source_ip": "1.1.1.1", "action": "monitor"}

    log_response_action(conn, row, "failed", "connection timeout")
    conn.commit()

    rows = _fetch_log_rows(cur)
    assert len(rows) == 1
    assert rows[0][3] == "failed"
    assert rows[0][4] == "connection timeout"


def test_log_response_action_writes_null_alert_id(postgres_db):
    conn, cur = postgres_db
    row = {"alert_id": None, "source_ip": "8.8.8.8", "action": "monitor"}

    log_response_action(conn, row, "executed", "monitor complete")
    conn.commit()

    rows = _fetch_log_rows(cur)
    assert len(rows) == 1
    assert rows[0][0] is None


def test_log_response_action_writes_null_source_ip(postgres_db):
    conn, cur = postgres_db
    row = {"alert_id": None, "source_ip": None, "action": "flag_high_priority"}

    log_response_action(conn, row, "executed", "flag complete")
    conn.commit()

    rows = _fetch_log_rows(cur)
    assert len(rows) == 1
    assert rows[0][1] is None


def test_log_response_action_invalid_status_raises_before_insert(postgres_db):
    conn, cur = postgres_db
    row = {"alert_id": None, "source_ip": "8.8.8.8", "action": "monitor"}

    with pytest.raises(ValueError):
        log_response_action(conn, row, "unknown_status", "bad")

    conn.commit()
    assert _fetch_log_rows(cur) == []


def test_log_response_action_does_not_commit(postgres_db):
    conn, cur = postgres_db
    row = {"alert_id": None, "source_ip": "8.8.8.8", "action": "monitor"}

    log_response_action(conn, row, "executed", "will roll back")
    conn.rollback()

    assert _fetch_log_rows(cur) == []
