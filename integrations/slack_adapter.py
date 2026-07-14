from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from core.integration_audit import log_integration_execution_attempt
from integrations.adapter_rate_limiter import check_adapter_rate_limit
from integrations.base_integration import (
    FAILURE_CLASSIFICATION_CREDENTIAL_MISSING,
    FAILURE_CLASSIFICATION_NON_TRANSIENT,
    FAILURE_CLASSIFICATION_TIMEOUT,
    FAILURE_CLASSIFICATION_TRANSIENT,
    FAILURE_CLASSIFICATION_PROVIDER_RATE_LIMITED,
    REAL_MODE,
    SIMULATION_MODE,
    BaseIntegration,
    _validate_real_mode_guards,
)

SLACK_WEBHOOK_ENV = "SLACK_WEBHOOK_URL"
SLACK_PFSENSE_WEBHOOK_ENV = "SLACK_PFSENSE_WEBHOOK_URL"
SLACK_HONEYPOT_WEBHOOK_ENV = "SLACK_HONEYPOT_WEBHOOK_URL"
SLACK_REAL_ALLOW_ENV = "SOAR_REAL_SLACK_ENABLED"
SLACK_ENV_ENV = "SOAR_ENV"
SLACK_TIMEOUT_ENV = "SLACK_TIMEOUT_SECONDS"
DEFAULT_SLACK_TIMEOUT_SECONDS = 3
MAX_SLACK_TEXT_CHARS = 3000
ROUTE_KEY_TO_SLACK_WEBHOOK_ENV = {
    "pfsense": SLACK_PFSENSE_WEBHOOK_ENV,
    "honeypot": SLACK_HONEYPOT_WEBHOOK_ENV,
}


# spec: SPEC-INTEG-003
def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _slack_webhook_configured() -> bool:
    return bool(os.getenv(SLACK_WEBHOOK_ENV, "").strip())


def _slack_webhook_valid() -> bool:
    value = os.getenv(SLACK_WEBHOOK_ENV, "").strip()
    return value.startswith("https://hooks.slack.com/services/")


def _slack_webhook_value(env_name: str) -> str:
    return os.getenv(env_name, "").strip()


def _slack_webhook_valid_for_env(env_name: str) -> bool:
    return _slack_webhook_value(env_name).startswith("https://hooks.slack.com/services/")


def _notification_policy_route_key(context: dict[str, Any]) -> str | None:
    if context.get("notification_policy") is not True:
        return None
    route_key = str(context.get("route_key") or "").strip().lower()
    return route_key or None


def _resolve_slack_webhook_target(context: dict[str, Any]) -> dict[str, Any]:
    route_key = _notification_policy_route_key(context)
    if route_key in ROUTE_KEY_TO_SLACK_WEBHOOK_ENV:
        env_name = ROUTE_KEY_TO_SLACK_WEBHOOK_ENV[route_key]
        webhook_url = _slack_webhook_value(env_name)
        return {
            "route_key": route_key,
            "env_name": env_name,
            "webhook_url": webhook_url,
            "configured": bool(webhook_url),
            "valid": _slack_webhook_valid_for_env(env_name),
            "generic": False,
        }
    return {
        "route_key": None,
        "env_name": SLACK_WEBHOOK_ENV,
        "webhook_url": _slack_webhook_value(SLACK_WEBHOOK_ENV),
        "configured": _slack_webhook_configured(),
        "valid": _slack_webhook_valid(),
        "generic": True,
    }


def _slack_real_mode_allowed() -> bool:
    readiness = _validate_real_mode_guards(
        "slack",
        mode=REAL_MODE,
        enabled_env=SLACK_REAL_ALLOW_ENV,
        credential_envs=(SLACK_WEBHOOK_ENV,),
    )
    return bool(readiness["real_mode_allowed"])


def _slack_real_guard_readiness(mode: str, credential_envs: tuple[str, ...]) -> dict[str, Any]:
    return _validate_real_mode_guards(
        "slack",
        mode=mode,
        enabled_env=SLACK_REAL_ALLOW_ENV,
        credential_envs=credential_envs,
    )


