from contextlib import contextmanager
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

import siem_backend
from engines.detection_applicability import RULE_APPLICABILITY

ADMIN_USER = "testadmin"
ADMIN_PASS = "testpassword123!"


class _RouteSafeConnection:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return self._conn.cursor()

    def close(self):
        return None

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()


@contextmanager
def _patched_app_db(conn):
    wrapper = _RouteSafeConnection(conn)
    with patch("routes.admin_routes.get_db_connection", return_value=wrapper), patch(
        "core.audit_helpers.get_db_connection", return_value=wrapper
    ), patch("engines.detection_config.get_db_connection", return_value=wrapper), patch(
        "core.db.get_db_connection", return_value=wrapper
    ):
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


@pytest.mark.parametrize("path", [
    "/admin/users",
    "/admin/audit-log",
    "/admin/pfsense-ingest-filters",
    "/admin/pfsense-ingest-filters/metrics",
])
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
        ("/admin/pfsense-ingest-filters", _fake_viewer(), "viewerpass"),
        ("/admin/pfsense-ingest-filters", _fake_analyst(), "analystpass"),
        ("/admin/pfsense-ingest-filters/metrics", _fake_viewer(), "viewerpass"),
        ("/admin/pfsense-ingest-filters/metrics", _fake_analyst(), "analystpass"),
    ],
)
def test_admin_list_routes_as_viewer_or_analyst_return_403(client, mock_db, path, fake_user, password):
    # load_user runs on every request; keep both namespaces patched through login + GET.
    with patch("routes.auth_routes.get_user_by_username", return_value=fake_user), patch(
        "core.auth.get_user_by_username", return_value=fake_user
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
    assert len(data) == 15
    assert {rule["rule_id"] for rule in data} == {
        "failed_login_threshold",
        "port_scan_threshold",
        "password_spraying_threshold",
        "http_error_threshold",
        "application_exception_threshold",
        "high_request_rate_threshold",
        "successful_login_after_spray",
        "honeypot_env_probe_threshold",
        "honeypot_admin_probe_threshold",
        "honeypot_scanner_detected",
        "honeypot_credential_stuffing_threshold",
        "pfsense_firewall_repeated_deny",
        "pfsense_firewall_port_scan",
        "pfsense_firewall_noisy_source",
        "pfsense_firewall_suspicious_allow",
    }
    for rule in data:
        for key in (
            "rule_id",
            "display_name",
            "parameters",
            "active",
            "description",
            "override_status",
            "has_override",
            "applicable_sources",
            "source_applicability_category",
        ):
            assert key in rule

        registry_entry = RULE_APPLICABILITY[rule["rule_id"]]
        assert rule["source_applicability_category"] == registry_entry.classification
        assert rule["applicable_sources"] == [
            {"source": identity.source, "source_type": identity.source_type}
            for identity in sorted(registry_entry.allowed_sources)
        ]


def test_patch_admin_detection_rule_empty_payload_returns_400(client):
    _login_super_admin(client)
    resp = client.patch(
        "/admin/detection-rules/failed_login_threshold",
        json={},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "At least one of parameters or active is required"


def test_patch_detection_rule_active_false_true_and_audit(client, postgres_db):
    conn, cur = postgres_db
    _login_super_admin(client)

    with _patched_app_db(conn), patch(
        "engines.detection_engine.lookup_ip_reputation",
        return_value={
            "reputation_score": 0,
            "reputation_label": "unknown",
            "reputation_source": "test",
            "reputation_summary": "test",
        },
    ), patch(
        "engines.correlation_engine.lookup_ip_reputation",
        return_value={
            "reputation_score": 0,
            "reputation_label": "unknown",
            "reputation_source": "test",
            "reputation_summary": "test",
        },
    ):
        disabled = client.patch(
            "/admin/detection-rules/failed_login_threshold",
            json={"active": False},
        )
        assert disabled.status_code == 200
        assert disabled.get_json()["active"] is False

        enabled = client.patch(
            "/admin/detection-rules/failed_login_threshold",
            json={"active": True},
        )
        assert enabled.status_code == 200
        assert enabled.get_json()["active"] is True

    cur.execute(
        """
        SELECT active, parameters
        FROM detection_config
        WHERE rule_id = 'failed_login_threshold'
        """
    )
    active, parameters = cur.fetchone()
    assert active is True
    assert parameters == {"threshold": 3, "window_minutes": 15}

    cur.execute(
        """
        SELECT details
        FROM audit_log
        WHERE event_type = 'detection_rule_updated'
        ORDER BY id
        """
    )
    audits = [row[0] for row in cur.fetchall()]
    assert [(item["old_active"], item["new_active"]) for item in audits] == [
        (True, False),
        (False, True),
    ]
    assert audits[0]["changes"] == [{"field": "active", "old": True, "new": False}]


@pytest.mark.parametrize("invalid_active", [None, 0, 1, "false", [], {}])
def test_patch_detection_rule_rejects_non_boolean_active(client, invalid_active):
    _login_super_admin(client)
    response = client.patch(
        "/admin/detection-rules/failed_login_threshold",
        json={"active": invalid_active},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "Active must be a boolean"


@pytest.mark.parametrize("field", ["applicable_sources", "source_applicability_category", "unknown"])
def test_patch_detection_rule_rejects_read_only_or_unknown_fields(client, field):
    _login_super_admin(client)
    response = client.patch(
        "/admin/detection-rules/failed_login_threshold",
        json={field: []},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == f"Unknown field: {field}"


def test_patch_detection_rule_parameter_only_remains_compatible(client, postgres_db):
    conn, cur = postgres_db
    _login_super_admin(client)
    with _patched_app_db(conn):
        response = client.patch(
            "/admin/detection-rules/failed_login_threshold",
            json={"parameters": {"threshold": 7}},
        )

    assert response.status_code == 200
    body = response.get_json()
    assert body["active"] is True
    assert body["parameters"] == {"threshold": 7, "window_minutes": 15}
    cur.execute(
        "SELECT parameters, active FROM detection_config WHERE rule_id = 'failed_login_threshold'"
    )
    assert cur.fetchone() == ({"threshold": 7, "window_minutes": 15}, True)


def test_patch_detection_rule_combines_parameters_and_active(client, postgres_db):
    conn, cur = postgres_db
    _login_super_admin(client)
    with _patched_app_db(conn):
        response = client.patch(
            "/admin/detection-rules/http_error_threshold",
            json={"parameters": {"threshold": 2, "window_minutes": 9}, "active": False},
        )

    assert response.status_code == 200
    body = response.get_json()
    assert body["active"] is False
    assert body["parameters"] == {"threshold": 2, "window_minutes": 9}
    cur.execute(
        "SELECT parameters, active FROM detection_config WHERE rule_id = 'http_error_threshold'"
    )
    assert cur.fetchone() == ({"threshold": 2, "window_minutes": 9}, False)


def test_active_change_through_api_immediately_controls_detection_without_deleting_events(client, postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.230"
    _login_super_admin(client)
    reputation = {
        "reputation_score": 0,
        "reputation_label": "unknown",
        "reputation_source": "test",
        "reputation_summary": "test",
    }
    with _patched_app_db(conn), patch(
        "engines.detection_engine.lookup_ip_reputation", return_value=reputation
    ), patch("engines.correlation_engine.lookup_ip_reputation", return_value=reputation):
        disabled = client.patch(
            "/admin/detection-rules/failed_login_threshold",
            json={"parameters": {"threshold": 1}, "active": False},
        )
        assert disabled.status_code == 200

        result = siem_backend.ingest_normalized_event(
            {
                "event_type": "failed_login",
                "severity": "medium",
                "source_ip": source_ip,
                "source": "bank_app",
                "source_type": "custom",
                "event_timestamp": None,
                "message": "failed login",
                "app_name": "test",
                "environment": "test",
                "raw_payload": {"username": "alice"},
            },
            conn,
            cur,
        )
        assert result == []

        enabled = client.patch(
            "/admin/detection-rules/failed_login_threshold",
            json={"active": True},
        )
        assert enabled.status_code == 200

        result = siem_backend.ingest_normalized_event(
            {
                "event_type": "failed_login",
                "severity": "medium",
                "source_ip": source_ip,
                "source": "bank_app",
                "source_type": "custom",
                "event_timestamp": None,
                "message": "failed login",
                "app_name": "test",
                "environment": "test",
                "raw_payload": {"username": "bob"},
            },
            conn,
            cur,
        )

    assert len(result) == 1
    assert result[0]["attempts"] == 2
    cur.execute("SELECT COUNT(*) FROM events WHERE source_ip = %s", (source_ip,))
    assert cur.fetchone()[0] == 2


def test_pfsense_ingest_filters_require_super_admin(client):
    assert client.get("/admin/pfsense-ingest-filters").status_code == 401
    assert client.get("/admin/pfsense-ingest-filters/metrics").status_code == 401


def test_pfsense_filter_metrics_are_bounded_process_aggregates(client):
    _login_super_admin(client)
    response = client.get("/admin/pfsense-ingest-filters/metrics")
    assert response.status_code == 200
    data = response.get_json()
    assert data["reset_on_process_restart"] is True
    assert isinstance(data["counts"], dict)
    assert data["listener_outcome_contract"] == [
        "forwarded",
        "filtered",
        "ingested",
        "rejected",
        "backend_failed",
    ]


def test_get_and_patch_pfsense_ingest_filters_apply_immediately_and_audit(client, postgres_db):
    conn, cur = postgres_db
    _login_super_admin(client)
    with _patched_app_db(conn):
        response = client.get("/admin/pfsense-ingest-filters")
        assert response.status_code == 200
        policy = response.get_json()
        assert set(policy["categories"]) == {
            "block_events",
            "inbound_sensitive_port_allows",
            "all_allow_events",
            "dns_traffic",
            "icmp_traffic",
        }
        assert policy["categories"]["all_allow_events"]["enabled"] is False

        updated = client.patch(
            "/admin/pfsense-ingest-filters/all_allow_events",
            json={"enabled": True, "parameters": {}},
        )
        assert updated.status_code == 200
        assert updated.get_json()["enabled"] is True

        immediate = client.get("/admin/pfsense-ingest-filters").get_json()
        assert immediate["categories"]["all_allow_events"]["enabled"] is True

    cur.execute(
        "SELECT event_type, details FROM audit_log WHERE event_type = %s ORDER BY id DESC LIMIT 1",
        ("pfsense_ingest_filter_updated",),
    )
    audit = cur.fetchone()
    assert audit[0] == "pfsense_ingest_filter_updated"
    assert audit[1]["category"] == "all_allow_events"
    assert audit[1]["old"]["enabled"] is False
    assert audit[1]["new"]["enabled"] is True


@pytest.mark.parametrize(
    "category,payload",
    [
        ("unknown", {"enabled": True}),
        ("all_allow_events", {"enabled": "yes"}),
        ("block_events", {"enabled": True, "extra": True}),
        ("inbound_sensitive_port_allows", {"enabled": True, "parameters": {"sensitive_ports": [22, 22]}}),
    ],
)
def test_invalid_pfsense_filter_updates_do_not_change_configuration(client, postgres_db, category, payload):
    conn, cur = postgres_db
    _login_super_admin(client)
    with _patched_app_db(conn):
        response = client.patch(f"/admin/pfsense-ingest-filters/{category}", json=payload)
    assert response.status_code in {400, 404}
    cur.execute("SELECT enabled FROM pfsense_ingest_config WHERE category = 'all_allow_events'")
    assert cur.fetchone()[0] is False
