from unittest.mock import patch

import pytest
from psycopg2.extras import Json

import siem_backend
import engines.detection_engine as backend_detection_engine
from core.core_playbook_pack_v1 import (
    CORE_V1_PFSENSE_PORT_SCAN_CONTAINMENT_ID,
    CORE_V1_PFSENSE_PORT_SCAN_INVESTIGATION_ID,
    CORE_V1_PFSENSE_REPEATED_DENY_INVESTIGATION_ID,
    CORE_V1_PFSENSE_SUSPICIOUS_ALLOW_CONTAINMENT_ID,
    seed_core_playbook_pack_v1,
)
from core import approval_store, playbook_store
from engines import playbook_step_executor
from engines.playbook_engine import match_playbooks
from engines.ingest_engine import ingest_normalized_event
from helpers.enrichment_helpers import enrich_alert_with_mitre


REPUTATION_LOW = {
    "reputation_score": 10,
    "reputation_label": "low-risk",
    "reputation_source": "test-reputation",
    "reputation_summary": "Deterministic low-risk test reputation",
}
REPUTATION_HIGH = {
    "reputation_score": 85,
    "reputation_label": "high-risk",
    "reputation_source": "test-reputation",
    "reputation_summary": "Deterministic high-risk test reputation",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def insert_pfsense_event(
    cur,
    *,
    event_type,
    source_ip,
    destination_ip="203.0.113.10",
    destination_port=443,
    protocol="tcp",
    interface="igb1",
    direction="in",
    seconds_ago=1,
    action=None,
):
    raw_payload = {
        "action": action or ("block" if event_type == "firewall_block" else "pass"),
        "interface": interface,
        "direction": direction,
        "ip_version": "4",
        "protocol": protocol,
        "source_ip": source_ip,
        "destination_ip": destination_ip,
        "destination_port": destination_port,
    }
    cur.execute(
        """
        INSERT INTO events (
            event_type, severity, source_ip, source, source_type,
            event_timestamp, message, app_name, environment, raw_payload, created_at
        ) VALUES (
            %s, %s, %s, 'pfsense', 'firewall',
            NOW() - (%s * INTERVAL '1 second'), %s, 'pfsense_filterlog', 'test', %s,
            NOW() - (%s * INTERVAL '1 second')
        )
        """,
        (
            event_type,
            "medium" if event_type == "firewall_block" else "low",
            source_ip,
            seconds_ago,
            f"pfSense {event_type} test event",
            Json(raw_payload),
            seconds_ago,
        ),
    )


def make_pfsense_event(
    *,
    event_type="firewall_block",
    source_ip="198.51.100.20",
    destination_ip="203.0.113.10",
    destination_port=443,
    protocol="tcp",
    interface="igb1",
    direction="in",
    action=None,
):
    return {
        "event_type": event_type,
        "severity": "medium" if event_type == "firewall_block" else "low",
        "source_ip": source_ip,
        "source": "pfsense",
        "source_type": "firewall",
        "event_timestamp": None,
        "message": f"pfSense {event_type} test event",
        "app_name": "pfsense_filterlog",
        "environment": "test",
        "raw_payload": {
            "action": action or ("block" if event_type == "firewall_block" else "pass"),
            "interface": interface,
            "direction": direction,
            "ip_version": "4",
            "protocol": protocol,
            "source_ip": source_ip,
            "destination_ip": destination_ip,
            "destination_port": destination_port,
        },
    }


def fetch_alerts_for_ip(cur, source_ip):
    cur.execute(
        """
        SELECT id, alert_type, severity, response_action, response_status, context
        FROM alerts
        WHERE source_ip = %s
        ORDER BY id
        """,
        (source_ip,),
    )
    return cur.fetchall()


def fetch_alert_by_type(cur, source_ip, alert_type):
    cur.execute(
        """
        SELECT id, alert_type, severity, response_action, response_status, context
        FROM alerts
        WHERE source_ip = %s AND alert_type = %s
        """,
        (source_ip, alert_type),
    )
    return cur.fetchone()


# ---------------------------------------------------------------------------
# Taxonomy / isolated event behavior
# ---------------------------------------------------------------------------


def test_isolated_firewall_block_produces_no_alert(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.201"
    insert_pfsense_event(cur, event_type="firewall_block", source_ip=source_ip)

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        assert backend_detection_engine._generate_pfsense_repeated_deny_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        ) == []
        assert backend_detection_engine._generate_pfsense_port_scan_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        ) == []
        assert backend_detection_engine._generate_pfsense_noisy_source_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        ) == []

    assert fetch_alerts_for_ip(cur, source_ip) == []


