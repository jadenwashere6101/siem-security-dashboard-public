import ipaddress
import logging
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, jsonify, request
from psycopg2.extras import Json

from adapters.azure_insights_adapter import (
    normalize_azure_identity_telemetry,
    normalize_azure_insights_telemetry,
)
from core.ingestion_checkpoint_store import get_checkpoint, upsert_checkpoint
from adapters.nginx_adapter import parse_nginx_access_log_line
from adapters.otel_adapter import normalize_otel_telemetry
from adapters.pfsense_filterlog_adapter import (
    MAX_PFSENSE_INGEST_BYTES,
    validate_pfsense_normalized_event,
)
from helpers.api_guards import require_api_key, require_azure_api_key, require_otel_api_key
from core.db import get_db_connection
from core.extensions import limiter
from core.incident_store import maybe_create_or_link_incident
from core.notification_policy_service import (
    notify_for_alert,
    notify_for_incident,
    notify_for_material_recon_activity,
)
from core.recon_activity_store import enroll_alert_in_recon_activity, fetch_alert_context
from engines.ingest_engine import ingest_normalized_event
from engines.pfsense_ingest_filter import (
    evaluate_event,
    load_effective_policy,
    record_filter_decision,
)
from engines.soar_playbook_orchestrator import create_pending_executions_for_committed_alerts
from engines.soar_enqueue_orchestrator import enqueue_committed_alerts
from helpers.ingest_normalizers import (
    _get_azure_app_name,
    _get_azure_identity_app_name,
    _get_otel_app_name,
    _is_azure_identity_payload,
    has_valid_location,
    reject_raw_password_fields,
)
from core.ip_helpers import lookup_ip_location


ingest_bp = Blueprint("ingest", __name__)
logger = logging.getLogger(__name__)

VALID_SEVERITIES = {"low", "medium", "high", "critical"}
VALID_EVENT_TYPES = {
    "failed_login",
    "login_failure",
    "successful_login",
    "port_scan",
    "normal_activity",
    "env_probe",
    "admin_probe",
    "scanner_detected",
    "credential_stuffing",
}
HONEYPOT_INGEST_EVENT_TYPES = {
    "env_probe",
    "admin_probe",
    "scanner_detected",
    "credential_stuffing",
    "http_error",
}
HONEYPOT_SEVERITY_BY_EVENT_TYPE = {
    "env_probe": "high",
    "admin_probe": "medium",
    "scanner_detected": "medium",
    "credential_stuffing": "high",
    "http_error": "medium",
}
INCIDENT_SEVERITIES = {"HIGH", "CRITICAL"}
AZURE_CHECKPOINT_CONNECTOR = "azure_insights"
AZURE_CHECKPOINT_DEFAULT_LOOKBACK = timedelta(hours=1)
AZURE_CHECKPOINT_MIN_LOOKBACK = timedelta(minutes=15)


def _enroll_recon_activity_members(alerts_created, conn):
    for alert in alerts_created or []:
        alert_type = str(alert.get("alert_type") or "")
        if alert_type not in {"pfsense_firewall_port_scan", "pfsense_firewall_repeated_deny"}:
            continue
        alert_id = alert.get("alert_id")
        if not alert_id:
            continue
        context = fetch_alert_context(conn, int(alert_id))
        if not isinstance(context, dict):
            continue
        flags = context["context"].get("operational_flags") if isinstance(context.get("context"), dict) else {}
        if not isinstance(flags, dict):
            continue
        if not bool(flags.get("aggregate_eligible")):
            continue
        activity = enroll_alert_in_recon_activity(conn, int(alert_id))
        if isinstance(activity, dict) and activity.get("id"):
            alert["recon_activity_id"] = activity["id"]


