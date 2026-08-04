from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import date
from decimal import Decimal
import json
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

from core.ai.config import (
    AI_MODE_AUTOMATIC_FALLBACK,
    AI_MODE_DISABLED,
    AI_MODE_LOCAL_ONLY,
    AiGatewayConfig,
    default_ai_profiles,
)
from core.ai.gateway import AiGateway
from core.ai.gateway_config_store import (
    GatewayConfigValidationError,
    PostgresGatewayConfigStore,
    validate_gateway_config_updates,
)
from core.ai.models import (
    AI_STATUS_FALLBACK_BLOCKED,
    AI_STATUS_SUCCESS,
    AiCapabilityResult,
    AiGatewayRequest,
    AiGatewayResponse,
    AiProviderReadiness,
    AiRequestMetadata,
)
from core.ai.paid_usage_store import PaidUsageReservation, PaidUsageSettlement
from core.ai.paid_usage_store import (
    PaidAccountingConfigurationError,
    PostgresPaidUsageStore,
    pricing_from_config,
)
from core.ai.profile_registry import AI_PROFILE_AGENTIC_PLANNING


class RouteSafeConnection:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return self._conn.cursor()

    def close(self):
        return None

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()


class RecordingProvider:
    provider_key = "anthropic"

    def __init__(self):
        self.calls = []

    def supports(self, _request):
        return AiCapabilityResult(True, AI_STATUS_SUCCESS)

    def readiness(self, config):
        return AiProviderReadiness(
            provider=self.provider_key,
            configured=True,
            ready=True,
            status=AI_STATUS_SUCCESS,
            model=config.anthropic_model,
        )

    def generate(self, request, config):
        profile = config.profile(request.profile)
        self.calls.append((request, profile.model))
        return AiGatewayResponse(
            status=AI_STATUS_SUCCESS,
            content="ok",
            error=None,
            metadata=AiRequestMetadata(
                provider="anthropic",
                model=profile.model,
                mode=config.mode,
                status=AI_STATUS_SUCCESS,
                latency_ms=4,
                paid_request=True,
                profile=profile.name,
            ),
        )


class AllowingAccountingStore:
    def __init__(self):
        self.attempts = 0
        self.daily_caps = []

    def reserve(self, **kwargs):
        self.attempts += 1
        self.daily_caps.append(kwargs["pricing"].daily_cap_usd)
        return PaidUsageReservation(
            attempt_id=f"runtime-attempt-{self.attempts}",
            usage_day=date(2026, 8, 4),
            reserved_cost_usd=Decimal("0.10"),
            remaining_usd=Decimal("9.90"),
            estimated_input_tokens=10,
            estimated_output_tokens=20,
            correlation_id=None,
            attempt_kind="initial",
        )

    def settle(self, reservation, _response, **_kwargs):
        return PaidUsageSettlement(
            attempt_id=reservation.attempt_id,
            usage_day=reservation.usage_day,
            charged_cost_usd=Decimal("0.10"),
            remaining_usd=Decimal("9.90"),
            input_tokens=10,
            output_tokens=20,
            total_tokens=30,
            token_usage_source="estimated",
            cost_source="estimated",
        )


class StatusAccountingStore:
    def summary(self, **_kwargs):
        class Summary:
            def as_dict(self):
                return {
                    "usage_day": "2026-08-04",
                    "daily_cap_usd": 12.0,
                    "reserved_usd": 0.0,
                    "settled_usd": 1.0,
                    "used_usd": 1.0,
                    "remaining_usd": 11.0,
                    "total_input_tokens": 10,
                    "total_output_tokens": 5,
                    "total_tokens": 15,
                    "attempt_count": 1,
                    "token_usage_source": "provider_reported",
                    "cost_source": "estimated",
                }

        return Summary()


def _source_config(**overrides):
    model = "claude-source-model"
    base = AiGatewayConfig(
        mode=AI_MODE_DISABLED,
        configured_mode=AI_MODE_DISABLED,
        local_provider="ollama",
        local_base_url="http://127.0.0.1:11434",
        local_model="llama3.2:3b",
        anthropic_enabled=True,
        anthropic_api_key="test-key-never-return",
        anthropic_model=model,
        anthropic_daily_budget_usd=5.0,
        anthropic_input_cost_per_million_tokens=3.0,
        anthropic_output_cost_per_million_tokens=15.0,
        profiles=default_ai_profiles(local_model="llama3.2:3b", anthropic_model=model),
    )
    return replace(base, **overrides)


