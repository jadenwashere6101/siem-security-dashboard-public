from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from core import notification_delivery_store
from core.notification_policy_store import get_effective_notification_policy
from integrations.base_integration import REAL_MODE
from integrations.integration_registry import get_integration_adapter

SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}

ROUTE_KEY_PFSENSE = "pfsense"
ROUTE_KEY_HONEYPOT = "honeypot"


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
        return policy.get("pfsense_destination")
    if route_key == ROUTE_KEY_HONEYPOT:
        return policy.get("honeypot_destination")
    return None


def _delivery_status_from_adapter_result(adapter_result: dict[str, Any]) -> str:
    if adapter_result.get("success") is True:
        return "success"
    metadata = adapter_result.get("metadata") if isinstance(adapter_result.get("metadata"), dict) else {}
    classification = str(metadata.get("failure_classification") or "").strip().lower()
    if classification == "timeout" or metadata.get("timed_out") is True:
        return "timeout"
    return "blocked" if adapter_result.get("executed") is not True else "failed"


def evaluate_notification_policy(
    policy: dict[str, Any],
    *,
    event_kind: str,
    severity: Any,
    source: Any,
    source_type: Any = None,
) -> dict[str, Any]:
    if policy.get("status") == "unavailable":
        return {"should_notify": False, "reason": "policy_unavailable", "route_key": None, "destination": None}

    normalized_kind = str(event_kind or "").strip().lower()
    if normalized_kind == "alert" and not policy.get("notify_on_alerts", True):
        return {"should_notify": False, "reason": "alerts_disabled", "route_key": None, "destination": None}
    if normalized_kind == "incident" and not policy.get("notify_on_incidents", True):
        return {"should_notify": False, "reason": "incidents_disabled", "route_key": None, "destination": None}
    if not policy.get("slack_enabled", False):
        return {"should_notify": False, "reason": "slack_disabled", "route_key": None, "destination": None}

    normalized_severity = str(severity or "").strip().lower()
    threshold = str(policy.get("minimum_severity") or "high").strip().lower()
    if normalized_severity not in SEVERITY_RANK or threshold not in SEVERITY_RANK:
        return {"should_notify": False, "reason": "invalid_severity", "route_key": None, "destination": None}
    if SEVERITY_RANK[normalized_severity] < SEVERITY_RANK[threshold]:
        return {"should_notify": False, "reason": "below_minimum_severity", "route_key": None, "destination": None}

    route_key = normalize_notification_source(source, source_type)
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


def _notification_correlation_id(kind: str, object_id: int, route_key: str) -> str:
    return f"policy-{kind}-{route_key}-{object_id}-{uuid4().hex[:10]}"


def _notification_idempotency_key(kind: str, object_id: int, route_key: str, slack_format: str) -> str:
    raw = f"policy:{kind}:{object_id}:{route_key}:{slack_format}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


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
    timeout_seconds: int | None = None,
    circuit_breaker_state: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        provider="slack",
        mode="real" if status in {"success", "failed", "timeout"} else "simulation",
        status=status,
        adapter_name="slack",
        action="send_message",
        alert_id=alert_id,
        incident_id=incident_id,
        requested_at=now,
        started_at=now,
        completed_at=now,
        failure_code=failure_code,
        failure_message=failure_message,
        timeout_seconds=timeout_seconds,
        circuit_breaker_state=circuit_breaker_state,
        metadata=metadata,
    )


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
                response_status
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
    policy = get_effective_notification_policy()
    decision = evaluate_notification_policy(
        policy,
        event_kind="alert",
        severity=alert.get("severity"),
        source=alert.get("source"),
        source_type=alert.get("source_type"),
    )
    route_key = decision.get("route_key") or "unrouted"
    correlation_id = _notification_correlation_id("alert", alert_id, route_key)
    idempotency_key = _notification_idempotency_key(
        "alert",
        alert_id,
        route_key,
        str(policy.get("slack_format") or "compact"),
    )
    if not decision["should_notify"]:
        return _record_attempt(
            conn,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            status="blocked",
            failure_code=decision["reason"],
            failure_message=f"Notification policy suppressed Slack delivery: {decision['reason']}.",
            metadata={
                "notification_policy": True,
                "event_kind": "alert",
                "policy_status": policy.get("status"),
                "policy_reason": decision["reason"],
                "source": alert.get("source"),
                "source_type": alert.get("source_type"),
                "severity": alert.get("severity"),
                "executed": False,
                "simulated": True,
            },
            alert_id=alert_id,
        )

    text = format_alert_notification(
        alert,
        slack_format=decision["slack_format"],
        destination=decision["destination"],
    )
    adapter = get_integration_adapter("slack", mode=REAL_MODE)
    result = adapter.execute(
        "send_message",
        params={
            "text": text,
            "message": alert.get("message"),
            "destination_label": decision["destination"],
        },
        context={
            "alert_id": alert_id,
            "playbook_id": "notification_policy",
            "execution_id": correlation_id,
            "notification_policy": True,
            "route_key": decision["route_key"],
        },
    )
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    return _record_attempt(
        conn,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        status=_delivery_status_from_adapter_result(result),
        failure_code=metadata.get("failure_classification"),
        failure_message=None if result.get("success") else result.get("message"),
        metadata={
            "notification_policy": True,
            "event_kind": "alert",
            "route_key": decision["route_key"],
            "destination_label": decision["destination"],
            "slack_format": decision["slack_format"],
            "source": alert.get("source"),
            "source_type": alert.get("source_type"),
            "severity": alert.get("severity"),
            "executed": result.get("executed"),
            "simulated": result.get("simulated"),
            "adapter_result": {
                "success": result.get("success"),
                "failure_classification": metadata.get("failure_classification"),
            },
        },
        alert_id=alert_id,
        timeout_seconds=metadata.get("timeout_seconds"),
        circuit_breaker_state=metadata.get("circuit_state"),
    )


