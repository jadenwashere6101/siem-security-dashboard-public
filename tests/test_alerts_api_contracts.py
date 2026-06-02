from unittest.mock import patch

import siem_backend
from psycopg2.extras import Json


ADMIN_USER = "testadmin"
ADMIN_PASS = "testpassword123!"
BEHAVIORAL_REPUTATION = {
    "reputation_score": 0,
    "reputation_label": "Normal",
    "reputation_summary": "Contract test behavioral reputation",
    "contributing_signals": [],
}
EXTERNAL_REPUTATION = {
    "reputation_score": 42,
    "reputation_label": "external-medium",
    "reputation_source": "contract-threat-intel",
    "reputation_summary": "Stored external reputation snapshot",
}


class _RouteSafeConnection:
    """Route-level connection wrapper that ignores close()."""

    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return self._conn.cursor()

    def close(self):
        # /alerts closes connections. Keep fixture-owned DB alive for teardown.
        return None


def _insert_alert(
    cur,
    *,
    alert_type,
    source_ip,
    message,
    severity="high",
    status="open",
    reputation=None,
):
    reputation = reputation or EXTERNAL_REPUTATION
    cur.execute(
        """
        INSERT INTO alerts (
            alert_type,
            severity,
            source_ip,
            source,
            source_type,
            message,
            status,
            reputation_score,
            reputation_label,
            reputation_source,
            reputation_summary
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            alert_type,
            severity,
            source_ip,
            "bank_app",
            "custom",
            message,
            status,
            reputation["reputation_score"],
            reputation["reputation_label"],
            reputation["reputation_source"],
            reputation["reputation_summary"],
        ),
    )


def _login_as_super_admin(client):
    resp = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert resp.status_code == 200


def _fetch_alerts_response(client, conn):
    with patch("routes.alerts_events_routes.get_db_connection", return_value=_RouteSafeConnection(conn)), patch(
        "routes.alerts_events_routes.get_ip_reputation", return_value=BEHAVIORAL_REPUTATION
    ):
        return client.get("/alerts")


def _alert_by_type(alerts, alert_type):
    return next(alert for alert in alerts if alert.get("alert_type") == alert_type)


def _assert_mitre(alert, technique_id, technique_name, tactic):
    assert alert["mitre_technique_id"] == technique_id
    assert alert["mitre_technique_name"] == technique_name
    assert alert["mitre_tactic"] == tactic


def _assert_null_mitre(alert):
    for field in ("mitre_technique_id", "mitre_technique_name", "mitre_tactic"):
        assert field in alert
        assert alert[field] is None


def test_get_alerts_without_session_returns_401(client):
    resp = client.get("/alerts")
    assert resp.status_code == 401


def test_get_alerts_authenticated_returns_200_and_json_list_with_core_fields(client, postgres_db):
    conn, cur = postgres_db
    _insert_alert(
        cur,
        alert_type="failed_login_threshold",
        source_ip="198.51.100.201",
        message="Failed login threshold exceeded",
    )
    conn.commit()

    _login_as_super_admin(client)
    resp = _fetch_alerts_response(client, conn)

    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) >= 1

    alert = data[0]
    for field in ("id", "alert_type", "severity", "source_ip", "status", "created_at"):
        assert field in alert


def test_get_alerts_preserves_stored_external_reputation_and_adds_behavioral_reputation(client, postgres_db):
    conn, cur = postgres_db
    stored_reputation = {
        "reputation_score": 71,
        "reputation_label": "abuseipdb-high",
        "reputation_source": "abuseipdb",
        "reputation_summary": "Stored AbuseIPDB snapshot",
    }
    _insert_alert(
        cur,
        alert_type="failed_login_threshold",
        source_ip="198.51.100.220",
        message="Failed login threshold exceeded",
        reputation=stored_reputation,
    )
    conn.commit()

    _login_as_super_admin(client)
    resp = _fetch_alerts_response(client, conn)

    assert resp.status_code == 200
    alert = _alert_by_type(resp.get_json(), "failed_login_threshold")
    assert alert["reputation_score"] == 71
    assert alert["reputation_label"] == "abuseipdb-high"
    assert alert["reputation_source"] == "abuseipdb"
    assert alert["reputation_summary"] == "Stored AbuseIPDB snapshot"
    assert alert["reputation_source"] != "siem_internal"
    assert alert["behavioral_reputation"] == {
        "score": BEHAVIORAL_REPUTATION["reputation_score"],
        "label": BEHAVIORAL_REPUTATION["reputation_label"],
        "source": "siem_internal",
        "summary": BEHAVIORAL_REPUTATION["reputation_summary"],
        "contributing_signals": BEHAVIORAL_REPUTATION["contributing_signals"],
    }
    assert alert["contributing_signals"] == BEHAVIORAL_REPUTATION["contributing_signals"]


def test_get_alerts_behavioral_reputation_shape_always_present(client, postgres_db):
    conn, cur = postgres_db
    _insert_alert(
        cur,
        alert_type="port_scan_threshold",
        source_ip="198.51.100.221",
        message="Port scan threshold exceeded",
    )
    conn.commit()

    _login_as_super_admin(client)
    resp = _fetch_alerts_response(client, conn)

    assert resp.status_code == 200
    alert = _alert_by_type(resp.get_json(), "port_scan_threshold")
    behavioral = alert["behavioral_reputation"]
    assert set(behavioral) == {"score", "label", "source", "summary", "contributing_signals"}
    assert behavioral["source"] == "siem_internal"
    assert isinstance(behavioral["contributing_signals"], list)


def test_get_alerts_correlation_alerts_include_correlation_contract_fields(client, postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.202"
    _insert_alert(
        cur,
        alert_type="correlated_activity",
        source_ip=source_ip,
        message=(
            f"Multi-source suspicious activity detected from {source_ip} "
            "involving: port_scan_threshold, failed_login_threshold"
        ),
    )
    conn.commit()

    _login_as_super_admin(client)
    resp = _fetch_alerts_response(client, conn)

    assert resp.status_code == 200
    data = resp.get_json()
    correlation_alerts = [alert for alert in data if alert.get("alert_type") == "correlated_activity"]
    assert correlation_alerts

    correlation_alert = correlation_alerts[0]
    assert "is_correlation_alert" in correlation_alert
    assert "correlated_alert_types" in correlation_alert


def test_get_alerts_prefers_structured_context_over_message_parsing(client, postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.217"
    structured_context = {
        "correlation_type": "correlated_activity",
        "matched_rule_id": "correlated_activity",
        "matched_window_minutes": 10,
        "matched_alert_count": 2,
        "contributing_alert_types": ["port_scan_threshold", "failed_login_threshold"],
        "contributing_alert_ids": [901, 902],
        "contributing_sources": ["nginx", "bank_app"],
        "contributing_source_types": ["web_log", "custom"],
    }
    cur.execute(
        """
        INSERT INTO alerts (
            alert_type,
            severity,
            source_ip,
            source,
            source_type,
            message,
            status,
            context
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            "correlated_activity",
            "high",
            source_ip,
            "bank_app",
            "custom",
            (
                f"Multi-source suspicious activity detected from {source_ip} "
                "involving: legacy_only_type"
            ),
            "open",
            Json(structured_context),
        ),
    )
    conn.commit()

    _login_as_super_admin(client)
    resp = _fetch_alerts_response(client, conn)

    assert resp.status_code == 200
    alert = _alert_by_type(resp.get_json(), "correlated_activity")
    assert alert["context"] == structured_context
    assert alert["is_correlation_alert"] is True
    assert alert["correlated_alert_types"] == ["port_scan_threshold", "failed_login_threshold"]
    assert alert["correlated_alert_count"] == 2
    assert alert["correlation_context"]["contributing_alert_ids"] == [901, 902]