def test_isolated_firewall_allow_non_sensitive_port_produces_no_alert(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.202"
    insert_pfsense_event(
        cur,
        event_type="firewall_allow",
        source_ip=source_ip,
        destination_port=443,
        direction="out",
    )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        assert backend_detection_engine._generate_pfsense_suspicious_allow_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        ) == []

    assert fetch_alerts_for_ip(cur, source_ip) == []


# ---------------------------------------------------------------------------
# Repeated deny
# ---------------------------------------------------------------------------


def test_repeated_deny_threshold_creates_aggregate_alert_with_expected_fields(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.30"

    for seconds_ago in range(5, 0, -1):
        insert_pfsense_event(
            cur,
            event_type="firewall_block",
            source_ip=source_ip,
            destination_ip="203.0.113.55",
            destination_port=8080,
            protocol="tcp",
            seconds_ago=seconds_ago,
        )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        alerts_created = backend_detection_engine._generate_pfsense_repeated_deny_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )

    assert len(alerts_created) == 1
    assert alerts_created[0]["severity"] == "medium"
    assert alerts_created[0]["response_action"] == "enrich_source_ip"

    alert = fetch_alert_by_type(cur, source_ip, "pfsense_firewall_repeated_deny")
    assert alert is not None
    _, alert_type, severity, response_action, response_status, context = alert
    assert severity == "medium"
    assert response_action == "enrich_source_ip"
    assert response_status == "pending"
    assert context["destination_ip"] == "203.0.113.55"
    assert context["destination_port"] == "8080"
    assert context["protocol"] == "tcp"
    assert context["event_count"] == 5
    assert context["first_seen"] is not None
    assert context["last_seen"] is not None

    mitre = enrich_alert_with_mitre({"alert_type": alert_type})
    assert mitre["mitre_technique_id"] is None


def test_repeated_deny_escalates_to_high_severity_with_high_reputation(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.31"

    for seconds_ago in range(5, 0, -1):
        insert_pfsense_event(
            cur,
            event_type="firewall_block",
            source_ip=source_ip,
            destination_ip="203.0.113.56",
            destination_port=22,
            seconds_ago=seconds_ago,
        )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_HIGH
    ):
        alerts_created = backend_detection_engine._generate_pfsense_repeated_deny_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )

    assert len(alerts_created) == 1
    assert alerts_created[0]["severity"] == "high"
    assert alerts_created[0]["response_action"] == "request_firewall_block_approval"


def test_repeated_deny_duplicate_suppression_keeps_single_open_alert(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.32"

    for seconds_ago in range(5, 0, -1):
        insert_pfsense_event(
            cur,
            event_type="firewall_block",
            source_ip=source_ip,
            destination_ip="203.0.113.57",
            destination_port=445,
            seconds_ago=seconds_ago,
        )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        first_result = backend_detection_engine._generate_pfsense_repeated_deny_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )
        insert_pfsense_event(
            cur,
            event_type="firewall_block",
            source_ip=source_ip,
            destination_ip="203.0.113.57",
            destination_port=445,
            seconds_ago=1,
        )
        second_result = backend_detection_engine._generate_pfsense_repeated_deny_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )

    assert len(first_result) == 1
    assert second_result == []

    cur.execute(
        """
        SELECT COUNT(*) FROM alerts
        WHERE source_ip = %s AND alert_type = 'pfsense_firewall_repeated_deny' AND status = 'open'
        """,
        (source_ip,),
    )
    assert cur.fetchone()[0] == 1


