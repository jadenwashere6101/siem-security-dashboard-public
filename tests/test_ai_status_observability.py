from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
import json
from unittest.mock import patch

from core.ai.config import (
    AI_MODE_AUTOMATIC_FALLBACK,
    AI_MODE_LOCAL_ONLY,
    AiGatewayConfig,
    default_ai_profiles,
)
from core.ai.gateway_config_store import PostgresGatewayConfigStore
from core.ai.models import (
    AI_STATUS_CONFIGURATION_ERROR,
    AI_STATUS_PROVIDER_UNAVAILABLE,
    AI_STATUS_SUCCESS,
    AiProviderReadiness,
)
from core.ai.paid_usage_store import PaidUsagePricing, PaidUsageSummary, PostgresPaidUsageStore
from core.ai.profile_registry import (
    AI_PROFILE_AGENTIC_PLANNING,
    AI_PROFILE_DEEP_BRIEFING,
    AI_PROVIDER_ANTHROPIC,
    AI_PROVIDER_OLLAMA,
    APPROVED_AI_PROFILES,
    PROFILE_PROVIDER_ROUTING,
)
from core.ai.readiness import get_ai_gateway_status


USAGE_DAY = date(2026, 8, 4)


class StatusProvider:
    def __init__(self, provider_key, *, ready=True, status=AI_STATUS_SUCCESS, error_code=None):
        self.provider_key = provider_key
        self.ready = ready
        self.status = status
        self.error_code = error_code

    def readiness(self, config):
        return AiProviderReadiness(
            provider=self.provider_key,
            configured=self.ready,
            ready=self.ready,
            status=self.status,
            model=(config.anthropic_model if self.provider_key == AI_PROVIDER_ANTHROPIC else config.local_model),
            error_code=self.error_code,
            readiness_scope="configuration_only" if self.provider_key == AI_PROVIDER_ANTHROPIC else None,
            latency_ms=8 if self.provider_key == AI_PROVIDER_OLLAMA else None,
        )

    def supports(self, _request):
        raise AssertionError("status must not perform capability execution")

    def generate(self, *_args, **_kwargs):
        raise AssertionError("status must not perform inference")


class FailingReadinessProvider(StatusProvider):
    def __init__(self, provider_key, secret):
        super().__init__(provider_key)
        self.secret = secret

    def readiness(self, _config):
        raise RuntimeError(self.secret)


class SummaryStore:
    def __init__(self, summary=None, *, error=None):
        self._summary = summary or _summary()
        self._error = error

    def summary(self, **_kwargs):
        if self._error:
            raise self._error
        return self._summary


class ConnectionWithoutClose:
    def __init__(self, connection):
        self.connection = connection

    def cursor(self):
        return self.connection.cursor()

    def close(self):
        return None


def _config(**updates):
    model = "claude-status-model"
    profiles = default_ai_profiles(local_model="llama3.2:3b", anthropic_model=model)
    config = AiGatewayConfig(
        mode=AI_MODE_AUTOMATIC_FALLBACK,
        configured_mode=AI_MODE_AUTOMATIC_FALLBACK,
        local_provider=AI_PROVIDER_OLLAMA,
        local_base_url="http://local-provider.invalid:11434",
        local_model="llama3.2:3b",
        anthropic_enabled=True,
        anthropic_routing_enabled=True,
        anthropic_api_key="test-status-secret",
        anthropic_model=model,
        anthropic_daily_budget_usd=5.0,
        anthropic_input_cost_per_million_tokens=3.0,
        anthropic_output_cost_per_million_tokens=15.0,
        profiles=profiles,
    )
    return replace(config, **updates)


