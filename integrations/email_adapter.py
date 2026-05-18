from __future__ import annotations

from email.message import EmailMessage
import os
import smtplib
import socket
import time
from typing import Any

from core.integration_audit import log_integration_execution_attempt
from integrations.adapter_rate_limiter import check_adapter_rate_limit
from integrations.base_integration import (
    FAILURE_CLASSIFICATION_CREDENTIAL_MISSING,
    FAILURE_CLASSIFICATION_INVALID_CREDENTIALS,
    FAILURE_CLASSIFICATION_MALFORMED_PAYLOAD,
    FAILURE_CLASSIFICATION_PROVIDER_RATE_LIMITED,
    FAILURE_CLASSIFICATION_TEMPORARY_PROVIDER_FAILURE,
    FAILURE_CLASSIFICATION_TIMEOUT,
    FAILURE_CLASSIFICATION_TRANSIENT_NETWORK_ERROR,
    REAL_MODE,
    SIMULATION_MODE,
    BaseIntegration,
    _validate_real_mode_guards,
)

SMTP_HOST_ENV = "SMTP_HOST"
SMTP_PORT_ENV = "SMTP_PORT"
SMTP_USERNAME_ENV = "SMTP_USERNAME"
SMTP_PASSWORD_ENV = "SMTP_PASSWORD"
SMTP_FROM_ENV = "SMTP_FROM_EMAIL"
SMTP_TO_ENV = "SMTP_TO_EMAIL"
SMTP_USE_TLS_ENV = "SMTP_USE_TLS"
EMAIL_REAL_ALLOW_ENV = "SOAR_REAL_EMAIL_ENABLED"
EMAIL_TIMEOUT_ENV = "EMAIL_TIMEOUT_SECONDS"
DEFAULT_EMAIL_TIMEOUT_SECONDS = 10
DEFAULT_SMTP_PORT = 587
MAX_EMAIL_SUBJECT_CHARS = 160
MAX_EMAIL_BODY_CHARS = 4000


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _smtp_host_configured() -> bool:
    return bool(os.getenv(SMTP_HOST_ENV, "").strip())


def _smtp_username_configured() -> bool:
    return bool(os.getenv(SMTP_USERNAME_ENV, "").strip())


def _smtp_from_configured() -> bool:
    return bool(os.getenv(SMTP_FROM_ENV, "").strip())


def _smtp_to_configured() -> bool:
    return bool(os.getenv(SMTP_TO_ENV, "").strip())


def get_email_real_mode_readiness(configured_mode: str | None = None) -> dict[str, Any]:
    """Return safe Email readiness metadata. Never include SMTP values."""
    mode = str(configured_mode or os.getenv("INTEGRATION_MODE", SIMULATION_MODE)).strip().lower()
    guard_readiness = _validate_real_mode_guards(
        "email",
        mode=mode,
        enabled_env=EMAIL_REAL_ALLOW_ENV,
        credential_envs=(SMTP_HOST_ENV, SMTP_USERNAME_ENV),
    )
    smtp_configured = _smtp_host_configured() and _smtp_username_configured()
    payload_defaults_configured = _smtp_from_configured() and _smtp_to_configured()
    allowed = bool(guard_readiness["real_mode_allowed"])
    ready = bool(allowed and payload_defaults_configured)
    if mode != REAL_MODE:
        status = "simulation"
    elif guard_readiness["missing_guards"]:
        status = guard_readiness["real_mode_status"]
    elif not payload_defaults_configured:
        status = "blocked: Email real mode requires SMTP_FROM_EMAIL and SMTP_TO_EMAIL defaults"
    else:
        status = "ready"
    return {
        "smtp_configured": smtp_configured,
        "smtp_host_configured": _smtp_host_configured(),
        "smtp_username_configured": _smtp_username_configured(),
        "smtp_from_configured": _smtp_from_configured(),
        "smtp_to_configured": _smtp_to_configured(),
        "email_real_enabled": _truthy(os.getenv(EMAIL_REAL_ALLOW_ENV)),
        "real_mode_allowed": allowed,
        "real_mode_ready": ready,
        "real_mode_status": status,
        "missing_guards": guard_readiness["missing_guards"],
        "credential_envs": [SMTP_HOST_ENV, SMTP_USERNAME_ENV],
        "payload_envs": [SMTP_FROM_ENV, SMTP_TO_ENV],
    }


def _get_timeout_seconds() -> int:
    raw = os.getenv(EMAIL_TIMEOUT_ENV, str(DEFAULT_EMAIL_TIMEOUT_SECONDS)).strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_EMAIL_TIMEOUT_SECONDS
    return max(1, min(value, 60))


def _get_smtp_port() -> int:
    raw = os.getenv(SMTP_PORT_ENV, str(DEFAULT_SMTP_PORT)).strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_SMTP_PORT
    return max(1, min(value, 65535))


def _safe_email(value: Any) -> str:
    return str(value or "").strip()[:320]


def _valid_email(value: str) -> bool:
    return bool(value and "@" in value and "\n" not in value and "\r" not in value)


