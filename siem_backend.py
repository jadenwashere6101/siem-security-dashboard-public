from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from psycopg2.extras import Json
from dotenv import load_dotenv
from functools import wraps
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash
import logging
import os
import ipaddress
import csv
import json
from io import BytesIO, StringIO
from datetime import datetime, timezone
import requests
import psycopg2
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas
from adapters.azure_insights_adapter import normalize_azure_insights_telemetry
from adapters.nginx_adapter import parse_nginx_access_log_line
from adapters.otel_adapter import normalize_otel_telemetry


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


DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
]

MITRE_ATTACK_MAPPINGS = {
    "failed_login_threshold": {
        "mitre_technique_id": "T1110",
        "mitre_technique_name": "Brute Force",
        "mitre_tactic": "Credential Access",
    },
    "port_scan_threshold": {
        "mitre_technique_id": "T1046",
        "mitre_technique_name": "Network Service Discovery",
        "mitre_tactic": "Discovery",
    },
    "suspicious_ip_reputation": {
        "mitre_technique_id": "T1595",
        "mitre_technique_name": "Active Scanning",
        "mitre_tactic": "Reconnaissance",
    },
    "password_spraying_threshold": {
        "mitre_technique_id": "T1110.003",
        "mitre_technique_name": "Password Spraying",
        "mitre_tactic": "Credential Access",
    },
    "successful_login_after_spray": {
        "mitre_technique_id": "T1110.003",
        "mitre_technique_name": "Password Spraying",
        "mitre_tactic": "Credential Access",
    },
}

geo_cache = {}

SIEM_ALLOWED_ORIGINS = env_csv("SIEM_ALLOWED_ORIGINS", default=DEFAULT_ALLOWED_ORIGINS)
SIEM_BIND_HOST = env_first("SIEM_BIND_HOST", default="0.0.0.0")
SIEM_PORT = int(env_first("SIEM_PORT", default="5051"))
SIEM_DEBUG = env_first("SIEM_DEBUG", default="false").strip().lower() == "true"

FAILED_LOGIN_THRESHOLD = 3
FAILED_LOGIN_WINDOW_MINUTES = 15

PORT_SCAN_THRESHOLD = 2
PORT_SCAN_WINDOW_MINUTES = 15

PASSWORD_SPRAY_THRESHOLD = 5
PASSWORD_SPRAY_WINDOW_MINUTES = 15

HTTP_ERROR_THRESHOLD = 5
HTTP_ERROR_WINDOW_MINUTES = 15

HIGH_REQUEST_RATE_THRESHOLD = 20
HIGH_REQUEST_RATE_WINDOW_MINUTES = 5
CORRELATION_WINDOW_MINUTES = 10

SUCCESS_AFTER_SPRAY_SUCCESS_WINDOW_MINUTES = 15
SUCCESS_AFTER_SPRAY_FAILED_LOOKBACK_MINUTES = 30
SUCCESS_AFTER_SPRAY_CORRELATION_WINDOW_MINUTES = 15
SUCCESS_AFTER_SPRAY_THRESHOLD = 5

DETECTION_THRESHOLD_MIN = 1
DETECTION_THRESHOLD_MAX = 100
DETECTION_WINDOW_MINUTES_MIN = 1
DETECTION_WINDOW_MINUTES_MAX = 1440


def get_detection_rule_defaults():
    return {
        "failed_login_threshold": {
            "rule_id": "failed_login_threshold",
            "display_name": "Failed Login Threshold",
            "parameters": {
                "threshold": FAILED_LOGIN_THRESHOLD,
                "window_minutes": FAILED_LOGIN_WINDOW_MINUTES,
            },
            "active": True,
            "description": "Triggers when multiple failed login attempts occur within a time window.",
        },
        "port_scan_threshold": {
            "rule_id": "port_scan_threshold",
            "display_name": "Port Scan Threshold",
            "parameters": {
                "threshold": PORT_SCAN_THRESHOLD,
                "window_minutes": PORT_SCAN_WINDOW_MINUTES,
            },
            "active": True,
            "description": "Triggers when repeated port scan events occur from the same source within a time window.",
        },
        "password_spraying_threshold": {
            "rule_id": "password_spraying_threshold",
            "display_name": "Password Spraying Threshold",
            "parameters": {
                "threshold": PASSWORD_SPRAY_THRESHOLD,
                "window_minutes": PASSWORD_SPRAY_WINDOW_MINUTES,
            },
            "active": True,
            "description": "Triggers when failed logins target multiple distinct usernames from the same source within a time window.",
        },
        "successful_login_after_spray": {
            "rule_id": "successful_login_after_spray",
            "display_name": "Successful Login After Spray",
            "parameters": {
                "threshold": SUCCESS_AFTER_SPRAY_THRESHOLD,
                "success_window_minutes": SUCCESS_AFTER_SPRAY_SUCCESS_WINDOW_MINUTES,
                "failed_lookback_minutes": SUCCESS_AFTER_SPRAY_FAILED_LOOKBACK_MINUTES,
                "correlation_window_minutes": SUCCESS_AFTER_SPRAY_CORRELATION_WINDOW_MINUTES,
            },
            "active": True,
            "description": "Triggers when password spraying activity is followed by a successful login from the same source.",
        },
    }


def parse_detection_rule_parameters(raw_parameters):
    if raw_parameters is None:
        return {}

    if isinstance(raw_parameters, str):
        try:
            raw_parameters = json.loads(raw_parameters)
        except json.JSONDecodeError as error:
            raise ValueError("Parameters must be valid JSON") from error

    if not isinstance(raw_parameters, dict):
        raise ValueError("Parameters must be an object")

    return raw_parameters


