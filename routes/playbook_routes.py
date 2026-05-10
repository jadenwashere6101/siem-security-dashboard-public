"""
HTTP API for playbook definitions and executions.

GET routes are read-only for analysts and super admins. Definition mutations
(POST/PUT/PATCH) are super_admin only and do not run matching, enqueue work, or
create execution rows.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import psycopg2
from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from core.auth import analyst_or_super_admin_required, super_admin_required
from core.audit_helpers import log_audit_event
from core.approval_store import get_latest_playbook_step_approval_request
from core.db import get_db_connection
from core.playbook_store import (
    abandon_playbook_execution,
    active_playbook_execution_exists,
    create_playbook_definition,
    create_retry_execution,
    get_playbook_definition,
    get_playbook_execution,
    list_playbook_executions,
    mark_playbook_execution_permanently_failed,
    set_playbook_definition_enabled,
    update_execution_status,
    update_playbook_definition,
)
from engines.playbook_registry import validate_playbook_steps

playbook_bp = Blueprint("playbooks", __name__)

DEFAULT_LIMIT = 50
MAX_LIMIT = 100

_VALID_EXECUTION_STATUSES = frozenset(
    {
        "pending",
        "running",
        "awaiting_approval",
        "success",
        "failed",
        "abandoned",
        "permanently_failed",
    }
)

PLAYBOOK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
MAX_PLAYBOOK_NAME_LEN = 200


def _validate_new_playbook_id(raw: Any) -> tuple[str | None, str | None]:
    """Return (normalized_id, error_message)."""
    if raw is None:
        return None, "playbook id is required"
    if not isinstance(raw, str):
        return None, "playbook id must be a string"
    s = raw.strip()
    if not s:
        return None, "playbook id is required"
    if not PLAYBOOK_ID_RE.fullmatch(s):
        return None, "invalid playbook id format"
    return s, None


def _validate_name_field(raw: Any) -> tuple[str | None, str | None]:
    if raw is None:
        return None, "name is required"
    if not isinstance(raw, str):
        return None, "name must be a string"
    n = raw.strip()
    if not n:
        return None, "name must not be empty"
    if len(n) > MAX_PLAYBOOK_NAME_LEN:
        return None, f"name must be at most {MAX_PLAYBOOK_NAME_LEN} characters"
    return n, None


def _normalize_description(raw: Any) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    t = raw.strip()
    return t if t else None


def _validate_trigger_config_field(raw: Any) -> tuple[dict[str, Any] | None, str | None]:
    if raw is None:
        return {}, None
    if not isinstance(raw, dict):
        return None, "trigger_config must be an object"
    return raw, None


def _validate_steps_field(raw: Any) -> tuple[list[dict] | None, str | None]:
    if raw is None:
        return None, "steps is required"
    if not isinstance(raw, list):
        return None, "steps must be a list"
    errs = validate_playbook_steps(raw)
    if errs:
        return None, "; ".join(errs)
    return raw, None


def _validate_enabled_field(raw: Any, *, required: bool) -> tuple[bool | None, str | None]:
    if raw is None:
        if required:
            return None, "enabled is required"
        return None, None
    if not isinstance(raw, bool):
        return None, "enabled must be a boolean"
    return raw, None


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _serialize_definition_row(row: tuple[Any, ...]) -> dict[str, Any]:
    (
        row_id,
        name,
        description,
        trigger_config,
        steps,
        enabled,
        created_at,
        updated_at,
    ) = row
    return {
        "id": row_id,
        "name": name,
        "description": description,
        "trigger_config": trigger_config if isinstance(trigger_config, dict) else {},
        "steps": steps if isinstance(steps, list) else [],
        "enabled": enabled,
        "created_at": _iso(created_at),
        "updated_at": _iso(updated_at),
    }


def _serialize_definition_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "trigger_config": row["trigger_config"],
        "steps": row["steps"],
        "enabled": row["enabled"],
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }


def _serialize_execution_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "playbook_id": row["playbook_id"],
        "alert_id": row["alert_id"],
        "incident_id": row["incident_id"],
        "status": row["status"],
        "started_at": _iso(row["started_at"]),
        "completed_at": _iso(row["completed_at"]),
        "last_completed_step": row["last_completed_step"],
        "steps_log": row["steps_log"],
        "created_at": _iso(row["created_at"]),
    }


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


def _parse_enabled_filter(raw: str | None) -> tuple[bool | None, str | None]:
    """Return (enabled_filter, error_message). None means no filter (all definitions)."""
    if raw is None:
        return None, None
    lowered = raw.strip().lower()
    if lowered == "true":
        return True, None
    if lowered == "false":
        return False, None
    return None, "invalid enabled filter"


def _derive_gating_step_index(execution: dict[str, Any]) -> int:
    steps_log = execution.get("steps_log")
    if isinstance(steps_log, list):
        for entry in reversed(steps_log):
            if not isinstance(entry, dict):
                continue
            if entry.get("status") == "awaiting_approval":
                raw_index = entry.get("step_index")
                try:
                    return int(raw_index)
                except (TypeError, ValueError):
                    break
    last_completed = execution.get("last_completed_step")
    return (int(last_completed) if last_completed is not None else -1) + 1


def _write_playbook_execution_audit(event_type: str, details: dict[str, Any]) -> None:
    log_audit_event(
        event_type,
        actor_username=current_user.id,
        actor_role=getattr(current_user, "role", None),
        http_method=request.method,
        request_path=request.path,
        source_ip=request.remote_addr,
        details=details,
    )


def _list_definitions(conn, enabled_filter: bool | None, limit: int) -> list[dict[str, Any]]:
    """Read-only list; mirrors playbook_definitions columns used by the store."""
    with conn.cursor() as cur:
        if enabled_filter is True:
            cur.execute(
                """
                SELECT id, name, description, trigger_config, steps, enabled,
                       created_at, updated_at
                FROM playbook_definitions
                WHERE enabled = TRUE
                ORDER BY id ASC
                LIMIT %s
                """,
                (limit,),
            )
        elif enabled_filter is False:
            cur.execute(
                """
                SELECT id, name, description, trigger_config, steps, enabled,
                       created_at, updated_at
                FROM playbook_definitions
                WHERE enabled = FALSE
                ORDER BY id ASC
                LIMIT %s
                """,
                (limit,),
            )
        else:
            cur.execute(
                """
                SELECT id, name, description, trigger_config, steps, enabled,
                       created_at, updated_at
                FROM playbook_definitions
                ORDER BY id ASC
                LIMIT %s
                """,
                (limit,),
            )
        return [_serialize_definition_row(row) for row in cur.fetchall()]


@playbook_bp.route("/playbooks", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def list_playbooks_route():
    conn = None
    try:
        enabled_raw = request.args.get("enabled")
        enabled_filter, enabled_err = _parse_enabled_filter(enabled_raw)
        if enabled_err:
            return jsonify({"error": enabled_err}), 400

        limit, limit_error = _parse_non_negative_int(
            request.args.get("limit"),
            DEFAULT_LIMIT,
            "limit",
        )
        if limit_error:
            return jsonify({"error": limit_error}), 400
        limit = min(limit, MAX_LIMIT)

        conn = get_db_connection()
        items = _list_definitions(conn, enabled_filter, limit)
        return (
            jsonify(
                {
                    "items": items,
                    "limit": limit,
                    "enabled": enabled_filter,
                }
            ),
            200,
        )
    except Exception as error:
        current_app.logger.error("Error in list_playbooks_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@playbook_bp.route("/playbooks", methods=["POST"])
@login_required
@super_admin_required
def create_playbook_route():
    conn = None
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "invalid JSON body"}), 400

        pid, pid_err = _validate_new_playbook_id(data.get("id"))
        if pid_err:
            return jsonify({"error": pid_err}), 400

        name, name_err = _validate_name_field(data.get("name"))
        if name_err:
            return jsonify({"error": name_err}), 400

        trigger_config, tc_err = _validate_trigger_config_field(data.get("trigger_config"))
        if tc_err:
            return jsonify({"error": tc_err}), 400

        steps, steps_err = _validate_steps_field(data.get("steps"))
        if steps_err:
            return jsonify({"error": steps_err}), 400

        enabled, en_err = _validate_enabled_field(data.get("enabled"), required=False)
        if en_err:
            return jsonify({"error": en_err}), 400
        enabled_final = False if enabled is None else enabled

        description = _normalize_description(data.get("description"))

        conn = get_db_connection()
        row = create_playbook_definition(
            conn,
            pid,
            name,
            steps=steps,
            trigger_config=trigger_config,
            enabled=enabled_final,
            description=description,
        )
        conn.commit()
        return jsonify(_serialize_definition_dict(row)), 201
    except ValueError as ve:
        if conn:
            conn.rollback()
        return jsonify({"error": str(ve)}), 400
    except psycopg2.IntegrityError:
        if conn:
            conn.rollback()
        return jsonify({"error": "playbook id already exists"}), 409
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("Error in create_playbook_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@playbook_bp.route("/playbooks/<string:playbook_id>", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def get_playbook_route(playbook_id):
    conn = None
    try:
        conn = get_db_connection()
        row = get_playbook_definition(conn, playbook_id)
        if row is None:
            return jsonify({"error": "playbook not found"}), 404
        return jsonify(_serialize_definition_dict(row)), 200
    except Exception as error:
        current_app.logger.error("Error in get_playbook_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@playbook_bp.route("/playbooks/<string:playbook_id>", methods=["PUT"])
@login_required
@super_admin_required
def update_playbook_route(playbook_id):
    conn = None
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "invalid JSON body"}), 400

        if "id" in data and str(data.get("id", "")).strip() != playbook_id:
            return jsonify({"error": "playbook id cannot be changed"}), 400

        name, name_err = _validate_name_field(data.get("name"))
        if name_err:
            return jsonify({"error": name_err}), 400

        trigger_config, tc_err = _validate_trigger_config_field(data.get("trigger_config"))
        if tc_err:
            return jsonify({"error": tc_err}), 400

        steps, steps_err = _validate_steps_field(data.get("steps"))
        if steps_err:
            return jsonify({"error": steps_err}), 400

        enabled, en_err = _validate_enabled_field(data.get("enabled"), required=True)
        if en_err:
            return jsonify({"error": en_err}), 400

        description = _normalize_description(data.get("description"))

        conn = get_db_connection()
        row = update_playbook_definition(
            conn,
            playbook_id,
            name=name,
            description=description,
            trigger_config=trigger_config,
            steps=steps,
            enabled=enabled,
        )
        if row is None:
            conn.rollback()
            return jsonify({"error": "playbook not found"}), 404
        conn.commit()
        return jsonify(_serialize_definition_dict(row)), 200
    except ValueError as ve:
        if conn:
            conn.rollback()
        return jsonify({"error": str(ve)}), 400
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("Error in update_playbook_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@playbook_bp.route("/playbooks/<string:playbook_id>/enabled", methods=["PATCH"])
@login_required
@super_admin_required
def patch_playbook_enabled_route(playbook_id):
    conn = None
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "invalid JSON body"}), 400

        enabled, en_err = _validate_enabled_field(data.get("enabled"), required=True)
        if en_err:
            return jsonify({"error": en_err}), 400

        conn = get_db_connection()
        row = set_playbook_definition_enabled(conn, playbook_id, enabled)
        if row is None:
            conn.rollback()
            return jsonify({"error": "playbook not found"}), 404
        conn.commit()
        return jsonify(_serialize_definition_dict(row)), 200
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("Error in patch_playbook_enabled_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@playbook_bp.route("/playbook-executions", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def list_playbook_executions_route():
    conn = None
    try:
        playbook_id = request.args.get("playbook_id")
        if playbook_id is not None and not playbook_id.strip():
            return jsonify({"error": "invalid playbook_id filter"}), 400
        if playbook_id is not None:
            playbook_id = playbook_id.strip()

        status = request.args.get("status")
        if status is not None:
            status = status.strip()
            if status not in _VALID_EXECUTION_STATUSES:
                return jsonify({"error": "invalid status filter"}), 400

        limit, limit_error = _parse_non_negative_int(
            request.args.get("limit"),
            DEFAULT_LIMIT,
            "limit",
        )
        if limit_error:
            return jsonify({"error": limit_error}), 400
        limit = min(limit, MAX_LIMIT)

        conn = get_db_connection()
        rows = list_playbook_executions(
            conn,
            playbook_id=playbook_id,
            status=status,
            limit=limit,
        )
        items = [_serialize_execution_dict(r) for r in rows]
        return (
            jsonify(
                {
                    "items": items,
                    "limit": limit,
                    "playbook_id": playbook_id,
                    "status": status,
                }
            ),
            200,
        )
    except Exception as error:
        current_app.logger.error("Error in list_playbook_executions_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@playbook_bp.route("/playbook-executions/<int:execution_id>", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def get_playbook_execution_route(execution_id):
    conn = None
    try:
        conn = get_db_connection()
        row = get_playbook_execution(conn, execution_id)
        if row is None:
            return jsonify({"error": "playbook execution not found"}), 404
        return jsonify(_serialize_execution_dict(row)), 200
    except Exception as error:
        current_app.logger.error("Error in get_playbook_execution_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@playbook_bp.route("/playbook-executions/<int:execution_id>/retry", methods=["POST"])
@login_required
@super_admin_required
def retry_playbook_execution_route(execution_id):
    conn = None
    try:
        conn = get_db_connection()
        execution = get_playbook_execution(conn, execution_id)
        if execution is None:
            return jsonify({"error": "playbook execution not found"}), 404

        if execution["status"] not in {"failed", "abandoned"}:
            return (
                jsonify(
                    {
                        "error": (
                            "retry requires failed or abandoned execution; "
                            f"current status: {execution['status']}"
                        )
                    }
                ),
                409,
            )

        if get_playbook_definition(conn, execution["playbook_id"]) is None:
            return jsonify({"error": "playbook definition not found for execution"}), 409

        if active_playbook_execution_exists(
            conn,
            execution["playbook_id"],
            execution["alert_id"],
        ):
            return (
                jsonify({"error": "active execution already exists for playbook and alert"}),
                409,
            )

        new_execution_id = create_retry_execution(conn, execution_id)
        conn.commit()
        _write_playbook_execution_audit(
            "PLAYBOOK_EXECUTION_RETRY",
            {
                "source_execution_id": execution_id,
                "new_execution_id": new_execution_id,
                "playbook_id": execution["playbook_id"],
            },
        )
        return (
            jsonify(
                {
                    "source_execution_id": execution_id,
                    "new_execution_id": new_execution_id,
                    "status": "pending",
                    "message": "New simulation execution created. No steps have run yet.",
                }
            ),
            201,
        )
    except ValueError as error:
        if conn:
            conn.rollback()
        status_code = 404 if str(error) == "execution not found" else 409
        return jsonify({"error": str(error)}), status_code
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("Error in retry_playbook_execution_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@playbook_bp.route("/playbook-executions/<int:execution_id>/abandon", methods=["POST"])
@login_required
@super_admin_required
def abandon_playbook_execution_route(execution_id):
    conn = None
    try:
        conn = get_db_connection()
        execution = get_playbook_execution(conn, execution_id)
        if execution is None:
            return jsonify({"error": "playbook execution not found"}), 404

        previous_status = execution["status"]
        outcome = abandon_playbook_execution(conn, execution_id)
        conn.commit()
        if outcome == "no_op":
            return jsonify({"outcome": "no_op", "execution_id": execution_id}), 200

        _write_playbook_execution_audit(
            "PLAYBOOK_EXECUTION_ABANDON",
            {
                "execution_id": execution_id,
                "previous_status": previous_status,
                "playbook_id": execution["playbook_id"],
            },
        )
        return jsonify({"outcome": "abandoned", "execution_id": execution_id}), 200
    except ValueError as error:
        if conn:
            conn.rollback()
        if "execution not found" in str(error):
            return jsonify({"error": str(error)}), 404
        if "cannot abandon terminal" in str(error):
            return jsonify({"error": str(error)}), 409
        return jsonify({"error": str(error)}), 409
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("Error in abandon_playbook_execution_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@playbook_bp.route("/playbook-executions/<int:execution_id>/permanently-fail", methods=["POST"])
@login_required
@super_admin_required
def permanently_fail_playbook_execution_route(execution_id):
    conn = None
    try:
        conn = get_db_connection()
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "JSON body required"}), 400
        raw_reason = payload.get("failure_reason")
        if raw_reason is None:
            return jsonify({"error": "failure_reason is required"}), 400
        if not isinstance(raw_reason, str):
            return jsonify({"error": "failure_reason must be a string"}), 400

        previous = get_playbook_execution(conn, execution_id)
        if previous is None:
            return jsonify({"error": "playbook execution not found"}), 404

        updated = mark_playbook_execution_permanently_failed(
            conn,
            execution_id,
            failure_reason=raw_reason,
        )
        if updated is None:
            return jsonify({"error": "playbook execution not found"}), 404

        conn.commit()
        outcome = "no_op" if previous["status"] == "permanently_failed" else "permanently_failed"
        if outcome != "no_op":
            _write_playbook_execution_audit(
                "PLAYBOOK_EXECUTION_PERMANENTLY_FAIL",
                {
                    "execution_id": execution_id,
                    "playbook_id": updated["playbook_id"],
                    "outcome": outcome,
                    "previous_status": previous["status"],
                },
            )
        body = _serialize_execution_dict(updated)
        body["outcome"] = outcome
        return jsonify(body), 200
    except ValueError as error:
        if conn:
            conn.rollback()
        message = str(error)
        if message == "failure_reason is required":
            return jsonify({"error": message}), 400
        if "cannot mark execution as permanently_failed from terminal status" in message:
            return jsonify({"error": message}), 409
        if "permanently_failed is only allowed from" in message:
            return jsonify({"error": message}), 409
        return jsonify({"error": message}), 400
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error(
            "Error in permanently_fail_playbook_execution_route: %s", error
        )
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@playbook_bp.route("/playbook-executions/<int:execution_id>/resume", methods=["POST"])
@login_required
@super_admin_required
def resume_playbook_execution_route(execution_id):
    conn = None
    try:
        conn = get_db_connection()
        execution = get_playbook_execution(conn, execution_id)
        if execution is None:
            return jsonify({"error": "playbook execution not found"}), 404

        if execution["status"] != "awaiting_approval":
            return (
                jsonify(
                    {
                        "error": (
                            "resume requires awaiting_approval execution; "
                            f"current status: {execution['status']}"
                        )
                    }
                ),
                409,
            )

        gating_step_index = _derive_gating_step_index(execution)
        approval = get_latest_playbook_step_approval_request(
            conn,
            playbook_execution_id=execution_id,
            playbook_step_index=gating_step_index,
        )
        if approval is None:
            return (
                jsonify({"error": f"no approval request found for gating step {gating_step_index}"}),
                409,
            )
        if approval["status"] != "approved":
            return (
                jsonify(
                    {
                        "error": (
                            f"approval for step {gating_step_index} is not approved; "
                            f"current status: {approval['status']}"
                        )
                    }
                ),
                409,
            )

        update_execution_status(conn, execution_id, "pending")
        conn.commit()
        _write_playbook_execution_audit(
            "PLAYBOOK_EXECUTION_RESUME",
            {
                "execution_id": execution_id,
                "playbook_id": execution["playbook_id"],
                "gating_step_index": gating_step_index,
                "approval_request_id": approval["id"],
            },
        )
        return (
            jsonify(
                {
                    "execution_id": execution_id,
                    "status": "pending",
                    "message": "Simulation execution re-queued. Run the executor to continue.",
                }
            ),
            200,
        )
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("Error in resume_playbook_execution_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()
