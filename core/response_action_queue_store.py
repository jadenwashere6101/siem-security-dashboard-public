from datetime import timedelta


STALE_RUNNING_TIMEOUT = timedelta(minutes=15)


class QueueTransitionError(ValueError):
    pass


def _queue_row_from_record(record):
    if record is None:
        return None

    (
        row_id,
        alert_id,
        source_ip,
        action,
        status,
        retry_count,
        max_retries,
        last_error,
        idempotency_key,
        created_at,
        updated_at,
    ) = record
    return {
        "id": row_id,
        "alert_id": alert_id,
        "source_ip": source_ip,
        "action": action,
        "status": status,
        "retry_count": retry_count,
        "max_retries": max_retries,
        "last_error": last_error,
        "idempotency_key": idempotency_key,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _returning_queue_row_sql():
    return """
        RETURNING id, alert_id, host(source_ip), action, status,
                  retry_count, max_retries, last_error,
                  idempotency_key, created_at, updated_at
    """


def get_queue_action(conn, queue_id):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, alert_id, host(source_ip), action, status,
                   retry_count, max_retries, last_error,
                   idempotency_key, created_at, updated_at
            FROM response_actions_queue
            WHERE id = %s
            """,
            (queue_id,),
        )
        return _queue_row_from_record(cur.fetchone())


def get_queue_status_counts(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM response_actions_queue
            GROUP BY status
            """
        )
        return {row[0]: row[1] for row in cur.fetchall()}


def list_recent_queue_actions(conn, limit=50, status=None):
    """
    Retrieve recent queue actions in read-only mode.
    
    Args:
        conn: database connection
        limit: maximum number of rows to return (clamped to 100)
        status: optional status filter (pending/running/success/failed/skipped)
    
    Returns:
        list of queue row dicts, newest first
    """
    # Clamp limit to safe max
    limit = min(int(limit) if limit else 50, 100)
    
    with conn.cursor() as cur:
        if status is None:
            cur.execute(
                """
                SELECT id, alert_id, host(source_ip), action, status,
                       retry_count, max_retries, last_error,
                       idempotency_key, created_at, updated_at
                FROM response_actions_queue
                ORDER BY id DESC
                LIMIT %s
                """,
                (limit,),
            )
        else:
            cur.execute(
                """
                SELECT id, alert_id, host(source_ip), action, status,
                       retry_count, max_retries, last_error,
                       idempotency_key, created_at, updated_at
                FROM response_actions_queue
                WHERE status = %s
                ORDER BY id DESC
                LIMIT %s
                """,
                (status, limit),
            )
        return [_queue_row_from_record(row) for row in cur.fetchall()]


def claim_next_pending_action(conn, now=None):
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE response_actions_queue AS queue
            SET status = 'running',
                updated_at = COALESCE(%s::timestamptz, NOW())
            WHERE queue.id = (
                SELECT id
                FROM response_actions_queue
                WHERE status = 'pending'
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            {_returning_queue_row_sql()}
            """,
            (now,),
        )
        return _queue_row_from_record(cur.fetchone())


def mark_action_success(conn, queue_id, now=None):
    return _transition_running_action(conn, queue_id, "success", None, now)


def mark_action_skipped(conn, queue_id, reason, now=None):
    return _transition_running_action(conn, queue_id, "skipped", reason, now)


def mark_action_failed(conn, queue_id, error_message, now=None):
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE response_actions_queue
            SET status = 'failed',
                retry_count = retry_count + 1,
                last_error = %s,
                updated_at = COALESCE(%s::timestamptz, NOW())
            WHERE id = %s
              AND status = 'running'
            {_returning_queue_row_sql()}
            """,
            (error_message, now, queue_id),
        )
        row = _queue_row_from_record(cur.fetchone())

    if row is None:
        raise QueueTransitionError(f"queue action {queue_id} is not running")
    return row


def requeue_failed_action(conn, queue_id, now=None):
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE response_actions_queue
            SET status = 'pending',
                updated_at = COALESCE(%s::timestamptz, NOW())
            WHERE id = %s
              AND status = 'failed'
              AND retry_count < max_retries
            {_returning_queue_row_sql()}
            """,
            (now, queue_id),
        )
        row = _queue_row_from_record(cur.fetchone())

    if row is None:
        raise QueueTransitionError(f"queue action {queue_id} is not retryable")
    return row


def record_action_failure(conn, queue_id, error_message, *, retryable=False, now=None):
    failed_row = mark_action_failed(conn, queue_id, error_message, now=now)
    if retryable and failed_row["retry_count"] < failed_row["max_retries"]:
        return requeue_failed_action(conn, queue_id, now=now)
    return failed_row


def recover_stale_running_actions(conn, now=None, stale_after=STALE_RUNNING_TIMEOUT, limit=None):
    interval_seconds = int(stale_after.total_seconds())
    query_limit = "" if limit is None else "LIMIT %s"
    params = [now, interval_seconds]
    if limit is not None:
        params.append(limit)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            WITH stale AS (
                SELECT id
                FROM response_actions_queue
                WHERE status = 'running'
                  AND updated_at <= COALESCE(%s::timestamptz, NOW()) - (%s * INTERVAL '1 second')
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                {query_limit}
            )
            UPDATE response_actions_queue AS queue
            SET status = CASE
                    WHEN queue.retry_count < queue.max_retries THEN 'pending'
                    ELSE 'failed'
                END,
                last_error = CASE
                    WHEN queue.retry_count < queue.max_retries THEN queue.last_error
                    ELSE COALESCE(queue.last_error, 'stale running action exhausted retries')
                END,
                updated_at = COALESCE(%s::timestamptz, NOW())
            FROM stale
            WHERE queue.id = stale.id
            RETURNING queue.id, queue.alert_id, host(queue.source_ip), queue.action,
                      queue.status, queue.retry_count, queue.max_retries,
                      queue.last_error, queue.idempotency_key,
                      queue.created_at, queue.updated_at
            """,
            [*params, now],
        )
        return [_queue_row_from_record(row) for row in cur.fetchall()]


def _transition_running_action(conn, queue_id, new_status, last_error, now=None):
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE response_actions_queue
            SET status = %s,
                last_error = %s,
                updated_at = COALESCE(%s::timestamptz, NOW())
            WHERE id = %s
              AND status = 'running'
            {_returning_queue_row_sql()}
            """,
            (new_status, last_error, now, queue_id),
        )
        row = _queue_row_from_record(cur.fetchone())

    if row is None:
        raise QueueTransitionError(f"queue action {queue_id} is not running")
    return row
