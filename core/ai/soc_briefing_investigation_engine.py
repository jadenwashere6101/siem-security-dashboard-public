from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
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


@dataclass(frozen=True)
class InvestigationBudget:
    max_runtime_seconds: int = 45
    max_entities: int = 8
    max_tool_calls: int = 12
    max_rows_per_tool: int = DEFAULT_TOOL_LIMIT
    max_evidence_refs: int = 40
    max_prompt_chars: int = 8000
    max_prompt_tokens: int = 3000
    max_completion_tokens: int = 800
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
    prompt_payload = {
        "task": "Produce structured read-only scheduled SOC briefing content.",
        "required_sections": list(BRIEFING_SECTIONS),
        "policy": {
            "read_only": True,
            "no_actions": True,
            "no_tool_calls": True,
            "no_sql": True,
            "no_chain_of_thought": True,
        },
        "candidates": [candidate.as_ref() for candidate in selected],
        "skipped": skipped[: budget.max_entities],
        "evidence": tool_summary_for_prompt(evidence_summary, max_chars=budget.max_prompt_chars),
        "evidence_refs": evidence_refs,
        "output_schema": {
            "summary": "string",
            "sections": {key: "array" for key in BRIEFING_SECTIONS},
        },
    }
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
    response = (gateway or AiGateway(config=scheduled_config)).generate(
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
    parsed = _parse_structured_response(response.content)
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
        )
    return {
        "run_status": RUN_STATUS_SUCCESS,
        "job_status": JOB_STATUS_SUCCESS,
        "window_status": "success",
        "briefing_status": "success",
        "content_status": "ready",
        "summary": _bounded_text(parsed.get("summary"), 2000) or "Scheduled SOC briefing generated.",
        "sections": _ensure_sections(parsed.get("sections"), selected=selected, skipped=skipped, evidence_refs=evidence_refs),
        "step_status": STEP_STATUS_SUCCESS,
        "sanitized_input": {"prompt_tokens": tokens, "paid_request": False},
        "decision_summary": "Generated structured advisory scheduled SOC briefing through AI Gateway.",
        "error_code": None,
        "error_message": None,
        "ai_gateway_status": response.status,
        "provider_status": response.metadata.provider,
        "latency_ms": latency_ms,
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
        "sanitized_input": {"prompt_tokens": prompt_tokens, "paid_request": False},
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
    alerts = [candidate.as_ref() for candidate in selected if candidate.entity_type == "alert"]
    critical = [
        candidate.as_ref()
        for candidate in selected
        if str(candidate.metadata.get("severity") or "").lower() == "critical"
    ]
    escalations = [
        candidate.as_ref()
        for candidate in selected
        if str(candidate.metadata.get("severity") or "").lower() in {"critical", "high"}
        or str(candidate.metadata.get("priority") or "") == "P1"
    ]
    dismissed = [item for item in skipped if item.get("reason") == "duplicate_recent_investigation"]
    return {
        "alerts_reviewed": alerts,
        "dismissed_low_priority_findings": dismissed,
        "escalations": escalations,
        "critical_findings": critical,
        "evidence": evidence_refs,
        "recommendations": [
            {
                "title": "Review scheduled SOC briefing evidence",
                "detail": message,
                "advisory": True,
                "read_only": True,
            }
        ],
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
        merged[key] = value if isinstance(value, list) else base[key]
    return redact_sensitive_values(merged)


def _parse_structured_response(content: str | None) -> dict[str, Any] | None:
    if not content:
        return None
    try:
        payload = json.loads(content)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    sections = payload.get("sections")
    if not isinstance(sections, dict):
        return None
    if not all(key in sections for key in BRIEFING_SECTIONS):
        return None
    return payload


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
