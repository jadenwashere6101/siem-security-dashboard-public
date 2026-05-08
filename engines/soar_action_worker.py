from core.approval_store import (
    create_approval_request,
    expire_pending_requests,
    get_latest_approval_for_queue_action,
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
from engines.soar_errors import RetryableActionError, SkippedAction
from engines.soar_executor import SimulationExecutor
from engines.soar_log_writer import log_response_action


APPROVAL_REQUIRED_ACTIONS = frozenset({"block_ip"})


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
            log_response_action(
                conn,
                {**skipped, "status": "awaiting_approval"},
                log_status="skipped",
                details=skipped["last_error"],
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

    conn.commit()
    approval_result = _handle_approval_gate(conn, row, now=now)
    if approval_result is not None:
        return approval_result

    try:
        execution_result = executor(row)
        _validate_executor_result(execution_result)
        updated = mark_action_success(conn, row["id"], now=now)
        log_response_action(
            conn,
            row,
            log_status="executed",
            details=execution_result["message"],
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
        log_response_action(
            conn,
            row,
            log_status="skipped",
            details=str(error),
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
            log_response_action(
                conn,
                row,
                log_status="failed",
                details=str(error),
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
        log_response_action(
            conn,
            row,
            log_status="failed",
            details=str(error),
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


def _handle_approval_gate(conn, row, now=None):
    if not action_requires_approval(row["action"]):
        return None

    expire_pending_requests(conn, now=now)
    approval = get_latest_approval_for_queue_action(
        conn,
        queue_id=row["id"],
        action=row["action"],
    )

    if approval is None:
        create_approval_request(
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
    log_response_action(
        conn,
        row,
        log_status="skipped",
        details=reason,
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