# ---------------------------------------------------------------------------
# Port scan
# ---------------------------------------------------------------------------


def test_port_scan_threshold_creates_alert_with_mitre_mapping(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.40"

    insert_pfsense_event(
        cur, event_type="firewall_block", source_ip=source_ip, destination_port=22, seconds_ago=2
    )
    insert_pfsense_event(
        cur, event_type="firewall_block", source_ip=source_ip, destination_port=3389, seconds_ago=1
    )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        alerts_created = backend_detection_engine._generate_pfsense_port_scan_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )

    assert len(alerts_created) == 1
    assert alerts_created[0]["severity"] == "medium"
    assert alerts_created[0]["response_action"] == "enrich_source_ip"

    alert = fetch_alert_by_type(cur, source_ip, "pfsense_firewall_port_scan")
    assert alert is not None
    _, alert_type, severity, response_action, _, context = alert
    assert context["distinct_port_count"] == 2

    mitre = enrich_alert_with_mitre({"alert_type": alert_type})
    assert mitre["mitre_technique_id"] == "T1046"
    assert mitre["mitre_technique_name"] == "Network Service Discovery"
    assert mitre["mitre_tactic"] == "Discovery"


def test_port_scan_same_destination_port_does_not_alert(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.41"

    insert_pfsense_event(
        cur, event_type="firewall_block", source_ip=source_ip, destination_port=443, seconds_ago=2
    )
    insert_pfsense_event(
        cur, event_type="firewall_block", source_ip=source_ip, destination_port=443, seconds_ago=1
    )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        result = backend_detection_engine._generate_pfsense_port_scan_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )

    assert result == []
    assert fetch_alert_by_type(cur, source_ip, "pfsense_firewall_port_scan") is None


def test_port_scan_breadth_escalates_to_high_severity(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.42"

    for port in (21, 22, 23, 25, 80, 443, 3389):
        insert_pfsense_event(
            cur, event_type="firewall_block", source_ip=source_ip, destination_port=port, seconds_ago=1
        )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        alerts_created = backend_detection_engine._generate_pfsense_port_scan_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )

    assert len(alerts_created) == 1
    assert alerts_created[0]["severity"] == "high"
    assert alerts_created[0]["response_action"] == "request_firewall_block_approval"


# ---------------------------------------------------------------------------
# Suspicious allow
# ---------------------------------------------------------------------------


def test_suspicious_allow_sensitive_port_inbound_creates_high_severity_alert(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.50"

    insert_pfsense_event(
        cur,
        event_type="firewall_allow",
        source_ip=source_ip,
        destination_port=3389,
        direction="in",
    )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        alerts_created = backend_detection_engine._generate_pfsense_suspicious_allow_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )

    assert len(alerts_created) == 1
    assert alerts_created[0]["severity"] == "high"
    assert alerts_created[0]["response_action"] == "request_firewall_block_approval"

    alert = fetch_alert_by_type(cur, source_ip, "pfsense_firewall_suspicious_allow")
    assert alert is not None
    _, alert_type, severity, response_action, _, context = alert
    assert context["destination_port"] == "3389"
    assert context["direction"] == "in"

    mitre = enrich_alert_with_mitre({"alert_type": alert_type})
    assert mitre["mitre_technique_id"] is None


def test_suspicious_allow_outbound_sensitive_port_does_not_alert(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.51"

    insert_pfsense_event(
        cur,
        event_type="firewall_allow",
        source_ip=source_ip,
        destination_port=22,
        direction="out",
    )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        result = backend_detection_engine._generate_pfsense_suspicious_allow_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )

    assert result == []
    assert fetch_alerts_for_ip(cur, source_ip) == []


def test_suspicious_allow_non_sensitive_port_inbound_does_not_alert(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.52"

    insert_pfsense_event(
        cur,
        event_type="firewall_allow",
        source_ip=source_ip,
        destination_port=8443,
        direction="in",
    )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        result = backend_detection_engine._generate_pfsense_suspicious_allow_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )

    assert result == []
    assert fetch_alerts_for_ip(cur, source_ip) == []


