from __future__ import annotations

from typing import Any

from core.ai.repo_assistant_service import RepoAssistantValidationError, repo_scope_boundary_response
from core.ai.workflow_request_store import (
    ASYNC_WORKFLOW_REPO_ASSISTANT,
    create_or_get_request,
    get_request,
    idempotency_key_for_payload,
    serialize_request,
)
from core.db import get_db_connection


def queue_repo_assistant_request(payload: dict[str, Any], *, actor_username: str, actor_role: str) -> tuple[dict[str, Any], int]:
    if not isinstance(payload, dict):
        raise RepoAssistantValidationError("JSON object body is required.")

    boundary = repo_scope_boundary_response(payload)
    if boundary is not None:
        body = dict(boundary.payload)
        body.setdefault("metadata", {})
        if isinstance(body["metadata"], dict):
            body["metadata"] = {
                **body["metadata"],
                "async": False,
                "request_route": "POST /ai/repo/requests",
                "immediate": True,
            }
        return body, boundary.status_code

    request_payload = {**payload, "workflow": ASYNC_WORKFLOW_REPO_ASSISTANT}
    classification = {
        "requested_workflow": ASYNC_WORKFLOW_REPO_ASSISTANT,
        "classified_workflow": ASYNC_WORKFLOW_REPO_ASSISTANT,
        "confidence": "explicit",
        "reason": "Explicit Repo Assistant request route.",
        "chooser_required": False,
    }
    key = idempotency_key_for_payload(request_payload, actor_username=actor_username)
    conn = None
    try:
        conn = get_db_connection()
        row, created = create_or_get_request(
            conn,
            workflow=ASYNC_WORKFLOW_REPO_ASSISTANT,
            context_type="repository",
            payload=request_payload,
            classification=classification,
            actor_username=actor_username,
            actor_role=actor_role,
            idempotency_key=key,
            max_attempts=1,
            priority=80,
        )
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

    serialized = serialize_request(row) or {}
    serialized["created"] = created
    return serialized, 202 if created else 200


def read_repo_assistant_request(request_id: str, *, actor_username: str) -> tuple[dict[str, Any], int]:
    conn = None
    try:
        conn = get_db_connection()
        row = get_request(conn, request_id, actor_username=actor_username)
    finally:
        if conn:
            conn.close()
    if row is None or row.get("workflow") != ASYNC_WORKFLOW_REPO_ASSISTANT:
        return {"status": "not_found", "error": "Repo Assistant request not found."}, 404
    return serialize_request(row) or {"status": "not_found", "error": "Repo Assistant request not found."}, 200
