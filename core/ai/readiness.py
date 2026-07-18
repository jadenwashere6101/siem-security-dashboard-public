from __future__ import annotations

from core.ai.config import AiGatewayConfig, load_ai_gateway_config
from core.ai.providers import AiProvider, build_default_providers


def get_ai_gateway_status(
    *,
    config: AiGatewayConfig | None = None,
    providers: dict[str, AiProvider] | None = None,
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

    return {
        "gateway": resolved_config.sanitized(),
        "providers": provider_rows,
        "read_only": True,
        "on_demand_only": True,
    }
