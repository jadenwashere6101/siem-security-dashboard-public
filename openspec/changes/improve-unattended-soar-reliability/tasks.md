This spec's authoring step (creating proposal.md/design.md/tasks.md/specs/) makes no code changes. Section 1 reflects verification completed while writing this spec, re-confirmed directly against code this session (building on, and not repeating, the earlier operational-reliability audit). Section 2 is this spec's own future implementation work, to be executed only in a separate, later, explicitly-requested pass.

## 1. Verification (completed as part of writing this spec)

- [x] 1.1 Re-confirm `approval_requests.status`'s `CHECK` constraint already covers `pending`/`approved`/`denied`/`expired` (`schema.sql:231-232`) and that `expire_pending_requests()` already runs automatically every 5 minutes via `soar-response-action-worker.timer` — the approval layer itself needs no change.
- [x] 1.2 Re-confirm `_process_awaiting_approval_execution`'s denied/expired branch (`engines/playbook_step_executor.py`) always falls through to `_finalize_failed` today because no pfSense playbook sets `on_denied`/`on_expired: "branch"`.
- [x] 1.3 Re-confirm `_finalize_failed` is the single shared choke point for genuine failures and expected approval terminals: it hardcodes `status='failed'` (`core/playbook_store.py:set_playbook_execution_failed`) and unconditionally calls `capture_failed_execution_dead_letter`.
- [x] 1.4 Re-confirm `_NON_RETRYABLE_FAILURE_CLASSES` in `core/dead_letter_store.py` already includes `approval_expired`/`approval_denied`, and that `GET /dead-letters`/`GET /metrics/dead-letters` already support `failure_class` filtering — the data to distinguish these already exists, just isn't structurally separated.
- [x] 1.5 Confirm `playbook_executions.status` (`schema.sql:387-411`) is `VARCHAR(30)` with **no** `CHECK` constraint, so a new terminal status value requires no migration; confirm `soar_dead_letters.status` (`schema.sql:563-564`) **does** have a `CHECK` constraint, so a new dead-letter status value would require one — informing the "don't create the row" design choice over "create and relabel the row."
- [x] 1.6 Confirm `abandoned`/`permanently_failed` (`routes/playbook_routes.py:863,918`) are manual, super_admin-only, operator-triggered statuses, distinct in intent from an automatic expected-lifecycle terminal, and should not be silently repurposed for it.
- [x] 1.7 Confirm the legacy queue's frozen status is already recorded in `openspec/specs/soar-automation-path-consolidation-decision/spec.md` and identify the exact rendering call site (`frontend/src/App.js:749`, `SoarQueuePanel`) that needs the frozen-queue banner.
- [x] 1.8 Confirm `"soar-operations"` (`frontend/src/utils/sectionsConfig.js:102-106`) currently renders only `<DeadLettersPanel />` (`frontend/src/App.js:828-838`) with no running/pending/expired summary.
- [x] 1.9 Confirm `GET /playbook-executions?status=...` and `GET /approvals?status=...` already support every status filter a summary needs, so no new list-query logic is required, only thin aggregation.
- [x] 1.10 Document the chosen architecture (new `not_actioned` terminal status, no dead-letter row for that path), the rejected migration-requiring alternative, existing-backlog handling, and risks in `design.md`.

## 2. Implementation (this spec's own future work — not started, not part of this authoring step)

### Phase 1 — Approval terminal-state and lifecycle contract (`core/playbook_store.py`, `engines/playbook_step_executor.py`)

- [x] 2.1 Add `not_actioned` to `_VALID_EXECUTION_STATUSES` and `_TERMINAL_EXECUTION_STATUSES` in `core/playbook_store.py`.
- [x] 2.2 Add `set_playbook_execution_not_actioned(...)` mirroring `set_playbook_execution_failed`'s exact shape (lease-aware, same `RETURNING` columns), writing `status = 'not_actioned'`.
- [x] 2.3 Add `_finalize_not_actioned(...)` in `engines/playbook_step_executor.py`, mirroring `_finalize_failed` except: calls `set_playbook_execution_not_actioned`, appends the existing approval-decision outcome event unchanged, and does **not** call `capture_failed_execution_dead_letter`.
- [x] 2.4 Route `_process_awaiting_approval_execution`'s denied/expired branch to `_finalize_not_actioned` specifically when `terminal_behavior != "branch"` (today's only reachable case); leave the `branch_continue` path and every other `_finalize_failed` call site (genuine step failures) untouched.
- [x] 2.5 Audit every existing consumer of `_TERMINAL_EXECUTION_STATUSES`/status-based filtering (lease/stale-recovery checks, `GET /playbook-executions?status=`, any "is this execution done" check) to confirm `not_actioned` is treated as terminal and filterable everywhere `failed`/`success`/`abandoned` already are.
- [x] 2.6 Confirm via test that no protected action (`block_ip`) can execute after an execution reaches `not_actioned` — this should already hold structurally (steps after the gate are already skipped before finalization) but must be verified, not assumed.

