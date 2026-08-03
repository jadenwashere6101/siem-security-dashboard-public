from dataclasses import replace
from unittest.mock import MagicMock

from core.ai.config import (
    AI_MODE_LOCAL_ONLY,
    DEFAULT_AGENTIC_PLANNING_MAX_OUTPUT_TOKENS,
    DEFAULT_AGENTIC_PLANNING_MAX_PROMPT_CHARS,
    DEFAULT_AGENTIC_PLANNING_MODEL,
    DEFAULT_AGENTIC_PLANNING_TIMEOUT_SECONDS,
    DEFAULT_DEEP_TIMEOUT_SECONDS,
    DEFAULT_DEVELOPER_TIMEOUT_SECONDS,
    DEFAULT_FAST_TIMEOUT_SECONDS,
    DEFAULT_GUIDED_TIMEOUT_SECONDS,
    AiGatewayConfig,
    default_ai_profiles,
    load_ai_gateway_config,
)
from core.ai.context_builder import build_ai_context
from core.ai.draft_schemas import DRAFT_DEFINITIONS
from core.ai.explainer_service import ALLOWED_EXPLAIN_ACTIONS, explain_context
from core.ai.gateway import AiGateway
from core.ai.investigation_models import (
    WORKFLOW_ALERT,
    WORKFLOW_DASHBOARD_ANOMALY,
    WORKFLOW_INCIDENT,
    WORKFLOW_RECON_CLUSTER,
    WORKFLOW_RESPONSE_REGISTRY,
    WORKFLOW_SOURCE_IP,
)
from core.ai.models import AI_STATUS_SUCCESS, AiCapabilityResult, AiGatewayRequest, AiGatewayResponse, AiRequestMetadata
from core.ai.profile_registry import (
    AI_PROFILE_AGENTIC_PLANNING,
    AI_PROFILE_DEEP_BRIEFING,
    AI_PROFILE_DEVELOPER_ASSISTANT,
    AI_PROFILE_FAST_TRIAGE,
    AI_PROFILE_GUIDED_ANALYSIS,
    APPROVED_AI_PROFILES,
    FAST_EXPLAIN_ACTIONS,
    GUIDED_DRAFT_TYPES,
    GUIDED_INVESTIGATION_WORKFLOWS,
    inventory_selectors,
    profile_for_draft_type,
    profile_for_agentic_planning,
    profile_for_explain_action,
    profile_for_investigation,
    profile_for_repo_assistant,
    profile_for_soc_briefing,
)
from core.ai.providers import OllamaProvider


def _config(**overrides):
    profiles = default_ai_profiles(
        local_model="llama3.1:8b",
        local_timeout_seconds=30,
    )
    profiles[AI_PROFILE_FAST_TRIAGE] = replace(
        profiles[AI_PROFILE_FAST_TRIAGE],
        model="llama3.2:3b",
        timeout_seconds=45,
        max_prompt_chars=8000,
        max_output_tokens=512,
        temperature=0.2,
    )
    base = AiGatewayConfig(
        mode=AI_MODE_LOCAL_ONLY,
        configured_mode=AI_MODE_LOCAL_ONLY,
        local_provider="ollama",
        local_base_url="http://127.0.0.1:11434",
        local_model="llama3.1:8b",
        local_timeout_seconds=30,
        profiles=profiles,
    )
    return replace(base, **overrides)


class RecordingProvider:
    provider_key = "ollama"

    def __init__(self):
        self.requests = []

    def supports(self, request):
        return AiCapabilityResult(True, AI_STATUS_SUCCESS)

    def generate(self, request, config):
        self.requests.append(request)
        profile = config.profile(request.profile)
        return AiGatewayResponse(
            status=AI_STATUS_SUCCESS,
            content="ok",
            error=None,
            metadata=AiRequestMetadata(
                provider="ollama",
                model=profile.model,
                mode=config.mode,
                status=AI_STATUS_SUCCESS,
                local_request=True,
                estimated_cost_usd=0,
                profile=profile.name,
                task_category=profile.task_category,
                timeout_seconds=profile.timeout_seconds,
                max_output_tokens=profile.max_output_tokens,
            ),
        )


