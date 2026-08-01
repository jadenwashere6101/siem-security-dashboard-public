## ADDED Requirements

### Requirement: Consolidated Anakin controls
The frontend SHALL replace action-specific AI button clusters with surface-appropriate controls mapped to canonical workflows.

#### Scenario: Dashboard controls are limited
- **WHEN** AI is enabled on the Dashboard
- **THEN** the visible controls SHALL be `Ask Anakin`, `Quick Explain`, and `Deep Investigate`
- **AND** dashboard artifact controls SHALL NOT be shown unless explicitly supported.

#### Scenario: Detail surfaces use workflow shortcuts
- **WHEN** AI is enabled on Alert Details, Source IP, Incident, SOC Command Center recon, or Response Registry detail surfaces
- **THEN** the controls SHALL use only canonical workflow shortcuts and a single Generate Artifact menu where supported
- **AND** low-value duplicate summary, why-important, suggested-action, and wording-only variants SHALL NOT render.

### Requirement: Workflow endpoint routing
Consolidated AI interactions SHALL call `POST /ai/workflows`.

#### Scenario: Freeform Ask Anakin uses auto workflow
- **WHEN** a user submits freeform Anakin text
- **THEN** the frontend SHALL send `workflow=auto`
- **AND** SHALL render backend classification metadata without requiring the user to understand internal workflow names.

#### Scenario: Shortcut buttons use explicit workflow
- **WHEN** a user selects a workflow shortcut
- **THEN** the frontend SHALL send the selected canonical workflow explicitly
- **AND** SHALL include bounded entity/context and tool policy appropriate to the surface.

### Requirement: Artifact menu behavior
Generate Artifact SHALL be exposed as one menu per relevant surface.

#### Scenario: Artifact menu preserves approved artifacts
- **WHEN** Generate Artifact is available
- **THEN** the menu SHALL expose only backend-supported artifact types relevant to that surface
- **AND** SHALL preserve incident notes, investigation checklists, escalation summaries, playbook drafts, detection changes, and response recommendations where supported.

#### Scenario: Preview and confirm remain gated
- **WHEN** an artifact response includes a reviewable action candidate
- **THEN** preview and confirm SHALL remain separate gated controls
- **AND** Decision Support SHALL NOT render draft/apply controls.

### Requirement: Workflow visibility and progress
The Anakin response UI SHALL show compact workflow routing and truthful progress/failure state.

#### Scenario: Classification metadata is visible
- **WHEN** a workflow response includes classification and metadata
- **THEN** the UI SHALL show classified workflow and model/profile metadata compactly.

#### Scenario: Chooser state renders
- **WHEN** the backend returns `chooser_required`
- **THEN** the UI SHALL render a compact chooser for allowed workflows
- **AND** resubmission SHALL use the selected explicit workflow.

#### Scenario: Deep Investigate progress is truthful
- **WHEN** Deep Investigate runs or completes
- **THEN** the UI SHALL show only backend-provided lifecycle stages
- **AND** SHALL NOT present synchronous execution as a durable background job.

### Requirement: Role boundaries and inventory
The interface SHALL preserve existing role boundaries and acceptance inventory coverage.

#### Scenario: Repo Assistant is role-aware
- **WHEN** the user is not authorized for Repo Assistant
- **THEN** Repo Assistant SHALL NOT appear as an available AI command or destination.

#### Scenario: Acceptance inventory covers remaining controls
- **WHEN** frontend AI controls are discovered
- **THEN** every remaining control SHALL map to exactly one canonical workflow
- **AND** removed legacy action IDs SHALL fail focused tests if they return.
