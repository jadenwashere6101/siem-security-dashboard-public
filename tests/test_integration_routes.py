import http.client
import json
import smtplib
import socket
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from werkzeug.security import generate_password_hash

from integrations.base_integration import (
    CIRCUIT_STATE_CLOSED,
    CIRCUIT_STATE_OPEN,
    configure_simulated_circuit_breaker,
    get_simulated_circuit_breaker_dict,
    reset_simulated_circuit_breakers,
)


ADMIN_USER = "testadmin"
ADMIN_PASS = "testpassword123!"


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


def _login_role(client, *, username, password, role):
    user = _fake_user(username, password, role)
    patchers = [
        patch("routes.auth_routes.get_user_by_username", return_value=user),
        patch("core.auth.get_user_by_username", return_value=user),
    ]
    for patcher in patchers:
        patcher.start()
    resp = client.post("/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return patchers


def _stop_patchers(patchers):
    for patcher in reversed(patchers):
        patcher.stop()


@pytest.fixture(autouse=True)
def _isolate_simulated_integration_circuits():
    reset_simulated_circuit_breakers()
    yield
    reset_simulated_circuit_breakers()


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
def _patched_audit_db(conn):
    wrapper = _RouteSafeConnection(conn)
    with patch("core.audit_helpers.get_db_connection", return_value=wrapper):
        yield


def _deny_network(monkeypatch):
    def fail_network(*_args, **_kwargs):
        raise AssertionError("network call attempted by integration status route")

    monkeypatch.setattr(socket, "socket", fail_network)
    monkeypatch.setattr(smtplib, "SMTP", fail_network)
    monkeypatch.setattr(smtplib, "SMTP_SSL", fail_network)
    monkeypatch.setattr(http.client.HTTPConnection, "request", fail_network)
    monkeypatch.setattr(http.client.HTTPSConnection, "request", fail_network)
    monkeypatch.setattr(urllib.request, "urlopen", fail_network)


def _assert_status_shape(data):
    assert data["mode"] == "simulation"
    assert data["simulated"] is True
    assert data["real_mode_enabled"] is False
    assert data["real_mode_status"]
    assert data["slack_configured"] in {True, False}
    assert data["teams_configured"] in {True, False}
    assert data["smtp_configured"] in {True, False}
    assert data["email_real_enabled"] in {True, False}
    assert data["real_mode_allowed"] in {True, False}
    assert data["real_mode_ready"] in {True, False}
    adapters = {adapter["name"]: adapter for adapter in data["adapters"]}
    assert set(adapters) == {"email", "firewall", "slack", "teams", "webhook"}
    assert adapters["slack"]["supported_actions"] == [
        "notify_channel",
        "send_message",
        "test_notification",
    ]
    assert adapters["teams"]["supported_actions"] == [
        "notify_channel",
        "notify_teams",
        "send_message",
        "test_notification",
    ]
    assert adapters["email"]["supported_actions"] == [
        "notify_owner",
        "send_email",
        "test_notification",
    ]
    assert adapters["firewall"]["supported_actions"] == ["block_ip", "tag_ip", "unblock_ip"]
    assert adapters["webhook"]["supported_actions"] == [
        "notify_webhook",
        "post_event",
        "send_webhook",
        "test_notification",
    ]
    assert {adapter["mode"] for adapter in adapters.values()} == {"simulation"}
    assert {adapter["simulated"] for adapter in adapters.values()} == {True}
    assert {adapter["real_client"] for adapter in adapters.values()} == {False}
    assert "slack_configured" in adapters["slack"]
    assert "real_mode_allowed" in adapters["slack"]
    assert "real_mode_ready" in adapters["slack"]
    assert "smtp_configured" in adapters["email"]
    assert "email_real_enabled" in adapters["email"]
    assert "webhook_configured" in adapters["slack"]
    assert "teams_configured" in adapters["teams"]
    assert "real_mode_allowed" in adapters["teams"]
    assert "real_mode_ready" in adapters["teams"]
    assert "webhook_configured" in adapters["teams"]
    assert adapters["firewall"]["real_mode_available"] is False
    assert adapters["firewall"]["real_mode_allowed"] is False
    assert adapters["firewall"]["real_mode_ready"] is False


def test_integration_status_without_session_returns_401(client):
    resp = client.get("/integrations/status")

    assert resp.status_code == 401


def test_integration_status_viewer_returns_403(client, mock_db):
    patchers = _login_role(client, username="int_viewer", password="p", role="viewer")
    try:
        resp = client.get("/integrations/status")
    finally:
        _stop_patchers(patchers)

    assert resp.status_code == 403
    assert resp.get_json()["error"] == "forbidden"


def test_integration_status_analyst_can_read(client, mock_db, monkeypatch):
    _deny_network(monkeypatch)
    patchers = _login_role(client, username="int_analyst", password="p", role="analyst")
    try:
        resp = client.get("/integrations/status")
    finally:
        _stop_patchers(patchers)

    assert resp.status_code == 200
    _assert_status_shape(resp.get_json())


def test_integration_status_super_admin_can_read(client, mock_db, monkeypatch):
    _deny_network(monkeypatch)
    _login_super_admin(client)

    resp = client.get("/integrations/status")

    assert resp.status_code == 200
    _assert_status_shape(resp.get_json())


def test_integration_status_does_not_require_secrets(client, mock_db, monkeypatch):
    for env_name in [
        "SLACK_WEBHOOK_URL",
        "TEAMS_WEBHOOK_URL",
        "SMTP_PASSWORD",
        "SENDGRID_API_KEY",
        "FIREWALL_API_TOKEN",
        "WEBHOOK_URL",
    ]:
        monkeypatch.delenv(env_name, raising=False)
    _login_super_admin(client)

    resp = client.get("/integrations/status")

    assert resp.status_code == 200
    _assert_status_shape(resp.get_json())


def test_integration_status_reports_real_mode_fail_closed(client, mock_db, monkeypatch):
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    _deny_network(monkeypatch)
    _login_super_admin(client)

    resp = client.get("/integrations/status")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["mode"] == "simulation"
    assert data["configured_mode"] == "real"
    assert data["simulated"] is True
    assert data["real_mode_enabled"] is False
    assert data["real_mode_allowed"] is False
    assert data["real_mode_ready"] is False
    assert "SOAR_ENV" in data["real_mode_status"]
    assert "SOAR_REAL_SLACK_ENABLED" in data["real_mode_status"]


def test_integration_status_slack_real_readiness_uses_safe_booleans(
    client, mock_db, monkeypatch
):
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_SLACK_ENABLED", "true")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T000/B000/SECRET")
    _deny_network(monkeypatch)
    _login_super_admin(client)

    resp = client.get("/integrations/status")

    assert resp.status_code == 200
    data = resp.get_json()
    rendered = json.dumps(data, sort_keys=True)
    assert data["mode"] == "real"
    assert data["configured_mode"] == "real"
    assert data["real_mode_enabled"] is True
    assert data["slack_configured"] is True
    assert data["real_mode_allowed"] is True
    assert data["real_mode_ready"] is True
    adapters = {adapter["name"]: adapter for adapter in data["adapters"]}
    assert adapters["slack"]["mode"] == "real"
    assert adapters["slack"]["real_client"] is True
    assert adapters["slack"]["webhook_configured"] is True
    assert adapters["email"]["mode"] == "simulation"
    assert adapters["firewall"]["mode"] == "simulation"
    assert adapters["teams"]["mode"] == "simulation"
    assert adapters["webhook"]["mode"] == "simulation"
    assert "hooks.slack.com/services" not in rendered
    assert "SECRET" not in rendered


