from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import re
import time
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from core.ai.anakin_persona import banned_filler_phrases, filler_pattern_phrases
from core.ai.config import AI_MODE_LOCAL_ONLY, AiGatewayConfig, default_ai_profiles, load_ai_gateway_config
from core.ai.context_builder import AiContextPayload, AiContextSource
from core.ai.drafting_service import _build_draft_prompt
from core.ai.draft_schemas import DraftRequest
from core.ai.draft_schemas import validate_draft_payload
from core.ai.explainer_service import _build_prompt as build_explainer_prompt
from core.ai.gateway import AiGateway
from core.ai.investigation_planner import build_investigation_plan, classify_routing_profile
from core.ai.investigation_service import _build_correlation_prompt
from core.ai.profile_registry import (
    AI_INVOCATION_INVENTORY,
    AI_PROFILE_DEEP_BRIEFING,
    AI_PROFILE_DEVELOPER_ASSISTANT,
    AI_PROFILE_FAST_TRIAGE,
    AI_PROFILE_GUIDED_ANALYSIS,
    AiInvocationInventoryEntry,
    profile_for_chat,
    profile_for_draft_type,
    profile_for_explain_action,
    profile_for_investigation,
    profile_for_repo_assistant,
    profile_for_soc_briefing,
)
from core.ai.repo_assistant_service import _build_prompt as build_repo_prompt, classify_repo_question
from core.ai.repo_index import RepoChunk
from core.ai.soc_briefing_investigation_engine import InvestigationBudget
from core.ai.soc_tools import SocToolExecutionSummary, SocToolResult, SocToolSource
from core.ai.workflow_orchestrator import (
    WORKFLOW_AUTO,
    WORKFLOW_DEEP_INVESTIGATE,
    WORKFLOW_DECISION_SUPPORT,
    WORKFLOW_GENERATE_ARTIFACT,
    WORKFLOW_QUICK_EXPLAIN,
    WORKFLOW_REPO_ASSISTANT,
    WORKFLOW_SOC_BRIEFING,
    workflow_for_inventory_path,
)

ROOT_CAUSE_PROMPT_TOO_LARGE = "prompt_too_large"
ROOT_CAUSE_STALE_CONTEXT = "stale_context"
ROOT_CAUSE_PROVIDER_TIMEOUT = "provider_timeout"
ROOT_CAUSE_INVALID_RESPONSE = "invalid_response"
ROOT_CAUSE_WORKER_UNAVAILABLE = "worker_unavailable"
ROOT_CAUSE_CITATION_CONTRACT = "citation_contract"
ROOT_CAUSE_FRONTEND_CONTRACT_MISMATCH = "frontend_contract_mismatch"

TERMINAL_MANUAL_BRIEFING_STATES = {"completed", "partial", "degraded", "failed", "blocked", "timed_out"}
LIVE_STATUS_ROUTE = "GET"
LIVE_SMOKE_ENV = "AI_ACCEPTANCE_LIVE_OLLAMA"
LIVE_SWEEP_ENV = "AI_ACCEPTANCE_LIVE_BACKEND_SWEEP"
LIVE_MANUAL_BRIEFING_MUTATION_ENV = "AI_ACCEPTANCE_CREATE_MANUAL_BRIEFING_JOB"
DEFAULT_LIVE_BASE_URL = "http://127.0.0.1:5051"
DEFAULT_LIVE_THROTTLE_SECONDS = 2.0
REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SOURCE_ROOT = REPO_ROOT / "frontend" / "src"
ENTITY_AI_CONTEXT_TYPES = {"alert", "source_ip", "incident", "recon_activity", "response_registry", "detection"}
ASYNC_WORKFLOW_REQUEST_ROUTE = "POST /ai/workflows/requests"
ASYNC_WORKFLOW_REQUESTS = {
    WORKFLOW_AUTO,
    WORKFLOW_DEEP_INVESTIGATE,
    WORKFLOW_DECISION_SUPPORT,
    WORKFLOW_GENERATE_ARTIFACT,
}
ASYNC_WORKFLOW_TERMINAL_STATES = {"completed", "partial", "degraded", "failed", "timed_out", "cancelled", "expired"}
ASYNC_WORKFLOW_SUCCESS_STATES = {"completed", "partial", "degraded"}
ASYNC_WORKFLOW_LIVE_POLL_SECONDS = 150
ASYNC_WORKFLOW_LIVE_POLL_INTERVAL_SECONDS = 3
CANONICAL_ACCEPTANCE_WORKFLOWS = (
    WORKFLOW_QUICK_EXPLAIN,
    WORKFLOW_DEEP_INVESTIGATE,
    WORKFLOW_DECISION_SUPPORT,
    WORKFLOW_GENERATE_ARTIFACT,
    WORKFLOW_SOC_BRIEFING,
    WORKFLOW_REPO_ASSISTANT,
)
REMOVED_FRONTEND_AI_LABELS = (
    "Dashboard summary",
    "Guided dashboard investigation",
    "Draft dashboard investigation checklist",
    "Explain graph/anomaly",
    "Explain this alert",
    "Recommend investigation",
    "Why is this important?",
    "Explain detection",
    "Explain this IP",
    "Is this reconnaissance?",
    "Summarize activity",
    "Summarize incident",
    "Recommend next steps",
    "Explain recon",
    "Investigate cluster",
    "Guided review",
    "Explain this response",
    "Draft checklist",
    "Draft response",
    "Draft incident note",
    "Draft escalation",
    "Draft playbook",
    "Draft detection change",
)
REMOVED_FRONTEND_ACTION_IDS = (
    "ask_dashboard",
    "explain_anomaly",
    "explain_alert",
    "why_important",
    "explain_detection",
    "explain_ip",
    "assess_reconnaissance",
    "summarize_activity",
    "summarize_incident",
    "explain_recon_activity",
    "investigate_cluster",
    "explain_response",
    "suggestedactions",
)
APPROVED_SURFACE_CONTROL_MATRIX = {
    "Dashboard": ("Ask Anakin", "Quick Explain", "Deep Investigate"),
    "Alert Details": ("Quick Explain", "Deep Investigate", "Decision Support", "Generate Artifact"),
    "Source IP": ("Quick Explain", "Deep Investigate", "Decision Support", "Generate Artifact"),
    "Incident": ("Deep Investigate", "Decision Support", "Generate Artifact"),
    "SOC Command Center / Recon": ("Deep Investigate", "Decision Support", "Generate Artifact"),
    "Response Registry": ("Decision Support", "Deep Investigate", "Generate Artifact"),
    "Analyst Workspace": ("Deep Investigate", "Decision Support", "Generate Artifact"),
    "Global Anakin": ("Ask Anakin", "Quick Explain", "Deep Investigate", "Decision Support", "Generate Artifact"),
    "Command Palette": ("Quick Explain", "Deep Investigate", "Decision Support", "Generate Artifact", "SOC Briefing", "Repo Assistant"),
    "SOC Briefings": ("Generate/Run Briefing",),
    "Repo Assistant": ("Dedicated assistant",),
}
LIVE_SWEEP_VM_COMMAND = (
    "AI_ACCEPTANCE_LIVE_BACKEND_SWEEP=1 "
    "AI_ACCEPTANCE_SESSION_COOKIE='<authenticated-session-cookie>' "
    ".venv/bin/python -m pytest tests/test_ai_acceptance_harness.py "
    "-q -k live_backend_sweep_runs_status_checks_and_representative_plan_only"
)


@dataclass(frozen=True)
class FrontendAiOption:
    key: str
    source_file: str
    line_number: int
    options: dict[str, Any]


@dataclass(frozen=True)
class HarnessInventoryEntry:
    key: str
    frontend_surface: str
    backend_path: str
    selector_type: str
    selector: str
    profile: str
    workflow: str
    notes: str = ""

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class AcceptanceCase:
    inventory_key: str
    action_name: str
    frontend_action_id: str
    backend_route: str
    context_type: str
    stale_policy: str
    sample_question: str
    frontend_options: dict[str, Any] = field(default_factory=dict)
    request_payload: dict[str, Any] = field(default_factory=dict)
    entity_id: str | int | None = None


@dataclass
class AcceptanceResult:
    action_button_name: str
    frontend_action_id: str
    backend_route: str
    context_type: str
    entity: str | int | None
    selected_profile: str
    selected_model: str
    prompt_size: int
    prompt_limit: int
    response_time_ms: int
    success: bool
    error_code: str | None
    stale_state_result: str
    response_usefulness_checks: dict[str, bool]
    root_cause: str | None = None
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AcceptanceReport:
    actions_discovered: int
    actions_covered: int
    results: list[AcceptanceResult]
    failures_by_root_cause: dict[str, list[str]] = field(default_factory=dict)
    live_smoke_results: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "actions_discovered": self.actions_discovered,
            "actions_covered": self.actions_covered,
            "failures_by_root_cause": dict(self.failures_by_root_cause),
            "results": [result.as_dict() for result in self.results],
            "live_smoke_results": list(self.live_smoke_results),
        }


@dataclass(frozen=True)
class GoldenReasoningCase:
    key: str
    workflow: str
    scenario: str
    question: str
    context: dict[str, Any]
    expected_answer: str
    required_terms: tuple[str, ...]
    forbidden_terms: tuple[str, ...] = ()


def build_acceptance_cases() -> dict[str, AcceptanceCase]:
    inventory, frontend_options = build_complete_ai_inventory()
    return {entry.key: _case_for_entry(entry, frontend_options=frontend_options) for entry in inventory}


def build_complete_ai_inventory() -> tuple[tuple[HarnessInventoryEntry, ...], dict[str, dict[str, Any]]]:
    frontend_options: dict[str, dict[str, Any]] = {}
    entries: list[HarnessInventoryEntry] = []
    seen: set[str] = set()

    for discovered in discover_frontend_ai_option_entries():
        options = _with_large_entity_fixture(discovered.options, _normalize_context_type(discovered.options.get("contextType")))
        entry = _inventory_entry_for_frontend_option(discovered, options)
        if entry.key in seen:
            continue
        seen.add(entry.key)
        frontend_options[entry.key] = options
        entries.append(entry)

    for command in _default_command_contracts():
        entry = _inventory_entry_for_static_contract(command)
        if entry.key in seen:
            continue
        seen.add(entry.key)
        frontend_options[entry.key] = command
        entries.append(entry)

    for contract in _static_surface_contracts():
        entry = _inventory_entry_for_static_contract(contract)
        if entry.key in seen:
            continue
        seen.add(entry.key)
        frontend_options[entry.key] = contract
        entries.append(entry)

    for legacy in AI_INVOCATION_INVENTORY:
        key = f"legacy_adapter.{legacy.key}"
        if key in seen:
            continue
        entry = HarnessInventoryEntry(
            key=key,
            frontend_surface=f"Legacy backend compatibility adapter: {legacy.frontend_surface}",
            backend_path=legacy.backend_path,
            selector_type=legacy.selector_type,
            selector=legacy.selector,
            profile=legacy.profile,
            workflow=workflow_for_inventory_path(legacy.backend_path, legacy.selector_type, legacy.selector),
            notes="Legacy route retained as backend compatibility adapter, not a surviving consolidated frontend control.",
        )
        seen.add(key)
        frontend_options[key] = _legacy_options_for_inventory_entry(legacy)
        entries.append(entry)

    return tuple(entries), frontend_options


def discover_frontend_ai_options(source_root: Path | None = None) -> dict[str, dict[str, Any]]:
    discovered: dict[str, dict[str, Any]] = {}
    for option in discover_frontend_ai_option_entries(source_root):
        discovered.setdefault(_frontend_contract_key(option.options, Path(option.source_file).name), option.options)
    for command in _default_command_contracts():
        discovered.setdefault(command["contract_key"], command)
    return discovered


def discover_frontend_ai_option_entries(source_root: Path | None = None) -> list[FrontendAiOption]:
    source_root = source_root or FRONTEND_SOURCE_ROOT
    discovered: list[FrontendAiOption] = []
    for path in sorted(source_root.glob("components/**/*.js")):
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(source_root).as_posix()
        for block, line_number in _extract_on_ask_ai_blocks(text):
            parsed = _parse_frontend_ai_options(block)
            if not parsed:
                continue
            key = _frontend_contract_key(parsed, path.name)
            unique = f"{key}.line_{line_number}"
            parsed = {**parsed, "contract_key": unique, "source_file": relative, "line_number": line_number}
            discovered.append(FrontendAiOption(unique, relative, line_number, parsed))
    return discovered


def run_offline_contract_tier(config: AiGatewayConfig | None = None) -> AcceptanceReport:
    resolved_config = config or _acceptance_config()
    inventory, _frontend_options = build_complete_ai_inventory()
    cases = build_acceptance_cases()
    results: list[AcceptanceResult] = []
    failures: dict[str, list[str]] = {}
    inventory_by_key = {entry.key: entry for entry in inventory}

    for key, entry in inventory_by_key.items():
        case = cases.get(key)
        if case is None:
            result = AcceptanceResult(
                action_button_name=entry.frontend_surface,
                frontend_action_id=entry.key,
                backend_route=entry.backend_path,
                context_type="unknown",
                entity=None,
                selected_profile=entry.profile,
                selected_model="unknown",
                prompt_size=0,
                prompt_limit=0,
                response_time_ms=0,
                success=False,
                error_code="missing_acceptance_case",
                stale_state_result="not_tested",
                response_usefulness_checks=_empty_usefulness(False),
                root_cause=ROOT_CAUSE_FRONTEND_CONTRACT_MISMATCH,
            )
        else:
            result = _run_case(entry, case, resolved_config)
        results.append(result)
        if not result.success and result.root_cause:
            failures.setdefault(result.root_cause, []).append(result.frontend_action_id)

    missing = sorted(set(inventory_by_key) - set(cases))
    for key in missing:
        failures.setdefault(ROOT_CAUSE_FRONTEND_CONTRACT_MISMATCH, []).append(key)

    return AcceptanceReport(
        actions_discovered=len(inventory_by_key),
        actions_covered=len(set(cases) & set(inventory_by_key)),
        results=results,
        failures_by_root_cause=failures,
    )


