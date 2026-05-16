from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core import playbook_store
from core.playbook_worker_identity import generate_playbook_worker_id
from engines.playbook_step_executor import process_playbook_execution_batch

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 10
MAX_BATCH_SIZE = 50
DEFAULT_STALE_LIMIT = 50
MAX_STALE_LIMIT = 200


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run one simulation-only SOAR playbook executor batch and exit."
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--json", action="store_true", default=False)
    parser.add_argument(
        "--recover-stale",
        action="store_true",
        default=False,
        help="Manually scan expired running playbook leases and mark them for recovery.",
    )
    parser.add_argument(
        "--stale-limit",
        type=int,
        default=DEFAULT_STALE_LIMIT,
        help=f"Maximum stale executions to inspect when --recover-stale is used (1-{MAX_STALE_LIMIT}).",
    )
    parser.add_argument(
        "--dry-run-recovery",
        action="store_true",
        default=False,
        help="List stale executions without mutating them. Requires --recover-stale.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    batch_size = _normalize_batch_size(args.batch_size)
    stale_limit = _normalize_stale_limit(args.stale_limit)
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        message = "DATABASE_URL is required"
        if args.json:
            print(json.dumps({"error": message}))
        else:
            print(f"ERROR: {message}", file=sys.stderr)
        return 1

    conn = None
    worker_id = generate_playbook_worker_id()
    try:
        conn = psycopg2.connect(database_url)
        logging.basicConfig(level=logging.INFO)
        logger.info("Playbook executor worker_id=%s", worker_id)
        if args.dry_run_recovery and not args.recover_stale:
            raise ValueError("--dry-run-recovery requires --recover-stale")
        if args.recover_stale:
            result = recover_stale_playbook_executions(
                conn,
                limit=stale_limit,
                dry_run=args.dry_run_recovery,
            )
            if args.dry_run_recovery:
                conn.rollback()
            else:
                conn.commit()
            payload = {
                "mode": "simulation",
                "worker_id": worker_id,
                "recovery": result,
            }
            if args.json:
                print(json.dumps(payload, default=str))
            else:
                print("=== SOAR Playbook Stale Recovery ===")
                print(f"Mode:       {payload['mode']}")
                print(f"Worker id:  {worker_id}")
                print(f"Dry run:    {result['dry_run']}")
                print(f"Scanned:    {result['scanned']}")
                print(f"Recovered:  {result['recovered']}")
                print(f"Pending:    {result['pending']}")
                print(f"Failed:     {result['failed']}")
                print("No playbook steps were executed.")
            return 0
        result = process_playbook_execution_batch(
            conn,
            limit=batch_size,
            worker_id=worker_id,
        )
        conn.commit()
        payload = {
            "mode": "simulation",
            "worker_id": worker_id,
            "batch_size": batch_size,
            "summary": {
                "processed": result["processed"],
                "success": result["success"],
                "failed": result["failed"],
                "skipped": result["skipped"],
            },
            "results": result["results"],
        }
        if args.json:
            print(json.dumps(payload, default=str))
        else:
            print("=== SOAR Playbook Simulation Executor ===")
            print(f"Mode:       {payload['mode']}")
            print(f"Worker id:  {worker_id}")
            print(f"Batch size: {batch_size}")
            print(f"Processed:  {payload['summary']['processed']}")
            print(f"Success:    {payload['summary']['success']}")
            print(f"Failed:     {payload['summary']['failed']}")
            print(f"Skipped:    {payload['summary']['skipped']}")
            print("No real integrations were called.")
        return 0
    except Exception as error:
        if conn is not None:
            conn.rollback()
        if args.json:
            print(json.dumps({"error": str(error)}))
        else:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2
    finally:
        if conn is not None:
            conn.close()


def _normalize_batch_size(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_BATCH_SIZE
    if parsed < 1:
        return 1
    return min(parsed, MAX_BATCH_SIZE)


def _normalize_stale_limit(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_STALE_LIMIT
    if parsed < 1:
        return 1
    return min(parsed, MAX_STALE_LIMIT)


def recover_stale_playbook_executions(
    conn,
    *,
    limit: int = DEFAULT_STALE_LIMIT,
    dry_run: bool = False,
    now: datetime | None = None,
) -> dict:
    timestamp = now or datetime.now(timezone.utc)
    stale_rows = playbook_store.list_stale_running_executions(
        conn,
        now=timestamp,
        limit=_normalize_stale_limit(limit),
    )

    if dry_run:
        return {
            "dry_run": True,
            "scanned": len(stale_rows),
            "recovered": 0,
            "pending": 0,
            "failed": 0,
            "stale": [_recovery_row_summary(row) for row in stale_rows],
            "results": [],
        }

    results = []
    for row in stale_rows:
        updated = playbook_store.mark_stale_execution_for_recovery(
            conn,
            row["id"],
            now=timestamp,
        )
        if updated is None:
            results.append(
                {
                    "execution_id": row["id"],
                    "prior_status": row["status"],
                    "new_status": row["status"],
                    "outcome": "skipped",
                    "reason": "not_recovered",
                }
            )
            continue
        results.append(
            {
                "execution_id": updated["id"],
                "prior_status": row["status"],
                "new_status": updated["status"],
                "outcome": "recovered",
                "attempt_count": updated["attempt_count"],
                "max_attempts": updated["max_attempts"],
                "recovery_count": updated["recovery_count"],
                "last_completed_step": updated["last_completed_step"],
                "failure_reason": updated["failure_reason"],
            }
        )

    return {
        "dry_run": False,
        "scanned": len(stale_rows),
        "recovered": sum(1 for row in results if row.get("outcome") == "recovered"),
        "pending": sum(1 for row in results if row.get("new_status") == "pending"),
        "failed": sum(1 for row in results if row.get("new_status") == "failed"),
        "stale": [_recovery_row_summary(row) for row in stale_rows],
        "results": results,
    }


def _recovery_row_summary(row):
    return {
        "execution_id": row["id"],
        "status": row["status"],
        "lease_owner": row["lease_owner"],
        "lease_expires_at": row["lease_expires_at"],
        "attempt_count": row["attempt_count"],
        "max_attempts": row["max_attempts"],
        "recovery_count": row["recovery_count"],
        "last_completed_step": row["last_completed_step"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
