# Tasks: Schema Migration Versioning

This change is design-only. No implementation tasks are approved until this spec is reviewed and the implementation is explicitly authorized.

---

## Pre-implementation review

- [ ] Confirm design.md §9 migration-to-schema.sql mapping against actual git history of `schema.sql` to verify the version split is accurate.
- [ ] Confirm that every `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, and `DO $$ ... $$` block in the current `schema.sql` has a home in exactly one migration file in §9.
- [ ] Confirm that `CREATE INDEX CONCURRENTLY` is not used anywhere in the current `schema.sql` (it would require special handling in migration files). If present, note it.
- [ ] Confirm that the `schema_migrations` table definition (design.md §1) does not conflict with any existing table name in `schema.sql`. Currently no such table exists.
- [ ] Review and accept the rollback policy (forward-only, no destructive down-migrations). This is a permanent constraint on the project.
- [ ] Review and accept the `schema.sql` role change (reference snapshot only, no longer the apply target for live DBs).
- [ ] Identify who owns the VM deploy workflow step and confirm they will follow the documented process.

---

## Implementation slice 1 — Foundation (approved separately)

### Migration file directory

- [ ] Create `migrations/` directory at repo root.
- [ ] Create `migrations/RETIRED.md` stub (empty, for future use when version numbers are retired).
- [ ] Create `migrations/0001_initial_siem_tables.sql` extracted from the original SIEM-era tables in `schema.sql`.
- [ ] Create `migrations/0002_add_soar_incidents.sql`.
- [ ] Create `migrations/0003_add_soar_approvals.sql`.
- [ ] Create `migrations/0004_add_soar_playbooks.sql`.
- [ ] Create `migrations/0005_add_soar_playbook_execution_reliability_columns.sql`.
- [ ] Create `migrations/0006_add_soar_approval_playbook_fk.sql`.
- [ ] Create `migrations/0007_add_soar_notification_delivery.sql`.
- [ ] For each file: verify it is additive only (no DROP, no TRUNCATE, no DELETE, no RENAME, no CONCURRENTLY).
- [ ] For each file: verify it uses `IF NOT EXISTS` guards or `DO $$ ... EXCEPTION WHEN duplicate_object THEN NULL; END $$;` guards for idempotency.
- [ ] Verify that applying all files in order on a blank local DB produces a schema that matches `schema.sql` structurally.

### schema_migrations table

- [ ] The `schema_migrations` table does **not** get its own migration file. It is created by the apply script on first run (`CREATE TABLE IF NOT EXISTS`). This ensures a blank DB can bootstrap without a chicken-and-egg dependency.

### Apply script

- [ ] Create `scripts/migrate.py`.
- [ ] Implement: connect, create `schema_migrations` if not exists.
- [ ] Implement: read applied versions from `schema_migrations`.
- [ ] Implement: list and sort migration files from `migrations/` directory.
- [ ] Implement: gap detection — error and exit if a version number is missing from the directory sequence.
- [ ] Implement: for each unapplied migration, BEGIN, execute SQL, INSERT schema_migrations row, COMMIT.
- [ ] Implement: ROLLBACK and exit non-zero on any SQL error; log the failing migration name and version.
- [ ] Implement: `--dry-run` flag that prints pending migrations without executing.
- [ ] Implement: `--target N` flag that stops at version N.
- [ ] Implement: `--db-url` argument (or read from `DATABASE_URL` env var if not supplied).
- [ ] Implement: final log line: "Nothing to apply. DB at version NNNN." or "Applied N migration(s). DB now at version NNNN."

### Tests

- [ ] Test: fresh DB → apply all migrations → `schema_migrations` contains all versions in order.
- [ ] Test: re-run apply script on fully-migrated DB → no-op, idempotent, exit 0.
- [ ] Test: DB at version 0003 → apply script applies 0004, 0005, 0006, 0007 only.
- [ ] Test: gap in migrations directory (e.g. 0004 missing, 0005 present) → script errors before applying anything.
- [ ] Test: a migration file with an intentional SQL error → transaction rolls back, `schema_migrations` row not inserted, script exits non-zero, DB left at prior version.
- [ ] Test: `--dry-run` prints pending migrations and does not modify the DB.
- [ ] Test: `--target 0003` applies 0001, 0002, 0003 only and stops.
- [ ] Test: all six ingest/detection/correlation regression tests still pass after migration system is added.

---

## Implementation slice 2 — CI and lint (approved separately)

- [ ] Add a CI step that applies all migrations to a blank test DB and diffs the resulting schema against `schema.sql`. Fails if they diverge.
- [ ] Add a CI lint step that greps migration files for prohibited keywords: `DROP TABLE`, `DROP COLUMN`, `TRUNCATE`, `DELETE FROM`, `RENAME`. Fails if found.
- [ ] Add the apply script invocation to the VM deployment runbook.
- [ ] Update any existing deployment documentation that references `psql < schema.sql` to reference `scripts/migrate.py` instead.

---

## Verification commands (after implementation slice 1)

```bash
# Apply to a fresh local DB
python3 scripts/migrate.py --db-url $LOCAL_DB_URL

