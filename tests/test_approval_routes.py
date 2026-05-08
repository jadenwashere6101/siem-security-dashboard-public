from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from core.approval_store import create_approval_request


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
    with patch("routes.approval_routes.get_db_connection", return_value=wrapper), patch(
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


def _insert_incident(cur, source_ip="203.0.114.10"):
    cur.execute(
        """
        INSERT INTO incidents (title, severity, priority, status, source_ip)
        VALUES ('Approval route test incident', 'HIGH', 'P2', 'open', %s::inet)
        RETURNING id
        """,
        (source_ip,),
    )
    return cur.fetchone()[0]


def _insert_admin_db_user(cur):
    """Insert the 'admin' sentinel as a real DB user so actor FK lookups succeed."""
    cur.execute(
        """
        INSERT INTO users (username, password_hash, role)
        VALUES ('admin', 'sentinel_hash', 'super_admin')
        RETURNING id
        """,
    )
    return cur.fetchone()[0]


def _insert_approval(conn, incident_id, *, expires_in_minutes=120):
    future = datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes)
    approval = create_approval_request(
        conn,
        incident_id=incident_id,
        action="block_ip",
        risk_level="high",
        request_reason="route test",
        expires_at=future,
    )
    conn.commit()
    return approval


# ---------------------------------------------------------------------------
# Unauthenticated requests
# ---------------------------------------------------------------------------

def test_list_approvals_unauthenticated_returns_401(client):
    resp = client.get("/approvals")
    assert resp.status_code == 401


def test_get_approval_detail_unauthenticated_returns_401(client):
    resp = client.get("/approvals/1")
    assert resp.status_code == 401


