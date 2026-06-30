"""
Read-only incident metrics API (GET /metrics/incidents).
"""

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

from routes.metrics_routes import KNOWN_APPROVAL_STATUSES, KNOWN_INCIDENT_SEVERITIES, KNOWN_INCIDENT_STATUSES


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
def _patched_metrics_db(conn):
    wrapper = _RouteSafeConnection(conn)
    with patch("routes.metrics_routes.get_db_connection", return_value=wrapper), patch(
        "core.audit_helpers.get_db_connection", return_value=wrapper
    ):
        yield


@contextmanager
def _patched_fake_user(username, password, role):
    fake = {
        "username": username,
        "password_hash": generate_password_hash(password, method="pbkdf2:sha256"),
        "role": role,
        "is_active": True,
    }
    with patch("routes.auth_routes.get_user_by_username", return_value=fake), patch(
        "core.auth.get_user_by_username", return_value=fake
    ):
        yield


def _insert_incident(cur, *, title, severity, status="open", age="1 hour"):
    cur.execute(
        """
        INSERT INTO incidents (title, severity, priority, status, created_at)
        VALUES (%s, %s, 'P2', %s, NOW() - (%s::interval))
        RETURNING id
        """,
        (title, severity, status, age),
    )
    return cur.fetchone()[0]


def _insert_approval(cur, *, status="pending", age="1 hour"):
    incident_id = _insert_incident(cur, title=f"Approval target {status} {age}", severity="HIGH")
    approved_by = None
    if status == "approved":
        cur.execute(
            """
            INSERT INTO users (username, password_hash, role)
            VALUES (%s, 'test-hash', 'analyst')
            RETURNING id
            """,
            (f"approval_actor_{age.replace(' ', '_')}",),
        )
        approved_by = cur.fetchone()[0]
    cur.execute(
        """
        INSERT INTO approval_requests (incident_id, status, action, approved_by, created_at, decided_at, expires_at)
        VALUES (%s, %s, 'playbook.require_approval', %s, NOW() - (%s::interval),
                CASE WHEN %s = 'pending' THEN NULL ELSE NOW() END,
                NOW() + INTERVAL '1 hour')
        RETURNING id
        """,
        (incident_id, status, approved_by, age, status),
    )
    return cur.fetchone()[0]


def test_incident_metrics_without_session_returns_401(client):
    assert client.get("/metrics/incidents").status_code == 401


def test_incident_metrics_viewer_forbidden(client, mock_db):
    with _patched_fake_user("incident_metrics_viewer", "vpass", "viewer"):
        assert client.post("/login", json={"username": "incident_metrics_viewer", "password": "vpass"}).status_code == 200
        resp = client.get("/metrics/incidents")
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "forbidden"


@pytest.mark.usefixtures("postgres_db")
def test_incident_metrics_analyst_allowed_empty(client, postgres_db):
    conn, _cur = postgres_db
    with _patched_fake_user("incident_metrics_analyst", "apass", "analyst"):
        assert client.post("/login", json={"username": "incident_metrics_analyst", "password": "apass"}).status_code == 200
        with _patched_metrics_db(conn):
            resp = client.get("/metrics/incidents")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total_count"] == 0
    assert set(body["by_status"].keys()) == set(KNOWN_INCIDENT_STATUSES)
    assert set(body["by_severity"].keys()) == set(KNOWN_INCIDENT_SEVERITIES)


@pytest.mark.usefixtures("postgres_db")
def test_incident_metrics_super_admin_allowed_empty(client, postgres_db):
    conn, _cur = postgres_db
    with _patched_fake_user("incident_metrics_admin", "spass", "super_admin"):
        assert client.post("/login", json={"username": "incident_metrics_admin", "password": "spass"}).status_code == 200
        with _patched_metrics_db(conn):
            resp = client.get("/metrics/incidents")
    assert resp.status_code == 200


@pytest.mark.usefixtures("postgres_db")
def test_incident_metrics_empty_database_all_zero_buckets(client, postgres_db):
    conn, _cur = postgres_db
    with _patched_fake_user("incident_metrics_empty", "epass", "analyst"):
        assert client.post("/login", json={"username": "incident_metrics_empty", "password": "epass"}).status_code == 200
        with _patched_metrics_db(conn):
            resp = client.get("/metrics/incidents")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total_count"] == 0
    assert data["total"] == 0
    assert data["open_count"] == 0
    assert data["open_high_critical_count"] == 0
    assert data["open_high_critical"] == 0
    assert data["newest_incident_at"] is None
    assert data["oldest_open_incident_at"] is None
    for status in KNOWN_INCIDENT_STATUSES:
        assert data["by_status"][status] == 0
    for severity in KNOWN_INCIDENT_SEVERITIES:
        assert data["by_severity"][severity] == 0
    assert data["canonical_outcome_counts"]["execution_mode"]["simulation"] == 0
    assert data["canonical_outcome_counts"]["tracking_recorded"]["true"] == 0


