## ADDED Requirements

### Requirement: Branch Step Shape and Forward-Only Jump
The playbook step executor SHALL support a `branch` step action that evaluates a single structured `condition` and directs execution to a named `label`, using only forward jumps within the same playbook definition.

#### Scenario: Branch step jumps forward on a true condition
- **WHEN** a `branch` step's `condition` evaluates true and `goto_true` names a label on a later step
- **THEN** the executor SHALL resume execution at that later step's index, recording explicit `"skipped"` entries in `steps_log` for every step strictly between the branch step and the target.

#### Scenario: Branch step falls through on a false condition with no goto_false
- **WHEN** a `branch` step's `condition` evaluates false and `goto_false` is not set
- **THEN** the executor SHALL proceed to the immediately following step exactly as it would for any other successful step, with no steps skipped.

#### Scenario: Branch step jumps forward on a false condition with goto_false set
- **WHEN** a `branch` step's `condition` evaluates false and `goto_false` names a label on a later step
- **THEN** the executor SHALL resume execution at that later step's index, recording explicit `"skipped"` entries for every step strictly between the branch step and the target.

#### Scenario: Backward or self-referential jumps are impossible
- **WHEN** a playbook definition contains a `branch` step whose `goto_true` or `goto_false` resolves to a step at or before the branch step's own index
- **THEN** the definition SHALL be rejected at save time and SHALL NOT be persisted.

### Requirement: Condition Sources Reuse Existing Field Surfaces
Branch conditions SHALL be structured objects of the form `{"source", "field", "op", "value"}` and SHALL only reference data already exposed by existing engine capabilities: the alert-field binding allow-list, the most recently recorded step outcome, or the latest approval decision.

#### Scenario: Alert-sourced condition reuses the binding allow-list
- **WHEN** a `branch` step's condition has `source: "alert"`
- **THEN** `field` SHALL be validated against the same `ALERT_BINDING_FIELDS` allow-list used by dynamic playbook parameter binding, and SHALL be rejected at save time if the field is not a member of that allow-list.

#### Scenario: Severity comparisons reuse the existing ordinal ranking
- **WHEN** a `branch` step's condition has `source: "alert"`, `field: "severity"`, and an ordinal operator (`>=`, `>`, `<=`, `<`)
- **THEN** the comparison SHALL be evaluated using the existing `SEVERITY_RANK` ordering already used for trigger matching, not a new or separate ranking.

#### Scenario: Previous-step condition reflects the most recently recorded outcome
- **WHEN** a `branch` step's condition has `source: "previous_step"`, `field: "status"`
- **THEN** it SHALL evaluate against the most recently recorded step outcome in `steps_log` at the time the branch step runs, including when an earlier branch step skipped over the positionally-preceding step.

#### Scenario: Approval condition reflects the latest recorded gate decision
- **WHEN** a `branch` step's condition has `source: "approval"`, `field: "status"`
- **THEN** it SHALL evaluate against the most recently recorded `require_approval` gate decision (`approved`, `denied`, or `expired`) in `steps_log`.

### Requirement: Definition-Time Branch Validation
The playbook registry SHALL validate every `branch` step's shape, condition, and jump targets at definition save time, in addition to existing action and param-binding validation.

#### Scenario: Missing required branch fields are rejected
- **WHEN** a `branch` step is saved without a `condition` object or without `goto_true`
- **THEN** the definition SHALL be rejected with a clear validation error.

#### Scenario: Unknown condition source or field is rejected
- **WHEN** a condition's `source` is not one of `alert`, `previous_step`, `approval`, or an `alert`-sourced condition's `field` is not in the allowed field surface
- **THEN** the definition SHALL be rejected at save time.

#### Scenario: Operator mismatched to field type is rejected
- **WHEN** a condition uses an ordinal operator (`>=`, `>`, `<=`, `<`) against a string/enum alert field that is not `severity`
- **THEN** the definition SHALL be rejected at save time.

