"""
Tests for SOAR queue visibility admin endpoints.

Coverage:
- Auth (401 for unauthenticated, 403 for non-admin, 200 for admin)
- Response shape consistency
- Nullable alert_id handling
- Query parameter validation
- No mutation of queue state
"""

from contextlib import contextmanager
from unittest.mock import patch
from datetime import datetime, timezone

import pytest
from werkzeug.security import generate_password_hash

from core import soar_response_outcomes as outcomes
import siem_backend


ADMIN_USER = "testadmin"
ADMIN_PASS = "testpassword123!"


class _RouteSafeConnection:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return self._conn.cursor()

    def close(self):
        return None


@contextmanager
def _patched_app_db(conn):
    wrapper = _RouteSafeConnection(conn)
    with patch("routes.admin_routes.get_db_connection", return_value=wrapper), patch(
        "core.audit_helpers.get_db_connection", return_value=wrapper
    ), patch("engines.detection_config.get_db_connection", return_value=wrapper):
        yield


def _login_super_admin(client):
    resp = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert resp.status_code == 200


def _fake_viewer():
    return {
        "username": "queue_viewer",
        "password_hash": generate_password_hash("viewerpass", method="pbkdf2:sha256"),
        "role": "viewer",
        "is_active": True,
    }


def _fake_analyst():
    return {
        "username": "queue_analyst",
        "password_hash": generate_password_hash("analystpass", method="pbkdf2:sha256"),
        "role": "analyst",
        "is_active": True,
    }


def _insert_queue_row(cur, alert_id, source_ip, action, status, retry_count=0, 
                      max_retries=3, last_error=None):
    """Helper to insert a queue row and return its ID."""
    import hashlib
    idempotency_key = hashlib.sha256(
        f"{action}:{source_ip}:{alert_id}".encode()
    ).hexdigest()
    
    cur.execute(
        """
        INSERT INTO response_actions_queue 
        (idempotency_key, alert_id, source_ip, action, status, retry_count, max_retries, last_error)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (idempotency_key, alert_id, source_ip, action, status, retry_count, max_retries, last_error),
    )
    return cur.fetchone()[0]


def _insert_alert(cur, source_ip="10.0.0.1"):
    """Helper to insert an alert and return its ID."""
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message)
        VALUES ('test_alert', 'low', %s, 'test alert')
        RETURNING id
        """,
        (source_ip,),
    )
    return cur.fetchone()[0]


def _fetch_queue_row(cur, queue_id):
    """Fetch a queue row to verify no mutations."""
    cur.execute(
        """
        SELECT id, alert_id, source_ip::text, action, status, 
               retry_count, max_retries, last_error, updated_at
        FROM response_actions_queue
        WHERE id = %s
        """,
        (queue_id,),
    )
    return cur.fetchone()


