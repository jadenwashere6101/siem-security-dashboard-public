from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from core.ingestion_checkpoint_store import get_checkpoint, upsert_checkpoint


class _RouteSafeConnection:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return self._conn.cursor()

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return None


def test_checkpoint_store_round_trip(postgres_db):
    conn, _cur = postgres_db
    assert get_checkpoint("azure_insights", conn) is None

    saved = upsert_checkpoint(
        "azure_insights",
        conn,
        last_processed_at=datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc),
        poll_status="success",
        poll_counts={"returned": 5, "forwarded": 5, "failures": 0},
    )
    conn.commit()

    loaded = get_checkpoint("azure_insights", conn)
    assert loaded["connector_name"] == "azure_insights"
    assert loaded["last_processed_at"] == saved["last_processed_at"]
    assert loaded["last_poll_status"] == "success"
    assert loaded["last_poll_counts"] == {"returned": 5, "forwarded": 5, "failures": 0}


def test_checkpoint_routes_require_api_key_and_persist(client, postgres_db, monkeypatch):
    conn, _cur = postgres_db
    monkeypatch.setenv("AZURE_INGEST_API_KEY", "azure-key")

    with patch("routes.ingest_routes.get_db_connection", return_value=_RouteSafeConnection(conn)):
        unauthorized = client.get("/ingest/azure/checkpoint")
        assert unauthorized.status_code == 401

        response = client.get(
            "/ingest/azure/checkpoint",
            headers={"X-API-Key": "azure-key"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["connector_name"] == "azure_insights"
        assert data["last_processed_at"] is not None

        patch_response = client.patch(
            "/ingest/azure/checkpoint",
            json={
                "last_processed_at": "2026-07-14T12:10:00+00:00",
                "last_poll_status": "partial",
                "last_poll_counts": {"returned": 10, "forwarded": 9, "failures": 1},
            },
            headers={"X-API-Key": "azure-key"},
        )
        assert patch_response.status_code == 200
        payload = patch_response.get_json()
        assert payload["last_processed_at"] == "2026-07-14T12:10:00+00:00"
        assert payload["last_poll_status"] == "partial"
        assert payload["last_poll_counts"] == {"returned": 10, "forwarded": 9, "failures": 1}


def test_azure_ingest_duplicate_payload_is_ignored(postgres_db, client, monkeypatch):
    conn, _cur = postgres_db
    monkeypatch.setenv("AZURE_INGEST_API_KEY", "azure-key")
    telemetry = {
        "client_IP": "198.51.100.92",
        "baseType": "RequestData",
        "time": "2026-07-14T12:00:00+00:00",
        "cloud_RoleName": "orders-api",
        "data": {
            "baseData": {
                "name": "GET /api/orders",
                "message": "GET /api/orders",
                "responseCode": "401",
            }
        },
    }

    with patch("routes.ingest_routes.get_db_connection", return_value=_RouteSafeConnection(conn)):
        first = client.post(
            "/ingest/azure",
            json=telemetry,
            headers={"X-API-Key": "azure-key"},
        )
        second = client.post(
            "/ingest/azure",
            json=telemetry,
            headers={"X-API-Key": "azure-key"},
        )

    assert first.status_code == 201
    assert second.status_code == 201

    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM events WHERE source = 'azure_insights'")
        assert cur.fetchone()[0] == 1
    finally:
        cur.close()
