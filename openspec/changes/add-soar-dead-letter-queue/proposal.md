# Proposal: SOAR Dead Letter Queue

## Problem

SOAR playbook execution now has lease ownership, stale recovery, durable resume, and duplicate side-effect guards. Failed playbook/action work still lacks a durable review queue. Failures are visible through execution rows, logs, delivery records, and action queue statuses, but operators do not have one consistent place to review failed SOAR work, understand retry eligibility, dismiss known failures, or measure backlog depth.

This creates operational risk:

- Failed remediation or notification actions can be overlooked after the original execution finishes.
- Retry decisions may be made from scattered state rather than a durable failure record.
- Approval-related failures need explicit review so retries do not bypass approval semantics.
- Metrics cannot cleanly answer how much failed SOAR work is awaiting operator attention.

## Goal

Add a durable SOAR dead letter queue for failed playbook/action work that supports operator review, safe retry, dismissal, and backlog metrics without introducing autonomous retry loops.

The change should:

1. Persist failed SOAR work in a forward-only migration-managed table.
2. Provide store helpers for enqueue/list/detail/retry/dismiss flows.
3. Add read and mutation routes for review, retry, and dismissal.
4. Preserve approval semantics and idempotency guarantees.
5. Expose metrics for dead letter count/depth.
6. Keep initial frontend visibility out of scope unless a later slice explicitly adds it.

## Scope

- Create a migration for a durable `soar_dead_letters` or `failed_actions` table.
- Capture failure source, failure class, execution/action linkage, retry eligibility, dismissal state, and safe metadata.
- Add store helpers for:
  - create/upsert dead letter records from failed playbook/action outcomes
  - list/detail filtering
  - mark retry requested/performed
  - dismiss with reason and actor
- Add routes for list/detail/retry/dismiss.
- Add metrics for open dead letter count and age/depth.
- Define retry behavior that is explicit, manual, idempotency-aware, and approval-aware.
- Document operational behavior and tests.

## Out of Scope

- No code implementation in this proposal step.
- No schema changes until an approved implementation slice.
- No direct `schema.sql` edits; schema changes must use migrations.
- No VM actions.
- No autonomous retry loops, daemon workers, cron jobs, or schedulers.
- No frontend work in the first implementation.
- No notification sending as part of dead letter review.
- No playbook execution during spec creation.
- No changes to ingest, detection, or correlation transaction contracts.

## Success Criteria

- Operators can list and inspect failed SOAR work from a durable queue.
- Retry is explicit and safe, and does not bypass active approvals.
- Dismissal records who dismissed the item and why.
- Dead letter metrics show current open backlog and basic depth.
- Duplicate dead letter records are avoided for the same failed unit of work.
- Existing SOAR execution, notification delivery, approval, ingest, detection, and correlation behavior remains compatible.

## Why Now

The migration framework, deployment workflow, lease ownership, stale recovery, and duplicate side-effect prevention are now stable. A dead letter queue is the next reliability layer: it gives operators a durable review surface before adding more automation around scheduled playbooks or real remediation.
