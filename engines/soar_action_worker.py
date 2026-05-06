from core.response_action_queue_store import (
    claim_next_pending_action,
    mark_action_skipped,
    mark_action_success,
    record_action_failure,
)


class RetryableActionError(Exception):
    def __init__(self, message, code="retryable_error"):
        super().__init__(message)
        self.code = code


class SkippedAction(Exception):
    def __init__(self, message, code="skipped"):
        super().__init__(message)
        self.code = code


SUPPORTED_PLACEHOLDER_ACTIONS = {"block_ip", "flag_high_priority", "monitor"}


def placeholder_execute_action(row):
    if row["action"] not in SUPPORTED_PLACEHOLDER_ACTIONS:
        raise SkippedAction(
            f"Unsupported response action: {row['action']}",
            code="unsupported_action",
        )

    return {
        "code": "placeholder_success",
        "message": f"Placeholder worker accepted {row['action']}",
    }


def process_next_action(conn, now=None, executor=None):
    executor = executor or placeholder_execute_action
    row = claim_next_pending_action(conn, now=now)
    if row is None:
        conn.commit()
        return None

    conn.commit()
    try:
        execution_result = executor(row)
        updated = mark_action_success(conn, row["id"], now=now)
        conn.commit()
        return _worker_result(
            row,
            updated,
            outcome="success",
            retryable=False,
            code=_result_code(execution_result, "success"),
            message=_result_message(execution_result, "Response action completed"),
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


def _result_code(execution_result, default):
    if isinstance(execution_result, dict):
        return execution_result.get("code") or default
    return default


def _result_message(execution_result, default):
    if isinstance(execution_result, dict):
        return execution_result.get("message") or default
    return default
