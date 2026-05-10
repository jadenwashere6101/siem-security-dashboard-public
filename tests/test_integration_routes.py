import http.client
import smtplib
import socket
from unittest.mock import patch

from werkzeug.security import generate_password_hash


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


def _deny_network(monkeypatch):
    def fail_network(*_args, **_kwargs):
        raise AssertionError("network call attempted by integration status route")

    monkeypatch.setattr(socket, "socket", fail_network)
    monkeypatch.setattr(smtplib, "SMTP", fail_network)
    monkeypatch.setattr(smtplib, "SMTP_SSL", fail_network)
    monkeypatch.setattr(http.client.HTTPConnection, "request", fail_network)
    monkeypatch.setattr(http.client.HTTPSConnection, "request", fail_network)


def _assert_status_shape(data):
    assert data["mode"] == "simulation"
    assert data["simulated"] is True
    assert data["real_mode_enabled"] is False
    assert data["real_mode_status"]
    adapters = {adapter["name"]: adapter for adapter in data["adapters"]}
    assert set(adapters) == {"email", "firewall", "slack", "webhook"}
    assert adapters["slack"]["supported_actions"] == ["notify_channel", "send_message"]
    assert adapters["email"]["supported_actions"] == ["notify_owner", "send_email"]
    assert adapters["firewall"]["supported_actions"] == ["block_ip", "tag_ip", "unblock_ip"]
    assert adapters["webhook"]["supported_actions"] == [
        "notify_webhook",
        "post_event",
        "send_webhook",
    ]
    assert {adapter["mode"] for adapter in adapters.values()} == {"simulation"}
    assert {adapter["simulated"] for adapter in adapters.values()} == {True}
    assert {adapter["real_client"] for adapter in adapters.values()} == {False}


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
    assert "not implemented" in data["real_mode_status"]
