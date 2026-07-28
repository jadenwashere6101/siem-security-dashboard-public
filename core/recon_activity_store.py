from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from psycopg2.extras import Json

from core.investigation_intelligence import (
    build_campaign_intelligence,
    build_investigation_value,
)
from core.pfsense_recon import (
    PFSENSE_RECON_ACTIVITY_LABEL,
    PFSENSE_RECON_ACTIVITY_TYPE,
    build_service_signature,
    classify_target_mode,
    summarize_reputation_bucket,
)

VPN_PORTS = frozenset({500, 1194, 1197, 1701, 4500, 51820})
VALID_RECON_CLASSIFICATIONS = frozenset(
    {"recon_candidate", "recon_cluster", "possible_campaign", "campaign_recon"}
)
VALID_RECON_CONFIDENCE_LEVELS = frozenset({"low", "medium", "high"})
VALID_RECON_SORT_OPTIONS = frozenset({"last_seen_desc", "last_seen_asc", "first_seen_desc", "severity_desc"})
MAX_RECON_PAGE_SIZE = 100


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
            "distinct_service_count": len(destination_ports),
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


def _format_service_label(port_value: Any) -> str | None:
    try:
        port = int(port_value)
    except (TypeError, ValueError):
        return None
    if port in VPN_PORTS:
        return f"VPN service ({port})"
    return f"Port {port}"


def _build_coordination_assessment(summary: dict[str, Any], coordination_status: str | None) -> dict[str, Any]:
    status = str(coordination_status or "not_established").lower()
    if status == "supported":
        label = "Campaign evidence present"
    elif status == "possible":
        label = "Coordination may be developing"
    else:
        label = "Coordination not established"

    reasons: list[dict[str, str]] = []
    if int(summary.get("destination_ip_count") or 0) > 0:
        reasons.append({"id": "target", "text": "The same target range was observed"})
    if int(summary.get("distinct_service_count") or 0) > 0:
        reasons.append({"id": "service", "text": "The same service pattern was observed"})
    if status == "not_established":
        reasons.append({"id": "timing", "text": "Timing evidence is not strong enough yet"})
    if not reasons:
        reasons.append({"id": "limited", "text": "Only limited recon evidence is available"})
    return {"label": label, "reasons": reasons[:3]}


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _duration_minutes(first_seen: Any, last_seen: Any) -> float:
    first = _parse_datetime(first_seen)
    last = _parse_datetime(last_seen)
    if not first or not last:
        return 0.0
    if first.tzinfo is None:
        first = first.replace(tzinfo=timezone.utc)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return max((last - first).total_seconds() / 60.0, 0.0)


def build_recon_intelligence_projection(
    *,
    summary: dict[str, Any],
    coordination_status: str | None,
    related_incident_id: Any,
    first_seen: Any,
    last_seen: Any,
) -> dict[str, Any]:
    alert_count = int(summary.get("underlying_alert_count") or 0)
    source_count = int(summary.get("source_ip_count") or 0)
    destination_count = int(summary.get("destination_ip_count") or 0)
    service_count = int(summary.get("distinct_service_count") or 0)
    alert_type_count = len(summary.get("alert_types") or [])
    duration_minutes = _duration_minutes(first_seen, last_seen)
    has_incident = related_incident_id is not None
    progression_observed = bool(summary.get("progression_observed"))
    coordination_supported = str(coordination_status or "").lower() == "supported"

    reasons: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    score = 0

    if alert_count >= 3:
        score += 2
        reasons.append({"id": "linked_alert_volume", "text": f"{alert_count} linked recon alerts"})
    elif alert_count >= 2:
        score += 1
        reasons.append({"id": "linked_alert_volume", "text": "Multiple linked recon alerts"})
    else:
        missing.append({"id": "linked_alert_volume", "text": "Only one linked alert is present"})

    if source_count >= 3:
        score += 2
        reasons.append({"id": "source_diversity", "text": f"{source_count} contributing sources"})
    elif source_count >= 2:
        score += 1
        reasons.append({"id": "source_diversity", "text": "More than one source contributed"})
    else:
        missing.append({"id": "source_diversity", "text": "Only one source is present"})

    if duration_minutes >= 30:
        score += 1
        reasons.append({"id": "temporal_depth", "text": "Activity spans at least 30 minutes"})
    else:
        missing.append({"id": "temporal_depth", "text": "Activity duration is short"})

    if destination_count > 0 and service_count > 0 and alert_count >= 2:
        score += 1
        reasons.append({"id": "target_service_consistency", "text": "Linked alerts share target or service evidence"})
    else:
        missing.append({"id": "target_service_consistency", "text": "Target/service consistency is limited"})

    if alert_type_count >= 2:
        score += 1
        reasons.append({"id": "alert_type_diversity", "text": "Multiple recon detection types contributed"})
    else:
        missing.append({"id": "alert_type_diversity", "text": "Only one detection type contributed"})

    if has_incident:
        score += 2
        reasons.append({"id": "incident_correlation", "text": "Recon is linked to an active incident"})
    else:
        missing.append({"id": "incident_correlation", "text": "No active incident correlation is present"})

    if progression_observed or coordination_supported:
        score += 2
        reasons.append({"id": "progression", "text": "Progression or supported coordination evidence is present"})
    else:
        missing.append({"id": "progression", "text": "No progression evidence is present"})

    evidence_categories = len(reasons)
    weak_singleton = (
        alert_count <= 1
        and source_count <= 1
        and duration_minutes < 30
        and not has_incident
        and not progression_observed
        and not coordination_supported
    )
    if weak_singleton:
        classification = "recon_candidate"
        confidence = "low"
    elif score >= 7 and evidence_categories >= 3 and (has_incident or progression_observed or coordination_supported or source_count >= 3):
        classification = "campaign_recon"
        confidence = "high"
    elif score >= 4 and evidence_categories >= 2:
        classification = "possible_campaign"
        confidence = "medium"
    else:
        classification = "recon_cluster"
        confidence = "low"

    return {
        "classification": classification,
        "confidence": confidence,
        "primary_view_visible": classification != "recon_candidate",
        "score": score,
        "reasons": reasons[:5],
        "missing_evidence": missing[:5],
        "duration_minutes": round(duration_minutes, 1),
    }


