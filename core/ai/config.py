from __future__ import annotations

from dataclasses import dataclass, field
import os
import re

from core.ai.profile_registry import (
    AI_PROFILE_AGENTIC_PLANNING,
    AI_PROFILE_DEEP_BRIEFING,
    AI_PROFILE_DEVELOPER_ASSISTANT,
    AI_PROFILE_FAST_TRIAGE,
    AI_PROFILE_GUIDED_ANALYSIS,
    AI_PROVIDER_ANTHROPIC,
    AI_PROVIDER_OLLAMA,
    APPROVED_AI_PROFILES,
    AiModelProfile,
    validate_profile_provider_routing,
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
DEFAULT_ANTHROPIC_TIMEOUT_SECONDS = 20.0
DEFAULT_ANTHROPIC_API_VERSION = "2023-06-01"
DEFAULT_ANTHROPIC_DAILY_BUDGET_USD = 0.0
DEFAULT_ANTHROPIC_INPUT_COST_PER_MILLION_TOKENS = 0.0
DEFAULT_ANTHROPIC_OUTPUT_COST_PER_MILLION_TOKENS = 0.0
DEFAULT_MAX_PROMPT_CHARS = 12000
DEFAULT_FAST_MODEL = "llama3.2:3b"
DEFAULT_AGENTIC_PLANNING_MODEL = ""
DEFAULT_GUIDED_MODEL = "llama3.1:8b"
DEFAULT_DEEP_MODEL = "llama3.1:8b"
DEFAULT_DEVELOPER_MODEL = "llama3.1:8b"
DEFAULT_FAST_TIMEOUT_SECONDS = 45.0
DEFAULT_AGENTIC_PLANNING_TIMEOUT_SECONDS = 90.0
DEFAULT_GUIDED_TIMEOUT_SECONDS = 120.0
DEFAULT_DEEP_TIMEOUT_SECONDS = 150.0
DEFAULT_DEVELOPER_TIMEOUT_SECONDS = 120.0
DEFAULT_FAST_MAX_PROMPT_CHARS = 8000
DEFAULT_AGENTIC_PLANNING_MAX_PROMPT_CHARS = 8000
DEFAULT_GUIDED_MAX_PROMPT_CHARS = 14000
DEFAULT_DEEP_MAX_PROMPT_CHARS = 18000
DEFAULT_DEVELOPER_MAX_PROMPT_CHARS = 20000
DEFAULT_FAST_MAX_OUTPUT_TOKENS = 512
DEFAULT_AGENTIC_PLANNING_MAX_OUTPUT_TOKENS = 1024
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
    anthropic_enabled: bool = False
    anthropic_enabled_valid: bool = True
    anthropic_routing_enabled: bool = False
    anthropic_api_key: str = field(default="", repr=False, compare=False)
    anthropic_model: str = ""
    anthropic_timeout_seconds: float = DEFAULT_ANTHROPIC_TIMEOUT_SECONDS
    anthropic_timeout_valid: bool = True
    anthropic_api_version: str = DEFAULT_ANTHROPIC_API_VERSION
    anthropic_daily_budget_usd: float = DEFAULT_ANTHROPIC_DAILY_BUDGET_USD
    anthropic_input_cost_per_million_tokens: float = DEFAULT_ANTHROPIC_INPUT_COST_PER_MILLION_TOKENS
    anthropic_output_cost_per_million_tokens: float = DEFAULT_ANTHROPIC_OUTPUT_COST_PER_MILLION_TOKENS
    anthropic_budget_valid: bool = True
    max_prompt_chars: int = DEFAULT_MAX_PROMPT_CHARS
    profiles: dict[str, AiModelProfile] | None = None

    @property
    def local_configured(self) -> bool:
        return bool(self.local_provider and self.local_base_url and self.local_model)

    @property
    def paid_configured(self) -> bool:
        return bool(self.paid_provider and self.paid_model)

    @property
    def anthropic_configured(self) -> bool:
        return bool(
            self.anthropic_api_key
            and self.anthropic_model
            and self.anthropic_timeout_valid
            and self.anthropic_api_version
        )

    @property
    def anthropic_budget_configured(self) -> bool:
        return bool(
            self.anthropic_budget_valid
            and self.anthropic_daily_budget_usd > 0
            and self.anthropic_input_cost_per_million_tokens > 0
            and self.anthropic_output_cost_per_million_tokens > 0
        )

    def profile(self, name: str | None = None) -> AiModelProfile:
        profile_name = str(name or AI_PROFILE_FAST_TRIAGE).strip().lower()
        if profile_name not in APPROVED_AI_PROFILES:
            profile_name = AI_PROFILE_FAST_TRIAGE
        profiles = self.profiles or default_ai_profiles(
            local_model=self.local_model,
            local_timeout_seconds=self.local_timeout_seconds,
            anthropic_model=self.anthropic_model,
        )
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
            "anthropic_enabled": self.anthropic_enabled,
            "anthropic_enabled_valid": self.anthropic_enabled_valid,
            "anthropic_routing_enabled": self.anthropic_routing_enabled,
            "anthropic_api_key_configured": bool(self.anthropic_api_key),
            "anthropic_model": self.anthropic_model,
            "anthropic_timeout_seconds": self.anthropic_timeout_seconds,
            "anthropic_timeout_valid": self.anthropic_timeout_valid,
            "anthropic_api_version": self.anthropic_api_version,
            "anthropic_configured": self.anthropic_configured,
            "anthropic_daily_budget_usd": self.anthropic_daily_budget_usd,
            "anthropic_input_cost_per_million_tokens": self.anthropic_input_cost_per_million_tokens,
            "anthropic_output_cost_per_million_tokens": self.anthropic_output_cost_per_million_tokens,
            "anthropic_budget_valid": self.anthropic_budget_valid,
            "anthropic_budget_configured": self.anthropic_budget_configured,
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


def _env_bool_with_validity(name: str, default: bool = False) -> tuple[bool, bool]:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default, True
    normalized = str(raw).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True, True
    if normalized in {"0", "false", "no", "off"}:
        return False, True
    return default, False


def _env_positive_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    try:
        value = float(str(raw).strip()) if raw is not None else default
    except (TypeError, ValueError):
        return default
    if value <= 0:
        return default
    return value


def _env_positive_float_with_validity(name: str, default: float) -> tuple[float, bool]:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default, True
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        return default, False
    if value <= 0:
        return default, False
    return value, True


class AiGatewayConfigurationError(RuntimeError):
    """Raised when explicitly enabled AI provider configuration is unsafe."""


def validate_ai_gateway_startup(config: AiGatewayConfig | None = None) -> AiGatewayConfig:
    resolved = config if config is not None else load_ai_gateway_config()
    if not resolved.anthropic_enabled_valid:
        raise AiGatewayConfigurationError(
            "AI_ANTHROPIC_ENABLED must be a recognized boolean value."
        )
    if not resolved.anthropic_enabled:
        return resolved

    missing = []
    if not resolved.anthropic_api_key:
        missing.append("ANTHROPIC_API_KEY")
    if not resolved.anthropic_model:
        missing.append("AI_ANTHROPIC_MODEL")
    if not resolved.anthropic_api_version:
        missing.append("ANTHROPIC_API_VERSION")
    if missing:
        raise AiGatewayConfigurationError(
            "Anthropic is enabled but required environment variables are missing: "
            + ", ".join(missing)
        )
    if not resolved.anthropic_timeout_valid:
        raise AiGatewayConfigurationError(
            "AI_ANTHROPIC_TIMEOUT_SECONDS must be a positive number when Anthropic is enabled."
        )
    if not resolved.anthropic_budget_valid:
        raise AiGatewayConfigurationError(
            "Anthropic budget and pricing values must be positive numbers when Anthropic is enabled."
        )
    budget_missing = []
    if resolved.anthropic_daily_budget_usd <= 0:
        budget_missing.append("AI_ANTHROPIC_DAILY_BUDGET_USD")
    if resolved.anthropic_input_cost_per_million_tokens <= 0:
        budget_missing.append("AI_ANTHROPIC_INPUT_COST_PER_MILLION_TOKENS")
    if resolved.anthropic_output_cost_per_million_tokens <= 0:
        budget_missing.append("AI_ANTHROPIC_OUTPUT_COST_PER_MILLION_TOKENS")
    if budget_missing:
        raise AiGatewayConfigurationError(
            "Anthropic is enabled but required budget environment variables are missing: "
            + ", ".join(budget_missing)
        )
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", resolved.anthropic_api_version):
        raise AiGatewayConfigurationError(
            "ANTHROPIC_API_VERSION must use YYYY-MM-DD format when Anthropic is enabled."
        )
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}", resolved.anthropic_model):
        raise AiGatewayConfigurationError(
            "AI_ANTHROPIC_MODEL must be a valid provider model identifier."
        )
    return resolved


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
    anthropic_model: str = "",
) -> dict[str, AiModelProfile]:
    del local_timeout_seconds
    profiles = {
        AI_PROFILE_FAST_TRIAGE: AiModelProfile(
            name=AI_PROFILE_FAST_TRIAGE,
            provider=AI_PROVIDER_OLLAMA,
            model=_profile_model("AI_FAST_MODEL", DEFAULT_FAST_MODEL, ""),
            timeout_seconds=_env_positive_float("AI_FAST_TIMEOUT_SECONDS", DEFAULT_FAST_TIMEOUT_SECONDS),
            max_prompt_chars=_env_positive_int("AI_FAST_MAX_PROMPT_CHARS", DEFAULT_FAST_MAX_PROMPT_CHARS),
            max_output_tokens=_env_positive_int("AI_FAST_MAX_OUTPUT_TOKENS", DEFAULT_FAST_MAX_OUTPUT_TOKENS),
            temperature=_env_positive_float("AI_FAST_TEMPERATURE", 0.2),
            task_category="quick SOC triage and short explanations",
        ),
        AI_PROFILE_AGENTIC_PLANNING: AiModelProfile(
            name=AI_PROFILE_AGENTIC_PLANNING,
            provider=AI_PROVIDER_ANTHROPIC,
            model=anthropic_model,
            timeout_seconds=_profile_timeout(
                "AI_AGENTIC_PLANNING_TIMEOUT_SECONDS",
                DEFAULT_AGENTIC_PLANNING_TIMEOUT_SECONDS,
            ),
            max_prompt_chars=_env_positive_int(
                "AI_AGENTIC_PLANNING_MAX_PROMPT_CHARS",
                DEFAULT_AGENTIC_PLANNING_MAX_PROMPT_CHARS,
            ),
            max_output_tokens=_env_positive_int(
                "AI_AGENTIC_PLANNING_MAX_OUTPUT_TOKENS",
                DEFAULT_AGENTIC_PLANNING_MAX_OUTPUT_TOKENS,
            ),
            temperature=_env_positive_float("AI_AGENTIC_PLANNING_TEMPERATURE", 0.1),
            task_category="bounded agentic analyst turn planning",
            local_only=False,
            paid_fallback_enabled=True,
        ),
        AI_PROFILE_GUIDED_ANALYSIS: AiModelProfile(
            name=AI_PROFILE_GUIDED_ANALYSIS,
            provider=AI_PROVIDER_OLLAMA,
            model=_profile_model("AI_GUIDED_MODEL", DEFAULT_GUIDED_MODEL, local_model),
            timeout_seconds=_profile_timeout("AI_GUIDED_TIMEOUT_SECONDS", DEFAULT_GUIDED_TIMEOUT_SECONDS),
            max_prompt_chars=_env_positive_int("AI_GUIDED_MAX_PROMPT_CHARS", DEFAULT_GUIDED_MAX_PROMPT_CHARS),
            max_output_tokens=_env_positive_int("AI_GUIDED_MAX_OUTPUT_TOKENS", DEFAULT_GUIDED_MAX_OUTPUT_TOKENS),
            temperature=_env_positive_float("AI_GUIDED_TEMPERATURE", 0.2),
            task_category="guided multi-source SOC analysis",
        ),
        AI_PROFILE_DEEP_BRIEFING: AiModelProfile(
            name=AI_PROFILE_DEEP_BRIEFING,
            provider=AI_PROVIDER_OLLAMA,
            model=_profile_model("AI_DEEP_MODEL", DEFAULT_DEEP_MODEL, local_model),
            timeout_seconds=_profile_timeout("AI_DEEP_TIMEOUT_SECONDS", DEFAULT_DEEP_TIMEOUT_SECONDS),
            max_prompt_chars=_env_positive_int("AI_DEEP_MAX_PROMPT_CHARS", DEFAULT_DEEP_MAX_PROMPT_CHARS),
            max_output_tokens=_env_positive_int("AI_DEEP_MAX_OUTPUT_TOKENS", DEFAULT_DEEP_MAX_OUTPUT_TOKENS),
            temperature=_env_positive_float("AI_DEEP_TEMPERATURE", 0.1),
            task_category="scheduled and manual SOC briefing synthesis",
        ),
        AI_PROFILE_DEVELOPER_ASSISTANT: AiModelProfile(
            name=AI_PROFILE_DEVELOPER_ASSISTANT,
            provider=AI_PROVIDER_OLLAMA,
            model=_profile_model("AI_DEVELOPER_MODEL", DEFAULT_DEVELOPER_MODEL, local_model),
            timeout_seconds=_profile_timeout("AI_DEVELOPER_TIMEOUT_SECONDS", DEFAULT_DEVELOPER_TIMEOUT_SECONDS),
            max_prompt_chars=_env_positive_int("AI_DEVELOPER_MAX_PROMPT_CHARS", DEFAULT_DEVELOPER_MAX_PROMPT_CHARS),
            max_output_tokens=_env_positive_int("AI_DEVELOPER_MAX_OUTPUT_TOKENS", DEFAULT_DEVELOPER_MAX_OUTPUT_TOKENS),
            temperature=_env_positive_float("AI_DEVELOPER_TEMPERATURE", 0.1),
            task_category="repository architecture assistance",
        ),
    }
    validate_profile_provider_routing(profiles)
    return profiles


