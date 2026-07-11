"""Regression: canonical outcome modes match actual action behavior."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

from core.response_command_contracts import ORIGIN_MANUAL_ALERT, ResponseCommandRequest
from core.response_command_service import execute_response_command
from engines import playbook_step_executor
from engines.soar_action_worker import (
    _queue_outcome_classification,
    process_next_action,
)
from engines.soar_executor import SimulationExecutor


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
    with patch("routes.alert_mutation_routes.get_db_connection", return_value=wrapper), patch(
        "core.audit_helpers.get_db_connection", return_value=wrapper
    ):
        yield


def _insert_alert(cur, *, source_ip="198.51.100.77"):
    cur.execute(
        """
        INSERT INTO alerts (
            alert_type, severity, source_ip, source, source_type, message, status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        ("failed_login_threshold", "high", source_ip, "bank_app", "custom", "mode regression", "open"),
    )
    return cur.fetchone()[0]


def _latest_outcome(cur, alert_id):
    cur.execute(
        """
        SELECT e.execution_mode, e.execution_state, e.simulated,
               e.external_executed, e.tracking_recorded, e.reason_code,
               d.selected_action
        FROM soar_response_outcome_events e
        JOIN soar_response_decisions d ON d.id = e.decision_id
        WHERE e.alert_id = %s
        ORDER BY e.id DESC
        LIMIT 1
        """,
        (alert_id,),
    )
    return cur.fetchone()


