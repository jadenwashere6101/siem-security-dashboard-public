# Tasks: Real SOAR Integration Safety Model

Implementation is split into small, verifiable slices. Do not implement from this proposal step.
Each slice must pass the canonical regression suite before the next slice begins.

Canonical regression suite (run after every slice):
```bash
pytest tests/test_failed_login_detection.py tests/test_password_spraying_detection.py \
       tests/test_correlated_activity.py tests/test_targeted_correlation.py \
       tests/test_ingest_api_contracts.py tests/test_alert_mutation_api_contracts.py -v
```

---

## Pre-Implementation Review

- [x] Audit `integrations/slack_adapter.py` — confirm four-guard, timeout, retry classification,
      circuit breaker wiring, and delivery tracking are all present and complete.
- [x] Audit `integrations/teams_adapter.py` — same audit as Slack.
- [x] Audit `integrations/email_adapter.py` — confirm simulation-only, no real-mode path exists.
- [x] Audit `integrations/firewall_adapter.py` — confirm simulation-only, no real-mode path exists.
- [x] Audit `integrations/webhook_adapter.py` — confirm simulation-only, no real-mode path exists.
- [x] Audit `integrations/circuit_breaker.py` — document current state machine and confirm startup
      behavior (confirm state initializes to `closed` with no persistence).
- [x] Audit `integrations/integration_registry.py` — confirm how circuit breaker state is
      exposed and how adapters are registered.
- [x] Audit `engines/soar_action_worker.py` — confirm `APPROVAL_REQUIRED_ACTIONS` and check
      whether remediation approval is enforced at the playbook executor layer.
- [x] Audit `engines/playbook_step_executor.py` — confirm `_step_already_succeeded_in_log`
      and delivery dedup; identify where a pre-call idempotency check must be added for real
      remediation actions.
- [x] Audit `core/notification_delivery_store.py` — confirm idempotency key structure,
      deterministic key derivation, and existing dedup path.
- [x] Audit `core/dead_letter_store.py` / `engines/playbook_step_executor.py` —
      confirm `capture_failed_execution_dead_letter()` hardcodes `retryable=False`; plan the
      failure-class-to-retryable mapping fix.
- [x] Audit `core/audit_helpers.py` — confirm `log_audit_event()` call signature and available
      field set; plan the real-adapter-attempt audit event format.
- [x] Audit `routes/integration_routes.py` — confirm `GET /integrations/status` response shape
      and which readiness booleans are already exposed.
- [x] Confirm current latest migration number (expected: 0010) before any schema work.
- [x] Confirm `SOAR_REAL_EMAIL_ENABLED`, `SOAR_REAL_FIREWALL_ENABLED`, and
      `SOAR_REAL_WEBHOOK_ENABLED` env vars are not yet referenced anywhere in the codebase.
- [x] Document any additional gaps found during audit that affect the design.

---

## Slice 1 — Unified Safety Config and Registry Hardening

Goal: Enforce that the per-adapter four-guard model is the canonical pattern and that no adapter
can silently skip guard evaluation.

- [x] Add a `_validate_real_mode_guards(adapter_name, mode, env_flag, credential_env)` helper
      in `integrations/base_integration.py` (or a dedicated `integrations/adapter_guards.py`)
      that validates all four guards and returns a structured readiness dict with
      `real_mode_allowed`, `real_mode_status`, and `failure_classification` when failed.
- [x] Extend `integrations/integration_registry.py` to emit a structured startup log line when
      any adapter's circuit breaker state is initialized, indicating a reset-to-closed event.
- [x] Confirm `FirewallSimulationAdapter` has no real-mode code path and add a comment
      `# spec: SPEC-INTEG-005 — real firewall execution permanently blocked until separate
      approved design` at the class level.
- [x] Confirm `EmailSimulationAdapter` and `WebhookSimulationAdapter` are unconditionally
      simulation-only and add equivalent spec comments.
- [x] Add tests:
  - [x] `INTEGRATION_MODE=real` with no adapter-specific flag falls back to simulation for
        email, firewall, and webhook.
  - [x] Registry startup logs a structured circuit breaker reset event per adapter.
  - [x] `_validate_real_mode_guards` returns `real_mode_allowed: False` for each missing guard.
  - [x] Guard validation never logs credential values.

---

## Slice 2 — Dead Letter `retryable` Flag Fix

Goal: Make the `retryable` field in `soar_dead_letters` accurate so that operator-facing
filtering (`GET /dead-letters?retryable=true`) is meaningful.