def _count_queue_route_state(cur):
    cur.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM response_actions_queue),
            (SELECT COUNT(*) FROM soar_response_decisions),
            (SELECT COUNT(*) FROM soar_response_outcome_events)
        """
    )
    return cur.fetchone()


def _insert_approval_request(cur, queue_id, action="block_ip", status="pending"):
    cur.execute(
        """
        INSERT INTO approval_requests (
            queue_id, action, status, risk_level, request_reason,
            decision_comment, expires_at, decided_at
        )
        VALUES (
            %s,
            %s,
            %s,
            'high',
            'approval visibility test',
            CASE WHEN %s = 'pending' THEN NULL ELSE 'terminal decision' END,
            NOW() + INTERVAL '1 hour',
            CASE WHEN %s = 'pending' THEN NULL ELSE NOW() END
        )
        RETURNING id
        """,
        (queue_id, action, status, status, status),
    )
    return cur.fetchone()[0]


# ============================================================================
# Auth Tests
# ============================================================================


@pytest.mark.parametrize(
    "path",
    [
        "/admin/soar/queue/status",
        "/admin/soar/queue/recent",
        "/admin/soar/queue/123",
    ],
)
def test_queue_visibility_endpoints_without_session_return_401(client, path):
    """Unauthenticated requests should return 401."""
    resp = client.get(path)
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "Unauthorized"


@pytest.mark.parametrize(
    "path,fake_user,password",
    [
        ("/admin/soar/queue/status", _fake_viewer(), "viewerpass"),
        ("/admin/soar/queue/status", _fake_analyst(), "analystpass"),
        ("/admin/soar/queue/recent", _fake_viewer(), "viewerpass"),
        ("/admin/soar/queue/recent", _fake_analyst(), "analystpass"),
        ("/admin/soar/queue/123", _fake_viewer(), "viewerpass"),
        ("/admin/soar/queue/123", _fake_analyst(), "analystpass"),
    ],
)
def test_queue_visibility_endpoints_as_non_admin_return_403(
    client, mock_db, path, fake_user, password
):
    """Non-admin users should receive 403."""
    with patch("routes.auth_routes.get_user_by_username", return_value=fake_user), patch(
        "core.auth.get_user_by_username", return_value=fake_user
    ):
        login = client.post("/login", json={"username": fake_user["username"], "password": password})
        assert login.status_code == 200
        resp = client.get(path)
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "forbidden"


# ============================================================================
# Status Endpoint Tests
# ============================================================================


def test_queue_status_endpoint_as_super_admin_returns_200_stable_shape(client, postgres_db):
    """Admin should be able to read queue status with stable response shape."""
    conn, cur = postgres_db
    
    # Seed queue with rows of different statuses
    alert_id = _insert_alert(cur)
    conn.commit()
    
    _insert_queue_row(cur, alert_id, "192.0.2.1", "block_ip", "pending")
    _insert_queue_row(cur, alert_id, "192.0.2.2", "block_ip", "running")
    _insert_queue_row(cur, alert_id, "192.0.2.3", "block_ip", "success")
    _insert_queue_row(cur, alert_id, "192.0.2.4", "block_ip", "failed", last_error="timeout")
    _insert_queue_row(cur, alert_id, "192.0.2.5", "block_ip", "skipped")
    _insert_queue_row(cur, alert_id, "192.0.2.6", "block_ip", "awaiting_approval")
    conn.commit()
    
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/admin/soar/queue/status")
    
    assert resp.status_code == 200
    data = resp.get_json()
    
    # Check stable shape
    assert "counts" in data
    assert "total" in data
    assert "generated_at" in data
    
    # Check all statuses present
    counts = data["counts"]
    for status in ("pending", "running", "awaiting_approval", "success", "failed", "skipped"):
        assert status in counts
    
    # Check counts
    assert counts["pending"] == 1
    assert counts["running"] == 1
    assert counts["success"] == 1
    assert counts["failed"] == 1
    assert counts["skipped"] == 1
    assert counts["awaiting_approval"] == 1
    assert data["total"] == 6


def test_queue_status_includes_zero_counts_for_absent_statuses(client, postgres_db):
    """Status endpoint should include all statuses even with zero count."""
    conn, cur = postgres_db
    
    alert_id = _insert_alert(cur)
    conn.commit()
    
    # Only insert pending
    _insert_queue_row(cur, alert_id, "192.0.2.1", "block_ip", "pending")
    conn.commit()
    
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/admin/soar/queue/status")
    
    assert resp.status_code == 200
    data = resp.get_json()
    
    counts = data["counts"]
    assert counts["pending"] == 1
    assert counts["running"] == 0
    assert counts["awaiting_approval"] == 0
    assert counts["success"] == 0
    assert counts["failed"] == 0
    assert counts["skipped"] == 0


# ============================================================================
# Recent Endpoint Tests
# ============================================================================


def test_queue_recent_endpoint_as_super_admin_returns_200_stable_shape(client, postgres_db):
    """Admin should be able to read recent queue items with stable response shape."""
    conn, cur = postgres_db
    
    alert_id = _insert_alert(cur)
    conn.commit()
    
    _insert_queue_row(cur, alert_id, "192.0.2.1", "block_ip", "pending")
    _insert_queue_row(cur, alert_id, "192.0.2.2", "notify_slack", "success")
    conn.commit()
    
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/admin/soar/queue/recent")
    
    assert resp.status_code == 200
    data = resp.get_json()
    
    # Check stable shape
    assert "items" in data
    assert "limit" in data
    assert "status" in data
    
    # Check items
    items = data["items"]
    assert len(items) == 2
    assert data["limit"] == 50
    assert data["status"] is None
    
    # Check item shape
    for item in items:
        for key in (
            "id",
            "alert_id",
            "alert_reference",
            "source_ip",
            "action",
            "status",
            "retry_count",
            "max_retries",
            "last_error",
            "created_at",
            "updated_at",
            "response_outcome",
        ):
            assert key in item
        
        # Check alert_reference shape
        assert "status" in item["alert_reference"]
        assert "label" in item["alert_reference"]


def test_queue_recent_returns_newest_first(client, postgres_db):
    """Queue items should be returned newest first (by ID DESC)."""
    conn, cur = postgres_db
    
    alert_id = _insert_alert(cur)
    conn.commit()
    
    id1 = _insert_queue_row(cur, alert_id, "192.0.2.1", "block_ip", "pending")
    id2 = _insert_queue_row(cur, alert_id, "192.0.2.2", "block_ip", "pending")
    id3 = _insert_queue_row(cur, alert_id, "192.0.2.3", "block_ip", "pending")
    conn.commit()
    
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/admin/soar/queue/recent")
    
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    
    # Should be newest (highest ID) first
    assert items[0]["id"] == id3
    assert items[1]["id"] == id2
    assert items[2]["id"] == id1


def test_queue_recent_respects_limit_param(client, postgres_db):
    """Recent endpoint should respect limit parameter."""
    conn, cur = postgres_db
    
    alert_id = _insert_alert(cur)
    conn.commit()
    
    for i in range(10):
        _insert_queue_row(cur, alert_id, f"192.0.2.{i}", "block_ip", "pending")
    conn.commit()
    
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/admin/soar/queue/recent?limit=3")
    
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["items"]) == 3
    assert data["limit"] == 3


def test_queue_recent_clamps_excessive_limit(client, postgres_db):
    """Recent endpoint should clamp limit to 100 max."""
    conn, cur = postgres_db
    
    alert_id = _insert_alert(cur)
    conn.commit()
    
    _insert_queue_row(cur, alert_id, "192.0.2.1", "block_ip", "pending")
    conn.commit()
    
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/admin/soar/queue/recent?limit=500")
    
    assert resp.status_code == 200
    # Should be clamped to 100, but only 1 row exists
    assert len(resp.get_json()["items"]) == 1


def test_queue_recent_invalid_limit_returns_400(client, postgres_db):
    """Invalid limit parameter should return 400."""
    conn, cur = postgres_db
    
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/admin/soar/queue/recent?limit=abc")
    
    assert resp.status_code == 400
    assert "integer" in resp.get_json()["error"].lower()


def test_queue_recent_invalid_status_returns_400(client, postgres_db):
    """Invalid status parameter should return 400."""
    conn, cur = postgres_db
    
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/admin/soar/queue/recent?status=invalid_status")
    
    assert resp.status_code == 400
    assert "status" in resp.get_json()["error"].lower()


def test_queue_recent_filters_by_status(client, postgres_db):
    """Recent endpoint should filter by status parameter."""
    conn, cur = postgres_db
    
    alert_id = _insert_alert(cur)
    conn.commit()
    
    _insert_queue_row(cur, alert_id, "192.0.2.1", "block_ip", "pending")
    _insert_queue_row(cur, alert_id, "192.0.2.2", "block_ip", "running")
    _insert_queue_row(cur, alert_id, "192.0.2.3", "block_ip", "success")
    _insert_queue_row(cur, alert_id, "192.0.2.4", "block_ip", "awaiting_approval")
    conn.commit()
    
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/admin/soar/queue/recent?status=success")
    
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["items"]) == 1
    assert data["items"][0]["status"] == "success"

    with _patched_app_db(conn):
        resp = client.get("/admin/soar/queue/recent?status=awaiting_approval")

    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["items"]) == 1
    assert data["items"][0]["status"] == "awaiting_approval"


def test_queue_recent_unlinked_rows_include_null_response_outcome(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    queue_id = _insert_queue_row(cur, alert_id, "192.0.2.41", "block_ip", "pending")
    conn.commit()

    _login_super_admin(client)
    before_counts = _count_queue_route_state(cur)
    with _patched_app_db(conn):
        resp = client.get("/admin/soar/queue/recent")
    after_counts = _count_queue_route_state(cur)

    assert resp.status_code == 200
    assert after_counts == before_counts
    item = resp.get_json()["items"][0]
    assert item["id"] == queue_id
    assert item["alert_id"] == alert_id
    assert item["source_ip"] == "192.0.2.41"
    assert item["action"] == "block_ip"
    assert item["status"] == "pending"
    assert item["response_outcome"] is None


def test_queue_recent_linked_row_returns_canonical_response_outcome(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, source_ip="192.0.2.42")
    queue_id = _insert_queue_row(cur, alert_id, "192.0.2.42", "block_ip", "success")
    decision = outcomes.create_response_decision(
        conn,
        selected_action="block_ip",
        decision_source="manual",
        outcome_summary="Queue response selected.",
        alert_id=alert_id,
        source_ip="192.0.2.42",
        queue_id=queue_id,
        reason_code="tracking_only",
    )
    event = outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        execution_mode="tracking_only",
        execution_state="succeeded",
        execution_actor="manual",
        external_executed=False,
        tracking_recorded=True,
        simulated=False,
        reason_code="tracking_only",
        outcome_summary="Queue response recorded as tracking only.",
        alert_id=alert_id,
        source_ip="192.0.2.42",
        queue_id=queue_id,
    )
    cur.execute(
        """
        UPDATE response_actions_queue
        SET decision_id = %s, soar_correlation_id = %s
        WHERE id = %s
        """,
        (decision["id"], decision["soar_correlation_id"], queue_id),
    )
    conn.commit()

    _login_super_admin(client)
    before_counts = _count_queue_route_state(cur)
    with _patched_app_db(conn):
        resp = client.get("/admin/soar/queue/recent")
    after_counts = _count_queue_route_state(cur)

    assert resp.status_code == 200
    assert after_counts == before_counts
    item = resp.get_json()["items"][0]
    assert item["id"] == queue_id
    outcome = item["response_outcome"]
    assert outcome is not None
    assert outcome["decision_id"] == decision["id"]
    assert outcome["latest_outcome_event_id"] == event["id"]
    assert outcome["soar_correlation_id"] == decision["soar_correlation_id"]
    assert outcome["selected_action"] == "block_ip"
    assert outcome["decision_source"] == "manual"
    assert outcome["execution_mode"] == "tracking_only"
    assert outcome["execution_state"] == "succeeded"
    assert outcome["tracking_recorded"] is True
    assert outcome["external_executed"] is False
    assert outcome["simulated"] is False
    assert outcome["related"]["queue_id"] == queue_id


def test_queue_recent_uses_bulk_response_outcome_lookup(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    _insert_queue_row(cur, alert_id, "192.0.2.43", "block_ip", "pending")
    _insert_queue_row(cur, alert_id, "192.0.2.44", "monitor", "success")
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn), patch(
        "routes.admin_routes.get_latest_outcomes_for_queues_bulk",
        wraps=outcomes.get_latest_outcomes_for_queues_bulk,
    ) as bulk_lookup:
        resp = client.get("/admin/soar/queue/recent")

    assert resp.status_code == 200
    assert bulk_lookup.call_count == 1
    assert len(bulk_lookup.call_args.args[1]) == 2


# ============================================================================
# Nullable alert_id Tests
# ============================================================================


def test_queue_recent_with_null_alert_id(client, postgres_db):
    """Queue rows with alert_id=NULL should serialize safely."""
    conn, cur = postgres_db
    conn.commit()
    
    # Insert queue row with no alert
    _insert_queue_row(cur, None, "192.0.2.1", "block_ip", "pending")
    conn.commit()
    
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/admin/soar/queue/recent")
    
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    assert len(items) == 1
    
    item = items[0]
    assert item["alert_id"] is None
    assert item["alert_reference"]["status"] == "deleted_or_missing"
    assert item["alert_reference"]["label"] == "Deleted alert"


def test_queue_recent_with_linked_alert(client, postgres_db):
    """Queue rows with alert_id should show linked status."""
    conn, cur = postgres_db
    
    alert_id = _insert_alert(cur)
    conn.commit()
    
    _insert_queue_row(cur, alert_id, "192.0.2.1", "block_ip", "pending")
    conn.commit()
    
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/admin/soar/queue/recent")
    
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    
    item = items[0]
    assert item["alert_id"] == alert_id
    assert item["alert_reference"]["status"] == "linked"
    assert f"Alert {alert_id}" in item["alert_reference"]["label"]


# ============================================================================
# Detail Endpoint Tests
# ============================================================================


def test_queue_detail_endpoint_returns_404_for_missing_item(client, postgres_db):
    """Detail endpoint should return 404 for non-existent queue ID."""
    conn, cur = postgres_db
    
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/admin/soar/queue/9999")
    
    assert resp.status_code == 404
    assert "not found" in resp.get_json()["error"].lower()


def test_queue_detail_endpoint_returns_stable_shape(client, postgres_db):
    """Detail endpoint should return stable queue item shape."""
    conn, cur = postgres_db
    
    alert_id = _insert_alert(cur)
    conn.commit()
    
    queue_id = _insert_queue_row(cur, alert_id, "192.0.2.1", "block_ip", "pending")
    conn.commit()
    
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get(f"/admin/soar/queue/{queue_id}")
    
    assert resp.status_code == 200
    item = resp.get_json()
    
    # Check all expected keys including idempotency_key
    for key in (
        "id",
        "alert_id",
        "alert_reference",
        "source_ip",
        "action",
        "status",
        "retry_count",
        "max_retries",
        "last_error",
        "created_at",
        "updated_at",
        "response_outcome",
        "idempotency_key",
        "latest_approval",
        "approval_events",
    ):
        assert key in item


def test_queue_detail_unlinked_row_includes_null_response_outcome(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    queue_id = _insert_queue_row(cur, alert_id, "192.0.2.45", "monitor", "pending")
    conn.commit()

    _login_super_admin(client)
    before_counts = _count_queue_route_state(cur)
    with _patched_app_db(conn):
        resp = client.get(f"/admin/soar/queue/{queue_id}")
    after_counts = _count_queue_route_state(cur)

    assert resp.status_code == 200
    assert after_counts == before_counts
    item = resp.get_json()
    assert item["id"] == queue_id
    assert item["alert_id"] == alert_id
    assert item["source_ip"] == "192.0.2.45"
    assert item["action"] == "monitor"
    assert item["status"] == "pending"
    assert item["response_outcome"] is None


def test_queue_detail_linked_by_correlation_id_returns_canonical_response_outcome(
    client, postgres_db
):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, source_ip="192.0.2.46")
    queue_id = _insert_queue_row(cur, alert_id, "192.0.2.46", "monitor", "success")
    decision = outcomes.create_response_decision(
        conn,
        selected_action="monitor",
        decision_source="manual",
        outcome_summary="Queue monitor response selected.",
        alert_id=alert_id,
        source_ip="192.0.2.46",
        queue_id=queue_id,
        reason_code="simulation_mode",
    )
    event = outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        execution_mode="simulation",
        execution_state="succeeded",
        execution_actor="manual",
        external_executed=False,
        tracking_recorded=False,
        simulated=True,
        reason_code="simulation_mode",
        outcome_summary="Queue monitor response completed in simulation.",
        alert_id=alert_id,
        source_ip="192.0.2.46",
        queue_id=queue_id,
    )
    cur.execute(
        """
        UPDATE response_actions_queue
        SET soar_correlation_id = %s
        WHERE id = %s
        """,
        (decision["soar_correlation_id"], queue_id),
    )
    conn.commit()

    _login_super_admin(client)
    before_counts = _count_queue_route_state(cur)
    with _patched_app_db(conn):
        resp = client.get(f"/admin/soar/queue/{queue_id}")
    after_counts = _count_queue_route_state(cur)

    assert resp.status_code == 200
    assert after_counts == before_counts
    item = resp.get_json()
    outcome = item["response_outcome"]
    assert outcome is not None
    assert outcome["decision_id"] == decision["id"]
    assert outcome["latest_outcome_event_id"] == event["id"]
    assert outcome["soar_correlation_id"] == decision["soar_correlation_id"]
    assert outcome["selected_action"] == "monitor"
    assert outcome["execution_mode"] == "simulation"
    assert outcome["execution_state"] == "succeeded"
    assert outcome["simulated"] is True
    assert outcome["related"]["queue_id"] == queue_id


def test_queue_detail_latest_approval_null_when_no_approval(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    queue_id = _insert_queue_row(cur, alert_id, "192.0.2.11", "block_ip", "pending")
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get(f"/admin/soar/queue/{queue_id}")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["latest_approval"] is None
    assert payload["approval_events"] == []


def test_queue_detail_latest_approval_populated_when_approval_exists(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    queue_id = _insert_queue_row(
        cur, alert_id, "192.0.2.12", "block_ip", "awaiting_approval"
    )
    approval_id = _insert_approval_request(cur, queue_id, status="pending")
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get(f"/admin/soar/queue/{queue_id}")

    assert resp.status_code == 200
    latest_approval = resp.get_json()["latest_approval"]
    assert latest_approval["id"] == approval_id
    assert latest_approval["status"] == "pending"
    assert "risk_level" in latest_approval
    assert "created_at" in latest_approval
    assert "expires_at" in latest_approval
    assert "decided_at" in latest_approval


def test_queue_detail_latest_approval_uses_most_recent_approval(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    queue_id = _insert_queue_row(
        cur, alert_id, "192.0.2.13", "block_ip", "awaiting_approval"
    )
    _insert_approval_request(cur, queue_id, status="expired")
    latest_id = _insert_approval_request(cur, queue_id, status="pending")
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get(f"/admin/soar/queue/{queue_id}")

    assert resp.status_code == 200
    latest_approval = resp.get_json()["latest_approval"]
    assert latest_approval["id"] == latest_id
    assert latest_approval["status"] == "pending"


def test_queue_detail_latest_approval_excludes_sensitive_fields(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    queue_id = _insert_queue_row(
        cur, alert_id, "192.0.2.14", "block_ip", "awaiting_approval"
    )
    _insert_approval_request(cur, queue_id, status="pending")
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get(f"/admin/soar/queue/{queue_id}")

    assert resp.status_code == 200
    latest_approval = resp.get_json()["latest_approval"]
    assert set(latest_approval.keys()) == {
        "id",
        "status",
        "risk_level",
        "created_at",
        "expires_at",
        "decided_at",
    }
    for field in (
        "requested_by",
        "approved_by",
        "decided_by",
        "request_reason",
        "decision_comment",
    ):
        assert field not in latest_approval


def test_queue_detail_approval_events_populated_and_ordered(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    queue_id = _insert_queue_row(
        cur, alert_id, "192.0.2.15", "block_ip", "awaiting_approval"
    )
    approval_id = _insert_approval_request(cur, queue_id, status="pending")
    cur.execute(
        """
        INSERT INTO approval_request_events (
            approval_request_id, event_type, previous_status, new_status, comment
        )
        VALUES (%s, 'created', NULL, 'pending', 'approval visibility test')
        """,
        (approval_id,),
    )
    cur.execute(
        """
        INSERT INTO approval_request_events (
            approval_request_id, event_type, previous_status, new_status, comment
        )
        VALUES (%s, 'denied', 'pending', 'denied', 'Too broad')
        """,
        (approval_id,),
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get(f"/admin/soar/queue/{queue_id}")

    assert resp.status_code == 200
    approval_events = resp.get_json()["approval_events"]
    assert len(approval_events) == 2
    assert approval_events[0]["event_type"] == "created"
    assert approval_events[1]["event_type"] == "denied"


def test_queue_detail_approval_events_empty_when_no_approval(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    queue_id = _insert_queue_row(cur, alert_id, "192.0.2.16", "monitor", "pending")
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get(f"/admin/soar/queue/{queue_id}")

    assert resp.status_code == 200
    assert resp.get_json()["approval_events"] == []


def test_queue_detail_includes_idempotency_key(client, postgres_db):
    """Detail endpoint should include idempotency_key (unlike list)."""
    conn, cur = postgres_db
    
    alert_id = _insert_alert(cur)
    conn.commit()
    
    queue_id = _insert_queue_row(cur, alert_id, "192.0.2.1", "block_ip", "pending")
    conn.commit()
    
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get(f"/admin/soar/queue/{queue_id}")
    
    assert resp.status_code == 200
    item = resp.get_json()
    assert "idempotency_key" in item
    assert isinstance(item["idempotency_key"], str)
    assert len(item["idempotency_key"]) > 0


# ============================================================================
# No-Mutation Tests
# ============================================================================


def test_queue_visibility_endpoints_do_not_mutate_status(client, postgres_db):
    """Calling visibility endpoints should not change queue status."""
    conn, cur = postgres_db
    
    alert_id = _insert_alert(cur)
    conn.commit()
    
    queue_id = _insert_queue_row(cur, alert_id, "192.0.2.1", "block_ip", "pending")
    original_row = _fetch_queue_row(cur, queue_id)
    conn.commit()
    
    _login_super_admin(client)
    with _patched_app_db(conn):
        client.get("/admin/soar/queue/status")
        client.get("/admin/soar/queue/recent")
        client.get(f"/admin/soar/queue/{queue_id}")
    
    # Re-fetch and verify unchanged
    after_row = _fetch_queue_row(cur, queue_id)
    assert original_row[4] == after_row[4]  # status unchanged


def test_queue_visibility_endpoints_do_not_mutate_retry_count(client, postgres_db):
    """Calling visibility endpoints should not change retry_count."""
    conn, cur = postgres_db
    
    alert_id = _insert_alert(cur)
    conn.commit()
    
    queue_id = _insert_queue_row(cur, alert_id, "192.0.2.1", "block_ip", "failed", retry_count=2)
    original_row = _fetch_queue_row(cur, queue_id)
    conn.commit()
    
    _login_super_admin(client)
    with _patched_app_db(conn):
        client.get("/admin/soar/queue/recent")
        client.get(f"/admin/soar/queue/{queue_id}")
    
    after_row = _fetch_queue_row(cur, queue_id)
    assert original_row[5] == after_row[5]  # retry_count unchanged


def test_queue_visibility_endpoints_do_not_mutate_updated_at(client, postgres_db):
    """Calling visibility endpoints should not change updated_at timestamp."""
    conn, cur = postgres_db
    
    alert_id = _insert_alert(cur)
    conn.commit()
    
    queue_id = _insert_queue_row(cur, alert_id, "192.0.2.1", "block_ip", "pending")
    original_row = _fetch_queue_row(cur, queue_id)
    conn.commit()
    
    _login_super_admin(client)
    with _patched_app_db(conn):
        client.get("/admin/soar/queue/status")
        client.get("/admin/soar/queue/recent")
        client.get(f"/admin/soar/queue/{queue_id}")
    
    after_row = _fetch_queue_row(cur, queue_id)
    assert original_row[8] == after_row[8]  # updated_at unchanged


# ============================================================================
# List endpoint idempotency_key exclusion
# ============================================================================


def test_queue_recent_does_not_expose_idempotency_key(client, postgres_db):
    """Recent list endpoint should not expose idempotency_key."""
    conn, cur = postgres_db
    
    alert_id = _insert_alert(cur)
    conn.commit()
    
    _insert_queue_row(cur, alert_id, "192.0.2.1", "block_ip", "pending")
    conn.commit()
    
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/admin/soar/queue/recent")
    
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    
    for item in items:
        assert "idempotency_key" not in item
