import uuid
from datetime import datetime, timedelta, timezone

import pytest

from core import soar_response_outcomes as outcomes
from core.response_action_queue_store import get_queue_action
from engines.soar_enqueue_orchestrator import enqueue_committed_alerts


def _insert_alert(cur, source_ip="10.20.30.40"):
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message)
        VALUES ('test_alert', 'LOW', %s::inet, 'msg')
        RETURNING id
        """,
        (source_ip,),
    )
    return cur.fetchone()[0]


@pytest.mark.usefixtures("postgres_db")
def test_generate_soar_correlation_id_format():
    correlation_id = outcomes.generate_soar_correlation_id(alert_id=42)
    assert correlation_id.startswith("soar-42-")
    assert outcomes.validate_soar_correlation_id(correlation_id) == correlation_id
    assert len(correlation_id) <= 128


@pytest.mark.usefixtures("postgres_db")
def test_generate_soar_correlation_id_rejects_urls():
    with pytest.raises(outcomes.SoarResponseOutcomeValidationError):
        outcomes.validate_soar_correlation_id("soar-1-http://bad.example")


@pytest.mark.usefixtures("postgres_db")
def test_generate_legacy_soar_correlation_id():
    correlation_id = outcomes.generate_legacy_soar_correlation_id("response_actions_log", 99)
    assert correlation_id == "legacy-response_actions_log-99"


@pytest.mark.usefixtures("postgres_db")
def test_create_decision_generates_correlation_id(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()

    decision = outcomes.create_response_decision(
        conn,
        alert_id=alert_id,
        source_ip="10.20.30.40",
        selected_action="monitor",
        decision_source="manual",
        outcome_summary="Analyst selected monitor.",
    )
    conn.commit()

    assert decision["id"] is not None
    assert decision["soar_correlation_id"].startswith(f"soar-{alert_id}-")
    assert decision["selected_action"] == "monitor"
    assert decision["safe_metadata"] == {}


@pytest.mark.usefixtures("postgres_db")
def test_create_decision_with_supplied_correlation_id(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()

    supplied = f"soar-{alert_id}-custom123"
    decision = outcomes.create_response_decision(
        conn,
        alert_id=alert_id,
        soar_correlation_id=supplied,
        selected_action="escalate",
        decision_source="detection_default",
        outcome_summary="Detection default response selected.",
    )
    conn.commit()

    assert decision["soar_correlation_id"] == supplied


@pytest.mark.usefixtures("postgres_db")
def test_create_decision_rejects_invalid_decision_source(postgres_db):
    conn, _cur = postgres_db
    with pytest.raises(outcomes.SoarResponseOutcomeValidationError):
        outcomes.create_response_decision(
            conn,
            selected_action="monitor",
            decision_source="queue_worker",
            outcome_summary="invalid",
        )


@pytest.mark.parametrize(
    "execution_mode,execution_state,external_executed,tracking_recorded,simulated,execution_actor,summary",
    [
        ("observed", "observed", False, False, False, "system", "Detection observed only."),
        (
            "simulation",
            "succeeded",
            False,
            False,
            True,
            "queue_worker",
            "Simulated queue action completed.",
        ),
        (
            "tracking_only",
            "succeeded",
            False,
            True,
            False,
            "manual",
            "Recorded IP in SIEM blocklist only; no firewall enforcement occurred.",
        ),
        (
            "real",
            "succeeded",
            True,
            False,
            False,
            "adapter",
            "Provider confirmed delivery.",
        ),
    ],
)
@pytest.mark.usefixtures("postgres_db")
def test_append_outcome_event_modes(
    postgres_db,
    execution_mode,
    execution_state,
    external_executed,
    tracking_recorded,
    simulated,
    execution_actor,
    summary,
):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()

    decision = outcomes.create_response_decision(
        conn,
        alert_id=alert_id,
        selected_action="block_ip",
        decision_source="manual",
        outcome_summary="Manual block selected.",
    )
    conn.commit()

    event = outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        execution_mode=execution_mode,
        execution_state=execution_state,
        external_executed=external_executed,
        tracking_recorded=tracking_recorded,
        simulated=simulated,
        execution_actor=execution_actor,
        outcome_summary=summary,
        reason_code="tracking_only" if execution_mode == "tracking_only" else None,
    )
    conn.commit()

    assert event["decision_id"] == decision["id"]
    assert event["execution_mode"] == execution_mode
    assert event["execution_state"] == execution_state
    assert event["external_executed"] is external_executed
    assert event["tracking_recorded"] is tracking_recorded
    assert event["simulated"] is simulated


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "execution_mode": "simulation",
            "execution_state": "succeeded",
            "external_executed": True,
            "tracking_recorded": False,
            "simulated": True,
            "execution_actor": "queue_worker",
            "outcome_summary": "invalid simulation booleans",
        },
        {
            "execution_mode": "bad_mode",
            "execution_state": "selected",
            "execution_actor": "system",
            "outcome_summary": "bad mode",
        },
        {
            "execution_mode": "simulation",
            "execution_state": "pending",
            "execution_actor": "system",
            "outcome_summary": "bad state",
        },
        {
            "execution_mode": "simulation",
            "execution_state": "selected",
            "execution_actor": "worker",
            "outcome_summary": "bad actor",
        },
        {
            "execution_mode": "simulation",
            "execution_state": "selected",
            "execution_actor": "system",
            "outcome_summary": "bad reason",
            "reason_code": "not_a_real_reason",
        },
    ],
)
@pytest.mark.usefixtures("postgres_db")
def test_append_outcome_event_rejects_invalid_inputs(postgres_db, kwargs):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()
    decision = outcomes.create_response_decision(
        conn,
        alert_id=alert_id,
        selected_action="monitor",
        decision_source="manual",
        outcome_summary="test",
    )
    conn.commit()

    with pytest.raises(outcomes.SoarResponseOutcomeValidationError):
        outcomes.append_outcome_event(conn, decision_id=decision["id"], **kwargs)


@pytest.mark.usefixtures("postgres_db")
def test_latest_outcome_returns_newest_event(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()
    decision = outcomes.create_response_decision(
        conn,
        alert_id=alert_id,
        selected_action="monitor",
        decision_source="manual",
        outcome_summary="test",
    )
    conn.commit()

    older_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    newer_time = datetime.now(timezone.utc) - timedelta(minutes=1)

    outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        execution_mode="simulation",
        execution_state="queued",
        execution_actor="queue_worker",
        outcome_summary="queued",
        occurred_at=older_time,
    )
    outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        execution_mode="simulation",
        execution_state="succeeded",
        simulated=True,
        execution_actor="queue_worker",
        outcome_summary="simulation succeeded",
        occurred_at=newer_time,
    )
    conn.commit()

    latest = outcomes.get_latest_outcome_for_decision(conn, decision["id"])
    assert latest is not None
    assert latest["execution_state"] == "succeeded"
    assert latest["outcome_summary"] == "simulation succeeded"

    by_correlation = outcomes.get_latest_outcome_by_correlation_id(
        conn, decision["soar_correlation_id"]
    )
    assert by_correlation["id"] == latest["id"]


@pytest.mark.usefixtures("postgres_db")
def test_get_decision_with_latest_outcome_without_events_defaults_to_selected(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()
    decision = outcomes.create_response_decision(
        conn,
        alert_id=alert_id,
        selected_action="monitor",
        decision_source="manual",
        outcome_summary="Decision only; no events yet.",
    )
    conn.commit()

    read_model = outcomes.get_decision_with_latest_outcome(
        conn, soar_correlation_id=decision["soar_correlation_id"]
    )
    assert read_model["latest_outcome"] is None
    assert read_model["outcome_label"] == "Selected"
    assert read_model["execution_mode"] == "observed"
    assert read_model["execution_state"] == "selected"


@pytest.mark.usefixtures("postgres_db")
def test_get_decision_with_latest_outcome_read_model(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()
    decision = outcomes.create_response_decision(
        conn,
        alert_id=alert_id,
        selected_action="block_ip",
        decision_source="manual",
        outcome_summary="Manual tracking-only block selected.",
    )
    conn.commit()

    outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        execution_mode="tracking_only",
        execution_state="succeeded",
        tracking_recorded=True,
        execution_actor="manual",
        outcome_summary="Recorded IP in SIEM blocklist only; no firewall enforcement occurred.",
        reason_code="tracking_only",
    )
    conn.commit()

    read_model = outcomes.get_decision_with_latest_outcome(
        conn, decision_id=decision["id"]
    )
    assert read_model is not None
    assert read_model["decision"]["id"] == decision["id"]
    assert read_model["latest_outcome"] is not None
    assert read_model["outcome_label"] == "Tracking only"
    assert read_model["execution_mode"] == "tracking_only"
    assert read_model["tracking_recorded"] is True
    assert read_model["external_executed"] is False
    assert read_model["simulated"] is False
    assert read_model["selected_action"] == "block_ip"


@pytest.mark.parametrize(
    "execution_mode,execution_state,external_executed,tracking_recorded,simulated,expected",
    [
        ("observed", "observed", False, False, False, "Observed only"),
        ("simulation", "succeeded", False, False, True, "Simulated"),
        ("tracking_only", "succeeded", False, True, False, "Tracking only"),
        ("real", "succeeded", True, False, False, "Real executed"),
        ("simulation", "awaiting_approval", False, False, False, "Awaiting approval"),
        ("simulation", "blocked", False, False, False, "Blocked"),
        ("simulation", "skipped", False, False, False, "Skipped"),
        ("simulation", "failed", False, False, False, "Failed"),
        ("simulation", "running", False, False, False, "Running"),
        ("simulation", "queued", False, False, False, "Queued"),
        ("simulation", "selected", False, False, False, "Selected"),
    ],
)
def test_derive_outcome_label(
    execution_mode,
    execution_state,
    external_executed,
    tracking_recorded,
    simulated,
    expected,
):
    label = outcomes.derive_outcome_label(
        execution_mode=execution_mode,
        execution_state=execution_state,
        external_executed=external_executed,
        tracking_recorded=tracking_recorded,
        simulated=simulated,
    )
    assert label == expected


@pytest.mark.usefixtures("postgres_db")
def test_idempotency_key_returns_existing_event(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()
    decision = outcomes.create_response_decision(
        conn,
        alert_id=alert_id,
        selected_action="monitor",
        decision_source="manual",
        outcome_summary="test",
    )
    conn.commit()

    idempotency_key = f"idem-{uuid.uuid4().hex}"
    first = outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        execution_mode="simulation",
        execution_state="selected",
        execution_actor="system",
        outcome_summary="first write",
        idempotency_key=idempotency_key,
    )
    second = outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        execution_mode="simulation",
        execution_state="failed",
        execution_actor="system",
        outcome_summary="should not insert",
        idempotency_key=idempotency_key,
    )
    conn.commit()

    assert second["id"] == first["id"]
    assert second["outcome_summary"] == "first write"


@pytest.mark.usefixtures("postgres_db")
def test_metadata_jsonb_round_trip_is_redacted(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()
    decision = outcomes.create_response_decision(
        conn,
        alert_id=alert_id,
        selected_action="monitor",
        decision_source="manual",
        outcome_summary="test",
        safe_metadata={
            "channel_label": "#soc",
            "webhook_configured": True,
            "api_key": "secret-value",
            "callback": "https://example.com/hook",
        },
    )
    conn.commit()

    assert decision["safe_metadata"]["channel_label"] == "#soc"
    assert "api_key" not in decision["safe_metadata"]
    assert decision["safe_metadata"]["callback"] == "[REDACTED_URL]"

    event = outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        execution_mode="simulation",
        execution_state="selected",
        execution_actor="system",
        outcome_summary="metadata test",
        metadata={"provider_status": "ok", "access_token": "nope"},
    )
    conn.commit()

    assert event["metadata"]["provider_status"] == "ok"
    assert "access_token" not in event["metadata"]


# ---------------------------------------------------------------------------
# Phase 4 Slice 3: enqueue orchestrator canonical integration tests
# ---------------------------------------------------------------------------

def _make_alert(alert_id, source_ip="10.20.30.40", action="monitor", alert_type=None):
    entry = {"alert_id": alert_id, "source_ip": source_ip, "response_action": action}
    if alert_type is not None:
        entry["alert_type"] = alert_type
    return entry


def test_enqueue_committed_alerts_creates_decision_linked_to_queue(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()

    results = enqueue_committed_alerts([_make_alert(alert_id)], conn)
    conn.commit()

    assert results[0]["status"] == "enqueued"
    queue_id = results[0]["queue_id"]
    assert queue_id is not None

    queue_row = get_queue_action(conn, queue_id)
    assert queue_row["decision_id"] is not None
    assert queue_row["soar_correlation_id"] is not None
    assert queue_row["soar_correlation_id"].startswith(f"soar-{alert_id}-")

    decision = outcomes._fetch_decision_by_id(conn, queue_row["decision_id"])
    assert decision is not None
    assert decision["alert_id"] == alert_id
    assert decision["selected_action"] == "monitor"
    assert decision["queue_id"] == queue_id


def test_enqueue_committed_alerts_appends_queued_simulation_event(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()

    results = enqueue_committed_alerts([_make_alert(alert_id)], conn)
    conn.commit()

    queue_id = results[0]["queue_id"]
    queue_row = get_queue_action(conn, queue_id)

    event = outcomes.get_latest_outcome_for_queue(conn, queue_id)
    assert event is not None
    assert event["execution_mode"] == "simulation"
    assert event["execution_state"] == "queued"
    assert event["simulated"] is True
    assert event["external_executed"] is False
    assert event["tracking_recorded"] is False
    assert event["execution_actor"] == "system"
    assert event["reason_code"] == "simulation_mode"
    assert event["queue_id"] == queue_id
    assert event["alert_id"] == alert_id
    assert event["idempotency_key"] == f"queue-enqueue-{queue_id}"
    assert event["decision_id"] == queue_row["decision_id"]


def test_enqueue_committed_alerts_decision_source_detection_default(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()

    enqueue_committed_alerts([_make_alert(alert_id)], conn)
    conn.commit()

    event = outcomes.get_latest_outcome_for_alert(conn, alert_id)
    assert event is not None
    decision = outcomes._fetch_decision_by_id(conn, event["decision_id"])
    assert decision["decision_source"] == "detection_default"


def test_enqueue_committed_alerts_decision_source_correlation_for_correlated_activity(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()

    enqueue_committed_alerts(
        [_make_alert(alert_id, action="flag_high_priority", alert_type="correlated_activity")],
        conn,
    )
    conn.commit()

    event = outcomes.get_latest_outcome_for_alert(conn, alert_id)
    decision = outcomes._fetch_decision_by_id(conn, event["decision_id"])
    assert decision["decision_source"] == "correlation"


def test_enqueue_committed_alerts_duplicate_does_not_create_duplicate_canonical_records(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()

    alert = _make_alert(alert_id, source_ip="10.20.30.40", action="monitor")
    first = enqueue_committed_alerts([alert], conn)
    conn.commit()

    second = enqueue_committed_alerts([alert], conn)
    conn.commit()

    assert first[0]["status"] == "enqueued"
    assert second[0]["status"] == "duplicate_skipped"
    assert second[0]["queue_id"] is None

    # Only one decision and one event should exist for this alert
    cur.execute(
        "SELECT COUNT(*) FROM soar_response_decisions WHERE alert_id = %s",
        (alert_id,),
    )
    assert cur.fetchone()[0] == 1

    cur.execute(
        "SELECT COUNT(*) FROM soar_response_outcome_events WHERE alert_id = %s",
        (alert_id,),
    )
    assert cur.fetchone()[0] == 1


def test_enqueue_committed_alerts_idempotency_key_deduplicated_on_retry(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()

    results = enqueue_committed_alerts([_make_alert(alert_id)], conn)
    conn.commit()

    queue_id = results[0]["queue_id"]
    decision_id = get_queue_action(conn, queue_id)["decision_id"]

    # Simulate retry: append again with same idempotency key
    second_event = outcomes.append_outcome_event(
        conn,
        decision_id=decision_id,
        execution_mode="simulation",
        execution_state="queued",
        execution_actor="system",
        simulated=True,
        outcome_summary="duplicate attempt",
        queue_id=queue_id,
        idempotency_key=f"queue-enqueue-{queue_id}",
    )
    conn.commit()

    first_event = outcomes.get_latest_outcome_for_queue(conn, queue_id)
    # idempotency key returns the existing row, not a new one
    assert second_event["id"] == first_event["id"]
    assert second_event["outcome_summary"] != "duplicate attempt"

    cur.execute(
        "SELECT COUNT(*) FROM soar_response_outcome_events WHERE queue_id = %s",
        (queue_id,),
    )
    assert cur.fetchone()[0] == 1


def test_enqueue_missing_response_action_skips_without_canonical_write(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()

    results = enqueue_committed_alerts(
        [{"alert_id": alert_id, "source_ip": "10.20.30.40"}],
        conn,
    )
    conn.commit()

    assert results[0]["status"] == "skipped"
    assert results[0]["skip_reason"] == "missing_response_action"

    cur.execute(
        "SELECT COUNT(*) FROM soar_response_decisions WHERE alert_id = %s",
        (alert_id,),
    )
    assert cur.fetchone()[0] == 0


# ---------------------------------------------------------------------------
# Phase 6 Slice 1: serialize_latest_outcome, serialize_outcome_timeline,
# get_latest_outcomes_for_alerts_bulk
# ---------------------------------------------------------------------------


def _make_decision_with_event(
    conn,
    cur,
    *,
    source_ip="10.20.30.40",
    decision_summary="Decision created.",
    event_summary="Event outcome text.",
    execution_mode="simulation",
    execution_state="succeeded",
    simulated=True,
    external_executed=False,
    tracking_recorded=False,
    execution_actor="queue_worker",
    reason_code="simulation_mode",
):
    alert_id = _insert_alert(cur, source_ip=source_ip)
    conn.commit()
    decision = outcomes.create_response_decision(
        conn,
        alert_id=alert_id,
        selected_action="monitor",
        decision_source="manual",
        outcome_summary=decision_summary,
    )
    conn.commit()
    event = outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        execution_mode=execution_mode,
        execution_state=execution_state,
        simulated=simulated,
        external_executed=external_executed,
        tracking_recorded=tracking_recorded,
        execution_actor=execution_actor,
        outcome_summary=event_summary,
        reason_code=reason_code,
    )
    conn.commit()
    return alert_id, decision, event


# --- serialize_latest_outcome ---


@pytest.mark.usefixtures("postgres_db")
def test_serialize_latest_outcome_returns_decision_6_shape(postgres_db):
    conn, cur = postgres_db
    alert_id, decision, event = _make_decision_with_event(conn, cur)

    result = outcomes.serialize_latest_outcome(conn, decision_id=decision["id"])

    assert result is not None
    assert result["soar_correlation_id"] == decision["soar_correlation_id"]
    assert result["decision_id"] == decision["id"]
    assert result["latest_outcome_event_id"] == event["id"]
    assert result["selected_action"] == "monitor"
    assert result["decision_source"] == "manual"
    assert result["execution_mode"] == "simulation"
    assert result["execution_state"] == "succeeded"
    assert result["external_executed"] is False
    assert result["tracking_recorded"] is False
    assert result["simulated"] is True
    assert result["execution_actor"] == "queue_worker"
    assert "related" in result
    assert result["related"]["alert_id"] == alert_id
    assert "timestamps" in result
    assert result["timestamps"]["selected_at"] is not None


@pytest.mark.usefixtures("postgres_db")
def test_serialize_latest_outcome_uses_event_outcome_summary_not_decision(postgres_db):
    conn, cur = postgres_db
    _alert_id, decision, _event = _make_decision_with_event(
        conn,
        cur,
        decision_summary="Decision-level text that must not appear at top level.",
        event_summary="Event-level text that must appear at top level.",
    )

    result = outcomes.serialize_latest_outcome(conn, decision_id=decision["id"])

    assert result is not None
    assert result["outcome_summary"] == "Event-level text that must appear at top level."
    assert result["outcome_summary"] != "Decision-level text that must not appear at top level."


@pytest.mark.usefixtures("postgres_db")
def test_serialize_latest_outcome_returns_none_when_no_decision(postgres_db):
    conn, _cur = postgres_db

    result = outcomes.serialize_latest_outcome(conn, decision_id=999999)

    assert result is None


@pytest.mark.usefixtures("postgres_db")
def test_serialize_latest_outcome_no_events_returns_selected_state(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()
    decision = outcomes.create_response_decision(
        conn,
        alert_id=alert_id,
        selected_action="monitor",
        decision_source="detection_default",
        outcome_summary="Detection selected monitor action.",
    )
    conn.commit()

    result = outcomes.serialize_latest_outcome(conn, decision_id=decision["id"])

    assert result is not None
    assert result["latest_outcome_event_id"] is None
    assert result["execution_mode"] == "observed"
    assert result["execution_state"] == "selected"
    assert result["external_executed"] is False
    assert result["tracking_recorded"] is False
    assert result["simulated"] is False
    assert result["execution_actor"] is None
    assert result["outcome_summary"] == "Detection selected monitor action."
    assert result["timestamps"]["occurred_at"] is None


@pytest.mark.usefixtures("postgres_db")
def test_serialize_latest_outcome_by_correlation_id(postgres_db):
    conn, cur = postgres_db
    alert_id, decision, event = _make_decision_with_event(conn, cur)

    result = outcomes.serialize_latest_outcome(
        conn, soar_correlation_id=decision["soar_correlation_id"]
    )

    assert result is not None
    assert result["decision_id"] == decision["id"]
    assert result["latest_outcome_event_id"] == event["id"]


@pytest.mark.usefixtures("postgres_db")
def test_serialize_latest_outcome_by_alert_id(postgres_db):
    conn, cur = postgres_db
    alert_id, decision, event = _make_decision_with_event(conn, cur)

    result = outcomes.serialize_latest_outcome(conn, alert_id=alert_id)

    assert result is not None
    assert result["decision_id"] == decision["id"]
    assert result["related"]["alert_id"] == alert_id


@pytest.mark.usefixtures("postgres_db")
def test_serialize_latest_outcome_alert_id_no_decision_returns_none(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()

    result = outcomes.serialize_latest_outcome(conn, alert_id=alert_id)

    assert result is None


@pytest.mark.usefixtures("postgres_db")
def test_serialize_latest_outcome_requires_at_least_one_lookup_arg(postgres_db):
    conn, _cur = postgres_db
    with pytest.raises(outcomes.SoarResponseOutcomeValidationError):
        outcomes.serialize_latest_outcome(conn)


@pytest.mark.usefixtures("postgres_db")
def test_serialize_latest_outcome_includes_all_related_fields(postgres_db):
    conn, cur = postgres_db
    _alert_id, decision, _event = _make_decision_with_event(conn, cur)

    result = outcomes.serialize_latest_outcome(conn, decision_id=decision["id"])

    related = result["related"]
    for key in (
        "alert_id",
        "incident_id",
        "queue_id",
        "playbook_id",
        "playbook_execution_id",
        "playbook_step_index",
        "approval_request_id",
        "notification_delivery_attempt_id",
        "response_action_log_id",
    ):
        assert key in related, f"missing related field: {key}"


# --- serialize_outcome_timeline ---


@pytest.mark.usefixtures("postgres_db")
def test_serialize_outcome_timeline_ordered_oldest_first(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()
    decision = outcomes.create_response_decision(
        conn,
        alert_id=alert_id,
        selected_action="monitor",
        decision_source="manual",
        outcome_summary="test",
    )
    conn.commit()

    older_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    middle_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    newest_time = datetime.now(timezone.utc) - timedelta(minutes=1)

    for summary, occurred_at in (
        ("first event", older_time),
        ("middle event", middle_time),
        ("newest event", newest_time),
    ):
        outcomes.append_outcome_event(
            conn,
            decision_id=decision["id"],
            execution_mode="simulation",
            execution_state="queued",
            execution_actor="queue_worker",
            outcome_summary=summary,
            occurred_at=occurred_at,
        )
    conn.commit()

    timeline = outcomes.serialize_outcome_timeline(conn, decision["id"])

    assert len(timeline) == 3
    assert timeline[0]["outcome_summary"] == "first event"
    assert timeline[1]["outcome_summary"] == "middle event"
    assert timeline[2]["outcome_summary"] == "newest event"


@pytest.mark.usefixtures("postgres_db")
def test_serialize_outcome_timeline_empty_when_no_decision(postgres_db):
    conn, _cur = postgres_db

    timeline = outcomes.serialize_outcome_timeline(conn, 999999)

    assert timeline == []


@pytest.mark.usefixtures("postgres_db")
def test_serialize_outcome_timeline_empty_when_no_events(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()
    decision = outcomes.create_response_decision(
        conn,
        alert_id=alert_id,
        selected_action="monitor",
        decision_source="manual",
        outcome_summary="no events yet",
    )
    conn.commit()

    timeline = outcomes.serialize_outcome_timeline(conn, decision["id"])

    assert timeline == []


@pytest.mark.usefixtures("postgres_db")
def test_serialize_outcome_timeline_limit_respected(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()
    decision = outcomes.create_response_decision(
        conn,
        alert_id=alert_id,
        selected_action="monitor",
        decision_source="manual",
        outcome_summary="test",
    )
    conn.commit()

    for i in range(5):
        outcomes.append_outcome_event(
            conn,
            decision_id=decision["id"],
            execution_mode="simulation",
            execution_state="queued",
            execution_actor="system",
            outcome_summary=f"event {i}",
        )
    conn.commit()

    timeline = outcomes.serialize_outcome_timeline(conn, decision["id"], limit=3)
    assert len(timeline) == 3


# --- get_latest_outcomes_for_alerts_bulk ---


@pytest.mark.usefixtures("postgres_db")
def test_get_latest_outcomes_for_alerts_bulk_returns_map_by_alert_id(postgres_db):
    conn, cur = postgres_db
    alert_id_a, decision_a, event_a = _make_decision_with_event(
        conn, cur, event_summary="event for alert A"
    )
    alert_id_b, decision_b, event_b = _make_decision_with_event(
        conn, cur, event_summary="event for alert B"
    )

    result = outcomes.get_latest_outcomes_for_alerts_bulk(conn, [alert_id_a, alert_id_b])

    assert alert_id_a in result
    assert alert_id_b in result
    assert result[alert_id_a]["outcome_summary"] == "event for alert A"
    assert result[alert_id_b]["outcome_summary"] == "event for alert B"
    assert result[alert_id_a]["alert_id"] == alert_id_a
    assert result[alert_id_b]["alert_id"] == alert_id_b


@pytest.mark.usefixtures("postgres_db")
def test_get_latest_outcomes_for_alerts_bulk_returns_latest_per_alert(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    conn.commit()
    decision = outcomes.create_response_decision(
        conn,
        alert_id=alert_id,
        selected_action="monitor",
        decision_source="manual",
        outcome_summary="test",
    )
    conn.commit()

    older_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    newer_time = datetime.now(timezone.utc) - timedelta(minutes=1)

    outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        execution_mode="simulation",
        execution_state="queued",
        execution_actor="queue_worker",
        outcome_summary="older event",
        occurred_at=older_time,
    )
    outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        execution_mode="simulation",
        execution_state="succeeded",
        simulated=True,
        execution_actor="queue_worker",
        outcome_summary="newer event",
        occurred_at=newer_time,
    )
    conn.commit()

    result = outcomes.get_latest_outcomes_for_alerts_bulk(conn, [alert_id])

    assert alert_id in result
    assert result[alert_id]["outcome_summary"] == "newer event"
    assert result[alert_id]["execution_state"] == "succeeded"


@pytest.mark.usefixtures("postgres_db")
def test_get_latest_outcomes_for_alerts_bulk_empty_input_returns_empty_dict(postgres_db):
    conn, _cur = postgres_db

    result = outcomes.get_latest_outcomes_for_alerts_bulk(conn, [])

    assert result == {}


@pytest.mark.usefixtures("postgres_db")
def test_get_latest_outcomes_for_alerts_bulk_missing_alert_absent_from_result(postgres_db):
    conn, cur = postgres_db
    alert_id_with_events, _decision, _event = _make_decision_with_event(conn, cur)
    alert_id_no_events = _insert_alert(cur)
    conn.commit()

    result = outcomes.get_latest_outcomes_for_alerts_bulk(
        conn, [alert_id_with_events, alert_id_no_events]
    )

    assert alert_id_with_events in result
    assert alert_id_no_events not in result


@pytest.mark.usefixtures("postgres_db")
def test_get_latest_outcomes_for_alerts_bulk_all_missing_returns_empty_dict(postgres_db):
    conn, _cur = postgres_db

    result = outcomes.get_latest_outcomes_for_alerts_bulk(conn, [999991, 999992, 999993])

    assert result == {}
