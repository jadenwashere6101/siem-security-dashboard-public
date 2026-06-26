from unittest.mock import MagicMock, call, patch

from engines.soar_enqueue_orchestrator import enqueue_committed_alerts


def make_conn():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    return conn, cur


def test_enqueue_committed_alerts_success_for_supported_actions():
    conn, cur = make_conn()
    alerts = [
        {"alert_id": 1, "source_ip": "1.2.3.4", "response_action": "block_ip"},
        {"alert_id": 2, "source_ip": "1.2.3.5", "response_action": "flag_high_priority"},
        {"alert_id": 3, "source_ip": "1.2.3.6", "response_action": "monitor"},
    ]

    with patch(
        "engines.soar_enqueue_orchestrator.enqueue_response_action",
        side_effect=[101, 102, 103],
    ) as enqueue:
        results = enqueue_committed_alerts(alerts, conn)

    assert [result["status"] for result in results] == ["enqueued", "enqueued", "enqueued"]
    assert [result["queue_id"] for result in results] == [101, 102, 103]
    assert enqueue.call_count == 3
    enqueue.assert_any_call(cur, 1, "1.2.3.4", "block_ip")
    enqueue.assert_any_call(cur, 2, "1.2.3.5", "flag_high_priority")
    enqueue.assert_any_call(cur, 3, "1.2.3.6", "monitor")
    conn.commit.assert_not_called()
    conn.rollback.assert_not_called()


def test_enqueue_committed_alerts_duplicate_returns_skipped_result():
    conn, _cur = make_conn()
    alert = {"alert_id": 1, "source_ip": "1.2.3.4", "response_action": "block_ip"}

    with patch(
        "engines.soar_enqueue_orchestrator.enqueue_response_action",
        return_value=None,
    ):
        results = enqueue_committed_alerts([alert], conn)

    assert results == [
        {
            "alert_id": 1,
            "source_ip": "1.2.3.4",
            "action": "block_ip",
            "queue_id": None,
            "skipped": True,
            "status": "duplicate_skipped",
            "skip_reason": "duplicate",
            "index": 0,
        }
    ]
    conn.commit.assert_not_called()
    conn.rollback.assert_not_called()


def test_enqueue_committed_alerts_missing_alert_id_skips_without_enqueue():
    conn, _cur = make_conn()
    alert = {"source_ip": "1.2.3.4", "response_action": "block_ip"}

    with patch("engines.soar_enqueue_orchestrator.enqueue_response_action") as enqueue:
        results = enqueue_committed_alerts([alert], conn)

    enqueue.assert_not_called()
    assert results[0]["skipped"] is True
    assert results[0]["status"] == "skipped"
    assert results[0]["skip_reason"] == "missing_alert_id"


def test_enqueue_committed_alerts_missing_source_ip_skips_without_enqueue():
    conn, _cur = make_conn()
    alert = {"alert_id": 1, "response_action": "block_ip"}

    with patch("engines.soar_enqueue_orchestrator.enqueue_response_action") as enqueue:
        results = enqueue_committed_alerts([alert], conn)

    enqueue.assert_not_called()
    assert results[0]["skipped"] is True
    assert results[0]["skip_reason"] == "missing_source_ip"


def test_enqueue_committed_alerts_missing_response_action_skips_without_enqueue():
    conn, _cur = make_conn()
    alert = {"alert_id": 1, "source_ip": "1.2.3.4"}

    with patch("engines.soar_enqueue_orchestrator.enqueue_response_action") as enqueue:
        results = enqueue_committed_alerts([alert], conn)

    enqueue.assert_not_called()
    assert results[0]["skipped"] is True
    assert results[0]["skip_reason"] == "missing_response_action"


def test_enqueue_committed_alerts_enqueue_exception_returns_error_and_logs(caplog):
    conn, _cur = make_conn()
    alert = {"alert_id": 1, "source_ip": "1.2.3.4", "response_action": "block_ip"}

    with patch(
        "engines.soar_enqueue_orchestrator.enqueue_response_action",
        side_effect=RuntimeError("database unavailable"),
    ):
        results = enqueue_committed_alerts([alert], conn)

    assert results[0]["skipped"] is True
    assert results[0]["status"] == "error"
    assert results[0]["skip_reason"] == "enqueue_exception"
    assert results[0]["error_type"] == "RuntimeError"
    assert "database unavailable" in results[0]["error"]
    assert "[SOAR ENQUEUE FAILED]" in caplog.text
    conn.commit.assert_not_called()
    conn.rollback.assert_not_called()


