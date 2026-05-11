"""
Read-only notification delivery attempt history (GET only).

Uses notification_delivery_store; does not create attempts, call adapters, or mutate
delivery rows. Responses return persisted rows (metadata already redacted at insert).
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from flask_login import login_required

from core import notification_delivery_store
from core.auth import analyst_or_super_admin_required
from core.db import get_db_connection

notification_delivery_bp = Blueprint("notification_deliveries", __name__)


def _parse_limit():
    raw = request.args.get("limit", default="100")
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        return None, (jsonify({"error": "invalid_query", "message": "limit must be an integer."}), 400)
    if limit < 1:
        return None, (jsonify({"error": "invalid_query", "message": "limit must be >= 1."}), 400)
    return limit, None


def _parse_offset():
    raw = request.args.get("offset", default="0")
    try:
        offset = int(raw)
    except (TypeError, ValueError):
        return None, (jsonify({"error": "invalid_query", "message": "offset must be an integer."}), 400)
    if offset < 0:
        return None, (jsonify({"error": "invalid_query", "message": "offset must be >= 0."}), 400)
    return offset, None


def _optional_int_param(name: str):
    raw = request.args.get(name)
    if raw is None or raw == "":
        return None, None
    try:
        return int(raw), None
    except ValueError:
        return None, (
            jsonify({"error": "invalid_query", "message": f"{name} must be an integer."}),
            400,
        )


def _optional_str_param(name: str) -> str | None:
    raw = request.args.get(name)
    if raw is None:
        return None
    s = raw.strip()
    return s if s else None


@notification_delivery_bp.route("/notification-deliveries", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def list_notification_deliveries():
    conn = None
    try:
        limit, err = _parse_limit()
        if err:
            return err
        offset, err = _parse_offset()
        if err:
            return err

        provider = _optional_str_param("provider")
        mode = _optional_str_param("mode")
        status = _optional_str_param("status")
        correlation_id = _optional_str_param("correlation_id")
        adapter_name = _optional_str_param("adapter_name")

        playbook_execution_id, err = _optional_int_param("playbook_execution_id")
        if err:
            return err
        incident_id, err = _optional_int_param("incident_id")
        if err:
            return err
        approval_request_id, err = _optional_int_param("approval_request_id")
        if err:
            return err

        conn = get_db_connection()
        try:
            items = notification_delivery_store.list_notification_delivery_attempts(
                conn,
                limit=limit,
                offset=offset,
                provider=provider,
                mode=mode,
                status=status,
                correlation_id=correlation_id,
                playbook_execution_id=playbook_execution_id,
                incident_id=incident_id,
                approval_request_id=approval_request_id,
                adapter_name=adapter_name,
            )
        except ValueError as exc:
            return jsonify({"error": "invalid_query", "message": str(exc)}), 400

        return (
            jsonify(
                {
                    "items": items,
                    "limit": limit,
                    "offset": offset,
                }
            ),
            200,
        )
    except Exception as error:
        current_app.logger.error("list_notification_deliveries: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@notification_delivery_bp.route("/notification-deliveries/<int:attempt_id>", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def get_notification_delivery(attempt_id: int):
    conn = None
    try:
        conn = get_db_connection()
        row = notification_delivery_store.get_notification_delivery_attempt(conn, attempt_id)
        if row is None:
            return jsonify({"error": "not_found", "message": "Delivery attempt not found."}), 404
        return jsonify(row), 200
    except Exception as error:
        current_app.logger.error("get_notification_delivery: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()
