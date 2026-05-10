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
from flask_login import login_required

from core.auth import analyst_or_super_admin_required, super_admin_required
from core.db import get_db_connection
from core.playbook_store import (
    create_playbook_definition,
    get_playbook_definition,
    get_playbook_execution,
    list_playbook_executions,
    set_playbook_definition_enabled,
    update_playbook_definition,
)
from engines.playbook_registry import validate_playbook_steps

playbook_bp = Blueprint("playbooks", __name__)

DEFAULT_LIMIT = 50
MAX_LIMIT = 100

_VALID_EXECUTION_STATUSES = frozenset(
    {"pending", "running", "success", "failed", "abandoned"}
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
