from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from core.ai.agentic_analyst_planner import (
    AgenticAnalystPlan,
    PlannerOutcome,
    build_planner_packet,
    deterministic_shortcut_plan,
    plan_turn,
)
from core.ai.config import load_ai_gateway_config
from core.ai.conversation_context import (
    ConversationSelection,
    ConversationContextError,
    conversation_budget,
    select_conversation_context,
)
from core.ai.session_memory_service import validate_conversation_entity, validate_owned_thread
from core.ai.session_memory_store import (
    SessionMemoryError,
    SessionMemoryValidationError,
    ThreadVersionConflictError,
    append_turn,
    create_evidence,
    fail_execution_turn,
    finalize_execution_turn,
    get_thread,
    get_turn_by_client_request,
    get_turn_by_id,
    linked_workflow_request_for_turn,
    link_async_request,
    serialize_turn,
    utc_now,
)
from core.ai.workflow_orchestrator import (
    WORKFLOW_PROFILES,
    WORKFLOW_AUTO,
    WORKFLOW_LATENCY_TARGETS,
    WORKFLOW_QUICK_EXPLAIN,
    WorkflowClassification,
    WorkflowResult,
    WorkflowValidationError,
    classify_workflow,
    run_workflow,
)
from core.ai.workflow_request_store import create_or_get_request, serialize_request
from core.auth import User
from core.db import get_db_connection


CONVERSATION_WORKFLOWS = frozenset(
    {"quick_explain", "deep_investigate", "decision_support", "generate_artifact"}
)
ASYNC_CONVERSATION_WORKFLOWS = frozenset({"deep_investigate", "decision_support", "generate_artifact"})
ISOLATED_WORKFLOWS = frozenset({"repo_assistant", "soc_briefing"})


class ConversationOrchestrationError(SessionMemoryError):
    error_code = "conversation_orchestration_error"


class ConversationBoundaryError(ConversationOrchestrationError):
    status_code = 400
    error_code = "conversation_workflow_boundary"


class ConversationActorUnavailableError(ConversationOrchestrationError):
    status_code = 403
    error_code = "conversation_actor_unavailable"


@dataclass(frozen=True)
class ResolvedExecutionContext:
    active_entity: dict[str, Any] | None
    entities: tuple[dict[str, Any], ...]
    comparison_entities: tuple[dict[str, Any], ...]
    context_type: str
    context: dict[str, Any]
    entity_snapshot: dict[str, Any]
    resolution: dict[str, Any]
    source: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "active_entity": dict(self.active_entity) if self.active_entity else None,
            "entities": [dict(item) for item in self.entities],
            "comparison_entities": [dict(item) for item in self.comparison_entities],
            "context_type": self.context_type,
            "context": dict(self.context),
            "entity_snapshot": dict(self.entity_snapshot),
            "resolution": dict(self.resolution),
            "source": self.source,
        }


@dataclass(frozen=True)
class AssistantTerminalContent:
    content: str
    category: str
    result_status: str
    missing_sections: tuple[str, ...] = ()
    provider_status: str | None = None
    error: str | None = None


_TURN_CONTEXT_IDENTITY_FIELDS = (
    "alert_id",
    "incident_id",
    "source_ip",
    "host",
    "hostname",
    "user",
    "username",
    "activity_id",
    "recon_activity_id",
    "registry_id",
    "investigation_id",
)


def has_conversation_envelope(payload: Any) -> bool:
    return isinstance(payload, dict) and payload.get("conversation") is not None


def reject_isolated_conversation(payload: dict[str, Any], *, workflow: str) -> None:
    if workflow in ISOLATED_WORKFLOWS and has_conversation_envelope(payload):
        raise ConversationBoundaryError(f"{workflow.replace('_', ' ').title()} cannot use SIEM conversation memory.")


def validate_original_conversation_workflow(payload: dict[str, Any]) -> str:
    """Validate the client-requested namespace before planning can transform it."""
    requested = str(payload.get("workflow") or WORKFLOW_AUTO).strip().lower() or WORKFLOW_AUTO
    if requested in ISOLATED_WORKFLOWS:
        raise ConversationBoundaryError(
            f"{requested.replace('_', ' ').title()} cannot use SIEM conversation memory."
        )
    if requested != WORKFLOW_AUTO and requested not in CONVERSATION_WORKFLOWS:
        raise WorkflowValidationError("workflow is unsupported.", error_code="unsupported_workflow")
    return requested


def run_conversational_workflow(
    payload: dict[str, Any],
    *,
    owner_username: str,
    actor_role: str,
    gateway=None,
    config=None,
    planned: dict[str, Any] | None = None,
) -> WorkflowResult:
    if not has_conversation_envelope(payload):
        return run_workflow(payload, gateway=gateway, config=config)
    validate_original_conversation_workflow(payload)
    planning = planned or plan_conversational_submission(
        payload,
        owner_username=owner_username,
        gateway=gateway,
        config=config,
    )
    classification = planning["classification"]
    workflow = classification.classified_workflow
    reject_isolated_conversation(payload, workflow=workflow)
    if workflow != WORKFLOW_QUICK_EXPLAIN:
        raise ConversationBoundaryError("Conversational long-running workflows must use the async request route.")
    resolved_config = config if config is not None else load_ai_gateway_config()
    prepared = _prepare_submission(
        payload,
        workflow=workflow,
        owner_username=owner_username,
        classification=classification,
        resolved_config=resolved_config,
        planner_outcome=planning["outcome"],
    )
    if prepared.get("duplicate_result") is not None:
        return WorkflowResult(prepared["duplicate_result"], 200)
    if prepared.get("deterministic_result") is not None:
        return WorkflowResult(prepared["deterministic_result"], 200)
    execution_payload = _with_context(prepared["execution_payload"], prepared["selection"].packet)
    _assert_execution_alignment(execution_payload, prepared["resolved_context"], prepared["selection"].packet)
    try:
        result = run_workflow(execution_payload, gateway=gateway, config=resolved_config)
        return _complete_sync(prepared, result)
    except Exception:
        _fail_prepared_turn(prepared)
        raise


def queue_conversational_request(
    payload: dict[str, Any],
    *,
    classification: WorkflowClassification,
    actor_username: str,
    actor_role: str,
    planned: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], int]:
    validate_original_conversation_workflow(payload)
    planning = planned or plan_conversational_submission(payload, owner_username=actor_username)
    classification = planning["classification"]
    workflow = classification.classified_workflow
    reject_isolated_conversation(payload, workflow=workflow)
    non_executing = planning["outcome"].plan is None or planning["outcome"].plan.proposed_strategy in {
        "clarification_required",
        "unsupported_or_boundary",
    }
    if workflow not in ASYNC_CONVERSATION_WORKFLOWS and not non_executing:
        raise ConversationBoundaryError("The selected workflow is not an asynchronous conversation workflow.")
    resolved_config = load_ai_gateway_config()
    prepared = _prepare_submission(
        payload,
        workflow=workflow,
        owner_username=actor_username,
        classification=classification,
        resolved_config=resolved_config,
        create_async_request=True,
        actor_role=actor_role,
        planner_outcome=planning["outcome"],
    )
    if prepared.get("deterministic_result") is not None:
        return prepared["deterministic_result"], 200
    request_row = prepared.get("request")
    serialized = serialize_request(request_row) or {}
    serialized.update(
        {
            "created": prepared["request_created"],
            "conversation": _conversation_metadata(
                prepared["thread"],
                prepared["user_turn"],
                assistant_turn=None,
                selection=prepared["selection"],
            ),
        }
    )
    return serialized, 202 if prepared["request_created"] else 200


