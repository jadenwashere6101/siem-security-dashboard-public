from unittest.mock import patch

import pytest
from psycopg2.extras import Json

import siem_backend
import engines.detection_engine as backend_detection_engine
from engines.detection_config import get_detection_rule_defaults


REPUTATION = {
    "reputation_score": 65,
    "reputation_label": "medium-risk",
    "reputation_source": "test-reputation",
    "reputation_summary": "Deterministic test reputation",
}

LOCATION = {
    "country": "United States",
    "city": "New York",
    "lat": "40.7128",
    "lon": "-74.0060",
}


def make_honeypot_event(
    *,
    event_type,
    source_ip="203.0.113.10",
    raw_payload=None,
    source="honeypot",
    source_type="honeypot",
    message=None,
):
    return {
        "event_type": event_type,
        "severity": "medium",
        "source_ip": source_ip,
        "source": source,
        "source_type": source_type,
        "event_timestamp": None,
        "message": message or f"Honeypot {event_type} event",
        "app_name": "flask_honeypot",
        "environment": "test",
        "raw_payload": raw_payload or {"location": LOCATION},
    }


def insert_honeypot_event(
    cur,
    *,
    event_type,
    source_ip="203.0.113.10",
    raw_payload=None,
    seconds_ago=1,
    source="honeypot",
    source_type="honeypot",
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
            'medium',
            %s,
            %s,
            %s,
            NOW() - (%s * INTERVAL '1 second'),
            %s,
            'flask_honeypot',
            'test',
            %s,
            NOW() - (%s * INTERVAL '1 second')
        )
        """,
        (
            event_type,
            source_ip,
            source,
            source_type,
            seconds_ago,
            f"Honeypot {event_type} event",
            Json(raw_payload or {"location": LOCATION}),
            seconds_ago,
        ),
    )


def insert_detection_config_override(cur, *, rule_id, threshold, window_minutes):
    cur.execute(
        """
        INSERT INTO detection_config (rule_id, parameters, active, updated_by)
        VALUES (%s, %s, TRUE, 'test')
        """,
        (rule_id, Json({"threshold": threshold, "window_minutes": window_minutes})),
    )


def fetch_events(cur, source_ip):
    cur.execute(
        """
        SELECT event_type, host(source_ip), source, source_type, raw_payload
        FROM events
        WHERE source_ip = %s
        ORDER BY id
        """,
        (source_ip,),
    )
    return cur.fetchall()


def fetch_alert(cur, *, alert_type, source_ip):
    cur.execute(
        """
        SELECT alert_type, severity, host(source_ip), source, source_type, message, status, response_action
        FROM alerts
        WHERE alert_type = %s
          AND source_ip = %s
        ORDER BY id
        LIMIT 1
        """,
        (alert_type, source_ip),
    )
    return cur.fetchone()


@pytest.mark.parametrize(
    "event_type",
    ["env_probe", "admin_probe", "scanner_detected", "credential_stuffing"],
)
def test_honeypot_event_types_are_accepted_and_stored(postgres_db, event_type):
    conn, cur = postgres_db
    source_ip = "203.0.113.11"

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation",
        return_value=REPUTATION,
    ):
        result = siem_backend.ingest_normalized_event(
            make_honeypot_event(event_type=event_type, source_ip=source_ip),
            conn,
            cur,
        )

    rows = fetch_events(cur, source_ip)
    assert len(rows) == 1
    assert rows[0][0] == event_type
    assert rows[0][1] == source_ip
    assert rows[0][2] == "honeypot"
    assert rows[0][3] == "honeypot"

    if event_type == "scanner_detected":
        assert len(result) == 1
        assert result[0]["severity"] == "medium"
        assert result[0]["alert_id"] is not None
    else:
        assert result == []


@pytest.mark.parametrize(
    "password_field,password_value",
    [
        ("password", "secret123"),
        ("passwd", "secret123"),
        ("pwd", "secret123"),
        ("user_password", "secret123"),
    ],
)
def test_raw_password_fields_are_rejected(postgres_db, password_field, password_value):
    conn, cur = postgres_db
    source_ip = "203.0.113.12"

    with pytest.raises(ValueError, match="Raw password field"):
        siem_backend.ingest_normalized_event(
            make_honeypot_event(
                event_type="credential_stuffing",
                source_ip=source_ip,
                raw_payload={
                    "username": "alice",
                    password_field: password_value,
                    "location": LOCATION,
                },
            ),
            conn,
            cur,
        )

    assert fetch_events(cur, source_ip) == []


def test_safe_credential_metadata_is_accepted(postgres_db):
    conn, cur = postgres_db
    source_ip = "203.0.113.13"

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation",
        return_value=REPUTATION,
    ):
        siem_backend.ingest_normalized_event(
            make_honeypot_event(
                event_type="credential_stuffing",
                source_ip=source_ip,
                raw_payload={
                    "username": "alice",
                    "password_length": 12,
                    "credential_present": True,
                    "location": LOCATION,
                },
            ),
            conn,
            cur,
        )

    rows = fetch_events(cur, source_ip)
    assert len(rows) == 1
    raw_payload = rows[0][4]
    assert raw_payload["username"] == "alice"
    assert raw_payload["password_length"] == 12
    assert raw_payload["credential_present"] is True
    assert "password" not in raw_payload


def test_env_probe_triggers_on_distinct_paths_only(postgres_db):
    conn, cur = postgres_db
    source_ip = "203.0.113.20"

    for index, path in enumerate(("/.env", "/.env.local", "/config.php"), start=3):
        insert_honeypot_event(
            cur,
            event_type="env_probe",
            source_ip=source_ip,
            raw_payload={"path": path, "location": LOCATION},
            seconds_ago=index,
        )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation",
        return_value=REPUTATION,
    ):
        alerts_created = backend_detection_engine._generate_env_probe_alerts_core(
            cur,
            conn,
            source="honeypot",
            source_type="honeypot",
        )

    assert len(alerts_created) == 1
    assert alerts_created[0]["distinct_path_count"] == 3
    assert alerts_created[0]["severity"] == "high"
    alert = fetch_alert(cur, alert_type="honeypot_env_probe_threshold", source_ip=source_ip)
    assert alert[0] == "honeypot_env_probe_threshold"
    assert alert[3] == "honeypot"
    assert alert[4] == "honeypot"


def test_env_probe_repeated_same_path_does_not_trigger(postgres_db):
    conn, cur = postgres_db
    source_ip = "203.0.113.21"

    for seconds_ago in range(1, 6):
        insert_honeypot_event(
            cur,
            event_type="env_probe",
            source_ip=source_ip,
            raw_payload={"path": "/.env", "location": LOCATION},
            seconds_ago=seconds_ago,
        )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation",
        return_value=REPUTATION,
    ):
        alerts_created = backend_detection_engine._generate_env_probe_alerts_core(
            cur,
            conn,
            source="honeypot",
            source_type="honeypot",
        )

    assert alerts_created == []


def test_admin_probe_triggers_on_distinct_paths_only(postgres_db):
    conn, cur = postgres_db
    source_ip = "203.0.113.22"

    for index, path in enumerate(("/admin", "/wp-admin", "/phpmyadmin"), start=3):
        insert_honeypot_event(
            cur,
            event_type="admin_probe",
            source_ip=source_ip,
            raw_payload={"path": path, "location": LOCATION},
            seconds_ago=index,
        )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation",
        return_value=REPUTATION,
    ):
        alerts_created = backend_detection_engine._generate_admin_probe_alerts_core(
            cur,
            conn,
            source="honeypot",
            source_type="honeypot",
        )

    assert len(alerts_created) == 1
    assert alerts_created[0]["distinct_path_count"] == 3
    assert alerts_created[0]["severity"] == "medium"
    alert = fetch_alert(cur, alert_type="honeypot_admin_probe_threshold", source_ip=source_ip)
    assert alert[0] == "honeypot_admin_probe_threshold"


def test_admin_probe_repeated_same_path_does_not_trigger(postgres_db):
    conn, cur = postgres_db
    source_ip = "203.0.113.23"

    for seconds_ago in range(1, 6):
        insert_honeypot_event(
            cur,
            event_type="admin_probe",
            source_ip=source_ip,
            raw_payload={"path": "/admin", "location": LOCATION},
            seconds_ago=seconds_ago,
        )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation",
        return_value=REPUTATION,
    ):
        alerts_created = backend_detection_engine._generate_admin_probe_alerts_core(
            cur,
            conn,
            source="honeypot",
            source_type="honeypot",
        )

    assert alerts_created == []


def test_scanner_detected_triggers_at_default_threshold(postgres_db):
    conn, cur = postgres_db
    source_ip = "203.0.113.24"

    insert_honeypot_event(
        cur,
        event_type="scanner_detected",
        source_ip=source_ip,
        raw_payload={
            "scanner_signature": "nikto",
            "user_agent": "Nikto/2.1.6",
            "location": LOCATION,
        },
        seconds_ago=1,
    )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation",
        return_value=REPUTATION,
    ):
        alerts_created = backend_detection_engine._generate_scanner_detected_alerts_core(
            cur,
            conn,
            source="honeypot",
            source_type="honeypot",
        )

    assert len(alerts_created) == 1
    assert alerts_created[0]["scanner_events"] == 1
    assert alerts_created[0]["severity"] == "medium"
    alert = fetch_alert(cur, alert_type="honeypot_scanner_detected", source_ip=source_ip)
    assert alert[0] == "honeypot_scanner_detected"


def test_credential_stuffing_triggers_on_distinct_usernames(postgres_db):
    conn, cur = postgres_db
    source_ip = "203.0.113.25"

    for index, username in enumerate(("alice", "bob", "carol", "dave", "erin"), start=5):
        insert_honeypot_event(
            cur,
            event_type="credential_stuffing",
            source_ip=source_ip,
            raw_payload={
                "username": username,
                "password_length": 10,
                "credential_present": True,
                "location": LOCATION,
            },
            seconds_ago=index,
        )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation",
        return_value=REPUTATION,
    ):
        alerts_created = backend_detection_engine._generate_credential_stuffing_alerts_core(
            cur,
            conn,
            source="honeypot",
            source_type="honeypot",
        )

    assert len(alerts_created) == 1
    assert alerts_created[0]["distinct_username_count"] == 5
    assert alerts_created[0]["severity"] == "high"
    alert = fetch_alert(cur, alert_type="honeypot_credential_stuffing_threshold", source_ip=source_ip)
    assert alert[0] == "honeypot_credential_stuffing_threshold"


def test_credential_stuffing_repeated_username_does_not_trigger(postgres_db):
    conn, cur = postgres_db
    source_ip = "203.0.113.26"

    for seconds_ago in range(1, 8):
        insert_honeypot_event(
            cur,
            event_type="credential_stuffing",
            source_ip=source_ip,
            raw_payload={
                "username": "alice",
                "password_length": 10,
                "credential_present": True,
                "location": LOCATION,
            },
            seconds_ago=seconds_ago,
        )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation",
        return_value=REPUTATION,
    ):
        alerts_created = backend_detection_engine._generate_credential_stuffing_alerts_core(
            cur,
            conn,
            source="honeypot",
            source_type="honeypot",
        )

    assert alerts_created == []


def test_honeypot_detection_config_override_controls_env_probe_threshold(postgres_db):
    conn, cur = postgres_db
    source_ip = "203.0.113.27"

    insert_detection_config_override(
        cur,
        rule_id="honeypot_env_probe_threshold",
        threshold=2,
        window_minutes=10,
    )

    for index, path in enumerate(("/.env", "/.git/config"), start=2):
        insert_honeypot_event(
            cur,
            event_type="env_probe",
            source_ip=source_ip,
            raw_payload={"path": path, "location": LOCATION},
            seconds_ago=index,
        )

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation",
        return_value=REPUTATION,
    ):
        alerts_created = backend_detection_engine._generate_env_probe_alerts_core(
            cur,
            conn,
            source="honeypot",
            source_type="honeypot",
        )

    assert len(alerts_created) == 1
    assert alerts_created[0]["distinct_path_count"] == 2


def test_honeypot_defaults_include_all_rule_ids():
    defaults = get_detection_rule_defaults()
    assert {
        "honeypot_env_probe_threshold",
        "honeypot_admin_probe_threshold",
        "honeypot_scanner_detected",
        "honeypot_credential_stuffing_threshold",
    } <= set(defaults.keys())


def test_ingest_normalized_event_returns_honeypot_alerts_for_soar_handoff(postgres_db):
    conn, cur = postgres_db
    source_ip = "203.0.113.28"

    with siem_backend.app.app_context(), patch(
        "engines.detection_engine.lookup_ip_reputation",
        return_value=REPUTATION,
    ):
        for path in ("/.env", "/.env.local"):
            siem_backend.ingest_normalized_event(
                make_honeypot_event(
                    event_type="env_probe",
                    source_ip=source_ip,
                    raw_payload={"path": path, "location": LOCATION},
                ),
                conn,
                cur,
            )
        alerts_created = siem_backend.ingest_normalized_event(
            make_honeypot_event(
                event_type="env_probe",
                source_ip=source_ip,
                raw_payload={"path": "/config.php", "location": LOCATION},
            ),
            conn,
            cur,
        )

    assert len(alerts_created) == 1
    alert = alerts_created[0]
    assert alert["alert_id"] is not None
    assert str(alert["source_ip"]) == source_ip
    assert alert["response_action"] == "flag_high_priority"
    assert alert["severity"] == "high"
