import psycopg2
from datetime import datetime, timezone
from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required
from psycopg2.extras import Json
from werkzeug.security import generate_password_hash

from core.audit_helpers import log_audit_event
from core.approval_store import (
    expire_pending_requests,
    get_latest_approval_for_queue_action,
    list_approval_events,
)
from core.auth import super_admin_required
from core.db import get_db_connection
from core.response_action_queue_store import (
    get_queue_status_counts,
    get_queue_action,
    list_recent_queue_actions,
    sweep_terminal_approval_queue_rows,
)
from core.soar_response_outcomes import get_latest_outcomes_for_queues_bulk
from engines.soar_action_worker import process_batch
from engines.detection_config import (
    get_all_effective_detection_rules,
    get_detection_rule_defaults,
    get_effective_detection_rule,
    validate_detection_rule_config,
)
from engines.pfsense_ingest_filter import (
    DEFAULT_PFSENSE_INGEST_CONFIG,
    get_all_effective_config,
    get_filter_metrics,
    load_effective_policy,
    upsert_config_override,
)
from engines.soar_executor import SimulationExecutor
from core.extensions import limiter


admin_bp = Blueprint("admin", __name__)
DEFAULT_ADMIN_RUN_BATCH_SIZE = 10
MAX_ADMIN_RUN_BATCH_SIZE = 25


@admin_bp.route("/admin/pfsense-ingest-filters", methods=["GET"])
@login_required
@super_admin_required
def list_pfsense_ingest_filters():
    policy = get_all_effective_config()
    return jsonify(policy), 200


@admin_bp.route("/admin/pfsense-ingest-filters/metrics", methods=["GET"])
@login_required
@super_admin_required
def get_pfsense_ingest_filter_metrics():
    return jsonify(get_filter_metrics()), 200


