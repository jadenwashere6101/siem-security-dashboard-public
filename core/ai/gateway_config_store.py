from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
import logging
import math
import re
from typing import Callable

from core.ai.config import (
    AI_MODE_DISABLED,
    AI_MODE_LOCAL_ONLY,
    VALID_AI_GATEWAY_MODES,
    AiGatewayConfig,
    load_ai_gateway_config,
)
from core.ai.profile_registry import (
    AI_PROFILE_AGENTIC_PLANNING,
    AI_PROVIDER_OLLAMA,
    APPROVED_AI_PROFILES,
    validate_profile_provider_routing,
)
from core.db import get_db_connection


_LOGGER = logging.getLogger(__name__)
_MODEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
_MAX_DAILY_BUDGET_USD = Decimal("9999999999.99999999")
_POLICY_FIELDS = frozenset(
    {
        "gateway_mode",
        "preferred_anthropic_model",
        "daily_paid_budget_usd",
        "anthropic_routing_enabled",
    }
)
_SENSITIVE_FIELD_MARKERS = (
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "endpoint",
    "evidence",
    "password",
    "prompt",
    "secret",
    "token",
)


class GatewayConfigError(RuntimeError):
    pass


class GatewayConfigValidationError(GatewayConfigError):
    pass


@dataclass(frozen=True)
class RuntimeGatewayPolicy:
    gateway_mode: str
    preferred_anthropic_model: str
    daily_paid_budget_usd: Decimal
    anthropic_routing_enabled: bool
    updated_by: str | None = None
    updated_at: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "gateway_mode": self.gateway_mode,
            "preferred_anthropic_model": self.preferred_anthropic_model,
            "daily_paid_budget_usd": float(self.daily_paid_budget_usd),
            "anthropic_routing_enabled": self.anthropic_routing_enabled,
        }


