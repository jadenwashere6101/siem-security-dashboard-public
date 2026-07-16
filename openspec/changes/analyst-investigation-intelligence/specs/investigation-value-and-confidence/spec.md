## ADDED Requirements

### Requirement: Investigation Value SHALL exist separately from Severity
The system SHALL expose an Investigation Value model that is distinct from Severity. Severity SHALL continue to answer "How dangerous is this?" Investigation Value SHALL answer "Why should I investigate this first?"

#### Scenario: Investigation Value does not replace Severity
- **WHEN** an analyst views an alert, incident, campaign, or recon activity
- **THEN** the system SHALL preserve Severity as a separate signal and SHALL NOT redefine Investigation Value as a renamed Severity field

#### Scenario: High Severity and high Investigation Value remain different concepts
- **WHEN** an object is dangerous but not urgent to investigate first
- **THEN** the system SHALL be able to keep its Severity high while assigning a lower Investigation Value with visible reasons

### Requirement: Investigation Value SHALL be explainable
The system SHALL expose the reasons behind Investigation Value in analyst-readable plain English and SHALL NOT produce opaque or unexplained numbers.

#### Scenario: Reasons are visible alongside the value
- **WHEN** the system presents an elevated Investigation Value
- **THEN** it SHALL show the strongest contributing reasons such as progression, repeated target activity, campaign membership, persistence, or response history

#### Scenario: Mysterious scores are prohibited
- **WHEN** the system presents Investigation Value
- **THEN** it SHALL NOT display an unexplained numeric score, AI score, or urgency label without visible reasoning

### Requirement: Investigation Value SHALL be derived from investigation-specific factors
The system SHALL derive Investigation Value from analyst-priority factors rather than from Severity alone.

#### Scenario: Investigation Value can rise with additional evidence
- **WHEN** progression, persistence, campaign evidence, recurrence, repeated destination targeting, repeated services, corroboration, destination importance, or response history increase
- **THEN** Investigation Value SHALL be able to increase even if Severity does not change

#### Scenario: Investigation Value can remain moderate for routine recon
- **WHEN** a routine commodity reconnaissance alert lacks progression, repeated targeting, campaign escalation, or high-value destination evidence
- **THEN** the system SHALL be able to keep Investigation Value below its highest state even if the alert is still visible

### Requirement: Investigation Value SHALL evolve over time
The system SHALL allow Investigation Value to change as evidence accumulates across existing objects and workflow history.

#### Scenario: Recurrence across days increases attention
- **WHEN** the same protected target or service receives recurring related activity across multiple days
- **THEN** the system SHALL be able to raise Investigation Value and explain the recurrence

#### Scenario: Investigation Value can fall after response and resolution
- **WHEN** meaningful response history, analyst closure, or lack of continued progression reduces urgency
- **THEN** the system SHALL be able to reduce Investigation Value while preserving historical evidence

### Requirement: Analyst confidence SHALL be optional and explainable
The system MAY expose a separate analyst-confidence indicator only if it improves understanding more than it increases complexity. If present, it SHALL be explainable and SHALL NOT duplicate Severity or Investigation Value.

#### Scenario: Confidence is omitted when not justified
- **WHEN** a separate analyst-confidence model would behave like duplicated Severity or duplicated Investigation Value
- **THEN** the system SHALL omit analyst confidence rather than add another weak signal

#### Scenario: Confidence reasons are explicit
- **WHEN** analyst confidence is shown
- **THEN** the system SHALL explain whether confidence is high, medium, or low through visible reasons such as progression consistency, corroboration strength, or lack of established coordination

### Requirement: Investigation-priority wording SHALL be understandable at a glance
Any Investigation Value or analyst-confidence wording added by this capability SHALL be understandable at a glance and SHALL prefer short plain-English phrasing over jargon.

#### Scenario: Short explanation replaces jargon
- **WHEN** the system needs to explain why something deserves attention
- **THEN** it SHALL prefer a short reason such as `Repeated targeting of the same service across multiple days` over internal scoring jargon or undocumented shorthand

