import os
from dataclasses import dataclass, field
from typing import Dict

_DEFAULT_TIMEOUT_SECONDS = 5
_DEFAULT_EXECUTION_MODE = "simulation"
_ALLOWED_MODES = {"simulation", "real"}


@dataclass(frozen=True)
class SoarAdapterConfig:
    execution_mode: str = _DEFAULT_EXECUTION_MODE
    action_to_adapter: Dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS
    adapter_enabled: Dict[str, bool] = field(default_factory=dict)

    def is_real_mode(self) -> bool:
        return self.execution_mode == "real"

    def is_adapter_enabled(self, adapter_name: str) -> bool:
        return self.adapter_enabled.get(adapter_name, True)


def load_soar_adapter_config() -> SoarAdapterConfig:
    raw_mode = os.getenv("SOAR_EXECUTION_MODE", _DEFAULT_EXECUTION_MODE).strip().lower()
    execution_mode = raw_mode if raw_mode in _ALLOWED_MODES else _DEFAULT_EXECUTION_MODE

    timeout_value = _parse_timeout(os.getenv("SOAR_ACTION_TIMEOUT_SECONDS"))
    action_to_adapter = _load_action_adapter_map()
    adapter_enabled = _load_adapter_enabled_flags()

    return SoarAdapterConfig(
        execution_mode=execution_mode,
        action_to_adapter=action_to_adapter,
        timeout_seconds=timeout_value,
        adapter_enabled=adapter_enabled,
    )


def _load_action_adapter_map() -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for key, value in os.environ.items():
        if not key.startswith("SOAR_ADAPTER_"):
            continue
        if key.endswith("_ENABLED"):
            continue
        adapter_name = value.strip()
        if not adapter_name:
            continue
        action_name = key[len("SOAR_ADAPTER_") :].lower()
        mapping[action_name] = adapter_name
    return mapping


def _load_adapter_enabled_flags() -> Dict[str, bool]:
    enabled: Dict[str, bool] = {}
    for key, value in os.environ.items():
        if not key.startswith("SOAR_ADAPTER_") or not key.endswith("_ENABLED"):
            continue
        adapter_name = key[len("SOAR_ADAPTER_") : -len("_ENABLED")].strip().lower()
        if not adapter_name:
            continue
        enabled[adapter_name] = value.strip().lower() in {"1", "true", "yes", "on"}
    return enabled


def _parse_timeout(raw_timeout: str) -> int:
    if raw_timeout is None:
        return _DEFAULT_TIMEOUT_SECONDS
    try:
        value = int(raw_timeout)
    except ValueError:
        return _DEFAULT_TIMEOUT_SECONDS
    if value <= 0:
        return _DEFAULT_TIMEOUT_SECONDS
    return value

