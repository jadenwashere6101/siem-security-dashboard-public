import uuid
from unittest.mock import patch

import pytest
from psycopg2.extras import Json

from core import soar_response_outcomes as outcomes
from scripts import soar_outcome_backfill


class _ConnWrapper:
    def __init__(self, wrapped):
        self._wrapped = wrapped

    def __getattr__(self, name):
        return getattr(self._wrapped, name)

    def close(self):
        return None


def _run_backfill_cli(conn, args):
    with patch(
        "scripts.soar_outcome_backfill.psycopg2.connect",
        return_value=_ConnWrapper(conn),
    ):
        return soar_outcome_backfill.main([*args, "--db-url", "postgresql://example/db"])


def _insert_alert(cur, source_ip="198.51.100.20", response_action=None):
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message, response_action)
        VALUES ('test_alert', 'LOW', %s::inet, 'msg', %s)
        RETURNING id
        """,
        (source_ip, response_action),
    )
    return cur.fetchone()[0]


def _insert_queue_action(cur, alert_id, *, action="block_ip", status="pending"):
    cur.execute(
        """
        INSERT INTO response_actions_queue (
            idempotency_key, alert_id, source_ip, action, status
        )
        VALUES (%s, %s, '198.51.100.20'::inet, %s, %s)
        RETURNING id
        """,
        (uuid.uuid4().hex, alert_id, action, status),
    )
    return cur.fetchone()[0]


def _count_table(cur, table_name):
    cur.execute(f"SELECT COUNT(*) FROM {table_name}")
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


def _insert_playbook_execution(cur, *, playbook_id="pb_test", steps_log=None):
    _insert_playbook_definition(cur, playbook_id)
    cur.execute(
        """
        INSERT INTO playbook_executions (playbook_id, status, steps_log)
        VALUES (%s, 'success', %s::jsonb)
        RETURNING id
        """,
        (playbook_id, Json(steps_log or [])),
    )
    return cur.fetchone()[0]


@pytest.mark.usefixtures("postgres_db")
def test_plan_backfill_dry_run_produces_summary(postgres_db):
    conn, cur = postgres_db
    alert_observed = _insert_alert(cur)
    alert_selected = _insert_alert(cur, response_action="monitor")
    cur.execute(
        """
        INSERT INTO response_actions_queue (
            idempotency_key, alert_id, source_ip, action, status
        )
        VALUES (%s, %s, %s::inet, 'block_ip', 'pending')
        """,
        (uuid.uuid4().hex, alert_selected, "198.51.100.20"),
    )
    conn.commit()

    before_decisions = _count_table(cur, "soar_response_decisions")
    before_events = _count_table(cur, "soar_response_outcome_events")

    plan = outcomes.plan_backfill_dry_run(conn)
    summary = outcomes.format_backfill_plan_summary(plan)

    after_decisions = _count_table(cur, "soar_response_decisions")
    after_events = _count_table(cur, "soar_response_outcome_events")

    assert before_decisions == after_decisions == 0
    assert before_events == after_events == 0
    assert plan.total_records_scanned >= 2
    assert plan.decisions_by_source["alerts"] >= 1
    assert plan.events_by_source["response_actions_queue"] >= 1
    assert "Dry-run only: no database writes were performed." in summary
    assert "Proposed decisions:" in summary


@pytest.mark.usefixtures("postgres_db")
def test_script_defaults_to_dry_run_without_writes(postgres_db, capsys):
    conn, cur = postgres_db
    _insert_alert(cur, response_action="monitor")
    conn.commit()

    before_decisions = _count_table(cur, "soar_response_decisions")
    before_events = _count_table(cur, "soar_response_outcome_events")

    code = _run_backfill_cli(conn, [])
    output = capsys.readouterr().out

    after_decisions = _count_table(cur, "soar_response_decisions")
    after_events = _count_table(cur, "soar_response_outcome_events")

    assert code == 0
    assert "SOAR outcome backfill dry-run summary" in output
    assert "Dry-run only: no database writes were performed." in output
    assert before_decisions == after_decisions == 0
    assert before_events == after_events == 0


@pytest.mark.usefixtures("postgres_db")
def test_dry_run_script_prints_summary_without_writes(postgres_db, capsys):
    conn, cur = postgres_db
    _insert_alert(cur)
    conn.commit()

    before_decisions = _count_table(cur, "soar_response_decisions")
    before_events = _count_table(cur, "soar_response_outcome_events")

    code = _run_backfill_cli(conn, ["--dry-run"])

    output = capsys.readouterr().out

    after_decisions = _count_table(cur, "soar_response_decisions")
    after_events = _count_table(cur, "soar_response_outcome_events")

    assert code == 0
    assert "SOAR outcome backfill dry-run summary" in output
    assert before_decisions == after_decisions == 0
    assert before_events == after_events == 0


@pytest.mark.usefixtures("postgres_db")
def test_repeated_dry_run_plan_counts_are_stable(postgres_db):
    conn, cur = postgres_db
    _insert_alert(cur, response_action="monitor")
    conn.commit()

    first = outcomes.plan_backfill_dry_run(conn).to_summary_dict()
    second = outcomes.plan_backfill_dry_run(conn).to_summary_dict()

    assert first["proposed_decisions"] == second["proposed_decisions"]
    assert first["proposed_events"] == second["proposed_events"]
    assert first["mode_state_counts"] == second["mode_state_counts"]


@pytest.mark.usefixtures("postgres_db")
def test_dry_run_does_not_double_count_playbook_real_notification(postgres_db):
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

    plan = outcomes.plan_backfill_dry_run(conn)

    assert plan.boolean_counts["external_executed"] == 1
    assert plan.mode_state_counts["real/succeeded"] == 1
    assert plan.events_by_source["playbook_executions"] == 1
    assert plan.events_by_source["notification_delivery_attempts"] == 0


@pytest.mark.usefixtures("postgres_db")
def test_apply_writes_expected_decision_event_and_links_legacy_row(postgres_db, capsys):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, response_action="block_ip")
    queue_id = _insert_queue_action(cur, alert_id, action="block_ip", status="pending")
    conn.commit()

    code = _run_backfill_cli(conn, ["--apply"])
    output = capsys.readouterr().out

    cur.execute(
        """
        SELECT decision_id, soar_correlation_id
        FROM response_actions_queue
        WHERE id = %s
        """,
        (queue_id,),
    )
    decision_id, correlation_id = cur.fetchone()
    cur.execute(
        """
        SELECT execution_mode, execution_state, queue_id, idempotency_key
        FROM soar_response_outcome_events
        WHERE decision_id = %s
        """,
        (decision_id,),
    )
    event = cur.fetchone()

    assert code == 0
    assert "SOAR outcome backfill dry-run summary" in output
    assert "Applying write-mode backfill (--apply requested)." in output
    assert "SOAR outcome backfill apply summary" in output
    assert decision_id is not None
    assert correlation_id
    assert event[0] == "simulation"
    assert event[1] == "queued"
    assert event[2] == queue_id
    assert event[3] == f"legacy-backfill-response_actions_queue-{queue_id}-event-latest"


@pytest.mark.usefixtures("postgres_db")
def test_repeated_apply_is_idempotent(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, response_action="block_ip")
    _insert_queue_action(cur, alert_id, action="block_ip", status="pending")
    conn.commit()

    assert _run_backfill_cli(conn, ["--apply"]) == 0
    first_decisions = _count_table(cur, "soar_response_decisions")
    first_events = _count_table(cur, "soar_response_outcome_events")

    assert _run_backfill_cli(conn, ["--apply"]) == 0
    second_decisions = _count_table(cur, "soar_response_decisions")
    second_events = _count_table(cur, "soar_response_outcome_events")

    assert first_decisions == second_decisions == 1
    assert first_events == second_events == 1


@pytest.mark.usefixtures("postgres_db")
def test_apply_keeps_ambiguous_legacy_records_conservative(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, response_action="notify_slack")
    cur.execute(
        """
        INSERT INTO notification_delivery_attempts (
            correlation_id, idempotency_key, provider, mode, status,
            alert_id, adapter_name, action, metadata
        )
        VALUES (
            %s, %s, 'slack', 'real', 'success',
            %s, 'slack', 'send_message', %s::jsonb
        )
        """,
        (
            "provider-corr-ambiguous",
            f"idem-{uuid.uuid4().hex}",
            alert_id,
            Json({"executed": True, "adapter_mode": "real"}),
        ),
    )
    conn.commit()

    assert _run_backfill_cli(conn, ["--apply"]) == 0

    cur.execute(
        """
        SELECT execution_mode, execution_state, external_executed, simulated, metadata
        FROM soar_response_outcome_events
        WHERE notification_delivery_attempt_id IS NOT NULL
        """
    )
    mode, state, external_executed, simulated, metadata = cur.fetchone()

    assert mode == "simulation"
    assert state == "succeeded"
    assert external_executed is False
    assert simulated is True
    assert metadata["needs_review"] is True
    assert metadata["ambiguous"] is True
    assert metadata["ambiguity_reason"] == "real_delivery_without_executed_metadata"


@pytest.mark.usefixtures("postgres_db")
def test_apply_links_relevant_audit_log_rows_to_canonical_outcome(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    execution_id = _insert_playbook_execution(
        cur,
        steps_log=[{"action": "notify_slack", "status": "success"}],
    )
    cur.execute(
        "UPDATE playbook_executions SET alert_id = %s WHERE id = %s",
        (alert_id, execution_id),
    )
    cur.execute(
        """
        INSERT INTO audit_log (event_type, actor_username, details)
        VALUES ('PLAYBOOK_EXECUTION_ABANDON', 'analyst', %s::jsonb)
        RETURNING id
        """,
        (Json({"execution_id": execution_id}),),
    )
    audit_id = cur.fetchone()[0]
    conn.commit()

    assert _run_backfill_cli(conn, ["--apply"]) == 0

    cur.execute("SELECT details FROM audit_log WHERE id = %s", (audit_id,))
    details = cur.fetchone()[0]
    cur.execute(
        """
        SELECT event_type, playbook_execution_id, metadata
        FROM soar_response_outcome_events
        WHERE id = %s
        """,
        (details["latest_outcome_event_id"],),
    )
    event_type, linked_execution_id, metadata = cur.fetchone()

    assert details["decision_id"]
    assert details["soar_correlation_id"]
    assert event_type == "audit_link"
    assert linked_execution_id == execution_id
    assert metadata["audit_log_id"] == audit_id
    assert metadata["audit_event_type"] == "PLAYBOOK_EXECUTION_ABANDON"
