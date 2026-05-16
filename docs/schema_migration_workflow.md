# Schema Migration Workflow

**Spec:** SPEC-SCHEMA-001 (`openspec/changes/add-schema-migration-versioning/`)  
**Apply tool:** `scripts/migrate.py`  
**Migration files:** `migrations/*.sql`

This document is the operator and developer runbook for schema changes. It complements the design in `openspec/changes/add-schema-migration-versioning/design.md`.

---

## 1. Purpose

The SIEM/SOAR stack needs a **versioned, additive-only** way to change PostgreSQL schema on fresh databases, staging, and long-lived VMs—without replaying the monolithic `schema.sql` file against live data.

`scripts/migrate.py` applies numbered SQL files in order and records each successful apply in `schema_migrations`. That table is the **only** authoritative record of which migration versions a database has received.

**Goals:**

- Know exactly which schema version a database is on.
- Apply only missing migrations on deploy.
- Keep DDL idempotent and forward-only.
- Stop using `psql < schema.sql` as a live-database update path.

**Current repo state (slice 1 foundation):**

- `migrations/0001_schema_migrations.sql` — creates the `schema_migrations` history table.
- `scripts/migrate.py` — discovery, dry-run, apply, `--target`.
- `tests/test_schema_migrations.py` — framework behavior tests.

Historical extraction of SIEM/SOAR tables from `schema.sql` into `0002+` files is **not** done yet. Until those files exist, operators with existing VMs may still have schema created by earlier manual or `schema.sql` paths; new work must follow this workflow going forward.

---

## 2. How migration numbering works

### Filename convention

```
migrations/NNNN_descriptive_slug.sql
```

| Rule | Detail |
|------|--------|
| Prefix | Four-digit zero-padded integer: `0001`, `0002`, … |
| Separator | Single underscore after the version |
| Slug | Lowercase words separated by underscores (e.g. `add_soar_incidents`) |
| Extension | `.sql` only |
| Immutability | Once merged and applied anywhere, **never edit** the file. Corrections use a new higher number. |

Examples (illustrative):

- `migrations/0001_schema_migrations.sql`
- `migrations/0002_add_soar_incidents.sql`

### Version sequence

- Versions must be **contiguous** starting at `0001` with no gaps (`0001`, `0002`, `0003`, …).
- `scripts/migrate.py` rejects a missing intermediate version before applying anything.
- Duplicate version numbers in the directory are rejected.

### What each version records

After a migration succeeds, one row is inserted into `schema_migrations`:

| Column | Meaning |
|--------|---------|
| `version` | Integer from the filename prefix |
| `name` | Filename stem (e.g. `0002_add_soar_incidents`) |
| `applied_at` | Timestamp |
| `applied_by` | `user@hostname` from the apply environment |
| `checksum` | SHA-256 of the file at apply time |

Rows are **append-only** (no updates or deletes).

### Retired numbers

If a migration is removed from git **before** any database applied it, document the retired version in `migrations/RETIRED.md` and do not reuse that number.

---

## 3. Local dry-run workflow

Use a **local or disposable** database only. Do not use production or shared VM URLs for experimentation unless you are performing an approved deploy.

### Prerequisites

- Python 3 with `psycopg2` available (same as the app).
- A PostgreSQL DSN, e.g. `postgresql://USER:PASSWORD@HOST:PORT/DATABASE`.

### Steps

1. **Set the DSN** (placeholder):

   ```bash
   export DATABASE_URL='postgresql://USER:PASSWORD@localhost:5432/DBNAME'
   ```

2. **Dry-run** — lists pending migrations and previews the first lines of each file; does **not** create `schema_migrations` or run migration SQL:

   ```bash
   python3 scripts/migrate.py --db-url "$DATABASE_URL" --dry-run
   ```

   Expected when fully up to date:

   ```text
   Nothing to apply. DB at version NNNN.
   ```

3. **Review output** — confirm only additive DDL (`CREATE … IF NOT EXISTS`, `ALTER TABLE … ADD COLUMN IF NOT EXISTS`, guarded `DO $$` blocks). No `DROP TABLE`, `DROP COLUMN`, `TRUNCATE`, or bulk `DELETE`.

4. **Apply** (local only):

   ```bash
   python3 scripts/migrate.py --db-url "$DATABASE_URL"
   ```

5. **Re-run dry-run** — confirms idempotency:

   ```bash
   python3 scripts/migrate.py --db-url "$DATABASE_URL" --dry-run
   ```

### Partial apply (optional)

Stop after a specific version (numeric, with or without leading zeros):

```bash
python3 scripts/migrate.py --db-url "$DATABASE_URL" --target 3
```

### Run framework tests (no live DB required)

```bash
python3 -m pytest tests/test_schema_migrations.py -v
```

---

## 4. VM deployment workflow

Use this on the Azure VM (or any long-lived environment) when pulling a release that includes new `migrations/*.sql` files.

