from datetime import datetime

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from core.audit_helpers import log_audit_event
from core.auth import analyst_or_super_admin_required
from core.db import get_db_connection, validate_blocked_ip
from core.response_command_contracts import ORIGIN_BLOCKLIST_FORM, ResponseCommandRequest
from core.response_command_service import execute_response_command
from core.soar_response_outcomes import get_latest_outcomes_for_blocked_ips_bulk

blocklist_bp = Blueprint("blocklist", __name__)


@blocklist_bp.route("/blocked-ips", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def list_blocked_ips():
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                id,
                ip_address,
                reason,
                CASE
                    WHEN status = 'active'
                     AND expires_at IS NOT NULL
                     AND expires_at <= NOW()
                    THEN 'expired'
                    ELSE status
                END AS effective_status,
                created_by,
                created_at,
                expires_at,
                source_alert_id
            FROM blocked_ips
            ORDER BY created_at DESC
            """
        )

        rows = cur.fetchall()
        response_outcomes = get_latest_outcomes_for_blocked_ips_bulk(
            conn,
            [row[0] for row in rows],
        )
        blocked_ips = []
        for row in rows:
            blocked_ips.append(
                {
                    "id": row[0],
                    "ip_address": str(row[1]) if row[1] is not None else None,
                    "reason": row[2],
                    "status": row[3],
                    "created_by": row[4],
                    "created_at": str(row[5]),
                    "expires_at": str(row[6]) if row[6] is not None else None,
                    "source_alert_id": row[7],
                    "response_outcome": response_outcomes.get(row[0]),
                }
            )

        return jsonify(blocked_ips), 200
    except Exception as error:
        current_app.logger.error("Error in list_blocked_ips: %s", error)
        return jsonify({"error": "Unable to list blocked IPs"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@blocklist_bp.route("/blocked-ips", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def add_blocked_ip():
    conn = None
    cur = None

    try:
        data = request.get_json() or {}
        ip_address = data.get("ip_address")
        reason = (data.get("reason") or "").strip() or None
        source_alert_id = data.get("source_alert_id")
        expires_at = (data.get("expires_at") or "").strip() or None

        if expires_at:
            try:
                datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            except ValueError:
                return jsonify({"error": "Invalid expires_at"}), 400

        conn = get_db_connection()
        cur = conn.cursor()
        normalized_ip = validate_blocked_ip(ip_address)
        try:
            actor_user_id = int(current_user.id)
        except (TypeError, ValueError):
            actor_user_id = None
        result = execute_response_command(
            conn,
            ResponseCommandRequest(
                action="block_ip",
                indicator_value=normalized_ip,
                alert_id=source_alert_id,
                reason=reason,
                actor_user_id=actor_user_id,
                origin_surface=ORIGIN_BLOCKLIST_FORM,
                expires_at=expires_at,
                idempotency_key=f"blocklist-form-{normalized_ip}-{source_alert_id or 'none'}",
            ),
        )
        if not result.success:
            conn.rollback()
            return jsonify({"error": result.error or result.message}), 400

        conn.commit()
        block_id = result.blocked_ip_id

        log_audit_event(
            "block_ip_added",
            actor_username=current_user.id,
            actor_role=current_user.role,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={
                "ip_address": normalized_ip,
                "reason": reason,
                "actor": current_user.id,
                "source_alert_id": source_alert_id,
                "block_id": block_id,
                "idempotent": result.idempotent,
                "registry_record_id": result.registry_record_id,
            },
        )

        status_code = 200 if result.idempotent else 201
        return jsonify({
            "message": result.compatible_fields.get(
                "message", "Blocked IP added successfully"
            ),
            "id": block_id,
            **result.to_api_dict(),
        }), status_code
    except ValueError as error:
        if conn:
            conn.rollback()
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("Error in add_blocked_ip: %s", error)
        return jsonify({"error": "Unable to add blocked IP"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@blocklist_bp.route("/blocked-ips/<int:block_id>/unblock", methods=["PATCH"])
@login_required
@analyst_or_super_admin_required
def unblock_blocked_ip(block_id):
    conn = None
    cur = None

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ip_address, reason, source_alert_id, status
            FROM blocked_ips
            WHERE id = %s
            """,
            (block_id,),
        )
        row = cur.fetchone()

        if not row:
            return jsonify({"error": "Blocked IP entry not found"}), 404

        if row[3] != "active":
            return jsonify({"error": "Blocked IP entry is not active"}), 400

        cur.execute(
            """
            UPDATE blocked_ips
            SET status = 'inactive'
            WHERE id = %s
            """,
            (block_id,),
        )
        conn.commit()

        ip_address = str(row[0]) if row[0] is not None else None
        log_audit_event(
            "block_ip_removed",
            actor_username=current_user.id,
            actor_role=current_user.role,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={
                "ip_address": ip_address,
                "reason": row[1],
                "actor": current_user.id,
                "source_alert_id": row[2],
                "block_id": block_id,
            },
        )

        return jsonify({"message": "Blocked IP removed successfully"}), 200
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("Error in unblock_blocked_ip: %s", error)
        return jsonify({"error": "Unable to unblock blocked IP"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
