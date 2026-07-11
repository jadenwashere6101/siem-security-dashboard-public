from contextlib import contextmanager
from unittest.mock import patch

import siem_backend
from core import soar_response_outcomes as outcomes


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
    "response_outcome",
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
    with patch("core.audit_helpers.get_db_connection", return_value=wrapper), patch(
        "routes.blocklist_routes.get_db_connection", return_value=wrapper
    ):
        yield


def _login_super_admin(client):
    resp = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert resp.status_code == 200


def _insert_blocked_ip(
    cur,
    *,
    ip_address,
    reason="contract test block",
    status="active",
    expires_interval=None,
    source_alert_id=None,
):
    expires_sql = "NULL" if expires_interval is None else f"NOW() + INTERVAL '{expires_interval}'"
    cur.execute(
        f"""
        INSERT INTO blocked_ips (ip_address, reason, status, created_by, expires_at, source_alert_id)
        VALUES (%s, %s, %s, %s, {expires_sql}, %s)
        RETURNING id
        """,
        (ip_address, reason, status, "testadmin", source_alert_id),
    )
    return cur.fetchone()[0]


def _insert_alert(cur, *, source_ip=VALID_BLOCKABLE_IP):
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message)
        VALUES ('blocklist_contract', 'high', %s::inet, 'blocklist contract')
        RETURNING id
        """,
        (source_ip,),
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
    assert entry["response_outcome"] is None


def test_get_blocked_ips_linked_source_alert_returns_response_outcome(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    block_id = _insert_blocked_ip(
        cur,
        ip_address=VALID_BLOCKABLE_IP,
        source_alert_id=alert_id,
    )
    decision = outcomes.create_response_decision(
        conn,
        selected_action="block_ip",
        decision_source="manual",
        outcome_summary="Block selected.",
        alert_id=alert_id,
        source_ip=VALID_BLOCKABLE_IP,
        reason_code="tracking_only",
    )
    event = outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        execution_mode="tracking_only",
        execution_state="succeeded",
        execution_actor="manual",
        tracking_recorded=True,
        outcome_summary="Block recorded as tracking only.",
        alert_id=alert_id,
        source_ip=VALID_BLOCKABLE_IP,
        reason_code="tracking_only",
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/blocked-ips")

    assert resp.status_code == 200
    entry = next(item for item in resp.get_json() if item["id"] == block_id)
    assert entry["source_alert_id"] == alert_id
    assert entry["response_outcome"]["decision_id"] == decision["id"]
    assert entry["response_outcome"]["latest_outcome_event_id"] == event["id"]


def test_get_blocked_ips_normalizes_expired_active_entry_as_expired(client, postgres_db):
    conn, cur = postgres_db
    block_id = _insert_blocked_ip(
        cur,
        ip_address=VALID_BLOCKABLE_IP,
        status="active",
        expires_interval="-1 hour",
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/blocked-ips")

    assert resp.status_code == 200
    data = resp.get_json()
    entry = next(item for item in data if item["id"] == block_id)
    assert entry["status"] == "expired"

    cur.execute("SELECT status FROM blocked_ips WHERE id = %s", (block_id,))
    assert cur.fetchone()[0] == "active"


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
    assert "tracking removed" in data.get("message", "").lower()
    assert "firewall" in data.get("message", "").lower()
