from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

INVESTIGATION_STATUS_QUEUED = "queued"
INVESTIGATION_STATUS_RUNNING = "running"
INVESTIGATION_STATUS_CANCELLED = "cancelled"
INVESTIGATION_STATUS_SUCCESS = "success"
INVESTIGATION_STATUS_PARTIAL = "partial"
INVESTIGATION_STATUS_TIMEOUT = "timeout"
INVESTIGATION_STATUS_FAILED = "failed"
INVESTIGATION_STATUS_INSUFFICIENT_CONTEXT = "insufficient_context"

STEP_STATUS_PENDING = "pending"
STEP_STATUS_RUNNING = "running"
STEP_STATUS_SUCCESS = "success"
STEP_STATUS_SKIPPED = "skipped"
STEP_STATUS_FORBIDDEN = "forbidden"
STEP_STATUS_FAILED = "failed"
STEP_STATUS_TIMEOUT = "timed_out"
STEP_STATUS_CANCELLED = "cancelled"
STEP_STATUS_PARTIAL = "partial"
STEP_STATUS_COMPLETE = "complete"

STEP_BUILD_CONTEXT = "build_context"
STEP_PLAN_READ_TOOLS = "plan_read_tools"
STEP_EXECUTE_READ_TOOL = "execute_read_tool"
STEP_VALIDATE_EVIDENCE = "validate_evidence"
STEP_CORRELATE_EVIDENCE = "correlate_evidence"
STEP_SUGGEST_RESPONSE_PLAN = "suggest_response_plan"
STEP_GENERATE_TRANSIENT_DRAFT = "generate_transient_draft"
STEP_FINALIZE_SUMMARY = "finalize_summary"

ALLOWED_STEP_TYPES = frozenset(
    {
        STEP_BUILD_CONTEXT,
        STEP_PLAN_READ_TOOLS,
        STEP_EXECUTE_READ_TOOL,
        STEP_VALIDATE_EVIDENCE,
        STEP_CORRELATE_EVIDENCE,
        STEP_SUGGEST_RESPONSE_PLAN,
        STEP_GENERATE_TRANSIENT_DRAFT,
        STEP_FINALIZE_SUMMARY,
    }
)

WORKFLOW_ALERT = "alert_investigation"
WORKFLOW_INCIDENT = "incident_investigation"
WORKFLOW_SOURCE_IP = "source_ip_investigation"
WORKFLOW_RECON_CLUSTER = "recon_cluster_investigation"
WORKFLOW_RESPONSE_REGISTRY = "response_registry_review"
WORKFLOW_DASHBOARD_ANOMALY = "dashboard_anomaly_review"

ROUTING_SIMPLE = "simple"
ROUTING_STANDARD = "standard"
ROUTING_ADVANCED = "advanced"

DEFAULT_INVESTIGATION_TIMEOUT_SECONDS = 45.0
DEFAULT_STEP_TIMEOUT_SECONDS = 5.0
MAX_WORKFLOW_STEPS = 8
MAX_TOTAL_TOOL_CALLS = 7
MAX_TOOL_CALLS_PER_PASS = 5
MAX_PLANNING_PASSES = 1
MAX_GENERATION_CALLS = 2
MAX_AUTOMATIC_DRAFTS = 1


@dataclass(frozen=True)
class InvestigationStepResult:
    step_type: str
    status: str
    title: str
    detail: str = ""
    sources: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0
    error_code: str | None = None
    read_only: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AiRoutingProfile:
    profile: str
    inputs: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"profile": self.profile, "inputs": dict(self.inputs)}


@dataclass(frozen=True)
class InvestigationObservability:
    status: str
    workflow_type: str
    routing_profile: AiRoutingProfile
    total_latency_ms: int = 0
    planned_step_count: int = 0
    executed_step_count: int = 0
    tool_call_count: int = 0
    tool_statuses: dict[str, int] = field(default_factory=dict)
    source_count: int = 0
    truncated: bool = False
    omitted_count: int = 0
    retry_count: int = 0
    timed_out: bool = False
    cancelled: bool = False
    aggregate_prompt_tokens: int = 0
    aggregate_completion_tokens: int = 0
    aggregate_estimated_cost_usd: float | None = None
    fallback_path: list[dict[str, Any]] = field(default_factory=list)
    automatic_draft_decision: dict[str, Any] = field(default_factory=dict)
    draft_validation_state: dict[str, Any] = field(default_factory=dict)
    provider_responses: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "routing_profile": self.routing_profile.as_dict(),
        }


@dataclass(frozen=True)
class InvestigationRun:
    run_id: str
    status: str
    workflow_type: str
    context_snapshot: dict[str, Any]
    steps: list[InvestigationStepResult]
    summary: str | None
    correlations: list[dict[str, Any]]
    recommendations: list[dict[str, Any]]
    drafts: list[dict[str, Any]]
    evidence: dict[str, Any]
    observability: InvestigationObservability
    labels: dict[str, bool] = field(
        default_factory=lambda: {
            "read_only": True,
            "writes_performed": False,
            "production_action_required_for_changes": True,
        }
    )
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "workflow_type": self.workflow_type,
            "context_snapshot": self.context_snapshot,
            "steps": [step.as_dict() for step in self.steps],
            "summary": self.summary,
            "correlations": list(self.correlations),
            "recommendations": list(self.recommendations),
            "drafts": list(self.drafts),
            "evidence": self.evidence,
            "observability": self.observability.as_dict(),
            "labels": dict(self.labels),
            "error": self.error,
        }


__all__ = [
    "ALLOWED_STEP_TYPES",
    "DEFAULT_INVESTIGATION_TIMEOUT_SECONDS",
    "DEFAULT_STEP_TIMEOUT_SECONDS",
    "InvestigationObservability",
    "InvestigationRun",
    "InvestigationStepResult",
    "AiRoutingProfile",
    "MAX_AUTOMATIC_DRAFTS",
    "MAX_GENERATION_CALLS",
    "MAX_PLANNING_PASSES",
    "MAX_TOOL_CALLS_PER_PASS",
    "MAX_TOTAL_TOOL_CALLS",
    "MAX_WORKFLOW_STEPS",
    "ROUTING_ADVANCED",
    "ROUTING_SIMPLE",
    "ROUTING_STANDARD",
    "STEP_BUILD_CONTEXT",
    "STEP_CORRELATE_EVIDENCE",
    "STEP_EXECUTE_READ_TOOL",
    "STEP_FINALIZE_SUMMARY",
    "STEP_GENERATE_TRANSIENT_DRAFT",
    "STEP_PLAN_READ_TOOLS",
    "STEP_STATUS_CANCELLED",
    "STEP_STATUS_COMPLETE",
    "STEP_STATUS_FAILED",
    "STEP_STATUS_FORBIDDEN",
    "STEP_STATUS_PARTIAL",
    "STEP_STATUS_PENDING",
    "STEP_STATUS_RUNNING",
    "STEP_STATUS_SKIPPED",
    "STEP_STATUS_SUCCESS",
    "STEP_STATUS_TIMEOUT",
    "STEP_SUGGEST_RESPONSE_PLAN",
    "STEP_VALIDATE_EVIDENCE",
    "WORKFLOW_ALERT",
    "WORKFLOW_DASHBOARD_ANOMALY",
    "WORKFLOW_INCIDENT",
    "WORKFLOW_RECON_CLUSTER",
    "WORKFLOW_RESPONSE_REGISTRY",
    "WORKFLOW_SOURCE_IP",
]
