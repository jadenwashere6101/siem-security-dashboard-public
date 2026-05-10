from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

SIMULATION_MODE = "simulation"
SECRET_FIELD_NAMES = {
    "api_key",
    "authorization",
    "auth",
    "password",
    "secret",
    "token",
    "webhook_url",
}

CIRCUIT_STATE_CLOSED = "closed"
CIRCUIT_STATE_OPEN = "open"
CIRCUIT_STATE_HALF_OPEN = "half_open"

_VALID_CIRCUIT_STATES = frozenset(
    {CIRCUIT_STATE_CLOSED, CIRCUIT_STATE_OPEN, CIRCUIT_STATE_HALF_OPEN}
)

FAILURE_CLASSIFICATION_TRANSIENT = "transient"
FAILURE_CLASSIFICATION_NON_TRANSIENT = "non_transient"
FAILURE_CLASSIFICATION_TIMEOUT = "timeout"
FAILURE_CLASSIFICATION_CIRCUIT_OPEN = "circuit_open"
FAILURE_CLASSIFICATION_CIRCUIT_STATE_INVALID = "circuit_state_invalid"


@dataclass
class IntegrationResult:
    adapter: str
    action: str
    mode: str
    simulated: bool
    executed: bool
    success: bool
    message: str
    params: dict[str, Any]
    context: dict[str, Any]
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "action": self.action,
            "mode": self.mode,
            "simulated": self.simulated,
            "executed": self.executed,
            "success": self.success,
            "message": self.message,
            "params": self.params,
            "context": self.context,
            "metadata": self.metadata,
        }


@dataclass
class _SimulatedCircuitBreakerState:
    """In-process simulation-only breaker state (not persisted across restarts)."""

    state: str = CIRCUIT_STATE_CLOSED
    consecutive_failures: int = 0
    failure_threshold: int = 3
    cooldown_seconds: int = 60
    opened_at: datetime | None = None
    last_failure_reason: str | None = None
    timeout_seconds: int | None = 30
    retry_eligible: bool = True
    cooldown_until: datetime | None = None
    last_failure_classification: str | None = None
    half_open_probe_available: bool = False
    last_manual_action: str | None = None
    last_manual_action_by: str | None = None
    last_manual_action_at: datetime | None = None
    last_manual_reason: str | None = None


_circuit_store: dict[str, _SimulatedCircuitBreakerState] = {}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_adapter_key(name: str) -> str:
    return str(name or "").strip().lower()


def _get_circuit_state(adapter_name: str) -> _SimulatedCircuitBreakerState:
    key = _normalize_adapter_key(adapter_name)
    if key not in _circuit_store:
        _circuit_store[key] = _SimulatedCircuitBreakerState()
    return _circuit_store[key]


def reset_simulated_circuit_breakers(adapter_name: str | None = None) -> None:
    """Reset in-memory breaker simulation (primarily for tests). None clears all adapters."""
    global _circuit_store
    if adapter_name is None:
        _circuit_store = {}
        return
    key = _normalize_adapter_key(adapter_name)
    _circuit_store.pop(key, None)


def configure_simulated_circuit_breaker(
    adapter_name: str,
    *,
    failure_threshold: int | None = None,
    cooldown_seconds: int | None = None,
    timeout_seconds: int | None = None,
    state: str | None = None,
    consecutive_failures: int | None = None,
    cooldown_until: datetime | None = None,
    opened_at: datetime | None = None,
    last_failure_reason: str | None = None,
    last_failure_classification: str | None = None,
    retry_eligible: bool | None = None,
    half_open_probe_available: bool | None = None,
) -> None:
    """Narrow test/admin hook to set simulation fields without executing adapters."""
    st = _get_circuit_state(adapter_name)
    if failure_threshold is not None:
        st.failure_threshold = max(1, int(failure_threshold))
    if cooldown_seconds is not None:
        st.cooldown_seconds = max(0, int(cooldown_seconds))
    if timeout_seconds is not None:
        st.timeout_seconds = int(timeout_seconds) if timeout_seconds is not None else None
    if state is not None:
        st.state = str(state).strip().lower()
        if st.state == CIRCUIT_STATE_HALF_OPEN:
            st.half_open_probe_available = True
        else:
            st.half_open_probe_available = False
    if consecutive_failures is not None:
        st.consecutive_failures = max(0, int(consecutive_failures))
    if cooldown_until is not None:
        st.cooldown_until = cooldown_until
    if opened_at is not None:
        st.opened_at = opened_at
    if last_failure_reason is not None:
        st.last_failure_reason = last_failure_reason
    if last_failure_classification is not None:
        st.last_failure_classification = last_failure_classification
    if retry_eligible is not None:
        st.retry_eligible = bool(retry_eligible)
    if half_open_probe_available is not None:
        st.half_open_probe_available = bool(half_open_probe_available)


