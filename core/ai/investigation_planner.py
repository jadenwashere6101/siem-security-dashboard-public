from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import json
from typing import Any

from core.ai.config import AiGatewayConfig
from core.ai.context_builder import AiContextPayload
from core.ai.draft_schemas import DEFAULT_DRAFT_LABELS
from core.ai.investigation_models import (
    ALLOWED_STEP_TYPES,
    MAX_TOOL_CALLS_PER_PASS,
    MAX_TOTAL_TOOL_CALLS,
    MAX_WORKFLOW_STEPS,
    ROUTING_ADVANCED,
    ROUTING_SIMPLE,
    ROUTING_STANDARD,
    STEP_BUILD_CONTEXT,
    STEP_CORRELATE_EVIDENCE,
    STEP_EXECUTE_READ_TOOL,
    STEP_FINALIZE_SUMMARY,
    STEP_GENERATE_TRANSIENT_DRAFT,
    STEP_PLAN_READ_TOOLS,
    STEP_SUGGEST_RESPONSE_PLAN,
    STEP_VALIDATE_EVIDENCE,
    WORKFLOW_ALERT,
    WORKFLOW_DASHBOARD_ANOMALY,
    WORKFLOW_INCIDENT,
    WORKFLOW_RECON_CLUSTER,
    WORKFLOW_RESPONSE_REGISTRY,
    WORKFLOW_SOURCE_IP,
    AiRoutingProfile,
)
from core.ai.models import estimate_tokens
from core.ai.soc_tool_executor import build_deterministic_tool_plan
from core.ai.soc_tools import (
    TOOL_STATUS_FORBIDDEN,
    TOOL_STATUS_SUCCESS,
    TOOL_STATUS_TRUNCATED,
    SocToolExecutionSummary,
    SocToolResult,
    redact_sensitive_values,
    validate_tool_args,
    validate_tool_name,
)


class InvestigationPlannerError(ValueError):
    def __init__(self, message: str, *, error_code: str = "invalid_investigation"):
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True)
class InvestigationPlan:
    workflow_type: str
    context_type: str
    steps: tuple[str, ...]
    tool_calls: tuple[dict[str, Any], ...]
    draft_policy: dict[str, Any]
    bounds: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "workflow_type": self.workflow_type,
            "context_type": self.context_type,
            "steps": list(self.steps),
            "tool_calls": [dict(call) for call in self.tool_calls],
            "draft_policy": dict(self.draft_policy),
            "bounds": dict(self.bounds),
        }


WORKFLOW_BY_CONTEXT = {
    "alert": WORKFLOW_ALERT,
    "incident": WORKFLOW_INCIDENT,
    "source_ip": WORKFLOW_SOURCE_IP,
    "recon_activity": WORKFLOW_RECON_CLUSTER,
    "response_registry": WORKFLOW_RESPONSE_REGISTRY,
    "dashboard": WORKFLOW_DASHBOARD_ANOMALY,
    "general": WORKFLOW_DASHBOARD_ANOMALY,
    "detection": WORKFLOW_ALERT,
}

