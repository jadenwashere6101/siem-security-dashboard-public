# Design: SOAR Integration Circuit Breaker Simulation

## Proposed architecture
Add simulation-mode circuit breaker semantics around integration adapter execution. The breaker should be checked before adapter-backed playbook steps run and should return a fail-closed simulated result when the adapter is not eligible to execute.

This design aligns with the roadmap's Phase 3 circuit breaker guidance while keeping the current architecture simulation-only. The goal is to validate adapter reliability behavior before any real outbound execution mode exists.

The implementation should remain explicit and operator-visible:
- No background worker opens, closes, or probes breakers.
- No autonomous retry loop replays failed executions.
- No real provider clients are created.
- No external services are contacted.

## Circuit breaker states
Each simulation adapter should expose one of three states:

- `closed`: Adapter is eligible for simulated execution. Consecutive failures are below threshold.
- `open`: Adapter is not eligible for simulated execution. Calls fail closed immediately with structured metadata.
- `half_open`: Adapter is eligible for a bounded manual probe only. A successful probe closes the breaker and resets consecutive failures. A failed probe reopens the breaker and records a new cooldown.

Unknown, corrupt, unsupported, or missing breaker state must fail closed. The safest fallback is `open` with a reason such as `circuit_state_invalid`.

## Consecutive failure tracking
Track consecutive simulated failures per adapter, not globally. The failure counter should reset only when a successful eligible simulated adapter execution or explicit successful probe occurs.

Suggested metadata:
- `adapter`: stable adapter name such as `slack`, `email`, `firewall`, or `webhook`.
- `state`: `closed`, `open`, or `half_open`.
- `consecutive_failures`: integer counter.
- `failure_threshold`: integer threshold that opens the breaker.
- `last_failure_at`: timestamp.
- `last_success_at`: timestamp.
- `opened_at`: timestamp.
- `cooldown_until`: timestamp.
- `last_failure_classification`: `transient`, `non_transient`, `timeout`, `circuit_open`, or similar.

State may initially be in memory or stored in a lightweight additive persistence layer if restart visibility is required. If state is in memory, restart ambiguity must be explicit in status output and must fail closed for any uncertain half-open probe state.

## Cooldown windows
When an adapter reaches the failure threshold, transition it to `open` and set `cooldown_until`.

While `open`:
- Adapter-backed steps must not call the adapter execution path.
- The result should be a structured simulated failure with `success: false`, `simulated: true`, `executed: false`, and `failure_classification: circuit_open`.
- The playbook executor should handle the result using existing bounded retry and failure semantics.
- The state should be visible through operator-facing integration status and metrics.

Cooldown expiration should not automatically run a probe. It only makes the adapter eligible for an explicit manual probe or the next explicitly requested simulation path to transition to `half_open`, depending on the implementation design. Avoid hidden autonomous behavior.

## Recovery probing behavior
Recovery probing should be explicit, bounded, and simulation-only.

Acceptable designs:
- A super-admin-only manual probe action that transitions `open` to `half_open` after cooldown.
- A one-shot simulation executor invocation may perform at most one `half_open` probe for an adapter whose cooldown has expired, if this behavior is clearly visible and bounded.

Probe rules:
- Only one probe should be allowed per adapter per cooldown window.
- A successful simulated probe sets state to `closed` and resets `consecutive_failures`.
- A failed simulated probe sets state to `open`, increments or records failure metadata, and starts a new cooldown.
- Probes must not contact Slack, email, webhook, firewall, PagerDuty, or any external API.
- Probes must not mutate `blocked_ips` or call subprocesses.

## Timeout metadata
Timeouts should be represented as explicit metadata on simulated adapter results and breaker state. Since adapters are simulation-only, timeout behavior may be injected by test fixtures, config, or adapter simulation parameters.

Suggested fields:
- `timeout_seconds`
- `timed_out`
- `elapsed_ms`
- `timeout_classification`
- `retry_eligible`

Timeout metadata must not introduce timers, daemon checks, async cancellation, or external network timeouts. It exists to validate classification and operator visibility before real adapters exist.

## Transient vs non-transient failures
Simulated adapter failures should be classified:

- `transient`: timeout-like, temporary unavailable, rate limited, or simulated provider unavailable. These may be retry eligible while bounded by playbook `max_attempts`, adapter retry metadata, and breaker state.
- `non_transient`: invalid configuration, unsupported action, malformed params, permission-like failures, or protected-target refusal. These should not be retry eligible.

Non-transient failures may open the breaker immediately if they indicate adapter configuration is unsafe. Protected-target refusals should remain fail-closed and must not mutate `blocked_ips`.

## Adapter-level retry eligibility metadata
Adapter results should expose retry metadata without starting retries:
- `retry_eligible`: boolean.
- `retry_after_seconds`: optional cooldown or suggested delay.
- `max_adapter_attempts`: optional adapter-level bound.
- `failure_classification`: transient/non-transient/timeout/circuit_open.
- `circuit_state`: current adapter breaker state.

