from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import time
import uuid
from typing import Any, Callable

from flask_login import current_user

from core.ai.config import AiGatewayConfig, load_ai_gateway_config
from core.ai.context_builder import (
    AiContextError,
    AiContextPayload,
    build_ai_context,
)
from core.ai.drafting_service import create_draft
from core.ai.gateway import AiGateway
from core.ai.investigation_models import (
    DEFAULT_INVESTIGATION_TIMEOUT_SECONDS,
    INVESTIGATION_STATUS_CANCELLED,
    INVESTIGATION_STATUS_FAILED,
    INVESTIGATION_STATUS_INSUFFICIENT_CONTEXT,
    INVESTIGATION_STATUS_PARTIAL,
    INVESTIGATION_STATUS_SUCCESS,
    INVESTIGATION_STATUS_TIMEOUT,
    InvestigationObservability,
    InvestigationRun,
    InvestigationStepResult,
    STEP_BUILD_CONTEXT,
    STEP_CORRELATE_EVIDENCE,
    STEP_EXECUTE_READ_TOOL,
    STEP_FINALIZE_SUMMARY,
    STEP_GENERATE_TRANSIENT_DRAFT,
    STEP_PLAN_READ_TOOLS,
    STEP_STATUS_CANCELLED,
    STEP_STATUS_FAILED,
    STEP_STATUS_PARTIAL,
    STEP_STATUS_SKIPPED,
    STEP_STATUS_SUCCESS,
    STEP_STATUS_TIMEOUT,
    STEP_SUGGEST_RESPONSE_PLAN,
    STEP_VALIDATE_EVIDENCE,
)
from core.ai.investigation_planner import (
    InvestigationPlan,
    InvestigationPlannerError,
    build_investigation_plan,
    classify_routing_profile,
    select_automatic_draft,
    validate_tool_evidence,
)
from core.ai.models import AI_STATUS_SUCCESS, AiGatewayRequest, AiRequestMetadata
from core.ai.soc_tool_executor import (
    execute_tool_plan,
    normalize_tool_policy,
    tool_summary_for_prompt,
)
from core.ai.soc_tools import SocToolExecutionSummary, redact_sensitive_values

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class InvestigationServiceResult:
    payload: dict[str, Any]
    status_code: int = 200


class InvestigationCancelled(Exception):
    """Raised when the request-scoped cancellation check stops a run."""


