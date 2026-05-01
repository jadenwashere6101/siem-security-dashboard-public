def fetch_alert_rows(cur, filters=None):
    filters = filters or {}
    clauses = []
    params = []

    severity = (filters.get("severity") or "").strip().lower()
    if severity and severity != "all":
        clauses.append("severity = %s")
        params.append(severity)

    status = (filters.get("status") or "").strip().lower()
    if status and status != "all":
        clauses.append("status = %s")
        params.append(status)

    search = (filters.get("search") or "").strip()
    if search:
        clauses.append("(source_ip::text ILIKE %s OR message ILIKE %s OR alert_type ILIKE %s)")
        like_value = f"%{search}%"
        params.extend([like_value, like_value, like_value])

    query = """
        SELECT
            id,
            alert_type,
            severity,
            source_ip,
            created_at,
            message,
            status,
            country,
            city,
            reputation_label,
            reputation_summary,
            response_action,
            response_status
        FROM alerts
    """

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += " ORDER BY created_at DESC"
    cur.execute(query, tuple(params))
    return cur.fetchall()


def fetch_response_logs_by_alert_id(cur, alert_ids):
    if not alert_ids:
        return {}

    cur.execute(
        """
        SELECT alert_id, action, status, details, executed_at
        FROM response_actions_log
        WHERE alert_id = ANY(%s)
        ORDER BY executed_at DESC
        """,
        (alert_ids,)
    )

    log_map = {alert_id: [] for alert_id in alert_ids}
    for row in cur.fetchall():
        log_map.setdefault(row[0], []).append(row[1:])
    return log_map


def fetch_alert_csv_rows(cur, filters=None):
    filters = filters or {}
    clauses = []
    params = []

    severity = (filters.get("severity") or "").strip().lower()
    if severity and severity != "all":
        clauses.append("a.severity = %s")
        params.append(severity)

    status = (filters.get("status") or "").strip().lower()
    if status and status != "all":
        clauses.append("a.status = %s")
        params.append(status)

    search = (filters.get("search") or "").strip()
    if search:
        clauses.append("(a.source_ip::text ILIKE %s OR a.message ILIKE %s OR a.alert_type ILIKE %s)")
        like_value = f"%{search}%"
        params.extend([like_value, like_value, like_value])

    query = """
        SELECT
            a.id,
            a.alert_type,
            a.severity,
            a.source_ip,
            a.status,
            a.created_at,
            a.message,
            latest_event.environment
        FROM alerts a
        LEFT JOIN LATERAL (
            SELECT e.environment
            FROM events e
            WHERE e.source_ip = a.source_ip
            ORDER BY e.created_at DESC
            LIMIT 1
        ) AS latest_event ON TRUE
    """

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += " ORDER BY a.created_at DESC"
    cur.execute(query, tuple(params))
    return cur.fetchall()
