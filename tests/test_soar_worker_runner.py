from unittest.mock import MagicMock, patch
import json

import siem_backend
from core.ip_helpers import enqueue_response_action
from engines.soar_executor import AdapterBackedExecutor
from scripts import soar_worker_run


def _set_base_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    monkeypatch.setenv("SOAR_EXECUTION_MODE", "simulation")
    monkeypatch.setenv("SOAR_RUNNER_BATCH_SIZE", "10")


def test_runner_refuses_active_flask_context(monkeypatch):
    _set_base_env(monkeypatch)
    with siem_backend.app.app_context(), patch(
        "scripts.soar_worker_run.process_batch"
    ) as process_batch_mock:
        code = soar_worker_run.main([])
    assert code == 1
    process_batch_mock.assert_not_called()


def test_runner_unknown_mode_exits_1(monkeypatch):
    monkeypatch.setenv("SOAR_EXECUTION_MODE", "invalid")
    monkeypatch.setenv("SOAR_RUNNER_BATCH_SIZE", "10")
    code = soar_worker_run.main([])
    assert code == 1


def test_runner_non_integer_batch_exits_1(monkeypatch):
    monkeypatch.setenv("SOAR_EXECUTION_MODE", "simulation")
    monkeypatch.setenv("SOAR_RUNNER_BATCH_SIZE", "abc")
    code = soar_worker_run.main([])
    assert code == 1


def test_runner_batch_below_one_exits_1(monkeypatch):
    monkeypatch.setenv("SOAR_EXECUTION_MODE", "simulation")
    monkeypatch.setenv("SOAR_RUNNER_BATCH_SIZE", "0")
    code = soar_worker_run.main([])
    assert code == 1


def test_runner_batch_clamped_to_50(monkeypatch):
    monkeypatch.setenv("SOAR_EXECUTION_MODE", "simulation")
    monkeypatch.setenv("SOAR_RUNNER_BATCH_SIZE", "999")
    args = MagicMock(mode=None, batch_size=None)
    mode, batch_size = soar_worker_run._load_and_validate_config(args)
    assert mode == "simulation"
    assert batch_size == 50


