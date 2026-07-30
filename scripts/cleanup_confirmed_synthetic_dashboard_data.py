from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKUP_DIR = "synthetic_cleanup_backups"

sys.path.insert(0, str(REPO_ROOT))

from core.synthetic_data_policy import (
    CONFIRMED_SYNTHETIC_CLEANUP_SOURCE_IPS,
    SYNTHETIC_PROVENANCE_VALUES,
    SYNTHETIC_TEXT_EVIDENCE_REGEX,
    build_synthetic_json_value_sql,
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
BENIGN_MONITOR_DEPENDENCY_TABLES = frozenset(
    {
        "response_actions_queue",
        "response_actions_log",
        "soar_response_decisions",
        "soar_response_outcome_events",
        "indicator_response_events",
    }
)


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


def _synthetic_event_cte() -> tuple[str, list]:
    synthetic_values = sorted(SYNTHETIC_PROVENANCE_VALUES)
    raw_payload_value_sql = build_synthetic_json_value_sql("e.raw_payload")
    return (
        f"""
        WITH synthetic_events AS (
            SELECT e.*
            FROM events e
            WHERE host(e.source_ip) = ANY(%s)
              AND (
                  LOWER(COALESCE(e.source, '')) = ANY(%s)
                  OR LOWER(COALESCE(e.source_type, '')) = ANY(%s)
                  OR LOWER(COALESCE(e.app_name, '')) = ANY(%s)
                  OR LOWER(COALESCE(e.environment, '')) = ANY(%s)
                  OR {raw_payload_value_sql} = ANY(%s)
                  OR COALESCE(e.message, '') ~* %s
                  OR COALESCE(e.raw_payload::text, '') ~* %s
              )
        )
        """,
        [
            synthetic_values,
            synthetic_values,
            synthetic_values,
            synthetic_values,
            synthetic_values,
            SYNTHETIC_TEXT_EVIDENCE_REGEX,
            SYNTHETIC_TEXT_EVIDENCE_REGEX,
        ],
    )


def fetch_synthetic_event_rows(
    cur,
    *,
    source_ips: tuple[str, ...],
) -> list[dict[str, Any]]:
    cte_sql, cte_params = _synthetic_event_cte()
    return _fetch_dicts(
        cur,
        f"""
        {cte_sql}
        SELECT *
        FROM synthetic_events
        ORDER BY id
        """,
        (sorted(source_ips), *cte_params),
    )


def fetch_alert_rows_for_synthetic_events(
    cur,
    *,
    alert_ids: tuple[int, ...],
    source_ips: tuple[str, ...],
) -> list[dict[str, Any]]:
    cte_sql, cte_params = _synthetic_event_cte()
    return _fetch_dicts(
        cur,
        f"""
        {cte_sql},
        synthetic_event_batches AS (
            SELECT
                host(source_ip) AS source_ip_key,
                MIN(created_at) AS first_seen,
                MAX(created_at) AS last_seen
            FROM synthetic_events
            GROUP BY host(source_ip)
        )
        SELECT DISTINCT a.*
        FROM alerts a
        JOIN synthetic_event_batches b
          ON b.source_ip_key = host(a.source_ip)
        WHERE a.id = ANY(%s)
           OR (
               a.created_at >= b.first_seen - INTERVAL '24 hours'
               AND a.created_at <= b.last_seen + INTERVAL '24 hours'
           )
        ORDER BY a.id
        """,
        (sorted(source_ips), *cte_params, list(alert_ids)),
    )


def fetch_dependency_report(cur, alert_ids: tuple[int, ...]) -> dict[str, list[dict[str, Any]]]:
    return {
        table: _fetch_dicts(cur, query, (list(alert_ids),))
        for table, query in DEPENDENCY_QUERIES.items()
    }


def _is_benign_monitor_dependency(table: str, row: dict[str, Any]) -> bool:
    joined_text = " ".join(str(value or "") for value in row.values())
    has_synthetic_text = bool(re.search(SYNTHETIC_TEXT_EVIDENCE_REGEX, joined_text, re.I))
    if table == "alert_notes":
        return has_synthetic_text
    if table not in BENIGN_MONITOR_DEPENDENCY_TABLES:
        return False
    action = str(row.get("action") or row.get("selected_action") or row.get("requested_action") or "").lower()
    if action not in {"monitor", "escalate", "escalation", "simulated_escalation"}:
        return False
    if action != "monitor" and not has_synthetic_text:
        return False
    if table == "soar_response_outcome_events":
        return str(row.get("execution_mode") or "").lower() in {"observed", "simulation", "tracking_only", "read_only"}
    return True


def _find_unpaired_selected_alerts(alerts: list[dict[str, Any]], events: list[dict[str, Any]]) -> list[int]:
    event_source_ips = {str(row["source_ip"]) for row in events}
    return [int(row["id"]) for row in alerts if str(row["source_ip"]) not in event_source_ips]


def _unexpected_dependency_counts(dependencies: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    unexpected = {}
    for table, rows in dependencies.items():
        unexpected_count = sum(1 for row in rows if not _is_benign_monitor_dependency(table, row))
        if unexpected_count:
            unexpected[table] = unexpected_count
    return unexpected


def build_cleanup_report(
    conn,
    *,
    alert_ids: tuple[int, ...] | None = None,
    source_ips: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    alert_ids = normalize_confirmed_synthetic_alert_ids(alert_ids)
    source_ips = tuple(sorted(source_ips or CONFIRMED_SYNTHETIC_CLEANUP_SOURCE_IPS))
    with conn.cursor() as cur:
        events = fetch_synthetic_event_rows(cur, source_ips=source_ips)
        alerts = fetch_alert_rows_for_synthetic_events(cur, alert_ids=alert_ids, source_ips=source_ips)
        dependencies = fetch_dependency_report(cur, tuple(row["id"] for row in alerts))
        found_alert_ids = {int(row["id"]) for row in alerts}
        dependency_counts = {table: len(rows) for table, rows in dependencies.items()}
        benign_monitor_dependency_counts = {
            table: sum(1 for row in rows if _is_benign_monitor_dependency(table, row))
            for table, rows in dependencies.items()
        }
        benign_monitor_dependency_counts = {
            table: count for table, count in benign_monitor_dependency_counts.items() if count
        }
        refusal_reasons = []
        missing_alert_ids = [alert_id for alert_id in alert_ids if alert_id not in found_alert_ids]
        unpaired_alert_ids = _find_unpaired_selected_alerts(alerts, events)
        if alerts and not events:
            refusal_reasons.append({"code": "selected_alerts_without_synthetic_events"})
        if unpaired_alert_ids:
            refusal_reasons.append({"code": "selected_alerts_without_matching_events", "alert_ids": unpaired_alert_ids})
        unexpected_dependencies = _unexpected_dependency_counts(dependencies)
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
            "benign_monitor_dependency_counts": benign_monitor_dependency_counts,
            "missing_configured_alert_ids": missing_alert_ids,
            "refusal_reasons": refusal_reasons,
            "would_delete": {
                "alerts": len(alerts),
                "events": len(events),
            },
        }


def write_backup(report: dict[str, Any], backup_dir: str | Path) -> Path:
    backup_path = _resolve_backup_path(backup_dir)
    backup_path.mkdir(parents=True, exist_ok=True)
    output_path = backup_path / (
        f"confirmed_synthetic_dashboard_cleanup_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    output_path.write_text(json.dumps(report, indent=2, default=_json_default) + "\n", encoding="utf-8")
    return output_path


def _resolve_backup_path(backup_dir: str | Path) -> Path:
    backup_path = Path(backup_dir)
    if not backup_path.is_absolute():
        backup_path = REPO_ROOT / backup_path
    resolved_backup_path = backup_path.resolve()
    allowed_root = (REPO_ROOT / DEFAULT_BACKUP_DIR).resolve()
    if resolved_backup_path != allowed_root and allowed_root not in resolved_backup_path.parents:
        raise ValueError(f"backup_dir must stay under {allowed_root}")
    return resolved_backup_path


def execute_cleanup(
    conn,
    *,
    execute: bool = False,
    confirm: str | None = None,
    backup_dir: str | Path = DEFAULT_BACKUP_DIR,
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
    parser.add_argument("--backup-dir", default=DEFAULT_BACKUP_DIR)
    args = parser.parse_args()

    from core.db import get_db_connection

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
