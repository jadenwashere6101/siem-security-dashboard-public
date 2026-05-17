from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from core import playbook_store
from engines import soar_playbook_worker
from engines.soar_playbook_worker import PlaybookWorkerConfig, PlaybookWorkerShutdown


class FakeConnection:
    def __init__(self, name="conn"):
        self.name = name
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class NoCloseConnection:
    def __init__(self, conn):
        self.conn = conn
        self.closed = False

    def cursor(self, *args, **kwargs):
        return self.conn.cursor(*args, **kwargs)

    def commit(self):
        return self.conn.commit()

    def rollback(self):
        return self.conn.rollback()

    def close(self):
        self.closed = True


def _config(**overrides):
    values = {
        "batch_size": 10,
        "poll_interval_seconds": 1,
        "idle_backoff_seconds": 5,
        "jitter_seconds": 0,
        "error_backoff_seconds": 7,
        "stale_recovery_interval_seconds": 60,
        "stale_limit": 50,
        "max_loops": 1,
    }
    values.update(overrides)
    return PlaybookWorkerConfig(**values)


def _clock(start=None, step_seconds=1):
    current = start or datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)

    def now():
        nonlocal current
        value = current
        current = current + timedelta(seconds=step_seconds)
        return value

    return now


def test_daemon_loop_processes_one_batch_and_uses_worker_identity(caplog):
    conn = FakeConnection()
    sleeps = []

    with patch("engines.soar_playbook_worker.generate_playbook_worker_id", return_value="worker-alpha"), patch(
        "engines.soar_playbook_worker.recover_stale_playbook_executions",
        return_value={"recovered": 0},
    ) as recover, patch(
        "engines.soar_playbook_worker.process_playbook_execution_batch",
        return_value={"processed": 1, "success": 1, "failed": 0, "skipped": 0},
    ) as batch:
        result = soar_playbook_worker.run_playbook_worker(
            config=_config(),
            connect=lambda: conn,
            sleeper=sleeps.append,
            now_fn=_clock(),
        )

    assert result["worker_id"] == "worker-alpha"
    assert result["loops"] == 1
    assert result["processed"] == 1
    assert conn.commits == 2
    assert conn.rollbacks == 0
    assert conn.closed is True
    recover.assert_called_once()
    batch.assert_called_once()
    assert batch.call_args.kwargs["worker_id"] == "worker-alpha"
    assert sleeps == [1]
    assert "soar_playbook_worker_loop worker_id=worker-alpha" in caplog.text


def test_idle_loop_uses_idle_backoff():
    conn = FakeConnection()
    sleeps = []

    with patch(
        "engines.soar_playbook_worker.recover_stale_playbook_executions",
        return_value={"recovered": 0},
    ), patch(
        "engines.soar_playbook_worker.process_playbook_execution_batch",
        return_value={"processed": 0, "success": 0, "failed": 0, "skipped": 0},
    ):
        result = soar_playbook_worker.run_playbook_worker(
            config=_config(idle_backoff_seconds=9),
            worker_id="worker-idle",
            connect=lambda: conn,
            sleeper=sleeps.append,
            now_fn=_clock(),
        )

    assert result["loops"] == 1
    assert sleeps == [9]


def test_max_loop_mode_exits_without_extra_claims():
    connections = [FakeConnection("one"), FakeConnection("two")]
    sleeps = []

    with patch(
        "engines.soar_playbook_worker.recover_stale_playbook_executions",
        return_value={"recovered": 0},
    ), patch(
        "engines.soar_playbook_worker.process_playbook_execution_batch",
        return_value={"processed": 0, "success": 0, "failed": 0, "skipped": 0},
    ) as batch:
        result = soar_playbook_worker.run_playbook_worker(
            config=_config(max_loops=2, poll_interval_seconds=0, idle_backoff_seconds=0),
            worker_id="worker-max",
            connect=lambda: connections.pop(0),
            sleeper=sleeps.append,
            now_fn=_clock(),
        )

    assert result["loops"] == 2
    assert result["shutdown_reason"] == "max_loops"
    assert batch.call_count == 2
    assert sleeps == []


def test_stale_recovery_cadence_does_not_run_every_loop():
    connections = [FakeConnection(str(index)) for index in range(3)]

    with patch(
        "engines.soar_playbook_worker.recover_stale_playbook_executions",
        return_value={"recovered": 0},
    ) as recover, patch(
        "engines.soar_playbook_worker.process_playbook_execution_batch",
        return_value={"processed": 0, "success": 0, "failed": 0, "skipped": 0},
    ):
        result = soar_playbook_worker.run_playbook_worker(
            config=_config(
                max_loops=3,
                poll_interval_seconds=0,
                idle_backoff_seconds=0,
                stale_recovery_interval_seconds=60,
            ),
            worker_id="worker-recovery",
            connect=lambda: connections.pop(0),
            sleeper=lambda _seconds: None,
            now_fn=_clock(step_seconds=10),
        )

    assert result["loops"] == 3
    assert recover.call_count == 1


