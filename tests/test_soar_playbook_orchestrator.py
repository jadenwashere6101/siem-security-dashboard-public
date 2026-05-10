from unittest.mock import patch

from core import playbook_store
from engines.soar_playbook_orchestrator import (
    create_pending_executions_for_committed_alerts,
)


def _valid_steps():
    return [{"action": "monitor", "params": {}}]


def _insert_alert(
    cur,
    *,
    alert_type="password_spraying",
    severity="HIGH",
    source_ip="203.0.113.10",
    source="bank_app",
    reputation_score=90,
):
    cur.execute(
        """
        INSERT INTO alerts (
            alert_type, severity, source_ip, message, source, reputation_score
        )
        VALUES (%s, %s, %s::inet, 'msg', %s, %s)
        RETURNING id
        """,
        (alert_type, severity, source_ip, source, reputation_score),
    )
    return cur.fetchone()[0]


def _count_rows(cur, table):
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    return cur.fetchone()[0]


def test_empty_alert_list_returns_empty_summary(postgres_db):
    conn, _cur = postgres_db
    result = create_pending_executions_for_committed_alerts([], conn)

    assert result["summary"]["processed_alerts"] == 0
    assert result["summary"]["created"] == 0
    assert result["results"] == []


def test_invalid_alert_entries_are_skipped(postgres_db):
    conn, _cur = postgres_db
    result = create_pending_executions_for_committed_alerts(
        [None, {"source_ip": "203.0.113.10"}],
        conn,
    )

    assert result["summary"]["skipped"] == 2
    assert [row["skip_reason"] for row in result["results"]] == [
        "invalid_alert_dict",
        "missing_alert_id",
    ]


def test_no_matching_playbooks_creates_no_executions(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert(cur, alert_type="failed_login")
    playbook_store.create_playbook_definition(
        conn,
        "pb_no_match",
        "No Match",
        steps=_valid_steps(),
        trigger_config={"alert_type": "password_spraying"},
    )

    result = create_pending_executions_for_committed_alerts([{"alert_id": aid}], conn)

    assert result["summary"]["created"] == 0
    assert result["results"][0]["status"] == "no_match"
    assert _count_rows(cur, "playbook_executions") == 0


def test_matching_enabled_playbook_creates_pending_execution(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert(cur)
    playbook_store.create_playbook_definition(
        conn,
        "pb_match",
        "Match",
        steps=_valid_steps(),
        trigger_config={"alert_type": "password_spraying", "min_severity": "HIGH"},
    )

    result = create_pending_executions_for_committed_alerts([{"alert_id": aid}], conn)

    assert result["summary"]["processed_alerts"] == 1
    assert result["summary"]["matched_playbooks"] == 1
    assert result["summary"]["created"] == 1
    assert result["results"][0]["status"] == "created"
    cur.execute(
        """
        SELECT playbook_id, alert_id, status, started_at, completed_at, steps_log
        FROM playbook_executions
        """
    )
    assert cur.fetchall() == [("pb_match", aid, "pending", None, None, [])]


def test_multiple_matches_create_multiple_pending_executions(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert(cur)
    for playbook_id in ["pb_a", "pb_b"]:
        playbook_store.create_playbook_definition(
            conn,
            playbook_id,
            playbook_id,
            steps=_valid_steps(),
            trigger_config={"min_severity": "MEDIUM"},
        )

    result = create_pending_executions_for_committed_alerts([{"alert_id": aid}], conn)

    assert result["summary"]["created"] == 2
    cur.execute("SELECT playbook_id, status FROM playbook_executions ORDER BY playbook_id")
    assert cur.fetchall() == [("pb_a", "pending"), ("pb_b", "pending")]


def test_disabled_playbooks_do_not_create_executions(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert(cur)
    playbook_store.create_playbook_definition(
        conn,
        "pb_disabled",
        "Disabled",
        steps=_valid_steps(),
        trigger_config={"alert_type": "password_spraying"},
        enabled=False,
    )

    result = create_pending_executions_for_committed_alerts([{"alert_id": aid}], conn)

    assert result["summary"]["created"] == 0
    assert _count_rows(cur, "playbook_executions") == 0


def test_repeated_orchestration_does_not_duplicate_rows(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert(cur)
    playbook_store.create_playbook_definition(
        conn,
        "pb_once",
        "Once",
        steps=_valid_steps(),
        trigger_config={"alert_type": "password_spraying"},
    )

    first = create_pending_executions_for_committed_alerts([{"alert_id": aid}], conn)
    second = create_pending_executions_for_committed_alerts([{"alert_id": aid}], conn)

    assert first["summary"]["created"] == 1
    assert second["summary"]["created"] == 0
    assert second["summary"]["duplicates"] == 1
    assert _count_rows(cur, "playbook_executions") == 1


def test_missing_alert_id_is_skipped_safely(postgres_db):
    conn, cur = postgres_db
    result = create_pending_executions_for_committed_alerts([{"alert_id": 999999}], conn)

    assert result["summary"]["created"] == 0
    assert result["results"][0]["status"] == "no_match"
    assert _count_rows(cur, "playbook_executions") == 0


def test_match_exception_is_caught_and_reported(postgres_db):
    conn, _cur = postgres_db

    with patch("engines.soar_playbook_orchestrator.match_playbooks", side_effect=RuntimeError("boom")):
        result = create_pending_executions_for_committed_alerts([{"alert_id": 1}], conn)

    assert result["summary"]["errors"] == 1
    assert result["results"][0]["status"] == "error"
    assert result["results"][0]["error_type"] == "RuntimeError"


def test_insert_exception_is_caught_and_reported(postgres_db):
    conn, _cur = postgres_db

    with patch(
        "engines.soar_playbook_orchestrator.match_playbooks",
        return_value=[{"id": "pb_error"}],
    ), patch(
        "engines.soar_playbook_orchestrator.create_pending_playbook_execution_once",
        side_effect=RuntimeError("insert boom"),
    ):
        result = create_pending_executions_for_committed_alerts([{"alert_id": 1}], conn)

    assert result["summary"]["errors"] == 1
    assert result["results"][0]["status"] == "error"
    assert result["results"][0]["error_type"] == "RuntimeError"


def test_orchestrator_does_not_create_queue_logs_or_approvals(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert(cur)
    playbook_store.create_playbook_definition(
        conn,
        "pb_safe",
        "Safe",
        steps=_valid_steps(),
        trigger_config={"alert_type": "password_spraying"},
    )
    before = {
        "response_actions_queue": _count_rows(cur, "response_actions_queue"),
        "response_actions_log": _count_rows(cur, "response_actions_log"),
        "approval_requests": _count_rows(cur, "approval_requests"),
    }

    with patch("core.playbook_store.update_execution_status") as update_status:
        result = create_pending_executions_for_committed_alerts([{"alert_id": aid}], conn)

    assert result["summary"]["created"] == 1
    update_status.assert_not_called()
    for table, expected in before.items():
        assert _count_rows(cur, table) == expected
