from typing import Dict, Optional

from engines.soar_errors import SkippedAction
from integrations.soar_adapters.base import BaseSoarActionAdapter
from integrations.soar_adapters.config import SoarAdapterConfig, load_soar_adapter_config


class SoarAdapterRegistry:
    def __init__(self, config: Optional[SoarAdapterConfig] = None):
        self.config = config or load_soar_adapter_config()
        self._adapters: Dict[str, BaseSoarActionAdapter] = {}

    def register(self, name: str, adapter: BaseSoarActionAdapter) -> None:
        normalized_name = (name or "").strip().lower()
        if not normalized_name:
            raise ValueError("Adapter name cannot be empty")
        self._adapters[normalized_name] = adapter

    def get_adapter_for_action(self, action: str) -> BaseSoarActionAdapter:
        normalized_action = (action or "").strip().lower()
        if not normalized_action:
            raise SkippedAction("Missing action for adapter selection", code="missing_action")

        if not self.config.is_real_mode():
            raise SkippedAction(
                "Real adapter execution is disabled in simulation mode",
                code="real_mode_disabled",
            )

        adapter_name = self.config.action_to_adapter.get(normalized_action)
        if not adapter_name:
            raise SkippedAction(
                f"No adapter configured for action: {normalized_action}",
                code="adapter_not_configured",
            )

        normalized_adapter_name = adapter_name.strip().lower()
        adapter = self._adapters.get(normalized_adapter_name)
        if adapter is None:
            raise SkippedAction(
                f"Unknown adapter configured for action {normalized_action}: {adapter_name}",
                code="unknown_adapter",
            )

        if not self.config.is_adapter_enabled(normalized_adapter_name):
            raise SkippedAction(
                f"Adapter {normalized_adapter_name} is disabled",
                code="adapter_disabled",
            )

        if not adapter.can_handle(normalized_action):
            raise SkippedAction(
                f"Adapter {normalized_adapter_name} cannot handle action {normalized_action}",
                code="unsupported_adapter_action",
            )

        return adapter

