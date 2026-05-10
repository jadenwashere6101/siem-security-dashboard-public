from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SIMULATION_MODE = "simulation"
SECRET_FIELD_NAMES = {
    "api_key",
    "authorization",
    "auth",
    "password",
    "secret",
    "token",
    "webhook_url",
}


@dataclass(frozen=True)
class IntegrationResult:
    adapter: str
    action: str
    mode: str
    simulated: bool
    executed: bool
    success: bool
    message: str
    params: dict[str, Any]
    context: dict[str, Any]
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "action": self.action,
            "mode": self.mode,
            "simulated": self.simulated,
            "executed": self.executed,
            "success": self.success,
            "message": self.message,
            "params": self.params,
            "context": self.context,
            "metadata": self.metadata,
        }


class BaseIntegration:
    adapter_name = "base"
    supported_actions: frozenset[str] = frozenset()

    def __init__(self, mode: str = SIMULATION_MODE):
        normalized_mode = (mode or SIMULATION_MODE).strip().lower()
        if normalized_mode != SIMULATION_MODE:
            raise NotImplementedError("real integration mode is not implemented")
        self.mode = normalized_mode

    def can_handle(self, action: str) -> bool:
        return self._normalize_action(action) in self.supported_actions

    def execute(
        self,
        action: str,
        params: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_action = self._normalize_action(action)
        safe_params = sanitize_payload(params)
        safe_context = sanitize_payload(context)
        if not self.can_handle(normalized_action):
            return self._result(
                normalized_action or "unspecified",
                safe_params,
                safe_context,
                success=False,
                message=(
                    f"Unsupported simulated {self.adapter_name} action: "
                    f"{normalized_action or 'unspecified'}"
                ),
            )
        return self._simulate(normalized_action, safe_params, safe_context)

    def _simulate(
        self,
        action: str,
        params: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return self._result(
            action,
            params,
            context,
            success=True,
            message=f"Simulated {self.adapter_name} action.",
        )

    def _result(
        self,
        action: str,
        params: dict[str, Any],
        context: dict[str, Any],
        *,
        success: bool,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return IntegrationResult(
            adapter=self.adapter_name,
            action=action,
            mode=SIMULATION_MODE,
            simulated=True,
            executed=False,
            success=success,
            message=message,
            params=params,
            context=context,
            metadata=metadata or {},
        ).as_dict()

    @staticmethod
    def _normalize_action(action: str | None) -> str:
        return str(action or "").strip().lower()


def sanitize_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    return {str(key): _sanitize_value(str(key), value) for key, value in payload.items()}


def _sanitize_value(key: str, value: Any) -> Any:
    if key.lower() in SECRET_FIELD_NAMES:
        return "[redacted]"
    if isinstance(value, dict):
        return sanitize_payload(value)
    if isinstance(value, list):
        return [_sanitize_value("", item) for item in value]
    return value
