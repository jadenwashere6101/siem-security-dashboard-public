from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from core import playbook_store


ADMIN_USER = "testadmin"
ADMIN_PASS = "testpassword123!"
SOURCE_IP = "8.8.8.8"


class _RouteSafeConnection:
    """Wrap postgres_db connection and keep route cleanup from closing the fixture."""

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
    with patch("routes.source_ip_context_routes.get_db_connection", return_value=wrapper), patch(
        "core.audit_helpers.get_db_connection", return_value=wrapper
    ):
        yield


def _fake_user(username, password, role):
    return {
        "username": username,
        "password_hash": generate_password_hash(password, method="pbkdf2:sha256"),
        "role": role,
        "is_active": True,
    }


@contextmanager
def _logged_in_role(client, username, password, role):
    user = _fake_user(username, password, role)
    with patch("routes.auth_routes.get_user_by_username", return_value=user), patch(
        "core.auth.get_user_by_username", return_value=user
    ):
        resp = client.post("/login", json={"username": username, "password": password})
        assert resp.status_code == 200
        yield


def _login_super_admin(client):
    resp = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert resp.status_code == 200


def _insert_alert(
    cur,
    *,
    source_ip=SOURCE_IP,
    alert_type="failed_login_threshold",
    severity="high",
    status="open",
    response_status="pending",
    reputation_score=72,
    reputation_label="malicious",
    created_offset_seconds=0,
):
    created_at = datetime.now(timezone.utc) + timedelta(seconds=created_offset_seconds)
    cur.execute(
        """
        INSERT INTO alerts (
            alert_type, severity, source_ip, source, source_type, message, status,
            response_action, response_status, reputation_score, reputation_label,
            reputation_source, reputation_summary, created_at
        )
        VALUES (
            %s, %s, %s::inet, 'bank_app', 'custom', %s, %s,
            'block_ip', %s, %s, %s, 'abuseipdb', 'external snapshot', %s
        )
        RETURNING id
        """,
        (
            alert_type,
            severity,
            source_ip,
            f"{alert_type} source context contract",
            status,
            response_status,
            reputation_score,
            reputation_label,
            created_at,
        ),
    )
    return cur.fetchone()[0]


def _insert_incident(cur, *, source_ip=SOURCE_IP, alert_id=None):
    cur.execute(
        """
        INSERT INTO incidents (title, severity, priority, status, source_ip)
        VALUES ('Source context incident', 'high', 'P1', 'investigating', %s::inet)
        RETURNING id
        """,
        (source_ip,),
    )
    incident_id = cur.fetchone()[0]
    if alert_id is not None:
        cur.execute(
            """
            INSERT INTO incident_alerts (incident_id, alert_id)
            VALUES (%s, %s)
            """,
            (incident_id, alert_id),
        )
    return incident_id


def _insert_queue_row(cur, *, alert_id, source_ip=SOURCE_IP, status="pending"):
    cur.execute(
        """
        INSERT INTO response_actions_queue (idempotency_key, alert_id, source_ip, action, status)
        VALUES (md5(random()::text), %s, %s::inet, 'block_ip', %s)
        RETURNING id
        """,
        (alert_id, source_ip, status),
    )
    return cur.fetchone()[0]


def _insert_blocked_ip(cur, *, source_ip=SOURCE_IP, expires_interval="-1 hour"):
    cur.execute(
        f"""
        INSERT INTO blocked_ips (ip_address, reason, status, created_by, expires_at)
        VALUES (%s::inet, 'source context contract', 'active', 'pytest', NOW() + INTERVAL '{expires_interval}')
        RETURNING id
        """,
        (source_ip,),
    )
    return cur.fetchone()[0]


def _insert_playbook_execution(conn, *, alert_id, incident_id):
    playbook_store.create_playbook_definition(
        conn,
        "source_ip_context_contract_pb",
        "Source IP context contract",
        steps=[{"action": "monitor", "params": {}}],
    )
    return playbook_store.create_playbook_execution(
        conn,
        "source_ip_context_contract_pb",
        alert_id,
        incident_id,
    )


def _count_rows(cur):
    counts = {}
    for table in (
        "alerts",
        "incidents",
        "incident_alerts",
        "response_actions_queue",
        "blocked_ips",
        "playbook_definitions",
        "playbook_executions",
        "approval_requests",
    ):
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        counts[table] = cur.fetchone()[0]
    return counts


def test_source_ip_context_without_session_returns_401(client):
    resp = client.get(f"/source-ip-context?source_ip={SOURCE_IP}")
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "Unauthorized"


def test_source_ip_context_viewer_returns_403(client, mock_db):
    with _logged_in_role(client, "context_viewer", "viewerpass", "viewer"):
        resp = client.get(f"/source-ip-context?source_ip={SOURCE_IP}")

    assert resp.status_code == 403
    assert resp.get_json()["error"] == "forbidden"


