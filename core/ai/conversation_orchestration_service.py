from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from core.ai.config import load_ai_gateway_config
from core.ai.conversation_context import (
    ConversationContextError,
    conversation_budget,
    select_conversation_context,
)
from core.ai.session_memory_service import validate_conversation_entity, validate_owned_thread
from core.ai.session_memory_store import (
    SessionMemoryError,
    SessionMemoryValidationError,
    append_turn,
    create_evidence,
    fail_execution_turn,
    finalize_execution_turn,
    get_turn_by_client_request,
    get_turn_by_id,
    linked_workflow_request_for_turn,
    link_async_request,
    serialize_turn,
    utc_now,
)
from core.ai.workflow_orchestrator import (
    WORKFLOW_PROFILES,
    WORKFLOW_QUICK_EXPLAIN,
    WorkflowClassification,
    WorkflowResult,
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


def has_conversation_envelope(payload: Any) -> bool:
    return isinstance(payload, dict) and payload.get("conversation") is not None


def reject_isolated_conversation(payload: dict[str, Any], *, workflow: str) -> None:
    if workflow in ISOLATED_WORKFLOWS and has_conversation_envelope(payload):
        raise ConversationBoundaryError(f"{workflow.replace('_', ' ').title()} cannot use SIEM conversation memory.")


def run_conversational_workflow(
    payload: dict[str, Any],
    *,
    owner_username: str,
    actor_role: str,
    gateway=None,
    config=None,
) -> WorkflowResult:
    classification = classify_workflow(payload)
    workflow = classification.classified_workflow
    reject_isolated_conversation(payload, workflow=workflow)
    if not has_conversation_envelope(payload):
        return run_workflow(payload, gateway=gateway, config=config)
    if workflow != WORKFLOW_QUICK_EXPLAIN:
        raise ConversationBoundaryError("Conversational long-running workflows must use the async request route.")
    resolved_config = config if config is not None else load_ai_gateway_config()
    prepared = _prepare_submission(
        payload,
        workflow=workflow,
        owner_username=owner_username,
        classification=classification,
        resolved_config=resolved_config,
    )
    if prepared.get("duplicate_result") is not None:
        return WorkflowResult(prepared["duplicate_result"], 200)
    if prepared.get("deterministic_result") is not None:
        return WorkflowResult(prepared["deterministic_result"], 200)
    execution_payload = _with_context(payload, prepared["selection"].packet)
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
) -> tuple[dict[str, Any], int]:
    workflow = classification.classified_workflow
    reject_isolated_conversation(payload, workflow=workflow)
    if workflow not in ASYNC_CONVERSATION_WORKFLOWS:
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
    profile = load_ai_gateway_config().profile(WORKFLOW_PROFILES[workflow])
    selection = select_conversation_context(
        conn,
        thread=thread,
        owner_username=job["actor_username"],
        question=_question(payload),
        workflow=workflow,
        max_chars=conversation_budget(profile_max_prompt_chars=profile.max_prompt_chars, workflow=workflow),
    )
    execution = {
        "thread_id": thread_id,
        "turn_id": int(turn_id),
        "expected_thread_version": turn["thread_version_after_append"],
        "selection": selection,
    }
    return _with_context(payload, selection.packet, execution=execution), current_role


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
            "context_bounds": execution_payload.get("selection", {}).get("bounds", {}),
            "authoritative_history": "postgresql",
        }
        return WorkflowResult(enriched, result.status_code)
    content = _assistant_content(result.payload, workflow=job["workflow"])
    if not content:
        raise ConversationOrchestrationError("Workflow completed without analyst-facing assistant content.")
    structured = _assistant_structured_payload(
        result.payload,
        workflow=job["workflow"],
        request_id=job.get("request_id"),
    )
    completed_user, assistant_turn, thread = finalize_execution_turn(
        conn,
        thread_id=job["thread_id"],
        owner_username=job["actor_username"],
        user_turn_id=int(job["turn_id"]),
        expected_thread_version=int(user_turn["thread_version_after_append"]),
        workflow=job["workflow"],
        content=content,
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
) -> dict[str, Any]:
    if "_conversation_execution" in payload or "conversation_context" in payload:
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
        selection = select_conversation_context(
            conn,
            thread=thread,
            owner_username=owner_username,
            question=_question(payload),
            workflow=workflow,
            max_chars=conversation_budget(profile_max_prompt_chars=profile.max_prompt_chars, workflow=workflow),
        )
        resolution = selection.resolution
        if resolution.get("intent") == "correction":
            assertion_type = "correction"
        elif resolution.get("status") in {"clarification_required", "unresolved"}:
            assertion_type = "unresolved_question"
        else:
            assertion_type = "analyst_statement"
        parent_turn_id = None
        if assertion_type == "correction":
            referent = resolution.get("referent") if isinstance(resolution.get("referent"), dict) else {}
            parent_turn_id = referent.get("database_id")
        entity_snapshot = _entity_snapshot(payload, thread, resolution)
        for entity in entity_snapshot.get("entities", []):
            validate_conversation_entity(
                conn,
                owner_username=owner_username,
                entity_type=entity.get("type"),
                entity_id=entity.get("id"),
            )
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
            structured_payload={"reference_resolution": resolution},
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
        }
        if resolution.get("status") in {"clarification_required", "unresolved", "command_required"}:
            message = str(resolution.get("message") or "Clarify the referenced investigation context before continuing.")
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
                    "provenance": {"type": "deterministic_reference_resolver"},
                    "reference_resolution": resolution,
                },
                entity_snapshot=entity_snapshot,
            )
            conn.commit()
            prepared["deterministic_result"] = _deterministic_envelope(
                classification,
                workflow=workflow,
                message=message,
                resolution=resolution,
                thread=final_thread,
                user_turn=completed_user,
                assistant_turn=assistant_turn,
                selection=selection,
            )
            return prepared
        if create_async_request:
            server_payload = {
                **payload,
                "client_request_id": client_request_id,
                "_conversation_execution": {
                    "thread_id": thread_id,
                    "turn_id": user_turn["id"],
                    "expected_thread_version": user_turn["thread_version_after_append"],
                },
            }
            request_row, request_created = create_or_get_request(
                conn,
                workflow=workflow,
                context_type=payload.get("context_type"),
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
    content = _assistant_content(result.payload, workflow=prepared["workflow"])
    if not content:
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
            content=content,
            client_request_id=f"{prepared['user_turn']['client_request_id']}:assistant",
            structured_payload=_assistant_structured_payload(result.payload, workflow=prepared["workflow"]),
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
            },
        }
    return result


