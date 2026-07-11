from __future__ import annotations

import os
from typing import Any

from integrations.base_integration import BaseIntegration

TEAMS_WEBHOOK_ENV = "TEAMS_WEBHOOK_URL"
TEAMS_TIMEOUT_ENV = "TEAMS_TIMEOUT_SECONDS"
DEFAULT_TEAMS_TIMEOUT_SECONDS = 3
MAX_TEAMS_TEXT_CHARS = 3000


def _teams_webhook_configured() -> bool:
    return bool(os.getenv(TEAMS_WEBHOOK_ENV, "").strip())


def _teams_webhook_valid() -> bool:
    """Validate webhook shape for status metadata only; never used for delivery."""
    value = os.getenv(TEAMS_WEBHOOK_ENV, "").strip()
    if not value:
        return False
    # Keep shape checks local and secret-safe; Teams remains simulation-only.
    lower = value.lower()
    return lower.startswith("https://") and (
        "webhook.office.com" in lower
        or "logic.azure.com" in lower
        or ("office.com" in lower and "webhook" in lower)
    )


def get_teams_real_mode_readiness(configured_mode: str | None = None) -> dict[str, Any]:
    """Return safe Teams readiness metadata. Never include the webhook value.

    Product rule: Teams remains simulation-only. Real mode is never allowed or ready,
    even when INTEGRATION_MODE=real and webhook env vars are present.
    """
    configured = _teams_webhook_configured()
    return {
        "teams_configured": configured,
        "real_mode_allowed": False,
        "real_mode_ready": False,
        "real_mode_status": "disabled: Teams remains simulation-only",
        "webhook_configured": configured,
        "webhook_valid": _teams_webhook_valid() if configured else False,
        "simulation_only": True,
    }


def _get_timeout_seconds() -> int:
    raw = os.getenv(TEAMS_TIMEOUT_ENV, str(DEFAULT_TEAMS_TIMEOUT_SECONDS)).strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_TEAMS_TIMEOUT_SECONDS
    return max(1, min(value, 30))


class TeamsSimulationAdapter(BaseIntegration):
    adapter_name = "teams"
    supported_actions = frozenset(
        {"send_message", "notify_channel", "notify_teams", "test_notification"}
    )
    # Product rule: Teams is simulation-only; never advertise or execute real delivery.
    allow_real_mode = False

    def _simulate(self, action, params, context):
        readiness = get_teams_real_mode_readiness(self.mode)
        return self._result(
            action,
            params,
            context,
            success=True,
            message="Simulated Teams action. No webhook or API call was made.",
            metadata={
                "delivery": "not_sent",
                "simulation_only": True,
                "teams_configured": readiness["teams_configured"],
                "real_mode_allowed": False,
                "real_mode_ready": False,
                "timeout_seconds": _get_timeout_seconds(),
            },
        )

    def _execute_supported_action(self, action, params, context):
        # Always simulate; real Teams delivery is intentionally unavailable.
        return self._simulate(action, params, context)
