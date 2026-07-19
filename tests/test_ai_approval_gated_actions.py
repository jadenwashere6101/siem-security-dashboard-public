from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

from psycopg2.extras import Json
from werkzeug.security import generate_password_hash

from core.ai.action_schemas import (
    ACTION_ADD_ALERT_NOTE,
    ACTION_ADD_INCIDENT_NOTE,
    ACTION_CHANGE_INCIDENT_STATUS,
    ACTION_CREATE_INCIDENT_FROM_ALERT,
    ACTION_CREATE_PLAYBOOK_DRAFT,
    ACTION_UPDATE_DETECTION_RULE_PARAMETERS,
    STATUS_CONFIRMED,
    STATUS_DUPLICATE_SUPPRESSED,
    STATUS_PREVIEW_READY,
    STATUS_STALE_SOURCE,
)


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
def _patched_action_db(conn):
    wrapper = _RouteSafeConnection(conn)
    with patch("core.ai.action_service.get_db_connection", return_value=wrapper), patch(
        "core.audit_helpers.get_db_connection", return_value=wrapper
    ):
        yield


def _fake_user(username: str, password: str, role: str):
    return {
        "username": username,
        "password_hash": generate_password_hash(password, method="pbkdf2:sha256"),
        "role": role,
        "is_active": True,
    }


