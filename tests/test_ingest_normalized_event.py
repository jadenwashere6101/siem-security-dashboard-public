from unittest.mock import patch

import pytest

import siem_backend


REPUTATION = {
    "reputation_score": 65,
    "reputation_label": "medium-risk",
    "reputation_source": "test-reputation",
    "reputation_summary": "Deterministic test reputation",
}


def make_event(
    *,
    event_type="normal_activity",
    source_ip="198.51.100.132",
    source="bank_app",
    source_type="custom",
    message="Normalized event",
    raw_payload=None,
):
    return {
        "event_type": event_type,
        "severity": "medium",
        "source_ip": source_ip,
        "source": source,
        "source_type": source_type,
        "event_timestamp": None,
        "message": message,
        "app_name": "test_app",
        "environment": "test",
        "raw_payload": raw_payload
        or {
            "location": {
                "country": "United States",
                "city": "New York",
                "lat": "40.7128",
                "lon": "-74.0060",
            }
        },
    }


def fetch_event(cur, source_ip):
    cur.execute(
        """
        SELECT
            event_type,
            severity,
            host(source_ip),
            source,
            source_type,
            message,
            app_name,
            environment,
            raw_payload->'location'->>'country'
        FROM events
        WHERE source_ip = %s
        ORDER BY id
        """,
        (source_ip,),
    )
    return cur.fetchone()


def count_rows(cur, table_name):
    cur.execute(f"SELECT COUNT(*) FROM {table_name}")
    return cur.fetchone()[0]


