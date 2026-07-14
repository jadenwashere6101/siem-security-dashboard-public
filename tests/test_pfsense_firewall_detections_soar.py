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


def assert_target_context_mode(context, expected_mode):
    assert "target_context" in context
    assert context["target_context"]["mode"] == expected_mode


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
    assert alerts_created[0]["severity"] == "low"
    assert alerts_created[0]["response_action"] == "monitor_only"

    alert = fetch_alert_by_type(cur, source_ip, "pfsense_firewall_repeated_deny")
    assert alert is not None
    _, alert_type, severity, response_action, response_status, context = alert
    assert severity == "low"
    assert response_action == "monitor_only"
    assert response_status == "pending"
    assert context["destination_ip"] == "203.0.113.55"
    assert context["destination_port"] == "8080"
    assert context["protocol"] == "tcp"
    assert context["event_count"] == 5
    assert context["first_seen"] is not None
    assert context["last_seen"] is not None
    assert_target_context_mode(context, "single_target")
    assert context["target_context"]["destination_ip"] == "203.0.113.55"
    assert context["target_context"]["destination_port"] == "8080"
    assert context["target_context"]["firewall_action"] == "block"
    assert context["target_context"]["attempts"] == 5

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
    assert alerts_created[0]["response_action"] == "block_ip"


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


def test_repeated_deny_outbound_direction_escalates_at_base_threshold(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.35"

    # Outbound (LAN->WAN) denies escalate at the base threshold rather than
    # requiring the multiplier-scaled count inbound denies need, since a host
    # repeatedly denied reaching external destinations is a stronger signal.
    for seconds_ago in range(5, 0, -1):
        insert_pfsense_event(
            cur,
            event_type="firewall_block",
            source_ip=source_ip,
            destination_ip="203.0.113.60",
            destination_port=443,
            direction="out",
            seconds_ago=seconds_ago,
        )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        alerts_created = backend_detection_engine._generate_pfsense_repeated_deny_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )

    assert len(alerts_created) == 1
    assert alerts_created[0]["severity"] == "high"
    assert alerts_created[0]["response_action"] == "block_ip"

    alert = fetch_alert_by_type(cur, source_ip, "pfsense_firewall_repeated_deny")
    assert alert is not None
    _, _, _, _, _, context = alert
    assert context["direction"] == "out"


def test_repeated_deny_inbound_direction_stays_low_at_base_threshold(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.36"

    # Same count, same threshold, but inbound (direction="in", the fixture
    # default) now stays low for routine WAN deny noise at the base threshold.
    for seconds_ago in range(5, 0, -1):
        insert_pfsense_event(
            cur,
            event_type="firewall_block",
            source_ip=source_ip,
            destination_ip="203.0.113.61",
            destination_port=443,
            seconds_ago=seconds_ago,
        )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        alerts_created = backend_detection_engine._generate_pfsense_repeated_deny_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )

    assert len(alerts_created) == 1
    assert alerts_created[0]["severity"] == "low"
    assert alerts_created[0]["response_action"] == "monitor_only"


def test_repeated_deny_cooldown_suppresses_equal_severity_recurrence_after_close(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.37"

    for seconds_ago in range(5, 0, -1):
        insert_pfsense_event(
            cur,
            event_type="firewall_block",
            source_ip=source_ip,
            destination_ip="203.0.113.62",
            destination_port=445,
            seconds_ago=seconds_ago,
        )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        first = backend_detection_engine._generate_pfsense_repeated_deny_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )
    assert len(first) == 1
    alert_id = first[0]["alert_id"]

    cur.execute("UPDATE alerts SET status = 'resolved' WHERE id = %s", (alert_id,))
    cur.execute(
        "INSERT INTO audit_log (event_type, target_alert_id, details) VALUES (%s, %s, %s)",
        ("UPDATE_ALERT_STATUS", alert_id, Json({"status": "resolved"})),
    )
    conn.commit()

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        second = backend_detection_engine._generate_pfsense_repeated_deny_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )

    assert second == []


