from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core import internet_noise


def test_cache_hit_returns_cached_assessment(monkeypatch):
    internet_noise.reset_internet_noise_state_for_tests()
    now = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(internet_noise, "_utcnow", lambda: now)
    monkeypatch.setenv("SIEM_GREYNOISE_API_KEY", "test-key")

    internet_noise._CACHE["198.51.100.10"] = {
        "assessment": internet_noise.build_internet_noise_assessment(
            assessment="commodity",
            explanation="Known commodity internet scanner.",
            lookup_status="succeeded",
            last_checked=now.isoformat(),
        ),
        "expires_at": now + timedelta(hours=1),
    }

    result = internet_noise.get_internet_noise_assessment("198.51.100.10", allow_enqueue=False)

    assert result["assessment"] == "commodity"
    assert result["cached"] is True
    assert internet_noise.get_internet_noise_metrics()["cache_hits"] == 1


def test_expired_cache_returns_neutral(monkeypatch):
    internet_noise.reset_internet_noise_state_for_tests()
    now = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(internet_noise, "_utcnow", lambda: now)
    monkeypatch.setenv("SIEM_GREYNOISE_API_KEY", "test-key")
    internet_noise._CACHE["198.51.100.11"] = {
        "assessment": internet_noise.build_internet_noise_assessment(
            assessment="commodity",
            explanation="Known commodity internet scanner.",
        ),
        "expires_at": now - timedelta(seconds=1),
    }

    result = internet_noise.get_internet_noise_assessment("198.51.100.11", allow_enqueue=False)

    assert result["assessment"] == "neutral"
    assert result["lookup_status"] == "stale"
    assert result["provider_metadata"]["stale_assessment"] == "commodity"


def test_provider_timeout_is_neutral(monkeypatch):
    internet_noise.reset_internet_noise_state_for_tests()
    monkeypatch.setenv("SIEM_GREYNOISE_API_KEY", "test-key")

    def fake_get(*_args, **_kwargs):
        raise internet_noise.requests.Timeout("timeout")

    monkeypatch.setattr(internet_noise.requests, "get", fake_get)
    monkeypatch.setattr(internet_noise.time, "sleep", lambda *_args, **_kwargs: None)

    result = internet_noise.refresh_internet_noise_assessment("198.51.100.12")

    assert result["assessment"] == "neutral"
    assert result["lookup_status"] == "failed"


def test_retry_backoff_retries_transient_failures(monkeypatch):
    internet_noise.reset_internet_noise_state_for_tests()
    monkeypatch.setenv("SIEM_GREYNOISE_API_KEY", "test-key")
    sleeps = []
    statuses = [429, 500, 200]

    class _Response:
        def __init__(self, status_code):
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise internet_noise.requests.HTTPError(f"status={self.status_code}")

        def json(self):
            return {"classification": "benign", "noise": True, "name": "scanner"}

    def fake_get(*_args, **_kwargs):
        return _Response(statuses.pop(0))

    monkeypatch.setattr(internet_noise.requests, "get", fake_get)
    monkeypatch.setattr(internet_noise.time, "sleep", lambda value: sleeps.append(value))

    result = internet_noise.refresh_internet_noise_assessment("198.51.100.13")

    assert result["assessment"] == "commodity"
    assert sleeps == [0.2, 0.4]


def test_missing_provider_key_is_neutral_and_cached(monkeypatch):
    internet_noise.reset_internet_noise_state_for_tests()
    monkeypatch.delenv("SIEM_GREYNOISE_API_KEY", raising=False)
    monkeypatch.delenv("GREYNOISE_API_KEY", raising=False)

    result = internet_noise.get_internet_noise_assessment("198.51.100.14", allow_enqueue=False)

    assert result["assessment"] == "neutral"
    assert result["lookup_status"] == "provider_unavailable"


def test_shadow_mode_is_the_default(monkeypatch):
    monkeypatch.delenv("INTERNET_NOISE_POLICY_MODE", raising=False)

    decision = internet_noise.build_internet_noise_decision(
        internet_noise.build_internet_noise_assessment(
            assessment="commodity",
            explanation="Known commodity internet scanner.",
            lookup_status="succeeded",
        ),
        override_reasons=[],
    )

    assert decision["policy_mode"] == "shadow"
    assert decision["effect"] == "shadow_observation"
    assert decision["would_reduce_urgency"] is True
    assert decision["applied_to_investigation"] is False
    assert decision["applied_to_incident"] is False
