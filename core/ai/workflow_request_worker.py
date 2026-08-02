from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
import signal
import time
from typing import Callable

from flask_login import login_user

from core.ai.repo_assistant_service import answer_repo_question
from core.auth import User
from core.ai.workflow_orchestrator import run_workflow
from core.ai.workflow_request_store import (
    ASYNC_WORKFLOW_REPO_ASSISTANT,
    STATUS_COMPLETED,
    STATUS_DEGRADED,
    STATUS_FAILED,
    STATUS_PARTIAL,
    STATUS_TIMED_OUT,
    STAGE_GATHERING_CONTEXT,
    STAGE_GENERATING_ANALYSIS,
    STAGE_GENERATING_ANSWER,
    STAGE_QUERYING_TOOLS,
    STAGE_PREPARING_REPOSITORY_CONTEXT,
    STAGE_RETRIEVING_REPOSITORY_EVIDENCE,
    STAGE_RETRIEVING_EVIDENCE,
    STAGE_VALIDATING_CITATIONS,
    STAGE_VALIDATING_RESPONSE,
    WORKFLOW_REQUEST_WORKER_NAME,
    claim_next_request,
    complete_request,
    fail_request,
    heartbeat_request,
    recover_stale_requests,
    update_request_stage,
    utc_now,
)
from core.db import get_db_connection
from core.worker_heartbeat_store import WORKER_HEARTBEAT_INTERVAL_SECONDS, upsert_worker_heartbeat

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 3
DEFAULT_MAX_RUNTIME_SECONDS = 240
DEFAULT_STALE_RECOVERY_LIMIT = 25
DEFAULT_LEASE_DURATION_SECONDS = 240


@dataclass(frozen=True)
class AnakinWorkflowWorkerConfig:
    batch_size: int = DEFAULT_BATCH_SIZE
    stale_recovery_limit: int = DEFAULT_STALE_RECOVERY_LIMIT
    max_runtime_seconds: int = DEFAULT_MAX_RUNTIME_SECONDS
    lease_duration_seconds: int = DEFAULT_LEASE_DURATION_SECONDS
    heartbeat_interval_seconds: int = WORKER_HEARTBEAT_INTERVAL_SECONDS


class AnakinWorkflowWorkerShutdown:
    def __init__(self) -> None:
        self.requested = False
        self.reason = "not_requested"

    def request(self, reason: str = "requested") -> None:
        self.requested = True
        self.reason = reason


def install_shutdown_signal_handlers(shutdown: AnakinWorkflowWorkerShutdown) -> None:
    def _handle_signal(signum, _frame) -> None:
        shutdown.request(f"signal_{signum}")

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)