- [x] In `engines/playbook_step_executor.py`, update `capture_failed_execution_dead_letter()` to
      derive `retryable` from the step's `failure_classification` field in `steps_log`.
- [x] Set `retryable=True` for transient/operator-actionable classes: `timeout`,
      `transient`, `rate_limited`, `adapter_timeout`, `transient_network_error`,
      `circuit_breaker_open`, `circuit_open`, `provider_rate_limited`,
      `adapter_simulation_failed`, and `temporary_provider_failure`.
- [x] Set `retryable=False` for non-actionable classes: `non_transient`,
      `credential_missing`, `credential_invalid`, `guard_failed`, `simulation_only`,
      `approval_expired`, `unsupported_action`, `malformed_payload`, and `unknown`.
- [x] Add tests:
  - [x] Dead letter captured after timeout failure has `retryable=True`.
  - [x] Dead letter captured after non-transient failure has `retryable=False`.
  - [x] Dead letter captured after circuit-open failure has `retryable=True`.
  - [x] `GET /dead-letters?retryable=true` returns only correctly flagged rows.
  - [x] Existing dead letter tests pass unchanged.
- [ ] Run canonical regression suite.

---

## Slice 3 — Audit Logging for Real Execution Attempts

Goal: Every real outbound call — success or failure — writes a structured, secret-free audit
log entry.

- [x] Define the `soar_real_adapter_attempt` audit event format in a constants file or in
      `core/audit_helpers.py` comments.
- [x] Add `_log_real_adapter_attempt(conn, result, context)` helper that calls
      `log_audit_event()` with the safe fields defined in design section 4.4.
- [x] Wire the helper into `integrations/slack_adapter.py` after real-mode path execution
      (success and failure).
- [x] Wire the helper into `integrations/teams_adapter.py` equivalently.
- [x] Add stub wiring points in `integrations/email_adapter.py` and
      `integrations/webhook_adapter.py` for when those adapters gain real-mode paths.
- [x] Add tests:
  - [x] Real Slack execution (mocked HTTP) writes exactly one audit event with safe fields.
  - [x] Audit event contains no webhook URL, token, header, or raw response.
  - [x] Audit event is not written for simulation-mode adapter calls.
  - [x] Audit event is written on both success and failure paths.
  - [x] Existing Slack and Teams tests pass unchanged.
- [x] Run canonical regression suite.

---

## Slice 4 — Rate Limiting and Notification Flood Protection

Goal: Add per-adapter in-process rate limiting so alert bursts cannot exhaust provider rate
limits or flood dead letters.

- [x] Add `integrations/adapter_rate_limiter.py` implementing a per-adapter sliding-window
      token bucket or fixed-window counter with configurable max sends and window in seconds.
- [x] Rate limiter state is in-process; document that it resets on restart.
- [x] Wire rate limiter into `SlackAdapter.execute()`: check before real outbound call; return
      `failure_classification: provider_rate_limited`, `retry_eligible: True` if cap exceeded.
- [x] Wire rate limiter into `TeamsAdapter.execute()` equivalently.
- [x] Add stub wiring points in email and webhook adapters.
- [x] Rate-limited results must not increment the circuit breaker failure counter.
- [x] Add configurable env vars: `SLACK_MAX_SENDS_PER_MINUTE`, `TEAMS_MAX_SENDS_PER_MINUTE`,
      `EMAIL_MAX_SENDS_PER_MINUTE`, `WEBHOOK_MAX_SENDS_PER_MINUTE` with conservative defaults
      (20 for Slack/Teams, 10 for Email, 30 for Webhook).
- [x] Add tests:
  - [x] Rate limiter blocks an over-threshold Slack call within a 60-second window.
  - [x] Rate-limited result has correct classification and `retry_eligible: True`.
  - [x] Circuit breaker failure count is not incremented for rate-limited calls.
  - [x] Simulation-mode calls bypass the rate limiter entirely.
  - [x] Rate limiter state resets between test invocations (isolated test fixture).
  - [x] Env vars override defaults correctly.
  - [x] Existing Slack and Teams adapter tests pass unchanged.
- [x] Run canonical regression suite.

---

## Slice 5 — Notification Delivery Dedup Pre-Call Check

Goal: Prevent duplicate real sends for the same step even when `steps_log` and
`last_completed_step` state diverges (e.g., during retry or manual re-dispatch).