#### Scenario: Duplicate labels are rejected
- **WHEN** a playbook definition contains two or more steps with the same `label` value
- **THEN** the definition SHALL be rejected at save time.

#### Scenario: Unresolvable jump target is rejected
- **WHEN** a `branch` step's `goto_true` or `goto_false` does not match exactly one `label` present in the playbook's steps
- **THEN** the definition SHALL be rejected at save time.

### Requirement: Fail-Closed Branch Evaluation
When a branch condition cannot be resolved at execution time, the branch step SHALL fail rather than defaulting to either outcome.

#### Scenario: Missing or null alert field fails the step
- **WHEN** an `alert`-sourced condition's referenced field resolves to `null`, or the execution has no alert context
- **THEN** the branch step SHALL fail with a defined error code and SHALL NOT proceed to either jump target.

#### Scenario: Missing previous-step or approval context fails the step
- **WHEN** a `previous_step`- or `approval`-sourced condition has no qualifying prior entry in `steps_log`
- **THEN** the branch step SHALL fail with a defined error code and SHALL NOT proceed to either jump target.

### Requirement: Branch Decisions and Skips Are Fully Audited
Every branch evaluation and every step it skips SHALL be recorded in `steps_log`, and branch evaluations SHALL flow through the existing non-adapter step outcome-event path unchanged.

#### Scenario: Branch evaluation entry records condition and outcome
- **WHEN** a `branch` step evaluates successfully
- **THEN** its `steps_log` entry SHALL include the full `condition`, the resolved boolean `result`, and the `goto_label`/`goto_step_index` of the path taken.

#### Scenario: Skipped steps are explicit, not omitted
- **WHEN** a taken branch skips over one or more steps
- **THEN** each skipped step SHALL have its own `steps_log` entry with `status: "skipped"` and `skip_reason: "branch_not_taken"`; no step index SHALL be absent from `steps_log`.

#### Scenario: Branch outcome events use the existing non-adapter path
- **WHEN** a `branch` step succeeds or fails
- **THEN** a `step_succeeded` or `step_failed` canonical outcome event SHALL be emitted via the same mechanism already used for other non-adapter, non-approval steps, with no new event type introduced.

### Requirement: Opt-In Approval-Denial Branching
The `require_approval` step's `on_denied`/`on_expired` behavior SHALL support an additional `"branch"` value, strictly opt-in, that allows execution to continue to the next step instead of finalizing the execution as failed.

#### Scenario: Default approval-denial behavior is unchanged
- **WHEN** a `require_approval` step does not set `on_denied`/`on_expired`, or sets it to `"fail"`, and the approval is denied or expires
- **THEN** the execution SHALL be finalized as failed exactly as it is today, with no behavior change.

#### Scenario: Opt-in branch value allows continuation after denial
- **WHEN** a `require_approval` step sets `on_denied`/`on_expired: "branch"` and the approval is denied or expires
- **THEN** the executor SHALL record the decision as it does today and continue to the next step instead of finalizing the execution as failed, allowing a subsequent `branch` step to react to `approval.status`.

### Requirement: Engine-Only Change Boundary
This change SHALL define engine capability requirements only. It SHALL NOT author playbook content, SHALL NOT modify application source code as part of this spec-writing step, and SHALL NOT create `playbook_definitions` rows.

#### Scenario: No functional files touched by spec authoring
- **WHEN** this change is reviewed via `git status`/`git diff` after being written
- **THEN** the only files added or modified SHALL be under `openspec/changes/conditional-branching-primitive/`, with zero changes under `engines/`, `core/`, `routes/`, `migrations/`, `frontend/`, or `tests/`.

#### Scenario: No playbook rows created
- **WHEN** this change's artifacts are created
- **THEN** no `playbook_definitions` row SHALL be created and no existing engine behavior SHALL be modified — implementation remains a separate, later pass.
