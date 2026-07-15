from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from core import notification_delivery_store
from core.notification_policy_store import get_effective_notification_policy, load_notification_policy
from core.recon_activity_store import (
    fetch_recon_activity_notification_state,
    record_recon_activity_notification,
)
from integrations.base_integration import REAL_MODE
from integrations.integration_registry import get_integration_adapter

SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}

ROUTE_KEY_PFSENSE = "pfsense"
ROUTE_KEY_HONEYPOT = "honeypot"
ROUTE_KEY_CRITICAL_CROSS_SOURCE = "critical_cross_source"
logger = logging.getLogger(__name__)

PURPOSE_IMMEDIATE_ALERT = "immediate_alert"
PURPOSE_INCIDENT_CREATED = "incident_created"
PURPOSE_INVESTIGATION_UPDATE = "investigation_update"
PURPOSE_CONTAINMENT_OUTCOME = "containment_outcome"
PURPOSE_ROUTE_TEST = "route_test"

NOTIFICATION_PURPOSES = frozenset(
    {
        PURPOSE_IMMEDIATE_ALERT,
        PURPOSE_INCIDENT_CREATED,
        PURPOSE_INVESTIGATION_UPDATE,
        PURPOSE_CONTAINMENT_OUTCOME,
        PURPOSE_ROUTE_TEST,
    }
)

DELIVERY_STAGE_INITIAL = "initial"
DELIVERY_STAGE_PLAYBOOK = "playbook"
DELIVERY_STAGE_TEST = "test"


def normalize_notification_source(source: Any, source_type: Any = None) -> str | None:
    normalized_source = str(source or "").strip().lower()
    normalized_source_type = str(source_type or "").strip().lower()
    if normalized_source == "pfsense" or normalized_source_type == "firewall":
        return ROUTE_KEY_PFSENSE
    if normalized_source == "honeypot" or normalized_source_type == "honeypot":
        return ROUTE_KEY_HONEYPOT
    return None


def _policy_destination(policy: dict[str, Any], route_key: str) -> str | None:
    if route_key == ROUTE_KEY_PFSENSE:
        value = policy.get("pfsense_destination")
        return (str(value).strip() or None) if value is not None else None
    if route_key == ROUTE_KEY_HONEYPOT:
        value = policy.get("honeypot_destination")
        return (str(value).strip() or None) if value is not None else None
    if route_key == ROUTE_KEY_CRITICAL_CROSS_SOURCE:
        value = policy.get("critical_cross_source_destination")
        return (str(value).strip() or None) if value is not None else None
    return None


def _delivery_status_from_adapter_result(adapter_result: dict[str, Any]) -> str:
    if adapter_result.get("success") is True:
        return "success"
    metadata = adapter_result.get("metadata") if isinstance(adapter_result.get("metadata"), dict) else {}
    classification = str(metadata.get("failure_classification") or "").strip().lower()
    if classification == "timeout" or metadata.get("timed_out") is True:
        return "timeout"
    if classification in {
        "circuit_open",
        "circuit_state_invalid",
        "provider_rate_limited",
        "guard_failed",
        "credential_missing",
    }:
        return "blocked"
    return "failed"


def _normalize_notification_purpose(value: Any, *, default: str) -> str:
    purpose = str(value or "").strip().lower()
    if purpose in NOTIFICATION_PURPOSES:
        return purpose
    return default


def _delivery_stage_for_purpose(purpose: str) -> str:
    if purpose == PURPOSE_ROUTE_TEST:
        return DELIVERY_STAGE_TEST
    if purpose in {PURPOSE_INVESTIGATION_UPDATE, PURPOSE_CONTAINMENT_OUTCOME}:
        return DELIVERY_STAGE_PLAYBOOK
    return DELIVERY_STAGE_INITIAL


