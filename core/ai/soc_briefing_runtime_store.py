from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from psycopg2.extras import Json

from core.ai.config import AI_MODE_DISABLED, AiGatewayConfig, load_ai_gateway_config
from core.ai.models import AI_STATUS_DISABLED
from core.ai.soc_tools import ROLE_ANALYST, redact_sensitive_values, validate_tool_name
from core.worker_heartbeat_store import (
    SOC_BRIEFING_WORKER_NAME,
    get_worker_heartbeat,
    summarize_worker_health,
)

SERVICE_ACTOR = "scheduled_soc_briefing_worker"
SERVICE_ACTOR_ROLE = ROLE_ANALYST

JOB_STATUS_PENDING = "pending"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_SUCCESS = "success"
JOB_STATUS_FAILED = "failed"
JOB_STATUS_BLOCKED = "blocked"
JOB_STATUS_SKIPPED = "skipped"
JOB_STATUS_INTERRUPTED = "interrupted"

WINDOW_STATUS_PENDING = "pending"
WINDOW_STATUS_QUEUED = "queued"
WINDOW_STATUS_SUCCESS = "success"
WINDOW_STATUS_FAILED = "failed"
WINDOW_STATUS_BLOCKED = "blocked"
WINDOW_STATUS_SKIPPED = "skipped"

RUN_STATUS_RUNNING = "running"
RUN_STATUS_SUCCESS = "success"
RUN_STATUS_FAILED = "failed"
RUN_STATUS_BLOCKED = "blocked"
RUN_STATUS_INTERRUPTED = "interrupted"

STEP_STATUS_SUCCESS = "success"
STEP_STATUS_FAILED = "failed"
STEP_STATUS_BLOCKED = "blocked"
STEP_STATUS_SKIPPED = "skipped"
STEP_STATUS_INTERRUPTED = "interrupted"

DEFAULT_MAX_CATCH_UP_WINDOWS = 3
DEFAULT_MAX_LOOKBACK_HOURS = 24
DEFAULT_LEASE_DURATION_SECONDS = 120

MUTATION_ACTIONS = frozenset(
    {
        "approve",
        "deny",
        "execute",
        "retry",
        "resume",
        "abandon",
        "block",
        "unblock",
        "send_slack",
        "create_note",
        "mutate_incident",
        "shell",
        "file",
        "subprocess",
        "deploy",
    }
)


class SocBriefingRuntimeError(RuntimeError):
    pass


class SocBriefingPersistenceError(SocBriefingRuntimeError):
    pass


class SocBriefingScheduleError(SocBriefingRuntimeError):
    pass


class SocBriefingSecurityError(SocBriefingRuntimeError):
    pass


