from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import re
import uuid
from typing import Callable

from core.ai.config import AiGatewayConfig
from core.ai.models import AiGatewayRequest, AiGatewayResponse, estimate_tokens
from core.db import get_db_connection


MONEY_QUANTUM = Decimal("0.00000001")
MILLION = Decimal("1000000")
SAFE_CORRELATION_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class PaidAccountingError(RuntimeError):
    pass


class PaidAccountingUnavailable(PaidAccountingError):
    pass


class PaidAccountingConfigurationError(PaidAccountingError):
    pass


class PaidBudgetExhausted(PaidAccountingError):
    def __init__(
        self,
        *,
        attempt_id: str,
        usage_day: date,
        requested_usd: Decimal,
        remaining_usd: Decimal,
    ):
        super().__init__("Daily paid AI budget is exhausted.")
        self.attempt_id = attempt_id
        self.usage_day = usage_day
        self.requested_usd = requested_usd
        self.remaining_usd = remaining_usd


@dataclass(frozen=True)
class PaidUsagePricing:
    daily_cap_usd: Decimal
    input_cost_per_million_tokens: Decimal
    output_cost_per_million_tokens: Decimal


@dataclass(frozen=True)
class PaidUsageReservation:
    attempt_id: str
    usage_day: date
    reserved_cost_usd: Decimal
    remaining_usd: Decimal
    estimated_input_tokens: int
    estimated_output_tokens: int
    correlation_id: str | None
    attempt_kind: str


@dataclass(frozen=True)
class PaidUsageSettlement:
    attempt_id: str
    usage_day: date
    charged_cost_usd: Decimal
    remaining_usd: Decimal
    input_tokens: int
    output_tokens: int
    total_tokens: int
    token_usage_source: str
    cost_source: str


@dataclass(frozen=True)
class PaidUsageSummary:
    usage_day: date
    daily_cap_usd: Decimal
    reserved_usd: Decimal
    settled_usd: Decimal
    remaining_usd: Decimal
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    attempt_count: int
    token_usage_source: str

    def as_dict(self) -> dict[str, object]:
        return {
            "usage_day": self.usage_day.isoformat(),
            "daily_cap_usd": float(self.daily_cap_usd),
            "reserved_usd": float(self.reserved_usd),
            "settled_usd": float(self.settled_usd),
            "used_usd": float(self.reserved_usd + self.settled_usd),
            "remaining_usd": float(self.remaining_usd),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_tokens,
            "attempt_count": self.attempt_count,
            "token_usage_source": self.token_usage_source,
            "cost_source": "estimated",
        }


def pricing_from_config(config: AiGatewayConfig) -> PaidUsagePricing:
    try:
        pricing = PaidUsagePricing(
            daily_cap_usd=Decimal(str(config.anthropic_daily_budget_usd)),
            input_cost_per_million_tokens=Decimal(
                str(config.anthropic_input_cost_per_million_tokens)
            ),
            output_cost_per_million_tokens=Decimal(
                str(config.anthropic_output_cost_per_million_tokens)
            ),
        )
    except (InvalidOperation, ValueError):
        raise PaidAccountingConfigurationError("Paid AI pricing is invalid.") from None
    if (
        not config.anthropic_budget_valid
        or pricing.daily_cap_usd <= 0
        or pricing.input_cost_per_million_tokens <= 0
        or pricing.output_cost_per_million_tokens <= 0
    ):
        raise PaidAccountingConfigurationError("Paid AI pricing is invalid.")
    return pricing


def conservative_request_cost(
    request: AiGatewayRequest,
    *,
    max_output_tokens: int,
    pricing: PaidUsagePricing,
) -> tuple[int, int, Decimal]:
    prompt_bytes = len(request.prompt.encode("utf-8"))
    input_tokens = max(estimate_tokens(request.prompt), prompt_bytes)
    output_tokens = max(0, int(max_output_tokens))
    cost = _token_cost(input_tokens, output_tokens, pricing)
    if cost <= 0:
        raise PaidAccountingConfigurationError("Paid AI request cost is invalid.")
    return input_tokens, output_tokens, cost


