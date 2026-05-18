import pytest

from core import dead_letter_store
from engines import playbook_step_executor


def _insert_user(cur, username="dead_letter_user"):
    cur.execute(
        """
        INSERT INTO users (username, password_hash, role)
        VALUES (%s, 'x', 'analyst')
        RETURNING id
        """,
        (username,),
    )
    return cur.fetchone()[0]


def _insert_alert(cur):
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message)
        VALUES ('dead_letter_test', 'HIGH', '10.1.1.1'::inet, 'dead letter alert')
        RETURNING id
        """
    )
    return cur.fetchone()[0]


def _insert_incident(cur):
    cur.execute(
        """
        INSERT INTO incidents (title, severity)
        VALUES ('dead letter incident', 'HIGH')
        RETURNING id
        """
    )
    return cur.fetchone()[0]


def _insert_playbook_execution(cur, alert_id=None, incident_id=None, playbook_id="pb_dead_letter"):
    cur.execute(
        """
        INSERT INTO playbook_definitions (id, name, trigger_config, steps)
        VALUES (%s, 'Dead letter test', '{}'::jsonb, '[]'::jsonb)
        ON CONFLICT (id) DO NOTHING
        """,
        (playbook_id,),
    )
    cur.execute(
        """
        INSERT INTO playbook_executions (playbook_id, alert_id, incident_id, status, steps_log)
        VALUES (%s, %s, %s, 'failed', '[]'::jsonb)
        RETURNING id
        """,
        (playbook_id, alert_id, incident_id),
    )
    return cur.fetchone()[0], playbook_id


@pytest.mark.parametrize(
    "failure_class",
    [
        "adapter_timeout",
        "transient_network_error",
        "circuit_breaker_open",
        "circuit_open",
        "provider_rate_limited",
        "rate_limited",
        "adapter_simulation_failed",
        "temporary_provider_failure",
        "timeout",
        "transient",
    ],
)
def test_dead_letter_retryable_classifier_retryable_matrix(failure_class):
    assert dead_letter_store.classify_dead_letter_retryable(
        failure_class,
        source_type="playbook_execution",
        status="open",
    ) is True


@pytest.mark.parametrize(
    "failure_class",
    [
        "invalid_credentials",
        "credential_invalid",
        "credential_missing",
        "malformed_payload",
        "approval_expired",
        "approval_denied",
        "unsupported_action",
        "permanent_provider_rejection",
        "non_transient",
        "simulation_only",
        "guard_failed",
        "unknown",
    ],
)
def test_dead_letter_retryable_classifier_non_retryable_matrix(failure_class):
    assert dead_letter_store.classify_dead_letter_retryable(
        failure_class,
        source_type="playbook_execution",
        status="open",
    ) is False


def test_dead_letter_retryable_classifier_unknown_and_terminal_fail_closed():
    assert dead_letter_store.classify_dead_letter_retryable(
        "new_provider_error",
        source_type="playbook_execution",
        status="open",
    ) is False
    assert dead_letter_store.classify_dead_letter_retryable(
        "timeout",
        source_type="approval",
        status="open",
    ) is False
    assert dead_letter_store.classify_dead_letter_retryable(
        "timeout",
        source_type="playbook_execution",
        status="dismissed",
    ) is False


@pytest.mark.usefixtures("postgres_db")
def test_create_list_get_dead_letter_round_trip_and_redacts_payload(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    incident_id = _insert_incident(cur)
    execution_id, playbook_id = _insert_playbook_execution(
        cur, alert_id=alert_id, incident_id=incident_id
    )
    conn.commit()

    row = dead_letter_store.create_dead_letter(
        conn,
        source_type="playbook_execution",
        source_id=execution_id,
        execution_id=execution_id,
        incident_id=incident_id,
        alert_id=alert_id,
        playbook_id=playbook_id,
        step_index=1,
        action_name="notify_slack",
        failure_class="adapter_failed",
        retryable=True,
        error_message="failed at https://hooks.slack.com/services/secret",
        payload_json={
            "safe": "kept",
            "authorization": "Bearer secret",
            "nested": {"callback_url": "https://example.test/callback"},
        },
    )
    conn.commit()

    assert row["id"] >= 1
    assert row["status"] == "open"
    assert row["source_type"] == "playbook_execution"
    assert row["source_id"] == execution_id
    assert row["execution_id"] == execution_id
    assert row["incident_id"] == incident_id
    assert row["alert_id"] == alert_id
    assert row["playbook_id"] == playbook_id
    assert row["step_index"] == 1
    assert row["action_name"] == "notify_slack"
    assert row["failure_class"] == "adapter_failed"
    assert row["retryable"] is True
    assert "[REDACTED_URL]" in row["error_message"]
    assert row["payload_json"] == {"safe": "kept", "nested": {}}

    loaded = dead_letter_store.get_dead_letter(conn, row["id"])
    assert loaded == row

    listed = dead_letter_store.list_dead_letters(
        conn,
        status="open",
        source_type="playbook_execution",
        retryable=True,
        execution_id=execution_id,
    )
    assert [item["id"] for item in listed] == [row["id"]]


@pytest.mark.usefixtures("postgres_db")
def test_dismiss_flow_requires_reason_and_sets_terminal_fields(postgres_db):
    conn, cur = postgres_db
    user_id = _insert_user(cur, "dead_letter_dismiss")
    row = dead_letter_store.create_dead_letter(
        conn,
        source_type="response_action",
        source_id=42,
        failure_class="permanent",
        error_message="operator reviewed",
    )
    conn.commit()

    with pytest.raises(ValueError, match="reason is required"):
        dead_letter_store.mark_dead_letter_dismissed(
            conn, row["id"], dismissed_by=user_id, reason="   "
        )

    dismissed = dead_letter_store.mark_dead_letter_dismissed(
        conn,
        row["id"],
        dismissed_by=user_id,
        reason="known invalid target https://example.test/secret",
    )
    conn.commit()

    assert dismissed["status"] == "dismissed"
    assert dismissed["dismissed_by"] == user_id
    assert dismissed["dismissed_at"] is not None
    assert dismissed["dismiss_reason"] == "known invalid target [REDACTED_URL]"

    assert dead_letter_store.mark_dead_letter_dismissed(
        conn, row["id"], dismissed_by=user_id, reason="again"
    ) is None


@pytest.mark.usefixtures("postgres_db")
def test_retry_request_flow_increments_count_once_for_open_row(postgres_db):
    conn, cur = postgres_db
    user_id = _insert_user(cur, "dead_letter_retry")
    row = dead_letter_store.create_dead_letter(
        conn,
        source_type="notification_delivery",
        source_id=99,
        failure_class="timeout",
        error_message="provider timed out",
    )
    conn.commit()

    retrying = dead_letter_store.mark_dead_letter_retry_requested(
        conn, row["id"], requested_by=user_id
    )
    conn.commit()

    assert retrying["status"] == "retrying"
    assert retrying["retry_count"] == 1
    assert retrying["retry_requested_by"] == user_id
    assert retrying["retry_requested_at"] is not None

    assert dead_letter_store.mark_dead_letter_retry_requested(
        conn, row["id"], requested_by=user_id
    ) is None


@pytest.mark.usefixtures("postgres_db")
def test_mark_dead_letter_retried_transitions_retrying_only(postgres_db):
    conn, cur = postgres_db
    user_id = _insert_user(cur, "dead_letter_retried")
    row = dead_letter_store.create_dead_letter(
        conn,
        source_type="playbook_execution",
        source_id=199,
        failure_class="adapter_failed",
        error_message="failed",
    )
    retrying = dead_letter_store.mark_dead_letter_retry_requested(
        conn, row["id"], requested_by=user_id
    )
    conn.commit()

    retried = dead_letter_store.mark_dead_letter_retried(conn, row["id"])
    conn.commit()

    assert retrying["status"] == "retrying"
    assert retried["status"] == "retried"
    assert retried["retry_count"] == 1
    assert retried["retry_requested_by"] == user_id
    assert retried["retry_requested_at"] is not None


@pytest.mark.usefixtures("postgres_db")
def test_mark_dead_letter_retried_rejects_open_dismissed_retried_and_missing(postgres_db):
    conn, cur = postgres_db
    user_id = _insert_user(cur, "dead_letter_retried_reject")
    open_row = dead_letter_store.create_dead_letter(
        conn,
        source_type="playbook_execution",
        source_id=200,
        failure_class="adapter_failed",
        error_message="failed",
    )
    dismissed_row = dead_letter_store.create_dead_letter(
        conn,
        source_type="response_action",
        source_id=201,
        failure_class="permanent",
        error_message="dismiss me",
    )
    retry_row = dead_letter_store.create_dead_letter(
        conn,
        source_type="notification_delivery",
        source_id=202,
        failure_class="timeout",
        error_message="retry me",
    )
    dead_letter_store.mark_dead_letter_dismissed(
        conn, dismissed_row["id"], dismissed_by=user_id, reason="handled"
    )
    dead_letter_store.mark_dead_letter_retry_requested(
        conn, retry_row["id"], requested_by=user_id
    )
    dead_letter_store.mark_dead_letter_retried(conn, retry_row["id"])
    conn.commit()

    assert dead_letter_store.mark_dead_letter_retried(conn, open_row["id"]) is None
    assert dead_letter_store.mark_dead_letter_retried(conn, dismissed_row["id"]) is None
    assert dead_letter_store.mark_dead_letter_retried(conn, retry_row["id"]) is None
    assert dead_letter_store.mark_dead_letter_retried(conn, 999999) is None

    assert dead_letter_store.get_dead_letter(conn, open_row["id"])["status"] == "open"
    assert (
        dead_letter_store.get_dead_letter(conn, dismissed_row["id"])["status"]
        == "dismissed"
    )
    assert dead_letter_store.get_dead_letter(conn, retry_row["id"])["status"] == "retried"


@pytest.mark.usefixtures("postgres_db")
def test_metrics_aggregate_status_source_and_failure_class(postgres_db):
    conn, cur = postgres_db
    user_id = _insert_user(cur, "dead_letter_metrics")
    open_row = dead_letter_store.create_dead_letter(
        conn,
        source_type="playbook_execution",
        source_id=1,
        failure_class="adapter_failed",
        error_message="failed",
    )
    retry_row = dead_letter_store.create_dead_letter(
        conn,
        source_type="notification_delivery",
        source_id=2,
        failure_class="timeout",
        error_message="timeout",
    )
    dismiss_row = dead_letter_store.create_dead_letter(
        conn,
        source_type="approval",
        source_id=3,
        failure_class="approval_expired",
        error_message="expired",
    )
    dead_letter_store.mark_dead_letter_retry_requested(conn, retry_row["id"], requested_by=user_id)
    dead_letter_store.mark_dead_letter_dismissed(
        conn, dismiss_row["id"], dismissed_by=user_id, reason="handled elsewhere"
    )
    conn.commit()

    metrics = dead_letter_store.get_dead_letter_metrics(conn)

    assert metrics["total"] == 3
    assert metrics["open"] == 1
    assert metrics["retrying"] == 1
    assert metrics["dismissed"] == 1
    assert metrics["retried"] == 0
    assert metrics["active"] == 2
    assert metrics["oldest_active_at"] is not None
    assert metrics["by_status"]["open"] == 1
    assert metrics["by_source_type"]["playbook_execution"] == 1
    assert metrics["by_source_type"]["notification_delivery"] == 1
    assert metrics["by_failure_class"]["adapter_failed"] == 1
    assert metrics["by_failure_class"]["timeout"] == 1
    assert dead_letter_store.get_dead_letter(conn, open_row["id"])["status"] == "open"


@pytest.mark.usefixtures("postgres_db")
def test_duplicate_active_source_updates_existing_row_and_terminal_allows_new_one(postgres_db):
    conn, cur = postgres_db
    user_id = _insert_user(cur, "dead_letter_duplicate")
    first = dead_letter_store.create_dead_letter(
        conn,
        source_type="response_action",
        source_id=123,
        failure_class="transient",
        error_message="first failure",
        payload_json={"attempt": 1},
    )
    second = dead_letter_store.create_dead_letter(
        conn,
        source_type="response_action",
        source_id=123,
        failure_class="permanent",
        error_message="second failure",
        payload_json={"attempt": 2},
    )
    conn.commit()

    assert second["id"] == first["id"]
    assert second["failure_class"] == "permanent"
    assert second["error_message"] == "second failure"
    assert second["payload_json"] == {"attempt": 2}
    assert len(dead_letter_store.list_dead_letters(conn)) == 1

    dead_letter_store.mark_dead_letter_dismissed(
        conn, first["id"], dismissed_by=user_id, reason="reviewed"
    )
    third = dead_letter_store.create_dead_letter(
        conn,
        source_type="response_action",
        source_id=123,
        failure_class="transient",
        error_message="new active failure",
    )
    conn.commit()

    assert third["id"] != first["id"]
    assert len(dead_letter_store.list_dead_letters(conn, source_type="response_action")) == 2


@pytest.mark.usefixtures("postgres_db")
def test_repeated_playbook_failure_capture_keeps_single_active_dead_letter(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    execution_id, playbook_id = _insert_playbook_execution(cur, alert_id=alert_id)
    steps_log = [
        {
            "step_index": 0,
            "action": "notify_slack",
            "status": "failed",
            "message": "first transient failure",
            "error": {"message": "first transient failure"},
            "output": {"adapter_result": {"metadata": {"failure_classification": "timeout"}}},
        }
    ]
    conn.commit()

    execution = {
        "id": execution_id,
        "status": "failed",
        "failure_reason": "failed",
        "alert_id": alert_id,
        "incident_id": None,
        "playbook_id": playbook_id,
    }
    playbook_step_executor.capture_failed_execution_dead_letter(
        conn,
        execution,
        steps_log,
        last_completed_step=None,
        now=None,
    )
    steps_log[0]["message"] = "second transient failure"
    steps_log[0]["error"]["message"] = "second transient failure"
    playbook_step_executor.capture_failed_execution_dead_letter(
        conn,
        execution,
        steps_log,
        last_completed_step=None,
        now=None,
    )
    conn.commit()

    rows = dead_letter_store.list_dead_letters(
        conn,
        source_type="playbook_execution",
        execution_id=execution_id,
    )
    assert len(rows) == 1
    assert rows[0]["status"] == "open"
    assert rows[0]["source_id"] == execution_id
    assert rows[0]["failure_class"] == "timeout"
    assert rows[0]["retryable"] is True
    assert rows[0]["error_message"] == "second transient failure"


@pytest.mark.usefixtures("postgres_db")
def test_playbook_failure_capture_unknown_class_defaults_not_retryable(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    execution_id, playbook_id = _insert_playbook_execution(cur, alert_id=alert_id)
    steps_log = [
        {
            "step_index": 0,
            "action": "custom_step",
            "status": "failed",
            "message": "unknown failure",
            "error": {"message": "unknown failure"},
            "output": {"adapter_result": {"metadata": {"failure_classification": "new_error"}}},
        }
    ]
    conn.commit()

    playbook_step_executor.capture_failed_execution_dead_letter(
        conn,
        {
            "id": execution_id,
            "status": "failed",
            "failure_reason": "failed",
            "alert_id": alert_id,
            "incident_id": None,
            "playbook_id": playbook_id,
        },
        steps_log,
        last_completed_step=None,
        now=None,
    )
    conn.commit()

    rows = dead_letter_store.list_dead_letters(
        conn,
        source_type="playbook_execution",
        execution_id=execution_id,
    )
    assert len(rows) == 1
    assert rows[0]["failure_class"] == "new_error"
    assert rows[0]["retryable"] is False


def test_store_validation_rejects_invalid_enums_and_inputs():
    with pytest.raises(ValueError, match="source_type must be one of"):
        dead_letter_store._validate_source_type("bad_source")
    with pytest.raises(ValueError, match="status must be one of"):
        dead_letter_store._validate_status("bad_status")
    with pytest.raises(ValueError, match="source_id must be an integer"):
        dead_letter_store._validate_source_id("not-int")
    with pytest.raises(ValueError, match="step_index must be >= 0"):
        dead_letter_store._validate_optional_nonnegative(-1, "step_index")
    with pytest.raises(ValueError, match="retryable must be a boolean"):
        dead_letter_store._validate_bool("false", "retryable")