def get_simulated_circuit_breaker_dict(adapter_name: str, *, now: datetime | None = None) -> dict[str, Any]:
    """Operator-visible circuit snapshot for status APIs and tests."""
    when = now if now is not None else _utc_now()
    st = _get_circuit_state(adapter_name)
    return {
        "state": st.state,
        "consecutive_failures": st.consecutive_failures,
        "failure_threshold": st.failure_threshold,
        "cooldown_seconds": st.cooldown_seconds,
        "opened_at": _iso_utc(st.opened_at),
        "last_failure_reason": st.last_failure_reason,
        "timeout_seconds": st.timeout_seconds,
        "retry_eligible": _compute_retry_eligible(st, when),
        "cooldown_until": _iso_utc(st.cooldown_until),
        "last_failure_classification": st.last_failure_classification,
        "half_open_probe_available": st.half_open_probe_available,
        "last_manual_action": st.last_manual_action,
        "last_manual_action_by": st.last_manual_action_by,
        "last_manual_action_at": _iso_utc(st.last_manual_action_at),
        "last_manual_reason": st.last_manual_reason,
        "state_persisted": False,
    }


class SimulatedCircuitBreakerControlError(Exception):
    """Raised when a manual simulation circuit control cannot be applied."""

    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _apply_manual_operator_metadata(
    st: _SimulatedCircuitBreakerState,
    action: str,
    actor_username: str,
    reason: str,
    when: datetime,
) -> None:
    st.last_manual_action = action
    st.last_manual_action_by = actor_username
    st.last_manual_action_at = when
    trimmed = (reason or "").strip()
    st.last_manual_reason = trimmed[:2000] if trimmed else None


