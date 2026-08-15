from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from core.source_health import aggregate_source_health
from core.source_ingestion_health_state import record_persisted_push_event
from scripts.backfill_source_ingestion_health_state import (
    initialize_backfill,
    inspect_backfill,
    process_backfill_batch,
    run_backfill,
)


NOW = datetime(2026, 8, 15, 16, 0, tzinfo=timezone.utc)


def _insert_event(cur, *, source, created_at, raw_payload=None):
    cur.execute(
        """
        INSERT INTO events (
            event_type, severity, source_ip, source, source_type,
            message, app_name, environment, raw_payload, created_at
        )
        VALUES (
            'normal_activity', 'low', '9.9.9.9', %s, 'test',
            'backfill fixture', 'backfill_test', 'test', %s::jsonb, %s
        )
        RETURNING id
        """,
        (source, json.dumps(raw_payload or {}), created_at),
    )
    return cur.fetchone()[0]


def _entry(snapshot, source):
    return next(item for item in snapshot["sources"] if item["source"] == source)


def test_backfill_is_bounded_resumable_and_idempotent(postgres_db):
    conn, cur = postgres_db
    _insert_event(cur, source="pfsense", created_at=NOW - timedelta(hours=2))
    _insert_event(
        cur,
        source="pfsense",
        created_at=NOW - timedelta(minutes=1),
        raw_payload={"data_provenance": "synthetic"},
    )
    _insert_event(cur, source="azure_insights", created_at=NOW - timedelta(minutes=1))
    conn.commit()

    initialized = initialize_backfill(conn)
    high_water = initialized["sources"][0]["backfill_high_water_event_id"]
    assert high_water == 3
    assert all(not item["historical_backfill_complete"] for item in initialized["sources"])

    first = process_backfill_batch(conn, batch_size=1)
    assert first == {
        "completed": False,
        "batch_start_event_id": 0,
        "batch_end_event_id": 1,
        "events_examined": 1,
    }
    resumed = run_backfill(conn, batch_size=1)
    assert resumed["completed"] is True
    assert resumed["batches_processed"] == 2
    assert all(
        item["backfill_last_processed_event_id"] == high_water
        and item["historical_backfill_complete"]
        for item in resumed["state"]["sources"]
    )

    repeated = run_backfill(conn, batch_size=1)
    assert repeated["completed"] is True
    assert repeated["batches_processed"] == 1
    assert repeated["events_examined"] == 0

    pfsense = _entry(aggregate_source_health(conn, generated_at=NOW), "pfsense")
    assert pfsense["latest_ingestion_at"] == (NOW - timedelta(hours=2)).isoformat()
    assert pfsense["last_event_at"] == (NOW - timedelta(minutes=1)).isoformat()
    assert pfsense["health_status"] == "degraded"


def test_live_ingestion_during_backfill_cannot_be_overwritten(postgres_db):
    conn, cur = postgres_db
    _insert_event(cur, source="nginx", created_at=NOW - timedelta(days=2))
    conn.commit()
    initialize_backfill(conn)

    live_timestamp = NOW - timedelta(minutes=2)
    record_persisted_push_event(
        cur,
        source="nginx",
        ingested_at=live_timestamp,
        raw_payload={},
    )
    conn.commit()

    result = run_backfill(conn, batch_size=10)
    assert result["completed"] is True
    state = next(item for item in inspect_backfill(conn)["sources"] if item["source"] == "nginx")
    assert state["latest_event_at"] == live_timestamp.isoformat()
    assert state["latest_qualifying_real_ingestion_at"] == live_timestamp.isoformat()


def test_empty_completed_backfill_establishes_never_seen_unknown(postgres_db):
    conn, _cur = postgres_db
    result = run_backfill(conn, batch_size=10)
    assert result["completed"] is True
    assert all(item["backfill_high_water_event_id"] == 0 for item in result["state"]["sources"])

    pfsense = _entry(aggregate_source_health(conn, generated_at=NOW), "pfsense")
    assert pfsense["historical_backfill_complete"] is True
    assert pfsense["health_status"] == "unknown"
    assert pfsense["health_reason"] == "no_qualifying_ingestion"
