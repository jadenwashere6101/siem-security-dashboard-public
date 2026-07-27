## 1. Schema And Store Layer

- [x] 1.1 Add an additive migration for SOC briefing schedules, schedule windows, jobs, runs, run steps, and briefing lifecycle records with constraints, indexes, idempotency keys, and retention-ready timestamps.
- [x] 1.2 Add migration tests and schema snapshot validation for all new tables, indexes, checks, and uniqueness constraints.
- [x] 1.3 Implement a `core/ai/soc_briefing_runtime_store.py` helper layer for schedule CRUD needed by the worker, window materialization, job creation, job claiming, lease renewal, completion, stale recovery, run creation, step persistence, briefing lifecycle writes, and read-only health summaries.
- [x] 1.4 Ensure required persistence failures raise explicit exceptions and do not continue silently.

## 2. Scheduler And Catch-Up

- [x] 2.1 Implement schedule validation for cadence, timezone, due timestamps, catch-up limits, and enabled state.
- [x] 2.2 Implement window computation using `last_successful_window_end`, `next_due_at`, maximum catch-up count, maximum lookback, and coalescing behavior.
- [x] 2.3 Persist skipped or stale windows with explicit reasons such as `disabled`, `malformed_schedule`, `coalesced`, `outside_lookback`, and `stale_window`.
- [x] 2.4 Add tests for duplicate schedule-window suppression, bounded catch-up, overnight coalescing, disabled schedules, and malformed schedules.

## 3. Worker, Leases, And Heartbeat

- [x] 3.1 Implement a bounded one-shot worker module that materializes due windows, recovers stale leases, claims jobs with `FOR UPDATE SKIP LOCKED`, creates isolated runs, persists durable steps, checks AI readiness states, and exits within configured runtime limits.
- [x] 3.2 Add lease acquisition, lease heartbeat, owner-matched completion, retry exhaustion, and stale recovery tests proving only one worker can own a job.
- [x] 3.3 Extend worker heartbeat support for logical worker name `soc_briefing_worker` and expose unknown, healthy, degraded, and offline health metadata.
- [x] 3.4 Add graceful shutdown handling that stops new claims, preserves completed step records, and leaves unfinished leased work recoverable.
- [x] 3.5 Add tests proving heartbeat accuracy, isolated run state, durable step persistence, and failed persistence abort behavior.

## 4. Runtime Security And Service Identity

- [x] 4.1 Define the `scheduled_soc_briefing_worker` service actor and enforce read-only analyst-equivalent SOC tool access.
- [x] 4.2 Add runtime guards proving the service actor cannot approve, deny, execute, retry, resume, abandon, block, unblock, send Slack, create notes, mutate incidents, run shell/file/subprocess code, or bypass existing read-tool validation.
- [x] 4.3 Persist AI Gateway disabled, local provider unavailable, Mini PC unavailable, provider timeout, and paid fallback blocked outcomes without requiring an AI/provider call in foundation tests.
- [x] 4.4 Add tests proving no production mutation path exists and no AI/provider call is required to verify the runtime foundation.

## 5. Systemd And Deployment Integration

- [x] 5.1 Add `scripts/soc_briefing_worker.py` as the repository-owned worker entry point with bounded batch/runtime arguments and JSON/status output for journals.
- [x] 5.2 Add `deploy/systemd/soc-briefing-worker.service` as a one-shot service using the VM `.env`, repository working directory, and virtual environment.
- [x] 5.3 Add `deploy/systemd/soc-briefing-worker.timer` with `OnBootSec=2min`, `OnUnitActiveSec=5min`, `RandomizedDelaySec=30s`, `Persistent=true`, and the service unit binding.
- [x] 5.4 Update deployment helper scripts to install and restart the new briefing worker units only after approved migration/backend deployment flow.
- [x] 5.5 Add deployment/unit tests or static assertions for the service/timer contract.

## 6. Minimal Runtime API And Observability

- [x] 6.1 Add read-only backend status/metrics contract for briefing worker health, due/pending/running/failed job counts, last heartbeat, and last run outcome.
- [x] 6.2 Gate runtime status visibility with existing analyst/super-admin RBAC and avoid exposing secrets, prompt bodies, or lease-owner internals that resemble credentials.
- [x] 6.3 Add focused API tests for RBAC, health states, and failure metadata.

## 7. Documentation And Handoff

- [x] 7.1 Update worker deployment/runbook documentation for the new service and timer.
- [x] 7.2 Update AI architecture documentation to describe the scheduled runtime boundary and out-of-scope autonomous content generation.
- [x] 7.3 Update verification checklist and VM handoff documentation with migration, systemd, health, rollback, and no-production-mutation checks.
- [x] 7.4 Update migration workflow documentation only if implementation introduces a new schema convention; update the Mac/VM source-of-truth policy only if ownership or deployment rules genuinely change.

## 8. Verification

- [x] 8.1 Run focused backend tests for store, scheduler, worker, leases, catch-up, heartbeat, RBAC, and mutation guard behavior.
- [x] 8.2 Run migration tests and schema snapshot validation.
- [x] 8.3 Run `git diff --check`.
- [x] 8.4 Run `openspec validate scheduled-soc-briefing-runtime --strict`.
- [x] 8.5 Prepare a VM handoff note stating that VM sync is required only after implementation is committed, pushed, and explicitly approved.
