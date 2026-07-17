"""API contracts for Response Registry Phase 2 routes."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from core.indicator_response_registry import append_registry_event, upsert_indicator_identity
from core.response_command_contracts import DISPOSITION_MONITORED, ORIGIN_RESPONSE_REGISTRY


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
    with patch("core.audit_helpers.get_db_connection", return_value=wrapper), patch(
        "routes.response_registry_routes.get_db_connection", return_value=wrapper
    ), patch(
        "routes.blocklist_routes.get_db_connection", return_value=wrapper
    ):
        yield


def _login_super_admin(client):
    resp = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert resp.status_code == 200


def _insert_alert(cur, source_ip="8.8.4.4", alert_type="response_registry_test"):
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message, status)
        VALUES (%s, 'HIGH', %s, %s, 'open')
        RETURNING id
        """,
        (alert_type, source_ip, f"{alert_type} message"),
    )
    return cur.fetchone()[0]


def _insert_incident(cur, source_ip="8.8.4.4"):
    cur.execute(
        """
        INSERT INTO incidents (title, severity, priority, status, source_ip)
        VALUES ('Registry Incident', 'HIGH', 'P2', 'open', %s)
        RETURNING id
        """,
        (source_ip,),
    )
    return cur.fetchone()[0]


def _insert_playbook_execution(cur, alert_id=None, incident_id=None, source_ip="8.8.4.4"):
    cur.execute(
        """
        INSERT INTO playbook_definitions (id, name, trigger_config, steps, enabled)
        VALUES ('registry-test-playbook', 'Registry Test', '{}'::jsonb, '[]'::jsonb, TRUE)
        ON CONFLICT (id) DO NOTHING
        """
    )
    cur.execute(
        """
        INSERT INTO playbook_executions (playbook_id, alert_id, incident_id, status, steps_log)
        VALUES ('registry-test-playbook', %s, %s, 'awaiting_approval', '[]'::jsonb)
        RETURNING id
        """,
        (alert_id, incident_id),
    )
    return cur.fetchone()[0]


def _insert_approval(cur, incident_id):
    cur.execute(
        """
        INSERT INTO approval_requests (incident_id, action, risk_level, expires_at, status)
        VALUES (%s, 'block_ip', 'high', %s, 'pending')
        RETURNING id
        """,
        (incident_id, datetime.now(timezone.utc) + timedelta(hours=1)),
    )
    return cur.fetchone()[0]


def test_list_and_detail_registry_records(postgres_db, client):
    conn, _cur = postgres_db
    registry = upsert_indicator_identity(
        conn, indicator_type="ip", indicator_value="8.8.4.4"
    )
    cur = conn.cursor()
    alert_id = _insert_alert(cur, "8.8.4.4", "registry_relationship_alert")
    incident_id = _insert_incident(cur, "8.8.4.4")
    playbook_execution_id = _insert_playbook_execution(cur, alert_id=alert_id, incident_id=incident_id)
    approval_request_id = _insert_approval(cur, incident_id)
    append_registry_event(
        conn,
        registry_id=registry["id"],
        event_type="monitor_started",
        requested_action="monitor",
        outcome="succeeded",
        disposition_after=DISPOSITION_MONITORED,
        origin_surface=ORIGIN_RESPONSE_REGISTRY,
        reason="api contract",
        alert_id=alert_id,
        incident_id=incident_id,
        playbook_execution_id=playbook_execution_id,
        approval_request_id=approval_request_id,
        idempotency_key="registry-api-monitor-1",
    )
    conn.commit()

    with _patched_app_db(conn):
        _login_super_admin(client)
        listed = client.get("/response-registry?view=monitoring")
        assert listed.status_code == 200
        body = listed.get_json()
        assert body["total"] >= 1
        assert any(item["indicator_value"] == "8.8.4.4" for item in body["items"])

        detail = client.get(f"/response-registry/{registry['id']}")
        assert detail.status_code == 200
        payload = detail.get_json()
        assert payload["record"]["indicator_value"] == "8.8.4.4"
        assert payload["enforcement_statement"]
        assert payload["events"]
        assert payload["relationships"]["alerts"]["primary_id"] == alert_id
        assert payload["relationships"]["incidents"]["primary_id"] == incident_id
        assert payload["relationships"]["playbooks"]["primary_id"] == playbook_execution_id
        assert payload["relationships"]["approvals"]["primary_id"] == approval_request_id
        assert payload["primary_alert"]["alert_type"] == "registry_relationship_alert"
        assert payload["primary_incident"]["status"] == "open"
        assert payload["primary_playbook_execution"]["status"] == "awaiting_approval"
        assert payload["primary_approval_request"]["status"] == "pending"