@dataclass(frozen=True)
class MaterializeResult:
    windows_created: int = 0
    jobs_created: int = 0
    duplicate_windows: int = 0
    skipped_windows: int = 0
    blocked_schedules: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "windows_created": self.windows_created,
            "jobs_created": self.jobs_created,
            "duplicate_windows": self.duplicate_windows,
            "skipped_windows": self.skipped_windows,
            "blocked_schedules": self.blocked_schedules,
        }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def idempotency_key(*parts: Any) -> str:
    raw = ":".join(str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


def _fetchone_dict(cur) -> dict[str, Any] | None:
    row = cur.fetchone()
    if row is None:
        return None
    columns = [desc[0] for desc in cur.description]
    return dict(zip(columns, row))


def _fetchall_dicts(cur) -> list[dict[str, Any]]:
    columns = [desc[0] for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def create_schedule(
    conn,
    *,
    name: str,
    next_due_at: datetime,
    cadence_minutes: int = 1440,
    enabled: bool = False,
    timezone_name: str = "UTC",
    catch_up_enabled: bool = True,
    max_catch_up_windows: int = DEFAULT_MAX_CATCH_UP_WINDOWS,
    max_lookback_hours: int = DEFAULT_MAX_LOOKBACK_HOURS,
    coalesce_missed_windows: bool = True,
    created_by: str | None = None,
) -> dict[str, Any]:
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO soc_briefing_schedules (
                    name, timezone, cadence_minutes, enabled, catch_up_enabled,
                    max_catch_up_windows, max_lookback_hours, coalesce_missed_windows,
                    next_due_at, created_by, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    name,
                    timezone_name,
                    cadence_minutes,
                    enabled,
                    catch_up_enabled,
                    max_catch_up_windows,
                    max_lookback_hours,
                    coalesce_missed_windows,
                    as_utc(next_due_at),
                    created_by,
                    utc_now(),
                ),
            )
            row = _fetchone_dict(cur)
    except Exception as error:
        raise SocBriefingPersistenceError("failed to create SOC briefing schedule") from error
    if row is None:
        raise SocBriefingPersistenceError("schedule insert returned no row")
    return row


def list_due_schedules(conn, *, now: datetime | None = None, limit: int = 50) -> list[dict[str, Any]]:
    current = as_utc(now) or utc_now()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM soc_briefing_schedules
            WHERE enabled = TRUE
              AND next_due_at IS NOT NULL
              AND next_due_at <= %s
            ORDER BY next_due_at ASC, id ASC
            LIMIT %s
            """,
            (current, max(1, min(int(limit), 200))),
        )
        return _fetchall_dicts(cur)


def validate_schedule(schedule: dict[str, Any]) -> None:
    if not schedule.get("enabled"):
        raise SocBriefingScheduleError("schedule is disabled")
    try:
        ZoneInfo(str(schedule.get("timezone") or "UTC"))
    except ZoneInfoNotFoundError as error:
        raise SocBriefingScheduleError("invalid timezone") from error
    cadence = int(schedule.get("cadence_minutes") or 0)
    if cadence <= 0 or cadence > 10080:
        raise SocBriefingScheduleError("invalid cadence")
    if int(schedule.get("max_catch_up_windows") or 0) < 0:
        raise SocBriefingScheduleError("invalid max_catch_up_windows")
    if int(schedule.get("max_lookback_hours") or 0) <= 0:
        raise SocBriefingScheduleError("invalid max_lookback_hours")
    if as_utc(schedule.get("next_due_at")) is None:
        raise SocBriefingScheduleError("next_due_at is required")


def mark_schedule_blocked(conn, schedule_id: int, *, failure_code: str, failure_message: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE soc_briefing_schedules
            SET status = 'blocked',
                failure_code = %s,
                failure_message = %s,
                updated_at = %s
            WHERE id = %s
            """,
            (failure_code, failure_message[:1000], utc_now(), schedule_id),
        )


def materialize_due_schedule(
    conn,
    schedule: dict[str, Any],
    *,
    now: datetime | None = None,
) -> MaterializeResult:
    current = as_utc(now) or utc_now()
    try:
        validate_schedule(schedule)
    except SocBriefingScheduleError as error:
        mark_schedule_blocked(
            conn,
            int(schedule["id"]),
            failure_code="malformed_schedule" if "disabled" not in str(error) else "disabled",
            failure_message=str(error),
        )
        return MaterializeResult(blocked_schedules=1)

    cadence = timedelta(minutes=int(schedule["cadence_minutes"]))
    next_due = as_utc(schedule["next_due_at"])
    if next_due is None or next_due > current:
        return MaterializeResult()

    max_catch_up = int(schedule.get("max_catch_up_windows") or DEFAULT_MAX_CATCH_UP_WINDOWS)
    max_lookback = timedelta(hours=int(schedule.get("max_lookback_hours") or DEFAULT_MAX_LOOKBACK_HOURS))
    catch_up_enabled = bool(schedule.get("catch_up_enabled"))
    coalesce = bool(schedule.get("coalesce_missed_windows"))
    earliest = current - max_lookback
    window_ends: list[datetime] = []
    cursor = next_due
    while cursor <= current and len(window_ends) <= max(max_catch_up, 1) + 500:
        if cursor >= earliest:
            window_ends.append(cursor)
        cursor += cadence

    skipped = 0
    runnable: list[tuple[datetime, datetime, bool]] = []
    if not catch_up_enabled and window_ends:
        runnable = [(window_ends[-1] - cadence, window_ends[-1], False)]
        skipped += max(0, len(window_ends) - 1)
    elif len(window_ends) > max_catch_up:
        if coalesce and max_catch_up > 0:
            selected = window_ends[-max_catch_up:]
            runnable = [(selected[0] - cadence, selected[-1], True)]
            skipped += max(0, len(window_ends) - len(selected))
        else:
            selected = window_ends[-max_catch_up:] if max_catch_up > 0 else []
            runnable = [(end - cadence, end, False) for end in selected]
            skipped += max(0, len(window_ends) - len(selected))
    else:
        runnable = [(end - cadence, end, False) for end in window_ends]

    if skipped:
        _create_skipped_window(
            conn,
            schedule_id=int(schedule["id"]),
            window_start=earliest,
            window_end=min(window_ends[0] if window_ends else current, current),
            reason="coalesced" if coalesce else "outside_lookback",
        )

    windows_created = 0
    jobs_created = 0
    duplicates = 0
    for window_start, window_end, coalesced in runnable:
        window, created = create_or_get_window(
            conn,
            schedule_id=int(schedule["id"]),
            window_start=window_start,
            window_end=window_end,
            status=WINDOW_STATUS_QUEUED,
            coalesced=coalesced,
        )
        if created:
            windows_created += 1
        else:
            duplicates += 1
        _job, job_created = create_or_get_job(conn, schedule_id=int(schedule["id"]), window_id=int(window["id"]))
        if job_created:
            jobs_created += 1

    next_due_after = cursor
    update_schedule_due_state(conn, int(schedule["id"]), next_due_at=next_due_after)
    return MaterializeResult(
        windows_created=windows_created,
        jobs_created=jobs_created,
        duplicate_windows=duplicates,
        skipped_windows=skipped,
    )