def _store(conn):
    wrapper = RouteSafeConnection(conn)
    return PostgresGatewayConfigStore(connection_factory=lambda: wrapper)


def _planner_request():
    return AiGatewayRequest(
        prompt="Plan this bounded read-only turn.",
        capability="agentic_analyst_planning",
        profile=AI_PROFILE_AGENTIC_PLANNING,
    )


@contextmanager
def _patched_route_db(conn):
    wrapper = RouteSafeConnection(conn)
    with patch("routes.admin_routes.get_db_connection", return_value=wrapper), patch(
        "core.audit_helpers.get_db_connection", return_value=wrapper
    ), patch("core.ai.gateway_config_store.get_db_connection", return_value=wrapper):
        yield


def _login_super_admin(client):
    response = client.post("/login", json={"username": "testadmin", "password": "testpassword123!"})
    assert response.status_code == 200


def test_default_runtime_configuration_uses_valid_source_policy(postgres_db):
    conn, _cur = postgres_db
    effective = _store(conn).resolve(_source_config())

    assert effective.mode == AI_MODE_DISABLED
    assert effective.anthropic_model == "claude-source-model"
    assert effective.anthropic_daily_budget_usd == 5.0
    assert effective.anthropic_routing_enabled is False
    assert effective.runtime_config_status == "default"
    assert effective.runtime_config_updated_at is None


def test_runtime_changes_apply_to_next_gateway_request_without_restart(postgres_db):
    conn, cur = postgres_db
    source = _source_config()
    store = _store(conn)
    provider = RecordingProvider()
    accounting = AllowingAccountingStore()
    gateway = AiGateway(
        config=source,
        providers={"anthropic": provider},
        accounting_store=accounting,
        runtime_config_store=store,
    )

    first = gateway.generate(_planner_request())
    assert first.status == "disabled"

    store.stage_update(
        cur,
        source_config=source,
        updates={
            "gateway_mode": AI_MODE_AUTOMATIC_FALLBACK,
            "preferred_anthropic_model": "claude-runtime-model",
            "daily_paid_budget_usd": 10,
            "anthropic_routing_enabled": True,
        },
        updated_by="testadmin",
    )
    conn.commit()

    second = gateway.generate(_planner_request())
    assert second.status == AI_STATUS_SUCCESS
    assert second.metadata.model == "claude-runtime-model"
    assert provider.calls[-1][1] == "claude-runtime-model"
    assert accounting.daily_caps[-1] == Decimal("10.0")

    store.stage_update(
        cur,
        source_config=source,
        updates={"daily_paid_budget_usd": 1},
        updated_by="testadmin",
    )
    conn.commit()
    reduced = gateway.generate(_planner_request())
    assert reduced.status == AI_STATUS_SUCCESS
    assert accounting.daily_caps[-1] == Decimal("1.0")

    store.stage_update(
        cur,
        source_config=source,
        updates={"gateway_mode": AI_MODE_LOCAL_ONLY},
        updated_by="testadmin",
    )
    conn.commit()
    third = gateway.generate(_planner_request())

    assert third.status == AI_STATUS_FALLBACK_BLOCKED
    assert len(provider.calls) == 2


