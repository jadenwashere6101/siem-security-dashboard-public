## ADDED Requirements

### Requirement: Internet-noise assessment SHALL remain separate from severity and reputation
The system SHALL model internet-noise assessment as a distinct concept from detector-authored severity, stored external reputation, and current internal behavioral reputation.

#### Scenario: Alert payload preserves separate concepts
- **WHEN** an alert is enriched with internet-noise intelligence
- **THEN** the alert contract SHALL keep detector severity, external reputation, behavioral reputation, and internet-noise assessment as separate fields rather than collapsing them into one reputation or severity value

#### Scenario: Source-IP context preserves separate concepts
- **WHEN** source-IP context is returned for an analyst
- **THEN** the response SHALL expose internet-noise assessment separately from behavioral reputation and separately from historical external reputation snapshots

### Requirement: Internet-noise assessment SHALL be additive and non-suppressive
The system SHALL use internet-noise assessment as additive prioritization context and SHALL NOT suppress detections, suppress alerts, or auto-close incidents solely because a provider classifies a source as benign, a crawler, or commodity background activity.

#### Scenario: Benign classification does not suppress the alert
- **WHEN** a provider classifies a source IP as benign or commodity background activity
- **THEN** the existing alert SHALL remain visible and SHALL NOT be discarded, hidden, or auto-resolved solely from that classification

#### Scenario: Benign classification does not auto-close an incident
- **WHEN** an existing incident contains alerts from a source later classified as commodity background activity
- **THEN** the system SHALL NOT auto-close the incident solely because of that internet-noise classification

### Requirement: Internet-noise assessment SHALL lower urgency only through negative weighting
The system SHALL allow internet-noise assessment to lower investigation urgency only through explicit negative weighting in investigation-priority logic.

#### Scenario: Commodity activity lowers investigation urgency when local evidence is weak
- **WHEN** a source is classified as commodity background activity and the local evidence lacks progression, protected-target repetition, high-value corroboration, or other stronger escalation signals
- **THEN** the system SHALL be able to lower investigation urgency and explain that the observed activity currently aligns with normal internet background noise

#### Scenario: Unknown classification does not lower urgency by default
- **WHEN** the internet-noise provider returns `unknown`, `unclassified`, or a lookup failure
- **THEN** the system SHALL NOT lower investigation urgency solely because of the missing or unknown internet-noise result

### Requirement: Local evidence SHALL override commodity-noise deprioritization
The system SHALL preserve or raise seriousness when stronger local evidence indicates meaningful attack behavior even if the same source is classified as commodity background activity by an external provider.

#### Scenario: Successful-authentication evidence overrides commodity classification
- **WHEN** a source is classified as commodity background activity but the local evidence shows successful authentication after abuse, likely compromise, or equivalent successful-attack progression
- **THEN** the system SHALL preserve or raise seriousness based on the local evidence and SHALL explain that local evidence overrides the commodity classification

#### Scenario: Protected-target repetition overrides commodity classification
- **WHEN** a source is classified as commodity background activity but repeatedly targets protected assets, repeated sensitive paths, or corroborated target-specific activity
- **THEN** the system SHALL remain able to preserve elevated investigation urgency or incident eligibility and SHALL explain the override reasons

#### Scenario: Correlation and campaign progression override commodity classification
- **WHEN** a source is classified as commodity background activity but participates in cross-source correlation, cross-surface corroboration, or campaign progression
- **THEN** the system SHALL treat the local evidence as authoritative for urgency and SHALL not let the commodity classification suppress seriousness

### Requirement: Incident policy SHALL consume internet-noise assessment only after evidence gating
The system SHALL allow internet-noise assessment to influence prospective incident eligibility or incident priority only after local-evidence override checks have been evaluated.

#### Scenario: Commodity activity can remain alert-only prospectively
- **WHEN** a medium or high alert is classified as commodity background activity and the local evidence does not exceed the override threshold
- **THEN** the system SHALL be able to keep the alert visible while avoiding a new incident prospectively and SHALL record the reason in incident-policy explanation

#### Scenario: Incident-worthy local evidence still creates or preserves an incident
- **WHEN** an alert or grouped investigation carries incident-worthy local evidence despite commodity-noise classification
- **THEN** the system SHALL remain able to create or link an incident prospectively and SHALL explain why local evidence won

### Requirement: Analyst explanation SHALL be visible and explicit
The system SHALL expose plain-English reasons whenever internet-noise assessment lowers urgency or whenever local evidence overrides that deprioritization.

#### Scenario: Deprioritization reason is visible
- **WHEN** internet-noise assessment lowers investigation urgency
- **THEN** the analyst-facing response SHALL explain that the source is known commodity background activity and that current local evidence does not exceed normal internet noise

#### Scenario: Override reason is visible
- **WHEN** local evidence overrides a commodity-noise classification
- **THEN** the analyst-facing response SHALL explicitly describe the stronger local evidence that kept the investigation elevated

### Requirement: Production rollout SHALL be gated by audited impact evidence
The system SHALL require a production audit of recent real alerts and incidents before implementation enables internet-noise-aware prioritization to alter incident behavior or analyst-priority behavior in production.

#### Scenario: Audit evidence exists before rollout
- **WHEN** the implementation is prepared for production rollout
- **THEN** operators SHALL have a bounded last-30-day audit showing how recent alert and incident IPs map to benign, malicious, unknown, and error internet-noise classifications with prospective override outcomes

#### Scenario: Rollout remains blocked without audit evidence
- **WHEN** that production audit evidence has not been produced
- **THEN** internet-noise-aware policy changes SHALL NOT be enabled in production
