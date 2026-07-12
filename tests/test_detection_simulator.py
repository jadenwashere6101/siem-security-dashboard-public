from __future__ import annotations

import json
import os
from unittest.mock import patch

import psycopg2
from psycopg2 import sql
import pytest
from werkzeug.security import generate_password_hash

import siem_backend
from engines.detection_simulator import SimulationValidationError, run_detection_simulation


def run_sim(**kwargs):
    # Detector functions call current_app.logger, so any call that can reach
    # a matching row (i.e. that isn't stopped by request validation, parsing,
    # or applicability) needs a pushed Flask app context, exactly like
    # tests/test_ingest_normalized_event.py's direct engine-layer calls.
    with siem_backend.app.app_context():
        return run_detection_simulation(**kwargs)


ADMIN_USER = "testadmin"
ADMIN_PASS = "testpassword123!"

SIMULATED_REPUTATION = {
    "reputation_score": 0,
    "reputation_label": "unknown",
    "reputation_source": "simulated",
    "reputation_summary": "Reputation lookup stubbed during simulation; no live third-party API call was made.",
}


class RollbackOnlyConnection:
    """Route-safe wrapper for a real postgres_db fixture connection.

    cursor()/rollback() pass through to the real connection; close() is a
    no-op so the fixture can still tear down its schema afterward.

    commit() is deliberately NOT implemented. If code under test ever calls
    conn.commit(), this raises AttributeError immediately instead of
    silently committing into the shared per-test schema -- the
    zero-durable-write guarantee, made into an executable test assertion.
    """

    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return self._conn.cursor()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return None


def role_user(role):
    return {
        "username": f"detection_simulator_{role}",
        "password_hash": generate_password_hash("rolepass", method="pbkdf2:sha256"),
        "role": role,
        "is_active": True,
    }


def logged_in_role(client, role):
    from contextlib import contextmanager

    @contextmanager
    def _cm():
        user = role_user(role)
        with patch("routes.auth_routes.get_user_by_username", return_value=user), patch(
            "core.auth.get_user_by_username", return_value=user
        ), patch("core.audit_helpers.get_db_connection"):
            response = client.post("/login", json={"username": user["username"], "password": "rolepass"})
            assert response.status_code == 200
            yield

    return _cm()


def login_super_admin(client):
    response = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert response.status_code == 200


def count_rows(cur, table_name):
    cur.execute(f"SELECT COUNT(*) FROM {table_name}")
    return cur.fetchone()[0]


def insert_playbook(cur, playbook_id, *, trigger_config, steps):
    cur.execute(
        """
        INSERT INTO playbook_definitions (id, name, description, trigger_config, steps, enabled)
        VALUES (%s, %s, '', %s, %s, TRUE)
        ON CONFLICT (id) DO NOTHING
        """,
        (playbook_id, f"Test playbook {playbook_id}", json.dumps(trigger_config), json.dumps(steps)),
    )


# --- request-shape validation (no DB) ---------------------------------------


def test_unknown_source_is_rejected():
    with pytest.raises(SimulationValidationError, match="Unknown source"):
        run_detection_simulation(
            source="not_a_real_source",
            rule_id="failed_login_threshold",
            input_format="json",
            json_events=[{"event_type": "failed_login"}],
        )


def test_unknown_rule_id_is_rejected():
    with pytest.raises(SimulationValidationError, match="Unknown rule_id"):
        run_detection_simulation(
            source="bank_app",
            rule_id="not_a_real_rule",
            input_format="json",
            json_events=[{"event_type": "failed_login"}],
        )


def test_unsupported_input_format_for_source_is_rejected():
    # nginx only supports raw input; json is not supported.
    with pytest.raises(SimulationValidationError, match="does not support input_format"):
        run_detection_simulation(
            source="nginx",
            rule_id="http_error_threshold",
            input_format="json",
            json_events=[{"foo": "bar"}],
        )


def test_empty_raw_lines_is_rejected():
    with pytest.raises(SimulationValidationError, match="raw_lines must contain"):
        run_detection_simulation(
            source="nginx",
            rule_id="http_error_threshold",
            input_format="raw",
            raw_lines=["   ", ""],
        )


