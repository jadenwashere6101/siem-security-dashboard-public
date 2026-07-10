"""API contracts for Response Registry Phase 2 routes."""

from contextlib import contextmanager
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


def test_list_and_detail_registry_records(postgres_db, client):
    conn, _cur = postgres_db
    registry = upsert_indicator_identity(
        conn, indicator_type="ip", indicator_value="8.8.4.4"
    )
    append_registry_event(
        conn,
        registry_id=registry["id"],
        event_type="monitor_started",
        requested_action="monitor",
        outcome="succeeded",
        disposition_after=DISPOSITION_MONITORED,
        origin_surface=ORIGIN_RESPONSE_REGISTRY,
        reason="api contract",
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


def test_registry_command_monitor_and_stop(postgres_db, client):
    conn, _cur = postgres_db
    with _patched_app_db(conn):
        _login_super_admin(client)
        created = client.post(
            "/response-registry/commands",
            json={
                "action": "monitor",
                "indicator_value": "1.1.1.1",
                "reason": "watch from api",
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
                "idempotency_key": "registry-cmd-stop-1",
            },
        )
        assert stopped.status_code in {200, 201}
        stop_body = stopped.get_json()
        assert stop_body["success"] is True
        assert stop_body["disposition"] == "removed"

        detail = client.get(f"/response-registry/{registry_id}")
        assert detail.status_code == 200
        assert detail.get_json()["record"]["current_disposition"] == "removed"


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
