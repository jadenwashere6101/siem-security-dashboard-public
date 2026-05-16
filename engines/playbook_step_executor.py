"""
Simulation-only SOAR playbook step executor.

Consumes pending playbook_executions and records simulated step outcomes. It does not
enqueue SOAR actions, create approvals, or mutate firewalls/blocklists.
"""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from core import approval_store
from core import notification_delivery_store
from core import playbook_store
from core.playbook_worker_identity import generate_playbook_worker_id
from engines.playbook_registry import SUPPORTED_ACTIONS
from integrations.base_integration import (
    FAILURE_CLASSIFICATION_CIRCUIT_OPEN,
    FAILURE_CLASSIFICATION_CIRCUIT_STATE_INVALID,
    FAILURE_CLASSIFICATION_TIMEOUT,
    get_simulated_circuit_breaker_dict,
)
from integrations.integration_registry import execute_playbook_simulated_adapter

logger = logging.getLogger(__name__)

DEFAULT_PLAYBOOK_LEASE_SECONDS = 60

# spec: SPEC-PLAYBOOK-003
TERMINAL_STATUSES = frozenset({"success", "failed", "abandoned", "permanently_failed"})
# spec: SPEC-PLAYBOOK-001
# spec: SPEC-INTEG-002
ADAPTER_ACTIONS = {
    "notify_slack": ("slack", "send_message"),
    "notify_teams": ("teams", "send_message"),
    "notify_email": ("email", "send_email"),
    "block_ip": ("firewall", "block_ip"),
    "notify_webhook": ("webhook", "post_event"),
}

_NOTIFICATION_ACTIONS = frozenset({"notify_slack", "notify_teams"})
_PROVIDER_FOR_ACTION: dict[str, str] = {"notify_slack": "slack", "notify_teams": "teams"}


# spec: SPEC-NOTIFY-001
def _delivery_status_from_adapter_result(adapter_result: dict[str, Any]) -> str:
    """Map adapter result to a delivery store status value."""
    if adapter_result.get("success") is True:
        return "success"
    meta = adapter_result.get("metadata") or {}
    fc = str(meta.get("failure_classification") or "").strip().lower()
    if fc == FAILURE_CLASSIFICATION_TIMEOUT:
        return "timeout"
    if fc in (FAILURE_CLASSIFICATION_CIRCUIT_OPEN, FAILURE_CLASSIFICATION_CIRCUIT_STATE_INVALID):
        return "blocked"
    return "failed"


def _make_delivery_correlation_id(provider: str, execution_id: int, step_index: int) -> str:
    return f"ntfy-{provider[:8]}-{execution_id}-{step_index}-{uuid.uuid4().hex[:12]}"


def _make_delivery_idempotency_key(
    provider: str, action: str, execution_id: int, step_index: int
) -> str:
    raw = f"{provider}:{action}:{execution_id}:{step_index}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


