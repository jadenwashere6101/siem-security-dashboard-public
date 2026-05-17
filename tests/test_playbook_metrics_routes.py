"""
Read-only playbook execution metrics API (GET /metrics/playbooks).
"""

import hashlib
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

from core import approval_store
from core import playbook_store
from routes.metrics_routes import KNOWN_EXECUTION_STATUSES, RECENT_WINDOW_HOURS

ADMIN_USER = "testadmin"
ADMIN_PASS = "testpassword123!"


class _RouteSafeConnection:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return self._conn.cursor()

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return None


@contextmanager
def _patched_metrics_db(conn):
    wrapper = _RouteSafeConnection(conn)
    with patch("routes.metrics_routes.get_db_connection", return_value=wrapper), patch(
        "core.audit_helpers.get_db_connection", return_value=wrapper
    ):
        yield


def _login_super_admin(client):
    resp = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert resp.status_code == 200


def _fake_user(username, password, role):
    return {
        "username": username,
        "password_hash": generate_password_hash(password, method="pbkdf2:sha256"),
        "role": role,
        "is_active": True,
    }


def _valid_steps():
    return [{"action": "monitor", "params": {}}]


def _insert_queue_row(cur, alert_id, source_ip="10.0.0.50", action="block_ip", status="pending"):
    idem = hashlib.sha256(f"{action}:{source_ip}:{alert_id}".encode()).hexdigest()
    cur.execute(
        """
        INSERT INTO response_actions_queue
        (idempotency_key, alert_id, source_ip, action, status)
        VALUES (%s, %s, %s::inet, %s, %s)
        RETURNING id
        """,
        (idem, alert_id, source_ip, action, status),
    )
    return cur.fetchone()[0]


def _insert_response_log(cur, alert_id):
    cur.execute(
        """
        INSERT INTO response_actions_log (alert_id, action, status, details)
        VALUES (%s, 'monitor', 'simulated', 'test')
        RETURNING id
        """,
        (alert_id,),
    )
    return cur.fetchone()[0]


