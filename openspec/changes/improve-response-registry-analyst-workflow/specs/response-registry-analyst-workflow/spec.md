## ADDED Requirements

### Requirement: Canonical investigation handoff
The Response Registry SHALL expose one canonical `Investigate` action in indicator detail and SHALL route the analyst to the best authoritative next workspace target without requiring them to choose among raw relationship identifiers.

#### Scenario: Linked incident exists
- **WHEN** the selected registry record has a linked incident available to the current user
- **THEN** `Investigate` SHALL open the authoritative incident workspace for that incident

#### Scenario: No incident but originating alert exists
- **WHEN** the selected registry record has no linked incident and has an originating alert available to the current user
- **THEN** `Investigate` SHALL open the authoritative alert workspace for that alert

#### Scenario: No incident or alert but indicator context exists
- **WHEN** the selected registry record has no linked incident or originating alert and still has a valid source or indicator context
- **THEN** `Investigate` SHALL open the authoritative Source/IP Context workspace for that indicator

#### Scenario: No investigation target exists
- **WHEN** the selected registry record has no linked incident, no originating alert, and no valid Source/IP Context target
- **THEN** the workspace SHALL explain that no investigation target is available and SHALL NOT attempt blind navigation

### Requirement: Compact relationship summary
The Response Registry detail pane SHALL render a compact relationship summary instead of raw text ID lists and SHALL make each supported relationship type clickable when a valid destination exists.

#### Scenario: Multiple relationship types exist
- **WHEN** the selected registry record has related alerts, incidents, playbooks, approvals, or a combination of them
- **THEN** the detail pane SHALL render each relationship type as a compact labeled summary with its count and click target

#### Scenario: Relationship destination is unavailable
- **WHEN** a relationship count exists but the current user cannot open its destination or the destination cannot be resolved
- **THEN** the workspace SHALL render the relationship truthfully and SHALL explain why navigation is unavailable

### Requirement: Compact response summary
The Response Registry detail pane SHALL expose a compact Response Summary that answers alert, indicator, response, and outcome without duplicating full alert or incident detail panels.

#### Scenario: Analyst opens registry detail
- **WHEN** an analyst opens a registry record detail pane
- **THEN** the pane SHALL show a compact summary covering the linked alert reference when present, the canonical indicator, the current response state, and the latest outcome label

### Requirement: Deterministic recommended next step
The Response Registry detail pane SHALL expose one deterministic Recommended Next Step derived from current record state and linked relationships and SHALL NOT use AI-generated reasoning.

#### Scenario: Linked incident is active
- **WHEN** the selected registry record has a linked incident that remains open or otherwise actionable
- **THEN** the recommended next step SHALL direct the analyst to investigate the related incident

#### Scenario: Awaiting approval state exists
- **WHEN** the latest registry or linked response state is awaiting analyst approval
- **THEN** the recommended next step SHALL direct the analyst to review the relevant approval state

#### Scenario: Monitoring remains active
- **WHEN** the current registry disposition is monitored and no stronger investigation target takes priority
- **THEN** the recommended next step SHALL state that monitoring is active and whether further analyst action is required

#### Scenario: No further action is required
- **WHEN** the selected registry record is terminal, informational, or otherwise has no remaining analyst follow-up
- **THEN** the recommended next step SHALL explicitly state that no further analyst action is required

### Requirement: Consistent analyst-facing outcome badges
The Response Registry SHALL use a consistent analyst-facing outcome vocabulary for summary and history surfaces.

#### Scenario: Tracking-only outcome is rendered
- **WHEN** the canonical outcome represents tracking-only behavior with no external enforcement
- **THEN** the UI SHALL render a `Tracking Only` analyst-facing outcome badge

#### Scenario: Approval is pending
- **WHEN** the canonical outcome or linked response state indicates approval is still pending
- **THEN** the UI SHALL render an `Awaiting Approval` analyst-facing outcome badge

#### Scenario: Other canonical outcomes are rendered
- **WHEN** the canonical outcome indicates executed, monitoring, simulated, skipped, or failed behavior
- **THEN** the UI SHALL render the corresponding consistent analyst-facing badge without mixing that vocabulary with generic or contradictory copy

### Requirement: Registry command context reliability
Response Registry manual commands SHALL receive sufficient context to execute consistently regardless of whether the analyst opened the record from the registry, an alert, an incident, or another investigation workflow.

#### Scenario: Alert-origin registry action
- **WHEN** an analyst opens Response Registry from an alert-driven workflow and runs a registry command
- **THEN** the request SHALL preserve the available alert, incident, and indicator provenance needed for truthful execution and audit history

#### Scenario: Incident-origin registry action
- **WHEN** an analyst opens Response Registry from an incident-driven workflow and runs a registry command
- **THEN** the request SHALL preserve the available incident, alert, and indicator provenance needed for truthful execution and audit history

#### Scenario: Registry-native action
- **WHEN** an analyst opens a record directly from the Response Registry and runs a manual command
- **THEN** the request SHALL still carry the minimum authoritative context required for the backend to validate and execute the command reliably

### Requirement: Actionable analyst error feedback
The Response Registry SHALL replace generic command failures with actionable analyst-facing messages tied to known failure classes.

#### Scenario: Command cannot resolve a valid target
- **WHEN** a registry command cannot execute because no valid actionable target can be resolved
- **THEN** the workspace SHALL explain that the target context is incomplete or unavailable and SHALL NOT show only a generic failure

#### Scenario: Command is blocked by current state
- **WHEN** a registry command cannot execute because tracking is inactive, monitoring is already stopped, the target is protected, or another known state guard applies
- **THEN** the workspace SHALL explain the specific state guard in analyst-facing language

### Requirement: Scoped registry usability fixes
The Response Registry SHALL include the confirmed scoped usability fixes without expanding into a broader redesign.

#### Scenario: Detail load fails
- **WHEN** indicator detail fails to load
- **THEN** the detail pane SHALL expose a retry action in place

#### Scenario: List load fails after paging
- **WHEN** the registry list fails to load after the analyst has paged away from the first page
- **THEN** retrying the list SHALL preserve the current pagination context instead of resetting to page one

#### Scenario: Analyst enters mutation reasons
- **WHEN** the analyst enters a tracking reason and an incident-creation reason
- **THEN** the workspace SHALL preserve those as separate inputs and SHALL NOT silently share state between them

#### Scenario: Incident creation control is shown
- **WHEN** the control that creates or links an incident is rendered
- **THEN** its label SHALL use clear incident-oriented wording rather than a generic `Escalate` label

#### Scenario: Approval and playbook relationships exist
- **WHEN** the selected registry record has related approvals or playbook executions
- **THEN** the relationship summary SHALL provide navigation to those authoritative workspaces instead of rendering those relationships as text-only identifiers
