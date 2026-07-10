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
    dispositions: list[str] | None = None,
    indicator_type: str | None = None,
    q: str | None = None,
    origin_surface: str | None = None,
    actor_user_id: int | None = None,
    outcome: str | None = None,
    enforcement: str | None = None,
    requested_action: str | None = None,
    related_alert_id: int | None = None,
    related_incident_id: int | None = None,
    updated_after: datetime | None = None,
    updated_before: datetime | None = None,
    sort: str = "updated_at_desc",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    clauses = ["TRUE"]
    params: list[Any] = []

    disposition_values: list[str] = []
    if dispositions:
        disposition_values.extend(
            [d for d in dispositions if d and d in VALID_DISPOSITIONS]
        )
    if disposition and disposition in VALID_DISPOSITIONS:
        disposition_values.append(disposition)
    disposition_values = list(dict.fromkeys(disposition_values))
    if disposition_values:
        clauses.append("r.current_disposition = ANY(%s)")
        params.append(disposition_values)

    if indicator_type:
        clauses.append("r.indicator_type = %s")
        params.append(indicator_type)
    if q:
        clauses.append("r.indicator_value ILIKE %s")
        params.append(f"%{q.strip()}%")
    if updated_after is not None:
        clauses.append("r.updated_at >= %s")
        params.append(updated_after)
    if updated_before is not None:
        clauses.append("r.updated_at <= %s")
        params.append(updated_before)
    if origin_surface:
        clauses.append("e.origin_surface = %s")
        params.append(origin_surface)
    if actor_user_id is not None:
        clauses.append("e.actor_user_id = %s")
        params.append(actor_user_id)
    if outcome:
        clauses.append("e.outcome = %s")
        params.append(outcome)
    if enforcement:
        clauses.append("e.enforcement = %s")
        params.append(enforcement)
    if requested_action:
        clauses.append("e.requested_action = %s")
        params.append(requested_action)
    if related_alert_id is not None:
        clauses.append(
            """
            EXISTS (
                SELECT 1 FROM indicator_response_events ev
                WHERE ev.registry_id = r.id AND ev.alert_id = %s
            )
            """
        )
        params.append(related_alert_id)
    if related_incident_id is not None:
        clauses.append(
            """
            EXISTS (
                SELECT 1 FROM indicator_response_events ev
                WHERE ev.registry_id = r.id AND ev.incident_id = %s
            )
            """
        )
        params.append(related_incident_id)

    where = " AND ".join(clauses)
    order_by = {
        "updated_at_asc": "r.updated_at ASC, r.id ASC",
        "created_at_desc": "r.created_at DESC, r.id DESC",
        "created_at_asc": "r.created_at ASC, r.id ASC",
        "indicator_value_asc": "r.indicator_value ASC, r.id ASC",
        "indicator_value_desc": "r.indicator_value DESC, r.id DESC",
    }.get(sort or "updated_at_desc", "r.updated_at DESC, r.id DESC")

    from_sql = f"""
        FROM indicator_registry r
        LEFT JOIN LATERAL (
            SELECT
                requested_action,
                outcome,
                enforcement,
                origin_surface,
                actor_user_id,
                reason,
                alert_id,
                incident_id
            FROM indicator_response_events
            WHERE registry_id = r.id
            ORDER BY created_at DESC, id DESC
            LIMIT 1
        ) e ON TRUE
        WHERE {where}
    """

    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) {from_sql}", params)
    total = cur.fetchone()[0]
    cur.execute(
        f"""
        SELECT
            r.id,
            r.indicator_type,
            r.indicator_value,
            r.current_disposition,
            r.active_blocked_ip_id,
            r.active_incident_id,
            r.monitor_expires_at,
            r.created_at,
            r.updated_at,
            e.requested_action,
            e.outcome,
            e.enforcement,
            e.origin_surface,
            e.actor_user_id,
            e.reason,
            e.alert_id,
            e.incident_id
        {from_sql}
        ORDER BY {order_by}
        LIMIT %s OFFSET %s
        """,
        [*params, limit, offset],
    )
    rows = []
    for row in cur.fetchall():
        item = _registry_row_to_dict(row[:9])
        item.update(
            {
                "latest_requested_action": row[9],
                "latest_outcome": row[10],
                "enforcement": row[11] or "none",
                "latest_origin_surface": row[12],
                "latest_actor_user_id": row[13],
                "latest_reason": row[14],
                "latest_alert_id": row[15],
                "latest_incident_id": row[16],
                "related_alert_id": row[15],
                "related_incident_id": row[16] or item.get("active_incident_id"),
                "enforcement_statement": (
                    "Tracking only; no firewall or host enforcement."
                    if item.get("current_disposition") == DISPOSITION_BLOCKLIST_TRACKED
                    or row[11] in {None, "none", "tracking_only"}
                    else f"Enforcement mode: {row[11]}"
                ),
            }
        )
        rows.append(item)
    return {"total": total, "limit": limit, "offset": offset, "items": rows}


