from unittest.mock import patch

import pytest
from psycopg2.extras import Json

import siem_backend
import engines.detection_engine as backend_detection_engine


REPUTATION = {
    "reputation_score": 65,
    "reputation_label": "medium-risk",
    "reputation_source": "test-reputation",
    "reputation_summary": "Deterministic test reputation",
}


def insert_request_event(
    cur,
    *,
    event_type="normal_activity",
    source_type="web_log",
    source_ip="198.51.100.102",
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
            'low',
            %s,
            'nginx',
            %s,
            NOW() - (%s * INTERVAL '1 second'),
            'Request event',
            'edge_gateway',
            'test',
            %s,
            NOW() - (%s * INTERVAL '1 second')
        )
        """,
        (
            event_type,
            source_ip,
            source_type,
            seconds_ago,
            Json({"location": {"country": country, "city": city, "lat": lat, "lon": lon}}),
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


def test_high_request_rate_threshold_boundary_and_alert_field_fidelity(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.102"

    for seconds_ago in range(20, 1, -1):
        insert_request_event(cur, source_ip=source_ip, seconds_ago=seconds_ago, country="Canada", city="Toronto")

    with siem_backend.app.app_context(), patch("engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION):
        assert backend_detection_engine._generate_high_request_rate_alerts_core(cur, conn, source="nginx", source_type="web_log") == []

        insert_request_event(
            cur,
            source_ip=source_ip,
            seconds_ago=1,
            country="United States",
            city="New York",
            lat="40.7128",
            lon="-74.0060",
        )
        alerts_created = backend_detection_engine._generate_high_request_rate_alerts_core(
            cur,
            conn,
            source="nginx",
            source_type="web_log",
        )

    assert len(alerts_created) == 1
    assert alerts_created[0]["alert_id"] is not None
    assert str(alerts_created[0]["source_ip"]) == source_ip
    assert alerts_created[0]["attempts"] == 20
    assert alerts_created[0]["response_action"] == "flag_high_priority"

    alert = fetch_one_alert(cur)
    assert alert is not None
    assert alert[1] == "high_request_rate_threshold"
    assert alert[2] == "medium"
    assert alert[3] == source_ip
    assert alert[4] == "nginx"
    assert alert[5] == "web_log"
    assert alert[6] == f"High request rate detected from {source_ip}"
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


def test_high_request_rate_isolates_exact_source_pair_and_event_type(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.103"

    for seconds_ago in range(20, 0, -1):
        insert_request_event(
            cur,
            event_type="port_scan",
            source_type="web_log",
            source_ip=source_ip,
            seconds_ago=seconds_ago,
        )
        insert_request_event(
            cur,
            event_type="normal_activity",
            source_type="custom",
            source_ip=source_ip,
            seconds_ago=seconds_ago,
        )

    with siem_backend.app.app_context(), patch("engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION):
        assert backend_detection_engine._generate_high_request_rate_alerts_core(cur, conn, source="nginx", source_type="web_log") == []

        for seconds_ago in range(20, 0, -1):
            insert_request_event(
                cur,
                event_type="http_error",
                source_type="telemetry",
                source_ip=source_ip,
                seconds_ago=seconds_ago,
            )

        alerts_created = backend_detection_engine._generate_high_request_rate_alerts_core(
            cur,
            conn,
            source="nginx",
            source_type="web_log",
        )

        assert alerts_created == []

        for seconds_ago in range(20, 0, -1):
            insert_request_event(
                cur,
                event_type="http_error",
                source_type="web_log",
                source_ip=source_ip,
                seconds_ago=seconds_ago,
            )

        alerts_created = backend_detection_engine._generate_high_request_rate_alerts_core(
            cur,
            conn,
            source="nginx",
            source_type="web_log",
        )

    assert len(alerts_created) == 1
    assert str(alerts_created[0]["source_ip"]) == source_ip
    assert alerts_created[0]["attempts"] == 20


def test_high_request_rate_duplicate_suppression_keeps_single_open_alert(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.104"

    for seconds_ago in range(20, 0, -1):
        insert_request_event(cur, source_ip=source_ip, seconds_ago=seconds_ago)

    with siem_backend.app.app_context(), patch("engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION):
        first_result = backend_detection_engine._generate_high_request_rate_alerts_core(
            cur,
            conn,
            source="nginx",
            source_type="web_log",
        )
        insert_request_event(cur, source_ip=source_ip, seconds_ago=1)
        second_result = backend_detection_engine._generate_high_request_rate_alerts_core(
            cur,
            conn,
            source="nginx",
            source_type="web_log",
        )

    assert len(first_result) == 1
    assert second_result == []

    cur.execute(
        """
        SELECT COUNT(*)
        FROM alerts
        WHERE source_ip = %s
          AND alert_type = 'high_request_rate_threshold'
          AND status = 'open'
        """,
        (source_ip,),
    )
    assert cur.fetchone()[0] == 1


def test_high_request_rate_currval_sets_alert_metadata_without_sync_response_log(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.105"

    for seconds_ago in range(20, 0, -1):
        insert_request_event(cur, source_ip=source_ip, seconds_ago=seconds_ago)

    with siem_backend.app.app_context(), patch("engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION):
        backend_detection_engine._generate_high_request_rate_alerts_core(cur, conn, source="nginx", source_type="web_log")

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


def test_high_request_rate_uses_detection_config_override(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.106"
    insert_detection_config_override(cur, rule_id="high_request_rate_threshold", threshold=2, window_minutes=1)

    insert_request_event(cur, source_ip=source_ip, seconds_ago=120)
    insert_request_event(cur, source_ip=source_ip, seconds_ago=1)

    with siem_backend.app.app_context(), patch("engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION):
        assert backend_detection_engine._generate_high_request_rate_alerts_core(
            cur,
            conn,
            source="nginx",
            source_type="web_log",
        ) == []

        insert_request_event(cur, source_ip=source_ip, seconds_ago=1)
        alerts_created = backend_detection_engine._generate_high_request_rate_alerts_core(
            cur,
            conn,
            source="nginx",
            source_type="web_log",
        )

    assert len(alerts_created) == 1
    assert alerts_created[0]["attempts"] == 2
