"""
SOAR playbook step executor.

Consumes pending playbook_executions and records step outcomes. Notification and
firewall adapter steps remain simulation/real-guarded via adapters. Canonical
`block_ip` / `monitor` / `flag_high_priority` steps also record durable tracking
through the shared response command service (Blocklist tracking only; no host
firewall enforcement).
"""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from core import approval_store
from core import dead_letter_store
from core import notification_delivery_store
from core import playbook_store
from core.playbook_worker_identity import generate_playbook_worker_id
from core.response_command_contracts import ORIGIN_PLAYBOOK, ResponseCommandRequest
from core.response_command_service import execute_response_command
from core.soar_protected_targets import require_unprotected_target
from core.soar_response_outcomes import append_outcome_event
from engines.soar_errors import SkippedAction
from helpers.playbook_enrichment_context import build_playbook_enrichment_context
from engines.playbook_branch_conditions import (
    PlaybookBranchConditionError,
    evaluate_branch_condition,
    resolve_label_target_index,
)
from engines.playbook_param_binding import PlaybookParamBindingError, resolve_step_params
from engines.playbook_registry import ADAPTER_ACTIONS, KNOWN_PLAYBOOK_ACTIONS
from engines.soar_playbook_orchestrator import create_and_link_playbook_execution_decision
from integrations.base_integration import (
    FAILURE_CLASSIFICATION_CIRCUIT_OPEN,
    FAILURE_CLASSIFICATION_CIRCUIT_STATE_INVALID,
    FAILURE_CLASSIFICATION_CREDENTIAL_MISSING,
    FAILURE_CLASSIFICATION_GUARD_FAILED,
    FAILURE_CLASSIFICATION_PROVIDER_RATE_LIMITED,
    FAILURE_CLASSIFICATION_TIMEOUT,
    get_simulated_circuit_breaker_dict,
)
from integrations.integration_registry import execute_playbook_simulated_adapter

logger = logging.getLogger(__name__)

DEFAULT_PLAYBOOK_LEASE_SECONDS = 60
MAX_CHAIN_DEPTH = 3

# spec: SPEC-PLAYBOOK-003
TERMINAL_STATUSES = frozenset({"success", "failed", "abandoned", "permanently_failed"})
_NOTIFICATION_ACTIONS = frozenset(
    {"notify_slack", "notify_teams", "notify_email", "notify_webhook"}
)
_PROVIDER_FOR_ACTION: dict[str, str] = {
    "notify_slack": "slack",
    "notify_teams": "teams",
    "notify_email": "email",
    "notify_webhook": "webhook",
}


# spec: SPEC-NOTIFY-001 / SPEC-UI-004 - delivery status feeds real workflow visibility.
def _delivery_status_from_adapter_result(adapter_result: dict[str, Any]) -> str:
    """Map adapter result to a delivery store status value."""
    if adapter_result.get("success") is True:
        return "success"
    meta = adapter_result.get("metadata") or {}
    fc = str(meta.get("failure_classification") or "").strip().lower()
    if fc == FAILURE_CLASSIFICATION_TIMEOUT:
        return "timeout"
    if fc in (
        FAILURE_CLASSIFICATION_CIRCUIT_OPEN,
        FAILURE_CLASSIFICATION_CIRCUIT_STATE_INVALID,
        FAILURE_CLASSIFICATION_PROVIDER_RATE_LIMITED,
        FAILURE_CLASSIFICATION_GUARD_FAILED,
        FAILURE_CLASSIFICATION_CREDENTIAL_MISSING,
    ):
        return "blocked"
    if (
        str(adapter_result.get("mode") or "").strip().lower() == "real"
        and adapter_result.get("simulated") is True
        and adapter_result.get("executed") is False
    ):
        return "blocked"
    return "failed"


def _make_delivery_correlation_id(provider: str, execution_id: int, step_index: int) -> str:
    return f"ntfy-{provider[:8]}-{execution_id}-{step_index}-{uuid.uuid4().hex[:12]}"


def _make_delivery_idempotency_key(
    provider: str, action: str, execution_id: int, step_index: int
) -> str:
    raw = f"{provider}:{action}:{execution_id}:{step_index}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


def _existing_active_delivery(conn, provider: str, action: str, execution_id: int, step_index: int):
    idempotency_key = _make_delivery_idempotency_key(provider, action, execution_id, step_index)
    rows = notification_delivery_store.list_notification_delivery_attempts(
        conn,
        idempotency_key=idempotency_key,
        limit=10,
    )
    for row in rows:
        if row.get("status") in ("success", "pending"):
            return row
    return None


def _record_notification_delivery_attempt(
    conn,
    execution: dict[str, Any],
    step: dict[str, Any],
    step_index: int,
    entry: dict[str, Any],
    now: datetime,
) -> dict[str, Any] | None:
    """
    Append an immutable delivery record for a notification step.
    Failures here are logged but never propagate to the step outcome.
    """
    try:
        action = step.get("action")
        provider = _PROVIDER_FOR_ACTION.get(action)
        if provider is None:
            return None

        adapter_name, adapter_action = ADAPTER_ACTIONS[action]
        adapter_result: dict[str, Any] = (entry.get("output") or {}).get("adapter_result") or {}

        result_mode = str(adapter_result.get("mode") or "simulation").strip().lower()
        if result_mode not in ("simulation", "real"):
            result_mode = "simulation"

        status = _delivery_status_from_adapter_result(adapter_result)

        circuit_snapshot = (entry.get("output") or {}).get("circuit_breaker") or {}
        circuit_state_raw = circuit_snapshot.get("state") or (
            (adapter_result.get("metadata") or {}).get("circuit_state")
        )
        circuit_state: str | None = None
        if circuit_state_raw:
            candidate = str(circuit_state_raw).strip().lower()
            if candidate in ("closed", "open", "half_open", "unknown", "invalid"):
                circuit_state = candidate

        meta = adapter_result.get("metadata") or {}
        timeout_seconds: int | None = None
        raw_timeout = meta.get("timeout_seconds")
        if raw_timeout is not None:
            try:
                timeout_seconds = int(raw_timeout)
            except (TypeError, ValueError):
                pass

        failure_code: str | None = None
        failure_message: str | None = None
        if not adapter_result.get("success"):
            err = entry.get("error")
            if isinstance(err, dict):
                failure_code = err.get("code")
                failure_message = err.get("message")

        safe_meta: dict[str, Any] = {}
        if isinstance(meta, dict):
            safe_meta.update(meta)
        safe_meta["adapter_mode"] = adapter_result.get("mode")
        safe_meta["simulated"] = adapter_result.get("simulated")
        safe_meta["executed"] = adapter_result.get("executed")

        execution_id: int = execution["id"]
        delivery_attempt = notification_delivery_store.create_notification_delivery_attempt(
            conn,
            correlation_id=_make_delivery_correlation_id(provider, execution_id, step_index),
            idempotency_key=_make_delivery_idempotency_key(
                provider, action, execution_id, step_index
            ),
            provider=provider,
            mode=result_mode,
            status=status,
            adapter_name=adapter_name,
            action=adapter_action,
            metadata=safe_meta,
            playbook_execution_id=execution_id,
            playbook_step_index=step_index,
            incident_id=execution.get("incident_id"),
            approval_request_id=None,
            alert_id=execution.get("alert_id"),
            started_at=now,
            completed_at=now,
            failure_code=failure_code,
            failure_message=failure_message,
            timeout_seconds=timeout_seconds,
            circuit_breaker_state=circuit_state,
        )
        _append_notification_delivery_outcome_event(conn, execution, delivery_attempt)
        return {
            "id": delivery_attempt.get("id"),
            "provider": delivery_attempt.get("provider"),
            "mode": delivery_attempt.get("mode"),
            "status": delivery_attempt.get("status"),
            "adapter_name": delivery_attempt.get("adapter_name"),
            "action": delivery_attempt.get("action"),
            "playbook_step_index": delivery_attempt.get("playbook_step_index"),
            "failure_code": delivery_attempt.get("failure_code"),
            "failure_message": delivery_attempt.get("failure_message"),
            "circuit_breaker_state": delivery_attempt.get("circuit_breaker_state"),
        }
    except Exception:
        logger.warning(
            "[PLAYBOOK SIMULATION] delivery tracking failed safely "
            "execution_id=%s step_index=%s",
            execution.get("id"),
            step_index,
            exc_info=True,
        )
        return None


def process_next_pending_playbook_execution(
    conn,
    now=None,
    *,
    worker_id: str | None = None,
    lease_duration_seconds: int | None = None,
) -> dict[str, Any] | None:
    owner = _resolve_worker_id(worker_id)
    duration = _coerce_lease_duration(lease_duration_seconds)
    claimed = playbook_store.claim_next_pending_playbook_execution_with_lease(
        conn,
        owner,
        lease_duration_seconds=duration,
        now=_coerce_now(now),
    )
    if claimed is None:
        return None
    _append_playbook_running_outcome_event(conn, claimed)
    return _process_running_execution(
        conn,
        claimed,
        now=_coerce_now(now),
        prior_status="pending",
        worker_id=owner,
        lease_duration_seconds=duration,
    )


