from unittest.mock import MagicMock, patch

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
