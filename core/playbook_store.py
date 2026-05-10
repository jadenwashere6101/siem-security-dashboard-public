"""
DB helpers for playbook_definitions and playbook_executions.

Callers own transaction boundaries (commit/rollback). Execution wiring from ingest
or workers is intentionally out of scope.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from psycopg2.extras import Json

from engines.playbook_registry import validate_playbook_steps

logger = logging.getLogger(__name__)

_TERMINAL_EXECUTION_STATUSES = frozenset({"success", "failed", "abandoned"})
_VALID_EXECUTION_STATUSES = frozenset(
    {"pending", "running", "success", "failed", "abandoned"}
)


def _definition_row_to_dict(record: tuple[Any, ...]) -> dict[str, Any]:
    (
        row_id,
        name,
        description,
        trigger_config,
        steps,
        enabled,
        created_at,
        updated_at,
    ) = record
    return {
        "id": row_id,
        "name": name,
        "description": description,
        "trigger_config": trigger_config if isinstance(trigger_config, dict) else {},
        "steps": steps if isinstance(steps, list) else [],
        "enabled": enabled,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _execution_row_to_dict(record: tuple[Any, ...]) -> dict[str, Any]:
    (
        row_id,
        playbook_id,
        alert_id,
        incident_id,
        status,
        started_at,
        completed_at,
        last_completed_step,
        steps_log,
        created_at,
    ) = record
    return {
        "id": row_id,
        "playbook_id": playbook_id,
        "alert_id": alert_id,
        "incident_id": incident_id,
        "status": status,
        "started_at": started_at,
        "completed_at": completed_at,
        "last_completed_step": last_completed_step,
        "steps_log": steps_log if isinstance(steps_log, list) else [],
        "created_at": created_at,
    }


def update_playbook_definition(
    conn,
    playbook_id: str,
    *,
    name: str,
    description: str | None,
    trigger_config: dict,
    steps: list[dict],
    enabled: bool,
) -> dict[str, Any] | None:
    """
    Update editable fields for an existing definition. Returns None if id is unknown.

    Validates steps via the registry. Does not touch playbook_executions. Caller commits.
    """
    if not isinstance(trigger_config, dict):
        raise ValueError("trigger_config must be a dict")
    step_errors = validate_playbook_steps(steps)
    if step_errors:
        raise ValueError("; ".join(step_errors))

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE playbook_definitions
            SET name = %s,
                description = %s,
                trigger_config = %s,
                steps = %s,
                enabled = %s,
                updated_at = NOW()
            WHERE id = %s
            RETURNING id, name, description, trigger_config, steps, enabled,
                      created_at, updated_at
            """,
            (
                name,
                description,
                Json(trigger_config),
                Json(steps),
                enabled,
                playbook_id,
            ),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return _definition_row_to_dict(row)


def set_playbook_definition_enabled(
    conn,
    playbook_id: str,
    enabled: bool,
) -> dict[str, Any] | None:
    """Set enabled flag only. Returns None if id is unknown. Caller commits."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE playbook_definitions
            SET enabled = %s,
                updated_at = NOW()
            WHERE id = %s
            RETURNING id, name, description, trigger_config, steps, enabled,
                      created_at, updated_at
            """,
            (enabled, playbook_id),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return _definition_row_to_dict(row)


