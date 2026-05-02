import ipaddress
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request
from flask_login import login_required

from backend_auth import analyst_or_super_admin_required
from backend_db import get_db_connection
from backend_enrichment_helpers import enrich_alert_with_correlation_context, enrich_alert_with_mitre
from backend_ip_helpers import get_ip_reputation


alerts_events_bp = Blueprint("alerts_events", __name__)

VALID_EVENT_TYPES = {"failed_login", "login_failure", "successful_login", "port_scan", "normal_activity"}
VALID_EVENT_SEARCH_TYPES = VALID_EVENT_TYPES | {
    "unauthorized_access",
    "http_error",
    "application_exception",
    "availability_failure",
}
VALID_EVENT_SOURCES = {"bank_app", "nginx", "azure_insights", "opentelemetry"}


@alerts_events_bp.route("/alerts", methods=["GET"])
@login_required
def get_alerts():
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
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
                source_type
            FROM alerts
            ORDER BY created_at DESC
        """)

        rows = cur.fetchall()
        reputation_by_ip = {}

        alerts = []
        for row in rows:
            source_ip = str(row[4]) if row[4] is not None else None
            if source_ip not in reputation_by_ip:
                reputation_by_ip[source_ip] = get_ip_reputation(source_ip, cur=cur)
            reputation = reputation_by_ip[source_ip]

            alerts.append(
                enrich_alert_with_correlation_context(
                    enrich_alert_with_mitre({
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
                    "reputation_score": reputation["reputation_score"],
                    "reputation_label": reputation["reputation_label"],
                    "reputation_source": "siem_internal",
                    "reputation_summary": reputation["reputation_summary"],
                    "contributing_signals": reputation["contributing_signals"],
                    "response_action": row[15],
                    "response_status": row[16],
                    "source": row[17] or "unknown",
                    "source_type": row[18] or "legacy",
                    })
                )
            )


        cur.close()
        conn.close()

        return jsonify(alerts), 200

    except Exception as e:
        current_app.logger.error("Error in get_alerts: %s", e)
        return jsonify({"error": "Internal server error"}), 500


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

        query += " ORDER BY created_at DESC LIMIT 100"

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
