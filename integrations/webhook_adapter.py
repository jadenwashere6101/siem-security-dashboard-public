from __future__ import annotations

import ipaddress
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urljoin, urlparse

from core.integration_audit import log_integration_execution_attempt
from integrations.adapter_rate_limiter import check_adapter_rate_limit
from integrations.base_integration import (
    FAILURE_CLASSIFICATION_CREDENTIAL_MISSING,
    FAILURE_CLASSIFICATION_INVALID_CREDENTIALS,
    FAILURE_CLASSIFICATION_INVALID_TARGET,
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

WEBHOOK_URL_ENV = "WEBHOOK_URL"
WEBHOOK_BASE_URL_ENV = "WEBHOOK_BASE_URL"
WEBHOOK_REAL_ALLOW_ENV = "SOAR_REAL_WEBHOOK_ENABLED"
WEBHOOK_TIMEOUT_ENV = "WEBHOOK_TIMEOUT_SECONDS"
WEBHOOK_AUTH_TOKEN_ENV = "WEBHOOK_AUTH_TOKEN"
DEFAULT_WEBHOOK_TIMEOUT_SECONDS = 5
MAX_WEBHOOK_BODY_BYTES = 8192
MAX_WEBHOOK_SUMMARY_CHARS = 2000

_SAFE_PAYLOAD_KEYS = frozenset(
    {
        "alert_id",
        "alert_type",
        "event",
        "event_type",
        "execution_id",
        "incident_id",
        "message",
        "playbook_id",
        "severity",
        "source",
        "summary",
    }
)


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _configured_webhook_url() -> str:
    for env_name in (WEBHOOK_URL_ENV, WEBHOOK_BASE_URL_ENV):
        value = os.getenv(env_name, "").strip()
        if value:
            return value
    return ""


def _webhook_url_configured() -> bool:
    return bool(_configured_webhook_url())


def _hostname_from_url(url: str) -> str | None:
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    return (parsed.hostname or "").strip().lower() or None


def _is_blocked_hostname(hostname: str) -> bool:
    host = hostname.strip().lower().rstrip(".")
    if not host:
        return True
    if host in {"localhost", "0.0.0.0", "::1", "[::1]"}:
        return True
    if host.endswith(".localhost") or host.endswith(".local") or host.endswith(".internal"):
        return True
    if host == "metadata.google.internal" or host.endswith(".metadata.google.internal"):
        return True
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
        return bool(
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        )
    except ValueError:
        pass
    if host.startswith("127."):
        return True
    if host.startswith("10.") or host.startswith("192.168.") or host.startswith("169.254."):
        return True
    if host.startswith("172."):
        parts = host.split(".")
        if len(parts) >= 2:
            try:
                second = int(parts[1])
                if 16 <= second <= 31:
                    return True
            except ValueError:
                pass
    return False


def _validate_https_target_url(url: str) -> tuple[bool, str | None]:
    """Return (allowed, failure_classification). Never log or return the URL."""
    if not url:
        return False, FAILURE_CLASSIFICATION_CREDENTIAL_MISSING
    try:
        parsed = urlparse(url)
    except ValueError:
        return False, FAILURE_CLASSIFICATION_MALFORMED_PAYLOAD
    scheme = (parsed.scheme or "").strip().lower()
    if scheme in {"file", "ftp", "gopher", "javascript", "data"}:
        return False, FAILURE_CLASSIFICATION_INVALID_TARGET
    if scheme != "https":
        return False, FAILURE_CLASSIFICATION_INVALID_CREDENTIALS
    if not parsed.netloc:
        return False, FAILURE_CLASSIFICATION_MALFORMED_PAYLOAD
    hostname = _hostname_from_url(url)
    if not hostname or _is_blocked_hostname(hostname):
        return False, FAILURE_CLASSIFICATION_INVALID_TARGET
    return True, None


def get_webhook_real_mode_readiness(configured_mode: str | None = None) -> dict[str, Any]:
    """Return safe Webhook readiness metadata. Never include URL, token, or headers."""
    mode = str(configured_mode or os.getenv("INTEGRATION_MODE", SIMULATION_MODE)).strip().lower()
    guard_readiness = _validate_real_mode_guards(
        "webhook",
        mode=mode,
        enabled_env=WEBHOOK_REAL_ALLOW_ENV,
        credential_envs=(),
    )
    configured = _webhook_url_configured()
    missing_guards = list(guard_readiness["missing_guards"])
    if not configured:
        missing_guards.append(WEBHOOK_URL_ENV)
    missing_guards = list(dict.fromkeys(missing_guards))
    allowed = not missing_guards
    target_url = _configured_webhook_url()
    target_allowed = False
    target_failure: str | None = None
    if configured:
        target_allowed, target_failure = _validate_https_target_url(target_url)
    ready = bool(allowed and configured and target_allowed)
    if mode != REAL_MODE:
        status = "simulation"
    elif missing_guards:
        status = (
            f"blocked: webhook real mode requires guard(s): {', '.join(missing_guards)}"
        )
    elif not configured:
        status = "blocked: Webhook URL is not configured"
    elif not target_allowed:
        if target_failure == FAILURE_CLASSIFICATION_INVALID_CREDENTIALS:
            status = "blocked: Webhook URL must use https:// scheme"
        elif target_failure == FAILURE_CLASSIFICATION_INVALID_TARGET:
            status = "blocked: Webhook URL target is not allowed"
        else:
            status = "blocked: Webhook URL configuration is invalid"
    else:
        status = "ready"
    return {
        "webhook_configured": configured,
        "webhook_url_configured": configured,
        "webhook_real_enabled": _truthy(os.getenv(WEBHOOK_REAL_ALLOW_ENV)),
        "real_mode_allowed": allowed,
        "real_mode_ready": ready,
        "real_mode_status": status,
        "missing_guards": missing_guards,
        "credential_envs": [WEBHOOK_URL_ENV, WEBHOOK_BASE_URL_ENV],
    }


def _get_timeout_seconds() -> int:
    raw = os.getenv(WEBHOOK_TIMEOUT_ENV, str(DEFAULT_WEBHOOK_TIMEOUT_SECONDS)).strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_WEBHOOK_TIMEOUT_SECONDS
    return max(1, min(value, 60))


def _safe_scalar(value: Any, *, max_len: int = 512) -> str | int | float | bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value
    text = str(value).strip()
    if not text or "\n" in text or "\r" in text:
        return None
    return text[:max_len]


def _build_webhook_payload(action: str, params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "event": "soar_playbook_notification",
        "action": action,
        "playbook_id": _safe_scalar(context.get("playbook_id")),
        "execution_id": _safe_scalar(context.get("execution_id")),
        "alert_id": _safe_scalar(context.get("alert_id")),
        "incident_id": _safe_scalar(context.get("incident_id")),
    }
    nested = params.get("payload")
    if isinstance(nested, dict):
        for key, value in nested.items():
            normalized_key = str(key).strip().lower()
            if normalized_key not in _SAFE_PAYLOAD_KEYS:
                continue
            safe_value = _safe_scalar(value, max_len=MAX_WEBHOOK_SUMMARY_CHARS)
            if safe_value is not None:
                payload[normalized_key] = safe_value
    for key in _SAFE_PAYLOAD_KEYS:
        if key in payload:
            continue
        if key in params:
            safe_value = _safe_scalar(params.get(key), max_len=MAX_WEBHOOK_SUMMARY_CHARS)
            if safe_value is not None:
                payload[key] = safe_value
    summary = _safe_scalar(
        params.get("message") or params.get("summary") or params.get("event"),
        max_len=MAX_WEBHOOK_SUMMARY_CHARS,
    )
    if summary is not None:
        payload["summary"] = summary
    if not payload.get("summary"):
        payload["summary"] = "SOAR playbook notification."
    compacted = {key: value for key, value in payload.items() if value is not None}
    encoded = json.dumps(compacted, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(encoded) > MAX_WEBHOOK_BODY_BYTES:
        raise ValueError("Webhook payload exceeds maximum allowed size")
    return compacted


def _build_request_headers() -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "SOAR-Webhook/1.0",
    }
    token = os.getenv(WEBHOOK_AUTH_TOKEN_ENV, "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _resolve_request_url(params: dict[str, Any]) -> tuple[str | None, str | None]:
    base_url = _configured_webhook_url()
    if not base_url:
        return None, FAILURE_CLASSIFICATION_CREDENTIAL_MISSING
    allowed, failure = _validate_https_target_url(base_url)
    if not allowed:
        return None, failure
    path = str(params.get("path") or "").strip()
    if path:
        if not path.startswith("/") or "://" in path or path.startswith("//"):
            return None, FAILURE_CLASSIFICATION_MALFORMED_PAYLOAD
        target = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    else:
        target = base_url
    allowed, failure = _validate_https_target_url(target)
    if not allowed:
        return None, failure
    return target, None


def _post_webhook_request(
    target_url: str,
    payload: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(body) > MAX_WEBHOOK_BODY_BYTES:
        raise ValueError("Webhook payload exceeds maximum allowed size")
    req = urllib.request.Request(
        target_url,
        data=body,
        headers=_build_request_headers(),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
        return {"status_code": getattr(resp, "status", None) or resp.getcode()}


# spec: SPEC-INTEG-005 / SPEC-UI-004 - guarded real webhook path only; simulation-safe remains default.
class WebhookSimulationAdapter(BaseIntegration):
    adapter_name = "webhook"
    supported_actions = frozenset({"post_event", "send_webhook", "notify_webhook"})
    allow_real_mode = True

    def _simulate(self, action, params, context):
        return self._result(
            action,
            params,
            context,
            success=True,
            message="Simulated webhook action. No HTTP request was made.",
            metadata={"delivery": "not_sent"},
        )

    def _execute_supported_action(self, action, params, context):
        if self.mode != REAL_MODE:
            return self._simulate(action, params, context)
        return self._execute_real_webhook(action, params, context)

    # spec: SPEC-INTEG-005
    def _audit_real_attempt(self, result, context):
        log_integration_execution_attempt(result, context)
        return result

    def _execute_real_webhook(self, action, params, context):
        readiness = get_webhook_real_mode_readiness(REAL_MODE)
        timeout_seconds = _get_timeout_seconds()
        base_metadata = {
            "delivery": "not_sent",
            "webhook_configured": readiness["webhook_configured"],
            "webhook_url_configured": readiness["webhook_url_configured"],
            "webhook_real_enabled": readiness["webhook_real_enabled"],
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
                message=f"Webhook real mode failed closed: {readiness['real_mode_status']}.",
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
            failure = FAILURE_CLASSIFICATION_MALFORMED_PAYLOAD
            if "https://" in readiness["real_mode_status"]:
                failure = FAILURE_CLASSIFICATION_INVALID_CREDENTIALS
            elif "target is not allowed" in readiness["real_mode_status"]:
                failure = FAILURE_CLASSIFICATION_INVALID_TARGET
            return self._audit_real_attempt(self._result(
                action,
                params,
                context,
                success=False,
                message=f"Webhook real mode failed closed: {readiness['real_mode_status']}.",
                metadata={
                    **base_metadata,
                    "failure_classification": failure,
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
                message="Webhook real-mode send blocked safely by adapter rate limit.",
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

        target_url, target_failure = _resolve_request_url(params)
        if not target_url:
            return self._audit_real_attempt(self._result(
                action,
                params,
                context,
                success=False,
                message="Webhook real-mode target rejected safely before outbound call.",
                metadata={
                    **base_metadata,
                    "failure_classification": target_failure or FAILURE_CLASSIFICATION_INVALID_TARGET,
                    "retry_eligible": False,
                },
                mode=REAL_MODE,
                simulated=False,
                executed=False,
            ), context)

        try:
            payload = _build_webhook_payload(action, params, context)
        except ValueError as exc:
            return self._audit_real_attempt(self._result(
                action,
                params,
                context,
                success=False,
                message=f"Webhook real-mode payload rejected safely: {exc}",
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
            response = _post_webhook_request(target_url, payload, timeout_seconds)
        except TimeoutError:
            return self._audit_real_attempt(self._result(
                action,
                params,
                context,
                success=False,
                message="Webhook real-mode send timed out safely.",
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
        except urllib.error.HTTPError as exc:
            status_code = int(getattr(exc, "code", 0) or 0)
            if status_code == 429:
                classification = FAILURE_CLASSIFICATION_PROVIDER_RATE_LIMITED
                retryable = True
            elif status_code >= 500:
                classification = FAILURE_CLASSIFICATION_TEMPORARY_PROVIDER_FAILURE
                retryable = True
            else:
                classification = FAILURE_CLASSIFICATION_MALFORMED_PAYLOAD
                retryable = False
            return self._audit_real_attempt(self._result(
                action,
                params,
                context,
                success=False,
                message=f"Webhook real-mode send failed safely with HTTP {status_code}.",
                metadata={
                    **base_metadata,
                    "failure_classification": classification,
                    "retry_eligible": retryable,
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
                message="Webhook real-mode send failed safely before confirmation.",
                metadata={
                    **base_metadata,
                    "failure_classification": FAILURE_CLASSIFICATION_TRANSIENT_NETWORK_ERROR,
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
            message="Webhook real-mode notification sent.",
            metadata={
                **base_metadata,
                "delivery": "sent",
                "http_status": status_code,
                "payload_fields": sorted(payload.keys()),
                "retry_eligible": False,
                "elapsed_ms": int((time.monotonic() - started) * 1000),
            },
            mode=REAL_MODE,
            simulated=False,
            executed=True,
        ), context)