@admin_bp.route("/admin/pfsense-ingest-filters/<category>", methods=["PATCH"])
@login_required
@super_admin_required
def update_pfsense_ingest_filter(category):
    if category not in DEFAULT_PFSENSE_INGEST_CONFIG:
        return jsonify({"error": "pfSense ingest filter category not found"}), 404

    payload = request.get_json()
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid JSON"}), 400
    if set(payload) - {"enabled", "parameters"}:
        return jsonify({"error": "Unknown pfSense ingest filter field"}), 400
    if "enabled" not in payload:
        return jsonify({"error": "Missing required field: enabled"}), 400

    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        old_policy = load_effective_policy(cur)
        old_entry = old_policy["categories"][category]
        parameters = payload.get("parameters", old_entry["parameters"])
        try:
            upsert_config_override(cur, category, payload["enabled"], parameters, current_user.id)
        except ValueError as error:
            conn.rollback()
            return jsonify({"error": str(error)}), 400

        updated_policy = load_effective_policy(cur)
        updated_entry = updated_policy["categories"][category]
        conn.commit()

        log_audit_event(
            "pfsense_ingest_filter_updated",
            actor_username=current_user.id,
            actor_role=current_user.role,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={
                "category": category,
                "old": {"enabled": old_entry["enabled"], "parameters": old_entry["parameters"]},
                "new": {"enabled": updated_entry["enabled"], "parameters": updated_entry["parameters"]},
            },
        )
        return jsonify(updated_entry), 200
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("Unable to update pfSense ingest filter category=%s: %s", category, error)
        return jsonify({"error": "Unable to update pfSense ingest filter"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@admin_bp.route("/admin/users", methods=["POST"])
@limiter.limit("30 per minute")
@login_required
@super_admin_required
def create_user():
    # spec: SPEC-AUTH-001
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


# ============================================================================
# SOAR Queue Visibility Endpoints (read-only)
# ============================================================================


def _serialize_queue_item_for_list(queue_row, response_outcome=None):
    """Serialize queue row for list responses. Excludes idempotency_key."""
    if queue_row is None:
        return None
    
    alert_ref_status = "linked" if queue_row["alert_id"] is not None else "deleted_or_missing"
    alert_ref_label = f"Alert {queue_row['alert_id']}" if queue_row["alert_id"] is not None else "Deleted alert"
    
    return {
        "id": queue_row["id"],
        "alert_id": queue_row["alert_id"],
        "alert_reference": {
            "status": alert_ref_status,
            "label": alert_ref_label,
        },
        "source_ip": queue_row["source_ip"],
        "action": queue_row["action"],
        "status": queue_row["status"],
        "retry_count": queue_row["retry_count"],
        "max_retries": queue_row["max_retries"],
        "last_error": queue_row["last_error"],
        "created_at": str(queue_row["created_at"]),
        "updated_at": str(queue_row["updated_at"]),
        "response_outcome": response_outcome,
    }


def _serialize_queue_item_for_detail(queue_row, response_outcome=None):
    """Serialize queue row for detail responses. Includes idempotency_key."""
    if queue_row is None:
        return None
    
    item = _serialize_queue_item_for_list(
        queue_row,
        response_outcome=response_outcome,
    )
    item["idempotency_key"] = queue_row["idempotency_key"]
    return item


def _serialize_approval_summary(approval):
    if approval is None:
        return None
    return {
        "id": approval["id"],
        "status": approval["status"],
        "risk_level": approval["risk_level"],
        "created_at": approval["created_at"],
        "expires_at": approval["expires_at"],
        "decided_at": approval["decided_at"],
    }


def _parse_soar_run_batch_size(data):
    raw_batch_size = (data or {}).get("batch_size", DEFAULT_ADMIN_RUN_BATCH_SIZE)
    if isinstance(raw_batch_size, bool):
        raise ValueError("batch_size must be an integer")

    try:
        requested_batch_size = int(raw_batch_size)
    except (TypeError, ValueError) as error:
        raise ValueError("batch_size must be an integer") from error

    if requested_batch_size < 1:
        raise ValueError("batch_size must be >= 1")

    return requested_batch_size, min(requested_batch_size, MAX_ADMIN_RUN_BATCH_SIZE)


def _summarize_soar_worker_results(results):
    return {
        "processed": len(results),
        "success": sum(1 for row in results if row.get("outcome") == "success"),
        "failed": sum(1 for row in results if row.get("outcome") == "failed"),
        "skipped": sum(1 for row in results if row.get("outcome") == "skipped"),
        "requeued": sum(1 for row in results if row.get("outcome") == "requeued"),
    }


@admin_bp.route("/admin/soar/queue/status", methods=["GET"])
@limiter.limit("30 per minute")
@login_required
@super_admin_required
def get_queue_status():
    """Get SOAR queue status counts summary."""
    conn = None
    try:
        conn = get_db_connection()
        status_counts = get_queue_status_counts(conn)
        
        # Ensure all known statuses are present with zero defaults
        all_statuses = {"pending", "running", "awaiting_approval", "success", "failed", "skipped"}
        counts = {status: status_counts.get(status, 0) for status in all_statuses}
        total = sum(counts.values())
        
        return jsonify({
            "counts": counts,
            "total": total,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }), 200
    except Exception:
        current_app.logger.exception("Error reading SOAR queue status")
        return jsonify({"error": "Unable to read SOAR queue"}), 500
    finally:
        if conn:
            conn.close()


@admin_bp.route("/admin/soar/queue/recent", methods=["GET"])
@limiter.limit("30 per minute")
@login_required
@super_admin_required
def get_queue_recent():
    """Get recent SOAR queue items."""
    limit = request.args.get("limit", "50")
    status_filter = request.args.get("status", None)
    
    # Validate limit is numeric
    try:
        limit = int(limit)
        if limit < 1:
            return jsonify({"error": "limit must be >= 1"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "limit must be an integer"}), 400
    
    # Validate status filter if provided
    if status_filter is not None:
        valid_statuses = {"pending", "running", "awaiting_approval", "success", "failed", "skipped"}
        if status_filter not in valid_statuses:
            return jsonify({"error": f"status must be one of {sorted(valid_statuses)}"}), 400
    
    conn = None
    try:
        conn = get_db_connection()
        # Helper function clamps limit to 100 max
        queue_rows = list_recent_queue_actions(conn, limit=limit, status=status_filter)
        response_outcomes = get_latest_outcomes_for_queues_bulk(
            conn,
            [row["id"] for row in queue_rows],
        )
        
        items = [
            _serialize_queue_item_for_list(
                row,
                response_outcome=response_outcomes.get(row["id"]),
            )
            for row in queue_rows
        ]
        
        return jsonify({
            "items": items,
            "limit": limit,
            "status": status_filter,
        }), 200
    except Exception:
        current_app.logger.exception("Error reading SOAR queue recent items")
        return jsonify({"error": "Unable to read SOAR queue"}), 500
    finally:
        if conn:
            conn.close()


@admin_bp.route("/admin/soar/queue/<int:queue_id>", methods=["GET"])
@limiter.limit("30 per minute")
@login_required
@super_admin_required
def get_queue_item_detail(queue_id):
    """Get a specific SOAR queue item detail."""
    conn = None
    try:
        conn = get_db_connection()
        queue_row = get_queue_action(conn, queue_id)
        
        if queue_row is None:
            return jsonify({"error": "Queue item not found"}), 404
        
        response_outcome = get_latest_outcomes_for_queues_bulk(conn, [queue_id]).get(queue_id)
        item = _serialize_queue_item_for_detail(
            queue_row,
            response_outcome=response_outcome,
        )
        approval = get_latest_approval_for_queue_action(
            conn, queue_id=queue_id, action=queue_row["action"]
        )
        item["latest_approval"] = _serialize_approval_summary(approval)
        item["approval_events"] = (
            list_approval_events(conn, approval["id"]) if approval is not None else []
        )
        return jsonify(item), 200
    except Exception:
        current_app.logger.exception("Error reading SOAR queue item detail queue_id=%s", queue_id)
        return jsonify({"error": "Unable to read SOAR queue"}), 500
    finally:
        if conn:
            conn.close()


@admin_bp.route("/admin/soar/worker/run-once", methods=["POST"])
@limiter.limit("10 per minute")
@login_required
@super_admin_required
def run_soar_worker_once():
    """Run one bounded SOAR worker batch in simulation mode."""
    data = request.get_json(silent=True) or {}
    requested_mode = (data.get("mode") or "simulation").strip().lower() if isinstance(data.get("mode") or "simulation", str) else data.get("mode")
    if requested_mode != "simulation":
        return jsonify({"error": "SOAR worker admin run is simulation-only"}), 400

    try:
        requested_batch_size, batch_size = _parse_soar_run_batch_size(data)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    started_at = datetime.now(timezone.utc).isoformat()
    conn = None
    try:
        conn = get_db_connection()
        results = process_batch(conn, limit=batch_size, executor=SimulationExecutor())
        summary = _summarize_soar_worker_results(results)
        completed_at = datetime.now(timezone.utc).isoformat()

        log_audit_event(
            "SOAR_WORKER_RUN_ONCE",
            actor_username=current_user.id,
            actor_role=current_user.role,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={
                "mode": "simulation",
                "requested_batch_size": requested_batch_size,
                "batch_size": batch_size,
                "summary": summary,
            },
        )
        current_app.logger.info(
            "SOAR worker run-once triggered actor=%s batch_size=%s summary=%s",
            current_user.id,
            batch_size,
            summary,
        )

        return jsonify({
            "mode": "simulation",
            "requested_batch_size": requested_batch_size,
            "batch_size": batch_size,
            "started_at": started_at,
            "completed_at": completed_at,
            "summary": summary,
            "results": results,
        }), 200
    except Exception:
        current_app.logger.exception("Error running SOAR worker batch")
        return jsonify({"error": "Unable to run SOAR worker batch"}), 500
    finally:
        if conn:
            conn.close()


@admin_bp.route("/admin/soar/approvals/expire-pending", methods=["POST"])
@limiter.limit("10 per minute")
@login_required
@super_admin_required
def expire_pending_approvals():
    """Manually expire overdue approvals and sweep linked queue rows."""
    conn = None
    try:
        conn = get_db_connection()
        expired = expire_pending_requests(conn)
        swept = sweep_terminal_approval_queue_rows(conn)
        conn.commit()
        return jsonify({
            "expired_approvals": len(expired),
            "skipped_queue_rows": len(swept),
            "expired_approval_ids": [row["id"] for row in expired],
            "skipped_queue_ids": [row["id"] for row in swept],
        }), 200
    except Exception:
        if conn:
            conn.rollback()
        current_app.logger.exception("Error in expire_pending_approvals")
        return jsonify({"error": "Unable to expire approvals"}), 500
    finally:
        if conn:
            conn.close()
