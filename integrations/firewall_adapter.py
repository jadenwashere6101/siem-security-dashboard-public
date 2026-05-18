from __future__ import annotations

from integrations.base_integration import BaseIntegration


# spec: SPEC-INTEG-005 / SPEC-UI-004 - firewall remains simulation/dry-run only in this spec.
# No promotion path exists here; any real firewall execution requires a separate
# future approved OpenSpec before API calls, subprocesses, or blocklist mutation.
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
