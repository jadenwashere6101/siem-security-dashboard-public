from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

AI_PROFILE_FAST_TRIAGE = "fast_triage"
AI_PROFILE_AGENTIC_PLANNING = "agentic_planning"
AI_PROFILE_GUIDED_ANALYSIS = "guided_analysis"
AI_PROFILE_DEEP_BRIEFING = "deep_briefing"
AI_PROFILE_DEVELOPER_ASSISTANT = "developer_assistant"

AI_PROVIDER_OLLAMA = "ollama"
AI_PROVIDER_ANTHROPIC = "anthropic"

APPROVED_AI_PROFILES = frozenset(
    {
        AI_PROFILE_FAST_TRIAGE,
        AI_PROFILE_AGENTIC_PLANNING,
        AI_PROFILE_GUIDED_ANALYSIS,
        AI_PROFILE_DEEP_BRIEFING,
        AI_PROFILE_DEVELOPER_ASSISTANT,
    }
)

PROFILE_PROVIDER_ROUTING = {
    AI_PROFILE_FAST_TRIAGE: AI_PROVIDER_OLLAMA,
    AI_PROFILE_AGENTIC_PLANNING: AI_PROVIDER_ANTHROPIC,
    AI_PROFILE_GUIDED_ANALYSIS: AI_PROVIDER_OLLAMA,
    AI_PROFILE_DEEP_BRIEFING: AI_PROVIDER_OLLAMA,
    AI_PROFILE_DEVELOPER_ASSISTANT: AI_PROVIDER_OLLAMA,
}


def validate_profile_provider_routing(profiles: dict[str, "AiModelProfile"]) -> None:
    if set(profiles) != set(APPROVED_AI_PROFILES):
        raise ValueError("AI profile routing must define every approved profile exactly once.")
    for profile_name, expected_provider in PROFILE_PROVIDER_ROUTING.items():
        profile = profiles[profile_name]
        if profile.name != profile_name or profile.provider != expected_provider:
            raise ValueError(f"AI profile routing is invalid for {profile_name}.")
        if expected_provider == AI_PROVIDER_OLLAMA and (
            not profile.local_only or profile.paid_fallback_enabled
        ):
            raise ValueError(f"Ollama profile {profile_name} must remain local-only.")
        if expected_provider == AI_PROVIDER_ANTHROPIC and (
            profile.local_only or not profile.paid_fallback_enabled
        ):
            raise ValueError(f"Anthropic profile {profile_name} must be paid-eligible and prohibit local routing.")
        if profile.local_fallback_profile is not None:
            fallback_provider = PROFILE_PROVIDER_ROUTING.get(profile.local_fallback_profile)
            if fallback_provider != AI_PROVIDER_OLLAMA:
                raise ValueError(f"AI profile {profile_name} has an invalid local fallback profile.")


