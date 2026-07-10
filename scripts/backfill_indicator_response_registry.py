#!/usr/bin/env python3
"""Evidence-safe backfill of indicator_registry from blocked_ips.

Only imports provable relationships. Labels provenance as inferred when actor
or alert linkage is incomplete. Never manufactures success outcomes.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

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


def _resolve_actor_user_id(conn, created_by: Any) -> int | None:
    """Resolve legacy blocked_ips.created_by values to users.id.

    Historical databases may contain either the current integer user id or the
    older username representation. Numeric strings are treated as ids; all
    other non-empty strings are resolved through users.username.
    """
    if created_by is None or isinstance(created_by, bool):
        return None

    candidate: int | None = None
    if isinstance(created_by, int):
        candidate = created_by
    elif isinstance(created_by, str):
        value = created_by.strip()
        if not value:
            return None
        try:
            candidate = int(value)
        except ValueError:
            cur = conn.cursor()
            cur.execute("SELECT id FROM users WHERE username = %s", (value,))
            row = cur.fetchone()
            return int(row[0]) if row else None
    else:
        return None

    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE id = %s", (candidate,))
    row = cur.fetchone()
    return int(row[0]) if row else None


def _preserve_historical_event_timestamp(
    conn,
    *,
    event_id: int,
    created_at: datetime | None,
) -> None:
    if created_at is None:
        return
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE indicator_response_events
        SET created_at = %s
        WHERE id = %s
          AND idempotency_key LIKE 'backfill-blocked-ip-%%'
        """,
        (created_at, event_id),
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
    unresolved_actors: list[dict[str, Any]] = []
    for row in rows:
        block_id, ip_address, reason, created_by, source_alert_id, created_at, status = row
        if ip_address is None:
            skipped += 1
            continue
        actor_user_id = _resolve_actor_user_id(conn, created_by)
        if created_by is not None and actor_user_id is None:
            warning = {
                "blocked_ip_id": block_id,
                "created_by": str(created_by),
                "reason": "actor could not be resolved to users.id",
            }
            unresolved_actors.append(warning)
            skipped += 1
            print(
                "WARNING: skipping blocked_ips "
                f"id={block_id}: created_by={created_by!r} could not be resolved to users.id",
                file=sys.stderr,
            )
            continue
        registry = upsert_indicator_identity(
            conn,
            indicator_type=INDICATOR_TYPE_IP,
            indicator_value=str(ip_address),
        )
        created += 1
        provenance = "recorded" if source_alert_id and actor_user_id else "inferred"
        disposition = (
            DISPOSITION_BLOCKLIST_TRACKED if status == "active" else "removed"
        )
        event = append_registry_event(
            conn,
            registry_id=registry["id"],
            event_type="backfill_blocklist",
            requested_action="block_ip",
            outcome="succeeded" if status == "active" else "removed",
            disposition_after=disposition,
            enforcement="tracking_only",
            origin_surface=ORIGIN_BACKFILL,
            actor_user_id=actor_user_id,
            reason=reason or "Historical blocklist backfill",
            alert_id=source_alert_id,
            blocked_ip_id=block_id,
            idempotency_key=f"backfill-blocked-ip-{block_id}",
            provenance=provenance,
            safe_metadata={"source": "blocked_ips", "status": status},
        )
        _preserve_historical_event_timestamp(
            conn,
            event_id=event["id"],
            created_at=created_at,
        )
        events += 1
    conn.commit()
    return {
        "rows": len(rows),
        "identities_touched": created,
        "events": events,
        "skipped": skipped,
        "unresolved_actor_count": len(unresolved_actors),
        "unresolved_actors": unresolved_actors,
    }


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
        print(json.dumps(stats, sort_keys=True))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
