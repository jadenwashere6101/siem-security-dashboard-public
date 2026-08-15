from __future__ import annotations

from datetime import datetime

from core.source_inventory import CANONICAL_PUSH_SOURCE_IDS
from core.synthetic_data_policy import is_synthetic_json_payload


SOURCE_INGESTION_HEALTH_STATE_UPSERT_SQL = """
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


def record_persisted_push_event(
    cur,
    *,
    source: str,
    ingested_at: datetime,
    raw_payload: object,
) -> bool:
    """Record committed-source candidates on the caller-owned transaction."""
    if source not in CANONICAL_PUSH_SOURCE_IDS:
        return False
    qualifying_at = None if is_synthetic_json_payload(raw_payload) else ingested_at
    cur.execute(
        SOURCE_INGESTION_HEALTH_STATE_UPSERT_SQL,
        (source, ingested_at, qualifying_at),
    )
    return True