def test_registry_command_monitor_and_stop(postgres_db, client):
    conn, _cur = postgres_db
    with _patched_app_db(conn):
        _login_super_admin(client)
        cur = conn.cursor()
        alert_id = _insert_alert(cur, "1.1.1.1", "registry_monitor_alert")
        incident_id = _insert_incident(cur, "1.1.1.1")
        playbook_execution_id = _insert_playbook_execution(cur, alert_id=alert_id, incident_id=incident_id)
        approval_request_id = _insert_approval(cur, incident_id)
        conn.commit()
        created = client.post(
            "/response-registry/commands",
            json={
                "action": "monitor",
                "indicator_value": "1.1.1.1",
                "reason": "watch from api",
                "alert_id": alert_id,
                "incident_id": incident_id,
                "playbook_execution_id": playbook_execution_id,
                "approval_request_id": approval_request_id,
                "idempotency_key": "registry-cmd-monitor-1",
            },
        )
        assert created.status_code in {200, 201}
        body = created.get_json()
        assert body["success"] is True
        assert body["disposition"] == "monitored"
        assert body["enforcement"] == "none"
        registry_id = body["registry_record_id"]

        stopped = client.post(
            "/response-registry/commands",
            json={
                "action": "stop_monitor",
                "indicator_value": "1.1.1.1",
                "reason": "done",
                "alert_id": alert_id,
                "incident_id": incident_id,
                "idempotency_key": "registry-cmd-stop-1",
            },
        )
        assert stopped.status_code in {200, 201}
        stop_body = stopped.get_json()
        assert stop_body["success"] is True
        assert stop_body["disposition"] == "removed"

        detail = client.get(f"/response-registry/{registry_id}")
        assert detail.status_code == 200
        payload = detail.get_json()
        assert payload["record"]["current_disposition"] == "removed"
        assert payload["events"][0]["alert_id"] == alert_id
        assert payload["events"][0]["incident_id"] == incident_id


def test_registry_command_rejections_are_actionable(postgres_db, client):
    conn, _cur = postgres_db
    with _patched_app_db(conn):
        _login_super_admin(client)

        invalid = client.post(
            "/response-registry/commands",
            json={"action": "monitor", "indicator_value": "not-an-ip"},
        )
        assert invalid.status_code == 400
        invalid_body = invalid.get_json()
        assert invalid_body["success"] is False
        assert "valid actionable IP" in invalid_body["message"]

        missing_target = client.post(
            "/response-registry/commands",
            json={"action": "monitor"},
        )
        assert missing_target.status_code == 400
        assert "No actionable IP" in missing_target.get_json()["message"]

        protected = client.post(
            "/response-registry/commands",
            json={"action": "block_ip", "indicator_value": "127.0.0.1"},
        )
        assert protected.status_code == 400
        protected_body = protected.get_json()
        assert protected_body["success"] is False
        assert "protected target" in protected_body["message"].lower() or "cannot be blocked" in protected_body["message"].lower()