def create_or_get_window(
    conn,
    *,
    schedule_id: int,
    window_start: datetime,
    window_end: datetime,
    status: str = WINDOW_STATUS_PENDING,
    skip_reason: str | None = None,
    coalesced: bool = False,
) -> tuple[dict[str, Any], bool]:
    key = idempotency_key("soc-briefing-window", schedule_id, as_utc(window_start), as_utc(window_end))
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO soc_briefing_schedule_windows (
                schedule_id, window_start, window_end, idempotency_key,
                status, skip_reason, coalesced, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (schedule_id, window_start, window_end) DO NOTHING
            RETURNING *
            """,
            (schedule_id, as_utc(window_start), as_utc(window_end), key, status, skip_reason, coalesced, utc_now()),
        )
        row = _fetchone_dict(cur)
        if row is not None:
            return row, True
        cur.execute(
            """
            SELECT *
            FROM soc_briefing_schedule_windows
            WHERE schedule_id = %s AND window_start = %s AND window_end = %s
            """,
            (schedule_id, as_utc(window_start), as_utc(window_end)),
        )
        existing = _fetchone_dict(cur)
    if existing is None:
        raise SocBriefingPersistenceError("failed to fetch existing schedule window after conflict")
    return existing, False


def _create_skipped_window(
    conn,
    *,
    schedule_id: int,
    window_start: datetime,
    window_end: datetime,
    reason: str,
) -> None:
    if window_end <= window_start:
        window_end = window_start + timedelta(seconds=1)
    create_or_get_window(
        conn,
        schedule_id=schedule_id,
        window_start=window_start,
        window_end=window_end,
        status=WINDOW_STATUS_SKIPPED,
        skip_reason=reason,
        coalesced=True,
    )


def create_or_get_job(conn, *, schedule_id: int, window_id: int, max_attempts: int = 3) -> tuple[dict[str, Any], bool]:
    key = idempotency_key("soc-briefing-job", window_id)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO soc_briefing_jobs (
                schedule_id, window_id, idempotency_key, max_attempts, service_actor, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (window_id) DO NOTHING
            RETURNING *
            """,
            (schedule_id, window_id, key, max_attempts, SERVICE_ACTOR, utc_now()),
        )
        row = _fetchone_dict(cur)
        if row is not None:
            return row, True
        cur.execute("SELECT * FROM soc_briefing_jobs WHERE window_id = %s", (window_id,))
        existing = _fetchone_dict(cur)
    if existing is None:
        raise SocBriefingPersistenceError("failed to fetch existing SOC briefing job after conflict")
    return existing, False


def update_schedule_due_state(
    conn,
    schedule_id: int,
    *,
    next_due_at: datetime,
    last_successful_window_end: datetime | None = None,
) -> None:
    assignments = ["next_due_at = %s", "updated_at = %s", "status = 'active'", "failure_code = NULL", "failure_message = NULL"]
    params: list[Any] = [as_utc(next_due_at), utc_now()]
    if last_successful_window_end is not None:
        assignments.append("last_successful_window_end = %s")
        params.append(as_utc(last_successful_window_end))
    params.append(schedule_id)
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE soc_briefing_schedules SET {', '.join(assignments)} WHERE id = %s",
            params,
        )