def process_playbook_execution(
    conn,
    execution_id: int,
    now=None,
    *,
    worker_id: str | None = None,
    lease_duration_seconds: int | None = None,
) -> dict[str, Any]:
    execution = playbook_store.get_playbook_execution(conn, execution_id)
    if execution is None:
        return {
            "execution_id": execution_id,
            "playbook_id": None,
            "prior_status": None,
            "new_status": None,
            "outcome": "skipped",
            "reason": "execution_not_found",
            "steps_processed": 0,
            "message": "Playbook execution not found.",
        }

    owner = _resolve_worker_id(worker_id)
    duration = _coerce_lease_duration(lease_duration_seconds)
    timestamp = _coerce_now(now)

    prior_status = execution["status"]
    if prior_status in TERMINAL_STATUSES:
        return {
            "execution_id": execution_id,
            "playbook_id": execution["playbook_id"],
            "prior_status": prior_status,
            "new_status": prior_status,
            "outcome": "skipped",
            "reason": "terminal_status",
            "steps_processed": 0,
            "message": "Terminal playbook execution was not re-run.",
        }

    if prior_status == "running":
        if execution.get("lease_owner") and execution.get("lease_owner") != owner:
            logger.info(
                "[PLAYBOOK SIMULATION] lease skip execution_id=%s worker_id=%s owner=%s reason=lease_not_owned",
                execution_id,
                owner,
                execution.get("lease_owner"),
            )
            return _skip_result(
                execution,
                prior_status,
                "lease_not_owned",
                "Running playbook execution is owned by another worker.",
            )
        if execution.get("lease_owner") == owner:
            return _process_running_execution(
                conn,
                execution,
                now=timestamp,
                prior_status=prior_status,
                worker_id=owner,
                lease_duration_seconds=duration,
            )
        return {
            "execution_id": execution_id,
            "playbook_id": execution["playbook_id"],
            "prior_status": prior_status,
            "new_status": prior_status,
            "outcome": "skipped",
            "reason": "already_running",
            "steps_processed": 0,
            "message": "Running playbook execution was not re-run.",
        }

    if prior_status == "awaiting_approval":
        return _process_awaiting_approval_execution(
            conn,
            execution,
            now=timestamp,
            worker_id=owner,
            lease_duration_seconds=duration,
        )

    if prior_status != "pending":
        return {
            "execution_id": execution_id,
            "playbook_id": execution["playbook_id"],
            "prior_status": prior_status,
            "new_status": prior_status,
            "outcome": "skipped",
            "reason": "unsupported_status",
            "steps_processed": 0,
            "message": "Playbook execution status is not processable.",
        }

    running = playbook_store.acquire_execution_lease(
        conn,
        execution_id,
        owner,
        lease_duration_seconds=duration,
        now=timestamp,
    )
    if running is None:
        latest = playbook_store.get_playbook_execution(conn, execution_id) or execution
        reason = "lease_not_acquired"
        if latest.get("status") != "pending":
            reason = "claim_failed"
        logger.info(
            "[PLAYBOOK SIMULATION] lease acquire skip execution_id=%s worker_id=%s reason=%s latest_status=%s",
            execution_id,
            owner,
            reason,
            latest.get("status"),
        )
        return _skip_result(
            execution,
            prior_status,
            reason,
            "Playbook execution could not be leased for processing.",
            new_status=latest.get("status"),
        )
    _append_playbook_running_outcome_event(conn, running)
    return _process_running_execution(
        conn,
        running,
        now=timestamp,
        prior_status=prior_status,
        worker_id=owner,
        lease_duration_seconds=duration,
    )


def process_playbook_execution_batch(
    conn,
    limit=10,
    now=None,
    *,
    worker_id: str | None = None,
    lease_duration_seconds: int | None = None,
) -> dict[str, Any]:
    owner = _resolve_worker_id(worker_id)
    duration = _coerce_lease_duration(lease_duration_seconds)
    logger.info("[PLAYBOOK SIMULATION] worker_id=%s batch_limit=%s", owner, limit)

    batch_limit = _normalize_limit(limit)
    results = []
    for _ in range(batch_limit):
        result = process_next_pending_playbook_execution(
            conn,
            now=now,
            worker_id=owner,
            lease_duration_seconds=duration,
        )
        if result is None:
            break
        results.append(result)

    remaining = batch_limit - len(results)
    if remaining > 0:
        awaiting_rows = playbook_store.list_awaiting_approval_playbook_executions(
            conn,
            limit=remaining,
        )
        for row in awaiting_rows:
            results.append(
                process_playbook_execution(
                    conn,
                    row["id"],
                    now=now,
                    worker_id=owner,
                    lease_duration_seconds=duration,
                )
            )

    return {
        "processed": len(results),
        "success": sum(1 for row in results if row.get("outcome") == "success"),
        "failed": sum(1 for row in results if row.get("outcome") == "failed"),
        "skipped": sum(1 for row in results if row.get("outcome") == "skipped"),
        "results": results,
    }


def _process_running_execution(
    conn,
    execution: dict[str, Any],
    now=None,
    prior_status: str | None = None,
    *,
    worker_id: str | None = None,
    lease_duration_seconds: int | None = None,
) -> dict[str, Any]:
    execution_id = execution["id"]
    playbook_id = execution["playbook_id"]
    prior = prior_status or execution["status"]
    timestamp = _coerce_now(now)
    owner = _resolve_worker_id(worker_id or execution.get("lease_owner"))
    duration = _coerce_lease_duration(lease_duration_seconds)

    definition = playbook_store.get_playbook_definition(conn, playbook_id)
    if definition is None:
        steps_log = [
            _failure_entry(
                step_index=None,
                action=None,
                message="Playbook definition not found.",
                code="definition_not_found",
                now=timestamp,
            )
        ]
        _finalize_failed(
            conn,
            execution_id,
            owner,
            steps_log,
            last_completed_step=None,
            now=timestamp,
        )
        return _result(
            execution,
            prior,
            "failed",
            "failed",
            len(steps_log),
            "Playbook definition not found.",
        )

    steps = definition.get("steps")
    if not isinstance(steps, list):
        steps_log = [
            _failure_entry(
                step_index=None,
                action=None,
                message="Playbook definition steps must be a list.",
                code="invalid_steps",
                now=timestamp,
            )
        ]
        _finalize_failed(
            conn,
            execution_id,
            owner,
            steps_log,
            last_completed_step=None,
            now=timestamp,
        )
        return _result(
            execution,
            prior,
            "failed",
            "failed",
            len(steps_log),
            "Playbook definition steps are invalid.",
        )

    start_index, steps_log, last_completed_step = _resume_progress(execution)

    return _process_steps(
        conn,
        execution,
        steps,
        timestamp,
        prior,
        start_index=min(start_index, len(steps)),
        steps_log=steps_log,
        last_completed_step=last_completed_step,
        worker_id=owner,
        lease_duration_seconds=duration,
    )


def _process_awaiting_approval_execution(
    conn,
    execution: dict[str, Any],
    now=None,
    *,
    worker_id: str | None = None,
    lease_duration_seconds: int | None = None,
) -> dict[str, Any]:
    timestamp = _coerce_now(now)
    owner = _resolve_worker_id(worker_id)
    duration = _coerce_lease_duration(lease_duration_seconds)
    steps_log = list(execution.get("steps_log") or [])
    approval_entry = _latest_gate_entry(steps_log)
    if approval_entry is None:
        return _fail_awaiting_execution(
            conn,
            execution,
            steps_log,
            None,
            "missing_approval_gate",
            "Awaiting approval execution has no approval gate entry.",
            timestamp,
            worker_id=owner,
        )

    gate_index = approval_entry["step_index"]
    approval_request = approval_store.get_latest_playbook_step_approval_request(
        conn,
        playbook_execution_id=execution["id"],
        playbook_step_index=gate_index,
        materialize_expired=True,
        now=timestamp,
    )
    if approval_request is None:
        return _fail_awaiting_execution(
            conn,
            execution,
            steps_log,
            gate_index,
            "missing_approval_request",
            "Linked approval request was not found.",
            timestamp,
            worker_id=owner,
        )

    if approval_request["status"] == "pending":
        return {
            "execution_id": execution["id"],
            "playbook_id": execution["playbook_id"],
            "prior_status": "awaiting_approval",
            "new_status": "awaiting_approval",
            "outcome": "skipped",
            "reason": "approval_pending",
            "steps_processed": 0,
            "message": "Playbook execution is still awaiting approval.",
        }

    if approval_request["status"] == "approved":
        _append_playbook_approval_decision_outcome_event(
            conn,
            execution,
            approval_request=approval_request,
            event_type="approval_approved",
            execution_state="running",
            summary="Approval granted for simulated playbook gate.",
        )
        if not _has_gate_event(steps_log, gate_index, approval_request["id"], "approval_approved"):
            steps_log.append(
                _approval_decision_entry(
                    step_index=gate_index,
                    approval_request=approval_request,
                    status="approved",
                    event="approval_approved",
                    message="Approval granted for simulated playbook gate.",
                    now=timestamp,
                )
            )
        if not _has_gate_event(steps_log, gate_index, approval_request["id"], "approval_resumed"):
            steps_log.append(
                _approval_decision_entry(
                    step_index=gate_index,
                    approval_request=approval_request,
                    status="resumed",
                    event="approval_resumed",
                    message="Simulation resumed after approval.",
                    now=timestamp,
                )
            )

        resumed = playbook_store.acquire_awaiting_approval_resume_lease(
            conn,
            execution["id"],
            owner,
            steps_log,
            gate_index,
            lease_duration_seconds=duration,
            now=timestamp,
        )
        if resumed is None:
            latest = playbook_store.get_playbook_execution(conn, execution["id"]) or execution
            return _skip_result(
                execution,
                "awaiting_approval",
                "lease_not_acquired",
                "Playbook execution could not be leased for approval resume.",
                new_status=latest.get("status"),
            )

        _append_playbook_running_outcome_event(conn, resumed)
        _append_playbook_resumed_outcome_event(
            conn,
            resumed,
            approval_request=approval_request,
        )

        definition = playbook_store.get_playbook_definition(conn, execution["playbook_id"])
        if definition is None or not isinstance(definition.get("steps"), list):
            return _fail_awaiting_execution(
                conn,
                resumed,
                steps_log,
                gate_index,
                "invalid_resume_definition",
                "Playbook definition could not be loaded for approval resume.",
                timestamp,
                prior_status="awaiting_approval",
                worker_id=owner,
            )

        return _process_steps(
            conn,
            resumed,
            definition["steps"],
            timestamp,
            "awaiting_approval",
            start_index=gate_index + 1,
            steps_log=steps_log,
            last_completed_step=gate_index,
            worker_id=owner,
            lease_duration_seconds=duration,
        )

    if approval_request["status"] in {"denied", "expired"}:
        event = f"approval_{approval_request['status']}"
        definition = playbook_store.get_playbook_definition(conn, execution["playbook_id"])
        steps = definition.get("steps") if definition else []
        gate_step = (
            steps[gate_index]
            if isinstance(steps, list)
            and 0 <= gate_index < len(steps)
            and isinstance(steps[gate_index], dict)
            else {}
        )
        terminal_key = "on_denied" if approval_request["status"] == "denied" else "on_expired"
        terminal_behavior = gate_step.get(terminal_key, "fail")
        branch_continue = terminal_behavior == "branch" and isinstance(steps, list)
        _append_playbook_approval_decision_outcome_event(
            conn,
            execution,
            approval_request=approval_request,
            event_type=event,
            execution_state="running" if branch_continue else "blocked",
            summary=(
                f"Approval {approval_request['status']}; simulated playbook "
                f"{'continuing to branch path.' if branch_continue else 'stopped safely.'}"
            ),
        )
        if not _has_gate_event(steps_log, gate_index, approval_request["id"], event):
            steps_log.append(
                _approval_decision_entry(
                    step_index=gate_index,
                    approval_request=approval_request,
                    status=approval_request["status"],
                    event=event,
                    message=f"Approval {approval_request['status']}; later steps were not run.",
                    now=timestamp,
                )
            )

        if branch_continue:
            resumed = playbook_store.acquire_awaiting_approval_resume_lease(
                conn,
                execution["id"],
                owner,
                steps_log,
                gate_index,
                lease_duration_seconds=duration,
                now=timestamp,
            )
            if resumed is None:
                latest = playbook_store.get_playbook_execution(conn, execution["id"]) or execution
                return _skip_result(
                    execution,
                    "awaiting_approval",
                    "lease_not_acquired",
                    "Playbook execution could not be leased for approval branch resume.",
                    new_status=latest.get("status"),
                )

            _append_playbook_running_outcome_event(conn, resumed)
            return _process_steps(
                conn,
                resumed,
                steps,
                timestamp,
                "awaiting_approval",
                start_index=gate_index + 1,
                steps_log=steps_log,
                last_completed_step=gate_index,
                worker_id=owner,
                lease_duration_seconds=duration,
            )

        if isinstance(steps, list):
            steps_log.extend(
                _skipped_later_step_entries(
                    steps,
                    start_index=gate_index + 1,
                    reason=f"approval_{approval_request['status']}",
                    now=timestamp,
                )
            )

        _finalize_failed(
            conn,
            execution["id"],
            owner,
            steps_log,
            last_completed_step=execution.get("last_completed_step"),
            now=timestamp,
        )
        return _result(
            execution,
            "awaiting_approval",
            "failed",
            "failed",
            0,
            f"Approval {approval_request['status']}; simulated playbook stopped safely.",
        )

    return {
        "execution_id": execution["id"],
        "playbook_id": execution["playbook_id"],
        "prior_status": "awaiting_approval",
        "new_status": "awaiting_approval",
        "outcome": "skipped",
        "reason": "unsupported_approval_status",
        "steps_processed": 0,
        "message": "Linked approval status is not processable.",
    }


