import inspect
from unittest.mock import patch

from core import playbook_store
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


def _count(cur, table):
    cur.execute(f"SELECT COUNT(*) FROM {table}")
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
        "approval_store",
        "requests",
        "subprocess",
        "socket",
        "urllib",
    ]
    for token in forbidden:
        assert token not in source
