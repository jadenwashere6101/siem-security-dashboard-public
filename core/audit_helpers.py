from flask import current_app
from psycopg2.extras import Json
from core.db import get_db_connection


# spec: SPEC-AUTH-001
def log_audit_event(
    event_type,
    actor_username=None,
    actor_role=None,
    target_username=None,
    target_alert_id=None,
    http_method=None,
    request_path=None,
    source_ip=None,
    details=None
):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO audit_log (
                event_type,
                actor_username,
                actor_role,
                target_username,
                target_alert_id,
                http_method,
                request_path,
                source_ip,
                details
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                event_type,
                actor_username,
                actor_role,
                target_username,
                target_alert_id,
                http_method,
                request_path,
                source_ip,
                Json(details) if details is not None else None,
            ),
        )
        conn.commit()
    except Exception as e:
        current_app.logger.error("Failed to write audit log event=%s error=%s", event_type, e)
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
