import logging
import re

from core.approval_store import (
    create_approval_request,
    expire_pending_requests,
    get_latest_approval_for_queue_action,
)
from core.response_command_contracts import ORIGIN_RESPONSE_QUEUE, ResponseCommandRequest
from core.response_command_service import execute_response_command
from core.soar_protected_targets import (
    ProtectedTargetConfigError,
    require_unprotected_target,
)
from core.response_action_queue_store import (
    claim_next_approved_awaiting_action,
    claim_next_pending_action,
    mark_action_awaiting_approval,
    mark_action_skipped,
    mark_action_success,
    record_action_failure,
    skip_next_terminal_approval_action,
)
from core.soar_response_outcomes import append_outcome_event
from engines.soar_errors import RetryableActionError, SkippedAction
from engines.soar_executor import SimulationExecutor
from engines.soar_log_writer import log_response_action


logger = logging.getLogger(__name__)

# Frozen path notice:
# The response-action queue worker remains for existing queued work and audit
# compatibility. `soar-automation-path-consolidation-decision` designates the
# playbook engine as authoritative for new SOAR automation; queue retirement or
# removal is a separately approved future stage, not part of ongoing worker changes.
# Phase 1 routes block_ip/monitor/flag_high_priority through the shared response
# command service for durable tracking while preserving approval gates.

APPROVAL_REQUIRED_ACTIONS = frozenset({"block_ip"})
CANONICAL_QUEUE_ACTIONS = frozenset({"block_ip", "monitor", "flag_high_priority"})


