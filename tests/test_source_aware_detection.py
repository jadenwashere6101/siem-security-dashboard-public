from unittest.mock import patch

import pytest
from psycopg2.extras import Json

import siem_backend
import engines.detection_engine as detection_engine
from engines.detection_applicability import RULE_APPLICABILITY
from engines.detection_config import get_detection_rule_defaults


REPUTATION = {
    "reputation_score": 10,
    "reputation_label": "low-risk",
    "reputation_source": "test",
    "reputation_summary": "source-aware test",
}


DETECTORS = {
    "failed_login_threshold": detection_engine._generate_failed_login_alerts_core,
    "port_scan_threshold": detection_engine._generate_port_scan_alerts_core,
    "password_spraying_threshold": detection_engine._generate_password_spraying_alerts_core,
    "http_error_threshold": detection_engine._generate_http_error_alerts_core,
    "application_exception_threshold": detection_engine._generate_application_exception_alerts_core,
    "high_request_rate_threshold": detection_engine._generate_high_request_rate_alerts_core,
    "successful_login_after_spray": detection_engine._generate_successful_login_after_spray_alerts_core,
    "honeypot_env_probe_threshold": detection_engine._generate_env_probe_alerts_core,
    "honeypot_admin_probe_threshold": detection_engine._generate_admin_probe_alerts_core,
    "honeypot_scanner_detected": detection_engine._generate_scanner_detected_alerts_core,
    "honeypot_credential_stuffing_threshold": detection_engine._generate_credential_stuffing_alerts_core,
    "pfsense_firewall_repeated_deny": detection_engine._generate_pfsense_repeated_deny_alerts_core,
    "pfsense_firewall_port_scan": detection_engine._generate_pfsense_port_scan_alerts_core,
    "pfsense_firewall_noisy_source": detection_engine._generate_pfsense_noisy_source_alerts_core,
    "pfsense_firewall_suspicious_allow": detection_engine._generate_pfsense_suspicious_allow_alerts_core,
}


RULE_SOURCE_CASES = [
    (rule_id, identity.source, identity.source_type)
    for rule_id, applicability in RULE_APPLICABILITY.items()
    for identity in sorted(applicability.allowed_sources)
]


def _parameters_at_threshold_one(rule_id):
    parameters = dict(get_detection_rule_defaults()[rule_id]["parameters"])
    parameters["threshold"] = 1
    return parameters


def _insert_event(cur, rule_id, source_ip, source, source_type, *, event_type=None, username="alice"):
    event_types = {
        "failed_login_threshold": "failed_login",
        "port_scan_threshold": "port_scan",
        "password_spraying_threshold": "failed_login",
        "http_error_threshold": "http_error",
        "application_exception_threshold": "application_exception",
        "high_request_rate_threshold": "normal_activity",
        "successful_login_after_spray": "failed_login",
        "honeypot_env_probe_threshold": "env_probe",
        "honeypot_admin_probe_threshold": "admin_probe",
        "honeypot_scanner_detected": "scanner_detected",
        "honeypot_credential_stuffing_threshold": "credential_stuffing",
        "pfsense_firewall_repeated_deny": "firewall_block",
        "pfsense_firewall_port_scan": "firewall_block",
        "pfsense_firewall_noisy_source": "firewall_block",
        "pfsense_firewall_suspicious_allow": "firewall_allow",
    }
    payload = {
        "username": username,
        "path": "/admin/config",
        "destination_ip": "203.0.113.10",
        "destination_port": "22",
        "protocol": "tcp",
        "interface": "wan",
        "direction": "in",
        "location": {"country": "US", "city": "New York", "lat": "40.7", "lon": "-74.0"},
    }
    cur.execute(
        """
        INSERT INTO events (
            event_type, severity, source_ip, source, source_type,
            message, app_name, environment, raw_payload, created_at
        ) VALUES (%s, 'medium', %s, %s, %s, 'test', 'test', 'test', %s, NOW())
        """,
        (event_type or event_types[rule_id], source_ip, source, source_type, Json(payload)),
    )


