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
RUN_STATUS_PARTIAL = "partial"
RUN_STATUS_FAILED = "failed"
RUN_STATUS_BLOCKED = "blocked"
RUN_STATUS_SKIPPED = "skipped"
RUN_STATUS_INTERRUPTED = "interrupted"

STEP_STATUS_SUCCESS = "success"
STEP_STATUS_PARTIAL = "partial"
STEP_STATUS_FAILED = "failed"
STEP_STATUS_BLOCKED = "blocked"
STEP_STATUS_SKIPPED = "skipped"
STEP_STATUS_INTERRUPTED = "interrupted"

DEFAULT_MAX_CATCH_UP_WINDOWS = 3
DEFAULT_MAX_LOOKBACK_HOURS = 24
DEFAULT_LEASE_DURATION_SECONDS = 120
BRIEFING_MODE_MANUAL_ONLY = "manual_only"
BRIEFING_MODE_SCHEDULED_AUTONOMOUS = "scheduled_autonomous"
CONTROL_ROW_ID = 1
MANUAL_SCHEDULE_NAME = "Manual Anakin briefing"
TRIGGER_TYPE_SCHEDULED = "scheduled"
TRIGGER_TYPE_MANUAL = "manual"
ACTIVE_JOB_STATUSES = (JOB_STATUS_PENDING, JOB_STATUS_RUNNING)
SOC_BRIEFING_HEALTH_RUNNING = "running"
SOC_BRIEFING_HEALTH_HEALTHY_WAITING = "healthy_waiting"
SOC_BRIEFING_HEALTH_RECENTLY_SUCCESSFUL = "recently_successful"
SOC_BRIEFING_HEALTH_STALE = "stale"
SOC_BRIEFING_HEALTH_FAILED = "failed"
SOC_BRIEFING_HEALTH_TIMER_INACTIVE = "timer_inactive"

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


def get_or_create_controls(conn) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO soc_briefing_controls (id, mode, schedules_paused, pause_reason)
            VALUES (%s, %s, TRUE, 'manual-first default')
            ON CONFLICT (id) DO NOTHING
            """,
            (CONTROL_ROW_ID, BRIEFING_MODE_MANUAL_ONLY),
        )
        cur.execute("SELECT * FROM soc_briefing_controls WHERE id = %s", (CONTROL_ROW_ID,))
        row = _fetchone_dict(cur)
    if row is None:
        raise SocBriefingPersistenceError("failed to read SOC briefing controls")
    return row


def update_controls(
    conn,
    *,
    mode: str | None = None,
    schedules_paused: bool | None = None,
    pause_reason: str | None = None,
    updated_by: str | None = None,
) -> dict[str, Any]:
    current = get_or_create_controls(conn)
    next_mode = (mode or current["mode"] or BRIEFING_MODE_MANUAL_ONLY).strip()
    if next_mode not in {BRIEFING_MODE_MANUAL_ONLY, BRIEFING_MODE_SCHEDULED_AUTONOMOUS}:
        raise ValueError("invalid briefing mode")
    next_paused = bool(current["schedules_paused"]) if schedules_paused is None else bool(schedules_paused)
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE soc_briefing_controls
            SET mode = %s,
                schedules_paused = %s,
                pause_reason = %s,
                updated_by = %s,
                updated_at = %s
            WHERE id = %s
            RETURNING *
            """,
            (
                next_mode,
                next_paused,
                (pause_reason or "").strip()[:500] or None,
                (updated_by or "").strip()[:255] or None,
                utc_now(),
                CONTROL_ROW_ID,
            ),
        )
        row = _fetchone_dict(cur)
    if row is None:
        raise SocBriefingPersistenceError("failed to update SOC briefing controls")
    return row


def autonomous_scheduling_enabled(conn) -> bool:
    controls = get_or_create_controls(conn)
    return controls["mode"] == BRIEFING_MODE_SCHEDULED_AUTONOMOUS and not bool(controls["schedules_paused"])


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