def test_empty_json_events_is_rejected():
    with pytest.raises(SimulationValidationError, match="json_events must contain"):
        run_detection_simulation(
            source="bank_app",
            rule_id="failed_login_threshold",
            input_format="json",
            json_events=[],
        )


def test_batch_size_over_limit_is_rejected():
    with pytest.raises(SimulationValidationError, match="exceeds maximum size"):
        run_detection_simulation(
            source="bank_app",
            rule_id="failed_login_threshold",
            input_format="json",
            json_events=[{"event_type": "failed_login"}] * 26,
        )


# --- parser/normalizer reuse (no DB needed: pick a rule inapplicable to the
# source so the function returns before opening a database connection) ------


def test_pfsense_raw_parser_reuse_succeeds_before_db():
    raw_line = (
        "Jan  1 00:00:00 filterlog: 1,,,1000000103,igb1,match,block,in,4,0x0,,64,0,0,DF,"
        "6,tcp,60,203.0.113.5,198.51.100.10,54321,22,0,S"
    )
    result = run_detection_simulation(
        source="pfsense",
        rule_id="honeypot_scanner_detected",  # not applicable to pfsense
        input_format="raw",
        raw_lines=[raw_line],
    )
    assert result["stages"]["parser"]["status"] == "succeeded"
    assert result["stages"]["normalized_event"]["status"] == "succeeded"
    normalized = result["stages"]["normalized_event"]["events"][0]
    assert normalized["source"] == "pfsense"
    assert normalized["event_type"] == "firewall_block"
    assert result["stages"]["detection_applicability"]["status"] == "failed"
    assert result["stages"]["detection_evaluation"]["reason"] == "rule_not_applicable_to_source"


def test_pfsense_raw_parser_failure_is_reported_not_raised():
    result = run_detection_simulation(
        source="pfsense",
        rule_id="pfsense_firewall_repeated_deny",
        input_format="raw",
        raw_lines=["this is not a valid filterlog line"],
    )
    assert result["stages"]["parser"]["status"] == "failed"
    assert result["stages"]["parser"]["results"][0]["status"] == "failed"
    assert "error" in result["stages"]["parser"]["results"][0]
    assert result["stages"]["normalized_event"]["status"] == "skipped"
    assert result["stages"]["normalized_event"]["reason"] == "parser_failed"
    assert result["stages"]["detection_applicability"]["status"] == "skipped"


def test_nginx_raw_parser_reuse_succeeds_before_db():
    line = '203.0.113.9 - - [10/Oct/2026:13:55:36 -0700] "GET /admin HTTP/1.1" 500 123'
    result = run_detection_simulation(
        source="nginx",
        rule_id="honeypot_scanner_detected",  # not applicable to nginx
        input_format="raw",
        raw_lines=[line],
    )
    normalized = result["stages"]["normalized_event"]["events"][0]
    assert normalized["source"] == "nginx"
    assert normalized["event_type"] == "http_error"
    assert result["stages"]["detection_applicability"]["status"] == "failed"


def test_honeypot_json_normalizer_reuse_succeeds_before_db():
    result = run_detection_simulation(
        source="honeypot",
        rule_id="port_scan_threshold",  # not applicable to honeypot
        input_format="json",
        json_events=[
            {
                "event_type": "env_probe",
                "source_ip": "203.0.113.11",
                "path": "/.env",
                "method": "GET",
            }
        ],
    )
    normalized = result["stages"]["normalized_event"]["events"][0]
    assert normalized["source"] == "honeypot"
    assert normalized["event_type"] == "env_probe"
    assert result["stages"]["detection_applicability"]["status"] == "failed"


def test_honeypot_raw_password_field_is_rejected_by_reused_normalizer():
    result = run_detection_simulation(
        source="honeypot",
        rule_id="honeypot_credential_stuffing_threshold",
        input_format="json",
        json_events=[
            {
                "event_type": "credential_stuffing",
                "source_ip": "203.0.113.12",
                "username": "admin",
                "password": "hunter2",
            }
        ],
    )
    assert result["stages"]["parser"]["status"] == "failed"
    assert "password" in result["stages"]["parser"]["results"][0]["error"].lower()


