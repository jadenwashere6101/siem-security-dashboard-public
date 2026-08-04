from __future__ import annotations

from dataclasses import replace

import pytest

from core.ai.config import (
    AI_MODE_ASK_BEFORE_PAID_FALLBACK,
    AI_MODE_AUTOMATIC_FALLBACK,
    AI_MODE_DISABLED,
    AI_MODE_LOCAL_ONLY,
    AiGatewayConfig,
    default_ai_profiles,
)
from core.ai.gateway import AiGateway
from core.ai.models import (
    AI_STATUS_CONFIGURATION_ERROR,
    AI_STATUS_DISABLED,
    AI_STATUS_FALLBACK_BLOCKED,
    AI_STATUS_FALLBACK_REQUIRES_CONFIRMATION,
    AI_STATUS_SUCCESS,
    AiCapabilityResult,
    AiGatewayRequest,
    AiGatewayResponse,
    AiProviderReadiness,
    AiRequestMetadata,
)
from core.ai.profile_registry import (
    AI_PROFILE_AGENTIC_PLANNING,
    AI_PROFILE_DEEP_BRIEFING,
    AI_PROFILE_DEVELOPER_ASSISTANT,
    AI_PROFILE_FAST_TRIAGE,
    AI_PROFILE_GUIDED_ANALYSIS,
    AI_PROVIDER_ANTHROPIC,
    AI_PROVIDER_OLLAMA,
    PROFILE_PROVIDER_ROUTING,
)


OLLAMA_PROFILES = (
    AI_PROFILE_FAST_TRIAGE,
    AI_PROFILE_GUIDED_ANALYSIS,
    AI_PROFILE_DEEP_BRIEFING,
    AI_PROFILE_DEVELOPER_ASSISTANT,
)


class RecordingProvider:
    def __init__(self, provider_key: str, *, paid_request: bool):
        self.provider_key = provider_key
        self.paid_request = paid_request
        self.requests: list[AiGatewayRequest] = []

    def supports(self, request: AiGatewayRequest) -> AiCapabilityResult:
        return AiCapabilityResult(True, AI_STATUS_SUCCESS)

    def readiness(self, config: AiGatewayConfig) -> AiProviderReadiness:
        return AiProviderReadiness(self.provider_key, True, True, AI_STATUS_SUCCESS)

    def generate(self, request: AiGatewayRequest, config: AiGatewayConfig) -> AiGatewayResponse:
        self.requests.append(request)
        profile = config.profile(request.profile)
        return AiGatewayResponse(
            status=AI_STATUS_SUCCESS,
            content="ok",
            error=None,
            metadata=AiRequestMetadata(
                provider=self.provider_key,
                model=profile.model,
                mode=config.mode,
                status=AI_STATUS_SUCCESS,
                local_request=not self.paid_request,
                paid_request=self.paid_request,
                estimated_cost_usd=None if self.paid_request else 0,
                profile=profile.name,
                task_category=profile.task_category,
                timeout_seconds=profile.timeout_seconds,
                max_output_tokens=profile.max_output_tokens,
            ),
        )


def _config(mode: str, *, routing_enabled: bool = False) -> AiGatewayConfig:
    anthropic_model = "claude-test-model"
    return AiGatewayConfig(
        mode=mode,
        configured_mode=mode,
        local_provider=AI_PROVIDER_OLLAMA,
        local_base_url="http://127.0.0.1:11434",
        local_model="llama3.2:3b",
        anthropic_enabled=True,
        anthropic_routing_enabled=routing_enabled,
        anthropic_api_key="test-key-never-send",
        anthropic_model=anthropic_model,
        profiles=default_ai_profiles(
            local_model="llama3.2:3b",
            anthropic_model=anthropic_model,
        ),
    )


def _providers():
    return {
        AI_PROVIDER_OLLAMA: RecordingProvider(AI_PROVIDER_OLLAMA, paid_request=False),
        AI_PROVIDER_ANTHROPIC: RecordingProvider(AI_PROVIDER_ANTHROPIC, paid_request=True),
    }


