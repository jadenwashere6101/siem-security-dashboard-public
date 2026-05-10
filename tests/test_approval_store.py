from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from psycopg2 import IntegrityError

from core.approval_store import (
    approve_request,
    create_approval_request,
    create_playbook_step_approval_request,
    deny_request,
    expire_pending_requests,
    get_active_playbook_step_approval_request,
    get_approval_request,
    list_approval_events,
    list_approval_requests,
)
from core import playbook_store


def _insert_user(cur, username="analyst1", role="analyst"):
    cur.execute(
        """
        INSERT INTO users (username, password_hash, role)
        VALUES (%s, 'hash', %s)
        RETURNING id
        """,
        (username, role),
    )
    return cur.fetchone()[0]


def _insert_incident(cur, source_ip="203.0.113.10"):
    cur.execute(
        """
        INSERT INTO incidents (title, severity, priority, status, source_ip)
        VALUES ('Approval incident', 'HIGH', 'P2', 'open', %s::inet)
        RETURNING id
        """,
        (source_ip,),
    )
    return cur.fetchone()[0]


def _insert_alert(cur, source_ip="203.0.113.10"):
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message, status)
        VALUES ('approval_test_alert', 'HIGH', %s::inet, 'approval test', 'open')
        RETURNING id
        """,
        (source_ip,),
    )
    return cur.fetchone()[0]


def _insert_queue_item(cur, source_ip="203.0.113.10"):
    alert_id = _insert_alert(cur, source_ip)
    cur.execute(
        """
        INSERT INTO response_actions_queue (
            idempotency_key, alert_id, source_ip, action
        )
        VALUES (%s, %s, %s::inet, 'block_ip')
        RETURNING id
        """,
        (f"approval-test-{alert_id}", alert_id, source_ip),
    )
    return cur.fetchone()[0]


def _insert_playbook_execution(conn, cur):
    alert_id = _insert_alert(cur, "203.0.113.77")
    playbook_store.create_playbook_definition(
        conn,
        "pb_approval_store",
        "Approval store playbook",
        steps=[{"action": "require_approval"}, {"action": "monitor"}],
    )
    return playbook_store.create_playbook_execution(conn, "pb_approval_store", alert_id)


def _count_rows(cur, table):
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    return cur.fetchone()[0]


@pytest.fixture
def audit_mock():
    with patch("core.approval_store.log_audit_event") as mocked:
        yield mocked


def test_schema_tables_exist(postgres_db):
    _conn, cur = postgres_db
    cur.execute(
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = current_schema()
          AND table_name IN ('approval_requests', 'approval_request_events')
        ORDER BY table_name
        """
    )
    assert [row[0] for row in cur.fetchall()] == [
        "approval_request_events",
        "approval_requests",
    ]


