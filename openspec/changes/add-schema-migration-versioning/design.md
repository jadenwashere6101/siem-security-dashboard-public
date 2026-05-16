# Design: Schema Migration Versioning

## Overview

This design establishes a lightweight, additive-only schema migration system. The core contract is simple: every schema change is a numbered SQL file; a `schema_migrations` table records what has been applied; an apply script computes the diff and runs only what is missing in order. No destructive SQL is ever permitted.

---

## 1. Migration History Table

A new table `schema_migrations` is the single source of truth for what has been applied to any given database instance.

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    id            SERIAL PRIMARY KEY,
    version       INTEGER NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    applied_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    applied_by    TEXT,
    checksum      TEXT
);
```

**Field semantics:**

| Field | Purpose |
|---|---|
| `version` | Monotonically increasing integer. Determines apply order. Must be unique. |
| `name` | Human-readable slug matching the filename (e.g. `0001_initial_siem_tables`). |
| `applied_at` | Timestamp of when the migration completed successfully. |
| `applied_by` | Optional: username, hostname, or deploy context. Not required for correctness. |
| `checksum` | Optional: SHA-256 of the migration file contents at apply time. Enables drift detection. |

**Invariants:**

- A row is inserted **only after the migration SQL completes without error**. A row in this table means the migration ran successfully.
- Rows are never updated or deleted. The table is append-only.
- The `version` column has a `UNIQUE` constraint. Applying the same version twice is a no-op (the script checks before running).
- No FK constraints to any application table. This table must be createable on a blank DB before any other table exists.

---

## 2. Migration File Convention

### Directory

```
migrations/
  0001_initial_siem_tables.sql
  0002_add_soar_queue_and_incidents.sql
  0003_add_soar_approvals.sql
  0004_add_soar_playbooks.sql
  0005_add_soar_notification_delivery.sql
  ...
```

### Naming rules

- Zero-padded four-digit version prefix: `0001`, `0002`, ..., `9999`.
- Underscore separator, then a lowercase kebab-style slug describing the change.
- `.sql` extension.
- Name must be stable after creation. Once merged, the filename is immutable.

### Content rules

- **Additive only.** Each file may contain only:
  - `CREATE TABLE IF NOT EXISTS`
  - `CREATE INDEX IF NOT EXISTS` / `CREATE UNIQUE INDEX IF NOT EXISTS`
  - `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
  - `ALTER TABLE ... ADD CONSTRAINT` (wrapped in a `DO $$ BEGIN ... EXCEPTION WHEN duplicate_object THEN NULL; END $$;` guard)
  - `DO $$ ... $$` blocks for idempotent conditional DDL (e.g. constraint replacement logic already used in `schema.sql`)
  - `INSERT` statements for seed/reference data (if needed)
- **Never permitted in a migration file:**
  - `DROP TABLE`
  - `DROP COLUMN`
  - `TRUNCATE`
  - `DELETE`
  - `ALTER TABLE ... RENAME`
  - `DROP INDEX` (except as part of a conditional recreate guard)
  - Any DML that modifies existing row data
- Each file is a self-contained, idempotent unit. Running it twice on the same DB must produce no errors and no data change.
- Files are ordered by version number. Migrations must be applied in strict ascending order.
- A migration file, once committed, is never modified. Corrections go in a new higher-numbered file.

### What `0001_initial_siem_tables.sql` contains

The first migration file is extracted from the current `schema.sql`. It contains all `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` statements for the original SIEM tables:

- `events`
- `alerts`
- `response_actions_log`
- `response_actions_queue`
- `users`
- `audit_log`
- `alert_notes`
- `detection_config`
- `blocked_ips`

And their associated indexes.

Subsequent files cover each major SOAR addition in the order they were actually introduced.

---

## 3. Apply Script Behavior

The apply script is a Python CLI: `scripts/migrate.py`.

### Invocation

```bash
python3 scripts/migrate.py --db-url postgresql://user:pass@host/dbname
python3 scripts/migrate.py --db-url $DATABASE_URL --dry-run
python3 scripts/migrate.py --db-url $DATABASE_URL --target 0003
```

### Algorithm

