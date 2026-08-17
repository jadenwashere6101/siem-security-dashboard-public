#!/usr/bin/env python3
"""Initialize durable canonical-source lifetime totals once, outside request paths.

Dry-run is the default. ``--apply`` performs one historical count and then a
short locked reconciliation so concurrent ingestion is neither lost nor
double-counted.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.db import get_db_connection
from core.source_inventory import CANONICAL_SOURCE_IDS


def _sources() -> tuple[str, ...]:
    return tuple(sorted(CANONICAL_SOURCE_IDS))


def inspect_totals(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT source, total_events, total_events_initialized
            FROM source_ingestion_health_state
            WHERE source = ANY(%s)
            ORDER BY source
            """,
            (list(_sources()),),
        )
        rows = cur.fetchall()
    return {
        "sources": [
            {
                "source": row[0],
                "total_events": int(row[1]),
                "total_events_initialized": bool(row[2]),
            }
            for row in rows
        ]
    }


def _count_through(cur, *, lower_exclusive: int, upper_inclusive: int) -> dict[str, int]:
    if upper_inclusive <= lower_exclusive:
        return {}
    cur.execute(
        """
        SELECT source, COUNT(*)
        FROM events
        WHERE id > %s
          AND id <= %s
          AND source = ANY(%s)
        GROUP BY source
        """,
        (lower_exclusive, upper_inclusive, list(_sources())),
    )
    return {row[0]: int(row[1]) for row in cur.fetchall()}


def initialize_totals(conn) -> dict:
    current = inspect_totals(conn)
    initialized = {
        item["source"]
        for item in current["sources"]
        if item["total_events_initialized"]
    }
    if initialized:
        if initialized != set(_sources()):
            raise RuntimeError("canonical source total initialization is inconsistent")
        return {"initialized": True, "events_counted": 0, "state": current}

    with conn.cursor() as cur:
        cur.execute("SELECT COALESCE(MAX(id), 0) FROM events")
        initial_high_water = int(cur.fetchone()[0])
        base_counts = _count_through(
            cur,
            lower_exclusive=0,
            upper_inclusive=initial_high_water,
        )
    conn.commit()

    with conn.cursor() as cur:
        for source in _sources():
            cur.execute(
                """
                INSERT INTO source_ingestion_health_state (source)
                VALUES (%s)
                ON CONFLICT (source) DO NOTHING
                """,
                (source,),
            )
        cur.execute(
            """
            SELECT source
            FROM source_ingestion_health_state
            WHERE source = ANY(%s)
            ORDER BY source
            FOR UPDATE
            """,
            (list(_sources()),),
        )
        locked_sources = {row[0] for row in cur.fetchall()}
        if locked_sources != set(_sources()):
            raise RuntimeError("unable to lock every canonical source total")

        cur.execute("SELECT COALESCE(MAX(id), 0) FROM events")
        reconciled_high_water = int(cur.fetchone()[0])
        delta_counts = _count_through(
            cur,
            lower_exclusive=initial_high_water,
            upper_inclusive=reconciled_high_water,
        )
        for source in _sources():
            total = base_counts.get(source, 0) + delta_counts.get(source, 0)
            cur.execute(
                """
                UPDATE source_ingestion_health_state
                SET total_events = %s,
                    total_events_initialized = TRUE,
                    updated_at = NOW()
                WHERE source = %s
                """,
                (total, source),
            )
    conn.commit()
    state = inspect_totals(conn)
    return {
        "initialized": True,
        "initial_high_water_event_id": initial_high_water,
        "reconciled_high_water_event_id": reconciled_high_water,
        "events_counted": sum(item["total_events"] for item in state["sources"]),
        "state": state,
    }


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    conn = get_db_connection()
    try:
        result = initialize_totals(conn) if args.apply else {
            "dry_run": True,
            "state": inspect_totals(conn),
        }
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
