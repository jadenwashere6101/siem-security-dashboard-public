from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from core.audit_helpers import log_audit_event
from core.auth import analyst_or_super_admin_required, super_admin_required
from integrations.base_integration import (
    SimulatedCircuitBreakerControlError,
    get_simulated_circuit_breaker_dict,
    manual_enable_half_open_probe_simulated_circuit_breaker,
    manual_force_open_simulated_circuit_breaker,
    manual_reset_simulated_circuit_breaker,
)
from integrations.integration_registry import (
    get_integration_status,
    normalize_registered_integration_adapter_name,
)

integration_bp = Blueprint("integrations", __name__)

_EVENT_CIRCUIT_RESET = "SIMULATION_CIRCUIT_BREAKER_RESET"
_EVENT_CIRCUIT_FORCE_OPEN = "SIMULATION_CIRCUIT_BREAKER_FORCE_OPEN"
_EVENT_CIRCUIT_ENABLE_HALF_OPEN = "SIMULATION_CIRCUIT_BREAKER_ENABLE_HALF_OPEN"


def _circuit_control_json():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, (jsonify({"error": "invalid_body", "message": "JSON object body is required."}), 400)
    reason = data.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return None, (
            jsonify(
                {
                    "error": "invalid_body",
                    "message": "Field reason is required and must be non-empty.",
                }
            ),
            400,
        )
    raw_override = data.get("override_cooldown")
    override_cooldown = bool(raw_override) if raw_override is not None else False
    return {"reason": reason.strip(), "override_cooldown": override_cooldown}, None


def _resolved_adapter_or_404(adapter_name: str):
    key = normalize_registered_integration_adapter_name(adapter_name)
    if key is None:
        return None, (
            jsonify({"error": "not_found", "message": "Unknown integration adapter."}),
            404,
        )
    return key, None


def _log_circuit_control(
    event_type: str,
    *,
    adapter_key: str,
    previous_state: str,
    circuit_breaker: dict,
    reason: str,
    override_cooldown: bool | None = None,
):
    details = {
        "adapter": adapter_key,
        "previous_state": previous_state,
        "new_state": circuit_breaker.get("state"),
        "reason": reason,
        "half_open_probe_available": circuit_breaker.get("half_open_probe_available"),
        "cooldown_until": circuit_breaker.get("cooldown_until"),
    }
    if override_cooldown is not None:
        details["override_cooldown"] = override_cooldown
    log_audit_event(
        event_type,
        actor_username=current_user.id,
        actor_role=getattr(current_user, "role", None),
        http_method=request.method,
        request_path=request.path,
        source_ip=request.remote_addr,
        details=details,
    )


@integration_bp.route("/integrations/status", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def integration_status_route():
    try:
        return jsonify(get_integration_status()), 200
    except Exception as error:
        current_app.logger.error("Error in integration_status_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500


@integration_bp.route("/integrations/<adapter_name>/circuit-breaker/reset", methods=["POST"])
@login_required
@super_admin_required
def integration_circuit_breaker_reset_route(adapter_name: str):
    body, err = _circuit_control_json()
    if err is not None:
        return err
    adapter_key, err = _resolved_adapter_or_404(adapter_name)
    if err is not None:
        return err
    prev = get_simulated_circuit_breaker_dict(adapter_key)["state"]
    try:
        updated = manual_reset_simulated_circuit_breaker(
            adapter_key,
            actor_username=current_user.id,
            reason=body["reason"],
        )
    except SimulatedCircuitBreakerControlError as exc:
        return jsonify({"error": "control_rejected", "message": exc.message}), exc.status_code
    _log_circuit_control(
        _EVENT_CIRCUIT_RESET,
        adapter_key=adapter_key,
        previous_state=prev,
        circuit_breaker=updated,
        reason=body["reason"],
    )
    return jsonify({"adapter": adapter_key, "circuit_breaker": updated}), 200


@integration_bp.route("/integrations/<adapter_name>/circuit-breaker/force-open", methods=["POST"])
@login_required
@super_admin_required
def integration_circuit_breaker_force_open_route(adapter_name: str):
    body, err = _circuit_control_json()
    if err is not None:
        return err
    adapter_key, err = _resolved_adapter_or_404(adapter_name)
    if err is not None:
        return err
    prev = get_simulated_circuit_breaker_dict(adapter_key)["state"]
    try:
        updated = manual_force_open_simulated_circuit_breaker(
            adapter_key,
            actor_username=current_user.id,
            reason=body["reason"],
        )
    except SimulatedCircuitBreakerControlError as exc:
        return jsonify({"error": "control_rejected", "message": exc.message}), exc.status_code
    _log_circuit_control(
        _EVENT_CIRCUIT_FORCE_OPEN,
        adapter_key=adapter_key,
        previous_state=prev,
        circuit_breaker=updated,
        reason=body["reason"],
    )
    return jsonify({"adapter": adapter_key, "circuit_breaker": updated}), 200


@integration_bp.route(
    "/integrations/<adapter_name>/circuit-breaker/enable-half-open",
    methods=["POST"],
)
@login_required
@super_admin_required
def integration_circuit_breaker_enable_half_open_route(adapter_name: str):
    body, err = _circuit_control_json()
    if err is not None:
        return err
    adapter_key, err = _resolved_adapter_or_404(adapter_name)
    if err is not None:
        return err
    prev = get_simulated_circuit_breaker_dict(adapter_key)["state"]
    try:
        updated = manual_enable_half_open_probe_simulated_circuit_breaker(
            adapter_key,
            actor_username=current_user.id,
            reason=body["reason"],
            override_cooldown=body["override_cooldown"],
        )
    except SimulatedCircuitBreakerControlError as exc:
        return jsonify({"error": "control_rejected", "message": exc.message}), exc.status_code
    _log_circuit_control(
        _EVENT_CIRCUIT_ENABLE_HALF_OPEN,
        adapter_key=adapter_key,
        previous_state=prev,
        circuit_breaker=updated,
        reason=body["reason"],
        override_cooldown=body["override_cooldown"],
    )
    return jsonify({"adapter": adapter_key, "circuit_breaker": updated}), 200
