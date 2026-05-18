import http.client
import json
import logging
import smtplib
import socket
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from core.integration_audit import build_integration_attempt_audit_details
from integrations.base_integration import (
    CIRCUIT_STATE_CLOSED,
    CIRCUIT_STATE_HALF_OPEN,
    CIRCUIT_STATE_OPEN,
    FAILURE_CLASSIFICATION_CIRCUIT_OPEN,
    FAILURE_CLASSIFICATION_CIRCUIT_STATE_INVALID,
    FAILURE_CLASSIFICATION_CREDENTIAL_MISSING,
    FAILURE_CLASSIFICATION_GUARD_FAILED,
    FAILURE_CLASSIFICATION_NON_TRANSIENT,
    FAILURE_CLASSIFICATION_TRANSIENT,
    SimulatedCircuitBreakerControlError,
    configure_simulated_circuit_breaker,
    get_simulated_circuit_breaker_dict,
    manual_enable_half_open_probe_simulated_circuit_breaker,
    manual_force_open_simulated_circuit_breaker,
    manual_reset_simulated_circuit_breaker,
    record_simulated_adapter_failure,
    record_simulated_adapter_success,
    request_half_open_probe,
    reset_simulated_circuit_breakers,
    _validate_real_mode_guards,
)
from integrations.integration_registry import (
    get_integration_adapter,
    get_integration_status,
    list_integration_adapters,
    normalize_registered_integration_adapter_name,
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
    monkeypatch.setattr(urllib.request, "urlopen", fail_network)


def test_integration_mode_defaults_to_simulation(monkeypatch):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)

    assert resolve_integration_mode() == "simulation"


def test_non_simulation_mode_fails_closed(monkeypatch):
    monkeypatch.setenv("INTEGRATION_MODE", "real")

    assert resolve_integration_mode() == "real"
    for adapter_name in ("slack", "teams"):
        adapter = get_integration_adapter(adapter_name)
        result = adapter.execute("send_message")
        assert adapter.mode == "real"
        assert result["success"] is False
        assert result["simulated"] is True
        assert result["executed"] is False
        assert result["metadata"]["real_mode_ready"] is False


def test_real_mode_guard_helper_reports_each_missing_guard(monkeypatch):
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.delenv("SOAR_ENV", raising=False)
    monkeypatch.delenv("SOAR_REAL_EMAIL_ENABLED", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_USERNAME", raising=False)

    result = _validate_real_mode_guards(
        "email",
        enabled_env="SOAR_REAL_EMAIL_ENABLED",
        credential_envs=("SMTP_HOST", "SMTP_USERNAME"),
    )

    assert result["real_mode_allowed"] is False
    assert result["failure_classification"] == FAILURE_CLASSIFICATION_CREDENTIAL_MISSING
    assert result["missing_guards"] == [
        "SOAR_ENV",
        "SOAR_REAL_EMAIL_ENABLED",
        "SMTP_HOST",
        "SMTP_USERNAME",
    ]
    assert result["credential_envs"] == ["SMTP_HOST", "SMTP_USERNAME"]


def test_real_mode_guard_helper_missing_mode_fails_closed(monkeypatch):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_SLACK_ENABLED", "true")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T000/B000/SECRET")

    result = _validate_real_mode_guards(
        "slack",
        enabled_env="SOAR_REAL_SLACK_ENABLED",
        credential_envs=("SLACK_WEBHOOK_URL",),
    )

    assert result["real_mode_allowed"] is False
    assert result["failure_classification"] == FAILURE_CLASSIFICATION_GUARD_FAILED
    assert result["missing_guards"] == ["INTEGRATION_MODE"]


def test_real_mode_guard_helper_all_guards_present(monkeypatch):
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_TEAMS_ENABLED", "true")
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://contoso.webhook.office.com/webhookb2/SECRET")

    result = _validate_real_mode_guards(
        "teams",
        enabled_env="SOAR_REAL_TEAMS_ENABLED",
        credential_envs=("TEAMS_WEBHOOK_URL",),
    )

    assert result["real_mode_allowed"] is True
    assert result["real_mode_status"] == "ready"
    assert result["failure_classification"] is None
    assert result["missing_guards"] == []


