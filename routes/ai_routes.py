from __future__ import annotations

from flask import Blueprint, current_app, jsonify
from flask_login import login_required

from core.ai.readiness import get_ai_gateway_status
from core.auth import analyst_or_super_admin_required

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
