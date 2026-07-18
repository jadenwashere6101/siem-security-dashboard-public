from __future__ import annotations

import ipaddress
from datetime import datetime, timezone
from typing import Any

from flask import Blueprint, current_app, jsonify, request
from flask_login import login_required

from core.auth import analyst_or_super_admin_required
from core.db import get_db_connection
from core.internet_noise import build_internet_noise_decision, get_internet_noise_assessment
from core.investigation_intelligence import (
    build_campaign_intelligence,
    build_local_evidence_override_reasons,
    build_returning_attacker_context,
)
from core.ip_helpers import get_ip_reputation
from core.soar_response_outcomes import (
    get_outcome_count_groups,
    get_recent_outcomes_for_source_ip,
)


source_ip_context_bp = Blueprint("source_ip_context", __name__)

RECENT_LIMITS = {
    "alerts": 10,
    "incidents": 10,
    "queue": 10,
    "playbook_executions": 10,
    "external_reputation_snapshots": 5,
}


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _validate_source_ip(raw_value: str | None) -> str | tuple[dict[str, str], int]:
    source_ip = (raw_value or "").strip()
    if not source_ip:
        return {"error": "source_ip is required"}, 400
    try:
        return str(ipaddress.ip_address(source_ip))
    except ValueError:
        return {"error": "source_ip is invalid"}, 400


def _fetch_alert_context(cur, source_ip: str) -> tuple[dict[str, Any], list[int]]:
    cur.execute(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE status = 'open') AS open_count,
            COUNT(*) FILTER (WHERE status = 'resolved') AS resolved_count
        FROM alerts
        WHERE source_ip = %s::inet
        """,
        (source_ip,),
    )
    total, open_count, resolved_count = cur.fetchone() or (0, 0, 0)

    cur.execute(
        """
        SELECT
            id,
            alert_type,
            severity,
            status,
            message,
            created_at,
            response_action,
            response_status,
            source,
            source_type,
            country,
            city,
            latitude,
            longitude,
            reputation_score,
            reputation_label,
            reputation_source,
            reputation_summary
        FROM alerts
        WHERE source_ip = %s::inet
        ORDER BY created_at DESC, id DESC
        LIMIT %s
        """,
        (source_ip, RECENT_LIMITS["alerts"]),
    )
    recent = [
        {
            "id": row[0],
            "alert_type": row[1],
            "severity": row[2],
            "status": row[3],
            "message": row[4],
            "created_at": _iso(row[5]),
            "response_action": row[6],
            "response_status": row[7],
            "source": row[8] or "unknown",
            "source_type": row[9] or "legacy",
            "country": row[10],
            "city": row[11],
            "latitude": row[12],
            "longitude": row[13],
            "external_reputation": {
                "score": row[14],
                "label": row[15],
                "source": row[16],
                "summary": row[17],
            },
        }
        for row in cur.fetchall()
    ]

    cur.execute(
        """
        SELECT id
        FROM alerts
        WHERE source_ip = %s::inet
        """,
        (source_ip,),
    )
    alert_ids = [row[0] for row in cur.fetchall()]

    return (
        {
            "counts": {
                "total": int(total or 0),
                "open": int(open_count or 0),
                "resolved": int(resolved_count or 0),
            },
            "recent": recent,
        },
        alert_ids,
    )


def _fetch_incident_context(cur, source_ip: str, alert_ids: list[int]) -> tuple[dict[str, Any], list[int]]:
    cur.execute(
        """
        SELECT
            i.id,
            i.title,
            i.severity,
            i.priority,
            i.status,
            host(i.source_ip),
            i.assigned_to,
            i.created_at,
            i.resolved_at,
            COALESCE(
                ARRAY_AGG(DISTINCT ia.alert_id) FILTER (WHERE ia.alert_id IS NOT NULL),
                ARRAY[]::INTEGER[]
            ) AS linked_alert_ids
        FROM incidents i
        LEFT JOIN incident_alerts ia ON ia.incident_id = i.id
        WHERE i.source_ip = %s::inet
           OR EXISTS (
                SELECT 1
                FROM incident_alerts ia_match
                WHERE ia_match.incident_id = i.id
                  AND ia_match.alert_id = ANY(%s::INTEGER[])
           )
        GROUP BY i.id, i.title, i.severity, i.priority, i.status, i.source_ip,
                 i.assigned_to, i.created_at, i.resolved_at
        ORDER BY i.created_at DESC, i.id DESC
        LIMIT %s
        """,
        (source_ip, alert_ids, RECENT_LIMITS["incidents"]),
    )
    recent = []
    incident_ids = []
    for row in cur.fetchall():
        incident_ids.append(row[0])
        recent.append(
            {
                "id": row[0],
                "title": row[1],
                "severity": row[2],
                "priority": row[3],
                "status": row[4],
                "source_ip": row[5],
                "assigned_to": row[6],
                "created_at": _iso(row[7]),
                "resolved_at": _iso(row[8]),
                "linked_alert_ids": list(row[9] or []),
            }
        )

    return {"count": len(recent), "recent": recent}, incident_ids


def _fetch_queue_context(cur, source_ip: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT status, COUNT(*)
        FROM response_actions_queue
        WHERE source_ip = %s::inet
        GROUP BY status
        """,
        (source_ip,),
    )
    by_status = {row[0]: int(row[1]) for row in cur.fetchall()}

    cur.execute(
        """
        SELECT
            id,
            alert_id,
            action,
            status,
            retry_count,
            max_retries,
            last_error,
            created_at,
            updated_at
        FROM response_actions_queue
        WHERE source_ip = %s::inet
        ORDER BY created_at DESC, id DESC
        LIMIT %s
        """,
        (source_ip, RECENT_LIMITS["queue"]),
    )
    recent = [
        {
            "id": row[0],
            "alert_id": row[1],
            "source_ip": source_ip,
            "action": row[2],
            "status": row[3],
            "retry_count": row[4],
            "max_retries": row[5],
            "last_error": row[6],
            "created_at": _iso(row[7]),
            "updated_at": _iso(row[8]),
        }
        for row in cur.fetchall()
    ]
    return {"counts": {"total": sum(by_status.values()), "by_status": by_status}, "recent": recent}