def validate_detection_rule_config(rule_id, parameters, active):
    defaults = get_detection_rule_defaults()
    rule_defaults = defaults.get(rule_id)

    if not rule_defaults:
        raise ValueError("Unknown rule_id")

    parameters = parse_detection_rule_parameters(parameters)

    if not isinstance(active, bool):
        raise ValueError("Active must be a boolean")

    allowed_parameters = set(rule_defaults["parameters"].keys())
    normalized_parameters = {}

    for key, value in parameters.items():
        if key not in allowed_parameters:
            raise ValueError(f"Unknown parameter key: {key}")

        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"Parameter {key} must be an integer")

        if key == "threshold":
            if not DETECTION_THRESHOLD_MIN <= value <= DETECTION_THRESHOLD_MAX:
                raise ValueError(f"Parameter {key} must be between {DETECTION_THRESHOLD_MIN} and {DETECTION_THRESHOLD_MAX}")
        else:
            if not DETECTION_WINDOW_MINUTES_MIN <= value <= DETECTION_WINDOW_MINUTES_MAX:
                raise ValueError(
                    f"Parameter {key} must be between {DETECTION_WINDOW_MINUTES_MIN} and {DETECTION_WINDOW_MINUTES_MAX}"
                )

        normalized_parameters[key] = value

    return {
        "parameters": normalized_parameters,
        "active": active,
    }


def get_effective_detection_rule(rule_id, cur=None):
    defaults = get_detection_rule_defaults()
    rule_defaults = defaults.get(rule_id)

    if not rule_defaults:
        raise ValueError("Unknown rule_id")

    effective_rule = {
        "rule_id": rule_defaults["rule_id"],
        "display_name": rule_defaults["display_name"],
        "parameters": dict(rule_defaults["parameters"]),
        "active": rule_defaults["active"],
        "description": rule_defaults["description"],
        "updated_by": None,
        "updated_at": None,
        "has_override": False,
        "override_status": "default",
    }

    owns_connection = cur is None
    conn = None
    uses_savepoint = cur is not None

    try:
        if owns_connection:
            conn = get_db_connection()
            cur = conn.cursor()
            uses_savepoint = False

        if uses_savepoint:
            cur.execute("SAVEPOINT detection_config_lookup")

        cur.execute(
            """
            SELECT parameters, active, updated_by, updated_at
            FROM detection_config
            WHERE rule_id = %s
            """,
            (rule_id,),
        )
        row = cur.fetchone()

        if not row:
            return effective_rule

        effective_rule["has_override"] = True
        parameters = parse_detection_rule_parameters(row[0] if row[0] is not None else {})
        active = row[1]
        effective_rule["updated_by"] = row[2]
        effective_rule["updated_at"] = str(row[3]) if row[3] is not None else None

        validated = validate_detection_rule_config(rule_id, parameters, active)
        merged_parameters = dict(effective_rule["parameters"])
        merged_parameters.update(validated["parameters"])

        effective_rule["parameters"] = merged_parameters
        effective_rule["active"] = validated["active"]
        effective_rule["override_status"] = "applied"
        return effective_rule
    except ValueError as error:
        app.logger.warning("Invalid detection_config override for rule_id=%s: %s", rule_id, error)
        effective_rule["override_status"] = "invalid"
        return effective_rule
    except Exception as error:
        if uses_savepoint:
            try:
                cur.execute("ROLLBACK TO SAVEPOINT detection_config_lookup")
            except Exception:
                pass
        app.logger.warning("Falling back to detection defaults for rule_id=%s: %s", rule_id, error)
        effective_rule["override_status"] = "unavailable"
        return effective_rule
    finally:
        if uses_savepoint:
            try:
                cur.execute("RELEASE SAVEPOINT detection_config_lookup")
            except Exception:
                pass
        if owns_connection:
            if cur:
                cur.close()
            if conn:
                conn.close()


def get_all_effective_detection_rules():
    defaults = get_detection_rule_defaults()
    conn = None
    cur = None

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        return [get_effective_detection_rule(rule_id, cur=cur) for rule_id in defaults.keys()]
    except Exception as error:
        app.logger.warning("Falling back to detection defaults for admin detection rules list: %s", error)
        return [
            {
                **rule_defaults,
                "parameters": dict(rule_defaults["parameters"]),
                "has_override": False,
                "override_status": "unavailable",
            }
            for rule_defaults in defaults.values()
        ]
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def get_db_connection():
    return psycopg2.connect(
        dbname=env_first("SIEM_DB_NAME", "DB_NAME"),
        user=env_first("SIEM_DB_USER", "DB_USER"),
        host=env_first("SIEM_DB_HOST", "DB_HOST"),
        password=env_first("SIEM_DB_PASSWORD", "DB_PASSWORD")
    )


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


def validate_blocked_ip(ip_address):
    if ip_address is None or not str(ip_address).strip():
        raise ValueError("IP address is required")

    try:
        parsed_ip = ipaddress.ip_address(str(ip_address).strip())
    except ValueError as error:
        raise ValueError("Invalid IP address") from error

    if (
        parsed_ip.is_loopback
        or parsed_ip.is_private
        or parsed_ip.is_link_local
        or parsed_ip.is_multicast
        or parsed_ip.is_reserved
        or parsed_ip.is_unspecified
    ):
        raise ValueError("Private, loopback, and internal IPs cannot be blocked")

    return str(parsed_ip)


def create_blocked_ip_record(cur, ip_address, created_by=None, reason=None, source_alert_id=None, expires_at=None):
    normalized_ip = validate_blocked_ip(ip_address)

    if source_alert_id is not None:
        cur.execute(
            """
            SELECT 1
            FROM alerts
            WHERE id = %s
            """,
            (source_alert_id,),
        )
        if not cur.fetchone():
            raise ValueError("Source alert not found")

    cur.execute(
        """
        SELECT 1
        FROM blocked_ips
        WHERE ip_address = %s
          AND status = 'active'
        """,
        (normalized_ip,),
    )
    if cur.fetchone():
        raise ValueError("An active block already exists for this IP")

    cur.execute(
        """
        INSERT INTO blocked_ips (
            ip_address,
            reason,
            status,
            created_by,
            expires_at,
            source_alert_id
        )
        VALUES (%s, %s, 'active', %s, %s, %s)
        RETURNING id
        """,
        (
            normalized_ip,
            reason,
            created_by,
            expires_at,
            source_alert_id,
        ),
    )
    return cur.fetchone()[0]


def _get_reputation_label(score):
    if score <= 0:
        return "Normal"
    if score <= 4:
        return "Low Suspicion"
    if score <= 9:
        return "Suspicious"
    if score <= 14:
        return "High Risk"
    return "Critical"


