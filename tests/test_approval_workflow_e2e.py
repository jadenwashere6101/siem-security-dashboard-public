from contextlib import contextmanager
from unittest.mock import patch

from core import playbook_store
from engines import playbook_step_executor


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
def _patched_workflow_routes(conn):
    wrapper = _RouteSafeConnection(conn)
    with patch("routes.playbook_routes.get_db_connection", return_value=wrapper), patch(
        "routes.approval_routes.get_db_connection", return_value=wrapper
    ), patch("core.audit_helpers.get_db_connection", return_value=wrapper), patch(
        "routes.auth_routes.log_audit_event"
    ), patch(
        "routes.playbook_routes.log_audit_event"
    ):
        yield


def _login_super_admin(client):
    resp = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert resp.status_code == 200


def _insert_admin_db_user(cur):
    cur.execute(
        """
        INSERT INTO users (username, password_hash, role)
        VALUES ('admin', 'sentinel_hash', 'super_admin')
        RETURNING id
        """,
    )
    return cur.fetchone()[0]


def _insert_alert(cur):
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message)
        VALUES ('approval_workflow_test', 'HIGH', '203.0.113.250'::inet, 'approval workflow')
        RETURNING id
        """,
    )
    return cur.fetchone()[0]


def test_playbook_approval_request_can_be_decided_end_to_end(client, postgres_db):
    conn, cur = postgres_db
    _insert_admin_db_user(cur)
    conn.commit()

    with _patched_workflow_routes(conn):
        _login_super_admin(client)

        create_resp = client.post(
            "/playbooks",
            json={
                "id": "approval-workflow-e2e",
                "name": "Approval Workflow E2E",
                "description": "Simulation-only approval workflow contract test.",
                "trigger_config": {"source": "test"},
                "enabled": True,
                "steps": [
                    {"action": "monitor", "params": {}},
                    {
                        "action": "require_approval",
                        "risk_level": "critical",
                        "reason": "Approve simulated containment before continuing",
                        "expires_in_minutes": 30,
                    },
                    {"action": "monitor", "params": {}},
                ],
            },
        )
        assert create_resp.status_code == 201

        alert_id = _insert_alert(cur)
        execution_id = playbook_store.create_pending_playbook_execution_once(
            conn,
            "approval-workflow-e2e",
            alert_id,
        )
        conn.commit()
        assert execution_id is not None

        pause_result = playbook_step_executor.process_playbook_execution(conn, execution_id)
        conn.commit()
        assert pause_result["outcome"] == "awaiting_approval"

        execution = playbook_store.get_playbook_execution(conn, execution_id)
        assert execution["status"] == "awaiting_approval"
        approval_gate = execution["steps_log"][1]
        assert approval_gate["action"] == "require_approval"
        assert approval_gate["approval_status"] == "pending"
        approval_id = approval_gate["approval_request_id"]

        pending_resp = client.get("/approvals?status=pending")
        assert pending_resp.status_code == 200
        pending_items = pending_resp.get_json()["approvals"]
        pending_approval = next(item for item in pending_items if item["id"] == approval_id)
        assert pending_approval["status"] == "pending"
        assert pending_approval["action"] == "playbook.require_approval"
        assert pending_approval["playbook_execution_id"] == execution_id
        assert pending_approval["playbook_step_index"] == 1

        detail_resp = client.get(f"/approvals/{approval_id}")
        assert detail_resp.status_code == 200
        detail = detail_resp.get_json()["approval"]
        assert detail["status"] == "pending"
        assert [event["event_type"] for event in detail["events"]] == ["created"]

        decision_resp = client.post(
            f"/approvals/{approval_id}/decision",
            json={"decision": "approved", "reason": "operator approved simulation"},
        )
        assert decision_resp.status_code == 200
        approved = decision_resp.get_json()["approval"]
        assert approved["status"] == "approved"
        assert approved["decision_comment"] == "operator approved simulation"
        assert approved["decided_at"] is not None

        approved_detail_resp = client.get(f"/approvals/{approval_id}")
        assert approved_detail_resp.status_code == 200
        approved_detail = approved_detail_resp.get_json()["approval"]
        assert approved_detail["status"] == "approved"
        assert [event["event_type"] for event in approved_detail["events"]] == [
            "created",
            "approved",
        ]
        assert approved_detail["events"][-1]["previous_status"] == "pending"
        assert approved_detail["events"][-1]["new_status"] == "approved"
        assert approved_detail["events"][-1]["comment"] == "operator approved simulation"

        approved_list_resp = client.get("/approvals?status=approved")
        assert approved_list_resp.status_code == 200
        approved_ids = {item["id"] for item in approved_list_resp.get_json()["approvals"]}
        assert approval_id in approved_ids

        second_decision_resp = client.post(
            f"/approvals/{approval_id}/decision",
            json={"decision": "denied", "reason": "second decision should fail"},
        )
        assert second_decision_resp.status_code == 400
        assert "not pending" in second_decision_resp.get_json()["error"]
