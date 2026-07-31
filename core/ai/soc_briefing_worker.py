from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import signal
import time
from typing import Callable

from core.ai.config import AiGatewayConfig
from core.ai.soc_briefing_investigation_engine import (
    InvestigationBudget,
    ToolExecutor,
    run_scheduled_investigation,
)
from core.ai.soc_briefing_runtime_store import (
    DEFAULT_LEASE_DURATION_SECONDS,
    JOB_STATUS_INTERRUPTED,
    RUN_STATUS_INTERRUPTED,
    SERVICE_ACTOR,
    STEP_STATUS_INTERRUPTED,
    SocBriefingPersistenceError,
    autonomous_scheduling_enabled,
    as_utc,
    claim_next_job,
    complete_job,
    complete_run,
    complete_window,
    create_run,
    create_run_step,
    get_runtime_metrics,
    list_due_schedules,
    materialize_due_schedule,
    recover_stale_jobs,
    utc_now,
)
from core.db import get_db_connection
from core.worker_heartbeat_store import (
    SOC_BRIEFING_WORKER_NAME,
    WORKER_HEARTBEAT_INTERVAL_SECONDS,
    upsert_worker_heartbeat,
)

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 5
MAX_BATCH_SIZE = 25
DEFAULT_MAX_RUNTIME_SECONDS = 55
DEFAULT_MATERIALIZE_LIMIT = 25
DEFAULT_STALE_RECOVERY_LIMIT = 50


@dataclass(frozen=True)
class SocBriefingWorkerConfig:
    batch_size: int = DEFAULT_BATCH_SIZE
    materialize_limit: int = DEFAULT_MATERIALIZE_LIMIT
    stale_recovery_limit: int = DEFAULT_STALE_RECOVERY_LIMIT
    max_runtime_seconds: int = DEFAULT_MAX_RUNTIME_SECONDS
    lease_duration_seconds: int = DEFAULT_LEASE_DURATION_SECONDS
    heartbeat_interval_seconds: int = WORKER_HEARTBEAT_INTERVAL_SECONDS
    investigation_max_runtime_seconds: int = 45
    investigation_max_entities: int = 8
    investigation_max_tool_calls: int = 12
    investigation_max_prompt_chars: int = 8000
    investigation_max_prompt_tokens: int = 3000


class SocBriefingWorkerShutdown:
    def __init__(self) -> None:
        self.requested = False
        self.reason = "not_requested"

    def request(self, reason: str = "requested") -> None:
        self.requested = True
        self.reason = reason


def install_shutdown_signal_handlers(shutdown: SocBriefingWorkerShutdown) -> None:
    def _handle_signal(signum, _frame) -> None:
        shutdown.request(f"signal_{signum}")

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)


def normalize_config(config: SocBriefingWorkerConfig | None = None) -> SocBriefingWorkerConfig:
    raw = config or SocBriefingWorkerConfig()
    return SocBriefingWorkerConfig(
        batch_size=_clamp(raw.batch_size, 1, MAX_BATCH_SIZE, DEFAULT_BATCH_SIZE),
        materialize_limit=_clamp(raw.materialize_limit, 1, 200, DEFAULT_MATERIALIZE_LIMIT),
        stale_recovery_limit=_clamp(raw.stale_recovery_limit, 0, 200, DEFAULT_STALE_RECOVERY_LIMIT),
        max_runtime_seconds=_clamp(raw.max_runtime_seconds, 1, 300, DEFAULT_MAX_RUNTIME_SECONDS),
        lease_duration_seconds=_clamp(raw.lease_duration_seconds, 30, 900, DEFAULT_LEASE_DURATION_SECONDS),
        heartbeat_interval_seconds=_clamp(raw.heartbeat_interval_seconds, 1, 300, WORKER_HEARTBEAT_INTERVAL_SECONDS),
        investigation_max_runtime_seconds=_clamp(raw.investigation_max_runtime_seconds, 1, 240, 45),
        investigation_max_entities=_clamp(raw.investigation_max_entities, 1, 50, 8),
        investigation_max_tool_calls=_clamp(raw.investigation_max_tool_calls, 1, 50, 12),
        investigation_max_prompt_chars=_clamp(raw.investigation_max_prompt_chars, 1000, 50000, 8000),
        investigation_max_prompt_tokens=_clamp(raw.investigation_max_prompt_tokens, 250, 12000, 3000),
    )