def manual_reset_simulated_circuit_breaker(
    adapter_name: str,
    *,
    actor_username: str,
    reason: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Super-admin manual control: clear breaker to closed (simulation state only)."""
    when = now if now is not None else _utc_now()
    st = _get_circuit_state(adapter_name)
    _reset_to_closed_success(st)
    _apply_manual_operator_metadata(st, "reset", actor_username, reason, when)
    return get_simulated_circuit_breaker_dict(adapter_name, now=when)


def manual_force_open_simulated_circuit_breaker(
    adapter_name: str,
    *,
    actor_username: str,
    reason: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Super-admin manual containment: force open without executing adapters."""
    when = now if now is not None else _utc_now()
    st = _get_circuit_state(adapter_name)
    st.state = CIRCUIT_STATE_OPEN
    st.opened_at = when
    st.cooldown_until = when + timedelta(seconds=st.cooldown_seconds)
    st.retry_eligible = False
    st.half_open_probe_available = False
    note = (reason or "").strip()
    st.last_failure_reason = f"manual force_open: {note[:500]}"
    st.last_failure_classification = FAILURE_CLASSIFICATION_CIRCUIT_OPEN
    _apply_manual_operator_metadata(st, "force_open", actor_username, reason, when)
    return get_simulated_circuit_breaker_dict(adapter_name, now=when)


def manual_enable_half_open_probe_simulated_circuit_breaker(
    adapter_name: str,
    *,
    actor_username: str,
    reason: str,
    override_cooldown: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Super-admin: allow one bounded half-open probe on the next simulated execution path.
    Does not run adapter logic or probes.
    """
    when = now if now is not None else _utc_now()
    st = _get_circuit_state(adapter_name)
    if st.state not in _VALID_CIRCUIT_STATES:
        raise SimulatedCircuitBreakerControlError(
            "Circuit breaker state is invalid; reset the breaker before enabling a half-open probe.",
            status_code=409,
        )
    if st.state != CIRCUIT_STATE_OPEN:
        raise SimulatedCircuitBreakerControlError(
            "Half-open probe can only be enabled when the breaker is open.",
            status_code=400,
        )
    if st.cooldown_until is not None and when < st.cooldown_until:
        if not override_cooldown:
            raise SimulatedCircuitBreakerControlError(
                "Cooldown is still active; retry after cooldown or pass override_cooldown=true with reason.",
                status_code=409,
            )
    st.state = CIRCUIT_STATE_HALF_OPEN
    st.half_open_probe_available = True
    st.retry_eligible = False
    _apply_manual_operator_metadata(st, "enable_half_open", actor_username, reason, when)
    return get_simulated_circuit_breaker_dict(adapter_name, now=when)


def _iso_utc(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _compute_retry_eligible(st: _SimulatedCircuitBreakerState, now: datetime) -> bool:
    if st.state == CIRCUIT_STATE_OPEN:
        return False
    if st.state not in _VALID_CIRCUIT_STATES:
        return False
    if st.last_failure_classification == FAILURE_CLASSIFICATION_NON_TRANSIENT:
        return False
    return bool(st.retry_eligible)


def request_half_open_probe(adapter_name: str, *, now: datetime | None = None) -> bool:
    """
    Explicit transition open -> half_open after cooldown. Does not run adapter logic.
    Returns True when the transition occurred.
    """
    when = now if now is not None else _utc_now()
    st = _get_circuit_state(adapter_name)
    if st.state != CIRCUIT_STATE_OPEN:
        return False
    if st.cooldown_until is not None and when < st.cooldown_until:
        return False
    st.state = CIRCUIT_STATE_HALF_OPEN
    st.half_open_probe_available = True
    st.retry_eligible = False
    return True


def record_simulated_adapter_failure(
    adapter_name: str,
    *,
    reason: str,
    classification: str = FAILURE_CLASSIFICATION_TRANSIENT,
    now: datetime | None = None,
) -> None:
    """Increment consecutive failures and optionally open the breaker (simulation bookkeeping)."""
    _apply_failure_increment(
        _get_circuit_state(adapter_name),
        reason=str(reason),
        classification=str(classification).strip().lower() or FAILURE_CLASSIFICATION_TRANSIENT,
        now=now if now is not None else _utc_now(),
    )


def record_simulated_adapter_success(adapter_name: str) -> None:
    """Reset consecutive failures to a closed healthy state."""
    st = _get_circuit_state(adapter_name)
    _reset_to_closed_success(st)


def _reset_to_closed_success(st: _SimulatedCircuitBreakerState) -> None:
    st.state = CIRCUIT_STATE_CLOSED
    st.consecutive_failures = 0
    st.opened_at = None
    st.cooldown_until = None
    st.last_failure_reason = None
    st.last_failure_classification = None
    st.retry_eligible = True
    st.half_open_probe_available = False


def _force_open(st: _SimulatedCircuitBreakerState, reason: str, classification: str, now: datetime) -> None:
    st.state = CIRCUIT_STATE_OPEN
    st.opened_at = now
    st.last_failure_reason = reason
    st.last_failure_classification = classification
    st.cooldown_until = now + timedelta(seconds=st.cooldown_seconds)
    st.retry_eligible = False
    st.half_open_probe_available = False
    if st.consecutive_failures < st.failure_threshold:
        st.consecutive_failures = st.failure_threshold


def _apply_failure_increment(
    st: _SimulatedCircuitBreakerState,
    *,
    reason: str,
    classification: str,
    now: datetime,
) -> None:
    if st.state == CIRCUIT_STATE_OPEN:
        return
    st.last_failure_reason = reason
    st.last_failure_classification = classification
    if classification == FAILURE_CLASSIFICATION_NON_TRANSIENT:
        _force_open(st, reason, classification, now)
        return
    st.consecutive_failures += 1
    if st.consecutive_failures >= st.failure_threshold:
        _force_open(st, reason, classification, now)
        return
    st.retry_eligible = classification == FAILURE_CLASSIFICATION_TRANSIENT


def _complete_half_open_failure(st: _SimulatedCircuitBreakerState, reason: str, now: datetime) -> None:
    st.state = CIRCUIT_STATE_OPEN
    st.opened_at = now
    st.last_failure_reason = reason
    st.last_failure_classification = FAILURE_CLASSIFICATION_TRANSIENT
    st.cooldown_until = now + timedelta(seconds=st.cooldown_seconds)
    st.retry_eligible = False
    st.half_open_probe_available = False


def _merge_result_circuit_metadata(adapter_name: str, result: dict[str, Any], *, now: datetime) -> None:
    meta = result.setdefault("metadata", {})
    if not isinstance(meta, dict):
        return
    snap = get_simulated_circuit_breaker_dict(adapter_name, now=now)
    meta.setdefault("circuit_state", snap["state"])
    meta.setdefault("retry_eligible", snap["retry_eligible"])
    if "timeout_seconds" not in meta and snap.get("timeout_seconds") is not None:
        meta["timeout_seconds"] = snap["timeout_seconds"]


def _integrate_circuit_after_simulation(
    adapter_name: str,
    result_dict: dict[str, Any],
    *,
    was_half_open: bool,
    now: datetime,
) -> None:
    st = _get_circuit_state(adapter_name)
    success = bool(result_dict.get("success"))
    meta = result_dict.get("metadata")
    if not isinstance(meta, dict):
        meta = {}
        result_dict["metadata"] = meta
    classification = str(
        meta.get("failure_classification") or FAILURE_CLASSIFICATION_TRANSIENT
    ).strip().lower()

    if success:
        _reset_to_closed_success(st)
        meta["circuit_state"] = CIRCUIT_STATE_CLOSED
        meta["retry_eligible"] = True
        return

    if was_half_open:
        _complete_half_open_failure(st, str(result_dict.get("message") or "half_open probe failed"), now)
    else:
        _apply_failure_increment(
            st,
            reason=str(result_dict.get("message") or "simulated failure"),
            classification=classification,
            now=now,
        )
    meta["circuit_state"] = st.state
    meta["failure_classification"] = (
        FAILURE_CLASSIFICATION_CIRCUIT_OPEN
        if st.state == CIRCUIT_STATE_OPEN and was_half_open
        else classification
    )
    meta["retry_eligible"] = _compute_retry_eligible(st, now)


class BaseIntegration:
    adapter_name = "base"
    supported_actions: frozenset[str] = frozenset()

    def __init__(self, mode: str = SIMULATION_MODE):
        normalized_mode = (mode or SIMULATION_MODE).strip().lower()
        if normalized_mode != SIMULATION_MODE:
            raise NotImplementedError("real integration mode is not implemented")
        self.mode = normalized_mode

    def can_handle(self, action: str) -> bool:
        return self._normalize_action(action) in self.supported_actions

    def execute(
        self,
        action: str,
        params: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_action = self._normalize_action(action)
        safe_params = sanitize_payload(params)
        safe_context = sanitize_payload(context)
        now = _utc_now()
        st = _get_circuit_state(self.adapter_name)

        if st.state not in _VALID_CIRCUIT_STATES:
            res = self._result(
                normalized_action or "unspecified",
                safe_params,
                safe_context,
                success=False,
                message="Simulated execution blocked: circuit breaker state is invalid.",
                metadata={
                    "failure_classification": FAILURE_CLASSIFICATION_CIRCUIT_STATE_INVALID,
                    "circuit_state": CIRCUIT_STATE_OPEN,
                    "retry_eligible": False,
                    "timeout_seconds": st.timeout_seconds,
                },
            )
            _merge_result_circuit_metadata(self.adapter_name, res, now=now)
            return res

        if st.state == CIRCUIT_STATE_OPEN:
            res = self._result(
                normalized_action or "unspecified",
                safe_params,
                safe_context,
                success=False,
                message="Simulated execution blocked: integration circuit breaker is open.",
                metadata={
                    "failure_classification": FAILURE_CLASSIFICATION_CIRCUIT_OPEN,
                    "circuit_state": CIRCUIT_STATE_OPEN,
                    "retry_eligible": False,
                    "timeout_seconds": st.timeout_seconds,
                },
            )
            _merge_result_circuit_metadata(self.adapter_name, res, now=now)
            return res

        if st.state == CIRCUIT_STATE_HALF_OPEN:
            if not st.half_open_probe_available:
                res = self._result(
                    normalized_action or "unspecified",
                    safe_params,
                    safe_context,
                    success=False,
                    message=(
                        "Simulated execution blocked: half-open recovery probe was already used."
                    ),
                    metadata={
                        "failure_classification": FAILURE_CLASSIFICATION_CIRCUIT_OPEN,
                        "circuit_state": CIRCUIT_STATE_HALF_OPEN,
                        "retry_eligible": False,
                        "timeout_seconds": st.timeout_seconds,
                    },
                )
                _merge_result_circuit_metadata(self.adapter_name, res, now=now)
                return res
            st.half_open_probe_available = False

        was_half_open = st.state == CIRCUIT_STATE_HALF_OPEN

        if not self.can_handle(normalized_action):
            _apply_failure_increment(
                st,
                reason=(
                    f"Unsupported simulated {self.adapter_name} action: "
                    f"{normalized_action or 'unspecified'}"
                ),
                classification=FAILURE_CLASSIFICATION_NON_TRANSIENT,
                now=now,
            )
            res = self._result(
                normalized_action or "unspecified",
                safe_params,
                safe_context,
                success=False,
                message=(
                    f"Unsupported simulated {self.adapter_name} action: "
                    f"{normalized_action or 'unspecified'}"
                ),
                metadata={
                    "failure_classification": FAILURE_CLASSIFICATION_NON_TRANSIENT,
                    "circuit_state": st.state,
                    "retry_eligible": _compute_retry_eligible(st, now),
                    "timeout_seconds": st.timeout_seconds,
                },
            )
            _merge_result_circuit_metadata(self.adapter_name, res, now=now)
            return res

        try:
            result = self._simulate(normalized_action, safe_params, safe_context)
        except Exception as exc:
            if was_half_open:
                _complete_half_open_failure(
                    st,
                    f"simulation error: {exc}",
                    now,
                )
                result = self._result(
                    normalized_action,
                    safe_params,
                    safe_context,
                    success=False,
                    message=f"Simulated execution error: {exc}",
                    metadata={
                        "failure_classification": FAILURE_CLASSIFICATION_CIRCUIT_OPEN,
                        "circuit_state": CIRCUIT_STATE_OPEN,
                        "retry_eligible": False,
                        "timeout_seconds": st.timeout_seconds,
                    },
                )
                _merge_result_circuit_metadata(self.adapter_name, result, now=now)
                return result
            raise

        if not isinstance(result, dict):
            result = self._result(
                normalized_action,
                safe_params,
                safe_context,
                success=False,
                message="Adapter returned invalid simulation result.",
                metadata={"failure_classification": FAILURE_CLASSIFICATION_NON_TRANSIENT},
            )
        _integrate_circuit_after_simulation(
            self.adapter_name,
            result,
            was_half_open=was_half_open,
            now=now,
        )
        _merge_result_circuit_metadata(self.adapter_name, result, now=now)
        return result

    def _simulate(
        self,
        action: str,
        params: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return self._result(
            action,
            params,
            context,
            success=True,
            message=f"Simulated {self.adapter_name} action.",
        )

    def _result(
        self,
        action: str,
        params: dict[str, Any],
        context: dict[str, Any],
        *,
        success: bool,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return IntegrationResult(
            adapter=self.adapter_name,
            action=action,
            mode=SIMULATION_MODE,
            simulated=True,
            executed=False,
            success=success,
            message=message,
            params=params,
            context=context,
            metadata=metadata or {},
        ).as_dict()

    @staticmethod
    def _normalize_action(action: str | None) -> str:
        return str(action or "").strip().lower()


def sanitize_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    return {str(key): _sanitize_value(str(key), value) for key, value in payload.items()}


def _sanitize_value(key: str, value: Any) -> Any:
    if key.lower() in SECRET_FIELD_NAMES:
        return "[redacted]"
    if isinstance(value, dict):
        return sanitize_payload(value)
    if isinstance(value, list):
        return [_sanitize_value("", item) for item in value]
    return value
