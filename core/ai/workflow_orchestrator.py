from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from core.ai.config import AiGatewayConfig
from core.ai.drafting_service import DraftServiceResult, create_draft
from core.ai.explainer_service import AiContextError, AiServiceResult, chat_about_siem, explain_context
from core.ai.gateway import AiGateway
from core.ai.investigation_service import InvestigationServiceResult, run_investigation
from core.ai.profile_registry import (
    AI_PROFILE_DEEP_BRIEFING,
    AI_PROFILE_DEVELOPER_ASSISTANT,
    AI_PROFILE_FAST_TRIAGE,
    AI_PROFILE_GUIDED_ANALYSIS,
)

WORKFLOW_AUTO = "auto"
WORKFLOW_QUICK_EXPLAIN = "quick_explain"
WORKFLOW_DEEP_INVESTIGATE = "deep_investigate"
WORKFLOW_DECISION_SUPPORT = "decision_support"
WORKFLOW_GENERATE_ARTIFACT = "generate_artifact"
WORKFLOW_SOC_BRIEFING = "soc_briefing"
WORKFLOW_REPO_ASSISTANT = "repo_assistant"

CANONICAL_WORKFLOWS = frozenset(
    {
        WORKFLOW_QUICK_EXPLAIN,
        WORKFLOW_DEEP_INVESTIGATE,
        WORKFLOW_DECISION_SUPPORT,
        WORKFLOW_GENERATE_ARTIFACT,
        WORKFLOW_SOC_BRIEFING,
        WORKFLOW_REPO_ASSISTANT,
    }
)

NORMAL_AUTO_WORKFLOWS = frozenset(
    {
        WORKFLOW_QUICK_EXPLAIN,
        WORKFLOW_DEEP_INVESTIGATE,
        WORKFLOW_DECISION_SUPPORT,
        WORKFLOW_GENERATE_ARTIFACT,
    }
)

WORKFLOW_PROFILES = {
    WORKFLOW_QUICK_EXPLAIN: AI_PROFILE_FAST_TRIAGE,
    WORKFLOW_DEEP_INVESTIGATE: AI_PROFILE_GUIDED_ANALYSIS,
    WORKFLOW_DECISION_SUPPORT: AI_PROFILE_GUIDED_ANALYSIS,
    WORKFLOW_GENERATE_ARTIFACT: AI_PROFILE_GUIDED_ANALYSIS,
    WORKFLOW_SOC_BRIEFING: AI_PROFILE_DEEP_BRIEFING,
    WORKFLOW_REPO_ASSISTANT: AI_PROFILE_DEVELOPER_ASSISTANT,
}

WORKFLOW_LATENCY_TARGETS = {
    WORKFLOW_QUICK_EXPLAIN: {"mode": "sync", "p50_seconds": 3, "p95_seconds": 8},
    WORKFLOW_DEEP_INVESTIGATE: {"mode": "polling", "first_stage_seconds": 1, "completion_seconds": [45, 90]},
    WORKFLOW_DECISION_SUPPORT: {"mode": "sync", "p50_seconds": 6, "p95_seconds": 15},
    WORKFLOW_GENERATE_ARTIFACT: {"mode": "sync", "p50_seconds": 8, "p95_seconds": 20},
    WORKFLOW_SOC_BRIEFING: {"mode": "job", "target": "job_lifecycle"},
    WORKFLOW_REPO_ASSISTANT: {"mode": "sync", "p50_seconds": 8, "p95_seconds": 20},
}

LIFECYCLE_GATHERING_CONTEXT = "gathering_context"
LIFECYCLE_RETRIEVING_RELATED_EVIDENCE = "retrieving_related_evidence"
LIFECYCLE_QUERYING_APPROVED_TOOLS = "querying_approved_tools"
LIFECYCLE_PREPARING_EVIDENCE = "preparing_evidence"
LIFECYCLE_GENERATING_ANALYSIS = "generating_analysis"
LIFECYCLE_VALIDATING_RESPONSE = "validating_response"
LIFECYCLE_COMPLETE = "complete"