WORKFLOW_STEPS = {
    WORKFLOW_ALERT: (
        STEP_BUILD_CONTEXT,
        STEP_PLAN_READ_TOOLS,
        STEP_EXECUTE_READ_TOOL,
        STEP_VALIDATE_EVIDENCE,
        STEP_CORRELATE_EVIDENCE,
        STEP_SUGGEST_RESPONSE_PLAN,
        STEP_GENERATE_TRANSIENT_DRAFT,
        STEP_FINALIZE_SUMMARY,
    ),
    WORKFLOW_INCIDENT: (
        STEP_BUILD_CONTEXT,
        STEP_PLAN_READ_TOOLS,
        STEP_EXECUTE_READ_TOOL,
        STEP_VALIDATE_EVIDENCE,
        STEP_CORRELATE_EVIDENCE,
        STEP_SUGGEST_RESPONSE_PLAN,
        STEP_GENERATE_TRANSIENT_DRAFT,
        STEP_FINALIZE_SUMMARY,
    ),
    WORKFLOW_SOURCE_IP: (
        STEP_BUILD_CONTEXT,
        STEP_PLAN_READ_TOOLS,
        STEP_EXECUTE_READ_TOOL,
        STEP_VALIDATE_EVIDENCE,
        STEP_CORRELATE_EVIDENCE,
        STEP_SUGGEST_RESPONSE_PLAN,
        STEP_GENERATE_TRANSIENT_DRAFT,
        STEP_FINALIZE_SUMMARY,
    ),
    WORKFLOW_RECON_CLUSTER: (
        STEP_BUILD_CONTEXT,
        STEP_PLAN_READ_TOOLS,
        STEP_EXECUTE_READ_TOOL,
        STEP_VALIDATE_EVIDENCE,
        STEP_CORRELATE_EVIDENCE,
        STEP_SUGGEST_RESPONSE_PLAN,
        STEP_GENERATE_TRANSIENT_DRAFT,
        STEP_FINALIZE_SUMMARY,
    ),
    WORKFLOW_RESPONSE_REGISTRY: (
        STEP_BUILD_CONTEXT,
        STEP_PLAN_READ_TOOLS,
        STEP_EXECUTE_READ_TOOL,
        STEP_VALIDATE_EVIDENCE,
        STEP_CORRELATE_EVIDENCE,
        STEP_SUGGEST_RESPONSE_PLAN,
        STEP_FINALIZE_SUMMARY,
    ),
    WORKFLOW_DASHBOARD_ANOMALY: (
        STEP_BUILD_CONTEXT,
        STEP_PLAN_READ_TOOLS,
        STEP_EXECUTE_READ_TOOL,
        STEP_VALIDATE_EVIDENCE,
        STEP_CORRELATE_EVIDENCE,
        STEP_SUGGEST_RESPONSE_PLAN,
        STEP_FINALIZE_SUMMARY,
    ),
}

AUTOMATIC_DRAFT_TYPES = frozenset(
    {
        "incident_note",
        "investigation_checklist",
        "escalation_summary",
        "response_recommendation",
    }
)


def normalize_context_type(value: Any) -> str:
    context_type = str(value or "").strip().lower()
    if not context_type:
        raise InvestigationPlannerError("context_type is required")
    if context_type not in WORKFLOW_BY_CONTEXT:
        raise InvestigationPlannerError(f"unsupported context_type: {context_type}")
    return context_type


def workflow_for_context(context_type: str, requested_workflow: Any = None) -> str:
    requested = str(requested_workflow or "").strip().lower()
    expected = WORKFLOW_BY_CONTEXT[context_type]
    if not requested:
        return expected
    if requested not in WORKFLOW_STEPS:
        raise InvestigationPlannerError(f"unsupported workflow_type: {requested}")
    if requested != expected and context_type not in {"general", "detection"}:
        raise InvestigationPlannerError("workflow_type does not match context_type")
    return requested


