"""
Read-only notification delivery metrics API (GET /metrics/notifications).
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

from core import notification_delivery_store
from routes.metrics_routes import (
    KNOWN_CIRCUIT_BREAKER_STATES,
    KNOWN_NOTIFICATION_MODES,
    KNOWN_NOTIFICATION_STATUSES,
    KNOWN_RECENT_NOTIFICATION_BUCKETS,
    RECENT_WINDOW_HOURS,
)

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


@contextmanager
def _patched_fake_user(username, password, role):
    fake = _fake_user(username, password, role)
    with patch("routes.auth_routes.get_user_by_username", return_value=fake), patch(
        "core.auth.get_user_by_username", return_value=fake
    ):
        yield


def _login_fake(client, username, password, role):
    with _patched_fake_user(username, password, role):
        resp = client.post("/login", json={"username": username, "password": password})
    assert resp.status_code == 200


def _create_delivery(conn, *, correlation_id, idempotency_key, **kwargs):
    defaults = {
        "provider": "slack",
        "mode": "simulation",
        "status": "success",
        "adapter_name": "slack",
        "action": "send_message",
    }
    defaults.update(kwargs)
    return notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        **defaults,
    )


def test_notification_metrics_without_session_returns_401(client):
    assert client.get("/metrics/notifications").status_code == 401


def test_notification_metrics_viewer_forbidden(client, mock_db):
    with _patched_fake_user("notif_metrics_viewer", "vpass", "viewer"):
        assert client.post("/login", json={"username": "notif_metrics_viewer", "password": "vpass"}).status_code == 200
        resp = client.get("/metrics/notifications")
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "forbidden"


@pytest.mark.usefixtures("postgres_db")
def test_notification_metrics_analyst_allowed_empty(client, postgres_db):
    conn, _cur = postgres_db
    with _patched_fake_user("notif_metrics_analyst", "apass", "analyst"):
        assert client.post("/login", json={"username": "notif_metrics_analyst", "password": "apass"}).status_code == 200
        with _patched_metrics_db(conn):
            resp = client.get("/metrics/notifications")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total_delivery_attempts"] == 0
    assert body["by_provider"] == {}
    assert body["by_adapter_name"] == {}
    assert set(body["by_mode"].keys()) == set(KNOWN_NOTIFICATION_MODES)
    assert set(body["by_status"].keys()) == set(KNOWN_NOTIFICATION_STATUSES)


@pytest.mark.usefixtures("postgres_db")
def test_notification_metrics_empty_database_all_zero_buckets(client, postgres_db):
    conn, _cur = postgres_db
    _login_super_admin(client)
    with _patched_metrics_db(conn):
        resp = client.get("/metrics/notifications")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total_delivery_attempts"] == 0
    assert data["by_provider"] == {}
    assert data["by_adapter_name"] == {}
    for mode in KNOWN_NOTIFICATION_MODES:
        assert data["by_mode"][mode] == 0
    for status in KNOWN_NOTIFICATION_STATUSES:
        assert data["by_status"][status] == 0
    for bucket in KNOWN_RECENT_NOTIFICATION_BUCKETS:
        assert data["recent"][bucket] == 0
    for state in KNOWN_CIRCUIT_BREAKER_STATES:
        assert data["circuit_breaker_state_counts"][state] == 0
    assert data["canonical_outcome_counts"]["execution_mode"]["simulation"] == 0
    assert data["canonical_outcome_counts"]["external_executed"]["true"] == 0
    assert data["recent"]["window_hours"] == RECENT_WINDOW_HOURS
    assert "time_basis" in data["recent"]


@pytest.mark.usefixtures("postgres_db")
def test_notification_metrics_aggregate_counts(client, postgres_db):
    conn, _cur = postgres_db
    _create_delivery(
        conn,
        correlation_id="m-slack-success",
        idempotency_key="m-i1",
        provider="slack",
        mode="simulation",
        status="success",
        adapter_name="slack",
        circuit_breaker_state="closed",
    )
    _create_delivery(
        conn,
        correlation_id="m-slack-failed",
        idempotency_key="m-i2",
        provider="slack",
        mode="real",
        status="failed",
        adapter_name="slack",
        circuit_breaker_state="open",
    )
    _create_delivery(
        conn,
        correlation_id="m-teams-timeout",
        idempotency_key="m-i3",
        provider="teams",
        mode="simulation",
        status="timeout",
        adapter_name="teams",
        circuit_breaker_state="half_open",
    )
    _create_delivery(
        conn,
        correlation_id="m-teams-blocked",
        idempotency_key="m-i4",
        provider="teams",
        mode="simulation",
        status="blocked",
        adapter_name="teams",
        circuit_breaker_state="open",
    )
    _create_delivery(
        conn,
        correlation_id="m-pending",
        idempotency_key="m-i5",
        provider="slack",
        mode="simulation",
        status="pending",
        adapter_name="slack",
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_metrics_db(conn):
        resp = client.get("/metrics/notifications")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total_delivery_attempts"] == 5
    assert data["by_provider"] == {"slack": 3, "teams": 2}
    assert data["by_adapter_name"] == {"slack": 3, "teams": 2}
    assert data["by_mode"]["simulation"] == 4
    assert data["by_mode"]["real"] == 1
    assert data["by_status"]["pending"] == 1
    assert data["by_status"]["success"] == 1
    assert data["by_status"]["failed"] == 1
    assert data["by_status"]["timeout"] == 1
    assert data["by_status"]["blocked"] == 1
    assert data["circuit_breaker_state_counts"]["closed"] == 1
    assert data["circuit_breaker_state_counts"]["open"] == 2
    assert data["circuit_breaker_state_counts"]["half_open"] == 1
    assert data["circuit_breaker_state_counts"]["unknown"] == 0
    assert data["circuit_breaker_state_counts"]["invalid"] == 0


@pytest.mark.usefixtures("postgres_db")
def test_notification_metrics_recent_window_counts(client, postgres_db):
    conn, _cur = postgres_db
    now = datetime.now(timezone.utc)
    old = now - timedelta(hours=48)
    _create_delivery(
        conn,
        correlation_id="recent-success",
        idempotency_key="recent-i1",
        status="success",
        completed_at=now,
    )
    _create_delivery(
        conn,
        correlation_id="recent-failed",
        idempotency_key="recent-i2",
        status="failed",
        completed_at=now,
    )
    _create_delivery(
        conn,
        correlation_id="recent-timeout",
        idempotency_key="recent-i3",
        status="timeout",
        completed_at=now,
    )
    _create_delivery(
        conn,
        correlation_id="recent-blocked",
        idempotency_key="recent-i4",
        status="blocked",
        completed_at=now,
    )
    _create_delivery(
        conn,
        correlation_id="old-success",
        idempotency_key="recent-i5",
        status="success",
        completed_at=old,
        requested_at=old,
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_metrics_db(conn):
        resp = client.get("/metrics/notifications")
    assert resp.status_code == 200
    recent = resp.get_json()["recent"]
    assert recent["success"] == 1
    assert recent["failed"] == 1
    assert recent["timeout"] == 1
    assert recent["blocked"] == 1


@pytest.mark.usefixtures("postgres_db")
def test_notification_metrics_get_does_not_mutate_delivery_rows(client, postgres_db):
    conn, cur = postgres_db
    _create_delivery(conn, correlation_id="safe-count", idempotency_key="safe-count-i")
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM notification_delivery_attempts")
    before = cur.fetchone()[0]

    _login_super_admin(client)
    with _patched_metrics_db(conn):
        resp = client.get("/metrics/notifications")
    assert resp.status_code == 200

    cur.execute("SELECT COUNT(*) FROM notification_delivery_attempts")
    after = cur.fetchone()[0]
    assert before == after


@pytest.mark.usefixtures("postgres_db")
def test_notification_metrics_does_not_expose_metadata_or_secrets(client, postgres_db):
    conn, _cur = postgres_db
    _create_delivery(
        conn,
        correlation_id="secret-safe",
        idempotency_key="secret-safe-i",
        metadata={
            "webhook_configured": True,
            "slack_webhook_url": "https://example.invalid/secret",
            "token": "secret-token",
        },
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_metrics_db(conn):
        resp = client.get("/metrics/notifications")
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert "example.invalid" not in text
    assert "secret-token" not in text
    assert "metadata" not in text
    assert "webhook_configured" not in text


@pytest.mark.usefixtures("postgres_db")
def test_notification_metrics_does_not_invoke_executor_or_adapters(client, postgres_db):
    conn, _cur = postgres_db
    with _patched_fake_user("notif_metrics_no_run", "npass", "analyst"):
        assert client.post("/login", json={"username": "notif_metrics_no_run", "password": "npass"}).status_code == 200
        with _patched_metrics_db(conn), patch(
            "engines.playbook_step_executor.process_playbook_execution_batch"
        ) as mock_run, patch("integrations.integration_registry.get_integration_adapter") as mock_get:
            resp = client.get("/metrics/notifications")
    assert resp.status_code == 200
    mock_run.assert_not_called()
    mock_get.assert_not_called()