def test_reservation_rechecks_runtime_policy_and_applies_reduced_cap(postgres_db):
    conn, cur = postgres_db
    wrapper = RouteSafeConnection(conn)
    source = _source_config()
    runtime_store = _store(conn)
    runtime_store.stage_update(
        cur,
        source_config=source,
        updates={
            "gateway_mode": AI_MODE_AUTOMATIC_FALLBACK,
            "preferred_anthropic_model": "claude-runtime-model",
            "daily_paid_budget_usd": 10,
            "anthropic_routing_enabled": True,
        },
        updated_by="testadmin",
    )
    conn.commit()
    stale_config = runtime_store.resolve(source)
    stale_pricing = pricing_from_config(stale_config)

    runtime_store.stage_update(
        cur,
        source_config=source,
        updates={"daily_paid_budget_usd": 1},
        updated_by="testadmin",
    )
    conn.commit()
    paid_store = PostgresPaidUsageStore(
        connection_factory=lambda: wrapper,
        utc_day=lambda: date(2026, 8, 4),
    )

    with pytest.raises(PaidAccountingConfigurationError):
        paid_store.reserve(
            request=_planner_request(),
            provider="anthropic",
            model="claude-runtime-model",
            profile=AI_PROFILE_AGENTIC_PLANNING,
            max_output_tokens=1024,
            pricing=stale_pricing,
        )

    current_config = runtime_store.resolve(source)
    reservation = paid_store.reserve(
        request=_planner_request(),
        provider="anthropic",
        model="claude-runtime-model",
        profile=AI_PROFILE_AGENTIC_PLANNING,
        max_output_tokens=1024,
        pricing=pricing_from_config(current_config),
    )
    assert reservation.reserved_cost_usd < Decimal("1")
    cur.execute(
        "SELECT daily_cap_usd FROM ai_paid_usage_days WHERE usage_day = %s",
        (date(2026, 8, 4),),
    )
    assert cur.fetchone()[0] == Decimal("1.00000000")


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"gateway_mode": "hybrid"},
        {"anthropic_routing_enabled": "yes"},
        {"daily_paid_budget_usd": -1},
        {"preferred_anthropic_model": "invalid model"},
        {"api_key": "must-never-persist"},
        {"prompt": "sensitive evidence"},
    ],
)
def test_invalid_runtime_configuration_is_rejected(payload):
    with pytest.raises(GatewayConfigValidationError):
        validate_gateway_config_updates(payload)
        current = {
            "gateway_mode": AI_MODE_DISABLED,
            "preferred_anthropic_model": "",
            "daily_paid_budget_usd": 0,
            "anthropic_routing_enabled": False,
        }
        from core.ai.gateway_config_store import validate_gateway_policy

        validate_gateway_policy({**current, **payload})


def test_missing_configuration_store_fails_closed_to_local_only():
    def unavailable():
        raise RuntimeError("database unavailable")

    effective = PostgresGatewayConfigStore(connection_factory=unavailable).resolve(
        _source_config(
            mode=AI_MODE_AUTOMATIC_FALLBACK,
            configured_mode=AI_MODE_AUTOMATIC_FALLBACK,
            anthropic_routing_enabled=True,
        )
    )

    assert effective.mode == AI_MODE_LOCAL_ONLY
    assert effective.anthropic_routing_enabled is False
    assert effective.runtime_config_status == "unavailable"
    assert effective.runtime_config_error_code == "runtime_config_unavailable"


def test_missing_store_fails_closed_to_disabled_when_local_defaults_are_invalid():
    def unavailable():
        raise RuntimeError("database unavailable")

    effective = PostgresGatewayConfigStore(connection_factory=unavailable).resolve(
        _source_config(local_provider="unknown")
    )

    assert effective.mode == AI_MODE_DISABLED
    assert effective.anthropic_routing_enabled is False


