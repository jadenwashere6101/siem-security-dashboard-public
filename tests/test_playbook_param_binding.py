import pytest

from engines.playbook_param_binding import (
    PlaybookParamBindingError,
    parse_binding_expression,
    resolve_step_params,
    validate_param_binding_value,
    validate_step_param_bindings,
)
from engines.playbook_registry import validate_playbook_steps


def test_parse_binding_expression_alert_field():
    assert parse_binding_expression("{{alert.source_ip}}") == ("alert", "source_ip")


def test_parse_binding_expression_execution_field():
    assert parse_binding_expression("{{execution.id}}") == ("execution", "id")


def test_parse_binding_expression_static_value():
    assert parse_binding_expression("10.0.0.1") is None
    assert parse_binding_expression("Block {{alert.source_ip}} now") is None


def test_validate_param_binding_rejects_unknown_alert_field():
    errors = validate_param_binding_value(
        "{{alert.nonexistent_field}}",
        prefix="step[0].params.source_ip",
    )
    assert errors
    assert "unsupported alert binding field" in errors[0]


def test_validate_param_binding_rejects_malformed_expression():
    errors = validate_param_binding_value(
        "{{alert.source_ip",
        prefix="step[0].params.source_ip",
    )
    assert errors
    assert "invalid binding expression" in errors[0]


def test_validate_param_binding_accepts_supported_alert_field():
    assert (
        validate_param_binding_value(
            "{{alert.source_ip}}",
            prefix="step[0].params.source_ip",
        )
        == []
    )


def test_validate_playbook_steps_accepts_dynamic_block_ip_binding():
    steps = [{"action": "block_ip", "params": {"source_ip": "{{alert.source_ip}}"}}]
    assert validate_playbook_steps(steps) == []


def test_validate_playbook_steps_rejects_unknown_binding_field():
    steps = [{"action": "block_ip", "params": {"source_ip": "{{alert.nonexistent_field}}"}}]
    errors = validate_playbook_steps(steps)
    assert errors
    assert any("unsupported alert binding field" in error for error in errors)


def test_resolve_step_params_static_values_unchanged():
    params = {"message": "static text", "timeout": 30}
    resolved = resolve_step_params(
        None,
        params,
        execution={"id": 1, "playbook_id": "pb", "alert_id": 99},
    )
    assert resolved == params


def test_resolve_step_params_mixed_static_and_dynamic(postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message, status)
        VALUES ('test_alert', 'critical', '198.51.100.55'::inet, 'alert body', 'open')
        RETURNING id
        """
    )
    alert_id = cur.fetchone()[0]

    resolved = resolve_step_params(
        conn,
        {
            "source_ip": "{{alert.source_ip}}",
            "message": "static notification",
        },
        execution={"id": 7, "playbook_id": "pb_bind", "alert_id": alert_id},
    )

    assert resolved["source_ip"] == "198.51.100.55"
    assert resolved["message"] == "static notification"


def test_resolve_step_params_missing_nullable_field_fails(postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message)
        VALUES ('test_alert', 'low', '10.0.0.2'::inet, 'msg')
        RETURNING id
        """
    )
    alert_id = cur.fetchone()[0]

    with pytest.raises(PlaybookParamBindingError) as exc_info:
        resolve_step_params(
            conn,
            {"message": "{{alert.reputation_score}}"},
            execution={"id": 1, "playbook_id": "pb", "alert_id": alert_id},
        )

    assert exc_info.value.code == "binding_field_missing"


def test_resolve_step_params_missing_alert_context_fails():
    with pytest.raises(PlaybookParamBindingError) as exc_info:
        resolve_step_params(
            None,
            {"source_ip": "{{alert.source_ip}}"},
            execution={"id": 1, "playbook_id": "pb", "alert_id": None},
        )

    assert exc_info.value.code == "binding_alert_context_missing"


def test_validate_step_param_bindings_ignores_non_dict_params():
    assert validate_step_param_bindings({"params": "bad"}, prefix="step[0]") == []