def validate_gateway_config_updates(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise GatewayConfigValidationError("JSON object body is required.")
    if not payload:
        raise GatewayConfigValidationError("At least one gateway configuration field is required.")
    unknown = set(payload) - _POLICY_FIELDS
    if unknown:
        if any(
            marker in str(field).strip().lower()
            for field in unknown
            for marker in _SENSITIVE_FIELD_MARKERS
        ):
            raise GatewayConfigValidationError("Credential or sensitive fields are prohibited.")
        raise GatewayConfigValidationError("Unknown gateway configuration field.")
    return dict(payload)


def validate_gateway_policy(values: dict[str, object]) -> RuntimeGatewayPolicy:
    if set(values) != set(_POLICY_FIELDS):
        raise GatewayConfigValidationError("Gateway configuration is incomplete.")

    mode = values["gateway_mode"]
    if not isinstance(mode, str) or mode not in VALID_AI_GATEWAY_MODES:
        raise GatewayConfigValidationError("gateway_mode is invalid.")

    model = values["preferred_anthropic_model"]
    if not isinstance(model, str):
        raise GatewayConfigValidationError("preferred_anthropic_model must be a string.")
    model = model.strip()
    if model and not _MODEL_PATTERN.fullmatch(model):
        raise GatewayConfigValidationError("preferred_anthropic_model is invalid.")

    routing_enabled = values["anthropic_routing_enabled"]
    if not isinstance(routing_enabled, bool):
        raise GatewayConfigValidationError("anthropic_routing_enabled must be a boolean.")

    raw_budget = values["daily_paid_budget_usd"]
    if isinstance(raw_budget, bool) or not isinstance(raw_budget, (int, float, Decimal)):
        raise GatewayConfigValidationError("daily_paid_budget_usd must be a number.")
    if isinstance(raw_budget, float) and not math.isfinite(raw_budget):
        raise GatewayConfigValidationError("daily_paid_budget_usd must be finite.")
    try:
        budget = Decimal(str(raw_budget))
    except (InvalidOperation, ValueError):
        raise GatewayConfigValidationError("daily_paid_budget_usd is invalid.") from None
    if not budget.is_finite() or budget < 0 or budget > _MAX_DAILY_BUDGET_USD:
        raise GatewayConfigValidationError("daily_paid_budget_usd is outside the supported range.")
    if routing_enabled and (not model or budget <= 0):
        raise GatewayConfigValidationError(
            "Anthropic routing requires a preferred model and positive daily budget."
        )

    return RuntimeGatewayPolicy(
        gateway_mode=mode,
        preferred_anthropic_model=model,
        daily_paid_budget_usd=budget,
        anthropic_routing_enabled=routing_enabled,
    )


class PostgresGatewayConfigStore:
    def __init__(self, *, connection_factory: Callable[[], object] | None = None):
        self._connection_factory = connection_factory or get_db_connection

    def resolve(self, source_config: AiGatewayConfig | None = None) -> AiGatewayConfig:
        source = source_config or load_ai_gateway_config()
        conn = None
        cur = None
        try:
            conn = self._connection_factory()
            cur = conn.cursor()
            return self.resolve_with_cursor(cur, source)
        except Exception as error:
            _LOGGER.warning(
                "ai_gateway_runtime_config fallback=fail_closed status=unavailable reason=%s",
                type(error).__name__,
            )
            return _fail_closed_config(source, status="unavailable", error_code="runtime_config_unavailable")
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

    def resolve_with_cursor(self, cur, source_config: AiGatewayConfig) -> AiGatewayConfig:
        try:
            cur.execute("SAVEPOINT ai_gateway_config_read")
            cur.execute(
                """
                SELECT gateway_mode, preferred_anthropic_model,
                       daily_paid_budget_usd, anthropic_routing_enabled,
                       updated_by, updated_at
                FROM ai_gateway_config
                WHERE id = 1
                """
            )
            row = cur.fetchone()
            if row is None:
                if not source_config.mode_valid:
                    raise GatewayConfigValidationError("Source gateway mode is invalid.")
                policy = _source_policy(source_config)
                status = "default"
            else:
                policy = _policy_from_row(row)
                status = "applied"
            cur.execute("RELEASE SAVEPOINT ai_gateway_config_read")
            return _apply_policy(source_config, policy, status=status)
        except Exception as error:
            try:
                cur.execute("ROLLBACK TO SAVEPOINT ai_gateway_config_read")
                cur.execute("RELEASE SAVEPOINT ai_gateway_config_read")
            except Exception:
                pass
            status = "invalid" if isinstance(error, (GatewayConfigValidationError, ValueError)) else "unavailable"
            _LOGGER.warning(
                "ai_gateway_runtime_config fallback=fail_closed status=%s reason=%s",
                status,
                type(error).__name__,
            )
            error_code = "runtime_config_invalid" if status == "invalid" else "runtime_config_unavailable"
            return _fail_closed_config(source_config, status=status, error_code=error_code)

    def stage_update(
        self,
        cur,
        *,
        source_config: AiGatewayConfig,
        updates: object,
        updated_by: str,
    ) -> tuple[RuntimeGatewayPolicy, RuntimeGatewayPolicy]:
        normalized_updates = validate_gateway_config_updates(updates)
        cur.execute(
            """
            SELECT gateway_mode, preferred_anthropic_model,
                   daily_paid_budget_usd, anthropic_routing_enabled,
                   updated_by, updated_at
            FROM ai_gateway_config
            WHERE id = 1
            FOR UPDATE
            """
        )
        row = cur.fetchone()
        try:
            old_policy = _policy_from_row(row) if row is not None else _source_policy(source_config)
        except GatewayConfigValidationError:
            old_policy = _source_policy(source_config)
        merged = {**old_policy.as_dict(), **normalized_updates}
        new_policy = validate_gateway_policy(merged)
        cur.execute(
            """
            INSERT INTO ai_gateway_config (
                id, gateway_mode, preferred_anthropic_model,
                daily_paid_budget_usd, anthropic_routing_enabled,
                updated_by, updated_at
            )
            VALUES (1, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (id) DO UPDATE
            SET gateway_mode = EXCLUDED.gateway_mode,
                preferred_anthropic_model = EXCLUDED.preferred_anthropic_model,
                daily_paid_budget_usd = EXCLUDED.daily_paid_budget_usd,
                anthropic_routing_enabled = EXCLUDED.anthropic_routing_enabled,
                updated_by = EXCLUDED.updated_by,
                updated_at = NOW()
            RETURNING updated_at
            """,
            (
                new_policy.gateway_mode,
                new_policy.preferred_anthropic_model,
                new_policy.daily_paid_budget_usd,
                new_policy.anthropic_routing_enabled,
                updated_by,
            ),
        )
        updated_at = cur.fetchone()[0]
        new_policy = replace(
            new_policy,
            updated_by=updated_by,
            updated_at=str(updated_at),
        )
        return old_policy, new_policy


def runtime_config_view(config: AiGatewayConfig) -> dict[str, object]:
    requested_routing = config.runtime_anthropic_routing_requested
    if requested_routing is None:
        requested_routing = config.anthropic_routing_enabled
    return {
        "status": config.runtime_config_status,
        "error_code": config.runtime_config_error_code,
        "configuration": {
            "gateway_mode": config.configured_mode,
            "preferred_anthropic_model": config.anthropic_model,
            "daily_paid_budget_usd": config.anthropic_daily_budget_usd,
            "anthropic_routing_enabled": requested_routing,
        },
        "effective": {
            "gateway_mode": config.mode,
            "preferred_anthropic_model": config.anthropic_model,
            "daily_paid_budget_usd": config.anthropic_daily_budget_usd,
            "anthropic_routing_enabled": config.anthropic_routing_enabled,
        },
        "updated_by": config.runtime_config_updated_by,
        "updated_at": config.runtime_config_updated_at,
    }


def _policy_from_row(row) -> RuntimeGatewayPolicy:
    values = {
        "gateway_mode": row[0],
        "preferred_anthropic_model": row[1],
        "daily_paid_budget_usd": row[2],
        "anthropic_routing_enabled": row[3],
    }
    policy = validate_gateway_policy(values)
    return replace(
        policy,
        updated_by=row[4],
        updated_at=str(row[5]) if row[5] is not None else None,
    )


def _source_policy(config: AiGatewayConfig) -> RuntimeGatewayPolicy:
    return validate_gateway_policy(
        {
            "gateway_mode": config.mode,
            "preferred_anthropic_model": config.anthropic_model,
            "daily_paid_budget_usd": config.anthropic_daily_budget_usd,
            "anthropic_routing_enabled": config.anthropic_routing_enabled,
        }
    )


def _apply_policy(
    source: AiGatewayConfig,
    policy: RuntimeGatewayPolicy,
    *,
    status: str,
) -> AiGatewayConfig:
    profiles = dict(source.profiles or {})
    if not profiles:
        profiles = {name: source.profile(name) for name in APPROVED_AI_PROFILES}
    profiles[AI_PROFILE_AGENTIC_PLANNING] = replace(
        profiles[AI_PROFILE_AGENTIC_PLANNING],
        model=policy.preferred_anthropic_model,
    )
    validate_profile_provider_routing(profiles)
    provider_configured = bool(
        source.anthropic_enabled
        and source.anthropic_enabled_valid
        and source.anthropic_api_key
        and policy.preferred_anthropic_model
        and source.anthropic_timeout_valid
        and source.anthropic_api_version
        and source.anthropic_budget_valid
        and source.anthropic_input_cost_per_million_tokens > 0
        and source.anthropic_output_cost_per_million_tokens > 0
        and policy.daily_paid_budget_usd > 0
    )
    effective_routing = policy.anthropic_routing_enabled and provider_configured
    error_code = None
    if policy.anthropic_routing_enabled and not effective_routing:
        error_code = "anthropic_configuration_invalid"
    return replace(
        source,
        mode=policy.gateway_mode,
        configured_mode=policy.gateway_mode,
        mode_valid=True,
        anthropic_model=policy.preferred_anthropic_model,
        anthropic_daily_budget_usd=float(policy.daily_paid_budget_usd),
        anthropic_routing_enabled=effective_routing,
        profiles=profiles,
        runtime_config_status=status,
        runtime_config_error_code=error_code,
        runtime_config_updated_by=policy.updated_by,
        runtime_config_updated_at=policy.updated_at,
        runtime_anthropic_routing_requested=policy.anthropic_routing_enabled,
    )


def _fail_closed_config(
    source: AiGatewayConfig,
    *,
    status: str,
    error_code: str,
) -> AiGatewayConfig:
    effective_mode = AI_MODE_LOCAL_ONLY if _valid_local_defaults(source) else AI_MODE_DISABLED
    return replace(
        source,
        mode=effective_mode,
        mode_valid=True,
        anthropic_routing_enabled=False,
        runtime_config_status=status,
        runtime_config_error_code=error_code,
        runtime_config_updated_by=None,
        runtime_config_updated_at=None,
        runtime_anthropic_routing_requested=False,
    )


def _valid_local_defaults(source: AiGatewayConfig) -> bool:
    if source.local_provider != AI_PROVIDER_OLLAMA or not source.local_configured:
        return False
    try:
        profiles = dict(source.profiles or {})
        if not profiles:
            profiles = {name: source.profile(name) for name in APPROVED_AI_PROFILES}
        validate_profile_provider_routing(profiles)
    except (KeyError, ValueError):
        return False
    return True
