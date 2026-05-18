# Design: Real SOAR Integration Safety Model

## Overview

This design defines the unified safety model governing all SOAR integration adapters as they
transition from simulation-only to controlled real-mode readiness. It extends the proven
four-guard pattern from Slack and Teams, adds missing safety layers, and sets permanent
constraints for the highest-risk adapter (firewall).

The design builds on existing systems:
- `integrations/` adapter registry and base class
- `integrations/circuit_breaker.py` in-process circuit breaker
- `integrations/slack_adapter.py` and `integrations/teams_adapter.py` four-guard patterns
- `core/notification_delivery_store.py` idempotency and delivery tracking
- `engines/soar_action_worker.py` APPROVAL_REQUIRED_ACTIONS gate
- `engines/playbook_step_executor.py` step execution and adapter dispatch
- `core/dead_letter_store.py` failure capture
- `core/audit_helpers.py` structured audit logging
- `routes/integration_routes.py` status API and circuit breaker controls

No autonomous retry behavior, daemon changes, scheduler changes, ingest changes, detection changes,
or correlation changes are introduced.

---

## 1. Integration Safety Model

### 1.1 Default Behavior

`INTEGRATION_MODE` defaults to `simulation`. All adapters must simulate unless an explicit,
validated, provider-specific set of guards is satisfied simultaneously. A missing, empty, or
unrecognized `INTEGRATION_MODE` value fails closed to simulation.

### 1.2 Per-Adapter Enable Flags

The four-guard pattern established for Slack and Teams is the canonical model for all adapters
that may eventually gain real-mode support:

```
INTEGRATION_MODE=real         # global mode must be explicitly real
SOAR_ENV=staging              # environment must be staging
SOAR_REAL_<ADAPTER>_ENABLED=true   # adapter-specific opt-in flag
<ADAPTER>_CREDENTIAL_ENV=...  # non-empty, validated credential env var
```

Adapters that must remain simulation-only permanently (firewall in this spec) must not expose a
real-mode enable flag. Any attempt to set `INTEGRATION_MODE=real` for those adapters must fail
closed and log a structured warning without raising an unhandled exception.

Implemented current state:
- Slack: four-guard complete (`SOAR_REAL_SLACK_ENABLED`, `SLACK_WEBHOOK_URL`). Smoke test done.
- Teams: four-guard complete (`SOAR_REAL_TEAMS_ENABLED`, `TEAMS_WEBHOOK_URL`). Smoke test pending.
- Email: four-guard complete (`SOAR_REAL_EMAIL_ENABLED`, `SMTP_HOST`, `SMTP_USERNAME`).
  Staging smoke test pending.
- Firewall: no real-mode guard path. Simulation-only; real promotion permanently blocked by this
  spec until a separate approved design explicitly overrides this constraint.
- Webhook: four-guard complete (`SOAR_REAL_WEBHOOK_ENABLED`, `WEBHOOK_URL` or
  `WEBHOOK_BASE_URL`). Staging smoke test pending.

### 1.3 Credential Validation

All credential env vars must be validated before any real outbound call:
- Non-empty after stripping whitespace.
- Valid scheme for URL-based credentials (must be `https://` for webhook URLs; `http://` fails closed).
- Credentials must never be logged, stored in the database, returned in any API response, included
  in `steps_log` output, or embedded in audit log detail fields. Booleans only: `webhook_configured`,
  `smtp_configured`, etc.
- Invalid or missing credentials fail closed: adapter returns simulation result with
  `failure_classification: credential_missing` or `credential_invalid` and `real_mode_allowed: false`.

### 1.4 No Real Execution During Tests

All automated tests must run with simulation mode enforced. The test suite must not depend on
provider credentials or real network connectivity for any test.

Required guarantees:
- `SOAR_REAL_<ADAPTER>_ENABLED` must be unset or `false` in all pytest runs.
- Tests must mock the adapter's outbound HTTP or transport method — not the public `execute()`
  interface — so that any unmocked outbound call fails the test with a network error.
- Test fixtures must assert that no real calls were made when testing simulation paths.
- No snapshot, log assertion, or test output may contain credential values.

---