class PostgresPaidUsageStore:
    def __init__(
        self,
        *,
        connection_factory: Callable[[], object] = get_db_connection,
        utc_day: Callable[[], date] | None = None,
    ):
        self._connection_factory = connection_factory
        self._utc_day = utc_day or (lambda: datetime.now(timezone.utc).date())

    def reserve(
        self,
        *,
        request: AiGatewayRequest,
        provider: str,
        model: str,
        profile: str,
        max_output_tokens: int,
        pricing: PaidUsagePricing,
    ) -> PaidUsageReservation:
        usage_day = self._utc_day()
        attempt_id = uuid.uuid4().hex
        correlation_id = _correlation_id(request)
        attempt_kind = _attempt_kind(request)
        input_tokens, output_tokens, requested_cost = conservative_request_cost(
            request,
            max_output_tokens=max_output_tokens,
            pricing=pricing,
        )
        conn = None
        try:
            conn = self._connection_factory()
            with conn.cursor() as cur:
                _assert_runtime_policy_current(
                    cur,
                    model=model,
                    pricing=pricing,
                )
                cur.execute(
                    """
                    INSERT INTO ai_paid_usage_days (usage_day, daily_cap_usd)
                    VALUES (%s, %s)
                    ON CONFLICT (usage_day) DO NOTHING
                    """,
                    (usage_day, pricing.daily_cap_usd),
                )
                cur.execute(
                    """
                    SELECT daily_cap_usd, reserved_usd, settled_usd
                    FROM ai_paid_usage_days
                    WHERE usage_day = %s
                    FOR UPDATE
                    """,
                    (usage_day,),
                )
                row = cur.fetchone()
                if row is None:
                    raise PaidAccountingUnavailable("Paid AI usage day is unavailable.")
                stored_cap, reserved, settled = (Decimal(str(value)) for value in row)
                used = reserved + settled
                effective_cap = pricing.daily_cap_usd
                if stored_cap != effective_cap and used <= effective_cap:
                    cur.execute(
                        """
                        UPDATE ai_paid_usage_days
                        SET daily_cap_usd = %s, updated_at = NOW()
                        WHERE usage_day = %s
                        """,
                        (effective_cap, usage_day),
                    )
                    stored_cap = effective_cap
                remaining = max(Decimal("0"), effective_cap - used)
                if requested_cost > remaining:
                    cur.execute(
                        """
                        INSERT INTO ai_paid_request_attempts (
                            attempt_id, usage_day, provider, model, profile,
                            correlation_id, attempt_kind, status,
                            estimated_cost_usd, input_tokens, output_tokens,
                            total_tokens, token_usage_source, cost_source,
                            completed_at, error_code
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, 'estimated', 'estimated', NOW(), %s)
                        """,
                        (
                            attempt_id,
                            usage_day,
                            provider,
                            model,
                            profile,
                            correlation_id,
                            attempt_kind,
                            "budget_exhausted",
                            requested_cost,
                            input_tokens,
                            output_tokens,
                            input_tokens + output_tokens,
                            "budget_exhausted",
                        ),
                    )
                    conn.commit()
                    raise PaidBudgetExhausted(
                        attempt_id=attempt_id,
                        usage_day=usage_day,
                        requested_usd=requested_cost,
                        remaining_usd=remaining,
                    )
                cur.execute(
                    """
                    INSERT INTO ai_paid_request_attempts (
                        attempt_id, usage_day, provider, model, profile,
                        correlation_id, attempt_kind, status,
                        reserved_cost_usd, estimated_cost_usd,
                        input_tokens, output_tokens, total_tokens,
                        token_usage_source, cost_source, provider_started_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'reserved',
                            %s, %s, %s, %s, %s, 'estimated', 'estimated', NOW())
                    """,
                    (
                        attempt_id,
                        usage_day,
                        provider,
                        model,
                        profile,
                        correlation_id,
                        attempt_kind,
                        requested_cost,
                        requested_cost,
                        input_tokens,
                        output_tokens,
                        input_tokens + output_tokens,
                    ),
                )
                cur.execute(
                    """
                    UPDATE ai_paid_usage_days
                    SET reserved_usd = reserved_usd + %s, updated_at = NOW()
                    WHERE usage_day = %s
                    """,
                    (requested_cost, usage_day),
                )
            conn.commit()
            return PaidUsageReservation(
                attempt_id=attempt_id,
                usage_day=usage_day,
                reserved_cost_usd=requested_cost,
                remaining_usd=remaining - requested_cost,
                estimated_input_tokens=input_tokens,
                estimated_output_tokens=output_tokens,
                correlation_id=correlation_id,
                attempt_kind=attempt_kind,
            )
        except PaidBudgetExhausted:
            raise
        except PaidAccountingConfigurationError:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise
        except Exception:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise PaidAccountingUnavailable("Paid AI accounting is unavailable.") from None
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def settle(
        self,
        reservation: PaidUsageReservation,
        response: AiGatewayResponse,
        *,
        pricing: PaidUsagePricing,
    ) -> PaidUsageSettlement:
        reported_input = response.metadata.provider_reported_prompt_tokens
        reported_output = response.metadata.provider_reported_completion_tokens
        has_reported_usage = reported_input is not None and reported_output is not None
        if has_reported_usage:
            input_tokens = int(reported_input)
            output_tokens = int(reported_output)
            provider_cost = _token_cost(input_tokens, output_tokens, pricing)
            if provider_cost <= reservation.reserved_cost_usd:
                charged_cost = provider_cost
                token_source = "provider_reported"
            else:
                charged_cost = reservation.reserved_cost_usd
                token_source = "provider_reported"
        else:
            input_tokens = reservation.estimated_input_tokens
            output_tokens = reservation.estimated_output_tokens
            charged_cost = reservation.reserved_cost_usd
            token_source = "estimated"
        cost_source = "estimated"

        conn = None
        try:
            conn = self._connection_factory()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT reserved_cost_usd, status
                    FROM ai_paid_request_attempts
                    WHERE attempt_id = %s
                    FOR UPDATE
                    """,
                    (reservation.attempt_id,),
                )
                attempt = cur.fetchone()
                if attempt is None or attempt[1] != "reserved":
                    raise PaidAccountingUnavailable("Paid AI reservation is unavailable.")
                stored_reservation = Decimal(str(attempt[0]))
                cur.execute(
                    """
                    SELECT daily_cap_usd, reserved_usd, settled_usd
                    FROM ai_paid_usage_days
                    WHERE usage_day = %s
                    FOR UPDATE
                    """,
                    (reservation.usage_day,),
                )
                day_row = cur.fetchone()
                if day_row is None:
                    raise PaidAccountingUnavailable("Paid AI usage day is unavailable.")
                daily_cap, reserved_total, settled_total = (
                    Decimal(str(value)) for value in day_row
                )
                charged_cost = min(charged_cost, stored_reservation)
                new_reserved = reserved_total - stored_reservation
                new_settled = settled_total + charged_cost
                if new_reserved < 0 or new_reserved + new_settled > daily_cap:
                    raise PaidAccountingUnavailable("Paid AI accounting invariant failed.")
                cur.execute(
                    """
                    UPDATE ai_paid_usage_days
                    SET reserved_usd = %s, settled_usd = %s, updated_at = NOW()
                    WHERE usage_day = %s
                    """,
                    (new_reserved, new_settled, reservation.usage_day),
                )
                cur.execute(
                    """
                    UPDATE ai_paid_request_attempts
                    SET status = %s,
                        settled_cost_usd = %s,
                        estimated_cost_usd = %s,
                        input_tokens = %s,
                        output_tokens = %s,
                        total_tokens = %s,
                        token_usage_source = %s,
                        cost_source = %s,
                        provider_latency_ms = %s,
                        error_code = %s,
                        completed_at = NOW()
                    WHERE attempt_id = %s
                    """,
                    (
                        response.status,
                        charged_cost,
                        charged_cost,
                        input_tokens,
                        output_tokens,
                        input_tokens + output_tokens,
                        token_source,
                        cost_source,
                        response.metadata.latency_ms,
                        response.metadata.error_code,
                        reservation.attempt_id,
                    ),
                )
            conn.commit()
            return PaidUsageSettlement(
                attempt_id=reservation.attempt_id,
                usage_day=reservation.usage_day,
                charged_cost_usd=charged_cost,
                remaining_usd=daily_cap - new_reserved - new_settled,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                token_usage_source=token_source,
                cost_source=cost_source,
            )
        except Exception:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise PaidAccountingUnavailable("Paid AI accounting is unavailable.") from None
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def summary(self, *, pricing: PaidUsagePricing) -> PaidUsageSummary:
        usage_day = self._utc_day()
        conn = None
        try:
            conn = self._connection_factory()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT daily_cap_usd, reserved_usd, settled_usd
                    FROM ai_paid_usage_days
                    WHERE usage_day = %s
                    """,
                    (usage_day,),
                )
                day_row = cur.fetchone()
                cur.execute(
                    """
                    SELECT COALESCE(SUM(input_tokens) FILTER (
                               WHERE status <> 'budget_exhausted'
                           ), 0),
                           COALESCE(SUM(output_tokens) FILTER (
                               WHERE status <> 'budget_exhausted'
                           ), 0),
                           COALESCE(SUM(total_tokens) FILTER (
                               WHERE status <> 'budget_exhausted'
                           ), 0),
                           COUNT(*),
                           COUNT(*) FILTER (
                               WHERE status <> 'budget_exhausted'
                                 AND token_usage_source = 'estimated'
                           )
                    FROM ai_paid_request_attempts
                    WHERE usage_day = %s
                    """,
                    (usage_day,),
                )
                totals = cur.fetchone() or (0, 0, 0, 0)
            if day_row is None:
                cap = pricing.daily_cap_usd
                reserved = settled = Decimal("0")
            else:
                _stored_cap, reserved, settled = (Decimal(str(value)) for value in day_row)
                cap = pricing.daily_cap_usd
            return PaidUsageSummary(
                usage_day=usage_day,
                daily_cap_usd=cap,
                reserved_usd=reserved,
                settled_usd=settled,
                remaining_usd=max(Decimal("0"), cap - reserved - settled),
                total_input_tokens=int(totals[0]),
                total_output_tokens=int(totals[1]),
                total_tokens=int(totals[2]),
                attempt_count=int(totals[3]),
                token_usage_source=(
                    "estimated"
                    if int(totals[4]) > 0 or int(totals[3]) == 0
                    else "provider_reported"
                ),
            )
        except Exception:
            raise PaidAccountingUnavailable("Paid AI accounting is unavailable.") from None
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass


