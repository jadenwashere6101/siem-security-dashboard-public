"""
SOAR dead letter queue APIs.

Routes list/detail/metrics persisted dead letters and allow operator review
state changes. They do not execute retries, run playbooks, call adapters, or
send notifications.
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from core import dead_letter_store
from core.audit_helpers import log_audit_event
from core.auth import analyst_or_super_admin_required, super_admin_required
from core.db import get_db_connection
from core.notification_delivery_store import (
    redact_notification_delivery_metadata,
    sanitize_failure_message,
)
from core.playbook_store import create_retry_execution


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


def _json_body() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def _review_comment(payload: dict[str, Any]) -> str | None:
    raw = payload.get("comment")
    if raw is None:
        raw = payload.get("reason")
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError("comment must be a string")
    sanitized = sanitize_failure_message(raw)
    return sanitized if sanitized else None


def _actor_user_id(conn) -> int | None:
    username = getattr(current_user, "id", None)
    if not username:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE username = %s", (username,))
            row = cur.fetchone()
            return int(row[0]) if row else None
    except Exception:
        current_app.logger.warning(
            "dead_letter actor lookup failed username=%s", username, exc_info=True
        )
        return None


def _write_dead_letter_audit(event_type: str, details: dict[str, Any]) -> None:
    log_audit_event(
        event_type,
        actor_username=getattr(current_user, "id", None),
        actor_role=getattr(current_user, "role", None),
        http_method=request.method,
        request_path=request.path,
        source_ip=request.remote_addr,
        details=details,
    )


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


@dead_letter_bp.route("/dead-letters/<int:dead_letter_id>/dismiss", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def dismiss_dead_letter(dead_letter_id: int):
    conn = None
    try:
        payload = _json_body()
        try:
            comment = _review_comment(payload)
        except ValueError as exc:
            return jsonify({"error": "invalid_request", "message": str(exc)}), 400

        conn = get_db_connection()
        existing = dead_letter_store.get_dead_letter(conn, dead_letter_id)
        if existing is None:
            return jsonify({"error": "not_found", "message": "Dead letter not found."}), 404

        actor_id = _actor_user_id(conn)
        reason = comment or "dismissed from dead letter review"
        updated = dead_letter_store.mark_dead_letter_dismissed(
            conn,
            dead_letter_id,
            dismissed_by=actor_id,
            reason=reason,
        )
        if updated is None:
            conn.rollback()
            latest = dead_letter_store.get_dead_letter(conn, dead_letter_id) or existing
            return (
                jsonify(
                    {
                        "error": "invalid_state",
                        "message": "Dead letter cannot be dismissed from its current status.",
                        "status": latest.get("status"),
                    }
                ),
                409,
            )

        conn.commit()
        _write_dead_letter_audit(
            "DEAD_LETTER_DISMISS",
            {
                "dead_letter_id": dead_letter_id,
                "source_type": updated["source_type"],
                "source_id": updated["source_id"],
                "previous_status": existing["status"],
                "new_status": updated["status"],
            },
        )
        return jsonify(_safe_dead_letter(updated)), 200
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("dismiss_dead_letter: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@dead_letter_bp.route("/dead-letters/<int:dead_letter_id>/retry-request", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def retry_request_dead_letter(dead_letter_id: int):
    conn = None
    try:
        conn = get_db_connection()
        existing = dead_letter_store.get_dead_letter(conn, dead_letter_id)
        if existing is None:
            return jsonify({"error": "not_found", "message": "Dead letter not found."}), 404

        actor_id = _actor_user_id(conn)
        updated = dead_letter_store.mark_dead_letter_retry_requested(
            conn,
            dead_letter_id,
            requested_by=actor_id,
        )
        if updated is None:
            conn.rollback()
            latest = dead_letter_store.get_dead_letter(conn, dead_letter_id) or existing
            return (
                jsonify(
                    {
                        "error": "invalid_state",
                        "message": "Dead letter cannot be retry-requested from its current status.",
                        "status": latest.get("status"),
                    }
                ),
                409,
            )

        conn.commit()
        _write_dead_letter_audit(
            "DEAD_LETTER_RETRY_REQUEST",
            {
                "dead_letter_id": dead_letter_id,
                "source_type": updated["source_type"],
                "source_id": updated["source_id"],
                "previous_status": existing["status"],
                "new_status": updated["status"],
                "retry_count": updated["retry_count"],
            },
        )
        return jsonify(_safe_dead_letter(updated)), 200
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("retry_request_dead_letter: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@dead_letter_bp.route("/dead-letters/<int:dead_letter_id>/retry-execute", methods=["POST"])
@login_required
@super_admin_required
def retry_execute_dead_letter(dead_letter_id: int):
    conn = None
    try:
        conn = get_db_connection()
        existing = dead_letter_store.get_dead_letter(conn, dead_letter_id)
        if existing is None:
            return jsonify({"error": "not_found", "message": "Dead letter not found."}), 404
        if existing["status"] != "retrying":
            return (
                jsonify(
                    {
                        "error": "invalid_state",
                        "message": "Dead letter must be retrying before retry execution.",
                        "status": existing["status"],
                    }
                ),
                409,
            )
        if existing["source_type"] != "playbook_execution":
            return (
                jsonify(
                    {
                        "error": "unsupported_source_type",
                        "message": (
                            "Retry execution currently supports only playbook_execution "
                            "dead letters."
                        ),
                        "source_type": existing["source_type"],
                    }
                ),
                409,
            )

        try:
            new_execution_id = create_retry_execution(conn, existing["source_id"])
        except ValueError as exc:
            conn.rollback()
            return jsonify({"error": "retry_not_allowed", "message": str(exc)}), 409

        updated = dead_letter_store.mark_dead_letter_retried(conn, dead_letter_id)
        if updated is None:
            conn.rollback()
            latest = dead_letter_store.get_dead_letter(conn, dead_letter_id) or existing
            return (
                jsonify(
                    {
                        "error": "invalid_state",
                        "message": "Dead letter could not be marked retried.",
                        "status": latest.get("status"),
                    }
                ),
                409,
            )

        conn.commit()
        _write_dead_letter_audit(
            "DEAD_LETTER_RETRY_EXECUTE",
            {
                "dead_letter_id": dead_letter_id,
                "source_type": updated["source_type"],
                "source_id": updated["source_id"],
                "previous_status": existing["status"],
                "new_status": updated["status"],
                "new_execution_id": new_execution_id,
            },
        )
        return (
            jsonify(
                {
                    "dead_letter": _safe_dead_letter(updated),
                    "new_execution_id": new_execution_id,
                    "message": "New pending playbook retry execution created. No steps have run.",
                }
            ),
            201,
        )
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("retry_execute_dead_letter: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()
