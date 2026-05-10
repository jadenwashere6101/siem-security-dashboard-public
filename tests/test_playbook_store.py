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
