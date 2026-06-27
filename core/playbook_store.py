"""
DB helpers for playbook_definitions and playbook_executions.

Callers own transaction boundaries (commit/rollback). Execution wiring from ingest
or workers is intentionally out of scope.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg2
from psycopg2.extras import Json

from engines.playbook_registry import validate_playbook_steps

logger = logging.getLogger(__name__)

# Conservative default for max_attempts on new execution rows (metadata only in this slice).
# spec: SPEC-PLAYBOOK-003
DEFAULT_PLAYBOOK_EXECUTION_MAX_ATTEMPTS = 3

_EXECUTION_COLUMNS_SQL = (
    "id, playbook_id, alert_id, incident_id, status, "
    "started_at, completed_at, last_completed_step, steps_log, created_at, "
    "attempt_count, max_attempts, last_attempted_at, failure_reason, stale_after, timeout_seconds, "
    "lease_owner, lease_acquired_at, lease_heartbeat_at, lease_expires_at, recovery_count, "
    "decision_id, soar_correlation_id"
)
_SCHEDULE_COLUMNS_SQL = (
    "id, playbook_id, schedule_expression, timezone, enabled, paused, "
    "next_run_at, last_run_at, last_success_at, last_failure_at, "
    "last_scheduled_execution_id, missed_run_policy, max_catchup_runs, "
    "max_concurrent_runs, created_at, updated_at"
)


class _UnsetType:
    __slots__ = ()


_UNSET = _UnsetType()

_TERMINAL_EXECUTION_STATUSES = frozenset(
    {"success", "failed", "abandoned", "permanently_failed"}
)
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

_PERMANENT_FAIL_ELIGIBLE_STATUSES = frozenset({"running", "failed", "awaiting_approval"})
_VALID_MISSED_RUN_POLICIES = frozenset({"skip", "record_only", "run_once"})


def _utc_naive(dt: datetime) -> datetime:
    """Normalize for elapsed-time comparisons against mixed naive/aware datetimes."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def playbook_execution_row_is_stale_running(row: dict[str, Any], *, now: datetime | None = None) -> bool:
    """
    True when status is running, reliability metadata defines a threshold, and the run
    has been active at least that long since last_attempted_at or started_at.

    If stale_after and timeout_seconds are both NULL, or reference timestamps are missing,
    returns False (no automatic inference — operators set metadata first).
    """
    if row.get("status") != "running":
        return False
    threshold = row.get("stale_after")
    if threshold is None:
        threshold = row.get("timeout_seconds")
    if threshold is None:
        return False
    ref = row.get("last_attempted_at") or row.get("started_at")
    if ref is None:
        return False
    when = now if now is not None else _utc_now()
    elapsed = (_utc_naive(when) - _utc_naive(ref)).total_seconds()
    return elapsed >= int(threshold)


def playbook_execution_is_stale_running(
    conn, execution_id: int, *, now: datetime | None = None
) -> bool:
    """Convenience wrapper; False when the execution is missing or not stale-running."""
    row = get_playbook_execution(conn, execution_id)
    if row is None:
        return False
    return playbook_execution_row_is_stale_running(row, now=now)


