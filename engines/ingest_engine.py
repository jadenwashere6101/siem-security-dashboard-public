from psycopg2.extras import Json

from engines.correlation_engine import generate_correlated_activity_alerts, generate_targeted_correlation_alerts
from engines.detection_applicability import rule_applies_to_source
from engines.detection_config import get_effective_detection_rule
from engines.detection_engine import (
    _generate_app_insights_unauthorized_access_alerts_core,
    _generate_application_exception_alerts_core,
    _generate_credential_stuffing_alerts_core,
    _generate_env_probe_alerts_core,
    _generate_admin_probe_alerts_core,
    _generate_failed_login_alerts_core,
    _generate_high_request_rate_alerts_core,
    _generate_http_error_alerts_core,
    _generate_password_spraying_alerts_core,
    _generate_pfsense_noisy_source_alerts_core,
    _generate_pfsense_allow_after_deny_alerts_core,
    _generate_pfsense_port_scan_alerts_core,
    _generate_pfsense_repeated_deny_alerts_core,
    _generate_pfsense_suspicious_allow_alerts_core,
    _generate_port_scan_alerts_core,
    _generate_scanner_detected_alerts_core,
    _generate_successful_login_after_spray_alerts_core,
)
from helpers.ingest_normalizers import reject_raw_password_fields
from core.source_ingestion_health_state import record_persisted_push_event
from core.synthetic_data_policy import (
    SYNTHETIC_PROVENANCE_VALUES,
    synthetic_json_provenance_values,
)

IMPLEMENTED_BASE_DETECTION_RULE_IDS = (
    "failed_login_threshold",
    "port_scan_threshold",
    "password_spraying_threshold",
    "http_error_threshold",
    "application_exception_threshold",
    "app_insights_unauthorized_access_threshold",
    "high_request_rate_threshold",
    "successful_login_after_spray",
    "honeypot_env_probe_threshold",
    "honeypot_admin_probe_threshold",
    "honeypot_scanner_detected",
    "honeypot_credential_stuffing_threshold",
    "pfsense_firewall_repeated_deny",
    "pfsense_firewall_port_scan",
    "pfsense_firewall_noisy_source",
    "pfsense_firewall_suspicious_allow",
    "pfsense_firewall_allow_after_deny",
)


def _lower_text(value):
    return str(value or "").strip().lower()


def _raw_payload_provenance_values(raw_payload):
    return list(synthetic_json_provenance_values(raw_payload))


def _build_synthetic_provenance_context(event_dict):
    raw_payload = event_dict.get("raw_payload")
    provenance_values = set(_raw_payload_provenance_values(raw_payload))
    source_markers = {
        _lower_text(event_dict.get("source")),
        _lower_text(event_dict.get("source_type")),
        _lower_text(event_dict.get("app_name")),
    }
    matched = (provenance_values | source_markers) & SYNTHETIC_PROVENANCE_VALUES
    if not matched:
        return None
    origin = None
    provenance = raw_payload.get("provenance") if isinstance(raw_payload, dict) else None
    if isinstance(provenance, dict):
        origin = provenance.get("origin") or provenance.get("source")
    return {
        "data_provenance": "synthetic",
        "provenance": {
            "classification": "synthetic",
            "origin": origin or event_dict.get("app_name") or event_dict.get("source") or "ingest",
        },
    }


def _mark_alerts_with_synthetic_provenance(cur, alerts_created, provenance_context):
    if not provenance_context:
        return
    alert_ids = [
        int(alert["alert_id"])
        for alert in alerts_created
        if isinstance(alert, dict) and alert.get("alert_id") is not None
    ]
    if not alert_ids:
        return
    cur.execute(
        """
        UPDATE alerts
        SET context = COALESCE(context, '{}'::jsonb) || %s::jsonb
        WHERE id = ANY(%s)
        """,
        (Json(provenance_context), alert_ids),
    )


