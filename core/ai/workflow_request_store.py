from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import uuid
from typing import Any

from psycopg2.extras import Json

from core.ai.soc_tools import redact_sensitive_values

WORKFLOW_REQUEST_WORKER_NAME = "anakin_workflow_worker"

ASYNC_WORKFLOW_DEEP_INVESTIGATE = "deep_investigate"
ASYNC_WORKFLOW_DECISION_SUPPORT = "decision_support"
ASYNC_WORKFLOW_GENERATE_ARTIFACT = "generate_artifact"
ASYNC_WORKFLOW_REPO_ASSISTANT = "repo_assistant"
ASYNC_WORKFLOW_NIST_EVIDENCE_EXPLANATION = "nist_evidence_explanation"
ASYNC_WORKFLOWS = frozenset(
    {
        ASYNC_WORKFLOW_DEEP_INVESTIGATE,
        ASYNC_WORKFLOW_DECISION_SUPPORT,
        ASYNC_WORKFLOW_GENERATE_ARTIFACT,
        ASYNC_WORKFLOW_NIST_EVIDENCE_EXPLANATION,
    }
)

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_PARTIAL = "partial"
STATUS_DEGRADED = "degraded"
STATUS_FAILED = "failed"
STATUS_TIMED_OUT = "timed_out"
STATUS_CANCELLED = "cancelled"
STATUS_EXPIRED = "expired"

ACTIVE_STATUSES = (STATUS_QUEUED, STATUS_RUNNING)
TERMINAL_STATUSES = (
    STATUS_COMPLETED,
    STATUS_PARTIAL,
    STATUS_DEGRADED,
    STATUS_FAILED,
    STATUS_TIMED_OUT,
    STATUS_CANCELLED,
    STATUS_EXPIRED,
)

STAGE_QUEUED = "queued"
STAGE_RUNNING = "running"
STAGE_GATHERING_CONTEXT = "gathering_context"
STAGE_RETRIEVING_EVIDENCE = "retrieving_evidence"
STAGE_QUERYING_TOOLS = "querying_tools"
STAGE_PREPARING_EVIDENCE = "preparing_evidence"
STAGE_GENERATING_ANALYSIS = "generating_analysis"
STAGE_VALIDATING_RESPONSE = "validating_response"
STAGE_COMPLETE = "complete"
STAGE_FAILED = "failed"
STAGE_RETRIEVING_REPOSITORY_EVIDENCE = "retrieving_repository_evidence"
STAGE_PREPARING_REPOSITORY_CONTEXT = "preparing_repository_context"
STAGE_GENERATING_ANSWER = "generating_answer"
STAGE_VALIDATING_CITATIONS = "validating_citations"