# ---------------------------------------------------------------------------
# Noisy source suppression
# ---------------------------------------------------------------------------


def test_noisy_source_suppression_creates_single_low_severity_rollup(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.60"

    # 20 routine block events to 20 distinct destinations on the same port keeps
    # every individual (destination, port, protocol) tuple under the repeated-deny
    # threshold (5) and keeps distinct destination ports at 1, under the port-scan
    # threshold (2), so only noisy-source volume logic should trigger.
    for index in range(20):
        insert_pfsense_event(
            cur,
            event_type="firewall_block",
            source_ip=source_ip,
            destination_ip=f"203.0.113.{index + 1}",
            destination_port=443,
            seconds_ago=20 - index,
        )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        assert backend_detection_engine._generate_pfsense_repeated_deny_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        ) == []
        assert backend_detection_engine._generate_pfsense_port_scan_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        ) == []
        alerts_created = backend_detection_engine._generate_pfsense_noisy_source_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )

    assert len(alerts_created) == 1
    assert alerts_created[0]["severity"] == "low"
    assert alerts_created[0]["response_action"] == "suppress_noisy_source"

    alert = fetch_alert_by_type(cur, source_ip, "pfsense_firewall_noisy_source")
    assert alert is not None
    _, alert_type, severity, response_action, _, context = alert
    assert context["event_count"] == 20
    assert context["suppressed"] is True

    mitre = enrich_alert_with_mitre({"alert_type": alert_type})
    assert mitre["mitre_technique_id"] is None


def test_noisy_source_does_not_duplicate_when_specific_alert_already_open(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.61"

    for port in (21, 22, 23, 25, 80, 443, 3389):
        insert_pfsense_event(
            cur, event_type="firewall_block", source_ip=source_ip, destination_port=port, seconds_ago=1
        )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        port_scan_alerts = backend_detection_engine._generate_pfsense_port_scan_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )
        noisy_alerts = backend_detection_engine._generate_pfsense_noisy_source_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )

    assert len(port_scan_alerts) == 1
    assert noisy_alerts == []
    assert fetch_alert_by_type(cur, source_ip, "pfsense_firewall_noisy_source") is None


def test_noisy_source_suppression_breaks_on_later_escalation(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.62"

    for index in range(20):
        insert_pfsense_event(
            cur,
            event_type="firewall_block",
            source_ip=source_ip,
            destination_ip=f"203.0.113.{index + 1}",
            destination_port=443,
            seconds_ago=20 - index,
        )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        noisy_alerts = backend_detection_engine._generate_pfsense_noisy_source_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )
        assert len(noisy_alerts) == 1

        # Escalate: introduce enough distinct ports to cross the port-scan threshold.
        for port in (21, 22, 23, 25, 80, 8080, 8443):
            insert_pfsense_event(
                cur, event_type="firewall_block", source_ip=source_ip, destination_port=port, seconds_ago=1
            )

        port_scan_alerts = backend_detection_engine._generate_pfsense_port_scan_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )

    assert len(port_scan_alerts) == 1
    assert fetch_alert_by_type(cur, source_ip, "pfsense_firewall_port_scan") is not None
    # The earlier noisy-source rollup remains open alongside the new escalation.
    assert fetch_alert_by_type(cur, source_ip, "pfsense_firewall_noisy_source") is not None


# ---------------------------------------------------------------------------
# Ingest dispatch wiring
# ---------------------------------------------------------------------------