def claim_next_job(
    conn,
    *,
    lease_owner: str,
    now: datetime | None = None,
    lease_duration_seconds: int = DEFAULT_LEASE_DURATION_SECONDS,
) -> dict[str, Any] | None:
    owner = str(lease_owner or "").strip()
    if not owner:
        raise ValueError("lease_owner is required")
    current = as_utc(now) or utc_now()
    expires = current + timedelta(seconds=max(1, int(lease_duration_seconds)))
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM soc_briefing_jobs
            WHERE status = 'pending'
              AND not_before <= %s
            ORDER BY priority ASC, created_at ASC, id ASC
            LIMIT 1
            FOR UPDATE SKIP LOCKED
            """,
            (current,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        job_id = int(row[0])
        cur.execute(
            """
            UPDATE soc_briefing_jobs
            SET status = 'running',
                attempt_count = attempt_count + 1,
                started_at = COALESCE(started_at, %s),
                lease_owner = %s,
                lease_acquired_at = %s,
                lease_heartbeat_at = %s,
                lease_expires_at = %s,
                updated_at = %s
            WHERE id = %s AND status = 'pending'
            RETURNING *
            """,
            (current, owner, current, current, expires, current, job_id),
        )
        return _fetchone_dict(cur)


def heartbeat_job_lease(
    conn,
    job_id: int,
    *,
    lease_owner: str,
    now: datetime | None = None,
    lease_duration_seconds: int = DEFAULT_LEASE_DURATION_SECONDS,
) -> dict[str, Any] | None:
    current = as_utc(now) or utc_now()
    expires = current + timedelta(seconds=max(1, int(lease_duration_seconds)))
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE soc_briefing_jobs
            SET lease_heartbeat_at = %s,
                lease_expires_at = %s,
                updated_at = %s
            WHERE id = %s
              AND status = 'running'
              AND lease_owner = %s
              AND lease_expires_at IS NOT NULL
              AND lease_expires_at > %s
            RETURNING *
            """,
            (current, expires, current, job_id, lease_owner, current),
        )
        return _fetchone_dict(cur)


def complete_job(
    conn,
    job_id: int,
    *,
    lease_owner: str,
    status: str,
    failure_code: str | None = None,
    failure_message: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    current = as_utc(now) or utc_now()
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE soc_briefing_jobs
            SET status = %s,
                completed_at = %s,
                failure_code = %s,
                failure_message = %s,
                lease_owner = NULL,
                lease_acquired_at = NULL,
                lease_heartbeat_at = NULL,
                lease_expires_at = NULL,
                updated_at = %s
            WHERE id = %s
              AND status = 'running'
              AND lease_owner = %s
            RETURNING *
            """,
            (status, current, failure_code, failure_message, current, job_id, lease_owner),
        )
        return _fetchone_dict(cur)


def recover_stale_jobs(conn, *, now: datetime | None = None, limit: int = 50) -> dict[str, int]:
    current = as_utc(now) or utc_now()
    recovered = 0
    failed = 0
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM soc_briefing_jobs
            WHERE status = 'running'
              AND lease_expires_at IS NOT NULL
              AND lease_expires_at <= %s
            ORDER BY lease_expires_at ASC, id ASC
            LIMIT %s
            FOR UPDATE SKIP LOCKED
            """,
            (current, max(0, min(int(limit), 200))),
        )
        jobs = _fetchall_dicts(cur)
        for job in jobs:
            if int(job["attempt_count"]) < int(job["max_attempts"]):
                cur.execute(
                    """
                    UPDATE soc_briefing_jobs
                    SET status = 'pending',
                        recovery_count = recovery_count + 1,
                        failure_code = 'stale_lease_recovered',
                        failure_message = 'stale lease recovered for retry',
                        lease_owner = NULL,
                        lease_acquired_at = NULL,
                        lease_heartbeat_at = NULL,
                        lease_expires_at = NULL,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (current, job["id"]),
                )
                recovered += 1
            else:
                cur.execute(
                    """
                    UPDATE soc_briefing_jobs
                    SET status = 'failed',
                        recovery_count = recovery_count + 1,
                        completed_at = %s,
                        failure_code = 'stale_lease_expired',
                        failure_message = 'stale lease exceeded max attempts',
                        lease_owner = NULL,
                        lease_acquired_at = NULL,
                        lease_heartbeat_at = NULL,
                        lease_expires_at = NULL,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (current, current, job["id"]),
                )
                failed += 1
    return {"recovered": recovered, "failed": failed}


