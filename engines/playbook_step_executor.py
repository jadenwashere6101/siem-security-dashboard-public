"""
Simulation-only SOAR playbook step executor.

Consumes pending playbook_executions and records simulated step outcomes. It does not
enqueue SOAR actions, create approvals, mutate firewalls/blocklists, or call adapters.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from core import playbook_store
from engines.playbook_registry import SUPPORTED_ACTIONS

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = frozenset({"success", "failed", "abandoned"})


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

    steps_log: list[dict[str, Any]] = []
    last_completed_step = None
    failed = False
    failure_message = None

    for index, step in enumerate(steps):
        try:
            entry = _simulate_step(step, index, timestamp)
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


def _simulate_step(step: dict[str, Any], step_index: int, now: datetime) -> dict[str, Any]:
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


def _failure_entry(step_index, action, message: str, code: str, now: datetime) -> dict[str, Any]:
    return {
        "step_index": step_index,
        "action": action,
        "status": "failed",
        "mode": "simulation",
        "started_at": _iso(now),
        "completed_at": _iso(now),
        "message": message,
        "output": {
            "simulated": True,
            "executed": False,
        },
        "error": {
            "code": code,
            "message": message,
        },
    }


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