def test_get_alerts_targeted_correlation_with_empty_context_does_not_fabricate_details(
    client, postgres_db
):
    conn, cur = postgres_db
    _insert_alert(
        cur,
        alert_type="web_to_app_attack_pattern",
        source_ip="198.51.100.218",
        message="Web-to-app attack pattern detected from 198.51.100.218",
        severity="critical",
    )
    conn.commit()

    _login_as_super_admin(client)
    resp = _fetch_alerts_response(client, conn)

    assert resp.status_code == 200
    alert = _alert_by_type(resp.get_json(), "web_to_app_attack_pattern")
    assert alert.get("context") == {}
    assert "is_correlation_alert" not in alert
    assert "correlated_alert_types" not in alert
    assert "correlation_context" not in alert


def test_get_alerts_non_correlation_alert_exposes_empty_context(client, postgres_db):
    conn, cur = postgres_db
    _insert_alert(
        cur,
        alert_type="failed_login_threshold",
        source_ip="198.51.100.219",
        message="Failed login threshold exceeded",
    )
    conn.commit()

    _login_as_super_admin(client)
    resp = _fetch_alerts_response(client, conn)

    assert resp.status_code == 200
    alert = _alert_by_type(resp.get_json(), "failed_login_threshold")
    assert alert.get("context") == {}
    assert "is_correlation_alert" not in alert