def _token_cost(input_tokens: int, output_tokens: int, pricing: PaidUsagePricing) -> Decimal:
    raw = (
        Decimal(input_tokens) * pricing.input_cost_per_million_tokens
        + Decimal(output_tokens) * pricing.output_cost_per_million_tokens
    ) / MILLION
    return raw.quantize(MONEY_QUANTUM, rounding=ROUND_CEILING)


def _correlation_id(request: AiGatewayRequest) -> str | None:
    value = request.metadata.get("paid_correlation_id")
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized if SAFE_CORRELATION_ID.fullmatch(normalized) else None


def _attempt_kind(request: AiGatewayRequest) -> str:
    repair_attempt = request.metadata.get("repair_attempt")
    task = request.metadata.get("task")
    return "repair" if repair_attempt == 1 or task == "turn_plan_repair" else "initial"


def _assert_runtime_policy_current(
    cur,
    *,
    model: str,
    pricing: PaidUsagePricing,
) -> None:
    cur.execute(
        """
        SELECT gateway_mode, preferred_anthropic_model,
               daily_paid_budget_usd, anthropic_routing_enabled
        FROM ai_gateway_config
        WHERE id = 1
        FOR SHARE
        """
    )
    row = cur.fetchone()
    if row is None:
        return
    runtime_cap = Decimal(str(row[2]))
    if (
        row[0] != "automatic_fallback"
        or row[1] != model
        or runtime_cap != pricing.daily_cap_usd
        or row[3] is not True
    ):
        raise PaidAccountingConfigurationError(
            "Paid AI runtime policy changed before authorization."
        )