def test_registry_add_note_requires_reason(postgres_db, client):
    conn, _cur = postgres_db
    with _patched_app_db(conn):
        _login_super_admin(client)
        resp = client.post(
            "/response-registry/commands",
            json={"action": "add_note", "indicator_value": "9.9.9.9"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False


def test_registry_list_limit_offset_and_exact_related_filters(postgres_db, client):
    conn, _cur = postgres_db
    with _patched_app_db(conn):
        _login_super_admin(client)
        cur = conn.cursor()

        first_alert_id = _insert_alert(cur, "8.8.4.4", "registry_related_first")
        first_incident_id = _insert_incident(cur, "8.8.4.4")
        second_alert_id = _insert_alert(cur, "9.9.9.9", "registry_related_second")
        second_incident_id = _insert_incident(cur, "9.9.9.9")

        first_registry = upsert_indicator_identity(
            conn, indicator_type="ip", indicator_value="8.8.4.4"
        )
        second_registry = upsert_indicator_identity(
            conn, indicator_type="ip", indicator_value="9.9.9.9"
        )

        append_registry_event(
            conn,
            registry_id=first_registry["id"],
            event_type="monitor_started",
            requested_action="monitor",
            outcome="succeeded",
            disposition_after=DISPOSITION_MONITORED,
            origin_surface=ORIGIN_RESPONSE_REGISTRY,
            reason="first",
            alert_id=first_alert_id,
            incident_id=first_incident_id,
            idempotency_key="registry-list-first",
        )
        append_registry_event(
            conn,
            registry_id=second_registry["id"],
            event_type="monitor_started",
            requested_action="monitor",
            outcome="succeeded",
            disposition_after=DISPOSITION_MONITORED,
            origin_surface=ORIGIN_RESPONSE_REGISTRY,
            reason="second",
            alert_id=second_alert_id,
            incident_id=second_incident_id,
            idempotency_key="registry-list-second",
        )
        conn.commit()

        paged = client.get("/response-registry?view=monitoring&limit=1&offset=1&sort=indicator_value_asc")
        assert paged.status_code == 200
        paged_body = paged.get_json()
        assert paged_body["total"] >= 2
        assert len(paged_body["items"]) == 1
        assert paged_body["items"][0]["indicator_value"] == "9.9.9.9"

        by_alert = client.get(f"/response-registry?view=monitoring&related_alert_id={first_alert_id}")
        assert by_alert.status_code == 200
        by_alert_body = by_alert.get_json()
        assert [item["indicator_value"] for item in by_alert_body["items"]] == ["8.8.4.4"]

        by_incident = client.get(
            f"/response-registry?view=monitoring&related_incident_id={second_incident_id}"
        )
        assert by_incident.status_code == 200
        by_incident_body = by_incident.get_json()
        assert [item["indicator_value"] for item in by_incident_body["items"]] == ["9.9.9.9"]


def test_registry_invalid_integer_inputs_fail_safely_and_valid_command_ids_are_preserved(postgres_db, client):
    conn, _cur = postgres_db
    with _patched_app_db(conn):
        _login_super_admin(client)
        cur = conn.cursor()

        alert_id = _insert_alert(cur, "1.1.1.1", "registry-valid-provenance")
        incident_id = _insert_incident(cur, "1.1.1.1")
        playbook_execution_id = _insert_playbook_execution(cur, alert_id=alert_id, incident_id=incident_id)
        approval_request_id = _insert_approval(cur, incident_id)
        conn.commit()

        malformed = client.get(
            "/response-registry?limit=bad&offset=bad&actor_user_id=bad"
            "&related_alert_id=bad&related_incident_id=bad&exact_indicator=not-an-ip"
        )
        assert malformed.status_code == 200
        malformed_body = malformed.get_json()
        assert "items" in malformed_body
        assert "total" in malformed_body

        created = client.post(
            "/response-registry/commands",
            json={
                "action": "monitor",
                "indicator_value": "1.1.1.1",
                "reason": "watch from api",
                "alert_id": alert_id,
                "incident_id": incident_id,
                "playbook_execution_id": playbook_execution_id,
                "approval_request_id": approval_request_id,
                "idempotency_key": "registry-cmd-valid-provenance",
            },
        )
        assert created.status_code in {200, 201}
        registry_id = created.get_json()["registry_record_id"]

        detail = client.get(f"/response-registry/{registry_id}")
        assert detail.status_code == 200
        payload = detail.get_json()
        assert payload["events"][0]["alert_id"] == alert_id
        assert payload["events"][0]["incident_id"] == incident_id
        assert payload["events"][0]["playbook_execution_id"] == playbook_execution_id

        ignored_bad_ids = client.post(
            "/response-registry/commands",
            json={
                "action": "add_note",
                "indicator_value": "1.1.1.1",
                "reason": "note with ignored bad ids",
                "alert_id": "bad",
                "incident_id": "bad",
                "playbook_execution_id": "bad",
                "approval_request_id": "bad",
                "idempotency_key": "registry-cmd-ignored-bad-ids",
            },
        )
        assert ignored_bad_ids.status_code in {200, 201}
