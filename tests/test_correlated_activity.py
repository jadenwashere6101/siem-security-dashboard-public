from unittest.mock import patch

import siem_backend
import backend_correlation_engine
import backend_enrichment_helpers


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
            reputation_summary
        FROM alerts
        WHERE source_ip = %s
          AND alert_type = 'correlated_activity'
        ORDER BY id
        """,
        (source_ip,),
    )
    return cur.fetchone()


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

    with siem_backend.app.app_context(), patch("backend_correlation_engine.lookup_ip_reputation", return_value=REPUTATION):
        assert backend_correlation_engine.generate_correlated_activity_alerts(cur, conn, source_ip) is True

    alert = fetch_correlated_alert(cur, source_ip)
    assert alert is not None
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
    assert alert[9] == "executed"
    assert alert[10] == "United States"
    assert alert[11] == "New York"
    assert float(alert[12]) == 40.7128
    assert float(alert[13]) == -74.0060
    assert alert[14] == 65
    assert alert[15] == "medium-risk"
    assert alert[16] == "test-reputation"
    assert alert[17] == "Deterministic test reputation"

    cur.execute(
        """
        SELECT
            a.id,
            r.alert_id,
            host(r.source_ip),
            r.action,
            r.status,
            r.details
        FROM alerts a
        JOIN response_actions_log r ON r.alert_id = a.id
        WHERE a.source_ip = %s
          AND a.alert_type = 'correlated_activity'
        """,
        (source_ip,),
    )
    response_row = cur.fetchone()
    assert response_row is not None
    assert response_row[0] == response_row[1]
    assert response_row[2] == source_ip
    assert response_row[3] == "flag_high_priority"
    assert response_row[4] == "executed"
    assert response_row[5] == "Simulated escalation to SOC"


def test_correlated_activity_requires_different_alert_types(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.113"

    insert_open_alert(cur, source_ip=source_ip, alert_type="failed_login_threshold", source="bank_app", seconds_ago=2)
    insert_open_alert(cur, source_ip=source_ip, alert_type="failed_login_threshold", source="nginx", seconds_ago=1)

    with siem_backend.app.app_context(), patch("backend_correlation_engine.lookup_ip_reputation", return_value=REPUTATION):
        assert backend_correlation_engine.generate_correlated_activity_alerts(cur, conn, source_ip) is False

    assert fetch_correlated_alert(cur, source_ip) is None


def test_correlated_activity_requires_distinct_non_unknown_sources(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.114"

    insert_open_alert(cur, source_ip=source_ip, alert_type="failed_login_threshold", source="bank_app", seconds_ago=2)
    insert_open_alert(cur, source_ip=source_ip, alert_type="port_scan_threshold", source="unknown", seconds_ago=1)

    with siem_backend.app.app_context(), patch("backend_correlation_engine.lookup_ip_reputation", return_value=REPUTATION):
        assert backend_correlation_engine.generate_correlated_activity_alerts(cur, conn, source_ip) is False

    assert fetch_correlated_alert(cur, source_ip) is None


def test_correlated_activity_duplicate_suppression_keeps_single_open_alert(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.115"

    insert_open_alert(cur, source_ip=source_ip, alert_type="failed_login_threshold", source="bank_app", seconds_ago=2)
    insert_open_alert(cur, source_ip=source_ip, alert_type="port_scan_threshold", source="nginx", seconds_ago=1)

    with siem_backend.app.app_context(), patch("backend_correlation_engine.lookup_ip_reputation", return_value=REPUTATION):
        assert backend_correlation_engine.generate_correlated_activity_alerts(cur, conn, source_ip) is True
        assert backend_correlation_engine.generate_correlated_activity_alerts(cur, conn, source_ip) is False

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
    }

    enriched = backend_enrichment_helpers.enrich_alert_with_correlation_context(alert)

    assert enriched["is_correlation_alert"] is True
    assert enriched["correlated_alert_types"] == [
        "port_scan_threshold",
        "failed_login_threshold",
    ]
    assert enriched["correlated_alert_count"] == 2