def _build_email_message(action: str, params: dict[str, Any], context: dict[str, Any]) -> EmailMessage:
    to_addr = _safe_email(params.get("to") or params.get("recipient") or os.getenv(SMTP_TO_ENV))
    from_addr = _safe_email(params.get("from") or os.getenv(SMTP_FROM_ENV))
    if not _valid_email(to_addr) or not _valid_email(from_addr):
        raise ValueError("Email real mode requires valid from/to addresses")

    subject = str(params.get("subject") or "SOAR playbook notification").strip()
    if not subject or "\n" in subject or "\r" in subject:
        raise ValueError("Email real mode requires a safe subject")
    subject = subject[:MAX_EMAIL_SUBJECT_CHARS]

    body = str(
        params.get("body")
        or params.get("message")
        or "SOAR playbook notification."
    ).strip()
    if not body:
        body = "SOAR playbook notification."
    body = body[:MAX_EMAIL_BODY_CHARS]

    lines = [
        body,
        "",
        "SOAR context:",
        f"Action: {action}",
        f"Playbook: {context.get('playbook_id') or 'unknown'}",
        f"Execution: {context.get('execution_id') or 'unknown'}",
    ]
    if context.get("alert_id") is not None:
        lines.append(f"Alert: {context.get('alert_id')}")
    if context.get("incident_id") is not None:
        lines.append(f"Incident: {context.get('incident_id')}")

    message = EmailMessage()
    message["To"] = to_addr
    message["From"] = from_addr
    message["Subject"] = subject
    message.set_content("\n".join(lines)[:MAX_EMAIL_BODY_CHARS])
    return message


def _send_smtp_message(message: EmailMessage, timeout_seconds: int) -> dict[str, Any]:
    host = os.getenv(SMTP_HOST_ENV, "").strip()
    username = os.getenv(SMTP_USERNAME_ENV, "").strip()
    password = os.getenv(SMTP_PASSWORD_ENV, "")
    port = _get_smtp_port()
    with smtplib.SMTP(host, port, timeout=timeout_seconds) as smtp:
        if _truthy(os.getenv(SMTP_USE_TLS_ENV, "true")):
            smtp.starttls()
        if username:
            smtp.login(username, password)
        refused = smtp.send_message(message)
    return {"refused": refused or {}, "port": port}


