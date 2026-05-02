from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from psycopg2.extras import Json
from dotenv import load_dotenv
from backend_auth import (
    User,
    admin_required,
    analyst_or_super_admin_required,
    get_user_by_username,
    load_user,
    super_admin_required,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash
import logging
import os
import ipaddress
import csv
from io import StringIO
from datetime import datetime, timezone
import psycopg2
from backend_audit_helpers import log_audit_event
from backend_db import create_blocked_ip_record, get_db_connection, validate_blocked_ip
from backend_detection_config import (
    APPLICATION_EXCEPTION_THRESHOLD,
    APPLICATION_EXCEPTION_WINDOW_MINUTES,
    DETECTION_THRESHOLD_MAX,
    DETECTION_THRESHOLD_MIN,
    DETECTION_WINDOW_MINUTES_MAX,
    DETECTION_WINDOW_MINUTES_MIN,
    FAILED_LOGIN_THRESHOLD,
    FAILED_LOGIN_WINDOW_MINUTES,
    HIGH_REQUEST_RATE_THRESHOLD,
    HIGH_REQUEST_RATE_WINDOW_MINUTES,
    HTTP_ERROR_THRESHOLD,
    HTTP_ERROR_WINDOW_MINUTES,
    PASSWORD_SPRAY_THRESHOLD,
    PASSWORD_SPRAY_WINDOW_MINUTES,
    PORT_SCAN_THRESHOLD,
    PORT_SCAN_WINDOW_MINUTES,
    SUCCESS_AFTER_SPRAY_CORRELATION_WINDOW_MINUTES,
    SUCCESS_AFTER_SPRAY_FAILED_LOOKBACK_MINUTES,
    SUCCESS_AFTER_SPRAY_SUCCESS_WINDOW_MINUTES,
    SUCCESS_AFTER_SPRAY_THRESHOLD,
    get_all_effective_detection_rules,
    get_detection_rule_defaults,
    get_effective_detection_rule,
    parse_detection_rule_parameters,
    validate_detection_rule_config,
)
from backend_correlation_engine import generate_correlated_activity_alerts, generate_targeted_correlation_alerts
from backend_enrichment_helpers import enrich_alert_with_correlation_context, enrich_alert_with_mitre
from backend_ip_helpers import (
    determine_response_action,
    execute_response_action,
    get_ip_reputation,
    lookup_ip_location,
    lookup_ip_reputation,
)
from backend_pdf_helpers import build_pdf_report_response
from backend_ingest_normalizers import (
    _get_azure_app_name,
    _get_azure_identity_app_name,
    _get_otel_app_name,
    _is_azure_identity_payload,
    _safe_non_empty_string,
    has_valid_location,
)
from backend_api_guards import require_api_key, require_azure_api_key, require_otel_api_key
from backend_query_helpers import fetch_alert_csv_rows, fetch_alert_rows, fetch_response_logs_by_alert_id
from backend_reporting_helpers import (
    build_alert_report_sections,
    build_alert_summary,
    build_confidence_level,
    build_next_steps,
    build_report_header,
    build_severity_explanation,
    format_csv_timestamp,
    format_display_value,
    format_pdf_timestamp,
    format_report_timestamp,
    normalize_alert_report_data,
)
from adapters.azure_insights_adapter import (
    normalize_azure_identity_telemetry,
    normalize_azure_insights_telemetry,
)
from adapters.nginx_adapter import parse_nginx_access_log_line
from adapters.otel_adapter import normalize_otel_telemetry


# ============================================================================
# Imports / Environment Helpers
# ============================================================================


def env_first(*names, default=None):
    for name in names:
        value = os.getenv(name)
        if value not in (None, ""):
            return value
    return default


def env_csv(*names, default=None):
    raw_value = env_first(*names)
    if raw_value is None:
        return list(default or [])
    return [item.strip() for item in raw_value.split(",") if item.strip()]


# ============================================================================
# Constants / Validation Sets
# ============================================================================


DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
]

# Runtime / deployment settings.
SIEM_ALLOWED_ORIGINS = env_csv("SIEM_ALLOWED_ORIGINS", default=DEFAULT_ALLOWED_ORIGINS)
SIEM_BIND_HOST = env_first("SIEM_BIND_HOST", default="0.0.0.0")
SIEM_PORT = int(env_first("SIEM_PORT", default="5051"))
SIEM_DEBUG = env_first("SIEM_DEBUG", default="false").strip().lower() == "true"

def backfill_alert_sources(conn, cur):
    cur.execute(
        """
        WITH source_matches AS (
            SELECT
                a.id AS alert_id,
                event_meta.source,
                event_meta.source_type
            FROM alerts a
            JOIN LATERAL (
                SELECT e.source, e.source_type
                FROM events e
                WHERE e.source_ip = a.source_ip
                ORDER BY e.created_at ASC
                LIMIT 1
            ) AS event_meta ON TRUE
            WHERE a.source IS NULL
        )
        UPDATE alerts a
        SET
            source = source_matches.source,
            source_type = source_matches.source_type
        FROM source_matches
        WHERE a.id = source_matches.alert_id
        """
    )

    updated_count = cur.rowcount
    print(f"Updated {updated_count} alerts with source attribution")
    return updated_count



# ============================================================================
# Flask App Setup
# ============================================================================


load_dotenv()

app = Flask(__name__, static_folder="frontend/build/static")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[]
)
FRONTEND_BUILD_DIR = os.path.join(app.root_path, "frontend", "build")
app.config["SECRET_KEY"] = env_first("SIEM_SECRET_KEY", "SECRET_KEY")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = not SIEM_DEBUG

admin_username = env_first("SIEM_ADMIN_USERNAME", "ADMIN_USERNAME")
admin_password = env_first("SIEM_ADMIN_PASSWORD", "ADMIN_PASSWORD")

if not admin_username or not admin_password:
    raise RuntimeError("Missing ADMIN_USERNAME or ADMIN_PASSWORD environment variables")

CORS(app, resources={r"/*": {"origins": SIEM_ALLOWED_ORIGINS}}, supports_credentials=True)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


@login_manager.unauthorized_handler
def unauthorized():
    return jsonify({"error": "Unauthorized"}), 401


@app.errorhandler(429)
def handle_rate_limit(_error):
    return jsonify({
        "error": "rate_limited",
        "message": "Too many requests. Please try again later."
    }), 429



login_manager.user_loader(load_user)


# ============================================================================
# Auth / RBAC / Admin Routes
# ============================================================================


@app.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
def login():
    data = request.get_json() or {}

    username = data.get("username")
    password = data.get("password")

    if username == admin_username and password == admin_password:
        user = User("admin", role="super_admin")
        login_user(user)
        log_audit_event(
            "login_success",
            actor_username="admin",
            actor_role="super_admin",
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
        )
        return jsonify({"message": "Login successful"}), 200

    viewer_user = get_user_by_username(username)
    if not viewer_user or not viewer_user["is_active"]:
        log_audit_event(
            "login_failure",
            actor_username=username or None,
            actor_role=None,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={"reason": "invalid_credentials"},
        )
        return jsonify({"error": "Invalid credentials"}), 401

    if not check_password_hash(viewer_user["password_hash"], password):
        log_audit_event(
            "login_failure",
            actor_username=username or None,
            actor_role=None,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={"reason": "invalid_credentials"},
        )
        return jsonify({"error": "Invalid credentials"}), 401

    user = User(viewer_user["username"], role=viewer_user["role"])
    login_user(user)
    log_audit_event(
        "login_success",
        actor_username=viewer_user["username"],
        actor_role=viewer_user["role"],
        http_method=request.method,
        request_path=request.path,
        source_ip=request.remote_addr,
    )

    return jsonify({"message": "Login successful"}), 200


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    log_audit_event(
        "LOGOUT",
        actor_username=current_user.id,
        actor_role=current_user.role,
        http_method=request.method,
        request_path=request.path,
        source_ip=request.remote_addr,
    )
    logout_user()
    return jsonify({"message": "Logout successful"}), 200


