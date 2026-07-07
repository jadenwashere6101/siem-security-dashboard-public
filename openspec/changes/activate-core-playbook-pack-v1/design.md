## Executive Summary

Core Playbook Pack v1 is already implemented as five data definitions in `core/core_playbook_pack_v1.py`, and `seed_core_playbook_pack_v1(conn)` already inserts missing definitions idempotently. The smallest safe activation is to add a manual script that connects to a target database, calls the existing seed helper, commits on success, rolls back on error, and prints a clear summary.

The activation model MUST remain explicit. It MUST NOT run during Flask startup, migrations, deployment, or worker startup.

## Current State

`core/core_playbook_pack_v1.py` defines exactly five playbooks in `CORE_PLAYBOOK_PACK_V1`: Brute Force Containment, Password Spray Investigation, Successful Login After Spray Response, Malicious IP Containment, and Reputation-Only Investigation. The same module exposes `validate_core_playbook_pack_v1()` and `seed_core_playbook_pack_v1(conn, enabled=True)`.

`seed_core_playbook_pack_v1(conn)` is dormant. It has no caller in `siem_backend.py`, routes, workers, migrations, or scripts. Existing tests validate the pack data, trigger matching, execution behavior, and seed idempotency, but they exercise the helper directly.

`core/playbook_store.py` provides `create_playbook_definition()` and `get_playbook_definition()`. The seed helper uses those store APIs and skips rows whose IDs already exist, so repeated activation does not duplicate rows.

Existing script conventions favor explicit operator commands. `scripts/migrate.py`, `scripts/soar_outcome_backfill.py`, and playbook worker scripts use `DATABASE_URL` or `--db-url`, explicit command execution, transaction control, and concise terminal output.

Migrations define the `playbook_definitions` table but do not seed playbook content. Flask startup in `siem_backend.py` registers blueprints and configures the app; it does not mutate playbook data.

## Activation Options Considered

1. Manual seed script: preferred. It is explicit, testable, repeat-safe, easy to run in any target environment, and avoids application startup side effects.

2. Backend CLI command: acceptable but heavier. The project currently does not expose a Flask CLI command surface, so adding one would introduce a new operational pattern for a one-time seed action.

3. Auto-seed on app startup: rejected. Startup data mutation is surprising, can hide failed seeding inside web boot, and could alter a production database merely by starting the app.

4. Seed through migration: rejected. The migration system is for schema, not mutable operational content. Seeding enabled playbooks in a migration would make content activation implicit and harder to roll back without deleting operator-managed rows.

5. Document a Python one-liner only: rejected as insufficient. It keeps activation unsupported and error-prone, and does not provide a reusable validation or output contract.

## Recommended Activation Model

Add a manual script, tentatively `scripts/seed_core_playbook_pack_v1.py`.

The script should:

- Accept `--db-url`, defaulting to `DATABASE_URL`.
- Accept `--disabled` or equivalent only if needed to seed definitions disabled; the default should match the existing helper's `enabled=True`.
- Connect to PostgreSQL.
- Call `validate_core_playbook_pack_v1()` before writing and fail without mutation if validation returns errors.
- Call `seed_core_playbook_pack_v1(conn, enabled=...)`.
- Commit only after successful validation and seed completion.
- Roll back and exit non-zero on errors.
- Print the inserted playbook IDs and a clear no-op message when all five already exist.

This should be an operator-run activation command, not an automatic bootstrap step.

## Safety / Idempotency

The implementation should reuse the existing helper's ID-based skip behavior. Existing definitions with the same IDs MUST NOT be overwritten, deleted, disabled, enabled, or edited.

Repeated runs MUST be safe. The first run inserts missing definitions; later runs return an empty inserted list and leave existing rows unchanged.

Activation should be transaction-bound. If validation or any insert fails, the script should roll back and report failure.

## Implementation Scope

- Add one manual seed script under `scripts/`.
- Add focused tests for CLI argument handling, validation failure behavior, idempotent repeated execution, commit/rollback behavior, and output shape.
- Reuse `core.core_playbook_pack_v1.seed_core_playbook_pack_v1`.
- Reuse existing database connection conventions.
- Do not change playbook contents, playbook matching, execution, registry behavior, routes, frontend, migrations, or startup.

## Non-goals

- New playbooks.
- Playbook edits or redesign.
- Engine changes.
- Schema changes or migrations.
- UI changes.
- Automatic startup seeding.
- Deployment changes.
- Azure VM database changes during spec creation.
- Removing, updating, or reconciling operator-modified existing playbook rows.

## Acceptance Criteria

- A documented manual command exists for seeding Core Playbook Pack v1 into a target database.
- The command inserts the five existing pack playbooks when none exist.
- The command is idempotent and produces no duplicate rows on repeated runs.
- Existing playbook definitions with matching IDs are left unchanged.
- The command fails before writing if pack validation fails.
- The command commits on success, rolls back on failure, and exits non-zero on failure.
- No application startup, migration, deployment, UI, route, or engine path invokes the seed automatically.

## Validation Plan

- Unit-test the script with mocked database connections for missing `DATABASE_URL`, successful insert summary, no-op summary, validation failure, commit, rollback, and close behavior.
- Run existing `tests/test_core_playbook_pack_v1.py`.
- Run relevant script tests.
- Run `openspec validate activate-core-playbook-pack-v1 --strict`.
- Confirm no application source outside the approved future script/tests changes during implementation.

## Risks

- [Risk] Operators might run the script against the wrong database. Mitigation: require an explicit `DATABASE_URL` or `--db-url` and print the target DSN only in a sanitized form if displayed.
- [Risk] Existing rows with the same IDs may contain older or locally edited content. Mitigation: leave them unchanged and report them as already present; this activation is seed-only, not reconciliation.
- [Risk] Enabled-by-default activation could start matching alerts immediately after seeding. Mitigation: keep activation manual and allow a disabled seed mode if implementation chooses to expose it.

## Overall Assessment

Manual, explicit, idempotent script activation is the smallest safe path. It turns an existing dormant helper into an operator-supported workflow without changing schema, startup behavior, playbook content, or engine semantics.
