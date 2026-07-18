from unittest.mock import MagicMock, patch

from core.core_playbook_pack_v1 import CORE_PLAYBOOK_PACK_V1
from scripts import seed_core_playbook_pack_v1


def _mock_conn():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchone.return_value = (1,)
    conn.get_dsn_parameters.return_value = {
        "dbname": "siem_test",
        "host": "db.example.invalid",
        "port": "5432",
        "pass" + "word": "not-rendered",
    }
    return conn, cur


def test_missing_database_url_exits_nonzero(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    code = seed_core_playbook_pack_v1.main([])

    assert code == 1
    assert "DATABASE_URL is required" in capsys.readouterr().err


def test_database_url_environment_is_used(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql://env/db")
    conn, cur = _mock_conn()

    with patch(
        "scripts.seed_core_playbook_pack_v1.psycopg2.connect",
        return_value=conn,
    ) as connect_mock, patch(
        "scripts.seed_core_playbook_pack_v1.seed_core_playbook_pack_v1",
        return_value=[CORE_PLAYBOOK_PACK_V1[0]["id"]],
    ):
        code = seed_core_playbook_pack_v1.main([])

    assert code == 0
    connect_mock.assert_called_once_with("postgresql://env/db")
    cur.execute.assert_called_once_with("SELECT 1")
    conn.commit.assert_called_once()
    conn.rollback.assert_not_called()
    conn.close.assert_called_once()
    out = capsys.readouterr().out
    assert "Connected database: siem_test@db.example.invalid:5432" in out
    assert CORE_PLAYBOOK_PACK_V1[0]["id"] in out
    assert "not-rendered" not in out


def test_validation_failure_exits_before_connect(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")

    with patch(
        "scripts.seed_core_playbook_pack_v1.validate_core_playbook_pack_v1",
        return_value=["bad step"],
    ), patch("scripts.seed_core_playbook_pack_v1.psycopg2.connect") as connect_mock:
        code = seed_core_playbook_pack_v1.main([])

    assert code == 1
    connect_mock.assert_not_called()
    err = capsys.readouterr().err
    assert "validation failed" in err
    assert "bad step" in err


def test_success_summary_reports_inserted_and_existing(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    conn, _cur = _mock_conn()
    inserted = [item["id"] for item in CORE_PLAYBOOK_PACK_V1[:2]]

    with patch(
        "scripts.seed_core_playbook_pack_v1.psycopg2.connect",
        return_value=conn,
    ), patch(
        "scripts.seed_core_playbook_pack_v1.seed_core_playbook_pack_v1",
        return_value=inserted,
    ):
        code = seed_core_playbook_pack_v1.main([])

    assert code == 0
    out = capsys.readouterr().out
    total = len(CORE_PLAYBOOK_PACK_V1)
    existing = total - 2
    assert "Inserted playbooks (2):" in out
    assert f"Already-existing playbooks ({existing}):" in out
    assert f"Final totals: inserted=2 existing={existing} total={total}" in out
    for playbook_id in inserted:
        assert playbook_id in out


def test_noop_summary_reports_all_existing(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    conn, _cur = _mock_conn()

    with patch(
        "scripts.seed_core_playbook_pack_v1.psycopg2.connect",
        return_value=conn,
    ), patch(
        "scripts.seed_core_playbook_pack_v1.seed_core_playbook_pack_v1",
        return_value=[],
    ):
        code = seed_core_playbook_pack_v1.main([])

    assert code == 0
    out = capsys.readouterr().out
    assert "Inserted playbooks (0): none" in out
    assert f"Already-existing playbooks ({len(CORE_PLAYBOOK_PACK_V1)}):" in out
    assert "No changes made; all Core Playbook Pack v1 playbooks already exist." in out


def test_seed_error_rolls_back_and_closes(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    conn, _cur = _mock_conn()

    with patch(
        "scripts.seed_core_playbook_pack_v1.psycopg2.connect",
        return_value=conn,
    ), patch(
        "scripts.seed_core_playbook_pack_v1.seed_core_playbook_pack_v1",
        side_effect=RuntimeError("insert failed"),
    ):
        code = seed_core_playbook_pack_v1.main([])

    assert code == 2
    assert "insert failed" in capsys.readouterr().err
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()
    conn.close.assert_called_once()


def test_connection_validation_error_rolls_back_and_closes(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    conn, cur = _mock_conn()
    cur.execute.side_effect = RuntimeError("connection invalid")

    with patch(
        "scripts.seed_core_playbook_pack_v1.psycopg2.connect",
        return_value=conn,
    ), patch("scripts.seed_core_playbook_pack_v1.seed_core_playbook_pack_v1") as seed_mock:
        code = seed_core_playbook_pack_v1.main([])

    assert code == 2
    assert "connection invalid" in capsys.readouterr().err
    seed_mock.assert_not_called()
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()
    conn.close.assert_called_once()
