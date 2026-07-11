from flask import current_app
from psycopg2.extras import Json

from engines.detection_config import (
    PFSENSE_HIGH_REPUTATION_SCORE,
    PFSENSE_SEVERITY_ESCALATION_MULTIPLIER,
    get_effective_detection_rule,
)
from engines.pfsense_ingest_filter import get_effective_sensitive_ports
from core.ip_helpers import determine_response_action, lookup_ip_reputation


PFSENSE_ESCALATION_ALERT_TYPES = (
    "pfsense_firewall_repeated_deny",
    "pfsense_firewall_port_scan",
    "pfsense_firewall_suspicious_allow",
)
PFSENSE_NOISY_SOURCE_GUARD_ALERT_TYPES = PFSENSE_ESCALATION_ALERT_TYPES + (
    "pfsense_firewall_noisy_source",
)


def _pfsense_escalated_severity(base_severity, *, count, threshold, reputation_score):
    if base_severity != "medium":
        return base_severity
    if reputation_score is not None and reputation_score >= PFSENSE_HIGH_REPUTATION_SCORE:
        return "high"
    if threshold and count >= threshold * PFSENSE_SEVERITY_ESCALATION_MULTIPLIER:
        return "high"
    return "medium"


def _pfsense_response_action_for_severity(severity):
    if severity == "high":
        return "block_ip"
    if severity == "medium":
        return "enrich_source_ip"
    return "monitor_only"


# spec: SPEC-INGEST-001
def _generate_failed_login_alerts_core(cur, conn, source=None, source_type=None):
    rule_config = get_effective_detection_rule("failed_login_threshold", cur=cur)
    threshold = rule_config["parameters"]["threshold"]
    window_minutes = rule_config["parameters"]["window_minutes"]

    cur.execute(
        f"""
        SELECT source_ip, COUNT(*) as attempts
        FROM events
        WHERE event_type IN ('failed_login', 'login_failure', 'unauthorized_access')
        AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        GROUP BY source_ip
        HAVING COUNT(*) >= %s
        """,
        (threshold,)
    )

    rows = cur.fetchall()
    alerts_created = []

    for row in rows:
        source_ip = row[0]
        attempts = row[1]
        reputation = lookup_ip_reputation(str(source_ip))
        reputation_score = reputation["reputation_score"]
        response_action = determine_response_action(reputation_score)
        response_status = "pending"
        reputation_label = reputation["reputation_label"]
        reputation_source = reputation["reputation_source"]
        reputation_summary = reputation["reputation_summary"]


        cur.execute(
            """
            SELECT
                raw_payload->'location'->>'country',
                raw_payload->'location'->>'city',
                NULLIF(raw_payload->'location'->>'lat', '')::double precision,
                NULLIF(raw_payload->'location'->>'lon', '')::double precision
            FROM events
            WHERE source_ip = %s
              AND event_type IN ('failed_login', 'login_failure', 'unauthorized_access')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_ip,)
        )

        location_row = cur.fetchone()
        country = location_row[0] if location_row else None
        city = location_row[1] if location_row else None
        latitude = location_row[2] if location_row else None
        longitude = location_row[3] if location_row else None

        current_app.logger.info(
            "[ALERT LOCATION DEBUG] failed_login source_ip=%s country=%s city=%s latitude=%s longitude=%s",
            source_ip,
            country,
            city,
            latitude,
            longitude,
        )

        message = f"{attempts} failed login attempts detected from {source_ip}"

        cur.execute(
            """
            SELECT 1 FROM alerts
            WHERE source_ip = %s
            AND alert_type = %s
            AND status = 'open'
            """,
            (source_ip, "failed_login_threshold"),
        )

        if cur.fetchone():
            continue
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
                "failed_login_threshold",
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

        alerts_created.append(
            {
                "source_ip": source_ip,
                "attempts": attempts,
                "alert_id": alert_id,
                "response_action": response_action,
                "severity": "high",
            }
        )

    return alerts_created


def _generate_http_error_alerts_core(cur, conn, source=None, source_type=None):
    rule_config = get_effective_detection_rule("http_error_threshold", cur=cur)
    threshold = rule_config["parameters"]["threshold"]
    window_minutes = rule_config["parameters"]["window_minutes"]

    cur.execute(
        f"""
        SELECT source_ip, COUNT(*) as attempts
        FROM events
        WHERE event_type = 'http_error'
          AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        GROUP BY source_ip
        HAVING COUNT(*) >= %s
        """,
        (threshold,)
    )

    rows = cur.fetchall()
    alerts_created = []

    for row in rows:
        source_ip = row[0]
        attempts = row[1]
        reputation = lookup_ip_reputation(str(source_ip))
        reputation_score = reputation["reputation_score"]
        response_action = determine_response_action(reputation_score)
        response_status = "pending"
        reputation_label = reputation["reputation_label"]
        reputation_source = reputation["reputation_source"]
        reputation_summary = reputation["reputation_summary"]

        cur.execute(
            """
            SELECT
                raw_payload->'location'->>'country',
                raw_payload->'location'->>'city',
                NULLIF(raw_payload->'location'->>'lat', '')::double precision,
                NULLIF(raw_payload->'location'->>'lon', '')::double precision
            FROM events
            WHERE source_ip = %s
              AND event_type = 'http_error'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_ip,)
        )

        location_row = cur.fetchone()
        country = location_row[0] if location_row else None
        city = location_row[1] if location_row else None
        latitude = location_row[2] if location_row else None
        longitude = location_row[3] if location_row else None

        message = f"Repeated HTTP server errors detected from {source_ip}"

        cur.execute(
            """
            SELECT 1 FROM alerts
            WHERE source_ip = %s
              AND alert_type = %s
              AND status = 'open'
            """,
            (source_ip, "http_error_threshold"),
        )

        if cur.fetchone():
            continue

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
                "http_error_threshold",
                "medium",
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

        alerts_created.append(
            {
                "source_ip": source_ip,
                "attempts": attempts,
                "alert_id": alert_id,
                "response_action": response_action,
                "severity": "medium",
            }
        )

    return alerts_created