def _build_reputation_summary(signals):
    if not signals:
        return "No elevated behavioral signals observed in SIEM history."

    phrases = [signal["summary_phrase"] for signal in signals[:2] if signal.get("summary_phrase")]
    if not phrases:
        return "Behavioral signals observed in SIEM history."
    if len(phrases) == 1:
        return phrases[0]
    return f"{phrases[0]} and {phrases[1]}"


def get_ip_reputation(source_ip, cur=None):
    if source_ip is None:
        return {
            "reputation_score": 0,
            "reputation_label": "Normal",
            "reputation_summary": "No elevated behavioral signals observed in SIEM history.",
            "contributing_signals": [],
        }

    owns_connection = cur is None
    conn = None

    try:
        if owns_connection:
            conn = get_db_connection()
            cur = conn.cursor()

        cur.execute(
            """
            SELECT alert_type, COUNT(*)
            FROM alerts
            WHERE source_ip = %s
              AND alert_type IN (
                  'failed_login_threshold',
                  'password_spraying_threshold',
                  'successful_login_after_spray',
                  'port_scan_threshold',
                  'http_error_threshold',
                  'high_request_rate_threshold'
              )
            GROUP BY alert_type
            """,
            (source_ip,),
        )
        alert_counts = {row[0]: row[1] for row in cur.fetchall()}

        cur.execute(
            """
            SELECT COUNT(*)
            FROM blocked_ips
            WHERE ip_address = %s
              AND status = 'active'
            """,
            (source_ip,),
        )
        active_block_count = cur.fetchone()[0]

        signal_config = {
            "failed_login_threshold": {
                "weight": 3,
                "label": "Failed Login Threshold",
                "summary_phrase": "Multiple failed login attempts",
            },
            "password_spraying_threshold": {
                "weight": 5,
                "label": "Password Spraying",
                "summary_phrase": "Password spraying activity",
            },
            "successful_login_after_spray": {
                "weight": 6,
                "label": "Successful Login After Spray",
                "summary_phrase": "Successful login after spraying",
            },
            "port_scan_threshold": {
                "weight": 4,
                "label": "Port Scan Threshold",
                "summary_phrase": "Port scan activity",
            },
            "http_error_threshold": {
                "weight": 2,
                "label": "HTTP Error Threshold",
                "summary_phrase": "Repeated HTTP errors",
            },
            "high_request_rate_threshold": {
                "weight": 3,
                "label": "High Request Rate Threshold",
                "summary_phrase": "High request rate",
            },
        }

        contributing_signals = []
        reputation_score = 0

        for signal_key, config in signal_config.items():
            count = int(alert_counts.get(signal_key, 0) or 0)
            if count <= 0:
                continue

            total_weight = count * config["weight"]
            reputation_score += total_weight
            contributing_signals.append(
                {
                    "signal": signal_key,
                    "label": config["label"],
                    "count": count,
                    "weight": config["weight"],
                    "total": total_weight,
                    "summary_phrase": config["summary_phrase"],
                }
            )

        if active_block_count > 0:
            total_weight = active_block_count * 6
            reputation_score += total_weight
            contributing_signals.append(
                {
                    "signal": "blocked_ips",
                    "label": "Active Blocklist Entry",
                    "count": active_block_count,
                    "weight": 6,
                    "total": total_weight,
                    "summary_phrase": "Prior blocklist entry",
                }
            )

        contributing_signals.sort(key=lambda item: (-item["total"], item["label"]))

        return {
            "reputation_score": reputation_score,
            "reputation_label": _get_reputation_label(reputation_score),
            "reputation_summary": _build_reputation_summary(contributing_signals),
            "contributing_signals": [
                {key: value for key, value in signal.items() if key != "summary_phrase"}
                for signal in contributing_signals
            ],
        }
    finally:
        if owns_connection:
            if cur:
                cur.close()
            if conn:
                conn.close()


