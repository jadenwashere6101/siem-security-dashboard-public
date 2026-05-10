"""
DB helpers for playbook_definitions and playbook_executions.

Callers own transaction boundaries (commit/rollback). Execution wiring from ingest
or workers is intentionally out of scope.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import psycopg2
from psycopg2.extras import Json

from engines.playbook_registry import validate_playbook_steps

logger = logging.getLogger(__name__)

# Conservative default for max_attempts on new execution rows (metadata only in this slice).
DEFAULT_PLAYBOOK_EXECUTION_MAX_ATTEMPTS = 3

_EXECUTION_COLUMNS_SQL = (
    "id, playbook_id, alert_id, incident_id, status, "
    "started_at, completed_at, last_completed_step, steps_log, created_at, "
    "attempt_count, max_attempts, last_attempted_at, failure_reason, stale_after, timeout_seconds"
)


class _UnsetType:
    __slots__ = ()


_UNSET = _UnsetType()

_TERMINAL_EXECUTION_STATUSES = frozenset({"success", "failed", "abandoned"})
_VALID_EXECUTION_STATUSES = frozenset(
    {"pending", "running", "awaiting_approval", "success", "failed", "abandoned"}
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
        attempt_count,
        max_attempts,
        last_attempted_at,
        failure_reason,
        stale_after,
        timeout_seconds,
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
        "attempt_count": attempt_count,
        "max_attempts": max_attempts,
        "last_attempted_at": last_attempted_at,
        "failure_reason": failure_reason,
        "stale_after": stale_after,
        "timeout_seconds": timeout_seconds,
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
                  AND status IN ('pending', 'running', 'awaiting_approval')
                DO NOTHING
            RETURNING id
            """,
            (playbook_id, alert_id, incident_id),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return int(row[0])


def _active_execution_exists_for_pair(
    conn,
    playbook_id: str,
    alert_id: int | None,
    *,
    exclude_execution_id: int | None = None,
) -> bool:
    if alert_id is None:
        return False

    params: list[Any] = [playbook_id, alert_id]
    exclude_sql = ""
    if exclude_execution_id is not None:
        exclude_sql = "AND id <> %s"
        params.append(exclude_execution_id)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT 1
            FROM playbook_executions
            WHERE playbook_id = %s
              AND alert_id = %s
              AND status IN ('pending', 'running', 'awaiting_approval')
              {exclude_sql}
            LIMIT 1
            """,
            tuple(params),
        )
        return cur.fetchone() is not None


def active_playbook_execution_exists(
    conn,
    playbook_id: str,
    alert_id: int | None,
) -> bool:
    return _active_execution_exists_for_pair(conn, playbook_id, alert_id)


def create_retry_execution(conn, source_execution_id: int) -> int:
    source = get_playbook_execution(conn, source_execution_id)
    if source is None:
        raise ValueError("execution not found")
    if source["status"] not in {"failed", "abandoned"}:
        raise ValueError(
            "retry requires failed or abandoned execution; "
            f"current status: {source['status']}"
        )
    if _active_execution_exists_for_pair(
        conn,
        source["playbook_id"],
        source["alert_id"],
        exclude_execution_id=source_execution_id,
    ):
        raise ValueError("active execution already exists for playbook and alert")

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO playbook_executions (
                    playbook_id, alert_id, incident_id, status, steps_log, last_completed_step
                )
                VALUES (%s, %s, %s, 'pending', %s, NULL)
                RETURNING id
                """,
                (
                    source["playbook_id"],
                    source["alert_id"],
                    source["incident_id"],
                    Json([]),
                ),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("INSERT retry playbook_executions returned no row")
            return int(row[0])
    except psycopg2.IntegrityError as exc:
        raise ValueError("active execution already exists for playbook and alert") from exc


