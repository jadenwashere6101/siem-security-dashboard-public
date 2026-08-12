from __future__ import annotations

from dataclasses import replace

import pytest

from core.ai.config import (
    AI_MODE_AUTOMATIC_FALLBACK,
    AI_MODE_LOCAL_ONLY,
    AiGatewayConfig,
    AiGatewayConfigurationError,
    load_ai_gateway_config,
    validate_ai_gateway_startup,
)
from core.ai.gateway import AiGateway
from core.ai.models import (
    AI_STATUS_CONFIGURATION_ERROR,
    AI_STATUS_DISABLED,
    AI_STATUS_FALLBACK_BLOCKED,
    AI_STATUS_PROVIDER_AUTHENTICATION_ERROR,
    AI_STATUS_PROVIDER_INCAPABLE,
    AI_STATUS_PROVIDER_MALFORMED_RESPONSE,
    AI_STATUS_PROVIDER_RATE_LIMITED,
    AI_STATUS_PROVIDER_TIMEOUT,
    AI_STATUS_PROVIDER_UNAVAILABLE,
    AI_STATUS_SUCCESS,
    AiGatewayRequest,
    PROVIDER_COMPLETION_COMPLETE,
    PROVIDER_COMPLETION_MALFORMED_NO_TEXT,
    PROVIDER_COMPLETION_OUTPUT_EXHAUSTED,
    PROVIDER_COMPLETION_PROVIDER_ERROR,
)
from core.ai.profile_registry import AI_PROFILE_AGENTIC_PLANNING
from core.ai.providers import (
    ANTHROPIC_CAPABILITIES,
    AnthropicProvider,
    OllamaProvider,
    PlaceholderPaidProvider,
    _AnthropicHttpError,
    build_default_providers,
)
from core.ai.readiness import get_ai_gateway_status


FAKE_ANTHROPIC_KEY = "test-anthropic-key-never-send"


def _anthropic_config(**overrides) -> AiGatewayConfig:
    base = AiGatewayConfig(
        mode=AI_MODE_LOCAL_ONLY,
        configured_mode=AI_MODE_LOCAL_ONLY,
        local_provider="ollama",
        local_base_url="http://127.0.0.1:11434",
        local_model="llama3.2:3b",
        anthropic_enabled=True,
        anthropic_api_key=FAKE_ANTHROPIC_KEY,
        anthropic_model="claude-test-model",
        anthropic_timeout_seconds=12.5,
        anthropic_timeout_valid=True,
        anthropic_api_version="2023-06-01",
        anthropic_daily_budget_usd=5.0,
        anthropic_input_cost_per_million_tokens=3.0,
        anthropic_output_cost_per_million_tokens=15.0,
        anthropic_budget_valid=True,
    )
    return replace(base, **overrides)


def _planner_request() -> AiGatewayRequest:
    return AiGatewayRequest(
        prompt="Return a bounded read-only plan.",
        capability="agentic_analyst_planning",
        profile=AI_PROFILE_AGENTIC_PLANNING,
    )


def test_default_registry_uses_real_anthropic_provider_and_keeps_existing_providers():
    providers = build_default_providers()

    assert isinstance(providers["anthropic"], AnthropicProvider)
    assert isinstance(providers["ollama"], OllamaProvider)
    assert isinstance(providers["openai"], PlaceholderPaidProvider)
    assert providers["anthropic"] is not providers["paid"]


def test_anthropic_declares_only_agentic_planning_capability():
    provider = AnthropicProvider()

    assert ANTHROPIC_CAPABILITIES == frozenset({"agentic_analyst_planning"})
    assert provider.supports(_planner_request()).capable is True
    unsupported = provider.supports(
        AiGatewayRequest(prompt="Explain", capability="text_generation")
    )
    assert unsupported.capable is False
    assert unsupported.status == AI_STATUS_PROVIDER_INCAPABLE


def test_unsupported_capability_never_reaches_anthropic_transport(monkeypatch):
    monkeypatch.setattr(
        "core.ai.providers._anthropic_http_json",
        lambda **_kwargs: pytest.fail("unsupported capability reached HTTP transport"),
    )

    response = AnthropicProvider().generate(
        AiGatewayRequest(prompt="Explain", capability="text_generation"),
        _anthropic_config(),
    )

    assert response.status == AI_STATUS_PROVIDER_INCAPABLE
    assert response.metadata.provider == "anthropic"


