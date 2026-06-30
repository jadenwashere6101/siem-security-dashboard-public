from contextlib import contextmanager
from unittest.mock import patch

from routes.alert_mutation_routes import MAX_ALERT_NOTE_LENGTH


ADMIN_USER = "testadmin"
ADMIN_PASS = "testpassword123!"


class _RouteSafeConnection:
    """Route-level connection wrapper that ignores close()."""

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
    with patch("routes.alert_mutation_routes.get_db_connection", return_value=wrapper), patch(
        "core.audit_helpers.get_db_connection", return_value=wrapper
    ):
        yield


def _login_super_admin(client):
    resp = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert resp.status_code == 200


def _insert_alert(cur, *, source_ip="198.51.100.250", message="Contract alert"):
    cur.execute(
        """
        INSERT INTO alerts (
            alert_type,
            severity,
            source_ip,
            source,
            source_type,
            message,
            status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        ("failed_login_threshold", "high", source_ip, "bank_app", "custom", message, "open"),
    )
    return cur.fetchone()[0]


def _fetch_manual_outcomes(cur, alert_id):
    cur.execute(
        """
        SELECT d.selected_action,
               d.decision_source,
               d.reason_code,
               e.execution_mode,
               e.execution_state,
               e.simulated,
               e.external_executed,
               e.tracking_recorded,
               e.execution_actor,
               e.reason_code,
               e.outcome_summary,
               e.response_action_log_id
        FROM soar_response_decisions d
        JOIN soar_response_outcome_events e ON e.decision_id = d.id
        WHERE d.alert_id = %s
        ORDER BY e.id
        """,
        (alert_id,),
    )
    return cur.fetchall()


def _fetch_response_log_links(cur, alert_id):
    cur.execute(
        """
        SELECT id, action, status, details, decision_id, soar_correlation_id
        FROM response_actions_log
        WHERE alert_id = %s
        ORDER BY id
        """,
        (alert_id,),
    )
    return cur.fetchall()


def _count_response_log_route_state(cur, alert_id):
    cur.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM response_actions_log WHERE alert_id = %s),
            (SELECT COUNT(*) FROM soar_response_decisions WHERE alert_id = %s),
            (SELECT COUNT(*) FROM soar_response_outcome_events WHERE alert_id = %s)
        """,
        (alert_id, alert_id, alert_id),
    )
    return cur.fetchone()


def test_get_alert_notes_without_session_returns_401(client):
    resp = client.get("/alerts/1/notes")
    assert resp.status_code == 401


