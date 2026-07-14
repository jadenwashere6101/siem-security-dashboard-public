from core.notification_policy_store import (
    default_notification_policy,
    load_notification_policy,
    upsert_notification_policy,
    validate_notification_policy_updates,
)


def test_notification_policy_store_loads_seeded_defaults(postgres_db):
    conn, cur = postgres_db

    policy = load_notification_policy(cur)

    assert policy["slack_enabled"] is False
    assert policy["minimum_severity"] == "high"
    assert policy["notify_on_alerts"] is True
    assert policy["notify_on_incidents"] is True
    assert policy["slack_format"] == "compact"
    assert policy["pfsense_destination"] == "pfSense destination"
    assert policy["honeypot_destination"] == "Honeypot destination"
    assert policy["critical_cross_source_destination"] == "Critical / Cross-Source Security destination"
    assert policy["status"] == "applied"


def test_notification_policy_store_upsert_updates_current_row(postgres_db):
    conn, cur = postgres_db

    upsert_notification_policy(
        cur,
        {
            "slack_enabled": True,
            "minimum_severity": "critical",
            "slack_format": "detailed",
            "pfsense_destination": "#soc-pfsense",
            "honeypot_destination": "#soc-honeypot",
            "critical_cross_source_destination": "#soc-critical",
        },
        "testadmin",
    )
    conn.commit()

    policy = load_notification_policy(cur)
    assert policy["slack_enabled"] is True
    assert policy["minimum_severity"] == "critical"
    assert policy["slack_format"] == "detailed"
    assert policy["pfsense_destination"] == "#soc-pfsense"
    assert policy["honeypot_destination"] == "#soc-honeypot"
    assert policy["critical_cross_source_destination"] == "#soc-critical"
    assert policy["updated_by"] == "testadmin"


def test_notification_policy_store_rejects_url_destinations():
    try:
        validate_notification_policy_updates({"pfsense_destination": "https://hooks.slack.com/services/x"})
        assert False, "expected invalid destination to fail"
    except ValueError as error:
        assert "routing label" in str(error)


def test_default_notification_policy_is_safe_when_store_unavailable():
    policy = default_notification_policy(status="unavailable")

    assert policy["slack_enabled"] is False
    assert policy["status"] == "unavailable"
