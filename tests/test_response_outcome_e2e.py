"""Canonical response outcome API/read-model integration tests (Phase 11).

These tests seed canonical decisions/events directly and verify the API read models
that expose them. They intentionally do not claim to exercise writer/orchestrator
workflows end-to-end.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from core import notification_delivery_store
from core import playbook_store
from core import soar_response_outcomes as outcomes
from core.approval_store import create_approval_request
from response_outcome_test_helpers import patched_route_db

ADMIN_USER = "testadmin"
ADMIN_PASS = "testpassword123!"
SOURCE_IP = "198.51.100.77"


def _login_super_admin(client):
    resp = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert resp.status_code == 200


def _insert_alert(cur, *, source_ip=SOURCE_IP):
    cur.execute(
        """
        INSERT INTO alerts (
            alert_type, severity, source_ip, source, source_type, message,
            status, response_action, response_status
        )
        VALUES (
            'failed_login_threshold', 'high', %s::inet, 'bank_app', 'custom',
            'e2e alert', 'open', 'monitor', 'pending'
        )
        RETURNING id
        """,
        (source_ip,),
    )
    return cur.fetchone()[0]


def _insert_incident(cur, *, source_ip=SOURCE_IP, alert_id=None):
    cur.execute(
        """
        INSERT INTO incidents (title, severity, priority, status, source_ip)
        VALUES ('E2E incident', 'high', 'P1', 'investigating', %s::inet)
        RETURNING id
        """,
        (source_ip,),
    )
    incident_id = cur.fetchone()[0]
    if alert_id is not None:
        cur.execute(
            "INSERT INTO incident_alerts (incident_id, alert_id) VALUES (%s, %s)",
            (incident_id, alert_id),
        )
    return incident_id


def _insert_queue_row(cur, alert_id, *, source_ip=SOURCE_IP, action="block_ip"):
    idem = hashlib.sha256(f"{action}:{source_ip}:{alert_id}".encode()).hexdigest()
    cur.execute(
        """
        INSERT INTO response_actions_queue
        (idempotency_key, alert_id, source_ip, action, status)
        VALUES (%s, %s, %s::inet, %s, 'pending')
        RETURNING id
        """,
        (idem, alert_id, source_ip, action),
    )
    return cur.fetchone()[0]


def _insert_approval(conn, incident_id):
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    approval = create_approval_request(
        conn,
        incident_id=incident_id,
        action="block_ip",
        risk_level="high",
        request_reason="e2e approval",
        expires_at=future,
    )
    conn.commit()
    return approval


def _valid_steps():
    return [{"action": "monitor", "params": {}}]


def test_api_integration_observed_only_alert_returns_null_response_outcome(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()

    _login_super_admin(client)
    with patched_route_db(conn, "routes.alerts_events_routes"):
        resp = client.get(f"/alerts/{alert_id}")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["response_outcome"] is None
    assert body["response_action"] == "monitor"


def test_api_integration_simulated_queue_action_shape(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    queue_id = _insert_queue_row(cur, alert_id)
    decision = outcomes.create_response_decision(
        conn,
        alert_id=alert_id,
        source_ip=SOURCE_IP,
        queue_id=queue_id,
        selected_action="block_ip",
        decision_source="detection_default",
        outcome_summary="Detection selected simulated queue action.",
    )
    cur.execute(
        """
        UPDATE response_actions_queue
        SET decision_id = %s, soar_correlation_id = %s
        WHERE id = %s
        """,
        (decision["id"], decision["soar_correlation_id"], queue_id),
    )
    event = outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        execution_mode="simulation",
        execution_state="succeeded",
        simulated=True,
        execution_actor="queue_worker",
        outcome_summary="Simulated queue action completed.",
        alert_id=alert_id,
        source_ip=SOURCE_IP,
        queue_id=queue_id,
        reason_code="simulation_mode",
    )
    conn.commit()

    _login_super_admin(client)
    with patched_route_db(conn, "routes.admin_routes"):
        resp = client.get(f"/admin/soar/queue/{queue_id}")

    assert resp.status_code == 200
    outcome = resp.get_json()["response_outcome"]
    assert outcome["decision_id"] == decision["id"]
    assert outcome["latest_outcome_event_id"] == event["id"]
    assert outcome["execution_mode"] == "simulation"
    assert outcome["execution_state"] == "succeeded"
    assert outcome["simulated"] is True
    assert outcome["external_executed"] is False
    assert outcome["tracking_recorded"] is False


def test_api_integration_tracking_only_blocklist_action(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, source_ip="8.8.8.8")
    cur.execute(
        """
        INSERT INTO blocked_ips (ip_address, reason, status, source_alert_id)
        VALUES (%s::inet, 'e2e tracking only', 'active', %s)
        RETURNING id
        """,
        ("8.8.8.8", alert_id),
    )
    block_id = cur.fetchone()[0]
    decision = outcomes.create_response_decision(
        conn,
        alert_id=alert_id,
        source_ip="8.8.8.8",
        selected_action="block_ip",
        decision_source="manual",
        outcome_summary="Manual tracking-only block selected.",
        reason_code="tracking_only",
    )
    event = outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        execution_mode="tracking_only",
        execution_state="succeeded",
        tracking_recorded=True,
        execution_actor="manual",
        outcome_summary="Tracking-only block recorded.",
        alert_id=alert_id,
        source_ip="8.8.8.8",
        reason_code="tracking_only",
    )
    conn.commit()

    _login_super_admin(client)
    with patched_route_db(conn, "routes.blocklist_routes"):
        resp = client.get("/blocked-ips")

    assert resp.status_code == 200
    entry = next(item for item in resp.get_json() if item["id"] == block_id)
    outcome = entry["response_outcome"]
    assert outcome["execution_mode"] == "tracking_only"
    assert outcome["external_executed"] is False
    assert outcome["tracking_recorded"] is True
    assert outcomes.derive_outcome_label(
        execution_mode=outcome["execution_mode"],
        execution_state=outcome["execution_state"],
        external_executed=outcome["external_executed"],
        tracking_recorded=outcome["tracking_recorded"],
        simulated=outcome["simulated"],
    ) == "Tracking only"
    assert event["execution_mode"] == "tracking_only"


def test_api_integration_playbook_simulation_step_sequence(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    playbook_store.create_playbook_definition(conn, "pb_e2e_steps", "Steps", steps=_valid_steps())
    execution_id = playbook_store.create_playbook_execution(conn, "pb_e2e_steps", alert_id)
    decision = outcomes.create_response_decision(
        conn,
        alert_id=alert_id,
        playbook_id="pb_e2e_steps",
        playbook_execution_id=execution_id,
        selected_action="run_playbook",
        decision_source="playbook",
        outcome_summary="Playbook execution selected.",
    )
    step_events = []
    for step_index in (0, 1):
        step_events.append(
            outcomes.append_outcome_event(
                conn,
                decision_id=decision["id"],
                execution_mode="simulation",
                execution_state="succeeded",
                simulated=True,
                execution_actor="playbook_worker",
                outcome_summary=f"Simulated step {step_index} completed.",
                alert_id=alert_id,
                playbook_execution_id=execution_id,
                playbook_step_index=step_index,
                event_type="step_succeeded",
            )
        )
    playbook_store.set_playbook_execution_canonical_linkage(
        conn,
        execution_id,
        decision["id"],
        decision["soar_correlation_id"],
    )
    conn.commit()

    _login_super_admin(client)
    with patched_route_db(conn, "routes.playbook_routes"):
        resp = client.get(f"/playbook-executions/{execution_id}")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["response_outcome"]["decision_id"] == decision["id"]
    assert len(body["response_outcomes"]) == 2
    assert all(item["decision_id"] == decision["id"] for item in body["response_outcomes"])
    assert {item["playbook_step_index"] for item in body["response_outcomes"]} == {0, 1}
    assert body["response_outcomes"][-1]["id"] == step_events[-1]["id"]


def test_api_integration_playbook_awaiting_approval(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    playbook_store.create_playbook_definition(conn, "pb_e2e_wait", "Wait", steps=_valid_steps())
    execution_id = playbook_store.create_playbook_execution(conn, "pb_e2e_wait", alert_id)
    decision = outcomes.create_response_decision(
        conn,
        alert_id=alert_id,
        playbook_id="pb_e2e_wait",
        playbook_execution_id=execution_id,
        selected_action="run_playbook",
        decision_source="playbook",
        outcome_summary="Playbook awaiting approval.",
    )
    event = outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        execution_mode="simulation",
        execution_state="awaiting_approval",
        simulated=True,
        execution_actor="playbook_worker",
        outcome_summary="Playbook paused for approval.",
        alert_id=alert_id,
        playbook_execution_id=execution_id,
        reason_code="approval_required",
        event_type="awaiting_approval",
    )
    playbook_store.set_playbook_execution_canonical_linkage(
        conn, execution_id, decision["id"], decision["soar_correlation_id"]
    )
    conn.commit()

    _login_super_admin(client)
    with patched_route_db(conn, "routes.playbook_routes"):
        resp = client.get(f"/playbook-executions/{execution_id}")

    outcome = resp.get_json()["response_outcome"]
    assert outcome["execution_state"] == "awaiting_approval"
    assert event["execution_state"] == "awaiting_approval"


def test_api_integration_approval_denied_blocks_execution(client, postgres_db):
    conn, cur = postgres_db
    incident_id = _insert_incident(cur)
    approval = _insert_approval(conn, incident_id)
    decision = outcomes.create_response_decision(
        conn,
        incident_id=incident_id,
        approval_request_id=approval["id"],
        selected_action="block_ip",
        decision_source="manual",
        outcome_summary="Approval-gated response selected.",
    )
    event = outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        execution_mode="simulation",
        execution_state="blocked",
        simulated=True,
        execution_actor="approval_service",
        outcome_summary="Approval denied; execution blocked.",
        incident_id=incident_id,
        approval_request_id=approval["id"],
        reason_code="approval_denied",
        event_type="blocked",
    )
    conn.commit()

    _login_super_admin(client)
    with patched_route_db(conn, "routes.approval_routes"):
        resp = client.get(f"/approvals/{approval['id']}")

    outcome = resp.get_json()["approval"]["response_outcome"]
    assert outcome["execution_state"] == "blocked"
    assert outcome["reason_code"] == "approval_denied"
    assert outcome["external_executed"] is False
    assert event["reason_code"] == "approval_denied"


def test_api_integration_notification_simulated_delivery(client, postgres_db):
    conn, _cur = postgres_db
    row = notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="nd-e2e-sim",
        idempotency_key="nd-e2e-sim-key",
        provider="slack",
        mode="simulation",
        status="success",
        adapter_name="slack",
        action="send_message",
    )
    decision = outcomes.create_response_decision(
        conn,
        selected_action="notify_slack",
        decision_source="manual",
        outcome_summary="Notification selected.",
    )
    event = outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        execution_mode="simulation",
        execution_state="succeeded",
        simulated=True,
        execution_actor="adapter",
        outcome_summary="Notification simulated.",
        notification_delivery_attempt_id=row["id"],
        reason_code="simulation_mode",
    )
    conn.cursor().execute(
        """
        UPDATE notification_delivery_attempts
        SET decision_id = %s, soar_correlation_id = %s
        WHERE id = %s
        """,
        (decision["id"], decision["soar_correlation_id"], row["id"]),
    )
    conn.commit()

    _login_super_admin(client)
    with patched_route_db(conn, "routes.notification_delivery_routes"):
        resp = client.get(f"/notification-deliveries/{row['id']}")

    outcome = resp.get_json()["response_outcome"]
    assert outcome["execution_mode"] == "simulation"
    assert outcome["simulated"] is True
    assert outcome["external_executed"] is False
    assert event["simulated"] is True


def test_api_integration_guarded_real_notification_success(client, postgres_db):
    conn, _cur = postgres_db
    row = notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="nd-e2e-real",
        idempotency_key="nd-e2e-real-key",
        provider="email",
        mode="real",
        status="success",
        adapter_name="email",
        action="send_message",
    )
    decision = outcomes.create_response_decision(
        conn,
        selected_action="notify_email",
        decision_source="manual",
        outcome_summary="Real notification selected.",
    )
    event = outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        execution_mode="real",
        execution_state="succeeded",
        external_executed=True,
        execution_actor="adapter",
        outcome_summary="Provider confirmed delivery.",
        notification_delivery_attempt_id=row["id"],
        provider="email",
        adapter_name="email",
        external_reference="mock-provider-msg-1",
    )
    conn.cursor().execute(
        """
        UPDATE notification_delivery_attempts
        SET decision_id = %s, soar_correlation_id = %s
        WHERE id = %s
        """,
        (decision["id"], decision["soar_correlation_id"], row["id"]),
    )
    conn.commit()

    _login_super_admin(client)
    with patched_route_db(conn, "routes.notification_delivery_routes"):
        resp = client.get(f"/notification-deliveries/{row['id']}")

    outcome = resp.get_json()["response_outcome"]
    assert outcome["execution_mode"] == "real"
    assert outcome["external_executed"] is True
    assert outcome["execution_state"] == "succeeded"
    assert event["external_executed"] is True


def test_api_integration_real_capable_notification_fail_closed(client, postgres_db):
    conn, _cur = postgres_db
    row = notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="nd-e2e-fail",
        idempotency_key="nd-e2e-fail-key",
        provider="webhook",
        mode="real",
        status="failed",
        adapter_name="webhook",
        action="send_message",
    )
    decision = outcomes.create_response_decision(
        conn,
        selected_action="notify_webhook",
        decision_source="manual",
        outcome_summary="Real notification attempted.",
    )
    event = outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        execution_mode="real",
        execution_state="failed",
        external_executed=False,
        execution_actor="adapter",
        outcome_summary="Adapter fail-closed; no external execution confirmed.",
        notification_delivery_attempt_id=row["id"],
        reason_code="policy_blocked",
        provider="webhook",
        adapter_name="webhook",
    )
    conn.cursor().execute(
        """
        UPDATE notification_delivery_attempts
        SET decision_id = %s, soar_correlation_id = %s
        WHERE id = %s
        """,
        (decision["id"], decision["soar_correlation_id"], row["id"]),
    )
    conn.commit()

    _login_super_admin(client)
    with patched_route_db(conn, "routes.notification_delivery_routes"):
        resp = client.get(f"/notification-deliveries/{row['id']}")

    outcome = resp.get_json()["response_outcome"]
    assert outcome["execution_mode"] == "real"
    assert outcome["execution_state"] == "failed"
    assert outcome["external_executed"] is False
    assert event["external_executed"] is False


def test_api_integration_cross_surface_canonical_facts_match(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    incident_id = _insert_incident(cur, alert_id=alert_id)
    decision = outcomes.create_response_decision(
        conn,
        alert_id=alert_id,
        incident_id=incident_id,
        source_ip=SOURCE_IP,
        selected_action="block_ip",
        decision_source="manual",
        outcome_summary="Cross-surface canonical outcome.",
    )
    event = outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        execution_mode="tracking_only",
        execution_state="succeeded",
        tracking_recorded=True,
        execution_actor="manual",
        outcome_summary="Tracking-only response for source IP.",
        alert_id=alert_id,
        incident_id=incident_id,
        source_ip=SOURCE_IP,
        reason_code="tracking_only",
    )
    conn.commit()

    _login_super_admin(client)
    with patched_route_db(conn, "routes.source_ip_context_routes", "routes.incident_routes", "routes.metrics_routes"):
        source_resp = client.get(f"/source-ip-context?source_ip={SOURCE_IP}")
        incident_resp = client.get(f"/incidents/{incident_id}")
        metrics_resp = client.get("/metrics/incidents")

    source_outcome = source_resp.get_json()["response_outcomes"][0]
    incident_outcome = incident_resp.get_json()["incident"]["response_outcome"]
    metrics_counts = metrics_resp.get_json()["canonical_outcome_counts"]

    for outcome in (source_outcome, incident_outcome):
        assert outcome["decision_id"] == decision["id"]
        assert outcome["latest_outcome_event_id"] == event["id"]
        assert outcome["execution_mode"] == "tracking_only"
        assert outcome["external_executed"] is False
        assert outcome["tracking_recorded"] is True

    assert metrics_counts["execution_mode"]["tracking_only"] >= 1
    assert metrics_counts["tracking_recorded"]["true"] >= 1
    assert metrics_resp.get_json()["canonical_outcome_retention"]["live_retention_policy"] == "indefinite_by_default"


def test_regression_simulated_never_surfaces_as_real_executed(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    queue_id = _insert_queue_row(cur, alert_id)
    decision = outcomes.create_response_decision(
        conn,
        alert_id=alert_id,
        queue_id=queue_id,
        selected_action="block_ip",
        decision_source="detection_default",
        outcome_summary="Simulated regression seed.",
    )
    cur.execute(
        """
        UPDATE response_actions_queue
        SET decision_id = %s, soar_correlation_id = %s
        WHERE id = %s
        """,
        (decision["id"], decision["soar_correlation_id"], queue_id),
    )
    outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        execution_mode="simulation",
        execution_state="succeeded",
        simulated=True,
        execution_actor="queue_worker",
        outcome_summary="Simulated only.",
        alert_id=alert_id,
        queue_id=queue_id,
    )
    conn.commit()

    _login_super_admin(client)
    with patched_route_db(conn, "routes.alerts_events_routes", "routes.admin_routes"):
        alert_resp = client.get(f"/alerts/{alert_id}")
        queue_resp = client.get(f"/admin/soar/queue/{queue_id}")

    for outcome in (
        alert_resp.get_json()["response_outcome"],
        queue_resp.get_json()["response_outcome"],
    ):
        assert outcome["simulated"] is True
        assert outcome["external_executed"] is False
        assert outcome["execution_mode"] == "simulation"


def test_regression_tracking_only_never_surfaces_as_firewall_enforcement(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    decision = outcomes.create_response_decision(
        conn,
        alert_id=alert_id,
        source_ip=SOURCE_IP,
        selected_action="block_ip",
        decision_source="manual",
        outcome_summary="Tracking-only regression seed.",
    )
    outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        execution_mode="tracking_only",
        execution_state="succeeded",
        tracking_recorded=True,
        execution_actor="manual",
        outcome_summary="Tracking-only block recorded.",
        alert_id=alert_id,
        source_ip=SOURCE_IP,
        reason_code="tracking_only",
    )
    conn.commit()

    _login_super_admin(client)
    with patched_route_db(conn, "routes.alerts_events_routes", "routes.source_ip_context_routes"):
        alert_resp = client.get(f"/alerts/{alert_id}")
        source_resp = client.get(f"/source-ip-context?source_ip={SOURCE_IP}")

    for outcome in (
        alert_resp.get_json()["response_outcome"],
        source_resp.get_json()["response_outcomes"][0],
    ):
        assert outcome["tracking_recorded"] is True
        assert outcome["external_executed"] is False
        label = outcomes.derive_outcome_label(
            execution_mode=outcome["execution_mode"],
            execution_state=outcome["execution_state"],
            external_executed=outcome["external_executed"],
            tracking_recorded=outcome["tracking_recorded"],
            simulated=outcome["simulated"],
        )
        assert label == "Tracking only"
        assert label != "Real executed"
