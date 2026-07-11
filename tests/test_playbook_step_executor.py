import inspect
import http.client
import smtplib
import socket
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from psycopg2.extras import Json

from core import (
    approval_store,
    dead_letter_store,
    notification_delivery_store,
    playbook_store,
    soar_response_outcomes as outcomes,
)
from engines import playbook_step_executor
from scripts import run_playbook_executor_once
from integrations.base_integration import (
    CIRCUIT_STATE_CLOSED,
    CIRCUIT_STATE_HALF_OPEN,
    CIRCUIT_STATE_OPEN,
    FAILURE_CLASSIFICATION_GUARD_FAILED,
    FAILURE_CLASSIFICATION_PROVIDER_RATE_LIMITED,
    FAILURE_CLASSIFICATION_TIMEOUT,
    FAILURE_CLASSIFICATION_TRANSIENT,
    configure_simulated_circuit_breaker,
    get_simulated_circuit_breaker_dict,
    reset_simulated_circuit_breakers,
)
from integrations.adapter_rate_limiter import reset_adapter_rate_limiters
from integrations.slack_adapter import SlackSimulationAdapter


def _valid_steps():
    return [{"action": "monitor", "params": {}}]


def _insert_alert(cur, source_ip="10.0.0.1"):
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message)
        VALUES ('test_alert', 'LOW', %s::inet, 'msg')
        RETURNING id
        """,
        (source_ip,),
    )
    return cur.fetchone()[0]


def _create_execution(conn, cur, playbook_id="pb_exec", steps=None):
    aid = _insert_alert(cur)
    playbook_store.create_playbook_definition(
        conn,
        playbook_id,
        playbook_id,
        steps=steps if steps is not None else _valid_steps(),
    )
    return playbook_store.create_pending_playbook_execution_once(conn, playbook_id, aid)


def _create_linked_execution(
    conn,
    cur,
    playbook_id="pb_linked",
    steps=None,
    source_ip="198.51.100.42",
):
    aid = _insert_alert(cur, source_ip=source_ip)
    playbook_store.create_playbook_definition(
        conn,
        playbook_id,
        playbook_id,
        steps=steps if steps is not None else _valid_steps(),
    )
    decision = outcomes.create_response_decision(
        conn,
        selected_action=f"playbook:{playbook_id}",
        decision_source="playbook",
        outcome_summary=f"Playbook {playbook_id} selected for simulation.",
        alert_id=aid,
        source_ip=source_ip,
        playbook_id=playbook_id,
    )
    eid = playbook_store.create_pending_playbook_execution_once(
        conn,
        playbook_id,
        aid,
        decision_id=decision["id"],
        soar_correlation_id=decision["soar_correlation_id"],
    )
    return eid, decision


def _set_playbook_steps(cur, playbook_id, steps):
    cur.execute(
        "UPDATE playbook_definitions SET steps = %s WHERE id = %s",
        (Json(steps), playbook_id),
    )


def _count(cur, table):
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    return cur.fetchone()[0]


def _fetch_playbook_outcome_events(cur, execution_id):
    cur.execute(
        """
        SELECT event_type, execution_mode, execution_state, execution_actor,
               reason_code, simulated, external_executed, tracking_recorded,
               idempotency_key, playbook_execution_id, playbook_step_index,
               alert_id, host(source_ip), approval_request_id, metadata
        FROM soar_response_outcome_events
        WHERE playbook_execution_id = %s
        ORDER BY id
        """,
        (execution_id,),
    )
    return cur.fetchall()


def _progress_entry(step_index, action, now=None):
    timestamp = now or datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)
    return {
        "step_index": step_index,
        "action": action,
        "status": "success",
        "mode": "simulation",
        "started_at": timestamp.isoformat().replace("+00:00", "Z"),
        "completed_at": timestamp.isoformat().replace("+00:00", "Z"),
        "message": "previously completed",
        "output": {"simulated": True, "executed": False},
        "error": None,
    }


def _set_execution_progress(
    cur,
    execution_id,
    *,
    status="pending",
    steps_log=None,
    last_completed_step=None,
    lease_owner=None,
):
    cur.execute(
        """
        UPDATE playbook_executions
        SET status = %s,
            steps_log = %s,
            last_completed_step = %s,
            lease_owner = %s,
            lease_acquired_at = CASE WHEN %s IS NULL THEN NULL ELSE NOW() END,
            lease_heartbeat_at = CASE WHEN %s IS NULL THEN NULL ELSE NOW() END,
            lease_expires_at = CASE WHEN %s IS NULL THEN NULL ELSE NOW() + INTERVAL '5 minutes' END
        WHERE id = %s
        """,
        (
            status,
            Json(steps_log or []),
            last_completed_step,
            lease_owner,
            lease_owner,
            lease_owner,
            lease_owner,
            execution_id,
        ),
    )


def _set_expired_running_progress(cur, execution_id, *, steps_log, last_completed_step):
    expired = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)
    cur.execute(
        """
        UPDATE playbook_executions
        SET status = 'running',
            steps_log = %s,
            last_completed_step = %s,
            lease_owner = 'stale-worker',
            lease_acquired_at = %s,
            lease_heartbeat_at = %s,
            lease_expires_at = %s
        WHERE id = %s
        """,
        (Json(steps_log), last_completed_step, expired, expired, expired, execution_id),
    )
    return expired + timedelta(minutes=5)


@pytest.fixture(autouse=True)
def _reset_playbook_integration_circuits():
    reset_simulated_circuit_breakers()
    reset_adapter_rate_limiters()
    yield
    reset_adapter_rate_limiters()
    reset_simulated_circuit_breakers()


@pytest.fixture
def no_network(monkeypatch):
    def fail_network(*_args, **_kwargs):
        raise AssertionError("network call attempted by playbook adapter simulation")

    monkeypatch.setattr(socket, "socket", fail_network)
    monkeypatch.setattr(smtplib, "SMTP", fail_network)
    monkeypatch.setattr(smtplib, "SMTP_SSL", fail_network)
    monkeypatch.setattr(http.client.HTTPConnection, "request", fail_network)
    monkeypatch.setattr(http.client.HTTPSConnection, "request", fail_network)


def _insert_user(cur, username="playbook-approver"):
    cur.execute(
        """
        INSERT INTO users (username, password_hash, role)
        VALUES (%s, 'hash', 'analyst')
        RETURNING id
        """,
        (username,),
    )
    return cur.fetchone()[0]


def test_enrich_context_step_outputs_alert_context_without_external_lookup(postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO alerts (
            alert_type, severity, source_ip, message, source, source_type,
            country, city, latitude, longitude,
            reputation_score, reputation_label, reputation_source, reputation_summary,
            context
        )
        VALUES (
            'password_spraying_threshold', 'HIGH', '203.0.113.44'::inet,
            'spray detected', 'nginx', 'web_log',
            'United States', 'New York', 40.7, -74.0,
            72, 'High Risk', 'abuseipdb', 'stored snapshot',
            %s
        )
        RETURNING id
        """,
        (
            Json(
                {
                    "username": "alice",
                    "correlation_type": "auth",
                    "matched_rule_id": "spray-rule",
                    "matched_alert_count": 3,
                    "contributing_alert_types": ["failed_login_threshold"],
                }
            ),
        ),
    )
    alert_id = cur.fetchone()[0]
    playbook_store.create_playbook_definition(
        conn,
        "pb_enrich_alert",
        "Enrich Alert",
        steps=[{"action": "enrich_context", "params": {"limit": 3}}],
    )
    execution_id = playbook_store.create_playbook_execution(conn, "pb_enrich_alert", alert_id)
    conn.commit()

    with patch("core.ip_helpers.lookup_ip_reputation", side_effect=AssertionError("external lookup")):
        result = playbook_step_executor.process_playbook_execution(conn, execution_id)

    assert result["outcome"] == "success"
    row = playbook_store.get_playbook_execution(conn, execution_id)
    entry = row["steps_log"][0]
    assert entry["action"] == "enrich_context"
    assert entry["status"] == "success"
    assert entry["mode"] == "read_only"
    output = entry["output"]
    assert output["read_only"] is True
    assert output["executed"] is True
    assert output["simulated"] is False
    assert output["external_side_effect"] is False
    assert "no external action" in entry["message"].lower()
    context = output["context"]
    assert context["target"] == {
        "target_type": "alert",
        "target_id": alert_id,
        "alert_id": alert_id,
        "incident_id": None,
        "source_ip": "203.0.113.44",
    }
    assert context["alert"]["alert_type"] == "password_spraying_threshold"
    assert context["mitre"]["technique_id"] == "T1110.003"
    assert context["reputation"]["alert_snapshot"]["score"] == 72
    assert context["reputation"]["latest_external"]["source"] == "abuseipdb"
    assert context["source_ip_context"]["alert_counts"]["total"] == 1
    assert context["usernames"] == ["alice"]


def test_enrich_context_step_outputs_incident_and_linked_alert_context(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, source_ip="198.51.100.88")
    cur.execute(
        """
        INSERT INTO incidents (title, severity, priority, status, source_ip)
        VALUES ('Linked incident', 'HIGH', 'P2', 'open', '198.51.100.88'::inet)
        RETURNING id
        """
    )
    incident_id = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO incident_alerts (incident_id, alert_id) VALUES (%s, %s)",
        (incident_id, alert_id),
    )
    playbook_store.create_playbook_definition(
        conn,
        "pb_enrich_incident",
        "Enrich Incident",
        steps=[{"action": "enrich_context"}],
    )
    execution_id = playbook_store.create_playbook_execution(
        conn,
        "pb_enrich_incident",
        alert_id=None,
        incident_id=incident_id,
    )
    conn.commit()

    result = playbook_step_executor.process_playbook_execution(conn, execution_id)

    assert result["outcome"] == "success"
    row = playbook_store.get_playbook_execution(conn, execution_id)
    context = row["steps_log"][0]["output"]["context"]
    assert context["target"]["target_type"] == "incident"
    assert context["target"]["incident_id"] == incident_id
    assert context["incident"]["id"] == incident_id
    assert context["linked_alerts"][0]["id"] == alert_id
    assert context["source_ip_context"]["source_ip"] == "198.51.100.88"
    assert context["previous_incidents"]["count"] >= 1


def test_no_pending_execution_returns_empty_batch(postgres_db):
    conn, _cur = postgres_db

    assert playbook_step_executor.process_next_pending_playbook_execution(conn) is None
    assert playbook_step_executor.process_playbook_execution_batch(conn) == {
        "processed": 0,
        "success": 0,
        "failed": 0,
        "skipped": 0,
        "results": [],
    }


