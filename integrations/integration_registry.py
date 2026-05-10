from __future__ import annotations

import os
from typing import Any

from integrations.base_integration import (
    REAL_MODE,
    SIMULATION_MODE,
    BaseIntegration,
    get_simulated_circuit_breaker_dict,
)
from integrations.email_adapter import EmailSimulationAdapter
from integrations.firewall_adapter import FirewallSimulationAdapter
from integrations.slack_adapter import (
    SlackSimulationAdapter,
    get_slack_real_mode_readiness,
)
from integrations.webhook_adapter import WebhookSimulationAdapter

_ADAPTERS: dict[str, type[BaseIntegration]] = {
    "slack": SlackSimulationAdapter,
    "email": EmailSimulationAdapter,
    "firewall": FirewallSimulationAdapter,
    "webhook": WebhookSimulationAdapter,
}


def normalize_registered_integration_adapter_name(name: str) -> str | None:
    """Return canonical adapter key if registered, else None."""
    key = str(name or "").strip().lower()
    if not key or key not in _ADAPTERS:
        return None
    return key


def resolve_integration_mode(mode: str | None = None) -> str:
    raw_mode = mode if mode is not None else os.getenv("INTEGRATION_MODE", SIMULATION_MODE)
    normalized = str(raw_mode or SIMULATION_MODE).strip().lower()
    if normalized not in {SIMULATION_MODE, REAL_MODE}:
        raise NotImplementedError("real integration mode is not implemented")
    return normalized


def _resolve_adapter_mode(adapter_name: str, configured_mode: str) -> str:
    if configured_mode != REAL_MODE:
        return SIMULATION_MODE
    if adapter_name != "slack":
        return SIMULATION_MODE
    readiness = get_slack_real_mode_readiness(configured_mode)
    if not readiness["real_mode_allowed"]:
        raise NotImplementedError("real integration mode is not implemented")
    return REAL_MODE


def get_integration_adapter(name: str, mode: str | None = None) -> BaseIntegration:
    normalized_name = str(name or "").strip().lower()
    if not normalized_name:
        raise ValueError("integration adapter name is required")
    adapter_cls = _ADAPTERS.get(normalized_name)
    if adapter_cls is None:
        raise ValueError(f"unknown integration adapter: {normalized_name}")
    resolved_mode = _resolve_adapter_mode(normalized_name, resolve_integration_mode(mode))
    return adapter_cls(mode=resolved_mode)


def execute_playbook_simulated_adapter(
    adapter_name: str,
    adapter_action: str,
    *,
    params: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run simulation-only adapter logic for playbook steps (circuit breaker enforced)."""
    adapter = get_integration_adapter(adapter_name)
    return adapter.execute(adapter_action, params=params, context=context)


def list_integration_adapters(mode: str | None = None) -> dict[str, BaseIntegration]:
    configured_mode = resolve_integration_mode(mode)
    return {
        name: adapter_cls(
            mode=(
                REAL_MODE
                if name == "slack"
                and get_slack_real_mode_readiness(configured_mode)["real_mode_allowed"]
                else SIMULATION_MODE
            )
        )
        for name, adapter_cls in sorted(_ADAPTERS.items())
    }


def get_integration_status(mode: str | None = None) -> dict:
    raw_mode = mode if mode is not None else os.getenv("INTEGRATION_MODE", SIMULATION_MODE)
    configured_mode = str(raw_mode or SIMULATION_MODE).strip().lower()
    if configured_mode not in {SIMULATION_MODE, REAL_MODE}:
        configured_mode = SIMULATION_MODE
    slack_readiness = get_slack_real_mode_readiness(configured_mode)
    real_mode_requested = configured_mode == REAL_MODE
    real_mode_ready = bool(slack_readiness["real_mode_ready"])
    return {
        "mode": REAL_MODE if real_mode_ready else SIMULATION_MODE,
        "configured_mode": configured_mode,
        "simulated": not real_mode_ready,
        "real_mode_enabled": real_mode_ready,
        "real_mode_status": (
            slack_readiness["real_mode_status"] if real_mode_requested else "disabled"
        ),
        "slack_configured": slack_readiness["slack_configured"],
        "real_mode_allowed": slack_readiness["real_mode_allowed"],
        "real_mode_ready": real_mode_ready,
        "adapters": [
            {
                "name": name,
                "mode": REAL_MODE if name == "slack" and real_mode_ready else SIMULATION_MODE,
                "simulated": not (name == "slack" and real_mode_ready),
                "real_client": name == "slack" and real_mode_ready,
                "supported_actions": sorted(adapter_cls.supported_actions),
                "circuit_breaker": get_simulated_circuit_breaker_dict(name),
                **(
                    {
                        "slack_configured": slack_readiness["slack_configured"],
                        "real_mode_allowed": slack_readiness["real_mode_allowed"],
                        "real_mode_ready": real_mode_ready,
                        "webhook_configured": slack_readiness["webhook_configured"],
                    }
                    if name == "slack"
                    else {}
                ),
            }
            for name, adapter_cls in sorted(_ADAPTERS.items())
        ],
    }
