from __future__ import annotations

from dataclasses import dataclass
import os

AI_MODE_DISABLED = "disabled"
AI_MODE_LOCAL_ONLY = "local_only"
AI_MODE_ASK_BEFORE_PAID_FALLBACK = "ask_before_paid_fallback"
AI_MODE_AUTOMATIC_FALLBACK = "automatic_fallback"

VALID_AI_GATEWAY_MODES = frozenset(
    {
        AI_MODE_DISABLED,
        AI_MODE_LOCAL_ONLY,
        AI_MODE_ASK_BEFORE_PAID_FALLBACK,
        AI_MODE_AUTOMATIC_FALLBACK,
    }
)

DEFAULT_LOCAL_PROVIDER = "ollama"
DEFAULT_LOCAL_TIMEOUT_SECONDS = 10.0
DEFAULT_PAID_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_PROMPT_CHARS = 12000


@dataclass(frozen=True)
class AiGatewayConfig:
    mode: str = AI_MODE_DISABLED
    configured_mode: str = AI_MODE_DISABLED
    mode_valid: bool = True
    local_provider: str = DEFAULT_LOCAL_PROVIDER
    local_base_url: str = ""
    local_model: str = ""
    local_timeout_seconds: float = DEFAULT_LOCAL_TIMEOUT_SECONDS
    paid_provider: str = ""
    paid_model: str = ""
    paid_timeout_seconds: float = DEFAULT_PAID_TIMEOUT_SECONDS
    paid_fallback_enabled: bool = False
    max_prompt_chars: int = DEFAULT_MAX_PROMPT_CHARS

    @property
    def local_configured(self) -> bool:
        return bool(self.local_provider and self.local_base_url and self.local_model)

    @property
    def paid_configured(self) -> bool:
        return bool(self.paid_provider and self.paid_model)

    def sanitized(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "configured_mode": self.configured_mode,
            "mode_valid": self.mode_valid,
            "local_provider": self.local_provider,
            "local_base_url_configured": bool(self.local_base_url),
            "local_model": self.local_model,
            "local_timeout_seconds": self.local_timeout_seconds,
            "local_configured": self.local_configured,
            "paid_provider": self.paid_provider,
            "paid_model": self.paid_model,
            "paid_timeout_seconds": self.paid_timeout_seconds,
            "paid_fallback_enabled": self.paid_fallback_enabled,
            "paid_configured": self.paid_configured,
            "max_prompt_chars": self.max_prompt_chars,
        }


def _env_text(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or "").strip()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_positive_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    try:
        value = float(str(raw).strip()) if raw is not None else default
    except (TypeError, ValueError):
        return default
    if value <= 0:
        return default
    return value


def _env_positive_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        value = int(str(raw).strip()) if raw is not None else default
    except (TypeError, ValueError):
        return default
    if value <= 0:
        return default
    return value


def load_ai_gateway_config() -> AiGatewayConfig:
    configured_mode = _env_text("AI_GATEWAY_MODE", AI_MODE_DISABLED).lower()
    mode_valid = configured_mode in VALID_AI_GATEWAY_MODES
    mode = configured_mode if mode_valid else AI_MODE_DISABLED

    return AiGatewayConfig(
        mode=mode,
        configured_mode=configured_mode,
        mode_valid=mode_valid,
        local_provider=_env_text("AI_LOCAL_PROVIDER", DEFAULT_LOCAL_PROVIDER).lower(),
        local_base_url=_env_text("AI_LOCAL_BASE_URL"),
        local_model=_env_text("AI_LOCAL_MODEL"),
        local_timeout_seconds=_env_positive_float(
            "AI_LOCAL_TIMEOUT_SECONDS",
            DEFAULT_LOCAL_TIMEOUT_SECONDS,
        ),
        paid_provider=_env_text("AI_PAID_PROVIDER").lower(),
        paid_model=_env_text("AI_PAID_MODEL"),
        paid_timeout_seconds=_env_positive_float(
            "AI_PAID_TIMEOUT_SECONDS",
            DEFAULT_PAID_TIMEOUT_SECONDS,
        ),
        paid_fallback_enabled=_env_bool("AI_PAID_FALLBACK_ENABLED", False),
        max_prompt_chars=_env_positive_int("AI_MAX_PROMPT_CHARS", DEFAULT_MAX_PROMPT_CHARS),
    )
