from __future__ import annotations

import ipaddress
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request
from flask_login import login_required

from core.auth import admin_required, analyst_or_super_admin_required
from core.db import get_db_connection
from core.soar_response_outcomes import (
    build_latest_outcome_api_shape,
    get_latest_decisions_for_alerts_bulk,
    get_latest_outcomes_for_alerts_bulk,
    serialize_latest_outcome,
)
from helpers.enrichment_helpers import enrich_alert_with_correlation_context, enrich_alert_with_mitre
from core.ip_helpers import determine_response_action, get_ip_reputation, lookup_ip_reputation
from core.source_inventory import CANONICAL_SOURCE_IDS


alerts_events_bp = Blueprint("alerts_events", __name__)

VALID_EVENT_TYPES = {"failed_login", "login_failure", "successful_login", "port_scan", "normal_activity"}
VALID_EVENT_SEARCH_TYPES = VALID_EVENT_TYPES | {
    "unauthorized_access",
    "http_error",
    "application_exception",
    "availability_failure",
}
VALID_EVENT_SOURCES = CANONICAL_SOURCE_IDS

_ALERT_SELECT = """
    SELECT
        id,
        alert_type,
        severity,
        message,
        source_ip,
        created_at,
        status,
        country,
        city,
        latitude,
        longitude,
        reputation_score,
        reputation_label,
        reputation_source,
        reputation_summary,
        response_action,
        response_status,
        source,
        source_type,
        context
    FROM alerts
"""


def _resolve_alert_list_response_outcomes(conn, alert_ids: list[int]) -> dict[int, dict | None]:
    bulk_events = get_latest_outcomes_for_alerts_bulk(conn, alert_ids)
    latest_decisions = get_latest_decisions_for_alerts_bulk(conn, alert_ids)
    outcomes: dict[int, dict | None] = {}
    for alert_id in alert_ids:
        decision = latest_decisions.get(alert_id)
        if decision is None:
            outcomes[alert_id] = None
        else:
            outcomes[alert_id] = build_latest_outcome_api_shape(
                decision,
                bulk_events.get(alert_id),
            )
    return outcomes


def _build_alert_payload(
    row,
    *,
    cur,
    reputation_by_ip: dict,
    response_outcome,
) -> dict:
    source_ip = str(row[4]) if row[4] is not None else None
    if source_ip not in reputation_by_ip:
        reputation_by_ip[source_ip] = get_ip_reputation(source_ip, cur=cur)
    behavioral_reputation = reputation_by_ip[source_ip]
    behavioral_contributing_signals = behavioral_reputation.get("contributing_signals", [])

    return enrich_alert_with_correlation_context(
        enrich_alert_with_mitre(
            {
                "id": row[0],
                "alert_type": row[1],
                "severity": row[2],
                "message": row[3],
                "source_ip": row[4],
                "created_at": str(row[5]),
                "status": row[6],
                "country": row[7],
                "city": row[8],
                "latitude": row[9],
                "longitude": row[10],
                "reputation_score": row[11],
                "reputation_label": row[12],
                "reputation_source": row[13],
                "reputation_summary": row[14],
                "behavioral_reputation": {
                    "score": behavioral_reputation["reputation_score"],
                    "label": behavioral_reputation["reputation_label"],
                    "source": "siem_internal",
                    "summary": behavioral_reputation["reputation_summary"],
                    "contributing_signals": behavioral_contributing_signals,
                },
                "contributing_signals": behavioral_contributing_signals,
                "response_action": row[15],
                "response_status": row[16],
                "response_outcome": response_outcome,
                "source": row[17] or "unknown",
                "source_type": row[18] or "legacy",
                "context": row[19] if row[19] is not None else {},
            }
        )
    )


@alerts_events_bp.route("/alerts", methods=["GET"])
@login_required
def get_alerts():
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(f"{_ALERT_SELECT} ORDER BY created_at DESC")

        rows = cur.fetchall()
        alert_ids = [row[0] for row in rows]
        response_outcomes_by_alert = _resolve_alert_list_response_outcomes(conn, alert_ids)
        reputation_by_ip = {}

        alerts = []
        for row in rows:
            alerts.append(
                _build_alert_payload(
                    row,
                    cur=cur,
                    reputation_by_ip=reputation_by_ip,
                    response_outcome=response_outcomes_by_alert.get(row[0]),
                )
            )

        cur.close()
        conn.close()

        return jsonify(alerts), 200

    except Exception as e:
        current_app.logger.error("Error in get_alerts: %s", e)
        return jsonify({"error": "Internal server error"}), 500


