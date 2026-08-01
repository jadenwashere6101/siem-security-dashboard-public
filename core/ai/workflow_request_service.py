from __future__ import annotations

from typing import Any

from core.ai.workflow_orchestrator import (
    WORKFLOW_AUTO,
    WORKFLOW_DEEP_INVESTIGATE,
    WORKFLOW_DECISION_SUPPORT,
    WORKFLOW_GENERATE_ARTIFACT,
    WORKFLOW_QUICK_EXPLAIN,
    WorkflowValidationError,
    classify_workflow,
    run_workflow,
)
from core.ai.workflow_request_store import (
    ASYNC_WORKFLOWS,
    create_or_get_request,
    get_request,
    idempotency_key_for_payload,
    serialize_request,
)
from core.db import get_db_connection

FORBIDDEN_ASYNC_FIELDS = frozenset(
    {
        "action_type",
        "apply",
        "approve",
        "confirm",
        "confirmation_token",
        "payload_digest",
        "target_fingerprint",
    }
)

FORBIDDEN_DECISION_FIELDS = frozenset(
    {
        "artifact",
        "artifact_type",
        "draft_type",
        "draftType",
        "preview",
        "confirm",
        "confirmation_token",
        "payload_digest",
        "target_fingerprint",
    }
)


def queue_workflow_request(payload: dict[str, Any], *, actor_username: str, actor_role: str) -> tuple[dict[str, Any], int]:
    if not isinstance(payload, dict):
        raise WorkflowValidationError("JSON object body is required.")
    classification = classify_workflow(payload)
    workflow = classification.classified_workflow
    requested_workflow = str(payload.get("workflow") or "").strip().lower()
    if classification.chooser_required:
        return (
            {
                "status": "chooser_required",
                "workflow": workflow,
                "classification": classification.as_dict(),
                "lifecycle": {
                    "mode": "polling",
                    "status": "chooser_required",
                    "stage": "queued",
                    "terminal": True,
                    "stages": [],
                },
                "result": {"allowed_workflows": list(classification.allowed_workflows)},
                "metadata": {},
                "error": None,
            },
            200,
        )
    if requested_workflow == WORKFLOW_AUTO and workflow == WORKFLOW_QUICK_EXPLAIN:
        result = run_workflow(payload)
        quick_payload = dict(result.payload)
        quick_payload.setdefault("metadata", {})
        if isinstance(quick_payload["metadata"], dict):
            quick_payload["metadata"] = {
                **quick_payload["metadata"],
                "async": False,
                "request_route": "POST /ai/workflows/requests",
                "immediate": True,
            }
        return quick_payload, result.status_code
    if workflow not in ASYNC_WORKFLOWS:
        raise WorkflowValidationError(
            f"Workflow {workflow} is not available through async workflow requests.",
            status_code=400,
            error_code="workflow_not_async",
        )
    if any(field in payload for field in FORBIDDEN_ASYNC_FIELDS):
        raise WorkflowValidationError(
            "Async workflow requests cannot preview, confirm, apply, or mutate state.",
            error_code="async_workflow_read_only",
        )
    if workflow == WORKFLOW_DECISION_SUPPORT and any(field in payload for field in FORBIDDEN_DECISION_FIELDS):
        raise WorkflowValidationError(
            "Decision Support cannot generate artifacts, preview actions, confirm actions, or mutate state.",
            error_code="decision_support_read_only",
        )
    if workflow == WORKFLOW_GENERATE_ARTIFACT:
        artifact = payload.get("artifact") if isinstance(payload.get("artifact"), dict) else {}
        draft_type = payload.get("draft_type") or payload.get("draftType") or payload.get("artifact_type") or artifact.get("type")
        if not draft_type:
            raise WorkflowValidationError(
                "Generate Artifact requires artifact.type or draft_type.",
                error_code="artifact_type_required",
            )
    if workflow in {WORKFLOW_DEEP_INVESTIGATE, WORKFLOW_GENERATE_ARTIFACT} and not payload.get("context_type"):
        raise WorkflowValidationError("context_type is required.", error_code="context_type_required")

    key = idempotency_key_for_payload(payload, actor_username=actor_username)
    conn = None
    try:
        conn = get_db_connection()
        row, created = create_or_get_request(
            conn,
            workflow=workflow,
            context_type=payload.get("context_type"),
            payload=payload,
            classification=classification.as_dict(),
            actor_username=actor_username,
            actor_role=actor_role,
            idempotency_key=key,
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


def read_workflow_request(request_id: str, *, actor_username: str) -> tuple[dict[str, Any], int]:
    conn = None
    try:
        conn = get_db_connection()
        row = get_request(conn, request_id, actor_username=actor_username)
    finally:
        if conn:
            conn.close()
    if row is None:
        return {"status": "not_found", "error": "Workflow request not found."}, 404
    return serialize_request(row) or {"status": "not_found", "error": "Workflow request not found."}, 200
