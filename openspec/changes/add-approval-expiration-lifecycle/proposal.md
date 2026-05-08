# Proposal: Approval Expiration + Lifecycle Cleanup (Phase 2.5D)

## Problem

Approval expiration currently exists in the codebase but is not deterministic. The
`expire_pending_requests()` function is complete and correct — it materializes `pending →
expired` transitions with a full event record and audit log — but it is only called from two
places: inside the worker's `process_next_action()` and inside `_handle_approval_gate()`.
Both require the worker to run.

The worker has no background scheduler, no cron job, and no systemd unit. It only executes
when triggered via `POST /admin/soar/worker/run-once`. This creates a visible gap:

- An analyst opens the Approvals panel and sees a `pending` approval. The approval's
  `expires_at` is three hours ago. The worker hasn't run. The approval is still `pending` in
  the database. The analyst makes a decision based on stale state.
- A super_admin opens the approval detail view for an approval they want to act on. It shows
  `pending`. They submit `approved`. The `approve_request()` function checks `expires_at`,
  materializes the expiration, and raises `ValueError("approval request expired")`. The route
  returns a 400. The UI shows an error. The approval is now `expired` in the database — but
  only because the approval action happened to trigger it. A read-only view would not have.
- After the approval expires, the linked queue row is still in `awaiting_approval`. It will
  remain there until a worker run processes `skip_next_terminal_approval_action()` for it.
  Until then, the queue panel shows an `awaiting_approval` row with no resolved approval.

**The core issue:** expiration is write-behind. State that should be `expired` is surfaced as
`pending` until something writes the transition. Reads are never authoritative on their own.

This matters before Phase 3 (real integrations) because:
- Phase 3 will introduce real adapter execution. A `block_ip` action must not execute unless
  its approval is provably not expired at decision time.
- Stale `pending` state erodes trust in the approval panel before real stakes exist.
- Queue cleanup (transitioning `awaiting_approval → skipped` after expiration) currently
  requires sequential worker invocations, one row at a time. There is no batch sweep
  available to an operator who needs to clear a backlog.

## This change

Phase 2.5D adds two targeted fixes without introducing a scheduler, daemon, or background
job. GET routes remain read-only — expiration is an operational action and stays explicit.

1. **Manual expiration endpoint.** `POST /admin/soar/approvals/expire-pending` gives a
   super_admin a single endpoint that: (a) expires all overdue pending approvals, and (b)
   sweeps all `awaiting_approval` queue rows whose linked approval is now terminal. Returns
   counts of both. No scheduler required — an operator triggers it manually or via a shell
   script when needed.

2. **Batch queue sweep.** A new `sweep_terminal_approval_queue_rows(conn)` function in
   `response_action_queue_store.py` transitions all `awaiting_approval` queue rows with
   terminal approvals to `skipped` in one statement. This replaces the one-at-a-time
   `skip_next_terminal_approval_action()` pattern for batch operational cleanup.

## In scope

- `routes/admin_routes.py` — new `POST /admin/soar/approvals/expire-pending` endpoint.
- `core/response_action_queue_store.py` — new `sweep_terminal_approval_queue_rows(conn)`.
- `tests/test_soar_worker_admin_run_control.py` — tests for the new admin endpoint.
- `tests/test_response_action_queue_store.py` (or new file) — tests for the sweep function.

## Out of scope

- No scheduler, cron job, systemd unit, APScheduler, Celery, or background thread.
- No Slack/email notifications.
- No real firewall execution.
- No changes to the worker's own expiration behavior — it already calls
  `expire_pending_requests()` opportunistically; that path is not modified.
- No playbook changes.
- No ingest, detection, or correlation changes.
- No changes to `GET /approvals` or `GET /approvals/<id>`. Both routes remain read-only.
  Expiration is an operational action; the UI may show stale `pending` state until an operator
  explicitly triggers the admin endpoint or the worker runs.
- No frontend changes. `ApprovalsPanel.js` already has a correct `expired` badge and the
  `expired` filter.
- No changes to `approve_request()` or `deny_request()` — they already check `expires_at`
  and materialize expiration if needed.
- No schema changes. All required columns and indexes already exist.
- No queue deletion. Queue rows are never deleted — they transition to `skipped`.

## Role access

- `GET /approvals`, `GET /approvals/<id>` — unchanged. Already gated to
  `analyst_or_super_admin_required`. No change to auth model or behavior.
- `POST /admin/soar/approvals/expire-pending` — `super_admin_required`, consistent with all
  other `POST /admin/soar/*` mutating endpoints.

## Success criteria

- `POST /admin/soar/approvals/expire-pending` returns `expired_approvals` and
  `skipped_queue_rows` counts, commits both transitions atomically.
- Calling the endpoint multiple times is idempotent — already-expired approvals are not
  double-processed; already-skipped queue rows are not touched.
- `retry_count` is never incremented for queue rows transitioned by expiration.
- Already-approved and already-denied approval requests are not modified by any expiration
  path.
- All existing approval store, route, and worker tests continue to pass unchanged.
- No background thread, scheduler, or daemon is introduced.
