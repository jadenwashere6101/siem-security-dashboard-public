from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from werkzeug.security import generate_password_hash

from core.source_health import (
    SOURCE_HEALTH_CHECKPOINT_SQL,
    SOURCE_HEALTH_STATE_SQL,
    aggregate_source_health,
)
from core.source_ingestion_health_state import record_persisted_push_event
from core.source_inventory import CANONICAL_SOURCE_IDS, CANONICAL_SOURCES
from core.source_inventory import (
    AZURE_CHECKPOINT_FRESHNESS_SECONDS,
    INGESTION_MODE_CHECKPOINT,
    INGESTION_MODE_PUSH,
    PUSH_APPLICATION_FRESHNESS_SECONDS,
    PUSH_CONTINUOUS_FRESHNESS_SECONDS,
    PUSH_SPARSE_FRESHNESS_SECONDS,
    SourceDefinition,
)
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
    raw_payload=None,
):
    cur.execute(
        """
        INSERT INTO events (
            event_type, severity, source_ip, source, source_type,
            message, app_name, environment, raw_payload, created_at
        )
        VALUES ('normal_activity', 'low', %s, %s, %s, 'Source health test',
                'source_health_test', 'test', %s, %s)
        RETURNING created_at
        """,
        (source_ip, source, source_type, json.dumps(raw_payload or {}), created_at),
    )
    persisted_at = cur.fetchone()[0]
    record_persisted_push_event(
        cur,
        source=source,
        ingested_at=persisted_at,
        raw_payload=raw_payload or {},
    )