def test_ingest_normalized_event_dispatches_firewall_block_detectors(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.70"

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        for seconds_ago in range(5, 0, -1):
            event = make_pfsense_event(
                event_type="firewall_block",
                source_ip=source_ip,
                destination_ip="203.0.113.99",
                destination_port=9090,
            )
            result = ingest_normalized_event(event, conn, cur)

    assert any(alert["response_action"] == "enrich_source_ip" for alert in result)

    cur.execute("SELECT COUNT(*) FROM events WHERE source_ip = %s AND source = 'pfsense'", (source_ip,))
    assert cur.fetchone()[0] == 5


def test_ingest_normalized_event_dispatches_firewall_allow_detectors(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.71"

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        event = make_pfsense_event(
            event_type="firewall_allow",
            source_ip=source_ip,
            destination_port=3389,
            direction="in",
        )
        result = ingest_normalized_event(event, conn, cur)

    assert len(result) == 1
    assert result[0]["response_action"] == "request_firewall_block_approval"


# ---------------------------------------------------------------------------
# Correlation integration
# ---------------------------------------------------------------------------


def test_pfsense_port_scan_correlates_with_other_source_activity(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.80"

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        for _ in range(3):
            ingest_normalized_event(
                {
                    "event_type": "failed_login",
                    "severity": "medium",
                    "source_ip": source_ip,
                    "source": "bank_app",
                    "source_type": "custom",
                    "event_timestamp": None,
                    "message": "Failed login attempt",
                    "app_name": "bank_app",
                    "environment": "test",
                    "raw_payload": {},
                },
                conn,
                cur,
            )

        result = ingest_normalized_event(
            make_pfsense_event(
                event_type="firewall_block",
                source_ip=source_ip,
                destination_port=22,
            ),
            conn,
            cur,
        )
        result.extend(
            ingest_normalized_event(
                make_pfsense_event(
                    event_type="firewall_block",
                    source_ip=source_ip,
                    destination_port=3389,
                ),
                conn,
                cur,
            )
        )

    alert_types = {alert.get("alert_type") for alert in result if alert.get("alert_type")}
    assert "correlated_activity" in alert_types


# ---------------------------------------------------------------------------
# Playbook matching and approval-gated execution
# ---------------------------------------------------------------------------


def test_pfsense_playbooks_match_expected_alert_severities(postgres_db):
    conn, cur = postgres_db
    seed_core_playbook_pack_v1(conn)
    source_ip = "198.51.100.90"

    for seconds_ago in range(5, 0, -1):
        insert_pfsense_event(
            cur,
            event_type="firewall_block",
            source_ip=source_ip,
            destination_ip="203.0.113.200",
            destination_port=443,
            seconds_ago=seconds_ago,
        )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        repeated_deny_alerts = backend_detection_engine._generate_pfsense_repeated_deny_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )
    repeated_deny_alert_id = repeated_deny_alerts[0]["alert_id"]
    conn.commit()

    matched = match_playbooks(conn, repeated_deny_alert_id)
    assert any(row["id"] == CORE_V1_PFSENSE_REPEATED_DENY_INVESTIGATION_ID for row in matched)


def test_pfsense_port_scan_containment_matches_only_high_severity(postgres_db):
    conn, cur = postgres_db
    seed_core_playbook_pack_v1(conn)
    source_ip = "198.51.100.91"

    for port in (21, 22, 23, 25, 80, 443, 3389):
        insert_pfsense_event(
            cur, event_type="firewall_block", source_ip=source_ip, destination_port=port, seconds_ago=1
        )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        alerts_created = backend_detection_engine._generate_pfsense_port_scan_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )
    assert alerts_created[0]["severity"] == "high"
    alert_id = alerts_created[0]["alert_id"]
    conn.commit()

    matched = {row["id"] for row in match_playbooks(conn, alert_id)}
    assert CORE_V1_PFSENSE_PORT_SCAN_CONTAINMENT_ID in matched
    assert CORE_V1_PFSENSE_PORT_SCAN_INVESTIGATION_ID in matched


def test_pfsense_suspicious_allow_containment_pauses_for_approval_then_blocks(postgres_db):
    conn, cur = postgres_db
    seed_core_playbook_pack_v1(conn)
    offender_ip = "198.51.100.92"

    insert_pfsense_event(
        cur,
        event_type="firewall_allow",
        source_ip=offender_ip,
        destination_port=3389,
        direction="in",
    )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        alerts_created = backend_detection_engine._generate_pfsense_suspicious_allow_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )
    alert_id = alerts_created[0]["alert_id"]
    conn.commit()

    eid = playbook_store.create_pending_playbook_execution_once(
        conn, CORE_V1_PFSENSE_SUSPICIOUS_ALLOW_CONTAINMENT_ID, alert_id
    )
    cur.execute(
        """
        INSERT INTO users (username, password_hash, role)
        VALUES ('pfsense-pack-approver', 'hash', 'analyst')
        RETURNING id
        """
    )
    user_id = cur.fetchone()[0]
    conn.commit()

    captured = {}

    def capture_adapter(adapter_name, adapter_action, **kwargs):
        if adapter_name == "firewall" and adapter_action == "block_ip":
            captured["params"] = kwargs.get("params")
        return {
            "adapter": adapter_name,
            "action": adapter_action,
            "mode": "simulation",
            "simulated": True,
            "executed": False,
            "success": True,
            "message": "ok",
            "params": kwargs.get("params") or {},
            "context": kwargs.get("context") or {},
            "metadata": {},
        }

    with patch(
        "engines.playbook_step_executor.execute_playbook_simulated_adapter",
        side_effect=capture_adapter,
    ):
        pause = playbook_step_executor.process_playbook_execution(conn, eid)
        assert pause["outcome"] == "awaiting_approval"

        approval_entry = next(
            entry
            for entry in playbook_store.get_playbook_execution(conn, eid)["steps_log"]
            if entry.get("action") == "require_approval"
        )
        approval_store.approve_request(conn, approval_entry["approval_request_id"], actor_user_id=user_id)
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    assert captured["params"]["source_ip"] == offender_ip


