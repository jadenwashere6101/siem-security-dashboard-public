from psycopg2.extras import Json

from engines.correlation_engine import generate_correlated_activity_alerts, generate_targeted_correlation_alerts
from engines.detection_engine import (
    _generate_application_exception_alerts_core,
    _generate_failed_login_alerts_core,
    _generate_high_request_rate_alerts_core,
    _generate_http_error_alerts_core,
    _generate_password_spraying_alerts_core,
    _generate_port_scan_alerts_core,
    _generate_successful_login_after_spray_alerts_core,
)


def ingest_normalized_event(event_dict, conn, cur):
    # Central normalized ingestion path. Adapters and raw ingest routes feed
    # this function, and detector/correlation fan-out happens here.
    event_type = event_dict["event_type"]
    severity = event_dict["severity"]
    source_ip = event_dict["source_ip"]
    source = event_dict.get("source", "bank_app")
    source_type = event_dict.get("source_type", "custom")
    event_timestamp = event_dict.get("event_timestamp")
    message = event_dict["message"]
    app_name = event_dict["app_name"]
    environment = event_dict["environment"]
    raw_payload = event_dict["raw_payload"]

    cur.execute(
        """
        INSERT INTO events (
            event_type,
            severity,
            source_ip,
            source,
            source_type,
            event_timestamp,
            message,
            app_name,
            environment,
            raw_payload
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            event_type,
            severity,
            source_ip,
            source,
            source_type,
            event_timestamp,
            message,
            app_name,
            environment,
            Json(raw_payload),
        ),
    )

    alerts_created = []

    if event_type == "failed_login":
        alerts_created = _generate_failed_login_alerts_core(cur, conn, source=source, source_type=source_type)
        alerts_created.extend(_generate_password_spraying_alerts_core(cur, conn, source=source, source_type=source_type))
        alerts_created.extend(
            _generate_successful_login_after_spray_alerts_core(cur, conn, source=source, source_type=source_type)
        )
    elif event_type == "unauthorized_access":
        alerts_created = _generate_failed_login_alerts_core(cur, conn, source=source, source_type=source_type)
        if source_type in {"web_log", "telemetry"}:
            alerts_created.extend(
                _generate_high_request_rate_alerts_core(cur, conn, source=source, source_type=source_type)
            )
    elif event_type == "http_error":
        alerts_created = _generate_http_error_alerts_core(cur, conn, source=source, source_type=source_type)
        if source_type in {"web_log", "telemetry"}:
            alerts_created.extend(
                _generate_high_request_rate_alerts_core(cur, conn, source=source, source_type=source_type)
            )
    elif event_type == "application_exception":
        alerts_created = _generate_application_exception_alerts_core(cur, conn, source=source, source_type=source_type)
    elif event_type == "normal_activity":
        if source_type in {"web_log", "telemetry"}:
            alerts_created = _generate_high_request_rate_alerts_core(cur, conn, source=source, source_type=source_type)
    elif event_type == "successful_login":
        alerts_created.extend(
            _generate_successful_login_after_spray_alerts_core(cur, conn, source=source, source_type=source_type)
        )
    elif event_type == "port_scan":
        alerts_created = _generate_port_scan_alerts_core(cur, conn, source=source, source_type=source_type)

    for correlated_source_ip in {
        str(alert.get("source_ip"))
        for alert in alerts_created
        if alert.get("source_ip") is not None
    }:
        generate_correlated_activity_alerts(cur, conn, correlated_source_ip)
        generate_targeted_correlation_alerts(cur, conn, correlated_source_ip)

    return alerts_created
