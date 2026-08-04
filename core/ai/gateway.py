from __future__ import annotations

import logging
import time

from core.ai.config import (
    AI_MODE_ASK_BEFORE_PAID_FALLBACK,
    AI_MODE_AUTOMATIC_FALLBACK,
    AI_MODE_DISABLED,
    AI_MODE_LOCAL_ONLY,
    AiGatewayConfig,
    load_ai_gateway_config,
)
from core.ai.models import (
    AI_STATUS_CONFIGURATION_ERROR,
    AI_STATUS_DISABLED,
    AI_STATUS_FALLBACK_BLOCKED,
    AI_STATUS_FALLBACK_REQUIRES_CONFIRMATION,
    AI_STATUS_FAILED,
    AI_STATUS_PROVIDER_INCAPABLE,
    AI_STATUS_PROVIDER_UNAVAILABLE,
    AI_STATUS_SUCCESS,
    AiGatewayRequest,
    AiGatewayResponse,
    AiRequestMetadata,
    estimate_tokens,
)
from core.ai.providers import AiProvider, build_default_providers
from core.ai.profile_registry import (
    AI_PROVIDER_ANTHROPIC,
    AI_PROVIDER_OLLAMA,
    APPROVED_AI_PROFILES,
    validate_profile_provider_routing,
)

_LOGGER = logging.getLogger(__name__)