def _login_role(client, *, role: str):
    username = f"{role}_ai_action_user"
    password = "testpassword123!"
    user = _fake_user(username, password, role)
    patchers = [
        patch("routes.auth_routes.get_user_by_username", return_value=user),
        patch("core.auth.get_user_by_username", return_value=user),
    ]
    for patcher in patchers:
        patcher.start()
    response = client.post("/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return patchers


def _stop_patchers(patchers):
    for patcher in reversed(patchers):
        patcher.stop()


def _insert_alert(cur, *, severity="CRITICAL", source_ip="198.51.100.70"):
    cur.execute(
        """
        INSERT INTO alerts (
            alert_type, severity, source_ip, source, source_type, message, status, context
        )
        VALUES (%s, %s, %s, 'pfsense', 'firewall', 'AI action alert', 'open', %s)
        RETURNING id
        """,
        ("pfsense_firewall_repeated_deny", severity, source_ip, Json({"corroborating_detection_count": 2})),
    )
    return cur.fetchone()[0]


def _insert_incident(cur, *, status="open", source_ip="198.51.100.71"):
    cur.execute(
        """
        INSERT INTO incidents (title, severity, priority, status, source_ip)
        VALUES ('AI action incident', 'HIGH', 'P2', %s, %s)
        RETURNING id
        """,
        (status, source_ip),
    )
    return cur.fetchone()[0]


def _preview(client, payload):
    return client.post("/ai/actions/preview", json=payload)


def _confirm(client, preview_payload, preview):
    return client.post(
        "/ai/actions/confirm",
        json={
            **preview_payload,
            "confirm": True,
            "confirmation_token": preview["confirmation_token"],
            "payload_digest": preview["payload_digest"],
            "target_fingerprint": preview["target_fingerprint"],
        },
    )


def _count(cur, table):
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    return cur.fetchone()[0]


def test_preview_accepts_every_allowlisted_action_without_mutation(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    incident_id = _insert_incident(cur)
    conn.commit()
    before = {
        "alert_notes": _count(cur, "alert_notes"),
        "incident_notes": _count(cur, "incident_notes"),
        "incidents": _count(cur, "incidents"),
        "playbook_definitions": _count(cur, "playbook_definitions"),
        "detection_config": _count(cur, "detection_config"),
        "audit_log": _count(cur, "audit_log"),
    }
    payloads = [
        {"action_type": ACTION_ADD_ALERT_NOTE, "payload": {"alert_id": alert_id, "note_text": "Reviewed alert note"}, "idempotency_key": "ai-preview-alert-note-1"},
        {"action_type": ACTION_ADD_INCIDENT_NOTE, "payload": {"incident_id": incident_id, "note_text": "Reviewed incident note"}, "idempotency_key": "ai-preview-incident-note-1"},
        {"action_type": ACTION_CHANGE_INCIDENT_STATUS, "payload": {"incident_id": incident_id, "status": "investigating"}, "idempotency_key": "ai-preview-incident-status-1"},
        {
            "action_type": ACTION_CREATE_PLAYBOOK_DRAFT,
            "payload": {"playbook_id": "ai_review_playbook", "name": "AI Review Playbook", "steps": [{"action": "monitor", "params": {}}]},
            "idempotency_key": "ai-preview-playbook-1",
        },
        {"action_type": ACTION_UPDATE_DETECTION_RULE_PARAMETERS, "payload": {"rule_id": "failed_login_threshold", "parameters": {"threshold": 7}}, "idempotency_key": "ai-preview-detection-1"},
        {"action_type": ACTION_CREATE_INCIDENT_FROM_ALERT, "payload": {"alert_id": alert_id, "reason": "Create reviewed incident"}, "idempotency_key": "ai-preview-alert-incident-1"},
    ]
    patchers = _login_role(client, role="super_admin")
    try:
        with _patched_action_db(conn):
            for payload in payloads:
                response = _preview(client, payload)
                assert response.status_code == 200
                body = response.get_json()
                assert body["status"] == STATUS_PREVIEW_READY
                assert body["preview"]["requires_confirmation"] is True
                assert body["preview"]["payload"]
    finally:
        _stop_patchers(patchers)

    for table, expected in before.items():
        assert _count(cur, table) == expected


def test_preview_rejects_unsupported_and_smuggled_actions_without_mutation(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()
    before = _count(cur, "alert_notes")
    patchers = _login_role(client, role="analyst")
    try:
        with _patched_action_db(conn):
            unsupported = _preview(
                client,
                {"action_type": "block_ip", "payload": {"alert_id": alert_id}, "idempotency_key": "ai-reject-unsupported-1"},
            )
            smuggled = _preview(
                client,
                {
                    "action_type": ACTION_ADD_ALERT_NOTE,
                    "payload": {"alert_id": alert_id, "note_text": "x", "route": "/admin/users"},
                    "idempotency_key": "ai-reject-smuggled-1",
                },
            )
    finally:
        _stop_patchers(patchers)

    assert unsupported.status_code == 400
    assert smuggled.status_code == 400
    assert _count(cur, "alert_notes") == before


def test_analyst_cannot_preview_super_admin_actions(client, postgres_db):
    conn, cur = postgres_db
    conn.commit()
    patchers = _login_role(client, role="analyst")
    try:
        with _patched_action_db(conn):
            response = _preview(
                client,
                {
                    "action_type": ACTION_UPDATE_DETECTION_RULE_PARAMETERS,
                    "payload": {"rule_id": "failed_login_threshold", "parameters": {"threshold": 4}},
                    "idempotency_key": "ai-rbac-detection-1",
                },
            )
    finally:
        _stop_patchers(patchers)
    assert response.status_code == 403


def test_confirm_adds_incident_note_and_duplicate_does_not_repeat(client, postgres_db):
    conn, cur = postgres_db
    incident_id = _insert_incident(cur)
    conn.commit()
    payload = {
        "action_type": ACTION_ADD_INCIDENT_NOTE,
        "payload": {"incident_id": incident_id, "note_text": "Confirmed incident note"},
        "idempotency_key": "ai-confirm-incident-note-1",
    }
    patchers = _login_role(client, role="analyst")
    try:
        with _patched_action_db(conn):
            preview_response = _preview(client, payload)
            preview = preview_response.get_json()["preview"]
            confirm_response = _confirm(client, payload, preview)
            duplicate_response = _confirm(client, payload, preview)
    finally:
        _stop_patchers(patchers)

    assert confirm_response.status_code == 200
    assert confirm_response.get_json()["status"] == STATUS_CONFIRMED
    assert confirm_response.get_json()["result"]["outcome"] == "real"
    assert duplicate_response.status_code == 200
    assert duplicate_response.get_json()["status"] == STATUS_DUPLICATE_SUPPRESSED
    cur.execute("SELECT note_text FROM incident_notes WHERE incident_id = %s", (incident_id,))
    assert [row[0] for row in cur.fetchall()] == ["Confirmed incident note"]
    cur.execute("SELECT event_type, details FROM audit_log WHERE event_type = 'AI_ACTION_CONFIRMED'")
    audit_rows = cur.fetchall()
    assert len(audit_rows) == 1
    assert audit_rows[0][1]["action_type"] == ACTION_ADD_INCIDENT_NOTE
    assert "Confirmed incident note" not in str(audit_rows[0][1])


def test_confirm_rejects_stale_incident_status_without_mutation(client, postgres_db):
    conn, cur = postgres_db
    incident_id = _insert_incident(cur, status="open")
    conn.commit()
    payload = {
        "action_type": ACTION_CHANGE_INCIDENT_STATUS,
        "payload": {"incident_id": incident_id, "status": "investigating"},
        "idempotency_key": "ai-stale-status-1",
    }
    patchers = _login_role(client, role="analyst")
    try:
        with _patched_action_db(conn):
            preview = _preview(client, payload).get_json()["preview"]
            cur.execute("UPDATE incidents SET status = 'resolved' WHERE id = %s", (incident_id,))
            conn.commit()
            response = _confirm(client, payload, preview)
    finally:
        _stop_patchers(patchers)
    assert response.status_code == 409
    assert response.get_json()["status"] == STATUS_STALE_SOURCE
    cur.execute("SELECT status FROM incidents WHERE id = %s", (incident_id,))
    assert cur.fetchone()[0] == "resolved"


def test_confirm_dispatches_admin_actions_and_create_incident_from_alert(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, severity="CRITICAL", source_ip="198.51.100.88")
    conn.commit()
    payloads = [
        {
            "action_type": ACTION_CREATE_PLAYBOOK_DRAFT,
            "payload": {"playbook_id": "ai_confirm_playbook", "name": "AI Confirm Playbook", "steps": [{"action": "monitor", "params": {}}]},
            "idempotency_key": "ai-confirm-playbook-1",
        },
        {
            "action_type": ACTION_UPDATE_DETECTION_RULE_PARAMETERS,
            "payload": {"rule_id": "failed_login_threshold", "parameters": {"threshold": 6}},
            "idempotency_key": "ai-confirm-detection-1",
        },
        {
            "action_type": ACTION_CREATE_INCIDENT_FROM_ALERT,
            "payload": {"alert_id": alert_id, "reason": "Reviewed escalation"},
            "idempotency_key": "ai-confirm-incident-from-alert-1",
        },
    ]
    patchers = _login_role(client, role="super_admin")
    try:
        with _patched_action_db(conn):
            for payload in payloads:
                preview = _preview(client, payload).get_json()["preview"]
                response = _confirm(client, payload, preview)
                assert response.status_code == 200
                assert response.get_json()["result"]["outcome"] == "real"
    finally:
        _stop_patchers(patchers)

    cur.execute("SELECT enabled FROM playbook_definitions WHERE id = 'ai_confirm_playbook'")
    assert cur.fetchone()[0] is False
    cur.execute("SELECT parameters FROM detection_config WHERE rule_id = 'failed_login_threshold'")
    assert cur.fetchone()[0]["threshold"] == 6
    cur.execute("SELECT COUNT(*) FROM incident_alerts WHERE alert_id = %s", (alert_id,))
    assert cur.fetchone()[0] == 1