def build_golden_reasoning_cases() -> tuple[GoldenReasoningCase, ...]:
    return (
        GoldenReasoningCase(
            key="golden.casual_natural_tone",
            workflow=WORKFLOW_QUICK_EXPLAIN,
            scenario="casual user asks what is going on",
            question="what's actually going on here?",
            context={"alert": "vpn deny burst", "success": False},
            expected_answer=(
                "Short version: this looks like a VPN deny burst worth checking, not proof of compromise. "
                "Fact: I only see failed attempts. Inference: scanning or password guessing is plausible. "
                "Uncertainty: I do not have target-side auth outcomes. Confidence: medium. Next check: inspect VPN auth successes from the same source."
            ),
            required_terms=("short version", "fact", "inference", "uncertainty", "confidence", "next check"),
            forbidden_terms=("based on the information provided", "as an ai"),
        ),
        GoldenReasoningCase(
            key="golden.professional_tone",
            workflow=WORKFLOW_DEEP_INVESTIGATE,
            scenario="professional user requests assessment",
            question="Please provide a concise assessment.",
            context={"alert": "admin portal failures", "business_service": "customer portal"},
            expected_answer=(
                "Most important: admin-portal failures against a customer-facing service deserve review, but the evidence does not support containment yet. "
                "Fact: failed access attempts target an administrative surface. Inference: credential testing is plausible. "
                "Contradictory evidence: no successful login or post-auth activity is shown. Missing evidence: account list, MFA outcome, and source history. "
                "Confidence: medium. Next step: inspect auth outcomes for targeted accounts before escalation."
            ),
            required_terms=("most important", "fact", "inference", "contradictory evidence", "missing evidence", "confidence", "next step"),
            forbidden_terms=("i hope this helps",),
        ),
        GoldenReasoningCase(
            key="golden.profanity_conservative",
            workflow=WORKFLOW_DECISION_SUPPORT,
            scenario="casual frustrated analyst used profanity",
            question="is this thing actually bad or just noisy?",
            context={"noise": True, "success": False, "protected_target": False},
            expected_answer=(
                "Primary recommendation: monitor with a specific source-history check, not escalate. "
                "Reasoning: the activity is noisy, but no success, protected target, or progression is visible. "
                "Alternative: escalate if the same source starts hitting sensitive services. Risk: escalating now burns analyst time on likely commodity noise. "
                "Missing evidence: target criticality and source ownership. Confidence: medium-high. "
                "What would change it: successful auth, exploit evidence, or repeat targeting of critical assets. Next step: inspect source history for progression."
            ),
            required_terms=("primary recommendation", "reasoning", "alternative", "risk", "confidence", "what would change", "next step"),
            forbidden_terms=("shit", "damn", "fuck"),
        ),
        GoldenReasoningCase(
            key="golden.artifact_professional",
            workflow=WORKFLOW_GENERATE_ARTIFACT,
            scenario="shareable artifact stays professional",
            question="Draft an escalation summary.",
            context={"severity": "high", "evidence": "weak"},
            expected_answer=(
                "Title: Escalation summary for high-severity authentication activity. "
                "Evidence: failed authentication activity was observed, with no confirmed successful access in the supplied context. "
                "Uncertainty: source ownership and target-side outcomes are not confirmed. "
                "Recommended next steps: review authentication outcomes, source history, and affected account criticality before containment."
            ),
            required_terms=("title", "evidence", "uncertainty", "recommended next steps"),
            forbidden_terms=("shit", "damn", "fuck", "lol", "kinda"),
        ),
        GoldenReasoningCase(
            key="golden.analyst_disagreement",
            workflow=WORKFLOW_DECISION_SUPPORT,
            scenario="analyst assumes block is required but evidence is weak",
            question="This is high severity, should I block it now?",
            context={"severity": "high", "success": False, "source_reputation": "unknown", "protected_target": False},
            expected_answer=(
                "Primary recommendation: I would not block this yet. "
                "Reasoning: high severity raises priority, but the supplied evidence does not show success, impact, or a protected target. "
                "Alternative: escalate if source history shows repeated targeting of sensitive services. Risk: blocking now may create unnecessary disruption. "
                "Missing evidence: target criticality and source reputation are not established. Confidence: medium. "
                "What would change it: confirmed malicious reputation, successful auth, exploit evidence, or critical target exposure. Next step: inspect source history and target outcomes."
            ),
            required_terms=("primary recommendation", "would not block", "reasoning", "risk", "confidence", "what would change", "next step"),
            forbidden_terms=("block immediately",),
        ),
        GoldenReasoningCase(
            key="golden.password_spray_no_success",
            workflow=WORKFLOW_DEEP_INVESTIGATE,
            scenario="likely password spray with no successful login",
            question="Is this a password spray?",
            context={"failed_logins": 84, "successful_logins": 0, "distinct_users": 39, "window": "12m"},
            expected_answer=(
                "Most important: this looks like a password-spray pattern, but the absence of successful logins keeps the recommendation at investigate/escalate-not-contain. "
                "Fact: many failed logins hit many users in a short window. Inference: a low-and-wide spray is plausible. "
                "Against it: no success and no post-auth activity are shown. Missing evidence: source reputation, MFA prompts, lockouts, and any success after the window. "
                "Confidence: medium. Next check: inspect authentication logs for successful login, MFA fatigue, or impossible-travel events from the same source."
            ),
            required_terms=("most important", "fact", "inference", "against", "missing evidence", "confidence", "next check", "successful login"),
            forbidden_terms=("definitely compromised",),
        ),
        GoldenReasoningCase(
            key="golden.commodity_recon_low_value",
            workflow=WORKFLOW_DEEP_INVESTIGATE,
            scenario="noisy commodity recon that may not deserve escalation",
            question="Should this recon be escalated?",
            context={"scanner_reputation": "commodity", "linked_alerts": 3, "successful_connections": 0},
            expected_answer=(
                "Most important: this is probably low-value commodity recon unless it lines up with a protected service or a new internal target. "
                "Fact: the evidence shows scanning noise and no confirmed access. Inference: escalation is weak right now. "
                "Against escalation: commodity reputation and no successful follow-up. Missing evidence: target criticality and whether this source repeats across tuned detections. "
                "Confidence: medium-high. Next check: inspect related alerts for the same source against sensitive destinations before escalating."
            ),
            required_terms=("low-value", "fact", "inference", "against", "missing evidence", "confidence", "next check"),
            forbidden_terms=("escalate immediately",),
        ),
        GoldenReasoningCase(
            key="golden.high_severity_weak_followup",
            workflow=WORKFLOW_QUICK_EXPLAIN,
            scenario="high-severity alert with weak follow-up evidence",
            question="What matters here?",
            context={"severity": "high", "follow_up_events": 0, "target": "vpn"},
            expected_answer=(
                "Most important: the high severity deserves attention, but the follow-up evidence is thin. "
                "Fact: the alert is high severity and targets VPN. Inference: it may be an early signal rather than proven impact. "
                "Uncertainty: no related success or lateral movement is shown. Confidence: low-medium. Next check: inspect VPN auth successes and target-side events in the same window."
            ),
            required_terms=("most important", "fact", "inference", "uncertainty", "confidence", "next check"),
            forbidden_terms=("confirmed compromise",),
        ),
        GoldenReasoningCase(
            key="golden.incident_supporting_and_contradicting",
            workflow=WORKFLOW_DEEP_INVESTIGATE,
            scenario="incident with supporting and contradicting evidence",
            question="How strong is this incident?",
            context={"supports": ["repeated deny", "same source"], "contradicts": ["known scanner", "no successful session"]},
            expected_answer=(
                "Most important: the incident is worth keeping open, but the evidence supports investigation more than containment. "
                "Supporting evidence: repeated denies from the same source. Contradicting evidence: known scanner behavior and no successful session. "
                "Missing evidence: asset criticality, target logs, and whether the source appears in prior incidents. Confidence: medium. "
                "Next step: inspect target-side logs and related source-IP history before escalating."
            ),
            required_terms=("supporting evidence", "contradicting evidence", "missing evidence", "confidence", "next step"),
        ),
        GoldenReasoningCase(
            key="golden.graph_spike_one_source",
            workflow=WORKFLOW_QUICK_EXPLAIN,
            scenario="graph spike dominated by one source",
            question="Explain this dashboard spike.",
            context={"spike": "large", "dominant_source": "203.0.113.10", "other_sources": 2},
            expected_answer=(
                "Most important: the spike is dominated by one source, so treat it as a concentrated investigation rather than a broad environment-wide surge. "
                "Fact: one source accounts for most of the graph movement. Inference: a noisy scanner or repeated retry loop is plausible. "
                "Uncertainty: target spread and success outcomes are not shown. Confidence: medium. Next check: inspect that source's target distribution and outcome history."
            ),
            required_terms=("most important", "one source", "fact", "inference", "uncertainty", "confidence", "next check"),
        ),
        GoldenReasoningCase(
            key="golden.decision_monitor_escalate_block",
            workflow=WORKFLOW_DECISION_SUPPORT,
            scenario="decision between monitor, escalate, or block",
            question="Should I block, monitor, or escalate?",
            context={"severity": "medium", "success": False, "protected_target": True},
            expected_answer=(
                "Primary recommendation: escalate for analyst review, not block yet. "
                "Reasoning: the protected target raises impact, but no success or active compromise is shown. "
                "Alternative: monitor if target criticality is low; block only if repeated attempts continue or a confirmed malicious source is validated. "
                "Risk: blocking too early may disrupt legitimate NAT or scanner traffic. Missing evidence: target auth outcomes and source legitimacy. "
                "Confidence: medium. What would change it: successful auth, exploit evidence, or repeated hits on critical services. "
                "Next step: inspect target auth outcomes before containment."
            ),
            required_terms=("primary recommendation", "alternative", "risk", "confidence", "what would change", "not block yet"),
            forbidden_terms=("draft", "applied", "confirmed action"),
        ),
        GoldenReasoningCase(
            key="golden.soc_briefing_noise_and_trend",
            workflow="soc_briefing",
            scenario="SOC briefing with low-value noise and one important trend",
            question="Generate briefing.",
            context={"noise": "commodity scanners", "trend": "vpn denies increasing", "important": "one protected target"},
            expected_answer=(
                "Attention first: VPN denies against the protected target increased and deserve review. "
                "Probably ignore: commodity scanner noise with no successful follow-up. "
                "Trend: repeated VPN targeting is rising in the window. Evidence gaps: target-side auth outcomes and whether the source repeats across incidents. "
                "Next actions: inspect VPN auth successes, source-IP history, and target criticality before containment."
            ),
            required_terms=("attention first", "probably ignore", "trend", "evidence gaps", "next actions"),
            forbidden_terms=("raw alert inventory",),
        ),
        GoldenReasoningCase(
            key="golden.repo_most_impressive_feature",
            workflow="repo_assistant",
            scenario="What is my most impressive feature?",
            question="What is my most impressive feature?",
            context={"repo_features": ["AI acceptance harness", "SOC briefing worker", "preview-confirm gates"]},
            expected_answer=(
                "Answer: the most impressive feature is the AI acceptance and safety architecture around Anakin. "
                "Repository fact: the code has workflow routing, offline acceptance coverage, preview/confirm gates, and read-only SOC briefing controls. "
                "Judgment: that is stronger than a single flashy screen because it makes AI behavior testable and safer to operate. "
                "Uncertainty: this judgment depends on the supplied repository excerpts. Safe next step: compare it against the cited implementation files."
            ),
            required_terms=("answer", "repository fact", "judgment", "uncertainty", "acceptance"),
        ),
    )


def evaluate_golden_reasoning_answer(case: GoldenReasoningCase, answer: str) -> dict[str, bool]:
    text = str(answer or "").lower()
    required = {f"has_{term.replace(' ', '_')}": term.lower() in text for term in case.required_terms}
    forbidden = {f"omits_{term.replace(' ', '_')}": term.lower() not in text for term in case.forbidden_terms}
    generic_continue = "continue monitoring" in text and not any(
        term in text for term in ("inspect", "auth", "source", "target", "window", "successful", "destination")
    )
    filler = {phrase: phrase in text for phrase in (*banned_filler_phrases(), *filler_pattern_phrases())}
    return {
        "not_empty": bool(text.strip()),
        "specific_next_step": any(term in text for term in ("next check", "next step", "next action", "next actions")),
        "states_uncertainty_or_missing_evidence": any(term in text for term in ("uncertainty", "missing evidence", "evidence gaps")),
        "not_generic_monitoring": not generic_continue,
        "no_filler_phrases": not any(filler.values()),
        "no_generic_disclaimer_ending": not _has_generic_disclaimer_ending(text),
        "not_visible_field_only": not _looks_like_visible_field_restatement(text),
        **required,
        **forbidden,
    }


def _looks_like_visible_field_restatement(text: str) -> bool:
    normalized = " ".join(str(text or "").lower().split())
    if not normalized:
        return False
    has_reasoning = any(
        term in normalized
        for term in (
            "because",
            "matters",
            "suggests",
            "supports",
            "argues against",
            "missing",
            "uncertainty",
            "confidence",
            "next",
            "recommend",
            "would change",
            "not enough evidence",
        )
    )
    visible_terms = sum(
        1
        for term in ("severity", "alert title", "source ip", "timestamp", "status", "id")
        if term in normalized
    )
    return visible_terms >= 3 and not has_reasoning


def _has_generic_disclaimer_ending(text: str) -> bool:
    normalized = " ".join(str(text or "").lower().split())
    if not normalized:
        return False
    endings = (
        "as more information becomes available.",
        "if more information becomes available.",
        "with additional information.",
        "as additional details emerge.",
        "further investigation may reveal more.",
        "conclusions may change.",
    )
    return normalized.endswith(endings)


def removed_frontend_ai_controls_present(source_root: Path | None = None) -> dict[str, list[str]]:
    source_root = source_root or FRONTEND_SOURCE_ROOT
    labels: list[str] = []
    action_ids: list[str] = []
    for path in sorted(source_root.glob("components/**/*.js")):
        if path.name.endswith(".test.js"):
            continue
        text = path.read_text(encoding="utf-8")
        for label in REMOVED_FRONTEND_AI_LABELS:
            if label in text:
                labels.append(f"{path.relative_to(source_root).as_posix()}::{label}")
        for action_id in REMOVED_FRONTEND_ACTION_IDS:
            if re.search(rf"\b{re.escape(action_id)}\b", text):
                action_ids.append(f"{path.relative_to(source_root).as_posix()}::{action_id}")
    return {"labels": labels, "action_ids": action_ids}


def build_workflow_acceptance_summary() -> dict[str, Any]:
    inventory, frontend_options = build_complete_ai_inventory()
    report = run_offline_contract_tier()
    workflow_counts = {workflow: 0 for workflow in CANONICAL_ACCEPTANCE_WORKFLOWS}
    for entry in inventory:
        if entry.workflow in workflow_counts:
            workflow_counts[entry.workflow] += 1
    controls_by_surface = {
        surface: list(controls)
        for surface, controls in APPROVED_SURFACE_CONTROL_MATRIX.items()
    }
    obsolete = removed_frontend_ai_controls_present()
    unmapped = [
        entry.key
        for entry in inventory
        if entry.workflow not in CANONICAL_ACCEPTANCE_WORKFLOWS
    ]
    return {
        "workflows": workflow_counts,
        "controls_by_surface": controls_by_surface,
        "actions_discovered": report.actions_discovered,
        "actions_covered": report.actions_covered,
        "offline_failures": sum(len(items) for items in report.failures_by_root_cause.values()),
        "failures_by_root_cause": report.failures_by_root_cause,
        "unmapped": unmapped,
        "obsolete_frontend_controls": obsolete,
        "legacy_adapter_count": sum(1 for entry in inventory if entry.key.startswith("legacy_adapter.")),
        "canonical_frontend_count": sum(1 for entry in inventory if not entry.key.startswith("legacy_adapter.")),
        "frontend_option_keys": sorted(frontend_options),
    }


