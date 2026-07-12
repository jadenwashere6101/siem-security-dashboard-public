"""Detection Simulator API — authenticated dry-run pipeline preview.

See openspec/changes/add-detection-simulator-workspace/ for the approved
architecture. This route never calls conn.commit(); engines.detection_simulator
owns the rollback-only transaction boundary that guarantees zero durable
writes. This route must never call routes.ingest_routes' handlers directly.
"""
from flask import Blueprint, current_app, jsonify, request
from flask_login import login_required

from core.auth import analyst_or_super_admin_required
from engines.detection_config import get_all_effective_detection_rules
from engines.detection_simulator import SimulationValidationError, run_detection_simulation


detection_simulator_bp = Blueprint("detection_simulator", __name__)


@detection_simulator_bp.route("/detection-simulator/rules", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def list_simulator_rules():
    # Read-only reuse of the same rule listing /admin/detection-rules (super
    # admin only) uses, exposed to the analyst-or-super-admin boundary this
    # workspace needs for its rule selector. No rule data is mutated here.
    try:
        rules = get_all_effective_detection_rules()
    except Exception as error:
        current_app.logger.error("[DETECTION SIMULATOR] rules list failed: %s", error)
        return jsonify({"error": "Internal server error"}), 500

    return jsonify(
        {
            "rules": [
                {
                    "rule_id": rule["rule_id"],
                    "display_name": rule["display_name"],
                    "description": rule["description"],
                    "active": rule["active"],
                    "applicable_sources": rule.get("applicable_sources", []),
                }
                for rule in rules
            ]
        }
    ), 200


@detection_simulator_bp.route("/detection-simulator/run", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def run_simulation():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON"}), 400

    source = data.get("source")
    rule_id = data.get("rule_id")
    input_format = data.get("input_format")
    raw_lines = data.get("raw_lines")
    json_events = data.get("json_events")
    environment = data.get("environment") or "prod"

    if not isinstance(source, str) or not source:
        return jsonify({"error": "Missing required field: source"}), 400
    if not isinstance(rule_id, str) or not rule_id:
        return jsonify({"error": "Missing required field: rule_id"}), 400
    if not isinstance(input_format, str) or not input_format:
        return jsonify({"error": "Missing required field: input_format"}), 400
    if raw_lines is not None and not isinstance(raw_lines, list):
        return jsonify({"error": "raw_lines must be a list"}), 400
    if json_events is not None and not isinstance(json_events, list):
        return jsonify({"error": "json_events must be a list"}), 400
    if not isinstance(environment, str) or not environment.strip():
        return jsonify({"error": "environment must be a non-empty string"}), 400

    try:
        result = run_detection_simulation(
            source=source,
            rule_id=rule_id,
            input_format=input_format,
            raw_lines=raw_lines,
            json_events=json_events,
            environment=environment,
        )
        return jsonify(result), 200
    except SimulationValidationError as error:
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        current_app.logger.error("[DETECTION SIMULATOR] run failed: %s", error)
        return jsonify({"error": "Internal server error"}), 500
