from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import ipaddress
import json
import re
import time
from typing import Any, Callable

from core.ai.config import (
    AI_MODE_ASK_BEFORE_PAID_FALLBACK,
    AI_MODE_AUTOMATIC_FALLBACK,
    AI_MODE_DISABLED,
    AI_MODE_LOCAL_ONLY,
    AiGatewayConfig,
)
from core.ai.gateway import AiGateway
from core.ai.models import (
    AI_STATUS_CONFIGURATION_ERROR,
    AI_STATUS_DISABLED,
    AI_STATUS_FALLBACK_BLOCKED,
    AI_STATUS_FALLBACK_REQUIRES_CONFIRMATION,
    AI_STATUS_PROVIDER_TIMEOUT,
    AI_STATUS_PROVIDER_UNAVAILABLE,
    AI_STATUS_SUCCESS,
    AiGatewayRequest,
    estimate_tokens,
)
from core.ai.anakin_persona import soc_briefing_policy
from core.ai.profile_registry import profile_for_soc_briefing
from core.ai.soc_briefing_runtime_store import (
    JOB_STATUS_BLOCKED,
    JOB_STATUS_FAILED,
    JOB_STATUS_SUCCESS,
    RUN_STATUS_BLOCKED,
    RUN_STATUS_FAILED,
    RUN_STATUS_PARTIAL,
    RUN_STATUS_SUCCESS,
    SERVICE_ACTOR,
    SERVICE_ACTOR_ROLE,
    STEP_STATUS_BLOCKED,
    STEP_STATUS_FAILED,
    STEP_STATUS_PARTIAL,
    STEP_STATUS_SKIPPED,
    STEP_STATUS_SUCCESS,
    SocBriefingPersistenceError,
    as_utc,
    create_run_step,
    idempotency_key,
    record_scheduled_investigation_audit,
    update_briefing_content,
    utc_now,
)
from core.ai.soc_tool_executor import execute_tool_plan, tool_summary_for_prompt
from core.ai.soc_tools import (
    DEFAULT_TOOL_LIMIT,
    SocToolExecutionSummary,
    TOOL_STATUS_SUCCESS,
    SocToolValidationError,
    redact_sensitive_values,
    validate_tool_args,
    validate_tool_name,
)

EVENT_AUDIT = "SCHEDULED_SOC_INVESTIGATION"
BRIEFING_SECTIONS = (
    "alerts_reviewed",
    "dismissed_low_priority_findings",
    "escalations",
    "critical_findings",
    "evidence",
    "recommendations",
)
TERMINAL_SUCCESS_STATUSES = {RUN_STATUS_SUCCESS, RUN_STATUS_PARTIAL}
PLACEHOLDER_SUMMARY_PHRASES = (
    "analysis of provided evidence",
    "analysis of the provided evidence",
    "scheduled soc briefing generated",
    "local soc briefing generated",
)
ANALYST_FACING_INTERNAL_TERMS = (
    "selected candidate",
    "candidate(s)",
    "bounded evidence reference",
    "evidence reference(s)",
    "skipped duplicate candidate",
    "skipped candidate",
    "source_path",
    "tool_name",
    "record_ids",
    "record(s)",
    "record count",
    "dedup_key",
    "idempotency_key",
    "lifecycle_status",
    "content_status",
    "storage",
    "persisted",
    "soc_briefing_runs",
    "soc_briefings",
    "get_alert_detail",
    "get_related_events",
    "get_incident_timeline",
    "get_response_registry_context",
    "read-tool",
    "soc read tool",
    "source path",
    "tool metadata",
    "investigation engine",
    "candidate planning",
    "selected alert severity",
)


@dataclass(frozen=True)
class InvestigationBudget:
    max_runtime_seconds: int = 45
    max_entities: int = 8
    max_tool_calls: int = 12
    max_rows_per_tool: int = DEFAULT_TOOL_LIMIT
    max_evidence_refs: int = 40
    max_prompt_chars: int = 8000
    max_prompt_tokens: int = 3000
    max_completion_tokens: int = 1200
    max_estimated_cost_usd: float = 0.0
    dedup_horizon_hours: int = 24

    def as_dict(self) -> dict[str, Any]:
        return {
            "max_runtime_seconds": self.max_runtime_seconds,
            "max_entities": self.max_entities,
            "max_tool_calls": self.max_tool_calls,
            "max_rows_per_tool": self.max_rows_per_tool,
            "max_evidence_refs": self.max_evidence_refs,
            "max_prompt_chars": self.max_prompt_chars,
            "max_prompt_tokens": self.max_prompt_tokens,
            "max_completion_tokens": self.max_completion_tokens,
            "max_estimated_cost_usd": self.max_estimated_cost_usd,
            "dedup_horizon_hours": self.dedup_horizon_hours,
        }


