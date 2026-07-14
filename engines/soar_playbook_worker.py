from __future__ import annotations

import logging
import random
import signal
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from core.db import get_db_connection
from core.playbook_worker_identity import generate_playbook_worker_id
from core.worker_heartbeat_store import (
    PLAYBOOK_WORKER_NAME,
    WORKER_HEARTBEAT_INTERVAL_SECONDS,
    upsert_worker_heartbeat,
)
from engines.playbook_step_executor import process_playbook_execution_batch
from scripts.run_playbook_executor_once import recover_stale_playbook_executions

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parent.parent

# spec: SPEC-WORKER-001 / SPEC-UI-004 - daemon loop is real orchestration; adapter effects stay guarded.
DEFAULT_POLL_INTERVAL_SECONDS = 5.0
DEFAULT_IDLE_BACKOFF_SECONDS = 30.0
DEFAULT_JITTER_SECONDS = 2.0
DEFAULT_ERROR_BACKOFF_SECONDS = 10.0
DEFAULT_BATCH_SIZE = 10
MAX_BATCH_SIZE = 50
DEFAULT_STALE_RECOVERY_INTERVAL_SECONDS = 60.0
DEFAULT_STALE_LIMIT = 50
MAX_STALE_LIMIT = 200


@dataclass(frozen=True)
class PlaybookWorkerConfig:
    batch_size: int = DEFAULT_BATCH_SIZE
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS
    idle_backoff_seconds: float = DEFAULT_IDLE_BACKOFF_SECONDS
    jitter_seconds: float = DEFAULT_JITTER_SECONDS
    error_backoff_seconds: float = DEFAULT_ERROR_BACKOFF_SECONDS
    stale_recovery_interval_seconds: float = DEFAULT_STALE_RECOVERY_INTERVAL_SECONDS
    stale_limit: int = DEFAULT_STALE_LIMIT
    dry_run_recovery: bool = False
    max_loops: int | None = None
    heartbeat_interval_seconds: float = WORKER_HEARTBEAT_INTERVAL_SECONDS


class PlaybookWorkerShutdown:
    def __init__(self) -> None:
        self.requested = False
        self.reason = "not_requested"

    def request(self, reason: str = "requested") -> None:
        self.requested = True
        self.reason = reason


def normalize_config(config: PlaybookWorkerConfig | None = None) -> PlaybookWorkerConfig:
    raw = config or PlaybookWorkerConfig()
    return PlaybookWorkerConfig(
        batch_size=_clamp_int(raw.batch_size, 1, MAX_BATCH_SIZE, DEFAULT_BATCH_SIZE),
        poll_interval_seconds=_nonnegative_float(raw.poll_interval_seconds, DEFAULT_POLL_INTERVAL_SECONDS),
        idle_backoff_seconds=_nonnegative_float(raw.idle_backoff_seconds, DEFAULT_IDLE_BACKOFF_SECONDS),
        jitter_seconds=_nonnegative_float(raw.jitter_seconds, DEFAULT_JITTER_SECONDS),
        error_backoff_seconds=_nonnegative_float(raw.error_backoff_seconds, DEFAULT_ERROR_BACKOFF_SECONDS),
        stale_recovery_interval_seconds=_nonnegative_float(
            raw.stale_recovery_interval_seconds,
            DEFAULT_STALE_RECOVERY_INTERVAL_SECONDS,
        ),
        stale_limit=_clamp_int(raw.stale_limit, 1, MAX_STALE_LIMIT, DEFAULT_STALE_LIMIT),
        dry_run_recovery=bool(raw.dry_run_recovery),
        max_loops=raw.max_loops if raw.max_loops is None else max(0, int(raw.max_loops)),
        heartbeat_interval_seconds=_nonnegative_float(
            raw.heartbeat_interval_seconds,
            WORKER_HEARTBEAT_INTERVAL_SECONDS,
        ),
    )


def install_shutdown_signal_handlers(shutdown: PlaybookWorkerShutdown) -> None:
    def _handle_signal(signum, _frame) -> None:
        shutdown.request(f"signal_{signum}")

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)


