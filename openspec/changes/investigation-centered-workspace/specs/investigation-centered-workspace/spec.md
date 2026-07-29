## ADDED Requirements

### Requirement: Analyst Workspace centers on an active investigation
Analyst Workspace SHALL make investigations the primary object and SHALL organize investigation records around a selected active investigation.

#### Scenario: Analyst opens workspace with saved investigations
- **WHEN** an analyst opens Analyst Workspace and has one or more saved investigations
- **THEN** the workspace presents saved investigations as the primary navigation/selection surface
- **AND** selecting an investigation opens a dominant active investigation detail view

#### Scenario: Analyst opens workspace without investigations
- **WHEN** an analyst opens Analyst Workspace with no saved investigations
- **THEN** the workspace provides a clear path to start from an alert, incident, or source context
- **AND** it does not present unrelated storage cards as the main workflow

#### Scenario: Legacy unassigned records exist
- **WHEN** notes, hypotheses, tasks, pins, or evidence references are not attached to an investigation
- **THEN** the workspace keeps them discoverable as unassigned private workspace content
- **AND** unassigned content is visually secondary to active investigation work

### Requirement: Investigation detail presents analyst reasoning
The active investigation detail SHALL show a structured investigation story that separates source facts from analyst-authored reasoning.

#### Scenario: Analyst views investigation story
- **WHEN** an analyst selects an active investigation
- **THEN** the detail view presents trigger context, what happened, key entities, current assessment, evidence summary, open questions, and conclusion/disposition areas
- **AND** analyst-authored assertions are distinguishable from derived alert, incident, source-IP, enrichment, or SOAR facts

#### Scenario: Source context is incomplete
- **WHEN** linked alert, incident, source-IP, timeline, enrichment, or SOAR context is missing, loading, or unauthorized
- **THEN** the investigation detail marks that context as unavailable, incomplete, or access-denied
- **AND** it does not invent missing evidence or conclusions

### Requirement: Investigation lifecycle is lightweight and visible
Investigations SHALL expose lightweight lifecycle fields for status, disposition, confidence, progress, and conclusion without becoming enterprise case-management records.

#### Scenario: Analyst updates investigation lifecycle
- **WHEN** an analyst updates investigation status, confidence, disposition, summary, or conclusion
- **THEN** the private investigation record is updated and the active investigation view reflects the change
- **AND** alert status, incident state, detection output, SOAR state, approvals, and response actions are not mutated

#### Scenario: Analyst closes investigation
- **WHEN** an analyst marks an investigation closed
- **THEN** the UI prompts for or clearly surfaces disposition and conclusion state
- **AND** unresolved tasks, low confidence, or missing disposition remain visible as caveats rather than blocking system state

### Requirement: Evidence includes analyst rationale and source navigation
Evidence references SHALL explain why the analyst saved them and SHALL provide navigation back to the authoritative source object when available.

#### Scenario: Analyst saves evidence to investigation
- **WHEN** an analyst saves an alert, incident, source-IP context, event, response artifact, or other supported object as evidence
- **THEN** the evidence is attached to the active investigation with analyst rationale, source type, source identifier, label, and timestamp
- **AND** the underlying source object is not mutated

#### Scenario: Analyst opens evidence source
- **WHEN** an analyst activates a saved evidence source link
- **THEN** the app navigates to or opens the authoritative alert, incident, source-IP, response registry, or supported source view
- **AND** existing RBAC and workspace history behavior are preserved

#### Scenario: Analyst deletes evidence reference
- **WHEN** an analyst deletes an evidence reference from an investigation
- **THEN** only the private evidence reference or relationship is removed
- **AND** underlying alerts, incidents, logs, detections, SOAR records, and source data remain unchanged

### Requirement: Hypotheses connect to supporting and refuting evidence
Hypotheses SHALL be investigation-scoped and SHALL support evidence relationships that communicate analyst reasoning.

#### Scenario: Analyst links evidence to hypothesis
- **WHEN** an analyst links evidence to a hypothesis
- **THEN** the relationship records whether the evidence supports, refutes, or provides context for the hypothesis
- **AND** the hypothesis view groups evidence by relationship type

#### Scenario: Analyst reviews hypothesis confidence
- **WHEN** a hypothesis has supporting, refuting, and contextual evidence
- **THEN** the workspace presents the evidence in a way that helps the analyst reassess confidence and status
- **AND** it does not automatically change confidence without explicit analyst action

#### Scenario: Analyst deletes hypothesis relationship
- **WHEN** an analyst removes an evidence relationship from a hypothesis
- **THEN** the relationship is removed from private investigation state
- **AND** neither the evidence reference nor the source object is deleted unless the analyst explicitly deletes that private evidence reference