def get_user_by_username(username):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT username, password_hash, role, is_active
            FROM users
            WHERE username = %s
            """,
            (username,),
        )
        row = cur.fetchone()

        if not row:
            return None

        return {
            "username": row[0],
            "password_hash": row[1],
            "role": row[2],
            "is_active": row[3],
        }
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def log_audit_event(
    event_type,
    actor_username=None,
    actor_role=None,
    target_username=None,
    target_alert_id=None,
    http_method=None,
    request_path=None,
    source_ip=None,
    details=None
):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO audit_log (
                event_type,
                actor_username,
                actor_role,
                target_username,
                target_alert_id,
                http_method,
                request_path,
                source_ip,
                details
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                event_type,
                actor_username,
                actor_role,
                target_username,
                target_alert_id,
                http_method,
                request_path,
                source_ip,
                Json(details) if details is not None else None,
            ),
        )
        conn.commit()
    except Exception as e:
        app.logger.error("Failed to write audit log event=%s error=%s", event_type, e)
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

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


def deny_rbac_access(reason, message, target_alert_id=None):
    app.logger.warning(
        "RBAC deny username=%s role=%s method=%s path=%s remote_addr=%s",
        getattr(current_user, "id", None),
        getattr(current_user, "role", None),
        request.method,
        request.path,
        request.remote_addr,
    )
    log_audit_event(
        "rbac_deny",
        actor_username=getattr(current_user, "id", None),
        actor_role=getattr(current_user, "role", None),
        target_alert_id=target_alert_id,
        http_method=request.method,
        request_path=request.path,
        source_ip=request.remote_addr,
        details={"reason": reason},
    )
    return jsonify({
        "error": "forbidden",
        "message": message
    }), 403


def admin_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if getattr(current_user, "role", None) not in {"admin", "super_admin"}:
            return deny_rbac_access(
                "admin_required",
                "Admin role required",
                target_alert_id=kwargs.get("alert_id"),
            )

        return view_func(*args, **kwargs)

    return wrapped_view


def super_admin_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if getattr(current_user, "role", None) != "super_admin":
            return deny_rbac_access(
                "admin_required",
                "Super admin role required",
                target_alert_id=kwargs.get("alert_id"),
            )

        return view_func(*args, **kwargs)

    return wrapped_view


def analyst_or_super_admin_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if getattr(current_user, "role", None) not in {"super_admin", "analyst"}:
            return deny_rbac_access(
                "analyst_required",
                "Analyst or super admin role required",
                target_alert_id=kwargs.get("alert_id"),
            )

        return view_func(*args, **kwargs)

    return wrapped_view


class User(UserMixin):
    def __init__(self, user_id, role="admin"):
        self.id = user_id
        self.role = role


@login_manager.user_loader
def load_user(user_id):
    if user_id == "admin":
        return User(user_id, role="super_admin")

    db_user = get_user_by_username(user_id)
    if db_user and db_user["is_active"]:
        return User(db_user["username"], role=db_user["role"])

    return None


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


API_KEY_HEADER = "X-API-Key"
INGEST_API_KEY = env_first("SIEM_INGEST_API_KEY", "INGEST_API_KEY", default="")
AZURE_INGEST_API_KEY = env_first("AZURE_INGEST_API_KEY", default="")
OTEL_INGEST_API_KEY = env_first("OTEL_INGEST_API_KEY", default="")
ABUSEIPDB_API_KEY = env_first("SIEM_ABUSEIPDB_API_KEY", "ABUSEIPDB_API_KEY")
REPUTATION_CACHE = {}

def require_api_key():
    if not INGEST_API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    api_key = request.headers.get(API_KEY_HEADER, "")
    if api_key != INGEST_API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    return None


def require_azure_api_key():
    if not AZURE_INGEST_API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    api_key = request.headers.get(API_KEY_HEADER, "")
    if api_key != AZURE_INGEST_API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    return None


def require_otel_api_key():
    if not OTEL_INGEST_API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    api_key = request.headers.get(API_KEY_HEADER, "")
    if api_key != OTEL_INGEST_API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    return None

def lookup_ip_location(ip_address):
    try:
        if ip_address in geo_cache:
            return geo_cache[ip_address]

        response = requests.get(f"http://ip-api.com/json/{ip_address}", timeout=2)
        data = response.json()

        if data.get("status") != "success":
            return {
                "country": None,
                "city": None,
                "lat": None,
                "lon": None,
            }

        location = {
            "country": data.get("country"),
            "city": data.get("city"),
            "lat": data.get("lat"),
            "lon": data.get("lon"),
        }
        geo_cache[ip_address] = location
        if len(geo_cache) > 5000:
            geo_cache.clear()
        return location

    except Exception as e:
        app.logger.error("Error looking up IP location for %s: %s", ip_address, e)
        return {
            "country": None,
            "city": None,
            "lat": None,
            "lon": None,
        }


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


def has_valid_location(location):
    if not isinstance(location, dict):
        return False

    lat = location.get("lat")
    lon = location.get("lon")
    return lat not in (None, "") and lon not in (None, "")


def ingest_normalized_event(event_dict, conn, cur):
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
        for item in telemetry_items:
            try:
                normalized = normalize_azure_insights_telemetry(item)
            except ValueError as error:
                return jsonify({"error": str(error)}), 400

            normalized_events.append(
                {
                    "event_type": normalized["event_type"],
                    "severity": normalized["severity"],
                    "source_ip": normalized["source_ip"],
                    "source": "azure_insights",
                    "source_type": "cloud_api",
                    "event_timestamp": normalized.get("event_timestamp"),
                    "message": normalized["message"],
                    "app_name": "azure_application_insights",
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
                    "app_name": "opentelemetry",
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


def lookup_ip_reputation(ip_address):
    ip_address = str(ip_address)

    if ip_address in REPUTATION_CACHE:
        return REPUTATION_CACHE[ip_address]

    # If no API key -> fallback to mock
    if not ABUSEIPDB_API_KEY:
        app.logger.warning("ABUSEIPDB_API_KEY is missing; using mock reputation fallback for ip=%s", ip_address)
        result = {
            "reputation_score": 50,
            "reputation_label": "unknown",
            "reputation_source": "mock",
            "reputation_summary": "No API key configured"
        }

        REPUTATION_CACHE[ip_address] = result
        if len(REPUTATION_CACHE) > 5000:
            REPUTATION_CACHE.clear()
        return result

    try:
        url = "https://api.abuseipdb.com/api/v2/check"

        headers = {
            "Key": ABUSEIPDB_API_KEY,
            "Accept": "application/json"
        }

        params = {
            "ipAddress": ip_address,
            "maxAgeInDays": 90
        }

        response = requests.get(url, headers=headers, params=params, timeout=10)

        # Safety check
        if response.status_code != 200:
            app.logger.error(
                "AbuseIPDB API returned non-200 for ip=%s status=%s body=%s",
                ip_address,
                response.status_code,
                response.text[:300],
            )
            raise Exception("API request failed")

        data = response.json()["data"]

        score = data.get("abuseConfidenceScore", 0)

        # Map score -> label
        if score >= 70:
            label = "high-risk"
        elif score >= 30:
            label = "medium-risk"
        else:
            label = "low-risk"

        summary = f"{data.get('totalReports', 0)} reports. ISP: {data.get('isp', 'unknown')}"

        result = {
            "reputation_score": score,
            "reputation_label": label,
            "reputation_source": "abuseipdb",
            "reputation_summary": summary
        }

        REPUTATION_CACHE[ip_address] = result
        if len(REPUTATION_CACHE) > 5000:
            REPUTATION_CACHE.clear()
        return result

    except Exception as e:
        app.logger.error("AbuseIPDB lookup failed for ip=%s: %s", ip_address, e)
        # fallback if API fails
        result = {
            "reputation_score": 50,
            "reputation_label": "unknown",
            "reputation_source": "fallback",
            "reputation_summary": "API lookup failed"
        }

        REPUTATION_CACHE[ip_address] = result
        if len(REPUTATION_CACHE) > 5000:
            REPUTATION_CACHE.clear()
        return result


def determine_response_action(reputation_score):
    if reputation_score >= 80:
        return "block_ip"
    elif reputation_score >= 60:
        return "flag_high_priority"
    else:
        return "monitor"


def execute_response_action(
    cur,
    alert_id,
    source_ip,
    response_action,
    *,
    create_blocklist_record=False,
    created_by=None,
    reason=None,
    source_alert_id=None,
):
    status = "executed"
    details = None

    if response_action == "block_ip":
        if create_blocklist_record:
            create_blocked_ip_record(
                cur,
                source_ip,
                created_by=created_by,
                reason=reason,
                source_alert_id=source_alert_id,
            )
            app.logger.info("[BLOCKLIST TRACKING] alert_id=%s ip=%s", alert_id, source_ip)
            details = "Recorded in SIEM blocklist (tracking only)"
        else:
            app.logger.info("[SIMULATED BLOCK] alert_id=%s ip=%s", alert_id, source_ip)
            details = "Simulated IP block"

    elif response_action == "flag_high_priority":
        app.logger.info("[SIMULATED ESCALATION] alert_id=%s ip=%s", alert_id, source_ip)
        details = "Simulated escalation to SOC"

    else:
        app.logger.info("[SIMULATED MONITOR] alert_id=%s ip=%s", alert_id, source_ip)
        details = "Monitoring only"

    cur.execute(
        """
        INSERT INTO response_actions_log (alert_id, source_ip, action, status, details)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (alert_id, source_ip, response_action, status, details)
    )

    return status


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


