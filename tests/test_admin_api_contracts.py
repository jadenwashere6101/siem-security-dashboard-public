from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
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
    "/admin/notification-policy",
    "/admin/detection-rules/pfsense-health",
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
        ("/admin/notification-policy", _fake_viewer(), "viewerpass"),
        ("/admin/notification-policy", _fake_analyst(), "analystpass"),
        ("/admin/detection-rules/pfsense-health", _fake_viewer(), "viewerpass"),
        ("/admin/detection-rules/pfsense-health", _fake_analyst(), "analystpass"),
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


def test_notification_policy_route_test_without_session_returns_401(client):
    resp = client.post("/admin/notification-policy/test/pfsense")
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "Unauthorized"


@pytest.mark.parametrize(
    "fake_user,password",
    [
        (_fake_viewer(), "viewerpass"),
        (_fake_analyst(), "analystpass"),
    ],
)
def test_notification_policy_route_test_as_viewer_or_analyst_returns_403(client, mock_db, fake_user, password):
    with patch("routes.auth_routes.get_user_by_username", return_value=fake_user), patch(
        "core.auth.get_user_by_username", return_value=fake_user
    ):
        login = client.post("/login", json={"username": fake_user["username"], "password": password})
        assert login.status_code == 200
        resp = client.post("/admin/notification-policy/test/pfsense")
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
    assert len(data) == 17
    assert {rule["rule_id"] for rule in data} == {
        "failed_login_threshold",
        "port_scan_threshold",
        "password_spraying_threshold",
        "http_error_threshold",
        "application_exception_threshold",
        "app_insights_unauthorized_access_threshold",
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
        "pfsense_firewall_allow_after_deny",
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


def test_get_pfsense_detection_health_returns_ranked_utc_windowed_read_only_summary(client, postgres_db):
    conn, cur = postgres_db
    now = datetime.now(timezone.utc)
    inside_window = now - timedelta(hours=2)
    older_than_window = now - timedelta(hours=26)

    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, source, source_type, message, status, created_at)
        VALUES
            (%s, %s, %s, 'pfsense', 'firewall', %s, 'open', %s),
            (%s, %s, %s, 'pfsense', 'firewall', %s, 'open', %s),
            (%s, %s, %s, 'pfsense', 'firewall', %s, 'open', %s),
            (%s, %s, %s, 'pfsense', 'firewall', %s, 'open', %s),
            (%s, %s, %s, 'pfsense', 'firewall', %s, 'open', %s),
            (%s, %s, %s, 'pfsense', 'firewall', %s, 'open', %s),
            (%s, %s, %s, 'pfsense', 'firewall', %s, 'open', %s),
            (%s, %s, %s, 'pfsense', 'firewall', %s, 'open', %s),
            (%s, %s, %s, 'pfsense', 'firewall', %s, 'open', %s),
            (%s, %s, %s, 'pfsense', 'firewall', %s, 'open', %s),
            (%s, %s, %s, 'pfsense', 'firewall', %s, 'open', %s)
        """,
        (
            "pfsense_firewall_repeated_deny", "medium", "198.51.100.31", "Repeated deny 1", inside_window,
            "pfsense_firewall_repeated_deny", "high", "198.51.100.32", "Repeated deny 2", inside_window + timedelta(minutes=10),
            "pfsense_firewall_repeated_deny", "low", "198.51.100.33", "Repeated deny 3", inside_window + timedelta(minutes=20),
            "pfsense_firewall_repeated_deny", "critical", "198.51.100.34", "Repeated deny stale", older_than_window,
            "pfsense_firewall_port_scan", "critical", "198.51.100.41", "Port scan 1", inside_window + timedelta(minutes=5),
            "pfsense_firewall_port_scan", "low", "198.51.100.42", "Port scan 2", inside_window + timedelta(minutes=15),
            "pfsense_firewall_suspicious_allow", "medium", "198.51.100.51", "Suspicious allow 1", inside_window + timedelta(minutes=25),
            "pfsense_firewall_suspicious_allow", "medium", "198.51.100.52", "Suspicious allow 2", inside_window + timedelta(minutes=26),
            "pfsense_firewall_suspicious_allow", "medium", "198.51.100.53", "Suspicious allow 3", inside_window + timedelta(minutes=27),
            "pfsense_firewall_suspicious_allow", "medium", "198.51.100.54", "Suspicious allow 4", inside_window + timedelta(minutes=28),
            "pfsense_firewall_suspicious_allow", "medium", "198.51.100.55", "Suspicious allow 5", inside_window + timedelta(minutes=29),
        ),
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/admin/detection-rules/pfsense-health")

    assert resp.status_code == 200
    data = resp.get_json()
    assert [row["rule_id"] for row in data] == [
        "pfsense_firewall_suspicious_allow",
        "pfsense_firewall_repeated_deny",
        "pfsense_firewall_port_scan",
        "pfsense_firewall_noisy_source",
    ]

    suspicious_allow = data[0]
    assert suspicious_allow["fired_count_24h"] == 5
    assert suspicious_allow["highest_severity_24h"] == "medium"
    assert suspicious_allow["health_badge"] == "Needs Review"

    repeated_deny = data[1]
    assert repeated_deny["fired_count_24h"] == 3
    assert repeated_deny["highest_severity_24h"] == "high"
    assert repeated_deny["last_fired_at"] == (inside_window + timedelta(minutes=20)).astimezone(timezone.utc).isoformat()
    assert repeated_deny["health_badge"] == "Normal"

    port_scan = data[2]
    assert port_scan == {
        "rule_id": "pfsense_firewall_port_scan",
        "rule_name": "pfSense Firewall Port Scan",
        "fired_count_24h": 2,
        "highest_severity_24h": "critical",
        "last_fired_at": (inside_window + timedelta(minutes=15)).astimezone(timezone.utc).isoformat(),
        "health_badge": "Normal",
    }

    noisy_source = data[3]
    assert noisy_source == {
        "rule_id": "pfsense_firewall_noisy_source",
        "rule_name": "pfSense Firewall Noisy Source",
        "fired_count_24h": 0,
        "highest_severity_24h": None,
        "last_fired_at": None,
        "health_badge": "Normal",
    }


def test_get_pfsense_detection_health_returns_zero_count_rows_when_no_alerts_exist(client, postgres_db):
    conn, _ = postgres_db
    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/admin/detection-rules/pfsense-health")

    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 4
    assert all(row["fired_count_24h"] == 0 for row in data)
    assert all(row["highest_severity_24h"] is None for row in data)
    assert all(row["last_fired_at"] is None for row in data)
    assert all(row["health_badge"] == "Normal" for row in data)


def test_get_pfsense_detection_health_since_tuning_respects_baseline_within_window(client, postgres_db, monkeypatch):
    conn, cur = postgres_db
    now = datetime.now(timezone.utc)
    baseline = now - timedelta(hours=12)
    monkeypatch.setenv("SIEM_PFSENSE_TUNING_BASELINE", baseline.isoformat())
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, source, source_type, message, status, created_at)
        VALUES
            ('pfsense_firewall_port_scan', 'medium', '198.51.100.66', 'pfsense', 'firewall', 'before baseline', 'open', %s),
            ('pfsense_firewall_port_scan', 'high', '198.51.100.67', 'pfsense', 'firewall', 'after baseline', 'open', %s)
        """
        ,
        (baseline - timedelta(minutes=5), baseline + timedelta(minutes=5)),
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/admin/detection-rules/pfsense-health?operational_scope=since_tuning")

    assert resp.status_code == 200
    data = {row["rule_id"]: row for row in resp.get_json()}
    assert data["pfsense_firewall_port_scan"]["fired_count_24h"] == 1
    assert data["pfsense_firewall_port_scan"]["highest_severity_24h"] == "high"


