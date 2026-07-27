from datetime import datetime, timedelta, timezone
import json

import pytest

from core.ai.config import (
    AI_MODE_ASK_BEFORE_PAID_FALLBACK,
    AI_MODE_AUTOMATIC_FALLBACK,
    AI_MODE_DISABLED,
    AI_MODE_LOCAL_ONLY,
    AiGatewayConfig,
)
from core.ai.models import (
    AI_STATUS_PROVIDER_TIMEOUT,
    AI_STATUS_SUCCESS,
    AiGatewayResponse,
    AiRequestMetadata,
)
from core.ai.soc_briefing_investigation_engine import (
    BRIEFING_SECTIONS,
    InvestigationBudget,
    InvestigationCandidate,
    plan_investigation_candidates,
    run_scheduled_investigation,
)
from core.ai.soc_briefing_runtime_store import (
    SERVICE_ACTOR,
    SERVICE_ACTOR_ROLE,
    create_or_get_job,
    create_or_get_window,
    create_run,
    create_schedule,
    idempotency_key,
)
from core.ai.soc_tools import SocToolExecutionSummary, SocToolResult, SocToolSource
from core.ai.soc_briefing_worker import SocBriefingWorkerConfig, run_soc_briefing_worker


class NoCloseConnection:
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        return None


class FakeGateway:
    def __init__(self, *, content=None, status=AI_STATUS_SUCCESS, error=None, error_code=None, paid_request=False):
        self.calls = []
        self.content = content
        self.status = status
        self.error = error
        self.error_code = error_code
        self.paid_request = paid_request

    def generate(self, request):
        self.calls.append(request)
        return AiGatewayResponse(
            status=self.status,
            content=self.content,
            error=self.error,
            metadata=AiRequestMetadata(
                provider="fake-local",
                model="fake-model",
                mode="local_only",
                status=self.status,
                estimated_prompt_tokens=10,
                estimated_completion_tokens=5,
                estimated_cost_usd=0.01 if self.paid_request else 0,
                local_request=not self.paid_request,
                paid_request=self.paid_request,
                error_code=self.error_code,
            ),
        )


def _connect_same(conn):
    return lambda: NoCloseConnection(conn)


def _schedule_window_job_run(conn, *, now=None):
    current = now or datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)
    schedule = create_schedule(
        conn,
        name="Morning SOC briefing",
        next_due_at=current,
        cadence_minutes=60,
        enabled=True,
    )
    window, _ = create_or_get_window(
        conn,
        schedule_id=schedule["id"],
        window_start=current - timedelta(hours=1),
        window_end=current,
    )
    job, _ = create_or_get_job(conn, schedule_id=schedule["id"], window_id=window["id"])
    job = {
        **job,
        "status": "running",
        "attempt_count": 1,
        "lease_owner": "worker-test",
    }
    run = create_run(conn, job, now=current, budget_policy={})
    conn.commit()
    return schedule, window, job, run


def _window_job_run_for_schedule(conn, schedule, *, now):
    window, _ = create_or_get_window(
        conn,
        schedule_id=schedule["id"],
        window_start=now - timedelta(hours=1),
        window_end=now,
    )
    job, _ = create_or_get_job(conn, schedule_id=schedule["id"], window_id=window["id"])
    job = {
        **job,
        "status": "running",
        "attempt_count": 1,
        "lease_owner": "worker-test",
    }
    run = create_run(conn, job, now=now, budget_policy={})
    conn.commit()
    return window, job, run