def evaluate_notification_policy(
    policy: dict[str, Any],
    *,
    event_kind: str,
    severity: Any,
    source: Any,
    source_type: Any = None,
    bypass_slack_disabled: bool = False,
) -> dict[str, Any]:
    if policy.get("status") == "unavailable":
        return {"should_notify": False, "reason": "policy_unavailable", "route_key": None, "destination": None}

    normalized_kind = str(event_kind or "").strip().lower()
    if normalized_kind in {"alert", "recon_activity"} and not policy.get("notify_on_alerts", True):
        return {"should_notify": False, "reason": "alerts_disabled", "route_key": None, "destination": None}
    if normalized_kind == "incident" and not policy.get("notify_on_incidents", True):
        return {"should_notify": False, "reason": "incidents_disabled", "route_key": None, "destination": None}
    if not bypass_slack_disabled and not policy.get("slack_enabled", False):
        return {"should_notify": False, "reason": "slack_disabled", "route_key": None, "destination": None}

    normalized_severity = str(severity or "").strip().lower()
    threshold = str(policy.get("minimum_severity") or "high").strip().lower()
    if normalized_severity not in SEVERITY_RANK or threshold not in SEVERITY_RANK:
        return {"should_notify": False, "reason": "invalid_severity", "route_key": None, "destination": None}
    if SEVERITY_RANK[normalized_severity] < SEVERITY_RANK[threshold]:
        return {"should_notify": False, "reason": "below_minimum_severity", "route_key": None, "destination": None}

    route_key = normalize_notification_source(source, source_type)
    if route_key is None and normalized_severity == "critical":
        route_key = ROUTE_KEY_CRITICAL_CROSS_SOURCE
    destination = _policy_destination(policy, route_key) if route_key else None
    if route_key is None or not destination:
        return {"should_notify": False, "reason": "source_not_routed", "route_key": route_key, "destination": None}
    return {
        "should_notify": True,
        "reason": "eligible",
        "route_key": route_key,
        "destination": destination,
        "slack_format": policy.get("slack_format", "compact"),
    }


def _compact_alert_text(alert: dict[str, Any], destination: str) -> str:
    return (
        f"[{destination}] ALERT {str(alert.get('severity') or '').upper()} "
        f"{alert.get('source') or 'unknown'} "
        f"#{alert.get('id')} {alert.get('message') or 'Notification'}"
    )[:3000]


def _detailed_alert_text(alert: dict[str, Any], destination: str) -> str:
    lines = [
        f"[{destination}] Alert notification",
        f"Severity: {str(alert.get('severity') or '').upper() or 'UNKNOWN'}",
        f"Rule: {alert.get('alert_type') or 'unknown'}",
        f"Source: {alert.get('source') or 'unknown'}",
    ]
    if alert.get("source_ip"):
        lines.append(f"Source IP: {alert['source_ip']}")
    if alert.get("message"):
        lines.append(f"Summary: {alert['message']}")
    mitre = alert.get("mitre") if isinstance(alert.get("mitre"), str) else None
    if mitre:
        lines.append(f"MITRE: {mitre}")
    if alert.get("response_action"):
        lines.append(f"Response action: {alert['response_action']}")
    if alert.get("response_status"):
        lines.append(f"Response status: {alert['response_status']}")
    target_context = alert.get("target_context") if isinstance(alert.get("target_context"), str) else None
    if target_context:
        lines.append(f"Target context: {target_context}")
    return "\n".join(lines)[:3000]


def format_alert_notification(alert: dict[str, Any], *, slack_format: str, destination: str) -> str:
    if slack_format == "detailed":
        return _detailed_alert_text(alert, destination)
    return _compact_alert_text(alert, destination)


def _compact_recon_activity_text(activity: dict[str, Any], destination: str) -> str:
    return (
        f"[{destination}] RECON {str(activity.get('severity') or '').upper()} "
        f"#{activity.get('id')} {activity.get('message') or 'Distributed Internet Reconnaissance Activity'}"
    )[:3000]


def _detailed_recon_activity_text(activity: dict[str, Any], destination: str) -> str:
    lines = [
        f"[{destination}] Recon activity notification",
        f"Severity: {str(activity.get('severity') or '').upper() or 'UNKNOWN'}",
        f"Label: {activity.get('message') or 'Distributed Internet Reconnaissance Activity'}",
        f"Status: {activity.get('status') or 'unknown'}",
    ]
    if activity.get("assessment_text"):
        lines.append(f"Assessment: {activity['assessment_text']}")
    if activity.get("target_context"):
        lines.append(f"Target context: {activity['target_context']}")
    return "\n".join(lines)[:3000]


def format_recon_activity_notification(
    activity: dict[str, Any], *, slack_format: str, destination: str
) -> str:
    if slack_format == "detailed":
        return _detailed_recon_activity_text(activity, destination)
    return _compact_recon_activity_text(activity, destination)


def _compact_incident_text(incident: dict[str, Any], destination: str) -> str:
    return (
        f"[{destination}] INCIDENT {str(incident.get('severity') or '').upper()} "
        f"#{incident.get('id')} {incident.get('title') or 'Notification'}"
    )[:3000]


