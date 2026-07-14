from flask import Blueprint, current_app, jsonify
from flask_login import login_required

from core.auth import analyst_or_super_admin_required
from core.db import get_db_connection
from engines.severity_response_matrix import build_severity_response_matrix


severity_response_matrix_bp = Blueprint("severity_response_matrix", __name__)


@severity_response_matrix_bp.route("/api/severity-response-matrix", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def get_severity_response_matrix():
    conn = None
    try:
        conn = get_db_connection()
        return jsonify(build_severity_response_matrix(conn)), 200
    except Exception as error:
        current_app.logger.error("Error in get_severity_response_matrix: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()
