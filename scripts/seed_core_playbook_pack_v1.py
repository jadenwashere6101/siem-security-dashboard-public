#!/usr/bin/env python3
"""Manually seed Core Playbook Pack v1 into a target database."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg2

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.core_playbook_pack_v1 import (
    CORE_PLAYBOOK_PACK_V1,
    seed_core_playbook_pack_v1,
    validate_core_playbook_pack_v1,
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Manually seed Core Playbook Pack v1 into a PostgreSQL database."
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        print("ERROR: DATABASE_URL is required.", file=sys.stderr)
        return 1

    validation_errors = validate_core_playbook_pack_v1()
    if validation_errors:
        print("ERROR: Core Playbook Pack v1 validation failed.", file=sys.stderr)
        for error in validation_errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    conn = None
    try:
        conn = psycopg2.connect(db_url)
        _validate_connection(conn)
        database_label = _connection_label(conn)

        inserted = seed_core_playbook_pack_v1(conn)
        inserted_set = set(inserted)
        existing = [item["id"] for item in CORE_PLAYBOOK_PACK_V1 if item["id"] not in inserted_set]

        conn.commit()
        _print_summary(database_label, inserted, existing)
        return 0
    except Exception as error:
        if conn is not None:
            conn.rollback()
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    finally:
        if conn is not None:
            conn.close()


def _validate_connection(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
        cur.fetchone()


def _connection_label(conn) -> str:
    try:
        params = conn.get_dsn_parameters()
    except Exception:
        return "connected database"

    dbname = params.get("dbname") or params.get("database") or "unknown"
    host = params.get("host") or "local"
    port = params.get("port")
    if port:
        return f"{dbname}@{host}:{port}"
    return f"{dbname}@{host}"


def _print_summary(database_label: str, inserted: list[str], existing: list[str]) -> None:
    total = len(CORE_PLAYBOOK_PACK_V1)
    print("Core Playbook Pack v1 seed summary")
    print("===================================")
    print(f"Connected database: {database_label}")
    print(f"Inserted playbooks ({len(inserted)}): {_format_ids(inserted)}")
    print(f"Already-existing playbooks ({len(existing)}): {_format_ids(existing)}")
    print(f"Final totals: inserted={len(inserted)} existing={len(existing)} total={total}")
    if not inserted:
        print("No changes made; all Core Playbook Pack v1 playbooks already exist.")


def _format_ids(ids: list[str]) -> str:
    return ", ".join(ids) if ids else "none"


if __name__ == "__main__":
    raise SystemExit(main())