def test_pfsense_suspicious_allow_containment_denied_does_not_block(postgres_db):
    conn, cur = postgres_db
    seed_core_playbook_pack_v1(conn)
    offender_ip = "198.51.100.93"

    insert_pfsense_event(
        cur,
        event_type="firewall_allow",
        source_ip=offender_ip,
        destination_port=3389,
        direction="in",
    )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        alerts_created = backend_detection_engine._generate_pfsense_suspicious_allow_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )
    alert_id = alerts_created[0]["alert_id"]
    conn.commit()

    eid = playbook_store.create_pending_playbook_execution_once(
        conn, CORE_V1_PFSENSE_SUSPICIOUS_ALLOW_CONTAINMENT_ID, alert_id
    )
    cur.execute(
        """
        INSERT INTO users (username, password_hash, role)
        VALUES ('pfsense-pack-denier', 'hash', 'analyst')
        RETURNING id
        """
    )
    user_id = cur.fetchone()[0]
    conn.commit()

    def capture_adapter(adapter_name, adapter_action, **kwargs):
        return {
            "adapter": adapter_name,
            "action": adapter_action,
            "mode": "simulation",
            "simulated": True,
            "executed": False,
            "success": True,
            "message": "ok",
            "params": kwargs.get("params") or {},
            "context": kwargs.get("context") or {},
            "metadata": {},
        }

    with patch(
        "engines.playbook_step_executor.execute_playbook_simulated_adapter",
        side_effect=capture_adapter,
    ):
        pause = playbook_step_executor.process_playbook_execution(conn, eid)
        assert pause["outcome"] == "awaiting_approval"

        approval_entry = next(
            entry
            for entry in playbook_store.get_playbook_execution(conn, eid)["steps_log"]
            if entry.get("action") == "require_approval"
        )
        approval_store.deny_request(conn, approval_entry["approval_request_id"], actor_user_id=user_id)
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    row = playbook_store.get_playbook_execution(conn, eid)
    block_entries = [entry for entry in row["steps_log"] if entry["action"] == "block_ip"]
    assert len(block_entries) == 1
    assert block_entries[0]["status"] == "skipped"
    assert block_entries[0]["event"] == "skipped_after_approval_gate"
    assert "params" not in block_entries[0].get("output", {})
