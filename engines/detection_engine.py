from flask import current_app
from psycopg2.extras import Json

from engines.detection_config import (
    PFSENSE_ALERT_COOLDOWN_MINUTES,
    PFSENSE_HIGH_REPUTATION_SCORE,
    PFSENSE_PORT_SCAN_HOST_THRESHOLD,
    PFSENSE_SEVERITY_ESCALATION_MULTIPLIER,
    PFSENSE_SUSPICIOUS_ALLOW_DISTINCT_PORT_ESCALATION_THRESHOLD,
    PFSENSE_SUSPICIOUS_ALLOW_HIGH_CONFIDENCE_REPEAT_THRESHOLD,
    get_effective_detection_rule,
)
from engines.detection_applicability import rule_applies_to_source
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

# Ordinal ranking used only to decide whether a post-closure recurrence is an
# escalation (breaks cooldown suppression) or an equal-or-lower-severity repeat
# (stays suppressed for PFSENSE_ALERT_COOLDOWN_MINUTES).
_PFSENSE_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _pfsense_cooldown_suppresses(cur, source_ip, alert_type, candidate_severity):
    """True when a resolved alert for this (source_ip, alert_type) closed within
    the cooldown window at a severity at or above the new candidate's severity.

    A strictly higher-severity candidate always breaks through (escalation
    breakout); this mirrors the noisy-source rule's existing
    "suppression breaks on escalation" pattern rather than introducing a new one.
    Derives closure time from the existing alert-status audit trail
    (`audit_log`) so no new persisted timestamp column is required.
    """
    cur.execute(
        f"""
        SELECT a.severity
        FROM alerts a
        JOIN audit_log al ON al.target_alert_id = a.id
        WHERE a.source_ip = %s
          AND a.alert_type = %s
          AND a.status = 'resolved'
          AND al.event_type = 'UPDATE_ALERT_STATUS'
          AND (al.details->>'status') = 'resolved'
          AND al.created_at >= NOW() - INTERVAL '{int(PFSENSE_ALERT_COOLDOWN_MINUTES)} minutes'
        ORDER BY al.created_at DESC
        LIMIT 1
        """,
        (source_ip, alert_type),
    )
    row = cur.fetchone()
    if row is None:
        return False
    last_closed_severity = row[0]
    return (
        _PFSENSE_SEVERITY_RANK.get(candidate_severity, 0)
        <= _PFSENSE_SEVERITY_RANK.get(last_closed_severity, 0)
    )


def _prepare_rule_evaluation(rule_id, cur, source, source_type, rule_config):
    """Guard direct detector calls as well as orchestrated execution."""
    if not rule_applies_to_source(rule_id, source, source_type):
        return None
    effective = rule_config or get_effective_detection_rule(rule_id, cur=cur)
    return effective if effective["active"] else None


