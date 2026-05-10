import http.client
import smtplib
import socket
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from integrations.base_integration import (
    CIRCUIT_STATE_CLOSED,
    CIRCUIT_STATE_HALF_OPEN,
    CIRCUIT_STATE_OPEN,
    FAILURE_CLASSIFICATION_CIRCUIT_OPEN,
    FAILURE_CLASSIFICATION_CIRCUIT_STATE_INVALID,
    FAILURE_CLASSIFICATION_NON_TRANSIENT,
    FAILURE_CLASSIFICATION_TRANSIENT,
    configure_simulated_circuit_breaker,
    get_simulated_circuit_breaker_dict,
    record_simulated_adapter_failure,
    record_simulated_adapter_success,
    request_half_open_probe,
    reset_simulated_circuit_breakers,
)
from integrations.integration_registry import (
    get_integration_adapter,
    get_integration_status,
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


@pytest.fixture(autouse=True)
def _reset_integration_circuits():
    reset_simulated_circuit_breakers()
    yield
    reset_simulated_circuit_breakers()


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


def test_integration_status_metadata_is_offline_and_simulation_only(monkeypatch, no_network):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)

    status = get_integration_status()

    assert status["mode"] == "simulation"
    assert status["configured_mode"] == "simulation"
    assert status["simulated"] is True
    assert status["real_mode_enabled"] is False
    assert status["real_mode_status"] == "disabled"
    adapters = {adapter["name"]: adapter for adapter in status["adapters"]}
    assert set(adapters) == {"email", "firewall", "slack", "webhook"}
    assert adapters["slack"]["supported_actions"] == ["notify_channel", "send_message"]
    assert adapters["email"]["supported_actions"] == ["notify_owner", "send_email"]
    assert adapters["firewall"]["supported_actions"] == ["block_ip", "tag_ip", "unblock_ip"]
    assert adapters["webhook"]["supported_actions"] == [
        "notify_webhook",
        "post_event",
        "send_webhook",
    ]
    assert {adapter["real_client"] for adapter in adapters.values()} == {False}


def test_integration_status_reports_real_mode_fail_closed(monkeypatch, no_network):
    monkeypatch.setenv("INTEGRATION_MODE", "real")

    status = get_integration_status()

    assert status["mode"] == "simulation"
    assert status["configured_mode"] == "real"
    assert status["simulated"] is True
    assert status["real_mode_enabled"] is False
    assert "not implemented" in status["real_mode_status"]


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
    assert result["metadata"].get("circuit_state") == CIRCUIT_STATE_CLOSED


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


def test_initial_circuit_state_is_closed(monkeypatch, no_network):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)
    snap = get_simulated_circuit_breaker_dict("slack")
    assert snap["state"] == CIRCUIT_STATE_CLOSED
    assert snap["consecutive_failures"] == 0
    assert snap["retry_eligible"] is True


def test_consecutive_transient_failures_open_breaker(monkeypatch, no_network):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)
    configure_simulated_circuit_breaker("webhook", failure_threshold=3)
    for i in range(2):
        record_simulated_adapter_failure(
            "webhook",
            reason=f"err {i}",
            classification=FAILURE_CLASSIFICATION_TRANSIENT,
        )
    st = get_simulated_circuit_breaker_dict("webhook")
    assert st["state"] == CIRCUIT_STATE_CLOSED
    assert st["consecutive_failures"] == 2
    record_simulated_adapter_failure(
        "webhook",
        reason="err final",
        classification=FAILURE_CLASSIFICATION_TRANSIENT,
    )
    st = get_simulated_circuit_breaker_dict("webhook")
    assert st["state"] == CIRCUIT_STATE_OPEN
    assert st["opened_at"] is not None
    assert st["cooldown_until"] is not None


def test_open_breaker_fails_closed_without_calling_simulate(monkeypatch, no_network):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)
    configure_simulated_circuit_breaker("slack", state=CIRCUIT_STATE_OPEN, consecutive_failures=3)
    adapter = get_integration_adapter("slack")
    with patch.object(adapter, "_simulate", side_effect=AssertionError("_simulate must not run")):
        result = adapter.execute("send_message", params={})
    assert result["success"] is False
    assert result["metadata"]["failure_classification"] == FAILURE_CLASSIFICATION_CIRCUIT_OPEN
    assert result["metadata"]["retry_eligible"] is False


