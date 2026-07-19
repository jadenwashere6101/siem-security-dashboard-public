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
    chat_about_siem,
    explain_context,
    service_error_response,
)
from core.ai.drafting_service import (
    DraftValidationError,
    create_draft,
    service_error_response as draft_service_error_response,
)
from core.ai.readiness import get_ai_gateway_status
from core.ai.repo_assistant_service import (
    RepoAssistantValidationError,
    answer_repo_question,
    get_repo_assistant_status,
)
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