- [x] In `engines/playbook_step_executor.py`, before dispatching a notification-type step to
      the adapter, query `notification_delivery_attempts` for an existing row with the same
      `idempotency_key` and `status=success` or `status=pending`.
- [x] If found, return a no-op result without calling the adapter:
      `failure_classification: duplicate_delivery`, `success: True`, `executed: False`.
- [x] Record the no-op in `steps_log` with `skipped: True` and the reason.
- [x] This check is a defensive second layer; the primary guard remains
      `_step_already_succeeded_in_log`. Both guards must be present.
- [x] Add tests:
  - [x] Step is skipped and adapter is not called when a success delivery record exists.
  - [x] No second `notification_delivery_attempts` row is created on skip.
  - [x] Step proceeds normally when no matching delivery record exists.
  - [x] No-op skip result is recorded in `steps_log` with correct fields.
  - [x] Existing executor tests pass unchanged.
- [ ] Run canonical regression suite.

---

## Slice 6 — Email Adapter Real-Mode Guard Path

Goal: Add a four-guard real-mode path to the Email adapter so it matches the Slack/Teams
pattern. Real Email mode remains disabled by default and requires a future staging smoke test.

- [ ] Create a new `EmailRealAdapter` class or extend `EmailSimulationAdapter` with the
      four-guard check: `INTEGRATION_MODE=real`, `SOAR_ENV=staging`,
      `SOAR_REAL_EMAIL_ENABLED=true`, non-empty `SMTP_HOST` and `SMTP_USERNAME`.
- [ ] Add timeout handling: `EMAIL_TIMEOUT_SECONDS` env var, default 10s.
- [ ] Add retry classification: SMTP 5xx / connection refused / timeout → `transient`;
      SMTP 4xx / bad credentials / rejected recipient → `non_transient`.
- [ ] Add circuit breaker wiring using existing `integrations/circuit_breaker.py` pattern.
- [ ] Add credential validation: fail closed if `SMTP_HOST` or `SMTP_USERNAME` is missing.
      `SMTP_PASSWORD` must never appear in any result field, log, or test output.
- [ ] Add rate limiter wiring (from Slice 4 stub).
- [ ] Add audit log wiring (from Slice 3 stub).
- [ ] Add allowlisted payload construction: recipient address, subject, safe body only.
      Raw event payloads, alert raw data, and credentials are forbidden.
- [ ] Update `GET /integrations/status` to include Email readiness fields:
      `smtp_configured`, `email_real_enabled`, `real_mode_allowed`.
- [ ] Add `docs/soar_email_staging_smoke_test_runbook.md` (parallel to Slack runbook).
- [ ] Add tests:
  - [ ] Default configuration keeps Email in simulation.
  - [ ] `INTEGRATION_MODE=real` without all four Email guards fails closed.
  - [ ] Missing `SMTP_HOST` fails closed; `smtp_configured: False` in status.
  - [ ] `SMTP_PASSWORD` does not appear in any test output, logs, or result fields.
  - [ ] Staging guards + mocked SMTP produces a success result with `mode: real`.
  - [ ] Timeout returns `failure_classification: timeout`, `retry_eligible: True`.
  - [ ] SMTP 5xx returns `failure_classification: transient`, `retry_eligible: True`.
  - [ ] SMTP 4xx returns `failure_classification: non_transient`, `retry_eligible: False`.
  - [ ] Open circuit breaker blocks before SMTP call.
  - [ ] Rate limiter blocks when cap exceeded.
  - [ ] Slack and Teams adapters are unaffected.
  - [ ] Firewall remains simulation-only.
- [ ] Run canonical regression suite.

---

## Slice 7 — Webhook Adapter Real-Mode Guard Path

Goal: Add a four-guard real-mode path to the Webhook adapter. Lower priority than Email.

- [ ] Add four-guard check: `INTEGRATION_MODE=real`, `SOAR_ENV=staging`,
      `SOAR_REAL_WEBHOOK_ENABLED=true`, non-empty `WEBHOOK_URL` with `https://` scheme.
- [ ] `http://` scheme in `WEBHOOK_URL` fails closed: `failure_classification: credential_invalid`.
- [ ] Add timeout (`WEBHOOK_TIMEOUT_SECONDS`, default 5s).
- [ ] Add retry classification: connection refused / timeout / 5xx → `transient`;
      4xx / malformed payload → `non_transient`.
