from __future__ import annotations

from dataclasses import dataclass
import os

from core.ai.profile_registry import (
    AI_PROFILE_DEEP_BRIEFING,
    AI_PROFILE_DEVELOPER_ASSISTANT,
    AI_PROFILE_FAST_TRIAGE,
    AI_PROFILE_GUIDED_ANALYSIS,
    APPROVED_AI_PROFILES,
    AiModelProfile,
)

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
DEFAULT_FAST_MODEL = "llama3.2:3b"
DEFAULT_GUIDED_MODEL = "llama3.1:8b"
DEFAULT_DEEP_MODEL = "llama3.1:8b"
DEFAULT_DEVELOPER_MODEL = "llama3.1:8b"
DEFAULT_FAST_TIMEOUT_SECONDS = 45.0
DEFAULT_GUIDED_TIMEOUT_SECONDS = 120.0
DEFAULT_DEEP_TIMEOUT_SECONDS = 150.0
DEFAULT_DEVELOPER_TIMEOUT_SECONDS = 120.0
DEFAULT_FAST_MAX_PROMPT_CHARS = 8000
DEFAULT_GUIDED_MAX_PROMPT_CHARS = 14000
DEFAULT_DEEP_MAX_PROMPT_CHARS = 18000
DEFAULT_DEVELOPER_MAX_PROMPT_CHARS = 20000
DEFAULT_FAST_MAX_OUTPUT_TOKENS = 512
DEFAULT_GUIDED_MAX_OUTPUT_TOKENS = 1200
DEFAULT_DEEP_MAX_OUTPUT_TOKENS = 1800
DEFAULT_DEVELOPER_MAX_OUTPUT_TOKENS = 1600


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
    profiles: dict[str, AiModelProfile] | None = None

    @property
    def local_configured(self) -> bool:
        return bool(self.local_provider and self.local_base_url and self.local_model)

    @property
    def paid_configured(self) -> bool:
        return bool(self.paid_provider and self.paid_model)

    def profile(self, name: str | None = None) -> AiModelProfile:
        profile_name = str(name or AI_PROFILE_FAST_TRIAGE).strip().lower()
        if profile_name not in APPROVED_AI_PROFILES:
            profile_name = AI_PROFILE_FAST_TRIAGE
        profiles = self.profiles or default_ai_profiles(local_model=self.local_model, local_timeout_seconds=self.local_timeout_seconds)
        return profiles.get(profile_name) or profiles[AI_PROFILE_FAST_TRIAGE]

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
            "profiles": {
                name: profile.sanitized()
                for name, profile in (self.profiles or {}).items()
            },
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


def _profile_model(name: str, default: str, legacy_local_model: str) -> str:
    raw = _env_text(name)
    if raw:
        return raw
    if legacy_local_model:
        return legacy_local_model
    return default


def _profile_timeout(name: str, default: float) -> float:
    return _env_positive_float(name, default)


