from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any

from core.incident_store import ALL_INCIDENT_STATUSES
from core.note_store import MAX_NOTE_LENGTH, validate_note_text

ACTION_ADD_ALERT_NOTE = "add_alert_note"
ACTION_ADD_INCIDENT_NOTE = "add_incident_note"
ACTION_CHANGE_INCIDENT_STATUS = "change_incident_status"
ACTION_CREATE_PLAYBOOK_DRAFT = "create_playbook_draft"
ACTION_UPDATE_DETECTION_RULE_PARAMETERS = "update_detection_rule_parameters"
ACTION_CREATE_INCIDENT_FROM_ALERT = "create_incident_from_alert"

ROLE_ANALYST_OR_SUPER_ADMIN = "analyst_or_super_admin"
ROLE_SUPER_ADMIN = "super_admin"

OUTCOME_REAL = "real"
OUTCOME_SIMULATED = "simulated"
OUTCOME_TRACKING_ONLY = "tracking_only"
OUTCOME_PENDING = "pending"
OUTCOME_FAILED = "failed"
OUTCOME_UNKNOWN = "unknown"
OUTCOME_DUPLICATE = "duplicate"
OUTCOME_CANCELLED = "cancelled"
OUTCOME_REJECTED = "rejected"

STATUS_PREVIEW_READY = "preview_ready"
STATUS_CONFIRMED = "confirmed"
STATUS_FORBIDDEN = "forbidden"
STATUS_INVALID_REQUEST = "invalid_request"
STATUS_UNSUPPORTED_ACTION = "unsupported_action"
STATUS_STALE_SOURCE = "stale_source"
STATUS_DUPLICATE_SUPPRESSED = "duplicate_suppressed"

SUPPORTED_OUTCOMES = frozenset(
    {
        OUTCOME_REAL,
        OUTCOME_SIMULATED,
        OUTCOME_TRACKING_ONLY,
        OUTCOME_PENDING,
        OUTCOME_FAILED,
        OUTCOME_UNKNOWN,
        OUTCOME_DUPLICATE,
        OUTCOME_CANCELLED,
        OUTCOME_REJECTED,
    }
)

FORBIDDEN_CLIENT_FIELDS = frozenset(
    {
        "route",
        "url",
        "endpoint",
        "function",
        "sql",
        "shell",
        "command",
        "path",
        "provider_config",
        "tool_name",
        "approval_decision",
    }
)

_PLAYBOOK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
_IDEMPOTENCY_RE = re.compile(r"^[a-zA-Z0-9._:-]{8,160}$")


@dataclass(frozen=True)
class AiActionDefinition:
    action_type: str
    description: str
    required_role: str
    dispatch_path: str
    target_fields: tuple[str, ...]
    payload_fields: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


ACTION_DEFINITIONS: dict[str, AiActionDefinition] = {
    ACTION_ADD_ALERT_NOTE: AiActionDefinition(
        action_type=ACTION_ADD_ALERT_NOTE,
        description="Add a reviewed AI-assisted note to an alert.",
        required_role=ROLE_ANALYST_OR_SUPER_ADMIN,
        dispatch_path="core.note_store.create_alert_note",
        target_fields=("alert_id",),
        payload_fields=("note_text",),
    ),
    ACTION_ADD_INCIDENT_NOTE: AiActionDefinition(
        action_type=ACTION_ADD_INCIDENT_NOTE,
        description="Add a reviewed AI-assisted note to an incident.",
        required_role=ROLE_ANALYST_OR_SUPER_ADMIN,
        dispatch_path="core.note_store.create_incident_note",
        target_fields=("incident_id",),
        payload_fields=("note_text",),
    ),
    ACTION_CHANGE_INCIDENT_STATUS: AiActionDefinition(
        action_type=ACTION_CHANGE_INCIDENT_STATUS,
        description="Change an incident status using existing transition validation.",
        required_role=ROLE_ANALYST_OR_SUPER_ADMIN,
        dispatch_path="core.incident_store.update_incident_status",
        target_fields=("incident_id",),
        payload_fields=("status",),
    ),
    ACTION_CREATE_PLAYBOOK_DRAFT: AiActionDefinition(
        action_type=ACTION_CREATE_PLAYBOOK_DRAFT,
        description="Create a disabled playbook definition from a reviewed draft.",
        required_role=ROLE_SUPER_ADMIN,
        dispatch_path="core.playbook_store.create_playbook_definition",
        target_fields=("playbook_id",),
        payload_fields=("name", "description", "trigger_config", "steps"),
    ),
    ACTION_UPDATE_DETECTION_RULE_PARAMETERS: AiActionDefinition(
        action_type=ACTION_UPDATE_DETECTION_RULE_PARAMETERS,
        description="Update bounded parameters on an existing detection rule.",
        required_role=ROLE_SUPER_ADMIN,
        dispatch_path="engines.detection_config.validate_detection_rule_config",
        target_fields=("rule_id",),
        payload_fields=("parameters",),
    ),
    ACTION_CREATE_INCIDENT_FROM_ALERT: AiActionDefinition(
        action_type=ACTION_CREATE_INCIDENT_FROM_ALERT,
        description="Create or link an incident using existing alert incident policy.",
        required_role=ROLE_ANALYST_OR_SUPER_ADMIN,
        dispatch_path="core.incident_store.maybe_create_or_link_incident",
        target_fields=("alert_id",),
        payload_fields=("reason",),
    ),
}