def _detailed_incident_text(incident: dict[str, Any], destination: str) -> str:
    lines = [
        f"[{destination}] Incident notification",
        f"Severity: {str(incident.get('severity') or '').upper() or 'UNKNOWN'}",
        f"Title: {incident.get('title') or 'Untitled incident'}",
        f"Status: {incident.get('status') or 'unknown'}",
    ]
    if incident.get("source_ip"):
        lines.append(f"Source IP: {incident['source_ip']}")
    if incident.get("alert_type"):
        lines.append(f"Rule: {incident['alert_type']}")
    if incident.get("source"):
        lines.append(f"Source: {incident['source']}")
    if incident.get("response_action"):
        lines.append(f"Response action: {incident['response_action']}")
    if incident.get("target_context"):
        lines.append(f"Target context: {incident['target_context']}")
    return "\n".join(lines)[:3000]


def format_incident_notification(incident: dict[str, Any], *, slack_format: str, destination: str) -> str:
    if slack_format == "detailed":
        return _detailed_incident_text(incident, destination)
    return _compact_incident_text(incident, destination)


def _playbook_purpose_label(purpose: str) -> str:
    if purpose == PURPOSE_CONTAINMENT_OUTCOME:
        return "Containment outcome"
    if purpose == PURPOSE_INVESTIGATION_UPDATE:
        return "Investigation update"
    return "Notification update"


def _default_playbook_message(purpose: str, event_kind: str) -> str:
    if purpose == PURPOSE_CONTAINMENT_OUTCOME:
        return "Containment outcome update."
    if event_kind == "incident":
        return "Incident investigation update."
    return "Alert investigation update."


def _compact_playbook_text(
    subject: dict[str, Any],
    *,
    destination: str,
    event_kind: str,
    purpose: str,
    message: str,
) -> str:
    object_id = subject.get("id")
    severity = str(subject.get("severity") or "").upper() or "UNKNOWN"
    if event_kind == "incident":
        title = subject.get("title") or "Incident update"
        return f"[{destination}] {purpose.upper()} {severity} #{object_id} {title} {message}".strip()[:3000]
    source = subject.get("source") or "unknown"
    return f"[{destination}] {purpose.upper()} {severity} {source} #{object_id} {message}".strip()[:3000]


def _detailed_playbook_text(
    subject: dict[str, Any],
    *,
    destination: str,
    event_kind: str,
    purpose: str,
    message: str,
) -> str:
    lines = [
        f"[{destination}] {_playbook_purpose_label(purpose)}",
        f"Severity: {str(subject.get('severity') or '').upper() or 'UNKNOWN'}",
        f"Purpose: {purpose}",
    ]
    if event_kind == "incident":
        lines.extend(
            [
                f"Title: {subject.get('title') or 'Untitled incident'}",
                f"Status: {subject.get('status') or 'unknown'}",
            ]
        )
    else:
        lines.extend(
            [
                f"Rule: {subject.get('alert_type') or 'unknown'}",
                f"Source: {subject.get('source') or 'unknown'}",
            ]
        )
    if subject.get("source_ip"):
        lines.append(f"Source IP: {subject['source_ip']}")
    if subject.get("alert_type") and event_kind == "incident":
        lines.append(f"Rule: {subject['alert_type']}")
    if subject.get("source") and event_kind == "incident":
        lines.append(f"Source: {subject['source']}")
    if subject.get("response_action"):
        lines.append(f"Response action: {subject['response_action']}")
    if subject.get("response_status"):
        lines.append(f"Response status: {subject['response_status']}")
    target_context = subject.get("target_context") if isinstance(subject.get("target_context"), str) else None
    if target_context:
        lines.append(f"Target context: {target_context}")
    lines.append(f"Summary: {message}")
    return "\n".join(lines)[:3000]


def format_playbook_notification(
    subject: dict[str, Any],
    *,
    slack_format: str,
    destination: str,
    event_kind: str,
    purpose: str,
    message: str | None,
) -> str:
    text = (str(message).strip() if message is not None else "") or _default_playbook_message(
        purpose, event_kind
    )
    if slack_format == "detailed":
        return _detailed_playbook_text(
            subject,
            destination=destination,
            event_kind=event_kind,
            purpose=purpose,
            message=text,
        )
    return _compact_playbook_text(
        subject,
        destination=destination,
        event_kind=event_kind,
        purpose=purpose,
        message=text,
    )


def _notification_correlation_id(kind: str, object_id: int, route_key: str) -> str:
    return f"policy-{kind}-{route_key}-{object_id}-{uuid4().hex[:10]}"


def _notification_idempotency_key(
    kind: str,
    object_id: int,
    route_key: str,
    purpose: str,
    delivery_stage: str,
    scope_suffix: str | None = None,
) -> str:
    suffix = f":{scope_suffix}" if scope_suffix else ""
    raw = f"policy:{kind}:{object_id}:{route_key}:{purpose}:{delivery_stage}{suffix}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