def run_soc_briefing_worker(
    *,
    config: SocBriefingWorkerConfig | None = None,
    worker_id: str | None = None,
    shutdown: SocBriefingWorkerShutdown | None = None,
    connect: Callable[[], object] = get_db_connection,
    now_fn: Callable[[], datetime] | None = None,
    gateway_config: AiGatewayConfig | None = None,
    investigation_tool_executor: ToolExecutor | None = None,
) -> dict:
    cfg = normalize_config(config)
    state = shutdown or SocBriefingWorkerShutdown()
    owner = (worker_id or "").strip() or f"{SOC_BRIEFING_WORKER_NAME}-{int(time.time())}"
    clock = now_fn or utc_now
    started_at = as_utc(clock()) or utc_now()
    deadline = time.monotonic() + cfg.max_runtime_seconds
    stats = {
        "worker_name": SOC_BRIEFING_WORKER_NAME,
        "worker_id": owner,
        "service_actor": SERVICE_ACTOR,
        "build_version": None,
        "materialized_windows": 0,
        "queued_jobs": 0,
        "duplicate_windows": 0,
        "skipped_windows": 0,
        "blocked_schedules": 0,
        "recovered": 0,
        "recovery_failed": 0,
        "processed": 0,
        "success": 0,
        "failed": 0,
        "blocked": 0,
        "partial": 0,
        "skipped": 0,
        "interrupted": 0,
        "errors": 0,
        "shutdown_reason": None,
    }
    last_heartbeat = None

    logger.info("soc_briefing_worker_start worker_id=%s batch_size=%s", owner, cfg.batch_size)

    conn = None
    try:
        _record_heartbeat(connect, owner, stats["build_version"], started_at, clock())
        last_heartbeat = clock()
        conn = connect()
        recovery = recover_stale_jobs(conn, now=clock(), limit=cfg.stale_recovery_limit)
        conn.commit()
        stats["recovered"] += recovery["recovered"]
        stats["recovery_failed"] += recovery["failed"]
        _close(conn)
        conn = None

        conn = connect()
        if autonomous_scheduling_enabled(conn):
            schedules = list_due_schedules(conn, now=clock(), limit=cfg.materialize_limit)
            for schedule in schedules:
                if _deadline_reached(deadline) or state.requested:
                    break
                result = materialize_due_schedule(conn, schedule, now=clock())
                stats["materialized_windows"] += result.windows_created
                stats["queued_jobs"] += result.jobs_created
                stats["duplicate_windows"] += result.duplicate_windows
                stats["skipped_windows"] += result.skipped_windows
                stats["blocked_schedules"] += result.blocked_schedules
        else:
            stats["skipped_windows"] += 1
        conn.commit()
        _close(conn)
        conn = None

        while stats["processed"] < cfg.batch_size and not state.requested and not _deadline_reached(deadline):
            if _heartbeat_due(last_heartbeat, clock(), cfg.heartbeat_interval_seconds):
                _record_heartbeat(connect, owner, stats["build_version"], started_at, clock())
                last_heartbeat = clock()
            conn = connect()
            job = claim_next_job(
                conn,
                lease_owner=owner,
                now=clock(),
                lease_duration_seconds=cfg.lease_duration_seconds,
            )
            conn.commit()
            if job is None:
                _close(conn)
                conn = None
                break
            try:
                outcome = _process_job(
                    conn,
                    job,
                    lease_owner=owner,
                    now=clock(),
                    gateway_config=gateway_config,
                    worker_config=cfg,
                    investigation_tool_executor=investigation_tool_executor,
                )
                conn.commit()
                stats["processed"] += 1
                if outcome == "success":
                    stats["success"] += 1
                elif outcome == "blocked":
                    stats["blocked"] += 1
                elif outcome == "partial":
                    stats["partial"] += 1
                elif outcome == "skipped":
                    stats["skipped"] += 1
                else:
                    stats["failed"] += 1
            except Exception:
                conn.rollback()
                stats["errors"] += 1
                logger.exception("soc_briefing_worker_job_failed job_id=%s worker_id=%s", job.get("id"), owner)
                raise
            finally:
                _close(conn)
                conn = None

        if state.requested:
            stats["interrupted"] += _interrupt_owned_running_jobs(connect, owner, now=clock())
    except Exception:
        stats["errors"] += 1
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                logger.warning("soc_briefing_worker_rollback_failed worker_id=%s", owner, exc_info=True)
        raise
    finally:
        _close(conn)
        stats["shutdown_reason"] = state.reason if state.requested else "complete"
        logger.info("soc_briefing_worker_shutdown worker_id=%s stats=%s", owner, stats)
    return stats