def test_pending_monitor_step_becomes_success(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_monitor")

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "success"
    assert row["started_at"] is not None
    assert row["completed_at"] is not None
    assert row["last_completed_step"] == 0
    assert len(row["steps_log"]) == 1
    entry = row["steps_log"][0]
    assert entry["action"] == "monitor"
    assert entry["status"] == "success"
    assert entry["mode"] == "internal"
    assert entry["output"]["executed"] is True
    assert entry["output"]["canonical_response"] is True
    assert entry["output"]["registry_record_id"] is not None
    assert _count(cur, "soar_dead_letters") == 0


def test_linked_playbook_claim_appends_running_outcome_event(postgres_db):
    conn, cur = postgres_db
    eid, decision = _create_linked_execution(conn, cur, "pb_outcome_running")

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    events = _fetch_playbook_outcome_events(cur, eid)
    running = events[0]
    assert running[0:9] == (
        "running",
        "internal",
        "running",
        "playbook_worker",
        None,
        False,
        False,
        False,
        f"playbook-running-{eid}",
    )
    assert running[9] == eid
    assert running[10] is None
    assert running[11] == decision["alert_id"]
    assert running[12] == "198.51.100.42"


def test_linked_playbook_success_appends_succeeded_outcome_event(postgres_db):
    conn, cur = postgres_db
    eid, decision = _create_linked_execution(conn, cur, "pb_outcome_success")

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    events = _fetch_playbook_outcome_events(cur, eid)
    assert [event[0] for event in events] == ["running", "step_succeeded", "succeeded"]
    succeeded = [event for event in events if event[0] == "succeeded"][0]
    assert succeeded[0:9] == (
        "succeeded",
        "internal",
        "succeeded",
        "playbook_worker",
        None,
        False,
        False,
        False,
        f"playbook-success-{eid}",
    )
    assert succeeded[9] == eid
    assert succeeded[10] is None
    assert succeeded[11] == decision["alert_id"]


def test_linked_playbook_failure_appends_failed_outcome_event(postgres_db):
    conn, cur = postgres_db
    eid, _decision = _create_linked_execution(conn, cur, "pb_outcome_failed")
    _set_playbook_steps(cur, "pb_outcome_failed", [{"action": "bad_action"}])

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    events = _fetch_playbook_outcome_events(cur, eid)
    assert [event[0] for event in events] == ["running", "step_failed", "failed"]
    failed = [event for event in events if event[0] == "failed"][0]
    assert failed[0:9] == (
        "failed",
        "internal",
        "failed",
        "playbook_worker",
        None,
        False,
        False,
        False,
        f"playbook-failed-{eid}",
    )
    assert failed[9] == eid
    assert failed[10] is None


def test_playbook_outcome_idempotency_keys_prevent_duplicate_events(postgres_db):
    conn, cur = postgres_db
    eid, _decision = _create_linked_execution(conn, cur, "pb_outcome_idempotent")
    execution = playbook_store.get_playbook_execution(conn, eid)

    first = playbook_step_executor._append_playbook_running_outcome_event(conn, execution)
    second = playbook_step_executor._append_playbook_running_outcome_event(conn, execution)

    assert first["id"] == second["id"]
    events = _fetch_playbook_outcome_events(cur, eid)
    assert len(events) == 1
    assert events[0][8] == f"playbook-running-{eid}"


def test_unlinked_legacy_playbook_execution_preserves_behavior_without_outcomes(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_legacy_unlinked")

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "success"
    assert row["decision_id"] is None
    assert row["soar_correlation_id"] is None
    assert _fetch_playbook_outcome_events(cur, eid) == []


def test_linked_non_adapter_steps_append_step_outcome_events(postgres_db):
    conn, cur = postgres_db
    eid, _decision = _create_linked_execution(
        conn,
        cur,
        "pb_step_outcomes",
        steps=[
            {"action": "monitor"},
            {"action": "flag_high_priority"},
            {"action": "block_ip", "params": {"source_ip": "203.0.113.10"}},
        ],
    )

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    events = _fetch_playbook_outcome_events(cur, eid)
    step_events = [event for event in events if event[0] == "step_succeeded"]
    assert [(event[10], event[14]["action"]) for event in step_events] == [
        (0, "monitor"),
        (1, "flag_high_priority"),
    ]
    assert [event[8] for event in step_events] == [
        f"playbook-step-{eid}-0-succeeded",
        f"playbook-step-{eid}-1-succeeded",
    ]
    assert all(event[3] == "playbook_worker" for event in step_events)
    assert all(event[1] == "internal" for event in step_events)
    assert all(event[5] is False for event in step_events)
    assert all(event[10] != 2 for event in step_events)


def test_linked_playbook_awaiting_approval_appends_linked_event(postgres_db):
    conn, cur = postgres_db
    eid, _decision = _create_linked_execution(
        conn,
        cur,
        "pb_awaiting_outcome",
        steps=[
            {"action": "monitor"},
            {"action": "require_approval", "reason": "Pause for review"},
        ],
    )

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "awaiting_approval"
    row = playbook_store.get_playbook_execution(conn, eid)
    approval_id = row["steps_log"][1]["approval_request_id"]
    events = _fetch_playbook_outcome_events(cur, eid)
    awaiting = [event for event in events if event[0] == "awaiting_approval"][0]
    assert awaiting[1:9] == (
        "internal",
        "awaiting_approval",
        "playbook_worker",
        "approval_required",
        False,
        False,
        False,
        f"playbook-awaiting-approval-{eid}-1-{approval_id}",
    )
    assert awaiting[10] == 1
    assert awaiting[13] == approval_id
    assert awaiting[14]["approval_request_id"] == approval_id


def test_approved_playbook_approval_appends_decision_and_resumed_events(postgres_db):
    conn, cur = postgres_db
    user_id = _insert_user(cur)
    eid, _decision = _create_linked_execution(
        conn,
        cur,
        "pb_approved_outcome",
        steps=[
            {"action": "require_approval", "reason": "Approve continuation"},
            {"action": "monitor"},
        ],
    )
    playbook_step_executor.process_playbook_execution(conn, eid)
    approval_id = playbook_store.get_playbook_execution(conn, eid)["steps_log"][0][
        "approval_request_id"
    ]
    approval_store.approve_request(conn, approval_id, actor_user_id=user_id)

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    events = _fetch_playbook_outcome_events(cur, eid)
    approved = [event for event in events if event[0] == "approval_approved"][0]
    resumed = [event for event in events if event[0] == "resumed"][0]
    assert approved[1:9] == (
        "internal",
        "running",
        "approval_service",
        "approval_required",
        False,
        False,
        False,
        f"playbook-approval_approved-{eid}-{approval_id}",
    )
    assert approved[10] == 0
    assert approved[13] == approval_id
    assert approved[14]["approval_request_event_id"] is not None
    assert resumed[3] == "playbook_worker"
    assert resumed[13] == approval_id
    assert resumed[8] == f"playbook-resumed-{eid}-{approval_id}"


def test_denied_playbook_approval_appends_blocked_approval_event(postgres_db):
    conn, cur = postgres_db
    user_id = _insert_user(cur)
    eid, _decision = _create_linked_execution(
        conn,
        cur,
        "pb_denied_outcome",
        steps=[
            {"action": "require_approval", "reason": "Approve continuation"},
            {"action": "monitor"},
        ],
    )
    playbook_step_executor.process_playbook_execution(conn, eid)
    approval_id = playbook_store.get_playbook_execution(conn, eid)["steps_log"][0][
        "approval_request_id"
    ]
    approval_store.deny_request(conn, approval_id, actor_user_id=user_id)

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    events = _fetch_playbook_outcome_events(cur, eid)
    denied = [event for event in events if event[0] == "approval_denied"][0]
    assert denied[1:9] == (
        "internal",
        "blocked",
        "approval_service",
        "approval_denied",
        False,
        False,
        False,
        f"playbook-approval_denied-{eid}-{approval_id}",
    )
    assert denied[10] == 0
    assert denied[13] == approval_id
    assert denied[14]["approval_request_event_id"] is not None


def test_expired_playbook_approval_appends_blocked_approval_event(postgres_db):
    conn, cur = postgres_db
    now = datetime.now(timezone.utc)
    eid, _decision = _create_linked_execution(
        conn,
        cur,
        "pb_expired_outcome",
        steps=[
            {"action": "require_approval", "expires_in_minutes": 5},
            {"action": "monitor"},
        ],
    )
    playbook_step_executor.process_playbook_execution(conn, eid, now=now)
    approval_id = playbook_store.get_playbook_execution(conn, eid)["steps_log"][0][
        "approval_request_id"
    ]

    result = playbook_step_executor.process_playbook_execution(
        conn,
        eid,
        now=now + timedelta(minutes=10),
    )

    assert result["outcome"] == "failed"
    events = _fetch_playbook_outcome_events(cur, eid)
    expired = [event for event in events if event[0] == "approval_expired"][0]
    assert expired[1:9] == (
        "internal",
        "blocked",
        "approval_service",
        "approval_expired",
        False,
        False,
        False,
        f"playbook-approval_expired-{eid}-{approval_id}",
    )
    assert expired[10] == 0
    assert expired[13] == approval_id
    assert expired[14]["approval_request_event_id"] is not None


def test_playbook_approval_event_write_failure_preserves_legacy_behavior(
    postgres_db, monkeypatch, caplog
):
    conn, cur = postgres_db
    eid, _decision = _create_linked_execution(
        conn,
        cur,
        "pb_approval_outcome_failure",
        steps=[{"action": "require_approval"}],
    )

    def fail_append(*_args, **_kwargs):
        raise RuntimeError("canonical writer unavailable")

    monkeypatch.setattr("engines.playbook_step_executor.append_outcome_event", fail_append)

    with caplog.at_level("ERROR"):
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "awaiting_approval"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "awaiting_approval"
    assert _fetch_playbook_outcome_events(cur, eid) == []
    assert "Failed to append canonical awaiting_approval outcome" in caplog.text


def test_multiple_supported_steps_are_simulated_successfully(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(
        conn,
        cur,
        "pb_multi",
        steps=[
            {"action": "monitor", "params": {}},
            {"action": "flag_high_priority", "params": {}},
            {"action": "block_ip", "params": {}},
        ],
    )

    result = playbook_step_executor.process_next_pending_playbook_execution(conn)

    assert result["outcome"] == "success"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "success"
    assert row["last_completed_step"] == 2
    assert [entry["action"] for entry in row["steps_log"]] == [
        "monitor",
        "flag_high_priority",
        "block_ip",
    ]
    for entry in row["steps_log"]:
        assert entry["error"] is None
        if entry["action"] in {"monitor", "flag_high_priority"}:
            assert entry["output"]["executed"] is True
            assert entry["output"].get("canonical_response") is True
        else:
            assert entry["output"]["simulated"] is True


def test_adapter_backed_steps_are_simulated_through_registry(postgres_db, no_network):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_adapter_steps")
    _set_playbook_steps(
        cur,
        "pb_adapter_steps",
        [
            {"action": "notify_slack", "params": {"message": "hello", "token": "secret"}},
            {"action": "notify_email", "params": {"subject": "alert", "password": "secret"}},
            {"action": "block_ip", "params": {"source_ip": "203.0.113.10"}},
            {"action": "notify_webhook", "params": {"payload": {"event": "alert"}}},
        ],
    )
    before = {
        "blocked_ips": _count(cur, "blocked_ips"),
        "response_actions_queue": _count(cur, "response_actions_queue"),
    }

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "success"
    assert row["last_completed_step"] == 3
    expected = [
        ("notify_slack", "slack", "send_message"),
        ("notify_email", "email", "send_email"),
        ("block_ip", "firewall", "block_ip"),
        ("notify_webhook", "webhook", "post_event"),
    ]
    for entry, (step_action, adapter_name, adapter_action) in zip(row["steps_log"], expected):
        assert entry["action"] == step_action
        assert entry["status"] == "success"
        assert entry["mode"] == "simulation"
        assert entry["simulated"] is True
        assert entry["executed"] is False
        assert entry["output"]["simulated"] is True
        assert entry["output"]["executed"] is False
        adapter_result = entry["output"]["adapter_result"]
        assert adapter_result["adapter"] == adapter_name
        assert adapter_result["action"] == adapter_action
        assert adapter_result["mode"] == "simulation"
        assert adapter_result["simulated"] is True
        assert adapter_result["executed"] is False
        assert adapter_result["success"] is True
        assert adapter_result["context"]["execution_id"] == eid
        assert adapter_result["context"]["playbook_id"] == "pb_adapter_steps"
        assert entry["output"]["circuit_breaker"]["state"] == CIRCUIT_STATE_CLOSED

    assert row["steps_log"][0]["output"]["adapter_result"]["params"]["token"] == "[redacted]"
    assert row["steps_log"][1]["output"]["adapter_result"]["params"]["password"] == "[redacted]"
    assert _count(cur, "blocked_ips") == before["blocked_ips"]
    assert _count(cur, "response_actions_queue") == before["response_actions_queue"]


def test_block_ip_step_rejects_protected_target_before_adapter_dispatch(
    postgres_db, monkeypatch, no_network
):
    conn, cur = postgres_db
    protected_ip = "203.0.113.10"
    eid = _create_execution(
        conn,
        cur,
        "pb_protected_block",
        steps=[{"action": "block_ip", "params": {"source_ip": protected_ip}}],
    )
    monkeypatch.setenv("SOAR_PROTECTED_IPS", protected_ip)

    def fail_adapter(*_args, **_kwargs):
        raise AssertionError("adapter dispatch should not be reached")

    monkeypatch.setattr(
        "engines.playbook_step_executor.execute_playbook_simulated_adapter",
        fail_adapter,
    )

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "failed"
    entry = row["steps_log"][0]
    assert entry["action"] == "block_ip"
    assert entry["status"] == "failed"
    assert entry["error"]["code"] == "protected_target"
    assert "protected target" in entry["message"].lower()


def test_block_ip_step_resolves_dynamic_source_ip_from_alert(postgres_db, no_network):
    conn, cur = postgres_db
    offender_ip = "198.51.100.77"
    aid = _insert_alert(cur, source_ip=offender_ip)
    playbook_store.create_playbook_definition(
        conn,
        "pb_dynamic_block",
        "pb_dynamic_block",
        steps=[{"action": "block_ip", "params": {"source_ip": "{{alert.source_ip}}"}}],
    )
    eid = playbook_store.create_pending_playbook_execution_once(conn, "pb_dynamic_block", aid)

    captured = {}

    def capture_adapter(*_args, **kwargs):
        captured["params"] = kwargs.get("params")
        return {
            "adapter": "firewall",
            "action": "block_ip",
            "mode": "simulation",
            "simulated": True,
            "executed": False,
            "success": True,
            "message": "Simulated block completed.",
            "params": kwargs.get("params") or {},
            "context": kwargs.get("context") or {},
            "metadata": {},
        }

    with patch(
        "engines.playbook_step_executor.execute_playbook_simulated_adapter",
        side_effect=capture_adapter,
    ):
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    assert captured["params"]["source_ip"] == offender_ip
    row = playbook_store.get_playbook_execution(conn, eid)
    entry = row["steps_log"][0]
    assert entry["output"]["resolved_params"]["source_ip"] == offender_ip


def test_block_ip_step_rejects_protected_target_after_dynamic_resolution(
    postgres_db, monkeypatch, no_network
):
    conn, cur = postgres_db
    protected_ip = "203.0.113.10"
    aid = _insert_alert(cur, source_ip=protected_ip)
    playbook_store.create_playbook_definition(
        conn,
        "pb_dynamic_protected_block",
        "pb_dynamic_protected_block",
        steps=[{"action": "block_ip", "params": {"source_ip": "{{alert.source_ip}}"}}],
    )
    eid = playbook_store.create_pending_playbook_execution_once(
        conn, "pb_dynamic_protected_block", aid
    )
    monkeypatch.setenv("SOAR_PROTECTED_IPS", protected_ip)

    def fail_adapter(*_args, **_kwargs):
        raise AssertionError("adapter dispatch should not be reached")

    monkeypatch.setattr(
        "engines.playbook_step_executor.execute_playbook_simulated_adapter",
        fail_adapter,
    )

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    row = playbook_store.get_playbook_execution(conn, eid)
    entry = row["steps_log"][0]
    assert entry["error"]["code"] == "protected_target"


def test_adapter_step_fails_on_missing_nullable_binding_field(postgres_db, no_network):
    conn, cur = postgres_db
    aid = _insert_alert(cur)
    playbook_store.create_playbook_definition(
        conn,
        "pb_missing_binding",
        "pb_missing_binding",
        steps=[{"action": "notify_slack", "params": {"message": "{{alert.reputation_score}}"}}],
    )
    eid = playbook_store.create_pending_playbook_execution_once(conn, "pb_missing_binding", aid)

    def fail_adapter(*_args, **_kwargs):
        raise AssertionError("adapter dispatch should not be reached")

    with patch(
        "engines.playbook_step_executor.execute_playbook_simulated_adapter",
        side_effect=fail_adapter,
    ):
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    row = playbook_store.get_playbook_execution(conn, eid)
    entry = row["steps_log"][0]
    assert entry["error"]["code"] == "binding_field_missing"


def test_adapter_failure_marks_step_failed_and_respects_continue(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_adapter_failure")
    _set_playbook_steps(
        cur,
        "pb_adapter_failure",
        [
            {"action": "notify_slack", "on_failure": "continue"},
            {"action": "monitor", "params": {}},
        ],
    )

    failing_result = {
        "adapter": "slack",
        "action": "send_message",
        "mode": "simulation",
        "simulated": True,
        "executed": False,
        "success": False,
        "message": "Simulated adapter failure.",
        "params": {},
        "context": {},
        "metadata": {},
    }

    with patch(
        "engines.playbook_step_executor.execute_playbook_simulated_adapter",
        return_value=failing_result,
    ):
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "failed"
    assert row["last_completed_step"] == 1
    assert [entry["status"] for entry in row["steps_log"]] == ["failed", "success"]
    failed = row["steps_log"][0]
    assert failed["output"]["adapter_result"]["success"] is False
    assert failed["output"]["adapter_result"]["simulated"] is True
    assert failed["output"]["adapter_result"]["executed"] is False
    assert "circuit_breaker" in failed["output"]
    assert failed["error"]["code"] == "adapter_simulation_failed"

    dead_letters = dead_letter_store.list_dead_letters(
        conn, source_type="playbook_execution", execution_id=eid
    )
    assert len(dead_letters) == 1
    dead_letter = dead_letters[0]
    assert dead_letter["source_id"] == eid
    assert dead_letter["execution_id"] == eid
    assert dead_letter["alert_id"] == row["alert_id"]
    assert dead_letter["playbook_id"] == "pb_adapter_failure"
    assert dead_letter["step_index"] == 0
    assert dead_letter["action_name"] == "notify_slack"
    assert dead_letter["failure_class"] == "adapter_simulation_failed"
    assert dead_letter["error_message"] == "Simulated adapter failure."
    assert dead_letter["payload_json"]["source"] == "playbook_step_executor"
    assert dead_letter["payload_json"]["step"]["error"]["code"] == "adapter_simulation_failed"


def test_non_simulation_integration_mode_fails_closed(postgres_db, monkeypatch, no_network):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_adapter_real_mode")
    _set_playbook_steps(cur, "pb_adapter_real_mode", [{"action": "notify_slack"}])
    monkeypatch.setenv("INTEGRATION_MODE", "real")

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    row = playbook_store.get_playbook_execution(conn, eid)
    entry = row["steps_log"][0]
    assert entry["status"] == "failed"
    assert entry["error"]["code"] == "adapter_simulation_failed"
    assert "real mode failed closed" in entry["message"]
    assert "SOAR_ENV" in entry["message"]
    assert entry["output"]["simulated"] is True
    assert entry["output"]["executed"] is False
    assert "circuit_breaker" in entry["output"]
    assert _count(cur, "blocked_ips") == 0
    assert _count(cur, "response_actions_queue") == 0


def test_failed_playbook_step_sanitizes_dead_letter_message_and_payload(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_dead_letter_sanitize")
    _set_playbook_steps(cur, "pb_dead_letter_sanitize", [{"action": "notify_slack"}])

    failing_result = {
        "adapter": "slack",
        "action": "send_message",
        "mode": "simulation",
        "simulated": True,
        "executed": False,
        "success": False,
        "message": "failed webhook https://hooks.slack.com/services/secret",
        "params": {"token": "secret-token", "channel": "#soc"},
        "context": {},
        "metadata": {
            "failure_classification": FAILURE_CLASSIFICATION_TRANSIENT,
            "webhook_url": "https://hooks.slack.com/services/secret",
            "safe_label": "soc",
            "callback": "https://example.test/callback",
        },
    }

    with patch(
        "engines.playbook_step_executor.execute_playbook_simulated_adapter",
        return_value=failing_result,
    ):
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    [dead_letter] = dead_letter_store.list_dead_letters(conn, execution_id=eid)
    assert dead_letter["failure_class"] == FAILURE_CLASSIFICATION_TRANSIENT
    assert dead_letter["error_message"] == "failed webhook [REDACTED_URL]"

    step_payload = dead_letter["payload_json"]["step"]
    adapter_result = step_payload["output"]["adapter_result"]
    assert adapter_result["params"] == {"channel": "#soc"}
    assert adapter_result["metadata"]["safe_label"] == "soc"
    assert adapter_result["metadata"]["callback"] == "[REDACTED_URL]"
    assert "webhook_url" not in adapter_result["metadata"]


def test_repeated_failed_execution_does_not_create_duplicate_active_dead_letter(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(
        conn,
        cur,
        "pb_dead_letter_idempotent",
        steps=[{"action": "notify_slack"}],
    )
    failing_result = {
        "adapter": "slack",
        "action": "send_message",
        "mode": "simulation",
        "simulated": True,
        "executed": False,
        "success": False,
        "message": "repeatable simulated failure",
        "params": {},
        "context": {},
        "metadata": {},
    }

    with patch(
        "engines.playbook_step_executor.execute_playbook_simulated_adapter",
        return_value=failing_result,
    ):
        first = playbook_step_executor.process_playbook_execution(conn, eid)
    assert first["outcome"] == "failed"
    first_dead_letters = dead_letter_store.list_dead_letters(conn, execution_id=eid)
    assert len(first_dead_letters) == 1

    cur.execute(
        """
        UPDATE playbook_executions
        SET status = 'pending',
            completed_at = NULL,
            lease_owner = NULL,
            lease_acquired_at = NULL,
            lease_heartbeat_at = NULL,
            lease_expires_at = NULL
        WHERE id = %s
        """,
        (eid,),
    )

    with patch(
        "engines.playbook_step_executor.execute_playbook_simulated_adapter",
        return_value=failing_result,
    ):
        second = playbook_step_executor.process_playbook_execution(conn, eid)
    assert second["outcome"] == "failed"
    second_dead_letters = dead_letter_store.list_dead_letters(conn, execution_id=eid)
    assert len(second_dead_letters) == 1
    assert second_dead_letters[0]["id"] == first_dead_letters[0]["id"]


def test_playbook_notify_slack_open_circuit_fails_closed_without_simulate(
    postgres_db, no_network
):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_cb_open")
    _set_playbook_steps(cur, "pb_cb_open", [{"action": "notify_slack", "params": {}}])
    configure_simulated_circuit_breaker(
        "slack",
        state=CIRCUIT_STATE_OPEN,
        consecutive_failures=3,
    )

    with patch.object(
        SlackSimulationAdapter,
        "_simulate",
        side_effect=AssertionError("simulation body must not run when circuit is open"),
    ):
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    row = playbook_store.get_playbook_execution(conn, eid)
    entry = row["steps_log"][0]
    assert entry["status"] == "failed"
    assert entry["error"]["code"] == "circuit_breaker_open"
    assert entry["output"]["circuit_breaker"]["state"] == CIRCUIT_STATE_OPEN
    meta = entry["output"]["adapter_result"]["metadata"]
    assert meta["failure_classification"] == "circuit_open"
    assert _count(cur, "blocked_ips") == 0
    assert _count(cur, "response_actions_queue") == 0


def test_playbook_notify_slack_half_open_success_closes_circuit(postgres_db, no_network):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_cb_half_ok")
    _set_playbook_steps(cur, "pb_cb_half_ok", [{"action": "notify_slack", "params": {}}])
    t0 = datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc)
    configure_simulated_circuit_breaker(
        "slack",
        state=CIRCUIT_STATE_HALF_OPEN,
        consecutive_failures=2,
        cooldown_until=t0,
    )

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["steps_log"][0]["status"] == "success"
    assert get_simulated_circuit_breaker_dict("slack")["state"] == CIRCUIT_STATE_CLOSED
    assert row["steps_log"][0]["output"]["circuit_breaker"]["state"] == CIRCUIT_STATE_CLOSED


def test_playbook_notify_slack_half_open_failure_reopens_circuit(postgres_db, no_network):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_cb_half_fail")
    _set_playbook_steps(cur, "pb_cb_half_fail", [{"action": "notify_slack", "params": {}}])
    t0 = datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc)
    configure_simulated_circuit_breaker(
        "slack",
        state=CIRCUIT_STATE_HALF_OPEN,
        consecutive_failures=2,
        cooldown_until=t0,
    )

    def _failing_probe(adapter_self, action, params, context):
        return adapter_self._result(
            action,
            params,
            context,
            success=False,
            message="simulated outage",
            metadata={"failure_classification": FAILURE_CLASSIFICATION_TRANSIENT},
        )

    with patch.object(SlackSimulationAdapter, "_simulate", _failing_probe):
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["steps_log"][0]["status"] == "failed"
    assert get_simulated_circuit_breaker_dict("slack")["state"] == CIRCUIT_STATE_OPEN
    assert row["steps_log"][0]["error"]["code"] == "circuit_breaker_open"


def test_require_approval_pauses_execution_and_creates_linked_request(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(
        conn,
        cur,
        "pb_approval_gate",
        steps=[
            {"action": "monitor", "params": {}},
            {
                "action": "require_approval",
                "risk_level": "critical",
                "reason": "Approve simulated block before continuing",
                "expires_in_minutes": 20,
            },
            {"action": "block_ip", "params": {}},
        ],
    )

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "awaiting_approval"
    assert result["new_status"] == "awaiting_approval"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "awaiting_approval"
    assert row["completed_at"] is None
    assert row["last_completed_step"] == 0
    assert [entry["action"] for entry in row["steps_log"]] == ["monitor", "require_approval"]

    approval_entry = row["steps_log"][1]
    assert approval_entry["event"] == "approval_requested"
    assert approval_entry["status"] == "awaiting_approval"
    assert approval_entry["mode"] == "internal"
    assert approval_entry["simulated"] is False
    assert approval_entry["executed"] is True
    assert approval_entry["output"] == {
        "simulated": False,
        "executed": True,
        "approval_gate": True,
    }
    assert approval_entry["approval_status"] == "pending"
    assert approval_entry["risk_level"] == "critical"
    assert "Approve simulated block" in approval_entry["message"]

    cur.execute(
        """
        SELECT id, playbook_execution_id, playbook_step_index, status, action, risk_level,
               request_reason
        FROM approval_requests
        WHERE playbook_execution_id = %s
        """,
        (eid,),
    )
    approvals = cur.fetchall()
    assert len(approvals) == 1
    approval = approvals[0]
    assert approval[0] == approval_entry["approval_request_id"]
    assert approval[1] == eid
    assert approval[2] == 1
    assert approval[3] == "pending"
    assert approval[4] == "playbook.require_approval"
    assert approval[5] == "critical"
    assert approval[6] == "Approve simulated block before continuing"

    assert _count(cur, "response_actions_queue") == 0
    assert _count(cur, "soar_dead_letters") == 0
    # Canonical monitor step records a response_actions_log row via the shared command service.
    assert _count(cur, "response_actions_log") >= 1
    conn, cur = postgres_db
    eid = _create_execution(
        conn,
        cur,
        "pb_approval_rerun",
        steps=[
            {"action": "require_approval", "reason": "Pause here"},
            {"action": "monitor", "params": {}},
        ],
    )

    first = playbook_step_executor.process_playbook_execution(conn, eid)
    before = playbook_store.get_playbook_execution(conn, eid)
    second = playbook_step_executor.process_playbook_execution(conn, eid)
    after = playbook_store.get_playbook_execution(conn, eid)

    assert first["outcome"] == "awaiting_approval"
    assert second["outcome"] == "skipped"
    assert second["reason"] == "approval_pending"
    assert after["status"] == "awaiting_approval"
    assert after["steps_log"] == before["steps_log"]

    cur.execute(
        """
        SELECT COUNT(*)
        FROM approval_requests
        WHERE playbook_execution_id = %s AND playbook_step_index = 0
        """,
        (eid,),
    )
    assert cur.fetchone()[0] == 1


def test_approved_approval_resumes_from_next_step(postgres_db):
    conn, cur = postgres_db
    user_id = _insert_user(cur)
    eid = _create_execution(
        conn,
        cur,
        "pb_approval_resume",
        steps=[
            {"action": "monitor", "params": {}},
            {"action": "require_approval", "reason": "Approve next simulated step"},
            {"action": "block_ip", "params": {}},
        ],
    )
    pause = playbook_step_executor.process_playbook_execution(conn, eid)
    approval_id = playbook_store.get_playbook_execution(conn, eid)["steps_log"][1][
        "approval_request_id"
    ]
    approval_store.approve_request(conn, approval_id, actor_user_id=user_id)

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert pause["outcome"] == "awaiting_approval"
    assert result["outcome"] == "success"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "success"
    assert row["last_completed_step"] == 2
    events = [entry.get("event") for entry in row["steps_log"]]
    assert events == [
        None,
        "approval_requested",
        "approval_approved",
        "approval_resumed",
        None,
    ]
    assert row["steps_log"][-1]["action"] == "block_ip"
    assert row["steps_log"][-1]["output"]["simulated"] is True
    assert row["steps_log"][-1]["output"]["executed"] is False
    assert row["steps_log"][-1]["output"]["adapter_result"]["adapter"] == "firewall"
    assert _count(cur, "response_actions_queue") == 0
    # Monitor step records through the canonical response command service.
    assert _count(cur, "response_actions_log") >= 1

    rerun = playbook_step_executor.process_playbook_execution(conn, eid)
    assert rerun["outcome"] == "skipped"
    assert rerun["reason"] == "terminal_status"


def test_denied_approval_fails_and_skips_later_steps(postgres_db):
    conn, cur = postgres_db
    user_id = _insert_user(cur)
    eid = _create_execution(
        conn,
        cur,
        "pb_approval_denied",
        steps=[
            {"action": "require_approval", "reason": "Approve later steps"},
            {"action": "block_ip", "params": {}},
            {"action": "monitor", "params": {}},
        ],
    )
    playbook_step_executor.process_playbook_execution(conn, eid)
    approval_id = playbook_store.get_playbook_execution(conn, eid)["steps_log"][0][
        "approval_request_id"
    ]
    approval_store.deny_request(conn, approval_id, actor_user_id=user_id)

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "failed"
    assert row["last_completed_step"] is None
    assert [entry.get("event") for entry in row["steps_log"]] == [
        "approval_requested",
        "approval_denied",
        "skipped_after_approval_gate",
        "skipped_after_approval_gate",
    ]
    skipped = row["steps_log"][2:]
    assert [entry["action"] for entry in skipped] == ["block_ip", "monitor"]
    assert all(entry["status"] == "skipped" for entry in skipped)
    assert all(entry["output"]["executed"] is False for entry in skipped)
    assert _count(cur, "response_actions_queue") == 0


def test_expired_approval_fails_and_skips_later_steps(postgres_db):
    conn, cur = postgres_db
    now = datetime.now(timezone.utc)
    eid = _create_execution(
        conn,
        cur,
        "pb_approval_expired",
        steps=[
            {"action": "require_approval", "expires_in_minutes": 5},
            {"action": "block_ip", "params": {}},
        ],
    )
    playbook_step_executor.process_playbook_execution(conn, eid, now=now)

    result = playbook_step_executor.process_playbook_execution(
        conn,
        eid,
        now=now + timedelta(minutes=10),
    )

    assert result["outcome"] == "failed"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "failed"
    assert [entry.get("event") for entry in row["steps_log"]] == [
        "approval_requested",
        "approval_expired",
        "skipped_after_approval_gate",
    ]
    assert row["steps_log"][2]["action"] == "block_ip"
    assert row["steps_log"][2]["status"] == "skipped"
    cur.execute(
        "SELECT status FROM approval_requests WHERE playbook_execution_id = %s",
        (eid,),
    )
    assert cur.fetchone()[0] == "expired"


def test_batch_processes_approved_awaiting_approval_execution(postgres_db):
    conn, cur = postgres_db
    user_id = _insert_user(cur)
    eid = _create_execution(
        conn,
        cur,
        "pb_batch_approval_resume",
        steps=[
            {"action": "require_approval", "reason": "Approve batch resume"},
            {"action": "monitor", "params": {}},
        ],
    )
    playbook_step_executor.process_playbook_execution(conn, eid)
    approval_id = playbook_store.get_playbook_execution(conn, eid)["steps_log"][0][
        "approval_request_id"
    ]
    approval_store.approve_request(conn, approval_id, actor_user_id=user_id)

    result = playbook_step_executor.process_playbook_execution_batch(conn, limit=5)

    assert result["processed"] == 1
    assert result["success"] == 1
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "success"
    assert row["steps_log"][-1]["action"] == "monitor"


def test_unsupported_step_action_marks_execution_failed(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_bad")
    cur.execute(
        "UPDATE playbook_definitions SET steps = %s::jsonb WHERE id = %s",
        ('[{"action": "bad_action", "params": {}}]', "pb_bad"),
    )

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "failed"
    assert row["last_completed_step"] is None
    assert row["steps_log"][0]["status"] == "failed"
    assert row["steps_log"][0]["error"]["code"] == "unsupported_action"
    assert row["steps_log"][0]["mode"] == "internal"
    assert row["steps_log"][0]["output"]["simulated"] is False
    assert row["steps_log"][0]["output"]["executed"] is False


def test_on_failure_continue_records_later_success_but_execution_failed(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_continue")
    cur.execute(
        "UPDATE playbook_definitions SET steps = %s::jsonb WHERE id = %s",
        (
            '[{"action": "bad_action", "on_failure": "continue"}, {"action": "monitor"}]',
            "pb_continue",
        ),
    )

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "failed"
    assert row["last_completed_step"] == 1
    assert [entry["status"] for entry in row["steps_log"]] == ["failed", "success"]


def test_invalid_steps_root_marks_execution_failed(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_invalid_steps")

    with patch(
        "engines.playbook_step_executor.playbook_store.get_playbook_definition",
        return_value={"id": "pb_invalid_steps", "steps": {"not": "a-list"}},
    ):
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "failed"
    assert row["steps_log"][0]["error"]["code"] == "invalid_steps"


def test_missing_definition_marks_execution_failed(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_missing")

    with patch(
        "engines.playbook_step_executor.playbook_store.get_playbook_definition",
        return_value=None,
    ):
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "failed"
    assert row["steps_log"][0]["error"]["code"] == "definition_not_found"


def test_terminal_success_execution_is_not_rerun(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_done")
    playbook_step_executor.process_playbook_execution(conn, eid)
    before = playbook_store.get_playbook_execution(conn, eid)

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    after = playbook_store.get_playbook_execution(conn, eid)
    assert result["outcome"] == "skipped"
    assert result["reason"] == "terminal_status"
    assert after["steps_log"] == before["steps_log"]
    assert after["status"] == "success"


def test_running_execution_is_skipped(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_running")
    playbook_store.set_playbook_execution_running(conn, eid)

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "skipped"
    assert result["reason"] == "already_running"


def test_batch_processing_respects_limit(postgres_db):
    conn, cur = postgres_db
    first = _create_execution(conn, cur, "pb_one")
    second = _create_execution(conn, cur, "pb_two", steps=[{"action": "flag_high_priority"}])

    result = playbook_step_executor.process_playbook_execution_batch(conn, limit=1)

    assert result["processed"] == 1
    assert result["success"] == 1
    statuses = {
        first: playbook_store.get_playbook_execution(conn, first)["status"],
        second: playbook_store.get_playbook_execution(conn, second)["status"],
    }
    assert sorted(statuses.values()) == ["pending", "success"]


def test_executor_does_not_create_queue_logs_or_approvals(postgres_db):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_no_side_effects", steps=[{"action": "block_ip"}])
    before = {
        "response_actions_queue": _count(cur, "response_actions_queue"),
        "response_actions_log": _count(cur, "response_actions_log"),
        "approval_requests": _count(cur, "approval_requests"),
    }

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    for table, expected in before.items():
        assert _count(cur, table) == expected


def test_executor_module_has_no_real_execution_imports():
    source = inspect.getsource(playbook_step_executor)
    forbidden = [
        "soar_adapters",
        "AdapterBackedExecutor",
        "SimulationExecutor",
        "enqueue_response_action",
        "enqueue_committed_alerts",
        "requests",
        "subprocess",
        "socket",
        "urllib",
    ]
    for token in forbidden:
        assert token not in source


# ---------------------------------------------------------------------------
# Slice 3: notification delivery tracking
# ---------------------------------------------------------------------------


def _count_deliveries(cur, playbook_execution_id):
    cur.execute(
        "SELECT COUNT(*) FROM notification_delivery_attempts WHERE playbook_execution_id = %s",
        (playbook_execution_id,),
    )
    return cur.fetchone()[0]


def _fetch_deliveries(cur, playbook_execution_id):
    cur.execute(
        """
        SELECT provider, mode, status, playbook_step_index,
               adapter_name, action, alert_id, circuit_breaker_state
        FROM notification_delivery_attempts
        WHERE playbook_execution_id = %s
        ORDER BY playbook_step_index
        """,
        (playbook_execution_id,),
    )
    return cur.fetchall()


def _fetch_notification_outcomes(cur, playbook_execution_id):
    cur.execute(
        """
        SELECT event_type, execution_mode, execution_state, execution_actor,
               external_executed, simulated, reason_code,
               notification_delivery_attempt_id, playbook_step_index,
               provider, adapter_name, idempotency_key, metadata
        FROM soar_response_outcome_events
        WHERE playbook_execution_id = %s
          AND event_type = 'notification_delivery'
        ORDER BY id
        """,
        (playbook_execution_id,),
    )
    return cur.fetchall()


def test_notify_slack_step_creates_delivery_record(postgres_db, no_network):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_slack_delivery")
    _set_playbook_steps(
        cur,
        "pb_slack_delivery",
        [{"action": "notify_slack", "params": {"message": "test alert"}}],
    )

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    rows = _fetch_deliveries(cur, eid)
    assert len(rows) == 1
    provider, mode, status, step_idx, adapter_name, action, alert_id, cb_state = rows[0]
    assert provider == "slack"
    assert mode == "simulation"
    assert status == "success"
    assert step_idx == 0
    assert adapter_name == "slack"
    assert action == "send_message"
    assert cb_state == "closed"


def test_simulated_notification_maps_to_simulation_outcome(postgres_db, no_network):
    conn, cur = postgres_db
    eid, _decision = _create_linked_execution(
        conn,
        cur,
        "pb_slack_canonical_sim",
        steps=[{"action": "notify_slack", "params": {"message": "test alert"}}],
    )

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    [outcome] = _fetch_notification_outcomes(cur, eid)
    delivery_id = outcome[7]
    assert outcome[0:7] == (
        "notification_delivery",
        "simulation",
        "succeeded",
        "adapter",
        False,
        True,
        "simulation_mode",
    )
    assert outcome[8] == 0
    assert outcome[9] == "slack"
    assert outcome[10] == "slack"
    assert outcome[11] == f"playbook-notification-{eid}-0-{delivery_id}"


def test_real_success_notification_with_strong_evidence_marks_external_executed(
    postgres_db,
):
    conn, cur = postgres_db
    eid, _decision = _create_linked_execution(
        conn,
        cur,
        "pb_slack_canonical_real",
        steps=[{"action": "notify_slack", "params": {"message": "real alert"}}],
    )
    real_result = {
        "adapter": "slack",
        "action": "send_message",
        "mode": "real",
        "simulated": False,
        "executed": True,
        "success": True,
        "message": "Delivered to Slack.",
        "params": {},
        "context": {},
        "metadata": {"provider_success": True},
    }

    with patch(
        "engines.playbook_step_executor.execute_playbook_simulated_adapter",
        return_value=real_result,
    ):
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    row = playbook_store.get_playbook_execution(conn, eid)
    entry = row["steps_log"][0]
    assert entry["mode"] == "real"
    assert entry["simulated"] is False
    assert entry["executed"] is True
    assert entry["message"] == "Delivered to Slack."
    assert entry["output"]["notification_delivery"]["mode"] == "real"
    assert entry["output"]["notification_delivery"]["status"] == "success"
    [outcome] = _fetch_notification_outcomes(cur, eid)
    assert outcome[1:7] == ("real", "succeeded", "adapter", True, False, None)
    assert outcome[12]["real_evidence"] is True


def test_real_guard_blocked_notification_is_not_reported_as_provider_failure(
    postgres_db,
):
    conn, cur = postgres_db
    eid, _decision = _create_linked_execution(
        conn,
        cur,
        "pb_slack_guard_blocked",
        steps=[{"action": "notify_slack", "params": {"message": "real alert"}}],
    )
    blocked_result = {
        "adapter": "slack",
        "action": "send_message",
        "mode": "real",
        "simulated": True,
        "executed": False,
        "success": False,
        "message": "blocked: slack real mode requires guard(s): SLACK_WEBHOOK_URL",
        "params": {},
        "context": {},
        "metadata": {"failure_classification": FAILURE_CLASSIFICATION_GUARD_FAILED},
    }

    with patch(
        "engines.playbook_step_executor.execute_playbook_simulated_adapter",
        return_value=blocked_result,
    ):
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    row = playbook_store.get_playbook_execution(conn, eid)
    entry = row["steps_log"][0]
    assert entry["mode"] == "real"
    assert entry["simulated"] is True
    assert entry["executed"] is False
    assert entry["output"]["notification_delivery"]["status"] == "blocked"
    assert entry["output"]["notification_delivery"]["mode"] == "real"
    rows = _fetch_deliveries(cur, eid)
    assert rows[0][2] == "blocked"
    [outcome] = _fetch_notification_outcomes(cur, eid)
    assert outcome[1:7] == ("real", "blocked", "adapter", False, False, "policy_blocked")


def test_real_success_missing_simulated_false_does_not_mark_external_executed(
    postgres_db,
):
    conn, cur = postgres_db
    eid, _decision = _create_linked_execution(
        conn,
        cur,
        "pb_slack_missing_simulated_false",
        steps=[{"action": "notify_slack"}],
    )
    real_result = {
        "adapter": "slack",
        "action": "send_message",
        "mode": "real",
        "executed": True,
        "success": True,
        "message": "Delivered to Slack.",
        "params": {},
        "context": {},
        "metadata": {"provider_success": True},
    }

    with patch(
        "engines.playbook_step_executor.execute_playbook_simulated_adapter",
        return_value=real_result,
    ):
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    [outcome] = _fetch_notification_outcomes(cur, eid)
    assert outcome[1:7] == (
        "simulation",
        "succeeded",
        "adapter",
        False,
        True,
        "simulation_mode",
    )
    assert outcome[12]["real_evidence"] is False


def test_real_success_missing_provider_evidence_does_not_mark_external_executed(
    postgres_db,
):
    conn, cur = postgres_db
    eid, _decision = _create_linked_execution(
        conn,
        cur,
        "pb_slack_missing_provider_evidence",
        steps=[{"action": "notify_slack"}],
    )
    execution = playbook_store.get_playbook_execution(conn, eid)
    delivery = notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id=f"missing-evidence-{eid}",
        idempotency_key=f"missing-evidence-{eid}",
        provider="slack",
        mode="real",
        status="success",
        adapter_name="slack",
        action="send_message",
        metadata={"executed": True, "simulated": False},
        playbook_execution_id=eid,
        playbook_step_index=0,
        alert_id=execution["alert_id"],
    )

    playbook_step_executor._append_notification_delivery_outcome_event(
        conn,
        execution,
        delivery,
    )

    [outcome] = _fetch_notification_outcomes(cur, eid)
    assert outcome[1:7] == (
        "simulation",
        "succeeded",
        "adapter",
        False,
        True,
        "simulation_mode",
    )
    assert outcome[12]["real_evidence"] is False


def test_notify_teams_step_creates_delivery_record(postgres_db, no_network):
    conn, cur = postgres_db
    eid = _create_execution(
        conn,
        cur,
        "pb_teams_delivery",
        steps=[{"action": "notify_teams", "params": {"message": "test alert"}}],
    )

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    rows = _fetch_deliveries(cur, eid)
    assert len(rows) == 1
    provider, mode, status, step_idx, adapter_name, action, _alert_id, cb_state = rows[0]
    assert provider == "teams"
    assert mode == "simulation"
    assert status == "success"
    assert step_idx == 0
    assert adapter_name == "teams"
    assert action == "send_message"
    assert cb_state == "closed"


def test_notify_email_step_creates_delivery_record(postgres_db, no_network):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_email_delivery")
    _set_playbook_steps(
        cur,
        "pb_email_delivery",
        [{"action": "notify_email", "params": {"subject": "test alert"}}],
    )

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    rows = _fetch_deliveries(cur, eid)
    assert len(rows) == 1
    provider, mode, status, step_idx, adapter_name, action, _alert_id, cb_state = rows[0]
    assert provider == "email"
    assert mode == "simulation"
    assert status == "success"
    assert step_idx == 0
    assert adapter_name == "email"
    assert action == "send_email"
    assert cb_state == "closed"


def test_non_notification_steps_do_not_create_delivery_records(postgres_db, no_network):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_no_delivery")
    _set_playbook_steps(
        cur,
        "pb_no_delivery",
        [
            {"action": "monitor"},
            {"action": "block_ip", "params": {"source_ip": "203.0.113.10"}},
        ],
    )

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    assert _count_deliveries(cur, eid) == 0


def test_firewall_playbook_adapter_remains_simulation_dry_run(postgres_db, no_network):
    conn, cur = postgres_db
    eid, _decision = _create_linked_execution(
        conn,
        cur,
        "pb_firewall_dry_run_outcome",
        steps=[{"action": "block_ip", "params": {"source_ip": "203.0.113.10"}}],
    )

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    assert _count_deliveries(cur, eid) == 0
    row = playbook_store.get_playbook_execution(conn, eid)
    entry = row["steps_log"][0]
    assert entry["action"] == "block_ip"
    assert entry["mode"] == "simulation"
    assert entry["output"]["adapter_result"]["adapter"] == "firewall"
    assert entry["output"]["adapter_result"]["mode"] == "simulation"
    assert entry["output"]["adapter_result"]["executed"] is False
    assert entry["output"]["adapter_result"]["simulated"] is True
    events = _fetch_playbook_outcome_events(cur, eid)
    assert _fetch_notification_outcomes(cur, eid) == []
    assert all(event[4] is not True for event in events)
    assert all(event[1] != "real" for event in events)


def test_delivery_tracking_failure_does_not_crash_step(postgres_db, no_network):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_delivery_crash")
    _set_playbook_steps(cur, "pb_delivery_crash", [{"action": "notify_slack", "params": {}}])

    with patch(
        "engines.playbook_step_executor.notification_delivery_store"
        ".create_notification_delivery_attempt",
        side_effect=RuntimeError("simulated delivery store crash"),
    ):
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "success"
    assert row["steps_log"][0]["status"] == "success"


def test_notification_canonical_write_failure_does_not_break_delivery(
    postgres_db, monkeypatch, caplog, no_network
):
    conn, cur = postgres_db
    eid, _decision = _create_linked_execution(
        conn,
        cur,
        "pb_notification_canonical_failure",
        steps=[{"action": "notify_slack", "params": {}}],
    )

    def fail_append(*_args, **_kwargs):
        raise RuntimeError("canonical writer unavailable")

    monkeypatch.setattr("engines.playbook_step_executor.append_outcome_event", fail_append)

    with caplog.at_level("ERROR"):
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    assert _count_deliveries(cur, eid) == 1
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "success"
    assert _fetch_notification_outcomes(cur, eid) == []
    assert "Failed to append canonical notification_delivery outcome" in caplog.text


def test_circuit_blocked_notify_slack_creates_blocked_delivery_record(postgres_db, no_network):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_cb_delivery")
    _set_playbook_steps(cur, "pb_cb_delivery", [{"action": "notify_slack", "params": {}}])
    configure_simulated_circuit_breaker("slack", state=CIRCUIT_STATE_OPEN, consecutive_failures=3)

    with patch.object(
        SlackSimulationAdapter,
        "_simulate",
        side_effect=AssertionError("simulation body must not run when circuit is open"),
    ):
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    rows = _fetch_deliveries(cur, eid)
    assert len(rows) == 1
    provider, mode, status, _step_idx, _adapter, _action, _alert_id, cb_state = rows[0]
    assert provider == "slack"
    assert status == "blocked"
    assert cb_state == "open"


def test_blocked_notification_maps_to_blocked_outcome(postgres_db, no_network):
    conn, cur = postgres_db
    eid, _decision = _create_linked_execution(
        conn,
        cur,
        "pb_blocked_notification_outcome",
        steps=[{"action": "notify_slack", "params": {}}],
    )
    configure_simulated_circuit_breaker("slack", state=CIRCUIT_STATE_OPEN, consecutive_failures=3)

    with patch.object(
        SlackSimulationAdapter,
        "_simulate",
        side_effect=AssertionError("simulation body must not run when circuit is open"),
    ):
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    [outcome] = _fetch_notification_outcomes(cur, eid)
    assert outcome[1:7] == (
        "simulation",
        "blocked",
        "adapter",
        False,
        True,
        "policy_blocked",
    )


def test_notify_slack_and_teams_steps_create_separate_delivery_records(postgres_db, no_network):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_multi_notify")
    _set_playbook_steps(
        cur,
        "pb_multi_notify",
        [
            {"action": "notify_slack", "params": {"message": "slack msg"}},
            {"action": "notify_teams", "params": {"message": "teams msg"}},
        ],
    )

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    rows = _fetch_deliveries(cur, eid)
    assert len(rows) == 2
    assert (rows[0][0], rows[0][3]) == ("slack", 0)
    assert (rows[1][0], rows[1][3]) == ("teams", 1)
    assert all(r[2] == "success" for r in rows)


def test_delivery_record_links_alert_id(postgres_db, no_network):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_slack_alert_link")
    _set_playbook_steps(cur, "pb_slack_alert_link", [{"action": "notify_slack", "params": {}}])
    cur.execute("SELECT alert_id FROM playbook_executions WHERE id = %s", (eid,))
    alert_id = cur.fetchone()[0]

    playbook_step_executor.process_playbook_execution(conn, eid)

    cur.execute(
        "SELECT alert_id FROM notification_delivery_attempts WHERE playbook_execution_id = %s",
        (eid,),
    )
    row = cur.fetchone()
    assert row is not None
    assert row[0] == alert_id


def test_delivery_record_idempotency_key_is_deterministic(postgres_db, no_network):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_idem_key")
    _set_playbook_steps(cur, "pb_idem_key", [{"action": "notify_slack", "params": {}}])

    playbook_step_executor.process_playbook_execution(conn, eid)

    cur.execute(
        "SELECT idempotency_key FROM notification_delivery_attempts "
        "WHERE playbook_execution_id = %s",
        (eid,),
    )
    key = cur.fetchone()[0]
    expected = playbook_step_executor._make_delivery_idempotency_key("slack", "notify_slack", eid, 0)
    assert key == expected


def test_failed_notify_slack_step_creates_failed_delivery_record(postgres_db, no_network):
    conn, cur = postgres_db
    eid = _create_execution(conn, cur, "pb_slack_fail_delivery")
    _set_playbook_steps(cur, "pb_slack_fail_delivery", [{"action": "notify_slack", "params": {}}])

    failing_result = {
        "adapter": "slack",
        "action": "send_message",
        "mode": "simulation",
        "simulated": True,
        "executed": False,
        "success": False,
        "message": "Simulated adapter failure.",
        "params": {},
        "context": {},
        "metadata": {"failure_classification": "transient"},
    }

    with patch(
        "engines.playbook_step_executor.execute_playbook_simulated_adapter",
        return_value=failing_result,
    ):
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    rows = _fetch_deliveries(cur, eid)
    assert len(rows) == 1
    assert rows[0][2] == "failed"


@pytest.mark.parametrize(
    ("failure_classification", "expected_status", "expected_reason"),
    [
        ("transient", "failed", "provider_error"),
        (FAILURE_CLASSIFICATION_TIMEOUT, "timeout", "adapter_unavailable"),
    ],
)
def test_failed_or_timeout_notification_maps_to_failed_outcome(
    postgres_db,
    no_network,
    failure_classification,
    expected_status,
    expected_reason,
):
    conn, cur = postgres_db
    eid, _decision = _create_linked_execution(
        conn,
        cur,
        f"pb_notification_{expected_status}_outcome",
        steps=[{"action": "notify_slack", "params": {}}],
    )
    failing_result = {
        "adapter": "slack",
        "action": "send_message",
        "mode": "simulation",
        "simulated": True,
        "executed": False,
        "success": False,
        "message": "Simulated adapter failure.",
        "params": {},
        "context": {},
        "metadata": {"failure_classification": failure_classification},
    }

    with patch(
        "engines.playbook_step_executor.execute_playbook_simulated_adapter",
        return_value=failing_result,
    ):
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    rows = _fetch_deliveries(cur, eid)
    assert rows[0][2] == expected_status
    [outcome] = _fetch_notification_outcomes(cur, eid)
    assert outcome[1:7] == (
        "simulation",
        "failed",
        "adapter",
        False,
        True,
        expected_reason,
    )


def test_rate_limited_notify_slack_creates_blocked_delivery_record(
    postgres_db, monkeypatch
):
    conn, cur = postgres_db
    eid = _create_execution(
        conn,
        cur,
        "pb_slack_rate_limited_delivery",
        steps=[
            {"action": "notify_slack", "params": {"message": "first"}},
            {"action": "notify_slack", "params": {"message": "second"}},
        ],
    )
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_SLACK_ENABLED", "true")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T000/B000/SECRET")
    monkeypatch.setenv("SLACK_MAX_SENDS_PER_MINUTE", "1")

    with patch(
        "integrations.slack_adapter._post_slack_webhook",
        return_value={"status_code": 200},
    ) as post_mock, patch("core.integration_audit.log_audit_event"):
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "failed"
    assert post_mock.call_count == 1
    cur.execute(
        """
        SELECT status, failure_code, failure_message, metadata
        FROM notification_delivery_attempts
        WHERE playbook_execution_id = %s
        ORDER BY playbook_step_index
        """,
        (eid,),
    )
    rows = cur.fetchall()
    assert len(rows) == 2
    assert rows[0][0] == "success"
    blocked_status, failure_code, failure_message, metadata = rows[1]
    assert blocked_status == "blocked"
    assert failure_code == "adapter_simulation_failed"
    assert metadata["failure_classification"] == FAILURE_CLASSIFICATION_PROVIDER_RATE_LIMITED
    assert metadata["rate_limited"] is True
    assert "hooks.slack.com/services" not in str(metadata)
    assert "SECRET" not in str(metadata)
    assert "hooks.slack.com/services" not in (failure_message or "")


def test_duplicate_successful_delivery_skips_adapter_and_dead_letter(postgres_db, no_network):
    conn, cur = postgres_db
    eid = _create_execution(
        conn,
        cur,
        "pb_slack_delivery_dedup",
        steps=[{"action": "notify_slack", "params": {"message": "already sent"}}],
    )
    cur.execute("SELECT alert_id FROM playbook_executions WHERE id = %s", (eid,))
    alert_id = cur.fetchone()[0]
    notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id=f"existing-success-{eid}-0",
        idempotency_key=playbook_step_executor._make_delivery_idempotency_key(
            "slack", "notify_slack", eid, 0
        ),
        provider="slack",
        mode="simulation",
        status="success",
        adapter_name="slack",
        action="send_message",
        metadata={"adapter_mode": "simulation"},
        playbook_execution_id=eid,
        playbook_step_index=0,
        alert_id=alert_id,
        circuit_breaker_state="closed",
    )
    conn.commit()

    with patch(
        "engines.playbook_step_executor.execute_playbook_simulated_adapter",
        side_effect=AssertionError("duplicate delivery must not execute adapter"),
    ):
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    row = playbook_store.get_playbook_execution(conn, eid)
    entry = row["steps_log"][0]
    assert entry["status"] == "success"
    assert entry["skipped"] is True
    assert entry["output"]["skip_reason"] == "delivery_success"
    assert entry["output"]["failure_classification"] == "duplicate_delivery"
    assert _count_deliveries(cur, eid) == 1
    assert dead_letter_store.list_dead_letters(conn, execution_id=eid) == []


def test_duplicate_in_flight_delivery_skips_adapter(postgres_db, no_network):
    conn, cur = postgres_db
    eid = _create_execution(
        conn,
        cur,
        "pb_slack_delivery_pending_dedup",
        steps=[{"action": "notify_slack", "params": {"message": "already pending"}}],
    )
    cur.execute("SELECT alert_id FROM playbook_executions WHERE id = %s", (eid,))
    alert_id = cur.fetchone()[0]
    notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id=f"existing-pending-{eid}-0",
        idempotency_key=playbook_step_executor._make_delivery_idempotency_key(
            "slack", "notify_slack", eid, 0
        ),
        provider="slack",
        mode="simulation",
        status="pending",
        adapter_name="slack",
        action="send_message",
        metadata={"adapter_mode": "simulation"},
        playbook_execution_id=eid,
        playbook_step_index=0,
        alert_id=alert_id,
        circuit_breaker_state="closed",
    )
    conn.commit()

    with patch(
        "engines.playbook_step_executor.execute_playbook_simulated_adapter",
        side_effect=AssertionError("in-flight duplicate must not execute adapter"),
    ):
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["steps_log"][0]["output"]["skip_reason"] == "delivery_pending"
    assert _count_deliveries(cur, eid) == 1


def test_duplicate_email_delivery_skips_smtp_send(postgres_db, monkeypatch, no_network):
    conn, cur = postgres_db
    eid = _create_execution(
        conn,
        cur,
        "pb_email_delivery_dedup",
        steps=[{"action": "notify_email", "params": {"subject": "already sent"}}],
    )
    cur.execute("SELECT alert_id FROM playbook_executions WHERE id = %s", (eid,))
    alert_id = cur.fetchone()[0]
    notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id=f"existing-email-{eid}-0",
        idempotency_key=playbook_step_executor._make_delivery_idempotency_key(
            "email", "notify_email", eid, 0
        ),
        provider="email",
        mode="real",
        status="success",
        adapter_name="email",
        action="send_email",
        metadata={"adapter_mode": "real"},
        playbook_execution_id=eid,
        playbook_step_index=0,
        alert_id=alert_id,
        circuit_breaker_state="closed",
    )
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_EMAIL_ENABLED", "true")
    monkeypatch.setenv("SMTP_HOST", "smtp.staging.local")
    monkeypatch.setenv("SMTP_USERNAME", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-secret")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "soar@example.com")
    monkeypatch.setenv("SMTP_TO_EMAIL", "analyst@example.com")
    conn.commit()

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    row = playbook_store.get_playbook_execution(conn, eid)
    entry = row["steps_log"][0]
    assert entry["skipped"] is True
    assert entry["output"]["skip_reason"] == "delivery_success"
    assert _count_deliveries(cur, eid) == 1


def test_duplicate_webhook_delivery_skips_http_call(postgres_db, monkeypatch, no_network):
    conn, cur = postgres_db
    eid = _create_execution(
        conn,
        cur,
        "pb_webhook_delivery_dedup",
        steps=[{"action": "notify_webhook", "params": {"payload": {"event": "already sent"}}}],
    )
    cur.execute("SELECT alert_id FROM playbook_executions WHERE id = %s", (eid,))
    alert_id = cur.fetchone()[0]
    notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id=f"existing-webhook-{eid}-0",
        idempotency_key=playbook_step_executor._make_delivery_idempotency_key(
            "webhook", "notify_webhook", eid, 0
        ),
        provider="webhook",
        mode="real",
        status="success",
        adapter_name="webhook",
        action="post_event",
        metadata={"adapter_mode": "real"},
        playbook_execution_id=eid,
        playbook_step_index=0,
        alert_id=alert_id,
        circuit_breaker_state="closed",
    )
    monkeypatch.setenv("INTEGRATION_MODE", "real")
    monkeypatch.setenv("SOAR_ENV", "staging")
    monkeypatch.setenv("SOAR_REAL_WEBHOOK_ENABLED", "true")
    monkeypatch.setenv("WEBHOOK_URL", "https://events.staging.example/hooks/soar")
    conn.commit()

    with patch(
        "integrations.webhook_adapter._post_webhook_request",
        side_effect=AssertionError("duplicate delivery must not execute HTTP"),
    ):
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    row = playbook_store.get_playbook_execution(conn, eid)
    entry = row["steps_log"][0]
    assert entry["skipped"] is True
    assert entry["output"]["skip_reason"] == "delivery_success"
    assert _count_deliveries(cur, eid) == 1


@pytest.fixture
def utc_db(postgres_db):
    conn, cur = postgres_db
    cur.execute("SET TIME ZONE 'UTC'")
    conn.commit()
    return conn, cur


def test_executor_acquires_lease_before_processing(utc_db):
    conn, cur = utc_db
    eid = _create_execution(conn, cur, "pb_lease_acquire")

    result = playbook_step_executor.process_playbook_execution(
        conn, eid, worker_id="worker-alpha"
    )

    row = playbook_store.get_playbook_execution(conn, eid)
    assert result["outcome"] == "success"
    assert row["status"] == "success"
    assert row["lease_owner"] is None


def test_second_worker_cannot_process_leased_execution(utc_db, caplog):
    conn, cur = utc_db
    eid = _create_execution(conn, cur, "pb_lease_block")
    leased = playbook_store.acquire_execution_lease(
        conn, eid, "worker-alpha", lease_duration_seconds=120
    )
    conn.commit()
    assert leased is not None

    caplog.set_level("INFO", logger="engines.playbook_step_executor")
    result = playbook_step_executor.process_playbook_execution(
        conn, eid, worker_id="worker-beta"
    )

    assert result["outcome"] == "skipped"
    assert result["reason"] == "lease_not_owned"
    assert "worker_id=worker-beta" in caplog.text
    assert "reason=lease_not_owned" in caplog.text


def test_failed_lease_acquisition_skips_processing(utc_db):
    conn, cur = utc_db
    eid = _create_execution(conn, cur, "pb_lease_skip")
    playbook_store.acquire_execution_lease(
        conn, eid, "worker-alpha", lease_duration_seconds=120
    )
    conn.commit()

    result = playbook_step_executor.process_playbook_execution(
        conn, eid, worker_id="worker-beta"
    )

    assert result["outcome"] == "skipped"
    assert result["reason"] == "lease_not_owned"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "running"
    assert row["lease_owner"] == "worker-alpha"


def test_pending_with_expired_lease_can_be_acquired_by_worker(utc_db):
    conn, cur = utc_db
    eid = _create_execution(conn, cur, "pb_lease_expired_pending")
    cur.execute(
        """
        UPDATE playbook_executions
        SET lease_owner = %s,
            lease_acquired_at = NOW() - INTERVAL '10 minutes',
            lease_heartbeat_at = NOW() - INTERVAL '10 minutes',
            lease_expires_at = NOW() - INTERVAL '5 minutes'
        WHERE id = %s
        """,
        ("stale-worker", eid),
    )
    conn.commit()

    result = playbook_step_executor.process_playbook_execution(
        conn, eid, worker_id="worker-beta"
    )

    assert result["outcome"] == "success"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "success"


def test_heartbeat_called_during_execution(utc_db, monkeypatch):
    conn, cur = utc_db
    eid = _create_execution(conn, cur, "pb_lease_hb")
    calls = []
    original_heartbeat = playbook_store.heartbeat_execution_lease

    def _record_heartbeat(conn, execution_id, lease_owner, **kwargs):
        calls.append((execution_id, lease_owner))
        return original_heartbeat(conn, execution_id, lease_owner, **kwargs)

    monkeypatch.setattr(
        playbook_step_executor.playbook_store,
        "heartbeat_execution_lease",
        _record_heartbeat,
    )

    playbook_step_executor.process_playbook_execution(
        conn, eid, worker_id="worker-alpha", lease_duration_seconds=60
    )

    assert calls
    assert all(owner == "worker-alpha" for _, owner in calls)
    assert all(exec_id == eid for exec_id, _ in calls)


def test_lease_released_after_terminal_success(utc_db):
    conn, cur = utc_db
    eid = _create_execution(conn, cur, "pb_lease_release_ok")

    playbook_step_executor.process_playbook_execution(
        conn, eid, worker_id="worker-alpha"
    )
    conn.commit()

    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "success"
    assert row["lease_owner"] is None
    assert row["lease_expires_at"] is None


def test_lease_released_when_pausing_for_approval(utc_db):
    conn, cur = utc_db
    eid = _create_execution(
        conn,
        cur,
        "pb_lease_approval_pause",
        steps=[{"action": "require_approval", "params": {}}],
    )

    result = playbook_step_executor.process_playbook_execution(
        conn, eid, worker_id="worker-alpha"
    )
    conn.commit()

    row = playbook_store.get_playbook_execution(conn, eid)
    assert result["outcome"] == "awaiting_approval"
    assert row["status"] == "awaiting_approval"
    assert row["lease_owner"] is None


def test_single_execution_path_uses_explicit_worker_id(utc_db):
    conn, cur = utc_db
    eid = _create_execution(conn, cur, "pb_single_worker")

    result = playbook_step_executor.process_playbook_execution(
        conn, eid, worker_id="smoke-worker-1"
    )
    conn.commit()

    assert result["outcome"] == "success"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["lease_owner"] is None


def test_notify_slack_creates_one_delivery_under_lease_processing(utc_db, no_network):
    conn, cur = utc_db
    eid = _create_execution(conn, cur, "pb_lease_notify")
    _set_playbook_steps(cur, "pb_lease_notify", [{"action": "notify_slack", "params": {}}])

    result = playbook_step_executor.process_playbook_execution(
        conn, eid, worker_id="worker-alpha"
    )

    assert result["outcome"] == "success"
    assert _count(cur, "notification_delivery_attempts") == 1


def test_recovered_pending_execution_resumes_after_last_completed_step(utc_db, monkeypatch):
    conn, cur = utc_db
    eid = _create_execution(
        conn,
        cur,
        "pb_resume_pending",
        steps=[
            {"action": "monitor", "params": {}},
            {"action": "flag_high_priority", "params": {}},
        ],
    )
    _set_execution_progress(
        cur,
        eid,
        status="pending",
        steps_log=[_progress_entry(0, "monitor")],
        last_completed_step=0,
    )
    calls = []
    original = playbook_step_executor._simulate_step

    def _record_step(conn_arg, step, step_index, now, execution):
        calls.append(step_index)
        return original(conn_arg, step, step_index, now, execution)

    monkeypatch.setattr(playbook_step_executor, "_simulate_step", _record_step)

    result = playbook_step_executor.process_playbook_execution(
        conn, eid, worker_id="worker-alpha"
    )

    assert result["outcome"] == "success"
    assert calls == [1]
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["last_completed_step"] == 1
    assert [entry["action"] for entry in row["steps_log"]] == [
        "monitor",
        "flag_high_priority",
    ]


def test_execution_without_completed_step_starts_at_step_zero(utc_db, monkeypatch):
    conn, cur = utc_db
    eid = _create_execution(
        conn,
        cur,
        "pb_resume_fresh",
        steps=[
            {"action": "monitor", "params": {}},
            {"action": "flag_high_priority", "params": {}},
        ],
    )
    calls = []
    original = playbook_step_executor._simulate_step

    def _record_step(conn_arg, step, step_index, now, execution):
        calls.append(step_index)
        return original(conn_arg, step, step_index, now, execution)

    monkeypatch.setattr(playbook_step_executor, "_simulate_step", _record_step)

    result = playbook_step_executor.process_playbook_execution(
        conn, eid, worker_id="worker-alpha"
    )

    assert result["outcome"] == "success"
    assert calls == [0, 1]


def test_running_owned_execution_resumes_without_replaying_success_step(utc_db, monkeypatch):
    conn, cur = utc_db
    eid = _create_execution(
        conn,
        cur,
        "pb_resume_running",
        steps=[
            {"action": "monitor", "params": {}},
            {"action": "flag_high_priority", "params": {}},
        ],
    )
    _set_execution_progress(
        cur,
        eid,
        status="running",
        steps_log=[_progress_entry(0, "monitor")],
        last_completed_step=0,
        lease_owner="worker-alpha",
    )
    calls = []
    original = playbook_step_executor._simulate_step

    def _record_step(conn_arg, step, step_index, now, execution):
        calls.append(step_index)
        return original(conn_arg, step, step_index, now, execution)

    monkeypatch.setattr(playbook_step_executor, "_simulate_step", _record_step)

    result = playbook_step_executor.process_playbook_execution(
        conn, eid, worker_id="worker-alpha"
    )

    assert result["outcome"] == "success"
    assert calls == [1]
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "success"
    assert row["last_completed_step"] == 1


def test_completed_notification_step_is_not_recorded_again_on_resume(utc_db, no_network):
    conn, cur = utc_db
    eid = _create_execution(
        conn,
        cur,
        "pb_resume_notify",
        steps=[
            {"action": "notify_slack", "params": {"message": "already sent"}},
            {"action": "monitor", "params": {}},
        ],
    )
    cur.execute("SELECT alert_id FROM playbook_executions WHERE id = %s", (eid,))
    alert_id = cur.fetchone()[0]
    notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id=f"existing-{eid}-0",
        idempotency_key=playbook_step_executor._make_delivery_idempotency_key(
            "slack", "notify_slack", eid, 0
        ),
        provider="slack",
        mode="simulation",
        status="success",
        adapter_name="slack",
        action="send_message",
        metadata={"adapter_mode": "simulation"},
        playbook_execution_id=eid,
        playbook_step_index=0,
        alert_id=alert_id,
        circuit_breaker_state="closed",
    )
    _set_execution_progress(
        cur,
        eid,
        status="pending",
        steps_log=[_progress_entry(0, "notify_slack")],
        last_completed_step=0,
    )

    with patch(
        "engines.playbook_step_executor.notification_delivery_store"
        ".create_notification_delivery_attempt",
        side_effect=AssertionError("completed notification step was replayed"),
    ):
        result = playbook_step_executor.process_playbook_execution(
            conn, eid, worker_id="worker-alpha"
        )

    assert result["outcome"] == "success"
    assert _count_deliveries(cur, eid) == 1
    row = playbook_store.get_playbook_execution(conn, eid)
    assert [entry["action"] for entry in row["steps_log"]] == ["notify_slack", "monitor"]


def test_resumed_execution_still_requires_matching_lease_owner(utc_db):
    conn, cur = utc_db
    eid = _create_execution(
        conn,
        cur,
        "pb_resume_lease_guard",
        steps=[
            {"action": "monitor", "params": {}},
            {"action": "flag_high_priority", "params": {}},
        ],
    )
    prior_log = [_progress_entry(0, "monitor")]
    _set_execution_progress(
        cur,
        eid,
        status="running",
        steps_log=prior_log,
        last_completed_step=0,
        lease_owner="worker-alpha",
    )

    result = playbook_step_executor.process_playbook_execution(
        conn, eid, worker_id="worker-beta"
    )

    row = playbook_store.get_playbook_execution(conn, eid)
    assert result["outcome"] == "skipped"
    assert result["reason"] == "lease_not_owned"
    assert row["status"] == "running"
    assert row["last_completed_step"] == 0
    assert row["steps_log"] == prior_log


def test_finalize_success_does_not_fallback_after_lease_loss(utc_db):
    conn, cur = utc_db
    eid = _create_execution(conn, cur, "pb_finalize_success_guard")
    start = datetime(2026, 5, 16, 12, 0, 0)
    playbook_store.acquire_execution_lease(
        conn,
        eid,
        "fresh-worker",
        lease_duration_seconds=120,
        now=start,
    )
    conn.commit()

    playbook_step_executor._finalize_success(
        conn,
        eid,
        "stale-worker",
        [_progress_entry(0, "monitor", now=start.replace(tzinfo=timezone.utc))],
        last_completed_step=0,
        now=start + timedelta(seconds=5),
    )
    conn.commit()

    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "running"
    assert row["lease_owner"] == "fresh-worker"
    assert row["steps_log"] == []


def test_finalize_failed_does_not_fallback_or_dead_letter_after_lease_loss(utc_db):
    conn, cur = utc_db
    eid = _create_execution(conn, cur, "pb_finalize_failure_guard")
    start = datetime(2026, 5, 16, 12, 0, 0)
    playbook_store.acquire_execution_lease(
        conn,
        eid,
        "fresh-worker",
        lease_duration_seconds=120,
        now=start,
    )
    conn.commit()

    playbook_step_executor._finalize_failed(
        conn,
        eid,
        "stale-worker",
        [
            {
                "step_index": 0,
                "action": "notify_slack",
                "status": "failed",
                "message": "stale worker failure",
                "error": {"message": "stale worker failure"},
            }
        ],
        last_completed_step=None,
        now=start + timedelta(seconds=5),
    )
    conn.commit()

    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["status"] == "running"
    assert row["lease_owner"] == "fresh-worker"
    assert row["steps_log"] == []
    assert dead_letter_store.list_dead_letters(conn, execution_id=eid) == []


@pytest.mark.parametrize("status", ["failed", "abandoned", "permanently_failed"])
def test_terminal_failed_or_aborted_executions_do_not_resume(utc_db, status):
    conn, cur = utc_db
    eid = _create_execution(
        conn,
        cur,
        f"pb_terminal_{status}",
        steps=[
            {"action": "monitor", "params": {}},
            {"action": "flag_high_priority", "params": {}},
        ],
    )
    prior_log = [_progress_entry(0, "monitor")]
    _set_execution_progress(
        cur,
        eid,
        status=status,
        steps_log=prior_log,
        last_completed_step=0,
    )

    result = playbook_step_executor.process_playbook_execution(
        conn, eid, worker_id="worker-alpha"
    )

    row = playbook_store.get_playbook_execution(conn, eid)
    assert result["outcome"] == "skipped"
    assert result["reason"] == "terminal_status"
    assert row["status"] == status
    assert row["steps_log"] == prior_log


def test_recovered_stale_execution_later_resumes_after_completed_step(utc_db, monkeypatch):
    conn, cur = utc_db
    eid = _create_execution(
        conn,
        cur,
        "pb_stale_resume",
        steps=[
            {"action": "monitor", "params": {}},
            {"action": "flag_high_priority", "params": {}},
        ],
    )
    recovery_at = _set_expired_running_progress(
        cur,
        eid,
        steps_log=[_progress_entry(0, "monitor")],
        last_completed_step=0,
    )
    conn.commit()

    recovered = run_playbook_executor_once.recover_stale_playbook_executions(
        conn,
        limit=10,
        dry_run=False,
        now=recovery_at,
    )
    conn.commit()

    calls = []
    original = playbook_step_executor._simulate_step

    def _record_step(conn_arg, step, step_index, now, execution):
        calls.append(step_index)
        return original(conn_arg, step, step_index, now, execution)

    monkeypatch.setattr(playbook_step_executor, "_simulate_step", _record_step)
    result = playbook_step_executor.process_playbook_execution(
        conn,
        eid,
        worker_id="worker-alpha",
    )

    row = playbook_store.get_playbook_execution(conn, eid)
    assert recovered["recovered"] == 1
    assert result["outcome"] == "success"
    assert calls == [1]
    assert row["last_completed_step"] == 1
    assert [entry["action"] for entry in row["steps_log"]] == [
        "monitor",
        "flag_high_priority",
    ]


def test_recovered_stale_notification_step_is_not_recorded_again(utc_db, no_network):
    conn, cur = utc_db
    eid = _create_execution(
        conn,
        cur,
        "pb_stale_notify_resume",
        steps=[
            {"action": "notify_slack", "params": {"message": "already sent"}},
            {"action": "monitor", "params": {}},
        ],
    )
    cur.execute("SELECT alert_id FROM playbook_executions WHERE id = %s", (eid,))
    alert_id = cur.fetchone()[0]
    notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id=f"stale-existing-{eid}-0",
        idempotency_key=playbook_step_executor._make_delivery_idempotency_key(
            "slack", "notify_slack", eid, 0
        ),
        provider="slack",
        mode="simulation",
        status="success",
        adapter_name="slack",
        action="send_message",
        metadata={"adapter_mode": "simulation"},
        playbook_execution_id=eid,
        playbook_step_index=0,
        alert_id=alert_id,
        circuit_breaker_state="closed",
    )
    recovery_at = _set_expired_running_progress(
        cur,
        eid,
        steps_log=[_progress_entry(0, "notify_slack")],
        last_completed_step=0,
    )
    conn.commit()

    recovered = run_playbook_executor_once.recover_stale_playbook_executions(
        conn,
        limit=10,
        dry_run=False,
        now=recovery_at,
    )
    conn.commit()

    with patch(
        "engines.playbook_step_executor.notification_delivery_store"
        ".create_notification_delivery_attempt",
        side_effect=AssertionError("completed notification step was replayed"),
    ):
        result = playbook_step_executor.process_playbook_execution(
            conn,
            eid,
            worker_id="worker-alpha",
        )

    row = playbook_store.get_playbook_execution(conn, eid)
    assert recovered["recovered"] == 1
    assert result["outcome"] == "success"
    assert _count_deliveries(cur, eid) == 1
    assert [entry["action"] for entry in row["steps_log"]] == ["notify_slack", "monitor"]


# ---------------------------------------------------------------------------
# Slice 5: notification/remediation duplication guard
# ---------------------------------------------------------------------------


def test_recovered_teams_step_does_not_create_duplicate_delivery(utc_db, no_network):
    conn, cur = utc_db
    eid = _create_execution(conn, cur, "pb_stale_teams_dedup")
    _set_playbook_steps(
        cur,
        "pb_stale_teams_dedup",
        [
            {"action": "notify_teams", "params": {"message": "already sent"}},
            {"action": "monitor", "params": {}},
        ],
    )
    cur.execute("SELECT alert_id FROM playbook_executions WHERE id = %s", (eid,))
    alert_id = cur.fetchone()[0]
    notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id=f"stale-teams-{eid}-0",
        idempotency_key=playbook_step_executor._make_delivery_idempotency_key(
            "teams", "notify_teams", eid, 0
        ),
        provider="teams",
        mode="simulation",
        status="success",
        adapter_name="teams",
        action="send_message",
        metadata={"adapter_mode": "simulation"},
        playbook_execution_id=eid,
        playbook_step_index=0,
        alert_id=alert_id,
        circuit_breaker_state="closed",
    )
    recovery_at = _set_expired_running_progress(
        cur,
        eid,
        steps_log=[_progress_entry(0, "notify_teams")],
        last_completed_step=0,
    )
    conn.commit()

    recovered = run_playbook_executor_once.recover_stale_playbook_executions(
        conn, limit=10, dry_run=False, now=recovery_at
    )
    conn.commit()

    with patch(
        "engines.playbook_step_executor.notification_delivery_store"
        ".create_notification_delivery_attempt",
        side_effect=AssertionError("completed Teams notification step was replayed"),
    ):
        result = playbook_step_executor.process_playbook_execution(
            conn, eid, worker_id="worker-alpha"
        )

    row = playbook_store.get_playbook_execution(conn, eid)
    assert recovered["recovered"] == 1
    assert result["outcome"] == "success"
    assert _count_deliveries(cur, eid) == 1
    assert [entry["action"] for entry in row["steps_log"]] == ["notify_teams", "monitor"]


def test_completed_block_ip_remediation_step_skipped_on_resume(utc_db, monkeypatch, no_network):
    conn, cur = utc_db
    eid = _create_execution(
        conn,
        cur,
        "pb_resume_block_ip",
        steps=[
            {"action": "block_ip", "params": {"source_ip": "1.2.3.4"}},
            {"action": "monitor", "params": {}},
        ],
    )
    _set_execution_progress(
        cur,
        eid,
        status="pending",
        steps_log=[_progress_entry(0, "block_ip")],
        last_completed_step=0,
    )
    conn.commit()

    steps_executed = []
    original_simulate = playbook_step_executor._simulate_step

    def _record_and_run(conn_arg, step, step_index, now, execution):
        steps_executed.append(step_index)
        return original_simulate(conn_arg, step, step_index, now, execution)

    monkeypatch.setattr(playbook_step_executor, "_simulate_step", _record_and_run)

    result = playbook_step_executor.process_playbook_execution(
        conn, eid, worker_id="worker-alpha"
    )

    assert result["outcome"] == "success"
    assert 0 not in steps_executed
    assert 1 in steps_executed
    row = playbook_store.get_playbook_execution(conn, eid)
    assert [entry["action"] for entry in row["steps_log"]] == ["block_ip", "monitor"]
    assert row["last_completed_step"] == 1


def test_two_workers_cannot_both_complete_same_execution(utc_db, no_network):
    conn, cur = utc_db
    eid = _create_execution(
        conn,
        cur,
        "pb_two_workers_dedup",
        steps=[
            {"action": "notify_slack", "params": {"message": "race test"}},
            {"action": "monitor", "params": {}},
        ],
    )
    playbook_store.acquire_execution_lease(
        conn, eid, "worker-alpha", lease_duration_seconds=120
    )
    conn.commit()

    result_beta = playbook_step_executor.process_playbook_execution(
        conn, eid, worker_id="worker-beta"
    )

    assert result_beta["outcome"] == "skipped"
    assert result_beta["reason"] == "lease_not_owned"
    assert _count_deliveries(cur, eid) == 0

    playbook_store.release_execution_lease(conn, eid, "worker-alpha")
    cur.execute("UPDATE playbook_executions SET status = 'pending' WHERE id = %s", (eid,))
    conn.commit()

    result_alpha = playbook_step_executor.process_playbook_execution(
        conn, eid, worker_id="worker-alpha"
    )

    assert result_alpha["outcome"] == "success"
    assert _count_deliveries(cur, eid) == 1


def test_steps_log_success_guard_prevents_reexecution_when_last_completed_step_missing(
    utc_db, monkeypatch, no_network
):
    conn, cur = utc_db
    eid = _create_execution(
        conn,
        cur,
        "pb_guard_lcs_null",
        steps=[
            {"action": "notify_slack", "params": {"message": "done"}},
            {"action": "monitor", "params": {}},
        ],
    )
    # Intentionally diverged state: steps_log has step 0 as success but last_completed_step=NULL
    cur.execute(
        "UPDATE playbook_executions SET steps_log = %s, last_completed_step = NULL WHERE id = %s",
        (Json([_progress_entry(0, "notify_slack")]), eid),
    )
    conn.commit()

    steps_executed = []
    original_simulate = playbook_step_executor._simulate_step

    def _record_and_run(conn_arg, step, step_index, now, execution):
        steps_executed.append(step_index)
        return original_simulate(conn_arg, step, step_index, now, execution)

    monkeypatch.setattr(playbook_step_executor, "_simulate_step", _record_and_run)

    with patch(
        "engines.playbook_step_executor.notification_delivery_store"
        ".create_notification_delivery_attempt",
        side_effect=AssertionError("notify_slack must not be re-executed via guard"),
    ):
        result = playbook_step_executor.process_playbook_execution(
            conn, eid, worker_id="worker-alpha"
        )

    assert result["outcome"] == "success"
    assert steps_executed == [1]
    row = playbook_store.get_playbook_execution(conn, eid)
    assert [entry["action"] for entry in row["steps_log"]] == ["notify_slack", "monitor"]
    assert row["last_completed_step"] == 1
