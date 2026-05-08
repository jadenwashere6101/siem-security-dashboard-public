from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from core.audit_helpers import log_audit_event
from core.auth import analyst_or_super_admin_required
from core.db import get_db_connection
from core.incident_store import (
    ALL_INCIDENT_STATUSES,
    get_incident_detail,
    list_incidents,
    update_incident_status,
)


incident_bp = Blueprint("incidents", __name__)

VALID_SEVERITIES = frozenset({"LOW", "MEDIUM", "HIGH", "CRITICAL"})
DEFAULT_LIMIT = 50
MAX_LIMIT = 100


def _parse_non_negative_int(value, default, field_name):
    if value is None:
        return default, None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None, f"invalid {field_name}"
    if parsed < 0:
        return None, f"invalid {field_name}"
    return parsed, None


@incident_bp.route("/incidents", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def list_incidents_route():
    conn = None
    try:
        status = request.args.get("status")
        severity = request.args.get("severity")

        if status is not None and status not in ALL_INCIDENT_STATUSES:
            return jsonify({"error": "invalid status filter"}), 400

        if severity is not None:
            severity = severity.upper()
            if severity not in VALID_SEVERITIES:
                return jsonify({"error": "invalid severity filter"}), 400

        limit, limit_error = _parse_non_negative_int(
            request.args.get("limit"),
            DEFAULT_LIMIT,
            "limit",
        )
        if limit_error:
            return jsonify({"error": limit_error}), 400
        limit = min(limit, MAX_LIMIT)

        offset, offset_error = _parse_non_negative_int(
            request.args.get("offset"),
            0,
            "offset",
        )
        if offset_error:
            return jsonify({"error": offset_error}), 400

        conn = get_db_connection()
        incidents = list_incidents(
            conn,
            status=status,
            severity=severity,
            limit=limit,
            offset=offset,
        )
        return jsonify({"incidents": incidents, "count": len(incidents)}), 200
    except Exception as error:
        current_app.logger.error("Error in list_incidents_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@incident_bp.route("/incidents/<int:incident_id>", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def get_incident_route(incident_id):
    conn = None
    try:
        conn = get_db_connection()
        incident = get_incident_detail(conn, incident_id)
        if incident is None:
            return jsonify({"error": "incident not found"}), 404
        return jsonify({"incident": incident}), 200
    except Exception as error:
        current_app.logger.error("Error in get_incident_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@incident_bp.route("/incidents/<int:incident_id>/status", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def update_incident_status_route(incident_id):
    conn = None
    try:
        data = request.get_json(silent=True) or {}
        new_status = data.get("status")

        if not new_status:
            return jsonify({"error": "status is required"}), 400

        if new_status not in ALL_INCIDENT_STATUSES:
            return jsonify({"error": "invalid status"}), 400

        conn = get_db_connection()
        actor_username = getattr(current_user, "username", None) or current_user.id
        incident = update_incident_status(conn, incident_id, new_status, actor_username)
        conn.commit()

        log_audit_event(
            "UPDATE_INCIDENT_STATUS",
            actor_username=current_user.id,
            actor_role=current_user.role,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={"incident_id": incident_id, "status": new_status},
        )

        return jsonify({"incident": incident}), 200
    except ValueError as error:
        if conn:
            conn.rollback()
        message = str(error)
        if message == "incident not found":
            return jsonify({"error": "incident not found"}), 404
        return jsonify({"error": message}), 400
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("Error in update_incident_status_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()
