from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from core.audit_helpers import log_audit_event
from core.auth import analyst_or_super_admin_required
from core.db import get_db_connection
from core.extensions import limiter
from core.incident_store import auto_close_resolved_p3_incidents_for_alert
from core.note_store import MAX_NOTE_LENGTH, create_alert_note, list_alert_notes, validate_note_text
from core.response_command_contracts import (
    ORIGIN_MANUAL_ALERT,
    ResponseCommandRequest,
)
from core.response_command_service import execute_response_command
from core.soar_response_outcomes import resolve_response_log_outcome


alert_mutation_bp = Blueprint("alert_mutation", __name__)

VALID_RESPONSE_ACTIONS = {"block_ip", "monitor", "flag_high_priority"}
MAX_ALERT_NOTE_LENGTH = MAX_NOTE_LENGTH


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
            (alert_id,),
        )

        rows = cur.fetchall()

        logs = []
        for row in rows:
            response_outcome = resolve_response_log_outcome(conn, row[0])
            logs.append(
                {
                    "id": row[0],
                    "alert_id": row[1],
                    "source_ip": row[2],
                    "action": row[3],
                    "status": row[4],
                    "details": row[5],
                    "executed_at": str(row[6]),
                    "response_outcome": response_outcome,
                }
            )

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
    try:
        conn = get_db_connection()
        return jsonify(list_alert_notes(conn, alert_id)), 200
    except Exception as e:
        current_app.logger.error("Error in get_alert_notes: %s", e)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@alert_mutation_bp.route("/alerts/<int:alert_id>/notes", methods=["POST"])
@limiter.limit("30 per minute")
@login_required
@analyst_or_super_admin_required
def add_alert_note(alert_id):
    conn = None
    try:
        data = request.get_json() or {}
        try:
            note_text = validate_note_text(data.get("note_text"))
        except ValueError as error:
            return jsonify({"error": str(error)}), 400

        conn = get_db_connection()
        try:
            note = create_alert_note(conn, alert_id=alert_id, author=current_user.id, note_text=note_text)
        except LookupError:
            return jsonify({"error": "Alert not found"}), 404

        conn.commit()

        return jsonify(note), 201
    except Exception as e:
        if conn:
            conn.rollback()
        current_app.logger.error("Error in add_alert_note: %s", e)
        return jsonify({"error": "Internal server error"}), 500
    finally:
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
        result = execute_response_command(
            conn,
            ResponseCommandRequest(
                action=action,
                indicator_value=str(source_ip) if source_ip is not None else None,
                alert_id=alert_id,
                reason=(
                    f"Manual block recorded from alert {alert_id}"
                    if action == "block_ip"
                    else data.get("reason")
                ),
                actor_user_id=_numeric_user_id_or_none(current_user.id),
                origin_surface=ORIGIN_MANUAL_ALERT,
                idempotency_key=f"manual-alert-{alert_id}-{action}",
            ),
        )
        if not result.success:
            conn.rollback()
            return jsonify({"error": result.error or result.message}), 400

        conn.commit()

        log_audit_event(
            "EXECUTE_RESPONSE_ACTION",
            actor_username=current_user.id,
            actor_role=current_user.role,
            target_alert_id=alert_id,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={
                "action": action,
                "status": result.compatible_fields.get("response_status", "executed"),
                "registry_record_id": result.registry_record_id,
                "blocked_ip_id": result.blocked_ip_id,
                "incident_id": result.incident_id,
            },
        )

        payload = {
            "message": "Action executed successfully",
            "alert_id": alert_id,
            "action": action,
            "response_status": result.compatible_fields.get("response_status", "executed"),
            **result.to_api_dict(),
        }
        return jsonify(payload), 200

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


def _numeric_user_id_or_none(user_id):
    try:
        return int(user_id)
    except (TypeError, ValueError):
        return None


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

        auto_closed_incident_ids = []
        if new_status == "resolved":
            auto_closed_incident_ids = auto_close_resolved_p3_incidents_for_alert(conn, alert_id)
        conn.commit()
        log_audit_event(
            "UPDATE_ALERT_STATUS",
            actor_username=current_user.id,
            actor_role=current_user.role,
            target_alert_id=alert_id,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={"status": new_status, "auto_closed_incident_ids": auto_closed_incident_ids},
        )
        cur.close()
        conn.close()

        return jsonify({"message": "Alert status updated successfully", "auto_closed_incident_ids": auto_closed_incident_ids}), 200

    except Exception as e:
        current_app.logger.error("Error in update_alert_status: %s", e)
        return jsonify({"error": "Internal server error"}), 500