def _resolve_evaluation_source_ip(cur, source_ip, source, source_type):
    """Use the explicit ingest entity; retain deterministic direct-test compatibility."""
    if source_ip is not None:
        return source_ip
    cur.execute(
        """
        SELECT source_ip
        FROM events
        WHERE source = %s AND source_type = %s
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (source, source_type),
    )
    row = cur.fetchone()
    return row[0] if row else None


def _pfsense_escalated_severity(base_severity, *, count, threshold, reputation_score, direction=None):
    """Escalate medium to high on reputation or volume/breadth multiple of threshold.

    An outbound (LAN->WAN) candidate uses a multiplier of 1 instead of
    PFSENSE_SEVERITY_ESCALATION_MULTIPLIER: an internal host repeatedly denied
    when reaching external destinations is a stronger investigative signal
    (possible compromised host) than the same count of inbound WAN noise, so it
    escalates at the base threshold rather than requiring a multiple of it.
    """
    if base_severity != "medium":
        return base_severity
    if reputation_score is not None and reputation_score >= PFSENSE_HIGH_REPUTATION_SCORE:
        return "high"
    effective_multiplier = 1 if direction == "out" else PFSENSE_SEVERITY_ESCALATION_MULTIPLIER
    if threshold and count >= threshold * effective_multiplier:
        return "high"
    return "medium"


def _pfsense_repeated_deny_severity(*, count, threshold, reputation_score, direction=None):
    if reputation_score is not None and reputation_score >= PFSENSE_HIGH_REPUTATION_SCORE:
        return "high"
    if direction == "out":
        return "high" if threshold and count >= threshold else "medium"
    if threshold and count >= threshold * PFSENSE_SEVERITY_ESCALATION_MULTIPLIER:
        return "medium"
    return "low"


def _pfsense_response_action_for_severity(severity):
    if severity == "high":
        return "block_ip"
    if severity == "medium":
        return "enrich_source_ip"
    return "monitor_only"


def _build_pfsense_target_context(mode, **fields):
    target_context = {"mode": mode}
    for key, value in fields.items():
        if value in (None, ""):
            continue
        target_context[key] = value
    return target_context


# spec: SPEC-INGEST-001
def _generate_failed_login_alerts_core(cur, conn, source=None, source_type=None, source_ip=None, rule_config=None):
    rule_config = _prepare_rule_evaluation("failed_login_threshold", cur, source, source_type, rule_config)
    if rule_config is None:
        return []
    source_ip = _resolve_evaluation_source_ip(cur, source_ip, source, source_type)
    if source_ip is None:
        return []
    threshold = rule_config["parameters"]["threshold"]
    window_minutes = rule_config["parameters"]["window_minutes"]

    cur.execute(
        f"""
        SELECT source_ip, COUNT(*) as attempts
        FROM events
        WHERE event_type IN ('failed_login', 'login_failure', 'unauthorized_access')
        AND (%s::inet IS NULL OR source_ip = %s)
        AND source = %s
        AND source_type = %s
        AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        GROUP BY source_ip
        HAVING COUNT(*) >= %s
        """,
        (source_ip, source_ip, source, source_type, threshold,)
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
              AND source = %s
              AND source_type = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_ip, source, source_type,)
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


def _generate_http_error_alerts_core(cur, conn, source=None, source_type=None, source_ip=None, rule_config=None):
    rule_config = _prepare_rule_evaluation("http_error_threshold", cur, source, source_type, rule_config)
    if rule_config is None:
        return []
    source_ip = _resolve_evaluation_source_ip(cur, source_ip, source, source_type)
    if source_ip is None:
        return []
    threshold = rule_config["parameters"]["threshold"]
    window_minutes = rule_config["parameters"]["window_minutes"]

    cur.execute(
        f"""
        SELECT source_ip, COUNT(*) as attempts
        FROM events
        WHERE event_type = 'http_error'
          AND (%s::inet IS NULL OR source_ip = %s)
          AND source = %s
          AND source_type = %s
          AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        GROUP BY source_ip
        HAVING COUNT(*) >= %s
        """,
        (source_ip, source_ip, source, source_type, threshold,)
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
              AND source = %s
              AND source_type = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_ip, source, source_type,)
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


def _generate_port_scan_alerts_core(cur, conn, source=None, source_type=None, source_ip=None, rule_config=None):
    rule_config = _prepare_rule_evaluation("port_scan_threshold", cur, source, source_type, rule_config)
    if rule_config is None:
        return []
    source_ip = _resolve_evaluation_source_ip(cur, source_ip, source, source_type)
    if source_ip is None:
        return []
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
              AND (%s::inet IS NULL OR source_ip = %s)
              AND source = %s
              AND source_type = %s
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
        (source_ip, source_ip, source, source_type, threshold,)
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
              AND source = %s
              AND source_type = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_ip, source, source_type,)
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


def _generate_password_spraying_alerts_core(cur, conn, source=None, source_type=None, source_ip=None, rule_config=None):
    rule_config = _prepare_rule_evaluation("password_spraying_threshold", cur, source, source_type, rule_config)
    if rule_config is None:
        return []
    source_ip = _resolve_evaluation_source_ip(cur, source_ip, source, source_type)
    if source_ip is None:
        return []
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
              AND (%s::inet IS NULL OR source_ip = %s)
              AND source = %s
              AND source_type = %s
              AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        )
        SELECT source_ip, COUNT(DISTINCT extracted_username) AS distinct_username_count
        FROM extracted_failed_logins
        WHERE extracted_username IS NOT NULL
        GROUP BY source_ip
        HAVING COUNT(DISTINCT extracted_username) >= %s
        """,
        (source_ip, source_ip, source, source_type, threshold,)
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
              AND source = %s
              AND source_type = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_ip, source, source_type,)
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