def _generate_port_scan_alerts_core(cur, conn, source=None, source_type=None):
    rule_config = get_effective_detection_rule("port_scan_threshold", cur=cur)
    threshold = rule_config["parameters"]["threshold"]
    window_minutes = rule_config["parameters"]["window_minutes"]

    cur.execute(
        f"""
        WITH port_scan_events AS (
            SELECT
                source_ip,
                COALESCE(
                    raw_payload->>'destination_port',
                    raw_payload->>'dest_port',
                    raw_payload->>'dst_port',
                    raw_payload->>'port'
                ) AS destination_port_text
            FROM events
            WHERE event_type = 'port_scan'
              AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        ),
        normalized_ports AS (
            SELECT
                source_ip,
                CASE
                    WHEN destination_port_text ~ '^\\d{{1,5}}$'
                    THEN destination_port_text::integer
                    ELSE NULL
                END AS destination_port
            FROM port_scan_events
        )
        SELECT source_ip, COUNT(DISTINCT destination_port) as attempts
        FROM normalized_ports
        WHERE destination_port BETWEEN 1 AND 65535
        GROUP BY source_ip
        HAVING COUNT(DISTINCT destination_port) >= %s
        """,
        (threshold,)
    )

    rows = cur.fetchall()
    alerts_created = []

    for row in rows:
        source_ip = row[0]
        attempts = row[1]
        reputation = lookup_ip_reputation(str(source_ip))
        reputation_score = reputation["reputation_score"]
        response_action = determine_response_action(reputation_score)
        response_status = "pending"
        reputation_label = reputation["reputation_label"]
        reputation_source = reputation["reputation_source"]
        reputation_summary = reputation["reputation_summary"]

        cur.execute(
            """
            SELECT
                raw_payload->'location'->>'country',
                raw_payload->'location'->>'city',
                NULLIF(raw_payload->'location'->>'lat', '')::double precision,
                NULLIF(raw_payload->'location'->>'lon', '')::double precision
            FROM events
            WHERE source_ip = %s
              AND event_type = 'port_scan'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_ip,)
        )

        location_row = cur.fetchone()
        country = location_row[0] if location_row else None
        city = location_row[1] if location_row else None
        latitude = location_row[2] if location_row else None
        longitude = location_row[3] if location_row else None

        current_app.logger.info(
            "[ALERT LOCATION DEBUG] port_scan source_ip=%s country=%s city=%s latitude=%s longitude=%s",
            source_ip,
            country,
            city,
            latitude,
            longitude,
        )

        message = f"{attempts} port scan events detected from {source_ip}"

        cur.execute(
            """
            SELECT 1 FROM alerts
            WHERE source_ip = %s
              AND alert_type = %s
              AND status = 'open'
            """,
            (source_ip, "port_scan_threshold"),
        )

        if cur.fetchone():
            continue

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
                "port_scan_threshold",
                "medium",
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

        alerts_created.append(
            {
                "source_ip": source_ip,
                "attempts": attempts,
                "alert_id": alert_id,
                "response_action": response_action,
                "severity": "medium",
            }
        )

    return alerts_created


def _generate_password_spraying_alerts_core(cur, conn, source=None, source_type=None):
    rule_config = get_effective_detection_rule("password_spraying_threshold", cur=cur)
    threshold = rule_config["parameters"]["threshold"]
    window_minutes = rule_config["parameters"]["window_minutes"]

    cur.execute(
        f"""
        WITH extracted_failed_logins AS (
            SELECT
                source_ip,
                NULLIF(
                    LOWER(
                        TRIM(
                            COALESCE(
                                raw_payload->>'username',
                                SUBSTRING(raw_payload->>'message' FROM 'Failed login attempt for username:\\s*([^,;]+)')
                            )
                        )
                    ),
                    ''
                ) AS extracted_username
            FROM events
            WHERE event_type = 'failed_login'
              AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        )
        SELECT source_ip, COUNT(DISTINCT extracted_username) AS distinct_username_count
        FROM extracted_failed_logins
        WHERE extracted_username IS NOT NULL
        GROUP BY source_ip
        HAVING COUNT(DISTINCT extracted_username) >= %s
        """,
        (threshold,)
    )

    rows = cur.fetchall()
    alerts_created = []

    for row in rows:
        source_ip = row[0]
        distinct_username_count = row[1]
        reputation = lookup_ip_reputation(str(source_ip))
        reputation_score = reputation["reputation_score"]
        response_action = determine_response_action(reputation_score)
        response_status = "pending"
        reputation_label = reputation["reputation_label"]
        reputation_source = reputation["reputation_source"]
        reputation_summary = reputation["reputation_summary"]

        cur.execute(
            """
            SELECT
                raw_payload->'location'->>'country',
                raw_payload->'location'->>'city',
                NULLIF(raw_payload->'location'->>'lat', '')::double precision,
                NULLIF(raw_payload->'location'->>'lon', '')::double precision
            FROM events
            WHERE source_ip = %s
              AND event_type = 'failed_login'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_ip,)
        )

        location_row = cur.fetchone()
        country = location_row[0] if location_row else None
        city = location_row[1] if location_row else None
        latitude = location_row[2] if location_row else None
        longitude = location_row[3] if location_row else None

        message = (
            f"Password spraying suspected from {source_ip}: "
            f"failed logins across {distinct_username_count} usernames"
        )

        cur.execute(
            """
            SELECT 1 FROM alerts
            WHERE source_ip = %s
              AND alert_type = %s
              AND status = 'open'
            """,
            (source_ip, "password_spraying_threshold"),
        )

        if cur.fetchone():
            continue

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
                "password_spraying_threshold",
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

        alerts_created.append(
            {
                "source_ip": source_ip,
                "distinct_username_count": distinct_username_count,
                "alert_id": alert_id,
                "response_action": response_action,
                "severity": "high",
            }
        )

    return alerts_created