```
1. Connect to the target DB.
2. CREATE TABLE IF NOT EXISTS schema_migrations (see §1).
3. SELECT version FROM schema_migrations ORDER BY version ASC.
   → This is the set of already-applied versions.
4. List all files in migrations/ directory, sort by version number ascending.
5. For each file in sorted order:
     If file.version is already in applied set: skip (log "already applied").
     If file.version > --target (if provided): stop.
     Otherwise:
       a. Log: "Applying migration NNNN_name.sql ..."
       b. Read file contents.
       c. BEGIN TRANSACTION.
       d. Execute file SQL.
       e. INSERT INTO schema_migrations (version, name, checksum) VALUES (...).
       f. COMMIT.
       g. Log: "Migration NNNN applied."
       If any step d-f raises an error:
         ROLLBACK.
         Log the error with migration version and name.
         EXIT with non-zero status. Do not continue to next migration.
6. Log: "All migrations applied. DB at version NNNN."
```

### Key guarantees

- **Atomic per-migration**: each migration file runs inside its own transaction. If the SQL fails, the transaction rolls back and no partial schema change is written. The `schema_migrations` row is not inserted on failure.
- **No partial state on failure**: a failed migration leaves the DB at the last successfully applied version. The apply script exits non-zero. The next run re-attempts the failed migration.
- **Idempotent on re-run**: `IF NOT EXISTS` guards and the `schema_migrations` check mean re-running the script is always safe. Already-applied migrations are skipped silently.
- **Ordering enforced**: migrations are applied strictly in ascending version order. A gap (e.g. `0003` present but `0002` missing from the migrations/ directory) is treated as an error: the script logs the gap and exits non-zero without applying anything.
- **No full schema.sql replay**: the script never reads or executes `schema.sql`. It only reads from the `migrations/` directory.

### Dry run mode

`--dry-run` prints each migration that *would* be applied (version, name, first 5 lines of SQL) without executing any SQL. Useful for reviewing before a VM deploy.

---

## 4. How schema.sql is Used Going Forward

`schema.sql` remains in the repository but its role changes.

**Old role**: the authoritative apply target. Run `psql < schema.sql` to set up any DB.

**New role**: a human-readable reference snapshot of the full schema at the current HEAD. It is kept up to date by convention — when a new migration file is added, `schema.sql` is also updated to reflect the current full schema. But `schema.sql` is never the file executed against a live database.

**Why keep it**: it provides a complete at-a-glance view of all tables and their current shape, useful for code review, documentation, and verifying that a migration correctly defines its target structure. It also serves as the source of truth for fresh-DB setup via the migration system (the first migration file is derived from it).

**Rule**: `schema.sql` and the cumulative result of all migration files must remain in sync. A CI check (to be defined in a future tasks slice) verifies this by applying all migrations to a blank DB and diffing the result against `schema.sql`.

**Replaying schema.sql on a live DB is permanently prohibited** after the migration system is in place. The `schema.sql` file contains `ALTER TABLE ... ADD COLUMN` and `DO $$ ... $$` constraint-replacement blocks that were written as safe live-DB guards but are not safe to replay arbitrarily. The migration files supersede it as the apply target.

---

## 5. VM Deployment Workflow

### First-time sync on an existing VM (like the Slack smoke test scenario)

When a VM database already has some tables but is missing others:

```
1. Pull the latest repo state on the VM.
2. Run: python3 scripts/migrate.py --db-url $DATABASE_URL --dry-run
   → Review which migrations will be applied.
3. Confirm the dry-run output is additive only (no DROP, no RENAME, no data loss).
4. Run: python3 scripts/migrate.py --db-url $DATABASE_URL
   → The script detects schema_migrations doesn't exist, creates it.
   → It checks which tables/columns already exist (via IF NOT EXISTS guards in each file).
   → It applies missing migrations in order, skipping DDL that already applied.
5. Verify (see §6).
```

### Fresh DB setup (new environment, CI, local dev)

```
1. Create a blank database.
2. Run: python3 scripts/migrate.py --db-url $DATABASE_URL
   → Applies all migrations in order from 0001.
3. Verify (see §6).
```

### Ongoing deploy workflow (new migration added)

```
1. Developer adds migrations/00NN_description.sql.
2. Developer updates schema.sql to reflect the change.
3. PR review includes the new migration file and the schema.sql update.
4. On merge, CI applies the migration to staging: python3 scripts/migrate.py --db-url $STAGING_DB_URL
5. VM deployment: pull repo, run scripts/migrate.py, verify.
```

### Never do this

- Do not run `psql < schema.sql` on a live database.
- Do not apply SQL manually to the VM without recording it in a numbered migration file first.
- Do not edit or delete an existing migration file after it has been applied to any database.
- Do not apply migrations out of order.

