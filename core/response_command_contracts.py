"""Shared contracts for canonical analyst response commands and registry APIs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


ORIGIN_MANUAL_ALERT = "manual_alert"
ORIGIN_BLOCKLIST_FORM = "blocklist_form"
ORIGIN_PLAYBOOK = "playbook"
ORIGIN_RESPONSE_QUEUE = "response_queue"
ORIGIN_APPROVAL = "approval"
ORIGIN_SYSTEM = "system"
ORIGIN_BACKFILL = "backfill"
ORIGIN_RESPONSE_REGISTRY = "response_registry"

DISPOSITION_OBSERVED = "observed"
DISPOSITION_MONITORED = "monitored"
DISPOSITION_ESCALATED = "escalated"
DISPOSITION_PENDING = "pending"
DISPOSITION_BLOCKLIST_TRACKED = "blocklist_tracked"
DISPOSITION_REJECTED = "rejected"
DISPOSITION_FAILED = "failed"
DISPOSITION_EXPIRED = "expired"
DISPOSITION_REMOVED = "removed"

INDICATOR_TYPE_IP = "ip"

DEFAULT_MONITOR_TTL_HOURS = 168  # 7 days
ESCALATION_DEFAULT_PRIORITY = "P2"
ESCALATION_DEFAULT_SEVERITY = "high"


@dataclass
class ResponseCommandRequest:
    action: str
    indicator_type: str = INDICATOR_TYPE_IP
    indicator_value: str | None = None
    alert_id: int | None = None
    incident_id: int | None = None
    reason: str | None = None
    actor_user_id: int | None = None
    origin_surface: str = ORIGIN_SYSTEM
    idempotency_key: str | None = None
    expires_at: str | None = None  # ISO-8601 optional
    playbook_execution_id: int | None = None
    playbook_step_index: int | None = None
    queue_id: int | None = None
    approval_request_id: int | None = None
    safe_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResponseCommandResult:
    success: bool
    action: str
    outcome_label: str
    idempotent: bool = False
    enforcement: str = "none"
    registry_record_id: int | None = None
    registry_event_id: int | None = None
    blocked_ip_id: int | None = None
    incident_id: int | None = None
    decision_id: int | None = None
    soar_correlation_id: str | None = None
    response_action_log_id: int | None = None
    disposition: str | None = None
    message: str = ""
    error: str | None = None
    error_code: str | None = None
    affected_resource_keys: list[str] = field(default_factory=list)
    compatible_fields: dict[str, Any] = field(default_factory=dict)

    def to_api_dict(self) -> dict[str, Any]:
        payload = {
            "success": self.success,
            "action": self.action,
            "outcome_label": self.outcome_label,
            "idempotent": self.idempotent,
            "enforcement": self.enforcement,
            "registry_record_id": self.registry_record_id,
            "registry_event_id": self.registry_event_id,
            "blocked_ip_id": self.blocked_ip_id,
            "incident_id": self.incident_id,
            "decision_id": self.decision_id,
            "soar_correlation_id": self.soar_correlation_id,
            "response_action_log_id": self.response_action_log_id,
            "disposition": self.disposition,
            "message": self.message,
            "affected_resource_keys": list(self.affected_resource_keys),
        }
        if self.error:
            payload["error"] = self.error
        if self.error_code:
            payload["error_code"] = self.error_code
        payload.update(self.compatible_fields)
        return payload


def build_affected_resource_keys(
    *,
    alert_id: int | None = None,
    incident_id: int | None = None,
    source_ip: str | None = None,
    blocked_ip_id: int | None = None,
    registry_record_id: int | None = None,
    queue_id: int | None = None,
    playbook_execution_id: int | None = None,
) -> list[str]:
    keys: list[str] = []
    if alert_id is not None:
        keys.append(f"alert:{alert_id}")
    if incident_id is not None:
        keys.append(f"incident:{incident_id}")
    if source_ip:
        keys.append(f"source_ip:{source_ip}")
    if blocked_ip_id is not None:
        keys.append(f"blocked_ip:{blocked_ip_id}")
    if registry_record_id is not None:
        keys.append(f"registry:{registry_record_id}")
    if queue_id is not None:
        keys.append(f"queue:{queue_id}")
    if playbook_execution_id is not None:
        keys.append(f"playbook_execution:{playbook_execution_id}")
    keys.append("response_registry")
    keys.append("blocklist")
    return keys