def run_anakin_workflow_worker(
    *,
    config: AnakinWorkflowWorkerConfig | None = None,
    worker_id: str | None = None,
    shutdown: AnakinWorkflowWorkerShutdown | None = None,
    connect: Callable[[], object] = get_db_connection,
    now_fn: Callable[[], datetime] | None = None,
    flask_app=None,
) -> dict:
    cfg = _normalize_config(config)
    state = shutdown or AnakinWorkflowWorkerShutdown()
    owner = (worker_id or "").strip() or f"{WORKFLOW_REQUEST_WORKER_NAME}-{int(time.time())}"
    clock = now_fn or utc_now
    started_at = clock()
    deadline = time.monotonic() + cfg.max_runtime_seconds
    stats = {
        "worker_name": WORKFLOW_REQUEST_WORKER_NAME,
        "worker_id": owner,
        "processed": 0,
        "success": 0,
        "partial": 0,
        "degraded": 0,
        "failed": 0,
        "timed_out": 0,
        "recovered": 0,
        "recovery_failed": 0,
        "errors": 0,
        "shutdown_reason": "complete",
    }
    conn = None
    try:
        conn = connect()
        heartbeat = upsert_worker_heartbeat(
            conn,
            worker_name=WORKFLOW_REQUEST_WORKER_NAME,
            worker_instance_id=owner,
            started_at=started_at,
            last_heartbeat_at=started_at,
        )
        recovery = recover_stale_requests(conn, now=clock(), limit=cfg.stale_recovery_limit)
        stats["recovered"] = recovery["recovered"]
        stats["recovery_failed"] = recovery["failed"]
        conn.commit()
        last_heartbeat = time.monotonic()

        while stats["processed"] < cfg.batch_size and not state.requested and time.monotonic() < deadline:
            _maybe_heartbeat(conn, owner, started_at, cfg, last_heartbeat, clock)
            last_heartbeat = time.monotonic()
            job = claim_next_request(
                conn,
                lease_owner=owner,
                now=clock(),
                lease_duration_seconds=cfg.lease_duration_seconds,
            )
            conn.commit()
            if job is None:
                break
            outcome = _process_request(
                conn,
                job,
                lease_owner=owner,
                lease_duration_seconds=cfg.lease_duration_seconds,
                clock=clock,
                flask_app=flask_app,
            )
            conn.commit()
            stats["processed"] += 1
            stats[outcome] = stats.get(outcome, 0) + 1
        if state.requested:
            stats["shutdown_reason"] = state.reason
    except Exception:
        if conn:
            conn.rollback()
        logger.exception("anakin_workflow_worker_failed worker_id=%s", owner)
        stats["errors"] += 1
        stats["shutdown_reason"] = "error"
    finally:
        if conn:
            conn.close()
    return stats


def _process_request(
    conn,
    job: dict,
    *,
    lease_owner: str,
    lease_duration_seconds: int,
    clock: Callable[[], datetime],
    flask_app=None,
) -> str:
    request_id = job["request_id"]
    payload = job.get("request_payload") if isinstance(job.get("request_payload"), dict) else {}
    try:
        update_request_stage(conn, request_id, lease_owner=lease_owner, stage=STAGE_GATHERING_CONTEXT, now=clock())
        conn.commit()
        workflow = job.get("workflow")
        if workflow == ASYNC_WORKFLOW_REPO_ASSISTANT:
            update_request_stage(conn, request_id, lease_owner=lease_owner, stage=STAGE_RETRIEVING_REPOSITORY_EVIDENCE, now=clock())
            conn.commit()
            update_request_stage(conn, request_id, lease_owner=lease_owner, stage=STAGE_PREPARING_REPOSITORY_CONTEXT, now=clock())
            conn.commit()
            update_request_stage(conn, request_id, lease_owner=lease_owner, stage=STAGE_GENERATING_ANSWER, now=clock())
            conn.commit()
        elif workflow == "deep_investigate":
            update_request_stage(conn, request_id, lease_owner=lease_owner, stage=STAGE_RETRIEVING_EVIDENCE, now=clock())
            conn.commit()
            update_request_stage(conn, request_id, lease_owner=lease_owner, stage=STAGE_QUERYING_TOOLS, now=clock())
            conn.commit()
        if workflow != ASYNC_WORKFLOW_REPO_ASSISTANT:
            update_request_stage(conn, request_id, lease_owner=lease_owner, stage=STAGE_GENERATING_ANALYSIS, now=clock())
        heartbeat_request(
            conn,
            request_id,
            lease_owner=lease_owner,
            now=clock(),
            lease_duration_seconds=lease_duration_seconds,
        )
        conn.commit()
        result = _run_with_user_context(
            payload,
            workflow=workflow,
            actor_username=job["actor_username"],
            actor_role=job["actor_role"],
            flask_app=flask_app,
        )
        update_request_stage(
            conn,
            request_id,
            lease_owner=lease_owner,
            stage=STAGE_VALIDATING_CITATIONS if workflow == ASYNC_WORKFLOW_REPO_ASSISTANT else STAGE_VALIDATING_RESPONSE,
            now=clock(),
        )
        status = _terminal_status_for_result(result.payload, result.status_code)
        error_code, error_message = _error_fields(result.payload)
        completed = complete_request(
            conn,
            request_id,
            lease_owner=lease_owner,
            status=status,
            result_payload=result.payload,
            metadata={"http_status_code": result.status_code},
            error_code=error_code,
            error_message=error_message,
            now=clock(),
        )
        if completed is None:
            raise RuntimeError("owner-matched async workflow completion failed")
        return _stats_key(status)
    except Exception as error:
        logger.exception("anakin_workflow_request_failed request_id=%s", request_id)
        failed = fail_request(
            conn,
            request_id,
            lease_owner=lease_owner,
            error_code=type(error).__name__,
            error_message=str(error),
            now=clock(),
        )
        if failed is None:
            raise
        return "failed"


