"""
Phase 5A/5B focused tests: playbook_executions linkage columns and execution-level
canonical decision creation.

Covers:
- Migration: columns exist at the DB level
- playbook_store round-trip: create/read new fields + set_playbook_execution_canonical_linkage
- Orchestrator: creates execution-level playbook decision per execution, appends pending event
- Backward compat: canonical failures do not abort execution creation
- Duplicate suppression: second orchestrator call creates no second decision
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from core import playbook_store
from core.soar_response_outcomes import append_outcome_event, create_response_decision
from engines.soar_playbook_orchestrator import (
    create_pending_executions_for_committed_alerts,
)


_VALID_STEPS = [{"action": "monitor", "params": {}}]


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


def _insert_decision(conn, cur, alert_id, soar_cid="soar-test-0001"):
    cur.execute(
        """
        INSERT INTO soar_response_decisions (
            soar_correlation_id, alert_id, selected_action, decision_source, outcome_summary
        )
        VALUES (%s, %s, 'monitor', 'detection_default', 'test decision')
        RETURNING id
        """,
        (soar_cid, alert_id),
    )
    decision_id = cur.fetchone()[0]
    conn.commit()
    return decision_id


def _create_definition(conn, playbook_id="pb_test"):
    playbook_store.create_playbook_definition(
        conn,
        playbook_id,
        "Test Playbook",
        steps=_VALID_STEPS,
        trigger_config={"alert_type": "test_alert"},
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Migration: columns exist
# ---------------------------------------------------------------------------

def test_migration_0012_includes_playbook_executions_linkage_columns():
    """Phase 5A: 0012 migration already adds decision_id and soar_correlation_id to playbook_executions."""
    migration_path = (
        Path(__file__).resolve().parent.parent / "migrations" / "0012_soar_response_outcomes.sql"
    )
    sql = migration_path.read_text(encoding="utf-8")

    assert "ALTER TABLE playbook_executions" in sql
    assert "ADD COLUMN IF NOT EXISTS decision_id INTEGER REFERENCES soar_response_decisions(id)" in sql
    assert "ADD COLUMN IF NOT EXISTS soar_correlation_id VARCHAR(128)" in sql
    assert "idx_playbook_executions_decision_id" in sql
    assert "idx_playbook_executions_soar_correlation_id" in sql


@pytest.mark.usefixtures("postgres_db")
def test_playbook_executions_linkage_columns_exist_in_db(postgres_db):
    """Phase 5A: DB confirms both linkage columns are live after migration."""
    conn, cur = postgres_db
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'playbook_executions'
          AND column_name IN ('decision_id', 'soar_correlation_id')
        ORDER BY column_name
        """
    )
    cols = {row[0] for row in cur.fetchall()}
    assert "decision_id" in cols
    assert "soar_correlation_id" in cols


# ---------------------------------------------------------------------------
# playbook_store round-trip: create_playbook_execution
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("postgres_db")
def test_create_playbook_execution_without_linkage_returns_null_fields(postgres_db):
    """Backward compatibility: create without linkage → decision_id and soar_correlation_id are NULL."""
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    _create_definition(conn)

    eid = playbook_store.create_playbook_execution(conn, "pb_test", alert_id)
    conn.commit()

    row = playbook_store.get_playbook_execution(conn, eid)
    assert row is not None
    assert row["decision_id"] is None
    assert row["soar_correlation_id"] is None


@pytest.mark.usefixtures("postgres_db")
def test_create_playbook_execution_with_linkage_persists_fields(postgres_db):
    """Phase 5A: create with linkage → decision_id and soar_correlation_id are stored and returned."""
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    decision_id = _insert_decision(conn, cur, alert_id, "soar-abc-0001")
    _create_definition(conn)

    eid = playbook_store.create_playbook_execution(
        conn,
        "pb_test",
        alert_id,
        decision_id=decision_id,
        soar_correlation_id="soar-abc-0001",
    )
    conn.commit()

    row = playbook_store.get_playbook_execution(conn, eid)
    assert row is not None
    assert row["decision_id"] == decision_id
    assert row["soar_correlation_id"] == "soar-abc-0001"


