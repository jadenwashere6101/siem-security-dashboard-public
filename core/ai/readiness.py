from __future__ import annotations

import logging

from core.ai.config import (
    AI_MODE_ASK_BEFORE_PAID_FALLBACK,
    AI_MODE_AUTOMATIC_FALLBACK,
    AI_MODE_DISABLED,
    AI_MODE_LOCAL_ONLY,
    AiGatewayConfig,
    load_ai_gateway_config,
)
from core.ai.gateway_config_store import PostgresGatewayConfigStore, runtime_config_view
from core.ai.models import (
    AI_STATUS_ACCOUNTING_UNAVAILABLE,
    AI_STATUS_BUDGET_EXHAUSTED,
    AI_STATUS_CONFIGURATION_ERROR,
    AI_STATUS_DISABLED,
    AI_STATUS_FALLBACK_BLOCKED,
    AI_STATUS_FALLBACK_REQUIRES_CONFIRMATION,
    AI_STATUS_PROVIDER_UNAVAILABLE,
    AI_STATUS_SUCCESS,
)
from core.ai.paid_usage_store import PostgresPaidUsageStore, pricing_from_config
from core.ai.profile_registry import (
    AI_PROFILE_AGENTIC_PLANNING,
    AI_PROFILE_DEEP_BRIEFING,
    AI_PROVIDER_ANTHROPIC,
    AI_PROVIDER_OLLAMA,
    APPROVED_AI_PROFILES,
    PROFILE_PROVIDER_ROUTING,
)
from core.ai.providers import AiProvider, build_default_providers


_LOGGER = logging.getLogger(__name__)
_FAIL_CLOSED_RUNTIME_STATES = frozenset({"invalid", "unavailable"})


def get_ai_gateway_status(
    *,
    config: AiGatewayConfig | None = None,
    providers: dict[str, AiProvider] | None = None,
    accounting_store: PostgresPaidUsageStore | None = None,
    runtime_config_store: PostgresGatewayConfigStore | None = None,
) -> dict[str, object]:
    try:
        resolved_config = _resolve_config(config, runtime_config_store)
    except Exception as error:
        _log_status_failure("configuration", error)
        return degraded_ai_gateway_status(error_code="status_configuration_unavailable")

    try:
        resolved_providers = providers if providers is not None else build_default_providers()
    except Exception as error:
        _log_status_failure("provider_registry", error)
        resolved_providers = {}

    provider_rows = _provider_readiness_rows(resolved_config, resolved_providers)
    budget = _budget_status(resolved_config, accounting_store)
    profile_rows = _profile_status_rows(resolved_config, provider_rows, budget)
    overall_status = _overall_status(resolved_config, profile_rows, budget)

    return {
        "status": overall_status,
        "gateway": resolved_config.sanitized(),
        "runtime_configuration": runtime_config_view(resolved_config),
        "providers": provider_rows,
        "profiles": profile_rows,
        "budget": budget,
        "read_only": True,
        "on_demand_only": True,
    }


def degraded_ai_gateway_status(*, error_code: str = "status_unavailable") -> dict[str, object]:
    provider_rows = [
        _unavailable_provider_row(AI_PROVIDER_OLLAMA, error_code=error_code),
        _unavailable_provider_row(AI_PROVIDER_ANTHROPIC, error_code=error_code),
    ]
    profiles = [
        {
            "profile": profile_name,
            "provider": PROFILE_PROVIDER_ROUTING[profile_name],
            "model": None,
            "task_category": None,
            "local_only": PROFILE_PROVIDER_ROUTING[profile_name] == AI_PROVIDER_OLLAMA,
            "paid_fallback_enabled": profile_name == AI_PROFILE_AGENTIC_PLANNING,
            "executable": False,
            "status": AI_STATUS_CONFIGURATION_ERROR,
            "error_code": error_code,
            "provider_ready": False,
            "provider_status": AI_STATUS_PROVIDER_UNAVAILABLE,
            "scheduled_soc_briefing_local_only": profile_name == AI_PROFILE_DEEP_BRIEFING,
        }
        for profile_name in sorted(APPROVED_AI_PROFILES)
    ]
    return {
        "status": "degraded",
        "gateway": {
            "mode": AI_MODE_DISABLED,
            "configured_mode": None,
            "mode_valid": False,
            "anthropic_routing_enabled": False,
        },
        "runtime_configuration": {
            "status": "unavailable",
            "error_code": error_code,
            "configuration": None,
            "effective": {
                "gateway_mode": AI_MODE_DISABLED,
                "preferred_anthropic_model": None,
                "daily_paid_budget_usd": None,
                "anthropic_routing_enabled": False,
            },
            "updated_by": None,
            "updated_at": None,
        },
        "providers": provider_rows,
        "profiles": profiles,
        "budget": _unavailable_budget("accounting_unavailable", daily_cap_usd=None),
        "read_only": True,
        "on_demand_only": True,
    }