def plan_conversational_submission(
    payload: dict[str, Any],
    *,
    owner_username: str,
    gateway=None,
    config=None,
) -> dict[str, Any]:
    """Build and execute a read-only planning snapshot without holding a DB lock."""
    if not has_conversation_envelope(payload):
        raise ConversationBoundaryError("Agentic planning requires a SIEM conversation envelope.")
    requested = validate_original_conversation_workflow(payload)
    if any(field in payload for field in {"_conversation_execution", "conversation_context", "_agentic_plan"}):
        raise ConversationBoundaryError("Server-owned conversation planning fields cannot be supplied by clients.")
    envelope = payload.get("conversation")
    if not isinstance(envelope, dict):
        raise SessionMemoryValidationError("conversation must be an object.")
    thread_id = _required_text(envelope.get("thread_id"), "conversation.thread_id", 128)
    expected_version = _positive_int(envelope.get("expected_version"), "conversation.expected_version")
    client_request_id = _required_text(
        envelope.get("client_request_id") or payload.get("client_request_id"),
        "conversation.client_request_id",
        256,
    )
    resolved_config = config if config is not None else load_ai_gateway_config()
    conn = get_db_connection()
    existing_turn = None
    try:
        thread = get_thread(conn, thread_id=thread_id, owner_username=owner_username)
        existing_turn = get_turn_by_client_request(
            conn,
            thread_id=thread_id,
            owner_username=owner_username,
            client_request_id=client_request_id,
        )
        if existing_turn is None and int(thread.get("version") or 0) != expected_version:
            raise ThreadVersionConflictError("Conversation thread version is stale; reload before planning the next turn.")
        explicit_entity = _explicit_entity(payload)
        profile = resolved_config.profile(WORKFLOW_PROFILES[WORKFLOW_QUICK_EXPLAIN])
        selection = select_conversation_context(
            conn,
            thread=thread,
            owner_username=owner_username,
            workflow=WORKFLOW_QUICK_EXPLAIN,
            max_chars=conversation_budget(
                profile_max_prompt_chars=profile.max_prompt_chars,
                workflow=WORKFLOW_QUICK_EXPLAIN,
            ),
            request_entity=explicit_entity,
        )
    finally:
        conn.close()

    preferred = requested if requested in CONVERSATION_WORKFLOWS else None
    packet = build_planner_packet(
        question=_question(payload),
        request_context=_planner_request_context(payload),
        conversation_packet=selection.packet,
        preferred_capability=preferred,
        latency_class=WORKFLOW_LATENCY_TARGETS.get(preferred or WORKFLOW_QUICK_EXPLAIN),
    )
    if existing_turn is not None:
        outcome = PlannerOutcome(
            "idempotent_existing",
            None,
            packet,
            False,
            message="Returning the original conversation submission.",
        )
    else:
        outcome = plan_turn(packet, gateway=gateway, config=resolved_config)
        if outcome.plan is None and preferred:
            outcome = deterministic_shortcut_plan(packet, preferred)
    workflow = outcome.workflow or WORKFLOW_QUICK_EXPLAIN
    if outcome.plan and outcome.plan.proposed_strategy == "artifact_draft":
        draft_type = outcome.plan.artifact_type
        if draft_type:
            payload["draft_type"] = draft_type
            workflow = "generate_artifact"
    classification = WorkflowClassification(
        requested_workflow=requested,
        classified_workflow=workflow,
        confidence=outcome.plan.confidence if outcome.plan else "low",
        reason=(
            f"Validated agentic plan selected {outcome.plan.proposed_strategy}."
            if outcome.plan
            else "The agentic planner did not return a valid executable plan."
        ),
    )
    return {
        "outcome": outcome,
        "classification": classification,
        "planning_thread_version": thread.get("version"),
    }


def prepare_worker_conversation(conn, job: dict[str, Any]) -> tuple[dict[str, Any], str]:
    payload = job.get("request_payload") if isinstance(job.get("request_payload"), dict) else {}
    thread_id = job.get("thread_id")
    turn_id = job.get("turn_id")
    if not thread_id and not turn_id:
        return payload, str(job.get("actor_role") or "")
    if not thread_id or not turn_id:
        raise ConversationBoundaryError("Async conversation linkage is incomplete.")
    current_role = _current_actor_role(conn, str(job.get("actor_username") or ""))
    workflow = str(job.get("workflow") or "")
    if workflow not in ASYNC_CONVERSATION_WORKFLOWS:
        raise ConversationBoundaryError("Linked conversation request uses an isolated workflow.")
    thread = validate_owned_thread(conn, thread_id=thread_id, owner_username=job["actor_username"])
    turn = get_turn_by_id(conn, thread_id=thread_id, owner_username=job["actor_username"], turn_id=int(turn_id))
    if turn is None or turn.get("lifecycle_status") not in {"queued", "running"}:
        raise ConversationBoundaryError("Linked conversation turn is not available for execution.")
    execution_metadata = (
        payload.get("_conversation_execution")
        if isinstance(payload.get("_conversation_execution"), dict)
        else {}
    )
    full_context = execution_metadata.get("resolved_context")
    stored_context = (
        _resolved_context_from_value(full_context)
        if isinstance(full_context, dict)
        else _resolved_context_from_turn(turn)
    )
    _validate_resolved_entities(conn, owner_username=job["actor_username"], resolved=stored_context)
    profile = load_ai_gateway_config().profile(WORKFLOW_PROFILES[workflow])
    selection = select_conversation_context(
        conn,
        thread=thread,
        owner_username=job["actor_username"],
        workflow=workflow,
        max_chars=conversation_budget(profile_max_prompt_chars=profile.max_prompt_chars, workflow=workflow),
    )
    selection = ConversationSelection(
        packet=selection.packet,
        resolution=stored_context.resolution,
        resolved_entity=stored_context.active_entity,
    )
    resolved_payload = _apply_resolved_context(payload, stored_context)
    _assert_execution_alignment(resolved_payload, stored_context, selection.packet)
    execution = {
        "thread_id": thread_id,
        "turn_id": int(turn_id),
        "expected_thread_version": turn["thread_version_after_append"],
        "selection": selection,
        "resolved_context": stored_context.as_dict(),
    }
    return _with_context(resolved_payload, selection.packet, execution=execution), current_role


def complete_worker_conversation(conn, job: dict[str, Any], result: WorkflowResult) -> WorkflowResult:
    if not job.get("thread_id") and not job.get("turn_id"):
        return result
    payload = job.get("request_payload") if isinstance(job.get("request_payload"), dict) else {}
    execution_payload = payload.get("_conversation_execution") if isinstance(payload.get("_conversation_execution"), dict) else {}
    user_turn = get_turn_by_id(
        conn,
        thread_id=job["thread_id"],
        owner_username=job["actor_username"],
        turn_id=int(job["turn_id"]),
    )
    if user_turn is None:
        raise ConversationBoundaryError("Linked conversation turn was not found at completion.")
    if _generation_failed(result.payload, result.status_code):
        failed_user = fail_execution_turn(
            conn,
            thread_id=job["thread_id"],
            owner_username=job["actor_username"],
            turn_id=int(job["turn_id"]),
        ) or user_turn
        enriched = dict(result.payload)
        enriched["conversation"] = {
            "thread_id": job["thread_id"],
            "thread_version": user_turn["thread_version_after_append"],
            "user_turn": failed_user,
            "assistant_turn": None,
            "reference_resolution": execution_payload.get("selection", {}).get("resolution"),
            "active_entity": execution_payload.get("selection", {}).get("active_entity"),
            "context_bounds": execution_payload.get("selection", {}).get("bounds", {}),
            "authoritative_history": "postgresql",
        }
        return WorkflowResult(enriched, result.status_code)
    terminal = _normalize_assistant_content(result.payload, workflow=job["workflow"])
    if not terminal.content:
        fail_execution_turn(
            conn,
            thread_id=job["thread_id"],
            owner_username=job["actor_username"],
            turn_id=int(job["turn_id"]),
        )
        raise ConversationOrchestrationError("Workflow completed without analyst-facing assistant content.")
    structured = _assistant_structured_payload(
        result.payload,
        workflow=job["workflow"],
        request_id=job.get("request_id"),
        terminal=terminal,
    )
    completed_user, assistant_turn, thread = finalize_execution_turn(
        conn,
        thread_id=job["thread_id"],
        owner_username=job["actor_username"],
        user_turn_id=int(job["turn_id"]),
        expected_thread_version=int(user_turn["thread_version_after_append"]),
        workflow=job["workflow"],
        content=terminal.content,
        client_request_id=f"{user_turn['client_request_id']}:assistant",
        structured_payload=structured,
        entity_snapshot=user_turn.get("entity_snapshot") or {},
        artifact_preview=job["workflow"] == "generate_artifact",
    )
    _persist_result_evidence(
        conn,
        payload=result.payload,
        workflow=job["workflow"],
        thread_id=job["thread_id"],
        owner_username=job["actor_username"],
        assistant_turn=assistant_turn,
    )
    enriched = dict(result.payload)
    enriched["conversation"] = _conversation_metadata(
        thread,
        completed_user,
        assistant_turn=assistant_turn,
        selection=execution_payload.get("selection"),
    )
    return WorkflowResult(enriched, result.status_code)


