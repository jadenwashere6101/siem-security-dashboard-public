# soar-automation-path-consolidation-decision Specification

## Purpose
TBD - created by archiving change soar-automation-path-consolidation-decision. Update Purpose after archive.
## Requirements
### Requirement: Recorded Automation Path Decision
The project SHALL record exactly one decision on the relationship between the response-action queue path and the playbook engine path, including the current architecture of both, the risks of leaving them ambiguous, the alternatives considered, the criteria used to choose, and the exact decision reached. The decision SHALL designate the playbook engine as the single authoritative SOAR orchestration layer and SHALL freeze the response-action queue path against new alert types, new `response_action` values, and new actions.

#### Scenario: Decision names an authoritative path
- **WHEN** the recorded decision is read
- **THEN** it SHALL state that the playbook engine is the single authoritative orchestration layer going forward, and SHALL state that the response-action queue path is frozen (no new alert types, response actions, or actions added to it).

#### Scenario: Alternatives are documented with rejection rationale
- **WHEN** the recorded decision's alternatives section is read
- **THEN** it SHALL list at least the merge, permanently-separate, retire-playbook-engine, and retire-queue-path options, each with a stated reason it was or was not selected.

#### Scenario: No new overlap is introduced before retirement
- **WHEN** any future work considers adding a new alert type or action
- **THEN** it SHALL be implemented as a playbook (`playbook_definitions` + `trigger_config` + `steps`) and SHALL NOT be added as a new `response_action` mapping to the queue path, and no alert type SHALL simultaneously carry a queue-triggering `response_action` and a playbook `trigger_config` match for the same action class.

### Requirement: Queue Path Retirement Readiness Criteria
The project SHALL define explicit, checkable criteria that must all be satisfied before the response-action queue path's ingest-time trigger is removed. Retirement SHALL NOT proceed on a fixed calendar date; it SHALL proceed only once these criteria are met.

#### Scenario: Safety parity confirmed before retirement
- **WHEN** retirement of the queue path is considered
- **THEN** the playbook engine's `block_ip` step SHALL be confirmed to enforce the same protected-target check (`soar_protected_targets.require_unprotected_target`) the queue path enforces today.

#### Scenario: Coverage confirmed before retirement
- **WHEN** retirement of the queue path is considered
- **THEN** a coverage map SHALL exist showing that every alert type currently routed to the queue path via `response_action` has an equivalent playbook, or an explicitly accepted and documented gap.

#### Scenario: Freeze notice present before retirement
- **WHEN** retirement of the queue path is considered
- **THEN** `engines/soar_enqueue_orchestrator.py` and `engines/soar_action_worker.py` SHALL carry a freeze/deprecation notice referencing this decision.

### Requirement: Decision-Only Change Boundary
This change SHALL NOT modify application source code, database schema, migrations, or tests, SHALL NOT create new playbooks, engine features (branching, chaining, ad hoc triggers, enrichment steps), playbook schedules work, or evidence-collection work, and SHALL NOT perform any enforcement of the recorded decision. Enforcement is deferred to a separately-scoped future child spec.

#### Scenario: No functional files touched
- **WHEN** this change is reviewed via `git status`/`git diff` after being written
- **THEN** the only files added or modified SHALL be under `openspec/changes/soar-automation-path-consolidation-decision/`, with zero changes under `engines/`, `core/`, `routes/`, `migrations/`, `frontend/`, or `tests/`.

#### Scenario: No enforcement performed as part of this change
- **WHEN** this change's artifacts are created
- **THEN** no freeze notice, coverage map artifact, or code change enforcing the decision SHALL be produced as part of this change — those remain deferred tasks tracked in `tasks.md` for a future spec.