def ensure_manual_schedule(conn, *, created_by: str | None = None) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM soc_briefing_schedules
            WHERE name = %s AND enabled = FALSE
            ORDER BY id ASC
            LIMIT 1
            """,
            (MANUAL_SCHEDULE_NAME,),
        )
        existing = _fetchone_dict(cur)
        if existing is not None:
            return existing
        cur.execute(
            """
            INSERT INTO soc_briefing_schedules (
                name, timezone, cadence_minutes, enabled, catch_up_enabled,
                max_catch_up_windows, max_lookback_hours, coalesce_missed_windows,
                next_due_at, created_by, updated_at
            )
            VALUES (%s, 'UTC', 1440, FALSE, FALSE, 1, 24, TRUE, NULL, %s, %s)
            RETURNING *
            """,
            (MANUAL_SCHEDULE_NAME, created_by, utc_now()),
        )
        row = _fetchone_dict(cur)
    if row is None:
        raise SocBriefingPersistenceError("failed to create manual SOC briefing schedule")
    return row


def get_active_manual_job(conn) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT j.*, w.window_start, w.window_end, s.name AS schedule_name
            FROM soc_briefing_jobs j
            JOIN soc_briefing_schedule_windows w ON w.id = j.window_id
            JOIN soc_briefing_schedules s ON s.id = j.schedule_id
            WHERE j.trigger_type = %s
              AND j.status IN ('pending', 'running')
            ORDER BY j.created_at ASC, j.id ASC
            LIMIT 1
            """,
            (TRIGGER_TYPE_MANUAL,),
        )
        return _fetchone_dict(cur)


def get_manual_job(conn, job_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT j.*, w.window_start, w.window_end, w.status AS window_status, w.skip_reason AS window_skip_reason,
                   s.name AS schedule_name
            FROM soc_briefing_jobs j
            JOIN soc_briefing_schedule_windows w ON w.id = j.window_id
            JOIN soc_briefing_schedules s ON s.id = j.schedule_id
            WHERE j.id = %s
              AND j.trigger_type = %s
            """,
            (job_id, TRIGGER_TYPE_MANUAL),
        )
        return _fetchone_dict(cur)


def _latest_run_for_job(conn, job_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM soc_briefing_runs
            WHERE job_id = %s
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            """,
            (job_id,),
        )
        return _fetchone_dict(cur)