def test_decision_unauthenticated_returns_401(client):
    resp = client.post("/approvals/1/decision", json={"decision": "approved"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Unauthorized roles
# ---------------------------------------------------------------------------

def test_list_approvals_viewer_returns_403(client, mock_db):
    patchers = _login_role(
        client,
        username="approvalviewer1",
        password="viewerpass",
        role="viewer",
    )
    try:
        resp = client.get("/approvals")
    finally:
        _stop_patchers(patchers)
    assert resp.status_code == 403


def test_get_approval_detail_viewer_returns_403(client, mock_db):
    patchers = _login_role(
        client,
        username="approvalviewer2",
        password="viewerpass",
        role="viewer",
    )
    try:
        resp = client.get("/approvals/1")
    finally:
        _stop_patchers(patchers)
    assert resp.status_code == 403


def test_decision_viewer_returns_403(client, mock_db):
    patchers = _login_role(
        client,
        username="approvalviewer3",
        password="viewerpass",
        role="viewer",
    )
    try:
        resp = client.post("/approvals/1/decision", json={"decision": "approved"})
    finally:
        _stop_patchers(patchers)
    assert resp.status_code == 403


def test_decision_analyst_returns_403(client, mock_db):
    patchers = _login_role(
        client,
        username="approvalanalyst1",
        password="analystpass",
        role="analyst",
    )
    try:
        resp = client.post("/approvals/1/decision", json={"decision": "approved"})
    finally:
        _stop_patchers(patchers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Analyst read access
# ---------------------------------------------------------------------------

def test_list_approvals_analyst_can_list(client, postgres_db):
    conn, cur = postgres_db
    incident_id = _insert_incident(cur, source_ip="203.0.114.11")
    conn.commit()
    _insert_approval(conn, incident_id)

    patchers = _login_role(
        client,
        username="applistanalyst",
        password="analystpass",
        role="analyst",
    )
    try:
        with _patched_app_db(conn):
            resp = client.get("/approvals")
    finally:
        _stop_patchers(patchers)

    assert resp.status_code == 200
    data = resp.get_json()
    assert "approvals" in data
    assert "count" in data
    assert data["count"] >= 1


def test_list_approvals_super_admin_can_list(client, postgres_db):
    conn, cur = postgres_db
    incident_id = _insert_incident(cur, source_ip="203.0.114.12")
    conn.commit()
    _insert_approval(conn, incident_id)

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/approvals")

    assert resp.status_code == 200
    assert "approvals" in resp.get_json()


def test_get_approval_detail_analyst_can_view(client, postgres_db):
    conn, cur = postgres_db
    incident_id = _insert_incident(cur, source_ip="203.0.114.13")
    conn.commit()
    approval = _insert_approval(conn, incident_id)

    patchers = _login_role(
        client,
        username="appdetailanalyst",
        password="analystpass",
        role="analyst",
    )
    try:
        with _patched_app_db(conn):
            resp = client.get(f"/approvals/{approval['id']}")
    finally:
        _stop_patchers(patchers)

    assert resp.status_code == 200
    data = resp.get_json()
    assert "approval" in data
    assert data["approval"]["id"] == approval["id"]
    assert isinstance(data["approval"]["events"], list)


def test_get_approval_detail_super_admin_can_view(client, postgres_db):
    conn, cur = postgres_db
    incident_id = _insert_incident(cur, source_ip="203.0.114.14")
    conn.commit()
    approval = _insert_approval(conn, incident_id)

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get(f"/approvals/{approval['id']}")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["approval"]["id"] == approval["id"]


# ---------------------------------------------------------------------------
# Decision route — valid approve
# ---------------------------------------------------------------------------

def test_super_admin_approve_succeeds(client, postgres_db):
    conn, cur = postgres_db
    _insert_admin_db_user(cur)
    incident_id = _insert_incident(cur, source_ip="203.0.114.15")
    conn.commit()
    approval = _insert_approval(conn, incident_id)

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.post(
            f"/approvals/{approval['id']}/decision",
            json={"decision": "approved", "reason": "Looks good"},
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["approval"]["status"] == "approved"
    assert data["approval"]["approved_by"] is not None
    assert data["approval"]["decided_by"] is not None


def test_super_admin_approve_creates_approved_event(client, postgres_db):
    conn, cur = postgres_db
    _insert_admin_db_user(cur)
    incident_id = _insert_incident(cur, source_ip="203.0.114.16")
    conn.commit()
    approval = _insert_approval(conn, incident_id)

    _login_super_admin(client)
    with _patched_app_db(conn):
        client.post(
            f"/approvals/{approval['id']}/decision",
            json={"decision": "approved"},
        )

    cur.execute(
        "SELECT event_type FROM approval_request_events WHERE approval_request_id = %s ORDER BY id",
        (approval["id"],),
    )
    event_types = [row[0] for row in cur.fetchall()]
    assert "approved" in event_types


# ---------------------------------------------------------------------------
# Decision route — valid deny
# ---------------------------------------------------------------------------

def test_super_admin_deny_succeeds(client, postgres_db):
    conn, cur = postgres_db
    _insert_admin_db_user(cur)
    incident_id = _insert_incident(cur, source_ip="203.0.114.17")
    conn.commit()
    approval = _insert_approval(conn, incident_id)

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.post(
            f"/approvals/{approval['id']}/decision",
            json={"decision": "denied", "reason": "Risk too high"},
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["approval"]["status"] == "denied"
    assert data["approval"]["approved_by"] is None
    assert data["approval"]["decided_by"] is not None


def test_super_admin_deny_creates_denied_event(client, postgres_db):
    conn, cur = postgres_db
    _insert_admin_db_user(cur)
    incident_id = _insert_incident(cur, source_ip="203.0.114.18")
    conn.commit()
    approval = _insert_approval(conn, incident_id)

    _login_super_admin(client)
    with _patched_app_db(conn):
        client.post(
            f"/approvals/{approval['id']}/decision",
            json={"decision": "denied"},
        )

    cur.execute(
        "SELECT event_type FROM approval_request_events WHERE approval_request_id = %s ORDER BY id",
        (approval["id"],),
    )
    event_types = [row[0] for row in cur.fetchall()]
    assert "denied" in event_types


# ---------------------------------------------------------------------------
# Decision route — validation errors
# ---------------------------------------------------------------------------

def test_decision_missing_decision_field_returns_400(client, postgres_db):
    conn, cur = postgres_db
    _insert_admin_db_user(cur)
    incident_id = _insert_incident(cur, source_ip="203.0.114.19")
    conn.commit()
    approval = _insert_approval(conn, incident_id)

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.post(f"/approvals/{approval['id']}/decision", json={})

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "decision is required"


def test_decision_invalid_value_returns_400(client, postgres_db):
    conn, cur = postgres_db
    _insert_admin_db_user(cur)
    incident_id = _insert_incident(cur, source_ip="203.0.114.20")
    conn.commit()
    approval = _insert_approval(conn, incident_id)

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.post(
            f"/approvals/{approval['id']}/decision",
            json={"decision": "maybe"},
        )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid decision"


def test_decision_missing_approval_returns_404(client, postgres_db):
    conn, _cur = postgres_db

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.post(
            "/approvals/999999/decision",
            json={"decision": "approved"},
        )

    assert resp.status_code == 404
    assert resp.get_json()["error"] == "approval request not found"


def test_get_approval_detail_missing_returns_404(client, postgres_db):
    conn, _cur = postgres_db

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/approvals/999999")

    assert resp.status_code == 404
    assert resp.get_json()["error"] == "approval not found"


def test_decision_terminal_state_returns_400(client, postgres_db):
    conn, cur = postgres_db
    _insert_admin_db_user(cur)
    incident_id = _insert_incident(cur, source_ip="203.0.114.21")
    conn.commit()
    approval = _insert_approval(conn, incident_id)

    _login_super_admin(client)
    with _patched_app_db(conn):
        client.post(
            f"/approvals/{approval['id']}/decision",
            json={"decision": "approved"},
        )
        resp = client.post(
            f"/approvals/{approval['id']}/decision",
            json={"decision": "denied"},
        )

    assert resp.status_code == 400
    assert "not pending" in resp.get_json()["error"]


# ---------------------------------------------------------------------------
# List filters
# ---------------------------------------------------------------------------

def test_list_approvals_status_filter_returns_only_matching(client, postgres_db):
    conn, cur = postgres_db
    user_id = _insert_admin_db_user(cur)
    incident_id = _insert_incident(cur, source_ip="203.0.114.22")
    conn.commit()
    pending_approval = _insert_approval(conn, incident_id)

    incident_id2 = _insert_incident(cur, source_ip="203.0.114.23")
    conn.commit()
    approved_approval = _insert_approval(conn, incident_id2)
    conn.commit()
    cur.execute(
        """
        UPDATE approval_requests
        SET status = 'approved', approved_by = %s, decided_by = %s,
            decided_at = NOW()
        WHERE id = %s
        """,
        (user_id, user_id, approved_approval["id"]),
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/approvals?status=pending")

    assert resp.status_code == 200
    data = resp.get_json()
    ids = [a["id"] for a in data["approvals"]]
    assert pending_approval["id"] in ids
    assert approved_approval["id"] not in ids


def test_list_approvals_invalid_status_returns_400(client):
    _login_super_admin(client)
    resp = client.get("/approvals?status=unknown")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid status filter"


def test_list_approvals_invalid_limit_returns_400(client):
    _login_super_admin(client)
    resp = client.get("/approvals?limit=notanint")
    assert resp.status_code == 400


def test_list_approvals_limit_clamped_to_100(client, postgres_db, monkeypatch):
    conn, _cur = postgres_db
    captured = {}

    def fake_list(conn, *, status=None, incident_id=None, queue_id=None, limit=50, offset=0):
        captured["limit"] = limit
        return []

    monkeypatch.setattr("routes.approval_routes.list_approval_requests", fake_list)

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/approvals?limit=500")

    assert resp.status_code == 200
    assert captured["limit"] == 100
