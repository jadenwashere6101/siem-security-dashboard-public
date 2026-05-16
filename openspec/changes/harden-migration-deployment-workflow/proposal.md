# Proposal: Harden Migration Deployment Workflow

## Problem

The schema migration system is now implemented and proven in three important paths:

- migrations `0001` through `0008` exist and apply cleanly on a fresh disposable database.
- `scripts/migrate.py` is operational and records successful migrations in `schema_migrations`.
- The Azure VM database has been aligned through the normal runner and now reports version `0008`.

The remaining risk is operational, not structural. The project still needs guardrails that make the migration workflow the default path during deployment and CI. Without those guardrails, future changes can still reintroduce drift:

- A deploy could restart the backend before required migrations apply.
- A migration file could be added with a numbering gap or unsafe SQL.
- `schema.sql` could diverge from migration history.
- A developer or operator could accidentally rely on manual SQL instead of the ledger-backed runner.
- CI could pass even when a fresh database cannot be created from the migration chain.

## Goal

Create an operational hardening plan for deployment and CI so schema migrations remain safe, reproducible, and visible.

This change will define how deployment should invoke migrations, how CI should validate migration history, and how future schema drift should be prevented.

## Scope

- Integrate migration execution into deployment ordering.
- Require VM deployment to use the project virtualenv interpreter for `scripts/migrate.py`.
- Define fail-fast behavior so backend restart does not happen after a failed migration.
- Define dry-run behavior for staging verification.
- Add CI validation requirements for migration numbering, destructive SQL, schema snapshot parity, and fresh-database migration apply.
- Define `schema.sql` as a reference snapshot only, with migrations as authoritative history.
- Document the forward-only migration policy and no-manual-VM-SQL policy.
- Define operational preflight checks, logging expectations, backup recommendations, and failure handling.
- Capture future hardening ideas, including checksum validation and migration locking.

## Out of scope

- No implementation in this change.
- No edits to `deploy.sh`.
- No edits to CI configuration.
- No edits to `schema.sql`.
- No migration file edits.
- No database changes.
- No VM actions.
- No changes to ingest, detection, correlation, or their transaction contracts.
- No changes to SOAR execution semantics.
- No route, adapter, executor, or frontend changes.
- No runtime notification execution.
- No commit to version control.

## Success criteria

- Deployment order is specified as: git sync, migration apply, backend restart, health verification.
- Deployment fails before backend restart if migration apply fails.
- CI rejects migration gaps, duplicate versions, destructive SQL, and migration/schema snapshot drift.
- CI proves the full migration chain applies to a disposable fresh database.
- The allowed exception for guarded `DROP CONSTRAINT` inside conditional replacement blocks is documented.
- Operators have a clear staging dry-run and post-apply verification workflow.
- The spec preserves existing ingest/detection/correlation contracts and SOAR runtime safety boundaries.

## Why now

The VM ledger is now aligned and the migration chain is no longer theoretical. This is the right moment to move from manual validation to repeatable operational enforcement. Hardening deploy and CI next keeps the new migration system from becoming optional process knowledge.
