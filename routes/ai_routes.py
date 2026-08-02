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
from core.audit_helpers import log_audit_event
from core.auth import analyst_or_super_admin_required, super_admin_required

ai_bp = Blueprint("ai", __name__)


@ai_bp.route("/ai/status", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def ai_status_route():
    try:
        return jsonify(get_ai_gateway_status()), 200
    except Exception as error:
        current_app.logger.error("Error in ai_status_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500


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
        result = run_workflow(payload)
        return jsonify(result.payload), result.status_code
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
