from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from psycopg2.extras import Json
from werkzeug.security import generate_password_hash

import siem_backend
from core import soar_response_outcomes as outcomes
from core.incident_store import create_incident, link_alert_to_incident, maybe_create_or_link_incident
from routes.incident_routes import _map_step_event_type


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


def _login_role(client, *, username, login_secret, role):
    user = _fake_user(username, login_secret, role)
    patchers = [
        patch("routes.auth_routes.get_user_by_username", return_value=user),
        patch("core.auth.get_user_by_username", return_value=user),
    ]
    for patcher in patchers:
        patcher.start()
    resp = client.post("/login", json={"username": username, "pass" + "word": login_secret})
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
        login_secret="viewerpass",
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
        login_secret="analystpass",
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

    def fake_list_incidents(conn, status=None, severity=None, operational_scope="all_history", limit=50, offset=0):
        captured["limit"] = limit
        captured["operational_scope"] = operational_scope
        return []

    monkeypatch.setattr("routes.incident_routes.list_incidents", fake_list_incidents)

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/incidents?limit=200")

    assert resp.status_code == 200
    assert captured["limit"] == 100


def test_get_incidents_since_tuning_scope_is_forwarded(client, postgres_db, monkeypatch):
    conn, _cur = postgres_db
    captured = {}

    def fake_list_incidents(conn, status=None, severity=None, operational_scope="all_history", limit=50, offset=0):
        captured["operational_scope"] = operational_scope
        return []

    monkeypatch.setattr("routes.incident_routes.list_incidents", fake_list_incidents)

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/incidents?operational_scope=since_tuning")

    assert resp.status_code == 200
    assert captured["operational_scope"] == "since_tuning"


def test_get_incident_detail_without_session_returns_401(client):
    resp = client.get("/incidents/1")
    assert resp.status_code == 401


