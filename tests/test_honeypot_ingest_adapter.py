from unittest.mock import MagicMock

import pytest


VALID_API_KEY = "test-ingest-api-key"

REPUTATION = {
    "reputation_score": 65,
    "reputation_label": "medium-risk",
    "reputation_source": "test-reputation",
    "reputation_summary": "Deterministic test reputation",
}


class ConnectionProxy:
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        pass


def honeypot_payload(**overrides):
    payload = {
        "event_type": "env_probe",
        "source_ip": "203.0.113.80",
        "timestamp": "2026-06-23T12:34:56Z",
        "path": "/.env",
        "method": "GET",
        "user_agent": "curl/8.0",
        "environment": "honeypot",
        "request_id": "hp-test-1",
    }
    payload.update(overrides)
    return payload


def install_route_db(monkeypatch, postgres_db):
    conn, _cur = postgres_db
    import routes.ingest_routes as ingest_routes

    monkeypatch.setattr(ingest_routes, "get_db_connection", lambda: ConnectionProxy(conn))
    monkeypatch.setattr(ingest_routes, "lookup_ip_location", lambda _ip: {})
    monkeypatch.setattr(ingest_routes, "enqueue_committed_alerts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(ingest_routes, "_create_incidents_for_alerts", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        ingest_routes,
        "create_pending_executions_for_committed_alerts",
        lambda *_args, **_kwargs: {"summary": {"created": 0}, "results": []},
    )


def fetch_event(cur, source_ip):
    cur.execute(
        """
        SELECT
            event_type,
            severity,
            host(source_ip),
            source,
            source_type,
            event_timestamp::text,
            message,
            app_name,
            environment,
            raw_payload
        FROM events
        WHERE source_ip = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (source_ip,),
    )
    return cur.fetchone()


def fetch_alert(cur, source_ip):
    cur.execute(
        """
        SELECT
            alert_type,
            host(source_ip),
            country,
            city,
            latitude,
            longitude
        FROM alerts
        WHERE source_ip = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (source_ip,),
    )
    return cur.fetchone()


def post_honeypot(client, payload, api_key=VALID_API_KEY):
    headers = {"X-API-Key": api_key} if api_key is not None else {}
    return client.post("/ingest/honeypot", json=payload, headers=headers)


def test_honeypot_ingest_requires_api_key(client, monkeypatch):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)

    missing = post_honeypot(client, honeypot_payload(), api_key=None)
    wrong = post_honeypot(client, honeypot_payload(), api_key="wrong-key")

    assert missing.status_code == 401
    assert wrong.status_code == 401


def test_valid_env_probe_is_accepted_and_stored_with_honeypot_source(client, monkeypatch, postgres_db):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)
    install_route_db(monkeypatch, postgres_db)
    _conn, cur = postgres_db
    source_ip = "203.0.113.81"

    response = post_honeypot(client, honeypot_payload(source_ip=source_ip))

    assert response.status_code == 201
    assert response.get_json()["message"] == "Honeypot event ingested successfully"
    event = fetch_event(cur, source_ip)
    assert event[0] == "env_probe"
    assert event[1] == "high"
    assert event[2] == source_ip
    assert event[3] == "honeypot"
    assert event[4] == "honeypot"
    assert event[7] == "flask_honeypot"
    assert event[8] == "honeypot"


def test_honeypot_ingest_adds_lookup_location_to_raw_payload(client, monkeypatch, postgres_db):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)
    install_route_db(monkeypatch, postgres_db)
    import routes.ingest_routes as ingest_routes

    monkeypatch.setattr(
        ingest_routes,
        "lookup_ip_location",
        lambda _ip: {
            "country": "Netherlands",
            "city": "Amsterdam",
            "lat": 52.3676,
            "lon": 4.9041,
        },
    )
    _conn, cur = postgres_db
    source_ip = "203.0.113.87"

    response = post_honeypot(client, honeypot_payload(source_ip=source_ip))

    assert response.status_code == 201
    raw_payload = fetch_event(cur, source_ip)[9]
    assert raw_payload["location"] == {
        "country": "Netherlands",
        "city": "Amsterdam",
        "lat": 52.3676,
        "lon": 4.9041,
    }


def test_honeypot_alert_uses_ingested_location(client, monkeypatch, postgres_db):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)
    install_route_db(monkeypatch, postgres_db)
    import engines.detection_engine as detection_engine
    import routes.ingest_routes as ingest_routes

    monkeypatch.setattr(detection_engine, "lookup_ip_reputation", lambda _ip: REPUTATION)
    monkeypatch.setattr(
        ingest_routes,
        "lookup_ip_location",
        lambda _ip: {
            "country": "Germany",
            "city": "Frankfurt am Main",
            "lat": 50.1109,
            "lon": 8.6821,
        },
    )
    _conn, cur = postgres_db
    source_ip = "203.0.113.88"

    response = post_honeypot(
        client,
        honeypot_payload(event_type="scanner_detected", source_ip=source_ip),
    )

    assert response.status_code == 201
    alert = fetch_alert(cur, source_ip)
    assert alert[0] == "honeypot_scanner_detected"
    assert alert[2] == "Germany"
    assert alert[3] == "Frankfurt am Main"
    assert alert[4] == 50.1109
    assert alert[5] == 8.6821