DEEP_INVESTIGATE_LIFECYCLE_STAGES = (
    LIFECYCLE_GATHERING_CONTEXT,
    LIFECYCLE_RETRIEVING_RELATED_EVIDENCE,
    LIFECYCLE_QUERYING_APPROVED_TOOLS,
    LIFECYCLE_PREPARING_EVIDENCE,
    LIFECYCLE_GENERATING_ANALYSIS,
    LIFECYCLE_VALIDATING_RESPONSE,
    LIFECYCLE_COMPLETE,
)

DECISION_RECOMMENDATIONS = frozenset({"block", "monitor", "escalate", "ignore", "gather_more_evidence"})

DECISION_ACTIONS = frozenset(
    {
        "recommend_investigation",
        "recommend_next_steps",
        "assess_reconnaissance",
        "investigate_cluster",
        "suggestedactions",
    }
)

PRIVILEGED_OR_MUTATING_TERMS = frozenset(
    {
        "apply",
        "approve",
        "briefing",
        "commit",
        "confirm",
        "deploy",
        "execute",
        "repo",
        "repository",
        "restart",
        "run briefing",
        "save",
        "soc briefing",
        "ssh",
        "vm",
    }
)


class WorkflowValidationError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400, error_code: str = "invalid_workflow_request"):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


@dataclass(frozen=True)
class WorkflowClassification:
    requested_workflow: str
    classified_workflow: str
    confidence: str
    reason: str
    chooser_required: bool = False
    allowed_workflows: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkflowResult:
    payload: dict[str, Any]
    status_code: int = 200


def run_workflow(
    payload: dict[str, Any],
    *,
    gateway: AiGateway | None = None,
    config: AiGatewayConfig | None = None,
) -> WorkflowResult:
    if not isinstance(payload, dict):
        raise WorkflowValidationError("JSON object body is required.")

    classification = classify_workflow(payload)
    if classification.chooser_required:
        return WorkflowResult(
            _envelope(
                status="chooser_required",
                workflow=classification.classified_workflow,
                classification=classification,
                result={
                    "allowed_workflows": list(classification.allowed_workflows),
                    "message": "Choose an allowed Anakin workflow before continuing.",
                },
                metadata={},
                lifecycle=_sync_lifecycle("chooser_required"),
                error=None,
            ),
            200,
        )

    workflow = classification.classified_workflow
    if workflow == WORKFLOW_QUICK_EXPLAIN:
        service_result = _run_quick_explain(payload, gateway=gateway, config=config)
        return _canonical_from_service(service_result, workflow=workflow, classification=classification)
    if workflow == WORKFLOW_DEEP_INVESTIGATE:
        service_result = _run_deep_investigate(payload, gateway=gateway, config=config)
        return _canonical_from_service(
            service_result,
            workflow=workflow,
            classification=classification,
            lifecycle=_deep_lifecycle(service_result.payload.get("investigation")),
        )
    if workflow == WORKFLOW_DECISION_SUPPORT:
        service_result = _run_decision_support(payload, gateway=gateway, config=config)
        return _canonical_from_service(service_result, workflow=workflow, classification=classification)
    if workflow == WORKFLOW_GENERATE_ARTIFACT:
        service_result = _run_generate_artifact(payload, gateway=gateway, config=config)
        return _canonical_from_service(service_result, workflow=workflow, classification=classification)

    raise WorkflowValidationError(
        f"Workflow {workflow} is only available through its explicit capability route.",
        status_code=403,
        error_code="workflow_not_available_from_normal_route",
    )


def legacy_explain_context(
    payload: dict[str, Any],
    *,
    gateway: AiGateway | None = None,
    config: AiGatewayConfig | None = None,
) -> AiServiceResult:
    classification = classify_workflow({**(payload or {}), "workflow": _workflow_for_legacy_explain(payload)})
    if classification.classified_workflow == WORKFLOW_DECISION_SUPPORT:
        result = _run_decision_support(payload, gateway=gateway, config=config)
    else:
        result = explain_context(payload, gateway=gateway, config=config)
    return AiServiceResult(
        _with_workflow_metadata(result.payload, workflow=classification.classified_workflow, classification=classification),
        result.status_code,
    )


