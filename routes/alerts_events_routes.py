from __future__ import annotations

import ipaddress
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import Blueprint, current_app, jsonify, request
from flask_login import login_required

from core.auth import admin_required, analyst_or_super_admin_required
from core.db import get_db_connection
from core.investigation_intelligence import (
    build_campaign_intelligence,
    build_investigation_value,
    build_port_scan_story,
    build_returning_attacker_context,
)
from core.pfsense_operational_baseline import (
    build_alert_operational_history,
    build_pfsense_alert_baseline_filter,
    normalize_operational_scope,
)
from core.recon_activity_store import get_recon_activity_detail, list_recon_activities
from core.soar_response_outcomes import (
    build_latest_outcome_api_shape,
    get_latest_decisions_for_alerts_bulk,
    get_latest_outcomes_for_alerts_bulk,
    serialize_latest_outcome,
)
from helpers.enrichment_helpers import enrich_alert_with_correlation_context, enrich_alert_with_mitre
from core.ip_helpers import determine_response_action, get_ip_reputation, lookup_ip_reputation
from core.source_inventory import CANONICAL_SOURCE_IDS
from engines.detection_config import PFSENSE_ALERT_COOLDOWN_MINUTES, get_detection_rule_defaults


alerts_events_bp = Blueprint("alerts_events", __name__)

VALID_EVENT_TYPES = {"failed_login", "login_failure", "successful_login", "port_scan", "normal_activity"}
VALID_EVENT_SEARCH_TYPES = VALID_EVENT_TYPES | {
    "unauthorized_access",
    "http_error",
    "application_exception",
    "availability_failure",
}
VALID_EVENT_SOURCES = CANONICAL_SOURCE_IDS
PFSENSE_ALERT_TYPES = frozenset(
    {
        "pfsense_firewall_repeated_deny",
        "pfsense_firewall_port_scan",
        "pfsense_firewall_suspicious_allow",
        "pfsense_firewall_noisy_source",
        "pfsense_firewall_allow_after_deny",
    }
)
PFSENSE_WHY_FIRED_LABELS = {
    "action": "Firewall action",
    "direction": "Traffic direction",
    "event_count": "Matching events",
    "destination_ip": "Destination IP",
    "destination_port": "Destination port",
    "source_port": "Source port",
    "tcp_flags": "TCP flags",
    "protocol": "Protocol",
    "interface": "Interface",
    "distinct_port_count": "Distinct destination ports",
    "distinct_destination_count": "Distinct destination hosts",
    "distinct_sensitive_port_count": "Distinct sensitive ports",
    "scan_description": "Scan description",
    "traffic_role": "Traffic role",
    "traffic_role_reason": "Traffic role assessment",
    "first_seen": "First seen",
    "last_seen": "Last seen",
}
DEFAULT_ALERT_LIMIT = 50
MAX_ALERT_LIMIT = 100
VALID_ALERT_SORT_OPTIONS = frozenset({"newest", "oldest", "severity"})
VALID_ALERT_SOURCE_FILTERS = VALID_EVENT_SOURCES | {"legacy"}
ALERT_TIMELINE_RANGES = {
    "24h": {"hours": 24, "bucket": "hour"},
    "7d": {"days": 7, "bucket": "6 hours"},
    "30d": {"days": 30, "bucket": "day"},
    "90d": {"days": 90, "bucket": "day"},
}
DEFAULT_ALERT_TIMELINE_RANGE = "7d"

_ALERT_SELECT = """
    SELECT
        id,
        alert_type,
        severity,
        message,
        source_ip,
        created_at,
        status,
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
        source,
        source_type,
        context
    FROM alerts
"""


def _parse_non_negative_int(value, default, field_name):
    if value is None:
        return default, None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None, f"invalid {field_name}"
    if parsed < 0:
        return None, f"invalid {field_name}"
    return parsed, None


