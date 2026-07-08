from unittest.mock import Mock, patch

import pytest

from core import notification_test_service


@pytest.fixture(autouse=True)
def _clear_provider_env(monkeypatch):
    for name in [
        "INTEGRATION_MODE",
        "SOAR_ENV",
        "SOAR_REAL_SLACK_ENABLED",
        "SOAR_REAL_TEAMS_ENABLED",
        "SOAR_REAL_EMAIL_ENABLED",
        "SOAR_REAL_WEBHOOK_ENABLED",
        "SLACK_WEBHOOK_URL",
        "TEAMS_WEBHOOK_URL",
        "SMTP_HOST",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_FROM_EMAIL",
        "SMTP_TO_EMAIL",
        "WEBHOOK_URL",
        "WEBHOOK_BASE_URL",
        "WEBHOOK_AUTH_TOKEN",
    ]:
        monkeypatch.delenv(name, raising=False)


def test_provider_configuration_reports_missing_names_only(monkeypatch):
    assert notification_test_service.get_provider_configuration("slack") == {
        "provider": "slack",
        "label": "Slack",
        "configured": False,
        "missing_configuration": ["SLACK_WEBHOOK_URL"],
    }

    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T/B/S")
    assert notification_test_service.get_provider_configuration("slack")[
        "missing_configuration"
    ] == []

    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "user")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "from@example.com")
    assert notification_test_service.get_provider_configuration("email")[
        "missing_configuration"
    ] == ["SMTP_PASSWORD", "SMTP_TO_EMAIL"]

    assert notification_test_service.get_provider_configuration("webhook")[
        "missing_configuration"
    ] == ["WEBHOOK_URL", "WEBHOOK_BASE_URL"]
    monkeypatch.setenv("WEBHOOK_BASE_URL", "https://hooks.example.com/soar")
    assert notification_test_service.get_provider_configuration("webhook")["configured"] is True


def test_rejects_firewall_and_unknown_provider():
    with pytest.raises(notification_test_service.NotificationTestError):
        notification_test_service.get_provider_configuration("firewall")
    with pytest.raises(notification_test_service.NotificationTestError):
        notification_test_service.send_notification_test(Mock(), "unknown")


def test_send_skips_unconfigured_provider_without_recording(monkeypatch):
    adapter = Mock()
    with patch.object(notification_test_service, "get_integration_adapter", return_value=adapter), patch.object(
        notification_test_service, "create_notification_delivery_attempt"
    ) as create_attempt:
        result = notification_test_service.send_notification_test(Mock(), "teams")

    assert result["outcome"] == "not_configured"
    assert result["attempt"] is None
    adapter.execute.assert_not_called()
    create_attempt.assert_not_called()