def test_real_mode_guard_helper_does_not_log_credentials(monkeypatch, caplog):
    secret = "https://hooks.slack.com/services/T000/B000/VERYSECRET"
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_SLACK_ENABLED", "true")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", secret)

    with caplog.at_level(logging.INFO):
        result = _validate_real_mode_guards(
            "slack",
            enabled_env="SOAR_REAL_SLACK_ENABLED",
            credential_envs=("SLACK_WEBHOOK_URL",),
        )

    assert result["real_mode_allowed"] is True
    assert secret not in caplog.text
    assert "VERYSECRET" not in json.dumps(result, sort_keys=True)


def test_integration_attempt_audit_details_redact_secrets():
    secret_url = "https://hooks.slack.com/services/T000/B000/SECRET"
    details = build_integration_attempt_audit_details(
        {
            "adapter": "slack",
            "action": "send_message",
            "mode": "real",
            "success": False,
            "simulated": False,
            "executed": False,
            "metadata": {
                "failure_classification": "transient",
                "retry_eligible": True,
                "webhook_url": secret_url,
                "authorization": "Bearer token-secret",
                "raw_payload": {"message": "do not log"},
            },
        },
        {
            "execution_id": 44,
            "incident_id": 5,
            "alert_id": 99,
            "correlation_id": "corr-1",
            "idempotency_key": "idem-1",
            "headers": {"Authorization": "Bearer token-secret"},
            "raw_payload": {"text": secret_url},
        },
    )

    rendered = json.dumps(details, sort_keys=True)
    assert details["adapter"] == "slack"
    assert details["action"] == "send_message"
    assert details["playbook_execution_id"] == 44
    assert details["incident_id"] == 5
    assert details["alert_id"] == 99
    assert details["correlation_id"] == "corr-1"
    assert details["idempotency_key"] == "idem-1"
    assert details["failure_class"] == "transient"
    assert secret_url not in rendered
    assert "token-secret" not in rendered
    assert "raw_payload" not in rendered
    assert "authorization" not in rendered.lower()


def test_registry_startup_logs_circuit_reset_without_secrets(monkeypatch, caplog):
    secret = "https://hooks.slack.com/services/T000/B000/SECRET"
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_SLACK_ENABLED", "true")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", secret)

    with caplog.at_level(logging.INFO, logger="integrations.integration_registry"):
        status = get_integration_status()

    assert {adapter["name"] for adapter in status["adapters"]} == {
        "email",
        "firewall",
        "slack",
        "teams",
        "webhook",
    }
    log_text = caplog.text
    assert "integration_adapter_startup adapter=slack" in log_text
    assert "circuit_breaker_reset_to=closed" in log_text
    assert "SLACK_WEBHOOK_URL" in log_text
    assert secret not in log_text
    assert "SECRET" not in log_text


def test_registry_returns_simulation_adapters_case_insensitive(monkeypatch):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)

    assert get_integration_adapter("SLACK").adapter_name == "slack"
    assert get_integration_adapter("Teams").adapter_name == "teams"
    assert get_integration_adapter("email").adapter_name == "email"
    assert get_integration_adapter("Firewall").adapter_name == "firewall"
    assert get_integration_adapter("webhook").adapter_name == "webhook"


def test_list_integration_adapters_defaults_to_simulation(monkeypatch):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)

    adapters = list_integration_adapters()

    assert set(adapters) == {"email", "firewall", "slack", "teams", "webhook"}
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
    assert set(adapters) == {"email", "firewall", "slack", "teams", "webhook"}
    assert adapters["slack"]["supported_actions"] == ["notify_channel", "send_message"]
    assert adapters["teams"]["supported_actions"] == [
        "notify_channel",
        "notify_teams",
        "send_message",
    ]
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
    assert status["real_mode_allowed"] is False
    assert status["real_mode_ready"] is False
    assert "SOAR_ENV" in status["real_mode_status"]
    assert "SOAR_REAL_SLACK_ENABLED" in status["real_mode_status"]


def test_unknown_adapter_fails_locally():
    with pytest.raises(ValueError, match="unknown integration adapter"):
        get_integration_adapter("pagerduty")


