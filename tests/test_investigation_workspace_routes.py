from contextlib import contextmanager
from unittest.mock import patch

from werkzeug.security import generate_password_hash


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


def _fake_user(username, password, role):
    return {
        "username": username,
        "password_hash": generate_password_hash(password, method="pbkdf2:sha256"),
        "role": role,
        "is_active": True,
    }


@contextmanager
def _patched_user(username, password="pass", role="analyst"):
    user = _fake_user(username, password, role)
    patchers = [
        patch("routes.auth_routes.get_user_by_username", return_value=user),
        patch("core.auth.get_user_by_username", return_value=user),
    ]
    for patcher in patchers:
        patcher.start()
    try:
        yield
    finally:
        for patcher in reversed(patchers):
            patcher.stop()


@contextmanager
def _patched_workspace_db(conn):
    wrapper = _RouteSafeConnection(conn)
    with patch("routes.investigation_workspace_routes.get_db_connection", return_value=wrapper), patch(
        "core.audit_helpers.get_db_connection", return_value=wrapper
    ):
        yield


def _login(client, username, password="pass"):
    response = client.post("/login", json={"username": username, "password": password})
    assert response.status_code == 200


def _insert_alert(cur, *, status="open"):
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, source, message, status)
        VALUES ('failed_login_threshold', 'HIGH', '203.0.113.40'::inet, 'bank_app', 'failed login burst', %s)
        RETURNING id
        """,
        (status,),
    )
    return cur.fetchone()[0]


def _insert_incident(cur):
    cur.execute(
        """
        INSERT INTO incidents (title, severity, priority, status, source_ip)
        VALUES ('Investigation workspace incident', 'HIGH', 'P2', 'open', '203.0.113.40'::inet)
        RETURNING id
        """
    )
    return cur.fetchone()[0]


def test_investigation_workspace_schema_loaded(postgres_db):
    _conn, cur = postgres_db
    for table_name in [
        "analyst_workspaces",
        "workspace_items",
        "investigations",
        "investigation_notes",
        "investigation_hypotheses",
        "investigation_tasks",
        "evidence_references",
    ]:
        cur.execute("SELECT to_regclass(%s)", (table_name,))
        assert cur.fetchone()[0] == table_name


def test_analyst_workspace_crud_is_private_and_audited(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    incident_id = _insert_incident(cur)
    conn.commit()

    with _patched_user("investigator1", role="analyst"):
        _login(client, "investigator1")
        with _patched_workspace_db(conn):
            workspace_response = client.get("/analyst-workspace")
            pin_response = client.post(
                "/analyst-workspace/pins",
                json={
                    "item_type": "alert",
                    "referenced_object_id": str(alert_id),
                    "label": f"Alert #{alert_id}",
                    "metadata": {"source": "test"},
                },
            )
            update_pin_response = client.patch(
                f"/analyst-workspace/pins/{pin_response.get_json()['id']}",
                json={"label": "Updated alert pin", "item_order": 2},
            )
            reorder_response = client.post(
                "/analyst-workspace/pins/reorder",
                json={"ordered_item_ids": [pin_response.get_json()["id"]]},
            )
            investigation_response = client.post(
                "/investigations",
                json={
                    "title": "Credential spray review",
                    "linked_alert_id": alert_id,
                    "linked_incident_id": incident_id,
                    "saved_state": {"drawer": "open"},
                },
            )
            update_investigation_response = client.patch(
                f"/investigations/{investigation_response.get_json()['id']}",
                json={"status": "investigating", "summary": "Updated summary"},
            )
            note_response = client.post("/analyst-workspace/notes", json={"body": "Initial analyst observation"})
            update_note_response = client.patch(
                f"/analyst-workspace/notes/{note_response.get_json()['id']}",
                json={"body": "Updated analyst observation"},
            )
            hypothesis_response = client.post(
                "/analyst-workspace/hypotheses",
                json={"title": "Password spray is likely", "body": "Multiple failures from one source"},
            )
            update_hypothesis_response = client.patch(
                f"/analyst-workspace/hypotheses/{hypothesis_response.get_json()['id']}",
                json={"status": "supported"},
            )
            task_response = client.post("/analyst-workspace/tasks", json={"title": "Check MFA logs"})
            update_task_response = client.patch(
                f"/analyst-workspace/tasks/{task_response.get_json()['id']}",
                json={"status": "in_progress"},
            )
            evidence_response = client.post(
                "/analyst-workspace/evidence",
                json={"referenced_object_type": "alert", "referenced_object_id": str(alert_id), "label": "Primary alert"},
            )
            update_evidence_response = client.patch(
                f"/analyst-workspace/evidence/{evidence_response.get_json()['id']}",
                json={"label": "Updated primary alert"},
            )

    assert workspace_response.status_code == 200
    assert workspace_response.get_json()["workspace"]["owner_username"] == "investigator1"
    assert pin_response.status_code == 201
    assert pin_response.get_json()["owner_username"] == "investigator1"
    assert update_pin_response.status_code == 200
    assert update_pin_response.get_json()["label"] == "Updated alert pin"
    assert reorder_response.status_code == 200
    assert investigation_response.status_code == 201
    assert investigation_response.get_json()["visibility"] == "private"
    assert update_investigation_response.status_code == 200
    assert update_investigation_response.get_json()["status"] == "investigating"
    assert note_response.status_code == 201
    assert update_note_response.status_code == 200
    assert update_note_response.get_json()["body"] == "Updated analyst observation"
    assert hypothesis_response.status_code == 201
    assert update_hypothesis_response.status_code == 200
    assert update_hypothesis_response.get_json()["status"] == "supported"
    assert task_response.status_code == 201
    assert update_task_response.status_code == 200
    assert update_task_response.get_json()["status"] == "in_progress"
    assert evidence_response.status_code == 201
    assert update_evidence_response.status_code == 200
    assert update_evidence_response.get_json()["label"] == "Updated primary alert"

    cur.execute("SELECT status FROM alerts WHERE id = %s", (alert_id,))
    assert cur.fetchone()[0] == "open"
    cur.execute("SELECT status FROM incidents WHERE id = %s", (incident_id,))
    assert cur.fetchone()[0] == "open"
    cur.execute("SELECT event_type, details FROM audit_log WHERE actor_username = 'investigator1' ORDER BY id")
    events = cur.fetchall()
    event_types = [row[0] for row in events]
    assert "INVESTIGATION_WORKSPACE_PIN" in event_types
    assert "INVESTIGATION_WORKSPACE_UPDATE" in event_types
    assert "INVESTIGATION_WORKSPACE_REORDER" in event_types
    assert "INVESTIGATION_CREATE" in event_types
    assert "INVESTIGATION_UPDATE" in event_types
    assert any(row[1].get("system_mutation") is False for row in events if isinstance(row[1], dict))


def test_non_owner_delete_fails_closed_and_does_not_reveal_private_content(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()

    with _patched_user("owner1", role="analyst"):
        _login(client, "owner1")
        with _patched_workspace_db(conn):
            pin_response = client.post(
                "/analyst-workspace/pins",
                json={"item_type": "alert", "referenced_object_id": str(alert_id), "label": "Private alert"},
            )
    assert pin_response.status_code == 201
    item_id = pin_response.get_json()["id"]

    with client.session_transaction() as session:
        session.clear()
    with _patched_user("owner2", role="analyst"):
        _login(client, "owner2")
        with _patched_workspace_db(conn):
            delete_response = client.delete(f"/analyst-workspace/pins/{item_id}")

    assert delete_response.status_code == 403
    body = delete_response.get_json()
    assert body["error"] == "forbidden"
    assert "Private alert" not in str(body)
    cur.execute("SELECT COUNT(*) FROM workspace_items WHERE id = %s", (item_id,))
    assert cur.fetchone()[0] == 1
    cur.execute(
        "SELECT COUNT(*) FROM audit_log WHERE actor_username = 'owner2' AND event_type = 'INVESTIGATION_WORKSPACE_ACCESS_DENIED'"
    )
    assert cur.fetchone()[0] == 1


def test_viewer_cannot_access_analyst_workspace(client, mock_db):
    with _patched_user("workspace_viewer", role="viewer"):
        _login(client, "workspace_viewer")
        response = client.get("/analyst-workspace")
    assert response.status_code == 403
