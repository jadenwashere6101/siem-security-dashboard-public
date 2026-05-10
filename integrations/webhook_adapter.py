from __future__ import annotations

from integrations.base_integration import BaseIntegration


class WebhookSimulationAdapter(BaseIntegration):
    adapter_name = "webhook"
    supported_actions = frozenset({"post_event", "send_webhook", "notify_webhook"})

    def _simulate(self, action, params, context):
        return self._result(
            action,
            params,
            context,
            success=True,
            message="Simulated webhook action. No HTTP request was made.",
            metadata={"delivery": "not_sent"},
        )
