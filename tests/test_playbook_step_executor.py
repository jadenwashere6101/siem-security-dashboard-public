import inspect
import http.client
import smtplib
import socket
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from psycopg2.extras import Json

from core import approval_store, playbook_store
from engines import playbook_step_executor


def _valid_steps():
    return [{"action": "monitor", "params": {}}]


def _insert_alert(cur, source_ip="10.0.0.1"):
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message)
        VALUES ('test_alert', 'LOW', %s::inet, 'msg')
        RETURNING id
        """,
        (source_ip,),
    )
    return cur.fetchone()[0]


def _create_execution(conn, cur, playbook_id="pb_exec", steps=None):
    aid = _insert_alert(cur)
    playbook_store.create_playbook_definition(
        conn,
        playbook_id,
        playbook_id,
        steps=steps if steps is not None else _valid_steps(),
    )
    return playbook_store.create_pending_playbook_execution_once(conn, playbook_id, aid)


def _set_playbook_steps(cur, playbook_id, steps):
    cur.execute(
        "UPDATE playbook_definitions SET steps = %s WHERE id = %s",
        (Json(steps), playbook_id),
    )


def _count(cur, table):
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    return cur.fetchone()[0]


@pytest.fixture
def no_network(monkeypatch):
    def fail_network(*_args, **_kwargs):
        raise AssertionError("network call attempted by playbook adapter simulation")

    monkeypatch.setattr(socket, "socket", fail_network)
    monkeypatch.setattr(smtplib, "SMTP", fail_network)
    monkeypatch.setattr(smtplib, "SMTP_SSL", fail_network)
    monkeypatch.setattr(http.client.HTTPConnection, "request", fail_network)
    monkeypatch.setattr(http.client.HTTPSConnection, "request", fail_network)


def _insert_user(cur, username="playbook-approver"):
    cur.execute(
        """
        INSERT INTO users (username, password_hash, role)
        VALUES (%s, 'hash', 'analyst')
        RETURNING id
        """,
        (username,),
    )
    return cur.fetchone()[0]


def test_no_pending_execution_returns_empty_batch(postgres_db):
    conn, _cur = postgres_db

    assert playbook_step_executor.process_next_pending_playbook_execution(conn) is None
    assert playbook_step_executor.process_playbook_execution_batch(conn) == {
        "processed": 0,
        "success": 0,
        "failed": 0,
        "skipped": 0,
        "results": [],
    }


def test_pending_monitor_step_becomes_success(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_monitor")

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "success"
    assert row["started_at"] is not None
    assert row["completed_at"] is not None
    assert row["last_completed_step"] == 0
    assert len(row["steps_log"]) == 1
    entry = row["steps_log"][0]
    assert entry["action"] == "monitor"
    assert entry["status"] == "success"
    assert entry["mode"] == "simulation"
    assert entry["output"] == {"simulated": True, "executed": False}


def test_multiple_supported_steps_are_simulated_successfully(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(
        conn,
        cur,
        "pb_multi",
        steps=[
            {"action": "monitor", "params": {}},
            {"action": "flag_high_priority", "params": {}},
            {"action": "block_ip", "params": {}},
        ],
    )

    result = playbook_step_executor.process_next_pending_playbook_execution(conn)

    assert result["outcome"] == "success"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "success"
    assert row["last_completed_step"] == 2
    assert [entry["action"] for entry in row["steps_log"]] == [
        "monitor",
        "flag_high_priority",
        "block_ip",
    ]
    for entry in row["steps_log"]:
        assert entry["output"]["simulated"] is True
        assert entry["output"]["executed"] is False
        assert entry["error"] is None


def test_adapter_backed_steps_are_simulated_through_registry(postgres_db, no_network):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_adapter_steps")
    _set_playbook_steps(
        cur,
        "pb_adapter_steps",
        [
            {"action": "notify_slack", "params": {"message": "hello", "token": "secret"}},
            {"action": "notify_email", "params": {"subject": "alert", "password": "secret"}},
            {"action": "block_ip", "params": {"source_ip": "203.0.113.10"}},
            {"action": "notify_webhook", "params": {"payload": {"event": "alert"}}},
        ],
    )
    before = {
        "blocked_ips": _count(cur, "blocked_ips"),
        "response_actions_queue": _count(cur, "response_actions_queue"),
    }

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "success"
    assert row["last_completed_step"] == 3
    expected = [
        ("notify_slack", "slack", "send_message"),
        ("notify_email", "email", "send_email"),
        ("block_ip", "firewall", "block_ip"),
        ("notify_webhook", "webhook", "post_event"),
    ]
    for entry, (step_action, adapter_name, adapter_action) in zip(row["steps_log"], expected):
        assert entry["action"] == step_action
        assert entry["status"] == "success"
        assert entry["mode"] == "simulation"
        assert entry["simulated"] is True
        assert entry["executed"] is False
        assert entry["output"]["simulated"] is True
        assert entry["output"]["executed"] is False
        adapter_result = entry["output"]["adapter_result"]
        assert adapter_result["adapter"] == adapter_name
        assert adapter_result["action"] == adapter_action
        assert adapter_result["mode"] == "simulation"
        assert adapter_result["simulated"] is True
        assert adapter_result["executed"] is False
        assert adapter_result["success"] is True
        assert adapter_result["context"]["execution_id"] == eid
        assert adapter_result["context"]["playbook_id"] == "pb_adapter_steps"

    assert row["steps_log"][0]["output"]["adapter_result"]["params"]["token"] == "[redacted]"
    assert row["steps_log"][1]["output"]["adapter_result"]["params"]["password"] == "[redacted]"
    assert _count(cur, "blocked_ips") == before["blocked_ips"]
    assert _count(cur, "response_actions_queue") == before["response_actions_queue"]


def test_adapter_failure_marks_step_failed_and_respects_continue(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_adapter_failure")
    _set_playbook_steps(
        cur,
        "pb_adapter_failure",
        [
            {"action": "notify_slack", "on_failure": "continue"},
            {"action": "monitor", "params": {}},
        ],
    )

    class FailingAdapter:
        def execute(self, action, params=None, context=None):
            return {
                "adapter": "slack",
                "action": action,
                "mode": "simulation",
                "simulated": True,
                "executed": False,
                "success": False,
                "message": "Simulated adapter failure.",
                "params": params or {},
                "context": context or {},
                "metadata": {},
            }

    with patch(
        "engines.playbook_step_executor.get_integration_adapter",
        return_value=FailingAdapter(),
    ):
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "failed"
    assert row["last_completed_step"] == 1
    assert [entry["status"] for entry in row["steps_log"]] == ["failed", "success"]
    failed = row["steps_log"][0]
    assert failed["output"]["adapter_result"]["success"] is False
    assert failed["output"]["adapter_result"]["simulated"] is True
    assert failed["output"]["adapter_result"]["executed"] is False
    assert failed["error"]["code"] == "adapter_simulation_failed"


def test_non_simulation_integration_mode_fails_closed(postgres_db, monkeypatch, no_network):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_adapter_real_mode")
    _set_playbook_steps(cur, "pb_adapter_real_mode", [{"action": "notify_slack"}])
    monkeypatch.setenv("INTEGRATION_MODE", "real")

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    row = playbook_store.get_playbook_execution(conn, eid)
    entry = row["steps_log"][0]
    assert entry["status"] == "failed"
    assert entry["error"]["code"] == "adapter_simulation_failed"
    assert "real integration mode is not implemented" in entry["message"]
    assert entry["output"]["simulated"] is True
    assert entry["output"]["executed"] is False
    assert _count(cur, "blocked_ips") == 0
    assert _count(cur, "response_actions_queue") == 0


def test_require_approval_pauses_execution_and_creates_linked_request(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(
        conn,
        cur,
        "pb_approval_gate",
        steps=[
            {"action": "monitor", "params": {}},
            {
                "action": "require_approval",
                "risk_level": "critical",
                "reason": "Approve simulated block before continuing",
                "expires_in_minutes": 20,
            },
            {"action": "block_ip", "params": {}},
        ],
    )

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "awaiting_approval"
    assert result["new_status"] == "awaiting_approval"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "awaiting_approval"
    assert row["completed_at"] is None
    assert row["last_completed_step"] == 0
    assert [entry["action"] for entry in row["steps_log"]] == ["monitor", "require_approval"]

    approval_entry = row["steps_log"][1]
    assert approval_entry["event"] == "approval_requested"
    assert approval_entry["status"] == "awaiting_approval"
    assert approval_entry["mode"] == "simulation"
    assert approval_entry["simulated"] is True
    assert approval_entry["executed"] is False
    assert approval_entry["output"] == {
        "simulated": True,
        "executed": False,
        "approval_gate": True,
    }
    assert approval_entry["approval_status"] == "pending"
    assert approval_entry["risk_level"] == "critical"
    assert "Approve simulated block" in approval_entry["message"]

    cur.execute(
        """
        SELECT id, playbook_execution_id, playbook_step_index, status, action, risk_level,
               request_reason
        FROM approval_requests
        WHERE playbook_execution_id = %s
        """,
        (eid,),
    )
    approvals = cur.fetchall()
    assert len(approvals) == 1
    approval = approvals[0]
    assert approval[0] == approval_entry["approval_request_id"]
    assert approval[1] == eid
    assert approval[2] == 1
    assert approval[3] == "pending"
    assert approval[4] == "playbook.require_approval"
    assert approval[5] == "critical"
    assert approval[6] == "Approve simulated block before continuing"

    assert _count(cur, "response_actions_queue") == 0
    assert _count(cur, "response_actions_log") == 0


def test_require_approval_pending_rerun_does_not_duplicate_request_or_steps(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(
        conn,
        cur,
        "pb_approval_rerun",
        steps=[
            {"action": "require_approval", "reason": "Pause here"},
            {"action": "monitor", "params": {}},
        ],
    )

    first = playbook_step_executor.process_playbook_execution(conn, eid)
    before = playbook_store.get_playbook_execution(conn, eid)
    second = playbook_step_executor.process_playbook_execution(conn, eid)
    after = playbook_store.get_playbook_execution(conn, eid)

    assert first["outcome"] == "awaiting_approval"
    assert second["outcome"] == "skipped"
    assert second["reason"] == "approval_pending"
    assert after["status"] == "awaiting_approval"
    assert after["steps_log"] == before["steps_log"]

    cur.execute(
        """
        SELECT COUNT(*)
        FROM approval_requests
        WHERE playbook_execution_id = %s AND playbook_step_index = 0
        """,
        (eid,),
    )
    assert cur.fetchone()[0] == 1


def test_approved_approval_resumes_from_next_step(postgres_db):
    conn, cur = postgres_db
    user_id = _insert_user(cur)
    eid = _create_execution(
        conn,
        cur,
        "pb_approval_resume",
        steps=[
            {"action": "monitor", "params": {}},
            {"action": "require_approval", "reason": "Approve next simulated step"},
            {"action": "block_ip", "params": {}},
        ],
    )
    pause = playbook_step_executor.process_playbook_execution(conn, eid)
    approval_id = playbook_store.get_playbook_execution(conn, eid)["steps_log"][1][
        "approval_request_id"
    ]
    approval_store.approve_request(conn, approval_id, actor_user_id=user_id)

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert pause["outcome"] == "awaiting_approval"
    assert result["outcome"] == "success"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "success"
    assert row["last_completed_step"] == 2
    events = [entry.get("event") for entry in row["steps_log"]]
    assert events == [
        None,
        "approval_requested",
        "approval_approved",
        "approval_resumed",
        None,
    ]
    assert row["steps_log"][-1]["action"] == "block_ip"
    assert row["steps_log"][-1]["output"]["simulated"] is True
    assert row["steps_log"][-1]["output"]["executed"] is False
    assert row["steps_log"][-1]["output"]["adapter_result"]["adapter"] == "firewall"
    assert _count(cur, "response_actions_queue") == 0
    assert _count(cur, "response_actions_log") == 0

    rerun = playbook_step_executor.process_playbook_execution(conn, eid)
    assert rerun["outcome"] == "skipped"
    assert rerun["reason"] == "terminal_status"


def test_denied_approval_fails_and_skips_later_steps(postgres_db):
    conn, cur = postgres_db
    user_id = _insert_user(cur)
    eid = _create_execution(
        conn,
        cur,
        "pb_approval_denied",
        steps=[
            {"action": "require_approval", "reason": "Approve later steps"},
            {"action": "block_ip", "params": {}},
            {"action": "monitor", "params": {}},
        ],
    )
    playbook_step_executor.process_playbook_execution(conn, eid)
    approval_id = playbook_store.get_playbook_execution(conn, eid)["steps_log"][0][
        "approval_request_id"
    ]
    approval_store.deny_request(conn, approval_id, actor_user_id=user_id)

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "failed"
    assert row["last_completed_step"] is None
    assert [entry.get("event") for entry in row["steps_log"]] == [
        "approval_requested",
        "approval_denied",
        "skipped_after_approval_gate",
        "skipped_after_approval_gate",
    ]
    skipped = row["steps_log"][2:]
    assert [entry["action"] for entry in skipped] == ["block_ip", "monitor"]
    assert all(entry["status"] == "skipped" for entry in skipped)
    assert all(entry["output"]["executed"] is False for entry in skipped)
    assert _count(cur, "response_actions_queue") == 0


def test_expired_approval_fails_and_skips_later_steps(postgres_db):
    conn, cur = postgres_db
    now = datetime.now(timezone.utc)
    eid = _create_execution(
        conn,
        cur,
        "pb_approval_expired",
        steps=[
            {"action": "require_approval", "expires_in_minutes": 5},
            {"action": "block_ip", "params": {}},
        ],
    )
    playbook_step_executor.process_playbook_execution(conn, eid, now=now)

    result = playbook_step_executor.process_playbook_execution(
        conn,
        eid,
        now=now + timedelta(minutes=10),
    )

    assert result["outcome"] == "failed"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "failed"
    assert [entry.get("event") for entry in row["steps_log"]] == [
        "approval_requested",
        "approval_expired",
        "skipped_after_approval_gate",
    ]
    assert row["steps_log"][2]["action"] == "block_ip"
    assert row["steps_log"][2]["status"] == "skipped"
    cur.execute(
        "SELECT status FROM approval_requests WHERE playbook_execution_id = %s",
        (eid,),
    )
    assert cur.fetchone()[0] == "expired"


def test_batch_processes_approved_awaiting_approval_execution(postgres_db):
    conn, cur = postgres_db
    user_id = _insert_user(cur)
    eid = _create_execution(
        conn,
        cur,
        "pb_batch_approval_resume",
        steps=[
            {"action": "require_approval", "reason": "Approve batch resume"},
            {"action": "monitor", "params": {}},
        ],
    )
    playbook_step_executor.process_playbook_execution(conn, eid)
    approval_id = playbook_store.get_playbook_execution(conn, eid)["steps_log"][0][
        "approval_request_id"
    ]
    approval_store.approve_request(conn, approval_id, actor_user_id=user_id)

    result = playbook_step_executor.process_playbook_execution_batch(conn, limit=5)

    assert result["processed"] == 1
    assert result["success"] == 1
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "success"
    assert row["steps_log"][-1]["action"] == "monitor"


def test_unsupported_step_action_marks_execution_failed(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_bad")
    cur.execute(
        "UPDATE playbook_definitions SET steps = %s::jsonb WHERE id = %s",
        ('[{"action": "bad_action", "params": {}}]', "pb_bad"),
    )

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "failed"
    assert row["last_completed_step"] is None
    assert row["steps_log"][0]["status"] == "failed"
    assert row["steps_log"][0]["error"]["code"] == "unsupported_action"
    assert row["steps_log"][0]["output"]["simulated"] is True
    assert row["steps_log"][0]["output"]["executed"] is False


def test_on_failure_continue_records_later_success_but_execution_failed(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_continue")
    cur.execute(
        "UPDATE playbook_definitions SET steps = %s::jsonb WHERE id = %s",
        (
            '[{"action": "bad_action", "on_failure": "continue"}, {"action": "monitor"}]',
            "pb_continue",
        ),
    )

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "failed"
    assert row["last_completed_step"] == 1
    assert [entry["status"] for entry in row["steps_log"]] == ["failed", "success"]


def test_invalid_steps_root_marks_execution_failed(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_invalid_steps")

    with patch(
        "engines.playbook_step_executor.playbook_store.get_playbook_definition",
        return_value={"id": "pb_invalid_steps", "steps": {"not": "a-list"}},
    ):
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "failed"
    assert row["steps_log"][0]["error"]["code"] == "invalid_steps"


def test_missing_definition_marks_execution_failed(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_missing")

    with patch(
        "engines.playbook_step_executor.playbook_store.get_playbook_definition",
        return_value=None,
    ):
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "failed"
    assert row["steps_log"][0]["error"]["code"] == "definition_not_found"


def test_terminal_success_execution_is_not_rerun(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_done")
    playbook_step_executor.process_playbook_execution(conn, eid)
    before = playbook_store.get_playbook_execution(conn, eid)

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    after = playbook_store.get_playbook_execution(conn, eid)
    assert result["outcome"] == "skipped"
    assert result["reason"] == "terminal_status"
    assert after["steps_log"] == before["steps_log"]
    assert after["status"] == "success"


def test_running_execution_is_skipped(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_running")
    playbook_store.set_playbook_execution_running(conn, eid)

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "skipped"
    assert result["reason"] == "already_running"


def test_batch_processing_respects_limit(postgres_db):
    conn, cur = postgres_db
    first = _create_execution(conn, cur, "pb_one")
    second = _create_execution(conn, cur, "pb_two", steps=[{"action": "flag_high_priority"}])

    result = playbook_step_executor.process_playbook_execution_batch(conn, limit=1)

    assert result["processed"] == 1
    assert result["success"] == 1
    statuses = {
        first: playbook_store.get_playbook_execution(conn, first)["status"],
        second: playbook_store.get_playbook_execution(conn, second)["status"],
    }
    assert sorted(statuses.values()) == ["pending", "success"]


def test_executor_does_not_create_queue_logs_or_approvals(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_no_side_effects", steps=[{"action": "block_ip"}])
    before = {
        "response_actions_queue": _count(cur, "response_actions_queue"),
        "response_actions_log": _count(cur, "response_actions_log"),
        "approval_requests": _count(cur, "approval_requests"),
    }

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    for table, expected in before.items():
        assert _count(cur, table) == expected


def test_executor_module_has_no_real_execution_imports():
    source = inspect.getsource(playbook_step_executor)
    forbidden = [
        "soar_adapters",
        "AdapterBackedExecutor",
        "SimulationExecutor",
        "enqueue_response_action",
        "enqueue_committed_alerts",
        "requests",
        "subprocess",
        "socket",
        "urllib",
    ]
    for token in forbidden:
        assert token not in source
