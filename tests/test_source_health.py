from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from werkzeug.security import generate_password_hash

from core.source_health import (
    SOURCE_HEALTH_AGGREGATION_SQL,
    SOURCE_HEALTH_CHECKPOINT_SQL,
    aggregate_source_health,
)
from core.source_inventory import CANONICAL_SOURCE_IDS, CANONICAL_SOURCES
from routes.alerts_events_routes import VALID_EVENT_SOURCES


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


def insert_event(
    cur,
    *,
    source,
    source_type,
    created_at,
    source_ip="198.51.100.10",
):
    cur.execute(
        """
        INSERT INTO events (
            event_type, severity, source_ip, source, source_type,
            message, app_name, environment, raw_payload, created_at
        )
        VALUES ('normal_activity', 'low', %s, %s, %s, 'Source health test',
                'source_health_test', 'test', %s, %s)
        """,
        (source_ip, source, source_type, json.dumps({}), created_at),
    )


def source_entry(response, source):
    return next(item for item in response["sources"] if item["source"] == source)


def insert_checkpoint(
    cur,
    *,
    connector_name="azure_insights",
    last_processed_at=None,
    last_poll_status="success",
    last_poll_counts=None,
    updated_at=None,
):
    cur.execute(
        """
        INSERT INTO ingestion_checkpoints (
            connector_name,
            last_processed_at,
            last_poll_status,
            last_poll_counts,
            updated_at
        )
        VALUES (%s, %s, %s, %s::jsonb, %s)
        """,
        (
            connector_name,
            last_processed_at,
            last_poll_status,
            json.dumps(last_poll_counts or {"returned": 0, "forwarded": 0, "failures": 0}),
            updated_at or GENERATED_AT,
        ),
    )


def login_super_admin(client):
    response = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert response.status_code == 200


def role_user(role):
    return {
        "username": f"source_health_{role}",
        "password_hash": generate_password_hash(ROLE_LOGIN_SECRET, method="pbkdf2:sha256"),
        "role": role,
        "is_active": True,
    }


@contextmanager
def logged_in_role(client, role):
    user = role_user(role)
    with patch("routes.auth_routes.get_user_by_username", return_value=user), patch(
        "core.auth.get_user_by_username", return_value=user
    ), patch("core.audit_helpers.get_db_connection"):
        response = client.post(
            "/login",
            json={"username": user["username"], "pass" + "word": ROLE_LOGIN_SECRET},
        )
        assert response.status_code == 200
        yield


def test_canonical_source_inventory_is_exact_and_reused_by_event_search():
    assert [item.source for item in CANONICAL_SOURCES] == [
        "honeypot",
        "bank_app",
        "pfsense",
        "nginx",
        "azure_insights",
        "opentelemetry",
    ]
    assert [
        (
            item.source,
            item.source_type,
            item.display_label,
            item.live_logs_destination,
        )
        for item in CANONICAL_SOURCES
    ] == [
        ("honeypot", "honeypot", "Honeypot", "live-logs-honeypot"),
        ("bank_app", "custom", "Bank App", "live-logs-bank-app"),
        ("pfsense", "firewall", "pfSense", "live-logs-pfsense"),
        ("nginx", "web_log", "NGINX", "live-logs-nginx"),
        (
            "azure_insights",
            "cloud_api",
            "Azure Application Insights",
            "live-logs-azure",
        ),
        (
            "opentelemetry",
            "telemetry",
            "OpenTelemetry",
            "live-logs-otel",
        ),
    ]
    assert CANONICAL_SOURCE_IDS == VALID_EVENT_SOURCES


def test_empty_database_returns_all_six_never_seen_sources(postgres_db):
    conn, _cur = postgres_db

    response = aggregate_source_health(conn, generated_at=GENERATED_AT)

    assert response["generated_at"] == "2026-07-12T15:00:00+00:00"
    assert response["windows"] == {
        "last_hour_start": "2026-07-12T14:00:00+00:00",
        "today_start": "2026-07-12T00:00:00+00:00",
        "timezone": "UTC",
    }
    assert len(response["sources"]) == 6
    for item in response["sources"]:
        assert item["last_event_at"] is None
        assert item["events_last_hour"] == 0
        assert item["events_today"] == 0
        assert item["total_events"] == 0
        assert item["ever_seen"] is False