SUPPORTED_ACTION_TYPES = frozenset(ACTION_DEFINITIONS)


class AiActionValidationError(ValueError):
    def __init__(self, message: str, *, status: str = STATUS_INVALID_REQUEST, status_code: int = 400):
        super().__init__(message)
        self.status = status
        self.status_code = status_code


def get_action_definition(action_type: Any) -> AiActionDefinition:
    normalized = str(action_type or "").strip().lower()
    if not normalized:
        raise AiActionValidationError("action_type is required")
    if normalized not in ACTION_DEFINITIONS:
        raise AiActionValidationError(
            f"unsupported AI action type: {normalized}",
            status=STATUS_UNSUPPORTED_ACTION,
        )
    return ACTION_DEFINITIONS[normalized]


def reject_smuggled_fields(payload: dict[str, Any]) -> None:
    found = sorted(set(payload) & FORBIDDEN_CLIENT_FIELDS)
    if found:
        raise AiActionValidationError(f"unsupported action field: {found[0]}")


def normalize_positive_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise AiActionValidationError(f"{field_name} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise AiActionValidationError(f"{field_name} must be a positive integer") from None
    if parsed <= 0:
        raise AiActionValidationError(f"{field_name} must be a positive integer")
    return parsed


def normalize_action_payload(action_type: str, raw_payload: Any) -> dict[str, Any]:
    if not isinstance(raw_payload, dict):
        raise AiActionValidationError("payload must be an object")
    reject_smuggled_fields(raw_payload)

    if action_type == ACTION_ADD_ALERT_NOTE:
        return {
            "alert_id": normalize_positive_int(raw_payload.get("alert_id"), field_name="alert_id"),
            "note_text": validate_note_text(raw_payload.get("note_text")),
        }
    if action_type == ACTION_ADD_INCIDENT_NOTE:
        return {
            "incident_id": normalize_positive_int(raw_payload.get("incident_id"), field_name="incident_id"),
            "note_text": validate_note_text(raw_payload.get("note_text")),
        }
    if action_type == ACTION_CHANGE_INCIDENT_STATUS:
        status = str(raw_payload.get("status") or "").strip().lower()
        if status not in ALL_INCIDENT_STATUSES:
            raise AiActionValidationError("status is not allowed for incidents")
        return {
            "incident_id": normalize_positive_int(raw_payload.get("incident_id"), field_name="incident_id"),
            "status": status,
        }
    if action_type == ACTION_CREATE_PLAYBOOK_DRAFT:
        playbook_id = str(raw_payload.get("playbook_id") or raw_payload.get("id") or "").strip()
        if not _PLAYBOOK_ID_RE.fullmatch(playbook_id):
            raise AiActionValidationError("playbook_id format is invalid")
        name = _bounded_string(raw_payload.get("name"), "name", max_len=200)
        description = _optional_bounded_string(raw_payload.get("description"), "description", max_len=2000)
        trigger_config = raw_payload.get("trigger_config") or {}
        steps = raw_payload.get("steps")
        if not isinstance(trigger_config, dict):
            raise AiActionValidationError("trigger_config must be an object")
        if not isinstance(steps, list) or not steps:
            raise AiActionValidationError("steps must be a non-empty list")
        if len(steps) > 20:
            raise AiActionValidationError("steps must contain 20 items or fewer")
        return {
            "playbook_id": playbook_id,
            "name": name,
            "description": description,
            "trigger_config": trigger_config,
            "steps": steps,
            "enabled": False,
        }
    if action_type == ACTION_UPDATE_DETECTION_RULE_PARAMETERS:
        rule_id = _bounded_string(raw_payload.get("rule_id"), "rule_id", max_len=120)
        parameters = raw_payload.get("parameters")
        if not isinstance(parameters, dict) or not parameters:
            raise AiActionValidationError("parameters must be a non-empty object")
        if "active" in raw_payload:
            raise AiActionValidationError("AI detection rule actions may update parameters only")
        return {"rule_id": rule_id, "parameters": parameters}
    if action_type == ACTION_CREATE_INCIDENT_FROM_ALERT:
        normalized = {
            "alert_id": normalize_positive_int(raw_payload.get("alert_id"), field_name="alert_id"),
        }
        reason = _optional_bounded_string(raw_payload.get("reason"), "reason", max_len=500)
        if reason:
            normalized["reason"] = reason
        return normalized

    raise AiActionValidationError(f"unsupported AI action type: {action_type}", status=STATUS_UNSUPPORTED_ACTION)


def normalize_idempotency_key(value: Any) -> str:
    key = str(value or "").strip()
    if not key:
        raise AiActionValidationError("idempotency_key is required")
    if not _IDEMPOTENCY_RE.fullmatch(key):
        raise AiActionValidationError("idempotency_key format is invalid")
    return key


def payload_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def safe_payload_for_response(payload: dict[str, Any]) -> dict[str, Any]:
    safe = dict(payload)
    for key in ("note_text",):
        if key in safe and isinstance(safe[key], str) and len(safe[key]) > 160:
            safe[key] = f"{safe[key][:160]}..."
    return safe


def _bounded_string(value: Any, field_name: str, *, max_len: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise AiActionValidationError(f"{field_name} is required")
    if len(text) > max_len:
        raise AiActionValidationError(f"{field_name} must be {max_len} characters or fewer")
    return text


def _optional_bounded_string(value: Any, field_name: str, *, max_len: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > max_len:
        raise AiActionValidationError(f"{field_name} must be {max_len} characters or fewer")
    return text
