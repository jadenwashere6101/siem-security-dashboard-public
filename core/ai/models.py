from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

AI_STATUS_DISABLED = "disabled"
AI_STATUS_SUCCESS = "success"
AI_STATUS_PROVIDER_UNAVAILABLE = "provider_unavailable"
AI_STATUS_PROVIDER_TIMEOUT = "provider_timeout"
AI_STATUS_PROVIDER_INCAPABLE = "provider_incapable"
AI_STATUS_FALLBACK_REQUIRES_CONFIRMATION = "fallback_requires_confirmation"
AI_STATUS_FALLBACK_BLOCKED = "fallback_blocked"
AI_STATUS_CONFIGURATION_ERROR = "configuration_error"
AI_STATUS_FAILED = "failed"


@dataclass(frozen=True)
class AiGatewayRequest:
    prompt: str
    capability: str = "text_generation"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AiCapabilityResult:
    capable: bool
    status: str
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AiProviderReadiness:
    provider: str
    configured: bool
    ready: bool
    status: str
    model: str | None = None
    missing_env_vars: list[str] = field(default_factory=list)
    credential_env_vars: list[str] = field(default_factory=list)
    credential_configured: dict[str, bool] = field(default_factory=dict)
    error_code: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "configured": self.configured,
            "ready": self.ready,
            "status": self.status,
            "model": self.model,
            "missing_env_vars": list(self.missing_env_vars),
            "credential_env_vars": list(self.credential_env_vars),
            "credential_configured": dict(self.credential_configured),
            "error_code": self.error_code,
        }


@dataclass(frozen=True)
class AiRequestMetadata:
    provider: str | None
    model: str | None
    mode: str
    status: str
    read_only: bool = True
    latency_ms: int | None = None
    estimated_prompt_tokens: int = 0
    estimated_completion_tokens: int = 0
    estimated_cost_usd: float | None = None
    local_request: bool = False
    paid_request: bool = False
    fallback_attempted: bool = False
    fallback_reason: str | None = None
    error_code: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AiGatewayResponse:
    status: str
    content: str | None
    metadata: AiRequestMetadata
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "content": self.content,
            "metadata": self.metadata.as_dict(),
            "error": self.error,
        }


def estimate_tokens(text: str | None) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)
