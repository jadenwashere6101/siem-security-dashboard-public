from __future__ import annotations

from datetime import datetime, timezone

import siem_backend

from core.source_health import aggregate_source_health
from scripts.initialize_source_event_totals import initialize_totals


NOW = datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc)


def _insert_event(cur, source):
    cur.execute(
        """
        INSERT INTO events (
            event_type, severity, source_ip, source, source_type,
            message, app_name, environment, raw_payload, created_at
        )
        VALUES (
            'normal_activity', 'low', '198.51.100.10', %s, 'test',
            'total fixture', 'source_total_test', 'test', '{}'::jsonb, %s
        )
        """,
        (source, NOW),
    )


def _state(payload, source):
    return next(item for item in payload["state"]["sources"] if item["source"] == source)


def _health(payload, source):
    return next(item for item in payload["sources"] if item["source"] == source)


def _normalized_event(source, source_type):
    return {
        "event_type": "normal_activity",
        "severity": "low",
        "source_ip": "198.51.100.11",
        "source": source,
        "source_type": source_type,
        "event_timestamp": None,
        "message": "post-initialization event",
        "app_name": "source_total_test",
        "environment": "test",
        "raw_payload": {},
    }


def test_one_time_initialization_counts_only_canonical_sources_and_is_idempotent(postgres_db):
    conn, cur = postgres_db
    for source in ("pfsense", "pfsense", "pfsense", "azure_insights", "otlp"):
        _insert_event(cur, source)
    conn.commit()

    result = initialize_totals(conn)

    assert result["initialized"] is True
    assert result["events_counted"] == 4
    assert _state(result, "pfsense")["total_events"] == 3
    assert _state(result, "azure_insights")["total_events"] == 1
    assert _state(result, "opentelemetry")["total_events"] == 0
    assert all(item["total_events_initialized"] for item in result["state"]["sources"])

    repeated = initialize_totals(conn)
    assert repeated["initialized"] is True
    assert repeated["events_counted"] == 0


def test_live_ingestion_increments_initialized_total_without_recounting_history(postgres_db):
    conn, cur = postgres_db
    _insert_event(cur, "pfsense")
    conn.commit()
    initialize_totals(conn)

    siem_backend.ingest_normalized_event(
        _normalized_event("pfsense", "firewall"),
        conn,
        cur,
    )
    conn.commit()

    cur.execute(
        "SELECT total_events FROM source_ingestion_health_state WHERE source = 'pfsense'"
    )
    assert cur.fetchone()[0] == 2


def test_rolled_back_ingestion_does_not_increment_initialized_total(postgres_db):
    conn, cur = postgres_db
    initialize_totals(conn)

    siem_backend.ingest_normalized_event(
        _normalized_event("pfsense", "firewall"),
        conn,
        cur,
    )
    conn.rollback()

    cur.execute(
        "SELECT total_events FROM source_ingestion_health_state WHERE source = 'pfsense'"
    )
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT COUNT(*) FROM events WHERE source = 'pfsense'")
    assert cur.fetchone()[0] == 0


def test_source_health_reads_multi_million_total_from_tiny_state_only(postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO source_ingestion_health_state (
            source, total_events, total_events_initialized
        )
        VALUES ('pfsense', 5930682, TRUE)
        """
    )
    conn.commit()

    response = aggregate_source_health(conn, generated_at=NOW)

    assert _health(response, "pfsense")["total_events"] == 5930682
    assert _health(response, "bank_app")["total_events"] is None


def test_uninitialized_total_is_unavailable_without_changing_health_semantics(postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO source_ingestion_health_state (
            source, total_events, total_events_initialized,
            historical_backfill_complete,
            backfill_high_water_event_id,
            backfill_last_processed_event_id
        )
        VALUES ('pfsense', 99, FALSE, TRUE, 0, 0)
        """
    )
    conn.commit()

    pfsense = _health(aggregate_source_health(conn, generated_at=NOW), "pfsense")

    assert pfsense["total_events"] is None
    assert pfsense["health_status"] == "unknown"
    assert pfsense["health_reason"] == "no_qualifying_ingestion"
