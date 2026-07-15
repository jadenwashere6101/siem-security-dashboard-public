from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from psycopg2.extras import Json

from core.pfsense_recon import (
    PFSENSE_RECON_ACTIVITY_LABEL,
    PFSENSE_RECON_ACTIVITY_TYPE,
    build_service_signature,
    classify_target_mode,
    summarize_reputation_bucket,
)


def _normalize_alert_context(row: tuple[Any, ...]) -> dict[str, Any]:
    context = row[10] if isinstance(row[10], dict) else {}
    target_context = context.get("target_context") if isinstance(context.get("target_context"), dict) else {}
    return {
        "alert_id": int(row[0]),
        "alert_type": row[1],
        "severity": row[2],
        "source_ip": row[3],
        "country": row[4],
        "reputation_score": row[5],
        "created_at": row[6],
        "message": row[7],
        "source": row[8],
        "source_type": row[9],
        "context": context,
        "target_context": target_context,
    }


def fetch_alert_context(conn, alert_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                id,
                alert_type,
                severity,
                host(source_ip),
                country,
                reputation_score,
                created_at,
                message,
                source,
                source_type,
                context
            FROM alerts
            WHERE id = %s
            """,
            (alert_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return _normalize_alert_context(row)


def _fetch_candidate_activities(conn, protected_range_key: str, first_seen: str | None, last_seen: str | None):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                id,
                service_signature,
                first_seen,
                last_seen,
                summary,
                severity,
                status
            FROM recon_activities
            WHERE activity_type = %s
              AND protected_range_key = %s
              AND status <> 'resolved'
              AND first_seen <= %s::timestamptz + INTERVAL '30 minutes'
              AND last_seen >= %s::timestamptz - INTERVAL '30 minutes'
            ORDER BY last_seen DESC, id DESC
            """,
            (PFSENSE_RECON_ACTIVITY_TYPE, protected_range_key, last_seen, first_seen),
        )
        return cur.fetchall()


def _service_overlap(left: list[int], right: list[int]) -> int:
    return len(set(int(value) for value in left) & set(int(value) for value in right))


def _choose_activity_id(candidate_rows, service_signature: list[int]) -> int | None:
    choice: tuple[int, int] | None = None
    for row in candidate_rows:
        overlap = _service_overlap(row[1] or [], service_signature)
        if overlap <= 0:
            continue
        rank = (overlap, int(row[0]))
        if choice is None or rank > choice:
            choice = rank
    return choice[1] if choice else None


def _coerce_target_snapshot(alert: dict[str, Any]) -> dict[str, Any]:
    target_context = alert.get("target_context") or {}
    sample_ips = list(target_context.get("sample_destination_ips") or [])
    sample_ports = [int(value) for value in (target_context.get("sample_destination_ports") or [])]
    if target_context.get("primary_destination_ip") and not sample_ips:
        sample_ips = [target_context["primary_destination_ip"]]
    if target_context.get("primary_destination_port") and not sample_ports:
        sample_ports = [int(target_context["primary_destination_port"])]
    return {
        "primary_destination_ip": target_context.get("primary_destination_ip"),
        "primary_destination_port": target_context.get("primary_destination_port"),
        "sample_destination_ips": sample_ips,
        "sample_destination_ports": sample_ports,
        "distinct_destination_count": int(target_context.get("distinct_destination_count") or 0),
        "distinct_port_count": int(target_context.get("distinct_port_count") or 0),
        "attempts": int(target_context.get("attempts") or alert["context"].get("event_count") or 0),
        "first_seen": target_context.get("first_seen") or alert["context"].get("first_seen"),
        "last_seen": target_context.get("last_seen") or alert["context"].get("last_seen"),
        "related_event_count": int(
            target_context.get("related_event_count") or alert["context"].get("event_count") or 0
        ),
        "protected_range_key": alert["context"].get("protected_range_key"),
        "service_signature_ports": list(alert["context"].get("service_signature_ports") or sample_ports),
    }