# spec: SPEC-INTEG-005 - guarded real email path only; simulation remains default.
class EmailSimulationAdapter(BaseIntegration):
    adapter_name = "email"
    supported_actions = frozenset({"send_email", "notify_owner"})
    allow_real_mode = True

    def _simulate(self, action, params, context):
        return self._result(
            action,
            params,
            context,
            success=True,
            message="Simulated email action. No SMTP or provider call was made.",
            metadata={"delivery": "not_sent"},
        )

    def _execute_supported_action(self, action, params, context):
        if self.mode != REAL_MODE:
            return self._simulate(action, params, context)
        return self._execute_real_email(action, params, context)

    # spec: SPEC-INTEG-005
    def _audit_real_attempt(self, result, context):
        log_integration_execution_attempt(result, context)
        return result

    def _execute_real_email(self, action, params, context):
        readiness = get_email_real_mode_readiness(REAL_MODE)
        timeout_seconds = _get_timeout_seconds()
        base_metadata = {
            "delivery": "not_sent",
            "smtp_configured": readiness["smtp_configured"],
            "smtp_host_configured": readiness["smtp_host_configured"],
            "smtp_username_configured": readiness["smtp_username_configured"],
            "smtp_from_configured": readiness["smtp_from_configured"],
            "smtp_to_configured": readiness["smtp_to_configured"],
            "email_real_enabled": readiness["email_real_enabled"],
            "real_mode_allowed": readiness["real_mode_allowed"],
            "real_mode_ready": readiness["real_mode_ready"],
            "timeout_seconds": timeout_seconds,
            "max_adapter_attempts": 1,
        }
        if not readiness["real_mode_allowed"]:
            return self._audit_real_attempt(self._result(
                action,
                params,
                context,
                success=False,
                message=f"Email real mode failed closed: {readiness['real_mode_status']}.",
                metadata={
                    **base_metadata,
                    "failure_classification": FAILURE_CLASSIFICATION_CREDENTIAL_MISSING,
                    "retry_eligible": False,
                },
                mode=REAL_MODE,
                simulated=True,
                executed=False,
            ), context)
        if not readiness["real_mode_ready"]:
            return self._audit_real_attempt(self._result(
                action,
                params,
                context,
                success=False,
                message=f"Email real mode failed closed: {readiness['real_mode_status']}.",
                metadata={
                    **base_metadata,
                    "failure_classification": FAILURE_CLASSIFICATION_MALFORMED_PAYLOAD,
                    "retry_eligible": False,
                },
                mode=REAL_MODE,
                simulated=True,
                executed=False,
            ), context)

        rate_limit = check_adapter_rate_limit(self.adapter_name)
        if not rate_limit["allowed"]:
            return self._audit_real_attempt(self._result(
                action,
                params,
                context,
                success=False,
                message="Email real-mode send blocked safely by adapter rate limit.",
                metadata={
                    **base_metadata,
                    "failure_classification": FAILURE_CLASSIFICATION_PROVIDER_RATE_LIMITED,
                    "retry_eligible": True,
                    "rate_limited": True,
                    "rate_limit": {
                        "limit": rate_limit["limit"],
                        "window_seconds": rate_limit["window_seconds"],
                        "reset_after_seconds": rate_limit["reset_after_seconds"],
                    },
                },
                mode=REAL_MODE,
                simulated=False,
                executed=False,
            ), context)

        try:
            message = _build_email_message(action, params, context)
        except ValueError as exc:
            return self._audit_real_attempt(self._result(
                action,
                params,
                context,
                success=False,
                message=f"Email real-mode payload rejected safely: {exc}",
                metadata={
                    **base_metadata,
                    "failure_classification": FAILURE_CLASSIFICATION_MALFORMED_PAYLOAD,
                    "retry_eligible": False,
                },
                mode=REAL_MODE,
                simulated=False,
                executed=False,
            ), context)

        started = time.monotonic()
        try:
            response = _send_smtp_message(message, timeout_seconds)
        except (TimeoutError, socket.timeout):
            return self._audit_real_attempt(self._result(
                action,
                params,
                context,
                success=False,
                message="Email real-mode send timed out safely.",
                metadata={
                    **base_metadata,
                    "failure_classification": FAILURE_CLASSIFICATION_TIMEOUT,
                    "retry_eligible": True,
                    "timed_out": True,
                    "elapsed_ms": int((time.monotonic() - started) * 1000),
                },
                mode=REAL_MODE,
                simulated=False,
                executed=False,
            ), context)
        except smtplib.SMTPAuthenticationError:
            return self._audit_real_attempt(self._result(
                action,
                params,
                context,
                success=False,
                message="Email real-mode authentication failed safely.",
                metadata={
                    **base_metadata,
                    "failure_classification": FAILURE_CLASSIFICATION_INVALID_CREDENTIALS,
                    "retry_eligible": False,
                },
                mode=REAL_MODE,
                simulated=False,
                executed=False,
            ), context)
        except smtplib.SMTPRecipientsRefused:
            return self._audit_real_attempt(self._result(
                action,
                params,
                context,
                success=False,
                message="Email real-mode recipient was rejected safely.",
                metadata={
                    **base_metadata,
                    "failure_classification": FAILURE_CLASSIFICATION_MALFORMED_PAYLOAD,
                    "retry_eligible": False,
                },
                mode=REAL_MODE,
                simulated=False,
                executed=False,
            ), context)
        except smtplib.SMTPResponseException as exc:
            status_code = int(getattr(exc, "smtp_code", 0) or 0)
            classification = (
                FAILURE_CLASSIFICATION_PROVIDER_RATE_LIMITED
                if status_code in {421, 450, 451, 452}
                else FAILURE_CLASSIFICATION_TEMPORARY_PROVIDER_FAILURE
                if status_code >= 500
                else FAILURE_CLASSIFICATION_MALFORMED_PAYLOAD
            )
            retryable = classification in {
                FAILURE_CLASSIFICATION_PROVIDER_RATE_LIMITED,
                FAILURE_CLASSIFICATION_TEMPORARY_PROVIDER_FAILURE,
            }
            return self._audit_real_attempt(self._result(
                action,
                params,
                context,
                success=False,
                message=f"Email real-mode provider rejected safely with SMTP {status_code}.",
                metadata={
                    **base_metadata,
                    "failure_classification": classification,
                    "retry_eligible": retryable,
                    "smtp_status": status_code,
                },
                mode=REAL_MODE,
                simulated=False,
                executed=False,
            ), context)
        except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, OSError):
            return self._audit_real_attempt(self._result(
                action,
                params,
                context,
                success=False,
                message="Email real-mode send failed safely before confirmation.",
                metadata={
                    **base_metadata,
                    "failure_classification": FAILURE_CLASSIFICATION_TRANSIENT_NETWORK_ERROR,
                    "retry_eligible": True,
                },
                mode=REAL_MODE,
                simulated=False,
                executed=False,
            ), context)

        refused = response.get("refused") if isinstance(response, dict) else {}
        if refused:
            return self._audit_real_attempt(self._result(
                action,
                params,
                context,
                success=False,
                message="Email real-mode provider refused one or more recipients safely.",
                metadata={
                    **base_metadata,
                    "failure_classification": FAILURE_CLASSIFICATION_MALFORMED_PAYLOAD,
                    "retry_eligible": False,
                },
                mode=REAL_MODE,
                simulated=False,
                executed=False,
            ), context)

        return self._audit_real_attempt(self._result(
            action,
            params,
            context,
            success=True,
            message="Email real-mode notification sent.",
            metadata={
                **base_metadata,
                "delivery": "sent",
                "payload_fields": ["body", "from", "subject", "to"],
                "retry_eligible": False,
                "elapsed_ms": int((time.monotonic() - started) * 1000),
            },
            mode=REAL_MODE,
            simulated=False,
            executed=True,
        ), context)
