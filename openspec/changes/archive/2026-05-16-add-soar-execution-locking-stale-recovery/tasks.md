# Tasks: SOAR Execution Locking and Stale Recovery

This is a design/spec change only. Implementation should be split into later approved slices.

---

## Pre-implementation review

- [x] Confirm current playbook execution claim path uses `FOR UPDATE SKIP LOCKED`.
- [x] Confirm current approval resume path and where it must gain lease ownership.
- [x] Confirm current notification delivery idempotency behavior and whether DB uniqueness exists.
- [x] Confirm current retry semantics for failed/abandoned executions.
- [x] Confirm which runner entrypoints should generate worker identity.
- [x] Confirm lease timeout defaults for staging.

---

## Slice 1 — Schema and store primitives

- [x] Add migration for nullable lease metadata on `playbook_executions`.
- [x] Add indexes for stale lease scan and owner inspection.
- [x] Update `schema.sql` snapshot marker and reference snapshot.
- [x] Extend row serialization to include lease fields.
- [x] Add store helpers:
  - [x] claim pending execution with worker lease.
  - [x] heartbeat owned execution.
  - [x] release/clear lease on terminal status.
  - [x] claim approval-resumed execution with worker lease.
  - [x] list stale leased executions.
- [x] Add unit tests for lease claim and heartbeat guards.

---

## Slice 2 — Worker ownership integration

- [x] Generate worker identity in playbook runner entrypoints.
- [x] Pass `worker_id` through batch processing.
- [x] Claim pending executions with lease owner.
- [x] Claim approved `awaiting_approval` executions with lease owner before resume.
- [x] Guard step-log updates by lease owner.
- [x] Guard success/failure/awaiting-approval transitions by lease owner.
- [x] Stop processing if heartbeat or guarded update loses ownership.
- [x] Add concurrency tests with two workers/transactions.

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

- [x] Expose lease fields in read-only execution APIs if needed.
  - Not needed in this slice; existing route coverage remains unchanged.
- [x] Add worker id, claimed ids, heartbeat loss, and recovery counts to CLI output.
- [x] Document operational stale recovery workflow.
- [x] Add manual recovery/admin tasks if approved.
  - No admin route was approved; manual CLI recovery and validation docs cover this slice.
- [x] Add regression tests for existing approval and notification behavior.

---

## Verification planning

- [x] Run focused playbook store tests.
- [x] Run playbook route tests.
- [x] Run notification delivery store/routes tests.
- [x] Run approval store/routes tests.
- [x] Run ingest/detection/correlation regression suite.
- [x] Validate migrations on fresh disposable DB.
- [x] Validate VM dry-run before any staging apply.

---

## Safety boundaries

- [x] Do not change ingest transaction flow.
- [x] Do not change detection internals.
- [x] Do not change correlation internals.
- [x] Do not send notifications in tests except mocked/simulated paths.
- [x] Do not run real remediation adapters.
- [x] Do not create destructive migrations.
