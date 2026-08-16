from pathlib import Path
from unittest.mock import MagicMock

from scripts import migrate


REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATION_PATH = REPO_ROOT / "migrations" / "0012_soar_response_outcomes.sql"
EVENTS_SOURCE_INDEX_MIGRATION_PATH = REPO_ROOT / "migrations" / "0014_events_source_index.sql"
INVESTIGATION_CENTERED_WORKSPACE_MIGRATION_PATH = REPO_ROOT / "migrations" / "0029_investigation_centered_workspace.sql"


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


def test_events_source_index_migration_scope():
    sql = EVENTS_SOURCE_INDEX_MIGRATION_PATH.read_text(encoding="utf-8")

    assert "CREATE INDEX IF NOT EXISTS idx_events_source ON events(source);" in sql
    assert "DROP" not in sql.upper()
    assert "TRUNCATE" not in sql.upper()
    assert "DELETE FROM" not in sql.upper()


def test_investigation_centered_workspace_migration_scope():
    sql = INVESTIGATION_CENTERED_WORKSPACE_MIGRATION_PATH.read_text(encoding="utf-8")

    assert "ALTER TABLE investigations" in sql
    assert "ADD COLUMN IF NOT EXISTS disposition TEXT" in sql
    assert "ADD COLUMN IF NOT EXISTS confidence TEXT" in sql
    assert "ADD COLUMN IF NOT EXISTS conclusion TEXT" in sql
    assert "ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMPTZ" in sql
    assert "ALTER TABLE evidence_references" in sql
    assert "ADD COLUMN IF NOT EXISTS rationale TEXT" in sql
    assert "ADD COLUMN IF NOT EXISTS relationship_type TEXT" in sql
    assert "CREATE TABLE IF NOT EXISTS investigation_hypothesis_evidence" in sql
    assert "UNIQUE (hypothesis_id, evidence_reference_id)" in sql
    assert "ON DELETE CASCADE" in sql

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
    assert "Would apply migration 0014 0014_events_source_index" in output
    assert "Would apply migration 0015 0015_indicator_response_registry" in output
    assert "Would apply migration 0016 0016_pfsense_ingest_config" in output
    assert "Would apply migration 0017 0017_approval_expired_reason_code" in output
    assert "Would apply migration 0018 0018_internal_read_only_execution_modes" in output
    assert "Would apply migration 0019 0019_playbook_worker_daemon_health" in output
    assert "Would apply migration 0020 0020_notification_policy" in output
    assert "Would apply migration 0021 0021_notification_policy_critical_cross_source" in output
    assert "Would apply migration 0027 0027_soc_briefing_delivery_attempts" in output
    assert "Would apply migration 0028 0028_investigation_workflow" in output
    assert "Would apply migration 0029 0029_investigation_centered_workspace" in output
    assert "Would apply migration 0030 0030_manual_soc_briefing_mode" in output
    assert "Would apply migration 0033 0033_anakin_session_memory_foundation" in output
    assert "Would apply migration 0038 0038_nist_analyst_workspace_grounded_explanation" in output
    assert "Dry run complete. 27 pending migration(s)." in output


def test_migration_0013_is_pending_when_db_at_0012(capsys):
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchall.return_value = [(version,) for version in range(1, 13)]

    code = migrate.run(conn, migrations_dir=REPO_ROOT / "migrations", dry_run=True)

    assert code == 0
    output = capsys.readouterr().out
    assert "Would apply migration 0013 0013_playbook_chaining" in output
    assert "Would apply migration 0014 0014_events_source_index" in output
    assert "Would apply migration 0015 0015_indicator_response_registry" in output
    assert "Would apply migration 0016 0016_pfsense_ingest_config" in output
    assert "Would apply migration 0017 0017_approval_expired_reason_code" in output
    assert "Would apply migration 0018 0018_internal_read_only_execution_modes" in output
    assert "Would apply migration 0019 0019_playbook_worker_daemon_health" in output
    assert "Would apply migration 0020 0020_notification_policy" in output
    assert "Would apply migration 0021 0021_notification_policy_critical_cross_source" in output
    assert "Would apply migration 0027 0027_soc_briefing_delivery_attempts" in output
    assert "Would apply migration 0028 0028_investigation_workflow" in output
    assert "Would apply migration 0029 0029_investigation_centered_workspace" in output
    assert "Would apply migration 0030 0030_manual_soc_briefing_mode" in output
    assert "Would apply migration 0033 0033_anakin_session_memory_foundation" in output
    assert "Dry run complete. 26 pending migration(s)." in output


