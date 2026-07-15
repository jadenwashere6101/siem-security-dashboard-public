from datetime import datetime, timezone
from unittest.mock import patch

from psycopg2.extras import Json

from core.notification_policy_service import (
    evaluate_notification_policy,
    format_alert_notification,
    format_incident_notification,
    notify_for_alert,
    notify_for_incident,
    notify_for_material_recon_activity,
    send_notification_policy_route_test,
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


def _insert_recon_activity(cur, *, severity="high", status="open", ports=None, opened=False):
    selected_ports = list(ports or [5060])
    cur.execute(
        """
        INSERT INTO recon_activities (
            activity_type,
            source,
            source_type,
            status,
            severity,
            coordination_status,
            protected_range_key,
            service_signature,
            first_seen,
            last_seen,
            assessment_text,
            membership_evidence,
            summary,
            opened_notification_sent_at,
            last_notified_fingerprint,
            last_notified_at
        )
        VALUES (
            'distributed_internet_reconnaissance',
            'pfsense',
            'firewall',
            %s,
            %s,
            'not_established',
            '203.0.113.0/24',
            %s::jsonb,
            NOW() - INTERVAL '5 minutes',
            NOW(),
            'Distributed commodity scanning against public services. Coordination is not established.',
            '{}'::jsonb,
            %s::jsonb,
            %s,
            NULL,
            NULL
        )
        RETURNING id
        """,
        (
            status,
            severity,
            Json(selected_ports),
            Json(
                {
                    "primary_destination_ports": selected_ports,
                    "target_context": {
                        "primary_destination_port": selected_ports[0],
                        "sample_destination_ports": selected_ports,
                    },
                }
            ),
            datetime.now(timezone.utc) if opened else None,
        ),
    )
    return cur.fetchone()[0]


def _policy(**overrides):
    policy = {
        "status": "applied",
        "slack_enabled": True,
        "minimum_severity": "high",
        "notify_on_alerts": True,
        "notify_on_incidents": True,
        "slack_format": "compact",
        "pfsense_destination": "#pf",
        "honeypot_destination": "#hp",
        "critical_cross_source_destination": "#critical",
    }
    policy.update(overrides)
    return policy


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
    policy = _policy(minimum_severity="medium")
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
    policy = _policy(minimum_severity="low", notify_on_alerts=False)
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


def test_evaluate_notification_policy_fails_safe_when_policy_unavailable():
    unavailable = evaluate_notification_policy(
        {"status": "unavailable"},
        event_kind="alert",
        severity="critical",
        source="pfsense",
        source_type="firewall",
    )
    assert unavailable["should_notify"] is False
    assert unavailable["reason"] == "policy_unavailable"


def test_evaluate_notification_policy_routes_critical_cross_source_only_for_critical():
    critical = evaluate_notification_policy(
        _policy(minimum_severity="low"),
        event_kind="alert",
        severity="critical",
        source="bank_app",
        source_type="custom",
    )
    non_critical = evaluate_notification_policy(
        _policy(minimum_severity="low"),
        event_kind="alert",
        severity="high",
        source="bank_app",
        source_type="custom",
    )
    assert critical["should_notify"] is True
    assert critical["route_key"] == "critical_cross_source"
    assert critical["destination"] == "#critical"
    assert non_critical["should_notify"] is False
    assert non_critical["reason"] == "source_not_routed"


def test_evaluate_notification_policy_missing_critical_cross_source_destination_fails_safe():
    decision = evaluate_notification_policy(
        _policy(minimum_severity="low", critical_cross_source_destination=""),
        event_kind="alert",
        severity="critical",
        source="nginx",
        source_type="web_log",
    )
    assert decision["should_notify"] is False
    assert decision["reason"] == "source_not_routed"


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
        return_value=_policy(),
    ), patch("core.notification_policy_service.get_integration_adapter") as adapter_factory:
        attempt = notify_for_alert(conn, alert_id)
        conn.commit()

    assert adapter_factory.called is False
    assert attempt["status"] == "blocked"
    assert attempt["failure_code"] == "below_minimum_severity"


