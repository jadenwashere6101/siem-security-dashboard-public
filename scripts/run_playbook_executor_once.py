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
                for line in _render_recovery_summary_lines(payload):
                    print(line)
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
                "skip_reasons": _skip_reason_counts(result["results"]),
                "claimed_execution_ids": _claimed_execution_ids(result["results"]),
            },
            "results": result["results"],
        }
        if args.json:
            print(json.dumps(payload, default=str))
        else:
            for line in _render_batch_summary_lines(payload):
                print(line)
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
    awaiting_approval_skipped = playbook_store.count_expired_awaiting_approval_leases(
        conn,
        now=timestamp,
    )

    if dry_run:
        logger.info(
            "playbook stale recovery dry_run scanned=%s skipped_awaiting_approval=%s",
            len(stale_rows),
            awaiting_approval_skipped,
        )
        return {
            "dry_run": True,
            "scanned": len(stale_rows),
            "recovered": 0,
            "pending": 0,
            "failed": 0,
            "skipped_awaiting_approval": awaiting_approval_skipped,
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

    payload = {
        "dry_run": False,
        "scanned": len(stale_rows),
        "recovered": sum(1 for row in results if row.get("outcome") == "recovered"),
        "pending": sum(1 for row in results if row.get("new_status") == "pending"),
        "failed": sum(1 for row in results if row.get("new_status") == "failed"),
        "skipped_awaiting_approval": awaiting_approval_skipped,
        "stale": [_recovery_row_summary(row) for row in stale_rows],
        "results": results,
    }
    logger.info(
        "playbook stale recovery applied scanned=%s recovered=%s pending=%s failed=%s skipped_awaiting_approval=%s",
        payload["scanned"],
        payload["recovered"],
        payload["pending"],
        payload["failed"],
        payload["skipped_awaiting_approval"],
    )
    return payload


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


def _skip_reason_counts(results):
    counts = {}
    for row in results:
        if row.get("outcome") != "skipped":
            continue
        reason = str(row.get("reason") or "unknown")
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def _claimed_execution_ids(results):
    return [
        row["execution_id"]
        for row in results
        if row.get("execution_id") is not None and row.get("outcome") != "skipped"
    ]


def _render_batch_summary_lines(payload):
    summary = payload["summary"]
    lines = [
        "=== SOAR Playbook Simulation Executor ===",
        f"Mode:       {payload['mode']}",
        f"Worker id:  {payload['worker_id']}",
        f"Batch size: {payload['batch_size']}",
        f"Processed:  {summary['processed']}",
        f"Success:    {summary['success']}",
        f"Failed:     {summary['failed']}",
        f"Skipped:    {summary['skipped']}",
    ]
    claimed_ids = summary.get("claimed_execution_ids") or []
    lines.append(f"Claimed execution ids: {_format_id_list(claimed_ids)}")
    skip_reasons = summary.get("skip_reasons") or {}
    if skip_reasons:
        rendered = ", ".join(f"{key}={value}" for key, value in sorted(skip_reasons.items()))
    else:
        rendered = "none"
    lines.append(f"Skip reasons: {rendered}")
    lines.append("No real integrations were called.")
    return lines


def _render_recovery_summary_lines(payload):
    recovery = payload["recovery"]
    stale_ids = [row["execution_id"] for row in recovery.get("stale", [])]
    recovered_ids = [
        row["execution_id"]
        for row in recovery.get("results", [])
        if row.get("outcome") == "recovered"
    ]
    lines = [
        "=== SOAR Playbook Stale Recovery ===",
        f"Mode:       {payload['mode']}",
        f"Worker id:  {payload['worker_id']}",
        f"Dry run:    {recovery['dry_run']}",
        f"Scanned:    {recovery['scanned']}",
        f"Recovered:  {recovery['recovered']}",
        f"Pending:    {recovery['pending']}",
        f"Failed:     {recovery['failed']}",
        f"Skipped awaiting approval: {recovery.get('skipped_awaiting_approval', 0)}",
        f"Stale execution ids: {_format_id_list(stale_ids)}",
        f"Recovered execution ids: {_format_id_list(recovered_ids)}",
    ]
    for row in recovery.get("results", []):
        if row.get("outcome") == "recovered":
            lines.append(
                "Recovered execution "
                f"{row['execution_id']}: {row['prior_status']} -> {row['new_status']} "
                f"recovery_count={row['recovery_count']}"
            )
        elif row.get("outcome") == "skipped":
            lines.append(
                "Skipped execution "
                f"{row['execution_id']}: reason={row.get('reason', 'unknown')}"
            )
    lines.append("No playbook steps were executed.")
    return lines


def _format_id_list(values):
    if not values:
        return "none"
    return ",".join(str(value) for value in values)


if __name__ == "__main__":
    raise SystemExit(main())