## 2. Adapter Hardening

### 2.1 Uniform Adapter Result Contract

All adapter `execute()` calls must return a dict conforming to the base result shape defined in
`integrations/base_integration.py`. Real-mode calls must include additional fields:

```python
{
  "adapter":                str,          # adapter name
  "action":                 str,          # action name
  "mode":                   str,          # "simulation" or "real"
  "simulated":              bool,
  "executed":               bool,         # True only if outbound call completed without error
  "success":                bool,
  "message":                str,
  "failure_classification":  str | None,  # see section 2.2
  "retry_eligible":         bool,
  "timeout_seconds":        int | None,
  "elapsed_ms":             int | None,   # real mode only, omitted on timeout
  "circuit_breaker_state":  str,          # "closed", "open", or "half_open"
  "metadata":               dict,         # safe fields only, no secrets
}
```

Simulation results set `simulated: true`, `executed: false`, `mode: "simulation"`.

### 2.2 Failure Classification

All adapters must classify failures into one of the following categories, used by the circuit
breaker, retry eligibility metadata, and dead-letter capture:

| Class | Meaning | Retry eligible |
|---|---|---|
| `timeout` | Request timed out before response | Yes |
| `transient` | 5xx or provider-side error | Yes |
| `non_transient` | 4xx, malformed payload, bad credentials | No |
| `circuit_open` | Breaker was open before call | No |
| `credential_missing` | Required env var absent or empty | No |
| `credential_invalid` | Env var present but invalid format | No |
| `rate_limited` | Provider rate limit response received | Yes, after delay |
| `simulation_only` | Adapter does not support real mode | No |
| `guard_failed` | One or more four-guard checks not satisfied | No |
| `unknown` | Unclassified error | No (conservative default) |

Retry eligibility metadata is advisory. Circuit breaker state and playbook execution reliability
limits remain authoritative.

### 2.3 Timeout Policy

Every real outbound call must have an explicit timeout. Timeouts must not start background retries,
queue replay, daemon behavior, or autonomous recovery.

Default timeouts per adapter:

| Adapter | Default | Config env var |
|---|---|---|
| Slack | 3s (already implemented) | `SLACK_TIMEOUT_SECONDS` |
| Teams | 3s (already implemented) | `TEAMS_TIMEOUT_SECONDS` |
| Email (SMTP) | 10s | `EMAIL_TIMEOUT_SECONDS` |
| Webhook | 5s | `WEBHOOK_TIMEOUT_SECONDS` |
| Firewall | N/A (simulation-only) | — |

Timeout failures produce `failure_classification: timeout`, `retry_eligible: true`, and structured
elapsed/timeout metadata in the result. They do not raise unhandled exceptions.

### 2.4 Circuit Breaker Wiring

All adapters must check circuit breaker state before every real outbound call, using the existing
`integrations/circuit_breaker.py` pattern. Circuit breaker behavior:

- `closed`: allow the call.
- `open`: fail closed immediately with `failure_classification: circuit_open`. Do not call the
  transport layer.
- `half_open`: allow at most one probe call. On probe success, transition to `closed`. On probe
  failure, transition back to `open`.
- Unknown or invalid state: fail closed.

Transient failures and timeouts increment the circuit breaker's consecutive failure counter.
Non-transient failures (credential errors, guard failures) must not update the failure counter —
they represent configuration problems, not adapter instability.

**Circuit breaker persistence**: In-process state resets on worker restart. Until a persistent
circuit breaker design is approved (out of scope for this spec), the adapter registry must log a
structured startup event indicating that circuit breaker state has been reset to `closed`. This
provides an audit trail of resets without requiring a persistence layer. A future spec may add
a lightweight `integration_circuit_state` DB table.

### 2.5 Slack Adapter

Current state: four-guard complete, timeout implemented, retry classification implemented, circuit
breaker wired, staging smoke test complete, system returned to simulation.

Gaps addressed in this spec's implementation:
- Add rate limiting (see section 3).
- Add structured audit log entry for every real outbound attempt (see section 5.3).
- Document that `SLACK_WEBHOOK_URL` must be `https://` scheme; `http://` fails closed.

