## ADDED Requirements

### Requirement: pfSense target context SHALL preserve bounded exact and aggregate evidence
The system SHALL expand pfSense target-context snapshots so analysts can inspect actual targets without storing unbounded raw payload data on alerts or aggregates.

#### Scenario: Target context distinguishes exact from aggregate evidence
- **WHEN** the system persists or returns pfSense target evidence for an alert or related reconnaissance aggregate
- **THEN** the evidence SHALL identify whether it represents `exact_target` evidence or bounded `aggregate_sample` evidence

#### Scenario: Target context includes required bounded fields
- **WHEN** the system returns pfSense target evidence
- **THEN** it SHALL include, where available, a primary destination IP, primary destination port, sample destination IPs, sample destination ports, total distinct destination count, total distinct port count, protocol, firewall action, interface or direction, attempts, first seen, last seen, related event count, and a bounded evidence window

### Requirement: Sample destination evidence SHALL be deterministic and bounded
The system SHALL provide representative target samples without unbounded or unstable ordering.

#### Scenario: Sample destination IPs are deterministic
- **WHEN** the system returns sample destination IPs for pfSense target evidence
- **THEN** it SHALL return at most 5 destination IPs ordered by descending matching-event frequency and ascending IP text for ties

#### Scenario: Sample destination ports are deterministic
- **WHEN** the system returns sample destination ports for pfSense target evidence
- **THEN** it SHALL return at most 5 destination ports ordered by descending matching-event frequency and ascending numeric port for ties

### Requirement: Target evidence SHALL preserve a path to related underlying events
The system SHALL let analysts inspect bounded related pfSense events without copying unbounded raw event payloads into alert or aggregate records.

#### Scenario: Related-event inspection is available from stored evidence
- **WHEN** an analyst requests related underlying events for a pfSense alert or reconnaissance aggregate
- **THEN** the system SHALL provide a bounded related-event inspection path derived from the stored evidence window and target filters

#### Scenario: Raw payload remains authoritative
- **WHEN** analysts need packet- or event-level detail beyond the bounded snapshot
- **THEN** the source of truth SHALL remain `events.raw_payload` and the alert or aggregate snapshot SHALL remain a bounded investigation summary

### Requirement: The backend SHALL provide canonical human-readable scan descriptions
The system SHALL generate analyst-facing scan descriptions in the backend so wording stays consistent across UI surfaces and notifications.

#### Scenario: One port across many hosts uses host-sweep wording
- **WHEN** a pfSense scan candidate touches exactly one distinct destination port across multiple destination hosts
- **THEN** the canonical description SHALL use the pattern `Scanned port <port> across <count> <host label>.`

#### Scenario: Many ports on one host uses port-sweep wording
- **WHEN** a pfSense scan candidate touches multiple distinct destination ports on exactly one destination host
- **THEN** the canonical description SHALL use the pattern `Scanned <count> ports on 1 destination host.`

#### Scenario: Many ports across many hosts uses mixed-breadth wording
- **WHEN** a pfSense scan candidate touches multiple distinct destination ports across multiple destination hosts
- **THEN** the canonical description SHALL use the pattern `Scanned <port count> ports across <host count> destination hosts.`

### Requirement: Human-readable descriptions SHALL be grammatically and technically precise
The system SHALL use singular/plural grammar correctly and SHALL not claim unsupported target semantics.

#### Scenario: Singular and plural forms are correct
- **WHEN** a human-readable pfSense scan description is generated
- **THEN** the wording SHALL use correct singular and plural forms for port and host counts

#### Scenario: Public IP wording is used only when supported
- **WHEN** the evidence proves the sampled or primary targets are public IP addresses
- **THEN** the description MAY use `public IPs`; otherwise it SHALL use `destination hosts`

### Requirement: Expanded target evidence SHALL remain additive to existing pfSense investigation contracts
The system SHALL extend current pfSense target and investigation rendering without forcing downstream consumers to parse message text.

#### Scenario: Exact counts remain available separately from prose
- **WHEN** the system returns canonical scan descriptions
- **THEN** the corresponding exact counts and sampled target evidence SHALL remain available in structured target-context fields

#### Scenario: Alert details can render structured evidence without parsing the message
- **WHEN** a frontend alert-detail surface renders pfSense target evidence
- **THEN** it SHALL be able to render the canonical description and structured fields from additive backend data rather than inferring them from free-form alert messages
