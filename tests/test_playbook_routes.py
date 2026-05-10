"""
Playbook API contracts: read access for analysts, super-admin-only definition mutations.
"""

import hashlib
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

from core import playbook_store

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
    with patch("routes.playbook_routes.get_db_connection", return_value=wrapper), patch(
        "core.audit_helpers.get_db_connection", return_value=wrapper
    ):
        yield


def _login_super_admin(client):
    resp = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert resp.status_code == 200


def _fake_user(username, password, role):
    return {
        "username": username,
        "password_hash": generate_password_hash(password, method="pbkdf2:sha256"),
        "role": role,
        "is_active": True,
    }


def _login_role(client, *, username, password, role):
    user = _fake_user(username, password, role)
    patchers = [
        patch("routes.auth_routes.get_user_by_username", return_value=user),
        patch("core.auth.get_user_by_username", return_value=user),
    ]
    for p in patchers:
        p.start()
    resp = client.post("/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return patchers


def _stop_patchers(patchers):
    for p in reversed(patchers):
        p.stop()


def _valid_steps():
    return [{"action": "monitor", "params": {}}]


def _create_body(playbook_id="pb_api_create"):
    return {
        "id": playbook_id,
        "name": "API playbook",
        "description": "from test",
        "trigger_config": {"min_severity": "LOW"},
        "steps": _valid_steps(),
        "enabled": False,
    }


def _insert_alert(cur, source_ip="10.0.0.50"):
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message)
        VALUES ('test_alert', 'LOW', %s::inet, 'msg')
        RETURNING id
        """,
        (source_ip,),
    )
    return cur.fetchone()[0]


def _insert_queue_row(cur, alert_id, source_ip, action="block_ip", status="pending"):
    idem = hashlib.sha256(f"{action}:{source_ip}:{alert_id}".encode()).hexdigest()
    cur.execute(
        """
        INSERT INTO response_actions_queue
        (idempotency_key, alert_id, source_ip, action, status)
        VALUES (%s, %s, %s::inet, %s, %s)
        RETURNING id
        """,
        (idem, alert_id, source_ip, action, status),
    )
    return cur.fetchone()[0]


def _def_keys():
    return {
        "id",
        "name",
        "description",
        "trigger_config",
        "steps",
        "enabled",
        "created_at",
        "updated_at",
    }


def _exec_keys():
    return {
        "id",
        "playbook_id",
        "alert_id",
        "incident_id",
        "status",
        "started_at",
        "completed_at",
        "last_completed_step",
        "steps_log",
        "created_at",
    }


# --- Auth ---


def test_playbooks_without_session_returns_401(client):
    assert client.get("/playbooks").status_code == 401


def test_playbook_executions_without_session_returns_401(client):
    assert client.get("/playbook-executions").status_code == 401


def test_playbooks_viewer_forbidden(client, mock_db):
    fake = _fake_user("pb_viewer", "vpass", "viewer")
    with patch("routes.auth_routes.get_user_by_username", return_value=fake), patch(
        "core.auth.get_user_by_username", return_value=fake
    ):
        assert client.post("/login", json={"username": "pb_viewer", "password": "vpass"}).status_code == 200
        resp = client.get("/playbooks")
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "forbidden"


def test_playbook_executions_viewer_forbidden(client, mock_db):
    fake = _fake_user("pb_exec_viewer", "vpass", "viewer")
    with patch("routes.auth_routes.get_user_by_username", return_value=fake), patch(
        "core.auth.get_user_by_username", return_value=fake
    ):
        assert client.post("/login", json={"username": "pb_exec_viewer", "password": "vpass"}).status_code == 200
        resp = client.get("/playbook-executions")
    assert resp.status_code == 403


def test_playbooks_detail_viewer_forbidden(client, mock_db):
    fake = _fake_user("pb_detail_viewer", "vpass", "viewer")
    with patch("routes.auth_routes.get_user_by_username", return_value=fake), patch(
        "core.auth.get_user_by_username", return_value=fake
    ):
        assert client.post("/login", json={"username": "pb_detail_viewer", "password": "vpass"}).status_code == 200
        resp = client.get("/playbooks/any-id")
    assert resp.status_code == 403


def test_playbook_executions_detail_viewer_forbidden(client, mock_db):
    fake = _fake_user("pb_exd_viewer", "vpass", "viewer")
    with patch("routes.auth_routes.get_user_by_username", return_value=fake), patch(
        "core.auth.get_user_by_username", return_value=fake
    ):
        assert client.post("/login", json={"username": "pb_exd_viewer", "password": "vpass"}).status_code == 200
        resp = client.get("/playbook-executions/1")
    assert resp.status_code == 403


# --- Definitions list / detail ---


@pytest.mark.usefixtures("postgres_db")
def test_list_playbooks_authorized_shape_and_filters(client, postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(
        conn,
        "pb_on",
        "On",
        steps=_valid_steps(),
        enabled=True,
        trigger_config={"min_severity": "HIGH"},
    )
    playbook_store.create_playbook_definition(
        conn,
        "pb_off",
        "Off",
        steps=_valid_steps(),
        enabled=False,
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        r_all = client.get("/playbooks")
        r_true = client.get("/playbooks?enabled=true")
        r_false = client.get("/playbooks?enabled=false")

    assert r_all.status_code == 200
    data_all = r_all.get_json()
    assert set(data_all.keys()) == {"items", "limit", "enabled"}
    assert data_all["enabled"] is None
    assert len(data_all["items"]) == 2
    assert {i["id"] for i in data_all["items"]} == {"pb_off", "pb_on"}

    assert r_true.status_code == 200
    d_true = r_true.get_json()
    assert d_true["enabled"] is True
    assert [i["id"] for i in d_true["items"]] == ["pb_on"]

    assert r_false.status_code == 200
    d_false = r_false.get_json()
    assert d_false["enabled"] is False
    assert [i["id"] for i in d_false["items"]] == ["pb_off"]


@pytest.mark.usefixtures("postgres_db")
def test_list_playbooks_invalid_enabled_returns_400(client, postgres_db):
    conn, _cur = postgres_db
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/playbooks?enabled=maybe")
    assert resp.status_code == 400


@pytest.mark.usefixtures("postgres_db")
def test_list_playbooks_invalid_limit_returns_400(client, postgres_db):
    conn, _cur = postgres_db
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/playbooks?limit=notint")
    assert resp.status_code == 400


@pytest.mark.usefixtures("postgres_db")
def test_list_playbooks_limit_clamped(client, postgres_db):
    conn, _cur = postgres_db
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/playbooks?limit=500")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["limit"] == 100


@pytest.mark.usefixtures("postgres_db")
def test_get_playbook_detail_authorized_and_404(client, postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(
        conn,
        "pb_detail",
        "Detail",
        steps=_valid_steps(),
        description="desc",
        trigger_config={"alert_type": "password_spraying"},
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        ok = client.get("/playbooks/pb_detail")
        missing = client.get("/playbooks/does-not-exist")

    assert ok.status_code == 200
    body = ok.get_json()
    assert _def_keys() == set(body.keys())
    assert body["id"] == "pb_detail"
    assert body["trigger_config"]["alert_type"] == "password_spraying"
    assert isinstance(body["steps"], list)

    assert missing.status_code == 404


# --- Executions list / detail ---


@pytest.mark.usefixtures("postgres_db")
def test_list_playbook_executions_filters_and_shape(client, postgres_db):
    conn, cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_a", "A", steps=_valid_steps())
    playbook_store.create_playbook_definition(conn, "pb_b", "B", steps=_valid_steps())
    e1 = playbook_store.create_playbook_execution(conn, "pb_a", alert_id=None)
    playbook_store.update_execution_status(conn, e1, "running")
    e2 = playbook_store.create_playbook_execution(conn, "pb_b", alert_id=None)
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        r0 = client.get("/playbook-executions")
        r_pb = client.get("/playbook-executions?playbook_id=pb_a")
        r_st = client.get("/playbook-executions?status=pending")

    assert r0.status_code == 200
    d0 = r0.get_json()
    assert set(d0.keys()) == {"items", "limit", "playbook_id", "status"}
    assert d0["playbook_id"] is None
    assert d0["status"] is None
    assert {x["playbook_id"] for x in d0["items"]} == {"pb_a", "pb_b"}

    d_pb = r_pb.get_json()
    assert all(x["playbook_id"] == "pb_a" for x in d_pb["items"])

    d_st = r_st.get_json()
    assert all(x["status"] == "pending" for x in d_st["items"])
    assert any(x["id"] == e2 for x in d_st["items"])


@pytest.mark.usefixtures("postgres_db")
def test_list_playbook_executions_invalid_status_returns_400(client, postgres_db):
    conn, _cur = postgres_db
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/playbook-executions?status=nope")
    assert resp.status_code == 400


@pytest.mark.usefixtures("postgres_db")
def test_get_playbook_execution_detail(client, postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_ex", "E", steps=_valid_steps())
    eid = playbook_store.create_playbook_execution(conn, "pb_ex", alert_id=None, incident_id=None)
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        ok = client.get(f"/playbook-executions/{eid}")
        missing = client.get("/playbook-executions/999999")

    assert ok.status_code == 200
    body = ok.get_json()
    assert _exec_keys() == set(body.keys())
    assert body["alert_id"] is None
    assert body["incident_id"] is None
    assert body["steps_log"] == []

    assert missing.status_code == 404


@pytest.mark.usefixtures("postgres_db")
def test_analyst_can_read_playbooks(client, postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_an", "Analyst", steps=_valid_steps())
    conn.commit()
    patchers = _login_role(client, username="pbanalyst", password="apass", role="analyst")
    try:
        with _patched_app_db(conn):
            resp = client.get("/playbooks")
    finally:
        _stop_patchers(patchers)
    assert resp.status_code == 200


# --- No mutation ---


@pytest.mark.usefixtures("postgres_db")
def test_read_endpoints_do_not_mutate_definitions_executions_or_queue(client, postgres_db):
    conn, cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_nm", "NM", steps=_valid_steps())
    eid = playbook_store.create_playbook_execution(conn, "pb_nm", alert_id=None)
    playbook_store.update_execution_status(conn, eid, "running")
    conn.commit()

    cur.execute("SELECT id, name, trigger_config, steps, enabled FROM playbook_definitions WHERE id = %s", ("pb_nm",))
    def_before = cur.fetchone()
    cur.execute(
        """
        SELECT id, status, started_at, completed_at, last_completed_step, steps_log
        FROM playbook_executions WHERE id = %s
        """,
        (eid,),
    )
    ex_before = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM response_actions_queue")
    q_before = cur.fetchone()[0]

    _login_super_admin(client)
    with _patched_app_db(conn):
        assert client.get("/playbooks").status_code == 200
        assert client.get("/playbooks/pb_nm").status_code == 200
        assert client.get("/playbook-executions").status_code == 200
        assert client.get(f"/playbook-executions/{eid}").status_code == 200

    cur.execute("SELECT id, name, trigger_config, steps, enabled FROM playbook_definitions WHERE id = %s", ("pb_nm",))
    def_after = cur.fetchone()
    cur.execute(
        """
        SELECT id, status, started_at, completed_at, last_completed_step, steps_log
        FROM playbook_executions WHERE id = %s
        """,
        (eid,),
    )
    ex_after = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM response_actions_queue")
    q_after = cur.fetchone()[0]

    assert def_before == def_after
    assert ex_before == ex_after
    assert q_before == q_after


# --- Definition mutations (super_admin only) ---


def test_post_playbooks_unauthenticated_returns_401(client):
    resp = client.post("/playbooks", json=_create_body("pb_unauth"))
    assert resp.status_code == 401


@pytest.mark.usefixtures("postgres_db")
def test_post_playbooks_analyst_forbidden(client, postgres_db):
    conn, _cur = postgres_db
    patchers = _login_role(client, username="pbanalyst2", password="ap2", role="analyst")
    try:
        with _patched_app_db(conn):
            resp = client.post("/playbooks", json=_create_body("pb_analyst_denied"))
    finally:
        _stop_patchers(patchers)
    assert resp.status_code == 403


@pytest.mark.usefixtures("postgres_db")
def test_post_playbooks_viewer_forbidden(client, postgres_db):
    conn, _cur = postgres_db
    fake = _fake_user("pb_view_mut", "v", "viewer")
    with patch("routes.auth_routes.get_user_by_username", return_value=fake), patch(
        "core.auth.get_user_by_username", return_value=fake
    ):
        assert client.post("/login", json={"username": "pb_view_mut", "password": "v"}).status_code == 200
        with _patched_app_db(conn):
            resp = client.post("/playbooks", json=_create_body("pb_view_denied"))
    assert resp.status_code == 403


@pytest.mark.usefixtures("postgres_db")
def test_super_admin_post_playbooks_201(client, postgres_db):
    conn, _cur = postgres_db
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.post("/playbooks", json=_create_body("pb_post_ok"))
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["id"] == "pb_post_ok"
    assert body["name"] == "API playbook"
    assert body["enabled"] is False
    assert _def_keys().issubset(set(body.keys()))


@pytest.mark.usefixtures("postgres_db")
def test_super_admin_post_duplicate_returns_409(client, postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(
        conn, "pb_dup", "Dup", steps=_valid_steps(), enabled=False
    )
    conn.commit()
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.post("/playbooks", json=_create_body("pb_dup"))
    assert resp.status_code == 409


@pytest.mark.usefixtures("postgres_db")
def test_post_playbooks_invalid_id_returns_400(client, postgres_db):
    conn, _cur = postgres_db
    _login_super_admin(client)
    body = _create_body("INVALID_UPPER")
    with _patched_app_db(conn):
        resp = client.post("/playbooks", json=body)
    assert resp.status_code == 400


@pytest.mark.usefixtures("postgres_db")
def test_post_playbooks_invalid_steps_returns_400(client, postgres_db):
    conn, _cur = postgres_db
    _login_super_admin(client)
    body = _create_body("pb_bad_steps")
    body["steps"] = [{"action": "notify_slack"}]
    with _patched_app_db(conn):
        resp = client.post("/playbooks", json=body)
    assert resp.status_code == 400


@pytest.mark.usefixtures("postgres_db")
def test_super_admin_put_playbook_200_and_404(client, postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(
        conn, "pb_put", "Old", steps=_valid_steps(), trigger_config={}, enabled=True
    )
    conn.commit()
    _login_super_admin(client)
    with _patched_app_db(conn):
        ok = client.put(
            "/playbooks/pb_put",
            json={
                "name": "New name",
                "description": None,
                "trigger_config": {"alert_type": "password_spraying"},
                "steps": [{"action": "flag_high_priority", "params": {}}],
                "enabled": False,
            },
        )
        missing = client.put(
            "/playbooks/missing_pb_put",
            json={
                "name": "X",
                "trigger_config": {},
                "steps": _valid_steps(),
                "enabled": True,
            },
        )
    assert ok.status_code == 200
    assert ok.get_json()["name"] == "New name"
    assert missing.status_code == 404


@pytest.mark.usefixtures("postgres_db")
def test_put_playbook_blank_name_returns_400(client, postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_put_blank", "B", steps=_valid_steps())
    conn.commit()
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.put(
            "/playbooks/pb_put_blank",
            json={
                "name": "   ",
                "trigger_config": {},
                "steps": _valid_steps(),
                "enabled": True,
            },
        )
    assert resp.status_code == 400


@pytest.mark.usefixtures("postgres_db")
def test_put_playbook_analyst_forbidden(client, postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_put_an", "A", steps=_valid_steps())
    conn.commit()
    patchers = _login_role(client, username="an_put", password="p", role="analyst")
    try:
        with _patched_app_db(conn):
            resp = client.put(
                "/playbooks/pb_put_an",
                json={
                    "name": "Hacked",
                    "trigger_config": {},
                    "steps": _valid_steps(),
                    "enabled": False,
                },
            )
    finally:
        _stop_patchers(patchers)
    assert resp.status_code == 403


@pytest.mark.usefixtures("postgres_db")
def test_patch_enabled_super_admin_200(client, postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(
        conn, "pb_patch_en", "P", steps=_valid_steps(), enabled=False
    )
    conn.commit()
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.patch("/playbooks/pb_patch_en/enabled", json={"enabled": True})
    assert resp.status_code == 200
    assert resp.get_json()["enabled"] is True


@pytest.mark.usefixtures("postgres_db")
def test_patch_enabled_missing_body_returns_400(client, postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_patch_bad", "B", steps=_valid_steps())
    conn.commit()
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.patch("/playbooks/pb_patch_bad/enabled", json={})
    assert resp.status_code == 400


@pytest.mark.usefixtures("postgres_db")
def test_patch_enabled_non_boolean_returns_400(client, postgres_db):
    conn, _cur = postgres_db
    playbook_store.create_playbook_definition(conn, "pb_patch_nb", "B", steps=_valid_steps())
    conn.commit()
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.patch("/playbooks/pb_patch_nb/enabled", json={"enabled": "yes"})
    assert resp.status_code == 400


@pytest.mark.usefixtures("postgres_db")
def test_patch_enabled_unknown_returns_404(client, postgres_db):
    conn, _cur = postgres_db
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.patch("/playbooks/nope_pb/enabled", json={"enabled": True})
    assert resp.status_code == 404


@pytest.mark.usefixtures("postgres_db")
def test_analyst_get_playbooks_still_ok_after_super_create(client, postgres_db):
    conn, _cur = postgres_db
    _login_super_admin(client)
    with _patched_app_db(conn):
        assert client.post("/playbooks", json=_create_body("pb_read_coexist")).status_code == 201
    patchers = _login_role(client, username="an_read", password="p", role="analyst")
    try:
        with _patched_app_db(conn):
            resp = client.get("/playbooks")
    finally:
        _stop_patchers(patchers)
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.get_json()["items"]}
    assert "pb_read_coexist" in ids


@pytest.mark.usefixtures("postgres_db")
def test_mutations_do_not_create_executions_or_touch_queue_or_log(client, postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert(cur)
    qid = _insert_queue_row(cur, aid, "192.0.2.1")
    cur.execute("INSERT INTO response_actions_log (alert_id, source_ip, action, status) VALUES (%s, %s::inet, %s, %s)", (aid, "192.0.2.1", "monitor", "ok"))
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM playbook_executions")
    ex0 = cur.fetchone()[0]
    cur.execute("SELECT id, status, updated_at FROM response_actions_queue WHERE id = %s", (qid,))
    q_before = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM response_actions_log")
    log0 = cur.fetchone()[0]

    _login_super_admin(client)
    with _patched_app_db(conn):
        assert client.post("/playbooks", json=_create_body("pb_safe_mut")).status_code == 201
        assert (
            client.put(
                "/playbooks/pb_safe_mut",
                json={
                    "name": "Updated",
                    "trigger_config": {},
                    "steps": _valid_steps(),
                    "enabled": True,
                },
            ).status_code
            == 200
        )
        assert (
            client.patch("/playbooks/pb_safe_mut/enabled", json={"enabled": False}).status_code
            == 200
        )

    cur.execute("SELECT COUNT(*) FROM playbook_executions")
    assert cur.fetchone()[0] == ex0
    cur.execute("SELECT id, status, updated_at FROM response_actions_queue WHERE id = %s", (qid,))
    assert cur.fetchone() == q_before
    cur.execute("SELECT COUNT(*) FROM response_actions_log")
    assert cur.fetchone()[0] == log0