def test_integration_status_slack_missing_webhook_not_ready(client, mock_db, monkeypatch):
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_SLACK_ENABLED", "true")
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    _deny_network(monkeypatch)
    _login_super_admin(client)

    resp = client.get("/integrations/status")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["mode"] == "simulation"
    assert data["slack_configured"] is False
    assert data["real_mode_allowed"] is False
    assert data["real_mode_ready"] is False
    adapters = {adapter["name"]: adapter for adapter in data["adapters"]}
    assert adapters["slack"]["webhook_configured"] is False
    assert adapters["slack"]["real_mode_ready"] is False


def test_integration_status_teams_real_readiness_uses_safe_booleans(
    client, mock_db, monkeypatch
):
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_TEAMS_ENABLED", "true")
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://contoso.webhook.office.com/webhookb2/SECRET")
    _deny_network(monkeypatch)
    _login_super_admin(client)

    resp = client.get("/integrations/status")

    assert resp.status_code == 200
    data = resp.get_json()
    rendered = json.dumps(data, sort_keys=True)
    assert data["mode"] == "simulation"
    assert data["configured_mode"] == "real"
    assert data["real_mode_enabled"] is False
    assert data["teams_configured"] is True
    assert data["real_mode_allowed"] is False
    assert data["real_mode_ready"] is False
    adapters = {adapter["name"]: adapter for adapter in data["adapters"]}
    assert adapters["teams"]["mode"] == "simulation"
    assert adapters["teams"]["real_client"] is False
    assert adapters["teams"]["simulation_only"] is True
    assert adapters["teams"]["real_mode_ready"] is False
    assert adapters["teams"]["webhook_configured"] is True
    assert adapters["slack"]["mode"] == "simulation"
    assert adapters["email"]["mode"] == "simulation"
    assert adapters["firewall"]["mode"] == "simulation"
    assert adapters["webhook"]["mode"] == "simulation"
    assert "webhook.office.com" not in rendered
    assert "SECRET" not in rendered


