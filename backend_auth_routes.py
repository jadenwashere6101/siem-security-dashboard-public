from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash

from backend_audit_helpers import log_audit_event
from backend_auth import User, get_user_by_username
from core.extensions import limiter


auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
def login():
    data = request.get_json() or {}

    username = data.get("username")
    password = data.get("password")

    if username == current_app.config["SIEM_ADMIN_USERNAME"] and password == current_app.config["SIEM_ADMIN_PASSWORD"]:
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


@auth_bp.route("/logout", methods=["POST"])
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


@auth_bp.route("/auth/me", methods=["GET"])
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
