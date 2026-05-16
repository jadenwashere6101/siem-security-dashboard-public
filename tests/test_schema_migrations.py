from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts import migrate


def _write_migration(directory, filename, sql="CREATE TABLE IF NOT EXISTS example (id SERIAL PRIMARY KEY);\n"):
    path = Path(directory) / filename
    path.write_text(sql, encoding="utf-8")
    return path


def test_discover_migrations_sorts_by_numeric_prefix(tmp_path):
    _write_migration(tmp_path, "0002_second.sql")
    _write_migration(tmp_path, "0001_first.sql")

    migrations = migrate.discover_migrations(tmp_path)

    assert [migration.version for migration in migrations] == [1, 2]
    assert [migration.name for migration in migrations] == ["0001_first", "0002_second"]


def test_discover_migrations_rejects_gap(tmp_path):
    _write_migration(tmp_path, "0001_first.sql")
    _write_migration(tmp_path, "0003_third.sql")

    try:
        migrate.discover_migrations(tmp_path)
        assert False, "Expected migration gap to fail"
    except migrate.MigrationError as error:
        assert "Missing migration version(s): 0002" in str(error)


def test_select_pending_migrations_skips_already_applied_and_honors_target(tmp_path):
    _write_migration(tmp_path, "0001_first.sql")
    _write_migration(tmp_path, "0002_second.sql")
    _write_migration(tmp_path, "0003_third.sql")
    migrations = migrate.discover_migrations(tmp_path)

    pending = migrate.select_pending_migrations(migrations, {1}, target=2)

    assert [migration.version for migration in pending] == [2]


def test_dry_run_prints_pending_without_creating_schema_migrations(tmp_path, capsys):
    _write_migration(tmp_path, "0001_first.sql")
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchone.return_value = (None,)
    cur.fetchall.return_value = []

    code = migrate.run(conn, migrations_dir=tmp_path, dry_run=True)

    assert code == 0
    output = capsys.readouterr().out
    assert "Would apply migration 0001 0001_first" in output
    assert "Dry run complete. 1 pending migration(s)." in output
    assert cur.execute.call_args_list[0].args[0] == "SELECT to_regclass('schema_migrations')"
    assert migrate.SCHEMA_MIGRATIONS_SQL not in [
        call.args[0] for call in cur.execute.call_args_list
    ]
    conn.commit.assert_not_called()


def test_already_applied_migration_is_noop(tmp_path, capsys):
    _write_migration(tmp_path, "0001_first.sql")
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchall.return_value = [(1,)]

    code = migrate.run(conn, migrations_dir=tmp_path)

    assert code == 0
    assert "Nothing to apply. DB at version 0001." in capsys.readouterr().out
    cur.execute.assert_any_call(migrate.SCHEMA_MIGRATIONS_SQL)
    cur.execute.assert_any_call("SELECT version FROM schema_migrations ORDER BY version ASC")
    conn.commit.assert_called_once()


def test_apply_records_successful_migration_in_transaction(tmp_path, capsys):
    migration_path = _write_migration(
        tmp_path,
        "0001_first.sql",
        "CREATE TABLE IF NOT EXISTS first_table (id SERIAL PRIMARY KEY);\n",
    )
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchall.return_value = []

    with patch("scripts.migrate.checksum_file", return_value="abc123"), patch(
        "scripts.migrate.applied_by", return_value="tester@host"
    ):
        code = migrate.run(conn, migrations_dir=tmp_path)

    assert code == 0
    output = capsys.readouterr().out
    assert "Applying migration 0001_first.sql ..." in output
    assert "Applied 1 migration(s). DB now at version 0001." in output
    cur.execute.assert_any_call(migration_path.read_text(encoding="utf-8"))
    cur.execute.assert_any_call(
        """
                INSERT INTO schema_migrations (version, name, applied_by, checksum)
                VALUES (%s, %s, %s, %s)
                """,
        (1, "0001_first", "tester@host", "abc123"),
    )
    assert conn.commit.call_count == 2


def test_failed_migration_rolls_back_and_exits_nonzero(tmp_path, capsys):
    _write_migration(tmp_path, "0001_first.sql", "BROKEN SQL;\n")
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchall.return_value = []
    cur.execute.side_effect = [None, [], Exception("syntax error")]

    code = migrate.run(conn, migrations_dir=tmp_path)

    assert code == 1
    assert "Migration 0001 0001_first failed" in capsys.readouterr().err
    conn.rollback.assert_called_once()


def test_main_uses_db_url_argument_and_closes_connection(tmp_path):
    _write_migration(tmp_path, "0001_first.sql")
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchall.return_value = [(1,)]

    with patch("scripts.migrate.psycopg2.connect", return_value=conn) as connect_mock:
        code = migrate.main(
            [
                "--db-url",
                "postgresql://example/db",
                "--migrations-dir",
                str(tmp_path),
            ]
        )

    assert code == 0
    connect_mock.assert_called_once_with("postgresql://example/db")
    conn.close.assert_called_once()


def test_base_siem_core_migration_scope():
    migration_path = Path(__file__).resolve().parent.parent / "migrations" / "0002_base_siem_core.sql"
    sql = migration_path.read_text(encoding="utf-8")

    included_tables = [
        "events",
        "alerts",
        "response_actions_log",
        "response_actions_queue",
    ]
    excluded_tables = [
        "users",
        "audit_log",
        "alert_notes",
        "detection_config",
        "blocked_ips",
        "incidents",
        "approval_requests",
        "playbook_definitions",
        "notification_delivery_attempts",
    ]
    for table in included_tables:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    for table in excluded_tables:
        assert f"CREATE TABLE IF NOT EXISTS {table}" not in sql

    assert "DROP" not in sql.upper()
    assert "DO $$" not in sql
    assert "awaiting_approval" in sql
    assert "idx_response_actions_queue_status" in sql
    assert "idx_response_actions_queue_alert_id" in sql
