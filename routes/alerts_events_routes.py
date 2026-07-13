from __future__ import annotations

import ipaddress
from datetime import datetime, timedelta, timezone

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
from engines.detection_config import PFSENSE_ALERT_COOLDOWN_MINUTES, get_detection_rule_defaults


alerts_events_bp = Blueprint("alerts_events", __name__)

VALID_EVENT_TYPES = {"failed_login", "login_failure", "successful_login", "port_scan", "normal_activity"}
VALID_EVENT_SEARCH_TYPES = VALID_EVENT_TYPES | {
    "unauthorized_access",
    "http_error",
    "application_exception",
    "availability_failure",
}
VALID_EVENT_SOURCES = CANONICAL_SOURCE_IDS
PFSENSE_ALERT_TYPES = frozenset(
    {
        "pfsense_firewall_repeated_deny",
        "pfsense_firewall_port_scan",
        "pfsense_firewall_suspicious_allow",
        "pfsense_firewall_noisy_source",
    }
)
PFSENSE_WHY_FIRED_LABELS = {
    "action": "Firewall action",
    "direction": "Traffic direction",
    "event_count": "Matching events",
    "destination_ip": "Destination IP",
    "destination_port": "Destination port",
    "protocol": "Protocol",
    "interface": "Interface",
    "distinct_port_count": "Distinct destination ports",
    "distinct_destination_count": "Distinct destination hosts",
    "distinct_sensitive_port_count": "Distinct sensitive ports",
    "first_seen": "First seen",
    "last_seen": "Last seen",
}

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


def _serialize_pfsense_cooldown_state(resolved_at):
    if resolved_at is None:
        return {
            "active": False,
            "resolved_at": None,
            "cooldown_until": None,
            "window_minutes": PFSENSE_ALERT_COOLDOWN_MINUTES,
        }

    if resolved_at.tzinfo is None:
        resolved_at = resolved_at.replace(tzinfo=timezone.utc)
    else:
        resolved_at = resolved_at.astimezone(timezone.utc)

    cooldown_until = resolved_at + timedelta(minutes=PFSENSE_ALERT_COOLDOWN_MINUTES)
    return {
        "active": cooldown_until > datetime.now(timezone.utc),
        "resolved_at": resolved_at.isoformat(),
        "cooldown_until": cooldown_until.isoformat(),
        "window_minutes": PFSENSE_ALERT_COOLDOWN_MINUTES,
    }


def _fetch_latest_resolved_audits(cur, alert_ids: list[int]) -> dict[int, dict]:
    filtered_ids = [int(alert_id) for alert_id in alert_ids if alert_id is not None]
    if not filtered_ids:
        return {}

    cur.execute(
        """
        SELECT DISTINCT ON (target_alert_id)
            target_alert_id,
            created_at
        FROM audit_log
        WHERE event_type = 'UPDATE_ALERT_STATUS'
          AND (details->>'status') = 'resolved'
          AND target_alert_id = ANY(%s)
        ORDER BY target_alert_id, created_at DESC
        """,
        (filtered_ids,),
    )
    return {
        row[0]: _serialize_pfsense_cooldown_state(row[1])
        for row in cur.fetchall()
    }


def _build_pfsense_quality_metadata(row, cooldown_by_alert_id: dict[int, dict]):
    alert_id = row[0]
    alert_type = row[1]
    source = row[17] or "unknown"
    context = row[19] if isinstance(row[19], dict) else {}

    if source != "pfsense" or alert_type not in PFSENSE_ALERT_TYPES:
        return None

    cooldown = cooldown_by_alert_id.get(alert_id) or _serialize_pfsense_cooldown_state(None)
    return {
        "why_fired_available": True,
        "suppressed_rollup": bool(context.get("suppressed")),
        "cooldown": cooldown,
    }


def _format_pfsense_context_value(field_name, value):
    if value in (None, "", []):
        return None
    if field_name == "direction":
        return "LAN → WAN (outbound)" if value == "out" else "WAN → LAN (inbound)" if value == "in" else value
    if field_name == "action":
        return "pass" if value == "pass" else "block" if value == "block" else value
    return value


