from __future__ import annotations

import ipaddress

from core.pfsense_operational_baseline import build_pfsense_alert_baseline_filter
from engines.detection_rule_catalog import DETECTION_RULE_CATALOG


def normalize_alert_filter_value(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "all":
        return None
    return text


def normalize_ip_filter_value(value):
    normalized = normalize_alert_filter_value(value)
    if normalized is None:
        return None
    try:
        return str(ipaddress.ip_address(normalized))
    except ValueError as exc:
        raise ValueError("invalid IP filter") from exc


def normalize_rule_id_filter(value):
    normalized = normalize_alert_filter_value(value)
    if normalized is None:
        return None
    if not normalized.replace("_", "").replace("-", "").isalnum():
        raise ValueError("invalid rule_id")
    return normalized


def fetch_observed_alert_types(cur) -> set[str]:
    cur.execute(
        """
        SELECT DISTINCT alert_type
        FROM alerts
        WHERE alert_type IS NOT NULL
        """
    )
    return {str(row[0]) for row in cur.fetchall() if row[0]}


def validate_rule_id_filter(cur, rule_id):
    if rule_id is None:
        return None
    if rule_id in DETECTION_RULE_CATALOG:
        return None
    if rule_id in fetch_observed_alert_types(cur):
        return None
    return "unsupported rule_id"


def build_alert_filter_sql(filters: dict, *, table_alias: str | None = None, include_alert_type_search: bool = False):
    clauses = []
    params = []
    prefix = f"{table_alias}." if table_alias else ""
    source_ip_expr = f"host({prefix}source_ip)"

    search = normalize_alert_filter_value(filters.get("search"))
    if search:
        pattern = f"%{search}%"
        if include_alert_type_search:
            clauses.append(
                f"({source_ip_expr} ILIKE %s OR {prefix}message ILIKE %s OR {prefix}alert_type ILIKE %s)"
            )
            params.extend((pattern, pattern, pattern))
        else:
            clauses.append(f"({source_ip_expr} ILIKE %s OR {prefix}message ILIKE %s)")
            params.extend((pattern, pattern))

    exact_source_ip = normalize_ip_filter_value(filters.get("exact_source_ip"))
    if exact_source_ip:
        clauses.append(f"{source_ip_expr} = %s")
        params.append(exact_source_ip)

    exact_target_ip = normalize_ip_filter_value(filters.get("exact_target_ip"))
    if exact_target_ip:
        clauses.append(
            f"""
            (
                COALESCE({prefix}context->'target_context'->>'primary_destination_ip', '') = %s
                OR COALESCE({prefix}context->'target_context'->>'destination_ip', '') = %s
                OR COALESCE({prefix}context->'target_context'->>'top_destination_ip', '') = %s
                OR EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements_text(
                        COALESCE({prefix}context->'target_context'->'sample_destination_ips', '[]'::jsonb)
                    ) AS sample_destination_ip(value)
                    WHERE sample_destination_ip.value = %s
                )
            )
            """
        )
        params.extend((exact_target_ip, exact_target_ip, exact_target_ip, exact_target_ip))

    alert_id = filters.get("alert_id")
    if alert_id is not None:
        clauses.append(f"{prefix}id = %s")
        params.append(alert_id)

    rule_id = normalize_rule_id_filter(filters.get("rule_id"))
    if rule_id:
        clauses.append(f"{prefix}alert_type = %s")
        params.append(rule_id)

    severity = normalize_alert_filter_value(filters.get("severity"))
    if severity:
        clauses.append(f"{prefix}severity = %s")
        params.append(severity.lower())

    status = normalize_alert_filter_value(filters.get("status"))
    if status:
        clauses.append(f"{prefix}status = %s")
        params.append(status.lower())

    source = normalize_alert_filter_value(filters.get("source"))
    if source:
        clauses.append(f"COALESCE({prefix}source, 'legacy') = %s")
        params.append(source)

    operational_clause, operational_params = build_pfsense_alert_baseline_filter(
        filters.get("operational_scope") or "all_history",
        created_at_column=f"{prefix}created_at" if prefix else "created_at",
        source_column=f"{prefix}source" if prefix else "source",
        source_type_column=f"{prefix}source_type" if prefix else "source_type",
    )
    if operational_clause:
        clauses.append(operational_clause)
        params.extend(operational_params)

    return clauses, params


def build_alerts_where_clause(clauses: list[str]) -> str:
    if not clauses:
        return ""
    return " WHERE " + " AND ".join(clauses)


def build_alert_filter_scope_label(filters: dict) -> str:
    scope_parts = ["Filtered Alert Export"]
    labels = (
        ("search", "search"),
        ("rule_id", "rule"),
        ("severity", "severity"),
        ("status", "status"),
        ("source", "source"),
        ("operational_scope", "scope"),
        ("exact_source_ip", "source_ip"),
        ("exact_target_ip", "target_ip"),
        ("alert_id", "alert_id"),
    )
    for key, label in labels:
        value = normalize_alert_filter_value(filters.get(key))
        if key == "operational_scope" and value == "all_history":
            continue
        if value:
            scope_parts.append(f'{label}="{value}"' if key == "search" else f"{label}={value}")
    return " | ".join(scope_parts)


def fetch_alert_rows(cur, filters=None):
    filters = filters or {}
    clauses, params = build_alert_filter_sql(filters, include_alert_type_search=True)

    query = """
        SELECT
            id,
            alert_type,
            severity,
            source_ip,
            created_at,
            message,
            status,
            country,
            city,
            reputation_label,
            reputation_summary,
            response_action,
            response_status
        FROM alerts
    """

    query += build_alerts_where_clause(clauses)

    query += " ORDER BY created_at DESC"
    cur.execute(query, tuple(params))
    return cur.fetchall()


def fetch_response_logs_by_alert_id(cur, alert_ids):
    if not alert_ids:
        return {}

    cur.execute(
        """
        SELECT alert_id, action, status, details, executed_at
        FROM response_actions_log
        WHERE alert_id = ANY(%s)
        ORDER BY executed_at DESC
        """,
        (alert_ids,)
    )

    log_map = {alert_id: [] for alert_id in alert_ids}
    for row in cur.fetchall():
        log_map.setdefault(row[0], []).append(row[1:])
    return log_map


def fetch_alert_csv_rows(cur, filters=None):
    filters = filters or {}
    clauses, params = build_alert_filter_sql(
        filters,
        table_alias="a",
        include_alert_type_search=True,
    )

    query = """
        SELECT
            a.id,
            a.alert_type,
            a.severity,
            a.source_ip,
            a.status,
            a.created_at,
            a.message,
            latest_event.environment
        FROM alerts a
        LEFT JOIN LATERAL (
            SELECT e.environment
            FROM events e
            WHERE e.source_ip = a.source_ip
            ORDER BY e.created_at DESC
            LIMIT 1
        ) AS latest_event ON TRUE
    """

    query += build_alerts_where_clause(clauses)

    query += " ORDER BY a.created_at DESC"
    cur.execute(query, tuple(params))
    return cur.fetchall()