def notify_for_incident(conn, incident_id: int) -> dict[str, Any] | None:
    incident = fetch_incident_notification_context(conn, incident_id)
    if incident is None:
        return None
    policy = get_effective_notification_policy()
    decision = evaluate_notification_policy(
        policy,
        event_kind="incident",
        severity=incident.get("severity"),
        source=incident.get("source"),
        source_type=incident.get("source_type"),
    )
    route_key = decision.get("route_key") or "unrouted"
    correlation_id = _notification_correlation_id("incident", incident_id, route_key)
    idempotency_key = _notification_idempotency_key(
        "incident",
        incident_id,
        route_key,
        str(policy.get("slack_format") or "compact"),
    )
    if not decision["should_notify"]:
        return _record_attempt(
            conn,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            status="blocked",
            failure_code=decision["reason"],
            failure_message=f"Notification policy suppressed Slack delivery: {decision['reason']}.",
            metadata={
                "notification_policy": True,
                "event_kind": "incident",
                "policy_status": policy.get("status"),
                "policy_reason": decision["reason"],
                "source": incident.get("source"),
                "source_type": incident.get("source_type"),
                "severity": incident.get("severity"),
                "executed": False,
                "simulated": True,
            },
            incident_id=incident_id,
        )

    text = format_incident_notification(
        incident,
        slack_format=decision["slack_format"],
        destination=decision["destination"],
    )
    adapter = get_integration_adapter("slack", mode=REAL_MODE)
    result = adapter.execute(
        "send_message",
        params={
            "text": text,
            "message": incident.get("title"),
            "destination_label": decision["destination"],
        },
        context={
            "incident_id": incident_id,
            "playbook_id": "notification_policy",
            "execution_id": correlation_id,
            "notification_policy": True,
            "route_key": decision["route_key"],
        },
    )
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    return _record_attempt(
        conn,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        status=_delivery_status_from_adapter_result(result),
        failure_code=metadata.get("failure_classification"),
        failure_message=None if result.get("success") else result.get("message"),
        metadata={
            "notification_policy": True,
            "event_kind": "incident",
            "route_key": decision["route_key"],
            "destination_label": decision["destination"],
            "slack_format": decision["slack_format"],
            "source": incident.get("source"),
            "source_type": incident.get("source_type"),
            "severity": incident.get("severity"),
            "executed": result.get("executed"),
            "simulated": result.get("simulated"),
            "adapter_result": {
                "success": result.get("success"),
                "failure_classification": metadata.get("failure_classification"),
            },
        },
        incident_id=incident_id,
        timeout_seconds=metadata.get("timeout_seconds"),
        circuit_breaker_state=metadata.get("circuit_state"),
    )