def test_bank_app_json_normalizer_reuse_succeeds_before_db():
    result = run_detection_simulation(
        source="bank_app",
        rule_id="honeypot_scanner_detected",  # not applicable to bank_app
        input_format="json",
        json_events=[
            {
                "event_type": "failed_login",
                "severity": "medium",
                "source_ip": "203.0.113.13",
                "message": "Failed login attempt",
                "app_name": "bank_app",
                "environment": "test",
            }
        ],
    )
    normalized = result["stages"]["normalized_event"]["events"][0]
    assert normalized["source"] == "bank_app"
    assert result["stages"]["detection_applicability"]["status"] == "failed"


def test_bank_app_missing_field_is_reported_as_parser_failure():
    result = run_detection_simulation(
        source="bank_app",
        rule_id="failed_login_threshold",
        input_format="json",
        json_events=[{"event_type": "failed_login", "source_ip": "203.0.113.14"}],
    )
    assert result["stages"]["parser"]["status"] == "failed"
    assert result["stages"]["normalized_event"]["status"] == "skipped"


# --- Detection Applicability stage: explicit fail-closed --------------------


def test_rule_not_applicable_to_source_marks_applicability_failed():
    result = run_detection_simulation(
        source="honeypot",
        rule_id="failed_login_threshold",  # only bank_app/azure_insights/nginx/otel
        input_format="json",
        json_events=[{"event_type": "env_probe", "source_ip": "203.0.113.15", "path": "/.env"}],
    )
    stage = result["stages"]["detection_applicability"]
    assert stage["status"] == "failed"
    assert "not applicable" in stage["reason"]
    for name in ("detection_evaluation", "threshold_window_evaluation", "alert_preview", "mitre_mapping", "soar_preview"):
        assert result["stages"][name]["status"] == "skipped"


# --- rollback-only transaction: zero durable writes, real Postgres ----------


def _make_bank_app_event(username, source_ip="198.51.100.201"):
    return {
        "event_type": "failed_login",
        "severity": "medium",
        "source_ip": source_ip,
        "message": f"Failed login attempt for username: {username}",
        "app_name": "bank_app",
        "environment": "test",
        "username": username,
    }


def test_zero_durable_writes_across_all_guarded_tables(postgres_db):
    conn, cur = postgres_db
    insert_playbook(
        cur,
        "pb-sim-test",
        trigger_config={"alert_type": "failed_login_threshold"},
        steps=[{"action": "notify_slack", "params": {}}, {"action": "require_approval", "risk_level": "high"}],
    )
    conn.commit()

    guarded_tables = (
        "events",
        "alerts",
        "playbook_executions",
        "soar_response_decisions",
        "response_actions_queue",
        "response_actions_log",
        "incidents",
        "incident_alerts",
        "audit_log",
    )
    before_counts = {table: count_rows(cur, table) for table in guarded_tables}

    events = [_make_bank_app_event(f"user{i}") for i in range(5)]

    with patch("engines.detection_simulator.get_db_connection", return_value=RollbackOnlyConnection(conn)):
        result = run_sim(
            source="bank_app",
            rule_id="failed_login_threshold",
            input_format="json",
            json_events=events,
        )

    # Sanity: this scenario really would have produced an alert on the real
    # /ingest path (5 failed logins >= default threshold of 3).
    assert result["stages"]["threshold_window_evaluation"]["matched"] is True
    assert result["stages"]["alert_preview"]["alert"] is not None

    after_counts = {table: count_rows(cur, table) for table in guarded_tables}
    assert after_counts == before_counts, "simulation left durable rows in a guarded table"