def _effective_blocklist_status(raw_status: str, expires_at: Any) -> str:
    if raw_status == "active":
        if expires_at is not None:
            expires_dt = expires_at
            if expires_dt.tzinfo is None:
                expires_dt = expires_dt.replace(tzinfo=timezone.utc)
            if expires_dt <= datetime.now(timezone.utc):
                return "expired"
        return "active"
    return raw_status or "none"


def _summarize_blocklist_status(entries: list[dict[str, Any]]) -> str:
    statuses = [entry["effective_status"] for entry in entries]
    for candidate in ("active", "expired", "inactive"):
        if candidate in statuses:
            return candidate
    return "none"


def _fetch_blocklist_context(cur, source_ip: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT id, ip_address, reason, status, created_by, created_at, expires_at, source_alert_id
        FROM blocked_ips
        WHERE ip_address = %s::inet
        ORDER BY created_at DESC, id DESC
        """,
        (source_ip,),
    )
    entries = []
    for row in cur.fetchall():
        raw_status = row[3]
        effective_status = _effective_blocklist_status(raw_status, row[6])
        entries.append(
            {
                "id": row[0],
                "ip_address": str(row[1]) if row[1] is not None else None,
                "status": effective_status,
                "raw_status": raw_status,
                "effective_status": effective_status,
                "reason": row[2],
                "created_by": row[4],
                "created_at": _iso(row[5]),
                "expires_at": _iso(row[6]),
                "source_alert_id": row[7],
            }
        )

    return {
        "effective_status": _summarize_blocklist_status(entries),
        "entries": entries,
    }


def _fetch_external_reputation_snapshots(cur, source_ip: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT
            id,
            created_at,
            reputation_score,
            reputation_label,
            reputation_source,
            reputation_summary
        FROM alerts
        WHERE source_ip = %s::inet
          AND (
              reputation_score IS NOT NULL
              OR reputation_label IS NOT NULL
              OR reputation_source IS NOT NULL
              OR reputation_summary IS NOT NULL
          )
        ORDER BY created_at DESC, id DESC
        LIMIT %s
        """,
        (source_ip, RECENT_LIMITS["external_reputation_snapshots"]),
    )
    snapshots = [
        {
            "alert_id": row[0],
            "created_at": _iso(row[1]),
            "score": row[2],
            "label": row[3],
            "source": row[4],
            "summary": row[5],
        }
        for row in cur.fetchall()
    ]
    return {"latest_external": snapshots[0] if snapshots else None, "external_snapshots": snapshots}


