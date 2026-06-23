"""Backfill geolocation for honeypot events and alerts.

Dry-run by default. Use --apply to write location data.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import sys

import psycopg2
from psycopg2.extras import Json

from core.ip_helpers import lookup_ip_location
from helpers.ingest_normalizers import has_valid_location


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Backfill missing honeypot geolocation on events and alerts."
    )
    parser.add_argument(
        "--db-url",
        help="PostgreSQL DSN. Defaults to DATABASE_URL.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write updates. Without this flag, only prints a dry-run plan.",
    )
    return parser.parse_args(argv)


def _is_global_ip(source_ip):
    try:
        return ipaddress.ip_address(str(source_ip)).is_global
    except ValueError:
        return False


def _candidate_ips(cur):
    cur.execute(
        """
        SELECT DISTINCT host(source_ip)
        FROM (
            SELECT source_ip
            FROM events
            WHERE (source = 'honeypot' OR source_type = 'honeypot')
              AND (
                raw_payload->'location' IS NULL
                OR NULLIF(raw_payload->'location'->>'lat', '') IS NULL
                OR NULLIF(raw_payload->'location'->>'lon', '') IS NULL
              )
            UNION
            SELECT source_ip
            FROM alerts
            WHERE (source = 'honeypot' OR source_type = 'honeypot')
              AND (latitude IS NULL OR longitude IS NULL)
        ) candidates
        ORDER BY 1
        """
    )
    return [row[0] for row in cur.fetchall()]


def _count_event_updates(cur, source_ip):
    cur.execute(
        """
        SELECT COUNT(*)
        FROM events
        WHERE (source = 'honeypot' OR source_type = 'honeypot')
          AND source_ip = %s::inet
          AND (
            raw_payload->'location' IS NULL
            OR NULLIF(raw_payload->'location'->>'lat', '') IS NULL
            OR NULLIF(raw_payload->'location'->>'lon', '') IS NULL
          )
        """,
        (source_ip,),
    )
    return int(cur.fetchone()[0])


def _count_alert_updates(cur, source_ip):
    cur.execute(
        """
        SELECT COUNT(*)
        FROM alerts
        WHERE (source = 'honeypot' OR source_type = 'honeypot')
          AND source_ip = %s::inet
          AND (latitude IS NULL OR longitude IS NULL)
        """,
        (source_ip,),
    )
    return int(cur.fetchone()[0])


def _apply_updates(cur, source_ip, location):
    cur.execute(
        """
        UPDATE events
        SET raw_payload = jsonb_set(
            COALESCE(raw_payload, '{}'::jsonb),
            '{location}',
            %s::jsonb,
            true
        )
        WHERE (source = 'honeypot' OR source_type = 'honeypot')
          AND source_ip = %s::inet
          AND (
            raw_payload->'location' IS NULL
            OR NULLIF(raw_payload->'location'->>'lat', '') IS NULL
            OR NULLIF(raw_payload->'location'->>'lon', '') IS NULL
          )
        """,
        (Json(location), source_ip),
    )
    events_updated = cur.rowcount

    cur.execute(
        """
        UPDATE alerts
        SET
            country = %s,
            city = %s,
            latitude = %s,
            longitude = %s
        WHERE (source = 'honeypot' OR source_type = 'honeypot')
          AND source_ip = %s::inet
          AND (latitude IS NULL OR longitude IS NULL)
        """,
        (
            location.get("country"),
            location.get("city"),
            location.get("lat"),
            location.get("lon"),
            source_ip,
        ),
    )
    alerts_updated = cur.rowcount
    return events_updated, alerts_updated


def run_backfill(conn, *, apply=False):
    summary = {
        "candidate_ips": 0,
        "geolocated_ips": 0,
        "skipped_non_global": 0,
        "skipped_no_location": 0,
        "events_to_update": 0,
        "alerts_to_update": 0,
        "events_updated": 0,
        "alerts_updated": 0,
    }

    with conn.cursor() as cur:
        for source_ip in _candidate_ips(cur):
            summary["candidate_ips"] += 1
            if not _is_global_ip(source_ip):
                summary["skipped_non_global"] += 1
                continue

            location = lookup_ip_location(source_ip)
            if not has_valid_location(location):
                summary["skipped_no_location"] += 1
                continue

            summary["geolocated_ips"] += 1
            event_count = _count_event_updates(cur, source_ip)
            alert_count = _count_alert_updates(cur, source_ip)
            summary["events_to_update"] += event_count
            summary["alerts_to_update"] += alert_count

            if apply:
                events_updated, alerts_updated = _apply_updates(cur, source_ip, location)
                summary["events_updated"] += events_updated
                summary["alerts_updated"] += alerts_updated

    if apply:
        conn.commit()
    else:
        conn.rollback()

    return summary


def _format_summary(summary, *, apply):
    mode = "apply" if apply else "dry-run"
    lines = [f"Honeypot location backfill {mode} summary"]
    lines.append("=" * len(lines[0]))
    for key in (
        "candidate_ips",
        "geolocated_ips",
        "skipped_non_global",
        "skipped_no_location",
        "events_to_update",
        "alerts_to_update",
        "events_updated",
        "alerts_updated",
    ):
        lines.append(f"{key}: {summary[key]}")
    if not apply:
        lines.append("Dry-run only: no database writes were performed.")
    return "\n".join(lines)


def main(argv=None):
    args = _parse_args(argv)
    db_url = args.db_url or os.getenv("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL or --db-url is required.", file=sys.stderr)
        return 1

    conn = None
    try:
        conn = psycopg2.connect(db_url)
        summary = run_backfill(conn, apply=args.apply)
        print(_format_summary(summary, apply=args.apply))
        return 0
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
