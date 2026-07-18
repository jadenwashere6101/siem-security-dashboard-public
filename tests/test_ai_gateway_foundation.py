from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from core.ai.config import (
    AI_MODE_ASK_BEFORE_PAID_FALLBACK,
    AI_MODE_AUTOMATIC_FALLBACK,
    AI_MODE_DISABLED,
    AI_MODE_LOCAL_ONLY,
    DEFAULT_LOCAL_TIMEOUT_SECONDS,
    DEFAULT_MAX_PROMPT_CHARS,
    DEFAULT_PAID_TIMEOUT_SECONDS,
    AiGatewayConfig,
    load_ai_gateway_config,
)
from core.ai.gateway import AiGateway
from core.ai.models import (
    AI_STATUS_DISABLED,
    AI_STATUS_FALLBACK_BLOCKED,
    AI_STATUS_FALLBACK_REQUIRES_CONFIRMATION,
    AI_STATUS_PROVIDER_INCAPABLE,
    AI_STATUS_PROVIDER_TIMEOUT,
    AI_STATUS_PROVIDER_UNAVAILABLE,
    AI_STATUS_SUCCESS,
    AiCapabilityResult,
    AiGatewayRequest,
    AiGatewayResponse,
    AiProviderReadiness,
    AiRequestMetadata,
)
from core.ai.providers import DisabledAiProvider, OllamaProvider, PlaceholderPaidProvider
from core.ai.readiness import get_ai_gateway_status

ADMIN_USER = "testadmin"
ADMIN_PASS = "testpassword123!"


class FakeProvider:
    def __init__(
        self,
        provider_key: str,
        *,
        response_status: str = AI_STATUS_SUCCESS,
        capable: bool = True,
        error_code: str | None = None,
        local_request: bool = False,
        paid_request: bool = False,
    ):
        self.provider_key = provider_key
        self.response_status = response_status
        self.capable = capable
        self.error_code = error_code or response_status
        self.local_request = local_request
        self.paid_request = paid_request
        self.generate_calls = 0

    def supports(self, request: AiGatewayRequest) -> AiCapabilityResult:
        if not self.capable:
            return AiCapabilityResult(
                False,
                AI_STATUS_PROVIDER_INCAPABLE,
                "provider is incapable",
            )
        return AiCapabilityResult(True, AI_STATUS_SUCCESS)

    def readiness(self, config: AiGatewayConfig) -> AiProviderReadiness:
        return AiProviderReadiness(
            provider=self.provider_key,
            configured=True,
            ready=self.response_status == AI_STATUS_SUCCESS,
            status=self.response_status,
            model=config.local_model if self.local_request else config.paid_model,
        )

    def generate(self, request: AiGatewayRequest, config: AiGatewayConfig) -> AiGatewayResponse:
        self.generate_calls += 1
        return AiGatewayResponse(
            status=self.response_status,
            content="fake response" if self.response_status == AI_STATUS_SUCCESS else None,
            error=None if self.response_status == AI_STATUS_SUCCESS else "provider failed",
            metadata=AiRequestMetadata(
                provider=self.provider_key,
                model=config.local_model if self.local_request else config.paid_model,
                mode=config.mode,
                status=self.response_status,
                latency_ms=1,
                estimated_prompt_tokens=1,
                estimated_completion_tokens=2 if self.response_status == AI_STATUS_SUCCESS else 0,
                estimated_cost_usd=0 if self.local_request else None,
                local_request=self.local_request,
                paid_request=self.paid_request,
                error_code=None if self.response_status == AI_STATUS_SUCCESS else self.error_code,
            ),
        )


def _config(**overrides) -> AiGatewayConfig:
    base = AiGatewayConfig(
        mode=AI_MODE_LOCAL_ONLY,
        configured_mode=AI_MODE_LOCAL_ONLY,
        local_provider="local",
        local_base_url="http://127.0.0.1:11434",
        local_model="llama3",
        paid_provider="paid",
        paid_model="premium-model",
    )
    return replace(base, **overrides)


def _login_super_admin(client):
    resp = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert resp.status_code == 200


def _fake_user(username: str, password: str, role: str):
    return {
        "username": username,
        "password_hash": generate_password_hash(password, method="pbkdf2:sha256"),
        "role": role,
        "is_active": True,
    }