def _insert_alert(conn, *, created_at=None, severity="critical", source_ip="203.0.113.10"):
    current = created_at or datetime(2026, 7, 27, 7, 30, tzinfo=timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO alerts (alert_type, severity, source_ip, source, source_type, message, status, context, created_at)
            VALUES ('pfsense_firewall_port_scan', %s, %s, 'pfsense', 'firewall', 'scan detected', 'open', '{}'::jsonb, %s)
            RETURNING id
            """,
            (severity, source_ip, current),
        )
        alert_id = cur.fetchone()[0]
    conn.commit()
    return alert_id


def _success_content():
    return json.dumps(
        {
            "summary": "Structured morning SOC briefing.",
            "sections": {key: [] for key in BRIEFING_SECTIONS},
        }
    )


def _tool_summary(*, truncated=False):
    source = SocToolSource(
        tool_name="get_alert_detail",
        source_type="alert",
        source_path="/alerts/1",
        source_helper="core.ai.context_builder alert context",
        record_ids=[1],
        truncated=truncated,
        omitted_count=2 if truncated else 0,
    )
    return SocToolExecutionSummary(
        used=True,
        calls=[
            SocToolResult(
                tool_name="get_alert_detail",
                status="success",
                data={"alert": {"id": 1, "secret_token": "hidden"}},
                sources=[source],
                truncated=truncated,
                omitted_count=2 if truncated else 0,
                latency_ms=12,
            )
        ],
        sources=[source],
        truncated=truncated,
        omitted_count=2 if truncated else 0,
    )


def test_planning_is_deterministic_and_bounded(postgres_db):
    conn, _cur = postgres_db
    _, window, _job, _run = _schedule_window_job_run(conn)
    _insert_alert(conn, severity="critical")
    _insert_alert(conn, severity="medium", source_ip="203.0.113.11")

    first, skipped = plan_investigation_candidates(conn, window=window, budget=InvestigationBudget(max_entities=1))
    second, second_skipped = plan_investigation_candidates(conn, window=window, budget=InvestigationBudget(max_entities=1))

    assert [item.as_ref() for item in first] == [item.as_ref() for item in second]
    assert len(first) == 1
    assert skipped[0]["reason"] == "entity_limit_exceeded"
    assert second_skipped[0]["reason"] == "entity_limit_exceeded"


def test_successful_engine_persists_structured_briefing_audit_and_steps(postgres_db):
    conn, _cur = postgres_db
    _insert_alert(conn)
    _schedule, _window, job, run = _schedule_window_job_run(conn)
    gateway = FakeGateway(content=_success_content())

    outcome = run_scheduled_investigation(
        conn,
        job=job,
        run=run,
        gateway_config=AiGatewayConfig(
            mode=AI_MODE_LOCAL_ONLY,
            configured_mode=AI_MODE_LOCAL_ONLY,
            local_base_url="http://127.0.0.1:11434",
            local_model="llama",
        ),
        gateway=gateway,
        tool_executor=lambda _calls, _context: _tool_summary(),
    )
    conn.commit()

    assert outcome.run_status == "success"
    assert len(gateway.calls) == 1
    prompt = gateway.calls[0].prompt
    assert "no_tool_calls" in prompt
    assert "secret_token" not in prompt
    with conn.cursor() as cur:
        cur.execute("SELECT status, lifecycle_status, content_status, summary, sections FROM soc_briefings")
        status, lifecycle, content_status, summary, sections = cur.fetchone()
        assert (status, lifecycle, content_status) == ("success", "content_ready", "ready")
        assert summary == "Structured morning SOC briefing."
        assert sorted(sections) == sorted(BRIEFING_SECTIONS)
        cur.execute("SELECT COUNT(*) FROM soc_briefing_run_steps WHERE run_id = %s", (run["id"],))
        assert cur.fetchone()[0] >= 5
        cur.execute("SELECT actor_username, actor_role, details FROM audit_log WHERE event_type = 'SCHEDULED_SOC_INVESTIGATION'")
        rows = cur.fetchall()
        assert rows
        assert all(row[0] == SERVICE_ACTOR and row[1] == SERVICE_ACTOR_ROLE for row in rows)


def test_gateway_disabled_blocks_without_provider_call_and_saves_blocked_briefing(postgres_db):
    conn, _cur = postgres_db
    _insert_alert(conn)
    _schedule, _window, job, run = _schedule_window_job_run(conn)
    gateway = FakeGateway(content=_success_content())

    outcome = run_scheduled_investigation(
        conn,
        job=job,
        run=run,
        gateway_config=AiGatewayConfig(mode=AI_MODE_DISABLED, configured_mode=AI_MODE_DISABLED),
        gateway=gateway,
        tool_executor=lambda _calls, _context: _tool_summary(),
    )
    conn.commit()

    assert outcome.run_status == "blocked"
    assert outcome.error_code == "ai_gateway_disabled"
    assert gateway.calls == []
    with conn.cursor() as cur:
        cur.execute("SELECT status, content_status, error_code FROM soc_briefings")
        assert cur.fetchone() == ("blocked", "blocked", "ai_gateway_disabled")


def test_deduplication_skips_recent_same_fingerprint(postgres_db):
    conn, _cur = postgres_db
    alert_id = _insert_alert(conn)
    schedule, window, job, run = _schedule_window_job_run(conn)
    candidate = plan_investigation_candidates(conn, window=window, budget=InvestigationBudget(max_entities=4))[0]
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO soc_briefing_run_steps (
                run_id, step_index, step_type, status, sanitized_input, evidence_refs, decision_summary
            )
            VALUES (%s, 42, 'investigation_candidate_result', 'success', %s, '[]'::jsonb, 'prior')
            """,
            (
                run["id"],
                json.dumps({"dedup_key": candidate.dedup_key, "evidence_fingerprint": candidate.fingerprint}),
            ),
        )
    conn.commit()
    _window2, job2, run2 = _window_job_run_for_schedule(
        conn,
        schedule,
        now=datetime(2026, 7, 27, 8, 30, tzinfo=timezone.utc),
    )

    outcome = run_scheduled_investigation(
        conn,
        job=job2,
        run=run2,
        gateway_config=AiGatewayConfig(mode=AI_MODE_DISABLED, configured_mode=AI_MODE_DISABLED),
        tool_executor=lambda _calls, _context: pytest.fail("duplicate candidate should not execute tools"),
    )
    conn.commit()

    assert alert_id
    assert outcome.error_code == "ai_gateway_disabled"
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT error_code
            FROM soc_briefing_run_steps
            WHERE run_id = %s AND step_type = 'investigation_candidate_result'
            """,
            (run2["id"],),
        )
        assert "duplicate_recent_investigation" in [row[0] for row in cur.fetchall()]


def test_new_evidence_bypasses_deduplication(postgres_db):
    conn, _cur = postgres_db
    _insert_alert(conn, severity="medium")
    schedule, window, job, run = _schedule_window_job_run(conn)
    candidate = plan_investigation_candidates(conn, window=window, budget=InvestigationBudget(max_entities=4))[0]
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO soc_briefing_run_steps (
                run_id, step_index, step_type, status, sanitized_input, evidence_refs, decision_summary
            )
            VALUES (%s, 42, 'investigation_candidate_result', 'success', %s, '[]'::jsonb, 'prior')
            """,
            (
                run["id"],
                json.dumps({"dedup_key": candidate.dedup_key, "evidence_fingerprint": "old-fingerprint"}),
            ),
        )
    conn.commit()
    _window2, job2, run2 = _window_job_run_for_schedule(
        conn,
        schedule,
        now=datetime(2026, 7, 27, 8, 30, tzinfo=timezone.utc),
    )
    calls = []

    run_scheduled_investigation(
        conn,
        job=job2,
        run=run2,
        gateway_config=AiGatewayConfig(mode=AI_MODE_DISABLED, configured_mode=AI_MODE_DISABLED),
        tool_executor=lambda planned, _context: calls.extend(planned) or _tool_summary(),
    )

    assert calls


