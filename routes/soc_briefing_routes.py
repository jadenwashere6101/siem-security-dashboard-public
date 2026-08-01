from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from core.ai import soc_briefing_history_store
from core.ai.readiness import get_ai_gateway_status
from core.ai.soc_briefing_runtime_store import (
    BRIEFING_MODE_MANUAL_ONLY,
    BRIEFING_MODE_SCHEDULED_AUTONOMOUS,
    create_manual_briefing_job,
    get_briefing_control_status,
    get_manual_briefing_lifecycle_status,
    update_controls,
)
from core.audit_helpers import log_audit_event
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


def _actor() -> tuple[str | None, str | None]:
    return getattr(current_user, "id", None), getattr(current_user, "role", None)


def _audit(event_type: str, details: dict) -> None:
    username, role = _actor()
    log_audit_event(
        event_type,
        actor_username=username,
        actor_role=role,
        http_method=request.method,
        request_path=request.path,
        source_ip=request.remote_addr,
        details=details,
    )


def _control_payload(conn) -> dict:
    status = get_briefing_control_status(conn)
    ai_status = get_ai_gateway_status()
    gateway = ai_status.get("gateway") if isinstance(ai_status, dict) else {}
    providers = ai_status.get("providers") if isinstance(ai_status, dict) else []
    local_provider = None
    if isinstance(providers, list):
        for provider in providers:
            if isinstance(provider, dict) and provider.get("provider") == gateway.get("local_provider"):
                local_provider = provider
                break
    status["ai"] = {
        "gateway": gateway,
        "local_provider": local_provider,
        "providers": providers,
        "local_only": gateway.get("mode") == "local_only",
        "no_paid_fallback": gateway.get("paid_fallback_enabled") is False,
    }
    return status


def _manual_lifecycle_payload(conn, *, job_id: int | None = None, already_running: bool = False) -> dict:
    payload = get_manual_briefing_lifecycle_status(
        conn,
        job_id=job_id,
        already_running=already_running,
    )
    ai_status = get_ai_gateway_status()
    gateway = ai_status.get("gateway") if isinstance(ai_status, dict) else {}
    providers = ai_status.get("providers") if isinstance(ai_status, dict) else []
    payload["ai"] = {
        "gateway": gateway,
        "providers": providers,
        "local_only": gateway.get("mode") == "local_only",
        "no_paid_fallback": gateway.get("paid_fallback_enabled") is False,
    }
    if not payload.get("job"):
        return payload
    local_ready = True
    if isinstance(providers, list) and gateway.get("local_provider"):
        for provider in providers:
            if isinstance(provider, dict) and provider.get("provider") == gateway.get("local_provider"):
                local_ready = bool(provider.get("ready"))
                if not local_ready:
                    payload.setdefault("blocked_reasons", []).append(
                        {
                            "code": "local_model_unavailable",
                            "message": provider.get("message") or "Local model or provider is unavailable.",
                        }
                    )
                break
    payload["local_model_ready"] = local_ready
    return payload


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


@soc_briefing_bp.route("/soc-briefings/control", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def get_soc_briefing_control():
    conn = None
    try:
        conn = get_db_connection()
        payload = _control_payload(conn)
        conn.commit()
        return jsonify(payload), 200
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("get_soc_briefing_control: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@soc_briefing_bp.route("/soc-briefings/control/mode", methods=["PUT"])
@login_required
@analyst_or_super_admin_required
def update_soc_briefing_mode():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode") if isinstance(data, dict) else None
    if mode not in {BRIEFING_MODE_MANUAL_ONLY, BRIEFING_MODE_SCHEDULED_AUTONOMOUS}:
        return jsonify({"error": "invalid_mode", "message": "mode must be manual_only or scheduled_autonomous."}), 400
    conn = None
    try:
        username, _role = _actor()
        conn = get_db_connection()
        controls = update_controls(conn, mode=mode, updated_by=username)
        conn.commit()
        _audit("soc_briefing_mode_updated", {"mode": controls["mode"], "read_only": True})
        return jsonify(_control_payload(conn)), 200
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("update_soc_briefing_mode: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@soc_briefing_bp.route("/soc-briefings/control/pause", methods=["PUT"])
@login_required
@analyst_or_super_admin_required
def update_soc_briefing_pause():
    data = request.get_json(silent=True) or {}
    paused = data.get("schedules_paused") if isinstance(data, dict) else None
    if not isinstance(paused, bool):
        return jsonify({"error": "invalid_pause", "message": "schedules_paused must be true or false."}), 400
    pause_reason = data.get("pause_reason") if isinstance(data, dict) else None
    conn = None
    try:
        username, _role = _actor()
        conn = get_db_connection()
        controls = update_controls(
            conn,
            schedules_paused=paused,
            pause_reason=pause_reason,
            updated_by=username,
        )
        conn.commit()
        _audit(
            "soc_briefing_schedules_pause_updated",
            {"schedules_paused": bool(controls["schedules_paused"]), "read_only": True},
        )
        return jsonify(_control_payload(conn)), 200
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("update_soc_briefing_pause: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@soc_briefing_bp.route("/soc-briefings/run-now", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def run_soc_briefing_now():
    conn = None
    try:
        username, role = _actor()
        conn = get_db_connection()
        job, created = create_manual_briefing_job(conn, requested_by=username)
        conn.commit()
        _audit(
            "soc_briefing_manual_run_requested",
            {
                "job_id": job.get("id"),
                "schedule_id": job.get("schedule_id"),
                "window_id": job.get("window_id"),
                "created": created,
                "trigger_type": "manual",
                "actor_role": role,
                "read_only": True,
                "writes_performed": False,
            },
        )
        status_code = 201 if created else 200
        lifecycle = _manual_lifecycle_payload(conn, job_id=int(job["id"]), already_running=not created)
        return jsonify({
            "job": job,
            "created": created,
            "status": "queued" if created else "already_running",
            "manual_lifecycle": lifecycle,
        }), status_code
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("run_soc_briefing_now: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@soc_briefing_bp.route("/soc-briefings/manual-run/status", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def get_soc_briefing_manual_run_status():
    conn = None
    try:
        job_id, err = _parse_int_param("job_id")
        if err:
            return err
        conn = get_db_connection()
        payload = _manual_lifecycle_payload(conn, job_id=job_id)
        conn.commit()
        return jsonify(payload), 200
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("get_soc_briefing_manual_run_status: %s", error)
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
