import pytest

from engines.playbook_branch_conditions import (
    PlaybookBranchConditionError,
    build_label_index_map,
    evaluate_branch_condition,
    validate_branch_condition,
    validate_branch_step,
)
from engines.playbook_registry import validate_playbook_steps


def test_validate_branch_condition_accepts_alert_severity():
    assert (
        validate_branch_condition(
            {
                "source": "alert",
                "field": "severity",
                "op": ">=",
                "value": "high",
            },
            prefix="step[0].condition",
        )
        == []
    )


def test_validate_branch_condition_rejects_unknown_alert_field():
    errors = validate_branch_condition(
        {
            "source": "alert",
            "field": "nonexistent",
            "op": "==",
            "value": "x",
        },
        prefix="step[0].condition",
    )
    assert errors
    assert "unsupported alert condition field" in errors[0]


def test_validate_branch_condition_rejects_ordinal_on_string_field():
    errors = validate_branch_condition(
        {
            "source": "alert",
            "field": "message",
            "op": ">=",
            "value": "x",
        },
        prefix="step[0].condition",
    )
    assert errors
    assert "not valid for alert field" in errors[0]


@pytest.mark.parametrize(
    "condition, expected",
    [
        (
            {"source": "unknown", "field": "severity", "op": "==", "value": "high"},
            "invalid condition.source",
        ),
        (
            {"source": "alert", "field": "reputation_score", "op": ">=", "value": "high"},
            "condition.value must be a number",
        ),
        (
            {"source": "previous_step", "field": "action", "op": "==", "value": "success"},
            "previous_step conditions must use field 'status'",
        ),
        (
            {"source": "previous_step", "field": "status", "op": ">=", "value": "success"},
            "previous_step conditions support only",
        ),
        (
            {"source": "approval", "field": "status", "op": "==", "value": "pending"},
            "approval condition value must be one of",
        ),
    ],
)
def test_validate_branch_condition_rejects_invalid_shapes(condition, expected):
    errors = validate_branch_condition(condition, prefix="step[0].condition")
    assert errors
    assert expected in errors[0]


def test_validate_branch_step_rejects_backward_jump():
    steps = [
        {"label": "target", "action": "monitor"},
        {
            "action": "branch",
            "condition": {
                "source": "alert",
                "field": "severity",
                "op": ">=",
                "value": "high",
            },
            "goto_true": "target",
        },
    ]
    errors = validate_branch_step(steps[1], step_index=1, label_map=build_label_index_map(steps))
    assert errors
    assert "not forward" in errors[0]


def test_validate_playbook_steps_rejects_duplicate_labels():
    steps = [
        {"label": "dup", "action": "monitor"},
        {"label": "dup", "action": "monitor"},
    ]
    errors = validate_playbook_steps(steps)
    assert any("duplicate label" in error for error in errors)


def test_validate_playbook_steps_accepts_valid_branch_playbook():
    steps = [
        {"action": "monitor"},
        {
            "action": "branch",
            "condition": {
                "source": "alert",
                "field": "severity",
                "op": ">=",
                "value": "high",
            },
            "goto_true": "contain",
        },
        {"label": "contain", "action": "flag_high_priority"},
    ]
    assert validate_playbook_steps(steps) == []


def test_validate_playbook_steps_rejects_invalid_label():
    errors = validate_playbook_steps([{"label": "Bad-Label", "action": "monitor"}])
    assert any("invalid label" in error for error in errors)


def test_validate_playbook_steps_rejects_missing_branch_fields():
    errors = validate_playbook_steps([{"action": "branch"}])
    assert any("requires condition" in error for error in errors)
    assert any("requires non-empty goto_true" in error for error in errors)


def test_evaluate_alert_severity_condition(postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message)
        VALUES ('failed_login_threshold', 'critical', '10.0.0.5'::inet, 'msg')
        RETURNING id
        """
    )
    alert_id = cur.fetchone()[0]
    result = evaluate_branch_condition(
        conn,
        {
            "source": "alert",
            "field": "severity",
            "op": ">=",
            "value": "high",
        },
        execution={"id": 1, "playbook_id": "pb", "alert_id": alert_id},
        steps_log=[],
    )
    assert result is True


def test_evaluate_previous_step_condition_uses_latest_recorded_outcome():
    result = evaluate_branch_condition(
        None,
        {
            "source": "previous_step",
            "field": "status",
            "op": "==",
            "value": "failed",
        },
        execution={"id": 1, "playbook_id": "pb", "alert_id": None},
        steps_log=[
            {"step_index": 0, "action": "monitor", "status": "success"},
            {"step_index": 1, "action": "notify_slack", "status": "skipped"},
            {"step_index": 2, "action": "branch", "status": "success"},
        ],
    )
    assert result is False


def test_evaluate_missing_previous_step_context_fails():
    with pytest.raises(PlaybookBranchConditionError) as exc_info:
        evaluate_branch_condition(
            None,
            {
                "source": "previous_step",
                "field": "status",
                "op": "==",
                "value": "success",
            },
            execution={"id": 1, "playbook_id": "pb", "alert_id": None},
            steps_log=[],
        )
    assert exc_info.value.code == "branch_context_missing"