def test_notify_for_alert_short_circuits_when_slack_disabled(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, severity="critical")
    conn.commit()

    with patch(
        "core.notification_policy_service.get_effective_notification_policy",
        return_value=_policy(slack_enabled=False, minimum_severity="low"),
    ), patch("core.notification_policy_service.get_integration_adapter") as adapter_factory:
        attempt = notify_for_alert(conn, alert_id)
        conn.commit()

    assert adapter_factory.called is False
    assert attempt["status"] == "blocked"
    assert attempt["failure_code"] == "slack_disabled"


def test_notification_policy_route_test_bypasses_only_global_slack_disable_without_other_writes(postgres_db):
    conn, cur = postgres_db
    before = {}
    for table in ("alerts", "incidents", "playbook_executions", "approval_requests", "notification_delivery_attempts"):
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        before[table] = cur.fetchone()[0]

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
        "core.notification_policy_service.load_notification_policy",
        return_value=_policy(slack_enabled=False, minimum_severity="critical"),
    ), patch("core.notification_policy_service.get_integration_adapter", return_value=adapter):
        result = send_notification_policy_route_test(
            conn,
            route_key="pfsense",
            requested_by="testadmin",
            bypass_slack_disabled=True,
        )
        conn.commit()

    assert result["success"] is True
    assert result["status"] == "success"

    for table in ("alerts", "incidents", "playbook_executions", "approval_requests"):
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        assert cur.fetchone()[0] == before[table]

    cur.execute("SELECT COUNT(*) FROM notification_delivery_attempts")
    assert cur.fetchone()[0] == before["notification_delivery_attempts"] + 1


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
        return_value=_policy(slack_format="detailed"),
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


def test_recon_activity_notifications_send_one_opening_and_deduplicate_unchanged_updates(postgres_db):
    conn, cur = postgres_db
    activity_id = _insert_recon_activity(cur, severity="high", ports=[5060], opened=False)
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
        return_value=_policy(minimum_severity="high"),
    ), patch("core.notification_policy_service.get_integration_adapter", return_value=adapter):
        first = notify_for_material_recon_activity(conn, activity_id)
        conn.commit()
        second = notify_for_material_recon_activity(conn, activity_id)
        conn.commit()

    assert first["success"] is True
    assert first["purpose"] == "immediate_alert"
    assert second["suppressed"] is True
    assert second["policy_decision"]["reason"] == "no_material_change"

    cur.execute(
        """
        SELECT COUNT(*)
        FROM notification_delivery_attempts
        WHERE recon_activity_id = %s
          AND status = 'success'
        """,
        (activity_id,),
    )
    assert cur.fetchone()[0] == 1

    cur.execute(
        """
        SELECT opened_notification_sent_at, last_notified_fingerprint, last_notified_at
        FROM recon_activities
        WHERE id = %s
        """,
        (activity_id,),
    )
    opened_at, fingerprint, last_notified_at = cur.fetchone()
    assert opened_at is not None
    assert fingerprint
    assert last_notified_at is not None


def test_recon_activity_notifications_send_material_update_once(postgres_db):
    conn, cur = postgres_db
    activity_id = _insert_recon_activity(cur, severity="high", ports=[5060], opened=False)
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
        return_value=_policy(minimum_severity="high"),
    ), patch("core.notification_policy_service.get_integration_adapter", return_value=adapter):
        notify_for_material_recon_activity(conn, activity_id)
        conn.commit()

        cur.execute(
            """
            UPDATE recon_activities
            SET summary = jsonb_set(summary, '{primary_destination_ports}', '[5060,22]'::jsonb, true)
            WHERE id = %s
            """,
            (activity_id,),
        )
        conn.commit()

        updated = notify_for_material_recon_activity(conn, activity_id)
        conn.commit()
        duplicate_update = notify_for_material_recon_activity(conn, activity_id)
        conn.commit()

    assert updated["success"] is True
    assert updated["purpose"] == "investigation_update"
    assert duplicate_update["suppressed"] is True
    assert duplicate_update["policy_decision"]["reason"] == "no_material_change"

    cur.execute(
        """
        SELECT metadata->>'purpose', COUNT(*)
        FROM notification_delivery_attempts
        WHERE recon_activity_id = %s AND status = 'success'
        GROUP BY metadata->>'purpose'
        ORDER BY metadata->>'purpose'
        """,
        (activity_id,),
    )
    assert cur.fetchall() == [("immediate_alert", 1), ("investigation_update", 1)]