def process_next_action(conn, now=None, executor=None):
    executor = executor or SimulationExecutor()
    row = claim_next_pending_action(conn, now=now)
    if row is None:
        expire_pending_requests(conn, now=now)
        row = claim_next_approved_awaiting_action(conn, now=now)
        if row is None:
            skipped = skip_next_terminal_approval_action(conn, now=now)
            if skipped is None:
                conn.commit()
                return None
            approval = get_latest_approval_for_queue_action(
                conn,
                queue_id=skipped["id"],
                action=skipped["action"],
            )
            response_action_log_id = log_response_action(
                conn,
                {**skipped, "status": "awaiting_approval"},
                log_status="skipped",
                details=skipped["last_error"],
                decision_id=skipped.get("decision_id"),
                soar_correlation_id=skipped.get("soar_correlation_id"),
            )
            _append_worker_outcome_event(
                conn,
                skipped,
                execution_state="blocked",
                reason_code="approval_denied",
                summary=skipped["last_error"],
                event_type="blocked",
                response_action_log_id=response_action_log_id,
                approval_request_id=approval["id"] if approval else None,
            )
            conn.commit()
            return _worker_result(
                {**skipped, "status": "awaiting_approval"},
                skipped,
                outcome="skipped",
                retryable=False,
                code="approval_denied"
                if skipped.get("approval_status") == "denied"
                else "approval_expired",
                reason=skipped["last_error"],
                message=skipped["last_error"],
            )

    _append_running_outcome_event(conn, row)
    conn.commit()
    approval_result = _handle_approval_gate(conn, row, now=now)
    if approval_result is not None:
        return approval_result

    try:
        if row.get("action") in CANONICAL_QUEUE_ACTIONS:
            command_result = execute_response_command(
                conn,
                ResponseCommandRequest(
                    action=row["action"],
                    indicator_value=str(row["source_ip"]) if row.get("source_ip") else None,
                    alert_id=row.get("alert_id"),
                    reason=f"Queue worker {row['action']}",
                    origin_surface=ORIGIN_RESPONSE_QUEUE,
                    queue_id=row.get("id"),
                    approval_request_id=row.get("approval_request_id"),
                    idempotency_key=f"queue-{row['id']}-{row['action']}",
                ),
            )
            if not command_result.success:
                raise SkippedAction(
                    command_result.error or command_result.message,
                    code=command_result.error_code or "response_command_failed",
                )
            execution_result = {
                "code": command_result.outcome_label,
                "message": command_result.message,
            }
            updated = mark_action_success(conn, row["id"], now=now)
            response_action_log_id = command_result.response_action_log_id
            reason_code = (
                "tracking_only"
                if row.get("action") == "block_ip"
                else None
            )
            _append_worker_outcome_event(
                conn,
                updated,
                execution_state="succeeded",
                reason_code=reason_code or "simulation_mode",
                summary=execution_result["message"],
                event_type="succeeded",
                response_action_log_id=response_action_log_id,
            )
            conn.commit()
            return _worker_result(
                row,
                updated,
                outcome="success",
                retryable=False,
                code=execution_result["code"],
                message=execution_result["message"],
            )

        execution_result = executor(row)
        _validate_executor_result(execution_result)
        updated = mark_action_success(conn, row["id"], now=now)
        response_action_log_id = log_response_action(
            conn,
            row,
            log_status="executed",
            details=execution_result["message"],
            decision_id=row.get("decision_id"),
            soar_correlation_id=row.get("soar_correlation_id"),
        )
        _append_worker_outcome_event(
            conn,
            updated,
            execution_state="succeeded",
            reason_code="simulation_mode",
            summary=execution_result["message"],
            event_type="succeeded",
            response_action_log_id=response_action_log_id,
        )
        conn.commit()
        return _worker_result(
            row,
            updated,
            outcome="success",
            retryable=False,
            code=execution_result["code"],
            message=execution_result["message"],
        )
    except SkippedAction as error:
        updated = mark_action_skipped(conn, row["id"], str(error), now=now)
        response_action_log_id = log_response_action(
            conn,
            row,
            log_status="skipped",
            details=str(error),
            decision_id=row.get("decision_id"),
            soar_correlation_id=row.get("soar_correlation_id"),
        )
        _append_worker_outcome_event(
            conn,
            updated,
            execution_state="skipped",
            reason_code=_canonical_worker_reason_code(error.code),
            summary=str(error),
            event_type="skipped",
            response_action_log_id=response_action_log_id,
            error_code=error.code,
        )
        conn.commit()
        return _worker_result(
            row,
            updated,
            outcome="skipped",
            retryable=False,
            code=error.code,
            reason=str(error),
            message=str(error),
        )
    except RetryableActionError as error:
        updated = record_action_failure(
            conn,
            row["id"],
            str(error),
            retryable=True,
            now=now,
        )
        if updated["status"] == "failed":
            response_action_log_id = log_response_action(
                conn,
                row,
                log_status="failed",
                details=str(error),
                decision_id=row.get("decision_id"),
                soar_correlation_id=row.get("soar_correlation_id"),
            )
        else:
            response_action_log_id = None
        _append_retry_outcome_events(
            conn,
            updated,
            error_code=error.code,
            error_message=str(error),
            response_action_log_id=response_action_log_id,
        )
        conn.commit()
        outcome = "requeued" if updated["status"] == "pending" else "failed"
        return _worker_result(
            row,
            updated,
            outcome=outcome,
            retryable=updated["status"] == "pending",
            code=error.code,
            reason=str(error),
            message=str(error),
        )
    except Exception as error:
        updated = record_action_failure(
            conn,
            row["id"],
            str(error),
            retryable=False,
            now=now,
        )
        response_action_log_id = log_response_action(
            conn,
            row,
            log_status="failed",
            details=str(error),
            decision_id=row.get("decision_id"),
            soar_correlation_id=row.get("soar_correlation_id"),
        )
        _append_worker_outcome_event(
            conn,
            updated,
            execution_state="failed",
            reason_code="provider_error",
            summary=str(error),
            event_type="failed",
            response_action_log_id=response_action_log_id,
            error_code="unexpected_error",
        )
        conn.commit()
        return _worker_result(
            row,
            updated,
            outcome="failed",
            retryable=False,
            code="unexpected_error",
            reason=str(error),
            message=str(error),
        )


def process_batch(conn, limit=10, now=None, executor=None):
    results = []
    for _ in range(limit):
        result = process_next_action(conn, now=now, executor=executor)
        if result is None:
            break
        results.append(result)
    return results


def action_requires_approval(action):
    return action in APPROVAL_REQUIRED_ACTIONS


def _append_running_outcome_event(conn, row):
    decision_id = row.get("decision_id")
    soar_correlation_id = row.get("soar_correlation_id")
    if decision_id is None or not soar_correlation_id:
        return None

    queue_id = row["id"]
    retry_count = row.get("retry_count") or 0
    return _with_canonical_outcome_savepoint(
        conn,
        queue_id,
        "running",
        lambda: append_outcome_event(
            conn,
            decision_id=decision_id,
            soar_correlation_id=soar_correlation_id,
            event_type="running",
            execution_mode="simulation",
            execution_state="running",
            simulated=True,
            external_executed=False,
            tracking_recorded=False,
            execution_actor="queue_worker",
            reason_code="simulation_mode",
            outcome_summary=f"Queue worker claimed response action {row['action']} for simulation.",
            queue_id=queue_id,
            idempotency_key=f"queue-running-{queue_id}-{retry_count}",
            metadata={
                "queue_id": queue_id,
                "retry_count": retry_count,
                "action": row.get("action"),
            },
        ),
    )