def _generate_successful_login_after_spray_alerts_core(cur, conn, source=None, source_type=None, source_ip=None, rule_config=None):
    rule_config = _prepare_rule_evaluation("successful_login_after_spray", cur, source, source_type, rule_config)
    if rule_config is None:
        return []
    source_ip = _resolve_evaluation_source_ip(cur, source_ip, source, source_type)
    if source_ip is None:
        return []
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
              AND (%s::inet IS NULL OR source_ip = %s)
              AND source = %s
              AND source_type = %s
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
              AND (%s::inet IS NULL OR source_ip = %s)
              AND source = %s
              AND source_type = %s
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
        (
            source_ip, source_ip, source, source_type,
            source_ip, source_ip, source, source_type,
            threshold,
        )
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
              AND source = %s
              AND source_type = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_ip, source, source_type,)
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


def _generate_application_exception_alerts_core(cur, conn, source=None, source_type=None, source_ip=None, rule_config=None):
    rule_config = _prepare_rule_evaluation("application_exception_threshold", cur, source, source_type, rule_config)
    if rule_config is None:
        return []
    source_ip = _resolve_evaluation_source_ip(cur, source_ip, source, source_type)
    if source_ip is None:
        return []
    threshold = rule_config["parameters"]["threshold"]
    window_minutes = rule_config["parameters"]["window_minutes"]

    cur.execute(
        f"""
        SELECT source_ip, COUNT(*) as attempts
        FROM events
        WHERE event_type = 'application_exception'
          AND (%s::inet IS NULL OR source_ip = %s)
          AND source = %s
          AND source_type = %s
          AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        GROUP BY source_ip
        HAVING COUNT(*) >= %s
        """,
        (source_ip, source_ip, source, source_type, threshold,)
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
              AND source = %s
              AND source_type = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_ip, source, source_type,)
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


def _generate_high_request_rate_alerts_core(cur, conn, source=None, source_type=None, source_ip=None, rule_config=None):
    rule_config = _prepare_rule_evaluation("high_request_rate_threshold", cur, source, source_type, rule_config)
    if rule_config is None:
        return []
    source_ip = _resolve_evaluation_source_ip(cur, source_ip, source, source_type)
    if source_ip is None:
        return []
    threshold = rule_config["parameters"]["threshold"]
    window_minutes = rule_config["parameters"]["window_minutes"]

    cur.execute(
        f"""
        SELECT source_ip, COUNT(*) as attempts
        FROM events
        WHERE event_type IN ('normal_activity', 'unauthorized_access', 'http_error')
          AND (%s::inet IS NULL OR source_ip = %s)
          AND source = %s
          AND source_type = %s
          AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        GROUP BY source_ip
        HAVING COUNT(*) >= %s
        """,
        (source_ip, source_ip, source, source_type, threshold,)
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
              AND source = %s
              AND source_type = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_ip, source, source_type,)
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


def _fetch_latest_honeypot_location(cur, source_ip, event_type, source, source_type):
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
          AND source = %s
          AND source_type = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (source_ip, event_type, source, source_type),
    )
    location_row = cur.fetchone()
    if not location_row:
        return None, None, None, None
    return location_row[0], location_row[1], location_row[2], location_row[3]