def test_anthropic_environment_config_loads_without_exposing_key(monkeypatch):
    monkeypatch.setenv("AI_ANTHROPIC_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_ANTHROPIC_KEY)
    monkeypatch.setenv("AI_ANTHROPIC_MODEL", "claude-test-model")
    monkeypatch.setenv("AI_ANTHROPIC_TIMEOUT_SECONDS", "15")
    monkeypatch.setenv("ANTHROPIC_API_VERSION", "2023-06-01")
    monkeypatch.setenv("AI_ANTHROPIC_DAILY_BUDGET_USD", "5")
    monkeypatch.setenv("AI_ANTHROPIC_INPUT_COST_PER_MILLION_TOKENS", "3")
    monkeypatch.setenv("AI_ANTHROPIC_OUTPUT_COST_PER_MILLION_TOKENS", "15")

    config = load_ai_gateway_config()

    assert config.anthropic_enabled is True
    assert config.anthropic_configured is True
    assert config.anthropic_timeout_seconds == 15
    assert config.anthropic_routing_enabled is True
    assert config.sanitized()["anthropic_api_key_configured"] is True
    assert FAKE_ANTHROPIC_KEY not in repr(config)
    assert FAKE_ANTHROPIC_KEY not in str(config.sanitized())


def test_local_only_startup_does_not_require_anthropic_credentials(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_MODE", AI_MODE_LOCAL_ONLY)
    monkeypatch.delenv("AI_ANTHROPIC_ENABLED", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("AI_ANTHROPIC_MODEL", raising=False)

    config = validate_ai_gateway_startup()

    assert config.mode == AI_MODE_LOCAL_ONLY
    assert config.anthropic_enabled is False
    assert config.anthropic_configured is False


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"anthropic_enabled_valid": False}, "AI_ANTHROPIC_ENABLED"),
        ({"anthropic_api_key": ""}, "ANTHROPIC_API_KEY"),
        ({"anthropic_model": ""}, "AI_ANTHROPIC_MODEL"),
        ({"anthropic_model": "invalid model"}, "AI_ANTHROPIC_MODEL"),
        ({"anthropic_timeout_valid": False}, "AI_ANTHROPIC_TIMEOUT_SECONDS"),
        ({"anthropic_budget_valid": False}, "budget and pricing"),
        ({"anthropic_daily_budget_usd": 0}, "AI_ANTHROPIC_DAILY_BUDGET_USD"),
        (
            {"anthropic_input_cost_per_million_tokens": 0},
            "AI_ANTHROPIC_INPUT_COST_PER_MILLION_TOKENS",
        ),
        (
            {"anthropic_output_cost_per_million_tokens": 0},
            "AI_ANTHROPIC_OUTPUT_COST_PER_MILLION_TOKENS",
        ),
        ({"anthropic_api_version": "latest"}, "ANTHROPIC_API_VERSION"),
    ],
)
def test_anthropic_required_startup_fails_closed(overrides, expected):
    with pytest.raises(AiGatewayConfigurationError, match=expected):
        validate_ai_gateway_startup(_anthropic_config(**overrides))


def test_missing_key_readiness_is_sanitized_and_non_generating(monkeypatch):
    monkeypatch.setattr(
        "core.ai.providers._anthropic_http_json",
        lambda **_kwargs: pytest.fail("readiness attempted Anthropic HTTP"),
    )

    readiness = AnthropicProvider().readiness(
        _anthropic_config(anthropic_api_key="")
    ).as_dict()

    assert readiness["provider"] == "anthropic"
    assert readiness["configured"] is False
    assert readiness["ready"] is False
    assert readiness["status"] == AI_STATUS_CONFIGURATION_ERROR
    assert readiness["credential_configured"] == {"ANTHROPIC_API_KEY": False}
    assert "ANTHROPIC_API_KEY" in readiness["missing_env_vars"]
    assert readiness["readiness_scope"] == "configuration_only"
    assert FAKE_ANTHROPIC_KEY not in str(readiness)


def test_disabled_anthropic_readiness_reports_configuration_without_network(monkeypatch):
    monkeypatch.setattr(
        "core.ai.providers._anthropic_http_json",
        lambda **_kwargs: pytest.fail("disabled readiness attempted Anthropic HTTP"),
    )

    readiness = AnthropicProvider().readiness(
        _anthropic_config(anthropic_enabled=False)
    )

    assert readiness.configured is True
    assert readiness.ready is False
    assert readiness.status == AI_STATUS_DISABLED
    assert readiness.error_code == "anthropic_disabled"


