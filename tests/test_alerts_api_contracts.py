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


def _fetch_alerts_response_for_path(client, conn, path):
    with patch("routes.alerts_events_routes.get_db_connection", return_value=_RouteSafeConnection(conn)), patch(
        "routes.alerts_events_routes.get_ip_reputation", return_value=BEHAVIORAL_REPUTATION
    ):
        return client.get(path)


def _fetch_alert_summary_response(client, conn):
    with patch("routes.alerts_events_routes.get_db_connection", return_value=_RouteSafeConnection(conn)), patch(
        "routes.alerts_events_routes.get_ip_reputation", return_value=BEHAVIORAL_REPUTATION
    ):
        return client.get("/alerts/summary")


def _fetch_alert_summary_response_for_path(client, conn, path):
    with patch("routes.alerts_events_routes.get_db_connection", return_value=_RouteSafeConnection(conn)), patch(
        "routes.alerts_events_routes.get_ip_reputation", return_value=BEHAVIORAL_REPUTATION
    ):
        return client.get(path)


def _alert_items(payload):
    return payload["items"] if isinstance(payload, dict) else payload


def _fetch_why_fired_response(client, conn, alert_id):
    with patch("routes.alerts_events_routes.get_db_connection", return_value=_RouteSafeConnection(conn)), patch(
        "routes.alerts_events_routes.get_ip_reputation", return_value=BEHAVIORAL_REPUTATION
    ):
        return client.get(f"/alerts/{alert_id}/why-fired")


def _fetch_recon_activities_response(client, conn, path="/recon-activities"):
    with patch("routes.alerts_events_routes.get_db_connection", return_value=_RouteSafeConnection(conn)), patch(
        "routes.alerts_events_routes.get_ip_reputation", return_value=BEHAVIORAL_REPUTATION
    ):
        return client.get(path)


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


def test_get_alerts_summary_without_session_returns_401(client):
    resp = client.get("/alerts/summary")
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
    assert isinstance(data, dict)
    assert isinstance(data["items"], list)
    assert len(data["items"]) >= 1
    assert data["limit"] == 50
    assert data["offset"] == 0

    alert = data["items"][0]
    for field in ("id", "alert_type", "severity", "source_ip", "status", "created_at"):
        assert field in alert


def test_get_alerts_applies_limit_offset_and_max_page_size(client, postgres_db):
    conn, cur = postgres_db
    for index in range(3):
        _insert_alert(
            cur,
            alert_type=f"paged_alert_{index}",
            source_ip=f"198.51.100.{230 + index}",
            message=f"Paged alert {index}",
        )
    conn.commit()

    _login_as_super_admin(client)
    with patch("routes.alerts_events_routes.get_db_connection", return_value=_RouteSafeConnection(conn)), patch(
        "routes.alerts_events_routes.get_ip_reputation", return_value=BEHAVIORAL_REPUTATION
    ):
        resp = client.get("/alerts?limit=999&offset=1&sort=newest")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["limit"] == 100
    assert payload["offset"] == 1
    items = payload["items"]
    assert len(items) == 2
    assert [item["alert_type"] for item in items] == ["paged_alert_1", "paged_alert_0"]


def test_get_alerts_since_tuning_filters_only_pre_tuning_pfsense_alerts(client, postgres_db, monkeypatch):
    conn, cur = postgres_db
    monkeypatch.setenv("SIEM_PFSENSE_TUNING_BASELINE", "2026-06-01T00:00:00Z")
    cur.execute(
        """
        INSERT INTO alerts (
            alert_type, severity, source_ip, source, source_type, message, status, created_at
        )
        VALUES
            ('pfsense_firewall_repeated_deny', 'low', '198.51.100.210', 'pfsense', 'firewall', 'legacy pfSense', 'open', '2026-05-01T00:00:00+00:00'),
            ('pfsense_firewall_port_scan', 'medium', '198.51.100.211', 'pfsense', 'firewall', 'current pfSense', 'open', '2026-06-15T00:00:00+00:00'),
            ('failed_login_threshold', 'high', '198.51.100.212', 'bank_app', 'custom', 'non-pfSense', 'open', '2026-05-01T00:00:00+00:00')
        """
    )
    conn.commit()

    _login_as_super_admin(client)
    resp = _fetch_alerts_response_for_path(client, conn, "/alerts?operational_scope=since_tuning&sort=oldest")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert [item["message"] for item in payload["items"]] == ["non-pfSense", "current pfSense"]