def _generate_successful_login_after_spray_alerts_core(cur, conn, source=None, source_type=None):
    rule_config = get_effective_detection_rule("successful_login_after_spray", cur=cur)
    threshold = rule_config["parameters"]["threshold"]
    success_window_minutes = rule_config["parameters"]["success_window_minutes"]
    failed_lookback_minutes = rule_config["parameters"]["failed_lookback_minutes"]
    correlation_window_minutes = rule_config["parameters"]["correlation_window_minutes"]

    cur.execute(
        f"""
        WITH recent_successes AS (
            SELECT source_ip, created_at AS success_at
            FROM events
            WHERE event_type = 'successful_login'
              AND created_at >= NOW() - INTERVAL '{success_window_minutes} minutes'
        ),
        extracted_failed_logins AS (
            SELECT
                source_ip,
                created_at,
                NULLIF(
                    LOWER(
                        TRIM(
                            COALESCE(
                                raw_payload->>'username',
                                SUBSTRING(raw_payload->>'message' FROM 'Failed login attempt for username:\\s*([^,;]+)')
                            )
                        )
                    ),
                    ''
                ) AS extracted_username
            FROM events
            WHERE event_type = 'failed_login'
              AND created_at >= NOW() - INTERVAL '{failed_lookback_minutes} minutes'
        ),
        qualifying_successes AS (
            SELECT
                recent_successes.source_ip,
                MAX(recent_successes.success_at) AS success_at
            FROM recent_successes
            JOIN extracted_failed_logins
              ON extracted_failed_logins.source_ip = recent_successes.source_ip
             AND extracted_failed_logins.extracted_username IS NOT NULL
             AND extracted_failed_logins.created_at >= recent_successes.success_at - INTERVAL '{correlation_window_minutes} minutes'
             AND extracted_failed_logins.created_at <= recent_successes.success_at
            GROUP BY recent_successes.source_ip, recent_successes.success_at
            HAVING COUNT(DISTINCT extracted_failed_logins.extracted_username) >= %s
        )
        SELECT source_ip, success_at
        FROM qualifying_successes
        """,
        (threshold,)
    )

    rows = cur.fetchall()
    alerts_created = []

    for row in rows:
        source_ip = row[0]
        success_at = row[1]
        reputation = lookup_ip_reputation(str(source_ip))
        reputation_score = reputation["reputation_score"]
        response_action = determine_response_action(reputation_score)
        response_status = "pending"
        reputation_label = reputation["reputation_label"]
        reputation_source = reputation["reputation_source"]
        reputation_summary = reputation["reputation_summary"]

        cur.execute(
            """
            SELECT
                raw_payload->'location'->>'country',
                raw_payload->'location'->>'city',
                NULLIF(raw_payload->'location'->>'lat', '')::double precision,
                NULLIF(raw_payload->'location'->>'lon', '')::double precision
            FROM events
            WHERE source_ip = %s
              AND event_type IN ('successful_login', 'failed_login')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_ip,)
        )

        location_row = cur.fetchone()
        country = location_row[0] if location_row else None
        city = location_row[1] if location_row else None
        latitude = location_row[2] if location_row else None
        longitude = location_row[3] if location_row else None

        cur.execute(
            """
            SELECT 1 FROM alerts
            WHERE source_ip = %s
              AND alert_type = %s
              AND status = 'open'
            """,
            (source_ip, "successful_login_after_spray"),
        )

        if cur.fetchone():
            continue

        message = f"Successful login after password spraying detected from {source_ip}"

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
                "successful_login_after_spray",
                "critical",
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

        alerts_created.append(
            {
                "source_ip": source_ip,
                "success_at": str(success_at),
                "alert_id": alert_id,
                "response_action": response_action,
                "severity": "critical",
            }
        )

    return alerts_created


def _generate_application_exception_alerts_core(cur, conn, source=None, source_type=None):
    rule_config = get_effective_detection_rule("application_exception_threshold", cur=cur)
    threshold = rule_config["parameters"]["threshold"]
    window_minutes = rule_config["parameters"]["window_minutes"]

    cur.execute(
        f"""
        SELECT source_ip, COUNT(*) as attempts
        FROM events
        WHERE event_type = 'application_exception'
          AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        GROUP BY source_ip
        HAVING COUNT(*) >= %s
        """,
        (threshold,)
    )

    rows = cur.fetchall()
    alerts_created = []

    for row in rows:
        source_ip = row[0]
        attempts = row[1]
        reputation = lookup_ip_reputation(str(source_ip))
        reputation_score = reputation["reputation_score"]
        response_action = determine_response_action(reputation_score)
        response_status = "pending"
        reputation_label = reputation["reputation_label"]
        reputation_source = reputation["reputation_source"]
        reputation_summary = reputation["reputation_summary"]

        cur.execute(
            """
            SELECT
                raw_payload->'location'->>'country',
                raw_payload->'location'->>'city',
                NULLIF(raw_payload->'location'->>'lat', '')::double precision,
                NULLIF(raw_payload->'location'->>'lon', '')::double precision
            FROM events
            WHERE source_ip = %s
              AND event_type = 'application_exception'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_ip,)
        )

        location_row = cur.fetchone()
        country = location_row[0] if location_row else None
        city = location_row[1] if location_row else None
        latitude = location_row[2] if location_row else None
        longitude = location_row[3] if location_row else None

        message = f"Repeated application exceptions detected from {source_ip}"

        cur.execute(
            """
            SELECT 1 FROM alerts
            WHERE source_ip = %s
              AND alert_type = %s
              AND status = 'open'
            """,
            (source_ip, "application_exception_threshold"),
        )

        if cur.fetchone():
            continue

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
                "application_exception_threshold",
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

        alerts_created.append(
            {
                "source_ip": source_ip,
                "attempts": attempts,
                "alert_id": alert_id,
                "response_action": response_action,
                "severity": "high",
            }
        )

    return alerts_created


