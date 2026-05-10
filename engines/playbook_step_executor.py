"""
Simulation-only SOAR playbook step executor.

Consumes pending playbook_executions and records simulated step outcomes. It does not
enqueue SOAR actions, create approvals, or mutate firewalls/blocklists.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from core import approval_store
from core import playbook_store
from engines.playbook_registry import SUPPORTED_ACTIONS
from integrations.base_integration import (
    FAILURE_CLASSIFICATION_CIRCUIT_OPEN,
    FAILURE_CLASSIFICATION_CIRCUIT_STATE_INVALID,
    get_simulated_circuit_breaker_dict,
)
from integrations.integration_registry import execute_playbook_simulated_adapter

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = frozenset({"success", "failed", "abandoned"})
ADAPTER_ACTIONS = {
    "notify_slack": ("slack", "send_message"),
    "notify_email": ("email", "send_email"),
    "block_ip": ("firewall", "block_ip"),
    "notify_webhook": ("webhook", "post_event"),
}


def process_next_pending_playbook_execution(conn, now=None) -> dict[str, Any] | None:
    claimed = playbook_store.claim_next_pending_playbook_execution(conn, now=_coerce_now(now))
    if claimed is None:
        return None
    return _process_running_execution(conn, claimed, now=_coerce_now(now))


def process_playbook_execution(conn, execution_id: int, now=None) -> dict[str, Any]:
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
        return _process_awaiting_approval_execution(conn, execution, now=_coerce_now(now))

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

    running = playbook_store.set_playbook_execution_running(
        conn,
        execution_id,
        now=_coerce_now(now),
    )
    if running is None:
        latest = playbook_store.get_playbook_execution(conn, execution_id) or execution
        return {
            "execution_id": execution_id,
            "playbook_id": execution["playbook_id"],
            "prior_status": prior_status,
            "new_status": latest.get("status"),
            "outcome": "skipped",
            "reason": "claim_failed",
            "steps_processed": 0,
            "message": "Playbook execution could not be moved to running.",
        }
    return _process_running_execution(conn, running, now=_coerce_now(now), prior_status=prior_status)


def process_playbook_execution_batch(conn, limit=10, now=None) -> dict[str, Any]:
    batch_limit = _normalize_limit(limit)
    results = []
    for _ in range(batch_limit):
        result = process_next_pending_playbook_execution(conn, now=now)
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
            results.append(process_playbook_execution(conn, row["id"], now=now))

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
) -> dict[str, Any]:
    execution_id = execution["id"]
    playbook_id = execution["playbook_id"]
    prior = prior_status or execution["status"]
    timestamp = _coerce_now(now)

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
        playbook_store.set_playbook_execution_failed(
            conn,
            execution_id,
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
        playbook_store.set_playbook_execution_failed(
            conn,
            execution_id,
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

    return _process_steps(
        conn,
        execution,
        steps,
        timestamp,
        prior,
        start_index=0,
        steps_log=[],
        last_completed_step=None,
    )


def _process_awaiting_approval_execution(conn, execution: dict[str, Any], now=None) -> dict[str, Any]:
    timestamp = _coerce_now(now)
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

        resumed = playbook_store.set_playbook_execution_resumed_running(
            conn,
            execution["id"],
            steps_log,
            last_completed_step=gate_index,
            now=timestamp,
        )
        if resumed is None:
            latest = playbook_store.get_playbook_execution(conn, execution["id"]) or execution
            return {
                "execution_id": execution["id"],
                "playbook_id": execution["playbook_id"],
                "prior_status": "awaiting_approval",
                "new_status": latest.get("status"),
                "outcome": "skipped",
                "reason": "resume_claim_failed",
                "steps_processed": 0,
                "message": "Playbook execution could not be resumed.",
            }

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

        playbook_store.set_playbook_execution_failed(
            conn,
            execution["id"],
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
) -> dict[str, Any]:
    execution_id = execution["id"]
    playbook_id = execution["playbook_id"]
    failed = False
    failure_message = None

    for index, step in enumerate(steps[start_index:], start=start_index):
        if isinstance(step, dict) and step.get("action") == "require_approval":
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
            playbook_store.set_playbook_execution_awaiting_approval(
                conn,
                execution_id,
                steps_log,
                last_completed_step=last_completed_step,
            )
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
        if entry["status"] == "success":
            last_completed_step = index
            playbook_store.update_playbook_execution_step_log(
                conn,
                execution_id,
                steps_log,
                last_completed_step=last_completed_step,
            )
            continue

        failed = True
        failure_message = entry["message"]
        on_failure = step.get("on_failure", "abort") if isinstance(step, dict) else "abort"
        if on_failure != "continue":
            break

    if failed:
        playbook_store.set_playbook_execution_failed(
            conn,
            execution_id,
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

    playbook_store.set_playbook_execution_success(
        conn,
        execution_id,
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
    playbook_store.set_playbook_execution_failed(
        conn,
        execution["id"],
        steps_log,
        last_completed_step=execution.get("last_completed_step"),
        now=now,
    )
    return _result(execution, prior_status, "failed", "failed", 0, message)


def _result(execution, prior_status, new_status, outcome, steps_processed, message):
    return {
        "execution_id": execution["id"],
        "playbook_id": execution["playbook_id"],
        "prior_status": prior_status,
        "new_status": new_status,
        "outcome": outcome,
        "steps_processed": steps_processed,
        "message": message,
    }


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


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")
