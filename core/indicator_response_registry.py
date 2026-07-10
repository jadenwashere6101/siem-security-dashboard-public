"""Persistence for the canonical indicator response registry."""

from __future__ import annotations

import ipaddress
from datetime import datetime, timezone
from typing import Any

from core.response_command_contracts import (
    DISPOSITION_BLOCKLIST_TRACKED,
    DISPOSITION_ESCALATED,
    DISPOSITION_EXPIRED,
    DISPOSITION_FAILED,
    DISPOSITION_MONITORED,
    DISPOSITION_OBSERVED,
    DISPOSITION_PENDING,
    DISPOSITION_REJECTED,
    DISPOSITION_REMOVED,
    INDICATOR_TYPE_IP,
)


VALID_DISPOSITIONS = frozenset(
    {
        DISPOSITION_OBSERVED,
        DISPOSITION_MONITORED,
        DISPOSITION_ESCALATED,
        DISPOSITION_PENDING,
        DISPOSITION_BLOCKLIST_TRACKED,
        DISPOSITION_REJECTED,
        DISPOSITION_FAILED,
        DISPOSITION_EXPIRED,
        DISPOSITION_REMOVED,
    }
)

_REGISTRY_COLUMNS = (
    "id, indicator_type, indicator_value, current_disposition, "
    "active_blocked_ip_id, active_incident_id, monitor_expires_at, "
    "created_at, updated_at"
)

_EVENT_COLUMNS = (
    "id, registry_id, event_type, requested_action, outcome, disposition_after, "
    "enforcement, origin_surface, actor_user_id, reason, alert_id, incident_id, "
    "playbook_execution_id, playbook_step_index, queue_id, approval_request_id, "
    "blocked_ip_id, decision_id, soar_correlation_id, response_action_log_id, "
    "idempotency_key, provenance, expires_at, safe_metadata, created_at"
)


def normalize_indicator_value(indicator_type: str, value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Indicator value is required")
    if indicator_type == INDICATOR_TYPE_IP:
        return str(ipaddress.ip_address(raw))
    return raw.lower()


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _registry_row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "indicator_type": row[1],
        "indicator_value": row[2],
        "current_disposition": row[3],
        "active_blocked_ip_id": row[4],
        "active_incident_id": row[5],
        "monitor_expires_at": _iso(row[6]),
        "created_at": _iso(row[7]),
        "updated_at": _iso(row[8]),
    }


def _event_row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "registry_id": row[1],
        "event_type": row[2],
        "requested_action": row[3],
        "outcome": row[4],
        "disposition_after": row[5],
        "enforcement": row[6],
        "origin_surface": row[7],
        "actor_user_id": row[8],
        "reason": row[9],
        "alert_id": row[10],
        "incident_id": row[11],
        "playbook_execution_id": row[12],
        "playbook_step_index": row[13],
        "queue_id": row[14],
        "approval_request_id": row[15],
        "blocked_ip_id": row[16],
        "decision_id": row[17],
        "soar_correlation_id": row[18],
        "response_action_log_id": row[19],
        "idempotency_key": row[20],
        "provenance": row[21],
        "expires_at": _iso(row[22]),
        "safe_metadata": row[23] or {},
        "created_at": _iso(row[24]),
    }


def upsert_indicator_identity(
    conn,
    *,
    indicator_type: str,
    indicator_value: str,
) -> dict[str, Any]:
    normalized = normalize_indicator_value(indicator_type, indicator_value)
    cur = conn.cursor()
    cur.execute(
        f"""
        INSERT INTO indicator_registry (indicator_type, indicator_value)
        VALUES (%s, %s)
        ON CONFLICT (indicator_type, indicator_value) DO UPDATE
            SET updated_at = NOW()
        RETURNING {_REGISTRY_COLUMNS}
        """,
        (indicator_type, normalized),
    )
    row = cur.fetchone()
    return _registry_row_to_dict(row)


def get_indicator_by_id(conn, registry_id: int) -> dict[str, Any] | None:
    cur = conn.cursor()
    cur.execute(
        f"SELECT {_REGISTRY_COLUMNS} FROM indicator_registry WHERE id = %s",
        (registry_id,),
    )
    row = cur.fetchone()
    return _registry_row_to_dict(row) if row else None


