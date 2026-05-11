"""
Read-only notification delivery APIs (GET /notification-deliveries, GET .../<id>).
"""

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

from core import notification_delivery_store

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
def _patched_nd_db(conn):
    wrapper = _RouteSafeConnection(conn)
    with patch("routes.notification_delivery_routes.get_db_connection", return_value=wrapper), patch(
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


def test_list_without_session_returns_401(client):
    assert client.get("/notification-deliveries").status_code == 401


def test_list_viewer_forbidden(client, mock_db):
    fake = _fake_user("nd_viewer", "vpass", "viewer")
    with patch("routes.auth_routes.get_user_by_username", return_value=fake), patch(
        "core.auth.get_user_by_username", return_value=fake
    ):
        assert client.post("/login", json={"username": "nd_viewer", "password": "vpass"}).status_code == 200
        resp = client.get("/notification-deliveries")
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "forbidden"


def test_detail_viewer_forbidden(client, mock_db):
    fake = _fake_user("nd_viewer2", "vpass2", "viewer")
    with patch("routes.auth_routes.get_user_by_username", return_value=fake), patch(
        "core.auth.get_user_by_username", return_value=fake
    ):
        assert client.post("/login", json={"username": "nd_viewer2", "password": "vpass2"}).status_code == 200
        resp = client.get("/notification-deliveries/1")
    assert resp.status_code == 403


@pytest.mark.usefixtures("postgres_db")
def test_list_analyst_allowed_empty(client, postgres_db):
    conn, _cur = postgres_db
    fake = _fake_user("nd_analyst", "apass", "analyst")
    with patch("routes.auth_routes.get_user_by_username", return_value=fake), patch(
        "core.auth.get_user_by_username", return_value=fake
    ):
        assert client.post("/login", json={"username": "nd_analyst", "password": "apass"}).status_code == 200
        with _patched_nd_db(conn):
            resp = client.get("/notification-deliveries")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["items"] == []
    assert body["limit"] == 100
    assert body["offset"] == 0


@pytest.mark.usefixtures("postgres_db")
def test_list_super_admin_shape_and_filters(client, postgres_db):
    conn, _cur = postgres_db
    notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="route-c1",
        idempotency_key="route-i1",
        provider="slack",
        mode="simulation",
        status="success",
        adapter_name="slack",
        action="send_message",
        metadata={"channel_label": "#alerts"},
    )
    notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="route-c2",
        idempotency_key="route-i2",
        provider="teams",
        mode="simulation",
        status="failed",
        adapter_name="teams",
        action="send_message",
        metadata={"safe": True},
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_nd_db(conn):
        resp = client.get("/notification-deliveries")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["limit"] == 100
    assert len(body["items"]) == 2
    assert body["items"][0]["correlation_id"] == "route-c2"

    with _patched_nd_db(conn):
        r2 = client.get("/notification-deliveries?provider=slack")
    assert len(r2.get_json()["items"]) == 1
    assert r2.get_json()["items"][0]["provider"] == "slack"

    with _patched_nd_db(conn):
        r3 = client.get("/notification-deliveries?adapter_name=teams")
    assert len(r3.get_json()["items"]) == 1
    assert r3.get_json()["items"][0]["adapter_name"] == "teams"

    with _patched_nd_db(conn):
        r4 = client.get("/notification-deliveries?correlation_id=route-c1")
    assert len(r4.get_json()["items"]) == 1

    with _patched_nd_db(conn):
        r5 = client.get("/notification-deliveries?status=failed")
    assert len(r5.get_json()["items"]) == 1
    assert r5.get_json()["items"][0]["status"] == "failed"


@pytest.mark.usefixtures("postgres_db")
def test_list_invalid_mode_returns_400(client, postgres_db):
    conn, _cur = postgres_db
    _login_super_admin(client)
    with _patched_nd_db(conn):
        resp = client.get("/notification-deliveries?mode=not_a_mode")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_query"


@pytest.mark.usefixtures("postgres_db")
def test_list_invalid_limit_returns_400(client, postgres_db):
    conn, _cur = postgres_db
    _login_super_admin(client)
    with _patched_nd_db(conn):
        assert client.get("/notification-deliveries?limit=0").status_code == 400
        assert client.get("/notification-deliveries?limit=abc").status_code == 400


@pytest.mark.usefixtures("postgres_db")
def test_list_invalid_playbook_execution_id_returns_400(client, postgres_db):
    conn, _cur = postgres_db
    _login_super_admin(client)
    with _patched_nd_db(conn):
        resp = client.get("/notification-deliveries?playbook_execution_id=nan")
    assert resp.status_code == 400


@pytest.mark.usefixtures("postgres_db")
def test_get_detail_round_trip_and_404(client, postgres_db):
    conn, _cur = postgres_db
    row = notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="d1",
        idempotency_key="i1",
        provider="slack",
        mode="simulation",
        status="blocked",
        adapter_name="slack",
        action="send_message",
        circuit_breaker_state="open",
    )
    conn.commit()
    aid = row["id"]

    _login_super_admin(client)
    with _patched_nd_db(conn):
        resp = client.get(f"/notification-deliveries/{aid}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["id"] == aid
    assert body["correlation_id"] == "d1"
    assert body["circuit_breaker_state"] == "open"

    with _patched_nd_db(conn):
        r404 = client.get("/notification-deliveries/999999")
    assert r404.status_code == 404
    assert r404.get_json()["error"] == "not_found"


@pytest.mark.usefixtures("postgres_db")
def test_get_detail_unauthenticated_401(client, postgres_db):
    conn, _cur = postgres_db
    row = notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="d2",
        idempotency_key="i2",
        provider="teams",
        mode="simulation",
        status="success",
        adapter_name="teams",
        action="send_message",
    )
    conn.commit()
    assert client.get(f"/notification-deliveries/{row['id']}").status_code == 401


@pytest.mark.usefixtures("postgres_db")
def test_response_metadata_redacted_no_secrets(client, postgres_db):
    conn, _cur = postgres_db
    notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="red",
        idempotency_key="red-i",
        provider="slack",
        mode="simulation",
        status="success",
        adapter_name="slack",
        action="send_message",
        metadata={
            "ok": True,
            "slack_webhook_url": "https://hooks.slack.com/secret",
        },
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_nd_db(conn):
        resp = client.get("/notification-deliveries")
    item = resp.get_json()["items"][0]
    assert item["metadata"].get("ok") is True
    assert "slack_webhook_url" not in item["metadata"]


@pytest.mark.usefixtures("postgres_db")
def test_get_list_no_row_count_change(client, postgres_db):
    conn, cur = postgres_db
    notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="cnt",
        idempotency_key="cnt-i",
        provider="slack",
        mode="simulation",
        status="success",
        adapter_name="slack",
        action="send_message",
    )
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM notification_delivery_attempts")
    before = cur.fetchone()[0]

    _login_super_admin(client)
    with _patched_nd_db(conn):
        assert client.get("/notification-deliveries").status_code == 200
        assert client.get("/notification-deliveries?limit=5&offset=0").status_code == 200

    cur.execute("SELECT COUNT(*) FROM notification_delivery_attempts")
    after = cur.fetchone()[0]
    assert before == after