def _briefing_for_run(conn, run_id: int | None) -> dict[str, Any] | None:
    if not run_id:
        return None
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM soc_briefings
            WHERE run_id = %s
            ORDER BY generated_at DESC NULLS LAST, created_at DESC, id DESC
            LIMIT 1
            """,
            (run_id,),
        )
        return _fetchone_dict(cur)


def _normalize_manual_lifecycle(
    *,
    job: dict[str, Any] | None,
    run: dict[str, Any] | None,
    briefing: dict[str, Any] | None,
    worker: dict[str, Any],
    already_running: bool = False,
) -> dict[str, Any]:
    if job is None:
        return {"status": "unknown", "terminal": True, "blocked_reasons": [{"code": "manual_job_not_found", "message": "Manual briefing job was not found."}]}

    job_status = str(job.get("status") or "").lower()
    run_status = str((run or {}).get("status") or "").lower()
    content_status = str((briefing or {}).get("content_status") or "").lower()
    provider_status = str((run or {}).get("provider_status") or "").lower()
    error_code = job.get("failure_code") or (run or {}).get("error_code") or (briefing or {}).get("error_code")
    error_message = job.get("failure_message") or (run or {}).get("error_message") or (briefing or {}).get("error_message")
    worker_status = str(worker.get("status") or "").lower() if isinstance(worker, dict) else ""

    status = "unknown"
    terminal = False
    if job_status == JOB_STATUS_PENDING:
        status = "queued"
    elif job_status == JOB_STATUS_RUNNING or run_status == RUN_STATUS_RUNNING:
        status = "running"
    elif run_status == RUN_STATUS_PARTIAL or (briefing and str(briefing.get("status") or "").lower() == "partial"):
        status = "partial"
        terminal = True
    elif job_status == JOB_STATUS_SUCCESS or run_status == RUN_STATUS_SUCCESS:
        status = "completed"
        terminal = True
    elif job_status == JOB_STATUS_BLOCKED or run_status == RUN_STATUS_BLOCKED or content_status == "blocked":
        status = "blocked"
        terminal = True
    elif job_status == JOB_STATUS_FAILED or run_status == RUN_STATUS_FAILED or content_status == "failed":
        status = "timed_out" if str(error_code or "").lower() in {"timeout", "provider_timeout", "runtime_timeout", "stale_lease_expired"} else "failed"
        terminal = True
    elif job_status in {JOB_STATUS_SKIPPED, JOB_STATUS_INTERRUPTED} or run_status in {RUN_STATUS_SKIPPED, RUN_STATUS_INTERRUPTED}:
        status = "degraded"
        terminal = True

    blocked_reasons: list[dict[str, str]] = []
    if already_running:
        blocked_reasons.append({"code": "already_running", "message": "A manual Anakin briefing is already pending or running."})
    if job_status == JOB_STATUS_PENDING and worker_status in {"failed", "stale", "timer_inactive", "unavailable"}:
        blocked_reasons.append(
            {
                "code": "worker_unavailable",
                "message": worker.get("message") if isinstance(worker, dict) and worker.get("message") else "SOC briefing worker is not currently able to process this job.",
            }
        )
    if provider_status in {"local_provider_not_configured", "provider_unavailable", "local_provider_unavailable"}:
        blocked_reasons.append({"code": "local_model_unavailable", "message": "Local AI provider or model is unavailable."})
    if error_code:
        message = str(error_message or str(error_code).replace("_", " "))
        blocked_reasons.append({"code": str(error_code), "message": message[:500]})

    return {"status": status, "terminal": terminal, "blocked_reasons": blocked_reasons}


def get_manual_briefing_lifecycle_status(
    conn,
    *,
    job_id: int | None = None,
    already_running: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = as_utc(now) or utc_now()
    job = get_manual_job(conn, int(job_id)) if job_id else get_active_manual_job(conn)
    run = _latest_run_for_job(conn, int(job["id"])) if job else None
    briefing = _briefing_for_run(conn, int(run["id"])) if run else None
    control_status = get_briefing_control_status(conn, now=current)
    worker = control_status["worker"]
    lifecycle = _normalize_manual_lifecycle(
        job=job,
        run=run,
        briefing=briefing,
        worker=worker,
        already_running=already_running,
    )
    return {
        "job": job,
        "run": run,
        "briefing": briefing,
        "worker": worker,
        "lifecycle": lifecycle,
        "blocked_reasons": lifecycle["blocked_reasons"],
        "terminal": bool(lifecycle["terminal"]),
        "now": current,
        "read_only": True,
    }


def create_manual_briefing_job(
    conn,
    *,
    requested_by: str | None = None,
    now: datetime | None = None,
    window_minutes: int = 60,
) -> tuple[dict[str, Any], bool]:
    existing = get_active_manual_job(conn)
    if existing is not None:
        return existing, False

    current = as_utc(now) or utc_now()
    minutes = max(5, min(int(window_minutes or 60), 24 * 60))
    schedule = ensure_manual_schedule(conn, created_by=requested_by)
    window, _window_created = create_or_get_window(
        conn,
        schedule_id=int(schedule["id"]),
        window_start=current - timedelta(minutes=minutes),
        window_end=current,
        status=WINDOW_STATUS_QUEUED,
        coalesced=False,
    )
    job, job_created = create_or_get_job(
        conn,
        schedule_id=int(schedule["id"]),
        window_id=int(window["id"]),
        max_attempts=1,
        trigger_type=TRIGGER_TYPE_MANUAL,
        requested_by=requested_by,
        request_metadata={
            "trigger_type": TRIGGER_TYPE_MANUAL,
            "requested_by": requested_by,
            "window_minutes": minutes,
            "read_only": True,
            "writes_performed": False,
        },
        priority=25,
        now=current,
    )
    return job, job_created


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
        _job, job_created = create_or_get_job(conn, schedule_id=int(schedule["id"]), window_id=int(window["id"]), now=current)
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


def create_or_get_job(
    conn,
    *,
    schedule_id: int,
    window_id: int,
    max_attempts: int = 3,
    trigger_type: str = TRIGGER_TYPE_SCHEDULED,
    requested_by: str | None = None,
    request_metadata: dict[str, Any] | None = None,
    priority: int = 100,
    now: datetime | None = None,
) -> tuple[dict[str, Any], bool]:
    normalized_trigger = (trigger_type or TRIGGER_TYPE_SCHEDULED).strip()
    if normalized_trigger not in {TRIGGER_TYPE_SCHEDULED, TRIGGER_TYPE_MANUAL}:
        raise ValueError("invalid SOC briefing job trigger_type")
    current = as_utc(now) or utc_now()
    key = idempotency_key("soc-briefing-job", window_id)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO soc_briefing_jobs (
                schedule_id, window_id, idempotency_key, max_attempts, service_actor,
                priority, trigger_type, requested_by, request_metadata, not_before, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (window_id) DO NOTHING
            RETURNING *
            """,
            (
                schedule_id,
                window_id,
                key,
                max_attempts,
                SERVICE_ACTOR,
                max(1, min(int(priority), 1000)),
                normalized_trigger,
                (requested_by or "").strip()[:255] or None,
                Json(request_metadata or {}),
                current,
                current,
            ),
        )
        row = _fetchone_dict(cur)
        if row is not None:
            return row, True
        cur.execute("SELECT * FROM soc_briefing_jobs WHERE window_id = %s", (window_id,))
        existing = _fetchone_dict(cur)
    if existing is None:
        raise SocBriefingPersistenceError("failed to fetch existing SOC briefing job after conflict")
    return existing, False