def test_get_alert_payload_marks_pre_tuning_pfsense_alerts(client, postgres_db, monkeypatch):
    conn, cur = postgres_db
    monkeypatch.setenv("SIEM_PFSENSE_TUNING_BASELINE", "2026-06-01T00:00:00Z")
    cur.execute(
        """
        INSERT INTO alerts (
            alert_type, severity, source_ip, source, source_type, message, status, created_at
        )
        VALUES ('pfsense_firewall_repeated_deny', 'low', '198.51.100.213', 'pfsense', 'firewall', 'legacy pfSense', 'open', '2026-05-01T00:00:00+00:00')
        RETURNING id
        """
    )
    alert_id = cur.fetchone()[0]
    conn.commit()

    _login_as_super_admin(client)
    with patch("routes.alerts_events_routes.get_db_connection", return_value=_RouteSafeConnection(conn)), patch(
        "routes.alerts_events_routes.get_ip_reputation", return_value=BEHAVIORAL_REPUTATION
    ):
        resp = client.get(f"/alerts/{alert_id}")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["operational_history"]["is_pre_tuning"] is True
    assert payload["operational_history"]["label"] == "Pre-Tuning"


def test_get_alerts_summary_remains_authoritative_independent_of_alert_page(client, postgres_db):
    conn, cur = postgres_db
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
            latitude,
            longitude,
            country,
            city,
            created_at
        )
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s),
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s),
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            "summary_high_one",
            "high",
            "198.51.100.10",
            "bank_app",
            "custom",
            "Summary high alert 1",
            "open",
            40.7128,
            -74.0060,
            "United States",
            "New York",
            "2026-07-14T10:00:00Z",
            "summary_high_two",
            "high",
            "198.51.100.10",
            "bank_app",
            "custom",
            "Summary high alert 2",
            "open",
            40.7128,
            -74.0060,
            "United States",
            "New York",
            "2026-07-14T10:10:00Z",
            "summary_medium_one",
            "medium",
            "198.51.100.11",
            "nginx",
            "web_log",
            "Summary medium alert",
            "open",
            34.0522,
            -118.2437,
            "United States",
            "Los Angeles",
            "2026-07-14T11:00:00Z",
        ),
    )
    conn.commit()

    _login_as_super_admin(client)

    with patch("routes.alerts_events_routes.get_db_connection", return_value=_RouteSafeConnection(conn)), patch(
        "routes.alerts_events_routes.get_ip_reputation", return_value=BEHAVIORAL_REPUTATION
    ):
        paged_resp = client.get("/alerts?limit=1&offset=0&sort=newest")
        summary_resp = client.get("/alerts/summary")

    assert paged_resp.status_code == 200
    assert summary_resp.status_code == 200

    paged_payload = paged_resp.get_json()
    summary_payload = summary_resp.get_json()

    assert len(paged_payload["items"]) == 1
    assert paged_payload["total"] == 3
    assert summary_payload["metrics"] == {
        "total_alerts": 3,
        "high_count": 2,
        "medium_count": 1,
        "low_count": 0,
        "unique_source_ips": 2,
    }


def test_get_alerts_summary_since_tuning_preserves_non_pfsense_metrics(client, postgres_db, monkeypatch):
    conn, cur = postgres_db
    monkeypatch.setenv("SIEM_PFSENSE_TUNING_BASELINE", "2026-06-01T00:00:00Z")
    cur.execute(
        """
        INSERT INTO alerts (
            alert_type, severity, source_ip, source, source_type, message, status, created_at
        )
        VALUES
            ('pfsense_firewall_repeated_deny', 'low', '198.51.100.214', 'pfsense', 'firewall', 'legacy pfSense', 'open', '2026-05-01T00:00:00+00:00'),
            ('pfsense_firewall_port_scan', 'medium', '198.51.100.215', 'pfsense', 'firewall', 'current pfSense', 'open', '2026-06-15T00:00:00+00:00'),
            ('failed_login_threshold', 'high', '198.51.100.216', 'bank_app', 'custom', 'non-pfSense', 'open', '2026-05-01T00:00:00+00:00')
        """
    )
    conn.commit()

    _login_as_super_admin(client)
    resp = _fetch_alert_summary_response_for_path(client, conn, "/alerts/summary?operational_scope=since_tuning")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["metrics"]["total_alerts"] == 2
    assert payload["metrics"]["high_count"] == 1
    assert payload["metrics"]["medium_count"] == 1


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
    alert = _alert_by_type(_alert_items(resp.get_json()), "failed_login_threshold")
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
    alert = _alert_by_type(_alert_items(resp.get_json()), "port_scan_threshold")
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
    data = _alert_items(resp.get_json())
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
    alert = _alert_by_type(_alert_items(resp.get_json()), "correlated_activity")
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
    alert = _alert_by_type(_alert_items(resp.get_json()), "web_to_app_attack_pattern")
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
    alert = _alert_by_type(_alert_items(resp.get_json()), "failed_login_threshold")
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
    data = _alert_items(resp.get_json())
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
    data = _alert_items(resp.get_json())
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
    data = _alert_items(resp.get_json())
    assert isinstance(data, list)

    _assert_null_mitre(_alert_by_type(data, "custom_unmapped_alert"))


