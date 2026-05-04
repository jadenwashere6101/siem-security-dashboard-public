from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from core.audit_helpers import log_audit_event
from backend_auth import analyst_or_super_admin_required
from core.db import get_db_connection
from core.extensions import limiter
from core.ip_helpers import execute_response_action


alert_mutation_bp = Blueprint("alert_mutation", __name__)

VALID_RESPONSE_ACTIONS = {"block_ip", "monitor", "flag_high_priority"}
MAX_ALERT_NOTE_LENGTH = 2000


@alert_mutation_bp.route("/alerts/<int:alert_id>/response-log", methods=["GET"])
@login_required
def get_response_log(alert_id):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, alert_id, source_ip, action, status, details, executed_at
            FROM response_actions_log
            WHERE alert_id = %s
            ORDER BY executed_at DESC
            """,
            (alert_id,)
        )

        rows = cur.fetchall()

        logs = [
            {
                "id": row[0],
                "alert_id": row[1],
                "source_ip": row[2],
                "action": row[3],
                "status": row[4],
                "details": row[5],
                "executed_at": str(row[6])
            }
            for row in rows
        ]

        return jsonify(logs)

    except Exception as e:
        current_app.logger.error("Error in get_response_log: %s", e)
        return jsonify({"error": "Internal server error"}), 500

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@alert_mutation_bp.route("/alerts/<int:alert_id>/notes", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def get_alert_notes(alert_id):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, alert_id, author, note_text, created_at
            FROM alert_notes
            WHERE alert_id = %s
            ORDER BY created_at DESC
            """,
            (alert_id,)
        )

        rows = cur.fetchall()
        notes = [
            {
                "id": row[0],
                "alert_id": row[1],
                "author": row[2],
                "note_text": row[3],
                "created_at": str(row[4]),
            }
            for row in rows
        ]

        return jsonify(notes), 200
    except Exception as e:
        current_app.logger.error("Error in get_alert_notes: %s", e)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@alert_mutation_bp.route("/alerts/<int:alert_id>/notes", methods=["POST"])
@limiter.limit("30 per minute")
@login_required
@analyst_or_super_admin_required
def add_alert_note(alert_id):
    conn = None
    cur = None
    try:
        data = request.get_json() or {}
        note_text = (data.get("note_text") or "").strip()

        if not note_text:
            return jsonify({"error": "note_text is required"}), 400

        if len(note_text) > MAX_ALERT_NOTE_LENGTH:
            return jsonify({"error": f"note_text must be {MAX_ALERT_NOTE_LENGTH} characters or fewer"}), 400

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT 1
            FROM alerts
            WHERE id = %s
            """,
            (alert_id,)
        )

        if not cur.fetchone():
            return jsonify({"error": "Alert not found"}), 404

        cur.execute(
            """
            INSERT INTO alert_notes (alert_id, author, note_text)
            VALUES (%s, %s, %s)
            RETURNING id, alert_id, author, note_text, created_at
            """,
            (alert_id, current_user.id, note_text)
        )

        row = cur.fetchone()
        conn.commit()

        return jsonify({
            "id": row[0],
            "alert_id": row[1],
            "author": row[2],
            "note_text": row[3],
            "created_at": str(row[4]),
        }), 201
    except Exception as e:
        if conn:
            conn.rollback()
        current_app.logger.error("Error in add_alert_note: %s", e)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@alert_mutation_bp.route("/alerts/<int:alert_id>/execute", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def manual_execute_alert(alert_id):
    conn = None
    cur = None

    try:
        data = request.get_json() or {}
        action = data.get("action")

        if not action:
            return jsonify({"error": "Missing action"}), 400

        if action not in VALID_RESPONSE_ACTIONS:
            return jsonify({"error": "Invalid response action"}), 400

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT source_ip
            FROM alerts
            WHERE id = %s
            """,
            (alert_id,)
        )
        row = cur.fetchone()

        if not row:
            return jsonify({"error": "Alert not found"}), 404

        source_ip = row[0]

        block_reason = f"Manual block recorded from alert {alert_id}" if action == "block_ip" else None
        execution_status = execute_response_action(
            cur,
            alert_id,
            str(source_ip),
            action,
            create_blocklist_record=action == "block_ip",
            created_by=current_user.id,
            reason=block_reason,
            source_alert_id=alert_id if action == "block_ip" else None,
        )

        cur.execute(
            """
            UPDATE alerts
            SET response_action = %s,
                response_status = %s
            WHERE id = %s
            """,
            (action, execution_status, alert_id)
        )

        conn.commit()

        log_audit_event(
            "EXECUTE_RESPONSE_ACTION",
            actor_username=current_user.id,
            actor_role=current_user.role,
            target_alert_id=alert_id,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={"action": action, "status": execution_status},
        )

        return jsonify({
            "message": "Action executed successfully",
            "alert_id": alert_id,
            "action": action,
            "response_status": execution_status
        }), 200

    except ValueError as e:
        if conn:
            conn.rollback()
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        if conn:
            conn.rollback()
        print("Error in manual_execute_alert:", e)
        return jsonify({"error": "Internal server error"}), 500

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@alert_mutation_bp.route("/alerts/<int:alert_id>/status", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def update_alert_status(alert_id):
    try:
        data = request.get_json() or {}
        new_status = data.get("status")

        if new_status not in ["open", "resolved"]:
            return jsonify({"error": "Invalid status"}), 400

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            UPDATE alerts
            SET status = %s
            WHERE id = %s
            """,
            (new_status, alert_id),
        )

        if cur.rowcount == 0:
            conn.rollback()
            return jsonify({"error": "Alert not found"}), 404

        conn.commit()
        log_audit_event(
            "UPDATE_ALERT_STATUS",
            actor_username=current_user.id,
            actor_role=current_user.role,
            target_alert_id=alert_id,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={"status": new_status},
        )
        cur.close()
        conn.close()

        return jsonify({"message": "Alert status updated successfully"}), 200

    except Exception as e:
        current_app.logger.error("Error in update_alert_status: %s", e)
        return jsonify({"error": "Internal server error"}), 500