def generate_correlated_activity_alerts(cur, conn, source_ip):
    qualifying_alert_types = (
        "failed_login_threshold",
        "password_spraying_threshold",
        "successful_login_after_spray",
        "port_scan_threshold",
        "http_error_threshold",
        "high_request_rate_threshold",
    )

    cur.execute(
        """
        SELECT 1
        FROM alerts
        WHERE source_ip = %s
          AND alert_type = %s
          AND status = 'open'
        """,
        (source_ip, "correlated_activity"),
    )

    if cur.fetchone():
        return False

    cur.execute(
        f"""
        SELECT
            id,
            alert_type,
            source,
            source_type,
            country,
            city,
            latitude,
            longitude,
            created_at
        FROM alerts
        WHERE source_ip = %s
          AND status = 'open'
          AND alert_type IN %s
          AND created_at >= NOW() - INTERVAL '{CORRELATION_WINDOW_MINUTES} minutes'
        ORDER BY created_at DESC
        """,
        (source_ip, qualifying_alert_types),
    )

    rows = cur.fetchall()
    if len(rows) < 2:
        return False

    alert_types = []
    known_sources = []
    for row in rows:
        alert_type = row[1]
        if alert_type not in alert_types:
            alert_types.append(alert_type)
        source = row[2]
        if source is not None:
            normalized_source = str(source).strip().lower()
            if normalized_source and normalized_source != "unknown" and normalized_source not in known_sources:
                known_sources.append(normalized_source)

    if len(alert_types) < 2:
        return False

    if len(known_sources) < 2:
        return False

    newest_alert = rows[0]
    source = newest_alert[2] or "unknown"
    source_type = newest_alert[3] or "legacy"
    country = newest_alert[4]
    city = newest_alert[5]
    latitude = newest_alert[6]
    longitude = newest_alert[7]

    reputation = lookup_ip_reputation(str(source_ip))
    reputation_score = reputation["reputation_score"]
    response_action = determine_response_action(reputation_score)
    response_status = "pending"
    reputation_label = reputation["reputation_label"]
    reputation_source = reputation["reputation_source"]
    reputation_summary = reputation["reputation_summary"]

    alert_types_text = ", ".join(alert_types)
    message = f"Multi-source suspicious activity detected from {source_ip} involving: {alert_types_text}"

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
            "correlated_activity",
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

    app.logger.info(
        "Correlated activity detected source_ip=%s linked_alert_count=%d alert_types=%s",
        source_ip,
        len(rows),
        alert_types_text,
    )

    return True


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


def format_report_timestamp(value):
    if value is None:
        return "Unknown"
    return str(value)


def format_pdf_timestamp(value):
    if value is None:
        return "Unknown"

    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return str(value)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return dt.strftime("%B %d, %Y · %H:%M UTC")


def format_csv_timestamp(value):
    if value is None:
        return ""

    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return str(value)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return dt.strftime("%Y-%m-%d %H:%M UTC")


def format_display_value(value):
    if value in (None, ""):
        return "Unknown"

    text = str(value).strip()
    if not text:
        return "Unknown"

    explicit_map = {
        "flag_high_priority": "Flag High Priority",
        "block_ip": "Block IP",
        "monitor": "Monitor",
        "executed": "Executed",
        "pending": "Pending",
        "failed": "Failed",
        "open": "Open",
        "resolved": "Resolved",
        "not set": "Not Set",
    }

    lowered = text.lower()
    if lowered in explicit_map:
        return explicit_map[lowered]

    return text.replace("_", " ").title()


def enrich_alert_with_mitre(alert_dict):
    alert_type = alert_dict.get("alert_type")
    mitre_data = MITRE_ATTACK_MAPPINGS.get(alert_type, {})

    alert_dict["mitre_technique_id"] = mitre_data.get("mitre_technique_id")
    alert_dict["mitre_technique_name"] = mitre_data.get("mitre_technique_name")
    alert_dict["mitre_tactic"] = mitre_data.get("mitre_tactic")

    return alert_dict


def build_alert_summary(alert_type):
    summary_map = {
        "failed_login_threshold": "Multiple failed login attempts were grouped into a threshold alert, indicating likely credential abuse or password guessing activity.",
        "port_scan_threshold": "Repeated port scan activity was observed from the same source, suggesting reconnaissance against exposed services.",
        "failed_login": "A failed authentication event was detected and surfaced for analyst review.",
        "login_failure": "A login failure event was detected and surfaced for analyst review.",
        "port_scan": "A port scanning event was detected and surfaced for analyst review.",
        "normal_activity": "This alert reflects activity recorded by the platform that may require analyst validation based on surrounding context.",
    }
    return summary_map.get(
        alert_type,
        f"This incident report covers a {alert_type} alert generated by the SIEM and summarizes the available evidence for analyst review.",
    )


def build_severity_explanation(severity):
    severity_explanations = {
        "low": "Low severity indicates limited immediate risk. The event should be documented and monitored for changes or recurrence.",
        "medium": "Medium severity indicates suspicious activity that warrants analyst review and possible containment if supporting evidence increases.",
        "high": "High severity indicates elevated risk and likely malicious behavior requiring prompt investigation and response.",
        "critical": "Critical severity indicates urgent risk with likely active compromise or major impact, requiring immediate containment and escalation.",
    }
    return severity_explanations.get(
        severity,
        "Severity was not recognized. Review the alert context and supporting telemetry directly."
    )