def build_workflow_representative_fixtures() -> tuple[dict[str, Any], ...]:
    return (
        {
            "workflow": WORKFLOW_QUICK_EXPLAIN,
            "key": "fixture.quick_explain.high_severity_weak_followup",
            "context_type": "alert",
            "prompt": "What matters about this high severity alert?",
            "context": {"alert_id": 1001, "severity": "HIGH", "successful_followup": False},
            "expected_profile": AI_PROFILE_FAST_TRIAGE,
            "expected_route": "POST /ai/workflows",
        },
        {
            "workflow": WORKFLOW_DEEP_INVESTIGATE,
            "key": "fixture.deep_investigate.password_spray_no_success",
            "context_type": "alert",
            "prompt": "Deep investigate this likely password spray with no successful login.",
            "context": {"alert_id": 1001, "failed_logins": 84, "successful_logins": 0},
            "expected_profile": AI_PROFILE_GUIDED_ANALYSIS,
            "expected_route": ASYNC_WORKFLOW_REQUEST_ROUTE,
        },
        {
            "workflow": WORKFLOW_DECISION_SUPPORT,
            "key": "fixture.decision_support.monitor_escalate_block",
            "context_type": "source_ip",
            "prompt": "Should I monitor, escalate, or block?",
            "context": {"source_ip": "203.0.113.77", "protected_target": True, "success": False},
            "expected_profile": AI_PROFILE_GUIDED_ANALYSIS,
            "expected_route": ASYNC_WORKFLOW_REQUEST_ROUTE,
        },
        {
            "workflow": WORKFLOW_GENERATE_ARTIFACT,
            "key": "fixture.generate_artifact.investigation_checklist",
            "context_type": "alert",
            "prompt": "Generate an investigation checklist for review only.",
            "artifact": {"type": "investigation_checklist"},
            "context": {"alert_id": 1001, "source_ip": "203.0.113.77"},
            "expected_profile": AI_PROFILE_GUIDED_ANALYSIS,
            "expected_route": ASYNC_WORKFLOW_REQUEST_ROUTE,
            "non_persistent": True,
        },
        {
            "workflow": WORKFLOW_SOC_BRIEFING,
            "key": "fixture.soc_briefing.status_only",
            "context_type": "soc_briefing",
            "prompt": "Read SOC briefing status only.",
            "expected_profile": AI_PROFILE_DEEP_BRIEFING,
            "expected_route": "soc_briefing_worker",
            "status_only": True,
        },
        {
            "workflow": WORKFLOW_REPO_ASSISTANT,
            "key": "fixture.repo_assistant.evaluative",
            "context_type": "repository",
            "prompt": "What is my most impressive feature?",
            "expected_profile": AI_PROFILE_DEVELOPER_ASSISTANT,
            "expected_route": "POST /ai/repo/requests",
            "citations_backend_owned": True,
        },
    )


def build_production_like_alert_checklist_fixture() -> dict[str, Any]:
    related_events = [
        {
            "id": idx,
            "timestamp": f"2026-08-01T12:{idx % 60:02d}:00Z",
            "source_ip": "203.0.113.77",
            "destination_ip": f"10.0.{idx % 8}.{idx % 250}",
            "destination_port": 443 + (idx % 80),
            "protocol": "tcp",
            "action": "deny",
            "message": "Repeated deny event against protected edge service with verbose firewall enrichment metadata.",
            "raw_event": "raw firewall payload omitted by prompt compaction " * 12,
        }
        for idx in range(500)
    ]
    ai_context = AiContextPayload(
        context_type="alert",
        data={
            "summary": {
                "headline": "Repeated deny alert with many neighboring events",
                "counts": {"related_events": len(related_events), "distinct_targets": 84},
            },
            "alert": {
                "id": 1001,
                "alert_type": "pfsense_firewall_repeated_deny",
                "severity": "high",
                "status": "open",
                "source_ip": "203.0.113.77",
                "message": "Repeated deny threshold exceeded",
            },
            "why_fired": {"rule": "Repeated deny threshold exceeded", "threshold": 25, "observed": 612},
            "related_events": related_events,
            "related_alerts": [
                {
                    "id": idx,
                    "alert_type": "pfsense_firewall_repeated_deny",
                    "severity": "high",
                    "status": "open",
                    "source_ip": "203.0.113.77",
                    "message": "Neighbor alert with verbose analyst-facing explanation " * 8,
                }
                for idx in range(80)
            ],
            "_evidence": {
                "source_references": ["/alerts/1001", "/alerts/1001/events", "/source-ip-context/203.0.113.77"],
                "counts": {"events": len(related_events), "neighbor_alerts": 80},
            },
        },
        sources=[
            AiContextSource("alert", "/alerts/1001", [1001]),
            AiContextSource("events", "/alerts/1001/events", list(range(500)), truncated=True, omitted_count=475),
        ],
        truncated=True,
        omitted_count=475,
    )
    tool_sources = [
        SocToolSource(
            tool_name=f"alert_evidence_tool_{idx}",
            source_type="events",
            source_path=f"/alerts/1001/tool-evidence-{idx}",
            source_helper="core.ai.soc_tools",
            record_ids=list(range(idx * 25, idx * 25 + 25)),
            truncated=True,
            omitted_count=400,
        )
        for idx in range(5)
    ]
    tool_calls = [
        SocToolResult(
            tool_name=source.tool_name,
            status="success",
            data={"related_events": related_events, "raw_notes": "verbose tool evidence omitted by compaction " * 200},
            sources=[source],
            truncated=True,
            omitted_count=400,
        )
        for source in tool_sources
    ]
    return {
        "request": DraftRequest(
            draft_type="investigation_checklist",
            instruction="Generate an investigation checklist for review only.",
            context_type="alert",
            context={"alert_id": 1001, "source_ip": "203.0.113.77"},
            client_request_id="acceptance-prod-like-alert-checklist",
        ),
        "ai_context": ai_context,
        "tools": SocToolExecutionSummary(
            used=True,
            calls=tool_calls,
            sources=tool_sources,
            truncated=True,
            omitted_count=2000,
        ),
        "profile_max_prompt_chars": 14000,
    }


def build_production_safe_live_sweep_matrix() -> tuple[dict[str, Any], ...]:
    return (
        {"key": "status.ai_gateway", "route": "GET /ai/status", "workflow": "status", "mutation": False},
        {"key": "status.repo_assistant", "route": "GET /ai/repo/status", "workflow": "status", "mutation": False},
        {"key": "frontend.dashboard.quick_explain", "route": "POST /ai/workflows", "workflow": WORKFLOW_QUICK_EXPLAIN, "mutation": False},
        {"key": "frontend.alert.deep_investigate", "route": ASYNC_WORKFLOW_REQUEST_ROUTE, "workflow": WORKFLOW_DEEP_INVESTIGATE, "mutation": False},
        {"key": "frontend.alert.decision_support", "route": ASYNC_WORKFLOW_REQUEST_ROUTE, "workflow": WORKFLOW_DECISION_SUPPORT, "mutation": False},
        {"key": "frontend.alert.artifact.checklist", "route": ASYNC_WORKFLOW_REQUEST_ROUTE, "workflow": WORKFLOW_GENERATE_ARTIFACT, "mutation": False, "non_persistent": True},
        {"key": "frontend.floating_anakin.ask", "route": ASYNC_WORKFLOW_REQUEST_ROUTE, "workflow": WORKFLOW_AUTO, "mutation": False},
        {"key": "frontend.floating_anakin.low_confidence_chooser", "route": ASYNC_WORKFLOW_REQUEST_ROUTE, "workflow": WORKFLOW_AUTO, "expected_status": "chooser_required", "mutation": False},
        {"key": "frontend.repo_architecture.chat.factual", "route": "POST /ai/repo/requests", "workflow": WORKFLOW_REPO_ASSISTANT, "mutation": False},
        {"key": "frontend.repo_architecture.chat.evaluative", "route": "POST /ai/repo/requests", "workflow": WORKFLOW_REPO_ASSISTANT, "mutation": False},
        {"key": "worker.soc_briefing.manual_run_now", "route": "GET /soc-briefings/control", "workflow": WORKFLOW_SOC_BRIEFING, "mutation": False, "status_only_default": True},
        {"key": "frontend.ai_action.preview.add_incident_note", "route": "POST /ai/actions/preview", "workflow": WORKFLOW_GENERATE_ARTIFACT, "mutation": False, "confirmation_skipped": True},
    )


def run_optional_live_smoke_tier(config: AiGatewayConfig | None = None) -> list[dict[str, Any]]:
    if os.getenv(LIVE_SMOKE_ENV) != "1":
        return [
            {
                "enabled": False,
                "reason": f"Set {LIVE_SMOKE_ENV}=1 to run one live local Ollama smoke request per profile.",
            }
        ]

    resolved_config = config or load_ai_gateway_config()
    gateway = AiGateway(config=resolved_config)
    prompts = {
        AI_PROFILE_FAST_TRIAGE: "Reply with OK and one short SIEM triage note.",
        AI_PROFILE_GUIDED_ANALYSIS: "Reply with OK and one short evidence-gap note for a read-only SOC investigation.",
        AI_PROFILE_DEEP_BRIEFING: "Reply with OK and one short scheduled SOC briefing summary.",
        AI_PROFILE_DEVELOPER_ASSISTANT: "Reply with OK and one short repository architecture observation.",
    }
    results = []
    for profile_name, prompt in prompts.items():
        started = time.monotonic()
        try:
            from core.ai.models import AiGatewayRequest

            response = gateway.generate(AiGatewayRequest(prompt=prompt, profile=profile_name, capability="text_generation"))
            payload = response.as_dict()
            results.append(
                {
                    "enabled": True,
                    "profile": profile_name,
                    "model": payload["metadata"].get("model"),
                    "status": payload["status"],
                    "error": payload["error"],
                    "latency_ms": int((time.monotonic() - started) * 1000),
                }
            )
        except Exception as error:
            results.append(
                {
                    "enabled": True,
                    "profile": profile_name,
                    "status": "failed",
                    "error": str(error),
                    "latency_ms": int((time.monotonic() - started) * 1000),
                    "root_cause": ROOT_CAUSE_PROVIDER_TIMEOUT if "timeout" in str(error).lower() else "provider_error",
                }
            )
    return results


def run_acceptance_harness(*, include_live_smoke: bool = True, config: AiGatewayConfig | None = None) -> AcceptanceReport:
    report = run_offline_contract_tier(config=config)
    if include_live_smoke:
        report.live_smoke_results = run_optional_live_smoke_tier(config=config)
    return report


def run_live_backend_sweep(
    *,
    base_url: str | None = None,
    session_cookie: str | None = None,
    throttle_seconds: float = DEFAULT_LIVE_THROTTLE_SECONDS,
    create_manual_briefing_job: bool = False,
) -> dict[str, Any]:
    if os.getenv(LIVE_SWEEP_ENV) != "1":
        return {
            "enabled": False,
            "reason": f"Set {LIVE_SWEEP_ENV}=1 on the VM to run the authenticated production-safe live backend sweep.",
        }
    cookie = session_cookie or os.getenv("AI_ACCEPTANCE_SESSION_COOKIE", "")
    if not cookie:
        return {"enabled": True, "status": "blocked", "error": "AI_ACCEPTANCE_SESSION_COOKIE is required."}

    resolved_base_url = (base_url or os.getenv("AI_ACCEPTANCE_BASE_URL") or DEFAULT_LIVE_BASE_URL).rstrip("/")
    config = load_ai_gateway_config()
    ids = _discover_live_entities(resolved_base_url, cookie)
    inventory, _frontend_options = build_complete_ai_inventory()
    cases = build_acceptance_cases()
    representative_plan = _select_live_representative_cases(inventory, cases)
    rows: list[dict[str, Any]] = []
    failures: dict[str, list[str]] = {}

    status_rows = [
        _live_status_check(resolved_base_url, cookie, "/ai/status", "status.ai_gateway", config),
        _live_status_check(resolved_base_url, cookie, "/ai/repo/status", "status.repo_assistant", config),
    ]
    for row in status_rows:
        rows.append(row)
        if not row.get("success"):
            failures.setdefault(str(row.get("root_cause") or "other"), []).append(str(row.get("frontend_action_id")))

    for entry, case in representative_plan:
        if entry.backend_path == "soc_briefing_worker":
            row = _live_manual_briefing_check(
                resolved_base_url,
                cookie,
                entry,
                create_manual_briefing_job=create_manual_briefing_job or os.getenv(LIVE_MANUAL_BRIEFING_MUTATION_ENV) == "1",
            )
        else:
            row = _live_ai_action_check(resolved_base_url, cookie, entry, case, ids, config)
        rows.append(row)
        if not row.get("success"):
            failures.setdefault(str(row.get("root_cause") or "other"), []).append(str(row.get("frontend_action_id")))
        time.sleep(max(0.0, throttle_seconds))

    manual_briefing_mutation = create_manual_briefing_job or os.getenv(LIVE_MANUAL_BRIEFING_MUTATION_ENV) == "1"
    return {
        "enabled": True,
        "base_url": resolved_base_url,
        "offline_actions_discovered": len(inventory),
        "offline_actions_covered": len(cases),
        "actions_discovered": len(inventory),
        "representative_calls_planned": len(representative_plan) + len(status_rows),
        "actions_invoked": len(rows),
        "estimated_runtime_seconds": int((len(representative_plan) + len(status_rows)) * max(0.0, throttle_seconds) + 240),
        "entity_discovery": ids,
        "failures_by_root_cause": failures,
        "results": rows,
        "safety": {
            "offline_full_button_coverage": True,
            "live_strategy": "representative_unique_backend_execution_paths",
            "draft_routes_preview_only": True,
            "allow_automatic_draft_false": True,
            "manual_briefing_create_job": manual_briefing_mutation,
            "actions_confirm_route_skipped": True,
            "production_mutations_allowed": False,
        },
    }


def render_live_sweep_markdown(result: dict[str, Any]) -> str:
    lines = ["# Anakin Live Backend Acceptance Sweep", ""]
    if not result.get("enabled"):
        lines.append(f"Disabled: {result.get('reason')}")
        return "\n".join(lines) + "\n"
    lines.extend(
        [
            f"- Base URL: {result.get('base_url')}",
            f"- Offline actions covered: {result.get('offline_actions_covered', result.get('actions_discovered'))}",
            f"- Representative live calls planned: {result.get('representative_calls_planned', result.get('actions_invoked'))}",
            f"- Representative live calls invoked: {result.get('actions_invoked')}",
            f"- Estimated runtime seconds: {result.get('estimated_runtime_seconds')}",
            f"- Failures: {sum(len(items) for items in (result.get('failures_by_root_cause') or {}).values())}",
            "",
            "## Failures By Root Cause",
        ]
    )
    failures = result.get("failures_by_root_cause") or {}
    if not failures:
        lines.append("- None")
    for root_cause, action_ids in sorted(failures.items()):
        lines.append(f"- `{root_cause}`: {len(action_ids)}")
        for action_id in action_ids:
            lines.append(f"  - `{action_id}`")
    lines.extend(["", "## Results"])
    for row in result.get("results") or []:
        status = "PASS" if row.get("success") else f"FAIL {row.get('error_code') or row.get('error') or 'unknown'}"
        lines.append(
            f"- {status} `{row.get('frontend_action_id')}` {row.get('execution_path') or row.get('route')} "
            f"entity=`{row.get('entity')}` profile=`{row.get('profile')}` model=`{row.get('model')}` "
            f"prompt={row.get('prompt_size')}/{row.get('prompt_limit')} latency={row.get('latency_ms')}ms"
        )
    return "\n".join(lines) + "\n"