def test_no_pending_row_is_visible_to_a_genuinely_separate_connection(postgres_db):
    # engines.soar_action_worker / engines.soar_playbook_worker poll
    # response_actions_queue / playbook_executions for status='pending' rows
    # on their OWN database connections, not the simulation's. This test
    # proves the worker-visible surface directly, from a second, independent
    # connection, rather than only inferring it from an unchanged row count
    # on the same connection the simulation used.
    conn, cur = postgres_db
    cur.execute("SELECT current_schema()")
    schema_name = cur.fetchone()[0]

    insert_playbook(
        cur,
        "pb-worker-visibility-test",
        trigger_config={"alert_type": "failed_login_threshold"},
        steps=[{"action": "notify_slack", "params": {}}],
    )
    conn.commit()

    events = [_make_bank_app_event(f"worker{i}") for i in range(5)]
    with patch("engines.detection_simulator.get_db_connection", return_value=RollbackOnlyConnection(conn)):
        result = run_sim(
            source="bank_app",
            rule_id="failed_login_threshold",
            input_format="json",
            json_events=events,
        )
    assert result["stages"]["threshold_window_evaluation"]["matched"] is True

    dsn = os.getenv("SIEM_TEST_DATABASE_URL") or os.getenv("TEST_DATABASE_URL") or "dbname=postgres"
    worker_conn = psycopg2.connect(dsn)
    try:
        worker_cur = worker_conn.cursor()
        worker_cur.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema_name)))
        worker_cur.execute("SELECT COUNT(*) FROM playbook_executions WHERE status = 'pending'")
        assert worker_cur.fetchone()[0] == 0
        worker_cur.execute("SELECT COUNT(*) FROM response_actions_queue WHERE status = 'pending'")
        assert worker_cur.fetchone()[0] == 0
    finally:
        worker_conn.close()


def test_mid_pipeline_exception_still_rolls_back(postgres_db):
    conn, cur = postgres_db
    before_events = count_rows(cur, "events")
    before_alerts = count_rows(cur, "alerts")

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated unexpected failure")

    with patch("engines.detection_simulator.get_db_connection", return_value=RollbackOnlyConnection(conn)), patch(
        "engines.detection_simulator.match_playbooks", side_effect=_boom
    ):
        events = [_make_bank_app_event(f"crash{i}", source_ip="198.51.100.202") for i in range(5)]
        with pytest.raises(RuntimeError, match="simulated unexpected failure"):
            run_sim(
                source="bank_app",
                rule_id="failed_login_threshold",
                input_format="json",
                json_events=events,
            )

    assert count_rows(cur, "events") == before_events
    assert count_rows(cur, "alerts") == before_alerts


def test_never_commits_even_when_wrapper_forbids_commit(postgres_db):
    # RollbackOnlyConnection has no commit() method at all. If anything in
    # the simulation code path ever called conn.commit(), this test would
    # fail with AttributeError instead of silently succeeding.
    conn, cur = postgres_db
    events = [_make_bank_app_event(f"nocommit{i}", source_ip="198.51.100.203") for i in range(5)]

    with patch("engines.detection_simulator.get_db_connection", return_value=RollbackOnlyConnection(conn)):
        result = run_sim(
            source="bank_app",
            rule_id="failed_login_threshold",
            input_format="json",
            json_events=events,
        )

    assert result["stages"]["detection_evaluation"]["status"] == "succeeded"


# --- detection matched: alert preview, MITRE, and disclosures ---------------


def test_detection_matched_alert_preview_and_mitre(postgres_db):
    conn, cur = postgres_db
    events = [_make_bank_app_event(f"mitre{i}", source_ip="198.51.100.204") for i in range(5)]

    with patch("engines.detection_simulator.get_db_connection", return_value=RollbackOnlyConnection(conn)):
        result = run_sim(
            source="bank_app",
            rule_id="failed_login_threshold",
            input_format="json",
            json_events=events,
        )

    alert = result["stages"]["alert_preview"]["alert"]
    assert alert["alert_type"] == "failed_login_threshold"
    assert alert["reputation_source"] == "simulated"
    assert result["stages"]["mitre_mapping"]["mitre_technique_id"] == "T1110"
    assert result["stages"]["soar_preview"]["status"] == "succeeded"
    assert result["stages"]["soar_preview"]["no_playbook_match"] is True


def test_existing_open_alert_suppression_is_disclosed(postgres_db):
    conn, cur = postgres_db
    source_ip = "198.51.100.205"
    cur.execute(
        """
        INSERT INTO alerts (source_ip, alert_type, severity, source, source_type, message, status)
        VALUES (%s, 'failed_login_threshold', 'high', 'bank_app', 'custom', 'pre-existing open alert', 'open')
        """,
        (source_ip,),
    )
    conn.commit()

    events = [_make_bank_app_event(f"dup{i}", source_ip=source_ip) for i in range(5)]

    with patch("engines.detection_simulator.get_db_connection", return_value=RollbackOnlyConnection(conn)):
        result = run_sim(
            source="bank_app",
            rule_id="failed_login_threshold",
            input_format="json",
            json_events=events,
        )

    threshold_stage = result["stages"]["threshold_window_evaluation"]
    assert threshold_stage["existing_open_alert_for_rule"] is True
    assert threshold_stage["matched"] is False
    assert "suppress" in threshold_stage["note"]
    # Dedup already explains "no alert" -- no evidence call should have run,
    # and no numeric value is fabricated to fill the gap.
    assert threshold_stage["evidence_available"] is False
    assert threshold_stage["observed_value"] is None