@pytest.mark.parametrize(
    "event_type,extra",
    [
        ("admin_probe", {"path": "/admin"}),
        ("scanner_detected", {"scanner_signature": "nikto", "user_agent": "Nikto/2.1.6"}),
        (
            "credential_stuffing",
            {"username": "alice", "password_length": 12, "credential_present": True},
        ),
        ("http_error", {"path": "/missing", "status_code": 404}),
    ],
)
def test_supported_honeypot_event_types_are_accepted(client, monkeypatch, postgres_db, event_type, extra):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)
    install_route_db(monkeypatch, postgres_db)
    _conn, cur = postgres_db
    source_ip = f"203.0.113.{90 + len(event_type)}"

    response = post_honeypot(
        client,
        honeypot_payload(event_type=event_type, source_ip=source_ip, **extra),
    )

    assert response.status_code == 201
    event = fetch_event(cur, source_ip)
    assert event[0] == event_type
    assert event[3] == "honeypot"
    assert event[4] == "honeypot"


@pytest.mark.parametrize(
    "payload,expected_error",
    [
        ({}, "Missing required fields"),
        ({"event_type": "env_probe"}, "Missing required fields"),
        ({"event_type": "env_probe", "source_ip": "not-an-ip"}, "Invalid source_ip"),
        ({"event_type": "unknown", "source_ip": "203.0.113.82"}, "Invalid event_type"),
    ],
)
def test_invalid_honeypot_payloads_are_rejected(client, monkeypatch, payload, expected_error):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)

    response = post_honeypot(client, payload)

    assert response.status_code == 400
    assert response.get_json()["error"] == expected_error


@pytest.mark.parametrize(
    "payload_update",
    [
        {"password": "secret123"},
        {"passwd": "secret123"},
        {"pwd": "secret123"},
        {"user_password": "secret123"},
        {"raw_payload": {"password": "secret123"}},
        {"nested": {"credentials": {"pwd": "secret123"}}},
    ],
)
def test_raw_password_fields_are_rejected_without_echoing_values(client, monkeypatch, payload_update):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)

    response = post_honeypot(client, honeypot_payload(event_type="credential_stuffing", **payload_update))

    assert response.status_code == 400
    body = response.get_json()
    assert "Raw password field" in body["error"]
    assert "secret123" not in body["error"]


def test_timestamp_maps_to_event_timestamp(client, monkeypatch, postgres_db):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)
    install_route_db(monkeypatch, postgres_db)
    _conn, cur = postgres_db
    source_ip = "203.0.113.83"

    response = post_honeypot(
        client,
        honeypot_payload(source_ip=source_ip, timestamp="2026-06-23T18:45:12"),
    )

    assert response.status_code == 201
    event = fetch_event(cur, source_ip)
    assert event[5].startswith("2026-06-23 18:45:12")


def test_raw_payload_preserves_safe_and_future_metadata(client, monkeypatch, postgres_db):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)
    install_route_db(monkeypatch, postgres_db)
    _conn, cur = postgres_db
    source_ip = "203.0.113.84"

    response = post_honeypot(
        client,
        honeypot_payload(
            event_type="credential_stuffing",
            source_ip=source_ip,
            username="alice",
            password_length=14,
            credential_present=True,
            scanner_signature="custom-scanner",
            future_signal={"confidence": 0.95},
        ),
    )

    assert response.status_code == 201
    raw_payload = fetch_event(cur, source_ip)[9]
    assert raw_payload["path"] == "/.env"
    assert raw_payload["method"] == "GET"
    assert raw_payload["user_agent"] == "curl/8.0"
    assert raw_payload["username"] == "alice"
    assert raw_payload["password_length"] == 14
    assert raw_payload["credential_present"] is True
    assert raw_payload["scanner_signature"] == "custom-scanner"
    assert raw_payload["future_signal"] == {"confidence": 0.95}
    assert "password" not in raw_payload


def test_adapter_ingested_events_trigger_detection_alerts(client, monkeypatch, postgres_db):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)
    install_route_db(monkeypatch, postgres_db)
    import engines.detection_engine as detection_engine

    monkeypatch.setattr(detection_engine, "lookup_ip_reputation", lambda _ip: REPUTATION)
    source_ip = "203.0.113.85"

    for path in ("/.env", "/.env.local", "/config.php"):
        response = post_honeypot(
            client,
            honeypot_payload(source_ip=source_ip, path=path),
        )
        assert response.status_code == 201

    body = response.get_json()
    assert len(body["alerts_created"]) == 1
    assert body["alerts_created"][0]["alert_id"] is not None
    assert body["alerts_created"][0]["source_ip"] == source_ip
    assert body["alerts_created"][0]["response_action"] == "flag_high_priority"
    assert body["alerts_created"][0]["severity"] == "high"


def test_alerts_created_soar_handoff_shape_is_preserved(client, monkeypatch):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)
    import routes.ingest_routes as ingest_routes

    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    alerts_created = [
        {
            "alert_id": 456,
            "source_ip": "203.0.113.86",
            "response_action": "monitor",
            "severity": "medium",
        }
    ]

    monkeypatch.setattr(ingest_routes, "get_db_connection", lambda: conn)
    monkeypatch.setattr(ingest_routes, "ingest_normalized_event", lambda *_args, **_kwargs: alerts_created)
    enqueue_mock = MagicMock(return_value=[])
    playbook_mock = MagicMock(return_value={"summary": {"created": 0}, "results": []})
    monkeypatch.setattr(ingest_routes, "enqueue_committed_alerts", enqueue_mock)
    monkeypatch.setattr(ingest_routes, "_create_incidents_for_alerts", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ingest_routes, "create_pending_executions_for_committed_alerts", playbook_mock)

    response = post_honeypot(client, honeypot_payload(event_type="scanner_detected"))

    assert response.status_code == 201
    assert response.get_json()["alerts_created"] == alerts_created
    enqueue_mock.assert_called_once_with(alerts_created, conn)
    playbook_mock.assert_called_once_with(alerts_created, conn)
