from psycopg2.extras import Json

from core import playbook_store
from core import soar_response_outcomes as outcomes
from engines import playbook_step_executor


def _insert_alert(cur, source_ip="10.0.0.8"):
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message)
        VALUES ('test_alert', 'HIGH', %s::inet, 'chaining test')
        RETURNING id
        """,
        (source_ip,),
    )
    return cur.fetchone()[0]


def _create_definition(conn, playbook_id, steps, *, enabled=True):
    playbook_store.create_playbook_definition(
        conn,
        playbook_id,
        playbook_id,
        steps=steps,
        enabled=enabled,
    )


def _create_linked_execution(
    conn,
    cur,
    playbook_id,
    steps,
    *,
    alert_id=None,
    parent_execution_id=None,
    chain_depth=0,
):
    if alert_id is None:
        alert_id = _insert_alert(cur)
    _create_definition(conn, playbook_id, steps)
    decision = outcomes.create_response_decision(
        conn,
        selected_action=f"playbook:{playbook_id}",
        decision_source="playbook",
        outcome_summary=f"Playbook {playbook_id} selected for simulation.",
        alert_id=alert_id,
        source_ip="10.0.0.8",
        playbook_id=playbook_id,
    )
    execution_id = playbook_store.create_playbook_execution(
        conn,
        playbook_id,
        alert_id,
        decision_id=decision["id"],
        soar_correlation_id=decision["soar_correlation_id"],
        parent_execution_id=parent_execution_id,
        chain_depth=chain_depth,
    )
    return execution_id, decision


def _set_playbook_steps(cur, playbook_id, steps):
    cur.execute(
        "UPDATE playbook_definitions SET steps = %s WHERE id = %s",
        (Json(steps), playbook_id),
    )


def _child_execution(conn, playbook_id, alert_id):
    return playbook_store.get_active_playbook_execution_for_pair(conn, playbook_id, alert_id)


def _decision_for_execution(cur, execution_id):
    cur.execute(
        """
        SELECT parent_soar_correlation_id, playbook_id, playbook_execution_id
        FROM soar_response_decisions
        WHERE playbook_execution_id = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (execution_id,),
    )
    return cur.fetchone()


def test_playbook_chaining_schema_columns_exist(postgres_db):
    _conn, cur = postgres_db

    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'playbook_executions'
          AND column_name IN ('parent_execution_id', 'chain_depth')
        """
    )
    assert {row[0] for row in cur.fetchall()} == {"parent_execution_id", "chain_depth"}

    cur.execute(
        """
        SELECT indexname
        FROM pg_indexes
        WHERE tablename = 'playbook_executions'
          AND indexname = 'idx_playbook_executions_parent_execution_id'
        """
    )
    assert cur.fetchone() is not None


def test_trigger_playbook_creates_child_execution_and_canonical_parent_link(postgres_db):
    conn, cur = postgres_db
    _create_definition(conn, "child_pb", [{"action": "monitor"}])
    parent_id, parent_decision = _create_linked_execution(
        conn,
        cur,
        "parent_pb",
        [{"action": "trigger_playbook", "params": {"playbook_id": "child_pb"}}],
    )

    result = playbook_step_executor.process_playbook_execution(conn, parent_id)

    assert result["outcome"] == "success"
    parent = playbook_store.get_playbook_execution(conn, parent_id)
    assert parent["status"] == "success"
    child = _child_execution(conn, "child_pb", parent["alert_id"])
    assert child is not None
    assert child["parent_execution_id"] == parent_id
    assert child["chain_depth"] == 1
    assert child["incident_id"] == parent["incident_id"]

    trigger_entry = parent["steps_log"][0]
    assert trigger_entry["status"] == "success"
    assert trigger_entry["event"] == "playbook_triggered"
    assert trigger_entry["child_execution_id"] == child["id"]
    assert trigger_entry["output"]["duplicate"] is False

    child_decision = _decision_for_execution(cur, child["id"])
    assert child_decision == (
        parent_decision["soar_correlation_id"],
        "child_pb",
        child["id"],
    )


def test_parent_success_remains_independent_after_child_failure(postgres_db):
    conn, cur = postgres_db
    _create_definition(conn, "child_fail_pb", [{"action": "monitor"}])
    parent_id, _decision = _create_linked_execution(
        conn,
        cur,
        "parent_success_pb",
        [{"action": "trigger_playbook", "params": {"playbook_id": "child_fail_pb"}}],
    )
    playbook_step_executor.process_playbook_execution(conn, parent_id)
    parent = playbook_store.get_playbook_execution(conn, parent_id)
    child = _child_execution(conn, "child_fail_pb", parent["alert_id"])
    assert child is not None

    _set_playbook_steps(cur, "child_fail_pb", [{"action": "bad_action"}])
    child_result = playbook_step_executor.process_playbook_execution(conn, child["id"])

    assert child_result["outcome"] == "failed"
    assert playbook_store.get_playbook_execution(conn, child["id"])["status"] == "failed"
    assert playbook_store.get_playbook_execution(conn, parent_id)["status"] == "success"


def test_trigger_playbook_fails_closed_at_max_chain_depth(postgres_db):
    conn, cur = postgres_db
    _create_definition(conn, "depth_child_pb", [{"action": "monitor"}])
    parent_id, _decision = _create_linked_execution(
        conn,
        cur,
        "depth_parent_pb",
        [{"action": "trigger_playbook", "params": {"playbook_id": "depth_child_pb"}}],
        chain_depth=playbook_step_executor.MAX_CHAIN_DEPTH,
    )

    result = playbook_step_executor.process_playbook_execution(conn, parent_id)

    assert result["outcome"] == "failed"
    parent = playbook_store.get_playbook_execution(conn, parent_id)
    assert parent["steps_log"][0]["error"]["code"] == "chain_depth_exceeded"
    assert _child_execution(conn, "depth_child_pb", parent["alert_id"]) is None


def test_trigger_playbook_fails_closed_on_ancestor_cycle(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    ancestor_id, _ancestor_decision = _create_linked_execution(
        conn,
        cur,
        "ancestor_pb",
        [{"action": "monitor"}],
        alert_id=alert_id,
    )
    parent_id, _parent_decision = _create_linked_execution(
        conn,
        cur,
        "cycle_parent_pb",
        [{"action": "trigger_playbook", "params": {"playbook_id": "ancestor_pb"}}],
        alert_id=alert_id,
        parent_execution_id=ancestor_id,
        chain_depth=1,
    )

    result = playbook_step_executor.process_playbook_execution(conn, parent_id)

    assert result["outcome"] == "failed"
    parent = playbook_store.get_playbook_execution(conn, parent_id)
    assert parent["steps_log"][0]["error"]["code"] == "chain_cycle_detected"