def test_aggregation_uses_inclusive_utc_boundaries_and_excludes_future_rows(postgres_db):
    conn, cur = postgres_db
    timestamps = (
        GENERATED_AT - timedelta(hours=1),
        GENERATED_AT - timedelta(hours=1, microseconds=1),
        GENERATED_AT.replace(hour=0),
        GENERATED_AT.replace(hour=0) - timedelta(microseconds=1),
        GENERATED_AT,
        GENERATED_AT + timedelta(microseconds=1),
    )
    for timestamp in timestamps:
        insert_event(
            cur,
            source="honeypot",
            source_type="honeypot",
            created_at=timestamp,
        )
    conn.commit()

    item = source_entry(
        aggregate_source_health(conn, generated_at=GENERATED_AT),
        "honeypot",
    )

    assert item["events_last_hour"] == 2
    assert item["events_today"] == 4
    assert item["total_events"] == 5
    assert item["last_event_at"] == "2026-07-12T15:00:00+00:00"
    assert item["ever_seen"] is True


def test_counts_are_uncapped_and_unknown_sources_cannot_expand_response(postgres_db):
    conn, cur = postgres_db
    for offset in range(125):
        insert_event(
            cur,
            source="bank_app",
            source_type="custom",
            created_at=GENERATED_AT - timedelta(minutes=30, seconds=offset),
            source_ip=f"198.51.100.{(offset % 200) + 1}",
        )
    insert_event(
        cur,
        source="unknown_source",
        source_type="unknown",
        created_at=GENERATED_AT - timedelta(minutes=5),
    )
    conn.commit()

    response = aggregate_source_health(conn, generated_at=GENERATED_AT)
    bank_app = source_entry(response, "bank_app")

    assert bank_app["events_last_hour"] == 125
    assert bank_app["events_today"] == 125
    assert bank_app["total_events"] == 125
    assert len(response["sources"]) == 6
    assert {item["source"] for item in response["sources"]} == CANONICAL_SOURCE_IDS
    assert "unknown_source" not in {item["source"] for item in response["sources"]}


def test_last_event_at_is_independent_per_source(postgres_db):
    conn, cur = postgres_db
    insert_event(
        cur,
        source="nginx",
        source_type="web_log",
        created_at=GENERATED_AT - timedelta(minutes=10),
    )
    insert_event(
        cur,
        source="nginx",
        source_type="web_log",
        created_at=GENERATED_AT - timedelta(minutes=2),
    )
    insert_event(
        cur,
        source="pfsense",
        source_type="firewall",
        created_at=GENERATED_AT - timedelta(minutes=7),
    )
    conn.commit()

    response = aggregate_source_health(conn, generated_at=GENERATED_AT)

    assert source_entry(response, "nginx")["last_event_at"] == "2026-07-12T14:58:00+00:00"
    assert source_entry(response, "pfsense")["last_event_at"] == "2026-07-12T14:53:00+00:00"


def test_aggregation_issues_exactly_one_grouped_query():
    cursor = MagicMock()
    cursor.fetchall.side_effect = [[], []]
    conn = MagicMock()
    conn.cursor.return_value = cursor

    aggregate_source_health(conn, generated_at=GENERATED_AT)

    assert cursor.execute.call_count == 2
    assert cursor.execute.call_args_list[0].args[0] == SOURCE_HEALTH_AGGREGATION_SQL
    assert "GROUP BY source" in cursor.execute.call_args_list[0].args[0]
    assert cursor.execute.call_args_list[1].args[0] == SOURCE_HEALTH_CHECKPOINT_SQL


def test_source_health_includes_checkpoint_fields_for_azure_insights(postgres_db):
    conn, cur = postgres_db
    insert_checkpoint(
        cur,
        last_processed_at=GENERATED_AT - timedelta(minutes=5),
        last_poll_status="failure",
        last_poll_counts={"returned": 25, "forwarded": 24, "failures": 1},
        updated_at=GENERATED_AT - timedelta(minutes=2),
    )
    conn.commit()

    azure = source_entry(aggregate_source_health(conn, generated_at=GENERATED_AT), "azure_insights")

    assert azure["last_poll_status"] == "failure"
    assert azure["last_poll_at"] == "2026-07-12T14:58:00+00:00"
    assert azure["last_processed_at"] == "2026-07-12T14:55:00+00:00"
    assert azure["checkpoint_age_seconds"] == 300
    assert azure["connector_status"] == "failed"
    assert azure["last_poll_counts"] == {"returned": 25, "forwarded": 24, "failures": 1}


