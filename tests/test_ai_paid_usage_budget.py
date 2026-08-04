from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date
from decimal import Decimal

import psycopg2
from psycopg2 import sql
import pytest

from core.ai.config import AI_MODE_AUTOMATIC_FALLBACK, AiGatewayConfig, default_ai_profiles
from core.ai.gateway import AiGateway
from core.ai.models import (
    AI_STATUS_ACCOUNTING_UNAVAILABLE,
    AI_STATUS_BUDGET_EXHAUSTED,
    AI_STATUS_PROVIDER_TIMEOUT,
    AI_STATUS_PROVIDER_UNAVAILABLE,
    AI_STATUS_SUCCESS,
    AiCapabilityResult,
    AiGatewayRequest,
    AiGatewayResponse,
    AiProviderReadiness,
    AiRequestMetadata,
)
from core.ai.paid_usage_store import (
    PaidAccountingUnavailable,
    PaidBudgetExhausted,
    PaidUsagePricing,
    PaidUsageReservation,
    PaidUsageSettlement,
    PostgresPaidUsageStore,
)
from core.ai.profile_registry import (
    AI_PROFILE_AGENTIC_PLANNING,
    AI_PROFILE_DEEP_BRIEFING,
    AI_PROFILE_FAST_TRIAGE,
)
from core.ai.readiness import get_ai_gateway_status


USAGE_DAY = date(2026, 8, 4)


class RecordingProvider:
    def __init__(
        self,
        provider_key: str,
        events: list[str],
        *,
        status: str = AI_STATUS_SUCCESS,
        paid: bool = False,
    ):
        self.provider_key = provider_key
        self.events = events
        self.status = status
        self.paid = paid
        self.calls = 0

    def supports(self, _request):
        return AiCapabilityResult(True, AI_STATUS_SUCCESS)

    def readiness(self, _config):
        return AiProviderReadiness(self.provider_key, True, True, AI_STATUS_SUCCESS)

    def generate(self, request, config):
        self.calls += 1
        self.events.append(f"provider:{self.provider_key}")
        profile = config.profile(request.profile)
        return AiGatewayResponse(
            status=self.status,
            content="ok" if self.status == AI_STATUS_SUCCESS else None,
            error=None if self.status == AI_STATUS_SUCCESS else "Provider unavailable.",
            metadata=AiRequestMetadata(
                provider=self.provider_key,
                model=profile.model,
                mode=config.mode,
                status=self.status,
                latency_ms=7,
                provider_reported_prompt_tokens=11 if self.paid else None,
                provider_reported_completion_tokens=5 if self.paid else None,
                provider_reported_total_tokens=16 if self.paid else None,
                token_usage_source="provider_reported" if self.paid else "estimated",
                local_request=not self.paid,
                paid_request=self.paid,
                error_code=None if self.status == AI_STATUS_SUCCESS else self.status,
                profile=profile.name,
            ),
        )


class ControlledAccountingStore:
    def __init__(self, events: list[str], *, failure: str | None = None):
        self.events = events
        self.failure = failure
        self.reservations = []
        self.settlements = []

    def reserve(self, *, request, **_kwargs):
        self.events.append("reserve")
        if self.failure == "unavailable":
            raise PaidAccountingUnavailable("unavailable")
        if self.failure == "exhausted":
            raise PaidBudgetExhausted(
                attempt_id="blocked-attempt",
                usage_day=USAGE_DAY,
                requested_usd=Decimal("0.10"),
                remaining_usd=Decimal("0.01"),
            )
        attempt_kind = "repair" if request.metadata.get("repair_attempt") == 1 else "initial"
        reservation = PaidUsageReservation(
            attempt_id=f"attempt-{len(self.reservations) + 1}",
            usage_day=USAGE_DAY,
            reserved_cost_usd=Decimal("0.10"),
            remaining_usd=Decimal("4.90"),
            estimated_input_tokens=20,
            estimated_output_tokens=30,
            correlation_id=request.metadata.get("paid_correlation_id"),
            attempt_kind=attempt_kind,
        )
        self.reservations.append(reservation)
        return reservation

    def settle(self, reservation, response, **_kwargs):
        self.events.append("settle")
        self.settlements.append((reservation, response))
        return PaidUsageSettlement(
            attempt_id=reservation.attempt_id,
            usage_day=reservation.usage_day,
            charged_cost_usd=Decimal("0.02"),
            remaining_usd=Decimal("4.98"),
            input_tokens=11,
            output_tokens=5,
            total_tokens=16,
            token_usage_source="provider_reported",
            cost_source="estimated",
        )

    def summary(self, **_kwargs):
        class Summary:
            def as_dict(self):
                return {
                    "usage_day": USAGE_DAY.isoformat(),
                    "daily_cap_usd": 5.0,
                    "reserved_usd": 0.1,
                    "settled_usd": 1.25,
                    "used_usd": 1.35,
                    "remaining_usd": 3.65,
                    "total_input_tokens": 100,
                    "total_output_tokens": 40,
                    "total_tokens": 140,
                    "attempt_count": 3,
                    "token_usage_source": "estimated",
                    "cost_source": "estimated",
                }

        return Summary()