def test_runner_missing_database_url_exits_1(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SOAR_EXECUTION_MODE", "simulation")
    monkeypatch.setenv("SOAR_RUNNER_BATCH_SIZE", "10")
    code = soar_worker_run.main([])
    assert code == 1


def test_runner_connect_uses_database_url(monkeypatch):
    _set_base_env(monkeypatch)
    mock_conn = MagicMock()
    with patch("scripts.soar_worker_run.psycopg2.connect", return_value=mock_conn) as connect_mock, patch(
        "scripts.soar_worker_run.process_batch", return_value=[]
    ):
        code = soar_worker_run.main([])
    assert code == 0
    connect_mock.assert_called_once()
    assert connect_mock.call_args.args[0] == "postgresql://example/db"


def test_runner_default_executor_is_simulation(monkeypatch):
    _set_base_env(monkeypatch)
    executor = soar_worker_run._build_executor("simulation")
    assert executor.__class__.__name__ == "SimulationExecutor"


def test_runner_real_mode_executor_is_adapter_backed(monkeypatch):
    monkeypatch.setenv("SOAR_ADAPTER_BLOCK_IP", "linux_firewall_dry_run")
    monkeypatch.setenv("SOAR_LINUX_FIREWALL_DRY_RUN_ENABLED", "true")
    executor = soar_worker_run._build_executor("real")
    assert isinstance(executor, AdapterBackedExecutor)


def test_runner_aggregate_counts():
    counts = soar_worker_run._aggregate_results(
        [
            {"outcome": "success"},
            {"outcome": "failed"},
            {"outcome": "skipped"},
            {"outcome": "requeued"},
            {"outcome": "success"},
        ]
    )
    assert counts == {
        "processed": 5,
        "success": 2,
        "failed": 1,
        "skipped": 1,
        "requeued": 1,
    }


def test_runner_aggregate_invalid_shape_raises():
    try:
        soar_worker_run._aggregate_results([{"no_outcome": "x"}])
        assert False, "Expected aggregate shape validation failure"
    except Exception as error:
        assert "outcome" in str(error)


def test_runner_process_batch_uncaught_exception_exits_2(monkeypatch):
    _set_base_env(monkeypatch)
    mock_conn = MagicMock()
    with patch("scripts.soar_worker_run.psycopg2.connect", return_value=mock_conn), patch(
        "scripts.soar_worker_run.process_batch", side_effect=Exception("boom")
    ):
        code = soar_worker_run.main([])
    assert code == 2


def test_cli_batch_size_overrides_env(monkeypatch):
    monkeypatch.setenv("SOAR_RUNNER_BATCH_SIZE", "20")
    args = MagicMock(mode=None, batch_size=5)
    _, batch_size = soar_worker_run._load_and_validate_config(args)
    assert batch_size == 5


def test_cli_mode_overrides_env(monkeypatch):
    monkeypatch.setenv("SOAR_EXECUTION_MODE", "simulation")
    args = MagicMock(mode="real", batch_size=None)
    mode, _ = soar_worker_run._load_and_validate_config(args)
    assert mode == "real"


def test_env_batch_size_used_when_cli_not_set(monkeypatch):
    monkeypatch.setenv("SOAR_RUNNER_BATCH_SIZE", "15")
    args = MagicMock(mode=None, batch_size=None)
    _, batch_size = soar_worker_run._load_and_validate_config(args)
    assert batch_size == 15


def test_env_mode_defaults_to_simulation_when_cli_not_set(monkeypatch):
    monkeypatch.delenv("SOAR_EXECUTION_MODE", raising=False)
    args = MagicMock(mode=None, batch_size=None)
    mode, _ = soar_worker_run._load_and_validate_config(args)
    assert mode == "simulation"


def test_runner_json_config_error_output(monkeypatch, capsys):
    monkeypatch.setenv("SOAR_EXECUTION_MODE", "invalid")
    code = soar_worker_run.main(["--json"])
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert "error" in payload


def test_runner_json_output_parseable(monkeypatch, capsys):
    _set_base_env(monkeypatch)
    mock_conn = MagicMock()
    with patch("scripts.soar_worker_run.psycopg2.connect", return_value=mock_conn), patch(
        "scripts.soar_worker_run.process_batch", return_value=[{"outcome": "success"}]
    ):
        code = soar_worker_run.main(["--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert {"mode", "batch_size", "started_at", "results", "summary"} <= set(payload.keys())
    assert payload["summary"]["processed"] == len(payload["results"])


def test_runner_json_output_empty_queue(monkeypatch, capsys):
    _set_base_env(monkeypatch)
    mock_conn = MagicMock()
    with patch("scripts.soar_worker_run.psycopg2.connect", return_value=mock_conn), patch(
        "scripts.soar_worker_run.process_batch", return_value=[]
    ):
        code = soar_worker_run.main(["--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["results"] == []
    assert payload["summary"]["processed"] == 0


def _insert_alert(cur, source_ip):
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message)
        VALUES ('runner_test', 'low', %s, 'runner test alert')
        RETURNING id
        """,
        (source_ip,),
    )
    return cur.fetchone()[0]


def _count_queue_by_status(cur, status):
    cur.execute("SELECT COUNT(*) FROM response_actions_queue WHERE status = %s", (status,))
    return cur.fetchone()[0]


def _snapshot_queue_statuses(cur):
    cur.execute("SELECT id, status FROM response_actions_queue ORDER BY id")
    return cur.fetchall()


class _NoCloseConnectionProxy:
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        return None


def test_runner_db_backed_simulation_success(postgres_db):
    conn, cur = postgres_db
    alert_ids = [
        _insert_alert(cur, "8.8.8.8"),
        _insert_alert(cur, "1.1.1.1"),
        _insert_alert(cur, "9.9.9.9"),
    ]
    for alert_id, ip in zip(alert_ids, ["8.8.8.8", "1.1.1.1", "9.9.9.9"]):
        enqueue_response_action(cur, alert_id, ip, "block_ip")
    conn.commit()

    results = soar_worker_run.process_batch(conn, limit=10, executor=soar_worker_run.SimulationExecutor())
    counts = soar_worker_run._aggregate_results(results)

    assert counts["processed"] == 3
    assert counts["success"] == 3
    assert counts["failed"] == 0
    assert counts["skipped"] == 0
    assert counts["requeued"] == 0
    assert _count_queue_by_status(cur, "success") == 3


def test_runner_db_backed_simulation_partial_skip(postgres_db):
    conn, cur = postgres_db
    ok1 = _insert_alert(cur, "8.8.8.8")
    ok2 = _insert_alert(cur, "1.1.1.1")
    bad = _insert_alert(cur, "10.0.0.1")
    enqueue_response_action(cur, ok1, "8.8.8.8", "block_ip")
    enqueue_response_action(cur, ok2, "1.1.1.1", "block_ip")
    enqueue_response_action(cur, bad, "10.0.0.1", "block_ip")
    conn.commit()

    results = soar_worker_run.process_batch(conn, limit=10, executor=soar_worker_run.SimulationExecutor())
    counts = soar_worker_run._aggregate_results(results)

    assert counts["processed"] == 3
    assert counts["success"] == 2
    assert counts["skipped"] == 1


def test_runner_db_backed_empty_queue(postgres_db):
    conn, _cur = postgres_db
    results = soar_worker_run.process_batch(conn, limit=10, executor=soar_worker_run.SimulationExecutor())
    counts = soar_worker_run._aggregate_results(results)
    assert counts["processed"] == 0


def test_normalize_queue_counts_defaults_and_filters():
    assert soar_worker_run._normalize_queue_counts({}) == {
        "pending": 0,
        "running": 0,
        "failed": 0,
        "skipped": 0,
        "success": 0,
    }
    normalized = soar_worker_run._normalize_queue_counts(
        {"pending": 3, "failed": 1, "unknown_status": 99}
    )
    assert normalized == {
        "pending": 3,
        "running": 0,
        "failed": 1,
        "skipped": 0,
        "success": 0,
    }


def test_dry_run_info_does_not_call_process_batch(postgres_db, monkeypatch):
    conn, cur = postgres_db
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    alert_id = _insert_alert(cur, "8.8.8.8")
    enqueue_response_action(cur, alert_id, "8.8.8.8", "block_ip")
    conn.commit()

    with patch(
        "scripts.soar_worker_run.psycopg2.connect",
        return_value=_NoCloseConnectionProxy(conn),
    ), patch(
        "scripts.soar_worker_run.process_batch"
    ) as process_batch_mock:
        code = soar_worker_run.main(["--dry-run-info"])
    assert code == 0
    process_batch_mock.assert_not_called()


def test_dry_run_info_keeps_queue_unchanged(postgres_db, monkeypatch):
    conn, cur = postgres_db
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    alert_id = _insert_alert(cur, "8.8.8.8")
    enqueue_response_action(cur, alert_id, "8.8.8.8", "block_ip")
    conn.commit()
    before = _snapshot_queue_statuses(cur)

    with patch(
        "scripts.soar_worker_run.psycopg2.connect",
        return_value=_NoCloseConnectionProxy(conn),
    ):
        code = soar_worker_run.main(["--dry-run-info"])
    assert code == 0
    after = _snapshot_queue_statuses(cur)
    assert before == after


def test_dry_run_info_json_output(postgres_db, capsys, monkeypatch):
    conn, cur = postgres_db
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    alert_id = _insert_alert(cur, "8.8.8.8")
    enqueue_response_action(cur, alert_id, "8.8.8.8", "block_ip")
    conn.commit()

    with patch(
        "scripts.soar_worker_run.psycopg2.connect",
        return_value=_NoCloseConnectionProxy(conn),
    ):
        code = soar_worker_run.main(["--dry-run-info", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "dry_run_info"
    assert set(payload["queue_counts"].keys()) == {
        "pending",
        "running",
        "failed",
        "skipped",
        "success",
    }