def test_migration_0018_is_noop_when_already_applied(capsys):
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchall.return_value = [(version,) for version in range(1, 19)]

    code = migrate.run(conn, migrations_dir=REPO_ROOT / "migrations", dry_run=True)

    assert code == 0
    output = capsys.readouterr().out
    assert "Would apply migration 0019 0019_playbook_worker_daemon_health" in output
    assert "Would apply migration 0020 0020_notification_policy" in output
    assert "Would apply migration 0021 0021_notification_policy_critical_cross_source" in output
    assert "Would apply migration 0027 0027_soc_briefing_delivery_attempts" in output
    assert "Would apply migration 0028 0028_investigation_workflow" in output
    assert "Would apply migration 0029 0029_investigation_centered_workspace" in output
    assert "Would apply migration 0030 0030_manual_soc_briefing_mode" in output
    assert "Would apply migration 0033 0033_anakin_session_memory_foundation" in output
    assert "Dry run complete. 20 pending migration(s)." in output


def test_migration_0014_is_pending_when_db_at_0013(capsys):
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchall.return_value = [(version,) for version in range(1, 14)]

    code = migrate.run(conn, migrations_dir=REPO_ROOT / "migrations", dry_run=True)

    assert code == 0
    output = capsys.readouterr().out
    assert "Would apply migration 0014 0014_events_source_index" in output
    assert "Would apply migration 0015 0015_indicator_response_registry" in output
    assert "Would apply migration 0016 0016_pfsense_ingest_config" in output
    assert "Would apply migration 0017 0017_approval_expired_reason_code" in output
    assert "Would apply migration 0018 0018_internal_read_only_execution_modes" in output
    assert "Would apply migration 0019 0019_playbook_worker_daemon_health" in output
    assert "Would apply migration 0020 0020_notification_policy" in output
    assert "Would apply migration 0021 0021_notification_policy_critical_cross_source" in output
    assert "Would apply migration 0027 0027_soc_briefing_delivery_attempts" in output
    assert "Would apply migration 0028 0028_investigation_workflow" in output
    assert "Would apply migration 0029 0029_investigation_centered_workspace" in output
    assert "Would apply migration 0030 0030_manual_soc_briefing_mode" in output
    assert "Would apply migration 0033 0033_anakin_session_memory_foundation" in output
    assert "Dry run complete. 25 pending migration(s)." in output


def test_migration_0015_is_pending_when_db_at_0014(capsys):
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchall.return_value = [(version,) for version in range(1, 15)]

    code = migrate.run(conn, migrations_dir=REPO_ROOT / "migrations", dry_run=True)

    assert code == 0
    output = capsys.readouterr().out
    assert "Would apply migration 0015 0015_indicator_response_registry" in output
    assert "Would apply migration 0016 0016_pfsense_ingest_config" in output
    assert "Would apply migration 0017 0017_approval_expired_reason_code" in output
    assert "Would apply migration 0018 0018_internal_read_only_execution_modes" in output
    assert "Would apply migration 0019 0019_playbook_worker_daemon_health" in output
    assert "Would apply migration 0020 0020_notification_policy" in output
    assert "Would apply migration 0021 0021_notification_policy_critical_cross_source" in output
    assert "Would apply migration 0027 0027_soc_briefing_delivery_attempts" in output
    assert "Would apply migration 0028 0028_investigation_workflow" in output
    assert "Would apply migration 0029 0029_investigation_centered_workspace" in output
    assert "Would apply migration 0030 0030_manual_soc_briefing_mode" in output
    assert "Would apply migration 0033 0033_anakin_session_memory_foundation" in output
    assert "Dry run complete. 24 pending migration(s)." in output