def _summary():
    return PaidUsageSummary(
        usage_day=USAGE_DAY,
        daily_cap_usd=Decimal("5"),
        reserved_usd=Decimal("0.50"),
        settled_usd=Decimal("1.25"),
        remaining_usd=Decimal("3.25"),
        total_input_tokens=120,
        total_output_tokens=50,
        total_tokens=170,
        attempt_count=4,
        token_usage_source="mixed",
        provider_reported_input_tokens=80,
        provider_reported_output_tokens=30,
        provider_reported_total_tokens=110,
        estimated_input_tokens=40,
        estimated_output_tokens=20,
        estimated_total_tokens=60,
        cost_usage_source="estimated",
        estimated_cost_usd=Decimal("1.25"),
        provider_latency_sample_count=3,
        average_provider_latency_ms=22.5,
        maximum_provider_latency_ms=31,
        attempt_status_counts={"success": 3, "provider_timeout": 1},
    )


def _providers(*, anthropic_ready=True):
    return {
        AI_PROVIDER_OLLAMA: StatusProvider(AI_PROVIDER_OLLAMA),
        AI_PROVIDER_ANTHROPIC: StatusProvider(
            AI_PROVIDER_ANTHROPIC,
            ready=anthropic_ready,
            status=AI_STATUS_SUCCESS if anthropic_ready else AI_STATUS_CONFIGURATION_ERROR,
            error_code=None if anthropic_ready else "anthropic_configuration_invalid",
        ),
    }


def test_status_reports_effective_provider_model_and_executability_for_every_profile():
    status = get_ai_gateway_status(
        config=_config(),
        providers=_providers(),
        accounting_store=SummaryStore(),
    )

    rows = {row["profile"]: row for row in status["profiles"]}
    assert set(rows) == set(APPROVED_AI_PROFILES)
    for profile_name, provider in PROFILE_PROVIDER_ROUTING.items():
        assert rows[profile_name]["provider"] == provider
        assert rows[profile_name]["model"]
        assert rows[profile_name]["executable"] is True
    assert rows[AI_PROFILE_DEEP_BRIEFING]["provider"] == AI_PROVIDER_OLLAMA
    assert rows[AI_PROFILE_DEEP_BRIEFING]["local_only"] is True
    assert rows[AI_PROFILE_DEEP_BRIEFING]["scheduled_soc_briefing_local_only"] is True


def test_anthropic_unavailability_does_not_mark_ollama_profiles_unavailable():
    status = get_ai_gateway_status(
        config=_config(anthropic_routing_enabled=False),
        providers=_providers(anthropic_ready=False),
        accounting_store=SummaryStore(),
    )
    rows = {row["profile"]: row for row in status["profiles"]}
    providers = {row["provider"]: row for row in status["providers"]}

    assert providers[AI_PROVIDER_OLLAMA]["ready"] is True
    assert providers[AI_PROVIDER_ANTHROPIC]["ready"] is False
    assert rows[AI_PROFILE_AGENTIC_PLANNING]["executable"] is False
    assert rows[AI_PROFILE_AGENTIC_PLANNING]["status"] == AI_STATUS_PROVIDER_UNAVAILABLE
    assert all(
        row["executable"] is True
        for name, row in rows.items()
        if name != AI_PROFILE_AGENTIC_PLANNING
    )


def test_required_but_unconfigured_anthropic_planning_is_explicitly_unavailable():
    config = _config(
        anthropic_enabled=False,
        anthropic_routing_enabled=False,
        anthropic_api_key="",
    )
    status = get_ai_gateway_status(
        config=config,
        providers=_providers(anthropic_ready=False),
        accounting_store=SummaryStore(),
    )
    planner = next(row for row in status["profiles"] if row["profile"] == AI_PROFILE_AGENTIC_PLANNING)

    assert planner["provider"] == AI_PROVIDER_ANTHROPIC
    assert planner["executable"] is False
    assert planner["status"] == AI_STATUS_PROVIDER_UNAVAILABLE
    assert planner["error_code"] == "anthropic_configuration_invalid"


