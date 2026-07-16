## ADDED Requirements

### Requirement: Incident creation SHALL reflect investigation actionability
The system SHALL create incidents based on investigation actionability rather than Severity alone.

#### Scenario: Commodity activity can stay outside incidents
- **WHEN** an alert or recon activity is visible but remains commodity background activity without stronger progression, campaign escalation, or high-priority destination impact
- **THEN** the system SHALL be able to keep it outside incident creation

#### Scenario: Actionable progression can create an incident
- **WHEN** source-specific progression, campaign escalation, or other materially actionable evidence is present
- **THEN** the system SHALL be able to create or link an incident and explain why the activity justified case ownership

### Requirement: Incident priority SHALL be smarter than direct Severity mapping
The system SHALL support smarter P1/P2/P3 priority assignment that remains explainable to analysts.

#### Scenario: Priority reasons are visible
- **WHEN** the system assigns or changes incident priority
- **THEN** it SHALL expose the main reasons such as progression, destination importance, campaign escalation, or response urgency in plain English

#### Scenario: P2 inflation is reduced
- **WHEN** many incidents would previously have been created as nearly identical P2 cases
- **THEN** the system SHALL be able to use merging, aggregate ownership, campaign ownership, or non-incident visibility to avoid that inflation

### Requirement: Incidents SHALL support smarter merging and ownership
The system SHALL distinguish source-owned, aggregate-owned, and campaign-owned investigation paths.

#### Scenario: Related activity merges into one case
- **WHEN** multiple alerts or activities describe the same actionable investigation story
- **THEN** the system SHALL be able to merge them into one incident rather than create parallel duplicate cases

#### Scenario: Aggregate or campaign ownership is possible
- **WHEN** a recon activity or campaign is the correct primary investigation object
- **THEN** the system SHALL be able to assign incident ownership to that aggregate or campaign rather than to every member source independently

### Requirement: Incidents SHALL support bounded automatic closure
The system SHALL support bounded auto-closure behavior for stale or non-progressing investigation objects where closure improves analyst workflow.

#### Scenario: Stale non-progressing case can close
- **WHEN** an incident or aggregate-owned investigation shows no meaningful progression, no active response path, and no new qualifying evidence over the defined window
- **THEN** the system SHALL be able to auto-close it with visible closure reasoning

#### Scenario: Closure does not erase evidence
- **WHEN** the system auto-closes an incident or related investigation object
- **THEN** all historical evidence and reasoning SHALL remain visible for later review

### Requirement: Recon Activities SHALL become first-class analyst workflow objects
Recon Activities SHALL be visible and navigable as normal investigation surfaces rather than secondary summary objects.

#### Scenario: Analysts can discover Recon Activities naturally
- **WHEN** an analyst views related alerts, incidents, source-IP context, or SOC operational surfaces
- **THEN** the system SHALL provide bounded discovery paths into relevant Recon Activities

#### Scenario: Recon Activities explain their operational meaning
- **WHEN** an analyst opens a Recon Activity
- **THEN** the activity SHALL summarize history, related destinations or services, campaign relationships, repeated targeting, and why it matters operationally

### Requirement: Recon and incident wording SHALL be understandable at a glance
Analyst-facing labels and status text affected by this capability SHALL be understandable at a glance and SHALL avoid requiring documentation for interpretation.

#### Scenario: Clear ownership wording
- **WHEN** the system indicates that an incident is source-owned, aggregate-owned, or campaign-owned
- **THEN** it SHALL use short plain-English wording that tells the analyst what owns the investigation and why

