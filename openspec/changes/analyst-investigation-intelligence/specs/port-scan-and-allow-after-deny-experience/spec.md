## ADDED Requirements

### Requirement: Port Scan analyst experience SHALL explain operational meaning without redesigning the detector
The system SHALL preserve the existing Port Scan detector while improving how analysts understand the result.

#### Scenario: Port Scan summary explains whether the activity is routine
- **WHEN** an analyst views a Port Scan alert or related investigation object
- **THEN** the system SHALL be able to communicate whether the activity appears to be routine internet recon, persistent source activity, repeated destination targeting, broader campaign behavior, or progression-backed behavior

#### Scenario: Port Scan does not stop at rule name plus Severity
- **WHEN** a Port Scan alert is shown
- **THEN** the analyst-facing presentation SHALL provide more immediate meaning than only `Port Scan` and a Severity label

### Requirement: Port Scan explanations SHALL expose reasons, not just labels
The system SHALL explain why a Port Scan is being characterized a certain way.

#### Scenario: Plain-English reasons support the summary
- **WHEN** the system describes a Port Scan as routine, persistent, repeated, or campaign-linked
- **THEN** it SHALL expose the underlying reasons such as repeated destination targeting, repeated services, recurrence across days, or lack of progression

#### Scenario: Progression absence is explicit
- **WHEN** no stronger follow-on behavior is present for a Port Scan
- **THEN** the system SHALL be able to state that progression is absent rather than leaving the analyst to infer it

### Requirement: Allow After Deny SHALL strengthen campaign understanding before it creates more alerts
The system SHALL evaluate whether Allow After Deny should enrich campaign or incident understanding before introducing any additional alerting behavior.

#### Scenario: Many-source same-destination history enriches the progression story
- **WHEN** multiple unrelated IPs previously denied against the same destination or service are followed by a later Allow After Deny path
- **THEN** the system SHALL be able to expose that same-destination history as campaign or investigation enrichment

#### Scenario: Additional alerts require stronger justification
- **WHEN** campaign enrichment around Allow After Deny can explain the investigative importance of the pattern
- **THEN** the system SHALL prefer enrichment over creating additional alerts

### Requirement: Port Scan and Allow After Deny wording SHALL be understandable at a glance
Any analyst-facing wording introduced or modified by this capability SHALL be understandable at a glance and SHALL avoid security shorthand where a short plain-English explanation is possible.

#### Scenario: Port Scan uses direct language
- **WHEN** the system labels a Port Scan-related summary
- **THEN** it SHALL prefer plain-English phrases such as `Routine internet recon against the same service` or `Persistent source repeatedly targeting one destination` over cryptic shorthand

#### Scenario: Allow After Deny uses direct language
- **WHEN** the system explains Allow After Deny
- **THEN** it SHALL describe the progression in plain English, such as `Repeated blocked attempts were followed by a later allowed connection to the same service`