# ---------------------------------------------------------------------------
# playbook_store round-trip: create_pending_playbook_execution_once
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("postgres_db")
def test_create_pending_once_without_linkage_returns_null_fields(postgres_db):
    """Backward compatibility: create_pending_once without linkage → NULL fields."""
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    _create_definition(conn)

    eid = playbook_store.create_pending_playbook_execution_once(conn, "pb_test", alert_id)
    conn.commit()

    assert eid is not None
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row is not None
    assert row["decision_id"] is None
    assert row["soar_correlation_id"] is None


@pytest.mark.usefixtures("postgres_db")
def test_create_pending_once_with_linkage_persists_fields(postgres_db):
    """Phase 5A: create_pending_once with linkage → both fields stored and returned."""
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    decision_id = _insert_decision(conn, cur, alert_id, "soar-xyz-0002")
    _create_definition(conn)

    eid = playbook_store.create_pending_playbook_execution_once(
        conn,
        "pb_test",
        alert_id,
        decision_id=decision_id,
        soar_correlation_id="soar-xyz-0002",
    )
    conn.commit()

    assert eid is not None
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row is not None
    assert row["decision_id"] == decision_id
    assert row["soar_correlation_id"] == "soar-xyz-0002"


@pytest.mark.usefixtures("postgres_db")
def test_create_pending_once_duplicate_suppression_still_returns_none(postgres_db):
    """Backward compatibility: duplicate suppression path is unaffected by new params."""
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    decision_id = _insert_decision(conn, cur, alert_id, "soar-dup-0003")
    _create_definition(conn)

    first = playbook_store.create_pending_playbook_execution_once(
        conn, "pb_test", alert_id, decision_id=decision_id, soar_correlation_id="soar-dup-0003"
    )
    conn.commit()
    assert first is not None

    second = playbook_store.create_pending_playbook_execution_once(
        conn, "pb_test", alert_id, decision_id=decision_id, soar_correlation_id="soar-dup-0003"
    )
    conn.commit()
    assert second is None


# ---------------------------------------------------------------------------
# Full RETURNING round-trip: verify all store helpers expose new fields
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("postgres_db")
def test_execution_columns_sql_includes_linkage_fields_in_all_returning_paths(postgres_db):
    """Phase 5A: every function using _EXECUTION_COLUMNS_SQL returns decision_id and soar_correlation_id."""
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    decision_id = _insert_decision(conn, cur, alert_id, "soar-ret-0004")
    _create_definition(conn)

    eid = playbook_store.create_pending_playbook_execution_once(
        conn, "pb_test", alert_id, decision_id=decision_id, soar_correlation_id="soar-ret-0004"
    )
    conn.commit()

    # list_pending_playbook_executions uses _EXECUTION_COLUMNS_SQL
    pending = playbook_store.list_pending_playbook_executions(conn)
    match = next((r for r in pending if r["id"] == eid), None)
    assert match is not None
    assert match["decision_id"] == decision_id
    assert match["soar_correlation_id"] == "soar-ret-0004"

    # claim_next_pending_playbook_execution uses _EXECUTION_COLUMNS_SQL
    claimed = playbook_store.claim_next_pending_playbook_execution(conn)
    assert claimed is not None
    assert claimed["decision_id"] == decision_id
    assert claimed["soar_correlation_id"] == "soar-ret-0004"

    # set_playbook_execution_success uses _EXECUTION_COLUMNS_SQL
    finished = playbook_store.set_playbook_execution_success(conn, eid, [], 0)
    assert finished is not None
    assert finished["decision_id"] == decision_id
    assert finished["soar_correlation_id"] == "soar-ret-0004"


# ---------------------------------------------------------------------------
# Orchestrator: correlation propagation
# ---------------------------------------------------------------------------

