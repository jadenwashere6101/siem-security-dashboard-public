import os

# Must be set before siem_backend is imported. load_dotenv() in siem_backend
# does not override vars already in the environment, so these take precedence
# over any .env file. The RuntimeError at line ~189 requires both admin vars.
os.environ.setdefault("SIEM_ADMIN_USERNAME", "testadmin")
os.environ.setdefault("SIEM_ADMIN_PASSWORD", "testpassword123!")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
# SIEM_DEBUG=true makes SESSION_COOKIE_SECURE=False, which lets the test
# client send session cookies over plain HTTP.
os.environ.setdefault("SIEM_DEBUG", "true")

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import MagicMock, patch

import siem_backend

# Apply once for the whole session before any request is made.
siem_backend.app.config["TESTING"] = True
siem_backend.app.config["SESSION_COOKIE_SECURE"] = False
# Disable rate limiting so repeated login calls in tests don't get throttled.
siem_backend.limiter.enabled = False


@pytest.fixture
def client():
    with siem_backend.app.test_client() as c:
        yield c


@pytest.fixture
def mock_db():
    """Silence all DB I/O in the auth and audit modules.

    backend_auth and backend_audit_helpers each imported get_db_connection
    into their own namespace via `from backend_db import get_db_connection`.
    Patching the name in each module's namespace is the correct target.

    The mock cursor returns None from fetchone() by default, which makes
    get_user_by_username() return None (unknown user) unless overridden.
    """
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.fetchone.return_value = None

    with patch("backend_auth.get_db_connection", return_value=mock_conn), \
         patch("backend_audit_helpers.get_db_connection", return_value=mock_conn):
        yield mock_conn, mock_cur
