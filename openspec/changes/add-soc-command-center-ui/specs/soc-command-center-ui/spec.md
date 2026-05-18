## ADDED Requirements

### Requirement: Command Center Summary
The system SHALL provide a SOC Command Center landing view that summarizes operational security posture using existing SIEM and SOAR data.

#### Scenario: Summary cards render from existing data
- **WHEN** an authorized analyst or super admin opens the SOC Command Center
- **THEN** the view shows compact summary cards for incident pressure, active automations, pending approvals, dead-letter pressure, notification health, worker health, and integration safety status

#### Scenario: Simulation and real-mode safety are visible
- **WHEN** integration status data is available
- **THEN** the view clearly labels adapters and overall integration posture as simulation, real-enabled, blocked, or unavailable without exposing credentials or endpoint values

### Requirement: Global Activity Feed
The system SHALL provide a global activity feed that aggregates recent operational events from existing read-only APIs where available.

#### Scenario: Feed combines multiple event types
- **WHEN** incidents, playbook executions, approvals, dead letters, notification deliveries, worker metrics, or queue data are available
- **THEN** the feed presents a timeline-style list with type, status, timestamp, severity or priority where available, and safe links into existing detail views

#### Scenario: Missing API data degrades safely
- **WHEN** one or more source APIs are unavailable, forbidden, or return an unexpected shape
- **THEN** the feed still renders available sources and shows a non-blocking unavailable state for missing sources

### Requirement: Incident Workspace
The system SHALL provide an incident-focused workspace inside the Command Center using existing incident and linked-context data.

#### Scenario: Selecting an incident shows context
- **WHEN** a user selects an incident from the Command Center
- **THEN** the workspace shows incident summary, severity/status, linked alerts where available, incident timeline where available, and related playbook, approval, dead-letter, and notification context where existing APIs can provide it

#### Scenario: Mutations remain limited to existing safe controls
- **WHEN** the selected incident workspace is rendered
- **THEN** it MUST NOT introduce new mutation behavior beyond existing safe APIs and MUST hide analyst-only controls from viewer/auditor roles

### Requirement: Attention Panel
The system SHALL provide a “What needs attention?” panel that prioritizes operational work from existing data.

#### Scenario: Attention items prioritize actionable states
- **WHEN** stale or running executions, retrying/open dead letters, pending approvals, failed playbooks, notification failures, or queue pressure exist
- **THEN** the panel lists those states with concise counts, severity, and safe navigation affordances

#### Scenario: Empty state is useful
- **WHEN** no attention items are present
- **THEN** the panel shows a quiet healthy state rather than an error or blank panel

### Requirement: Role-Aware Command Center
The system SHALL enforce existing frontend role visibility rules in the SOC Command Center.

#### Scenario: Analyst and super admin can see operational controls
- **WHEN** an analyst or super admin opens the Command Center
- **THEN** the view may show existing safe operational links and controls that those roles can already access elsewhere

#### Scenario: Viewer/auditor controls are restricted
- **WHEN** a viewer/auditor opens or navigates to the Command Center
- **THEN** the view MUST NOT expose analyst-only mutation controls and MUST either show read-only posture or follow the existing access pattern for restricted SOAR sections

### Requirement: Polished Frontend Experience
The system SHALL present the Command Center as a polished operational security console consistent with the existing dashboard architecture.

#### Scenario: Responsive operational layout
- **WHEN** the Command Center is viewed on narrow or desktop widths
- **THEN** the layout remains readable with compact cards, status badges, timeline feed, loading states, error states, and empty states without overlapping text

#### Scenario: Existing tabs remain intact
- **WHEN** the Command Center is added to navigation
- **THEN** existing SOAR Operations, SOAR Metrics, Integrations, Approvals, Playbooks, Incidents, and Dashboard tabs remain available and behavior-compatible
