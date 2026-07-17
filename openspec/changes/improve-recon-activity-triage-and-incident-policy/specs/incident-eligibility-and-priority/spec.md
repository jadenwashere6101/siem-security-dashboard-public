## ADDED Requirements

### Requirement: Incident eligibility SHALL be separate from alert severity
The system SHALL decide incident creation from operational actionability rather than direct severity mapping alone.

#### Scenario: Routine honeypot scanner/admin probing stays alert-only
- **WHEN** a honeypot alert is `honeypot_scanner_detected` or `honeypot_admin_probe`
- **THEN** the system SHALL not create an incident from that alert by itself

#### Scenario: Routine aggregate pfSense recon stays outside incidents
- **WHEN** a pfSense alert represents routine aggregate reconnaissance without stronger progression or separately approved escalation evidence
- **THEN** the system SHALL keep that activity visible without creating a source-level incident

#### Scenario: Stronger evidence remains incident-eligible
- **WHEN** an alert carries stronger approved evidence such as progression-backed pfSense behavior or incident-eligible honeypot credential stuffing
- **THEN** the system SHALL remain able to create or link an incident and explain why

### Requirement: Honeypot env probing SHALL follow an alert-first policy
The system SHALL treat `honeypot_env_probe_threshold` as alert-first unless stronger supporting evidence is already available.

#### Scenario: Standalone env probing remains alert-only
- **WHEN** `honeypot_env_probe_threshold` fires without corroborating progression, recurrence, campaign support, or repeated protected-service targeting
- **THEN** the system SHALL not create an incident from that alert by itself

#### Scenario: Stronger env probing can escalate
- **WHEN** `honeypot_env_probe_threshold` carries stronger approved supporting evidence in context
- **THEN** the system SHALL be able to create or link an incident and record the reasons

### Requirement: Incident priority SHALL reflect actionability
The system SHALL assign P1, P2, and P3 from response urgency and investigation actionability rather than direct severity inheritance.

#### Scenario: Priority reasons are visible
- **WHEN** an incident is created or its priority is computed
- **THEN** the system SHALL expose short plain-English reasons for that priority

#### Scenario: High severity does not automatically become P2
- **WHEN** a high-severity alert is incident-eligible but lacks urgent response or strong progression evidence
- **THEN** the system SHALL be able to create a P3 incident instead of defaulting to P2

#### Scenario: Critical behavior remains immediately urgent
- **WHEN** the system identifies critical or likely-compromise behavior requiring immediate action
- **THEN** the incident SHALL remain eligible for P1 handling

### Requirement: Recon incident ownership SHALL be grouped where appropriate
The system SHALL let one Recon Activity own at most one grouped incident and SHALL avoid duplicate source-level fan-out for the same aggregate investigation story.

#### Scenario: Member alerts link to a grouped recon incident
- **WHEN** multiple member alerts belong to the same case-worthy Recon Activity
- **THEN** the system SHALL link those alerts to one grouped incident rather than create one incident per source

#### Scenario: Source-specific progression stays separately actionable
- **WHEN** one source leaves the routine aggregate path through stronger progression or other approved source-specific evidence
- **THEN** the system SHALL still be able to create or link a separate actionable incident for that source

### Requirement: Safe P3 auto-close behavior SHALL remain intact
The system SHALL preserve the existing P3 auto-close safety requirements while applying the new incident policy prospectively.

#### Scenario: Auto-close requires fully safe conditions
- **WHEN** the system auto-closes a P3 incident
- **THEN** every linked alert SHALL already be resolved, there SHALL be no pending approvals, no active response actions, no active playbook executions, no active investigation state, and no assigned analyst

#### Scenario: Auto-close remains auditable and idempotent
- **WHEN** the same eligible P3 auto-close path runs more than once
- **THEN** it SHALL record an auditable closure reason and SHALL not perform duplicate closure side effects

### Requirement: Historical incidents SHALL remain unchanged
The system SHALL apply the new incident policy prospectively without rewriting historical incidents, alerts, approvals, or priorities.

#### Scenario: Legacy incident remains as created
- **WHEN** an incident existed before the new policy took effect
- **THEN** the system SHALL not retroactively rewrite its original severity, priority, or creation history
