from unittest.mock import patch

import pytest

import siem_backend
import engines.correlation_engine as backend_correlation_engine
from engines.detection_config import CORRELATION_WINDOW_MINUTES
from helpers import enrichment_helpers
REPUTATION = {
    "reputation_score": 65,
    "reputation_label": "medium-risk",
    "reputation_source": "test-reputation",
    "reputation_summary": "Deterministic test reputation",
}


def insert_open_alert(
    cur,
    *,
    source_ip="198.51.100.112",
    alert_type="failed_login_threshold",
    source="bank_app",
    source_type="custom",
    seconds_ago=2,
    country="United States",
    city="New York",
    lat=40.7128,
    lon=-74.0060,
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
            status,
            country,
            city,
            latitude,
            longitude,
            response_action,
            response_status,
            created_at
        )
        VALUES (
            %s,
            'high',
            %s,
            %s,
            %s,
            %s,
            'open',
            %s,
            %s,
            %s,
            %s,
            'monitor',
            'executed',
            NOW() - (%s * INTERVAL '1 second')
        )
        """,
        (
            alert_type,
            source_ip,
            source,
            source_type,
            f"{alert_type} prerequisite alert",
            country,
            city,
            lat,
            lon,
            seconds_ago,
        ),
    )


def fetch_correlated_alert(cur, source_ip):
    cur.execute(
        """
        SELECT
            id,
            alert_type,
            severity,
            host(source_ip),
            source,
            source_type,
            message,
            status,
            response_action,
            response_status,
            country,
            city,
            latitude,
            longitude,
            reputation_score,
            reputation_label,
            reputation_source,
            reputation_summary,
            context
        FROM alerts
        WHERE source_ip = %s
          AND alert_type = 'correlated_activity'
        ORDER BY id
        """,
        (source_ip,),
    )
    return cur.fetchone()


def fetch_open_prerequisite_alerts(cur, source_ip):
    cur.execute(
        """
        SELECT id, alert_type, source, source_type
        FROM alerts
        WHERE source_ip = %s
          AND status = 'open'
          AND alert_type IN (
              'failed_login_threshold',
              'port_scan_threshold'
          )
        ORDER BY created_at DESC
        """,
        (source_ip,),
    )
    return cur.fetchall()


def assert_no_response_action_link(cur, source_ip, alert_type):
    cur.execute(
        """
        SELECT COUNT(*)
        FROM alerts a
        JOIN response_actions_log r ON r.alert_id = a.id
        WHERE a.source_ip = %s
          AND a.alert_type = %s
        """,
        (source_ip, alert_type),
    )
    assert cur.fetchone()[0] == 0


def test_correlated_activity_fires_with_two_qualifying_open_alerts(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.112"

    insert_open_alert(
        cur,
        source_ip=source_ip,
        alert_type="failed_login_threshold",
        source="bank_app",
        source_type="custom",
        seconds_ago=3,
        country="Canada",
        city="Toronto",
    )
    insert_open_alert(
        cur,
        source_ip=source_ip,
        alert_type="port_scan_threshold",
        source="nginx",
        source_type="web_log",
        seconds_ago=1,
        country="United States",
        city="New York",
    )

    with siem_backend.app.app_context(), patch("engines.correlation_engine.lookup_ip_reputation", return_value=REPUTATION):
        alerts_created = backend_correlation_engine.generate_correlated_activity_alerts(cur, conn, source_ip)

    alert = fetch_correlated_alert(cur, source_ip)
    assert alert is not None
    assert alerts_created == [
        {
            "alert_id": alert[0],
            "source_ip": source_ip,
            "response_action": "flag_high_priority",
            "severity": "high",
            "alert_type": "correlated_activity",
            "source": "nginx",
            "source_type": "web_log",
        }
    ]
    assert alert[1] == "correlated_activity"
    assert alert[2] == "high"
    assert alert[3] == source_ip
    assert alert[4] == "nginx"
    assert alert[5] == "web_log"
    assert alert[6] == (
        f"Multi-source suspicious activity detected from {source_ip} "
        "involving: port_scan_threshold, failed_login_threshold"
    )
    assert "involving:" in alert[6]
    assert alert[7] == "open"
    assert alert[8] == "flag_high_priority"
    assert alert[9] == "pending"
    assert alert[10] == "United States"
    assert alert[11] == "New York"
    assert float(alert[12]) == pytest.approx(40.7128)
    assert float(alert[13]) == pytest.approx(-74.0060)
    assert alert[14] == 65
    assert alert[15] == "medium-risk"
    assert alert[16] == "test-reputation"
    assert alert[17] == "Deterministic test reputation"
    prerequisites = fetch_open_prerequisite_alerts(cur, source_ip)
    context = alert[18]
    assert context["correlation_type"] == "correlated_activity"
    assert context["matched_rule_id"] == "correlated_activity"
    assert context["matched_window_minutes"] == CORRELATION_WINDOW_MINUTES
    assert context["matched_alert_count"] == 2
    assert context["contributing_alert_ids"] == [row[0] for row in prerequisites]
    assert context["contributing_alert_types"] == ["port_scan_threshold", "failed_login_threshold"]
    assert context["contributing_sources"] == ["nginx", "bank_app"]
    assert context["contributing_source_types"] == ["web_log", "custom"]
    assert "raw_payload" not in context
    assert_no_response_action_link(cur, source_ip, "correlated_activity")


def test_correlated_activity_requires_different_alert_types(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.113"

    insert_open_alert(cur, source_ip=source_ip, alert_type="failed_login_threshold", source="bank_app", seconds_ago=2)
    insert_open_alert(cur, source_ip=source_ip, alert_type="failed_login_threshold", source="nginx", seconds_ago=1)

    with siem_backend.app.app_context(), patch("engines.correlation_engine.lookup_ip_reputation", return_value=REPUTATION):
        assert backend_correlation_engine.generate_correlated_activity_alerts(cur, conn, source_ip) == []

    assert fetch_correlated_alert(cur, source_ip) is None


def test_correlated_activity_requires_distinct_non_unknown_sources(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.114"

    insert_open_alert(cur, source_ip=source_ip, alert_type="failed_login_threshold", source="bank_app", seconds_ago=2)
    insert_open_alert(cur, source_ip=source_ip, alert_type="port_scan_threshold", source="unknown", seconds_ago=1)

    with siem_backend.app.app_context(), patch("engines.correlation_engine.lookup_ip_reputation", return_value=REPUTATION):
        assert backend_correlation_engine.generate_correlated_activity_alerts(cur, conn, source_ip) == []

    assert fetch_correlated_alert(cur, source_ip) is None


def test_correlated_activity_duplicate_suppression_keeps_single_open_alert(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.115"

    insert_open_alert(cur, source_ip=source_ip, alert_type="failed_login_threshold", source="bank_app", seconds_ago=2)
    insert_open_alert(cur, source_ip=source_ip, alert_type="port_scan_threshold", source="nginx", seconds_ago=1)

    with siem_backend.app.app_context(), patch("engines.correlation_engine.lookup_ip_reputation", return_value=REPUTATION):
        assert len(backend_correlation_engine.generate_correlated_activity_alerts(cur, conn, source_ip)) == 1
        assert backend_correlation_engine.generate_correlated_activity_alerts(cur, conn, source_ip) == []

    cur.execute(
        """
        SELECT COUNT(*)
        FROM alerts
        WHERE source_ip = %s
          AND alert_type = 'correlated_activity'
          AND status = 'open'
        """,
        (source_ip,),
    )
    assert cur.fetchone()[0] == 1


def test_enrich_alert_with_correlation_context_parses_involving_message():
    alert = {
        "alert_type": "correlated_activity",
        "message": (
            "Multi-source suspicious activity detected from 198.51.100.116 "
            "involving: port_scan_threshold, failed_login_threshold"
        ),
        "context": {},
    }

    enriched = enrichment_helpers.enrich_alert_with_correlation_context(alert)

    assert enriched["is_correlation_alert"] is True
    assert enriched["correlated_alert_types"] == [
        "port_scan_threshold",
        "failed_login_threshold",
    ]
    assert enriched["correlated_alert_count"] == 2
    assert "correlation_context" not in enriched


def test_enrich_alert_with_correlation_context_prefers_structured_context():
    alert = {
        "alert_type": "correlated_activity",
        "message": "Multi-source suspicious activity detected involving: legacy_type",
        "context": {
            "correlation_type": "correlated_activity",
            "matched_rule_id": "correlated_activity",
            "matched_window_minutes": 10,
            "matched_alert_count": 2,
            "contributing_alert_types": ["port_scan_threshold", "failed_login_threshold"],
            "contributing_alert_ids": [11, 12],
            "contributing_sources": ["nginx", "bank_app"],
            "contributing_source_types": ["web_log", "custom"],
        },
    }

    enriched = enrichment_helpers.enrich_alert_with_correlation_context(alert)

    assert enriched["is_correlation_alert"] is True
    assert enriched["correlated_alert_types"] == ["port_scan_threshold", "failed_login_threshold"]
    assert enriched["correlated_alert_count"] == 2
    assert enriched["correlation_context"]["matched_rule_id"] == "correlated_activity"
    assert enriched["correlation_context"]["contributing_alert_ids"] == [11, 12]


def test_enrich_alert_with_correlation_context_ignores_malformed_context():
    alert = {
        "alert_type": "correlated_activity",
        "message": (
            "Multi-source suspicious activity detected from 198.51.100.116 "
            "involving: port_scan_threshold"
        ),
        "context": {"contributing_alert_types": "not-a-list"},
    }

    enriched = enrichment_helpers.enrich_alert_with_correlation_context(alert)

    assert enriched["is_correlation_alert"] is True
    assert enriched["correlated_alert_types"] == ["port_scan_threshold"]


def test_non_correlation_alert_with_empty_context_has_no_correlation_fields():
    alert = {
        "alert_type": "failed_login_threshold",
        "message": "Failed login threshold exceeded",
        "context": {},
    }

    enriched = enrichment_helpers.enrich_alert_with_correlation_context(alert)

    assert "is_correlation_alert" not in enriched
    assert "correlated_alert_types" not in enriched
    assert "correlation_context" not in enriched


def test_alerts_context_defaults_to_empty_object(postgres_db):
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
            status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING context
        """,
        (
            "failed_login_threshold",
            "high",
            "198.51.100.117",
            "bank_app",
            "custom",
            "Detection alert without explicit context",
            "open",
        ),
    )
    assert cur.fetchone()[0] == {}