DEFAULT_LEASE_DURATION_SECONDS = 180
DEFAULT_MAX_ATTEMPTS = 1


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def idempotency_key_for_payload(payload: dict[str, Any], *, actor_username: str) -> str:
    explicit = str(payload.get("client_request_id") or payload.get("idempotency_key") or "").strip()
    if explicit:
        conversation = payload.get("conversation") if isinstance(payload.get("conversation"), dict) else {}
        execution = payload.get("_conversation_execution") if isinstance(payload.get("_conversation_execution"), dict) else {}
        thread_scope = str(conversation.get("thread_id") or execution.get("thread_id") or "stateless").strip()
        raw = f"{actor_username}:{thread_scope}:explicit:{explicit}"
    else:
        safe = redact_sensitive_values(payload)
        raw = f"{actor_username}:payload:{repr(_stable_jsonish(safe))}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_or_get_request(
    conn,
    *,
    workflow: str,
    context_type: str | None,
    payload: dict[str, Any],
    classification: dict[str, Any],
    actor_username: str,
    actor_role: str,
    idempotency_key: str | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    priority: int = 100,
    now: datetime | None = None,
) -> tuple[dict[str, Any], bool]:
    current = as_utc(now) or utc_now()
    key = (idempotency_key or idempotency_key_for_payload(payload, actor_username=actor_username)).strip()
    safe_payload = redact_sensitive_values(payload)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM ai_workflow_requests
            WHERE actor_username = %s
              AND idempotency_key = %s
              AND status IN ('queued', 'running')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (actor_username, key),
        )
        existing = _fetchone_dict(cur)
        if existing is not None:
            return existing, False

        request_id = f"aiwf_{uuid.uuid4().hex}"
        cur.execute(
            """
            INSERT INTO ai_workflow_requests (
                request_id, workflow, status, stage, context_type, idempotency_key,
                request_payload, classification, lifecycle, metadata, actor_username,
                actor_role, max_attempts, priority, not_before, queued_at, created_at, updated_at
            )
            VALUES (%s, %s, 'queued', 'queued', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                request_id,
                workflow,
                context_type,
                key,
                Json(safe_payload),
                Json(classification),
                Json(_lifecycle(STATUS_QUEUED, STAGE_QUEUED, workflow=workflow)),
                Json({"read_only": True, "async": True}),
                actor_username,
                actor_role,
                max(1, min(int(max_attempts), 5)),
                int(priority),
                current,
                current,
                current,
                current,
            ),
        )
        row = _fetchone_dict(cur)
    return row, True


def get_request(conn, request_id: str, *, actor_username: str | None = None) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        if actor_username:
            cur.execute(
                "SELECT * FROM ai_workflow_requests WHERE request_id = %s AND actor_username = %s",
                (request_id, actor_username),
            )
        else:
            cur.execute("SELECT * FROM ai_workflow_requests WHERE request_id = %s", (request_id,))
        return _fetchone_dict(cur)


def claim_next_request(
    conn,
    *,
    lease_owner: str,
    now: datetime | None = None,
    lease_duration_seconds: int = DEFAULT_LEASE_DURATION_SECONDS,
) -> dict[str, Any] | None:
    owner = (lease_owner or "").strip()
    if not owner:
        raise ValueError("lease_owner is required")
    current = as_utc(now) or utc_now()
    expires = current + timedelta(seconds=max(1, int(lease_duration_seconds)))
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH candidate AS (
                SELECT id
                FROM ai_workflow_requests
                WHERE status = 'queued'
                  AND not_before <= %s
                ORDER BY priority ASC, id ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            UPDATE ai_workflow_requests AS requests
            SET status = 'running',
                stage = 'running',
                attempt_count = attempt_count + 1,
                lease_owner = %s,
                lease_acquired_at = %s,
                lease_heartbeat_at = %s,
                lease_expires_at = %s,
                started_at = COALESCE(started_at, %s),
                lifecycle = %s,
                updated_at = %s
            FROM candidate
            WHERE requests.id = candidate.id
            RETURNING requests.*
            """,
            (
                current,
                owner,
                current,
                current,
                expires,
                current,
                Json(_lifecycle(STATUS_RUNNING, STAGE_RUNNING)),
                current,
            ),
        )
        return _fetchone_dict(cur)


def update_request_stage(
    conn,
    request_id: str,
    *,
    lease_owner: str,
    stage: str,
    status: str = STATUS_RUNNING,
    metadata: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    current = as_utc(now) or utc_now()
    workflow = _request_workflow_for_lease(conn, request_id, lease_owner=lease_owner)
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE ai_workflow_requests
            SET status = %s,
                stage = %s,
                lifecycle = %s,
                metadata = metadata || %s,
                lease_heartbeat_at = %s,
                updated_at = %s
            WHERE request_id = %s
              AND lease_owner = %s
              AND status = 'running'
            RETURNING *
            """,
            (
                status,
                stage,
                Json(_lifecycle(status, stage, workflow=workflow)),
                Json(metadata or {}),
                current,
                current,
                request_id,
                lease_owner,
            ),
        )
        return _fetchone_dict(cur)


def heartbeat_request(
    conn,
    request_id: str,
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
            UPDATE ai_workflow_requests
            SET lease_heartbeat_at = %s,
                lease_expires_at = %s,
                updated_at = %s
            WHERE request_id = %s
              AND lease_owner = %s
              AND status = 'running'
            RETURNING *
            """,
            (current, expires, current, request_id, lease_owner),
        )
        return _fetchone_dict(cur)