@pytest.mark.usefixtures("postgres_db")
def test_incident_metrics_aggregates_status_severity_and_open_high_critical(client, postgres_db):
    conn, cur = postgres_db
    _insert_incident(cur, title="Open critical", severity="CRITICAL", status="open", age="5 hours")
    _insert_incident(cur, title="Open high", severity="HIGH", status="open", age="4 hours")
    _insert_incident(cur, title="Open lowercase high", severity="high", status="open", age="3 hours")
    _insert_incident(cur, title="Investigating high", severity="HIGH", status="investigating", age="2 hours")
    _insert_incident(cur, title="Investigating medium", severity="MEDIUM", status="investigating", age="90 minutes")
    _insert_incident(cur, title="Resolved low", severity="LOW", status="resolved", age="1 hour")
    _insert_incident(cur, title="Closed critical", severity="CRITICAL", status="closed", age="30 minutes")
    conn.commit()

    with _patched_fake_user("incident_metrics_counts", "cpass", "analyst"):
        assert client.post("/login", json={"username": "incident_metrics_counts", "password": "cpass"}).status_code == 200
        with _patched_metrics_db(conn):
            resp = client.get("/metrics/incidents")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total_count"] == 7
    assert data["total"] == 7
    assert data["open_count"] == 3
    assert data["by_status"] == {
        "open": 3,
        "investigating": 2,
        "resolved": 1,
        "closed": 1,
    }
    assert data["by_severity"] == {
        "CRITICAL": 2,
        "HIGH": 3,
        "MEDIUM": 1,
        "LOW": 1,
    }
    assert data["open_high_critical_count"] == 4
    assert data["open_high_critical"] == 4
    assert data["newest_incident_at"] is not None
    assert data["oldest_open_incident_at"] is not None


def test_approval_metrics_without_session_returns_401(client):
    assert client.get("/metrics/approvals").status_code == 401


def test_approval_metrics_viewer_forbidden(client, mock_db):
    with _patched_fake_user("approval_metrics_viewer", "vpass", "viewer"):
        assert client.post("/login", json={"username": "approval_metrics_viewer", "password": "vpass"}).status_code == 200
        resp = client.get("/metrics/approvals")
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "forbidden"


@pytest.mark.usefixtures("postgres_db")
def test_approval_metrics_analyst_allowed_empty(client, postgres_db):
    conn, _cur = postgres_db
    with _patched_fake_user("approval_metrics_analyst", "apass", "analyst"):
        assert client.post("/login", json={"username": "approval_metrics_analyst", "password": "apass"}).status_code == 200
        with _patched_metrics_db(conn):
            resp = client.get("/metrics/approvals")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total_count"] == 0
    assert set(body["by_status"].keys()) == set(KNOWN_APPROVAL_STATUSES)


@pytest.mark.usefixtures("postgres_db")
def test_approval_metrics_super_admin_allowed_empty(client, postgres_db):
    conn, _cur = postgres_db
    with _patched_fake_user("approval_metrics_admin", "spass", "super_admin"):
        assert client.post("/login", json={"username": "approval_metrics_admin", "password": "spass"}).status_code == 200
        with _patched_metrics_db(conn):
            resp = client.get("/metrics/approvals")
    assert resp.status_code == 200


@pytest.mark.usefixtures("postgres_db")
def test_approval_metrics_empty_database_all_zero_buckets(client, postgres_db):
    conn, _cur = postgres_db
    with _patched_fake_user("approval_metrics_empty", "epass", "analyst"):
        assert client.post("/login", json={"username": "approval_metrics_empty", "password": "epass"}).status_code == 200
        with _patched_metrics_db(conn):
            resp = client.get("/metrics/approvals")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total_count"] == 0
    assert data["total"] == 0
    assert data["pending_count"] == 0
    assert data["newest_approval_at"] is None
    assert data["oldest_pending_approval_at"] is None
    for status in KNOWN_APPROVAL_STATUSES:
        assert data["by_status"][status] == 0
    assert data["canonical_outcome_counts"]["execution_state"]["succeeded"] == 0
    assert data["canonical_outcome_counts"]["simulated"]["true"] == 0


@pytest.mark.usefixtures("postgres_db")
def test_approval_metrics_aggregates_status_and_oldest_pending(client, postgres_db):
    conn, cur = postgres_db
    oldest_pending_id = _insert_approval(cur, status="pending", age="5 hours")
    newest_pending_id = _insert_approval(cur, status="pending", age="1 hour")
    _insert_approval(cur, status="approved", age="4 hours")
    _insert_approval(cur, status="denied", age="3 hours")
    _insert_approval(cur, status="expired", age="2 hours")
    conn.commit()

    cur.execute("SELECT created_at FROM approval_requests WHERE id = %s", (oldest_pending_id,))
    oldest_pending_created_at = cur.fetchone()[0].isoformat()
    cur.execute("SELECT created_at FROM approval_requests WHERE id = %s", (newest_pending_id,))
    newest_approval_created_at = cur.fetchone()[0].isoformat()

    with _patched_fake_user("approval_metrics_counts", "cpass", "analyst"):
        assert client.post("/login", json={"username": "approval_metrics_counts", "password": "cpass"}).status_code == 200
        with _patched_metrics_db(conn):
            resp = client.get("/metrics/approvals")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total_count"] == 5
    assert data["total"] == 5
    assert data["pending_count"] == 2
    assert data["by_status"] == {
        "pending": 2,
        "approved": 1,
        "denied": 1,
        "expired": 1,
    }
    assert data["oldest_pending_approval_at"] == oldest_pending_created_at
    assert data["newest_approval_at"] == newest_approval_created_at
