"""Detection Simulator API — authenticated dry-run pipeline preview.

See openspec/changes/add-detection-simulator-workspace/ for the approved
architecture. This route never calls conn.commit(); engines.detection_simulator
owns the rollback-only transaction boundary that guarantees zero durable
writes. This route must never call routes.ingest_routes' handlers directly.

Version 3 Sigma subset import accepts ``simulation_mode='sigma_subset_import'``
and ``sigma_yaml``. The backend compiles Sigma into the temporary-rule model
and evaluates only through that path — never a second engine.
"""
from flask import Blueprint, current_app, jsonify, request
from flask_login import login_required

from core.auth import analyst_or_super_admin_required
from engines.detection_config import get_all_effective_detection_rules
from engines.detection_simulator import (
    SIGMA_FORBIDDEN_REQUEST_KEYS,
    SIMULATION_MODE_EXISTING_PRODUCTION_RULE,
    SIMULATION_MODE_SIGMA_SUBSET_IMPORT,
    SIMULATION_MODE_TEMPORARY_PLAYGROUND_RULE,
    TEMPORARY_RULE_FORBIDDEN_REQUEST_KEYS,
    SimulationValidationError,
    run_detection_simulation,
)


detection_simulator_bp = Blueprint("detection_simulator", __name__)


def _validation_error_response(error):
    payload = {"error": str(error)}
    details = getattr(error, "details", None)
    if isinstance(details, dict):
        payload["validation"] = details
    return jsonify(payload), 400


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

    simulation_mode = data.get("simulation_mode") or SIMULATION_MODE_EXISTING_PRODUCTION_RULE
    environment = data.get("environment") or "prod"

    if not isinstance(environment, str) or not environment.strip():
        return jsonify({"error": "environment must be a non-empty string"}), 400

    try:
        if simulation_mode == SIMULATION_MODE_SIGMA_SUBSET_IMPORT:
            forbidden_keys = sorted(key for key in SIGMA_FORBIDDEN_REQUEST_KEYS if key in data)
            if forbidden_keys:
                return jsonify(
                    {
                        "error": (
                            "Sigma subset requests do not support persisted drafts, promotion, "
                            f"or history-aware fields: {', '.join(forbidden_keys)}"
                        ),
                        "validation": {
                            "class": "invalid_request",
                            "element": ",".join(forbidden_keys),
                            "reason": "Persisted-rule and alternate execution fields are rejected",
                        },
                    }
                ), 400

            sigma_yaml = data.get("sigma_yaml")
            input_text = data.get("input_text")
            sample_events = data.get("sample_events")
            json_events = data.get("json_events")
            input_format = data.get("input_format")
            event_type = data.get("event_type")

            if sigma_yaml is not None and not isinstance(sigma_yaml, str):
                return jsonify({"error": "sigma_yaml must be a string"}), 400
            if input_text is not None and not isinstance(input_text, str):
                return jsonify({"error": "input_text must be a string"}), 400
            if sample_events is not None and not isinstance(sample_events, list):
                return jsonify({"error": "sample_events must be a list"}), 400
            if json_events is not None and not isinstance(json_events, list):
                return jsonify({"error": "json_events must be a list"}), 400
            if input_format is not None and not isinstance(input_format, str):
                return jsonify({"error": "input_format must be a string"}), 400
            if event_type is not None and not isinstance(event_type, str):
                return jsonify({"error": "event_type must be a string"}), 400

            result = run_detection_simulation(
                simulation_mode=simulation_mode,
                sigma_yaml=sigma_yaml,
                input_format=input_format,
                event_type=event_type,
                input_text=input_text,
                sample_events=sample_events,
                json_events=json_events,
                environment=environment,
            )
        elif simulation_mode == SIMULATION_MODE_TEMPORARY_PLAYGROUND_RULE:
            forbidden_keys = sorted(key for key in TEMPORARY_RULE_FORBIDDEN_REQUEST_KEYS if key in data)
            if forbidden_keys:
                return jsonify(
                    {
                        "error": (
                            "Temporary playground requests do not support persisted drafts or "
                            f"history-aware fields: {', '.join(forbidden_keys)}"
                        )
                    }
                ), 400

            temporary_rule = data.get("temporary_rule")
            input_text = data.get("input_text")
            sample_events = data.get("sample_events")
            json_events = data.get("json_events")

            if input_text is not None and not isinstance(input_text, str):
                return jsonify({"error": "input_text must be a string"}), 400
            if sample_events is not None and not isinstance(sample_events, list):
                return jsonify({"error": "sample_events must be a list"}), 400
            if json_events is not None and not isinstance(json_events, list):
                return jsonify({"error": "json_events must be a list"}), 400

            result = run_detection_simulation(
                simulation_mode=simulation_mode,
                temporary_rule=temporary_rule,
                input_text=input_text,
                sample_events=sample_events,
                json_events=json_events,
                environment=environment,
            )
        else:
            source = data.get("source")
            rule_id = data.get("rule_id")
            input_format = data.get("input_format")
            raw_lines = data.get("raw_lines")
            json_events = data.get("json_events")

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

            result = run_detection_simulation(
                simulation_mode=SIMULATION_MODE_EXISTING_PRODUCTION_RULE,
                source=source,
                rule_id=rule_id,
                input_format=input_format,
                raw_lines=raw_lines,
                json_events=json_events,
                environment=environment,
            )
        return jsonify(result), 200
    except SimulationValidationError as error:
        return _validation_error_response(error)
    except Exception as error:
        current_app.logger.error("[DETECTION SIMULATOR] run failed: %s", error)
        return jsonify({"error": "Internal server error"}), 500