def test_profile_inventory_covers_backend_ai_selectors():
    explain_selectors = inventory_selectors("explain_action")
    assert set(ALLOWED_EXPLAIN_ACTIONS).issubset(explain_selectors | FAST_EXPLAIN_ACTIONS)
    assert "explain_recon_activity" in ALLOWED_EXPLAIN_ACTIONS
    assert profile_for_explain_action("explain_recon_activity") == AI_PROFILE_GUIDED_ANALYSIS
    assert set(DRAFT_DEFINITIONS) == GUIDED_DRAFT_TYPES
    for draft_type in DRAFT_DEFINITIONS:
        assert profile_for_draft_type(draft_type) == AI_PROFILE_GUIDED_ANALYSIS
    assert {
        WORKFLOW_ALERT,
        WORKFLOW_INCIDENT,
        WORKFLOW_SOURCE_IP,
        WORKFLOW_RECON_CLUSTER,
        WORKFLOW_RESPONSE_REGISTRY,
        WORKFLOW_DASHBOARD_ANOMALY,
    } == GUIDED_INVESTIGATION_WORKFLOWS
    assert profile_for_investigation() == AI_PROFILE_GUIDED_ANALYSIS
    assert profile_for_agentic_planning() == AI_PROFILE_AGENTIC_PLANNING
    assert profile_for_soc_briefing() == AI_PROFILE_DEEP_BRIEFING
    assert profile_for_repo_assistant() == AI_PROFILE_DEVELOPER_ASSISTANT


def test_correlation_heavy_explain_actions_use_guided_profile():
    for action in (
        "recommend_investigation",
        "summarize_incident",
        "recommend_next_steps",
        "explain_ip",
        "assess_reconnaissance",
        "summarize_activity",
        "explain_campaign",
        "explain_recon_activity",
        "investigate_cluster",
        "explain_response",
    ):
        assert profile_for_explain_action(action) == AI_PROFILE_GUIDED_ANALYSIS

    for action in ("ask_dashboard", "explain_anomaly", "explain_alert", "why_important", "general_chat"):
        assert profile_for_explain_action(action) == AI_PROFILE_FAST_TRIAGE


def test_agentic_planning_has_dedicated_local_8b_profile_without_changing_fast_triage():
    config = _config()

    planner = config.profile(AI_PROFILE_AGENTIC_PLANNING)
    quick = config.profile(AI_PROFILE_FAST_TRIAGE)

    assert APPROVED_AI_PROFILES.issuperset({AI_PROFILE_AGENTIC_PLANNING, AI_PROFILE_FAST_TRIAGE})
    assert planner.model == DEFAULT_AGENTIC_PLANNING_MODEL == "llama3.1:8b"
    assert planner.timeout_seconds == DEFAULT_AGENTIC_PLANNING_TIMEOUT_SECONDS == 90.0
    assert planner.max_prompt_chars == DEFAULT_AGENTIC_PLANNING_MAX_PROMPT_CHARS == 8000
    assert planner.max_output_tokens == DEFAULT_AGENTIC_PLANNING_MAX_OUTPUT_TOKENS == 1024
    assert planner.local_only is True
    assert planner.paid_fallback_enabled is False
    assert quick.model == "llama3.2:3b"
    assert quick.max_output_tokens == 512
    assert config.profile(AI_PROFILE_GUIDED_ANALYSIS).model == "llama3.1:8b"
    assert config.profile(AI_PROFILE_DEEP_BRIEFING).model == "llama3.1:8b"
    assert config.profile(AI_PROFILE_DEVELOPER_ASSISTANT).model == "llama3.1:8b"


