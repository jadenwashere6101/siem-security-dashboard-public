"""Phase 1 tests for indicator registry and response command service."""

from datetime import datetime, timedelta, timezone

import pytest

from core.indicator_response_registry import (
    append_registry_event,
    apply_monitor_expiry,
    get_indicator_by_value,
    list_registry_events,
    list_registry_records,
    upsert_indicator_identity,
)
from core.response_command_contracts import (
    DISPOSITION_BLOCKLIST_TRACKED,
    DISPOSITION_ESCALATED,
    DISPOSITION_MONITORED,
    INDICATOR_TYPE_IP,
    ORIGIN_MANUAL_ALERT,
    ResponseCommandRequest,
)
from core.response_command_service import execute_response_command


def _insert_alert(cur, source_ip="8.8.8.8"):
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message)
        VALUES ('test', 'high', %s, 'canonical command test')
        RETURNING id
        """,
        (source_ip,),
    )
    return cur.fetchone()[0]


def test_registry_upsert_normalizes_duplicate_ips(postgres_db):
    conn, _cur = postgres_db
    first = upsert_indicator_identity(
        conn, indicator_type=INDICATOR_TYPE_IP, indicator_value="8.8.4.4"
    )
    second = upsert_indicator_identity(
        conn, indicator_type=INDICATOR_TYPE_IP, indicator_value="8.8.4.4"
    )
    assert first["id"] == second["id"]
    conn.commit()


def test_registry_event_idempotency(postgres_db):
    conn, _cur = postgres_db
    record = upsert_indicator_identity(
        conn, indicator_type=INDICATOR_TYPE_IP, indicator_value="1.1.1.1"
    )
    first = append_registry_event(
        conn,
        registry_id=record["id"],
        event_type="note",
        requested_action="monitor",
        outcome="succeeded",
        origin_surface="test",
        idempotency_key="evt-1",
    )
    second = append_registry_event(
        conn,
        registry_id=record["id"],
        event_type="note",
        requested_action="monitor",
        outcome="succeeded",
        origin_surface="test",
        idempotency_key="evt-1",
    )
    assert first["id"] == second["id"]
    events = list_registry_events(conn, record["id"])
    assert len(events) == 1
    conn.commit()


def test_block_ip_command_creates_and_reuses_blocklist(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, "1.2.3.4")
    conn.commit()

    first = execute_response_command(
        conn,
        ResponseCommandRequest(
            action="block_ip",
            indicator_value="1.2.3.4",
            alert_id=alert_id,
            origin_surface=ORIGIN_MANUAL_ALERT,
            actor_user_id=None,
            idempotency_key="cmd-block-1",
        ),
    )
    conn.commit()
    assert first.success is True
    assert first.blocked_ip_id is not None
    assert first.idempotent is False
    assert first.enforcement == "none"
    assert first.disposition == DISPOSITION_BLOCKLIST_TRACKED

    second = execute_response_command(
        conn,
        ResponseCommandRequest(
            action="block_ip",
            indicator_value="1.2.3.4",
            alert_id=alert_id,
            origin_surface=ORIGIN_MANUAL_ALERT,
            idempotency_key="cmd-block-2",
        ),
    )
    conn.commit()
    assert second.success is True
    assert second.idempotent is True
    assert second.blocked_ip_id == first.blocked_ip_id

    cur.execute(
        "SELECT COUNT(*) FROM blocked_ips WHERE ip_address = %s AND status = 'active'",
        ("1.2.3.4",),
    )
    assert cur.fetchone()[0] == 1


def test_block_ip_rejects_private_target(postgres_db):
    conn, _cur = postgres_db
    result = execute_response_command(
        conn,
        ResponseCommandRequest(
            action="block_ip",
            indicator_value="10.0.0.8",
            origin_surface=ORIGIN_MANUAL_ALERT,
            idempotency_key="cmd-block-private",
        ),
    )
    assert result.success is False
    assert result.error_code in {"invalid_indicator", "protected_target"}


def test_monitor_and_escalate_are_durable(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, "9.9.9.9")
    conn.commit()

    monitored = execute_response_command(
        conn,
        ResponseCommandRequest(
            action="monitor",
            indicator_value="9.9.9.9",
            alert_id=alert_id,
            origin_surface=ORIGIN_MANUAL_ALERT,
            idempotency_key="cmd-monitor-1",
        ),
    )
    conn.commit()
    assert monitored.success is True
    assert monitored.disposition == DISPOSITION_MONITORED
    record = get_indicator_by_value(
        conn, indicator_type=INDICATOR_TYPE_IP, indicator_value="9.9.9.9"
    )
    assert record["current_disposition"] == DISPOSITION_MONITORED

    escalated = execute_response_command(
        conn,
        ResponseCommandRequest(
            action="flag_high_priority",
            indicator_value="9.9.9.9",
            alert_id=alert_id,
            origin_surface=ORIGIN_MANUAL_ALERT,
            idempotency_key="cmd-escalate-1",
        ),
    )
    conn.commit()
    assert escalated.success is True
    assert escalated.incident_id is not None
    assert escalated.disposition == DISPOSITION_ESCALATED
    cur.execute("SELECT COUNT(*) FROM incidents WHERE id = %s", (escalated.incident_id,))
    assert cur.fetchone()[0] == 1


def test_registry_list_and_expiry(postgres_db):
    conn, _cur = postgres_db
    record = upsert_indicator_identity(
        conn, indicator_type=INDICATOR_TYPE_IP, indicator_value="4.4.4.4"
    )
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    append_registry_event(
        conn,
        registry_id=record["id"],
        event_type="monitor_started",
        requested_action="monitor",
        outcome="succeeded",
        origin_surface="test",
        disposition_after=DISPOSITION_MONITORED,
        expires_at=past,
        idempotency_key="monitor-exp-1",
    )
    conn.commit()
    updated = apply_monitor_expiry(conn, now=datetime.now(timezone.utc))
    conn.commit()
    assert updated >= 1
    listing = list_registry_records(conn, disposition="expired")
    assert listing["total"] >= 1
