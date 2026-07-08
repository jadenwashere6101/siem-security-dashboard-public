from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from core.notification_delivery_store import (
    create_notification_delivery_attempt,
    list_notification_delivery_attempts,
)
from integrations.base_integration import REAL_MODE
from integrations.email_adapter import get_email_real_mode_readiness
from integrations.integration_registry import get_integration_adapter
from integrations.slack_adapter import get_slack_real_mode_readiness
from integrations.teams_adapter import get_teams_real_mode_readiness
from integrations.webhook_adapter import get_webhook_real_mode_readiness

TEST_NOTIFICATION_ACTION = "test_notification"
ALLOWED_NOTIFICATION_TEST_PROVIDERS = ("slack", "teams", "email", "webhook")

_PROVIDER_LABELS = {
    "slack": "Slack",
    "teams": "Teams",
    "email": "Email",
    "webhook": "Webhook",
}


class NotificationTestError(ValueError):
    pass


def _env_present(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def _provider_key(provider: str) -> str:
    key = str(provider or "").strip().lower()
    if key not in ALLOWED_NOTIFICATION_TEST_PROVIDERS:
        raise NotificationTestError("Notification test provider is not supported.")
    return key


def get_provider_configuration(provider: str) -> dict[str, Any]:
    key = _provider_key(provider)
    if key == "slack":
        readiness = get_slack_real_mode_readiness()
        missing = [] if readiness["slack_configured"] else ["SLACK_WEBHOOK_URL"]
        configured = not missing
    elif key == "teams":
        readiness = get_teams_real_mode_readiness()
        missing = [] if readiness["teams_configured"] else ["TEAMS_WEBHOOK_URL"]
        configured = not missing
    elif key == "email":
        readiness = get_email_real_mode_readiness()
        missing = [
            name
            for name in (
                "SMTP_HOST",
                "SMTP_USERNAME",
                "SMTP_PASSWORD",
                "SMTP_FROM_EMAIL",
                "SMTP_TO_EMAIL",
            )
            if not _env_present(name)
        ]
        configured = not missing
    else:
        readiness = get_webhook_real_mode_readiness()
        configured = bool(readiness["webhook_configured"])
        missing = [] if configured else ["WEBHOOK_URL", "WEBHOOK_BASE_URL"]

    return {
        "provider": key,
        "label": _PROVIDER_LABELS[key],
        "configured": bool(configured),
        "missing_configuration": missing,
    }


def _manual_test_params(provider: str) -> dict[str, Any]:
    message = (
        "MANUAL SOAR NOTIFICATION READINESS TEST. "
        "This is not a real security event."
    )
    if provider == "email":
        return {
            "subject": "Manual SOAR notification readiness test",
            "body": message,
        }
    if provider == "webhook":
        return {
            "event": "manual_soar_notification_readiness_test",
            "summary": message,
            "message": message,
        }
    return {"message": message, "summary": message}


def _manual_test_context(provider: str, correlation_id: str) -> dict[str, Any]:
    return {
        "playbook_id": "manual_readiness_test",
        "execution_id": correlation_id,
        "notification_test": True,
        "provider": provider,
    }


def _status_from_adapter_result(result: dict[str, Any]) -> str:
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    if result.get("success") is True:
        return "success"
    if metadata.get("timed_out") is True or metadata.get("failure_classification") == "timeout":
        return "timeout"
    if result.get("simulated") is True or metadata.get("rate_limited") is True:
        return "blocked"
    if metadata.get("failure_classification") in {
        "credential_missing",
        "guard_failed",
        "invalid_target",
    }:
        return "blocked"
    return "failed"


def _failure_code_from_result(result: dict[str, Any], status: str) -> str | None:
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    code = metadata.get("failure_classification")
    if isinstance(code, str) and code.strip():
        return code.strip()
    if status == "blocked":
        return "guard_blocked"
    if status == "failed":
        return "test_failed"
    if status == "timeout":
        return "timeout"
    return None


def send_notification_test(conn, provider: str) -> dict[str, Any]:
    key = _provider_key(provider)
    configuration = get_provider_configuration(key)
    if not configuration["configured"]:
        return {
            **configuration,
            "tested": "never_tested",
            "ready": False,
            "outcome": "not_configured",
            "message": "Provider is not configured; no test notification was attempted.",
            "attempt": None,
        }

    correlation_id = f"manual-notification-test-{key}-{uuid4()}"
    idempotency_key = f"{correlation_id}-attempt"
    now = datetime.now(timezone.utc)
    adapter = get_integration_adapter(key, mode=REAL_MODE)
    result = adapter.execute(
        TEST_NOTIFICATION_ACTION,
        params=_manual_test_params(key),
        context=_manual_test_context(key, correlation_id),
    )
    status = _status_from_adapter_result(result)
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    attempt = create_notification_delivery_attempt(
        conn,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        provider=key,
        mode=REAL_MODE,
        status=status,
        adapter_name=key,
        action=TEST_NOTIFICATION_ACTION,
        playbook_execution_id=None,
        incident_id=None,
        approval_request_id=None,
        alert_id=None,
        requested_at=now,
        started_at=now,
        completed_at=datetime.now(timezone.utc),
        failure_code=_failure_code_from_result(result, status),
        failure_message=None if status == "success" else result.get("message"),
        timeout_seconds=metadata.get("timeout_seconds"),
        circuit_breaker_state=metadata.get("circuit_state"),
        metadata={
            "manual_readiness_test": True,
            "adapter_result": {
                "success": result.get("success"),
                "simulated": result.get("simulated"),
                "executed": result.get("executed"),
                "failure_classification": metadata.get("failure_classification"),
                "rate_limited": metadata.get("rate_limited"),
                "timed_out": metadata.get("timed_out"),
            },
        },
    )
    tested = "passed" if status == "success" else ("failed" if status in {"failed", "timeout"} else "never_tested")
    return {
        **configuration,
        "tested": tested,
        "ready": bool(configuration["configured"] and tested == "passed"),
        "outcome": "success" if status == "success" else ("test_failed" if tested == "failed" else "guard_blocked"),
        "message": result.get("message"),
        "attempt": _attempt_summary(attempt),
    }


def _attempt_summary(attempt: dict[str, Any] | None) -> dict[str, Any] | None:
    if not attempt:
        return None
    return {
        "id": attempt.get("id"),
        "provider": attempt.get("provider"),
        "status": attempt.get("status"),
        "action": attempt.get("action"),
        "created_at": attempt.get("created_at"),
        "completed_at": attempt.get("completed_at"),
        "failure_code": attempt.get("failure_code"),
        "failure_message": attempt.get("failure_message"),
    }


def _read_latest_test_attempt(conn, provider: str) -> dict[str, Any] | None:
    rows = list_notification_delivery_attempts(
        conn,
        limit=1,
        provider=provider,
        adapter_name=provider,
        action=TEST_NOTIFICATION_ACTION,
    )
    return rows[0] if rows else None


def _tested_from_attempt(attempt: dict[str, Any] | None) -> str:
    if not attempt:
        return "never_tested"
    status = attempt.get("status")
    if status == "success":
        return "passed"
    if status in {"failed", "timeout"}:
        return "failed"
    return "never_tested"


def get_notification_readiness(conn) -> dict[str, Any]:
    providers = []
    for provider in ALLOWED_NOTIFICATION_TEST_PROVIDERS:
        configuration = get_provider_configuration(provider)
        latest = _read_latest_test_attempt(conn, provider)
        tested = _tested_from_attempt(latest)
        providers.append(
            {
                **configuration,
                "tested": tested,
                "ready": bool(configuration["configured"] and tested == "passed"),
                "last_test_at": latest.get("created_at") if latest else None,
                "last_test_status": latest.get("status") if latest else None,
                "last_test_message": latest.get("failure_message") if latest else None,
                "last_test_failure_code": latest.get("failure_code") if latest else None,
            }
        )
    return {"providers": providers}