def _existing_policy_delivery(conn, *, idempotency_key: str) -> dict[str, Any] | None:
    rows = notification_delivery_store.list_notification_delivery_attempts(
        conn,
        idempotency_key=idempotency_key,
        limit=10,
    )
    for row in rows:
        if row.get("status") in {"success", "pending"}:
            return row
    return None


def _record_attempt(
    conn,
    *,
    correlation_id: str,
    idempotency_key: str,
    status: str,
    failure_code: str | None,
    failure_message: str | None,
    metadata: dict[str, Any],
    alert_id: int | None = None,
    incident_id: int | None = None,
    playbook_execution_id: int | None = None,
    playbook_step_index: int | None = None,
    mode_override: str | None = None,
    timeout_seconds: int | None = None,
    circuit_breaker_state: str | None = None,
    recon_activity_id: int | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    record_mode = str(mode_override or "").strip().lower()
    if record_mode not in {"simulation", "real"}:
        record_mode = "real" if status in {"success", "failed", "timeout"} else "simulation"
    return notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        provider="slack",
        mode=record_mode,
        status=status,
        adapter_name="slack",
        action="send_message",
        alert_id=alert_id,
        incident_id=incident_id,
        recon_activity_id=recon_activity_id,
        playbook_execution_id=playbook_execution_id,
        playbook_step_index=playbook_step_index,
        requested_at=now,
        started_at=now,
        completed_at=now,
        failure_code=failure_code,
        failure_message=failure_message,
        timeout_seconds=timeout_seconds,
        circuit_breaker_state=circuit_breaker_state,
        metadata=metadata,
    )


def _record_attempt_safe(conn, **kwargs) -> dict[str, Any] | None:
    try:
        return _record_attempt(conn, **kwargs)
    except Exception:
        logger.warning(
            "notification policy delivery attempt tracking failed safely",
            exc_info=True,
        )
        return None


