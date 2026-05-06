"""Adapter interfaces and registry for SOAR actions."""

from integrations.soar_adapters.base import (
    AdapterExecutionResult,
    AdapterTerminalError,
    BaseSoarActionAdapter,
    classify_adapter_error,
    validate_public_ip_target,
)
from integrations.soar_adapters.config import SoarAdapterConfig, load_soar_adapter_config
from integrations.soar_adapters.linux_firewall import LinuxFirewallDryRunAdapter
from integrations.soar_adapters.registry import SoarAdapterRegistry

__all__ = [
    "AdapterExecutionResult",
    "AdapterTerminalError",
    "BaseSoarActionAdapter",
    "LinuxFirewallDryRunAdapter",
    "SoarAdapterConfig",
    "SoarAdapterRegistry",
    "classify_adapter_error",
    "load_soar_adapter_config",
    "validate_public_ip_target",
]

