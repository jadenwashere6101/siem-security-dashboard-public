from __future__ import annotations

from dataclasses import replace
import json
import logging
import socket
import time
from typing import Protocol
from urllib import error as url_error
from urllib import request as url_request
from urllib.parse import urljoin

from core.ai.config import AiGatewayConfig, AiGatewayConfigurationError, validate_ai_gateway_startup
from core.ai.models import (
    AI_STATUS_CONFIGURATION_ERROR,
    AI_STATUS_DISABLED,
    AI_STATUS_FAILED,
    AI_STATUS_PROVIDER_AUTHENTICATION_ERROR,
    AI_STATUS_PROVIDER_INCAPABLE,
    AI_STATUS_PROVIDER_MALFORMED_RESPONSE,
    AI_STATUS_PROVIDER_RATE_LIMITED,
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

OLLAMA_CAPABILITIES = frozenset(
    {
        "agentic_analyst_planning",
        "scheduled_soc_briefing",
        "text_generation",
    }
)

ANTHROPIC_CAPABILITIES = frozenset({"agentic_analyst_planning"})
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"


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
        if request.capability not in OLLAMA_CAPABILITIES:
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
        profile = config.profile(request.profile)
        if len(request.prompt) > profile.max_prompt_chars:
            return _provider_response(
                provider=self.provider_key,
                model=profile.model,
                mode=config.mode,
                status=AI_STATUS_FAILED,
                prompt_tokens=prompt_tokens,
                started=started,
                error="AI request exceeds configured profile prompt limit.",
                error_code="prompt_too_large",
                local_request=True,
                profile=profile,
            )

        payload = {
            "model": profile.model,
            "prompt": request.prompt,
            "stream": False,
            "options": {
                "num_predict": profile.max_output_tokens,
                "temperature": profile.temperature,
            },
        }
        try:
            response = _http_json(
                "POST",
                _ollama_url(config.local_base_url, "/api/generate"),
                payload=payload,
                timeout=profile.timeout_seconds,
            )
        except TimeoutError:
            return _provider_response(
                provider=self.provider_key,
                model=profile.model,
                mode=config.mode,
                status=AI_STATUS_PROVIDER_TIMEOUT,
                prompt_tokens=prompt_tokens,
                started=started,
                error="Local AI provider timed out for the selected profile. The model may still be cold-loading or generation exceeded the bounded timeout.",
                error_code=AI_STATUS_PROVIDER_TIMEOUT,
                local_request=True,
                profile=profile,
            )
        except OSError:
            return _provider_response(
                provider=self.provider_key,
                model=profile.model,
                mode=config.mode,
                status=AI_STATUS_PROVIDER_UNAVAILABLE,
                prompt_tokens=prompt_tokens,
                started=started,
                error="Local AI provider is unavailable.",
                error_code=AI_STATUS_PROVIDER_UNAVAILABLE,
                local_request=True,
                profile=profile,
            )

        content = str(response.get("response", "")).strip()
        return _provider_response(
            provider=self.provider_key,
            model=profile.model,
            mode=config.mode,
            status=AI_STATUS_SUCCESS,
            prompt_tokens=prompt_tokens,
            completion_tokens=estimate_tokens(content),
            started=started,
            content=content,
            local_request=True,
            profile=profile,
        )


class _AnthropicHttpError(Exception):
    def __init__(self, status_code: int):
        super().__init__("Anthropic HTTP request failed")
        self.status_code = status_code


class _AnthropicMalformedResponse(Exception):
    pass


class AnthropicProvider:
    provider_key = "anthropic"

    def supports(self, request: AiGatewayRequest) -> AiCapabilityResult:
        if request.capability not in ANTHROPIC_CAPABILITIES:
            return AiCapabilityResult(
                False,
                AI_STATUS_PROVIDER_INCAPABLE,
                f"Unsupported capability: {request.capability}",
            )
        return AiCapabilityResult(True, AI_STATUS_SUCCESS)

    def readiness(self, config: AiGatewayConfig) -> AiProviderReadiness:
        credential_configured = {"ANTHROPIC_API_KEY": bool(config.anthropic_api_key)}
        missing = []
        if not config.anthropic_api_key:
            missing.append("ANTHROPIC_API_KEY")
        if not config.anthropic_model:
            missing.append("AI_ANTHROPIC_MODEL")
        if not config.anthropic_api_version:
            missing.append("ANTHROPIC_API_VERSION")

        if not config.anthropic_enabled_valid:
            return AiProviderReadiness(
                provider=self.provider_key,
                configured=False,
                ready=False,
                status=AI_STATUS_CONFIGURATION_ERROR,
                model=config.anthropic_model or None,
                missing_env_vars=missing,
                credential_env_vars=["ANTHROPIC_API_KEY"],
                credential_configured=credential_configured,
                error_code="anthropic_configuration_invalid",
                readiness_scope="configuration_only",
            )

        if not config.anthropic_enabled:
            return AiProviderReadiness(
                provider=self.provider_key,
                configured=config.anthropic_configured,
                ready=False,
                status=AI_STATUS_DISABLED,
                model=config.anthropic_model or None,
                missing_env_vars=missing,
                credential_env_vars=["ANTHROPIC_API_KEY"],
                credential_configured=credential_configured,
                error_code="anthropic_disabled",
                readiness_scope="configuration_only",
            )

        try:
            validate_ai_gateway_startup(config)
        except AiGatewayConfigurationError:
            return AiProviderReadiness(
                provider=self.provider_key,
                configured=False,
                ready=False,
                status=AI_STATUS_CONFIGURATION_ERROR,
                model=config.anthropic_model or None,
                missing_env_vars=missing,
                credential_env_vars=["ANTHROPIC_API_KEY"],
                credential_configured=credential_configured,
                error_code="anthropic_configuration_invalid",
                readiness_scope="configuration_only",
            )

        return AiProviderReadiness(
            provider=self.provider_key,
            configured=True,
            ready=True,
            status=AI_STATUS_SUCCESS,
            model=config.anthropic_model,
            credential_env_vars=["ANTHROPIC_API_KEY"],
            credential_configured=credential_configured,
            error_code=None,
            readiness_scope="configuration_only",
        )

    def generate(self, request: AiGatewayRequest, config: AiGatewayConfig) -> AiGatewayResponse:
        started = time.monotonic()
        prompt_tokens = estimate_tokens(request.prompt)
        profile = config.profile(request.profile)

        capability = self.supports(request)
        if not capability.capable:
            return _provider_response(
                provider=self.provider_key,
                model=profile.model or None,
                mode=config.mode,
                status=AI_STATUS_PROVIDER_INCAPABLE,
                prompt_tokens=prompt_tokens,
                started=started,
                error=capability.reason or "Anthropic provider is incapable.",
                error_code=capability.status,
                paid_request=True,
                profile=profile,
            )

        try:
            validate_ai_gateway_startup(config)
        except AiGatewayConfigurationError:
            return _provider_response(
                provider=self.provider_key,
                model=profile.model or None,
                mode=config.mode,
                status=AI_STATUS_CONFIGURATION_ERROR,
                prompt_tokens=prompt_tokens,
                started=started,
                error="Anthropic provider configuration is invalid or incomplete.",
                error_code="anthropic_configuration_invalid",
                paid_request=True,
                profile=profile,
            )

        if len(request.prompt) > profile.max_prompt_chars:
            return _provider_response(
                provider=self.provider_key,
                model=profile.model,
                mode=config.mode,
                status=AI_STATUS_FAILED,
                prompt_tokens=prompt_tokens,
                started=started,
                error="AI request exceeds configured profile prompt limit.",
                error_code="prompt_too_large",
                paid_request=True,
                profile=profile,
            )

        payload = {
            "model": profile.model,
            "max_tokens": profile.max_output_tokens,
            "messages": [{"role": "user", "content": request.prompt}],
            "temperature": profile.temperature,
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-api-key": config.anthropic_api_key,
            "anthropic-version": config.anthropic_api_version,
        }

        try:
            response = _anthropic_http_json(
                payload=payload,
                headers=headers,
                timeout=profile.timeout_seconds,
            )
            content = _anthropic_content(response)
            input_tokens, output_tokens = _anthropic_usage(response)
        except TimeoutError:
            return self._failure(
                config=config,
                profile=profile,
                prompt_tokens=prompt_tokens,
                started=started,
                status=AI_STATUS_PROVIDER_TIMEOUT,
                error="Anthropic provider timed out.",
                error_code=AI_STATUS_PROVIDER_TIMEOUT,
            )
        except _AnthropicHttpError as error:
            status, message, error_code = _anthropic_http_outcome(error.status_code)
            return self._failure(
                config=config,
                profile=profile,
                prompt_tokens=prompt_tokens,
                started=started,
                status=status,
                error=message,
                error_code=error_code,
            )
        except _AnthropicMalformedResponse:
            return self._failure(
                config=config,
                profile=profile,
                prompt_tokens=prompt_tokens,
                started=started,
                status=AI_STATUS_PROVIDER_MALFORMED_RESPONSE,
                error="Anthropic provider returned a malformed response.",
                error_code=AI_STATUS_PROVIDER_MALFORMED_RESPONSE,
            )
        except OSError:
            return self._failure(
                config=config,
                profile=profile,
                prompt_tokens=prompt_tokens,
                started=started,
                status=AI_STATUS_PROVIDER_UNAVAILABLE,
                error="Anthropic provider is unavailable.",
                error_code=AI_STATUS_PROVIDER_UNAVAILABLE,
            )
        except Exception as error:
            _LOGGER.warning(
                "anthropic_provider_error error_type=%s",
                type(error).__name__,
            )
            return self._failure(
                config=config,
                profile=profile,
                prompt_tokens=prompt_tokens,
                started=started,
                status=AI_STATUS_FAILED,
                error="Anthropic provider failed.",
                error_code=AI_STATUS_FAILED,
            )

        return _provider_response(
            provider=self.provider_key,
            model=profile.model,
            mode=config.mode,
            status=AI_STATUS_SUCCESS,
            prompt_tokens=prompt_tokens,
            completion_tokens=estimate_tokens(content),
            provider_prompt_tokens=input_tokens,
            provider_completion_tokens=output_tokens,
            started=started,
            content=content,
            paid_request=True,
            profile=profile,
        )

    def _failure(
        self,
        *,
        config: AiGatewayConfig,
        profile,
        prompt_tokens: int,
        started: float,
        status: str,
        error: str,
        error_code: str,
    ) -> AiGatewayResponse:
        return _provider_response(
            provider=self.provider_key,
            model=profile.model or None,
            mode=config.mode,
            status=status,
            prompt_tokens=prompt_tokens,
            started=started,
            error=error,
            error_code=error_code,
            paid_request=True,
            profile=profile,
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
    anthropic = AnthropicProvider()
    return {
        disabled.provider_key: disabled,
        ollama.provider_key: ollama,
        paid.provider_key: paid,
        "openai": paid,
        anthropic.provider_key: anthropic,
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


def _anthropic_http_json(
    *,
    payload: dict[str, object],
    headers: dict[str, str],
    timeout: float,
) -> dict[str, object]:
    req = url_request.Request(
        ANTHROPIC_MESSAGES_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with url_request.urlopen(req, timeout=timeout) as response:
            body = response.read()
    except url_error.HTTPError as error:
        raise _AnthropicHttpError(int(error.code)) from None
    except url_error.URLError as error:
        reason = getattr(error, "reason", None)
        if isinstance(reason, (TimeoutError, socket.timeout)):
            raise TimeoutError() from None
        raise OSError("Anthropic provider request failed") from None
    except (TimeoutError, socket.timeout):
        raise TimeoutError() from None

    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise _AnthropicMalformedResponse() from None
    if not isinstance(decoded, dict):
        raise _AnthropicMalformedResponse()
    return decoded


def _anthropic_content(response: dict[str, object]) -> str:
    blocks = response.get("content")
    if not isinstance(blocks, list):
        raise _AnthropicMalformedResponse()
    parts = []
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
    content = "\n".join(parts).strip()
    if not content:
        raise _AnthropicMalformedResponse()
    return content


def _anthropic_usage(response: dict[str, object]) -> tuple[int | None, int | None]:
    usage = response.get("usage")
    if usage is None:
        return None, None
    if not isinstance(usage, dict):
        raise _AnthropicMalformedResponse()
    return _optional_nonnegative_int(usage.get("input_tokens")), _optional_nonnegative_int(
        usage.get("output_tokens")
    )


def _optional_nonnegative_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _AnthropicMalformedResponse()
    return value


def _anthropic_http_outcome(status_code: int) -> tuple[str, str, str]:
    if status_code in {401, 403}:
        return (
            AI_STATUS_PROVIDER_AUTHENTICATION_ERROR,
            "Anthropic provider authentication failed.",
            AI_STATUS_PROVIDER_AUTHENTICATION_ERROR,
        )
    if status_code == 429:
        return (
            AI_STATUS_PROVIDER_RATE_LIMITED,
            "Anthropic provider rate limit was reached.",
            AI_STATUS_PROVIDER_RATE_LIMITED,
        )
    if status_code in {408, 504}:
        return (
            AI_STATUS_PROVIDER_TIMEOUT,
            "Anthropic provider timed out.",
            AI_STATUS_PROVIDER_TIMEOUT,
        )
    if status_code >= 500:
        return (
            AI_STATUS_PROVIDER_UNAVAILABLE,
            "Anthropic provider is unavailable.",
            AI_STATUS_PROVIDER_UNAVAILABLE,
        )
    return (
        AI_STATUS_FAILED,
        "Anthropic provider rejected the request.",
        "provider_request_rejected",
    )


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
    provider_prompt_tokens: int | None = None,
    provider_completion_tokens: int | None = None,
    content: str | None = None,
    error: str | None = None,
    error_code: str | None = None,
    local_request: bool = False,
    paid_request: bool = False,
    profile=None,
) -> AiGatewayResponse:
    metadata = AiRequestMetadata(
        provider=provider,
        model=model,
        mode=mode,
        status=status,
        latency_ms=max(0, int((time.monotonic() - started) * 1000)),
        estimated_prompt_tokens=prompt_tokens,
        estimated_completion_tokens=completion_tokens,
        provider_reported_prompt_tokens=provider_prompt_tokens,
        provider_reported_completion_tokens=provider_completion_tokens,
        provider_reported_total_tokens=(
            provider_prompt_tokens + provider_completion_tokens
            if provider_prompt_tokens is not None and provider_completion_tokens is not None
            else None
        ),
        token_usage_source=(
            "provider_reported"
            if provider_prompt_tokens is not None or provider_completion_tokens is not None
            else "estimated"
        ),
        estimated_cost_usd=0 if local_request else None,
        actual_billed_cost_usd=None,
        cost_source="estimated" if local_request else None,
        local_request=local_request,
        paid_request=paid_request,
        error_code=error_code,
        profile=profile.name if profile else None,
        task_category=profile.task_category if profile else None,
        timeout_seconds=profile.timeout_seconds if profile else None,
        max_output_tokens=profile.max_output_tokens if profile else None,
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