def test_enqueue_committed_alerts_mixed_list_returns_result_per_alert():
    conn, _cur = make_conn()
    alerts = [
        {"alert_id": 1, "source_ip": "1.2.3.4", "response_action": "block_ip"},
        {"source_ip": "1.2.3.5", "response_action": "monitor"},
    ]

    with patch(
        "engines.soar_enqueue_orchestrator.enqueue_response_action",
        return_value=101,
    ) as enqueue:
        results = enqueue_committed_alerts(alerts, conn)

    enqueue.assert_called_once()
    assert len(results) == 2
    assert results[0]["status"] == "enqueued"
    assert results[1]["status"] == "skipped"
    assert results[1]["skip_reason"] == "missing_alert_id"


def test_enqueue_committed_alerts_empty_list_returns_empty_result():
    conn, _cur = make_conn()

    with patch("engines.soar_enqueue_orchestrator.enqueue_response_action") as enqueue:
        results = enqueue_committed_alerts([], conn)

    assert results == []
    enqueue.assert_not_called()
    conn.commit.assert_not_called()
    conn.rollback.assert_not_called()


# ---------------------------------------------------------------------------
# Phase 4 Slice 3: canonical enqueue outcome unit tests
# ---------------------------------------------------------------------------

_MOCK_DECISION = {
    "id": 7,
    "soar_correlation_id": "soar-1-abc123abc123",
    "selected_action": "monitor",
    "decision_source": "detection_default",
    "alert_id": 1,
    "source_ip": "1.2.3.4",
}


def _canonical_patches(queue_id=99, decision=None):
    if decision is None:
        decision = {**_MOCK_DECISION, "queue_id": queue_id}
    return (
        patch("engines.soar_enqueue_orchestrator.enqueue_response_action", return_value=queue_id),
        patch(
            "engines.soar_enqueue_orchestrator.outcomes.create_response_decision",
            return_value=decision,
        ),
        patch("engines.soar_enqueue_orchestrator.set_queue_linkage"),
        patch("engines.soar_enqueue_orchestrator.outcomes.append_outcome_event"),
    )


def test_enqueue_new_queue_calls_create_response_decision():
    conn, _cur = make_conn()
    alert = {"alert_id": 1, "source_ip": "1.2.3.4", "response_action": "monitor"}

    p_enqueue, p_decision, p_linkage, p_event = _canonical_patches()
    with p_enqueue, p_decision as mock_dec, p_linkage, p_event:
        results = enqueue_committed_alerts([alert], conn)

    assert results[0]["status"] == "enqueued"
    assert results[0]["queue_id"] == 99
    mock_dec.assert_called_once()
    kw = mock_dec.call_args[1]
    assert kw["alert_id"] == 1
    assert kw["source_ip"] == "1.2.3.4"
    assert kw["selected_action"] == "monitor"
    assert kw["decision_source"] == "detection_default"
    assert kw["queue_id"] == 99


def test_enqueue_new_queue_calls_set_queue_linkage():
    conn, _cur = make_conn()
    alert = {"alert_id": 1, "source_ip": "1.2.3.4", "response_action": "block_ip"}

    p_enqueue, p_decision, p_linkage, p_event = _canonical_patches(queue_id=55)
    with p_enqueue, p_decision, p_linkage as mock_link, p_event:
        enqueue_committed_alerts([alert], conn)

    mock_link.assert_called_once_with(
        conn,
        55,
        decision_id=7,
        soar_correlation_id="soar-1-abc123abc123",
    )


