"""
Legacy SOAR record compatibility inference and dry-run backfill planning.

Read-only: derives canonical outcome read models from pre-migration tables.
Does not insert or update database rows.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from core.soar_response_outcomes import (
    derive_outcome_label,
    generate_legacy_soar_correlation_id,
    get_decision_with_latest_outcome,
)

_SIMULATION_HINTS = ("simulated", "monitoring only", "simulation")
_TRACKING_ONLY_HINTS = (
    "tracking only",
    "recorded in siem blocklist",
    "blocklist (tracking",
)


@dataclass
class LegacyMappingResult:
    source_table: str
    source_id: int
    soar_correlation_id: str
    selected_action: str | None
    decision_source: str
    execution_mode: str
    execution_state: str
    external_executed: bool
    tracking_recorded: bool
    simulated: bool
    execution_actor: str
    outcome_summary: str
    reason_code: str | None = None
    ambiguous: bool = False
    needs_review: bool = False
    ambiguity_reason: str | None = None
    alert_id: int | None = None
    incident_id: int | None = None
    source_ip: str | None = None
    queue_id: int | None = None
    playbook_execution_id: int | None = None
    approval_request_id: int | None = None
    notification_delivery_attempt_id: int | None = None
    response_action_log_id: int | None = None
    blocked_ip_id: int | None = None
    proposed_decision: bool = True
    proposed_event_count: int = 1

    def to_read_model(self) -> dict[str, Any]:
        outcome_label = derive_outcome_label(
            execution_mode=self.execution_mode,
            execution_state=self.execution_state,
            external_executed=self.external_executed,
            tracking_recorded=self.tracking_recorded,
            simulated=self.simulated,
        )
        return {
            "source_table": self.source_table,
            "source_id": self.source_id,
            "inferred": True,
            "ambiguous": self.ambiguous,
            "needs_review": self.needs_review,
            "ambiguity_reason": self.ambiguity_reason,
            "soar_correlation_id": self.soar_correlation_id,
            "decision_id": None,
            "latest_outcome_event_id": None,
            "selected_action": self.selected_action,
            "decision_source": self.decision_source,
            "execution_actor": self.execution_actor,
            "outcome_label": outcome_label,
            "execution_mode": self.execution_mode,
            "execution_state": self.execution_state,
            "external_executed": self.external_executed,
            "tracking_recorded": self.tracking_recorded,
            "simulated": self.simulated,
            "outcome_summary": self.outcome_summary,
            "reason_code": self.reason_code,
            "decision": None,
            "latest_outcome": None,
            "related": {
                "alert_id": self.alert_id,
                "incident_id": self.incident_id,
                "source_ip": self.source_ip,
                "queue_id": self.queue_id,
                "playbook_execution_id": self.playbook_execution_id,
                "approval_request_id": self.approval_request_id,
                "notification_delivery_attempt_id": self.notification_delivery_attempt_id,
                "response_action_log_id": self.response_action_log_id,
                "blocked_ip_id": self.blocked_ip_id,
            },
            "proposed_idempotency_keys": self._proposed_idempotency_keys(),
        }

    def _proposed_idempotency_keys(self) -> dict[str, str]:
        base = f"legacy-backfill-{self.source_table}-{self.source_id}"
        return {
            "decision": f"{base}-decision",
            "latest_event": f"{base}-event-latest",
        }


@dataclass
class BackfillDryRunPlan:
    decisions_by_source: Counter = field(default_factory=Counter)
    events_by_source: Counter = field(default_factory=Counter)
    mode_state_counts: Counter = field(default_factory=Counter)
    reason_code_counts: Counter = field(default_factory=Counter)
    boolean_counts: Counter = field(default_factory=Counter)
    ambiguous_records: list[dict[str, Any]] = field(default_factory=list)
    observed_only_count: int = 0
    total_records_scanned: int = 0

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "total_records_scanned": self.total_records_scanned,
            "proposed_decisions": sum(self.decisions_by_source.values()),
            "proposed_events": sum(self.events_by_source.values()),
            "decisions_by_source": dict(self.decisions_by_source),
            "events_by_source": dict(self.events_by_source),
            "mode_state_counts": dict(self.mode_state_counts),
            "reason_code_counts": dict(self.reason_code_counts),
            "boolean_counts": dict(self.boolean_counts),
            "observed_only_count": self.observed_only_count,
            "ambiguous_count": len(self.ambiguous_records),
            "ambiguous_records": self.ambiguous_records[:25],
        }


def _details_indicates_simulation(details: str | None) -> bool:
    text = (details or "").lower()
    return any(hint in text for hint in _SIMULATION_HINTS)


def _details_indicates_tracking_only(details: str | None) -> bool:
    text = (details or "").lower()
    return any(hint in text for hint in _TRACKING_ONLY_HINTS)


def _notification_metadata_has_provider_success_evidence(metadata: Any) -> bool:
    if not isinstance(metadata, dict):
        return False
    http_status = metadata.get("http_status")
    try:
        if http_status is not None and 200 <= int(http_status) < 300:
            return True
    except (TypeError, ValueError):
        pass
    delivery = str(metadata.get("delivery") or "").strip().lower()
    return delivery in {"sent", "delivered", "accepted", "success"}


def _notification_metadata_confirms_execution(metadata: Any) -> bool:
    if not isinstance(metadata, dict):
        return False
    if metadata.get("executed") is not True:
        return False
    if metadata.get("simulated") is not False:
        return False
    adapter_mode = str(metadata.get("adapter_mode") or metadata.get("mode") or "").strip().lower()
    return adapter_mode == "real" or _notification_metadata_has_provider_success_evidence(metadata)


def _coerce_steps_log(raw_steps_log: Any) -> list[dict[str, Any]]:
    if isinstance(raw_steps_log, list):
        return [step for step in raw_steps_log if isinstance(step, dict)]
    if isinstance(raw_steps_log, str):
        try:
            parsed = json.loads(raw_steps_log)
        except json.JSONDecodeError:
            return []
        return [step for step in parsed if isinstance(step, dict)] if isinstance(parsed, list) else []
    return []


def _latest_playbook_step(steps_log: Any) -> dict[str, Any] | None:
    steps = _coerce_steps_log(steps_log)
    return steps[-1] if steps else None


def _playbook_step_evidence(step: dict[str, Any] | None) -> tuple[bool, bool, bool]:
    if not step:
        return False, False, False
    output = step.get("output") if isinstance(step.get("output"), dict) else {}
    adapter_result = (
        output.get("adapter_result")
        if isinstance(output.get("adapter_result"), dict)
        else {}
    )
    simulated = bool(
        step.get("simulated")
        or output.get("simulated")
        or adapter_result.get("simulated")
    )
    external_executed = bool(
        step.get("executed")
        or output.get("executed")
        or adapter_result.get("executed")
    )
    tracking_recorded = bool(output.get("tracking_recorded") or adapter_result.get("tracking_recorded"))
    return simulated, external_executed, tracking_recorded


def _wrap_canonical_read_model(
    read_model: dict[str, Any], *, source_table: str, source_id: int
) -> dict[str, Any]:
    return {
        **read_model,
        "source_table": source_table,
        "source_id": source_id,
        "inferred": False,
        "ambiguous": False,
        "needs_review": False,
        "ambiguity_reason": None,
        "related": {
            "alert_id": read_model.get("decision", {}).get("alert_id"),
            "incident_id": read_model.get("decision", {}).get("incident_id"),
            "source_ip": read_model.get("decision", {}).get("source_ip"),
            "queue_id": read_model.get("decision", {}).get("queue_id"),
            "playbook_execution_id": read_model.get("decision", {}).get("playbook_execution_id"),
            "approval_request_id": read_model.get("decision", {}).get("approval_request_id"),
            "notification_delivery_attempt_id": None,
            "response_action_log_id": None,
            "blocked_ip_id": None,
        },
    }


def _find_canonical_decision_id(conn, *, column: str, value: Any) -> int | None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id
            FROM soar_response_decisions
            WHERE {column} = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (value,),
        )
        row = cur.fetchone()
    return row[0] if row else None


def _resolve_canonical_or_infer(
    conn,
    *,
    source_table: str,
    source_id: int,
    lookup_column: str | None,
    lookup_value: Any,
    infer_fn,
) -> dict[str, Any]:
    if lookup_column is not None and lookup_value is not None:
        decision_id = _find_canonical_decision_id(conn, column=lookup_column, value=lookup_value)
        if decision_id is not None:
            read_model = get_decision_with_latest_outcome(conn, decision_id=decision_id)
            if read_model is not None:
                return _wrap_canonical_read_model(
                    read_model, source_table=source_table, source_id=source_id
                )

    inferred = infer_fn()
    return inferred.to_read_model()


def infer_alert_legacy_outcome(
    *,
    alert_id: int,
    source_ip: str | None,
    response_action: str | None,
    has_queue: bool,
    has_log: bool,
) -> LegacyMappingResult:
    correlation_id = generate_legacy_soar_correlation_id("alerts", alert_id)
    if not response_action and not has_queue and not has_log:
        return LegacyMappingResult(
            source_table="alerts",
            source_id=alert_id,
            soar_correlation_id=correlation_id,
            selected_action=None,
            decision_source="migration",
            execution_mode="observed",
            execution_state="observed",
            external_executed=False,
            tracking_recorded=False,
            simulated=False,
            execution_actor="system",
            outcome_summary="Detection observed; no response selected or executed.",
            alert_id=alert_id,
            source_ip=source_ip,
            proposed_decision=False,
            proposed_event_count=1,
        )

    selected_action = response_action or "monitor"
    if has_queue or has_log:
        return LegacyMappingResult(
            source_table="alerts",
            source_id=alert_id,
            soar_correlation_id=correlation_id,
            selected_action=selected_action,
            decision_source="detection_default",
            execution_mode="simulation",
            execution_state="selected",
            external_executed=False,
            tracking_recorded=False,
            simulated=False,
            execution_actor="system",
            outcome_summary="Legacy alert selected a response; queue/log records provide lifecycle detail.",
            alert_id=alert_id,
            source_ip=source_ip,
            proposed_decision=True,
            proposed_event_count=0,
        )

    return LegacyMappingResult(
        source_table="alerts",
        source_id=alert_id,
        soar_correlation_id=correlation_id,
        selected_action=selected_action,
        decision_source="detection_default",
        execution_mode="simulation",
        execution_state="selected",
        external_executed=False,
        tracking_recorded=False,
        simulated=False,
        execution_actor="system",
        outcome_summary="Legacy alert selected a response; no queue or log evidence found.",
        alert_id=alert_id,
        source_ip=source_ip,
        ambiguous=True,
        needs_review=True,
        ambiguity_reason="response_action_without_queue_or_log",
    )


def infer_alert_notification_legacy_outcome(
    *,
    alert_id: int,
    source_ip: str | None,
    response_action: str | None,
    attempt_id: int,
    incident_id: int | None,
    playbook_execution_id: int | None,
    approval_request_id: int | None,
    approval_status: str | None,
    action: str,
    mode: str,
    status: str,
    metadata: Any,
    failure_message: str | None,
) -> LegacyMappingResult:
    correlation_id = generate_legacy_soar_correlation_id("alerts", alert_id)
    if approval_status in {"denied", "expired"}:
        return LegacyMappingResult(
            source_table="alerts",
            source_id=alert_id,
            soar_correlation_id=correlation_id,
            selected_action=response_action or action,
            decision_source="detection_default",
            execution_mode="simulation",
            execution_state="blocked",
            external_executed=False,
            tracking_recorded=False,
            simulated=False,
            execution_actor="approval_service",
            outcome_summary=failure_message or f"Linked approval request was {approval_status}.",
            reason_code=(
                "approval_denied"
                if approval_status == "denied"
                else "approval_expired"
            ),
            alert_id=alert_id,
            incident_id=incident_id,
            source_ip=source_ip,
            playbook_execution_id=playbook_execution_id,
            approval_request_id=approval_request_id,
            notification_delivery_attempt_id=attempt_id,
            proposed_decision=True,
            proposed_event_count=1,
        )

    notification_mapping = infer_notification_delivery_legacy_outcome(
        attempt_id=attempt_id,
        alert_id=alert_id,
        incident_id=incident_id,
        playbook_execution_id=playbook_execution_id,
        approval_request_id=approval_request_id,
        action=action,
        mode=mode,
        status=status,
        metadata=metadata,
        failure_message=failure_message,
    )
    return LegacyMappingResult(
        source_table="alerts",
        source_id=alert_id,
        soar_correlation_id=correlation_id,
        selected_action=response_action or notification_mapping.selected_action,
        decision_source="detection_default",
        execution_mode=notification_mapping.execution_mode,
        execution_state=notification_mapping.execution_state,
        external_executed=notification_mapping.external_executed,
        tracking_recorded=notification_mapping.tracking_recorded,
        simulated=notification_mapping.simulated,
        execution_actor=notification_mapping.execution_actor,
        outcome_summary=notification_mapping.outcome_summary,
        reason_code=notification_mapping.reason_code,
        ambiguous=notification_mapping.ambiguous,
        needs_review=notification_mapping.needs_review,
        ambiguity_reason=notification_mapping.ambiguity_reason,
        alert_id=alert_id,
        incident_id=incident_id,
        source_ip=source_ip,
        playbook_execution_id=playbook_execution_id,
        approval_request_id=approval_request_id,
        notification_delivery_attempt_id=attempt_id,
        proposed_decision=True,
        proposed_event_count=1,
    )


def infer_queue_legacy_outcome(
    *,
    queue_id: int,
    alert_id: int | None,
    source_ip: str | None,
    action: str,
    status: str,
    last_error: str | None,
) -> LegacyMappingResult:
    correlation_id = generate_legacy_soar_correlation_id("response_actions_queue", queue_id)
    base = dict(
        source_table="response_actions_queue",
        source_id=queue_id,
        soar_correlation_id=correlation_id,
        selected_action=action,
        decision_source="migration",
        alert_id=alert_id,
        source_ip=source_ip,
        queue_id=queue_id,
        proposed_decision=True,
        proposed_event_count=1,
    )

    if status == "pending":
        return LegacyMappingResult(
            **base,
            execution_mode="simulation",
            execution_state="queued",
            external_executed=False,
            tracking_recorded=False,
            simulated=False,
            execution_actor="queue_worker",
            outcome_summary="Legacy queue action is pending execution.",
        )
    if status == "running":
        return LegacyMappingResult(
            **base,
            execution_mode="simulation",
            execution_state="running",
            external_executed=False,
            tracking_recorded=False,
            simulated=False,
            execution_actor="queue_worker",
            outcome_summary="Legacy queue action is running.",
        )
    if status == "awaiting_approval":
        return LegacyMappingResult(
            **base,
            execution_mode="simulation",
            execution_state="awaiting_approval",
            external_executed=False,
            tracking_recorded=False,
            simulated=False,
            execution_actor="queue_worker",
            outcome_summary="Legacy queue action is awaiting approval.",
            reason_code="approval_required",
        )
    if status == "skipped":
        return LegacyMappingResult(
            **base,
            execution_mode="simulation",
            execution_state="skipped",
            external_executed=False,
            tracking_recorded=False,
            simulated=False,
            execution_actor="queue_worker",
            outcome_summary=last_error or "Legacy queue action was skipped.",
            reason_code="policy_blocked",
        )
    if status == "failed":
        return LegacyMappingResult(
            **base,
            execution_mode="simulation",
            execution_state="failed",
            external_executed=False,
            tracking_recorded=False,
            simulated=False,
            execution_actor="queue_worker",
            outcome_summary=last_error or "Legacy queue action failed.",
            reason_code="provider_error",
        )
    if status == "success":
        return LegacyMappingResult(
            **base,
            execution_mode="simulation",
            execution_state="succeeded",
            external_executed=False,
            tracking_recorded=False,
            simulated=True,
            execution_actor="queue_worker",
            outcome_summary="Legacy queue action completed in simulation mode.",
            reason_code="simulation_mode",
        )

    return LegacyMappingResult(
        **base,
        execution_mode="simulation",
        execution_state="selected",
        external_executed=False,
        tracking_recorded=False,
        simulated=False,
        execution_actor="queue_worker",
        outcome_summary=f"Legacy queue status '{status}' mapped conservatively.",
        ambiguous=True,
        needs_review=True,
        ambiguity_reason=f"unknown_queue_status:{status}",
    )


def infer_response_log_legacy_outcome(
    *,
    log_id: int,
    alert_id: int | None,
    source_ip: str | None,
    action: str,
    status: str,
    details: str | None,
    blocked_ip_exists: bool,
) -> LegacyMappingResult:
    correlation_id = generate_legacy_soar_correlation_id("response_actions_log", log_id)
    base = dict(
        source_table="response_actions_log",
        source_id=log_id,
        soar_correlation_id=correlation_id,
        selected_action=action,
        decision_source="migration",
        alert_id=alert_id,
        source_ip=source_ip,
        response_action_log_id=log_id,
        proposed_decision=True,
        proposed_event_count=1,
    )

    if status == "skipped":
        return LegacyMappingResult(
            **base,
            execution_mode="simulation",
            execution_state="skipped",
            external_executed=False,
            tracking_recorded=False,
            simulated=False,
            execution_actor="queue_worker",
            outcome_summary=details or "Legacy response log entry was skipped.",
            reason_code="policy_blocked",
        )
    if status == "failed":
        return LegacyMappingResult(
            **base,
            execution_mode="simulation",
            execution_state="failed",
            external_executed=False,
            tracking_recorded=False,
            simulated=False,
            execution_actor="queue_worker",
            outcome_summary=details or "Legacy response log entry failed.",
            reason_code="provider_error",
        )

    if _details_indicates_tracking_only(details) or (
        action == "block_ip" and blocked_ip_exists
    ):
        return LegacyMappingResult(
            **base,
            execution_mode="tracking_only",
            execution_state="succeeded",
            external_executed=False,
            tracking_recorded=True,
            simulated=False,
            execution_actor="manual",
            outcome_summary=details
            or "Recorded IP in SIEM blocklist only; no firewall enforcement occurred.",
            reason_code="tracking_only",
        )

    if _details_indicates_simulation(details):
        return LegacyMappingResult(
            **base,
            execution_mode="simulation",
            execution_state="succeeded",
            external_executed=False,
            tracking_recorded=False,
            simulated=True,
            execution_actor="queue_worker",
            outcome_summary=details or "Legacy simulated response completed.",
            reason_code="simulation_mode",
        )

    return LegacyMappingResult(
        **base,
        execution_mode="simulation",
        execution_state="succeeded",
        external_executed=False,
        tracking_recorded=False,
        simulated=True,
        execution_actor="queue_worker",
        outcome_summary=details or "Legacy response log mapped conservatively as simulation.",
        reason_code="simulation_mode",
        ambiguous=True,
        needs_review=True,
        ambiguity_reason="executed_log_without_explicit_simulation_or_tracking_evidence",
    )


def infer_approval_request_legacy_outcome(
    *,
    approval_request_id: int,
    alert_id: int | None,
    incident_id: int | None,
    queue_id: int | None,
    playbook_execution_id: int | None,
    action: str,
    status: str,
    request_reason: str | None,
) -> LegacyMappingResult:
    correlation_id = generate_legacy_soar_correlation_id("approval_requests", approval_request_id)
    base = dict(
        source_table="approval_requests",
        source_id=approval_request_id,
        soar_correlation_id=correlation_id,
        selected_action=action,
        decision_source="migration",
        alert_id=alert_id,
        incident_id=incident_id,
        queue_id=queue_id,
        playbook_execution_id=playbook_execution_id,
        approval_request_id=approval_request_id,
        proposed_decision=True,
        proposed_event_count=1,
    )

    if status == "pending":
        return LegacyMappingResult(
            **base,
            execution_mode="simulation",
            execution_state="awaiting_approval",
            external_executed=False,
            tracking_recorded=False,
            simulated=False,
            execution_actor="approval_service",
            outcome_summary=request_reason or "Legacy approval request is pending.",
            reason_code="approval_required",
        )
    if status in {"denied", "expired"}:
        return LegacyMappingResult(
            **base,
            execution_mode="simulation",
            execution_state="blocked",
            external_executed=False,
            tracking_recorded=False,
            simulated=False,
            execution_actor="approval_service",
            outcome_summary=request_reason or f"Legacy approval request was {status}.",
            reason_code=(
                "approval_denied" if status == "denied" else "approval_expired"
            ),
        )
    if status == "approved":
        return LegacyMappingResult(
            **base,
            execution_mode="simulation",
            execution_state="selected",
            external_executed=False,
            tracking_recorded=False,
            simulated=False,
            execution_actor="approval_service",
            outcome_summary=request_reason or "Legacy approval request was approved.",
        )

    return LegacyMappingResult(
        **base,
        execution_mode="simulation",
        execution_state="selected",
        external_executed=False,
        tracking_recorded=False,
        simulated=False,
        execution_actor="approval_service",
        outcome_summary=request_reason or f"Legacy approval status '{status}' mapped conservatively.",
        ambiguous=True,
        needs_review=True,
        ambiguity_reason=f"unknown_approval_status:{status}",
    )


def infer_notification_delivery_legacy_outcome(
    *,
    attempt_id: int,
    alert_id: int | None,
    incident_id: int | None,
    playbook_execution_id: int | None,
    approval_request_id: int | None,
    action: str,
    mode: str,
    status: str,
    metadata: Any,
    failure_message: str | None,
) -> LegacyMappingResult:
    correlation_id = generate_legacy_soar_correlation_id(
        "notification_delivery_attempts", attempt_id
    )
    base = dict(
        source_table="notification_delivery_attempts",
        source_id=attempt_id,
        soar_correlation_id=correlation_id,
        selected_action=action,
        decision_source="migration",
        alert_id=alert_id,
        incident_id=incident_id,
        playbook_execution_id=playbook_execution_id,
        approval_request_id=approval_request_id,
        notification_delivery_attempt_id=attempt_id,
        proposed_decision=True,
        proposed_event_count=1,
    )

    if mode == "simulation" and status == "success":
        return LegacyMappingResult(
            **base,
            execution_mode="simulation",
            execution_state="succeeded",
            external_executed=False,
            tracking_recorded=False,
            simulated=True,
            execution_actor="adapter",
            outcome_summary="Legacy notification delivery completed in simulation mode.",
            reason_code="simulation_mode",
        )
    if mode == "real" and status == "success" and _notification_metadata_confirms_execution(metadata):
        return LegacyMappingResult(
            **base,
            execution_mode="real",
            execution_state="succeeded",
            external_executed=True,
            tracking_recorded=False,
            simulated=False,
            execution_actor="adapter",
            outcome_summary="Legacy notification delivery confirmed real execution.",
        )
    if mode == "real" and status == "success":
        return LegacyMappingResult(
            **base,
            execution_mode="simulation",
            execution_state="succeeded",
            external_executed=False,
            tracking_recorded=False,
            simulated=True,
            execution_actor="adapter",
            outcome_summary="Legacy real-mode delivery succeeded without explicit execution evidence.",
            reason_code="simulation_mode",
            ambiguous=True,
            needs_review=True,
            ambiguity_reason="real_delivery_without_executed_metadata",
        )
    if status == "blocked":
        return LegacyMappingResult(
            **base,
            execution_mode="simulation",
            execution_state="blocked",
            external_executed=False,
            tracking_recorded=False,
            simulated=False,
            execution_actor="adapter",
            outcome_summary=failure_message or "Legacy notification delivery was blocked.",
            reason_code="policy_blocked",
        )
    if status in {"failed", "timeout"}:
        return LegacyMappingResult(
            **base,
            execution_mode="simulation" if mode == "simulation" else "real",
            execution_state="failed",
            external_executed=False,
            tracking_recorded=False,
            simulated=mode == "simulation",
            execution_actor="adapter",
            outcome_summary=failure_message or f"Legacy notification delivery {status}.",
            reason_code="provider_error",
        )
    if status == "pending":
        return LegacyMappingResult(
            **base,
            execution_mode="simulation" if mode == "simulation" else "real",
            execution_state="running",
            external_executed=False,
            tracking_recorded=False,
            simulated=False,
            execution_actor="adapter",
            outcome_summary="Legacy notification delivery is pending.",
        )

    return LegacyMappingResult(
        **base,
        execution_mode="simulation",
        execution_state="selected",
        external_executed=False,
        tracking_recorded=False,
        simulated=False,
        execution_actor="adapter",
        outcome_summary=failure_message or f"Legacy notification status '{status}' mapped conservatively.",
        ambiguous=True,
        needs_review=True,
        ambiguity_reason=f"unknown_notification_status:{status}",
    )


def infer_playbook_execution_legacy_outcome(
    *,
    execution_id: int,
    alert_id: int | None,
    incident_id: int | None,
    playbook_id: str,
    status: str,
    steps_log: Any,
    failure_reason: str | None,
    real_notification_confirmed: bool = False,
) -> LegacyMappingResult:
    correlation_id = generate_legacy_soar_correlation_id("playbook_executions", execution_id)
    base = dict(
        source_table="playbook_executions",
        source_id=execution_id,
        soar_correlation_id=correlation_id,
        selected_action=playbook_id,
        decision_source="playbook",
        alert_id=alert_id,
        incident_id=incident_id,
        playbook_execution_id=execution_id,
        proposed_decision=True,
        proposed_event_count=max(1, len(_coerce_steps_log(steps_log))),
    )
    last_step = _latest_playbook_step(steps_log)
    simulated, external_executed, tracking_recorded = _playbook_step_evidence(last_step)

    if status == "pending":
        return LegacyMappingResult(
            **base,
            execution_mode="simulation",
            execution_state="queued",
            external_executed=False,
            tracking_recorded=False,
            simulated=False,
            execution_actor="playbook_worker",
            outcome_summary="Legacy playbook execution is pending.",
        )
    if status == "running":
        return LegacyMappingResult(
            **base,
            execution_mode="simulation",
            execution_state="running",
            external_executed=False,
            tracking_recorded=False,
            simulated=False,
            execution_actor="playbook_worker",
            outcome_summary="Legacy playbook execution is running.",
        )
    if status == "awaiting_approval":
        return LegacyMappingResult(
            **base,
            execution_mode="simulation",
            execution_state="awaiting_approval",
            external_executed=False,
            tracking_recorded=False,
            simulated=False,
            execution_actor="playbook_worker",
            outcome_summary="Legacy playbook execution is awaiting approval.",
            reason_code="approval_required",
        )
    if status in {"failed", "abandoned", "permanently_failed"}:
        terminal_state = "failed" if status == "failed" else "skipped"
        return LegacyMappingResult(
            **base,
            execution_mode="simulation",
            execution_state=terminal_state,
            external_executed=False,
            tracking_recorded=False,
            simulated=simulated,
            execution_actor="playbook_worker",
            outcome_summary=failure_reason or f"Legacy playbook execution {status}.",
            reason_code="provider_error" if status == "failed" else "unsupported_action",
        )
    if status in {"success", "completed"}:
        if external_executed and real_notification_confirmed:
            return LegacyMappingResult(
                **base,
                execution_mode="real",
                execution_state="succeeded",
                external_executed=True,
                tracking_recorded=False,
                simulated=False,
                execution_actor="playbook_worker",
                outcome_summary="Legacy playbook step reported real execution.",
            )
        if external_executed:
            return LegacyMappingResult(
                **base,
                execution_mode="simulation",
                execution_state="succeeded",
                external_executed=False,
                tracking_recorded=False,
                simulated=True,
                execution_actor="playbook_worker",
                outcome_summary=(
                    "Legacy playbook step reported execution in nested output, "
                    "but no corroborating real notification delivery was found."
                ),
                reason_code="simulation_mode",
                ambiguous=True,
                needs_review=True,
                ambiguity_reason="playbook_real_execution_without_notification_corroboration",
            )
        if tracking_recorded:
            return LegacyMappingResult(
                **base,
                execution_mode="tracking_only",
                execution_state="succeeded",
                external_executed=False,
                tracking_recorded=True,
                simulated=False,
                execution_actor="playbook_worker",
                outcome_summary="Legacy playbook step recorded tracking-only state.",
                reason_code="tracking_only",
            )
        return LegacyMappingResult(
            **base,
            execution_mode="simulation",
            execution_state="succeeded",
            external_executed=False,
            tracking_recorded=False,
            simulated=True if simulated or not last_step else simulated,
            execution_actor="playbook_worker",
            outcome_summary="Legacy playbook execution completed in simulation mode.",
            reason_code="simulation_mode",
        )

    return LegacyMappingResult(
        **base,
        execution_mode="simulation",
        execution_state="selected",
        external_executed=False,
        tracking_recorded=False,
        simulated=False,
        execution_actor="playbook_worker",
        outcome_summary=failure_reason or f"Legacy playbook status '{status}' mapped conservatively.",
        ambiguous=True,
        needs_review=True,
        ambiguity_reason=f"unknown_playbook_status:{status}",
    )


def infer_blocked_ip_legacy_outcome(
    *,
    block_id: int,
    source_ip: str,
    source_alert_id: int | None,
    reason: str | None,
) -> LegacyMappingResult:
    correlation_id = generate_legacy_soar_correlation_id("blocked_ips", block_id)
    return LegacyMappingResult(
        source_table="blocked_ips",
        source_id=block_id,
        soar_correlation_id=correlation_id,
        selected_action="block_ip",
        decision_source="migration",
        execution_mode="tracking_only",
        execution_state="succeeded",
        external_executed=False,
        tracking_recorded=True,
        simulated=False,
        execution_actor="manual",
        outcome_summary=reason
        or "Recorded IP in SIEM blocklist only; no firewall enforcement occurred.",
        reason_code="tracking_only",
        alert_id=source_alert_id,
        source_ip=source_ip,
        blocked_ip_id=block_id,
        proposed_decision=True,
        proposed_event_count=1,
    )


def resolve_alert_outcome(conn, alert_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, host(source_ip), response_action
            FROM alerts
            WHERE id = %s
            """,
            (alert_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM response_actions_queue WHERE alert_id = %s)",
            (alert_id,),
        )
        has_queue = bool(cur.fetchone()[0])
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM response_actions_log WHERE alert_id = %s)",
            (alert_id,),
        )
        has_log = bool(cur.fetchone()[0])
        cur.execute(
            """
            SELECT n.id, n.incident_id, n.playbook_execution_id, n.approval_request_id,
                   ar.status AS approval_status, n.action, n.mode, n.status,
                   n.metadata, n.failure_message
            FROM notification_delivery_attempts n
            LEFT JOIN approval_requests ar ON ar.id = n.approval_request_id
            WHERE n.alert_id = %s
            ORDER BY n.created_at DESC, n.id DESC
            LIMIT 1
            """,
            (alert_id,),
        )
        notification_row = cur.fetchone()

    return _resolve_canonical_or_infer(
        conn,
        source_table="alerts",
        source_id=alert_id,
        lookup_column="alert_id",
        lookup_value=alert_id,
        infer_fn=lambda: (
            infer_alert_notification_legacy_outcome(
                alert_id=alert_id,
                source_ip=row[1],
                response_action=row[2],
                attempt_id=notification_row[0],
                incident_id=notification_row[1],
                playbook_execution_id=notification_row[2],
                approval_request_id=notification_row[3],
                approval_status=notification_row[4],
                action=notification_row[5],
                mode=notification_row[6],
                status=notification_row[7],
                metadata=notification_row[8],
                failure_message=notification_row[9],
            )
            if notification_row is not None
            else infer_alert_legacy_outcome(
                alert_id=alert_id,
                source_ip=row[1],
                response_action=row[2],
                has_queue=has_queue,
                has_log=has_log,
            )
        ),
    )


