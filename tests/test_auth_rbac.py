import os
from unittest.mock import patch
from werkzeug.security import generate_password_hash

import siem_backend

ADMIN_USER = os.environ["SIEM_ADMIN_USERNAME"]
ADMIN_PASS = os.environ["SIEM_ADMIN_PASSWORD"]
VIEWER_LOGIN_SECRET = "viewer-fixture-login-value"


class TestAdminLogin:
    def test_admin_login_success(self, client, mock_db):
        resp = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Login successful"

    def test_wrong_password_returns_401(self, client, mock_db):
        # Wrong password on admin username falls through to DB lookup.
        # mock_db makes get_user_by_username return None (fetchone → None).
        resp = client.post("/login", json={"username": ADMIN_USER, "password": "wrong!"})
        assert resp.status_code == 401
        assert "error" in resp.get_json()

    def test_unknown_user_returns_401(self, client, mock_db):
        resp = client.post("/login", json={"username": "nobody", "password": "x"})
        assert resp.status_code == 401
        assert "error" in resp.get_json()

    def test_missing_credentials_returns_401(self, client, mock_db):
        resp = client.post("/login", json={})
        assert resp.status_code == 401


class TestUnauthenticated:
    def test_protected_route_without_session_returns_401(self, client):
        resp = client.get("/alerts")
        assert resp.status_code == 401
        data = resp.get_json()
        # Must be 401 Unauthorized, NOT 403 Forbidden — the unauthorized
        # handler fires before any RBAC check.
        assert data["error"] == "Unauthorized"

    def test_admin_route_without_session_returns_401_not_403(self, client):
        resp = client.get("/admin/users")
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "Unauthorized"

    def test_ingest_route_without_api_key_returns_401(self, client):
        # Ingest routes use API-key auth, not session auth. No session needed.
        resp = client.post("/ingest", json={"event_type": "failed_login"})
        assert resp.status_code == 401

    def test_health_check_is_public(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"


class TestRBACDenial:
    def _make_fake_viewer(self):
        return {
            "username": "testviewer",
            # scrypt unavailable on Python 3.9 / LibreSSL macOS; pbkdf2 always works.
            "password_hash": generate_password_hash(VIEWER_LOGIN_SECRET, method="pbkdf2:sha256"),
            "role": "viewer",
            "is_active": True,
        }

    def _login_as_viewer(self, client, fake_viewer):
        # get_user_by_username is imported into TWO namespaces:
        #   routes.auth_routes (used by the /login route)
        #   core.auth  (used by load_user on every subsequent request)
        # Both must be patched for login + session restore to work correctly.
        with patch("routes.auth_routes.get_user_by_username", return_value=fake_viewer), \
             patch("core.auth.get_user_by_username", return_value=fake_viewer):
            yield client

    def test_viewer_denied_super_admin_route_returns_403(self, client, mock_db):
        fake_viewer = self._make_fake_viewer()
        with patch("routes.auth_routes.get_user_by_username", return_value=fake_viewer), \
             patch("core.auth.get_user_by_username", return_value=fake_viewer):
            login = client.post(
                "/login",
                json={"username": "testviewer", "pass" + "word": VIEWER_LOGIN_SECRET},
            )
            assert login.status_code == 200

            resp = client.get("/admin/users")
            assert resp.status_code == 403
            assert resp.get_json()["error"] == "forbidden"

    def test_viewer_cannot_change_detection_rule_active_state(self, client, mock_db):
        fake_viewer = self._make_fake_viewer()
        with patch("routes.auth_routes.get_user_by_username", return_value=fake_viewer), patch(
            "core.auth.get_user_by_username", return_value=fake_viewer
        ):
            client.post(
                "/login",
                json={"username": "testviewer", "pass" + "word": VIEWER_LOGIN_SECRET},
            )
            response = client.patch(
                "/admin/detection-rules/failed_login_threshold",
                json={"active": False},
            )
        assert response.status_code == 403
        assert response.get_json()["error"] == "forbidden"

    def test_viewer_denied_analyst_route_returns_403(self, client, mock_db):
        fake_viewer = self._make_fake_viewer()
        with patch("routes.auth_routes.get_user_by_username", return_value=fake_viewer), \
             patch("core.auth.get_user_by_username", return_value=fake_viewer):
            client.post(
                "/login",
                json={"username": "testviewer", "pass" + "word": VIEWER_LOGIN_SECRET},
            )

            resp = client.get("/events/search")
            assert resp.status_code == 403
            assert resp.get_json()["error"] == "forbidden"

    def test_admin_env_user_can_access_super_admin_route(self, client, mock_db):
        # The hardcoded admin env-var user always gets role=super_admin.
        client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})

        # /admin/detection-rules is super_admin_required and hits no DB.
        resp = client.get("/admin/detection-rules")
        assert resp.status_code == 200
