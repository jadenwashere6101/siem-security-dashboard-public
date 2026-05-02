import json
from unittest.mock import patch

import siem_backend


ADMIN_USER = "testadmin"
ADMIN_PASS = "testpassword123!"
REPUTATION = {
    "reputation_score": 0,
    "reputation_label": "low-risk",
    "reputation_summary": "Contract test reputation",
    "contributing_signals": [],
}

REQUIRED_EVENT_FIELDS = (
    "id",
    "event_type",
    "severity",
    "source_ip",
    "message",
    "app_name",
    "environment",
    "source",
    "source_type",
    "raw_payload",
    "created_at",
    "reputation_score",
    "reputation_label",
    "reputation_summary",
    "contributing_signals",
)


class _RouteSafeConnection:
    """Wraps postgres_db connection; ignores close() so the fixture-owned conn stays alive."""

    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return self._conn.cursor()

    def close(self):
        return None


def _insert_event(
    cur,
    *,
    event_type="failed_login",
    severity="medium",
    source_ip="198.51.100.10",
    source="bank_app",
    source_type="custom",
    message="Test event",
    app_name="test_app",
    environment="dev",
    raw_payload=None,
):
    cur.execute(
        """
        INSERT INTO events (
            event_type, severity, source_ip, source, source_type,
            message, app_name, environment, raw_payload
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            event_type,
            severity,
            source_ip,
            source,
            source_type,
            message,
            app_name,
            environment,
            json.dumps(raw_payload if raw_payload is not None else {}),
        ),
    )


def _login_as_super_admin(client):
    resp = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert resp.status_code == 200


def _fetch_events_search(client, conn, **params):
    with patch("backend_alerts_events_routes.get_db_connection", return_value=_RouteSafeConnection(conn)), patch(
        "backend_alerts_events_routes.get_ip_reputation", return_value=REPUTATION
    ):
        return client.get("/events/search", query_string=params or None)


def test_get_events_search_without_session_returns_401(client):
    resp = client.get("/events/search")
    assert resp.status_code == 401


def test_get_events_search_as_super_admin_returns_200(client, postgres_db):
    conn, cur = postgres_db
    _insert_event(cur, source_ip="198.51.100.20", message="Auth contract test event")
    conn.commit()

    _login_as_super_admin(client)
    resp = _fetch_events_search(client, conn)

    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)


def test_get_events_search_response_shape_is_stable(client, postgres_db):
    conn, cur = postgres_db
    _insert_event(cur, source_ip="198.51.100.21", message="Shape contract test event")
    conn.commit()

    _login_as_super_admin(client)
    resp = _fetch_events_search(client, conn)

    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) >= 1

    event = data[0]
    for field in REQUIRED_EVENT_FIELDS:
        assert field in event, f"Missing required field in /events/search response: {field}"


def test_get_events_search_seeded_event_appears_with_correct_fields(client, postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.22"
    message = "Seeded events search contract marker"
    _insert_event(
        cur,
        source_ip=source_ip,
        event_type="failed_login",
        severity="high",
        message=message,
    )
    conn.commit()

    _login_as_super_admin(client)
    resp = _fetch_events_search(client, conn)

    assert resp.status_code == 200
    data = resp.get_json()
    matching = [e for e in data if e.get("source_ip") == source_ip]
    assert matching, f"Expected seeded event with source_ip={source_ip} in response"

    event = matching[0]
    assert event["message"] == message
    assert event["event_type"] == "failed_login"
    assert event["severity"] == "high"
    assert event["reputation_score"] == REPUTATION["reputation_score"]
    assert event["reputation_label"] == REPUTATION["reputation_label"]


def test_get_events_search_filter_by_source_ip_preserves_shape(client, postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.23"
    _insert_event(cur, source_ip=source_ip, message="IP filter shape test event")
    conn.commit()

    _login_as_super_admin(client)
    resp = _fetch_events_search(client, conn, source_ip=source_ip)

    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    for event in data:
        for field in REQUIRED_EVENT_FIELDS:
            assert field in event, f"Missing field after source_ip filter: {field}"


def test_get_events_search_filter_by_event_type_preserves_shape(client, postgres_db):
    conn, cur = postgres_db
    _insert_event(cur, source_ip="198.51.100.24", event_type="port_scan", message="Port scan filter test")
    conn.commit()

    _login_as_super_admin(client)
    resp = _fetch_events_search(client, conn, event_type="port_scan")

    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    for event in data:
        for field in REQUIRED_EVENT_FIELDS:
            assert field in event, f"Missing field after event_type filter: {field}"


def test_get_events_search_filter_by_source_preserves_shape(client, postgres_db):
    conn, cur = postgres_db
    _insert_event(cur, source_ip="198.51.100.25", source="nginx", message="Nginx source filter test")
    conn.commit()

    _login_as_super_admin(client)
    resp = _fetch_events_search(client, conn, source="nginx")

    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    for event in data:
        for field in REQUIRED_EVENT_FIELDS:
            assert field in event, f"Missing field after source filter: {field}"
