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
from core.ai.providers import AiProvider, build_default_providers, with_fallback_metadata

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
        if not self.config.mode_valid:
            return _failure_response(
                mode=self.config.mode,
                status=AI_STATUS_CONFIGURATION_ERROR,
                error="AI gateway configuration is invalid and failed closed.",
                error_code=AI_STATUS_CONFIGURATION_ERROR,
                prompt_tokens=prompt_tokens,
            )
        if self.config.mode == AI_MODE_DISABLED:
            return _failure_response(
                mode=self.config.mode,
                status=AI_STATUS_DISABLED,
                error="AI gateway is disabled.",
                error_code=AI_STATUS_DISABLED,
                prompt_tokens=prompt_tokens,
            )

        local_response = self._try_local(request)
        if local_response.status == AI_STATUS_SUCCESS:
            return local_response

        fallback_reason = local_response.metadata.error_code or local_response.status
        if self.config.mode == AI_MODE_LOCAL_ONLY:
            return with_fallback_metadata(
                local_response,
                fallback_attempted=False,
                fallback_reason=fallback_reason,
            )
        if self.config.mode == AI_MODE_ASK_BEFORE_PAID_FALLBACK:
            return _failure_response(
                mode=self.config.mode,
                status=AI_STATUS_FALLBACK_REQUIRES_CONFIRMATION,
                error="Paid fallback requires analyst confirmation.",
                error_code=AI_STATUS_FALLBACK_REQUIRES_CONFIRMATION,
                prompt_tokens=prompt_tokens,
                fallback_attempted=True,
                fallback_reason=fallback_reason,
            )
        if self.config.mode == AI_MODE_AUTOMATIC_FALLBACK:
            return self._try_automatic_paid_fallback(request, fallback_reason)

        return _failure_response(
            mode=self.config.mode,
            status=AI_STATUS_CONFIGURATION_ERROR,
            error="AI gateway mode is unsupported.",
            error_code=AI_STATUS_CONFIGURATION_ERROR,
            prompt_tokens=prompt_tokens,
        )

    def _try_local(self, request: AiGatewayRequest) -> AiGatewayResponse:
        provider = self.providers.get(self.config.local_provider)
        if provider is None or not self.config.local_configured:
            return _failure_response(
                mode=self.config.mode,
                status=AI_STATUS_PROVIDER_UNAVAILABLE,
                provider=self.config.local_provider or None,
                model=self.config.local_model or None,
                error="Local AI provider is not configured.",
                error_code="local_provider_not_configured",
                prompt_tokens=estimate_tokens(request.prompt),
                local_request=True,
            )

        capability = provider.supports(request)
        if not capability.capable:
            return _failure_response(
                mode=self.config.mode,
                status=AI_STATUS_PROVIDER_INCAPABLE,
                provider=self.config.local_provider,
                model=self.config.local_model,
                error=capability.reason or "Local AI provider is incapable.",
                error_code=capability.status,
                prompt_tokens=estimate_tokens(request.prompt),
                local_request=True,
            )

        try:
            return provider.generate(request, self.config)
        except Exception:
            _LOGGER.exception("ai_gateway_provider_error provider=%s", self.config.local_provider)
            return _failure_response(
                mode=self.config.mode,
                status=AI_STATUS_FAILED,
                provider=self.config.local_provider,
                model=self.config.local_model,
                error="Local AI provider failed.",
                error_code="provider_exception",
                prompt_tokens=estimate_tokens(request.prompt),
                local_request=True,
            )

    def _try_automatic_paid_fallback(
        self,
        request: AiGatewayRequest,
        fallback_reason: str | None,
    ) -> AiGatewayResponse:
        prompt_tokens = estimate_tokens(request.prompt)
        if not self.config.paid_fallback_enabled or not self.config.paid_configured:
            return _failure_response(
                mode=self.config.mode,
                status=AI_STATUS_FALLBACK_BLOCKED,
                error="Paid fallback is not enabled or configured.",
                error_code=AI_STATUS_FALLBACK_BLOCKED,
                prompt_tokens=prompt_tokens,
                fallback_attempted=True,
                fallback_reason=fallback_reason,
            )

        provider = self.providers.get(self.config.paid_provider)
        if provider is None:
            return _failure_response(
                mode=self.config.mode,
                status=AI_STATUS_FALLBACK_BLOCKED,
                provider=self.config.paid_provider,
                model=self.config.paid_model,
                error="Paid AI provider is not registered.",
                error_code="paid_provider_not_registered",
                prompt_tokens=prompt_tokens,
                fallback_attempted=True,
                fallback_reason=fallback_reason,
                paid_request=True,
            )

        capability = provider.supports(request)
        if not capability.capable:
            return _failure_response(
                mode=self.config.mode,
                status=AI_STATUS_PROVIDER_INCAPABLE,
                provider=self.config.paid_provider,
                model=self.config.paid_model,
                error=capability.reason or "Paid AI provider is incapable.",
                error_code=capability.status,
                prompt_tokens=prompt_tokens,
                fallback_attempted=True,
                fallback_reason=fallback_reason,
                paid_request=True,
            )

        try:
            return with_fallback_metadata(
                provider.generate(request, self.config),
                fallback_attempted=True,
                fallback_reason=fallback_reason,
            )
        except Exception:
            _LOGGER.exception("ai_gateway_provider_error provider=%s", self.config.paid_provider)
            return _failure_response(
                mode=self.config.mode,
                status=AI_STATUS_FAILED,
                provider=self.config.paid_provider,
                model=self.config.paid_model,
                error="Paid AI provider failed.",
                error_code="provider_exception",
                prompt_tokens=prompt_tokens,
                fallback_attempted=True,
                fallback_reason=fallback_reason,
                paid_request=True,
            )


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
        ),
    )
