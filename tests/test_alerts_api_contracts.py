from unittest.mock import patch

import siem_backend


ADMIN_USER = "testadmin"
ADMIN_PASS = "testpassword123!"
REPUTATION = {
    "reputation_score": 0,
    "reputation_label": "low-risk",
    "reputation_summary": "Contract test reputation",
    "contributing_signals": [],
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
):
    cur.execute(
        """
        INSERT INTO alerts (
            alert_type,
            severity,
            source_ip,
            source,
            source_type,
            message,
            status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (alert_type, severity, source_ip, "bank_app", "custom", message, status),
    )


def _login_as_super_admin(client):
    resp = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert resp.status_code == 200


def _fetch_alerts_response(client, conn):
    with patch("siem_backend.get_db_connection", return_value=_RouteSafeConnection(conn)), patch(
        "siem_backend.get_ip_reputation", return_value=REPUTATION
    ):
        return client.get("/alerts")


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


def test_get_alerts_mitre_fields_exist_and_unknown_mapping_keeps_shape(client, postgres_db):
    conn, cur = postgres_db
    _insert_alert(
        cur,
        alert_type="failed_login_threshold",
        source_ip="198.51.100.203",
        message="Known MITRE mapping alert",
    )
    _insert_alert(
        cur,
        alert_type="custom_unmapped_alert",
        source_ip="198.51.100.204",
        message="Unknown MITRE mapping alert",
    )
    conn.commit()

    _login_as_super_admin(client)
    resp = _fetch_alerts_response(client, conn)

    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)

    known_alert = next(alert for alert in data if alert.get("alert_type") == "failed_login_threshold")
    unknown_alert = next(alert for alert in data if alert.get("alert_type") == "custom_unmapped_alert")

    for field in ("mitre_technique_id", "mitre_technique_name", "mitre_tactic"):
        assert field in known_alert
        assert field in unknown_alert
