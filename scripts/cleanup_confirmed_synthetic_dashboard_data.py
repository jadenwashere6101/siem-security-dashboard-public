from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from core.db import get_db_connection
from core.synthetic_data_policy import (
    CONFIRMED_LEGACY_SYNTHETIC_SOURCE_IPS,
    SYNTHETIC_PROVENANCE_VALUES,
    normalize_confirmed_synthetic_alert_ids,
)

CONFIRMATION_TOKEN = "DELETE_CONFIRMED_SYNTHETIC_DASHBOARD_DATA"
DEPENDENCY_QUERIES = {
    "incident_alerts": "SELECT * FROM incident_alerts WHERE alert_id = ANY(%s) ORDER BY alert_id, incident_id",
    "response_actions_queue": "SELECT * FROM response_actions_queue WHERE alert_id = ANY(%s) ORDER BY alert_id, id",
    "response_actions_log": "SELECT * FROM response_actions_log WHERE alert_id = ANY(%s) ORDER BY alert_id, id",
    "alert_notes": "SELECT * FROM alert_notes WHERE alert_id = ANY(%s) ORDER BY alert_id, id",
    "audit_log": "SELECT * FROM audit_log WHERE target_alert_id = ANY(%s) ORDER BY target_alert_id, id",
    "notification_delivery_attempts": (
        "SELECT * FROM notification_delivery_attempts WHERE alert_id = ANY(%s) ORDER BY alert_id, id"
    ),
    "playbook_executions": "SELECT * FROM playbook_executions WHERE alert_id = ANY(%s) ORDER BY alert_id, id",
    "soar_dead_letters": "SELECT * FROM soar_dead_letters WHERE alert_id = ANY(%s) ORDER BY alert_id, id",
    "soar_response_decisions": "SELECT * FROM soar_response_decisions WHERE alert_id = ANY(%s) ORDER BY alert_id, id",
    "soar_response_outcome_events": (
        "SELECT * FROM soar_response_outcome_events WHERE alert_id = ANY(%s) ORDER BY alert_id, id"
    ),
    "indicator_response_events": (
        "SELECT * FROM indicator_response_events WHERE alert_id = ANY(%s) ORDER BY alert_id, id"
    ),
    "blocked_ips": "SELECT * FROM blocked_ips WHERE source_alert_id = ANY(%s) ORDER BY source_alert_id, id",
    "recon_activity_alerts": (
        "SELECT * FROM recon_activity_alerts WHERE alert_id = ANY(%s) ORDER BY alert_id, recon_activity_id"
    ),
}