class AiGateway:
    def __init__(
        self,
        *,
        config: AiGatewayConfig | None = None,
        providers: dict[str, AiProvider] | None = None,
    ):
        self.config = config if config is not None else load_ai_gateway_config()
        self.providers = providers if providers is not None else build_default_providers()

    def generate(self, request: AiGatewayRequest) -> AiGatewayResponse:
        prompt_tokens = estimate_tokens(request.prompt)
        profile = self.config.profile(request.profile)
        try:
            validate_profile_provider_routing(
                self.config.profiles
                or {
                    name: self.config.profile(name)
                    for name in APPROVED_AI_PROFILES
                }
            )
        except (KeyError, ValueError):
            return _failure_response(
                mode=self.config.mode,
                status=AI_STATUS_CONFIGURATION_ERROR,
                provider=profile.provider or None,
                model=profile.model or None,
                error="AI profile provider routing is invalid and failed closed.",
                error_code="invalid_profile_provider_routing",
                prompt_tokens=prompt_tokens,
                profile=profile,
            )
        if not self.config.mode_valid:
            return _failure_response(
                mode=self.config.mode,
                status=AI_STATUS_CONFIGURATION_ERROR,
                provider=profile.provider,
                model=profile.model or None,
                error="AI gateway configuration is invalid and failed closed.",
                error_code=AI_STATUS_CONFIGURATION_ERROR,
                prompt_tokens=prompt_tokens,
                profile=profile,
            )
        if self.config.mode == AI_MODE_DISABLED:
            return _failure_response(
                mode=self.config.mode,
                status=AI_STATUS_DISABLED,
                provider=profile.provider,
                model=profile.model or None,
                error="AI gateway is disabled.",
                error_code=AI_STATUS_DISABLED,
                prompt_tokens=prompt_tokens,
                profile=profile,
            )

        if profile.provider == AI_PROVIDER_OLLAMA:
            return self._try_profile_provider(request, profile=profile, paid_request=False)
        if profile.provider != AI_PROVIDER_ANTHROPIC:
            return _failure_response(
                mode=self.config.mode,
                status=AI_STATUS_CONFIGURATION_ERROR,
                provider=profile.provider or None,
                model=profile.model or None,
                error="AI profile provider is not registered in the trusted routing table.",
                error_code="profile_provider_not_registered",
                prompt_tokens=prompt_tokens,
                profile=profile,
            )
        if self.config.mode == AI_MODE_LOCAL_ONLY:
            return _failure_response(
                mode=self.config.mode,
                status=AI_STATUS_FALLBACK_BLOCKED,
                provider=profile.provider,
                model=profile.model or None,
                error="The selected AI profile requires a paid provider that local-only mode prohibits.",
                error_code="profile_provider_blocked_by_mode",
                prompt_tokens=prompt_tokens,
                profile=profile,
            )
        if self.config.mode == AI_MODE_ASK_BEFORE_PAID_FALLBACK:
            return _failure_response(
                mode=self.config.mode,
                status=AI_STATUS_FALLBACK_REQUIRES_CONFIRMATION,
                provider=profile.provider,
                model=profile.model or None,
                error="Paid profile execution requires analyst confirmation.",
                error_code=AI_STATUS_FALLBACK_REQUIRES_CONFIRMATION,
                prompt_tokens=prompt_tokens,
                profile=profile,
            )
        if self.config.mode == AI_MODE_AUTOMATIC_FALLBACK:
            return self._try_paid_profile(request, profile=profile)
        return _failure_response(
            mode=self.config.mode,
            status=AI_STATUS_CONFIGURATION_ERROR,
            provider=profile.provider,
            model=profile.model or None,
            error="AI gateway mode is unsupported.",
            error_code=AI_STATUS_CONFIGURATION_ERROR,
            prompt_tokens=prompt_tokens,
            profile=profile,
        )

    def _try_profile_provider(self, request: AiGatewayRequest, *, profile, paid_request: bool) -> AiGatewayResponse:
        provider_key = profile.provider
        if provider_key == AI_PROVIDER_OLLAMA:
            configured = self.config.local_provider == provider_key and self.config.local_configured and bool(profile.model)
            not_configured_code = "local_provider_not_configured"
            not_configured_message = "Local AI provider is not configured for the selected AI profile."
        elif provider_key == AI_PROVIDER_ANTHROPIC:
            configured = (
                self.config.anthropic_enabled
                and self.config.anthropic_configured
                and bool(profile.model)
                and profile.model == self.config.anthropic_model
            )
            not_configured_code = "anthropic_configuration_invalid"
            not_configured_message = "Anthropic provider configuration is invalid or incomplete."
        else:
            configured = False
            not_configured_code = "profile_provider_not_registered"
            not_configured_message = "AI profile provider is not registered."

        provider = self.providers.get(provider_key)
        if provider is None or not configured:
            return _failure_response(
                mode=self.config.mode,
                status=AI_STATUS_PROVIDER_UNAVAILABLE if provider_key == AI_PROVIDER_OLLAMA else AI_STATUS_CONFIGURATION_ERROR,
                provider=provider_key,
                model=profile.model or None,
                error=not_configured_message,
                error_code=not_configured_code,
                prompt_tokens=estimate_tokens(request.prompt),
                local_request=not paid_request,
                paid_request=paid_request,
                profile=profile,
            )

        capability = provider.supports(request)
        if not capability.capable:
            return _failure_response(
                mode=self.config.mode,
                status=AI_STATUS_PROVIDER_INCAPABLE,
                provider=provider_key,
                model=profile.model or None,
                error=capability.reason or "AI provider is incapable.",
                error_code=capability.status,
                prompt_tokens=estimate_tokens(request.prompt),
                local_request=not paid_request,
                paid_request=paid_request,
                profile=profile,
            )

        try:
            return provider.generate(request, self.config)
        except Exception as error:
            _LOGGER.warning(
                "ai_gateway_provider_error provider=%s error_type=%s",
                provider_key,
                type(error).__name__,
            )
            return _failure_response(
                mode=self.config.mode,
                status=AI_STATUS_FAILED,
                provider=provider_key,
                model=profile.model or None,
                error="AI provider failed.",
                error_code="provider_exception",
                prompt_tokens=estimate_tokens(request.prompt),
                local_request=not paid_request,
                paid_request=paid_request,
                profile=profile,
            )

    def _try_paid_profile(self, request: AiGatewayRequest, *, profile) -> AiGatewayResponse:
        prompt_tokens = estimate_tokens(request.prompt)
        if not profile.paid_fallback_enabled or profile.local_only:
            return _failure_response(
                mode=self.config.mode,
                status=AI_STATUS_FALLBACK_BLOCKED,
                provider=profile.provider,
                model=profile.model or None,
                error="The selected AI profile is not eligible for paid execution.",
                error_code="profile_not_paid_eligible",
                prompt_tokens=prompt_tokens,
                profile=profile,
            )
        if not self.config.anthropic_routing_enabled:
            return _failure_response(
                mode=self.config.mode,
                status=AI_STATUS_FALLBACK_BLOCKED,
                provider=profile.provider,
                model=profile.model or None,
                error="Anthropic profile routing remains feature-disabled until paid accounting is implemented.",
                error_code="anthropic_routing_not_enabled",
                prompt_tokens=prompt_tokens,
                profile=profile,
            )
        return self._try_profile_provider(request, profile=profile, paid_request=True)


def _failure_response(
    *,
    mode: str,
    status: str,
    error: str,
    error_code: str,
    prompt_tokens: int,
    provider: str | None = None,
    model: str | None = None,
    fallback_attempted: bool = False,
    fallback_reason: str | None = None,
    local_request: bool = False,
    paid_request: bool = False,
    profile=None,
) -> AiGatewayResponse:
    started = time.monotonic()
    return AiGatewayResponse(
        status=status,
        content=None,
        error=error,
        metadata=AiRequestMetadata(
            provider=provider,
            model=model,
            mode=mode,
            status=status,
            latency_ms=max(0, int((time.monotonic() - started) * 1000)),
            estimated_prompt_tokens=prompt_tokens,
            estimated_completion_tokens=0,
            estimated_cost_usd=0 if local_request else None,
            local_request=local_request,
            paid_request=paid_request,
            fallback_attempted=fallback_attempted,
            fallback_reason=fallback_reason,
            error_code=error_code,
            profile=profile.name if profile else None,
            task_category=profile.task_category if profile else None,
            timeout_seconds=profile.timeout_seconds if profile else None,
            max_output_tokens=profile.max_output_tokens if profile else None,
        ),
    )