def resolve_queue_outcome(conn, queue_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT alert_id, host(source_ip), action, status, last_error, decision_id
            FROM response_actions_queue
            WHERE id = %s
            """,
            (queue_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None

    if row[5] is not None:
        read_model = get_decision_with_latest_outcome(conn, decision_id=row[5])
        if read_model is not None:
            return _wrap_canonical_read_model(
                read_model, source_table="response_actions_queue", source_id=queue_id
            )

    return infer_queue_legacy_outcome(
        queue_id=queue_id,
        alert_id=row[0],
        source_ip=row[1],
        action=row[2],
        status=row[3],
        last_error=row[4],
    ).to_read_model()


def resolve_response_log_outcome(conn, log_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT alert_id, host(source_ip), action, status, details, decision_id
            FROM response_actions_log
            WHERE id = %s
            """,
            (log_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        blocked_ip_exists = False
        if row[0] is not None and row[2] == "block_ip":
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM blocked_ips
                    WHERE source_alert_id = %s
                      AND status = 'active'
                )
                """,
                (row[0],),
            )
            blocked_ip_exists = bool(cur.fetchone()[0])

    if row[5] is not None:
        read_model = get_decision_with_latest_outcome(conn, decision_id=row[5])
        if read_model is not None:
            return _wrap_canonical_read_model(
                read_model, source_table="response_actions_log", source_id=log_id
            )

    return infer_response_log_legacy_outcome(
        log_id=log_id,
        alert_id=row[0],
        source_ip=row[1],
        action=row[2],
        status=row[3],
        details=row[4],
        blocked_ip_exists=blocked_ip_exists,
    ).to_read_model()


def resolve_approval_request_outcome(conn, approval_request_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT incident_id, queue_id, playbook_execution_id, action, status,
                   request_reason, decision_id
            FROM approval_requests
            WHERE id = %s
            """,
            (approval_request_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None

    if row[6] is not None:
        read_model = get_decision_with_latest_outcome(conn, decision_id=row[6])
        if read_model is not None:
            return _wrap_canonical_read_model(
                read_model,
                source_table="approval_requests",
                source_id=approval_request_id,
            )

    alert_id = None
    with conn.cursor() as cur:
        if row[1] is not None:
            cur.execute(
                "SELECT alert_id FROM response_actions_queue WHERE id = %s",
                (row[1],),
            )
            queue_alert = cur.fetchone()
            alert_id = queue_alert[0] if queue_alert else None
        elif row[2] is not None:
            cur.execute(
                "SELECT alert_id FROM playbook_executions WHERE id = %s",
                (row[2],),
            )
            execution_alert = cur.fetchone()
            alert_id = execution_alert[0] if execution_alert else None

    return infer_approval_request_legacy_outcome(
        approval_request_id=approval_request_id,
        alert_id=alert_id,
        incident_id=row[0],
        queue_id=row[1],
        playbook_execution_id=row[2],
        action=row[3],
        status=row[4],
        request_reason=row[5],
    ).to_read_model()


def resolve_notification_delivery_outcome(
    conn, notification_delivery_attempt_id: int
) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT alert_id, incident_id, playbook_execution_id, approval_request_id,
                   action, mode, status, metadata, failure_message, decision_id
            FROM notification_delivery_attempts
            WHERE id = %s
            """,
            (notification_delivery_attempt_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None

    if row[9] is not None:
        read_model = get_decision_with_latest_outcome(conn, decision_id=row[9])
        if read_model is not None:
            return _wrap_canonical_read_model(
                read_model,
                source_table="notification_delivery_attempts",
                source_id=notification_delivery_attempt_id,
            )

    return infer_notification_delivery_legacy_outcome(
        attempt_id=notification_delivery_attempt_id,
        alert_id=row[0],
        incident_id=row[1],
        playbook_execution_id=row[2],
        approval_request_id=row[3],
        action=row[4],
        mode=row[5],
        status=row[6],
        metadata=row[7],
        failure_message=row[8],
    ).to_read_model()


def resolve_playbook_execution_outcome(conn, playbook_execution_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT alert_id, incident_id, playbook_id, status, steps_log, failure_reason,
                   decision_id
            FROM playbook_executions
            WHERE id = %s
            """,
            (playbook_execution_id,),
        )
        row = cur.fetchone()
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM notification_delivery_attempts
                WHERE playbook_execution_id = %s
                  AND mode = 'real'
                  AND status = 'success'
                  AND metadata->>'executed' = 'true'
                  AND metadata->>'simulated' = 'false'
                  AND (
                    metadata->>'adapter_mode' = 'real'
                    OR metadata->>'mode' = 'real'
                    OR metadata->>'delivery' IN ('sent', 'delivered', 'accepted', 'success')
                    OR (
                        metadata ? 'http_status'
                        AND (metadata->>'http_status') ~ '^[0-9]+$'
                        AND (metadata->>'http_status')::integer BETWEEN 200 AND 299
                    )
                  )
            )
            """,
            (playbook_execution_id,),
        )
        real_notification_confirmed = bool(cur.fetchone()[0])
    if row is None:
        return None

    if row[6] is not None:
        read_model = get_decision_with_latest_outcome(conn, decision_id=row[6])
        if read_model is not None:
            return _wrap_canonical_read_model(
                read_model,
                source_table="playbook_executions",
                source_id=playbook_execution_id,
            )

    return infer_playbook_execution_legacy_outcome(
        execution_id=playbook_execution_id,
        alert_id=row[0],
        incident_id=row[1],
        playbook_id=row[2],
        status=row[3],
        steps_log=row[4],
        failure_reason=row[5],
        real_notification_confirmed=real_notification_confirmed,
    ).to_read_model()


def resolve_blocked_ip_outcome(conn, blocked_ip_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT host(ip_address), source_alert_id, reason
            FROM blocked_ips
            WHERE id = %s
            """,
            (blocked_ip_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None

    return infer_blocked_ip_legacy_outcome(
        block_id=blocked_ip_id,
        source_ip=row[0],
        source_alert_id=row[1],
        reason=row[2],
    ).to_read_model()


def _record_plan_item(plan: BackfillDryRunPlan, mapping: LegacyMappingResult) -> None:
    plan.total_records_scanned += 1
    if mapping.proposed_decision:
        plan.decisions_by_source[mapping.source_table] += 1
    plan.events_by_source[mapping.source_table] += mapping.proposed_event_count
    plan.mode_state_counts[f"{mapping.execution_mode}/{mapping.execution_state}"] += 1
    if mapping.reason_code:
        plan.reason_code_counts[mapping.reason_code] += 1
    plan.boolean_counts["external_executed"] += int(mapping.external_executed)
    plan.boolean_counts["tracking_recorded"] += int(mapping.tracking_recorded)
    plan.boolean_counts["simulated"] += int(mapping.simulated)
    if (
        mapping.execution_mode == "observed"
        and mapping.execution_state == "observed"
    ):
        plan.observed_only_count += 1
    if mapping.ambiguous or mapping.needs_review:
        plan.ambiguous_records.append(
            {
                "source_table": mapping.source_table,
                "source_id": mapping.source_id,
                "soar_correlation_id": mapping.soar_correlation_id,
                "ambiguity_reason": mapping.ambiguity_reason,
                "execution_mode": mapping.execution_mode,
                "execution_state": mapping.execution_state,
            }
        )


def plan_backfill_dry_run(conn) -> BackfillDryRunPlan:
    plan = BackfillDryRunPlan()

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, host(source_ip), response_action
            FROM alerts
            ORDER BY id
            """
        )
        alert_rows = cur.fetchall()
        for alert_id, source_ip, response_action in alert_rows:
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM response_actions_queue WHERE alert_id = %s)",
                (alert_id,),
            )
            has_queue = bool(cur.fetchone()[0])
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM response_actions_log WHERE alert_id = %s)",
                (alert_id,),
            )
            has_log = bool(cur.fetchone()[0])
            cur.execute(
                """
                SELECT n.id, n.incident_id, n.playbook_execution_id, n.approval_request_id,
                       ar.status AS approval_status, n.action, n.mode, n.status,
                       n.metadata, n.failure_message
                FROM notification_delivery_attempts n
                LEFT JOIN approval_requests ar ON ar.id = n.approval_request_id
                WHERE n.alert_id = %s
                ORDER BY n.created_at DESC, n.id DESC
                LIMIT 1
                """,
                (alert_id,),
            )
            notification_row = cur.fetchone()
            if _find_canonical_decision_id(conn, column="alert_id", value=alert_id):
                continue
            if notification_row is not None:
                mapping = infer_alert_notification_legacy_outcome(
                    alert_id=alert_id,
                    source_ip=source_ip,
                    response_action=response_action,
                    attempt_id=notification_row[0],
                    incident_id=notification_row[1],
                    playbook_execution_id=notification_row[2],
                    approval_request_id=notification_row[3],
                    approval_status=notification_row[4],
                    action=notification_row[5],
                    mode=notification_row[6],
                    status=notification_row[7],
                    metadata=notification_row[8],
                    failure_message=notification_row[9],
                )
            else:
                mapping = infer_alert_legacy_outcome(
                    alert_id=alert_id,
                    source_ip=source_ip,
                    response_action=response_action,
                    has_queue=has_queue,
                    has_log=has_log,
                )
            _record_plan_item(plan, mapping)

        cur.execute(
            """
            SELECT id, alert_id, host(source_ip), action, status, last_error, decision_id
            FROM response_actions_queue
            ORDER BY id
            """
        )
        for queue_id, alert_id, source_ip, action, status, last_error, decision_id in cur.fetchall():
            if decision_id is not None:
                continue
            _record_plan_item(
                plan,
                infer_queue_legacy_outcome(
                    queue_id=queue_id,
                    alert_id=alert_id,
                    source_ip=source_ip,
                    action=action,
                    status=status,
                    last_error=last_error,
                ),
            )

        cur.execute(
            """
            SELECT l.id, l.alert_id, host(l.source_ip), l.action, l.status, l.details, l.decision_id
            FROM response_actions_log l
            ORDER BY l.id
            """
        )
        for log_id, alert_id, source_ip, action, status, details, decision_id in cur.fetchall():
            if decision_id is not None:
                continue
            blocked_ip_exists = False
            if alert_id is not None and action == "block_ip":
                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM blocked_ips
                        WHERE source_alert_id = %s AND status = 'active'
                    )
                    """,
                    (alert_id,),
                )
                blocked_ip_exists = bool(cur.fetchone()[0])
            _record_plan_item(
                plan,
                infer_response_log_legacy_outcome(
                    log_id=log_id,
                    alert_id=alert_id,
                    source_ip=source_ip,
                    action=action,
                    status=status,
                    details=details,
                    blocked_ip_exists=blocked_ip_exists,
                ),
            )

        cur.execute(
            """
            SELECT id, alert_id, incident_id, playbook_id, status, steps_log, failure_reason,
                   decision_id
            FROM playbook_executions
            ORDER BY id
            """
        )
        for row in cur.fetchall():
            if row[7] is not None:
                continue
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM notification_delivery_attempts
                    WHERE playbook_execution_id = %s
                      AND mode = 'real'
                      AND status = 'success'
                      AND metadata->>'executed' = 'true'
                      AND metadata->>'simulated' = 'false'
                      AND (
                        metadata->>'adapter_mode' = 'real'
                        OR metadata->>'mode' = 'real'
                        OR metadata->>'delivery' IN ('sent', 'delivered', 'accepted', 'success')
                        OR (
                            metadata ? 'http_status'
                            AND (metadata->>'http_status') ~ '^[0-9]+$'
                            AND (metadata->>'http_status')::integer BETWEEN 200 AND 299
                        )
                      )
                )
                """,
                (row[0],),
            )
            real_notification_confirmed = bool(cur.fetchone()[0])
            _record_plan_item(
                plan,
                infer_playbook_execution_legacy_outcome(
                    execution_id=row[0],
                    alert_id=row[1],
                    incident_id=row[2],
                    playbook_id=row[3],
                    status=row[4],
                    steps_log=row[5],
                    failure_reason=row[6],
                    real_notification_confirmed=real_notification_confirmed,
                ),
            )

        cur.execute(
            """
            SELECT id, incident_id, queue_id, playbook_execution_id, action, status,
                   request_reason, decision_id
            FROM approval_requests
            ORDER BY id
            """
        )
        for row in cur.fetchall():
            if row[7] is not None:
                continue
            alert_id = None
            if row[2] is not None:
                cur.execute(
                    "SELECT alert_id FROM response_actions_queue WHERE id = %s",
                    (row[2],),
                )
                queue_alert = cur.fetchone()
                alert_id = queue_alert[0] if queue_alert else None
            elif row[3] is not None:
                cur.execute(
                    "SELECT alert_id FROM playbook_executions WHERE id = %s",
                    (row[3],),
                )
                execution_alert = cur.fetchone()
                alert_id = execution_alert[0] if execution_alert else None
            _record_plan_item(
                plan,
                infer_approval_request_legacy_outcome(
                    approval_request_id=row[0],
                    alert_id=alert_id,
                    incident_id=row[1],
                    queue_id=row[2],
                    playbook_execution_id=row[3],
                    action=row[4],
                    status=row[5],
                    request_reason=row[6],
                ),
            )

        cur.execute(
            """
            SELECT id, alert_id, incident_id, playbook_execution_id, approval_request_id,
                   action, mode, status, metadata, failure_message, decision_id
            FROM notification_delivery_attempts
            ORDER BY id
            """
        )
        for row in cur.fetchall():
            if row[10] is not None:
                continue
            if (
                row[3] is not None
                and row[6] == "real"
                and row[7] == "success"
                and _notification_metadata_confirms_execution(row[8])
            ):
                # Playbook-linked notification attempts are represented by the
                # playbook execution outcome when they corroborate a real send.
                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM playbook_executions
                        WHERE id = %s
                          AND decision_id IS NULL
                    )
                    """,
                    (row[3],),
                )
                if bool(cur.fetchone()[0]):
                    continue
            _record_plan_item(
                plan,
                infer_notification_delivery_legacy_outcome(
                    attempt_id=row[0],
                    alert_id=row[1],
                    incident_id=row[2],
                    playbook_execution_id=row[3],
                    approval_request_id=row[4],
                    action=row[5],
                    mode=row[6],
                    status=row[7],
                    metadata=row[8],
                    failure_message=row[9],
                ),
            )

        cur.execute(
            """
            SELECT id, host(ip_address), source_alert_id, reason
            FROM blocked_ips
            WHERE source_alert_id IS NOT NULL
            ORDER BY id
            """
        )
        for block_id, source_ip, source_alert_id, reason in cur.fetchall():
            _record_plan_item(
                plan,
                infer_blocked_ip_legacy_outcome(
                    block_id=block_id,
                    source_ip=source_ip,
                    source_alert_id=source_alert_id,
                    reason=reason,
                ),
            )

    return plan


