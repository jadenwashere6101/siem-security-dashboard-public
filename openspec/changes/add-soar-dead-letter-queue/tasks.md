# Tasks: SOAR Dead Letter Queue

Implementation should be split into small approved slices. Do not implement from this proposal step.

---

## Pre-implementation Review

- [x] Inspect existing SOAR playbook execution failure paths.
- [x] Inspect response action queue/log failure paths.
- [x] Inspect notification delivery failure paths.
- [x] Inspect approval denial/expiration behavior.
- [x] Inspect existing RBAC/audit route patterns.
- [x] Confirm migration workflow and current latest migration number.
- [x] Confirm metadata redaction helpers that can be reused.

---

## Slice 1 — Schema and Store Foundation

- [x] Add a forward-only migration for `soar_dead_letters`.
- [x] Add indexes and active-source duplicate prevention.
- [x] Update schema reference snapshot only if required by migration workflow.
- [x] Create dead letter store module/helpers.
- [x] Validate statuses, source types, retryability, and dismissal reason.
- [x] Redact/sanitize metadata before persistence.
- [x] Add tests for create/list/detail/idempotency/validation.

---

## Slice 2 — Capture Failed Work

- [x] Capture failed playbook execution dead letters.
- [ ] Capture failed response action queue dead letters if compatible with current queue flow.
- [ ] Capture notification delivery dead letters only for operator-actionable terminal failures.
- [x] Ensure creation is idempotent for the same active source.
- [x] Ensure read/list/metrics paths do not create dead letters.
- [x] Add tests for each enabled source capture path.

---

## Slice 3 — Review Routes

- [x] Add authenticated list route.
- [x] Add authenticated detail route.
- [x] Add filters for status, source type, retryable, limit, and offset.
- [x] Apply existing RBAC conventions.
- [x] Redact secret-bearing metadata in responses.
- [x] Add route tests for auth, RBAC, filters, shape, no mutation, and 404s.

---

## Slice 4 — Retry and Dismiss Routes

- [x] Add manual retry endpoint.
- [x] Add dismissal endpoint with required reason.
- [x] Audit retry and dismissal actions.
- [x] Preserve approval semantics.
- [ ] Block retry when idempotency cannot be proven.
- [x] Ensure retry does not directly call adapters or send notifications.
- [x] Add tests for allowed retry, blocked retry, dismissal, audit, and no adapter calls.

---

## Slice 5 — Metrics and Operations

- [x] Add dead letter metrics helper.
- [x] Add metrics route for count/depth/source/failure-class breakdowns.
- [x] Ensure metrics responses do not expose metadata or secrets.
- [ ] Document operational review workflow.
- [x] Add tests for counts, oldest age, filters, no mutation, and auth/RBAC.

---

## Verification Planning

- [x] Run dead letter store tests.
- [x] Run dead letter route tests.
- [x] Run playbook execution route tests.
- [ ] Run response action queue tests.
- [x] Run notification delivery store/routes/metrics tests.
- [ ] Run approval route/store tests.
- [x] Run ingest/detection/correlation regression suite.
- [ ] Run migration validation on a disposable database.
- [x] Run `git diff --check`.

---

## Safety Boundaries

- [x] Do not change ingest transaction flow.
- [x] Do not change detection internals.
- [x] Do not change correlation internals.
- [x] Do not create destructive migrations.
- [x] Do not edit `schema.sql` directly outside the migration snapshot workflow.
- [x] Do not run VM or live DB actions.
- [x] Do not send notifications.
- [x] Do not run playbooks from dead letter creation/list/detail/metrics.
- [x] Do not add autonomous retry loops, daemons, cron jobs, or schedulers.
- [x] Do not add frontend work in the first implementation unless separately approved.
