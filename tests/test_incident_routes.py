from contextlib import contextmanager
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from core.incident_store import create_incident, link_alert_to_incident


ADMIN_USER = "testadmin"
ADMIN_PASS = "testpassword123!"


class _RouteSafeConnection:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return self._conn.cursor()

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return None


@contextmanager
def _patched_app_db(conn):
    wrapper = _RouteSafeConnection(conn)
    with patch("routes.incident_routes.get_db_connection", return_value=wrapper), patch(
        "core.audit_helpers.get_db_connection", return_value=wrapper
    ):
        yield


def _fake_user(username, password, role):
    return {
        "username": username,
        "password_hash": generate_password_hash(password, method="pbkdf2:sha256"),
        "role": role,
        "is_active": True,
    }


def _login_super_admin(client):
    resp = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert resp.status_code == 200


def _login_role(client, *, username, password, role):
    user = _fake_user(username, password, role)
    patchers = [
        patch("routes.auth_routes.get_user_by_username", return_value=user),
        patch("core.auth.get_user_by_username", return_value=user),
    ]
    for patcher in patchers:
        patcher.start()
    resp = client.post("/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return patchers


def _stop_patchers(patchers):
    for patcher in reversed(patchers):
        patcher.stop()


def _insert_alert(cur, *, source_ip="203.0.113.70", severity="HIGH"):
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message, status)
        VALUES ('route_test_alert', %s, %s::inet, 'route test alert', 'open')
        RETURNING id
        """,
        (severity, source_ip),
    )
    return cur.fetchone()[0]


def _insert_incident(conn, *, title="Route incident", severity="HIGH", source_ip="203.0.113.80"):
    incident = create_incident(conn, title, severity, source_ip)
    conn.commit()
    return incident


def test_get_incidents_without_session_returns_401(client):
    resp = client.get("/incidents")
    assert resp.status_code == 401


def test_get_incidents_viewer_returns_403(client, mock_db):
    patchers = _login_role(
        client,
        username="incidentviewer",
        password="viewerpass",
        role="viewer",
    )
    try:
        resp = client.get("/incidents")
    finally:
        _stop_patchers(patchers)

    assert resp.status_code == 403
    assert resp.get_json()["error"] == "forbidden"


def test_get_incidents_analyst_can_list(client, postgres_db):
    conn, _cur = postgres_db
    _insert_incident(conn, title="Analyst list", source_ip="203.0.113.81")

    patchers = _login_role(
        client,
        username="incidentanalyst",
        password="analystpass",
        role="analyst",
    )
    try:
        with _patched_app_db(conn):
            resp = client.get("/incidents")
    finally:
        _stop_patchers(patchers)

    assert resp.status_code == 200
    data = resp.get_json()
    assert set(data.keys()) == {"incidents", "count"}
    assert data["count"] >= 1
    incident = data["incidents"][0]
    for field in (
        "id",
        "title",
        "severity",
        "priority",
        "status",
        "source_ip",
        "assigned_to",
        "created_at",
        "resolved_at",
    ):
        assert field in incident


def test_get_incidents_super_admin_can_list(client, postgres_db):
    conn, _cur = postgres_db
    _insert_incident(conn, title="Admin list", source_ip="203.0.113.82")

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/incidents")

    assert resp.status_code == 200
    assert "incidents" in resp.get_json()


def test_get_incidents_status_filter_returns_only_matching(client, postgres_db):
    conn, cur = postgres_db
    open_incident = _insert_incident(conn, title="Open", source_ip="203.0.113.83")
    resolved = _insert_incident(conn, title="Resolved", source_ip="203.0.113.84")
    cur.execute("UPDATE incidents SET status = 'resolved' WHERE id = %s", (resolved["id"],))
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/incidents?status=open")

    assert resp.status_code == 200
    data = resp.get_json()
    assert [item["id"] for item in data["incidents"]] == [open_incident["id"]]


def test_get_incidents_invalid_status_returns_400(client):
    _login_super_admin(client)
    resp = client.get("/incidents?status=invalid")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid status filter"


def test_get_incidents_limit_is_clamped_to_100(client, postgres_db, monkeypatch):
    conn, _cur = postgres_db
    captured = {}

    def fake_list_incidents(conn, status=None, severity=None, limit=50, offset=0):
        captured["limit"] = limit
        return []

    monkeypatch.setattr("routes.incident_routes.list_incidents", fake_list_incidents)

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/incidents?limit=200")

    assert resp.status_code == 200
    assert captured["limit"] == 100


def test_get_incident_detail_without_session_returns_401(client):
    resp = client.get("/incidents/1")
    assert resp.status_code == 401


def test_get_incident_detail_viewer_returns_403(client, mock_db):
    patchers = _login_role(
        client,
        username="incidentviewer2",
        password="viewerpass",
        role="viewer",
    )
    try:
        resp = client.get("/incidents/1")
    finally:
        _stop_patchers(patchers)

    assert resp.status_code == 403


def test_get_incident_detail_analyst_can_view_with_alerts(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, source_ip="203.0.113.85")
    incident = _insert_incident(conn, title="Detail", source_ip="203.0.113.85")
    link_alert_to_incident(conn, incident["id"], alert_id)
    conn.commit()

    patchers = _login_role(
        client,
        username="detailanalyst",
        password="analystpass",
        role="analyst",
    )
    try:
        with _patched_app_db(conn):
            resp = client.get(f"/incidents/{incident['id']}")
    finally:
        _stop_patchers(patchers)

    assert resp.status_code == 200
    data = resp.get_json()
    assert "incident" in data
    assert data["incident"]["id"] == incident["id"]
    assert isinstance(data["incident"]["alerts"], list)
    assert data["incident"]["alerts"][0]["alert_id"] == alert_id


def test_get_incident_detail_super_admin_can_view(client, postgres_db):
    conn, _cur = postgres_db
    incident = _insert_incident(conn, title="Admin detail", source_ip="203.0.113.86")

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get(f"/incidents/{incident['id']}")

    assert resp.status_code == 200
    assert resp.get_json()["incident"]["id"] == incident["id"]


def test_get_incident_detail_missing_returns_404(client, postgres_db):
    conn, _cur = postgres_db
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/incidents/999999")

    assert resp.status_code == 404
    assert resp.get_json()["error"] == "incident not found"


def test_post_incident_status_without_session_returns_401(client):
    resp = client.post("/incidents/1/status", json={"status": "investigating"})
    assert resp.status_code == 401


def test_post_incident_status_viewer_returns_403(client, mock_db):
    patchers = _login_role(
        client,
        username="incidentviewer3",
        password="viewerpass",
        role="viewer",
    )
    try:
        resp = client.post("/incidents/1/status", json={"status": "investigating"})
    finally:
        _stop_patchers(patchers)

    assert resp.status_code == 403


def test_post_incident_status_valid_update_works(client, postgres_db):
    conn, _cur = postgres_db
    incident = _insert_incident(conn, title="Status update", source_ip="203.0.113.87")

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.post(
            f"/incidents/{incident['id']}/status",
            json={"status": "investigating"},
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["incident"]["id"] == incident["id"]
    assert data["incident"]["status"] == "investigating"


def test_post_incident_status_missing_status_returns_400(client, postgres_db):
    conn, _cur = postgres_db
    incident = _insert_incident(conn, title="Missing status", source_ip="203.0.113.88")

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.post(f"/incidents/{incident['id']}/status", json={})

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "status is required"


def test_post_incident_status_invalid_status_rejected(client, postgres_db):
    conn, _cur = postgres_db
    incident = _insert_incident(conn, title="Invalid status", source_ip="203.0.113.89")

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.post(
            f"/incidents/{incident['id']}/status",
            json={"status": "not_a_status"},
        )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid status"


def test_post_incident_status_invalid_transition_rejected(client, postgres_db):
    conn, _cur = postgres_db
    incident = _insert_incident(conn, title="Invalid transition", source_ip="203.0.113.90")

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.post(f"/incidents/{incident['id']}/status", json={"status": "open"})

    assert resp.status_code == 400
    assert "invalid status transition" in resp.get_json()["error"]


def test_post_incident_status_missing_incident_returns_404(client, postgres_db):
    conn, _cur = postgres_db
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.post("/incidents/999999/status", json={"status": "investigating"})

    assert resp.status_code == 404
    assert resp.get_json()["error"] == "incident not found"