def test_get_alerts_mitre_fields_include_expected_known_mappings(client, postgres_db):
    conn, cur = postgres_db
    mapped_alerts = (
        ("failed_login_threshold", "198.51.100.203", "T1110", "Brute Force", "Credential Access"),
        ("port_scan_threshold", "198.51.100.204", "T1046", "Network Service Discovery", "Discovery"),
        ("suspicious_ip_reputation", "198.51.100.205", "T1595", "Active Scanning", "Reconnaissance"),
        ("password_spraying_threshold", "198.51.100.206", "T1110.003", "Password Spraying", "Credential Access"),
        ("successful_login_after_spray", "198.51.100.207", "T1110.003", "Password Spraying", "Credential Access"),
        ("spray_then_success_pattern", "198.51.100.208", "T1110.003", "Password Spraying", "Credential Access"),
    )
    for alert_type, source_ip, _technique_id, _technique_name, _tactic in mapped_alerts:
        _insert_alert(
            cur,
            alert_type=alert_type,
            source_ip=source_ip,
            message=f"Known MITRE mapping alert: {alert_type}",
        )
    conn.commit()

    _login_as_super_admin(client)
    resp = _fetch_alerts_response(client, conn)

    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)

    for alert_type, _source_ip, technique_id, technique_name, tactic in mapped_alerts:
        _assert_mitre(_alert_by_type(data, alert_type), technique_id, technique_name, tactic)


def test_get_alerts_intentionally_unmapped_mitre_alerts_return_null_fields(client, postgres_db):
    conn, cur = postgres_db
    intentionally_unmapped_alert_types = (
        "http_error_threshold",
        "application_exception_threshold",
        "high_request_rate_threshold",
        "correlated_activity",
        "web_to_app_attack_pattern",
        "cloud_app_error_pattern",
    )
    for index, alert_type in enumerate(intentionally_unmapped_alert_types, start=210):
        _insert_alert(
            cur,
            alert_type=alert_type,
            source_ip=f"198.51.100.{index}",
            message=f"Intentionally unmapped MITRE alert: {alert_type}",
        )
    conn.commit()

    _login_as_super_admin(client)
    resp = _fetch_alerts_response(client, conn)

    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)

    for alert_type in intentionally_unmapped_alert_types:
        _assert_null_mitre(_alert_by_type(data, alert_type))


def test_get_alerts_unknown_mitre_mapping_keeps_null_field_shape(client, postgres_db):
    conn, cur = postgres_db
    _insert_alert(
        cur,
        alert_type="custom_unmapped_alert",
        source_ip="198.51.100.216",
        message="Unknown MITRE mapping alert",
    )
    conn.commit()

    _login_as_super_admin(client)
    resp = _fetch_alerts_response(client, conn)

    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)

    _assert_null_mitre(_alert_by_type(data, "custom_unmapped_alert"))