@dataclass(frozen=True)
class InvestigationCandidate:
    entity_type: str
    entity_id: str
    label: str
    source_ip: str | None
    fingerprint: str
    tool_calls: tuple[dict[str, Any], ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def dedup_key(self) -> str:
        return idempotency_key("scheduled-soc-investigation", self.entity_type, self.entity_id)

    def as_ref(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "label": self.label,
            "source_ip": self.source_ip,
            "fingerprint": self.fingerprint,
            "dedup_key": self.dedup_key,
        }


@dataclass(frozen=True)
class InvestigationOutcome:
    run_status: str
    job_status: str
    window_status: str
    briefing_status: str
    lifecycle_status: str
    content_status: str
    summary: str | None
    sections: dict[str, Any]
    evidence_refs: list[dict[str, Any]]
    ai_gateway_status: str | None = None
    provider_status: str | None = None
    error_code: str | None = None
    error_message: str | None = None


ToolExecutor = Callable[[list[dict[str, Any]], dict[str, Any]], SocToolExecutionSummary]


def run_scheduled_investigation(
    conn,
    *,
    job: dict[str, Any],
    run: dict[str, Any],
    gateway_config: AiGatewayConfig,
    gateway: AiGateway | None = None,
    budget: InvestigationBudget | None = None,
    tool_executor: ToolExecutor | None = None,
    now_fn: Callable[[], datetime] | None = None,
) -> InvestigationOutcome:
    current_budget = budget or InvestigationBudget()
    started = time.monotonic()
    clock = now_fn or utc_now
    window = _fetch_window(conn, int(job["window_id"]))
    deadline = started + current_budget.max_runtime_seconds

    _persist_step(
        conn,
        run,
        1,
        "investigation_plan",
        STEP_STATUS_SUCCESS,
        {"window": _window_ref(window), "budget": current_budget.as_dict()},
        [],
        "Planned read-only scheduled investigation candidates deterministically.",
    )
    candidates, skipped = plan_investigation_candidates(conn, window=window, budget=current_budget)
    recent = _recent_dedup_fingerprints(
        conn,
        schedule_id=int(run["schedule_id"]),
        before=as_utc(window["window_end"]) or clock(),
        budget=current_budget,
    )

    selected: list[InvestigationCandidate] = []
    candidate_refs: list[dict[str, Any]] = []
    step_index = 2
    for candidate in candidates:
        previous = recent.get(candidate.dedup_key)
        if previous == candidate.fingerprint:
            skipped.append({**candidate.as_ref(), "reason": "duplicate_recent_investigation"})
            _persist_step(
                conn,
                run,
                step_index,
                "investigation_candidate_result",
                STEP_STATUS_SKIPPED,
                {"dedup_key": candidate.dedup_key, "evidence_fingerprint": candidate.fingerprint},
                [candidate.as_ref()],
                "Skipped duplicate recent scheduled investigation candidate.",
                error_code="duplicate_recent_investigation",
            )
            step_index += 1
            continue
        selected.append(candidate)
        candidate_refs.append(candidate.as_ref())

    _audit(
        conn,
        run,
        "planned",
        {
            "candidate_count": len(candidates),
            "selected_count": len(selected),
            "skipped_count": len(skipped),
            "skipped_reasons": sorted({str(item.get("reason")) for item in skipped if item.get("reason")}),
        },
    )

    evidence_summary = SocToolExecutionSummary(used=False)
    evidence_refs: list[dict[str, Any]] = []
    omitted_tools = 0
    if selected:
        if _deadline_reached(deadline):
            return _budget_exhausted(conn, run, "runtime_budget_exhausted", candidate_refs)
        planned_calls, omitted_tools = _build_tool_calls(selected, current_budget)
        evidence_summary = _execute_evidence_tools(
            conn,
            run,
            step_index,
            planned_calls,
            gateway_config=gateway_config,
            budget=current_budget,
            tool_executor=tool_executor,
        )
        step_index += max(1, min(len(planned_calls), current_budget.max_tool_calls))
        evidence_refs = _bounded_sources(evidence_summary, current_budget)
        _audit(
            conn,
            run,
            "evidence_collected",
            {
                "tool_calls": len(evidence_summary.calls),
                "truncated": evidence_summary.truncated,
                "omitted_count": evidence_summary.omitted_count + omitted_tools,
                "evidence_ref_count": len(evidence_refs),
            },
        )
    else:
        _persist_step(
            conn,
            run,
            step_index,
            "evidence_collection",
            STEP_STATUS_SKIPPED,
            {"reason": "no_candidates", "skipped_candidates": skipped[: current_budget.max_entities]},
            [],
            "No bounded candidates required SOC read-tool evidence collection.",
            error_code="no_candidates",
        )
        step_index += 1

    for candidate in selected:
        _persist_step(
            conn,
            run,
            step_index,
            "investigation_candidate_result",
            STEP_STATUS_SUCCESS,
            {"dedup_key": candidate.dedup_key, "evidence_fingerprint": candidate.fingerprint},
            [candidate.as_ref()],
            "Recorded scheduled read-only investigation candidate result.",
        )
        step_index += 1

    synthesis = _synthesize_briefing(
        selected=selected,
        skipped=skipped,
        evidence_summary=evidence_summary,
        evidence_refs=evidence_refs,
        gateway_config=gateway_config,
        gateway=gateway,
        budget=current_budget,
    )
    _persist_step(
        conn,
        run,
        step_index,
        "ai_synthesis",
        synthesis["step_status"],
        synthesis["sanitized_input"],
        evidence_refs,
        synthesis["decision_summary"],
        latency_ms=synthesis["latency_ms"],
        error_code=synthesis["error_code"],
        error_message=synthesis["error_message"],
    )
    step_index += 1

    sections = _ensure_sections(synthesis["sections"], selected=selected, skipped=skipped, evidence_refs=evidence_refs)
    briefing_status = synthesis["briefing_status"]
    lifecycle_status = "content_ready" if briefing_status in {"success", "partial"} else briefing_status
    content_status = "ready" if briefing_status in {"success", "partial"} else synthesis["content_status"]
    update_briefing_content(
        conn,
        run,
        status=briefing_status,
        lifecycle_status=lifecycle_status,
        content_status=content_status,
        summary=synthesis["summary"],
        sections=sections,
        evidence_refs=evidence_refs,
        error_code=synthesis["error_code"],
        error_message=synthesis["error_message"],
        generated_at=clock(),
    )
    _persist_step(
        conn,
        run,
        step_index,
        "briefing_persisted",
        STEP_STATUS_SUCCESS,
        {"briefing_status": briefing_status, "section_keys": list(sections)},
        evidence_refs,
        "Persisted structured advisory scheduled SOC briefing content.",
    )
    _audit(
        conn,
        run,
        "completed",
        {
            "run_status": synthesis["run_status"],
            "briefing_status": briefing_status,
            "ai_gateway_status": synthesis["ai_gateway_status"],
            "provider_status": synthesis["provider_status"],
            "error_code": synthesis["error_code"],
        },
    )
    return InvestigationOutcome(
        run_status=synthesis["run_status"],
        job_status=synthesis["job_status"],
        window_status=synthesis["window_status"],
        briefing_status=briefing_status,
        lifecycle_status=lifecycle_status,
        content_status=content_status,
        summary=synthesis["summary"],
        sections=sections,
        evidence_refs=evidence_refs,
        ai_gateway_status=synthesis["ai_gateway_status"],
        provider_status=synthesis["provider_status"],
        error_code=synthesis["error_code"],
        error_message=synthesis["error_message"],
    )


def plan_investigation_candidates(
    conn,
    *,
    window: dict[str, Any],
    budget: InvestigationBudget,
) -> tuple[list[InvestigationCandidate], list[dict[str, Any]]]:
    window_start = as_utc(window["window_start"])
    window_end = as_utc(window["window_end"])
    if window_start is None or window_end is None:
        raise SocBriefingPersistenceError("schedule window timestamps are required for investigation planning")

    raw: list[InvestigationCandidate] = []
    raw.extend(_alert_candidates(conn, window_start, window_end, budget.max_entities + 1))
    raw.extend(_incident_candidates(conn, window_start, window_end, budget.max_entities + 1))
    raw.extend(_recon_candidates(conn, window_start, window_end, budget.max_entities + 1))
    raw.extend(_indicator_candidates(conn, window_start, window_end, budget.max_entities + 1))

    deduped: dict[str, InvestigationCandidate] = {}
    for candidate in raw:
        deduped.setdefault(candidate.dedup_key, candidate)

    ordered = sorted(deduped.values(), key=lambda item: (item.entity_type, item.entity_id))
    selected = ordered[: budget.max_entities]
    skipped = [
        {**candidate.as_ref(), "reason": "entity_limit_exceeded"}
        for candidate in ordered[budget.max_entities :]
    ]
    return selected, skipped


def _execute_evidence_tools(
    conn,
    run: dict[str, Any],
    first_step_index: int,
    planned_calls: list[dict[str, Any]],
    *,
    gateway_config: AiGatewayConfig,
    budget: InvestigationBudget,
    tool_executor: ToolExecutor | None,
) -> SocToolExecutionSummary:
    executor = tool_executor or _default_tool_executor
    safe_calls: list[dict[str, Any]] = []
    validation_index = first_step_index
    for call in planned_calls[: budget.max_tool_calls]:
        started = time.monotonic()
        tool_name = str(call.get("tool_name") or "")
        try:
            validated_name = validate_tool_name(tool_name)
            validated_args = validate_tool_args(validated_name, call.get("arguments") or {})
            safe_call = {"tool_name": validated_name, "arguments": validated_args}
            safe_calls.append(safe_call)
            status = STEP_STATUS_SUCCESS
            error_code = None
            error_message = None
            summary = "Validated scheduled SOC read-tool call before local execution."
        except SocToolValidationError as error:
            status = STEP_STATUS_FAILED
            error_code = error.error_code
            error_message = str(error)
            summary = "Rejected unsupported or mutation-like scheduled SOC read-tool call."
        _persist_step(
            conn,
            run,
            validation_index,
            "soc_read_tool_validation",
            status,
            {"tool_name": tool_name, "arguments": call.get("arguments") or {}},
            [],
            summary,
            latency_ms=int((time.monotonic() - started) * 1000),
            error_code=error_code,
            error_message=error_message,
        )
        validation_index += 1
    if not safe_calls:
        return SocToolExecutionSummary(used=False, error_code="no_valid_tool_calls")

    summary = executor(
        safe_calls,
        {
            "actor_role": SERVICE_ACTOR_ROLE,
            "config": gateway_config,
            "tool_policy": {
                "max_tool_calls": budget.max_tool_calls,
                "max_rows_per_tool": budget.max_rows_per_tool,
            },
        },
    )
    execution_index = validation_index
    for offset, result in enumerate(summary.calls):
        _persist_step(
            conn,
            run,
            execution_index + offset,
            "soc_read_tool",
            STEP_STATUS_SUCCESS if result.status == TOOL_STATUS_SUCCESS else STEP_STATUS_PARTIAL,
            {"tool_name": result.tool_name, "read_only": result.read_only},
            [source.as_dict() for source in result.sources],
            "Executed approved local SOC read tool for scheduled investigation evidence.",
            latency_ms=result.latency_ms,
            error_code=result.error_code,
            error_message=result.error,
            tool_name=result.tool_name,
        )
    return summary


def _synthesize_briefing(
    *,
    selected: list[InvestigationCandidate],
    skipped: list[dict[str, Any]],
    evidence_summary: SocToolExecutionSummary,
    evidence_refs: list[dict[str, Any]],
    gateway_config: AiGatewayConfig,
    gateway: AiGateway | None,
    budget: InvestigationBudget,
) -> dict[str, Any]:
    prompt_payload = _build_synthesis_prompt_payload(
        selected=selected,
        skipped=skipped,
        evidence_summary=evidence_summary,
        evidence_refs=evidence_refs,
        budget=budget,
    )
    prompt = json.dumps(redact_sensitive_values(prompt_payload), default=str, sort_keys=True)
    tokens = estimate_tokens(prompt)
    if len(prompt) > budget.max_prompt_chars or tokens > budget.max_prompt_tokens:
        prompt = prompt[: budget.max_prompt_chars]
        tokens = estimate_tokens(prompt)
    if tokens > budget.max_prompt_tokens:
        return _synthesis_result(
            RUN_STATUS_PARTIAL,
            "partial",
            "partial",
            "partial",
            "budget_exhausted",
            "Prompt token budget was exhausted before AI synthesis.",
            selected=selected,
            skipped=skipped,
            evidence_refs=evidence_refs,
            step_status=STEP_STATUS_PARTIAL,
            ai_gateway_status="budget_exhausted",
            content_status="ready",
        )
    readiness = _gateway_block(gateway_config)
    if readiness is not None:
        return _synthesis_result(
            readiness["run_status"],
            readiness["job_status"],
            readiness["window_status"],
            readiness["briefing_status"],
            readiness["error_code"],
            readiness["message"],
            selected=selected,
            skipped=skipped,
            evidence_refs=evidence_refs,
            step_status=readiness["step_status"],
            ai_gateway_status=readiness["ai_gateway_status"],
            provider_status=readiness["provider_status"],
            content_status=readiness["content_status"],
            prompt_tokens=tokens,
        )

    scheduled_config = _scheduled_gateway_config(gateway_config)
    started = time.monotonic()

    synthesis_gateway = gateway or AiGateway(config=scheduled_config)
    response = synthesis_gateway.generate(
        AiGatewayRequest(
            prompt=prompt,
            capability="scheduled_soc_briefing",
            profile=profile_for_soc_briefing(),
            metadata={
                "service_actor": SERVICE_ACTOR,
                "read_only": True,
                "estimated_prompt_tokens": tokens,
                "max_completion_tokens": budget.max_completion_tokens,
                "max_estimated_cost_usd": budget.max_estimated_cost_usd,
            },
        )
    )
    latency_ms = int((time.monotonic() - started) * 1000)
    metadata = response.metadata.as_dict()
    if metadata.get("paid_request") or (metadata.get("estimated_cost_usd") or 0) > budget.max_estimated_cost_usd:
        return _synthesis_result(
            RUN_STATUS_BLOCKED,
            JOB_STATUS_BLOCKED,
            "blocked",
            "blocked",
            "paid_fallback_blocked",
            "Scheduled autonomous investigation blocked paid provider spending.",
            selected=selected,
            skipped=skipped,
            evidence_refs=evidence_refs,
            step_status=STEP_STATUS_BLOCKED,
            ai_gateway_status=AI_STATUS_FALLBACK_BLOCKED,
            provider_status=metadata.get("provider"),
            content_status="blocked",
            latency_ms=latency_ms,
            prompt_tokens=tokens,
        )
    if response.status != AI_STATUS_SUCCESS:
        status = _status_from_gateway_error(response.metadata.error_code or response.status)
        return _synthesis_result(
            status["run_status"],
            status["job_status"],
            status["window_status"],
            status["briefing_status"],
            response.metadata.error_code or response.status,
            response.error or "AI Gateway synthesis failed.",
            selected=selected,
            skipped=skipped,
            evidence_refs=evidence_refs,
            step_status=status["step_status"],
            ai_gateway_status=response.status,
            provider_status=response.metadata.provider,
            content_status=status["content_status"],
            latency_ms=latency_ms,
            prompt_tokens=tokens,
        )
    parsed, validation_errors = _validate_structured_response(response.content)
    repair_attempted = False
    if parsed is None:
        repair_attempted = True
        repair_started = time.monotonic()
        repaired = _attempt_structured_briefing_repair(
            synthesis_gateway,
            original_content=response.content,
            validation_errors=validation_errors,
            profile_name=profile_for_soc_briefing(),
        )
        latency_ms += int((time.monotonic() - repair_started) * 1000)
        if repaired is not None:
            repair_metadata = repaired.metadata.as_dict()
            if repair_metadata.get("paid_request") or (repair_metadata.get("estimated_cost_usd") or 0) > budget.max_estimated_cost_usd:
                return _synthesis_result(
                    RUN_STATUS_BLOCKED,
                    JOB_STATUS_BLOCKED,
                    "blocked",
                    "blocked",
                    "paid_fallback_blocked",
                    "Scheduled autonomous investigation blocked paid provider spending during JSON repair.",
                    selected=selected,
                    skipped=skipped,
                    evidence_refs=evidence_refs,
                    step_status=STEP_STATUS_BLOCKED,
                    ai_gateway_status=AI_STATUS_FALLBACK_BLOCKED,
                    provider_status=repair_metadata.get("provider"),
                    content_status="blocked",
                    latency_ms=latency_ms,
                    prompt_tokens=tokens,
                    repair_attempted=repair_attempted,
                    validation_errors=validation_errors,
                )
            response = repaired
            parsed, validation_errors = _validate_structured_response(response.content)
    if parsed is None:
        return _synthesis_result(
            RUN_STATUS_PARTIAL,
            "partial",
            "partial",
            "partial",
            "malformed_provider_output",
            "AI provider returned malformed briefing JSON; saved deterministic partial briefing.",
            selected=selected,
            skipped=skipped,
            evidence_refs=evidence_refs,
            step_status=STEP_STATUS_PARTIAL,
            ai_gateway_status=response.status,
            provider_status=response.metadata.provider,
            content_status="ready",
            latency_ms=latency_ms,
            prompt_tokens=tokens,
            repair_attempted=repair_attempted,
            validation_errors=validation_errors,
        )
    return {
        "run_status": RUN_STATUS_SUCCESS,
        "job_status": JOB_STATUS_SUCCESS,
        "window_status": "success",
        "briefing_status": "success",
        "content_status": "ready",
        "summary": _briefing_summary(parsed.get("summary"), selected=selected, skipped=skipped, evidence_refs=evidence_refs),
        "sections": _ensure_sections(parsed.get("sections"), selected=selected, skipped=skipped, evidence_refs=evidence_refs),
        "step_status": STEP_STATUS_SUCCESS,
        "sanitized_input": {
            "prompt_tokens": tokens,
            "paid_request": False,
            "repair_attempted": repair_attempted,
            "repair_count": 1 if repair_attempted else 0,
        },
        "decision_summary": (
            "Generated structured advisory scheduled SOC briefing through AI Gateway."
            if not repair_attempted
            else "Generated structured advisory scheduled SOC briefing after one bounded JSON repair."
        ),
        "error_code": None,
        "error_message": None,
        "ai_gateway_status": response.status,
        "provider_status": response.metadata.provider,
        "latency_ms": latency_ms,
    }


def _build_synthesis_prompt_payload(
    *,
    selected: list[InvestigationCandidate],
    skipped: list[dict[str, Any]],
    evidence_summary: SocToolExecutionSummary,
    evidence_refs: list[dict[str, Any]],
    budget: InvestigationBudget,
) -> dict[str, Any]:
    return {
        "task": "Produce structured read-only scheduled SOC briefing content.",
        "anakin_persona_policy": soc_briefing_policy(),
        "required_sections": list(BRIEFING_SECTIONS),
        "policy": {
            "read_only": True,
            "no_actions": True,
            "no_tool_calls": True,
            "no_sql": True,
            "no_chain_of_thought": True,
            "prioritize_attention": True,
            "avoid_raw_alert_inventory": True,
            "call_out_low_value_noise": True,
        },
        "analyst_quality_contract": {
            "executive_summary": [
                "Answer what happened, why it matters, what changed, and what deserves immediate attention.",
                "Use approximately 2-4 concise paragraphs.",
                "Never use placeholder summaries such as 'Analysis of provided evidence'.",
                "Do not mention selected candidates, bounded evidence references, skipped candidates, source paths, tool names, record counts, or investigation-engine mechanics.",
            ],
            "critical_findings": [
                "Each finding must explain what happened, evidence, why it matters, evidence-qualified confidence, and action without duplicating escalation prose.",
                "If no critical findings exist, explain why the evidence does not justify a critical finding.",
            ],
            "escalations": [
                "Only include items requiring analyst attention.",
                "State immediate action, urgency, evidence, and why it cannot wait without duplicating Critical Findings.",
            ],
            "low_priority_findings": [
                "Explain downgrades using evidence: expected scanner, isolated event, duplicate alert, or insufficient evidence.",
            ],
            "evidence_reviewed": [
                "Do not dump raw JSON.",
                "Explain what was learned from each source in analyst-readable language; do not name backend routes, tool names, source paths, or record counts.",
            ],
            "recommendations": [
                "Reference specific analyst-meaningful evidence such as source IP, alert behavior, alert family, or related events.",
                "Use natural instructions naming what to inspect and why; avoid generic or mechanically concatenated field labels.",
            ],
            "correlation": [
                "Correlate by same source IP, destination, subnet, alert family, repeated behavior, and timeline relationships when evidence supports it.",
            ],
            "analyst_judgment": [
                "State whether activity is malicious, expected, noisy, or uncertain and why; scanning or blocked attempts alone do not prove malicious intent.",
                "State uncertainty naturally without generic disclaimers.",
            ],
        },
        "section_item_guidance": {
            "alerts_reviewed": "Readable alert observations and correlations, not raw inventory.",
            "dismissed_low_priority_findings": "Downgraded items with reason and evidence.",
            "escalations": "Only analyst-attention items with urgency, why, and evidence.",
            "critical_findings": "Reasoned findings with evidence, why it matters, confidence, and recommended action.",
            "evidence": "Evidence Reviewed in readable prose describing what was learned; never raw JSON, source paths, tool names, or record counts.",
            "recommendations": "Evidence-specific read-only next steps.",
        },
        "candidates": [candidate.as_ref() for candidate in selected],
        "skipped": skipped[: budget.max_entities],
        "evidence": tool_summary_for_prompt(evidence_summary, max_chars=budget.max_prompt_chars),
        "evidence_refs": evidence_refs,
        "output_schema": {
            "summary": "string",
            "sections": {
                "alerts_reviewed": [
                    {
                        "what_happened": "string",
                        "supporting_evidence": "string",
                        "analyst_judgment": "string",
                    }
                ],
                "dismissed_low_priority_findings": [
                    {
                        "what_happened": "string",
                        "supporting_evidence": "string",
                        "reason": "string",
                        "recommended_action": "string",
                    }
                ],
                "escalations": [
                    {
                        "what_happened": "string",
                        "supporting_evidence": "string",
                        "why_it_matters": "string",
                        "urgency": "string",
                        "recommended_action": "string",
                    }
                ],
                "critical_findings": [
                    {
                        "what_happened": "string",
                        "supporting_evidence": "string",
                        "why_it_matters": "string",
                        "confidence": "string",
                        "recommended_action": "string",
                    }
                ],
                "evidence": [
                    {
                        "fact": "string",
                        "inference": "string",
                        "uncertainty": "string",
                        "missing_evidence": "string",
                    }
                ],
                "recommendations": [
                    {
                        "recommended_action": "string",
                        "target": "string",
                        "reason": "string",
                        "priority": "string",
                    }
                ],
            },
        },
    }


def _synthesis_result(
    run_status: str,
    job_status: str,
    window_status: str,
    briefing_status: str,
    error_code: str | None,
    message: str,
    *,
    selected: list[InvestigationCandidate],
    skipped: list[dict[str, Any]],
    evidence_refs: list[dict[str, Any]],
    step_status: str,
    ai_gateway_status: str | None,
    provider_status: str | None = None,
    content_status: str,
    latency_ms: int = 0,
    prompt_tokens: int = 0,
    repair_attempted: bool = False,
    validation_errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "run_status": run_status,
        "job_status": job_status,
        "window_status": window_status,
        "briefing_status": briefing_status,
        "content_status": content_status,
        "summary": message,
        "sections": _deterministic_sections(selected=selected, skipped=skipped, evidence_refs=evidence_refs, message=message),
        "step_status": step_status,
        "sanitized_input": {
            "prompt_tokens": prompt_tokens,
            "paid_request": False,
            "repair_attempted": repair_attempted,
            "repair_count": 1 if repair_attempted else 0,
            "validation_errors": (validation_errors or [])[:8],
        },
        "decision_summary": message,
        "error_code": error_code,
        "error_message": message if error_code else None,
        "ai_gateway_status": ai_gateway_status,
        "provider_status": provider_status,
        "latency_ms": latency_ms,
    }


def _gateway_block(config: AiGatewayConfig) -> dict[str, Any] | None:
    if not config.mode_valid:
        return {
            "run_status": RUN_STATUS_FAILED,
            "job_status": JOB_STATUS_FAILED,
            "window_status": "failed",
            "briefing_status": "failed",
            "step_status": STEP_STATUS_FAILED,
            "ai_gateway_status": AI_STATUS_CONFIGURATION_ERROR,
            "provider_status": None,
            "content_status": "failed",
            "error_code": "ai_gateway_configuration_error",
            "message": "AI gateway configuration is invalid.",
        }
    if config.mode == AI_MODE_DISABLED:
        return {
            "run_status": RUN_STATUS_BLOCKED,
            "job_status": JOB_STATUS_BLOCKED,
            "window_status": "blocked",
            "briefing_status": "blocked",
            "step_status": STEP_STATUS_BLOCKED,
            "ai_gateway_status": AI_STATUS_DISABLED,
            "provider_status": None,
            "content_status": "blocked",
            "error_code": "ai_gateway_disabled",
            "message": "AI gateway is disabled; scheduled briefing synthesis was blocked.",
        }
    if config.mode == AI_MODE_LOCAL_ONLY and not config.local_configured:
        return {
            "run_status": RUN_STATUS_BLOCKED,
            "job_status": JOB_STATUS_BLOCKED,
            "window_status": "blocked",
            "briefing_status": "blocked",
            "step_status": STEP_STATUS_BLOCKED,
            "ai_gateway_status": AI_STATUS_PROVIDER_UNAVAILABLE,
            "provider_status": "local_provider_not_configured",
            "content_status": "blocked",
            "error_code": "local_provider_unavailable",
            "message": "Local AI provider is not configured or unavailable.",
        }
    if config.mode == AI_MODE_ASK_BEFORE_PAID_FALLBACK:
        return {
            "run_status": RUN_STATUS_BLOCKED,
            "job_status": JOB_STATUS_BLOCKED,
            "window_status": "blocked",
            "briefing_status": "blocked",
            "step_status": STEP_STATUS_BLOCKED,
            "ai_gateway_status": AI_STATUS_FALLBACK_REQUIRES_CONFIRMATION,
            "provider_status": None,
            "content_status": "blocked",
            "error_code": "paid_fallback_blocked",
            "message": "Scheduled autonomous investigation does not request paid fallback confirmation.",
        }
    return None


def _status_from_gateway_error(error_code: str) -> dict[str, str]:
    if error_code in {AI_STATUS_PROVIDER_TIMEOUT, "provider_timeout"}:
        return {
            "run_status": RUN_STATUS_PARTIAL,
            "job_status": "partial",
            "window_status": "partial",
            "briefing_status": "partial",
            "step_status": STEP_STATUS_PARTIAL,
            "content_status": "ready",
        }
    if error_code in {AI_STATUS_PROVIDER_UNAVAILABLE, "local_provider_not_configured"}:
        return {
            "run_status": RUN_STATUS_BLOCKED,
            "job_status": JOB_STATUS_BLOCKED,
            "window_status": "blocked",
            "briefing_status": "blocked",
            "step_status": STEP_STATUS_BLOCKED,
            "content_status": "blocked",
        }
    return {
        "run_status": RUN_STATUS_PARTIAL,
        "job_status": "partial",
        "window_status": "partial",
        "briefing_status": "partial",
        "step_status": STEP_STATUS_PARTIAL,
        "content_status": "ready",
    }


def _scheduled_gateway_config(config: AiGatewayConfig) -> AiGatewayConfig:
    if config.mode == AI_MODE_AUTOMATIC_FALLBACK:
        return AiGatewayConfig(
            mode=AI_MODE_LOCAL_ONLY,
            configured_mode=config.configured_mode,
            mode_valid=config.mode_valid,
            local_provider=config.local_provider,
            local_base_url=config.local_base_url,
            local_model=config.local_model,
            local_timeout_seconds=config.local_timeout_seconds,
            paid_provider="",
            paid_model="",
            paid_timeout_seconds=config.paid_timeout_seconds,
            paid_fallback_enabled=False,
            max_prompt_chars=config.max_prompt_chars,
            profiles=config.profiles,
        )
    return config


def _default_tool_executor(calls: list[dict[str, Any]], context: dict[str, Any]) -> SocToolExecutionSummary:
    return execute_tool_plan(
        calls,
        actor_role=context.get("actor_role"),
        config=context["config"],
        tool_policy=context.get("tool_policy"),
    )


def _build_tool_calls(
    candidates: list[InvestigationCandidate],
    budget: InvestigationBudget,
) -> tuple[list[dict[str, Any]], int]:
    calls: list[dict[str, Any]] = []
    for candidate in candidates:
        for call in candidate.tool_calls:
            args = dict(call.get("arguments") or {})
            if "limit" in args:
                args["limit"] = min(int(args["limit"]), budget.max_rows_per_tool)
            calls.append({"tool_name": call["tool_name"], "arguments": args})
    return calls[: budget.max_tool_calls], max(0, len(calls) - budget.max_tool_calls)


def _alert_candidates(conn, start: datetime, end: datetime, limit: int) -> list[InvestigationCandidate]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, alert_type, severity, status, source_ip::text, created_at, message, context
            FROM alerts
            WHERE created_at >= %s AND created_at <= %s
            ORDER BY
                CASE lower(severity)
                    WHEN 'critical' THEN 0
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    ELSE 3
                END,
                created_at DESC,
                id DESC
            LIMIT %s
            """,
            (start, end, max(1, limit)),
        )
        rows = cur.fetchall()
    return [
        InvestigationCandidate(
            entity_type="alert",
            entity_id=str(row[0]),
            label=f"{row[2]} alert {row[1]}",
            source_ip=str(row[4]) if row[4] else None,
            fingerprint=idempotency_key("alert", row[0], row[3], row[5], row[6], row[7]),
            tool_calls=(
                {"tool_name": "get_alert_detail", "arguments": {"alert_id": row[0]}},
                {"tool_name": "get_related_events", "arguments": {"alert_id": row[0], "limit": DEFAULT_TOOL_LIMIT}},
            ),
            metadata={"severity": row[2], "status": row[3], "created_at": row[5]},
        )
        for row in rows
    ]


def _incident_candidates(conn, start: datetime, end: datetime, limit: int) -> list[InvestigationCandidate]:
    del start
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, title, severity, priority, status, source_ip::text, created_at, resolved_at
            FROM incidents
            WHERE status IN ('open', 'investigating')
               OR (created_at <= %s AND COALESCE(resolved_at, %s) >= %s)
            ORDER BY
                CASE priority WHEN 'P1' THEN 0 WHEN 'P2' THEN 1 WHEN 'P3' THEN 2 ELSE 3 END,
                created_at DESC,
                id DESC
            LIMIT %s
            """,
            (end, end, end - timedelta(hours=24), max(1, limit)),
        )
        rows = cur.fetchall()
    return [
        InvestigationCandidate(
            entity_type="incident",
            entity_id=str(row[0]),
            label=f"{row[3]} incident {row[1]}",
            source_ip=str(row[5]) if row[5] else None,
            fingerprint=idempotency_key("incident", row[0], row[2], row[3], row[4], row[7]),
            tool_calls=({"tool_name": "get_incident_timeline", "arguments": {"incident_id": row[0]}},),
            metadata={"severity": row[2], "priority": row[3], "status": row[4]},
        )
        for row in rows
    ]


