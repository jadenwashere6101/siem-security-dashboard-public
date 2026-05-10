from datetime import datetime, timedelta, timezone

import pytest
import psycopg2

from core import playbook_store


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


@pytest.mark.usefixtures("postgres_db")
def test_list_enabled_empty(postgres_db):
    conn, _cur = postgres_db
    assert playbook_store.list_enabled_playbook_definitions(conn) == []


@pytest.mark.usefixtures("postgres_db")
def test_list_enabled_returns_inserted_and_orders_by_id(postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(
        conn,
        "pb_b",
        "Second",
        steps=_valid_steps(),
        trigger_config={"alert_type": "password_spraying"},
    )
    playbook_store.create_playbook_definition(
        conn,
        "pb_a",
        "First",
        steps=_valid_steps(),
        trigger_config={},
    )
    rows = playbook_store.list_enabled_playbook_definitions(conn)
    assert [r["id"] for r in rows] == ["pb_a", "pb_b"]


@pytest.mark.usefixtures("postgres_db")
def test_list_enabled_excludes_disabled(postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(
        conn,
        "pb_off",
        "Off",
        steps=_valid_steps(),
        enabled=False,
    )
    assert playbook_store.list_enabled_playbook_definitions(conn) == []


@pytest.mark.usefixtures("postgres_db")
def test_get_playbook_definition_round_trip(postgres_db):
    conn, _cur = postgres_db
    tc = {"alert_type": "password_spraying", "min_severity": "HIGH"}
    playbook_store.create_playbook_definition(
        conn,
        "pb_one",
        "One",
        steps=_valid_steps(),
        trigger_config=tc,
        description="d",
    )
    row = playbook_store.get_playbook_definition(conn, "pb_one")
    assert row is not None
    assert row["id"] == "pb_one"
    assert row["name"] == "One"
    assert row["description"] == "d"
    assert row["trigger_config"] == tc
    assert isinstance(row["trigger_config"], dict)
    assert row["steps"] == _valid_steps()
    assert row["enabled"] is True


@pytest.mark.usefixtures("postgres_db")
def test_get_playbook_definition_unknown(postgres_db):
    conn, _cur = postgres_db
    assert playbook_store.get_playbook_definition(conn, "nope") is None


@pytest.mark.usefixtures("postgres_db")
def test_create_and_get_playbook_schedule_metadata(postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_sched", "Sched", steps=_valid_steps())

    schedule = playbook_store.create_playbook_schedule(
        conn,
        "pb_sched",
        schedule_expression="0 * * * *",
        timezone_name="UTC",
        enabled=True,
        paused=False,
        missed_run_policy="skip",
        max_catchup_runs=0,
        max_concurrent_runs=1,
    )

    assert isinstance(schedule["id"], int)
    assert schedule["playbook_id"] == "pb_sched"
    assert schedule["schedule_expression"] == "0 * * * *"
    assert schedule["timezone"] == "UTC"
    assert schedule["enabled"] is True
    assert schedule["paused"] is False
    assert schedule["next_run_at"] is None
    assert schedule["last_run_at"] is None
    assert schedule["last_success_at"] is None
    assert schedule["last_failure_at"] is None
    assert schedule["last_scheduled_execution_id"] is None
    assert schedule["missed_run_policy"] == "skip"
    assert schedule["max_catchup_runs"] == 0
    assert schedule["max_concurrent_runs"] == 1

    fetched = playbook_store.get_playbook_schedule(conn, schedule["id"])
    assert fetched == schedule


@pytest.mark.usefixtures("postgres_db")
def test_list_playbook_schedules_filters_and_orders(postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_sched_a", "A", steps=_valid_steps())
    playbook_store.create_playbook_definition(conn, "pb_sched_b", "B", steps=_valid_steps())
    s1 = playbook_store.create_playbook_schedule(
        conn,
        "pb_sched_a",
        schedule_expression="0 * * * *",
        enabled=True,
    )
    s2 = playbook_store.create_playbook_schedule(
        conn,
        "pb_sched_b",
        schedule_expression="15 * * * *",
        enabled=False,
    )
    s3 = playbook_store.create_playbook_schedule(
        conn,
        "pb_sched_a",
        schedule_expression="30 * * * *",
        enabled=False,
    )

    all_rows = playbook_store.list_playbook_schedules(conn)
    assert [row["id"] for row in all_rows] == [s1["id"], s2["id"], s3["id"]]

    only_a = playbook_store.list_playbook_schedules(conn, playbook_id="pb_sched_a")
    assert [row["id"] for row in only_a] == [s1["id"], s3["id"]]

    enabled = playbook_store.list_playbook_schedules(conn, enabled=True)
    assert [row["id"] for row in enabled] == [s1["id"]]

    limited = playbook_store.list_playbook_schedules(conn, limit=2)
    assert [row["id"] for row in limited] == [s1["id"], s2["id"]]


@pytest.mark.usefixtures("postgres_db")
def test_create_playbook_schedule_validates_metadata(postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_sched_invalid", "S", steps=_valid_steps())

    with pytest.raises(ValueError, match="schedule_expression is required"):
        playbook_store.create_playbook_schedule(
            conn,
            "pb_sched_invalid",
            schedule_expression=" ",
        )
    with pytest.raises(ValueError, match="invalid missed_run_policy"):
        playbook_store.create_playbook_schedule(
            conn,
            "pb_sched_invalid",
            schedule_expression="0 * * * *",
            missed_run_policy="replay_all",
        )
    with pytest.raises(ValueError, match="max_catchup_runs must be non-negative"):
        playbook_store.create_playbook_schedule(
            conn,
            "pb_sched_invalid",
            schedule_expression="0 * * * *",
            max_catchup_runs=-1,
        )
    with pytest.raises(ValueError, match="max_concurrent_runs must be at least 1"):
        playbook_store.create_playbook_schedule(
            conn,
            "pb_sched_invalid",
            schedule_expression="0 * * * *",
            max_concurrent_runs=0,
        )


@pytest.mark.usefixtures("postgres_db")
def test_playbook_schedule_metadata_does_not_create_executions_or_queue(postgres_db):
    conn, cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_sched_safe", "Safe", steps=_valid_steps())
    cur.execute("SELECT COUNT(*) FROM playbook_executions")
    executions_before = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM response_actions_queue")
    queue_before = cur.fetchone()[0]

    playbook_store.create_playbook_schedule(
        conn,
        "pb_sched_safe",
        schedule_expression="0 * * * *",
        enabled=True,
    )
    playbook_store.list_playbook_schedules(conn)

    cur.execute("SELECT COUNT(*) FROM playbook_executions")
    assert cur.fetchone()[0] == executions_before
    cur.execute("SELECT COUNT(*) FROM response_actions_queue")
    assert cur.fetchone()[0] == queue_before


@pytest.mark.usefixtures("postgres_db")
def test_create_playbook_definition_invalid_steps_raises(postgres_db):
    conn, _cur = postgres_db
    with pytest.raises(ValueError):
        playbook_store.create_playbook_definition(
            conn,
            "bad",
            "Bad",
            steps=[{"action": "unknown"}],
        )


@pytest.mark.usefixtures("postgres_db")
def test_create_and_get_execution(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert(cur)
    playbook_store.create_playbook_definition(
        conn,
        "pb_exec",
        "Exec",
        steps=_valid_steps(),
    )
    eid = playbook_store.create_playbook_execution(conn, "pb_exec", alert_id=aid, incident_id=None)
    assert isinstance(eid, int)
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row is not None
    assert row["playbook_id"] == "pb_exec"
    assert row["alert_id"] == aid
    assert row["incident_id"] is None
    assert row["status"] == "pending"
    assert row["started_at"] is None
    assert row["completed_at"] is None
    assert row["steps_log"] == []
    assert row["attempt_count"] == 0
    assert row["max_attempts"] == playbook_store.DEFAULT_PLAYBOOK_EXECUTION_MAX_ATTEMPTS
    assert row["last_attempted_at"] is None
    assert row["failure_reason"] is None
    assert row["stale_after"] is None
    assert row["timeout_seconds"] is None
    meta = playbook_store.get_playbook_execution_reliability_metadata(conn, eid)
    assert meta == {
        "attempt_count": 0,
        "max_attempts": playbook_store.DEFAULT_PLAYBOOK_EXECUTION_MAX_ATTEMPTS,
        "last_attempted_at": None,
        "failure_reason": None,
        "stale_after": None,
        "timeout_seconds": None,
    }


@pytest.mark.usefixtures("postgres_db")
def test_create_execution_null_alert(postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(
        conn,
        "pb_null_alert",
        "NA",
        steps=_valid_steps(),
    )
    eid = playbook_store.create_playbook_execution(conn, "pb_null_alert", alert_id=None)
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["alert_id"] is None


@pytest.mark.usefixtures("postgres_db")
def test_get_playbook_execution_unknown(postgres_db):
    conn, _cur = postgres_db
    assert playbook_store.get_playbook_execution(conn, 999999) is None


@pytest.mark.usefixtures("postgres_db")
def test_update_execution_status_running_and_terminal(postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(
        conn,
        "pb_status",
        "S",
        steps=_valid_steps(),
    )
    eid = playbook_store.create_playbook_execution(conn, "pb_status", alert_id=None)

    playbook_store.update_execution_status(conn, eid, "running")
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "running"
    assert row["started_at"] is not None
    assert row["completed_at"] is None

    playbook_store.update_execution_status(conn, eid, "success")
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "success"
    assert row["completed_at"] is not None


@pytest.mark.usefixtures("postgres_db")
def test_update_execution_status_awaiting_approval(postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(
        conn,
        "pb_awaiting",
        "Awaiting",
        steps=_valid_steps(),
    )
    eid = playbook_store.create_playbook_execution(conn, "pb_awaiting", alert_id=None)
    playbook_store.update_execution_status(conn, eid, "awaiting_approval")

    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "awaiting_approval"
    assert row["completed_at"] is None


@pytest.mark.usefixtures("postgres_db")
def test_update_execution_status_failed_sets_completed(postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(
        conn,
        "pb_fail",
        "F",
        steps=_valid_steps(),
    )
    eid = playbook_store.create_playbook_execution(conn, "pb_fail", alert_id=None)
    playbook_store.update_execution_status(conn, eid, "running")
    playbook_store.update_execution_status(conn, eid, "failed")
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "failed"
    assert row["completed_at"] is not None


@pytest.mark.usefixtures("postgres_db")
def test_update_execution_status_abandoned(postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(
        conn,
        "pb_ab",
        "A",
        steps=_valid_steps(),
    )
    eid = playbook_store.create_playbook_execution(conn, "pb_ab", alert_id=None)
    playbook_store.update_execution_status(conn, eid, "abandoned")
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "abandoned"
    assert row["completed_at"] is not None


@pytest.mark.usefixtures("postgres_db")
def test_update_execution_status_invalid_raises(postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(
        conn,
        "pb_inv",
        "I",
        steps=_valid_steps(),
    )
    eid = playbook_store.create_playbook_execution(conn, "pb_inv", alert_id=None)
    with pytest.raises(ValueError):
        playbook_store.update_execution_status(conn, eid, "bogus")


@pytest.mark.usefixtures("postgres_db")
def test_list_playbook_executions_order_and_filters(postgres_db):
    conn, cur = postgres_db
    playbook_store.create_playbook_definition(
        conn,
        "pb_x",
        "X",
        steps=_valid_steps(),
    )
    playbook_store.create_playbook_definition(
        conn,
        "pb_y",
        "Y",
        steps=_valid_steps(),
    )
    e1 = playbook_store.create_playbook_execution(conn, "pb_x", alert_id=None)
    e2 = playbook_store.create_playbook_execution(conn, "pb_y", alert_id=None)
    e3 = playbook_store.create_playbook_execution(conn, "pb_x", alert_id=None)
    # Same-transaction inserts can share identical created_at; pin ordering for DESC tests.
    cur.execute(
        "UPDATE playbook_executions SET created_at = NOW() - INTERVAL '3 hours' WHERE id = %s",
        (e1,),
    )
    cur.execute(
        "UPDATE playbook_executions SET created_at = NOW() - INTERVAL '2 hours' WHERE id = %s",
        (e2,),
    )
    cur.execute(
        "UPDATE playbook_executions SET created_at = NOW() - INTERVAL '1 hour' WHERE id = %s",
        (e3,),
    )

    all_rows = playbook_store.list_playbook_executions(conn)
    assert [r["id"] for r in all_rows] == [e3, e2, e1]

    only_x = playbook_store.list_playbook_executions(conn, playbook_id="pb_x")
    assert {r["id"] for r in only_x} == {e1, e3}

    playbook_store.update_execution_status(conn, e2, "running")
    running_only = playbook_store.list_playbook_executions(conn, status="running")
    assert [r["id"] for r in running_only] == [e2]

    limited = playbook_store.list_playbook_executions(conn, limit=2)
    assert len(limited) == 2
    assert [r["id"] for r in limited] == [e3, e2]


@pytest.mark.usefixtures("postgres_db")
def test_update_playbook_definition_updates_fields(postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(
        conn,
        "pb_upd",
        "Original",
        steps=_valid_steps(),
        trigger_config={"alert_type": "failed_login"},
        description="old",
        enabled=True,
    )
    conn.commit()

    updated = playbook_store.update_playbook_definition(
        conn,
        "pb_upd",
        name="Renamed",
        description="new desc",
        trigger_config={"min_severity": "HIGH"},
        steps=[{"action": "block_ip", "params": {}, "on_failure": "abort"}],
        enabled=False,
    )
    assert updated is not None
    assert updated["id"] == "pb_upd"
    assert updated["name"] == "Renamed"
    assert updated["description"] == "new desc"
    assert updated["trigger_config"] == {"min_severity": "HIGH"}
    assert updated["enabled"] is False
    assert len(updated["steps"]) == 1


@pytest.mark.usefixtures("postgres_db")
def test_update_playbook_definition_unknown_returns_none(postgres_db):
    conn, _cur = postgres_db
    assert (
        playbook_store.update_playbook_definition(
            conn,
            "missing_pb",
            name="X",
            description=None,
            trigger_config={},
            steps=_valid_steps(),
            enabled=True,
        )
        is None
    )


@pytest.mark.usefixtures("postgres_db")
def test_update_playbook_definition_invalid_steps_raises(postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_bad_step", "B", steps=_valid_steps())
    conn.commit()
    with pytest.raises(ValueError):
        playbook_store.update_playbook_definition(
            conn,
            "pb_bad_step",
            name="B",
            description=None,
            trigger_config={},
            steps=[{"action": "bad_action"}],
            enabled=True,
        )


@pytest.mark.usefixtures("postgres_db")
def test_set_playbook_definition_enabled(postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(
        conn,
        "pb_en",
        "E",
        steps=_valid_steps(),
        enabled=False,
    )
    conn.commit()

    on = playbook_store.set_playbook_definition_enabled(conn, "pb_en", True)
    assert on is not None and on["enabled"] is True

    off = playbook_store.set_playbook_definition_enabled(conn, "pb_en", False)
    assert off is not None and off["enabled"] is False


@pytest.mark.usefixtures("postgres_db")
def test_set_playbook_definition_enabled_unknown_returns_none(postgres_db):
    conn, _cur = postgres_db
    assert playbook_store.set_playbook_definition_enabled(conn, "no_such", True) is None


@pytest.mark.usefixtures("postgres_db")
def test_update_and_set_enabled_do_not_create_executions(postgres_db):
    conn, cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_noex", "N", steps=_valid_steps())
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM playbook_executions")
    before = cur.fetchone()[0]

    playbook_store.update_playbook_definition(
        conn,
        "pb_noex",
        name="N2",
        description=None,
        trigger_config={},
        steps=_valid_steps(),
        enabled=True,
    )
    playbook_store.set_playbook_definition_enabled(conn, "pb_noex", False)

    cur.execute("SELECT COUNT(*) FROM playbook_executions")
    assert cur.fetchone()[0] == before


@pytest.mark.usefixtures("postgres_db")
def test_create_pending_playbook_execution_once_is_idempotent(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert(cur)
    playbook_store.create_playbook_definition(conn, "pb_once", "Once", steps=_valid_steps())

    first = playbook_store.create_pending_playbook_execution_once(conn, "pb_once", aid)
    second = playbook_store.create_pending_playbook_execution_once(conn, "pb_once", aid)

    assert isinstance(first, int)
    assert second is None

    cur.execute(
        """
        SELECT id, status, started_at, completed_at
        FROM playbook_executions
        WHERE playbook_id = %s AND alert_id = %s
        """,
        ("pb_once", aid),
    )
    rows = cur.fetchall()
    assert rows == [(first, "pending", None, None)]


@pytest.mark.usefixtures("postgres_db")
def test_active_playbook_execution_uniqueness_blocks_active_duplicates(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert(cur)
    playbook_store.create_playbook_definition(conn, "pb_active_unique", "AU", steps=_valid_steps())
    first = playbook_store.create_pending_playbook_execution_once(conn, "pb_active_unique", aid)
    conn.commit()

    with pytest.raises(psycopg2.IntegrityError):
        playbook_store.create_playbook_execution(conn, "pb_active_unique", aid)
    conn.rollback()

    playbook_store.update_execution_status(conn, first, "running")
    conn.commit()
    with pytest.raises(psycopg2.IntegrityError):
        playbook_store.create_playbook_execution(conn, "pb_active_unique", aid)
    conn.rollback()

    playbook_store.update_execution_status(conn, first, "awaiting_approval")
    conn.commit()
    with pytest.raises(psycopg2.IntegrityError):
        playbook_store.create_playbook_execution(conn, "pb_active_unique", aid)
    conn.rollback()


@pytest.mark.usefixtures("postgres_db")
def test_active_playbook_execution_uniqueness_allows_history(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert(cur)
    playbook_store.create_playbook_definition(conn, "pb_history", "History", steps=_valid_steps())

    failed = playbook_store.create_pending_playbook_execution_once(conn, "pb_history", aid)
    playbook_store.update_execution_status(conn, failed, "failed")
    abandoned = playbook_store.create_playbook_execution(conn, "pb_history", aid)
    playbook_store.update_execution_status(conn, abandoned, "abandoned")
    success = playbook_store.create_playbook_execution(conn, "pb_history", aid)
    playbook_store.update_execution_status(conn, success, "success")

    cur.execute(
        """
        SELECT status
        FROM playbook_executions
        WHERE playbook_id = %s AND alert_id = %s
        ORDER BY id ASC
        """,
        ("pb_history", aid),
    )
    assert [row[0] for row in cur.fetchall()] == ["failed", "abandoned", "success"]


@pytest.mark.usefixtures("postgres_db")
def test_create_retry_execution_creates_new_pending_history_row(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert(cur)
    playbook_store.create_playbook_definition(conn, "pb_retry", "Retry", steps=_valid_steps())
    failed = playbook_store.create_playbook_execution(conn, "pb_retry", aid)
    playbook_store.set_playbook_execution_failed(
        conn,
        failed,
        [{"step_index": 0, "status": "failed"}],
    )

    retry_id = playbook_store.create_retry_execution(conn, failed)

    source = playbook_store.get_playbook_execution(conn, failed)
    retry = playbook_store.get_playbook_execution(conn, retry_id)
    assert source["status"] == "failed"
    assert source["steps_log"] == [{"step_index": 0, "status": "failed"}]
    assert retry["status"] == "pending"
    assert retry["playbook_id"] == "pb_retry"
    assert retry["alert_id"] == aid
    assert retry["steps_log"] == []
    assert retry["last_completed_step"] is None


@pytest.mark.usefixtures("postgres_db")
def test_create_retry_execution_blocks_when_active_execution_exists(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert(cur)
    playbook_store.create_playbook_definition(conn, "pb_retry_active", "RA", steps=_valid_steps())
    failed = playbook_store.create_playbook_execution(conn, "pb_retry_active", aid)
    playbook_store.update_execution_status(conn, failed, "failed")
    active = playbook_store.create_playbook_execution(conn, "pb_retry_active", aid)
    assert playbook_store.get_playbook_execution(conn, active)["status"] == "pending"

    with pytest.raises(ValueError, match="active execution already exists"):
        playbook_store.create_retry_execution(conn, failed)


@pytest.mark.usefixtures("postgres_db")
def test_abandon_playbook_execution_transitions_and_noops(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert(cur)
    playbook_store.create_playbook_definition(conn, "pb_abandon_helper", "A", steps=_valid_steps())
    eid = playbook_store.create_playbook_execution(conn, "pb_abandon_helper", aid)

    assert playbook_store.abandon_playbook_execution(conn, eid) == "ok"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "abandoned"
    assert row["completed_at"] is not None
    assert playbook_store.abandon_playbook_execution(conn, eid) == "no_op"


@pytest.mark.usefixtures("postgres_db")
def test_create_pending_playbook_execution_once_allows_distinct_pairs(postgres_db):
    conn, cur = postgres_db
    aid_one = _insert_alert(cur, "10.0.0.2")
    aid_two = _insert_alert(cur, "10.0.0.3")
    playbook_store.create_playbook_definition(conn, "pb_one", "One", steps=_valid_steps())
    playbook_store.create_playbook_definition(conn, "pb_two", "Two", steps=_valid_steps())

    same_alert_first = playbook_store.create_pending_playbook_execution_once(conn, "pb_one", aid_one)
    same_alert_second = playbook_store.create_pending_playbook_execution_once(conn, "pb_two", aid_one)
    same_playbook_other_alert = playbook_store.create_pending_playbook_execution_once(conn, "pb_one", aid_two)

    assert all(
        isinstance(value, int)
        for value in [same_alert_first, same_alert_second, same_playbook_other_alert]
    )
    cur.execute("SELECT COUNT(*) FROM playbook_executions")
    assert cur.fetchone()[0] == 3


@pytest.mark.usefixtures("postgres_db")
def test_create_pending_playbook_execution_once_requires_alert_id(postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_req", "Req", steps=_valid_steps())

    with pytest.raises(ValueError):
        playbook_store.create_pending_playbook_execution_once(conn, "pb_req", None)


@pytest.mark.usefixtures("postgres_db")
def test_create_pending_playbook_execution_once_does_not_touch_queue_or_logs(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert(cur)
    playbook_store.create_playbook_definition(conn, "pb_safe", "Safe", steps=_valid_steps())

    cur.execute("SELECT COUNT(*) FROM response_actions_queue")
    queue_before = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM response_actions_log")
    log_before = cur.fetchone()[0]

    playbook_store.create_pending_playbook_execution_once(conn, "pb_safe", aid)

    cur.execute("SELECT COUNT(*) FROM response_actions_queue")
    assert cur.fetchone()[0] == queue_before
    cur.execute("SELECT COUNT(*) FROM response_actions_log")
    assert cur.fetchone()[0] == log_before


@pytest.mark.usefixtures("postgres_db")
def test_list_and_claim_pending_playbook_executions(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert(cur)
    playbook_store.create_playbook_definition(conn, "pb_claim", "Claim", steps=_valid_steps())
    e1 = playbook_store.create_playbook_execution(conn, "pb_claim", aid)
    e2 = playbook_store.create_playbook_execution(conn, "pb_claim", alert_id=None)
    playbook_store.update_execution_status(conn, e2, "success")

    pending = playbook_store.list_pending_playbook_executions(conn)
    assert [row["id"] for row in pending] == [e1]

    claimed = playbook_store.claim_next_pending_playbook_execution(conn)
    assert claimed["id"] == e1
    assert claimed["status"] == "running"
    assert claimed["started_at"] is not None

    assert playbook_store.claim_next_pending_playbook_execution(conn) is None


@pytest.mark.usefixtures("postgres_db")
def test_playbook_execution_step_log_and_terminal_helpers(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert(cur)
    playbook_store.create_playbook_definition(conn, "pb_log", "Log", steps=_valid_steps())
    eid = playbook_store.create_playbook_execution(conn, "pb_log", aid)
    running = playbook_store.set_playbook_execution_running(conn, eid)
    assert running["status"] == "running"
    assert running["started_at"] is not None

    steps_log = [{"step_index": 0, "status": "success"}]
    updated = playbook_store.update_playbook_execution_step_log(
        conn,
        eid,
        steps_log,
        last_completed_step=0,
    )
    assert updated["steps_log"] == steps_log
    assert updated["last_completed_step"] == 0

    success = playbook_store.set_playbook_execution_success(
        conn,
        eid,
        steps_log,
        last_completed_step=0,
    )
    assert success["status"] == "success"
    assert success["completed_at"] is not None

    cur.execute("SELECT COUNT(*) FROM response_actions_queue")
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT COUNT(*) FROM approval_requests")
    assert cur.fetchone()[0] == 0


@pytest.mark.usefixtures("postgres_db")
def test_playbook_execution_awaiting_approval_helper(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert(cur)
    playbook_store.create_playbook_definition(conn, "pb_gate", "Gate", steps=_valid_steps())
    eid = playbook_store.create_playbook_execution(conn, "pb_gate", aid)
    playbook_store.set_playbook_execution_running(conn, eid)

    steps_log = [
        {"step_index": 0, "status": "success"},
        {"step_index": 1, "status": "awaiting_approval", "event": "approval_requested"},
    ]
    awaiting = playbook_store.set_playbook_execution_awaiting_approval(
        conn,
        eid,
        steps_log,
        last_completed_step=0,
    )

    assert awaiting["status"] == "awaiting_approval"
    assert awaiting["completed_at"] is None
    assert awaiting["last_completed_step"] == 0
    assert awaiting["steps_log"] == steps_log

    cur.execute("SELECT COUNT(*) FROM response_actions_queue")
    assert cur.fetchone()[0] == 0


@pytest.mark.usefixtures("postgres_db")
def test_list_awaiting_and_resumed_running_helpers(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert(cur)
    playbook_store.create_playbook_definition(conn, "pb_resume", "Resume", steps=_valid_steps())
    awaiting_id = playbook_store.create_playbook_execution(conn, "pb_resume", aid)
    pending_id = playbook_store.create_playbook_execution(conn, "pb_resume", alert_id=None)
    playbook_store.set_playbook_execution_running(conn, awaiting_id)
    playbook_store.set_playbook_execution_awaiting_approval(
        conn,
        awaiting_id,
        [{"step_index": 0, "status": "awaiting_approval"}],
        last_completed_step=None,
    )

    awaiting = playbook_store.list_awaiting_approval_playbook_executions(conn)
    assert [row["id"] for row in awaiting] == [awaiting_id]

    resumed_log = [
        {"step_index": 0, "status": "awaiting_approval"},
        {"step_index": 0, "status": "approved", "event": "approval_approved"},
    ]
    resumed = playbook_store.set_playbook_execution_resumed_running(
        conn,
        awaiting_id,
        resumed_log,
        last_completed_step=0,
    )

    assert resumed["status"] == "running"
    assert resumed["steps_log"] == resumed_log
    assert resumed["last_completed_step"] == 0
    assert playbook_store.set_playbook_execution_resumed_running(
        conn,
        pending_id,
        [],
        last_completed_step=None,
    ) is None


@pytest.mark.usefixtures("postgres_db")
def test_playbook_execution_failed_helper(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert(cur)
    playbook_store.create_playbook_definition(conn, "pb_fail_helper", "Fail", steps=_valid_steps())
    eid = playbook_store.create_playbook_execution(conn, "pb_fail_helper", aid)
    playbook_store.set_playbook_execution_running(conn, eid)

    steps_log = [{"step_index": 0, "status": "failed"}]
    failed = playbook_store.set_playbook_execution_failed(
        conn,
        eid,
        steps_log,
        last_completed_step=None,
    )

    assert failed["status"] == "failed"
    assert failed["completed_at"] is not None
    assert failed["steps_log"] == steps_log
    cur.execute("SELECT COUNT(*) FROM response_actions_queue")
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT COUNT(*) FROM approval_requests")
    assert cur.fetchone()[0] == 0


@pytest.mark.usefixtures("postgres_db")
def test_update_playbook_execution_reliability_metadata_partial_and_clear(postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(
        conn,
        "pb_rel",
        "Reliability",
        steps=_valid_steps(),
    )
    eid = playbook_store.create_playbook_execution(conn, "pb_rel", alert_id=None)
    when = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)

    updated = playbook_store.update_playbook_execution_reliability_metadata(
        conn,
        eid,
        attempt_count=1,
        last_attempted_at=when,
        failure_reason="step simulation error",
        stale_after=3600,
        timeout_seconds=120,
    )
    assert updated is not None
    assert updated["attempt_count"] == 1
    assert updated["max_attempts"] == playbook_store.DEFAULT_PLAYBOOK_EXECUTION_MAX_ATTEMPTS
    assert updated["last_attempted_at"] == when
    assert updated["failure_reason"] == "step simulation error"
    assert updated["stale_after"] == 3600
    assert updated["timeout_seconds"] == 120

    bumped_max = playbook_store.update_playbook_execution_reliability_metadata(
        conn, eid, max_attempts=5
    )
    assert bumped_max is not None
    assert bumped_max["max_attempts"] == 5
    assert bumped_max["attempt_count"] == 1
    assert bumped_max["failure_reason"] == "step simulation error"

    cleared = playbook_store.update_playbook_execution_reliability_metadata(
        conn,
        eid,
        failure_reason=None,
        stale_after=None,
    )
    assert cleared is not None
    assert cleared["failure_reason"] is None
    assert cleared["stale_after"] is None
    assert cleared["timeout_seconds"] == 120

    assert playbook_store.update_playbook_execution_reliability_metadata(conn, 999999, attempt_count=0) is None


@pytest.mark.usefixtures("postgres_db")
def test_update_playbook_execution_reliability_metadata_no_ops_returns_full_row(postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_rel2", "R2", steps=_valid_steps())
    eid = playbook_store.create_playbook_execution(conn, "pb_rel2", alert_id=None)
    row = playbook_store.update_playbook_execution_reliability_metadata(conn, eid)
    assert row is not None
    assert row["id"] == eid
    assert row["attempt_count"] == 0

    with pytest.raises(ValueError):
        playbook_store.update_playbook_execution_reliability_metadata(conn, eid, attempt_count=-1)


@pytest.mark.usefixtures("postgres_db")
def test_playbook_execution_stale_running_uses_metadata(postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_stale", "S", steps=_valid_steps())
    eid = playbook_store.create_playbook_execution(conn, "pb_stale", alert_id=None)
    t0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    playbook_store.set_playbook_execution_running(conn, eid, now=t0)
    playbook_store.update_playbook_execution_reliability_metadata(conn, eid, stale_after=300)
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "running"
    assert not playbook_store.playbook_execution_row_is_stale_running(
        row, now=t0 + timedelta(seconds=200)
    )
    assert playbook_store.playbook_execution_row_is_stale_running(
        row, now=t0 + timedelta(seconds=300)
    )
    assert playbook_store.playbook_execution_is_stale_running(
        conn, eid, now=t0 + timedelta(seconds=400)
    )


@pytest.mark.usefixtures("postgres_db")
def test_playbook_execution_stale_falls_back_to_timeout_seconds(postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_stale_to", "ST", steps=_valid_steps())
    eid = playbook_store.create_playbook_execution(conn, "pb_stale_to", alert_id=None)
    t0 = datetime(2026, 2, 1, 0, 0, 0, tzinfo=timezone.utc)
    playbook_store.set_playbook_execution_running(conn, eid, now=t0)
    playbook_store.update_playbook_execution_reliability_metadata(
        conn, eid, timeout_seconds=100, stale_after=None
    )
    row = playbook_store.get_playbook_execution(conn, eid)
    assert playbook_store.playbook_execution_row_is_stale_running(
        row, now=t0 + timedelta(seconds=100)
    )


@pytest.mark.usefixtures("postgres_db")
def test_playbook_execution_not_stale_without_threshold_or_when_not_running(postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_nstale", "N", steps=_valid_steps())
    eid = playbook_store.create_playbook_execution(conn, "pb_nstale", alert_id=None)
    t0 = datetime(2026, 6, 1, 0, 0, 0)
    playbook_store.set_playbook_execution_running(conn, eid, now=t0)
    row = playbook_store.get_playbook_execution(conn, eid)
    assert not playbook_store.playbook_execution_row_is_stale_running(
        row, now=t0 + timedelta(days=99)
    )
    playbook_store.update_playbook_execution_reliability_metadata(conn, eid, stale_after=60)
    row = playbook_store.get_playbook_execution(conn, eid)
    playbook_store.update_execution_status(conn, eid, "success")
    row = playbook_store.get_playbook_execution(conn, eid)
    assert not playbook_store.playbook_execution_row_is_stale_running(
        row, now=t0 + timedelta(days=99)
    )


@pytest.mark.usefixtures("postgres_db")
def test_stale_running_uses_last_attempted_at_over_started_at(postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_sref", "SR", steps=_valid_steps())
    eid = playbook_store.create_playbook_execution(conn, "pb_sref", alert_id=None)
    t0 = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
    playbook_store.set_playbook_execution_running(conn, eid, now=t0)
    playbook_store.update_playbook_execution_reliability_metadata(
        conn,
        eid,
        stale_after=100,
        last_attempted_at=t0 + timedelta(seconds=500),
    )
    row = playbook_store.get_playbook_execution(conn, eid)
    assert not playbook_store.playbook_execution_row_is_stale_running(
        row, now=t0 + timedelta(seconds=550)
    )
    assert playbook_store.playbook_execution_row_is_stale_running(
        row, now=t0 + timedelta(seconds=651)
    )


@pytest.mark.usefixtures("postgres_db")
def test_list_stale_running_playbook_execution_ids(postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_lst", "L", steps=_valid_steps())
    stale_id = playbook_store.create_playbook_execution(conn, "pb_lst", alert_id=None)
    fresh_id = playbook_store.create_playbook_execution(conn, "pb_lst", alert_id=None)
    t0 = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
    playbook_store.set_playbook_execution_running(conn, stale_id, now=t0)
    playbook_store.set_playbook_execution_running(conn, fresh_id, now=t0 + timedelta(seconds=500))
    playbook_store.update_playbook_execution_reliability_metadata(conn, stale_id, stale_after=100)
    playbook_store.update_playbook_execution_reliability_metadata(conn, fresh_id, stale_after=10000)
    now = t0 + timedelta(seconds=200)
    assert playbook_store.list_stale_running_playbook_execution_ids(conn, now=now) == [stale_id]


@pytest.mark.usefixtures("postgres_db")
def test_mark_playbook_execution_permanently_failed_and_idempotent(postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_pf", "PF", steps=_valid_steps())
    eid = playbook_store.create_playbook_execution(conn, "pb_pf", alert_id=None)
    playbook_store.set_playbook_execution_running(conn, eid)
    updated = playbook_store.mark_playbook_execution_permanently_failed(
        conn, eid, failure_reason="stale running"
    )
    assert updated is not None
    assert updated["status"] == "permanently_failed"
    assert updated["failure_reason"] == "stale running"
    assert updated["completed_at"] is not None

    again = playbook_store.mark_playbook_execution_permanently_failed(
        conn, eid, failure_reason="should not replace"
    )
    assert again["failure_reason"] == "stale running"

    noop = playbook_store.mark_playbook_execution_permanently_failed(conn, eid, failure_reason="  ")
    assert noop["failure_reason"] == "stale running"


@pytest.mark.usefixtures("postgres_db")
def test_mark_permanently_failed_requires_non_empty_reason_when_transitioning(postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_pfr", "PR", steps=_valid_steps())
    eid = playbook_store.create_playbook_execution(conn, "pb_pfr", alert_id=None)
    playbook_store.set_playbook_execution_running(conn, eid)
    with pytest.raises(ValueError, match="failure_reason is required"):
        playbook_store.mark_playbook_execution_permanently_failed(conn, eid, failure_reason="   ")


@pytest.mark.usefixtures("postgres_db")
def test_mark_permanently_failed_from_failed_and_awaiting_approval(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert(cur)
    playbook_store.create_playbook_definition(conn, "pb_pf2", "P2", steps=_valid_steps())
    failed_id = playbook_store.create_playbook_execution(conn, "pb_pf2", aid)
    playbook_store.set_playbook_execution_failed(
        conn, failed_id, [{"step_index": 0, "status": "failed"}]
    )
    row = playbook_store.mark_playbook_execution_permanently_failed(
        conn, failed_id, failure_reason="dead letter"
    )
    assert row["status"] == "permanently_failed"

    await_id = playbook_store.create_playbook_execution(conn, "pb_pf2", aid)
    playbook_store.set_playbook_execution_awaiting_approval(
        conn,
        await_id,
        [{"step_index": 0, "status": "awaiting_approval"}],
    )
    row2 = playbook_store.mark_playbook_execution_permanently_failed(
        conn, await_id, failure_reason="stuck gate"
    )
    assert row2["status"] == "permanently_failed"


@pytest.mark.usefixtures("postgres_db")
def test_mark_permanently_failed_rejects_success_abandoned_pending(postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_pfx", "PX", steps=_valid_steps())

    for status in ("pending", "success", "abandoned"):
        eid = playbook_store.create_playbook_execution(conn, "pb_pfx", alert_id=None)
        if status != "pending":
            playbook_store.update_execution_status(conn, eid, status)
        with pytest.raises(ValueError):
            playbook_store.mark_playbook_execution_permanently_failed(
                conn, eid, failure_reason="nope"
            )


@pytest.mark.usefixtures("postgres_db")
def test_abandon_rejects_permanently_failed(postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_pfa", "PA", steps=_valid_steps())
    eid = playbook_store.create_playbook_execution(conn, "pb_pfa", alert_id=None)
    playbook_store.update_execution_status(conn, eid, "running")
    playbook_store.update_execution_status(conn, eid, "permanently_failed")
    with pytest.raises(ValueError, match="cannot abandon terminal"):
        playbook_store.abandon_playbook_execution(conn, eid)


@pytest.mark.usefixtures("postgres_db")
def test_update_execution_status_permanently_failed_terminal(postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_pfs", "PS", steps=_valid_steps())
    eid = playbook_store.create_playbook_execution(conn, "pb_pfs", alert_id=None)
    playbook_store.update_execution_status(conn, eid, "running")
    playbook_store.update_execution_status(conn, eid, "permanently_failed")
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "permanently_failed"
    assert row["completed_at"] is not None


@pytest.mark.usefixtures("postgres_db")
def test_mark_permanently_failed_does_not_touch_queue(postgres_db):
    conn, cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_pfq", "PQ", steps=_valid_steps())
    eid = playbook_store.create_playbook_execution(conn, "pb_pfq", alert_id=None)
    playbook_store.set_playbook_execution_running(conn, eid)
    cur.execute("SELECT COUNT(*) FROM response_actions_queue")
    before = cur.fetchone()[0]
    playbook_store.mark_playbook_execution_permanently_failed(conn, eid, failure_reason="x")
    cur.execute("SELECT COUNT(*) FROM response_actions_queue")
    assert cur.fetchone()[0] == before