def complete_request(
    conn,
    request_id: str,
    *,
    lease_owner: str,
    status: str,
    result_payload: dict[str, Any] | None,
    metadata: dict[str, Any] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    current = as_utc(now) or utc_now()
    final_stage = STAGE_COMPLETE if status in {STATUS_COMPLETED, STATUS_PARTIAL, STATUS_DEGRADED} else STAGE_FAILED
    workflow = _request_workflow_for_lease(conn, request_id, lease_owner=lease_owner)
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE ai_workflow_requests
            SET status = %s,
                stage = %s,
                result_payload = %s,
                metadata = metadata || %s,
                lifecycle = %s,
                error_code = %s,
                error_message = %s,
                completed_at = %s,
                lease_owner = NULL,
                lease_acquired_at = NULL,
                lease_heartbeat_at = NULL,
                lease_expires_at = NULL,
                updated_at = %s
            WHERE request_id = %s
              AND lease_owner = %s
              AND status = 'running'
            RETURNING *
            """,
            (
                status,
                final_stage,
                Json(result_payload) if result_payload is not None else None,
                Json(metadata or {}),
                Json(_lifecycle(status, final_stage, workflow=workflow)),
                error_code,
                (error_message or "")[:1000] if error_message else None,
                current,
                current,
                request_id,
                lease_owner,
            ),
        )
        return _fetchone_dict(cur)


def fail_request(
    conn,
    request_id: str,
    *,
    lease_owner: str,
    error_code: str,
    error_message: str,
    status: str = STATUS_FAILED,
    result_payload: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    return complete_request(
        conn,
        request_id,
        lease_owner=lease_owner,
        status=status,
        result_payload=result_payload,
        metadata={"error_code": error_code},
        error_code=error_code,
        error_message=error_message,
        now=now,
    )


def recover_stale_requests(
    conn,
    *,
    now: datetime | None = None,
    limit: int = 25,
) -> dict[str, int]:
    current = as_utc(now) or utc_now()
    recovered = 0
    failed = 0
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, attempt_count, max_attempts
            FROM ai_workflow_requests
            WHERE status = 'running'
              AND lease_expires_at IS NOT NULL
              AND lease_expires_at <= %s
            ORDER BY lease_expires_at ASC, id ASC
            LIMIT %s
            FOR UPDATE SKIP LOCKED
            """,
            (current, max(0, int(limit))),
        )
        rows = cur.fetchall()
        for row_id, attempt_count, max_attempts in rows:
            if int(attempt_count) < int(max_attempts):
                cur.execute(
                    """
                    UPDATE ai_workflow_requests
                    SET status = 'queued',
                        stage = 'queued',
                        recovery_count = recovery_count + 1,
                        lease_owner = NULL,
                        lease_acquired_at = NULL,
                        lease_heartbeat_at = NULL,
                        lease_expires_at = NULL,
                        lifecycle = %s,
                        error_code = 'stale_lease_recovered',
                        error_message = 'stale workflow lease recovered for retry',
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (Json(_lifecycle(STATUS_QUEUED, STAGE_QUEUED)), current, row_id),
                )
                recovered += 1
            else:
                cur.execute(
                    """
                    UPDATE ai_workflow_requests
                    SET status = 'timed_out',
                        stage = 'failed',
                        recovery_count = recovery_count + 1,
                        lease_owner = NULL,
                        lease_acquired_at = NULL,
                        lease_heartbeat_at = NULL,
                        lease_expires_at = NULL,
                        lifecycle = %s,
                        error_code = 'stale_lease_expired',
                        error_message = 'stale workflow lease exceeded max attempts',
                        completed_at = %s,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (Json(_lifecycle(STATUS_TIMED_OUT, STAGE_FAILED)), current, current, row_id),
                )
                failed += 1
    return {"recovered": recovered, "failed": failed}