@pytest.mark.parametrize(
    ("adapter_name", "action"),
    [
        ("slack", "send_message"),
        ("teams", "send_message"),
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


@pytest.mark.parametrize("adapter_name", ["slack", "teams", "email", "firewall", "webhook"])
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
        "TEAMS_WEBHOOK_URL",
        "SMTP_PASSWORD",
        "SENDGRID_API_KEY",
        "FIREWALL_API_TOKEN",
        "WEBHOOK_URL",
    ]:
        monkeypatch.delenv(env_name, raising=False)

    for adapter_name, action in [
        ("slack", "notify_channel"),
        ("teams", "notify_teams"),
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


def test_half_open_without_probe_fails_closed_without_simulate(monkeypatch, no_network):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)
    t0 = datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc)
    configure_simulated_circuit_breaker(
        "slack",
        state=CIRCUIT_STATE_HALF_OPEN,
        consecutive_failures=3,
        cooldown_until=t0,
        half_open_probe_available=False,
    )
    adapter = get_integration_adapter("slack")
    with patch.object(adapter, "_simulate", side_effect=AssertionError("_simulate must not run")):
        result = adapter.execute("send_message", params={})
    assert result["success"] is False
    assert result["metadata"]["failure_classification"] == FAILURE_CLASSIFICATION_CIRCUIT_OPEN
    assert get_simulated_circuit_breaker_dict("slack")["state"] == CIRCUIT_STATE_HALF_OPEN


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
    assert "half_open_probe_available" in cb
    assert "last_manual_action" in cb
    assert cb["state_persisted"] is False


def test_slack_real_mode_missing_webhook_fails_closed_without_network(monkeypatch, no_network):
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_SLACK_ENABLED", "true")
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)

    adapter = get_integration_adapter("slack")
    result = adapter.execute(
        "send_message",
        params={"message": "hello"},
        context={"execution_id": 1, "playbook_id": "pb"},
    )

    assert adapter.mode == "real"
    assert result["mode"] == "real"
    assert result["simulated"] is True
    assert result["executed"] is False
    assert result["success"] is False
    readiness = _validate_real_mode_guards(
        "slack",
        enabled_env="SOAR_REAL_SLACK_ENABLED",
        credential_envs=("SLACK_WEBHOOK_URL",),
    )
    assert readiness["real_mode_allowed"] is False
    assert readiness["failure_classification"] == FAILURE_CLASSIFICATION_CREDENTIAL_MISSING
    assert "SLACK_WEBHOOK_URL" in readiness["missing_guards"]


def test_slack_real_mode_invalid_webhook_redacts_value(monkeypatch, no_network):
    secret_url = "https://hooks.slack.com/services/T000/B000/SECRET"
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_SLACK_ENABLED", "true")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.invalid/not-slack")

    adapter = get_integration_adapter("slack")
    result = adapter.execute(
        "send_message",
        params={"message": secret_url, "slack_webhook_url": secret_url},
    )

    rendered = json.dumps(result, sort_keys=True)
    assert result["success"] is False
    assert result["params"]["slack_webhook_url"] == "[redacted]"
    assert secret_url not in rendered
    assert "hooks.slack.com/services" not in rendered


def test_slack_real_mode_staging_uses_mocked_outbound_call(monkeypatch):
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_SLACK_ENABLED", "true")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T000/B000/SECRET")

    with patch(
        "integrations.slack_adapter._post_slack_webhook",
        return_value={"status_code": 200},
    ) as post_mock, patch("core.integration_audit.log_audit_event") as audit_mock:
        result = get_integration_adapter("slack").execute(
            "send_message",
            params={"message": "Staging notification"},
            context={
                "execution_id": 44,
                "playbook_id": "pb_slack",
                "alert_id": 99,
                "incident_id": 5,
                "correlation_id": "corr-slack",
                "idempotency_key": "idem-slack",
            },
        )

    assert result["success"] is True
    assert result["mode"] == "real"
    assert result["simulated"] is False
    assert result["executed"] is True
    assert result["metadata"]["delivery"] == "sent"
    post_mock.assert_called_once()
    audit_mock.assert_called_once()
    event_type = audit_mock.call_args.args[0]
    details = audit_mock.call_args.kwargs["details"]
    assert event_type == "SOAR_REAL_ADAPTER_ATTEMPT"
    assert details["adapter"] == "slack"
    assert details["action"] == "send_message"
    assert details["mode"] == "real"
    assert details["success"] is True
    assert details["executed"] is True
    assert details["result_status"] == "success"
    assert details["playbook_execution_id"] == 44
    assert details["incident_id"] == 5
    assert details["alert_id"] == 99
    assert details["correlation_id"] == "corr-slack"
    assert details["idempotency_key"] == "idem-slack"
    rendered = json.dumps(result, sort_keys=True)
    rendered_details = json.dumps(details, sort_keys=True)
    assert "hooks.slack.com/services" not in rendered
    assert "SECRET" not in rendered
    assert "hooks.slack.com/services" not in rendered_details
    assert "SECRET" not in rendered_details


