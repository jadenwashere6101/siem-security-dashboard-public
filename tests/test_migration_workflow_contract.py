from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "migration-validation.yml"


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_active_migration_workflow_uses_database_url_environment_contract():
    text = _workflow_text()

    command_prefix = "python3 scripts/" + "migrate.py --"
    removed_arg = "db" + "-url"
    assert command_prefix + removed_arg not in text
    assert 'DATABASE_URL="$DATABASE_URL" python3 scripts/migrate.py' in text
    assert 'DATABASE_URL="$DATABASE_URL" python3 scripts/migrate.py --dry-run' in text


def test_active_migration_workflow_does_not_print_database_url():
    text = _workflow_text()

    unsafe_fragments = (
        'echo "$DATABASE_URL"',
        "echo '$DATABASE_URL'",
        'printf "%s\\n" "$DATABASE_URL"',
        "printf '%s\\n' \"$DATABASE_URL\"",
    )
    for fragment in unsafe_fragments:
        assert fragment not in text


def test_migrate_cli_missing_database_url_fails_safely(monkeypatch, capsys):
    from scripts import migrate

    monkeypatch.delenv("DATABASE_URL", raising=False)

    code = migrate.main([])

    captured = capsys.readouterr()
    assert code == 1
    assert "DATABASE_URL is required" in captured.err
    assert "postgresql://" not in captured.err
    assert captured.out == ""