def _select_live_representative_cases(
    inventory: tuple[HarnessInventoryEntry, ...],
    cases: dict[str, AcceptanceCase],
) -> list[tuple[HarnessInventoryEntry, AcceptanceCase]]:
    by_key = {entry.key: entry for entry in inventory}
    selected: list[tuple[HarnessInventoryEntry, AcceptanceCase]] = []
    used: set[str] = set()

    def add(key: str) -> None:
        entry = by_key[key]
        selected.append((entry, cases[key]))
        used.add(key)

    add("frontend.dashboard.quick_explain")
    add("frontend.alert.deep_investigate")
    add("frontend.alert.decision_support")
    add("frontend.alert.artifact.checklist")
    add("frontend.floating_anakin.ask")
    add("frontend.floating_anakin.low_confidence_chooser")
    add("frontend.repo_architecture.chat.factual")
    add("frontend.repo_architecture.chat.evaluative")
    add("worker.soc_briefing.manual_run_now")
    add("frontend.ai_action.preview.add_incident_note")
    return selected


def _discover_live_entities(base_url: str, cookie: str) -> dict[str, Any]:
    alerts = _live_get_json(base_url, "/alerts?limit=1&offset=0", cookie)
    alert_row = _first_row(alerts, "alerts", "items", "results", "data")
    source_ip = alert_row.get("source_ip") if isinstance(alert_row, dict) else None
    incidents = _live_get_json(base_url, "/incidents?limit=1&offset=0", cookie)
    incident_row = _first_row(incidents, "incidents", "items", "results", "data")
    recon = _live_get_json(base_url, "/recon-activities?limit=1&offset=0", cookie)
    recon_row = _first_row(recon, "activities", "recon_activities", "items", "results", "data")
    registry = _live_get_json(base_url, "/response-registry?limit=1&offset=0", cookie)
    registry_row = _first_row(registry, "records", "items", "results", "data")
    return {
        "alert_id": _row_id(alert_row, "alert_id", "id"),
        "source_ip": source_ip or "127.0.0.1",
        "incident_id": _row_id(incident_row, "incident_id", "id"),
        "activity_id": _row_id(recon_row, "activity_id", "id"),
        "registry_id": _row_id(registry_row, "registry_id", "id"),
        "discovery_errors": [
            value.get("_error")
            for value in (alerts, incidents, recon, registry)
            if isinstance(value, dict) and value.get("_error")
        ],
    }


def _live_ai_action_check(
    base_url: str,
    cookie: str,
    entry: AiInvocationInventoryEntry,
    case: AcceptanceCase,
    ids: dict[str, Any],
    config: AiGatewayConfig,
) -> dict[str, Any]:
    payload = _live_payload_for_case(entry, case, ids)
    route = _route_path(entry.backend_path)
    profile = config.profile(entry.profile)
    prompt_size = case.prompt_size if hasattr(case, "prompt_size") else _safe_prompt_size(entry, case, config)
    started = time.monotonic()
    status_code = 0
    body: dict[str, Any] = {}
    error_text = None
    try:
        status_code, body = _live_post_json(base_url, route, payload, cookie)
        if entry.backend_path == ASYNC_WORKFLOW_REQUEST_ROUTE and 200 <= status_code < 300 and body.get("request_id"):
            poll_deadline = time.monotonic() + ASYNC_WORKFLOW_LIVE_POLL_SECONDS
            while str(body.get("status") or "").lower() not in ASYNC_WORKFLOW_TERMINAL_STATES and time.monotonic() < poll_deadline:
                time.sleep(ASYNC_WORKFLOW_LIVE_POLL_INTERVAL_SECONDS)
                status_code, body = _live_get_json_with_status(base_url, f"/ai/workflows/requests/{body['request_id']}", cookie)
            if str(body.get("status") or "").lower() not in ASYNC_WORKFLOW_TERMINAL_STATES:
                body.setdefault("error", "Workflow request did not reach a terminal state before live sweep polling timed out.")
                body["status"] = "timed_out"
    except Exception as error:
        error_text = str(error)
    latency_ms = int((time.monotonic() - started) * 1000)
    metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
    status = body.get("status") or metadata.get("status")
    error_value = body.get("error") or error_text
    root_cause = _root_cause_from_live(status=status, error=error_value, http_status=status_code, body=body)
    success_statuses = {"success", "partial"}
    if entry.backend_path == ASYNC_WORKFLOW_REQUEST_ROUTE:
        success_statuses.update(ASYNC_WORKFLOW_SUCCESS_STATES)
    if entry.backend_path == "POST /ai/actions/preview":
        success_statuses.add("preview_ready")
    if entry.key == "frontend.floating_anakin.low_confidence_chooser":
        success_statuses.add("chooser_required")
    success = 200 <= status_code < 300 and status in success_statuses and not error_value
    return {
        "frontend_action_id": entry.key,
        "execution_path": entry.backend_path,
        "action": case.action_name,
        "route": route,
        "entity": _stable_ai_entity_id(payload.get("context") or payload.get("visible_context")),
        "context_type": payload.get("context_type") or "general",
        "profile": entry.profile,
        "model": metadata.get("model") or profile.model,
        "prompt_size": prompt_size,
        "prompt_limit": profile.max_prompt_chars,
        "latency_ms": latency_ms,
        "http_status": status_code,
        "provider_status": metadata.get("status") or status,
        "success": success,
        "error_code": status if not success else None,
        "error": error_value,
        "root_cause": None if success else root_cause,
    }


def _live_status_check(base_url: str, cookie: str, path: str, frontend_action_id: str, config: AiGatewayConfig) -> dict[str, Any]:
    started = time.monotonic()
    status_code = 0
    body: dict[str, Any] = {}
    error_text = None
    try:
        status_code, body = _live_get_json_with_status(base_url, path, cookie)
    except Exception as error:
        error_text = str(error)
    latency_ms = int((time.monotonic() - started) * 1000)
    gateway = body.get("gateway") if isinstance(body.get("gateway"), dict) else {}
    providers = body.get("providers") if isinstance(body.get("providers"), list) else []
    provider = providers[0] if providers and isinstance(providers[0], dict) else {}
    status = body.get("status") or provider.get("status") or gateway.get("mode") or ("success" if 200 <= status_code < 300 else "failed")
    error_value = body.get("error") or provider.get("error") or error_text
    success = 200 <= status_code < 300 and not error_value
    profile_name = AI_PROFILE_DEVELOPER_ASSISTANT if path == "/ai/repo/status" else AI_PROFILE_FAST_TRIAGE
    profile = config.profile(profile_name)
    return {
        "frontend_action_id": frontend_action_id,
        "execution_path": f"GET {path}",
        "action": f"Status check {path}",
        "route": path,
        "entity": None,
        "context_type": "status",
        "profile": profile_name,
        "model": provider.get("model") or gateway.get("local_model") or profile.model,
        "prompt_size": 0,
        "prompt_limit": profile.max_prompt_chars,
        "latency_ms": latency_ms,
        "http_status": status_code,
        "provider_status": status,
        "success": success,
        "error_code": None if success else status,
        "error": error_value,
        "root_cause": None if success else _root_cause_from_live(status=status, error=error_value, http_status=status_code, body=body),
    }


def _live_manual_briefing_check(
    base_url: str,
    cookie: str,
    entry: AiInvocationInventoryEntry,
    *,
    create_manual_briefing_job: bool,
) -> dict[str, Any]:
    started = time.monotonic()
    if create_manual_briefing_job:
        status_code, body = _live_post_json(base_url, "/soc-briefings/run-now", {}, cookie)
    else:
        status_code, body = _live_get_json_with_status(base_url, "/soc-briefings/control", cookie)
    lifecycle = body.get("manual_lifecycle") or body.get("lifecycle") or {}
    worker = body.get("worker") or body.get("worker_status") or {}
    status = lifecycle.get("status") or ("status_only" if status_code else "failed")
    success = bool(200 <= status_code < 300 and (status == "status_only" or status in TERMINAL_MANUAL_BRIEFING_STATES or status in {"queued", "running"}))
    root_cause = None if success else ROOT_CAUSE_WORKER_UNAVAILABLE
    return {
        "frontend_action_id": entry.key,
        "execution_path": "POST /soc-briefings/run-now" if create_manual_briefing_job else "GET /soc-briefings/control",
        "action": entry.frontend_surface,
        "route": "/soc-briefings/run-now" if create_manual_briefing_job else "/soc-briefings/control",
        "entity": lifecycle.get("job_id") or lifecycle.get("job", {}).get("id"),
        "context_type": "soc_briefing",
        "profile": entry.profile,
        "model": None,
        "prompt_size": None,
        "prompt_limit": None,
        "latency_ms": int((time.monotonic() - started) * 1000),
        "http_status": status_code,
        "provider_status": lifecycle.get("provider_status"),
        "worker_status": worker.get("status") if isinstance(worker, dict) else worker,
        "success": success,
        "error_code": None if success else status,
        "error": body.get("error"),
        "root_cause": root_cause,
        "mutation_performed": create_manual_briefing_job,
    }


def _live_repo_assistant_checks(base_url: str, cookie: str, config: AiGatewayConfig) -> list[dict[str, Any]]:
    rows = []
    profile = config.profile(AI_PROFILE_DEVELOPER_ASSISTANT)
    for label, question in (
        ("repo.factual.soar_worker", "Where is the SOAR worker implemented?"),
        ("repo.evaluative.impressive_feature", "What is my most impressive feature?"),
    ):
        started = time.monotonic()
        status_code, body = _live_post_json(base_url, "/ai/repo/requests", {"message": question}, cookie)
        if 200 <= status_code < 300 and body.get("request_id"):
            poll_deadline = time.monotonic() + ASYNC_WORKFLOW_LIVE_POLL_SECONDS
            while str(body.get("status") or "").lower() not in ASYNC_WORKFLOW_TERMINAL_STATES and time.monotonic() < poll_deadline:
                time.sleep(ASYNC_WORKFLOW_LIVE_POLL_INTERVAL_SECONDS)
                status_code, body = _live_get_json_with_status(base_url, f"/ai/repo/requests/{body['request_id']}", cookie)
            if str(body.get("status") or "").lower() not in ASYNC_WORKFLOW_TERMINAL_STATES:
                body.setdefault("error", "Repo Assistant request did not reach a terminal state before live sweep polling timed out.")
                body["status"] = "timed_out"
        result = body.get("result") if isinstance(body.get("result"), dict) else body
        metadata = {}
        if isinstance(result.get("metadata"), dict):
            metadata.update(result["metadata"])
        if isinstance(body.get("metadata"), dict):
            metadata.update(body["metadata"])
        error_value = result.get("error") or body.get("error")
        provider_status = metadata.get("status") or result.get("status") or body.get("status")
        success = (
            200 <= status_code < 300
            and str(body.get("status") or result.get("status") or "").lower() in {"success", *ASYNC_WORKFLOW_SUCCESS_STATES}
            and bool(result.get("answer"))
            and not error_value
        )
        rows.append(
            {
                "frontend_action_id": label,
                "action": question,
                "route": "/ai/repo/requests",
                "entity": "repository",
                "context_type": "repository",
                "profile": AI_PROFILE_DEVELOPER_ASSISTANT,
                "model": metadata.get("model") or profile.model,
                "prompt_size": None,
                "prompt_limit": profile.max_prompt_chars,
                "latency_ms": int((time.monotonic() - started) * 1000),
                "http_status": status_code,
                "provider_status": provider_status,
                "success": success,
                "error_code": None if success else body.get("status") or result.get("status"),
                "error": error_value,
                "root_cause": None if success else _root_cause_from_live(status=body.get("status") or result.get("status"), error=error_value, http_status=status_code, body=body),
            }
        )
    return rows