def _create_incidents_for_alerts(alerts_created, conn):
    created_incident_ids = []
    for alert in alerts_created or []:
        alert_id = alert.get("alert_id")
        severity = alert.get("severity")
        source_ip = alert.get("source_ip")

        if not alert_id or not severity or not source_ip:
            logger.warning(
                "[SOAR INCIDENT SKIP] Missing incident fields alert_id=%s source_ip=%s severity=%s",
                alert_id,
                source_ip,
                severity,
            )
            continue

        if str(severity).upper() not in INCIDENT_SEVERITIES:
            continue

        try:
            incident = maybe_create_or_link_incident(
                conn,
                alert_id,
                severity,
                str(source_ip),
                alert_type=alert.get("alert_type"),
                context=alert.get("context") if isinstance(alert.get("context"), dict) else None,
            )
            if incident and incident.get("created") is True:
                created_incident_ids.append(int(incident["id"]))
        except Exception as incident_error:
            logger.error(
                "[SOAR INCIDENT FAILED] %s | alert_id=%s source_ip=%s severity=%s",
                incident_error,
                alert_id,
                source_ip,
                severity,
            )
    return created_incident_ids


def _send_alert_notifications_for_alerts(alerts_created, conn):
    for alert in alerts_created or []:
        alert_id = alert.get("alert_id")
        if not alert_id:
            continue
        try:
            notify_for_alert(conn, int(alert_id))
        except Exception as notify_error:
            logger.error(
                "[NOTIFICATION POLICY ALERT FAILED] %s | alert_id=%s",
                notify_error,
                alert_id,
            )


def _send_incident_notifications_for_incidents(incident_ids, conn):
    for incident_id in incident_ids or []:
        try:
            notify_for_incident(conn, int(incident_id))
        except Exception as notify_error:
            logger.error(
                "[NOTIFICATION POLICY INCIDENT FAILED] %s | incident_id=%s",
                notify_error,
                incident_id,
            )


def _send_recon_activity_notifications_for_alerts(alerts_created, conn):
    activity_ids = []
    seen = set()
    for alert in alerts_created or []:
        activity_id = alert.get("recon_activity_id")
        if not activity_id:
            continue
        try:
            normalized = int(activity_id)
        except (TypeError, ValueError):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        activity_ids.append(normalized)

    for activity_id in activity_ids:
        try:
            notify_for_material_recon_activity(conn, activity_id)
        except Exception as notify_error:
            logger.error(
                "[NOTIFICATION POLICY RECON FAILED] %s | recon_activity_id=%s",
                notify_error,
                activity_id,
            )


def _create_playbook_executions_for_alerts(alerts_created, conn):
    try:
        result = create_pending_executions_for_committed_alerts(alerts_created, conn)
        conn.commit()

        try:
            _send_alert_notifications_for_alerts(alerts_created, conn)
            conn.commit()
        except Exception as notification_error:
            current_app.logger.error(
                "[NOTIFICATION POLICY ALERT FAILED] Post-commit alert notification failed — ingest was committed: %s",
                notification_error,
            )
        return result
    except Exception as playbook_error:
        conn.rollback()
        current_app.logger.error(
            "[PLAYBOOK ORCHESTRATION ERROR] Post-commit playbook scheduling failed — ingest was committed: %s",
            playbook_error,
        )
        return {"summary": {"errors": 1}, "results": []}


def _playbook_claimed_alert_ids(playbook_result):
    claimed = set()
    if not isinstance(playbook_result, dict):
        return claimed
    for item in playbook_result.get("results") or []:
        if not isinstance(item, dict):
            continue
        if item.get("status") not in {"created", "duplicate"}:
            continue
        alert_id = item.get("alert_id")
        if alert_id is None:
            continue
        try:
            claimed.add(int(alert_id))
        except (TypeError, ValueError):
            continue
    return claimed


def _utc_now():
    return datetime.now(timezone.utc)


def _serialize_datetime(value):
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _bounded_default_checkpoint(now=None):
    now = now or _utc_now()
    bounded = now - AZURE_CHECKPOINT_DEFAULT_LOOKBACK
    floor = now - AZURE_CHECKPOINT_MIN_LOOKBACK
    if bounded > floor:
        bounded = floor
    return bounded