def run_playbook_worker(
    *,
    config: PlaybookWorkerConfig | None = None,
    worker_id: str | None = None,
    shutdown: PlaybookWorkerShutdown | None = None,
    connect: Callable[[], object] = get_db_connection,
    sleeper: Callable[[float], None] = time.sleep,
    now_fn: Callable[[], datetime] | None = None,
    jitter_fn: Callable[[float], float] | None = None,
) -> dict:
    """
    Run the daemon loop until shutdown is requested or max_loops is reached.

    The loop opens a fresh DB connection per iteration. That keeps DB disconnects
    fail-closed and lets the next iteration reconnect instead of reusing a broken
    connection.
    """
    cfg = normalize_config(config)
    state = shutdown or PlaybookWorkerShutdown()
    owner = (worker_id or "").strip() or generate_playbook_worker_id()
    clock = now_fn or _utc_now
    jitter = jitter_fn or _default_jitter
    stats = {
        "worker_name": PLAYBOOK_WORKER_NAME,
        "worker_id": owner,
        "build_version": _resolve_worker_build_version(),
        "loops": 0,
        "processed": 0,
        "success": 0,
        "failed": 0,
        "skipped": 0,
        "recovered": 0,
        "errors": 0,
        "shutdown_reason": None,
    }
    process_started_at = clock()
    last_recovery_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    last_heartbeat_attempt_at: datetime | None = None

    logger.info(
        "soar_playbook_worker_start worker_id=%s batch_size=%s poll_interval=%s idle_backoff=%s stale_recovery_interval=%s dry_run_recovery=%s",
        owner,
        cfg.batch_size,
        cfg.poll_interval_seconds,
        cfg.idle_backoff_seconds,
        cfg.stale_recovery_interval_seconds,
        cfg.dry_run_recovery,
    )

    while not state.requested:
        if cfg.max_loops is not None and stats["loops"] >= cfg.max_loops:
            state.request("max_loops")
            break

        loop_started_at = clock()
        conn = None
        did_recovery = False
        recovery_result = None
        batch_result = None
        try:
            if _heartbeat_due(
                last_heartbeat_attempt_at,
                loop_started_at,
                cfg.heartbeat_interval_seconds,
            ):
                last_heartbeat_attempt_at = loop_started_at
                if _record_worker_heartbeat(
                    connect=connect,
                    worker_id=owner,
                    build_version=stats["build_version"],
                    process_started_at=process_started_at,
                    heartbeat_at=loop_started_at,
                ):
                    last_heartbeat_at = loop_started_at
            conn = connect()
            if _should_run_recovery(
                last_recovery_at,
                loop_started_at,
                cfg.stale_recovery_interval_seconds,
            ):
                did_recovery = True
                recovery_result = recover_stale_playbook_executions(
                    conn,
                    limit=cfg.stale_limit,
                    dry_run=cfg.dry_run_recovery,
                    now=loop_started_at,
                )
                if cfg.dry_run_recovery:
                    conn.rollback()
                else:
                    conn.commit()
                last_recovery_at = loop_started_at
                stats["recovered"] += int(recovery_result.get("recovered") or 0)

            batch_result = process_playbook_execution_batch(
                conn,
                limit=cfg.batch_size,
                now=loop_started_at,
                worker_id=owner,
            )
            conn.commit()
            stats["loops"] += 1
            stats["processed"] += int(batch_result.get("processed") or 0)
            stats["success"] += int(batch_result.get("success") or 0)
            stats["failed"] += int(batch_result.get("failed") or 0)
            stats["skipped"] += int(batch_result.get("skipped") or 0)
            logger.info(
                "soar_playbook_worker_loop worker_id=%s loop=%s processed=%s success=%s failed=%s skipped=%s recovered=%s recovery_ran=%s",
                owner,
                stats["loops"],
                batch_result.get("processed"),
                batch_result.get("success"),
                batch_result.get("failed"),
                batch_result.get("skipped"),
                (recovery_result or {}).get("recovered", 0),
                did_recovery,
            )
            sleep_for = _sleep_seconds(
                cfg,
                idle=_loop_was_idle(batch_result, recovery_result),
                jitter_fn=jitter,
                last_heartbeat_at=last_heartbeat_attempt_at,
                now=clock(),
            )
        except Exception as error:
            stats["errors"] += 1
            _rollback_safely(conn, owner)
            logger.error(
                "soar_playbook_worker_loop_error worker_id=%s loop=%s error_type=%s",
                owner,
                stats["loops"] + 1,
                type(error).__name__,
            )
            sleep_for = _sleep_seconds_for_error(
                cfg,
                jitter,
                last_heartbeat_at=last_heartbeat_attempt_at,
                now=clock(),
            )
        finally:
            _close_safely(conn, owner)

        _sleep_if_needed(sleep_for, state, sleeper)

    stats["shutdown_reason"] = state.reason
    logger.info(
        "soar_playbook_worker_shutdown worker_id=%s reason=%s loops=%s processed=%s recovered=%s errors=%s",
        owner,
        state.reason,
        stats["loops"],
        stats["processed"],
        stats["recovered"],
        stats["errors"],
    )
    return stats


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _default_jitter(max_seconds: float) -> float:
    if max_seconds <= 0:
        return 0.0
    return random.uniform(0, max_seconds)


