"""
Phase 5A focused tests: playbook_executions linkage columns (decision_id, soar_correlation_id).

Covers:
- Migration: columns exist at the DB level
- playbook_store round-trip: create/read new fields
- Correlation propagation: orchestrator inherits linkage from alert's canonical decision
- Backward compatibility: callers that omit linkage fields work unchanged
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from core import playbook_store
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

def test_orchestrator_propagates_decision_linkage_when_canonical_decision_exists(postgres_db):
    """
    Phase 5A: when get_latest_outcome_for_alert returns a decision, the orchestrator
    writes decision_id and soar_correlation_id onto the created playbook execution.
    """
    conn, cur = postgres_db
    alert_id = _insert_alert(cur)
    decision_id = _insert_decision(conn, cur, alert_id, "soar-orch-0005")
    _create_definition(conn)
    conn.commit()

    fake_outcome = {"decision_id": decision_id, "soar_correlation_id": "soar-orch-0005"}

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
    assert row["decision_id"] == decision_id
    assert row["soar_correlation_id"] == "soar-orch-0005"


def test_orchestrator_creates_execution_without_linkage_when_no_canonical_decision(postgres_db):
    """
    Backward compatibility: when no canonical decision exists for the alert,
    the orchestrator creates the execution with NULL linkage fields.
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
    assert row["decision_id"] is None
    assert row["soar_correlation_id"] is None


def test_orchestrator_creates_execution_when_linkage_lookup_raises(postgres_db):
    """
    Backward compatibility: a lookup exception must not prevent execution creation;
    the execution is created with NULL linkage fields.
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
    assert row["decision_id"] is None
    assert row["soar_correlation_id"] is None
