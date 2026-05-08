from contextlib import contextmanager
import hashlib
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

import siem_backend


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
def _patched_app_db(conn):
    wrapper = _RouteSafeConnection(conn)
    with patch("routes.admin_routes.get_db_connection", return_value=wrapper), patch(
        "core.audit_helpers.get_db_connection", return_value=wrapper
    ), patch("core.approval_store.log_audit_event"):
        yield


def _login_super_admin(client):
    resp = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert resp.status_code == 200


def _fake_viewer():
    return {
        "username": "worker_viewer",
        "password_hash": generate_password_hash("viewerpass", method="pbkdf2:sha256"),
        "role": "viewer",
        "is_active": True,
    }


def _fake_analyst():
    return {
        "username": "worker_analyst",
        "password_hash": generate_password_hash("analystpass", method="pbkdf2:sha256"),
        "role": "analyst",
        "is_active": True,
    }


def _insert_alert(cur, source_ip="8.8.8.8"):
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message)
        VALUES ('test_alert', 'low', %s, 'test alert')
        RETURNING id
        """,
        (source_ip,),
    )
    return cur.fetchone()[0]


def _insert_queue_row(
    cur,
    alert_id,
    source_ip,
    action="monitor",
    status="pending",
    retry_count=0,
    max_retries=3,
    last_error=None,
    nonce="",
):
    idempotency_key = hashlib.sha256(
        f"{alert_id}:{source_ip}:{action}:{status}:{nonce}".encode()
    ).hexdigest()
    cur.execute(
        """
        INSERT INTO response_actions_queue
            (idempotency_key, alert_id, source_ip, action, status,
             retry_count, max_retries, last_error)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            idempotency_key,
            alert_id,
            source_ip,
            action,
            status,
            retry_count,
            max_retries,
            last_error,
        ),
    )
    return cur.fetchone()[0]


def _fetch_queue_row(cur, queue_id):
    cur.execute(
        """
        SELECT id, status, retry_count, max_retries, last_error, updated_at
        FROM response_actions_queue
        WHERE id = %s
        """,
        (queue_id,),
    )
    return cur.fetchone()


def _insert_approval_request(
    cur,
    *,
    queue_id=None,
    action="block_ip",
    status="pending",
    expires_in_minutes=-60,
):
    cur.execute(
        """
        INSERT INTO approval_requests (
            queue_id, action, status, expires_at, decided_at
        )
        VALUES (
            %s,
            %s,
            %s,
            NOW() + (%s * INTERVAL '1 minute'),
            CASE WHEN %s = 'pending' THEN NULL ELSE NOW() END
        )
        RETURNING id
        """,
        (queue_id, action, status, expires_in_minutes, status),
    )
    return cur.fetchone()[0]


def _fetch_approval_status(cur, approval_id):
    cur.execute(
        "SELECT status FROM approval_requests WHERE id = %s",
        (approval_id,),
    )
    return cur.fetchone()[0]


def _count_audit_events(cur, event_type):
    cur.execute("SELECT COUNT(*) FROM audit_log WHERE event_type = %s", (event_type,))
    return cur.fetchone()[0]


def test_worker_run_once_without_session_returns_401(client):
    resp = client.post("/admin/soar/worker/run-once", json={})

    assert resp.status_code == 401
    assert resp.get_json()["error"] == "Unauthorized"


@pytest.mark.parametrize(
    "fake_user,password",
    [
        (_fake_viewer(), "viewerpass"),
        (_fake_analyst(), "analystpass"),
    ],
)
def test_worker_run_once_as_non_admin_returns_403(client, mock_db, fake_user, password):
    with patch("routes.auth_routes.get_user_by_username", return_value=fake_user), patch(
        "core.auth.get_user_by_username", return_value=fake_user
    ):
        login = client.post("/login", json={"username": fake_user["username"], "password": password})
        assert login.status_code == 200
        resp = client.post("/admin/soar/worker/run-once", json={})

    assert resp.status_code == 403
    assert resp.get_json()["error"] == "forbidden"


def test_worker_run_once_empty_queue_returns_zero_summary(client, postgres_db):
    conn, _cur = postgres_db
    _login_super_admin(client)

    with _patched_app_db(conn):
        resp = client.post("/admin/soar/worker/run-once", json={})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["mode"] == "simulation"
    assert data["requested_batch_size"] == 10
    assert data["batch_size"] == 10
    assert data["summary"] == {
        "processed": 0,
        "success": 0,
        "failed": 0,
        "skipped": 0,
        "requeued": 0,
    }
    assert data["results"] == []


