from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from core.incident_store import get_incident_detail
from core.ip_helpers import get_ip_reputation
from helpers.enrichment_helpers import (
    enrich_alert_with_correlation_context,
    enrich_alert_with_mitre,
)

DEFAULT_LIMIT = 5
MAX_LIMIT = 25

_USERNAME_CONTEXT_KEYS = (
    "username",
    "user",
    "account",
    "target_username",
    "source_username",
    "usernames",
)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _normalize_context(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _cap_limit(raw_limit: Any) -> int:
    if isinstance(raw_limit, bool):
        return DEFAULT_LIMIT
    try:
        parsed = int(raw_limit)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    return min(max(parsed, 1), MAX_LIMIT)


def _fetch_alert(cur, alert_id: int | None) -> dict[str, Any] | None:
    if alert_id is None:
        return None
    cur.execute(
        """
        SELECT
            id,
            alert_type,
            severity,
            host(source_ip),
            status,
            message,
            source,
            source_type,
            country,
            city,
            latitude,
            longitude,
            reputation_score,
            reputation_label,
            reputation_source,
            reputation_summary,
            response_action,
            response_status,
            created_at,
            context
        FROM alerts
        WHERE id = %s
        """,
        (alert_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    context = _normalize_context(row[19])
    alert = {
        "id": row[0],
        "alert_type": row[1],
        "severity": row[2],
        "source_ip": row[3],
        "status": row[4],
        "message": row[5],
        "source": row[6],
        "source_type": row[7],
        "country": row[8],
        "city": row[9],
        "latitude": row[10],
        "longitude": row[11],
        "reputation_score": row[12],
        "reputation_label": row[13],
        "reputation_source": row[14],
        "reputation_summary": row[15],
        "response_action": row[16],
        "response_status": row[17],
        "created_at": _iso(row[18]),
        "context": context,
    }
    return alert


def _fetch_alerts_by_ids(cur, alert_ids: list[int], limit: int) -> list[dict[str, Any]]:
    if not alert_ids:
        return []
    cur.execute(
        """
        SELECT id, alert_type, severity, host(source_ip), status, message,
               source, source_type, country, city, latitude, longitude,
               reputation_score, reputation_label, reputation_source,
               reputation_summary, response_action, response_status,
               created_at, context
        FROM alerts
        WHERE id = ANY(%s::INTEGER[])
        ORDER BY created_at DESC, id DESC
        LIMIT %s
        """,
        (alert_ids, limit),
    )
    alerts = []
    for row in cur.fetchall():
        alerts.append(
            {
                "id": row[0],
                "alert_type": row[1],
                "severity": row[2],
                "source_ip": row[3],
                "status": row[4],
                "message": row[5],
                "source": row[6],
                "source_type": row[7],
                "country": row[8],
                "city": row[9],
                "latitude": row[10],
                "longitude": row[11],
                "reputation_score": row[12],
                "reputation_label": row[13],
                "reputation_source": row[14],
                "reputation_summary": row[15],
                "response_action": row[16],
                "response_status": row[17],
                "created_at": _iso(row[18]),
                "context": _normalize_context(row[19]),
            }
        )
    return alerts


def _fetch_related_alerts(cur, source_ip: str | None, limit: int) -> tuple[dict[str, Any], list[int]]:
    if not source_ip:
        return {"counts": {"total": 0, "open": 0, "resolved": 0}, "recent": []}, []
    cur.execute(
        """
        SELECT
            COUNT(*),
            COUNT(*) FILTER (WHERE status = 'open'),
            COUNT(*) FILTER (WHERE status = 'resolved')
        FROM alerts
        WHERE source_ip = %s::inet
        """,
        (source_ip,),
    )
    total, open_count, resolved_count = cur.fetchone() or (0, 0, 0)

    cur.execute(
        """
        SELECT id, alert_type, severity, status, message, created_at,
               response_action, response_status, source, source_type,
               country, city, latitude, longitude,
               reputation_score, reputation_label, reputation_source, reputation_summary
        FROM alerts
        WHERE source_ip = %s::inet
        ORDER BY created_at DESC, id DESC
        LIMIT %s
        """,
        (source_ip, limit),
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
            "source": row[8],
            "source_type": row[9],
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

    cur.execute("SELECT id FROM alerts WHERE source_ip = %s::inet", (source_ip,))
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


def _fetch_historical_detections(cur, source_ip: str | None, limit: int) -> dict[str, Any]:
    if not source_ip:
        return {"by_alert_type": [], "total": 0}
    cur.execute(
        """
        SELECT alert_type, COUNT(*), MAX(created_at)
        FROM alerts
        WHERE source_ip = %s::inet
        GROUP BY alert_type
        ORDER BY COUNT(*) DESC, MAX(created_at) DESC, alert_type ASC
        LIMIT %s
        """,
        (source_ip, limit),
    )
    rows = [
        {"alert_type": row[0], "count": int(row[1] or 0), "last_seen_at": _iso(row[2])}
        for row in cur.fetchall()
    ]
    return {"by_alert_type": rows, "total": sum(item["count"] for item in rows)}


def _fetch_previous_incidents(
    cur,
    source_ip: str | None,
    alert_ids: list[int],
    limit: int,
) -> tuple[dict[str, Any], list[int]]:
    if not source_ip and not alert_ids:
        return {"count": 0, "recent": []}, []
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
            )
        FROM incidents i
        LEFT JOIN incident_alerts ia ON ia.incident_id = i.id
        WHERE (%s::TEXT IS NOT NULL AND i.source_ip = %s::inet)
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
        (source_ip, source_ip, alert_ids, limit),
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


def _fetch_external_reputation_snapshots(
    cur,
    source_ip: str | None,
    limit: int,
) -> dict[str, Any]:
    if not source_ip:
        return {"latest_external": None, "external_snapshots": []}
    cur.execute(
        """
        SELECT id, created_at, reputation_score, reputation_label,
               reputation_source, reputation_summary
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
        (source_ip, limit),
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
    cur,
    alert_ids: list[int],
    incident_ids: list[int],
    limit: int,
) -> dict[str, Any]:
    if not alert_ids and not incident_ids:
        return {"count": 0, "recent": []}
    cur.execute(
        """
        SELECT id, playbook_id, alert_id, incident_id, status,
               started_at, completed_at, created_at
        FROM playbook_executions
        WHERE alert_id = ANY(%s::INTEGER[])
           OR incident_id = ANY(%s::INTEGER[])
        ORDER BY created_at DESC, id DESC
        LIMIT %s
        """,
        (alert_ids, incident_ids, limit),
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


def _extract_usernames(*contexts: dict[str, Any]) -> list[str]:
    usernames: set[str] = set()
    for context in contexts:
        if not isinstance(context, dict):
            continue
        for key in _USERNAME_CONTEXT_KEYS:
            value = context.get(key)
            if isinstance(value, str) and value.strip():
                usernames.add(value.strip())
            elif isinstance(value, list):
                usernames.update(item.strip() for item in value if isinstance(item, str) and item.strip())
    return sorted(usernames)


def build_playbook_enrichment_context(
    conn,
    execution: dict[str, Any],
    *,
    limit: Any = DEFAULT_LIMIT,
) -> dict[str, Any]:
    capped_limit = _cap_limit(limit)
    alert_id = execution.get("alert_id")
    incident_id = execution.get("incident_id")

    with conn.cursor() as cur:
        alert = _fetch_alert(cur, int(alert_id)) if alert_id is not None else None
        incident = get_incident_detail(conn, int(incident_id)) if incident_id is not None else None
        linked_alert_ids = [
            int(item["alert_id"])
            for item in (incident or {}).get("alerts", [])
            if item.get("alert_id") is not None
        ]
        linked_alerts = _fetch_alerts_by_ids(cur, linked_alert_ids, capped_limit)

        if alert is None and linked_alerts:
            alert = linked_alerts[0]

        source_ip = None
        if alert is not None:
            source_ip = alert.get("source_ip")
        if not source_ip and incident is not None:
            source_ip = incident.get("source_ip")

        enriched_alert = None
        mitre = {}
        correlation = {}
        if alert is not None:
            enriched = enrich_alert_with_correlation_context(
                enrich_alert_with_mitre(dict(alert))
            )
            enriched_alert = {
                key: enriched.get(key)
                for key in (
                    "id",
                    "alert_type",
                    "severity",
                    "source_ip",
                    "status",
                    "message",
                    "source",
                    "source_type",
                    "country",
                    "city",
                    "latitude",
                    "longitude",
                    "response_action",
                    "response_status",
                    "created_at",
                )
            }
            enriched_alert["context"] = enriched.get("context") or {}
            mitre = {
                "technique_id": enriched.get("mitre_technique_id"),
                "technique_name": enriched.get("mitre_technique_name"),
                "tactic": enriched.get("mitre_tactic"),
            }
            correlation = {
                "is_correlation_alert": bool(enriched.get("is_correlation_alert")),
                "correlated_alert_types": enriched.get("correlated_alert_types") or [],
                "correlated_alert_count": enriched.get("correlated_alert_count"),
                "correlation_context": enriched.get("correlation_context") or None,
            }

        related_alerts, alert_ids = _fetch_related_alerts(cur, source_ip, capped_limit)
        if alert_id is not None and int(alert_id) not in alert_ids:
            alert_ids.append(int(alert_id))
        for linked_id in linked_alert_ids:
            if linked_id not in alert_ids:
                alert_ids.append(linked_id)

        previous_incidents, incident_ids = _fetch_previous_incidents(
            cur, source_ip, alert_ids, capped_limit
        )
        if incident_id is not None and int(incident_id) not in incident_ids:
            incident_ids.append(int(incident_id))

        reputation = _fetch_external_reputation_snapshots(cur, source_ip, capped_limit)
        reputation["behavioral"] = get_ip_reputation(source_ip, cur=cur) if source_ip else get_ip_reputation(None)
        reputation["alert_snapshot"] = (
            {
                "score": alert.get("reputation_score"),
                "label": alert.get("reputation_label"),
                "source": alert.get("reputation_source"),
                "summary": alert.get("reputation_summary"),
            }
            if alert is not None
            else None
        )

        historical_detections = _fetch_historical_detections(cur, source_ip, capped_limit)
        playbook_executions = _fetch_playbook_execution_context(
            cur, alert_ids, incident_ids, capped_limit
        )

    target_type = "alert" if alert_id is not None else "incident"
    return {
        "target": {
            "target_type": target_type,
            "target_id": int(alert_id) if alert_id is not None else int(incident_id),
            "alert_id": int(alert_id) if alert_id is not None else None,
            "incident_id": int(incident_id) if incident_id is not None else None,
            "source_ip": source_ip,
        },
        "alert": enriched_alert,
        "incident": incident,
        "linked_alerts": linked_alerts,
        "mitre": mitre,
        "correlation": correlation,
        "reputation": reputation,
        "related_alerts": related_alerts,
        "historical_detections": historical_detections,
        "previous_incidents": previous_incidents,
        "source_ip_context": {
            "source_ip": source_ip,
            "alert_counts": related_alerts.get("counts", {}),
            "incident_count": previous_incidents.get("count", 0),
            "playbook_execution_count": playbook_executions.get("count", 0),
            "behavioral_reputation": reputation.get("behavioral"),
            "latest_external_reputation": reputation.get("latest_external"),
        },
        "playbook_executions": playbook_executions,
        "usernames": _extract_usernames(
            (alert or {}).get("context", {}),
            *[item.get("context", {}) for item in linked_alerts],
        ),
        "limits": {"collection_limit": capped_limit},
    }
