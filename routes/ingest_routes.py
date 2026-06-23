import ipaddress
import logging

from flask import Blueprint, current_app, jsonify, request

from adapters.azure_insights_adapter import (
    normalize_azure_identity_telemetry,
    normalize_azure_insights_telemetry,
)
from adapters.nginx_adapter import parse_nginx_access_log_line
from adapters.otel_adapter import normalize_otel_telemetry
from helpers.api_guards import require_api_key, require_azure_api_key, require_otel_api_key
from core.db import get_db_connection
from core.extensions import limiter
from core.incident_store import maybe_create_or_link_incident
from engines.ingest_engine import ingest_normalized_event
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


def _create_incidents_for_alerts(alerts_created, conn):
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
            maybe_create_or_link_incident(conn, alert_id, severity, str(source_ip))
        except Exception as incident_error:
            logger.error(
                "[SOAR INCIDENT FAILED] %s | alert_id=%s source_ip=%s severity=%s",
                incident_error,
                alert_id,
                source_ip,
                severity,
            )


def _create_playbook_executions_for_alerts(alerts_created, conn):
    try:
        create_pending_executions_for_committed_alerts(alerts_created, conn)
        conn.commit()
    except Exception as playbook_error:
        conn.rollback()
        current_app.logger.error(
            "[PLAYBOOK ORCHESTRATION ERROR] Post-commit playbook scheduling failed — ingest was committed: %s",
            playbook_error,
        )


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

        try:
            enqueue_committed_alerts(alerts_created, conn)
            conn.commit()
        except Exception as enqueue_error:
            current_app.logger.error(
                "[SOAR ENQUEUE ERROR] Post-commit enqueue failed — ingest was committed: %s",
                enqueue_error,
            )

        try:
            _create_incidents_for_alerts(alerts_created, conn)
            conn.commit()
        except Exception as incident_error:
            current_app.logger.error(
                "[SOAR INCIDENT FAILED] Post-commit incident creation failed — ingest was committed: %s | alerts=%s",
                incident_error,
                [(a.get("alert_id"), a.get("source_ip"), a.get("severity")) for a in alerts_created],
            )

        _create_playbook_executions_for_alerts(alerts_created, conn)

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

        conn = get_db_connection()
        cur = conn.cursor()

        alerts_created = ingest_normalized_event(normalized_event, conn, cur)

        conn.commit()

        try:
            enqueue_committed_alerts(alerts_created, conn)
            conn.commit()
        except Exception as enqueue_error:
            current_app.logger.error(
                "[SOAR ENQUEUE ERROR] Post-commit enqueue failed — ingest was committed: %s",
                enqueue_error,
            )

        try:
            _create_incidents_for_alerts(alerts_created, conn)
            conn.commit()
        except Exception as incident_error:
            current_app.logger.error(
                "[SOAR INCIDENT FAILED] Post-commit incident creation failed — ingest was committed: %s | alerts=%s",
                incident_error,
                [(a.get("alert_id"), a.get("source_ip"), a.get("severity")) for a in alerts_created],
            )

        _create_playbook_executions_for_alerts(alerts_created, conn)

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

        try:
            enqueue_committed_alerts(alerts_created, conn)
            conn.commit()
        except Exception as enqueue_error:
            current_app.logger.error(
                "[SOAR ENQUEUE ERROR] Post-commit enqueue failed — ingest was committed: %s",
                enqueue_error,
            )

        try:
            _create_incidents_for_alerts(alerts_created, conn)
            conn.commit()
        except Exception as incident_error:
            current_app.logger.error(
                "[SOAR INCIDENT FAILED] Post-commit incident creation failed — ingest was committed: %s | alerts=%s",
                incident_error,
                [(a.get("alert_id"), a.get("source_ip"), a.get("severity")) for a in alerts_created],
            )

        _create_playbook_executions_for_alerts(alerts_created, conn)

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
            alerts_created.extend(ingest_normalized_event(event_dict, conn, cur))

        conn.commit()

        try:
            enqueue_committed_alerts(alerts_created, conn)
            conn.commit()
        except Exception as enqueue_error:
            current_app.logger.error(
                "[SOAR ENQUEUE ERROR] Post-commit enqueue failed — ingest was committed: %s",
                enqueue_error,
            )

        try:
            _create_incidents_for_alerts(alerts_created, conn)
            conn.commit()
        except Exception as incident_error:
            current_app.logger.error(
                "[SOAR INCIDENT FAILED] Post-commit incident creation failed — ingest was committed: %s | alerts=%s",
                incident_error,
                [(a.get("alert_id"), a.get("source_ip"), a.get("severity")) for a in alerts_created],
            )

        _create_playbook_executions_for_alerts(alerts_created, conn)

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

        try:
            enqueue_committed_alerts(alerts_created, conn)
            conn.commit()
        except Exception as enqueue_error:
            current_app.logger.error(
                "[SOAR ENQUEUE ERROR] Post-commit enqueue failed — ingest was committed: %s",
                enqueue_error,
            )

        try:
            _create_incidents_for_alerts(alerts_created, conn)
            conn.commit()
        except Exception as incident_error:
            current_app.logger.error(
                "[SOAR INCIDENT FAILED] Post-commit incident creation failed — ingest was committed: %s | alerts=%s",
                incident_error,
                [(a.get("alert_id"), a.get("source_ip"), a.get("severity")) for a in alerts_created],
            )

        _create_playbook_executions_for_alerts(alerts_created, conn)

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