# Confirm idempotency
python3 scripts/migrate.py --db-url $LOCAL_DB_URL --dry-run
# Expected: "Nothing to apply. DB at version 0007."

# Check migration history
psql $LOCAL_DB_URL -c "SELECT version, name, applied_at FROM schema_migrations ORDER BY version;"

# List tables to confirm schema
psql $LOCAL_DB_URL -c "\dt"

# Backend compile check
python3 -m py_compile core/*.py engines/*.py integrations/*.py routes/*.py scripts/*.py

# Regression suite (must pass unchanged)
python3 -m pytest tests/test_failed_login_detection.py tests/test_password_spraying_detection.py tests/test_correlated_activity.py tests/test_targeted_correlation.py tests/test_ingest_api_contracts.py tests/test_alert_mutation_api_contracts.py -v

# SOAR-specific tests
python3 -m pytest tests/test_soar_worker.py tests/test_playbook_routes.py tests/test_incident_routes.py tests/test_approval_routes.py tests/test_notification_delivery_routes.py -v
```

---

## VM deployment verification (after implementation is live)

```bash
# On the VM: dry-run first
python3 scripts/migrate.py --db-url $DATABASE_URL --dry-run

# Review output. If additive only, proceed.
python3 scripts/migrate.py --db-url $DATABASE_URL

# Confirm DB version
psql $DATABASE_URL -c "SELECT version, name, applied_at FROM schema_migrations ORDER BY version;"

# Confirm nothing left to apply
python3 scripts/migrate.py --db-url $DATABASE_URL --dry-run
# Expected: "Nothing to apply. DB at version NNNN."

# Run smoke-check routes
curl -s http://localhost:5000/health
```

---

## Stop and rollback conditions

- [ ] Stop if any migration file contains `DROP TABLE`, `DROP COLUMN`, `TRUNCATE`, `DELETE FROM`, or `RENAME`. Remove the offending statement and replace with a forward-only correction in a new file.
- [ ] Stop if the apply script fails mid-migration on the VM. Query `schema_migrations` to identify the last successfully applied version. Diagnose the failing migration file. Write a corrective forward migration if needed. Do not attempt destructive rollback.
- [ ] Stop if CI diff between migrations result and `schema.sql` reveals a discrepancy. Correct the migration files or `schema.sql` before merging.
- [ ] Stop if any ingest/detection/correlation regression test fails after the migration system is added. The migration system touches only `migrations/` and `scripts/migrate.py`. If those tests fail, a file outside the stated scope was modified accidentally.
- [ ] Stop if `schema_migrations` table creation interferes with any existing table or FK. (It should not — it has no FKs to application tables.)

---

## Process rules going forward (permanent)

- Every new SOAR table or column addition requires a numbered migration file in `migrations/`.
- The corresponding `schema.sql` update must be in the same PR as the migration file.
- No SQL is applied to the VM outside of `scripts/migrate.py`.
- `psql < schema.sql` is permanently retired as a live-DB apply command.
- Retired version numbers are documented in `migrations/RETIRED.md` and never reused.
- Failed partial migrations are corrected by a new forward migration, not by editing the original file.