def _gateway_config(*, local_fallback: bool = False) -> AiGatewayConfig:
    model = "claude-test-model"
    profiles = default_ai_profiles(local_model="llama3.2:3b", anthropic_model=model)
    if local_fallback:
        profiles[AI_PROFILE_AGENTIC_PLANNING] = replace(
            profiles[AI_PROFILE_AGENTIC_PLANNING],
            local_fallback_profile=AI_PROFILE_FAST_TRIAGE,
        )
    return AiGatewayConfig(
        mode=AI_MODE_AUTOMATIC_FALLBACK,
        configured_mode=AI_MODE_AUTOMATIC_FALLBACK,
        local_provider="ollama",
        local_base_url="http://127.0.0.1:11434",
        local_model="llama3.2:3b",
        anthropic_enabled=True,
        anthropic_routing_enabled=True,
        anthropic_api_key="test-key-never-send",
        anthropic_model=model,
        anthropic_daily_budget_usd=5.0,
        anthropic_input_cost_per_million_tokens=3.0,
        anthropic_output_cost_per_million_tokens=15.0,
        profiles=profiles,
    )


def _paid_request(**metadata) -> AiGatewayRequest:
    return AiGatewayRequest(
        prompt="Plan this read-only analyst turn.",
        capability="agentic_analyst_planning",
        profile=AI_PROFILE_AGENTIC_PLANNING,
        metadata=metadata,
    )


def test_initial_paid_call_reserves_before_provider_and_settles_afterward():
    events = []
    accounting = ControlledAccountingStore(events)
    paid = RecordingProvider("anthropic", events, paid=True)
    response = AiGateway(
        config=_gateway_config(),
        providers={"anthropic": paid},
        accounting_store=accounting,
    ).generate(_paid_request())

    assert response.status == AI_STATUS_SUCCESS
    assert events == ["reserve", "provider:anthropic", "settle"]
    assert response.metadata.accounting_attempt_kind == "initial"
    assert response.metadata.cost_source == "estimated"
    assert response.metadata.actual_billed_cost_usd is None


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    (("exhausted", AI_STATUS_BUDGET_EXHAUSTED), ("unavailable", AI_STATUS_ACCOUNTING_UNAVAILABLE)),
)
def test_budget_or_accounting_failure_blocks_provider_before_invocation(failure, expected_status):
    events = []
    paid = RecordingProvider("anthropic", events, paid=True)
    response = AiGateway(
        config=_gateway_config(),
        providers={"anthropic": paid},
        accounting_store=ControlledAccountingStore(events, failure=failure),
    ).generate(_paid_request())

    assert response.status == expected_status
    assert paid.calls == 0
    assert events == ["reserve"]
    assert response.error


def test_explicit_local_fallback_runs_only_after_budget_exhaustion():
    events = []
    paid = RecordingProvider("anthropic", events, paid=True)
    local = RecordingProvider("ollama", events)
    response = AiGateway(
        config=_gateway_config(local_fallback=True),
        providers={"anthropic": paid, "ollama": local},
        accounting_store=ControlledAccountingStore(events, failure="exhausted"),
    ).generate(_paid_request())

    assert response.status == AI_STATUS_SUCCESS
    assert paid.calls == 0
    assert local.calls == 1
    assert response.metadata.fallback_attempted is True
    assert response.metadata.fallback_reason == AI_STATUS_BUDGET_EXHAUSTED
    assert response.metadata.accounting_attempt_id == "blocked-attempt"


def test_local_fallback_failure_returns_graceful_degraded_response():
    events = []
    local = RecordingProvider("ollama", events, status=AI_STATUS_PROVIDER_UNAVAILABLE)
    response = AiGateway(
        config=_gateway_config(local_fallback=True),
        providers={"anthropic": RecordingProvider("anthropic", events, paid=True), "ollama": local},
        accounting_store=ControlledAccountingStore(events, failure="exhausted"),
    ).generate(_paid_request())

    assert response.status == AI_STATUS_PROVIDER_UNAVAILABLE
    assert response.error == "Provider unavailable."
    assert response.metadata.fallback_attempted is True
    assert response.metadata.fallback_reason == AI_STATUS_BUDGET_EXHAUSTED


