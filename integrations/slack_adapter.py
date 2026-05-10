from __future__ import annotations

from integrations.base_integration import BaseIntegration


class SlackSimulationAdapter(BaseIntegration):
    adapter_name = "slack"
    supported_actions = frozenset({"send_message", "notify_channel"})

    def _simulate(self, action, params, context):
        return self._result(
            action,
            params,
            context,
            success=True,
            message="Simulated slack action. No webhook or API call was made.",
            metadata={"delivery": "not_sent"},
        )