def _generate_high_request_rate_alerts_core(cur, conn, source=None, source_type=None):
    rule_config = get_effective_detection_rule("high_request_rate_threshold", cur=cur)
    threshold = rule_config["parameters"]["threshold"]
    window_minutes = rule_config["parameters"]["window_minutes"]

    cur.execute(
        f"""
        SELECT source_ip, COUNT(*) as attempts
        FROM events
        WHERE event_type IN ('normal_activity', 'unauthorized_access', 'http_error')
          AND source_type IN ('web_log', 'telemetry')
          AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        GROUP BY source_ip
        HAVING COUNT(*) >= %s
        """,
        (threshold,)
    )

    rows = cur.fetchall()
    alerts_created = []

    for row in rows:
        source_ip = row[0]
        attempts = row[1]
        reputation = lookup_ip_reputation(str(source_ip))
        reputation_score = reputation["reputation_score"]
        response_action = determine_response_action(reputation_score)
        response_status = "pending"
        reputation_label = reputation["reputation_label"]
        reputation_source = reputation["reputation_source"]
        reputation_summary = reputation["reputation_summary"]

        cur.execute(
            """
            SELECT
                raw_payload->'location'->>'country',
                raw_payload->'location'->>'city',
                NULLIF(raw_payload->'location'->>'lat', '')::double precision,
                NULLIF(raw_payload->'location'->>'lon', '')::double precision
            FROM events
            WHERE source_ip = %s
              AND event_type IN ('normal_activity', 'unauthorized_access', 'http_error')
              AND source_type IN ('web_log', 'telemetry')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_ip,)
        )

        location_row = cur.fetchone()
        country = location_row[0] if location_row else None
        city = location_row[1] if location_row else None
        latitude = location_row[2] if location_row else None
        longitude = location_row[3] if location_row else None

        message = f"High request rate detected from {source_ip}"

        cur.execute(
            """
            SELECT 1 FROM alerts
            WHERE source_ip = %s
              AND alert_type = %s
              AND status = 'open'
            """,
            (source_ip, "high_request_rate_threshold"),
        )

        if cur.fetchone():
            continue

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
                "high_request_rate_threshold",
                "medium",
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

        alerts_created.append(
            {
                "source_ip": source_ip,
                "attempts": attempts,
                "alert_id": alert_id,
                "response_action": response_action,
                "severity": "medium",
            }
        )

    return alerts_created


def _fetch_latest_honeypot_location(cur, source_ip, event_type):
    cur.execute(
        """
        SELECT
            raw_payload->'location'->>'country',
            raw_payload->'location'->>'city',
            NULLIF(raw_payload->'location'->>'lat', '')::double precision,
            NULLIF(raw_payload->'location'->>'lon', '')::double precision
        FROM events
        WHERE source_ip = %s
          AND event_type = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (source_ip, event_type),
    )
    location_row = cur.fetchone()
    if not location_row:
        return None, None, None, None
    return location_row[0], location_row[1], location_row[2], location_row[3]