def test_invalid_stored_configuration_fails_closed_to_local_only(postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO ai_gateway_config (
            id, gateway_mode, preferred_anthropic_model,
            daily_paid_budget_usd, anthropic_routing_enabled
        )
        VALUES (1, 'automatic_fallback', 'invalid model', 5, FALSE)
        """
    )
    conn.commit()

    effective = _store(conn).resolve(_source_config())

    assert effective.mode == AI_MODE_LOCAL_ONLY
    assert effective.anthropic_routing_enabled is False
    assert effective.runtime_config_status == "invalid"


def test_ai_gateway_config_routes_require_super_admin(client, mock_db):
    assert client.get("/admin/ai-gateway-config").status_code == 401
    assert client.patch("/admin/ai-gateway-config", json={"gateway_mode": "disabled"}).status_code == 401

    analyst = {
        "username": "runtime_analyst",
        "password_hash": generate_password_hash("analystpass", method="pbkdf2:sha256"),
        "role": "analyst",
        "is_active": True,
    }
    with patch("routes.auth_routes.get_user_by_username", return_value=analyst), patch(
        "core.auth.get_user_by_username", return_value=analyst
    ), patch("core.auth.log_audit_event") as audit:
        login = client.post("/login", json={"username": analyst["username"], "password": "analystpass"})
        assert login.status_code == 200
        assert client.get("/admin/ai-gateway-config").status_code == 403
        denied = client.patch("/admin/ai-gateway-config", json={"gateway_mode": "disabled"})
        assert denied.status_code == 403
    assert audit.call_count == 2
    assert all(call.args[0] == "rbac_deny" for call in audit.call_args_list)
    assert all(call.kwargs["actor_username"] == "runtime_analyst" for call in audit.call_args_list)


def test_super_admin_patch_is_immediate_and_audited(client, postgres_db):
    conn, cur = postgres_db
    _login_super_admin(client)
    with _patched_route_db(conn):
        initial = client.get("/admin/ai-gateway-config")
        assert initial.status_code == 200
        assert initial.get_json()["status"] == "default"

        updated = client.patch(
            "/admin/ai-gateway-config",
            json={
                "gateway_mode": AI_MODE_AUTOMATIC_FALLBACK,
                "preferred_anthropic_model": "claude-admin-model",
                "daily_paid_budget_usd": 12,
                "anthropic_routing_enabled": True,
            },
        )
        immediate = client.get("/admin/ai-gateway-config")

    assert updated.status_code == 200
    assert updated.get_json()["configuration"]["anthropic_routing_enabled"] is True
    assert updated.get_json()["updated_by"] == "admin"
    assert updated.get_json()["updated_at"] is not None
    assert immediate.get_json()["configuration"]["preferred_anthropic_model"] == "claude-admin-model"
    cur.execute(
        """
        SELECT actor_username, actor_role, http_method, request_path,
               details, created_at
        FROM audit_log
        WHERE event_type = 'ai_gateway_config_updated'
        ORDER BY id DESC LIMIT 1
        """
    )
    audit = cur.fetchone()
    assert audit[:4] == (
        "admin",
        "super_admin",
        "PATCH",
        "/admin/ai-gateway-config",
    )
    assert audit[4]["outcome"] == "success"
    assert audit[4]["old"]["gateway_mode"] == AI_MODE_DISABLED
    assert audit[4]["new"]["preferred_anthropic_model"] == "claude-admin-model"
    assert audit[5] is not None


def test_invalid_admin_update_is_audited_without_secret_value(client, postgres_db):
    conn, cur = postgres_db
    secret = "secret-key-must-not-appear"
    _login_super_admin(client)
    with _patched_route_db(conn):
        response = client.patch("/admin/ai-gateway-config", json={"api_key": secret})

    assert response.status_code == 400
    cur.execute(
        "SELECT details FROM audit_log WHERE event_type = 'ai_gateway_config_update_rejected' ORDER BY id DESC LIMIT 1"
    )
    rendered = json.dumps(cur.fetchone()[0], sort_keys=True)
    assert secret not in rendered
    assert "api_key" not in rendered
    cur.execute("SELECT COUNT(*) FROM ai_gateway_config")
    assert cur.fetchone()[0] == 0


def test_ai_status_exposes_effective_runtime_config_without_secrets(client, postgres_db):
    conn, cur = postgres_db
    source = _source_config()
    cur.execute(
        """
        INSERT INTO ai_gateway_config (
            id, gateway_mode, preferred_anthropic_model,
            daily_paid_budget_usd, anthropic_routing_enabled, updated_by
        )
        VALUES (1, 'automatic_fallback', 'claude-status-model', 12, TRUE, 'testadmin')
        """
    )
    conn.commit()
    _login_super_admin(client)
    wrapper = RouteSafeConnection(conn)
    with patch("core.ai.readiness.load_ai_gateway_config", return_value=source), patch(
        "core.ai.gateway_config_store.get_db_connection", return_value=wrapper
    ), patch("core.ai.readiness.PostgresPaidUsageStore", return_value=StatusAccountingStore()), patch(
        "core.ai.providers._http_json", return_value={"models": []}
    ):
        response = client.get("/ai/status")

    assert response.status_code == 200
    payload = response.get_json()
    runtime = payload["runtime_configuration"]
    assert runtime["status"] == "applied"
    assert runtime["effective"]["gateway_mode"] == AI_MODE_AUTOMATIC_FALLBACK
    assert runtime["effective"]["preferred_anthropic_model"] == "claude-status-model"
    assert runtime["effective"]["anthropic_routing_enabled"] is True
    assert payload["budget"]["daily_cap_usd"] == 12.0
    rendered = json.dumps(payload, sort_keys=True)
    assert source.anthropic_api_key not in rendered
    assert source.local_base_url not in rendered
    assert "prompt" not in payload["runtime_configuration"]