def _aggregate_summary(conn, activity_id: int) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                a.id,
                a.alert_type,
                a.severity,
                host(a.source_ip),
                a.country,
                a.reputation_score,
                a.created_at,
                a.message,
                a.source,
                a.source_type,
                a.context
            FROM recon_activity_alerts ral
            JOIN alerts a ON a.id = ral.alert_id
            WHERE ral.recon_activity_id = %s
            ORDER BY a.created_at ASC, a.id ASC
            """,
            (activity_id,),
        )
        alerts = [_normalize_alert_context(row) for row in cur.fetchall()]
        if not alerts:
            return {
                "underlying_alert_count": 0,
                "underlying_event_count": 0,
                "source_ip_count": 0,
                "destination_ip_count": 0,
                "primary_destination_ports": [],
                "alert_types": [],
                "countries": [],
                "asns": [],
                "reputation_distribution": {},
                "representative_sources": [],
                "target_context": {},
            }

        source_ips = sorted({alert["source_ip"] for alert in alerts if alert.get("source_ip")})
        destination_ips = Counter()
        destination_ports = Counter()
        alert_types = Counter()
        countries = Counter()
        reputation_distribution = Counter()
        total_events = 0
        for alert in alerts:
            alert_types[str(alert["alert_type"])] += 1
            if alert.get("country"):
                countries[str(alert["country"])] += 1
            reputation_distribution[summarize_reputation_bucket(alert.get("reputation_score"))] += 1
            snapshot = _coerce_target_snapshot(alert)
            total_events += snapshot["related_event_count"]
            for ip_value in snapshot["sample_destination_ips"]:
                destination_ips[str(ip_value)] += 1
            for port_value in snapshot["service_signature_ports"] or snapshot["sample_destination_ports"]:
                destination_ports[int(port_value)] += 1

        target_mode = classify_target_mode(len(destination_ips), len(destination_ports))
        primary_ports = [port for port, _count in destination_ports.most_common(5)]
        primary_ip = destination_ips.most_common(1)[0][0] if destination_ips else None
        primary_port = primary_ports[0] if primary_ports else None
        return {
            "underlying_alert_count": len(alerts),
            "underlying_event_count": total_events,
            "source_ip_count": len(source_ips),
            "destination_ip_count": len(destination_ips),
            "primary_destination_ports": primary_ports,
            "alert_types": sorted(alert_types),
            "countries": [{"value": value, "count": count} for value, count in countries.most_common(10)],
            "asns": [],
            "reputation_distribution": dict(reputation_distribution),
            "representative_sources": source_ips[:10],
            "representative_alert_ids": [int(alert["alert_id"]) for alert in alerts[:10]],
            "target_context": {
                "mode": target_mode,
                "primary_destination_ip": primary_ip,
                "primary_destination_port": primary_port,
                "sample_destination_ips": [value for value, _count in destination_ips.most_common(5)],
                "sample_destination_ports": primary_ports,
                "distinct_destination_count": len(destination_ips),
                "distinct_port_count": len(destination_ports),
                "related_event_count": total_events,
            },
        }


def _build_assessment_text(summary: dict[str, Any]) -> str:
    port_text = ", ".join(str(value) for value in summary.get("primary_destination_ports") or [])
    if port_text:
        return (
            "Distributed commodity scanning against public services. "
            f"Primary ports observed: {port_text}. Coordination is not established."
        )
    return "Distributed commodity scanning against public services. Coordination is not established."


def _update_activity_summary(conn, activity_id: int) -> None:
    summary = _aggregate_summary(conn, activity_id)
    severity = "high" if summary["source_ip_count"] >= 25 else "medium" if summary["source_ip_count"] >= 2 else "low"
    status = "open" if severity == "high" else "monitoring"
    assessment_text = _build_assessment_text(summary)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                MIN(a.created_at),
                MAX(a.created_at),
                COALESCE(MAX(i.id), NULL)
            FROM recon_activity_alerts ral
            JOIN alerts a ON a.id = ral.alert_id
            LEFT JOIN incident_alerts ia ON ia.alert_id = a.id
            LEFT JOIN incidents i ON i.id = ia.incident_id AND i.status IN ('open', 'investigating')
            WHERE ral.recon_activity_id = %s
            """,
            (activity_id,),
        )
        row = cur.fetchone() or (None, None, None)
        cur.execute(
            """
            UPDATE recon_activities
            SET
                severity = %s,
                status = %s,
                first_seen = COALESCE(%s, first_seen),
                last_seen = COALESCE(%s, last_seen),
                related_incident_id = %s,
                assessment_text = %s,
                summary = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            (
                severity,
                status,
                row[0],
                row[1],
                row[2],
                assessment_text,
                Json(summary),
                activity_id,
            ),
        )


def enroll_alert_in_recon_activity(conn, alert_id: int) -> dict[str, Any] | None:
    alert = fetch_alert_context(conn, alert_id)
    if alert is None:
        return None
    context = alert["context"]
    target_context = alert["target_context"]
    protected_range = context.get("protected_range_key")
    service_signature = build_service_signature(context.get("service_signature_ports") or target_context.get("sample_destination_ports") or [])
    if not protected_range or not service_signature:
        return None

    candidate_rows = _fetch_candidate_activities(
        conn,
        protected_range,
        target_context.get("first_seen") or context.get("first_seen"),
        target_context.get("last_seen") or context.get("last_seen"),
    )
    activity_id = _choose_activity_id(candidate_rows, service_signature)

    with conn.cursor() as cur:
        if activity_id is None:
            cur.execute(
                """
                INSERT INTO recon_activities (
                    activity_type,
                    source,
                    source_type,
                    status,
                    severity,
                    coordination_status,
                    protected_range_key,
                    service_signature,
                    first_seen,
                    last_seen,
                    assessment_text,
                    membership_evidence,
                    summary
                )
                VALUES (%s, %s, %s, 'monitoring', %s, 'not_established', %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    PFSENSE_RECON_ACTIVITY_TYPE,
                    alert["source"] or "pfsense",
                    alert["source_type"] or "firewall",
                    alert["severity"] if alert["severity"] in {"low", "medium", "high"} else "medium",
                    protected_range,
                    Json(service_signature),
                    target_context.get("first_seen") or context.get("first_seen"),
                    target_context.get("last_seen") or context.get("last_seen"),
                    "Distributed commodity scanning against public services. Coordination is not established.",
                    Json(
                        {
                            "protected_range_key": protected_range,
                            "service_signature_ports": service_signature,
                            "compatible_alert_types": [alert["alert_type"]],
                        }
                    ),
                    Json({}),
                ),
            )
            activity_id = int(cur.fetchone()[0])

        cur.execute(
            """
            INSERT INTO recon_activity_alerts (
                recon_activity_id,
                alert_id,
                member_role,
                source_ip,
                first_seen,
                last_seen,
                membership_evidence
            )
            VALUES (%s, %s, 'primary', %s::inet, %s, %s, %s)
            ON CONFLICT (alert_id) DO NOTHING
            """,
            (
                activity_id,
                alert_id,
                alert["source_ip"],
                target_context.get("first_seen") or context.get("first_seen"),
                target_context.get("last_seen") or context.get("last_seen"),
                Json(
                    {
                        "protected_range_key": protected_range,
                        "service_signature_ports": service_signature,
                        "target_mode": target_context.get("mode"),
                    }
                ),
            ),
        )
        cur.execute(
            """
            UPDATE alerts
            SET context = jsonb_set(
                jsonb_set(
                    context,
                    '{recon_activity}',
                    %s::jsonb,
                    true
                ),
                '{notification_policy,immediate_alert_eligible}',
                'false'::jsonb,
                true
            )
            WHERE id = %s
            """,
            (
                Json(
                    {
                        "id": activity_id,
                        "label": PFSENSE_RECON_ACTIVITY_LABEL,
                        "activity_type": PFSENSE_RECON_ACTIVITY_TYPE,
                        "coordination_status": "not_established",
                    }
                ),
                alert_id,
            ),
        )

    _update_activity_summary(conn, activity_id)
    return get_recon_activity_detail(conn, activity_id)