def _process_steps(
    conn,
    execution: dict[str, Any],
    steps: list[dict[str, Any]],
    timestamp: datetime,
    prior: str,
    *,
    start_index: int,
    steps_log: list[dict[str, Any]],
    last_completed_step: int | None,
    worker_id: str,
    lease_duration_seconds: int,
) -> dict[str, Any]:
    execution_id = execution["id"]
    playbook_id = execution["playbook_id"]
    failed = False
    failure_message = None

    index = start_index
    while index < len(steps):
        step = steps[index]
        # spec: SPEC-PLAYBOOK-003
        # Defensive guard: if steps_log already has a success entry for this index (e.g.
        # last_completed_step and steps_log diverged after a crash + recovery), skip the
        # step entirely so notification/remediation side effects are never duplicated.
        if _step_already_succeeded_in_log(steps_log, index):
            last_completed_step = index
            index += 1
            continue

        if _step_already_skipped_in_log(steps_log, index):
            index += 1
            continue

        if not _heartbeat_lease(
            conn,
            execution_id,
            worker_id,
            timestamp,
            lease_duration_seconds,
        ):
            logger.warning(
                "[PLAYBOOK SIMULATION] lease lost before step execution_id=%s worker_id=%s step_index=%s",
                execution_id,
                worker_id,
                index,
            )
            return _result(
                execution,
                prior,
                execution.get("status") or "running",
                "skipped",
                len(steps_log),
                "Playbook execution lease was lost before step execution.",
                reason="lease_lost",
            )

        if isinstance(step, dict) and step.get("action") == "require_approval":
            # spec: SPEC-PLAYBOOK-002
            approval_request = approval_store.create_playbook_step_approval_request(
                conn,
                playbook_execution_id=execution_id,
                playbook_step_index=index,
                request_reason=step.get("reason") or "Approval required before continuing simulated playbook.",
                risk_level=step.get("risk_level", "high"),
                ttl_minutes=step.get(
                    "expires_in_minutes",
                    approval_store.DEFAULT_APPROVAL_TTL_MINUTES,
                ),
            )
            entry = _approval_requested_entry(
                step_index=index,
                approval_request=approval_request,
                step=step,
                now=timestamp,
            )
            steps_log.append(entry)
            updated = playbook_store.set_playbook_execution_awaiting_approval(
                conn,
                execution_id,
                steps_log,
                last_completed_step=last_completed_step,
                lease_owner=worker_id,
            )
            if updated is None:
                logger.warning(
                    "[PLAYBOOK SIMULATION] lease lost while pausing for approval execution_id=%s worker_id=%s step_index=%s",
                    execution_id,
                    worker_id,
                    index,
                )
                return _result(
                    execution,
                    prior,
                    execution.get("status") or "running",
                    "skipped",
                    len(steps_log),
                    "Playbook execution lease was lost while pausing for approval.",
                    reason="lease_lost",
                )
            _append_playbook_awaiting_approval_outcome_event(
                conn,
                updated,
                approval_request=approval_request,
                step_index=index,
                summary=entry["message"],
            )
            playbook_store.release_execution_lease(conn, execution_id, worker_id)
            return _result(
                execution,
                prior,
                "awaiting_approval",
                "awaiting_approval",
                len(steps_log),
                "Approval requested before continuing simulated playbook.",
            )

        if isinstance(step, dict) and step.get("action") == "branch":
            entry, skip_entries, next_index = _execute_branch_step(
                conn,
                step,
                index,
                steps,
                steps_log,
                execution,
                timestamp,
            )
            steps_log.append(entry)
            steps_log.extend(skip_entries)
            _append_non_adapter_playbook_step_outcome_event(conn, execution, entry)
            if entry["status"] == "success":
                last_completed_step = index
                if (
                    playbook_store.update_playbook_execution_step_log(
                        conn,
                        execution_id,
                        steps_log,
                        last_completed_step=last_completed_step,
                        lease_owner=worker_id,
                    )
                    is None
                ):
                    logger.warning(
                        "[PLAYBOOK SIMULATION] lease lost while saving branch progress execution_id=%s worker_id=%s step_index=%s",
                        execution_id,
                        worker_id,
                        index,
                    )
                    return _result(
                        execution,
                        prior,
                        execution.get("status") or "running",
                        "skipped",
                        len(steps_log),
                        "Playbook execution lease was lost while saving branch progress.",
                        reason="lease_lost",
                    )
                index = next_index
                continue

            failed = True
            failure_message = entry["message"]
            on_failure = step.get("on_failure", "abort")
            if on_failure != "continue":
                break
            index += 1
            continue

        if isinstance(step, dict) and step.get("action") == "trigger_playbook":
            entry = _execute_trigger_playbook_step(conn, step, index, execution, timestamp)
            steps_log.append(entry)
            _append_non_adapter_playbook_step_outcome_event(conn, execution, entry)
            if entry["status"] == "success":
                last_completed_step = index
                if (
                    playbook_store.update_playbook_execution_step_log(
                        conn,
                        execution_id,
                        steps_log,
                        last_completed_step=last_completed_step,
                        lease_owner=worker_id,
                    )
                    is None
                ):
                    logger.warning(
                        "[PLAYBOOK SIMULATION] lease lost while saving trigger_playbook progress "
                        "execution_id=%s worker_id=%s step_index=%s",
                        execution_id,
                        worker_id,
                        index,
                    )
                    return _result(
                        execution,
                        prior,
                        execution.get("status") or "running",
                        "skipped",
                        len(steps_log),
                        "Playbook execution lease was lost while saving trigger_playbook progress.",
                        reason="lease_lost",
                    )
                index += 1
                continue

            failed = True
            failure_message = entry["message"]
            on_failure = step.get("on_failure", "abort")
            if on_failure != "continue":
                break
            index += 1
            continue

        if isinstance(step, dict) and step.get("action") == "enrich_context":
            entry = _execute_enrich_context_step(conn, step, index, execution, timestamp)
            steps_log.append(entry)
            _append_non_adapter_playbook_step_outcome_event(conn, execution, entry)
            if entry["status"] == "success":
                last_completed_step = index
                if (
                    playbook_store.update_playbook_execution_step_log(
                        conn,
                        execution_id,
                        steps_log,
                        last_completed_step=last_completed_step,
                        lease_owner=worker_id,
                    )
                    is None
                ):
                    logger.warning(
                        "[PLAYBOOK SIMULATION] lease lost while saving enrich_context progress "
                        "execution_id=%s worker_id=%s step_index=%s",
                        execution_id,
                        worker_id,
                        index,
                    )
                    return _result(
                        execution,
                        prior,
                        execution.get("status") or "running",
                        "skipped",
                        len(steps_log),
                        "Playbook execution lease was lost while saving enrich_context progress.",
                        reason="lease_lost",
                    )
                index += 1
                continue

            failed = True
            failure_message = entry["message"]
            on_failure = step.get("on_failure", "abort")
            if on_failure != "continue":
                break
            index += 1
            continue

        try:
            entry = _simulate_step(conn, step, index, timestamp, execution)
        except Exception as error:
            logger.exception(
                "[PLAYBOOK SIMULATION] step simulation failed execution_id=%s playbook_id=%s step_index=%s",
                execution_id,
                playbook_id,
                index,
            )
            entry = _failure_entry(
                step_index=index,
                action=step.get("action") if isinstance(step, dict) else None,
                message=str(error),
                code="simulation_exception",
                now=timestamp,
            )

        steps_log.append(entry)

        if (
            isinstance(step, dict)
            and step.get("action") in _NOTIFICATION_ACTIONS
            and entry.get("skipped") is not True
        ):
            delivery_attempt = _record_notification_delivery_attempt(
                conn, execution, step, index, entry, timestamp
            )
            if delivery_attempt is not None:
                output = entry.setdefault("output", {})
                if isinstance(output, dict):
                    output["notification_delivery"] = delivery_attempt

        if entry["status"] == "success":
            last_completed_step = index
            if (
                playbook_store.update_playbook_execution_step_log(
                    conn,
                    execution_id,
                    steps_log,
                    last_completed_step=last_completed_step,
                    lease_owner=worker_id,
                )
                is None
            ):
                logger.warning(
                    "[PLAYBOOK SIMULATION] lease lost while saving progress execution_id=%s worker_id=%s step_index=%s",
                    execution_id,
                    worker_id,
                    index,
                )
                return _result(
                    execution,
                    prior,
                    execution.get("status") or "running",
                    "skipped",
                    len(steps_log),
                    "Playbook execution lease was lost while saving step progress.",
                    reason="lease_lost",
                )
            _append_non_adapter_playbook_step_outcome_event(conn, execution, entry)
            index += 1
            continue

        _append_non_adapter_playbook_step_outcome_event(conn, execution, entry)
        failed = True
        failure_message = entry["message"]
        on_failure = step.get("on_failure", "abort") if isinstance(step, dict) else "abort"
        if on_failure != "continue":
            break
        index += 1

    if failed:
        _finalize_failed(
            conn,
            execution_id,
            worker_id,
            steps_log,
            last_completed_step=last_completed_step,
            now=timestamp,
        )
        return _result(
            execution,
            prior,
            "failed",
            "failed",
            len(steps_log),
            failure_message or "One or more simulated playbook steps failed.",
        )

    _finalize_success(
        conn,
        execution_id,
        worker_id,
        steps_log,
        last_completed_step=last_completed_step,
        now=timestamp,
    )
    return _result(
        execution,
        prior,
        "success",
        "success",
        len(steps_log),
        "Simulated playbook execution completed successfully.",
    )