def load_ai_gateway_config() -> AiGatewayConfig:
    configured_mode = _env_text("AI_GATEWAY_MODE", AI_MODE_DISABLED).lower()
    mode_valid = configured_mode in VALID_AI_GATEWAY_MODES
    mode = configured_mode if mode_valid else AI_MODE_DISABLED

    legacy_local_model = _env_text("AI_LOCAL_MODEL")
    legacy_local_timeout = _env_positive_float(
        "AI_LOCAL_TIMEOUT_SECONDS",
        DEFAULT_LOCAL_TIMEOUT_SECONDS,
    )
    anthropic_model = _env_text("AI_ANTHROPIC_MODEL")
    profiles = default_ai_profiles(
        local_model=legacy_local_model,
        local_timeout_seconds=legacy_local_timeout,
        anthropic_model=anthropic_model,
    )
    fast_profile = profiles[AI_PROFILE_FAST_TRIAGE]
    anthropic_timeout, anthropic_timeout_valid = _env_positive_float_with_validity(
        "AI_ANTHROPIC_TIMEOUT_SECONDS",
        DEFAULT_ANTHROPIC_TIMEOUT_SECONDS,
    )
    anthropic_enabled, anthropic_enabled_valid = _env_bool_with_validity(
        "AI_ANTHROPIC_ENABLED",
        False,
    )
    anthropic_daily_budget, anthropic_daily_budget_valid = _env_positive_float_with_validity(
        "AI_ANTHROPIC_DAILY_BUDGET_USD",
        DEFAULT_ANTHROPIC_DAILY_BUDGET_USD,
    )
    anthropic_input_cost, anthropic_input_cost_valid = _env_positive_float_with_validity(
        "AI_ANTHROPIC_INPUT_COST_PER_MILLION_TOKENS",
        DEFAULT_ANTHROPIC_INPUT_COST_PER_MILLION_TOKENS,
    )
    anthropic_output_cost, anthropic_output_cost_valid = _env_positive_float_with_validity(
        "AI_ANTHROPIC_OUTPUT_COST_PER_MILLION_TOKENS",
        DEFAULT_ANTHROPIC_OUTPUT_COST_PER_MILLION_TOKENS,
    )
    anthropic_budget_valid = (
        anthropic_daily_budget_valid
        and anthropic_input_cost_valid
        and anthropic_output_cost_valid
    )

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
        anthropic_enabled=anthropic_enabled,
        anthropic_enabled_valid=anthropic_enabled_valid,
        anthropic_routing_enabled=(
            anthropic_enabled
            and anthropic_enabled_valid
            and anthropic_budget_valid
            and anthropic_daily_budget > 0
            and anthropic_input_cost > 0
            and anthropic_output_cost > 0
        ),
        anthropic_api_key=_env_text("ANTHROPIC_API_KEY"),
        anthropic_model=anthropic_model,
        anthropic_timeout_seconds=anthropic_timeout,
        anthropic_timeout_valid=anthropic_timeout_valid,
        anthropic_api_version=_env_text(
            "ANTHROPIC_API_VERSION",
            DEFAULT_ANTHROPIC_API_VERSION,
        ),
        anthropic_daily_budget_usd=anthropic_daily_budget,
        anthropic_input_cost_per_million_tokens=anthropic_input_cost,
        anthropic_output_cost_per_million_tokens=anthropic_output_cost,
        anthropic_budget_valid=anthropic_budget_valid,
        max_prompt_chars=_env_positive_int("AI_MAX_PROMPT_CHARS", DEFAULT_MAX_PROMPT_CHARS),
        profiles=profiles,
    )
