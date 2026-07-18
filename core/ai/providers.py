from __future__ import annotations

from dataclasses import replace
import json
import logging
import time
from typing import Protocol
from urllib import error as url_error
from urllib import request as url_request
from urllib.parse import urljoin

from core.ai.config import AiGatewayConfig
from core.ai.models import (
    AI_STATUS_DISABLED,
    AI_STATUS_FAILED,
    AI_STATUS_PROVIDER_INCAPABLE,
    AI_STATUS_PROVIDER_TIMEOUT,
    AI_STATUS_PROVIDER_UNAVAILABLE,
    AI_STATUS_SUCCESS,
    AiCapabilityResult,
    AiGatewayRequest,
    AiGatewayResponse,
    AiProviderReadiness,
    AiRequestMetadata,
    estimate_tokens,
)

_LOGGER = logging.getLogger(__name__)


class AiProvider(Protocol):
    provider_key: str

    def supports(self, request: AiGatewayRequest) -> AiCapabilityResult:
        ...

    def readiness(self, config: AiGatewayConfig) -> AiProviderReadiness:
        ...

    def generate(self, request: AiGatewayRequest, config: AiGatewayConfig) -> AiGatewayResponse:
        ...


class DisabledAiProvider:
    provider_key = "disabled"

    def supports(self, request: AiGatewayRequest) -> AiCapabilityResult:
        return AiCapabilityResult(False, AI_STATUS_DISABLED, "AI gateway is disabled.")

    def readiness(self, config: AiGatewayConfig) -> AiProviderReadiness:
        return AiProviderReadiness(
            provider=self.provider_key,
            configured=False,
            ready=False,
            status=AI_STATUS_DISABLED,
        )

    def generate(self, request: AiGatewayRequest, config: AiGatewayConfig) -> AiGatewayResponse:
        return AiGatewayResponse(
            status=AI_STATUS_DISABLED,
            content=None,
            error="AI gateway is disabled.",
            metadata=AiRequestMetadata(
                provider=self.provider_key,
                model=None,
                mode=config.mode,
                status=AI_STATUS_DISABLED,
                estimated_prompt_tokens=estimate_tokens(request.prompt),
                estimated_cost_usd=0,
                error_code=AI_STATUS_DISABLED,
            ),
        )


class OllamaProvider:
    provider_key = "ollama"

    def supports(self, request: AiGatewayRequest) -> AiCapabilityResult:
        if request.capability != "text_generation":
            return AiCapabilityResult(
                False,
                AI_STATUS_PROVIDER_INCAPABLE,
                f"Unsupported capability: {request.capability}",
            )
        return AiCapabilityResult(True, AI_STATUS_SUCCESS)

    def readiness(self, config: AiGatewayConfig) -> AiProviderReadiness:
        missing = []
        if not config.local_base_url:
            missing.append("AI_LOCAL_BASE_URL")
        if not config.local_model:
            missing.append("AI_LOCAL_MODEL")
        if missing:
            return AiProviderReadiness(
                provider=self.provider_key,
                configured=False,
                ready=False,
                status=AI_STATUS_PROVIDER_UNAVAILABLE,
                model=config.local_model or None,
                missing_env_vars=missing,
                error_code="missing_config",
            )

        try:
            _http_json(
                "GET",
                _ollama_url(config.local_base_url, "/api/tags"),
                timeout=config.local_timeout_seconds,
            )
        except TimeoutError:
            return AiProviderReadiness(
                provider=self.provider_key,
                configured=True,
                ready=False,
                status=AI_STATUS_PROVIDER_TIMEOUT,
                model=config.local_model,
                error_code=AI_STATUS_PROVIDER_TIMEOUT,
            )
        except OSError:
            return AiProviderReadiness(
                provider=self.provider_key,
                configured=True,
                ready=False,
                status=AI_STATUS_PROVIDER_UNAVAILABLE,
                model=config.local_model,
                error_code=AI_STATUS_PROVIDER_UNAVAILABLE,
            )
        except Exception:
            _LOGGER.exception("ai_provider_readiness_error provider=%s", self.provider_key)
            return AiProviderReadiness(
                provider=self.provider_key,
                configured=True,
                ready=False,
                status=AI_STATUS_FAILED,
                model=config.local_model,
                error_code=AI_STATUS_FAILED,
            )

        return AiProviderReadiness(
            provider=self.provider_key,
            configured=True,
            ready=True,
            status=AI_STATUS_SUCCESS,
            model=config.local_model,
        )

    def generate(self, request: AiGatewayRequest, config: AiGatewayConfig) -> AiGatewayResponse:
        started = time.monotonic()
        prompt_tokens = estimate_tokens(request.prompt)
        if len(request.prompt) > config.max_prompt_chars:
            return _provider_response(
                provider=self.provider_key,
                model=config.local_model,
                mode=config.mode,
                status=AI_STATUS_FAILED,
                prompt_tokens=prompt_tokens,
                started=started,
                error="AI request exceeds configured prompt limit.",
                error_code="prompt_too_large",
                local_request=True,
            )

        payload = {
            "model": config.local_model,
            "prompt": request.prompt,
            "stream": False,
        }
        try:
            response = _http_json(
                "POST",
                _ollama_url(config.local_base_url, "/api/generate"),
                payload=payload,
                timeout=config.local_timeout_seconds,
            )
        except TimeoutError:
            return _provider_response(
                provider=self.provider_key,
                model=config.local_model,
                mode=config.mode,
                status=AI_STATUS_PROVIDER_TIMEOUT,
                prompt_tokens=prompt_tokens,
                started=started,
                error="Local AI provider timed out.",
                error_code=AI_STATUS_PROVIDER_TIMEOUT,
                local_request=True,
            )
        except OSError:
            return _provider_response(
                provider=self.provider_key,
                model=config.local_model,
                mode=config.mode,
                status=AI_STATUS_PROVIDER_UNAVAILABLE,
                prompt_tokens=prompt_tokens,
                started=started,
                error="Local AI provider is unavailable.",
                error_code=AI_STATUS_PROVIDER_UNAVAILABLE,
                local_request=True,
            )

        content = str(response.get("response", "")).strip()
        return _provider_response(
            provider=self.provider_key,
            model=config.local_model,
            mode=config.mode,
            status=AI_STATUS_SUCCESS,
            prompt_tokens=prompt_tokens,
            completion_tokens=estimate_tokens(content),
            started=started,
            content=content,
            local_request=True,
        )