def _generate_env_probe_alerts_core(cur, conn, source=None, source_type=None):
    rule_config = get_effective_detection_rule("honeypot_env_probe_threshold", cur=cur)
    threshold = rule_config["parameters"]["threshold"]
    window_minutes = rule_config["parameters"]["window_minutes"]

    cur.execute(
        f"""
        WITH extracted_paths AS (
            SELECT
                source_ip,
                NULLIF(LOWER(TRIM(raw_payload->>'path')), '') AS normalized_path
            FROM events
            WHERE event_type = 'env_probe'
              AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        )
        SELECT source_ip, COUNT(DISTINCT normalized_path) AS distinct_path_count
        FROM extracted_paths
        WHERE normalized_path IS NOT NULL
        GROUP BY source_ip
        HAVING COUNT(DISTINCT normalized_path) >= %s
        """,
        (threshold,),
    )

    rows = cur.fetchall()
    alerts_created = []

    for row in rows:
        source_ip = row[0]
        distinct_path_count = row[1]
        reputation = lookup_ip_reputation(str(source_ip))
        reputation_score = reputation["reputation_score"]
        response_action = determine_response_action(reputation_score)
        response_status = "pending"
        reputation_label = reputation["reputation_label"]
        reputation_source = reputation["reputation_source"]
        reputation_summary = reputation["reputation_summary"]
        country, city, latitude, longitude = _fetch_latest_honeypot_location(cur, source_ip, "env_probe")

        message = (
            f"Sensitive file probing detected from {source_ip}: "
            f"{distinct_path_count} distinct paths"
        )

        cur.execute(
            """
            SELECT 1 FROM alerts
            WHERE source_ip = %s
              AND alert_type = %s
              AND status = 'open'
            """,
            (source_ip, "honeypot_env_probe_threshold"),
        )

        if cur.fetchone():
            continue

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
                "honeypot_env_probe_threshold",
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

        alerts_created.append(
            {
                "source_ip": source_ip,
                "distinct_path_count": distinct_path_count,
                "alert_id": alert_id,
                "response_action": response_action,
                "severity": "high",
            }
        )

    return alerts_created


def _generate_admin_probe_alerts_core(cur, conn, source=None, source_type=None):
    rule_config = get_effective_detection_rule("honeypot_admin_probe_threshold", cur=cur)
    threshold = rule_config["parameters"]["threshold"]
    window_minutes = rule_config["parameters"]["window_minutes"]

    cur.execute(
        f"""
        WITH extracted_paths AS (
            SELECT
                source_ip,
                NULLIF(LOWER(TRIM(raw_payload->>'path')), '') AS normalized_path
            FROM events
            WHERE event_type = 'admin_probe'
              AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        )
        SELECT source_ip, COUNT(DISTINCT normalized_path) AS distinct_path_count
        FROM extracted_paths
        WHERE normalized_path IS NOT NULL
        GROUP BY source_ip
        HAVING COUNT(DISTINCT normalized_path) >= %s
        """,
        (threshold,),
    )

    rows = cur.fetchall()
    alerts_created = []

    for row in rows:
        source_ip = row[0]
        distinct_path_count = row[1]
        reputation = lookup_ip_reputation(str(source_ip))
        reputation_score = reputation["reputation_score"]
        response_action = determine_response_action(reputation_score)
        response_status = "pending"
        reputation_label = reputation["reputation_label"]
        reputation_source = reputation["reputation_source"]
        reputation_summary = reputation["reputation_summary"]
        country, city, latitude, longitude = _fetch_latest_honeypot_location(cur, source_ip, "admin_probe")

        message = (
            f"Admin panel probing detected from {source_ip}: "
            f"{distinct_path_count} distinct paths"
        )

        cur.execute(
            """
            SELECT 1 FROM alerts
            WHERE source_ip = %s
              AND alert_type = %s
              AND status = 'open'
            """,
            (source_ip, "honeypot_admin_probe_threshold"),
        )

        if cur.fetchone():
            continue

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
                "honeypot_admin_probe_threshold",
                "medium",
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

        alerts_created.append(
            {
                "source_ip": source_ip,
                "distinct_path_count": distinct_path_count,
                "alert_id": alert_id,
                "response_action": response_action,
                "severity": "medium",
            }
        )

    return alerts_created


def _generate_scanner_detected_alerts_core(cur, conn, source=None, source_type=None):
    rule_config = get_effective_detection_rule("honeypot_scanner_detected", cur=cur)
    threshold = rule_config["parameters"]["threshold"]
    window_minutes = rule_config["parameters"]["window_minutes"]

    cur.execute(
        f"""
        SELECT source_ip, COUNT(*) AS scanner_events
        FROM events
        WHERE event_type = 'scanner_detected'
          AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        GROUP BY source_ip
        HAVING COUNT(*) >= %s
        """,
        (threshold,),
    )

    rows = cur.fetchall()
    alerts_created = []

    for row in rows:
        source_ip = row[0]
        scanner_events = row[1]
        reputation = lookup_ip_reputation(str(source_ip))
        reputation_score = reputation["reputation_score"]
        response_action = determine_response_action(reputation_score)
        response_status = "pending"
        reputation_label = reputation["reputation_label"]
        reputation_source = reputation["reputation_source"]
        reputation_summary = reputation["reputation_summary"]
        country, city, latitude, longitude = _fetch_latest_honeypot_location(cur, source_ip, "scanner_detected")

        message = f"Scanner activity detected from {source_ip}: {scanner_events} scanner events"

        cur.execute(
            """
            SELECT 1 FROM alerts
            WHERE source_ip = %s
              AND alert_type = %s
              AND status = 'open'
            """,
            (source_ip, "honeypot_scanner_detected"),
        )

        if cur.fetchone():
            continue

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
                "honeypot_scanner_detected",
                "medium",
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

        alerts_created.append(
            {
                "source_ip": source_ip,
                "scanner_events": scanner_events,
                "alert_id": alert_id,
                "response_action": response_action,
                "severity": "medium",
            }
        )

    return alerts_created