def legacy_chat_about_siem(
    payload: dict[str, Any],
    *,
    gateway: AiGateway | None = None,
    config: AiGatewayConfig | None = None,
) -> AiServiceResult:
    classification = classify_workflow(
        {
            "workflow": WORKFLOW_AUTO,
            "prompt": (payload or {}).get("message"),
            "context_type": "general",
            "context": (payload or {}).get("visible_context") if isinstance((payload or {}).get("visible_context"), dict) else {},
        }
    )
    if classification.chooser_required or classification.classified_workflow == WORKFLOW_QUICK_EXPLAIN:
        result = chat_about_siem(payload, gateway=gateway, config=config)
    elif classification.classified_workflow == WORKFLOW_DECISION_SUPPORT:
        result = _run_decision_support(
            {
                "context_type": "general",
                "context": (payload or {}).get("visible_context") if isinstance((payload or {}).get("visible_context"), dict) else {},
                "prompt": (payload or {}).get("message") or "",
            },
            gateway=gateway,
            config=config,
        )
    elif classification.classified_workflow == WORKFLOW_DEEP_INVESTIGATE:
        result = _run_deep_investigate(
            {
                "context_type": "general",
                "context": (payload or {}).get("visible_context") if isinstance((payload or {}).get("visible_context"), dict) else {},
                "prompt": (payload or {}).get("message") or "",
                "tool_policy": (payload or {}).get("tool_policy"),
                "allow_automatic_draft": False,
            },
            gateway=gateway,
            config=config,
        )
        return AiServiceResult(
            _chat_shape_from_investigation(result.payload, classification=classification),
            result.status_code,
        )
    else:
        result = chat_about_siem(payload, gateway=gateway, config=config)
    return AiServiceResult(
        _with_workflow_metadata(result.payload, workflow=classification.classified_workflow, classification=classification),
        result.status_code,
    )


def legacy_create_draft(
    payload: dict[str, Any],
    *,
    gateway: AiGateway | None = None,
    config: AiGatewayConfig | None = None,
) -> DraftServiceResult:
    classification = WorkflowClassification(
        requested_workflow=WORKFLOW_GENERATE_ARTIFACT,
        classified_workflow=WORKFLOW_GENERATE_ARTIFACT,
        confidence="high",
        reason="Legacy draft route maps directly to Generate Artifact.",
    )
    result = create_draft(payload, gateway=gateway, config=config)
    return DraftServiceResult(
        _with_workflow_metadata(result.payload, workflow=WORKFLOW_GENERATE_ARTIFACT, classification=classification),
        result.status_code,
    )


def legacy_run_investigation(
    payload: dict[str, Any],
    *,
    gateway: AiGateway | None = None,
    config: AiGatewayConfig | None = None,
) -> InvestigationServiceResult:
    classification = WorkflowClassification(
        requested_workflow=WORKFLOW_DEEP_INVESTIGATE,
        classified_workflow=WORKFLOW_DEEP_INVESTIGATE,
        confidence="high",
        reason="Legacy investigation route maps directly to Deep Investigate.",
    )
    result = run_investigation(payload, gateway=gateway, config=config)
    enriched = _with_workflow_metadata(result.payload, workflow=WORKFLOW_DEEP_INVESTIGATE, classification=classification)
    enriched["lifecycle"] = _deep_lifecycle(result.payload.get("investigation"))
    return InvestigationServiceResult(enriched, result.status_code)