def test_enqueue_new_queue_appends_queued_simulation_event():
    conn, _cur = make_conn()
    alert = {"alert_id": 1, "source_ip": "1.2.3.4", "response_action": "flag_high_priority"}

    p_enqueue, p_decision, p_linkage, p_event = _canonical_patches(queue_id=77)
    with p_enqueue, p_decision, p_linkage, p_event as mock_ev:
        enqueue_committed_alerts([alert], conn)

    mock_ev.assert_called_once()
    kw = mock_ev.call_args[1]
    assert kw["execution_mode"] == "simulation"
    assert kw["execution_state"] == "queued"
    assert kw["execution_actor"] == "system"
    assert kw["simulated"] is True
    assert kw["external_executed"] is False
    assert kw["tracking_recorded"] is False
    assert kw["reason_code"] == "simulation_mode"
    assert kw["queue_id"] == 77
    assert kw["alert_id"] == 1
    assert kw["idempotency_key"] == "queue-enqueue-77"


def test_enqueue_correlation_alert_uses_correlation_decision_source():
    conn, _cur = make_conn()
    alert = {
        "alert_id": 2,
        "source_ip": "5.6.7.8",
        "response_action": "flag_high_priority",
        "alert_type": "correlated_activity",
    }

    p_enqueue, p_decision, p_linkage, p_event = _canonical_patches(queue_id=88)
    with p_enqueue, p_decision as mock_dec, p_linkage, p_event:
        enqueue_committed_alerts([alert], conn)

    kw = mock_dec.call_args[1]
    assert kw["decision_source"] == "correlation"


def test_enqueue_duplicate_does_not_call_canonical_helpers():
    conn, _cur = make_conn()
    alert = {"alert_id": 1, "source_ip": "1.2.3.4", "response_action": "block_ip"}

    p_enqueue, p_decision, p_linkage, p_event = _canonical_patches(queue_id=None)
    with p_enqueue, p_decision as mock_dec, p_linkage as mock_link, p_event as mock_ev:
        results = enqueue_committed_alerts([alert], conn)

    assert results[0]["status"] == "duplicate_skipped"
    mock_dec.assert_not_called()
    mock_link.assert_not_called()
    mock_ev.assert_not_called()


def test_enqueue_canonical_error_does_not_prevent_enqueued_result(caplog):
    conn, _cur = make_conn()
    alert = {"alert_id": 1, "source_ip": "1.2.3.4", "response_action": "monitor"}

    with patch(
        "engines.soar_enqueue_orchestrator.enqueue_response_action", return_value=42
    ), patch(
        "engines.soar_enqueue_orchestrator.outcomes.create_response_decision",
        side_effect=RuntimeError("db unavailable"),
    ):
        results = enqueue_committed_alerts([alert], conn)

    assert results[0]["status"] == "enqueued"
    assert results[0]["queue_id"] == 42
    assert "[SOAR CANONICAL OUTCOME FAILED]" in caplog.text


def test_enqueue_return_shape_unchanged_for_valid_alert():
    conn, _cur = make_conn()
    alert = {"alert_id": 3, "source_ip": "9.9.9.9", "response_action": "monitor"}

    p_enqueue, p_decision, p_linkage, p_event = _canonical_patches(queue_id=200)
    with p_enqueue, p_decision, p_linkage, p_event:
        results = enqueue_committed_alerts([alert], conn)

    result = results[0]
    assert result["alert_id"] == 3
    assert result["source_ip"] == "9.9.9.9"
    assert result["action"] == "monitor"
    assert result["queue_id"] == 200
    assert result["skipped"] is False
    assert result["status"] == "enqueued"
    assert result["skip_reason"] is None
    assert result["index"] == 0


def test_enqueue_multiple_alerts_calls_canonical_helpers_per_new_queue():
    conn, _cur = make_conn()
    alerts = [
        {"alert_id": 1, "source_ip": "1.1.1.1", "response_action": "monitor"},
        {"alert_id": 2, "source_ip": "2.2.2.2", "response_action": "block_ip"},
    ]

    p_enqueue, p_decision, p_linkage, p_event = _canonical_patches()
    with patch(
        "engines.soar_enqueue_orchestrator.enqueue_response_action",
        side_effect=[10, 11],
    ), p_decision as mock_dec, p_linkage, p_event as mock_ev:
        results = enqueue_committed_alerts(alerts, conn)

    assert all(r["status"] == "enqueued" for r in results)
    assert mock_dec.call_count == 2
    assert mock_ev.call_count == 2
