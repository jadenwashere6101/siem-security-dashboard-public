from __future__ import annotations

import logging
import os
from typing import Any

from integrations.base_integration import (
    REAL_MODE,
    SIMULATION_MODE,
    BaseIntegration,
    get_simulated_circuit_breaker_dict,
    _validate_real_mode_guards,
)
from integrations.email_adapter import EmailSimulationAdapter, get_email_real_mode_readiness
from integrations.firewall_adapter import FirewallSimulationAdapter
from integrations.slack_adapter import (
    SlackSimulationAdapter,
    get_slack_real_mode_readiness,
)
from integrations.teams_adapter import (
    TeamsSimulationAdapter,
    get_teams_real_mode_readiness,
)
from integrations.webhook_adapter import WebhookSimulationAdapter

_ADAPTERS: dict[str, type[BaseIntegration]] = {
    "slack": SlackSimulationAdapter,
    "teams": TeamsSimulationAdapter,
    "email": EmailSimulationAdapter,
    "firewall": FirewallSimulationAdapter,
    "webhook": WebhookSimulationAdapter,
}

_LOGGER = logging.getLogger(__name__)

_ADAPTER_REAL_GUARDS = {
    "slack": ("SOAR_REAL_SLACK_ENABLED", ("SLACK_WEBHOOK_URL",)),
    "teams": ("SOAR_REAL_TEAMS_ENABLED", ("TEAMS_WEBHOOK_URL",)),
    "email": ("SOAR_REAL_EMAIL_ENABLED", ("SMTP_HOST", "SMTP_USERNAME")),
    "firewall": ("SOAR_REAL_FIREWALL_ENABLED", ("FIREWALL_API_TOKEN",)),
    "webhook": ("SOAR_REAL_WEBHOOK_ENABLED", ("WEBHOOK_URL",)),
}


# spec: SPEC-INTEG-001
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


def _adapter_guard_readiness(adapter_name: str, configured_mode: str) -> dict[str, Any]:
    enabled_env, credential_envs = _ADAPTER_REAL_GUARDS[adapter_name]
    return _validate_real_mode_guards(
        adapter_name,
        mode=configured_mode,
        enabled_env=enabled_env,
        credential_envs=credential_envs,
    )


def _safe_adapter_mode_decision(adapter_name: str, configured_mode: str) -> str:
    if configured_mode != REAL_MODE:
        return SIMULATION_MODE
    if adapter_name in {"slack", "teams", "email"}:
        return REAL_MODE
    return SIMULATION_MODE


def _log_adapter_registry_startup(adapter_name: str, configured_mode: str, mode_decision: str) -> None:
    readiness = _adapter_guard_readiness(adapter_name, configured_mode)
    circuit = get_simulated_circuit_breaker_dict(adapter_name)
    _LOGGER.info(
        "integration_adapter_startup adapter=%s mode_decision=%s missing_guards=%s "
        "credential_envs=%s circuit_breaker_reset_to=%s",
        adapter_name,
        mode_decision,
        ",".join(readiness["missing_guards"]) or "none",
        ",".join(readiness["credential_envs"]) or "none",
        circuit["state"],
        extra={
            "event": "integration_adapter_startup",
            "adapter": adapter_name,
            "configured_mode": configured_mode,
            "mode_decision": mode_decision,
            "missing_guards": readiness["missing_guards"],
            "credential_envs": readiness["credential_envs"],
            "circuit_breaker_state": circuit["state"],
            "circuit_breaker_state_persisted": circuit["state_persisted"],
        },
    )


def _resolve_adapter_mode(adapter_name: str, configured_mode: str) -> str:
    return _safe_adapter_mode_decision(adapter_name, configured_mode)


def get_integration_adapter(name: str, mode: str | None = None) -> BaseIntegration:
    normalized_name = str(name or "").strip().lower()
    if not normalized_name:
        raise ValueError("integration adapter name is required")
    adapter_cls = _ADAPTERS.get(normalized_name)
    if adapter_cls is None:
        raise ValueError(f"unknown integration adapter: {normalized_name}")
    configured_mode = resolve_integration_mode(mode)
    resolved_mode = _resolve_adapter_mode(normalized_name, configured_mode)
    _log_adapter_registry_startup(
        normalized_name,
        configured_mode,
        resolved_mode,
    )
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
    adapters: dict[str, BaseIntegration] = {}
    for name, adapter_cls in sorted(_ADAPTERS.items()):
        mode_decision = _safe_adapter_mode_decision(name, configured_mode)
        _log_adapter_registry_startup(name, configured_mode, mode_decision)
        adapters[name] = adapter_cls(mode=mode_decision)
    return adapters