### Requirement: Tasks belong to investigations and unresolved questions
Tasks SHALL be scoped to investigations and MAY reference a related hypothesis or evidence item to show why the task exists.

#### Scenario: Analyst creates investigation task
- **WHEN** an analyst creates a task from an active investigation
- **THEN** the task is associated with that investigation and appears in the investigation task list
- **AND** the task can optionally reference a hypothesis or evidence gap

#### Scenario: Analyst completes task
- **WHEN** an analyst completes or reopens an investigation task
- **THEN** the task status updates in private workspace state
- **AND** the investigation progress indicators reflect the updated task state

#### Scenario: Analyst deletes task
- **WHEN** an analyst deletes an investigation task
- **THEN** only the private task record is removed
- **AND** linked evidence, hypotheses, alerts, incidents, and system state remain unchanged

### Requirement: Investigation timeline shows source and analyst milestones
The active investigation SHALL provide a timeline that combines available source-object events with analyst workspace milestones.

#### Scenario: Timeline has source and analyst events
- **WHEN** an investigation has linked alert or incident events and analyst actions such as evidence saved, hypothesis updated, task completed, or conclusion recorded
- **THEN** the timeline presents the events in chronological order with clear source labels
- **AND** analyst milestones are distinguishable from authoritative system events

#### Scenario: Timeline data is partial
- **WHEN** only analyst milestones or only source-object events are available
- **THEN** the timeline renders the available events and marks the missing side as unavailable or not yet recorded

### Requirement: Active investigation bundle is authorization-safe
The system SHALL load active investigation data through ownership-aware and RBAC-aware contracts.

#### Scenario: Owner loads active investigation
- **WHEN** an authenticated analyst loads their active investigation
- **THEN** the API returns the investigation, linked private notes, evidence, hypotheses, tasks, conclusions, relationships, and permitted source-object metadata
- **AND** source-object metadata is omitted or marked unauthorized when existing RBAC does not allow access

#### Scenario: Non-owner requests private investigation
- **WHEN** a user requests or mutates an investigation or related private record they do not own
- **THEN** the API denies the operation without revealing private content
- **AND** the denial is auditable according to existing project conventions

#### Scenario: Workspace mutation is audited
- **WHEN** an analyst creates, updates, links, unlinks, deletes, or reorders private investigation content
- **THEN** the operation records owner, action, target type, target identifier, and timestamp
- **AND** the operation does not trigger SOAR, notification, approval, detection, or incident side effects

### Requirement: Workspace remains portfolio-realistic and not enterprise case management
The investigation-centered workspace SHALL provide a coherent individual analyst investigation workflow while keeping enterprise case-management features out of scope.

#### Scenario: Enterprise workflow request is encountered
- **WHEN** implementation encounters assignment, collaboration, SLA, approval, reporting-engine, case-owner, source-IP watchlist, or heavy automation behavior
- **THEN** the behavior is deferred unless a future OpenSpec explicitly enables it
- **AND** the current change remains focused on individual private investigation reasoning

#### Scenario: Existing SOAR and incident workflows remain separate
- **WHEN** an analyst works an investigation in Analyst Workspace
- **THEN** SOAR incidents, approvals, playbooks, queues, response registry entries, alert lifecycle, and detection outputs retain their existing authoritative workflows
- **AND** workspace records remain private analyst context rather than operational source of truth

### Requirement: Investigation-centered workspace is accessible and responsive
The workspace SHALL preserve the existing dark SOC theme, responsive shell behavior, keyboard accessibility, and visible action feedback.

#### Scenario: Analyst uses keyboard navigation
- **WHEN** an analyst navigates investigation selection, evidence, hypotheses, tasks, lifecycle controls, and source links with the keyboard
- **THEN** focus order is predictable, active context is announced by labels or headings, and mutation feedback uses accessible status or alert messaging

#### Scenario: Workspace renders on narrow viewport
- **WHEN** the workspace is rendered on tablet or mobile widths
- **THEN** investigation selection, active detail, evidence, hypotheses, tasks, and conclusion content remain readable without overlapping or horizontal overflow
- **AND** primary investigation context remains discoverable before secondary unassigned content

### Requirement: Implementation verification covers investigation workflow behavior
Implementation SHALL include focused verification for the investigation-centered workflow, persistence boundaries, accessibility, and regression risk.

#### Scenario: Verification runs before handoff
- **WHEN** implementation is ready for handoff
- **THEN** frontend tests cover active investigation selection, story sections, lifecycle updates, evidence rationale, hypothesis-evidence relationships, investigation-scoped tasks, timeline milestones, source navigation, and responsive/accessibility behavior
- **AND** backend tests cover ownership, RBAC, audit logging, relationship validation, private deletion, and no source-object mutation
- **AND** required builds, migration/schema checks if applicable, `git diff --check`, and `openspec validate investigation-centered-workspace --strict` pass