def workflow_for_inventory_path(backend_path: str, selector_type: str, selector: str) -> str:
    if backend_path == "POST /ai/workflows":
        if selector in CANONICAL_WORKFLOWS:
            return str(selector)
        return WORKFLOW_QUICK_EXPLAIN
    if backend_path == "POST /ai/drafts":
        return WORKFLOW_GENERATE_ARTIFACT
    if backend_path == "POST /ai/investigations":
        return WORKFLOW_DEEP_INVESTIGATE
    if backend_path in {"POST /ai/repo/chat", "POST /ai/repo/requests"}:
        return WORKFLOW_REPO_ASSISTANT
    if backend_path == "soc_briefing_worker":
        return WORKFLOW_SOC_BRIEFING
    if backend_path == "POST /ai/chat":
        return WORKFLOW_QUICK_EXPLAIN
    if backend_path == "POST /ai/actions/preview":
        return WORKFLOW_GENERATE_ARTIFACT
    if selector_type == "explain_action" and str(selector or "").lower() in DECISION_ACTIONS:
        return WORKFLOW_DECISION_SUPPORT
    return WORKFLOW_QUICK_EXPLAIN


def classify_workflow(payload: dict[str, Any]) -> WorkflowClassification:
    requested = str(payload.get("workflow") or WORKFLOW_AUTO).strip().lower() or WORKFLOW_AUTO
    prompt = str(payload.get("prompt") or payload.get("question") or payload.get("message") or payload.get("instruction") or "")
    text = " ".join(
        [
            prompt,
            str(payload.get("action") or ""),
            str(payload.get("draft_type") or payload.get("draftType") or ""),
            str(payload.get("artifact_type") or ""),
        ]
    ).lower()

    if requested != WORKFLOW_AUTO:
        if requested not in CANONICAL_WORKFLOWS:
            raise WorkflowValidationError("workflow is unsupported.", error_code="unsupported_workflow")
        if requested in {WORKFLOW_SOC_BRIEFING, WORKFLOW_REPO_ASSISTANT}:
            return WorkflowClassification(
                requested_workflow=requested,
                classified_workflow=requested,
                confidence="high",
                reason="Explicit privileged workflow must be handled by its dedicated route.",
            )
        return WorkflowClassification(
            requested_workflow=requested,
            classified_workflow=requested,
            confidence="high",
            reason="Client selected an allowed Anakin workflow shortcut.",
        )

    if _mentions_forbidden_auto(text):
        return WorkflowClassification(
            requested_workflow=WORKFLOW_AUTO,
            classified_workflow=WORKFLOW_QUICK_EXPLAIN,
            confidence="low",
            reason="Prompt mentions privileged or mutating capabilities that auto-routing cannot invoke.",
            chooser_required=True,
            allowed_workflows=tuple(sorted(NORMAL_AUTO_WORKFLOWS)),
        )

    if payload.get("draft_type") or payload.get("draftType") or isinstance(payload.get("artifact"), dict):
        return WorkflowClassification(
            requested_workflow=WORKFLOW_AUTO,
            classified_workflow=WORKFLOW_GENERATE_ARTIFACT,
            confidence="high",
            reason="Request includes an artifact or draft type.",
        )
    if payload.get("investigation") is True or any(term in text for term in ("deep investigate", "investigate", "correlate", "evidence gaps", "root cause")):
        return WorkflowClassification(
            requested_workflow=WORKFLOW_AUTO,
            classified_workflow=WORKFLOW_DEEP_INVESTIGATE,
            confidence="high",
            reason="Prompt asks for investigation, correlation, or evidence gaps.",
        )
    if any(term in text for term in ("what should i do", "should i", "recommend", "block or", "monitor or", "escalate", "ignore")):
        return WorkflowClassification(
            requested_workflow=WORKFLOW_AUTO,
            classified_workflow=WORKFLOW_DECISION_SUPPORT,
            confidence="high",
            reason="Prompt asks for a recommendation or analyst decision.",
        )
    if len(text.strip()) < 12:
        return WorkflowClassification(
            requested_workflow=WORKFLOW_AUTO,
            classified_workflow=WORKFLOW_QUICK_EXPLAIN,
            confidence="low",
            reason="Prompt is short or ambiguous, so auto-routing defaults to Quick Explain.",
        )
    return WorkflowClassification(
        requested_workflow=WORKFLOW_AUTO,
        classified_workflow=WORKFLOW_QUICK_EXPLAIN,
        confidence="medium",
        reason="No deeper workflow intent was detected; using Quick Explain.",
    )