def _resolve_config(
    config: AiGatewayConfig | None,
    runtime_config_store: PostgresGatewayConfigStore | None,
) -> AiGatewayConfig:
    if config is not None:
        return config
    source_config = load_ai_gateway_config()
    return (runtime_config_store or PostgresGatewayConfigStore()).resolve(source_config)


def _provider_readiness_rows(
    config: AiGatewayConfig,
    providers: dict[str, AiProvider],
) -> list[dict[str, object]]:
    keys = [AI_PROVIDER_OLLAMA, AI_PROVIDER_ANTHROPIC]
    for key in (config.local_provider, config.paid_provider):
        if key and key not in keys:
            keys.append(key)

    rows = []
    for key in keys:
        provider = providers.get(key)
        if provider is None:
            model = (
                config.anthropic_model
                if key == AI_PROVIDER_ANTHROPIC
                else config.local_model
            )
            rows.append(
                _unavailable_provider_row(
                    key,
                    model=model or None,
                    error_code=f"{key}_provider_not_registered",
                )
            )
            continue
        try:
            rows.append(provider.readiness(config).as_dict())
        except Exception as error:
            _log_status_failure(f"provider_readiness:{key}", error)
            model = (
                config.anthropic_model
                if key == AI_PROVIDER_ANTHROPIC
                else config.local_model
            )
            rows.append(
                _unavailable_provider_row(
                    key,
                    model=model or None,
                    error_code=f"{key}_readiness_unavailable",
                )
            )
    return rows


def _unavailable_provider_row(
    provider: str,
    *,
    model: str | None = None,
    error_code: str,
) -> dict[str, object]:
    return {
        "provider": provider,
        "configured": False,
        "ready": False,
        "status": AI_STATUS_PROVIDER_UNAVAILABLE,
        "model": model,
        "missing_env_vars": [],
        "credential_env_vars": [],
        "credential_configured": {},
        "error_code": error_code,
        "profile": None,
        "readiness_scope": None,
        "latency_ms": None,
    }


def _budget_status(
    config: AiGatewayConfig,
    accounting_store: PostgresPaidUsageStore | None,
) -> dict[str, object]:
    if config.runtime_config_status in _FAIL_CLOSED_RUNTIME_STATES:
        return _unavailable_budget(
            "configuration_unavailable",
            daily_cap_usd=None,
            error_code=config.runtime_config_error_code or "runtime_config_unavailable",
        )
    if not config.anthropic_budget_configured:
        return {
            **_empty_budget(daily_cap_usd=config.anthropic_daily_budget_usd),
            "status": "not_configured",
            "accounting_status": "not_configured",
        }
    try:
        store = accounting_store or PostgresPaidUsageStore()
        budget = store.summary(pricing=pricing_from_config(config)).as_dict()
        budget["status"] = "available"
        budget["accounting_status"] = "available"
        if float(budget["remaining_usd"]) <= 0:
            budget["status"] = AI_STATUS_BUDGET_EXHAUSTED
        return budget
    except Exception as error:
        _log_status_failure("accounting", error)
        return _unavailable_budget(
            "accounting_unavailable",
            daily_cap_usd=config.anthropic_daily_budget_usd,
            error_code=AI_STATUS_ACCOUNTING_UNAVAILABLE,
        )


def _empty_budget(*, daily_cap_usd: float | None) -> dict[str, object]:
    return {
        "usage_day": None,
        "daily_cap_usd": daily_cap_usd,
        "reserved_usd": 0.0,
        "settled_usd": 0.0,
        "used_usd": 0.0,
        "remaining_usd": 0.0,
        "attempt_count": 0,
        "token_usage_source": "estimated",
        "cost_source": "estimated",
        "reserved_usage": {"amount_usd": 0.0, "source": "estimated"},
        "settled_usage": {"amount_usd": 0.0, "source": "estimated"},
        "token_usage": {
            "provider_reported": {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "source": "provider_reported",
            },
            "estimated": {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "source": "estimated",
            },
        },
        "cost_usage": {
            "provider_reported": {"amount_usd": 0.0, "source": "provider_reported"},
            "estimated": {"amount_usd": 0.0, "source": "estimated"},
        },
        "provider_latency": {"sample_count": 0, "average_ms": None, "maximum_ms": None},
        "attempt_status_counts": {},
    }


def _unavailable_budget(
    status: str,
    *,
    daily_cap_usd: float | None,
    error_code: str | None = None,
) -> dict[str, object]:
    return {
        "status": status,
        "accounting_status": status,
        "error_code": error_code,
        "usage_day": None,
        "daily_cap_usd": daily_cap_usd,
        "reserved_usd": None,
        "settled_usd": None,
        "used_usd": None,
        "remaining_usd": None,
        "attempt_count": None,
        "token_usage_source": None,
        "cost_source": None,
        "reserved_usage": None,
        "settled_usage": None,
        "token_usage": None,
        "cost_usage": None,
        "provider_latency": None,
        "attempt_status_counts": None,
    }