def build_confidence_level(severity):
    if severity == "low":
        return "Low"
    if severity == "medium":
        return "Medium"
    if severity in {"high", "critical"}:
        return "High"
    return "Unknown"


def build_next_steps(alert_type):
    next_steps_map = {
        "failed_login_threshold": [
            "Validate whether the targeted account experienced additional authentication failures or a lockout condition.",
            "Correlate the source IP with firewall, reverse proxy, or identity provider logs for repeated access attempts.",
            "Consider blocking or rate-limiting the source if the activity is confirmed malicious.",
        ],
        "port_scan_threshold": [
            "Review exposed services and confirm whether the probed ports were expected to be reachable.",
            "Correlate the source IP with network telemetry to determine scan breadth and duration.",
            "Consider blocking the source and validating there was no follow-on exploitation activity.",
        ],
    }
    return next_steps_map.get(
        alert_type,
        [
            "Review surrounding SIEM events for related indicators from the same source.",
            "Confirm whether the observed activity matches expected behavior for the environment.",
            "Document analyst findings and escalate if additional malicious evidence is found.",
        ],
    )


def normalize_alert_report_data(alert_row):
    location = "Location unavailable"
    if alert_row[8] and alert_row[7]:
        location = f"{alert_row[8]}, {alert_row[7]}"

    severity = (alert_row[2] or "unknown").lower()
    alert_type = alert_row[1] or "unknown_alert"

    return enrich_alert_with_mitre({
        "id": alert_row[0],
        "alert_type": alert_type,
        "severity": severity,
        "source_ip": str(alert_row[3]) if alert_row[3] is not None else "Unknown",
        "timestamp": format_report_timestamp(alert_row[4]),
        "message": alert_row[5] or "No message provided",
        "status": alert_row[6] or "unknown",
        "location": location,
        "reputation_label": alert_row[9] or "No reputation label",
        "reputation_summary": alert_row[10] or "No reputation summary",
        "response_action": alert_row[11] or "Not set",
        "response_status": alert_row[12] or "Not set",
        "summary": build_alert_summary(alert_type),
        "severity_explanation": build_severity_explanation(severity),
        "confidence_level": build_confidence_level(severity),
        "recommended_steps": build_next_steps(alert_type),
    })


def build_alert_report_sections(alert_data, response_logs, include_identifier=True):
    lines = [
        "SUMMARY",
        "=======",
        alert_data["summary"],
        "",
        "SEVERITY ANALYSIS",
        "=================",
        f"Severity Level: {alert_data['severity']}",
        f"Confidence Level: {alert_data['confidence_level']}",
        alert_data["severity_explanation"],
        "",
        "ALERT DETAILS",
        "=============",
    ]

    if include_identifier:
        lines.append(f"Alert ID: {alert_data['id']}")

    lines.extend([
        f"Alert Type: {alert_data['alert_type']}",
        f"Source IP: {alert_data['source_ip']}",
        f"Timestamp: {alert_data['timestamp']}",
        f"Status: {alert_data['status']}",
        f"Message: {alert_data['message']}",
        "",
        "SOURCE INTELLIGENCE",
        "===================",
        f"Location: {alert_data['location']}",
        f"Reputation Label: {alert_data['reputation_label']}",
        f"Reputation Summary: {alert_data['reputation_summary']}",
        "",
        "TIMELINE",
        "========",
        f"- Alert created: {alert_data['timestamp']}",
    ])

    if response_logs:
        for log in response_logs:
            executed_at = format_report_timestamp(log[3])
            action = log[0] or "unknown"
            log_status = log[1] or "unknown"
            details = log[2] or "n/a"
            lines.append(
                f"- Response log: {executed_at} | action={action} | status={log_status} | details={details}"
            )
    else:
        lines.append("- No response actions recorded")

    lines.extend([
        "",
        "RESPONSE ACTION",
        "===============",
        f"Recommended Response Action: {alert_data['response_action']}",
        f"Current Response Status: {alert_data['response_status']}",
        "",
        "RECOMMENDED NEXT STEPS",
        "======================",
    ])

    for step in alert_data["recommended_steps"]:
        lines.append(f"- {step}")

    return lines


def fetch_alert_rows(cur, filters=None):
    filters = filters or {}
    clauses = []
    params = []

    severity = (filters.get("severity") or "").strip().lower()
    if severity and severity != "all":
        clauses.append("severity = %s")
        params.append(severity)

    status = (filters.get("status") or "").strip().lower()
    if status and status != "all":
        clauses.append("status = %s")
        params.append(status)

    search = (filters.get("search") or "").strip()
    if search:
        clauses.append("(source_ip::text ILIKE %s OR message ILIKE %s OR alert_type ILIKE %s)")
        like_value = f"%{search}%"
        params.extend([like_value, like_value, like_value])

    query = """
        SELECT
            id,
            alert_type,
            severity,
            source_ip,
            created_at,
            message,
            status,
            country,
            city,
            reputation_label,
            reputation_summary,
            response_action,
            response_status
        FROM alerts
    """

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += " ORDER BY created_at DESC"
    cur.execute(query, tuple(params))
    return cur.fetchall()


def fetch_response_logs_by_alert_id(cur, alert_ids):
    if not alert_ids:
        return {}

    cur.execute(
        """
        SELECT alert_id, action, status, details, executed_at
        FROM response_actions_log
        WHERE alert_id = ANY(%s)
        ORDER BY executed_at DESC
        """,
        (alert_ids,)
    )

    log_map = {alert_id: [] for alert_id in alert_ids}
    for row in cur.fetchall():
        log_map.setdefault(row[0], []).append(row[1:])
    return log_map


