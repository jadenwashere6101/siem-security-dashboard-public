import http.client
import smtplib
import socket

import pytest

from integrations.integration_registry import (
    get_integration_adapter,
    list_integration_adapters,
    resolve_integration_mode,
)


EXPECTED_RESULT_KEYS = {
    "adapter",
    "action",
    "mode",
    "simulated",
    "executed",
    "success",
    "message",
    "params",
    "context",
    "metadata",
}


@pytest.fixture
def no_network(monkeypatch):
    def fail_network(*_args, **_kwargs):
        raise AssertionError("network call attempted in simulation adapter")

    monkeypatch.setattr(socket, "socket", fail_network)
    monkeypatch.setattr(smtplib, "SMTP", fail_network)
    monkeypatch.setattr(smtplib, "SMTP_SSL", fail_network)
    monkeypatch.setattr(http.client.HTTPConnection, "request", fail_network)
    monkeypatch.setattr(http.client.HTTPSConnection, "request", fail_network)


def test_integration_mode_defaults_to_simulation(monkeypatch):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)

    assert resolve_integration_mode() == "simulation"


def test_non_simulation_mode_fails_closed(monkeypatch):
    monkeypatch.setenv("INTEGRATION_MODE", "real")

    with pytest.raises(NotImplementedError, match="real integration mode is not implemented"):
        resolve_integration_mode()


def test_registry_returns_simulation_adapters_case_insensitive(monkeypatch):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)

    assert get_integration_adapter("SLACK").adapter_name == "slack"
    assert get_integration_adapter("email").adapter_name == "email"
    assert get_integration_adapter("Firewall").adapter_name == "firewall"
    assert get_integration_adapter("webhook").adapter_name == "webhook"


def test_list_integration_adapters_defaults_to_simulation(monkeypatch):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)

    adapters = list_integration_adapters()

    assert set(adapters) == {"email", "firewall", "slack", "webhook"}
    assert {adapter.mode for adapter in adapters.values()} == {"simulation"}


def test_unknown_adapter_fails_locally():
    with pytest.raises(ValueError, match="unknown integration adapter"):
        get_integration_adapter("pagerduty")


@pytest.mark.parametrize(
    ("adapter_name", "action"),
    [
        ("slack", "send_message"),
        ("email", "send_email"),
        ("firewall", "block_ip"),
        ("webhook", "post_event"),
    ],
)
def test_simulation_adapters_return_stable_result_shape(no_network, adapter_name, action):
    adapter = get_integration_adapter(adapter_name)

    result = adapter.execute(
        action,
        params={"message": "hello", "token": "secret-token"},
        context={"alert_id": 123, "password": "secret-password"},
    )

    assert set(result) == EXPECTED_RESULT_KEYS
    assert result["adapter"] == adapter_name
    assert result["action"] == action
    assert result["mode"] == "simulation"
    assert result["simulated"] is True
    assert result["executed"] is False
    assert result["success"] is True
    assert result["params"]["token"] == "[redacted]"
    assert result["context"]["password"] == "[redacted]"


@pytest.mark.parametrize("adapter_name", ["slack", "email", "firewall", "webhook"])
def test_unsupported_actions_return_simulated_failure(no_network, adapter_name):
    adapter = get_integration_adapter(adapter_name)

    result = adapter.execute("unsupported_action", params={"secret": "value"})

    assert set(result) == EXPECTED_RESULT_KEYS
    assert result["mode"] == "simulation"
    assert result["simulated"] is True
    assert result["executed"] is False
    assert result["success"] is False
    assert "Unsupported simulated" in result["message"]
    assert result["params"]["secret"] == "[redacted]"


def test_simulation_adapters_do_not_require_secrets(monkeypatch, no_network):
    for env_name in [
        "SLACK_WEBHOOK_URL",
        "SMTP_PASSWORD",
        "SENDGRID_API_KEY",
        "FIREWALL_API_TOKEN",
        "WEBHOOK_URL",
    ]:
        monkeypatch.delenv(env_name, raising=False)

    for adapter_name, action in [
        ("slack", "notify_channel"),
        ("email", "notify_owner"),
        ("firewall", "tag_ip"),
        ("webhook", "send_webhook"),
    ]:
        result = get_integration_adapter(adapter_name).execute(action)
        assert result["success"] is True
        assert result["simulated"] is True
        assert result["executed"] is False


@pytest.mark.usefixtures("postgres_db")
def test_firewall_simulation_does_not_mutate_blocked_ips_or_queue(postgres_db, no_network):
    conn, cur = postgres_db
    cur.execute("SELECT COUNT(*) FROM blocked_ips")
    blocked_before = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM response_actions_queue")
    queue_before = cur.fetchone()[0]

    result = get_integration_adapter("firewall").execute(
        "block_ip",
        params={"source_ip": "203.0.113.10"},
        context={"alert_id": 55},
    )

    assert result["success"] is True
    cur.execute("SELECT COUNT(*) FROM blocked_ips")
    assert cur.fetchone()[0] == blocked_before
    cur.execute("SELECT COUNT(*) FROM response_actions_queue")
    assert cur.fetchone()[0] == queue_before
