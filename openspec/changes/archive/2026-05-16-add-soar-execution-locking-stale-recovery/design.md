# Design: SOAR Execution Locking and Stale Recovery

## Overview

This design adds an explicit lease model to `playbook_executions`. A worker claims an execution by setting owner and lease timestamps inside a row lock. While processing, the worker heartbeats. Other workers skip leased rows. If a worker crashes, a later recovery pass can safely detect expired leases and either requeue or fail the execution according to its progress and idempotency state.

The design builds on current behavior:

- `claim_next_pending_playbook_execution()` already uses `FOR UPDATE SKIP LOCKED` for pending rows.
- Approval requests are unique per active playbook execution/step.
- Notification delivery rows are append-only and include deterministic idempotency keys.
- Reliability metadata already exists on `playbook_executions`: `attempt_count`, `max_attempts`, `last_attempted_at`, `failure_reason`, `stale_after`, and `timeout_seconds`.

The missing piece is ownership: who is allowed to continue or finalize a running execution.

---

## 1. Additive Schema Model

A future migration should add nullable lease metadata to `playbook_executions`:

- `lease_owner TEXT`
- `lease_acquired_at TIMESTAMPTZ`
- `lease_expires_at TIMESTAMPTZ`
- `heartbeat_at TIMESTAMPTZ`
- `recovered_at TIMESTAMPTZ`
- `recovery_count INTEGER NOT NULL DEFAULT 0`

Indexes:

- `(status, lease_expires_at, created_at, id)` for claim/recovery scans.
- `(lease_owner)` for operational inspection.

These fields are additive and safe for existing rows. Existing executions with `NULL` lease fields retain current semantics until the worker code starts using leases.

---

## 2. Worker Identity

Each runner process should generate a stable identity at startup:

```text
<hostname>:<pid>:<uuid-fragment>
```

This value is stored in `lease_owner` and included in logs/results. It is not an authorization mechanism; it is an operational ownership marker.

Workers must pass their `worker_id` through claim, heartbeat, resume, and finalize calls. A worker can only mutate a leased `running` execution if:

- `status = 'running'`
- `lease_owner = worker_id`
- `lease_expires_at > NOW()` unless the function is explicitly a recovery path

---

## 3. Claiming Pending Executions

Claim should remain row-lock based:

```sql
SELECT id
FROM playbook_executions
WHERE status = 'pending'
ORDER BY created_at ASC, id ASC
LIMIT 1
FOR UPDATE SKIP LOCKED;
```

Then update the selected row in the same transaction:

- `status = 'running'`
- `started_at = COALESCE(started_at, now)`
- `attempt_count = attempt_count + 1`
- `last_attempted_at = now`
- `lease_owner = worker_id`
- `lease_acquired_at = now`
- `heartbeat_at = now`
- `lease_expires_at = now + lease_duration`
- clear stale `failure_reason` only if policy says retrying should reset it

The claim transaction should commit before executing external-like step logic. This keeps the row lock short and prevents long-running steps from holding database locks.

---

## 4. Heartbeat Model

Workers should heartbeat before starting each step and after each step completes:

- Verify lease ownership.
- Update `heartbeat_at = now`.
- Extend `lease_expires_at = now + lease_duration`.

If heartbeat update affects zero rows, the worker has lost ownership and must stop processing immediately without finalizing success/failure. This prevents a stale worker from overwriting recovery decisions.

Lease duration should be longer than normal step execution time. For first implementation, use a conservative default such as 60 seconds, configurable by environment or function argument in tests.

---

## 5. Step Transaction Boundaries

Current playbook execution runs a batch in one outer connection/transaction. The locking design should move to explicit per-step persistence:

1. Claim execution and commit.
2. For each step:
   - heartbeat and commit.
   - execute the step outside long-held row locks.
   - write step result with lease-owner guard and commit.
3. Finalize success/failure with lease-owner guard and commit.

This prevents a crash from rolling back the claim and hiding that work started. It also makes `last_completed_step` and `steps_log` durable across crashes.

The design must preserve existing ingest/detection/correlation transaction contracts. Playbook execution stays post-commit and outside ingest transactions.

---

## 6. Stale Detection

An execution is stale when:

- `status = 'running'`
- `lease_expires_at IS NOT NULL`
- `lease_expires_at <= NOW()`

Existing `stale_after` / `timeout_seconds` metadata can remain as policy inputs, but lease expiration should become the primary recovery trigger. `heartbeat_at` is diagnostic and useful for operators.

Recovery scans should use:

```sql
SELECT id
FROM playbook_executions
WHERE status = 'running'
  AND lease_expires_at <= NOW()
ORDER BY lease_expires_at ASC, id ASC
LIMIT %s
FOR UPDATE SKIP LOCKED;
```

---

## 7. Recovery Policy