def test_worker_run_once_admin_processes_simulation_batch(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    queue_id = _insert_queue_row(cur, alert_id, "8.8.8.8", action="monitor")
    conn.commit()
    _login_super_admin(client)

    with _patched_app_db(conn):
        resp = client.post("/admin/soar/worker/run-once", json={"batch_size": 1})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["mode"] == "simulation"
    assert data["summary"]["processed"] == 1
    assert data["summary"]["success"] == 1
    assert data["results"][0]["queue_id"] == queue_id
    assert data["results"][0]["outcome"] == "success"
    assert _fetch_queue_row(cur, queue_id)[1] == "success"


def test_worker_run_once_rejects_real_mode(client, postgres_db):
    conn, _cur = postgres_db
    _login_super_admin(client)

    with _patched_app_db(conn):
        resp = client.post("/admin/soar/worker/run-once", json={"mode": "real"})

    assert resp.status_code == 400
    assert "simulation-only" in resp.get_json()["error"]


def test_worker_run_once_invalid_batch_size_returns_400(client, postgres_db):
    conn, _cur = postgres_db
    _login_super_admin(client)

    with _patched_app_db(conn):
        resp = client.post("/admin/soar/worker/run-once", json={"batch_size": "abc"})

    assert resp.status_code == 400
    assert "integer" in resp.get_json()["error"]


def test_worker_run_once_clamps_excessive_batch_size(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    for index in range(30):
        _insert_queue_row(cur, alert_id, f"8.8.8.{index + 1}", nonce=str(index))
    conn.commit()
    _login_super_admin(client)

    with _patched_app_db(conn):
        resp = client.post("/admin/soar/worker/run-once", json={"batch_size": 999})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["requested_batch_size"] == 999
    assert data["batch_size"] == 25
    assert data["summary"]["processed"] == 25
    assert len(data["results"]) == 25


def test_worker_run_once_ignores_real_execution_env(client, postgres_db, monkeypatch):
    conn, cur = postgres_db
    monkeypatch.setenv("SOAR_EXECUTION_MODE", "real")
    alert_id = _insert_alert(cur)
    queue_id = _insert_queue_row(cur, alert_id, "8.8.4.4", action="monitor")
    conn.commit()
    _login_super_admin(client)

    with _patched_app_db(conn):
        resp = client.post("/admin/soar/worker/run-once", json={"batch_size": 1})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["mode"] == "simulation"
    assert data["results"][0]["queue_id"] == queue_id
    assert data["results"][0]["message"].startswith("Monitoring only")


def test_worker_run_once_terminal_rows_are_not_mutated(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    terminal_id = _insert_queue_row(
        cur,
        alert_id,
        "8.8.8.8",
        action="monitor",
        status="success",
        nonce="terminal",
    )
    pending_id = _insert_queue_row(
        cur,
        alert_id,
        "8.8.4.4",
        action="monitor",
        status="pending",
        nonce="pending",
    )
    conn.commit()
    original_terminal = _fetch_queue_row(cur, terminal_id)
    _login_super_admin(client)

    with _patched_app_db(conn):
        resp = client.post("/admin/soar/worker/run-once", json={"batch_size": 10})

    assert resp.status_code == 200
    assert _fetch_queue_row(cur, terminal_id) == original_terminal
    assert _fetch_queue_row(cur, pending_id)[1] == "success"


def test_worker_run_once_writes_audit_event(client, postgres_db):
    conn, cur = postgres_db
    _login_super_admin(client)

    with _patched_app_db(conn):
        resp = client.post("/admin/soar/worker/run-once", json={"batch_size": 1})

    assert resp.status_code == 200
    assert _count_audit_events(cur, "SOAR_WORKER_RUN_ONCE") == 1


def test_worker_run_once_does_not_import_real_adapter_path():
    import routes.admin_routes as admin_routes

    assert not hasattr(admin_routes, "AdapterBackedExecutor")


def test_expire_pending_approvals_without_session_returns_401(client):
    resp = client.post("/admin/soar/approvals/expire-pending")

    assert resp.status_code == 401
    assert resp.get_json()["error"] == "Unauthorized"


@pytest.mark.parametrize(
    "fake_user,password",
    [
        (_fake_viewer(), "viewerpass"),
        (_fake_analyst(), "analystpass"),
    ],
)
def test_expire_pending_approvals_as_non_admin_returns_403(client, mock_db, fake_user, password):
    with patch("routes.auth_routes.get_user_by_username", return_value=fake_user), patch(
        "core.auth.get_user_by_username", return_value=fake_user
    ):
        login = client.post("/login", json={"username": fake_user["username"], "password": password})
        assert login.status_code == 200
        resp = client.post("/admin/soar/approvals/expire-pending")

    assert resp.status_code == 403
    assert resp.get_json()["error"] == "forbidden"


def test_expire_pending_approvals_empty_returns_zero_counts(client, postgres_db):
    conn, _cur = postgres_db
    _login_super_admin(client)

    with _patched_app_db(conn):
        resp = client.post("/admin/soar/approvals/expire-pending")

    assert resp.status_code == 200
    assert resp.get_json() == {
        "expired_approvals": 0,
        "skipped_queue_rows": 0,
        "expired_approval_ids": [],
        "skipped_queue_ids": [],
    }


def test_expire_pending_approvals_expires_overdue_pending_approvals(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    queue_id = _insert_queue_row(cur, alert_id, "8.8.8.9", action="block_ip")
    approval_id = _insert_approval_request(cur, queue_id=queue_id, status="pending")
    conn.commit()
    _login_super_admin(client)

    with _patched_app_db(conn):
        resp = client.post("/admin/soar/approvals/expire-pending")

    data = resp.get_json()
    assert resp.status_code == 200
    assert data["expired_approvals"] == 1
    assert data["expired_approval_ids"] == [approval_id]
    assert data["skipped_queue_rows"] == 0
    assert _fetch_approval_status(cur, approval_id) == "expired"


def test_expire_pending_approvals_sweeps_awaiting_approval_queue_rows(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    queue_id = _insert_queue_row(
        cur,
        alert_id,
        "8.8.8.10",
        action="block_ip",
        status="awaiting_approval",
    )
    _insert_approval_request(cur, queue_id=queue_id, status="expired")
    conn.commit()
    _login_super_admin(client)

    with _patched_app_db(conn):
        resp = client.post("/admin/soar/approvals/expire-pending")

    data = resp.get_json()
    queue_row = _fetch_queue_row(cur, queue_id)
    assert resp.status_code == 200
    assert data["expired_approvals"] == 0
    assert data["skipped_queue_rows"] == 1
    assert data["skipped_queue_ids"] == [queue_id]
    assert queue_row[1] == "skipped"
    assert queue_row[4] == "approval expired"


def test_expire_pending_approvals_expires_and_sweeps_in_one_call(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    queue_id = _insert_queue_row(
        cur,
        alert_id,
        "8.8.8.11",
        action="block_ip",
        status="awaiting_approval",
    )
    approval_id = _insert_approval_request(cur, queue_id=queue_id, status="pending")
    conn.commit()
    _login_super_admin(client)

    with _patched_app_db(conn):
        resp = client.post("/admin/soar/approvals/expire-pending")

    data = resp.get_json()
    assert resp.status_code == 200
    assert data["expired_approvals"] == 1
    assert data["expired_approval_ids"] == [approval_id]
    assert data["skipped_queue_rows"] == 1
    assert data["skipped_queue_ids"] == [queue_id]
    assert _fetch_approval_status(cur, approval_id) == "expired"
    assert _fetch_queue_row(cur, queue_id)[1] == "skipped"


def test_expire_pending_approvals_endpoint_is_idempotent(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    queue_id = _insert_queue_row(
        cur,
        alert_id,
        "8.8.8.12",
        action="block_ip",
        status="awaiting_approval",
    )
    _insert_approval_request(cur, queue_id=queue_id, status="pending")
    conn.commit()
    _login_super_admin(client)

    with _patched_app_db(conn):
        first = client.post("/admin/soar/approvals/expire-pending")
        second = client.post("/admin/soar/approvals/expire-pending")

    assert first.status_code == 200
    assert first.get_json()["expired_approvals"] == 1
    assert first.get_json()["skipped_queue_rows"] == 1
    assert second.status_code == 200
    assert second.get_json() == {
        "expired_approvals": 0,
        "skipped_queue_rows": 0,
        "expired_approval_ids": [],
        "skipped_queue_ids": [],
    }


def test_expire_pending_approvals_does_not_increment_retry_count(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    queue_id = _insert_queue_row(
        cur,
        alert_id,
        "8.8.8.13",
        action="block_ip",
        status="awaiting_approval",
        retry_count=1,
        max_retries=3,
    )
    _insert_approval_request(cur, queue_id=queue_id, status="expired")
    conn.commit()
    _login_super_admin(client)

    with _patched_app_db(conn):
        resp = client.post("/admin/soar/approvals/expire-pending")

    queue_row = _fetch_queue_row(cur, queue_id)
    assert resp.status_code == 200
    assert resp.get_json()["skipped_queue_rows"] == 1
    assert queue_row[1] == "skipped"
    assert queue_row[2] == 1