def test_get_pfsense_detection_health_single_rule_and_tie_breaking_by_rule_name(client, postgres_db):
    conn, cur = postgres_db
    now = datetime.now(timezone.utc)
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, source, source_type, message, status, created_at)
        VALUES
            (%s, 'high', %s, 'pfsense', 'firewall', %s, 'open', %s),
            (%s, 'medium', %s, 'pfsense', 'firewall', %s, 'open', %s),
            (%s, 'medium', %s, 'pfsense', 'firewall', %s, 'open', %s),
            (%s, 'medium', %s, 'pfsense', 'firewall', %s, 'open', %s)
        """,
        (
            "pfsense_firewall_noisy_source", "198.51.100.61", "Noisy source 1", now - timedelta(minutes=20),
            "pfsense_firewall_noisy_source", "198.51.100.62", "Noisy source 2", now - timedelta(minutes=10),
            "pfsense_firewall_port_scan", "198.51.100.63", "Port scan 1", now - timedelta(minutes=19),
            "pfsense_firewall_port_scan", "198.51.100.64", "Port scan 2", now - timedelta(minutes=9),
        ),
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/admin/detection-rules/pfsense-health")

    assert resp.status_code == 200
    data = resp.get_json()
    assert [row["rule_id"] for row in data[:2]] == [
        "pfsense_firewall_noisy_source",
        "pfsense_firewall_port_scan",
    ]
    assert data[0]["fired_count_24h"] == 2
    assert data[1]["fired_count_24h"] == 2


def test_get_pfsense_detection_health_badge_boundaries_are_exact(client, postgres_db):
    conn, cur = postgres_db
    now = datetime.now(timezone.utc)
    rows = []
    for index in range(5):
        rows.extend([
            "pfsense_firewall_suspicious_allow",
            "medium",
            f"198.51.100.{70 + index}",
            f"Suspicious allow {index}",
            now - timedelta(minutes=index),
        ])
    for index in range(20):
        rows.extend([
            "pfsense_firewall_port_scan",
            "medium",
            f"198.51.100.{90 + index}",
            f"Port scan {index}",
            now - timedelta(minutes=index),
        ])

    placeholders = ", ".join(["(%s, %s, %s, 'pfsense', 'firewall', %s, 'open', %s)"] * 25)
    cur.execute(
        f"""
        INSERT INTO alerts (alert_type, severity, source_ip, source, source_type, message, status, created_at)
        VALUES {placeholders}
        """,
        tuple(rows),
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/admin/detection-rules/pfsense-health")

    assert resp.status_code == 200
    data = {row["rule_id"]: row for row in resp.get_json()}
    assert data["pfsense_firewall_suspicious_allow"]["fired_count_24h"] == 5
    assert data["pfsense_firewall_suspicious_allow"]["health_badge"] == "Needs Review"
    assert data["pfsense_firewall_port_scan"]["fired_count_24h"] == 20
    assert data["pfsense_firewall_port_scan"]["health_badge"] == "Noisy"


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


def test_get_and_patch_notification_policy_apply_immediately_and_audit(client, postgres_db):
    conn, cur = postgres_db
    _login_super_admin(client)
    with _patched_app_db(conn):
        response = client.get("/admin/notification-policy")
        assert response.status_code == 200
        assert response.get_json()["slack_enabled"] is False

        updated = client.patch(
            "/admin/notification-policy",
            json={
                "slack_enabled": True,
                "minimum_severity": "critical",
                "notify_on_alerts": False,
                "notify_on_incidents": True,
                "slack_format": "detailed",
                "pfsense_destination": "#soc-pfsense",
                "honeypot_destination": "#soc-honeypot",
                "critical_cross_source_destination": "#soc-critical",
            },
        )
        assert updated.status_code == 200
        assert updated.get_json()["slack_enabled"] is True
        assert updated.get_json()["minimum_severity"] == "critical"
        assert updated.get_json()["slack_format"] == "detailed"

        immediate = client.get("/admin/notification-policy")
        assert immediate.status_code == 200
        assert immediate.get_json()["pfsense_destination"] == "#soc-pfsense"

    cur.execute(
        """
        SELECT
            slack_enabled,
            minimum_severity,
            pfsense_destination,
            honeypot_destination,
            critical_cross_source_destination
        FROM notification_policy
        WHERE id = 1
        """
    )
    assert cur.fetchone() == (
        True,
        "critical",
        "#soc-pfsense",
        "#soc-honeypot",
        "#soc-critical",
    )

    cur.execute(
        "SELECT details FROM audit_log WHERE event_type = 'notification_policy_updated' ORDER BY id DESC LIMIT 1"
    )
    audit = cur.fetchone()[0]
    changed_fields = {item["field"] for item in audit["changes"]}
    assert {
        "slack_enabled",
        "minimum_severity",
        "notify_on_alerts",
        "slack_format",
        "pfsense_destination",
        "honeypot_destination",
        "critical_cross_source_destination",
    } <= changed_fields


@pytest.mark.parametrize(
    "payload,error_text",
    [
        ({}, "Notification policy payload must be a non-empty object"),
        ({"minimum_severity": "urgent"}, "minimum_severity must be one of"),
        ({"slack_format": "rich"}, "slack_format must be one of"),
        ({"pfsense_destination": "https://hooks.slack.com/services/x"}, "routing label"),
    ],
)
def test_notification_policy_update_validation_errors_return_400(client, postgres_db, payload, error_text):
    conn, _ = postgres_db
    _login_super_admin(client)
    with _patched_app_db(conn):
        response = client.patch("/admin/notification-policy", json=payload)
    assert response.status_code == 400
    assert error_text in response.get_json()["error"]


def test_notification_policy_route_test_records_attempt_without_other_writes(client, postgres_db):
    conn, cur = postgres_db
    _login_super_admin(client)

    before = {}
    for table in (
        "alerts",
        "incidents",
        "playbook_executions",
        "approval_requests",
        "notification_delivery_attempts",
    ):
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        before[table] = cur.fetchone()[0]

    with _patched_app_db(conn), patch(
        "routes.admin_routes.send_notification_policy_route_test",
        return_value={
            "route_key": "pfsense",
            "success": True,
            "status": "success",
            "message": "Notification policy route test sent for pfsense.",
            "attempt": {
                "id": 77,
                "provider": "slack",
                "status": "success",
                "action": "send_message",
                "created_at": "2026-07-14T00:00:00+00:00",
                "completed_at": "2026-07-14T00:00:00+00:00",
                "failure_code": None,
                "failure_message": None,
            },
        },
    ) as route_test:
        response = client.post("/admin/notification-policy/test/pfsense")

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    route_test.assert_called_once()

    for table in ("alerts", "incidents", "playbook_executions", "approval_requests"):
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        assert cur.fetchone()[0] == before[table]

    cur.execute(
        "SELECT details FROM audit_log WHERE event_type = 'notification_policy_route_test_requested' ORDER BY id DESC LIMIT 1"
    )
    audit = cur.fetchone()[0]
    assert audit["route_key"] == "pfsense"
    assert audit["success"] is True
    assert audit["bypassed_slack_disabled"] is True


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
