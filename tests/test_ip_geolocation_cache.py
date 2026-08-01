from unittest.mock import MagicMock

from core import ip_helpers


class FakeGeoResponse:
    def __init__(self, payload=None, *, status_code=200, json_error=None):
        self.payload = payload
        self.status_code = status_code
        self.json_error = json_error

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload


def _configure_short_geo_windows(monkeypatch):
    ip_helpers.reset_geolocation_cache_state()
    monkeypatch.setattr(ip_helpers, "GEOLOCATION_NEGATIVE_CACHE_TTL_SECONDS", 1)
    monkeypatch.setattr(ip_helpers, "GEOLOCATION_PROVIDER_FAILURE_THRESHOLD", 2)
    monkeypatch.setattr(ip_helpers, "GEOLOCATION_PROVIDER_COOLDOWN_SECONDS", 30)
    monkeypatch.setattr(ip_helpers, "GEOLOCATION_FAILURE_LOG_THROTTLE_SECONDS", 60)


def test_lookup_ip_location_caches_successful_provider_response(monkeypatch):
    _configure_short_geo_windows(monkeypatch)
    provider_get = MagicMock(
        return_value=FakeGeoResponse(
            {
                "status": "success",
                "country": "United States",
                "city": "New York",
                "lat": 40.7128,
                "lon": -74.006,
            }
        )
    )
    monkeypatch.setattr(ip_helpers.requests, "get", provider_get)

    first = ip_helpers.lookup_ip_location("8.8.8.8")
    second = ip_helpers.lookup_ip_location("8.8.8.8")

    assert first == {
        "country": "United States",
        "city": "New York",
        "lat": 40.7128,
        "lon": -74.006,
    }
    assert second == first
    provider_get.assert_called_once()


def test_lookup_ip_location_negatively_caches_non_json_response(monkeypatch):
    _configure_short_geo_windows(monkeypatch)
    monkeypatch.setattr(ip_helpers.time, "monotonic", lambda: 1000.0)
    provider_get = MagicMock(return_value=FakeGeoResponse(json_error=ValueError("empty response")))
    log_failure = MagicMock()
    monkeypatch.setattr(ip_helpers.requests, "get", provider_get)
    monkeypatch.setattr(ip_helpers, "_log_geolocation_failure", log_failure)

    first = ip_helpers.lookup_ip_location("8.8.4.4")
    second = ip_helpers.lookup_ip_location("8.8.4.4")

    assert first == {"country": None, "city": None, "lat": None, "lon": None}
    assert second == first
    provider_get.assert_called_once()
    log_failure.assert_called_once()


def test_lookup_ip_location_circuit_breaker_skips_provider_until_cooldown_expires(monkeypatch):
    _configure_short_geo_windows(monkeypatch)
    current_time = {"value": 1000.0}
    monkeypatch.setattr(ip_helpers.time, "monotonic", lambda: current_time["value"])
    provider_get = MagicMock(
        side_effect=[
            FakeGeoResponse(status_code=503),
            FakeGeoResponse(json_error=ValueError("not json")),
            FakeGeoResponse(
                {
                    "status": "success",
                    "country": "United States",
                    "city": "Los Angeles",
                    "lat": 34.0522,
                    "lon": -118.2437,
                }
            ),
        ]
    )
    log_failure = MagicMock()
    monkeypatch.setattr(ip_helpers.requests, "get", provider_get)
    monkeypatch.setattr(ip_helpers, "_log_geolocation_failure", log_failure)

    assert ip_helpers.lookup_ip_location("8.8.4.10") == {"country": None, "city": None, "lat": None, "lon": None}
    assert ip_helpers.lookup_ip_location("8.8.4.11") == {"country": None, "city": None, "lat": None, "lon": None}
    assert ip_helpers.lookup_ip_location("8.8.4.12") == {"country": None, "city": None, "lat": None, "lon": None}
    assert provider_get.call_count == 2
    assert log_failure.call_count == 1

    current_time["value"] = 1031.0
    recovered = ip_helpers.lookup_ip_location("8.8.4.12")

    assert recovered == {
        "country": "United States",
        "city": "Los Angeles",
        "lat": 34.0522,
        "lon": -118.2437,
    }
    assert provider_get.call_count == 3