def _build_pfsense_why_fired_payload(row, cooldown_by_alert_id: dict[int, dict]):
    alert_id = row[0]
    alert_type = row[1]
    source = row[17] or "unknown"
    source_type = row[18] or "legacy"
    context = row[19] if isinstance(row[19], dict) else {}

    if source != "pfsense" or alert_type not in PFSENSE_ALERT_TYPES:
        return None

    rule_defaults = get_detection_rule_defaults().get(alert_type, {})
    evidence_fields_by_type = {
        "pfsense_firewall_repeated_deny": (
            "action",
            "direction",
            "event_count",
            "destination_ip",
            "destination_port",
            "protocol",
            "interface",
            "first_seen",
            "last_seen",
        ),
        "pfsense_firewall_port_scan": (
            "action",
            "distinct_port_count",
            "distinct_destination_count",
            "first_seen",
            "last_seen",
        ),
        "pfsense_firewall_suspicious_allow": (
            "action",
            "direction",
            "event_count",
            "distinct_sensitive_port_count",
            "destination_ip",
            "destination_port",
            "protocol",
            "interface",
            "first_seen",
            "last_seen",
        ),
        "pfsense_firewall_noisy_source": (
            "event_count",
            "first_seen",
            "last_seen",
        ),
    }
    evidence = []
    for field_name in evidence_fields_by_type.get(alert_type, ()):
        formatted_value = _format_pfsense_context_value(field_name, context.get(field_name))
        if formatted_value in (None, "", []):
            continue
        evidence.append(
            {
                "field": field_name,
                "label": PFSENSE_WHY_FIRED_LABELS.get(field_name, field_name.replace("_", " ").title()),
                "value": formatted_value,
            }
        )

    if bool(context.get("suppressed")):
        evidence.append(
            {
                "field": "suppressed",
                "label": "Suppression mode",
                "value": "Routine traffic was rolled up into one noisy-source alert.",
            }
        )

    cooldown = cooldown_by_alert_id.get(alert_id) or _serialize_pfsense_cooldown_state(None)
    return {
        "alert_id": alert_id,
        "rule_id": alert_type,
        "rule_name": rule_defaults.get("display_name", alert_type),
        "source": source,
        "source_type": source_type,
        "summary": row[3],
        "context": context,
        "evidence": evidence,
        "suppressed_rollup": bool(context.get("suppressed")),
        "cooldown": cooldown,
    }


def _build_alert_payload(
    row,
    *,
    cur,
    reputation_by_ip: dict,
    response_outcome,
    cooldown_by_alert_id: dict[int, dict],
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
                "pfsense_quality": _build_pfsense_quality_metadata(row, cooldown_by_alert_id),
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
        cooldown_by_alert_id = _fetch_latest_resolved_audits(cur, alert_ids)
        reputation_by_ip = {}

        alerts = []
        for row in rows:
            alerts.append(
                _build_alert_payload(
                    row,
                    cur=cur,
                    reputation_by_ip=reputation_by_ip,
                    response_outcome=response_outcomes_by_alert.get(row[0]),
                    cooldown_by_alert_id=cooldown_by_alert_id,
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
        cooldown_by_alert_id = _fetch_latest_resolved_audits(cur, [alert_id])
        alert = _build_alert_payload(
            row,
            cur=cur,
            reputation_by_ip={},
            response_outcome=response_outcome,
            cooldown_by_alert_id=cooldown_by_alert_id,
        )

        cur.close()
        conn.close()

        return jsonify(alert), 200

    except Exception as e:
        current_app.logger.error("Error in get_alert: %s", e)
        return jsonify({"error": "Internal server error"}), 500


@alerts_events_bp.route("/alerts/<int:alert_id>/why-fired", methods=["GET"])
@login_required
def get_pfsense_why_fired(alert_id):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(f"{_ALERT_SELECT} WHERE id = %s", (alert_id,))
        row = cur.fetchone()
        if row is None:
            return jsonify({"error": "Alert not found"}), 404

        payload = _build_pfsense_why_fired_payload(
            row,
            _fetch_latest_resolved_audits(cur, [alert_id]),
        )
        if payload is None:
            return jsonify({"error": "Why this fired is available only for pfSense alerts"}), 400

        return jsonify(payload), 200
    except Exception as error:
        current_app.logger.error("Error in get_pfsense_why_fired: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


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
