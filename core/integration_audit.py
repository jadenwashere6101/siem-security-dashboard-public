"""Safe audit helpers for SOAR integration execution attempts."""

from __future__ import annotations

import logging
from typing import Any

from core.audit_helpers import log_audit_event
from core.notification_delivery_store import redact_notification_delivery_metadata

SOAR_REAL_ADAPTER_ATTEMPT_EVENT = "SOAR_REAL_ADAPTER_ATTEMPT"

_LOGGER = logging.getLogger(__name__)
_SAFE_CONTEXT_KEYS = (
    "playbook_execution_id",
    "execution_id",
    "incident_id",
    "alert_id",
    "correlation_id",
    "idempotency_key",
)


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_text(value: Any, *, max_len: int = 256) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:max_len] if text else None


# spec: SPEC-INTEG-005 / SPEC-UI-004 - audit details expose safe metadata, never secrets.
def build_integration_attempt_audit_details(
    result: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an allowlisted, secret-free audit payload for adapter attempts."""
    safe_result = result if isinstance(result, dict) else {}
    safe_context = context if isinstance(context, dict) else {}
    metadata = safe_result.get("metadata") if isinstance(safe_result.get("metadata"), dict) else {}
    redacted_metadata = redact_notification_delivery_metadata(metadata)

    details: dict[str, Any] = {
        "adapter": _safe_text(safe_result.get("adapter")),
        "action": _safe_text(safe_result.get("action")),
        "mode": _safe_text(safe_result.get("mode")),
        "success": bool(safe_result.get("success")),
        "simulated": bool(safe_result.get("simulated")),
        "executed": bool(safe_result.get("executed")),
        "result_status": "success" if safe_result.get("success") is True else "failed",
        "failure_class": _safe_text(redacted_metadata.get("failure_classification")),
        "failure_code": _safe_text(redacted_metadata.get("failure_code")),
        "retry_eligible": bool(redacted_metadata.get("retry_eligible"))
        if "retry_eligible" in redacted_metadata
        else None,
    }

    execution_id = safe_context.get("playbook_execution_id", safe_context.get("execution_id"))
    details["playbook_execution_id"] = _safe_int(execution_id)
    details["incident_id"] = _safe_int(safe_context.get("incident_id"))
    details["alert_id"] = _safe_int(safe_context.get("alert_id"))
    details["correlation_id"] = _safe_text(safe_context.get("correlation_id"))
    details["idempotency_key"] = _safe_text(safe_context.get("idempotency_key"))

    for key in _SAFE_CONTEXT_KEYS:
        if key not in safe_context:
            continue
        if key in {"playbook_execution_id", "execution_id", "incident_id", "alert_id"}:
            continue
        details.setdefault(key, _safe_text(safe_context.get(key)))

    compacted = {key: value for key, value in details.items() if value is not None}
    return redact_notification_delivery_metadata(compacted)


# spec: SPEC-INTEG-005
def log_integration_execution_attempt(
    result: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write safe audit/log evidence for a real-mode adapter execution attempt."""
    details = build_integration_attempt_audit_details(result, context)
    _LOGGER.info(
        "soar_real_adapter_attempt adapter=%s action=%s mode=%s success=%s executed=%s",
        details.get("adapter"),
        details.get("action"),
        details.get("mode"),
        details.get("success"),
        details.get("executed"),
        extra={"event": SOAR_REAL_ADAPTER_ATTEMPT_EVENT, "details": details},
    )
    try:
        log_audit_event(SOAR_REAL_ADAPTER_ATTEMPT_EVENT, details=details)
    except Exception:
        _LOGGER.warning(
            "soar_real_adapter_attempt audit persistence failed safely",
            exc_info=True,
        )
    return details