def test_migration_0016_is_pending_when_db_at_0015(capsys):
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchall.return_value = [(version,) for version in range(1, 16)]

    code = migrate.run(conn, migrations_dir=REPO_ROOT / "migrations", dry_run=True)

    assert code == 0
    output = capsys.readouterr().out
    assert "Would apply migration 0016 0016_pfsense_ingest_config" in output
    assert "Would apply migration 0017 0017_approval_expired_reason_code" in output
    assert "Would apply migration 0018 0018_internal_read_only_execution_modes" in output
    assert "Would apply migration 0019 0019_playbook_worker_daemon_health" in output
    assert "Would apply migration 0020 0020_notification_policy" in output
    assert "Would apply migration 0021 0021_notification_policy_critical_cross_source" in output
    assert "Would apply migration 0027 0027_soc_briefing_delivery_attempts" in output
    assert "Would apply migration 0028 0028_investigation_workflow" in output
    assert "Would apply migration 0029 0029_investigation_centered_workspace" in output
    assert "Would apply migration 0030 0030_manual_soc_briefing_mode" in output
    assert "Would apply migration 0033 0033_anakin_session_memory_foundation" in output
    assert "Dry run complete. 23 pending migration(s)." in output


def test_migration_0018_is_pending_when_db_at_0017(capsys):
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchall.return_value = [(version,) for version in range(1, 18)]

    code = migrate.run(conn, migrations_dir=REPO_ROOT / "migrations", dry_run=True)

    assert code == 0
    output = capsys.readouterr().out
    assert "Would apply migration 0018 0018_internal_read_only_execution_modes" in output
    assert "Would apply migration 0019 0019_playbook_worker_daemon_health" in output
    assert "Would apply migration 0020 0020_notification_policy" in output
    assert "Would apply migration 0021 0021_notification_policy_critical_cross_source" in output
    assert "Would apply migration 0027 0027_soc_briefing_delivery_attempts" in output
    assert "Would apply migration 0028 0028_investigation_workflow" in output
    assert "Would apply migration 0029 0029_investigation_centered_workspace" in output
    assert "Would apply migration 0030 0030_manual_soc_briefing_mode" in output
    assert "Would apply migration 0033 0033_anakin_session_memory_foundation" in output
    assert "Dry run complete. 21 pending migration(s)." in output


def test_migration_0020_and_0021_are_pending_when_db_at_0019(capsys):
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchall.return_value = [(version,) for version in range(1, 20)]

    code = migrate.run(conn, migrations_dir=REPO_ROOT / "migrations", dry_run=True)

    assert code == 0
    output = capsys.readouterr().out
    assert "Would apply migration 0020 0020_notification_policy" in output
    assert "Would apply migration 0021 0021_notification_policy_critical_cross_source" in output
    assert "Would apply migration 0027 0027_soc_briefing_delivery_attempts" in output
    assert "Would apply migration 0028 0028_investigation_workflow" in output
    assert "Would apply migration 0029 0029_investigation_centered_workspace" in output
    assert "Would apply migration 0030 0030_manual_soc_briefing_mode" in output
    assert "Would apply migration 0033 0033_anakin_session_memory_foundation" in output
    assert "Dry run complete. 19 pending migration(s)." in output


def test_migration_0018_execution_mode_sql_targets_membership_check_not_boolean_guards():
    sql = (
        REPO_ROOT / "migrations" / "0018_internal_read_only_execution_modes.sql"
    ).read_text(encoding="utf-8")

    assert "soar_response_outcome_events_execution_mode_check" in sql
    assert "'internal'" in sql
    assert "'read_only'" in sql
    assert "NOT LIKE '%execution_mode <>%'" in sql
    assert "soar_response_outcome_events_internal_mode_booleans_check" in sql
    assert "soar_response_outcome_events_read_only_mode_booleans_check" in sql
    assert "DROP CONSTRAINT" in sql.upper()
    assert "TRUNCATE" not in sql.upper()
    assert "DELETE FROM" not in sql.upper()
    assert "UPDATE " not in sql.upper()