def get_briefing_control_status(conn, *, now: datetime | None = None) -> dict[str, Any]:
    controls = get_or_create_controls(conn)
    current = as_utc(now) or utc_now()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, next_due_at, catch_up_enabled, max_catch_up_windows,
                   max_lookback_hours, coalesce_missed_windows, status, failure_code
            FROM soc_briefing_schedules
            WHERE enabled = TRUE
              AND next_due_at IS NOT NULL
            ORDER BY next_due_at ASC, id ASC
            LIMIT 1
            """
        )
        next_schedule = _fetchone_dict(cur)
        cur.execute(
            """
            SELECT b.id AS briefing_id,
                   b.generated_at,
                   b.created_at,
                   b.status AS briefing_status,
                   b.content_status,
                   r.id AS run_id,
                   r.status AS run_status,
                   r.provider_status,
                   r.ai_gateway_status,
                   r.runtime_ms,
                   r.error_code,
                   j.trigger_type
            FROM soc_briefings b
            JOIN soc_briefing_runs r ON r.id = b.run_id
            JOIN soc_briefing_jobs j ON j.id = r.job_id
            WHERE b.status IN ('success', 'partial')
              AND b.content_status IN ('ready', 'blocked', 'failed')
            ORDER BY COALESCE(b.generated_at, b.created_at) DESC, b.id DESC
            LIMIT 1
            """
        )
        last_run = _fetchone_dict(cur)
        cur.execute(
            """
            SELECT trigger_type, status, COUNT(*)
            FROM soc_briefing_jobs
            WHERE status IN ('pending', 'running')
            GROUP BY trigger_type, status
            """
        )
        counts = _fetchall_dicts(cur)
        cur.execute(
            """
            SELECT id, trigger_type, status, failure_code, failure_message,
                   lease_owner, lease_acquired_at, lease_heartbeat_at, lease_expires_at,
                   started_at, completed_at, updated_at
            FROM soc_briefing_jobs
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """
        )
        latest_job = _fetchone_dict(cur)

    active_manual = get_active_manual_job(conn)

    active_counts: dict[str, dict[str, int]] = {
        TRIGGER_TYPE_MANUAL: {JOB_STATUS_PENDING: 0, JOB_STATUS_RUNNING: 0},
        TRIGGER_TYPE_SCHEDULED: {JOB_STATUS_PENDING: 0, JOB_STATUS_RUNNING: 0},
    }
    for row in counts:
        trigger = row.get("trigger_type") or TRIGGER_TYPE_SCHEDULED
        status = row.get("status") or JOB_STATUS_PENDING
        if trigger not in active_counts:
            active_counts[trigger] = {}
        active_counts[trigger][status] = int(row.get("count") or 0)

    heartbeat = summarize_worker_health(
        get_worker_heartbeat(conn, worker_name=SOC_BRIEFING_WORKER_NAME),
        now=current,
    )
    worker = _timer_aware_worker_health(
        heartbeat=heartbeat,
        controls=controls,
        latest_run=last_run,
        latest_job=latest_job,
        active_counts=active_counts,
        next_schedule=next_schedule,
        now=current,
    )

    catch_up = None
    if next_schedule is not None:
        catch_up = {
            "enabled": bool(next_schedule.get("catch_up_enabled")),
            "max_windows": int(next_schedule.get("max_catch_up_windows") or 0),
            "max_lookback_hours": int(next_schedule.get("max_lookback_hours") or 0),
            "coalesce_missed_windows": bool(next_schedule.get("coalesce_missed_windows")),
            "status": "paused"
            if bool(controls["schedules_paused"])
            else ("manual_only" if controls["mode"] == BRIEFING_MODE_MANUAL_ONLY else "active"),
        }

    return {
        "mode": controls["mode"],
        "schedules_paused": bool(controls["schedules_paused"]),
        "pause_reason": controls.get("pause_reason"),
        "updated_at": controls.get("updated_at"),
        "updated_by": controls.get("updated_by"),
        "autonomous_scheduling_enabled": controls["mode"] == BRIEFING_MODE_SCHEDULED_AUTONOMOUS
        and not bool(controls["schedules_paused"]),
        "now": current,
        "next_scheduled_run": next_schedule,
        "last_successful_run": last_run,
        "latest_job": latest_job,
        "worker": worker,
        "catch_up": catch_up,
        "active_jobs": active_counts,
        "active_manual_job": active_manual,
    }


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
            terminal = _terminal_recovery_from_latest_run(cur, job, current)
            if terminal is not None:
                if terminal:
                    recovered += 1
                continue
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
    metadata = {
        "read_only": True,
        "writes_performed": False,
        "trigger_type": job.get("trigger_type") or TRIGGER_TYPE_SCHEDULED,
        "requested_by": job.get("requested_by"),
    }
    if isinstance(job.get("request_metadata"), dict):
        metadata.update(job["request_metadata"])
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
                Json(metadata),
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
            ON CONFLICT (run_id, step_index) DO UPDATE
            SET step_type = EXCLUDED.step_type,
                status = EXCLUDED.status,
                tool_name = EXCLUDED.tool_name,
                sanitized_input = jsonb_set(
                    EXCLUDED.sanitized_input,
                    '{retry_history}',
                    COALESCE(soc_briefing_run_steps.sanitized_input->'retry_history', '[]'::jsonb) ||
                        jsonb_build_array(
                            jsonb_build_object(
                                'status', soc_briefing_run_steps.status,
                                'step_type', soc_briefing_run_steps.step_type,
                                'tool_name', soc_briefing_run_steps.tool_name,
                                'decision_summary', soc_briefing_run_steps.decision_summary,
                                'error_code', soc_briefing_run_steps.error_code,
                                'updated_at', soc_briefing_run_steps.updated_at
                            )
                        ),
                    TRUE
                ),
                evidence_refs = EXCLUDED.evidence_refs,
                decision_summary = EXCLUDED.decision_summary,
                latency_ms = EXCLUDED.latency_ms,
                error_code = EXCLUDED.error_code,
                error_message = EXCLUDED.error_message,
                read_only = TRUE,
                updated_at = EXCLUDED.updated_at
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


def _timer_aware_worker_health(
    *,
    heartbeat: dict[str, Any],
    controls: dict[str, Any],
    latest_run: dict[str, Any] | None,
    latest_job: dict[str, Any] | None,
    active_counts: dict[str, dict[str, int]],
    next_schedule: dict[str, Any] | None,
    now: datetime,
) -> dict[str, Any]:
    raw_status = str(heartbeat.get("status") or "unknown").lower()
    manual_active = sum(int(value or 0) for value in active_counts.get(TRIGGER_TYPE_MANUAL, {}).values())
    scheduled_active = sum(int(value or 0) for value in active_counts.get(TRIGGER_TYPE_SCHEDULED, {}).values())
    running_jobs = int(active_counts.get(TRIGGER_TYPE_MANUAL, {}).get(JOB_STATUS_RUNNING, 0)) + int(
        active_counts.get(TRIGGER_TYPE_SCHEDULED, {}).get(JOB_STATUS_RUNNING, 0)
    )
    latest_job_status = str((latest_job or {}).get("status") or "").lower()
    latest_failure_code = (latest_job or {}).get("failure_code") or (latest_run or {}).get("error_code")
    latest_failure_message = (latest_job or {}).get("failure_message") or (latest_run or {}).get("error_message")
    latest_completed_at = as_utc((latest_job or {}).get("completed_at")) or as_utc((latest_run or {}).get("generated_at")) or as_utc((latest_run or {}).get("created_at"))
    latest_age_seconds = None
    if latest_completed_at is not None:
        latest_age_seconds = max(0, int((now - latest_completed_at).total_seconds()))

    if running_jobs > 0 and raw_status in {"healthy", "degraded"}:
        status = SOC_BRIEFING_HEALTH_RUNNING
        message = "SOC briefing worker is processing queued briefing work."
    elif latest_job_status in {JOB_STATUS_FAILED, JOB_STATUS_INTERRUPTED} and latest_failure_code:
        status = SOC_BRIEFING_HEALTH_FAILED
        message = str(latest_failure_message or latest_failure_code).strip()[:500] or "Last SOC briefing worker execution failed."
    elif latest_age_seconds is not None and latest_age_seconds <= 15 * 60 and latest_job_status in {JOB_STATUS_SUCCESS, JOB_STATUS_BLOCKED, JOB_STATUS_SKIPPED}:
        status = SOC_BRIEFING_HEALTH_RECENTLY_SUCCESSFUL
        message = "SOC briefing worker completed a recent one-shot execution."
    elif raw_status in {"healthy", "degraded"}:
        status = SOC_BRIEFING_HEALTH_HEALTHY_WAITING
        message = "SOC briefing worker timer is healthy and waiting for queued or scheduled work."
    elif raw_status in {"offline", "unknown"} and (manual_active or scheduled_active):
        status = SOC_BRIEFING_HEALTH_STALE
        message = "SOC briefing worker has active queued work but no recent execution heartbeat."
    elif controls["mode"] == BRIEFING_MODE_MANUAL_ONLY and not manual_active:
        status = SOC_BRIEFING_HEALTH_HEALTHY_WAITING
        message = "Manual-only mode is waiting for explicit Run Now requests."
    elif next_schedule is None and not manual_active and not scheduled_active:
        status = SOC_BRIEFING_HEALTH_TIMER_INACTIVE
        message = "No active SOC briefing timer schedule is configured."
    else:
        status = SOC_BRIEFING_HEALTH_STALE if raw_status in {"offline", "unknown"} else raw_status
        message = heartbeat.get("message") or "SOC briefing worker timer status is unavailable."

    return {
        **heartbeat,
        "status": status,
        "raw_heartbeat_status": raw_status,
        "source": "timer_aware_worker_health",
        "one_shot_timer": True,
        "active_manual_jobs": manual_active,
        "active_scheduled_jobs": scheduled_active,
        "latest_job_status": latest_job_status or None,
        "latest_failure_code": latest_failure_code,
        "message": message,
    }


def _terminal_recovery_from_latest_run(cur, job: dict[str, Any], current: datetime) -> bool | None:
    cur.execute(
        """
        SELECT r.status AS run_status,
               r.error_code,
               r.error_message,
               b.id AS briefing_id,
               b.status AS briefing_status,
               b.content_status
        FROM soc_briefing_runs r
        LEFT JOIN soc_briefings b ON b.run_id = r.id
        WHERE r.job_id = %s
        ORDER BY r.started_at DESC, r.id DESC
        LIMIT 1
        """,
        (job["id"],),
    )
    run = _fetchone_dict(cur)
    if run is None:
        return None
    run_status = str(run.get("run_status") or "").lower()
    briefing_id = run.get("briefing_id")
    if run_status in {RUN_STATUS_SUCCESS, RUN_STATUS_PARTIAL, RUN_STATUS_BLOCKED, RUN_STATUS_SKIPPED} and briefing_id:
        job_status = JOB_STATUS_SUCCESS if run_status in {RUN_STATUS_SUCCESS, RUN_STATUS_PARTIAL} else run_status
        cur.execute(
            """
            UPDATE soc_briefing_jobs
            SET status = %s,
                recovery_count = recovery_count + 1,
                failure_code = %s,
                failure_message = %s,
                completed_at = COALESCE(completed_at, %s),
                lease_owner = NULL,
                lease_acquired_at = NULL,
                lease_heartbeat_at = NULL,
                lease_expires_at = NULL,
                updated_at = %s
            WHERE id = %s
              AND status = 'running'
            """,
            (
                job_status,
                run.get("error_code"),
                run.get("error_message"),
                current,
                current,
                job["id"],
            ),
        )
        return True
    return None


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


def update_briefing_content(
    conn,
    run: dict[str, Any],
    *,
    status: str,
    lifecycle_status: str,
    content_status: str,
    summary: str | None,
    sections: dict[str, Any],
    evidence_refs: list[dict[str, Any]],
    error_code: str | None = None,
    error_message: str | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    current = as_utc(generated_at) or utc_now()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO soc_briefings (
                run_id, schedule_id, window_id, status, lifecycle_status,
                content_status, generated_at, summary, sections, evidence_refs,
                error_code, error_message, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id) DO UPDATE
            SET status = EXCLUDED.status,
                lifecycle_status = EXCLUDED.lifecycle_status,
                content_status = EXCLUDED.content_status,
                generated_at = EXCLUDED.generated_at,
                summary = EXCLUDED.summary,
                sections = EXCLUDED.sections,
                evidence_refs = EXCLUDED.evidence_refs,
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
                current,
                summary,
                Json(redact_sensitive_values(sections or {})),
                Json(redact_sensitive_values(evidence_refs or [])),
                error_code,
                error_message,
                current,
            ),
        )
        row = _fetchone_dict(cur)
    if row is None:
        raise SocBriefingPersistenceError("briefing content upsert returned no row")
    return row


def record_scheduled_investigation_audit(
    conn,
    *,
    event_type: str,
    run_id: int,
    schedule_id: int,
    window_id: int,
    details: dict[str, Any],
    target_alert_id: int | None = None,
) -> dict[str, Any]:
    safe_details = redact_sensitive_values(
        {
            "run_id": run_id,
            "schedule_id": schedule_id,
            "window_id": window_id,
            "service_actor": SERVICE_ACTOR,
            "service_actor_role": SERVICE_ACTOR_ROLE,
            "read_only": True,
            **(details or {}),
        }
    )
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit_log (
                event_type, actor_username, actor_role, target_alert_id,
                request_path, details
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                event_type,
                SERVICE_ACTOR,
                SERVICE_ACTOR_ROLE,
                target_alert_id,
                "scheduled_soc_briefing_worker",
                Json(safe_details),
            ),
        )
        row = _fetchone_dict(cur)
    if row is None:
        raise SocBriefingPersistenceError("scheduled investigation audit insert returned no row")
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