def test_cooldown_expiration_does_not_auto_half_open(monkeypatch, no_network):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)
    t0 = datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc)
    configure_simulated_circuit_breaker(
        "email",
        state=CIRCUIT_STATE_OPEN,
        consecutive_failures=3,
        opened_at=t0,
        cooldown_until=t0 + timedelta(seconds=30),
    )
    later = t0 + timedelta(minutes=5)
    st = get_simulated_circuit_breaker_dict("email", now=later)
    assert st["state"] == CIRCUIT_STATE_OPEN
    assert request_half_open_probe("email", now=later) is True
    assert get_simulated_circuit_breaker_dict("email", now=later)["state"] == CIRCUIT_STATE_HALF_OPEN


def test_half_open_probe_success_closes_breaker(monkeypatch, no_network):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)
    t0 = datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc)
    configure_simulated_circuit_breaker(
        "firewall",
        state=CIRCUIT_STATE_HALF_OPEN,
        consecutive_failures=3,
        cooldown_until=t0,
    )
    adapter = get_integration_adapter("firewall")
    result = adapter.execute("tag_ip", params={})
    assert result["success"] is True
    assert get_simulated_circuit_breaker_dict("firewall")["state"] == CIRCUIT_STATE_CLOSED
    assert get_simulated_circuit_breaker_dict("firewall")["consecutive_failures"] == 0


def test_half_open_probe_failure_reopens_breaker(monkeypatch, no_network):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)
    t0 = datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc)
    configure_simulated_circuit_breaker(
        "slack",
        state=CIRCUIT_STATE_HALF_OPEN,
        consecutive_failures=3,
        cooldown_until=t0,
    )
    adapter = get_integration_adapter("slack")

    with patch.object(
        adapter,
        "_simulate",
        side_effect=lambda action, params, context: adapter._result(
            action,
            params,
            context,
            success=False,
            message="simulated outage",
            metadata={"failure_classification": FAILURE_CLASSIFICATION_TRANSIENT},
        ),
    ):
        result = adapter.execute("send_message", params={})
    assert result["success"] is False
    assert get_simulated_circuit_breaker_dict("slack")["state"] == CIRCUIT_STATE_OPEN


def test_timeout_metadata_recorded_without_timers(monkeypatch, no_network):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)
    configure_simulated_circuit_breaker("webhook", timeout_seconds=42)
    adapter = get_integration_adapter("webhook")
    result = adapter.execute(
        "post_event",
        params={},
        context={},
    )
    assert result["metadata"].get("timeout_seconds") == 42
    assert result["metadata"].get("timed_out") is None


def test_non_transient_not_retry_eligible_and_may_open(monkeypatch, no_network):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)
    record_simulated_adapter_failure(
        "firewall",
        reason="bad config",
        classification=FAILURE_CLASSIFICATION_NON_TRANSIENT,
    )
    st = get_simulated_circuit_breaker_dict("firewall")
    assert st["state"] == CIRCUIT_STATE_OPEN
    assert st["retry_eligible"] is False


def test_invalid_circuit_state_fails_closed(monkeypatch, no_network):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)
    configure_simulated_circuit_breaker("webhook", state="not_a_valid_state")
    adapter = get_integration_adapter("webhook")
    result = adapter.execute("post_event", params={})
    assert result["success"] is False
    assert result["metadata"]["failure_classification"] == FAILURE_CLASSIFICATION_CIRCUIT_STATE_INVALID


def test_integration_status_includes_circuit_breaker(monkeypatch, no_network):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)
    record_simulated_adapter_success("slack")
    status = get_integration_status()
    by_name = {a["name"]: a for a in status["adapters"]}
    assert "circuit_breaker" in by_name["slack"]
    cb = by_name["slack"]["circuit_breaker"]
    assert cb["state"] == CIRCUIT_STATE_CLOSED
    assert "consecutive_failures" in cb
    assert "failure_threshold" in cb
    assert "cooldown_seconds" in cb
    assert "retry_eligible" in cb
    assert cb["state_persisted"] is False


def test_request_half_open_before_cooldown_fails(monkeypatch, no_network):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)
    t0 = datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc)
    configure_simulated_circuit_breaker(
        "email",
        state=CIRCUIT_STATE_OPEN,
        cooldown_until=t0 + timedelta(seconds=120),
    )
    assert request_half_open_probe("email", now=t0) is False
    assert get_simulated_circuit_breaker_dict("email", now=t0)["state"] == CIRCUIT_STATE_OPEN
