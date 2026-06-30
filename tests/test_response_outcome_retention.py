"""Retention, archive, reporting, and performance verification (Phase 10)."""

from __future__ import annotations

import time
import uuid

import pytest

from core import soar_response_outcomes as outcomes
from response_outcome_test_helpers import patched_route_db


def _insert_alert(cur, source_ip="203.0.113.44"):
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message)
        VALUES ('test_alert', 'LOW', %s::inet, 'retention test')
        RETURNING id
        """,
        (source_ip,),
    )
    return cur.fetchone()[0]


def _insert_incident(cur, source_ip="203.0.113.44"):
    cur.execute(
        """
        INSERT INTO incidents (title, severity, priority, status, source_ip)
        VALUES ('Retention incident', 'high', 'P2', 'open', %s::inet)
        RETURNING id
        """,
        (source_ip,),
    )
    return cur.fetchone()[0]


def _seed_decision_with_event(conn, *, alert_id=None, incident_id=None, suffix=None):
    suffix = suffix or uuid.uuid4().hex[:8]
    decision = outcomes.create_response_decision(
        conn,
        alert_id=alert_id,
        incident_id=incident_id,
        selected_action="monitor",
        decision_source="manual",
        outcome_summary=f"Retention seed decision {suffix}.",
        soar_correlation_id=f"soar-ret-{suffix}",
    )
    event = outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        execution_mode="simulation",
        execution_state="succeeded",
        simulated=True,
        execution_actor="manual",
        outcome_summary=f"Retention seed event {suffix}.",
        alert_id=alert_id,
        incident_id=incident_id,
    )
    return decision, event


def test_retention_policy_documents_indefinite_live_window_by_default():
    policy = outcomes.get_canonical_outcome_retention_policy()

    assert policy["live_retention_days"] is None
    assert policy["live_retention_policy"] == "indefinite_by_default"
    assert "external_executed = true" in policy["archive_strategy"] or "Real-execution" in policy["archive_strategy"]
    assert set(policy["archive_preserved_fields"]) == set(outcomes.ARCHIVE_PRESERVED_FIELDS)
    assert outcomes.PRIMARY_ANALYST_QUESTION in policy["primary_analyst_question"]


def test_retention_policy_reads_positive_env_window(monkeypatch):
    monkeypatch.setenv("SIEM_OUTCOME_RETENTION_DAYS", "365")

    policy = outcomes.get_canonical_outcome_retention_policy()

    assert policy["live_retention_days"] == 365
    assert policy["live_retention_policy"] == "365_day_live_window"


@pytest.mark.parametrize("raw_value", ["", "0", "-1", "not-a-number"])
def test_retention_policy_ignores_invalid_env_window(monkeypatch, raw_value):
    monkeypatch.setenv("SIEM_OUTCOME_RETENTION_DAYS", raw_value)

    policy = outcomes.get_canonical_outcome_retention_policy()

    assert policy["live_retention_days"] is None
    assert policy["live_retention_policy"] == "indefinite_by_default"


def test_archive_record_preserves_required_fields(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    decision, event = _seed_decision_with_event(conn, alert_id=alert_id)
    conn.commit()

    archive = outcomes.build_archive_record(decision, event)

    for field in outcomes.ARCHIVE_PRESERVED_FIELDS:
        assert field in archive
    assert archive["decision_id"] == decision["id"]
    assert archive["soar_correlation_id"] == decision["soar_correlation_id"]
    assert archive["selected_action"] == "monitor"
    assert archive["execution_mode"] == "simulation"
    assert archive["external_executed"] is False


def test_traceability_report_by_alert_id(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    decision, _event = _seed_decision_with_event(conn, alert_id=alert_id)
    conn.commit()

    report = outcomes.get_response_outcome_traceability_report(conn, alert_id=alert_id)

    assert len(report) == 1
    entry = report[0]
    assert entry["analyst_question"] == outcomes.PRIMARY_ANALYST_QUESTION
    assert entry["selected_response"] == "monitor"
    assert entry["decision_source"] == "manual"
    assert entry["playbook_ran"] is False
    assert entry["anything_actually_executed"] is False
    assert entry["latest_outcome"]["decision_id"] == decision["id"]
    assert entry["archive_record"]["alert_id"] == alert_id


def test_traceability_report_by_incident_id(postgres_db):
    conn, cur = postgres_db
    incident_id = _insert_incident(cur)
    decision, _event = _seed_decision_with_event(conn, incident_id=incident_id)
    conn.commit()

    report = outcomes.get_response_outcome_traceability_report(conn, incident_id=incident_id)

    assert len(report) == 1
    assert report[0]["latest_outcome"]["related"]["incident_id"] == incident_id
    assert report[0]["archive_record"]["incident_id"] == incident_id
    assert report[0]["decision_source"] == "manual"


def test_traceability_report_supports_migration_decision_source(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    suffix = uuid.uuid4().hex[:8]
    decision = outcomes.create_response_decision(
        conn,
        alert_id=alert_id,
        selected_action="block_ip",
        decision_source="migration",
        outcome_summary="Inferred from legacy response log.",
        soar_correlation_id=f"legacy-response_actions_log-{suffix}",
    )
    outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        execution_mode="tracking_only",
        execution_state="succeeded",
        tracking_recorded=True,
        execution_actor="system",
        outcome_summary="Legacy tracking-only block recorded.",
        alert_id=alert_id,
        reason_code="tracking_only",
    )
    conn.commit()

    report = outcomes.get_response_outcome_traceability_report(conn, alert_id=alert_id)

    assert report[0]["decision_source"] == "migration"
    assert report[0]["latest_outcome"]["execution_mode"] == "tracking_only"
    assert report[0]["anything_actually_executed"] is False


def _seed_performance_volume(conn, *, decisions=10_000, events_per_decision=5):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO soar_response_decisions (
                soar_correlation_id, selected_action, decision_source, outcome_summary
            )
            SELECT
                'soar-perf-' || g::text,
                'monitor',
                'manual',
                'Performance seed decision'
            FROM generate_series(1, %s) AS g
            RETURNING id
            """,
            (decisions,),
        )
        decision_ids = [row[0] for row in cur.fetchall()]

        event_rows = []
        for decision_id in decision_ids:
            for step in range(events_per_decision):
                event_rows.append(
                    (
                        decision_id,
                        f"soar-perf-{decision_id}",
                        "outcome_recorded",
                        "simulation",
                        "succeeded",
                        False,
                        False,
                        True,
                        "queue_worker",
                        f"Performance seed event step {step}",
                    )
                )

        cur.executemany(
            """
            INSERT INTO soar_response_outcome_events (
                decision_id,
                soar_correlation_id,
                event_type,
                execution_mode,
                execution_state,
                external_executed,
                tracking_recorded,
                simulated,
                execution_actor,
                outcome_summary
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            event_rows,
        )
    conn.commit()
    return decision_ids


@pytest.mark.slow
def test_latest_outcome_queries_meet_performance_targets(postgres_db):
    conn, _cur = postgres_db
    decision_ids = _seed_performance_volume(conn)
    sample_decision_id = decision_ids[0]
    alert_ids = list(range(1, 101))
    approval_ids = list(range(1, 51))

    start = time.perf_counter()
    latest = outcomes.get_latest_outcome_for_decision(conn, sample_decision_id)
    decision_elapsed_ms = (time.perf_counter() - start) * 1000
    assert latest is not None
    assert decision_elapsed_ms < 50, f"decision lookup took {decision_elapsed_ms:.2f}ms"

    start = time.perf_counter()
    outcomes.get_latest_outcomes_for_alerts_bulk(conn, alert_ids)
    alerts_elapsed_ms = (time.perf_counter() - start) * 1000
    assert alerts_elapsed_ms < 200, f"alerts bulk lookup took {alerts_elapsed_ms:.2f}ms"

    start = time.perf_counter()
    outcomes.get_latest_outcomes_for_approvals_bulk(conn, approval_ids)
    approvals_elapsed_ms = (time.perf_counter() - start) * 1000
    assert approvals_elapsed_ms < 200, f"approvals bulk lookup took {approvals_elapsed_ms:.2f}ms"


def test_metrics_endpoints_document_live_retention_window(client, postgres_db):
    conn, _cur = postgres_db
    login = client.post(
        "/login",
        json={"username": "testadmin", "password": "testpassword123!"},
    )
    assert login.status_code == 200

    for path in (
        "/metrics/playbooks",
        "/metrics/notifications",
        "/metrics/incidents",
        "/metrics/approvals",
    ):
        with patched_route_db(conn, "routes.metrics_routes"):
            resp = client.get(path)
        assert resp.status_code == 200
        retention = resp.get_json()["canonical_outcome_retention"]
        assert retention["live_retention_policy"] == "indefinite_by_default"
        assert "canonical_outcome_counts" in resp.get_json()
        assert "currently stored in soar_response_outcome_events" in retention["metrics_scope"]