---

## 6. Verification Checks After Migration Apply

After every apply (automated or manual), run:

```bash
# 1. Check migration history
psql $DATABASE_URL -c "SELECT version, name, applied_at FROM schema_migrations ORDER BY version;"

# 2. Confirm expected tables exist
psql $DATABASE_URL -c "\dt"

# 3. Confirm the apply script reports nothing left to apply (idempotency check)
python3 scripts/migrate.py --db-url $DATABASE_URL --dry-run
# Expected output: "Nothing to apply. DB at version NNNN."

# 4. Run backend compile check
python3 -m py_compile core/*.py engines/*.py integrations/*.py routes/*.py

# 5. Run SOAR-specific regression tests
python3 -m pytest tests/test_soar_worker.py tests/test_playbook_routes.py tests/test_incident_routes.py tests/test_approval_routes.py tests/test_notification_delivery_routes.py -v

# 6. Run ingest/detection/correlation regression suite (must always pass)
python3 -m pytest tests/test_failed_login_detection.py tests/test_password_spraying_detection.py tests/test_correlated_activity.py tests/test_targeted_correlation.py tests/test_ingest_api_contracts.py tests/test_alert_mutation_api_contracts.py -v
```

---

## 7. Rollback Policy

**There is no destructive rollback.**

This is a deliberate design choice, consistent with the additive-only constraint that has governed every SOAR schema change to date.

**Why no down-migrations:**

- Down-migrations that drop tables or columns risk destroying live operational data (delivery ledger rows, playbook execution records, audit events).
- In practice, no SOAR table has ever needed to be dropped in production. Every correction has been additive.
- Maintaining paired up/down migrations doubles the maintenance burden and creates new risk surface: a carelessly written down-migration on a production database is catastrophic.

**Forward-only fix policy:**

If a migration contains an error:

1. Do not modify the already-applied migration file.
2. Write a new higher-numbered migration file that corrects the schema additively (e.g. adds a missing column, adds a missing index, replaces a wrong constraint via a conditional `DO $$ ... $$` block).
3. Apply the corrective migration through the normal workflow.

**If a migration is rolled back in git before being applied to any live DB:**

The migration file can be deleted from the repository and the version number retired, because no DB has a record of it. Document the retired version in a `migrations/RETIRED.md` file so the number is never reused.

---

## 8. How Future SOAR Table Changes Are Added

Every new SOAR table, column, index, or constraint addition follows this process:

1. **Write the migration file first.** Create `migrations/00NN_description.sql` with the new DDL, additive only. The version number is the next unused integer.
2. **Update `schema.sql`** to incorporate the same DDL so the reference snapshot stays current.
3. **Test locally** by running `scripts/migrate.py` against a local DB that has all prior migrations applied. Confirm the new migration applies cleanly and the schema looks correct.
4. **Add or update tests** that verify the new table/column is used correctly by the application layer.
5. **Include both files in the same PR**: the migration file and the `schema.sql` update. Reviewers check that both are consistent.
6. **On merge**, CI applies the migration to the staging DB. VM receives it on the next deploy.

**Prohibited patterns:**

- Editing `schema.sql` without a paired migration file.
- Adding a migration file without updating `schema.sql`.
- Editing an existing migration file after it has been applied to any DB.
- Adding `DROP`, `TRUNCATE`, `RENAME`, or bulk `DELETE` to any migration file.
- Applying any ad-hoc SQL to the VM without a corresponding migration file.

---

## 9. Mapping Current schema.sql to Migration Files

The following migration file structure covers the current `schema.sql` history as best as it can be reconstructed:

| Version | Name | Contents |
|---|---|---|
| 0001 | `initial_siem_tables` | `events`, `alerts`, `response_actions_log`, `response_actions_queue`, `users`, `audit_log`, `alert_notes`, `detection_config`, `blocked_ips`, all associated indexes |
| 0002 | `add_soar_incidents` | `incidents`, `incident_alerts`, associated indexes |
| 0003 | `add_soar_approvals` | `approval_requests`, `approval_request_events`, associated indexes, initial constraint shape |
| 0004 | `add_soar_playbooks` | `playbook_definitions`, `playbook_executions`, `playbook_schedules`, associated indexes, active-execution partial unique index |
| 0005 | `add_soar_playbook_execution_reliability_columns` | `ALTER TABLE playbook_executions ADD COLUMN IF NOT EXISTS` for `attempt_count`, `max_attempts`, `last_attempted_at`, `failure_reason`, `stale_after`, `timeout_seconds` |
| 0006 | `add_soar_approval_playbook_fk` | `ALTER TABLE approval_requests ADD COLUMN IF NOT EXISTS playbook_execution_id`, `playbook_step_index`; FK constraint; `playbook_execution_id` and `playbook_step_active` indexes; updated `target_check` constraint |
| 0007 | `add_soar_notification_delivery` | `notification_delivery_attempts`, all associated indexes |