def _append_worker_outcome_event(
    conn,
    row,
    *,
    execution_state,
    reason_code,
    summary,
    event_type=None,
    response_action_log_id=None,
    approval_request_id=None,
    error_code=None,
):
    decision_id = row.get("decision_id")
    soar_correlation_id = row.get("soar_correlation_id")
    if decision_id is None or not soar_correlation_id:
        return None

    queue_id = row["id"]
    retry_count = row.get("retry_count") or 0
    event_type_value = event_type or execution_state
    idempotency_key = f"queue-{event_type_value}-{queue_id}-{retry_count}"
    return _with_canonical_outcome_savepoint(
        conn,
        queue_id,
        event_type_value,
        lambda: append_outcome_event(
            conn,
            decision_id=decision_id,
            soar_correlation_id=soar_correlation_id,
            event_type=event_type_value,
            execution_mode="simulation",
            execution_state=execution_state,
            simulated=execution_state == "succeeded",
            external_executed=False,
            tracking_recorded=False,
            execution_actor="queue_worker",
            reason_code=reason_code,
            outcome_summary=_safe_outcome_summary(summary),
            queue_id=queue_id,
            approval_request_id=approval_request_id,
            response_action_log_id=response_action_log_id,
            idempotency_key=idempotency_key,
            metadata={
                "queue_id": queue_id,
                "retry_count": retry_count,
                "action": row.get("action"),
                "error_code": error_code,
            },
        ),
    )


def _append_retry_outcome_events(
    conn,
    row,
    *,
    error_code,
    error_message,
    response_action_log_id=None,
):
    failed_event_type = (
        "failed_attempt" if row["status"] == "pending" else "failed"
    )
    failed_event = _append_worker_outcome_event(
        conn,
        row,
        execution_state="failed",
        reason_code=_canonical_worker_reason_code(error_code),
        summary=error_message,
        event_type=failed_event_type,
        response_action_log_id=response_action_log_id,
        error_code=error_code,
    )
    if row["status"] != "pending":
        return failed_event

    return _append_worker_outcome_event(
        conn,
        row,
        execution_state="queued",
        reason_code=_canonical_worker_reason_code(error_code),
        summary="Retryable response action failure requeued for another attempt.",
        event_type="requeued",
        error_code=error_code,
    )


def _with_canonical_outcome_savepoint(conn, queue_id, event_type, writer):
    savepoint_name = "canonical_worker_outcome"
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
                    "Failed to rollback canonical %s outcome savepoint for queue_id=%s",
                    event_type,
                    queue_id,
                )
        logger.exception(
            "Failed to append canonical %s outcome for queue_id=%s",
            event_type,
            queue_id,
        )
        return None


def _canonical_worker_reason_code(code):
    if code in {"approval_required", "approval_pending"}:
        return "approval_required"
    if code in {"approval_denied", "approval_expired"}:
        return "approval_denied"
    if code == "unsupported_action":
        return "unsupported_action"
    if code in {
        "adapter_unavailable",
        "adapter_timeout",
        "timeout",
        "retryable_error",
    }:
        return "adapter_unavailable"
    if code in {
        "protected_target",
        "protected_target_config_invalid",
        "policy_disabled",
        "validation_missing_alert_id",
        "validation_no_target",
        "validation_null_source_ip",
        "validation_invalid_ip_format",
        "validation_private_ip",
    }:
        return "policy_blocked"
    if code in {
        "simulated_block_ip",
        "simulated_flag_high_priority",
        "simulated_monitor",
    }:
        return "simulation_mode"
    return "provider_error"


def _safe_outcome_summary(summary):
    text = str(summary or "").replace("\n", " ").replace("\r", " ").strip()
    text = re.sub(r"https?://\S+", "[redacted-url]", text, flags=re.IGNORECASE)
    text = re.sub(
        r"(?i)(token|secret|password|api[_-]?key)=\S+",
        r"\1=[redacted]",
        text,
    )
    return text[:500] or "SOAR queue worker outcome recorded."