def _clamp_int(value: int | None, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)


def _nonnegative_float(value: float | int | None, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0.0, parsed)


def _should_run_recovery(
    last_recovery_at: datetime | None,
    now: datetime,
    interval_seconds: float,
) -> bool:
    if last_recovery_at is None:
        return True
    if interval_seconds <= 0:
        return True
    return now >= last_recovery_at + timedelta(seconds=interval_seconds)


def _loop_was_idle(batch_result: dict | None, recovery_result: dict | None) -> bool:
    processed = int((batch_result or {}).get("processed") or 0)
    recovered = int((recovery_result or {}).get("recovered") or 0)
    return processed == 0 and recovered == 0


def _sleep_seconds(
    config: PlaybookWorkerConfig,
    *,
    idle: bool,
    jitter_fn: Callable[[float], float],
    last_heartbeat_at: datetime | None,
    now: datetime,
) -> float:
    base = config.idle_backoff_seconds if idle else config.poll_interval_seconds
    sleep_for = base + jitter_fn(config.jitter_seconds)
    return min(sleep_for, _seconds_until_heartbeat_due(last_heartbeat_at, now, config.heartbeat_interval_seconds))


def _sleep_seconds_for_error(
    config: PlaybookWorkerConfig,
    jitter_fn: Callable[[float], float],
    last_heartbeat_at: datetime | None,
    now: datetime,
) -> float:
    sleep_for = config.error_backoff_seconds + jitter_fn(config.jitter_seconds)
    return min(sleep_for, _seconds_until_heartbeat_due(last_heartbeat_at, now, config.heartbeat_interval_seconds))


def _seconds_until_heartbeat_due(
    last_heartbeat_at: datetime | None,
    now: datetime,
    interval_seconds: float,
) -> float:
    interval = max(0.0, float(interval_seconds))
    if interval == 0:
        return 0.0
    if last_heartbeat_at is None:
        return 0.0
    elapsed = max(0.0, (now - last_heartbeat_at).total_seconds())
    return max(0.0, interval - elapsed)


def _heartbeat_due(
    last_heartbeat_at: datetime | None,
    now: datetime,
    interval_seconds: float,
) -> bool:
    return _seconds_until_heartbeat_due(last_heartbeat_at, now, interval_seconds) <= 0


def _record_worker_heartbeat(
    *,
    connect: Callable[[], object],
    worker_id: str,
    build_version: str | None,
    process_started_at: datetime,
    heartbeat_at: datetime,
) -> bool:
    conn = None
    try:
        conn = connect()
        upsert_worker_heartbeat(
            conn,
            worker_name=PLAYBOOK_WORKER_NAME,
            worker_instance_id=worker_id,
            build_version=build_version,
            started_at=process_started_at,
            last_heartbeat_at=heartbeat_at,
        )
        conn.commit()
        return True
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                logger.warning(
                    "soar_playbook_worker_heartbeat_rollback_failed worker_id=%s",
                    worker_id,
                    exc_info=True,
                )
        logger.warning(
            "soar_playbook_worker_heartbeat_failed worker_id=%s",
            worker_id,
            exc_info=True,
        )
        return False
    finally:
        if conn is not None:
            _close_safely(conn, worker_id)


def _resolve_worker_build_version() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return None
    value = (result.stdout or "").strip()
    return value or None


def _sleep_if_needed(
    seconds: float,
    shutdown: PlaybookWorkerShutdown,
    sleeper: Callable[[float], None],
) -> None:
    if shutdown.requested or seconds <= 0:
        return
    sleeper(seconds)


def _rollback_safely(conn, worker_id: str) -> None:
    if conn is None:
        return
    try:
        conn.rollback()
    except Exception:
        logger.warning(
            "soar_playbook_worker_rollback_failed worker_id=%s",
            worker_id,
            exc_info=True,
        )


def _close_safely(conn, worker_id: str) -> None:
    if conn is None:
        return
    try:
        conn.close()
    except Exception:
        logger.warning(
            "soar_playbook_worker_close_failed worker_id=%s",
            worker_id,
            exc_info=True,
        )