def test_get_alert_notes_authenticated_returns_200_stable_json_shape(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    cur.execute(
        """
        INSERT INTO alert_notes (alert_id, author, note_text)
        VALUES (%s, %s, %s)
        """,
        (alert_id, "admin", "contract note"),
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get(f"/alerts/{alert_id}/notes")

    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) >= 1
    note = data[0]
    for key in ("id", "alert_id", "author", "note_text", "created_at"):
        assert key in note


def test_post_alert_notes_invalid_or_too_long_returns_400(client):
    _login_super_admin(client)
    max_len = MAX_ALERT_NOTE_LENGTH

    resp_empty = client.post("/alerts/99999/notes", json={"note_text": "   "})
    assert resp_empty.status_code == 400
    assert resp_empty.get_json()["error"] == "note_text is required"

    too_long = "x" * (max_len + 1)
    resp_long = client.post("/alerts/99999/notes", json={"note_text": too_long})
    assert resp_long.status_code == 400
    err = resp_long.get_json()["error"]
    assert str(max_len) in err


def test_post_alert_status_without_session_returns_401(client):
    resp = client.post("/alerts/1/status", json={"status": "resolved"})
    assert resp.status_code == 401


def test_post_alert_status_invalid_status_returns_400(client):
    _login_super_admin(client)
    resp = client.post("/alerts/1/status", json={"status": "not_a_valid_status"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Invalid status"


def test_post_alert_execute_without_session_returns_401(client):
    resp = client.post("/alerts/1/execute", json={"action": "monitor"})
    assert resp.status_code == 401


def test_post_alert_execute_missing_action_returns_400(client):
    _login_super_admin(client)
    resp = client.post("/alerts/1/execute", json={})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Missing action"


def test_post_alert_execute_invalid_action_returns_400(client):
    _login_super_admin(client)
    resp = client.post("/alerts/1/execute", json={"action": "not_a_valid_action"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Invalid response action"


def test_post_alert_execute_nonexistent_alert_id_returns_404(client, postgres_db):
    conn, _ = postgres_db
    _login_super_admin(client)

    with _patched_app_db(conn):
        resp = client.post("/alerts/99999/execute", json={"action": "monitor"})

    assert resp.status_code == 404
    assert resp.get_json()["error"] == "Alert not found"


def test_post_alert_execute_monitor_creates_simulation_outcome_and_keeps_response_shape(
    client, postgres_db
):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, source_ip="198.51.100.252")
    conn.commit()
    _login_super_admin(client)

    with _patched_app_db(conn):
        resp = client.post(f"/alerts/{alert_id}/execute", json={"action": "monitor"})

    assert resp.status_code == 200
    assert resp.get_json() == {
        "message": "Action executed successfully",
        "alert_id": alert_id,
        "action": "monitor",
        "response_status": "executed",
    }
    logs = _fetch_response_log_links(cur, alert_id)
    assert len(logs) == 1
    assert logs[0][1:4] == ("monitor", "executed", "Monitoring only")
    assert logs[0][4] is not None
    assert logs[0][5]

    outcomes = _fetch_manual_outcomes(cur, alert_id)
    assert outcomes == [
        (
            "monitor",
            "manual",
            "simulation_mode",
            "simulation",
            "succeeded",
            True,
            False,
            False,
            "manual",
            "simulation_mode",
            "Manual monitor response completed in simulation mode.",
            logs[0][0],
        )
    ]


def test_post_alert_execute_flag_high_priority_creates_simulation_outcome(
    client, postgres_db
):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, source_ip="198.51.100.253")
    conn.commit()
    _login_super_admin(client)

    with _patched_app_db(conn):
        resp = client.post(
            f"/alerts/{alert_id}/execute",
            json={"action": "flag_high_priority"},
        )

    assert resp.status_code == 200
    outcomes = _fetch_manual_outcomes(cur, alert_id)
    assert len(outcomes) == 1
    assert outcomes[0][0:10] == (
        "flag_high_priority",
        "manual",
        "simulation_mode",
        "simulation",
        "succeeded",
        True,
        False,
        False,
        "manual",
        "simulation_mode",
    )


def test_post_alert_execute_block_ip_creates_tracking_only_outcome_and_log_link(
    client, postgres_db
):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, source_ip="8.8.4.4")
    conn.commit()
    _login_super_admin(client)

    with _patched_app_db(conn):
        resp = client.post(f"/alerts/{alert_id}/execute", json={"action": "block_ip"})

    assert resp.status_code == 200
    logs = _fetch_response_log_links(cur, alert_id)
    assert len(logs) == 1
    assert logs[0][1:4] == (
        "block_ip",
        "executed",
        "Recorded in SIEM blocklist (tracking only)",
    )
    assert logs[0][4] is not None
    assert logs[0][5]

    cur.execute(
        """
        SELECT host(ip_address), status, source_alert_id
        FROM blocked_ips
        WHERE source_alert_id = %s
        """,
        (alert_id,),
    )
    assert cur.fetchall() == [("8.8.4.4", "active", alert_id)]

    outcomes = _fetch_manual_outcomes(cur, alert_id)
    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome[0:10] == (
        "block_ip",
        "manual",
        "tracking_only",
        "tracking_only",
        "succeeded",
        False,
        False,
        True,
        "manual",
        "tracking_only",
    )
    assert "SIEM blocklist tracking was recorded" in outcome[10]
    assert "no firewall" in outcome[10].lower()
    assert outcome[11] == logs[0][0]


def test_post_alert_execute_duplicate_block_ip_does_not_write_tracking_success(
    client, postgres_db
):
    conn, cur = postgres_db
    first_alert_id = _insert_alert(cur, source_ip="8.8.4.5")
    duplicate_alert_id = _insert_alert(cur, source_ip="8.8.4.5")
    cur.execute(
        """
        INSERT INTO blocked_ips (ip_address, status, source_alert_id)
        VALUES ('8.8.4.5', 'active', %s)
        """,
        (first_alert_id,),
    )
    conn.commit()
    _login_super_admin(client)

    with _patched_app_db(conn):
        resp = client.post(
            f"/alerts/{duplicate_alert_id}/execute",
            json={"action": "block_ip"},
        )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "An active block already exists for this IP"
    assert _fetch_response_log_links(cur, duplicate_alert_id) == []
    assert _fetch_manual_outcomes(cur, duplicate_alert_id) == []


def test_post_alert_execute_invalid_block_ip_does_not_write_tracking_success(
    client, postgres_db
):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, source_ip="10.0.0.1")
    conn.commit()
    _login_super_admin(client)

    with _patched_app_db(conn):
        resp = client.post(f"/alerts/{alert_id}/execute", json={"action": "block_ip"})

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Private, loopback, and internal IPs cannot be blocked"
    assert _fetch_response_log_links(cur, alert_id) == []
    assert _fetch_manual_outcomes(cur, alert_id) == []


def test_post_alert_execute_canonical_write_failure_rolls_back_legacy_success(
    client, postgres_db
):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, source_ip="198.51.100.254")
    conn.commit()
    _login_super_admin(client)

    def fail_append(*_args, **_kwargs):
        raise RuntimeError("canonical writer unavailable")

    with _patched_app_db(conn), patch(
        "routes.alert_mutation_routes.append_outcome_event",
        side_effect=fail_append,
    ):
        resp = client.post(f"/alerts/{alert_id}/execute", json={"action": "monitor"})

    assert resp.status_code == 500
    assert resp.get_json()["error"] == "Internal server error"
    assert _fetch_response_log_links(cur, alert_id) == []
    assert _fetch_manual_outcomes(cur, alert_id) == []
    cur.execute(
        "SELECT response_action, response_status FROM alerts WHERE id = %s",
        (alert_id,),
    )
    assert cur.fetchone() == (None, None)


