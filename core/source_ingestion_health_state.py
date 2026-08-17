from __future__ import annotations

from datetime import datetime

from core.source_inventory import CANONICAL_PUSH_SOURCE_IDS, CANONICAL_SOURCE_IDS
from core.synthetic_data_policy import is_synthetic_json_payload


SOURCE_INGESTION_STATE_UPSERT_SQL = """
    INSERT INTO source_ingestion_health_state (
        source,
        latest_event_at,
        latest_qualifying_real_ingestion_at,
        updated_at
    )
    VALUES (%s, %s, %s, NOW())
    ON CONFLICT (source) DO UPDATE
    SET latest_event_at = GREATEST(
            source_ingestion_health_state.latest_event_at,
            EXCLUDED.latest_event_at
        ),
        latest_qualifying_real_ingestion_at = GREATEST(
            source_ingestion_health_state.latest_qualifying_real_ingestion_at,
            EXCLUDED.latest_qualifying_real_ingestion_at
        ),
        updated_at = NOW()
"""

SOURCE_INGESTION_STATE_WITH_TOTAL_UPSERT_SQL = """
    INSERT INTO source_ingestion_health_state (
        source,
        latest_event_at,
        latest_qualifying_real_ingestion_at,
        total_events,
        updated_at
    )
    VALUES (%s, %s, %s, 0, NOW())
    ON CONFLICT (source) DO UPDATE
    SET latest_event_at = GREATEST(
            source_ingestion_health_state.latest_event_at,
            EXCLUDED.latest_event_at
        ),
        latest_qualifying_real_ingestion_at = GREATEST(
            source_ingestion_health_state.latest_qualifying_real_ingestion_at,
            EXCLUDED.latest_qualifying_real_ingestion_at
        ),
        total_events = source_ingestion_health_state.total_events + CASE
            WHEN source_ingestion_health_state.total_events_initialized THEN 1
            ELSE 0
        END,
        updated_at = NOW()
"""


def record_persisted_push_event(
    cur,
    *,
    source: str,
    ingested_at: datetime,
    raw_payload: object,
    increment_total: bool = True,
) -> bool:
    """Record committed-source candidates on the caller-owned transaction."""
    if source not in CANONICAL_SOURCE_IDS:
        return False
    is_push_source = source in CANONICAL_PUSH_SOURCE_IDS
    latest_event_at = ingested_at if is_push_source else None
    qualifying_at = (
        None
        if not is_push_source or is_synthetic_json_payload(raw_payload)
        else ingested_at
    )
    cur.execute(
        SOURCE_INGESTION_STATE_WITH_TOTAL_UPSERT_SQL
        if increment_total
        else SOURCE_INGESTION_STATE_UPSERT_SQL,
        (source, latest_event_at, qualifying_at),
    )
    return True
