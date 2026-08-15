#!/usr/bin/env python3
"""Resumably initialize durable push-source ingestion health state.

Dry-run by default. Use --apply to capture a high-water mark and process
bounded primary-key ranges. Each committed batch is independently resumable.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.db import get_db_connection
from core.source_ingestion_health_state import record_persisted_push_event
from core.source_inventory import CANONICAL_PUSH_SOURCE_IDS
from core.synthetic_data_policy import build_synthetic_json_value_sql


DEFAULT_BATCH_SIZE = 1000
MAX_BATCH_SIZE = 10000
_PROVENANCE_SQL = build_synthetic_json_value_sql("raw_payload")


def _push_sources() -> tuple[str, ...]:
    return tuple(sorted(CANONICAL_PUSH_SOURCE_IDS))


def _load_locked_state(cur) -> list[tuple]:
    cur.execute(
        """
        SELECT source, historical_backfill_complete,
               backfill_high_water_event_id, backfill_last_processed_event_id
        FROM source_ingestion_health_state
        WHERE source = ANY(%s)
        ORDER BY source
        FOR UPDATE
        """,
        (list(_push_sources()),),
    )
    return cur.fetchall()


def initialize_backfill(conn) -> dict:
    """Create missing state rows and atomically capture one global high-water mark."""
    with conn.cursor() as cur:
        for source in _push_sources():
            cur.execute(
                """
                INSERT INTO source_ingestion_health_state (source)
                VALUES (%s)
                ON CONFLICT (source) DO NOTHING
                """,
                (source,),
            )

        rows = _load_locked_state(cur)
        high_water_marks = {row[2] for row in rows if row[2] is not None}
        if len(high_water_marks) > 1:
            raise RuntimeError("inconsistent source-health backfill high-water marks")
        if high_water_marks:
            high_water = high_water_marks.pop()
        else:
            cur.execute("SELECT COALESCE(MAX(id), 0) FROM events")
            high_water = int(cur.fetchone()[0])

        cur.execute(
            """
            UPDATE source_ingestion_health_state
            SET backfill_high_water_event_id = %s,
                updated_at = NOW()
            WHERE source = ANY(%s)
              AND backfill_high_water_event_id IS NULL
            """,
            (high_water, list(_push_sources())),
        )
    conn.commit()
    return inspect_backfill(conn)


def inspect_backfill(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT source, historical_backfill_complete,
                   backfill_high_water_event_id, backfill_last_processed_event_id,
                   latest_event_at, latest_qualifying_real_ingestion_at
            FROM source_ingestion_health_state
            WHERE source = ANY(%s)
            ORDER BY source
            """,
            (list(_push_sources()),),
        )
        rows = cur.fetchall()
        cur.execute("SELECT COALESCE(MAX(id), 0) FROM events")
        current_max_event_id = int(cur.fetchone()[0])
    return {
        "current_max_event_id": current_max_event_id,
        "sources": [
            {
                "source": row[0],
                "historical_backfill_complete": bool(row[1]),
                "backfill_high_water_event_id": row[2],
                "backfill_last_processed_event_id": int(row[3]),
                "latest_event_at": row[4].astimezone(timezone.utc).isoformat() if row[4] else None,
                "latest_qualifying_real_ingestion_at": (
                    row[5].astimezone(timezone.utc).isoformat() if row[5] else None
                ),
            }
            for row in rows
        ],
    }


def process_backfill_batch(conn, *, batch_size: int) -> dict:
    if batch_size < 1 or batch_size > MAX_BATCH_SIZE:
        raise ValueError(f"batch_size must be between 1 and {MAX_BATCH_SIZE}")

    with conn.cursor() as cur:
        rows = _load_locked_state(cur)
        if len(rows) != len(_push_sources()):
            raise RuntimeError("source-health backfill is not initialized")

        high_water_marks = {row[2] for row in rows}
        cursors = {int(row[3]) for row in rows}
        completion_states = {bool(row[1]) for row in rows}
        if None in high_water_marks or len(high_water_marks) != 1:
            raise RuntimeError("source-health backfill high-water mark is unavailable")
        if len(cursors) != 1 or len(completion_states) != 1:
            raise RuntimeError("source-health backfill progress is inconsistent")

        high_water = int(high_water_marks.pop())
        cursor = cursors.pop()
        if completion_states.pop():
            conn.commit()
            return {
                "completed": True,
                "batch_start_event_id": cursor,
                "batch_end_event_id": cursor,
                "events_examined": 0,
            }

        batch_end = min(cursor + batch_size, high_water)
        cur.execute(
            f"""
            SELECT id, source, created_at, {_PROVENANCE_SQL} AS provenance
            FROM events
            WHERE id > %s
              AND id <= %s
            ORDER BY id
            """,
            (cursor, batch_end),
        )
        event_rows = cur.fetchall()
        for _event_id, source, created_at, provenance in event_rows:
            if source not in CANONICAL_PUSH_SOURCE_IDS:
                continue
            record_persisted_push_event(
                cur,
                source=source,
                ingested_at=created_at,
                raw_payload={"data_provenance": provenance},
            )

        completed = batch_end >= high_water
        cur.execute(
            """
            UPDATE source_ingestion_health_state
            SET backfill_last_processed_event_id = %s,
                historical_backfill_complete = %s,
                updated_at = NOW()
            WHERE source = ANY(%s)
            """,
            (batch_end, completed, list(_push_sources())),
        )
    conn.commit()
    return {
        "completed": completed,
        "batch_start_event_id": cursor,
        "batch_end_event_id": batch_end,
        "events_examined": len(event_rows),
    }


def run_backfill(conn, *, batch_size: int, max_batches: int | None = None) -> dict:
    initialize_backfill(conn)
    batches = []
    while max_batches is None or len(batches) < max_batches:
        result = process_backfill_batch(conn, batch_size=batch_size)
        batches.append(result)
        if result["completed"]:
            break
    return {
        "batch_size": batch_size,
        "batches_processed": len(batches),
        "events_examined": sum(item["events_examined"] for item in batches),
        "completed": bool(batches and batches[-1]["completed"]),
        "state": inspect_backfill(conn),
    }


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--max-batches", type=int, default=None)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    if args.batch_size < 1 or args.batch_size > MAX_BATCH_SIZE:
        print(
            f"ERROR: --batch-size must be between 1 and {MAX_BATCH_SIZE}",
            file=sys.stderr,
        )
        return 2
    if args.max_batches is not None and args.max_batches < 1:
        print("ERROR: --max-batches must be positive", file=sys.stderr)
        return 2

    conn = get_db_connection()
    try:
        result = (
            run_backfill(
                conn,
                batch_size=args.batch_size,
                max_batches=args.max_batches,
            )
            if args.apply
            else {"dry_run": True, "state": inspect_backfill(conn)}
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
