from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from core.ai import soc_briefing_history_store
from core.auth import analyst_or_super_admin_required, super_admin_required
from core.db import get_db_connection

soc_briefing_bp = Blueprint("soc_briefings", __name__)


def _parse_int_param(name: str, default: int | None = None) -> tuple[int | None, tuple | None]:
    raw = request.args.get(name)
    if raw in (None, ""):
        return default, None
    try:
        return int(raw), None
    except ValueError:
        return None, (jsonify({"error": "invalid_query", "message": f"{name} must be an integer."}), 400)


def _str_param(name: str) -> str | None:
    value = request.args.get(name)
    if value is None:
        return None
    normalized = value.strip()
    return normalized if normalized else None


@soc_briefing_bp.route("/soc-briefings", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def list_soc_briefings():
    conn = None
    try:
        limit, err = _parse_int_param("limit", soc_briefing_history_store.DEFAULT_LIMIT)
        if err:
            return err
        offset, err = _parse_int_param("offset", 0)
        if err:
            return err
        schedule_id, err = _parse_int_param("schedule_id")
        if err:
            return err

        conn = get_db_connection()
        try:
            payload = soc_briefing_history_store.list_briefings(
                conn,
                limit=limit or soc_briefing_history_store.DEFAULT_LIMIT,
                offset=offset or 0,
                status=_str_param("status"),
                content_status=_str_param("content_status"),
                schedule_id=schedule_id,
                delivery_status=_str_param("delivery_status"),
                provider_status=_str_param("provider_status"),
                generated_from=_str_param("generated_from"),
                generated_to=_str_param("generated_to"),
                search=_str_param("search"),
            )
        except ValueError as exc:
            return jsonify({"error": "invalid_query", "message": str(exc)}), 400
        return jsonify(payload), 200
    except Exception as error:
        current_app.logger.error("list_soc_briefings: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@soc_briefing_bp.route("/soc-briefings/<int:briefing_id>", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def get_soc_briefing(briefing_id: int):
    conn = None
    try:
        conn = get_db_connection()
        payload = soc_briefing_history_store.get_briefing_detail(conn, briefing_id)
        if payload is None:
            return jsonify({"error": "not_found", "message": "SOC briefing not found."}), 404
        return jsonify(payload), 200
    except Exception as error:
        current_app.logger.error("get_soc_briefing: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@soc_briefing_bp.route("/soc-briefings/<int:briefing_id>/deliveries/slack/retry", methods=["POST"])
@login_required
@super_admin_required
def retry_soc_briefing_slack_delivery(briefing_id: int):
    conn = None
    try:
        data = request.get_json(silent=True) or {}
        siem_url = data.get("siem_url") if isinstance(data, dict) else None
        conn = get_db_connection()
        try:
            result = soc_briefing_history_store.deliver_briefing_to_slack(
                conn,
                briefing_id,
                actor_username=getattr(current_user, "id", None),
                actor_role=getattr(current_user, "role", None),
                siem_url=siem_url,
            )
        except LookupError:
            conn.rollback()
            return jsonify({"error": "not_found", "message": "SOC briefing not found."}), 404
        conn.commit()
        return jsonify(result), 200
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("retry_soc_briefing_slack_delivery: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()
