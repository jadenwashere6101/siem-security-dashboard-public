from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import re
from typing import Any

from core.ai.soc_tools import (
    SENSITIVE_KEY_FRAGMENTS,
    has_mutation_intent,
    redact_sensitive_values,
)

DRAFT_STATUS_SUCCESS = "success"
DRAFT_STATUS_INVALID_REQUEST = "invalid_request"
DRAFT_STATUS_UNSUPPORTED_TYPE = "unsupported_draft_type"
DRAFT_STATUS_INSUFFICIENT_CONTEXT = "insufficient_context"
DRAFT_STATUS_PARSE_FAILED = "draft_parse_failed"
DRAFT_STATUS_VALIDATION_FAILED = "draft_validation_failed"

DEFAULT_DRAFT_LABELS = {
    "ai_generated": True,
    "read_only": True,
    "persisted": False,
    "applied": False,
    "approval_required_before_apply": True,
}

SUPPORTED_DRAFT_TYPES = frozenset(
    {
        "detection_rule_change",
        "playbook_draft",
        "incident_note",
        "escalation_summary",
        "response_recommendation",
        "investigation_checklist",
    }
)

MUTATION_FIELD_FRAGMENTS = frozenset(
    {
        "execute",
        "executed",
        "apply",
        "applied",
        "approve",
        "approved",
        "save",
        "saved",
        "persist",
        "persisted",
        "commit",
        "push",
        "deploy",
        "shell",
    }
)

SECRET_VALUE_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}\b"),
    re.compile(r"\b[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\b"),
)


@dataclass(frozen=True)
class DraftField:
    name: str
    kind: str = "string"
    required: bool = True
    max_items: int | None = None


@dataclass(frozen=True)
class DraftTypeDefinition:
    draft_type: str
    title: str
    description: str
    allowed_context_types: tuple[str, ...]
    fields: tuple[DraftField, ...]
    max_payload_chars: int = 8000
    future_handoff_target: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "labels": dict(DEFAULT_DRAFT_LABELS),
        }


@dataclass(frozen=True)
class DraftRequest:
    draft_type: str
    instruction: str
    context_type: str
    context: dict[str, Any] = field(default_factory=dict)
    use_tools: bool = False
    tool_policy: dict[str, Any] | None = None
    client_request_id: str | None = None


@dataclass(frozen=True)
class DraftValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "errors": list(self.errors)}


@dataclass(frozen=True)
class DraftResult:
    draft_type: str
    title: str
    payload: dict[str, Any]
    validation: DraftValidationResult
    generated_at: str
    labels: dict[str, bool] = field(default_factory=lambda: dict(DEFAULT_DRAFT_LABELS))

    def as_dict(self) -> dict[str, Any]:
        return {
            "draft_type": self.draft_type,
            "title": self.title,
            "payload": redact_draft_value(self.payload),
            "validation": self.validation.as_dict(),
            "generated_at": self.generated_at,
            "labels": dict(self.labels),
        }


class DraftValidationError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str = DRAFT_STATUS_INVALID_REQUEST,
        status_code: int = 400,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code


