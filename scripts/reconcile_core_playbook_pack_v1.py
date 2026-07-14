#!/usr/bin/env python3
"""Reconcile existing Core Playbook Pack v1 definitions to the current source of truth."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg2

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.core_playbook_pack_v1 import CORE_PLAYBOOK_PACK_V1, validate_core_playbook_pack_v1
from core.playbook_store import (
    create_playbook_definition,
    get_playbook_definition,
    update_playbook_definition,
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Reconcile seeded Core Playbook Pack v1 definitions in a PostgreSQL database."
    )
    parser.add_argument("--db-url", default=None, help="PostgreSQL DSN. Defaults to DATABASE_URL.")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    db_url = args.db_url or os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        print("ERROR: --db-url or DATABASE_URL is required.", file=sys.stderr)
        return 1

    errors = validate_core_playbook_pack_v1()
    if errors:
        print("ERROR: Core Playbook Pack v1 validation failed.", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    conn = None
    try:
        conn = psycopg2.connect(db_url)
        changed = reconcile_core_playbook_pack_v1(conn)
        conn.commit()
        print("Core Playbook Pack v1 reconciliation summary")
        print("===========================================")
        print(f"Changed definitions ({len(changed)}): {', '.join(changed) if changed else 'none'}")
        return 0
    except Exception as error:
        if conn is not None:
            conn.rollback()
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    finally:
        if conn is not None:
            conn.close()


def reconcile_core_playbook_pack_v1(conn) -> list[str]:
    changed: list[str] = []
    for playbook in CORE_PLAYBOOK_PACK_V1:
        current = get_playbook_definition(conn, playbook["id"])
        if current is None:
            create_playbook_definition(
                conn,
                playbook["id"],
                playbook["name"],
                description=playbook.get("description"),
                trigger_config=playbook["trigger_config"],
                steps=playbook["steps"],
                enabled=True,
            )
            changed.append(playbook["id"])
            continue

        if (
            current.get("name") == playbook["name"]
            and current.get("description") == playbook.get("description")
            and current.get("trigger_config") == playbook["trigger_config"]
            and current.get("steps") == playbook["steps"]
            and current.get("enabled") is True
        ):
            continue

        update_playbook_definition(
            conn,
            playbook["id"],
            name=playbook["name"],
            description=playbook.get("description"),
            trigger_config=playbook["trigger_config"],
            steps=playbook["steps"],
            enabled=True,
        )
        changed.append(playbook["id"])
    return changed


if __name__ == "__main__":
    raise SystemExit(main())
