from unittest.mock import patch

from core.notification_policy_service import (
    evaluate_notification_policy,
    format_alert_notification,
    format_incident_notification,
    notify_for_alert,
    notify_for_incident,
)


def _insert_alert(cur, *, source="pfsense", source_type="firewall", severity="high", alert_type="pfsense_firewall_port_scan"):
    cur.execute(
        """
        INSERT INTO alerts (
            alert_type, severity, source_ip, source, source_type, message, status, response_action, response_status
        )
        VALUES (%s, %s, %s::inet, %s, %s, %s, 'open', 'monitor', 'pending')
        RETURNING id
        """,
        (
            alert_type,
            severity,
            "198.51.100.11",
            source,
            source_type,
            "Deterministic notification test alert",
        ),
    )
    return cur.fetchone()[0]


def _insert_incident(cur, *, severity="high", source_ip="198.51.100.11", alert_id=None):
    cur.execute(
        """
        INSERT INTO incidents (title, severity, priority, status, source_ip)
        VALUES ('Deterministic incident', %s, 'P2', 'open', %s::inet)
        RETURNING id
        """,
        (severity, source_ip),
    )
    incident_id = cur.fetchone()[0]
    if alert_id is not None:
        cur.execute(
            "INSERT INTO incident_alerts (incident_id, alert_id) VALUES (%s, %s)",
            (incident_id, alert_id),
        )
    return incident_id


def test_evaluate_notification_policy_respects_global_disable():
    decision = evaluate_notification_policy(
        {
            "status": "applied",
            "slack_enabled": False,
            "minimum_severity": "low",
            "notify_on_alerts": True,
            "notify_on_incidents": True,
        },
        event_kind="alert",
        severity="critical",
        source="pfsense",
        source_type="firewall",
    )
    assert decision["should_notify"] is False
    assert decision["reason"] == "slack_disabled"


def test_evaluate_notification_policy_routes_pfsense_and_honeypot_independently():
    policy = {
        "status": "applied",
        "slack_enabled": True,
        "minimum_severity": "medium",
        "notify_on_alerts": True,
        "notify_on_incidents": True,
        "slack_format": "compact",
        "pfsense_destination": "#pf",
        "honeypot_destination": "#hp",
    }
    pfsense = evaluate_notification_policy(
        policy,
        event_kind="alert",
        severity="high",
        source="pfsense",
        source_type="firewall",
    )
    honeypot = evaluate_notification_policy(
        policy,
        event_kind="alert",
        severity="high",
        source="honeypot",
        source_type="honeypot",
    )
    assert pfsense["destination"] == "#pf"
    assert honeypot["destination"] == "#hp"


def test_evaluate_notification_policy_distinguishes_alerts_and_incidents():
    policy = {
        "status": "applied",
        "slack_enabled": True,
        "minimum_severity": "low",
        "notify_on_alerts": False,
        "notify_on_incidents": True,
        "slack_format": "compact",
        "pfsense_destination": "#pf",
        "honeypot_destination": "#hp",
    }
    alert_decision = evaluate_notification_policy(
        policy,
        event_kind="alert",
        severity="critical",
        source="pfsense",
        source_type="firewall",
    )
    incident_decision = evaluate_notification_policy(
        policy,
        event_kind="incident",
        severity="critical",
        source="pfsense",
        source_type="firewall",
    )
    assert alert_decision["should_notify"] is False
    assert alert_decision["reason"] == "alerts_disabled"
    assert incident_decision["should_notify"] is True


def test_evaluate_notification_policy_fails_safe_when_policy_unavailable_or_source_unrouted():
    unavailable = evaluate_notification_policy(
        {"status": "unavailable"},
        event_kind="alert",
        severity="critical",
        source="pfsense",
        source_type="firewall",
    )
    unrouted = evaluate_notification_policy(
        {
            "status": "applied",
            "slack_enabled": True,
            "minimum_severity": "low",
            "notify_on_alerts": True,
            "notify_on_incidents": True,
            "slack_format": "compact",
            "pfsense_destination": "#pf",
            "honeypot_destination": "#hp",
        },
        event_kind="alert",
        severity="critical",
        source="nginx",
        source_type="proxy",
    )
    assert unavailable["should_notify"] is False
    assert unavailable["reason"] == "policy_unavailable"
    assert unrouted["should_notify"] is False
    assert unrouted["reason"] == "source_not_routed"


