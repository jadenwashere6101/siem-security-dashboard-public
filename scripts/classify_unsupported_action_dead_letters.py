#!/usr/bin/env python3
"""Classify historical unsupported_action dead letters for notify/enrich_context.

Report-only. Does not retry, dismiss, or mutate dead-letter rows.
Intended for VM handoff after Mac Phase 3 routing fixes are deployed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import psycopg2


SAFE_RETRY_HINTS = {
    "notify": (
        "Do not retry bare notify. Require remapping to notify_slack / notify_email / "
        "notify_webhook / notify_teams before any canary retry."
    ),
    "enrich_context": (
        "Do not retry via response-action queue. enrich_context is playbook-read-only; "
        "dismiss obsolete queue rows or re-run as a playbook step."
    ),
}


def classify_action(action: str | None) -> dict:
    name = str(action or "").strip()
    if name == "notify":
        return {
            "cohort": "ambiguous_notify",
            "disposition": "dismiss_or_remap",
            "hint": SAFE_RETRY_HINTS["notify"],
        }
    if name == "enrich_context":
        return {
            "cohort": "misrouted_enrich_context",
            "disposition": "dismiss_or_playbook_only",
            "hint": SAFE_RETRY_HINTS["enrich_context"],
        }
    if name.startswith("notify_"):
        return {
            "cohort": "provider_notify",
            "disposition": "canary_retry_if_idempotent",
            "hint": "Provider-specific notify may be canary-retried only when idempotent and safe.",
        }
    return {
        "cohort": "other_unsupported",
        "disposition": "manual_review",
        "hint": "Review payload and owning executor before any retry.",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="store_true", help="Print JSON report to stdout")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args(argv)
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL is required", file=sys.stderr)
        return 2

    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor()
        # Prefer dead-letter table when present; fall back to queue skipped rows.
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'soar_dead_letters'
            )
            """
        )
        has_dead_letters = bool(cur.fetchone()[0])
        rows = []
        if has_dead_letters:
            cur.execute(
                """
                SELECT id, status, error_code, action, created_at
                FROM soar_dead_letters
                WHERE error_code = 'unsupported_action'
                   OR COALESCE(action, '') IN ('notify', 'enrich_context')
                ORDER BY id DESC
                LIMIT %s
                """,
                (args.limit,),
            )
            rows = cur.fetchall()
        else:
            cur.execute(
                """
                SELECT id, status, last_error, action, created_at
                FROM response_actions_queue
                WHERE status IN ('skipped', 'failed')
                  AND (
                    COALESCE(action, '') IN ('notify', 'enrich_context')
                    OR COALESCE(last_error, '') ILIKE '%%unsupported%%'
                  )
                ORDER BY id DESC
                LIMIT %s
                """,
                (args.limit,),
            )
            rows = cur.fetchall()

        classified = []
        cohort_counts = Counter()
        for row in rows:
            action = row[3]
            info = classify_action(action)
            cohort_counts[info["cohort"]] += 1
            classified.append(
                {
                    "id": row[0],
                    "status": row[1],
                    "error": row[2],
                    "action": action,
                    "created_at": str(row[4]) if row[4] is not None else None,
                    **info,
                }
            )

        report = {
            "total": len(classified),
            "cohort_counts": dict(cohort_counts),
            "items": classified,
            "notes": [
                "Report only — no mutations performed.",
                "Canary retry only after Mac routing deploy and idempotency review.",
            ],
        }
        if args.report or True:
            print(json.dumps(report, indent=2, default=str))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
