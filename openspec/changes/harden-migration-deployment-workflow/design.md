# Design: Harden Migration Deployment Workflow

## Overview

This design turns the migration framework into an operational deployment contract. `scripts/migrate.py` remains the only schema apply mechanism. `schema.sql` remains a reference snapshot. Deployment and CI become the enforcement points that prevent schema drift.

The change is intentionally scoped to operational hardening. It does not change migration semantics, application routes, ingest flow, detection/correlation behavior, playbook execution, or notification delivery.

---

## 1. Deployment Integration

Deployment should run migrations before restarting the backend.

Required order:

1. Sync code on the VM to the target revision.
2. Verify runtime safety flags.
3. Run `scripts/migrate.py` using the VM virtualenv.
4. Stop immediately if migration apply exits non-zero.
5. Restart the backend only after migration apply succeeds.
6. Run health and read-only smoke checks.

The deploy script should use the VM project virtualenv, not system Python:

```bash
venv/bin/python scripts/migrate.py --db-url "$DATABASE_URL"
```

If the project uses `SIEM_DB_*` environment variables instead of a single `DATABASE_URL`, the deploy workflow should construct the equivalent PostgreSQL DSN without printing secrets.

### Fail-fast behavior

Migration apply is a hard gate. If `scripts/migrate.py` exits non-zero:

- Deployment exits non-zero.
- Backend restart is skipped.
- Health checks are skipped because the new runtime must not start against an unknown schema state.
- The deploy log must show which migration failed.
- Operators must inspect `schema_migrations` to identify the last successful version.

### Dry-run option

Deployment should support a staging verification mode that runs:

```bash
venv/bin/python scripts/migrate.py --db-url "$DATABASE_URL" --dry-run
```

Dry-run mode must not create `schema_migrations`, execute DDL, insert ledger rows, restart the backend, run playbooks, or send notifications.

### Logging expectations

Deploy logs should include:

- Target git revision.
- Migration dry-run/apply command shape with secrets redacted.
- Pending migration list or "nothing to apply" output.
- Successful final version.
- Failure reason and failing migration if apply fails.
- Backend restart result.
- Health check result.

Deploy logs must not include DB passwords, API keys, Slack/Teams webhook URLs, or notification payloads.

---

## 2. Runtime Safety Preflight

Before migration apply on staging or VM environments, deployment should verify:

- The migration files are present.
- `scripts/migrate.py` is present.
- The virtualenv Python can import `psycopg2`.
- The DB connection is available.
- Runtime notification mode is safe for staging:
  - `INTEGRATION_MODE=simulation`
  - `SOAR_REAL_SLACK_ENABLED=false` unless an explicitly approved production migration process says otherwise.

Migration execution itself must not call playbook executors, notification adapters, ingest routes, detection engines, or correlation engines. It only connects to PostgreSQL and executes migration SQL.

---

## 3. CI Migration Validation

CI should enforce migration safety before code reaches staging or the VM.

### Numbering validation

CI must fail if:

- Migration versions are not contiguous from `0001`.
- Duplicate version prefixes exist.
- A filename does not match `NNNN_descriptive_slug.sql`.
- A retired version number is reused.

### Destructive SQL lint

CI must fail if migration files contain prohibited destructive patterns:

- `DROP TABLE`
- `TRUNCATE`
- `DELETE FROM`
- `ALTER COLUMN TYPE`
- `RENAME COLUMN`
- `DROP COLUMN`

The lint should also reject `CREATE INDEX CONCURRENTLY` because migrations run inside per-file transactions.

### Guarded constraint replacement exception

`DROP CONSTRAINT` may be allowed only inside a narrowly scoped guarded `DO $$ ... $$` replacement block when all of these are true:

- The block is idempotent.
- The block replaces a named or discovered check constraint with an equivalent forward-compatible constraint.
- The replacement does not drop a table, column, index, or user data.
- The behavior is covered by migration tests or catalog verification.

This exception exists because historical migrations need to refine constraints such as approval target checks while preserving data and forward-only semantics.

### Fresh database apply

CI should create a disposable PostgreSQL database, run all migrations from scratch, then run:

```bash
python3 scripts/migrate.py --db-url "$CI_DATABASE_URL"
python3 scripts/migrate.py --db-url "$CI_DATABASE_URL" --dry-run
```

The second command must report nothing pending and DB version equal to the highest migration.

### pytest integration

CI should run:

```bash
python3 -m py_compile scripts/migrate.py
python3 -m pytest tests/test_schema_migrations.py -v
```

CI should also run the relevant app regression suites for any schema-impacting change.

---

## 4. Schema Drift Prevention

Migration files are the authoritative schema history. `schema.sql` is a reference snapshot only.

Future schema changes must include:

- One new migration file with the next version number.
- A corresponding `schema.sql` snapshot update.
- Tests or CI checks proving the migration chain remains valid.

CI should detect both mismatch directions:

- `schema.sql` changed without a matching migration.
- A migration file changed or was added without a matching `schema.sql` snapshot update.

The exact implementation may compare changed paths in pull requests first, then mature into structural schema diffing by applying migrations to a disposable DB and comparing against a schema snapshot.

Manual SQL on the VM is not a normal deployment path. Emergency manual SQL may only be considered when the application is down or data is at risk, and it must be followed by a forward migration that records the intended schema history.

---

## 5. Failure and Recovery

Rollback is forward-only.

If migration apply fails:

1. Do not restart the backend.
2. Do not manually edit `schema_migrations`.
3. Query the ledger to identify the last successful version.
4. Diagnose the failed migration.
5. If the migration has not been applied anywhere, correct it before deployment continues.
6. If it has been applied anywhere, write a new higher-numbered forward-fix migration.

Before future production migrations, operators should take or verify a database backup/snapshot. The backup is an operational safety net, not a replacement for forward-only migration design.

---

## 6. Future Hardening Ideas

These are intentionally not required for the first implementation slice:

- Checksum validation for already-applied migration files.
- Advisory lock or lock-table protection so two deploys cannot run migrations concurrently.
- CI structural schema diff between cumulative migrations and `schema.sql`.
- Deploy log archival for migration runs.
- A read-only migration status command that prints current DB version and pending migrations.

---

## 7. Safety Boundaries

This change must not:

- Touch detection or correlation internals.
- Change ingest transaction flow.
- Modify SOAR execution semantics.
- Start playbooks during migration execution.
- Send Slack, Teams, or other runtime notifications.
- Change notification adapter behavior.
- Modify frontend behavior.

The migration runner remains a database schema tool only.