def _process_job(
    conn,
    job: dict,
    *,
    lease_owner: str,
    now: datetime,
    gateway_config: AiGatewayConfig | None,
    worker_config: SocBriefingWorkerConfig,
    investigation_tool_executor: ToolExecutor | None,
) -> str:
    budget = InvestigationBudget(
        max_runtime_seconds=worker_config.investigation_max_runtime_seconds,
        max_entities=worker_config.investigation_max_entities,
        max_tool_calls=worker_config.investigation_max_tool_calls,
        max_prompt_chars=worker_config.investigation_max_prompt_chars,
        max_prompt_tokens=worker_config.investigation_max_prompt_tokens,
    )
    run = create_run(
        conn,
        job,
        now=now,
        budget_policy=budget.as_dict(),
    )
    create_run_step(
        conn,
        run["id"],
        step_index=0,
        step_type="runtime_investigation_start",
        status="success",
        sanitized_input={"job_id": job["id"], "window_id": job["window_id"]},
        evidence_refs=[],
        decision_summary="Created isolated scheduled briefing run and started read-only autonomous investigation.",
    )
    outcome = run_scheduled_investigation(
        conn,
        job=job,
        run=run,
        gateway_config=gateway_config or AiGatewayConfig(),
        budget=budget,
        tool_executor=investigation_tool_executor,
        now_fn=lambda: now,
    )
    complete_run(
        conn,
        run["id"],
        status=outcome.run_status,
        started_at=run["started_at"],
        ai_gateway_status=outcome.ai_gateway_status,
        provider_status=outcome.provider_status,
        error_code=outcome.error_code,
        error_message=outcome.error_message,
        now=now,
    )
    updated = complete_job(
        conn,
        int(job["id"]),
        lease_owner=lease_owner,
        status=outcome.job_status,
        failure_code=outcome.error_code,
        failure_message=outcome.error_message,
        now=now,
    )
    if updated is None:
        raise SocBriefingPersistenceError("owner-matched job completion failed")
    complete_window(
        conn,
        int(job["window_id"]),
        status=outcome.window_status if outcome.window_status in {"success", "failed", "blocked", "skipped", "partial"} else "partial",
        skip_reason=outcome.error_code,
    )
    return outcome.job_status


def _interrupt_owned_running_jobs(connect, owner: str, *, now: datetime) -> int:
    conn = None
    try:
        conn = connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, window_id
                FROM soc_briefing_jobs
                WHERE status = 'running' AND lease_owner = %s
                """,
                (owner,),
            )
            rows = cur.fetchall()
            for job_id, window_id in rows:
                cur.execute(
                    """
                    UPDATE soc_briefing_jobs
                    SET status = %s,
                        completed_at = %s,
                        failure_code = 'worker_shutdown',
                        failure_message = 'Worker shutdown interrupted this job.',
                        lease_owner = NULL,
                        lease_acquired_at = NULL,
                        lease_heartbeat_at = NULL,
                        lease_expires_at = NULL,
                        updated_at = %s
                    WHERE id = %s AND lease_owner = %s
                    """,
                    (JOB_STATUS_INTERRUPTED, now, now, job_id, owner),
                )
                cur.execute(
                    """
                    UPDATE soc_briefing_runs
                    SET status = %s,
                        completed_at = %s,
                        error_code = 'worker_shutdown',
                        error_message = 'Worker shutdown interrupted this run.',
                        updated_at = %s
                    WHERE job_id = %s AND status = 'running'
                    """,
                    (RUN_STATUS_INTERRUPTED, now, now, job_id),
                )
                cur.execute(
                    """
                    INSERT INTO soc_briefing_run_steps (
                        run_id, step_index, step_type, status, decision_summary,
                        error_code, error_message, read_only, updated_at
                    )
                    SELECT id, 999, 'worker_shutdown', %s,
                           'Worker shutdown preserved completed state and stopped new claims.',
                           'worker_shutdown', 'Worker shutdown interrupted this run.', TRUE, %s
                    FROM soc_briefing_runs
                    WHERE job_id = %s
                    ON CONFLICT (run_id, step_index) DO NOTHING
                    """,
                    (STEP_STATUS_INTERRUPTED, now, job_id),
                )
                cur.execute(
                    "UPDATE soc_briefing_schedule_windows SET status = 'failed', skip_reason = 'worker_shutdown', updated_at = %s WHERE id = %s",
                    (now, window_id),
                )
        conn.commit()
        return len(rows)
    finally:
        _close(conn)


def runtime_metrics(connect: Callable[[], object] = get_db_connection, *, now: datetime | None = None) -> dict:
    conn = None
    try:
        conn = connect()
        return get_runtime_metrics(conn, now=now)
    finally:
        _close(conn)


def _record_heartbeat(connect, owner: str, build_version: str | None, started_at: datetime, heartbeat_at: datetime) -> None:
    conn = None
    try:
        conn = connect()
        upsert_worker_heartbeat(
            conn,
            worker_name=SOC_BRIEFING_WORKER_NAME,
            worker_instance_id=owner,
            build_version=build_version,
            started_at=started_at,
            last_heartbeat_at=heartbeat_at,
        )
        conn.commit()
    finally:
        _close(conn)


def _clamp(value: int | None, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)


def _deadline_reached(deadline: float) -> bool:
    return time.monotonic() >= deadline


def _heartbeat_due(last_heartbeat: datetime | None, now: datetime, interval_seconds: int) -> bool:
    if last_heartbeat is None:
        return True
    return (now - last_heartbeat).total_seconds() >= interval_seconds


def _close(conn) -> None:
    if conn is None:
        return
    try:
        conn.close()
    except Exception:
        logger.warning("soc_briefing_worker_close_failed", exc_info=True)
