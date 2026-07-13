"""Phase 1–2: not_actioned terminal lifecycle for denied/expired approvals."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core import approval_store, dead_letter_store, playbook_store
from engines import playbook_step_executor


def _insert_alert(cur, source_ip="10.0.0.50"):
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message)
        VALUES ('test_alert', 'HIGH', %s::inet, 'msg')
        RETURNING id
        """,
        (source_ip,),
    )
    return cur.fetchone()[0]


def _insert_user(cur, username="not-actioned-approver"):
    cur.execute(
        """
        INSERT INTO users (username, password_hash, role)
        VALUES (%s, 'hash', 'analyst')
        RETURNING id
        """,
        (username,),
    )
    return cur.fetchone()[0]


def _create_execution(conn, cur, playbook_id, steps):
    aid = _insert_alert(cur)
    playbook_store.create_playbook_definition(conn, playbook_id, playbook_id, steps=steps)
    return playbook_store.create_pending_playbook_execution_once(conn, playbook_id, aid)


def _count_dead_letters(cur):
    cur.execute("SELECT COUNT(*) FROM soar_dead_letters")
    return cur.fetchone()[0]


def test_denied_without_branch_reaches_not_actioned_without_dead_letter(postgres_db):
    conn, cur = postgres_db
    user_id = _insert_user(cur)
    before = _count_dead_letters(cur)
    eid = _create_execution(
        conn,
        cur,
        "pb_na_denied",
        steps=[
            {"action": "require_approval", "reason": "Approve block"},
            {"action": "block_ip", "params": {}},
        ],
    )
    playbook_step_executor.process_playbook_execution(conn, eid)
    approval_id = playbook_store.get_playbook_execution(conn, eid)["steps_log"][0][
        "approval_request_id"
    ]
    approval_store.deny_request(conn, approval_id, actor_user_id=user_id)

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "not_actioned"
    assert result["new_status"] == "not_actioned"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "not_actioned"
    assert row["completed_at"] is not None
    assert row["lease_owner"] is None
    assert row["lease_expires_at"] is None
    skipped = [e for e in row["steps_log"] if e.get("event") == "skipped_after_approval_gate"]
    assert any(e["action"] == "block_ip" for e in skipped)
    assert all(e["status"] == "skipped" and e["output"]["executed"] is False for e in skipped)
    assert _count_dead_letters(cur) == before
    assert dead_letter_store.list_dead_letters(conn, execution_id=eid) == []


def test_expired_without_branch_reaches_not_actioned_without_dead_letter(postgres_db):
    conn, cur = postgres_db
    now = datetime.now(timezone.utc)
    before = _count_dead_letters(cur)
    eid = _create_execution(
        conn,
        cur,
        "pb_na_expired",
        steps=[
            {"action": "require_approval", "expires_in_minutes": 5},
            {"action": "block_ip", "params": {}},
        ],
    )
    playbook_step_executor.process_playbook_execution(conn, eid, now=now)

    result = playbook_step_executor.process_playbook_execution(
        conn, eid, now=now + timedelta(minutes=10)
    )

    assert result["outcome"] == "not_actioned"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "not_actioned"
    assert row["steps_log"][-1]["action"] == "block_ip"
    assert row["steps_log"][-1]["status"] == "skipped"
    assert row["steps_log"][-1]["output"]["executed"] is False
    assert _count_dead_letters(cur) == before
    assert dead_letter_store.list_dead_letters(conn, execution_id=eid) == []