def test_slack_real_mode_failure_audit_redacts_webhook(monkeypatch):
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_SLACK_ENABLED", "true")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T000/B000/SECRET")

    with patch(
        "integrations.slack_adapter._post_slack_webhook",
        side_effect=urllib.error.URLError("temporary provider failure"),
    ) as post_mock, patch("core.integration_audit.log_audit_event") as audit_mock:
        result = get_integration_adapter("slack").execute(
            "send_message",
            params={
                "message": "Staging notification",
                "slack_webhook_url": "https://hooks.slack.com/services/T000/B000/SECRET",
            },
            context={"execution_id": 45, "alert_id": 101},
        )

    assert result["success"] is False
    assert result["executed"] is False
    post_mock.assert_called_once()
    audit_mock.assert_called_once()
    details = audit_mock.call_args.kwargs["details"]
    rendered_details = json.dumps(details, sort_keys=True)
    assert details["adapter"] == "slack"
    assert details["action"] == "send_message"
    assert details["mode"] == "real"
    assert details["success"] is False
    assert details["executed"] is False
    assert details["result_status"] == "failed"
    assert details["failure_class"] == FAILURE_CLASSIFICATION_TRANSIENT
    assert details["playbook_execution_id"] == 45
    assert details["alert_id"] == 101
    assert "hooks.slack.com/services" not in rendered_details
    assert "SECRET" not in rendered_details


def test_simulation_mode_does_not_write_real_adapter_audit(monkeypatch, no_network):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)

    with patch("core.integration_audit.log_audit_event") as audit_mock:
        result = get_integration_adapter("slack").execute(
            "send_message",
            params={"message": "simulation only"},
            context={"execution_id": 44, "alert_id": 99},
        )

    assert result["mode"] == "simulation"
    assert result["simulated"] is True
    assert result["executed"] is False
    audit_mock.assert_not_called()


def test_real_mode_does_not_apply_to_non_slack_adapters(monkeypatch, no_network):
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_SLACK_ENABLED", "true")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T000/B000/SECRET")

    for adapter_name, action in [
        ("email", "send_email"),
        ("firewall", "block_ip"),
        ("webhook", "post_event"),
    ]:
        adapter = get_integration_adapter(adapter_name)
        result = adapter.execute(action)
        assert adapter.mode == "simulation"
        assert result["mode"] == "simulation"
        assert result["simulated"] is True
        assert result["executed"] is False


@pytest.mark.parametrize(
    ("adapter_name", "action"),
    [
        ("email", "send_email"),
        ("firewall", "block_ip"),
        ("webhook", "post_event"),
    ],
)
def test_real_mode_without_adapter_flag_fails_closed_for_simulation_only_adapters(
    monkeypatch,
    no_network,
    adapter_name,
    action,
):
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")

    adapter = get_integration_adapter(adapter_name)
    result = adapter.execute(action)

    assert adapter.mode == "simulation"
    assert result["mode"] == "simulation"
    assert result["simulated"] is True
    assert result["executed"] is False
    assert result["success"] is True


def test_slack_real_mode_open_circuit_blocks_before_network(monkeypatch, no_network):
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_SLACK_ENABLED", "true")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T000/B000/SECRET")
    configure_simulated_circuit_breaker("slack", state=CIRCUIT_STATE_OPEN, consecutive_failures=3)

    with patch(
        "integrations.slack_adapter._post_slack_webhook",
        side_effect=AssertionError("Slack network path must not run when circuit is open"),
    ):
        result = get_integration_adapter("slack").execute("send_message")

    assert result["success"] is False
    assert result["metadata"]["failure_classification"] == FAILURE_CLASSIFICATION_CIRCUIT_OPEN
    assert result["metadata"]["retry_eligible"] is False