def test_schema_has_playbook_approval_link_columns(postgres_db):
    _conn, cur = postgres_db
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'approval_requests'
          AND column_name IN ('playbook_execution_id', 'playbook_step_index')
        ORDER BY column_name
        """
    )
    assert [row[0] for row in cur.fetchall()] == [
        "playbook_execution_id",
        "playbook_step_index",
    ]


def test_schema_invalid_status_rejected(postgres_db):
    conn, cur = postgres_db
    incident_id = _insert_incident(cur)
    with pytest.raises(IntegrityError):
        cur.execute(
            """
            INSERT INTO approval_requests (incident_id, status, action, expires_at)
            VALUES (%s, 'unknown', 'block_ip', NOW() + INTERVAL '1 hour')
            """,
            (incident_id,),
        )
    conn.rollback()


def test_schema_invalid_risk_level_rejected(postgres_db):
    conn, cur = postgres_db
    incident_id = _insert_incident(cur)
    with pytest.raises(IntegrityError):
        cur.execute(
            """
            INSERT INTO approval_requests (incident_id, action, risk_level, expires_at)
            VALUES (%s, 'block_ip', 'low', NOW() + INTERVAL '1 hour')
            """,
            (incident_id,),
        )
    conn.rollback()


def test_schema_requires_incident_or_queue_target(postgres_db):
    conn, cur = postgres_db
    with pytest.raises(IntegrityError):
        cur.execute(
            """
            INSERT INTO approval_requests (action, expires_at)
            VALUES ('block_ip', NOW() + INTERVAL '1 hour')
            """
        )
    conn.rollback()


def test_schema_allows_playbook_execution_target(postgres_db, audit_mock):
    conn, cur = postgres_db
    execution_id = _insert_playbook_execution(conn, cur)

    req = create_approval_request(
        conn,
        playbook_execution_id=execution_id,
        playbook_step_index=0,
        action="playbook.require_approval",
    )

    assert req["playbook_execution_id"] == execution_id
    assert req["playbook_step_index"] == 0
    assert req["incident_id"] is None
    assert req["queue_id"] is None


def test_schema_approved_requires_approved_by(postgres_db):
    conn, cur = postgres_db
    incident_id = _insert_incident(cur)
    with pytest.raises(IntegrityError):
        cur.execute(
            """
            INSERT INTO approval_requests (
                incident_id, status, action, decided_at, expires_at
            )
            VALUES (%s, 'approved', 'block_ip', NOW(), NOW() + INTERVAL '1 hour')
            """,
            (incident_id,),
        )
    conn.rollback()


def test_schema_pending_cannot_have_decided_at(postgres_db):
    conn, cur = postgres_db
    incident_id = _insert_incident(cur)
    with pytest.raises(IntegrityError):
        cur.execute(
            """
            INSERT INTO approval_requests (
                incident_id, status, action, decided_at, expires_at
            )
            VALUES (%s, 'pending', 'block_ip', NOW(), NOW() + INTERVAL '1 hour')
            """,
            (incident_id,),
        )
    conn.rollback()


def test_schema_unknown_event_type_rejected(postgres_db, audit_mock):
    conn, cur = postgres_db
    incident_id = _insert_incident(cur)
    req = create_approval_request(conn, incident_id=incident_id, action="block_ip")
    with pytest.raises(IntegrityError):
        cur.execute(
            """
            INSERT INTO approval_request_events (
                approval_request_id, event_type, new_status
            )
            VALUES (%s, 'unknown', 'pending')
            """,
            (req["id"],),
        )
    conn.rollback()


def test_create_approval_request_tied_to_incident(postgres_db, audit_mock):
    conn, cur = postgres_db
    incident_id = _insert_incident(cur)
    user_id = _insert_user(cur)
    conn.commit()

    req = create_approval_request(
        conn,
        incident_id=incident_id,
        action="block_ip",
        requested_by=user_id,
        request_reason="high risk block",
    )
    conn.commit()

    assert req["incident_id"] == incident_id
    assert req["queue_id"] is None
    assert req["status"] == "pending"
    assert req["action"] == "block_ip"
    assert req["risk_level"] == "high"
    assert req["requested_by"] == user_id
    assert req["expires_at"]

    cur.execute(
        "SELECT event_type, new_status FROM approval_request_events WHERE approval_request_id = %s",
        (req["id"],),
    )
    assert cur.fetchall() == [("created", "pending")]
    audit_mock.assert_called_with(
        "approval_request_created",
        actor_username=str(user_id),
        details={
            "approval_request_id": req["id"],
            "incident_id": incident_id,
            "queue_id": None,
            "action": "block_ip",
            "previous_status": None,
            "new_status": "pending",
            "decision_comment": "high risk block",
        },
    )


def test_create_approval_request_tied_to_queue_item(postgres_db, audit_mock):
    conn, cur = postgres_db
    queue_id = _insert_queue_item(cur)
    conn.commit()

    req = create_approval_request(conn, queue_id=queue_id, action="block_ip")
    conn.commit()

    assert req["queue_id"] == queue_id
    assert req["incident_id"] is None


def test_create_approval_request_can_include_incident_and_queue(postgres_db, audit_mock):
    conn, cur = postgres_db
    incident_id = _insert_incident(cur)
    queue_id = _insert_queue_item(cur)
    conn.commit()

    req = create_approval_request(
        conn,
        incident_id=incident_id,
        queue_id=queue_id,
        action="block_ip",
        risk_level="critical",
    )
    conn.commit()

    assert req["incident_id"] == incident_id
    assert req["queue_id"] == queue_id
    assert req["risk_level"] == "critical"


def test_create_playbook_step_approval_request_is_linked_and_reused(postgres_db, audit_mock):
    conn, cur = postgres_db
    execution_id = _insert_playbook_execution(conn, cur)

    first = create_playbook_step_approval_request(
        conn,
        playbook_execution_id=execution_id,
        playbook_step_index=1,
        request_reason="Approve simulated block",
        risk_level="critical",
        ttl_minutes=15,
    )
    second = create_playbook_step_approval_request(
        conn,
        playbook_execution_id=execution_id,
        playbook_step_index=1,
        request_reason="Approve simulated block",
        risk_level="critical",
        ttl_minutes=15,
    )

    assert second["id"] == first["id"]
    assert first["playbook_execution_id"] == execution_id
    assert first["playbook_step_index"] == 1
    assert first["action"] == "playbook.require_approval"
    assert first["risk_level"] == "critical"
    assert first["request_reason"] == "Approve simulated block"

    active = get_active_playbook_step_approval_request(
        conn,
        playbook_execution_id=execution_id,
        playbook_step_index=1,
    )
    assert active["id"] == first["id"]

    cur.execute(
        """
        SELECT COUNT(*)
        FROM approval_requests
        WHERE playbook_execution_id = %s AND playbook_step_index = 1
        """,
        (execution_id,),
    )
    assert cur.fetchone()[0] == 1


def test_create_approval_request_computes_expires_at_from_ttl(postgres_db, audit_mock):
    conn, cur = postgres_db
    incident_id = _insert_incident(cur)
    before = datetime.now(timezone.utc)

    req = create_approval_request(
        conn,
        incident_id=incident_id,
        action="block_ip",
        ttl_minutes=30,
    )
    conn.commit()

    expires_at = datetime.fromisoformat(req["expires_at"])
    after = before + timedelta(minutes=31)
    assert before + timedelta(minutes=29) <= expires_at <= after


def test_create_approval_request_rejects_missing_target(postgres_db, audit_mock):
    conn, _cur = postgres_db
    with pytest.raises(ValueError, match="target required"):
        create_approval_request(conn, action="block_ip")


def test_create_approval_request_rejects_empty_action(postgres_db, audit_mock):
    conn, cur = postgres_db
    incident_id = _insert_incident(cur)
    with pytest.raises(ValueError, match="action is required"):
        create_approval_request(conn, incident_id=incident_id, action="  ")


def test_get_approval_request_returns_detail_with_events(postgres_db, audit_mock):
    conn, cur = postgres_db
    incident_id = _insert_incident(cur)
    req = create_approval_request(conn, incident_id=incident_id, action="block_ip")
    conn.commit()

    detail = get_approval_request(conn, req["id"])

    assert detail["id"] == req["id"]
    assert detail["events"][0]["event_type"] == "created"
    assert detail["events"][0]["new_status"] == "pending"


def test_get_approval_request_unknown_returns_none(postgres_db):
    conn, _cur = postgres_db
    assert get_approval_request(conn, 999999) is None


def test_list_approval_events_returns_events_ordered_by_created_at(postgres_db, audit_mock):
    conn, cur = postgres_db
    incident_id = _insert_incident(cur)
    user_id = _insert_user(cur)
    req = create_approval_request(conn, incident_id=incident_id, action="block_ip")
    conn.commit()

    deny_request(conn, req["id"], actor_user_id=user_id, decision_comment="too risky")
    conn.commit()

    events = list_approval_events(conn, req["id"])

    assert len(events) == 2
    assert events[0]["event_type"] == "created"
    assert events[1]["event_type"] == "denied"


def test_list_approval_events_returns_all_event_columns(postgres_db, audit_mock):
    conn, cur = postgres_db
    incident_id = _insert_incident(cur)
    req = create_approval_request(conn, incident_id=incident_id, action="block_ip")
    conn.commit()

    events = list_approval_events(conn, req["id"])

    assert len(events) == 1
    assert set(events[0].keys()) == {
        "id",
        "approval_request_id",
        "event_type",
        "actor_user_id",
        "previous_status",
        "new_status",
        "comment",
        "created_at",
    }


def test_list_approval_events_filters_by_approval_request_id(postgres_db, audit_mock):
    conn, cur = postgres_db
    incident_id = _insert_incident(cur)
    req_one = create_approval_request(conn, incident_id=incident_id, action="block_ip")
    req_two = create_approval_request(conn, incident_id=incident_id, action="monitor")
    conn.commit()

    events = list_approval_events(conn, req_one["id"])

    assert len(events) == 1
    assert all(event["approval_request_id"] == req_one["id"] for event in events)
    assert all(event["approval_request_id"] != req_two["id"] for event in events)


def test_list_approval_events_returns_empty_list_for_unknown_approval_id(postgres_db):
    conn, _cur = postgres_db
    assert list_approval_events(conn, 999999) == []


def test_list_approval_requests_filters_and_caps_limit(postgres_db, audit_mock):
    conn, cur = postgres_db
    incident_one = _insert_incident(cur, "203.0.113.20")
    incident_two = _insert_incident(cur, "203.0.113.21")
    queue_id = _insert_queue_item(cur, "203.0.113.22")
    conn.commit()

    first = create_approval_request(conn, incident_id=incident_one, action="block_ip")
    second = create_approval_request(conn, incident_id=incident_two, action="block_ip")
    third = create_approval_request(conn, queue_id=queue_id, action="monitor")
    conn.commit()
    approve_request(conn, second["id"], actor_user_id=_insert_user(cur, "approver"))
    conn.commit()

    pending = list_approval_requests(conn, status="pending")
    assert {item["id"] for item in pending} == {first["id"], third["id"]}

    by_incident = list_approval_requests(conn, incident_id=incident_one)
    assert [item["id"] for item in by_incident] == [first["id"]]

    by_queue = list_approval_requests(conn, queue_id=queue_id)
    assert [item["id"] for item in by_queue] == [third["id"]]

    assert len(list_approval_requests(conn, limit=200)) == 3


def test_approve_request_transitions_pending_and_writes_event(postgres_db, audit_mock):
    conn, cur = postgres_db
    incident_id = _insert_incident(cur)
    user_id = _insert_user(cur)
    req = create_approval_request(conn, incident_id=incident_id, action="block_ip")
    conn.commit()

    approved = approve_request(
        conn,
        req["id"],
        actor_user_id=user_id,
        decision_comment="approved for containment",
    )
    conn.commit()

    assert approved["status"] == "approved"
    assert approved["approved_by"] == user_id
    assert approved["decided_by"] == user_id
    assert approved["decided_at"] is not None
    assert approved["decision_comment"] == "approved for containment"

    detail = get_approval_request(conn, req["id"])
    assert [event["event_type"] for event in detail["events"]] == ["created", "approved"]
    audit_mock.assert_any_call(
        "approval_request_approved",
        actor_username=str(user_id),
        details={
            "approval_request_id": req["id"],
            "incident_id": incident_id,
            "queue_id": None,
            "action": "block_ip",
            "previous_status": "pending",
            "new_status": "approved",
            "decision_comment": "approved for containment",
        },
    )


def test_deny_request_transitions_pending_and_writes_event(postgres_db, audit_mock):
    conn, cur = postgres_db
    incident_id = _insert_incident(cur)
    user_id = _insert_user(cur)
    req = create_approval_request(conn, incident_id=incident_id, action="block_ip")
    conn.commit()

    denied = deny_request(
        conn,
        req["id"],
        actor_user_id=user_id,
        decision_comment="deny risky block",
    )
    conn.commit()

    assert denied["status"] == "denied"
    assert denied["approved_by"] is None
    assert denied["decided_by"] == user_id
    assert denied["decided_at"] is not None
    assert denied["decision_comment"] == "deny risky block"
    detail = get_approval_request(conn, req["id"])
    assert [event["event_type"] for event in detail["events"]] == ["created", "denied"]
    audit_mock.assert_any_call(
        "approval_request_denied",
        actor_username=str(user_id),
        details={
            "approval_request_id": req["id"],
            "incident_id": incident_id,
            "queue_id": None,
            "action": "block_ip",
            "previous_status": "pending",
            "new_status": "denied",
            "decision_comment": "deny risky block",
        },
    )


def test_invalid_terminal_state_transitions_rejected(postgres_db, audit_mock):
    conn, cur = postgres_db
    incident_id = _insert_incident(cur)
    user_id = _insert_user(cur)
    approved = create_approval_request(conn, incident_id=incident_id, action="block_ip")
    denied = create_approval_request(conn, incident_id=incident_id, action="block_ip")
    expired = create_approval_request(
        conn,
        incident_id=incident_id,
        action="block_ip",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    conn.commit()
    approve_request(conn, approved["id"], actor_user_id=user_id)
    deny_request(conn, denied["id"], actor_user_id=user_id)
    expire_pending_requests(conn)
    conn.commit()

    for req in (approved, denied, expired):
        with pytest.raises(ValueError, match="not pending"):
            approve_request(conn, req["id"], actor_user_id=user_id)
        with pytest.raises(ValueError, match="not pending"):
            deny_request(conn, req["id"], actor_user_id=user_id)


def test_approve_expired_pending_materializes_expiration_and_raises(postgres_db, audit_mock):
    conn, cur = postgres_db
    incident_id = _insert_incident(cur)
    user_id = _insert_user(cur)
    req = create_approval_request(
        conn,
        incident_id=incident_id,
        action="block_ip",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    conn.commit()

    with pytest.raises(ValueError, match="expired"):
        approve_request(conn, req["id"], actor_user_id=user_id)
    conn.commit()

    detail = get_approval_request(conn, req["id"])
    assert detail["status"] == "expired"
    assert [event["event_type"] for event in detail["events"]] == ["created", "expired"]


def test_deny_expired_pending_materializes_expiration_and_raises(postgres_db, audit_mock):
    conn, cur = postgres_db
    incident_id = _insert_incident(cur)
    user_id = _insert_user(cur)
    req = create_approval_request(
        conn,
        incident_id=incident_id,
        action="block_ip",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    conn.commit()

    with pytest.raises(ValueError, match="expired"):
        deny_request(conn, req["id"], actor_user_id=user_id)
    conn.commit()

    detail = get_approval_request(conn, req["id"])
    assert detail["status"] == "expired"
    assert [event["event_type"] for event in detail["events"]] == ["created", "expired"]


def test_expire_pending_requests_only_expires_eligible_pending(postgres_db, audit_mock):
    conn, cur = postgres_db
    incident_id = _insert_incident(cur)
    user_id = _insert_user(cur)
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    old_pending = create_approval_request(
        conn, incident_id=incident_id, action="block_ip", expires_at=past
    )
    future_pending = create_approval_request(
        conn, incident_id=incident_id, action="block_ip", expires_at=future
    )
    approved = create_approval_request(
        conn, incident_id=incident_id, action="block_ip", expires_at=future
    )
    denied = create_approval_request(
        conn, incident_id=incident_id, action="block_ip", expires_at=future
    )
    conn.commit()
    approve_request(conn, approved["id"], actor_user_id=user_id)
    deny_request(conn, denied["id"], actor_user_id=user_id)
    conn.commit()

    expired = expire_pending_requests(conn, now=datetime.now(timezone.utc))
    conn.commit()

    assert [item["id"] for item in expired] == [old_pending["id"]]
    statuses = {
        item["id"]: item["status"]
        for item in list_approval_requests(conn, limit=100)
    }
    assert statuses[old_pending["id"]] == "expired"
    assert statuses[future_pending["id"]] == "pending"
    assert statuses[approved["id"]] == "approved"
    assert statuses[denied["id"]] == "denied"

    detail = get_approval_request(conn, old_pending["id"])
    assert [event["event_type"] for event in detail["events"]] == ["created", "expired"]


def test_store_helpers_do_not_commit_caller_rollback_removes_writes(postgres_db, audit_mock):
    conn, cur = postgres_db
    incident_id = _insert_incident(cur)
    conn.commit()

    create_approval_request(conn, incident_id=incident_id, action="block_ip")
    assert _count_rows(cur, "approval_requests") == 1
    assert _count_rows(cur, "approval_request_events") == 1

    conn.rollback()
    assert _count_rows(cur, "approval_requests") == 0
    assert _count_rows(cur, "approval_request_events") == 0