# --- near-miss threshold evidence: reuses the real detector, never a shadow evaluator ---


def test_rule_id_to_detector_maps_to_the_exact_production_functions():
    from engines import correlation_engine, detection_engine
    from engines.detection_simulator import RULE_ID_TO_DETECTOR

    # Proves every mapped callable is the identical function object
    # engines.detection_engine defines -- not a copy, wrapper, or reimplementation.
    for rule_id, mapped_fn in RULE_ID_TO_DETECTOR.items():
        production_fn = getattr(detection_engine, mapped_fn.__name__)
        assert mapped_fn is production_fn, f"{rule_id} does not map to the real detector function"

    # correlation_engine's two functions are never user-selectable rule ids
    # (they aren't in get_detection_rule_defaults()), so they are correctly
    # absent from this mapping -- not an oversight.
    from engines.detection_config import get_detection_rule_defaults

    assert set(RULE_ID_TO_DETECTOR) == set(get_detection_rule_defaults())
    assert not hasattr(correlation_engine, "RULE_ID_TO_DETECTOR")


def test_threshold_not_met_surfaces_real_observed_value_via_evidence_call(postgres_db):
    conn, cur = postgres_db
    # Default failed_login_threshold threshold is 3; two attempts is a
    # genuine below-threshold near-miss.
    events = [_make_bank_app_event(f"nearmiss{i}", source_ip="198.51.100.220") for i in range(2)]

    with patch("engines.detection_simulator.get_db_connection", return_value=RollbackOnlyConnection(conn)):
        result = run_sim(
            source="bank_app",
            rule_id="failed_login_threshold",
            input_format="json",
            json_events=events,
        )

    stage = result["stages"]["threshold_window_evaluation"]
    assert stage["matched"] is False
    assert stage["existing_open_alert_for_rule"] is False
    assert stage["evidence_available"] is True
    assert stage["observed_value"] == 2
    assert stage["observed_value_label"] == "attempts"
    assert stage["configured_threshold"] == 3
    assert stage["evaluated_window_minutes"] == 15
    assert result["stages"]["alert_preview"]["alert"] is None


def test_threshold_met_reports_observed_value_without_a_second_query(postgres_db):
    conn, cur = postgres_db
    events = [_make_bank_app_event(f"met{i}", source_ip="198.51.100.221") for i in range(5)]

    with patch("engines.detection_simulator.get_db_connection", return_value=RollbackOnlyConnection(conn)):
        result = run_sim(
            source="bank_app",
            rule_id="failed_login_threshold",
            input_format="json",
            json_events=events,
        )

    stage = result["stages"]["threshold_window_evaluation"]
    assert stage["matched"] is True
    assert stage["evidence_available"] is True
    # Genuine production behavior, not a rounding artifact: the real
    # detector alerts the moment count crosses the threshold (at the 3rd
    # ingested event), then production dedup silently skips re-evaluating
    # once an open alert exists -- so the true observed value at the moment
    # of alert creation is 3, not 5, even though 5 events were pasted. This
    # is exactly the kind of truthful evaluation evidence this instrumentation
    # exists to surface rather than paper over.
    assert stage["observed_value"] == 3
    assert stage["observed_value_label"] == "attempts"
    assert stage["configured_threshold"] == 3