def _resume_progress(
    execution: dict[str, Any],
) -> tuple[int, list[dict[str, Any]], int | None]:
    steps_log = list(execution.get("steps_log") or [])
    last_completed_step = execution.get("last_completed_step")
    if last_completed_step is None:
        return 0, steps_log, None
    try:
        completed = int(last_completed_step)
    except (TypeError, ValueError):
        return 0, steps_log, None
    if completed < 0:
        return 0, steps_log, None
    return completed + 1, steps_log, completed


def _simulate_step(
    conn,
    step: dict[str, Any],
    step_index: int,
    now: datetime,
    execution: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(step, dict):
        return _failure_entry(
            step_index=step_index,
            action=None,
            message="Playbook step must be an object.",
            code="invalid_step",
            now=now,
        )

    action = step.get("action")
    if not isinstance(action, str) or not action:
        return _failure_entry(
            step_index=step_index,
            action=action,
            message="Playbook step action is required.",
            code="missing_action",
            now=now,
        )

    if action in ADAPTER_ACTIONS:
        return _simulate_adapter_step(conn, step, step_index, now, execution)

    if action not in KNOWN_PLAYBOOK_ACTIONS:
        return _failure_entry(
            step_index=step_index,
            action=action,
            message="Unsupported playbook step action.",
            code="unsupported_action",
            now=now,
        )

    if action in {"monitor", "flag_high_priority"}:
        return _execute_canonical_response_step(
            conn, step, step_index, now, execution, action=action
        )

    messages = {
        "monitor": "[SIMULATED PLAYBOOK STEP] monitor",
        "flag_high_priority": "[SIMULATED PLAYBOOK STEP] flag_high_priority",
        "block_ip": "[SIMULATED PLAYBOOK STEP] block_ip",
    }
    entry = {
        "step_index": step_index,
        "action": action,
        "status": "success",
        "mode": "simulation",
        "started_at": _iso(now),
        "completed_at": _iso(now),
        "message": messages.get(action, f"[PLAYBOOK STEP] {action}"),
        "output": {
            "simulated": True,
            "executed": False,
        },
        "error": None,
    }
    if isinstance(step.get("label"), str) and step.get("label"):
        entry["label"] = step["label"]
    return entry


def _execute_canonical_response_step(
    conn,
    step: dict[str, Any],
    step_index: int,
    now: datetime,
    execution: dict[str, Any],
    *,
    action: str,
) -> dict[str, Any]:
    raw_params = step.get("params") if isinstance(step.get("params"), dict) else {}
    try:
        params = resolve_step_params(conn, raw_params, execution=execution)
    except PlaybookParamBindingError as error:
        return _failure_entry(
            step_index=step_index,
            action=action,
            message=error.message,
            code=error.code,
            now=now,
        )

    source_ip = params.get("source_ip") or execution.get("source_ip")
    result = execute_response_command(
        conn,
        ResponseCommandRequest(
            action=action,
            indicator_value=str(source_ip) if source_ip else None,
            alert_id=execution.get("alert_id"),
            incident_id=execution.get("incident_id"),
            reason=params.get("reason") or f"Playbook step {action}",
            origin_surface=ORIGIN_PLAYBOOK,
            playbook_execution_id=execution.get("id"),
            playbook_step_index=step_index,
            idempotency_key=f"playbook-{execution.get('id')}-{step_index}-{action}",
            safe_metadata={"playbook_id": execution.get("playbook_id")},
        ),
    )
    if not result.success:
        return _failure_entry(
            step_index=step_index,
            action=action,
            message=result.error or result.message,
            code=result.error_code or "response_command_failed",
            now=now,
        )
    entry = {
        "step_index": step_index,
        "action": action,
        "status": "success",
        "mode": "simulation",
        "started_at": _iso(now),
        "completed_at": _iso(now),
        "message": result.message,
        "output": {
            "simulated": False,
            "executed": True,
            "enforcement": result.enforcement,
            "registry_record_id": result.registry_record_id,
            "registry_event_id": result.registry_event_id,
            "blocked_ip_id": result.blocked_ip_id,
            "incident_id": result.incident_id,
            "disposition": result.disposition,
            "canonical_response": True,
        },
        "error": None,
    }
    if isinstance(step.get("label"), str) and step.get("label"):
        entry["label"] = step["label"]
    return entry


def _simulate_adapter_step(
    conn,
    step: dict[str, Any],
    step_index: int,
    now: datetime,
    execution: dict[str, Any],
) -> dict[str, Any]:
    action = step["action"]
    adapter_name, adapter_action = ADAPTER_ACTIONS[action]
    # spec: SPEC-INTEG-005 / SPEC-UI-004 - dedup prevents duplicate sends before adapter execution.
    if action in _NOTIFICATION_ACTIONS:
        provider = _PROVIDER_FOR_ACTION[action]
        existing_delivery = _existing_active_delivery(
            conn,
            provider,
            action,
            execution["id"],
            step_index,
        )
        if existing_delivery is not None:
            entry = {
                "step_index": step_index,
                "action": action,
                "status": "success",
                "event": "notification_delivery_already_delivered",
                "mode": "simulation",
                "simulated": True,
                "executed": False,
                "skipped": True,
                "started_at": _iso(now),
                "completed_at": _iso(now),
                "message": "Notification delivery already succeeded; adapter call skipped.",
                "output": {
                    "simulated": True,
                    "executed": False,
                    "skipped": True,
                    "skip_reason": f"delivery_{existing_delivery.get('status')}",
                    "failure_classification": "duplicate_delivery",
                    "existing_delivery_id": existing_delivery.get("id"),
                    "existing_delivery_status": existing_delivery.get("status"),
                    "idempotency_key": existing_delivery.get("idempotency_key"),
                },
                "error": None,
            }
            if isinstance(step.get("label"), str) and step.get("label"):
                entry["label"] = step["label"]
            return entry
    raw_params = step.get("params") if isinstance(step.get("params"), dict) else {}
    try:
        params = resolve_step_params(conn, raw_params, execution=execution)
    except PlaybookParamBindingError as error:
        return _failure_entry(
            step_index=step_index,
            action=action,
            message=error.message,
            code=error.code,
            now=now,
        )

    if action == "block_ip":
        try:
            require_unprotected_target(params.get("source_ip"))
        except SkippedAction as error:
            return _failure_entry(
                step_index=step_index,
                action=action,
                message=str(error),
                code=error.code,
                now=now,
            )

    context = {
        "execution_id": execution["id"],
        "playbook_id": execution["playbook_id"],
        "alert_id": execution.get("alert_id"),
        "incident_id": execution.get("incident_id"),
        "step_index": step_index,
    }

    try:
        adapter_result = execute_playbook_simulated_adapter(
            adapter_name,
            adapter_action,
            params=params,
            context=context,
        )
    except Exception as error:
        return _failure_entry(
            step_index=step_index,
            action=action,
            message=f"Simulated adapter action failed safely: {error}",
            code="adapter_simulation_failed",
            now=now,
            output={
                "simulated": True,
                "executed": False,
                "adapter": adapter_name,
                "adapter_action": adapter_action,
                "circuit_breaker": get_simulated_circuit_breaker_dict(adapter_name, now=now),
            },
        )

    status = "success" if adapter_result.get("success") is True else "failed"
    result_mode = str(adapter_result.get("mode") or "simulation").strip().lower()
    if result_mode not in ("simulation", "real"):
        result_mode = "simulation"
    adapter_simulated = (
        adapter_result.get("simulated")
        if isinstance(adapter_result.get("simulated"), bool)
        else result_mode != "real"
    )
    adapter_executed = adapter_result.get("executed") is True
    message = (
        adapter_result.get("message")
        or (
            "Real adapter action completed."
            if result_mode == "real" and adapter_executed
            else "Simulated adapter action completed."
        )
        if status == "success"
        else adapter_result.get("message") or "Adapter action failed safely."
    )
    circuit_snapshot = get_simulated_circuit_breaker_dict(adapter_name, now=now)
    err_meta = adapter_result.get("metadata")
    err_code = "adapter_simulation_failed"
    if status != "success" and isinstance(err_meta, dict):
        fc = str(err_meta.get("failure_classification") or "").strip().lower()
        if fc == FAILURE_CLASSIFICATION_CIRCUIT_STATE_INVALID:
            err_code = "circuit_breaker_invalid"
        elif fc == FAILURE_CLASSIFICATION_CIRCUIT_OPEN:
            err_code = "circuit_breaker_open"
    entry = {
        "step_index": step_index,
        "action": action,
        "status": status,
        "mode": result_mode,
        "simulated": adapter_simulated,
        "executed": adapter_executed,
        "started_at": _iso(now),
        "completed_at": _iso(now),
        "message": message,
        "output": {
            "simulated": adapter_simulated,
            "executed": adapter_executed,
            "adapter_mode": result_mode,
            "resolved_params": params,
            "adapter_result": adapter_result,
            "circuit_breaker": circuit_snapshot,
        },
        "error": None
        if status == "success"
        else {
            "code": err_code,
            "message": adapter_result.get("message") or message,
        },
    }
    if isinstance(step.get("label"), str) and step.get("label"):
        entry["label"] = step["label"]

    if status == "success" and action == "block_ip":
        tracking = _record_playbook_block_tracking(
            conn, step=step, step_index=step_index, execution=execution, params=params
        )
        if tracking is not None:
            entry["output"]["blocklist_tracking"] = tracking
            # Ineligible/private documentation IPs keep adapter success; tracking is skipped.
            if tracking.get("success") is False and tracking.get("error_code") not in {
                "invalid_indicator",
                "protected_target",
                "protected_target_config_invalid",
                "validation_no_target",
            }:
                entry["status"] = "failed"
                entry["error"] = {
                    "code": tracking.get("error_code") or "blocklist_tracking_failed",
                    "message": tracking.get("message") or "Blocklist tracking failed",
                }
                entry["message"] = tracking.get("message") or entry["message"]

    return entry


def _record_playbook_block_tracking(
    conn,
    *,
    step: dict[str, Any],
    step_index: int,
    execution: dict[str, Any],
    params: dict[str, Any],
) -> dict[str, Any] | None:
    source_ip = params.get("source_ip")
    if not source_ip:
        return {
            "success": False,
            "skipped": True,
            "error_code": "validation_no_target",
            "message": "No source_ip for blocklist tracking",
        }
    try:
        from core.db import validate_blocked_ip

        validate_blocked_ip(str(source_ip))
    except ValueError as error:
        return {
            "success": False,
            "skipped": True,
            "error_code": "invalid_indicator",
            "message": str(error),
        }
    result = execute_response_command(
        conn,
        ResponseCommandRequest(
            action="block_ip",
            indicator_value=str(source_ip),
            alert_id=execution.get("alert_id"),
            incident_id=execution.get("incident_id"),
            reason=params.get("reason") or "Playbook block_ip tracking",
            origin_surface=ORIGIN_PLAYBOOK,
            playbook_execution_id=execution.get("id"),
            playbook_step_index=step_index,
            idempotency_key=f"playbook-block-{execution.get('id')}-{step_index}",
            safe_metadata={"playbook_id": execution.get("playbook_id")},
        ),
    )
    return {
        "success": result.success,
        "message": result.message,
        "error_code": result.error_code,
        "registry_record_id": result.registry_record_id,
        "blocked_ip_id": result.blocked_ip_id,
        "idempotent": result.idempotent,
        "enforcement": result.enforcement,
    }


def _failure_entry(
    step_index,
    action,
    message: str,
    code: str,
    now: datetime,
    output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "step_index": step_index,
        "action": action,
        "status": "failed",
        "mode": "simulation",
        "started_at": _iso(now),
        "completed_at": _iso(now),
        "message": message,
        "output": output or {
            "simulated": True,
            "executed": False,
        },
        "error": {
            "code": code,
            "message": message,
        },
    }


def _approval_requested_entry(
    *,
    step_index: int,
    approval_request: dict[str, Any],
    step: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    return {
        "step_index": step_index,
        "action": "require_approval",
        "status": "awaiting_approval",
        "event": "approval_requested",
        "mode": "simulation",
        "simulated": True,
        "executed": False,
        "started_at": _iso(now),
        "completed_at": None,
        "approval_request_id": approval_request["id"],
        "approval_status": approval_request["status"],
        "risk_level": approval_request["risk_level"],
        "message": step.get("reason") or "Approval requested before continuing simulated playbook.",
        "output": {
            "simulated": True,
            "executed": False,
            "approval_gate": True,
        },
        "error": None,
    }


def _approval_decision_entry(
    *,
    step_index: int,
    approval_request: dict[str, Any],
    status: str,
    event: str,
    message: str,
    now: datetime,
) -> dict[str, Any]:
    return {
        "step_index": step_index,
        "action": "require_approval",
        "status": status,
        "event": event,
        "mode": "simulation",
        "simulated": True,
        "executed": False,
        "started_at": _iso(now),
        "completed_at": _iso(now),
        "approval_request_id": approval_request["id"],
        "approval_status": approval_request["status"],
        "risk_level": approval_request["risk_level"],
        "message": message,
        "output": {
            "simulated": True,
            "executed": False,
            "approval_gate": True,
        },
        "error": None,
    }


def _execute_branch_step(
    conn,
    step: dict[str, Any],
    step_index: int,
    steps: list[dict[str, Any]],
    steps_log: list[dict[str, Any]],
    execution: dict[str, Any],
    now: datetime,
) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    condition = step.get("condition")
    if not isinstance(condition, dict):
        return (
            _failure_entry(
                step_index=step_index,
                action="branch",
                message="Branch step condition must be an object.",
                code="invalid_branch",
                now=now,
            ),
            [],
            step_index + 1,
        )

    try:
        result = evaluate_branch_condition(
            conn,
            condition,
            execution=execution,
            steps_log=steps_log,
        )
    except PlaybookBranchConditionError as error:
        return (
            _failure_entry(
                step_index=step_index,
                action="branch",
                message=error.message,
                code=error.code,
                now=now,
            ),
            [],
            step_index + 1,
        )

    goto_label: str | None
    if result:
        goto_label = step.get("goto_true")
        if not isinstance(goto_label, str) or not goto_label:
            return (
                _failure_entry(
                    step_index=step_index,
                    action="branch",
                    message="Branch step goto_true is missing.",
                    code="branch_target_not_found",
                    now=now,
                ),
                [],
                step_index + 1,
            )
        goto_step_index = resolve_label_target_index(
            steps,
            goto_label,
            branch_index=step_index,
        )
    else:
        if "goto_false" in step:
            goto_false = step.get("goto_false")
            if not isinstance(goto_false, str) or not goto_false:
                return (
                    _failure_entry(
                        step_index=step_index,
                        action="branch",
                        message="Branch step goto_false is invalid.",
                        code="branch_target_not_found",
                        now=now,
                    ),
                    [],
                    step_index + 1,
                )
            goto_label = goto_false
            goto_step_index = resolve_label_target_index(
                steps,
                goto_label,
                branch_index=step_index,
            )
        else:
            goto_label = None
            goto_step_index = step_index + 1

    if goto_step_index is None:
        return (
            _failure_entry(
                step_index=step_index,
                action="branch",
                message="Branch target label could not be resolved.",
                code="branch_target_not_found",
                now=now,
            ),
            [],
            step_index + 1,
        )

    skip_entries = _skipped_branch_step_entries(
        steps,
        start_index=step_index + 1,
        end_index=goto_step_index,
        now=now,
    )
    entry = {
        "step_index": step_index,
        "action": "branch",
        "label": step.get("label"),
        "status": "success",
        "event": "branch_evaluated",
        "condition": condition,
        "result": result,
        "goto_label": goto_label,
        "goto_step_index": goto_step_index,
        "mode": "simulation",
        "simulated": True,
        "executed": False,
        "started_at": _iso(now),
        "completed_at": _iso(now),
        "message": "Branch condition evaluated.",
        "output": {
            "simulated": True,
            "executed": False,
            "condition": condition,
            "result": result,
            "goto_label": goto_label,
            "goto_step_index": goto_step_index,
        },
        "error": None,
    }
    return entry, skip_entries, goto_step_index


def _execute_trigger_playbook_step(
    conn,
    step: dict[str, Any],
    step_index: int,
    execution: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    params = step.get("params")
    if not isinstance(params, dict):
        return _failure_entry(
            step_index=step_index,
            action="trigger_playbook",
            message="trigger_playbook requires params object.",
            code="invalid_trigger_playbook_params",
            now=now,
        )

    target_playbook_id = params.get("playbook_id")
    if not isinstance(target_playbook_id, str) or not target_playbook_id.strip():
        return _failure_entry(
            step_index=step_index,
            action="trigger_playbook",
            message="trigger_playbook requires params.playbook_id.",
            code="invalid_trigger_playbook_target",
            now=now,
        )
    target_playbook_id = target_playbook_id.strip()

    target_definition = playbook_store.get_playbook_definition(conn, target_playbook_id)
    if target_definition is None:
        return _failure_entry(
            step_index=step_index,
            action="trigger_playbook",
            message=f"Target playbook {target_playbook_id!r} was not found.",
            code="trigger_playbook_not_found",
            now=now,
        )
    if target_definition.get("enabled") is not True:
        return _failure_entry(
            step_index=step_index,
            action="trigger_playbook",
            message=f"Target playbook {target_playbook_id!r} is disabled.",
            code="trigger_playbook_disabled",
            now=now,
        )

    parent_depth = int(execution.get("chain_depth") or 0)
    if parent_depth >= MAX_CHAIN_DEPTH:
        return _failure_entry(
            step_index=step_index,
            action="trigger_playbook",
            message="Maximum playbook chain depth exceeded.",
            code="chain_depth_exceeded",
            now=now,
        )

    if _target_in_execution_ancestry(conn, execution, target_playbook_id):
        return _failure_entry(
            step_index=step_index,
            action="trigger_playbook",
            message="Playbook chain cycle detected.",
            code="chain_cycle_detected",
            now=now,
        )

    alert_id = execution.get("alert_id")
    if alert_id is None:
        return _failure_entry(
            step_index=step_index,
            action="trigger_playbook",
            message="trigger_playbook requires an alert_id on the parent execution.",
            code="trigger_playbook_alert_context_missing",
            now=now,
        )

    child_depth = parent_depth + 1
    child_execution_id = playbook_store.create_pending_playbook_execution_once(
        conn,
        target_playbook_id,
        int(alert_id),
        incident_id=execution.get("incident_id"),
        parent_execution_id=execution["id"],
        chain_depth=child_depth,
    )
    duplicate = child_execution_id is None
    child_row: dict[str, Any] | None = None
    if duplicate:
        child_row = playbook_store.get_active_playbook_execution_for_pair(
            conn,
            target_playbook_id,
            int(alert_id),
        )
        child_execution_id = child_row["id"] if child_row else None
    else:
        create_and_link_playbook_execution_decision(
            conn,
            int(child_execution_id),
            playbook_id=target_playbook_id,
            alert_id=int(alert_id),
            incident_id=execution.get("incident_id"),
            parent_soar_correlation_id=execution.get("soar_correlation_id"),
            initial_event_type="chained",
            initial_idempotency_key=f"playbook-chained-{child_execution_id}",
            initial_event_metadata={
                "triggered_by_execution_id": execution["id"],
                "triggered_by_step_index": step_index,
                "parent_playbook_id": execution.get("playbook_id"),
                "chain_depth": child_depth,
            },
        )

    message = (
        f"Triggered playbook {target_playbook_id}."
        if not duplicate
        else f"Target playbook {target_playbook_id} already has an active execution for this alert."
    )
    return {
        "step_index": step_index,
        "action": "trigger_playbook",
        "status": "success",
        "event": "playbook_triggered",
        "mode": "simulation",
        "simulated": True,
        "executed": False,
        "started_at": _iso(now),
        "completed_at": _iso(now),
        "message": message,
        "child_execution_id": child_execution_id,
        "child_playbook_id": target_playbook_id,
        "chain_depth": child_depth,
        "output": {
            "simulated": True,
            "executed": False,
            "child_execution_id": child_execution_id,
            "child_playbook_id": target_playbook_id,
            "chain_depth": child_depth,
            "duplicate": duplicate,
        },
        "error": None,
    }


def _execute_enrich_context_step(
    conn,
    step: dict[str, Any],
    step_index: int,
    execution: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    params = step.get("params") or {}
    if not isinstance(params, dict):
        return _failure_entry(
            step_index=step_index,
            action="enrich_context",
            message="enrich_context params must be an object.",
            code="invalid_enrich_context_params",
            now=now,
        )

    try:
        context = build_playbook_enrichment_context(
            conn,
            execution,
            limit=params.get("limit"),
        )
    except Exception as error:
        logger.exception(
            "[PLAYBOOK SIMULATION] enrich_context failed execution_id=%s step_index=%s",
            execution.get("id"),
            step_index,
        )
        return _failure_entry(
            step_index=step_index,
            action="enrich_context",
            message=str(error),
            code="enrich_context_failed",
            now=now,
        )

    entry = {
        "step_index": step_index,
        "action": "enrich_context",
        "status": "success",
        "mode": "read_only",
        "started_at": _iso(now),
        "completed_at": _iso(now),
        "message": "Read-only database enrichment completed; no external action was performed.",
        "output": {
            "simulated": False,
            "executed": True,
            "read_only": True,
            "external_side_effect": False,
            "context": context,
        },
        "error": None,
    }
    if isinstance(step.get("label"), str) and step.get("label"):
        entry["label"] = step["label"]
    return entry


def _target_in_execution_ancestry(
    conn,
    execution: dict[str, Any],
    target_playbook_id: str,
) -> bool:
    if target_playbook_id == execution.get("playbook_id"):
        return True
    for ancestor in playbook_store.get_playbook_execution_ancestor_chain(
        conn,
        int(execution["id"]),
        max_hops=MAX_CHAIN_DEPTH,
    ):
        if ancestor.get("playbook_id") == target_playbook_id:
            return True
    return False


def _skipped_branch_step_entries(
    steps: list[dict[str, Any]],
    *,
    start_index: int,
    end_index: int,
    now: datetime,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for index in range(start_index, end_index):
        step = steps[index] if 0 <= index < len(steps) else {}
        action = step.get("action") if isinstance(step, dict) else None
        entries.append(
            {
                "step_index": index,
                "action": action,
                "status": "skipped",
                "event": "skipped_by_branch",
                "skip_reason": "branch_not_taken",
                "mode": "simulation",
                "simulated": True,
                "executed": False,
                "started_at": None,
                "completed_at": _iso(now),
                "message": "Step skipped because branch chose another path.",
                "output": {
                    "simulated": True,
                    "executed": False,
                    "skip_reason": "branch_not_taken",
                },
                "error": None,
            }
        )
    return entries


def _step_already_skipped_in_log(steps_log: list[dict[str, Any]], step_index: int) -> bool:
    return any(
        isinstance(entry, dict)
        and entry.get("step_index") == step_index
        and entry.get("status") == "skipped"
        for entry in steps_log
    )


def _skipped_later_step_entries(
    steps: list[dict[str, Any]],
    *,
    start_index: int,
    reason: str,
    now: datetime,
) -> list[dict[str, Any]]:
    entries = []
    for index, step in enumerate(steps[start_index:], start=start_index):
        action = step.get("action") if isinstance(step, dict) else None
        entries.append(
            {
                "step_index": index,
                "action": action,
                "status": "skipped",
                "event": "skipped_after_approval_gate",
                "mode": "simulation",
                "simulated": True,
                "executed": False,
                "started_at": None,
                "completed_at": _iso(now),
                "message": f"Step skipped because {reason} stopped the simulated playbook.",
                "output": {
                    "simulated": True,
                    "executed": False,
                    "skip_reason": reason,
                },
                "error": None,
            }
        )
    return entries


def _step_already_succeeded_in_log(steps_log: list[dict[str, Any]], step_index: int) -> bool:
    """True when steps_log already records a successful outcome for this step index."""
    return any(
        isinstance(e, dict)
        and e.get("step_index") == step_index
        and e.get("status") == "success"
        for e in steps_log
    )


def _latest_gate_entry(steps_log: list[dict[str, Any]]) -> dict[str, Any] | None:
    for entry in reversed(steps_log):
        if (
            isinstance(entry, dict)
            and entry.get("action") == "require_approval"
            and entry.get("event") == "approval_requested"
            and isinstance(entry.get("step_index"), int)
        ):
            return entry
    return None


def _has_gate_event(
    steps_log: list[dict[str, Any]],
    step_index: int,
    approval_request_id: int,
    event: str,
) -> bool:
    return any(
        isinstance(entry, dict)
        and entry.get("step_index") == step_index
        and entry.get("approval_request_id") == approval_request_id
        and entry.get("event") == event
        for entry in steps_log
    )


def _fail_awaiting_execution(
    conn,
    execution: dict[str, Any],
    steps_log: list[dict[str, Any]],
    step_index: int | None,
    code: str,
    message: str,
    now: datetime,
    prior_status: str = "awaiting_approval",
    *,
    worker_id: str | None = None,
) -> dict[str, Any]:
    steps_log.append(
        _failure_entry(
            step_index=step_index,
            action="require_approval",
            message=message,
            code=code,
            now=now,
        )
    )
    owner = _resolve_worker_id(worker_id or execution.get("lease_owner"))
    _finalize_failed(
        conn,
        execution["id"],
        owner,
        steps_log,
        last_completed_step=execution.get("last_completed_step"),
        now=now,
    )
    return _result(execution, prior_status, "failed", "failed", 0, message)


def _result(
    execution,
    prior_status,
    new_status,
    outcome,
    steps_processed,
    message,
    *,
    reason: str | None = None,
):
    payload = {
        "execution_id": execution["id"],
        "playbook_id": execution["playbook_id"],
        "prior_status": prior_status,
        "new_status": new_status,
        "outcome": outcome,
        "steps_processed": steps_processed,
        "message": message,
    }
    if reason is not None:
        payload["reason"] = reason
    return payload


def _skip_result(
    execution: dict[str, Any],
    prior_status: str,
    reason: str,
    message: str,
    *,
    new_status: str | None = None,
) -> dict[str, Any]:
    return _result(
        execution,
        prior_status,
        new_status or prior_status,
        "skipped",
        0,
        message,
        reason=reason,
    )


def _normalize_limit(limit) -> int:
    try:
        parsed = int(limit)
    except (TypeError, ValueError):
        return 10
    if parsed < 1:
        return 1
    return min(parsed, 50)


def _coerce_now(now) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now


def _coerce_lease_duration(lease_duration_seconds: int | None) -> int:
    if lease_duration_seconds is not None:
        parsed = int(lease_duration_seconds)
        if parsed < 1:
            raise ValueError("lease_duration_seconds must be at least 1")
        return parsed
    raw = os.getenv("SOAR_PLAYBOOK_LEASE_SECONDS", str(DEFAULT_PLAYBOOK_LEASE_SECONDS)).strip()
    try:
        parsed = int(raw)
    except ValueError:
        return DEFAULT_PLAYBOOK_LEASE_SECONDS
    return max(1, parsed)


def _resolve_worker_id(worker_id: str | None) -> str:
    owner = (worker_id or "").strip()
    if owner:
        return owner
    return generate_playbook_worker_id()


def _heartbeat_lease(
    conn,
    execution_id: int,
    worker_id: str,
    now: datetime,
    lease_duration_seconds: int,
) -> bool:
    updated = playbook_store.heartbeat_execution_lease(
        conn,
        execution_id,
        worker_id,
        lease_duration_seconds=lease_duration_seconds,
        now=now,
    )
    return updated is not None


def _finalize_success(
    conn,
    execution_id: int,
    worker_id: str,
    steps_log: list[dict],
    *,
    last_completed_step: int | None,
    now: datetime,
) -> dict[str, Any] | None:
    updated = playbook_store.set_playbook_execution_success(
        conn,
        execution_id,
        steps_log,
        last_completed_step=last_completed_step,
        now=now,
        lease_owner=worker_id,
    )
    if updated is None:
        logger.info(
            "[PLAYBOOK SIMULATION] success finalize skipped execution_id=%s worker_id=%s reason=lease_not_owned",
            execution_id,
            worker_id,
        )
        return None
    _append_playbook_terminal_outcome_event(
        conn,
        updated,
        execution_state="succeeded",
        event_type="succeeded",
        summary="Simulated playbook execution completed successfully.",
    )
    playbook_store.release_execution_lease(conn, execution_id, worker_id)
    return updated


def _finalize_failed(
    conn,
    execution_id: int,
    worker_id: str,
    steps_log: list[dict],
    *,
    last_completed_step: int | None,
    now: datetime,
) -> dict[str, Any] | None:
    updated = playbook_store.set_playbook_execution_failed(
        conn,
        execution_id,
        steps_log,
        last_completed_step=last_completed_step,
        now=now,
        lease_owner=worker_id,
    )
    if updated is None:
        current = playbook_store.get_playbook_execution(conn, execution_id)
        if (
            current is not None
            and current.get("status") == "awaiting_approval"
            and not current.get("lease_owner")
        ):
            updated = playbook_store.set_playbook_execution_failed(
                conn,
                execution_id,
                steps_log,
                last_completed_step=last_completed_step,
                now=now,
            )
        else:
            logger.info(
                "[PLAYBOOK SIMULATION] failure finalize skipped execution_id=%s worker_id=%s reason=lease_not_owned",
                execution_id,
                worker_id,
            )
            return None
    if updated is None:
        logger.info(
            "[PLAYBOOK SIMULATION] failure finalize skipped execution_id=%s worker_id=%s reason=update_race",
            execution_id,
            worker_id,
        )
        return None
    _append_playbook_terminal_outcome_event(
        conn,
        updated,
        execution_state="failed",
        event_type="failed",
        summary="Simulated playbook execution failed.",
    )
    capture_failed_execution_dead_letter(
        conn,
        updated,
        steps_log,
        last_completed_step=last_completed_step,
        now=now,
    )
    playbook_store.release_execution_lease(conn, execution_id, worker_id)
    return updated


def _append_playbook_running_outcome_event(conn, execution: dict[str, Any]):
    return _append_playbook_execution_outcome_event(
        conn,
        execution,
        event_type="running",
        execution_state="running",
        summary=f"Playbook worker claimed playbook execution {execution['id']} for simulation.",
        idempotency_key=f"playbook-running-{execution['id']}",
    )


def _append_playbook_resumed_outcome_event(
    conn,
    execution: dict[str, Any],
    *,
    approval_request: dict[str, Any],
):
    return _append_playbook_execution_outcome_event(
        conn,
        execution,
        event_type="resumed",
        execution_state="running",
        summary="Simulated playbook execution resumed after approval.",
        idempotency_key=f"playbook-resumed-{execution['id']}-{approval_request['id']}",
        playbook_step_index=approval_request.get("playbook_step_index"),
        approval_request_id=approval_request["id"],
        execution_actor="playbook_worker",
        reason_code="approval_required",
        metadata={
            "approval_request_id": approval_request["id"],
            "approval_status": approval_request.get("status"),
        },
    )


def _append_notification_delivery_outcome_event(
    conn,
    execution: dict[str, Any],
    delivery_attempt: dict[str, Any],
):
    execution_id = execution["id"]
    step_index = delivery_attempt.get("playbook_step_index")
    delivery_id = delivery_attempt.get("id")
    mapped = _map_notification_delivery_outcome(delivery_attempt)
    return _append_playbook_execution_outcome_event(
        conn,
        execution,
        event_type="notification_delivery",
        execution_state=mapped["execution_state"],
        summary=mapped["summary"],
        idempotency_key=f"playbook-notification-{execution_id}-{step_index}-{delivery_id}",
        playbook_step_index=step_index,
        notification_delivery_attempt_id=delivery_id,
        execution_actor="adapter",
        reason_code=mapped["reason_code"],
        execution_mode=mapped["execution_mode"],
        simulated=mapped["simulated"],
        external_executed=mapped["external_executed"],
        provider=delivery_attempt.get("provider"),
        adapter_name=delivery_attempt.get("adapter_name"),
        metadata={
            "notification_delivery_attempt_id": delivery_id,
            "delivery_mode": delivery_attempt.get("mode"),
            "delivery_status": delivery_attempt.get("status"),
            "provider": delivery_attempt.get("provider"),
            "adapter_name": delivery_attempt.get("adapter_name"),
            "action": delivery_attempt.get("action"),
            "real_evidence": mapped["real_evidence"],
        },
    )


def _map_notification_delivery_outcome(delivery_attempt: dict[str, Any]) -> dict[str, Any]:
    mode = str(delivery_attempt.get("mode") or "simulation").strip().lower()
    status = str(delivery_attempt.get("status") or "failed").strip().lower()
    provider = delivery_attempt.get("provider") or "notification provider"
    metadata = delivery_attempt.get("metadata") or {}
    has_real_evidence = _notification_delivery_has_real_evidence(delivery_attempt)

    if status == "blocked":
        return {
            "execution_mode": "real" if mode == "real" else "simulation",
            "execution_state": "blocked",
            "external_executed": False,
            "simulated": mode != "real",
            "reason_code": "policy_blocked",
            "real_evidence": False,
            "summary": f"Notification delivery to {provider} was blocked; no real execution was confirmed.",
        }

    if status in {"failed", "timeout"}:
        reason = "adapter_unavailable" if status == "timeout" else "provider_error"
        return {
            "execution_mode": "real" if mode == "real" else "simulation",
            "execution_state": "failed",
            "external_executed": False,
            "simulated": mode != "real",
            "reason_code": reason,
            "real_evidence": False,
            "summary": f"Notification delivery to {provider} {status}; no real execution was confirmed.",
        }

    if mode == "real" and status == "success" and has_real_evidence:
        return {
            "execution_mode": "real",
            "execution_state": "succeeded",
            "external_executed": True,
            "simulated": False,
            "reason_code": None,
            "real_evidence": True,
            "summary": f"Notification delivery to {provider} succeeded with explicit real execution evidence.",
        }

    if mode == "real" and status == "success":
        return {
            "execution_mode": "simulation",
            "execution_state": "succeeded",
            "external_executed": False,
            "simulated": True,
            "reason_code": "simulation_mode",
            "real_evidence": False,
            "summary": (
                f"Notification delivery to {provider} reported success without complete "
                "real execution evidence; recorded as simulated."
            ),
        }

    return {
        "execution_mode": "simulation",
        "execution_state": "succeeded" if status == "success" else "failed",
        "external_executed": False,
        "simulated": True,
        "reason_code": "simulation_mode",
        "real_evidence": False,
        "summary": f"Simulated notification delivery to {provider} {status}.",
    }


def _notification_delivery_has_real_evidence(delivery_attempt: dict[str, Any]) -> bool:
    metadata = delivery_attempt.get("metadata") or {}
    if delivery_attempt.get("mode") != "real" or delivery_attempt.get("status") != "success":
        return False
    if metadata.get("executed") is not True:
        return False
    if metadata.get("simulated") is not False:
        return False
    adapter_mode = str(metadata.get("adapter_mode") or "").strip().lower()
    if adapter_mode == "real":
        return True
    return any(
        metadata.get(key) is True
        for key in (
            "provider_success",
            "provider_success_evidence",
            "provider_delivery_confirmed",
            "delivery_confirmed",
        )
    )


def _append_non_adapter_playbook_step_outcome_event(
    conn,
    execution: dict[str, Any],
    entry: dict[str, Any],
):
    action = entry.get("action")
    step_index = entry.get("step_index")
    if action == "require_approval" or action in ADAPTER_ACTIONS:
        return None
    if not isinstance(step_index, int):
        return None

    status = entry.get("status")
    if status == "success":
        execution_state = "succeeded"
        event_type = "step_succeeded"
        reason_code = "simulation_mode"
    elif status == "failed":
        execution_state = "failed"
        event_type = "step_failed"
        reason_code = _canonical_playbook_reason_code(entry)
    else:
        return None

    return _append_playbook_execution_outcome_event(
        conn,
        execution,
        event_type=event_type,
        execution_state=execution_state,
        summary=entry.get("message") or f"Simulated playbook step {step_index} {status}.",
        idempotency_key=f"playbook-step-{execution['id']}-{step_index}-{execution_state}",
        playbook_step_index=step_index,
        reason_code=reason_code,
        metadata={
            "step_index": step_index,
            "action": action,
            "step_status": status,
        },
    )


def _append_playbook_awaiting_approval_outcome_event(
    conn,
    execution: dict[str, Any],
    *,
    approval_request: dict[str, Any],
    step_index: int,
    summary: str,
):
    return _append_playbook_execution_outcome_event(
        conn,
        execution,
        event_type="awaiting_approval",
        execution_state="awaiting_approval",
        summary=summary,
        idempotency_key=(
            f"playbook-awaiting-approval-{execution['id']}-{step_index}-"
            f"{approval_request['id']}"
        ),
        playbook_step_index=step_index,
        approval_request_id=approval_request["id"],
        execution_actor="playbook_worker",
        reason_code="approval_required",
        simulated=False,
        metadata={
            "step_index": step_index,
            "action": "require_approval",
            "approval_request_id": approval_request["id"],
            "approval_status": approval_request["status"],
        },
    )


def _append_playbook_approval_decision_outcome_event(
    conn,
    execution: dict[str, Any],
    *,
    approval_request: dict[str, Any],
    event_type: str,
    execution_state: str,
    summary: str,
):
    step_index = approval_request.get("playbook_step_index")
    approval_request_id = approval_request["id"]
    metadata = {
        "approval_request_id": approval_request_id,
        "approval_status": approval_request.get("status"),
        "playbook_step_index": step_index,
    }
    approval_event_id = _latest_approval_request_event_id(
        conn,
        approval_request_id,
        approval_request.get("status"),
    )
    if approval_event_id is not None:
        metadata["approval_request_event_id"] = approval_event_id

    return _append_playbook_execution_outcome_event(
        conn,
        execution,
        event_type=event_type,
        execution_state=execution_state,
        summary=summary,
        idempotency_key=f"playbook-{event_type}-{execution['id']}-{approval_request_id}",
        playbook_step_index=step_index,
        approval_request_id=approval_request_id,
        execution_actor="approval_service",
        reason_code=(
            "approval_denied"
            if approval_request.get("status") in {"denied", "expired"}
            else "approval_required"
        ),
        simulated=False,
        metadata=metadata,
    )


def _append_playbook_terminal_outcome_event(
    conn,
    execution: dict[str, Any],
    *,
    execution_state: str,
    event_type: str,
    summary: str,
):
    return _append_playbook_execution_outcome_event(
        conn,
        execution,
        event_type=event_type,
        execution_state=execution_state,
        summary=summary,
        idempotency_key=(
            f"playbook-{_playbook_terminal_idempotency_label(event_type)}-{execution['id']}"
        ),
    )


def _append_playbook_execution_outcome_event(
    conn,
    execution: dict[str, Any],
    *,
    event_type: str,
    execution_state: str,
    summary: str,
    idempotency_key: str,
    playbook_step_index: int | None = None,
    approval_request_id: int | None = None,
    notification_delivery_attempt_id: int | None = None,
    execution_actor: str = "playbook_worker",
    reason_code: str = "simulation_mode",
    execution_mode: str = "simulation",
    simulated: bool = True,
    external_executed: bool = False,
    provider: str | None = None,
    adapter_name: str | None = None,
    metadata: dict[str, Any] | None = None,
):
    decision_id = execution.get("decision_id")
    soar_correlation_id = execution.get("soar_correlation_id")
    if decision_id is None or not soar_correlation_id:
        return None

    execution_id = execution["id"]
    return _with_canonical_playbook_outcome_savepoint(
        conn,
        execution_id,
        event_type,
        lambda: append_outcome_event(
            conn,
            decision_id=decision_id,
            soar_correlation_id=soar_correlation_id,
            event_type=event_type,
            execution_mode=execution_mode,
            execution_state=execution_state,
            simulated=simulated,
            external_executed=external_executed,
            tracking_recorded=False,
            execution_actor=execution_actor,
            reason_code=reason_code,
            outcome_summary=summary,
            alert_id=execution.get("alert_id"),
            incident_id=execution.get("incident_id"),
            source_ip=_resolve_playbook_alert_source_ip(conn, execution.get("alert_id")),
            playbook_execution_id=execution_id,
            playbook_step_index=playbook_step_index,
            approval_request_id=approval_request_id,
            notification_delivery_attempt_id=notification_delivery_attempt_id,
            provider=provider,
            adapter_name=adapter_name,
            idempotency_key=idempotency_key,
            metadata={
                "playbook_execution_id": execution_id,
                "playbook_id": execution.get("playbook_id"),
                "status": execution.get("status"),
                **(metadata or {}),
            },
        ),
    )


def try_append_playbook_lifecycle_outcome_event(
    conn,
    execution: dict[str, Any],
    *,
    event_type: str,
    execution_state: str,
    summary: str,
    idempotency_key: str,
    execution_actor: str = "system",
    reason_code: str = "simulation_mode",
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Public safe wrapper: append a lifecycle outcome event (abandoned, permanently_failed,
    retried, etc.) to a playbook execution.

    No-ops silently when the execution has no decision_id. Never raises.
    """
    _append_playbook_execution_outcome_event(
        conn,
        execution,
        event_type=event_type,
        execution_state=execution_state,
        summary=summary,
        idempotency_key=idempotency_key,
        execution_actor=execution_actor,
        reason_code=reason_code,
        execution_mode="simulation",
        simulated=True,
        external_executed=False,
        metadata=metadata,
    )


def _playbook_terminal_idempotency_label(event_type: str) -> str:
    if event_type == "succeeded":
        return "success"
    return event_type


def _resolve_playbook_alert_source_ip(conn, alert_id: int | None) -> str | None:
    if alert_id is None:
        return None
    with conn.cursor() as cur:
        cur.execute("SELECT host(source_ip) FROM alerts WHERE id = %s", (alert_id,))
        row = cur.fetchone()
    return row[0] if row and row[0] else None


def _latest_approval_request_event_id(
    conn,
    approval_request_id: int,
    approval_status: str | None,
) -> int | None:
    if not approval_status:
        return None
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM approval_request_events
            WHERE approval_request_id = %s
              AND event_type = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (approval_request_id, approval_status),
        )
        row = cur.fetchone()
    return int(row[0]) if row else None


def _canonical_playbook_reason_code(entry: dict[str, Any]) -> str:
    error = entry.get("error") if isinstance(entry.get("error"), dict) else {}
    code = error.get("code")
    if code == "unsupported_action":
        return "unsupported_action"
    if code in {"invalid_step", "missing_action"}:
        return "policy_blocked"
    return "provider_error"


def _with_canonical_playbook_outcome_savepoint(conn, execution_id, event_type, writer):
    savepoint_name = "canonical_playbook_outcome"
    savepoint_created = False
    try:
        with conn.cursor() as cur:
            cur.execute(f"SAVEPOINT {savepoint_name}")
            savepoint_created = True
        event = writer()
        with conn.cursor() as cur:
            cur.execute(f"RELEASE SAVEPOINT {savepoint_name}")
        return event
    except Exception:
        if savepoint_created:
            try:
                with conn.cursor() as cur:
                    cur.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
                    cur.execute(f"RELEASE SAVEPOINT {savepoint_name}")
            except Exception:
                logger.exception(
                    "Failed to rollback canonical %s outcome savepoint for playbook_execution_id=%s",
                    event_type,
                    execution_id,
                )
        logger.exception(
            "Failed to append canonical %s outcome for playbook_execution_id=%s",
            event_type,
            execution_id,
        )
        return None


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def capture_failed_execution_dead_letter(
    conn,
    execution: dict[str, Any],
    steps_log: list[dict],
    *,
    last_completed_step: int | None,
    now: datetime,
) -> None:
    entry = _latest_failed_step_entry(steps_log)
    if entry is None:
        return

    try:
        error = entry.get("error") if isinstance(entry.get("error"), dict) else {}
        message = (
            error.get("message")
            or entry.get("message")
            or execution.get("failure_reason")
            or "Playbook execution failed."
        )
        output = entry.get("output") if isinstance(entry.get("output"), dict) else {}
        failure_class = _dead_letter_failure_class(entry)
        dead_letter_store.create_dead_letter(
            conn,
            source_type="playbook_execution",
            source_id=execution["id"],
            execution_id=execution["id"],
            incident_id=execution.get("incident_id"),
            alert_id=execution.get("alert_id"),
            playbook_id=execution.get("playbook_id"),
            step_index=entry.get("step_index") if isinstance(entry.get("step_index"), int) else None,
            action_name=entry.get("action") if isinstance(entry.get("action"), str) else None,
            failure_class=failure_class,
            error_message=str(message),
            payload_json={
                "source": "playbook_step_executor",
                "execution_status": execution.get("status"),
                "failure_reason": execution.get("failure_reason"),
                "last_completed_step": last_completed_step,
                "step": {
                    "step_index": entry.get("step_index"),
                    "action": entry.get("action"),
                    "status": entry.get("status"),
                    "message": entry.get("message"),
                    "error": error,
                    "output": output,
                },
            },
            retryable=dead_letter_store.classify_dead_letter_retryable(
                failure_class,
                source_type="playbook_execution",
                status="open",
            ),
            first_failed_at=now,
            last_failed_at=now,
        )
    except Exception:
        logger.warning(
            "[PLAYBOOK SIMULATION] dead letter capture failed safely execution_id=%s",
            execution.get("id"),
            exc_info=True,
        )


def _latest_failed_step_entry(steps_log: list[dict]) -> dict[str, Any] | None:
    for entry in reversed(steps_log):
        if isinstance(entry, dict) and entry.get("status") == "failed":
            return entry
    return None


def _dead_letter_failure_class(entry: dict[str, Any]) -> str:
    output = entry.get("output") if isinstance(entry.get("output"), dict) else {}
    adapter_result = output.get("adapter_result") if isinstance(output.get("adapter_result"), dict) else {}
    metadata = adapter_result.get("metadata") if isinstance(adapter_result.get("metadata"), dict) else {}
    failure_class = metadata.get("failure_classification")
    if isinstance(failure_class, str) and failure_class.strip():
        return failure_class.strip()[:64]

    error = entry.get("error") if isinstance(entry.get("error"), dict) else {}
    code = error.get("code")
    if isinstance(code, str) and code.strip():
        return code.strip()[:64]
    return "unknown"
