import os
from unittest.mock import Mock

import pytest
from limits.errors import StorageError

import siem_backend
from core.rate_limit_config import (
    RateLimitStorageConfigError,
    apply_rate_limit_config,
    resolve_rate_limit_storage_config,
    sanitize_rate_limit_storage_uri,
    validate_rate_limit_storage_runtime,
)


def test_production_redis_storage_config_is_resolved_without_leaking_credentials():
    config = resolve_rate_limit_storage_config(
        {
            "SIEM_DEBUG": "false",
            "SIEM_RATE_LIMIT_STORAGE_URI": "redis://:secret-token@127.0.0.1:6379/0?ssl_cert_reqs=none",
        }
    )

    assert config.backend == "redis"
    assert config.host == "127.0.0.1"
    assert config.port == 6379
    assert config.database == "0"
    assert "secret-token" not in config.sanitized_summary
    assert "ssl_cert_reqs" not in config.sanitized_summary


def test_local_debug_uses_memory_when_storage_uri_is_unset():
    config = resolve_rate_limit_storage_config({"SIEM_DEBUG": "true"})

    assert config.storage_uri == "memory://"
    assert config.backend == "memory"
    assert config.production is False


@pytest.mark.parametrize(
    "uri, expected",
    [
        ("", "Missing SIEM_RATE_LIMIT_STORAGE_URI"),
        ("memory://", "cannot use memory"),
        ("memcached://127.0.0.1:11211", "redis:// or rediss://"),
        ("redis://10.0.0.25:6379/0", "loopback host"),
        ("redis://127.0.0.1:not-a-port/0", "invalid Redis port"),
    ],
)
def test_production_rejects_missing_memory_unsafe_scheme_public_host_and_bad_port(uri, expected):
    env = {"SIEM_DEBUG": "false"}
    if uri:
        env["SIEM_RATE_LIMIT_STORAGE_URI"] = uri

    with pytest.raises(RateLimitStorageConfigError, match=expected):
        resolve_rate_limit_storage_config(env)


def test_apply_rate_limit_config_sets_fail_closed_flask_limiter_options():
    app = Mock()
    app.config = {}

    config = apply_rate_limit_config(
        app,
        {
            "SIEM_DEBUG": "false",
            "SIEM_RATE_LIMIT_STORAGE_URI": "redis://127.0.0.1:6379/0",
        },
    )

    assert config.backend == "redis"
    assert app.config["RATELIMIT_STORAGE_URI"] == "redis://127.0.0.1:6379/0"
    assert app.config["RATELIMIT_SWALLOW_ERRORS"] is False
    assert app.config["RATELIMIT_IN_MEMORY_FALLBACK_ENABLED"] is False
    assert app.config["RATELIMIT_IN_MEMORY_FALLBACK"] == []
    assert app.config["RATELIMIT_STORAGE_OPTIONS"]["wrap_exceptions"] is True
    assert app.config["SIEM_RATE_LIMIT_STORAGE_SUMMARY"] == "backend=redis host=127.0.0.1 port=6379 db=0"


def test_sanitize_rate_limit_storage_uri_removes_credentials_and_query_string():
    sanitized = sanitize_rate_limit_storage_uri(
        "redis://user:super-secret@127.0.0.1:6379/0?token=secret"
    )

    assert sanitized == "redis://127.0.0.1:6379/0"
    assert "super-secret" not in sanitized
    assert "token" not in sanitized


def test_runtime_validation_without_ping_does_not_require_redis_client():
    config = validate_rate_limit_storage_runtime(
        {
            "SIEM_DEBUG": "false",
            "SIEM_RATE_LIMIT_STORAGE_URI": "redis://127.0.0.1:6379/0",
        },
        production=True,
        ping=False,
    )

    assert config.backend == "redis"


def test_app_uses_memory_storage_only_because_tests_run_in_debug_mode():
    assert siem_backend.app.config["RATELIMIT_STORAGE_URI"] == "memory://"
    assert siem_backend.app.config["RATELIMIT_IN_MEMORY_FALLBACK_ENABLED"] is False
    assert siem_backend.app.config["RATELIMIT_SWALLOW_ERRORS"] is False
    assert siem_backend.limiter._key_func.__name__ == "get_remote_address"


def test_login_rate_limit_preserves_existing_429_json(client, mock_db):
    siem_backend.limiter.enabled = True
    siem_backend.limiter.reset()
    try:
        response = None
        for index in range(6):
            response = client.post(
                "/login",
                json={"username": f"invalid-{index}", "password": "wrong"},
                environ_overrides={"REMOTE_ADDR": "203.0.113.10"},
            )

        assert response is not None
        assert response.status_code == 429
        assert response.get_json() == {
            "error": "rate_limited",
            "message": "Too many requests. Please try again later.",
        }
    finally:
        siem_backend.limiter.reset()
        siem_backend.limiter.enabled = False


def test_limiter_storage_error_fails_closed_without_leaking_credentials(client, monkeypatch):
    secret_uri = "redis://:leaked-password@127.0.0.1:6379/0"
    siem_backend.app.config["RATELIMIT_STORAGE_URI"] = secret_uri
    siem_backend.limiter.enabled = True
    siem_backend.limiter.reset()

    def raise_storage_error(*_args, **_kwargs):
        raise StorageError(RuntimeError(secret_uri))

    monkeypatch.setattr(siem_backend.limiter.storage, "incr", raise_storage_error)
    try:
        response = client.post(
            "/login",
            json={"username": "nobody", "password": "wrong"},
            environ_overrides={"REMOTE_ADDR": "203.0.113.11"},
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 503
        assert response.get_json() == {
            "error": "rate_limit_storage_unavailable",
            "message": "Rate limiting is temporarily unavailable. Please try again later.",
        }
        assert "leaked-password" not in body
        assert secret_uri not in body
    finally:
        siem_backend.app.config["RATELIMIT_STORAGE_URI"] = "memory://"
        siem_backend.limiter.reset()
        siem_backend.limiter.enabled = False


def test_unlimited_health_route_is_not_newly_throttled_when_storage_is_patched(client, monkeypatch):
    siem_backend.limiter.enabled = True
    siem_backend.limiter.reset()
    monkeypatch.setattr(
        siem_backend.limiter.storage,
        "incr",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(StorageError(RuntimeError("redis down"))),
    )
    try:
        response = client.get("/health")

        assert response.status_code == 200
        assert response.get_json()["status"] == "ok"
    finally:
        siem_backend.limiter.reset()
        siem_backend.limiter.enabled = False