def _generate_credential_stuffing_alerts_core(cur, conn, source=None, source_type=None):
    rule_config = get_effective_detection_rule("honeypot_credential_stuffing_threshold", cur=cur)
    threshold = rule_config["parameters"]["threshold"]
    window_minutes = rule_config["parameters"]["window_minutes"]

    cur.execute(
        f"""
        WITH extracted_usernames AS (
            SELECT
                source_ip,
                NULLIF(LOWER(TRIM(raw_payload->>'username')), '') AS normalized_username
            FROM events
            WHERE event_type = 'credential_stuffing'
              AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        )
        SELECT source_ip, COUNT(DISTINCT normalized_username) AS distinct_username_count
        FROM extracted_usernames
        WHERE normalized_username IS NOT NULL
        GROUP BY source_ip
        HAVING COUNT(DISTINCT normalized_username) >= %s
        """,
        (threshold,),
    )

    rows = cur.fetchall()
    alerts_created = []

    for row in rows:
        source_ip = row[0]
        distinct_username_count = row[1]
        reputation = lookup_ip_reputation(str(source_ip))
        reputation_score = reputation["reputation_score"]
        response_action = determine_response_action(reputation_score)
        response_status = "pending"
        reputation_label = reputation["reputation_label"]
        reputation_source = reputation["reputation_source"]
        reputation_summary = reputation["reputation_summary"]
        country, city, latitude, longitude = _fetch_latest_honeypot_location(
            cur,
            source_ip,
            "credential_stuffing",
        )

        message = (
            f"Credential stuffing suspected from {source_ip}: "
            f"{distinct_username_count} distinct usernames"
        )

        cur.execute(
            """
            SELECT 1 FROM alerts
            WHERE source_ip = %s
              AND alert_type = %s
              AND status = 'open'
            """,
            (source_ip, "honeypot_credential_stuffing_threshold"),
        )

        if cur.fetchone():
            continue

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
                "honeypot_credential_stuffing_threshold",
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

        alerts_created.append(
            {
                "source_ip": source_ip,
                "distinct_username_count": distinct_username_count,
                "alert_id": alert_id,
                "response_action": response_action,
                "severity": "high",
            }
        )

    return alerts_created


def _generate_pfsense_repeated_deny_alerts_core(cur, conn, source=None, source_type=None):
    rule_config = get_effective_detection_rule("pfsense_firewall_repeated_deny", cur=cur)
    threshold = rule_config["parameters"]["threshold"]
    window_minutes = rule_config["parameters"]["window_minutes"]

    cur.execute(
        f"""
        SELECT
            source_ip,
            raw_payload->>'destination_ip' AS destination_ip,
            raw_payload->>'destination_port' AS destination_port,
            raw_payload->>'protocol' AS protocol,
            raw_payload->>'interface' AS interface,
            raw_payload->>'direction' AS direction,
            COUNT(*) AS event_count,
            MIN(created_at) AS first_seen,
            MAX(created_at) AS last_seen
        FROM events
        WHERE event_type = 'firewall_block'
          AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        GROUP BY source_ip, destination_ip, destination_port, protocol, interface, direction
        HAVING COUNT(*) >= %s
        """,
        (threshold,),
    )

    rows = cur.fetchall()
    alerts_created = []

    for row in rows:
        (
            source_ip,
            destination_ip,
            destination_port,
            protocol,
            interface,
            direction,
            event_count,
            first_seen,
            last_seen,
        ) = row

        cur.execute(
            """
            SELECT 1 FROM alerts
            WHERE source_ip = %s
              AND alert_type = %s
              AND status = 'open'
            """,
            (source_ip, "pfsense_firewall_repeated_deny"),
        )
        if cur.fetchone():
            continue

        reputation = lookup_ip_reputation(str(source_ip))
        reputation_score = reputation["reputation_score"]
        reputation_label = reputation["reputation_label"]
        reputation_source = reputation["reputation_source"]
        reputation_summary = reputation["reputation_summary"]

        severity = _pfsense_escalated_severity(
            "medium",
            count=event_count,
            threshold=threshold,
            reputation_score=reputation_score,
        )
        response_action = _pfsense_response_action_for_severity(severity)
        response_status = "pending"

        country, city, latitude, longitude = _fetch_latest_honeypot_location(cur, source_ip, "firewall_block")

        destination_text = destination_ip or "unknown destination"
        if destination_port:
            destination_text = f"{destination_text}:{destination_port}"
        message = (
            f"pfSense blocked {event_count} connections from {source_ip} to "
            f"{destination_text} ({protocol or 'unknown protocol'})"
        )

        context = {
            "action": "block",
            "destination_ip": destination_ip,
            "destination_port": destination_port,
            "protocol": protocol,
            "interface": interface,
            "direction": direction,
            "event_count": event_count,
            "first_seen": str(first_seen) if first_seen else None,
            "last_seen": str(last_seen) if last_seen else None,
        }

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
                reputation_summary,
                context
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                source_ip,
                "pfsense_firewall_repeated_deny",
                severity,
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
                Json(context),
            ),
        )

        cur.execute("SELECT currval(pg_get_serial_sequence('alerts', 'id'))")
        alert_id = cur.fetchone()[0]

        alerts_created.append(
            {
                "source_ip": source_ip,
                "event_count": event_count,
                "alert_id": alert_id,
                "response_action": response_action,
                "severity": severity,
            }
        )

    return alerts_created


