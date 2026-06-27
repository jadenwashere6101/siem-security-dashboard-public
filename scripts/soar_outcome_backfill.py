#!/usr/bin/env python3
"""Plan or apply SOAR response outcome backfill.

Default mode is dry-run. Write mode requires explicit --apply.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import Json

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core import soar_response_outcomes as outcomes
from core.soar_response_outcomes_legacy import LegacyMappingResult


@dataclass
class BackfillApplyResult:
    decisions_created: int = 0
    decisions_existing: int = 0
    events_created: int = 0
    events_existing: int = 0
    legacy_rows_linked: Counter = field(default_factory=Counter)
    audit_rows_linked: int = 0
    skipped_observed_only: int = 0
    skipped_existing_linkage: int = 0
    ambiguous_written: int = 0

    def summary_lines(self) -> list[str]:
        lines = [
            "SOAR outcome backfill apply summary",
            "===================================",
            f"Decisions created: {self.decisions_created}",
            f"Decisions reused: {self.decisions_existing}",
            f"Outcome events created: {self.events_created}",
            f"Outcome events reused: {self.events_existing}",
            f"Observed-only skipped: {self.skipped_observed_only}",
            f"Existing-linkage skipped: {self.skipped_existing_linkage}",
            f"Ambiguous/conservative records written: {self.ambiguous_written}",
            f"Audit rows linked: {self.audit_rows_linked}",
            "",
            "Legacy rows linked:",
        ]
        if self.legacy_rows_linked:
            for table, count in sorted(self.legacy_rows_linked.items()):
                lines.append(f"  - {table}: {count}")
        else:
            lines.append("  - none")
        return lines


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Plan or apply SOAR response outcome backfill."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan legacy tables and print a backfill plan without writing rows.",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Write idempotent canonical decisions/events for eligible legacy rows.",
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="PostgreSQL DSN. Defaults to DATABASE_URL.",
    )
    return parser.parse_args(argv)


def _fetch_decision_by_correlation_id(conn, soar_correlation_id: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, soar_correlation_id
            FROM soar_response_decisions
            WHERE soar_correlation_id = %s
            """,
            (soar_correlation_id,),
        )
        row = cur.fetchone()
    return {"id": row[0], "soar_correlation_id": row[1]} if row else None


