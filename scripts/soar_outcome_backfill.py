#!/usr/bin/env python3
"""Dry-run planner for SOAR response outcome backfill. No write mode yet."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg2

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.soar_response_outcomes import format_backfill_plan_summary, plan_backfill_dry_run


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Plan SOAR response outcome backfill without modifying the database."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Scan legacy tables and print a backfill plan without writing rows.",
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="PostgreSQL DSN. Defaults to DATABASE_URL.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if not args.dry_run:
        print(
            "ERROR: only --dry-run is supported. No write mode is available yet.",
            file=sys.stderr,
        )
        return 2

    db_url = args.db_url or os.getenv("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL or --db-url is required.", file=sys.stderr)
        return 1

    conn = psycopg2.connect(db_url)
    try:
        plan = plan_backfill_dry_run(conn)
        print(format_backfill_plan_summary(plan))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