def _fetch_playbook_execution_context(
    cur, alert_ids: list[int], incident_ids: list[int]
) -> dict[str, Any]:
    cur.execute(
        """
        SELECT
            id,
            playbook_id,
            alert_id,
            incident_id,
            status,
            started_at,
            completed_at,
            created_at
        FROM playbook_executions
        WHERE alert_id = ANY(%s::INTEGER[])
           OR incident_id = ANY(%s::INTEGER[])
        ORDER BY created_at DESC, id DESC
        LIMIT %s
        """,
        (
            alert_ids,
            incident_ids,
            RECENT_LIMITS["playbook_executions"],
        ),
    )
    recent = [
        {
            "id": row[0],
            "playbook_id": row[1],
            "alert_id": row[2],
            "incident_id": row[3],
            "status": row[4],
            "started_at": _iso(row[5]),
            "completed_at": _iso(row[6]),
            "created_at": _iso(row[7]),
        }
        for row in cur.fetchall()
    ]
    return {"count": len(recent), "recent": recent}


def _fetch_returning_attacker_context(cur, source_ip: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT
            MIN(created_at),
            MAX(created_at),
            COUNT(DISTINCT DATE(created_at)),
            COUNT(DISTINCT ia.incident_id),
            COUNT(*) FILTER (WHERE response_status IS NOT NULL),
            COUNT(DISTINCT NULLIF(COALESCE(context->'target_context'->>'primary_destination_ip', ''), '')),
            COUNT(DISTINCT NULLIF(COALESCE(context->'target_context'->>'primary_destination_port', ''), '')),
            ARRAY_AGG(created_at ORDER BY created_at)
        FROM alerts a
        LEFT JOIN incident_alerts ia ON ia.alert_id = a.id
        WHERE a.source_ip = %s::inet
        """,
        (source_ip,),
    )
    row = cur.fetchone() or (None, None, 0, 0, 0, 0, 0, [])
    return build_returning_attacker_context(
        {
            "first_seen": _iso(row[0]),
            "last_seen": _iso(row[1]),
            "days_observed": int(row[2] or 0),
            "previous_incidents": int(row[3] or 0),
            "previous_responses": int(row[4] or 0),
            "repeated_destinations": int(row[5] or 0),
            "repeated_services": int(row[6] or 0),
            "observed_at": [_iso(value) for value in (row[7] or []) if value is not None],
        }
    )


def _fetch_campaign_memberships(cur, source_ip: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT
            ra.id,
            ra.first_seen,
            ra.last_seen,
            COALESCE((ra.summary->>'source_ip_count')::integer, 0),
            COALESCE((ra.summary->>'destination_ip_count')::integer, 0),
            COALESCE((ra.summary->>'distinct_service_count')::integer, 0),
            COALESCE(jsonb_array_length(COALESCE(ra.summary->'alert_types', '[]'::jsonb)), 0),
            ra.coordination_status,
            ra.related_incident_id
        FROM recon_activity_alerts ral
        JOIN recon_activities ra ON ra.id = ral.recon_activity_id
        WHERE ral.source_ip = %s::inet
        ORDER BY ra.last_seen DESC, ra.id DESC
        LIMIT 10
        """,
        (source_ip,),
    )
    recent = []
    for row in cur.fetchall():
        intelligence = build_campaign_intelligence(
            {
                "first_seen": _iso(row[1]),
                "last_seen": _iso(row[2]),
                "source_count": int(row[3] or 0),
                "destination_count": int(row[4] or 0),
                "service_count": int(row[5] or 0),
                "corroborating_alert_types": int(row[6] or 0),
                "relationship": f"Coordination status: {str(row[7] or 'not_established').replace('_', ' ')}",
            }
        )
        recent.append(
            {
                "id": int(row[0]),
                "label": f"Recon activity #{row[0]}",
                "first_seen": _iso(row[1]),
                "last_seen": _iso(row[2]),
                "related_incident_id": row[8],
                "campaign_intelligence": intelligence,
            }
        )
    return {"count": len(recent), "recent": recent}


