# Proposal: Real SOAR Integration Safety Model

## Problem

Slack and Teams real-mode guardrails are implemented and Slack's staging smoke test is complete.
The four-guard pattern (`INTEGRATION_MODE=real`, `SOAR_ENV=staging`, `SOAR_REAL_<ADAPTER>_ENABLED`,
valid credential env var) is proven for notification-only providers. However, the project currently
has no unified safety model governing how the remaining adapters — email, firewall, webhook — gain
real-mode readiness, and several gaps remain even in the adapters that are already guarded:

- Email, firewall, and webhook adapters have no real-mode guard path, timeout policy, retry
  classification, or circuit breaker wiring. Adding real-mode support to any of these would require
  ad-hoc decisions with no governing spec.
- No rate limiting or notification flood protection exists. A burst of CRITICAL alerts triggering
  `notify_slack` or `notify_email` steps simultaneously has no per-adapter send cap.
- Circuit breaker state is in-process and resets on restart. A restarted worker re-enters `closed`
  state with no memory of recent failures, which removes the circuit breaker's protective effect
  across process boundaries.
- Firewall actions (`block_ip`, `unblock_ip`) are approval-gated at the response-action queue layer
  but lack an equivalent playbook-layer guard that verifies approval before any real firewall call.
- Idempotency guarantees for real actions are defined per-step in `notification_delivery_attempts`
  for notifications, but real remediation actions have no analogous idempotency enforcement.
- Audit logging is in place for approval decisions but not yet defined for real outbound integration
  execution attempts in a uniform way across adapters.

Without a governing design, each new real-mode adapter path will make independent decisions that
may conflict, produce inconsistent safety guarantees, or silently degrade the existing protections.

## Goal

Define a unified real integration safety model that governs how all current and future SOAR adapters
gain controlled real-mode readiness. The model must extend the proven Slack/Teams four-guard pattern,
add missing safety layers — rate limiting, circuit breaker persistence, uniform audit logging,
firewall promotion gates, and real-action idempotency — and define a staged rollout strategy that
keeps firewall execution out of scope until a separate approved design explicitly permits it.

## Scope

1. Unified per-adapter safety config model — canonical env var pattern, fail-closed defaults,
   no-network test guarantees for all adapters.
2. Adapter hardening for each integration in the current registry: Slack, Teams, Email, Firewall,
   Webhook — covering timeout policy, retry classification, circuit breaker wiring, and real-mode
   guard completeness.
3. Rate limiting and notification flood protection — per-adapter send caps and dedup windows for
   notification adapters.
4. Circuit breaker persistence design — defining the path from in-process state to durable state
   without requiring a Redis/Celery migration in this spec.
5. Execution safety — approval gating, idempotency, dead-letter integration, and audit logging for
   real action attempts across adapter types.
6. Rollout strategy — simulation validation, staging Slack/Email first, firewall dry-run
   constraints, smoke test runbooks, kill-switch procedures.
7. Observability — per-adapter real vs simulation counts, dead-letter failure class integration,
   and dashboard updates if needed.

## Out of Scope

- No code implementation in this proposal step.
- No schema changes until an approved implementation slice.
- No real firewall execution, blocklist mutation, or `subprocess` calls in this spec.
- No real email execution until guardrails are implemented and a staging environment is ready.
- No PagerDuty integration.
- No Redis/Celery migration for circuit breaker persistence.
- No ingest, detection, or correlation changes.
- No daemon or scheduler changes.
- No autonomous retry behavior.
- No credential storage in the database.
- No VM actions.

## Success Criteria

- Every adapter has a documented, tested, fail-closed real-mode guard path or a documented
  permanent simulation constraint.
- No real outbound call can occur in automated tests for any adapter.
- Notification adapters are rate-limited so alert bursts cannot flood a provider.
- Circuit breaker state is defined to be durable or fail-closed across restarts.
- Real action attempts are audit-logged with safe operational metadata and without secrets.
- Real remediation actions require an approval gate at the playbook execution layer, not only at
  the response-action queue layer.
- Firewall real-mode promotion is gated by a separate future approved design; this spec defines
  the intermediate dry-run safety constraints that must be in place first.
- Rollback for any real-mode adapter is immediate and requires only env var changes.

## Why Now

The simulation-first platform is complete. The daemonized worker core is ready but not deployed.
The next gate before enabling the daemon in production or expanding real integration coverage is
a governing safety model. Without it, each operator decision about enabling a real adapter becomes
a one-off judgment call with no written constraints. This spec defines those constraints before
any of them are acted on.
