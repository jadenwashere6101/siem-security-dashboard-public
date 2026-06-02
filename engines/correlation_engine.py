from flask import current_app

from engines.detection_config import CORRELATION_WINDOW_MINUTES
from core.ip_helpers import determine_response_action, lookup_ip_reputation


def _alert_result(alert_id, source_ip, response_action, severity, alert_type, source, source_type):
    return {
        "alert_id": alert_id,
        "source_ip": source_ip,
        "response_action": response_action,
        "severity": severity,
        "alert_type": alert_type,
        "source": source,
        "source_type": source_type,
    }


# spec: SPEC-INGEST-001
def generate_correlated_activity_alerts(cur, conn, source_ip):
    qualifying_alert_types = (
        "failed_login_threshold",
        "password_spraying_threshold",
        "successful_login_after_spray",
        "port_scan_threshold",
        "http_error_threshold",
        "high_request_rate_threshold",
    )

    current_app.logger.info("[CORRELATION] Evaluating IP: %s", source_ip)

    cur.execute(
        """
        SELECT 1
        FROM alerts
        WHERE source_ip = %s
          AND alert_type = %s
          AND status = 'open'
        """,
        (source_ip, "correlated_activity"),
    )

    if cur.fetchone():
        current_app.logger.warning("[CORRELATION] Skipped: duplicate open correlated_activity alert exists | IP: %s", source_ip)
        return []

    cur.execute(
        f"""
        SELECT
            id,
            alert_type,
            source,
            source_type,
            country,
            city,
            latitude,
            longitude,
            created_at
        FROM alerts
        WHERE source_ip = %s
          AND status = 'open'
          AND alert_type IN %s
          AND created_at >= NOW() - INTERVAL '{CORRELATION_WINDOW_MINUTES} minutes'
        ORDER BY created_at DESC
        """,
        (source_ip, qualifying_alert_types),
    )

    rows = cur.fetchall()
    current_app.logger.debug("[CORRELATION] Detailed counts | IP: %s | qualifying_open_alerts=%d | window_minutes=%d", source_ip, len(rows), CORRELATION_WINDOW_MINUTES)
    if len(rows) < 2:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM alerts
            WHERE source_ip = %s
              AND status = 'open'
              AND alert_type IN %s
            """,
            (source_ip, qualifying_alert_types),
        )
        total_qualifying_alerts = cur.fetchone()[0]
        skip_reason = "alerts exist but not within correlation window" if total_qualifying_alerts >= 2 else "not enough qualifying alerts"
        current_app.logger.warning("[CORRELATION] Skipped: %s | IP: %s", skip_reason, source_ip)
        return []

    alert_types = []
    known_sources = []
    for row in rows:
        alert_type = row[1]
        if alert_type not in alert_types:
            alert_types.append(alert_type)
        source = row[2]
        if source is not None:
            normalized_source = str(source).strip().lower()
            if normalized_source and normalized_source != "unknown" and normalized_source not in known_sources:
                known_sources.append(normalized_source)

    if len(alert_types) < 2:
        current_app.logger.warning("[CORRELATION] Skipped: not enough distinct alert types | IP: %s", source_ip)
        return []

    if len(known_sources) < 2:
        current_app.logger.warning("[CORRELATION] Skipped: not enough distinct known sources | IP: %s", source_ip)
        return []

    newest_alert = rows[0]
    source = newest_alert[2] or "unknown"
    source_type = newest_alert[3] or "legacy"
    country = newest_alert[4]
    city = newest_alert[5]
    latitude = newest_alert[6]
    longitude = newest_alert[7]

    reputation = lookup_ip_reputation(str(source_ip))
    reputation_score = reputation["reputation_score"]
    response_action = determine_response_action(reputation_score)
    response_status = "pending"
    reputation_label = reputation["reputation_label"]
    reputation_source = reputation["reputation_source"]
    reputation_summary = reputation["reputation_summary"]

    alert_types_text = ", ".join(alert_types)
    message = f"Multi-source suspicious activity detected from {source_ip} involving: {alert_types_text}"

    cur.execute(
        """
        INSERT INTO alerts (
            source_ip,
            alert_type,
            severity,
            source,
            source_type,
            message,
            status,
            response_action,
            response_status,
            country,
            city,
            latitude,
            longitude,
            reputation_score,
            reputation_label,
            reputation_source,
            reputation_summary
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            source_ip,
            "correlated_activity",
            "high",
            source,
            source_type,
            message,
            "open",
            response_action,
            response_status,
            country,
            city,
            latitude,
            longitude,
            reputation_score,
            reputation_label,
            reputation_source,
            reputation_summary,
        ),
    )

    cur.execute("SELECT currval(pg_get_serial_sequence('alerts', 'id'))")
    alert_id = cur.fetchone()[0]

    current_app.logger.info(
        "[CORRELATION] Success | IP: %s | alerts=%d | types=%s | sources=%s",
        source_ip,
        len(rows),
        alert_types_text,
        ", ".join(known_sources),
    )

    return [_alert_result(alert_id, source_ip, response_action, "high", "correlated_activity", source, source_type)]