def list_recon_activities(conn, *, limit: int = 20, status: str | None = None) -> list[dict[str, Any]]:
    params: list[Any] = []
    clauses = ["activity_type = %s"]
    params.append(PFSENSE_RECON_ACTIVITY_TYPE)
    if status:
        clauses.append("status = %s")
        params.append(status)
    params.append(max(1, min(int(limit), 100)))
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
                id,
                activity_type,
                source,
                source_type,
                status,
                severity,
                coordination_status,
                protected_range_key,
                first_seen,
                last_seen,
                assessment_text,
                summary,
                related_incident_id,
                created_at,
                updated_at,
                resolved_at
            FROM recon_activities
            WHERE {' AND '.join(clauses)}
            ORDER BY last_seen DESC, id DESC
            LIMIT %s
            """,
            params,
        )
        rows = cur.fetchall()
    return [_serialize_recon_activity_row(row) for row in rows]


def get_recon_activity_detail(conn, activity_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                id,
                activity_type,
                source,
                source_type,
                status,
                severity,
                coordination_status,
                protected_range_key,
                first_seen,
                last_seen,
                assessment_text,
                summary,
                related_incident_id,
                created_at,
                updated_at,
                resolved_at
            FROM recon_activities
            WHERE id = %s
            """,
            (activity_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        payload = _serialize_recon_activity_row(row)
        cur.execute(
            """
            SELECT
                a.id,
                a.alert_type,
                a.severity,
                host(a.source_ip),
                a.message,
                a.created_at,
                a.country,
                a.reputation_score,
                a.context
            FROM recon_activity_alerts ral
            JOIN alerts a ON a.id = ral.alert_id
            WHERE ral.recon_activity_id = %s
            ORDER BY a.created_at DESC, a.id DESC
            LIMIT 25
            """,
            (activity_id,),
        )
        payload["alerts"] = [
            {
                "id": int(item[0]),
                "alert_type": item[1],
                "severity": item[2],
                "source_ip": item[3],
                "message": item[4],
                "created_at": item[5].isoformat() if item[5] else None,
                "country": item[6],
                "reputation_score": item[7],
                "target_context": item[8].get("target_context") if isinstance(item[8], dict) else {},
            }
            for item in cur.fetchall()
        ]
        return payload


def _serialize_recon_activity_row(row) -> dict[str, Any]:
    summary = row[11] if isinstance(row[11], dict) else {}
    return {
        "id": int(row[0]),
        "label": PFSENSE_RECON_ACTIVITY_LABEL,
        "activity_type": row[1],
        "source": row[2],
        "source_type": row[3],
        "status": row[4],
        "severity": row[5],
        "coordination_status": row[6],
        "protected_range_key": row[7],
        "first_seen": row[8].isoformat() if row[8] else None,
        "last_seen": row[9].isoformat() if row[9] else None,
        "assessment_text": row[10],
        "summary": summary,
        "related_incident_id": row[12],
        "created_at": row[13].isoformat() if row[13] else None,
        "updated_at": row[14].isoformat() if row[14] else None,
        "resolved_at": row[15].isoformat() if row[15] else None,
    }


def fetch_recon_activity_notification_state(conn, activity_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                id,
                severity,
                status,
                coordination_status,
                source,
                source_type,
                assessment_text,
                summary,
                opened_notification_sent_at,
                last_notified_fingerprint,
                last_notified_at
            FROM recon_activities
            WHERE id = %s
            """,
            (activity_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
    summary = row[7] if isinstance(row[7], dict) else {}
    return {
        "id": int(row[0]),
        "severity": row[1],
        "status": row[2],
        "coordination_status": row[3],
        "source": row[4],
        "source_type": row[5],
        "assessment_text": row[6],
        "summary": summary,
        "opened_notification_sent_at": row[8],
        "last_notified_fingerprint": row[9],
        "last_notified_at": row[10],
    }


def record_recon_activity_notification(
    conn,
    activity_id: int,
    *,
    fingerprint: str,
    opened_at: datetime | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE recon_activities
            SET
                opened_notification_sent_at = COALESCE(opened_notification_sent_at, %s),
                last_notified_fingerprint = %s,
                last_notified_at = COALESCE(%s, NOW()),
                updated_at = NOW()
            WHERE id = %s
            """,
            (
                opened_at,
                fingerprint,
                opened_at,
                activity_id,
            ),
        )