def test_budget_and_usage_provenance_are_explicit_without_claiming_billed_cost():
    status = get_ai_gateway_status(
        config=_config(),
        providers=_providers(),
        accounting_store=SummaryStore(),
    )
    budget = status["budget"]

    assert budget["usage_day"] == "2026-08-04"
    assert budget["daily_cap_usd"] == 5.0
    assert budget["reserved_usd"] == 0.5
    assert budget["settled_usd"] == 1.25
    assert budget["remaining_usd"] == 3.25
    assert budget["accounting_status"] == "available"
    assert budget["reserved_usage"]["source"] == "estimated"
    assert budget["settled_usage"]["source"] == "estimated"
    assert budget["token_usage"]["provider_reported"]["source"] == "provider_reported"
    assert budget["token_usage"]["estimated"]["source"] == "estimated"
    assert budget["cost_usage"] == {
        "provider_reported": {"amount_usd": 0.0, "source": "provider_reported"},
        "estimated": {"amount_usd": 1.25, "source": "estimated"},
    }
    assert "actual_billed_usage" not in budget
    assert budget["provider_latency"] == {
        "sample_count": 3,
        "average_ms": 22.5,
        "maximum_ms": 31,
    }
    assert budget["attempt_status_counts"] == {"success": 3, "provider_timeout": 1}


def test_accounting_failure_is_sanitized_and_only_paid_profile_fails_closed(caplog):
    secret = "secret-prompt-and-endpoint-value"
    status = get_ai_gateway_status(
        config=_config(),
        providers=_providers(),
        accounting_store=SummaryStore(error=RuntimeError(secret)),
    )
    rows = {row["profile"]: row for row in status["profiles"]}

    assert status["status"] == "degraded"
    assert status["budget"]["status"] == "accounting_unavailable"
    assert status["budget"]["reserved_usd"] is None
    assert rows[AI_PROFILE_AGENTIC_PLANNING]["executable"] is False
    assert rows[AI_PROFILE_DEEP_BRIEFING]["executable"] is True
    assert secret not in json.dumps(status, sort_keys=True)
    assert secret not in caplog.text


def test_runtime_configuration_failure_reports_unknown_accounting_without_harming_local_profiles():
    config = _config(
        mode=AI_MODE_LOCAL_ONLY,
        configured_mode=AI_MODE_LOCAL_ONLY,
        anthropic_routing_enabled=False,
        runtime_config_status="unavailable",
        runtime_config_error_code="runtime_config_unavailable",
    )
    status = get_ai_gateway_status(
        config=config,
        providers=_providers(),
        accounting_store=SummaryStore(),
    )
    rows = {row["profile"]: row for row in status["profiles"]}

    assert status["status"] == "degraded"
    assert status["runtime_configuration"]["status"] == "unavailable"
    assert status["budget"]["status"] == "configuration_unavailable"
    assert status["budget"]["daily_cap_usd"] is None
    assert status["budget"]["remaining_usd"] is None
    assert rows[AI_PROFILE_DEEP_BRIEFING]["executable"] is True
    assert rows[AI_PROFILE_AGENTIC_PLANNING]["executable"] is False


def test_credential_bearing_readiness_failure_is_redacted_from_status_and_logs(caplog):
    secret = "Bearer secret-key https://sensitive-provider.invalid prompt evidence response"
    status = get_ai_gateway_status(
        config=_config(),
        providers={
            AI_PROVIDER_OLLAMA: StatusProvider(AI_PROVIDER_OLLAMA),
            AI_PROVIDER_ANTHROPIC: FailingReadinessProvider(AI_PROVIDER_ANTHROPIC, secret),
        },
        accounting_store=SummaryStore(),
    )
    rendered = json.dumps(status, sort_keys=True)

    assert secret not in rendered
    assert "sensitive-provider.invalid" not in rendered
    assert secret not in caplog.text
    anthropic = next(row for row in status["providers"] if row["provider"] == AI_PROVIDER_ANTHROPIC)
    assert anthropic["status"] == AI_STATUS_PROVIDER_UNAVAILABLE
    assert anthropic["error_code"] == "anthropic_readiness_unavailable"


