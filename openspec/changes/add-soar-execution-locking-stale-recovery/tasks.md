# Tasks: SOAR Execution Locking and Stale Recovery

This is a design/spec change only. Implementation should be split into later approved slices.

---

## Pre-implementation review

- [ ] Confirm current playbook execution claim path uses `FOR UPDATE SKIP LOCKED`.
- [ ] Confirm current approval resume path and where it must gain lease ownership.
- [ ] Confirm current notification delivery idempotency behavior and whether DB uniqueness exists.
- [ ] Confirm current retry semantics for failed/abandoned executions.
- [ ] Confirm which runner entrypoints should generate worker identity.
- [ ] Confirm lease timeout defaults for staging.

---

## Slice 1 — Schema and store primitives

- [ ] Add migration for nullable lease metadata on `playbook_executions`.
- [ ] Add indexes for stale lease scan and owner inspection.
- [ ] Update `schema.sql` snapshot marker and reference snapshot.
- [ ] Extend row serialization to include lease fields.
- [ ] Add store helpers:
  - [ ] claim pending execution with worker lease.
  - [ ] heartbeat owned execution.
  - [ ] release/clear lease on terminal status.
  - [ ] claim approval-resumed execution with worker lease.
  - [ ] list stale leased executions.
- [ ] Add unit tests for lease claim and heartbeat guards.

---

## Slice 2 — Worker ownership integration

- [ ] Generate worker identity in playbook runner entrypoints.
- [ ] Pass `worker_id` through batch processing.
- [ ] Claim pending executions with lease owner.
- [ ] Claim approved `awaiting_approval` executions with lease owner before resume.
- [ ] Guard step-log updates by lease owner.
- [ ] Guard success/failure/awaiting-approval transitions by lease owner.
- [ ] Stop processing if heartbeat or guarded update loses ownership.
- [ ] Add concurrency tests with two workers/transactions.

---

## Slice 3 — Durable progress and resume behavior

- [x] Split fresh execution processing from recovered/resumed processing.
- [x] Resume from `last_completed_step + 1`.
- [x] Do not replay successful steps already present in `steps_log`.
- [x] Preserve existing approval gate entries and decision entries.
- [x] Add tests for crash-after-step-log and resume-from-progress scenarios.

---

## Slice 4 — Stale recovery workflow

- [x] Implement stale lease scanner using `FOR UPDATE SKIP LOCKED`.
- [x] Requeue stale running executions when attempts remain.
- [x] Mark exhausted stale executions failed/permanently_failed according to policy.
- [x] Do not treat `awaiting_approval` as stale-running.
- [x] Add CLI/admin-safe recovery command or dry-run status command.
- [x] Add tests for stale recovery, max attempts, and no-op terminal statuses.

---

## Slice 5 — Notification/remediation duplication guard

- [x] Decide whether to add unique DB constraint for `notification_delivery_attempts.idempotency_key`.
  - Decision: no migration required. Guard implemented at step-execution level.
- [x] If approved, add migration and store `ON CONFLICT` behavior.
  - Not needed: `_step_already_succeeded_in_log` guard prevents re-execution before delivery store is called.
- [x] Ensure recovered execution does not resend successful notification steps.
  - Guard checks `steps_log` for a success entry at the step index; skips execution + delivery recording if found.
- [x] Define manual-review behavior for ambiguous notification/remediation crash windows.
  - Single-transaction model means no crash window where delivery is committed but step log is not. If `last_completed_step`/`steps_log` diverge (future per-step-commit scenario), the guard catches it.
- [x] Add tests for no duplicate delivery rows on recovery/retry.
  - `test_recovered_teams_step_does_not_create_duplicate_delivery`
  - `test_completed_block_ip_remediation_step_skipped_on_resume`
  - `test_two_workers_cannot_both_complete_same_execution`
  - `test_steps_log_success_guard_prevents_reexecution_when_last_completed_step_missing`

---

## Slice 6 — Observability and operations

- [ ] Expose lease fields in read-only execution APIs if needed.
- [ ] Add worker id, claimed ids, heartbeat loss, and recovery counts to CLI output.
- [ ] Document operational stale recovery workflow.
- [ ] Add manual recovery/admin tasks if approved.
- [ ] Add regression tests for existing approval and notification behavior.

---

## Verification planning

- [ ] Run focused playbook store tests.
- [ ] Run playbook route tests.
- [ ] Run notification delivery store/routes tests.
- [ ] Run approval store/routes tests.
- [ ] Run ingest/detection/correlation regression suite.
- [ ] Validate migrations on fresh disposable DB.
- [ ] Validate VM dry-run before any staging apply.

---

## Safety boundaries

- [ ] Do not change ingest transaction flow.
- [ ] Do not change detection internals.
- [ ] Do not change correlation internals.
- [ ] Do not send notifications in tests except mocked/simulated paths.
- [ ] Do not run real remediation adapters.
- [ ] Do not create destructive migrations.
