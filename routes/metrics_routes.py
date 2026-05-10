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

RECENT_WINDOW_HOURS = 24


def _empty_by_status() -> dict[str, int]:
    return {s: 0 for s in KNOWN_EXECUTION_STATUSES}


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

