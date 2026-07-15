## ADDED Requirements

### Requirement: The system SHALL persist a bounded distributed reconnaissance aggregate for pfSense commodity scanning
The system SHALL create a durable analyst-facing aggregate labeled `Distributed Internet Reconnaissance Activity` for many-source pfSense commodity reconnaissance against the same protected public destination range and service set.

#### Scenario: Aggregate record is created for qualifying distributed reconnaissance
- **WHEN** qualifying pfSense reconnaissance alerts from many external sources target the same protected destination range and overlapping service signature within the aggregate window
- **THEN** the system SHALL create or update one `Distributed Internet Reconnaissance Activity` aggregate rather than treating each source as the primary operational object

#### Scenario: Underlying alerts remain preserved
- **WHEN** an alert is enrolled into a `Distributed Internet Reconnaissance Activity` aggregate
- **THEN** the underlying alert SHALL remain stored, viewable, and independently auditable

### Requirement: Aggregate membership SHALL require target signature overlap and SHALL NOT rely on time alone
The system SHALL determine distributed-recon aggregate membership from both temporal overlap and shared target evidence.

#### Scenario: Same time window alone is insufficient
- **WHEN** two pfSense reconnaissance alerts occur in the same time window but target different protected destination ranges or non-overlapping service signatures
- **THEN** they SHALL NOT be enrolled into the same `Distributed Internet Reconnaissance Activity` aggregate

#### Scenario: Shared target range and service signature join the same aggregate
- **WHEN** two qualifying pfSense reconnaissance alerts occur within the aggregate window, target the same protected destination range bucket, and share at least one destination port in their service signature
- **THEN** they SHALL be eligible for the same `Distributed Internet Reconnaissance Activity` aggregate

### Requirement: Aggregate enrollment SHALL be limited to routine external reconnaissance patterns
The aggregate SHALL represent distributed commodity reconnaissance, not every pfSense alert family or every high-severity source-specific escalation.

#### Scenario: Commodity port scan and repeated deny alerts can enroll
- **WHEN** inbound external-source `pfsense_firewall_port_scan` or `pfsense_firewall_repeated_deny` alerts satisfy this capability’s membership rules
- **THEN** they SHALL be eligible for enrollment into a `Distributed Internet Reconnaissance Activity` aggregate

#### Scenario: Source-specific progression or containment behavior stays outside the aggregate
- **WHEN** an alert represents `pfsense_firewall_suspicious_allow`, `pfsense_firewall_allow_after_deny`, or outbound/internal-host repeated deny behavior
- **THEN** it SHALL NOT be used as the primary member evidence for a `Distributed Internet Reconnaissance Activity` aggregate

### Requirement: Aggregate detail SHALL present a fixed investigation summary
The aggregate SHALL expose a bounded analyst summary with deterministic fields rather than free-form or unbounded event dumps.

#### Scenario: Aggregate detail includes required summary fields
- **WHEN** an analyst opens a `Distributed Internet Reconnaissance Activity` record
- **THEN** the record SHALL provide `first_seen`, `last_seen`, active duration or time window, source IP count, destination IP count, primary destination ports, represented alert types, total underlying alerts or events, countries and ASNs when available, reputation distribution, assessment text, coordination status, related incidents or approvals, and current status

#### Scenario: Assessment text does not overclaim coordination
- **WHEN** the evidence supports commodity distributed scanning but not operator linkage
- **THEN** the aggregate assessment SHALL describe distributed commodity scanning and SHALL state that coordination is not established

### Requirement: Aggregate coordination status SHALL be explicit and bounded
The system SHALL classify aggregate coordination evidence using exactly three bounded states.

#### Scenario: Coordination status starts as not established
- **WHEN** qualifying distributed reconnaissance reflects many one-shot or lightly repeated external sources without stronger linkage evidence
- **THEN** the aggregate coordination status SHALL be `not_established`

#### Scenario: Coordination status can increase only with stronger evidence
- **WHEN** additional evidence later supports stronger source linkage or patterned coordination
- **THEN** the aggregate coordination status MAY advance to `possible` or `supported`, and SHALL NOT advance automatically from source count alone

### Requirement: The aggregate SHALL be the primary operational object for routine distributed commodity reconnaissance
Routine distributed commodity reconnaissance SHALL remain visible without generating one automatic incident and one approval per source IP.

#### Scenario: Routine aggregate stays visible without bulk incident fan-out
- **WHEN** a `Distributed Internet Reconnaissance Activity` aggregate remains routine commodity scanning with coordination status `not_established` and no source-specific containment behavior
- **THEN** the system SHALL preserve member alerts and aggregate visibility without creating one automatic P2 incident per source IP

#### Scenario: Aggregate can own at most one grouped incident on escalation
- **WHEN** a `Distributed Internet Reconnaissance Activity` aggregate materially escalates beyond routine commodity reconnaissance
- **THEN** the system MAY create or link at most one grouped incident for that aggregate rather than creating separate automatic incidents for every member source

### Requirement: Aggregate notifications SHALL be deduplicated and material-change driven
The system SHALL use the existing notification policy path while reducing pfSense commodity notification noise through aggregate-level deduplication.

#### Scenario: Aggregate opening notification fires once
- **WHEN** a `Distributed Internet Reconnaissance Activity` aggregate first becomes notification-eligible under existing notification policy rules
- **THEN** the system SHALL emit at most one opening notification for that aggregate

#### Scenario: Aggregate update notification requires a material change
- **WHEN** an aggregate receives new member alerts but does not change severity, coordination status, primary service signature, or status
- **THEN** the system SHALL NOT emit a new update notification for that aggregate

#### Scenario: Aggregate update notification can reflect escalation or closure
- **WHEN** an aggregate changes severity, coordination status, primary service signature, or resolves
- **THEN** the system MAY emit one deduplicated aggregate update notification through the existing notification-policy path

### Requirement: The aggregate SHALL be exposed through small focused analyst surfaces
The system SHALL provide bounded read-only analyst access to distributed reconnaissance aggregates without redesigning the application.

#### Scenario: Analysts can inspect representative sources and targets
- **WHEN** an analyst opens a `Distributed Internet Reconnaissance Activity` view or detail surface
- **THEN** the system SHALL allow inspection of representative sources, target evidence, and linked underlying alerts or events

#### Scenario: Aggregate is visible from existing operational surfaces
- **WHEN** the platform renders alert details or SOC Command Center operational summaries for relevant pfSense activity
- **THEN** the system SHALL provide a bounded entry point to the related `Distributed Internet Reconnaissance Activity` record when one exists
