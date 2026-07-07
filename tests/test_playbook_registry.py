from engines.playbook_registry import (
    ADAPTER_ACTIONS,
    KNOWN_PLAYBOOK_ACTIONS,
    SUPPORTED_ACTIONS,
    validate_playbook_steps,
)


def test_validate_empty_steps():
    assert validate_playbook_steps([]) == []


def test_validate_supported_actions_ok():
    steps = [
        {"action": "block_ip", "params": {}},
        {"action": "monitor", "on_failure": "continue"},
        {"action": "flag_high_priority"},
        {"action": "notify_slack", "params": {"message": "hello"}},
        {"action": "notify_teams", "params": {"message": "hello"}},
        {"action": "notify_email", "params": {"subject": "alert"}},
        {"action": "notify_webhook", "params": {"payload": {"event": "alert"}}},
        {
            "action": "require_approval",
            "risk_level": "critical",
            "reason": "Approve simulated containment",
            "expires_in_minutes": 30,
            "on_denied": "fail",
            "on_expired": "fail",
        },
    ]
    assert validate_playbook_steps(steps) == []


def test_validate_require_approval_options():
    assert validate_playbook_steps([{"action": "require_approval"}]) == []

    errors = validate_playbook_steps(
        [
            {
                "action": "require_approval",
                "risk_level": "low",
                "expires_in_minutes": 0,
                "reason": {"not": "text"},
                "on_denied": "continue",
                "on_expired": "ignore",
            }
        ]
    )
    assert len(errors) == 5
    assert any("risk_level" in error for error in errors)
    assert any("expires_in_minutes" in error for error in errors)
    assert any("reason" in error for error in errors)
    assert any("on_denied" in error for error in errors)
    assert any("on_expired" in error for error in errors)


def test_validate_unknown_action():
    errors = validate_playbook_steps([{"action": "notify_pagerduty"}])
    assert errors
    assert "unsupported action" in errors[0].lower()


def test_validate_missing_action_key():
    errors = validate_playbook_steps([{"params": {}}])
    assert errors
    assert "action" in errors[0].lower()


def test_validate_invalid_on_failure():
    errors = validate_playbook_steps([{"action": "block_ip", "on_failure": "retry"}])
    assert errors
    assert "on_failure" in errors[0].lower()


def test_validate_dynamic_binding_on_block_ip():
    steps = [{"action": "block_ip", "params": {"source_ip": "{{alert.source_ip}}"}}]
    assert validate_playbook_steps(steps) == []


def test_validate_rejects_unknown_binding_field():
    errors = validate_playbook_steps(
        [{"action": "block_ip", "params": {"source_ip": "{{alert.nonexistent_field}}"}}]
    )
    assert errors
    assert any("unsupported alert binding field" in error for error in errors)


def test_validate_rejects_malformed_binding_expression():
    errors = validate_playbook_steps(
        [{"action": "notify_slack", "params": {"message": "Alert from {{alert.source_ip}}"}}]
    )
    assert errors
    assert any("invalid binding expression" in error for error in errors)


def test_validate_branch_playbook_and_approval_branch_option():
    steps = [
        {
            "action": "require_approval",
            "on_denied": "branch",
            "on_expired": "branch",
        },
        {
            "action": "branch",
            "condition": {
                "source": "approval",
                "field": "status",
                "op": "==",
                "value": "denied",
            },
            "goto_true": "notify_denied",
        },
        {"label": "notify_denied", "action": "monitor"},
    ]
    assert validate_playbook_steps(steps) == []


def test_validate_rejects_unknown_branch_goto_label():
    errors = validate_playbook_steps(
        [
            {
                "action": "branch",
                "condition": {
                    "source": "alert",
                    "field": "severity",
                    "op": ">=",
                    "value": "high",
                },
                "goto_true": "missing_label",
            }
        ]
    )
    assert errors
    assert any("unknown label" in error for error in errors)


def test_supported_actions_is_frozen():
    assert SUPPORTED_ACTIONS is KNOWN_PLAYBOOK_ACTIONS
    assert isinstance(SUPPORTED_ACTIONS, frozenset)
    assert "block_ip" in SUPPORTED_ACTIONS
    assert "require_approval" in SUPPORTED_ACTIONS
    assert "notify_slack" in SUPPORTED_ACTIONS
    assert "notify_teams" in SUPPORTED_ACTIONS
    assert "notify_email" in SUPPORTED_ACTIONS
    assert "notify_webhook" in SUPPORTED_ACTIONS


def test_known_playbook_actions_include_adapter_actions():
    assert set(ADAPTER_ACTIONS).issubset(KNOWN_PLAYBOOK_ACTIONS)
