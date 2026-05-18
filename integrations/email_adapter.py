from __future__ import annotations

from integrations.base_integration import BaseIntegration


# spec: SPEC-INTEG-005 - simulation-only until guarded real email design is implemented.
class EmailSimulationAdapter(BaseIntegration):
    adapter_name = "email"
    supported_actions = frozenset({"send_email", "notify_owner"})
    # Future real-mode path must call core.integration_audit.log_integration_execution_attempt.
    # Future real-mode path must call integrations.adapter_rate_limiter.check_adapter_rate_limit.

    def _simulate(self, action, params, context):
        return self._result(
            action,
            params,
            context,
            success=True,
            message="Simulated email action. No SMTP or provider call was made.",
            metadata={"delivery": "not_sent"},
        )
