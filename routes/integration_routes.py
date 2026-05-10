from flask import Blueprint, current_app, jsonify
from flask_login import login_required

from core.auth import analyst_or_super_admin_required
from integrations.integration_registry import get_integration_status


integration_bp = Blueprint("integrations", __name__)


@integration_bp.route("/integrations/status", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def integration_status_route():
    try:
        return jsonify(get_integration_status()), 200
    except Exception as error:
        current_app.logger.error("Error in integration_status_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500