def _normalize_alert_filter_value(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "all":
        return None
    return text


def _normalize_ip_filter_value(value):
    normalized = _normalize_alert_filter_value(value)
    if normalized is None:
        return None
    try:
        return str(ipaddress.ip_address(normalized))
    except ValueError:
        raise ValueError("invalid IP filter")


def _parse_alert_list_request_args(include_pagination: bool = False):
    search = _normalize_alert_filter_value(request.args.get("search"))
    try:
        exact_source_ip = _normalize_ip_filter_value(request.args.get("exact_source_ip"))
        exact_target_ip = _normalize_ip_filter_value(request.args.get("exact_target_ip"))
    except ValueError:
        return None, (jsonify({"error": "invalid IP filter"}), 400)
    severity = _normalize_alert_filter_value(request.args.get("severity"))
    if severity is not None:
        severity = severity.lower()

    status = _normalize_alert_filter_value(request.args.get("status"))
    if status is not None:
        status = status.lower()

    source = _normalize_alert_filter_value(request.args.get("source"))
    if source is not None and source not in VALID_ALERT_SOURCE_FILTERS:
        return None, (jsonify({"error": "invalid source filter"}), 400)

    sort = _normalize_alert_filter_value(request.args.get("sort")) or "newest"
    if sort not in VALID_ALERT_SORT_OPTIONS:
        return None, (jsonify({"error": "invalid sort option"}), 400)
    try:
        operational_scope = normalize_operational_scope(request.args.get("operational_scope"))
    except ValueError:
        return None, (jsonify({"error": "invalid operational scope"}), 400)
    alert_id, alert_id_error = _parse_non_negative_int(
        request.args.get("alert_id"),
        None,
        "alert_id",
    )
    if alert_id_error:
        return None, (jsonify({"error": alert_id_error}), 400)

    args = {
        "search": search,
        "exact_source_ip": exact_source_ip,
        "exact_target_ip": exact_target_ip,
        "alert_id": alert_id,
        "severity": severity,
        "status": status,
        "source": source,
        "sort": sort,
        "operational_scope": operational_scope,
    }

    timeline_range = _normalize_alert_filter_value(request.args.get("timeline_range")) or DEFAULT_ALERT_TIMELINE_RANGE
    if timeline_range not in ALERT_TIMELINE_RANGES:
        return None, (jsonify({"error": "invalid timeline_range"}), 400)
    args["timeline_range"] = timeline_range

    if include_pagination:
        limit, limit_error = _parse_non_negative_int(
            request.args.get("limit"),
            DEFAULT_ALERT_LIMIT,
            "limit",
        )
        if limit_error:
            return None, (jsonify({"error": limit_error}), 400)
        limit = max(1, min(limit, MAX_ALERT_LIMIT))

        offset, offset_error = _parse_non_negative_int(
            request.args.get("offset"),
            0,
            "offset",
        )
        if offset_error:
            return None, (jsonify({"error": offset_error}), 400)

        args["limit"] = limit
        args["offset"] = offset

    return args, None


def _build_alert_filter_sql(filters: dict):
    clauses = []
    params = []

    if filters.get("search"):
        pattern = f"%{filters['search']}%"
        clauses.append("(host(source_ip) ILIKE %s OR message ILIKE %s)")
        params.extend((pattern, pattern))

    if filters.get("exact_source_ip"):
        clauses.append("host(source_ip) = %s")
        params.append(filters["exact_source_ip"])

    if filters.get("exact_target_ip"):
        clauses.append(
            """
            (
                COALESCE(context->'target_context'->>'primary_destination_ip', '') = %s
                OR COALESCE(context->'target_context'->>'destination_ip', '') = %s
                OR COALESCE(context->'target_context'->>'top_destination_ip', '') = %s
                OR EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements_text(
                        COALESCE(context->'target_context'->'sample_destination_ips', '[]'::jsonb)
                    ) AS sample_destination_ip(value)
                    WHERE sample_destination_ip.value = %s
                )
            )
            """
        )
        params.extend(
            (
                filters["exact_target_ip"],
                filters["exact_target_ip"],
                filters["exact_target_ip"],
                filters["exact_target_ip"],
            )
        )

    if filters.get("alert_id") is not None:
        clauses.append("id = %s")
        params.append(filters["alert_id"])

    if filters.get("severity"):
        clauses.append("severity = %s")
        params.append(filters["severity"])

    if filters.get("status"):
        clauses.append("status = %s")
        params.append(filters["status"])

    if filters.get("source"):
        clauses.append("COALESCE(source, 'legacy') = %s")
        params.append(filters["source"])

    operational_clause, operational_params = build_pfsense_alert_baseline_filter(
        filters.get("operational_scope") or "all_history"
    )
    if operational_clause:
        clauses.append(operational_clause)
        params.extend(operational_params)

    return clauses, params


def _build_alert_order_clause(sort: str) -> str:
    if sort == "oldest":
        return "ORDER BY created_at ASC, id ASC"
    if sort == "severity":
        return """
            ORDER BY
                CASE severity
                    WHEN 'critical' THEN 0
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    WHEN 'low' THEN 3
                    ELSE 4
                END ASC,
                created_at DESC,
                id DESC
        """
    return "ORDER BY created_at DESC, id DESC"


def _build_alerts_where_clause(clauses: list[str]) -> str:
    if not clauses:
        return ""
    return " WHERE " + " AND ".join(clauses)


def _fetch_alert_rows(cur, where_clause: str, order_clause: str, params: list, *, limit: int, offset: int):
    query = f"{_ALERT_SELECT}{where_clause} {order_clause} LIMIT %s OFFSET %s"
    cur.execute(query, (*params, limit, offset))
    return cur.fetchall()


def _fetch_alert_total(cur, where_clause: str, params: list):
    cur.execute(f"SELECT COUNT(*) FROM alerts{where_clause}", tuple(params))
    row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def _fetch_alert_summary_metrics(cur, where_clause: str, params: list):
    cur.execute(
        f"""
        SELECT
            COUNT(*) AS total_alerts,
            COUNT(*) FILTER (WHERE severity = 'high') AS high_count,
            COUNT(*) FILTER (WHERE severity = 'medium') AS medium_count,
            COUNT(*) FILTER (WHERE severity = 'low') AS low_count,
            COUNT(DISTINCT host(source_ip)) FILTER (WHERE source_ip IS NOT NULL) AS unique_source_ips
        FROM alerts
        {where_clause}
        """,
        tuple(params),
    )
    row = cur.fetchone() or (0, 0, 0, 0, 0)
    return {
        "total_alerts": int(row[0] or 0),
        "high_count": int(row[1] or 0),
        "medium_count": int(row[2] or 0),
        "low_count": int(row[3] or 0),
        "unique_source_ips": int(row[4] or 0),
    }


def _fetch_top_source_ips(cur, where_clause: str, params: list):
    cur.execute(
        f"""
        SELECT host(source_ip) AS source_ip, COUNT(*) AS alert_count
        FROM alerts
        {where_clause}
        AND source_ip IS NOT NULL
        GROUP BY host(source_ip)
        ORDER BY alert_count DESC, source_ip ASC
        LIMIT 5
        """
        if where_clause
        else """
        SELECT host(source_ip) AS source_ip, COUNT(*) AS alert_count
        FROM alerts
        WHERE source_ip IS NOT NULL
        GROUP BY host(source_ip)
        ORDER BY alert_count DESC, source_ip ASC
        LIMIT 5
        """,
        tuple(params),
    )
    return [{"name": row[0], "value": int(row[1] or 0)} for row in cur.fetchall()]


def _resolve_timeline_window_start(timeline_range: str) -> datetime:
    range_meta = ALERT_TIMELINE_RANGES.get(
        timeline_range,
        ALERT_TIMELINE_RANGES[DEFAULT_ALERT_TIMELINE_RANGE],
    )
    now = datetime.now(timezone.utc)
    if range_meta.get("hours"):
        return now - timedelta(hours=int(range_meta["hours"]))
    return now - timedelta(days=int(range_meta["days"]))


def _fetch_alert_timeline(cur, where_clause: str, params: list, timeline_range: str):
    range_meta = ALERT_TIMELINE_RANGES.get(
        timeline_range,
        ALERT_TIMELINE_RANGES[DEFAULT_ALERT_TIMELINE_RANGE],
    )
    bucket = range_meta["bucket"]
    window_start = _resolve_timeline_window_start(timeline_range)
    timeline_where = (
        f"{where_clause} AND created_at >= %s"
        if where_clause
        else " WHERE created_at >= %s"
    )
    timeline_params = [*params, window_start]
    if bucket == "6 hours":
        bucket_sql = """
            date_trunc('day', created_at AT TIME ZONE 'UTC')
            + floor(extract(hour from created_at AT TIME ZONE 'UTC') / 6) * interval '6 hours'
        """
    elif bucket == "day":
        bucket_sql = "date_trunc('day', created_at AT TIME ZONE 'UTC')"
    else:
        bucket_sql = "date_trunc('hour', created_at AT TIME ZONE 'UTC')"
    cur.execute(
        f"""
        SELECT
            ({bucket_sql}) AT TIME ZONE 'UTC' AS bucket_start,
            COUNT(*) AS alert_count
        FROM alerts
        {timeline_where}
        GROUP BY bucket_start
        ORDER BY bucket_start ASC
        """,
        tuple(timeline_params),
    )
    return {
        "range": timeline_range,
        "bucket": bucket,
        "window_start": window_start.isoformat(),
        "points": [
            {
                "bucketStart": int(
                    row[0].replace(tzinfo=timezone.utc).timestamp() * 1000
                )
                if row[0].tzinfo is None
                else int(row[0].astimezone(timezone.utc).timestamp() * 1000),
                "count": int(row[1] or 0),
            }
            for row in cur.fetchall()
        ],
    }


def _load_synthetic_source_ip_exclusions() -> set[str]:
    raw_value = (
        os.getenv("SIEM_SYNTHETIC_SOURCE_IP_EXCLUSIONS")
        or os.getenv("SYNTHETIC_SOURCE_IP_EXCLUSIONS")
        or ""
    )
    exclusions: set[str] = set()
    for part in raw_value.split(","):
        normalized = part.strip()
        if not normalized:
            continue
        try:
            exclusions.add(str(ipaddress.ip_address(normalized)))
        except ValueError:
            current_app.logger.warning(
                "Ignoring invalid synthetic source IP exclusion: %s",
                normalized,
            )
    return exclusions


def _exclude_synthetic_source_ips(items: list[dict[str, Any]], excluded_ips: set[str]) -> list[dict[str, Any]]:
    if not excluded_ips:
        return items
    filtered_items = []
    for item in items:
        candidate = item.get("name") or item.get("source_ip")
        if str(candidate or "") in excluded_ips:
            continue
        filtered_items.append(item)
    return filtered_items


def _fetch_map_marker_rows(cur, where_clause: str, params: list):
    query = f"""
        WITH filtered AS (
            SELECT *
            FROM alerts
            {where_clause}
        ),
        source_counts AS (
            SELECT host(source_ip) AS source_ip_key, COUNT(*) AS alert_count
            FROM filtered
            WHERE source_ip IS NOT NULL
              AND latitude IS NOT NULL
              AND longitude IS NOT NULL
            GROUP BY host(source_ip)
        ),
        latest AS (
            SELECT DISTINCT ON (host(source_ip))
                id,
                alert_type,
                severity,
                message,
                source_ip,
                created_at,
                status,
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
                source,
                source_type,
                context
            FROM filtered
            WHERE source_ip IS NOT NULL
              AND latitude IS NOT NULL
              AND longitude IS NOT NULL
            ORDER BY host(source_ip), created_at DESC, id DESC
        )
        SELECT
            latest.id,
            latest.alert_type,
            latest.severity,
            latest.message,
            latest.source_ip,
            latest.created_at,
            latest.status,
            latest.country,
            latest.city,
            latest.latitude,
            latest.longitude,
            latest.reputation_score,
            latest.reputation_label,
            latest.reputation_source,
            latest.reputation_summary,
            latest.response_action,
            latest.response_status,
            latest.source,
            latest.source_type,
            latest.context,
            source_counts.alert_count
        FROM latest
        JOIN source_counts
          ON source_counts.source_ip_key = host(latest.source_ip)
        ORDER BY source_counts.alert_count DESC, latest.created_at DESC, latest.id DESC
    """
    cur.execute(query, tuple(params))
    return cur.fetchall()


def _resolve_alert_list_response_outcomes(conn, alert_ids: list[int]) -> dict[int, dict | None]:
    bulk_events = get_latest_outcomes_for_alerts_bulk(conn, alert_ids)
    latest_decisions = get_latest_decisions_for_alerts_bulk(conn, alert_ids)
    outcomes: dict[int, dict | None] = {}
    for alert_id in alert_ids:
        decision = latest_decisions.get(alert_id)
        if decision is None:
            outcomes[alert_id] = None
        else:
            outcomes[alert_id] = build_latest_outcome_api_shape(
                decision,
                bulk_events.get(alert_id),
            )
    return outcomes


def _serialize_pfsense_cooldown_state(resolved_at):
    if resolved_at is None:
        return {
            "active": False,
            "resolved_at": None,
            "cooldown_until": None,
            "window_minutes": PFSENSE_ALERT_COOLDOWN_MINUTES,
        }

    if resolved_at.tzinfo is None:
        resolved_at = resolved_at.replace(tzinfo=timezone.utc)
    else:
        resolved_at = resolved_at.astimezone(timezone.utc)

    cooldown_until = resolved_at + timedelta(minutes=PFSENSE_ALERT_COOLDOWN_MINUTES)
    return {
        "active": cooldown_until > datetime.now(timezone.utc),
        "resolved_at": resolved_at.isoformat(),
        "cooldown_until": cooldown_until.isoformat(),
        "window_minutes": PFSENSE_ALERT_COOLDOWN_MINUTES,
    }


def _fetch_latest_resolved_audits(cur, alert_ids: list[int]) -> dict[int, dict]:
    filtered_ids = [int(alert_id) for alert_id in alert_ids if alert_id is not None]
    if not filtered_ids:
        return {}

    cur.execute(
        """
        SELECT DISTINCT ON (target_alert_id)
            target_alert_id,
            created_at
        FROM audit_log
        WHERE event_type = 'UPDATE_ALERT_STATUS'
          AND (details->>'status') = 'resolved'
          AND target_alert_id = ANY(%s)
        ORDER BY target_alert_id, created_at DESC
        """,
        (filtered_ids,),
    )
    return {
        row[0]: _serialize_pfsense_cooldown_state(row[1])
        for row in cur.fetchall()
    }


def _build_pfsense_quality_metadata(row, cooldown_by_alert_id: dict[int, dict]):
    alert_id = row[0]
    alert_type = row[1]
    source = row[17] or "unknown"
    context = row[19] if isinstance(row[19], dict) else {}

    if source != "pfsense" or alert_type not in PFSENSE_ALERT_TYPES:
        return None

    cooldown = cooldown_by_alert_id.get(alert_id) or _serialize_pfsense_cooldown_state(None)
    return {
        "why_fired_available": True,
        "suppressed_rollup": bool(context.get("suppressed")),
        "cooldown": cooldown,
        "recon_activity": context.get("recon_activity") if isinstance(context.get("recon_activity"), dict) else None,
    }


def _format_pfsense_context_value(field_name, value):
    if value in (None, "", []):
        return None
    if field_name == "direction":
        return "LAN → WAN (outbound)" if value == "out" else "WAN → LAN (inbound)" if value == "in" else value
    if field_name == "action":
        return "pass" if value == "pass" else "block" if value == "block" else value
    if field_name == "traffic_role":
        return {
            "initiation_like": "Initiation-like traffic",
            "reply_or_teardown_like": "Reply or teardown traffic",
            "ambiguous": "Ambiguous initiator evidence",
            "not_applicable": "Not applicable",
        }.get(value, value)
    return value


def _build_pfsense_why_fired_payload(row, cooldown_by_alert_id: dict[int, dict]):
    alert_id = row[0]
    alert_type = row[1]
    source = row[17] or "unknown"
    source_type = row[18] or "legacy"
    context = row[19] if isinstance(row[19], dict) else {}

    if source != "pfsense" or alert_type not in PFSENSE_ALERT_TYPES:
        return None

    rule_defaults = get_detection_rule_defaults().get(alert_type, {})
    evidence_fields_by_type = {
        "pfsense_firewall_repeated_deny": (
            "action",
            "direction",
            "event_count",
            "destination_ip",
            "destination_port",
            "source_port",
            "tcp_flags",
            "protocol",
            "interface",
            "traffic_role",
            "traffic_role_reason",
            "first_seen",
            "last_seen",
        ),
        "pfsense_firewall_port_scan": (
            "action",
            "scan_description",
            "distinct_port_count",
            "distinct_destination_count",
            "traffic_role",
            "traffic_role_reason",
            "first_seen",
            "last_seen",
        ),
        "pfsense_firewall_suspicious_allow": (
            "action",
            "direction",
            "event_count",
            "distinct_sensitive_port_count",
            "destination_ip",
            "destination_port",
            "protocol",
            "interface",
            "first_seen",
            "last_seen",
        ),
        "pfsense_firewall_allow_after_deny": (
            "action",
            "direction",
            "event_count",
            "destination_ip",
            "destination_port",
            "protocol",
            "interface",
            "first_seen",
            "last_seen",
        ),
        "pfsense_firewall_noisy_source": (
            "event_count",
            "first_seen",
            "last_seen",
        ),
    }
    evidence = []
    for field_name in evidence_fields_by_type.get(alert_type, ()):
        if field_name == "traffic_role":
            value = context.get("traffic_role", {}).get("classification")
        elif field_name == "traffic_role_reason":
            value = context.get("traffic_role", {}).get("reason")
        else:
            value = context.get(field_name)
        formatted_value = _format_pfsense_context_value(field_name, value)
        if formatted_value in (None, "", []):
            continue
        evidence.append(
            {
                "field": field_name,
                "label": PFSENSE_WHY_FIRED_LABELS.get(field_name, field_name.replace("_", " ").title()),
                "value": formatted_value,
            }
        )

    if bool(context.get("suppressed")):
        evidence.append(
            {
                "field": "suppressed",
                "label": "Suppression mode",
                "value": "Routine traffic was rolled up into one noisy-source alert.",
            }
        )

    cooldown = cooldown_by_alert_id.get(alert_id) or _serialize_pfsense_cooldown_state(None)
    return {
        "alert_id": alert_id,
        "rule_id": alert_type,
        "rule_name": rule_defaults.get("display_name", alert_type),
        "source": source,
        "source_type": source_type,
        "summary": row[3],
        "context": context,
        "evidence": evidence,
        "suppressed_rollup": bool(context.get("suppressed")),
        "cooldown": cooldown,
    }


def _query_related_pfsense_events(cur, related_filter: dict, *, limit: int = 25):
    event_types = [value for value in related_filter.get("event_types") or [] if value]
    if not event_types:
        return []

    clauses = ["source = 'pfsense'", "source_type = 'firewall'", "event_type = ANY(%s)"]
    params: list = [event_types]
    source_ip = related_filter.get("source_ip")
    if source_ip:
        clauses.append("source_ip = %s::inet")
        params.append(source_ip)
    destination_ips = [value for value in related_filter.get("destination_ips") or [] if value]
    if destination_ips:
        clauses.append("raw_payload->>'destination_ip' = ANY(%s)")
        params.append(destination_ips)
    destination_ports = [str(int(value)) for value in related_filter.get("destination_ports") or [] if value is not None]
    if destination_ports:
        clauses.append("raw_payload->>'destination_port' = ANY(%s)")
        params.append(destination_ports)
    protocol = related_filter.get("protocol")
    if protocol:
        clauses.append("raw_payload->>'protocol' = %s")
        params.append(protocol)
    direction = related_filter.get("direction")
    if direction:
        clauses.append("COALESCE(raw_payload->>'direction', '') = %s")
        params.append(direction)
    first_seen = related_filter.get("first_seen")
    if first_seen:
        clauses.append("created_at >= %s::timestamptz")
        params.append(first_seen)
    last_seen = related_filter.get("last_seen")
    if last_seen:
        clauses.append("created_at <= %s::timestamptz")
        params.append(last_seen)

    query = f"""
        SELECT
            id,
            event_type,
            host(source_ip),
            message,
            created_at,
            raw_payload
        FROM events
        WHERE {' AND '.join(clauses)}
        ORDER BY created_at DESC, id DESC
        LIMIT %s
    """
    params.append(max(1, min(int(limit), 100)))
    cur.execute(query, params)
    return [
        {
            "id": row[0],
            "event_type": row[1],
            "source_ip": row[2],
            "message": row[3],
            "created_at": row[4].isoformat() if row[4] else None,
            "raw_payload": row[5],
        }
        for row in cur.fetchall()
    ]


def _is_important_destination(target_context: dict[str, Any]) -> bool:
    if not isinstance(target_context, dict):
        return False
    try:
        return int(target_context.get("primary_destination_port")) in {22, 443, 3389, 8443, 1194, 51820}
    except (TypeError, ValueError):
        return False


def _build_campaign_seed(row) -> dict[str, Any]:
    context = row[19] if isinstance(row[19], dict) else {}
    target_context = context.get("target_context") if isinstance(context.get("target_context"), dict) else {}
    recon_activity = context.get("recon_activity") if isinstance(context.get("recon_activity"), dict) else {}
    sample_destination_ips = target_context.get("sample_destination_ips") or []
    sample_destination_ports = target_context.get("sample_destination_ports") or []
    first_seen = target_context.get("first_seen") or context.get("first_seen")
    last_seen = target_context.get("last_seen") or context.get("last_seen") or str(row[5])
    days_active = 0
    try:
        if first_seen and last_seen:
            first_dt = datetime.fromisoformat(str(first_seen).replace("Z", "+00:00"))
            last_dt = datetime.fromisoformat(str(last_seen).replace("Z", "+00:00"))
            days_active = max((last_dt.date() - first_dt.date()).days + 1, 1)
    except ValueError:
        days_active = 0
    return {
        "first_seen": first_seen,
        "last_seen": last_seen,
        "days_active": days_active,
        "source_count": int(recon_activity.get("source_ip_count") or 0),
        "destination_count": int(target_context.get("distinct_destination_count") or len(sample_destination_ips) or 0),
        "service_count": int(target_context.get("distinct_port_count") or len(sample_destination_ports) or 0),
        "corroborating_alert_types": 1,
        "progression_observed": bool(
            row[1] == "pfsense_firewall_allow_after_deny"
            or context.get("progression_observed")
        ),
        "timing_pattern": bool(context.get("beacon_like_timing")),
        "relationship": "Shared recon activity" if recon_activity.get("id") else "",
    }


def _fetch_alert_intelligence(conn, rows) -> dict[int, dict[str, Any]]:
    if not rows:
        return {}

    alert_ids = [int(row[0]) for row in rows]
    source_ips = sorted({str(row[4]) for row in rows if row[4] is not None})

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                host(a.source_ip),
                MIN(a.created_at),
                MAX(a.created_at),
                COUNT(DISTINCT DATE(a.created_at)),
                COUNT(DISTINCT ia.incident_id),
                COUNT(*) FILTER (WHERE a.response_status IS NOT NULL),
                COUNT(DISTINCT NULLIF(COALESCE(a.context->'target_context'->>'primary_destination_ip', ''), '')),
                COUNT(DISTINCT NULLIF(COALESCE(a.context->'target_context'->>'primary_destination_port', ''), '')),
                ARRAY_AGG(a.created_at ORDER BY a.created_at)
            FROM alerts a
            LEFT JOIN incident_alerts ia ON ia.alert_id = a.id
            WHERE a.source_ip = ANY(%s::inet[])
            GROUP BY host(a.source_ip)
            """,
            (source_ips,),
        )
        history_by_ip = {
            row[0]: {
                "first_seen": row[1].isoformat() if row[1] else None,
                "last_seen": row[2].isoformat() if row[2] else None,
                "days_observed": int(row[3] or 0),
                "previous_incidents": max(int(row[4] or 0) - 1, 0),
                "previous_responses": int(row[5] or 0),
                "repeated_destinations": int(row[6] or 0),
                "repeated_services": int(row[7] or 0),
                "observed_at": [value.isoformat() for value in (row[8] or []) if value is not None],
                "campaign_count": 0,
            }
            for row in cur.fetchall()
        }

        cur.execute(
            """
            SELECT
                ral.alert_id,
                ra.id,
                ra.first_seen,
                ra.last_seen,
                COALESCE((ra.summary->>'source_ip_count')::integer, 0),
                COALESCE((ra.summary->>'destination_ip_count')::integer, 0),
                COALESCE((ra.summary->>'distinct_service_count')::integer, 0),
                COALESCE(jsonb_array_length(COALESCE(ra.summary->'alert_types', '[]'::jsonb)), 0),
                ra.coordination_status
            FROM recon_activity_alerts ral
            JOIN recon_activities ra ON ra.id = ral.recon_activity_id
            WHERE ral.alert_id = ANY(%s::int[])
            """,
            (alert_ids,),
        )
        campaign_rows = cur.fetchall()

    campaign_by_alert_id = {
        int(row[0]): {
            "id": int(row[1]),
            "first_seen": row[2].isoformat() if row[2] else None,
            "last_seen": row[3].isoformat() if row[3] else None,
            "source_count": int(row[4] or 0),
            "destination_count": int(row[5] or 0),
            "service_count": int(row[6] or 0),
            "corroborating_alert_types": int(row[7] or 0),
            "relationship": f"Recon activity #{row[1]} ({str(row[8] or 'not_established').replace('_', ' ')})",
        }
        for row in campaign_rows
    }

    intelligence: dict[int, dict[str, Any]] = {}
    for row in rows:
        alert_id = int(row[0])
        source_ip = str(row[4]) if row[4] is not None else None
        context = row[19] if isinstance(row[19], dict) else {}
        target_context = context.get("target_context") if isinstance(context.get("target_context"), dict) else {}
        history = dict(history_by_ip.get(source_ip, {}))
        campaign_seed = _build_campaign_seed(row)
        campaign_seed.update(campaign_by_alert_id.get(alert_id, {}))
        history["campaign_count"] = 1 if campaign_seed.get("id") else 0

        returning_attacker = build_returning_attacker_context(history)
        campaign_intelligence = build_campaign_intelligence(campaign_seed)
        progression_observed = bool(
            row[1] == "pfsense_firewall_allow_after_deny" or campaign_seed.get("progression_observed")
        )
        repeated_destination = returning_attacker.get("repeated_destinations", 0) > 0
        persistent_activity = returning_attacker.get("days_observed", 0) > 1
        investigation_value = build_investigation_value(
            severity=row[2],
            returning_attacker=returning_attacker,
            campaign_intelligence=campaign_intelligence,
            progression_observed=progression_observed,
            corroborating_detection_count=max(int(campaign_seed.get("corroborating_alert_types") or 0), 1),
            destination_important=_is_important_destination(target_context),
            response_history_present=returning_attacker.get("previous_responses", 0) > 0,
            repeated_destination=repeated_destination,
            persistent_activity=persistent_activity,
        )

        alert_story = None
        if row[1] == "pfsense_firewall_port_scan":
            alert_story = build_port_scan_story(
                investigation_value=investigation_value,
                returning_attacker=returning_attacker,
                campaign_intelligence=campaign_intelligence,
                repeated_destination=repeated_destination,
                progression_observed=progression_observed,
            )
        elif row[1] == "pfsense_firewall_allow_after_deny":
            alert_story = {
                "headline": (
                    "Campaign-linked deny-then-allow progression"
                    if campaign_intelligence.get("present")
                    else "Repeated deny activity led to a later allow"
                ),
                "disposition": investigation_value["label"],
            }

        intelligence[alert_id] = {
            "returning_attacker": returning_attacker,
            "campaign_intelligence": campaign_intelligence,
            "investigation_value": investigation_value,
            "alert_story": alert_story,
            "progression_observed": progression_observed,
        }

    return intelligence


def _build_alert_payload(
    row,
    *,
    cur,
    reputation_by_ip: dict,
    response_outcome,
    cooldown_by_alert_id: dict[int, dict],
    intelligence: dict[str, Any] | None = None,
) -> dict:
    source_ip = str(row[4]) if row[4] is not None else None
    if source_ip not in reputation_by_ip:
        reputation_by_ip[source_ip] = get_ip_reputation(source_ip, cur=cur)
    behavioral_reputation = reputation_by_ip[source_ip]
    behavioral_contributing_signals = behavioral_reputation.get("contributing_signals", [])
    intelligence = intelligence or {}

    return enrich_alert_with_correlation_context(
        enrich_alert_with_mitre(
            {
                "id": row[0],
                "alert_type": row[1],
                "severity": row[2],
                "message": row[3],
                "source_ip": row[4],
                "created_at": str(row[5]),
                "status": row[6],
                "country": row[7],
                "city": row[8],
                "latitude": row[9],
                "longitude": row[10],
                "reputation_score": row[11],
                "reputation_label": row[12],
                "reputation_source": row[13],
                "reputation_summary": row[14],
                "behavioral_reputation": {
                    "score": behavioral_reputation["reputation_score"],
                    "label": behavioral_reputation["reputation_label"],
                    "source": "siem_internal",
                    "summary": behavioral_reputation["reputation_summary"],
                    "contributing_signals": behavioral_contributing_signals,
                },
                "contributing_signals": behavioral_contributing_signals,
                "response_action": row[15],
                "response_status": row[16],
                "response_outcome": response_outcome,
                "source": row[17] or "unknown",
                "source_type": row[18] or "legacy",
                "context": row[19] if row[19] is not None else {},
                "investigation_value": intelligence.get("investigation_value"),
                "returning_attacker": intelligence.get("returning_attacker"),
                "campaign_intelligence": intelligence.get("campaign_intelligence"),
                "alert_story": intelligence.get("alert_story"),
                "investigation_intelligence": {
                    "progression_observed": bool(intelligence.get("progression_observed")),
                },
                "pfsense_quality": _build_pfsense_quality_metadata(row, cooldown_by_alert_id),
                "operational_history": build_alert_operational_history(
                    created_at=row[5],
                    source=row[17],
                    source_type=row[18],
                ),
            }
        )
    )


@alerts_events_bp.route("/alerts", methods=["GET"])
@login_required
def get_alerts():
    try:
        query_args, error_response = _parse_alert_list_request_args(include_pagination=True)
        if error_response:
            return error_response

        conn = get_db_connection()
        cur = conn.cursor()
        clauses, params = _build_alert_filter_sql(query_args)
        where_clause = _build_alerts_where_clause(clauses)
        order_clause = _build_alert_order_clause(query_args["sort"])
        total = _fetch_alert_total(cur, where_clause, params)
        rows = _fetch_alert_rows(
            cur,
            where_clause,
            order_clause,
            params,
            limit=query_args["limit"],
            offset=query_args["offset"],
        )
        alert_ids = [row[0] for row in rows]
        response_outcomes_by_alert = _resolve_alert_list_response_outcomes(conn, alert_ids)
        cooldown_by_alert_id = _fetch_latest_resolved_audits(cur, alert_ids)
        intelligence_by_alert_id = _fetch_alert_intelligence(conn, rows)
        reputation_by_ip = {}

        items = []
        for row in rows:
            items.append(
                _build_alert_payload(
                    row,
                    cur=cur,
                    reputation_by_ip=reputation_by_ip,
                    response_outcome=response_outcomes_by_alert.get(row[0]),
                    cooldown_by_alert_id=cooldown_by_alert_id,
                    intelligence=intelligence_by_alert_id.get(int(row[0])),
                )
            )

        cur.close()
        conn.close()

        return (
            jsonify(
                {
                    "items": items,
                    "total": total,
                    "limit": query_args["limit"],
                    "offset": query_args["offset"],
                    "sort": query_args["sort"],
                }
            ),
            200,
        )

    except Exception as e:
        current_app.logger.error("Error in get_alerts: %s", e)
        return jsonify({"error": "Internal server error"}), 500


@alerts_events_bp.route("/alerts/summary", methods=["GET"])
@login_required
def get_alerts_summary():
    conn = None
    cur = None
    try:
        query_args, error_response = _parse_alert_list_request_args(include_pagination=False)
        if error_response:
            return error_response

        conn = get_db_connection()
        cur = conn.cursor()
        clauses, params = _build_alert_filter_sql(query_args)
        where_clause = _build_alerts_where_clause(clauses)
        metrics = _fetch_alert_summary_metrics(cur, where_clause, params)
        top_source_ips = _fetch_top_source_ips(cur, where_clause, params)
        timeline_payload = _fetch_alert_timeline(
            cur,
            where_clause,
            params,
            query_args["timeline_range"],
        )
        marker_rows = _fetch_map_marker_rows(cur, where_clause, params)
        excluded_source_ips = _load_synthetic_source_ip_exclusions()

        marker_ids = [row[0] for row in marker_rows]
        response_outcomes_by_alert = _resolve_alert_list_response_outcomes(conn, marker_ids)
        cooldown_by_alert_id = _fetch_latest_resolved_audits(cur, marker_ids)
        intelligence_by_alert_id = _fetch_alert_intelligence(conn, [row[:20] for row in marker_rows])
        reputation_by_ip = {}
        map_markers = []
        for row in marker_rows:
            alert_payload = _build_alert_payload(
                row[:20],
                cur=cur,
                reputation_by_ip=reputation_by_ip,
                response_outcome=response_outcomes_by_alert.get(row[0]),
                cooldown_by_alert_id=cooldown_by_alert_id,
                intelligence=intelligence_by_alert_id.get(int(row[0])),
            )
            alert_payload["alert_count"] = int(row[20] or 0)
            map_markers.append(alert_payload)
        if excluded_source_ips:
            top_source_ips = _exclude_synthetic_source_ips(top_source_ips, excluded_source_ips)
            map_markers = _exclude_synthetic_source_ips(map_markers, excluded_source_ips)

        return (
            jsonify(
                {
                    "metrics": metrics,
                    "top_source_ips": top_source_ips,
                    "timeline": timeline_payload["points"],
                    "timeline_meta": {
                        "range": timeline_payload["range"],
                        "bucket": timeline_payload["bucket"],
                        "window_start": timeline_payload["window_start"],
                    },
                    "map_markers": map_markers,
                }
            ),
            200,
        )
    except Exception as error:
        current_app.logger.error("Error in get_alerts_summary: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@alerts_events_bp.route("/alerts/<int:alert_id>", methods=["GET"])
@login_required
def get_alert(alert_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(f"{_ALERT_SELECT} WHERE id = %s", (alert_id,))
        row = cur.fetchone()
        if row is None:
            cur.close()
            conn.close()
            return jsonify({"error": "Alert not found"}), 404

        response_outcome = serialize_latest_outcome(conn, alert_id=alert_id)
        cooldown_by_alert_id = _fetch_latest_resolved_audits(cur, [alert_id])
        intelligence_by_alert_id = _fetch_alert_intelligence(conn, [row])
        alert = _build_alert_payload(
            row,
            cur=cur,
            reputation_by_ip={},
            response_outcome=response_outcome,
            cooldown_by_alert_id=cooldown_by_alert_id,
            intelligence=intelligence_by_alert_id.get(int(alert_id)),
        )

        cur.close()
        conn.close()

        return jsonify(alert), 200

    except Exception as e:
        current_app.logger.error("Error in get_alert: %s", e)
        return jsonify({"error": "Internal server error"}), 500


@alerts_events_bp.route("/alerts/<int:alert_id>/why-fired", methods=["GET"])
@login_required
def get_pfsense_why_fired(alert_id):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(f"{_ALERT_SELECT} WHERE id = %s", (alert_id,))
        row = cur.fetchone()
        if row is None:
            return jsonify({"error": "Alert not found"}), 404

        payload = _build_pfsense_why_fired_payload(
            row,
            _fetch_latest_resolved_audits(cur, [alert_id]),
        )
        if payload is None:
            return jsonify({"error": "Why this fired is available only for pfSense alerts"}), 400

        return jsonify(payload), 200
    except Exception as error:
        current_app.logger.error("Error in get_pfsense_why_fired: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@alerts_events_bp.route("/alerts/<int:alert_id>/related-events", methods=["GET"])
@login_required
def get_alert_related_events(alert_id):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(f"{_ALERT_SELECT} WHERE id = %s", (alert_id,))
        row = cur.fetchone()
        if row is None:
            return jsonify({"error": "Alert not found"}), 404
        context = row[19] if isinstance(row[19], dict) else {}
        related_filter = context.get("related_event_filter") if isinstance(context.get("related_event_filter"), dict) else {}
        events = _query_related_pfsense_events(cur, related_filter, limit=request.args.get("limit", 25))
        return jsonify({"alert_id": alert_id, "events": events, "count": len(events)}), 200
    except Exception as error:
        current_app.logger.error("Error in get_alert_related_events: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@alerts_events_bp.route("/recon-activities", methods=["GET"])
@login_required
def get_recon_activities():
    conn = None
    try:
        conn = get_db_connection()
        status = _normalize_alert_filter_value(request.args.get("status"))
        limit, limit_error = _parse_non_negative_int(request.args.get("limit"), 20, "limit")
        if limit_error:
            return jsonify({"error": limit_error}), 400
        items = list_recon_activities(conn, status=status, limit=limit or 20)
        return jsonify({"items": items, "count": len(items)}), 200
    except Exception as error:
        current_app.logger.error("Error in get_recon_activities: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@alerts_events_bp.route("/recon-activities/<int:activity_id>", methods=["GET"])
@login_required
def get_recon_activity(activity_id):
    conn = None
    try:
        conn = get_db_connection()
        payload = get_recon_activity_detail(conn, activity_id)
        if payload is None:
            return jsonify({"error": "Recon activity not found"}), 404
        return jsonify(payload), 200
    except Exception as error:
        current_app.logger.error("Error in get_recon_activity: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@alerts_events_bp.route("/recon-activities/<int:activity_id>/related-events", methods=["GET"])
@login_required
def get_recon_activity_related_events(activity_id):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        payload = get_recon_activity_detail(conn, activity_id)
        if payload is None:
            return jsonify({"error": "Recon activity not found"}), 404
        cur = conn.cursor()
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        target_context = summary.get("target_context") if isinstance(summary.get("target_context"), dict) else {}
        first_seen = payload.get("first_seen")
        last_seen = payload.get("last_seen")
        representative_sources = summary.get("representative_sources") or []
        related_filter = {
            "event_types": ["firewall_block", "firewall_allow"],
            "source_ip": representative_sources[0] if representative_sources else None,
            "destination_ips": target_context.get("sample_destination_ips") or [],
            "destination_ports": target_context.get("sample_destination_ports") or [],
            "first_seen": first_seen,
            "last_seen": last_seen,
        }
        events = _query_related_pfsense_events(cur, related_filter, limit=request.args.get("limit", 25))
        return jsonify({"activity_id": activity_id, "events": events, "count": len(events)}), 200
    except Exception as error:
        current_app.logger.error("Error in get_recon_activity_related_events: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@alerts_events_bp.route("/alerts/backfill-reputation", methods=["POST"])
@login_required
@admin_required
def backfill_alert_reputation():
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, source_ip
            FROM alerts
            WHERE
                reputation_score IS NULL
                OR reputation_source IN ('mock', 'fallback')
                OR response_action IS NULL
                OR response_status IS NULL
            """
        )

        rows = cur.fetchall()
        updated = 0

        for row in rows:
            alert_id = row[0]
            source_ip = str(row[1])

            reputation = lookup_ip_reputation(source_ip)
            response_action = determine_response_action(reputation["reputation_score"])
            response_status = "pending"

            cur.execute(
                """
                UPDATE alerts
                SET
                    reputation_score = %s,
                    reputation_label = %s,
                    reputation_source = %s,
                    reputation_summary = %s,
                    response_action = %s,
                    response_status = %s
                WHERE id = %s
                """,
                (
                    reputation["reputation_score"],
                    reputation["reputation_label"],
                    reputation["reputation_source"],
                    reputation["reputation_summary"],
                    response_action,
                    response_status,
                    alert_id
                )
            )

            updated += 1

        conn.commit()

        return jsonify({
            "message": "Reputation backfill completed",
            "updated_alerts": updated
        }), 200

    except Exception as e:
        current_app.logger.error("Error in backfill_alert_reputation: %s", e)
        return jsonify({"error": "Internal server error"}), 500

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@alerts_events_bp.route("/events/search", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def search_events():
    conn = None
    cur = None

    try:
        source_ip = (request.args.get("source_ip") or "").strip()
        source = (request.args.get("source") or "").strip()
        event_type = (request.args.get("event_type") or "").strip()
        start_time = (request.args.get("start_time") or "").strip()
        end_time = (request.args.get("end_time") or "").strip()
        after_id = (request.args.get("after_id") or "").strip()

        clauses = []
        params = []

        if source_ip:
            try:
                ipaddress.ip_address(source_ip)
            except ValueError:
                return jsonify({"error": "Invalid source_ip"}), 400
            clauses.append("source_ip = %s")
            params.append(source_ip)

        if source:
            if source not in VALID_EVENT_SOURCES:
                return jsonify({"error": "Invalid source"}), 400
            clauses.append("source = %s")
            params.append(source)

        if event_type:
            if event_type not in VALID_EVENT_SEARCH_TYPES:
                return jsonify({"error": "Invalid event_type"}), 400
            clauses.append("event_type = %s")
            params.append(event_type)

        if after_id:
            try:
                parsed_after_id = int(after_id)
            except ValueError:
                return jsonify({"error": "Invalid after_id"}), 400
            if parsed_after_id < 0:
                return jsonify({"error": "Invalid after_id"}), 400
            clauses.append("id > %s")
            params.append(parsed_after_id)

        if start_time:
            try:
                parsed_start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            except ValueError:
                return jsonify({"error": "Invalid start_time"}), 400
            clauses.append("created_at >= %s")
            params.append(parsed_start)

        if end_time:
            try:
                parsed_end = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            except ValueError:
                return jsonify({"error": "Invalid end_time"}), 400
            clauses.append("created_at <= %s")
            params.append(parsed_end)

        query = """
            SELECT
                id,
                event_type,
                severity,
                source_ip,
                message,
                app_name,
                environment,
                source,
                source_type,
                raw_payload,
                created_at
            FROM events
        """

        if clauses:
            query += " WHERE " + " AND ".join(clauses)

        query += " ORDER BY id DESC LIMIT 100"

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(query, tuple(params))

        rows = cur.fetchall()
        reputation_by_ip = {}
        events = []
        for row in rows:
            source_ip = str(row[3]) if row[3] is not None else None
            if source_ip not in reputation_by_ip:
                reputation_by_ip[source_ip] = get_ip_reputation(source_ip, cur=cur)
            reputation = reputation_by_ip[source_ip]

            events.append(
                {
                    "id": row[0],
                    "event_type": row[1],
                    "severity": row[2],
                    "source_ip": source_ip,
                    "message": row[4],
                    "app_name": row[5],
                    "environment": row[6],
                    "source": row[7],
                    "source_type": row[8],
                    "raw_payload": row[9],
                    "created_at": str(row[10]),
                    "reputation_score": reputation["reputation_score"],
                    "reputation_label": reputation["reputation_label"],
                    "reputation_summary": reputation["reputation_summary"],
                    "contributing_signals": reputation["contributing_signals"],
                }
            )

        return jsonify(events), 200
    except Exception as e:
        current_app.logger.error("Error in search_events: %s", e)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
