from contextlib import contextmanager
from unittest.mock import patch

import siem_backend


ADMIN_USER = "testadmin"
ADMIN_PASS = "testpassword123!"

# Publicly routable IP that passes validate_blocked_ip on Python 3.9:
# 198.51.100.x / 203.0.113.x are is_private=True on this runtime.
VALID_BLOCKABLE_IP = "8.8.8.8"

REQUIRED_BLOCKED_IP_FIELDS = (
    "id",
    "ip_address",
    "reason",
    "status",
    "created_by",
    "created_at",
    "expires_at",
    "source_alert_id",
)


class _RouteSafeConnection:
    """Wraps postgres_db connection; ignores close(), delegates commit/rollback."""

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
    """Patch route, blocklist blueprint, and audit-helper DB connections to use the test conn."""
    wrapper = _RouteSafeConnection(conn)
    with patch("backend_audit_helpers.get_db_connection", return_value=wrapper), patch(
        "backend_blocklist_routes.get_db_connection", return_value=wrapper
    ):
        yield


def _login_super_admin(client):
    resp = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert resp.status_code == 200


def _insert_blocked_ip(cur, *, ip_address, reason="contract test block", status="active"):
    cur.execute(
        """
        INSERT INTO blocked_ips (ip_address, reason, status, created_by)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (ip_address, reason, status, "testadmin"),
    )
    return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# GET /blocked-ips
# ---------------------------------------------------------------------------


def test_get_blocked_ips_without_session_returns_401(client):
    resp = client.get("/blocked-ips")
    assert resp.status_code == 401


def test_get_blocked_ips_authenticated_returns_200_stable_shape(client, postgres_db):
    conn, cur = postgres_db
    _insert_blocked_ip(cur, ip_address=VALID_BLOCKABLE_IP)
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/blocked-ips")

    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) >= 1

    entry = data[0]
    for field in REQUIRED_BLOCKED_IP_FIELDS:
        assert field in entry, f"Missing required field in /blocked-ips response: {field}"


# ---------------------------------------------------------------------------
# POST /blocked-ips
# ---------------------------------------------------------------------------


def test_post_blocked_ips_without_session_returns_401(client):
    resp = client.post("/blocked-ips", json={"ip_address": VALID_BLOCKABLE_IP})
    assert resp.status_code == 401


def test_post_blocked_ips_missing_ip_returns_400(client, postgres_db):
    conn, cur = postgres_db
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.post("/blocked-ips", json={})

    assert resp.status_code == 400
    data = resp.get_json()
    assert isinstance(data, dict)
    assert "error" in data


def test_post_blocked_ips_invalid_ip_string_returns_400(client, postgres_db):
    conn, cur = postgres_db
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.post("/blocked-ips", json={"ip_address": "not-an-ip-address"})

    assert resp.status_code == 400
    data = resp.get_json()
    assert isinstance(data, dict)
    assert "error" in data


def test_post_blocked_ips_private_ip_returns_400(client, postgres_db):
    conn, cur = postgres_db
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.post("/blocked-ips", json={"ip_address": "192.168.1.100"})

    assert resp.status_code == 400
    data = resp.get_json()
    assert isinstance(data, dict)
    assert "error" in data


def test_post_blocked_ips_valid_public_ip_returns_201_with_id(client, postgres_db):
    conn, cur = postgres_db
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.post(
            "/blocked-ips",
            json={"ip_address": VALID_BLOCKABLE_IP, "reason": "contract test"},
        )

    assert resp.status_code == 201
    data = resp.get_json()
    assert isinstance(data, dict)
    assert data.get("message") == "Blocked IP added successfully"
    assert "id" in data
    assert isinstance(data["id"], int)


# ---------------------------------------------------------------------------
# PATCH /blocked-ips/<id>/unblock
# ---------------------------------------------------------------------------


def test_patch_unblock_without_session_returns_401(client):
    resp = client.patch("/blocked-ips/1/unblock")
    assert resp.status_code == 401


def test_patch_unblock_nonexistent_id_returns_404(client, postgres_db):
    conn, cur = postgres_db
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.patch("/blocked-ips/999999/unblock")

    assert resp.status_code == 404
    data = resp.get_json()
    assert isinstance(data, dict)
    assert "error" in data


def test_patch_unblock_active_entry_returns_200(client, postgres_db):
    conn, cur = postgres_db
    block_id = _insert_blocked_ip(cur, ip_address=VALID_BLOCKABLE_IP, status="active")
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.patch(f"/blocked-ips/{block_id}/unblock")

    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, dict)
    assert data.get("message") == "Blocked IP removed successfully"
