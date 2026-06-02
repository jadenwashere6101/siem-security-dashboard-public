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


def insert_application_event(
    cur,
    *,
    event_type="application_exception",
    source_ip="198.51.100.92",
    exception_type="ValueError",
    seconds_ago=1,
    country="United States",
    city="New York",
    lat="40.7128",
    lon="-74.0060",
):
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
            'high',
            %s,
            'opentelemetry',
            'telemetry',
            NOW() - (%s * INTERVAL '1 second'),
            %s,
            'checkout_api',
            'test',
            %s,
            NOW() - (%s * INTERVAL '1 second')
        )
        """,
        (
            event_type,
            source_ip,
            seconds_ago,
            f"Application exception: {exception_type}",
            Json(
                {
                    "exception_type": exception_type,
                    "location": {"country": country, "city": city, "lat": lat, "lon": lon},
                }
            ),
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


def insert_detection_config_override(cur, *, rule_id, threshold, window_minutes):
    cur.execute(
        """
        INSERT INTO detection_config (rule_id, parameters, active, updated_by)
        VALUES (%s, %s, TRUE, 'test')
        """,
        (rule_id, Json({"threshold": threshold, "window_minutes": window_minutes})),
    )


def test_application_exception_threshold_boundary_and_alert_field_fidelity(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.92"

    for seconds_ago in (3, 2):
        insert_application_event(cur, source_ip=source_ip, seconds_ago=seconds_ago, country="Canada", city="Toronto")

    with siem_backend.app.app_context(), patch("engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION):
        assert backend_detection_engine._generate_application_exception_alerts_core(
            cur,
            conn,
            source="opentelemetry",
            source_type="telemetry",
        ) == []

        insert_application_event(
            cur,
            source_ip=source_ip,
            seconds_ago=1,
            country="United States",
            city="New York",
            lat="40.7128",
            lon="-74.0060",
        )
        alerts_created = backend_detection_engine._generate_application_exception_alerts_core(
            cur,
            conn,
            source="opentelemetry",
            source_type="telemetry",
        )

    assert len(alerts_created) == 1
    assert alerts_created[0]["alert_id"] is not None
    assert str(alerts_created[0]["source_ip"]) == source_ip
    assert alerts_created[0]["attempts"] == 3
    assert alerts_created[0]["response_action"] == "flag_high_priority"

    alert = fetch_one_alert(cur)
    assert alert is not None
    assert alert[1] == "application_exception_threshold"
    assert alert[2] == "high"
    assert alert[3] == source_ip
    assert alert[4] == "opentelemetry"
    assert alert[5] == "telemetry"
    assert alert[6] == f"Repeated application exceptions detected from {source_ip}"
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


def test_application_exception_trigger_depends_on_application_exception_event_type(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.93"

    for seconds_ago in (3, 2, 1):
        insert_application_event(
            cur,
            event_type="normal_activity",
            source_ip=source_ip,
            exception_type="ValueError",
            seconds_ago=seconds_ago,
        )

    with siem_backend.app.app_context(), patch("engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION):
        assert backend_detection_engine._generate_application_exception_alerts_core(
            cur,
            conn,
            source="opentelemetry",
            source_type="telemetry",
        ) == []

        for seconds_ago in (3, 2, 1):
            insert_application_event(
                cur,
                event_type="application_exception",
                source_ip=source_ip,
                exception_type="ValueError",
                seconds_ago=seconds_ago,
            )

        alerts_created = backend_detection_engine._generate_application_exception_alerts_core(
            cur,
            conn,
            source="opentelemetry",
            source_type="telemetry",
        )

    assert len(alerts_created) == 1
    assert str(alerts_created[0]["source_ip"]) == source_ip
    assert alerts_created[0]["attempts"] == 3


def test_application_exception_duplicate_suppression_keeps_single_open_alert(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.94"

    for seconds_ago in (3, 2, 1):
        insert_application_event(cur, source_ip=source_ip, seconds_ago=seconds_ago)

    with siem_backend.app.app_context(), patch("engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION):
        first_result = backend_detection_engine._generate_application_exception_alerts_core(
            cur,
            conn,
            source="opentelemetry",
            source_type="telemetry",
        )
        insert_application_event(cur, source_ip=source_ip, seconds_ago=1)
        second_result = backend_detection_engine._generate_application_exception_alerts_core(
            cur,
            conn,
            source="opentelemetry",
            source_type="telemetry",
        )

    assert len(first_result) == 1
    assert second_result == []

    cur.execute(
        """
        SELECT COUNT(*)
        FROM alerts
        WHERE source_ip = %s
          AND alert_type = 'application_exception_threshold'
          AND status = 'open'
        """,
        (source_ip,),
    )
    assert cur.fetchone()[0] == 1


def test_application_exception_currval_sets_alert_metadata_without_sync_response_log(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.95"

    for seconds_ago in (3, 2, 1):
        insert_application_event(cur, source_ip=source_ip, seconds_ago=seconds_ago)

    with siem_backend.app.app_context(), patch("engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION):
        backend_detection_engine._generate_application_exception_alerts_core(
            cur,
            conn,
            source="opentelemetry",
            source_type="telemetry",
        )

    cur.execute(
        """
        SELECT
            a.id,
            a.response_action,
            a.response_status
        FROM alerts a
        WHERE a.source_ip = %s
        """,
        (source_ip,),
    )
    row = cur.fetchone()

    assert row is not None
    assert row[1] == "flag_high_priority"
    assert row[2] == "pending"
    cur.execute("SELECT COUNT(*) FROM response_actions_log WHERE alert_id = %s", (row[0],))
    assert cur.fetchone()[0] == 0


def test_application_exception_uses_detection_config_override(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.96"
    insert_detection_config_override(cur, rule_id="application_exception_threshold", threshold=2, window_minutes=1)

    insert_application_event(cur, source_ip=source_ip, seconds_ago=120)
    insert_application_event(cur, source_ip=source_ip, seconds_ago=1)

    with siem_backend.app.app_context(), patch("engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION):
        assert backend_detection_engine._generate_application_exception_alerts_core(
            cur,
            conn,
            source="opentelemetry",
            source_type="telemetry",
        ) == []

        insert_application_event(cur, source_ip=source_ip, seconds_ago=1)
        alerts_created = backend_detection_engine._generate_application_exception_alerts_core(
            cur,
            conn,
            source="opentelemetry",
            source_type="telemetry",
        )

    assert len(alerts_created) == 1
    assert alerts_created[0]["attempts"] == 2