def test_not_actioned_is_terminal_for_worker_lease_retry_and_stale_recovery(postgres_db):
    conn, cur = postgres_db
    user_id = _insert_user(cur, username="na-terminal-user")
    eid = _create_execution(
        conn,
        cur,
        "pb_na_terminal",
        steps=[
            {"action": "require_approval", "reason": "gate"},
            {"action": "block_ip", "params": {}},
        ],
    )
    playbook_step_executor.process_playbook_execution(conn, eid)
    approval_id = playbook_store.get_playbook_execution(conn, eid)["steps_log"][0][
        "approval_request_id"
    ]
    approval_store.deny_request(conn, approval_id, actor_user_id=user_id)
    playbook_step_executor.process_playbook_execution(conn, eid)

    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "not_actioned"

    skip = playbook_step_executor.process_playbook_execution(conn, eid, worker_id="worker-z")
    assert skip["outcome"] == "skipped"
    assert skip["reason"] == "terminal_status"
    assert playbook_store.get_playbook_execution(conn, eid)["status"] == "not_actioned"

    assert (
        playbook_store.acquire_execution_lease(conn, eid, "worker-z", lease_duration_seconds=60)
        is None
    )
    assert (
        playbook_store.acquire_awaiting_approval_resume_lease(
            conn, eid, "worker-z", row["steps_log"], 0, lease_duration_seconds=60
        )
        is None
    )
    assert eid not in playbook_store.list_stale_running_playbook_execution_ids(conn)
    assert playbook_store.list_stale_running_executions(conn) == []

    try:
        playbook_store.create_retry_execution(conn, eid)
        assert False, "retry must reject not_actioned"
    except ValueError as err:
        assert "failed or abandoned" in str(err)

    try:
        playbook_store.abandon_playbook_execution(conn, eid)
        assert False, "abandon must reject not_actioned"
    except ValueError as err:
        assert "terminal" in str(err)

    try:
        playbook_store.mark_playbook_execution_permanently_failed(
            conn, eid, failure_reason="nope"
        )
        assert False, "permanently_failed must reject not_actioned"
    except ValueError as err:
        assert "terminal" in str(err) or "only allowed from" in str(err)


def test_not_actioned_is_filterable_via_list_and_update_status(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(
        conn,
        cur,
        "pb_na_filter",
        steps=[{"action": "monitor"}],
    )
    playbook_store.update_execution_status(conn, eid, "not_actioned")
    listed = playbook_store.list_playbook_executions(conn, status="not_actioned", limit=10)
    assert any(row["id"] == eid for row in listed)
    assert "not_actioned" in playbook_store._TERMINAL_EXECUTION_STATUSES
    assert "not_actioned" in playbook_store._VALID_EXECUTION_STATUSES


def test_denied_with_branch_still_succeeds_and_does_not_use_not_actioned(postgres_db):
    conn, cur = postgres_db
    user_id = _insert_user(cur, username="na-branch-user")
    before = _count_dead_letters(cur)
    eid = _create_execution(
        conn,
        cur,
        "pb_na_branch",
        steps=[
            {
                "action": "require_approval",
                "reason": "Approve remediation",
                "on_denied": "branch",
            },
            {
                "action": "branch",
                "condition": {
                    "source": "approval",
                    "field": "status",
                    "op": "==",
                    "value": "denied",
                },
                "goto_true": "denied_path",
            },
            {"action": "monitor"},
            {"label": "denied_path", "action": "flag_high_priority"},
        ],
    )
    playbook_step_executor.process_playbook_execution(conn, eid)
    approval_id = next(
        entry["approval_request_id"]
        for entry in playbook_store.get_playbook_execution(conn, eid)["steps_log"]
        if entry.get("action") == "require_approval"
    )
    approval_store.deny_request(conn, approval_id, actor_user_id=user_id)

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "success"
    assert row["status"] != "not_actioned"
    assert _count_dead_letters(cur) == before


def test_genuine_adapter_failure_still_fails_and_creates_dead_letter(postgres_db):
    conn, cur = postgres_db
    before = _count_dead_letters(cur)
    eid = _create_execution(
        conn,
        cur,
        "pb_na_genuine_fail",
        steps=[{"action": "notify_slack"}],
    )
    failing_result = {
        "adapter": "slack",
        "action": "send_message",
        "mode": "simulation",
        "simulated": True,
        "executed": False,
        "success": False,
        "message": "Simulated adapter failure.",
        "params": {},
        "context": {},
        "metadata": {},
    }

    from unittest.mock import patch

    with patch(
        "engines.playbook_step_executor.execute_playbook_simulated_adapter",
        return_value=failing_result,
    ):
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "failed"
    assert row["status"] != "not_actioned"
    letters = dead_letter_store.list_dead_letters(conn, execution_id=eid)
    assert len(letters) == 1
    assert letters[0]["failure_class"] == "adapter_simulation_failed"
    assert _count_dead_letters(cur) == before + 1