def fetch_alert_csv_rows(cur, filters=None):
    filters = filters or {}
    clauses = []
    params = []

    severity = (filters.get("severity") or "").strip().lower()
    if severity and severity != "all":
        clauses.append("a.severity = %s")
        params.append(severity)

    status = (filters.get("status") or "").strip().lower()
    if status and status != "all":
        clauses.append("a.status = %s")
        params.append(status)

    search = (filters.get("search") or "").strip()
    if search:
        clauses.append("(a.source_ip::text ILIKE %s OR a.message ILIKE %s OR a.alert_type ILIKE %s)")
        like_value = f"%{search}%"
        params.extend([like_value, like_value, like_value])

    query = """
        SELECT
            a.id,
            a.alert_type,
            a.severity,
            a.source_ip,
            a.status,
            a.created_at,
            a.message,
            latest_event.environment
        FROM alerts a
        LEFT JOIN LATERAL (
            SELECT e.environment
            FROM events e
            WHERE e.source_ip = a.source_ip
            ORDER BY e.created_at DESC
            LIMIT 1
        ) AS latest_event ON TRUE
    """

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += " ORDER BY a.created_at DESC"
    cur.execute(query, tuple(params))
    return cur.fetchall()


def build_report_header(generated_at, scope):
    return [
        "SIEM INCIDENT REPORT",
        "====================",
        f"Generated At: {generated_at}",
        f"Report Scope: {scope}",
        "",
    ]


def get_pdf_severity_palette(severity):
    severity = (severity or "").lower()

    if severity == "critical":
        return {
            "background": HexColor("#7f1d1d"),
            "text": HexColor("#ffffff"),
            "border": HexColor("#b91c1c"),
        }

    if severity == "high":
        return {
            "background": HexColor("#991b1b"),
            "text": HexColor("#ffffff"),
            "border": HexColor("#dc2626"),
        }

    if severity == "medium":
        return {
            "background": HexColor("#fef3c7"),
            "text": HexColor("#92400e"),
            "border": HexColor("#f59e0b"),
        }

    return {
        "background": HexColor("#ecfccb"),
        "text": HexColor("#166534"),
        "border": HexColor("#65a30d"),
    }


