from flask import Flask, current_app, jsonify, send_from_directory
from flask_cors import CORS
from flask_login import LoginManager
from dotenv import load_dotenv
from core.auth import load_user
from werkzeug.middleware.proxy_fix import ProxyFix
import logging
import os
from routes.admin_routes import admin_bp
from backend_alert_mutation_routes import alert_mutation_bp
from backend_alerts_events_routes import alerts_events_bp
from backend_auth_routes import auth_bp
from routes.blocklist_routes import blocklist_bp
from backend_ingest_engine import ingest_normalized_event
from core.extensions import limiter
from routes.ingest_routes import ingest_bp
from routes.reporting_routes import reporting_bp


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


# ============================================================================
# Flask App Setup
# ============================================================================


def create_app():
    load_dotenv()

    app = Flask(__name__, static_folder="frontend/build/static")
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    limiter.init_app(app)
    app.config["FRONTEND_BUILD_DIR"] = os.path.join(app.root_path, "frontend", "build")
    app.config["SECRET_KEY"] = env_first("SIEM_SECRET_KEY", "SECRET_KEY")
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = not SIEM_DEBUG
    app.config["SIEM_ADMIN_USERNAME"] = env_first("SIEM_ADMIN_USERNAME", "ADMIN_USERNAME")
    app.config["SIEM_ADMIN_PASSWORD"] = env_first("SIEM_ADMIN_PASSWORD", "ADMIN_PASSWORD")

    if not app.config["SIEM_ADMIN_USERNAME"] or not app.config["SIEM_ADMIN_PASSWORD"]:
        raise RuntimeError("Missing ADMIN_USERNAME or ADMIN_PASSWORD environment variables")

    CORS(app, resources={r"/*": {"origins": SIEM_ALLOWED_ORIGINS}}, supports_credentials=True)
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

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

    app.register_blueprint(auth_bp)
    app.register_blueprint(blocklist_bp)
    app.register_blueprint(reporting_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(alerts_events_bp)
    app.register_blueprint(alert_mutation_bp)
    app.register_blueprint(ingest_bp)

    return app


app = create_app()

logging.basicConfig(level=logging.INFO)


@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "service": "siem_dashboard"}), 200


# ============================================================================
# Frontend Serving / Entrypoint
# ============================================================================


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    frontend_build_dir = current_app.config["FRONTEND_BUILD_DIR"]
    file_path = os.path.join(frontend_build_dir, path)

    if path and os.path.exists(file_path) and os.path.isfile(file_path):
        return send_from_directory(frontend_build_dir, path)

    return send_from_directory(frontend_build_dir, "index.html")


if __name__ == "__main__":
    app.run(host=SIEM_BIND_HOST, port=SIEM_PORT, debug=SIEM_DEBUG)