def test_ingest_normalized_event_inserts_event_without_detection(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.132"

    result = siem_backend.ingest_normalized_event(
        make_event(
            event_type="normal_activity",
            source_ip=source_ip,
            source="bank_app",
            source_type="custom",
            message="No detector route expected",
        ),
        conn,
        cur,
    )

    assert result == []
    event = fetch_event(cur, source_ip)
    assert event == (
        "normal_activity",
        "medium",
        source_ip,
        "bank_app",
        "custom",
        "No detector route expected",
        "test_app",
        "test",
        "United States",
    )
    assert count_rows(cur, "alerts") == 0


def test_ingest_normalized_event_routes_into_port_scan_detection_core(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.133"

    with siem_backend.app.app_context(), \
         patch("siem_backend.lookup_ip_reputation", return_value=REPUTATION), \
         patch("backend_correlation_engine.lookup_ip_reputation", return_value=REPUTATION):
        first_result = siem_backend.ingest_normalized_event(
            make_event(event_type="port_scan", source_ip=source_ip, source="nginx", source_type="web_log"),
            conn,
            cur,
        )
        second_result = siem_backend.ingest_normalized_event(
            make_event(event_type="port_scan", source_ip=source_ip, source="nginx", source_type="web_log"),
            conn,
            cur,
        )

    assert first_result == []
    assert len(second_result) == 1
    assert str(second_result[0]["source_ip"]) == source_ip
    assert second_result[0]["attempts"] == 2

    cur.execute(
        """
        SELECT alert_type, host(source_ip), source, source_type
        FROM alerts
        WHERE source_ip = %s
        """,
        (source_ip,),
    )
    assert cur.fetchone() == ("port_scan_threshold", source_ip, "nginx", "web_log")


def test_ingest_normalized_event_runs_detection_then_correlation_on_same_cursor(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.134"

    with siem_backend.app.app_context(), \
         patch("siem_backend.lookup_ip_reputation", return_value=REPUTATION), \
         patch("backend_correlation_engine.lookup_ip_reputation", return_value=REPUTATION):
        for username in ("alice", "bob"):
            siem_backend.ingest_normalized_event(
                make_event(
                    event_type="failed_login",
                    source_ip=source_ip,
                    source="bank_app",
                    source_type="custom",
                    raw_payload={"username": username, "location": {"country": "Canada", "city": "Toronto"}},
                ),
                conn,
                cur,
            )

        failed_login_alerts = siem_backend.ingest_normalized_event(
            make_event(
                event_type="failed_login",
                source_ip=source_ip,
                source="bank_app",
                source_type="custom",
                raw_payload={"username": "carol", "location": {"country": "Canada", "city": "Toronto"}},
            ),
            conn,
            cur,
        )

        assert len(failed_login_alerts) == 1

        siem_backend.ingest_normalized_event(
            make_event(event_type="port_scan", source_ip=source_ip, source="nginx", source_type="web_log"),
            conn,
            cur,
        )
        port_scan_alerts = siem_backend.ingest_normalized_event(
            make_event(event_type="port_scan", source_ip=source_ip, source="nginx", source_type="web_log"),
            conn,
            cur,
        )

    assert len(port_scan_alerts) == 1

    cur.execute(
        """
        SELECT alert_type
        FROM alerts
        WHERE source_ip = %s
        ORDER BY id
        """,
        (source_ip,),
    )
    assert [row[0] for row in cur.fetchall()] == [
        "failed_login_threshold",
        "port_scan_threshold",
        "correlated_activity",
    ]

    cur.execute(
        """
        SELECT message
        FROM alerts
        WHERE source_ip = %s
          AND alert_type = 'correlated_activity'
        """,
        (source_ip,),
    )
    assert cur.fetchone()[0] == (
        f"Multi-source suspicious activity detected from {source_ip} "
        "involving: failed_login_threshold, port_scan_threshold"
    )


def test_ingest_normalized_event_rolls_back_event_insert_on_downstream_failure(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.135"

    def fail_detector(_cur, _conn, source=None, source_type=None):
        raise RuntimeError("forced downstream failure")

    with patch("siem_backend._generate_port_scan_alerts_core", side_effect=fail_detector):
        with pytest.raises(RuntimeError, match="forced downstream failure"):
            siem_backend.ingest_normalized_event(
                make_event(event_type="port_scan", source_ip=source_ip, source="nginx", source_type="web_log"),
                conn,
                cur,
            )

    conn.rollback()

    assert count_rows(cur, "events") == 0
    assert count_rows(cur, "alerts") == 0
    assert count_rows(cur, "response_actions_log") == 0


def test_ingest_normalized_event_orchestration_ordering_uses_detection_before_correlation(postgres_db):
    conn, cur = postgres_db
    calls = []
    shared_ids = []

    def fake_port_scan(_cur, _conn, source=None, source_type=None):
        calls.append(("detect", source, source_type))
        shared_ids.append((id(cur), id(conn), id(_cur), id(_conn)))
        return [{"source_ip": "198.51.100.136"}]

    def fake_generic_correlation(_cur, _conn, source_ip):
        calls.append(("generic_correlation", source_ip))
        shared_ids.append((id(cur), id(conn), id(_cur), id(_conn)))

    def fake_targeted_correlation(_cur, _conn, source_ip):
        calls.append(("targeted_correlation", source_ip))
        shared_ids.append((id(cur), id(conn), id(_cur), id(_conn)))

    with patch("siem_backend._generate_port_scan_alerts_core", side_effect=fake_port_scan), \
         patch("siem_backend.generate_correlated_activity_alerts", side_effect=fake_generic_correlation), \
         patch("siem_backend.generate_targeted_correlation_alerts", side_effect=fake_targeted_correlation):
        result = siem_backend.ingest_normalized_event(
            make_event(event_type="port_scan", source_ip="198.51.100.136", source="nginx", source_type="web_log"),
            conn,
            cur,
        )

    assert result == [{"source_ip": "198.51.100.136"}]
    assert calls == [
        ("detect", "nginx", "web_log"),
        ("generic_correlation", "198.51.100.136"),
        ("targeted_correlation", "198.51.100.136"),
    ]
    assert all(item == (id(cur), id(conn), id(cur), id(conn)) for item in shared_ids)
