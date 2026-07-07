# playbook-chaining-and-cross-path-orchestration Specification

## Purpose
TBD - created by archiving change playbook-chaining-and-cross-path-orchestration. Update Purpose after archive.
## Requirements
### Requirement: Explicit, Asynchronous Playbook Chaining
The playbook step executor SHALL support a `trigger_playbook` step that explicitly dispatches a second playbook execution asynchronously, and SHALL NOT support any implicit or automatic chaining as a side effect of any other step, trigger match, or branch decision.

#### Scenario: Successful dispatch creates a linked child execution
- **WHEN** a `trigger_playbook` step executes with a valid, existing target `playbook_id`
- **THEN** the executor SHALL create exactly one new `playbook_executions` row for that playbook, using the dispatching execution's own `alert_id`, with `parent_execution_id` set to the dispatching execution's id and `chain_depth` set to the dispatching execution's `chain_depth + 1`.

#### Scenario: Parent step succeeds on dispatch, independent of child outcome
- **WHEN** a `trigger_playbook` step successfully creates a child execution row
- **THEN** the dispatching step SHALL be recorded as successful at that moment, and SHALL NOT be blocked, retried, or altered based on anything the child execution does afterward.

#### Scenario: No chaining occurs without an explicit step
- **WHEN** any playbook execution runs to completion without an authored `trigger_playbook` step
- **THEN** no second playbook execution SHALL be created as a side effect of that execution.

### Requirement: Loop Prevention via Depth Cap and Ancestor Check
The playbook engine SHALL prevent chaining cycles and unbounded chain growth using a definition-time self-reference check plus a dispatch-time depth cap and bounded ancestor-cycle check, and SHALL NOT rely on a full cross-definition graph-reachability validation.

#### Scenario: Definition-time self-reference is rejected
- **WHEN** a playbook definition's `trigger_playbook` step names that same playbook's own `id` as its target
- **THEN** the definition SHALL be rejected at save time.

#### Scenario: Depth cap fails closed
- **WHEN** a `trigger_playbook` step executes and the dispatching execution's `chain_depth` is already at or beyond the defined maximum
- **THEN** the step SHALL fail with a defined error code and SHALL NOT create a child execution row.

#### Scenario: Indirect cycle is caught at dispatch time
- **WHEN** a `trigger_playbook` step's target `playbook_id` already appears among the dispatching execution's own ancestor chain (traced via `parent_execution_id`)
- **THEN** the step SHALL fail with a defined error code and SHALL NOT create a child execution row, even when the definition-time check alone would not have detected this cycle.

### Requirement: Parent/Child Execution Linkage Reuses Existing Correlation Infrastructure
Chained executions SHALL be linked to their parent using the existing canonical-outcome parent-correlation column and one new, narrowly-scoped `playbook_executions` column, rather than a new dedicated chain/workflow table.

#### Scenario: Canonical decision records the parent correlation
- **WHEN** a child execution's canonical decision is created
- **THEN** its `parent_soar_correlation_id` SHALL be set to the dispatching parent execution's `soar_correlation_id`.

#### Scenario: Chained executions surface in the parent's incident timeline without new query logic
- **WHEN** a chained child execution is created for the same alert as its parent
- **THEN** it SHALL appear in that alert's incident timeline via the existing alert-id-based fallback already used for executions with a null `incident_id`, with no modification to the timeline query required.

### Requirement: Approval Gates Remain Independently Scoped Across Chained Executions
A chained child execution's approval gates SHALL behave identically to a standalone execution's approval gates, and chaining SHALL NOT introduce any new cross-execution approval concept.

#### Scenario: Child's approval pause does not affect the parent
- **WHEN** a chained child execution reaches a `require_approval` step and pauses awaiting a decision
- **THEN** the parent execution that dispatched it SHALL remain in whatever terminal state its own `trigger_playbook` step already reached, unaffected by the child's pending approval.

### Requirement: Exactly One Authoritative Automation Path Acts Per Alert
The ingest-time orchestration flow SHALL ensure that when a playbook claims an alert, the response-action queue path SHALL NOT also enqueue an action for that same alert.

#### Scenario: Playbook match suppresses queue enqueue
- **WHEN** playbook matching for a given alert produces at least one created or already-existing (`duplicate`) pending execution
- **THEN** the subsequent queue-enqueue step for that same alert SHALL be skipped with an explicit `skip_reason` of `playbook_precedence`, and no `response_actions_queue` row SHALL be created for it.

#### Scenario: Queue path is unaffected when no playbook matches
- **WHEN** playbook matching for a given alert produces no match
- **THEN** the queue-enqueue step SHALL behave exactly as it does today for that alert, with no change in outcome.

### Requirement: Queue Retirement Is Criteria-Gated, Not Calendar-Gated
Full removal of the response-action queue path's ingest-time trigger SHALL NOT be authorized until the consolidation decision's parity and coverage criteria are satisfied, and this spec's own coverage-gap finding is explicitly resolved or explicitly accepted and recorded.

#### Scenario: Coverage map is recorded with its gap
- **WHEN** the queue-to-playbook coverage map is reviewed
- **THEN** it SHALL show, for each of the queue's three reputation-based response actions, either a matching playbook trigger or an explicit statement that no playbook is required, and SHALL name the one identified gap (the `block_ip`/reputation-80 band's missing severity gate) explicitly rather than silently.

#### Scenario: Freeze notice is present
- **WHEN** `engines/soar_enqueue_orchestrator.py` and `engines/soar_action_worker.py` are reviewed
- **THEN** both SHALL carry a freeze/deprecation notice referencing the `soar-automation-path-consolidation-decision`.

#### Scenario: Full trigger removal is not authorized by this spec
- **WHEN** this change's artifacts are reviewed
- **THEN** they SHALL NOT include removal of the `enqueue_committed_alerts` ingest-time call sites, and SHALL NOT include deletion of `response_actions_queue` data, schema, or the `soar_action_worker.py`/`soar_enqueue_orchestrator.py` modules — those remain gated, future, separately-authorized steps.

### Requirement: Engine-Only Change Boundary
This change SHALL define playbook chaining and cross-path orchestration requirements only. It SHALL NOT modify application source code as part of this spec-writing step, and SHALL NOT create or alter any playbook definition, execution, or queue row.

#### Scenario: No functional files touched by spec authoring
- **WHEN** this change is reviewed via `git status`/`git diff` after being written
- **THEN** the only files added or modified SHALL be under `openspec/changes/playbook-chaining-and-cross-path-orchestration/`, with zero changes under `engines/`, `core/`, `routes/`, `migrations/`, `frontend/`, or `tests/`.

#### Scenario: No execution, definition, or queue rows created or altered
- **WHEN** this change's artifacts are created
- **THEN** no `playbook_executions`, `playbook_definitions`, or `response_actions_queue` row SHALL be created or modified, and no existing engine or orchestrator behavior SHALL be changed — implementation remains a separate, later pass.