def mark_backfill_complete(cur, source):
    cur.execute(
        """
        INSERT INTO source_ingestion_health_state (
            source, historical_backfill_complete,
            backfill_high_water_event_id, backfill_last_processed_event_id
        )
        VALUES (%s, TRUE, 0, 0)
        ON CONFLICT (source) DO UPDATE
        SET historical_backfill_complete = TRUE,
            backfill_high_water_event_id = 0,
            backfill_last_processed_event_id = 0
        """,
        (source,),
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
    assert [
        (item.source, item.ingestion_mode, item.freshness_threshold_seconds)
        for item in CANONICAL_SOURCES
    ] == [
        ("honeypot", INGESTION_MODE_PUSH, PUSH_SPARSE_FRESHNESS_SECONDS),
        ("bank_app", INGESTION_MODE_PUSH, PUSH_APPLICATION_FRESHNESS_SECONDS),
        ("pfsense", INGESTION_MODE_PUSH, PUSH_CONTINUOUS_FRESHNESS_SECONDS),
        ("nginx", INGESTION_MODE_PUSH, PUSH_APPLICATION_FRESHNESS_SECONDS),
        (
            "azure_insights",
            INGESTION_MODE_CHECKPOINT,
            AZURE_CHECKPOINT_FRESHNESS_SECONDS,
        ),
        ("opentelemetry", INGESTION_MODE_PUSH, PUSH_APPLICATION_FRESHNESS_SECONDS),
    ]


def test_empty_database_returns_all_six_fail_closed_sources(postgres_db):
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
        assert item["ever_seen"] is False
        assert item["health_status"] == "unknown"
        assert item["latest_ingestion_at"] is None
        assert "events_last_hour" not in item
        assert "events_today" not in item
        assert "total_events" not in item


def test_out_of_order_event_cannot_move_state_backward(postgres_db):
    conn, cur = postgres_db
    timestamps = (GENERATED_AT - timedelta(minutes=1), GENERATED_AT - timedelta(hours=2))
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

    assert item["last_event_at"] == "2026-07-12T14:59:00+00:00"
    assert item["latest_ingestion_at"] == "2026-07-12T14:59:00+00:00"
    assert item["ever_seen"] is True


def test_historical_counters_are_omitted_and_unknown_sources_cannot_expand_response(postgres_db):
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

    assert "events_last_hour" not in bank_app
    assert "events_today" not in bank_app
    assert "total_events" not in bank_app
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


def test_recent_push_ingestion_without_checkpoint_is_healthy(postgres_db):
    conn, cur = postgres_db
    insert_event(
        cur,
        source="pfsense",
        source_type="firewall",
        source_ip="9.9.9.9",
        created_at=GENERATED_AT - timedelta(minutes=2),
    )
    conn.commit()

    pfsense = source_entry(
        aggregate_source_health(conn, generated_at=GENERATED_AT), "pfsense"
    )

    assert pfsense["ingestion_mode"] == "push"
    assert pfsense["health_basis"] == "event_ingestion_freshness"
    assert pfsense["health_status"] == "healthy"
    assert pfsense["health_reason"] == "recent_qualifying_ingestion"
    assert pfsense["latest_ingestion_at"] == "2026-07-12T14:58:00+00:00"
    assert pfsense["health_basis_age_seconds"] == 120
    assert "connector_status" not in pfsense


def test_push_ingestion_freshness_boundary_is_inclusive_then_degraded(postgres_db):
    conn, cur = postgres_db
    insert_event(
        cur,
        source="pfsense",
        source_type="firewall",
        source_ip="9.9.9.9",
        created_at=GENERATED_AT - timedelta(seconds=PUSH_CONTINUOUS_FRESHNESS_SECONDS),
    )
    conn.commit()

    at_boundary = source_entry(
        aggregate_source_health(conn, generated_at=GENERATED_AT), "pfsense"
    )
    after_boundary = source_entry(
        aggregate_source_health(conn, generated_at=GENERATED_AT + timedelta(seconds=1)),
        "pfsense",
    )

    assert at_boundary["health_status"] == "healthy"
    assert after_boundary["health_status"] == "degraded"
    assert after_boundary["health_reason"] == "qualifying_ingestion_stale"


def test_never_seen_push_source_is_unknown(postgres_db):
    conn, cur = postgres_db
    mark_backfill_complete(cur, "pfsense")
    conn.commit()

    pfsense = source_entry(
        aggregate_source_health(conn, generated_at=GENERATED_AT), "pfsense"
    )

    assert pfsense["health_status"] == "unknown"
    assert pfsense["health_reason"] == "no_qualifying_ingestion"
    assert pfsense["health_basis_age_seconds"] is None
    assert pfsense["historical_backfill_complete"] is True


def test_incomplete_backfill_fails_closed(postgres_db):
    conn, cur = postgres_db
    cur.execute("INSERT INTO source_ingestion_health_state (source) VALUES ('pfsense')")
    conn.commit()

    pfsense = source_entry(
        aggregate_source_health(conn, generated_at=GENERATED_AT), "pfsense"
    )

    assert pfsense["health_status"] == "unknown"
    assert pfsense["health_reason"] == "historical_backfill_incomplete"
    assert pfsense["historical_backfill_complete"] is False


def test_unclassified_ingestion_mode_fails_closed():
    definition = SourceDefinition(
        "ambiguous_source",
        "custom",
        "Ambiguous Source",
        "live-logs-ambiguous",
        "unknown",
        3600,
    )
    cursor = MagicMock()
    cursor.fetchall.side_effect = [[], []]
    conn = MagicMock()
    conn.cursor.return_value = cursor

    with patch("core.source_health.CANONICAL_SOURCES", (definition,)):
        response = aggregate_source_health(conn, generated_at=GENERATED_AT)

    item = response["sources"][0]
    assert item["health_status"] == "unknown"
    assert item["health_basis"] == "unclassified"
    assert item["health_reason"] == "ingestion_mode_unknown"


def test_explicit_synthetic_ingestion_cannot_make_push_source_healthy(postgres_db):
    conn, cur = postgres_db
    mark_backfill_complete(cur, "pfsense")
    insert_event(
        cur,
        source="pfsense",
        source_type="firewall",
        source_ip="9.9.9.9",
        created_at=GENERATED_AT - timedelta(minutes=1),
        raw_payload={"data_provenance": "synthetic"},
    )
    conn.commit()

    pfsense = source_entry(
        aggregate_source_health(conn, generated_at=GENERATED_AT), "pfsense"
    )

    assert pfsense["last_event_at"] == "2026-07-12T14:59:00+00:00"
    assert pfsense["latest_ingestion_at"] is None
    assert pfsense["health_status"] == "unknown"


def test_stale_real_plus_recent_synthetic_remains_degraded(postgres_db):
    conn, cur = postgres_db
    insert_event(
        cur,
        source="pfsense",
        source_type="firewall",
        source_ip="9.9.9.9",
        created_at=GENERATED_AT - timedelta(hours=1),
    )
    insert_event(
        cur,
        source="pfsense",
        source_type="firewall",
        source_ip="9.9.9.9",
        created_at=GENERATED_AT - timedelta(minutes=1),
        raw_payload={"data_provenance": "synthetic"},
    )
    conn.commit()

    pfsense = source_entry(
        aggregate_source_health(conn, generated_at=GENERATED_AT), "pfsense"
    )

    assert pfsense["last_event_at"] == "2026-07-12T14:59:00+00:00"
    assert pfsense["latest_ingestion_at"] == "2026-07-12T14:00:00+00:00"
    assert pfsense["health_status"] == "degraded"


def test_aggregation_issues_only_bounded_state_and_checkpoint_queries():
    cursor = MagicMock()
    cursor.fetchall.side_effect = [[], []]
    conn = MagicMock()
    conn.cursor.return_value = cursor

    aggregate_source_health(conn, generated_at=GENERATED_AT)

    assert cursor.execute.call_count == 2
    assert cursor.execute.call_args_list[0].args[0] == SOURCE_HEALTH_STATE_SQL
    assert "events" not in SOURCE_HEALTH_STATE_SQL.lower()
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
    assert azure["health_status"] == "degraded"
    assert azure["health_basis"] == "poll_checkpoint"
    assert azure["health_reason"] == "checkpoint_failure"
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
    assert nginx["health_status"] == "unknown"


def test_checkpoint_source_requires_fresh_successful_checkpoint(postgres_db):
    conn, cur = postgres_db
    insert_checkpoint(
        cur,
        last_processed_at=GENERATED_AT - timedelta(minutes=5),
        updated_at=GENERATED_AT - timedelta(minutes=5),
    )
    conn.commit()

    fresh = source_entry(
        aggregate_source_health(conn, generated_at=GENERATED_AT), "azure_insights"
    )
    stale = source_entry(
        aggregate_source_health(
            conn,
            generated_at=GENERATED_AT
            + timedelta(seconds=AZURE_CHECKPOINT_FRESHNESS_SECONDS + 1),
        ),
        "azure_insights",
    )

    assert fresh["connector_status"] == "healthy"
    assert fresh["health_status"] == "healthy"
    assert fresh["health_reason"] == "checkpoint_success_fresh"
    assert stale["health_status"] == "degraded"
    assert stale["health_reason"] == "checkpoint_stale"


def test_representative_query_plan_never_reads_events_and_is_source_bounded(postgres_db):
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
    for source in ("honeypot", "bank_app", "pfsense", "nginx", "opentelemetry"):
        mark_backfill_complete(cur, source)
    conn.commit()
    cur.execute("ANALYZE source_ingestion_health_state")
    cur.execute(
        "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + SOURCE_HEALTH_STATE_SQL,
        (["honeypot", "bank_app", "pfsense", "nginx", "opentelemetry"],),
    )
    plan = cur.fetchone()[0][0]["Plan"]

    def walk(node):
        yield node
        for child in node.get("Plans", []):
            yield from walk(child)

    nodes = list(walk(plan))
    relation_names = {node.get("Relation Name") for node in nodes}

    assert "events" not in relation_names
    assert relation_names == {"source_ingestion_health_state"}
    assert plan["Actual Rows"] <= 5


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
            "ever_seen",
            "ingestion_mode",
            "health_status",
            "health_basis",
            "health_reason",
            "freshness_threshold_seconds",
            "health_basis_age_seconds",
            "latest_ingestion_at",
            "historical_backfill_complete",
        }.issubset(set(item))
        assert item["last_event_at"] is None
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