def test_send_records_blocked_when_guard_prevents_attempt(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T/B/S")
    adapter = Mock()
    adapter.execute.return_value = {
        "success": False,
        "simulated": True,
        "executed": False,
        "message": "Slack real mode failed closed: blocked: slack real mode requires guard(s): INTEGRATION_MODE.",
        "metadata": {"failure_classification": "guard_failed", "timeout_seconds": 3},
    }
    stored_attempt = {
        "id": 10,
        "provider": "slack",
        "status": "blocked",
        "action": notification_test_service.TEST_NOTIFICATION_ACTION,
        "created_at": "2026-07-08T00:00:00+00:00",
        "completed_at": "2026-07-08T00:00:00+00:00",
        "failure_code": "guard_failed",
        "failure_message": "blocked",
    }
    with patch.object(notification_test_service, "get_integration_adapter", return_value=adapter), patch.object(
        notification_test_service,
        "create_notification_delivery_attempt",
        return_value=stored_attempt,
    ) as create_attempt:
        result = notification_test_service.send_notification_test(Mock(), "slack")

    kwargs = create_attempt.call_args.kwargs
    assert kwargs["status"] == "blocked"
    assert kwargs["playbook_execution_id"] is None
    assert kwargs["incident_id"] is None
    assert kwargs["approval_request_id"] is None
    assert kwargs["alert_id"] is None
    assert result["outcome"] == "guard_blocked"
    assert result["tested"] == "never_tested"


@pytest.mark.parametrize(
    ("adapter_result", "expected_status", "expected_tested", "expected_outcome"),
    [
        (
            {"success": True, "simulated": False, "executed": True, "message": "sent", "metadata": {}},
            "success",
            "passed",
            "success",
        ),
        (
            {
                "success": False,
                "simulated": False,
                "executed": False,
                "message": "failed",
                "metadata": {"failure_classification": "transient"},
            },
            "failed",
            "failed",
            "test_failed",
        ),
        (
            {
                "success": False,
                "simulated": False,
                "executed": False,
                "message": "timeout",
                "metadata": {"failure_classification": "timeout", "timed_out": True},
            },
            "timeout",
            "failed",
            "test_failed",
        ),
    ],
)
def test_send_records_attempt_outcomes(monkeypatch, adapter_result, expected_status, expected_tested, expected_outcome):
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://contoso.webhook.office.com/webhookb2/secret")
    adapter = Mock()
    adapter.execute.return_value = adapter_result
    with patch.object(notification_test_service, "get_integration_adapter", return_value=adapter), patch.object(
        notification_test_service,
        "create_notification_delivery_attempt",
        return_value={
            "id": 1,
            "provider": "teams",
            "status": expected_status,
            "action": notification_test_service.TEST_NOTIFICATION_ACTION,
            "created_at": "2026-07-08T00:00:00+00:00",
            "completed_at": "2026-07-08T00:00:00+00:00",
            "failure_code": None,
            "failure_message": None,
        },
    ) as create_attempt:
        result = notification_test_service.send_notification_test(Mock(), "teams")

    assert create_attempt.call_args.kwargs["status"] == expected_status
    assert adapter.execute.call_args.args[0] == notification_test_service.TEST_NOTIFICATION_ACTION
    assert "MANUAL SOAR NOTIFICATION READINESS TEST" in adapter.execute.call_args.kwargs["params"]["message"]
    assert result["tested"] == expected_tested
    assert result["outcome"] == expected_outcome


def test_rate_limiter_block_result_is_recorded_as_blocked(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T/B/S")
    adapter = Mock()
    adapter.execute.return_value = {
        "success": False,
        "simulated": False,
        "executed": False,
        "message": "rate limited",
        "metadata": {"failure_classification": "provider_rate_limited", "rate_limited": True},
    }
    with patch.object(notification_test_service, "get_integration_adapter", return_value=adapter), patch.object(
        notification_test_service,
        "create_notification_delivery_attempt",
        return_value={"id": 1, "provider": "slack", "status": "blocked", "action": "test_notification"},
    ) as create_attempt:
        notification_test_service.send_notification_test(Mock(), "slack")

    assert create_attempt.call_args.kwargs["status"] == "blocked"


def test_readiness_uses_latest_test_attempt(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T/B/S")

    def fake_list(_conn, **kwargs):
        assert kwargs["action"] == notification_test_service.TEST_NOTIFICATION_ACTION
        if kwargs["provider"] == "slack":
            return [{"status": "success", "created_at": "2026-07-08T00:00:00+00:00"}]
        if kwargs["provider"] == "teams":
            return [{"status": "blocked", "created_at": "2026-07-08T00:01:00+00:00"}]
        return []

    with patch.object(notification_test_service, "list_notification_delivery_attempts", side_effect=fake_list):
        result = notification_test_service.get_notification_readiness(Mock())

    providers = {item["provider"]: item for item in result["providers"]}
    assert providers["slack"]["tested"] == "passed"
    assert providers["slack"]["ready"] is True
    assert providers["teams"]["tested"] == "never_tested"
    assert providers["teams"]["last_test_status"] == "blocked"
    assert "firewall" not in providers
