from unittest.mock import MagicMock, patch


VALID_INGEST_API_KEY = "test-ingest-api-key"
VALID_AZURE_API_KEY = "test-azure-api-key"


def _build_ingest_payload():
    return {
        "event_type": "normal_activity",
        "severity": "low",
        "source_ip": "8.8.8.8",
        "message": "Normal traffic observed",
        "app_name": "auth-service",
        "environment": "prod",
    }


def _build_mock_connection(commit_side_effect=None):
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    if commit_side_effect is not None:
        conn.commit.side_effect = commit_side_effect
    return conn


def test_enqueue_called_after_first_commit(client, monkeypatch):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_INGEST_API_KEY)
    mock_conn = _build_mock_connection()
    commit_count_at_enqueue = {"value": 0}

    def enqueue_side_effect(_alerts_created, conn):
        commit_count_at_enqueue["value"] = conn.commit.call_count
        return []

    with patch("routes.ingest_routes.get_db_connection", return_value=mock_conn), patch(
        "routes.ingest_routes.ingest_normalized_event",
        return_value=[{"alert_id": 11, "source_ip": "8.8.8.8", "response_action": "monitor"}],
    ), patch(
        "routes.ingest_routes.enqueue_committed_alerts",
        side_effect=enqueue_side_effect,
    ) as enqueue_mock:
        resp = client.post(
            "/ingest",
            json=_build_ingest_payload(),
            headers={"X-API-Key": VALID_INGEST_API_KEY},
        )

    assert resp.status_code == 201
    enqueue_mock.assert_called_once()
    assert commit_count_at_enqueue["value"] >= 1


def test_enqueue_failure_after_commit_still_returns_201(client, monkeypatch):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_INGEST_API_KEY)
    mock_conn = _build_mock_connection()

    with patch("routes.ingest_routes.get_db_connection", return_value=mock_conn), patch(
        "routes.ingest_routes.ingest_normalized_event",
        return_value=[{"alert_id": 12, "source_ip": "1.1.1.1", "response_action": "monitor"}],
    ), patch(
        "routes.ingest_routes.enqueue_committed_alerts",
        side_effect=RuntimeError("queue unavailable"),
    ):
        resp = client.post(
            "/ingest",
            json=_build_ingest_payload(),
            headers={"X-API-Key": VALID_INGEST_API_KEY},
        )

    assert resp.status_code == 201
    body = resp.get_json()
    assert body["message"] == "Event added successfully"
    assert "error" not in body


def test_no_enqueue_when_pre_commit_ingest_fails(client, monkeypatch):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_INGEST_API_KEY)
    mock_conn = _build_mock_connection()

    with patch("routes.ingest_routes.get_db_connection", return_value=mock_conn), patch(
        "routes.ingest_routes.ingest_normalized_event",
        side_effect=RuntimeError("detection failed"),
    ), patch("routes.ingest_routes.enqueue_committed_alerts") as enqueue_mock:
        resp = client.post(
            "/ingest",
            json=_build_ingest_payload(),
            headers={"X-API-Key": VALID_INGEST_API_KEY},
        )

    assert resp.status_code == 500
    enqueue_mock.assert_not_called()


def test_enqueue_receives_empty_alerts_list(client, monkeypatch):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_INGEST_API_KEY)
    mock_conn = _build_mock_connection()

    with patch("routes.ingest_routes.get_db_connection", return_value=mock_conn), patch(
        "routes.ingest_routes.ingest_normalized_event",
        return_value=[],
    ), patch("routes.ingest_routes.enqueue_committed_alerts", return_value=[]) as enqueue_mock:
        resp = client.post(
            "/ingest",
            json=_build_ingest_payload(),
            headers={"X-API-Key": VALID_INGEST_API_KEY},
        )

    assert resp.status_code == 201
    enqueue_mock.assert_called_once()
    assert enqueue_mock.call_args[0][0] == []


def test_azure_batch_enqueue_called_once_with_full_alert_list(client, monkeypatch):
    monkeypatch.setenv("AZURE_INGEST_API_KEY", VALID_AZURE_API_KEY)
    mock_conn = _build_mock_connection()
    azure_payload = [{"eventName": "custom-1"}, {"eventName": "custom-2"}]
    normalized = {
        "event_type": "failed_login",
        "severity": "high",
        "source_ip": "5.6.7.8",
        "message": "Azure auth failure",
    }

    with patch("routes.ingest_routes.get_db_connection", return_value=mock_conn), patch(
        "routes.ingest_routes._is_azure_identity_payload", return_value=False
    ), patch(
        "routes.ingest_routes.normalize_azure_insights_telemetry",
        return_value=normalized,
    ), patch(
        "routes.ingest_routes._get_azure_app_name",
        return_value="azure-test-app",
    ), patch(
        "routes.ingest_routes.ingest_normalized_event",
        return_value=[{"alert_id": 21, "source_ip": "5.6.7.8", "response_action": "block_ip"}],
    ), patch("routes.ingest_routes.enqueue_committed_alerts", return_value=[]) as enqueue_mock:
        resp = client.post(
            "/ingest/azure",
            json=azure_payload,
            headers={"X-API-Key": VALID_AZURE_API_KEY},
        )

    assert resp.status_code == 201
    enqueue_mock.assert_called_once()
    assert len(enqueue_mock.call_args[0][0]) == 2


def test_second_commit_called_after_enqueue_success(client, monkeypatch):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_INGEST_API_KEY)
    mock_conn = _build_mock_connection()

    with patch("routes.ingest_routes.get_db_connection", return_value=mock_conn), patch(
        "routes.ingest_routes.ingest_normalized_event",
        return_value=[{"alert_id": 31, "source_ip": "9.9.9.9", "response_action": "monitor"}],
    ), patch("routes.ingest_routes.enqueue_committed_alerts", return_value=[]):
        resp = client.post(
            "/ingest",
            json=_build_ingest_payload(),
            headers={"X-API-Key": VALID_INGEST_API_KEY},
        )

    assert resp.status_code == 201
    assert mock_conn.commit.call_count >= 2


def test_second_commit_failure_still_returns_201(client, monkeypatch):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_INGEST_API_KEY)
    mock_conn = _build_mock_connection(commit_side_effect=[None, RuntimeError("commit failed")])

    with patch("routes.ingest_routes.get_db_connection", return_value=mock_conn), patch(
        "routes.ingest_routes.ingest_normalized_event",
        return_value=[{"alert_id": 41, "source_ip": "4.4.4.4", "response_action": "monitor"}],
    ), patch("routes.ingest_routes.enqueue_committed_alerts", return_value=[]):
        resp = client.post(
            "/ingest",
            json=_build_ingest_payload(),
            headers={"X-API-Key": VALID_INGEST_API_KEY},
        )

    assert resp.status_code == 201
