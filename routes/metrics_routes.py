"""
Read-only SOAR playbook execution metrics.

Aggregates from playbook_executions (and approval linkage counts only). No executor,
queue, adapter, or ingest paths.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from flask import Blueprint, current_app, jsonify
from flask_login import login_required

from core.approval_store import list_approval_requests
from core.auth import analyst_or_super_admin_required
from core import dead_letter_store
from core.db import get_db_connection
from core.playbook_store import list_playbook_executions
from core.soar_response_outcomes import (
    get_canonical_outcome_retention_policy,
    get_outcome_count_groups,
)

metrics_bp = Blueprint("metrics", __name__)

KNOWN_EXECUTION_STATUSES: tuple[str, ...] = (
    "pending",
    "running",
    "awaiting_approval",
    "success",
    "failed",
    "abandoned",
    "not_actioned",
)

KNOWN_NOTIFICATION_MODES: tuple[str, ...] = ("simulation", "real")
KNOWN_NOTIFICATION_STATUSES: tuple[str, ...] = ("pending", "success", "failed", "timeout", "blocked")
KNOWN_CIRCUIT_BREAKER_STATES: tuple[str, ...] = (
    "closed",
    "open",
    "half_open",
    "unknown",
    "invalid",
)
# spec: SPEC-NOTIFY-001
KNOWN_RECENT_NOTIFICATION_BUCKETS: tuple[str, ...] = ("success", "failed", "timeout", "blocked")
KNOWN_INCIDENT_STATUSES: tuple[str, ...] = ("open", "investigating", "resolved", "closed")
KNOWN_INCIDENT_SEVERITIES: tuple[str, ...] = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
KNOWN_APPROVAL_STATUSES: tuple[str, ...] = ("pending", "approved", "denied", "expired")
RECENT_WINDOW_HOURS = 24
SOAR_OPERATIONS_WINDOW_HOURS = 24
SOAR_OPERATIONS_PREVIEW_LIMIT = 5
EXPECTED_APPROVAL_FAILURE_CLASSES = frozenset({"approval_expired", "approval_denied"})


def _attach_canonical_outcome_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    payload["canonical_outcome_retention"] = get_canonical_outcome_retention_policy()
    return payload


def _empty_by_status() -> dict[str, int]:
    return {s: 0 for s in KNOWN_EXECUTION_STATUSES}


def _empty_counts(keys: tuple[str, ...]) -> dict[str, int]:
    return {k: 0 for k in keys}


def _build_playbook_metrics(rows_by_playbook_status: list[tuple[str, str, int]]) -> list[dict[str, Any]]:
    """Rows: (playbook_id, status, count)."""
    totals: dict[str, int] = {}
    by_pb: dict[str, dict[str, int]] = {}

    for playbook_id, status, cnt in rows_by_playbook_status:
        if playbook_id not in by_pb:
            by_pb[playbook_id] = _empty_by_status()
        totals[playbook_id] = totals.get(playbook_id, 0) + cnt
        if status in KNOWN_EXECUTION_STATUSES:
            by_pb[playbook_id][status] = cnt

    out: list[dict[str, Any]] = []
    for playbook_id in sorted(totals.keys()):
        entry: dict[str, Any] = {
            "playbook_id": playbook_id,
            "total": totals[playbook_id],
            "by_status": {**by_pb.get(playbook_id, _empty_by_status())},
        }
        known_sum = sum(entry["by_status"].values())
        if entry["total"] > known_sum:
            entry["other_status_count"] = entry["total"] - known_sum
        out.append(entry)
    return out


def _build_count_map(rows: list[tuple[Any, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key, cnt in rows:
        label = str(key) if key is not None else "(null)"
        counts[label] = counts.get(label, 0) + int(cnt)
    return counts


def _merge_known_counts(rows: list[tuple[Any, Any]], known_keys: tuple[str, ...]) -> tuple[dict[str, int], dict[str, int]]:
    counts = _empty_counts(known_keys)
    unknown: dict[str, int] = {}
    for key, cnt in rows:
        label = str(key) if key is not None else ""
        c = int(cnt)
        if label in counts:
            counts[label] = c
        else:
            unknown[label or "(null)"] = unknown.get(label or "(null)", 0) + c
    return counts, unknown


def _iso_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _parse_datetime(value: Any):
    if value is None:
        return None
    if hasattr(value, "timestamp"):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _list_all_approval_requests(conn, *, status: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    offset = 0
    page_size = 100
    while True:
        batch = list_approval_requests(
            conn,
            status=status,
            limit=page_size,
            offset=offset,
        )
        items.extend(batch)
        if len(batch) < page_size:
            break
        offset += len(batch)
    return items


def _list_all_dead_letters(conn, *, status: str | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    offset = 0
    page_size = 500
    while True:
        batch = dead_letter_store.list_dead_letters(
            conn,
            status=status,
            limit=page_size,
            offset=offset,
        )
        items.extend(batch)
        if len(batch) < page_size:
            break
        offset += len(batch)
    return items


def _approval_terminal_timestamp(approval: dict[str, Any]):
    decided_at = _parse_datetime(approval.get("decided_at"))
    if decided_at is not None:
        return decided_at
    expires_at = _parse_datetime(approval.get("expires_at"))
    if expires_at is not None:
        return expires_at
    return _parse_datetime(approval.get("created_at"))


def _format_execution_preview(execution: dict[str, Any]) -> dict[str, Any]:
    return {
        "execution_id": execution["id"],
        "playbook_id": execution.get("playbook_id"),
        "status": execution.get("status"),
        "alert_id": execution.get("alert_id"),
        "incident_id": execution.get("incident_id"),
        "created_at": _iso_timestamp(execution.get("created_at")),
        "completed_at": _iso_timestamp(execution.get("completed_at")),
        "failure_reason": execution.get("failure_reason"),
    }


def _classify_dead_letter_preview(item: dict[str, Any]) -> dict[str, Any]:
    failure_class = str(item.get("failure_class") or "").strip()
    if failure_class == "approval_expired":
        return {"kind": "expected_expiration", "label": "Expected expiration"}
    if failure_class == "approval_denied":
        return {"kind": "expected_denial", "label": "Expected denial"}
    return {"kind": "system_failure", "label": "System failure"}


def _format_dead_letter_preview(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "dead_letter_id": item.get("id"),
        "status": item.get("status"),
        "source_type": item.get("source_type"),
        "execution_id": item.get("execution_id"),
        "incident_id": item.get("incident_id"),
        "alert_id": item.get("alert_id"),
        "failure_class": item.get("failure_class"),
        "retryable": item.get("retryable"),
        "created_at": _iso_timestamp(item.get("created_at")),
        "classification": _classify_dead_letter_preview(item),
    }


def _format_approval_preview(
    approval: dict[str, Any],
    execution_map: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    execution_id = approval.get("playbook_execution_id")
    execution = execution_map.get(execution_id) if execution_id is not None else None
    return {
        "approval_id": approval.get("id"),
        "status": approval.get("status"),
        "action": approval.get("action"),
        "risk_level": approval.get("risk_level"),
        "incident_id": approval.get("incident_id"),
        "queue_id": approval.get("queue_id"),
        "playbook_execution_id": execution_id,
        "playbook_step_index": approval.get("playbook_step_index"),
        "execution_status": execution.get("status") if execution else None,
        "alert_id": execution.get("alert_id") if execution else None,
        "playbook_id": execution.get("playbook_id") if execution else None,
        "request_reason": approval.get("request_reason"),
        "decision_comment": approval.get("decision_comment"),
        "created_at": _iso_timestamp(approval.get("created_at")),
        "decided_at": _iso_timestamp(approval.get("decided_at")),
        "expires_at": _iso_timestamp(approval.get("expires_at")),
    }


def _build_soar_operations_summary(conn) -> dict[str, Any]:
    executions = list_playbook_executions(conn, limit=1000000)
    execution_map = {int(row["id"]): row for row in executions if row.get("id") is not None}

    running_executions = [row for row in executions if row.get("status") == "running"]
    awaiting_approval_executions = [
        row for row in executions if row.get("status") == "awaiting_approval"
    ]
    failed_executions = [row for row in executions if row.get("status") == "failed"]

    pending_approvals = _list_all_approval_requests(conn, status="pending")
    denied_approvals = _list_all_approval_requests(conn, status="denied")
    expired_approvals = _list_all_approval_requests(conn, status="expired")

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=SOAR_OPERATIONS_WINDOW_HOURS)

    recent_terminal_approvals = []
    for approval in [*denied_approvals, *expired_approvals]:
        terminal_at = _approval_terminal_timestamp(approval)
        if terminal_at is None or terminal_at < window_start:
            continue
        recent_terminal_approvals.append((terminal_at, approval))
    recent_terminal_approvals.sort(key=lambda item: item[0], reverse=True)

    active_dead_letter_metrics = dead_letter_store.get_dead_letter_metrics(conn)
    actionable_dead_letters = _list_all_dead_letters(conn, status="open")

    expected_backlog_count = sum(
        1
        for item in actionable_dead_letters
        if str(item.get("failure_class") or "").strip() in EXPECTED_APPROVAL_FAILURE_CLASSES
    )

    return {
        "window_hours": SOAR_OPERATIONS_WINDOW_HOURS,
        "counts": {
            "running_playbooks": len(running_executions),
            "awaiting_approval_playbooks": len(awaiting_approval_executions),
            "active_playbooks": len(running_executions) + len(awaiting_approval_executions),
            "pending_approvals": len(pending_approvals),
            "recently_expired_denied": len(recent_terminal_approvals),
            "failed_executions": len(failed_executions),
            "actionable_dead_letters": len(actionable_dead_letters),
        },
        "running_playbooks": {
            "count": len(running_executions) + len(awaiting_approval_executions),
            "running_count": len(running_executions),
            "awaiting_approval_count": len(awaiting_approval_executions),
            "items": [
                _format_execution_preview(row)
                for row in [*running_executions, *awaiting_approval_executions][
                    :SOAR_OPERATIONS_PREVIEW_LIMIT
                ]
            ],
        },
        "pending_approvals": {
            "count": len(pending_approvals),
            "items": [
                _format_approval_preview(approval, execution_map)
                for approval in pending_approvals[:SOAR_OPERATIONS_PREVIEW_LIMIT]
            ],
        },
        "recently_expired_denied": {
            "count": len(recent_terminal_approvals),
            "window_hours": SOAR_OPERATIONS_WINDOW_HOURS,
            "items": [
                _format_approval_preview(approval, execution_map)
                for _, approval in recent_terminal_approvals[:SOAR_OPERATIONS_PREVIEW_LIMIT]
            ],
        },
        "failed_executions": {
            "count": len(failed_executions),
            "items": [
                _format_execution_preview(row)
                for row in failed_executions[:SOAR_OPERATIONS_PREVIEW_LIMIT]
            ],
        },
        "actionable_dead_letters": {
            "count": len(actionable_dead_letters),
            "open_count": int(active_dead_letter_metrics.get("open") or 0),
            "items": [
                _format_dead_letter_preview(item)
                for item in actionable_dead_letters[:SOAR_OPERATIONS_PREVIEW_LIMIT]
            ],
        },
        "legacy_expected_backlog": {
            "open_count": expected_backlog_count,
            "review_mode": "individual_reason_logged_dismissal_only",
        },
    }


def _build_playbook_worker_snapshot(cur) -> dict[str, Any]:
    cur.execute(
        """
        SELECT status, COUNT(*)
        FROM playbook_executions
        GROUP BY status
        """
    )
    by_status, unknown_statuses = _merge_known_counts(
        cur.fetchall() or [],
        KNOWN_EXECUTION_STATUSES,
    )

    cur.execute(
        """
        SELECT
            COUNT(*) FILTER (WHERE status = 'running') AS running_total,
            COUNT(*) FILTER (
                WHERE status = 'running'
                  AND lease_owner IS NOT NULL
                  AND lease_expires_at IS NOT NULL
                  AND lease_expires_at >= NOW()
            ) AS active_leased,
            COUNT(*) FILTER (
                WHERE status = 'running'
                  AND lease_expires_at IS NOT NULL
                  AND lease_expires_at < NOW()
            ) AS stale_running,
            COUNT(*) FILTER (
                WHERE status = 'running'
                  AND (lease_owner IS NULL OR lease_expires_at IS NULL)
            ) AS missing_lease
        FROM playbook_executions
        """
    )
    running_row = cur.fetchone() or (0, 0, 0, 0)
    running_total = int(running_row[0] or 0)
    active_leased = int(running_row[1] or 0)
    stale_running = int(running_row[2] or 0)
    missing_lease = int(running_row[3] or 0)

    cur.execute(
        """
        SELECT
            COALESCE(SUM(recovery_count), 0),
            COUNT(*) FILTER (WHERE recovery_count > 0)
        FROM playbook_executions
        """
    )
    recovery_row = cur.fetchone() or (0, 0)
    total_recovery_count = int(recovery_row[0] or 0)
    recovered_execution_count = int(recovery_row[1] or 0)

    cur.execute(
        """
        SELECT COUNT(*)
        FROM playbook_executions
        WHERE status = 'failed'
          AND COALESCE(completed_at, created_at)
              >= NOW() - %s * INTERVAL '1 hour'
        """,
        (RECENT_WINDOW_HOURS,),
    )
    recent_failed_executions = int(cur.fetchone()[0])

    cur.execute(
        """
        SELECT
            COUNT(*) FILTER (WHERE status IN ('open', 'retrying')) AS active_dead_letters,
            COUNT(*) FILTER (
                WHERE source_type = 'playbook_execution'
                  AND status IN ('open', 'retrying')
            ) AS active_playbook_dead_letters
        FROM soar_dead_letters
        """
    )
    dead_letter_row = cur.fetchone() or (0, 0)
    active_dead_letters = int(dead_letter_row[0] or 0)
    active_playbook_dead_letters = int(dead_letter_row[1] or 0)

    active_total = by_status["pending"] + by_status["running"] + by_status["awaiting_approval"]
    payload: dict[str, Any] = {
        "daemon_health": {
            "status": "unknown",
            "source": "database_snapshot",
            "worker_heartbeat_available": False,
            "message": "Worker process heartbeat is not persisted yet; DB queue health is available.",
        },
        "queue_depth": {
            "pending": by_status["pending"],
            "running": by_status["running"],
            "awaiting_approval": by_status["awaiting_approval"],
            "active_total": active_total,
        },
        "running": {
            "total": running_total,
            "active_leased": active_leased,
            "stale": stale_running,
            "missing_lease": missing_lease,
        },
        "stale_running_count": stale_running,
        "pending_execution_count": by_status["pending"],
        "running_execution_count": by_status["running"],
        "recent": {
            "window_hours": RECENT_WINDOW_HOURS,
            "failed_executions": recent_failed_executions,
            "active_dead_letters": active_dead_letters,
            "active_playbook_dead_letters": active_playbook_dead_letters,
        },
        "recovery": {
            "last_recovery_summary_available": False,
            "last_recovery_summary": None,
            "total_recovery_count": total_recovery_count,
            "recovered_execution_count": recovered_execution_count,
        },
    }
    if unknown_statuses:
        payload["unknown_statuses"] = unknown_statuses
    return payload


@metrics_bp.route("/metrics/playbooks", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def playbook_execution_metrics_route():
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM playbook_executions")
            total_row = cur.fetchone()
            total_executions = int(total_row[0]) if total_row and total_row[0] is not None else 0

            cur.execute(
                """
                SELECT status, COUNT(*)
                FROM playbook_executions
                GROUP BY status
                """
            )
            status_rows = cur.fetchall() or []

            by_status = _empty_by_status()
            unknown_statuses: dict[str, int] = {}
            for status, cnt in status_rows:
                c = int(cnt)
                s = str(status) if status is not None else ""
                if s in KNOWN_EXECUTION_STATUSES:
                    by_status[s] = c
                else:
                    unknown_statuses[s or "(null)"] = unknown_statuses.get(s or "(null)", 0) + c

            cur.execute(
                """
                SELECT playbook_id, status, COUNT(*)
                FROM playbook_executions
                GROUP BY playbook_id, status
                ORDER BY playbook_id ASC, status ASC
                """
            )
            pb_rows = cur.fetchall() or []
            by_playbook_id = _build_playbook_metrics(
                [(str(r[0]), str(r[1]) if r[1] is not None else "", int(r[2])) for r in pb_rows]
            )

            cur.execute(
                """
                SELECT COUNT(*)
                FROM playbook_executions
                WHERE status = 'success'
                  AND COALESCE(completed_at, created_at)
                      >= NOW() - %s * INTERVAL '1 hour'
                """,
                (RECENT_WINDOW_HOURS,),
            )
            recent_success = int(cur.fetchone()[0])

            cur.execute(
                """
                SELECT COUNT(*)
                FROM playbook_executions
                WHERE status = 'failed'
                  AND COALESCE(completed_at, created_at)
                      >= NOW() - %s * INTERVAL '1 hour'
                """,
                (RECENT_WINDOW_HOURS,),
            )
            recent_failed = int(cur.fetchone()[0])

            awaiting = by_status["awaiting_approval"]

            cur.execute(
                """
                SELECT COUNT(DISTINCT pe.id)
                FROM playbook_executions pe
                INNER JOIN approval_requests ar
                    ON ar.playbook_execution_id = pe.id
                """
            )
            with_linked_approval = int(cur.fetchone()[0])

            # spec: SPEC-METRICS-001
            cur.execute(
                """
                SELECT COUNT(*)
                FROM playbook_executions
                WHERE status = 'running'
                  AND lease_expires_at IS NOT NULL
                  AND lease_expires_at < NOW()
                """
            )
            stale_running_count = int(cur.fetchone()[0])
            canonical_outcome_counts = get_outcome_count_groups(conn)

        payload: dict[str, Any] = {
            "total_executions": total_executions,
            "by_status": by_status,
            "by_playbook_id": by_playbook_id,
            "recent": {
                "window_hours": RECENT_WINDOW_HOURS,
                "success": recent_success,
                "failed": recent_failed,
                "time_basis": "Rows are included when COALESCE(completed_at, created_at) "
                f"falls within the last {RECENT_WINDOW_HOURS} hours (UTC).",
            },
            "approval_gated": {
                "awaiting_approval": awaiting,
                "with_linked_approval": with_linked_approval,
            },
            "stale_running_count": stale_running_count,
            "canonical_outcome_counts": canonical_outcome_counts,
        }
        if unknown_statuses:
            payload["unknown_statuses"] = unknown_statuses

        return jsonify(_attach_canonical_outcome_metadata(payload)), 200
    except Exception as error:
        current_app.logger.error("Error in playbook_execution_metrics_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@metrics_bp.route("/metrics/playbook-worker", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def playbook_worker_metrics_route():
    # spec: SPEC-WORKER-001 / SPEC-UI-004 - metrics expose real worker health, not integration enablement.
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            payload = _build_playbook_worker_snapshot(cur)
        return jsonify(payload), 200
    except Exception as error:
        current_app.logger.error("Error in playbook_worker_metrics_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@metrics_bp.route("/metrics/notifications", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def notification_delivery_metrics_route():
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM notification_delivery_attempts")
            total_row = cur.fetchone()
            total_delivery_attempts = int(total_row[0]) if total_row and total_row[0] is not None else 0

            cur.execute(
                """
                SELECT provider, COUNT(*)
                FROM notification_delivery_attempts
                GROUP BY provider
                ORDER BY provider ASC
                """
            )
            by_provider = _build_count_map(cur.fetchall() or [])

            cur.execute(
                """
                SELECT mode, COUNT(*)
                FROM notification_delivery_attempts
                GROUP BY mode
                """
            )
            by_mode, unknown_modes = _merge_known_counts(
                cur.fetchall() or [],
                KNOWN_NOTIFICATION_MODES,
            )

            cur.execute(
                """
                SELECT status, COUNT(*)
                FROM notification_delivery_attempts
                GROUP BY status
                """
            )
            by_status, unknown_statuses = _merge_known_counts(
                cur.fetchall() or [],
                KNOWN_NOTIFICATION_STATUSES,
            )

            cur.execute(
                """
                SELECT adapter_name, COUNT(*)
                FROM notification_delivery_attempts
                GROUP BY adapter_name
                ORDER BY adapter_name ASC
                """
            )
            by_adapter_name = _build_count_map(cur.fetchall() or [])

            cur.execute(
                """
                SELECT status, COUNT(*)
                FROM notification_delivery_attempts
                WHERE status IN ('success', 'failed', 'timeout', 'blocked')
                  AND COALESCE(completed_at, started_at, requested_at, created_at)
                      >= NOW() - %s * INTERVAL '1 hour'
                GROUP BY status
                """,
                (RECENT_WINDOW_HOURS,),
            )
            recent, unknown_recent = _merge_known_counts(
                cur.fetchall() or [],
                KNOWN_RECENT_NOTIFICATION_BUCKETS,
            )

            cur.execute(
                """
                SELECT circuit_breaker_state, COUNT(*)
                FROM notification_delivery_attempts
                WHERE circuit_breaker_state IS NOT NULL
                GROUP BY circuit_breaker_state
                """
            )
            circuit_breaker_state_counts, unknown_circuit_breaker_states = _merge_known_counts(
                cur.fetchall() or [],
                KNOWN_CIRCUIT_BREAKER_STATES,
            )
            canonical_outcome_counts = get_outcome_count_groups(conn)

        payload: dict[str, Any] = {
            "total_delivery_attempts": total_delivery_attempts,
            "by_provider": by_provider,
            "by_mode": by_mode,
            "by_status": by_status,
            "by_adapter_name": by_adapter_name,
            "recent": {
                "window_hours": RECENT_WINDOW_HOURS,
                **recent,
                "time_basis": "Rows are included when COALESCE(completed_at, started_at, "
                f"requested_at, created_at) falls within the last {RECENT_WINDOW_HOURS} hours (UTC).",
            },
            "circuit_breaker_state_counts": circuit_breaker_state_counts,
            "canonical_outcome_counts": canonical_outcome_counts,
        }
        if unknown_modes:
            payload["unknown_modes"] = unknown_modes
        if unknown_statuses:
            payload["unknown_statuses"] = unknown_statuses
        if unknown_recent:
            payload["unknown_recent_statuses"] = unknown_recent
        if unknown_circuit_breaker_states:
            payload["unknown_circuit_breaker_states"] = unknown_circuit_breaker_states

        return jsonify(_attach_canonical_outcome_metadata(payload)), 200
    except Exception as error:
        current_app.logger.error("Error in notification_delivery_metrics_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@metrics_bp.route("/metrics/incidents", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def incident_metrics_route():
    # spec: SPEC-METRICS-001
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, severity, COUNT(*)
                FROM incidents
                GROUP BY status, severity
                """
            )
            rows = cur.fetchall() or []

            by_status = _empty_counts(KNOWN_INCIDENT_STATUSES)
            by_severity = _empty_counts(KNOWN_INCIDENT_SEVERITIES)
            total_count = 0
            open_high_critical_count = 0

            for status, severity, cnt in rows:
                count = int(cnt)
                normalized_status = str(status) if status is not None else ""
                normalized_severity = str(severity).upper() if severity is not None else ""

                total_count += count
                if normalized_status in by_status:
                    by_status[normalized_status] += count
                if normalized_severity in by_severity:
                    by_severity[normalized_severity] += count
                if normalized_status in {"open", "investigating"} and normalized_severity in {"HIGH", "CRITICAL"}:
                    open_high_critical_count += count

            cur.execute(
                """
                SELECT MAX(created_at)
                FROM incidents
                """
            )
            newest_row = cur.fetchone()
            newest_incident_at = newest_row[0] if newest_row else None

            cur.execute(
                """
                SELECT MIN(created_at)
                FROM incidents
                WHERE status = 'open'
                """
            )
            oldest_open_row = cur.fetchone()
            oldest_open_incident_at = oldest_open_row[0] if oldest_open_row else None
            canonical_outcome_counts = get_outcome_count_groups(conn)

        return (
            jsonify(
                _attach_canonical_outcome_metadata(
                    {
                        "total_count": total_count,
                        "total": total_count,
                        "open_count": by_status["open"],
                        "by_status": by_status,
                        "by_severity": by_severity,
                        "open_high_critical_count": open_high_critical_count,
                        "open_high_critical": open_high_critical_count,
                        "newest_incident_at": _iso_timestamp(newest_incident_at),
                        "oldest_open_incident_at": _iso_timestamp(oldest_open_incident_at),
                        "canonical_outcome_counts": canonical_outcome_counts,
                    }
                )
            ),
            200,
        )
    except Exception as error:
        current_app.logger.error("Error in incident_metrics_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@metrics_bp.route("/metrics/approvals", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def approval_metrics_route():
    # spec: SPEC-METRICS-001
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, COUNT(*)
                FROM approval_requests
                GROUP BY status
                """
            )
            rows = cur.fetchall() or []

            by_status = _empty_counts(KNOWN_APPROVAL_STATUSES)
            total_count = 0
            for status, cnt in rows:
                count = int(cnt)
                normalized_status = str(status) if status is not None else ""
                total_count += count
                if normalized_status in by_status:
                    by_status[normalized_status] += count

            cur.execute(
                """
                SELECT MAX(created_at)
                FROM approval_requests
                """
            )
            newest_row = cur.fetchone()
            newest_approval_at = newest_row[0] if newest_row else None

            cur.execute(
                """
                SELECT MIN(created_at)
                FROM approval_requests
                WHERE status = 'pending'
                """
            )
            oldest_pending_row = cur.fetchone()
            oldest_pending_approval_at = oldest_pending_row[0] if oldest_pending_row else None
            canonical_outcome_counts = get_outcome_count_groups(conn)

        return (
            jsonify(
                _attach_canonical_outcome_metadata(
                    {
                        "total_count": total_count,
                        "total": total_count,
                        "by_status": by_status,
                        "pending_count": by_status["pending"],
                        "newest_approval_at": _iso_timestamp(newest_approval_at),
                        "oldest_pending_approval_at": _iso_timestamp(oldest_pending_approval_at),
                        "canonical_outcome_counts": canonical_outcome_counts,
                    }
                )
            ),
            200,
        )
    except Exception as error:
        current_app.logger.error("Error in approval_metrics_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@metrics_bp.route("/metrics/soar-operations", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def soar_operations_summary_route():
    conn = None
    try:
        conn = get_db_connection()
        return jsonify(_build_soar_operations_summary(conn)), 200
    except Exception as error:
        current_app.logger.error("Error in soar_operations_summary_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()