# spec: SPEC-INTEG-003 / SPEC-INTEG-005 - Slack is real-capable only after adapter guards pass.
def get_slack_real_mode_readiness(configured_mode: str | None = None) -> dict[str, Any]:
    """Return safe Slack readiness metadata. Never include the webhook value."""
    mode = str(configured_mode or os.getenv("INTEGRATION_MODE", SIMULATION_MODE)).strip().lower()
    guard_readiness = _validate_real_mode_guards(
        "slack",
        mode=mode,
        enabled_env=SLACK_REAL_ALLOW_ENV,
        credential_envs=(SLACK_WEBHOOK_ENV,),
    )
    configured = _slack_webhook_configured()
    webhook_valid = _slack_webhook_valid()
    allowed = bool(guard_readiness["real_mode_allowed"])
    ready = bool(allowed and configured and webhook_valid)
    if mode != REAL_MODE:
        status = "simulation"
    elif guard_readiness["missing_guards"]:
        status = guard_readiness["real_mode_status"]
    elif not configured:
        status = "blocked: Slack webhook is not configured"
    elif not webhook_valid:
        status = "blocked: Slack webhook configuration is invalid"
    else:
        status = "ready"
    return {
        "slack_configured": configured,
        "real_mode_allowed": allowed,
        "real_mode_ready": ready,
        "real_mode_status": status,
        "webhook_configured": configured,
    }


def _get_timeout_seconds() -> int:
    raw = os.getenv(SLACK_TIMEOUT_ENV, str(DEFAULT_SLACK_TIMEOUT_SECONDS)).strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_SLACK_TIMEOUT_SECONDS
    return max(1, min(value, 30))


def _format_slack_payload(action: str, params: dict[str, Any], context: dict[str, Any]) -> dict[str, str]:
    preformatted_text = str(params.get("text") or "").strip()
    if preformatted_text:
        return {"text": preformatted_text[:MAX_SLACK_TEXT_CHARS]}
    summary = str(
        params.get("message")
        or params.get("summary")
        or "SOAR playbook notification."
    ).strip()
    if not summary:
        summary = "SOAR playbook notification."
    summary = summary[:MAX_SLACK_TEXT_CHARS]
    lines = [
        "SOAR notification",
        f"Action: {action}",
        f"Playbook: {context.get('playbook_id') or 'unknown'}",
        f"Execution: {context.get('execution_id') or 'unknown'}",
    ]
    if context.get("alert_id") is not None:
        lines.append(f"Alert: {context.get('alert_id')}")
    if context.get("incident_id") is not None:
        lines.append(f"Incident: {context.get('incident_id')}")
    destination_label = str(params.get("destination_label") or "").strip()
    if destination_label:
        lines.append(f"Destination: {destination_label}")
    lines.append(f"Summary: {summary}")
    return {"text": "\n".join(lines)[:MAX_SLACK_TEXT_CHARS]}


def _post_slack_webhook(webhook_url: str, payload: dict[str, str], timeout_seconds: int) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
        return {"status_code": getattr(resp, "status", None) or resp.getcode()}