def test_repeated_deny_escalation_breaks_cooldown_suppression(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.38"

    for seconds_ago in range(5, 0, -1):
        insert_pfsense_event(
            cur,
            event_type="firewall_block",
            source_ip=source_ip,
            destination_ip="203.0.113.63",
            destination_port=445,
            seconds_ago=seconds_ago,
        )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        first = backend_detection_engine._generate_pfsense_repeated_deny_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )
    assert first[0]["severity"] == "low"
    alert_id = first[0]["alert_id"]

    cur.execute("UPDATE alerts SET status = 'resolved' WHERE id = %s", (alert_id,))
    cur.execute(
        "INSERT INTO audit_log (event_type, target_alert_id, details) VALUES (%s, %s, %s)",
        ("UPDATE_ALERT_STATUS", alert_id, Json({"status": "resolved"})),
    )
    conn.commit()

    # Same source now carries known-bad reputation, so the new candidate computes
    # "high" — strictly above the closed alert's "medium" — and must break through
    # the cooldown rather than being suppressed.
    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_HIGH
    ):
        second = backend_detection_engine._generate_pfsense_repeated_deny_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )

    assert len(second) == 1
    assert second[0]["severity"] == "high"


def test_repeated_deny_inbound_sustained_volume_reaches_medium_before_high(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.38"

    for seconds_ago in range(15, 0, -1):
        insert_pfsense_event(
            cur,
            event_type="firewall_block",
            source_ip=source_ip,
            destination_ip="203.0.113.62",
            destination_port=8080,
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
    assert context["event_count"] == 2
    assert_target_context_mode(context, "aggregate_targets")
    assert context["target_context"]["top_destination_ip"] == "203.0.113.10"
    assert context["target_context"]["top_destination_port"] == 22
    assert context["target_context"]["attempts"] == 2

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
    assert alerts_created[0]["response_action"] == "block_ip"


def test_port_scan_host_breadth_sweep_triggers_alert_with_few_ports(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.43"

    # Only 1 distinct destination port (below the port-count threshold of 2) but
    # 5 distinct destination hosts (>= host_threshold), i.e. a horizontal sweep on
    # one port across many hosts rather than a port scan on one host.
    for index in range(5):
        insert_pfsense_event(
            cur,
            event_type="firewall_block",
            source_ip=source_ip,
            destination_ip=f"203.0.113.{120 + index}",
            destination_port=443,
            seconds_ago=5 - index,
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
    _, _, _, _, _, context = alert
    assert context["distinct_port_count"] == 1
    assert context["distinct_destination_count"] == 5
    assert_target_context_mode(context, "aggregate_targets")
    assert context["target_context"]["top_destination_port"] == 443
    assert context["target_context"]["distinct_destination_count"] == 5


# ---------------------------------------------------------------------------
# Suspicious allow
# ---------------------------------------------------------------------------


def test_suspicious_allow_single_uncorroborated_event_is_medium_severity(postgres_db):
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
    assert alerts_created[0]["severity"] == "medium"
    assert alerts_created[0]["response_action"] == "enrich_source_ip"

    alert = fetch_alert_by_type(cur, source_ip, "pfsense_firewall_suspicious_allow")
    assert alert is not None
    _, alert_type, severity, response_action, _, context = alert
    assert severity == "medium"
    assert response_action == "enrich_source_ip"
    assert context["destination_port"] == "3389"
    assert context["direction"] == "in"
    assert context["distinct_sensitive_port_count"] == 1
    assert_target_context_mode(context, "single_target")
    assert context["target_context"]["destination_ip"] == "203.0.113.10"
    assert context["target_context"]["destination_port"] == "3389"
    assert context["target_context"]["firewall_action"] == "pass"

    mitre = enrich_alert_with_mitre({"alert_type": alert_type})
    assert mitre["mitre_technique_id"] is None


def test_suspicious_allow_high_reputation_single_event_creates_high_severity_alert(postgres_db):
    conn, cur = postgres_db
    seed_core_playbook_pack_v1(conn)
    source_ip = "198.51.100.150"

    insert_pfsense_event(
        cur,
        event_type="firewall_allow",
        source_ip=source_ip,
        destination_port=3389,
        direction="in",
    )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_HIGH
    ):
        alerts_created = backend_detection_engine._generate_pfsense_suspicious_allow_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )

    assert len(alerts_created) == 1
    assert alerts_created[0]["severity"] == "high"
    assert alerts_created[0]["response_action"] == "block_ip"

    alert = fetch_alert_by_type(cur, source_ip, "pfsense_firewall_suspicious_allow")
    assert alert is not None
    _, alert_type, severity, response_action, _, context = alert
    assert response_action == "block_ip"
    assert context["destination_port"] == "3389"
    assert context["direction"] == "in"

    mitre = enrich_alert_with_mitre({"alert_type": alert_type})
    assert mitre["mitre_technique_id"] is None

    conn.commit()
    matches = match_playbooks(conn, alerts_created[0]["alert_id"])
    assert any(
        match["id"] == CORE_V1_PFSENSE_SUSPICIOUS_ALLOW_CONTAINMENT_ID
        for match in matches
    )


def test_suspicious_allow_repeated_events_escalate_to_high_severity(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.151"

    # 3 qualifying events (>= the high-confidence repeat threshold) accumulated
    # before the detector's first pass, corroborating via repetition alone.
    for seconds_ago in range(3, 0, -1):
        insert_pfsense_event(
            cur,
            event_type="firewall_allow",
            source_ip=source_ip,
            destination_port=3389,
            direction="in",
            seconds_ago=seconds_ago,
        )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        alerts_created = backend_detection_engine._generate_pfsense_suspicious_allow_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )

    assert len(alerts_created) == 1
    assert alerts_created[0]["severity"] == "high"
    assert alerts_created[0]["response_action"] == "block_ip"


def test_suspicious_allow_distinct_sensitive_ports_escalate_to_high_severity(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.152"

    # 2 distinct sensitive ports touched (>= the distinct-port escalation
    # threshold), a single event each — corroborating via port diversity rather
    # than repetition or reputation.
    insert_pfsense_event(
        cur, event_type="firewall_allow", source_ip=source_ip, destination_port=3389,
        direction="in", seconds_ago=2,
    )
    insert_pfsense_event(
        cur, event_type="firewall_allow", source_ip=source_ip, destination_port=22,
        direction="in", seconds_ago=1,
    )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        alerts_created = backend_detection_engine._generate_pfsense_suspicious_allow_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )

    assert len(alerts_created) == 1
    assert alerts_created[0]["severity"] == "high"
    assert alerts_created[0]["response_action"] == "block_ip"

    alert = fetch_alert_by_type(cur, source_ip, "pfsense_firewall_suspicious_allow")
    assert alert is not None
    _, _, _, _, _, context = alert
    assert context["distinct_sensitive_port_count"] == 2


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

    # 24 routine block events split across 2 destination hosts and 3 protocols
    # (4 events per host/protocol tuple) keeps every individual
    # (destination, port, protocol) tuple under the repeated-deny threshold (5),
    # keeps distinct destination ports at 1 (under the port-scan port threshold
    # of 2) and distinct destination hosts at 2 (under the port-scan host
    # threshold of 5), so only noisy-source volume logic should trigger.
    seconds_ago = 24
    for destination_ip in ("203.0.113.1", "203.0.113.2"):
        for protocol in ("tcp", "udp", "icmp"):
            for _ in range(4):
                insert_pfsense_event(
                    cur,
                    event_type="firewall_block",
                    source_ip=source_ip,
                    destination_ip=destination_ip,
                    destination_port=443,
                    protocol=protocol,
                    seconds_ago=seconds_ago,
                )
                seconds_ago -= 1

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
    assert context["event_count"] == 24
    assert context["suppressed"] is True
    assert_target_context_mode(context, "aggregate_targets")
    assert context["target_context"]["top_destination_port"] == "443"
    assert context["target_context"]["distinct_destination_count"] == 2
    assert context["target_context"]["distinct_port_count"] == 1
    assert context["target_context"]["firewall_action"] == "block"

    mitre = enrich_alert_with_mitre({"alert_type": alert_type})
    assert mitre["mitre_technique_id"] is None


def test_port_scan_target_context_uses_most_frequent_destination_and_port(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.44"

    insert_pfsense_event(
        cur, event_type="firewall_block", source_ip=source_ip, destination_ip="203.0.113.20",
        destination_port=22, seconds_ago=4,
    )
    insert_pfsense_event(
        cur, event_type="firewall_block", source_ip=source_ip, destination_ip="203.0.113.20",
        destination_port=22, seconds_ago=3,
    )
    insert_pfsense_event(
        cur, event_type="firewall_block", source_ip=source_ip, destination_ip="203.0.113.21",
        destination_port=22, seconds_ago=2,
    )
    insert_pfsense_event(
        cur, event_type="firewall_block", source_ip=source_ip, destination_ip="203.0.113.22",
        destination_port=3389, seconds_ago=1,
    )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        alerts_created = backend_detection_engine._generate_pfsense_port_scan_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )

    assert len(alerts_created) == 1
    alert = fetch_alert_by_type(cur, source_ip, "pfsense_firewall_port_scan")
    context = alert[5]
    assert context["target_context"]["top_destination_ip"] == "203.0.113.20"
    assert context["target_context"]["top_destination_port"] == 22
    assert context["target_context"]["attempts"] == 4


def test_noisy_source_target_context_uses_most_frequent_target_and_mixed_action(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.63"

    seconds_ago = 24
    for destination_ip in ("203.0.113.80", "203.0.113.82"):
        for protocol in ("tcp", "udp", "icmp"):
            for _ in range(4):
                insert_pfsense_event(
                    cur,
                    event_type="firewall_block",
                    source_ip=source_ip,
                    destination_ip=destination_ip,
                    destination_port=443,
                    protocol=protocol,
                    seconds_ago=seconds_ago,
                )
                seconds_ago -= 1
    for _ in range(12):
        insert_pfsense_event(
            cur,
            event_type="firewall_allow",
            source_ip=source_ip,
            destination_ip="203.0.113.81",
            destination_port=8443,
            direction="out",
            seconds_ago=seconds_ago,
        )
        seconds_ago -= 1

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_LOW
    ):
        alerts_created = backend_detection_engine._generate_pfsense_noisy_source_alerts_core(
            cur, conn, source="pfsense", source_type="firewall"
        )

    assert len(alerts_created) == 1
    alert = fetch_alert_by_type(cur, source_ip, "pfsense_firewall_noisy_source")
    context = alert[5]
    assert context["target_context"]["top_destination_ip"] == "203.0.113.80"
    assert context["target_context"]["top_destination_port"] == "443"
    assert context["target_context"]["firewall_action"] == "mixed"
    assert context["target_context"]["attempts"] == 36


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

    assert any(alert["response_action"] == "monitor_only" for alert in result)

    cur.execute("SELECT COUNT(*) FROM events WHERE source_ip = %s AND source = 'pfsense'", (source_ip,))
    assert cur.fetchone()[0] == 5


def test_ingest_normalized_event_dispatches_firewall_allow_detectors(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.71"

    # High reputation corroborates a single event so the dispatch wiring is
    # exercised on the "high severity -> block_ip" path.
    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION_HIGH
    ):
        event = make_pfsense_event(
            event_type="firewall_allow",
            source_ip=source_ip,
            destination_port=3389,
            direction="in",
        )
        result = ingest_normalized_event(event, conn, cur)

    assert len(result) == 1
    assert result[0]["response_action"] == "block_ip"


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
    assert matched == []


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