def test_orchestrator_creates_playbook_decision_with_parent_linkage(postgres_db):
    """
    Phase 5B: when get_latest_outcome_for_alert returns an existing decision,
    the orchestrator creates a NEW playbook-source decision whose
    parent_soar_correlation_id equals the alert's existing soar_correlation_id.
    """
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    _insert_decision(conn, cur, alert_id, "soar-orch-0005")
    _create_definition(conn)
    conn.commit()

    fake_outcome = {"decision_id": 999, "soar_correlation_id": "soar-orch-0005"}

    with patch(
        "engines.soar_playbook_orchestrator.get_latest_outcome_for_alert",
        return_value=fake_outcome,
    ), patch(
        "engines.soar_playbook_orchestrator.match_playbooks",
        return_value=[{"id": "pb_test"}],
    ):
        result = create_pending_executions_for_committed_alerts(
            [{"alert_id": alert_id}], conn
        )

    conn.commit()
    assert result["summary"]["created"] == 1
    eid = result["results"][0]["execution_id"]
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row is not None
    # A new playbook-source decision was created and linked
    assert row["decision_id"] is not None
    assert row["soar_correlation_id"] is not None
    assert row["soar_correlation_id"] != "soar-orch-0005"  # new decision, not the parent
    # Verify the new decision has decision_source=playbook and the parent linked
    cur.execute(
        "SELECT decision_source, parent_soar_correlation_id "
        "FROM soar_response_decisions WHERE id = %s",
        (row["decision_id"],),
    )
    dec = cur.fetchone()
    assert dec is not None
    assert dec[0] == "playbook"
    assert dec[1] == "soar-orch-0005"


def test_orchestrator_creates_playbook_decision_without_parent_when_no_alert_decision(postgres_db):
    """
    Phase 5B: when no parent alert decision exists, the orchestrator still creates
    a playbook-source decision for the execution (with parent_soar_correlation_id=NULL).
    """
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    _create_definition(conn)
    conn.commit()

    with patch(
        "engines.soar_playbook_orchestrator.get_latest_outcome_for_alert",
        return_value=None,
    ), patch(
        "engines.soar_playbook_orchestrator.match_playbooks",
        return_value=[{"id": "pb_test"}],
    ):
        result = create_pending_executions_for_committed_alerts(
            [{"alert_id": alert_id}], conn
        )

    conn.commit()
    assert result["summary"]["created"] == 1
    eid = result["results"][0]["execution_id"]
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row is not None
    assert row["decision_id"] is not None
    assert row["soar_correlation_id"] is not None
    cur.execute(
        "SELECT decision_source, parent_soar_correlation_id FROM soar_response_decisions WHERE id = %s",
        (row["decision_id"],),
    )
    dec = cur.fetchone()
    assert dec[0] == "playbook"
    assert dec[1] is None  # no parent


def test_orchestrator_creates_execution_when_parent_lookup_raises(postgres_db):
    """
    Resilience: if get_latest_outcome_for_alert raises, execution and playbook decision
    are still created (without a parent_soar_correlation_id).
    """
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    _create_definition(conn)
    conn.commit()

    with patch(
        "engines.soar_playbook_orchestrator.get_latest_outcome_for_alert",
        side_effect=RuntimeError("db hiccup"),
    ), patch(
        "engines.soar_playbook_orchestrator.match_playbooks",
        return_value=[{"id": "pb_test"}],
    ):
        result = create_pending_executions_for_committed_alerts(
            [{"alert_id": alert_id}], conn
        )

    conn.commit()
    assert result["summary"]["created"] == 1
    eid = result["results"][0]["execution_id"]
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row is not None
    assert row["decision_id"] is not None
    assert row["soar_correlation_id"] is not None


# ---------------------------------------------------------------------------
# Phase 5B: set_playbook_execution_canonical_linkage store helper
# ---------------------------------------------------------------------------

def test_set_playbook_execution_canonical_linkage_round_trip(postgres_db):
    """Phase 5B: set_playbook_execution_canonical_linkage writes both fields and returns them."""
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    decision_id = _insert_decision(conn, cur, alert_id, "soar-link-9001")
    _create_definition(conn)

    eid = playbook_store.create_playbook_execution(conn, "pb_test", alert_id)
    conn.commit()

    updated = playbook_store.set_playbook_execution_canonical_linkage(
        conn, eid, decision_id, "soar-link-9001"
    )
    conn.commit()

    assert updated is not None
    assert updated["id"] == eid
    assert updated["decision_id"] == decision_id
    assert updated["soar_correlation_id"] == "soar-link-9001"

    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["decision_id"] == decision_id
    assert row["soar_correlation_id"] == "soar-link-9001"