def test_tool_budget_and_truncation_persist_partial_evidence(postgres_db):
    conn, _cur = postgres_db
    _insert_alert(conn)
    _schedule, _window, job, run = _schedule_window_job_run(conn)
    calls = []

    outcome = run_scheduled_investigation(
        conn,
        job=job,
        run=run,
        gateway_config=AiGatewayConfig(mode=AI_MODE_DISABLED, configured_mode=AI_MODE_DISABLED),
        budget=InvestigationBudget(max_tool_calls=1),
        tool_executor=lambda planned, _context: calls.extend(planned) or _tool_summary(truncated=True),
    )
    conn.commit()

    assert len(calls) == 1
    assert outcome.evidence_refs[0]["truncated"] is True
    with conn.cursor() as cur:
        cur.execute("SELECT evidence_refs FROM soc_briefings")
        assert cur.fetchone()[0][0]["truncated"] is True


def test_mutation_like_tool_is_rejected_before_execution(postgres_db, monkeypatch):
    conn, _cur = postgres_db
    _schedule, _window, job, run = _schedule_window_job_run(conn)
    bad_candidate = InvestigationCandidate(
        entity_type="alert",
        entity_id="1",
        label="bad",
        source_ip=None,
        fingerprint=idempotency_key("bad"),
        tool_calls=({"tool_name": "delete_alert", "arguments": {"alert_id": 1}},),
    )
    monkeypatch.setattr(
        "core.ai.soc_briefing_investigation_engine.plan_investigation_candidates",
        lambda _conn, window, budget: ([bad_candidate], []),
    )

    run_scheduled_investigation(
        conn,
        job=job,
        run=run,
        gateway_config=AiGatewayConfig(mode=AI_MODE_DISABLED, configured_mode=AI_MODE_DISABLED),
        tool_executor=lambda _planned, _context: pytest.fail("invalid tool should not execute"),
    )
    conn.commit()

    with conn.cursor() as cur:
        cur.execute("SELECT status, error_code FROM soc_briefing_run_steps WHERE step_type = 'soc_read_tool_validation'")
        assert cur.fetchone() == ("failed", "mutation_tool_rejected")


