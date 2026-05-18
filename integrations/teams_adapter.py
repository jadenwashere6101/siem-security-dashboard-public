from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from integrations.base_integration import (
    FAILURE_CLASSIFICATION_NON_TRANSIENT,
    FAILURE_CLASSIFICATION_TIMEOUT,
    FAILURE_CLASSIFICATION_TRANSIENT,
    REAL_MODE,
    SIMULATION_MODE,
    BaseIntegration,
    _validate_real_mode_guards,
)

TEAMS_WEBHOOK_ENV = "TEAMS_WEBHOOK_URL"
TEAMS_REAL_ALLOW_ENV = "SOAR_REAL_TEAMS_ENABLED"
TEAMS_ENV_ENV = "SOAR_ENV"
TEAMS_TIMEOUT_ENV = "TEAMS_TIMEOUT_SECONDS"
DEFAULT_TEAMS_TIMEOUT_SECONDS = 3
MAX_TEAMS_TEXT_CHARS = 3000


# spec: SPEC-INTEG-004
def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _teams_webhook_configured() -> bool:
    return bool(os.getenv(TEAMS_WEBHOOK_ENV, "").strip())


def _teams_webhook_valid() -> bool:
    value = os.getenv(TEAMS_WEBHOOK_ENV, "").strip()
    if not value:
        return False
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        return False
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if host == "hooks.slack.com":
        return False
    return (
        "webhook.office.com" in host
        or "office.com" in host and "webhook" in path
        or "logic.azure.com" in host
    )


def _teams_real_mode_allowed() -> bool:
    readiness = _validate_real_mode_guards(
        "teams",
        mode=REAL_MODE,
        enabled_env=TEAMS_REAL_ALLOW_ENV,
        credential_envs=(TEAMS_WEBHOOK_ENV,),
    )
    return bool(readiness["real_mode_allowed"])


def get_teams_real_mode_readiness(configured_mode: str | None = None) -> dict[str, Any]:
    """Return safe Teams readiness metadata. Never include the webhook value."""
    mode = str(configured_mode or os.getenv("INTEGRATION_MODE", SIMULATION_MODE)).strip().lower()
    guard_readiness = _validate_real_mode_guards(
        "teams",
        mode=mode,
        enabled_env=TEAMS_REAL_ALLOW_ENV,
        credential_envs=(TEAMS_WEBHOOK_ENV,),
    )
    configured = _teams_webhook_configured()
    webhook_valid = _teams_webhook_valid()
    allowed = bool(guard_readiness["real_mode_allowed"])
    ready = bool(allowed and configured and webhook_valid)
    if mode != REAL_MODE:
        status = "simulation"
    elif guard_readiness["missing_guards"]:
        status = guard_readiness["real_mode_status"]
    elif not configured:
        status = "blocked: Teams webhook is not configured"
    elif not webhook_valid:
        status = "blocked: Teams webhook configuration is invalid"
    else:
        status = "ready"
    return {
        "teams_configured": configured,
        "real_mode_allowed": allowed,
        "real_mode_ready": ready,
        "real_mode_status": status,
        "webhook_configured": configured,
    }


def _get_timeout_seconds() -> int:
    raw = os.getenv(TEAMS_TIMEOUT_ENV, str(DEFAULT_TEAMS_TIMEOUT_SECONDS)).strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_TEAMS_TIMEOUT_SECONDS
    return max(1, min(value, 30))


def _format_teams_payload(action: str, params: dict[str, Any], context: dict[str, Any]) -> dict[str, str]:
    summary = str(
        params.get("message")
        or params.get("summary")
        or "SOAR playbook notification."
    ).strip()
    if not summary:
        summary = "SOAR playbook notification."
    summary = summary[:MAX_TEAMS_TEXT_CHARS]
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
    lines.append(f"Summary: {summary}")
    return {"text": "\n".join(lines)[:MAX_TEAMS_TEXT_CHARS]}


def _post_teams_webhook(webhook_url: str, payload: dict[str, str], timeout_seconds: int) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
        return {"status_code": getattr(resp, "status", None) or resp.getcode()}


class TeamsSimulationAdapter(BaseIntegration):
    adapter_name = "teams"
    supported_actions = frozenset({"send_message", "notify_channel", "notify_teams"})
    allow_real_mode = True

    def _simulate(self, action, params, context):
        return self._result(
            action,
            params,
            context,
            success=True,
            message="Simulated Teams action. No webhook or API call was made.",
            metadata={"delivery": "not_sent"},
        )

    def _execute_supported_action(self, action, params, context):
        if self.mode != REAL_MODE:
            return self._simulate(action, params, context)
        return self._execute_real_teams(action, params, context)

    def _execute_real_teams(self, action, params, context):
        readiness = get_teams_real_mode_readiness(REAL_MODE)
        timeout_seconds = _get_timeout_seconds()
        base_metadata = {
            "delivery": "not_sent",
            "teams_configured": readiness["teams_configured"],
            "real_mode_allowed": readiness["real_mode_allowed"],
            "real_mode_ready": readiness["real_mode_ready"],
            "webhook_configured": readiness["webhook_configured"],
            "timeout_seconds": timeout_seconds,
            "max_adapter_attempts": 1,
        }
        if not readiness["real_mode_ready"]:
            return self._result(
                action,
                params,
                context,
                success=False,
                message=f"Teams real mode failed closed: {readiness['real_mode_status']}.",
                metadata={
                    **base_metadata,
                    "failure_classification": FAILURE_CLASSIFICATION_NON_TRANSIENT,
                    "retry_eligible": False,
                },
                mode=REAL_MODE,
                simulated=True,
                executed=False,
            )

        webhook_url = os.getenv(TEAMS_WEBHOOK_ENV, "").strip()
        payload = _format_teams_payload(action, params, context)
        started = time.monotonic()
        try:
            response = _post_teams_webhook(webhook_url, payload, timeout_seconds)
        except TimeoutError:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            return self._result(
                action,
                params,
                context,
                success=False,
                message="Teams real-mode send timed out safely.",
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
            )
        except urllib.error.HTTPError as exc:
            status_code = int(getattr(exc, "code", 0) or 0)
            transient = status_code >= 500 or status_code == 429
            return self._result(
                action,
                params,
                context,
                success=False,
                message=f"Teams real-mode send failed safely with HTTP {status_code}.",
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
            )
        except urllib.error.URLError:
            return self._result(
                action,
                params,
                context,
                success=False,
                message="Teams real-mode send failed safely before confirmation.",
                metadata={
                    **base_metadata,
                    "failure_classification": FAILURE_CLASSIFICATION_TRANSIENT,
                    "retry_eligible": True,
                },
                mode=REAL_MODE,
                simulated=False,
                executed=False,
            )

        status_code = int(response.get("status_code") or 0)
        return self._result(
            action,
            params,
            context,
            success=200 <= status_code < 300,
            message="Teams real-mode notification sent.",
            metadata={
                **base_metadata,
                "delivery": "sent",
                "http_status": status_code,
                "payload_fields": sorted(_format_teams_payload(action, params, context).keys()),
                "retry_eligible": False,
            },
            mode=REAL_MODE,
            simulated=False,
            executed=True,
        )