def list_stale_running_playbook_execution_ids(
    conn, *, now: datetime | None = None
) -> list[int]:
    """Return ids of running executions that are stale per metadata (manual review only)."""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {_EXECUTION_COLUMNS_SQL}
            FROM playbook_executions
            WHERE status = 'running'
            ORDER BY id ASC
            """
        )
        rows = [_execution_row_to_dict(r) for r in cur.fetchall()]
    return [r["id"] for r in rows if playbook_execution_row_is_stale_running(r, now=now)]


def _lease_is_active(lease_expires_at: datetime | None, *, now: datetime) -> bool:
    if lease_expires_at is None:
        return False
    return _utc_naive(lease_expires_at) > _utc_naive(now)


def _lease_owner_sql(lease_owner: str | None) -> tuple[str, list[Any]]:
    owner = (lease_owner or "").strip()
    if not owner:
        return "", []
    return " AND lease_owner = %s", [owner]


def acquire_execution_lease(
    conn,
    execution_id: int,
    lease_owner: str,
    *,
    lease_duration_seconds: int = 60,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """
    Claim a pending execution with worker lease metadata and transition to running.

    Transaction-safe: row is locked with FOR UPDATE before the lease is written.
    Returns None when the execution is missing, not pending, or held by a non-expired lease.
    Caller commits.
    """
    # spec: openspec/changes/add-soar-execution-locking-stale-recovery/
    owner = (lease_owner or "").strip()
    if not owner:
        raise ValueError("lease_owner is required")
    if lease_duration_seconds < 1:
        raise ValueError("lease_duration_seconds must be at least 1")

    if now is None:
        now = _utc_now()
    expires_at = now + timedelta(seconds=lease_duration_seconds)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT status, lease_expires_at
            FROM playbook_executions
            WHERE id = %s
            FOR UPDATE
            """,
            (execution_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        status, lease_expires_at = row
        if status != "pending":
            return None
        if _lease_is_active(lease_expires_at, now=now):
            return None

        cur.execute(
            f"""
            UPDATE playbook_executions
            SET status = 'running',
                started_at = COALESCE(started_at, %s),
                lease_owner = %s,
                lease_acquired_at = %s,
                lease_heartbeat_at = %s,
                lease_expires_at = %s
            WHERE id = %s
              AND status = 'pending'
            RETURNING {_EXECUTION_COLUMNS_SQL}
            """,
            (now, owner, now, now, expires_at, execution_id),
        )
        updated = cur.fetchone()
        if updated is None:
            logger.info(
                "playbook lease acquire skipped execution_id=%s worker_id=%s reason=update_race",
                execution_id,
                owner,
            )
            return None
        logger.info(
            "playbook lease acquired execution_id=%s worker_id=%s expires_at=%s",
            execution_id,
            owner,
            expires_at,
        )
        return _execution_row_to_dict(updated)


def claim_next_pending_playbook_execution_with_lease(
    conn,
    lease_owner: str,
    *,
    lease_duration_seconds: int = 60,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """
    Atomically select the next pending execution (SKIP LOCKED) and acquire its lease.

    Returns None when the queue is empty or the row cannot be leased. Caller commits.
    """
    owner = (lease_owner or "").strip()
    if not owner:
        raise ValueError("lease_owner is required")
    if lease_duration_seconds < 1:
        raise ValueError("lease_duration_seconds must be at least 1")
    if now is None:
        now = _utc_now()
    expires_at = now + timedelta(seconds=lease_duration_seconds)

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
            SELECT status, lease_expires_at
            FROM playbook_executions
            WHERE id = %s
            FOR UPDATE
            """,
            (execution_id,),
        )
        locked = cur.fetchone()
        if locked is None:
            return None
        status, lease_expires_at = locked
        if status != "pending":
            return None
        if _lease_is_active(lease_expires_at, now=now):
            return None

        cur.execute(
            f"""
            UPDATE playbook_executions
            SET status = 'running',
                started_at = COALESCE(started_at, %s),
                lease_owner = %s,
                lease_acquired_at = %s,
                lease_heartbeat_at = %s,
                lease_expires_at = %s
            WHERE id = %s
              AND status = 'pending'
            RETURNING {_EXECUTION_COLUMNS_SQL}
            """,
            (now, owner, now, now, expires_at, execution_id),
        )
        updated = cur.fetchone()
        if updated is None:
            logger.info(
                "playbook lease claim skipped execution_id=%s worker_id=%s reason=update_race",
                execution_id,
                owner,
            )
            return None
        logger.info(
            "playbook lease claimed execution_id=%s worker_id=%s expires_at=%s",
            execution_id,
            owner,
            expires_at,
        )
        return _execution_row_to_dict(updated)


def acquire_awaiting_approval_resume_lease(
    conn,
    execution_id: int,
    lease_owner: str,
    steps_log: list[dict],
    last_completed_step: int | None,
    *,
    lease_duration_seconds: int = 60,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """
    Resume an approved awaiting_approval execution under a new worker lease.

    Transaction-safe row lock; returns None when not awaiting_approval or lease is held.
    Caller commits.
    """
    owner = (lease_owner or "").strip()
    if not owner:
        raise ValueError("lease_owner is required")
    if lease_duration_seconds < 1:
        raise ValueError("lease_duration_seconds must be at least 1")
    if now is None:
        now = _utc_now()
    expires_at = now + timedelta(seconds=lease_duration_seconds)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT status, lease_expires_at
            FROM playbook_executions
            WHERE id = %s
            FOR UPDATE
            """,
            (execution_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        status, lease_expires_at = row
        if status != "awaiting_approval":
            return None
        if _lease_is_active(lease_expires_at, now=now):
            return None

        cur.execute(
            f"""
            UPDATE playbook_executions
            SET status = 'running',
                started_at = COALESCE(started_at, %s),
                completed_at = NULL,
                steps_log = %s,
                last_completed_step = %s,
                lease_owner = %s,
                lease_acquired_at = %s,
                lease_heartbeat_at = %s,
                lease_expires_at = %s
            WHERE id = %s
              AND status = 'awaiting_approval'
            RETURNING {_EXECUTION_COLUMNS_SQL}
            """,
            (
                now,
                Json(steps_log),
                last_completed_step,
                owner,
                now,
                now,
                expires_at,
                execution_id,
            ),
        )
        updated = cur.fetchone()
        if updated is None:
            logger.info(
                "playbook approval resume lease skipped execution_id=%s worker_id=%s reason=update_race",
                execution_id,
                owner,
            )
            return None
        logger.info(
            "playbook approval resume lease acquired execution_id=%s worker_id=%s expires_at=%s",
            execution_id,
            owner,
            expires_at,
        )
        return _execution_row_to_dict(updated)


def heartbeat_execution_lease(
    conn,
    execution_id: int,
    lease_owner: str,
    *,
    lease_duration_seconds: int = 60,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Extend an active running lease for the matching owner. Caller commits."""
    owner = (lease_owner or "").strip()
    if not owner:
        raise ValueError("lease_owner is required")
    if lease_duration_seconds < 1:
        raise ValueError("lease_duration_seconds must be at least 1")

    if now is None:
        now = _utc_now()
    expires_at = now + timedelta(seconds=lease_duration_seconds)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE playbook_executions
            SET lease_heartbeat_at = %s,
                lease_expires_at = %s
            WHERE id = %s
              AND status = 'running'
              AND lease_owner = %s
              AND lease_expires_at IS NOT NULL
              AND lease_expires_at > %s
            RETURNING {_EXECUTION_COLUMNS_SQL}
            """,
            (now, expires_at, execution_id, owner, now),
        )
        row = cur.fetchone()
        if row is None:
            logger.info(
                "playbook lease heartbeat skipped execution_id=%s worker_id=%s reason=lease_not_active",
                execution_id,
                owner,
            )
            return None
        logger.debug(
            "playbook lease heartbeat execution_id=%s worker_id=%s expires_at=%s",
            execution_id,
            owner,
            expires_at,
        )
        return _execution_row_to_dict(row)


def release_execution_lease(
    conn,
    execution_id: int,
    lease_owner: str,
) -> dict[str, Any] | None:
    """Clear lease fields for a matching owner. Caller commits."""
    owner = (lease_owner or "").strip()
    if not owner:
        raise ValueError("lease_owner is required")

    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE playbook_executions
            SET lease_owner = NULL,
                lease_acquired_at = NULL,
                lease_heartbeat_at = NULL,
                lease_expires_at = NULL
            WHERE id = %s
              AND lease_owner = %s
            RETURNING {_EXECUTION_COLUMNS_SQL}
            """,
            (execution_id, owner),
        )
        row = cur.fetchone()
        if row is None:
            logger.info(
                "playbook lease release skipped execution_id=%s worker_id=%s reason=owner_mismatch",
                execution_id,
                owner,
            )
            return None
        logger.info(
            "playbook lease released execution_id=%s worker_id=%s",
            execution_id,
            owner,
        )
        return _execution_row_to_dict(row)


def list_stale_running_executions(
    conn,
    *,
    now: datetime | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    Running executions with an expired lease. Excludes awaiting_approval and other statuses.
    Caller commits not required for read-only use.
    """
    if limit < 0:
        raise ValueError("limit must be non-negative")
    if now is None:
        now = _utc_now()

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {_EXECUTION_COLUMNS_SQL}
            FROM playbook_executions
            WHERE status = 'running'
              AND lease_expires_at IS NOT NULL
              AND lease_expires_at <= %s
            ORDER BY lease_expires_at ASC, id ASC
            LIMIT %s
            FOR UPDATE SKIP LOCKED
            """,
            (now, limit),
        )
        return [_execution_row_to_dict(row) for row in cur.fetchall()]


def mark_stale_execution_for_recovery(
    conn,
    execution_id: int,
    *,
    now: datetime | None = None,
    failure_reason: str | None = None,
) -> dict[str, Any] | None:
    """
    Recover a stale running execution with an expired lease.

    Requeues to pending when attempts remain; otherwise marks failed. Never recovers
    awaiting_approval or non-expired leases. Increments recovery_count. Caller commits.
    """
    if now is None:
        now = _utc_now()

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {_EXECUTION_COLUMNS_SQL}
            FROM playbook_executions
            WHERE id = %s
            FOR UPDATE
            """,
            (execution_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        current = _execution_row_to_dict(row)
        if current["status"] != "running":
            return None
        if current["lease_expires_at"] is None:
            return None
        if _utc_naive(current["lease_expires_at"]) > _utc_naive(now):
            return None

        attempt_count = int(current["attempt_count"])
        max_attempts = int(current["max_attempts"])
        if attempt_count < max_attempts:
            new_status = "pending"
            reason = failure_reason or "stale lease recovered for retry"
            completed_at = None
        else:
            new_status = "failed"
            reason = failure_reason or "stale lease exceeded max attempts"
            completed_at = now

        cur.execute(
            f"""
            UPDATE playbook_executions
            SET status = %s,
                completed_at = %s,
                failure_reason = %s,
                recovery_count = recovery_count + 1,
                lease_owner = NULL,
                lease_acquired_at = NULL,
                lease_heartbeat_at = NULL,
                lease_expires_at = NULL
            WHERE id = %s
              AND status = 'running'
              AND lease_expires_at IS NOT NULL
              AND lease_expires_at <= %s
            RETURNING {_EXECUTION_COLUMNS_SQL}
            """,
            (new_status, completed_at, reason, execution_id, now),
        )
        updated = cur.fetchone()
        if updated is None:
            logger.info(
                "playbook stale recovery skipped execution_id=%s reason=update_race",
                execution_id,
            )
            return None
        recovered = _execution_row_to_dict(updated)
        logger.info(
            "playbook stale recovery applied execution_id=%s new_status=%s recovery_count=%s",
            execution_id,
            recovered["status"],
            recovered["recovery_count"],
        )
        return recovered


def count_expired_awaiting_approval_leases(
    conn,
    *,
    now: datetime | None = None,
) -> int:
    """Diagnostic count only; awaiting_approval is never recovered as stale-running."""
    if now is None:
        now = _utc_now()

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM playbook_executions
            WHERE status = 'awaiting_approval'
              AND lease_expires_at IS NOT NULL
              AND lease_expires_at <= %s
            """,
            (now,),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0


def mark_playbook_execution_permanently_failed(
    conn,
    execution_id: int,
    *,
    failure_reason: str,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """
    Operator dead-letter: transition running, failed, or awaiting_approval to permanently_failed.

    Idempotent: if already permanently_failed, returns the current row unchanged.
    Rejects success, abandoned, and pending. Caller commits. Does not call the executor.
    """
    if now is None:
        now = _utc_now()

    current = get_playbook_execution(conn, execution_id)
    if current is None:
        return None
    if current["status"] == "permanently_failed":
        return current

    reason = (failure_reason or "").strip()
    if not reason:
        raise ValueError("failure_reason is required")

    if current["status"] in {"success", "abandoned"}:
        raise ValueError(
            f"cannot mark execution as permanently_failed from terminal status "
            f"{current['status']!r}"
        )
    if current["status"] not in _PERMANENT_FAIL_ELIGIBLE_STATUSES:
        raise ValueError(
            "permanently_failed is only allowed from running, failed, or awaiting_approval; "
            f"current status: {current['status']!r}"
        )

    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE playbook_executions
            SET status = 'permanently_failed',
                completed_at = %s,
                failure_reason = %s
            WHERE id = %s
              AND status IN ('running', 'failed', 'awaiting_approval')
            RETURNING {_EXECUTION_COLUMNS_SQL}
            """,
            (now, reason, execution_id),
        )
        row = cur.fetchone()
        if row is None:
            return get_playbook_execution(conn, execution_id)
        return _execution_row_to_dict(row)


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
        lease_owner,
        lease_acquired_at,
        lease_heartbeat_at,
        lease_expires_at,
        recovery_count,
        decision_id,
        soar_correlation_id,
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
        "lease_owner": lease_owner,
        "lease_acquired_at": lease_acquired_at,
        "lease_heartbeat_at": lease_heartbeat_at,
        "lease_expires_at": lease_expires_at,
        "recovery_count": recovery_count,
        "decision_id": decision_id,
        "soar_correlation_id": soar_correlation_id,
    }


def _schedule_row_to_dict(record: tuple[Any, ...]) -> dict[str, Any]:
    (
        row_id,
        playbook_id,
        schedule_expression,
        timezone_name,
        enabled,
        paused,
        next_run_at,
        last_run_at,
        last_success_at,
        last_failure_at,
        last_scheduled_execution_id,
        missed_run_policy,
        max_catchup_runs,
        max_concurrent_runs,
        created_at,
        updated_at,
    ) = record
    return {
        "id": row_id,
        "playbook_id": playbook_id,
        "schedule_expression": schedule_expression,
        "timezone": timezone_name,
        "enabled": enabled,
        "paused": paused,
        "next_run_at": next_run_at,
        "last_run_at": last_run_at,
        "last_success_at": last_success_at,
        "last_failure_at": last_failure_at,
        "last_scheduled_execution_id": last_scheduled_execution_id,
        "missed_run_policy": missed_run_policy,
        "max_catchup_runs": max_catchup_runs,
        "max_concurrent_runs": max_concurrent_runs,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _validate_schedule_metadata(
    *,
    schedule_expression: str,
    timezone_name: str,
    missed_run_policy: str,
    max_catchup_runs: int,
    max_concurrent_runs: int,
) -> None:
    if not isinstance(schedule_expression, str) or not schedule_expression.strip():
        raise ValueError("schedule_expression is required")
    if not isinstance(timezone_name, str) or not timezone_name.strip():
        raise ValueError("timezone is required")
    if missed_run_policy not in _VALID_MISSED_RUN_POLICIES:
        raise ValueError("invalid missed_run_policy")
    if max_catchup_runs < 0:
        raise ValueError("max_catchup_runs must be non-negative")
    if max_concurrent_runs < 1:
        raise ValueError("max_concurrent_runs must be at least 1")


def create_playbook_schedule(
    conn,
    playbook_id: str,
    *,
    schedule_expression: str,
    timezone_name: str = "UTC",
    enabled: bool = False,
    paused: bool = False,
    next_run_at: datetime | None = None,
    missed_run_policy: str = "skip",
    max_catchup_runs: int = 0,
    max_concurrent_runs: int = 1,
) -> dict[str, Any]:
    """
    Create scheduled-playbook metadata only. Does not execute or enqueue anything.

    Caller owns commit/rollback.
    """
    _validate_schedule_metadata(
        schedule_expression=schedule_expression,
        timezone_name=timezone_name,
        missed_run_policy=missed_run_policy,
        max_catchup_runs=max_catchup_runs,
        max_concurrent_runs=max_concurrent_runs,
    )

    with conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO playbook_schedules (
                playbook_id, schedule_expression, timezone, enabled, paused,
                next_run_at, missed_run_policy, max_catchup_runs, max_concurrent_runs
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING {_SCHEDULE_COLUMNS_SQL}
            """,
            (
                playbook_id,
                schedule_expression.strip(),
                timezone_name.strip(),
                enabled,
                paused,
                next_run_at,
                missed_run_policy,
                max_catchup_runs,
                max_concurrent_runs,
            ),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("INSERT playbook_schedules returned no row")
        return _schedule_row_to_dict(row)


def get_playbook_schedule(conn, schedule_id: int) -> dict[str, Any] | None:
    """Read scheduled-playbook metadata by id. Does not execute anything."""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {_SCHEDULE_COLUMNS_SQL}
            FROM playbook_schedules
            WHERE id = %s
            """,
            (schedule_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return _schedule_row_to_dict(row)


def list_playbook_schedules(
    conn,
    *,
    playbook_id: str | None = None,
    enabled: bool | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List scheduled-playbook metadata. Read-only; does not execute anything."""
    if limit < 0:
        raise ValueError("limit must be non-negative")

    clauses: list[str] = []
    params: list[Any] = []
    if playbook_id is not None:
        clauses.append("playbook_id = %s")
        params.append(playbook_id)
    if enabled is not None:
        clauses.append("enabled = %s")
        params.append(enabled)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {_SCHEDULE_COLUMNS_SQL}
            FROM playbook_schedules
            {where_sql}
            ORDER BY id ASC
            LIMIT %s
            """,
            tuple(params),
        )
        return [_schedule_row_to_dict(row) for row in cur.fetchall()]


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
    *,
    decision_id: int | None = None,
    soar_correlation_id: str | None = None,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO playbook_executions (
                playbook_id, alert_id, incident_id, status,
                decision_id, soar_correlation_id
            )
            VALUES (%s, %s, %s, 'pending', %s, %s)
            RETURNING id
            """,
            (playbook_id, alert_id, incident_id, decision_id, soar_correlation_id),
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
    *,
    decision_id: int | None = None,
    soar_correlation_id: str | None = None,
) -> int | None:
    """
    Insert one pending execution for a playbook/alert pair.

    Returns the new execution id, or None when the pair already exists. Caller commits.
    decision_id and soar_correlation_id are written when provided (Phase 5A linkage).
    """
    if alert_id is None:
        raise ValueError("alert_id is required")

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO playbook_executions (
                playbook_id, alert_id, incident_id, status,
                decision_id, soar_correlation_id
            )
            VALUES (%s, %s, %s, 'pending', %s, %s)
            ON CONFLICT (playbook_id, alert_id)
                WHERE alert_id IS NOT NULL
                  AND status IN ('pending', 'running', 'awaiting_approval')
                DO NOTHING
            RETURNING id
            """,
            (playbook_id, alert_id, incident_id, decision_id, soar_correlation_id),
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


def set_playbook_execution_canonical_linkage(
    conn,
    execution_id: int,
    decision_id: int,
    soar_correlation_id: str,
) -> dict[str, Any] | None:
    """Write decision_id and soar_correlation_id back to a playbook_executions row.

    Used after creating an execution-level canonical decision. Caller owns commit.
    """
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE playbook_executions
            SET decision_id = %s,
                soar_correlation_id = %s
            WHERE id = %s
            RETURNING {_EXECUTION_COLUMNS_SQL}
            """,
            (decision_id, soar_correlation_id, execution_id),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return _execution_row_to_dict(row)


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
    if current["status"] in {"success", "failed", "permanently_failed"}:
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
        now = _utc_now()

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
        now = _utc_now()

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
        now = _utc_now()

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
    *,
    lease_owner: str | None = None,
) -> dict[str, Any] | None:
    lease_sql, lease_params = _lease_owner_sql(lease_owner)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE playbook_executions
            SET steps_log = %s,
                last_completed_step = %s
            WHERE id = %s
            {lease_sql}
            RETURNING {_EXECUTION_COLUMNS_SQL}
            """,
            (Json(steps_log), last_completed_step, execution_id, *lease_params),
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
    *,
    lease_owner: str | None = None,
) -> dict[str, Any] | None:
    if now is None:
        now = _utc_now()

    lease_sql, lease_params = _lease_owner_sql(lease_owner)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE playbook_executions
            SET status = 'success',
                completed_at = %s,
                steps_log = %s,
                last_completed_step = %s
            WHERE id = %s
            {lease_sql}
            RETURNING {_EXECUTION_COLUMNS_SQL}
            """,
            (now, Json(steps_log), last_completed_step, execution_id, *lease_params),
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
    *,
    lease_owner: str | None = None,
) -> dict[str, Any] | None:
    if now is None:
        now = _utc_now()

    lease_sql, lease_params = _lease_owner_sql(lease_owner)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE playbook_executions
            SET status = 'failed',
                completed_at = %s,
                steps_log = %s,
                last_completed_step = %s
            WHERE id = %s
            {lease_sql}
            RETURNING {_EXECUTION_COLUMNS_SQL}
            """,
            (now, Json(steps_log), last_completed_step, execution_id, *lease_params),
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
    *,
    lease_owner: str | None = None,
) -> dict[str, Any] | None:
    lease_sql, lease_params = _lease_owner_sql(lease_owner)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE playbook_executions
            SET status = 'awaiting_approval',
                completed_at = NULL,
                steps_log = %s,
                last_completed_step = %s
            WHERE id = %s
            {lease_sql}
            RETURNING {_EXECUTION_COLUMNS_SQL}
            """,
            (Json(steps_log), last_completed_step, execution_id, *lease_params),
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
        now = _utc_now()

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
