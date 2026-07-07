## 1. Manual Activation Script

- [ ] 1.1 Add `scripts/seed_core_playbook_pack_v1.py` using existing script conventions and repository import setup.
- [ ] 1.2 Parse `--db-url` with fallback to `DATABASE_URL`; fail with a clear message when no database URL is provided.
- [ ] 1.3 Validate the pack with `validate_core_playbook_pack_v1()` before opening write behavior.
- [ ] 1.4 Connect to PostgreSQL, call `seed_core_playbook_pack_v1(conn, enabled=True)`, commit on success, roll back on failure, and close the connection.
- [ ] 1.5 Print inserted playbook IDs and a no-op summary when all five definitions already exist.

## 2. Safety Boundaries

- [ ] 2.1 Do not change any `CORE_PLAYBOOK_PACK_V1` playbook definitions.
- [ ] 2.2 Do not add startup, migration, deployment, route, UI, worker, scheduler, or engine callers for the seed helper.
- [ ] 2.3 Do not add schema changes or dependencies.

## 3. Tests and Validation

- [ ] 3.1 Add tests for missing database URL, validation failure, successful seed commit, idempotent no-op output, rollback on failure, and connection close behavior.
- [ ] 3.2 Run `tests/test_core_playbook_pack_v1.py` and the new script tests.
- [ ] 3.3 Run `openspec validate activate-core-playbook-pack-v1 --strict`.
- [ ] 3.4 Run `git diff --check`.
