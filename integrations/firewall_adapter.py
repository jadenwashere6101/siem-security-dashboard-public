from __future__ import annotations

from integrations.base_integration import BaseIntegration


# spec: SPEC-INTEG-005 - real firewall execution permanently blocked until separate approved design.
class FirewallSimulationAdapter(BaseIntegration):
    adapter_name = "firewall"
    supported_actions = frozenset({"block_ip", "unblock_ip", "tag_ip"})

    def _simulate(self, action, params, context):
        return self._result(
            action,
            params,
            context,
            success=True,
            message="Simulated firewall action. No firewall or blocklist change was made.",
            metadata={"mutation": "none"},
        )
