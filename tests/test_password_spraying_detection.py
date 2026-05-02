from unittest.mock import patch

from psycopg2.extras import Json

import siem_backend


REPUTATION = {
    "reputation_score": 65,
    "reputation_label": "medium-risk",
    "reputation_source": "test-reputation",
    "reputation_summary": "Deterministic test reputation",
}


def insert_failed_login_event(
    cur,
    *,
    source_ip="198.51.100.62",
    username=None,
    message=None,
    seconds_ago=1,
    country="United States",
    city="New York",
    lat="40.7128",
    lon="-74.0060",
):
    payload = {
        "location": {"country": country, "city": city, "lat": lat, "lon": lon},
    }
    if username is not None:
        payload["username"] = username
    if message is not None:
        payload["message"] = message

    cur.execute(
        """
        INSERT INTO events (
            event_type,
            severity,
            source_ip,
            source,
            source_type,
            event_timestamp,
            message,
            app_name,
            environment,
            raw_payload,
            created_at
        )
        VALUES (
            'failed_login',
            'medium',
            %s,
            'bank_app',
            'custom',
            NOW() - (%s * INTERVAL '1 second'),
            %s,
            'banking_app',
            'test',
            %s,
            NOW() - (%s * INTERVAL '1 second')
        )
        """,
        (
            source_ip,
            seconds_ago,
            message or "Failed login attempt",
            Json(payload),
            seconds_ago,
        ),
    )


def fetch_one_alert(cur):
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
        ORDER BY id
        """
    )
    return cur.fetchone()


def test_password_spraying_threshold_boundary_and_alert_field_fidelity(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.62"

    for index, username in enumerate(("alice", "bob", "carol", "dave"), start=5):
        insert_failed_login_event(
            cur,
            source_ip=source_ip,
            username=username,
            seconds_ago=index,
            country="Canada",
            city="Toronto",
        )

    with siem_backend.app.app_context(), patch("backend_detection_engine.lookup_ip_reputation", return_value=REPUTATION):
        assert siem_backend._generate_password_spraying_alerts_core(
            cur,
            conn,
            source="bank_app",
            source_type="custom",
        ) == []

        insert_failed_login_event(
            cur,
            source_ip=source_ip,
            username="erin",
            seconds_ago=1,
            country="United States",
            city="New York",
            lat="40.7128",
            lon="-74.0060",
        )
        alerts_created = siem_backend._generate_password_spraying_alerts_core(
            cur,
            conn,
            source="bank_app",
            source_type="custom",
        )

    assert len(alerts_created) == 1
    assert str(alerts_created[0]["source_ip"]) == source_ip
    assert alerts_created[0]["distinct_username_count"] == 5

    alert = fetch_one_alert(cur)
    assert alert is not None
    assert alert[1] == "password_spraying_threshold"
    assert alert[2] == "high"
    assert alert[3] == source_ip
    assert alert[4] == "bank_app"
    assert alert[5] == "custom"
    assert alert[6] == f"Password spraying suspected from {source_ip}: failed logins across 5 usernames"
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


def test_password_spraying_requires_distinct_usernames(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.63"

    for seconds_ago, username in enumerate(("alice", "alice", "bob", "bob", "carol"), start=1):
        insert_failed_login_event(cur, source_ip=source_ip, username=username, seconds_ago=seconds_ago)

    with siem_backend.app.app_context(), patch("backend_detection_engine.lookup_ip_reputation", return_value=REPUTATION):
        assert siem_backend._generate_password_spraying_alerts_core(
            cur,
            conn,
            source="bank_app",
            source_type="custom",
        ) == []

        insert_failed_login_event(cur, source_ip=source_ip, username="dave", seconds_ago=1)
        assert siem_backend._generate_password_spraying_alerts_core(
            cur,
            conn,
            source="bank_app",
            source_type="custom",
        ) == []

        insert_failed_login_event(cur, source_ip=source_ip, username="erin", seconds_ago=1)
        alerts_created = siem_backend._generate_password_spraying_alerts_core(
            cur,
            conn,
            source="bank_app",
            source_type="custom",
        )

    assert len(alerts_created) == 1
    assert alerts_created[0]["distinct_username_count"] == 5


def test_password_spraying_extracts_distinct_usernames_from_message_payload(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.64"

    messages = (
        "Failed login attempt for username: Alice, source=web",
        "Failed login attempt for username: bob; source=web",
        "Failed login attempt for username: CAROL, source=web",
        "Failed login attempt for username: dave; source=web",
        "Failed login attempt for username: erin, source=web",
    )
    for seconds_ago, message in enumerate(messages, start=1):
        insert_failed_login_event(cur, source_ip=source_ip, message=message, seconds_ago=seconds_ago)

    with siem_backend.app.app_context(), patch("backend_detection_engine.lookup_ip_reputation", return_value=REPUTATION):
        alerts_created = siem_backend._generate_password_spraying_alerts_core(
            cur,
            conn,
            source="bank_app",
            source_type="custom",
        )

    assert len(alerts_created) == 1
    assert str(alerts_created[0]["source_ip"]) == source_ip
    assert alerts_created[0]["distinct_username_count"] == 5


def test_password_spraying_duplicate_suppression_keeps_single_open_alert(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.65"

    for seconds_ago, username in enumerate(("alice", "bob", "carol", "dave", "erin"), start=1):
        insert_failed_login_event(cur, source_ip=source_ip, username=username, seconds_ago=seconds_ago)

    with siem_backend.app.app_context(), patch("backend_detection_engine.lookup_ip_reputation", return_value=REPUTATION):
        first_result = siem_backend._generate_password_spraying_alerts_core(
            cur,
            conn,
            source="bank_app",
            source_type="custom",
        )
        insert_failed_login_event(cur, source_ip=source_ip, username="frank", seconds_ago=1)
        second_result = siem_backend._generate_password_spraying_alerts_core(
            cur,
            conn,
            source="bank_app",
            source_type="custom",
        )

    assert len(first_result) == 1
    assert second_result == []

    cur.execute(
        """
        SELECT COUNT(*)
        FROM alerts
        WHERE source_ip = %s
          AND alert_type = 'password_spraying_threshold'
          AND status = 'open'
        """,
        (source_ip,),
    )
    assert cur.fetchone()[0] == 1


def test_password_spraying_currval_links_response_action_to_inserted_alert(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.66"

    for seconds_ago, username in enumerate(("alice", "bob", "carol", "dave", "erin"), start=1):
        insert_failed_login_event(cur, source_ip=source_ip, username=username, seconds_ago=seconds_ago)

    with siem_backend.app.app_context(), patch("backend_detection_engine.lookup_ip_reputation", return_value=REPUTATION):
        siem_backend._generate_password_spraying_alerts_core(cur, conn, source="bank_app", source_type="custom")

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
        """,
        (source_ip,),
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
