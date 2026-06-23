import uuid

import psycopg2
import pytest


DECISION_COLUMNS = {
    "soar_correlation_id",
    "alert_id",
    "incident_id",
    "source_ip",
    "selected_action",
    "decision_source",
    "reason_code",
    "outcome_summary",
    "playbook_id",
    "playbook_execution_id",
    "queue_id",
    "approval_request_id",
    "created_by",
    "created_at",
}

OUTCOME_EVENT_COLUMNS = {
    "decision_id",
    "soar_correlation_id",
    "alert_id",
    "incident_id",
    "source_ip",
    "execution_mode",
    "execution_state",
    "external_executed",
    "tracking_recorded",
    "simulated",
    "execution_actor",
    "reason_code",
    "outcome_summary",
    "queue_id",
    "playbook_execution_id",
    "playbook_step_index",
    "approval_request_id",
    "notification_delivery_attempt_id",
    "response_action_log_id",
    "metadata",
    "created_at",
}

LINKAGE_TABLES = {
    "response_actions_queue": {"decision_id", "soar_correlation_id"},
    "response_actions_log": {"decision_id", "soar_correlation_id"},
    "playbook_executions": {"decision_id", "soar_correlation_id"},
    "approval_requests": {"decision_id", "soar_correlation_id"},
    "notification_delivery_attempts": {"decision_id", "soar_correlation_id"},
}

EXPECTED_INDEXES = {
    "soar_response_decisions": {
        "idx_soar_response_decisions_soar_correlation_id",
        "idx_soar_response_decisions_alert_id",
        "idx_soar_response_decisions_incident_id",
        "idx_soar_response_decisions_source_ip",
        "idx_soar_response_decisions_created_at",
    },
    "soar_response_outcome_events": {
        "idx_soar_response_outcome_events_decision_id",
        "idx_soar_response_outcome_events_alert_id",
        "idx_soar_response_outcome_events_incident_id",
        "idx_soar_response_outcome_events_source_ip",
        "idx_soar_response_outcome_events_soar_correlation_id",
        "idx_soar_response_outcome_events_created_at",
        "idx_soar_response_outcome_events_decision_latest",
        "idx_soar_response_outcome_events_mode_state_created",
        "idx_soar_response_outcome_events_idempotency_key",
    },
}


def _table_columns(cur, table_name):
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = %s
        """,
        (table_name,),
    )
    return {row[0] for row in cur.fetchall()}


def _table_indexes(cur, table_name):
    cur.execute(
        """
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = current_schema()
          AND tablename = %s
        """,
        (table_name,),
    )
    return {row[0] for row in cur.fetchall()}


def _insert_decision(cur, correlation_suffix=None):
    correlation_id = f"soar-test-{correlation_suffix or uuid.uuid4().hex}"
    cur.execute(
        """
        INSERT INTO soar_response_decisions (
            soar_correlation_id,
            selected_action,
            decision_source,
            outcome_summary
        )
        VALUES (%s, %s, %s, %s)
        RETURNING id, soar_correlation_id
        """,
        (
            correlation_id,
            "monitor",
            "manual",
            "Manual monitor decision for schema test.",
        ),
    )
    return cur.fetchone()


def test_soar_response_outcome_tables_exist(postgres_db):
    _conn, cur = postgres_db

    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = current_schema()
          AND table_name IN ('soar_response_decisions', 'soar_response_outcome_events')
        ORDER BY table_name
        """
    )
    assert [row[0] for row in cur.fetchall()] == [
        "soar_response_decisions",
        "soar_response_outcome_events",
    ]


def test_soar_response_outcome_required_columns_exist(postgres_db):
    _conn, cur = postgres_db

    decision_columns = _table_columns(cur, "soar_response_decisions")
    event_columns = _table_columns(cur, "soar_response_outcome_events")

    assert DECISION_COLUMNS.issubset(decision_columns)
    assert OUTCOME_EVENT_COLUMNS.issubset(event_columns)


def test_soar_response_outcome_linkage_columns_exist(postgres_db):
    _conn, cur = postgres_db

    for table_name, expected_columns in LINKAGE_TABLES.items():
        columns = _table_columns(cur, table_name)
        assert expected_columns.issubset(columns), table_name


def test_soar_response_outcome_indexes_exist(postgres_db):
    _conn, cur = postgres_db

    for table_name, expected_indexes in EXPECTED_INDEXES.items():
        indexes = _table_indexes(cur, table_name)
        assert expected_indexes.issubset(indexes), table_name


@pytest.mark.parametrize(
    "decision_source",
    ["queue_worker", "adapter", "detection", ""],
)
def test_decision_source_check_constraint_rejects_invalid_values(postgres_db, decision_source):
    _conn, cur = postgres_db
    correlation_id = f"soar-invalid-source-{uuid.uuid4().hex}"

    with pytest.raises(psycopg2.Error):
        cur.execute(
            """
            INSERT INTO soar_response_decisions (
                soar_correlation_id,
                selected_action,
                decision_source,
                outcome_summary
            )
            VALUES (%s, %s, %s, %s)
            """,
            (correlation_id, "monitor", decision_source, "invalid decision source test"),
        )
    _conn.rollback()