### 2.6 Teams Adapter

Current state: four-guard complete, timeout implemented, retry classification implemented, circuit
breaker wired. Staging smoke test not yet performed (environment blocker).

Gaps addressed in this spec's implementation:
- Add rate limiting (see section 3).
- Add structured audit log entry for every real outbound attempt.
- Confirm `TEAMS_WEBHOOK_URL` scheme validation matches Slack pattern.

Teams smoke test is a prerequisite for enabling Teams real mode in any deployment. It must follow
`docs/soar_teams_staging_smoke_test_runbook.md`.

### 2.7 Email Adapter

Current state: guarded real-mode path implemented in `EmailSimulationAdapter`; simulation remains
the default and staging smoke test evidence is still required before operational enablement.

Implemented real-mode readiness:
- Add four-guard pattern: `INTEGRATION_MODE=real`, `SOAR_ENV=staging`,
  `SOAR_REAL_EMAIL_ENABLED=true`, non-empty `SMTP_HOST` and `SMTP_USERNAME`.
- Add timeout (`EMAIL_TIMEOUT_SECONDS`, default 10s).
- Safe failure classification: timeout, invalid credentials, provider rate limiting,
  transient network error, malformed payload, and temporary provider failure.
- Circuit breaker wiring.
- Rate limiting (see section 3).
- Credential validation without exposing SMTP password or host in results or logs.
- Structured audit log entry for every real outbound attempt.
- Allowlisted payload construction: recipient address, subject line, and body must use bounded
  safe fields only. Raw event payloads, credentials, and alert raw data are forbidden.
- Secret redaction: `SMTP_HOST` may be logged as a boolean `smtp_configured`. `SMTP_PASSWORD`
  must never appear in logs, audit records, steps_log, or status API responses.

Email real mode is staging-only. It must not be enabled in production until a separate staging
smoke test is completed and evidence is captured.

### 2.8 Firewall Adapter

Current state: simulation-only (`FirewallSimulationAdapter`). Supported actions: `block_ip`,
`unblock_ip`, `tag_ip`.

**Permanent constraint in this spec:** Real firewall execution — any call that mutates a live
firewall, network ACL, cloud security group, or the `blocked_ips` database table via external
system integration — is out of scope for this spec. It requires a separate future approved design
that explicitly grants permission.

Dry-run safety gates (required before any future real-mode promotion):
- The `LinuxFirewallDryRunAdapter` in `integrations/soar_adapters/linux_firewall.py` exists and
  enforces protected-target policy before command-plan construction. This is the maximum firewall
  integration depth permitted by this spec.
- Any future firewall real-mode spec must confirm: protected-target policy enforced, approval gate
  required at both the playbook executor level and the response-action queue level, idempotency
  key checked before any external call, circuit breaker in `closed` state, and a staging-only
  smoke test runbook completed before production.
- The `blocked_ips` table must never be written by a real firewall adapter call until an approved
  future design explicitly permits it.

### 2.9 Webhook Adapter

Current state: guarded real-mode path implemented in `WebhookSimulationAdapter`; simulation
remains the default and staging smoke test evidence is still required before operational enablement.

Implemented real-mode readiness:
- Four-guard pattern: `INTEGRATION_MODE=real`, `SOAR_ENV=staging`,
  `SOAR_REAL_WEBHOOK_ENABLED=true`, non-empty `WEBHOOK_URL`.
- `WEBHOOK_URL` must be `https://` scheme; `http://` fails closed.
- Timeout (`WEBHOOK_TIMEOUT_SECONDS`, default 5s).
- Safe failure classification for timeout, invalid target/credential, provider rate limiting,
  transient network errors, malformed payloads, and temporary provider failures.
- Circuit breaker wiring.
- Rate limiting (see section 3).
- Credential validation without exposing `WEBHOOK_URL` or authentication headers.
- Structured audit log entry for every real outbound attempt.
- Webhook payloads must be allowlisted. Raw alert payloads, credentials, and internal DB IDs
  beyond safe reference fields are forbidden.

---

## 3. Rate Limiting and Notification Flood Protection

