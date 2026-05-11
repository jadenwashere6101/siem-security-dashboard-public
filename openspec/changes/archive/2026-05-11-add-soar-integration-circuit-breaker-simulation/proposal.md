# Proposal: SOAR Integration Circuit Breaker Simulation

## Problem
SOAR integration adapters currently run in simulation mode and do not make real outbound calls. That is the correct safety posture, but the integration layer still needs circuit breaker semantics before any future real execution mode can be considered.

The roadmap's Phase 3 guidance calls for per-integration circuit breakers, timeout handling, and retry classification so failed adapters cannot repeatedly consume execution attempts or flood downstream systems. Those patterns should be designed and validated while adapters are still simulation-only, before Slack, webhook, email, firewall, PagerDuty, or other external execution paths exist.

## Goal
Design simulation-mode integration reliability safeguards for adapter execution paths.

## Scope
- Define adapter circuit breaker states: `closed`, `open`, and `half_open`.
- Track consecutive simulated failures per adapter.
- Define cooldown windows for adapters in `open` state.
- Define manual, explicit recovery probing behavior for `half_open`.
- Add explicit timeout metadata for simulated adapter calls.
- Classify simulated failures as transient or non-transient.
- Expose adapter-level retry eligibility metadata.
- Preserve fail-closed behavior when adapter state is unsafe or ambiguous.
- Expose operator-visible circuit breaker state through existing integration visibility surfaces or a narrow read-only API extension.
- Define safe interaction with existing playbook execution states, reliability metadata, stale-running detection, and `permanently_failed`.
- Keep behavior simulation-only with bounded retries and no hidden autonomous replay.
- Prevent alert storms from repeatedly hammering failed adapters, even in simulation.

## Out of scope
- No implementation code in this change.
- No real outbound calls.
- No Slack, webhook, email, firewall, PagerDuty, or external service execution.
- No daemon or scheduler addition.
- No automatic autonomous retries.
- No background replay engine.
- No Redis, Celery, RQ, or queue backend migration.
- No ingest, detection, or correlation changes.
- No queue architecture rewrite.
- No `blocked_ips` mutation.
- No subprocess execution.
- No external API dependencies.
- No enabling `INTEGRATION_MODE=real`.
- No secrets or credential requirements.

## Success criteria
- Adapter circuit breaker states are defined and visible to operators.
- Consecutive simulated failures can open a breaker and stop further simulated adapter execution.
- Cooldown and `half_open` probing are explicit and bounded.
- Transient and non-transient simulated failures affect retry eligibility predictably.
- Existing playbook execution history remains immutable.
- Existing `permanently_failed` and stale-running behavior remains compatible with adapter circuit breaker failures.
- Tests can prove no network calls, subprocess calls, external API dependencies, `blocked_ips` writes, queue redesign, or ingest/detection/correlation changes are introduced.

## Why now
Circuit breakers should exist before real outbound execution because real adapters can fail loudly, slowly, or repeatedly. Without breaker state and bounded retry semantics, a future autonomous worker or alert burst could repeatedly hit a failed provider, consume execution attempts, and obscure the original failure. Simulation-first design validates state transitions, visibility, cooldowns, and failure classification while the system still cannot affect external systems.