def test_evidence_call_never_survives_rollback(postgres_db):
    # The evidence call inserts a phantom alert row (threshold=1) inside the
    # same rolled-back transaction when the real threshold isn't met. This
    # must never become a durable row, exactly like every other simulated
    # write.
    conn, cur = postgres_db
    before_alerts = count_rows(cur, "alerts")
    before_events = count_rows(cur, "events")

    events = [_make_bank_app_event(f"phantom{i}", source_ip="198.51.100.222") for i in range(1)]

    with patch("engines.detection_simulator.get_db_connection", return_value=RollbackOnlyConnection(conn)):
        result = run_sim(
            source="bank_app",
            rule_id="failed_login_threshold",
            input_format="json",
            json_events=events,
        )

    assert result["stages"]["threshold_window_evaluation"]["evidence_available"] is True
    assert result["stages"]["threshold_window_evaluation"]["observed_value"] == 1
    assert count_rows(cur, "alerts") == before_alerts
    assert count_rows(cur, "events") == before_events


def test_evidence_call_does_not_run_for_rules_without_a_threshold_parameter():
    # Defensive: _fetch_threshold_evidence must not crash for a hypothetical
    # rule_config lacking a "threshold" key; it should decline gracefully.
    from engines.detection_simulator import _fetch_threshold_evidence

    with siem_backend.app.app_context():
        label, value = _fetch_threshold_evidence(
            conn=None,
            cur=None,
            rule_id="failed_login_threshold",
            rule_config={"parameters": {}, "active": True},
            source="bank_app",
            source_type="custom",
            source_ip="198.51.100.223",
        )
    assert (label, value) == (None, None)