def test_get_incident_detail_viewer_returns_403(client, mock_db):
    patchers = _login_role(
        client,
        username="incidentviewer2",
        login_secret="viewerpass",
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
        login_secret="analystpass",
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


def test_incident_timeline_exposes_severity_escalation_audit_event(client, postgres_db):
    conn, cur = postgres_db
    audit_wrapper = _RouteSafeConnection(conn)
    first_alert_id = _insert_alert(cur, source_ip="203.0.113.160", severity="HIGH")
    with siem_backend.app.app_context(), patch(
        "core.audit_helpers.get_db_connection",
        return_value=audit_wrapper,
    ):
        incident = maybe_create_or_link_incident(conn, first_alert_id, "HIGH", "203.0.113.160")
    conn.commit()
    second_alert_id = _insert_alert(cur, source_ip="203.0.113.160", severity="CRITICAL")
    with siem_backend.app.app_context(), patch(
        "core.audit_helpers.get_db_connection",
        return_value=audit_wrapper,
    ):
        maybe_create_or_link_incident(conn, second_alert_id, "CRITICAL", "203.0.113.160")
    conn.commit()

    patchers = _login_role(
        client,
        username="timelineaudit",
        login_secret="analyst-fixture-login-value",
        role="analyst",
    )
    try:
        with _patched_app_db(conn):
            resp = client.get(f"/incidents/{incident['id']}/timeline")
    finally:
        _stop_patchers(patchers)

    assert resp.status_code == 200
    audit_entries = [
        entry for entry in resp.get_json()["timeline"] if entry.get("event_type") == "audit_event"
    ]
    assert any(entry.get("title") == "incident_severity_escalated" for entry in audit_entries)


def test_map_step_event_type_classifies_simulated_adapter_step():
    entry = {
        "status": "success",
        "mode": "simulation",
        "executed": False,
        "output": {
            "adapter_result": {"adapter": "slack", "action": "send_message", "success": True},
        },
    }
    assert _map_step_event_type(entry) == "playbook_adapter_simulated"


def test_map_step_event_type_classifies_real_executed_adapter_step():
    entry = {
        "status": "success",
        "mode": "real",
        "executed": True,
        "output": {
            "adapter_result": {"adapter": "slack", "action": "send_message", "success": True, "mode": "real"},
        },
    }
    assert _map_step_event_type(entry) == "playbook_adapter_real"


def test_map_step_event_type_real_mode_without_confirmed_execution_stays_simulated():
    # Fail-closed: real mode alone is not enough without confirmed execution.
    entry = {
        "status": "success",
        "mode": "real",
        "executed": False,
        "output": {
            "adapter_result": {"adapter": "slack", "action": "send_message", "success": True, "mode": "real"},
        },
    }
    assert _map_step_event_type(entry) == "playbook_adapter_simulated"


def test_map_step_event_type_missing_mode_info_defaults_to_simulated():
    # Legacy/historical entries without mode info remain safely simulated, never promoted to real.
    entry = {
        "status": "success",
        "output": {
            "adapter_result": {"adapter": "slack", "action": "send_message", "success": True},
        },
    }
    assert _map_step_event_type(entry) == "playbook_adapter_simulated"


def test_map_step_event_type_failed_adapter_step_unaffected():
    entry = {
        "status": "success",
        "mode": "real",
        "executed": True,
        "output": {
            "adapter_result": {"adapter": "slack", "action": "send_message", "success": False, "mode": "real"},
        },
    }
    assert _map_step_event_type(entry) == "playbook_step_failed"


def test_incident_list_detail_and_timeline_include_response_outcome(client, postgres_db):
    conn, _cur = postgres_db
    incident = _insert_incident(conn, title="Outcome incident", source_ip="203.0.113.186")
    decision = outcomes.create_response_decision(
        conn,
        selected_action="monitor",
        decision_source="manual",
        outcome_summary="Incident response selected.",
        incident_id=incident["id"],
        source_ip="203.0.113.186",
        reason_code="simulation_mode",
    )
    event = outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        execution_mode="simulation",
        execution_state="succeeded",
        execution_actor="manual",
        simulated=True,
        outcome_summary="Incident monitored in simulation.",
        incident_id=incident["id"],
        source_ip="203.0.113.186",
        reason_code="simulation_mode",
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        list_resp = client.get("/incidents")
        detail_resp = client.get(f"/incidents/{incident['id']}")
        timeline_resp = client.get(f"/incidents/{incident['id']}/timeline")

    assert list_resp.status_code == 200
    listed = next(item for item in list_resp.get_json()["incidents"] if item["id"] == incident["id"])
    assert listed["response_outcome"]["decision_id"] == decision["id"]
    assert listed["response_outcome"]["latest_outcome_event_id"] == event["id"]

    assert detail_resp.status_code == 200
    detail = detail_resp.get_json()["incident"]
    assert detail["response_outcome"]["decision_id"] == decision["id"]

    assert timeline_resp.status_code == 200
    outcome_entries = [
        entry for entry in timeline_resp.get_json()["timeline"]
        if entry.get("type") == "response_outcome"
    ]
    assert len(outcome_entries) == 1
    assert outcome_entries[0]["metadata"]["outcome_event_id"] == event["id"]


def test_incident_unlinked_response_outcome_is_null(client, postgres_db):
    conn, _cur = postgres_db
    incident = _insert_incident(conn, title="No outcome", source_ip="203.0.113.187")

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get(f"/incidents/{incident['id']}")

    assert resp.status_code == 200
    assert resp.get_json()["incident"]["response_outcome"] is None


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
        login_secret="viewerpass",
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


def test_get_incident_timeline_without_session_returns_401(client):
    resp = client.get("/incidents/1/timeline")
    assert resp.status_code == 401


def test_get_incident_timeline_viewer_forbidden(client, mock_db):
    patchers = _login_role(
        client,
        username="inctlviewer",
        login_secret="viewerpass",
        role="viewer",
    )
    try:
        resp = client.get("/incidents/1/timeline")
    finally:
        _stop_patchers(patchers)

    assert resp.status_code == 403


def test_get_incident_timeline_missing_returns_404(client, postgres_db):
    conn, _cur = postgres_db
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/incidents/999999/timeline")

    assert resp.status_code == 404
    assert resp.get_json()["error"] == "incident not found"


def _seed_playbook_definition(cur, playbook_id="pb_timeline_test"):
    cur.execute(
        """
        INSERT INTO playbook_definitions (id, name, description, trigger_config, steps)
        VALUES (%s, %s, '', '{}'::jsonb, '[]'::jsonb)
        ON CONFLICT (id) DO NOTHING
        """,
        (playbook_id, "Timeline test playbook"),
    )


def test_get_incident_timeline_analyst_read_only_aggregate(client, postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO users (username, password_hash, role)
        VALUES ('tl_approver', 'x', 'analyst')
        RETURNING id
        """
    )
    uid = cur.fetchone()[0]
    alert_id = _insert_alert(cur, source_ip="203.0.113.100")
    incident = _insert_incident(conn, title="Timeline incident", source_ip="203.0.113.101")
    link_alert_to_incident(conn, incident["id"], alert_id)
    conn.commit()

    _seed_playbook_definition(cur, "pb_timeline_test")
    steps_log = [
        {
            "step_index": 0,
            "action": "monitor",
            "status": "success",
            "started_at": "2026-05-10T12:00:00Z",
            "completed_at": "2026-05-10T12:00:01Z",
            "message": "simulated monitor",
        },
        {
            "step_index": 1,
            "action": "notify_slack",
            "status": "success",
            "started_at": "2026-05-10T12:00:02Z",
            "completed_at": "2026-05-10T12:00:03Z",
            "message": "slack sim",
            "output": {
                "simulated": True,
                "executed": False,
                "adapter_result": {
                    "adapter": "slack",
                    "action": "send_message",
                    "success": True,
                },
            },
        },
        {
            "step_index": 2,
            "action": "notify_slack",
            "status": "success",
            "mode": "real",
            "executed": True,
            "started_at": "2026-05-10T12:00:04Z",
            "completed_at": "2026-05-10T12:00:05Z",
            "message": "Slack real-mode notification sent.",
            "output": {
                "simulated": False,
                "executed": True,
                "adapter_mode": "real",
                "adapter_result": {
                    "adapter": "slack",
                    "action": "send_message",
                    "success": True,
                    "mode": "real",
                },
            },
        },
        None,
        "not-a-step",
    ]
    cur.execute(
        """
        INSERT INTO playbook_executions (
            playbook_id, alert_id, incident_id, status, started_at, completed_at,
            last_completed_step, steps_log, created_at
        )
        VALUES (
            %s, %s, %s, 'success', NOW(), NOW(), 1, %s, TIMESTAMPTZ '2026-05-10T11:59:00Z'
        )
        RETURNING id
        """,
        ("pb_timeline_test", alert_id, incident["id"], Json(steps_log)),
    )
    ex_id = cur.fetchone()[0]
    exp = datetime.now(timezone.utc) + timedelta(hours=2)
    cur.execute(
        """
        INSERT INTO approval_requests (
            incident_id, playbook_execution_id, playbook_step_index, status, action,
            request_reason, created_at, decided_at, expires_at, approved_by, decided_by
        )
        VALUES (
            %s, %s, 1, 'approved', 'playbook.require_approval', 'gate',
            TIMESTAMPTZ '2026-05-10T12:05:00Z',
            TIMESTAMPTZ '2026-05-10T12:06:00Z',
            %s, %s, %s
        )
        RETURNING id
        """,
        (incident["id"], ex_id, exp, uid, uid),
    )
    ar_id = cur.fetchone()[0]
    cur.execute(
        """
        INSERT INTO approval_request_events (
            approval_request_id, event_type, previous_status, new_status, comment, created_at
        )
        VALUES (%s, 'created', NULL, 'pending', 'req', TIMESTAMPTZ '2026-05-10T12:05:30Z')
        """,
        (ar_id,),
    )
    cur.execute(
        """
        INSERT INTO approval_request_events (
            approval_request_id, event_type, previous_status, new_status, comment, created_at
        )
        VALUES (%s, 'approved', 'pending', 'approved', 'ok', TIMESTAMPTZ '2026-05-10T12:05:45Z')
        """,
        (ar_id,),
    )
    cur.execute(
        """
        INSERT INTO audit_log (event_type, actor_username, details, created_at)
        VALUES (
            'UPDATE_INCIDENT_STATUS',
            'admin',
            %s,
            TIMESTAMPTZ '2026-05-10T12:07:00Z'
        )
        """,
        (Json({"incident_id": incident["id"], "status": "investigating"}),),
    )
    cur.execute(
        """
        INSERT INTO audit_log (event_type, actor_username, details, created_at)
        VALUES (
            'PLAYBOOK_EXECUTION_RESUME',
            'admin',
            %s,
            TIMESTAMPTZ '2026-05-10T12:08:00Z'
        )
        """,
        (Json({"execution_id": ex_id, "playbook_id": "pb_timeline_test"}),),
    )
    cur.execute(
        """
        INSERT INTO audit_log (event_type, actor_username, details, created_at)
        VALUES (
            'SHOULD_NOT_APPEAR',
            'admin',
            %s,
            TIMESTAMPTZ '2026-05-10T12:09:00Z'
        )
        """,
        (Json({"incident_id": 999999, "note": "wrong incident"}),),
    )
    conn.commit()

    counts_before = {}
    for table in (
        "incidents",
        "alerts",
        "playbook_executions",
        "approval_requests",
        "approval_request_events",
        "audit_log",
    ):
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        counts_before[table] = cur.fetchone()[0]

    patchers = _login_role(
        client,
        username="inctimeline",
        login_secret="analystpass",
        role="analyst",
    )
    try:
        with _patched_app_db(conn):
            resp = client.get(f"/incidents/{incident['id']}/timeline")
    finally:
        _stop_patchers(patchers)

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["incident_id"] == incident["id"]
    assert isinstance(body["timeline"], list)
    assert len(body["timeline"]) >= 1

    types = [e["event_type"] for e in body["timeline"]]
    assert "incident_created" in types
    assert "alert_linked" in types
    assert "playbook_execution_created" in types
    assert "playbook_step_completed" in types
    assert "playbook_adapter_simulated" in types
    assert "playbook_adapter_real" in types
    assert "approval_requested" in types
    assert "approval_approved" in types
    assert "audit_event" in types
    assert "SHOULD_NOT_APPEAR" not in [e.get("title") for e in body["timeline"]]

    adapter_ev = next(e for e in body["timeline"] if e["event_type"] == "playbook_adapter_simulated")
    assert adapter_ev["metadata"].get("output", {}).get("adapter") == "slack"
    assert "params" not in str(adapter_ev.get("metadata", {}))

    real_adapter_ev = next(e for e in body["timeline"] if e["event_type"] == "playbook_adapter_real")
    assert real_adapter_ev["metadata"].get("output", {}).get("adapter") == "slack"
    assert real_adapter_ev["summary"] == "Slack real-mode notification sent."
    assert "params" not in str(real_adapter_ev.get("metadata", {}))

    ts_nonempty = [e["timestamp"] for e in body["timeline"] if e.get("timestamp")]
    assert ts_nonempty == sorted(ts_nonempty)

    for table in counts_before:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        assert cur.fetchone()[0] == counts_before[table]


def test_get_incident_timeline_includes_execution_via_linked_alert_fallback(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, source_ip="203.0.113.120")
    incident = _insert_incident(conn, title="Fallback incident", source_ip="203.0.113.121")
    link_alert_to_incident(conn, incident["id"], alert_id)
    conn.commit()
    _seed_playbook_definition(cur, "pb_fallback_tl")
    cur.execute(
        """
        INSERT INTO playbook_executions (
            playbook_id, alert_id, incident_id, status, steps_log, created_at
        )
        VALUES (%s, %s, NULL, 'pending', '[]'::jsonb, NOW())
        RETURNING id
        """,
        ("pb_fallback_tl", alert_id),
    )
    ex_id = cur.fetchone()[0]
    conn.commit()

    patchers = _login_role(
        client,
        username="inctlfallback",
        login_secret="analystpass",
        role="analyst",
    )
    try:
        with _patched_app_db(conn):
            resp = client.get(f"/incidents/{incident['id']}/timeline")
    finally:
        _stop_patchers(patchers)

    assert resp.status_code == 200
    body = resp.get_json()
    meta_exec = next(
        e["metadata"]
        for e in body["timeline"]
        if e["event_type"] == "playbook_execution_created" and e["source_id"] == ex_id
    )
    assert meta_exec.get("via_alert_fallback") is True


def test_get_incident_detail_unchanged_shape(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, source_ip="203.0.113.130")
    incident = _insert_incident(conn, title="Shape check", source_ip="203.0.113.131")
    link_alert_to_incident(conn, incident["id"], alert_id)
    conn.commit()

    patchers = _login_role(
        client,
        username="incshapanalyst",
        login_secret="analystpass",
        role="analyst",
    )
    try:
        with _patched_app_db(conn):
            resp = client.get(f"/incidents/{incident['id']}")
    finally:
        _stop_patchers(patchers)

    assert resp.status_code == 200
    assert set(resp.get_json().keys()) == {"incident"}
    assert "timeline" not in resp.get_json()["incident"]
