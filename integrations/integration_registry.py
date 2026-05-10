from __future__ import annotations

import os
from typing import Any

from integrations.base_integration import (
    SIMULATION_MODE,
    BaseIntegration,
    get_simulated_circuit_breaker_dict,
)
from integrations.email_adapter import EmailSimulationAdapter
from integrations.firewall_adapter import FirewallSimulationAdapter
from integrations.slack_adapter import SlackSimulationAdapter
from integrations.webhook_adapter import WebhookSimulationAdapter

_ADAPTERS: dict[str, type[BaseIntegration]] = {
    "slack": SlackSimulationAdapter,
    "email": EmailSimulationAdapter,
    "firewall": FirewallSimulationAdapter,
    "webhook": WebhookSimulationAdapter,
}


def resolve_integration_mode(mode: str | None = None) -> str:
    raw_mode = mode if mode is not None else os.getenv("INTEGRATION_MODE", SIMULATION_MODE)
    normalized = str(raw_mode or SIMULATION_MODE).strip().lower()
    if normalized != SIMULATION_MODE:
        raise NotImplementedError("real integration mode is not implemented")
    return normalized


def get_integration_adapter(name: str, mode: str | None = None) -> BaseIntegration:
    normalized_name = str(name or "").strip().lower()
    if not normalized_name:
        raise ValueError("integration adapter name is required")
    adapter_cls = _ADAPTERS.get(normalized_name)
    if adapter_cls is None:
        raise ValueError(f"unknown integration adapter: {normalized_name}")
    resolved_mode = resolve_integration_mode(mode)
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
    resolved_mode = resolve_integration_mode(mode)
    return {
        name: adapter_cls(mode=resolved_mode)
        for name, adapter_cls in sorted(_ADAPTERS.items())
    }


def get_integration_status(mode: str | None = None) -> dict:
    raw_mode = mode if mode is not None else os.getenv("INTEGRATION_MODE", SIMULATION_MODE)
    configured_mode = str(raw_mode or SIMULATION_MODE).strip().lower()
    real_mode_requested = configured_mode != SIMULATION_MODE
    return {
        "mode": SIMULATION_MODE,
        "configured_mode": configured_mode,
        "simulated": True,
        "real_mode_enabled": False,
        "real_mode_status": (
            "disabled: real integration mode is not implemented"
            if real_mode_requested
            else "disabled"
        ),
        "adapters": [
            {
                "name": name,
                "mode": SIMULATION_MODE,
                "simulated": True,
                "real_client": False,
                "supported_actions": sorted(adapter_cls.supported_actions),
                "circuit_breaker": get_simulated_circuit_breaker_dict(name),
            }
            for name, adapter_cls in sorted(_ADAPTERS.items())
        ],
    }
