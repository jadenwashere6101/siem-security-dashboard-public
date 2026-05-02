from contextlib import contextmanager
from unittest.mock import patch

import siem_backend


ADMIN_USER = "testadmin"
ADMIN_PASS = "testpassword123!"


class _RouteSafeConnection:
    """Route-level connection wrapper that ignores close()."""

    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return self._conn.cursor()

    def close(self):
        return None


@contextmanager
def _patched_app_db(conn):
    wrapper = _RouteSafeConnection(conn)
    with patch("siem_backend.get_db_connection", return_value=wrapper), patch(
        "backend_audit_helpers.get_db_connection", return_value=wrapper
    ):
        yield


def _login_super_admin(client):
    resp = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert resp.status_code == 200


def _insert_alert(cur, *, source_ip="198.51.100.250", message="Contract alert"):
    cur.execute(
        """
        INSERT INTO alerts (
            alert_type,
            severity,
            source_ip,
            source,
            source_type,
            message,
            status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        ("failed_login_threshold", "high", source_ip, "bank_app", "custom", message, "open"),
    )
    return cur.fetchone()[0]


def test_get_alert_notes_without_session_returns_401(client):
    resp = client.get("/alerts/1/notes")
    assert resp.status_code == 401


def test_get_alert_notes_authenticated_returns_200_stable_json_shape(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    cur.execute(
        """
        INSERT INTO alert_notes (alert_id, author, note_text)
        VALUES (%s, %s, %s)
        """,
        (alert_id, "admin", "contract note"),
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get(f"/alerts/{alert_id}/notes")

    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) >= 1
    note = data[0]
    for key in ("id", "alert_id", "author", "note_text", "created_at"):
        assert key in note


def test_post_alert_notes_invalid_or_too_long_returns_400(client):
    _login_super_admin(client)
    max_len = siem_backend.MAX_ALERT_NOTE_LENGTH

    resp_empty = client.post("/alerts/99999/notes", json={"note_text": "   "})
    assert resp_empty.status_code == 400
    assert resp_empty.get_json()["error"] == "note_text is required"

    too_long = "x" * (max_len + 1)
    resp_long = client.post("/alerts/99999/notes", json={"note_text": too_long})
    assert resp_long.status_code == 400
    err = resp_long.get_json()["error"]
    assert str(max_len) in err


def test_post_alert_status_without_session_returns_401(client):
    resp = client.post("/alerts/1/status", json={"status": "resolved"})
    assert resp.status_code == 401


def test_post_alert_status_invalid_status_returns_400(client):
    _login_super_admin(client)
    resp = client.post("/alerts/1/status", json={"status": "not_a_valid_status"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Invalid status"


def test_post_alert_execute_without_session_returns_401(client):
    resp = client.post("/alerts/1/execute", json={"action": "monitor"})
    assert resp.status_code == 401


def test_post_alert_execute_missing_action_returns_400(client):
    _login_super_admin(client)
    resp = client.post("/alerts/1/execute", json={})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Missing action"


def test_post_alert_execute_invalid_action_returns_400(client):
    _login_super_admin(client)
    resp = client.post("/alerts/1/execute", json={"action": "not_a_valid_action"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Invalid response action"


def test_post_alert_execute_nonexistent_alert_id_returns_404(client, postgres_db):
    conn, _ = postgres_db
    _login_super_admin(client)

    with _patched_app_db(conn):
        resp = client.post("/alerts/99999/execute", json={"action": "monitor"})

    assert resp.status_code == 404
    assert resp.get_json()["error"] == "Alert not found"


def test_get_alert_response_log_authenticated_returns_200_stable_json_shape(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, source_ip="198.51.100.251", message="Response log contract")
    cur.execute(
        """
        INSERT INTO response_actions_log (alert_id, source_ip, action, status, details)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (alert_id, "203.0.113.10", "monitor", "executed", "contract details"),
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get(f"/alerts/{alert_id}/response-log")

    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) >= 1
    entry = data[0]
    for key in ("id", "alert_id", "source_ip", "action", "status", "details", "executed_at"):
        assert key in entry
