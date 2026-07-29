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
        "investigation_hypothesis_evidence",
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


def test_active_investigation_bundle_relationships_and_lifecycle_are_private(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    incident_id = _insert_incident(cur)
    conn.commit()

    with _patched_user("investigator_bundle", role="analyst"):
        _login(client, "investigator_bundle")
        with _patched_workspace_db(conn):
            investigation_response = client.post(
                "/investigations",
                json={
                    "title": "Credential spray review",
                    "linked_alert_id": alert_id,
                    "linked_incident_id": incident_id,
                    "linked_source_ip": "203.0.113.40",
                    "summary": "Initial story",
                    "confidence": "medium",
                    "disposition": "undetermined",
                    "saved_state": {"drawer": "open"},
                },
            )
            investigation = investigation_response.get_json()
            investigation_id = investigation["id"]
            note_response = client.post(
                "/analyst-workspace/notes",
                json={"investigation_id": investigation_id, "body": "Source IP triggered repeated failed logins"},
            )
            hypothesis_response = client.post(
                "/analyst-workspace/hypotheses",
                json={
                    "investigation_id": investigation_id,
                    "title": "Password spray is likely",
                    "body": "Failures fan out across users",
                    "confidence": "medium",
                },
            )
            evidence_response = client.post(
                "/analyst-workspace/evidence",
                json={
                    "investigation_id": investigation_id,
                    "referenced_object_type": "alert",
                    "referenced_object_id": str(alert_id),
                    "label": "Primary alert",
                    "source": "investigation_drawer",
                    "rationale": "Primary trigger",
                    "relationship_type": "context",
                },
            )
            task_response = client.post(
                "/analyst-workspace/tasks",
                json={
                    "investigation_id": investigation_id,
                    "title": "Review MFA outcome",
                    "hypothesis_id": hypothesis_response.get_json()["id"],
                    "evidence_reference_id": evidence_response.get_json()["id"],
                },
            )
            link_response = client.post(
                f"/investigations/{investigation_id}/hypothesis-evidence",
                json={
                    "hypothesis_id": hypothesis_response.get_json()["id"],
                    "evidence_reference_id": evidence_response.get_json()["id"],
                    "relationship_type": "supports",
                    "rationale": "Alert supports spray hypothesis",
                },
            )
            update_link_response = client.patch(
                f"/investigations/hypothesis-evidence/{link_response.get_json()['id']}",
                json={"relationship_type": "refutes", "rationale": "Updated relationship"},
            )
            update_task_response = client.patch(
                f"/analyst-workspace/tasks/{task_response.get_json()['id']}",
                json={"status": "done"},
            )
            update_investigation_response = client.patch(
                f"/investigations/{investigation_id}",
                json={
                    "status": "closed",
                    "confidence": "high",
                    "disposition": "true_positive",
                    "conclusion": "Credential spray confirmed.",
                },
            )
            list_response = client.get("/investigations")
            bundle_response = client.get(f"/investigations/{investigation_id}/workspace")
            delete_link_response = client.delete(f"/investigations/hypothesis-evidence/{link_response.get_json()['id']}")
            delete_evidence_response = client.delete(f"/analyst-workspace/evidence/{evidence_response.get_json()['id']}")

    assert investigation_response.status_code == 201
    assert investigation["owner_username"] == "investigator_bundle"
    assert investigation["visibility"] == "private"
    assert note_response.status_code == 201
    assert hypothesis_response.status_code == 201
    assert hypothesis_response.get_json()["confidence"] == "medium"
    assert evidence_response.status_code == 201
    assert evidence_response.get_json()["rationale"] == "Primary trigger"
    assert task_response.status_code == 201
    assert task_response.get_json()["hypothesis_id"] == hypothesis_response.get_json()["id"]
    assert task_response.get_json()["evidence_reference_id"] == evidence_response.get_json()["id"]
    assert link_response.status_code == 201
    assert link_response.get_json()["relationship_type"] == "supports"
    assert update_link_response.status_code == 200
    assert update_link_response.get_json()["relationship_type"] == "refutes"
    assert update_task_response.status_code == 200
    assert update_task_response.get_json()["status"] == "done"
    assert update_investigation_response.status_code == 200
    assert update_investigation_response.get_json()["status"] == "closed"
    assert update_investigation_response.get_json()["disposition"] == "true_positive"
    assert update_investigation_response.get_json()["confidence"] == "high"
    assert update_investigation_response.get_json()["closed_at"] is not None
    assert list_response.status_code == 200
    assert list_response.get_json()["investigations"][0]["id"] == investigation_id
    assert bundle_response.status_code == 200
    bundle = bundle_response.get_json()
    assert bundle["investigation"]["id"] == investigation_id
    assert bundle["source_context"]["alert"]["id"] == alert_id
    assert bundle["source_context"]["incident"]["id"] == incident_id
    assert bundle["notes"][0]["investigation_id"] == investigation_id
    assert bundle["hypotheses"][0]["investigation_id"] == investigation_id
    assert bundle["tasks"][0]["investigation_id"] == investigation_id
    assert bundle["hypothesis_evidence"][0]["hypothesis_id"] == hypothesis_response.get_json()["id"]
    assert any(event["kind"] == "analyst" for event in bundle["timeline"])
    assert delete_link_response.status_code == 200
    assert delete_evidence_response.status_code == 200

    cur.execute("SELECT status FROM alerts WHERE id = %s", (alert_id,))
    assert cur.fetchone()[0] == "open"
    cur.execute("SELECT status FROM incidents WHERE id = %s", (incident_id,))
    assert cur.fetchone()[0] == "open"
    cur.execute(
        "SELECT event_type, details FROM audit_log WHERE actor_username = 'investigator_bundle' ORDER BY id"
    )
    events = cur.fetchall()
    event_types = [row[0] for row in events]
    assert "INVESTIGATION_HYPOTHESIS_EVIDENCE_LINK" in event_types
    assert "INVESTIGATION_HYPOTHESIS_EVIDENCE_UPDATE" in event_types
    assert "INVESTIGATION_HYPOTHESIS_EVIDENCE_DELETE" in event_types
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


def test_non_owner_cannot_load_active_investigation_or_cross_link_relationships(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()

    with _patched_user("bundle_owner", role="analyst"):
        _login(client, "bundle_owner")
        with _patched_workspace_db(conn):
            investigation_response = client.post(
                "/investigations",
                json={"title": "Private investigation", "linked_alert_id": alert_id},
            )
            investigation_id = investigation_response.get_json()["id"]
            hypothesis_response = client.post(
                "/analyst-workspace/hypotheses",
                json={"investigation_id": investigation_id, "title": "Private hypothesis"},
            )
            evidence_response = client.post(
                "/analyst-workspace/evidence",
                json={
                    "investigation_id": investigation_id,
                    "referenced_object_type": "alert",
                    "referenced_object_id": str(alert_id),
                    "label": "Private evidence",
                },
            )
            missing_ids_response = client.post(
                f"/investigations/{investigation_id}/hypothesis-evidence",
                json={"relationship_type": "supports"},
            )

    assert investigation_response.status_code == 201
    assert missing_ids_response.status_code == 400

    with client.session_transaction() as session:
        session.clear()
    with _patched_user("bundle_intruder", role="analyst"):
        _login(client, "bundle_intruder")
        with _patched_workspace_db(conn):
            bundle_response = client.get(f"/investigations/{investigation_id}/workspace")
            cross_link_response = client.post(
                f"/investigations/{investigation_id}/hypothesis-evidence",
                json={
                    "hypothesis_id": hypothesis_response.get_json()["id"],
                    "evidence_reference_id": evidence_response.get_json()["id"],
                    "relationship_type": "supports",
                },
            )

    assert bundle_response.status_code == 403
    assert cross_link_response.status_code == 403
    assert "Private investigation" not in str(bundle_response.get_json())
    assert "Private evidence" not in str(cross_link_response.get_json())
    cur.execute(
        "SELECT COUNT(*) FROM audit_log WHERE actor_username = 'bundle_intruder' AND event_type = 'INVESTIGATION_WORKSPACE_ACCESS_DENIED'"
    )
    assert cur.fetchone()[0] >= 1


def test_viewer_cannot_access_analyst_workspace(client, mock_db):
    with _patched_user("workspace_viewer", role="viewer"):
        _login(client, "workspace_viewer")
        response = client.get("/analyst-workspace")
    assert response.status_code == 403
