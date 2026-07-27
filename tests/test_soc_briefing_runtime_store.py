from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from core.ai.config import AI_MODE_DISABLED, AI_MODE_LOCAL_ONLY, AiGatewayConfig
from core.ai.soc_briefing_runtime_store import (
    JOB_STATUS_BLOCKED,
    JOB_STATUS_FAILED,
    JOB_STATUS_PENDING,
    JOB_STATUS_RUNNING,
    SERVICE_ACTOR,
    SocBriefingSecurityError,
    claim_next_job,
    complete_job,
    create_or_get_job,
    create_or_get_window,
    create_schedule,
    enforce_service_actor_read_only,
    get_runtime_metrics,
    heartbeat_job_lease,
    materialize_due_schedule,
    recover_stale_jobs,
)
from core.ai.soc_briefing_worker import (
    SocBriefingWorkerConfig,
    run_soc_briefing_worker,
)
from core.worker_heartbeat_store import SOC_BRIEFING_WORKER_NAME, get_worker_heartbeat


class NoCloseConnection:
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        return None


def _connect_same(conn):
    return lambda: NoCloseConnection(conn)


def _due_schedule(conn, *, due_at=None, cadence_minutes=60, enabled=True, **kwargs):
    due = due_at or datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)
    schedule = create_schedule(
        conn,
        name=kwargs.pop("name", "Morning SOC briefing"),
        next_due_at=due,
        cadence_minutes=cadence_minutes,
        enabled=enabled,
        **kwargs,
    )
    conn.commit()
    return schedule


def test_duplicate_window_and_job_prevention(postgres_db):
    conn, _cur = postgres_db
    schedule = _due_schedule(conn)
    start = datetime(2026, 7, 27, 7, 0, tzinfo=timezone.utc)
    end = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)

    first_window, first_created = create_or_get_window(conn, schedule_id=schedule["id"], window_start=start, window_end=end)
    second_window, second_created = create_or_get_window(conn, schedule_id=schedule["id"], window_start=start, window_end=end)
    first_job, first_job_created = create_or_get_job(conn, schedule_id=schedule["id"], window_id=first_window["id"])
    second_job, second_job_created = create_or_get_job(conn, schedule_id=schedule["id"], window_id=first_window["id"])
    conn.commit()

    assert first_created is True
    assert second_created is False
    assert first_window["id"] == second_window["id"]
    assert first_job_created is True
    assert second_job_created is False
    assert first_job["id"] == second_job["id"]


def test_claim_lease_heartbeat_and_owner_matched_completion(postgres_db):
    conn, _cur = postgres_db
    schedule = _due_schedule(conn)
    window, _ = create_or_get_window(
        conn,
        schedule_id=schedule["id"],
        window_start=datetime(2026, 7, 27, 7, 0, tzinfo=timezone.utc),
        window_end=datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc),
    )
    create_or_get_job(conn, schedule_id=schedule["id"], window_id=window["id"])
    conn.commit()

    claimed = claim_next_job(conn, lease_owner="worker-a", now=datetime(2026, 7, 27, 8, 1, tzinfo=timezone.utc))
    second_claim = claim_next_job(conn, lease_owner="worker-b", now=datetime(2026, 7, 27, 8, 1, tzinfo=timezone.utc))
    assert claimed["status"] == JOB_STATUS_RUNNING
    assert second_claim is None

    assert heartbeat_job_lease(
        conn,
        claimed["id"],
        lease_owner="worker-b",
        now=datetime(2026, 7, 27, 8, 2, tzinfo=timezone.utc),
    ) is None
    assert heartbeat_job_lease(
        conn,
        claimed["id"],
        lease_owner="worker-a",
        now=datetime(2026, 7, 27, 8, 2, tzinfo=timezone.utc),
    ) is not None
    assert complete_job(conn, claimed["id"], lease_owner="worker-b", status="success") is None
    completed = complete_job(conn, claimed["id"], lease_owner="worker-a", status="success")
    conn.commit()
    assert completed["status"] == "success"