def _assistant_content(payload: dict[str, Any], *, workflow: str) -> str:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    if workflow in {"quick_explain", "decision_support"}:
        value = result.get("answer")
    elif workflow == "deep_investigate":
        investigation = result.get("investigation") if isinstance(result.get("investigation"), dict) else {}
        value = investigation.get("summary") or result.get("summary") or result.get("answer")
    elif workflow == "generate_artifact":
        value = result.get("draft") or result.get("artifact")
    else:
        value = result.get("answer")
    if isinstance(value, (dict, list)):
        text = json.dumps(value, default=str, sort_keys=True)
    else:
        text = str(value or "").strip()
    return text if len(text) <= 8000 else f"{text[:7950]}... [compacted for conversation storage]"


def _generation_failed(payload: dict[str, Any], status_code: int) -> bool:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    statuses = {str(payload.get("status") or "").lower(), str(result.get("status") or "").lower()}
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


def _assistant_structured_payload(payload: dict[str, Any], *, workflow: str, request_id: str | None = None) -> dict[str, Any]:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    status = str(result.get("status") or payload.get("status") or "unknown")
    structured = {
        "confidence": "low" if status in {"partial", "degraded", "insufficient_context"} else "medium",
        "provenance": {"type": "model_inference", "workflow": workflow, "request_id": request_id},
        "result_status": status,
    }
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


def _entity_snapshot(payload: dict[str, Any], thread: dict[str, Any], resolution: dict[str, Any]) -> dict[str, Any]:
    entities = []
    supplied = payload.get("entity") if isinstance(payload.get("entity"), dict) else {}
    supplied_type = supplied.get("type") or payload.get("context_type")
    supplied_id = supplied.get("id") or supplied.get("alert_id") or supplied.get("incident_id") or supplied.get("source_ip")
    if supplied_type and supplied_id not in (None, ""):
        entities.append({"type": str(supplied_type).lower().replace("-", "_"), "id": str(supplied_id)})
    candidates = resolution.get("candidates") if isinstance(resolution.get("candidates"), list) else []
    entities.extend(item for item in candidates if isinstance(item, dict))
    if not entities and isinstance(thread.get("primary_entity"), dict):
        entities.append(thread["primary_entity"])
    active = None
    referent = resolution.get("referent") if isinstance(resolution.get("referent"), dict) else None
    if referent and referent.get("type") not in {"assistant_turn", "unresolved_question"} and referent.get("id"):
        active = referent
    elif entities:
        active = entities[0]
    return {"active_entity": active, "entities": entities[:20]}


def _deterministic_envelope(
    classification: WorkflowClassification,
    *,
    workflow: str,
    message: str,
    resolution: dict[str, Any],
    thread: dict[str, Any],
    user_turn: dict[str, Any],
    assistant_turn: dict[str, Any],
    selection,
) -> dict[str, Any]:
    return {
        "status": resolution.get("status"),
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
    elif isinstance(selection, dict):
        bounds = selection.get("bounds", {})
        resolution = selection.get("resolution")
    else:
        bounds, resolution = {}, None
    return {
        "thread_id": thread.get("thread_id"),
        "thread_version": thread.get("version"),
        "user_turn": user_turn,
        "assistant_turn": assistant_turn,
        "reference_resolution": resolution,
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
]
