# Proposal: SOAR Execution Locking and Stale Recovery

## Problem

SOAR playbook execution has grown from a simulation path into an operational workflow with approvals, notification delivery records, retries, and VM deployment support. The current execution model has useful safeguards, including `FOR UPDATE SKIP LOCKED` when claiming pending executions and idempotent approval request creation, but it does not yet have a complete ownership model.

Current gaps:

- A `running` execution has no worker owner or lease expiration.
- There is no heartbeat timestamp to distinguish a healthy long-running worker from a crashed one.
- Stale-running detection exists as metadata helpers, but no recovery workflow safely reclaims or terminally marks stuck executions.
- Awaiting-approval resume is status-based and not integrated with worker ownership.
- Notification delivery rows are append-only, but duplicated step execution could still create duplicate delivery attempts if stale recovery replays a step carelessly.

These gaps are manageable in single-run simulation, but they become risky once multiple workers, scheduled execution, or longer-running steps are introduced.

## Goal

Design a safe, additive locking and stale recovery model for playbook executions that:

1. Prevents two workers from processing the same execution simultaneously.
2. Supports worker crash recovery.
3. Avoids duplicate notification or remediation actions.
4. Preserves approval semantics.
5. Preserves existing idempotency guarantees.
6. Fits the migration/versioning system and remains forward-only.

## Scope

- Define lease ownership fields for `playbook_executions`.
- Define heartbeat and stale timeout behavior.
- Define claim/resume/recovery transaction boundaries.
- Define use of `SELECT ... FOR UPDATE SKIP LOCKED`.
- Define worker identity generation and logging.
- Define interaction with retries, approvals, notification delivery, and terminal statuses.
- Define observability and manual recovery workflows.
- Split implementation into safe slices.

## Out of scope

- No implementation in this change.
- No schema migration creation yet.
- No edits to `schema.sql`.
- No runtime behavior changes.
- No changes to notification adapter execution.
- No changes to ingest, detection, or correlation.
- No frontend changes unless a later implementation slice explicitly adds admin visibility.
- No VM actions.
- No commit to version control.

## Success criteria

- The design explains how pending and approval-resumed executions are claimed by one worker only.
- The design explains how stale `running` executions are identified and recovered without duplicate side effects.
- The design defines idempotency rules for notification and remediation steps.
- The design preserves current approval behavior: pending approvals are not force-resumed, and denied/expired approvals still stop safely.
- The design is additive and migration-safe.
- The implementation can be split into small, testable slices.

## Why now

Migration/deploy/CI hardening is stable, so schema changes can now be introduced safely when needed. Execution locking should be designed before adding more automation around scheduled playbooks or daemonized workers, because concurrency and stale recovery are foundational reliability concerns.
