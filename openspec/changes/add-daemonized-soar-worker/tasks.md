## 1. Discovery and Safety Baseline

- [ ] 1.1 Audit the existing manual executor script, playbook execution store, lease fields, stale recovery helpers, dead-letter store, retry flows, metrics routes, and SOAR UI assumptions.
- [ ] 1.2 Document current execution states, legal transitions, retry limits, lease ownership checks, and simulation-mode guardrails.
- [ ] 1.3 Identify whether worker heartbeat visibility can use existing data or requires an additive persistence change.
- [ ] 1.4 Define default worker configuration values for polling cadence, batch size, lease duration, heartbeat interval, recovery interval, idle backoff, and max in-flight work.

## 2. Store-Level Concurrency Hardening

- [ ] 2.1 Add or refine atomic lease acquisition tests proving one worker owns one execution under contention.
- [ ] 2.2 Add ownership-checked completion, failure, renewal, and dead-letter transition tests.
- [ ] 2.3 Add idempotency tests for completed, failed, dismissed, dead-lettered, retrying, and stale executions.
- [ ] 2.4 Add retry-request and retry-execute coordination tests proving replacement executions do not duplicate prior attempts.

## 3. Worker Daemon Skeleton

- [ ] 3.1 Introduce a dedicated worker entrypoint with configuration parsing, stable worker identity, DB connectivity check, and simulation-safe startup validation.
- [ ] 3.2 Add signal handling for graceful shutdown and draining mode.
- [ ] 3.3 Add structured logging for worker lifecycle events, `worker_id`, `execution_id`, lease owner, and failure class.
- [ ] 3.4 Verify the worker can start and exit without claiming or executing work in a smoke test.

## 4. Continuous Execution Loop

- [ ] 4.1 Implement bounded polling with batch size, oldest-first eligibility, idle backoff, and jitter.
- [ ] 4.2 Implement max in-flight work controls and queue starvation prevention.
- [ ] 4.3 Integrate lease acquisition before execution and ownership validation after execution.
- [ ] 4.4 Add tests for empty queue, large queue, mixed statuses, shutdown during idle, and shutdown during active work.

## 5. Stale Recovery Loop

- [ ] 5.1 Implement bounded stale recovery cadence using existing lease timeout semantics.
- [ ] 5.2 Ensure active heartbeat or lease renewal prevents premature recovery.
- [ ] 5.3 Add tests for stale leased executions, active leased executions, repeated stale failures, and recovery race conditions.
- [ ] 5.4 Confirm manual recovery behavior remains available for break-glass use.

## 6. Failure and Dead-Letter Handling

- [ ] 6.1 Harden DB disconnect handling so the worker fails closed and does not mark success without persisted completion.
- [ ] 6.2 Add poison execution handling with retry exhaustion and dead-letter escalation.
- [ ] 6.3 Add tests for crash after lease, crash during step execution, failure before dead-letter write, and failure after dead-letter write.
- [ ] 6.4 Confirm retry-execute continues to create a new pending execution only and does not run steps immediately.

## 7. Operational Visibility APIs and Metrics

- [ ] 7.1 Add read-only worker health and heartbeat visibility if supported by the selected persistence model.
- [ ] 7.2 Add queue depth, stale execution, recovery, retry exhaustion, and failure-rate metrics.
- [ ] 7.3 Gate worker visibility consistently with SOAR Operations and SOAR Metrics RBAC.
- [ ] 7.4 Add backend tests for auth, RBAC, empty states, active worker state, stale worker state, queue depth, and recovery metrics.

## 8. Dashboard Visibility

- [ ] 8.1 Extend SOAR Metrics or SOAR Operations UI with read-only worker health and queue visibility.
- [ ] 8.2 Preserve viewer exclusion for SOAR worker operational data if consistent with current SOAR gating.
- [ ] 8.3 Add frontend tests for loading, empty, stale, unhealthy, and partial-metrics states.
- [ ] 8.4 Confirm no mutation controls are added for viewers.

## 9. Deployment Design and Rollout Artifacts

- [ ] 9.1 Draft systemd service design documentation with environment requirements, restart policy, logging, and graceful shutdown expectations.
- [ ] 9.2 Add deployment checklist for one-worker simulation rollout, multi-worker simulation rollout, and rollback to manual executor operation.
- [ ] 9.3 Add operator runbook entries for stopping the worker, checking health, reviewing dead letters, and recovering stale work.
- [ ] 9.4 Defer actual service file installation until implementation and validation slices pass.

## 10. Load and Failure Validation

- [ ] 10.1 Add multi-worker simulation tests proving no duplicate execution under concurrent claims.
- [ ] 10.2 Add queue pressure tests for batch limits, backpressure, starvation prevention, and metrics accuracy.
- [ ] 10.3 Add stale recovery simulations for expired leases, active leases, and workers that crash mid-step.
- [ ] 10.4 Add failure injection for DB disconnect, transaction rollback, dead-letter write failure, and retry exhaustion.
- [ ] 10.5 Run existing ingest, detection, correlation, SOAR Operations, and SOAR Metrics regression suites to prove contracts remain unchanged.

## 11. Final Verification and Archive

- [ ] 11.1 Verify daemonized worker remains simulation-safe by default and real Slack/Teams/firewall execution remains disabled.
- [ ] 11.2 Verify no schema rewrites, ingest changes, detection changes, correlation changes, or autonomous remediation broadening were introduced.
- [ ] 11.3 Complete final backend, frontend, concurrency, load, and build verification.
- [ ] 11.4 Update OpenSpec tasks with evidence and archive the change after implementation is complete.
