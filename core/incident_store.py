from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from core.pfsense_operational_baseline import (
    build_alert_operational_history,
    build_incident_operational_history,
    build_pfsense_incident_scope_filter,
)
from core.audit_helpers import log_audit_event
from core.investigation_intelligence import (
    build_campaign_intelligence,
    build_incident_intelligence,
    build_investigation_value,
    build_returning_attacker_context,
    determine_incident_priority,
)

logger = logging.getLogger(__name__)

SEVERITY_TO_PRIORITY = {"CRITICAL": "P1", "HIGH": "P2"}

ALL_INCIDENT_STATUSES = frozenset({"open", "investigating", "resolved", "closed"})

ALLOWED_STATUS_TRANSITIONS = {
    "open": frozenset({"investigating", "resolved", "closed"}),
    "investigating": frozenset({"resolved", "closed"}),
    "resolved": frozenset({"closed", "open"}),
    "closed": frozenset(),
}


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _incident_row_to_dict(
    record: tuple[Any, ...],
    *,
    operational_history: dict[str, Any] | None = None,
) -> dict[str, Any]:
    (
        row_id,
        title,
        severity,
        priority,
        status,
        source_ip,
        assigned_to,
        created_at,
        resolved_at,
    ) = record
    return {
        "id": row_id,
        "title": title,
        "severity": severity,
        "priority": priority,
        "status": status,
        "source_ip": source_ip,
        "assigned_to": assigned_to,
        "created_at": _iso(created_at),
        "resolved_at": _iso(resolved_at),
        "operational_history": operational_history,
    }


def create_incident(
    conn,
    title: str,
    severity: str,
    source_ip: str,
    *,
    priority: str | None = None,
) -> dict[str, Any]:
    sev_upper = severity.upper()
    priority = priority or SEVERITY_TO_PRIORITY.get(sev_upper, "P2")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO incidents (title, severity, priority, status, source_ip)
            VALUES (%s, %s, %s, 'open', %s::inet)
            RETURNING id, title, severity, priority, status, host(source_ip),
                      assigned_to, created_at, resolved_at
            """,
            (title, severity, priority, source_ip),
        )
        return _incident_row_to_dict(cur.fetchone())


def link_alert_to_incident(conn, incident_id: int, alert_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO incident_alerts (incident_id, alert_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            RETURNING incident_id
            """,
            (incident_id, alert_id),
        )
        if cur.fetchone() is not None:
            logger.info(
                "[INCIDENT LINK] incident_id=%s alert_id=%s",
                incident_id,
                alert_id,
            )
        else:
            logger.info(
                "[INCIDENT LINK] already linked incident_id=%s alert_id=%s",
                incident_id,
                alert_id,
            )


def find_open_incident_by_source_ip(
    conn, source_ip: str, dedup_window_minutes: int = 60
) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, title, severity, priority, status, host(source_ip),
                   assigned_to, created_at, resolved_at
            FROM incidents
            WHERE source_ip = %s::inet
              AND status IN ('open', 'investigating')
              AND created_at >= NOW() - (%s * INTERVAL '1 minute')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_ip, dedup_window_minutes),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return _incident_row_to_dict(row)


