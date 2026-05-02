from backend_detection_config import (
    APPLICATION_EXCEPTION_THRESHOLD,
    APPLICATION_EXCEPTION_WINDOW_MINUTES,
    HIGH_REQUEST_RATE_THRESHOLD,
    HIGH_REQUEST_RATE_WINDOW_MINUTES,
    HTTP_ERROR_THRESHOLD,
    HTTP_ERROR_WINDOW_MINUTES,
)
from backend_ip_helpers import determine_response_action, execute_response_action, lookup_ip_reputation


def _generate_http_error_alerts_core(cur, conn, source=None, source_type=None):
    threshold = HTTP_ERROR_THRESHOLD
    window_minutes = HTTP_ERROR_WINDOW_MINUTES

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

        execution_status = execute_response_action(
            cur,
            alert_id,
            str(source_ip),
            response_action
        )

        cur.execute(
            """
            UPDATE alerts
            SET response_status = %s
            WHERE id = %s
            """,
            (execution_status, alert_id)
        )

        alerts_created.append(
            {
                "source_ip": source_ip,
                "attempts": attempts,
            }
        )

    return alerts_created


def _generate_application_exception_alerts_core(cur, conn, source=None, source_type=None):
    threshold = APPLICATION_EXCEPTION_THRESHOLD
    window_minutes = APPLICATION_EXCEPTION_WINDOW_MINUTES

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

        execution_status = execute_response_action(
            cur,
            alert_id,
            str(source_ip),
            response_action
        )

        cur.execute(
            """
            UPDATE alerts
            SET response_status = %s
            WHERE id = %s
            """,
            (execution_status, alert_id)
        )

        alerts_created.append(
            {
                "source_ip": source_ip,
                "attempts": attempts,
            }
        )

    return alerts_created


def _generate_high_request_rate_alerts_core(cur, conn, source=None, source_type=None):
    threshold = HIGH_REQUEST_RATE_THRESHOLD
    window_minutes = HIGH_REQUEST_RATE_WINDOW_MINUTES

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

        execution_status = execute_response_action(
            cur,
            alert_id,
            str(source_ip),
            response_action
        )

        cur.execute(
            """
            UPDATE alerts
            SET response_status = %s
            WHERE id = %s
            """,
            (execution_status, alert_id)
        )

        alerts_created.append(
            {
                "source_ip": source_ip,
                "attempts": attempts,
            }
        )

    return alerts_created