def _generate_env_probe_alerts_core(cur, conn, source=None, source_type=None, source_ip=None, rule_config=None):
    rule_config = _prepare_rule_evaluation("honeypot_env_probe_threshold", cur, source, source_type, rule_config)
    if rule_config is None:
        return []
    source_ip = _resolve_evaluation_source_ip(cur, source_ip, source, source_type)
    if source_ip is None:
        return []
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
              AND (%s::inet IS NULL OR source_ip = %s)
              AND source = %s
              AND source_type = %s
              AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        )
        SELECT source_ip, COUNT(DISTINCT normalized_path) AS distinct_path_count
        FROM extracted_paths
        WHERE normalized_path IS NOT NULL
        GROUP BY source_ip
        HAVING COUNT(DISTINCT normalized_path) >= %s
        """,
        (source_ip, source_ip, source, source_type, threshold,),
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
        country, city, latitude, longitude = _fetch_latest_honeypot_location(
            cur, source_ip, "env_probe", source, source_type
        )

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


def _generate_admin_probe_alerts_core(cur, conn, source=None, source_type=None, source_ip=None, rule_config=None):
    rule_config = _prepare_rule_evaluation("honeypot_admin_probe_threshold", cur, source, source_type, rule_config)
    if rule_config is None:
        return []
    source_ip = _resolve_evaluation_source_ip(cur, source_ip, source, source_type)
    if source_ip is None:
        return []
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
              AND (%s::inet IS NULL OR source_ip = %s)
              AND source = %s
              AND source_type = %s
              AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        )
        SELECT source_ip, COUNT(DISTINCT normalized_path) AS distinct_path_count
        FROM extracted_paths
        WHERE normalized_path IS NOT NULL
        GROUP BY source_ip
        HAVING COUNT(DISTINCT normalized_path) >= %s
        """,
        (source_ip, source_ip, source, source_type, threshold,),
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
        country, city, latitude, longitude = _fetch_latest_honeypot_location(
            cur, source_ip, "admin_probe", source, source_type
        )

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


def _generate_scanner_detected_alerts_core(cur, conn, source=None, source_type=None, source_ip=None, rule_config=None):
    rule_config = _prepare_rule_evaluation("honeypot_scanner_detected", cur, source, source_type, rule_config)
    if rule_config is None:
        return []
    source_ip = _resolve_evaluation_source_ip(cur, source_ip, source, source_type)
    if source_ip is None:
        return []
    threshold = rule_config["parameters"]["threshold"]
    window_minutes = rule_config["parameters"]["window_minutes"]

    cur.execute(
        f"""
        SELECT source_ip, COUNT(*) AS scanner_events
        FROM events
        WHERE event_type = 'scanner_detected'
          AND (%s::inet IS NULL OR source_ip = %s)
          AND source = %s
          AND source_type = %s
          AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        GROUP BY source_ip
        HAVING COUNT(*) >= %s
        """,
        (source_ip, source_ip, source, source_type, threshold,),
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
        country, city, latitude, longitude = _fetch_latest_honeypot_location(
            cur, source_ip, "scanner_detected", source, source_type
        )

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


def _generate_credential_stuffing_alerts_core(cur, conn, source=None, source_type=None, source_ip=None, rule_config=None):
    rule_config = _prepare_rule_evaluation("honeypot_credential_stuffing_threshold", cur, source, source_type, rule_config)
    if rule_config is None:
        return []
    source_ip = _resolve_evaluation_source_ip(cur, source_ip, source, source_type)
    if source_ip is None:
        return []
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
              AND (%s::inet IS NULL OR source_ip = %s)
              AND source = %s
              AND source_type = %s
              AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        )
        SELECT source_ip, COUNT(DISTINCT normalized_username) AS distinct_username_count
        FROM extracted_usernames
        WHERE normalized_username IS NOT NULL
        GROUP BY source_ip
        HAVING COUNT(DISTINCT normalized_username) >= %s
        """,
        (source_ip, source_ip, source, source_type, threshold,),
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
            source,
            source_type,
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


def _generate_pfsense_repeated_deny_alerts_core(cur, conn, source=None, source_type=None, source_ip=None, rule_config=None):
    rule_config = _prepare_rule_evaluation("pfsense_firewall_repeated_deny", cur, source, source_type, rule_config)
    if rule_config is None:
        return []
    source_ip = _resolve_evaluation_source_ip(cur, source_ip, source, source_type)
    if source_ip is None:
        return []
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
          AND (%s::inet IS NULL OR source_ip = %s)
          AND source = %s
          AND source_type = %s
          AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        GROUP BY source_ip, destination_ip, destination_port, protocol, interface, direction
        HAVING COUNT(*) >= %s
        """,
        (source_ip, source_ip, source, source_type, threshold,),
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

        severity = _pfsense_repeated_deny_severity(
            count=event_count,
            threshold=threshold,
            reputation_score=reputation_score,
            direction=direction,
        )

        if _pfsense_cooldown_suppresses(cur, source_ip, "pfsense_firewall_repeated_deny", severity):
            continue

        response_action = _pfsense_response_action_for_severity(severity)
        response_status = "pending"

        country, city, latitude, longitude = _fetch_latest_honeypot_location(
            cur, source_ip, "firewall_block", source, source_type
        )

        destination_text = destination_ip or "unknown destination"
        if destination_port:
            destination_text = f"{destination_text}:{destination_port}"
        if direction == "out":
            message = (
                f"pfSense blocked {event_count} outbound connections from internal host "
                f"{source_ip} to {destination_text} ({protocol or 'unknown protocol'}) "
                "— possible compromised internal host"
            )
        else:
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
            "target_context": _build_pfsense_target_context(
                "single_target",
                destination_ip=destination_ip,
                destination_port=destination_port,
                protocol=protocol,
                firewall_action="block",
                attempts=event_count,
                first_seen=str(first_seen) if first_seen else None,
                last_seen=str(last_seen) if last_seen else None,
                interface=interface,
                direction=direction,
            ),
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