def maybe_create_or_link_incident(
    conn, alert_id: int, severity: str, source_ip: str, *, alert_type: str | None = None, context: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    sev_upper = (severity or "").upper()
    if sev_upper not in {"HIGH", "CRITICAL"}:
        return None
    if str(alert_type or "").startswith("pfsense_"):
        flags = context.get("operational_flags") if isinstance(context, dict) else {}
        if not bool(flags.get("incident_eligible")):
            return None

    existing = find_open_incident_by_source_ip(conn, source_ip)
    if existing is not None:
        iid = existing["id"]
        link_alert_to_incident(conn, iid, alert_id)
        upgraded = _maybe_upgrade_incident_severity(conn, existing, sev_upper, alert_id)
        logger.info(
            "[INCIDENT LINKED] alert_id=%s to existing incident_id=%s",
            alert_id,
            iid,
        )
        return {**(upgraded or existing), "created": False}

    context = context if isinstance(context, dict) else {}
    target_context = context.get("target_context") if isinstance(context.get("target_context"), dict) else {}
    returning_attacker = build_returning_attacker_context(
        {
            "first_seen": target_context.get("first_seen") or context.get("first_seen"),
            "last_seen": target_context.get("last_seen") or context.get("last_seen"),
            "previous_responses": 1 if context.get("response_status") else 0,
            "repeated_destinations": 1 if target_context.get("primary_destination_ip") else 0,
            "repeated_services": 1 if target_context.get("primary_destination_port") else 0,
            "campaign_count": 1 if context.get("recon_activity") else 0,
        }
    )
    campaign_intelligence = build_campaign_intelligence(
        {
            "first_seen": target_context.get("first_seen") or context.get("first_seen"),
            "last_seen": target_context.get("last_seen") or context.get("last_seen"),
            "source_count": int((context.get("recon_activity") or {}).get("source_ip_count") or 0),
            "destination_count": int(target_context.get("distinct_destination_count") or 0),
            "service_count": int(target_context.get("distinct_port_count") or 0),
            "corroborating_alert_types": 1,
            "progression_observed": bool(alert_type == "pfsense_firewall_allow_after_deny"),
            "relationship": "Shared recon activity" if context.get("recon_activity") else "",
        }
    )
    investigation_value = build_investigation_value(
        severity=severity,
        returning_attacker=returning_attacker,
        campaign_intelligence=campaign_intelligence,
        progression_observed=bool(alert_type == "pfsense_firewall_allow_after_deny"),
        corroborating_detection_count=1,
        response_history_present=bool(context.get("response_status")),
        repeated_destination=bool(target_context.get("primary_destination_ip")),
        persistent_activity=returning_attacker.get("days_observed", 0) > 1,
    )
    if not str(alert_type or "").startswith("pfsense_") and not context:
        priority = SEVERITY_TO_PRIORITY.get(sev_upper, "P2")
    else:
        priority = determine_incident_priority(
            severity=severity,
            investigation_value_level=investigation_value["level"],
            progression_observed=bool(alert_type == "pfsense_firewall_allow_after_deny"),
            campaign_present=campaign_intelligence.get("present", False),
        )
    title = f"[AUTO] {sev_upper} alert from {source_ip}"
    new_inc = create_incident(conn, title, severity, source_ip, priority=priority)
    link_alert_to_incident(conn, new_inc["id"], alert_id)
    logger.info(
        "[INCIDENT CREATED] incident_id=%s for alert_id=%s",
        new_inc["id"],
        alert_id,
    )
    return {**new_inc, "created": True}


def _maybe_upgrade_incident_severity(
    conn,
    incident: dict[str, Any],
    new_alert_severity: str,
    alert_id: int,
) -> dict[str, Any] | None:
    if str(new_alert_severity or "").upper() != "CRITICAL":
        return None

    current_severity = str(incident.get("severity") or "").upper()
    if current_severity == "CRITICAL":
        return None

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE incidents
            SET severity = 'CRITICAL',
                priority = 'P1'
            WHERE id = %s
              AND UPPER(severity) <> 'CRITICAL'
            RETURNING id, title, severity, priority, status, host(source_ip),
                      assigned_to, created_at, resolved_at
            """,
            (incident["id"],),
        )
        row = cur.fetchone()
        if row is None:
            return None
        upgraded = _incident_row_to_dict(row)

    log_audit_event(
        "incident_severity_escalated",
        target_alert_id=alert_id,
        details={
            "incident_id": incident["id"],
            "from_severity": incident.get("severity"),
            "to_severity": upgraded.get("severity"),
            "from_priority": incident.get("priority"),
            "to_priority": upgraded.get("priority"),
        },
    )
    logger.info(
        "[INCIDENT ESCALATED] incident_id=%s alert_id=%s from=%s/%s to=%s/%s",
        incident["id"],
        alert_id,
        incident.get("severity"),
        incident.get("priority"),
        upgraded.get("severity"),
        upgraded.get("priority"),
    )
    return upgraded


def list_incidents(
    conn,
    status: str | None = None,
    severity: str | None = None,
    operational_scope: str = "all_history",
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    cap = min(max(int(limit), 0), 100)
    offset = max(int(offset), 0)
    filters: list[str] = []
    params: list[Any] = []

    if status is not None:
        filters.append("status = %s")
        params.append(status)
    if severity is not None:
        filters.append("severity = %s")
        params.append(severity)
    operational_clause, operational_params = build_pfsense_incident_scope_filter(
        operational_scope,
        incident_alias="incidents",
    )
    if operational_clause:
        filters.append(operational_clause)
        params.extend(operational_params)

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    params.extend([cap, offset])

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, title, severity, priority, status, host(source_ip),
                   assigned_to, created_at, resolved_at
            FROM incidents
            {where}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            params,
        )
        rows = cur.fetchall()
        incident_ids = [row[0] for row in rows]
        legacy_by_incident_id = _build_incident_legacy_map(cur, incident_ids)
        incidents = [
            _incident_row_to_dict(
                row,
                operational_history=legacy_by_incident_id.get(row[0]),
            )
            for row in rows
        ]
        for incident in incidents:
            incident["incident_intelligence"] = {
                "ownership": "Source-specific investigation" if incident.get("source_ip") else "Aggregate investigation",
                "summary": f"{incident.get('priority') or 'Unclassified'} priority assigned by incident policy",
                "reasons": [
                    {
                        "id": "priority",
                        "text": f"Priority {incident.get('priority') or 'N/A'} is reserved for actionability, not severity alone",
                    }
                ],
                "auto_close_recommended": False,
                "auto_close_reason": None,
            }
        return incidents


def get_incident_detail(conn, incident_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, title, severity, priority, status, host(source_ip),
                   assigned_to, created_at, resolved_at
            FROM incidents
            WHERE id = %s
            """,
            (incident_id,),
        )
        inc_row = cur.fetchone()
        if inc_row is None:
            return None
        base = _incident_row_to_dict(inc_row)
        cur.execute(
            """
            SELECT a.id, a.alert_type, a.severity, host(a.source_ip), a.status, a.created_at,
                   a.source, a.source_type,
                   ia.linked_at
            FROM incident_alerts ia
            JOIN alerts a ON a.id = ia.alert_id
            WHERE ia.incident_id = %s
            ORDER BY ia.linked_at ASC
            """,
            (incident_id,),
        )
        alerts = []
        for a_row in cur.fetchall():
            (
                aid,
                alert_type,
                a_sev,
                a_ip,
                a_status,
                a_created,
                a_source,
                a_source_type,
                linked_at,
            ) = a_row
            alerts.append(
                {
                    "alert_id": aid,
                    "alert_type": alert_type,
                    "severity": a_sev,
                    "source_ip": a_ip,
                    "status": a_status,
                    "created_at": _iso(a_created),
                    "source": a_source,
                    "source_type": a_source_type,
                    "operational_history": build_alert_operational_history(
                        created_at=a_created,
                        source=a_source,
                        source_type=a_source_type,
                    ),
                    "linked_at": _iso(linked_at),
                }
            )
        base["alerts"] = alerts
        base["operational_history"] = build_incident_operational_history(
            created_at=base["created_at"],
            linked_alerts=alerts,
        )
        base["incident_intelligence"] = build_incident_intelligence(
            incident=base,
            linked_alerts=alerts,
        )
        return base