def test_get_alerts_pfsense_quality_metadata_and_why_fired_use_persisted_context_only(client, postgres_db):
    conn, cur = postgres_db
    context = {
        "action": "block",
        "direction": "out",
        "event_count": 6,
        "destination_ip": "203.0.113.10",
        "destination_port": 22,
        "source_port": 443,
        "tcp_flags": "RA",
        "protocol": "tcp",
        "interface": "wan",
        "first_seen": "2026-07-13T13:00:00Z",
        "last_seen": "2026-07-13T13:09:00Z",
        "traffic_role": {
            "classification": "reply_or_teardown_like",
            "reason": "Protected-host service traffic replied to a remote ephemeral port without a new SYN",
        },
        "target_context": {
            "mode": "exact_target",
            "destination_ip": "203.0.113.10",
            "destination_port": 22,
            "protocol": "tcp",
            "firewall_action": "block",
            "attempts": 6,
            "first_seen": "2026-07-13T13:00:00Z",
            "last_seen": "2026-07-13T13:09:00Z",
            "interface": "wan",
            "direction": "out",
        },
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
            context,
            reputation_score,
            reputation_label,
            reputation_source,
            reputation_summary
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            "pfsense_firewall_repeated_deny",
            "high",
            "198.51.100.250",
            "pfsense",
            "firewall",
            "Repeated deny threshold exceeded",
            "resolved",
            Json(context),
            EXTERNAL_REPUTATION["reputation_score"],
            EXTERNAL_REPUTATION["reputation_label"],
            EXTERNAL_REPUTATION["reputation_source"],
            EXTERNAL_REPUTATION["reputation_summary"],
        ),
    )
    alert_id = cur.fetchone()[0]
    cur.execute(
        """
        INSERT INTO audit_log (
            event_type,
            actor_username,
            actor_role,
            target_alert_id,
            request_path,
            details
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            "UPDATE_ALERT_STATUS",
            "testadmin",
            "super_admin",
            alert_id,
            f"/alerts/{alert_id}/status",
            Json({"status": "resolved"}),
        ),
    )
    conn.commit()

    _login_as_super_admin(client)
    alerts_resp = _fetch_alerts_response(client, conn)
    assert alerts_resp.status_code == 200
    alert = _alert_by_type(_alert_items(alerts_resp.get_json()), "pfsense_firewall_repeated_deny")
    assert alert["pfsense_quality"]["why_fired_available"] is True
    assert alert["pfsense_quality"]["suppressed_rollup"] is False
    assert alert["pfsense_quality"]["cooldown"]["window_minutes"] > 0
    assert alert["pfsense_quality"]["cooldown"]["resolved_at"] is not None
    assert alert["context"] == context

    why_fired_resp = _fetch_why_fired_response(client, conn, alert_id)
    assert why_fired_resp.status_code == 200
    payload = why_fired_resp.get_json()
    assert payload["alert_id"] == alert_id
    assert payload["rule_id"] == "pfsense_firewall_repeated_deny"
    assert payload["source"] == "pfsense"
    assert payload["source_type"] == "firewall"
    assert payload["context"] == context
    assert payload["context"]["target_context"]["mode"] == "exact_target"
    assert payload["suppressed_rollup"] is False
    assert payload["cooldown"]["window_minutes"] > 0
    evidence = {item["field"]: item["value"] for item in payload["evidence"]}
    assert evidence["action"] == "block"
    assert evidence["direction"] == "LAN → WAN (outbound)"
    assert evidence["event_count"] == 6
    assert evidence["destination_ip"] == "203.0.113.10"
    assert evidence["destination_port"] == 22
    assert evidence["source_port"] == 443
    assert evidence["tcp_flags"] == "RA"
    assert evidence["traffic_role"] == "Reply or teardown traffic"
    assert "ephemeral port" in evidence["traffic_role_reason"]


def test_get_alert_why_fired_rejects_non_pfsense_alerts(client, postgres_db):
    conn, cur = postgres_db
    _insert_alert(
        cur,
        alert_type="failed_login_threshold",
        source_ip="198.51.100.251",
        message="Failed login threshold exceeded",
    )
    cur.execute("SELECT id FROM alerts WHERE alert_type = %s", ("failed_login_threshold",))
    alert_id = cur.fetchone()[0]
    conn.commit()

    _login_as_super_admin(client)
    resp = _fetch_why_fired_response(client, conn, alert_id)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Why this fired is available only for pfSense alerts"


def test_get_recon_activities_and_detail_return_bounded_payloads(client, postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO alerts (
            alert_type, severity, source_ip, source, source_type, message, status, context
        )
        VALUES (
            'pfsense_firewall_port_scan', 'medium', '198.51.100.252', 'pfsense', 'firewall',
            'Port scan aggregate member', 'open',
            %s
        )
        RETURNING id
        """,
        (
            Json(
                {
                    "target_context": {
                        "mode": "aggregate_sample",
                        "primary_destination_ip": "203.0.113.20",
                        "primary_destination_port": 5060,
                        "sample_destination_ips": ["203.0.113.20", "203.0.113.21"],
                        "sample_destination_ports": [5060],
                        "distinct_destination_count": 2,
                        "distinct_port_count": 1,
                    }
                }
            ),
        ),
    )
    alert_id = cur.fetchone()[0]
    cur.execute(
        """
        INSERT INTO recon_activities (
            activity_type, source, source_type, status, severity, coordination_status,
            protected_range_key, service_signature, first_seen, last_seen, assessment_text, membership_evidence, summary
        )
        VALUES (
            'distributed_internet_reconnaissance', 'pfsense', 'firewall', 'monitoring', 'medium', 'not_established',
            '203.0.113.0/24', '[5060]'::jsonb, NOW() - INTERVAL '5 minutes', NOW(),
            'Distributed commodity scanning against public services. Coordination is not established.',
            '{}'::jsonb,
            %s
        )
        RETURNING id
        """,
        (
            Json(
                {
                    "source_ip_count": 1,
                    "destination_ip_count": 2,
                    "primary_destination_ports": [5060],
                    "alert_types": ["pfsense_firewall_port_scan"],
                    "underlying_alert_count": 1,
                    "target_context": {
                        "mode": "aggregate_sample",
                        "primary_destination_ip": "203.0.113.20",
                        "primary_destination_port": 5060,
                        "sample_destination_ips": ["203.0.113.20", "203.0.113.21"],
                        "sample_destination_ports": [5060],
                    },
                }
            ),
        ),
    )
    activity_id = cur.fetchone()[0]
    cur.execute(
        """
        INSERT INTO recon_activity_alerts (recon_activity_id, alert_id, membership_evidence)
        VALUES (%s, %s, '{}'::jsonb)
        """,
        (activity_id, alert_id),
    )
    conn.commit()

    _login_as_super_admin(client)
    list_resp = _fetch_recon_activities_response(client, conn)
    assert list_resp.status_code == 200
    payload = list_resp.get_json()
    assert payload["count"] == 1
    assert payload["items"][0]["label"] == "Distributed Internet Reconnaissance Activity"
    assert payload["items"][0]["display"]["target_summary"] == "203.0.113.20 (203.0.113.0/24)"

    detail_resp = _fetch_recon_activities_response(client, conn, f"/recon-activities/{activity_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.get_json()
    assert detail["summary"]["primary_destination_ports"] == [5060]
    assert detail["alerts"][0]["id"] == alert_id
    assert detail["display"]["coordination_label"] == "Coordination not established"


def test_get_alerts_exact_source_and_alert_id_filters_do_not_broaden_results(client, postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO alerts (
            alert_type, severity, source_ip, source, source_type, message, status
        )
        VALUES
            ('exact_source_match', 'high', '198.51.100.10', 'pfsense', 'firewall', 'source match', 'open'),
            ('exact_source_other', 'high', '198.51.100.11', 'pfsense', 'firewall', 'source other', 'open')
        RETURNING id, alert_type
        """
    )
    inserted = cur.fetchall()
    conn.commit()
    exact_alert_id = inserted[0][0]

    _login_as_super_admin(client)
    resp = _fetch_alerts_response_for_path(
        client,
        conn,
        "/alerts?exact_source_ip=198.51.100.10&search=198.51.100&sort=oldest",
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert [item["alert_type"] for item in payload["items"]] == ["exact_source_match"]

    summary_resp = _fetch_alert_summary_response_for_path(
        client,
        conn,
        f"/alerts/summary?alert_id={exact_alert_id}",
    )
    assert summary_resp.status_code == 200
    summary_payload = summary_resp.get_json()
    assert summary_payload["metrics"]["total_alerts"] == 1
    assert summary_payload["top_source_ips"] == [{"name": "198.51.100.10", "value": 1}]


def test_get_alerts_exact_target_filter_matches_primary_and_sample_destination_ips(client, postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO alerts (
            alert_type, severity, source_ip, source, source_type, message, status, context
        )
        VALUES
            (
                'target_primary_match',
                'medium',
                '198.51.100.21',
                'pfsense',
                'firewall',
                'primary target match',
                'open',
                %s
            ),
            (
                'target_sample_match',
                'medium',
                '198.51.100.22',
                'pfsense',
                'firewall',
                'sample target match',
                'open',
                %s
            ),
            (
                'target_non_match',
                'medium',
                '198.51.100.23',
                'pfsense',
                'firewall',
                'different target',
                'open',
                %s
            )
        """,
        (
            Json({"target_context": {"primary_destination_ip": "203.0.113.30"}}),
            Json({"target_context": {"sample_destination_ips": ["203.0.113.30", "203.0.113.31"]}}),
            Json({"target_context": {"primary_destination_ip": "203.0.113.40"}}),
        ),
    )
    conn.commit()

    _login_as_super_admin(client)
    resp = _fetch_alerts_response_for_path(
        client,
        conn,
        "/alerts?exact_target_ip=203.0.113.30&sort=oldest",
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert [item["alert_type"] for item in payload["items"]] == [
        "target_primary_match",
        "target_sample_match",
    ]

    summary_resp = _fetch_alert_summary_response_for_path(
        client,
        conn,
        "/alerts/summary?exact_target_ip=203.0.113.30",
    )
    assert summary_resp.status_code == 200
    assert summary_resp.get_json()["metrics"]["total_alerts"] == 2


def test_get_alerts_summary_honors_timeline_range_and_reports_bucket_metadata(client, postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO alerts (
            alert_type, severity, source_ip, source, source_type, message, status, created_at
        )
        VALUES
            ('range_recent', 'high', '198.51.100.30', 'pfsense', 'firewall', 'recent alert', 'open', NOW() - INTERVAL '2 hours'),
            ('range_old', 'high', '198.51.100.31', 'pfsense', 'firewall', 'old alert', 'open', NOW() - INTERVAL '40 days')
        """
    )
    conn.commit()

    _login_as_super_admin(client)
    summary_resp = _fetch_alert_summary_response_for_path(
        client,
        conn,
        "/alerts/summary?timeline_range=24h",
    )

    assert summary_resp.status_code == 200
    payload = summary_resp.get_json()
    assert payload["timeline_meta"]["range"] == "24h"
    assert payload["timeline_meta"]["bucket"] == "hour"
    assert payload["timeline"] == [
        {
            "bucketStart": payload["timeline"][0]["bucketStart"],
            "count": 1,
        }
    ]


def test_get_alerts_summary_excludes_configured_synthetic_ips_from_visuals(client, postgres_db, monkeypatch):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO alerts (
            alert_type, severity, source_ip, source, source_type, message, status
        )
        VALUES
            ('synthetic_source', 'medium', '198.51.100.40', 'pfsense', 'firewall', 'synthetic top ip', 'open'),
            ('legit_source', 'medium', '198.51.100.41', 'pfsense', 'firewall', 'legit top ip', 'open'),
            ('legit_source_repeat', 'medium', '198.51.100.41', 'pfsense', 'firewall', 'legit top ip 2', 'open')
        """
    )
    conn.commit()
    monkeypatch.setenv("SIEM_SYNTHETIC_SOURCE_IP_EXCLUSIONS", "198.51.100.40")

    _login_as_super_admin(client)
    summary_resp = _fetch_alert_summary_response(client, conn)

    assert summary_resp.status_code == 200
    payload = summary_resp.get_json()
    assert payload["top_source_ips"] == [{"name": "198.51.100.41", "value": 2}]
    assert all(marker["source_ip"] != "198.51.100.40" for marker in payload["map_markers"])
