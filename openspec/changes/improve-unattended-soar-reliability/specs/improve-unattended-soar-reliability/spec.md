## ADDED Requirements

### Requirement: Expired or denied approvals reach a distinct terminal execution state
The system SHALL provide a playbook-execution terminal state distinct from `failed`, `abandoned`, and `success` for the case where a `require_approval` gate resolves to `denied` or `expired` and no `on_denied`/`on_expired: "branch"` fallback is configured for that step. This state SHALL indicate that no protected action was taken because approval did not occur in time or was refused, not that a system or integration error occurred.

#### Scenario: Expired approval with no fallback reaches the distinct terminal state
- **WHEN** a `require_approval` gate's linked approval request transitions to `expired` and the gate step has no `on_expired: "branch"` configuration
- **THEN** the playbook execution SHALL reach the distinct terminal state rather than `failed`

#### Scenario: Denied approval with no fallback reaches the distinct terminal state
- **WHEN** a `require_approval` gate's linked approval request transitions to `denied` and the gate step has no `on_denied: "branch"` configuration
- **THEN** the playbook execution SHALL reach the distinct terminal state rather than `failed`

#### Scenario: Genuine execution failures are unaffected
- **WHEN** a playbook step fails for a reason other than approval denial/expiration (adapter error, worker error, validation error, integration failure)
- **THEN** the playbook execution SHALL reach `failed` exactly as before this change, with no change to its dead-letter or retry behavior

### Requirement: Approval expiration and denial remain fail-closed
No protected action (including but not limited to `block_ip`) SHALL execute after an approval request expires or is denied, regardless of the terminal execution state introduced by this capability.

#### Scenario: No protected action runs after expiration
- **WHEN** an approval request expires
- **THEN** the playbook execution's remaining steps, including any protected action gated by that approval, SHALL NOT execute

#### Scenario: No protected action runs after denial
- **WHEN** an approval request is denied
- **THEN** the playbook execution's remaining steps, including any protected action gated by that approval, SHALL NOT execute

### Requirement: Expected-lifecycle approval terminals do not create dead letters
The system SHALL NOT create a dead-letter record when a playbook execution reaches the distinct terminal state described above. Dead letters SHALL remain reserved for genuine execution, adapter, worker, validation, and integration failures.

#### Scenario: No dead letter for expected expiration
- **WHEN** a playbook execution reaches the distinct terminal state due to approval expiration
- **THEN** no row SHALL be created in the dead-letter store for that transition

#### Scenario: No dead letter for expected denial
- **WHEN** a playbook execution reaches the distinct terminal state due to approval denial
- **THEN** no row SHALL be created in the dead-letter store for that transition

#### Scenario: Dead letters still capture genuine failures
- **WHEN** a playbook execution fails for a reason other than approval denial/expiration
- **THEN** a dead-letter record SHALL still be created with retryability classified exactly as before this change

### Requirement: No retry path exists for denied or expired protected actions
No worker or retry mechanism SHALL retry, re-queue, or re-attempt a protected action whose gating approval was denied or expired.

#### Scenario: Nothing exists to retry
- **WHEN** an approval expires or is denied and the execution reaches the distinct terminal state
- **THEN** there SHALL be no dead-letter row, queue entry, or scheduled retry referencing that protected action, and no operator action SHALL be able to cause it to execute later

### Requirement: Approval and execution lifecycle states remain distinctly labeled
The system SHALL distinguish, in stored state and in any operator-facing view, between: pending approval; approved; denied; expired; a completed (successful) execution; the expected terminal-expiration/denial execution state; a genuine execution failure; and a dead letter requiring attention. These SHALL NOT be merged or relabeled as one another.

#### Scenario: Each state is independently queryable
- **WHEN** an operator filters playbook executions or approvals by state
- **THEN** pending approvals, denied approvals, expired approvals, executions in the expected terminal-expiration state, genuinely failed executions, and actionable dead letters SHALL each be selectable as distinct sets

### Requirement: Historical backlog dead letters are preserved and reviewed non-destructively
Existing dead-letter rows created before this capability (including the approval-expired/denied backlog) SHALL NOT be deleted or silently mutated as part of implementing this capability. Any dismissal of backlog rows SHALL use the existing single-row dismissal mechanism, require a reason, and be individually audit-logged.

#### Scenario: Backlog identification is read-only
- **WHEN** an operator identifies the existing approval-expired/denied dead-letter backlog
- **THEN** the identification SHALL use read-only filtering and SHALL NOT modify any row

#### Scenario: Backlog dismissal is reason-logged and per-row
- **WHEN** an operator dismisses a backlog dead letter
- **THEN** the dismissal SHALL record a reason and an audit event for that specific row, using the same mechanism already used for any other dead-letter dismissal

#### Scenario: No bulk deletion
- **WHEN** the existing backlog is reviewed
- **THEN** no bulk deletion or mass silent status change SHALL occur; each affected row's disposition SHALL be individually recorded

### Requirement: The legacy response-action queue is visibly identified as frozen
The SOAR Queue view SHALL clearly indicate that the legacy response-action queue path receives no new alert types or actions, per the already-recorded automation-path-consolidation decision, so its low or idle activity is not mistaken for broken automation.

#### Scenario: Frozen-queue banner is present
- **WHEN** an operator views the SOAR Queue section
- **THEN** it SHALL display an explanation that this queue is historical/frozen for current alert automation and that active automation runs through the playbook engine

#### Scenario: Existing queue data remains visible
- **WHEN** the frozen-queue banner is added
- **THEN** existing queue items, history, and functionality SHALL remain visible and unchanged

### Requirement: SOAR Operations surfaces active execution and approval state as the primary signal
The SOAR Operations view SHALL present, as its primary content, the current counts of: running/awaiting-approval playbook executions, pending approvals, recently expired/denied approvals, genuine failed executions, and actionable dead letters — computed from already-existing list/metrics data, not a new analytics or trend surface.

#### Scenario: Operator sees operational state in one place
- **WHEN** an operator opens SOAR Operations
- **THEN** they SHALL see counts for running playbooks, pending approvals, recently expired/denied approvals, genuine failures, and actionable dead letters without navigating to separate sections

#### Scenario: Expected outcomes are visually distinct from genuine failures
- **WHEN** SOAR Operations displays recently expired/denied approvals alongside genuine failures
- **THEN** the two categories SHALL be visually and structurally distinguishable, not merged into one count or list

#### Scenario: No new analytics surface
- **WHEN** SOAR Operations is extended by this capability
- **THEN** it SHALL NOT include charts, historical trend visualizations, or any capability beyond the fixed counts/lists described above

### Requirement: This change preserves existing SOAR, detection, and notification architecture
This capability SHALL NOT change pfSense detection thresholds or severities, alert generation, Slack notification policy, the frozen response-action-queue architecture decision, or the approval fail-closed guarantee. It SHALL NOT enable real IP blocking or auto-approve any request.

#### Scenario: No detection or notification behavior changes
- **WHEN** this capability is implemented
- **THEN** no detection rule threshold, alert severity, or Slack notification routing SHALL change as a result

#### Scenario: No weakening of protected-action safety
- **WHEN** this capability is implemented
- **THEN** `require_approval` gating, protected-target checks, and fail-closed behavior for real-mode adapters SHALL remain exactly as strict as before this change
