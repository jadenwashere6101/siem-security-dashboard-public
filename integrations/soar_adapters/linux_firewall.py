import logging
import os
from typing import Any, Dict, List, Optional

from engines.soar_errors import SkippedAction
from integrations.soar_adapters.base import BaseSoarActionAdapter, validate_public_ip_target


logger = logging.getLogger(__name__)

SUPPORTED_FIREWALL_TOOLS = {"ufw", "iptables", "nft"}


class LinuxFirewallDryRunAdapter(BaseSoarActionAdapter):
    adapter_name = "linux_firewall_dry_run"
    supported_actions = {"block_ip"}

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config=config)
        self.enabled = self._resolve_enabled()
        self.firewall_tool = self._resolve_tool()

    def execute(self, row: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        action = row.get("action")
        if action != "block_ip":
            raise SkippedAction(
                "Linux firewall dry-run adapter only supports block_ip",
                code="unsupported_action",
            )

        if not self.enabled:
            raise SkippedAction(
                "Linux firewall dry-run adapter is disabled",
                code="adapter_disabled",
            )

        source_ip = row.get("source_ip")
        validated_ip = str(validate_public_ip_target(source_ip))

        if self.firewall_tool not in SUPPORTED_FIREWALL_TOOLS:
            raise SkippedAction(
                f"Unsupported linux firewall tool: {self.firewall_tool}",
                code="unsupported_firewall_tool",
            )

        command_plan = _build_command_plan(self.firewall_tool, validated_ip)
        logger.info(
            "[SOAR DRY RUN] adapter=%s queue_id=%s alert_id=%s source_ip=%s firewall_tool=%s",
            self.adapter_name,
            row.get("id"),
            row.get("alert_id"),
            validated_ip,
            self.firewall_tool,
        )

        return {
            "code": "linux_firewall_dry_run_plan",
            "message": f"DRY RUN: would block {validated_ip} using {self.firewall_tool}",
            "details": {
                "adapter": self.adapter_name,
                "action": action,
                "source_ip": validated_ip,
                "alert_id": row.get("alert_id"),
                "queue_id": row.get("id"),
                "firewall_tool": self.firewall_tool,
                "command_plan": command_plan,
                "simulated": True,
                "dry_run": True,
                "executed": False,
            },
        }

    def _resolve_enabled(self) -> bool:
        if "enabled" in self.config:
            return bool(self.config.get("enabled"))
        return os.getenv("SOAR_LINUX_FIREWALL_DRY_RUN_ENABLED", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def _resolve_tool(self) -> str:
        configured_tool = self.config.get("firewall_tool") or os.getenv(
            "SOAR_LINUX_FIREWALL_TOOL", "ufw"
        )
        return str(configured_tool).strip().lower()


def _build_command_plan(firewall_tool: str, source_ip: str) -> List[str]:
    if firewall_tool == "ufw":
        return ["ufw", "deny", "from", source_ip]
    if firewall_tool == "iptables":
        return ["iptables", "-A", "INPUT", "-s", source_ip, "-j", "DROP"]
    if firewall_tool == "nft":
        return ["nft", "add", "rule", "inet", "filter", "input", "ip", "saddr", source_ip, "drop"]
    return []