Recovery must be conservative because steps may have external side effects.

Recommended first policy:

- If `attempt_count < max_attempts`, transition stale `running` to `pending`, clear `lease_owner`, clear lease timestamps, increment `recovery_count`, set `failure_reason = 'stale lease recovered for retry'`.
- If `attempt_count >= max_attempts`, transition to `failed` or `permanently_failed` with `failure_reason = 'stale lease exceeded max attempts'`.
- Do not recover `awaiting_approval` as stale; approval wait is a valid parked state, not a crashed worker.
- Do not recover terminal statuses.

Recovery should not execute steps. It only changes execution state so a later normal worker claim can continue or stop.

---

## 8. Resume Semantics

On retry after stale recovery:

- Re-read `steps_log` and `last_completed_step`.
- Start from `last_completed_step + 1`.
- Do not replay steps already marked `success`.
- If a previous step has an `awaiting_approval` entry, preserve approval semantics.
- If the execution is `awaiting_approval`, only resume after the linked approval becomes `approved`.

The current `_process_running_execution()` starts from index `0`; implementation must split fresh execution from resumed execution so recovered executions continue from durable progress.

---

## 9. Approval Semantics

Approval behavior must remain stable:

- Creating a `require_approval` step creates or reuses the active approval request for `(playbook_execution_id, playbook_step_index)`.
- `awaiting_approval` is not considered stale-running.
- Pending approval remains parked.
- Approved approval can be resumed only through a claim/resume path that sets lease ownership.
- Denied or expired approval transitions the execution to failed safely and does not run later steps.

When resuming after approval, the worker should claim the `awaiting_approval` row with `FOR UPDATE SKIP LOCKED`, set it to `running`, set lease owner/heartbeat, then commit before processing later steps.

---

## 10. Notification and Remediation Idempotency

Duplicate side effects are the highest-risk recovery failure.

Notification delivery:

- Current idempotency key is deterministic by provider/action/execution/step.
- Future migration should add a unique index on `notification_delivery_attempts(idempotency_key)` or define a store-level `ON CONFLICT DO NOTHING` path before automatic replay is enabled.
- Recovery must check `steps_log` and delivery idempotency before re-executing notification steps.
- If a notification step has a success entry in `steps_log`, never resend it.

Remediation actions:

- Real remediation remains out of scope for this design slice.
- Before real remediation is retried after stale recovery, the action must have an idempotency key and adapter-level idempotency semantics.
- Recovery may initially mark stale executions with notification/remediation uncertainty as failed for manual review instead of retrying automatically.

---

## 11. Safe Status Transitions

Allowed transitions:

- `pending -> running` by worker claim.
- `running -> awaiting_approval` by owned worker.
- `awaiting_approval -> running` by owned resume claim after approval.
- `running -> success` by lease owner.
- `running -> failed` by lease owner.
- `running -> pending` by stale recovery when lease expired and attempts remain.
- `running -> failed/permanently_failed` by stale recovery when attempts are exhausted.
- `failed/abandoned -> pending new row` through existing retry execution behavior.

All owned transitions should include `WHERE lease_owner = %s` once lease fields exist.

---

## 12. Observability

Add operator-visible metadata:

- current `lease_owner`
- `lease_acquired_at`
- `heartbeat_at`
- `lease_expires_at`
- `attempt_count`
- `max_attempts`
- `recovery_count`
- stale/recovery reason

CLI output should include:

- worker id
- claimed execution ids
- recovered execution ids
- skipped stale rows due to max attempts
- lost-lease events

Admin/API visibility can be a later slice if frontend changes are needed.

---

## 13. Manual Recovery

Manual recovery should be explicit and audited:

- Mark stale execution as `pending` for retry.
- Mark stale execution as `failed` with reason.
- Mark execution as `permanently_failed`.
- Inspect current lease and heartbeat metadata.

Manual actions must not run playbook steps directly. They only change state for normal workers to pick up.

---

## 14. Crash Scenarios

Worker crashes after claim before step:

- Lease expires.
- Recovery returns execution to pending if attempts remain.
- Next worker starts from `last_completed_step + 1` or `0` if no step completed.

Worker crashes after external notification succeeds but before step log commit:

- Highest risk case.
- First implementation should avoid automatic retry for notification/remediation steps unless delivery idempotency uniqueness is enforced.
- Operator review may be required if progress is ambiguous.

Worker crashes after step log commit:

- Next worker reads durable progress and continues after `last_completed_step`.

Worker loses lease while still running:

- Heartbeat/finalize guarded update affects zero rows.
- Worker stops without further side effects.

---

## 15. Safety Boundaries

This change must not alter:

- ingest transaction flow
- detection or correlation internals
- approval decision semantics
- notification adapter behavior
- frontend behavior unless explicitly scoped later

All schema work must be additive migrations only.
