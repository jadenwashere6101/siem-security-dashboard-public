"""HTTP API for the Response Registry workspace (Phase 2)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from core.auth import analyst_or_super_admin_required
from core.db import get_db_connection
from core.indicator_response_registry import get_registry_detail, list_registry_records
from core.response_command_contracts import (
    ORIGIN_RESPONSE_REGISTRY,
    ResponseCommandRequest,
)
from core.response_command_service import execute_response_command

response_registry_bp = Blueprint("response_registry", __name__)

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

VIEW_DISPOSITIONS = {
    "all": None,
    "monitoring": ["monitored"],
    "blocklist_tracking": ["blocklist_tracked"],
    "escalated": ["escalated"],
    "pending": ["pending"],
    "failed_rejected": ["failed", "rejected"],
    "history": ["expired", "removed", "observed"],
}


def _parse_iso_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _actor_user_id() -> int | None:
    try:
        return int(current_user.id)
    except (TypeError, ValueError, AttributeError):
        return None


@response_registry_bp.route("/response-registry", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def list_response_registry():
    conn = None
    try:
        view = (request.args.get("view") or "all").strip().lower()
        dispositions = VIEW_DISPOSITIONS.get(view)
        if view not in VIEW_DISPOSITIONS:
            return jsonify({"error": f"Unsupported view '{view}'"}), 400

        disposition = (request.args.get("disposition") or "").strip() or None
        dispositions_param = (request.args.get("dispositions") or "").strip()
        if dispositions_param:
            dispositions = [part.strip() for part in dispositions_param.split(",") if part.strip()]

        limit = _safe_int(request.args.get("limit")) or DEFAULT_LIMIT
        offset = _safe_int(request.args.get("offset")) or 0
        limit = max(1, min(limit, MAX_LIMIT))
        offset = max(0, offset)

        updated_after = _parse_iso_datetime(request.args.get("updated_after"))
        updated_before = _parse_iso_datetime(request.args.get("updated_before"))
        if request.args.get("updated_after") and updated_after is None:
            return jsonify({"error": "Invalid updated_after"}), 400
        if request.args.get("updated_before") and updated_before is None:
            return jsonify({"error": "Invalid updated_before"}), 400

        conn = get_db_connection()
        payload = list_registry_records(
            conn,
            disposition=disposition,
            dispositions=dispositions,
            indicator_type=(request.args.get("indicator_type") or "").strip() or None,
            q=(request.args.get("q") or "").strip() or None,
            origin_surface=(request.args.get("origin") or request.args.get("origin_surface") or "").strip()
            or None,
            actor_user_id=_safe_int(request.args.get("actor_user_id")),
            outcome=(request.args.get("outcome") or "").strip() or None,
            enforcement=(request.args.get("enforcement") or "").strip() or None,
            requested_action=(request.args.get("requested_action") or "").strip() or None,
            related_alert_id=_safe_int(request.args.get("related_alert_id")),
            related_incident_id=_safe_int(request.args.get("related_incident_id")),
            updated_after=updated_after,
            updated_before=updated_before,
            sort=(request.args.get("sort") or "updated_at_desc").strip(),
            limit=limit,
            offset=offset,
        )
        payload["view"] = view
        return jsonify(payload), 200
    except Exception as error:
        current_app.logger.error("Error in list_response_registry: %s", error)
        return jsonify({"error": "Unable to list response registry"}), 500
    finally:
        if conn:
            conn.close()


@response_registry_bp.route("/response-registry/<int:registry_id>", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def get_response_registry_detail(registry_id: int):
    conn = None
    try:
        conn = get_db_connection()
        detail = get_registry_detail(conn, registry_id)
        if detail is None:
            return jsonify({"error": "Registry record not found"}), 404
        return jsonify(detail), 200
    except Exception as error:
        current_app.logger.error("Error in get_response_registry_detail: %s", error)
        return jsonify({"error": "Unable to load registry detail"}), 500
    finally:
        if conn:
            conn.close()


@response_registry_bp.route("/response-registry/commands", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def execute_registry_command():
    conn = None
    try:
        data = request.get_json() or {}
        action = (data.get("action") or "").strip()
        indicator_value = (data.get("indicator_value") or data.get("source_ip") or "").strip() or None
        reason = (data.get("reason") or data.get("note") or "").strip() or None
        expires_at = (data.get("expires_at") or "").strip() or None
        idempotency_key = (data.get("idempotency_key") or "").strip() or None

        if not action:
            return jsonify({"error": "action is required"}), 400

        conn = get_db_connection()
        result = execute_response_command(
            conn,
            ResponseCommandRequest(
                action=action,
                indicator_value=indicator_value,
                alert_id=_safe_int(data.get("alert_id")),
                incident_id=_safe_int(data.get("incident_id")),
                reason=reason,
                actor_user_id=_actor_user_id(),
                origin_surface=ORIGIN_RESPONSE_REGISTRY,
                idempotency_key=idempotency_key,
                expires_at=expires_at,
            ),
        )
        if not result.success:
            conn.rollback()
            status = 400
            if result.error_code in {"unsupported_action", "ambiguous_notify"}:
                status = 400
            return jsonify(result.to_api_dict()), status

        conn.commit()
        status_code = 200 if result.idempotent else 201
        return jsonify(result.to_api_dict()), status_code
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("Error in execute_registry_command: %s", error)
        return jsonify({"error": "Unable to execute registry command"}), 500
    finally:
        if conn:
            conn.close()