def serialize_request(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    result_payload = row.get("result_payload") if isinstance(row.get("result_payload"), dict) else None
    result = result_payload.get("result") if isinstance(result_payload, dict) else None
    if result is None and row.get("workflow") == ASYNC_WORKFLOW_REPO_ASSISTANT and isinstance(result_payload, dict):
        result = result_payload
    metadata = dict(row.get("metadata") or {})
    if isinstance(result_payload, dict) and isinstance(result_payload.get("metadata"), dict):
        metadata = {**result_payload.get("metadata"), **metadata}
    metadata.update({"async": True, "request_id": row.get("request_id")})
    error = row.get("error_message")
    if isinstance(result_payload, dict) and result_payload.get("error"):
        error = result_payload.get("error")
    return {
        "request_id": row.get("request_id"),
        "thread_id": row.get("thread_id"),
        "turn_id": row.get("turn_id"),
        "status": row.get("status"),
        "workflow": row.get("workflow"),
        "classification": row.get("classification") or {},
        "lifecycle": row.get("lifecycle") or _lifecycle(row.get("status") or STATUS_QUEUED, row.get("stage") or STAGE_QUEUED, workflow=row.get("workflow")),
        "result": result,
        "metadata": metadata,
        "error": error,
        "error_code": row.get("error_code"),
        "timestamps": {
            "queued_at": _iso(row.get("queued_at")),
            "started_at": _iso(row.get("started_at")),
            "completed_at": _iso(row.get("completed_at")),
            "updated_at": _iso(row.get("updated_at")),
        },
        "terminal": row.get("status") in TERMINAL_STATUSES,
        "read_only": True,
    }


def _fetchone_dict(cur) -> dict[str, Any] | None:
    row = cur.fetchone()
    if row is None:
        return None
    columns = [desc[0] for desc in cur.description]
    return dict(zip(columns, row))


def _request_workflow_for_lease(conn, request_id: str, *, lease_owner: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT workflow
            FROM ai_workflow_requests
            WHERE request_id = %s
              AND lease_owner = %s
              AND status = 'running'
            """,
            (request_id, lease_owner),
        )
        row = cur.fetchone()
    return str(row[0]) if row and row[0] else None


def _lifecycle(status: str, stage: str, *, workflow: str | None = None) -> dict[str, Any]:
    terminal = status in TERMINAL_STATUSES
    stages = []
    order = [
        STAGE_QUEUED,
        STAGE_RUNNING,
        STAGE_GATHERING_CONTEXT,
        STAGE_RETRIEVING_EVIDENCE,
        STAGE_QUERYING_TOOLS,
        STAGE_PREPARING_EVIDENCE,
        STAGE_GENERATING_ANALYSIS,
        STAGE_VALIDATING_RESPONSE,
        STAGE_COMPLETE,
    ]
    if workflow == ASYNC_WORKFLOW_NIST_EVIDENCE_EXPLANATION:
        order = [
            STAGE_QUEUED,
            STAGE_RUNNING,
            STAGE_GATHERING_CONTEXT,
            STAGE_RETRIEVING_EVIDENCE,
            STAGE_PREPARING_EVIDENCE,
            STAGE_GENERATING_ANALYSIS,
            STAGE_VALIDATING_RESPONSE,
            STAGE_COMPLETE,
        ]
    elif workflow == ASYNC_WORKFLOW_REPO_ASSISTANT or stage in {
        STAGE_RETRIEVING_REPOSITORY_EVIDENCE,
        STAGE_PREPARING_REPOSITORY_CONTEXT,
        STAGE_GENERATING_ANSWER,
        STAGE_VALIDATING_CITATIONS,
    }:
        order = [
            STAGE_QUEUED,
            STAGE_RUNNING,
            STAGE_RETRIEVING_REPOSITORY_EVIDENCE,
            STAGE_PREPARING_REPOSITORY_CONTEXT,
            STAGE_GENERATING_ANSWER,
            STAGE_VALIDATING_CITATIONS,
            STAGE_COMPLETE,
        ]
    if stage not in order and stage != STAGE_FAILED:
        stage = STAGE_RUNNING if status == STATUS_RUNNING else STAGE_QUEUED
    for item in order:
        if terminal and status in {STATUS_COMPLETED, STATUS_PARTIAL, STATUS_DEGRADED}:
            item_status = "complete"
        elif stage == STAGE_FAILED:
            item_status = "failed" if item == STAGE_RUNNING else "pending"
        elif item == stage:
            item_status = "running" if not terminal else "complete"
        elif order.index(item) < order.index(stage if stage in order else STAGE_RUNNING):
            item_status = "complete"
        else:
            item_status = "pending"
        stages.append({"stage": item, "status": item_status})
    return {"mode": "polling", "status": status, "stage": stage, "terminal": terminal, "stages": stages}


def _iso(value: Any) -> str | None:
    if not isinstance(value, datetime):
        return None
    return value.astimezone(timezone.utc).isoformat()


def _stable_jsonish(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _stable_jsonish(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_stable_jsonish(item) for item in value]
    return value