def abandon_playbook_execution(conn, execution_id: int) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE playbook_executions
            SET status = 'abandoned',
                completed_at = NOW()
            WHERE id = %s
              AND status IN ('pending', 'running', 'awaiting_approval')
            RETURNING status
            """,
            (execution_id,),
        )
        if cur.fetchone() is not None:
            return "ok"

    current = get_playbook_execution(conn, execution_id)
    if current is None:
        raise ValueError("execution not found")
    if current["status"] == "abandoned":
        return "no_op"
    if current["status"] in {"success", "failed"}:
        raise ValueError(
            f"cannot abandon terminal execution with status '{current['status']}'"
        )
    raise ValueError(f"cannot abandon execution with status '{current['status']}'")


def get_playbook_execution_reliability_metadata(
    conn, execution_id: int
) -> dict[str, Any] | None:
    """Return reliability fields only, or None if the execution id is unknown. Caller commits."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT attempt_count, max_attempts, last_attempted_at, failure_reason,
                   stale_after, timeout_seconds
            FROM playbook_executions
            WHERE id = %s
            """,
            (execution_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        (
            attempt_count,
            max_attempts,
            last_attempted_at,
            failure_reason,
            stale_after,
            timeout_seconds,
        ) = row
    return {
        "attempt_count": attempt_count,
        "max_attempts": max_attempts,
        "last_attempted_at": last_attempted_at,
        "failure_reason": failure_reason,
        "stale_after": stale_after,
        "timeout_seconds": timeout_seconds,
    }


def update_playbook_execution_reliability_metadata(
    conn,
    execution_id: int,
    *,
    attempt_count: int | _UnsetType = _UNSET,
    max_attempts: int | _UnsetType = _UNSET,
    last_attempted_at: datetime | None | _UnsetType = _UNSET,
    failure_reason: str | None | _UnsetType = _UNSET,
    stale_after: int | None | _UnsetType = _UNSET,
    timeout_seconds: int | None | _UnsetType = _UNSET,
) -> dict[str, Any] | None:
    """
    Update only the provided reliability columns. Omitted parameters are left unchanged.

    Pass None for nullable fields to set them to NULL. Does not commit.
    """
    assignments: list[str] = []
    params: list[Any] = []

    if attempt_count is not _UNSET:
        if attempt_count < 0:
            raise ValueError("attempt_count must be non-negative")
        assignments.append("attempt_count = %s")
        params.append(attempt_count)
    if max_attempts is not _UNSET:
        if max_attempts < 0:
            raise ValueError("max_attempts must be non-negative")
        assignments.append("max_attempts = %s")
        params.append(max_attempts)
    if last_attempted_at is not _UNSET:
        assignments.append("last_attempted_at = %s")
        params.append(last_attempted_at)
    if failure_reason is not _UNSET:
        assignments.append("failure_reason = %s")
        params.append(failure_reason)
    if stale_after is not _UNSET:
        if stale_after is not None and stale_after < 0:
            raise ValueError("stale_after must be non-negative when set")
        assignments.append("stale_after = %s")
        params.append(stale_after)
    if timeout_seconds is not _UNSET:
        if timeout_seconds is not None and timeout_seconds < 0:
            raise ValueError("timeout_seconds must be non-negative when set")
        assignments.append("timeout_seconds = %s")
        params.append(timeout_seconds)

    if not assignments:
        return get_playbook_execution(conn, execution_id)

    params.append(execution_id)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE playbook_executions
            SET {", ".join(assignments)}
            WHERE id = %s
            RETURNING {_EXECUTION_COLUMNS_SQL}
            """,
            tuple(params),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return _execution_row_to_dict(row)


def get_playbook_execution(conn, execution_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {_EXECUTION_COLUMNS_SQL}
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
            f"""
            SELECT {_EXECUTION_COLUMNS_SQL}
            FROM playbook_executions
            WHERE status = 'pending'
            ORDER BY created_at ASC, id ASC
            LIMIT %s
            """,
            (limit,),
        )
        return [_execution_row_to_dict(row) for row in cur.fetchall()]


def list_awaiting_approval_playbook_executions(conn, limit: int = 10) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {_EXECUTION_COLUMNS_SQL}
            FROM playbook_executions
            WHERE status = 'awaiting_approval'
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
            f"""
            UPDATE playbook_executions
            SET status = 'running',
                started_at = COALESCE(started_at, %s)
            WHERE id = %s
            RETURNING {_EXECUTION_COLUMNS_SQL}
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
            f"""
            UPDATE playbook_executions
            SET status = 'running',
                started_at = COALESCE(started_at, %s)
            WHERE id = %s
              AND status = 'pending'
            RETURNING {_EXECUTION_COLUMNS_SQL}
            """,
            (now, execution_id),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return _execution_row_to_dict(row)


def set_playbook_execution_resumed_running(
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
            f"""
            UPDATE playbook_executions
            SET status = 'running',
                started_at = COALESCE(started_at, %s),
                completed_at = NULL,
                steps_log = %s,
                last_completed_step = %s
            WHERE id = %s
              AND status = 'awaiting_approval'
            RETURNING {_EXECUTION_COLUMNS_SQL}
            """,
            (now, Json(steps_log), last_completed_step, execution_id),
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
            f"""
            UPDATE playbook_executions
            SET steps_log = %s,
                last_completed_step = %s
            WHERE id = %s
            RETURNING {_EXECUTION_COLUMNS_SQL}
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
            f"""
            UPDATE playbook_executions
            SET status = 'success',
                completed_at = %s,
                steps_log = %s,
                last_completed_step = %s
            WHERE id = %s
            RETURNING {_EXECUTION_COLUMNS_SQL}
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
            f"""
            UPDATE playbook_executions
            SET status = 'failed',
                completed_at = %s,
                steps_log = %s,
                last_completed_step = %s
            WHERE id = %s
            RETURNING {_EXECUTION_COLUMNS_SQL}
            """,
            (now, Json(steps_log), last_completed_step, execution_id),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return _execution_row_to_dict(row)


def set_playbook_execution_awaiting_approval(
    conn,
    execution_id: int,
    steps_log: list[dict],
    last_completed_step: int | None = None,
) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE playbook_executions
            SET status = 'awaiting_approval',
                completed_at = NULL,
                steps_log = %s,
                last_completed_step = %s
            WHERE id = %s
            RETURNING {_EXECUTION_COLUMNS_SQL}
            """,
            (Json(steps_log), last_completed_step, execution_id),
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

    # pending/awaiting_approval — only status column (no automatic terminal timestamp).
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
            SELECT {_EXECUTION_COLUMNS_SQL}
            FROM playbook_executions
            {where_sql}
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (*params, limit),
        )
        return [_execution_row_to_dict(row) for row in cur.fetchall()]