def _build_incident_legacy_map(cur, incident_ids: list[int]) -> dict[int, dict[str, Any] | None]:
    filtered_ids = [int(incident_id) for incident_id in incident_ids if incident_id is not None]
    if not filtered_ids:
        return {}
    cur.execute(
        """
        SELECT
            i.id,
            i.created_at,
            a.created_at,
            a.source,
            a.source_type
        FROM incidents i
        LEFT JOIN incident_alerts ia ON ia.incident_id = i.id
        LEFT JOIN alerts a ON a.id = ia.alert_id
        WHERE i.id = ANY(%s)
        ORDER BY i.id ASC, ia.linked_at ASC
        """,
        (filtered_ids,),
    )
    grouped: dict[int, dict[str, Any]] = {}
    for incident_id, incident_created_at, alert_created_at, alert_source, alert_source_type in cur.fetchall():
        bucket = grouped.setdefault(
            incident_id,
            {"created_at": incident_created_at, "alerts": []},
        )
        if alert_created_at is not None:
            bucket["alerts"].append(
                {
                    "created_at": alert_created_at,
                    "source": alert_source,
                    "source_type": alert_source_type,
                }
            )
    return {
        incident_id: build_incident_operational_history(
            created_at=bucket["created_at"],
            linked_alerts=bucket["alerts"],
        )
        for incident_id, bucket in grouped.items()
    }