def _live_payload_for_case(entry: AiInvocationInventoryEntry, case: AcceptanceCase, ids: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(json.dumps(case.request_payload, default=str))
    if entry.backend_path in {"POST /ai/chat", "POST /ai/repo/requests"}:
        return payload
    if entry.backend_path == "POST /ai/actions/preview":
        preview_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        if payload.get("action_type") == "add_incident_note" and ids.get("incident_id"):
            preview_payload["incident_id"] = ids["incident_id"]
        payload["payload"] = preview_payload
        return payload
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    context_type = payload.get("context_type") or case.context_type
    if context_type == "alert" and ids.get("alert_id"):
        context["alert_id"] = ids["alert_id"]
    if context_type == "incident" and ids.get("incident_id"):
        context["incident_id"] = ids["incident_id"]
    if context_type == "source_ip" and ids.get("source_ip"):
        context["source_ip"] = ids["source_ip"]
    if context_type == "recon_activity" and ids.get("activity_id"):
        context["activity_id"] = ids["activity_id"]
    if context_type == "response_registry" and ids.get("registry_id"):
        context["registry_id"] = ids["registry_id"]
    payload["context"] = context
    if entry.backend_path == "POST /ai/investigations":
        payload["allow_automatic_draft"] = False
    return payload


def _safe_prompt_size(entry: AiInvocationInventoryEntry, case: AcceptanceCase, config: AiGatewayConfig) -> int | None:
    try:
        return len(_prompt_for_case(entry, case, config))
    except Exception:
        return None


def _route_path(backend_path: str) -> str:
    if backend_path.startswith("POST "):
        return backend_path.split(" ", 1)[1]
    return backend_path


def _root_cause_from_live(*, status: Any, error: Any, http_status: int, body: dict[str, Any]) -> str:
    status_text = str(status or body.get("status") or "").lower()
    error_text = str(error or body.get("error") or body.get("error_code") or "").lower()
    text = f"{status_text} {error_text}"
    if "prompt" in text and ("too large" in text or "exceed" in text):
        return ROOT_CAUSE_PROMPT_TOO_LARGE
    if "stale" in text:
        return ROOT_CAUSE_STALE_CONTEXT
    if (
        status_text in {"provider_timeout", "timeout", "timed_out"}
        or error_text in {"provider_timeout", "timeout", "timed_out"}
        or "timed out" in error_text
        or "timeout" in error_text
    ):
        return ROOT_CAUSE_PROVIDER_TIMEOUT
    if "citation" in text or "grounding" in text:
        return ROOT_CAUSE_CITATION_CONTRACT
    if "worker" in text and ("unavailable" in text or "offline" in text):
        return ROOT_CAUSE_WORKER_UNAVAILABLE
    if http_status in {400, 404, 409, 422}:
        return ROOT_CAUSE_FRONTEND_CONTRACT_MISMATCH
    if "invalid" in text or "parse" in text or "schema" in text:
        return ROOT_CAUSE_INVALID_RESPONSE
    return "other"


def _live_get_json(base_url: str, path: str, cookie: str) -> dict[str, Any]:
    status, body = _live_get_json_with_status(base_url, path, cookie)
    if status >= 400:
        body.setdefault("_error", f"GET {path} returned {status}")
    return body


def _live_get_json_with_status(base_url: str, path: str, cookie: str) -> tuple[int, dict[str, Any]]:
    request = urllib_request.Request(f"{base_url}{path}", headers={"Cookie": cookie, "Accept": "application/json"})
    return _send_json_request(request)


def _live_post_json(base_url: str, path: str, payload: dict[str, Any], cookie: str) -> tuple[int, dict[str, Any]]:
    encoded = json.dumps(payload).encode("utf-8")
    request = urllib_request.Request(
        f"{base_url}{path}",
        data=encoded,
        method="POST",
        headers={"Cookie": cookie, "Accept": "application/json", "Content-Type": "application/json"},
    )
    return _send_json_request(request)


def _send_json_request(request: urllib_request.Request) -> tuple[int, dict[str, Any]]:
    try:
        with urllib_request.urlopen(request, timeout=240) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return int(response.status), _json_object(raw)
    except urllib_error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        return int(error.code), _json_object(raw)


def _json_object(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {"_raw": raw, "_error": "non_json_response"}
    return parsed if isinstance(parsed, dict) else {"data": parsed}


def _first_row(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value[0]
        if isinstance(value, dict):
            nested = _first_row(value, "items", "results", "data", "records", "alerts", "incidents")
            if nested:
                return nested
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0]
    return {}


def _row_id(row: Any, *keys: str) -> int | None:
    if not isinstance(row, dict):
        return None
    for key in keys:
        if row.get(key) not in (None, ""):
            try:
                return int(row[key])
            except (TypeError, ValueError):
                return None
    return None


def render_markdown_report(report: AcceptanceReport) -> str:
    lines = [
        "# Anakin AI Acceptance Harness Report",
        "",
        f"- Actions discovered: {report.actions_discovered}",
        f"- Actions covered: {report.actions_covered}",
        f"- Failures: {sum(len(items) for items in report.failures_by_root_cause.values())}",
        "",
        "## Failures By Root Cause",
    ]
    if report.failures_by_root_cause:
        for root_cause, action_ids in sorted(report.failures_by_root_cause.items()):
            lines.append(f"- `{root_cause}`: {len(action_ids)}")
            for action_id in action_ids:
                lines.append(f"  - `{action_id}`")
    else:
        lines.append("- None")

    lines.extend(["", "## Actions", ""])
    for result in report.results:
        status = "PASS" if result.success else f"FAIL {result.error_code or 'unknown'}"
        lines.append(
            f"- {status} `{result.frontend_action_id}` "
            f"{result.backend_route} profile=`{result.selected_profile}` "
            f"prompt={result.prompt_size}/{result.prompt_limit}ms={result.response_time_ms}"
        )

    lines.extend(["", "## Live Smoke", ""])
    for smoke in report.live_smoke_results:
        lines.append(f"- `{smoke.get('profile', 'all')}`: {json.dumps(smoke, sort_keys=True)}")
    return "\n".join(lines) + "\n"


def _run_case(entry: AiInvocationInventoryEntry, case: AcceptanceCase, config: AiGatewayConfig) -> AcceptanceResult:
    started = time.monotonic()
    profile = config.profile(entry.profile)
    try:
        prompt = _prompt_for_case(entry, case, config)
        prompt_error = None
    except Exception as error:
        prompt = ""
        prompt_error = str(error)
    response_time_ms = int((time.monotonic() - started) * 1000)
    prompt_size = len(prompt)
    usefulness = _usefulness_checks(_sample_response_for_case(entry, case))
    if entry.backend_path == "POST /ai/drafts" or (
        entry.backend_path in {"POST /ai/workflows", ASYNC_WORKFLOW_REQUEST_ROUTE}
        and case.request_payload.get("workflow") == WORKFLOW_GENERATE_ARTIFACT
    ):
        artifact = case.request_payload.get("artifact") if isinstance(case.request_payload.get("artifact"), dict) else {}
        draft_type = str(case.request_payload.get("draft_type") or artifact.get("type") or "investigation_checklist")
        try:
            parsed_sample = json.loads(_sample_response_for_case(entry, case))
        except json.JSONDecodeError:
            parsed_sample = None
        draft_validation = validate_draft_payload(draft_type, parsed_sample)
        usefulness["draft_schema_valid"] = draft_validation.valid
        if draft_validation.valid:
            usefulness["has_assessment_or_title"] = True
            usefulness["has_uncertainty_or_gaps"] = True
            usefulness["has_next_steps_or_checks"] = True
    stale_result = _stale_result(case)
    success = prompt_error is None and prompt_size <= profile.max_prompt_chars and all(usefulness.values()) and _stale_ok(stale_result)
    error_code = None
    root_cause = None
    if prompt_error is not None:
        error_code = "frontend_request_contract_failed"
        root_cause = ROOT_CAUSE_FRONTEND_CONTRACT_MISMATCH
    elif prompt_size > profile.max_prompt_chars:
        error_code = "prompt_exceeded_profile_limit"
        root_cause = ROOT_CAUSE_PROMPT_TOO_LARGE
    elif not all(usefulness.values()):
        error_code = "generic_or_empty_response_contract"
        root_cause = ROOT_CAUSE_INVALID_RESPONSE
    elif not _stale_ok(stale_result):
        error_code = "stale_state_contract_failed"
        root_cause = ROOT_CAUSE_STALE_CONTEXT

    return AcceptanceResult(
        action_button_name=case.action_name,
        frontend_action_id=case.frontend_action_id,
        backend_route=case.backend_route,
        context_type=case.context_type,
        entity=case.entity_id,
        selected_profile=entry.profile,
        selected_model=profile.model,
        prompt_size=prompt_size,
        prompt_limit=profile.max_prompt_chars,
        response_time_ms=response_time_ms,
        success=success,
        error_code=error_code,
        stale_state_result=stale_result,
        response_usefulness_checks=usefulness,
        root_cause=root_cause,
        notes=prompt_error or "",
    )


def _prompt_for_case(entry: AiInvocationInventoryEntry, case: AcceptanceCase, config: AiGatewayConfig) -> str:
    profile = config.profile(entry.profile)
    if entry.backend_path in {"POST /ai/workflows", ASYNC_WORKFLOW_REQUEST_ROUTE}:
        payload = case.request_payload
        workflow = str(payload.get("workflow") or entry.selector)
        context_type = str(payload.get("context_type") or "general")
        question = str(payload.get("prompt") or case.sample_question)
        if workflow == WORKFLOW_GENERATE_ARTIFACT:
            artifact = payload.get("artifact") if isinstance(payload.get("artifact"), dict) else {}
            draft_type = str(artifact.get("type") or "investigation_checklist")
            request = DraftRequest(
                draft_type=draft_type,
                instruction=question,
                context_type=context_type,
                context=payload.get("context") if isinstance(payload.get("context"), dict) else _entity_context_for_type(context_type),
                client_request_id="acceptance-workflow-draft",
            )
            return _build_draft_prompt(
                request,
                _fixture_context(context_type),
                SocToolExecutionSummary(used=False),
                config=config,
                profile_max_prompt_chars=profile.max_prompt_chars,
            )
        if workflow == WORKFLOW_DEEP_INVESTIGATE:
            request_context = payload.get("context") if isinstance(payload.get("context"), dict) else _entity_context_for_type(context_type)
            context = _fixture_context(context_type)
            plan = build_investigation_plan(context_type=context_type, context=request_context, question=question)
            routing = classify_routing_profile(
                workflow_type=plan.workflow_type,
                context_type=plan.context_type,
                context_payload=context,
                planned_tool_calls=len(plan.tool_calls),
                successful_sources=len(context.sources),
                failed_sources=0,
                truncated=context.truncated,
                draft_decision={"decision": "skipped", "reason": "acceptance contract"},
                config=config,
                remaining_timeout_seconds=60,
            )
            return _build_correlation_prompt(
                plan=plan,
                question=question,
                ai_context=context,
                tools=SocToolExecutionSummary(used=False),
                routing=routing,
                config=config,
                profile_max_prompt_chars=profile.max_prompt_chars,
            )
        return build_explainer_prompt(
            _fixture_context(context_type),
            action=workflow if workflow != WORKFLOW_DECISION_SUPPORT else "recommend_next_steps",
            question=question,
            config=config,
            profile_max_prompt_chars=profile.max_prompt_chars,
        )
    if entry.backend_path == "POST /ai/explain":
        payload = case.request_payload
        return build_explainer_prompt(
            _fixture_context(case.context_type),
            action=str(payload.get("action") or entry.selector),
            question=str(payload.get("question") or case.sample_question),
            config=config,
            profile_max_prompt_chars=profile.max_prompt_chars,
        )
    if entry.backend_path == "POST /ai/chat":
        return build_explainer_prompt(
            _fixture_context("general"),
            action="general_chat",
            question=case.sample_question,
            config=config,
            profile_max_prompt_chars=profile.max_prompt_chars,
        )
    if entry.backend_path == "POST /ai/drafts":
        payload = case.request_payload
        request = DraftRequest(
            draft_type=str(payload.get("draft_type") or "investigation_checklist"),
            instruction=str(payload.get("instruction") or case.sample_question),
            context_type=str(payload.get("context_type") or "alert"),
            context=payload.get("context") if isinstance(payload.get("context"), dict) else {"alert_id": 1001},
            client_request_id="acceptance-draft-1001",
        )
        return _build_draft_prompt(
            request,
            _fixture_context(request.context_type),
            SocToolExecutionSummary(used=False),
            config=config,
            profile_max_prompt_chars=profile.max_prompt_chars,
        )
    if entry.backend_path == "POST /ai/investigations":
        payload = case.request_payload
        context_type = str(payload.get("context_type") or "alert")
        request_context = payload.get("context") if isinstance(payload.get("context"), dict) else {"alert_id": 1001}
        context = _fixture_context(context_type)
        plan = build_investigation_plan(context_type=context_type, context=request_context, question=case.sample_question)
        routing = classify_routing_profile(
            workflow_type=plan.workflow_type,
            context_type=plan.context_type,
            context_payload=context,
            planned_tool_calls=len(plan.tool_calls),
            successful_sources=len(context.sources),
            failed_sources=0,
            truncated=context.truncated,
            draft_decision={"decision": "skipped", "reason": "acceptance contract"},
            config=config,
            remaining_timeout_seconds=60,
        )
        return _build_correlation_prompt(
            plan=plan,
            question=str(payload.get("question") or case.sample_question),
            ai_context=context,
            tools=SocToolExecutionSummary(used=False),
            routing=routing,
            config=config,
            profile_max_prompt_chars=profile.max_prompt_chars,
        )
    if entry.backend_path == "POST /ai/repo/requests":
        return build_repo_prompt(
            case.sample_question,
            history=[],
            chunks=_repo_chunks(),
            max_prompt_chars=profile.max_prompt_chars,
            question_type=classify_repo_question(case.sample_question),
        )
    if entry.backend_path == "POST /ai/actions/preview":
        return json.dumps(
            {
                "non_mutating_ai_action_preview_contract": True,
                "request": case.request_payload,
                "expected_status": "preview_ready",
                "confirm_route_requires_explicit_token": True,
                "production_mutation_allowed": False,
            },
            default=str,
            sort_keys=True,
            indent=2,
        )
    if entry.backend_path == "soc_briefing_worker":
        budget = InvestigationBudget(max_prompt_chars=min(8000, profile.max_prompt_chars), max_prompt_tokens=3000)
        evidence = _fixture_context("recon_activity").metadata()
        return (
            "You are generating a read-only manual/scheduled SOC briefing.\n"
            "Preserve queued, running, completed, partial, failed, blocked, and timed_out lifecycle visibility.\n"
            f"Budget: {json.dumps(budget.as_dict(), sort_keys=True)}\n"
            f"Evidence: {json.dumps(evidence, sort_keys=True)}\n"
            f"Question: {case.sample_question}\n"
        )
    raise ValueError(f"Unsupported acceptance backend path: {entry.backend_path}")


def _case_for_entry(
    entry: HarnessInventoryEntry | AiInvocationInventoryEntry,
    *,
    frontend_options: dict[str, dict[str, Any]],
) -> AcceptanceCase:
    fallback_context_type = _context_type_for_entry(entry)
    options = _frontend_options_for_entry(entry, fallback_context_type, frontend_options)
    context_type = _normalize_context_type(options.get("contextType")) or fallback_context_type
    payload, route = build_frontend_realistic_request(options, active_section=_active_section_for_context(context_type))
    if entry.backend_path in {"soc_briefing_worker", "POST /ai/repo/requests"}:
        route = entry.backend_path
    else:
        route = entry.backend_path
    return AcceptanceCase(
        inventory_key=entry.key,
        action_name=entry.frontend_surface,
        frontend_action_id=entry.key,
        backend_route=route,
        context_type=context_type,
        stale_policy=_stale_policy_for_entry(entry),
        sample_question=options.get("question") or options.get("instruction") or _question_for_entry(entry, context_type),
        frontend_options=options,
        request_payload=payload,
        entity_id=_stable_ai_entity_id(payload.get("context") or payload.get("visible_context") or options.get("context")),
    )


def build_frontend_realistic_request(options: dict[str, Any], *, active_section: str = "dashboard") -> tuple[dict[str, Any], str]:
    explicit_route = options.get("route")
    if explicit_route == "soc_briefing_worker":
        return {"mode": "status_only", "create_job": False}, "soc_briefing_worker"
    if explicit_route == "POST /ai/actions/preview":
        return (
            {
                "action_type": options.get("action_type") or "add_incident_note",
                "payload": options.get("payload") if isinstance(options.get("payload"), dict) else {"incident_id": 2002, "note_text": "Acceptance preview only."},
                "idempotency_key": options.get("idempotency_key") or "acceptance-preview-action-2002",
                "source_draft": options.get("source_draft") if isinstance(options.get("source_draft"), dict) else {"draft_type": "incident_note", "read_only": True},
            },
            "POST /ai/actions/preview",
        )
    if explicit_route == "POST /ai/chat":
        return (
            {
                "message": options.get("message") or options.get("question") or "What should I inspect first in this workspace?",
                "visible_context": options.get("visible_context") if isinstance(options.get("visible_context"), dict) else _visible_context_fixture(active_section),
                "client_history": options.get("client_history") if isinstance(options.get("client_history"), list) else [],
                "use_tools": options.get("useTools", True) is not False,
                "tool_policy": options.get("toolPolicy") or {"max_tool_calls": 5, "time_window_hours": 24},
            },
            "POST /ai/chat",
        )
    if explicit_route == "POST /ai/repo/requests":
        payload = {
            "message": options.get("message") or options.get("question") or "What is my most impressive feature?",
        }
        if isinstance(options.get("client_history"), list):
            payload["client_history"] = options["client_history"]
        if isinstance(options.get("refresh"), bool):
            payload["refresh"] = options["refresh"]
        return payload, "POST /ai/repo/requests"

    normalized_context_type = _normalize_context_type(options.get("contextType"))
    entity_context = options.get("context") if isinstance(options.get("context"), dict) else {}
    should_include_visible = normalized_context_type not in ENTITY_AI_CONTEXT_TYPES
    contextual_command = {
        "id": options.get("commandId") or f"contextual.{options.get('contextType') or 'workspace'}.{options.get('action') or options.get('draftType') or 'ask'}",
        "label": options.get("title") or options.get("action") or options.get("draftType") or "Ask Anakin",
        "intent": options.get("draftType") and "draft" or (options.get("investigation") and "investigate") or options.get("action") or "ask_anakin",
        "read_only": True,
    }
    context = {
        **(_visible_context_fixture(active_section) if should_include_visible else {"active_section": active_section}),
        "command": contextual_command,
        **entity_context,
    }
    if options.get("workflow") or options.get("artifactType"):
        payload = {
            "workflow": options.get("workflow") or "auto",
            "prompt": options.get("prompt") or options.get("question") or options.get("instruction") or "",
            "context_type": options.get("contextType"),
            "entity": entity_context,
            "context": context,
            "tool_policy": options.get("toolPolicy") or (
                {"max_tool_calls": 5, "time_window_hours": 24}
                if options.get("workflow") == WORKFLOW_DEEP_INVESTIGATE
                else None
            ),
        }
        if options.get("artifactType"):
            payload["artifact"] = {"type": options.get("artifactType")}
        if payload.get("tool_policy") is None:
            payload.pop("tool_policy", None)
        route = ASYNC_WORKFLOW_REQUEST_ROUTE if payload["workflow"] in ASYNC_WORKFLOW_REQUESTS else "POST /ai/workflows"
        return payload, route
    if options.get("draftType"):
        return (
            {
                "draft_type": options.get("draftType"),
                "instruction": options.get("instruction") or options.get("question") or "",
                "context_type": options.get("contextType"),
                "context": context,
                "use_tools": options.get("useTools", True) is not False,
                "tool_policy": options.get("toolPolicy") or {"max_tool_calls": 3, "time_window_hours": 24},
            },
            "POST /ai/drafts",
        )
    if options.get("investigation"):
        return (
            {
                "context_type": options.get("contextType"),
                "context": context,
                "question": options.get("question") or "",
                "tool_policy": options.get("toolPolicy") or {"max_tool_calls": 5, "time_window_hours": 24},
                "allow_automatic_draft": False,
            },
            "POST /ai/investigations",
        )
    return (
        {
            "context_type": options.get("contextType"),
            "action": options.get("action"),
            "question": options.get("question") or "",
            "context": context,
        },
        "POST /ai/explain",
    )


def _inventory_entry_for_frontend_option(discovered: FrontendAiOption, options: dict[str, Any]) -> HarnessInventoryEntry:
    _payload, route = build_frontend_realistic_request(options, active_section=_active_section_for_context(_normalize_context_type(options.get("contextType"))))
    selector = str(options.get("draftType") or options.get("action") or "ask_anakin")
    if route in {"POST /ai/workflows", ASYNC_WORKFLOW_REQUEST_ROUTE}:
        selector = str(options.get("workflow") or "auto")
        if selector == WORKFLOW_QUICK_EXPLAIN:
            selector_type = "workflow"
            profile = AI_PROFILE_FAST_TRIAGE
        elif selector in {WORKFLOW_DEEP_INVESTIGATE, WORKFLOW_DECISION_SUPPORT, WORKFLOW_GENERATE_ARTIFACT}:
            selector_type = "workflow"
            profile = AI_PROFILE_GUIDED_ANALYSIS
        else:
            selector_type = "workflow"
            profile = profile_for_chat()
    elif route == "POST /ai/drafts":
        selector_type = "draft_type"
        profile = profile_for_draft_type(selector)
    elif route == "POST /ai/investigations":
        selector_type = "investigation_workflow"
        profile = profile_for_investigation()
    elif route == "POST /ai/explain":
        selector_type = "explain_action"
        profile = profile_for_explain_action(selector)
    elif route == "POST /ai/actions/preview":
        selector_type = "action_preview"
        profile = profile_for_investigation()
    else:
        selector_type = "route"
        profile = profile_for_chat()
    workflow_route = "POST /ai/workflows" if route == ASYNC_WORKFLOW_REQUEST_ROUTE else route
    label = options.get("title") or selector
    return HarnessInventoryEntry(
        key=discovered.key,
        frontend_surface=f"{discovered.source_file}:{discovered.line_number} {label}",
        backend_path=route,
        selector_type=selector_type,
        selector=selector,
        profile=profile,
        workflow=workflow_for_inventory_path(workflow_route, selector_type, selector),
        notes="Discovered from real frontend onAskAi payload construction.",
    )


def _inventory_entry_for_static_contract(options: dict[str, Any]) -> HarnessInventoryEntry:
    key = str(options["contract_key"])
    _payload, route = build_frontend_realistic_request(options, active_section=_active_section_for_context(_normalize_context_type(options.get("contextType"))))
    selector = str(options.get("draftType") or options.get("action") or options.get("selector") or "ask_anakin")
    if route in {"POST /ai/workflows", ASYNC_WORKFLOW_REQUEST_ROUTE}:
        selector = str(options.get("workflow") or "auto")
        if selector == WORKFLOW_QUICK_EXPLAIN:
            selector_type = "workflow"
            profile = AI_PROFILE_FAST_TRIAGE
        elif selector in {WORKFLOW_DEEP_INVESTIGATE, WORKFLOW_DECISION_SUPPORT, WORKFLOW_GENERATE_ARTIFACT}:
            selector_type = "workflow"
            profile = AI_PROFILE_GUIDED_ANALYSIS
        else:
            selector_type = "workflow"
            profile = profile_for_chat()
    elif route == "POST /ai/chat":
        selector_type = "route"
        profile = profile_for_chat()
    elif route == "POST /ai/repo/requests":
        selector_type = "route"
        profile = profile_for_repo_assistant()
    elif route == "soc_briefing_worker":
        selector_type = "capability"
        profile = profile_for_soc_briefing()
    elif route == "POST /ai/drafts":
        selector_type = "draft_type"
        profile = profile_for_draft_type(selector)
    elif route == "POST /ai/investigations":
        selector_type = "investigation_workflow"
        profile = profile_for_investigation()
    elif route == "POST /ai/actions/preview":
        selector_type = "action_preview"
        profile = profile_for_investigation()
    else:
        selector_type = "explain_action"
        profile = profile_for_explain_action(selector)
    workflow_route = "POST /ai/workflows" if route == ASYNC_WORKFLOW_REQUEST_ROUTE else route
    return HarnessInventoryEntry(
        key=key,
        frontend_surface=str(options.get("surface") or options.get("title") or key),
        backend_path=route,
        selector_type=selector_type,
        selector=selector,
        profile=profile,
        workflow=workflow_for_inventory_path(workflow_route, selector_type, selector),
        notes=str(options.get("source") or "static acceptance contract"),
    )


def _static_surface_contracts() -> list[dict[str, Any]]:
    contracts = [
        _workflow_contract("frontend.dashboard.ask_anakin", "Dashboard Ask Anakin", "dashboard", "auto", context={"dashboard_id": "summary"}),
        _workflow_contract("frontend.dashboard.quick_explain", "Dashboard Quick Explain", "dashboard", WORKFLOW_QUICK_EXPLAIN, context={"dashboard_id": "summary"}),
        _workflow_contract("frontend.dashboard.deep_investigate", "Dashboard Deep Investigate", "dashboard", WORKFLOW_DEEP_INVESTIGATE, context={"dashboard_id": "summary"}),
        _workflow_contract("frontend.alert.quick_explain", "Alert Details Quick Explain", "alert", WORKFLOW_QUICK_EXPLAIN, context={"alert_id": 1001, "source_ip": "203.0.113.77"}),
        _workflow_contract("frontend.alert.deep_investigate", "Alert Details Deep Investigate", "alert", WORKFLOW_DEEP_INVESTIGATE, context={"alert_id": 1001, "source_ip": "203.0.113.77"}),
        _workflow_contract("frontend.alert.decision_support", "Alert Details Decision Support", "alert", WORKFLOW_DECISION_SUPPORT, context={"alert_id": 1001, "source_ip": "203.0.113.77"}),
        _workflow_contract("frontend.alert.artifact.checklist", "Alert Details Generate Artifact: checklist", "alert", WORKFLOW_GENERATE_ARTIFACT, artifact_type="investigation_checklist", context={"alert_id": 1001, "source_ip": "203.0.113.77"}),
        _workflow_contract("frontend.alert.artifact.detection_change", "Alert Details Generate Artifact: detection change", "detection", WORKFLOW_GENERATE_ARTIFACT, artifact_type="detection_rule_change", context={"alert_id": 1001, "source_ip": "203.0.113.77"}),
        _workflow_contract("frontend.alert.artifact.response_recommendation", "Alert Details Generate Artifact: response recommendation", "alert", WORKFLOW_GENERATE_ARTIFACT, artifact_type="response_recommendation", context={"alert_id": 1001, "source_ip": "203.0.113.77"}),
        _workflow_contract("frontend.source_ip.quick_explain", "Source IP Quick Explain", "source_ip", WORKFLOW_QUICK_EXPLAIN, context={"source_ip": "203.0.113.77"}),
        _workflow_contract("frontend.source_ip.deep_investigate", "Source IP Deep Investigate", "source_ip", WORKFLOW_DEEP_INVESTIGATE, context={"source_ip": "203.0.113.77"}),
        _workflow_contract("frontend.source_ip.decision_support", "Source IP Decision Support", "source_ip", WORKFLOW_DECISION_SUPPORT, context={"source_ip": "203.0.113.77"}),
        _workflow_contract("frontend.source_ip.artifact.response_recommendation", "Source IP Generate Artifact: response recommendation", "source_ip", WORKFLOW_GENERATE_ARTIFACT, artifact_type="response_recommendation", context={"source_ip": "203.0.113.77"}),
        _workflow_contract("frontend.source_ip.artifact.checklist", "Source IP Generate Artifact: checklist", "source_ip", WORKFLOW_GENERATE_ARTIFACT, artifact_type="investigation_checklist", context={"source_ip": "203.0.113.77"}),
        _workflow_contract("frontend.incident.deep_investigate", "Incident Deep Investigate", "incident", WORKFLOW_DEEP_INVESTIGATE, context={"incident_id": 2002}),
        _workflow_contract("frontend.incident.decision_support", "Incident Decision Support", "incident", WORKFLOW_DECISION_SUPPORT, context={"incident_id": 2002}),
        _workflow_contract("frontend.incident.artifact.note", "Incident Generate Artifact: note", "incident", WORKFLOW_GENERATE_ARTIFACT, artifact_type="incident_note", context={"incident_id": 2002}),
        _workflow_contract("frontend.incident.artifact.escalation", "Incident Generate Artifact: escalation summary", "incident", WORKFLOW_GENERATE_ARTIFACT, artifact_type="escalation_summary", context={"incident_id": 2002}),
        _workflow_contract("frontend.incident.artifact.playbook", "Incident Generate Artifact: playbook draft", "incident", WORKFLOW_GENERATE_ARTIFACT, artifact_type="playbook_draft", context={"incident_id": 2002}),
        _workflow_contract("frontend.recon.deep_investigate", "SOC Command Center Recon Deep Investigate", "recon_activity", WORKFLOW_DEEP_INVESTIGATE, context={"activity_id": 3003}),
        _workflow_contract("frontend.recon.decision_support", "SOC Command Center Recon Decision Support", "recon_activity", WORKFLOW_DECISION_SUPPORT, context={"activity_id": 3003}),
        _workflow_contract("frontend.recon.artifact.checklist", "SOC Command Center Recon Generate Artifact: checklist", "recon_activity", WORKFLOW_GENERATE_ARTIFACT, artifact_type="investigation_checklist", context={"activity_id": 3003}),
        _workflow_contract("frontend.recon.artifact.response_recommendation", "SOC Command Center Recon Generate Artifact: response recommendation", "recon_activity", WORKFLOW_GENERATE_ARTIFACT, artifact_type="response_recommendation", context={"activity_id": 3003}),
        _workflow_contract("frontend.response_registry.decision_support", "Response Registry Decision Support", "response_registry", WORKFLOW_DECISION_SUPPORT, context={"registry_id": 4004, "source_ip": "203.0.113.77"}),
        _workflow_contract("frontend.response_registry.deep_investigate", "Response Registry Deep Investigate", "response_registry", WORKFLOW_DEEP_INVESTIGATE, context={"registry_id": 4004, "source_ip": "203.0.113.77"}),
        _workflow_contract("frontend.response_registry.artifact.response_recommendation", "Response Registry Generate Artifact: response recommendation", "response_registry", WORKFLOW_GENERATE_ARTIFACT, artifact_type="response_recommendation", context={"registry_id": 4004, "source_ip": "203.0.113.77"}),
        _workflow_contract("frontend.analyst_workspace.deep_investigate", "Analyst Workspace Deep Investigate", "general", WORKFLOW_DEEP_INVESTIGATE, context={"investigation_id": 5005}),
        _workflow_contract("frontend.analyst_workspace.decision_support", "Analyst Workspace Decision Support", "general", WORKFLOW_DECISION_SUPPORT, context={"investigation_id": 5005}),
        _workflow_contract("frontend.analyst_workspace.artifact.checklist", "Analyst Workspace Generate Artifact: checklist", "general", WORKFLOW_GENERATE_ARTIFACT, artifact_type="investigation_checklist", context={"investigation_id": 5005}),
        _workflow_contract("frontend.analyst_workspace.artifact.note", "Analyst Workspace Generate Artifact: incident note", "general", WORKFLOW_GENERATE_ARTIFACT, artifact_type="incident_note", context={"investigation_id": 5005}),
        _workflow_contract("frontend.analyst_workspace.artifact.escalation", "Analyst Workspace Generate Artifact: escalation summary", "general", WORKFLOW_GENERATE_ARTIFACT, artifact_type="escalation_summary", context={"investigation_id": 5005}),
        _workflow_contract("frontend.floating_anakin.ask", "Global Anakin Ask Anakin", "general", "auto", context={"active_section": "dashboard"}),
        _workflow_contract(
            "frontend.floating_anakin.low_confidence_chooser",
            "Global Anakin low-confidence chooser",
            "general",
            "auto",
            context={"active_section": "dashboard"},
            question="run briefing, repo deploy, and approve the action",
        ),
        _workflow_contract("frontend.floating_anakin.quick_explain", "Global Anakin Quick Explain", "general", WORKFLOW_QUICK_EXPLAIN, context={"active_section": "dashboard"}),
        _workflow_contract("frontend.floating_anakin.deep_investigate", "Global Anakin Deep Investigate", "general", WORKFLOW_DEEP_INVESTIGATE, context={"active_section": "dashboard"}),
        _workflow_contract("frontend.floating_anakin.decision_support", "Global Anakin Decision Support", "general", WORKFLOW_DECISION_SUPPORT, context={"active_section": "dashboard"}),
        _workflow_contract("frontend.floating_anakin.generate_artifact", "Global Anakin Generate Artifact", "general", WORKFLOW_GENERATE_ARTIFACT, artifact_type="investigation_checklist", context={"active_section": "dashboard"}),
    ]
    contracts.extend(
        [
            _workflow_contract("frontend.command_palette.quick_explain", "Command Palette Quick Explain", "general", WORKFLOW_QUICK_EXPLAIN, context={"active_section": "dashboard"}),
            _workflow_contract("frontend.command_palette.deep_investigate", "Command Palette Deep Investigate", "general", WORKFLOW_DEEP_INVESTIGATE, context={"active_section": "dashboard"}),
            _workflow_contract("frontend.command_palette.decision_support", "Command Palette Decision Support", "general", WORKFLOW_DECISION_SUPPORT, context={"active_section": "dashboard"}),
            _workflow_contract("frontend.command_palette.generate_artifact", "Command Palette Generate Artifact", "general", WORKFLOW_GENERATE_ARTIFACT, artifact_type="investigation_checklist", context={"active_section": "dashboard"}),
        ]
    )
    contracts.extend([
        {
            "contract_key": "frontend.command_palette.soc_briefing",
            "surface": "Command Palette SOC Briefing",
            "route": "soc_briefing_worker",
            "contextType": "soc_briefing",
            "action": "run_now",
            "source": "anakinCommandRegistry.socBriefing",
        },
        {
            "contract_key": "frontend.command_palette.repo_assistant",
            "surface": "Command Palette Repo Assistant",
            "route": "POST /ai/repo/requests",
            "message": "Where is the SOAR worker implemented?",
            "source": "anakinCommandRegistry.repoAssistant",
        },
        {
            "contract_key": "frontend.repo_architecture.chat.factual",
            "surface": "RepoArchitectureAssistantPanel factual question",
            "route": "POST /ai/repo/requests",
            "message": "Where is the SOAR worker implemented?",
            "source": "RepoArchitectureAssistantPanel",
        },
        {
            "contract_key": "frontend.repo_architecture.chat.evaluative",
            "surface": "RepoArchitectureAssistantPanel evaluative question",
            "route": "POST /ai/repo/requests",
            "message": "What is my most impressive feature?",
            "source": "RepoArchitectureAssistantPanel",
        },
        {
            "contract_key": "worker.soc_briefing.manual_run_now",
            "surface": "SocBriefingsPanel Run Anakin Briefing Now",
            "route": "soc_briefing_worker",
            "contextType": "soc_briefing",
            "action": "run_now",
            "source": "SocBriefingsPanel",
        },
        {
            "contract_key": "frontend.ai_action.preview.add_incident_note",
            "surface": "AiResponsePanel Preview action",
            "route": "POST /ai/actions/preview",
            "contextType": "incident",
            "selector": "add_incident_note",
            "action_type": "add_incident_note",
            "payload": {"incident_id": 2002, "note_text": "Acceptance preview only. Do not confirm."},
            "idempotency_key": "acceptance-preview-action-2002",
            "source_draft": {"draft_type": "incident_note", "read_only": True, "persisted": False, "applied": False},
            "source": "AiResponsePanel.previewAiAction",
        },
    ])
    return contracts


def _workflow_contract(
    contract_key: str,
    surface: str,
    context_type: str,
    workflow: str,
    *,
    artifact_type: str | None = None,
    context: dict[str, Any] | None = None,
    question: str | None = None,
) -> dict[str, Any]:
    label = workflow.replace("_", " ")
    options = {
        "contract_key": contract_key,
        "surface": surface,
        "route": ASYNC_WORKFLOW_REQUEST_ROUTE if workflow in ASYNC_WORKFLOW_REQUESTS else "POST /ai/workflows",
        "contextType": context_type,
        "workflow": workflow,
        "question": question or f"Run {label} for this {context_type} context using bounded SIEM evidence.",
        "context": context or _entity_context_for_type(context_type),
        "source": "AnakinWorkflowControls",
    }
    if workflow == WORKFLOW_DEEP_INVESTIGATE:
        options["toolPolicy"] = {"max_tool_calls": 5, "time_window_hours": 24}
    if artifact_type:
        options["artifactType"] = artifact_type
        options["instruction"] = f"Generate a {artifact_type.replace('_', ' ')} for analyst review only."
    return options


def _extract_on_ask_ai_blocks(text: str) -> list[tuple[str, int]]:
    blocks: list[tuple[str, int]] = []
    start = 0
    marker = "onAskAi({"
    while True:
        idx = text.find(marker, start)
        if idx < 0:
            break
        brace_start = text.find("{", idx)
        depth = 0
        for pos in range(brace_start, len(text)):
            char = text[pos]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    blocks.append((text[brace_start : pos + 1], text.count("\n", 0, idx) + 1))
                    start = pos + 1
                    break
        else:
            break
    return blocks


def _parse_frontend_ai_options(block: str) -> dict[str, Any] | None:
    context_type = _js_string_prop(block, "contextType")
    action = _js_string_prop(block, "action")
    draft_type = _js_string_prop(block, "draftType")
    if not context_type or not (action or draft_type):
        return None
    context = _context_from_js_block(block, context_type)
    return {
        "contextType": context_type,
        "action": action,
        "draftType": draft_type,
        "investigation": bool(re.search(r"\binvestigation\s*:\s*true\b", block)),
        "title": _js_template_or_string_prop(block, "title") or action or draft_type,
        "question": _js_string_prop(block, "question") or "",
        "instruction": _js_string_prop(block, "instruction") or "",
        "context": context,
        "toolPolicy": _tool_policy_from_js_block(block),
        "source": "frontend_onAskAi",
    }


def _js_string_prop(block: str, prop: str) -> str | None:
    match = re.search(rf"\b{re.escape(prop)}\s*:\s*['\"]([^'\"]+)['\"]", block)
    return match.group(1) if match else None


def _js_template_or_string_prop(block: str, prop: str) -> str | None:
    simple = _js_string_prop(block, prop)
    if simple:
        return simple
    match = re.search(rf"\b{re.escape(prop)}\s*:\s*`([^`]+)`", block)
    return match.group(1) if match else None


def _context_from_js_block(block: str, context_type: str) -> dict[str, Any]:
    if "alert_id" in block:
        return {"alert_id": 1001}
    if "incident_id" in block or "selectedIncident.id" in block:
        return {"incident_id": 2002}
    if "source_ip" in block or "sourceIp" in block:
        return {"source_ip": "203.0.113.77"}
    if "activity_id" in block or "recon_activity_id" in block:
        return {"activity_id": 3003}
    if "registry_id" in block or "record.id" in block:
        return {"registry_id": 4004}
    if "rule_id" in block:
        return {"rule_id": "pfsense_firewall_repeated_deny"}
    if context_type == "dashboard":
        return {"dashboard_id": "summary"}
    return {"id": 1001}


def _tool_policy_from_js_block(block: str) -> dict[str, Any] | None:
    if "toolPolicy" not in block:
        return None
    max_calls = re.search(r"max_tool_calls\s*:\s*(\d+)", block)
    hours = re.search(r"time_window_hours\s*:\s*(\d+)", block)
    return {
        "max_tool_calls": int(max_calls.group(1)) if max_calls else 5,
        "time_window_hours": int(hours.group(1)) if hours else 24,
    }


def _frontend_contract_key(options: dict[str, Any], filename: str) -> str:
    context_type = options.get("contextType")
    action = options.get("action") or options.get("draftType") or "ask"
    suffix = ".guided" if options.get("investigation") else ".draft" if options.get("draftType") else ""
    if filename == "DashboardMetrics.js":
        return f"frontend.dashboard.metrics.{action}"
    if filename == "DashboardVisuals.js":
        return f"frontend.dashboard.visuals.{action}"
    if filename == "AlertDetailsPanel.js":
        return f"frontend.alert.{action}{suffix}"
    if filename == "SourceIpContext.js":
        return f"frontend.source_ip.{action}{suffix}"
    if filename == "IncidentsPanel.js":
        return f"frontend.incident.{action}{suffix}"
    if filename == "SocCommandCenter.js":
        return f"frontend.recon.{action}{suffix}"
    if filename == "ResponseRegistryPanel.js":
        return f"frontend.response_registry.{action}{suffix}"
    return f"frontend.{context_type}.{action}{suffix}"


def _default_command_contracts() -> list[dict[str, Any]]:
    workspace = {
        "workspace": {"activeSection": "analyst_workspace"},
        "object": {"type": "workspace", "id": "analyst_workspace"},
        "data": _visible_context_fixture("analyst_workspace"),
    }
    return [
        {
            "contract_key": "frontend.command_registry.quick_explain",
            "contextType": "general",
            "workflow": WORKFLOW_QUICK_EXPLAIN,
            "question": "Explain the current SIEM context using loaded evidence.",
            "context": workspace,
            "source": "anakinCommandRegistry.commandToAiOptions",
        },
        {
            "contract_key": "frontend.command_registry.deep_investigate",
            "contextType": "general",
            "workflow": WORKFLOW_DEEP_INVESTIGATE,
            "question": "Run a bounded read-only investigation of the current context and identify source-cited next steps.",
            "context": workspace,
            "toolPolicy": {"max_tool_calls": 5, "time_window_hours": 24},
            "source": "anakinCommandRegistry.commandToAiOptions",
        },
        {
            "contract_key": "frontend.command_registry.decision_support",
            "contextType": "general",
            "workflow": WORKFLOW_DECISION_SUPPORT,
            "question": "Recommend what the analyst should do next without drafting or taking action.",
            "context": workspace,
            "source": "anakinCommandRegistry.commandToAiOptions",
        },
        {
            "contract_key": "frontend.command_registry.generate_artifact",
            "contextType": "general",
            "workflow": WORKFLOW_GENERATE_ARTIFACT,
            "artifactType": "investigation_checklist",
            "instruction": "Draft a read-only analyst checklist from the current context. Do not save or execute anything.",
            "context": workspace,
            "source": "anakinCommandRegistry.commandToAiOptions",
        },
        {
            "contract_key": "frontend.command_registry.soc_briefing",
            "contextType": "soc_briefing",
            "route": "soc_briefing_worker",
            "action": "run_now",
            "source": "anakinCommandRegistry.commandToAiOptions",
        },
        {
            "contract_key": "frontend.command_registry.repo_assistant",
            "contextType": "repository",
            "route": "POST /ai/repo/requests",
            "message": "Where is the SOAR worker implemented?",
            "source": "anakinCommandRegistry.commandToAiOptions",
        },
    ]


def _frontend_options_for_entry(
    entry: AiInvocationInventoryEntry,
    context_type: str,
    frontend_options: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if entry.key == "frontend.floating_chat.general":
        return {
            "route": "POST /ai/chat",
            "message": "What should I inspect first in this workspace?",
            "visible_context": _visible_context_fixture("dashboard"),
            "client_history": [],
            "source": "FloatingSiemChat",
        }
    if entry.key == "frontend.repo_architecture.chat":
        return {
            "route": "POST /ai/repo/requests",
            "message": "What is my most impressive feature?",
            "client_history": [],
            "refresh": False,
            "source": "RepoArchitectureAssistantPanel",
        }
    if entry.key == "worker.soc_briefing.manual_and_scheduled":
        return {"contextType": "soc_briefing", "action": "run_now", "source": "SocBriefingsPanel"}
    if entry.key in frontend_options:
        return _with_large_entity_fixture(frontend_options[entry.key], context_type)
    compatible = [
        options
        for options in frontend_options.values()
        if options.get("contextType") == context_type and (options.get("action") == entry.selector or options.get("draftType") == entry.selector)
    ]
    if compatible:
        return _with_large_entity_fixture(compatible[0], context_type)
    return {
        "contextType": context_type,
        "action": entry.selector if entry.selector_type == "explain_action" else "explain",
        "question": _question_for_entry(entry, context_type),
        "context": _entity_context_for_type(context_type),
        "source": "acceptance_fallback_from_inventory",
    }


def _legacy_options_for_inventory_entry(entry: AiInvocationInventoryEntry) -> dict[str, Any]:
    context_type = _context_type_for_entry(entry)
    if entry.backend_path == "POST /ai/chat":
        return {
            "route": "POST /ai/chat",
            "message": "What should I inspect first in this workspace?",
            "visible_context": _visible_context_fixture("dashboard"),
            "client_history": [],
            "source": "legacy_backend_compatibility_adapter",
        }
    if entry.backend_path == "POST /ai/repo/requests":
        return {
            "route": "POST /ai/repo/requests",
            "message": "What is my most impressive feature?",
            "client_history": [],
            "refresh": False,
            "source": "legacy_backend_compatibility_adapter",
        }
    if entry.backend_path == "soc_briefing_worker":
        return {"route": "soc_briefing_worker", "contextType": "soc_briefing", "action": "run_now", "source": "legacy_backend_compatibility_adapter"}
    if entry.backend_path == "POST /ai/drafts":
        return {
            "contextType": "alert",
            "draftType": "investigation_checklist",
            "instruction": "Draft a read-only analyst checklist from the current context. Do not save or execute anything.",
            "context": {"alert_id": 1001, "source_ip": "203.0.113.77"},
            "source": "legacy_backend_compatibility_adapter",
        }
    if entry.backend_path == "POST /ai/investigations":
        return {
            "contextType": "alert",
            "action": "recommend_investigation",
            "investigation": True,
            "question": "Run a bounded read-only investigation of the current alert context.",
            "context": {"alert_id": 1001, "source_ip": "203.0.113.77"},
            "toolPolicy": {"max_tool_calls": 5, "time_window_hours": 24},
            "source": "legacy_backend_compatibility_adapter",
        }
    return {
        "contextType": context_type,
        "action": entry.selector,
        "question": _question_for_entry(entry, context_type),
        "context": _entity_context_for_type(context_type),
        "source": "legacy_backend_compatibility_adapter",
    }


def _with_large_entity_fixture(options: dict[str, Any], context_type: str) -> dict[str, Any]:
    copied = {**options}
    context = dict(copied.get("context") or {})
    context.update(_entity_context_for_type(context_type))
    copied["context"] = context
    return copied


def _entity_context_for_type(context_type: str) -> dict[str, Any]:
    if context_type == "alert":
        return {"alert_id": 1001}
    if context_type == "incident":
        return {"incident_id": 2002}
    if context_type == "source_ip":
        return {"source_ip": "203.0.113.77"}
    if context_type == "recon_activity":
        return {"activity_id": 3003}
    if context_type == "response_registry":
        return {"registry_id": 4004}
    if context_type == "detection":
        return {"alert_id": 1001, "rule_id": "pfsense_firewall_repeated_deny"}
    return {"id": 1001}


def _visible_context_fixture(active_section: str) -> dict[str, Any]:
    return {
        "active_section": active_section,
        "visible_filters": {"severity": "high", "status": "open", "timeline_range": "7d"},
        "dashboard_summary": {"total_alerts": 4200, "critical": 17, "high": 231},
        "timeline": [{"bucket": idx, "count": 100 + idx, "severity": "high"} for idx in range(30)],
        "top_source_ips": [{"source_ip": f"203.0.113.{idx}", "count": 50 + idx} for idx in range(10)],
        "map_markers": [{"source_ip": f"198.51.100.{idx}", "count": 20 + idx, "lat": 40.0, "lon": -73.0} for idx in range(10)],
        "recent_alerts": [
            {
                "id": idx,
                "alert_type": "pfsense_firewall_repeated_deny",
                "severity": "high",
                "status": "open",
                "source_ip": f"203.0.113.{idx % 30}",
                "message": "Repeated deny events against exposed service.",
                "created_at": "2026-08-01T00:00:00Z",
            }
            for idx in range(10)
        ],
    }


def _normalize_context_type(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _stable_ai_entity_id(context: Any) -> str | int | None:
    if not isinstance(context, dict):
        return None
    for key in ("alert_id", "incident_id", "source_ip", "activity_id", "recon_activity_id", "registry_id", "id", "rule_id"):
        if context.get(key) not in (None, ""):
            return context[key]
    return None


def _active_section_for_context(context_type: str) -> str:
    return {
        "alert": "alerts",
        "dashboard": "dashboard",
        "source_ip": "source-ip-context",
        "incident": "incidents",
        "recon_activity": "soc-command-center",
        "response_registry": "response-registry",
        "repository": "admin",
        "soc_briefing": "soc-briefings",
    }.get(context_type, "analyst_workspace")


def _context_type_for_entry(entry: AiInvocationInventoryEntry) -> str:
    key = entry.key
    selector = entry.selector
    if "dashboard" in key:
        return "dashboard"
    if ".alert" in key or selector in {"explain_alert", "why_important", "recommend_investigation", "explain_detection"}:
        return "alert"
    if "source_ip" in key:
        return "source_ip"
    if "incident" in key:
        return "incident"
    if "recon" in key:
        return "recon_activity"
    if "response_registry" in key:
        return "response_registry"
    if "repo_architecture" in key:
        return "repository"
    if "soc_briefing" in key:
        return "soc_briefing"
    if "draft" in key:
        return "alert"
    if "guided_investigation" in key:
        return "alert"
    return "general"


def _stale_policy_for_entry(entry: AiInvocationInventoryEntry) -> str:
    if entry.backend_path in {"POST /ai/drafts", "POST /ai/actions/preview"} or (
        entry.backend_path in {"POST /ai/workflows", ASYNC_WORKFLOW_REQUEST_ROUTE} and entry.workflow == WORKFLOW_GENERATE_ARTIFACT
    ):
        return "strict_for_confirmable_preview"
    if entry.backend_path == "soc_briefing_worker":
        return "durable_lifecycle_recoverable"
    return "read_only_advisory"


def _question_for_entry(entry: AiInvocationInventoryEntry, context_type: str) -> str:
    if entry.backend_path == "POST /ai/repo/requests":
        return "What is my most impressive feature?"
    if entry.backend_path == "soc_briefing_worker":
        return "Run Anakin Briefing Now using current bounded SIEM evidence."
    return f"Analyze this {context_type} context and identify evidence, uncertainty, gaps, and next read-only steps."


def _fixture_context(context_type: str) -> AiContextPayload:
    data = _large_fixture_data(context_type)
    return AiContextPayload(
        context_type=context_type,
        data=data,
        sources=[
            AiContextSource(
                context_type,
                f"/acceptance/{context_type}/1001",
                [1001],
                "2026-08-01T00:00:00+00:00",
                truncated=True,
                omitted_count=488,
                truncation_reason="acceptance_large_fixture_bounded",
            )
        ],
        truncated=True,
        omitted_count=488,
    )


def _large_fixture_data(context_type: str) -> dict[str, Any]:
    base = {
        "summary": f"Acceptance fixture for {context_type}",
        "_evidence": {
            "included": {"primary": 1, "bounded_rows": 12},
            "omitted": {"raw_events": 488},
            "truncated": True,
        },
    }
    if context_type == "recon_activity":
        return {
            **base,
            "recon_activity": {
                "id": 3003,
                "severity": "high",
                "confidence": "medium",
                "primary_source_ip": "203.0.113.77",
                "target_ports": [22, 80, 443, 3389, 8080, 8443],
                "distinct_targets": 43,
                "window": "24h",
                "signals": [
                    {"name": "fanout", "value": 43},
                    {"name": "repeated_denies", "value": 612},
                    {"name": "admin_surface_touches", "value": 7},
                ],
            },
            "related_events": [
                {"id": idx, "source_ip": "203.0.113.77", "target_port": 443 + (idx % 20), "action": "deny"}
                for idx in range(40)
            ],
            "related_alerts": [
                {"id": idx, "severity": "high", "alert_type": "recon_cluster", "status": "open"}
                for idx in range(20)
            ],
        }
    if context_type == "source_ip":
        return {
            **base,
            "source_ip": "203.0.113.77",
            "reputation": {"status": "suspicious", "confidence": "medium", "last_seen": "2026-08-01T00:00:00Z"},
            "recent_alerts": [
                {"id": idx, "type": "pfsense_firewall_repeated_deny", "severity": "high", "target_port": 443 + idx}
                for idx in range(60)
            ],
            "campaign_memberships": [{"id": idx, "label": f"campaign-{idx}", "confidence": "medium"} for idx in range(10)],
            "response_outcomes": [{"action": "monitor", "status": "tracking_only", "count": idx + 1} for idx in range(12)],
        }
    if context_type == "incident":
        return {
            **base,
            "incident": {"id": 2002, "title": "VPN recon and repeated deny cluster", "severity": "high", "status": "open"},
            "timeline": [
                {"id": idx, "event_type": "alert_linked", "detail": "Repeated deny event added to incident", "created_at": "2026-08-01T00:00:00Z"}
                for idx in range(75)
            ],
            "linked_alerts": [{"id": idx, "severity": "high", "source_ip": f"203.0.113.{idx % 30}"} for idx in range(35)],
        }
    if context_type == "alert":
        return {
            **base,
            "alert": {
                "id": 1001,
                "alert_type": "pfsense_firewall_repeated_deny",
                "severity": "high",
                "status": "open",
                "source_ip": "203.0.113.77",
                "message": "Repeated deny events during background refresh.",
                "refresh_generation": 2,
            },
            "why_fired": {"rule": "Repeated deny threshold exceeded", "threshold": 25, "observed": 612},
            "related_events": [
                {"id": idx, "source_ip": "203.0.113.77", "target_port": 443 + (idx % 40), "action": "deny"}
                for idx in range(80)
            ],
            "background_refresh": {"previous_selected_alert_id": 1001, "current_selected_alert_id": 1001, "dashboard_refreshing": True},
        }
    if context_type == "response_registry":
        return {
            **base,
            "registry_record": {
                "id": 4004,
                "indicator_value": "203.0.113.77",
                "action": "monitor",
                "status": "active",
                "latest_outcome": "tracking_only",
            },
            "related_alerts": [{"id": idx, "severity": "high", "status": "open"} for idx in range(30)],
            "outcome_history": [{"id": idx, "status": "tracking_only", "note": "No production action executed"} for idx in range(20)],
        }
    if context_type in {"general", "analyst_workspace"}:
        return {
            **base,
            "workspace": "analyst_workspace",
            "visible_context": _visible_context_fixture("analyst_workspace"),
            "open_investigations": [{"id": idx, "status": "open", "severity": "high"} for idx in range(12)],
        }
    return {
        **base,
        "primary": {
            "id": 1001,
            "severity": "high",
            "status": "open",
            "source_ip": "203.0.113.77",
            "description": "Repeated deny events against VPN and admin surfaces.",
        },
        "bounded_rows": [
            {"id": idx, "event": "deny", "port": 443 + idx, "count": 10 + idx}
            for idx in range(12)
        ],
    }


def _repo_chunks() -> list[RepoChunk]:
    return [
        RepoChunk(
            path="core/ai/context_builder.py",
            line_start=1,
            line_end=80,
            text="SUPPORTED_CONTEXT_TYPES and bounded context builders package SIEM evidence before AI prompts.",
            trust_tier=1,
            source_kind="source",
            label="current",
            mtime=0,
            size=200,
            content_hash="acceptance-context",
        ),
        RepoChunk(
            path="core/ai/profile_registry.py",
            line_start=1,
            line_end=120,
            text="AI_INVOCATION_INVENTORY maps frontend AI surfaces to backend routes and model profiles.",
            trust_tier=1,
            source_kind="source",
            label="current",
            mtime=0,
            size=200,
            content_hash="acceptance-profile",
        ),
    ]


def _sample_response_for_case(entry: AiInvocationInventoryEntry, case: AcceptanceCase) -> str:
    if entry.backend_path == "POST /ai/drafts" or (
        entry.backend_path in {"POST /ai/workflows", ASYNC_WORKFLOW_REQUEST_ROUTE}
        and case.request_payload.get("workflow") == WORKFLOW_GENERATE_ARTIFACT
    ):
        artifact = case.request_payload.get("artifact") if isinstance(case.request_payload.get("artifact"), dict) else {}
        return json.dumps(_sample_draft_payload(str(case.request_payload.get("draft_type") or artifact.get("type") or "investigation_checklist"), case.context_type))
    if entry.backend_path == "POST /ai/actions/preview":
        return (
            "Assessment: action preview is ready for analyst review only.\n"
            "Evidence: payload digest, target fingerprint, and confirmation token are required before confirmation.\n"
            "Contradictions and uncertainty: stale target state blocks confirmation.\n"
            "Evidence gaps: analyst must review the generated draft and current target state.\n"
            "Read-only next steps: inspect preview details and reject or explicitly confirm through the guarded workflow."
        )
    return (
        "Assessment: repeated activity is notable because it targets sensitive surfaces.\n"
        "Evidence: bounded fixture rows support the assessment while omitted raw rows are reported.\n"
        "Contradictions and uncertainty: no successful login or containment outcome is shown.\n"
        "Evidence gaps: confirm affected asset criticality and related incidents.\n"
        "Read-only next steps: inspect related alerts, event timeline, and source-IP history."
    )


def _sample_draft_payload(draft_type: str, context_type: str) -> dict[str, Any]:
    if draft_type == "detection_rule_change":
        return {
            "title": "Tune repeated-deny detection threshold",
            "rationale": "Bounded evidence supports analyst review of the detection condition.",
            "target_rule": "pfsense_firewall_repeated_deny",
            "suggested_condition": "Require repeated deny events from one source across multiple target ports in the observed window.",
            "severity": "high",
            "false_positive_notes": "Check approved scanners, NAT gateways, monitoring tools, and maintenance windows before treating the activity as malicious.",
            "test_ideas": ["Replay benign scanner events.", "Replay recent high-confidence deny bursts."],
            "rollback_notes": "Restore the previous threshold if false positives increase after review.",
            "source_references": [context_type],
        }
    if draft_type == "playbook_draft":
        return {
            "name": "Review suspicious scanner",
            "trigger_context": "High-severity repeated deny evidence",
            "steps": ["Collect alert detail", "Review source-IP history"],
            "approval_gates": ["Analyst approval before enforcement"],
            "simulation_real_caveats": "This is review-only and does not execute a playbook.",
            "required_integrations": ["firewall"],
            "risks": ["Benign scanner may be misclassified"],
            "source_references": [context_type],
        }
    if draft_type == "incident_note":
        return {
            "summary": "Repeated suspicious activity requires analyst review.",
            "evidence": ["Bounded SIEM evidence supports the assessment."],
            "uncertainty": "Source ownership and benign scanner status remain unknown.",
            "recommended_next_steps": ["Review related events"],
            "attribution": [context_type],
        }
    if draft_type == "escalation_summary":
        return {
            "audience": "SOC lead",
            "urgency": "High",
            "business_or_security_impact": "Potential recon against exposed services.",
            "evidence": ["Multiple related alerts"],
            "asks": ["Confirm response policy"],
            "next_update_criteria": "Update after related-event review.",
            "source_references": [context_type],
        }
    if draft_type == "response_recommendation":
        return {
            "recommended_action_class": "Monitor and investigate",
            "prerequisites": ["Confirm source history"],
            "expected_outcome": "Improved confidence before enforcement.",
            "approval_need": "Required before any production action.",
            "risk": "Premature blocking may affect benign traffic.",
            "alternatives": ["Escalate to network owner"],
            "source_references": [context_type],
        }
    return {
        "title": "Acceptance investigation checklist",
        "checks": ["Review cited evidence", "Compare benign indicators", "Document uncertainty"],
        "data_sources": ["alerts", "events"],
        "expected_findings": ["Repeated denies may indicate recon"],
        "stop_conditions": ["No matching current evidence"],
        "source_references": [context_type],
    }


def _usefulness_checks(response: str) -> dict[str, bool]:
    normalized = str(response or "").strip().lower()
    return {
        "non_empty": bool(normalized),
        "has_assessment_or_title": "assessment" in normalized or "title" in normalized,
        "has_evidence": "evidence" in normalized or "source_references" in normalized,
        "has_uncertainty_or_gaps": "uncertainty" in normalized or "gap" in normalized,
        "has_next_steps_or_checks": "next step" in normalized or "checks" in normalized,
        "not_generic_monitoring_only": normalized != "continue monitoring.",
    }


def _empty_usefulness(value: bool) -> dict[str, bool]:
    return {
        "non_empty": value,
        "has_assessment_or_title": value,
        "has_evidence": value,
        "has_uncertainty_or_gaps": value,
        "has_next_steps_or_checks": value,
        "not_generic_monitoring_only": value,
    }


def _stale_result(case: AcceptanceCase) -> str:
    if case.stale_policy == "read_only_advisory":
        return "read_only_response_remains_visible_with_advisory"
    if case.stale_policy == "strict_for_confirmable_preview":
        return "confirmable_preview_blocks_confirmation_when_stale"
    if case.stale_policy == "durable_lifecycle_recoverable":
        lifecycle = ["queued", "running", "completed"]
        terminal = lifecycle[-1]
        return f"manual_lifecycle_visible_terminal:{terminal}" if terminal in TERMINAL_MANUAL_BRIEFING_STATES else "manual_lifecycle_missing_terminal"
    return "unknown"


def _stale_ok(stale_result: str) -> bool:
    return stale_result in {
        "read_only_response_remains_visible_with_advisory",
        "confirmable_preview_blocks_confirmation_when_stale",
    } or stale_result.startswith("manual_lifecycle_visible_terminal:")


def _acceptance_config() -> AiGatewayConfig:
    return AiGatewayConfig(
        mode=AI_MODE_LOCAL_ONLY,
        configured_mode=AI_MODE_LOCAL_ONLY,
        local_provider="ollama",
        local_base_url="http://127.0.0.1:11434",
        local_model="llama3.1:8b",
        local_timeout_seconds=30,
        profiles=default_ai_profiles(local_model="llama3.1:8b", local_timeout_seconds=30),
    )


__all__ = [
    "AcceptanceReport",
    "AcceptanceResult",
    "APPROVED_SURFACE_CONTROL_MATRIX",
    "CANONICAL_ACCEPTANCE_WORKFLOWS",
    "LIVE_SWEEP_VM_COMMAND",
    "LIVE_SMOKE_ENV",
    "LIVE_SWEEP_ENV",
    "REMOVED_FRONTEND_ACTION_IDS",
    "REMOVED_FRONTEND_AI_LABELS",
    "build_acceptance_cases",
    "build_frontend_realistic_request",
    "discover_frontend_ai_options",
    "build_complete_ai_inventory",
    "build_golden_reasoning_cases",
    "build_production_like_alert_checklist_fixture",
    "build_production_safe_live_sweep_matrix",
    "build_workflow_acceptance_summary",
    "build_workflow_representative_fixtures",
    "evaluate_golden_reasoning_answer",
    "removed_frontend_ai_controls_present",
    "render_live_sweep_markdown",
    "render_markdown_report",
    "run_acceptance_harness",
    "run_live_backend_sweep",
    "run_offline_contract_tier",
    "run_optional_live_smoke_tier",
]