def start_pdf_page(pdf, generated_at, scope):
    page_width, page_height = letter
    left_margin = 48
    top_y = page_height - 48

    pdf.setFillColor(colors.white)
    pdf.rect(0, 0, page_width, page_height, fill=1, stroke=0)

    pdf.setFillColor(HexColor("#0f172a"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(left_margin, top_y, "SIEM")

    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawString(left_margin, top_y - 24, "INCIDENT REPORT")

    pdf.setFillColor(HexColor("#475569"))
    pdf.setFont("Helvetica", 10)
    pdf.drawString(left_margin, top_y - 42, format_pdf_timestamp(generated_at))

    pdf.setStrokeColor(HexColor("#cbd5e1"))
    pdf.setLineWidth(1)
    pdf.line(left_margin, top_y - 54, page_width - left_margin, top_y - 54)

    pdf.setFillColor(HexColor("#334155"))
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(left_margin, top_y - 72, "REPORT SCOPE")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(left_margin, top_y - 88, scope)

    return top_y - 112


def ensure_pdf_space(pdf, current_y, needed_height, generated_at, scope):
    if current_y - needed_height >= 50:
        return current_y

    pdf.showPage()
    return start_pdf_page(pdf, generated_at, scope)


def draw_pdf_wrapped_text(pdf, text, x, y, width, font_name="Helvetica", font_size=10, color=HexColor("#0f172a"), line_gap=4):
    lines = simpleSplit(text or "", font_name, font_size, width) or [""]
    pdf.setFont(font_name, font_size)
    pdf.setFillColor(color)

    current_y = y
    for line in lines:
        pdf.drawString(x, current_y, line)
        current_y -= font_size + line_gap

    return current_y


def draw_pdf_section_heading(pdf, heading, y):
    pdf.setFillColor(HexColor("#0f172a"))
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(48, y, heading)
    pdf.setStrokeColor(HexColor("#e2e8f0"))
    pdf.setLineWidth(1)
    pdf.line(48, y - 6, 564, y - 6)
    return y - 22


def draw_pdf_key_value_rows(pdf, rows, y, generated_at, scope):
    left_x = 48
    value_x = 196
    current_y = y

    for label, value in rows:
        current_y = ensure_pdf_space(pdf, current_y, 22, generated_at, scope)
        pdf.setFillColor(HexColor("#475569"))
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(left_x, current_y, label.upper())
        current_y = draw_pdf_wrapped_text(
            pdf,
            str(value),
            value_x,
            current_y,
            352,
            font_name="Helvetica",
            font_size=10,
            color=HexColor("#0f172a"),
            line_gap=3,
        )
        current_y -= 4

    return current_y


def draw_pdf_severity_badge(pdf, severity, x, y):
    palette = get_pdf_severity_palette(severity)
    label = (severity or "unknown").upper()
    width = max(60, len(label) * 7 + 18)
    height = 18

    pdf.setFillColor(palette["background"])
    pdf.setStrokeColor(palette["border"])
    pdf.roundRect(x, y - height + 4, width, height, 8, fill=1, stroke=1)
    pdf.setFillColor(palette["text"])
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(x + 9, y - 8, label)


def draw_pdf_response_logs(pdf, response_logs, y, generated_at, scope):
    current_y = draw_pdf_section_heading(pdf, "Response Log", y)

    if not response_logs:
        return draw_pdf_wrapped_text(
            pdf,
            "No response actions recorded.",
            48,
            current_y,
            516,
            color=HexColor("#475569"),
        ) - 8

    for log in response_logs:
        current_y = ensure_pdf_space(pdf, current_y, 56, generated_at, scope)
        action = (log[0] or "unknown").replace("_", " ").title()
        action = format_display_value(log[0] or "unknown")
        log_status = format_display_value(log[1] or "unknown")
        details = log[2] or "n/a"
        executed_at = format_pdf_timestamp(log[3])

        pdf.setStrokeColor(HexColor("#e2e8f0"))
        pdf.setFillColor(HexColor("#f8fafc"))
        pdf.roundRect(48, current_y - 42, 516, 38, 8, fill=1, stroke=1)

        pdf.setFillColor(HexColor("#0f172a"))
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(58, current_y - 14, action)
        pdf.setFont("Helvetica", 9)
        pdf.setFillColor(HexColor("#475569"))
        pdf.drawString(58, current_y - 28, f"{executed_at} · {log_status}")

        details_lines = simpleSplit(f"Details: {details}", "Helvetica", 9, 320)
        detail_y = current_y - 14
        for line in details_lines[:2]:
            pdf.drawString(240, detail_y, line)
            detail_y -= 12

        current_y -= 52

    return current_y


def draw_pdf_mitre_section(pdf, alert_data, y, generated_at, scope):
    technique_id = alert_data.get("mitre_technique_id")
    technique_name = alert_data.get("mitre_technique_name")
    tactic = alert_data.get("mitre_tactic")

    if not technique_id and not technique_name and not tactic:
        return y

    current_y = draw_pdf_section_heading(pdf, "MITRE ATT&CK", y)

    current_y = draw_pdf_key_value_rows(
        pdf,
        [
            ("Technique ID", technique_id or "N/A"),
            ("Technique Name", technique_name or "Unknown Technique"),
            ("Tactic", tactic or "N/A"),
        ],
        current_y,
        generated_at,
        scope,
    )

    return current_y - 14


def draw_pdf_next_steps(pdf, steps, y, generated_at, scope):
    current_y = draw_pdf_section_heading(pdf, "Recommended Next Steps", y)

    for step in steps:
        wrapped_lines = simpleSplit(f"• {step}", "Helvetica", 10, 500)
        current_y = ensure_pdf_space(pdf, current_y, max(22, len(wrapped_lines) * 16), generated_at, scope)
        for line in wrapped_lines:
            pdf.setFont("Helvetica", 10)
            pdf.setFillColor(HexColor("#0f172a"))
            pdf.drawString(56, current_y, line)
            current_y -= 14
        current_y -= 4

    return current_y


def draw_pdf_summary_grid(pdf, severity_counts, total_alerts, y):
    metrics = [
        ("Total", total_alerts),
        ("Critical", severity_counts["critical"]),
        ("High", severity_counts["high"]),
        ("Medium", severity_counts["medium"]),
        ("Low", severity_counts["low"]),
    ]
    box_width = 96
    box_height = 52
    gap = 8
    start_x = 48

    pdf.setFont("Helvetica-Bold", 12)
    pdf.setFillColor(HexColor("#0f172a"))
    pdf.drawString(start_x, y, "Summary")

    current_x = start_x
    box_y = y - 18
    for label, value in metrics:
        pdf.setFillColor(HexColor("#f8fafc"))
        pdf.setStrokeColor(HexColor("#dbe4ee"))
        pdf.roundRect(current_x, box_y - box_height, box_width, box_height, 8, fill=1, stroke=1)
        pdf.setFillColor(HexColor("#64748b"))
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(current_x + 10, box_y - 16, label.upper())
        pdf.setFillColor(HexColor("#0f172a"))
        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(current_x + 10, box_y - 36, str(value))
        current_x += box_width + gap

    return box_y - box_height - 18


def draw_pdf_alert_card(pdf, alert_title, alert_data, response_logs, y, generated_at, scope):
    current_y = ensure_pdf_space(pdf, y, 220, generated_at, scope)

    pdf.setFillColor(HexColor("#ffffff"))
    pdf.setStrokeColor(HexColor("#dbe4ee"))
    pdf.roundRect(42, current_y - 164, 528, 156, 12, fill=1, stroke=1)

    pdf.setFillColor(HexColor("#0f172a"))
    pdf.setFont("Helvetica-Bold", 15)
    title_lines = simpleSplit(alert_title, "Helvetica-Bold", 15, 360)
    title_y = current_y - 24
    for line in title_lines[:2]:
        pdf.drawString(56, title_y, line)
        title_y -= 18

    draw_pdf_severity_badge(pdf, alert_data["severity"], 450, current_y - 14)

    field_y = current_y - 62
    current_y = draw_pdf_key_value_rows(
        pdf,
        [
            ("Source IP", alert_data["source_ip"]),
            ("Status", format_display_value(alert_data["status"])),
            ("Created", format_pdf_timestamp(alert_data["timestamp"])),
            ("Message", alert_data["message"]),
        ],
        field_y,
        generated_at,
        scope,
    )

    current_y -= 4
    current_y = draw_pdf_mitre_section(pdf, alert_data, current_y, generated_at, scope)
    current_y -= 4
    current_y = draw_pdf_section_heading(pdf, "Response Summary", current_y)
    current_y = draw_pdf_key_value_rows(
        pdf,
        [
            ("Recommended Action", format_display_value(alert_data["response_action"])),
            ("Current Response Status", format_display_value(alert_data["response_status"])),
            ("Location", alert_data["location"]),
        ],
        current_y,
        generated_at,
        scope,
    )
    current_y -= 6
    current_y = draw_pdf_response_logs(pdf, response_logs, current_y, generated_at, scope)
    current_y -= 6
    current_y = draw_pdf_next_steps(pdf, alert_data["recommended_steps"], current_y, generated_at, scope)

    return current_y - 8


def build_pdf_report_response(filename, generated_at, scope, alert_sections, severity_counts=None, summary_note=None):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle(filename)
    current_y = start_pdf_page(pdf, generated_at, scope)

    if severity_counts is not None:
        current_y = draw_pdf_summary_grid(
            pdf,
            severity_counts,
            sum(severity_counts.values()),
            current_y,
        )

    if summary_note:
        current_y = ensure_pdf_space(pdf, current_y, 42, generated_at, scope)
        current_y = draw_pdf_wrapped_text(
            pdf,
            summary_note,
            48,
            current_y,
            516,
            font_name="Helvetica",
            font_size=10,
            color=HexColor("#334155"),
        ) - 6

    for section in alert_sections:
        current_y = draw_pdf_alert_card(
            pdf,
            section["title"],
            section["alert_data"],
            section["response_logs"],
            current_y,
            generated_at,
            scope,
        )

    pdf.save()
    pdf_bytes = buffer.getvalue()
    buffer.close()

    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    file_path = os.path.join(FRONTEND_BUILD_DIR, path)

    if path and os.path.exists(file_path) and os.path.isfile(file_path):
        return send_from_directory(FRONTEND_BUILD_DIR, path)

    return send_from_directory(FRONTEND_BUILD_DIR, "index.html")


if __name__ == "__main__":
    app.run(host=SIEM_BIND_HOST, port=SIEM_PORT, debug=SIEM_DEBUG)
