from __future__ import annotations

from integrations.base_integration import BaseIntegration


# spec: SPEC-INTEG-005 - simulation-only until guarded real webhook design is implemented.
class WebhookSimulationAdapter(BaseIntegration):
    adapter_name = "webhook"
    supported_actions = frozenset({"post_event", "send_webhook", "notify_webhook"})
    # Future real-mode path must call core.integration_audit.log_integration_execution_attempt.

    def _simulate(self, action, params, context):
        return self._result(
            action,
            params,
            context,
            success=True,
            message="Simulated webhook action. No HTTP request was made.",
            metadata={"delivery": "not_sent"},
        )