- [ ] Add circuit breaker wiring.
- [ ] Add rate limiter wiring.
- [ ] Add audit log wiring.
- [ ] Payload allowlist: safe alert reference fields only. No raw payloads, no credentials.
- [ ] `WEBHOOK_URL` must never appear in logs, results, or test output.
- [ ] Update `GET /integrations/status` to include Webhook readiness fields.
- [ ] Add `docs/soar_webhook_staging_smoke_test_runbook.md`.
- [ ] Add tests mirroring the Email test set for Webhook-specific behavior.
- [ ] Run canonical regression suite.

---

## Slice 8 — Firewall Dry-Run Safety Gate Documentation

Goal: Formally document the constraints that must be satisfied before a future spec can promote
firewall from dry-run to real. This slice is documentation and code comments only — no new code.

- [ ] Add a `# spec: SPEC-INTEG-005 — real firewall execution permanently blocked` comment
      to `integrations/firewall_adapter.py` and `integrations/soar_adapters/linux_firewall.py`.
- [ ] Add a section to `docs/soar_playbook_worker_daemon_runbook.md` documenting firewall
      promotion prerequisites (protected-target policy, dual approval gate, idempotency key,
      staging smoke test, no autonomous retries).
- [ ] Update `openspec/spec-index.md` with `SPEC-INTEG-005` entry pointing to this change.
- [ ] No code changes to firewall adapter behavior.
- [ ] Run canonical regression suite to confirm no regressions.

---

## Slice 9 — Teams Staging Smoke Test

Goal: Execute the controlled Teams staging smoke test following the existing runbook. This slice
is an operational step, not a code implementation.

Prerequisites:
- Microsoft 365 enterprise tenant with webhook-capable Teams environment available.
- All four Teams guards confirmed set.
- Teams circuit breaker in `closed` state verified via `GET /integrations/status`.

Steps (from `docs/soar_teams_staging_smoke_test_runbook.md`):
- [ ] Set all four Teams guards in staging environment.
- [ ] Verify `GET /integrations/status` shows Teams real-mode ready without revealing webhook.
- [ ] Run controlled single-execution `notify_teams`-only playbook via manual executor.
- [ ] Confirm exactly one Teams message arrives.
- [ ] Confirm `steps_log`, audit output, and delivery records contain no webhook URL.
- [ ] Capture evidence: delivery row, metrics, steps_log, API responses.
- [ ] Roll back: unset `SOAR_REAL_TEAMS_ENABLED` and `TEAMS_WEBHOOK_URL`.
- [ ] Confirm `GET /integrations/status` shows Teams in simulation/fail-closed.
- [ ] Archive `add-soar-real-teams-smoke-test-checklist` OpenSpec after evidence captured.

---

## Verification Planning

After all slices:
- [ ] Run full adapter test suite: `pytest tests/test_integration_adapters.py tests/test_integration_routes.py -v`
- [ ] Run executor tests: `pytest tests/test_playbook_step_executor.py -v`
- [ ] Run dead letter tests: `pytest tests/test_dead_letter_store.py tests/test_dead_letter_routes.py -v`
- [ ] Run metrics tests: `pytest tests/test_metrics_routes.py -v`
- [ ] Run Slack adapter tests: `pytest tests/test_slack_adapter.py -v`
- [ ] Run Teams adapter tests: `pytest tests/test_teams_adapter.py -v`
- [ ] Run canonical regression suite.
- [ ] Confirm `git status` shows no untracked credential files.
- [ ] Confirm `GET /integrations/status` shows all adapters in simulation/fail-closed mode.

---

## Safety Boundaries

- [ ] Do not change ingest transaction flow.
- [ ] Do not change detection internals.
- [ ] Do not change correlation internals.
- [ ] Do not add real firewall execution, `subprocess` calls, or `blocked_ips` mutations.
- [ ] Do not enable real mode for Email, Webhook, or Firewall outside of explicitly staged,
      smoke-test-guarded slices.
- [ ] Do not add autonomous retry loops, daemons, cron jobs, or schedulers.
- [ ] Do not store credentials in the database.
- [ ] Do not commit `.env` files or credential values to version control.
- [ ] Do not run real outbound calls in automated tests.
- [ ] Do not create destructive migrations.
- [ ] Do not modify the VM or live database outside of formally requested deployment steps.
- [ ] Do not expand approval bypass for any remediation action.
- [ ] Do not remove or weaken `APPROVAL_REQUIRED_ACTIONS` gate in `soar_action_worker.py`.