This mapping is approximate — the exact split across files should be validated against the actual schema.sql diff history during implementation. The goal of the split is to make each migration file self-contained and independently re-runnable on a blank DB.

---

## 10. Risk Analysis

### Schema drift between repo and VM

**Risk**: The VM silently lags behind the repo. Code expects a column or table that doesn't exist yet on the VM.

**Mitigation**: `schema_migrations` table makes the VM's version queryable. Dry-run before every deploy shows exactly what will be applied. The apply script is the first step of every deploy, not an optional step.

### Duplicate or manual migrations

**Risk**: An operator manually applies SQL to the VM without creating a migration file. The migration system has no record of it. A later migration that re-creates the same object fails with an error.

**Mitigation**: `IF NOT EXISTS` guards on `CREATE TABLE` and `CREATE INDEX` make duplicate DDL a no-op, not an error. `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` handles duplicate column adds. The apply script will skip already-applied version numbers. The primary defense is process: the rule that no SQL goes to the VM except through a numbered migration file.

### Destructive schema changes

**Risk**: Someone adds `DROP TABLE` or `DROP COLUMN` to a migration file, executing it against a live DB and destroying data.

**Mitigation**: The additive-only rule is enforced at PR review. A CI lint step (to be defined) can grep migration files for prohibited keywords (`DROP TABLE`, `DROP COLUMN`, `TRUNCATE`, `DELETE`, `RENAME`) and fail the build if found.

### Live DB data loss

**Risk**: A migration file contains a `DELETE` or `UPDATE` that modifies existing rows unintentionally.

**Mitigation**: Additive-only rule prohibits all DML except seeding of reference/config rows. PR review checks for DML in migration files.

### Environment mismatch

**Risk**: A migration is applied to staging but not to the VM (or vice versa), causing the environments to diverge.

**Mitigation**: `schema_migrations` is per-DB. Running `SELECT version, name FROM schema_migrations ORDER BY version` on each environment shows its exact state. The deploy workflow includes a dry-run comparison step before every apply. Environments can be compared directly.

### Migration ordering

**Risk**: Migrations are applied out of order. A table that a FK depends on does not exist yet.

**Mitigation**: The apply script enforces ascending order. It validates that no version gaps exist in the `migrations/` directory before applying anything. A migration that references a table introduced in a later migration is caught at test time when the apply script is run from version 0001 on a blank DB.

### Failed partial migration

**Risk**: A migration file contains multiple DDL statements. The first succeeds, the second fails. The DB is left in an inconsistent intermediate state.

**Mitigation**: Each migration file executes inside a single transaction (BEGIN ... COMMIT). PostgreSQL DDL is transactional. On failure the entire transaction rolls back. The `schema_migrations` row is only inserted on COMMIT. The DB is always left at a clean version boundary.

**Caveat**: Some DDL operations in PostgreSQL cannot run inside a transaction (e.g. `CREATE INDEX CONCURRENTLY`). Migration files must not use `CONCURRENTLY` or other non-transactional DDL. Standard `CREATE INDEX IF NOT EXISTS` is transactional and safe.

### Replaying schema.sql on a live DB (prevented, not just mitigated)

**Risk**: Someone runs `psql < schema.sql` on the VM, re-executing the `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` and `DO $$ ... $$` blocks against a DB that already has those columns, and triggering the constraint-replacement `DO $$ ... $$` blocks which drop and re-add constraints.

**Mitigation**: The `IF NOT EXISTS` guards and `DO $$ ... $$` blocks in `schema.sql` were written to be re-runnable, but this is fragile — a re-run could drop and recreate a constraint while live rows violate the new shape. The migration system eliminates this risk by making `psql < schema.sql` permanently the wrong command for live DB updates. The apply script is the only supported path. Document this prohibition explicitly in deployment runbooks and the project README.