def _parse_checkpoint_timestamp(raw_value):
    if raw_value in (None, ""):
        return None
    if not isinstance(raw_value, str):
        raise ValueError("last_processed_at must be an ISO 8601 timestamp string")
    candidate = raw_value.strip()
    if not candidate:
        return None
    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as error:
        raise ValueError("last_processed_at must be an ISO 8601 timestamp string") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("last_processed_at must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _serialize_checkpoint_payload(row, *, fallback_to_default=False):
    checkpoint = row.get("last_processed_at") if row else None
    if checkpoint is None and fallback_to_default:
        checkpoint = _bounded_default_checkpoint()
    return {
        "connector_name": AZURE_CHECKPOINT_CONNECTOR,
        "last_processed_at": _serialize_datetime(checkpoint),
        "last_poll_status": row.get("last_poll_status") if row else None,
        "last_poll_counts": row.get("last_poll_counts") if row else {},
        "updated_at": _serialize_datetime(row.get("updated_at")) if row else None,
    }


def _azure_event_already_ingested(cur, event_dict):
    cur.execute(
        """
        SELECT 1
        FROM events
        WHERE source = %s
          AND source_type = %s
          AND event_type = %s
          AND source_ip = %s
          AND app_name = %s
          AND message = %s
          AND event_timestamp IS NOT DISTINCT FROM %s
          AND raw_payload = %s::jsonb
        LIMIT 1
        """,
        (
            event_dict["source"],
            event_dict["source_type"],
            event_dict["event_type"],
            event_dict["source_ip"],
            event_dict["app_name"],
            event_dict["message"],
            event_dict.get("event_timestamp"),
            Json(event_dict["raw_payload"]),
        ),
    )
    return cur.fetchone() is not None


def _normalize_honeypot_event(data):
    event_type = data.get("event_type")
    source_ip = data.get("source_ip")

    if not event_type or not source_ip:
        raise ValueError("Missing required fields")

    if event_type not in HONEYPOT_INGEST_EVENT_TYPES:
        raise ValueError("Invalid event_type")

    try:
        ipaddress.ip_address(str(source_ip))
    except ValueError as error:
        raise ValueError("Invalid source_ip") from error

    raw_payload = dict(data)
    normalized = {
        "event_type": event_type,
        "severity": HONEYPOT_SEVERITY_BY_EVENT_TYPE[event_type],
        "source_ip": source_ip,
        "source": "honeypot",
        "source_type": "honeypot",
        "event_timestamp": data.get("timestamp"),
        "message": _build_honeypot_message(data),
        "app_name": "flask_honeypot",
        "environment": str(data.get("environment") or "prod").strip() or "prod",
        "raw_payload": raw_payload,
    }
    reject_raw_password_fields(normalized)
    return normalized


def _build_honeypot_message(data):
    event_type = data.get("event_type")
    source_ip = data.get("source_ip")
    method = str(data.get("method") or "UNKNOWN").strip() or "UNKNOWN"
    path = str(data.get("path") or "/").strip() or "/"

    if event_type == "env_probe":
        return f"Honeypot sensitive path probe from {source_ip}: {method} {path}"
    if event_type == "admin_probe":
        return f"Honeypot admin path probe from {source_ip}: {method} {path}"
    if event_type == "scanner_detected":
        scanner_context = (
            str(data.get("scanner_signature") or data.get("user_agent") or "unknown scanner").strip()
            or "unknown scanner"
        )
        return f"Honeypot scanner detected from {source_ip}: {scanner_context}"
    if event_type == "credential_stuffing":
        username = str(data.get("username") or "unknown username").strip() or "unknown username"
        return f"Honeypot credential stuffing attempt from {source_ip} for username {username}"
    if event_type == "http_error":
        return f"Honeypot HTTP error from {source_ip}: {method} {path}"
    return f"Honeypot event from {source_ip}"


def _add_location_to_normalized_event(normalized_event):
    raw_payload = normalized_event.setdefault("raw_payload", {})
    if has_valid_location(raw_payload.get("location")):
        return

    location = lookup_ip_location(normalized_event.get("source_ip"))
    if has_valid_location(location):
        raw_payload["location"] = location


@ingest_bp.route("/ingest", methods=["POST"])
@limiter.limit("200 per minute")
def add_event():
    # spec: SPEC-INGEST-001
    api_key_error = require_api_key()
    if api_key_error:
        return api_key_error

    conn = None
    cur = None

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400

        event_type = data.get("event_type")
        severity = data.get("severity")
        source_ip = data.get("source_ip")
        message = data.get("message")
        app_name = data.get("app_name")
        environment = data.get("environment")
        raw_payload = dict(data)

        if not event_type or not severity or not source_ip:
            return jsonify({"error": "Missing required fields"}), 400

        try:
            ipaddress.ip_address(str(source_ip))
        except ValueError:
            return jsonify({"error": "Invalid source_ip"}), 400

        if not message:
            return jsonify({"error": "Missing required field: message"}), 400

        if not app_name:
            return jsonify({"error": "Missing required field: app_name"}), 400

        if not environment:
            return jsonify({"error": "Missing required field: environment"}), 400

        if event_type not in VALID_EVENT_TYPES:
            return jsonify({"error": "Invalid event_type"}), 400

        if severity not in VALID_SEVERITIES:
            return jsonify({"error": "Invalid severity"}), 400

        if not has_valid_location(raw_payload.get("location")):
            location = lookup_ip_location(source_ip)
            if has_valid_location(location):
                raw_payload["location"] = location

        conn = get_db_connection()
        cur = conn.cursor()

        alerts_created = ingest_normalized_event(
            {
                "event_type": event_type,
                "severity": severity,
                "source_ip": source_ip,
                "message": message,
                "app_name": app_name,
                "environment": environment,
                "raw_payload": raw_payload,
            },
            conn,
            cur,
        )

        conn.commit()

        playbook_result = _create_playbook_executions_for_alerts(alerts_created, conn)
        playbook_claimed_alert_ids = _playbook_claimed_alert_ids(playbook_result)

        try:
            enqueue_committed_alerts(
                alerts_created,
                conn,
                exclude_alert_ids=playbook_claimed_alert_ids,
            )
            conn.commit()
        except Exception as enqueue_error:
            current_app.logger.error(
                "[SOAR ENQUEUE ERROR] Post-commit enqueue failed — ingest was committed: %s",
                enqueue_error,
            )

        try:
            created_incident_ids = _create_incidents_for_alerts(alerts_created, conn)
            conn.commit()
            _send_incident_notifications_for_incidents(created_incident_ids, conn)
            conn.commit()
        except Exception as incident_error:
            current_app.logger.error(
                "[SOAR INCIDENT FAILED] Post-commit incident creation failed — ingest was committed: %s | alerts=%s",
                incident_error,
                [(a.get("alert_id"), a.get("source_ip"), a.get("severity")) for a in alerts_created],
            )

        return jsonify({
            "message": "Event added successfully",
            "alerts_created": alerts_created
        }), 201

    except Exception as e:
        if conn:
            conn.rollback()
        print("Error in add_event:", e)
        return jsonify({"error": "Internal server error"}), 500

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@ingest_bp.route("/ingest/honeypot", methods=["POST"])
def add_honeypot_event():
    api_key_error = require_api_key()
    if api_key_error:
        return api_key_error

    conn = None
    cur = None

    try:
        data = request.get_json()
        if not isinstance(data, dict):
            return jsonify({"error": "Invalid JSON"}), 400

        try:
            normalized_event = _normalize_honeypot_event(data)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400

        _add_location_to_normalized_event(normalized_event)

        conn = get_db_connection()
        cur = conn.cursor()

        alerts_created = ingest_normalized_event(normalized_event, conn, cur)

        conn.commit()
        _enroll_recon_activity_members(alerts_created, conn)
        conn.commit()
        _send_recon_activity_notifications_for_alerts(alerts_created, conn)
        conn.commit()
        for alert in alerts_created:
            alert_id = alert.get("alert_id")
            if not alert_id:
                continue
            alert_context = fetch_alert_context(conn, int(alert_id))
            if not isinstance(alert_context, dict):
                continue
            alert_context_payload = alert_context.get("context")
            if isinstance(alert_context_payload, dict):
                alert["context"] = alert_context_payload
            alert_type = alert_context.get("alert_type")
            if isinstance(alert_type, str) and alert_type:
                alert["alert_type"] = alert_type

        playbook_result = _create_playbook_executions_for_alerts(alerts_created, conn)
        playbook_claimed_alert_ids = _playbook_claimed_alert_ids(playbook_result)

        try:
            enqueue_committed_alerts(
                alerts_created,
                conn,
                exclude_alert_ids=playbook_claimed_alert_ids,
            )
            conn.commit()
        except Exception as enqueue_error:
            current_app.logger.error(
                "[SOAR ENQUEUE ERROR] Post-commit enqueue failed — ingest was committed: %s",
                enqueue_error,
            )

        try:
            created_incident_ids = _create_incidents_for_alerts(alerts_created, conn)
            conn.commit()
            _send_incident_notifications_for_incidents(created_incident_ids, conn)
            conn.commit()
        except Exception as incident_error:
            current_app.logger.error(
                "[SOAR INCIDENT FAILED] Post-commit incident creation failed — ingest was committed: %s | alerts=%s",
                incident_error,
                [(a.get("alert_id"), a.get("source_ip"), a.get("severity")) for a in alerts_created],
            )

        return jsonify({
            "message": "Honeypot event ingested successfully",
            "alerts_created": alerts_created,
        }), 201
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("Error in add_honeypot_event: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@ingest_bp.route("/ingest/web-log", methods=["POST"])
def add_web_log_event():
    # spec: SPEC-NORM-001
    api_key_error = require_api_key()
    if api_key_error:
        return api_key_error

    conn = None
    cur = None

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400

        line = data.get("line")
        if not isinstance(line, str) or not line.strip():
            return jsonify({"error": "Missing required field: line"}), 400

        try:
            parsed_line = parse_nginx_access_log_line(line)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400

        status_code = parsed_line["status"]
        if status_code in {401, 403}:
            event_type = "unauthorized_access"
            severity = "medium"
        elif 500 <= status_code <= 599:
            event_type = "http_error"
            severity = "medium"
        else:
            event_type = "normal_activity"
            severity = "low"

        method = parsed_line.get("method") or "UNKNOWN"
        path = parsed_line.get("path") or "/"
        source_ip = parsed_line["source_ip"]
        environment = data.get("environment") or "prod"
        raw_payload = {
            "line": line,
            "log_format": "nginx_access",
            **parsed_line,
        }

        if event_type == "unauthorized_access":
            message = f"Unauthorized web access detected: HTTP {status_code} for {method} {path}"
        elif event_type == "http_error":
            message = f"Web server error detected: HTTP {status_code} for {method} {path}"
        else:
            message = f"Web request observed: HTTP {status_code} for {method} {path}"

        conn = get_db_connection()
        cur = conn.cursor()

        alerts_created = ingest_normalized_event(
            {
                "event_type": event_type,
                "severity": severity,
                "source_ip": source_ip,
                "source": "nginx",
                "source_type": "web_log",
                "event_timestamp": parsed_line.get("event_timestamp"),
                "message": message,
                "app_name": "nginx",
                "environment": environment,
                "raw_payload": raw_payload,
            },
            conn,
            cur,
        )

        conn.commit()

        playbook_result = _create_playbook_executions_for_alerts(alerts_created, conn)
        playbook_claimed_alert_ids = _playbook_claimed_alert_ids(playbook_result)

        try:
            enqueue_committed_alerts(
                alerts_created,
                conn,
                exclude_alert_ids=playbook_claimed_alert_ids,
            )
            conn.commit()
        except Exception as enqueue_error:
            current_app.logger.error(
                "[SOAR ENQUEUE ERROR] Post-commit enqueue failed — ingest was committed: %s",
                enqueue_error,
            )

        try:
            created_incident_ids = _create_incidents_for_alerts(alerts_created, conn)
            conn.commit()
            _send_incident_notifications_for_incidents(created_incident_ids, conn)
            conn.commit()
        except Exception as incident_error:
            current_app.logger.error(
                "[SOAR INCIDENT FAILED] Post-commit incident creation failed — ingest was committed: %s | alerts=%s",
                incident_error,
                [(a.get("alert_id"), a.get("source_ip"), a.get("severity")) for a in alerts_created],
            )

        return jsonify({
            "message": "Event added successfully",
            "alerts_created": alerts_created
        }), 201
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("Error in add_web_log_event: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@ingest_bp.route("/ingest/azure", methods=["POST"])
def add_azure_event():
    api_key_error = require_azure_api_key()
    if api_key_error:
        return api_key_error

    conn = None
    cur = None

    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "Invalid JSON"}), 400

        if isinstance(data, list):
            if not data:
                return jsonify({"error": "Telemetry batch must not be empty"}), 400
            if len(data) > 25:
                return jsonify({"error": "Telemetry batch exceeds maximum size of 25"}), 400
            telemetry_items = data
        elif isinstance(data, dict):
            telemetry_items = [data]
        else:
            return jsonify({"error": "Invalid telemetry payload"}), 400

        normalized_events = []
        for item_index, item in enumerate(telemetry_items):
            try:
                is_identity_payload = _is_azure_identity_payload(item)
                if is_identity_payload:
                    normalized = normalize_azure_identity_telemetry(item)
                else:
                    normalized = normalize_azure_insights_telemetry(item)
            except ValueError as error:
                current_app.logger.warning(
                    "Azure telemetry batch item %s failed validation: %s: %s",
                    item_index,
                    type(error).__name__,
                    error,
                )
                return jsonify({"error": str(error)}), 400

            raw_payload = dict(item) if isinstance(item, dict) else item
            if is_identity_payload and isinstance(raw_payload, dict):
                raw_payload["username"] = normalized["username"]

            normalized_events.append(
                {
                    "event_type": normalized["event_type"],
                    "severity": normalized["severity"],
                    "source_ip": normalized["source_ip"],
                    "source": "azure_insights",
                    "source_type": "cloud_api",
                    "event_timestamp": normalized.get("event_timestamp"),
                    "message": normalized["message"],
                    "app_name": _get_azure_identity_app_name(item) if is_identity_payload else _get_azure_app_name(item),
                    "environment": (item.get("environment") or "prod") if isinstance(item, dict) else "prod",
                    "raw_payload": raw_payload,
                }
            )

        conn = get_db_connection()
        cur = conn.cursor()

        alerts_created = []
        for event_dict in normalized_events:
            if _azure_event_already_ingested(cur, event_dict):
                continue
            alerts_created.extend(ingest_normalized_event(event_dict, conn, cur))

        conn.commit()

        playbook_result = _create_playbook_executions_for_alerts(alerts_created, conn)
        playbook_claimed_alert_ids = _playbook_claimed_alert_ids(playbook_result)

        try:
            enqueue_committed_alerts(
                alerts_created,
                conn,
                exclude_alert_ids=playbook_claimed_alert_ids,
            )
            conn.commit()
        except Exception as enqueue_error:
            current_app.logger.error(
                "[SOAR ENQUEUE ERROR] Post-commit enqueue failed — ingest was committed: %s",
                enqueue_error,
            )

        try:
            created_incident_ids = _create_incidents_for_alerts(alerts_created, conn)
            conn.commit()
            _send_incident_notifications_for_incidents(created_incident_ids, conn)
            conn.commit()
        except Exception as incident_error:
            current_app.logger.error(
                "[SOAR INCIDENT FAILED] Post-commit incident creation failed — ingest was committed: %s | alerts=%s",
                incident_error,
                [(a.get("alert_id"), a.get("source_ip"), a.get("severity")) for a in alerts_created],
            )

        success_message = "Events added successfully" if len(normalized_events) > 1 else "Event added successfully"
        return jsonify({
            "message": success_message,
            "alerts_created": alerts_created,
        }), 201
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("Error in add_azure_event: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@ingest_bp.route("/ingest/azure/checkpoint", methods=["GET"])
def get_azure_ingestion_checkpoint():
    api_key_error = require_azure_api_key()
    if api_key_error:
        return api_key_error

    conn = None
    try:
        conn = get_db_connection()
        row = get_checkpoint(AZURE_CHECKPOINT_CONNECTOR, conn)
        return jsonify(_serialize_checkpoint_payload(row, fallback_to_default=True)), 200
    except Exception as error:
        current_app.logger.error("Error in get_azure_ingestion_checkpoint: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@ingest_bp.route("/ingest/azure/checkpoint", methods=["PATCH"])
def patch_azure_ingestion_checkpoint():
    api_key_error = require_azure_api_key()
    if api_key_error:
        return api_key_error

    conn = None
    try:
        data = request.get_json()
        if not isinstance(data, dict):
            return jsonify({"error": "Invalid JSON"}), 400

        try:
            last_processed_at = _parse_checkpoint_timestamp(data.get("last_processed_at"))
        except ValueError as error:
            return jsonify({"error": str(error)}), 400

        poll_status = data.get("last_poll_status")
        if poll_status is not None and poll_status not in {"success", "failure", "partial"}:
            return jsonify({"error": "last_poll_status must be success, failure, or partial"}), 400

        poll_counts = data.get("last_poll_counts") or {}
        if not isinstance(poll_counts, dict):
            return jsonify({"error": "last_poll_counts must be an object"}), 400

        conn = get_db_connection()
        row = upsert_checkpoint(
            AZURE_CHECKPOINT_CONNECTOR,
            conn,
            last_processed_at=last_processed_at,
            poll_status=poll_status,
            poll_counts=poll_counts,
        )
        conn.commit()
        return jsonify(_serialize_checkpoint_payload(row)), 200
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("Error in patch_azure_ingestion_checkpoint: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@ingest_bp.route("/ingest/otlp", methods=["POST"])
def add_otel_event():
    api_key_error = require_otel_api_key()
    if api_key_error:
        return api_key_error

    conn = None
    cur = None

    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "Invalid JSON"}), 400

        if isinstance(data, list):
            if not data:
                return jsonify({"error": "Telemetry batch must not be empty"}), 400
            if len(data) > 25:
                return jsonify({"error": "Telemetry batch exceeds maximum size of 25"}), 400
            telemetry_items = data
        elif isinstance(data, dict):
            telemetry_items = [data]
        else:
            return jsonify({"error": "Invalid telemetry payload"}), 400

        normalized_events = []
        for item in telemetry_items:
            try:
                normalized = normalize_otel_telemetry(item)
            except ValueError as error:
                return jsonify({"error": str(error)}), 400

            normalized_events.append(
                {
                    "event_type": normalized["event_type"],
                    "severity": normalized["severity"],
                    "source_ip": normalized["source_ip"],
                    "source": "opentelemetry",
                    "source_type": "telemetry",
                    "event_timestamp": normalized.get("event_timestamp"),
                    "message": normalized["message"],
                    "app_name": _get_otel_app_name(normalized, item),
                    "environment": (item.get("environment") or "prod") if isinstance(item, dict) else "prod",
                    "raw_payload": item,
                }
            )

        conn = get_db_connection()
        cur = conn.cursor()

        alerts_created = []
        for event_dict in normalized_events:
            alerts_created.extend(ingest_normalized_event(event_dict, conn, cur))

        conn.commit()

        playbook_result = _create_playbook_executions_for_alerts(alerts_created, conn)
        playbook_claimed_alert_ids = _playbook_claimed_alert_ids(playbook_result)

        try:
            enqueue_committed_alerts(
                alerts_created,
                conn,
                exclude_alert_ids=playbook_claimed_alert_ids,
            )
            conn.commit()
        except Exception as enqueue_error:
            current_app.logger.error(
                "[SOAR ENQUEUE ERROR] Post-commit enqueue failed — ingest was committed: %s",
                enqueue_error,
            )

        try:
            created_incident_ids = _create_incidents_for_alerts(alerts_created, conn)
            conn.commit()
            _send_incident_notifications_for_incidents(created_incident_ids, conn)
            conn.commit()
        except Exception as incident_error:
            current_app.logger.error(
                "[SOAR INCIDENT FAILED] Post-commit incident creation failed — ingest was committed: %s | alerts=%s",
                incident_error,
                [(a.get("alert_id"), a.get("source_ip"), a.get("severity")) for a in alerts_created],
            )

        success_message = "Events added successfully" if len(normalized_events) > 1 else "Event added successfully"
        return jsonify({
            "message": success_message,
            "alerts_created": alerts_created,
        }), 201
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("Error in add_otel_event: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@ingest_bp.route("/ingest/pfsense", methods=["POST"])
def add_pfsense_event():
    api_key_error = require_api_key()
    if api_key_error:
        return api_key_error

    content_length = request.content_length
    if content_length is not None and content_length > MAX_PFSENSE_INGEST_BYTES:
        return jsonify({"error": "Payload too large"}), 413

    request_data = request.get_data()
    if len(request_data) > MAX_PFSENSE_INGEST_BYTES:
        return jsonify({"error": "Payload too large"}), 413

    conn = None
    cur = None

    try:
        data = request.get_json()
        if not isinstance(data, dict):
            return jsonify({"error": "Invalid JSON"}), 400

        try:
            normalized_event = validate_pfsense_normalized_event(data)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400

        conn = get_db_connection()
        cur = conn.cursor()

        policy = load_effective_policy(cur)
        decision = evaluate_event(normalized_event, policy)
        record_filter_decision(decision)
        if not decision.retain:
            conn.rollback()
            current_app.logger.info(
                "pfsense_ingest_filter decision=filtered category=%s reason=%s config_status=%s",
                decision.category,
                decision.reason,
                policy["status"],
            )
            return jsonify({
                "status": "filtered",
                "category": decision.category,
                "reason": decision.reason,
            }), 202

        _add_location_to_normalized_event(normalized_event)

        alerts_created = ingest_normalized_event(normalized_event, conn, cur)

        conn.commit()
        _enroll_recon_activity_members(alerts_created, conn)
        conn.commit()
        _send_recon_activity_notifications_for_alerts(alerts_created, conn)
        conn.commit()
        for alert in alerts_created:
            alert_id = alert.get("alert_id")
            if not alert_id:
                continue
            alert_context = fetch_alert_context(conn, int(alert_id))
            if not isinstance(alert_context, dict):
                continue
            alert_context_payload = alert_context.get("context")
            if isinstance(alert_context_payload, dict):
                alert["context"] = alert_context_payload
            alert_type = alert_context.get("alert_type")
            if isinstance(alert_type, str) and alert_type:
                alert["alert_type"] = alert_type

        playbook_result = _create_playbook_executions_for_alerts(alerts_created, conn)
        playbook_claimed_alert_ids = _playbook_claimed_alert_ids(playbook_result)

        try:
            enqueue_committed_alerts(
                alerts_created,
                conn,
                exclude_alert_ids=playbook_claimed_alert_ids,
            )
            conn.commit()
        except Exception as enqueue_error:
            current_app.logger.error(
                "[SOAR ENQUEUE ERROR] Post-commit enqueue failed — ingest was committed: %s",
                enqueue_error,
            )

        try:
            created_incident_ids = _create_incidents_for_alerts(alerts_created, conn)
            conn.commit()
            _send_incident_notifications_for_incidents(created_incident_ids, conn)
            conn.commit()
        except Exception as incident_error:
            current_app.logger.error(
                "[SOAR INCIDENT FAILED] Post-commit incident creation failed — ingest was committed: %s | alerts=%s",
                incident_error,
                [(a.get("alert_id"), a.get("source_ip"), a.get("severity")) for a in alerts_created],
            )

        return jsonify({
            "message": "pfSense event ingested successfully",
            "alerts_created": alerts_created,
        }), 201
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("Error in add_pfsense_event: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
