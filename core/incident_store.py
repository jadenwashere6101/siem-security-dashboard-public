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
from core.internet_noise import get_internet_noise_assessment, record_internet_noise_outcome
from core.investigation_intelligence import (
    build_campaign_intelligence,
    build_incident_intelligence,
    build_investigation_value,
    build_local_evidence_override_reasons,
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


def _reason(reason_id: str, text: str) -> dict[str, str]:
    return {"id": reason_id, "text": text}


def _priority_summary(priority: str | None) -> tuple[str, str]:
    normalized = str(priority or "").upper()
    if normalized == "P1":
        return (
            "Immediate action is required",
            "Priority P1 is reserved for immediate action and likely-compromise handling",
        )
    if normalized == "P2":
        return (
            "Prompt analyst action is required",
            "Priority P2 is used for progression or containment decisions that should be reviewed promptly",
        )
    return (
        "This case is valid but not urgent",
        "Priority P3 is used for case-worthy activity that does not require immediate action",
    )


def _load_recon_activity_incident(conn, recon_activity_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.id, i.title, i.severity, i.priority, i.status, host(i.source_ip),
                   i.assigned_to, i.created_at, i.resolved_at
            FROM recon_activities ra
            JOIN incidents i ON i.id = ra.related_incident_id
            WHERE ra.id = %s
              AND i.status IN ('open', 'investigating')
            """,
            (recon_activity_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return _incident_row_to_dict(row)


def _set_recon_activity_incident(conn, recon_activity_id: int, incident_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE recon_activities
            SET related_incident_id = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            (incident_id, recon_activity_id),
        )


def _build_incident_policy(
    *,
    severity: str | None,
    alert_type: str | None,
    context: dict[str, Any] | None,
    source_ip: str,
) -> dict[str, Any]:
    context = context if isinstance(context, dict) else {}
    flags = context.get("operational_flags") if isinstance(context.get("operational_flags"), dict) else {}
    target_context = context.get("target_context") if isinstance(context.get("target_context"), dict) else {}
    recon_activity = context.get("recon_activity") if isinstance(context.get("recon_activity"), dict) else {}
    sev_upper = str(severity or "").upper()
    alert_type = str(alert_type or "")
    progression_observed = bool(
        alert_type == "pfsense_firewall_allow_after_deny"
        or flags.get("progression_observed")
        or context.get("progression_observed")
    )
    campaign_present = bool(recon_activity.get("id"))
    returning_attacker = build_returning_attacker_context(
        {
            "first_seen": target_context.get("first_seen") or context.get("first_seen"),
            "last_seen": target_context.get("last_seen") or context.get("last_seen"),
            "previous_incidents": context.get("previous_incidents"),
            "previous_responses": context.get("previous_responses"),
            "repeated_destinations": context.get("repeated_destinations")
            or (1 if target_context.get("primary_destination_ip") else 0),
            "repeated_services": context.get("repeated_services")
            or (1 if target_context.get("primary_destination_port") else 0),
            "campaign_count": 1 if campaign_present else 0,
        }
    )
    campaign_intelligence = build_campaign_intelligence(
        {
            "first_seen": target_context.get("first_seen") or context.get("first_seen"),
            "last_seen": target_context.get("last_seen") or context.get("last_seen"),
            "source_count": int(recon_activity.get("source_ip_count") or context.get("source_count") or 0),
            "destination_count": int(target_context.get("distinct_destination_count") or 0),
            "service_count": int(target_context.get("distinct_port_count") or 0),
            "corroborating_alert_types": int(context.get("corroborating_detection_count") or 1),
            "progression_observed": progression_observed,
            "relationship": "Shared recon activity" if campaign_present else "",
        }
    )
    investigation_value = build_investigation_value(
        alert_type=alert_type,
        severity=severity,
        returning_attacker=returning_attacker,
        campaign_intelligence=campaign_intelligence,
        progression_observed=progression_observed,
        corroborating_detection_count=int(context.get("corroborating_detection_count") or 1),
        response_history_present=bool(context.get("response_status") or context.get("response_history_present")),
        repeated_destination=bool(context.get("repeated_destination") or returning_attacker.get("repeated_destinations", 0) > 0),
        persistent_activity=returning_attacker.get("days_observed", 0) > 1,
        internet_noise_assessment=get_internet_noise_assessment(source_ip, allow_enqueue=False),
        internet_noise_override_reasons=build_local_evidence_override_reasons(
            alert_type=alert_type,
            context=context,
            returning_attacker=returning_attacker,
            campaign_intelligence=campaign_intelligence,
            progression_observed=progression_observed,
            corroborating_detection_count=int(context.get("corroborating_detection_count") or 1),
            destination_important=bool(context.get("destination_important")),
            response_history_present=bool(context.get("response_status") or context.get("response_history_present")),
            repeated_destination=bool(
                context.get("repeated_destination") or returning_attacker.get("repeated_destinations", 0) > 0
            ),
            persistent_activity=returning_attacker.get("days_observed", 0) > 1,
        ),
    )
    internet_noise = investigation_value.get("internet_noise") if isinstance(investigation_value, dict) else {}

    policy = {
        "eligible": False,
        "priority": "P3",
        "ownership": "Source-specific investigation",
        "group_by_recon_activity": False,
        "recon_activity_id": None,
        "title": f"[AUTO] {sev_upper or 'UNKNOWN'} alert from {source_ip}",
        "investigation_value": investigation_value,
        "campaign_intelligence": campaign_intelligence,
        "internet_noise": internet_noise,
        "reasons": [],
    }

    if sev_upper == "CRITICAL":
        policy["eligible"] = True
        policy["priority"] = "P1"
        policy["reasons"] = [
            _reason("critical", "Critical behavior requires immediate incident handling"),
        ]
        return policy

    if alert_type == "honeypot_scanner_detected":
        policy["reasons"] = [_reason("scanner_visibility", "Scanner detections stay alert-only unless stronger evidence appears")]
        return policy

    if alert_type == "honeypot_admin_probe_threshold":
        policy["reasons"] = [_reason("admin_probe_visibility", "Admin-path probing is a review signal, not a case by itself")]
        return policy

    if alert_type == "honeypot_env_probe_threshold":
        stronger_env_evidence = bool(
            progression_observed
            or campaign_present
            or context.get("incident_escalation_approved")
            or context.get("repeated_sensitive_path_probe")
            or context.get("protected_service_retargeted")
            or int(context.get("corroborating_detection_count") or 0) > 1
            or int(context.get("previous_incidents") or 0) > 0
        )
        if not stronger_env_evidence:
            policy["reasons"] = [
                _reason("env_probe_alert_first", "Sensitive-path probing remains alert-first until stronger evidence is present"),
            ]
            return policy
        policy["eligible"] = True
        policy["priority"] = "P2" if progression_observed or campaign_present else "P3"
        policy["reasons"] = [
            _reason("env_probe_escalated", "Sensitive-path probing is backed by stronger recurrence or corroboration"),
        ]
        return policy

    if alert_type == "honeypot_credential_stuffing_threshold":
        policy["eligible"] = True
        policy["priority"] = "P2" if progression_observed or campaign_present else "P3"
        policy["reasons"] = [
            _reason("credential_stuffing", "Credential stuffing is case-worthy malicious behavior"),
        ]
        return policy

    if alert_type.startswith("pfsense_"):
        if not bool(flags.get("incident_eligible")):
            policy["reasons"] = [
                _reason("routine_recon", "Routine pfSense reconnaissance remains visible without opening an incident"),
            ]
            return policy
        if internet_noise.get("effect") == "shadow_observation":
            record_internet_noise_outcome("shadow_incidents_would_prevent")
        elif internet_noise.get("applied_to_incident"):
            record_internet_noise_outcome("incidents_prevented")
            policy["reasons"] = [
                _reason(
                    "internet_noise",
                    "Known commodity internet scanner remains alert-visible, but local evidence does not justify a new incident",
                ),
            ]
            return policy
        policy["eligible"] = True
        policy["priority"] = determine_incident_priority(
            severity=severity,
            investigation_value_level=investigation_value["level"],
            progression_observed=progression_observed,
            campaign_present=campaign_present,
        )
        if campaign_present and not progression_observed:
            policy["ownership"] = "Recon-activity investigation"
            policy["group_by_recon_activity"] = True
            policy["recon_activity_id"] = int(recon_activity["id"])
            policy["title"] = f"[AUTO] Recon Activity {recon_activity['id']} requires review"
            policy["reasons"] = [
                _reason("grouped_recon", "This source belongs to a grouped recon investigation"),
            ]
        else:
            policy["reasons"] = [
                _reason("actionable_pfsense", "Progression-backed or source-specific pfSense behavior is case-worthy"),
            ]
        return policy

    if sev_upper not in {"HIGH", "CRITICAL"}:
        policy["reasons"] = [_reason("severity_gate", "This alert does not meet incident policy thresholds")]
        return policy

    if internet_noise.get("effect") == "shadow_observation":
        record_internet_noise_outcome("shadow_incidents_would_prevent")
    elif internet_noise.get("applied_to_incident"):
        record_internet_noise_outcome("incidents_prevented")
        policy["reasons"] = [
            _reason(
                "internet_noise",
                "Known commodity internet scanner remains visible, but local evidence does not justify a new incident",
            ),
        ]
        return policy

    policy["eligible"] = True
    policy["priority"] = determine_incident_priority(
        severity=severity,
        investigation_value_level=investigation_value["level"],
        progression_observed=progression_observed,
        campaign_present=campaign_present,
    )
    policy["reasons"] = [
        _reason("actionable_review", "This alert is case-worthy, but priority depends on actionability rather than severity alone"),
    ]
    return policy


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
    policy = _build_incident_policy(
        severity=severity,
        alert_type=alert_type,
        context=context,
        source_ip=source_ip,
    )
    if not policy["eligible"]:
        return None

    existing = None
    if policy["group_by_recon_activity"] and policy["recon_activity_id"] is not None:
        existing = _load_recon_activity_incident(conn, int(policy["recon_activity_id"]))
    if existing is None:
        existing = find_open_incident_by_source_ip(conn, source_ip)
    if existing is not None:
        iid = existing["id"]
        link_alert_to_incident(conn, iid, alert_id)
        upgraded = _maybe_upgrade_incident_severity(conn, existing, str(severity or "").upper(), alert_id)
        logger.info(
            "[INCIDENT LINKED] alert_id=%s to existing incident_id=%s",
            alert_id,
            iid,
        )
        return {**(upgraded or existing), "created": False}

    new_inc = create_incident(
        conn,
        policy["title"],
        severity,
        source_ip,
        priority=policy["priority"],
    )
    link_alert_to_incident(conn, new_inc["id"], alert_id)
    if policy["group_by_recon_activity"] and policy["recon_activity_id"] is not None:
        _set_recon_activity_incident(conn, int(policy["recon_activity_id"]), int(new_inc["id"]))
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
            summary, reason = _priority_summary(incident.get("priority"))
            incident["incident_intelligence"] = {
                "ownership": "Source-specific investigation" if incident.get("source_ip") else "Aggregate investigation",
                "summary": summary,
                "reasons": [
                    {
                        "id": "priority",
                        "text": reason,
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