def _insert_alert(cur, source_ip="10.0.0.99"):
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message)
        VALUES ('test_alert', 'LOW', %s::inet, 'msg')
        RETURNING id
        """,
        (source_ip,),
    )
    return cur.fetchone()[0]


# --- Auth ---


def test_metrics_playbooks_without_session_returns_401(client):
    assert client.get("/metrics/playbooks").status_code == 401


def test_metrics_playbooks_viewer_forbidden(client, mock_db):
    fake = _fake_user("metrics_viewer", "vpass", "viewer")
    with patch("routes.auth_routes.get_user_by_username", return_value=fake), patch(
        "core.auth.get_user_by_username", return_value=fake
    ):
        assert client.post("/login", json={"username": "metrics_viewer", "password": "vpass"}).status_code == 200
        resp = client.get("/metrics/playbooks")
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "forbidden"


@pytest.mark.usefixtures("postgres_db")
def test_metrics_playbooks_analyst_allowed(client, postgres_db):
    conn, _cur = postgres_db
    fake = _fake_user("metrics_analyst", "apass", "analyst")
    with patch("routes.auth_routes.get_user_by_username", return_value=fake), patch(
        "core.auth.get_user_by_username", return_value=fake
    ):
        assert client.post("/login", json={"username": "metrics_analyst", "password": "apass"}).status_code == 200
        with _patched_metrics_db(conn):
            resp = client.get("/metrics/playbooks")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total_executions"] == 0
    assert set(body["by_status"].keys()) == set(KNOWN_EXECUTION_STATUSES)


@pytest.mark.usefixtures("postgres_db")
def test_metrics_playbooks_super_admin_allowed(client, postgres_db):
    conn, _cur = postgres_db
    fake = _fake_user("metrics_admin", "spass", "super_admin")
    with patch("routes.auth_routes.get_user_by_username", return_value=fake), patch(
        "core.auth.get_user_by_username", return_value=fake
    ):
        assert client.post("/login", json={"username": "metrics_admin", "password": "spass"}).status_code == 200
        with _patched_metrics_db(conn):
            resp = client.get("/metrics/playbooks")
    assert resp.status_code == 200


# --- Data shape ---


@pytest.mark.usefixtures("postgres_db")
def test_metrics_empty_database_all_zero_buckets(client, postgres_db):
    conn, _cur = postgres_db
    _login_super_admin(client)
    with _patched_metrics_db(conn):
        resp = client.get("/metrics/playbooks")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total_executions"] == 0
    for s in KNOWN_EXECUTION_STATUSES:
        assert data["by_status"][s] == 0
    assert data["by_playbook_id"] == []
    assert data["recent"]["window_hours"] == RECENT_WINDOW_HOURS
    assert data["recent"]["success"] == 0
    assert data["recent"]["failed"] == 0
    assert "time_basis" in data["recent"]
    assert data["approval_gated"]["awaiting_approval"] == 0
    assert data["approval_gated"]["with_linked_approval"] == 0
    assert "unknown_statuses" not in data


@pytest.mark.usefixtures("postgres_db")
def test_metrics_totals_by_status_and_playbook(client, postgres_db):
    conn, cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_m1", "M1", steps=_valid_steps())
    playbook_store.create_playbook_definition(conn, "pb_m2", "M2", steps=_valid_steps())
    e1 = playbook_store.create_playbook_execution(conn, "pb_m1", alert_id=None)
    e2 = playbook_store.create_playbook_execution(conn, "pb_m1", alert_id=None)
    playbook_store.update_execution_status(conn, e2, "success")
    e3 = playbook_store.create_playbook_execution(conn, "pb_m2", alert_id=None)
    playbook_store.update_execution_status(conn, e3, "failed")
    e4 = playbook_store.create_playbook_execution(conn, "pb_m2", alert_id=None)
    playbook_store.update_execution_status(conn, e4, "awaiting_approval")
    conn.commit()

    _login_super_admin(client)
    with _patched_metrics_db(conn):
        resp = client.get("/metrics/playbooks")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total_executions"] == 4
    assert data["by_status"]["pending"] == 1
    assert data["by_status"]["success"] == 1
    assert data["by_status"]["failed"] == 1
    assert data["by_status"]["awaiting_approval"] == 1
    assert data["by_status"]["running"] == 0
    assert data["by_status"]["abandoned"] == 0

    by_pb = {x["playbook_id"]: x for x in data["by_playbook_id"]}
    assert by_pb["pb_m1"]["total"] == 2
    assert by_pb["pb_m1"]["by_status"]["pending"] == 1
    assert by_pb["pb_m1"]["by_status"]["success"] == 1
    assert by_pb["pb_m2"]["total"] == 2
    assert by_pb["pb_m2"]["by_status"]["failed"] == 1
    assert by_pb["pb_m2"]["by_status"]["awaiting_approval"] == 1

    assert data["approval_gated"]["awaiting_approval"] == 1


@pytest.mark.usefixtures("postgres_db")
def test_metrics_recent_success_and_failed_window(client, postgres_db):
    conn, cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_recent", "R", steps=_valid_steps())
    e_old_ok = playbook_store.create_playbook_execution(conn, "pb_recent", alert_id=None)
    playbook_store.update_execution_status(conn, e_old_ok, "success")
    e_new_ok = playbook_store.create_playbook_execution(conn, "pb_recent", alert_id=None)
    playbook_store.update_execution_status(conn, e_new_ok, "success")
    e_old_bad = playbook_store.create_playbook_execution(conn, "pb_recent", alert_id=None)
    playbook_store.update_execution_status(conn, e_old_bad, "failed")
    e_new_bad = playbook_store.create_playbook_execution(conn, "pb_recent", alert_id=None)
    playbook_store.update_execution_status(conn, e_new_bad, "failed")
    conn.commit()

    cur.execute(
        """
        UPDATE playbook_executions
        SET completed_at = NOW() - INTERVAL '48 hours'
        WHERE id IN (%s, %s)
        """,
        (e_old_ok, e_old_bad),
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_metrics_db(conn):
        resp = client.get("/metrics/playbooks")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["recent"]["success"] == 1
    assert data["recent"]["failed"] == 1


@pytest.mark.usefixtures("postgres_db")
def test_metrics_with_linked_approval_count(client, postgres_db):
    conn, cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_appr", "A", steps=_valid_steps())
    ex = playbook_store.create_playbook_execution(conn, "pb_appr", alert_id=None)
    playbook_store.update_execution_status(conn, ex, "awaiting_approval")
    approval_store.create_playbook_step_approval_request(
        conn,
        playbook_execution_id=ex,
        playbook_step_index=0,
        action="playbook.require_approval",
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_metrics_db(conn):
        resp = client.get("/metrics/playbooks")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["approval_gated"]["with_linked_approval"] == 1
    assert data["approval_gated"]["awaiting_approval"] == 1


@pytest.mark.usefixtures("postgres_db")
def test_metrics_unknown_status_bucket(client, postgres_db):
    conn, cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_unk", "U", steps=_valid_steps())
    playbook_store.create_playbook_execution(conn, "pb_unk", alert_id=None)
    cur.execute(
        """
        UPDATE playbook_executions SET status = 'legacy_unknown' WHERE playbook_id = 'pb_unk'
        """
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_metrics_db(conn):
        resp = client.get("/metrics/playbooks")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total_executions"] == 1
    assert sum(data["by_status"].values()) == 0
    assert data["unknown_statuses"]["legacy_unknown"] == 1
    pb = data["by_playbook_id"][0]
    assert pb["playbook_id"] == "pb_unk"
    assert pb["total"] == 1
    assert pb["other_status_count"] == 1


@pytest.mark.usefixtures("postgres_db")
def test_metrics_get_does_not_mutate_related_tables(client, postgres_db):
    conn, cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_safe", "S", steps=_valid_steps())
    alert_id = _insert_alert(cur)
    ex = playbook_store.create_playbook_execution(conn, "pb_safe", alert_id=alert_id)
    approval_store.create_playbook_step_approval_request(
        conn,
        playbook_execution_id=ex,
        playbook_step_index=0,
        action="playbook.require_approval",
    )
    qid = _insert_queue_row(cur, alert_id)
    log_id = _insert_response_log(cur, alert_id)
    conn.commit()

    def counts():
        cur.execute("SELECT COUNT(*) FROM playbook_executions")
        pe = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM approval_requests")
        ar = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM response_actions_queue")
        rq = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM response_actions_log")
        rl = cur.fetchone()[0]
        return pe, ar, rq, rl

    before = counts()
    _login_super_admin(client)
    with _patched_metrics_db(conn):
        resp = client.get("/metrics/playbooks")
    assert resp.status_code == 200
    after = counts()
    assert before == after
    assert after[0] >= 1
    assert qid and log_id


@pytest.mark.usefixtures("postgres_db")
def test_metrics_does_not_invoke_playbook_executor(client, postgres_db):
    conn, _cur = postgres_db
    fake = _fake_user("metrics_ex", "x", "analyst")
    with patch("routes.auth_routes.get_user_by_username", return_value=fake), patch(
        "core.auth.get_user_by_username", return_value=fake
    ):
        assert client.post("/login", json={"username": "metrics_ex", "password": "x"}).status_code == 200
        with _patched_metrics_db(conn), patch(
            "engines.playbook_step_executor.process_playbook_execution_batch"
        ) as mock_run:
            resp = client.get("/metrics/playbooks")
    assert resp.status_code == 200
    mock_run.assert_not_called()


@pytest.mark.usefixtures("postgres_db")
def test_metrics_does_not_invoke_integration_adapter_execute(client, postgres_db):
    conn, _cur = postgres_db
    fake = _fake_user("metrics_int", "x", "analyst")
    with patch("routes.auth_routes.get_user_by_username", return_value=fake), patch(
        "core.auth.get_user_by_username", return_value=fake
    ):
        assert client.post("/login", json={"username": "metrics_int", "password": "x"}).status_code == 200
        with _patched_metrics_db(conn), patch(
            "integrations.integration_registry.get_integration_adapter"
        ) as mock_get:
            resp = client.get("/metrics/playbooks")
    assert resp.status_code == 200
    mock_get.assert_not_called()


# --- stale_running_count ---


@pytest.mark.usefixtures("postgres_db")
def test_stale_running_count_zero_when_empty(client, postgres_db):
    conn, _cur = postgres_db
    _login_super_admin(client)
    with _patched_metrics_db(conn):
        resp = client.get("/metrics/playbooks")
    assert resp.status_code == 200
    assert resp.get_json()["stale_running_count"] == 0


@pytest.mark.usefixtures("postgres_db")
def test_stale_running_count_counts_expired_running_leases(client, postgres_db):
    conn, cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_stale", "Stale", steps=_valid_steps())
    ex1 = playbook_store.create_playbook_execution(conn, "pb_stale", alert_id=None)
    ex2 = playbook_store.create_playbook_execution(conn, "pb_stale", alert_id=None)
    # ex1: running with expired lease — counts
    cur.execute(
        """
        UPDATE playbook_executions
        SET status = 'running',
            lease_owner = 'worker:1234:abc',
            lease_expires_at = NOW() - INTERVAL '10 minutes'
        WHERE id = %s
        """,
        (ex1,),
    )
    # ex2: running with non-expired lease — must not count
    cur.execute(
        """
        UPDATE playbook_executions
        SET status = 'running',
            lease_owner = 'worker:1234:def',
            lease_expires_at = NOW() + INTERVAL '10 minutes'
        WHERE id = %s
        """,
        (ex2,),
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_metrics_db(conn):
        resp = client.get("/metrics/playbooks")
    assert resp.status_code == 200
    assert resp.get_json()["stale_running_count"] == 1


@pytest.mark.usefixtures("postgres_db")
def test_stale_running_count_excludes_awaiting_approval(client, postgres_db):
    conn, cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_awap", "Awap", steps=_valid_steps())
    ex = playbook_store.create_playbook_execution(conn, "pb_awap", alert_id=None)
    # awaiting_approval with an expired lease timestamp — must not count (wrong status)
    cur.execute(
        """
        UPDATE playbook_executions
        SET status = 'awaiting_approval',
            lease_expires_at = NOW() - INTERVAL '5 minutes'
        WHERE id = %s
        """,
        (ex,),
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_metrics_db(conn):
        resp = client.get("/metrics/playbooks")
    assert resp.status_code == 200
    assert resp.get_json()["stale_running_count"] == 0


@pytest.mark.usefixtures("postgres_db")
def test_stale_running_count_excludes_null_lease_expires_at(client, postgres_db):
    conn, cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_nolease", "NoLease", steps=_valid_steps())
    ex = playbook_store.create_playbook_execution(conn, "pb_nolease", alert_id=None)
    # running but lease_expires_at is NULL (no lease held) — must not count
    cur.execute(
        "UPDATE playbook_executions SET status = 'running', lease_expires_at = NULL WHERE id = %s",
        (ex,),
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_metrics_db(conn):
        resp = client.get("/metrics/playbooks")
    assert resp.status_code == 200
    assert resp.get_json()["stale_running_count"] == 0
