import argparse
import json
import logging
import os
import sys
from pathlib import Path

import psycopg2

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.playbook_worker_identity import generate_playbook_worker_id
from engines.playbook_step_executor import process_playbook_execution_batch

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 10
MAX_BATCH_SIZE = 50


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run one simulation-only SOAR playbook executor batch and exit."
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--json", action="store_true", default=False)
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    batch_size = _normalize_batch_size(args.batch_size)
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


if __name__ == "__main__":
    raise SystemExit(main())