No rate limiting exists in the current integration layer. A burst of HIGH/CRITICAL alerts can
trigger multiple concurrent `notify_slack` or `notify_email` steps. Without rate limiting, a
single alert flood could exhaust provider rate limits, fill the dead-letter queue, and open the
circuit breaker — causing legitimate notifications to be blocked for subsequent real events.

### 3.1 Per-Adapter Send Cap

Implement a lightweight in-process rate limiter for notification adapters (Slack, Teams, Email,
Webhook). The limiter tracks send timestamps per adapter and blocks execution if the send rate
exceeds a configurable threshold.

Configuration env vars:

| Adapter | Max sends per window | Window | Env var |
|---|---|---|---|
| Slack | 20 | 60s | `SLACK_MAX_SENDS_PER_MINUTE` |
| Teams | 20 | 60s | `TEAMS_MAX_SENDS_PER_MINUTE` |
| Email | 10 | 60s | `EMAIL_MAX_SENDS_PER_MINUTE` |
| Webhook | 30 | 60s | `WEBHOOK_MAX_SENDS_PER_MINUTE` |

The defaults above are conservative. Operators may increase limits via env vars.

When rate limit is exceeded:
- The adapter returns a structured result with `failure_classification: rate_limited`,
  `success: false`, `retry_eligible: true`.
- The circuit breaker is not incremented for rate-limit failures — they are a local policy
  decision, not an adapter instability signal.
- The step records the failure in `steps_log` and is subject to existing playbook retry policy.

Rate limiter state is in-process. It resets on worker restart. This is acceptable for the initial
implementation; a future hardening spec may move to a shared DB-backed counter.

### 3.2 Deduplication Window for Notifications

Notification steps that share the same `idempotency_key` (deterministic from provider + execution
+ step index + action, as defined in `core/notification_delivery_store.py`) must not re-send if
a successful delivery record already exists for that key.

The executor already checks `_step_already_succeeded_in_log` before dispatching. The adapter must
additionally check `notification_delivery_attempts` for an existing `success` row matching the
idempotency key before making an outbound call. This prevents duplicate sends on manual retry or
daemon re-pick after a DB write failure.

Result when dedup fires: `failure_classification: already_delivered`, `success: true` (idempotent
no-op), `executed: false`, `simulated: false`.

---

## 4. Execution Safety

### 4.1 Approval Gating for Real Remediation

`APPROVAL_REQUIRED_ACTIONS` in `engines/soar_action_worker.py` gates `block_ip` at the
response-action queue layer. This gate must also be enforced at the playbook executor layer for
any adapter-backed step that constitutes a remediation action.

Rule: Any playbook step whose `action` maps to a remediation handler (`block_ip`, `unblock_ip`,
`tag_ip`) must check whether an approved `approval_requests` row exists for the current
`(playbook_execution_id, step_index)` before dispatching to the adapter. If no approved row exists,
the step must pause with `awaiting_approval` status exactly as `require_approval` steps do.

Notification-only actions (`notify_slack`, `notify_teams`, `notify_email`, `notify_webhook`) do
not require approval gates. They must still respect circuit breaker, rate limiting, and idempotency.

### 4.2 Idempotency for Real Actions

Notification delivery idempotency is already enforced through deterministic `idempotency_key`
in `notification_delivery_attempts`.

For real remediation actions (currently out of scope for execution, but defined here for future
use):
- Each real remediation call must generate a deterministic idempotency key:
  `sha256(action_type + target + playbook_execution_id + step_index)`.
- Before dispatching to the adapter, check whether the key already exists in
  `response_actions_log` with `status=success`.
- If found: return a no-op result with `failure_classification: already_executed`.
- If not found: proceed with the adapter call, then write the idempotency key to
  `response_actions_log` atomically with the action result.
- The key constraint prevents double-block of the same IP by the same playbook step on retry.

### 4.3 Dead-Letter Behavior

Failed real adapter calls that exhaust retry eligibility must be captured by the existing
`capture_failed_execution_dead_letter()` path in `engines/playbook_step_executor.py`.