def test_stale_recovery_runs_every_loop_when_interval_zero():
    connections = [FakeConnection(str(index)) for index in range(3)]

    with patch(
        "engines.soar_playbook_worker.recover_stale_playbook_executions",
        return_value={"recovered": 1},
    ) as recover, patch(
        "engines.soar_playbook_worker.process_playbook_execution_batch",
        return_value={"processed": 0, "success": 0, "failed": 0, "skipped": 0},
    ):
        result = soar_playbook_worker.run_playbook_worker(
            config=_config(
                max_loops=3,
                poll_interval_seconds=0,
                idle_backoff_seconds=0,
                stale_recovery_interval_seconds=0,
            ),
            worker_id="worker-recovery",
            connect=lambda: connections.pop(0),
            sleeper=lambda _seconds: None,
            now_fn=_clock(),
        )

    assert result["loops"] == 3
    assert result["recovered"] == 3
    assert recover.call_count == 3


def test_dry_run_recovery_rolls_back_recovery_before_batch_commit():
    conn = FakeConnection()

    with patch(
        "engines.soar_playbook_worker.recover_stale_playbook_executions",
        return_value={"recovered": 0},
    ) as recover, patch(
        "engines.soar_playbook_worker.process_playbook_execution_batch",
        return_value={"processed": 0, "success": 0, "failed": 0, "skipped": 0},
    ):
        result = soar_playbook_worker.run_playbook_worker(
            config=_config(dry_run_recovery=True),
            worker_id="worker-dry-run",
            connect=lambda: conn,
            sleeper=lambda _seconds: None,
            now_fn=_clock(),
        )

    assert result["loops"] == 1
    assert conn.rollbacks == 1
    assert conn.commits == 1
    assert recover.call_args.kwargs["dry_run"] is True


def test_db_failure_rolls_back_closes_backs_off_and_retries_without_secret_logs(caplog):
    first = FakeConnection("first")
    second = FakeConnection("second")
    connections = [first, second]
    sleeps = []

    def batch(conn, **_kwargs):
        if conn is first:
            raise RuntimeError("postgresql://user:secret-password@example.invalid/db")
        return {"processed": 0, "success": 0, "failed": 0, "skipped": 0}

    with patch(
        "engines.soar_playbook_worker.recover_stale_playbook_executions",
        return_value={"recovered": 0},
    ), patch("engines.soar_playbook_worker.process_playbook_execution_batch", side_effect=batch):
        result = soar_playbook_worker.run_playbook_worker(
            config=_config(max_loops=1, error_backoff_seconds=11),
            worker_id="worker-retry",
            connect=lambda: connections.pop(0),
            sleeper=sleeps.append,
            now_fn=_clock(step_seconds=61),
        )

    assert result["loops"] == 1
    assert result["errors"] == 1
    assert first.rollbacks == 1
    assert first.closed is True
    assert second.closed is True
    assert sleeps == [11, 5]
    assert "worker-retry" in caplog.text
    assert "RuntimeError" in caplog.text
    assert "postgresql://" not in caplog.text
    assert "secret-password" not in caplog.text


def test_graceful_shutdown_flag_exits_cleanly():
    conn = FakeConnection()
    shutdown = PlaybookWorkerShutdown()

    def sleep_and_stop(_seconds):
        shutdown.request("test_shutdown")

    with patch(
        "engines.soar_playbook_worker.recover_stale_playbook_executions",
        return_value={"recovered": 0},
    ), patch(
        "engines.soar_playbook_worker.process_playbook_execution_batch",
        return_value={"processed": 0, "success": 0, "failed": 0, "skipped": 0},
    ):
        result = soar_playbook_worker.run_playbook_worker(
            config=_config(max_loops=None),
            worker_id="worker-stop",
            shutdown=shutdown,
            connect=lambda: conn,
            sleeper=sleep_and_stop,
            now_fn=_clock(),
        )

    assert result["loops"] == 1
    assert result["shutdown_reason"] == "test_shutdown"
    assert conn.closed is True


def test_two_daemon_instances_do_not_duplicate_execution(postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message)
        VALUES ('worker_test', 'LOW', '10.8.0.1'::inet, 'worker test')
        RETURNING id
        """
    )
    alert_id = cur.fetchone()[0]
    playbook_store.create_playbook_definition(
        conn,
        "pb_worker_daemon",
        "Worker daemon",
        steps=[{"action": "monitor", "params": {}}],
    )
    execution_id = playbook_store.create_pending_playbook_execution_once(
        conn,
        "pb_worker_daemon",
        alert_id,
    )
    conn.commit()

    first_conn = NoCloseConnection(conn)
    second_conn = NoCloseConnection(conn)

    first = soar_playbook_worker.run_playbook_worker(
        config=_config(max_loops=1, poll_interval_seconds=0, idle_backoff_seconds=0),
        worker_id="worker-one",
        connect=lambda: first_conn,
        sleeper=lambda _seconds: None,
        now_fn=_clock(),
    )
    second = soar_playbook_worker.run_playbook_worker(
        config=_config(max_loops=1, poll_interval_seconds=0, idle_backoff_seconds=0),
        worker_id="worker-two",
        connect=lambda: second_conn,
        sleeper=lambda _seconds: None,
        now_fn=_clock(),
    )

    row = playbook_store.get_playbook_execution(conn, execution_id)
    assert first["processed"] == 1
    assert second["processed"] == 0
    assert row["status"] == "success"
    assert len(row["steps_log"]) == 1
