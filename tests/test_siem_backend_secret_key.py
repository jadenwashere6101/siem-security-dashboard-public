import pytest

import siem_backend


def test_resolve_secret_key_uses_configured_secret(monkeypatch):
    monkeypatch.setattr(siem_backend, "SIEM_DEBUG", False)
    monkeypatch.setenv("SIEM_SECRET_KEY", "configured-test-secret")
    monkeypatch.delenv("SECRET_KEY", raising=False)

    assert siem_backend.resolve_secret_key() == "configured-test-secret"


def test_resolve_secret_key_requires_secret_outside_debug(monkeypatch):
    monkeypatch.setattr(siem_backend, "SIEM_DEBUG", False)
    monkeypatch.delenv("SIEM_SECRET_KEY", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="Missing SIEM_SECRET_KEY or SECRET_KEY"):
        siem_backend.resolve_secret_key()


def test_resolve_secret_key_generates_debug_only_fallback(monkeypatch):
    monkeypatch.setattr(siem_backend, "SIEM_DEBUG", True)
    monkeypatch.delenv("SIEM_SECRET_KEY", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)

    fallback = siem_backend.resolve_secret_key()

    assert isinstance(fallback, str)
    assert len(fallback) >= 32