### Phase 2 — Dead-letter classification and expected-expiration handling (`core/dead_letter_store.py`, backlog tooling)

- [x] 2.7 Confirm (via Phase 1 tests) that reaching `not_actioned` creates zero rows in `soar_dead_letters` going forward; confirm genuine failures elsewhere still create rows with `retryable` computed exactly as today.
- [x] 2.8 Document the existing-backlog review runbook (filter by `failure_class IN ('approval_expired','approval_denied')` and `status='open'` via the existing `GET /dead-letters` filters; dismiss individually via the existing `POST /dead-letters/<id>/dismiss` with a standard reason).
- [ ] 2.9 (Optional, flagged — implement only if explicitly requested) Add a bulk-dismiss-by-filter convenience route that calls the existing `mark_dead_letter_dismissed` once per matched row, same RBAC/reason/audit trail as the single-row endpoint — no new deletion semantics, no schema change.

### Phase 3 — Backend APIs and operational summaries (new, read-only routes)

- [x] 2.10 Add a read-only SOAR operational-summary endpoint returning: running/awaiting-approval playbook-execution counts, pending-approval count, recently expired/denied approval count (bounded window), genuine-failure count (`playbook_executions.status='failed'` and/or actionable dead letters), and actionable dead-letter count (`status='open'`) — computed by calling the existing `list_playbook_executions`/`list_approval_requests`/`list_dead_letters`/`get_dead_letter_metrics` functions, not duplicating their SQL.
- [x] 2.11 Add regression tests for the summary endpoint's shape and edge cases (no data, all-zero counts, mixed statuses).

### Phase 4 — SOAR Operations UI and legacy-queue clarification (frontend)

- [x] 2.12 Extend the `"soar-operations"` section with a compact summary strip (cards: Running Playbooks, Pending Approvals, Recently Expired/Denied, Failed Executions, Actionable Dead Letters) consuming Phase 3's endpoint, above the existing `DeadLettersPanel`.
- [x] 2.13 Add a dead-letter reason/category badge and an "Expected expiration" vs. "System failure" label driven by `failure_class`, distinguishing legacy backlog rows (this labeling applies to any pre-existing rows; going forward such rows are no longer created per Phase 1/2).
- [x] 2.14 Add a link from an approval outcome (expired/denied) to its parent playbook execution and originating alert, reusing existing IDs already present on `playbook_executions`/`approval_requests`.
- [x] 2.15 Add a frozen-queue informational banner to `SoarQueuePanel` ("SOAR Queue" section) stating it is historical/frozen for current alert automation, referencing the already-recorded consolidation decision; no removal of existing queue data or functionality.
- [x] 2.16 Add focused component tests and a dark-theme/accessibility pass for the new summary strip, badges, links, and banner.

### Phase 5 — Existing-backlog review tooling or documented handling

- [ ] 2.17 Execute (or explicitly schedule, per user authorization) the read-only identification step from Phase 2's runbook against the live backlog; report counts by `failure_class` without mutating anything.
- [ ] 2.18 If Phase 2.9's optional bulk-dismiss tool was built, use it only under explicit authorization per row-set, never as an automatic cleanup; otherwise proceed via the existing single-row endpoint.

### Phase 6 — Final quality gates and VM handoff

- [x] 2.19 Run the full existing approval, dead-letter, playbook-execution, and SOAR-queue test suites and confirm zero regressions.
- [x] 2.20 Add new focused tests per Phase 1/2/3 items above (terminal-state routing, no-dead-letter-for-expected-path, summary endpoint).
- [x] 2.21 Run `openspec validate improve-unattended-soar-reliability --strict` and `git diff --check` before any handoff.
- [x] 2.22 Prepare (do not execute) a VM handoff package per `docs/mac-vm-source-of-truth-policy.md`: requested commit, migration status (none expected), services requiring restart (`soar-playbook-worker.service` picks up the new status/finalizer logic on restart), and rollback readiness.

### Phase 7 — VM deployment and production verification (explicitly authorized only)

- [ ] 2.23 On explicit user authorization: clean-tree preflight, `git fetch`/`git reset --hard` to the approved commit, restart `soar-playbook-worker.service`, verify health, and confirm no unrelated services were touched.
- [ ] 2.24 Sanitized before/after evidence: dead-letter creation rate for `approval_expired`/`approval_denied` before vs. after (expect zero new rows of that class going forward), confirmation that genuine-failure dead-letter creation is unaffected.

## Safety Boundaries (for this authoring step)

- [x] Creating this spec's proposal/design/tasks/spec files makes no changes under `engines/`, `core/`, `routes/`, `migrations/`, `frontend/`, or `tests/`.
- [x] No schema migration is introduced or assumed by this authoring step.
- [x] No existing OpenSpec change or archived spec is modified.
- [x] Do not commit.
- [x] Do not push.
- [x] Do not archive.
- [x] Do not access the VM.