def test_legacy_local_timeout_does_not_override_profile_defaults(monkeypatch):
    for name in (
        "AI_FAST_TIMEOUT_SECONDS",
        "AI_GUIDED_TIMEOUT_SECONDS",
        "AI_DEEP_TIMEOUT_SECONDS",
        "AI_DEVELOPER_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AI_LOCAL_TIMEOUT_SECONDS", "30")

    config = load_ai_gateway_config()

    assert DEFAULT_FAST_TIMEOUT_SECONDS == 45.0
    assert DEFAULT_GUIDED_TIMEOUT_SECONDS == 120.0
    assert DEFAULT_DEEP_TIMEOUT_SECONDS == 150.0
    assert DEFAULT_DEVELOPER_TIMEOUT_SECONDS == 120.0
    assert config.local_timeout_seconds == 30
    assert config.profile(AI_PROFILE_FAST_TRIAGE).timeout_seconds == DEFAULT_FAST_TIMEOUT_SECONDS
    assert config.profile(AI_PROFILE_GUIDED_ANALYSIS).timeout_seconds == DEFAULT_GUIDED_TIMEOUT_SECONDS
    assert config.profile(AI_PROFILE_DEEP_BRIEFING).timeout_seconds == DEFAULT_DEEP_TIMEOUT_SECONDS
    assert config.profile(AI_PROFILE_DEVELOPER_ASSISTANT).timeout_seconds == DEFAULT_DEVELOPER_TIMEOUT_SECONDS


