from __future__ import annotations

from integrations.base_integration import BaseIntegration


class EmailSimulationAdapter(BaseIntegration):
    adapter_name = "email"
    supported_actions = frozenset({"send_email", "notify_owner"})

    def _simulate(self, action, params, context):
        return self._result(
            action,
            params,
            context,
            success=True,
            message="Simulated email action. No SMTP or provider call was made.",
            metadata={"delivery": "not_sent"},
        )