@source_ip_context_bp.route("/source-ip-context", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def get_source_ip_context():
    validated = _validate_source_ip(request.args.get("source_ip"))
    if isinstance(validated, tuple):
        payload, status_code = validated
        return jsonify(payload), status_code

    source_ip = validated
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            alerts, alert_ids = _fetch_alert_context(cur, source_ip)
            incidents, incident_ids = _fetch_incident_context(cur, source_ip, alert_ids)
            queue = _fetch_queue_context(cur, source_ip)
            blocklist = _fetch_blocklist_context(cur, source_ip)
            behavioral = get_ip_reputation(source_ip, cur=cur)
            external = _fetch_external_reputation_snapshots(cur, source_ip)
            playbook_executions = _fetch_playbook_execution_context(cur, alert_ids, incident_ids)
            returning_attacker = _fetch_returning_attacker_context(cur, source_ip)
            campaigns = _fetch_campaign_memberships(cur, source_ip)
            internet_noise = build_internet_noise_decision(
                get_internet_noise_assessment(source_ip),
                override_reasons=build_local_evidence_override_reasons(
                    returning_attacker=returning_attacker,
                    campaign_intelligence=(
                    campaigns["recent"][0]["campaign_intelligence"]
                        if campaigns.get("recent")
                        else {}
                    ),
                    corroborating_detection_count=max(campaigns.get("count") or 0, 1),
                    response_history_present=returning_attacker.get("previous_responses", 0) > 0,
                    repeated_destination=returning_attacker.get("repeated_destinations", 0) > 0,
                    persistent_activity=returning_attacker.get("days_observed", 0) > 1,
                ),
            )
            response_outcomes = get_recent_outcomes_for_source_ip(
                conn,
                source_ip,
                limit=10,
            )
            response_outcome_counts = get_outcome_count_groups(conn, source_ip=source_ip)

        return (
            jsonify(
                {
                    "source_ip": source_ip,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "limits": RECENT_LIMITS,
                    "alerts": alerts,
                    "incidents": incidents,
                    "queue": queue,
                    "blocklist": blocklist,
                    "reputation": {
                        "behavioral": {
                            "score": behavioral["reputation_score"],
                            "label": behavioral["reputation_label"],
                            "source": "siem_internal",
                            "summary": behavioral["reputation_summary"],
                            "contributing_signals": behavioral.get("contributing_signals", []),
                        },
                        **external,
                    },
                    "internet_noise": internet_noise,
                    "playbook_executions": playbook_executions,
                    "returning_attacker": returning_attacker,
                    "campaigns": campaigns,
                    "response_outcomes": response_outcomes,
                    "response_outcome_counts": response_outcome_counts,
                }
            ),
            200,
        )
    except Exception as error:
        current_app.logger.error("Error in get_source_ip_context: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()