def _json_default(value: Any):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _rows_as_dicts(cur) -> list[dict[str, Any]]:
    columns = [column.name for column in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def _fetch_dicts(cur, query: str, params: tuple) -> list[dict[str, Any]]:
    cur.execute(query, params)
    return _rows_as_dicts(cur)


def fetch_confirmed_synthetic_alert_rows(
    cur,
    *,
    alert_ids: tuple[int, ...],
    source_ips: tuple[str, ...],
) -> list[dict[str, Any]]:
    return _fetch_dicts(
        cur,
        """
        SELECT *
        FROM alerts
        WHERE id = ANY(%s)
          AND host(source_ip) = ANY(%s)
        ORDER BY id
        """,
        (list(alert_ids), list(source_ips)),
    )


def fetch_associated_synthetic_event_rows(
    cur,
    *,
    source_ips: tuple[str, ...],
) -> list[dict[str, Any]]:
    synthetic_values = sorted(SYNTHETIC_PROVENANCE_VALUES)
    return _fetch_dicts(
        cur,
        """
        SELECT *
        FROM events
        WHERE host(source_ip) = ANY(%s)
          AND (
              LOWER(COALESCE(source, '')) = ANY(%s)
              OR LOWER(COALESCE(source_type, '')) = ANY(%s)
              OR LOWER(COALESCE(app_name, '')) = ANY(%s)
              OR LOWER(COALESCE(environment, '')) = ANY(%s)
              OR LOWER(COALESCE(raw_payload->>'data_provenance', '')) = ANY(%s)
              OR LOWER(COALESCE(raw_payload->>'telemetry_provenance', '')) = ANY(%s)
              OR LOWER(COALESCE(raw_payload->>'provenance', '')) = ANY(%s)
              OR LOWER(COALESCE(raw_payload#>>'{provenance,classification}', '')) = ANY(%s)
              OR LOWER(COALESCE(raw_payload#>>'{provenance,source}', '')) = ANY(%s)
              OR message ILIKE 'Simulated %%'
          )
        ORDER BY id
        """,
        (
            list(source_ips),
            synthetic_values,
            synthetic_values,
            synthetic_values,
            synthetic_values,
            synthetic_values,
            synthetic_values,
            synthetic_values,
            synthetic_values,
            synthetic_values,
        ),
    )


def fetch_dependency_report(cur, alert_ids: tuple[int, ...]) -> dict[str, list[dict[str, Any]]]:
    return {
        table: _fetch_dicts(cur, query, (list(alert_ids),))
        for table, query in DEPENDENCY_QUERIES.items()
    }


def build_cleanup_report(
    conn,
    *,
    alert_ids: tuple[int, ...] | None = None,
    source_ips: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    alert_ids = normalize_confirmed_synthetic_alert_ids(alert_ids)
    source_ips = tuple(sorted(source_ips or CONFIRMED_LEGACY_SYNTHETIC_SOURCE_IPS))
    with conn.cursor() as cur:
        alerts = fetch_confirmed_synthetic_alert_rows(cur, alert_ids=alert_ids, source_ips=source_ips)
        events = fetch_associated_synthetic_event_rows(cur, source_ips=source_ips)
        dependencies = fetch_dependency_report(cur, tuple(row["id"] for row in alerts))
        found_alert_ids = {int(row["id"]) for row in alerts}
        dependency_counts = {table: len(rows) for table, rows in dependencies.items()}
        refusal_reasons = []
        missing_alert_ids = [alert_id for alert_id in alert_ids if alert_id not in found_alert_ids]
        if missing_alert_ids:
            refusal_reasons.append(
                {
                    "code": "missing_confirmed_alert_ids",
                    "alert_ids": missing_alert_ids,
                }
            )
        unexpected_dependencies = {
            table: count for table, count in dependency_counts.items() if count > 0
        }
        if unexpected_dependencies:
            refusal_reasons.append(
                {
                    "code": "unexpected_dependencies",
                    "counts": unexpected_dependencies,
                }
            )
        return {
            "mode": "dry_run",
            "configured_alert_ids": list(alert_ids),
            "confirmed_source_ips": list(source_ips),
            "selected_alerts": alerts,
            "selected_events": events,
            "dependencies": dependencies,
            "dependency_counts": dependency_counts,
            "refusal_reasons": refusal_reasons,
            "would_delete": {
                "alerts": len(alerts),
                "events": len(events),
            },
        }


def write_backup(report: dict[str, Any], backup_dir: str | Path) -> Path:
    backup_path = Path(backup_dir)
    backup_path.mkdir(parents=True, exist_ok=True)
    output_path = backup_path / f"confirmed_synthetic_dashboard_cleanup_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
    output_path.write_text(json.dumps(report, indent=2, default=_json_default) + "\n", encoding="utf-8")
    return output_path


def execute_cleanup(
    conn,
    *,
    execute: bool = False,
    confirm: str | None = None,
    backup_dir: str | Path = "synthetic_cleanup_backups",
) -> dict[str, Any]:
    report = build_cleanup_report(conn)
    if not execute:
        return report
    if confirm != CONFIRMATION_TOKEN:
        report["mode"] = "refused"
        report["refusal_reasons"].append({"code": "missing_confirmation_token"})
        return report
    if report["refusal_reasons"]:
        report["mode"] = "refused"
        return report

    backup_path = write_backup(report, backup_dir)
    alert_ids = [int(row["id"]) for row in report["selected_alerts"]]
    event_ids = [int(row["id"]) for row in report["selected_events"]]
    with conn.cursor() as cur:
        cur.execute("DELETE FROM events WHERE id = ANY(%s)", (event_ids,))
        deleted_events = cur.rowcount
        cur.execute("DELETE FROM alerts WHERE id = ANY(%s)", (alert_ids,))
        deleted_alerts = cur.rowcount
    conn.commit()
    report["mode"] = "executed"
    report["backup_path"] = str(backup_path)
    report["deleted"] = {"alerts": deleted_alerts, "events": deleted_events}
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dry-run or execute cleanup for confirmed legacy synthetic dashboard records."
    )
    parser.add_argument("--execute", action="store_true", help="Delete selected rows transactionally after safety checks.")
    parser.add_argument("--confirm", default="", help=f"Required for --execute: {CONFIRMATION_TOKEN}")
    parser.add_argument("--backup-dir", default="synthetic_cleanup_backups")
    args = parser.parse_args()

    conn = get_db_connection()
    try:
        report = execute_cleanup(
            conn,
            execute=args.execute,
            confirm=args.confirm,
            backup_dir=args.backup_dir,
        )
        if report["mode"] != "executed":
            conn.rollback()
        print(json.dumps(report, indent=2, default=_json_default))
        return 0 if report["mode"] in {"dry_run", "executed"} else 2
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