def _profile_status_rows(
    config: AiGatewayConfig,
    provider_rows: list[dict[str, object]],
    budget: dict[str, object],
) -> list[dict[str, object]]:
    readiness_by_provider = {str(row.get("provider")): row for row in provider_rows}
    rows = []
    for profile_name in sorted(APPROVED_AI_PROFILES):
        profile = config.profile(profile_name)
        readiness = readiness_by_provider.get(profile.provider) or _unavailable_provider_row(
            profile.provider,
            model=profile.model or None,
            error_code="profile_provider_readiness_unavailable",
        )
        executable, status, error_code = _profile_execution_state(
            config,
            profile,
            readiness,
            budget,
        )
        rows.append(
            {
                "profile": profile.name,
                "provider": profile.provider,
                "model": profile.model or None,
                "task_category": profile.task_category,
                "local_only": profile.local_only,
                "paid_fallback_enabled": profile.paid_fallback_enabled,
                "executable": executable,
                "status": status,
                "error_code": error_code,
                "provider_ready": bool(readiness.get("ready")),
                "provider_status": readiness.get("status"),
                "scheduled_soc_briefing_local_only": (
                    profile.name == AI_PROFILE_DEEP_BRIEFING
                    and profile.provider == AI_PROVIDER_OLLAMA
                    and profile.local_only
                    and not profile.paid_fallback_enabled
                ),
            }
        )
    return rows


def _profile_execution_state(config, profile, readiness, budget):
    if config.mode == AI_MODE_DISABLED:
        return False, AI_STATUS_DISABLED, AI_STATUS_DISABLED

    if profile.provider == AI_PROVIDER_OLLAMA:
        if (
            config.local_provider != AI_PROVIDER_OLLAMA
            or not config.local_configured
            or not profile.model
        ):
            return False, AI_STATUS_PROVIDER_UNAVAILABLE, "local_provider_not_configured"
        if not readiness.get("ready"):
            return (
                False,
                str(readiness.get("status") or AI_STATUS_PROVIDER_UNAVAILABLE),
                readiness.get("error_code"),
            )
        return True, AI_STATUS_SUCCESS, None

    if profile.provider != AI_PROVIDER_ANTHROPIC:
        return False, AI_STATUS_CONFIGURATION_ERROR, "profile_provider_not_registered"
    if config.mode == AI_MODE_LOCAL_ONLY:
        return False, AI_STATUS_FALLBACK_BLOCKED, "profile_provider_blocked_by_mode"
    if config.mode == AI_MODE_ASK_BEFORE_PAID_FALLBACK:
        return (
            False,
            AI_STATUS_FALLBACK_REQUIRES_CONFIRMATION,
            AI_STATUS_FALLBACK_REQUIRES_CONFIRMATION,
        )
    if config.mode != AI_MODE_AUTOMATIC_FALLBACK:
        return False, AI_STATUS_CONFIGURATION_ERROR, AI_STATUS_CONFIGURATION_ERROR
    if not readiness.get("ready"):
        return (
            False,
            AI_STATUS_PROVIDER_UNAVAILABLE,
            readiness.get("error_code") or "anthropic_configuration_invalid",
        )
    if not config.anthropic_routing_enabled:
        return False, AI_STATUS_FALLBACK_BLOCKED, config.runtime_config_error_code or "anthropic_routing_not_enabled"
    if budget.get("status") == AI_STATUS_BUDGET_EXHAUSTED:
        return False, AI_STATUS_BUDGET_EXHAUSTED, AI_STATUS_BUDGET_EXHAUSTED
    if budget.get("status") in {"accounting_unavailable", "configuration_unavailable"}:
        return (
            False,
            AI_STATUS_ACCOUNTING_UNAVAILABLE,
            str(budget.get("error_code") or AI_STATUS_ACCOUNTING_UNAVAILABLE),
        )
    if budget.get("status") != "available":
        return False, AI_STATUS_CONFIGURATION_ERROR, "paid_accounting_not_configured"
    return True, AI_STATUS_SUCCESS, None


def _overall_status(config, profiles, budget) -> str:
    if config.mode == AI_MODE_DISABLED:
        return AI_STATUS_DISABLED
    if config.runtime_config_status in _FAIL_CLOSED_RUNTIME_STATES:
        return "degraded"
    if budget.get("status") in {"accounting_unavailable", "configuration_unavailable"}:
        return "degraded"
    if any(not row["executable"] for row in profiles):
        return "degraded"
    return "ready"


def _log_status_failure(component: str, error: Exception) -> None:
    _LOGGER.warning(
        "ai_status_observability_degraded component=%s error_type=%s",
        component,
        type(error).__name__,
    )