def update_incident_status(
    conn, incident_id: int, new_status: str, actor_username: str
) -> dict[str, Any]:
    _ = actor_username
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, title, severity, priority, status, host(source_ip),
                   assigned_to, created_at, resolved_at
            FROM incidents
            WHERE id = %s
            FOR UPDATE
            """,
            (incident_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError("incident not found")

        current = row[4]
        if new_status not in ALL_INCIDENT_STATUSES:
            raise ValueError(f"invalid status transition: {current} -> {new_status}")
        allowed = ALLOWED_STATUS_TRANSITIONS.get(current, frozenset())
        if new_status not in allowed:
            raise ValueError(f"invalid status transition: {current} -> {new_status}")

        if new_status == "resolved":
            cur.execute(
                """
                UPDATE incidents
                SET status = %s, resolved_at = NOW()
                WHERE id = %s
                RETURNING id, title, severity, priority, status, host(source_ip),
                          assigned_to, created_at, resolved_at
                """,
                (new_status, incident_id),
            )
        else:
            cur.execute(
                """
                UPDATE incidents
                SET status = %s
                WHERE id = %s
                RETURNING id, title, severity, priority, status, host(source_ip),
                          assigned_to, created_at, resolved_at
                """,
                (new_status, incident_id),
            )
        return _incident_row_to_dict(cur.fetchone())


def auto_close_resolved_p3_incidents_for_alert(conn, alert_id: int) -> list[int]:
    closed_ids: list[int] = []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT i.id, i.status, i.assigned_to
            FROM incidents i
            JOIN incident_alerts ia ON ia.incident_id = i.id
            WHERE ia.alert_id = %s
              AND i.priority = 'P3'
              AND i.status IN ('open', 'investigating', 'resolved')
            """,
            (alert_id,),
        )
        incident_rows = cur.fetchall()
        for incident_id, incident_status, assigned_to in incident_rows:
            incident_id = int(incident_id)
            if str(incident_status or "").lower() == "investigating" or assigned_to:
                continue
            cur.execute(
                """
                SELECT COUNT(*)
                FROM incident_alerts ia
                JOIN alerts a ON a.id = ia.alert_id
                WHERE ia.incident_id = %s
                  AND a.status <> 'resolved'
                """,
                (incident_id,),
            )
            unresolved_count = int(cur.fetchone()[0] or 0)
            if unresolved_count > 0:
                continue
            cur.execute(
                """
                SELECT COUNT(*)
                FROM approval_requests
                WHERE incident_id = %s
                  AND status = 'pending'
                """,
                (incident_id,),
            )
            pending_approvals = int(cur.fetchone()[0] or 0)
            if pending_approvals > 0:
                continue
            cur.execute(
                """
                SELECT COUNT(*)
                FROM response_actions_queue
                WHERE alert_id IN (
                    SELECT alert_id
                    FROM incident_alerts
                    WHERE incident_id = %s
                )
                  AND status IN ('pending', 'running', 'awaiting_approval')
                """,
                (incident_id,),
            )
            active_queue_rows = int(cur.fetchone()[0] or 0)
            if active_queue_rows > 0:
                continue
            cur.execute(
                """
                SELECT COUNT(*)
                FROM playbook_executions
                WHERE incident_id = %s
                  AND status IN ('pending', 'running', 'awaiting_approval')
                """,
                (incident_id,),
            )
            active_playbooks = int(cur.fetchone()[0] or 0)
            if active_playbooks > 0:
                continue
            cur.execute(
                """
                UPDATE incidents
                SET status = 'closed',
                    resolved_at = COALESCE(resolved_at, NOW())
                WHERE id = %s
                  AND status <> 'closed'
                  AND status <> 'investigating'
                  AND assigned_to IS NULL
                RETURNING id
                """,
                (incident_id,),
            )
            row = cur.fetchone()
            if row is not None:
                closed_ids.append(int(row[0]))
                log_audit_event(
                    "incident_auto_closed",
                    target_alert_id=alert_id,
                    details={
                        "incident_id": incident_id,
                        "reason": "All linked alerts resolved and no pending approvals, active response actions, active playbooks, or analyst-owned review remained",
                        "closure_policy": "p3_resolved_autoclose",
                    },
                )
    return closed_ids
