from pathlib import Path
from unittest.mock import MagicMock

from scripts import migrate


REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATION_PATH = REPO_ROOT / "migrations" / "0012_soar_response_outcomes.sql"


def test_soar_response_outcomes_migration_scope():
    sql = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS soar_response_decisions" in sql
    assert "CREATE TABLE IF NOT EXISTS soar_response_outcome_events" in sql

    decision_columns = [
        "soar_correlation_id VARCHAR(128) NOT NULL",
        "selected_action TEXT NOT NULL",
        "decision_source VARCHAR(64) NOT NULL",
        "outcome_summary TEXT NOT NULL",
        "created_by INTEGER REFERENCES users(id) ON DELETE SET NULL",
    ]
    event_columns = [
        "decision_id INTEGER NOT NULL REFERENCES soar_response_decisions(id) ON DELETE CASCADE",
        "execution_mode VARCHAR(32) NOT NULL",
        "execution_state VARCHAR(32) NOT NULL",
        "external_executed BOOLEAN NOT NULL DEFAULT FALSE",
        "tracking_recorded BOOLEAN NOT NULL DEFAULT FALSE",
        "simulated BOOLEAN NOT NULL DEFAULT FALSE",
        "execution_actor VARCHAR(64) NOT NULL",
        "response_action_log_id INTEGER REFERENCES response_actions_log(id) ON DELETE SET NULL",
        "metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
    ]
    for column in decision_columns:
        assert column in sql
    for column in event_columns:
        assert column in sql

    linkage_tables = [
        "response_actions_queue",
        "response_actions_log",
        "playbook_executions",
        "approval_requests",
        "notification_delivery_attempts",
    ]
    for table in linkage_tables:
        assert f"ALTER TABLE {table}" in sql
        assert f"ADD COLUMN IF NOT EXISTS decision_id INTEGER" in sql
        assert f"ADD COLUMN IF NOT EXISTS soar_correlation_id VARCHAR(128)" in sql

    assert "'detection_default'" in sql
    assert "'tracking_only'" in sql
    assert "'awaiting_approval'" in sql
    assert "'approval_service'" in sql
    assert "idx_soar_response_outcome_events_decision_latest" in sql
    assert "idx_soar_response_outcome_events_idempotency_key" in sql

    assert "DROP" not in sql.upper()
    assert "TRUNCATE" not in sql.upper()
    assert "DELETE FROM" not in sql.upper()


def test_migration_0012_is_pending_when_db_at_0011(capsys):
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchone.return_value = ("schema_migrations",)
    cur.fetchall.return_value = [(version,) for version in range(1, 12)]

    code = migrate.run(conn, migrations_dir=REPO_ROOT / "migrations", dry_run=True)

    assert code == 0
    output = capsys.readouterr().out
    assert "Would apply migration 0012 0012_soar_response_outcomes" in output
    assert "Would apply migration 0013 0013_playbook_chaining" in output
    assert "Dry run complete. 2 pending migration(s)." in output


def test_migration_0013_is_pending_when_db_at_0012(capsys):
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchall.return_value = [(version,) for version in range(1, 13)]

    code = migrate.run(conn, migrations_dir=REPO_ROOT / "migrations", dry_run=True)

    assert code == 0
    output = capsys.readouterr().out
    assert "Would apply migration 0013 0013_playbook_chaining" in output
    assert "Dry run complete. 1 pending migration(s)." in output


def test_migration_0013_is_noop_when_already_applied(capsys):
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchall.return_value = [(version,) for version in range(1, 14)]

    code = migrate.run(conn, migrations_dir=REPO_ROOT / "migrations", dry_run=True)

    assert code == 0
    assert "Nothing to apply. DB at version 0013." in capsys.readouterr().out