def create_run(conn, job: dict[str, Any], *, now: datetime | None = None, budget_policy: dict[str, Any] | None = None) -> dict[str, Any]:
    current = as_utc(now) or utc_now()
    run_key = idempotency_key("soc-briefing-run", job["id"], job["attempt_count"], current.isoformat())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO soc_briefing_runs (
                job_id, schedule_id, window_id, run_key, service_actor,
                started_at, budget_policy, metadata, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                job["id"],
                job["schedule_id"],
                job["window_id"],
                run_key,
                SERVICE_ACTOR,
                current,
                Json(budget_policy or {}),
                Json({"read_only": True, "writes_performed": False}),
                current,
            ),
        )
        row = _fetchone_dict(cur)
    if row is None:
        raise SocBriefingPersistenceError("run insert returned no row")
    return row


def create_run_step(
    conn,
    run_id: int,
    *,
    step_index: int,
    step_type: str,
    status: str,
    tool_name: str | None = None,
    sanitized_input: dict[str, Any] | None = None,
    evidence_refs: list[dict[str, Any]] | None = None,
    decision_summary: str | None = None,
    latency_ms: int = 0,
    error_code: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    safe_input = redact_sensitive_values(sanitized_input or {})
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO soc_briefing_run_steps (
                run_id, step_index, step_type, status, tool_name, sanitized_input,
                evidence_refs, decision_summary, latency_ms, error_code, error_message, read_only, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s)
            RETURNING *
            """,
            (
                run_id,
                step_index,
                step_type,
                status,
                tool_name,
                Json(safe_input),
                Json(evidence_refs or []),
                decision_summary,
                max(0, int(latency_ms)),
                error_code,
                error_message,
                utc_now(),
            ),
        )
        row = _fetchone_dict(cur)
    if row is None:
        raise SocBriefingPersistenceError("run step insert returned no row")
    return row


def complete_run(
    conn,
    run_id: int,
    *,
    status: str,
    started_at: datetime,
    ai_gateway_status: str | None = None,
    provider_status: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    current = as_utc(now) or utc_now()
    runtime_ms = max(0, int((current - as_utc(started_at)).total_seconds() * 1000)) if started_at else 0
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE soc_briefing_runs
            SET status = %s,
                completed_at = %s,
                runtime_ms = %s,
                ai_gateway_status = %s,
                provider_status = %s,
                error_code = %s,
                error_message = %s,
                updated_at = %s
            WHERE id = %s
            RETURNING *
            """,
            (status, current, runtime_ms, ai_gateway_status, provider_status, error_code, error_message, current, run_id),
        )
        return _fetchone_dict(cur)


def create_briefing_lifecycle(
    conn,
    run: dict[str, Any],
    *,
    status: str,
    lifecycle_status: str,
    content_status: str,
    error_code: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO soc_briefings (
                run_id, schedule_id, window_id, status, lifecycle_status,
                content_status, sections, evidence_refs, error_code, error_message, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id) DO UPDATE
            SET status = EXCLUDED.status,
                lifecycle_status = EXCLUDED.lifecycle_status,
                content_status = EXCLUDED.content_status,
                error_code = EXCLUDED.error_code,
                error_message = EXCLUDED.error_message,
                updated_at = EXCLUDED.updated_at
            RETURNING *
            """,
            (
                run["id"],
                run["schedule_id"],
                run["window_id"],
                status,
                lifecycle_status,
                content_status,
                Json({}),
                Json([]),
                error_code,
                error_message,
                utc_now(),
            ),
        )
        row = _fetchone_dict(cur)
    if row is None:
        raise SocBriefingPersistenceError("briefing lifecycle insert returned no row")
    return row


def complete_window(conn, window_id: int, *, status: str, skip_reason: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE soc_briefing_schedule_windows
            SET status = %s,
                skip_reason = COALESCE(%s, skip_reason),
                updated_at = %s
            WHERE id = %s
            """,
            (status, skip_reason, utc_now(), window_id),
        )