def test_mocked_anthropic_generation_normalizes_profile_and_reported_usage(monkeypatch):
    captured = {}

    def fake_transport(*, payload, headers, timeout):
        captured.update(payload=payload, headers=headers, timeout=timeout)
        return {
            "content": [
                {"type": "thinking", "thinking": "bounded reasoning"},
                {"type": "text", "text": '{"strategy":"direct_answer"}'},
            ],
            "usage": {"input_tokens": 17, "output_tokens": 9},
        }

    monkeypatch.setattr("core.ai.providers._anthropic_http_json", fake_transport)

    response = AnthropicProvider().generate(_planner_request(), _anthropic_config())

    assert response.status == AI_STATUS_SUCCESS
    assert response.content == '{"strategy":"direct_answer"}'
    assert response.metadata.provider == "anthropic"
    assert response.metadata.model == "claude-test-model"
    assert response.metadata.profile == AI_PROFILE_AGENTIC_PLANNING
    assert response.metadata.paid_request is True
    assert response.metadata.latency_ms is not None
    assert response.metadata.provider_reported_prompt_tokens == 17
    assert response.metadata.provider_reported_completion_tokens == 9
    assert response.metadata.provider_reported_total_tokens == 26
    assert response.metadata.token_usage_source == "provider_reported"
    assert response.metadata.estimated_cost_usd is None
    assert response.metadata.actual_billed_cost_usd is None
    assert response.metadata.cost_source is None
    assert response.metadata.provider_completion_state == PROVIDER_COMPLETION_COMPLETE
    assert response.metadata.provider_stop_reason is None
    assert captured["payload"] == {
        "model": "claude-test-model",
        "max_tokens": 4096,
        "messages": [
            {"role": "user", "content": "Return a bounded read-only plan."}
        ],
    }
    assert "temperature" not in captured["payload"]
    assert captured["timeout"] == 90.0
    assert captured["headers"]["x-api-key"] == FAKE_ANTHROPIC_KEY
    assert FAKE_ANTHROPIC_KEY not in str(response.as_dict())


def test_anthropic_multiple_text_blocks_are_joined_in_provider_order(monkeypatch):
    monkeypatch.setattr(
        "core.ai.providers._anthropic_http_json",
        lambda **_kwargs: {
            "content": [
                {"type": "text", "text": '{"first":'},
                {"type": "thinking", "thinking": "hidden chain of thought"},
                {"type": "text", "text": "true}"},
            ],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 4, "output_tokens": 5},
        },
    )

    response = AnthropicProvider().generate(_planner_request(), _anthropic_config())

    assert response.status == AI_STATUS_SUCCESS
    assert response.content == '{"first":\ntrue}'
    assert "hidden chain of thought" not in response.content
    assert "hidden chain of thought" not in str(response.metadata.as_dict())
    assert response.metadata.provider_completion_state == PROVIDER_COMPLETION_COMPLETE
    assert response.metadata.provider_stop_reason == "end_turn"


