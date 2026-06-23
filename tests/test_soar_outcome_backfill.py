import uuid
from unittest.mock import patch

import pytest
from psycopg2.extras import Json

from core import soar_response_outcomes as outcomes
from scripts import soar_outcome_backfill


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
def test_dry_run_script_requires_dry_run_flag(capsys):
    code = soar_outcome_backfill.main([])
    assert code == 2
    assert "only --dry-run is supported" in capsys.readouterr().err


@pytest.mark.usefixtures("postgres_db")
def test_dry_run_script_prints_summary_without_writes(postgres_db, capsys):
    conn, cur = postgres_db
    _insert_alert(cur)
    conn.commit()

    before_decisions = _count_table(cur, "soar_response_decisions")
    before_events = _count_table(cur, "soar_response_outcome_events")

    class _ConnWrapper:
        def __init__(self, wrapped):
            self._wrapped = wrapped

        def __getattr__(self, name):
            return getattr(self._wrapped, name)

        def close(self):
            return None

    with patch(
        "scripts.soar_outcome_backfill.psycopg2.connect",
        return_value=_ConnWrapper(conn),
    ):
        code = soar_outcome_backfill.main(["--dry-run", "--db-url", "postgresql://example/db"])

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