### Before you start

- Pull the target git revision on the VM.
- Confirm `DATABASE_URL` (or equivalent) points at the **intended** database.
- Ensure no other operator is applying schema changes at the same time.
- **Do not** run `psql -f schema.sql` or pipe `schema.sql` into `psql` on the VM.

### First-time migration system on an existing VM

Many VMs already have tables from earlier additive SQL or `schema.sql` guards. The migration runner is designed for that:

1. Dry-run and read the pending list:

   ```bash
   cd /path/to/siem-security-dashboard-public
   python3 scripts/migrate.py --db-url "$DATABASE_URL" --dry-run
   ```

2. If pending migrations use only `IF NOT EXISTS` / safe guards, objects that already exist are no-ops; only missing objects are created.

3. Apply:

   ```bash
   python3 scripts/migrate.py --db-url "$DATABASE_URL"
   ```

4. Run verification (section 8).

### Ongoing deploy (new migration in release)

1. Pull latest code.
2. Dry-run → review pending migrations.
3. Apply → verify → deploy/restart application if needed.
4. Run application health checks (e.g. `GET /health`) after schema apply.

### Fresh database on the VM

1. Create an empty database.
2. Run `python3 scripts/migrate.py --db-url "$DATABASE_URL"` once (applies all files from `0001` upward).
3. Verify (section 8).

### If apply fails

- The failed migration is rolled back in a single transaction; `schema_migrations` is **not** updated for that version.
- Query the last successful version (section 8).
- Fix forward with a **new** migration file or corrected SQL in a new version—never edit an already-applied file.
- Do **not** attempt destructive rollback.

---

## 5. How to add a new migration

1. **Choose the next version** — highest existing `NNNN` + 1. Check `migrations/RETIRED.md` for numbers that must not be reused.

2. **Create the file** — additive DDL only, idempotent guards on every statement:

   ```sql
   -- migrations/0008_add_example_table.sql
   CREATE TABLE IF NOT EXISTS example (
       id SERIAL PRIMARY KEY,
       created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
   );

   CREATE INDEX IF NOT EXISTS idx_example_created_at
       ON example (created_at);
   ```

3. **Update `schema.sql`** in the **same change** so the reference snapshot matches the cumulative result of all migrations. Reviewers must see both files.

4. **Test locally** on a DB that has all prior migrations applied:

   ```bash
   python3 scripts/migrate.py --db-url "$LOCAL_DATABASE_URL" --dry-run
   python3 scripts/migrate.py --db-url "$LOCAL_DATABASE_URL"
   python3 scripts/migrate.py --db-url "$LOCAL_DATABASE_URL" --dry-run
   ```

5. **Add or extend tests** if application code depends on the new tables/columns.

6. **PR checklist**

   - [ ] New `migrations/NNNN_*.sql` only additive
   - [ ] `schema.sql` updated in same PR
   - [ ] No prohibited keywords (see section 6)
   - [ ] `pytest tests/test_schema_migrations.py` passes
   - [ ] Relevant app/SOAR tests pass

7. **After merge** — staging/VM deploy uses section 4 (dry-run, then apply).

**Note:** Extracting legacy SIEM/SOAR DDL from `schema.sql` into `0002`–`0007` is a separate approved slice. Do not duplicate that work ad hoc in one giant migration without design review.

---

## 6. What NOT to do

| Do not | Why |
|--------|-----|
| Run `psql … -f schema.sql` (or `< schema.sql`) on a **live** database | `schema.sql` mixes reference DDL with `ALTER` / `DO $$` guards not meant for arbitrary replay; risk of constraint churn and drift. |
| Apply ad-hoc SQL on the VM without a numbered migration file | No version record; environments diverge silently. |
| Edit or delete a migration file after it has been applied anywhere | Checksums and audit trail break; other DBs cannot reproduce state. |
| Skip version numbers or reuse retired numbers | `migrate.py` fails gap detection or causes confusion. |
| Put destructive DDL in migrations (`DROP TABLE`, `DROP COLUMN`, `TRUNCATE`, `RENAME`, bulk `DELETE`) | Violates forward-only policy; risks production data loss. |
| Use `CREATE INDEX CONCURRENTLY` in migration files | Non-transactional; breaks per-migration atomicity. |
| Run migrations against production from a developer laptop without approval | Use approved deploy process and credentials. |
| Change `schema.sql` without a paired migration (or vice versa) | Reference snapshot and applied history diverge. |
| Touch ingest/detection/correlation transaction code for schema-only work | Unrelated risk; see SPEC-INGEST-001. |

---

## 7. Rollback / forward-fix policy

**There are no down-migrations and no destructive rollback.**

If a migration is wrong **after** it has been applied:

