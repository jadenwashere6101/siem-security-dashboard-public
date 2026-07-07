from unittest.mock import patch

import pytest
from psycopg2.extras import Json

from core import approval_store, playbook_store
from core import soar_response_outcomes as outcomes
from engines import playbook_step_executor


def _insert_alert(cur, *, severity="HIGH", alert_type="failed_login_threshold"):
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message)
        VALUES (%s, %s, '10.0.0.8'::inet, 'branch test')
        RETURNING id
        """,
        (alert_type, severity),
    )
    return cur.fetchone()[0]


def _create_execution(conn, cur, playbook_id, steps, *, severity="HIGH"):
    aid = _insert_alert(cur, severity=severity)
    playbook_store.create_playbook_definition(
        conn,
        playbook_id,
        playbook_id,
        steps=steps,
    )
    return playbook_store.create_pending_playbook_execution_once(conn, playbook_id, aid)


def _create_linked_execution(conn, cur, playbook_id, steps, *, severity="HIGH"):
    aid = _insert_alert(cur, severity=severity)
    playbook_store.create_playbook_definition(
        conn,
        playbook_id,
        playbook_id,
        steps=steps,
    )
    decision = outcomes.create_response_decision(
        conn,
        selected_action=f"playbook:{playbook_id}",
        decision_source="playbook",
        outcome_summary=f"Playbook {playbook_id} selected for simulation.",
        alert_id=aid,
        source_ip="10.0.0.8",
        playbook_id=playbook_id,
    )
    return playbook_store.create_playbook_execution(
        conn,
        playbook_id,
        aid,
        decision_id=decision["id"],
        soar_correlation_id=decision["soar_correlation_id"],
    )


def test_branch_true_jumps_forward_and_skips_intermediate_steps(postgres_db):
    conn, cur = postgres_db
    steps = [
        {"action": "monitor"},
        {
            "action": "branch",
            "condition": {
                "source": "alert",
                "field": "severity",
                "op": ">=",
                "value": "high",
            },
            "goto_true": "target_step",
        },
        {"action": "flag_high_priority"},
        {"label": "target_step", "action": "monitor", "params": {}},
    ]
    eid = _create_execution(conn, cur, "pb_branch_true", steps)

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    row = playbook_store.get_playbook_execution(conn, eid)
    statuses = {entry["step_index"]: entry["status"] for entry in row["steps_log"]}
    assert statuses[1] == "success"
    assert statuses[1] and row["steps_log"][1]["event"] == "branch_evaluated"
    assert row["steps_log"][1]["condition"]["field"] == "severity"
    assert row["steps_log"][1]["result"] is True
    assert row["steps_log"][1]["goto_label"] == "target_step"
    assert row["steps_log"][1]["goto_step_index"] == 3
    assert statuses[2] == "skipped"
    assert row["steps_log"][2]["event"] == "skipped_by_branch"
    assert row["steps_log"][2]["skip_reason"] == "branch_not_taken"
    assert statuses[3] == "success"


def test_branch_false_falls_through_without_skips(postgres_db):
    conn, cur = postgres_db
    steps = [
        {
            "action": "branch",
            "condition": {
                "source": "alert",
                "field": "severity",
                "op": ">=",
                "value": "critical",
            },
            "goto_true": "never_reached",
        },
        {"action": "monitor"},
        {"label": "never_reached", "action": "flag_high_priority"},
    ]
    eid = _create_execution(conn, cur, "pb_branch_false", steps, severity="LOW")

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    row = playbook_store.get_playbook_execution(conn, eid)
    executed_indexes = {entry["step_index"] for entry in row["steps_log"]}
    assert executed_indexes == {0, 1, 2}
    branch_entry = row["steps_log"][0]
    assert branch_entry["output"]["result"] is False
    assert branch_entry["output"]["goto_step_index"] == 1


def test_branch_goto_false_jumps_on_false_condition(postgres_db):
    conn, cur = postgres_db
    steps = [
        {
            "action": "branch",
            "condition": {
                "source": "alert",
                "field": "severity",
                "op": ">=",
                "value": "critical",
            },
            "goto_true": "high_path",
            "goto_false": "low_path",
        },
        {"label": "high_path", "action": "flag_high_priority"},
        {"action": "monitor"},
        {"label": "low_path", "action": "monitor"},
    ]
    eid = _create_execution(conn, cur, "pb_branch_goto_false", steps, severity="LOW")

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    row = playbook_store.get_playbook_execution(conn, eid)
    statuses = {entry["step_index"]: entry["status"] for entry in row["steps_log"]}
    assert statuses[0] == "success"
    assert statuses[1] == "skipped"
    assert statuses[2] == "skipped"
    assert statuses[3] == "success"


def test_branch_missing_alert_field_fails_closed(postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message)
        VALUES ('failed_login_threshold', 'HIGH', '10.0.0.9'::inet, 'msg')
        RETURNING id
        """
    )
    aid = cur.fetchone()[0]
    playbook_store.create_playbook_definition(
        conn,
        "pb_branch_missing_field",
        "pb_branch_missing_field",
        steps=[
            {
                "action": "branch",
                "condition": {
                    "source": "alert",
                    "field": "reputation_score",
                    "op": ">=",
                    "value": 50,
                },
                "goto_true": "target",
            },
            {"label": "target", "action": "monitor"},
        ],
    )
    eid = playbook_store.create_pending_playbook_execution_once(
        conn, "pb_branch_missing_field", aid
    )

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    entry = playbook_store.get_playbook_execution(conn, eid)["steps_log"][0]
    assert entry["error"]["code"] == "binding_field_missing"