def create_playbook_definition(
    conn,
    playbook_id: str,
    name: str,
    *,
    steps: list[dict],
    trigger_config: dict | None = None,
    enabled: bool = True,
    description: str | None = None,
) -> dict[str, Any]:
    """
    Insert a playbook definition after validating step action names via the registry.

    Raises ValueError if steps fail validation.
    """
    trigger_config = trigger_config if trigger_config is not None else {}
    if not isinstance(trigger_config, dict):
        raise ValueError("trigger_config must be a dict")

    step_errors = validate_playbook_steps(steps)
    if step_errors:
        raise ValueError("; ".join(step_errors))

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO playbook_definitions (
                id, name, description, trigger_config, steps, enabled
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, name, description, trigger_config, steps, enabled,
                      created_at, updated_at
            """,
            (
                playbook_id,
                name,
                description,
                Json(trigger_config),
                Json(steps),
                enabled,
            ),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("INSERT playbook_definitions returned no row")
        return _definition_row_to_dict(row)


def list_enabled_playbook_definitions(conn) -> list[dict[str, Any]]:
    """Return enabled definitions ordered by id ASC."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, description, trigger_config, steps, enabled,
                   created_at, updated_at
            FROM playbook_definitions
            WHERE enabled = TRUE
            ORDER BY id ASC
            """
        )
        return [_definition_row_to_dict(row) for row in cur.fetchall()]


def get_playbook_definition(conn, playbook_id: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, description, trigger_config, steps, enabled,
                   created_at, updated_at
            FROM playbook_definitions
            WHERE id = %s
            """,
            (playbook_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return _definition_row_to_dict(row)


def create_playbook_execution(
    conn,
    playbook_id: str,
    alert_id: int | None,
    incident_id: int | None = None,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO playbook_executions (
                playbook_id, alert_id, incident_id, status
            )
            VALUES (%s, %s, %s, 'pending')
            RETURNING id
            """,
            (playbook_id, alert_id, incident_id),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("INSERT playbook_executions returned no row")
        return int(row[0])


def create_pending_playbook_execution_once(
    conn,
    playbook_id: str,
    alert_id: int,
    incident_id: int | None = None,
) -> int | None:
    """
    Insert one pending execution for a playbook/alert pair.

    Returns the new execution id, or None when the pair already exists. Caller commits.
    """
    if alert_id is None:
        raise ValueError("alert_id is required")

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO playbook_executions (
                playbook_id, alert_id, incident_id, status
            )
            VALUES (%s, %s, %s, 'pending')
            ON CONFLICT (playbook_id, alert_id)
                WHERE alert_id IS NOT NULL
                DO NOTHING
            RETURNING id
            """,
            (playbook_id, alert_id, incident_id),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return int(row[0])


def get_playbook_execution(conn, execution_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, playbook_id, alert_id, incident_id, status,
                   started_at, completed_at, last_completed_step, steps_log, created_at
            FROM playbook_executions
            WHERE id = %s
            """,
            (execution_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return _execution_row_to_dict(row)


def list_pending_playbook_executions(conn, limit: int = 10) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, playbook_id, alert_id, incident_id, status,
                   started_at, completed_at, last_completed_step, steps_log, created_at
            FROM playbook_executions
            WHERE status = 'pending'
            ORDER BY created_at ASC, id ASC
            LIMIT %s
            """,
            (limit,),
        )
        return [_execution_row_to_dict(row) for row in cur.fetchall()]


def claim_next_pending_playbook_execution(conn, now: datetime | None = None) -> dict[str, Any] | None:
    if now is None:
        now = datetime.utcnow()

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM playbook_executions
            WHERE status = 'pending'
            ORDER BY created_at ASC, id ASC
            LIMIT 1
            FOR UPDATE SKIP LOCKED
            """
        )
        row = cur.fetchone()
        if row is None:
            return None

        execution_id = int(row[0])
        cur.execute(
            """
            UPDATE playbook_executions
            SET status = 'running',
                started_at = COALESCE(started_at, %s)
            WHERE id = %s
            RETURNING id, playbook_id, alert_id, incident_id, status,
                      started_at, completed_at, last_completed_step, steps_log, created_at
            """,
            (now, execution_id),
        )
        updated = cur.fetchone()
        if updated is None:
            return None
        return _execution_row_to_dict(updated)


def set_playbook_execution_running(
    conn,
    execution_id: int,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    if now is None:
        now = datetime.utcnow()

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE playbook_executions
            SET status = 'running',
                started_at = COALESCE(started_at, %s)
            WHERE id = %s
              AND status = 'pending'
            RETURNING id, playbook_id, alert_id, incident_id, status,
                      started_at, completed_at, last_completed_step, steps_log, created_at
            """,
            (now, execution_id),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return _execution_row_to_dict(row)


def update_playbook_execution_step_log(
    conn,
    execution_id: int,
    steps_log: list[dict],
    last_completed_step: int | None = None,
) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE playbook_executions
            SET steps_log = %s,
                last_completed_step = %s
            WHERE id = %s
            RETURNING id, playbook_id, alert_id, incident_id, status,
                      started_at, completed_at, last_completed_step, steps_log, created_at
            """,
            (Json(steps_log), last_completed_step, execution_id),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return _execution_row_to_dict(row)


def set_playbook_execution_success(
    conn,
    execution_id: int,
    steps_log: list[dict],
    last_completed_step: int | None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    if now is None:
        now = datetime.utcnow()

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE playbook_executions
            SET status = 'success',
                completed_at = %s,
                steps_log = %s,
                last_completed_step = %s
            WHERE id = %s
            RETURNING id, playbook_id, alert_id, incident_id, status,
                      started_at, completed_at, last_completed_step, steps_log, created_at
            """,
            (now, Json(steps_log), last_completed_step, execution_id),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return _execution_row_to_dict(row)


def set_playbook_execution_failed(
    conn,
    execution_id: int,
    steps_log: list[dict],
    last_completed_step: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    if now is None:
        now = datetime.utcnow()

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE playbook_executions
            SET status = 'failed',
                completed_at = %s,
                steps_log = %s,
                last_completed_step = %s
            WHERE id = %s
            RETURNING id, playbook_id, alert_id, incident_id, status,
                      started_at, completed_at, last_completed_step, steps_log, created_at
            """,
            (now, Json(steps_log), last_completed_step, execution_id),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return _execution_row_to_dict(row)


def update_execution_status(
    conn,
    execution_id: int,
    status: str,
    now: datetime | None = None,
) -> None:
    if status not in _VALID_EXECUTION_STATUSES:
        raise ValueError(
            f"invalid execution status {status!r}; "
            f"must be one of {sorted(_VALID_EXECUTION_STATUSES)}"
        )

    if now is None:
        now = datetime.utcnow()

    if status == "running":
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE playbook_executions
                SET status = %s,
                    started_at = COALESCE(started_at, %s)
                WHERE id = %s
                """,
                (status, now, execution_id),
            )
        return

    if status in _TERMINAL_EXECUTION_STATUSES:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE playbook_executions
                SET status = %s,
                    completed_at = %s
                WHERE id = %s
                """,
                (status, now, execution_id),
            )
        return

    # pending — only status column (no automatic timestamp side effects)
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE playbook_executions
            SET status = %s
            WHERE id = %s
            """,
            (status, execution_id),
        )


def list_playbook_executions(
    conn,
    playbook_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    if playbook_id is not None:
        clauses.append("playbook_id = %s")
        params.append(playbook_id)
    if status is not None:
        clauses.append("status = %s")
        params.append(status)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, playbook_id, alert_id, incident_id, status,
                   started_at, completed_at, last_completed_step, steps_log, created_at
            FROM playbook_executions
            {where_sql}
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (*params, limit),
        )
        return [_execution_row_to_dict(row) for row in cur.fetchall()]