def test_anthropic_no_text_normal_completion_is_malformed_without_reasoning_exposure(monkeypatch):
    monkeypatch.setattr(
        "core.ai.providers._anthropic_http_json",
        lambda **_kwargs: {
            "content": [{"type": "thinking", "thinking": "hidden chain of thought"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 4, "output_tokens": 5},
        },
    )

    response = AnthropicProvider().generate(_planner_request(), _anthropic_config())

    assert response.status == AI_STATUS_PROVIDER_MALFORMED_RESPONSE
    assert response.content is None
    assert response.metadata.provider_completion_state == PROVIDER_COMPLETION_MALFORMED_NO_TEXT
    assert response.metadata.provider_stop_reason == "end_turn"
    assert "hidden chain of thought" not in str(response.as_dict())


@pytest.mark.parametrize(
    ("transport_error", "expected_status"),
    [
        (_AnthropicHttpError(401), AI_STATUS_PROVIDER_AUTHENTICATION_ERROR),
        (_AnthropicHttpError(429), AI_STATUS_PROVIDER_RATE_LIMITED),
        (TimeoutError(), AI_STATUS_PROVIDER_TIMEOUT),
        (OSError("network unavailable"), AI_STATUS_PROVIDER_UNAVAILABLE),
    ],
)
def test_anthropic_failures_are_normalized_and_redacted(
    monkeypatch,
    caplog,
    transport_error,
    expected_status,
):
    def fail_transport(**_kwargs):
        raise transport_error

    monkeypatch.setattr("core.ai.providers._anthropic_http_json", fail_transport)

    response = AnthropicProvider().generate(_planner_request(), _anthropic_config())

    assert response.status == expected_status
    assert response.metadata.error_code == expected_status
    assert FAKE_ANTHROPIC_KEY not in str(response.as_dict())
    assert FAKE_ANTHROPIC_KEY not in caplog.text


def test_unexpected_anthropic_error_logs_only_exception_type(monkeypatch, caplog):
    def fail_transport(**_kwargs):
        raise RuntimeError(f"{FAKE_ANTHROPIC_KEY} https://sensitive.invalid/path")

    monkeypatch.setattr("core.ai.providers._anthropic_http_json", fail_transport)

    response = AnthropicProvider().generate(_planner_request(), _anthropic_config())

    assert response.metadata.error_code == "failed"
    assert "RuntimeError" in caplog.text
    assert FAKE_ANTHROPIC_KEY not in caplog.text
    assert "sensitive.invalid" not in caplog.text
    assert FAKE_ANTHROPIC_KEY not in str(response.as_dict())


def test_thinking_only_max_tokens_response_is_normalized_as_output_exhaustion(monkeypatch):
    monkeypatch.setattr(
        "core.ai.providers._anthropic_http_json",
        lambda **_kwargs: {
            "content": [{"type": "thinking", "thinking": "truncated reasoning"}],
            "stop_reason": "max_tokens",
            "usage": {"input_tokens": 17, "output_tokens": 4096},
        },
    )

    response = AnthropicProvider().generate(_planner_request(), _anthropic_config())

    assert response.status == AI_STATUS_SUCCESS
    assert response.metadata.error_code is None
    assert response.content is None
    assert response.metadata.provider_completion_state == PROVIDER_COMPLETION_OUTPUT_EXHAUSTED
    assert response.metadata.provider_stop_reason == "max_tokens"
    assert response.metadata.provider_reported_completion_tokens == 4096
    assert "truncated reasoning" not in str(response.as_dict())


def test_anthropic_partial_text_max_tokens_preserves_text_but_marks_exhaustion(monkeypatch):
    monkeypatch.setattr(
        "core.ai.providers._anthropic_http_json",
        lambda **_kwargs: {
            "content": [{"type": "text", "text": '{"current_turn_intent":'}],
            "stop_reason": "max_tokens",
            "usage": {"input_tokens": 17, "output_tokens": 4096},
        },
    )

    response = AnthropicProvider().generate(_planner_request(), _anthropic_config())

    assert response.status == AI_STATUS_SUCCESS
    assert response.content == '{"current_turn_intent":'
    assert response.metadata.provider_completion_state == PROVIDER_COMPLETION_OUTPUT_EXHAUSTED
    assert response.metadata.provider_stop_reason == "max_tokens"


def test_anthropic_transport_error_marks_provider_completion_error(monkeypatch):
    def fail_transport(**_kwargs):
        raise TimeoutError()

    monkeypatch.setattr("core.ai.providers._anthropic_http_json", fail_transport)

    response = AnthropicProvider().generate(_planner_request(), _anthropic_config())

    assert response.status == AI_STATUS_PROVIDER_TIMEOUT
    assert response.metadata.provider_completion_state == PROVIDER_COMPLETION_PROVIDER_ERROR
    assert response.metadata.provider_stop_reason is None


def test_gateway_blocks_anthropic_routing_until_paid_accounting_exists(monkeypatch):
    monkeypatch.setattr(
        "core.ai.providers._anthropic_http_json",
        lambda **_kwargs: pytest.fail("Phase 1 gateway reached Anthropic HTTP"),
    )
    config = _anthropic_config(
        mode=AI_MODE_AUTOMATIC_FALLBACK,
        configured_mode=AI_MODE_AUTOMATIC_FALLBACK,
        local_provider="missing-local-provider",
        paid_provider="anthropic",
        paid_model="legacy-paid-model",
        paid_fallback_enabled=True,
    )

    response = AiGateway(config=config).generate(
        AiGatewayRequest(
            prompt="Attempt paid fallback.",
            capability="agentic_analyst_planning",
            profile=AI_PROFILE_AGENTIC_PLANNING,
        )
    )

    assert response.status == AI_STATUS_FALLBACK_BLOCKED
    assert response.metadata.error_code == "anthropic_routing_not_enabled"
    assert response.metadata.paid_request is False


def test_status_always_includes_sanitized_unassigned_anthropic_readiness(monkeypatch):
    monkeypatch.setattr("core.ai.providers._http_json", lambda *_args, **_kwargs: {"models": []})
    config = _anthropic_config(anthropic_enabled=False)

    status = get_ai_gateway_status(config=config)
    anthropic = next(row for row in status["providers"] if row["provider"] == "anthropic")

    assert anthropic["status"] == AI_STATUS_DISABLED
    assert anthropic["ready"] is False
    assert anthropic["credential_configured"] == {"ANTHROPIC_API_KEY": True}
    assert status["gateway"]["anthropic_routing_enabled"] is False
    assert FAKE_ANTHROPIC_KEY not in str(status)