def workflow_contracts() -> dict[str, dict[str, Any]]:
    return {
        workflow: {"profile": WORKFLOW_PROFILES[workflow], "latency_target": WORKFLOW_LATENCY_TARGETS[workflow]}
        for workflow in CANONICAL_WORKFLOWS
    }


def _workflow_for_legacy_explain(payload: dict[str, Any] | None) -> str:
    action = str((payload or {}).get("action") or "").strip().lower()
    return WORKFLOW_DECISION_SUPPORT if action in DECISION_ACTIONS else WORKFLOW_QUICK_EXPLAIN


def _run_quick_explain(payload: dict[str, Any], *, gateway: AiGateway | None, config: AiGatewayConfig | None) -> AiServiceResult:
    explain_payload = _explain_payload_from_envelope(payload, action="explain")
    return explain_context(explain_payload, gateway=gateway, config=config)


def _run_decision_support(payload: dict[str, Any], *, gateway: AiGateway | None, config: AiGatewayConfig | None) -> AiServiceResult:
    if _has_artifact_or_mutation_fields(payload):
        raise WorkflowValidationError(
            "Decision Support cannot generate artifacts, preview actions, confirm actions, or mutate state.",
            error_code="decision_support_read_only",
        )
    question = str(payload.get("prompt") or payload.get("question") or payload.get("message") or "").strip()
    action = str(payload.get("action") or "recommend_next_steps").strip().lower()
    if action not in DECISION_ACTIONS:
        action = "recommend_next_steps"
    explain_payload = _explain_payload_from_envelope(
        {
            **payload,
            "prompt": "",
            "question": (
                "First rendered content must be recommendation. Use this exact order: "
                "recommendation, why, evidence, risks, alternatives, what_would_change_my_mind, confidence. "
                "If the analyst's conclusion is not supported, explicitly say you disagree before explaining why. "
                "Recommend whether the analyst should block, monitor, escalate, ignore, or gather more evidence. "
                "Explain reasoning, confidence, prerequisites, risks, alternatives, and missing evidence. "
                "Do not draft artifacts, save anything, preview actions, confirm actions, or claim action was taken. "
                f"Analyst question: {question}"
            ),
        },
        action=action,
    )
    result = explain_context(explain_payload, gateway=gateway, config=config)
    payload_with_decision = dict(result.payload)
    answer, normalized = _recommendation_first_answer(payload_with_decision.get("answer"))
    payload_with_decision["answer"] = answer
    metadata = dict(payload_with_decision.get("metadata") or {})
    metadata.update(
        {
            "decision_support_contract": "recommendation_first",
            "recommendation_first_enforced": normalized,
            "required_sections": [
                "recommendation",
                "why",
                "evidence",
                "risks",
                "alternatives",
                "what_would_change_my_mind",
                "confidence",
            ],
        }
    )
    payload_with_decision["metadata"] = metadata
    payload_with_decision["decision_support"] = {
        "allowed_recommendations": sorted(DECISION_RECOMMENDATIONS),
        "read_only": True,
        "artifacts_generated": False,
        "actions_taken": False,
    }
    return AiServiceResult(payload_with_decision, result.status_code)


def _recommendation_first_answer(answer: Any) -> tuple[Any, bool]:
    if not isinstance(answer, str) or not answer.strip():
        return answer, False
    lines = [line.strip() for line in answer.splitlines() if line.strip()]
    if not lines:
        return answer, False
    if _is_recommendation_line(lines[0]):
        return answer, False
    for index, line in enumerate(lines[1:], start=1):
        if _is_recommendation_line(line):
            reordered = [line, *lines[:index], *lines[index + 1 :]]
            return "\n".join(reordered), True
    return answer, False


def _is_recommendation_line(line: str) -> bool:
    normalized = str(line or "").strip().lower()
    return normalized.startswith(("recommendation", "primary recommendation", "i recommend", "i would", "do not ", "don't "))