def run_investigation(
    payload: dict[str, Any],
    *,
    gateway: AiGateway | None = None,
    config: AiGatewayConfig | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    timeout_seconds: float = DEFAULT_INVESTIGATION_TIMEOUT_SECONDS,
) -> InvestigationServiceResult:
    if not isinstance(payload, dict):
        raise InvestigationPlannerError("JSON object body is required")

    started = time.monotonic()
    resolved_config = config if config is not None else load_ai_gateway_config()
    resolved_gateway = gateway if gateway is not None else AiGateway(config=resolved_config)
    cancel_check = is_cancelled or (lambda: False)
    run_id = _run_id(payload.get("client_request_id"))
    context_type = str(payload.get("context_type") or "").strip().lower()
    question = _question_from_payload(payload)
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    tool_policy = normalize_tool_policy(payload.get("tool_policy"))
    allow_automatic_draft = payload.get("allow_automatic_draft") is not False
    steps: list[InvestigationStepResult] = []
    provider_metadata: list[dict[str, Any]] = []
    drafts: list[dict[str, Any]] = []
    summary: str | None = None
    recommendations: list[dict[str, Any]] = []
    correlations: list[dict[str, Any]] = []
    error: str | None = None

    try:
        plan = build_investigation_plan(
            context_type=context_type,
            context=context,
            question=question,
            workflow_type=payload.get("workflow_type"),
            tool_policy=tool_policy,
            allow_automatic_draft=allow_automatic_draft,
        )
    except InvestigationPlannerError as planner_error:
        routing = classify_routing_profile(
            workflow_type="unknown",
            context_type=context_type or "unknown",
            context_payload=None,
            planned_tool_calls=0,
            successful_sources=0,
            failed_sources=1,
            truncated=False,
            draft_decision={"decision": "skipped", "reason": str(planner_error)},
            config=resolved_config,
            remaining_timeout_seconds=timeout_seconds,
        )
        run = _build_run(
            run_id=run_id,
            status=INVESTIGATION_STATUS_FAILED,
            workflow_type="unknown",
            context_snapshot={"context_type": context_type},
            steps=[
                _step(
                    STEP_PLAN_READ_TOOLS,
                    STEP_STATUS_FAILED,
                    "Validate investigation request",
                    str(planner_error),
                    error_code=planner_error.error_code,
                )
            ],
            summary=None,
            correlations=[],
            recommendations=[],
            drafts=[],
            evidence=_empty_evidence(),
            routing_profile=routing,
            provider_metadata=[],
            started=started,
            error=str(planner_error),
        )
        return InvestigationServiceResult({"status": run.status, "investigation": run.as_dict(), "error": run.error}, 400)

    context_snapshot = _context_snapshot(context_type=plan.context_type, context=context, workflow_type=plan.workflow_type)

    try:
        _raise_if_cancelled(cancel_check)
        _raise_if_timeout(started, timeout_seconds)
        step_started = time.monotonic()
        ai_context = build_ai_context(
            context_type=plan.context_type,
            context=context,
            config=resolved_config,
            question=question,
        )
        steps.append(
            _step(
                STEP_BUILD_CONTEXT,
                STEP_STATUS_SUCCESS,
                "Build SIEM context",
                "Collected bounded SIEM context from canonical read paths.",
                sources=[source.as_dict() for source in ai_context.sources],
                metadata=ai_context.metadata(),
                started=step_started,
            )
        )
    except AiContextError as context_error:
        routing = classify_routing_profile(
            workflow_type=plan.workflow_type,
            context_type=plan.context_type,
            context_payload=None,
            planned_tool_calls=len(plan.tool_calls),
            successful_sources=0,
            failed_sources=1,
            truncated=False,
            draft_decision={"decision": "skipped", "reason": str(context_error)},
            config=resolved_config,
            remaining_timeout_seconds=_remaining(started, timeout_seconds),
        )
        steps.append(
            _step(
                STEP_BUILD_CONTEXT,
                STEP_STATUS_FAILED,
                "Build SIEM context",
                str(context_error),
                error_code=getattr(context_error, "error_code", "context_error"),
            )
        )
        run = _build_run(
            run_id=run_id,
            status=INVESTIGATION_STATUS_INSUFFICIENT_CONTEXT,
            workflow_type=plan.workflow_type,
            context_snapshot=context_snapshot,
            steps=steps,
            summary=None,
            correlations=[],
            recommendations=[],
            drafts=[],
            evidence=_empty_evidence(),
            routing_profile=routing,
            provider_metadata=[],
            started=started,
            error=str(context_error),
        )
        return InvestigationServiceResult({"status": run.status, "investigation": run.as_dict(), "error": run.error}, 200)
    except InvestigationCancelled as cancel_error:
        return _cancelled_result(run_id, plan, context_snapshot, steps, resolved_config, started, timeout_seconds, str(cancel_error))
    except TimeoutError as timeout_error:
        return _timeout_result(run_id, plan, context_snapshot, steps, resolved_config, started, timeout_seconds, str(timeout_error))

    steps.append(
        _step(
            STEP_PLAN_READ_TOOLS,
            STEP_STATUS_SUCCESS,
            "Plan bounded read tools",
            "Prepared one deterministic, non-recursive read-tool pass.",
            metadata={"tool_calls": list(plan.tool_calls), "bounds": plan.bounds},
        )
    )

    tools = SocToolExecutionSummary(used=False)
    try:
        _raise_if_cancelled(cancel_check)
        _raise_if_timeout(started, timeout_seconds)
        step_started = time.monotonic()
        tools = execute_tool_plan(
            list(plan.tool_calls),
            actor_role=getattr(current_user, "role", None),
            config=resolved_config,
            tool_policy={**(tool_policy or {}), "max_tool_calls": min(len(plan.tool_calls), 5) or 5},
        )
        tool_status = STEP_STATUS_SUCCESS
        if tools.error_code or tools.truncated or any(call.status != "success" for call in tools.calls):
            tool_status = STEP_STATUS_PARTIAL
        steps.append(
            _step(
                STEP_EXECUTE_READ_TOOL,
                tool_status,
                "Execute read-only tools",
                "Executed only canonical SOC read tools.",
                sources=[source.as_dict() for source in tools.sources],
                metadata=tools.as_dict(),
                started=step_started,
            )
        )
    except InvestigationCancelled as cancel_error:
        return _cancelled_result(run_id, plan, context_snapshot, steps, resolved_config, started, timeout_seconds, str(cancel_error))
    except TimeoutError as timeout_error:
        return _timeout_result(run_id, plan, context_snapshot, steps, resolved_config, started, timeout_seconds, str(timeout_error))

    validated_tools, validation_metadata = validate_tool_evidence(
        tools,
        context_snapshot=context_snapshot,
        prompt_budget_chars=max(1000, resolved_config.max_prompt_chars // 3),
    )
    validation_status = STEP_STATUS_SUCCESS if validation_metadata["rejected_count"] == 0 else STEP_STATUS_PARTIAL
    steps.append(
        _step(
            STEP_VALIDATE_EVIDENCE,
            validation_status,
            "Validate evidence",
            "Validated tool source attribution, read-only markers, actor role boundaries, target ids, redaction, and prompt budget.",
            sources=[source.as_dict() for source in validated_tools.sources],
            metadata=validation_metadata,
        )
    )

    draft_decision = select_automatic_draft(
        plan=plan,
        ai_context=ai_context,
        validated_tools=validated_tools,
        gateway_status=None,
    )
    routing = classify_routing_profile(
        workflow_type=plan.workflow_type,
        context_type=plan.context_type,
        context_payload=ai_context,
        planned_tool_calls=len(plan.tool_calls),
        successful_sources=len(ai_context.sources) + len(validated_tools.sources),
        failed_sources=validation_metadata["rejected_count"],
        truncated=ai_context.truncated or validated_tools.truncated,
        draft_decision=draft_decision,
        config=resolved_config,
        remaining_timeout_seconds=_remaining(started, timeout_seconds),
    )

    gateway_response = None
    try:
        _raise_if_cancelled(cancel_check)
        _raise_if_timeout(started, timeout_seconds)
        step_started = time.monotonic()
        prompt = _build_correlation_prompt(
            plan=plan,
            question=question,
            ai_context=ai_context,
            tools=validated_tools,
            routing=routing,
            config=resolved_config,
        )
        if len(prompt) > resolved_config.max_prompt_chars:
            raise InvestigationPlannerError("Investigation prompt exceeded configured AI size limit", error_code="prompt_too_large")
        gateway_response = resolved_gateway.generate(
            AiGatewayRequest(
                prompt=prompt,
                capability="text_generation",
                metadata={
                    "action": "advanced_investigation",
                    "workflow_type": plan.workflow_type,
                    "context_type": plan.context_type,
                    "routing_profile": routing.profile,
                    "read_only": True,
                },
            )
        )
        gateway_payload = gateway_response.as_dict()
        provider_metadata.append(gateway_payload["metadata"])
        if gateway_response.status == AI_STATUS_SUCCESS:
            summary = gateway_response.content
            correlations = _source_citations(ai_context, validated_tools)
            steps.append(
                _step(
                    STEP_CORRELATE_EVIDENCE,
                    STEP_STATUS_SUCCESS,
                    "Correlate source-cited evidence",
                    "Generated a read-only investigation summary from supplied evidence.",
                    sources=_all_sources(ai_context, validated_tools),
                    metadata={"provider_response": gateway_payload["metadata"]},
                    started=step_started,
                )
            )
        else:
            error = gateway_response.error or gateway_response.status
            steps.append(
                _step(
                    STEP_CORRELATE_EVIDENCE,
                    STEP_STATUS_PARTIAL,
                    "Correlate source-cited evidence",
                    "Provider did not return a successful investigation summary; validated evidence is still available.",
                    sources=_all_sources(ai_context, validated_tools),
                    metadata={"provider_response": gateway_payload["metadata"]},
                    error_code=gateway_response.status,
                    started=step_started,
                )
            )
    except InvestigationPlannerError as planner_error:
        error = str(planner_error)
        steps.append(
            _step(
                STEP_CORRELATE_EVIDENCE,
                STEP_STATUS_FAILED,
                "Correlate source-cited evidence",
                str(planner_error),
                sources=_all_sources(ai_context, validated_tools),
                error_code=planner_error.error_code,
            )
        )
    except InvestigationCancelled as cancel_error:
        return _cancelled_result(run_id, plan, context_snapshot, steps, resolved_config, started, timeout_seconds, str(cancel_error))
    except TimeoutError as timeout_error:
        return _timeout_result(run_id, plan, context_snapshot, steps, resolved_config, started, timeout_seconds, str(timeout_error))

    recommendations = _build_recommendations(plan, ai_context, validated_tools, gateway_response)
    steps.append(
        _step(
            STEP_SUGGEST_RESPONSE_PLAN,
            STEP_STATUS_SUCCESS,
            "Suggest response plan",
            "Prepared advisory analyst next steps only; no production action was taken.",
            sources=_all_sources(ai_context, validated_tools),
            metadata={"recommendation_count": len(recommendations), "requires_confirmation": True},
        )
    )

    if draft_decision.get("decision") == "generate" and gateway_response and gateway_response.status == AI_STATUS_SUCCESS:
        try:
            _raise_if_cancelled(cancel_check)
            _raise_if_timeout(started, timeout_seconds)
            step_started = time.monotonic()
            draft_result = create_draft(
                {
                    "draft_type": draft_decision["selected_type"],
                    "instruction": _draft_instruction(draft_decision["selected_type"], plan),
                    "context_type": plan.context_type,
                    "context": context,
                    "use_tools": True,
                    "tool_policy": {"tool_requests": list(plan.tool_calls), "max_tool_calls": min(len(plan.tool_calls), 3) or 3},
                    "client_request_id": f"{run_id}-{draft_decision['selected_type']}",
                },
                gateway=resolved_gateway,
                config=resolved_config,
            )
            draft_payload = draft_result.payload
            provider_metadata.append(draft_payload.get("metadata") or {})
            draft = draft_payload.get("draft") if isinstance(draft_payload.get("draft"), dict) else None
            if draft and draft.get("labels", {}).get("persisted") is False and draft.get("labels", {}).get("applied") is False:
                drafts.append(draft_payload)
                draft_status = STEP_STATUS_SUCCESS if draft_payload.get("status") == "success" else STEP_STATUS_PARTIAL
            else:
                draft_status = STEP_STATUS_FAILED
            draft_decision = {
                **draft_decision,
                "status": draft_payload.get("status"),
                "validation": draft.get("validation") if draft else None,
            }
            steps.append(
                _step(
                    STEP_GENERATE_TRANSIENT_DRAFT,
                    draft_status,
                    "Generate transient draft",
                    "Generated at most one review-only automatic draft; it was not saved or applied.",
                    sources=(draft_payload.get("context") or {}).get("sources", []),
                    metadata={"draft_type": draft_decision["selected_type"], "draft_status": draft_payload.get("status")},
                    started=step_started,
                )
            )
        except InvestigationCancelled as cancel_error:
            steps.append(
                _step(
                    STEP_GENERATE_TRANSIENT_DRAFT,
                    STEP_STATUS_CANCELLED,
                    "Generate transient draft",
                    str(cancel_error),
                    error_code="cancelled",
                )
            )
        except TimeoutError as timeout_error:
            steps.append(
                _step(
                    STEP_GENERATE_TRANSIENT_DRAFT,
                    STEP_STATUS_TIMEOUT,
                    "Generate transient draft",
                    str(timeout_error),
                    error_code="timeout",
                )
            )
    else:
        steps.append(
            _step(
                STEP_GENERATE_TRANSIENT_DRAFT,
                STEP_STATUS_SKIPPED,
                "Generate transient draft",
                draft_decision.get("reason") or "Automatic draft policy skipped this workflow.",
                metadata=draft_decision,
            )
        )

    status = _final_status(ai_context, tools, validated_tools, gateway_response, error)
    steps.append(
        _step(
            STEP_FINALIZE_SUMMARY,
            STEP_STATUS_SUCCESS if status in {INVESTIGATION_STATUS_SUCCESS, INVESTIGATION_STATUS_PARTIAL} else STEP_STATUS_PARTIAL,
            "Finalize investigation",
            "Assembled read-only investigation result with source citations and observability metadata.",
            sources=_all_sources(ai_context, validated_tools),
            metadata={"status": status},
        )
    )
    routing = classify_routing_profile(
        workflow_type=plan.workflow_type,
        context_type=plan.context_type,
        context_payload=ai_context,
        planned_tool_calls=len(plan.tool_calls),
        successful_sources=len(ai_context.sources) + len(validated_tools.sources),
        failed_sources=validation_metadata["rejected_count"],
        truncated=ai_context.truncated or tools.truncated or validated_tools.truncated,
        draft_decision=draft_decision,
        config=resolved_config,
        remaining_timeout_seconds=_remaining(started, timeout_seconds),
    )
    run = _build_run(
        run_id=run_id,
        status=status,
        workflow_type=plan.workflow_type,
        context_snapshot=context_snapshot,
        steps=steps,
        summary=summary,
        correlations=correlations or _source_citations(ai_context, validated_tools),
        recommendations=recommendations,
        drafts=drafts,
        evidence={
            "context": ai_context.metadata(),
            "tools": validated_tools.as_dict(),
            "all_tool_results": tools.as_dict(),
            "read_only": True,
        },
        routing_profile=routing,
        provider_metadata=provider_metadata,
        started=started,
        draft_decision=draft_decision,
        error=error,
    )
    _LOGGER.info(
        "ai_investigation_finished run_id=%s workflow=%s status=%s steps=%s tools=%s sources=%s",
        run_id,
        plan.workflow_type,
        run.status,
        len(run.steps),
        len(plan.tool_calls),
        run.observability.source_count,
    )
    return InvestigationServiceResult({"status": run.status, "investigation": run.as_dict(), "error": run.error}, 200)


def service_error_response(error: Exception) -> InvestigationServiceResult:
    status = getattr(error, "error_code", "invalid_investigation")
    return InvestigationServiceResult(
        {
            "status": status,
            "investigation": None,
            "error": str(error),
        },
        getattr(error, "status_code", 400),
    )


def _question_from_payload(payload: dict[str, Any]) -> str:
    question = str(payload.get("question") or payload.get("instruction") or "").strip()
    if len(question) > 2000:
        raise InvestigationPlannerError("question is too large")
    return question or "Run a guided, read-only SOC investigation using available SIEM evidence."


def _run_id(value: Any) -> str:
    text = str(value or "").strip()
    if text and len(text) <= 120:
        return text
    return f"ai-investigation-{uuid.uuid4().hex[:12]}"


def _raise_if_cancelled(is_cancelled: Callable[[], bool]) -> None:
    if is_cancelled():
        raise InvestigationCancelled("Investigation was cancelled.")


def _raise_if_timeout(started: float, timeout_seconds: float) -> None:
    if time.monotonic() - started > timeout_seconds:
        raise TimeoutError("Investigation timeout budget was exhausted.")


def _remaining(started: float, timeout_seconds: float) -> float:
    return max(0.0, timeout_seconds - (time.monotonic() - started))


def _step(
    step_type: str,
    status: str,
    title: str,
    detail: str,
    *,
    sources: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
    started: float | None = None,
    error_code: str | None = None,
) -> InvestigationStepResult:
    return InvestigationStepResult(
        step_type=step_type,
        status=status,
        title=title,
        detail=detail,
        sources=sources or [],
        metadata=redact_sensitive_values(metadata or {}),
        latency_ms=max(0, int((time.monotonic() - started) * 1000)) if started else 0,
        error_code=error_code,
        read_only=True,
    )


def _build_correlation_prompt(
    *,
    plan: InvestigationPlan,
    question: str,
    ai_context: AiContextPayload,
    tools: SocToolExecutionSummary,
    routing,
    config: AiGatewayConfig,
) -> str:
    context_json = json.dumps(redact_sensitive_values(ai_context.data), default=str, sort_keys=True, indent=2)
    tools_json = json.dumps(
        tool_summary_for_prompt(tools, max_chars=max(1000, config.max_prompt_chars // 3)),
        default=str,
        sort_keys=True,
        indent=2,
    )
    sources_json = json.dumps(_all_sources(ai_context, tools), default=str, sort_keys=True)
    return (
        "You are a read-only advanced SIEM SOC assistant.\n"
        "Use only supplied SIEM context and validated read-only tool evidence.\n"
        "Cite source paths or record ids for material findings. Distinguish evidence from inference.\n"
        "Do not claim remediation, blocking, approval, execution, deployment, file changes, shell commands, or database writes happened.\n"
        "If evidence is missing or partial, say exactly what is missing.\n"
        "Return concise sections: Summary, Correlated Evidence, Uncertainty, Recommended Analyst Next Steps.\n\n"
        f"Workflow type: {plan.workflow_type}\n"
        f"Context type: {plan.context_type}\n"
        f"Routing profile: {routing.profile}\n"
        f"Question: {question}\n"
        f"Source citations available: {sources_json}\n\n"
        f"SIEM context:\n{context_json}\n\n"
        f"Validated read-only SOC tool evidence:\n{tools_json}\n"
    )


def _build_recommendations(
    plan: InvestigationPlan,
    ai_context: AiContextPayload,
    tools: SocToolExecutionSummary,
    gateway_response,
) -> list[dict[str, Any]]:
    base_sources = _all_sources(ai_context, tools)
    gateway_ok = bool(gateway_response and gateway_response.status == AI_STATUS_SUCCESS)
    return [
        {
            "title": "Review correlated evidence",
            "recommendation": "Use the cited alert, incident, source-IP, event, playbook, and registry evidence to confirm scope before any response.",
            "evidence_source_count": len(base_sources),
            "requires_confirmation": False,
            "production_action": False,
            "source_refs": base_sources[:8],
        },
        {
            "title": "Prepare response through existing controls",
            "recommendation": "If containment or record changes are warranted, use the existing preview and explicit confirmation workflow. This investigation did not execute any production action.",
            "requires_confirmation": True,
            "production_action": False,
            "source_refs": base_sources[:8],
        },
        {
            "title": "Handle incomplete evidence",
            "recommendation": "Treat missing, forbidden, failed, or truncated tool results as manual follow-up items before escalation.",
            "requires_confirmation": False,
            "production_action": False,
            "source_refs": base_sources[:8],
            "incomplete": not gateway_ok or tools.truncated or any(call.status != "success" for call in tools.calls),
        },
    ]


def _draft_instruction(draft_type: str, plan: InvestigationPlan) -> str:
    return (
        f"Create a {draft_type} from this {plan.workflow_type}. "
        "Use only supplied SIEM evidence. Keep it review-only, source-cited, not saved, not applied, and not executed."
    )


def _final_status(ai_context, tools, validated_tools, gateway_response, error: str | None) -> str:
    if ai_context.insufficient_context and not validated_tools.sources:
        return INVESTIGATION_STATUS_INSUFFICIENT_CONTEXT
    if error:
        return INVESTIGATION_STATUS_PARTIAL if validated_tools.sources or ai_context.sources else INVESTIGATION_STATUS_FAILED
    if gateway_response is None or gateway_response.status != AI_STATUS_SUCCESS:
        return INVESTIGATION_STATUS_PARTIAL if validated_tools.sources or ai_context.sources else INVESTIGATION_STATUS_FAILED
    if tools.truncated or any(call.status != "success" for call in tools.calls):
        return INVESTIGATION_STATUS_PARTIAL
    return INVESTIGATION_STATUS_SUCCESS


def _build_run(
    *,
    run_id: str,
    status: str,
    workflow_type: str,
    context_snapshot: dict[str, Any],
    steps: list[InvestigationStepResult],
    summary: str | None,
    correlations: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
    drafts: list[dict[str, Any]],
    evidence: dict[str, Any],
    routing_profile,
    provider_metadata: list[dict[str, Any]],
    started: float,
    draft_decision: dict[str, Any] | None = None,
    error: str | None = None,
) -> InvestigationRun:
    observability = _observability(
        status=status,
        workflow_type=workflow_type,
        steps=steps,
        evidence=evidence,
        routing_profile=routing_profile,
        provider_metadata=provider_metadata,
        started=started,
        draft_decision=draft_decision or {},
        drafts=drafts,
    )
    return InvestigationRun(
        run_id=run_id,
        status=status,
        workflow_type=workflow_type,
        context_snapshot=redact_sensitive_values(context_snapshot),
        steps=steps,
        summary=summary,
        correlations=correlations,
        recommendations=recommendations,
        drafts=drafts,
        evidence=redact_sensitive_values(evidence),
        observability=observability,
        error=error,
    )


def _observability(
    *,
    status: str,
    workflow_type: str,
    steps: list[InvestigationStepResult],
    evidence: dict[str, Any],
    routing_profile,
    provider_metadata: list[dict[str, Any]],
    started: float,
    draft_decision: dict[str, Any],
    drafts: list[dict[str, Any]],
) -> InvestigationObservability:
    tools = evidence.get("tools") if isinstance(evidence, dict) else {}
    calls = tools.get("calls") if isinstance(tools, dict) and isinstance(tools.get("calls"), list) else []
    statuses: dict[str, int] = {}
    for call in calls:
        status_value = str(call.get("status") or "unknown")
        statuses[status_value] = statuses.get(status_value, 0) + 1
    sources = tools.get("sources") if isinstance(tools, dict) and isinstance(tools.get("sources"), list) else []
    context = evidence.get("context") if isinstance(evidence, dict) and isinstance(evidence.get("context"), dict) else {}
    context_sources = context.get("sources") if isinstance(context.get("sources"), list) else []
    cost_values = [
        float(item["estimated_cost_usd"])
        for item in provider_metadata
        if isinstance(item, dict) and item.get("estimated_cost_usd") is not None
    ]
    fallback_path = [
        {
            "provider": item.get("provider"),
            "model": item.get("model"),
            "status": item.get("status"),
            "fallback_attempted": item.get("fallback_attempted"),
            "fallback_reason": item.get("fallback_reason"),
            "local_request": item.get("local_request"),
            "paid_request": item.get("paid_request"),
        }
        for item in provider_metadata
        if isinstance(item, dict)
    ]
    return InvestigationObservability(
        status=status,
        workflow_type=workflow_type,
        routing_profile=routing_profile,
        total_latency_ms=max(0, int((time.monotonic() - started) * 1000)),
        planned_step_count=len(steps),
        executed_step_count=len([step for step in steps if step.status != "pending"]),
        tool_call_count=len(calls),
        tool_statuses=statuses,
        source_count=len(sources) + len(context_sources),
        truncated=bool(tools.get("truncated") or context.get("truncated")),
        omitted_count=int(tools.get("omitted_count") or 0) + int(context.get("omitted_count") or 0),
        retry_count=0,
        timed_out=status == INVESTIGATION_STATUS_TIMEOUT,
        cancelled=status == "cancelled",
        aggregate_prompt_tokens=sum(int(item.get("estimated_prompt_tokens") or 0) for item in provider_metadata if isinstance(item, dict)),
        aggregate_completion_tokens=sum(int(item.get("estimated_completion_tokens") or 0) for item in provider_metadata if isinstance(item, dict)),
        aggregate_estimated_cost_usd=sum(cost_values) if cost_values else None,
        fallback_path=fallback_path,
        automatic_draft_decision=draft_decision,
        draft_validation_state=_draft_validation_state(drafts),
        provider_responses=provider_metadata,
    )


def _draft_validation_state(drafts: list[dict[str, Any]]) -> dict[str, Any]:
    if not drafts:
        return {"draft_count": 0, "valid_count": 0}
    valid_count = 0
    for draft_response in drafts:
        draft = draft_response.get("draft") if isinstance(draft_response, dict) else None
        validation = draft.get("validation") if isinstance(draft, dict) else None
        if isinstance(validation, dict) and validation.get("valid") is True:
            valid_count += 1
    return {"draft_count": len(drafts), "valid_count": valid_count}


def _context_snapshot(*, context_type: str, context: dict[str, Any], workflow_type: str) -> dict[str, Any]:
    keys = ("alert_id", "incident_id", "source_ip", "registry_id", "activity_id", "selected_alert_id", "selected_incident_id")
    return {
        "context_type": context_type,
        "workflow_type": workflow_type,
        **{key: context.get(key) for key in keys if context.get(key) not in (None, "")},
    }


def _all_sources(ai_context: AiContextPayload, tools: SocToolExecutionSummary) -> list[dict[str, Any]]:
    return [source.as_dict() for source in ai_context.sources] + [source.as_dict() for source in tools.sources]


def _source_citations(ai_context: AiContextPayload, tools: SocToolExecutionSummary) -> list[dict[str, Any]]:
    citations = []
    for source in _all_sources(ai_context, tools):
        citations.append(
            {
                "source_type": source.get("source_type"),
                "source_path": source.get("source_path"),
                "record_ids": source.get("record_ids", []),
                "finding_type": "direct_evidence",
            }
        )
    return citations


def _empty_evidence() -> dict[str, Any]:
    return {
        "context": {"context_type": None, "sources": [], "truncated": False, "omitted_count": 0},
        "tools": SocToolExecutionSummary(used=False).as_dict(),
        "all_tool_results": SocToolExecutionSummary(used=False).as_dict(),
        "read_only": True,
    }


def _timeout_result(
    run_id: str,
    plan: InvestigationPlan,
    context_snapshot: dict[str, Any],
    steps: list[InvestigationStepResult],
    config: AiGatewayConfig,
    started: float,
    timeout_seconds: float,
    message: str,
) -> InvestigationServiceResult:
    return _stop_result(
        run_id,
        plan,
        context_snapshot,
        steps,
        config,
        started,
        timeout_seconds,
        message,
        status=INVESTIGATION_STATUS_TIMEOUT,
        step_status=STEP_STATUS_TIMEOUT,
        error_code="timeout",
        reason="timeout",
    )


def _cancelled_result(
    run_id: str,
    plan: InvestigationPlan,
    context_snapshot: dict[str, Any],
    steps: list[InvestigationStepResult],
    config: AiGatewayConfig,
    started: float,
    timeout_seconds: float,
    message: str,
) -> InvestigationServiceResult:
    return _stop_result(
        run_id,
        plan,
        context_snapshot,
        steps,
        config,
        started,
        timeout_seconds,
        message,
        status=INVESTIGATION_STATUS_CANCELLED,
        step_status=STEP_STATUS_CANCELLED,
        error_code="cancelled",
        reason="cancelled",
    )


def _stop_result(
    run_id: str,
    plan: InvestigationPlan,
    context_snapshot: dict[str, Any],
    steps: list[InvestigationStepResult],
    config: AiGatewayConfig,
    started: float,
    timeout_seconds: float,
    message: str,
    *,
    status: str,
    step_status: str,
    error_code: str,
    reason: str,
) -> InvestigationServiceResult:
    routing = classify_routing_profile(
        workflow_type=plan.workflow_type,
        context_type=plan.context_type,
        context_payload=None,
        planned_tool_calls=len(plan.tool_calls),
        successful_sources=0,
        failed_sources=1,
        truncated=False,
        draft_decision={"decision": "skipped", "reason": reason},
        config=config,
        remaining_timeout_seconds=_remaining(started, timeout_seconds),
    )
    steps.append(_step(STEP_FINALIZE_SUMMARY, step_status, "Finalize investigation", message, error_code=error_code))
    run = _build_run(
        run_id=run_id,
        status=status,
        workflow_type=plan.workflow_type,
        context_snapshot=context_snapshot,
        steps=steps,
        summary=None,
        correlations=[],
        recommendations=[],
        drafts=[],
        evidence=_empty_evidence(),
        routing_profile=routing,
        provider_metadata=[],
        started=started,
        draft_decision={"decision": "skipped", "reason": reason},
        error=message,
    )
    return InvestigationServiceResult({"status": run.status, "investigation": run.as_dict(), "error": message}, 200)


__all__ = [
    "InvestigationServiceResult",
    "InvestigationPlannerError",
    "run_investigation",
    "service_error_response",
]