def test_gateway_timeout_and_malformed_output_become_partial_briefings(postgres_db):
    conn, _cur = postgres_db
    _insert_alert(conn)
    _schedule, _window, job, run = _schedule_window_job_run(conn)

    timeout = run_scheduled_investigation(
        conn,
        job=job,
        run=run,
        gateway_config=AiGatewayConfig(
            mode=AI_MODE_LOCAL_ONLY,
            configured_mode=AI_MODE_LOCAL_ONLY,
            local_base_url="http://127.0.0.1:11434",
            local_model="llama",
        ),
        gateway=FakeGateway(status=AI_STATUS_PROVIDER_TIMEOUT, error="timeout", error_code=AI_STATUS_PROVIDER_TIMEOUT),
        tool_executor=lambda _planned, _context: _tool_summary(),
    )
    assert timeout.run_status == "partial"
    assert timeout.error_code == AI_STATUS_PROVIDER_TIMEOUT

    _schedule2, _window2, job2, run2 = _schedule_window_job_run(conn, now=datetime(2026, 7, 27, 8, 30, tzinfo=timezone.utc))
    malformed = run_scheduled_investigation(
        conn,
        job=job2,
        run=run2,
        gateway_config=AiGatewayConfig(
            mode=AI_MODE_LOCAL_ONLY,
            configured_mode=AI_MODE_LOCAL_ONLY,
            local_base_url="http://127.0.0.1:11434",
            local_model="llama",
        ),
        gateway=FakeGateway(content="not-json"),
        tool_executor=lambda _planned, _context: _tool_summary(),
    )
    assert malformed.run_status == "partial"
    assert malformed.error_code == "malformed_provider_output"


def test_paid_fallback_modes_are_blocked_for_scheduled_work(postgres_db):
    conn, _cur = postgres_db
    _insert_alert(conn)
    _schedule, _window, job, run = _schedule_window_job_run(conn)

    ask = run_scheduled_investigation(
        conn,
        job=job,
        run=run,
        gateway_config=AiGatewayConfig(mode=AI_MODE_ASK_BEFORE_PAID_FALLBACK, configured_mode=AI_MODE_ASK_BEFORE_PAID_FALLBACK),
        gateway=FakeGateway(content=_success_content()),
        tool_executor=lambda _planned, _context: _tool_summary(),
    )
    assert ask.error_code == "paid_fallback_blocked"

    _schedule2, _window2, job2, run2 = _schedule_window_job_run(conn, now=datetime(2026, 7, 27, 8, 30, tzinfo=timezone.utc))
    automatic = run_scheduled_investigation(
        conn,
        job=job2,
        run=run2,
        gateway_config=AiGatewayConfig(
            mode=AI_MODE_AUTOMATIC_FALLBACK,
            configured_mode=AI_MODE_AUTOMATIC_FALLBACK,
            local_base_url="http://127.0.0.1:11434",
            local_model="llama",
            paid_provider="openai",
            paid_model="paid",
            paid_fallback_enabled=True,
        ),
        gateway=FakeGateway(content=_success_content(), paid_request=True),
        tool_executor=lambda _planned, _context: _tool_summary(),
    )
    assert automatic.error_code == "paid_fallback_blocked"


def test_persistence_failure_aborts_loudly(postgres_db, monkeypatch):
    conn, _cur = postgres_db
    _schedule, _window, job, run = _schedule_window_job_run(conn)

    def fail(*_args, **_kwargs):
        raise RuntimeError("step persist failed")

    monkeypatch.setattr("core.ai.soc_briefing_investigation_engine.create_run_step", fail)

    with pytest.raises(RuntimeError, match="step persist failed"):
        run_scheduled_investigation(
            conn,
            job=job,
            run=run,
            gateway_config=AiGatewayConfig(mode=AI_MODE_DISABLED, configured_mode=AI_MODE_DISABLED),
        )


def test_worker_invokes_investigation_engine_after_claim_without_creating_extra_runtime_work(postgres_db):
    conn, _cur = postgres_db
    _insert_alert(conn)
    create_schedule(
        conn,
        name="Morning SOC briefing",
        next_due_at=datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc),
        cadence_minutes=60,
        enabled=True,
    )
    conn.commit()

    stats = run_soc_briefing_worker(
        config=SocBriefingWorkerConfig(batch_size=1, materialize_limit=5, max_runtime_seconds=10),
        worker_id="soc-investigation-worker-test",
        connect=_connect_same(conn),
        now_fn=lambda: datetime(2026, 7, 27, 8, 1, tzinfo=timezone.utc),
        gateway_config=AiGatewayConfig(mode=AI_MODE_DISABLED, configured_mode=AI_MODE_DISABLED),
        investigation_tool_executor=lambda _planned, _context: _tool_summary(),
    )

    assert stats["processed"] == 1
    assert stats["blocked"] == 1
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM soc_briefing_jobs")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT step_type FROM soc_briefing_run_steps ORDER BY step_index")
        assert "investigation_plan" in [row[0] for row in cur.fetchall()]