The `failure_class` field written to `soar_dead_letters` must reflect the adapter's
`failure_classification`. The `retryable` field must be set to `True` for the following
failure classes: `timeout`, `transient`, `rate_limited`. All other classes default to `retryable: False`.

This resolves the existing gap noted in the handoff: the `retryable` flag is currently hardcoded
to `False` for all dead letters. This spec's implementation must update
`capture_failed_execution_dead_letter()` to set `retryable` based on `failure_classification`.

### 4.4 Audit Logging for Real Execution Attempts

Every real outbound integration attempt — success or failure — must write a structured audit log
entry via `core/audit_helpers.log_audit_event()`.

Required fields (all safe, no secrets):

```python
{
  "event_type": "soar_real_adapter_attempt",
  "adapter":    str,          # e.g. "slack", "email"
  "action":     str,          # e.g. "send_message", "send_email"
  "mode":       "real",
  "success":    bool,
  "failure_classification": str | None,
  "retry_eligible": bool,
  "circuit_breaker_state": str,
  "playbook_execution_id": int | None,
  "playbook_id": str | None,
  "step_index": int | None,
  "alert_id":   int | None,
  "incident_id": int | None,
  "elapsed_ms": int | None,
}
```

Fields must not include: webhook URLs, SMTP passwords, tokens, headers, raw request/response
bodies, or protected target details beyond safe display fields.

Simulation-mode adapter calls do not require audit log entries. Only real-mode attempts are
recorded.

---

## 5. Rollout Strategy

### 5.1 Simulation Validation Phase

Before enabling any adapter's real mode, the full automated test suite must pass with all adapters
in simulation. Run the canonical regression suite after every implementation slice:

```
pytest tests/test_failed_login_detection.py
pytest tests/test_password_spraying_detection.py
pytest tests/test_correlated_activity.py
pytest tests/test_targeted_correlation.py
pytest tests/test_ingest_api_contracts.py
pytest tests/test_alert_mutation_api_contracts.py
```

Plus adapter and executor focused suites:

```
pytest tests/test_integration_adapters.py tests/test_integration_routes.py
pytest tests/test_playbook_step_executor.py tests/test_playbook_routes.py
pytest tests/test_dead_letter_store.py tests/test_dead_letter_routes.py
```

### 5.2 Staging Order

Real-mode enablement must follow this order. No step may be skipped.

1. **Slack** — Complete. Smoke test done 2026-05-15. System in simulation.
2. **Teams** — Guards in place. Smoke test pending environment availability.
   Use `docs/soar_teams_staging_smoke_test_runbook.md`.
3. **Email** — Guards implemented. Staging smoke test pending.
   Use `docs/soar_email_staging_smoke_test_runbook.md`.
4. **Webhook** — Guards implemented. Staging smoke test pending.
   Use `docs/soar_webhook_staging_smoke_test_runbook.md`.
5. **Firewall** — Permanently blocked by this spec. Requires a separate future approved design.

### 5.3 Firewall Dry-Run Constraint

The `LinuxFirewallDryRunAdapter` in `integrations/soar_adapters/` is the maximum permitted
firewall integration depth in this spec. It builds a command plan only; it does not shell out,
does not call `subprocess`, and does not mutate any external system.

A future spec promoting firewall from dry-run to real must explicitly:
- Document that protected-target policy is enforced before any real call.
- Document that a human-approved `approval_requests` row is required.
- Confirm the idempotency key check prevents double-block.
- Document a staging rollback procedure.
- Confirm no automated retries can re-block a previously unblocked IP.

### 5.4 Rollback / Kill Switch

Rollback for any real-mode adapter is immediate and must require only env var changes:

1. Set `SOAR_REAL_<ADAPTER>_ENABLED=false` (or unset).
2. Optionally remove the credential env var.
3. Restart the application or worker.
4. Verify `GET /integrations/status` shows adapter in `simulation` mode.
5. Verify playbook executions using that adapter produce `simulated: true` results.

No schema changes, data migrations, queue redesigns, daemon changes, or frontend changes are
required for rollback. The kill switch must work within one deploy cycle.

---

## 6. Metrics and Observability

### 6.1 Per-Adapter Real vs Simulation Counts

