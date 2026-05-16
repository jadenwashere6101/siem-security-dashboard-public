# Proposal: Schema Migration Versioning

## Problem

During Slack staging smoke-test preparation on the Azure VM, the database was missing all SOAR tables even though application code expected them. The gap was discovered only when trying to run the smoke test. It was resolved by manually running additive SQL statements against the live VM.

The root cause is that `schema.sql` is a monolithic idempotent definition file, not a versioned migration record. There is no authoritative way to know:

- Which version of the schema a given database is at.
- Which changes have already been applied to a live database.
- Which SQL needs to run when deploying a new environment or syncing an existing one.

This creates a class of risks that will grow larger as the SOAR layer adds more tables and constraints:

- **Schema drift**: The repo schema and the VM schema silently diverge. Code that expects a column or table will fail at runtime, not at deploy time.
- **Re-replay danger**: Replaying the full `schema.sql` on a live database is unsafe because `schema.sql` now contains `ALTER TABLE`, `DO $$ ... $$` blocks, and index-drop-then-recreate patterns that were written as safe idempotent guards for a live DB but were never designed as a repeatable migration file.
- **Manual intervention as the only recovery path**: When schema drift is discovered, the fix requires manually identifying what is missing and writing one-off SQL — with no record that the fix was applied.
- **No deployment workflow**: There is no documented or scripted process for applying schema changes to the VM on each deploy.

## Goal

Design a lightweight, additive-only schema migration system that:

1. Tracks which migrations have been applied to each database instance.
2. Gives every schema change a numbered, immutable file with a clear name and intent.
3. Provides a safe, reproducible apply script that can run on a fresh DB or an existing live DB without replaying the full `schema.sql`.
4. Eliminates manual schema sync as the default path for VM deployments.
5. Establishes a rule: future SOAR table additions happen through numbered migration files, not inline edits to `schema.sql`.

## Scope

- Define the `schema_migrations` history table and its contract.
- Define the numbered migration file naming convention and directory structure.
- Define the apply script behavior (fresh DB vs live DB, idempotency, partial failure handling).
- Define the VM deployment workflow using the migration system.
- Define the rollback policy (no destructive rollback; forward-only fixes only).
- Define verification checks to run after any migration apply.
- Define how `schema.sql` is used going forward (reference snapshot only, not the apply target).
- Define how future SOAR table changes must be written.
- Define the risk surface before any implementation begins.

## Out of scope

- No code implementation in this change.
- No SQL execution.
- No edits to `schema.sql`.
- No database changes.
- No changes to ingest, detection, correlation, or their transaction contracts.
- No changes to any existing route, store, engine, or adapter.
- No Redis, Celery, APScheduler, or background worker changes.
- No frontend changes.
- No commit to version control.

## Success criteria

- A numbered, append-only migration file directory exists with one file per schema change.
- A `schema_migrations` table in the database tracks applied migrations by number and name.
- An apply script can determine what is missing on any target DB and apply only unapplied migrations in order.
- Replaying the full `schema.sql` on a live database is no longer the recovery path or the deploy workflow.
- All future SOAR table changes go through a numbered migration file, not a direct `schema.sql` edit.
- A failed partial migration is detectable and recoverable without data loss.
- The VM deployment workflow is documented step-by-step and does not require manual SQL identification.
- No existing ingest/detection/correlation behavior is touched.

## Why now

The Slack smoke test exposed the schema drift problem in a high-stakes moment. At that point we had nine missing SOAR tables on the VM and no scripted path to fix the gap safely. The fix was applied manually and carefully. That worked this time — but as the SOAR layer grows (Redis state, scheduler tables, dead-letter queue, rate limiting tables), the risk of missing a table or column on a VM deploy increases. Establishing the migration system now, before those changes arrive, means every future SOAR table addition is automatically covered.