def _handle_approval_gate(conn, row, now=None):
    if not action_requires_approval(row["action"]):
        return None

    if row["action"] == "block_ip":
        try:
            require_unprotected_target(row.get("source_ip"))
        except SkippedAction as error:
            updated = mark_action_skipped(conn, row["id"], str(error), now=now)
            response_action_log_id = log_response_action(
                conn,
                row,
                log_status="skipped",
                details=str(error),
                decision_id=row.get("decision_id"),
                soar_correlation_id=row.get("soar_correlation_id"),
            )
            _append_worker_outcome_event(
                conn,
                updated,
                execution_state="skipped",
                reason_code=_canonical_worker_reason_code(error.code),
                summary=str(error),
                event_type="skipped",
                response_action_log_id=response_action_log_id,
                error_code=error.code,
            )
            conn.commit()
            return _worker_result(
                row,
                updated,
                outcome="skipped",
                retryable=False,
                code=error.code,
                reason=str(error),
                message=str(error),
            )
        except ProtectedTargetConfigError as error:
            message = (
                "Protected target config invalid; refusing block_ip execution"
            )
            detailed_message = f"{message}: {error}"
            updated = mark_action_skipped(conn, row["id"], detailed_message, now=now)
            response_action_log_id = log_response_action(
                conn,
                row,
                log_status="skipped",
                details=detailed_message,
                decision_id=row.get("decision_id"),
                soar_correlation_id=row.get("soar_correlation_id"),
            )
            _append_worker_outcome_event(
                conn,
                updated,
                execution_state="skipped",
                reason_code="policy_blocked",
                summary=detailed_message,
                event_type="skipped",
                response_action_log_id=response_action_log_id,
                error_code="protected_target_config_invalid",
            )
            conn.commit()
            return _worker_result(
                row,
                updated,
                outcome="skipped",
                retryable=False,
                code="protected_target_config_invalid",
                reason=detailed_message,
                message=detailed_message,
            )

    expire_pending_requests(conn, now=now)
    approval = get_latest_approval_for_queue_action(
        conn,
        queue_id=row["id"],
        action=row["action"],
    )

    if approval is None:
        approval = create_approval_request(
            conn,
            queue_id=row["id"],
            action=row["action"],
            request_reason="approval required for high-risk SOAR action",
            risk_level="high",
        )
        updated = mark_action_awaiting_approval(
            conn,
            row["id"],
            "approval required",
            now=now,
        )
        _append_worker_outcome_event(
            conn,
            updated,
            execution_state="awaiting_approval",
            reason_code="approval_required",
            summary="approval required",
            event_type="awaiting_approval",
            approval_request_id=approval["id"],
            error_code="approval_required",
        )
        conn.commit()
        return _worker_result(
            row,
            updated,
            outcome="awaiting_approval",
            retryable=False,
            code="approval_required",
            reason="approval required",
            message="approval required",
        )

    if approval["status"] == "approved":
        return None

    if approval["status"] == "pending":
        if row["status"] == "running":
            updated = mark_action_awaiting_approval(
                conn,
                row["id"],
                "approval pending",
                now=now,
            )
        else:
            updated = row
        _append_worker_outcome_event(
            conn,
            updated,
            execution_state="awaiting_approval",
            reason_code="approval_required",
            summary="approval pending",
            event_type="awaiting_approval",
            approval_request_id=approval["id"],
            error_code="approval_pending",
        )
        conn.commit()
        return _worker_result(
            row,
            updated,
            outcome="awaiting_approval",
            retryable=False,
            code="approval_pending",
            reason="approval pending",
            message="approval pending",
        )

    reason = "approval denied" if approval["status"] == "denied" else "approval expired"
    updated = mark_action_skipped(conn, row["id"], reason, now=now)
    response_action_log_id = log_response_action(
        conn,
        row,
        log_status="skipped",
        details=reason,
        decision_id=row.get("decision_id"),
        soar_correlation_id=row.get("soar_correlation_id"),
    )
    _append_worker_outcome_event(
        conn,
        updated,
        execution_state="blocked",
        reason_code="approval_denied",
        summary=reason,
        event_type="blocked",
        response_action_log_id=response_action_log_id,
        approval_request_id=approval["id"],
        error_code="approval_denied"
        if approval["status"] == "denied"
        else "approval_expired",
    )
    conn.commit()
    return _worker_result(
        row,
        updated,
        outcome="skipped",
        retryable=False,
        code="approval_denied" if approval["status"] == "denied" else "approval_expired",
        reason=reason,
        message=reason,
    )


def _worker_result(
    original,
    updated,
    *,
    outcome,
    retryable,
    code,
    message,
    reason=None,
):
    return {
        "queue_id": original["id"],
        "prior_status": original["status"],
        "new_status": updated["status"],
        "outcome": outcome,
        "retryable": retryable,
        "retry_count": updated["retry_count"],
        "max_retries": updated["max_retries"],
        "error_code": code if outcome != "success" else None,
        "reason": reason,
        "message": message,
    }


def _validate_executor_result(execution_result):
    if not isinstance(execution_result, dict):
        raise Exception("Executor result must be a dict")

    if not execution_result.get("code"):
        raise Exception("Executor result missing required code")

    if not execution_result.get("message"):
        raise Exception("Executor result missing required message")
