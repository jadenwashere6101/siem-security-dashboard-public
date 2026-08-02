from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from core.ai.action_service import (
    AiActionValidationError,
    confirm_ai_action,
    preview_ai_action,
    service_error_response as action_service_error_response,
)

from core.ai.explainer_service import (
    AiContextError,
    service_error_response,
)
from core.ai.investigation_service import (
    InvestigationPlannerError,
    service_error_response as investigation_service_error_response,
)
from core.ai.drafting_service import (
    DraftValidationError,
    service_error_response as draft_service_error_response,
)
from core.ai.readiness import get_ai_gateway_status
from core.ai.repo_assistant_service import (
    RepoAssistantValidationError,
    answer_repo_question,
    get_repo_assistant_status,
)
from core.ai.repo_assistant_request_service import queue_repo_assistant_request, read_repo_assistant_request
from core.ai.workflow_orchestrator import (
    WorkflowValidationError,
    legacy_chat_about_siem as chat_about_siem,
    legacy_create_draft as create_draft,
    legacy_explain_context as explain_context,
    legacy_run_investigation as run_investigation,
    run_workflow,
)
from core.ai.workflow_request_service import queue_workflow_request, read_workflow_request
from core.ai.session_memory_service import (
    create_thread_request,
    error_payload as session_memory_error_payload,
    list_thread_turns_request,
    read_thread_request,
    reset_thread_request,
    submit_thread_turn_request,
)
from core.ai.session_memory_store import SessionMemoryError
from core.ai.conversation_context import ConversationContextError
from core.ai.conversation_orchestration_service import run_conversational_workflow
from core.audit_helpers import log_audit_event
from core.auth import analyst_or_super_admin_required, super_admin_required

ai_bp = Blueprint("ai", __name__)


def _thread_owner() -> str:
    return str(getattr(current_user, "id", "") or "").strip()


def _thread_audit(event_type: str, *, details: dict[str, object]) -> None:
    log_audit_event(
        event_type,
        actor_username=getattr(current_user, "id", None),
        actor_role=getattr(current_user, "role", None),
        http_method=request.method,
        request_path=request.path,
        source_ip=request.remote_addr,
        details=details,
    )


def _thread_error(error: Exception):
    if isinstance(error, SessionMemoryError):
        payload, status_code = session_memory_error_payload(error)
        _thread_audit(
            "ANAKIN_THREAD_ACCESS_DENIED" if status_code in {403, 404} else "ANAKIN_THREAD_REQUEST_REJECTED",
            details={
                "thread_id": (request.view_args or {}).get("thread_id"),
                "error_code": payload["error_code"],
                "status_code": status_code,
            },
        )
        return jsonify(payload), status_code
    current_app.logger.error("Anakin session-memory route failed: %s", error)
    return jsonify({"status": "error", "error": "Internal server error"}), 500