def test_scheduled_soc_briefing_never_enters_paid_accounting():
    events = []
    local = RecordingProvider("ollama", events)
    response = AiGateway(
        config=_gateway_config(),
        providers={"ollama": local},
        accounting_store=ControlledAccountingStore(events, failure="exhausted"),
    ).generate(
        AiGatewayRequest(
            prompt="Create a scheduled SOC briefing.",
            capability="scheduled_soc_briefing",
            profile=AI_PROFILE_DEEP_BRIEFING,
        )
    )

    assert response.status == AI_STATUS_SUCCESS
    assert events == ["provider:ollama"]
    assert response.metadata.paid_request is False


def test_status_reports_estimated_budget_usage_without_billed_cost_or_secret():
    events = []
    config = _gateway_config()
    status = get_ai_gateway_status(
        config=config,
        providers={
            "anthropic": RecordingProvider("anthropic", events, paid=True),
            "ollama": RecordingProvider("ollama", events),
        },
        accounting_store=ControlledAccountingStore(events),
    )

    assert status["budget"] == {
        "usage_day": USAGE_DAY.isoformat(),
        "daily_cap_usd": 5.0,
        "reserved_usd": 0.1,
        "settled_usd": 1.25,
        "used_usd": 1.35,
        "remaining_usd": 3.65,
        "total_input_tokens": 100,
        "total_output_tokens": 40,
        "total_tokens": 140,
        "attempt_count": 3,
        "token_usage_source": "estimated",
        "cost_source": "estimated",
        "status": "available",
    }
    assert "actual_billed" not in str(status["budget"])
    assert config.anthropic_api_key not in str(status)


def test_status_marks_anthropic_budget_blocked_when_no_budget_remains():
    events = []
    accounting = ControlledAccountingStore(events)
    original_summary = accounting.summary

    def exhausted_summary(**kwargs):
        summary = original_summary(**kwargs)
        values = summary.as_dict()
        values["used_usd"] = values["daily_cap_usd"]
        values["remaining_usd"] = 0.0

        class ExhaustedSummary:
            def as_dict(self):
                return values

        return ExhaustedSummary()

    accounting.summary = exhausted_summary
    status = get_ai_gateway_status(
        config=_gateway_config(),
        providers={
            "anthropic": RecordingProvider("anthropic", events, paid=True),
            "ollama": RecordingProvider("ollama", events),
        },
        accounting_store=accounting,
    )
    anthropic = next(row for row in status["providers"] if row["provider"] == "anthropic")

    assert status["budget"]["status"] == AI_STATUS_BUDGET_EXHAUSTED
    assert anthropic["ready"] is False
    assert anthropic["status"] == AI_STATUS_BUDGET_EXHAUSTED


def _postgres_store_factory(postgres_db, *, utc_day):
    conn, cur = postgres_db
    cur.execute("SELECT current_schema()")
    schema_name = cur.fetchone()[0]
    conn.commit()
    dsn = conn.dsn

    def connection_factory():
        worker = psycopg2.connect(dsn)
        with worker.cursor() as worker_cur:
            worker_cur.execute(
                sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema_name))
            )
        worker.commit()
        return worker

    return PostgresPaidUsageStore(connection_factory=connection_factory, utc_day=utc_day)


def _pricing(*, cap="10", input_rate="1", output_rate="1"):
    return PaidUsagePricing(
        daily_cap_usd=Decimal(cap),
        input_cost_per_million_tokens=Decimal(input_rate),
        output_cost_per_million_tokens=Decimal(output_rate),
    )


def _store_request(prompt="safe bounded prompt", **metadata):
    return AiGatewayRequest(
        prompt=prompt,
        capability="agentic_analyst_planning",
        profile=AI_PROFILE_AGENTIC_PLANNING,
        metadata=metadata,
    )


def test_postgres_concurrent_reservations_cannot_exceed_daily_cap(postgres_db):
    store = _postgres_store_factory(postgres_db, utc_day=lambda: USAGE_DAY)
    pricing = _pricing(cap="2", input_rate="1000000", output_rate="1000000")

    def reserve_once():
        try:
            return store.reserve(
                request=_store_request(prompt="a"),
                provider="anthropic",
                model="claude-test-model",
                profile=AI_PROFILE_AGENTIC_PLANNING,
                max_output_tokens=1,
                pricing=pricing,
            )
        except PaidBudgetExhausted as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _index: reserve_once(), range(2)))

    assert sum(isinstance(value, PaidUsageReservation) for value in outcomes) == 1
    assert sum(isinstance(value, PaidBudgetExhausted) for value in outcomes) == 1
    conn, cur = postgres_db
    conn.rollback()
    cur.execute(
        "SELECT reserved_usd, settled_usd FROM ai_paid_usage_days WHERE usage_day = %s",
        (USAGE_DAY,),
    )
    assert tuple(Decimal(str(value)) for value in cur.fetchone()) == (
        Decimal("2.00000000"),
        Decimal("0E-8"),
    )


