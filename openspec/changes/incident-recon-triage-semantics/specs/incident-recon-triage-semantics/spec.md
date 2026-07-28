## ADDED Requirements

### Requirement: Incident semantics SHALL separate detection severity from case triage
The system SHALL distinguish alert severity, incident severity presentation, incident priority, and actionability in API responses and analyst-facing incident views.

#### Scenario: High source alert does not imply high incident triage
- **WHEN** an incident is linked to one or more High alerts without urgent response evidence, critical compromise evidence, or progression evidence
- **THEN** the incident SHALL NOT be presented as a High incident solely because the maximum linked alert severity is High
- **AND** the incident SHALL expose either a recalculated incident severity or a clearly labeled maximum linked alert severity

#### Scenario: Incident priority remains urgency
- **WHEN** an incident is created or linked
- **THEN** priority SHALL represent response urgency as P1, P2, or P3
- **AND** priority SHALL be explainable independently from alert severity

#### Scenario: Historical records remain compatible
- **WHEN** existing incidents were created before this change
- **THEN** the system SHALL preserve their stored values unless an explicit migration or backfill policy is approved
- **AND** analyst-facing presentation SHALL identify legacy or maximum-linked-alert semantics where needed

### Requirement: Incident eligibility SHALL use actionability
The system SHALL create incidents from case-worthy evidence rather than direct High-or-Critical alert mapping alone.

#### Scenario: Single honeypot alert with no broader evidence
- **WHEN** one honeypot scanner, admin probe, or env probe alert exists without recurrence, credential activity, progression, campaign support, or prior incident context
- **THEN** no incident SHALL be created
- **AND** incident priority SHALL be absent
- **AND** incident severity presentation SHALL be absent
- **AND** recon classification SHALL be absent
- **AND** the activity SHALL remain visible as an alert but SHALL NOT appear as a primary incident or recon item

#### Scenario: Repeated honeypot credential activity
- **WHEN** honeypot credential activity crosses the approved credential-stuffing threshold or has corroborating recurrence
- **THEN** an incident SHALL be created or linked
- **AND** incident priority SHALL be P2 when prompt analyst review is required, or P3 when case-worthy but not urgent
- **AND** incident severity presentation SHALL reflect recalculated incident triage or clearly labeled maximum linked alert severity
- **AND** recon classification SHALL be absent unless separate recon criteria are met
- **AND** the incident SHALL appear in primary analyst incident views

#### Scenario: Incident linked to several low or medium alerts
- **WHEN** an incident is linked to several Low or Medium alerts that are case-worthy through correlation, recurrence, or progression
- **THEN** an incident MAY be created or linked
- **AND** incident priority SHALL be P3 unless urgency evidence raises it
- **AND** incident severity presentation SHALL NOT be High unless recalculated evidence justifies High
- **AND** recon classification SHALL be based on recon materiality if the alerts are recon-related
- **AND** the incident SHALL appear in primary analyst views when case-worthy

#### Scenario: Incident linked to one genuinely critical alert
- **WHEN** one Critical alert represents likely compromise or immediate response need
- **THEN** an incident SHALL be created or linked
- **AND** incident priority SHALL be P1
- **AND** incident severity presentation SHALL be Critical
- **AND** recon classification SHALL be absent unless separate recon criteria are met
- **AND** the incident SHALL appear in primary analyst incident views

### Requirement: Recon semantics SHALL use materiality stages
The system SHALL classify recon activity with explicit materiality stages: `recon_candidate`, `recon_cluster`, `possible_campaign`, and `campaign_recon`.

#### Scenario: One eligible pfSense recon alert
- **WHEN** exactly one aggregate-eligible pfSense recon alert exists without sustained duration, multiple sources, progression, incident linkage, or corroborating alert diversity
- **THEN** no incident SHALL be created
- **AND** incident priority SHALL be absent
- **AND** incident severity presentation SHALL be absent
- **AND** recon classification SHALL be `recon_candidate`
- **AND** the activity SHALL NOT appear in primary analyst recon views by default
- **AND** source-IP and linked-alert pivots SHALL remain available from alert detail or explicit search

#### Scenario: Several related alerts from one source
- **WHEN** several related recon alerts from one source share target or service evidence but lack multi-source breadth, progression, or incident linkage
- **THEN** no incident SHALL be created unless separate source-specific progression criteria are met
- **AND** incident priority SHALL be absent unless an incident is created from progression
- **AND** incident severity presentation SHALL be absent unless an incident is created
- **AND** recon classification SHALL be `recon_cluster`
- **AND** the activity MAY appear in primary recon views when linked alert count or duration meets materiality thresholds

#### Scenario: Multiple sources over time with service overlap
- **WHEN** multiple source IPs produce related pfSense recon alerts over time against the same protected range or overlapping service signature
- **THEN** a grouped incident SHALL NOT be created while coordination is not established and no progression evidence exists
- **AND** incident priority SHALL be absent unless grouped incident criteria are met
- **AND** incident severity presentation SHALL be absent unless grouped incident criteria are met
- **AND** recon classification SHALL be `possible_campaign` or `campaign_recon` based on source count, linked alert count, duration, progression, and confidence
- **AND** `possible_campaign` and `campaign_recon` SHALL appear in primary analyst recon views

### Requirement: Primary analyst views SHALL avoid singleton recon noise
The system SHALL prevent weak singleton recon evidence from flooding primary analyst views while preserving investigation evidence.

#### Scenario: Recon candidate is retained but demoted
- **WHEN** a recon item is classified as `recon_candidate`
- **THEN** the system SHALL either persist it with a suppressed or candidate stage, or stage it outside `recon_activities` until promotion
- **AND** it SHALL NOT be titled or presented as meaningful "Source-specific recon" in primary views

#### Scenario: Recon promotion preserves continuity
- **WHEN** a `recon_candidate` later meets `recon_cluster`, `possible_campaign`, or `campaign_recon` thresholds
- **THEN** the system SHALL preserve linked alert evidence and promote or create the analyst-visible recon object idempotently

### Requirement: Semantic thresholds SHALL be explicit and testable
The system SHALL define materiality thresholds using linked alert count, source count, duration, severity, progression, incident linkage, and confidence.

#### Scenario: Threshold explanation is exposed
- **WHEN** an analyst opens incident or recon detail
- **THEN** the API and UI SHALL expose concise reasons explaining priority, severity presentation, recon stage, and primary-view visibility