def test_stale_lease_recovery_requeues_then_fails_when_attempts_exhaust(postgres_db):
    conn, _cur = postgres_db
    schedule = _due_schedule(conn)
    now = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)
    window, _ = create_or_get_window(conn, schedule_id=schedule["id"], window_start=now - timedelta(hours=1), window_end=now)
    job, _ = create_or_get_job(conn, schedule_id=schedule["id"], window_id=window["id"], max_attempts=2)
    claim_next_job(conn, lease_owner="worker-a", now=now - timedelta(minutes=5), lease_duration_seconds=60)
    conn.commit()

    recovered = recover_stale_jobs(conn, now=now, limit=10)
    conn.commit()
    assert recovered == {"recovered": 1, "failed": 0}

    claim_next_job(conn, lease_owner="worker-b", now=now, lease_duration_seconds=60)
    failed = recover_stale_jobs(conn, now=now + timedelta(minutes=5), limit=10)
    conn.commit()
    assert failed == {"recovered": 0, "failed": 1}

    with conn.cursor() as cur:
        cur.execute("SELECT status, failure_code FROM soc_briefing_jobs WHERE id = %s", (job["id"],))
        assert cur.fetchone() == (JOB_STATUS_FAILED, "stale_lease_expired")


def test_bounded_catch_up_coalesces_overnight_work(postgres_db):
    conn, _cur = postgres_db
    due = datetime(2026, 7, 26, 20, 0, tzinfo=timezone.utc)
    now = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)
    schedule = _due_schedule(
        conn,
        due_at=due,
        cadence_minutes=60,
        max_catch_up_windows=3,
        max_lookback_hours=24,
        coalesce_missed_windows=True,
    )

    result = materialize_due_schedule(conn, schedule, now=now)
    conn.commit()

    assert result.jobs_created == 1
    assert result.skipped_windows > 0
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM soc_briefing_jobs")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT COUNT(*) FROM soc_briefing_schedule_windows WHERE skip_reason = 'coalesced'")
        assert cur.fetchone()[0] == 1


def test_malformed_and_disabled_schedules_fail_safely(postgres_db):
    conn, _cur = postgres_db
    disabled = _due_schedule(conn, enabled=False)
    assert materialize_due_schedule(conn, disabled).blocked_schedules == 1

    malformed = _due_schedule(conn, timezone_name="Not/AZone")
    result = materialize_due_schedule(conn, malformed)
    conn.commit()
    assert result.blocked_schedules == 1
    with conn.cursor() as cur:
        cur.execute("SELECT status, failure_code FROM soc_briefing_schedules WHERE id = %s", (malformed["id"],))
        assert cur.fetchone() == ("blocked", "malformed_schedule")


def test_worker_persists_ai_disabled_outcome_run_steps_briefing_and_heartbeat(postgres_db):
    conn, _cur = postgres_db
    _due_schedule(conn)

    stats = run_soc_briefing_worker(
        config=SocBriefingWorkerConfig(batch_size=1, materialize_limit=5, max_runtime_seconds=10),
        worker_id="soc-worker-test",
        connect=_connect_same(conn),
        now_fn=lambda: datetime(2026, 7, 27, 8, 1, tzinfo=timezone.utc),
        gateway_config=AiGatewayConfig(mode=AI_MODE_DISABLED, configured_mode=AI_MODE_DISABLED),
    )

    assert stats["processed"] == 1
    assert stats["blocked"] == 1
    assert get_worker_heartbeat(conn, worker_name=SOC_BRIEFING_WORKER_NAME)["worker_instance_id"] == "soc-worker-test"
    with conn.cursor() as cur:
        cur.execute("SELECT status, service_actor, ai_gateway_status, error_code FROM soc_briefing_runs")
        assert cur.fetchone() == ("blocked", SERVICE_ACTOR, "disabled", "ai_gateway_disabled")
        cur.execute("SELECT step_type, status, error_code FROM soc_briefing_run_steps ORDER BY step_index")
        steps = cur.fetchall()
        assert steps[0] == ("runtime_investigation_start", "success", None)
        assert ("ai_synthesis", "blocked", "ai_gateway_disabled") in steps
        cur.execute("SELECT status, lifecycle_status, content_status FROM soc_briefings")
        assert cur.fetchone() == ("blocked", "blocked", "blocked")