def _run_with_user_context(payload: dict, *, workflow: str | None = None, actor_username: str, actor_role: str, flask_app=None):
    app = flask_app
    if app is None:
        from siem_backend import app as app

    with app.test_request_context("/ai/workflows/requests/worker", method="POST", json={}):
        login_user(User(actor_username, role=actor_role))
        if workflow == ASYNC_WORKFLOW_REPO_ASSISTANT:
            return answer_repo_question(payload)
        return run_workflow(payload)


def _terminal_status_for_result(payload: dict, status_code: int) -> str:
    raw = str((payload or {}).get("status") or "").lower()
    nested = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    nested_status = str(nested.get("status") or "").lower()
    status = nested_status or raw
    if status_code >= 500:
        return STATUS_FAILED
    if status in {"success", "completed", "complete"}:
        return STATUS_COMPLETED
    if status in {"partial"}:
        return STATUS_PARTIAL
    if status in {"degraded", "insufficient_context"}:
        return STATUS_DEGRADED
    if "timeout" in status or status in {"timed_out", "provider_timeout"}:
        return STATUS_TIMED_OUT
    return STATUS_FAILED if status_code >= 400 or status in {"failed", "invalid_request", "validation_failed"} else STATUS_COMPLETED


def _error_fields(payload: dict) -> tuple[str | None, str | None]:
    nested = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    nested_metadata = nested.get("metadata") if isinstance(nested.get("metadata"), dict) else {}
    code = payload.get("error_code") or nested.get("error_code") or metadata.get("error_code") or nested_metadata.get("error_code")
    message = payload.get("error") or nested.get("error")
    return (str(code) if code else None, str(message) if message else None)


def _stats_key(status: str) -> str:
    if status == STATUS_COMPLETED:
        return "success"
    if status == STATUS_PARTIAL:
        return "partial"
    if status == STATUS_DEGRADED:
        return "degraded"
    if status == STATUS_TIMED_OUT:
        return "timed_out"
    return "failed"


def _normalize_config(config: AnakinWorkflowWorkerConfig | None) -> AnakinWorkflowWorkerConfig:
    raw = config or AnakinWorkflowWorkerConfig()
    return AnakinWorkflowWorkerConfig(
        batch_size=_clamp(raw.batch_size, 1, 20, DEFAULT_BATCH_SIZE),
        stale_recovery_limit=_clamp(raw.stale_recovery_limit, 0, 200, DEFAULT_STALE_RECOVERY_LIMIT),
        max_runtime_seconds=_clamp(raw.max_runtime_seconds, 30, 900, DEFAULT_MAX_RUNTIME_SECONDS),
        lease_duration_seconds=_clamp(raw.lease_duration_seconds, 60, 1200, DEFAULT_LEASE_DURATION_SECONDS),
        heartbeat_interval_seconds=_clamp(raw.heartbeat_interval_seconds, 1, 300, WORKER_HEARTBEAT_INTERVAL_SECONDS),
    )


def _clamp(value: int, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _maybe_heartbeat(conn, owner: str, started_at: datetime, cfg: AnakinWorkflowWorkerConfig, last_heartbeat: float, clock) -> None:
    if time.monotonic() - last_heartbeat < cfg.heartbeat_interval_seconds:
        return
    upsert_worker_heartbeat(
        conn,
        worker_name=WORKFLOW_REQUEST_WORKER_NAME,
        worker_instance_id=owner,
        started_at=started_at,
        last_heartbeat_at=clock(),
    )
