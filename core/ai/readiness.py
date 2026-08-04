from __future__ import annotations

from core.ai.config import AiGatewayConfig, load_ai_gateway_config
from core.ai.models import AI_STATUS_BUDGET_EXHAUSTED
from core.ai.paid_usage_store import (
    PaidAccountingError,
    PostgresPaidUsageStore,
    pricing_from_config,
)
from core.ai.providers import AiProvider, build_default_providers


def get_ai_gateway_status(
    *,
    config: AiGatewayConfig | None = None,
    providers: dict[str, AiProvider] | None = None,
    accounting_store: PostgresPaidUsageStore | None = None,
) -> dict[str, object]:
    resolved_config = config if config is not None else load_ai_gateway_config()
    resolved_providers = providers if providers is not None else build_default_providers()

    local_provider = resolved_providers.get(resolved_config.local_provider)
    paid_provider = resolved_providers.get(resolved_config.paid_provider) if resolved_config.paid_provider else None

    provider_rows = []
    if "disabled" in resolved_providers:
        provider_rows.append(resolved_providers["disabled"].readiness(resolved_config).as_dict())
    if local_provider is not None:
        provider_rows.append(local_provider.readiness(resolved_config).as_dict())
    elif resolved_config.local_provider:
        provider_rows.append(
            {
                "provider": resolved_config.local_provider,
                "configured": resolved_config.local_configured,
                "ready": False,
                "status": "provider_unavailable",
                "model": resolved_config.local_model or None,
                "missing_env_vars": [],
                "credential_env_vars": [],
                "credential_configured": {},
                "error_code": "local_provider_not_registered",
            }
        )
    if paid_provider is not None:
        provider_rows.append(paid_provider.readiness(resolved_config).as_dict())
    anthropic_provider = resolved_providers.get("anthropic")
    if anthropic_provider is not None and anthropic_provider is not paid_provider:
        provider_rows.append(anthropic_provider.readiness(resolved_config).as_dict())

    budget: dict[str, object]
    if not resolved_config.anthropic_budget_configured:
        budget = {
            "status": "not_configured",
            "usage_day": None,
            "daily_cap_usd": resolved_config.anthropic_daily_budget_usd,
            "reserved_usd": 0.0,
            "settled_usd": 0.0,
            "used_usd": 0.0,
            "remaining_usd": 0.0,
            "attempt_count": 0,
            "token_usage_source": "estimated",
            "cost_source": "estimated",
        }
    else:
        try:
            store = accounting_store or PostgresPaidUsageStore()
            budget = store.summary(pricing=pricing_from_config(resolved_config)).as_dict()
            budget["status"] = "available"
            if float(budget["remaining_usd"]) <= 0:
                budget["status"] = AI_STATUS_BUDGET_EXHAUSTED
                for row in provider_rows:
                    if row.get("provider") == "anthropic":
                        row["ready"] = False
                        row["status"] = AI_STATUS_BUDGET_EXHAUSTED
                        row["error_code"] = AI_STATUS_BUDGET_EXHAUSTED
        except PaidAccountingError:
            budget = {
                "status": "accounting_unavailable",
                "usage_day": None,
                "daily_cap_usd": resolved_config.anthropic_daily_budget_usd,
                "reserved_usd": None,
                "settled_usd": None,
                "used_usd": None,
                "remaining_usd": None,
                "attempt_count": None,
                "token_usage_source": "estimated",
                "cost_source": "estimated",
            }

    return {
        "gateway": resolved_config.sanitized(),
        "providers": provider_rows,
        "budget": budget,
        "read_only": True,
        "on_demand_only": True,
    }
