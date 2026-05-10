"""
Read-only HTTP API for playbook definitions and executions.

No trigger matching, execution creation, or queue side effects — observability only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from flask import Blueprint, current_app, jsonify, request
from flask_login import login_required

from core.auth import analyst_or_super_admin_required
from core.db import get_db_connection
from core.playbook_store import (
    get_playbook_definition,
    get_playbook_execution,
    list_playbook_executions,
)

playbook_bp = Blueprint("playbooks", __name__)

DEFAULT_LIMIT = 50
MAX_LIMIT = 100

_VALID_EXECUTION_STATUSES = frozenset(
    {"pending", "running", "success", "failed", "abandoned"}
)


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