Playbook execution should combine adapter retry metadata with existing playbook reliability safeguards. The stricter bound wins. No adapter metadata should cause automatic background retry.

## Fail-closed behavior
The circuit breaker must fail closed when:
- Breaker state is `open`.
- Breaker state is unknown or invalid.
- Adapter config is invalid.
- `INTEGRATION_MODE` is not `simulation`.
- A simulated timeout or non-transient unsafe failure occurs.
- A half-open probe fails.

Fail-closed means no adapter execution, no external calls, no queue enqueueing, and no real remediation. The playbook execution should receive a structured simulated failure and proceed through existing bounded failure handling.

## Interaction with playbook execution states
Circuit breaker failures should integrate with existing execution states:
- `pending`: eligible to be claimed only through existing manual executor invocation.
- `running`: adapter step checks breaker before simulated adapter call.
- `awaiting_approval`: breaker checks must not bypass approval gates.
- `failed`: ordinary terminal failure when retry may still be allowed by execution reliability metadata.
- `permanently_failed`: terminal state when retries or attempts are exhausted, including repeated circuit-open failures.
- `abandoned`: remains operator terminal and should not be resumed by breaker recovery.

Breaker failures must preserve immutable execution history. They may append structured step log entries, but must not rewrite prior terminal executions.

## Preventing alert storms
Alert storms are constrained by:
- Per-adapter failure thresholds.
- `open` state blocking repeated simulated adapter calls.
- Cooldown windows.
- One bounded half-open probe per cooldown.
- Existing playbook `max_attempts` and `permanently_failed` terminal state.
- Active execution uniqueness for active playbook executions.
- No daemon, scheduler, or autonomous retry loop.
- Metrics and status visibility so operators can see and disable problematic playbooks before real mode is ever designed.

## Operator-visible state exposure
Expose breaker state in operator-facing read paths, such as extending integration status data:

```json
{
  "name": "webhook",
  "mode": "simulation",
  "simulated": true,
  "supported_actions": ["post_event"],
  "circuit_breaker": {
    "state": "open",
    "consecutive_failures": 3,
    "failure_threshold": 3,
    "cooldown_until": "2026-05-10T18:30:00Z",
    "last_failure_classification": "timeout",
    "retry_eligible": false
  }
}
```

Analysts and super-admins may receive read-only visibility following existing integration status patterns. Any manual probe action, if implemented, should be super-admin-only and should remain simulation-only.

## Restart ambiguity
If breaker state is not persisted, restart behavior must be explicit and safe. The implementation should either:
- Rebuild state as `closed` only when there is no evidence of recent failures and status clearly reports state reset on restart, or
- Fail closed for ambiguous adapters until an operator explicitly probes or resets state.

Do not hide restart ambiguity. Operator visibility should show whether state is persisted, reset, or unknown.

## Safety boundaries
- Simulation-only.
- Fail-closed.
- Operator-visible.
- Explicit/manual recovery paths only.
- Bounded retries only.
- Preserve immutable execution history.
- No hidden autonomous behavior.
- No real outbound calls.
- No Slack, webhook, email, firewall, PagerDuty, or external service execution.
- No daemon or scheduler.
- No automatic autonomous retries.
- No background replay engine.
- No Redis/Celery/RQ migration.
- No ingest, detection, or correlation changes.
- No queue architecture rewrite.
- No `blocked_ips` mutation.
- No subprocess execution.
- No external API dependencies.
- No enabling `INTEGRATION_MODE=real`.

## Test strategy
Add backend tests that verify:
- Breaker states transition `closed` -> `open` after consecutive simulated failures.
- `open` adapters fail closed without calling adapter execution internals.
- Cooldown metadata is recorded and exposed.
- `half_open` probe success closes the breaker and resets consecutive failures.
- `half_open` probe failure reopens the breaker.
- Transient failures are retry eligible only within bounded playbook and adapter limits.
- Non-transient failures are not retry eligible.
- Timeout metadata is recorded without timers, daemon behavior, or network calls.
- Integration status exposes breaker state to authorized users.
- Circuit-open failures interact safely with `failed` and `permanently_failed` playbook execution states.
- Approval gates are not bypassed by breaker recovery or probing.
- No `blocked_ips` writes occur.
- No subprocess calls occur.
- No network calls or external API dependencies occur.
- `INTEGRATION_MODE=real` remains disabled/fail-closed.
- No SOAR queue architecture, ingest, detection, or correlation behavior changes.

## Risks and stop conditions
- Stop if implementation requires real provider clients, secrets, or network checks.
- Stop if implementation enables or depends on `INTEGRATION_MODE=real`.
- Stop if implementation introduces background retries, daemon workers, scheduling, or replay engines.
- Stop if circuit recovery can run unbounded probes or hidden retries.
- Stop if breaker failures rewrite immutable playbook execution history.
- Stop if integration reliability requires queue redesign or ingest/detection/correlation changes.