def test_worker_persists_local_provider_unavailable_without_model_call(postgres_db):
    conn, _cur = postgres_db
    _due_schedule(conn)

    run_soc_briefing_worker(
        config=SocBriefingWorkerConfig(batch_size=1, materialize_limit=5, max_runtime_seconds=10),
        worker_id="soc-worker-provider-test",
        connect=_connect_same(conn),
        now_fn=lambda: datetime(2026, 7, 27, 8, 1, tzinfo=timezone.utc),
        gateway_config=AiGatewayConfig(mode=AI_MODE_LOCAL_ONLY, configured_mode=AI_MODE_LOCAL_ONLY),
    )

    with conn.cursor() as cur:
        cur.execute("SELECT status, provider_status, error_code FROM soc_briefing_runs")
        assert cur.fetchone() == ("blocked", "local_provider_not_configured", "local_provider_unavailable")


def test_worker_persistence_failure_aborts_without_silent_continue(postgres_db):
    conn, _cur = postgres_db
    _due_schedule(conn)

    with patch("core.ai.soc_briefing_worker.create_run_step", side_effect=RuntimeError("persist failed")):
        with pytest.raises(RuntimeError, match="persist failed"):
            run_soc_briefing_worker(
                config=SocBriefingWorkerConfig(batch_size=1, materialize_limit=5, max_runtime_seconds=10),
                worker_id="soc-worker-failure-test",
                connect=_connect_same(conn),
                now_fn=lambda: datetime(2026, 7, 27, 8, 1, tzinfo=timezone.utc),
                gateway_config=AiGatewayConfig(mode=AI_MODE_DISABLED, configured_mode=AI_MODE_DISABLED),
            )


def test_graceful_shutdown_stops_new_claims(postgres_db):
    conn, _cur = postgres_db
    _due_schedule(conn)
    shutdown = type("Shutdown", (), {"requested": True, "reason": "test_shutdown"})()

    stats = run_soc_briefing_worker(
        config=SocBriefingWorkerConfig(batch_size=1, materialize_limit=5, max_runtime_seconds=10),
        worker_id="soc-worker-shutdown-test",
        shutdown=shutdown,
        connect=_connect_same(conn),
        now_fn=lambda: datetime(2026, 7, 27, 8, 1, tzinfo=timezone.utc),
        gateway_config=AiGatewayConfig(mode=AI_MODE_DISABLED, configured_mode=AI_MODE_DISABLED),
    )

    assert stats["processed"] == 0
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM soc_briefing_jobs WHERE status = %s", (JOB_STATUS_PENDING,))
        assert cur.fetchone()[0] == 1


def test_service_actor_rejects_mutations_and_allows_valid_read_tool():
    with pytest.raises(SocBriefingSecurityError):
        enforce_service_actor_read_only("approve")

    enforce_service_actor_read_only("read_tool", tool_name="search_alerts")


def test_runtime_metrics_hide_lease_owner_and_report_counts(postgres_db):
    conn, _cur = postgres_db
    schedule = _due_schedule(conn)
    window, _ = create_or_get_window(
        conn,
        schedule_id=schedule["id"],
        window_start=datetime(2026, 7, 27, 7, 0, tzinfo=timezone.utc),
        window_end=datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc),
    )
    create_or_get_job(conn, schedule_id=schedule["id"], window_id=window["id"])
    conn.commit()

    metrics = get_runtime_metrics(conn, now=datetime(2026, 7, 27, 8, 1, tzinfo=timezone.utc))

    assert metrics["read_only"] is True
    assert metrics["service_actor"] == SERVICE_ACTOR
    assert metrics["jobs"]["pending"] == 1
    assert "lease_owner" not in str(metrics)