DRAFT_DEFINITIONS: dict[str, DraftTypeDefinition] = {
    "detection_rule_change": DraftTypeDefinition(
        draft_type="detection_rule_change",
        title="Detection rule change draft",
        description="Propose bounded detection logic changes for analyst review.",
        allowed_context_types=("alert", "detection", "dashboard", "general", "source_ip", "recon_activity"),
        future_handoff_target="detection rule review",
        fields=(
            DraftField("title"),
            DraftField("rationale"),
            DraftField("target_rule", required=False),
            DraftField("suggested_condition"),
            DraftField("severity"),
            DraftField("false_positive_notes"),
            DraftField("test_ideas", kind="list", max_items=8),
            DraftField("rollback_notes"),
            DraftField("source_references", kind="list", max_items=8),
        ),
    ),
    "playbook_draft": DraftTypeDefinition(
        draft_type="playbook_draft",
        title="Playbook draft",
        description="Propose a playbook outline without creating or running it.",
        allowed_context_types=("alert", "incident", "source_ip", "recon_activity", "response_registry", "general"),
        future_handoff_target="playbook design review",
        fields=(
            DraftField("name"),
            DraftField("trigger_context"),
            DraftField("steps", kind="list", max_items=12),
            DraftField("approval_gates", kind="list", max_items=8),
            DraftField("simulation_real_caveats"),
            DraftField("required_integrations", kind="list", required=False, max_items=8),
            DraftField("risks", kind="list", max_items=8),
            DraftField("source_references", kind="list", max_items=8),
        ),
    ),
    "incident_note": DraftTypeDefinition(
        draft_type="incident_note",
        title="Incident note draft",
        description="Draft incident note text for analyst review only.",
        allowed_context_types=("incident", "alert", "source_ip", "recon_activity", "general"),
        future_handoff_target="incident note workflow",
        fields=(
            DraftField("summary"),
            DraftField("evidence", kind="list", max_items=10),
            DraftField("uncertainty"),
            DraftField("recommended_next_steps", kind="list", max_items=8),
            DraftField("attribution", kind="list", max_items=8),
        ),
    ),
    "escalation_summary": DraftTypeDefinition(
        draft_type="escalation_summary",
        title="Escalation summary draft",
        description="Draft a handoff or escalation summary.",
        allowed_context_types=("incident", "alert", "source_ip", "recon_activity", "dashboard", "general"),
        future_handoff_target="escalation workflow",
        fields=(
            DraftField("audience"),
            DraftField("urgency"),
            DraftField("business_or_security_impact"),
            DraftField("evidence", kind="list", max_items=10),
            DraftField("asks", kind="list", max_items=8),
            DraftField("next_update_criteria"),
            DraftField("source_references", kind="list", max_items=8),
        ),
    ),
    "response_recommendation": DraftTypeDefinition(
        draft_type="response_recommendation",
        title="Response recommendation draft",
        description="Propose response options without executing them.",
        allowed_context_types=("alert", "incident", "source_ip", "recon_activity", "response_registry", "general"),
        future_handoff_target="response approval workflow",
        fields=(
            DraftField("recommended_action_class"),
            DraftField("prerequisites", kind="list", max_items=8),
            DraftField("expected_outcome"),
            DraftField("approval_need"),
            DraftField("risk"),
            DraftField("alternatives", kind="list", max_items=8),
            DraftField("source_references", kind="list", max_items=8),
        ),
    ),
    "investigation_checklist": DraftTypeDefinition(
        draft_type="investigation_checklist",
        title="Investigation checklist draft",
        description="Draft an ordered analyst investigation checklist.",
        allowed_context_types=("alert", "incident", "source_ip", "recon_activity", "dashboard", "response_registry", "detection", "general"),
        future_handoff_target="analyst checklist review",
        fields=(
            DraftField("title"),
            DraftField("checks", kind="list", max_items=12),
            DraftField("data_sources", kind="list", max_items=10),
            DraftField("expected_findings", kind="list", max_items=10),
            DraftField("stop_conditions", kind="list", max_items=8),
            DraftField("source_references", kind="list", max_items=8),
        ),
    ),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_draft_type(value: Any) -> str:
    draft_type = str(value or "").strip().lower()
    if not draft_type:
        raise DraftValidationError("draft_type is required.")
    if has_mutation_intent(draft_type):
        raise DraftValidationError(
            "draft_type contains mutation intent and is not allowed.",
            error_code=DRAFT_STATUS_UNSUPPORTED_TYPE,
        )
    if draft_type not in DRAFT_DEFINITIONS:
        raise DraftValidationError(
            f"Unsupported draft_type: {draft_type}",
            error_code=DRAFT_STATUS_UNSUPPORTED_TYPE,
        )
    return draft_type


def get_draft_definition(draft_type: str) -> DraftTypeDefinition:
    return DRAFT_DEFINITIONS[normalize_draft_type(draft_type)]


def validate_context_type_for_draft(definition: DraftTypeDefinition, context_type: Any) -> str:
    normalized = str(context_type or "").strip().lower()
    if not normalized:
        raise DraftValidationError("context_type is required.")
    if normalized not in definition.allowed_context_types:
        raise DraftValidationError(
            f"context_type {normalized!r} is not supported for {definition.draft_type}.",
            error_code=DRAFT_STATUS_INVALID_REQUEST,
        )
    return normalized


def validate_instruction(value: Any) -> str:
    instruction = str(value or "").strip()
    if not instruction:
        raise DraftValidationError("instruction is required.")
    if len(instruction) > 2000:
        raise DraftValidationError("instruction is too large.")
    return instruction


def validate_client_request_id(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if len(text) > 120:
        raise DraftValidationError("client_request_id is too large.")
    return text


def validate_draft_payload(draft_type: str, payload: Any) -> DraftValidationResult:
    try:
        definition = get_draft_definition(draft_type)
    except DraftValidationError as error:
        return DraftValidationResult(False, [str(error)])
    if not isinstance(payload, dict):
        return DraftValidationResult(False, ["draft payload must be a JSON object"])

    errors: list[str] = []
    normalized = redact_draft_value(payload)
    for key in normalized:
        key_text = str(key).lower()
        if any(fragment in key_text for fragment in MUTATION_FIELD_FRAGMENTS):
            errors.append(f"{key} is not allowed in a review-only draft")

    for field_def in definition.fields:
        value = normalized.get(field_def.name)
        if field_def.required and value in (None, "", [], {}):
            errors.append(f"{field_def.name} is required")
            continue
        if value in (None, "", [], {}):
            continue
        if field_def.kind == "list":
            if not isinstance(value, list):
                errors.append(f"{field_def.name} must be a list")
            elif field_def.max_items is not None and len(value) > field_def.max_items:
                errors.append(f"{field_def.name} must contain at most {field_def.max_items} items")
        elif not isinstance(value, str):
            errors.append(f"{field_def.name} must be a string")

    return DraftValidationResult(valid=not errors, errors=errors)


def build_draft_result(draft_type: str, payload: dict[str, Any]) -> DraftResult:
    definition = get_draft_definition(draft_type)
    validation = validate_draft_payload(draft_type, payload)
    return DraftResult(
        draft_type=draft_type,
        title=definition.title,
        payload=payload if validation.valid else {},
        validation=validation,
        generated_at=utc_now(),
    )


def redact_draft_value(value: Any) -> Any:
    redacted = redact_sensitive_values(value)
    return _redact_secret_strings(redacted)


def _redact_secret_strings(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            key_text = str(key).lower().replace("-", "_")
            if any(fragment in key_text for fragment in SENSITIVE_KEY_FRAGMENTS):
                result[key] = "[REDACTED]"
            else:
                result[key] = _redact_secret_strings(child)
        return result
    if isinstance(value, list):
        return [_redact_secret_strings(item) for item in value]
    if isinstance(value, str):
        redacted = value
        for pattern in SECRET_VALUE_PATTERNS:
            redacted = pattern.sub("[REDACTED]", redacted)
        return redacted
    return value


__all__ = [
    "DEFAULT_DRAFT_LABELS",
    "DRAFT_DEFINITIONS",
    "DRAFT_STATUS_INSUFFICIENT_CONTEXT",
    "DRAFT_STATUS_INVALID_REQUEST",
    "DRAFT_STATUS_PARSE_FAILED",
    "DRAFT_STATUS_SUCCESS",
    "DRAFT_STATUS_UNSUPPORTED_TYPE",
    "DRAFT_STATUS_VALIDATION_FAILED",
    "DraftRequest",
    "DraftResult",
    "DraftTypeDefinition",
    "DraftValidationError",
    "DraftValidationResult",
    "SUPPORTED_DRAFT_TYPES",
    "build_draft_result",
    "get_draft_definition",
    "normalize_draft_type",
    "redact_draft_value",
    "validate_context_type_for_draft",
    "validate_draft_payload",
    "validate_instruction",
]
