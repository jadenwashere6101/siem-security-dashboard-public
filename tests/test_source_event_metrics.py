from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from werkzeug.security import generate_password_hash

from core.source_event_metrics import (
    SOURCE_EVENT_METRICS_SQL,
    SOURCE_EVENT_METRICS_STATEMENT_TIMEOUT_MS,
    aggregate_source_event_metrics,
    clear_source_event_metrics_cache,
)
from core.source_inventory import CANONICAL_SOURCES


GENERATED_AT = datetime(2026, 7, 12, 15, 0, 0, tzinfo=timezone.utc)
ADMIN_USER = "testadmin"
ADMIN_PASS = "testpassword123!"
ROLE_LOGIN_SECRET = "role-fixture-login-value"


class RouteSafeConnection:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return self._conn.cursor()

    def close(self):
        return None


def login_super_admin(client):
    response = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert response.status_code == 200


@contextmanager
def logged_in_role(client, role):
    user = {
        "username": f"source_metrics_{role}",
        "password_hash": generate_password_hash(
            ROLE_LOGIN_SECRET, method="pbkdf2:sha256"
        ),
        "role": role,
        "is_active": True,
    }
    with patch("routes.auth_routes.get_user_by_username", return_value=user), patch(
        "core.auth.get_user_by_username", return_value=user
    ), patch("core.audit_helpers.get_db_connection"):
        response = client.post(
            "/login",
            json={"username": user["username"], "password": ROLE_LOGIN_SECRET},
        )
        assert response.status_code == 200
        yield


def source_entry(payload, source):
    return next(item for item in payload["sources"] if item["source"] == source)


def test_metrics_count_actual_canonical_rows_without_alias_double_counting(postgres_db):
    conn, cur = postgres_db
    rows = [
        ("pfsense", GENERATED_AT - timedelta(minutes=15)),
        ("pfsense", GENERATED_AT - timedelta(hours=2)),
        ("pfsense", GENERATED_AT - timedelta(days=1)),
        ("bank_app", GENERATED_AT - timedelta(minutes=30)),
        ("otlp", GENERATED_AT - timedelta(minutes=5)),
        ("web_log", GENERATED_AT - timedelta(minutes=5)),
    ]
    for source, created_at in rows:
        cur.execute(
            """
            INSERT INTO events (
                event_type, severity, source_ip, source, source_type,
                message, app_name, environment, raw_payload, created_at
            )
            VALUES ('normal_activity', 'low', '198.51.100.10', %s, 'test',
                    'Metrics test', 'source_metrics_test', 'test', '{}'::jsonb, %s)
            """,
            (source, created_at),
        )
    conn.commit()

    payload = aggregate_source_event_metrics(
        conn, generated_at=GENERATED_AT, use_cache=False
    )

    assert [item["source"] for item in payload["sources"]] == [
        item.source for item in CANONICAL_SOURCES
    ]
    assert source_entry(payload, "pfsense") == {
        "source": "pfsense",
        "events_last_hour": 1,
        "events_today": 2,
        "total_events": 3,
    }
    assert source_entry(payload, "bank_app")["total_events"] == 1
    assert source_entry(payload, "opentelemetry")["total_events"] == 0
    assert source_entry(payload, "nginx")["total_events"] == 0


def test_metrics_support_multi_million_pfsense_total_without_materializing_rows():
    cursor = MagicMock()
    cursor.fetchall.return_value = [("pfsense", 15_234, 431_209, 5_873_421)]
    conn = MagicMock()
    conn.cursor.return_value = cursor

    payload = aggregate_source_event_metrics(
        conn, generated_at=GENERATED_AT, use_cache=False
    )

    assert source_entry(payload, "pfsense")["total_events"] == 5_873_421
    assert cursor.execute.call_args_list[0].args[0].startswith(
        "SET LOCAL statement_timeout"
    )
    assert cursor.execute.call_args_list[1].args[0] == SOURCE_EVENT_METRICS_SQL


def test_metrics_query_is_index_compatible_and_database_bounded(postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        SELECT indexdef
        FROM pg_indexes
        WHERE tablename = 'events'
          AND indexname = 'idx_events_source_created_at_nist'
        """
    )
    index_definition = cur.fetchone()[0]

    assert "(source, created_at DESC, id DESC)" in index_definition
    assert "FROM events" in SOURCE_EVENT_METRICS_SQL
    assert "source = ANY" in SOURCE_EVENT_METRICS_SQL
    assert "created_at <=" in SOURCE_EVENT_METRICS_SQL
    assert "raw_payload" not in SOURCE_EVENT_METRICS_SQL
    assert 100 <= SOURCE_EVENT_METRICS_STATEMENT_TIMEOUT_MS <= 10_000


def test_successful_metrics_are_cached_without_requerying_events():
    clear_source_event_metrics_cache()
    cursor = MagicMock()
    cursor.fetchall.return_value = [("pfsense", 1, 2, 3)]
    conn = MagicMock()
    conn.cursor.return_value = cursor

    first = aggregate_source_event_metrics(conn, generated_at=GENERATED_AT)
    second = aggregate_source_event_metrics(
        MagicMock(), generated_at=GENERATED_AT + timedelta(minutes=1)
    )

    assert second is first
    assert cursor.execute.call_count == 2
    clear_source_event_metrics_cache()


def test_source_health_metrics_requires_authentication(client):
    response = client.get("/source-health/metrics")

    assert response.status_code == 401


def test_source_health_metrics_allows_analyst(client, postgres_db):
    conn, _cur = postgres_db
    clear_source_event_metrics_cache()

    with logged_in_role(client, "analyst"):
        with patch(
            "routes.source_health_routes.get_db_connection",
            return_value=RouteSafeConnection(conn),
        ):
            response = client.get("/source-health/metrics")

    assert response.status_code == 200
    assert len(response.get_json()["sources"]) == len(CANONICAL_SOURCES)
    clear_source_event_metrics_cache()


def test_source_health_metrics_rejects_viewer(client):
    with logged_in_role(client, "viewer"):
        response = client.get("/source-health/metrics")

    assert response.status_code == 403


def test_metrics_timeout_or_database_failure_is_isolated_as_503(client):
    login_super_admin(client)
    with patch(
        "routes.source_health_routes.aggregate_source_event_metrics",
        side_effect=RuntimeError("statement timeout"),
    ), patch("routes.source_health_routes.get_db_connection", return_value=MagicMock()):
        response = client.get("/source-health/metrics")

    assert response.status_code == 503
    assert response.get_json() == {
        "error": "Historical event counts are temporarily unavailable"
    }