def _run_generate_artifact(payload: dict[str, Any], *, gateway: AiGateway | None, config: AiGatewayConfig | None) -> DraftServiceResult:
    artifact = payload.get("artifact") if isinstance(payload.get("artifact"), dict) else {}
    draft_payload = {
        "draft_type": payload.get("draft_type") or payload.get("draftType") or artifact.get("type") or payload.get("artifact_type"),
        "instruction": payload.get("instruction") or payload.get("prompt") or payload.get("question") or "",
        "context_type": payload.get("context_type"),
        "context": _context_from_envelope(payload),
        "use_tools": payload.get("use_tools", True),
        "tool_policy": payload.get("tool_policy"),
        "client_request_id": payload.get("client_request_id"),
    }
    return create_draft(draft_payload, gateway=gateway, config=config)


def _run_deep_investigate(payload: dict[str, Any], *, gateway: AiGateway | None, config: AiGatewayConfig | None) -> InvestigationServiceResult:
    investigation_payload = {
        "context_type": payload.get("context_type"),
        "context": _context_from_envelope(payload),
        "question": payload.get("prompt") or payload.get("question") or payload.get("message") or "",
        "tool_policy": payload.get("tool_policy") or {"max_tool_calls": 5, "time_window_hours": 24},
        "client_request_id": payload.get("client_request_id"),
        "allow_automatic_draft": payload.get("allow_automatic_draft", False),
    }
    return run_investigation(investigation_payload, gateway=gateway, config=config)


def _explain_payload_from_envelope(payload: dict[str, Any], *, action: str) -> dict[str, Any]:
    return {
        "context_type": payload.get("context_type") or "general",
        "action": payload.get("action") or action,
        "question": payload.get("prompt") or payload.get("question") or payload.get("message") or "",
        "context": _context_from_envelope(payload),
        "use_tools": payload.get("use_tools", False),
        "tool_policy": payload.get("tool_policy"),
    }


def _context_from_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    entity = payload.get("entity") if isinstance(payload.get("entity"), dict) else {}
    return {**context, **entity}


def _canonical_from_service(
    service_result,
    *,
    workflow: str,
    classification: WorkflowClassification,
    lifecycle: dict[str, Any] | None = None,
) -> WorkflowResult:
    payload = service_result.payload
    return WorkflowResult(
        _envelope(
            status=str(payload.get("status") or "unknown"),
            workflow=workflow,
            classification=classification,
            result=payload,
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
            lifecycle=lifecycle or _sync_lifecycle("complete"),
            error=payload.get("error"),
        ),
        service_result.status_code,
    )


def _envelope(
    *,
    status: str,
    workflow: str,
    classification: WorkflowClassification,
    result: dict[str, Any],
    metadata: dict[str, Any],
    lifecycle: dict[str, Any],
    error: str | None,
) -> dict[str, Any]:
    return {
        "status": status,
        "workflow": workflow,
        "classification": classification.as_dict(),
        "lifecycle": lifecycle,
        "result": result,
        "metadata": metadata,
        "error": error,
    }


def _with_workflow_metadata(
    payload: dict[str, Any],
    *,
    workflow: str,
    classification: WorkflowClassification,
) -> dict[str, Any]:
    enriched = dict(payload)
    enriched["workflow"] = workflow
    enriched["classification"] = classification.as_dict()
    if workflow == WORKFLOW_DEEP_INVESTIGATE:
        enriched["lifecycle"] = _deep_lifecycle(payload.get("investigation"))
    elif "lifecycle" not in enriched:
        enriched["lifecycle"] = _sync_lifecycle("complete")
    metadata = dict(enriched.get("metadata") or {})
    metadata["workflow"] = workflow
    metadata["classification"] = classification.as_dict()
    enriched["metadata"] = metadata
    return enriched


