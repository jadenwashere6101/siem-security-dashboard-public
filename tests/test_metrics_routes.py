"""
Read-only incident metrics API (GET /metrics/incidents).
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

from core import dead_letter_store, playbook_store
from core.approval_store import create_approval_request
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


def _insert_alert(cur, *, alert_type="metrics_soar", source_ip="198.51.100.10", message="SOAR metrics alert"):
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message, created_at)
        VALUES (%s, 'HIGH', %s::inet, %s, NOW())
        RETURNING id
        """,
        (alert_type, source_ip, message),
    )
    return cur.fetchone()[0]


def _insert_playbook_execution(
    conn,
    cur,
    *,
    playbook_id,
    status,
    alert_id=None,
    created_at=None,
    completed_at=None,
    failure_reason=None,
):
    playbook_store.create_playbook_definition(
        conn,
        playbook_id,
        f"Definition {playbook_id}",
        steps=[{"action": "monitor", "params": {}}],
    )
    cur.execute(
        """
        INSERT INTO playbook_executions (
            playbook_id,
            alert_id,
            status,
            steps_log,
            created_at,
            completed_at,
            failure_reason
        )
        VALUES (%s, %s, %s, '[]'::jsonb, %s, %s, %s)
        RETURNING id
        """,
        (
            playbook_id,
            alert_id,
            status,
            created_at or datetime.now(timezone.utc),
            completed_at,
            failure_reason,
        ),
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


@pytest.mark.usefixtures("postgres_db")
def test_incident_metrics_since_tuning_excludes_legacy_only_pfsense_incidents(client, postgres_db, monkeypatch):
    conn, cur = postgres_db
    monkeypatch.setenv("SIEM_PFSENSE_TUNING_BASELINE", "2026-06-01T00:00:00Z")
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, source, source_type, message, created_at)
        VALUES
          ('pfsense_firewall_repeated_deny', 'HIGH', '198.51.100.60'::inet, 'pfsense', 'firewall', 'legacy', '2026-05-01T00:00:00+00:00'),
          ('pfsense_firewall_port_scan', 'HIGH', '198.51.100.61'::inet, 'pfsense', 'firewall', 'current', '2026-06-15T00:00:00+00:00'),
          ('failed_login_threshold', 'HIGH', '198.51.100.62'::inet, 'bank_app', 'custom', 'other', '2026-05-01T00:00:00+00:00')
        RETURNING id
        """
    )
    legacy_alert_id, current_alert_id, other_alert_id = [row[0] for row in cur.fetchall()]
    legacy_incident_id = _insert_incident(cur, title="Legacy", severity="HIGH", status="open", age="1 hour")
    current_incident_id = _insert_incident(cur, title="Current", severity="HIGH", status="investigating", age="1 hour")
    other_incident_id = _insert_incident(cur, title="Other", severity="MEDIUM", status="open", age="1 hour")
    cur.execute(
        """
        INSERT INTO incident_alerts (incident_id, alert_id)
        VALUES (%s, %s), (%s, %s), (%s, %s)
        """,
        (
            legacy_incident_id,
            legacy_alert_id,
            current_incident_id,
            current_alert_id,
            other_incident_id,
            other_alert_id,
        ),
    )
    conn.commit()

    with _patched_fake_user("incident_metrics_scope", "apass", "analyst"):
        assert client.post("/login", json={"username": "incident_metrics_scope", "password": "apass"}).status_code == 200
        with _patched_metrics_db(conn):
            resp = client.get("/metrics/incidents?operational_scope=since_tuning")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total_count"] == 2
    assert body["by_status"]["open"] == 1
    assert body["by_status"]["investigating"] == 1
    assert body["open_high_critical"] == 1


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


def test_soar_operations_metrics_without_session_returns_401(client):
    assert client.get("/metrics/soar-operations").status_code == 401


def test_soar_operations_metrics_viewer_forbidden(client, mock_db):
    with _patched_fake_user("soar_operations_viewer", "vpass", "viewer"):
        assert client.post("/login", json={"username": "soar_operations_viewer", "password": "vpass"}).status_code == 200
        resp = client.get("/metrics/soar-operations")
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "forbidden"


@pytest.mark.usefixtures("postgres_db")
def test_soar_operations_metrics_empty_state_is_all_zero(client, postgres_db):
    conn, _cur = postgres_db
    with _patched_fake_user("soar_operations_empty", "epass", "analyst"):
        assert client.post("/login", json={"username": "soar_operations_empty", "password": "epass"}).status_code == 200
        with _patched_metrics_db(conn):
            resp = client.get("/metrics/soar-operations")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["window_hours"] == 24
    assert body["counts"] == {
        "running_playbooks": 0,
        "awaiting_approval_playbooks": 0,
        "active_playbooks": 0,
        "pending_approvals": 0,
        "recently_expired_denied": 0,
        "failed_executions": 0,
        "actionable_dead_letters": 0,
    }
    assert body["running_playbooks"]["items"] == []
    assert body["pending_approvals"]["items"] == []
    assert body["recently_expired_denied"]["items"] == []
    assert body["failed_executions"]["items"] == []
    assert body["actionable_dead_letters"]["items"] == []
    assert body["legacy_expected_backlog"]["open_count"] == 0


@pytest.mark.usefixtures("postgres_db")
def test_soar_operations_metrics_counts_and_preview_items_match_existing_contracts(client, postgres_db):
    conn, cur = postgres_db

    running_alert_id = _insert_alert(cur, alert_type="running_alert", source_ip="198.51.100.11")
    awaiting_alert_id = _insert_alert(cur, alert_type="awaiting_alert", source_ip="198.51.100.12")
    failed_alert_id = _insert_alert(cur, alert_type="failed_alert", source_ip="198.51.100.13")
    historical_alert_id = _insert_alert(cur, alert_type="historical_alert", source_ip="198.51.100.14")

    running_execution_id = _insert_playbook_execution(
        conn,
        cur,
        playbook_id="pb_running",
        status="running",
        alert_id=running_alert_id,
    )
    awaiting_execution_id = _insert_playbook_execution(
        conn,
        cur,
        playbook_id="pb_awaiting",
        status="awaiting_approval",
        alert_id=awaiting_alert_id,
    )
    failed_execution_id = _insert_playbook_execution(
        conn,
        cur,
        playbook_id="pb_failed",
        status="failed",
        alert_id=failed_alert_id,
        completed_at=datetime.now(timezone.utc),
        failure_reason="adapter timeout",
    )
    historical_execution_id = _insert_playbook_execution(
        conn,
        cur,
        playbook_id="pb_historical",
        status="not_actioned",
        alert_id=historical_alert_id,
        completed_at=datetime.now(timezone.utc),
    )

    pending_incident_id = _insert_incident(cur, title="Pending approval incident", severity="HIGH", age="30 minutes")
    recent_denied_incident_id = _insert_incident(cur, title="Denied approval incident", severity="HIGH", age="20 minutes")
    recent_expired_incident_id = _insert_incident(cur, title="Expired approval incident", severity="HIGH", age="15 minutes")
    old_expired_incident_id = _insert_incident(cur, title="Old expired approval incident", severity="HIGH", age="30 hours")

    create_approval_request(
        conn,
        incident_id=pending_incident_id,
        playbook_execution_id=awaiting_execution_id,
        playbook_step_index=1,
        action="block_ip",
        request_reason="pending review",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    create_approval_request(
        conn,
        incident_id=recent_denied_incident_id,
        playbook_execution_id=historical_execution_id,
        playbook_step_index=2,
        action="block_ip",
        request_reason="too broad",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    create_approval_request(
        conn,
        incident_id=recent_expired_incident_id,
        playbook_execution_id=historical_execution_id,
        playbook_step_index=3,
        action="block_ip",
        request_reason="awaited approval",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    create_approval_request(
        conn,
        incident_id=old_expired_incident_id,
        playbook_execution_id=historical_execution_id,
        playbook_step_index=4,
        action="block_ip",
        request_reason="too old",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=30),
    )

    cur.execute(
        """
        UPDATE approval_requests
        SET status = 'denied',
            decided_at = NOW() - INTERVAL '10 minutes',
            decision_comment = 'Denied by operator'
        WHERE incident_id = %s
        """,
        (recent_denied_incident_id,),
    )
    cur.execute(
        """
        UPDATE approval_requests
        SET status = 'expired',
            decided_at = NOW() - INTERVAL '5 minutes',
            expires_at = NOW() - INTERVAL '5 minutes'
        WHERE incident_id = %s
        """,
        (recent_expired_incident_id,),
    )
    cur.execute(
        """
        UPDATE approval_requests
        SET status = 'expired',
            decided_at = NOW() - INTERVAL '30 hours',
            expires_at = NOW() - INTERVAL '30 hours'
        WHERE incident_id = %s
        """,
        (old_expired_incident_id,),
    )

    dead_letter_store.create_dead_letter(
        conn,
        source_type="playbook_execution",
        source_id=failed_execution_id,
        execution_id=failed_execution_id,
        alert_id=failed_alert_id,
        playbook_id="pb_failed",
        failure_class="adapter_failed",
        error_message="adapter timeout",
        retryable=True,
    )
    dead_letter_store.create_dead_letter(
        conn,
        source_type="approval",
        source_id=9991,
        execution_id=historical_execution_id,
        alert_id=historical_alert_id,
        playbook_id="pb_historical",
        failure_class="approval_expired",
        error_message="historical expiration backlog",
        retryable=False,
    )
    dead_letter_store.create_dead_letter(
        conn,
        source_type="approval",
        source_id=9992,
        execution_id=historical_execution_id,
        alert_id=historical_alert_id,
        playbook_id="pb_historical",
        failure_class="approval_denied",
        error_message="historical denied backlog",
        retryable=False,
    )
    conn.commit()

    with _patched_fake_user("soar_operations_counts", "cpass", "analyst"):
        assert client.post("/login", json={"username": "soar_operations_counts", "password": "cpass"}).status_code == 200
        with _patched_metrics_db(conn):
            resp = client.get("/metrics/soar-operations")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["counts"] == {
        "running_playbooks": 1,
        "awaiting_approval_playbooks": 1,
        "active_playbooks": 2,
        "pending_approvals": 1,
        "recently_expired_denied": 2,
        "failed_executions": 1,
        "actionable_dead_letters": 3,
    }
    assert body["running_playbooks"]["running_count"] == 1
    assert body["running_playbooks"]["awaiting_approval_count"] == 1
    assert body["running_playbooks"]["items"][0]["execution_id"] == awaiting_execution_id or body["running_playbooks"]["items"][0]["execution_id"] == running_execution_id
    assert body["pending_approvals"]["items"][0]["playbook_execution_id"] == awaiting_execution_id
    assert body["pending_approvals"]["items"][0]["alert_id"] == awaiting_alert_id
    assert {item["status"] for item in body["recently_expired_denied"]["items"]} == {"denied", "expired"}
    assert all(item["alert_id"] == historical_alert_id for item in body["recently_expired_denied"]["items"])
    assert {item["execution_status"] for item in body["recently_expired_denied"]["items"]} == {"not_actioned"}
    assert body["failed_executions"]["items"][0]["execution_id"] == failed_execution_id
    assert body["failed_executions"]["items"][0]["failure_reason"] == "adapter timeout"
    assert {item["classification"]["kind"] for item in body["actionable_dead_letters"]["items"]} == {
        "system_failure",
        "expected_expiration",
        "expected_denial",
    }
    assert body["actionable_dead_letters"]["open_count"] == 3
    assert body["legacy_expected_backlog"]["open_count"] == 2
