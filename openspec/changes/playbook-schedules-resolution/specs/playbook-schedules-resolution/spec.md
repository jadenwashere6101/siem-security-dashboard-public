## ADDED Requirements

### Requirement: Schedule Surface Resolution Decision
The project SHALL resolve the `playbook_schedules` surface by retiring it rather than finishing a scheduler, on the grounds that the write path is unreachable in production today, no real playbook content exists yet to schedule, and no demonstrated need for time-based (as opposed to alert-triggered) automation exists among the audit's identified playbook scenarios.

#### Scenario: Decision is recorded with rationale
- **WHEN** the recorded decision is read
- **THEN** it SHALL state that the schedule surface is to be retired, not finished, and SHALL give the specific rationale (unreachable write path, no content to schedule, no demonstrated time-based-automation need, dead-surface interview-quality cost) rather than a preference-only statement.

#### Scenario: Decision does not foreclose future scheduling permanently
- **WHEN** the recorded decision's scope is read
- **THEN** it SHALL state explicitly that scheduled playbooks may be revisited later, designed fresh against real requirements once real playbook content exists, and that this decision is a "not now" call rather than a permanent rejection of the concept.

### Requirement: Retired Surface Definition
The project SHALL define exactly what "retired" means for each layer of the schedule surface, so a later implementation pass has an unambiguous target with no partial or symptom-only removal.

#### Scenario: Retirement covers every layer
- **WHEN** the retirement definition is read
- **THEN** it SHALL cover, at minimum: the two read-only API routes, the store-layer functions whose only callers are those routes and tests, the frontend Schedules tab and detail view, the frontend service fetch wrappers, and the corresponding test coverage — not the frontend UI alone.

#### Scenario: Schema table disposition is explicitly addressed, not silently assumed
- **WHEN** the retirement definition is read
- **THEN** it SHALL explicitly state whether dropping the underlying `playbook_schedules` table is in scope, out of scope, or an optional lower-priority follow-up — it SHALL NOT leave the table's fate unaddressed.

### Requirement: Decision-Only Change Boundary
This change SHALL NOT modify application source code, database schema, migrations, frontend files, or tests, SHALL NOT build a scheduler, and SHALL NOT delete anything. Retirement implementation is deferred to a separate, later, explicitly-requested implementation pass under this same child spec.

#### Scenario: No functional files touched
- **WHEN** this change is reviewed via `git status`/`git diff` after being written
- **THEN** the only files added or modified SHALL be under `openspec/changes/playbook-schedules-resolution/`, with zero changes under `routes/`, `core/`, `frontend/`, `migrations/`, or `tests/`.

#### Scenario: No retirement work performed as part of this change
- **WHEN** this change's artifacts are created
- **THEN** no route, store function, frontend file, test, or schema object SHALL be removed, deprecated, or modified as part of this change — those remain deferred tasks tracked in `tasks.md` for a future implementation pass.
