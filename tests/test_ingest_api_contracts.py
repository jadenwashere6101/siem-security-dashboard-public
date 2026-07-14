import pytest
from unittest.mock import MagicMock


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


def _valid_ingest_payload():
    return {
        "event_type": "failed_login",
        "severity": "medium",
        "source_ip": "203.0.113.20",
        "message": "Failed login attempt",
        "app_name": "auth-service",
        "environment": "prod",
        "location": {"country": "US", "city": "New York", "lat": 40.7, "lon": -74.0},
    }


def test_ingest_schedules_playbooks_before_queue_precedence_work(client, monkeypatch):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)
    import routes.ingest_routes as ingest_routes

    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    commit_events = []
    conn.commit.side_effect = lambda: commit_events.append("commit")
    alerts_created = [
        {
            "alert_id": 123,
            "source_ip": "203.0.113.20",
            "severity": "HIGH",
            "response_action": "monitor",
        }
    ]
    playbook_call_commit_count = []

    def fake_playbook_orchestration(alerts, db_conn):
        playbook_call_commit_count.append(len(commit_events))
        assert alerts == alerts_created
        assert db_conn is conn
        return {"summary": {"created": 1}, "results": []}

    monkeypatch.setattr(ingest_routes, "get_db_connection", lambda: conn)
    monkeypatch.setattr(ingest_routes, "ingest_normalized_event", lambda *_args, **_kwargs: alerts_created)
    monkeypatch.setattr(ingest_routes, "enqueue_committed_alerts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(ingest_routes, "_create_incidents_for_alerts", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ingest_routes, "notify_for_alert", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        ingest_routes,
        "create_pending_executions_for_committed_alerts",
        fake_playbook_orchestration,
    )

    resp = client.post(
        "/ingest",
        json=_valid_ingest_payload(),
        headers={"X-API-Key": VALID_API_KEY},
    )

    assert resp.status_code == 201
    assert resp.get_json() == {
        "message": "Event added successfully",
        "alerts_created": alerts_created,
    }
    assert playbook_call_commit_count == [1]
    assert conn.commit.call_count == 6
    conn.rollback.assert_not_called()


def test_ingest_playbook_scheduling_failure_does_not_fail_response(client, monkeypatch):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)
    import routes.ingest_routes as ingest_routes

    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    alerts_created = [{"alert_id": 123, "source_ip": "203.0.113.20", "severity": "HIGH"}]

    monkeypatch.setattr(ingest_routes, "get_db_connection", lambda: conn)
    monkeypatch.setattr(ingest_routes, "ingest_normalized_event", lambda *_args, **_kwargs: alerts_created)
    monkeypatch.setattr(ingest_routes, "enqueue_committed_alerts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(ingest_routes, "_create_incidents_for_alerts", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ingest_routes, "notify_for_alert", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        ingest_routes,
        "create_pending_executions_for_committed_alerts",
        MagicMock(side_effect=RuntimeError("playbook failure")),
    )

    resp = client.post(
        "/ingest",
        json=_valid_ingest_payload(),
        headers={"X-API-Key": VALID_API_KEY},
    )

    assert resp.status_code == 201
    assert resp.get_json()["alerts_created"] == alerts_created
    conn.rollback.assert_called_once()