def test_set_playbook_execution_canonical_linkage_missing_execution_returns_none(postgres_db):
    """Phase 5B: returns None for unknown execution_id."""
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    decision_id = _insert_decision(conn, cur, alert_id, "soar-link-9002")
    conn.commit()

    result = playbook_store.set_playbook_execution_canonical_linkage(
        conn, 999999, decision_id, "soar-link-9002"
    )
    assert result is None


# ---------------------------------------------------------------------------
# Phase 5B: orchestrator appends pending event + canonical failure safety
# ---------------------------------------------------------------------------

def test_orchestrator_appends_pending_event_on_execution_creation(postgres_db):
    """Phase 5B: after creating an execution, orchestrator writes a 'pending' outcome event."""
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    _create_definition(conn)
    conn.commit()

    with patch(
        "engines.soar_playbook_orchestrator.get_latest_outcome_for_alert",
        return_value=None,
    ), patch(
        "engines.soar_playbook_orchestrator.match_playbooks",
        return_value=[{"id": "pb_test"}],
    ):
        result = create_pending_executions_for_committed_alerts(
            [{"alert_id": alert_id}], conn
        )

    conn.commit()
    assert result["summary"]["created"] == 1
    eid = result["results"][0]["execution_id"]
    row = playbook_store.get_playbook_execution(conn, eid)

    cur.execute(
        """
        SELECT event_type, execution_state, execution_actor, execution_mode, simulated
        FROM soar_response_outcome_events
        WHERE decision_id = %s
        ORDER BY id
        """,
        (row["decision_id"],),
    )
    events = cur.fetchall()
    assert len(events) == 1
    assert events[0][0] == "pending"
    assert events[0][1] == "selected"
    assert events[0][2] == "system"
    assert events[0][3] == "simulation"
    assert events[0][4] is True


def test_orchestrator_canonical_failure_does_not_abort_execution(postgres_db):
    """
    Phase 5B: if create_response_decision raises, the execution row is still created
    and the outer transaction is intact.
    """
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    _create_definition(conn)
    conn.commit()

    with patch(
        "engines.soar_playbook_orchestrator.get_latest_outcome_for_alert",
        return_value=None,
    ), patch(
        "engines.soar_playbook_orchestrator.match_playbooks",
        return_value=[{"id": "pb_test"}],
    ), patch(
        "engines.soar_playbook_orchestrator.create_response_decision",
        side_effect=RuntimeError("decision table unavailable"),
    ):
        result = create_pending_executions_for_committed_alerts(
            [{"alert_id": alert_id}], conn
        )

    conn.commit()
    assert result["summary"]["created"] == 1
    eid = result["results"][0]["execution_id"]
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row is not None
    assert row["decision_id"] is None
    assert row["soar_correlation_id"] is None


def test_orchestrator_duplicate_does_not_create_second_decision(postgres_db):
    """
    Phase 5B: the second orchestrator call (duplicate suppressed) creates no new
    soar_response_decisions row.
    """
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    _create_definition(conn)
    conn.commit()

    with patch(
        "engines.soar_playbook_orchestrator.get_latest_outcome_for_alert",
        return_value=None,
    ), patch(
        "engines.soar_playbook_orchestrator.match_playbooks",
        return_value=[{"id": "pb_test"}],
    ):
        first = create_pending_executions_for_committed_alerts(
            [{"alert_id": alert_id}], conn
        )
        conn.commit()
        second = create_pending_executions_for_committed_alerts(
            [{"alert_id": alert_id}], conn
        )
        conn.commit()

    assert first["summary"]["created"] == 1
    assert second["summary"]["duplicates"] == 1

    cur.execute("SELECT COUNT(*) FROM soar_response_decisions WHERE decision_source = 'playbook'")
    assert cur.fetchone()[0] == 1
