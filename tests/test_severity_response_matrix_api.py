from contextlib import contextmanager
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from core.core_playbook_pack_v1 import seed_core_playbook_pack_v1


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
    with patch("routes.severity_response_matrix_routes.get_db_connection", return_value=wrapper), patch(
        "core.notification_policy_store.get_db_connection", return_value=wrapper
    ), patch("engines.detection_config.get_db_connection", return_value=wrapper):
        yield


def _fake_user(username, password, role):
    return {
        "username": username,
        "password_hash": generate_password_hash(password, method="pbkdf2:sha256"),
        "role": role,
        "is_active": True,
    }


def _login_super_admin(client):
    resp = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert resp.status_code == 200


def _login_role(client, *, username, password, role):
    user = _fake_user(username, password, role)
    patchers = [
        patch("routes.auth_routes.get_user_by_username", return_value=user),
        patch("core.auth.get_user_by_username", return_value=user),
    ]
    for patcher in patchers:
        patcher.start()
    resp = client.post("/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return patchers


def _stop_patchers(patchers):
    for patcher in reversed(patchers):
        patcher.stop()


def test_severity_response_matrix_requires_authentication(client):
    resp = client.get("/api/severity-response-matrix")
    assert resp.status_code == 401


def test_severity_response_matrix_denies_viewer(client, mock_db):
    patchers = _login_role(
        client,
        username="matrixviewer",
        password="viewerpass",
        role="viewer",
    )
    try:
        resp = client.get("/api/severity-response-matrix")
    finally:
        _stop_patchers(patchers)
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "forbidden"


def test_severity_response_matrix_returns_live_backend_contract_for_analyst(client, postgres_db):
    conn, cur = postgres_db
    seed_core_playbook_pack_v1(conn)
    cur.execute(
        """
        UPDATE notification_policy
        SET slack_enabled = TRUE,
            minimum_severity = 'high',
            critical_cross_source_destination = '#soc-critical'
        WHERE id = 1
        """
    )
    conn.commit()

    patchers = _login_role(
        client,
        username="matrixanalyst",
        password="analystpass",
        role="analyst",
    )
    try:
        with _patched_app_db(conn):
            resp = client.get("/api/severity-response-matrix")
    finally:
        _stop_patchers(patchers)

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["page_statement"] == "This page explains how the SIEM behaves. It is not another configuration interface."
    assert [entry["severity"] for entry in data["severity_definitions"]] == [
        "low",
        "medium",
        "high",
        "critical",
    ]
    critical_definition = next(
        entry for entry in data["severity_definitions"] if entry["severity"] == "critical"
    )
    assert "confirmed compromise" not in critical_definition["definition"].lower()

    rows = {row["rule_id"]: row for row in data["rules"]}
    assert rows["app_insights_unauthorized_access_threshold"]["default_severity"] == "high"
    assert rows["app_insights_unauthorized_access_threshold"]["maximum_severity"] == "high"
    assert rows["azure_auth_abuse_exception_correlation"]["default_severity"] == "high"
    assert rows["azure_auth_abuse_exception_correlation"]["maximum_severity"] == "high"
    assert rows["web_to_app_attack_pattern"]["default_severity"] == "high"
    assert rows["spray_then_success_pattern"]["default_severity"] == "high"
    assert rows["successful_login_after_spray"]["default_severity"] == "critical"
    assert rows["pfsense_firewall_noisy_source"]["maximum_severity"] == "low"
    assert rows["successful_login_after_spray"]["why"]
    assert "confirmed compromise" not in rows["successful_login_after_spray"]["why"].lower()
    assert rows["successful_login_after_spray"]["notification_behavior"].startswith(
        "Immediate Slack alert attempt"
    )
