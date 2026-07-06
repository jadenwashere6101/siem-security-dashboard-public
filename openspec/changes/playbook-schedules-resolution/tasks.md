This spec retires the unused `playbook_schedules` surface while preserving existing playbook runtime behavior. No scheduler is built, no migration runs, and the existing `playbook_schedules` table is left as intentionally inert legacy schema unless a future approved scheduler or cleanup spec changes that disposition.

## 1. Inventory and Verification (completed as part of writing this spec)

- [x] 1.1 Confirm the full `playbook_schedules` schema (`migrations/0006_soar_playbooks.sql`).
- [x] 1.2 Confirm the store-layer functions that exist for schedules (`core/playbook_store.py`) and that no update/pause/delete function exists.
- [x] 1.3 Confirm exactly which routes exist for schedules (`routes/playbook_routes.py`) and that no `POST`/`PATCH`/`DELETE` route exists — only the two `GET` routes.
- [x] 1.4 Confirm `create_playbook_schedule` has no caller anywhere in the codebase outside tests.
- [x] 1.5 Confirm no process anywhere (`engines/soar_playbook_worker.py`, `scripts/soar_playbook_worker_daemon.py`, `scripts/run_playbook_executor_once.py`) reads `next_run_at`/`schedule_expression` to trigger a run.
- [x] 1.6 Confirm the frontend already discloses non-functionality (`frontend/src/components/PlaybooksPanel.js` "metadata-only" labels).
- [x] 1.7 Confirm which tests reference schedule behavior (`tests/test_playbook_store.py`, `tests/test_playbook_routes.py`).
- [x] 1.8 Record the recommendation (retire), alternatives considered, and rejection rationale in `design.md`.

## 2. Retirement Implementation

- [x] 2.1 Remove `GET /playbook-schedules` and `GET /playbook-schedules/<id>` from `routes/playbook_routes.py`.
- [x] 2.2 Remove or clearly deprecate `create_playbook_schedule`, `get_playbook_schedule`, `list_playbook_schedules` in `core/playbook_store.py` once their only callers are removed/updated.
- [x] 2.3 Remove the "Schedules" tab and detail view from `frontend/src/components/PlaybooksPanel.js`.
- [x] 2.4 Remove the schedule fetch wrappers from `frontend/src/services/playbookService.js`.
- [x] 2.5 Update or remove the schedule-specific tests in `tests/test_playbook_routes.py` and `tests/test_playbook_store.py` so the suite reflects the retired surface.
- [x] 2.6 Run the full existing playbook test suite and confirm no unrelated regressions.
- [x] 2.7 Decide (optional, lower priority) whether to drop the `playbook_schedules` table via a separate forward-only migration, or leave it as intentionally inert schema.
- [x] 2.8 Update any documentation that references scheduled playbooks as a working or in-progress feature.

## Safety Boundaries (for this authoring step)

- [x] Creating this spec's proposal/design/tasks/spec files makes no changes under `routes/`, `core/`, `frontend/`, `migrations/`, or `tests/`.
- [x] Do not build a scheduler as part of this spec.
- [x] Do not delete anything as part of this spec.
- [x] Do not modify schema as part of this spec.
- [x] Do not modify UI as part of this spec.
- [x] No new playbooks, chaining, branching, ad hoc triggers, evidence collection, queue retirement, deployment, or UI-redesign work is introduced by this spec.
- [x] Do not commit.