`GET /metrics/notifications` currently aggregates from `notification_delivery_attempts` by
provider, mode, and status. This is sufficient for Slack/Teams. Email and Webhook delivery records
must be added to `notification_delivery_attempts` using the same append-only schema when their
real-mode paths are implemented.

No schema change is needed for this: `notification_delivery_attempts` already has a `mode` field
(`simulation` or `real`) and a `provider` field. Adding Email/Webhook delivery records uses the
existing schema.

### 6.2 Circuit Breaker State Visibility

`GET /integrations/status` already exposes per-adapter circuit breaker state. When the circuit
breaker resets on process restart (section 2.4), a structured log entry must be emitted so
operators can identify restart-induced state resets.

A future hardening spec may add a lightweight `integration_circuit_state` table for persistence.
Until then, startup reset events in structured logs are the observability mechanism.

### 6.3 Dead-Letter Failure Class Integration

`GET /metrics/dead-letters` already groups by `failure_class`. Once `retryable` is correctly
set by failure class (section 4.3), the `GET /dead-letters?retryable=true` filter becomes
operationally meaningful for operators identifying safe retry candidates.

No new route changes are required. The fix is in the capture helper.

### 6.4 Dashboard Updates

`SoarMetricsDashboard.js` includes a Notification Delivery section driven by
`GET /metrics/notifications`. No structural dashboard changes are required for this spec. If the
Email adapter adds delivery tracking to `notification_delivery_attempts`, its metrics will
automatically appear in the existing `by_provider` breakdown.

The integration status panel (`IntegrationStatusPanel.js`) will automatically reflect new
adapter real-mode readiness flags and circuit breaker state when the backend status API is
updated. No frontend changes are needed to surface new adapters if the status API contract is
preserved.

---

## 7. Safety Boundaries

These constraints are permanent for this spec and may not be overridden within it:

- `INTEGRATION_MODE=simulation` remains the default. Real mode requires explicit opt-in.
- No real firewall execution, blocklist mutation, or `subprocess` call.
- Email real mode: staging only, smoke-test runbook required before any staging enablement.
- Webhook real mode: staging only, smoke-test runbook required.
- No autonomous retries, daemon schedule, background replay, or Celery/Redis migration.
- No credential storage in the database.
- No real calls in automated tests for any adapter.
- Webhook URLs, SMTP passwords, and all credential values must never appear in logs, audit
  records, `steps_log`, status API responses, notification delivery records, or UI.
- Firewall real-mode promotion requires a separate future approved design. This spec does not
  grant that permission.
- Ingest, detection, and correlation internals must not be changed.
- Existing SOAR queue, approval, incident, and protected-target behavior must not be changed.
- Dead letter retry-execute for `notification_delivery` and `approval` source types remains
  deferred (existing constraint, unchanged by this spec).

## 8. Risks and Stop Conditions

| Risk | Mitigation |
|---|---|
| Email credentials leak into logs | Credential redaction enforced before result construction; no SMTP password in any structured field |
| Alert burst floods provider before rate limiter is in place | Rate limiter implemented in Slice 3 before Email/Webhook real-mode enablement |
| Circuit breaker resets on restart, sends to degraded provider | Startup log event alerts operators; future persistence spec tracks state |
| Firewall dry-run promotion attempted without approval gate | Spec explicitly blocks promotion; requires a future approved design |
| Teams smoke test run before runbook followed | `docs/soar_teams_staging_smoke_test_runbook.md` must be followed end-to-end; no ad-hoc test |
| Idempotency key collision produces false no-op | Key is deterministic from (action + target + execution_id + step_index); collision is intentional dedup |
| Real mode enabled in production prematurely | Four-guard requires `SOAR_ENV=staging`; production environment will fail the guard |

Stop and roll back if:
- Any real outbound call occurs during automated tests.
- Credential values appear in logs, audit records, steps_log, status APIs, or UI surfaces.
- Rate limiting or dedup logic is missing at the time any notification adapter goes real.
- Firewall adapter gains a real-mode code path without a separate approved design.
- Retry behavior becomes autonomous (no human action required to re-dispatch a failed real call).
- Ingest, detection, or correlation behavior changes.