def get_registry_detail(conn, registry_id: int) -> dict[str, Any] | None:
    record = get_indicator_by_id(conn, registry_id)
    if record is None:
        return None

    events = list_registry_events(conn, registry_id, limit=200, offset=0)
    cur = conn.cursor()

    blocklist_entry = None
    if record.get("active_blocked_ip_id"):
        cur.execute(
            """
            SELECT
                id,
                host(ip_address),
                reason,
                CASE
                    WHEN status = 'active'
                     AND expires_at IS NOT NULL
                     AND expires_at <= NOW()
                    THEN 'expired'
                    ELSE status
                END AS effective_status,
                created_by,
                created_at,
                expires_at,
                source_alert_id
            FROM blocked_ips
            WHERE id = %s
            """,
            (record["active_blocked_ip_id"],),
        )
        brow = cur.fetchone()
        if brow:
            blocklist_entry = {
                "id": brow[0],
                "ip_address": brow[1],
                "reason": brow[2],
                "status": brow[3],
                "created_by": brow[4],
                "created_at": _iso(brow[5]),
                "expires_at": _iso(brow[6]),
                "source_alert_id": brow[7],
            }

    cur.execute(
        """
        SELECT DISTINCT alert_id
        FROM indicator_response_events
        WHERE registry_id = %s AND alert_id IS NOT NULL
        ORDER BY alert_id
        """,
        (registry_id,),
    )
    related_alert_ids = [row[0] for row in cur.fetchall()]

    cur.execute(
        """
        SELECT DISTINCT incident_id
        FROM indicator_response_events
        WHERE registry_id = %s AND incident_id IS NOT NULL
        ORDER BY incident_id
        """,
        (registry_id,),
    )
    related_incident_ids = [row[0] for row in cur.fetchall()]
    if record.get("active_incident_id") and record["active_incident_id"] not in related_incident_ids:
        related_incident_ids.append(record["active_incident_id"])

    latest = events[0] if events else None
    disposition = record.get("current_disposition")
    enforcement = (latest or {}).get("enforcement") or "none"
    if disposition == DISPOSITION_BLOCKLIST_TRACKED or blocklist_entry:
        enforcement_statement = (
            "Tracking only; no firewall or host enforcement is implied."
        )
    elif enforcement in {None, "none"}:
        enforcement_statement = "No firewall or host enforcement."
    else:
        enforcement_statement = f"Enforcement mode: {enforcement}"

    return {
        "record": record,
        "events": events,
        "blocklist_entry": blocklist_entry,
        "related_alert_ids": related_alert_ids,
        "related_incident_ids": related_incident_ids,
        "related_alert_count": len(related_alert_ids),
        "related_incident_count": len(related_incident_ids),
        "enforcement": enforcement,
        "enforcement_statement": enforcement_statement,
        "first_seen": record.get("created_at"),
        "last_updated": record.get("updated_at"),
        "response_source": (latest or {}).get("origin_surface"),
        "latest_event": latest,
    }


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