def fail_worker_conversation(conn, job: dict[str, Any]) -> None:
    if not job.get("thread_id") or not job.get("turn_id"):
        return
    fail_execution_turn(
        conn,
        thread_id=job["thread_id"],
        owner_username=job["actor_username"],
        turn_id=int(job["turn_id"]),
    )


def _prepare_submission(
    payload: dict[str, Any],
    *,
    workflow: str,
    owner_username: str,
    classification: WorkflowClassification,
    resolved_config,
    create_async_request: bool = False,
    actor_role: str | None = None,
    planner_outcome: PlannerOutcome | None = None,
) -> dict[str, Any]:
    if "_conversation_execution" in payload or "conversation_context" in payload or "_agentic_plan" in payload:
        raise ConversationBoundaryError("Server-owned conversation fields cannot be supplied by clients.")
    envelope = payload.get("conversation")
    if not isinstance(envelope, dict):
        raise SessionMemoryValidationError("conversation must be an object.")
    thread_id = _required_text(envelope.get("thread_id"), "conversation.thread_id", 128)
    client_request_id = _required_text(
        envelope.get("client_request_id") or payload.get("client_request_id"),
        "conversation.client_request_id",
        256,
    )
    expected_version = _positive_int(envelope.get("expected_version"), "conversation.expected_version")
    conn = get_db_connection()
    try:
        thread = validate_owned_thread(conn, thread_id=thread_id, owner_username=owner_username)
        existing_turn = get_turn_by_client_request(
            conn,
            thread_id=thread_id,
            owner_username=owner_username,
            client_request_id=client_request_id,
        )
        if existing_turn is not None:
            linked = linked_workflow_request_for_turn(
                conn,
                thread_id=thread_id,
                owner_username=owner_username,
                turn_id=existing_turn["id"],
            )
            if create_async_request and linked is not None:
                conn.commit()
                return {
                    "thread": thread,
                    "user_turn": existing_turn,
                    "request": linked,
                    "request_created": False,
                    "selection": None,
                }
            duplicate = _sync_duplicate_result(conn, thread, existing_turn, owner_username=owner_username)
            conn.commit()
            return {"duplicate_result": duplicate}
        profile = resolved_config.profile(WORKFLOW_PROFILES[workflow])
        explicit_entity = _explicit_entity(payload)
        selection = select_conversation_context(
            conn,
            thread=thread,
            owner_username=owner_username,
            workflow=workflow,
            max_chars=conversation_budget(profile_max_prompt_chars=profile.max_prompt_chars, workflow=workflow),
            request_entity=explicit_entity,
        )
        plan = planner_outcome.plan if planner_outcome else None
        resolution = _planner_resolution(plan, planner_outcome)
        if plan:
            _validate_plan_selected_entities(conn, owner_username=owner_username, plan=plan)
        if plan and plan.current_turn_intent == "analyst_correction":
            assertion_type = "correction"
        elif plan and plan.proposed_strategy == "clarification_required":
            assertion_type = "unresolved_question"
        else:
            assertion_type = "analyst_statement"
        parent_turn_id = (
            _validated_correction_parent_turn_id(
                conn,
                thread_id=thread_id,
                owner_username=owner_username,
                plan=plan,
            )
            if plan and plan.current_turn_intent == "analyst_correction"
            else None
        )
        executable = bool(
            plan
            and plan.proposed_strategy not in {"clarification_required", "unsupported_or_boundary"}
        )
        resolved_context = (
            _execution_context_from_plan(
                conn,
                payload=payload,
                owner_username=owner_username,
                plan=plan,
                resolution=resolution,
            )
            if executable and plan
            else None
        )
        entity_snapshot = resolved_context.entity_snapshot if resolved_context else {
            "active_entity": None,
            "entities": [dict(item) for item in (plan.resolved_entities if plan else ())],
        }
        selection = ConversationSelection(
            packet=selection.packet,
            resolution=resolution,
            resolved_entity=resolved_context.active_entity if resolved_context else None,
        )
        execution_payload = _apply_resolved_context(payload, resolved_context) if resolved_context else dict(payload)
        execution_payload["workflow"] = workflow
        if planner_outcome:
            execution_payload["_agentic_plan"] = planner_outcome.metadata()
            _apply_planner_execution_hints(execution_payload, planner_outcome.plan)
        if resolved_context:
            _assert_execution_alignment(execution_payload, resolved_context, selection.packet)
        user_turn, updated_thread, _created = append_turn(
            conn,
            thread_id=thread_id,
            owner_username=owner_username,
            expected_version=expected_version,
            client_request_id=client_request_id,
            role="user",
            workflow=workflow,
            content=_question(payload),
            assertion_type=assertion_type,
            structured_payload=_conversation_turn_payload(
                workflow=workflow,
                payload=payload,
                resolution=resolution,
                resolved=resolved_context,
                planner_outcome=planner_outcome,
            ),
            parent_turn_id=parent_turn_id,
            entity_snapshot=entity_snapshot,
            lifecycle_status="queued",
        )
        prepared = {
            "thread": updated_thread,
            "user_turn": user_turn,
            "selection": selection,
            "owner_username": owner_username,
            "workflow": workflow,
            "resolved_context": resolved_context,
            "execution_payload": execution_payload,
        }
        if (
            planner_outcome is not None
            and planner_outcome.plan is None
            or planner_outcome is not None
            and planner_outcome.plan is not None
            and planner_outcome.plan.proposed_strategy in {"clarification_required", "unsupported_or_boundary"}
        ):
            boundary_message = (
                "That request is outside this read-only SIEM conversation. Use the dedicated approved surface or action workflow."
                if planner_outcome
                and planner_outcome.plan
                and planner_outcome.plan.proposed_strategy == "unsupported_or_boundary"
                else None
            )
            message = str(
                boundary_message
                or (planner_outcome.plan.clarification_question if planner_outcome and planner_outcome.plan else None)
                or (planner_outcome.message if planner_outcome else None)
                or "I could not safely plan this request. Please clarify the entity and desired outcome."
            )
            completed_user, assistant_turn, final_thread = finalize_execution_turn(
                conn,
                thread_id=thread_id,
                owner_username=owner_username,
                user_turn_id=user_turn["id"],
                expected_thread_version=user_turn["thread_version_after_append"],
                workflow=workflow,
                content=message,
                client_request_id=f"{client_request_id}:assistant",
                structured_payload={
                    "confidence": "high",
                    "provenance": {"type": "agentic_planner"},
                    "reference_resolution": resolution,
                    "agentic_plan": planner_outcome.metadata() if planner_outcome else None,
                },
                entity_snapshot=entity_snapshot,
            )
            conn.commit()
            prepared["deterministic_result"] = _deterministic_envelope(
                classification,
                workflow=workflow,
                message=message,
                status=(
                    "clarification_required"
                    if planner_outcome
                    and planner_outcome.plan
                    and planner_outcome.plan.proposed_strategy == "clarification_required"
                    else "unsupported_or_boundary"
                    if planner_outcome
                    and planner_outcome.plan
                    and planner_outcome.plan.proposed_strategy == "unsupported_or_boundary"
                    else str(resolution.get("status") or "planner_unavailable")
                ),
                resolution=resolution,
                thread=final_thread,
                user_turn=completed_user,
                assistant_turn=assistant_turn,
                selection=selection,
            )
            return prepared
        if create_async_request:
            server_payload = {
                **execution_payload,
                "client_request_id": client_request_id,
                "_conversation_execution": {
                    "thread_id": thread_id,
                    "turn_id": user_turn["id"],
                    "expected_thread_version": user_turn["thread_version_after_append"],
                    "resolved_context": resolved_context.as_dict(),
                    "agentic_plan": planner_outcome.metadata() if planner_outcome else None,
                },
            }
            request_row, request_created = create_or_get_request(
                conn,
                workflow=workflow,
                context_type=resolved_context.context_type,
                payload=server_payload,
                classification=classification.as_dict(),
                actor_username=owner_username,
                actor_role=str(actor_role or ""),
            )
            linked = link_async_request(
                conn,
                request_id=request_row["request_id"],
                thread_id=thread_id,
                turn_id=user_turn["id"],
                owner_username=owner_username,
            )
            prepared.update({"request": {**request_row, **linked}, "request_created": request_created})
        conn.commit()
        return prepared
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _complete_sync(prepared: dict[str, Any], result: WorkflowResult) -> WorkflowResult:
    if _generation_failed(result.payload, result.status_code):
        _fail_prepared_turn(prepared)
        enriched = dict(result.payload)
        enriched["conversation"] = _conversation_metadata(
            prepared["thread"],
            {**prepared["user_turn"], "lifecycle_status": "failed"},
            assistant_turn=None,
            selection=prepared["selection"],
        )
        return WorkflowResult(enriched, result.status_code)
    terminal = _normalize_assistant_content(result.payload, workflow=prepared["workflow"])
    if not terminal.content:
        _fail_prepared_turn(prepared)
        raise ConversationOrchestrationError("Workflow completed without analyst-facing assistant content.")
    conn = get_db_connection()
    try:
        completed_user, assistant_turn, thread = finalize_execution_turn(
            conn,
            thread_id=prepared["thread"]["thread_id"],
            owner_username=prepared["owner_username"],
            user_turn_id=prepared["user_turn"]["id"],
            expected_thread_version=prepared["user_turn"]["thread_version_after_append"],
            workflow=prepared["workflow"],
            content=terminal.content,
            client_request_id=f"{prepared['user_turn']['client_request_id']}:assistant",
            structured_payload=_assistant_structured_payload(
                result.payload,
                workflow=prepared["workflow"],
                terminal=terminal,
            ),
            entity_snapshot=prepared["user_turn"].get("entity_snapshot") or {},
        )
        _persist_result_evidence(
            conn,
            payload=result.payload,
            workflow=prepared["workflow"],
            thread_id=prepared["thread"]["thread_id"],
            owner_username=prepared["owner_username"],
            assistant_turn=assistant_turn,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    enriched = dict(result.payload)
    enriched["conversation"] = _conversation_metadata(
        thread,
        completed_user,
        assistant_turn=assistant_turn,
        selection=prepared["selection"],
    )
    return WorkflowResult(enriched, result.status_code)


def _fail_prepared_turn(prepared: dict[str, Any]) -> None:
    conn = get_db_connection()
    try:
        fail_execution_turn(
            conn,
            thread_id=prepared["thread"]["thread_id"],
            owner_username=prepared["owner_username"],
            turn_id=prepared["user_turn"]["id"],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _sync_duplicate_result(
    conn,
    thread: dict[str, Any],
    user_turn: dict[str, Any],
    *,
    owner_username: str,
) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT * FROM anakin_turns
            WHERE thread_id = %s AND owner_username = %s AND parent_turn_id = %s AND role = 'assistant'
            ORDER BY sequence ASC LIMIT 1
            """,
            (thread["thread_id"], owner_username, user_turn["id"]),
        )
        columns = [desc[0] for desc in cur.description]
        row = cur.fetchone()
    assistant = serialize_turn(dict(zip(columns, row))) if row is not None else None
    return {
        "status": "completed" if assistant else user_turn.get("lifecycle_status"),
        "workflow": user_turn.get("workflow"),
        "result": {"answer": assistant.get("content") if assistant else None},
        "metadata": {"duplicate": True, "model_invoked": False},
        "conversation": {
            "thread_id": thread["thread_id"],
            "thread_version": thread["version"],
            "user_turn": user_turn,
            "assistant_turn": assistant,
            "duplicate": True,
        },
        "error": None,
    }


def _current_actor_role(conn, username: str) -> str:
    if username == "admin":
        return "super_admin"
    with conn.cursor() as cur:
        cur.execute("SELECT role, is_active FROM users WHERE username = %s", (username,))
        row = cur.fetchone()
    if row is None or not bool(row[1]) or row[0] not in {"analyst", "super_admin"}:
        raise ConversationActorUnavailableError("Conversation actor is disabled or no longer has analyst access.")
    return str(row[0])


def _with_context(payload: dict[str, Any], packet: dict[str, Any], *, execution: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {**payload, "conversation_context": packet}
    if execution:
        result["_conversation_execution"] = {
            "thread_id": execution["thread_id"],
            "turn_id": execution["turn_id"],
            "expected_thread_version": execution["expected_thread_version"],
            "selection": {
                "resolution": execution["selection"].resolution,
                "bounds": execution["selection"].packet.get("bounds", {}),
                "active_entity": execution["resolved_context"].get("active_entity"),
            },
        }
    return result


def _assistant_content(payload: dict[str, Any], *, workflow: str) -> str:
    return _normalize_assistant_content(payload, workflow=workflow).content


def _normalize_assistant_content(payload: dict[str, Any], *, workflow: str) -> AssistantTerminalContent:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    if workflow in {"quick_explain", "decision_support"}:
        value = result.get("answer")
    elif workflow == "deep_investigate":
        return _normalize_deep_investigation_content(payload, result)
    elif workflow == "generate_artifact":
        value = result.get("draft") or result.get("artifact")
    else:
        value = result.get("answer")
    if isinstance(value, (dict, list)):
        text = json.dumps(value, default=str, sort_keys=True)
    else:
        text = str(value or "").strip()
    text = text if len(text) <= 8000 else f"{text[:7950]}... [compacted for conversation storage]"
    status = str(result.get("status") or payload.get("status") or "unknown").strip().lower()
    return AssistantTerminalContent(content=text, category="full" if text else "malformed", result_status=status)


def _normalize_deep_investigation_content(
    payload: dict[str, Any], result: dict[str, Any]
) -> AssistantTerminalContent:
    investigation = result.get("investigation") if isinstance(result.get("investigation"), dict) else {}
    status = str(investigation.get("status") or result.get("status") or payload.get("status") or "unknown").strip().lower()
    provider_status = _deep_provider_status(investigation)
    error = _clean_scalar(investigation.get("error") or result.get("error") or payload.get("error"), 500)
    failure_statuses = {"failed", "error", "provider_error", "provider_unavailable", "timed_out", "timeout", "cancelled"}
    if status in failure_statuses:
        return AssistantTerminalContent(
            content="",
            category="failed",
            result_status=status,
            provider_status=provider_status,
            error=error,
        )

    summary = _first_scalar(investigation, result, keys=("summary", "answer"), max_chars=7000)
    if summary:
        category = "partial" if status in {"partial", "degraded", "insufficient_context"} else "full"
        return AssistantTerminalContent(
            content=summary,
            category=category,
            result_status=status,
            provider_status=provider_status,
            error=error,
        )

    sections: list[tuple[str, list[str]]] = []
    assessment = _semantic_values(investigation, result, keys=("assessment",), limit=2)
    findings = _semantic_values(
        investigation,
        result,
        keys=("findings", "correlated_evidence", "correlations"),
        limit=3,
        allow_source_evidence=True,
    )
    hypotheses = _semantic_values(investigation, result, keys=("competing_hypotheses", "hypotheses"), limit=2)
    contradictions = _semantic_values(investigation, result, keys=("contradictions",), limit=2)
    gaps = _semantic_values(investigation, result, keys=("evidence_gaps", "missing_evidence"), limit=2)
    next_steps = _semantic_values(
        investigation,
        result,
        keys=("prioritized_next_step", "next_step", "recommendations"),
        limit=2,
        recommendation=True,
    )
    confidence = _first_scalar(investigation, result, keys=("confidence",), max_chars=160)
    for label, values in (
        ("Assessment", assessment),
        ("Validated findings", findings),
        ("Working hypotheses", hypotheses),
        ("Contradictions", contradictions),
        ("Evidence gaps", gaps),
        ("Next step", next_steps),
    ):
        if values:
            sections.append((label, values))
    lines = [f"{label}: {' '.join(values)}" for label, values in sections]
    if confidence:
        lines.append(f"Confidence: {confidence}")
    content = "\n".join(lines)
    if content and status in {"partial", "degraded", "insufficient_context"}:
        content = f"Partial investigation result ({status.replace('_', ' ')}).\n{content}"
    missing = tuple(
        name
        for name, values in (
            ("summary", [summary] if summary else []),
            ("assessment", assessment),
            ("findings", findings),
            ("evidence_gaps", gaps),
            ("next_step", next_steps),
        )
        if not values
    )
    category = "malformed" if not content else (
        "partial" if status in {"partial", "degraded", "insufficient_context"} else "structured"
    )
    return AssistantTerminalContent(
        content=content[:8000],
        category=category,
        result_status=status,
        missing_sections=missing,
        provider_status=provider_status,
        error=error,
    )


def _semantic_values(
    investigation: dict[str, Any],
    result: dict[str, Any],
    *,
    keys: tuple[str, ...],
    limit: int,
    recommendation: bool = False,
    allow_source_evidence: bool = False,
) -> list[str]:
    values: list[str] = []
    for container in (investigation, result):
        for key in keys:
            raw = container.get(key)
            items = raw if isinstance(raw, list) else ([raw] if raw not in (None, "", {}, []) else [])
            for item in items:
                text = _semantic_item_text(item, recommendation=recommendation, allow_source_evidence=allow_source_evidence)
                if text and text not in values:
                    values.append(text)
                    if len(values) >= limit:
                        return values
    return values


def _semantic_item_text(value: Any, *, recommendation: bool, allow_source_evidence: bool) -> str:
    scalar = _clean_scalar(value, 900)
    if scalar:
        return scalar
    if not isinstance(value, dict):
        return ""
    keys = (
        ("recommendation", "recommended_action", "next_step", "action", "description", "reason", "title")
        if recommendation
        else ("finding", "summary", "assessment", "description", "detail", "fact", "inference", "hypothesis", "contradiction", "gap")
    )
    parts = []
    for key in keys:
        text = _clean_scalar(value.get(key), 700)
        if text and text not in parts:
            parts.append(text)
    if parts:
        return " ".join(parts[:2])
    if allow_source_evidence:
        source_type = _clean_scalar(value.get("source_type") or value.get("type"), 80)
        if source_type:
            return f"Validated {source_type.replace('_', ' ')} evidence was available."
    return ""


def _first_scalar(*containers: dict[str, Any], keys: tuple[str, ...], max_chars: int) -> str:
    for container in containers:
        for key in keys:
            text = _clean_scalar(container.get(key), max_chars)
            if text:
                return text
    return ""


def _clean_scalar(value: Any, max_chars: int) -> str:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return ""
    text = " ".join(str(value).split()).strip()
    return text if len(text) <= max_chars else f"{text[: max_chars - 16]}... [compacted]"


def _deep_provider_status(investigation: dict[str, Any]) -> str | None:
    observability = investigation.get("observability") if isinstance(investigation.get("observability"), dict) else {}
    responses = observability.get("provider_responses") if isinstance(observability.get("provider_responses"), list) else []
    for response in reversed(responses):
        if isinstance(response, dict):
            status = _clean_scalar(response.get("status"), 80)
            if status:
                return status
    return None


def _generation_failed(payload: dict[str, Any], status_code: int) -> bool:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    investigation = result.get("investigation") if isinstance(result.get("investigation"), dict) else {}
    statuses = {
        str(payload.get("status") or "").lower(),
        str(result.get("status") or "").lower(),
        str(investigation.get("status") or "").lower(),
    }
    failure_statuses = {
        "failed",
        "error",
        "provider_error",
        "provider_unavailable",
        "timed_out",
        "timeout",
        "validation_failed",
        "parse_failed",
    }
    return status_code >= 500 or bool(statuses & failure_statuses)


def _assistant_structured_payload(
    payload: dict[str, Any],
    *,
    workflow: str,
    request_id: str | None = None,
    terminal: AssistantTerminalContent | None = None,
) -> dict[str, Any]:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    normalized = terminal or _normalize_assistant_content(payload, workflow=workflow)
    status = normalized.result_status
    structured = {
        "confidence": "low" if status in {"partial", "degraded", "insufficient_context"} else "medium",
        "provenance": {"type": "model_inference", "workflow": workflow, "request_id": request_id},
        "result_status": status,
        "terminal_category": normalized.category,
    }
    if normalized.missing_sections:
        structured["missing_sections"] = list(normalized.missing_sections)
    if normalized.provider_status:
        structured["provider_status"] = normalized.provider_status
    if normalized.error:
        structured["terminal_error"] = normalized.error
    evidence_envelope = result.get("evidence_envelope")
    if isinstance(evidence_envelope, dict):
        structured["evidence_grounding"] = _bounded_evidence_value(evidence_envelope)
    if workflow == "generate_artifact":
        structured.pop("confidence", None)
        structured["artifact"] = _bounded_artifact(result.get("draft") or result.get("artifact"))
    return structured


def _bounded_artifact(value: Any) -> Any:
    rendered = json.dumps(value, default=str, sort_keys=True)
    if len(rendered) <= 24000:
        return value
    return {"summary": "Artifact payload exceeded conversation structured-storage bounds.", "preview": rendered[:12000]}


def _persist_result_evidence(
    conn,
    *,
    payload: dict[str, Any],
    workflow: str,
    thread_id: str,
    owner_username: str,
    assistant_turn: dict[str, Any],
) -> None:
    observed = utc_now()
    for index, item in enumerate(_tool_evidence_items(payload)[:6], start=1):
        sources = item.get("sources") if isinstance(item.get("sources"), list) else []
        source = next((value for value in sources if isinstance(value, dict)), {})
        source_ref = str(source.get("source_path") or source.get("source_type") or "").strip()
        if not source_ref:
            source_ref = f"conversation:{workflow}:turn:{assistant_turn.get('turn_id')}:{index}"
        create_evidence(
            conn,
            thread_id=thread_id,
            owner_username=owner_username,
            source_type=str(item.get("tool_name") or "soc_read_evidence")[:128],
            source_ref=source_ref[:512],
            snapshot={
                "status": item.get("status"),
                "finding": _bounded_evidence_value(item.get("data")),
                "sources": _bounded_evidence_value(sources),
            },
            query_parameters={},
            entity_fingerprint=_entity_fingerprint_from_sources(sources),
            observed_at=observed,
            fresh_until=observed + timedelta(minutes=15),
            relationship_type="context",
        )


def _tool_evidence_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    packets = []
    if isinstance(result.get("tools"), dict):
        packets.append(result["tools"])
    investigation = result.get("investigation") if isinstance(result.get("investigation"), dict) else {}
    evidence = investigation.get("evidence") if isinstance(investigation.get("evidence"), dict) else {}
    if isinstance(evidence.get("tools"), dict):
        packets.append(evidence["tools"])
    items = []
    for packet in packets:
        calls = packet.get("calls") if isinstance(packet.get("calls"), list) else []
        items.extend(
            call for call in calls
            if isinstance(call, dict) and call.get("status") == "success" and call.get("data") not in (None, {}, [])
        )
    return items


def _bounded_evidence_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 3:
        text = str(value)
        return text if len(text) <= 240 else f"{text[:220]}... [compacted]"
    if isinstance(value, dict):
        return {
            str(key)[:80]: _bounded_evidence_value(child, depth=depth + 1)
            for key, child in list(value.items())[:16]
        }
    if isinstance(value, list):
        return [_bounded_evidence_value(item, depth=depth + 1) for item in value[:10]]
    if isinstance(value, str) and len(value) > 500:
        return f"{value[:480]}... [compacted]"
    return value


def _entity_fingerprint_from_sources(sources: list[Any]) -> str | None:
    for source in sources:
        if not isinstance(source, dict):
            continue
        record_ids = source.get("record_ids") if isinstance(source.get("record_ids"), list) else []
        if record_ids:
            return f"{source.get('source_type') or 'record'}:{record_ids[0]}"[:256]
    return None


_IDENTITY_CONTEXT_FIELDS = frozenset(
    {
        "alert_id",
        "incident_id",
        "source_ip",
        "activity_id",
        "recon_activity_id",
        "registry_id",
        "investigation_id",
    }
)


def _explicit_entity(payload: dict[str, Any]) -> dict[str, str] | None:
    supplied = payload.get("entity") if isinstance(payload.get("entity"), dict) else {}
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    entity_type = str(supplied.get("type") or payload.get("context_type") or "").strip().lower().replace("-", "_")
    aliases = {"analyst_workspace": "general", "soc_command_center": "general", "recon_history": "general"}
    entity_type = aliases.get(entity_type, entity_type)
    field_by_type = {
        "alert": ("alert_id", "id"),
        "detection": ("alert_id", "id"),
        "incident": ("incident_id", "id"),
        "source_ip": ("source_ip", "id"),
        "recon_activity": ("activity_id", "recon_activity_id", "id"),
        "response_registry": ("registry_id", "id"),
        "investigation": ("investigation_id", "id"),
    }
    value = supplied.get("id")
    for field in field_by_type.get(entity_type, ()):
        if value not in (None, ""):
            break
        value = supplied.get(field) if supplied.get(field) not in (None, "") else context.get(field)
    if value in (None, "") and entity_type in {"dashboard", "general"}:
        value = supplied.get("id") or entity_type
    if not entity_type or value in (None, ""):
        return None
    return {"type": entity_type, "id": str(value), "display_alias": supplied.get("display_alias")}


def _planner_request_context(payload: dict[str, Any]) -> dict[str, Any]:
    artifact = payload.get("artifact") if isinstance(payload.get("artifact"), dict) else {}
    artifact_type = payload.get("draft_type") or payload.get("draftType") or payload.get("artifact_type") or artifact.get("type")
    return {
        "context_type": str(payload.get("context_type") or "")[:64],
        "artifact_type": str(artifact_type)[:80] if artifact_type not in (None, "") else None,
    }


def _planner_resolution(plan: AgenticAnalystPlan | None, outcome: PlannerOutcome | None) -> dict[str, Any]:
    if plan is None:
        return {
            "status": "planner_unavailable",
            "intent": None,
            "relationship": None,
            "referent": None,
            "candidates": [],
            "error_code": outcome.error_code if outcome else None,
        }
    entities = [dict(item) for item in plan.resolved_entities]
    if plan.proposed_strategy == "clarification_required":
        status = "clarification_required"
        referent = None
    elif plan.proposed_strategy == "unsupported_or_boundary":
        status = "unsupported_or_boundary"
        referent = None
    else:
        status = "resolved"
        referent = {"entities": entities} if len(entities) > 1 else (entities[0] if entities else None)
    return {
        "status": status,
        "intent": plan.current_turn_intent,
        "relationship": plan.relationship_to_prior_turn,
        "referent": referent,
        "candidates": entities,
    }


def _execution_context_from_plan(
    conn,
    *,
    payload: dict[str, Any],
    owner_username: str,
    plan: AgenticAnalystPlan,
    resolution: dict[str, Any],
) -> ResolvedExecutionContext:
    planned_entities = _distinct_entities(list(plan.resolved_entities))
    if not planned_entities:
        context_type, context = _entityless_execution_context(payload)
        return ResolvedExecutionContext(
            active_entity=None,
            entities=(),
            comparison_entities=(),
            context_type=context_type,
            context=context,
            entity_snapshot={"active_entity": None, "entities": []},
            resolution=resolution,
            source="agentic_planner",
        )
    active = planned_entities[0]
    comparison = planned_entities if plan.proposed_strategy == "compare_entities" else []
    context_type, context = _execution_context_fields(
        conn,
        owner_username=owner_username,
        active=active,
        payload=payload,
    )
    derived = [{"type": "source_ip", "id": context["source_ip"]}] if context.get("source_ip") else []
    entities = _distinct_entities([*planned_entities, *derived])
    resolved = ResolvedExecutionContext(
        active_entity=active,
        entities=tuple(entities),
        comparison_entities=tuple(_distinct_entities(comparison)),
        context_type=context_type,
        context=context,
        entity_snapshot={"active_entity": active, "entities": entities[:20]},
        resolution=resolution,
        source="agentic_planner",
    )
    _validate_resolved_entities(conn, owner_username=owner_username, resolved=resolved)
    return resolved


def _entityless_execution_context(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    requested_type = str(payload.get("context_type") or "general").strip().lower().replace("-", "_")
    aliases = {"analyst_workspace": "general", "soc_command_center": "general", "recon_history": "general"}
    context_type = aliases.get(requested_type, requested_type)
    if context_type not in {"dashboard", "general"}:
        context_type = "general"
    original = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    context = {key: value for key, value in original.items() if key not in _IDENTITY_CONTEXT_FIELDS and key != "id"}
    return context_type, context


def _validate_plan_selected_entities(
    conn,
    *,
    owner_username: str,
    plan: AgenticAnalystPlan,
) -> None:
    for entity in plan.resolved_entities:
        validate_conversation_entity(
            conn,
            owner_username=owner_username,
            entity_type=entity["type"],
            entity_id=entity["id"],
        )


def _validated_correction_parent_turn_id(
    conn,
    *,
    thread_id: str,
    owner_username: str,
    plan: AgenticAnalystPlan,
) -> int:
    sequence = plan.referenced_turn_sequence
    if sequence is None:
        raise ConversationBoundaryError("Planner correction is missing its referenced turn.")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, role, assertion_type, entity_snapshot
            FROM anakin_turns
            WHERE thread_id = %s AND owner_username = %s AND sequence = %s
            """,
            (thread_id, owner_username, sequence),
        )
        row = cur.fetchone()
    if row is None or row[1] != "assistant" or row[2] != "model_inference":
        raise ConversationBoundaryError("Planner correction must reference an owned assistant inference.")
    snapshot = row[3] if isinstance(row[3], dict) else {}
    target = _normalized_entity(snapshot.get("active_entity"))
    selected = _normalized_entity(plan.resolved_entities[0]) if plan.resolved_entities else None
    if target and selected and _entity_identity(target) != _entity_identity(selected):
        raise ConversationBoundaryError("Planner correction entity does not match the referenced inference.")
    return int(row[0])


def _execution_context_fields(
    conn,
    *,
    owner_username: str,
    active: dict[str, Any],
    payload: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    original = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    context = {key: value for key, value in original.items() if key not in _IDENTITY_CONTEXT_FIELDS and key != "id"}
    entity_type, entity_id = _entity_identity(active)
    requested_type = str(payload.get("context_type") or "").strip().lower().replace("-", "_")

    if entity_type in {"alert", "detection"}:
        context_type = "detection" if entity_type == "detection" or requested_type == "detection" else "alert"
        context["alert_id"] = _entity_int(entity_id, entity_type)
        with conn.cursor() as cur:
            cur.execute("SELECT host(source_ip) FROM alerts WHERE id = %s", (context["alert_id"],))
            row = cur.fetchone()
        if row and row[0]:
            context["source_ip"] = str(row[0])
    elif entity_type == "incident":
        context_type = "incident"
        context["incident_id"] = _entity_int(entity_id, entity_type)
        with conn.cursor() as cur:
            cur.execute("SELECT host(source_ip) FROM incidents WHERE id = %s", (context["incident_id"],))
            row = cur.fetchone()
        if row and row[0]:
            context["source_ip"] = str(row[0])
    elif entity_type == "source_ip":
        context_type = "source_ip"
        context["source_ip"] = entity_id
    elif entity_type == "recon_activity":
        context_type = "recon_activity"
        context["activity_id"] = _entity_int(entity_id, entity_type)
    elif entity_type == "response_registry":
        context_type = "response_registry"
        context["registry_id"] = _entity_int(entity_id, entity_type)
    elif entity_type == "investigation":
        investigation_id = _entity_int(entity_id, entity_type)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT linked_alert_id, linked_incident_id, host(linked_source_ip)
                FROM investigations
                WHERE id = %s AND owner_username = %s AND visibility = 'private'
                """,
                (investigation_id, owner_username),
            )
            row = cur.fetchone()
        if row is None:
            raise ConversationBoundaryError("Resolved investigation is no longer available.")
        context["investigation_id"] = investigation_id
        if row[0] is not None:
            context_type, context["alert_id"] = "alert", int(row[0])
        elif row[1] is not None:
            context_type, context["incident_id"] = "incident", int(row[1])
        elif row[2]:
            context_type, context["source_ip"] = "source_ip", str(row[2])
        else:
            context_type = "general"
    elif entity_type in {"dashboard", "general"}:
        context_type = entity_type
    else:
        raise ConversationBoundaryError("Resolved entity type cannot be mapped to a workflow context.")
    return context_type, context


def _apply_resolved_context(payload: dict[str, Any], resolved: ResolvedExecutionContext) -> dict[str, Any]:
    result = {
        **payload,
        "context_type": resolved.context_type,
        "context": dict(resolved.context),
    }
    if resolved.active_entity:
        result["entity"] = dict(resolved.active_entity)
    else:
        result.pop("entity", None)
    if resolved.comparison_entities:
        result["context"]["comparison_entities"] = [dict(item) for item in resolved.comparison_entities]
    return result


def _resolved_context_from_turn(turn: dict[str, Any]) -> ResolvedExecutionContext:
    structured = turn.get("structured_payload") if isinstance(turn.get("structured_payload"), dict) else {}
    value = structured.get("resolved_execution_context")
    if not isinstance(value, dict):
        raise ConversationBoundaryError("Queued conversation turn is missing its resolved execution context.")
    if not isinstance(value.get("resolution"), dict) and isinstance(structured.get("reference_resolution"), dict):
        value = {**value, "resolution": structured["reference_resolution"]}
    return _resolved_context_from_value(value)


def _resolved_context_from_value(value: dict[str, Any]) -> ResolvedExecutionContext:
    active = _normalized_entity(value.get("active_entity"))
    entities = _distinct_entities(value.get("entities") if isinstance(value.get("entities"), list) else [])
    comparison = _distinct_entities(
        value.get("comparison_entities") if isinstance(value.get("comparison_entities"), list) else []
    )
    context = value.get("context") if isinstance(value.get("context"), dict) else None
    resolution = value.get("resolution") if isinstance(value.get("resolution"), dict) else None
    if context is None or resolution is None or (entities and not active):
        raise ConversationBoundaryError("Queued conversation resolved context is malformed.")
    if active and not any(_entity_identity(item) == _entity_identity(active) for item in entities):
        raise ConversationBoundaryError("Queued conversation active entity is absent from its entity snapshot.")
    return ResolvedExecutionContext(
        active_entity=active,
        entities=tuple(entities),
        comparison_entities=tuple(comparison),
        context_type=_required_text(value.get("context_type"), "resolved context type", 64),
        context=context,
        entity_snapshot={"active_entity": active, "entities": entities[:20]},
        resolution=resolution,
        source=str(value.get("source") or "conversation"),
    )


def _conversation_turn_payload(
    *,
    workflow: str,
    payload: dict[str, Any],
    resolution: dict[str, Any],
    resolved: ResolvedExecutionContext | None,
    planner_outcome: PlannerOutcome | None = None,
) -> dict[str, Any]:
    compact_resolution = _compact_turn_resolution(resolution)
    result: dict[str, Any] = {
        "schema_version": 1,
        "reference_resolution": compact_resolution,
        "workflow_intent": {
            "workflow": workflow,
            "command": _compact_command_intent(payload),
        },
        "provenance": {"type": "conversation_submission"},
    }
    if resolved:
        result["resolved_execution_context"] = {
            "active_entity": _compact_turn_entity(resolved.active_entity),
            "entities": [_compact_turn_entity(item) for item in resolved.entities[:20]],
            "comparison_entities": [
                _compact_turn_entity(item) for item in resolved.comparison_entities[:2]
            ],
            "context_type": resolved.context_type,
            "context": _compact_turn_context(resolved.context),
            "source": resolved.source,
        }
    if planner_outcome:
        result["agentic_plan"] = _compact_planner_turn(planner_outcome)
    if workflow == "generate_artifact":
        artifact = payload.get("artifact") if isinstance(payload.get("artifact"), dict) else {}
        result["artifact_safety"] = {
            "artifact_type": _compact_scalar(
                payload.get("draft_type") or payload.get("draftType") or payload.get("artifact_type") or artifact.get("type"),
                80,
            ),
            "preview_only": True,
            "persisted": False,
            "applied": False,
            "approval_required": True,
        }
    return result


def _compact_planner_turn(outcome: PlannerOutcome) -> dict[str, Any]:
    plan = outcome.plan
    return {
        "status": outcome.status,
        "strategy": plan.proposed_strategy if plan else None,
        "capability": plan.proposed_capability if plan else None,
        "intent": _compact_scalar(plan.current_turn_intent, 180) if plan else None,
        "relationship": plan.relationship_to_prior_turn if plan else None,
        "evidence_sufficiency": plan.evidence_sufficiency if plan else None,
        "evidence_requirements": dict(plan.evidence_requirements) if plan else {},
        "evidence_filter_provenance": dict(plan.evidence_filter_provenance) if plan else {},
        "resolved_entities": [dict(item) for item in plan.resolved_entities] if plan else [],
        "artifact_type": plan.artifact_type if plan else None,
        "referenced_turn_sequence": plan.referenced_turn_sequence if plan else None,
        "confidence": plan.confidence if plan else None,
        "read_only": True,
        "repaired": outcome.repaired,
        "packet_chars": outcome.packet.serialized_chars,
        "prompt_chars": outcome.packet.prompt_chars,
        "error_code": outcome.error_code,
    }


def _apply_planner_execution_hints(payload: dict[str, Any], plan: AgenticAnalystPlan | None) -> None:
    if plan is None:
        return
    payload["planner_intent"] = plan.current_turn_intent
    payload["planner_strategy"] = plan.proposed_strategy
    payload["planner_evidence_sufficiency"] = plan.evidence_sufficiency
    payload["planner_evidence_requirements"] = dict(plan.evidence_requirements)
    payload["planner_evidence_filter_provenance"] = dict(plan.evidence_filter_provenance)
    if plan.proposed_strategy == "quick_evidence_lookup":
        tool_request = _planner_tool_request(
            plan.proposed_tool_categories[0],
            payload,
            plan.evidence_requirements,
        )
        if tool_request is None:
            raise ConversationBoundaryError("The validated evidence category cannot be translated into a bounded read request.")
        payload["use_tools"] = True
        payload["tool_policy"] = {
            "max_tool_calls": 1,
            "tool_requests": [tool_request],
        }

def _planner_tool_request(
    category: str,
    payload: dict[str, Any],
    requirements: dict[str, Any],
) -> dict[str, Any] | None:
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    if category == "alerts":
        arguments = {
            "sort": requirements.get("sort") or "newest",
            "limit": requirements.get("limit") or 10,
        }
        for key in (
            "severity",
            "alert_type",
            "source_ip",
            "destination_ip",
            "hostname",
            "username",
            "time_window_minutes",
        ):
            if requirements.get(key) not in (None, ""):
                arguments[key] = requirements[key]
        return {"tool_name": "search_alerts", "arguments": arguments}
    if category == "incidents":
        incident_id = context.get("incident_id")
        if incident_id and not requirements:
            return {"tool_name": "get_incident_timeline", "arguments": {"incident_id": incident_id}}
        return {
            "tool_name": "search_incidents",
            "arguments": {
                "severity": requirements.get("severity"),
                "limit": requirements.get("limit") or 10,
            },
        }
    if category == "source_ip_activity":
        source_ip = requirements.get("source_ip") or context.get("source_ip")
        return {"tool_name": "get_source_ip_context", "arguments": {"source_ip": source_ip}} if source_ip else None
    if category == "response_registry":
        if requirements.get("source_ip"):
            arguments = {"source_ip": requirements["source_ip"]}
        else:
            arguments = {
                key: context[key]
                for key in ("registry_id", "source_ip")
                if context.get(key) not in (None, "")
            }
        if requirements.get("limit"):
            arguments["limit"] = requirements["limit"]
        return {"tool_name": "get_response_registry_context", "arguments": arguments} if arguments else None
    if category in {"events", "authentication_activity", "network_activity", "recon_activity"}:
        source_ip = requirements.get("source_ip") or context.get("source_ip")
        if requirements.get("alert_type") and not source_ip:
            return None
        if requirements and source_ip:
            arguments = {"source_ip": source_ip}
            if requirements.get("alert_type"):
                arguments["event_type"] = requirements["alert_type"]
            if requirements.get("limit"):
                arguments["limit"] = requirements["limit"]
        else:
            arguments = {
                key: context[key]
                for key in ("alert_id", "source_ip", "activity_id")
                if context.get(key) not in (None, "")
            }
            if requirements.get("limit"):
                arguments["limit"] = requirements["limit"]
        return {"tool_name": "get_related_events", "arguments": arguments} if arguments else None
    return None


def _compact_turn_resolution(value: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": _compact_scalar(value.get("status"), 64),
        "intent": _compact_scalar(value.get("intent"), 64),
        "relationship": _compact_scalar(value.get("relationship"), 64),
    }
    message = _compact_scalar(value.get("message"), 500)
    if message:
        result["message"] = message
    referent = _compact_turn_referent(value.get("referent"))
    if referent:
        result["referent"] = referent
    candidates = [
        entity
        for entity in (_compact_turn_entity(item) for item in (value.get("candidates") or [])[:6])
        if entity.get("type") and entity.get("id")
    ] if isinstance(value.get("candidates"), list) else []
    result["candidates"] = candidates
    return result


def _compact_turn_referent(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    if isinstance(value.get("entities"), list):
        entities = [
            entity
            for entity in (_compact_turn_entity(item) for item in value["entities"][:2])
            if entity.get("type") and entity.get("id")
        ]
        return {"entities": entities} if entities else None
    result = {
        key: compact
        for key, limit in (
            ("type", 64),
            ("id", 128),
            ("database_id", 32),
            ("sequence", 32),
            ("content", 700),
        )
        if (compact := _compact_scalar(value.get(key), limit)) is not None
    }
    entity = _compact_turn_entity(value.get("entity"))
    if entity.get("type") and entity.get("id"):
        result["entity"] = entity
    unresolved = value.get("value")
    if isinstance(unresolved, dict):
        result["value"] = {
            key: compact
            for key, limit in (("content", 500), ("turn_id", 128), ("assertion_type", 64))
            if (compact := _compact_scalar(unresolved.get(key), limit)) is not None
        }
    return result or None


def _compact_turn_entity(value: Any) -> dict[str, Any]:
    entity = _normalized_entity(value)
    if not entity:
        return {}
    result = {"type": entity["type"], "id": entity["id"]}
    alias = _compact_scalar(entity.get("display_alias"), 160)
    if alias:
        result["display_alias"] = alias
    return result


def _compact_turn_context(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: compact
        for key in _TURN_CONTEXT_IDENTITY_FIELDS
        if (compact := _compact_scalar(value.get(key), 256)) is not None
    }


def _compact_command_intent(payload: dict[str, Any]) -> dict[str, Any] | None:
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    command = context.get("command") if isinstance(context.get("command"), dict) else {}
    result = {
        key: compact
        for key, limit in (("id", 128), ("intent", 128), ("label", 160))
        if (compact := _compact_scalar(command.get(key), limit)) is not None
    }
    return result or None


def _compact_scalar(value: Any, limit: int) -> str | int | float | bool | None:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (dict, list, tuple, set)):
        return None
    text = str(value).strip()
    return text[:limit] if text else None


def _validate_resolved_entities(conn, *, owner_username: str, resolved: ResolvedExecutionContext) -> None:
    for entity in resolved.entities:
        validate_conversation_entity(
            conn,
            owner_username=owner_username,
            entity_type=entity["type"],
            entity_id=entity["id"],
        )


def _assert_execution_alignment(
    payload: dict[str, Any], resolved: ResolvedExecutionContext, packet: dict[str, Any]
) -> None:
    del packet
    payload_entity = _normalized_entity(payload.get("entity"))
    if resolved.active_entity is None:
        if payload_entity is not None:
            raise ConversationBoundaryError("Entityless planner result cannot carry a workflow execution entity.")
        return
    expected = _entity_identity(resolved.active_entity)
    if not payload_entity or _entity_identity(payload_entity) != expected:
        raise ConversationBoundaryError("Planner-selected entity and workflow execution entity do not match.")


def _normalized_entity(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    entity_type = str(value.get("type") or value.get("entity_type") or "").strip().lower().replace("-", "_")
    entity_id = str(value.get("id") or value.get("entity_id") or "").strip()
    if not entity_type or not entity_id:
        return None
    return {"type": entity_type, "id": entity_id, "display_alias": value.get("display_alias")}


def _distinct_entities(values: list[Any]) -> list[dict[str, Any]]:
    result = []
    for value in values:
        entity = _normalized_entity(value)
        if entity and not any(_entity_identity(item) == _entity_identity(entity) for item in result):
            result.append(entity)
    return result


def _entity_identity(entity: dict[str, Any]) -> tuple[str, str]:
    return str(entity.get("type") or ""), str(entity.get("id") or "")


def _entity_int(value: str, entity_type: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ConversationBoundaryError(f"Resolved {entity_type} identity must be an integer.") from error
    if parsed <= 0:
        raise ConversationBoundaryError(f"Resolved {entity_type} identity must be positive.")
    return parsed


def _deterministic_envelope(
    classification: WorkflowClassification,
    *,
    workflow: str,
    message: str,
    status: str,
    resolution: dict[str, Any],
    thread: dict[str, Any],
    user_turn: dict[str, Any],
    assistant_turn: dict[str, Any],
    selection,
) -> dict[str, Any]:
    return {
        "status": status,
        "workflow": workflow,
        "classification": classification.as_dict(),
        "result": {"answer": message, "reference_resolution": resolution},
        "metadata": {"read_only": True, "model_invoked": False},
        "lifecycle": {"mode": "sync", "status": "complete", "stage": "complete", "terminal": True, "stages": []},
        "conversation": _conversation_metadata(thread, user_turn, assistant_turn=assistant_turn, selection=selection),
        "error": None,
    }


def _conversation_metadata(thread, user_turn, *, assistant_turn, selection) -> dict[str, Any]:
    if hasattr(selection, "packet"):
        bounds = selection.packet.get("bounds", {})
        resolution = selection.resolution
        active_entity = selection.resolved_entity
    elif isinstance(selection, dict):
        bounds = selection.get("bounds", {})
        resolution = selection.get("resolution")
        active_entity = selection.get("active_entity")
    else:
        bounds, resolution, active_entity = {}, None, None
    return {
        "thread_id": thread.get("thread_id"),
        "thread_version": thread.get("version"),
        "user_turn": user_turn,
        "assistant_turn": assistant_turn,
        "reference_resolution": resolution,
        "active_entity": active_entity,
        "context_bounds": bounds,
        "authoritative_history": "postgresql",
    }


def _question(payload: dict[str, Any]) -> str:
    value = payload.get("prompt") or payload.get("question") or payload.get("message") or payload.get("instruction")
    return _required_text(value, "prompt", 2000)


def _required_text(value: Any, field_name: str, max_chars: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise SessionMemoryValidationError(f"{field_name} is required.")
    if len(text) > max_chars:
        raise SessionMemoryValidationError(f"{field_name} is too large.")
    return text


def _positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise SessionMemoryValidationError(f"{field_name} must be a positive integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise SessionMemoryValidationError(f"{field_name} must be a positive integer.") from error
    if parsed <= 0:
        raise SessionMemoryValidationError(f"{field_name} must be a positive integer.")
    return parsed


__all__ = [
    "ConversationActorUnavailableError",
    "ConversationBoundaryError",
    "ConversationContextError",
    "complete_worker_conversation",
    "fail_worker_conversation",
    "has_conversation_envelope",
    "prepare_worker_conversation",
    "queue_conversational_request",
    "reject_isolated_conversation",
    "run_conversational_workflow",
    "validate_original_conversation_workflow",
]