def test_formatters_bound_compact_and_detailed_content():
    alert = {
        "id": 7,
        "severity": "high",
        "source": "pfsense",
        "alert_type": "pfsense_firewall_port_scan",
        "source_ip": "198.51.100.11",
        "message": "Port scan observed",
        "response_action": "monitor",
        "response_status": "pending",
    }
    compact = format_alert_notification(alert, slack_format="compact", destination="#pf")
    detailed = format_alert_notification(alert, slack_format="detailed", destination="#pf")
    assert compact.startswith("[#pf] ALERT HIGH")
    assert "Port scan observed" in compact
    assert "Response action: monitor" in detailed
    assert "Rule: pfsense_firewall_port_scan" in detailed

    incident = {
        "id": 4,
        "severity": "critical",
        "title": "Escalated incident",
        "status": "open",
        "source": "honeypot",
        "alert_type": "honeypot_credential_stuffing_threshold",
    }
    incident_detail = format_incident_notification(
        incident, slack_format="detailed", destination="#hp"
    )
    assert "Incident notification" in incident_detail
    assert "Rule: honeypot_credential_stuffing_threshold" in incident_detail


def test_notify_for_alert_records_blocked_attempt_when_below_threshold(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, severity="medium")
    conn.commit()

    with patch(
        "core.notification_policy_service.get_effective_notification_policy",
        return_value={
            "status": "applied",
            "slack_enabled": True,
            "minimum_severity": "high",
            "notify_on_alerts": True,
            "notify_on_incidents": True,
            "slack_format": "compact",
            "pfsense_destination": "#pf",
            "honeypot_destination": "#hp",
        },
    ), patch("core.notification_policy_service.get_integration_adapter") as adapter_factory:
        attempt = notify_for_alert(conn, alert_id)
        conn.commit()

    assert adapter_factory.called is False
    assert attempt["status"] == "blocked"
    assert attempt["failure_code"] == "below_minimum_severity"


def test_notify_for_alert_and_incident_use_existing_slack_adapter_contract(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, source="honeypot", source_type="honeypot", alert_type="honeypot_credential_stuffing_threshold")
    incident_id = _insert_incident(cur, alert_id=alert_id)
    conn.commit()

    adapter = type(
        "Adapter",
        (),
        {
            "execute": lambda self, action, params, context: {
                "success": True,
                "simulated": False,
                "executed": True,
                "mode": "real",
                "message": "sent",
                "metadata": {"failure_classification": None, "timeout_seconds": 3},
            }
        },
    )()

    with patch(
        "core.notification_policy_service.get_effective_notification_policy",
        return_value={
            "status": "applied",
            "slack_enabled": True,
            "minimum_severity": "high",
            "notify_on_alerts": True,
            "notify_on_incidents": True,
            "slack_format": "detailed",
            "pfsense_destination": "#pf",
            "honeypot_destination": "#hp",
        },
    ), patch("core.notification_policy_service.get_integration_adapter", return_value=adapter):
        alert_attempt = notify_for_alert(conn, alert_id)
        incident_attempt = notify_for_incident(conn, incident_id)
        conn.commit()

    assert alert_attempt["status"] == "success"
    assert incident_attempt["status"] == "success"

    cur.execute(
        """
        SELECT metadata->>'destination_label', metadata->>'event_kind'
        FROM notification_delivery_attempts
        WHERE alert_id = %s OR incident_id = %s
        ORDER BY id
        """,
        (alert_id, incident_id),
    )
    rows = cur.fetchall()
    assert rows == [("#hp", "alert"), ("#hp", "incident")]