class SlackSimulationAdapter(BaseIntegration):
    adapter_name = "slack"
    supported_actions = frozenset({"send_message", "notify_channel", "test_notification"})
    allow_real_mode = True

    def _simulate(self, action, params, context):
        return self._result(
            action,
            params,
            context,
            success=True,
            message="Simulated slack action. No webhook or API call was made.",
            metadata={"delivery": "not_sent"},
        )

    def _execute_supported_action(self, action, params, context):
        if self.mode != REAL_MODE:
            return self._simulate(action, params, context)
        return self._execute_real_slack(action, params, context)

    # spec: SPEC-INTEG-005
    def _audit_real_attempt(self, result, context):
        log_integration_execution_attempt(result, context)
        return result

    def _execute_real_slack(self, action, params, context):
        timeout_seconds = _get_timeout_seconds()
        webhook_target = _resolve_slack_webhook_target(context)
        guard_readiness = _slack_real_guard_readiness(REAL_MODE, (webhook_target["env_name"],))
        base_metadata = {
            "delivery": "not_sent",
            "slack_configured": webhook_target["configured"],
            "real_mode_allowed": guard_readiness["real_mode_allowed"],
            "real_mode_ready": bool(
                guard_readiness["real_mode_allowed"] and webhook_target["configured"] and webhook_target["valid"]
            ),
            "webhook_configured": webhook_target["configured"],
            "timeout_seconds": timeout_seconds,
            "max_adapter_attempts": 1,
        }
        if not guard_readiness["real_mode_allowed"]:
            missing_guards = guard_readiness.get("missing_guards") or []
            failure_classification = (
                FAILURE_CLASSIFICATION_CREDENTIAL_MISSING
                if webhook_target["env_name"] in missing_guards
                else FAILURE_CLASSIFICATION_NON_TRANSIENT
            )
            return self._audit_real_attempt(self._result(
                action,
                params,
                context,
                success=False,
                message=f"Slack real mode failed closed: {guard_readiness['real_mode_status']}.",
                metadata={
                    **base_metadata,
                    "failure_classification": failure_classification,
                    "retry_eligible": False,
                },
                mode=REAL_MODE,
                simulated=True,
                executed=False,
            ), context)

        if not webhook_target["configured"]:
            target_name = webhook_target["env_name"]
            route_key = webhook_target["route_key"]
            message = (
                f"Slack real mode failed closed: missing route-specific webhook {target_name} for {route_key}."
                if route_key
                else f"Slack real mode failed closed: missing webhook {target_name}."
            )
            return self._audit_real_attempt(self._result(
                action,
                params,
                context,
                success=False,
                message=message,
                metadata={
                    **base_metadata,
                    "failure_classification": FAILURE_CLASSIFICATION_CREDENTIAL_MISSING,
                    "retry_eligible": False,
                    "webhook_configured": False,
                },
                mode=REAL_MODE,
                simulated=True,
                executed=False,
            ), context)

        if not webhook_target["valid"]:
            target_name = webhook_target["env_name"]
            route_key = webhook_target["route_key"]
            message = (
                f"Slack real mode failed closed: invalid route-specific webhook {target_name} for {route_key}."
                if route_key
                else f"Slack real mode failed closed: invalid webhook {target_name}."
            )
            return self._audit_real_attempt(self._result(
                action,
                params,
                context,
                success=False,
                message=message,
                metadata={
                    **base_metadata,
                    "failure_classification": FAILURE_CLASSIFICATION_NON_TRANSIENT,
                    "retry_eligible": False,
                    "webhook_configured": True,
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
                message="Slack real-mode send blocked safely by adapter rate limit.",
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

        webhook_url = webhook_target["webhook_url"]
        payload = _format_slack_payload(action, params, context)
        started = time.monotonic()
        try:
            response = _post_slack_webhook(webhook_url, payload, timeout_seconds)
        except TimeoutError:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            return self._audit_real_attempt(self._result(
                action,
                params,
                context,
                success=False,
                message="Slack real-mode send timed out safely.",
                metadata={
                    **base_metadata,
                    "failure_classification": FAILURE_CLASSIFICATION_TIMEOUT,
                    "retry_eligible": True,
                    "timed_out": True,
                    "elapsed_ms": elapsed_ms,
                },
                mode=REAL_MODE,
                simulated=False,
                executed=False,
            ), context)
        except urllib.error.HTTPError as exc:
            status_code = int(getattr(exc, "code", 0) or 0)
            transient = status_code >= 500 or status_code == 429
            return self._audit_real_attempt(self._result(
                action,
                params,
                context,
                success=False,
                message=f"Slack real-mode send failed safely with HTTP {status_code}.",
                metadata={
                    **base_metadata,
                    "failure_classification": (
                        FAILURE_CLASSIFICATION_TRANSIENT
                        if transient
                        else FAILURE_CLASSIFICATION_NON_TRANSIENT
                    ),
                    "retry_eligible": transient,
                    "http_status": status_code,
                },
                mode=REAL_MODE,
                simulated=False,
                executed=False,
            ), context)
        except urllib.error.URLError:
            return self._audit_real_attempt(self._result(
                action,
                params,
                context,
                success=False,
                message="Slack real-mode send failed safely before confirmation.",
                metadata={
                    **base_metadata,
                    "failure_classification": FAILURE_CLASSIFICATION_TRANSIENT,
                    "retry_eligible": True,
                },
                mode=REAL_MODE,
                simulated=False,
                executed=False,
            ), context)

        status_code = int(response.get("status_code") or 0)
        return self._audit_real_attempt(self._result(
            action,
            params,
            context,
            success=200 <= status_code < 300,
            message="Slack real-mode notification sent.",
            metadata={
                **base_metadata,
                "delivery": "sent",
                "http_status": status_code,
                "payload_fields": sorted(_format_slack_payload(action, params, context).keys()),
                "retry_eligible": False,
            },
            mode=REAL_MODE,
            simulated=False,
            executed=True,
        ), context)