@alerts_events_bp.route("/alerts/<int:alert_id>", methods=["GET"])
@login_required
def get_alert(alert_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(f"{_ALERT_SELECT} WHERE id = %s", (alert_id,))
        row = cur.fetchone()
        if row is None:
            cur.close()
            conn.close()
            return jsonify({"error": "Alert not found"}), 404

        response_outcome = serialize_latest_outcome(conn, alert_id=alert_id)
        alert = _build_alert_payload(
            row,
            cur=cur,
            reputation_by_ip={},
            response_outcome=response_outcome,
        )

        cur.close()
        conn.close()

        return jsonify(alert), 200

    except Exception as e:
        current_app.logger.error("Error in get_alert: %s", e)
        return jsonify({"error": "Internal server error"}), 500


@alerts_events_bp.route("/alerts/backfill-reputation", methods=["POST"])
@login_required
@admin_required
def backfill_alert_reputation():
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, source_ip
            FROM alerts
            WHERE
                reputation_score IS NULL
                OR reputation_source IN ('mock', 'fallback')
                OR response_action IS NULL
                OR response_status IS NULL
            """
        )

        rows = cur.fetchall()
        updated = 0

        for row in rows:
            alert_id = row[0]
            source_ip = str(row[1])

            reputation = lookup_ip_reputation(source_ip)
            response_action = determine_response_action(reputation["reputation_score"])
            response_status = "pending"

            cur.execute(
                """
                UPDATE alerts
                SET
                    reputation_score = %s,
                    reputation_label = %s,
                    reputation_source = %s,
                    reputation_summary = %s,
                    response_action = %s,
                    response_status = %s
                WHERE id = %s
                """,
                (
                    reputation["reputation_score"],
                    reputation["reputation_label"],
                    reputation["reputation_source"],
                    reputation["reputation_summary"],
                    response_action,
                    response_status,
                    alert_id
                )
            )

            updated += 1

        conn.commit()

        return jsonify({
            "message": "Reputation backfill completed",
            "updated_alerts": updated
        }), 200

    except Exception as e:
        current_app.logger.error("Error in backfill_alert_reputation: %s", e)
        return jsonify({"error": "Internal server error"}), 500

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@alerts_events_bp.route("/events/search", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def search_events():
    conn = None
    cur = None

    try:
        source_ip = (request.args.get("source_ip") or "").strip()
        source = (request.args.get("source") or "").strip()
        event_type = (request.args.get("event_type") or "").strip()
        start_time = (request.args.get("start_time") or "").strip()
        end_time = (request.args.get("end_time") or "").strip()
        after_id = (request.args.get("after_id") or "").strip()

        clauses = []
        params = []

        if source_ip:
            try:
                ipaddress.ip_address(source_ip)
            except ValueError:
                return jsonify({"error": "Invalid source_ip"}), 400
            clauses.append("source_ip = %s")
            params.append(source_ip)

        if source:
            if source not in VALID_EVENT_SOURCES:
                return jsonify({"error": "Invalid source"}), 400
            clauses.append("source = %s")
            params.append(source)

        if event_type:
            if event_type not in VALID_EVENT_SEARCH_TYPES:
                return jsonify({"error": "Invalid event_type"}), 400
            clauses.append("event_type = %s")
            params.append(event_type)

        if after_id:
            try:
                parsed_after_id = int(after_id)
            except ValueError:
                return jsonify({"error": "Invalid after_id"}), 400
            if parsed_after_id < 0:
                return jsonify({"error": "Invalid after_id"}), 400
            clauses.append("id > %s")
            params.append(parsed_after_id)

        if start_time:
            try:
                parsed_start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            except ValueError:
                return jsonify({"error": "Invalid start_time"}), 400
            clauses.append("created_at >= %s")
            params.append(parsed_start)

        if end_time:
            try:
                parsed_end = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            except ValueError:
                return jsonify({"error": "Invalid end_time"}), 400
            clauses.append("created_at <= %s")
            params.append(parsed_end)

        query = """
            SELECT
                id,
                event_type,
                severity,
                source_ip,
                message,
                app_name,
                environment,
                source,
                source_type,
                raw_payload,
                created_at
            FROM events
        """

        if clauses:
            query += " WHERE " + " AND ".join(clauses)

        query += " ORDER BY id DESC LIMIT 100"

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(query, tuple(params))

        rows = cur.fetchall()
        reputation_by_ip = {}
        events = []
        for row in rows:
            source_ip = str(row[3]) if row[3] is not None else None
            if source_ip not in reputation_by_ip:
                reputation_by_ip[source_ip] = get_ip_reputation(source_ip, cur=cur)
            reputation = reputation_by_ip[source_ip]

            events.append(
                {
                    "id": row[0],
                    "event_type": row[1],
                    "severity": row[2],
                    "source_ip": source_ip,
                    "message": row[4],
                    "app_name": row[5],
                    "environment": row[6],
                    "source": row[7],
                    "source_type": row[8],
                    "raw_payload": row[9],
                    "created_at": str(row[10]),
                    "reputation_score": reputation["reputation_score"],
                    "reputation_label": reputation["reputation_label"],
                    "reputation_summary": reputation["reputation_summary"],
                    "contributing_signals": reputation["contributing_signals"],
                }
            )

        return jsonify(events), 200
    except Exception as e:
        current_app.logger.error("Error in search_events: %s", e)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