@app.route("/auth/me", methods=["GET"])
def auth_me():
    if current_user.is_authenticated:
        return jsonify({
            "authenticated": True,
            "user": current_user.id,
            "role": current_user.role,
        }), 200

    return jsonify({
        "authenticated": False
    }), 200


@app.route("/admin/users", methods=["POST"])
@limiter.limit("30 per minute")
@login_required
@super_admin_required
def create_user():
    data = request.get_json() or {}

    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    role = (data.get("role") or "viewer").strip().lower()

    if not username or not password.strip():
        return jsonify({"error": "Username and password are required"}), 400

    if role not in {"viewer", "analyst"}:
        return jsonify({"error": "Invalid role"}), 400

    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users (username, password_hash, role, is_active)
            VALUES (%s, %s, %s, %s)
            """,
            (username, generate_password_hash(password), role, True),
        )
        conn.commit()
        log_audit_event(
            "user_create",
            actor_username=current_user.id,
            actor_role=current_user.role,
            target_username=username,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
        )

        app.logger.info("Admin created user username=%s role=%s", username, role)
        return jsonify({"message": "User created successfully"}), 201
    except psycopg2.IntegrityError:
        if conn:
            conn.rollback()
        return jsonify({"error": "Unable to create user"}), 409
    except Exception:
        if conn:
            conn.rollback()
        return jsonify({"error": "Unable to create user"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route("/admin/users", methods=["GET"])
@limiter.limit("30 per minute")
@login_required
@super_admin_required
def list_users():
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT username, role, is_active, created_at
            FROM users
            ORDER BY created_at ASC
            """
        )

        rows = cur.fetchall()
        users = [
            {
                "username": row[0],
                "role": row[1],
                "is_active": row[2],
                "created_at": str(row[3]),
            }
            for row in rows
        ]

        log_audit_event(
            "VIEW_ADMIN_USERS",
            actor_username=current_user.id,
            actor_role=current_user.role,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
        )
        return jsonify(users), 200
    except Exception:
        return jsonify({"error": "Unable to list users"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route("/admin/users/<username>/status", methods=["PATCH"])
@limiter.limit("30 per minute")
@login_required
@super_admin_required
def update_user_status(username):
    if username == current_user.id:
        return jsonify({"error": "Cannot modify your own account"}), 400

    data = request.get_json() or {}
    is_active = data.get("is_active")

    if not isinstance(is_active, bool):
        return jsonify({"error": "is_active must be a boolean"}), 400

    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE users
            SET is_active = %s
            WHERE username = %s
            """,
            (is_active, username),
        )

        if cur.rowcount == 0:
            conn.rollback()
            return jsonify({"error": "User not found"}), 404

        conn.commit()
        log_audit_event(
            "user_activate" if is_active else "user_deactivate",
            actor_username=current_user.id,
            actor_role=current_user.role,
            target_username=username,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
        )
        log_audit_event(
            "USER_STATUS_CHANGE",
            actor_username=current_user.id,
            actor_role=current_user.role,
            target_username=username,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={"is_active": is_active},
        )
        return jsonify({"message": "User status updated successfully"}), 200
    except Exception:
        if conn:
            conn.rollback()
        return jsonify({"error": "Unable to update user status"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route("/admin/users/<username>/password", methods=["PATCH"])
@limiter.limit("30 per minute")
@login_required
@super_admin_required
def update_user_password(username):
    if username == current_user.id:
        return jsonify({"error": "Cannot modify your own account"}), 400

    data = request.get_json() or {}
    password = data.get("password") or ""

    if not password.strip():
        return jsonify({"error": "Password is required"}), 400

    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE users
            SET password_hash = %s
            WHERE username = %s
            """,
            (generate_password_hash(password), username),
        )

        if cur.rowcount == 0:
            conn.rollback()
            return jsonify({"error": "User not found"}), 404

        conn.commit()
        log_audit_event(
            "user_password_reset",
            actor_username=current_user.id,
            actor_role=current_user.role,
            target_username=username,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
        )
        log_audit_event(
            "PASSWORD_RESET",
            actor_username=current_user.id,
            actor_role=current_user.role,
            target_username=username,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
        )
        return jsonify({"message": "Password updated successfully"}), 200
    except Exception:
        if conn:
            conn.rollback()
        return jsonify({"error": "Unable to update password"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route("/admin/users/<username>/role", methods=["PATCH"])
@limiter.limit("30 per minute")
@login_required
@super_admin_required
def update_user_role(username):
    data = request.get_json() or {}
    role = (data.get("role") or "").strip().lower()

    if role not in {"viewer", "analyst"}:
        return jsonify({"error": "Invalid role"}), 400

    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE users
            SET role = %s
            WHERE username = %s
            """,
            (role, username),
        )

        if cur.rowcount == 0:
            conn.rollback()
            return jsonify({"error": "User not found"}), 404

        conn.commit()
        log_audit_event(
            "user_role_update",
            actor_username=current_user.id,
            actor_role=current_user.role,
            target_username=username,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={"new_role": role},
        )
        log_audit_event(
            "USER_ROLE_CHANGE",
            actor_username=current_user.id,
            actor_role=current_user.role,
            target_username=username,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={"new_role": role},
        )
        return jsonify({"message": "User role updated successfully"}), 200
    except Exception:
        if conn:
            conn.rollback()
        return jsonify({"error": "Unable to update user role"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route("/admin/audit-log", methods=["GET"])
@limiter.limit("30 per minute")
@login_required
@super_admin_required
def list_audit_log():
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                event_type,
                actor_username,
                actor_role,
                target_username,
                target_alert_id,
                request_path,
                source_ip,
                created_at
            FROM audit_log
            ORDER BY created_at DESC
            LIMIT 50
            """
        )

        rows = cur.fetchall()
        events = [
            {
                "event_type": row[0],
                "actor_username": row[1],
                "actor_role": row[2],
                "target_username": row[3],
                "target_alert_id": row[4],
                "request_path": row[5],
                "source_ip": str(row[6]) if row[6] is not None else None,
                "created_at": str(row[7]),
            }
            for row in rows
        ]

        return jsonify(events), 200
    except Exception:
        return jsonify({"error": "Unable to list audit log"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route("/admin/detection-rules", methods=["GET"])
@login_required
@super_admin_required
def list_detection_rules():
    return jsonify(get_all_effective_detection_rules()), 200


@app.route("/admin/detection-rules/<rule_id>", methods=["PATCH"])
@login_required
@super_admin_required
def update_detection_rule(rule_id):
    defaults = get_detection_rule_defaults()
    if rule_id not in defaults:
        return jsonify({"error": "Detection rule not found"}), 404

    payload = request.get_json()
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid JSON"}), 400

    if "active" in payload:
        return jsonify({"error": "Active status cannot be updated in this phase"}), 400

    if "parameters" not in payload:
        return jsonify({"error": "Missing required field: parameters"}), 400

    conn = None
    cur = None

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        old_effective_rule = get_effective_detection_rule(rule_id, cur=cur)
        current_active = old_effective_rule["active"]

        try:
            validated = validate_detection_rule_config(
                rule_id,
                payload.get("parameters"),
                current_active,
            )
        except ValueError as error:
            conn.rollback()
            return jsonify({"error": str(error)}), 400

        normalized_parameters = validated["parameters"]
        changes = []
        all_parameter_keys = set(old_effective_rule["parameters"].keys()) | set(normalized_parameters.keys())

        for key in sorted(all_parameter_keys):
            old_value = old_effective_rule["parameters"].get(key)
            new_value = normalized_parameters.get(key, old_value)
            if old_value != new_value:
                changes.append({
                    "field": key,
                    "old": old_value,
                    "new": new_value,
                })

        cur.execute(
            """
            INSERT INTO detection_config (rule_id, parameters, updated_by, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (rule_id) DO UPDATE
            SET
                parameters = EXCLUDED.parameters,
                updated_by = EXCLUDED.updated_by,
                updated_at = NOW()
            """,
            (
                rule_id,
                Json(normalized_parameters),
                current_user.id,
            ),
        )

        updated_effective_rule = get_effective_detection_rule(rule_id, cur=cur)
        conn.commit()

        log_audit_event(
            "detection_rule_updated",
            actor_username=current_user.id,
            actor_role=current_user.role,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={
                "rule_id": rule_id,
                "old_parameters": old_effective_rule["parameters"],
                "new_parameters": updated_effective_rule["parameters"],
                "changes": changes,
                "actor": current_user.id,
            },
        )

        return jsonify(updated_effective_rule), 200
    except Exception as error:
        if conn:
            conn.rollback()
        app.logger.error("Unable to update detection rule rule_id=%s: %s", rule_id, error)
        return jsonify({"error": "Unable to update detection rule"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


logging.basicConfig(level=logging.INFO)


VALID_SEVERITIES = {"low", "medium", "high", "critical"}
VALID_EVENT_TYPES = {"failed_login", "login_failure", "successful_login", "port_scan", "normal_activity"}
VALID_EVENT_SEARCH_TYPES = VALID_EVENT_TYPES | {
    "unauthorized_access",
    "http_error",
    "application_exception",
    "availability_failure",
}
VALID_EVENT_SOURCES = {"bank_app", "nginx", "azure_insights", "opentelemetry"}
VALID_RESPONSE_ACTIONS = {"block_ip", "monitor", "flag_high_priority"}
MAX_ALERT_NOTE_LENGTH = 2000


# ============================================================================
# Ingestion Routes
# ============================================================================

# Event validation sets used by ingest endpoints and search APIs.

# Central normalized event write path.
def ingest_normalized_event(event_dict, conn, cur):
    # Central normalized ingestion path. Adapters and raw ingest routes feed
    # this function, and detector/correlation fan-out happens here.
    event_type = event_dict["event_type"]
    severity = event_dict["severity"]
    source_ip = event_dict["source_ip"]
    source = event_dict.get("source", "bank_app")
    source_type = event_dict.get("source_type", "custom")
    event_timestamp = event_dict.get("event_timestamp")
    message = event_dict["message"]
    app_name = event_dict["app_name"]
    environment = event_dict["environment"]
    raw_payload = event_dict["raw_payload"]

    cur.execute(
        """
        INSERT INTO events (
            event_type,
            severity,
            source_ip,
            source,
            source_type,
            event_timestamp,
            message,
            app_name,
            environment,
            raw_payload
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            event_type,
            severity,
            source_ip,
            source,
            source_type,
            event_timestamp,
            message,
            app_name,
            environment,
            Json(raw_payload),
        ),
    )

    alerts_created = []

    if event_type == "failed_login":
        alerts_created = _generate_failed_login_alerts_core(cur, conn, source=source, source_type=source_type)
        alerts_created.extend(_generate_password_spraying_alerts_core(cur, conn, source=source, source_type=source_type))
        alerts_created.extend(
            _generate_successful_login_after_spray_alerts_core(cur, conn, source=source, source_type=source_type)
        )
    elif event_type == "unauthorized_access":
        alerts_created = _generate_failed_login_alerts_core(cur, conn, source=source, source_type=source_type)
        if source_type in {"web_log", "telemetry"}:
            alerts_created.extend(
                _generate_high_request_rate_alerts_core(cur, conn, source=source, source_type=source_type)
            )
    elif event_type == "http_error":
        alerts_created = _generate_http_error_alerts_core(cur, conn, source=source, source_type=source_type)
        if source_type in {"web_log", "telemetry"}:
            alerts_created.extend(
                _generate_high_request_rate_alerts_core(cur, conn, source=source, source_type=source_type)
            )
    elif event_type == "application_exception":
        alerts_created = _generate_application_exception_alerts_core(cur, conn, source=source, source_type=source_type)
    elif event_type == "normal_activity":
        if source_type in {"web_log", "telemetry"}:
            alerts_created = _generate_high_request_rate_alerts_core(cur, conn, source=source, source_type=source_type)
    elif event_type == "successful_login":
        alerts_created.extend(
            _generate_successful_login_after_spray_alerts_core(cur, conn, source=source, source_type=source_type)
        )
    elif event_type == "port_scan":
        alerts_created = _generate_port_scan_alerts_core(cur, conn, source=source, source_type=source_type)

    for correlated_source_ip in {
        str(alert.get("source_ip"))
        for alert in alerts_created
        if alert.get("source_ip") is not None
    }:
        generate_correlated_activity_alerts(cur, conn, correlated_source_ip)
        generate_targeted_correlation_alerts(cur, conn, correlated_source_ip)

    return alerts_created


@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "service": "siem_dashboard"}), 200


@app.route("/ingest", methods=["POST"])
@limiter.limit("200 per minute")
def add_event():
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


@app.route("/ingest/web-log", methods=["POST"])
def add_web_log_event():
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

        return jsonify({
            "message": "Event added successfully",
            "alerts_created": alerts_created
        }), 201
    except Exception as error:
        if conn:
            conn.rollback()
        app.logger.error("Error in add_web_log_event: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route("/ingest/azure", methods=["POST"])
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
                app.logger.warning(
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

        success_message = "Events added successfully" if len(normalized_events) > 1 else "Event added successfully"
        return jsonify({
            "message": success_message,
            "alerts_created": alerts_created,
        }), 201
    except Exception as error:
        if conn:
            conn.rollback()
        app.logger.error("Error in add_azure_event: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route("/ingest/otlp", methods=["POST"])
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

        success_message = "Events added successfully" if len(normalized_events) > 1 else "Event added successfully"
        return jsonify({
            "message": success_message,
            "alerts_created": alerts_created,
        }), 201
    except Exception as error:
        if conn:
            conn.rollback()
        app.logger.error("Error in add_otel_event: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# ============================================================================
# Detection Engine
# ============================================================================

# Each detector owns its own duplicate suppression and alert creation path.

def _generate_failed_login_alerts_core(cur, conn, source=None, source_type=None):
    rule_config = get_effective_detection_rule("failed_login_threshold", cur=cur)
    threshold = rule_config["parameters"]["threshold"]
    window_minutes = rule_config["parameters"]["window_minutes"]

    cur.execute(
        f"""
        SELECT source_ip, COUNT(*) as attempts
        FROM events
        WHERE event_type IN ('failed_login', 'login_failure', 'unauthorized_access')
        AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        GROUP BY source_ip
        HAVING COUNT(*) >= %s
        """,
        (threshold,)
    )

    rows = cur.fetchall()
    alerts_created = []

    for row in rows:
        source_ip = row[0]
        attempts = row[1]
        reputation = lookup_ip_reputation(str(source_ip))
        reputation_score = reputation["reputation_score"]
        response_action = determine_response_action(reputation_score)
        response_status = "pending"
        reputation_label = reputation["reputation_label"]
        reputation_source = reputation["reputation_source"]
        reputation_summary = reputation["reputation_summary"]


        cur.execute(
            """
            SELECT
                raw_payload->'location'->>'country',
                raw_payload->'location'->>'city',
                NULLIF(raw_payload->'location'->>'lat', '')::double precision,
                NULLIF(raw_payload->'location'->>'lon', '')::double precision
            FROM events
            WHERE source_ip = %s
              AND event_type IN ('failed_login', 'login_failure', 'unauthorized_access')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_ip,)
        )

        location_row = cur.fetchone()
        country = location_row[0] if location_row else None
        city = location_row[1] if location_row else None
        latitude = location_row[2] if location_row else None
        longitude = location_row[3] if location_row else None

        app.logger.info(
            "[ALERT LOCATION DEBUG] failed_login source_ip=%s country=%s city=%s latitude=%s longitude=%s",
            source_ip,
            country,
            city,
            latitude,
            longitude,
        )

        message = f"{attempts} failed login attempts detected from {source_ip}"

        cur.execute(
            """
            SELECT 1 FROM alerts
            WHERE source_ip = %s
            AND alert_type = %s
            AND status = 'open'
            """,
            (source_ip, "failed_login_threshold"),
        )

        if cur.fetchone():
            continue
        cur.execute(
            """
            INSERT INTO alerts (
                source_ip,
                alert_type,
                severity,
                source,
                source_type,
                message,
                status,
                response_action,
                response_status,
                country,
                city,
                latitude,
                longitude,
                reputation_score,
                reputation_label,
                reputation_source,
                reputation_summary
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                source_ip,
                "failed_login_threshold",
                "high",
                source,
                source_type,
                message,
                "open",
                response_action,
                response_status,
                country,
                city,
                latitude,
                longitude,
                reputation_score,
                reputation_label,
                reputation_source,
                reputation_summary,
            ),
        )

        cur.execute("SELECT currval(pg_get_serial_sequence('alerts', 'id'))")
        alert_id = cur.fetchone()[0]

        execution_status = execute_response_action(
            cur,
            alert_id,
            str(source_ip),
            response_action
        )

        cur.execute(
            """
            UPDATE alerts
            SET response_status = %s
            WHERE id = %s
            """,
            (execution_status, alert_id)
        )

        alerts_created.append(
            {
                "source_ip": source_ip,
                "attempts": attempts,
            }
        )

    return alerts_created


def _generate_password_spraying_alerts_core(cur, conn, source=None, source_type=None):
    rule_config = get_effective_detection_rule("password_spraying_threshold", cur=cur)
    threshold = rule_config["parameters"]["threshold"]
    window_minutes = rule_config["parameters"]["window_minutes"]

    cur.execute(
        f"""
        WITH extracted_failed_logins AS (
            SELECT
                source_ip,
                NULLIF(
                    LOWER(
                        TRIM(
                            COALESCE(
                                raw_payload->>'username',
                                SUBSTRING(raw_payload->>'message' FROM 'Failed login attempt for username:\\s*([^,;]+)')
                            )
                        )
                    ),
                    ''
                ) AS extracted_username
            FROM events
            WHERE event_type = 'failed_login'
              AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        )
        SELECT source_ip, COUNT(DISTINCT extracted_username) AS distinct_username_count
        FROM extracted_failed_logins
        WHERE extracted_username IS NOT NULL
        GROUP BY source_ip
        HAVING COUNT(DISTINCT extracted_username) >= %s
        """,
        (threshold,)
    )

    rows = cur.fetchall()
    alerts_created = []

    for row in rows:
        source_ip = row[0]
        distinct_username_count = row[1]
        reputation = lookup_ip_reputation(str(source_ip))
        reputation_score = reputation["reputation_score"]
        response_action = determine_response_action(reputation_score)
        response_status = "pending"
        reputation_label = reputation["reputation_label"]
        reputation_source = reputation["reputation_source"]
        reputation_summary = reputation["reputation_summary"]

        cur.execute(
            """
            SELECT
                raw_payload->'location'->>'country',
                raw_payload->'location'->>'city',
                NULLIF(raw_payload->'location'->>'lat', '')::double precision,
                NULLIF(raw_payload->'location'->>'lon', '')::double precision
            FROM events
            WHERE source_ip = %s
              AND event_type = 'failed_login'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_ip,)
        )

        location_row = cur.fetchone()
        country = location_row[0] if location_row else None
        city = location_row[1] if location_row else None
        latitude = location_row[2] if location_row else None
        longitude = location_row[3] if location_row else None

        message = (
            f"Password spraying suspected from {source_ip}: "
            f"failed logins across {distinct_username_count} usernames"
        )

        cur.execute(
            """
            SELECT 1 FROM alerts
            WHERE source_ip = %s
              AND alert_type = %s
              AND status = 'open'
            """,
            (source_ip, "password_spraying_threshold"),
        )

        if cur.fetchone():
            continue

        cur.execute(
            """
            INSERT INTO alerts (
                source_ip,
                alert_type,
                severity,
                source,
                source_type,
                message,
                status,
                response_action,
                response_status,
                country,
                city,
                latitude,
                longitude,
                reputation_score,
                reputation_label,
                reputation_source,
                reputation_summary
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                source_ip,
                "password_spraying_threshold",
                "high",
                source,
                source_type,
                message,
                "open",
                response_action,
                response_status,
                country,
                city,
                latitude,
                longitude,
                reputation_score,
                reputation_label,
                reputation_source,
                reputation_summary,
            ),
        )

        cur.execute("SELECT currval(pg_get_serial_sequence('alerts', 'id'))")
        alert_id = cur.fetchone()[0]

        execution_status = execute_response_action(
            cur,
            alert_id,
            str(source_ip),
            response_action
        )

        cur.execute(
            """
            UPDATE alerts
            SET response_status = %s
            WHERE id = %s
            """,
            (execution_status, alert_id)
        )

        alerts_created.append(
            {
                "source_ip": source_ip,
                "distinct_username_count": distinct_username_count,
            }
        )

    return alerts_created


def _generate_successful_login_after_spray_alerts_core(cur, conn, source=None, source_type=None):
    rule_config = get_effective_detection_rule("successful_login_after_spray", cur=cur)
    threshold = rule_config["parameters"]["threshold"]
    success_window_minutes = rule_config["parameters"]["success_window_minutes"]
    failed_lookback_minutes = rule_config["parameters"]["failed_lookback_minutes"]
    correlation_window_minutes = rule_config["parameters"]["correlation_window_minutes"]

    cur.execute(
        f"""
        WITH recent_successes AS (
            SELECT source_ip, created_at AS success_at
            FROM events
            WHERE event_type = 'successful_login'
              AND created_at >= NOW() - INTERVAL '{success_window_minutes} minutes'
        ),
        extracted_failed_logins AS (
            SELECT
                source_ip,
                created_at,
                NULLIF(
                    LOWER(
                        TRIM(
                            COALESCE(
                                raw_payload->>'username',
                                SUBSTRING(raw_payload->>'message' FROM 'Failed login attempt for username:\\s*([^,;]+)')
                            )
                        )
                    ),
                    ''
                ) AS extracted_username
            FROM events
            WHERE event_type = 'failed_login'
              AND created_at >= NOW() - INTERVAL '{failed_lookback_minutes} minutes'
        ),
        qualifying_successes AS (
            SELECT
                recent_successes.source_ip,
                MAX(recent_successes.success_at) AS success_at
            FROM recent_successes
            JOIN extracted_failed_logins
              ON extracted_failed_logins.source_ip = recent_successes.source_ip
             AND extracted_failed_logins.extracted_username IS NOT NULL
             AND extracted_failed_logins.created_at >= recent_successes.success_at - INTERVAL '{correlation_window_minutes} minutes'
             AND extracted_failed_logins.created_at <= recent_successes.success_at
            GROUP BY recent_successes.source_ip, recent_successes.success_at
            HAVING COUNT(DISTINCT extracted_failed_logins.extracted_username) >= %s
        )
        SELECT source_ip, success_at
        FROM qualifying_successes
        """,
        (threshold,)
    )

    rows = cur.fetchall()
    alerts_created = []

    for row in rows:
        source_ip = row[0]
        success_at = row[1]
        reputation = lookup_ip_reputation(str(source_ip))
        reputation_score = reputation["reputation_score"]
        response_action = determine_response_action(reputation_score)
        response_status = "pending"
        reputation_label = reputation["reputation_label"]
        reputation_source = reputation["reputation_source"]
        reputation_summary = reputation["reputation_summary"]

        cur.execute(
            """
            SELECT
                raw_payload->'location'->>'country',
                raw_payload->'location'->>'city',
                NULLIF(raw_payload->'location'->>'lat', '')::double precision,
                NULLIF(raw_payload->'location'->>'lon', '')::double precision
            FROM events
            WHERE source_ip = %s
              AND event_type IN ('successful_login', 'failed_login')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_ip,)
        )

        location_row = cur.fetchone()
        country = location_row[0] if location_row else None
        city = location_row[1] if location_row else None
        latitude = location_row[2] if location_row else None
        longitude = location_row[3] if location_row else None

        cur.execute(
            """
            SELECT 1 FROM alerts
            WHERE source_ip = %s
              AND alert_type = %s
              AND status = 'open'
            """,
            (source_ip, "successful_login_after_spray"),
        )

        if cur.fetchone():
            continue

        message = f"Successful login after password spraying detected from {source_ip}"

        cur.execute(
            """
            INSERT INTO alerts (
                source_ip,
                alert_type,
                severity,
                source,
                source_type,
                message,
                status,
                response_action,
                response_status,
                country,
                city,
                latitude,
                longitude,
                reputation_score,
                reputation_label,
                reputation_source,
                reputation_summary
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                source_ip,
                "successful_login_after_spray",
                "critical",
                source,
                source_type,
                message,
                "open",
                response_action,
                response_status,
                country,
                city,
                latitude,
                longitude,
                reputation_score,
                reputation_label,
                reputation_source,
                reputation_summary,
            ),
        )

        cur.execute("SELECT currval(pg_get_serial_sequence('alerts', 'id'))")
        alert_id = cur.fetchone()[0]

        execution_status = execute_response_action(
            cur,
            alert_id,
            str(source_ip),
            response_action
        )

        cur.execute(
            """
            UPDATE alerts
            SET response_status = %s
            WHERE id = %s
            """,
            (execution_status, alert_id)
        )

        alerts_created.append(
            {
                "source_ip": source_ip,
                "success_at": str(success_at),
            }
        )

    return alerts_created


def _generate_port_scan_alerts_core(cur, conn, source=None, source_type=None):
    rule_config = get_effective_detection_rule("port_scan_threshold", cur=cur)
    threshold = rule_config["parameters"]["threshold"]
    window_minutes = rule_config["parameters"]["window_minutes"]

    cur.execute(
        f"""
        SELECT source_ip, COUNT(*) as attempts
        FROM events
        WHERE event_type = 'port_scan'
          AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        GROUP BY source_ip
        HAVING COUNT(*) >= %s
        """,
        (threshold,)
    )

    rows = cur.fetchall()
    alerts_created = []

    for row in rows:
        source_ip = row[0]
        attempts = row[1]
        reputation = lookup_ip_reputation(str(source_ip))
        reputation_score = reputation["reputation_score"]
        response_action = determine_response_action(reputation_score)
        response_status = "pending"
        reputation_label = reputation["reputation_label"]
        reputation_source = reputation["reputation_source"]
        reputation_summary = reputation["reputation_summary"]

        cur.execute(
            """
            SELECT
                raw_payload->'location'->>'country',
                raw_payload->'location'->>'city',
                NULLIF(raw_payload->'location'->>'lat', '')::double precision,
                NULLIF(raw_payload->'location'->>'lon', '')::double precision
            FROM events
            WHERE source_ip = %s
              AND event_type = 'port_scan'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_ip,)
        )

        location_row = cur.fetchone()
        country = location_row[0] if location_row else None
        city = location_row[1] if location_row else None
        latitude = location_row[2] if location_row else None
        longitude = location_row[3] if location_row else None

        app.logger.info(
            "[ALERT LOCATION DEBUG] port_scan source_ip=%s country=%s city=%s latitude=%s longitude=%s",
            source_ip,
            country,
            city,
            latitude,
            longitude,
        )

        message = f"{attempts} port scan events detected from {source_ip}"

        cur.execute(
            """
            SELECT 1 FROM alerts
            WHERE source_ip = %s
              AND alert_type = %s
              AND status = 'open'
            """,
            (source_ip, "port_scan_threshold"),
        )

        if cur.fetchone():
            continue

        cur.execute(
            """
            INSERT INTO alerts (
                source_ip,
                alert_type,
                severity,
                source,
                source_type,
                message,
                status,
                response_action,
                response_status,
                country,
                city,
                latitude,
                longitude,
                reputation_score,
                reputation_label,
                reputation_source,
                reputation_summary
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                source_ip,
                "port_scan_threshold",
                "medium",
                source,
                source_type,
                message,
                "open",
                response_action,
                response_status,
                country,
                city,
                latitude,
                longitude,
                reputation_score,
                reputation_label,
                reputation_source,
                reputation_summary,
            ),
        )

        cur.execute("SELECT currval(pg_get_serial_sequence('alerts', 'id'))")
        alert_id = cur.fetchone()[0]

        execution_status = execute_response_action(
            cur,
            alert_id,
            str(source_ip),
            response_action
        )

        cur.execute(
            """
            UPDATE alerts
            SET response_status = %s
            WHERE id = %s
            """,
            (execution_status, alert_id)
        )

        alerts_created.append(
            {
                "source_ip": source_ip,
                "attempts": attempts,
            }
        )

    return alerts_created


def _generate_http_error_alerts_core(cur, conn, source=None, source_type=None):
    threshold = HTTP_ERROR_THRESHOLD
    window_minutes = HTTP_ERROR_WINDOW_MINUTES

    cur.execute(
        f"""
        SELECT source_ip, COUNT(*) as attempts
        FROM events
        WHERE event_type = 'http_error'
          AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        GROUP BY source_ip
        HAVING COUNT(*) >= %s
        """,
        (threshold,)
    )

    rows = cur.fetchall()
    alerts_created = []

    for row in rows:
        source_ip = row[0]
        attempts = row[1]
        reputation = lookup_ip_reputation(str(source_ip))
        reputation_score = reputation["reputation_score"]
        response_action = determine_response_action(reputation_score)
        response_status = "pending"
        reputation_label = reputation["reputation_label"]
        reputation_source = reputation["reputation_source"]
        reputation_summary = reputation["reputation_summary"]

        cur.execute(
            """
            SELECT
                raw_payload->'location'->>'country',
                raw_payload->'location'->>'city',
                NULLIF(raw_payload->'location'->>'lat', '')::double precision,
                NULLIF(raw_payload->'location'->>'lon', '')::double precision
            FROM events
            WHERE source_ip = %s
              AND event_type = 'http_error'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_ip,)
        )

        location_row = cur.fetchone()
        country = location_row[0] if location_row else None
        city = location_row[1] if location_row else None
        latitude = location_row[2] if location_row else None
        longitude = location_row[3] if location_row else None

        message = f"Repeated HTTP server errors detected from {source_ip}"

        cur.execute(
            """
            SELECT 1 FROM alerts
            WHERE source_ip = %s
              AND alert_type = %s
              AND status = 'open'
            """,
            (source_ip, "http_error_threshold"),
        )

        if cur.fetchone():
            continue

        cur.execute(
            """
            INSERT INTO alerts (
                source_ip,
                alert_type,
                severity,
                source,
                source_type,
                message,
                status,
                response_action,
                response_status,
                country,
                city,
                latitude,
                longitude,
                reputation_score,
                reputation_label,
                reputation_source,
                reputation_summary
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                source_ip,
                "http_error_threshold",
                "medium",
                source,
                source_type,
                message,
                "open",
                response_action,
                response_status,
                country,
                city,
                latitude,
                longitude,
                reputation_score,
                reputation_label,
                reputation_source,
                reputation_summary,
            ),
        )

        cur.execute("SELECT currval(pg_get_serial_sequence('alerts', 'id'))")
        alert_id = cur.fetchone()[0]

        execution_status = execute_response_action(
            cur,
            alert_id,
            str(source_ip),
            response_action
        )

        cur.execute(
            """
            UPDATE alerts
            SET response_status = %s
            WHERE id = %s
            """,
            (execution_status, alert_id)
        )

        alerts_created.append(
            {
                "source_ip": source_ip,
                "attempts": attempts,
            }
        )

    return alerts_created


def _generate_application_exception_alerts_core(cur, conn, source=None, source_type=None):
    threshold = APPLICATION_EXCEPTION_THRESHOLD
    window_minutes = APPLICATION_EXCEPTION_WINDOW_MINUTES

    cur.execute(
        f"""
        SELECT source_ip, COUNT(*) as attempts
        FROM events
        WHERE event_type = 'application_exception'
          AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        GROUP BY source_ip
        HAVING COUNT(*) >= %s
        """,
        (threshold,)
    )

    rows = cur.fetchall()
    alerts_created = []

    for row in rows:
        source_ip = row[0]
        attempts = row[1]
        reputation = lookup_ip_reputation(str(source_ip))
        reputation_score = reputation["reputation_score"]
        response_action = determine_response_action(reputation_score)
        response_status = "pending"
        reputation_label = reputation["reputation_label"]
        reputation_source = reputation["reputation_source"]
        reputation_summary = reputation["reputation_summary"]

        cur.execute(
            """
            SELECT
                raw_payload->'location'->>'country',
                raw_payload->'location'->>'city',
                NULLIF(raw_payload->'location'->>'lat', '')::double precision,
                NULLIF(raw_payload->'location'->>'lon', '')::double precision
            FROM events
            WHERE source_ip = %s
              AND event_type = 'application_exception'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_ip,)
        )

        location_row = cur.fetchone()
        country = location_row[0] if location_row else None
        city = location_row[1] if location_row else None
        latitude = location_row[2] if location_row else None
        longitude = location_row[3] if location_row else None

        message = f"Repeated application exceptions detected from {source_ip}"

        cur.execute(
            """
            SELECT 1 FROM alerts
            WHERE source_ip = %s
              AND alert_type = %s
              AND status = 'open'
            """,
            (source_ip, "application_exception_threshold"),
        )

        if cur.fetchone():
            continue

        cur.execute(
            """
            INSERT INTO alerts (
                source_ip,
                alert_type,
                severity,
                source,
                source_type,
                message,
                status,
                response_action,
                response_status,
                country,
                city,
                latitude,
                longitude,
                reputation_score,
                reputation_label,
                reputation_source,
                reputation_summary
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                source_ip,
                "application_exception_threshold",
                "high",
                source,
                source_type,
                message,
                "open",
                response_action,
                response_status,
                country,
                city,
                latitude,
                longitude,
                reputation_score,
                reputation_label,
                reputation_source,
                reputation_summary,
            ),
        )

        cur.execute("SELECT currval(pg_get_serial_sequence('alerts', 'id'))")
        alert_id = cur.fetchone()[0]

        execution_status = execute_response_action(
            cur,
            alert_id,
            str(source_ip),
            response_action
        )

        cur.execute(
            """
            UPDATE alerts
            SET response_status = %s
            WHERE id = %s
            """,
            (execution_status, alert_id)
        )

        alerts_created.append(
            {
                "source_ip": source_ip,
                "attempts": attempts,
            }
        )

    return alerts_created


def _generate_high_request_rate_alerts_core(cur, conn, source=None, source_type=None):
    threshold = HIGH_REQUEST_RATE_THRESHOLD
    window_minutes = HIGH_REQUEST_RATE_WINDOW_MINUTES

    cur.execute(
        f"""
        SELECT source_ip, COUNT(*) as attempts
        FROM events
        WHERE event_type IN ('normal_activity', 'unauthorized_access', 'http_error')
          AND source_type IN ('web_log', 'telemetry')
          AND created_at >= NOW() - INTERVAL '{window_minutes} minutes'
        GROUP BY source_ip
        HAVING COUNT(*) >= %s
        """,
        (threshold,)
    )

    rows = cur.fetchall()
    alerts_created = []

    for row in rows:
        source_ip = row[0]
        attempts = row[1]
        reputation = lookup_ip_reputation(str(source_ip))
        reputation_score = reputation["reputation_score"]
        response_action = determine_response_action(reputation_score)
        response_status = "pending"
        reputation_label = reputation["reputation_label"]
        reputation_source = reputation["reputation_source"]
        reputation_summary = reputation["reputation_summary"]

        cur.execute(
            """
            SELECT
                raw_payload->'location'->>'country',
                raw_payload->'location'->>'city',
                NULLIF(raw_payload->'location'->>'lat', '')::double precision,
                NULLIF(raw_payload->'location'->>'lon', '')::double precision
            FROM events
            WHERE source_ip = %s
              AND event_type IN ('normal_activity', 'unauthorized_access', 'http_error')
              AND source_type IN ('web_log', 'telemetry')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_ip,)
        )

        location_row = cur.fetchone()
        country = location_row[0] if location_row else None
        city = location_row[1] if location_row else None
        latitude = location_row[2] if location_row else None
        longitude = location_row[3] if location_row else None

        message = f"High request rate detected from {source_ip}"

        cur.execute(
            """
            SELECT 1 FROM alerts
            WHERE source_ip = %s
              AND alert_type = %s
              AND status = 'open'
            """,
            (source_ip, "high_request_rate_threshold"),
        )

        if cur.fetchone():
            continue

        cur.execute(
            """
            INSERT INTO alerts (
                source_ip,
                alert_type,
                severity,
                source,
                source_type,
                message,
                status,
                response_action,
                response_status,
                country,
                city,
                latitude,
                longitude,
                reputation_score,
                reputation_label,
                reputation_source,
                reputation_summary
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                source_ip,
                "high_request_rate_threshold",
                "medium",
                source,
                source_type,
                message,
                "open",
                response_action,
                response_status,
                country,
                city,
                latitude,
                longitude,
                reputation_score,
                reputation_label,
                reputation_source,
                reputation_summary,
            ),
        )

        cur.execute("SELECT currval(pg_get_serial_sequence('alerts', 'id'))")
        alert_id = cur.fetchone()[0]

        execution_status = execute_response_action(
            cur,
            alert_id,
            str(source_ip),
            response_action
        )

        cur.execute(
            """
            UPDATE alerts
            SET response_status = %s
            WHERE id = %s
            """,
            (execution_status, alert_id)
        )

        alerts_created.append(
            {
                "source_ip": source_ip,
                "attempts": attempts,
            }
        )

    return alerts_created


# ============================================================================
# Correlation Engine
# ============================================================================

# ============================================================================
# Alerts / Events APIs
# ============================================================================


@app.route("/alerts", methods=["GET"])
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
        app.logger.error("Error in get_alerts: %s", e)
        return jsonify({"error": "Internal server error"}), 500


@app.route("/events/search", methods=["GET"])
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
        app.logger.error("Error in search_events: %s", e)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route("/alerts/backfill-reputation", methods=["POST"])
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
        app.logger.error("Error in backfill_alert_reputation: %s", e)
        return jsonify({"error": "Internal server error"}), 500

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# ============================================================================
# Reporting / Export Helpers
# ============================================================================

# Reporting helpers below are formatting/rendering utilities for text, CSV, and PDF exports.

# Export routes for single-alert and filtered multi-alert report downloads.
@app.route("/alerts/<int:alert_id>/report", methods=["GET"])
@login_required
def export_alert_report(alert_id):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        alert_rows = fetch_alert_rows(cur, {"search": "", "severity": "", "status": ""})
        alert_row = next((row for row in alert_rows if row[0] == alert_id), None)

        if not alert_row:
            return jsonify({"error": "Alert not found"}), 404

        response_logs_map = fetch_response_logs_by_alert_id(cur, [alert_id])
        alert_data = normalize_alert_report_data(alert_row)
        generated_at = datetime.now(timezone.utc).isoformat()

        lines = build_report_header(generated_at, f"Single Alert (Alert ID {alert_id})")
        lines.extend(build_alert_report_sections(alert_data, response_logs_map.get(alert_id, [])))

        report_body = "\n".join(lines) + "\n"
        filename = f"incident-report-alert-{alert_id}.txt"

        log_audit_event(
            "DOWNLOAD_REPORT",
            actor_username=current_user.id,
            actor_role=current_user.role,
            target_alert_id=alert_id,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={"report_type": "txt", "scope": "single_alert"},
        )

        return Response(
            report_body,
            mimetype="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except Exception as e:
        app.logger.error("Error in export_alert_report: %s", e)
        return jsonify({"error": "Internal server error"}), 500

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route("/alerts/<int:alert_id>/report/pdf", methods=["GET"])
@login_required
def export_alert_report_pdf(alert_id):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        alert_rows = fetch_alert_rows(cur, {"search": "", "severity": "", "status": ""})
        alert_row = next((row for row in alert_rows if row[0] == alert_id), None)

        if not alert_row:
            return jsonify({"error": "Alert not found"}), 404

        response_logs_map = fetch_response_logs_by_alert_id(cur, [alert_id])
        alert_data = normalize_alert_report_data(alert_row)
        generated_at = datetime.now(timezone.utc).isoformat()
        scope = f"Single Alert (Alert ID {alert_id})"

        log_audit_event(
            "DOWNLOAD_REPORT",
            actor_username=current_user.id,
            actor_role=current_user.role,
            target_alert_id=alert_id,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={"report_type": "pdf", "scope": "single_alert"},
        )

        return build_pdf_report_response(
            f"incident-report-alert-{alert_id}.pdf",
            generated_at,
            scope,
            [
                {
                    "title": f"{alert_data['alert_type'].replace('_', ' ').title()} · Alert {alert_id}",
                    "alert_data": alert_data,
                    "response_logs": response_logs_map.get(alert_id, []),
                }
            ],
        )

    except Exception as e:
        app.logger.error("Error in export_alert_report_pdf: %s", e)
        return jsonify({"error": "Internal server error"}), 500

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route("/alerts/report", methods=["GET"])
@login_required
def export_multi_alert_report():
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        filters = {
            "search": request.args.get("search", ""),
            "severity": request.args.get("severity", ""),
            "status": request.args.get("status", ""),
        }
        alert_rows = fetch_alert_rows(cur, filters)
        alert_ids = [row[0] for row in alert_rows]
        response_logs_map = fetch_response_logs_by_alert_id(cur, alert_ids)
        generated_at = datetime.now(timezone.utc).isoformat()

        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for row in alert_rows:
            severity = (row[2] or "").lower()
            if severity in severity_counts:
                severity_counts[severity] += 1

        scope_parts = ["Filtered Alert Export"]
        if filters["search"]:
            scope_parts.append(f'search="{filters["search"]}"')
        if filters["severity"] and filters["severity"].lower() != "all":
            scope_parts.append(f'severity={filters["severity"]}')
        if filters["status"] and filters["status"].lower() != "all":
            scope_parts.append(f'status={filters["status"]}')
        scope_text = " | ".join(scope_parts)

        lines = build_report_header(generated_at, scope_text)
        lines.extend([
            "SUMMARY",
            "=======",
            f"Total Alerts: {len(alert_rows)}",
            f"Critical Alerts: {severity_counts['critical']}",
            f"High Alerts: {severity_counts['high']}",
            f"Medium Alerts: {severity_counts['medium']}",
            f"Low Alerts: {severity_counts['low']}",
            "",
        ])

        if alert_rows:
            lines.append("The report includes all alerts matching the current dashboard filters at the time of export.")
        else:
            lines.append("No alerts matched the current dashboard filters at the time of export.")

        for index, row in enumerate(alert_rows, start=1):
            alert_data = normalize_alert_report_data(row)
            lines.extend([
                "",
                f"ALERT {index}",
                "-------",
            ])
            lines.extend(build_alert_report_sections(alert_data, response_logs_map.get(row[0], [])))

        report_body = "\n".join(lines) + "\n"
        filename = "incident-report-alerts.txt"

        log_audit_event(
            "DOWNLOAD_REPORT",
            actor_username=current_user.id,
            actor_role=current_user.role,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={"report_type": "txt", "scope": "filtered_alerts"},
        )

        return Response(
            report_body,
            mimetype="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except Exception as e:
        app.logger.error("Error in export_multi_alert_report: %s", e)
        return jsonify({"error": "Internal server error"}), 500

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route("/alerts/export/csv", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def export_alerts_csv():
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        filters = {
            "search": request.args.get("search", ""),
            "severity": request.args.get("severity", ""),
            "status": request.args.get("status", ""),
        }
        alert_rows = fetch_alert_csv_rows(cur, filters)

        string_io = StringIO()
        writer = csv.writer(string_io)
        writer.writerow(["id", "alert_type", "severity", "source_ip", "status", "created_at", "environment", "message"])

        for row in alert_rows:
            writer.writerow([
                row[0],
                row[1],
                row[2],
                str(row[3]) if row[3] is not None else "",
                row[4],
                format_csv_timestamp(row[5]),
                row[7] or "",
                row[6],
            ])

        csv_body = string_io.getvalue()
        string_io.close()
        filename = f"alerts-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.csv"

        return Response(
            csv_body,
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        app.logger.error("Error in export_alerts_csv: %s", e)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route("/alerts/report/pdf", methods=["GET"])
@login_required
def export_multi_alert_report_pdf():
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        filters = {
            "search": request.args.get("search", ""),
            "severity": request.args.get("severity", ""),
            "status": request.args.get("status", ""),
        }
        alert_rows = fetch_alert_rows(cur, filters)
        alert_ids = [row[0] for row in alert_rows]
        response_logs_map = fetch_response_logs_by_alert_id(cur, alert_ids)
        generated_at = datetime.now(timezone.utc).isoformat()

        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for row in alert_rows:
            severity = (row[2] or "").lower()
            if severity in severity_counts:
                severity_counts[severity] += 1

        scope_parts = ["Filtered Alert Export"]
        if filters["search"]:
            scope_parts.append(f'search="{filters["search"]}"')
        if filters["severity"] and filters["severity"].lower() != "all":
            scope_parts.append(f'severity={filters["severity"]}')
        if filters["status"] and filters["status"].lower() != "all":
            scope_parts.append(f'status={filters["status"]}')
        scope_text = " | ".join(scope_parts)

        summary_note = (
            "The report includes all alerts matching the current dashboard filters at the time of export."
            if alert_rows
            else "No alerts matched the current dashboard filters at the time of export."
        )
        alert_sections = []
        for index, row in enumerate(alert_rows, start=1):
            alert_data = normalize_alert_report_data(row)
            alert_sections.append(
                {
                    "title": f"Alert {index} · {alert_data['alert_type'].replace('_', ' ').title()}",
                    "alert_data": alert_data,
                    "response_logs": response_logs_map.get(row[0], []),
                }
            )

        log_audit_event(
            "DOWNLOAD_REPORT",
            actor_username=current_user.id,
            actor_role=current_user.role,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={"report_type": "pdf", "scope": "filtered_alerts"},
        )

        return build_pdf_report_response(
            "incident-report-alerts.pdf",
            generated_at,
            scope_text,
            alert_sections,
            severity_counts=severity_counts,
            summary_note=summary_note,
        )

    except Exception as e:
        app.logger.error("Error in export_multi_alert_report_pdf: %s", e)
        return jsonify({"error": "Internal server error"}), 500

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# ============================================================================
# Response Actions / Notes / Blocklist
# ============================================================================


@app.route("/alerts/<int:alert_id>/response-log", methods=["GET"])
@login_required
def get_response_log(alert_id):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, alert_id, source_ip, action, status, details, executed_at
            FROM response_actions_log
            WHERE alert_id = %s
            ORDER BY executed_at DESC
            """,
            (alert_id,)
        )

        rows = cur.fetchall()

        logs = [
            {
                "id": row[0],
                "alert_id": row[1],
                "source_ip": row[2],
                "action": row[3],
                "status": row[4],
                "details": row[5],
                "executed_at": str(row[6])
            }
            for row in rows
        ]

        return jsonify(logs)

    except Exception as e:
        app.logger.error("Error in get_response_log: %s", e)
        return jsonify({"error": "Internal server error"}), 500

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route("/alerts/<int:alert_id>/notes", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def get_alert_notes(alert_id):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, alert_id, author, note_text, created_at
            FROM alert_notes
            WHERE alert_id = %s
            ORDER BY created_at DESC
            """,
            (alert_id,)
        )

        rows = cur.fetchall()
        notes = [
            {
                "id": row[0],
                "alert_id": row[1],
                "author": row[2],
                "note_text": row[3],
                "created_at": str(row[4]),
            }
            for row in rows
        ]

        return jsonify(notes), 200
    except Exception as e:
        app.logger.error("Error in get_alert_notes: %s", e)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route("/alerts/<int:alert_id>/notes", methods=["POST"])
@limiter.limit("30 per minute")
@login_required
@analyst_or_super_admin_required
def add_alert_note(alert_id):
    conn = None
    cur = None
    try:
        data = request.get_json() or {}
        note_text = (data.get("note_text") or "").strip()

        if not note_text:
            return jsonify({"error": "note_text is required"}), 400

        if len(note_text) > MAX_ALERT_NOTE_LENGTH:
            return jsonify({"error": f"note_text must be {MAX_ALERT_NOTE_LENGTH} characters or fewer"}), 400

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT 1
            FROM alerts
            WHERE id = %s
            """,
            (alert_id,)
        )

        if not cur.fetchone():
            return jsonify({"error": "Alert not found"}), 404

        cur.execute(
            """
            INSERT INTO alert_notes (alert_id, author, note_text)
            VALUES (%s, %s, %s)
            RETURNING id, alert_id, author, note_text, created_at
            """,
            (alert_id, current_user.id, note_text)
        )

        row = cur.fetchone()
        conn.commit()

        return jsonify({
            "id": row[0],
            "alert_id": row[1],
            "author": row[2],
            "note_text": row[3],
            "created_at": str(row[4]),
        }), 201
    except Exception as e:
        if conn:
            conn.rollback()
        app.logger.error("Error in add_alert_note: %s", e)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route("/blocked-ips", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def list_blocked_ips():
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, ip_address, reason, status, created_by, created_at, expires_at, source_alert_id
            FROM blocked_ips
            ORDER BY created_at DESC
            """
        )

        rows = cur.fetchall()
        blocked_ips = [
            {
                "id": row[0],
                "ip_address": str(row[1]) if row[1] is not None else None,
                "reason": row[2],
                "status": row[3],
                "created_by": row[4],
                "created_at": str(row[5]),
                "expires_at": str(row[6]) if row[6] is not None else None,
                "source_alert_id": row[7],
            }
            for row in rows
        ]

        return jsonify(blocked_ips), 200
    except Exception as error:
        app.logger.error("Error in list_blocked_ips: %s", error)
        return jsonify({"error": "Unable to list blocked IPs"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route("/blocked-ips", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def add_blocked_ip():
    conn = None
    cur = None

    try:
        data = request.get_json() or {}
        ip_address = data.get("ip_address")
        reason = (data.get("reason") or "").strip() or None
        source_alert_id = data.get("source_alert_id")
        expires_at = (data.get("expires_at") or "").strip()
        parsed_expires_at = None

        if expires_at:
            try:
                parsed_expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            except ValueError:
                return jsonify({"error": "Invalid expires_at"}), 400

        conn = get_db_connection()
        cur = conn.cursor()

        block_id = create_blocked_ip_record(
            cur,
            ip_address,
            created_by=current_user.id,
            reason=reason,
            source_alert_id=source_alert_id,
            expires_at=parsed_expires_at,
        )
        normalized_ip = validate_blocked_ip(ip_address)
        conn.commit()

        log_audit_event(
            "block_ip_added",
            actor_username=current_user.id,
            actor_role=current_user.role,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={
                "ip_address": normalized_ip,
                "reason": reason,
                "actor": current_user.id,
                "source_alert_id": source_alert_id,
                "block_id": block_id,
            },
        )

        return jsonify({"message": "Blocked IP added successfully", "id": block_id}), 201
    except ValueError as error:
        if conn:
            conn.rollback()
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        if conn:
            conn.rollback()
        app.logger.error("Error in add_blocked_ip: %s", error)
        return jsonify({"error": "Unable to add blocked IP"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route("/blocked-ips/<int:block_id>/unblock", methods=["PATCH"])
@login_required
@analyst_or_super_admin_required
def unblock_blocked_ip(block_id):
    conn = None
    cur = None

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ip_address, reason, source_alert_id, status
            FROM blocked_ips
            WHERE id = %s
            """,
            (block_id,),
        )
        row = cur.fetchone()

        if not row:
            return jsonify({"error": "Blocked IP entry not found"}), 404

        if row[3] != "active":
            return jsonify({"error": "Blocked IP entry is not active"}), 400

        cur.execute(
            """
            UPDATE blocked_ips
            SET status = 'inactive'
            WHERE id = %s
            """,
            (block_id,),
        )
        conn.commit()

        ip_address = str(row[0]) if row[0] is not None else None
        log_audit_event(
            "block_ip_removed",
            actor_username=current_user.id,
            actor_role=current_user.role,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={
                "ip_address": ip_address,
                "reason": row[1],
                "actor": current_user.id,
                "source_alert_id": row[2],
                "block_id": block_id,
            },
        )

        return jsonify({"message": "Blocked IP removed successfully"}), 200
    except Exception as error:
        if conn:
            conn.rollback()
        app.logger.error("Error in unblock_blocked_ip: %s", error)
        return jsonify({"error": "Unable to unblock blocked IP"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route("/alerts/<int:alert_id>/execute", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def manual_execute_alert(alert_id):
    conn = None
    cur = None

    try:
        data = request.get_json() or {}
        action = data.get("action")

        if not action:
            return jsonify({"error": "Missing action"}), 400

        if action not in VALID_RESPONSE_ACTIONS:
            return jsonify({"error": "Invalid response action"}), 400

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT source_ip
            FROM alerts
            WHERE id = %s
            """,
            (alert_id,)
        )
        row = cur.fetchone()

        if not row:
            return jsonify({"error": "Alert not found"}), 404

        source_ip = row[0]

        block_reason = f"Manual block recorded from alert {alert_id}" if action == "block_ip" else None
        execution_status = execute_response_action(
            cur,
            alert_id,
            str(source_ip),
            action,
            create_blocklist_record=action == "block_ip",
            created_by=current_user.id,
            reason=block_reason,
            source_alert_id=alert_id if action == "block_ip" else None,
        )

        cur.execute(
            """
            UPDATE alerts
            SET response_action = %s,
                response_status = %s
            WHERE id = %s
            """,
            (action, execution_status, alert_id)
        )

        conn.commit()

        log_audit_event(
            "EXECUTE_RESPONSE_ACTION",
            actor_username=current_user.id,
            actor_role=current_user.role,
            target_alert_id=alert_id,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={"action": action, "status": execution_status},
        )

        return jsonify({
            "message": "Action executed successfully",
            "alert_id": alert_id,
            "action": action,
            "response_status": execution_status
        }), 200

    except ValueError as e:
        if conn:
            conn.rollback()
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        if conn:
            conn.rollback()
        print("Error in manual_execute_alert:", e)
        return jsonify({"error": "Internal server error"}), 500

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route("/alerts/<int:alert_id>/status", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def update_alert_status(alert_id):
    try:
        data = request.get_json() or {}
        new_status = data.get("status")

        if new_status not in ["open", "resolved"]:
            return jsonify({"error": "Invalid status"}), 400

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            UPDATE alerts
            SET status = %s
            WHERE id = %s
            """,
            (new_status, alert_id),
        )

        if cur.rowcount == 0:
            conn.rollback()
            return jsonify({"error": "Alert not found"}), 404

        conn.commit()
        log_audit_event(
            "UPDATE_ALERT_STATUS",
            actor_username=current_user.id,
            actor_role=current_user.role,
            target_alert_id=alert_id,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={"status": new_status},
        )
        cur.close()
        conn.close()

        return jsonify({"message": "Alert status updated successfully"}), 200

    except Exception as e:
        app.logger.error("Error in update_alert_status: %s", e)
        return jsonify({"error": "Internal server error"}), 500


# ============================================================================
# Frontend Serving / Entrypoint
# ============================================================================


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    file_path = os.path.join(FRONTEND_BUILD_DIR, path)

    if path and os.path.exists(file_path) and os.path.isfile(file_path):
        return send_from_directory(FRONTEND_BUILD_DIR, path)

    return send_from_directory(FRONTEND_BUILD_DIR, "index.html")


if __name__ == "__main__":
    app.run(host=SIEM_BIND_HOST, port=SIEM_PORT, debug=SIEM_DEBUG)