@pytest.mark.parametrize(("rule_id", "source", "source_type"), RULE_SOURCE_CASES)
def test_every_allowed_rule_source_pair_produces_detection(postgres_db, rule_id, source, source_type):
    conn, cur = postgres_db
    source_ip = "198.51.100.210"
    parameters = _parameters_at_threshold_one(rule_id)
    cur.execute(
        """
        INSERT INTO detection_config (rule_id, parameters, active, updated_by)
        VALUES (%s, %s, TRUE, 'pytest')
        """,
        (rule_id, Json(parameters)),
    )
    _insert_event(cur, rule_id, source_ip, source, source_type)
    if rule_id == "successful_login_after_spray":
        _insert_event(
            cur,
            rule_id,
            source_ip,
            source,
            source_type,
            event_type="successful_login",
        )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION
    ):
        alerts = DETECTORS[rule_id](
            cur,
            conn,
            source_ip=source_ip,
            source=source,
            source_type=source_type,
        )

    assert len(alerts) == 1
    cur.execute("SELECT source, source_type FROM alerts WHERE id = %s", (alerts[0]["alert_id"],))
    assert cur.fetchone() == (source, source_type)


def _normalized_event(source_ip, source, source_type, username):
    return {
        "event_type": "failed_login",
        "severity": "medium",
        "source_ip": source_ip,
        "source": source,
        "source_type": source_type,
        "event_timestamp": None,
        "message": "failed login",
        "app_name": "test",
        "environment": "test",
        "raw_payload": {"username": username},
    }


def test_supported_sources_cannot_contaminate_each_others_thresholds(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.211"
    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION
    ), patch("engines.correlation_engine.lookup_ip_reputation", return_value=REPUTATION):
        for username in ("bank-a", "bank-b"):
            assert siem_backend.ingest_normalized_event(
                _normalized_event(source_ip, "bank_app", "custom", username), conn, cur
            ) == []
        assert siem_backend.ingest_normalized_event(
            _normalized_event(source_ip, "azure_insights", "cloud_api", "azure-a"), conn, cur
        ) == []
        alerts = siem_backend.ingest_normalized_event(
            _normalized_event(source_ip, "bank_app", "custom", "bank-c"), conn, cur
        )

    assert len(alerts) == 1
    assert alerts[0]["attempts"] == 3


def test_inactive_rule_stores_event_without_execution_or_alert(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.212"
    cur.execute(
        """
        INSERT INTO detection_config (rule_id, parameters, active, updated_by)
        VALUES ('failed_login_threshold', '{"threshold": 1, "window_minutes": 15}'::jsonb, FALSE, 'pytest')
        """
    )
    with siem_backend.app.app_context():
        result = siem_backend.ingest_normalized_event(
            _normalized_event(source_ip, "bank_app", "custom", "alice"), conn, cur
        )
    assert result == []
    cur.execute("SELECT COUNT(*) FROM events WHERE source_ip = %s", (source_ip,))
    assert cur.fetchone()[0] == 1
    cur.execute("SELECT COUNT(*) FROM alerts WHERE source_ip = %s", (source_ip,))
    assert cur.fetchone()[0] == 0


def test_triggering_event_cannot_create_alert_for_unrelated_ip(postgres_db):
    conn, cur = postgres_db
    historical_ip = "198.51.100.213"
    triggering_ip = "198.51.100.214"
    for username in ("a", "b", "c"):
        _insert_event(cur, "failed_login_threshold", historical_ip, "bank_app", "custom", username=username)

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION
    ):
        result = siem_backend.ingest_normalized_event(
            _normalized_event(triggering_ip, "bank_app", "custom", "new"), conn, cur
        )
    assert result == []
    cur.execute("SELECT COUNT(*) FROM alerts")
    assert cur.fetchone()[0] == 0