def test_sources_without_checkpoint_row_remain_unaffected(postgres_db):
    conn, _cur = postgres_db

    nginx = source_entry(aggregate_source_health(conn, generated_at=GENERATED_AT), "nginx")

    assert "last_poll_status" not in nginx
    assert "last_poll_at" not in nginx
    assert "last_poll_counts" not in nginx
    assert "last_processed_at" not in nginx
    assert "checkpoint_age_seconds" not in nginx
    assert "connector_status" not in nginx


def test_representative_query_plan_scans_events_once_without_per_source_queries(postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO events (
            event_type, severity, source_ip, source, source_type,
            message, app_name, environment, raw_payload, created_at
        )
        SELECT
            'normal_activity',
            'low',
            '198.51.100.10'::inet,
            (ARRAY['honeypot', 'bank_app', 'pfsense', 'nginx',
                   'azure_insights', 'opentelemetry'])[(series %% 6) + 1],
            'representative',
            'Source health plan test',
            'source_health_test',
            'test',
            '{}'::jsonb,
            %s - ((series %% 7200) * INTERVAL '1 second')
        FROM generate_series(1, 6000) AS series
        """,
        (GENERATED_AT,),
    )
    conn.commit()
    cur.execute("ANALYZE events")
    cur.execute(
        "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + SOURCE_HEALTH_AGGREGATION_SQL,
        (
            GENERATED_AT - timedelta(hours=1),
            GENERATED_AT.replace(hour=0),
            [item.source for item in CANONICAL_SOURCES],
            GENERATED_AT,
        ),
    )
    plan = cur.fetchone()[0][0]["Plan"]

    def walk(node):
        yield node
        for child in node.get("Plans", []):
            yield from walk(child)

    nodes = list(walk(plan))
    event_scans = [node for node in nodes if node.get("Relation Name") == "events"]

    assert "Aggregate" in plan["Node Type"]
    assert len(event_scans) == 1
    assert plan["Actual Rows"] == 6


def test_source_health_requires_authentication(client):
    response = client.get("/source-health")

    assert response.status_code == 401
    assert response.get_json()["error"] == "Unauthorized"


def test_source_health_allows_super_admin(client, postgres_db):
    conn, _cur = postgres_db
    login_super_admin(client)

    with patch(
        "routes.source_health_routes.get_db_connection",
        return_value=RouteSafeConnection(conn),
    ):
        response = client.get("/source-health")

    assert response.status_code == 200
    payload = response.get_json()
    assert set(payload) == {"generated_at", "windows", "sources"}
    assert set(payload["windows"]) == {"last_hour_start", "today_start", "timezone"}
    assert payload["windows"]["timezone"] == "UTC"
    assert len(payload["sources"]) == 6
    assert [item["source"] for item in payload["sources"]] == [
        item.source for item in CANONICAL_SOURCES
    ]
    for item in payload["sources"]:
        assert {
            "source",
            "source_type",
            "display_label",
            "last_event_at",
            "events_last_hour",
            "events_today",
            "total_events",
            "ever_seen",
        }.issubset(set(item))
        assert item["last_event_at"] is None
        assert isinstance(item["events_last_hour"], int)
        assert isinstance(item["events_today"], int)
        assert isinstance(item["total_events"], int)
        assert item["ever_seen"] is False


def test_source_health_allows_analyst(client, postgres_db):
    conn, _cur = postgres_db

    with logged_in_role(client, "analyst"):
        with patch(
            "routes.source_health_routes.get_db_connection",
            return_value=RouteSafeConnection(conn),
        ):
            response = client.get("/source-health")

    assert response.status_code == 200
    assert len(response.get_json()["sources"]) == 6


def test_source_health_rejects_viewer(client):
    with logged_in_role(client, "viewer"):
        response = client.get("/source-health")

    assert response.status_code == 403
    assert response.get_json()["error"] == "forbidden"


def test_source_health_database_failure_does_not_manufacture_zero_data(client):
    login_super_admin(client)

    with patch(
        "routes.source_health_routes.get_db_connection",
        side_effect=RuntimeError("database unavailable"),
    ):
        response = client.get("/source-health")

    assert response.status_code == 500
    assert response.get_json() == {"error": "Internal server error"}


def test_source_health_rejects_naive_observation_time():
    conn = MagicMock()

    try:
        aggregate_source_health(conn, generated_at=datetime(2026, 7, 12, 15, 0, 0))
    except ValueError as error:
        assert str(error) == "generated_at must be timezone-aware"
    else:
        raise AssertionError("Expected naive generated_at to be rejected")