def validate_workflow_steps(steps: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    if len(steps) > MAX_WORKFLOW_STEPS:
        raise InvestigationPlannerError("workflow exceeds maximum step depth", error_code="workflow_depth_exceeded")
    normalized = tuple(str(step or "").strip().lower() for step in steps)
    for step in normalized:
        if step not in ALLOWED_STEP_TYPES:
            raise InvestigationPlannerError(f"unsupported workflow step: {step}", error_code="unsupported_step")
    if len(normalized) != len(set(normalized)):
        raise InvestigationPlannerError("recursive or duplicate workflow steps are not allowed", error_code="loop_prevented")
    return normalized


def build_investigation_plan(
    *,
    context_type: str,
    context: dict[str, Any],
    question: str,
    workflow_type: str | None = None,
    tool_policy: dict[str, Any] | None = None,
    allow_automatic_draft: bool = True,
) -> InvestigationPlan:
    normalized_type = normalize_context_type(context_type)
    workflow = workflow_for_context(normalized_type, workflow_type)
    steps = validate_workflow_steps(WORKFLOW_STEPS[workflow])
    tool_calls = _planned_tool_calls(
        question=question,
        context_type=normalized_type,
        context=context,
        workflow_type=workflow,
        tool_policy=tool_policy,
    )
    draft_policy = {
        "enabled": bool(allow_automatic_draft and STEP_GENERATE_TRANSIENT_DRAFT in steps),
        "allowed_types": sorted(AUTOMATIC_DRAFT_TYPES),
        "max_automatic_drafts": 1,
        "decision": "pending",
        "reason": None,
        "selected_type": None,
        "labels": dict(DEFAULT_DRAFT_LABELS),
    }
    return InvestigationPlan(
        workflow_type=workflow,
        context_type=normalized_type,
        steps=steps,
        tool_calls=tuple(tool_calls),
        draft_policy=draft_policy,
        bounds={
            "max_steps": MAX_WORKFLOW_STEPS,
            "max_total_tool_calls": MAX_TOTAL_TOOL_CALLS,
            "max_tool_calls_per_pass": MAX_TOOL_CALLS_PER_PASS,
            "max_planning_passes": 1,
            "max_generation_calls": 2,
            "max_automatic_drafts": 1,
        },
    )


def _planned_tool_calls(
    *,
    question: str,
    context_type: str,
    context: dict[str, Any],
    workflow_type: str,
    tool_policy: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    deterministic = build_deterministic_tool_plan(
        question=question,
        context_type=context_type,
        context=context,
        tool_policy=tool_policy,
    ).calls
    calls = list(deterministic)
    if workflow_type == WORKFLOW_INCIDENT and context.get("incident_id"):
        calls.insert(0, {"tool_name": "get_incident_timeline", "arguments": {"incident_id": context["incident_id"]}})
        calls.append({"tool_name": "list_playbook_executions", "arguments": {}})
    if workflow_type == WORKFLOW_ALERT and context.get("source_ip"):
        calls.append({"tool_name": "get_source_ip_context", "arguments": {"source_ip": context["source_ip"]}})
        calls.append({"tool_name": "list_playbook_executions", "arguments": {}})
    if workflow_type == WORKFLOW_RESPONSE_REGISTRY and context.get("source_ip"):
        calls.append({"tool_name": "get_source_ip_context", "arguments": {"source_ip": context["source_ip"]}})
    if workflow_type == WORKFLOW_DASHBOARD_ANOMALY:
        calls.append({"tool_name": "search_alerts", "arguments": {}})

    valid_calls: list[dict[str, Any]] = []
    for call in _dedupe_calls(calls):
        if len(valid_calls) >= MAX_TOOL_CALLS_PER_PASS:
            break
        tool_name = validate_tool_name(call.get("tool_name") or call.get("name"))
        arguments = validate_tool_args(tool_name, call.get("arguments") or call.get("args") or {})
        valid_calls.append({"tool_name": tool_name, "arguments": arguments})
    return valid_calls


def validate_tool_evidence(
    summary: SocToolExecutionSummary,
    *,
    context_snapshot: dict[str, Any],
    prompt_budget_chars: int,
) -> tuple[SocToolExecutionSummary, dict[str, Any]]:
    accepted: list[SocToolResult] = []
    rejected: list[dict[str, Any]] = []
    for result in summary.calls:
        reason = _tool_result_rejection_reason(result, context_snapshot)
        if reason:
            rejected.append({"tool_name": result.tool_name, "status": result.status, "reason": reason})
            continue
        accepted.append(result)

    sources = [source for result in accepted for source in result.sources]
    validated = SocToolExecutionSummary(
        used=summary.used,
        calls=accepted,
        sources=sources,
        truncated=summary.truncated or any(result.truncated for result in accepted),
        omitted_count=summary.omitted_count + sum(result.omitted_count for result in accepted),
        error_code=summary.error_code if not accepted else None,
    )
    compacted = redact_sensitive_values(validated.as_dict())
    serialized = json.dumps(compacted, default=str, sort_keys=True, separators=(",", ":"))
    if len(serialized) > prompt_budget_chars:
        validated = SocToolExecutionSummary(
            used=validated.used,
            calls=validated.calls,
            sources=validated.sources,
            truncated=True,
            omitted_count=validated.omitted_count,
            error_code=validated.error_code,
        )
    metadata = {
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "rejected": rejected,
        "source_count": len(sources),
        "truncated": validated.truncated,
        "prompt_budget_chars": prompt_budget_chars,
    }
    return validated, metadata


def _tool_result_rejection_reason(result: SocToolResult, context_snapshot: dict[str, Any]) -> str | None:
    if result.read_only is not True:
        return "tool result was not read-only"
    if result.status == TOOL_STATUS_FORBIDDEN:
        return "tool forbidden for actor role"
    if result.status not in {TOOL_STATUS_SUCCESS, TOOL_STATUS_TRUNCATED}:
        return "tool did not return usable evidence"
    if result.data not in (None, {}, []) and not result.sources:
        return "tool evidence was missing source attribution"
    expected_source_ip = context_snapshot.get("source_ip")
    if expected_source_ip and not _result_matches_source_ip(result, str(expected_source_ip)):
        return "tool evidence did not match source IP context"
    expected_ids = {
        "alert_id": context_snapshot.get("alert_id"),
        "incident_id": context_snapshot.get("incident_id"),
        "registry_id": context_snapshot.get("registry_id"),
        "activity_id": context_snapshot.get("activity_id"),
    }
    for field_name, expected in expected_ids.items():
        if expected and result.tool_name in _tools_requiring_id_match(field_name):
            if not _result_sources_include(result, expected):
                return f"tool evidence did not match {field_name}"
    return None


def select_automatic_draft(
    *,
    plan: InvestigationPlan,
    ai_context: AiContextPayload,
    validated_tools: SocToolExecutionSummary,
    gateway_status: str | None,
) -> dict[str, Any]:
    if not plan.draft_policy["enabled"]:
        return {**plan.draft_policy, "decision": "skipped", "reason": "automatic draft not enabled"}
    if gateway_status and gateway_status != "success":
        return {**plan.draft_policy, "decision": "skipped", "reason": f"gateway status {gateway_status}"}
    if ai_context.insufficient_context:
        return {**plan.draft_policy, "decision": "skipped", "reason": "insufficient context"}
    severity = _extract_severity(ai_context.data)
    if severity not in {"high", "critical"} and plan.workflow_type in {WORKFLOW_ALERT, WORKFLOW_INCIDENT}:
        return {**plan.draft_policy, "decision": "skipped", "reason": "severity not high or critical"}
    has_evidence = bool(ai_context.sources or validated_tools.sources)
    if not has_evidence:
        return {**plan.draft_policy, "decision": "skipped", "reason": "no validated evidence"}

    selected = None
    if plan.workflow_type == WORKFLOW_INCIDENT:
        selected = "incident_note"
    elif plan.workflow_type == WORKFLOW_ALERT:
        selected = "investigation_checklist"
        if severity == "critical" and _has_incident_reference(ai_context.data, validated_tools):
            selected = "escalation_summary"
    elif plan.workflow_type in {WORKFLOW_SOURCE_IP, WORKFLOW_RECON_CLUSTER}:
        selected = "investigation_checklist"
    elif plan.workflow_type == WORKFLOW_RESPONSE_REGISTRY and validated_tools.sources:
        selected = "response_recommendation"

    if selected not in AUTOMATIC_DRAFT_TYPES:
        return {**plan.draft_policy, "decision": "skipped", "reason": "workflow not eligible"}
    return {**plan.draft_policy, "decision": "generate", "reason": "eligible", "selected_type": selected}


def classify_routing_profile(
    *,
    workflow_type: str,
    context_type: str,
    context_payload: AiContextPayload | None,
    planned_tool_calls: int,
    successful_sources: int,
    failed_sources: int,
    truncated: bool,
    draft_decision: dict[str, Any],
    config: AiGatewayConfig,
    remaining_timeout_seconds: float,
) -> AiRoutingProfile:
    context_data = context_payload.data if context_payload is not None else {}
    prompt_tokens = estimate_tokens(json.dumps(redact_sensitive_values(context_data), default=str))
    tool_tokens = max(0, planned_tool_calls * 250)
    structured = draft_decision.get("decision") == "generate"
    if structured or planned_tool_calls >= 4 or failed_sources > 0 or truncated:
        profile = ROUTING_ADVANCED
    elif planned_tool_calls > 1 or prompt_tokens > 1200 or successful_sources > 3:
        profile = ROUTING_STANDARD
    else:
        profile = ROUTING_SIMPLE
    return AiRoutingProfile(
        profile=profile,
        inputs={
            "workflow_type": workflow_type,
            "context_type": context_type,
            "estimated_prompt_tokens": prompt_tokens,
            "estimated_tool_evidence_tokens": tool_tokens,
            "planned_tool_call_count": planned_tool_calls,
            "successful_source_count": successful_sources,
            "failed_source_count": failed_sources,
            "truncated": truncated,
            "draft_requested": bool(structured),
            "structured_output_needed": bool(structured),
            "local_provider": config.local_provider,
            "local_model": config.local_model,
            "local_configured": config.local_configured,
            "fallback_mode": config.mode,
            "paid_fallback_enabled": config.paid_fallback_enabled,
            "remaining_timeout_seconds": max(0, round(float(remaining_timeout_seconds), 3)),
        },
    )


def _dedupe_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for call in calls:
        key = json.dumps(call, default=str, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(call)
    return deduped


def _result_sources_include(result: SocToolResult, expected: Any) -> bool:
    text = str(expected)
    return any(text in {str(record_id) for record_id in source.record_ids} or text in source.source_path for source in result.sources)


def _result_matches_source_ip(result: SocToolResult, source_ip: str) -> bool:
    try:
        normalized = str(ipaddress.ip_address(source_ip))
    except ValueError:
        normalized = source_ip
    payload = json.dumps(redact_sensitive_values(result.as_dict()), default=str)
    return normalized in payload


def _tools_requiring_id_match(field_name: str) -> set[str]:
    return {
        "alert_id": {"get_alert_detail", "get_related_events"},
        "incident_id": {"get_incident_timeline"},
        "registry_id": {"get_response_registry_context"},
        "activity_id": {"get_related_events"},
    }.get(field_name, set())


def _extract_severity(data: Any) -> str | None:
    if isinstance(data, dict):
        for key in ("alert", "incident"):
            value = data.get(key)
            if isinstance(value, dict) and value.get("severity"):
                return str(value.get("severity")).strip().lower()
        for child in data.values():
            found = _extract_severity(child)
            if found:
                return found
    if isinstance(data, list):
        for child in data:
            found = _extract_severity(child)
            if found:
                return found
    return None


def _has_incident_reference(data: Any, tools: SocToolExecutionSummary) -> bool:
    payload = json.dumps(redact_sensitive_values(data), default=str).lower()
    if "incident" in payload:
        return True
    return any("incident" in source.source_type.lower() or "incident" in source.source_path.lower() for source in tools.sources)


__all__ = [
    "AUTOMATIC_DRAFT_TYPES",
    "InvestigationPlan",
    "InvestigationPlannerError",
    "WORKFLOW_BY_CONTEXT",
    "WORKFLOW_STEPS",
    "build_investigation_plan",
    "classify_routing_profile",
    "normalize_context_type",
    "select_automatic_draft",
    "validate_tool_evidence",
    "validate_workflow_steps",
    "workflow_for_context",
]
