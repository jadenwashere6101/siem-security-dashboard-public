"""Shared canonical response command service for block/monitor/escalate."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from core.canonical_action_vocabulary import (
    CanonicalActionValidationError,
    validate_response_command_action,
)
from core.db import create_blocked_ip_record, validate_blocked_ip
from core.indicator_response_registry import (
    append_registry_event,
    get_indicator_by_value,
    upsert_indicator_identity,
)
from core.response_command_contracts import (
    DEFAULT_MONITOR_TTL_HOURS,
    DISPOSITION_BLOCKLIST_TRACKED,
    DISPOSITION_ESCALATED,
    DISPOSITION_MONITORED,
    DISPOSITION_REJECTED,
    DISPOSITION_REMOVED,
    ESCALATION_DEFAULT_PRIORITY,
    ESCALATION_DEFAULT_SEVERITY,
    INDICATOR_TYPE_IP,
    ORIGIN_SYSTEM,
    ResponseCommandRequest,
    ResponseCommandResult,
    build_affected_resource_keys,
)
from core.soar_protected_targets import (
    ProtectedTargetConfigError,
    require_unprotected_target,
)
from core.soar_response_outcomes import (
    append_outcome_event,
    create_response_decision,
)
from engines.soar_errors import SkippedAction


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_expires_at(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _default_idempotency_key(request: ResponseCommandRequest) -> str:
    if request.idempotency_key:
        return request.idempotency_key
    raw = "|".join(
        [
            request.action,
            request.indicator_type,
            str(request.indicator_value or ""),
            str(request.alert_id or ""),
            str(request.origin_surface or ""),
            str(request.queue_id or ""),
            str(request.playbook_execution_id or ""),
            str(request.playbook_step_index or ""),
        ]
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def _resolve_source_ip(conn, request: ResponseCommandRequest) -> str | None:
    if request.indicator_value:
        return _normalize_ip_or_raise(request.indicator_value)
    if request.alert_id is None:
        return None
    cur = conn.cursor()
    cur.execute("SELECT source_ip FROM alerts WHERE id = %s", (request.alert_id,))
    row = cur.fetchone()
    if not row or row[0] is None:
        return None
    return str(row[0])


def _normalize_ip_or_raise(value: str) -> str:
    import ipaddress

    return str(ipaddress.ip_address(str(value).strip()))


def _get_or_create_active_blocked_ip(
    cur,
    *,
    ip_address: str,
    created_by: int | None,
    reason: str | None,
    source_alert_id: int | None,
    expires_at: datetime | None,
) -> tuple[int, bool]:
    """Return (blocked_ip_id, created_new)."""
    normalized = validate_blocked_ip(ip_address)
    cur.execute(
        """
        SELECT id
        FROM blocked_ips
        WHERE ip_address = %s
          AND status = 'active'
          AND (expires_at IS NULL OR expires_at > NOW())
        ORDER BY id ASC
        LIMIT 1
        """,
        (normalized,),
    )
    row = cur.fetchone()
    if row:
        return row[0], False
    block_id = create_blocked_ip_record(
        cur,
        normalized,
        created_by=created_by,
        reason=reason,
        source_alert_id=source_alert_id,
        expires_at=expires_at,
    )
    return block_id, True


def _ensure_escalation_incident(
    conn,
    *,
    alert_id: int | None,
    source_ip: str | None,
    actor_user_id: int | None,
) -> int:
    cur = conn.cursor()
    if alert_id is not None:
        cur.execute(
            """
            SELECT ia.incident_id
            FROM incident_alerts ia
            JOIN incidents i ON i.id = ia.incident_id
            WHERE ia.alert_id = %s
              AND i.status IN ('open', 'investigating')
            ORDER BY ia.linked_at DESC
            LIMIT 1
            """,
            (alert_id,),
        )
        linked = cur.fetchone()
        if linked:
            return linked[0]

    if source_ip:
        cur.execute(
            """
            SELECT id
            FROM incidents
            WHERE source_ip = %s::inet
              AND status IN ('open', 'investigating')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_ip,),
        )
        existing = cur.fetchone()
        if existing:
            incident_id = existing[0]
            if alert_id is not None:
                cur.execute(
                    """
                    INSERT INTO incident_alerts (incident_id, alert_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (incident_id, alert_id),
                )
            return incident_id

    title = f"Escalated alert {alert_id}" if alert_id else f"Escalated IP {source_ip}"
    cur.execute(
        """
        INSERT INTO incidents (title, severity, priority, status, source_ip, assigned_to)
        VALUES (%s, %s, %s, 'open', %s::inet, %s)
        RETURNING id
        """,
        (
            title,
            ESCALATION_DEFAULT_SEVERITY,
            ESCALATION_DEFAULT_PRIORITY,
            source_ip,
            actor_user_id,
        ),
    )
    incident_id = cur.fetchone()[0]
    if alert_id is not None:
        cur.execute(
            """
            INSERT INTO incident_alerts (incident_id, alert_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (incident_id, alert_id),
        )
    return incident_id


def _log_response_action(
    cur,
    *,
    alert_id: int | None,
    source_ip: str | None,
    action: str,
    status: str,
    details: str,
    decision_id: int | None,
    soar_correlation_id: str | None,
) -> int:
    cur.execute(
        """
        INSERT INTO response_actions_log (
            alert_id, source_ip, action, status, details,
            decision_id, soar_correlation_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            alert_id,
            source_ip,
            action,
            status,
            details,
            decision_id,
            soar_correlation_id,
        ),
    )
    return cur.fetchone()[0]


def execute_response_command(conn, request: ResponseCommandRequest) -> ResponseCommandResult:
    """Execute block_ip / monitor / flag_high_priority through one shared path."""
    try:
        action = validate_response_command_action(request.action)
    except CanonicalActionValidationError as error:
        return ResponseCommandResult(
            success=False,
            action=str(request.action or ""),
            outcome_label="rejected",
            message=str(error),
            error=str(error),
            error_code=error.code,
        )

    source_ip = None
    try:
        source_ip = _resolve_source_ip(conn, request)
    except ValueError as error:
        return ResponseCommandResult(
            success=False,
            action=action,
            outcome_label="rejected",
            message=str(error),
            error=str(error),
            error_code="invalid_indicator",
        )

    if action in {"block_ip", "monitor", "stop_monitor", "remove_tracking", "add_note"} and not source_ip:
        return ResponseCommandResult(
            success=False,
            action=action,
            outcome_label="rejected",
            message="source_ip is required",
            error="source_ip is required",
            error_code="validation_no_target",
        )

    if action == "flag_high_priority" and request.alert_id is None and not source_ip:
        return ResponseCommandResult(
            success=False,
            action=action,
            outcome_label="rejected",
            message="alert_id or source_ip is required for escalation",
            error="alert_id or source_ip is required for escalation",
            error_code="validation_no_target",
        )

    if action == "add_note" and not (request.reason or "").strip():
        return ResponseCommandResult(
            success=False,
            action=action,
            outcome_label="rejected",
            message="reason is required for add_note",
            error="reason is required for add_note",
            error_code="validation_missing_reason",
        )

    idem_key = _default_idempotency_key(
        ResponseCommandRequest(
            **{
                **request.to_dict(),
                "action": action,
                "indicator_value": source_ip or request.indicator_value,
            }
        )
    )

    if action == "block_ip":
        return _execute_block_ip(conn, request, action, source_ip, idem_key)
    if action == "monitor":
        return _execute_monitor(conn, request, action, source_ip, idem_key)
    if action == "stop_monitor":
        return _execute_stop_monitor(conn, request, action, source_ip, idem_key)
    if action == "remove_tracking":
        return _execute_remove_tracking(conn, request, action, source_ip, idem_key)
    if action == "add_note":
        return _execute_add_note(conn, request, action, source_ip, idem_key)
    return _execute_escalate(conn, request, action, source_ip, idem_key)


def _execute_block_ip(
    conn,
    request: ResponseCommandRequest,
    action: str,
    source_ip: str,
    idem_key: str,
) -> ResponseCommandResult:
    cur = conn.cursor()
    try:
        require_unprotected_target(source_ip)
        validate_blocked_ip(source_ip)
    except SkippedAction as error:
        return _reject(
            conn,
            request,
            action,
            source_ip,
            idem_key,
            message=str(error),
            error_code=error.code,
        )
    except ProtectedTargetConfigError as error:
        return _reject(
            conn,
            request,
            action,
            source_ip,
            idem_key,
            message=str(error),
            error_code="protected_target_config_invalid",
        )
    except ValueError as error:
        return _reject(
            conn,
            request,
            action,
            source_ip,
            idem_key,
            message=str(error),
            error_code="invalid_indicator",
        )

    expires_at = _parse_expires_at(request.expires_at)
    registry = upsert_indicator_identity(
        conn, indicator_type=INDICATOR_TYPE_IP, indicator_value=source_ip
    )
    block_id, created_new = _get_or_create_active_blocked_ip(
        cur,
        ip_address=source_ip,
        created_by=request.actor_user_id,
        reason=request.reason or "Canonical block_ip tracking",
        source_alert_id=request.alert_id,
        expires_at=expires_at,
    )

    decision = create_response_decision(
        conn,
        alert_id=request.alert_id,
        incident_id=request.incident_id,
        source_ip=source_ip,
        selected_action=action,
        decision_source="manual" if request.origin_surface != "playbook" else "playbook",
        reason_code="tracking_only",
        outcome_summary=(
            "SIEM blocklist tracking recorded; no firewall or host enforcement occurred."
        ),
        playbook_execution_id=request.playbook_execution_id,
        playbook_step_index=request.playbook_step_index,
        queue_id=request.queue_id,
        approval_request_id=request.approval_request_id,
        created_by=request.actor_user_id,
        safe_metadata={
            "origin_surface": request.origin_surface,
            "idempotent": not created_new,
            **(request.safe_metadata or {}),
        },
    )
    log_id = _log_response_action(
        cur,
        alert_id=request.alert_id,
        source_ip=source_ip,
        action=action,
        status="executed",
        details=(
            "Recorded in SIEM blocklist (tracking only)"
            if created_new
            else "Reused active SIEM blocklist tracking record"
        ),
        decision_id=decision["id"],
        soar_correlation_id=decision["soar_correlation_id"],
    )
    append_outcome_event(
        conn,
        decision_id=decision["id"],
        soar_correlation_id=decision["soar_correlation_id"],
        event_type="succeeded",
        execution_mode="tracking_only",
        execution_state="succeeded",
        external_executed=False,
        tracking_recorded=True,
        simulated=False,
        execution_actor="manual" if request.actor_user_id else "system",
        reason_code="tracking_only" if created_new else "duplicate_suppressed",
        outcome_summary=(
            "SIEM blocklist tracking was recorded for this IP; no firewall enforcement occurred."
            if created_new
            else "Active blocklist tracking already existed; provenance appended."
        ),
        alert_id=request.alert_id,
        source_ip=source_ip,
        response_action_log_id=log_id,
        queue_id=request.queue_id,
        playbook_execution_id=request.playbook_execution_id,
        approval_request_id=request.approval_request_id,
        idempotency_key=f"outcome-{idem_key}",
        metadata={"blocked_ip_id": block_id, "created_new": created_new},
    )
    event = append_registry_event(
        conn,
        registry_id=registry["id"],
        event_type="block_ip_tracking",
        requested_action=action,
        outcome="succeeded" if created_new else "idempotent_reuse",
        disposition_after=DISPOSITION_BLOCKLIST_TRACKED,
        enforcement="tracking_only",
        origin_surface=request.origin_surface or ORIGIN_SYSTEM,
        actor_user_id=request.actor_user_id,
        reason=request.reason,
        alert_id=request.alert_id,
        incident_id=request.incident_id,
        playbook_execution_id=request.playbook_execution_id,
        playbook_step_index=request.playbook_step_index,
        queue_id=request.queue_id,
        approval_request_id=request.approval_request_id,
        blocked_ip_id=block_id,
        decision_id=decision["id"],
        soar_correlation_id=decision["soar_correlation_id"],
        response_action_log_id=log_id,
        idempotency_key=idem_key,
        expires_at=expires_at,
        safe_metadata={"created_new": created_new},
    )

    if request.alert_id is not None:
        cur.execute(
            """
            UPDATE alerts
            SET response_action = %s, response_status = 'executed'
            WHERE id = %s
            """,
            (action, request.alert_id),
        )

    return ResponseCommandResult(
        success=True,
        action=action,
        outcome_label="tracking_recorded" if created_new else "idempotent_reuse",
        idempotent=not created_new,
        enforcement="none",
        registry_record_id=registry["id"],
        registry_event_id=event["id"],
        blocked_ip_id=block_id,
        decision_id=decision["id"],
        soar_correlation_id=decision["soar_correlation_id"],
        response_action_log_id=log_id,
        disposition=DISPOSITION_BLOCKLIST_TRACKED,
        message=(
            "Blocked IP tracking recorded (no firewall enforcement)."
            if created_new
            else "Active blocklist tracking reused; provenance recorded."
        ),
        affected_resource_keys=build_affected_resource_keys(
            alert_id=request.alert_id,
            source_ip=source_ip,
            blocked_ip_id=block_id,
            registry_record_id=registry["id"],
            queue_id=request.queue_id,
            playbook_execution_id=request.playbook_execution_id,
        ),
        compatible_fields={
            "id": block_id,
            "message": "Blocked IP added successfully"
            if created_new
            else "Active block already exists for this IP",
            "response_status": "executed",
            "alert_id": request.alert_id,
        },
    )


def _execute_monitor(
    conn,
    request: ResponseCommandRequest,
    action: str,
    source_ip: str,
    idem_key: str,
) -> ResponseCommandResult:
    cur = conn.cursor()
    expires_at = _parse_expires_at(request.expires_at)
    if expires_at is None:
        expires_at = _now() + timedelta(hours=DEFAULT_MONITOR_TTL_HOURS)

    registry = upsert_indicator_identity(
        conn, indicator_type=INDICATOR_TYPE_IP, indicator_value=source_ip
    )
    decision = create_response_decision(
        conn,
        alert_id=request.alert_id,
        incident_id=request.incident_id,
        source_ip=source_ip,
        selected_action=action,
        decision_source="manual",
        reason_code=None,
        outcome_summary="Durable monitor/watch disposition recorded.",
        playbook_execution_id=request.playbook_execution_id,
        queue_id=request.queue_id,
        created_by=request.actor_user_id,
        safe_metadata={"origin_surface": request.origin_surface},
    )
    log_id = _log_response_action(
        cur,
        alert_id=request.alert_id,
        source_ip=source_ip,
        action=action,
        status="executed",
        details="Monitoring disposition recorded",
        decision_id=decision["id"],
        soar_correlation_id=decision["soar_correlation_id"],
    )
    append_outcome_event(
        conn,
        decision_id=decision["id"],
        soar_correlation_id=decision["soar_correlation_id"],
        event_type="succeeded",
        execution_mode="simulation",
        execution_state="succeeded",
        external_executed=False,
        tracking_recorded=False,
        simulated=False,
        execution_actor="manual" if request.actor_user_id else "system",
        reason_code=None,
        outcome_summary="Monitor/watch disposition is active in the response registry.",
        alert_id=request.alert_id,
        source_ip=source_ip,
        response_action_log_id=log_id,
        idempotency_key=f"outcome-{idem_key}",
    )
    event = append_registry_event(
        conn,
        registry_id=registry["id"],
        event_type="monitor_started",
        requested_action=action,
        outcome="succeeded",
        disposition_after=DISPOSITION_MONITORED,
        enforcement="none",
        origin_surface=request.origin_surface or ORIGIN_SYSTEM,
        actor_user_id=request.actor_user_id,
        reason=request.reason or "Monitor selected",
        alert_id=request.alert_id,
        incident_id=request.incident_id,
        playbook_execution_id=request.playbook_execution_id,
        queue_id=request.queue_id,
        decision_id=decision["id"],
        soar_correlation_id=decision["soar_correlation_id"],
        response_action_log_id=log_id,
        idempotency_key=idem_key,
        expires_at=expires_at,
    )
    if request.alert_id is not None:
        cur.execute(
            """
            UPDATE alerts
            SET response_action = %s, response_status = 'executed'
            WHERE id = %s
            """,
            (action, request.alert_id),
        )
    return ResponseCommandResult(
        success=True,
        action=action,
        outcome_label="monitored",
        enforcement="none",
        registry_record_id=registry["id"],
        registry_event_id=event["id"],
        decision_id=decision["id"],
        soar_correlation_id=decision["soar_correlation_id"],
        response_action_log_id=log_id,
        disposition=DISPOSITION_MONITORED,
        message="Monitoring disposition recorded.",
        affected_resource_keys=build_affected_resource_keys(
            alert_id=request.alert_id,
            source_ip=source_ip,
            registry_record_id=registry["id"],
        ),
        compatible_fields={
            "response_status": "executed",
            "alert_id": request.alert_id,
            "action": action,
        },
    )


def _execute_escalate(
    conn,
    request: ResponseCommandRequest,
    action: str,
    source_ip: str | None,
    idem_key: str,
) -> ResponseCommandResult:
    cur = conn.cursor()
    incident_id = _ensure_escalation_incident(
        conn,
        alert_id=request.alert_id,
        source_ip=source_ip,
        actor_user_id=request.actor_user_id,
    )
    registry = None
    if source_ip:
        registry = upsert_indicator_identity(
            conn, indicator_type=INDICATOR_TYPE_IP, indicator_value=source_ip
        )

    decision = create_response_decision(
        conn,
        alert_id=request.alert_id,
        incident_id=incident_id,
        source_ip=source_ip,
        selected_action=action,
        decision_source="manual",
        reason_code=None,
        outcome_summary="Internal escalation recorded via incident handoff.",
        playbook_execution_id=request.playbook_execution_id,
        queue_id=request.queue_id,
        created_by=request.actor_user_id,
        safe_metadata={"origin_surface": request.origin_surface},
    )
    log_id = _log_response_action(
        cur,
        alert_id=request.alert_id,
        source_ip=source_ip,
        action=action,
        status="executed",
        details=f"Escalated to incident {incident_id}",
        decision_id=decision["id"],
        soar_correlation_id=decision["soar_correlation_id"],
    )
    append_outcome_event(
        conn,
        decision_id=decision["id"],
        soar_correlation_id=decision["soar_correlation_id"],
        event_type="succeeded",
        execution_mode="simulation",
        execution_state="succeeded",
        external_executed=False,
        tracking_recorded=False,
        simulated=False,
        execution_actor="manual" if request.actor_user_id else "system",
        reason_code=None,
        outcome_summary=f"Escalation created/linked incident {incident_id}.",
        alert_id=request.alert_id,
        incident_id=incident_id,
        source_ip=source_ip,
        response_action_log_id=log_id,
        idempotency_key=f"outcome-{idem_key}",
        metadata={"incident_id": incident_id},
    )
    event_id = None
    registry_id = None
    if registry:
        event = append_registry_event(
            conn,
            registry_id=registry["id"],
            event_type="escalated",
            requested_action=action,
            outcome="escalated",
            disposition_after=DISPOSITION_ESCALATED,
            enforcement="none",
            origin_surface=request.origin_surface or ORIGIN_SYSTEM,
            actor_user_id=request.actor_user_id,
            reason=request.reason or "Escalation selected",
            alert_id=request.alert_id,
            incident_id=incident_id,
            playbook_execution_id=request.playbook_execution_id,
            queue_id=request.queue_id,
            decision_id=decision["id"],
            soar_correlation_id=decision["soar_correlation_id"],
            response_action_log_id=log_id,
            idempotency_key=idem_key,
        )
        event_id = event["id"]
        registry_id = registry["id"]

    if request.alert_id is not None:
        cur.execute(
            """
            UPDATE alerts
            SET response_action = %s, response_status = 'executed'
            WHERE id = %s
            """,
            (action, request.alert_id),
        )

    return ResponseCommandResult(
        success=True,
        action=action,
        outcome_label="escalated",
        enforcement="none",
        registry_record_id=registry_id,
        registry_event_id=event_id,
        incident_id=incident_id,
        decision_id=decision["id"],
        soar_correlation_id=decision["soar_correlation_id"],
        response_action_log_id=log_id,
        disposition=DISPOSITION_ESCALATED if registry_id else None,
        message=f"Escalation recorded; incident {incident_id}.",
        affected_resource_keys=build_affected_resource_keys(
            alert_id=request.alert_id,
            incident_id=incident_id,
            source_ip=source_ip,
            registry_record_id=registry_id,
        ),
        compatible_fields={
            "response_status": "executed",
            "alert_id": request.alert_id,
            "action": action,
            "incident_id": incident_id,
        },
    )


def _execute_stop_monitor(
    conn,
    request: ResponseCommandRequest,
    action: str,
    source_ip: str,
    idem_key: str,
) -> ResponseCommandResult:
    registry = get_indicator_by_value(
        conn, indicator_type=INDICATOR_TYPE_IP, indicator_value=source_ip
    )
    if registry is None:
        registry = upsert_indicator_identity(
            conn, indicator_type=INDICATOR_TYPE_IP, indicator_value=source_ip
        )
    if registry.get("current_disposition") != DISPOSITION_MONITORED:
        # Idempotent: already not monitored
        if registry.get("current_disposition") == DISPOSITION_REMOVED:
            return ResponseCommandResult(
                success=True,
                action=action,
                outcome_label="removed",
                idempotent=True,
                enforcement="none",
                registry_record_id=registry["id"],
                disposition=DISPOSITION_REMOVED,
                message="Monitoring is already stopped for this indicator.",
                affected_resource_keys=build_affected_resource_keys(
                    source_ip=source_ip,
                    registry_record_id=registry["id"],
                    alert_id=request.alert_id,
                ),
            )

    event = append_registry_event(
        conn,
        registry_id=registry["id"],
        event_type="monitor_stopped",
        requested_action=action,
        outcome="removed",
        disposition_after=DISPOSITION_REMOVED,
        enforcement="none",
        origin_surface=request.origin_surface or ORIGIN_SYSTEM,
        actor_user_id=request.actor_user_id,
        reason=request.reason or "Monitoring stopped",
        alert_id=request.alert_id,
        incident_id=request.incident_id,
        idempotency_key=idem_key,
    )
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE indicator_registry
        SET monitor_expires_at = NULL,
            updated_at = NOW()
        WHERE id = %s
        """,
        (registry["id"],),
    )
    return ResponseCommandResult(
        success=True,
        action=action,
        outcome_label="removed",
        enforcement="none",
        registry_record_id=registry["id"],
        registry_event_id=event["id"],
        disposition=DISPOSITION_REMOVED,
        message="Monitoring stopped. No firewall or host enforcement changed.",
        affected_resource_keys=build_affected_resource_keys(
            source_ip=source_ip,
            registry_record_id=registry["id"],
            alert_id=request.alert_id,
        ),
    )


def _execute_remove_tracking(
    conn,
    request: ResponseCommandRequest,
    action: str,
    source_ip: str,
    idem_key: str,
) -> ResponseCommandResult:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, status
        FROM blocked_ips
        WHERE ip_address = %s::inet AND status = 'active'
        ORDER BY id DESC
        LIMIT 1
        """,
        (source_ip,),
    )
    row = cur.fetchone()
    registry = upsert_indicator_identity(
        conn, indicator_type=INDICATOR_TYPE_IP, indicator_value=source_ip
    )
    if row is None:
        return ResponseCommandResult(
            success=True,
            action=action,
            outcome_label="removed",
            idempotent=True,
            enforcement="none",
            registry_record_id=registry["id"],
            disposition=registry.get("current_disposition"),
            message="No active Blocklist tracking exists for this IP.",
            affected_resource_keys=build_affected_resource_keys(
                source_ip=source_ip,
                registry_record_id=registry["id"],
            ),
        )

    block_id = row[0]
    cur.execute(
        """
        UPDATE blocked_ips
        SET status = 'inactive'
        WHERE id = %s AND status = 'active'
        """,
        (block_id,),
    )
    event = append_registry_event(
        conn,
        registry_id=registry["id"],
        event_type="tracking_removed",
        requested_action=action,
        outcome="removed",
        disposition_after=DISPOSITION_REMOVED,
        enforcement="none",
        origin_surface=request.origin_surface or ORIGIN_SYSTEM,
        actor_user_id=request.actor_user_id,
        reason=request.reason or "Blocklist tracking removed",
        alert_id=request.alert_id,
        blocked_ip_id=block_id,
        idempotency_key=idem_key,
    )
    cur.execute(
        """
        UPDATE indicator_registry
        SET active_blocked_ip_id = NULL,
            updated_at = NOW()
        WHERE id = %s
        """,
        (registry["id"],),
    )
    return ResponseCommandResult(
        success=True,
        action=action,
        outcome_label="removed",
        enforcement="none",
        registry_record_id=registry["id"],
        registry_event_id=event["id"],
        blocked_ip_id=block_id,
        disposition=DISPOSITION_REMOVED,
        message=(
            "Blocklist tracking removed. Tracking only; no firewall or host "
            "enforcement changed."
        ),
        affected_resource_keys=build_affected_resource_keys(
            source_ip=source_ip,
            blocked_ip_id=block_id,
            registry_record_id=registry["id"],
            alert_id=request.alert_id,
        ),
        compatible_fields={
            "message": (
                "SIEM Blocklist tracking removed. History remains; "
                "no firewall or host enforcement changed."
            ),
            "id": block_id,
        },
    )


def _execute_add_note(
    conn,
    request: ResponseCommandRequest,
    action: str,
    source_ip: str,
    idem_key: str,
) -> ResponseCommandResult:
    registry = upsert_indicator_identity(
        conn, indicator_type=INDICATOR_TYPE_IP, indicator_value=source_ip
    )
    note = (request.reason or "").strip()
    event = append_registry_event(
        conn,
        registry_id=registry["id"],
        event_type="note",
        requested_action=action,
        outcome="recorded",
        disposition_after=registry.get("current_disposition") or "observed",
        enforcement="none",
        origin_surface=request.origin_surface or ORIGIN_SYSTEM,
        actor_user_id=request.actor_user_id,
        reason=note,
        alert_id=request.alert_id,
        incident_id=request.incident_id,
        idempotency_key=idem_key,
        update_registry=False,
    )
    cur = conn.cursor()
    cur.execute(
        "UPDATE indicator_registry SET updated_at = NOW() WHERE id = %s",
        (registry["id"],),
    )
    return ResponseCommandResult(
        success=True,
        action=action,
        outcome_label="recorded",
        enforcement="none",
        registry_record_id=registry["id"],
        registry_event_id=event["id"],
        disposition=registry.get("current_disposition"),
        message="Note recorded in response history.",
        affected_resource_keys=build_affected_resource_keys(
            source_ip=source_ip,
            registry_record_id=registry["id"],
            alert_id=request.alert_id,
        ),
    )


def _reject(
    conn,
    request: ResponseCommandRequest,
    action: str,
    source_ip: str | None,
    idem_key: str,
    *,
    message: str,
    error_code: str,
) -> ResponseCommandResult:
    registry_id = None
    event_id = None
    if source_ip:
        try:
            registry = upsert_indicator_identity(
                conn, indicator_type=INDICATOR_TYPE_IP, indicator_value=source_ip
            )
            event = append_registry_event(
                conn,
                registry_id=registry["id"],
                event_type="rejected",
                requested_action=action,
                outcome="rejected",
                disposition_after=DISPOSITION_REJECTED,
                enforcement="none",
                origin_surface=request.origin_surface or ORIGIN_SYSTEM,
                actor_user_id=request.actor_user_id,
                reason=message,
                alert_id=request.alert_id,
                idempotency_key=f"reject-{idem_key}",
                safe_metadata={"error_code": error_code},
            )
            registry_id = registry["id"]
            event_id = event["id"]
        except Exception:
            pass
    return ResponseCommandResult(
        success=False,
        action=action,
        outcome_label="rejected",
        registry_record_id=registry_id,
        registry_event_id=event_id,
        disposition=DISPOSITION_REJECTED if registry_id else None,
        message=message,
        error=message,
        error_code=error_code,
        affected_resource_keys=build_affected_resource_keys(
            alert_id=request.alert_id,
            source_ip=source_ip,
            registry_record_id=registry_id,
        ),
    )
