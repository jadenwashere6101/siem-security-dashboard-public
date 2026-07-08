import inspect
from datetime import datetime, timezone

import pytest

from core import notification_delivery_store


def _insert_alert(cur, source_ip="10.0.0.1"):
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message)
        VALUES ('test_alert', 'LOW', %s::inet, 'msg')
        RETURNING id
        """,
        (source_ip,),
    )
    return cur.fetchone()[0]


def _insert_user(cur, username):
    cur.execute(
        """
        INSERT INTO users (username, password_hash, role)
        VALUES (%s, 'x', 'analyst')
        RETURNING id
        """,
        (username,),
    )
    return cur.fetchone()[0]


def _insert_incident(cur, title="t", severity="HIGH"):
    cur.execute(
        """
        INSERT INTO incidents (title, severity)
        VALUES (%s, %s)
        RETURNING id
        """,
        (title, severity),
    )
    return cur.fetchone()[0]


def _insert_playbook_and_execution(cur, playbook_id="pb_ndt", alert_id=None, incident_id=None):
    cur.execute(
        """
        INSERT INTO playbook_definitions (id, name, trigger_config, steps)
        VALUES (%s, 'n', '{}'::jsonb, '[]'::jsonb)
        ON CONFLICT (id) DO NOTHING
        """,
        (playbook_id,),
    )
    cur.execute(
        """
        INSERT INTO playbook_executions (
            playbook_id, alert_id, incident_id, status, steps_log
        )
        VALUES (%s, %s, %s, 'pending', '[]'::jsonb)
        RETURNING id
        """,
        (playbook_id, alert_id, incident_id),
    )
    return cur.fetchone()[0]


@pytest.mark.usefixtures("postgres_db")
def test_create_get_round_trip(postgres_db):
    conn, _cur = postgres_db
    row = notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="corr-1",
        idempotency_key="idem-1",
        provider="slack",
        mode="simulation",
        status="success",
        adapter_name="slack",
        action="send_message",
        metadata={"channel_label": "#soc", "webhook_configured": True},
    )
    conn.commit()
    assert row["id"] >= 1
    assert row["correlation_id"] == "corr-1"
    assert row["idempotency_key"] == "idem-1"
    assert row["provider"] == "slack"
    assert row["mode"] == "simulation"
    assert row["status"] == "success"
    assert row["playbook_execution_id"] is None
    assert row["metadata"]["channel_label"] == "#soc"
    assert row["metadata"]["webhook_configured"] is True

    loaded = notification_delivery_store.get_notification_delivery_attempt(conn, row["id"])
    assert loaded == row


@pytest.mark.usefixtures("postgres_db")
def test_get_unknown_returns_none(postgres_db):
    conn, _cur = postgres_db
    assert notification_delivery_store.get_notification_delivery_attempt(conn, 999999) is None


@pytest.mark.usefixtures("postgres_db")
def test_list_filters_and_order(postgres_db):
    conn, _cur = postgres_db
    notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="c-a",
        idempotency_key="i-a",
        provider="slack",
        mode="simulation",
        status="success",
        adapter_name="slack",
        action="send_message",
    )
    notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="c-b",
        idempotency_key="i-b",
        provider="teams",
        mode="simulation",
        status="failed",
        adapter_name="teams",
        action="send_message",
    )
    conn.commit()

    all_rows = notification_delivery_store.list_notification_delivery_attempts(conn, limit=10)
    assert [r["correlation_id"] for r in all_rows] == ["c-b", "c-a"]

    slack_only = notification_delivery_store.list_notification_delivery_attempts(
        conn, provider="slack"
    )
    assert len(slack_only) == 1
    assert slack_only[0]["provider"] == "slack"

    failed = notification_delivery_store.list_notification_delivery_attempts(conn, status="failed")
    assert len(failed) == 1
    assert failed[0]["correlation_id"] == "c-b"


@pytest.mark.usefixtures("postgres_db")
def test_list_filter_by_idempotency_and_correlation(postgres_db):
    conn, _cur = postgres_db
    notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="cx",
        idempotency_key="same-logical",
        provider="slack",
        mode="simulation",
        status="blocked",
        adapter_name="slack",
        action="send_message",
        circuit_breaker_state="open",
    )
    notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="cy",
        idempotency_key="same-logical",
        provider="slack",
        mode="simulation",
        status="success",
        adapter_name="slack",
        action="send_message",
    )
    conn.commit()

    by_idem = notification_delivery_store.list_notification_delivery_attempts(
        conn, idempotency_key="same-logical"
    )
    assert len(by_idem) == 2

    by_corr = notification_delivery_store.list_notification_delivery_attempts(
        conn, correlation_id="cy"
    )
    assert len(by_corr) == 1
    assert by_corr[0]["status"] == "success"


@pytest.mark.usefixtures("postgres_db")
def test_linkage_fields_optional_and_populated(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    incident_id = _insert_incident(cur)
    exec_id = _insert_playbook_and_execution(cur, alert_id=alert_id, incident_id=incident_id)
    user_id = _insert_user(cur, "approver_ndt_1")
    cur.execute(
        """
        INSERT INTO approval_requests (
            incident_id, playbook_execution_id, playbook_step_index,
            requested_by, status, action, risk_level, expires_at
        )
        VALUES (%s, %s, 0, %s, 'pending', 'notify_slack', 'high', NOW() + interval '1 hour')
        RETURNING id
        """,
        (incident_id, exec_id, user_id),
    )
    approval_id = cur.fetchone()[0]
    conn.commit()

    row = notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="corr-link",
        idempotency_key="idem-link",
        provider="teams",
        mode="real",
        status="pending",
        adapter_name="teams",
        action="send_message",
        playbook_execution_id=exec_id,
        playbook_step_index=2,
        incident_id=incident_id,
        approval_request_id=approval_id,
        alert_id=alert_id,
        timeout_seconds=30,
        circuit_breaker_state="closed",
    )
    conn.commit()

    assert row["playbook_execution_id"] == exec_id
    assert row["playbook_step_index"] == 2
    assert row["incident_id"] == incident_id
    assert row["approval_request_id"] == approval_id
    assert row["alert_id"] == alert_id
    assert row["timeout_seconds"] == 30

    listed = notification_delivery_store.list_notification_delivery_attempts(
        conn, playbook_execution_id=exec_id
    )
    assert len(listed) == 1
    assert listed[0]["approval_request_id"] == approval_id

    by_inc = notification_delivery_store.list_notification_delivery_attempts(
        conn, incident_id=incident_id
    )
    assert len(by_inc) == 1

    by_appr = notification_delivery_store.list_notification_delivery_attempts(
        conn, approval_request_id=approval_id
    )
    assert len(by_appr) == 1

    by_alert = notification_delivery_store.list_notification_delivery_attempts(conn, alert_id=alert_id)
    assert len(by_alert) == 1


@pytest.mark.usefixtures("postgres_db")
def test_metadata_redaction_removes_secrets_and_urls(postgres_db):
    conn, _cur = postgres_db
    row = notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="cr",
        idempotency_key="id",
        provider="slack",
        mode="simulation",
        status="success",
        adapter_name="slack",
        action="send_message",
        metadata={
            "safe": True,
            "slack_webhook_url": "https://hooks.slack.com/secret",
            "nested": {"authorization": "bearer x", "ok": 1},
            "message_preview": "See https://evil.example/path",
        },
    )
    conn.commit()
    meta = row["metadata"]
    assert meta["safe"] is True
    assert "slack_webhook_url" not in meta
    assert "authorization" not in meta.get("nested", {})
    assert meta["nested"]["ok"] == 1
    assert "[REDACTED_URL]" in meta["message_preview"]


@pytest.mark.usefixtures("postgres_db")
def test_failure_message_sanitizes_urls(postgres_db):
    conn, _cur = postgres_db
    row = notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="cf",
        idempotency_key="if",
        provider="teams",
        mode="simulation",
        status="failed",
        adapter_name="teams",
        action="send_message",
        failure_code="network_error",
        failure_message="timeout calling https://hooks.example.com/trick",
    )
    conn.commit()
    assert row["failure_code"] == "network_error"
    assert "hooks.example.com" not in (row["failure_message"] or "")
    assert "[REDACTED_URL]" in (row["failure_message"] or "")


@pytest.mark.usefixtures("postgres_db")
def test_requested_at_explicit(postgres_db):
    conn, _cur = postgres_db
    when = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    row = notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="ct",
        idempotency_key="it",
        provider="slack",
        mode="simulation",
        status="timeout",
        adapter_name="slack",
        action="send_message",
        requested_at=when,
        started_at=when,
        completed_at=when,
    )
    conn.commit()
    assert datetime.fromisoformat(row["requested_at"]) == when
    assert datetime.fromisoformat(row["started_at"]) == when
    assert datetime.fromisoformat(row["completed_at"]) == when


@pytest.mark.usefixtures("postgres_db")
def test_immutability_no_update_helpers_in_store(postgres_db):
    names = {name for name, _ in inspect.getmembers(notification_delivery_store, inspect.isfunction)}
    assert not any(n.startswith("update_") for n in names)
    assert "create_notification_delivery_attempt" in names
    assert "get_notification_delivery_attempt" in names
    assert "list_notification_delivery_attempts" in names


@pytest.mark.usefixtures("postgres_db")
def test_validation_errors(postgres_db):
    conn, _cur = postgres_db
    with pytest.raises(ValueError, match="correlation_id"):
        notification_delivery_store.create_notification_delivery_attempt(
            conn,
            correlation_id="  ",
            idempotency_key="k",
            provider="slack",
            mode="simulation",
            status="success",
            adapter_name="slack",
            action="send_message",
        )
    with pytest.raises(ValueError, match="mode"):
        notification_delivery_store.create_notification_delivery_attempt(
            conn,
            correlation_id="c",
            idempotency_key="k",
            provider="slack",
            mode="invalid",
            status="success",
            adapter_name="slack",
            action="send_message",
        )
    with pytest.raises(ValueError, match="circuit_breaker_state"):
        notification_delivery_store.create_notification_delivery_attempt(
            conn,
            correlation_id="c",
            idempotency_key="k2",
            provider="slack",
            mode="simulation",
            status="blocked",
            adapter_name="slack",
            action="send_message",
            circuit_breaker_state="bogus",
        )


@pytest.mark.usefixtures("postgres_db")
def test_list_invalid_filter_raises(postgres_db):
    conn, _cur = postgres_db
    with pytest.raises(ValueError, match="mode"):
        notification_delivery_store.list_notification_delivery_attempts(conn, mode="nope")


@pytest.mark.usefixtures("postgres_db")
def test_list_filter_by_adapter_name(postgres_db):
    conn, _cur = postgres_db
    notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="ca",
        idempotency_key="ia",
        provider="slack",
        mode="simulation",
        status="success",
        adapter_name="slack",
        action="send_message",
    )
    notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="cb",
        idempotency_key="ib",
        provider="teams",
        mode="simulation",
        status="success",
        adapter_name="teams",
        action="send_message",
    )
    conn.commit()
    rows = notification_delivery_store.list_notification_delivery_attempts(
        conn, adapter_name="teams"
    )
    assert len(rows) == 1
    assert rows[0]["adapter_name"] == "teams"


@pytest.mark.usefixtures("postgres_db")
def test_list_filter_by_action_is_additive(postgres_db):
    conn, _cur = postgres_db
    notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="action-a",
        idempotency_key="action-ia",
        provider="slack",
        mode="simulation",
        status="success",
        adapter_name="slack",
        action="send_message",
    )
    notification_delivery_store.create_notification_delivery_attempt(
        conn,
        correlation_id="action-b",
        idempotency_key="action-ib",
        provider="slack",
        mode="simulation",
        status="success",
        adapter_name="slack",
        action="test_notification",
    )
    conn.commit()

    all_rows = notification_delivery_store.list_notification_delivery_attempts(conn, provider="slack")
    test_rows = notification_delivery_store.list_notification_delivery_attempts(
        conn, provider="slack", action="test_notification"
    )

    assert len(all_rows) == 2
    assert len(test_rows) == 1
    assert test_rows[0]["action"] == "test_notification"


def test_redact_metadata_rejects_non_dict():
    with pytest.raises(TypeError):
        notification_delivery_store.redact_notification_delivery_metadata("bad")  # type: ignore[arg-type]
