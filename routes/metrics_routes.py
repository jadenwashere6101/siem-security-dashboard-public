"""
Read-only SOAR playbook execution metrics.

Aggregates from playbook_executions (and approval linkage counts only). No executor,
queue, adapter, or ingest paths.
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, jsonify
from flask_login import login_required

from core.auth import analyst_or_super_admin_required
from core.db import get_db_connection

metrics_bp = Blueprint("metrics", __name__)

KNOWN_EXECUTION_STATUSES: tuple[str, ...] = (
    "pending",
    "running",
    "awaiting_approval",
    "success",
    "failed",
    "abandoned",
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
RECENT_WINDOW_HOURS = 24


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
        }
        if unknown_statuses:
            payload["unknown_statuses"] = unknown_statuses

        return jsonify(payload), 200
    except Exception as error:
        current_app.logger.error("Error in playbook_execution_metrics_route: %s", error)
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
        }
        if unknown_modes:
            payload["unknown_modes"] = unknown_modes
        if unknown_statuses:
            payload["unknown_statuses"] = unknown_statuses
        if unknown_recent:
            payload["unknown_recent_statuses"] = unknown_recent
        if unknown_circuit_breaker_states:
            payload["unknown_circuit_breaker_states"] = unknown_circuit_breaker_states

        return jsonify(payload), 200
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

        return (
            jsonify(
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
                }
            ),
            200,
        )
    except Exception as error:
        current_app.logger.error("Error in incident_metrics_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()
