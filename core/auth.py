from functools import wraps
from flask import current_app, jsonify, request
from flask_login import UserMixin, current_user
from core.audit_helpers import log_audit_event
from core.db import get_db_connection


def get_user_by_username(username):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT username, password_hash, role, is_active
            FROM users
            WHERE username = %s
            """,
            (username,),
        )
        row = cur.fetchone()

        if not row:
            return None

        return {
            "username": row[0],
            "password_hash": row[1],
            "role": row[2],
            "is_active": row[3],
        }
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


class User(UserMixin):
    def __init__(self, user_id, role="admin"):
        self.id = user_id
        self.role = role


def load_user(user_id):
    if user_id == "admin":
        return User(user_id, role="super_admin")

    db_user = get_user_by_username(user_id)
    if db_user and db_user["is_active"]:
        return User(db_user["username"], role=db_user["role"])

    return None


def deny_rbac_access(reason, message, target_alert_id=None):
    current_app.logger.warning(
        "RBAC deny username=%s role=%s method=%s path=%s remote_addr=%s",
        getattr(current_user, "id", None),
        getattr(current_user, "role", None),
        request.method,
        request.path,
        request.remote_addr,
    )
    log_audit_event(
        "rbac_deny",
        actor_username=getattr(current_user, "id", None),
        actor_role=getattr(current_user, "role", None),
        target_alert_id=target_alert_id,
        http_method=request.method,
        request_path=request.path,
        source_ip=request.remote_addr,
        details={"reason": reason},
    )
    return jsonify({
        "error": "forbidden",
        "message": message
    }), 403


def admin_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if getattr(current_user, "role", None) not in {"admin", "super_admin"}:
            return deny_rbac_access(
                "admin_required",
                "Admin role required",
                target_alert_id=kwargs.get("alert_id"),
            )

        return view_func(*args, **kwargs)

    return wrapped_view


def super_admin_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if getattr(current_user, "role", None) != "super_admin":
            return deny_rbac_access(
                "admin_required",
                "Super admin role required",
                target_alert_id=kwargs.get("alert_id"),
            )

        return view_func(*args, **kwargs)

    return wrapped_view


def analyst_or_super_admin_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if getattr(current_user, "role", None) not in {"super_admin", "analyst"}:
            return deny_rbac_access(
                "analyst_required",
                "Analyst or super admin role required",
                target_alert_id=kwargs.get("alert_id"),
            )

        return view_func(*args, **kwargs)

    return wrapped_view
