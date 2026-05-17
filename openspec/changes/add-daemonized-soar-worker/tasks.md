## 1. Discovery and Safety Baseline

- [x] 1.1 Audit the existing manual executor script, playbook execution store, lease fields, stale recovery helpers, dead-letter store, retry flows, metrics routes, and SOAR UI assumptions.
- [x] 1.2 Document current execution states, legal transitions, retry limits, lease ownership checks, and simulation-mode guardrails.
- [x] 1.3 Identify whether worker heartbeat visibility can use existing data or requires an additive persistence change.
- [x] 1.4 Define default worker configuration values for polling cadence, batch size, lease duration, heartbeat interval, recovery interval, idle backoff, and max in-flight work.

### Slice 1 audit findings (2026-05-17)

**Execution entry points today (all one-shot; no daemon):**

| Path | What it runs | Commit model |
|------|----------------|--------------|
| `scripts/run_playbook_executor_once.py` | `process_playbook_execution_batch()` or `recover_stale_playbook_executions()` | Single `conn.commit()` per invocation |
| `scripts/soar_worker_run.py` | `engines.soar_action_worker.process_batch()` on `response_actions_queue` | Per-action commits inside worker |
| `POST /admin/soar/worker/run-once` | Same as `soar_worker_run` (response queue only, simulation-only) | Request-scoped DB connection |
| `engines/soar_playbook_orchestrator.py` | Creates `pending` `playbook_executions` post-commit only | Called from ingest post-commit path |

There is **no** HTTP or daemon entry point for playbook batch execution; operators use the CLI script only.

**Playbook executor call chain (safe to wrap in a daemon loop):**

1. `generate_playbook_worker_id()` → stable `hostname:pid:uuid` per process.
2. `process_playbook_execution_batch(conn, limit, worker_id=…)`:
   - Pending: `claim_next_pending_playbook_execution_with_lease` (`FOR UPDATE SKIP LOCKED`, oldest-first).
   - Then `_process_running_execution` → `_process_steps` with per-step `_heartbeat_lease`.
   - Remaining batch slots: `list_awaiting_approval_playbook_executions` + `process_playbook_execution` per row (resume path uses `acquire_awaiting_approval_resume_lease`).
3. Stale recovery (manual today): `list_stale_running_executions` → `mark_stale_execution_for_recovery` → optional `capture_failed_execution_dead_letter` when recovery marks `failed` (implemented in script, not in store).

**Response-action queue worker is separate.** `soar_worker_run.py` / admin run-once do not execute playbooks. Design open question (design.md): unify in one daemon later vs. playbook daemon first.

**Legal execution statuses:** `pending`, `running`, `awaiting_approval`, `success`, `failed`, `abandoned`, `permanently_failed` (`TERMINAL_STATUSES` in executor). Active uniqueness for scheduling: `(playbook_id, alert_id)` while `pending` / `running` / `awaiting_approval`.

**Lease / idempotency (already implemented):**

- Store: `acquire_execution_lease`, `claim_next_pending_playbook_execution_with_lease`, `heartbeat_execution_lease`, `release_execution_lease`, `list_stale_running_executions`, `mark_stale_execution_for_recovery`.
- Executor: skip terminal; ownership checks on `running`; `_step_already_succeeded_in_log` after resume; lease release on success/fail and on approval pause.
- Env: `SOAR_PLAYBOOK_LEASE_SECONDS` (default **60** via `DEFAULT_PLAYBOOK_LEASE_SECONDS`).

**Dead letter / retry (worker must not bypass):**

- Failure: `capture_failed_execution_dead_letter` from `_finalize_failed` (best-effort).
- `create_retry_execution` inserts new `pending` row only; dead-letter `retry-execute` API does not run steps.
- Store tests: `tests/test_dead_letter_store.py`, `tests/test_dead_letter_routes.py`.

**Metrics / visibility today:**