def test_source_ip_context_analyst_can_access(client, postgres_db):
    conn, cur = postgres_db
    _insert_alert(cur)
    conn.commit()

    with _logged_in_role(client, "context_analyst", "analystpass", "analyst"):
        with _patched_app_db(conn):
            resp = client.get(f"/source-ip-context?source_ip={SOURCE_IP}")

    assert resp.status_code == 200
    assert resp.get_json()["source_ip"] == SOURCE_IP


def test_source_ip_context_super_admin_can_access(client, postgres_db):
    conn, cur = postgres_db
    _insert_alert(cur)
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get(f"/source-ip-context?source_ip={SOURCE_IP}")

    assert resp.status_code == 200
    assert resp.get_json()["source_ip"] == SOURCE_IP


def test_source_ip_context_rejects_missing_and_invalid_source_ip(client, postgres_db):
    conn, _cur = postgres_db
    _login_super_admin(client)

    with _patched_app_db(conn):
        missing = client.get("/source-ip-context")
        invalid = client.get("/source-ip-context?source_ip=not-an-ip")

    assert missing.status_code == 400
    assert missing.get_json()["error"] == "source_ip is required"
    assert invalid.status_code == 400
    assert invalid.get_json()["error"] == "source_ip is invalid"


def test_source_ip_context_response_shape_sections_and_no_unified_status(client, postgres_db):
    conn, cur = postgres_db
    _insert_alert(cur)
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get(f"/source-ip-context?source_ip={SOURCE_IP}")

    assert resp.status_code == 200
    data = resp.get_json()
    for section in (
        "source_ip",
        "generated_at",
        "limits",
        "alerts",
        "incidents",
        "queue",
        "blocklist",
        "reputation",
        "playbook_executions",
    ):
        assert section in data
    assert "status" not in data
    assert set(data["limits"]) == {
        "alerts",
        "incidents",
        "queue",
        "playbook_executions",
        "external_reputation_snapshots",
    }
    assert "behavioral" in data["reputation"]
    assert "latest_external" in data["reputation"]
    assert "external_snapshots" in data["reputation"]


def test_source_ip_context_caps_recent_collections(client, postgres_db):
    conn, cur = postgres_db
    alert_ids = []
    for index in range(12):
        alert_ids.append(
            _insert_alert(
                cur,
                response_status=f"queued-{index}",
                reputation_score=index,
                reputation_label=f"snapshot-{index}",
                created_offset_seconds=index,
            )
        )
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get(f"/source-ip-context?source_ip={SOURCE_IP}")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["limits"]["alerts"] == 10
    assert len(data["alerts"]["recent"]) == 10
    assert data["alerts"]["counts"]["total"] == len(alert_ids)
    assert data["limits"]["external_reputation_snapshots"] == 5
    assert len(data["reputation"]["external_snapshots"]) == 5


def test_source_ip_context_populates_linked_context_and_separate_reputation(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, reputation_score=91, reputation_label="known_bad")
    incident_id = _insert_incident(cur, alert_id=alert_id)
    queue_id = _insert_queue_row(cur, alert_id=alert_id, status="awaiting_approval")
    block_id = _insert_blocked_ip(cur, expires_interval="-1 hour")
    execution_id = _insert_playbook_execution(conn, alert_id=alert_id, incident_id=incident_id)
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get(f"/source-ip-context?source_ip={SOURCE_IP}")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["alerts"]["counts"]["total"] == 1
    assert data["alerts"]["recent"][0]["id"] == alert_id
    assert data["incidents"]["recent"][0]["id"] == incident_id
    assert data["incidents"]["recent"][0]["status"] == "investigating"
    assert data["queue"]["recent"][0]["id"] == queue_id
    assert data["queue"]["recent"][0]["status"] == "awaiting_approval"

    block_entry = next(entry for entry in data["blocklist"]["entries"] if entry["id"] == block_id)
    assert data["blocklist"]["effective_status"] == "expired"
    assert block_entry["raw_status"] == "active"
    assert block_entry["effective_status"] == "expired"

    behavioral = data["reputation"]["behavioral"]
    assert behavioral["source"] == "siem_internal"
    assert behavioral["score"] == 3
    assert behavioral["label"] == "Low Suspicion"
    assert data["reputation"]["latest_external"]["score"] == 91
    assert data["reputation"]["latest_external"]["label"] == "known_bad"
    assert data["reputation"]["external_snapshots"][0]["alert_id"] == alert_id

    assert data["playbook_executions"]["recent"][0]["id"] == execution_id
    assert data["playbook_executions"]["recent"][0]["status"] == "pending"

    cur.execute("SELECT status FROM blocked_ips WHERE id = %s", (block_id,))
    assert cur.fetchone()[0] == "active"


def test_source_ip_context_is_read_only(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    incident_id = _insert_incident(cur, alert_id=alert_id)
    _insert_queue_row(cur, alert_id=alert_id)
    _insert_blocked_ip(cur, expires_interval="1 hour")
    _insert_playbook_execution(conn, alert_id=alert_id, incident_id=incident_id)
    conn.commit()
    before = _count_rows(cur)

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get(f"/source-ip-context?source_ip={SOURCE_IP}")

    assert resp.status_code == 200
    after = _count_rows(cur)
    assert after == before