def test_blended_with_real_history_is_disclosed(postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO events (event_type, severity, source_ip, source, source_type, message, app_name, environment, raw_payload)
        VALUES ('failed_login', 'medium', '198.51.100.206', 'bank_app', 'custom', 'real prior event', 'bank_app', 'test', '{}'::jsonb)
        """
    )
    conn.commit()

    events = [_make_bank_app_event("blend1", source_ip="198.51.100.206")]

    with patch("engines.detection_simulator.get_db_connection", return_value=RollbackOnlyConnection(conn)):
        result = run_sim(
            source="bank_app",
            rule_id="failed_login_threshold",
            input_format="json",
            json_events=events,
        )

    assert result["stages"]["threshold_window_evaluation"]["blended_with_real_history"] is True


def test_soar_preview_matches_playbook_and_surfaces_approval(postgres_db):
    conn, cur = postgres_db
    insert_playbook(
        cur,
        "pb-approval-test",
        trigger_config={"alert_type": "failed_login_threshold"},
        steps=[{"action": "require_approval", "risk_level": "critical"}],
    )
    conn.commit()

    events = [_make_bank_app_event(f"approve{i}", source_ip="198.51.100.207") for i in range(5)]

    with patch("engines.detection_simulator.get_db_connection", return_value=RollbackOnlyConnection(conn)):
        result = run_sim(
            source="bank_app",
            rule_id="failed_login_threshold",
            input_format="json",
            json_events=events,
        )

    soar = result["stages"]["soar_preview"]
    assert soar["no_playbook_match"] is False
    matched = next(p for p in soar["matched_playbooks"] if p["playbook_id"] == "pb-approval-test")
    assert matched["approval_required"] is True
    assert matched["approval_risk_levels"] == ["critical"]


def test_no_integration_adapter_invoked_during_simulation(postgres_db):
    conn, cur = postgres_db
    insert_playbook(
        cur,
        "pb-adapter-test",
        trigger_config={"alert_type": "failed_login_threshold"},
        steps=[{"action": "notify_slack", "params": {}}],
    )
    conn.commit()

    events = [_make_bank_app_event(f"adapter{i}", source_ip="198.51.100.208") for i in range(5)]

    with patch("engines.detection_simulator.get_db_connection", return_value=RollbackOnlyConnection(conn)), patch(
        "integrations.slack_adapter._post_slack_webhook"
    ) as mock_post_webhook:
        run_sim(
            source="bank_app",
            rule_id="failed_login_threshold",
            input_format="json",
            json_events=events,
        )

    mock_post_webhook.assert_not_called()


# --- reputation stub: no live third-party call, no production impact -------


def test_reputation_lookup_is_stubbed_not_called_live(postgres_db):
    # Patch requests.get at its source: if the stub in engines.detection_simulator
    # ever failed to apply and the real core.ip_helpers.lookup_ip_reputation ran,
    # this is the outbound HTTP call it would make. Asserting it's never called is
    # a stronger guarantee than mocking lookup_ip_reputation itself, since that
    # would not detect a broken patch target (detection_engine/correlation_engine
    # each import their own bound reference to the function).
    conn, cur = postgres_db
    events = [_make_bank_app_event(f"rep{i}", source_ip="198.51.100.209") for i in range(5)]

    with patch("engines.detection_simulator.get_db_connection", return_value=RollbackOnlyConnection(conn)), patch(
        "core.ip_helpers.requests.get"
    ) as mock_get:
        result = run_sim(
            source="bank_app",
            rule_id="failed_login_threshold",
            input_format="json",
            json_events=events,
        )

    mock_get.assert_not_called()
    assert result["stages"]["alert_preview"]["alert"]["reputation_source"] == "simulated"


# --- HTTP route: authentication / authorization ------------------------------


def test_route_requires_authentication(client):
    response = client.post("/detection-simulator/run", json={})
    assert response.status_code == 401


def test_route_rejects_viewer_role(client):
    with logged_in_role(client, "viewer"):
        response = client.post("/detection-simulator/run", json={})
    assert response.status_code == 403
    assert response.get_json()["error"] == "forbidden"


def test_route_allows_analyst_and_returns_simulation_result(client, postgres_db):
    conn, cur = postgres_db

    with logged_in_role(client, "analyst"):
        with patch(
            "engines.detection_simulator.get_db_connection",
            return_value=RollbackOnlyConnection(conn),
        ):
            response = client.post(
                "/detection-simulator/run",
                json={
                    "source": "bank_app",
                    "rule_id": "failed_login_threshold",
                    "input_format": "json",
                    "json_events": [_make_bank_app_event("routeuser", source_ip="198.51.100.210")],
                },
            )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["simulated"] is True
    assert set(payload["stages"]) == set(
        [
            "raw_input",
            "parser",
            "normalized_event",
            "detection_applicability",
            "detection_evaluation",
            "threshold_window_evaluation",
            "alert_preview",
            "mitre_mapping",
            "soar_preview",
        ]
    )


def test_route_allows_super_admin(client, postgres_db):
    conn, cur = postgres_db
    login_super_admin(client)

    with patch(
        "engines.detection_simulator.get_db_connection",
        return_value=RollbackOnlyConnection(conn),
    ):
        response = client.post(
            "/detection-simulator/run",
            json={
                "source": "bank_app",
                "rule_id": "failed_login_threshold",
                "input_format": "json",
                "json_events": [_make_bank_app_event("adminuser", source_ip="198.51.100.211")],
            },
        )

    assert response.status_code == 200


def test_route_rejects_malformed_request_body(client):
    with logged_in_role(client, "analyst"):
        response = client.post("/detection-simulator/run", json={"source": "bank_app"})
    assert response.status_code == 400


# --- HTTP route: rule listing --------------------------------------------


def test_rules_route_requires_authentication(client):
    response = client.get("/detection-simulator/rules")
    assert response.status_code == 401


def test_rules_route_rejects_viewer_role(client):
    with logged_in_role(client, "viewer"):
        response = client.get("/detection-simulator/rules")
    assert response.status_code == 403


def test_rules_route_allows_analyst_and_lists_existing_rules_only(client):
    from engines.detection_config import get_detection_rule_defaults

    with logged_in_role(client, "analyst"):
        response = client.get("/detection-simulator/rules")

    assert response.status_code == 200
    payload = response.get_json()
    rule_ids = {rule["rule_id"] for rule in payload["rules"]}
    assert rule_ids == set(get_detection_rule_defaults())
    for rule in payload["rules"]:
        assert set(rule) == {"rule_id", "display_name", "description", "active", "applicable_sources"}


def test_route_rejects_unknown_rule_id(client):
    with logged_in_role(client, "analyst"):
        response = client.post(
            "/detection-simulator/run",
            json={
                "source": "bank_app",
                "rule_id": "not_a_real_rule",
                "input_format": "json",
                "json_events": [{"event_type": "failed_login"}],
            },
        )
    assert response.status_code == 400


def test_route_rejects_unsupported_source_rule_input_combo(client):
    with logged_in_role(client, "analyst"):
        response = client.post(
            "/detection-simulator/run",
            json={
                "source": "nginx",
                "rule_id": "http_error_threshold",
                "input_format": "json",
                "json_events": [{"foo": "bar"}],
            },
        )
    assert response.status_code == 400
