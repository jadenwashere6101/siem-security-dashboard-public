## ADDED Requirements

### Requirement: Recon Activity list entries SHALL be distinguishable at a glance
The system SHALL render Recon Activity list entries as compact triage summaries rather than repeated generic titles.

#### Scenario: Distinct activities show distinct summaries
- **WHEN** two Recon Activities differ by target, service, source mix, investigation value, or recent timing
- **THEN** their list entries SHALL expose enough compact information for an analyst to know which one is worth opening first

#### Scenario: Compact cards stay high-signal
- **WHEN** a Recon Activity has many possible summary fields
- **THEN** the system SHALL prefer headline, target/service identity, representative scope, recent timing, status, and investigation-value summary over low-signal implementation metadata

### Requirement: Recon Activity review state SHALL be truthful
The system SHALL distinguish between unreviewed, materially updated, and unchanged Recon Activities without implying a false unread model.

#### Scenario: Activity has never been reviewed
- **WHEN** a Recon Activity has no persisted review marker under the implemented review-state model
- **THEN** the system SHALL indicate that it is new

#### Scenario: Activity changed after review
- **WHEN** a Recon Activity gains material new evidence after its last review marker
- **THEN** the system SHALL indicate that it was updated

#### Scenario: Refresh does not falsely reset review state
- **WHEN** the analyst refreshes the page or loads a later session
- **THEN** the review-state indicator SHALL remain consistent with the implemented persistence model

### Requirement: Recon Activity detail SHALL identify the investigation immediately
The system SHALL make Recon Activity detail answer target, source, service, timing, investigation meaning, and next pivots before lower-level metadata.

#### Scenario: Detail opens on a populated activity
- **WHEN** an analyst opens a Recon Activity with linked evidence
- **THEN** the detail pane SHALL show primary target, representative source, service or port summary, first seen, last seen, investigation value, and current assessment prominently

#### Scenario: Detail handles missing relationships safely
- **WHEN** a Recon Activity lacks a linked incident, representative source, or supported target pivot
- **THEN** the detail pane SHALL not render a misleading enabled pivot for that missing relationship

### Requirement: Recon Activity pivots SHALL remain intentionally small
The system SHALL expose only the highest-value investigation pivots from the Recon Activity detail pane.

#### Scenario: Analyst opens linked evidence
- **WHEN** linked alerts, a related incident, a representative source, or a primary target are available and supported by current navigation
- **THEN** the detail pane SHALL provide direct pivots to those destinations

#### Scenario: Unsupported pivot is absent
- **WHEN** the underlying identifier or supported destination does not exist
- **THEN** the system SHALL hide or disable the pivot in a way that does not imply it will work

### Requirement: Recon wording SHALL be understandable at a glance
Touched Recon Activity labels and reason text SHALL use plain English instead of implementation-heavy wording wherever a shorter clearer label is available.

#### Scenario: Ambiguous status wording is replaced
- **WHEN** a touched Recon Activity field uses wording such as implementation keys or vague statuses
- **THEN** the analyst-facing label SHALL be replaced with concise plain-English wording

#### Scenario: Bare negative status gets reasons
- **WHEN** a touched Recon Activity status would otherwise say only `Not Established`
- **THEN** the system SHALL pair that status with short reason text that explains why the assessment remains unconfirmed
