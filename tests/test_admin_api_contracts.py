from contextlib import contextmanager
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

import siem_backend

ADMIN_USER = "testadmin"
ADMIN_PASS = "testpassword123!"


class _RouteSafeConnection:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return self._conn.cursor()

    def close(self):
        return None


@contextmanager
def _patched_app_db(conn):
    wrapper = _RouteSafeConnection(conn)
    with patch("backend_admin_routes.get_db_connection", return_value=wrapper), patch(
        "backend_audit_helpers.get_db_connection", return_value=wrapper
    ), patch("backend_detection_config.get_db_connection", return_value=wrapper):
        yield


def _login_super_admin(client):
    resp = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert resp.status_code == 200


def _fake_viewer():
    return {
        "username": "contract_viewer",
        "password_hash": generate_password_hash("viewerpass", method="pbkdf2:sha256"),
        "role": "viewer",
        "is_active": True,
    }


def _fake_analyst():
    return {
        "username": "contract_analyst",
        "password_hash": generate_password_hash("analystpass", method="pbkdf2:sha256"),
        "role": "analyst",
        "is_active": True,
    }


@pytest.mark.parametrize("path", ["/admin/users", "/admin/audit-log"])
def test_admin_list_routes_without_session_return_401(client, path):
    resp = client.get(path)
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "Unauthorized"


@pytest.mark.parametrize(
    "path,fake_user,password",
    [
        ("/admin/users", _fake_viewer(), "viewerpass"),
        ("/admin/users", _fake_analyst(), "analystpass"),
        ("/admin/audit-log", _fake_viewer(), "viewerpass"),
        ("/admin/audit-log", _fake_analyst(), "analystpass"),
    ],
)
def test_admin_list_routes_as_viewer_or_analyst_return_403(client, mock_db, path, fake_user, password):
    # load_user runs on every request; keep both namespaces patched through login + GET.
    with patch("siem_backend.get_user_by_username", return_value=fake_user), patch(
        "backend_auth.get_user_by_username", return_value=fake_user
    ):
        login = client.post("/login", json={"username": fake_user["username"], "password": password})
        assert login.status_code == 200
        resp = client.get(path)
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "forbidden"


def test_get_admin_users_as_super_admin_returns_200_stable_shape(client, postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO users (username, password_hash, role, is_active)
        VALUES (%s, %s, %s, %s)
        """,
        ("seed_user", generate_password_hash("x", method="pbkdf2:sha256"), "viewer", True),
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/admin/users")

    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) >= 1
    row = data[0]
    for key in ("username", "role", "is_active", "created_at"):
        assert key in row


def test_get_admin_audit_log_as_super_admin_returns_200_stable_shape(client, postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO audit_log (
            event_type,
            actor_username,
            actor_role,
            target_username,
            target_alert_id,
            request_path,
            source_ip
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s::inet)
        """,
        ("contract_event", "admin", "super_admin", None, None, "/admin/audit-log", "127.0.0.1"),
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/admin/audit-log")

    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) >= 1
    row = data[0]
    for key in (
        "event_type",
        "actor_username",
        "actor_role",
        "target_username",
        "target_alert_id",
        "request_path",
        "source_ip",
        "created_at",
    ):
        assert key in row


def test_get_admin_detection_rules_as_super_admin_returns_200_stable_shape(client, postgres_db):
    _login_super_admin(client)
    conn, _ = postgres_db
    with _patched_app_db(conn):
        resp = client.get("/admin/detection-rules")

    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) == 4
    for rule in data:
        for key in (
            "rule_id",
            "display_name",
            "parameters",
            "active",
            "description",
            "override_status",
            "has_override",
        ):
            assert key in rule


def test_patch_admin_detection_rule_missing_parameters_returns_400(client):
    _login_super_admin(client)
    resp = client.patch(
        "/admin/detection-rules/failed_login_threshold",
        json={},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Missing required field: parameters"