def test_get_alert_response_log_authenticated_returns_200_stable_json_shape(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, source_ip="198.51.100.251", message="Response log contract")
    cur.execute(
        """
        INSERT INTO response_actions_log (alert_id, source_ip, action, status, details)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (alert_id, "203.0.113.10", "monitor", "executed", "contract details"),
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get(f"/alerts/{alert_id}/response-log")

    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) >= 1
    entry = data[0]
    for key in (
        "id",
        "alert_id",
        "source_ip",
        "action",
        "status",
        "details",
        "executed_at",
        "response_outcome",
    ):
        assert key in entry
    assert entry["id"] is not None
    assert entry["alert_id"] == alert_id
    assert entry["source_ip"] == "203.0.113.10"
    assert entry["action"] == "monitor"
    assert entry["status"] == "executed"
    assert entry["details"] == "contract details"


def test_get_alert_response_log_linked_canonical_log_returns_response_outcome(
    client, postgres_db
):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, source_ip="198.51.100.252")
    conn.commit()
    _login_super_admin(client)

    with _patched_app_db(conn):
        execute_resp = client.post(f"/alerts/{alert_id}/execute", json={"action": "monitor"})
        assert execute_resp.status_code == 200

        before_counts = _count_response_log_route_state(cur, alert_id)
        resp = client.get(f"/alerts/{alert_id}/response-log")
        after_counts = _count_response_log_route_state(cur, alert_id)

    assert resp.status_code == 200
    assert after_counts == before_counts
    data = resp.get_json()
    assert len(data) == 1
    entry = data[0]
    for key in ("id", "alert_id", "source_ip", "action", "status", "details", "executed_at"):
        assert key in entry
    outcome = entry["response_outcome"]
    assert outcome is not None
    assert outcome["inferred"] is False
    assert outcome["decision_id"] is not None
    assert outcome["latest_outcome_event_id"] is not None
    assert outcome["selected_action"] == "monitor"
    assert outcome["decision_source"] == "manual"
    assert outcome["execution_mode"] == "simulation"
    assert outcome["execution_state"] == "succeeded"
    assert outcome["simulated"] is True
    assert outcome["external_executed"] is False
    assert outcome["tracking_recorded"] is False
    assert outcome["related"]["alert_id"] == alert_id
    assert outcome["source_table"] == "response_actions_log"
    assert outcome["source_id"] == entry["id"]
    assert outcome["latest_outcome"]["response_action_log_id"] == entry["id"]


def test_get_alert_response_log_unlinked_legacy_log_returns_conservative_outcome(
    client, postgres_db
):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, source_ip="198.51.100.253", message="Legacy log")
    cur.execute(
        """
        INSERT INTO response_actions_log (alert_id, source_ip, action, status, details)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (alert_id, "203.0.113.11", "monitor", "executed", "legacy simulation"),
    )
    log_id = cur.fetchone()[0]
    conn.commit()

    _login_super_admin(client)
    before_counts = _count_response_log_route_state(cur, alert_id)
    with _patched_app_db(conn):
        resp = client.get(f"/alerts/{alert_id}/response-log")
    after_counts = _count_response_log_route_state(cur, alert_id)

    assert resp.status_code == 200
    assert after_counts == before_counts
    data = resp.get_json()
    assert len(data) == 1
    entry = data[0]
    assert entry["id"] == log_id
    assert entry["alert_id"] == alert_id
    assert entry["source_ip"] == "203.0.113.11"
    assert entry["action"] == "monitor"
    assert entry["status"] == "executed"
    assert entry["details"] == "legacy simulation"
    outcome = entry["response_outcome"]
    assert outcome is not None
    assert outcome["inferred"] is True
    assert outcome["decision_id"] is None
    assert outcome["latest_outcome_event_id"] is None
    assert outcome["selected_action"] == "monitor"
    assert outcome["execution_mode"] == "simulation"
    assert outcome["execution_state"] == "succeeded"
    assert outcome["simulated"] is True
    assert outcome["external_executed"] is False
    assert outcome["tracking_recorded"] is False
    assert outcome["related"]["alert_id"] == alert_id
    assert outcome["related"]["response_action_log_id"] == log_id


def test_get_alert_response_log_resolver_miss_returns_null_response_outcome(
    client, postgres_db
):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, source_ip="198.51.100.254", message="Resolver miss")
    cur.execute(
        """
        INSERT INTO response_actions_log (alert_id, source_ip, action, status, details)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (alert_id, "203.0.113.12", "monitor", "executed", "contract details"),
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn), patch(
        "routes.alert_mutation_routes.resolve_response_log_outcome",
        return_value=None,
    ):
        resp = client.get(f"/alerts/{alert_id}/response-log")

    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["response_outcome"] is None
