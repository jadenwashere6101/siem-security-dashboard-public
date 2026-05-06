VALID_LOG_STATUSES = {"executed", "skipped", "failed"}


def log_response_action(conn, row, log_status, details):
    """Write one terminal SOAR worker outcome to response_actions_log.

    The caller owns the transaction boundary. A stale recovered action can be
    executed again and therefore can legitimately produce another audit row.
    """
    if log_status not in VALID_LOG_STATUSES:
        raise ValueError(f"Invalid response action log status: {log_status}")

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO response_actions_log
                (alert_id, source_ip, action, status, details)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                row.get("alert_id"),
                row.get("source_ip"),
                row.get("action"),
                log_status,
                details,
            ),
        )