def _fetch_event_by_idempotency_key(conn, idempotency_key: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, idempotency_key
            FROM soar_response_outcome_events
            WHERE idempotency_key = %s
            """,
            (idempotency_key,),
        )
        row = cur.fetchone()
    return {"id": row[0], "idempotency_key": row[1]} if row else None


def _create_or_get_decision(conn, mapping: LegacyMappingResult) -> tuple[dict[str, Any], bool]:
    existing = _fetch_decision_by_correlation_id(conn, mapping.soar_correlation_id)
    if existing is not None:
        return existing, False

    decision = outcomes.create_response_decision(
        conn,
        selected_action=mapping.selected_action or "legacy_response",
        decision_source=mapping.decision_source,
        outcome_summary=mapping.outcome_summary,
        alert_id=mapping.alert_id,
        incident_id=mapping.incident_id,
        source_ip=mapping.source_ip,
        reason_code=mapping.reason_code,
        soar_correlation_id=mapping.soar_correlation_id,
        playbook_execution_id=mapping.playbook_execution_id,
        queue_id=mapping.queue_id,
        approval_request_id=mapping.approval_request_id,
        safe_metadata={
            "source_table": mapping.source_table,
            "source_id": mapping.source_id,
            "needs_review": mapping.needs_review,
            "ambiguity_reason": mapping.ambiguity_reason,
        },
    )
    return decision, True


def _append_or_get_event(
    conn,
    mapping: LegacyMappingResult,
    decision: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    idempotency_key = mapping._proposed_idempotency_keys()["latest_event"]
    existing = _fetch_event_by_idempotency_key(conn, idempotency_key)
    if existing is not None:
        return existing, False

    event = outcomes.append_outcome_event(
        conn,
        decision_id=decision["id"],
        soar_correlation_id=decision["soar_correlation_id"],
        event_type="legacy_backfill",
        execution_mode=mapping.execution_mode,
        execution_state=mapping.execution_state,
        external_executed=mapping.external_executed,
        tracking_recorded=mapping.tracking_recorded,
        simulated=mapping.simulated,
        execution_actor=mapping.execution_actor,
        reason_code=mapping.reason_code,
        outcome_summary=mapping.outcome_summary,
        alert_id=mapping.alert_id,
        incident_id=mapping.incident_id,
        source_ip=mapping.source_ip,
        queue_id=mapping.queue_id,
        playbook_execution_id=mapping.playbook_execution_id,
        approval_request_id=mapping.approval_request_id,
        notification_delivery_attempt_id=mapping.notification_delivery_attempt_id,
        response_action_log_id=mapping.response_action_log_id,
        idempotency_key=idempotency_key,
        metadata={
            "source_table": mapping.source_table,
            "source_id": mapping.source_id,
            "needs_review": mapping.needs_review,
            "ambiguous": mapping.ambiguous,
            "ambiguity_reason": mapping.ambiguity_reason,
        },
    )
    return event, True


def _link_legacy_row(
    conn,
    mapping: LegacyMappingResult,
    decision: dict[str, Any],
) -> bool:
    table_and_id = {
        "response_actions_queue": ("response_actions_queue", mapping.queue_id),
        "response_actions_log": ("response_actions_log", mapping.response_action_log_id),
        "playbook_executions": ("playbook_executions", mapping.playbook_execution_id),
        "approval_requests": ("approval_requests", mapping.approval_request_id),
        "notification_delivery_attempts": (
            "notification_delivery_attempts",
            mapping.notification_delivery_attempt_id,
        ),
    }.get(mapping.source_table)
    if table_and_id is None:
        return False

    table, row_id = table_and_id
    if row_id is None:
        return False
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE {table}
            SET decision_id = COALESCE(decision_id, %s),
                soar_correlation_id = COALESCE(soar_correlation_id, %s)
            WHERE id = %s
              AND (decision_id IS NULL OR soar_correlation_id IS NULL)
            """,
            (decision["id"], decision["soar_correlation_id"], row_id),
        )
        return cur.rowcount > 0


