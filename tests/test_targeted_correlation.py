from unittest.mock import patch

import siem_backend
import engines.correlation_engine as backend_correlation_engine
from core.core_playbook_pack_v1 import seed_core_playbook_pack_v1
from core.incident_store import maybe_create_or_link_incident
from engines.playbook_engine import match_playbooks


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
            reputation_summary,
            context
        FROM alerts
        WHERE source_ip = %s
          AND alert_type = %s
        ORDER BY id
        """,
        (source_ip, alert_type),
    )
    return cur.fetchone()


def _assert_targeted_context(context, *, matched_rule_id, window_minutes, matched_groups):
    assert context["correlation_type"] == "targeted_correlation"
    assert context["matched_rule_id"] == matched_rule_id
    assert context["matched_window_minutes"] == window_minutes
    assert context["matched_alert_count"] >= 2
    assert set(context["matched_groups"]) == set(matched_groups)
    assert len(context["matched_groups"]) == len(matched_groups)
    assert context["contributing_alert_ids"]
    assert context["contributing_alert_types"]
    assert context["contributing_sources"]
    assert context["contributing_source_types"]
    assert "raw_payload" not in context


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

    with siem_backend.app.app_context(), patch("engines.correlation_engine.lookup_ip_reputation", return_value=REPUTATION):
        alerts_created = backend_correlation_engine.generate_targeted_correlation_alerts(cur, conn, source_ip)

    alert = fetch_targeted_alert(cur, source_ip, "web_to_app_attack_pattern")
    assert alert is not None
    assert alerts_created == [
        {
            "alert_id": alert[0],
            "source_ip": source_ip,
            "response_action": "flag_high_priority",
            "severity": "high",
            "alert_type": "web_to_app_attack_pattern",
            "source": "nginx",
            "source_type": "web_log",
        }
    ]
    assert alert[1] == "web_to_app_attack_pattern"
    assert alert[2] == "high"
    assert alert[3] == source_ip
    assert alert[4] == "nginx"
    assert alert[5] == "web_log"
    assert alert[6] == f"Web-to-app attack pattern detected from {source_ip}"
    assert alert[7] == "open"
    assert alert[8] == "flag_high_priority"
    assert alert[9] == "pending"
    assert alert[10] == "United States"
    assert alert[11] == "New York"
    assert float(alert[12]) == 40.7128
    assert float(alert[13]) == -74.0060
    assert alert[14] == 65
    assert alert[15] == "medium-risk"
    assert alert[16] == "test-reputation"
    assert alert[17] == "Deterministic test reputation"
    _assert_targeted_context(
        alert[18],
        matched_rule_id="web_to_app_attack_pattern",
        window_minutes=10,
        matched_groups=["nginx_web", "bank_app_custom"],
    )
    assert_no_response_action_link(cur, source_ip, "web_to_app_attack_pattern")


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

    with siem_backend.app.app_context(), patch("engines.correlation_engine.lookup_ip_reputation", return_value=REPUTATION):
        alerts_created = backend_correlation_engine.generate_targeted_correlation_alerts(cur, conn, source_ip)

    alert = fetch_targeted_alert(cur, source_ip, "spray_then_success_pattern")
    assert alert is not None
    assert alerts_created == [
        {
            "alert_id": alert[0],
            "source_ip": source_ip,
            "response_action": "flag_high_priority",
            "severity": "high",
            "alert_type": "spray_then_success_pattern",
            "source": "bank_app",
            "source_type": "custom",
        }
    ]
    assert alert[1] == "spray_then_success_pattern"
    assert alert[2] == "high"
    assert alert[3] == source_ip
    assert alert[4] == "bank_app"
    assert alert[5] == "custom"
    assert alert[6] == f"Password spray followed by successful login from {source_ip}"
    assert alert[8] == "flag_high_priority"
    assert alert[9] == "pending"
    _assert_targeted_context(
        alert[18],
        matched_rule_id="spray_then_success_pattern",
        window_minutes=15,
        matched_groups=["password_spraying_threshold", "successful_login_after_spray"],
    )
    assert_no_response_action_link(cur, source_ip, "spray_then_success_pattern")


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

    with siem_backend.app.app_context(), patch("engines.correlation_engine.lookup_ip_reputation", return_value=REPUTATION):
        alerts_created = backend_correlation_engine.generate_targeted_correlation_alerts(cur, conn, source_ip)

    alert = fetch_targeted_alert(cur, source_ip, "cloud_app_error_pattern")
    assert alert is not None
    assert alerts_created == [
        {
            "alert_id": alert[0],
            "source_ip": source_ip,
            "response_action": "flag_high_priority",
            "severity": "high",
            "alert_type": "cloud_app_error_pattern",
            "source": "nginx",
            "source_type": "web_log",
        }
    ]
    assert alert[1] == "cloud_app_error_pattern"
    assert alert[2] == "high"
    assert alert[3] == source_ip
    assert alert[4] == "nginx"
    assert alert[5] == "web_log"
    assert alert[6] == f"Cloud and web application errors correlated from {source_ip}"
    assert alert[8] == "flag_high_priority"
    assert alert[9] == "pending"
    assert alert[10] == "United States"
    assert alert[11] == "New York"
    _assert_targeted_context(
        alert[18],
        matched_rule_id="cloud_app_error_pattern",
        window_minutes=10,
        matched_groups=["azure_cloud", "nginx_web"],
    )
    assert_no_response_action_link(cur, source_ip, "cloud_app_error_pattern")


def test_targeted_correlation_azure_auth_abuse_exception_correlation(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.126"

    insert_open_alert(
        cur,
        source_ip=source_ip,
        alert_type="app_insights_unauthorized_access_threshold",
        source="azure_insights",
        source_type="cloud_api",
        seconds_ago=3,
        country="Canada",
        city="Toronto",
    )
    insert_open_alert(
        cur,
        source_ip=source_ip,
        alert_type="application_exception_threshold",
        source="azure_insights",
        source_type="cloud_api",
        seconds_ago=1,
        country="Canada",
        city="Toronto",
    )

    with siem_backend.app.app_context(), patch("engines.correlation_engine.lookup_ip_reputation", return_value=REPUTATION):
        alerts_created = backend_correlation_engine.generate_targeted_correlation_alerts(cur, conn, source_ip)

    alert = fetch_targeted_alert(cur, source_ip, "azure_auth_abuse_exception_correlation")
    assert alert is not None
    assert alerts_created == [
        {
            "alert_id": alert[0],
            "source_ip": source_ip,
            "response_action": "flag_high_priority",
            "severity": "high",
            "alert_type": "azure_auth_abuse_exception_correlation",
            "source": "azure_insights",
            "source_type": "cloud_api",
        }
    ]
    assert alert[1] == "azure_auth_abuse_exception_correlation"
    assert alert[2] == "high"
    _assert_targeted_context(
        alert[18],
        matched_rule_id="azure_auth_abuse_exception_correlation",
        window_minutes=10,
        matched_groups=["azure_auth_abuse", "azure_exception"],
    )
    assert_no_response_action_link(cur, source_ip, "azure_auth_abuse_exception_correlation")


def test_targeted_correlation_azure_auth_abuse_exception_does_not_fire_on_isolated_exception(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.127"

    insert_open_alert(
        cur,
        source_ip=source_ip,
        alert_type="application_exception_threshold",
        source="azure_insights",
        source_type="cloud_api",
        seconds_ago=1,
    )

    with siem_backend.app.app_context(), patch("engines.correlation_engine.lookup_ip_reputation", return_value=REPUTATION):
        alerts_created = backend_correlation_engine.generate_targeted_correlation_alerts(cur, conn, source_ip)

    assert alerts_created == []
    assert fetch_targeted_alert(cur, source_ip, "azure_auth_abuse_exception_correlation") is None


def test_azure_auth_abuse_exception_links_existing_incident_without_containment_cycle(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.128"
    seed_core_playbook_pack_v1(conn)

    insert_open_alert(
        cur,
        source_ip=source_ip,
        alert_type="successful_login_after_spray",
        source="azure_insights",
        source_type="cloud_api",
        seconds_ago=5,
    )
    cur.execute(
        """
        SELECT id
        FROM alerts
        WHERE source_ip = %s
          AND alert_type = 'successful_login_after_spray'
        ORDER BY id DESC
        LIMIT 1
        """,
        (source_ip,),
    )
    existing_alert_id = cur.fetchone()[0]
    existing_incident = maybe_create_or_link_incident(conn, existing_alert_id, "CRITICAL", source_ip)

    insert_open_alert(
        cur,
        source_ip=source_ip,
        alert_type="app_insights_unauthorized_access_threshold",
        source="azure_insights",
        source_type="cloud_api",
        seconds_ago=3,
    )
    insert_open_alert(
        cur,
        source_ip=source_ip,
        alert_type="application_exception_threshold",
        source="azure_insights",
        source_type="cloud_api",
        seconds_ago=1,
    )

    with siem_backend.app.app_context(), patch("engines.correlation_engine.lookup_ip_reputation", return_value=REPUTATION):
        alerts_created = backend_correlation_engine.generate_targeted_correlation_alerts(cur, conn, source_ip)

    correlation_alert = next(
        alert for alert in alerts_created if alert["alert_type"] == "azure_auth_abuse_exception_correlation"
    )
    linked = maybe_create_or_link_incident(conn, correlation_alert["alert_id"], "HIGH", source_ip)

    cur.execute("SELECT COUNT(*) FROM incidents WHERE source_ip = %s", (source_ip,))
    assert cur.fetchone()[0] == 1
    assert linked["id"] == existing_incident["id"]
    cur.execute(
        """
        SELECT COUNT(*)
        FROM incident_alerts
        WHERE incident_id = %s
        """,
        (existing_incident["id"],),
    )
    assert cur.fetchone()[0] == 2

    matched = {row["id"]: row for row in match_playbooks(conn, correlation_alert["alert_id"])}
    assert "core-v1-azure-auth-abuse-exception-correlation-investigation" in matched
    assert all(
        step["action"] not in {"require_approval", "block_ip"}
        for step in matched["core-v1-azure-auth-abuse-exception-correlation-investigation"]["steps"]
    )


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

    with siem_backend.app.app_context(), patch("engines.correlation_engine.lookup_ip_reputation", return_value=REPUTATION):
        assert len(backend_correlation_engine.generate_targeted_correlation_alerts(cur, conn, source_ip)) == 1
        assert backend_correlation_engine.generate_targeted_correlation_alerts(cur, conn, source_ip) == []

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