1. Do **not** modify the applied migration file.
2. Do **not** `DROP` tables/columns to “undo” on production.
3. Add a **new** higher-numbered migration that fixes the schema additively (add missing column, add index, replace constraint inside a guarded `DO $$ … EXCEPTION WHEN duplicate_object …` block).
4. Apply via `scripts/migrate.py` using the normal VM workflow.

If a migration **failed** mid-apply:

- PostgreSQL rolls back that file’s transaction; the DB stays at the previous `schema_migrations.version`.
- Fix the SQL in a **new** file (or fix the unreleased file before any DB applied it), then re-run the apply script.

If a migration was merged but **never** applied to any database:

- It may be removed from git and the version documented in `migrations/RETIRED.md`.

---

## 8. Verification commands

Run after every apply (local, staging, or VM). Replace placeholders with your environment values.

### Migration history

```bash
psql "$DATABASE_URL" -c "SELECT version, name, applied_at, applied_by FROM schema_migrations ORDER BY version;"
```

### Tables present

```bash
psql "$DATABASE_URL" -c "\dt"
```

### Idempotency (nothing pending)

```bash
python3 scripts/migrate.py --db-url "$DATABASE_URL" --dry-run
```

Expected when caught up: `Nothing to apply. DB at version NNNN.`

### Backend compile (from repo root)

```bash
python3 -m py_compile core/*.py engines/*.py integrations/*.py routes/*.py scripts/migrate.py
```

### Schema migration unit tests

```bash
python3 -m pytest tests/test_schema_migrations.py -v
```

### Ingest / detection / correlation regression (must stay green)

```bash
python3 -m pytest \
  tests/test_failed_login_detection.py \
  tests/test_password_spraying_detection.py \
  tests/test_correlated_activity.py \
  tests/test_targeted_correlation.py \
  tests/test_ingest_api_contracts.py \
  tests/test_alert_mutation_api_contracts.py -v
```

### SOAR-related smoke (when SOAR tables are in scope)

```bash
python3 -m pytest \
  tests/test_soar_worker.py \
  tests/test_playbook_routes.py \
  tests/test_incident_routes.py \
  tests/test_approval_routes.py \
  tests/test_notification_delivery_routes.py -v
```

### Application health (VM, after deploy)

```bash
curl -s "http://HOST:PORT/health"
```

---

## 9. Relation between `migrations/` and `schema.sql`

| Artifact | Role |
|----------|------|
| `migrations/NNNN_*.sql` | **Apply target** — only these files are executed by `scripts/migrate.py` on any environment. |
| `schema.sql` | **Reference snapshot** — full schema at repo HEAD for review, docs, and future CI diff. **Not** executed on live DBs. |
| `schema_migrations` (table) | **Per-database ledger** — which migration versions ran successfully. |

**Sync rule:** When you add `migrations/0008_foo.sql`, update `schema.sql` in the same change so a reader sees the same end state.

**Planned (not yet implemented):** CI that applies all migrations to a blank database and diffs against `schema.sql`; grep lint for prohibited keywords in `migrations/*.sql`. See `openspec/changes/add-schema-migration-versioning/tasks.md`.

**Historical note:** VMs that were synchronized before this framework may have SOAR tables without corresponding rows in `schema_migrations`. The first apply on such a DB should be planned with a dry-run; additive `IF NOT EXISTS` migrations backfill missing objects without dropping data. Do not “catch up” by replaying `schema.sql`.

---

## 10. Example commands (placeholders only)

```bash
# --- Environment (replace placeholders) ---
export DATABASE_URL='postgresql://USER:PASSWORD@HOST:5432/DBNAME'
export REPO_ROOT='/path/to/siem-security-dashboard-public'
cd "$REPO_ROOT"

# --- Dry-run before VM or staging apply ---
python3 scripts/migrate.py --db-url "$DATABASE_URL" --dry-run

# --- Apply all pending migrations ---
python3 scripts/migrate.py --db-url "$DATABASE_URL"

# --- Apply only through version 3 ---
python3 scripts/migrate.py --db-url "$DATABASE_URL" --target 3

# --- Explicit DSN flag (same as DATABASE_URL) ---
python3 scripts/migrate.py --db-url 'postgresql://USER:PASSWORD@HOST:5432/DBNAME'

# --- Inspect ledger ---
psql "$DATABASE_URL" -c "SELECT version, name, applied_at FROM schema_migrations ORDER BY version;"

# --- Confirm no pending work ---
python3 scripts/migrate.py --db-url "$DATABASE_URL" --dry-run

# --- WRONG: do not use on live DB ---
# psql "$DATABASE_URL" -f schema.sql
```

---

## Traceability

- **Spec ID:** SPEC-SCHEMA-001  
- **OpenSpec change:** `openspec/changes/add-schema-migration-versioning/`  
- **Index:** `openspec/spec-index.md`  
- **Code:** `scripts/migrate.py`, `migrations/`, `tests/test_schema_migrations.py` (reference snapshot: `schema.sql`)

When changing migration behavior, update this doc and the OpenSpec change together.