def get_indicator_by_value(
    conn, *, indicator_type: str, indicator_value: str
) -> dict[str, Any] | None:
    normalized = normalize_indicator_value(indicator_type, indicator_value)
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT {_REGISTRY_COLUMNS}
        FROM indicator_registry
        WHERE indicator_type = %s AND indicator_value = %s
        """,
        (indicator_type, normalized),
    )
    row = cur.fetchone()
    return _registry_row_to_dict(row) if row else None


def derive_disposition_from_event(
    *,
    requested_action: str,
    outcome: str,
    previous: str | None = None,
) -> str:
    if outcome in {"rejected", "policy_blocked"}:
        return DISPOSITION_REJECTED
    if outcome in {"failed", "error"}:
        return DISPOSITION_FAILED
    if outcome in {"awaiting_approval", "pending"}:
        return DISPOSITION_PENDING
    if outcome in {"expired"}:
        return DISPOSITION_EXPIRED
    if outcome in {"removed", "unblocked"}:
        return DISPOSITION_REMOVED
    if requested_action == "block_ip" and outcome in {
        "succeeded",
        "tracking_recorded",
        "idempotent_reuse",
    }:
        return DISPOSITION_BLOCKLIST_TRACKED
    if requested_action == "monitor" and outcome in {"succeeded", "renewed"}:
        return DISPOSITION_MONITORED
    if requested_action in {"flag_high_priority", "escalate"} and outcome in {
        "succeeded",
        "escalated",
    }:
        return DISPOSITION_ESCALATED
    return previous if previous in VALID_DISPOSITIONS else DISPOSITION_OBSERVED


def append_registry_event(
    conn,
    *,
    registry_id: int,
    event_type: str,
    requested_action: str,
    outcome: str,
    origin_surface: str,
    disposition_after: str | None = None,
    enforcement: str = "none",
    actor_user_id: int | None = None,
    reason: str | None = None,
    alert_id: int | None = None,
    incident_id: int | None = None,
    playbook_execution_id: int | None = None,
    playbook_step_index: int | None = None,
    queue_id: int | None = None,
    approval_request_id: int | None = None,
    blocked_ip_id: int | None = None,
    decision_id: int | None = None,
    soar_correlation_id: str | None = None,
    response_action_log_id: int | None = None,
    idempotency_key: str | None = None,
    provenance: str = "recorded",
    expires_at: datetime | None = None,
    safe_metadata: dict[str, Any] | None = None,
    update_registry: bool = True,
) -> dict[str, Any]:
    if idempotency_key:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT {_EVENT_COLUMNS}
            FROM indicator_response_events
            WHERE idempotency_key = %s
            """,
            (idempotency_key,),
        )
        existing = cur.fetchone()
        if existing:
            return _event_row_to_dict(existing)

    record = get_indicator_by_id(conn, registry_id)
    if record is None:
        raise ValueError(f"Registry record {registry_id} not found")

    disposition = disposition_after or derive_disposition_from_event(
        requested_action=requested_action,
        outcome=outcome,
        previous=record.get("current_disposition"),
    )
    if disposition not in VALID_DISPOSITIONS:
        raise ValueError(f"Invalid disposition {disposition!r}")

    import json

    cur = conn.cursor()
    cur.execute(
        f"""
        INSERT INTO indicator_response_events (
            registry_id, event_type, requested_action, outcome, disposition_after,
            enforcement, origin_surface, actor_user_id, reason, alert_id, incident_id,
            playbook_execution_id, playbook_step_index, queue_id, approval_request_id,
            blocked_ip_id, decision_id, soar_correlation_id, response_action_log_id,
            idempotency_key, provenance, expires_at, safe_metadata
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s::jsonb
        )
        RETURNING {_EVENT_COLUMNS}
        """,
        (
            registry_id,
            event_type,
            requested_action,
            outcome,
            disposition,
            enforcement,
            origin_surface,
            actor_user_id,
            reason,
            alert_id,
            incident_id,
            playbook_execution_id,
            playbook_step_index,
            queue_id,
            approval_request_id,
            blocked_ip_id,
            decision_id,
            soar_correlation_id,
            response_action_log_id,
            idempotency_key,
            provenance,
            expires_at,
            json.dumps(safe_metadata or {}),
        ),
    )
    event = _event_row_to_dict(cur.fetchone())

    if update_registry:
        cur.execute(
            """
            UPDATE indicator_registry
            SET current_disposition = %s,
                active_blocked_ip_id = COALESCE(%s, active_blocked_ip_id),
                active_incident_id = COALESCE(%s, active_incident_id),
                monitor_expires_at = CASE
                    WHEN %s::timestamptz IS NOT NULL THEN %s::timestamptz
                    WHEN %s = 'monitored' THEN monitor_expires_at
                    ELSE monitor_expires_at
                END,
                updated_at = NOW()
            WHERE id = %s
            """,
            (
                disposition,
                blocked_ip_id,
                incident_id,
                expires_at,
                expires_at,
                disposition,
                registry_id,
            ),
        )
    return event


def list_registry_records(
    conn,
    *,
    disposition: str | None = None,
    indicator_type: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    clauses = ["TRUE"]
    params: list[Any] = []
    if disposition:
        clauses.append("current_disposition = %s")
        params.append(disposition)
    if indicator_type:
        clauses.append("indicator_type = %s")
        params.append(indicator_type)
    if q:
        clauses.append("indicator_value ILIKE %s")
        params.append(f"%{q.strip()}%")
    where = " AND ".join(clauses)
    cur = conn.cursor()
    cur.execute(
        f"SELECT COUNT(*) FROM indicator_registry WHERE {where}",
        params,
    )
    total = cur.fetchone()[0]
    cur.execute(
        f"""
        SELECT {_REGISTRY_COLUMNS}
        FROM indicator_registry
        WHERE {where}
        ORDER BY updated_at DESC, id DESC
        LIMIT %s OFFSET %s
        """,
        [*params, limit, offset],
    )
    rows = [_registry_row_to_dict(row) for row in cur.fetchall()]
    return {"total": total, "limit": limit, "offset": offset, "items": rows}


def list_registry_events(
    conn,
    registry_id: int,
    *,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT {_EVENT_COLUMNS}
        FROM indicator_response_events
        WHERE registry_id = %s
        ORDER BY created_at DESC, id DESC
        LIMIT %s OFFSET %s
        """,
        (registry_id, limit, offset),
    )
    return [_event_row_to_dict(row) for row in cur.fetchall()]


def apply_monitor_expiry(conn, *, now: datetime | None = None) -> int:
    """Mark monitored records past expiry as expired. Returns updated count."""
    moment = now or datetime.now(timezone.utc)
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE indicator_registry
        SET current_disposition = 'expired',
            updated_at = NOW()
        WHERE current_disposition = 'monitored'
          AND monitor_expires_at IS NOT NULL
          AND monitor_expires_at <= %s
        RETURNING id
        """,
        (moment,),
    )
    return len(cur.fetchall())