def test_teams_real_mode_missing_webhook_fails_closed_without_network(monkeypatch, no_network):
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_TEAMS_ENABLED", "true")
    monkeypatch.delenv("TEAMS_WEBHOOK_URL", raising=False)

    adapter = get_integration_adapter("teams")
    result = adapter.execute(
        "send_message",
        params={"message": "hello"},
        context={"execution_id": 1, "playbook_id": "pb"},
    )

    assert adapter.mode == "real"
    assert result["mode"] == "real"
    assert result["simulated"] is True
    assert result["executed"] is False
    assert result["success"] is False
    readiness = _validate_real_mode_guards(
        "teams",
        enabled_env="SOAR_REAL_TEAMS_ENABLED",
        credential_envs=("TEAMS_WEBHOOK_URL",),
    )
    assert readiness["real_mode_allowed"] is False
    assert readiness["failure_classification"] == FAILURE_CLASSIFICATION_CREDENTIAL_MISSING
    assert "TEAMS_WEBHOOK_URL" in readiness["missing_guards"]


def test_teams_real_mode_invalid_webhook_redacts_value(monkeypatch, no_network):
    secret_url = "https://contoso.webhook.office.com/webhookb2/SECRET"
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_TEAMS_ENABLED", "true")
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://hooks.slack.com/services/T000/B000/WRONG")

    adapter = get_integration_adapter("teams")
    result = adapter.execute(
        "send_message",
        params={"message": secret_url, "teams_webhook_url": secret_url},
    )

    rendered = json.dumps(result, sort_keys=True)
    assert result["success"] is False
    assert result["params"]["teams_webhook_url"] == "[redacted]"
    assert secret_url not in rendered
    assert "webhook.office.com" not in rendered
    assert "SECRET" not in rendered


def test_teams_real_mode_staging_uses_mocked_outbound_call(monkeypatch):
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_TEAMS_ENABLED", "true")
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://contoso.webhook.office.com/webhookb2/SECRET")

    with patch(
        "integrations.teams_adapter._post_teams_webhook",
        return_value={"status_code": 200},
    ) as post_mock:
        result = get_integration_adapter("teams").execute(
            "send_message",
            params={"message": "Staging Teams notification"},
            context={"execution_id": 45, "playbook_id": "pb_teams", "alert_id": 100},
        )

    assert result["success"] is True
    assert result["mode"] == "real"
    assert result["simulated"] is False
    assert result["executed"] is True
    assert result["metadata"]["delivery"] == "sent"
    post_mock.assert_called_once()
    rendered = json.dumps(result, sort_keys=True)
    assert "webhook.office.com" not in rendered
    assert "SECRET" not in rendered


def test_teams_and_slack_real_mode_configs_do_not_cross_enable(monkeypatch, no_network):
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_SLACK_ENABLED", "true")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T000/B000/SECRET")
    monkeypatch.delenv("SOAR_REAL_TEAMS_ENABLED", raising=False)
    monkeypatch.delenv("TEAMS_WEBHOOK_URL", raising=False)

    teams_result = get_integration_adapter("teams").execute("send_message")
    assert teams_result["success"] is False
    assert teams_result["executed"] is False

    monkeypatch.delenv("SOAR_REAL_SLACK_ENABLED", raising=False)
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("SOAR_REAL_TEAMS_ENABLED", "true")
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://contoso.webhook.office.com/webhookb2/SECRET")

    slack_result = get_integration_adapter("slack").execute("send_message")
    assert slack_result["success"] is False
    assert slack_result["executed"] is False


def test_real_mode_does_not_apply_to_non_teams_adapters(monkeypatch, no_network):
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_TEAMS_ENABLED", "true")
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://contoso.webhook.office.com/webhookb2/SECRET")

    for adapter_name, action in [
        ("email", "send_email"),
        ("firewall", "block_ip"),
        ("webhook", "post_event"),
    ]:
        adapter = get_integration_adapter(adapter_name)
        result = adapter.execute(action)
        assert adapter.mode == "simulation"
        assert result["mode"] == "simulation"
        assert result["simulated"] is True
        assert result["executed"] is False