def _build_recon_story(
    summary: dict[str, Any],
    campaign_intelligence: dict[str, Any],
    investigation_value: dict[str, Any],
    recon_intelligence: dict[str, Any],
) -> dict[str, str]:
    primary_port = ((summary.get("primary_destination_ports") or [None]) or [None])[0]
    service_label = _format_service_label(primary_port)
    source_count = int(summary.get("source_ip_count") or 0)

    classification = recon_intelligence.get("classification")
    if classification == "campaign_recon" and service_label and "VPN" in service_label:
        headline = "Campaign-grade VPN recon"
    elif classification == "campaign_recon":
        headline = "Campaign-grade recon"
    elif classification == "possible_campaign":
        headline = "Possible recon campaign"
    elif classification == "recon_candidate":
        headline = "Recon candidate"
    elif source_count > 1 and service_label and "VPN" in service_label:
        headline = "VPN recon cluster"
    elif source_count > 1:
        headline = "Recon cluster"
    else:
        headline = "Source-specific recon"

    disposition = (
        "Investigation recommended"
        if investigation_value.get("level") == "high"
        else "Review soon"
        if investigation_value.get("level") == "medium"
        else "No immediate investigation recommended"
    )
    return {
        "headline": headline,
        "disposition": disposition,
    }


def _build_display_projection(
    *,
    summary: dict[str, Any],
    protected_range_key: str | None,
    status: str | None,
    last_seen: datetime | None,
    related_incident_id: Any,
    investigation_value: dict[str, Any],
    coordination_assessment: dict[str, Any],
    story: dict[str, Any],
    recon_intelligence: dict[str, Any],
) -> dict[str, Any]:
    target_context = summary.get("target_context") if isinstance(summary.get("target_context"), dict) else {}
    primary_target = target_context.get("primary_destination_ip") or protected_range_key
    representative_sources = list(summary.get("representative_sources") or [])
    representative_source = representative_sources[0] if representative_sources else None
    source_count = int(summary.get("source_ip_count") or 0)
    destination_count = int(summary.get("destination_ip_count") or 0)
    alert_count = int(summary.get("underlying_alert_count") or 0)
    primary_port = target_context.get("primary_destination_port")
    primary_service = _format_service_label(primary_port)
    if primary_service is None:
        primary_ports = summary.get("primary_destination_ports") or []
        if primary_ports:
            primary_service = ", ".join(filter(None, (_format_service_label(value) for value in primary_ports[:2])))

    target_summary = primary_target or "Target unavailable"
    if protected_range_key and primary_target and primary_target != protected_range_key:
        target_summary = f"{primary_target} ({protected_range_key})"

    primary_view_visible = bool(recon_intelligence.get("primary_view_visible"))
    scope_bits: list[str] = []
    if source_count > 0:
        scope_bits.append(f"{source_count} source" if source_count == 1 else f"{source_count} sources")
    if destination_count > 0:
        scope_bits.append(
            f"{destination_count} destination" if destination_count == 1 else f"{destination_count} destinations"
        )
    scope_summary = " • ".join(scope_bits)

    version_parts = [
        str(status or ""),
        str(related_incident_id or ""),
        str(investigation_value.get("level") or ""),
        str(target_summary),
        str(primary_service or ""),
        str(alert_count),
        str(last_seen.isoformat() if last_seen else ""),
    ]
    return {
        "headline": story.get("headline") or "Recon activity",
        "target_summary": target_summary,
        "primary_target": primary_target,
        "representative_source": representative_source,
        "additional_source_count": max(source_count - 1, 0) if representative_source else source_count,
        "primary_service": primary_service,
        "scope_summary": scope_summary,
        "linked_alert_count": alert_count,
        "status_label": str(status or "").replace("_", " ").title(),
        "investigation_label": investigation_value.get("label") or "Monitor",
        "coordination_label": coordination_assessment.get("label") or "Current assessment unavailable",
        "classification": recon_intelligence.get("classification") or "recon_cluster",
        "confidence": recon_intelligence.get("confidence") or "low",
        "stage": recon_intelligence.get("classification") or "recon_cluster",
        "primary_view_visible": primary_view_visible,
        "visibility_label": "Primary view" if primary_view_visible else "Evidence pivot only",
        "action_recommendation": story.get("disposition") or "No immediate investigation recommended",
        "review_state_version": "|".join(version_parts),
    }


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
                COALESCE(MAX(i.id), NULL),
                MAX(ra.coordination_status)
            FROM recon_activity_alerts ral
            JOIN recon_activities ra ON ra.id = ral.recon_activity_id
            JOIN alerts a ON a.id = ral.alert_id
            LEFT JOIN incident_alerts ia ON ia.alert_id = a.id
            LEFT JOIN incidents i ON i.id = ia.incident_id AND i.status IN ('open', 'investigating')
            WHERE ral.recon_activity_id = %s
            """,
            (activity_id,),
        )
        row = cur.fetchone() or (None, None, None)
        summary["progression_observed"] = bool(summary.get("progression_observed"))
        summary["recon_intelligence"] = build_recon_intelligence_projection(
            summary=summary,
            coordination_status=row[3],
            related_incident_id=row[2],
            first_seen=row[0],
            last_seen=row[1],
        )
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


def _normalize_recon_limit(limit: int | None) -> int:
    return max(1, min(int(limit or 20), MAX_RECON_PAGE_SIZE))


def _normalize_recon_offset(offset: int | None) -> int:
    return max(0, int(offset or 0))


def _sort_clause(sort: str | None) -> str:
    if sort == "last_seen_asc":
        return "last_seen ASC NULLS LAST, id ASC"
    if sort == "first_seen_desc":
        return "first_seen DESC NULLS LAST, id DESC"
    if sort == "severity_desc":
        return """
            CASE severity
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
                ELSE 4
            END,
            last_seen DESC NULLS LAST,
            id DESC
        """
    return "last_seen DESC NULLS LAST, id DESC"


def list_recon_activities(
    conn,
    *,
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
    severity: str | None = None,
    confidence: str | None = None,
    classification: str | None = None,
    search: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    sort: str | None = None,
) -> dict[str, Any]:
    normalized_limit = _normalize_recon_limit(limit)
    normalized_offset = _normalize_recon_offset(offset)
    normalized_sort = sort if sort in VALID_RECON_SORT_OPTIONS else "last_seen_desc"
    params: list[Any] = []
    clauses = ["activity_type = %s"]
    params.append(PFSENSE_RECON_ACTIVITY_TYPE)
    if status:
        clauses.append("status = %s")
        params.append(status)
    if severity:
        clauses.append("severity = %s")
        params.append(severity)
    if start_time:
        clauses.append("last_seen >= %s::timestamptz")
        params.append(start_time)
    if end_time:
        clauses.append("first_seen <= %s::timestamptz")
        params.append(end_time)
    if search:
        clauses.append(
            """
            (
                protected_range_key ILIKE %s
                OR assessment_text ILIKE %s
                OR source ILIKE %s
                OR source_type ILIKE %s
                OR summary::text ILIKE %s
            )
            """
        )
        search_value = f"%{search}%"
        params.extend([search_value, search_value, search_value, search_value, search_value])

    hide_candidates_from_primary = not search and not classification
    needs_projection_filter = bool(confidence or classification or hide_candidates_from_primary)
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
            ORDER BY {_sort_clause(normalized_sort)}
            {'' if needs_projection_filter else 'LIMIT %s OFFSET %s'}
            """,
            params if needs_projection_filter else [*params, normalized_limit, normalized_offset],
        )
        rows = cur.fetchall()

        if needs_projection_filter:
            serialized = [_serialize_recon_activity_row(row) for row in rows]
            if hide_candidates_from_primary:
                serialized = [
                    item
                    for item in serialized
                    if item.get("recon_intelligence", {}).get("classification") != "recon_candidate"
                ]
            if confidence:
                serialized = [item for item in serialized if item.get("recon_intelligence", {}).get("confidence") == confidence]
            if classification:
                serialized = [
                    item
                    for item in serialized
                    if item.get("recon_intelligence", {}).get("classification") == classification
                ]
            total = len(serialized)
            items = serialized[normalized_offset : normalized_offset + normalized_limit]
        else:
            items = [_serialize_recon_activity_row(row) for row in rows]
            cur.execute(
                f"""
                SELECT COUNT(*)
                FROM recon_activities
                WHERE {' AND '.join(clauses)}
                """,
                params,
            )
            total = int(cur.fetchone()[0] or 0)
    return {
        "items": items,
        "count": len(items),
        "total": total,
        "limit": normalized_limit,
        "offset": normalized_offset,
        "sort": normalized_sort,
        "filters": {
            "status": status,
            "severity": severity,
            "confidence": confidence,
            "classification": classification,
            "search": search,
            "start_time": start_time,
            "end_time": end_time,
        },
    }


