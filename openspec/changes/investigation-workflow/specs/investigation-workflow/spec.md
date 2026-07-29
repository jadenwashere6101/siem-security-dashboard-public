## ADDED Requirements

### Requirement: Investigation Drawer provides focused investigation context
The system SHALL provide a responsive Investigation Drawer or panel for investigating a selected alert, incident, source IP, recon activity, or investigation without replacing the current workspace route.

#### Scenario: Analyst opens drawer from selected alert
- **WHEN** an analyst opens an investigation for a selected alert
- **THEN** the drawer presents available alert summary, incident summary, timeline, enrichment summary, related entities, related detections, SOAR response history, recommended next steps, and evidence links
- **AND** the current workspace context and navigation history remain intact

#### Scenario: Drawer handles partial evidence
- **WHEN** timeline, enrichment, incident, or SOAR response data is unavailable, loading, or unauthorized
- **THEN** the drawer renders an explicit loading, unavailable, partial, or access-denied state for that section
- **AND** it does not fabricate missing investigation evidence

#### Scenario: Drawer is responsive and accessible
- **WHEN** the drawer is opened on desktop, tablet, or mobile
- **THEN** it uses foundation responsive primitives for side-panel or full-width overlay presentation
- **AND** Escape/backdrop close, focus return, labels, keyboard navigation, and scroll containment are preserved

### Requirement: Threat Story explains investigations as a coherent narrative
The system SHALL provide a Threat Story view that converts existing authoritative investigation inputs into a narrative explanation of what happened and why it matters.

#### Scenario: Threat Story renders narrative sections
- **WHEN** an investigation has relevant alert, incident, timeline, entity, detection, recon, enrichment, SOAR, or analyst-observation data
- **THEN** the Threat Story can render what happened, why it mattered, affected entities, attack progression, detections triggered, SOAR actions, analyst observations, and current investigation status
- **AND** each section identifies the evidence source or marks the section incomplete

#### Scenario: Attack progression uses supported correlation data
- **WHEN** existing timeline or correlation data supports ordered progression
- **THEN** the Threat Story displays the progression using existing event order and labels
- **AND** it does not invent unsupported stages such as recon, spray, success, approval, or resolution

#### Scenario: Threat Story preserves system state boundaries
- **WHEN** an analyst reads or updates analyst observations in the story
- **THEN** observations are stored as analyst-owned workspace/investigation state
- **AND** alert lifecycle, incident state, detection output, and SOAR execution state are not changed unless an existing protected workflow is explicitly invoked outside this requirement

### Requirement: Analyst Workspace is a private manual investigation notebook
The system SHALL provide an analyst-owned workspace for manually organizing investigation context, notes, hypotheses, tasks, evidence references, and pinned objects.

#### Scenario: Analyst manually pins an object
- **WHEN** an analyst pins an alert, incident, recon activity, source IP, investigation, or evidence reference to their workspace
- **THEN** the item appears only in that analyst's workspace by default
- **AND** the underlying alert, incident, recon item, source IP, or investigation record is not mutated by the pin

#### Scenario: Workspace is not automatically populated
- **WHEN** new alerts, incidents, recon activities, SOAR actions, approvals, or detections occur
- **THEN** they do not automatically appear in the Analyst Workspace
- **AND** the analyst must explicitly pin or create workspace content

#### Scenario: Analyst manages private notes and tasks
- **WHEN** an analyst creates notes, hypotheses, checklist tasks, or organization labels
- **THEN** the records are persisted with owner identity, timestamps, status where applicable, and links to their parent workspace or investigation
- **AND** removing those records affects only private workspace state

### Requirement: Investigation persistence enforces ownership and RBAC
The system SHALL persist investigation workflow state with explicit ownership, authorization checks, auditability, and reference integrity.

#### Scenario: Owner reads private workspace state
- **WHEN** an authenticated analyst requests their workspace, investigations, notes, hypotheses, tasks, pins, or evidence references
- **THEN** the API returns only records owned by that analyst unless a future sharing capability explicitly grants access
- **AND** referenced system objects are resolved only when existing RBAC allows the analyst to view them

#### Scenario: Non-owner access fails closed
- **WHEN** a user requests or mutates another analyst's private workspace record without explicit authorization
- **THEN** the API denies the request without revealing private content
- **AND** the denial is auditable according to existing project conventions for sensitive access

#### Scenario: Workspace mutation is audited without production side effects
- **WHEN** an analyst creates, updates, deletes, pins, unpins, or reorders workspace content
- **THEN** the operation records owner, action, target type, target identifier, and timestamp
- **AND** it does not trigger SOAR actions, approvals, blocking, notifications, detection changes, or incident state transitions

### Requirement: Investigation workflow reuses existing architecture and extension points
Implementation SHALL extend the prior foundation and Anakin architecture without redesigning shell, theme, command palette, Anakin command surface, AI providers, detection engine, or SOAR engine.

#### Scenario: Drawer, story, and workspace reuse existing primitives
- **WHEN** investigation workflow surfaces are implemented
- **THEN** they use foundation theme tokens, panels, cards, chips, status/severity primitives, responsive breakpoints, and accessibility patterns
- **AND** they do not introduce a separate visual system

#### Scenario: Anakin and palette integrations use registry extensions
- **WHEN** investigation workflow adds commands such as open investigation, pin to workspace, draft hypothesis, or summarize story
- **THEN** those commands use the existing command registry, sanitized context providers, and read-only/mutation safety model
- **AND** the existing Anakin surface and command palette are not redesigned

#### Scenario: Future collaboration remains reserved
- **WHEN** persistence models include fields for visibility, sharing, reporting, evidence uploads, or collaboration
- **THEN** those fields remain inactive or private-only in this phase
- **AND** shared workspaces, case management, evidence uploads, report export, and collaborative editing are not exposed until a future OpenSpec enables them
