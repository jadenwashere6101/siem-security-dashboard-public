import pytest


VALID_API_KEY = "test-ingest-api-key"


@pytest.mark.parametrize(
    "endpoint",
    ["/ingest", "/ingest/web-log"],
)
def test_ingest_endpoints_without_api_key_return_401(client, endpoint):
    resp = client.post(endpoint, json={"event_type": "failed_login"})
    assert resp.status_code == 401
    data = resp.get_json()
    assert isinstance(data, dict)
    assert "error" in data


@pytest.mark.parametrize(
    "endpoint",
    ["/ingest/azure", "/ingest/otlp"],
)
def test_cloud_ingest_endpoints_without_api_key_return_401(client, endpoint):
    resp = client.post(endpoint, json={"event_type": "failed_login"})
    assert resp.status_code == 401
    data = resp.get_json()
    assert isinstance(data, dict)
    assert "error" in data


def test_ingest_with_valid_api_key_and_invalid_raw_json_returns_400(client, monkeypatch):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)

    resp = client.post(
        "/ingest",
        data="null",
        content_type="application/json",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Invalid JSON"


def test_ingest_with_valid_api_key_and_missing_required_fields_returns_400(client, monkeypatch):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)

    resp = client.post(
        "/ingest",
        json={"event_type": "failed_login"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert isinstance(data, dict)
    assert "error" in data


def test_ingest_with_valid_api_key_and_invalid_source_ip_returns_400(client, monkeypatch):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)

    resp = client.post(
        "/ingest",
        json={
            "event_type": "failed_login",
            "severity": "medium",
            "source_ip": "not-an-ip",
            "message": "Failed login attempt",
            "app_name": "auth-service",
            "environment": "prod",
        },
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Invalid source_ip"