def list_recon_activity_alerts(
    conn,
    activity_id: int,
    *,
    limit: int = 20,
    offset: int = 0,
    sort: str | None = None,
) -> dict[str, Any]:
    normalized_limit = _normalize_recon_limit(limit)
    normalized_offset = _normalize_recon_offset(offset)
    order_clause = "a.created_at ASC, a.id ASC" if sort == "oldest" else "a.created_at DESC, a.id DESC"
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM recon_activity_alerts
            WHERE recon_activity_id = %s
            """,
            (activity_id,),
        )
        total = int(cur.fetchone()[0] or 0)
        cur.execute(
            f"""
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
            ORDER BY {order_clause}
            LIMIT %s OFFSET %s
            """,
            (activity_id, normalized_limit, normalized_offset),
        )
        rows = cur.fetchall()
    return {
        "activity_id": activity_id,
        "items": [_serialize_recon_activity_alert_row(row) for row in rows],
        "count": len(rows),
        "total": total,
        "limit": normalized_limit,
        "offset": normalized_offset,
        "sort": "oldest" if sort == "oldest" else "newest",
    }


def _serialize_recon_activity_alert_row(row) -> dict[str, Any]:
    return {
        "id": int(row[0]),
        "alert_type": row[1],
        "severity": row[2],
        "source_ip": row[3],
        "message": row[4],
        "created_at": row[5].isoformat() if row[5] else None,
        "country": row[6],
        "reputation_score": row[7],
        "target_context": row[8].get("target_context") if isinstance(row[8], dict) else {},
    }


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
        linked_alerts = list_recon_activity_alerts(conn, activity_id, limit=10, offset=0)
        payload["alerts"] = linked_alerts["items"]
        payload["alerts_total"] = linked_alerts["total"]
        payload["alerts_limit"] = linked_alerts["limit"]
        payload["alerts_offset"] = linked_alerts["offset"]
        return payload


def _serialize_recon_activity_row(row) -> dict[str, Any]:
    summary = row[11] if isinstance(row[11], dict) else {}
    campaign_intelligence = build_campaign_intelligence(
        {
            "first_seen": row[8].isoformat() if row[8] else None,
            "last_seen": row[9].isoformat() if row[9] else None,
            "days_active": 0,
            "source_count": int(summary.get("source_ip_count") or 0),
            "destination_count": int(summary.get("destination_ip_count") or 0),
            "service_count": int(summary.get("distinct_service_count") or 0),
            "corroborating_alert_types": len(summary.get("alert_types") or []),
            "progression_observed": False,
            "relationship": f"Coordination status: {str(row[6] or 'not_established').replace('_', ' ')}",
        }
    )
    investigation_value = build_investigation_value(
        severity=row[5],
        campaign_intelligence=campaign_intelligence,
        progression_observed=False,
        corroborating_detection_count=len(summary.get("alert_types") or []),
        repeated_destination=int(summary.get("destination_ip_count") or 0) > 0,
        persistent_activity=int(summary.get("source_ip_count") or 0) > 1,
    )
    coordination_assessment = _build_coordination_assessment(summary, row[6])
    recon_intelligence = build_recon_intelligence_projection(
        summary=summary,
        coordination_status=row[6],
        related_incident_id=row[12],
        first_seen=row[8],
        last_seen=row[9],
    )
    story = _build_recon_story(summary, campaign_intelligence, investigation_value, recon_intelligence)
    display = _build_display_projection(
        summary=summary,
        protected_range_key=row[7],
        status=row[4],
        last_seen=row[9],
        related_incident_id=row[12],
        investigation_value=investigation_value,
        coordination_assessment=coordination_assessment,
        story=story,
        recon_intelligence=recon_intelligence,
    )
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
        "campaign_intelligence": campaign_intelligence,
        "recon_intelligence": recon_intelligence,
        "investigation_value": investigation_value,
        "story": story,
        "coordination_assessment": coordination_assessment,
        "display": display,
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
