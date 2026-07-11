import uuid

import pytest
from psycopg2.extras import Json

from core import soar_response_outcomes as outcomes
from core.soar_response_outcomes_legacy import (
    infer_alert_legacy_outcome,
    infer_notification_delivery_legacy_outcome,
    infer_playbook_execution_legacy_outcome,
    infer_queue_legacy_outcome,
    infer_response_log_legacy_outcome,
)


def _insert_alert(cur, source_ip="203.0.113.10", response_action=None):
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message, response_action)
        VALUES ('test_alert', 'LOW', %s::inet, 'msg', %s)
        RETURNING id
        """,
        (source_ip, response_action),
    )
    return cur.fetchone()[0]


def _insert_queue(cur, alert_id, action="block_ip", status="pending", last_error=None):
    cur.execute(
        """
        INSERT INTO response_actions_queue (
            idempotency_key, alert_id, source_ip, action, status, last_error
        )
        VALUES (%s, %s, %s::inet, %s, %s, %s)
        RETURNING id
        """,
        (uuid.uuid4().hex, alert_id, "203.0.113.10", action, status, last_error),
    )
    return cur.fetchone()[0]


def _insert_log(cur, alert_id, action, status, details):
    cur.execute(
        """
        INSERT INTO response_actions_log (alert_id, source_ip, action, status, details)
        VALUES (%s, %s::inet, %s, %s, %s)
        RETURNING id
        """,
        (alert_id, "203.0.113.10", action, status, details),
    )
    return cur.fetchone()[0]


def _insert_approval(cur, queue_id, action="block_ip", status="pending"):
    decided_at = "NOW()" if status != "pending" else "NULL"
    cur.execute(
        f"""
        INSERT INTO approval_requests (
            queue_id, action, status, expires_at, decided_at
        )
        VALUES (%s, %s, %s, NOW() + INTERVAL '1 hour', {decided_at})
        RETURNING id
        """,
        (queue_id, action, status),
    )
    return cur.fetchone()[0]


def _insert_incident(cur, source_ip="203.0.113.10"):
    cur.execute(
        """
        INSERT INTO incidents (title, severity, source_ip)
        VALUES ('incident', 'MEDIUM', %s::inet)
        RETURNING id
        """,
        (source_ip,),
    )
    return cur.fetchone()[0]


def _insert_incident_approval(cur, incident_id, action="block_ip", status="denied"):
    decided_at = "NOW()" if status != "pending" else "NULL"
    cur.execute(
        f"""
        INSERT INTO approval_requests (
            incident_id, action, status, expires_at, decided_at, request_reason
        )
        VALUES (%s, %s, %s, NOW() + INTERVAL '1 hour', {decided_at}, 'approval required')
        RETURNING id
        """,
        (incident_id, action, status),
    )
    return cur.fetchone()[0]


def _insert_playbook_definition(cur, playbook_id="pb_test"):
    cur.execute(
        """
        INSERT INTO playbook_definitions (id, name, steps)
        VALUES (%s, 'Test Playbook', '[]'::jsonb)
        ON CONFLICT (id) DO NOTHING
        """,
        (playbook_id,),
    )
    return playbook_id


def _insert_playbook_execution(cur, *, playbook_id="pb_test", status="success", steps_log=None):
    _insert_playbook_definition(cur, playbook_id)
    cur.execute(
        """
        INSERT INTO playbook_executions (playbook_id, status, steps_log)
        VALUES (%s, %s, %s::jsonb)
        RETURNING id
        """,
        (playbook_id, status, Json(steps_log or [])),
    )
    return cur.fetchone()[0]


def _count_table(cur, table_name):
    cur.execute(f"SELECT COUNT(*) FROM {table_name}")
    return cur.fetchone()[0]


@pytest.mark.usefixtures("postgres_db")
def test_resolve_observed_only_alert(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()

    read_model = outcomes.resolve_alert_outcome(conn, alert_id)
    assert read_model["inferred"] is True
    assert read_model["execution_mode"] == "observed"
    assert read_model["execution_state"] == "observed"
    assert read_model["outcome_label"] == "Observed only"
    assert read_model["external_executed"] is False


@pytest.mark.usefixtures("postgres_db")
def test_resolve_selected_alert_with_response_action_only(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, response_action="monitor")
    conn.commit()

    read_model = outcomes.resolve_alert_outcome(conn, alert_id)
    assert read_model["execution_state"] == "selected"
    assert read_model["selected_action"] == "monitor"
    assert read_model["ambiguous"] is True
    assert read_model["needs_review"] is True


@pytest.mark.usefixtures("postgres_db")
def test_resolve_alert_direct_blocked_notification_takes_precedence(postgres_db):
    conn, cur = postgres_db
    from core import notification_delivery_store

    alert_id = _insert_alert(cur, response_action="notify")
    row = notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="provider-corr-alert-blocked",
        idempotency_key=f"idem-{uuid.uuid4().hex}",
        provider="slack",
        mode="simulation",
        status="blocked",
        adapter_name="slack",
        action="send_message",
        alert_id=alert_id,
        metadata={"simulation": True},
        failure_code="simulation_blocked",
        failure_message="simulated policy block only",
    )
    conn.commit()

    read_model = outcomes.resolve_alert_outcome(conn, alert_id)
    assert read_model["source_table"] == "alerts"
    assert read_model["execution_mode"] == "simulation"
    assert read_model["execution_state"] == "blocked"
    assert read_model["outcome_label"] == "Blocked"
    assert read_model["related"]["notification_delivery_attempt_id"] == row["id"]
    assert read_model["ambiguous"] is False
    assert read_model["needs_review"] is False


@pytest.mark.usefixtures("postgres_db")
def test_resolve_alert_notification_linked_denied_approval_is_blocked(postgres_db):
    conn, cur = postgres_db
    from core import notification_delivery_store

    alert_id = _insert_alert(cur, response_action="notify")
    incident_id = _insert_incident(cur)
    approval_id = _insert_incident_approval(cur, incident_id, status="denied")
    notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="provider-corr-alert-denied",
        idempotency_key=f"idem-{uuid.uuid4().hex}",
        provider="slack",
        mode="simulation",
        status="blocked",
        adapter_name="slack",
        action="send_message",
        alert_id=alert_id,
        incident_id=incident_id,
        approval_request_id=approval_id,
        metadata={"simulation": True},
        failure_message="simulated policy block only",
    )
    conn.commit()

    read_model = outcomes.resolve_alert_outcome(conn, alert_id)
    assert read_model["execution_state"] == "blocked"
    assert read_model["reason_code"] == "approval_denied"
    assert read_model["related"]["incident_id"] == incident_id
    assert read_model["related"]["approval_request_id"] == approval_id
    assert read_model["ambiguous"] is False


@pytest.mark.usefixtures("postgres_db")
def test_resolve_queued_queue_row(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, response_action="block_ip")
    queue_id = _insert_queue(cur, alert_id, status="pending")
    conn.commit()

    read_model = outcomes.resolve_queue_outcome(conn, queue_id)
    assert read_model["execution_state"] == "queued"
    assert read_model["outcome_label"] == "Queued"
    assert read_model["external_executed"] is False


@pytest.mark.usefixtures("postgres_db")
def test_resolve_awaiting_approval_queue_row(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, response_action="block_ip")
    queue_id = _insert_queue(cur, alert_id, status="awaiting_approval")
    conn.commit()

    read_model = outcomes.resolve_queue_outcome(conn, queue_id)
    assert read_model["execution_state"] == "awaiting_approval"
    assert read_model["outcome_label"] == "Awaiting approval"
    assert read_model["reason_code"] == "approval_required"


@pytest.mark.usefixtures("postgres_db")
def test_resolve_approval_denied_as_blocked(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, response_action="block_ip")
    queue_id = _insert_queue(cur, alert_id, status="awaiting_approval")
    approval_id = _insert_approval(cur, queue_id, status="denied")
    conn.commit()

    read_model = outcomes.resolve_approval_request_outcome(conn, approval_id)
    assert read_model["execution_state"] == "blocked"
    assert read_model["outcome_label"] == "Blocked"
    assert read_model["reason_code"] == "approval_denied"
    assert read_model["external_executed"] is False


@pytest.mark.usefixtures("postgres_db")
def test_resolve_approval_expired_as_blocked_distinct_reason(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, response_action="block_ip")
    queue_id = _insert_queue(cur, alert_id, status="awaiting_approval")
    approval_id = _insert_approval(cur, queue_id, status="expired")
    conn.commit()

    read_model = outcomes.resolve_approval_request_outcome(conn, approval_id)
    assert read_model["execution_state"] == "blocked"
    assert read_model["outcome_label"] == "Blocked"
    assert read_model["reason_code"] == "approval_expired"
    assert read_model["external_executed"] is False
    assert read_model["simulated"] is False
    assert read_model["tracking_recorded"] is False


@pytest.mark.usefixtures("postgres_db")
def test_resolve_tracking_only_response_log(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, response_action="block_ip")
    log_id = _insert_log(
        cur,
        alert_id,
        "block_ip",
        "executed",
        "Recorded in SIEM blocklist (tracking only)",
    )
    conn.commit()

    read_model = outcomes.resolve_response_log_outcome(conn, log_id)
    assert read_model["execution_mode"] == "tracking_only"
    assert read_model["tracking_recorded"] is True
    assert read_model["external_executed"] is False
    assert read_model["outcome_label"] == "Tracking only"


@pytest.mark.usefixtures("postgres_db")
def test_resolve_simulated_queue_success(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, response_action="monitor")
    queue_id = _insert_queue(cur, alert_id, action="monitor", status="success")
    conn.commit()

    read_model = outcomes.resolve_queue_outcome(conn, queue_id)
    assert read_model["execution_mode"] == "simulation"
    assert read_model["execution_state"] == "succeeded"
    assert read_model["simulated"] is True
    assert read_model["external_executed"] is False
    assert read_model["outcome_label"] == "Simulated"


@pytest.mark.usefixtures("postgres_db")
def test_resolve_simulation_notification_delivery(postgres_db):
    conn, cur = postgres_db
    from core import notification_delivery_store

    row = notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="provider-corr-1",
        idempotency_key=f"idem-{uuid.uuid4().hex}",
        provider="slack",
        mode="simulation",
        status="success",
        adapter_name="slack",
        action="send_message",
        metadata={"executed": False},
    )
    conn.commit()

    read_model = outcomes.resolve_notification_delivery_outcome(conn, row["id"])
    assert read_model["execution_mode"] == "simulation"
    assert read_model["simulated"] is True
    assert read_model["external_executed"] is False


@pytest.mark.usefixtures("postgres_db")
def test_resolve_real_notification_success_requires_executed_metadata(postgres_db):
    conn, cur = postgres_db
    from core import notification_delivery_store

    row = notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="provider-corr-2",
        idempotency_key=f"idem-{uuid.uuid4().hex}",
        provider="slack",
        mode="real",
        status="success",
        adapter_name="slack",
        action="send_message",
        metadata={"executed": True, "simulated": False, "adapter_mode": "real"},
    )
    conn.commit()

    read_model = outcomes.resolve_notification_delivery_outcome(conn, row["id"])
    assert read_model["execution_mode"] == "real"
    assert read_model["external_executed"] is True
    assert read_model["outcome_label"] == "Real executed"


@pytest.mark.usefixtures("postgres_db")
def test_ambiguous_real_notification_without_executed_metadata_is_not_real(postgres_db):
    conn, cur = postgres_db
    from core import notification_delivery_store

    row = notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="provider-corr-3",
        idempotency_key=f"idem-{uuid.uuid4().hex}",
        provider="slack",
        mode="real",
        status="success",
        adapter_name="slack",
        action="send_message",
        metadata={},
    )
    conn.commit()

    read_model = outcomes.resolve_notification_delivery_outcome(conn, row["id"])
    assert read_model["execution_mode"] == "simulation"
    assert read_model["external_executed"] is False
    assert read_model["ambiguous"] is True
    assert read_model["needs_review"] is True


@pytest.mark.usefixtures("postgres_db")
def test_real_notification_success_requires_simulated_false(postgres_db):
    conn, cur = postgres_db
    from core import notification_delivery_store

    row = notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="provider-corr-sim-missing",
        idempotency_key=f"idem-{uuid.uuid4().hex}",
        provider="slack",
        mode="real",
        status="success",
        adapter_name="slack",
        action="send_message",
        metadata={"executed": True, "adapter_mode": "real"},
    )
    conn.commit()

    read_model = outcomes.resolve_notification_delivery_outcome(conn, row["id"])
    assert read_model["execution_mode"] == "simulation"
    assert read_model["external_executed"] is False
    assert read_model["ambiguous"] is True
    assert read_model["needs_review"] is True


def test_playbook_nested_adapter_execution_alone_is_not_real():
    mapping = infer_playbook_execution_legacy_outcome(
        execution_id=1,
        alert_id=None,
        incident_id=None,
        playbook_id="pb",
        status="success",
        failure_reason=None,
        steps_log=[
            {
                "action": "notify_slack",
                "mode": "simulation",
                "simulated": True,
                "executed": False,
                "output": {
                    "simulated": True,
                    "executed": False,
                    "adapter_result": {
                        "mode": "real",
                        "success": True,
                        "executed": True,
                        "simulated": False,
                    },
                },
            }
        ],
    )

    assert mapping.execution_mode == "simulation"
    assert mapping.execution_state == "succeeded"
    assert mapping.external_executed is False
    assert mapping.ambiguous is True
    assert mapping.needs_review is True
    assert (
        mapping.ambiguity_reason
        == "playbook_real_execution_without_notification_corroboration"
    )


@pytest.mark.usefixtures("postgres_db")
def test_playbook_real_execution_requires_notification_corroboration(postgres_db):
    conn, cur = postgres_db
    from core import notification_delivery_store

    execution_id = _insert_playbook_execution(
        cur,
        steps_log=[
            {
                "action": "notify_slack",
                "output": {
                    "adapter_result": {
                        "mode": "real",
                        "success": True,
                        "executed": True,
                        "simulated": False,
                    }
                },
            }
        ],
    )
    notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="provider-corr-playbook-real",
        idempotency_key=f"idem-{uuid.uuid4().hex}",
        provider="slack",
        mode="real",
        status="success",
        adapter_name="slack",
        action="send_message",
        playbook_execution_id=execution_id,
        playbook_step_index=0,
        metadata={
            "executed": True,
            "simulated": False,
            "adapter_mode": "real",
            "delivery": "sent",
        },
    )
    conn.commit()

    read_model = outcomes.resolve_playbook_execution_outcome(conn, execution_id)
    assert read_model["execution_mode"] == "real"
    assert read_model["execution_state"] == "succeeded"
    assert read_model["external_executed"] is True
    assert read_model["outcome_label"] == "Real executed"
    assert read_model["ambiguous"] is False


@pytest.mark.usefixtures("postgres_db")
def test_resolve_failed_queue_row(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, response_action="block_ip")
    queue_id = _insert_queue(
        cur, alert_id, status="failed", last_error="executor timeout"
    )
    conn.commit()

    read_model = outcomes.resolve_queue_outcome(conn, queue_id)
    assert read_model["execution_state"] == "failed"
    assert read_model["outcome_label"] == "Failed"
    assert read_model["external_executed"] is False


@pytest.mark.usefixtures("postgres_db")
def test_canonical_decision_takes_precedence_over_legacy_inference(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, response_action="monitor")
    conn.commit()

    decision = outcomes.create_response_decision(
        conn,
        alert_id=alert_id,
        selected_action="monitor",
        decision_source="manual",
        outcome_summary="Canonical decision exists.",
    )
    outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        execution_mode="simulation",
        execution_state="succeeded",
        simulated=True,
        execution_actor="manual",
        outcome_summary="Canonical simulated outcome.",
    )
    conn.commit()

    read_model = outcomes.resolve_alert_outcome(conn, alert_id)
    assert read_model["inferred"] is False
    assert read_model["decision_id"] == decision["id"]
    assert read_model["outcome_label"] == "Simulated"


def test_legacy_idempotency_keys_are_stable():
    first = infer_queue_legacy_outcome(
        queue_id=42,
        alert_id=7,
        source_ip="203.0.113.1",
        action="monitor",
        status="pending",
        last_error=None,
    ).to_read_model()
    second = infer_queue_legacy_outcome(
        queue_id=42,
        alert_id=7,
        source_ip="203.0.113.1",
        action="monitor",
        status="pending",
        last_error=None,
    ).to_read_model()
    assert first["proposed_idempotency_keys"] == second["proposed_idempotency_keys"]


def test_infer_helpers_map_examples():
    observed = infer_alert_legacy_outcome(
        alert_id=1,
        source_ip="1.1.1.1",
        response_action=None,
        has_queue=False,
        has_log=False,
    )
    assert observed.execution_mode == "observed"

    simulated_notification = infer_notification_delivery_legacy_outcome(
        attempt_id=1,
        alert_id=None,
        incident_id=None,
        playbook_execution_id=None,
        approval_request_id=None,
        action="send_message",
        mode="simulation",
        status="success",
        metadata={"executed": False},
        failure_message=None,
    )
    assert simulated_notification.simulated is True
    assert simulated_notification.external_executed is False

    tracking_log = infer_response_log_legacy_outcome(
        log_id=1,
        alert_id=1,
        source_ip="1.1.1.1",
        action="block_ip",
        status="executed",
        details="Recorded in SIEM blocklist (tracking only)",
        blocked_ip_exists=True,
    )
    assert tracking_log.tracking_recorded is True
    assert tracking_log.external_executed is False