def _recon_candidates(conn, start: datetime, end: datetime, limit: int) -> list[InvestigationCandidate]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, activity_type, severity, status, protected_range_key, last_seen, summary
            FROM recon_activities
            WHERE status IN ('open', 'monitoring')
              AND last_seen >= %s
              AND first_seen <= %s
            ORDER BY last_seen DESC, id DESC
            LIMIT %s
            """,
            (start, end, max(1, limit)),
        )
        rows = cur.fetchall()
    return [
        InvestigationCandidate(
            entity_type="recon_activity",
            entity_id=str(row[0]),
            label=f"{row[2]} recon activity {row[4]}",
            source_ip=None,
            fingerprint=idempotency_key("recon", row[0], row[3], row[5], row[6]),
            tool_calls=({"tool_name": "get_related_events", "arguments": {"activity_id": row[0], "limit": DEFAULT_TOOL_LIMIT}},),
            metadata={"severity": row[2], "status": row[3], "protected_range_key": row[4]},
        )
        for row in rows
    ]


def _indicator_candidates(conn, start: datetime, end: datetime, limit: int) -> list[InvestigationCandidate]:
    del start
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, indicator_type, indicator_value, current_disposition, updated_at
            FROM indicator_registry
            WHERE current_disposition IN ('monitored', 'escalated', 'pending', 'blocklist_tracked')
              AND updated_at <= %s
            ORDER BY updated_at DESC, id DESC
            LIMIT %s
            """,
            (end, max(1, limit)),
        )
        rows = cur.fetchall()
    candidates: list[InvestigationCandidate] = []
    for row in rows:
        args: dict[str, Any] = {"registry_id": row[0], "limit": DEFAULT_TOOL_LIMIT}
        candidates.append(
            InvestigationCandidate(
                entity_type="indicator",
                entity_id=str(row[0]),
                label=f"{row[3]} {row[1]} indicator",
                source_ip=str(row[2]) if row[1] == "ip" else None,
                fingerprint=idempotency_key("indicator", row[0], row[3], row[4]),
                tool_calls=({"tool_name": "get_response_registry_context", "arguments": args},),
                metadata={"indicator_type": row[1], "disposition": row[3]},
            )
        )
    return candidates


