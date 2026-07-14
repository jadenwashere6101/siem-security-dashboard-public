from unittest.mock import patch

from psycopg2.extras import Json

import siem_backend
import engines.detection_engine as backend_detection_engine


REPUTATION = {
    "reputation_score": 65,
    "reputation_label": "medium-risk",
    "reputation_source": "test-reputation",
    "reputation_summary": "Deterministic test reputation",
}

LOW_REPUTATION = {
    "reputation_score": 0,
    "reputation_label": "normal",
    "reputation_source": "test-reputation",
    "reputation_summary": "No elevated history",
}


def insert_auth_event(
    cur,
    *,
    event_type,
    source_ip="198.51.100.72",
    username=None,
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
            %s,
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
            event_type,
            source_ip,
            seconds_ago,
            f"{event_type} event",
            Json(payload),
            seconds_ago,
        ),
    )


def insert_failed_login_spray_events(cur, *, source_ip, seconds_start=10):
    for offset, username in enumerate(("alice", "bob", "carol", "dave", "erin")):
        insert_auth_event(
            cur,
            event_type="failed_login",
            source_ip=source_ip,
            username=username,
            seconds_ago=seconds_start - offset,
            country="Canada",
            city="Toronto",
        )


def insert_password_spraying_alert(cur, *, source_ip):
    cur.execute(
        """
        INSERT INTO alerts (
            source_ip,
            alert_type,
            severity,
            source,
            source_type,
            message,
            status,
            response_action,
            response_status
        )
        VALUES (
            %s,
            'password_spraying_threshold',
            'high',
            'bank_app',
            'custom',
            'Password spraying prerequisite alert',
            'open',
            'monitor',
            'executed'
        )
        """,
        (source_ip,),
    )


def fetch_one_success_after_spray_alert(cur):
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
        WHERE alert_type = 'successful_login_after_spray'
        ORDER BY id
        """
    )
    return cur.fetchone()


def test_success_after_spray_does_not_require_existing_spray_alert(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.72"

    insert_failed_login_spray_events(cur, source_ip=source_ip)
    insert_auth_event(
        cur,
        event_type="successful_login",
        source_ip=source_ip,
        seconds_ago=1,
        country="United States",
        city="New York",
    )

    with siem_backend.app.app_context(), patch("engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION):
        alerts_created = backend_detection_engine._generate_successful_login_after_spray_alerts_core(
            cur,
            conn,
            source="bank_app",
            source_type="custom",
        )

    assert len(alerts_created) == 1
    assert alerts_created[0]["alert_id"] is not None
    assert str(alerts_created[0]["source_ip"]) == source_ip
    assert alerts_created[0]["success_at"]
    assert alerts_created[0]["response_action"] == "flag_high_priority"


def test_success_after_spray_successful_login_trigger_and_alert_field_fidelity(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.73"

    insert_password_spraying_alert(cur, source_ip=source_ip)
    insert_failed_login_spray_events(cur, source_ip=source_ip)

    with siem_backend.app.app_context(), patch("engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION):
        assert backend_detection_engine._generate_successful_login_after_spray_alerts_core(
            cur,
            conn,
            source="bank_app",
            source_type="custom",
        ) == []

        insert_auth_event(
            cur,
            event_type="successful_login",
            source_ip=source_ip,
            seconds_ago=1,
            country="United States",
            city="New York",
            lat="40.7128",
            lon="-74.0060",
        )
        alerts_created = backend_detection_engine._generate_successful_login_after_spray_alerts_core(
            cur,
            conn,
            source="bank_app",
            source_type="custom",
        )

    assert len(alerts_created) == 1
    assert str(alerts_created[0]["source_ip"]) == source_ip
    assert alerts_created[0]["success_at"]

    alert = fetch_one_success_after_spray_alert(cur)
    assert alert is not None
    assert alert[1] == "successful_login_after_spray"
    assert alert[2] == "critical"
    assert alert[3] == source_ip
    assert alert[4] == "bank_app"
    assert alert[5] == "custom"
    assert alert[6] == f"Successful login after password spraying detected from {source_ip}"
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


def test_success_after_spray_duplicate_suppression_keeps_single_open_alert(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.74"

    insert_password_spraying_alert(cur, source_ip=source_ip)
    insert_failed_login_spray_events(cur, source_ip=source_ip)
    insert_auth_event(cur, event_type="successful_login", source_ip=source_ip, seconds_ago=1)

    with siem_backend.app.app_context(), patch("engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION):
        first_result = backend_detection_engine._generate_successful_login_after_spray_alerts_core(
            cur,
            conn,
            source="bank_app",
            source_type="custom",
        )
        insert_auth_event(cur, event_type="successful_login", source_ip=source_ip, seconds_ago=1)
        second_result = backend_detection_engine._generate_successful_login_after_spray_alerts_core(
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
          AND alert_type = 'successful_login_after_spray'
          AND status = 'open'
        """,
        (source_ip,),
    )
    assert cur.fetchone()[0] == 1


def test_success_after_spray_critical_alert_floor_prevents_monitor_response_action(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.79"

    insert_password_spraying_alert(cur, source_ip=source_ip)
    insert_failed_login_spray_events(cur, source_ip=source_ip)
    insert_auth_event(cur, event_type="successful_login", source_ip=source_ip, seconds_ago=1)

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation",
        return_value=LOW_REPUTATION,
    ):
        alerts_created = backend_detection_engine._generate_successful_login_after_spray_alerts_core(
            cur,
            conn,
            source="bank_app",
            source_type="custom",
        )

    assert len(alerts_created) == 1
    alert = fetch_one_success_after_spray_alert(cur)
    assert alert is not None
    assert alert[2] == "critical"
    assert alert[8] == "flag_high_priority"


def test_success_after_spray_currval_sets_alert_metadata_without_sync_response_log(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.75"

    insert_password_spraying_alert(cur, source_ip=source_ip)
    insert_failed_login_spray_events(cur, source_ip=source_ip)
    insert_auth_event(cur, event_type="successful_login", source_ip=source_ip, seconds_ago=1)

    with siem_backend.app.app_context(), patch("engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION):
        backend_detection_engine._generate_successful_login_after_spray_alerts_core(
            cur,
            conn,
            source="bank_app",
            source_type="custom",
        )

    cur.execute(
        """
        SELECT
            a.id,
            a.response_action,
            a.response_status
        FROM alerts a
        WHERE a.source_ip = %s
          AND a.alert_type = 'successful_login_after_spray'
        """,
        (source_ip,),
    )
    row = cur.fetchone()

    assert row is not None
    assert row[1] == "flag_high_priority"
    assert row[2] == "pending"
    cur.execute("SELECT COUNT(*) FROM response_actions_log WHERE alert_id = %s", (row[0],))
    assert cur.fetchone()[0] == 0
