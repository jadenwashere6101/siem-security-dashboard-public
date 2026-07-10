#!/usr/bin/env python3
"""Evidence-safe backfill of indicator_registry from blocked_ips.

Only imports provable relationships. Labels provenance as inferred when actor
or alert linkage is incomplete. Never manufactures success outcomes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.db import get_db_connection
from core.indicator_response_registry import append_registry_event, upsert_indicator_identity
from core.response_command_contracts import (
    DISPOSITION_BLOCKLIST_TRACKED,
    INDICATOR_TYPE_IP,
    ORIGIN_BACKFILL,
)


def backfill(conn, *, limit: int | None = None) -> dict:
    cur = conn.cursor()
    sql = """
        SELECT id, ip_address, reason, created_by, source_alert_id, created_at, status
        FROM blocked_ips
        ORDER BY id ASC
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    cur.execute(sql)
    rows = cur.fetchall()
    created = 0
    events = 0
    skipped = 0
    for row in rows:
        block_id, ip_address, reason, created_by, source_alert_id, created_at, status = row
        if ip_address is None:
            skipped += 1
            continue
        registry = upsert_indicator_identity(
            conn,
            indicator_type=INDICATOR_TYPE_IP,
            indicator_value=str(ip_address),
        )
        created += 1
        provenance = "recorded" if source_alert_id and created_by else "inferred"
        disposition = (
            DISPOSITION_BLOCKLIST_TRACKED if status == "active" else "removed"
        )
        append_registry_event(
            conn,
            registry_id=registry["id"],
            event_type="backfill_blocklist",
            requested_action="block_ip",
            outcome="succeeded" if status == "active" else "removed",
            disposition_after=disposition,
            enforcement="tracking_only",
            origin_surface=ORIGIN_BACKFILL,
            actor_user_id=created_by,
            reason=reason or "Historical blocklist backfill",
            alert_id=source_alert_id,
            blocked_ip_id=block_id,
            idempotency_key=f"backfill-blocked-ip-{block_id}",
            provenance=provenance,
            safe_metadata={"source": "blocked_ips", "status": status},
        )
        events += 1
    conn.commit()
    return {"rows": len(rows), "identities_touched": created, "events": events, "skipped": skipped}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    conn = get_db_connection()
    try:
        if args.dry_run:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM blocked_ips")
            count = cur.fetchone()[0]
            print(f"Dry run: would inspect {count} blocked_ips rows")
            return 0
        stats = backfill(conn, limit=args.limit)
        print(stats)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
