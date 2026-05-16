"""
Read-only SOAR dead letter queue APIs.

Routes only list/detail/metrics persisted dead letters. They do not retry,
dismiss, execute playbooks, call adapters, or send notifications.
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, jsonify, request
from flask_login import login_required

from core import dead_letter_store
from core.auth import analyst_or_super_admin_required
from core.db import get_db_connection
from core.notification_delivery_store import (
    redact_notification_delivery_metadata,
    sanitize_failure_message,
)


dead_letter_bp = Blueprint("dead_letters", __name__)


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


def _optional_bool_param(name: str):
    raw = request.args.get(name)
    if raw is None or raw == "":
        return None, None
    normalized = raw.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True, None
    if normalized in {"false", "0", "no"}:
        return False, None
    return None, (
        jsonify({"error": "invalid_query", "message": f"{name} must be a boolean."}),
        400,
    )


def _optional_str_param(name: str) -> str | None:
    raw = request.args.get(name)
    if raw is None:
        return None
    stripped = raw.strip()
    return stripped if stripped else None


def _safe_dead_letter(row: dict[str, Any]) -> dict[str, Any]:
    safe = dict(row)
    safe["payload_json"] = redact_notification_delivery_metadata(
        safe.get("payload_json") if isinstance(safe.get("payload_json"), dict) else {}
    )
    safe["error_message"] = sanitize_failure_message(safe.get("error_message"))
    safe["dismiss_reason"] = sanitize_failure_message(safe.get("dismiss_reason"))
    return safe


@dead_letter_bp.route("/dead-letters", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def list_dead_letters():
    conn = None
    try:
        limit, err = _parse_limit()
        if err:
            return err
        offset, err = _parse_offset()
        if err:
            return err

        incident_id, err = _optional_int_param("incident_id")
        if err:
            return err
        alert_id, err = _optional_int_param("alert_id")
        if err:
            return err
        execution_id, err = _optional_int_param("execution_id")
        if err:
            return err
        retryable, err = _optional_bool_param("retryable")
        if err:
            return err

        conn = get_db_connection()
        try:
            items = dead_letter_store.list_dead_letters(
                conn,
                limit=limit,
                offset=offset,
                status=_optional_str_param("status"),
                source_type=_optional_str_param("source_type"),
                failure_class=_optional_str_param("failure_class"),
                retryable=retryable,
                incident_id=incident_id,
                alert_id=alert_id,
                execution_id=execution_id,
            )
        except ValueError as exc:
            return jsonify({"error": "invalid_query", "message": str(exc)}), 400

        return jsonify({"items": [_safe_dead_letter(item) for item in items], "limit": limit, "offset": offset}), 200
    except Exception as error:
        current_app.logger.error("list_dead_letters: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@dead_letter_bp.route("/dead-letters/<int:dead_letter_id>", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def get_dead_letter(dead_letter_id: int):
    conn = None
    try:
        conn = get_db_connection()
        row = dead_letter_store.get_dead_letter(conn, dead_letter_id)
        if row is None:
            return jsonify({"error": "not_found", "message": "Dead letter not found."}), 404
        return jsonify(_safe_dead_letter(row)), 200
    except Exception as error:
        current_app.logger.error("get_dead_letter: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@dead_letter_bp.route("/metrics/dead-letters", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def dead_letter_metrics():
    conn = None
    try:
        conn = get_db_connection()
        return jsonify(dead_letter_store.get_dead_letter_metrics(conn)), 200
    except Exception as error:
        current_app.logger.error("dead_letter_metrics: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()