@ai_bp.route("/ai/status", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def ai_status_route():
    try:
        return jsonify(get_ai_gateway_status()), 200
    except Exception as error:
        current_app.logger.error("Error in ai_status_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500


@ai_bp.route("/ai/threads", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def create_ai_thread_route():
    try:
        result, status_code = create_thread_request(request.get_json(silent=True), owner_username=_thread_owner())
        thread = result["thread"]
        _thread_audit(
            "ANAKIN_THREAD_CREATE" if result["created"] else "ANAKIN_THREAD_RESOLVE",
            details={
                "thread_id": thread["thread_id"],
                "domain": thread["domain"],
                "entity_type": thread["primary_entity"]["type"],
                "is_default": thread["is_default"],
                "created": result["created"],
            },
        )
        return jsonify(result), status_code
    except Exception as error:
        return _thread_error(error)


@ai_bp.route("/ai/threads/<thread_id>", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def read_ai_thread_route(thread_id):
    try:
        result, status_code = read_thread_request(thread_id, owner_username=_thread_owner())
        return jsonify(result), status_code
    except Exception as error:
        return _thread_error(error)


@ai_bp.route("/ai/threads/<thread_id>/turns", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def list_ai_thread_turns_route(thread_id):
    try:
        result, status_code = list_thread_turns_request(
            thread_id,
            owner_username=_thread_owner(),
            cursor=request.args.get("cursor"),
            limit=request.args.get("limit", 50),
        )
        return jsonify(result), status_code
    except Exception as error:
        return _thread_error(error)


@ai_bp.route("/ai/threads/<thread_id>/turns", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def submit_ai_thread_turn_route(thread_id):
    try:
        result, status_code = submit_thread_turn_request(
            thread_id,
            request.get_json(silent=True),
            owner_username=_thread_owner(),
        )
        _thread_audit(
            "ANAKIN_THREAD_TURN_RECORDED" if result["created"] else "ANAKIN_THREAD_TURN_DUPLICATE",
            details={
                "thread_id": thread_id,
                "turn_id": result["turn"]["turn_id"],
                "sequence": result["turn"]["sequence"],
                "assertion_type": result["turn"]["assertion_type"],
                "created": result["created"],
                "llm_invoked": False,
            },
        )
        return jsonify(result), status_code
    except Exception as error:
        return _thread_error(error)


@ai_bp.route("/ai/threads/<thread_id>/reset", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def reset_ai_thread_route(thread_id):
    try:
        result, status_code = reset_thread_request(
            thread_id,
            request.get_json(silent=True),
            owner_username=_thread_owner(),
        )
        _thread_audit(
            "ANAKIN_THREAD_RESET",
            details={
                "thread_id": thread_id,
                "replacement_thread_id": result["thread"]["thread_id"],
                "created": result["created"],
            },
        )
        return jsonify(result), status_code
    except Exception as error:
        return _thread_error(error)


@ai_bp.route("/ai/explain", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def ai_explain_route():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON object body is required."}), 400

    try:
        result = explain_context(payload)
        return jsonify(result.payload), result.status_code
    except AiContextError as error:
        result = service_error_response(error)
        return jsonify(result.payload), result.status_code
    except Exception as error:
        current_app.logger.error("Error in ai_explain_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500


@ai_bp.route("/ai/chat", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def ai_chat_route():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON object body is required."}), 400

    try:
        result = chat_about_siem(payload)
        return jsonify(result.payload), result.status_code
    except AiContextError as error:
        result = service_error_response(error)
        return jsonify(result.payload), result.status_code
    except Exception as error:
        current_app.logger.error("Error in ai_chat_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500


@ai_bp.route("/ai/workflows", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def ai_workflows_route():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON object body is required."}), 400

    try:
        result = run_conversational_workflow(
            payload,
            owner_username=_thread_owner(),
            actor_role=str(getattr(current_user, "role", "") or ""),
        )
        return jsonify(result.payload), result.status_code
    except SessionMemoryError as error:
        return _thread_error(error)
    except ConversationContextError as error:
        return jsonify({"status": "error", "error_code": error.error_code, "error": str(error)}), error.status_code
    except (AiContextError, DraftValidationError, InvestigationPlannerError, WorkflowValidationError) as error:
        status_code = getattr(error, "status_code", 400)
        return jsonify(
            {
                "status": getattr(error, "error_code", "invalid_workflow_request"),
                "error_code": getattr(error, "error_code", "invalid_workflow_request"),
                "workflow": None,
                "classification": None,
                "lifecycle": {"mode": "sync", "stage": "failed", "stages": [{"stage": "failed", "status": "failed"}]},
                "result": {},
                "metadata": {},
                "error": str(error),
            }
        ), status_code
    except Exception as error:
        current_app.logger.error("Error in ai_workflows_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500


@ai_bp.route("/ai/workflows/requests", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def ai_workflow_requests_route():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON object body is required."}), 400

    try:
        result, status_code = queue_workflow_request(
            payload,
            actor_username=str(getattr(current_user, "id", "") or ""),
            actor_role=str(getattr(current_user, "role", "") or ""),
        )
        log_audit_event(
            "ai_workflow_request_queued",
            actor_username=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={
                "workflow": result.get("workflow"),
                "request_id": result.get("request_id"),
                "status": result.get("status"),
                "created": result.get("created"),
                "read_only": True,
            },
        )
        return jsonify(result), status_code
    except SessionMemoryError as error:
        return _thread_error(error)
    except ConversationContextError as error:
        return jsonify({"status": "error", "error_code": error.error_code, "error": str(error)}), error.status_code
    except WorkflowValidationError as error:
        status_code = getattr(error, "status_code", 400)
        return jsonify(
            {
                "status": getattr(error, "error_code", "invalid_workflow_request"),
                "error_code": getattr(error, "error_code", "invalid_workflow_request"),
                "workflow": None,
                "classification": None,
                "lifecycle": {"mode": "polling", "stage": "failed", "stages": [{"stage": "failed", "status": "failed"}]},
                "result": {},
                "metadata": {},
                "error": str(error),
            }
        ), status_code
    except Exception as error:
        current_app.logger.error("Error in ai_workflow_requests_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500


@ai_bp.route("/ai/workflows/requests/<request_id>", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def ai_workflow_request_status_route(request_id):
    try:
        result, status_code = read_workflow_request(
            request_id,
            actor_username=str(getattr(current_user, "id", "") or ""),
        )
        return jsonify(result), status_code
    except Exception as error:
        current_app.logger.error("Error in ai_workflow_request_status_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500


@ai_bp.route("/ai/drafts", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def ai_drafts_route():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON object body is required."}), 400

    try:
        result = create_draft(payload)
        return jsonify(result.payload), result.status_code
    except (AiContextError, DraftValidationError) as error:
        result = draft_service_error_response(error)
        return jsonify(result.payload), result.status_code
    except Exception as error:
        current_app.logger.error("Error in ai_drafts_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500


@ai_bp.route("/ai/investigations", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def ai_investigations_route():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON object body is required."}), 400

    try:
        result = run_investigation(payload)
        return jsonify(result.payload), result.status_code
    except (AiContextError, InvestigationPlannerError) as error:
        result = investigation_service_error_response(error)
        return jsonify(result.payload), result.status_code
    except Exception as error:
        current_app.logger.error("Error in ai_investigations_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500


@ai_bp.route("/ai/actions/preview", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def ai_action_preview_route():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON object body is required."}), 400

    try:
        result = preview_ai_action(payload, actor=current_user)
        return jsonify(result.payload), result.status_code
    except AiActionValidationError as error:
        result = action_service_error_response(error)
        return jsonify(result.payload), result.status_code
    except Exception as error:
        current_app.logger.error("Error in ai_action_preview_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500


@ai_bp.route("/ai/actions/confirm", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def ai_action_confirm_route():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON object body is required."}), 400

    try:
        result = confirm_ai_action(payload, actor=current_user)
        return jsonify(result.payload), result.status_code
    except AiActionValidationError as error:
        result = action_service_error_response(error)
        return jsonify(result.payload), result.status_code
    except Exception as error:
        current_app.logger.error("Error in ai_action_confirm_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500


@ai_bp.route("/ai/repo/status", methods=["GET"])
@login_required
@super_admin_required
def ai_repo_status_route():
    try:
        return jsonify(get_repo_assistant_status()), 200
    except Exception as error:
        current_app.logger.error("Error in ai_repo_status_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500


@ai_bp.route("/ai/repo/chat", methods=["POST"])
@login_required
@super_admin_required
def ai_repo_chat_route():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON object body is required."}), 400

    try:
        result = answer_repo_question(payload)
        return jsonify(result.payload), result.status_code
    except RepoAssistantValidationError as error:
        return jsonify({"status": error.error_code, "error": str(error)}), error.status_code
    except Exception as error:
        current_app.logger.error("Error in ai_repo_chat_route status=failed error=%s", error)
        return jsonify({"error": "Internal server error"}), 500


@ai_bp.route("/ai/repo/requests", methods=["POST"])
@login_required
@super_admin_required
def ai_repo_request_route():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON object body is required."}), 400

    try:
        body, status_code = queue_repo_assistant_request(
            payload,
            actor_username=getattr(current_user, "username", None) or "unknown",
            actor_role=getattr(current_user, "role", None) or "viewer",
        )
        return jsonify(body), status_code
    except RepoAssistantValidationError as error:
        return jsonify({"status": error.error_code, "error": str(error)}), error.status_code
    except Exception as error:
        current_app.logger.error("Error in ai_repo_request_route status=failed error=%s", error)
        return jsonify({"error": "Internal server error"}), 500


@ai_bp.route("/ai/repo/requests/<request_id>", methods=["GET"])
@login_required
@super_admin_required
def ai_repo_request_status_route(request_id):
    try:
        body, status_code = read_repo_assistant_request(
            request_id,
            actor_username=getattr(current_user, "username", None) or "unknown",
        )
        return jsonify(body), status_code
    except Exception as error:
        current_app.logger.error("Error in ai_repo_request_status_route status=failed error=%s", error)
        return jsonify({"error": "Internal server error"}), 500
