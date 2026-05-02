from unittest.mock import patch

import siem_backend


REPUTATION = {
    "reputation_score": 65,
    "reputation_label": "medium-risk",
    "reputation_source": "test-reputation",
    "reputation_summary": "Deterministic test reputation",
}


def insert_open_alert(
    cur,
    *,
    source_ip="198.51.100.122",
    alert_type="http_error_threshold",
    source="nginx",
    source_type="web_log",
    seconds_ago=1,
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


def fetch_targeted_alert(cur, source_ip, alert_type):
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
          AND alert_type = %s
        ORDER BY id
        """,
        (source_ip, alert_type),
    )
    return cur.fetchone()


def assert_response_action_link(cur, source_ip, alert_type):
    cur.execute(
        """
        SELECT
            a.id,
            a.response_action,
            a.response_status,
            r.alert_id,
            host(r.source_ip),
            r.action,
            r.status,
            r.details
        FROM alerts a
        JOIN response_actions_log r ON r.alert_id = a.id
        WHERE a.source_ip = %s
          AND a.alert_type = %s
        """,
        (source_ip, alert_type),
    )
    row = cur.fetchone()

    assert row is not None
    assert row[0] == row[3]
    assert row[1] == "flag_high_priority"
    assert row[2] == "executed"
    assert row[4] == source_ip
    assert row[5] == "flag_high_priority"
    assert row[6] == "executed"
    assert row[7] == "Simulated escalation to SOC"


def test_targeted_correlation_web_to_app_attack_pattern(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.122"

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
        alert_type="http_error_threshold",
        source="nginx",
        source_type="web_log",
        seconds_ago=1,
        country="United States",
        city="New York",
    )

    with siem_backend.app.app_context(), patch("backend_correlation_engine.lookup_ip_reputation", return_value=REPUTATION):
        siem_backend.generate_targeted_correlation_alerts(cur, conn, source_ip)

    alert = fetch_targeted_alert(cur, source_ip, "web_to_app_attack_pattern")
    assert alert is not None
    assert alert[1] == "web_to_app_attack_pattern"
    assert alert[2] == "critical"
    assert alert[3] == source_ip
    assert alert[4] == "nginx"
    assert alert[5] == "web_log"
    assert alert[6] == f"Web-to-app attack pattern detected from {source_ip}"
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
    assert_response_action_link(cur, source_ip, "web_to_app_attack_pattern")


def test_targeted_correlation_spray_then_success_pattern(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.123"

    insert_open_alert(
        cur,
        source_ip=source_ip,
        alert_type="password_spraying_threshold",
        source="bank_app",
        source_type="custom",
        seconds_ago=3,
    )
    insert_open_alert(
        cur,
        source_ip=source_ip,
        alert_type="successful_login_after_spray",
        source="bank_app",
        source_type="custom",
        seconds_ago=1,
    )

    with siem_backend.app.app_context(), patch("backend_correlation_engine.lookup_ip_reputation", return_value=REPUTATION):
        siem_backend.generate_targeted_correlation_alerts(cur, conn, source_ip)

    alert = fetch_targeted_alert(cur, source_ip, "spray_then_success_pattern")
    assert alert is not None
    assert alert[1] == "spray_then_success_pattern"
    assert alert[2] == "critical"
    assert alert[3] == source_ip
    assert alert[4] == "bank_app"
    assert alert[5] == "custom"
    assert alert[6] == f"Password spray followed by successful login from {source_ip}"
    assert alert[8] == "flag_high_priority"
    assert alert[9] == "executed"
    assert_response_action_link(cur, source_ip, "spray_then_success_pattern")


def test_targeted_correlation_cloud_app_error_pattern(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.124"

    insert_open_alert(
        cur,
        source_ip=source_ip,
        alert_type="application_exception_threshold",
        source="azure_insights",
        source_type="cloud_api",
        seconds_ago=3,
        country="Canada",
        city="Toronto",
    )
    insert_open_alert(
        cur,
        source_ip=source_ip,
        alert_type="high_request_rate_threshold",
        source="nginx",
        source_type="web_log",
        seconds_ago=1,
        country="United States",
        city="New York",
    )

    with siem_backend.app.app_context(), patch("backend_correlation_engine.lookup_ip_reputation", return_value=REPUTATION):
        siem_backend.generate_targeted_correlation_alerts(cur, conn, source_ip)

    alert = fetch_targeted_alert(cur, source_ip, "cloud_app_error_pattern")
    assert alert is not None
    assert alert[1] == "cloud_app_error_pattern"
    assert alert[2] == "high"
    assert alert[3] == source_ip
    assert alert[4] == "nginx"
    assert alert[5] == "web_log"
    assert alert[6] == f"Cloud and web application errors correlated from {source_ip}"
    assert alert[8] == "flag_high_priority"
    assert alert[9] == "executed"
    assert alert[10] == "United States"
    assert alert[11] == "New York"
    assert_response_action_link(cur, source_ip, "cloud_app_error_pattern")


def test_targeted_correlation_duplicate_suppression_keeps_single_open_alert(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.125"

    insert_open_alert(
        cur,
        source_ip=source_ip,
        alert_type="failed_login_threshold",
        source="bank_app",
        source_type="custom",
        seconds_ago=3,
    )
    insert_open_alert(
        cur,
        source_ip=source_ip,
        alert_type="http_error_threshold",
        source="nginx",
        source_type="web_log",
        seconds_ago=1,
    )

    with siem_backend.app.app_context(), patch("backend_correlation_engine.lookup_ip_reputation", return_value=REPUTATION):
        siem_backend.generate_targeted_correlation_alerts(cur, conn, source_ip)
        siem_backend.generate_targeted_correlation_alerts(cur, conn, source_ip)

    cur.execute(
        """
        SELECT COUNT(*)
        FROM alerts
        WHERE source_ip = %s
          AND alert_type = 'web_to_app_attack_pattern'
          AND status = 'open'
        """,
        (source_ip,),
    )
    assert cur.fetchone()[0] == 1
