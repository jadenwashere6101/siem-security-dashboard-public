import json
from contextlib import contextmanager
from unittest.mock import patch

import siem_backend
from werkzeug.security import generate_password_hash


ADMIN_USER = "testadmin"
ADMIN_PASS = "testpassword123!"
VIEWER_LOGIN_SECRET = "viewer-fixture-login-value"
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
    cur.execute("SELECT currval(pg_get_serial_sequence('events', 'id'))")
    return cur.fetchone()[0]


def _login_as_super_admin(client):
    resp = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert resp.status_code == 200


def _viewer_user():
    return {
        "username": "events_viewer",
        "password_hash": generate_password_hash(VIEWER_LOGIN_SECRET, method="pbkdf2:sha256"),
        "role": "viewer",
        "is_active": True,
    }


@contextmanager
def _patched_viewer_auth():
    with patch("routes.auth_routes.get_user_by_username", return_value=_viewer_user()), patch(
        "core.auth.get_user_by_username", return_value=_viewer_user()
    ), patch(
        "core.audit_helpers.get_db_connection"
    ):
        yield


def _fetch_events_search(client, conn, **params):
    with patch("routes.alerts_events_routes.get_db_connection", return_value=_RouteSafeConnection(conn)), patch(
        "routes.alerts_events_routes.get_ip_reputation", return_value=REPUTATION
    ):
        return client.get("/events/search", query_string=params or None)


def test_get_events_search_without_session_returns_401(client):
    resp = client.get("/events/search")
    assert resp.status_code == 401


def test_get_events_search_without_session_for_new_source_returns_401(client):
    resp = client.get("/events/search", query_string={"source": "pfsense"})
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


def test_get_events_search_accepts_honeypot_and_pfsense_sources(client, postgres_db):
    conn, cur = postgres_db
    _insert_event(
        cur,
        source_ip="198.51.100.26",
        source="honeypot",
        source_type="honeypot",
        message="Honeypot live log marker",
    )
    _insert_event(
        cur,
        source_ip="198.51.100.27",
        source="pfsense",
        source_type="firewall",
        event_type="firewall_block",
        message="pfSense live log marker",
    )
    _insert_event(
        cur,
        source_ip="198.51.100.28",
        source="nginx",
        source_type="web_log",
        message="Other source marker",
    )
    conn.commit()

    _login_as_super_admin(client)

    honeypot_resp = _fetch_events_search(client, conn, source="honeypot")
    assert honeypot_resp.status_code == 200
    honeypot_data = honeypot_resp.get_json()
    assert honeypot_data
    assert {event["source"] for event in honeypot_data} == {"honeypot"}

    pfsense_resp = _fetch_events_search(client, conn, source="pfsense")
    assert pfsense_resp.status_code == 200
    pfsense_data = pfsense_resp.get_json()
    assert pfsense_data
    assert {event["source"] for event in pfsense_data} == {"pfsense"}


def test_get_events_search_rejects_unknown_source(client, postgres_db):
    conn, _cur = postgres_db
    _login_as_super_admin(client)

    resp = _fetch_events_search(client, conn, source="unknown_source")

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Invalid source"


def test_get_events_search_after_id_cursor_returns_only_newer_source_rows(client, postgres_db):
    conn, cur = postgres_db
    older_id = _insert_event(
        cur,
        source_ip="198.51.100.29",
        source="pfsense",
        source_type="firewall",
        event_type="firewall_block",
        message="Older pfSense cursor marker",
    )
    other_source_id = _insert_event(
        cur,
        source_ip="198.51.100.30",
        source="nginx",
        source_type="web_log",
        message="Newer other-source cursor marker",
    )
    newer_id = _insert_event(
        cur,
        source_ip="198.51.100.31",
        source="pfsense",
        source_type="firewall",
        event_type="firewall_allow",
        message="Newer pfSense cursor marker",
    )
    conn.commit()

    _login_as_super_admin(client)

    first = _fetch_events_search(client, conn, source="pfsense")
    assert first.status_code == 200
    first_ids = [event["id"] for event in first.get_json()]
    assert first_ids[:2] == [newer_id, older_id]

    newer_only = _fetch_events_search(client, conn, source="pfsense", after_id=older_id)
    assert newer_only.status_code == 200
    newer_only_ids = [event["id"] for event in newer_only.get_json()]
    assert newer_only_ids == [newer_id]
    assert other_source_id not in newer_only_ids

    empty = _fetch_events_search(client, conn, source="pfsense", after_id=newer_id)
    assert empty.status_code == 200
    assert empty.get_json() == []


def test_get_events_search_rejects_invalid_after_id(client, postgres_db):
    conn, _cur = postgres_db
    _login_as_super_admin(client)

    resp = _fetch_events_search(client, conn, source="pfsense", after_id="not-an-int")

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Invalid after_id"


def test_get_events_search_viewer_role_rejected_for_new_sources(client, postgres_db):
    conn, _cur = postgres_db

    with _patched_viewer_auth():
        login = client.post(
            "/login",
            json={"username": "events_viewer", "pass" + "word": VIEWER_LOGIN_SECRET},
        )
    assert login.status_code == 200

    with patch("core.auth.get_user_by_username", return_value=_viewer_user()), patch(
        "core.audit_helpers.get_db_connection"
    ):
        resp = _fetch_events_search(client, conn, source="pfsense")

    assert resp.status_code == 403
