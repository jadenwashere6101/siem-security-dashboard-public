## ADDED Requirements

### Requirement: Recent Alerts investigation detail SHALL be grouped for analyst review
The system SHALL present expanded `Recent Alerts` investigation detail in grouped, evidence-first sections that reduce repetition without removing forensic content.

#### Scenario: Analyst expands an alert
- **WHEN** an analyst opens expanded detail for an alert in `Recent Alerts`
- **THEN** the UI SHALL group the content into clearly labeled investigation sections such as summary, target or network evidence, threat or campaign evidence, response context, and raw metadata rather than one uninterrupted stack of repeated labels

#### Scenario: Lower-signal evidence is collapsed
- **WHEN** the UI uses collapsible sections for lower-signal content
- **THEN** investigation-critical evidence including identifiers, timestamps, why-fired evidence, response history, and authoritative related-record pivots SHALL remain available without being removed

### Requirement: Investigation wording SHALL distinguish severity from analyst priority
The system SHALL describe alert severity and investigation priority as separate concepts so they do not read as contradictory analyst guidance.

#### Scenario: Low severity with high investigation value
- **WHEN** an alert has low raw severity but high investigation value because of progression, campaign evidence, or returning-attacker context
- **THEN** the UI SHALL preserve both values and SHALL explain that severity reflects the alert event while the investigation label reflects analyst follow-up priority

#### Scenario: Alert detail shows why it matters
- **WHEN** an alert detail or recon detail surface shows investigation guidance
- **THEN** the wording SHALL use short plain-English labels and reasons that explain why the item matters instead of relying on urgency phrases alone

### Requirement: Recon Activity SHALL support bounded, convincing analyst pivots
The system SHALL keep the existing bounded Recon Activity workspace but make it more usable for analyst investigation.

#### Scenario: Recon list exceeds the visible column
- **WHEN** the number or height of recon cards exceeds the visible list region
- **THEN** the list column SHALL remain scrollable without breaking the adjacent detail region

#### Scenario: Recon detail has a supported primary target
- **WHEN** Recon Activity detail includes an existing supported `primary_target` identifier
- **THEN** the UI SHALL offer `Open Primary Target` as an analyst pivot in addition to the existing supported pivots

#### Scenario: Recon detail explains why the activity matters
- **WHEN** an analyst opens a recon activity
- **THEN** the detail SHALL lead with the target, representative source, service, linked-alert scope, campaign or coordination evidence, and investigation reasons in a way that makes the case for review clearer than a generic severity label alone

### Requirement: Shared loading affordances SHALL truthfully communicate activity
Shared analyst-workflow loading indicators SHALL visibly animate or otherwise communicate active loading instead of appearing static.

#### Scenario: Initial workspace loading indicator is shown
- **WHEN** a workspace uses the shared initial loading spinner
- **THEN** the spinner SHALL animate consistently so the state reads as active loading rather than a broken or frozen icon