def test_integration_status_teams_missing_webhook_not_ready(client, mock_db, monkeypatch):
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_TEAMS_ENABLED", "true")
    monkeypatch.delenv("TEAMS_WEBHOOK_URL", raising=False)
    _deny_network(monkeypatch)
    _login_super_admin(client)

    resp = client.get("/integrations/status")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["mode"] == "simulation"
    assert data["teams_configured"] is False
    assert data["real_mode_allowed"] is False
    assert data["real_mode_ready"] is False
    adapters = {adapter["name"]: adapter for adapter in data["adapters"]}
    assert adapters["teams"]["webhook_configured"] is False
    assert adapters["teams"]["real_mode_ready"] is False


def test_integration_status_email_real_readiness_uses_safe_booleans(
    client, mock_db, monkeypatch
):
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_EMAIL_ENABLED", "true")
    monkeypatch.setenv("SMTP_HOST", "smtp.staging.local")
    monkeypatch.setenv("SMTP_USERNAME", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-secret")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "soar@example.com")
    monkeypatch.setenv("SMTP_TO_EMAIL", "analyst@example.com")
    _deny_network(monkeypatch)
    _login_super_admin(client)

    resp = client.get("/integrations/status")

    assert resp.status_code == 200
    data = resp.get_json()
    rendered = json.dumps(data, sort_keys=True)
    assert data["mode"] == "real"
    assert data["configured_mode"] == "real"
    assert data["real_mode_enabled"] is True
    assert data["smtp_configured"] is True
    assert data["email_real_enabled"] is True
    assert data["real_mode_allowed"] is True
    assert data["real_mode_ready"] is True
    adapters = {adapter["name"]: adapter for adapter in data["adapters"]}
    assert adapters["email"]["mode"] == "real"
    assert adapters["email"]["real_client"] is True
    assert adapters["email"]["smtp_configured"] is True
    assert adapters["email"]["email_real_enabled"] is True
    assert adapters["slack"]["mode"] == "simulation"
    assert adapters["teams"]["mode"] == "simulation"
    assert adapters["firewall"]["mode"] == "simulation"
    assert adapters["webhook"]["mode"] == "simulation"
    assert "smtp.staging.local" not in rendered
    assert "smtp-user" not in rendered
    assert "smtp-secret" not in rendered


def test_integration_status_email_missing_smtp_host_not_ready(
    client, mock_db, monkeypatch
):
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_EMAIL_ENABLED", "true")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.setenv("SMTP_USERNAME", "smtp-user")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "soar@example.com")
    monkeypatch.setenv("SMTP_TO_EMAIL", "analyst@example.com")
    _deny_network(monkeypatch)
    _login_super_admin(client)

    resp = client.get("/integrations/status")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["mode"] == "simulation"
    assert data["smtp_configured"] is False
    assert data["real_mode_ready"] is False
    adapters = {adapter["name"]: adapter for adapter in data["adapters"]}
    assert adapters["email"]["smtp_configured"] is False
    assert adapters["email"]["smtp_host_configured"] is False
    assert adapters["email"]["real_mode_ready"] is False


def test_integration_status_webhook_real_readiness_uses_safe_booleans(
    client, mock_db, monkeypatch
):
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_WEBHOOK_ENABLED", "true")
    monkeypatch.setenv("WEBHOOK_URL", "https://events.staging.example/hooks/soar")
    monkeypatch.setenv("WEBHOOK_AUTH_TOKEN", "webhook-secret")
    _deny_network(monkeypatch)
    _login_super_admin(client)

    resp = client.get("/integrations/status")

    assert resp.status_code == 200
    data = resp.get_json()
    rendered = json.dumps(data, sort_keys=True)
    assert data["configured_mode"] == "real"
    assert data["real_mode_enabled"] is True
    adapters = {adapter["name"]: adapter for adapter in data["adapters"]}
    assert adapters["webhook"]["mode"] == "real"
    assert adapters["webhook"]["real_client"] is True
    assert adapters["webhook"]["webhook_url_configured"] is True
    assert adapters["webhook"]["webhook_real_enabled"] is True
    assert adapters["slack"]["mode"] == "simulation"
    assert "events.staging.example" not in rendered
    assert "webhook-secret" not in rendered


def test_integration_status_webhook_invalid_target_not_ready(client, mock_db, monkeypatch):
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_WEBHOOK_ENABLED", "true")
    monkeypatch.setenv("WEBHOOK_URL", "https://127.0.0.1/hooks/soar")
    _deny_network(monkeypatch)
    _login_super_admin(client)

    resp = client.get("/integrations/status")

    assert resp.status_code == 200
    data = resp.get_json()
    rendered = json.dumps(data, sort_keys=True)
    adapters = {adapter["name"]: adapter for adapter in data["adapters"]}
    assert adapters["webhook"]["webhook_url_configured"] is True
    assert adapters["webhook"]["real_mode_ready"] is False
    assert "127.0.0.1" not in rendered


def test_integration_status_firewall_never_implies_real_mode(
    client, mock_db, monkeypatch
):
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_FIREWALL_ENABLED", "true")
    monkeypatch.setenv("FIREWALL_API_TOKEN", "firewall-secret")
    _deny_network(monkeypatch)
    _login_super_admin(client)

    resp = client.get("/integrations/status")

    assert resp.status_code == 200
    data = resp.get_json()
    adapters = {adapter["name"]: adapter for adapter in data["adapters"]}
    assert adapters["firewall"]["mode"] == "simulation"
    assert adapters["firewall"]["real_client"] is False
    assert adapters["firewall"]["real_mode_available"] is False
    assert adapters["firewall"]["real_mode_allowed"] is False
    assert adapters["firewall"]["real_mode_ready"] is False
    assert "separate approved OpenSpec" in adapters["firewall"]["real_mode_status"]
    assert "firewall-secret" not in json.dumps(data, sort_keys=True)


def test_integration_status_slack_and_teams_config_are_independent(
    client, mock_db, monkeypatch
):
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_TEAMS_ENABLED", "true")
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://contoso.webhook.office.com/webhookb2/SECRET")
    monkeypatch.delenv("SOAR_REAL_SLACK_ENABLED", raising=False)
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    _deny_network(monkeypatch)
    _login_super_admin(client)

    resp = client.get("/integrations/status")

    assert resp.status_code == 200
    data = resp.get_json()
    adapters = {adapter["name"]: adapter for adapter in data["adapters"]}
    assert adapters["teams"]["real_mode_ready"] is False
    assert adapters["teams"]["simulation_only"] is True
    assert adapters["teams"]["mode"] == "simulation"
    assert adapters["slack"]["real_mode_ready"] is False
    assert adapters["slack"]["mode"] == "simulation"
    rendered = json.dumps(data, sort_keys=True)
    assert "webhook.office.com" not in rendered
    assert "SECRET" not in rendered


def test_circuit_breaker_reset_requires_auth(client):
    resp = client.post("/integrations/slack/circuit-breaker/reset", json={"reason": "x"})
    assert resp.status_code == 401


def test_notification_readiness_requires_login(client):
    resp = client.get("/integrations/notification-readiness")

    assert resp.status_code == 401


def test_notification_readiness_viewer_forbidden(client, mock_db):
    patchers = _login_role(client, username="ready_viewer", password="p", role="viewer")
    try:
        resp = client.get("/integrations/notification-readiness")
    finally:
        _stop_patchers(patchers)

    assert resp.status_code == 403


def test_notification_readiness_route_returns_provider_shape(client, mock_db):
    _login_super_admin(client)
    payload = {
        "providers": [
            {
                "provider": "slack",
                "label": "Slack",
                "configured": True,
                "missing_configuration": [],
                "tested": "passed",
                "ready": True,
                "last_test_at": "2026-07-08T00:00:00+00:00",
                "last_test_status": "success",
                "last_test_message": None,
                "last_test_failure_code": None,
            },
            {
                "provider": "teams",
                "label": "Teams",
                "configured": True,
                "missing_configuration": [],
                "tested": "never_tested",
                "ready": False,
                "last_test_at": "2026-07-08T00:01:00+00:00",
                "last_test_status": "blocked",
                "last_test_message": "blocked by guard",
                "last_test_failure_code": "guard_failed",
            },
        ]
    }
    conn = Mock()
    with patch("routes.integration_routes.get_db_connection", return_value=conn), patch(
        "routes.integration_routes.get_notification_readiness",
        return_value=payload,
    ) as readiness:
        resp = client.get("/integrations/notification-readiness")

    assert resp.status_code == 200
    assert resp.get_json() == payload
    readiness.assert_called_once_with(conn)
    conn.close.assert_called_once()


def test_notification_test_send_requires_super_admin(client, mock_db):
    patchers = _login_role(client, username="ready_analyst", password="p", role="analyst")
    try:
        resp = client.post("/integrations/slack/test-send", json={})
    finally:
        _stop_patchers(patchers)

    assert resp.status_code == 403


@pytest.mark.parametrize("adapter_name", ["firewall", "unknown"])
def test_notification_test_send_rejects_firewall_and_unknown(client, mock_db, adapter_name):
    _login_super_admin(client)
    conn = Mock()
    with patch("routes.integration_routes.get_db_connection", return_value=conn):
        resp = client.post(f"/integrations/{adapter_name}/test-send", json={})

    assert resp.status_code == 404
    assert resp.get_json()["error"] == "not_found"
    conn.rollback.assert_called_once()


@pytest.mark.parametrize(
    ("outcome", "tested", "attempt_status"),
    [
        ("success", "passed", "success"),
        ("test_failed", "failed", "failed"),
        ("guard_blocked", "never_tested", "blocked"),
        ("not_configured", "never_tested", None),
    ],
)
def test_notification_test_send_route_returns_outcome_shape(
    client, mock_db, outcome, tested, attempt_status
):
    _login_super_admin(client)
    conn = Mock()
    payload = {
        "provider": "slack",
        "label": "Slack",
        "configured": outcome != "not_configured",
        "missing_configuration": [] if outcome != "not_configured" else ["SLACK_WEBHOOK_URL"],
        "tested": tested,
        "ready": tested == "passed",
        "outcome": outcome,
        "message": "result",
        "attempt": None if attempt_status is None else {"status": attempt_status},
    }
    with patch("routes.integration_routes.get_db_connection", return_value=conn), patch(
        "routes.integration_routes.send_notification_test",
        return_value=payload,
    ) as send_test:
        resp = client.post("/integrations/slack/test-send", json={})

    assert resp.status_code == 200
    assert resp.get_json() == payload
    send_test.assert_called_once_with(conn, "slack")
    conn.commit.assert_called_once()


def test_circuit_breaker_reset_forbidden_for_viewer(client, mock_db):
    patchers = _login_role(client, username="cb_viewer", password="p", role="viewer")
    try:
        resp = client.post("/integrations/slack/circuit-breaker/reset", json={"reason": "x"})
    finally:
        _stop_patchers(patchers)
    assert resp.status_code == 403


def test_circuit_breaker_reset_forbidden_for_analyst(client, mock_db):
    patchers = _login_role(client, username="cb_analyst", password="p", role="analyst")
    try:
        resp = client.post("/integrations/slack/circuit-breaker/reset", json={"reason": "x"})
    finally:
        _stop_patchers(patchers)
    assert resp.status_code == 403


def test_circuit_breaker_unknown_adapter_returns_404(client, mock_db):
    _login_super_admin(client)
    resp = client.post(
        "/integrations/pagerduty/circuit-breaker/reset",
        json={"reason": "x"},
    )
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "not_found"


def test_circuit_breaker_reset_requires_reason(client, mock_db):
    _login_super_admin(client)
    resp = client.post("/integrations/slack/circuit-breaker/reset", json={})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_body"


def test_circuit_breaker_reset_super_admin_returns_updated_state_and_writes_audit(
    client, postgres_db, monkeypatch
):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)
    conn, cur = postgres_db
    configure_simulated_circuit_breaker("slack", state=CIRCUIT_STATE_OPEN, consecutive_failures=2)
    with _patched_audit_db(conn):
        _login_super_admin(client)
        resp = client.post(
            "/integrations/slack/circuit-breaker/reset",
            json={"reason": "operator cleared simulation breaker"},
        )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["adapter"] == "slack"
    assert body["circuit_breaker"]["state"] == CIRCUIT_STATE_CLOSED
    assert body["circuit_breaker"]["last_manual_action"] == "reset"
    cur.execute(
        """
        SELECT event_type, actor_username, details
        FROM audit_log
        WHERE event_type = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        ("SIMULATION_CIRCUIT_BREAKER_RESET",),
    )
    row = cur.fetchone()
    assert row is not None
    assert row[0] == "SIMULATION_CIRCUIT_BREAKER_RESET"
    assert row[1] == "admin"
    details = row[2]
    assert details["adapter"] == "slack"
    assert details["previous_state"] == CIRCUIT_STATE_OPEN
    assert details["new_state"] == CIRCUIT_STATE_CLOSED
    assert "operator cleared" in details["reason"]


def test_circuit_breaker_force_open_super_admin_writes_audit(client, postgres_db, monkeypatch):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)
    conn, cur = postgres_db
    with _patched_audit_db(conn):
        _login_super_admin(client)
        resp = client.post(
            "/integrations/webhook/circuit-breaker/force-open",
            json={"reason": "containment drill"},
        )
    assert resp.status_code == 200
    assert resp.get_json()["circuit_breaker"]["state"] == CIRCUIT_STATE_OPEN
    cur.execute(
        "SELECT COUNT(*) FROM audit_log WHERE event_type = %s",
        ("SIMULATION_CIRCUIT_BREAKER_FORCE_OPEN",),
    )
    assert cur.fetchone()[0] >= 1


def test_circuit_breaker_enable_half_open_during_cooldown_requires_override(
    client, postgres_db, monkeypatch
):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)
    conn, cur = postgres_db
    t0 = datetime.now(timezone.utc)
    configure_simulated_circuit_breaker(
        "email",
        state=CIRCUIT_STATE_OPEN,
        cooldown_until=t0 + timedelta(hours=1),
    )
    with _patched_audit_db(conn):
        _login_super_admin(client)
        denied = client.post(
            "/integrations/email/circuit-breaker/enable-half-open",
            json={"reason": "too early"},
        )
        assert denied.status_code == 409
        ok = client.post(
            "/integrations/email/circuit-breaker/enable-half-open",
            json={"reason": "super-admin override", "override_cooldown": True},
        )
    assert ok.status_code == 200
    assert ok.get_json()["circuit_breaker"]["state"] == "half_open"
    assert ok.get_json()["circuit_breaker"]["half_open_probe_available"] is True
    cur.execute(
        "SELECT COUNT(*) FROM audit_log WHERE event_type = %s",
        ("SIMULATION_CIRCUIT_BREAKER_ENABLE_HALF_OPEN",),
    )
    assert cur.fetchone()[0] >= 1


def test_integration_status_read_is_idempotent_for_breaker_state(client, mock_db, monkeypatch):
    _deny_network(monkeypatch)
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)
    configure_simulated_circuit_breaker("slack", state=CIRCUIT_STATE_OPEN, consecutive_failures=1)
    patchers = _login_role(client, username="cb_analyst2", password="p", role="analyst")
    try:
        before = get_simulated_circuit_breaker_dict("slack")["state"]
        r1 = client.get("/integrations/status")
        r2 = client.get("/integrations/status")
    finally:
        _stop_patchers(patchers)
    assert r1.status_code == 200 and r2.status_code == 200
    assert get_simulated_circuit_breaker_dict("slack")["state"] == before


def test_circuit_control_does_not_touch_blocked_ips(client, postgres_db, monkeypatch):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO blocked_ips (ip_address, reason, status)
        VALUES ('192.0.2.10'::inet, 'test', 'active')
        """
    )
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM blocked_ips")
    n = cur.fetchone()[0]
    with _patched_audit_db(conn):
        _login_super_admin(client)
        resp = client.post(
            "/integrations/firewall/circuit-breaker/force-open",
            json={"reason": "no firewall mutation expected"},
        )
    assert resp.status_code == 200
    cur.execute("SELECT COUNT(*) FROM blocked_ips")
    assert cur.fetchone()[0] == n


def test_circuit_control_does_not_instantiate_adapter(client, postgres_db, monkeypatch):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)
    conn, cur = postgres_db
    with _patched_audit_db(conn), patch(
        "integrations.integration_registry.get_integration_adapter",
        side_effect=AssertionError("adapter must not be constructed for breaker controls"),
    ):
        _login_super_admin(client)
        resp = client.post(
            "/integrations/slack/circuit-breaker/reset",
            json={"reason": "no adapter"},
        )
    assert resp.status_code == 200
