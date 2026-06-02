from core.ip_helpers import get_ip_reputation


def _insert_alert(cur, source_ip, alert_type):
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message, source, source_type)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            alert_type,
            "high",
            source_ip,
            f"{alert_type} test alert",
            "bank_app",
            "custom",
        ),
    )


def _insert_blocked_ip(cur, source_ip):
    cur.execute(
        """
        INSERT INTO blocked_ips (ip_address, reason, status, created_by)
        VALUES (%s, %s, %s, %s)
        """,
        (source_ip, "test block", "active", "pytest"),
    )


def _signal_by_name(reputation, signal):
    return next(
        item for item in reputation["contributing_signals"] if item["signal"] == signal
    )


def test_base_detection_and_blocklist_scoring_is_unchanged(postgres_db):
    _, cur = postgres_db
    source_ip = "198.51.100.10"

    for alert_type in (
        "failed_login_threshold",
        "password_spraying_threshold",
        "successful_login_after_spray",
        "port_scan_threshold",
        "http_error_threshold",
        "high_request_rate_threshold",
    ):
        _insert_alert(cur, source_ip, alert_type)
    _insert_blocked_ip(cur, source_ip)

    reputation = get_ip_reputation(source_ip, cur=cur)

    assert reputation["reputation_score"] == 29
    assert reputation["reputation_label"] == "Critical"
    assert _signal_by_name(reputation, "failed_login_threshold")["total"] == 3
    assert _signal_by_name(reputation, "password_spraying_threshold")["total"] == 5
    assert _signal_by_name(reputation, "successful_login_after_spray")["total"] == 6
    assert _signal_by_name(reputation, "port_scan_threshold")["total"] == 4
    assert _signal_by_name(reputation, "http_error_threshold")["total"] == 2
    assert _signal_by_name(reputation, "high_request_rate_threshold")["total"] == 3
    assert _signal_by_name(reputation, "blocked_ips")["total"] == 6


def test_correlation_only_alert_adds_capped_correlation_bonus(postgres_db):
    _, cur = postgres_db
    source_ip = "198.51.100.11"
    _insert_alert(cur, source_ip, "spray_then_success_pattern")

    reputation = get_ip_reputation(source_ip, cur=cur)

    assert reputation["reputation_score"] == 5
    assert reputation["reputation_label"] == "Suspicious"
    signal = _signal_by_name(reputation, "correlation_escalation_bonus")
    assert signal["total"] == 5
    assert signal["raw_total"] == 5
    assert signal["applied_total"] == 5
    assert signal["cap"] == 8
    assert signal["cap_applied"] is False
    assert signal["correlation_alert_types"] == [
        {
            "alert_type": "spray_then_success_pattern",
            "label": "Spray Then Success Pattern",
            "count": 1,
            "weight": 5,
            "raw_total": 5,
        }
    ]


def test_base_plus_correlation_adds_applied_bonus(postgres_db):
    _, cur = postgres_db
    source_ip = "198.51.100.12"
    _insert_alert(cur, source_ip, "failed_login_threshold")
    _insert_alert(cur, source_ip, "web_to_app_attack_pattern")

    reputation = get_ip_reputation(source_ip, cur=cur)

    assert reputation["reputation_score"] == 9
    assert reputation["reputation_label"] == "Suspicious"
    assert _signal_by_name(reputation, "failed_login_threshold")["total"] == 3
    signal = _signal_by_name(reputation, "correlation_escalation_bonus")
    assert signal["raw_total"] == 6
    assert signal["applied_total"] == 6
    assert signal["cap_applied"] is False


def test_multiple_correlation_alerts_are_capped_at_eight_points(postgres_db):
    _, cur = postgres_db
    source_ip = "198.51.100.13"
    _insert_alert(cur, source_ip, "web_to_app_attack_pattern")
    _insert_alert(cur, source_ip, "spray_then_success_pattern")
    _insert_alert(cur, source_ip, "cloud_app_error_pattern")

    reputation = get_ip_reputation(source_ip, cur=cur)

    assert reputation["reputation_score"] == 8
    assert reputation["reputation_label"] == "Suspicious"
    signal = _signal_by_name(reputation, "correlation_escalation_bonus")
    assert signal["count"] == 3
    assert signal["total"] == 8
    assert signal["raw_total"] == 15
    assert signal["applied_total"] == 8
    assert signal["cap"] == 8
    assert signal["cap_applied"] is True
    assert signal["correlation_alert_types"] == [
        {
            "alert_type": "spray_then_success_pattern",
            "label": "Spray Then Success Pattern",
            "count": 1,
            "weight": 5,
            "raw_total": 5,
        },
        {
            "alert_type": "web_to_app_attack_pattern",
            "label": "Web To App Attack Pattern",
            "count": 1,
            "weight": 6,
            "raw_total": 6,
        },
        {
            "alert_type": "cloud_app_error_pattern",
            "label": "Cloud App Error Pattern",
            "count": 1,
            "weight": 4,
            "raw_total": 4,
        },
    ]


def test_correlation_alerts_do_not_count_as_uncapped_base_signals(postgres_db):
    _, cur = postgres_db
    source_ip = "198.51.100.14"

    for _ in range(3):
        _insert_alert(cur, source_ip, "web_to_app_attack_pattern")

    reputation = get_ip_reputation(source_ip, cur=cur)

    assert reputation["reputation_score"] == 8
    assert reputation["reputation_label"] == "Suspicious"
    assert len(reputation["contributing_signals"]) == 1
    signal = reputation["contributing_signals"][0]
    assert signal["signal"] == "correlation_escalation_bonus"
    assert signal["raw_total"] == 18
    assert signal["applied_total"] == 8
    assert signal["cap_applied"] is True