def test_runtime_policy_change_appears_on_next_status_read_without_restart(postgres_db):
    conn, cur = postgres_db
    source = _config()
    store = PostgresGatewayConfigStore(
        connection_factory=lambda: ConnectionWithoutClose(conn)
    )
    with patch("core.ai.readiness.load_ai_gateway_config", return_value=source):
        first = get_ai_gateway_status(
            runtime_config_store=store,
            providers=_providers(),
            accounting_store=SummaryStore(),
        )
        assert first["gateway"]["mode"] == AI_MODE_AUTOMATIC_FALLBACK

        store.stage_update(
            cur,
            source_config=source,
            updates={"gateway_mode": AI_MODE_LOCAL_ONLY},
            updated_by="statusadmin",
        )
        conn.commit()
        second = get_ai_gateway_status(
            runtime_config_store=store,
            providers=_providers(),
            accounting_store=SummaryStore(),
        )

    assert second["gateway"]["mode"] == AI_MODE_LOCAL_ONLY
    assert second["runtime_configuration"]["updated_by"] == "statusadmin"
    planner = next(row for row in second["profiles"] if row["profile"] == AI_PROFILE_AGENTIC_PLANNING)
    assert planner["executable"] is False


def test_postgres_summary_separates_reported_estimated_and_actual_billed_usage(postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO ai_paid_usage_days (usage_day, daily_cap_usd, reserved_usd, settled_usd)
        VALUES (%s, 5, 0.50, 1.25)
        """,
        (USAGE_DAY,),
    )
    attempts = [
        ("reported", "success", 80, 30, 110, "provider_reported", 20),
        ("estimated", "provider_timeout", 40, 20, 60, "estimated", 30),
    ]
    for attempt_id, status, input_tokens, output_tokens, total_tokens, source, latency in attempts:
        cur.execute(
            """
            INSERT INTO ai_paid_request_attempts (
                attempt_id, usage_day, provider, model, profile, attempt_kind,
                status, reserved_cost_usd, settled_cost_usd, estimated_cost_usd,
                input_tokens, output_tokens, total_tokens, token_usage_source,
                cost_source, provider_latency_ms
            ) VALUES (%s, %s, 'anthropic', 'claude-status-model', 'agentic_planning',
                      'initial', %s, 0, 0.25, 0.25, %s, %s, %s, %s, 'estimated', %s)
            """,
            (attempt_id, USAGE_DAY, status, input_tokens, output_tokens, total_tokens, source, latency),
        )
    conn.commit()
    store = PostgresPaidUsageStore(
        connection_factory=lambda: ConnectionWithoutClose(conn),
        utc_day=lambda: USAGE_DAY,
    )
    summary = store.summary(
        pricing=PaidUsagePricing(Decimal("5"), Decimal("3"), Decimal("15"))
    ).as_dict()

    assert summary["token_usage"]["provider_reported"]["total_tokens"] == 110
    assert summary["token_usage"]["estimated"]["total_tokens"] == 60
    assert summary["token_usage_source"] == "mixed"
    assert summary["cost_usage"]["estimated"] == {
        "amount_usd": 0.5,
        "source": "estimated",
    }
    assert summary["provider_latency"] == {
        "sample_count": 2,
        "average_ms": 25.0,
        "maximum_ms": 30,
    }
    assert summary["attempt_status_counts"] == {"provider_timeout": 1, "success": 1}
    assert "actual_billed_usage" not in summary

    cur.execute(
        """
        UPDATE ai_paid_request_attempts
        SET actual_billed_cost_usd = 0.20
        WHERE attempt_id = 'reported'
        """
    )
    conn.commit()
    with_billed = store.summary(
        pricing=PaidUsagePricing(Decimal("5"), Decimal("3"), Decimal("15"))
    ).as_dict()
    assert with_billed["actual_billed_usage"] == {
        "amount_usd": 0.2,
        "attempt_count": 1,
        "source": "actual_billed",
    }


def test_route_unexpected_failure_returns_sanitized_degraded_status(client, mock_db):
    client.post("/login", json={"username": "testadmin", "password": "testpassword123!"})
    secret = "secret-provider-response"
    with patch("routes.ai_routes.get_ai_gateway_status", side_effect=RuntimeError(secret)):
        response = client.get("/ai/status")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "degraded"
    assert payload["read_only"] is True
    assert secret not in json.dumps(payload, sort_keys=True)