class PlaceholderPaidProvider:
    """Provider slot for future paid AI integrations without mandatory SDKs."""

    provider_key = "paid"

    def supports(self, request: AiGatewayRequest) -> AiCapabilityResult:
        if request.capability != "text_generation":
            return AiCapabilityResult(
                False,
                AI_STATUS_PROVIDER_INCAPABLE,
                f"Unsupported capability: {request.capability}",
            )
        return AiCapabilityResult(True, AI_STATUS_SUCCESS)

    def readiness(self, config: AiGatewayConfig) -> AiProviderReadiness:
        credential_envs = _paid_credential_envs(config.paid_provider)
        credential_configured = {name: _env_present(name) for name in credential_envs}
        missing = []
        if not config.paid_provider:
            missing.append("AI_PAID_PROVIDER")
        if not config.paid_model:
            missing.append("AI_PAID_MODEL")
        missing.extend(name for name, configured in credential_configured.items() if not configured)

        return AiProviderReadiness(
            provider=config.paid_provider or self.provider_key,
            configured=bool(config.paid_provider and config.paid_model),
            ready=False,
            status=AI_STATUS_PROVIDER_UNAVAILABLE,
            model=config.paid_model or None,
            missing_env_vars=missing,
            credential_env_vars=credential_envs,
            credential_configured=credential_configured,
            error_code="paid_provider_not_implemented",
        )

    def generate(self, request: AiGatewayRequest, config: AiGatewayConfig) -> AiGatewayResponse:
        return AiGatewayResponse(
            status=AI_STATUS_PROVIDER_UNAVAILABLE,
            content=None,
            error="Paid AI provider execution is not implemented in Phase 1A.",
            metadata=AiRequestMetadata(
                provider=config.paid_provider or self.provider_key,
                model=config.paid_model or None,
                mode=config.mode,
                status=AI_STATUS_PROVIDER_UNAVAILABLE,
                estimated_prompt_tokens=estimate_tokens(request.prompt),
                estimated_cost_usd=None,
                paid_request=True,
                error_code="paid_provider_not_implemented",
            ),
        )


def build_default_providers() -> dict[str, AiProvider]:
    ollama = OllamaProvider()
    disabled = DisabledAiProvider()
    paid = PlaceholderPaidProvider()
    return {
        disabled.provider_key: disabled,
        ollama.provider_key: ollama,
        paid.provider_key: paid,
        "openai": paid,
        "anthropic": paid,
    }


def _paid_credential_envs(provider: str) -> list[str]:
    if provider == "openai":
        return ["OPENAI_API_KEY"]
    if provider == "anthropic":
        return ["ANTHROPIC_API_KEY"]
    return []


def _env_present(name: str) -> bool:
    from os import getenv

    return bool(getenv(name, "").strip())


def _ollama_url(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _http_json(
    method: str,
    url: str,
    *,
    payload: dict[str, object] | None = None,
    timeout: float,
) -> dict[str, object]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = url_request.Request(url, data=data, headers=headers, method=method)
    try:
        with url_request.urlopen(req, timeout=timeout) as response:
            body = response.read()
    except url_error.URLError as error:
        reason = getattr(error, "reason", error)
        if isinstance(reason, TimeoutError):
            raise TimeoutError() from error
        raise OSError("AI provider request failed") from error
    except TimeoutError:
        raise

    if not body:
        return {}
    return json.loads(body.decode("utf-8"))


def _provider_response(
    *,
    provider: str,
    model: str | None,
    mode: str,
    status: str,
    prompt_tokens: int,
    started: float,
    completion_tokens: int = 0,
    content: str | None = None,
    error: str | None = None,
    error_code: str | None = None,
    local_request: bool = False,
    paid_request: bool = False,
) -> AiGatewayResponse:
    metadata = AiRequestMetadata(
        provider=provider,
        model=model,
        mode=mode,
        status=status,
        latency_ms=max(0, int((time.monotonic() - started) * 1000)),
        estimated_prompt_tokens=prompt_tokens,
        estimated_completion_tokens=completion_tokens,
        estimated_cost_usd=0 if local_request else None,
        local_request=local_request,
        paid_request=paid_request,
        error_code=error_code,
    )
    return AiGatewayResponse(status=status, content=content, error=error, metadata=metadata)


def with_fallback_metadata(
    response: AiGatewayResponse,
    *,
    fallback_attempted: bool,
    fallback_reason: str | None,
) -> AiGatewayResponse:
    return replace(
        response,
        metadata=replace(
            response.metadata,
            fallback_attempted=fallback_attempted,
            fallback_reason=fallback_reason,
        ),
    )
