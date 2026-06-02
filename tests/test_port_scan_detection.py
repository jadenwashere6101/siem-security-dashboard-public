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


def insert_port_scan_event(
    cur,
    *,
    source_ip="198.51.100.52",
    seconds_ago=1,
    country="United States",
    city="New York",
    lat="40.7128",
    lon="-74.0060",
    destination_port=None,
    port_key="destination_port",
):
    raw_payload = {"location": {"country": country, "city": city, "lat": lat, "lon": lon}}
    if destination_port is not None:
        raw_payload[port_key] = destination_port

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
            'port_scan',
            'medium',
            %s,
            'nginx',
            'web_log',
            NOW() - (%s * INTERVAL '1 second'),
            'Port scan event',
            'edge_gateway',
            'test',
            %s,
            NOW() - (%s * INTERVAL '1 second')
        )
        """,
        (
            source_ip,
            seconds_ago,
            Json(raw_payload),
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


def insert_detection_config_override(cur, *, threshold, window_minutes):
    cur.execute(
        """
        INSERT INTO detection_config (rule_id, parameters, active, updated_by)
        VALUES ('port_scan_threshold', %s, TRUE, 'test')
        """,
        (Json({"threshold": threshold, "window_minutes": window_minutes}),),
    )


def test_port_scan_threshold_boundary_and_alert_field_fidelity(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.52"

    insert_port_scan_event(
        cur,
        source_ip=source_ip,
        seconds_ago=2,
        country="Canada",
        city="Toronto",
        destination_port=22,
    )

    with siem_backend.app.app_context(), patch("engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION):
        assert backend_detection_engine._generate_port_scan_alerts_core(cur, conn, source="nginx", source_type="web_log") == []

        insert_port_scan_event(
            cur,
            source_ip=source_ip,
            seconds_ago=1,
            country="United States",
            city="New York",
            lat="40.7128",
            lon="-74.0060",
            destination_port=443,
        )
        alerts_created = backend_detection_engine._generate_port_scan_alerts_core(
            cur,
            conn,
            source="nginx",
            source_type="web_log",
        )

    assert len(alerts_created) == 1
    assert alerts_created[0]["alert_id"] is not None
    assert str(alerts_created[0]["source_ip"]) == source_ip
    assert alerts_created[0]["attempts"] == 2
    assert alerts_created[0]["response_action"] == "flag_high_priority"

    alert = fetch_one_alert(cur)
    assert alert is not None
    assert alert[1] == "port_scan_threshold"
    assert alert[2] == "medium"
    assert alert[3] == source_ip
    assert alert[4] == "nginx"
    assert alert[5] == "web_log"
    assert alert[6] == f"2 port scan events detected from {source_ip}"
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


def test_port_scan_same_destination_port_does_not_alert(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.55"

    insert_port_scan_event(cur, source_ip=source_ip, seconds_ago=2, destination_port=443)
    insert_port_scan_event(cur, source_ip=source_ip, seconds_ago=1, destination_port=443)

    with siem_backend.app.app_context(), patch("engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION):
        result = backend_detection_engine._generate_port_scan_alerts_core(
            cur,
            conn,
            source="nginx",
            source_type="web_log",
        )

    assert result == []
    assert fetch_one_alert(cur) is None


def test_port_scan_missing_destination_port_does_not_alert(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.56"

    insert_port_scan_event(cur, source_ip=source_ip, seconds_ago=2)
    insert_port_scan_event(cur, source_ip=source_ip, seconds_ago=1)

    with siem_backend.app.app_context(), patch("engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION):
        result = backend_detection_engine._generate_port_scan_alerts_core(
            cur,
            conn,
            source="nginx",
            source_type="web_log",
        )

    assert result == []
    assert fetch_one_alert(cur) is None


def test_port_scan_invalid_destination_port_is_ignored(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.57"

    insert_port_scan_event(cur, source_ip=source_ip, seconds_ago=3, destination_port=22)
    insert_port_scan_event(cur, source_ip=source_ip, seconds_ago=2, destination_port="not-a-port")

    with siem_backend.app.app_context(), patch("engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION):
        assert backend_detection_engine._generate_port_scan_alerts_core(
            cur,
            conn,
            source="nginx",
            source_type="web_log",
        ) == []

        insert_port_scan_event(cur, source_ip=source_ip, seconds_ago=1, destination_port=443)
        alerts_created = backend_detection_engine._generate_port_scan_alerts_core(
            cur,
            conn,
            source="nginx",
            source_type="web_log",
        )

    assert len(alerts_created) == 1
    assert alerts_created[0]["attempts"] == 2


@pytest.mark.parametrize("port_key", ["destination_port", "dest_port", "dst_port", "port"])
def test_port_scan_supports_common_destination_port_keys(postgres_db, port_key):
    conn, cur = postgres_db
    source_ip = "198.51.100.58"

    insert_port_scan_event(cur, source_ip=source_ip, seconds_ago=2, destination_port=22, port_key=port_key)
    insert_port_scan_event(cur, source_ip=source_ip, seconds_ago=1, destination_port=443, port_key=port_key)

    with siem_backend.app.app_context(), patch("engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION):
        alerts_created = backend_detection_engine._generate_port_scan_alerts_core(
            cur,
            conn,
            source="nginx",
            source_type="web_log",
        )

    assert len(alerts_created) == 1
    assert alerts_created[0]["attempts"] == 2


def test_port_scan_detection_config_override_controls_distinct_port_threshold_and_window(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.59"
    insert_detection_config_override(cur, threshold=3, window_minutes=1)

    insert_port_scan_event(cur, source_ip=source_ip, seconds_ago=120, destination_port=22)
    insert_port_scan_event(cur, source_ip=source_ip, seconds_ago=2, destination_port=80)
    insert_port_scan_event(cur, source_ip=source_ip, seconds_ago=1, destination_port=443)

    with siem_backend.app.app_context(), patch("engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION):
        assert backend_detection_engine._generate_port_scan_alerts_core(
            cur,
            conn,
            source="nginx",
            source_type="web_log",
        ) == []

        insert_port_scan_event(cur, source_ip=source_ip, seconds_ago=1, destination_port=8080)
        alerts_created = backend_detection_engine._generate_port_scan_alerts_core(
            cur,
            conn,
            source="nginx",
            source_type="web_log",
        )

    assert len(alerts_created) == 1
    assert alerts_created[0]["attempts"] == 3


def test_port_scan_duplicate_suppression_keeps_single_open_alert(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.53"

    for seconds_ago, destination_port in ((3, 22), (2, 443)):
        insert_port_scan_event(cur, source_ip=source_ip, seconds_ago=seconds_ago, destination_port=destination_port)

    with siem_backend.app.app_context(), patch("engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION):
        first_result = backend_detection_engine._generate_port_scan_alerts_core(
            cur,
            conn,
            source="nginx",
            source_type="web_log",
        )
        insert_port_scan_event(cur, source_ip=source_ip, seconds_ago=1, destination_port=8080)
        second_result = backend_detection_engine._generate_port_scan_alerts_core(
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
          AND alert_type = 'port_scan_threshold'
          AND status = 'open'
        """,
        (source_ip,),
    )
    assert cur.fetchone()[0] == 1


def test_port_scan_currval_sets_alert_metadata_without_sync_response_log(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.54"

    for seconds_ago, destination_port in ((2, 22), (1, 443)):
        insert_port_scan_event(cur, source_ip=source_ip, seconds_ago=seconds_ago, destination_port=destination_port)

    with siem_backend.app.app_context(), patch("engines.detection_engine.lookup_ip_reputation", return_value=REPUTATION):
        backend_detection_engine._generate_port_scan_alerts_core(cur, conn, source="nginx", source_type="web_log")

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