def _legacy_mappings(conn) -> list[LegacyMappingResult]:
    mappings: list[LegacyMappingResult] = []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, alert_id, host(source_ip), action, status, last_error, decision_id
            FROM response_actions_queue
            ORDER BY id
            """
        )
        for queue_id, alert_id, source_ip, action, status, last_error, decision_id in cur.fetchall():
            if decision_id is None:
                mappings.append(
                    outcomes.infer_queue_legacy_outcome(
                        queue_id=queue_id,
                        alert_id=alert_id,
                        source_ip=source_ip,
                        action=action,
                        status=status,
                        last_error=last_error,
                    )
                )

        cur.execute(
            """
            SELECT l.id, l.alert_id, host(l.source_ip), l.action, l.status, l.details, l.decision_id
            FROM response_actions_log l
            ORDER BY l.id
            """
        )
        for log_id, alert_id, source_ip, action, status, details, decision_id in cur.fetchall():
            if decision_id is not None:
                continue
            blocked_ip_exists = False
            if alert_id is not None and action == "block_ip":
                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM blocked_ips
                        WHERE source_alert_id = %s AND status = 'active'
                    )
                    """,
                    (alert_id,),
                )
                blocked_ip_exists = bool(cur.fetchone()[0])
            mappings.append(
                outcomes.infer_response_log_legacy_outcome(
                    log_id=log_id,
                    alert_id=alert_id,
                    source_ip=source_ip,
                    action=action,
                    status=status,
                    details=details,
                    blocked_ip_exists=blocked_ip_exists,
                )
            )

        cur.execute(
            """
            SELECT id, alert_id, incident_id, playbook_id, status, steps_log, failure_reason,
                   decision_id
            FROM playbook_executions
            ORDER BY id
            """
        )
        for row in cur.fetchall():
            if row[7] is not None:
                continue
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM notification_delivery_attempts
                    WHERE playbook_execution_id = %s
                      AND mode = 'real'
                      AND status = 'success'
                      AND metadata->>'executed' = 'true'
                      AND metadata->>'simulated' = 'false'
                      AND (
                        metadata->>'adapter_mode' = 'real'
                        OR metadata->>'mode' = 'real'
                        OR metadata->>'delivery' IN ('sent', 'delivered', 'accepted', 'success')
                        OR (
                            metadata ? 'http_status'
                            AND (metadata->>'http_status') ~ '^[0-9]+$'
                            AND (metadata->>'http_status')::integer BETWEEN 200 AND 299
                        )
                      )
                )
                """,
                (row[0],),
            )
            mappings.append(
                outcomes.infer_playbook_execution_legacy_outcome(
                    execution_id=row[0],
                    alert_id=row[1],
                    incident_id=row[2],
                    playbook_id=row[3],
                    status=row[4],
                    steps_log=row[5],
                    failure_reason=row[6],
                    real_notification_confirmed=bool(cur.fetchone()[0]),
                )
            )

        cur.execute(
            """
            SELECT id, incident_id, queue_id, playbook_execution_id, action, status,
                   request_reason, decision_id
            FROM approval_requests
            ORDER BY id
            """
        )
        for row in cur.fetchall():
            if row[7] is not None:
                continue
            alert_id = None
            if row[2] is not None:
                cur.execute("SELECT alert_id FROM response_actions_queue WHERE id = %s", (row[2],))
                found = cur.fetchone()
                alert_id = found[0] if found else None
            elif row[3] is not None:
                cur.execute("SELECT alert_id FROM playbook_executions WHERE id = %s", (row[3],))
                found = cur.fetchone()
                alert_id = found[0] if found else None
            mappings.append(
                outcomes.infer_approval_request_legacy_outcome(
                    approval_request_id=row[0],
                    alert_id=alert_id,
                    incident_id=row[1],
                    queue_id=row[2],
                    playbook_execution_id=row[3],
                    action=row[4],
                    status=row[5],
                    request_reason=row[6],
                )
            )

        cur.execute(
            """
            SELECT id, alert_id, incident_id, playbook_execution_id, approval_request_id,
                   action, mode, status, metadata, failure_message, decision_id
            FROM notification_delivery_attempts
            ORDER BY id
            """
        )
        for row in cur.fetchall():
            if row[10] is not None:
                continue
            mappings.append(
                outcomes.infer_notification_delivery_legacy_outcome(
                    attempt_id=row[0],
                    alert_id=row[1],
                    incident_id=row[2],
                    playbook_execution_id=row[3],
                    approval_request_id=row[4],
                    action=row[5],
                    mode=row[6],
                    status=row[7],
                    metadata=row[8],
                    failure_message=row[9],
                )
            )
    return mappings


def _link_relevant_audit_rows(conn) -> int:
    linked = 0
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, event_type, details
            FROM audit_log
            WHERE event_type IN (
                'PLAYBOOK_EXECUTION_RETRY',
                'PLAYBOOK_EXECUTION_ABANDON',
                'PLAYBOOK_EXECUTION_RESUME',
                'PLAYBOOK_EXECUTION_PERMANENTLY_FAIL'
            )
            ORDER BY id
            """
        )
        rows = cur.fetchall()
        for audit_id, event_type, details in rows:
            details = details if isinstance(details, dict) else {}
            if details.get("decision_id") or details.get("soar_correlation_id"):
                continue
            execution_id = (
                details.get("execution_id")
                or details.get("source_execution_id")
                or details.get("new_execution_id")
            )
            if execution_id is None:
                continue
            cur.execute(
                """
                SELECT decision_id, soar_correlation_id, alert_id, incident_id
                FROM playbook_executions
                WHERE id = %s
                  AND decision_id IS NOT NULL
                  AND soar_correlation_id IS NOT NULL
                """,
                (execution_id,),
            )
            execution = cur.fetchone()
            if execution is None:
                continue
            decision_id, correlation_id, alert_id, incident_id = execution
            event_id = _append_or_get_audit_link_event(
                conn,
                audit_id=audit_id,
                event_type=event_type,
                decision_id=decision_id,
                soar_correlation_id=correlation_id,
                alert_id=alert_id,
                incident_id=incident_id,
                playbook_execution_id=int(execution_id),
            )
            cur.execute(
                """
                UPDATE audit_log
                SET details = COALESCE(details, '{}'::jsonb) || %s
                WHERE id = %s
                  AND NOT (COALESCE(details, '{}'::jsonb) ? 'decision_id')
                  AND NOT (COALESCE(details, '{}'::jsonb) ? 'soar_correlation_id')
                """,
                (
                    Json(
                        {
                            "decision_id": decision_id,
                            "soar_correlation_id": correlation_id,
                            "latest_outcome_event_id": event_id,
                        }
                    ),
                    audit_id,
                ),
            )
            if cur.rowcount:
                linked += 1
    return linked