def _generate_pfsense_port_scan_alerts_core(cur, conn, source=None, source_type=None):
    rule_config = get_effective_detection_rule("pfsense_firewall_port_scan", cur=cur)
    threshold = rule_config["parameters"]["threshold"]
    window_minutes = rule_config["parameters"]["window_minutes"]

    cur.execute(
        f"""
        WITH scan_events AS (
            SELECT
                source_ip,
                raw_payload->>'destination_ip' AS destination_ip,
                raw_payload->>'destination_port' AS destination_port_text,
                created_at
            FROM events
            WHERE event_type = 'firewall_block'
              AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        ),
        normalized_ports AS (
            SELECT
                source_ip,
                destination_ip,
                created_at,
                CASE
                    WHEN destination_port_text ~ '^\\d{{1,5}}$'
                    THEN destination_port_text::integer
                    ELSE NULL
                END AS destination_port
            FROM scan_events
        )
        SELECT
            source_ip,
            COUNT(DISTINCT destination_port) AS distinct_port_count,
            COUNT(DISTINCT destination_ip) AS distinct_destination_count,
            MIN(created_at) AS first_seen,
            MAX(created_at) AS last_seen
        FROM normalized_ports
        WHERE destination_port BETWEEN 1 AND 65535
        GROUP BY source_ip
        HAVING COUNT(DISTINCT destination_port) >= %s
        """,
        (threshold,),
    )

    rows = cur.fetchall()
    alerts_created = []

    for row in rows:
        source_ip, distinct_port_count, distinct_destination_count, first_seen, last_seen = row

        cur.execute(
            """
            SELECT 1 FROM alerts
            WHERE source_ip = %s
              AND alert_type = %s
              AND status = 'open'
            """,
            (source_ip, "pfsense_firewall_port_scan"),
        )
        if cur.fetchone():
            continue

        reputation = lookup_ip_reputation(str(source_ip))
        reputation_score = reputation["reputation_score"]
        reputation_label = reputation["reputation_label"]
        reputation_source = reputation["reputation_source"]
        reputation_summary = reputation["reputation_summary"]

        severity = _pfsense_escalated_severity(
            "medium",
            count=distinct_port_count,
            threshold=threshold,
            reputation_score=reputation_score,
        )
        response_action = _pfsense_response_action_for_severity(severity)
        response_status = "pending"

        country, city, latitude, longitude = _fetch_latest_honeypot_location(cur, source_ip, "firewall_block")

        message = (
            f"pfSense firewall port scan suspected from {source_ip}: "
            f"{distinct_port_count} distinct destination ports"
        )

        context = {
            "action": "block",
            "distinct_port_count": distinct_port_count,
            "distinct_destination_count": distinct_destination_count,
            "event_count": distinct_port_count,
            "first_seen": str(first_seen) if first_seen else None,
            "last_seen": str(last_seen) if last_seen else None,
        }

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
                reputation_summary,
                context
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                source_ip,
                "pfsense_firewall_port_scan",
                severity,
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
                Json(context),
            ),
        )

        cur.execute("SELECT currval(pg_get_serial_sequence('alerts', 'id'))")
        alert_id = cur.fetchone()[0]

        alerts_created.append(
            {
                "source_ip": source_ip,
                "distinct_port_count": distinct_port_count,
                "alert_id": alert_id,
                "response_action": response_action,
                "severity": severity,
            }
        )

    return alerts_created