def classify_ai_readiness(config: AiGatewayConfig | None = None) -> dict[str, str | None]:
    resolved = config if config is not None else load_ai_gateway_config()
    if resolved.mode == AI_MODE_DISABLED:
        return {
            "run_status": RUN_STATUS_BLOCKED,
            "job_status": JOB_STATUS_BLOCKED,
            "step_status": STEP_STATUS_BLOCKED,
            "ai_gateway_status": AI_STATUS_DISABLED,
            "provider_status": None,
            "error_code": "ai_gateway_disabled",
            "message": "AI gateway is disabled; scheduled briefing content was not generated.",
        }
    if not resolved.mode_valid:
        return {
            "run_status": RUN_STATUS_FAILED,
            "job_status": JOB_STATUS_FAILED,
            "step_status": STEP_STATUS_FAILED,
            "ai_gateway_status": "configuration_error",
            "provider_status": None,
            "error_code": "ai_gateway_configuration_error",
            "message": "AI gateway configuration is invalid.",
        }
    if resolved.mode == "local_only" and not resolved.local_configured:
        return {
            "run_status": RUN_STATUS_BLOCKED,
            "job_status": JOB_STATUS_BLOCKED,
            "step_status": STEP_STATUS_BLOCKED,
            "ai_gateway_status": "provider_unavailable",
            "provider_status": "local_provider_not_configured",
            "error_code": "local_provider_unavailable",
            "message": "Local AI provider is not configured or unavailable.",
        }
    if resolved.mode == "ask_before_paid_fallback":
        return {
            "run_status": RUN_STATUS_BLOCKED,
            "job_status": JOB_STATUS_BLOCKED,
            "step_status": STEP_STATUS_BLOCKED,
            "ai_gateway_status": "fallback_blocked",
            "provider_status": None,
            "error_code": "paid_fallback_blocked",
            "message": "Scheduled briefing runtime does not spend on paid fallback.",
        }
    return {
        "run_status": RUN_STATUS_SUCCESS,
        "job_status": JOB_STATUS_SUCCESS,
        "step_status": STEP_STATUS_SUCCESS,
        "ai_gateway_status": "ready",
        "provider_status": resolved.local_provider,
        "error_code": None,
        "message": "Runtime foundation completed readiness check; briefing content generation is out of scope.",
    }


def enforce_service_actor_read_only(action: str, *, tool_name: str | None = None) -> None:
    normalized = str(action or "").strip().lower()
    if normalized in MUTATION_ACTIONS:
        raise SocBriefingSecurityError(f"scheduled service actor cannot perform mutation action: {normalized}")
    if tool_name:
        validate_tool_name(tool_name)


def get_runtime_metrics(conn, *, now: datetime | None = None) -> dict[str, Any]:
    current = as_utc(now) or utc_now()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT status, COUNT(*)
            FROM soc_briefing_jobs
            GROUP BY status
            """
        )
        job_counts = {row[0]: int(row[1]) for row in cur.fetchall()}
        cur.execute(
            """
            SELECT COUNT(*)
            FROM soc_briefing_schedules
            WHERE enabled = TRUE AND next_due_at IS NOT NULL AND next_due_at <= %s
            """,
            (current,),
        )
        due_count = int(cur.fetchone()[0])
        cur.execute(
            """
            SELECT id, status, started_at, completed_at, error_code, error_message
            FROM soc_briefing_runs
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            """
        )
        latest_run = _fetchone_dict(cur)
    heartbeat = summarize_worker_health(
        get_worker_heartbeat(conn, worker_name=SOC_BRIEFING_WORKER_NAME),
        now=current,
    )
    return {
        "worker": heartbeat,
        "service_actor": SERVICE_ACTOR,
        "read_only": True,
        "due_schedules": due_count,
        "jobs": {
            "pending": job_counts.get(JOB_STATUS_PENDING, 0),
            "running": job_counts.get(JOB_STATUS_RUNNING, 0),
            "success": job_counts.get(JOB_STATUS_SUCCESS, 0),
            "failed": job_counts.get(JOB_STATUS_FAILED, 0),
            "blocked": job_counts.get(JOB_STATUS_BLOCKED, 0),
            "skipped": job_counts.get(JOB_STATUS_SKIPPED, 0),
            "interrupted": job_counts.get(JOB_STATUS_INTERRUPTED, 0),
        },
        "latest_run": latest_run,
    }