def _generate_pfsense_port_scan_alerts_core(cur, conn, source=None, source_type=None, source_ip=None, rule_config=None):
    rule_config = _prepare_rule_evaluation("pfsense_firewall_port_scan", cur, source, source_type, rule_config)
    if rule_config is None:
        return []
    source_ip = _resolve_evaluation_source_ip(cur, source_ip, source, source_type)
    if source_ip is None:
        return []
    threshold = rule_config["parameters"]["threshold"]
    window_minutes = rule_config["parameters"]["window_minutes"]
    host_threshold = rule_config["parameters"].get("host_threshold", PFSENSE_PORT_SCAN_HOST_THRESHOLD)

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
              AND (%s::inet IS NULL OR source_ip = %s)
              AND source = %s
              AND source_type = %s
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
        ),
        filtered_ports AS (
            SELECT
                source_ip,
                destination_ip,
                destination_port,
                created_at,
                COUNT(*) OVER (PARTITION BY source_ip, destination_ip) AS destination_event_count,
                COUNT(*) OVER (PARTITION BY source_ip, destination_port) AS port_event_count
            FROM normalized_ports
            WHERE destination_port BETWEEN 1 AND 65535
        )
        SELECT
            source_ip,
            COUNT(DISTINCT destination_port) AS distinct_port_count,
            COUNT(DISTINCT destination_ip) AS distinct_destination_count,
            COUNT(*) AS event_count,
            MIN(created_at) AS first_seen,
            MAX(created_at) AS last_seen,
            (
                ARRAY_AGG(destination_ip ORDER BY destination_event_count DESC, destination_ip ASC)
            )[1] AS top_destination_ip,
            (
                ARRAY_AGG(destination_port ORDER BY port_event_count DESC, destination_port ASC)
            )[1] AS top_destination_port
        FROM filtered_ports
        GROUP BY source_ip
        HAVING COUNT(DISTINCT destination_port) >= %s OR COUNT(DISTINCT destination_ip) >= %s
        """,
        (source_ip, source_ip, source, source_type, threshold, host_threshold),
    )

    rows = cur.fetchall()
    alerts_created = []

    for row in rows:
        (
            source_ip,
            distinct_port_count,
            distinct_destination_count,
            event_count,
            first_seen,
            last_seen,
            top_destination_ip,
            top_destination_port,
        ) = row

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

        # Breadth is measured on two independent axes: many ports on one host
        # (port breadth) and one/few ports swept across many hosts (host
        # breadth). Either axis crossing its own escalation bar is sufficient;
        # they are not summed or blended into a single score.
        severity = _pfsense_escalated_severity(
            "medium",
            count=distinct_port_count,
            threshold=threshold,
            reputation_score=reputation_score,
        )
        if severity != "high":
            host_breadth_severity = _pfsense_escalated_severity(
                "medium",
                count=distinct_destination_count,
                threshold=host_threshold,
                reputation_score=reputation_score,
            )
            if host_breadth_severity == "high":
                severity = "high"

        if _pfsense_cooldown_suppresses(cur, source_ip, "pfsense_firewall_port_scan", severity):
            continue

        response_action = _pfsense_response_action_for_severity(severity)
        response_status = "pending"

        country, city, latitude, longitude = _fetch_latest_honeypot_location(
            cur, source_ip, "firewall_block", source, source_type
        )

        message = (
            f"pfSense firewall scan activity suspected from {source_ip}: "
            f"{distinct_port_count} distinct destination ports across "
            f"{distinct_destination_count} distinct destination hosts"
        )

        context = {
            "action": "block",
            "distinct_port_count": distinct_port_count,
            "distinct_destination_count": distinct_destination_count,
            "event_count": event_count,
            "first_seen": str(first_seen) if first_seen else None,
            "last_seen": str(last_seen) if last_seen else None,
            "target_context": _build_pfsense_target_context(
                "aggregate_targets",
                top_destination_ip=top_destination_ip,
                top_destination_port=top_destination_port,
                distinct_destination_count=distinct_destination_count,
                distinct_port_count=distinct_port_count,
                firewall_action="block",
                attempts=event_count,
                first_seen=str(first_seen) if first_seen else None,
                last_seen=str(last_seen) if last_seen else None,
            ),
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


def _generate_pfsense_suspicious_allow_alerts_core(cur, conn, source=None, source_type=None, source_ip=None, rule_config=None):
    rule_config = _prepare_rule_evaluation("pfsense_firewall_suspicious_allow", cur, source, source_type, rule_config)
    if rule_config is None:
        return []
    source_ip = _resolve_evaluation_source_ip(cur, source_ip, source, source_type)
    if source_ip is None:
        return []
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
              AND (%s::inet IS NULL OR source_ip = %s)
              AND source = %s
              AND source_type = %s
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
            COUNT(DISTINCT destination_port_text) AS distinct_port_count,
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
        (source_ip, source_ip, source, source_type, sensitive_ports, threshold),
    )

    rows = cur.fetchall()
    alerts_created = []

    high_confidence_repeat_threshold = rule_config["parameters"].get(
        "high_confidence_repeat_threshold",
        PFSENSE_SUSPICIOUS_ALLOW_HIGH_CONFIDENCE_REPEAT_THRESHOLD,
    )
    distinct_port_escalation_threshold = rule_config["parameters"].get(
        "distinct_port_escalation_threshold",
        PFSENSE_SUSPICIOUS_ALLOW_DISTINCT_PORT_ESCALATION_THRESHOLD,
    )

    for row in rows:
        (
            source_ip,
            event_count,
            distinct_port_count,
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

        # High severity requires repetition or corroborating context, not event
        # count alone: known-bad reputation, enough repeated allows to rule out
        # a one-off intentionally-forwarded port, or multiple distinct sensitive
        # ports touched by the same source in-window. An uncorroborated single
        # allow is real signal but not yet high-confidence.
        if reputation_score is not None and reputation_score >= PFSENSE_HIGH_REPUTATION_SCORE:
            severity = "high"
        elif event_count >= high_confidence_repeat_threshold:
            severity = "high"
        elif distinct_port_count >= distinct_port_escalation_threshold:
            severity = "high"
        else:
            severity = "medium"

        if _pfsense_cooldown_suppresses(cur, source_ip, "pfsense_firewall_suspicious_allow", severity):
            continue

        response_action = _pfsense_response_action_for_severity(severity)
        response_status = "pending"

        country, city, latitude, longitude = _fetch_latest_honeypot_location(
            cur, source_ip, "firewall_allow", source, source_type
        )

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
            "distinct_sensitive_port_count": distinct_port_count,
            "first_seen": str(first_seen) if first_seen else None,
            "last_seen": str(last_seen) if last_seen else None,
            "target_context": _build_pfsense_target_context(
                "single_target",
                destination_ip=destination_ip,
                destination_port=destination_port,
                protocol=protocol,
                firewall_action="pass",
                attempts=event_count,
                first_seen=str(first_seen) if first_seen else None,
                last_seen=str(last_seen) if last_seen else None,
                interface=interface,
                direction="in",
            ),
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


def _generate_pfsense_noisy_source_alerts_core(cur, conn, source=None, source_type=None, source_ip=None, rule_config=None):
    rule_config = _prepare_rule_evaluation("pfsense_firewall_noisy_source", cur, source, source_type, rule_config)
    if rule_config is None:
        return []
    source_ip = _resolve_evaluation_source_ip(cur, source_ip, source, source_type)
    if source_ip is None:
        return []
    threshold = rule_config["parameters"]["threshold"]
    window_minutes = rule_config["parameters"]["window_minutes"]

    cur.execute(
        f"""
        WITH noisy_events AS (
            SELECT
                source_ip,
                raw_payload->>'destination_ip' AS destination_ip,
                raw_payload->>'destination_port' AS destination_port_text,
                COALESCE(raw_payload->>'action', CASE WHEN event_type = 'firewall_block' THEN 'block' ELSE 'pass' END) AS action,
                created_at
            FROM events
            WHERE event_type IN ('firewall_block', 'firewall_allow')
              AND (%s::inet IS NULL OR source_ip = %s)
              AND source = %s
              AND source_type = %s
              AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        ),
        ranked_noisy_events AS (
            SELECT
                source_ip,
                destination_ip,
                destination_port_text,
                action,
                created_at,
                COUNT(*) OVER (PARTITION BY source_ip, destination_ip) AS destination_event_count,
                COUNT(*) OVER (PARTITION BY source_ip, destination_port_text) AS port_event_count
            FROM noisy_events
        )
        SELECT
            source_ip,
            COUNT(*) AS event_count,
            MIN(created_at) AS first_seen,
            MAX(created_at) AS last_seen,
            (
                ARRAY_AGG(destination_ip ORDER BY destination_event_count DESC, destination_ip ASC)
            )[1] AS top_destination_ip,
            (
                ARRAY_AGG(destination_port_text ORDER BY port_event_count DESC, destination_port_text ASC)
            )[1] AS top_destination_port,
            CASE
                WHEN COUNT(DISTINCT destination_ip) > 0 THEN COUNT(DISTINCT destination_ip)
                ELSE NULL
            END AS distinct_destination_count,
            CASE
                WHEN COUNT(DISTINCT destination_port_text) > 0 THEN COUNT(DISTINCT destination_port_text)
                ELSE NULL
            END AS distinct_port_count,
            CASE
                WHEN COUNT(DISTINCT action) = 1 THEN MIN(action)
                ELSE 'mixed'
            END AS firewall_action
        FROM ranked_noisy_events
        GROUP BY source_ip
        HAVING COUNT(*) >= %s
        """,
        (source_ip, source_ip, source, source_type, threshold,),
    )

    rows = cur.fetchall()
    alerts_created = []

    for row in rows:
        (
            source_ip,
            event_count,
            first_seen,
            last_seen,
            top_destination_ip,
            top_destination_port,
            distinct_destination_count,
            distinct_port_count,
            firewall_action,
        ) = row

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

        severity = "low"

        if _pfsense_cooldown_suppresses(cur, source_ip, "pfsense_firewall_noisy_source", severity):
            continue

        reputation = lookup_ip_reputation(str(source_ip))
        reputation_score = reputation["reputation_score"]
        reputation_label = reputation["reputation_label"]
        reputation_source = reputation["reputation_source"]
        reputation_summary = reputation["reputation_summary"]

        response_action = "suppress_noisy_source"
        response_status = "pending"

        country, city, latitude, longitude = _fetch_latest_honeypot_location(
            cur, source_ip, "firewall_block", source, source_type
        )

        message = f"pfSense firewall noise suppressed from {source_ip}: {event_count} routine events"

        context = {
            "event_count": event_count,
            "first_seen": str(first_seen) if first_seen else None,
            "last_seen": str(last_seen) if last_seen else None,
            "suppressed": True,
            "target_context": _build_pfsense_target_context(
                "aggregate_targets",
                top_destination_ip=top_destination_ip,
                top_destination_port=top_destination_port,
                distinct_destination_count=distinct_destination_count,
                distinct_port_count=distinct_port_count,
                firewall_action=firewall_action,
                attempts=event_count,
                first_seen=str(first_seen) if first_seen else None,
                last_seen=str(last_seen) if last_seen else None,
            ),
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