def _deliver_notification(
    conn,
    *,
    event_kind: str,
    object_id: int,
    subject: dict[str, Any],
    policy: dict[str, Any],
    purpose: str,
    custom_text: str | None = None,
    requested_by: str | None = None,
    bypass_slack_disabled: bool = False,
    allow_dedup: bool = True,
    playbook_execution_id: int | None = None,
    playbook_step_index: int | None = None,
    correlation_kind: str | None = None,
    destination_label_override: str | None = None,
    idempotency_scope_suffix: str | None = None,
    recon_activity_id: int | None = None,
) -> dict[str, Any]:
    normalized_purpose = _normalize_notification_purpose(
        purpose,
        default=PURPOSE_IMMEDIATE_ALERT if event_kind == "alert" else PURPOSE_INCIDENT_CREATED,
    )
    delivery_stage = _delivery_stage_for_purpose(normalized_purpose)
    decision = evaluate_notification_policy(
        policy,
        event_kind=event_kind,
        severity=subject.get("severity"),
        source=subject.get("source"),
        source_type=subject.get("source_type"),
        bypass_slack_disabled=bypass_slack_disabled,
    )
    route_key = decision.get("route_key") or "unrouted"
    correlation_id = _notification_correlation_id(
        correlation_kind or event_kind,
        object_id,
        route_key,
    )
    idempotency_key = _notification_idempotency_key(
        event_kind,
        object_id,
        route_key,
        normalized_purpose,
        delivery_stage,
        idempotency_scope_suffix,
    )
    common_metadata = {
        "notification_policy": True,
        "event_kind": event_kind,
        "purpose": normalized_purpose,
        "delivery_stage": delivery_stage,
        "source": subject.get("source"),
        "source_type": subject.get("source_type"),
        "severity": subject.get("severity"),
        "requested_by": requested_by,
        "playbook_execution_id": playbook_execution_id,
        "playbook_step_index": playbook_step_index,
        "recon_activity_id": recon_activity_id,
    }
    alert_ref = object_id if event_kind == "alert" and object_id > 0 else None
    incident_ref = object_id if event_kind == "incident" and object_id > 0 else None

    if not decision["should_notify"]:
        attempt = _record_attempt_safe(
            conn,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            status="blocked",
            failure_code=decision["reason"],
            failure_message=f"Notification policy suppressed Slack delivery: {decision['reason']}.",
            metadata={
                **common_metadata,
                "policy_status": policy.get("status"),
                "policy_reason": decision["reason"],
                "executed": False,
                "simulated": True,
            },
            alert_id=alert_ref,
            incident_id=incident_ref,
            playbook_execution_id=playbook_execution_id,
            playbook_step_index=playbook_step_index,
            recon_activity_id=recon_activity_id,
        )
        return {
            "success": False,
            "suppressed": True,
            "duplicate": False,
            "purpose": normalized_purpose,
            "delivery_stage": delivery_stage,
            "route_key": route_key,
            "message": (
                attempt["failure_message"]
                if attempt is not None
                else f"Notification policy suppressed Slack delivery: {decision['reason']}."
            ),
            "attempt": attempt,
            "adapter_result": None,
            "policy_decision": decision,
        }

    if allow_dedup:
        existing = _existing_policy_delivery(conn, idempotency_key=idempotency_key)
        if existing is not None:
            attempt = _record_attempt_safe(
                conn,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                status="blocked",
                failure_code="duplicate_delivery",
                failure_message="Equivalent Slack notification already delivered; duplicate send suppressed.",
                metadata={
                    **common_metadata,
                    "route_key": decision["route_key"],
                    "destination_label": decision["destination"],
                    "duplicate_of_attempt_id": existing.get("id"),
                    "duplicate_of_status": existing.get("status"),
                    "executed": False,
                    "simulated": True,
                },
                alert_id=alert_ref,
                incident_id=incident_ref,
                playbook_execution_id=playbook_execution_id,
                playbook_step_index=playbook_step_index,
                recon_activity_id=recon_activity_id,
            )
            return {
                "success": False,
                "suppressed": True,
                "duplicate": True,
                "purpose": normalized_purpose,
                "delivery_stage": delivery_stage,
                "route_key": route_key,
                "message": (
                    attempt["failure_message"]
                    if attempt is not None
                    else "Equivalent Slack notification already delivered; duplicate send suppressed."
                ),
                "attempt": attempt,
                "adapter_result": None,
                "policy_decision": decision,
            }

    destination = destination_label_override or decision["destination"]
    if normalized_purpose == PURPOSE_ROUTE_TEST:
        text = _format_route_test_text(
            decision["route_key"],
            destination,
            str(decision["slack_format"] or "compact"),
        )
    elif event_kind == "recon_activity":
        text = format_recon_activity_notification(
            subject,
            slack_format=decision["slack_format"],
            destination=destination,
        )
    elif normalized_purpose == PURPOSE_IMMEDIATE_ALERT and event_kind == "alert":
        text = format_alert_notification(
            subject,
            slack_format=decision["slack_format"],
            destination=destination,
        )
    elif normalized_purpose == PURPOSE_INCIDENT_CREATED and event_kind == "incident":
        text = format_incident_notification(
            subject,
            slack_format=decision["slack_format"],
            destination=destination,
        )
    else:
        text = format_playbook_notification(
            subject,
            slack_format=decision["slack_format"],
            destination=destination,
            event_kind=event_kind,
            purpose=normalized_purpose,
            message=custom_text,
        )

    adapter = get_integration_adapter("slack", mode=REAL_MODE)
    result = adapter.execute(
        "send_message",
        params={
            "text": text,
            "message": custom_text or subject.get("message") or subject.get("title"),
            "destination_label": destination,
        },
        context={
            "alert_id": alert_ref,
            "incident_id": incident_ref,
            "playbook_id": "notification_policy" if playbook_execution_id is None else subject.get("playbook_id"),
            "execution_id": correlation_id if playbook_execution_id is None else playbook_execution_id,
            "notification_policy": True,
            "route_key": decision["route_key"],
            "purpose": normalized_purpose,
            "delivery_stage": delivery_stage,
            "playbook_execution_id": playbook_execution_id,
            "playbook_step_index": playbook_step_index,
        },
    )
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    attempt = _record_attempt_safe(
        conn,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        status=_delivery_status_from_adapter_result(result),
        failure_code=metadata.get("failure_classification"),
        failure_message=None if result.get("success") else result.get("message"),
        metadata={
            **common_metadata,
            "route_key": decision["route_key"],
            "destination_label": destination,
            "slack_format": decision["slack_format"],
            "adapter_mode": result.get("mode"),
            "executed": result.get("executed"),
            "simulated": result.get("simulated"),
            "provider_success": metadata.get("provider_success"),
            "failure_classification": metadata.get("failure_classification"),
            "rate_limited": metadata.get("rate_limited"),
            "adapter_result": {
                "success": result.get("success"),
                "failure_classification": metadata.get("failure_classification"),
            },
        },
        alert_id=alert_ref,
        incident_id=incident_ref,
        playbook_execution_id=playbook_execution_id,
        playbook_step_index=playbook_step_index,
        recon_activity_id=recon_activity_id,
        timeout_seconds=metadata.get("timeout_seconds"),
        circuit_breaker_state=metadata.get("circuit_state"),
        mode_override=str(result.get("mode") or "simulation"),
    )
    return {
        "success": attempt["status"] == "success" if attempt is not None else bool(result.get("success")),
        "suppressed": False,
        "duplicate": False,
        "purpose": normalized_purpose,
        "delivery_stage": delivery_stage,
        "route_key": decision["route_key"],
        "message": result.get("message"),
        "attempt": attempt,
        "adapter_result": result,
        "policy_decision": decision,
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


def _route_test_source(route_key: str) -> tuple[str, str]:
    if route_key == ROUTE_KEY_PFSENSE:
        return ("pfsense", "firewall")
    if route_key == ROUTE_KEY_HONEYPOT:
        return ("honeypot", "honeypot")
    if route_key == ROUTE_KEY_CRITICAL_CROSS_SOURCE:
        return ("bank_app", "custom")
    raise ValueError("Notification policy test route is not supported")


def _format_route_test_text(route_key: str, destination: str, slack_format: str) -> str:
    if route_key == ROUTE_KEY_PFSENSE:
        route_label = "pfSense"
    elif route_key == ROUTE_KEY_HONEYPOT:
        route_label = "Honeypot"
    else:
        route_label = "Critical / Cross-Source"
    header = f"[{destination}] NOTIFICATION POLICY ROUTE TEST"
    compact = f"{header} {route_label} synthetic verification message. No alert or incident was created."
    if slack_format == "detailed":
        return "\n".join(
            [
                f"[{destination}] Notification policy route test",
                f"Route: {route_label}",
                "Severity: CRITICAL",
                "Source: synthetic_admin_test",
                "Summary: Synthetic notification-policy route verification. No alert, incident, playbook, approval, or SOAR execution was created.",
            ]
        )[:3000]
    return compact[:3000]


def fetch_alert_notification_context(conn, alert_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                id,
                alert_type,
                severity,
                host(source_ip),
                source,
                source_type,
                message,
                response_action,
                response_status,
                context
            FROM alerts
            WHERE id = %s
            """,
            (alert_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "alert_type": row[1],
            "severity": row[2],
            "source_ip": row[3],
            "source": row[4],
            "source_type": row[5],
            "message": row[6],
            "response_action": row[7],
            "response_status": row[8],
            "context": row[9] if isinstance(row[9], dict) else {},
        }


def fetch_incident_notification_context(conn, incident_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                incidents.id,
                incidents.title,
                incidents.severity,
                incidents.status,
                host(incidents.source_ip),
                alerts.alert_type,
                alerts.source,
                alerts.source_type,
                alerts.response_action,
                alerts.response_status
            FROM incidents
            LEFT JOIN incident_alerts ON incident_alerts.incident_id = incidents.id
            LEFT JOIN alerts ON alerts.id = incident_alerts.alert_id
            WHERE incidents.id = %s
            ORDER BY incident_alerts.linked_at ASC NULLS LAST
            LIMIT 1
            """,
            (incident_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "title": row[1],
            "severity": row[2],
            "status": row[3],
            "source_ip": row[4],
            "alert_type": row[5],
            "source": row[6],
            "source_type": row[7],
            "response_action": row[8],
            "response_status": row[9],
        }


def notify_for_alert(conn, alert_id: int) -> dict[str, Any] | None:
    alert = fetch_alert_notification_context(conn, alert_id)
    if alert is None:
        return None
    policy_override = alert.get("context") if isinstance(alert.get("context"), dict) else {}
    if (
        isinstance(policy_override.get("notification_policy"), dict)
        and policy_override["notification_policy"].get("immediate_alert_eligible") is False
    ):
        return None
    policy = get_effective_notification_policy()
    result = _deliver_notification(
        conn,
        event_kind="alert",
        object_id=alert_id,
        subject=alert,
        policy=policy,
        purpose=PURPOSE_IMMEDIATE_ALERT,
    )
    return result["attempt"]


def fetch_recon_activity_notification_context(conn, activity_id: int) -> dict[str, Any] | None:
    activity = fetch_recon_activity_notification_state(conn, activity_id)
    if activity is None:
        return None
    target_context = (
        activity["summary"].get("target_context")
        if isinstance(activity.get("summary"), dict)
        else {}
    )
    return {
        "id": activity["id"],
        "severity": activity["severity"],
        "status": activity["status"],
        "source": activity["source"],
        "source_type": activity["source_type"],
        "message": "Distributed Internet Reconnaissance Activity",
        "assessment_text": activity["assessment_text"],
        "coordination_status": activity["coordination_status"],
        "summary": activity["summary"],
        "target_context": json.dumps(target_context, sort_keys=True) if target_context else None,
        "opened_notification_sent_at": activity["opened_notification_sent_at"],
        "last_notified_fingerprint": activity["last_notified_fingerprint"],
        "last_notified_at": activity["last_notified_at"],
    }


def _recon_activity_material_fingerprint(activity: dict[str, Any]) -> str:
    summary = activity.get("summary") if isinstance(activity.get("summary"), dict) else {}
    ports = [int(value) for value in (summary.get("primary_destination_ports") or [])]
    payload = {
        "severity": str(activity.get("severity") or "").lower(),
        "status": str(activity.get("status") or "").lower(),
        "coordination_status": str(activity.get("coordination_status") or "").lower(),
        "primary_destination_ports": ports[:5],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def notify_for_recon_activity(
    conn,
    activity_id: int,
    *,
    purpose: str = PURPOSE_IMMEDIATE_ALERT,
    idempotency_scope_suffix: str | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    activity = fetch_recon_activity_notification_context(conn, activity_id)
    if activity is None:
        return None
    effective_policy = policy or get_effective_notification_policy()
    result = _deliver_notification(
        conn,
        event_kind="recon_activity",
        object_id=activity_id,
        subject=activity,
        policy=effective_policy,
        purpose=purpose,
        idempotency_scope_suffix=idempotency_scope_suffix,
        recon_activity_id=activity_id,
    )
    return result


def notify_for_material_recon_activity(conn, activity_id: int) -> dict[str, Any] | None:
    activity = fetch_recon_activity_notification_context(conn, activity_id)
    if activity is None:
        return None

    fingerprint = _recon_activity_material_fingerprint(activity)
    already_opened = activity.get("opened_notification_sent_at") is not None
    policy = get_effective_notification_policy()
    decision = evaluate_notification_policy(
        policy,
        event_kind="recon_activity",
        severity=activity.get("severity"),
        source=activity.get("source"),
        source_type=activity.get("source_type"),
    )
    if not decision.get("should_notify"):
        return {
            "success": False,
            "suppressed": True,
            "duplicate": False,
            "purpose": PURPOSE_IMMEDIATE_ALERT if not already_opened else PURPOSE_INVESTIGATION_UPDATE,
            "delivery_stage": DELIVERY_STAGE_INITIAL if not already_opened else DELIVERY_STAGE_PLAYBOOK,
            "route_key": decision.get("route_key") or "unrouted",
            "message": f"Recon activity notification suppressed by policy: {decision['reason']}.",
            "attempt": None,
            "adapter_result": None,
            "policy_decision": decision,
        }
    if not already_opened:
        result = notify_for_recon_activity(
            conn,
            activity_id,
            purpose=PURPOSE_IMMEDIATE_ALERT,
            idempotency_scope_suffix=f"opening:{fingerprint}",
            policy=policy,
        )
        if (
            result
            and not result.get("suppressed")
            and isinstance(result.get("attempt"), dict)
            and result["attempt"].get("status") in {"success", "pending"}
        ):
            record_recon_activity_notification(
                conn,
                activity_id,
                fingerprint=fingerprint,
                opened_at=datetime.now(timezone.utc),
            )
        return result

    if fingerprint == activity.get("last_notified_fingerprint"):
        return {
            "success": False,
            "suppressed": True,
            "duplicate": True,
            "purpose": PURPOSE_INVESTIGATION_UPDATE,
            "delivery_stage": DELIVERY_STAGE_PLAYBOOK,
            "route_key": normalize_notification_source(activity.get("source"), activity.get("source_type")) or "unrouted",
            "message": "Recon activity notification suppressed because no material aggregate change occurred.",
            "attempt": None,
            "adapter_result": None,
            "policy_decision": {"should_notify": False, "reason": "no_material_change"},
        }

    result = notify_for_recon_activity(
        conn,
        activity_id,
        purpose=PURPOSE_INVESTIGATION_UPDATE,
        idempotency_scope_suffix=f"update:{fingerprint}",
        policy=policy,
    )
    if (
        result
        and not result.get("suppressed")
        and isinstance(result.get("attempt"), dict)
        and result["attempt"].get("status") in {"success", "pending"}
    ):
        record_recon_activity_notification(
            conn,
            activity_id,
            fingerprint=fingerprint,
            opened_at=None,
        )
    return result


def notify_for_incident(conn, incident_id: int) -> dict[str, Any] | None:
    incident = fetch_incident_notification_context(conn, incident_id)
    if incident is None:
        return None
    policy = get_effective_notification_policy()
    result = _deliver_notification(
        conn,
        event_kind="incident",
        object_id=incident_id,
        subject=incident,
        policy=policy,
        purpose=PURPOSE_INCIDENT_CREATED,
    )
    return result["attempt"]


def send_playbook_notification(
    conn,
    *,
    execution: dict[str, Any],
    message: str | None = None,
    purpose: str | None = None,
    playbook_step_index: int | None = None,
) -> dict[str, Any]:
    alert_id = execution.get("alert_id")
    incident_id = execution.get("incident_id")
    event_kind = "alert" if alert_id is not None else "incident" if incident_id is not None else None
    if event_kind is None:
        attempt = _record_attempt(
            conn,
            correlation_id=_notification_correlation_id("playbook", int(execution.get("id") or 0), "unrouted"),
            idempotency_key=_notification_idempotency_key(
                "playbook",
                int(execution.get("id") or 0),
                "unrouted",
                _normalize_notification_purpose(purpose, default=PURPOSE_INVESTIGATION_UPDATE),
                DELIVERY_STAGE_PLAYBOOK,
            ),
            status="blocked",
            failure_code="missing_notification_subject",
            failure_message="Playbook Slack notification has no linked alert or incident context.",
            metadata={
                "notification_policy": True,
                "event_kind": "playbook",
                "purpose": _normalize_notification_purpose(
                    purpose, default=PURPOSE_INVESTIGATION_UPDATE
                ),
                "delivery_stage": DELIVERY_STAGE_PLAYBOOK,
                "executed": False,
                "simulated": True,
                "playbook_execution_id": execution.get("id"),
                "playbook_step_index": playbook_step_index,
            },
            playbook_execution_id=execution.get("id"),
            playbook_step_index=playbook_step_index,
        )
        return {
            "success": False,
            "suppressed": True,
            "duplicate": False,
            "purpose": _normalize_notification_purpose(
                purpose, default=PURPOSE_INVESTIGATION_UPDATE
            ),
            "delivery_stage": DELIVERY_STAGE_PLAYBOOK,
            "route_key": "unrouted",
            "message": attempt["failure_message"],
            "attempt": attempt,
            "adapter_result": None,
            "policy_decision": {"should_notify": False, "reason": "missing_notification_subject"},
        }

    if event_kind == "alert":
        subject = fetch_alert_notification_context(conn, int(alert_id))
        object_id = int(alert_id)
    else:
        subject = fetch_incident_notification_context(conn, int(incident_id))
        object_id = int(incident_id)
    if subject is None:
        return {
            "success": False,
            "suppressed": True,
            "duplicate": False,
            "purpose": _normalize_notification_purpose(
                purpose, default=PURPOSE_INVESTIGATION_UPDATE
            ),
            "delivery_stage": DELIVERY_STAGE_PLAYBOOK,
            "route_key": "unrouted",
            "message": "Linked notification context was not found.",
            "attempt": None,
            "adapter_result": None,
            "policy_decision": {"should_notify": False, "reason": "missing_notification_subject"},
        }
    subject["playbook_id"] = execution.get("playbook_id")
    policy = get_effective_notification_policy()
    return _deliver_notification(
        conn,
        event_kind=event_kind,
        object_id=object_id,
        subject=subject,
        policy=policy,
        purpose=_normalize_notification_purpose(
            purpose,
            default=PURPOSE_INVESTIGATION_UPDATE,
        ),
        custom_text=message,
        playbook_execution_id=execution.get("id"),
        playbook_step_index=playbook_step_index,
        correlation_kind="playbook",
    )


def send_notification_policy_route_test(
    conn,
    *,
    route_key: str,
    requested_by: str | None = None,
    bypass_slack_disabled: bool = True,
) -> dict[str, Any]:
    source, source_type = _route_test_source(str(route_key or "").strip().lower())
    with conn.cursor() as cur:
        policy = load_notification_policy(cur)

    subject = {
        "id": 0,
        "severity": "critical",
        "source": source,
        "source_type": source_type,
        "message": _format_route_test_text(route_key, "test", str(policy.get("slack_format") or "compact")),
    }
    result = _deliver_notification(
        conn,
        event_kind="alert",
        object_id=0,
        subject=subject,
        policy=policy,
        purpose=PURPOSE_ROUTE_TEST,
        custom_text=f"Notification policy route test for {route_key}",
        requested_by=requested_by,
        bypass_slack_disabled=bypass_slack_disabled,
        allow_dedup=False,
        correlation_kind="route_test",
    )
    attempt = result["attempt"]
    return {
        "route_key": result["route_key"],
        "success": attempt["status"] == "success",
        "status": attempt["status"],
        "message": (
            f"Notification policy route test sent for {result['route_key']}."
            if attempt["status"] == "success"
            else attempt["failure_message"]
        ),
        "attempt": _attempt_summary(attempt),
    }
