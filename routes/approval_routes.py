from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from core.auth import analyst_or_super_admin_required, super_admin_required
from core.db import get_db_connection
from core.approval_store import (
    APPROVAL_STATUSES,
    approve_request,
    deny_request,
    get_approval_request,
    list_approval_requests,
)
from core.soar_response_outcomes import get_latest_outcomes_for_approvals_bulk


approval_bp = Blueprint("approvals", __name__)

DEFAULT_LIMIT = 50
MAX_LIMIT = 100


def _resolve_actor_user_id(conn, username):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE username = %s", (username,))
        row = cur.fetchone()
        return row[0] if row else None


def _resolve_or_create_actor_user_id(conn, username, role):
    actor_user_id = _resolve_actor_user_id(conn, username)
    if actor_user_id is not None:
        return actor_user_id

    # The built-in super-admin login uses the Flask-Login sentinel "admin"
    # without requiring a pre-existing users row. Approval decisions persist a
    # users.id foreign key and the database requires approved_by for approved
    # requests, so materialize that sentinel on demand.
    if username != "admin" or role != "super_admin":
        return None

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (username, password_hash, role, is_active)
            VALUES (%s, %s, %s, TRUE)
            ON CONFLICT (username) DO UPDATE
            SET role = EXCLUDED.role,
                is_active = TRUE
            RETURNING id
            """,
            ("admin", "sentinel_admin_no_direct_login", "super_admin"),
        )
        row = cur.fetchone()
        return row[0] if row else None


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


@approval_bp.route("/approvals", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def list_approvals_route():
    conn = None
    try:
        status = request.args.get("status")
        if status is not None and status not in APPROVAL_STATUSES:
            return jsonify({"error": "invalid status filter"}), 400

        incident_id_raw = request.args.get("incident_id")
        incident_id, incident_id_error = _parse_non_negative_int(
            incident_id_raw, None, "incident_id"
        )
        if incident_id_error:
            return jsonify({"error": incident_id_error}), 400

        queue_id_raw = request.args.get("queue_id")
        queue_id, queue_id_error = _parse_non_negative_int(
            queue_id_raw, None, "queue_id"
        )
        if queue_id_error:
            return jsonify({"error": queue_id_error}), 400

        limit, limit_error = _parse_non_negative_int(
            request.args.get("limit"), DEFAULT_LIMIT, "limit"
        )
        if limit_error:
            return jsonify({"error": limit_error}), 400
        limit = min(limit, MAX_LIMIT)

        offset, offset_error = _parse_non_negative_int(
            request.args.get("offset"), 0, "offset"
        )
        if offset_error:
            return jsonify({"error": offset_error}), 400

        conn = get_db_connection()
        approvals = list_approval_requests(
            conn,
            status=status,
            incident_id=incident_id,
            queue_id=queue_id,
            limit=limit,
            offset=offset,
        )
        approval_ids = [a["id"] for a in approvals]
        response_outcomes = get_latest_outcomes_for_approvals_bulk(conn, approval_ids)
        for approval in approvals:
            approval["response_outcome"] = response_outcomes.get(approval["id"])
        return jsonify({"approvals": approvals, "count": len(approvals)}), 200
    except Exception as error:
        current_app.logger.error("Error in list_approvals_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@approval_bp.route("/approvals/<int:approval_id>", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def get_approval_route(approval_id):
    conn = None
    try:
        conn = get_db_connection()
        approval = get_approval_request(conn, approval_id)
        if approval is None:
            return jsonify({"error": "approval not found"}), 404
        approval["response_outcome"] = get_latest_outcomes_for_approvals_bulk(
            conn, [approval_id]
        ).get(approval_id)
        return jsonify({"approval": approval}), 200
    except Exception as error:
        current_app.logger.error("Error in get_approval_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@approval_bp.route("/approvals/<int:approval_id>/decision", methods=["POST"])
@login_required
@super_admin_required
def decision_approval_route(approval_id):
    conn = None
    try:
        body = request.get_json(silent=True) or {}
        decision = body.get("decision")
        reason = body.get("reason")
        if reason is not None:
            reason = str(reason).strip() or None

        if not decision:
            return jsonify({"error": "decision is required"}), 400
        if decision not in ("approved", "denied"):
            return jsonify({"error": "invalid decision"}), 400

        conn = get_db_connection()
        actor_user_id = _resolve_or_create_actor_user_id(
            conn,
            current_user.id,
            getattr(current_user, "role", None),
        )

        if decision == "approved":
            updated = approve_request(
                conn,
                approval_id,
                actor_user_id=actor_user_id,
                decision_comment=reason,
            )
        else:
            updated = deny_request(
                conn,
                approval_id,
                actor_user_id=actor_user_id,
                decision_comment=reason,
            )

        conn.commit()
        return jsonify({"approval": updated}), 200

    except ValueError as error:
        if conn:
            conn.rollback()
        message = str(error)
        if message == "approval request not found":
            return jsonify({"error": message}), 404
        return jsonify({"error": message}), 400
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("Error in decision_approval_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()