def _login_role(client, *, username: str, password: str, role: str):
    user = _fake_user(username, password, role)
    patchers = [
        patch("routes.auth_routes.get_user_by_username", return_value=user),
        patch("core.auth.get_user_by_username", return_value=user),
    ]
    for patcher in patchers:
        patcher.start()
    resp = client.post("/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return patchers


def _stop_patchers(patchers):
    for patcher in reversed(patchers):
        patcher.stop()


def test_ai_config_defaults_to_disabled_and_paid_optional(monkeypatch):
    for env_name in [
        "AI_GATEWAY_MODE",
        "AI_LOCAL_PROVIDER",
        "AI_LOCAL_BASE_URL",
        "AI_LOCAL_MODEL",
        "AI_LOCAL_TIMEOUT_SECONDS",
        "AI_PAID_PROVIDER",
        "AI_PAID_MODEL",
        "AI_PAID_TIMEOUT_SECONDS",
        "AI_PAID_FALLBACK_ENABLED",
        "AI_MAX_PROMPT_CHARS",
        "OPENAI_API_KEY",
    ]:
        monkeypatch.delenv(env_name, raising=False)

    config = load_ai_gateway_config()

    assert config.mode == AI_MODE_DISABLED
    assert config.local_provider == "ollama"
    assert config.paid_configured is False
    assert config.paid_fallback_enabled is False


def test_ai_config_invalid_values_fail_closed_with_safe_defaults(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_MODE", "always_on")
    monkeypatch.setenv("AI_LOCAL_TIMEOUT_SECONDS", "-1")
    monkeypatch.setenv("AI_PAID_TIMEOUT_SECONDS", "not-a-number")
    monkeypatch.setenv("AI_MAX_PROMPT_CHARS", "0")
    monkeypatch.setenv("AI_LOCAL_BASE_URL", "https://user:secret@example.test")

    config = load_ai_gateway_config()
    sanitized = config.sanitized()

    assert config.mode == AI_MODE_DISABLED
    assert config.configured_mode == "always_on"
    assert config.mode_valid is False
    assert config.local_timeout_seconds == DEFAULT_LOCAL_TIMEOUT_SECONDS
    assert config.paid_timeout_seconds == DEFAULT_PAID_TIMEOUT_SECONDS
    assert config.max_prompt_chars == DEFAULT_MAX_PROMPT_CHARS
    assert "secret" not in str(sanitized)
    assert "user:secret@example.test" not in str(sanitized)


def test_ollama_readiness_reports_missing_config_without_secrets():
    config = AiGatewayConfig(
        mode=AI_MODE_LOCAL_ONLY,
        configured_mode=AI_MODE_LOCAL_ONLY,
        local_base_url="https://user:secret@example.test",
        local_model="",
    )

    readiness = OllamaProvider().readiness(config).as_dict()

    assert readiness["ready"] is False
    assert readiness["status"] == AI_STATUS_PROVIDER_UNAVAILABLE
    assert "AI_LOCAL_MODEL" in readiness["missing_env_vars"]
    assert "secret" not in str(readiness)
    assert "user:secret@example.test" not in str(readiness)


def test_ollama_readiness_classifies_timeout(monkeypatch):
    monkeypatch.setattr("core.ai.providers._http_json", lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError()))

    readiness = OllamaProvider().readiness(
        AiGatewayConfig(
            mode=AI_MODE_LOCAL_ONLY,
            configured_mode=AI_MODE_LOCAL_ONLY,
            local_base_url="http://127.0.0.1:11434",
            local_model="llama3",
        )
    )

    assert readiness.status == AI_STATUS_PROVIDER_TIMEOUT
    assert readiness.ready is False


def test_paid_readiness_reports_env_names_not_secret_values(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")

    readiness = PlaceholderPaidProvider().readiness(
        AiGatewayConfig(
            mode=AI_MODE_AUTOMATIC_FALLBACK,
            configured_mode=AI_MODE_AUTOMATIC_FALLBACK,
            paid_provider="openai",
            paid_model="gpt-test",
        )
    ).as_dict()

    assert readiness["credential_env_vars"] == ["OPENAI_API_KEY"]
    assert readiness["credential_configured"] == {"OPENAI_API_KEY": True}
    assert "sk-secret-value" not in str(readiness)


def test_gateway_disabled_does_not_contact_providers():
    local = FakeProvider("local", local_request=True)
    paid = FakeProvider("paid", paid_request=True)
    gateway = AiGateway(
        config=_config(mode=AI_MODE_DISABLED, configured_mode=AI_MODE_DISABLED),
        providers={"local": local, "paid": paid},
    )

    response = gateway.generate(AiGatewayRequest(prompt="explain"))

    assert response.status == AI_STATUS_DISABLED
    assert local.generate_calls == 0
    assert paid.generate_calls == 0
    assert response.metadata.read_only is True


def test_gateway_uses_local_first_success_without_paid_fallback():
    local = FakeProvider("local", local_request=True)
    paid = FakeProvider("paid", paid_request=True)
    gateway = AiGateway(config=_config(), providers={"local": local, "paid": paid})

    response = gateway.generate(AiGatewayRequest(prompt="explain"))

    assert response.status == AI_STATUS_SUCCESS
    assert local.generate_calls == 1
    assert paid.generate_calls == 0
    assert response.metadata.local_request is True
    assert response.metadata.paid_request is False
    assert response.metadata.estimated_cost_usd == 0


def test_gateway_local_only_never_calls_paid_when_local_fails():
    local = FakeProvider(
        "local",
        response_status=AI_STATUS_PROVIDER_TIMEOUT,
        local_request=True,
    )
    paid = FakeProvider("paid", paid_request=True)
    gateway = AiGateway(config=_config(), providers={"local": local, "paid": paid})

    response = gateway.generate(AiGatewayRequest(prompt="explain"))

    assert response.status == AI_STATUS_PROVIDER_TIMEOUT
    assert local.generate_calls == 1
    assert paid.generate_calls == 0
    assert response.metadata.fallback_attempted is False


def test_gateway_ask_before_fallback_never_calls_paid_provider():
    local = FakeProvider(
        "local",
        response_status=AI_STATUS_PROVIDER_UNAVAILABLE,
        local_request=True,
    )
    paid = FakeProvider("paid", paid_request=True)
    gateway = AiGateway(
        config=_config(
            mode=AI_MODE_ASK_BEFORE_PAID_FALLBACK,
            configured_mode=AI_MODE_ASK_BEFORE_PAID_FALLBACK,
        ),
        providers={"local": local, "paid": paid},
    )

    response = gateway.generate(AiGatewayRequest(prompt="explain"))

    assert response.status == AI_STATUS_FALLBACK_REQUIRES_CONFIRMATION
    assert local.generate_calls == 1
    assert paid.generate_calls == 0
    assert response.metadata.fallback_attempted is True
    assert response.metadata.paid_request is False


def test_gateway_automatic_fallback_blocked_without_explicit_enablement():
    local = FakeProvider(
        "local",
        response_status=AI_STATUS_PROVIDER_UNAVAILABLE,
        local_request=True,
    )
    paid = FakeProvider("paid", paid_request=True)
    gateway = AiGateway(
        config=_config(
            mode=AI_MODE_AUTOMATIC_FALLBACK,
            configured_mode=AI_MODE_AUTOMATIC_FALLBACK,
            paid_fallback_enabled=False,
        ),
        providers={"local": local, "paid": paid},
    )

    response = gateway.generate(AiGatewayRequest(prompt="explain"))

    assert response.status == AI_STATUS_FALLBACK_BLOCKED
    assert paid.generate_calls == 0


def test_gateway_automatic_fallback_calls_paid_only_when_allowed():
    local = FakeProvider(
        "local",
        response_status=AI_STATUS_PROVIDER_UNAVAILABLE,
        local_request=True,
    )
    paid = FakeProvider("paid", paid_request=True)
    gateway = AiGateway(
        config=_config(
            mode=AI_MODE_AUTOMATIC_FALLBACK,
            configured_mode=AI_MODE_AUTOMATIC_FALLBACK,
            paid_fallback_enabled=True,
        ),
        providers={"local": local, "paid": paid},
    )

    response = gateway.generate(AiGatewayRequest(prompt="explain"))

    assert response.status == AI_STATUS_SUCCESS
    assert local.generate_calls == 1
    assert paid.generate_calls == 1
    assert response.metadata.fallback_attempted is True
    assert response.metadata.paid_request is True


def test_gateway_applies_capability_check_before_provider_use():
    local = FakeProvider("local", capable=False, local_request=True)
    paid = FakeProvider("paid", paid_request=True)
    gateway = AiGateway(config=_config(), providers={"local": local, "paid": paid})

    response = gateway.generate(AiGatewayRequest(prompt="explain", capability="tool_use"))

    assert response.status == AI_STATUS_PROVIDER_INCAPABLE
    assert local.generate_calls == 0
    assert paid.generate_calls == 0


def test_gateway_does_not_touch_database_or_shell(monkeypatch):
    local = FakeProvider("local", local_request=True)
    gateway = AiGateway(config=_config(), providers={"local": local})

    monkeypatch.setattr(
        "core.db.get_db_connection",
        lambda: (_ for _ in ()).throw(AssertionError("database access attempted")),
    )
    monkeypatch.setattr(
        "subprocess.run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("shell access attempted")),
    )

    response = gateway.generate(AiGatewayRequest(prompt="explain"))

    assert response.status == AI_STATUS_SUCCESS


def test_ai_status_payload_is_sanitized_and_read_only(monkeypatch):
    monkeypatch.setattr("core.ai.providers._http_json", lambda *_args, **_kwargs: {"models": []})
    monkeypatch.setenv("AI_GATEWAY_MODE", AI_MODE_LOCAL_ONLY)
    monkeypatch.setenv("AI_LOCAL_BASE_URL", "https://user:secret@example.test")
    monkeypatch.setenv("AI_LOCAL_MODEL", "llama3")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")

    status = get_ai_gateway_status()

    assert status["read_only"] is True
    assert status["on_demand_only"] is True
    assert status["gateway"]["local_base_url_configured"] is True
    assert "secret" not in str(status)
    assert "sk-secret-value" not in str(status)
    assert "user:secret@example.test" not in str(status)


def test_ai_status_route_requires_session(client):
    resp = client.get("/ai/status")

    assert resp.status_code == 401


def test_ai_status_route_rejects_viewer(client, mock_db):
    patchers = _login_role(client, username="ai_viewer", password="p", role="viewer")
    try:
        resp = client.get("/ai/status")
    finally:
        _stop_patchers(patchers)

    assert resp.status_code == 403


def test_ai_status_route_allows_analyst_and_sanitizes(client, mock_db, monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_MODE", AI_MODE_DISABLED)
    monkeypatch.setenv("AI_LOCAL_BASE_URL", "https://user:secret@example.test")
    patchers = _login_role(client, username="ai_analyst", password="p", role="analyst")
    try:
        resp = client.get("/ai/status")
    finally:
        _stop_patchers(patchers)

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["read_only"] is True
    assert data["gateway"]["mode"] == AI_MODE_DISABLED
    assert "secret" not in str(data)


def test_ai_status_route_allows_super_admin_without_inference_or_paid_call(client, monkeypatch):
    monkeypatch.setattr("core.ai.providers._http_json", lambda *_args, **_kwargs: {"models": []})
    monkeypatch.setenv("AI_GATEWAY_MODE", AI_MODE_AUTOMATIC_FALLBACK)
    monkeypatch.setenv("AI_LOCAL_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.setenv("AI_LOCAL_MODEL", "llama3")
    monkeypatch.setenv("AI_PAID_PROVIDER", "openai")
    monkeypatch.setenv("AI_PAID_MODEL", "gpt-test")
    monkeypatch.setenv("AI_PAID_FALLBACK_ENABLED", "true")
    monkeypatch.setattr(
        "core.ai.providers.OllamaProvider.generate",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("inference attempted")),
    )
    monkeypatch.setattr(
        "core.ai.providers.PlaceholderPaidProvider.generate",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("paid call attempted")),
    )
    _login_super_admin(client)

    resp = client.get("/ai/status")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["gateway"]["paid_fallback_enabled"] is True