def _append_or_get_audit_link_event(
    conn,
    *,
    audit_id: int,
    event_type: str,
    decision_id: int,
    soar_correlation_id: str,
    alert_id: int | None,
    incident_id: int | None,
    playbook_execution_id: int,
) -> int:
    key = f"legacy-backfill-audit_log-{audit_id}-event-latest"
    existing = _fetch_event_by_idempotency_key(conn, key)
    if existing is not None:
        return int(existing["id"])
    event = outcomes.append_outcome_event(
        conn,
        decision_id=decision_id,
        soar_correlation_id=soar_correlation_id,
        event_type="audit_link",
        execution_mode="simulation",
        execution_state="selected",
        external_executed=False,
        tracking_recorded=False,
        simulated=False,
        execution_actor="system",
        reason_code=None,
        outcome_summary=f"Linked audit log row {audit_id} ({event_type}) to canonical SOAR lifecycle.",
        alert_id=alert_id,
        incident_id=incident_id,
        playbook_execution_id=playbook_execution_id,
        idempotency_key=key,
        metadata={"audit_log_id": audit_id, "audit_event_type": event_type},
    )
    return int(event["id"])


def apply_backfill(conn) -> BackfillApplyResult:
    result = BackfillApplyResult()
    for mapping in _legacy_mappings(conn):
        if not mapping.proposed_decision or not mapping.selected_action:
            result.skipped_observed_only += 1
            continue
        decision, created_decision = _create_or_get_decision(conn, mapping)
        if created_decision:
            result.decisions_created += 1
        else:
            result.decisions_existing += 1
        event, created_event = _append_or_get_event(conn, mapping, decision)
        if created_event:
            result.events_created += 1
        else:
            result.events_existing += 1
        if mapping.needs_review or mapping.ambiguous:
            result.ambiguous_written += int(created_event)
        if _link_legacy_row(conn, mapping, decision):
            result.legacy_rows_linked[mapping.source_table] += 1
        else:
            result.skipped_existing_linkage += 1

    result.audit_rows_linked = _link_relevant_audit_rows(conn)
    return result


def main(argv=None) -> int:
    args = parse_args(argv)
    db_url = args.db_url or os.getenv("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL or --db-url is required.", file=sys.stderr)
        return 1

    conn = psycopg2.connect(db_url)
    try:
        plan = outcomes.plan_backfill_dry_run(conn)
        print(outcomes.format_backfill_plan_summary(plan))
        if not args.apply:
            return 0

        print("")
        print("Applying write-mode backfill (--apply requested).")
        result = apply_backfill(conn)
        conn.commit()
        print("\n".join(result.summary_lines()))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