def _recent_dedup_fingerprints(
    conn,
    *,
    schedule_id: int,
    before: datetime,
    budget: InvestigationBudget,
) -> dict[str, str]:
    since = before - timedelta(hours=max(1, budget.dedup_horizon_hours))
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.sanitized_input->>'dedup_key', s.sanitized_input->>'evidence_fingerprint'
            FROM soc_briefing_run_steps s
            JOIN soc_briefing_runs r ON r.id = s.run_id
            WHERE r.schedule_id = %s
              AND r.started_at >= %s
              AND r.started_at < %s
              AND r.status IN ('success', 'partial', 'running')
              AND s.step_type = 'investigation_candidate_result'
              AND s.status IN ('success', 'partial')
              AND s.sanitized_input ? 'dedup_key'
              AND s.sanitized_input ? 'evidence_fingerprint'
            ORDER BY s.created_at DESC
            LIMIT 500
            """,
            (schedule_id, since, before),
        )
        return {str(row[0]): str(row[1]) for row in cur.fetchall() if row[0] and row[1]}


def _fetch_window(conn, window_id: int) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM soc_briefing_schedule_windows WHERE id = %s", (window_id,))
        row = cur.fetchone()
        if row is None:
            raise SocBriefingPersistenceError("schedule window not found for investigation")
        columns = [desc[0] for desc in cur.description]
        return dict(zip(columns, row))


def _bounded_sources(summary: SocToolExecutionSummary, budget: InvestigationBudget) -> list[dict[str, Any]]:
    refs = [source.as_dict() for source in summary.sources]
    return redact_sensitive_values(refs[: budget.max_evidence_refs])


def _deterministic_sections(
    *,
    selected: list[InvestigationCandidate],
    skipped: list[dict[str, Any]],
    evidence_refs: list[dict[str, Any]],
    message: str,
) -> dict[str, Any]:
    critical = [
        _critical_finding_text(candidate, evidence_refs)
        for candidate in selected
        if str(candidate.metadata.get("severity") or "").lower() == "critical"
    ]
    escalations = [
        _escalation_text(candidate, evidence_refs)
        for candidate in selected
        if str(candidate.metadata.get("severity") or "").lower() in {"critical", "high"}
        or str(candidate.metadata.get("priority") or "") == "P1"
    ]
    dismissed = [_low_priority_text(item) for item in skipped if item.get("reason") == "duplicate_recent_investigation"]
    evidence = [_evidence_ref_text(ref) for ref in evidence_refs]
    recommendations = _recommendation_texts(selected, evidence_refs, message)
    return {
        "alerts_reviewed": _alerts_reviewed_texts(selected),
        "dismissed_low_priority_findings": dismissed
        or ["No low-priority findings were separated out. The reviewed activity does not include an obvious approved scanner, duplicate alert pattern, or isolated benign explanation that would justify downgrading it without more context."],
        "escalations": escalations
        or ["No escalation is warranted from the collected evidence because the reviewed activity did not show critical/high severity, P1 priority, or a confirmed impact signal."],
        "critical_findings": critical
        or ["No critical finding is listed because the available evidence does not show confirmed compromise, successful exploitation, or a critical-severity pattern requiring immediate containment."],
        "evidence": evidence
        or ["No detailed evidence was available for this briefing window. Treat the judgment as limited until alert details, related events, endpoint telemetry, or authentication outcomes are reviewed."],
        "recommendations": recommendations,
    }


def _ensure_sections(
    sections: Any,
    *,
    selected: list[InvestigationCandidate],
    skipped: list[dict[str, Any]],
    evidence_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    base = _deterministic_sections(
        selected=selected,
        skipped=skipped,
        evidence_refs=evidence_refs,
        message="Scheduled SOC briefing content prepared.",
    )
    if not isinstance(sections, dict):
        return base
    merged: dict[str, Any] = {}
    for key in BRIEFING_SECTIONS:
        value = sections.get(key, base[key])
        merged[key] = _normalize_section_items(key, value if isinstance(value, list) else base[key], fallback=base[key])
    return redact_sensitive_values(merged)


def _briefing_summary(
    value: Any,
    *,
    selected: list[InvestigationCandidate],
    skipped: list[dict[str, Any]],
    evidence_refs: list[dict[str, Any]],
) -> str:
    text = _bounded_text(value, 2000)
    if _summary_has_analyst_quality(text):
        return text
    return _deterministic_summary(selected=selected, skipped=skipped, evidence_refs=evidence_refs)


def _deterministic_summary(
    *,
    selected: list[InvestigationCandidate],
    skipped: list[dict[str, Any]],
    evidence_refs: list[dict[str, Any]],
) -> str:
    del skipped
    critical_count = sum(1 for item in selected if str(item.metadata.get("severity") or "").lower() == "critical")
    high_count = sum(1 for item in selected if str(item.metadata.get("severity") or "").lower() == "high")
    source_ips = sorted({_display_ip(item.source_ip) for item in selected if item.source_ip})
    activity = _activity_overview(selected, source_ips)
    judgment = _security_judgment(selected, evidence_refs)
    attention = _attention_sentence(critical_count, high_count, source_ips)
    next_action = _next_action_sentence(selected, evidence_refs)
    return (
        f"{activity} {judgment}\n\n"
        f"{attention} {next_action}"
    )


def _summary_has_analyst_quality(text: str | None) -> bool:
    if not text:
        return False
    cleaned = _sanitize_analyst_text(text)
    if not cleaned or _is_placeholder_summary(cleaned) or _has_internal_analyst_term(cleaned):
        return False
    normalized = " ".join(cleaned.lower().split())
    words = re.findall(r"\b[\w.-]+\b", normalized)
    if len(words) < 18:
        return False
    sentences = [part for part in re.split(r"[.!?]+", cleaned) if part.strip()]
    if len(sentences) < 2:
        return False
    alert_family_only = (
        len(words) <= 8
        and any(term in normalized for term in ("scan", "scanning", "port scan", "firewall", "alert", "activity"))
        and not any(term in normalized for term in ("because", "but", "so", "therefore", "verify", "review"))
    )
    if alert_family_only:
        return False
    has_activity = any(
        term in normalized
        for term in (
            "scan",
            "scanning",
            "connection",
            "attempt",
            "alert",
            "source ip",
            "firewall",
            "authentication",
            "deny",
            "denied",
            "traffic",
            "activity",
            "incident",
        )
    )
    has_judgment = any(
        term in normalized
        for term in (
            "looks like",
            "appears",
            "suggests",
            "matters",
            "because",
            "confirmed compromise",
            "reconnaissance",
            "benign",
            "malicious",
            "uncertain",
            "not show",
            "does not show",
            "no successful",
            "impact",
            "confidence",
        )
    )
    has_direction = any(
        term in normalized
        for term in (
            "next",
            "review",
            "verify",
            "check",
            "escalate",
            "monitor",
            "attention",
            "what matters",
            "before escalating",
            "investigate",
        )
    )
    return has_activity and has_judgment and has_direction


def _is_placeholder_summary(text: str) -> bool:
    normalized = " ".join(str(text or "").lower().split())
    return any(phrase in normalized for phrase in PLACEHOLDER_SUMMARY_PHRASES)


def _has_internal_analyst_term(text: str) -> bool:
    normalized = " ".join(str(text or "").lower().split())
    if re.search(r"/(?:alerts|incidents|events|recon|response-registry)/\d+", normalized):
        return True
    return any(term in normalized for term in ANALYST_FACING_INTERNAL_TERMS)


def _activity_overview(selected: list[InvestigationCandidate], source_ips: list[str]) -> str:
    if not selected:
        return "No alerts or related security activity stood out during this briefing window."
    entity_counts: dict[str, int] = {}
    for candidate in selected:
        entity_counts[candidate.entity_type] = entity_counts.get(candidate.entity_type, 0) + 1
    families = sorted({_friendly_label(candidate.label) for candidate in selected if candidate.label})
    family_text = families[0] if len(families) == 1 else ", ".join(families[:3])
    activity_text = _plural_activity(family_text or "security alert", len(selected))
    if source_ips:
        return f"{_count_word(len(selected)).capitalize()} {activity_text} involved source IP {', '.join(source_ips[:3])} during the briefing window."
    return f"{_count_word(len(selected)).capitalize()} {activity_text} appeared during the briefing window, but the available context did not include a source IP to correlate."


def _security_judgment(selected: list[InvestigationCandidate], evidence_refs: list[dict[str, Any]]) -> str:
    if not selected:
        return "There is not enough activity here to call this malicious; the main judgment is that no immediate handoff item is visible."
    critical_or_high = any(str(candidate.metadata.get("severity") or "").lower() in {"critical", "high"} for candidate in selected)
    if critical_or_high:
        return (
            "This is suspicious enough for same-shift review, but the available evidence does not show exploitation, successful authentication, or confirmed impact. "
            "That makes the current judgment reconnaissance or scanning rather than confirmed compromise."
        )
    if evidence_refs:
        return (
            "This currently looks like lower-confidence activity: evidence exists, but it does not show impact or a successful follow-up action. "
            "Keep it in view if the source repeats or touches protected services."
        )
    return "The available context is too thin to classify as malicious or benign; treat it as uncertain until alert details and related activity are available."


def _attention_sentence(critical_count: int, high_count: int, source_ips: list[str]) -> str:
    if critical_count or high_count:
        source = f" Source IP {source_ips[0]} is the first pivot." if source_ips else ""
        return f"What matters most: critical or high-severity activity needs analyst review before it is dismissed.{source}"
    return "What can wait: there is no critical finding or escalation signal in the reviewed evidence."


def _next_action_sentence(selected: list[InvestigationCandidate], evidence_refs: list[dict[str, Any]]) -> str:
    source_ips = sorted({_display_ip(candidate.source_ip) for candidate in selected if candidate.source_ip})
    if source_ips:
        return f"Next action: verify whether {source_ips[0]} belongs to an approved scanner, then check firewall and authentication activity for successful follow-up against internal hosts."
    if evidence_refs:
        return "Next action: review the alert detail and related-event timeline to determine whether the activity progressed beyond blocked or denied attempts."
    return "Next action: collect alert detail, related events, endpoint telemetry, and authentication outcomes before escalating."


def _normalize_section_items(section_key: str, value: list[Any], *, fallback: list[Any]) -> list[str]:
    items = value or fallback
    normalized = [_readable_item_text(item, section_key) for item in items]
    normalized = [item for item in normalized if item]
    normalized = [_sanitize_analyst_text(item) for item in normalized]
    normalized = [item for item in normalized if item and not _has_internal_analyst_term(item)]
    if normalized:
        return normalized
    fallback_items = [_sanitize_analyst_text(_readable_item_text(item, section_key)) for item in fallback]
    fallback_items = [item for item in fallback_items if item and not _has_internal_analyst_term(item)]
    return fallback_items or [_empty_section_judgment(section_key)]


def _readable_item_text(item: Any, section_key: str) -> str:
    if isinstance(item, str):
        return _sanitize_analyst_text(item)
    if isinstance(item, dict):
        return _readable_dict_item(item, section_key)
    if isinstance(item, (list, tuple)):
        values = [_sanitize_analyst_text(value) for value in _extract_scalar_values(item)]
        values = [value for value in values if value and not _has_internal_analyst_term(value)]
        if values:
            return f"{_section_prefix(section_key)} {'; '.join(values[:4])}."
        return _empty_section_judgment(section_key)
    return _sanitize_analyst_text(item)


def _readable_dict_item(item: dict[str, Any], section_key: str) -> str:
    values = _semantic_values(item)
    if section_key == "evidence":
        return _evidence_dict_text(item, values)
    if section_key == "recommendations":
        return _recommendation_dict_text(item, values)
    if section_key == "critical_findings":
        return _finding_dict_text(item, values, critical=True)
    if section_key == "escalations":
        return _finding_dict_text(item, values, critical=False, escalation=True)
    if section_key == "dismissed_low_priority_findings":
        return _low_priority_dict_text(item, values)
    if section_key == "alerts_reviewed":
        return _alert_review_dict_text(item, values)
    return _unknown_dict_text(section_key, values)


def _semantic_values(item: dict[str, Any]) -> dict[str, str]:
    keys = (
        "fact",
        "inference",
        "uncertainty",
        "missing_evidence",
        "type",
        "description",
        "step",
        "action",
        "target",
        "title",
        "summary",
        "detail",
        "what_happened",
        "supporting_evidence",
        "why_it_matters",
        "confidence",
        "recommended_action",
        "reason",
        "urgency",
        "priority",
        "source_ip",
        "alert_type",
        "status",
        "severity",
        "label",
        "analyst_judgment",
    )
    values: dict[str, str] = {}
    for key in keys:
        if key in item:
            value = _sanitize_analyst_text(item.get(key), field_name=key)
            if value:
                values[key] = value
    return values


def _evidence_dict_text(item: dict[str, Any], values: dict[str, str]) -> str:
    if values.get("fact") and values.get("inference"):
        text = f"Evidence showed: {values['fact']}. Analyst judgment: {values['inference']}."
        if values.get("uncertainty"):
            text += f" Uncertainty: {values['uncertainty']}."
        if values.get("missing_evidence"):
            text += f" Missing evidence: {values['missing_evidence']}."
        return text
    if values.get("fact"):
        text = f"Evidence showed: {values['fact']}."
        if values.get("uncertainty"):
            text += f" Uncertainty: {values['uncertainty']}."
        return text
    if values.get("type") and values.get("description"):
        return f"{_friendly_observation_type(values['type'])}: {values['description']}."
    if values.get("type"):
        return f"Evidence reviewed: {_friendly_observation_type(values['type'])}."
    if values.get("description"):
        return f"Evidence showed: {values['description']}."
    if item.get("source_path"):
        return _evidence_source_path_text(str(item.get("source_path") or ""))
    return _unknown_dict_text("evidence", values or _unknown_scalar_values(item))


def _recommendation_dict_text(item: dict[str, Any], values: dict[str, str]) -> str:
    if values.get("action") and values.get("target"):
        action = _recommendation_action(values["action"])
        target = _target_phrase(values.get("target"), action=action)
        reason = f" Reason: {values['reason']}." if values.get("reason") else ""
        return f"{action}{target} to determine whether additional reconnaissance or follow-up connections occurred.{reason}"
    if values.get("step") and values.get("description"):
        return f"Priority {values['step']}: {_recommendation_action(values['description'])}."
    if values.get("recommended_action"):
        action = _recommendation_action(values["recommended_action"])
        target = _target_phrase(values.get("target"), action=action)
        reason = f" Reason: {values['reason']}." if values.get("reason") else ""
        return f"{action}{target}.{reason}"
    if values.get("description"):
        return f"{_recommendation_action(values['description'])}."
    return _unknown_dict_text("recommendations", values or _unknown_scalar_values(item))


def _finding_dict_text(
    item: dict[str, Any],
    values: dict[str, str],
    *,
    critical: bool,
    escalation: bool = False,
) -> str:
    happened = values.get("what_happened") or values.get("fact") or values.get("title") or values.get("summary") or values.get("description")
    evidence = values.get("supporting_evidence") or values.get("detail") or values.get("reason")
    matters = values.get("why_it_matters") or values.get("inference")
    confidence = values.get("confidence") or ("medium" if critical else "")
    action = values.get("recommended_action") or values.get("action")
    if escalation:
        immediate = happened or evidence or "This item requires analyst review"
        next_action = _recommendation_action(action or "Review related firewall and authentication activity")
        why_wait = matters or evidence or "available severity and activity context indicate this should be reviewed before the shift handoff is closed"
        urgency = values.get("urgency") or "same-shift"
        evidence_basis = f" Evidence basis: {evidence}." if evidence else ""
        return (
            f"Immediate attention: {immediate}. "
            f"Next action: {next_action}. "
            f"Why this cannot wait: {why_wait}. "
            f"Urgency: {urgency}.{evidence_basis}"
        )
    parts = []
    if happened:
        parts.append(f"What happened: {happened}")
    if evidence:
        parts.append(f"Supporting evidence: {evidence}")
    if matters:
        parts.append(f"Why it matters: {matters}")
    if confidence:
        parts.append(f"Confidence: {_confidence_text(confidence, evidence=evidence, matters=matters)}")
    if action:
        parts.append(f"Recommended action: {_recommendation_action(action)}")
    if parts:
        return ". ".join(part.strip().rstrip(".") for part in parts) + "."
    return _unknown_dict_text("critical_findings" if critical else "escalations", values or _unknown_scalar_values(item))


def _low_priority_dict_text(item: dict[str, Any], values: dict[str, str]) -> str:
    happened = values.get("what_happened") or values.get("fact") or values.get("title") or values.get("summary") or values.get("description")
    reason = values.get("reason") or values.get("inference") or values.get("uncertainty")
    action = values.get("recommended_action") or values.get("action")
    if happened and reason:
        text = f"Downgraded: {happened}. Reason: {reason}."
        if action:
            text += f" Watch condition: {_recommendation_action(action)}."
        return text
    return _unknown_dict_text("dismissed_low_priority_findings", values or _unknown_scalar_values(item))


def _alert_review_dict_text(item: dict[str, Any], values: dict[str, str]) -> str:
    happened = values.get("what_happened") or values.get("fact") or values.get("title") or values.get("summary") or values.get("description")
    judgment = values.get("analyst_judgment") or values.get("inference")
    if happened and judgment:
        return f"Reviewed activity: {happened}. Analyst judgment: {judgment}."
    if happened:
        return f"Reviewed activity: {happened}."
    return _unknown_dict_text("alerts_reviewed", values or _unknown_scalar_values(item))


def _unknown_dict_text(section_key: str, values: dict[str, str]) -> str:
    scalar_values = []
    for value in values.values():
        cleaned = _sanitize_analyst_text(value)
        if cleaned and not _has_internal_analyst_term(cleaned):
            scalar_values.append(cleaned)
    if scalar_values:
        return f"{_section_prefix(section_key)} {'; '.join(scalar_values[:4])}."
    return _empty_section_judgment(section_key)


def _unknown_scalar_values(value: Any) -> dict[str, str]:
    scalars = _extract_scalar_values(value)
    return {str(index): scalar for index, scalar in enumerate(scalars)}


def _extract_scalar_values(value: Any, *, depth: int = 0) -> list[str]:
    if depth > 4:
        return []
    if isinstance(value, dict):
        results: list[str] = []
        for key, nested in value.items():
            if _internal_field_name(str(key)):
                continue
            results.extend(_extract_scalar_values(nested, depth=depth + 1))
        return results
    if isinstance(value, (list, tuple, set)):
        results: list[str] = []
        for nested in value:
            results.extend(_extract_scalar_values(nested, depth=depth + 1))
        return results
    cleaned = _sanitize_analyst_text(value)
    return [cleaned] if cleaned and not _has_internal_analyst_term(cleaned) else []


def _internal_field_name(key: str) -> bool:
    normalized = str(key or "").lower()
    return any(
        term in normalized
        for term in (
            "dedup_key",
            "idempotency_key",
            "source_path",
            "tool_name",
            "record_ids",
            "fingerprint",
            "storage",
            "lifecycle",
            "content_status",
            "run_id",
            "window_id",
            "schedule_id",
        )
    )


def _sanitize_analyst_text(value: Any, *, field_name: str | None = None) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, (dict, list, tuple, set)):
        scalars = _extract_scalar_values(value)
        return "; ".join(scalars[:4])
    text = str(value).strip()
    if not text:
        return ""
    if field_name == "type":
        text = _friendly_observation_type(text)
    text = text.replace("_", " ")
    text = re.sub(r"/(?:alerts|incidents|events|recon|response-registry)/\d+(?:/[\w.-]+)?", "", text)
    text = re.sub(r"\b(?:get_alert_detail|get_related_events|get_incident_timeline|get_response_registry_context)\b", "", text)
    text = re.sub(r"\b(?:dedup key|source path|tool name|record ids|record count|idempotency key)\b\s*[:=]?\s*\S*", "", text, flags=re.IGNORECASE)
    text = text.replace("{", "").replace("}", "").replace("[", "").replace("]", "")
    text = text.replace("'", "").replace('"', "")
    text = " ".join(text.split())
    text = re.sub(r"([.!?]){2,}", r"\1", text)
    text = re.sub(r"\s+([.!?,;:])", r"\1", text)
    return text.strip(" ,:;")


def _section_prefix(section_key: str) -> str:
    return {
        "alerts_reviewed": "Reviewed activity:",
        "dismissed_low_priority_findings": "Downgraded finding:",
        "escalations": "Escalation note:",
        "critical_findings": "Finding:",
        "evidence": "Evidence showed:",
        "recommendations": "Recommended action:",
    }.get(section_key, "Briefing note:")


def _empty_section_judgment(section_key: str) -> str:
    return {
        "alerts_reviewed": "No alerts or related security activity stood out during this briefing window.",
        "dismissed_low_priority_findings": "No low-priority findings were separated out; there was not enough benign or duplicate context to downgrade a specific item.",
        "escalations": "No escalation is warranted from the reviewed evidence because there is no confirmed impact or urgent analyst-attention signal.",
        "critical_findings": "No critical findings. The reviewed activity lacked exploitation, successful authentication, or evidence of impact.",
        "evidence": "No detailed evidence was available for this briefing window. Treat the judgment as limited until alert details, related events, endpoint telemetry, or authentication outcomes are reviewed.",
        "recommendations": "Next action: collect alert detail, related events, endpoint telemetry, and authentication outcomes before escalating.",
    }.get(section_key, "No analyst-facing detail was available for this section.")


def _friendly_observation_type(value: Any) -> str:
    text = str(value or "").replace("_", " ").strip()
    text = re.sub(r"\b(pfsense)\b", "pfSense", text, flags=re.IGNORECASE)
    return " ".join(text.split()) or "Security evidence"


def _recommendation_action(value: Any) -> str:
    text = _sanitize_analyst_text(value)
    if not text:
        return "Review related security evidence"
    lowered = text.lower()
    if "inspect network logs" in lowered or lowered == "inspect logs":
        return "Review firewall and authentication logs"
    if re.fullmatch(r"review (?:the )?source ip", lowered):
        return "Review firewall activity"
    if re.fullmatch(r"review (?:the )?destination host", lowered):
        return "Review destination-host activity"
    if lowered.startswith("inspect "):
        return "Review " + text[8:]
    if lowered.startswith("investigate "):
        return "Review " + text[12:]
    return text[0].upper() + text[1:]


def _target_phrase(target: str | None, *, action: str = "") -> str:
    if not target:
        return ""
    target = _sanitize_analyst_text(target)
    if not target:
        return ""
    normalized_target = " ".join(re.findall(r"[a-z0-9]+", target.lower()))
    normalized_action = " ".join(re.findall(r"[a-z0-9]+", action.lower()))
    if normalized_target and normalized_target in normalized_action:
        return ""
    try:
        address = ipaddress.ip_address(target)
    except ValueError:
        address = None
    if address is not None:
        return f" associated with source IP {target}"
    try:
        network = ipaddress.ip_network(target, strict=False)
    except ValueError:
        network = None
    if network is not None:
        return f" associated with subnet {target}"
    if re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9][a-z0-9-]{0,62}", target, flags=re.IGNORECASE):
        return f" associated with host {target}"
    if re.fullmatch(r"(?:user(?:name)?|account)\s+[a-z0-9._@\\/-]+", target, flags=re.IGNORECASE):
        return f" for {target}"
    return ""


def _confidence_text(confidence: str, *, evidence: str | None, matters: str | None) -> str:
    text = _sanitize_analyst_text(confidence)
    if not text:
        text = "Medium"
    if any(term in text.lower() for term in ("because", "but", "observed", "evidence", "successful", "confirmed", "available")):
        return text[0].upper() + text[1:]
    rationale = (evidence or matters or "").rstrip(".!? ")
    if rationale:
        return f"{text[0].upper() + text[1:]} - {rationale}, but no confirmed exploitation or successful follow-up is shown in the reviewed evidence."
    return f"{text[0].upper() + text[1:]} - available evidence supports review, but does not confirm exploitation or impact."


def _alerts_reviewed_texts(selected: list[InvestigationCandidate]) -> list[str]:
    if not selected:
        return ["No alerts or related entities were selected for detailed review in this briefing window."]
    items = []
    by_source: dict[str, list[InvestigationCandidate]] = {}
    for candidate in selected:
        if candidate.source_ip:
            by_source.setdefault(_display_ip(candidate.source_ip), []).append(candidate)
    for source_ip, candidates in sorted(by_source.items()):
        if len(candidates) > 1:
            labels = ", ".join(candidate.label for candidate in candidates[:4])
            items.append(f"Correlation: {_count_word(len(candidates)).capitalize()} related item(s) share source IP {source_ip}, including {labels}.")
    for candidate in selected:
        source = f" from source IP {_display_ip(candidate.source_ip)}" if candidate.source_ip else ""
        items.append(f"Reviewed {candidate.entity_type} {candidate.entity_id}: {candidate.label}{source}.")
    return items


def _critical_finding_text(candidate: InvestigationCandidate, evidence_refs: list[dict[str, Any]]) -> str:
    evidence = _best_evidence_phrase(candidate, evidence_refs)
    source = f" from source IP {_display_ip(candidate.source_ip)}" if candidate.source_ip else ""
    if candidate.source_ip:
        next_action = f"review firewall and authentication activity associated with source IP {_display_ip(candidate.source_ip)} before considering containment"
    else:
        next_action = "correlate the alert with related firewall and authentication outcomes before considering containment"
    return (
        f"What happened: {candidate.label}{source} appeared during the briefing window. "
        "Why it matters: critical severity can indicate activity that may affect protected assets or require fast triage if correlated with successful outcomes. "
        f"Supporting evidence: {evidence}. "
        "Confidence: Medium - critical alert severity and supporting evidence justify same-shift review, but no confirmed exploitation or successful follow-up is shown in the reviewed context. "
        f"Recommended action: {next_action}."
    )


def _escalation_text(candidate: InvestigationCandidate, evidence_refs: list[dict[str, Any]]) -> str:
    evidence = _best_evidence_phrase(candidate, evidence_refs)
    urgency = "immediate" if str(candidate.metadata.get("severity") or "").lower() == "critical" or str(candidate.metadata.get("priority") or "") == "P1" else "same-shift"
    source = f" Source IP: {_display_ip(candidate.source_ip)}." if candidate.source_ip else "."
    return (
        f"Immediate attention: {candidate.label}{source} "
        f"Next action: review firewall and authentication activity tied to this item before closing the handoff. "
        f"Why this cannot wait: severity or priority indicates the next analyst should confirm whether the activity progressed beyond blocked or denied attempts. "
        f"Urgency: {urgency}. Evidence basis: {evidence}."
    )


def _low_priority_text(item: dict[str, Any]) -> str:
    label = item.get("label") or item.get("entity_id") or "candidate"
    reason = item.get("reason") or "insufficient evidence"
    source = f" Source IP {_display_ip(item.get('source_ip'))}." if item.get("source_ip") else ""
    return f"Downgraded {label} because it was classified as {reason}; this can wait unless new related evidence appears.{source}"


def _evidence_ref_text(ref: dict[str, Any]) -> str:
    path = str(ref.get("source_path") or "")
    learned = _evidence_source_path_text(path)
    truncated = " The result was truncated, so absence of additional rows should not be treated as proof of absence." if ref.get("truncated") else ""
    return f"{learned}{truncated}"


def _recommendation_texts(selected: list[InvestigationCandidate], evidence_refs: list[dict[str, Any]], message: str) -> list[str]:
    recommendations: list[str] = []
    source_ips = sorted({_display_ip(candidate.source_ip) for candidate in selected if candidate.source_ip})
    if source_ips:
        recommendations.append(
            f"Review firewall activity associated with source IP {source_ips[0]} to determine whether additional reconnaissance or follow-up connections occurred."
        )
    if evidence_refs:
        recommendations.append(
            "Confirm whether the observed pattern has successful outcomes or only blocked/denied activity before escalating or opening containment work."
        )
    if not recommendations:
        recommendations.append(f"Use the briefing limitation as the next step: {message} Re-run with available alert, endpoint, or authentication evidence before making containment decisions.")
    return recommendations


def _best_evidence_phrase(candidate: InvestigationCandidate, evidence_refs: list[dict[str, Any]]) -> str:
    for ref in evidence_refs:
        path = str(ref.get("source_path") or "")
        record_ids = {str(item) for item in ref.get("record_ids") or []}
        if candidate.entity_id in record_ids or candidate.entity_id in path:
            return _evidence_source_path_text(path)
    if evidence_refs:
        ref = evidence_refs[0]
        return _evidence_source_path_text(str(ref.get("source_path") or ""))
    return f"{candidate.entity_type} {candidate.entity_id} was present in the briefing context, but no detailed evidence was available"


def _evidence_source_path_text(path: str) -> str:
    match = re.search(r"/alerts/(\d+)", str(path or ""))
    if match:
        return f"Alert {match.group(1)} showed activity that matched the briefing concern; the reviewed context did not show confirmed exploitation or successful authentication."
    match = re.search(r"/incidents/(\d+)", str(path or ""))
    if match:
        return f"Incident {match.group(1)} provided timeline context for the briefing concern; review is still evidence-gated because impact was not confirmed."
    if path:
        return "A supporting security record was reviewed, but it did not provide enough analyst-facing detail to prove impact."
    return "Supporting evidence was available, but the briefing context did not include enough detail to describe impact."


def _friendly_label(label: str) -> str:
    text = str(label or "").replace("_", " ").strip()
    text = re.sub(r"\b(pfsense|firewall)\b", "", text, flags=re.IGNORECASE)
    text = " ".join(text.split())
    return text or "security"


def _plural_activity(label: str, count: int) -> str:
    text = str(label or "security alert").strip()
    if count == 1:
        return text
    if text.endswith("y"):
        return text[:-1] + "ies"
    if text.endswith("s"):
        return text
    return text + "s"


def _count_word(value: int) -> str:
    words = {
        0: "no",
        1: "one",
        2: "two",
        3: "three",
        4: "four",
        5: "five",
    }
    return words.get(value, str(value))


def _display_ip(value: Any) -> str:
    return str(value or "").split("/", 1)[0]


def _parse_structured_response(content: str | None) -> dict[str, Any] | None:
    parsed, _errors = _validate_structured_response(content)
    return parsed


def _validate_structured_response(content: str | None) -> tuple[dict[str, Any] | None, list[str]]:
    if not content:
        return None, ["AI briefing response was empty."]
    payload = _parse_json_object(content)
    if not isinstance(payload, dict):
        return None, ["AI briefing response was not valid JSON."]
    errors = _structured_briefing_errors(payload)
    if errors:
        return None, errors
    return payload, []


def _parse_json_object(content: str | None) -> dict[str, Any] | None:
    if not content:
        return None
    text = str(content).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return payload if isinstance(payload, dict) else None


def _structured_briefing_errors(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload.get("summary"), str):
        errors.append("summary must be a string")
    sections = payload.get("sections")
    if not isinstance(sections, dict):
        return [*errors, "sections must be an object"]
    for key in BRIEFING_SECTIONS:
        if key not in sections:
            errors.append(f"sections.{key} is required")
        elif not isinstance(sections.get(key), list):
            errors.append(f"sections.{key} must be an array")
    return errors


def _attempt_structured_briefing_repair(
    gateway: AiGateway,
    *,
    original_content: str | None,
    validation_errors: list[str],
    profile_name: str,
):
    bounded_original = str(original_content or "")[:2400]
    bounded_errors = validation_errors[:8]
    repair_prompt = (
        "Repair this scheduled SOC briefing response. Return exactly one JSON object and no markdown.\n"
        "Do not invent evidence, alerts, incidents, trends, conclusions, or actions. Use only the original response content.\n"
        "The response must be read-only advisory content and must not claim anything was saved, applied, approved, executed, "
        "blocked, deployed, committed, or changed.\n"
        f"Required section keys: {json.dumps(list(BRIEFING_SECTIONS), sort_keys=True)}\n"
        "Required schema: {\"summary\":\"string\",\"sections\":{"
        "\"alerts_reviewed\":[{\"what_happened\":\"string\",\"supporting_evidence\":\"string\",\"analyst_judgment\":\"string\"}],"
        "\"dismissed_low_priority_findings\":[{\"what_happened\":\"string\",\"supporting_evidence\":\"string\",\"reason\":\"string\",\"recommended_action\":\"string\"}],"
        "\"escalations\":[{\"what_happened\":\"string\",\"supporting_evidence\":\"string\",\"why_it_matters\":\"string\",\"urgency\":\"string\",\"recommended_action\":\"string\"}],"
        "\"critical_findings\":[{\"what_happened\":\"string\",\"supporting_evidence\":\"string\",\"why_it_matters\":\"string\",\"confidence\":\"string\",\"recommended_action\":\"string\"}],"
        "\"evidence\":[{\"fact\":\"string\",\"inference\":\"string\",\"uncertainty\":\"string\",\"missing_evidence\":\"string\"}],"
        "\"recommendations\":[{\"recommended_action\":\"string\",\"target\":\"string\",\"reason\":\"string\",\"priority\":\"string\"}]}}\n"
        "Do not include raw dictionaries, source paths, tool names, record counts, dedup keys, or implementation metadata in section prose.\n"
        f"Validation errors: {json.dumps(bounded_errors, sort_keys=True)}\n"
        f"Original response:\n{bounded_original}\n"
    )
    repaired = gateway.generate(
        AiGatewayRequest(
            prompt=repair_prompt,
            capability="scheduled_soc_briefing",
            profile=profile_name,
            metadata={
                "service_actor": SERVICE_ACTOR,
                "read_only": True,
                "action": "soc_briefing_repair",
                "repair_attempt": 1,
                "no_actions": True,
            },
        )
    )
    return repaired if repaired.status == AI_STATUS_SUCCESS else None


def _budget_exhausted(
    conn,
    run: dict[str, Any],
    code: str,
    evidence_refs: list[dict[str, Any]],
) -> InvestigationOutcome:
    message = "Scheduled investigation runtime budget was exhausted."
    create_run_step(
        conn,
        int(run["id"]),
        step_index=98,
        step_type="budget_guard",
        status=STEP_STATUS_PARTIAL,
        sanitized_input={"error_code": code},
        evidence_refs=evidence_refs,
        decision_summary=message,
        error_code=code,
        error_message=message,
    )
    sections = _deterministic_sections(selected=[], skipped=[], evidence_refs=evidence_refs, message=message)
    update_briefing_content(
        conn,
        run,
        status="partial",
        lifecycle_status="content_ready",
        content_status="ready",
        summary=message,
        sections=sections,
        evidence_refs=evidence_refs,
        error_code=code,
        error_message=message,
    )
    return InvestigationOutcome(
        run_status=RUN_STATUS_PARTIAL,
        job_status="partial",
        window_status="partial",
        briefing_status="partial",
        lifecycle_status="content_ready",
        content_status="ready",
        summary=message,
        sections=sections,
        evidence_refs=evidence_refs,
        ai_gateway_status="budget_exhausted",
        error_code=code,
        error_message=message,
    )


def _persist_step(
    conn,
    run: dict[str, Any],
    step_index: int,
    step_type: str,
    status: str,
    sanitized_input: dict[str, Any],
    evidence_refs: list[dict[str, Any]],
    decision_summary: str,
    *,
    latency_ms: int = 0,
    error_code: str | None = None,
    error_message: str | None = None,
    tool_name: str | None = None,
) -> None:
    create_run_step(
        conn,
        int(run["id"]),
        step_index=step_index,
        step_type=step_type,
        status=status,
        tool_name=tool_name,
        sanitized_input=sanitized_input,
        evidence_refs=evidence_refs,
        decision_summary=decision_summary,
        latency_ms=latency_ms,
        error_code=error_code,
        error_message=error_message,
    )


def _audit(conn, run: dict[str, Any], phase: str, details: dict[str, Any]) -> None:
    record_scheduled_investigation_audit(
        conn,
        event_type=EVENT_AUDIT,
        run_id=int(run["id"]),
        schedule_id=int(run["schedule_id"]),
        window_id=int(run["window_id"]),
        details={"phase": phase, **details},
    )


def _window_ref(window: dict[str, Any]) -> dict[str, Any]:
    return {
        "window_id": window["id"],
        "window_start": _iso(window["window_start"]),
        "window_end": _iso(window["window_end"]),
        "coalesced": bool(window.get("coalesced")),
    }


def _iso(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _bounded_text(value: Any, limit: int) -> str | None:
    if value in (None, ""):
        return None
    return str(value)[: max(1, limit)]


def _deadline_reached(deadline: float) -> bool:
    return time.monotonic() >= deadline


__all__ = [
    "BRIEFING_SECTIONS",
    "EVENT_AUDIT",
    "InvestigationBudget",
    "InvestigationCandidate",
    "InvestigationOutcome",
    "plan_investigation_candidates",
    "run_scheduled_investigation",
]