def generate_targeted_correlation_alerts(cur, conn, source_ip):
    alerts_created = []
    rules = (
        {
            "alert_type": "web_to_app_attack_pattern",
            "window_minutes": 10,
            "severity": "critical",
            "message": f"Web-to-app attack pattern detected from {source_ip}",
            "matches": lambda row: (
                (row[2], row[3]) == ("nginx", "web_log")
                and row[1] in {"http_error_threshold", "high_request_rate_threshold"}
            ) or (
                (row[2], row[3]) == ("bank_app", "custom")
                and row[1] in {"failed_login_threshold", "password_spraying_threshold"}
            ),
            "required_groups": ("nginx_web", "bank_app_custom"),
            "group_for_row": lambda row: (
                "nginx_web"
                if (row[2], row[3]) == ("nginx", "web_log")
                and row[1] in {"http_error_threshold", "high_request_rate_threshold"}
                else "bank_app_custom"
                if (row[2], row[3]) == ("bank_app", "custom")
                and row[1] in {"failed_login_threshold", "password_spraying_threshold"}
                else None
            ),
        },
        {
            "alert_type": "spray_then_success_pattern",
            "window_minutes": 15,
            "severity": "critical",
            "message": f"Password spray followed by successful login from {source_ip}",
            "matches": lambda row: row[1] in {"password_spraying_threshold", "successful_login_after_spray"},
            "required_groups": ("password_spraying_threshold", "successful_login_after_spray"),
            "group_for_row": lambda row: row[1] if row[1] in {"password_spraying_threshold", "successful_login_after_spray"} else None,
        },
        {
            "alert_type": "cloud_app_error_pattern",
            "window_minutes": 10,
            "severity": "high",
            "message": f"Cloud and web application errors correlated from {source_ip}",
            "matches": lambda row: (
                (row[2], row[3]) == ("azure_insights", "cloud_api")
                and row[1] in {"http_error_threshold", "application_exception_threshold"}
            ) or (
                (row[2], row[3]) == ("nginx", "web_log")
                and row[1] in {"http_error_threshold", "high_request_rate_threshold"}
            ),
            "required_groups": ("azure_cloud", "nginx_web"),
            "group_for_row": lambda row: (
                "azure_cloud"
                if (row[2], row[3]) == ("azure_insights", "cloud_api")
                and row[1] in {"http_error_threshold", "application_exception_threshold"}
                else "nginx_web"
                if (row[2], row[3]) == ("nginx", "web_log")
                and row[1] in {"http_error_threshold", "high_request_rate_threshold"}
                else None
            ),
        },
    )

    for rule in rules:
        rule_alert_type = rule["alert_type"]
        current_app.logger.info("[TARGETED_CORRELATION] Evaluating rule=%s | IP: %s", rule_alert_type, source_ip)

        cur.execute(
            """
            SELECT 1
            FROM alerts
            WHERE source_ip = %s
              AND alert_type = %s
              AND status = 'open'
            """,
            (source_ip, rule_alert_type),
        )

        if cur.fetchone():
            current_app.logger.info("[TARGETED_CORRELATION] Skipped rule=%s | reason=duplicate_open_alert | IP: %s", rule_alert_type, source_ip)
            continue

        cur.execute(
            f"""
            SELECT
                id,
                alert_type,
                source,
                source_type,
                country,
                city,
                latitude,
                longitude,
                created_at
            FROM alerts
            WHERE source_ip = %s
              AND status = 'open'
              AND created_at >= NOW() - INTERVAL '{rule["window_minutes"]} minutes'
            ORDER BY created_at DESC
            """,
            (source_ip,),
        )

        rows = cur.fetchall()
        qualifying_rows = [row for row in rows if rule["matches"](row)]
        matched_groups = []
        for row in qualifying_rows:
            group = rule["group_for_row"](row)
            if group and group not in matched_groups:
                matched_groups.append(group)

        if not all(group in matched_groups for group in rule["required_groups"]):
            current_app.logger.info(
                "[TARGETED_CORRELATION] Skipped rule=%s | reason=missing_required_pattern | IP: %s",
                rule_alert_type,
                source_ip,
            )
            continue

        newest_alert = qualifying_rows[0]
        source = newest_alert[2] or "unknown"
        source_type = newest_alert[3] or "legacy"
        country = newest_alert[4]
        city = newest_alert[5]
        latitude = newest_alert[6]
        longitude = newest_alert[7]

        reputation = lookup_ip_reputation(str(source_ip))
        reputation_score = reputation["reputation_score"]
        response_action = determine_response_action(reputation_score)
        response_status = "pending"
        reputation_label = reputation["reputation_label"]
        reputation_source = reputation["reputation_source"]
        reputation_summary = reputation["reputation_summary"]

        cur.execute(
            """
            INSERT INTO alerts (
                source_ip,
                alert_type,
                severity,
                source,
                source_type,
                message,
                status,
                response_action,
                response_status,
                country,
                city,
                latitude,
                longitude,
                reputation_score,
                reputation_label,
                reputation_source,
                reputation_summary
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                source_ip,
                rule_alert_type,
                rule["severity"],
                source,
                source_type,
                rule["message"],
                "open",
                response_action,
                response_status,
                country,
                city,
                latitude,
                longitude,
                reputation_score,
                reputation_label,
                reputation_source,
                reputation_summary,
            ),
        )

        cur.execute("SELECT currval(pg_get_serial_sequence('alerts', 'id'))")
        alert_id = cur.fetchone()[0]

        current_app.logger.info(
            "[TARGETED_CORRELATION] Created rule=%s | IP: %s | matched_alerts=%d | sources=%s",
            rule_alert_type,
            source_ip,
            len(qualifying_rows),
            ", ".join(sorted({str(row[2]) for row in qualifying_rows if row[2]})),
        )

        alerts_created.append(
            _alert_result(
                alert_id,
                source_ip,
                response_action,
                rule["severity"],
                rule_alert_type,
                source,
                source_type,
            )
        )

    return alerts_created