def test_postgres_settlement_records_reported_and_estimated_usage_without_secrets(postgres_db):
    store = _postgres_store_factory(postgres_db, utc_day=lambda: USAGE_DAY)
    pricing = _pricing()
    secret_prompt = "secret-key-value sensitive-evidence-payload"
    reservation = store.reserve(
        request=_store_request(secret_prompt, paid_correlation_id="correlation-1"),
        provider="anthropic",
        model="claude-test-model",
        profile=AI_PROFILE_AGENTIC_PLANNING,
        max_output_tokens=100,
        pricing=pricing,
    )
    response = AiGatewayResponse(
        status=AI_STATUS_SUCCESS,
        content="bounded result",
        error=None,
        metadata=AiRequestMetadata(
            provider="anthropic",
            model="claude-test-model",
            mode=AI_MODE_AUTOMATIC_FALLBACK,
            status=AI_STATUS_SUCCESS,
            latency_ms=19,
            provider_reported_prompt_tokens=7,
            provider_reported_completion_tokens=3,
            provider_reported_total_tokens=10,
            token_usage_source="provider_reported",
            paid_request=True,
        ),
    )
    settled = store.settle(reservation, response, pricing=pricing)

    assert settled.input_tokens == 7
    assert settled.output_tokens == 3
    assert settled.token_usage_source == "provider_reported"
    assert settled.cost_source == "estimated"
    conn, cur = postgres_db
    conn.rollback()
    cur.execute(
        """
        SELECT provider, model, profile, status, input_tokens, output_tokens,
               token_usage_source, cost_source, provider_latency_ms,
               estimated_cost_usd, actual_billed_cost_usd, row_to_json(a)::text
        FROM ai_paid_request_attempts a
        WHERE attempt_id = %s
        """,
        (reservation.attempt_id,),
    )
    row = cur.fetchone()
    assert row[:9] == (
        "anthropic",
        "claude-test-model",
        AI_PROFILE_AGENTIC_PLANNING,
        AI_STATUS_SUCCESS,
        7,
        3,
        "provider_reported",
        "estimated",
        19,
    )
    assert row[9] is not None
    assert row[10] is None
    assert secret_prompt not in row[11]


@pytest.mark.parametrize("status", (AI_STATUS_PROVIDER_TIMEOUT, AI_STATUS_PROVIDER_UNAVAILABLE))
def test_postgres_failed_attempts_are_settled_with_estimated_usage(postgres_db, status):
    store = _postgres_store_factory(postgres_db, utc_day=lambda: USAGE_DAY)
    pricing = _pricing()
    reservation = store.reserve(
        request=_store_request(prompt=f"attempt-{status}"),
        provider="anthropic",
        model="claude-test-model",
        profile=AI_PROFILE_AGENTIC_PLANNING,
        max_output_tokens=100,
        pricing=pricing,
    )
    response = AiGatewayResponse(
        status=status,
        content=None,
        error="Provider failed safely.",
        metadata=AiRequestMetadata(
            provider="anthropic",
            model="claude-test-model",
            mode=AI_MODE_AUTOMATIC_FALLBACK,
            status=status,
            latency_ms=23,
            paid_request=True,
            error_code=status,
        ),
    )
    settlement = store.settle(reservation, response, pricing=pricing)

    assert settlement.token_usage_source == "estimated"
    conn, cur = postgres_db
    conn.rollback()
    cur.execute(
        "SELECT status, token_usage_source, cost_source, error_code FROM ai_paid_request_attempts WHERE attempt_id = %s",
        (reservation.attempt_id,),
    )
    assert cur.fetchone() == (status, "estimated", "estimated", status)


def test_postgres_utc_lazy_rollover_starts_a_new_daily_budget(postgres_db):
    current_day = [date(2026, 8, 4)]
    store = _postgres_store_factory(postgres_db, utc_day=lambda: current_day[0])
    pricing = _pricing(cap="2", input_rate="1000000", output_rate="1000000")
    arguments = {
        "request": _store_request(prompt="a"),
        "provider": "anthropic",
        "model": "claude-test-model",
        "profile": AI_PROFILE_AGENTIC_PLANNING,
        "max_output_tokens": 1,
        "pricing": pricing,
    }

    first = store.reserve(**arguments)
    with pytest.raises(PaidBudgetExhausted):
        store.reserve(**arguments)
    current_day[0] = date(2026, 8, 5)
    next_day = store.reserve(**arguments)

    assert first.usage_day == date(2026, 8, 4)
    assert next_day.usage_day == date(2026, 8, 5)
    conn, cur = postgres_db
    conn.rollback()
    cur.execute("SELECT usage_day, reserved_usd FROM ai_paid_usage_days ORDER BY usage_day")
    assert cur.fetchall() == [
        (date(2026, 8, 4), Decimal("2.00000000")),
        (date(2026, 8, 5), Decimal("2.00000000")),
    ]