- `GET /metrics/playbooks` includes `stale_running_count` (expired lease on `status=running`).
- **No** `GET /health/worker` route exists (mentioned only in `docs/soar_upgrade_roadmap.md` / archived SOAR UI design).
- No process-level worker heartbeat table; only `playbook_executions.lease_*` columns.

**1.3 — Heartbeat visibility:** Process health for a daemon **requires additive persistence** (e.g. `soar_worker_heartbeats` per design open questions) **or** derive “last activity” from logs/metrics only (weaker). Execution-level `lease_heartbeat_at` is insufficient to prove the worker process is alive when idle.

**1.4 — Proposed defaults for slice 3+ (simulation VM; tune under load):**

| Setting | Proposed default | Notes |
|---------|------------------|--------|
| Poll interval | 5s + 0–2s jitter | Avoid tight loop when idle |
| Idle backoff cap | 30s | When no pending/awaiting work |
| Batch size | 10 (max 50) | Match `run_playbook_executor_once` |
| Max in-flight per worker | 1 | Current batch loop is sequential; keep until step parallelism is designed |
| Lease duration | 60s (`SOAR_PLAYBOOK_LEASE_SECONDS`) | Must exceed longest step; renew each step today |
| Heartbeat / renew | Each step + before claim | Already in `_process_steps` |
| Stale recovery interval | 60s | Separate from poll; bounded `stale-limit` 50 |
| Recovery ownership | Every worker attempts; rely on `FOR UPDATE SKIP LOCKED` on stale list | Alternative: elected owner — defer to slice 5 |

**Test coverage map for daemon work:**

- Leases / stale recovery: `tests/test_playbook_execution_leases.py`, `tests/test_playbook_step_executor.py`, `tests/test_run_playbook_executor_once.py`
- Dead letters: `tests/test_dead_letter_store.py`, `tests/test_dead_letter_routes.py`
- Metrics (no worker health): `tests/test_playbook_metrics_routes.py`
- **Gaps:** multi-worker concurrent CLI simulation, daemon shutdown/drain, DB disconnect during loop, approval-resume races under two workers.

**Safe implementation path for slice 3 (daemon skeleton):**

1. New module e.g. `engines/soar_playbook_worker.py` (or `scripts/soar_playbook_worker_daemon.py`) that imports **existing** `process_playbook_execution_batch` and `recover_stale_playbook_executions` — do not fork executor logic.
2. Loop: connect → recovery tick (bounded) → batch tick → commit → sleep; signal handlers set draining flag.
3. Keep `run_playbook_executor_once.py` as thin CLI wrapper over the same functions for break-glass.
4. Do **not** enable real adapters; inherit simulation-only playbook executor and separate response-queue policy.
5. Add worker heartbeat persistence in slice 7 before relying on dashboard “healthy worker” semantics.

**Ingest / detection / correlation:** Untouched. Scheduling remains `soar_playbook_orchestrator` post-commit only; `playbook_schedules` is still metadata-only.

## 2. Store-Level Concurrency Hardening

- [x] 2.1 Add or refine atomic lease acquisition tests proving one worker owns one execution under contention.
- [x] 2.2 Add ownership-checked completion, failure, renewal, and dead-letter transition tests.
- [x] 2.3 Add idempotency tests for completed, failed, dismissed, dead-lettered, retrying, and stale executions.
- [x] 2.4 Add retry-request and retry-execute coordination tests proving replacement executions do not duplicate prior attempts.

### Slice 2 concurrency hardening notes (2026-05-17)

- Added store-level coverage for single-owner `claim_next_pending_playbook_execution_with_lease`, matching-owner terminal updates, retry-created pending row claim safety, awaiting-approval stale recovery exclusion, and awaiting-approval resume lease contention.
- Added executor-level regression coverage proving stale workers cannot finalize success/failure or create dead letters after losing ownership.
- Added dead-letter capture coverage proving repeated playbook failure capture keeps one active dead letter for the same execution.
- Fixed executor finalization safety: success/failure no longer falls back to unguarded terminal updates after lease loss. Failure finalization still permits the existing lease-free `awaiting_approval` denial/expiry path when no worker owns the row.

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
