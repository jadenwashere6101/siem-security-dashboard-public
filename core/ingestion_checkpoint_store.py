from __future__ import annotations

from datetime import datetime

from psycopg2.extras import Json


def get_checkpoint(connector_name: str, conn) -> dict | None:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT connector_name, last_processed_at, last_poll_status, last_poll_counts, updated_at
            FROM ingestion_checkpoints
            WHERE connector_name = %s
            """,
            (connector_name,),
        )
        row = cur.fetchone()
    finally:
        cur.close()

    if row is None:
        return None

    return {
        "connector_name": row[0],
        "last_processed_at": row[1],
        "last_poll_status": row[2],
        "last_poll_counts": row[3] or {},
        "updated_at": row[4],
    }


def upsert_checkpoint(
    connector_name: str,
    conn,
    *,
    last_processed_at: datetime | None,
    poll_status: str | None,
    poll_counts: dict | None,
) -> dict:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO ingestion_checkpoints (
                connector_name,
                last_processed_at,
                last_poll_status,
                last_poll_counts,
                updated_at
            )
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (connector_name) DO UPDATE
            SET last_processed_at = EXCLUDED.last_processed_at,
                last_poll_status = EXCLUDED.last_poll_status,
                last_poll_counts = EXCLUDED.last_poll_counts,
                updated_at = NOW()
            RETURNING connector_name, last_processed_at, last_poll_status, last_poll_counts, updated_at
            """,
            (
                connector_name,
                last_processed_at,
                poll_status,
                Json(poll_counts or {}),
            ),
        )
        row = cur.fetchone()
    finally:
        cur.close()

    return {
        "connector_name": row[0],
        "last_processed_at": row[1],
        "last_poll_status": row[2],
        "last_poll_counts": row[3] or {},
        "updated_at": row[4],
    }