def _generate_pfsense_suspicious_allow_alerts_core(cur, conn, source=None, source_type=None):
    rule_config = get_effective_detection_rule("pfsense_firewall_suspicious_allow", cur=cur)
    threshold = rule_config["parameters"]["threshold"]
    window_minutes = rule_config["parameters"]["window_minutes"]
    sensitive_ports = list(get_effective_sensitive_ports(cur))

    cur.execute(
        f"""
        WITH allow_events AS (
            SELECT
                source_ip,
                raw_payload->>'destination_ip' AS destination_ip,
                raw_payload->>'destination_port' AS destination_port_text,
                raw_payload->>'protocol' AS protocol,
                raw_payload->>'interface' AS interface,
                COALESCE(raw_payload->>'direction', '') AS direction,
                created_at
            FROM events
            WHERE event_type = 'firewall_allow'
              AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        ),
        qualifying_events AS (
            SELECT *
            FROM allow_events
            WHERE direction = 'in'
              AND destination_port_text ~ '^\\d{{1,5}}$'
              AND destination_port_text::integer = ANY(%s)
        )
        SELECT
            source_ip,
            COUNT(*) AS event_count,
            MIN(created_at) AS first_seen,
            MAX(created_at) AS last_seen,
            (ARRAY_AGG(destination_ip ORDER BY created_at DESC))[1] AS destination_ip,
            (ARRAY_AGG(destination_port_text ORDER BY created_at DESC))[1] AS destination_port,
            (ARRAY_AGG(protocol ORDER BY created_at DESC))[1] AS protocol,
            (ARRAY_AGG(interface ORDER BY created_at DESC))[1] AS interface
        FROM qualifying_events
        GROUP BY source_ip
        HAVING COUNT(*) >= %s
        """,
        (sensitive_ports, threshold),
    )

    rows = cur.fetchall()
    alerts_created = []

    for row in rows:
        (
            source_ip,
            event_count,
            first_seen,
            last_seen,
            destination_ip,
            destination_port,
            protocol,
            interface,
        ) = row

        cur.execute(
            """
            SELECT 1 FROM alerts
            WHERE source_ip = %s
              AND alert_type = %s
              AND status = 'open'
            """,
            (source_ip, "pfsense_firewall_suspicious_allow"),
        )
        if cur.fetchone():
            continue

        reputation = lookup_ip_reputation(str(source_ip))
        reputation_score = reputation["reputation_score"]
        reputation_label = reputation["reputation_label"]
        reputation_source = reputation["reputation_source"]
        reputation_summary = reputation["reputation_summary"]

        # A single allow of inbound traffic to a sensitive management port is
        # treated as high-confidence per the pfsense-firewall-detections-soar
        # spec's "contextual allow" guidance, independent of reputation.
        severity = "high"
        response_action = _pfsense_response_action_for_severity(severity)
        response_status = "pending"

        country, city, latitude, longitude = _fetch_latest_honeypot_location(cur, source_ip, "firewall_allow")

        message = (
            f"pfSense allowed inbound traffic from {source_ip} to sensitive port "
            f"{destination_port} ({protocol or 'unknown protocol'})"
        )

        context = {
            "action": "pass",
            "destination_ip": destination_ip,
            "destination_port": destination_port,
            "protocol": protocol,
            "interface": interface,
            "direction": "in",
            "event_count": event_count,
            "first_seen": str(first_seen) if first_seen else None,
            "last_seen": str(last_seen) if last_seen else None,
        }

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
                reputation_summary,
                context
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                source_ip,
                "pfsense_firewall_suspicious_allow",
                severity,
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
                Json(context),
            ),
        )

        cur.execute("SELECT currval(pg_get_serial_sequence('alerts', 'id'))")
        alert_id = cur.fetchone()[0]

        alerts_created.append(
            {
                "source_ip": source_ip,
                "event_count": event_count,
                "alert_id": alert_id,
                "response_action": response_action,
                "severity": severity,
            }
        )

    return alerts_created


def _generate_pfsense_noisy_source_alerts_core(cur, conn, source=None, source_type=None):
    rule_config = get_effective_detection_rule("pfsense_firewall_noisy_source", cur=cur)
    threshold = rule_config["parameters"]["threshold"]
    window_minutes = rule_config["parameters"]["window_minutes"]

    cur.execute(
        f"""
        SELECT
            source_ip,
            COUNT(*) AS event_count,
            MIN(created_at) AS first_seen,
            MAX(created_at) AS last_seen
        FROM events
        WHERE event_type IN ('firewall_block', 'firewall_allow')
          AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        GROUP BY source_ip
        HAVING COUNT(*) >= %s
        """,
        (threshold,),
    )

    rows = cur.fetchall()
    alerts_created = []

    for row in rows:
        source_ip, event_count, first_seen, last_seen = row

        # Suppress this roll-up if the source already has an open alert of any
        # pfSense firewall type, escalated or otherwise, so noisy-source noise
        # never masks or duplicates a more specific detection.
        cur.execute(
            """
            SELECT 1 FROM alerts
            WHERE source_ip = %s
              AND status = 'open'
              AND alert_type IN %s
            """,
            (source_ip, PFSENSE_NOISY_SOURCE_GUARD_ALERT_TYPES),
        )
        if cur.fetchone():
            continue

        reputation = lookup_ip_reputation(str(source_ip))
        reputation_score = reputation["reputation_score"]
        reputation_label = reputation["reputation_label"]
        reputation_source = reputation["reputation_source"]
        reputation_summary = reputation["reputation_summary"]

        severity = "low"
        response_action = "suppress_noisy_source"
        response_status = "pending"

        country, city, latitude, longitude = _fetch_latest_honeypot_location(cur, source_ip, "firewall_block")

        message = f"pfSense firewall noise suppressed from {source_ip}: {event_count} routine events"

        context = {
            "event_count": event_count,
            "first_seen": str(first_seen) if first_seen else None,
            "last_seen": str(last_seen) if last_seen else None,
            "suppressed": True,
        }

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
                reputation_summary,
                context
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                source_ip,
                "pfsense_firewall_noisy_source",
                severity,
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
                Json(context),
            ),
        )

        cur.execute("SELECT currval(pg_get_serial_sequence('alerts', 'id'))")
        alert_id = cur.fetchone()[0]

        alerts_created.append(
            {
                "source_ip": source_ip,
                "event_count": event_count,
                "alert_id": alert_id,
                "response_action": response_action,
                "severity": severity,
            }
        )

    return alerts_created