def get_integration_status(mode: str | None = None) -> dict:
    raw_mode = mode if mode is not None else os.getenv("INTEGRATION_MODE", SIMULATION_MODE)
    configured_mode = str(raw_mode or SIMULATION_MODE).strip().lower()
    if configured_mode not in {SIMULATION_MODE, REAL_MODE}:
        configured_mode = SIMULATION_MODE
    slack_readiness = get_slack_real_mode_readiness(configured_mode)
    teams_readiness = get_teams_real_mode_readiness(configured_mode)
    email_readiness = get_email_real_mode_readiness(configured_mode)
    real_mode_requested = configured_mode == REAL_MODE
    real_mode_ready = bool(
        slack_readiness["real_mode_ready"]
        or teams_readiness["real_mode_ready"]
        or email_readiness["real_mode_ready"]
    )
    real_mode_allowed = bool(
        slack_readiness["real_mode_allowed"]
        or teams_readiness["real_mode_allowed"]
        or email_readiness["real_mode_allowed"]
    )
    real_mode_status = "disabled"
    if real_mode_requested:
        if real_mode_ready:
            real_mode_status = "ready"
        else:
            real_mode_status = (
                "disabled: no real notification adapter ready; "
                f"slack={slack_readiness['real_mode_status']}; "
                f"teams={teams_readiness['real_mode_status']}; "
                f"email={email_readiness['real_mode_status']}"
            )
    adapter_rows = []
    for name, adapter_cls in sorted(_ADAPTERS.items()):
        mode_decision = REAL_MODE if (
            (name == "slack" and slack_readiness["real_mode_ready"])
            or (name == "teams" and teams_readiness["real_mode_ready"])
            or (name == "email" and email_readiness["real_mode_ready"])
        ) else SIMULATION_MODE
        _log_adapter_registry_startup(name, configured_mode, mode_decision)
        adapter_rows.append(
            {
                "name": name,
                "mode": mode_decision,
                "simulated": mode_decision != REAL_MODE,
                "real_client": mode_decision == REAL_MODE,
                "supported_actions": sorted(adapter_cls.supported_actions),
                "circuit_breaker": get_simulated_circuit_breaker_dict(name),
                **(
                    {
                        "slack_configured": slack_readiness["slack_configured"],
                        "real_mode_allowed": slack_readiness["real_mode_allowed"],
                        "real_mode_ready": slack_readiness["real_mode_ready"],
                        "webhook_configured": slack_readiness["webhook_configured"],
                    }
                    if name == "slack"
                    else {}
                ),
                **(
                    {
                        "smtp_configured": email_readiness["smtp_configured"],
                        "smtp_host_configured": email_readiness["smtp_host_configured"],
                        "smtp_username_configured": email_readiness["smtp_username_configured"],
                        "smtp_from_configured": email_readiness["smtp_from_configured"],
                        "smtp_to_configured": email_readiness["smtp_to_configured"],
                        "email_real_enabled": email_readiness["email_real_enabled"],
                        "real_mode_allowed": email_readiness["real_mode_allowed"],
                        "real_mode_ready": email_readiness["real_mode_ready"],
                    }
                    if name == "email"
                    else {}
                ),
                **(
                    {
                        "teams_configured": teams_readiness["teams_configured"],
                        "real_mode_allowed": teams_readiness["real_mode_allowed"],
                        "real_mode_ready": teams_readiness["real_mode_ready"],
                        "webhook_configured": teams_readiness["webhook_configured"],
                    }
                    if name == "teams"
                    else {}
                ),
            }
        )

    return {
        "mode": REAL_MODE if real_mode_ready else SIMULATION_MODE,
        "configured_mode": configured_mode,
        "simulated": not real_mode_ready,
        "real_mode_enabled": real_mode_ready,
        "real_mode_status": real_mode_status,
        "slack_configured": slack_readiness["slack_configured"],
        "teams_configured": teams_readiness["teams_configured"],
        "smtp_configured": email_readiness["smtp_configured"],
        "email_real_enabled": email_readiness["email_real_enabled"],
        "real_mode_allowed": real_mode_allowed,
        "real_mode_ready": real_mode_ready,
        "adapters": adapter_rows,
    }
