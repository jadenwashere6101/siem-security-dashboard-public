import os
import uuid

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

import psycopg2
from psycopg2 import sql
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

    core.auth and core.audit_helpers each imported get_db_connection
    into their own namespace via `from core.db import get_db_connection`.
    Patching the name in each module's namespace is the correct target.

    The mock cursor returns None from fetchone() by default, which makes
    get_user_by_username() return None (unknown user) unless overridden.
    """
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.fetchone.return_value = None

    with patch("core.auth.get_db_connection", return_value=mock_conn), \
         patch("core.audit_helpers.get_db_connection", return_value=mock_conn):
        yield mock_conn, mock_cur


@pytest.fixture
def postgres_db():
    """Real PostgreSQL connection isolated to a per-test schema.

    Detection and correlation code depends on PostgreSQL-specific behavior,
    including INET/JSONB columns, SERIAL sequences, and currval() semantics.
    SQLite or cursor mocks would not exercise the architecture contract.
    """
    dsn = os.getenv("SIEM_TEST_DATABASE_URL") or os.getenv("TEST_DATABASE_URL") or "dbname=postgres"
    schema_name = f"siem_test_{uuid.uuid4().hex}"
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    schema_path = os.path.join(repo_root, "schema.sql")
    conn = None
    cur = None

    try:
        conn = psycopg2.connect(dsn)
    except psycopg2.Error as error:
        pytest.skip(f"PostgreSQL test database unavailable: {error}")

    try:
        conn.autocommit = True
        with conn.cursor() as setup_cur:
            setup_cur.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name)))

        conn.autocommit = False
        cur = conn.cursor()
        cur.execute(
            sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema_name))
        )

        with open(schema_path, "r", encoding="utf-8") as schema_file:
            cur.execute(schema_file.read())
        conn.commit()

        yield conn, cur
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.rollback()
            conn.autocommit = True
            with conn.cursor() as cleanup_cur:
                cleanup_cur.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name))
                )
            conn.close()
