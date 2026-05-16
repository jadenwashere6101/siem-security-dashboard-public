# Tasks: Harden Migration Deployment Workflow

This change is a spec for operational hardening. No implementation is included in this proposal.

---

## Pre-implementation review

- [ ] Confirm current `deploy.sh` ordering and identify where migration apply belongs.
- [ ] Confirm how VM deployment currently loads DB credentials.
- [ ] Confirm VM deployment can use `venv/bin/python` reliably.
- [ ] Confirm staging runtime safety flags expected before migration apply.
- [ ] Confirm the CI environment can create a disposable PostgreSQL database.
- [ ] Confirm whether CI should use Docker PostgreSQL, a service container, or an existing test DB fixture.
- [ ] Confirm the allowed destructive-keyword lint exception for guarded `DROP CONSTRAINT` replacement blocks.

---

## Deployment integration

- [ ] Add migration preflight to deployment:
  - [ ] Verify `scripts/migrate.py` exists.
  - [ ] Verify `migrations/` exists.
  - [ ] Verify migration versions are contiguous.
  - [ ] Verify `venv/bin/python` can import `psycopg2`.
  - [ ] Verify DB connection settings are present without printing secrets.
- [ ] Add runtime safety preflight:
  - [ ] Confirm `INTEGRATION_MODE=simulation` for staging.
  - [ ] Confirm `SOAR_REAL_SLACK_ENABLED=false` for staging.
  - [ ] Confirm the deploy step does not invoke playbooks or notification adapters.
- [ ] Add migration apply before backend restart:
  - [ ] Run `venv/bin/python scripts/migrate.py --db-url "$DATABASE_URL"`.
  - [ ] Capture and print migration runner output.
  - [ ] Redact secrets from logs.
  - [ ] Exit deployment immediately on non-zero migration result.
  - [ ] Ensure backend restart is skipped if migration apply fails.
- [ ] Add a deploy dry-run mode:
  - [ ] Run `venv/bin/python scripts/migrate.py --db-url "$DATABASE_URL" --dry-run`.
  - [ ] Do not restart backend in dry-run mode.
  - [ ] Do not modify DB in dry-run mode.
- [ ] Enforce deployment ordering:
  - [ ] Git sync.
  - [ ] Migration preflight.
  - [ ] Migration apply.
  - [ ] Backend restart.
  - [ ] Health verification.
  - [ ] Read-only SOAR endpoint verification.

---

## CI validation

- [ ] Add migration filename validation:
  - [ ] Require `NNNN_descriptive_slug.sql`.
  - [ ] Reject duplicate versions.
  - [ ] Reject gaps from `0001` to highest migration.
  - [ ] Reject reused retired versions.
- [ ] Add destructive SQL lint:
  - [ ] Reject `DROP TABLE`.
  - [ ] Reject `TRUNCATE`.
  - [ ] Reject `DELETE FROM`.
  - [ ] Reject `ALTER COLUMN TYPE`.
  - [ ] Reject `RENAME COLUMN`.
  - [ ] Reject `DROP COLUMN`.
  - [ ] Reject `CREATE INDEX CONCURRENTLY`.
  - [ ] Allow guarded `DROP CONSTRAINT` only inside reviewed/idempotent `DO $$` replacement blocks.
- [ ] Add schema drift path checks:
  - [ ] Fail when `schema.sql` changes without a migration change.
  - [ ] Fail when a migration is added or modified without a `schema.sql` snapshot update.
  - [ ] Document how emergency exceptions are approved.
- [ ] Add fresh database migration validation:
  - [ ] Create disposable PostgreSQL database in CI.
  - [ ] Run `python3 scripts/migrate.py --db-url "$CI_DATABASE_URL"`.
  - [ ] Run `python3 scripts/migrate.py --db-url "$CI_DATABASE_URL" --dry-run`.
  - [ ] Assert dry-run reports no pending migrations.
  - [ ] Assert `schema_migrations` records all versions.
- [ ] Add pytest checks:
  - [ ] Run `python3 -m py_compile scripts/migrate.py`.
  - [ ] Run `python3 -m pytest tests/test_schema_migrations.py -v`.
  - [ ] Run relevant SOAR and ingest/detection/correlation regression suites for schema-impacting PRs.

---

## Schema drift prevention docs

- [ ] Update migration workflow documentation to state:
  - [ ] Migrations are authoritative history.
  - [ ] `schema.sql` is reference snapshot only.
  - [ ] VM SQL must go through `scripts/migrate.py`.
  - [ ] Manual VM SQL is emergency-only and requires a follow-up forward migration.
  - [ ] Rollback is forward-fix migration only.
- [ ] Document operator commands:
  - [ ] Check current DB migration version.
  - [ ] Run dry-run.
  - [ ] Run apply.
  - [ ] Verify no pending migrations.
  - [ ] Inspect failed migration state.

---

## VM staging validation workflow

- [ ] On staging VM, run migration dry-run after deploy script changes.
- [ ] Confirm dry-run output is additive and expected.
- [ ] Run migration apply through deploy script on staging.
- [ ] Verify `schema_migrations` records expected versions.
- [ ] Verify post-apply dry-run reports no pending migrations.
- [ ] Verify backend restart occurs only after migration success.
- [ ] Verify health endpoint after restart.
- [ ] Verify read-only SOAR endpoints:
  - [ ] `/playbooks`
  - [ ] `/playbook-executions`
  - [ ] `/notification-deliveries`
  - [ ] `/metrics/notifications`
  - [ ] `/integrations/status`
- [ ] Verify runtime remains simulation-safe.
- [ ] Verify no notification delivery rows are created by migration/deploy.

---

## Rollback/failure simulation checks

- [ ] Simulate migration command failure in a safe test environment.
- [ ] Confirm deploy exits non-zero.
- [ ] Confirm backend restart is skipped.
- [ ] Confirm failure output identifies the failed migration.
- [ ] Confirm `schema_migrations` does not record failed migration.
- [ ] Simulate CI migration numbering gap.
- [ ] Simulate CI destructive SQL lint failure.
- [ ] Simulate `schema.sql` changed without migration.
- [ ] Simulate migration added without `schema.sql` update.

---

## Deploy verification checklist

- [ ] Runtime safety flags checked before migration.
- [ ] Migration runner uses VM virtualenv.
- [ ] Migration output captured.
- [ ] Backend restart gated on migration success.
- [ ] Health check runs after restart.
- [ ] Read-only endpoint checks pass.
- [ ] Migration dry-run reports no pending migrations after deploy.
- [ ] No playbooks executed.
- [ ] No notifications sent.
- [ ] No manual `schema_migrations` inserts.
- [ ] No manual VM SQL.
- [ ] No destructive SQL.

---

## Safety boundaries

- [ ] Do not touch detection internals.
- [ ] Do not touch correlation internals.
- [ ] Do not change ingest transaction flow.
- [ ] Do not change SOAR execution semantics.
- [ ] Do not run playbooks from migration or deploy steps.
- [ ] Do not send runtime notifications from migration or deploy steps.
- [ ] Do not change frontend behavior.