@dataclass(frozen=True)
class AiModelProfile:
    name: str
    provider: str
    model: str
    timeout_seconds: float
    max_prompt_chars: int
    max_output_tokens: int
    temperature: float
    task_category: str
    local_only: bool = True
    paid_fallback_enabled: bool = False
    local_fallback_profile: str | None = None

    def sanitized(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AiInvocationInventoryEntry:
    key: str
    frontend_surface: str
    backend_path: str
    selector_type: str
    selector: str
    profile: str
    notes: str = ""

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


FAST_EXPLAIN_ACTIONS = frozenset(
    {
        "ask_anakin",
        "general_chat",
        "summarize",
        "explain",
        "explain_alert",
        "why_important",
        "ask_dashboard",
        "explain_anomaly",
        "explain_detection",
    }
)

GUIDED_DRAFT_TYPES = frozenset(
    {
        "detection_rule_change",
        "playbook_draft",
        "incident_note",
        "escalation_summary",
        "response_recommendation",
        "investigation_checklist",
    }
)

GUIDED_INVESTIGATION_WORKFLOWS = frozenset(
    {
        "alert_investigation",
        "incident_investigation",
        "source_ip_investigation",
        "recon_cluster_investigation",
        "response_registry_review",
        "dashboard_anomaly_review",
    }
)


AI_INVOCATION_INVENTORY: tuple[AiInvocationInventoryEntry, ...] = (
    AiInvocationInventoryEntry(
        "frontend.dashboard.metrics.ask_dashboard",
        "DashboardMetrics Anakin buttons",
        "POST /ai/explain",
        "explain_action",
        "ask_dashboard",
        AI_PROFILE_FAST_TRIAGE,
        "Dashboard metric explanation and anomaly overview.",
    ),
    AiInvocationInventoryEntry(
        "frontend.dashboard.visuals.explain_anomaly",
        "DashboardVisuals Explain graph/anomaly",
        "POST /ai/explain",
        "explain_action",
        "explain_anomaly",
        AI_PROFILE_FAST_TRIAGE,
        "Quick graph and anomaly explanations.",
    ),
    AiInvocationInventoryEntry(
        "frontend.alert.explain",
        "AlertDetailsPanel explain/why/recommend buttons",
        "POST /ai/explain",
        "explain_action",
        "explain_alert",
        AI_PROFILE_FAST_TRIAGE,
        "Short alert explanation.",
    ),
    AiInvocationInventoryEntry(
        "frontend.alert.why_important",
        "AlertDetailsPanel why important",
        "POST /ai/explain",
        "explain_action",
        "why_important",
        AI_PROFILE_FAST_TRIAGE,
    ),
    AiInvocationInventoryEntry(
        "frontend.alert.recommend_investigation",
        "AlertDetailsPanel recommend investigation",
        "POST /ai/explain",
        "explain_action",
        "recommend_investigation",
        AI_PROFILE_GUIDED_ANALYSIS,
        "Correlation-heavy next-step reasoning.",
    ),
    AiInvocationInventoryEntry(
        "frontend.detection.explain",
        "AlertDetailsPanel explain detection",
        "POST /ai/explain",
        "explain_action",
        "explain_detection",
        AI_PROFILE_FAST_TRIAGE,
    ),
    AiInvocationInventoryEntry(
        "frontend.source_ip.explain",
        "SourceIpContext quick AI actions",
        "POST /ai/explain",
        "explain_action",
        "explain_ip",
        AI_PROFILE_GUIDED_ANALYSIS,
    ),
    AiInvocationInventoryEntry(
        "frontend.source_ip.assess_recon",
        "SourceIpContext reconnaissance assessment",
        "POST /ai/explain",
        "explain_action",
        "assess_reconnaissance",
        AI_PROFILE_GUIDED_ANALYSIS,
    ),
    AiInvocationInventoryEntry(
        "frontend.source_ip.summarize_activity",
        "SourceIpContext activity summary",
        "POST /ai/explain",
        "explain_action",
        "summarize_activity",
        AI_PROFILE_GUIDED_ANALYSIS,
    ),
    AiInvocationInventoryEntry(
        "frontend.incident.summarize",
        "IncidentsPanel quick AI actions",
        "POST /ai/explain",
        "explain_action",
        "summarize_incident",
        AI_PROFILE_GUIDED_ANALYSIS,
    ),
    AiInvocationInventoryEntry(
        "frontend.incident.next_steps",
        "IncidentsPanel next steps",
        "POST /ai/explain",
        "explain_action",
        "recommend_next_steps",
        AI_PROFILE_GUIDED_ANALYSIS,
    ),
    AiInvocationInventoryEntry(
        "frontend.recon.explain_activity",
        "SocCommandCenter Explain recon",
        "POST /ai/explain",
        "explain_action",
        "explain_recon_activity",
        AI_PROFILE_GUIDED_ANALYSIS,
        "Recon interpretation needs multi-field correlation.",
    ),
    AiInvocationInventoryEntry(
        "frontend.recon.explain",
        "SocCommandCenter recon explain",
        "POST /ai/explain",
        "explain_action",
        "explain_campaign",
        AI_PROFILE_GUIDED_ANALYSIS,
    ),
    AiInvocationInventoryEntry(
        "frontend.recon.cluster",
        "SocCommandCenter cluster quick review",
        "POST /ai/explain",
        "explain_action",
        "investigate_cluster",
        AI_PROFILE_GUIDED_ANALYSIS,
        "Non-guided cluster explanation; guided path uses /ai/investigations.",
    ),
    AiInvocationInventoryEntry(
        "frontend.response_registry.explain",
        "ResponseRegistryPanel explain response",
        "POST /ai/explain",
        "explain_action",
        "explain_response",
        AI_PROFILE_GUIDED_ANALYSIS,
    ),
    AiInvocationInventoryEntry(
        "frontend.command_palette.explain",
        "Anakin command registry explain/summarize/suggested actions",
        "POST /ai/explain",
        "explain_action",
        "explain",
        AI_PROFILE_FAST_TRIAGE,
    ),
    AiInvocationInventoryEntry(
        "frontend.command_palette.summarize",
        "Anakin command registry summarize",
        "POST /ai/explain",
        "explain_action",
        "summarize",
        AI_PROFILE_FAST_TRIAGE,
    ),
    AiInvocationInventoryEntry(
        "frontend.command_palette.suggested_actions",
        "Anakin command registry suggested actions",
        "POST /ai/explain",
        "explain_action",
        "suggestedactions",
        AI_PROFILE_GUIDED_ANALYSIS,
    ),
    AiInvocationInventoryEntry(
        "frontend.floating_chat.general",
        "FloatingSiemChat and Ask Anakin command",
        "POST /ai/chat",
        "route",
        "general_chat",
        AI_PROFILE_FAST_TRIAGE,
        "Short general SIEM chat with visible context.",
    ),
    AiInvocationInventoryEntry(
        "frontend.guided_investigation",
        "Guided investigation buttons and command",
        "POST /ai/investigations",
        "route",
        "guided_investigation",
        AI_PROFILE_GUIDED_ANALYSIS,
        "Bounded multi-source read-only analysis.",
    ),
    AiInvocationInventoryEntry(
        "frontend.drafts",
        "Draft buttons across alert/source/incident/recon/response registry",
        "POST /ai/drafts",
        "route",
        "drafting_service",
        AI_PROFILE_GUIDED_ANALYSIS,
        "Review-only structured drafts.",
    ),
    AiInvocationInventoryEntry(
        "worker.soc_briefing.manual_and_scheduled",
        "Manual Run Anakin Briefing Now and scheduled SOC briefing worker",
        "soc_briefing_worker",
        "capability",
        "scheduled_soc_briefing",
        AI_PROFILE_DEEP_BRIEFING,
        "Long-form structured SOC briefing synthesis; local-only.",
    ),
    AiInvocationInventoryEntry(
        "frontend.repo_architecture.chat",
        "RepoArchitectureAssistantPanel",
        "POST /ai/repo/requests",
        "route",
        "repo_architecture_chat",
        AI_PROFILE_DEVELOPER_ASSISTANT,
        "Repository/source-code assistance for super-admins.",
    ),
)


def profile_for_explain_action(action: str) -> str:
    normalized = str(action or "").strip().lower()
    if normalized in FAST_EXPLAIN_ACTIONS:
        return AI_PROFILE_FAST_TRIAGE
    return AI_PROFILE_GUIDED_ANALYSIS


def profile_for_draft_type(draft_type: str) -> str:
    normalized = str(draft_type or "").strip().lower()
    if normalized in GUIDED_DRAFT_TYPES:
        return AI_PROFILE_GUIDED_ANALYSIS
    return AI_PROFILE_GUIDED_ANALYSIS


def profile_for_investigation() -> str:
    return AI_PROFILE_GUIDED_ANALYSIS


def profile_for_chat() -> str:
    return AI_PROFILE_FAST_TRIAGE


def profile_for_agentic_planning() -> str:
    return AI_PROFILE_AGENTIC_PLANNING


def profile_for_soc_briefing() -> str:
    return AI_PROFILE_DEEP_BRIEFING


def profile_for_repo_assistant() -> str:
    return AI_PROFILE_DEVELOPER_ASSISTANT


def invocation_inventory() -> list[dict[str, str]]:
    return [entry.as_dict() for entry in AI_INVOCATION_INVENTORY]


def inventory_selectors(selector_type: str) -> set[str]:
    return {entry.selector for entry in AI_INVOCATION_INVENTORY if entry.selector_type == selector_type}