def format_backfill_plan_summary(plan: BackfillDryRunPlan) -> str:
    summary = plan.to_summary_dict()
    lines = [
        "SOAR outcome backfill dry-run summary",
        "=====================================",
        f"Records scanned (legacy candidates): {summary['total_records_scanned']}",
        f"Proposed decisions: {summary['proposed_decisions']}",
        f"Proposed outcome events: {summary['proposed_events']}",
        f"Observed-only candidates: {summary['observed_only_count']}",
        f"Ambiguous / needs review: {summary['ambiguous_count']}",
        "",
        "Decisions by source:",
    ]
    for source, count in sorted(summary["decisions_by_source"].items()):
        lines.append(f"  - {source}: {count}")
    lines.extend(["", "Events by source:"])
    for source, count in sorted(summary["events_by_source"].items()):
        lines.append(f"  - {source}: {count}")
    lines.extend(["", "Mode/state counts:"])
    for key, count in sorted(summary["mode_state_counts"].items()):
        lines.append(f"  - {key}: {count}")
    lines.extend(["", "Reason code counts:"])
    for key, count in sorted(summary["reason_code_counts"].items()):
        lines.append(f"  - {key}: {count}")
    lines.extend(
        [
            "",
            "Execution boolean totals:",
            f"  - external_executed: {summary['boolean_counts'].get('external_executed', 0)}",
            f"  - tracking_recorded: {summary['boolean_counts'].get('tracking_recorded', 0)}",
            f"  - simulated: {summary['boolean_counts'].get('simulated', 0)}",
        ]
    )
    if summary["ambiguous_records"]:
        lines.extend(["", "Sample ambiguous records (up to 25):"])
        for item in summary["ambiguous_records"]:
            lines.append(
                "  - {source_table}:{source_id} {mode}/{state} ({reason})".format(
                    source_table=item["source_table"],
                    source_id=item["source_id"],
                    mode=item["execution_mode"],
                    state=item["execution_state"],
                    reason=item.get("ambiguity_reason") or "unspecified",
                )
            )
    lines.append("")
    lines.append("Dry-run only: no database writes were performed.")
    return "\n".join(lines)
