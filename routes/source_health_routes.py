from flask import Blueprint, current_app, jsonify
from flask_login import login_required

from core.auth import analyst_or_super_admin_required
from core.db import get_db_connection
from core.source_health import aggregate_source_health


source_health_bp = Blueprint("source_health", __name__)


@source_health_bp.route("/source-health", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def get_source_health():
    conn = None
    try:
        conn = get_db_connection()
        return jsonify(aggregate_source_health(conn)), 200
    except Exception as error:
        current_app.logger.error("Error in get_source_health: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()