def _run_detector(rule_id, detector, *, cur, conn, source_ip, source, source_type):
    """Fail closed before detector SQL for unsupported or inactive rules."""
    if not rule_applies_to_source(rule_id, source, source_type):
        return []
    rule_config = get_effective_detection_rule(rule_id, cur=cur)
    if not rule_config["active"]:
        return []
    return detector(
        cur,
        conn,
        source_ip=source_ip,
        source=source,
        source_type=source_type,
        rule_config=rule_config,
    )


def ingest_normalized_event(event_dict, conn, cur):
    # Central normalized ingestion path. Adapters and raw ingest routes feed
    # this function, and detector/correlation fan-out happens here.
    # spec: SPEC-INGEST-001
    # spec: SPEC-NORM-001
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

    reject_raw_password_fields(event_dict)

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
        RETURNING created_at
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
    ingested_at = cur.fetchone()[0]
    record_persisted_push_event(
        cur,
        source=source,
        ingested_at=ingested_at,
        raw_payload=raw_payload,
    )

    detector_candidates = {
        "failed_login": (
            ("failed_login_threshold", _generate_failed_login_alerts_core),
            ("password_spraying_threshold", _generate_password_spraying_alerts_core),
            ("successful_login_after_spray", _generate_successful_login_after_spray_alerts_core),
        ),
        "unauthorized_access": (
            ("failed_login_threshold", _generate_failed_login_alerts_core),
            ("app_insights_unauthorized_access_threshold", _generate_app_insights_unauthorized_access_alerts_core),
            ("high_request_rate_threshold", _generate_high_request_rate_alerts_core),
        ),
        "http_error": (
            ("http_error_threshold", _generate_http_error_alerts_core),
            ("high_request_rate_threshold", _generate_high_request_rate_alerts_core),
        ),
        "application_exception": (
            ("application_exception_threshold", _generate_application_exception_alerts_core),
        ),
        "normal_activity": (("high_request_rate_threshold", _generate_high_request_rate_alerts_core),),
        "successful_login": (
            ("successful_login_after_spray", _generate_successful_login_after_spray_alerts_core),
        ),
        "port_scan": (("port_scan_threshold", _generate_port_scan_alerts_core),),
        "env_probe": (("honeypot_env_probe_threshold", _generate_env_probe_alerts_core),),
        "admin_probe": (("honeypot_admin_probe_threshold", _generate_admin_probe_alerts_core),),
        "scanner_detected": (("honeypot_scanner_detected", _generate_scanner_detected_alerts_core),),
        "credential_stuffing": (
            ("honeypot_credential_stuffing_threshold", _generate_credential_stuffing_alerts_core),
        ),
        "firewall_block": (
            ("pfsense_firewall_repeated_deny", _generate_pfsense_repeated_deny_alerts_core),
            ("pfsense_firewall_port_scan", _generate_pfsense_port_scan_alerts_core),
            ("pfsense_firewall_noisy_source", _generate_pfsense_noisy_source_alerts_core),
        ),
        "firewall_allow": (
            ("pfsense_firewall_allow_after_deny", _generate_pfsense_allow_after_deny_alerts_core),
            ("pfsense_firewall_suspicious_allow", _generate_pfsense_suspicious_allow_alerts_core),
            ("pfsense_firewall_noisy_source", _generate_pfsense_noisy_source_alerts_core),
        ),
    }

    alerts_created = []
    for rule_id, detector in detector_candidates.get(event_type, ()):
        alerts_created.extend(
            _run_detector(
                rule_id,
                detector,
                cur=cur,
                conn=conn,
                source_ip=source_ip,
                source=source,
                source_type=source_type,
            )
        )

    for correlated_source_ip in {
        str(alert.get("source_ip"))
        for alert in alerts_created
        if alert.get("source_ip") is not None
    }:
        alerts_created.extend(generate_correlated_activity_alerts(cur, conn, correlated_source_ip))
        alerts_created.extend(generate_targeted_correlation_alerts(cur, conn, correlated_source_ip))

    _mark_alerts_with_synthetic_provenance(
        cur,
        alerts_created,
        _build_synthetic_provenance_context(event_dict),
    )

    return alerts_created