@pytest.mark.parametrize(
    "execution_mode",
    ["simulated", "real_external", "tracking", "observe"],
)
def test_execution_mode_check_constraint(postgres_db, execution_mode):
    _conn, cur = postgres_db
    decision_id, correlation_id = _insert_decision(cur)
    _conn.commit()

    with pytest.raises(psycopg2.Error):
        cur.execute(
            """
            INSERT INTO soar_response_outcome_events (
                decision_id,
                soar_correlation_id,
                event_type,
                execution_mode,
                execution_state,
                execution_actor,
                outcome_summary
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                decision_id,
                correlation_id,
                "state_changed",
                execution_mode,
                "selected",
                "system",
                "invalid execution mode test",
            ),
        )
    _conn.rollback()


@pytest.mark.parametrize(
    "execution_state",
    ["pending", "approved", "complete", "denied"],
)
def test_execution_state_check_constraint(postgres_db, execution_state):
    _conn, cur = postgres_db
    decision_id, correlation_id = _insert_decision(cur)
    _conn.commit()

    with pytest.raises(psycopg2.Error):
        cur.execute(
            """
            INSERT INTO soar_response_outcome_events (
                decision_id,
                soar_correlation_id,
                event_type,
                execution_mode,
                execution_state,
                execution_actor,
                outcome_summary
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                decision_id,
                correlation_id,
                "state_changed",
                "simulation",
                execution_state,
                "system",
                "invalid execution state test",
            ),
        )
    _conn.rollback()


@pytest.mark.parametrize(
    "execution_actor",
    ["worker", "admin", "detection_engine", "notification_adapter"],
)
def test_execution_actor_check_constraint(postgres_db, execution_actor):
    _conn, cur = postgres_db
    decision_id, correlation_id = _insert_decision(cur)
    _conn.commit()

    with pytest.raises(psycopg2.Error):
        cur.execute(
            """
            INSERT INTO soar_response_outcome_events (
                decision_id,
                soar_correlation_id,
                event_type,
                execution_mode,
                execution_state,
                execution_actor,
                outcome_summary
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                decision_id,
                correlation_id,
                "state_changed",
                "simulation",
                "selected",
                execution_actor,
                "invalid execution actor test",
            ),
        )
    _conn.rollback()


def test_observed_outcome_rejects_execution_booleans(postgres_db):
    _conn, cur = postgres_db
    decision_id, correlation_id = _insert_decision(cur)
    _conn.commit()

    with pytest.raises(psycopg2.Error):
        cur.execute(
            """
            INSERT INTO soar_response_outcome_events (
                decision_id,
                soar_correlation_id,
                event_type,
                execution_mode,
                execution_state,
                external_executed,
                tracking_recorded,
                simulated,
                execution_actor,
                outcome_summary
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                decision_id,
                correlation_id,
                "observed",
                "observed",
                "observed",
                True,
                False,
                False,
                "system",
                "invalid observed booleans",
            ),
        )
    _conn.rollback()


def test_simulation_outcome_rejects_external_executed(postgres_db):
    _conn, cur = postgres_db
    decision_id, correlation_id = _insert_decision(cur)
    _conn.commit()

    with pytest.raises(psycopg2.Error):
        cur.execute(
            """
            INSERT INTO soar_response_outcome_events (
                decision_id,
                soar_correlation_id,
                event_type,
                execution_mode,
                execution_state,
                external_executed,
                tracking_recorded,
                simulated,
                execution_actor,
                outcome_summary
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                decision_id,
                correlation_id,
                "simulated",
                "simulation",
                "succeeded",
                True,
                False,
                True,
                "queue_worker",
                "invalid simulation booleans",
            ),
        )
    _conn.rollback()


def test_tracking_only_success_accepts_tracking_recorded(postgres_db):
    _conn, cur = postgres_db
    decision_id, correlation_id = _insert_decision(cur)

    cur.execute(
        """
        INSERT INTO soar_response_outcome_events (
            decision_id,
            soar_correlation_id,
            event_type,
            execution_mode,
            execution_state,
            external_executed,
            tracking_recorded,
            simulated,
            execution_actor,
            outcome_summary,
            reason_code
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            decision_id,
            correlation_id,
            "tracking_recorded",
            "tracking_only",
            "succeeded",
            False,
            True,
            False,
            "manual",
            "Recorded IP in SIEM blocklist only; no firewall enforcement occurred.",
            "tracking_only",
        ),
    )
    assert cur.fetchone()[0] is not None
    _conn.commit()


def test_real_success_accepts_external_executed(postgres_db):
    _conn, cur = postgres_db
    decision_id, correlation_id = _insert_decision(cur)

    cur.execute(
        """
        INSERT INTO soar_response_outcome_events (
            decision_id,
            soar_correlation_id,
            event_type,
            execution_mode,
            execution_state,
            external_executed,
            tracking_recorded,
            simulated,
            execution_actor,
            outcome_summary
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            decision_id,
            correlation_id,
            "real_executed",
            "real",
            "succeeded",
            True,
            False,
            False,
            "adapter",
            "Provider confirmed delivery.",
        ),
    )
    assert cur.fetchone()[0] is not None
    _conn.commit()


def test_idempotency_key_is_unique_when_present(postgres_db):
    _conn, cur = postgres_db
    decision_id, correlation_id = _insert_decision(cur)
    idempotency_key = f"schema-test-{uuid.uuid4().hex}"

    cur.execute(
        """
        INSERT INTO soar_response_outcome_events (
            decision_id,
            soar_correlation_id,
            event_type,
            execution_mode,
            execution_state,
            execution_actor,
            outcome_summary,
            idempotency_key
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            decision_id,
            correlation_id,
            "selected",
            "simulation",
            "selected",
            "system",
            "first idempotency row",
            idempotency_key,
        ),
    )
    _conn.commit()

    with pytest.raises(psycopg2.Error):
        cur.execute(
            """
            INSERT INTO soar_response_outcome_events (
                decision_id,
                soar_correlation_id,
                event_type,
                execution_mode,
                execution_state,
                execution_actor,
                outcome_summary,
                idempotency_key
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                decision_id,
                correlation_id,
                "selected",
                "simulation",
                "selected",
                "system",
                "duplicate idempotency row",
                idempotency_key,
            ),
        )
    _conn.rollback()
