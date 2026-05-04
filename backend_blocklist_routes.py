from datetime import datetime

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from core.audit_helpers import log_audit_event
from backend_auth import analyst_or_super_admin_required
from core.db import create_blocked_ip_record, get_db_connection, validate_blocked_ip

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
            SELECT id, ip_address, reason, status, created_by, created_at, expires_at, source_alert_id
            FROM blocked_ips
            ORDER BY created_at DESC
            """
        )

        rows = cur.fetchall()
        blocked_ips = [
            {
                "id": row[0],
                "ip_address": str(row[1]) if row[1] is not None else None,
                "reason": row[2],
                "status": row[3],
                "created_by": row[4],
                "created_at": str(row[5]),
                "expires_at": str(row[6]) if row[6] is not None else None,
                "source_alert_id": row[7],
            }
            for row in rows
        ]

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
        expires_at = (data.get("expires_at") or "").strip()
        parsed_expires_at = None

        if expires_at:
            try:
                parsed_expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            except ValueError:
                return jsonify({"error": "Invalid expires_at"}), 400

        conn = get_db_connection()
        cur = conn.cursor()

        block_id = create_blocked_ip_record(
            cur,
            ip_address,
            created_by=current_user.id,
            reason=reason,
            source_alert_id=source_alert_id,
            expires_at=parsed_expires_at,
        )
        normalized_ip = validate_blocked_ip(ip_address)
        conn.commit()

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
            },
        )

        return jsonify({"message": "Blocked IP added successfully", "id": block_id}), 201
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