def test_monitor_command_writes_internal_mode(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()

    result = execute_response_command(
        conn,
        ResponseCommandRequest(
            action="monitor",
            indicator_value="198.51.100.77",
            alert_id=alert_id,
            origin_surface=ORIGIN_MANUAL_ALERT,
            idempotency_key="mode-monitor-1",
        ),
    )
    conn.commit()

    assert result.success is True
    mode, state, simulated, external, tracking, reason, action = _latest_outcome(cur, alert_id)
    assert (action, mode, state, simulated, external, tracking, reason) == (
        "monitor",
        "internal",
        "succeeded",
        False,
        False,
        False,
        None,
    )


def test_escalate_command_writes_internal_mode(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, source_ip="198.51.100.78")
    conn.commit()

    result = execute_response_command(
        conn,
        ResponseCommandRequest(
            action="flag_high_priority",
            indicator_value="198.51.100.78",
            alert_id=alert_id,
            origin_surface=ORIGIN_MANUAL_ALERT,
            idempotency_key="mode-escalate-1",
        ),
    )
    conn.commit()

    assert result.success is True
    mode, state, simulated, external, tracking, reason, action = _latest_outcome(cur, alert_id)
    assert action == "flag_high_priority"
    assert mode == "internal"
    assert state == "succeeded"
    assert simulated is False
    assert external is False
    assert tracking is False


def test_block_ip_command_writes_tracking_only_not_enforcement(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, source_ip="8.8.8.8")
    conn.commit()

    result = execute_response_command(
        conn,
        ResponseCommandRequest(
            action="block_ip",
            indicator_value="8.8.8.8",
            alert_id=alert_id,
            origin_surface=ORIGIN_MANUAL_ALERT,
            idempotency_key="mode-block-1",
        ),
    )
    conn.commit()

    assert result.success is True
    assert result.enforcement == "none"
    mode, state, simulated, external, tracking, reason, action = _latest_outcome(cur, alert_id)
    assert (action, mode, state, simulated, external, tracking, reason) == (
        "block_ip",
        "tracking_only",
        "succeeded",
        False,
        False,
        True,
        "tracking_only",
    )


def test_queue_classification_is_action_aware():
    assert _queue_outcome_classification(
        "monitor", execution_state="succeeded"
    )["execution_mode"] == "internal"
    assert _queue_outcome_classification(
        "flag_high_priority", execution_state="succeeded"
    )["execution_mode"] == "internal"
    block = _queue_outcome_classification("block_ip", execution_state="succeeded")
    assert block["execution_mode"] == "tracking_only"
    assert block["tracking_recorded"] is True
    assert block["simulated"] is False
    simulated = _queue_outcome_classification(
        "unknown_custom", execution_state="succeeded"
    )
    assert simulated["execution_mode"] == "simulation"
    assert simulated["simulated"] is True


def test_queue_monitor_latest_event_is_internal(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, source_ip="198.51.100.79")
    cur.execute(
        """
        INSERT INTO response_actions_queue (
            alert_id, source_ip, action, status, retry_count, max_retries, idempotency_key
        )
        VALUES (%s, %s::inet, 'monitor', 'pending', 0, 3, %s)
        RETURNING id
        """,
        (alert_id, "198.51.100.79", "mode-queue-monitor-1"),
    )
    queue_id = cur.fetchone()[0]
    cur.execute(
        """
        INSERT INTO soar_response_decisions (
            soar_correlation_id, alert_id, source_ip, selected_action, decision_source,
            outcome_summary
        )
        VALUES (%s, %s, %s::inet, 'monitor', 'manual', 'queue monitor')
        RETURNING id
        """,
        (f"soar-mode-queue-{queue_id}", alert_id, "198.51.100.79"),
    )
    decision_id = cur.fetchone()[0]
    cur.execute(
        """
        UPDATE response_actions_queue
        SET decision_id = %s, soar_correlation_id = %s
        WHERE id = %s
        """,
        (decision_id, f"soar-mode-queue-{queue_id}", queue_id),
    )
    conn.commit()

    result = process_next_action(conn, executor=SimulationExecutor())
    assert result["outcome"] == "success"
    cur.execute(
        """
        SELECT execution_mode, execution_state, simulated, reason_code
        FROM soar_response_outcome_events
        WHERE queue_id = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (queue_id,),
    )
    mode, state, simulated, reason = cur.fetchone()
    assert (mode, state, simulated, reason) == ("internal", "succeeded", False, None)


def test_playbook_step_classifier_maps_internal_and_read_only():
    internal = playbook_step_executor._playbook_step_outcome_classification(
        {"action": "branch", "status": "success", "mode": "internal"}
    )
    assert internal["execution_mode"] == "internal"
    assert internal["simulated"] is False

    enrich = playbook_step_executor._playbook_step_outcome_classification(
        {"action": "enrich_context", "status": "success", "mode": "read_only"}
    )
    assert enrich["execution_mode"] == "read_only"
    assert enrich["simulated"] is False

    unsupported = playbook_step_executor._playbook_step_outcome_classification(
        {
            "action": "bad_action",
            "status": "failed",
            "error": {"code": "unsupported_action"},
        }
    )
    assert unsupported["execution_mode"] == "internal"
    assert unsupported["reason_code"] == "unsupported_action"
    assert unsupported["simulated"] is False


def test_teams_notification_outcome_forced_to_simulation():
    mapped = playbook_step_executor._map_notification_delivery_outcome(
        {
            "mode": "real",
            "status": "success",
            "provider": "teams",
            "action": "notify_teams",
            "metadata": {
                "executed": True,
                "simulated": False,
                "adapter_mode": "real",
                "provider_success": True,
            },
        }
    )
    assert mapped["execution_mode"] == "simulation"
    assert mapped["external_executed"] is False
    assert mapped["simulated"] is True


def test_slack_real_evidence_remains_real():
    mapped = playbook_step_executor._map_notification_delivery_outcome(
        {
            "mode": "real",
            "status": "success",
            "provider": "slack",
            "action": "notify_slack",
            "metadata": {
                "executed": True,
                "simulated": False,
                "adapter_mode": "real",
                "provider_success": True,
            },
        }
    )
    assert mapped["execution_mode"] == "real"
    assert mapped["external_executed"] is True
    assert mapped["simulated"] is False