def test_branch_without_alert_context_fails_closed(postgres_db):
    conn, cur = postgres_db
    playbook_store.create_playbook_definition(
        conn,
        "pb_branch_no_alert",
        "pb_branch_no_alert",
        steps=[
            {
                "action": "branch",
                "condition": {
                    "source": "alert",
                    "field": "severity",
                    "op": "==",
                    "value": "high",
                },
                "goto_true": "target",
            },
            {"label": "target", "action": "monitor"},
        ],
    )
    eid = playbook_store.create_playbook_execution(conn, "pb_branch_no_alert", None)

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    entry = playbook_store.get_playbook_execution(conn, eid)["steps_log"][0]
    assert entry["error"]["code"] == "binding_alert_context_missing"


def test_branch_without_approval_context_fails_closed(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(
        conn,
        cur,
        "pb_branch_missing_approval",
        steps=[
            {
                "action": "branch",
                "condition": {
                    "source": "approval",
                    "field": "status",
                    "op": "==",
                    "value": "denied",
                },
                "goto_true": "target",
            },
            {"label": "target", "action": "monitor"},
        ],
    )

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    entry = playbook_store.get_playbook_execution(conn, eid)["steps_log"][0]
    assert entry["error"]["code"] == "branch_context_missing"


def test_branch_runtime_unresolved_target_fails_closed(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(
        conn,
        cur,
        "pb_branch_bad_runtime_target",
        steps=[
            {
                "action": "branch",
                "condition": {
                    "source": "alert",
                    "field": "severity",
                    "op": ">=",
                    "value": "high",
                },
                "goto_true": "target",
            },
            {"label": "target", "action": "monitor"},
        ],
    )
    cur.execute(
        """
        UPDATE playbook_definitions
        SET steps = %s
        WHERE id = 'pb_branch_bad_runtime_target'
        """,
        (
            Json(
                [
                    {
                        "action": "branch",
                        "condition": {
                            "source": "alert",
                            "field": "severity",
                            "op": ">=",
                            "value": "high",
                        },
                        "goto_true": "missing",
                    },
                ]
            ),
        ),
    )

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    entry = playbook_store.get_playbook_execution(conn, eid)["steps_log"][0]
    assert entry["error"]["code"] == "branch_target_not_found"


def test_branch_step_appends_existing_outcome_event(postgres_db):
    conn, cur = postgres_db
    eid = _create_linked_execution(
        conn,
        cur,
        "pb_branch_outcome",
        steps=[
            {
                "action": "branch",
                "condition": {
                    "source": "alert",
                    "field": "severity",
                    "op": ">=",
                    "value": "high",
                },
                "goto_true": "target",
            },
            {"label": "target", "action": "monitor"},
        ],
    )

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    cur.execute(
        """
        SELECT event_type, playbook_step_index, metadata
        FROM soar_response_outcome_events
        WHERE playbook_execution_id = %s
        ORDER BY id
        """,
        (eid,),
    )
    events = cur.fetchall()
    branch_events = [event for event in events if event[1] == 0]
    assert branch_events[0][0] == "step_succeeded"
    assert branch_events[0][2]["action"] == "branch"


def test_approval_denied_with_branch_continues_to_next_step(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(
        conn,
        cur,
        "pb_approval_branch",
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
    cur.execute(
        """
        INSERT INTO users (username, password_hash, role)
        VALUES ('branch-approver', 'hash', 'analyst')
        RETURNING id
        """
    )
    user_id = cur.fetchone()[0]

    pause = playbook_step_executor.process_playbook_execution(conn, eid)
    assert pause["outcome"] == "awaiting_approval"
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
    assert any(entry.get("label") == "denied_path" and entry["status"] == "success" for entry in row["steps_log"])


def test_approval_denied_default_still_fails_execution(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(
        conn,
        cur,
        "pb_approval_fail_default",
        steps=[
            {"action": "require_approval", "reason": "Approve remediation"},
            {"action": "monitor"},
        ],
    )
    cur.execute(
        """
        INSERT INTO users (username, password_hash, role)
        VALUES ('branch-approver-2', 'hash', 'analyst')
        RETURNING id
        """
    )
    user_id = cur.fetchone()[0]

    playbook_step_executor.process_playbook_execution(conn, eid)
    approval_id = next(
        entry["approval_request_id"]
        for entry in playbook_store.get_playbook_execution(conn, eid)["steps_log"]
        if entry.get("action") == "require_approval"
    )
    approval_store.deny_request(conn, approval_id, actor_user_id=user_id)

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    assert playbook_store.get_playbook_execution(conn, eid)["status"] == "failed"
