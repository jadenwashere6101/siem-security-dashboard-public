import psycopg2
from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required
from psycopg2.extras import Json
from werkzeug.security import generate_password_hash

from core.audit_helpers import log_audit_event
from backend_auth import super_admin_required
from core.db import get_db_connection
from backend_detection_config import (
    get_all_effective_detection_rules,
    get_detection_rule_defaults,
    get_effective_detection_rule,
    validate_detection_rule_config,
)
from core.extensions import limiter


admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin/users", methods=["POST"])
@limiter.limit("30 per minute")
@login_required
@super_admin_required
def create_user():
    data = request.get_json() or {}

    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    role = (data.get("role") or "viewer").strip().lower()

    if not username or not password.strip():
        return jsonify({"error": "Username and password are required"}), 400

    if role not in {"viewer", "analyst"}:
        return jsonify({"error": "Invalid role"}), 400

    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users (username, password_hash, role, is_active)
            VALUES (%s, %s, %s, %s)
            """,
            (username, generate_password_hash(password), role, True),
        )
        conn.commit()
        log_audit_event(
            "user_create",
            actor_username=current_user.id,
            actor_role=current_user.role,
            target_username=username,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
        )

        current_app.logger.info("Admin created user username=%s role=%s", username, role)
        return jsonify({"message": "User created successfully"}), 201
    except psycopg2.IntegrityError:
        if conn:
            conn.rollback()
        return jsonify({"error": "Unable to create user"}), 409
    except Exception:
        if conn:
            conn.rollback()
        return jsonify({"error": "Unable to create user"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@admin_bp.route("/admin/users", methods=["GET"])
@limiter.limit("30 per minute")
@login_required
@super_admin_required
def list_users():
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT username, role, is_active, created_at
            FROM users
            ORDER BY created_at ASC
            """
        )

        rows = cur.fetchall()
        users = [
            {
                "username": row[0],
                "role": row[1],
                "is_active": row[2],
                "created_at": str(row[3]),
            }
            for row in rows
        ]

        log_audit_event(
            "VIEW_ADMIN_USERS",
            actor_username=current_user.id,
            actor_role=current_user.role,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
        )
        return jsonify(users), 200
    except Exception:
        return jsonify({"error": "Unable to list users"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@admin_bp.route("/admin/users/<username>/status", methods=["PATCH"])
@limiter.limit("30 per minute")
@login_required
@super_admin_required
def update_user_status(username):
    if username == current_user.id:
        return jsonify({"error": "Cannot modify your own account"}), 400

    data = request.get_json() or {}
    is_active = data.get("is_active")

    if not isinstance(is_active, bool):
        return jsonify({"error": "is_active must be a boolean"}), 400

    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE users
            SET is_active = %s
            WHERE username = %s
            """,
            (is_active, username),
        )

        if cur.rowcount == 0:
            conn.rollback()
            return jsonify({"error": "User not found"}), 404

        conn.commit()
        log_audit_event(
            "user_activate" if is_active else "user_deactivate",
            actor_username=current_user.id,
            actor_role=current_user.role,
            target_username=username,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
        )
        log_audit_event(
            "USER_STATUS_CHANGE",
            actor_username=current_user.id,
            actor_role=current_user.role,
            target_username=username,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={"is_active": is_active},
        )
        return jsonify({"message": "User status updated successfully"}), 200
    except Exception:
        if conn:
            conn.rollback()
        return jsonify({"error": "Unable to update user status"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@admin_bp.route("/admin/users/<username>/password", methods=["PATCH"])
@limiter.limit("30 per minute")
@login_required
@super_admin_required
def update_user_password(username):
    if username == current_user.id:
        return jsonify({"error": "Cannot modify your own account"}), 400

    data = request.get_json() or {}
    password = data.get("password") or ""

    if not password.strip():
        return jsonify({"error": "Password is required"}), 400

    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE users
            SET password_hash = %s
            WHERE username = %s
            """,
            (generate_password_hash(password), username),
        )

        if cur.rowcount == 0:
            conn.rollback()
            return jsonify({"error": "User not found"}), 404

        conn.commit()
        log_audit_event(
            "user_password_reset",
            actor_username=current_user.id,
            actor_role=current_user.role,
            target_username=username,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
        )
        log_audit_event(
            "PASSWORD_RESET",
            actor_username=current_user.id,
            actor_role=current_user.role,
            target_username=username,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
        )
        return jsonify({"message": "Password updated successfully"}), 200
    except Exception:
        if conn:
            conn.rollback()
        return jsonify({"error": "Unable to update password"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@admin_bp.route("/admin/users/<username>/role", methods=["PATCH"])
@limiter.limit("30 per minute")
@login_required
@super_admin_required
def update_user_role(username):
    data = request.get_json() or {}
    role = (data.get("role") or "").strip().lower()

    if role not in {"viewer", "analyst"}:
        return jsonify({"error": "Invalid role"}), 400

    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE users
            SET role = %s
            WHERE username = %s
            """,
            (role, username),
        )

        if cur.rowcount == 0:
            conn.rollback()
            return jsonify({"error": "User not found"}), 404

        conn.commit()
        log_audit_event(
            "user_role_update",
            actor_username=current_user.id,
            actor_role=current_user.role,
            target_username=username,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={"new_role": role},
        )
        log_audit_event(
            "USER_ROLE_CHANGE",
            actor_username=current_user.id,
            actor_role=current_user.role,
            target_username=username,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={"new_role": role},
        )
        return jsonify({"message": "User role updated successfully"}), 200
    except Exception:
        if conn:
            conn.rollback()
        return jsonify({"error": "Unable to update user role"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@admin_bp.route("/admin/audit-log", methods=["GET"])
@limiter.limit("30 per minute")
@login_required
@super_admin_required
def list_audit_log():
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                event_type,
                actor_username,
                actor_role,
                target_username,
                target_alert_id,
                request_path,
                source_ip,
                created_at
            FROM audit_log
            ORDER BY created_at DESC
            LIMIT 50
            """
        )

        rows = cur.fetchall()
        events = [
            {
                "event_type": row[0],
                "actor_username": row[1],
                "actor_role": row[2],
                "target_username": row[3],
                "target_alert_id": row[4],
                "request_path": row[5],
                "source_ip": str(row[6]) if row[6] is not None else None,
                "created_at": str(row[7]),
            }
            for row in rows
        ]

        return jsonify(events), 200
    except Exception:
        return jsonify({"error": "Unable to list audit log"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@admin_bp.route("/admin/detection-rules", methods=["GET"])
@login_required
@super_admin_required
def list_detection_rules():
    return jsonify(get_all_effective_detection_rules()), 200


@admin_bp.route("/admin/detection-rules/<rule_id>", methods=["PATCH"])
@login_required
@super_admin_required
def update_detection_rule(rule_id):
    defaults = get_detection_rule_defaults()
    if rule_id not in defaults:
        return jsonify({"error": "Detection rule not found"}), 404

    payload = request.get_json()
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid JSON"}), 400

    if "active" in payload:
        return jsonify({"error": "Active status cannot be updated in this phase"}), 400

    if "parameters" not in payload:
        return jsonify({"error": "Missing required field: parameters"}), 400

    conn = None
    cur = None

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        old_effective_rule = get_effective_detection_rule(rule_id, cur=cur)
        current_active = old_effective_rule["active"]

        try:
            validated = validate_detection_rule_config(
                rule_id,
                payload.get("parameters"),
                current_active,
            )
        except ValueError as error:
            conn.rollback()
            return jsonify({"error": str(error)}), 400

        normalized_parameters = validated["parameters"]
        changes = []
        all_parameter_keys = set(old_effective_rule["parameters"].keys()) | set(normalized_parameters.keys())

        for key in sorted(all_parameter_keys):
            old_value = old_effective_rule["parameters"].get(key)
            new_value = normalized_parameters.get(key, old_value)
            if old_value != new_value:
                changes.append({
                    "field": key,
                    "old": old_value,
                    "new": new_value,
                })

        cur.execute(
            """
            INSERT INTO detection_config (rule_id, parameters, updated_by, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (rule_id) DO UPDATE
            SET
                parameters = EXCLUDED.parameters,
                updated_by = EXCLUDED.updated_by,
                updated_at = NOW()
            """,
            (
                rule_id,
                Json(normalized_parameters),
                current_user.id,
            ),
        )

        updated_effective_rule = get_effective_detection_rule(rule_id, cur=cur)
        conn.commit()

        log_audit_event(
            "detection_rule_updated",
            actor_username=current_user.id,
            actor_role=current_user.role,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={
                "rule_id": rule_id,
                "old_parameters": old_effective_rule["parameters"],
                "new_parameters": updated_effective_rule["parameters"],
                "changes": changes,
                "actor": current_user.id,
            },
        )

        return jsonify(updated_effective_rule), 200
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("Unable to update detection rule rule_id=%s: %s", rule_id, error)
        return jsonify({"error": "Unable to update detection rule"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