def test_profile_specific_timeout_overrides_win(monkeypatch):
    monkeypatch.setenv("AI_LOCAL_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("AI_FAST_TIMEOUT_SECONDS", "31")
    monkeypatch.setenv("AI_GUIDED_TIMEOUT_SECONDS", "91")
    monkeypatch.setenv("AI_DEEP_TIMEOUT_SECONDS", "151")
    monkeypatch.setenv("AI_DEVELOPER_TIMEOUT_SECONDS", "121")

    config = load_ai_gateway_config()

    assert config.profile(AI_PROFILE_FAST_TRIAGE).timeout_seconds == 31
    assert config.profile(AI_PROFILE_GUIDED_ANALYSIS).timeout_seconds == 91
    assert config.profile(AI_PROFILE_DEEP_BRIEFING).timeout_seconds == 151
    assert config.profile(AI_PROFILE_DEVELOPER_ASSISTANT).timeout_seconds == 121


def test_invalid_profile_timeout_values_fall_back_safely(monkeypatch):
    monkeypatch.setenv("AI_LOCAL_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("AI_FAST_TIMEOUT_SECONDS", "not-a-number")
    monkeypatch.setenv("AI_GUIDED_TIMEOUT_SECONDS", "0")
    monkeypatch.setenv("AI_DEEP_TIMEOUT_SECONDS", "-1")
    monkeypatch.setenv("AI_DEVELOPER_TIMEOUT_SECONDS", "")

    config = load_ai_gateway_config()

    assert config.profile(AI_PROFILE_FAST_TRIAGE).timeout_seconds == DEFAULT_FAST_TIMEOUT_SECONDS
    assert config.profile(AI_PROFILE_GUIDED_ANALYSIS).timeout_seconds == DEFAULT_GUIDED_TIMEOUT_SECONDS
    assert config.profile(AI_PROFILE_DEEP_BRIEFING).timeout_seconds == DEFAULT_DEEP_TIMEOUT_SECONDS
    assert config.profile(AI_PROFILE_DEVELOPER_ASSISTANT).timeout_seconds == DEFAULT_DEVELOPER_TIMEOUT_SECONDS


def test_ollama_provider_uses_profile_model_timeout_and_generation_options(monkeypatch):
    captured = {}

    def fake_http_json(method, url, *, payload=None, timeout):
        captured["method"] = method
        captured["url"] = url
        captured["payload"] = payload
        captured["timeout"] = timeout
        return {"response": "OK"}

    monkeypatch.setattr("core.ai.providers._http_json", fake_http_json)

    response = OllamaProvider().generate(
        AiGatewayRequest(prompt="Explain this graph", profile=AI_PROFILE_FAST_TRIAGE),
        _config(),
    )

    assert response.status == AI_STATUS_SUCCESS
    assert response.metadata.profile == AI_PROFILE_FAST_TRIAGE
    assert response.metadata.model == "llama3.2:3b"
    assert response.metadata.timeout_seconds == 45
    assert captured["payload"]["model"] == "llama3.2:3b"
    assert captured["payload"]["options"] == {"num_predict": 512, "temperature": 0.2}
    assert captured["timeout"] == 45


def test_gateway_ignores_client_model_timeout_metadata_and_uses_trusted_profile():
    provider = RecordingProvider()
    gateway = AiGateway(config=_config(), providers={"ollama": provider})

    response = gateway.generate(
        AiGatewayRequest(
            prompt="Explain this",
            profile=AI_PROFILE_FAST_TRIAGE,
            metadata={"model": "bad-model", "timeout_seconds": 999},
        )
    )

    assert response.status == AI_STATUS_SUCCESS
    assert response.metadata.model == "llama3.2:3b"
    assert response.metadata.profile == AI_PROFILE_FAST_TRIAGE
    assert provider.requests[0].metadata["model"] == "bad-model"


def test_explain_route_ignores_client_profile_model_and_timeout_fields(monkeypatch):
    provider = RecordingProvider()
    monkeypatch.setattr("core.ai.explainer_service.load_ai_gateway_config", lambda: _config())
    monkeypatch.setattr("core.ai.explainer_service.build_ai_context", lambda **_kwargs: _fake_context())

    result = explain_context(
        {
            "context_type": "recon_activity",
            "action": "explain_recon_activity",
            "question": "Explain this recon activity.",
            "context": {"activity_id": 90},
            "profile": AI_PROFILE_FAST_TRIAGE,
            "model": "client-selected-model",
            "timeout_seconds": 1,
        },
        gateway=AiGateway(config=_config(), providers={"ollama": provider}),
    )

    assert result.status_code == 200
    assert result.payload["metadata"]["profile"] == AI_PROFILE_GUIDED_ANALYSIS
    assert result.payload["metadata"]["model"] == "llama3.1:8b"
    assert provider.requests[0].profile == AI_PROFILE_GUIDED_ANALYSIS


def test_soc_command_center_recon_explain_action_uses_guided_profile(monkeypatch):
    provider = RecordingProvider()
    monkeypatch.setattr("core.ai.explainer_service.load_ai_gateway_config", lambda: _config())
    monkeypatch.setattr("core.ai.explainer_service.build_ai_context", lambda **_kwargs: _fake_context())

    result = explain_context(
        {
            "context_type": "recon_activity",
            "action": "explain_recon_activity",
            "question": "Explain this recon activity.",
            "context": {"activity_id": 90},
        },
        gateway=AiGateway(config=_config(), providers={"ollama": provider}),
    )

    assert result.status_code == 200
    assert result.payload["metadata"]["profile"] == AI_PROFILE_GUIDED_ANALYSIS
    assert provider.requests[0].profile == AI_PROFILE_GUIDED_ANALYSIS


def test_workspace_section_ids_normalize_to_safe_general_context():
    context = build_ai_context(
        context_type="soc-command-center",
        context={"visible_filters": {"status": "open"}, "dashboard_summary": {"total_alerts": 3}},
        config=_config(),
        question="Summarize current workspace.",
    )

    assert context.context_type == "general"
    assert context.data["visible_context"]["visible_filters"] == {"status": "open"}


def test_analyst_workspace_investigation_context_maps_to_supported_general_workflow():
    from core.ai.investigation_planner import build_investigation_plan
    from core.ai.investigation_models import WORKFLOW_DASHBOARD_ANOMALY

    plan = build_investigation_plan(
        context_type="analyst_workspace",
        context={"command": {"id": "anakin.investigate"}, "workspace": {"activeSection": "analyst_workspace"}},
        question="Run a bounded read-only investigation of this analyst workspace.",
    )

    assert plan.context_type == "general"
    assert plan.workflow_type == WORKFLOW_DASHBOARD_ANOMALY


def _fake_context():
    from core.ai.context_builder import AiContextPayload, AiContextSource

    return AiContextPayload(
        context_type="recon_activity",
        data={"recon_activity": {"id": 90, "label": "Repeated VPN recon"}},
        sources=[AiContextSource("recon_activity", "/recon-activities/90", [90])],
    )
