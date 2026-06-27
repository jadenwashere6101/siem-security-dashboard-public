from unittest.mock import patch

from core import soar_response_outcomes as outcomes


ADMIN_USER = "testadmin"
ADMIN_PASS = "testpassword123!"
BEHAVIORAL_REPUTATION = {
    "reputation_score": 0,
    "reputation_label": "Normal",
    "reputation_summary": "Contract test behavioral reputation",
    "contributing_signals": [],
}


class _RouteSafeConnection:
    """Route-level connection wrapper that ignores close()."""

    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return self._conn.cursor()

    def close(self):
        return None


def _insert_alert(
    cur,
    *,
    alert_type="failed_login_threshold",
    source_ip="198.51.100.31",
    message="Contract alert for response outcome",
    response_action="monitor",
    response_status="pending",
):
    cur.execute(
        """
        INSERT INTO alerts (
            alert_type,
            severity,
            source_ip,
            source,
            source_type,
            message,
            status,
            response_action,
            response_status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            alert_type,
            "high",
            source_ip,
            "bank_app",
            "custom",
            message,
            "open",
            response_action,
            response_status,
        ),
    )
    return cur.fetchone()[0]


def _login_as_super_admin(client):
    resp = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert resp.status_code == 200


def _fetch_alerts_response(client, conn):
    with patch("routes.alerts_events_routes.get_db_connection", return_value=_RouteSafeConnection(conn)), patch(
        "routes.alerts_events_routes.get_ip_reputation", return_value=BEHAVIORAL_REPUTATION
    ):
        return client.get("/alerts")


def _fetch_alert_detail_response(client, conn, alert_id):
    with patch("routes.alerts_events_routes.get_db_connection", return_value=_RouteSafeConnection(conn)), patch(
        "routes.alerts_events_routes.get_ip_reputation", return_value=BEHAVIORAL_REPUTATION
    ):
        return client.get(f"/alerts/{alert_id}")


def _make_canonical_outcome(conn, cur, alert_id):
    decision = outcomes.create_response_decision(
        conn,
        alert_id=alert_id,
        selected_action="monitor",
        decision_source="manual",
        outcome_summary="Decision summary should not appear at top level.",
    )
    conn.commit()
    event = outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        execution_mode="simulation",
        execution_state="succeeded",
        simulated=True,
        execution_actor="manual",
        outcome_summary="Canonical event outcome summary.",
        reason_code="simulation_mode",
    )
    conn.commit()
    return decision, event


def test_get_alerts_includes_response_outcome_key(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()

    _login_as_super_admin(client)
    resp = _fetch_alerts_response(client, conn)

    assert resp.status_code == 200
    alert = next(item for item in resp.get_json() if item["id"] == alert_id)
    assert "response_outcome" in alert
    assert alert["response_outcome"] is None


def test_get_alert_detail_includes_response_outcome_key(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()

    _login_as_super_admin(client)
    resp = _fetch_alert_detail_response(client, conn, alert_id)

    assert resp.status_code == 200
    alert = resp.get_json()
    assert alert["id"] == alert_id
    assert "response_outcome" in alert
    assert alert["response_outcome"] is None


def test_get_alerts_preserves_legacy_response_fields(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(
        cur,
        response_action="block_ip",
        response_status="executed",
    )
    conn.commit()

    _login_as_super_admin(client)
    resp = _fetch_alerts_response(client, conn)

    assert resp.status_code == 200
    alert = next(item for item in resp.get_json() if item["id"] == alert_id)
    assert alert["response_action"] == "block_ip"
    assert alert["response_status"] == "executed"


def test_get_alert_detail_preserves_legacy_response_fields(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(
        cur,
        response_action="escalate",
        response_status="pending",
    )
    conn.commit()

    _login_as_super_admin(client)
    resp = _fetch_alert_detail_response(client, conn, alert_id)

    assert resp.status_code == 200
    alert = resp.get_json()
    assert alert["response_action"] == "escalate"
    assert alert["response_status"] == "pending"


def test_get_alerts_without_canonical_outcome_returns_null_response_outcome(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()

    _login_as_super_admin(client)
    resp = _fetch_alerts_response(client, conn)

    assert resp.status_code == 200
    alert = next(item for item in resp.get_json() if item["id"] == alert_id)
    assert alert["response_outcome"] is None


def test_get_alert_detail_without_canonical_outcome_returns_null_response_outcome(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()

    _login_as_super_admin(client)
    resp = _fetch_alert_detail_response(client, conn, alert_id)

    assert resp.status_code == 200
    assert resp.get_json()["response_outcome"] is None


def test_get_alerts_includes_canonical_response_outcome_shape(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    decision, event = _make_canonical_outcome(conn, cur, alert_id)

    _login_as_super_admin(client)
    resp = _fetch_alerts_response(client, conn)

    assert resp.status_code == 200
    alert = next(item for item in resp.get_json() if item["id"] == alert_id)
    outcome = alert["response_outcome"]
    assert outcome is not None
    assert outcome["decision_id"] == decision["id"]
    assert outcome["latest_outcome_event_id"] == event["id"]
    assert outcome["selected_action"] == "monitor"
    assert outcome["execution_mode"] == "simulation"
    assert outcome["execution_state"] == "succeeded"
    assert outcome["outcome_summary"] == "Canonical event outcome summary."


def test_get_alert_detail_uses_serialize_latest_outcome(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    decision, event = _make_canonical_outcome(conn, cur, alert_id)
    expected = outcomes.serialize_latest_outcome(conn, alert_id=alert_id)

    _login_as_super_admin(client)
    with patch("routes.alerts_events_routes.get_db_connection", return_value=_RouteSafeConnection(conn)), patch(
        "routes.alerts_events_routes.get_ip_reputation", return_value=BEHAVIORAL_REPUTATION
    ), patch(
        "routes.alerts_events_routes.serialize_latest_outcome", return_value=expected
    ) as serialize_mock:
        resp = client.get(f"/alerts/{alert_id}")

    assert resp.status_code == 200
    serialize_mock.assert_called_once()
    assert serialize_mock.call_args.kwargs["alert_id"] == alert_id
    assert resp.get_json()["response_outcome"] == expected
    assert resp.get_json()["response_outcome"]["decision_id"] == decision["id"]
    assert resp.get_json()["response_outcome"]["latest_outcome_event_id"] == event["id"]


def test_get_alerts_uses_bulk_outcome_helper_once(client, postgres_db):
    conn, cur = postgres_db
    alert_id_a = _insert_alert(cur, source_ip="198.51.100.41", message="Alert A")
    alert_id_b = _insert_alert(cur, source_ip="198.51.100.42", message="Alert B")
    _make_canonical_outcome(conn, cur, alert_id_a)
    _make_canonical_outcome(conn, cur, alert_id_b)

    _login_as_super_admin(client)
    with patch("routes.alerts_events_routes.get_db_connection", return_value=_RouteSafeConnection(conn)), patch(
        "routes.alerts_events_routes.get_ip_reputation", return_value=BEHAVIORAL_REPUTATION
    ), patch(
        "routes.alerts_events_routes.get_latest_outcomes_for_alerts_bulk",
        wraps=outcomes.get_latest_outcomes_for_alerts_bulk,
    ) as bulk_mock, patch(
        "routes.alerts_events_routes.serialize_latest_outcome"
    ) as serialize_mock:
        resp = client.get("/alerts")

    assert resp.status_code == 200
    bulk_mock.assert_called_once()
    bulk_alert_ids = set(bulk_mock.call_args.args[1])
    assert alert_id_a in bulk_alert_ids
    assert alert_id_b in bulk_alert_ids
    serialize_mock.assert_not_called()

    data = resp.get_json()
    alert_a = next(item for item in data if item["id"] == alert_id_a)
    alert_b = next(item for item in data if item["id"] == alert_id_b)
    assert alert_a["response_outcome"] is not None
    assert alert_b["response_outcome"] is not None