def test_teams_real_mode_open_circuit_blocks_before_network(monkeypatch, no_network):
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_TEAMS_ENABLED", "true")
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://contoso.webhook.office.com/webhookb2/SECRET")
    configure_simulated_circuit_breaker("teams", state=CIRCUIT_STATE_OPEN, consecutive_failures=3)

    with patch(
        "integrations.teams_adapter._post_teams_webhook",
        side_effect=AssertionError("Teams network path must not run when circuit is open"),
    ):
        result = get_integration_adapter("teams").execute("send_message")

    assert result["success"] is False
    assert result["metadata"]["failure_classification"] == FAILURE_CLASSIFICATION_CIRCUIT_OPEN
    assert result["metadata"]["retry_eligible"] is False


def test_normalize_registered_integration_adapter_name(monkeypatch):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)
    assert normalize_registered_integration_adapter_name("Slack") == "slack"
    assert normalize_registered_integration_adapter_name("Teams") == "teams"
    assert normalize_registered_integration_adapter_name("pagerduty") is None


def test_manual_reset_clears_failures_and_records_metadata(monkeypatch, no_network):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)
    configure_simulated_circuit_breaker(
        "email",
        state=CIRCUIT_STATE_OPEN,
        consecutive_failures=3,
    )
    snap = manual_reset_simulated_circuit_breaker(
        "email",
        actor_username="super1",
        reason="verified healthy",
    )
    assert snap["state"] == CIRCUIT_STATE_CLOSED
    assert snap["consecutive_failures"] == 0
    assert snap["last_manual_action"] == "reset"
    assert snap["last_manual_action_by"] == "super1"
    assert snap["last_manual_reason"] == "verified healthy"


def test_manual_force_open_preserves_failure_count(monkeypatch, no_network):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)
    configure_simulated_circuit_breaker("webhook", consecutive_failures=2)
    snap = manual_force_open_simulated_circuit_breaker(
        "webhook",
        actor_username="super1",
        reason="hold traffic",
    )
    assert snap["state"] == CIRCUIT_STATE_OPEN
    assert snap["consecutive_failures"] == 2
    assert snap["last_manual_action"] == "force_open"
    assert "hold traffic" in (snap["last_manual_reason"] or "")


def test_manual_enable_half_open_sets_probe_flag_without_running_adapter(monkeypatch, no_network):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)
    t0 = datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc)
    configure_simulated_circuit_breaker(
        "slack",
        state=CIRCUIT_STATE_OPEN,
        consecutive_failures=2,
        cooldown_until=t0 - timedelta(seconds=1),
    )
    snap = manual_enable_half_open_probe_simulated_circuit_breaker(
        "slack",
        actor_username="super1",
        reason="prep probe",
    )
    assert snap["state"] == CIRCUIT_STATE_HALF_OPEN
    assert snap["half_open_probe_available"] is True


def test_manual_enable_respects_cooldown_unless_overridden(monkeypatch, no_network):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)
    t0 = datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc)
    configure_simulated_circuit_breaker(
        "slack",
        state=CIRCUIT_STATE_OPEN,
        cooldown_until=t0 + timedelta(minutes=30),
    )
    with pytest.raises(SimulatedCircuitBreakerControlError) as exc:
        manual_enable_half_open_probe_simulated_circuit_breaker(
            "slack",
            actor_username="a",
            reason="probe later",
            now=t0,
            override_cooldown=False,
        )
    assert exc.value.status_code == 409
    snap = manual_enable_half_open_probe_simulated_circuit_breaker(
        "slack",
        actor_username="a",
        reason="override cooldown for drill",
        now=t0,
        override_cooldown=True,
    )
    assert snap["state"] == CIRCUIT_STATE_HALF_OPEN


def test_manual_enable_half_open_rejects_non_open(monkeypatch, no_network):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)
    with pytest.raises(SimulatedCircuitBreakerControlError) as exc:
        manual_enable_half_open_probe_simulated_circuit_breaker(
            "slack",
            actor_username="super1",
            reason="bad",
        )
    assert exc.value.status_code == 400


def test_manual_enable_half_open_rejects_invalid_state(monkeypatch, no_network):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)
    configure_simulated_circuit_breaker("slack", state="not_a_valid_state")
    with pytest.raises(SimulatedCircuitBreakerControlError) as exc:
        manual_enable_half_open_probe_simulated_circuit_breaker(
            "slack",
            actor_username="super1",
            reason="bad",
        )
    assert exc.value.status_code == 409


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
