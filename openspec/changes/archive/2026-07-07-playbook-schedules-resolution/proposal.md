## Why

The playbook audit (`audit-soar-playbook-library`) flagged `playbook_schedules` as a fully modeled schema and API surface with no execution consumer. Direct re-inspection for this spec confirms the gap is narrower but more one-sided than "incomplete": there is no reachable way to even *create* a schedule through the product today (the only route surface is two `GET` routes; `create_playbook_schedule` in `core/playbook_store.py` has no route and is called only from tests), and nothing anywhere — not the playbook engine, not the worker, not any script — reads `next_run_at` or `schedule_expression` to trigger a run. The frontend already discloses this honestly (`PlaybooksPanel.js` shows "Schedules are metadata-only. No scheduler or daemon exists, and these records do not execute playbooks."), which is good practice, but a permanently-disclosed non-functional panel still invites the exact question a SOC-architecture review should pre-empt: why does this exist if it does nothing and can't even be populated in production? This spec decides whether to finish the scheduler or retire the surface, before any further playbook modernization work touches this area.

## What Changes

- Inventory every schedule-related code path (schema, store, routes, frontend, tests) as it exists today.
- Decide, with alternatives considered, whether to (A) build a real scheduler consumer or (B) retire the unused surface.
- Define the implementation boundaries, acceptance criteria, and validation plan for whichever direction is chosen, to be executed in a later, separately-requested implementation pass under this same child spec.
- No code, schema, or UI changes are made by this spec-creation step. No scheduler is built, nothing is deleted, no migration runs, no frontend file is edited.

## Capabilities

### New Capabilities
- `playbook-schedules-resolution`: records the decision on the `playbook_schedules` surface (finish vs. retire) and the boundaries/acceptance criteria for whichever direction is chosen. No existing spec under `openspec/specs/` (`response-action-queue-worker-rollout`, `soar-worker-orchestration`) covers this domain.

### Modified Capabilities
(none)

## Impact

- **Affected code (future implementation phase, not this proposal step):** `routes/playbook_routes.py`, `core/playbook_store.py`, `frontend/src/components/PlaybooksPanel.js`, `frontend/src/services/playbookService.js`, `tests/test_playbook_routes.py`, `tests/test_playbook_store.py`; optionally `migrations/` if a follow-up migration to drop the table is ever pursued.
- **Affected artifacts (this step):** adds `openspec/changes/playbook-schedules-resolution/` as a new, unimplemented child change under the `soar-playbook-modernization-roadmap` parent.
- **Downstream effect:** removes ambiguity before `Core Playbook Pack v1` and any future scheduling-related work; the roadmap's parent tracker should mark this item's decision recorded once this spec validates.
- **Dependencies:** `audit-soar-playbook-library` (source of the finding). No dependency on `soar-automation-path-consolidation-decision` or `playbook-engine-correctness-hardening` — this item is independent, per the parent roadmap's dependency notes.