def _chat_shape_from_investigation(payload: dict[str, Any], *, classification: WorkflowClassification) -> dict[str, Any]:
    investigation = payload.get("investigation") if isinstance(payload.get("investigation"), dict) else {}
    answer = investigation.get("summary") or payload.get("error") or "Deep investigation did not return a summary."
    return _with_workflow_metadata(
        {
            "status": payload.get("status"),
            "answer": answer,
            "insufficient_context": payload.get("status") == "insufficient_context",
            "context": investigation.get("context_snapshot") or {},
            "metadata": {},
            "tools": investigation.get("evidence", {}).get("tools", {}) if isinstance(investigation.get("evidence"), dict) else {},
            "error": payload.get("error"),
        },
        workflow=WORKFLOW_DEEP_INVESTIGATE,
        classification=classification,
    )


def _sync_lifecycle(stage: str) -> dict[str, Any]:
    return {"mode": "sync", "stage": stage, "stages": [{"stage": stage, "status": "complete"}]}


def _deep_lifecycle(investigation: Any) -> dict[str, Any]:
    completed = set()
    failed = set()
    if isinstance(investigation, dict):
        for step in investigation.get("steps") or []:
            if not isinstance(step, dict):
                continue
            status = step.get("status")
            stage = _stage_for_investigation_step(str(step.get("step_type") or ""))
            if status in {"success", "skipped", "complete", "partial"}:
                completed.add(stage)
            elif status in {"failed", "timed_out", "cancelled", "forbidden"}:
                failed.add(stage)
    stage_entries = []
    current = DEEP_INVESTIGATE_LIFECYCLE_STAGES[0]
    for stage in DEEP_INVESTIGATE_LIFECYCLE_STAGES:
        if stage in failed:
            status = "failed"
            current = stage
        elif stage in completed or stage == LIFECYCLE_COMPLETE and isinstance(investigation, dict):
            status = "complete"
            current = stage
        else:
            status = "pending"
        stage_entries.append({"stage": stage, "status": status})
    return {"mode": "polling", "stage": current, "stages": stage_entries}


def _stage_for_investigation_step(step_type: str) -> str:
    if step_type == "build_context":
        return LIFECYCLE_GATHERING_CONTEXT
    if step_type == "plan_read_tools":
        return LIFECYCLE_RETRIEVING_RELATED_EVIDENCE
    if step_type == "execute_read_tool":
        return LIFECYCLE_QUERYING_APPROVED_TOOLS
    if step_type in {"validate_evidence", "correlate_evidence"}:
        return LIFECYCLE_PREPARING_EVIDENCE
    if step_type in {"suggest_response_plan", "generate_transient_draft"}:
        return LIFECYCLE_GENERATING_ANALYSIS
    if step_type == "finalize_summary":
        return LIFECYCLE_VALIDATING_RESPONSE
    return LIFECYCLE_PREPARING_EVIDENCE


def _mentions_forbidden_auto(text: str) -> bool:
    return any(term in text for term in PRIVILEGED_OR_MUTATING_TERMS)


def _has_artifact_or_mutation_fields(payload: dict[str, Any]) -> bool:
    forbidden = {
        "artifact",
        "artifact_type",
        "draft_type",
        "draftType",
        "action_type",
        "confirm",
        "confirmation_token",
        "payload_digest",
        "target_fingerprint",
    }
    return any(key in payload for key in forbidden)


__all__ = [
    "CANONICAL_WORKFLOWS",
    "DEEP_INVESTIGATE_LIFECYCLE_STAGES",
    "NORMAL_AUTO_WORKFLOWS",
    "WORKFLOW_AUTO",
    "WORKFLOW_DEEP_INVESTIGATE",
    "WORKFLOW_DECISION_SUPPORT",
    "WORKFLOW_GENERATE_ARTIFACT",
    "WORKFLOW_QUICK_EXPLAIN",
    "WORKFLOW_REPO_ASSISTANT",
    "WORKFLOW_SOC_BRIEFING",
    "WorkflowValidationError",
    "classify_workflow",
    "legacy_chat_about_siem",
    "legacy_create_draft",
    "legacy_explain_context",
    "legacy_run_investigation",
    "run_workflow",
    "workflow_contracts",
    "workflow_for_inventory_path",
]