def test_profile_provider_routing_inventory_is_exhaustive():
    assert set(PROFILE_PROVIDER_ROUTING) == {
        AI_PROFILE_FAST_TRIAGE,
        AI_PROFILE_AGENTIC_PLANNING,
        AI_PROFILE_GUIDED_ANALYSIS,
        AI_PROFILE_DEEP_BRIEFING,
        AI_PROFILE_DEVELOPER_ASSISTANT,
    }
    assert PROFILE_PROVIDER_ROUTING[AI_PROFILE_AGENTIC_PLANNING] == AI_PROVIDER_ANTHROPIC
    assert all(PROFILE_PROVIDER_ROUTING[name] == AI_PROVIDER_OLLAMA for name in OLLAMA_PROFILES)


@pytest.mark.parametrize(
    "mode",
    (AI_MODE_LOCAL_ONLY, AI_MODE_ASK_BEFORE_PAID_FALLBACK, AI_MODE_AUTOMATIC_FALLBACK),
)
@pytest.mark.parametrize("profile_name", OLLAMA_PROFILES)
def test_ollama_profiles_never_call_anthropic_in_any_enabled_mode(mode, profile_name):
    providers = _providers()
    response = AiGateway(config=_config(mode), providers=providers).generate(
        AiGatewayRequest(prompt="bounded request", profile=profile_name)
    )

    assert response.status == AI_STATUS_SUCCESS
    assert response.metadata.provider == AI_PROVIDER_OLLAMA
    assert len(providers[AI_PROVIDER_OLLAMA].requests) == 1
    assert providers[AI_PROVIDER_ANTHROPIC].requests == []


@pytest.mark.parametrize(
    ("mode", "expected_status"),
    (
        (AI_MODE_DISABLED, AI_STATUS_DISABLED),
        (AI_MODE_LOCAL_ONLY, AI_STATUS_FALLBACK_BLOCKED),
        (AI_MODE_ASK_BEFORE_PAID_FALLBACK, AI_STATUS_FALLBACK_REQUIRES_CONFIRMATION),
        (AI_MODE_AUTOMATIC_FALLBACK, AI_STATUS_FALLBACK_BLOCKED),
    ),
)
def test_agentic_profile_never_substitutes_ollama_when_paid_execution_is_blocked(mode, expected_status):
    providers = _providers()
    response = AiGateway(config=_config(mode), providers=providers).generate(
        AiGatewayRequest(
            prompt="plan this turn",
            capability="agentic_analyst_planning",
            profile=AI_PROFILE_AGENTIC_PLANNING,
        )
    )

    assert response.status == expected_status
    assert response.metadata.provider == AI_PROVIDER_ANTHROPIC
    assert providers[AI_PROVIDER_OLLAMA].requests == []
    assert providers[AI_PROVIDER_ANTHROPIC].requests == []


def test_agentic_profile_resolves_directly_to_anthropic_when_test_guard_is_enabled():
    providers = _providers()
    response = AiGateway(
        config=_config(AI_MODE_AUTOMATIC_FALLBACK, routing_enabled=True),
        providers=providers,
    ).generate(
        AiGatewayRequest(
            prompt="plan this turn",
            capability="agentic_analyst_planning",
            profile=AI_PROFILE_AGENTIC_PLANNING,
            metadata={"provider": "ollama", "model": "qwen3:14b", "fallback": True},
        )
    )

    assert response.status == AI_STATUS_SUCCESS
    assert response.metadata.provider == AI_PROVIDER_ANTHROPIC
    assert response.metadata.model == "claude-test-model"
    assert response.metadata.fallback_attempted is False
    assert providers[AI_PROVIDER_OLLAMA].requests == []
    assert len(providers[AI_PROVIDER_ANTHROPIC].requests) == 1


def test_untrusted_profile_provider_override_fails_closed_before_provider_contact():
    config = _config(AI_MODE_AUTOMATIC_FALLBACK, routing_enabled=True)
    profiles = dict(config.profiles or {})
    profiles[AI_PROFILE_AGENTIC_PLANNING] = replace(
        profiles[AI_PROFILE_AGENTIC_PLANNING],
        provider=AI_PROVIDER_OLLAMA,
        local_only=True,
        paid_fallback_enabled=False,
    )
    providers = _providers()

    response = AiGateway(config=replace(config, profiles=profiles), providers=providers).generate(
        AiGatewayRequest(prompt="plan", profile=AI_PROFILE_AGENTIC_PLANNING)
    )

    assert response.status == AI_STATUS_CONFIGURATION_ERROR
    assert response.metadata.error_code == "invalid_profile_provider_routing"
    assert providers[AI_PROVIDER_OLLAMA].requests == []
    assert providers[AI_PROVIDER_ANTHROPIC].requests == []