def _record_notification_delivery_attempt(
    conn,
    execution: dict[str, Any],
    step: dict[str, Any],
    step_index: int,
    entry: dict[str, Any],
    now: datetime,
) -> None:
    """
    Append an immutable delivery record for a Slack/Teams notification step.
    Failures here are logged but never propagate to the step outcome.
    """
    try:
        action = step.get("action")
        provider = _PROVIDER_FOR_ACTION.get(action)
        if provider is None:
            return

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
        notification_delivery_store.create_notification_delivery_attempt(
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
    except Exception:
        logger.warning(
            "[PLAYBOOK SIMULATION] delivery tracking failed safely "
            "execution_id=%s step_index=%s",
            execution.get("id"),
            step_index,
            exc_info=True,
        )


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
        return _skip_result(
            execution,
            prior_status,
            reason,
            "Playbook execution could not be leased for processing.",
            new_status=latest.get("status"),
        )
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

        definition = playbook_store.get_playbook_definition(conn, execution["playbook_id"])
        steps = definition.get("steps") if definition else []
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

    for index, step in enumerate(steps[start_index:], start=start_index):
        # spec: SPEC-PLAYBOOK-003
        # Defensive guard: if steps_log already has a success entry for this index (e.g.
        # last_completed_step and steps_log diverged after a crash + recovery), skip the
        # step entirely so notification/remediation side effects are never duplicated.
        if _step_already_succeeded_in_log(steps_log, index):
            last_completed_step = index
            continue

        if not _heartbeat_lease(
            conn,
            execution_id,
            worker_id,
            timestamp,
            lease_duration_seconds,
        ):
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
                return _result(
                    execution,
                    prior,
                    execution.get("status") or "running",
                    "skipped",
                    len(steps_log),
                    "Playbook execution lease was lost while pausing for approval.",
                    reason="lease_lost",
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

        try:
            entry = _simulate_step(step, index, timestamp, execution)
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

        if isinstance(step, dict) and step.get("action") in _NOTIFICATION_ACTIONS:
            _record_notification_delivery_attempt(conn, execution, step, index, entry, timestamp)

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
                return _result(
                    execution,
                    prior,
                    execution.get("status") or "running",
                    "skipped",
                    len(steps_log),
                    "Playbook execution lease was lost while saving step progress.",
                    reason="lease_lost",
                )
            continue

        failed = True
        failure_message = entry["message"]
        on_failure = step.get("on_failure", "abort") if isinstance(step, dict) else "abort"
        if on_failure != "continue":
            break

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
        return _simulate_adapter_step(step, step_index, now, execution)

    if action not in SUPPORTED_ACTIONS:
        return _failure_entry(
            step_index=step_index,
            action=action,
            message="Unsupported playbook step action.",
            code="unsupported_action",
            now=now,
        )

    messages = {
        "monitor": "[SIMULATED PLAYBOOK STEP] monitor",
        "flag_high_priority": "[SIMULATED PLAYBOOK STEP] flag_high_priority",
        "block_ip": "[SIMULATED PLAYBOOK STEP] block_ip",
    }
    return {
        "step_index": step_index,
        "action": action,
        "status": "success",
        "mode": "simulation",
        "started_at": _iso(now),
        "completed_at": _iso(now),
        "message": messages[action],
        "output": {
            "simulated": True,
            "executed": False,
        },
        "error": None,
    }


def _simulate_adapter_step(
    step: dict[str, Any],
    step_index: int,
    now: datetime,
    execution: dict[str, Any],
) -> dict[str, Any]:
    action = step["action"]
    adapter_name, adapter_action = ADAPTER_ACTIONS[action]
    params = step.get("params") if isinstance(step.get("params"), dict) else {}
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
    message = (
        "Simulated adapter action completed."
        if status == "success"
        else adapter_result.get("message") or "Simulated adapter action failed."
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
    return {
        "step_index": step_index,
        "action": action,
        "status": status,
        "mode": "simulation",
        "simulated": True,
        "executed": False,
        "started_at": _iso(now),
        "completed_at": _iso(now),
        "message": message,
        "output": {
            "simulated": True,
            "executed": False,
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
) -> None:
    updated = playbook_store.set_playbook_execution_success(
        conn,
        execution_id,
        steps_log,
        last_completed_step=last_completed_step,
        now=now,
        lease_owner=worker_id,
    )
    if updated is None:
        playbook_store.set_playbook_execution_success(
            conn,
            execution_id,
            steps_log,
            last_completed_step=last_completed_step,
            now=now,
        )
    playbook_store.release_execution_lease(conn, execution_id, worker_id)


def _finalize_failed(
    conn,
    execution_id: int,
    worker_id: str,
    steps_log: list[dict],
    *,
    last_completed_step: int | None,
    now: datetime,
) -> None:
    updated = playbook_store.set_playbook_execution_failed(
        conn,
        execution_id,
        steps_log,
        last_completed_step=last_completed_step,
        now=now,
        lease_owner=worker_id,
    )
    if updated is None:
        playbook_store.set_playbook_execution_failed(
            conn,
            execution_id,
            steps_log,
            last_completed_step=last_completed_step,
            now=now,
        )
    playbook_store.release_execution_lease(conn, execution_id, worker_id)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")
