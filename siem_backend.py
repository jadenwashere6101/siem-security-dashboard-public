from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from psycopg2.extras import Json
from dotenv import load_dotenv
from functools import wraps
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash, generate_password_hash
import logging
import os
from io import BytesIO
from datetime import datetime, timezone
import requests
import psycopg2
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas


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


def get_db_connection():
    return psycopg2.connect(
        dbname=env_first("SIEM_DB_NAME", "DB_NAME"),
        user=env_first("SIEM_DB_USER", "DB_USER"),
        host=env_first("SIEM_DB_HOST", "DB_HOST"),
        password=env_first("SIEM_DB_PASSWORD", "DB_PASSWORD")
    )


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
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[]
)
FRONTEND_BUILD_DIR = os.path.join(app.root_path, "frontend", "build")
app.config["SECRET_KEY"] = env_first("SIEM_SECRET_KEY", "SECRET_KEY")

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


logging.basicConfig(level=logging.INFO)


API_KEY_HEADER = "X-API-Key"
INGEST_API_KEY = env_first("SIEM_INGEST_API_KEY", "INGEST_API_KEY", default="")
ABUSEIPDB_API_KEY = env_first("SIEM_ABUSEIPDB_API_KEY", "ABUSEIPDB_API_KEY")
REPUTATION_CACHE = {}

def require_api_key():
    if not INGEST_API_KEY:
        return jsonify({"error": "Service unavailable"}), 503

    api_key = request.headers.get(API_KEY_HEADER, "")
    if api_key != INGEST_API_KEY:
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


def has_valid_location(location):
    if not isinstance(location, dict):
        return False

    lat = location.get("lat")
    lon = location.get("lon")
    return lat not in (None, "") and lon not in (None, "")


@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "service": "siem_dashboard"}), 200


@app.route("/ingest", methods=["POST"])
@limiter.limit("200 per minute")
def add_event():
    api_key = request.headers.get("X-API-Key")
    if api_key != INGEST_API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

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

        cur.execute(
            """
            INSERT INTO events (event_type, severity, source_ip, message, app_name, environment, raw_payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (event_type, severity, source_ip, message, app_name, environment, Json(raw_payload)),
        )

        alerts_created = []

        if event_type == "failed_login":
            alerts_created = _generate_failed_login_alerts_core(cur, conn)
            alerts_created.extend(_generate_password_spraying_alerts_core(cur, conn))
            alerts_created.extend(_generate_successful_login_after_spray_alerts_core(cur, conn))
        elif event_type == "successful_login":
            alerts_created.extend(_generate_successful_login_after_spray_alerts_core(cur, conn))
        elif event_type == "port_scan":
            alerts_created = _generate_port_scan_alerts_core(cur, conn)

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


def execute_response_action(cur, alert_id, source_ip, response_action):
    status = "executed"
    details = None

    if response_action == "block_ip":
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


def _generate_failed_login_alerts_core(cur, conn):
    cur.execute(
        """
        SELECT source_ip, COUNT(*) as attempts
        FROM events
        WHERE event_type IN ('failed_login', 'login_failure')
        AND created_at >= NOW() - INTERVAL '15 minutes'
        GROUP BY source_ip
        HAVING COUNT(*) >= 3
        """
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
              AND event_type IN ('failed_login', 'login_failure')
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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                source_ip,
                "failed_login_threshold",
                "high",
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


def _generate_password_spraying_alerts_core(cur, conn):
    cur.execute(
        """
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
              AND created_at >= NOW() - INTERVAL '15 minutes'
        )
        SELECT source_ip, COUNT(DISTINCT extracted_username) AS distinct_username_count
        FROM extracted_failed_logins
        WHERE extracted_username IS NOT NULL
        GROUP BY source_ip
        HAVING COUNT(DISTINCT extracted_username) >= 5
        """
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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                source_ip,
                "password_spraying_threshold",
                "high",
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


def _generate_successful_login_after_spray_alerts_core(cur, conn):
    cur.execute(
        """
        WITH recent_successes AS (
            SELECT source_ip, created_at AS success_at
            FROM events
            WHERE event_type = 'successful_login'
              AND created_at >= NOW() - INTERVAL '15 minutes'
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
              AND created_at >= NOW() - INTERVAL '30 minutes'
        ),
        qualifying_successes AS (
            SELECT
                recent_successes.source_ip,
                MAX(recent_successes.success_at) AS success_at
            FROM recent_successes
            JOIN extracted_failed_logins
              ON extracted_failed_logins.source_ip = recent_successes.source_ip
             AND extracted_failed_logins.extracted_username IS NOT NULL
             AND extracted_failed_logins.created_at >= recent_successes.success_at - INTERVAL '15 minutes'
             AND extracted_failed_logins.created_at <= recent_successes.success_at
            GROUP BY recent_successes.source_ip, recent_successes.success_at
            HAVING COUNT(DISTINCT extracted_failed_logins.extracted_username) >= 5
        )
        SELECT source_ip, success_at
        FROM qualifying_successes
        """
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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                source_ip,
                "successful_login_after_spray",
                "critical",
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


def _generate_port_scan_alerts_core(cur, conn):
    cur.execute(
        """
        SELECT source_ip, COUNT(*) as attempts
        FROM events
        WHERE event_type = 'port_scan'
          AND created_at >= NOW() - INTERVAL '15 minutes'
        GROUP BY source_ip
        HAVING COUNT(*) >= 2
        """
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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                source_ip,
                "port_scan_threshold",
                "medium",
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
                response_status
            FROM alerts
            ORDER BY created_at DESC
        """)

        rows = cur.fetchall()

        alerts = [
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
                "reputation_score": row[11],
                "reputation_label": row[12],
                "reputation_source": row[13],
                "reputation_summary": row[14],
                "response_action": row[15],
                "response_status": row[16],
            })
            for row in rows
        ]


        cur.close()
        conn.close()

        return jsonify(alerts), 200

    except Exception as e:
        app.logger.error("Error in get_alerts: %s", e)
        return jsonify({"error": "Internal server error"}), 500


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

        execution_status = execute_response_action(cur, alert_id, str(source_ip), action)

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

        return jsonify({
            "message": "Action executed successfully",
            "alert_id": alert_id,
            "action": action,
            "response_status": execution_status
        }), 200

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

        conn.commit()
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
    app.run(host=SIEM_BIND_HOST, port=SIEM_PORT, debug=True)