def default_ai_profiles(
    *,
    local_model: str = "",
    local_timeout_seconds: float = DEFAULT_LOCAL_TIMEOUT_SECONDS,
) -> dict[str, AiModelProfile]:
    del local_timeout_seconds
    return {
        AI_PROFILE_FAST_TRIAGE: AiModelProfile(
            name=AI_PROFILE_FAST_TRIAGE,
            model=_profile_model("AI_FAST_MODEL", DEFAULT_FAST_MODEL, ""),
            timeout_seconds=_env_positive_float("AI_FAST_TIMEOUT_SECONDS", DEFAULT_FAST_TIMEOUT_SECONDS),
            max_prompt_chars=_env_positive_int("AI_FAST_MAX_PROMPT_CHARS", DEFAULT_FAST_MAX_PROMPT_CHARS),
            max_output_tokens=_env_positive_int("AI_FAST_MAX_OUTPUT_TOKENS", DEFAULT_FAST_MAX_OUTPUT_TOKENS),
            temperature=_env_positive_float("AI_FAST_TEMPERATURE", 0.2),
            task_category="quick SOC triage and short explanations",
        ),
        AI_PROFILE_GUIDED_ANALYSIS: AiModelProfile(
            name=AI_PROFILE_GUIDED_ANALYSIS,
            model=_profile_model("AI_GUIDED_MODEL", DEFAULT_GUIDED_MODEL, local_model),
            timeout_seconds=_profile_timeout("AI_GUIDED_TIMEOUT_SECONDS", DEFAULT_GUIDED_TIMEOUT_SECONDS),
            max_prompt_chars=_env_positive_int("AI_GUIDED_MAX_PROMPT_CHARS", DEFAULT_GUIDED_MAX_PROMPT_CHARS),
            max_output_tokens=_env_positive_int("AI_GUIDED_MAX_OUTPUT_TOKENS", DEFAULT_GUIDED_MAX_OUTPUT_TOKENS),
            temperature=_env_positive_float("AI_GUIDED_TEMPERATURE", 0.2),
            task_category="guided multi-source SOC analysis",
        ),
        AI_PROFILE_DEEP_BRIEFING: AiModelProfile(
            name=AI_PROFILE_DEEP_BRIEFING,
            model=_profile_model("AI_DEEP_MODEL", DEFAULT_DEEP_MODEL, local_model),
            timeout_seconds=_profile_timeout("AI_DEEP_TIMEOUT_SECONDS", DEFAULT_DEEP_TIMEOUT_SECONDS),
            max_prompt_chars=_env_positive_int("AI_DEEP_MAX_PROMPT_CHARS", DEFAULT_DEEP_MAX_PROMPT_CHARS),
            max_output_tokens=_env_positive_int("AI_DEEP_MAX_OUTPUT_TOKENS", DEFAULT_DEEP_MAX_OUTPUT_TOKENS),
            temperature=_env_positive_float("AI_DEEP_TEMPERATURE", 0.1),
            task_category="scheduled and manual SOC briefing synthesis",
        ),
        AI_PROFILE_DEVELOPER_ASSISTANT: AiModelProfile(
            name=AI_PROFILE_DEVELOPER_ASSISTANT,
            model=_profile_model("AI_DEVELOPER_MODEL", DEFAULT_DEVELOPER_MODEL, local_model),
            timeout_seconds=_profile_timeout("AI_DEVELOPER_TIMEOUT_SECONDS", DEFAULT_DEVELOPER_TIMEOUT_SECONDS),
            max_prompt_chars=_env_positive_int("AI_DEVELOPER_MAX_PROMPT_CHARS", DEFAULT_DEVELOPER_MAX_PROMPT_CHARS),
            max_output_tokens=_env_positive_int("AI_DEVELOPER_MAX_OUTPUT_TOKENS", DEFAULT_DEVELOPER_MAX_OUTPUT_TOKENS),
            temperature=_env_positive_float("AI_DEVELOPER_TEMPERATURE", 0.1),
            task_category="repository architecture assistance",
        ),
    }


def load_ai_gateway_config() -> AiGatewayConfig:
    configured_mode = _env_text("AI_GATEWAY_MODE", AI_MODE_DISABLED).lower()
    mode_valid = configured_mode in VALID_AI_GATEWAY_MODES
    mode = configured_mode if mode_valid else AI_MODE_DISABLED

    legacy_local_model = _env_text("AI_LOCAL_MODEL")
    legacy_local_timeout = _env_positive_float(
        "AI_LOCAL_TIMEOUT_SECONDS",
        DEFAULT_LOCAL_TIMEOUT_SECONDS,
    )
    profiles = default_ai_profiles(
        local_model=legacy_local_model,
        local_timeout_seconds=legacy_local_timeout,
    )
    fast_profile = profiles[AI_PROFILE_FAST_TRIAGE]

    return AiGatewayConfig(
        mode=mode,
        configured_mode=configured_mode,
        mode_valid=mode_valid,
        local_provider=_env_text("AI_LOCAL_PROVIDER", DEFAULT_LOCAL_PROVIDER).lower(),
        local_base_url=_env_text("AI_LOCAL_BASE_URL"),
        local_model=legacy_local_model or fast_profile.model,
        local_timeout_seconds=legacy_local_timeout,
        paid_provider=_env_text("AI_PAID_PROVIDER").lower(),
        paid_model=_env_text("AI_PAID_MODEL"),
        paid_timeout_seconds=_env_positive_float(
            "AI_PAID_TIMEOUT_SECONDS",
            DEFAULT_PAID_TIMEOUT_SECONDS,
        ),
        paid_fallback_enabled=_env_bool("AI_PAID_FALLBACK_ENABLED", False),
        max_prompt_chars=_env_positive_int("AI_MAX_PROMPT_CHARS", DEFAULT_MAX_PROMPT_CHARS),
        profiles=profiles,
    )
