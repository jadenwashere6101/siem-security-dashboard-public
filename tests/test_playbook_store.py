import pytest

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
