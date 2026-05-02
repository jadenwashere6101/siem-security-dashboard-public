from contextlib import contextmanager
from unittest.mock import patch

from werkzeug.security import generate_password_hash


ADMIN_USER = "testadmin"
ADMIN_PASS = "testpassword123!"
REPUTATION = {
    "reputation_score": 0,
    "reputation_label": "low-risk",
    "reputation_source": "contract_test",
    "reputation_summary": "Contract test reputation",
}


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
    with patch("backend_admin_routes.get_db_connection", return_value=wrapper), patch(
        "backend_admin_routes.lookup_ip_reputation", return_value=REPUTATION
    ):
        yield


def _login_super_admin(client):
    resp = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert resp.status_code == 200


def _fake_analyst():
    return {
        "username": "backfill_contract_analyst",
        "password_hash": generate_password_hash("analystpass", method="pbkdf2:sha256"),
        "role": "analyst",
        "is_active": True,
    }


def test_backfill_reputation_without_session_returns_401(client):
    resp = client.post("/alerts/backfill-reputation")
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "Unauthorized"


def test_backfill_reputation_as_non_admin_returns_403(client, mock_db):
    fake_user = _fake_analyst()

    with patch("backend_auth_routes.get_user_by_username", return_value=fake_user), patch(
        "backend_auth.get_user_by_username", return_value=fake_user
    ):
        login = client.post("/login", json={"username": fake_user["username"], "password": "analystpass"})
        assert login.status_code == 200
        resp = client.post("/alerts/backfill-reputation")

    assert resp.status_code == 403
    assert resp.get_json()["error"] == "forbidden"


def test_backfill_reputation_as_super_admin_returns_success_shape(client, postgres_db):
    conn, _ = postgres_db
    _login_super_admin(client)

    with _patched_app_db(conn):
        resp = client.post("/alerts/backfill-reputation")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["message"] == "Reputation backfill completed"
    assert data["updated_alerts"] == 0
