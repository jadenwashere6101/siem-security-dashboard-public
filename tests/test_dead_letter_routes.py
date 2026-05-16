"""
Read-only dead letter APIs (GET /dead-letters, detail, metrics).
"""

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from psycopg2.extras import Json
from werkzeug.security import generate_password_hash

from core import dead_letter_store

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
def _patched_dead_letter_db(conn):
    wrapper = _RouteSafeConnection(conn)
    with patch("routes.dead_letter_routes.get_db_connection", return_value=wrapper), patch(
        "core.audit_helpers.get_db_connection", return_value=wrapper
    ):
        yield


def _fake_user(username, password, role):
    return {
        "username": username,
        "password_hash": generate_password_hash(password, method="pbkdf2:sha256"),
        "role": role,
        "is_active": True,
    }


def _login_super_admin(client):
    resp = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert resp.status_code == 200


def _login_role(client, *, username, password, role):
    fake = _fake_user(username, password, role)
    patchers = [
        patch("routes.auth_routes.get_user_by_username", return_value=fake),
        patch("core.auth.get_user_by_username", return_value=fake),
    ]
    for patcher in patchers:
        patcher.start()
    resp = client.post("/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return patchers


def _stop_patchers(patchers):
    for patcher in patchers:
        patcher.stop()


def test_dead_letter_routes_without_session_return_401(client):
    assert client.get("/dead-letters").status_code == 401
    assert client.get("/dead-letters/1").status_code == 401
    assert client.get("/metrics/dead-letters").status_code == 401


def test_dead_letter_routes_viewer_forbidden(client, mock_db):
    patchers = _login_role(client, username="dl_viewer", password="vpass", role="viewer")
    try:
        assert client.get("/dead-letters").status_code == 403
        assert client.get("/dead-letters/1").status_code == 403
        assert client.get("/metrics/dead-letters").status_code == 403
    finally:
        _stop_patchers(patchers)


@pytest.mark.usefixtures("postgres_db")
def test_dead_letter_list_analyst_allowed_empty(client, postgres_db):
    conn, _cur = postgres_db
    patchers = _login_role(client, username="dl_analyst", password="apass", role="analyst")
    try:
        with _patched_dead_letter_db(conn):
            resp = client.get("/dead-letters")
    finally:
        _stop_patchers(patchers)

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["items"] == []
    assert body["limit"] == 100
    assert body["offset"] == 0


@pytest.mark.usefixtures("postgres_db")
def test_dead_letter_list_super_admin_filters(client, postgres_db):
    conn, _cur = postgres_db
    first = dead_letter_store.create_dead_letter(
        conn,
        source_type="playbook_execution",
        source_id=101,
        failure_class="adapter_failed",
        error_message="failed",
        retryable=True,
    )
    dead_letter_store.create_dead_letter(
        conn,
        source_type="notification_delivery",
        source_id=202,
        failure_class="timeout",
        error_message="timed out",
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_dead_letter_db(conn):
        resp = client.get(
            "/dead-letters?status=open&source_type=playbook_execution&failure_class=adapter_failed&retryable=true"
        )

    assert resp.status_code == 200
    body = resp.get_json()
    assert [item["id"] for item in body["items"]] == [first["id"]]
    assert body["items"][0]["source_type"] == "playbook_execution"
    assert body["items"][0]["failure_class"] == "adapter_failed"
    assert body["items"][0]["retryable"] is True


@pytest.mark.usefixtures("postgres_db")
def test_dead_letter_list_invalid_filters_return_400(client, postgres_db):
    conn, _cur = postgres_db
    _login_super_admin(client)
    with _patched_dead_letter_db(conn):
        assert client.get("/dead-letters?status=bad").status_code == 400
        assert client.get("/dead-letters?retryable=maybe").status_code == 400
        assert client.get("/dead-letters?limit=zero").status_code == 400
        assert client.get("/dead-letters?execution_id=x").status_code == 400


@pytest.mark.usefixtures("postgres_db")
def test_dead_letter_detail_round_trip_and_404(client, postgres_db):
    conn, _cur = postgres_db
    row = dead_letter_store.create_dead_letter(
        conn,
        source_type="response_action",
        source_id=303,
        failure_class="permanent",
        error_message="failed action",
        payload_json={"safe": True},
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_dead_letter_db(conn):
        detail = client.get(f"/dead-letters/{row['id']}")
        missing = client.get("/dead-letters/999999")

    assert detail.status_code == 200
    body = detail.get_json()
    assert body["id"] == row["id"]
    assert body["source_type"] == "response_action"
    assert body["payload_json"] == {"safe": True}
    assert missing.status_code == 404
    assert missing.get_json()["error"] == "not_found"


@pytest.mark.usefixtures("postgres_db")
def test_dead_letter_metrics_returns_safe_aggregate_counts(client, postgres_db):
    conn, _cur = postgres_db
    open_row = dead_letter_store.create_dead_letter(
        conn,
        source_type="playbook_execution",
        source_id=401,
        failure_class="adapter_failed",
        error_message="failed",
    )
    retrying = dead_letter_store.create_dead_letter(
        conn,
        source_type="notification_delivery",
        source_id=402,
        failure_class="timeout",
        error_message="timeout",
    )
    dead_letter_store.mark_dead_letter_retry_requested(conn, retrying["id"], requested_by=None)
    conn.commit()

    _login_super_admin(client)
    with _patched_dead_letter_db(conn):
        resp = client.get("/metrics/dead-letters")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 2
    assert body["open"] == 1
    assert body["retrying"] == 1
    assert body["active"] == 2
    assert body["by_status"]["open"] == 1
    assert body["by_source_type"]["playbook_execution"] == 1
    assert body["by_failure_class"]["timeout"] == 1
    assert "payload_json" not in body
    assert "error_message" not in body
    assert dead_letter_store.get_dead_letter(conn, open_row["id"])["status"] == "open"


@pytest.mark.usefixtures("postgres_db")
def test_dead_letter_responses_redact_unsafe_payload_fields(client, postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO soar_dead_letters (
            source_type, source_id, failure_class, error_message, payload_json
        )
        VALUES (
            'playbook_execution',
            501,
            'adapter_failed',
            'failed at https://hooks.slack.com/services/secret',
            %s
        )
        RETURNING id
        """,
        (
            Json(
                {
                    "safe": "kept",
                    "authorization": "Bearer secret",
                    "nested": {"webhook_url": "https://hooks.slack.com/services/secret"},
                    "callback": "https://example.test/callback",
                }
            ),
        ),
    )
    row_id = cur.fetchone()[0]
    conn.commit()

    _login_super_admin(client)
    with _patched_dead_letter_db(conn):
        detail = client.get(f"/dead-letters/{row_id}")
        listed = client.get("/dead-letters?source_type=playbook_execution")

    assert detail.status_code == 200
    body = detail.get_json()
    assert body["error_message"] == "failed at [REDACTED_URL]"
    assert body["payload_json"] == {
        "safe": "kept",
        "nested": {},
        "callback": "[REDACTED_URL]",
    }

    listed_item = listed.get_json()["items"][0]
    assert listed_item["payload_json"] == body["payload_json"]
