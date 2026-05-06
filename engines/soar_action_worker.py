from core.response_action_queue_store import (
    claim_next_pending_action,
    mark_action_skipped,
    mark_action_success,
    record_action_failure,
)
from engines.soar_errors import RetryableActionError, SkippedAction
from engines.soar_executor import SimulationExecutor


def process_next_action(conn, now=None, executor=None):
    executor = executor or SimulationExecutor()
    row = claim_next_pending_action(conn, now=now)
    if row is None:
        conn.commit()
        return None

    conn.commit()
    try:
        execution_result = executor(row)
        _validate_executor_result(execution_result)
        updated = mark_action_success(conn, row["id"], now=now)
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
