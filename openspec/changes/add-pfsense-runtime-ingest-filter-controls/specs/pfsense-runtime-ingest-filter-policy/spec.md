## ADDED Requirements

### Requirement: Persistent effective pfSense ingest policy
The system SHALL define validated code defaults and database overrides in `pfsense_ingest_config` for known filter categories and SHALL expose effective values plus default/applied/invalid/unavailable status.

#### Scenario: No overrides exist
- **WHEN** the configuration table has no row for a known category
- **THEN** the effective policy SHALL use the source-controlled default for that category

#### Scenario: Valid override exists
- **WHEN** a committed valid override exists
- **THEN** the next pfSense ingest request SHALL use it without restarting any service

#### Scenario: Configuration is invalid or unavailable
- **WHEN** an override fails validation or configuration lookup fails
- **THEN** the request SHALL use safe code defaults, emit a sanitized warning, and SHALL NOT fall back to retaining all traffic

### Requirement: Default retention policy
The default policy SHALL retain every supported blocked event and inbound allowed TCP/UDP traffic to a configured sensitive destination port while filtering routine allowed traffic.

#### Scenario: Blocked traffic arrives
- **WHEN** a valid supported event has action `block`
- **THEN** it SHALL be retained regardless of port or direction under defaults

#### Scenario: Inbound sensitive-port allow arrives
- **WHEN** a valid TCP/UDP `pass` event is inbound and its destination port is in the effective sensitive-port list
- **THEN** it SHALL be retained under defaults

#### Scenario: Routine allow arrives
- **WHEN** a valid `pass` event matches no enabled allow category
- **THEN** it SHALL be filtered under defaults

### Requirement: Deterministic category precedence
The policy SHALL retain a valid event when any enabled category matches and SHALL return one stable decision category and reason without storing the payload.

#### Scenario: All allows is enabled
- **WHEN** `all_allow_events` is enabled and a supported `pass` arrives
- **THEN** it SHALL be retained even when no narrower allow category matches

#### Scenario: DNS traffic is enabled
- **WHEN** `dns_traffic` is enabled and a TCP/UDP `pass` targets destination port 53
- **THEN** it SHALL be retained and SHALL be described as port-53 traffic, not resolver query evidence

### Requirement: Filtering precedes enrichment and storage
The authenticated pfSense route SHALL validate and evaluate policy before geolocation, `ingest_normalized_event()`, event insertion, detection, correlation, playbooks, queues, or incidents.

#### Scenario: Event is filtered
- **WHEN** policy returns a filtered decision
- **THEN** geolocation and `ingest_normalized_event()` SHALL NOT be called and no event, raw-event, alert, incident, queue, playbook, or delivery row SHALL be created

#### Scenario: Event is retained
- **WHEN** policy returns a retained decision
- **THEN** the existing geolocation, centralized ingest, commit, detection/correlation, and post-commit orchestration SHALL remain unchanged

### Requirement: Canonical sensitive-port configuration
The effective sensitive-port list SHALL be the sole runtime list used by both inbound allow retention and pfSense suspicious-allow detection.

#### Scenario: Port list changes
- **WHEN** a super admin commits a valid sensitive-port list
- **THEN** the next ingest decision and suspicious-allow detector evaluation SHALL use the same list

#### Scenario: Port list is invalid
- **WHEN** the list contains duplicates after normalization, booleans, non-integers, values outside 1–65535, or exceeds the configured maximum length
- **THEN** the update SHALL be rejected atomically without changing the effective list

### Requirement: Bounded IPv4 ICMP support
The filterlog parser and normalized validation contract SHALL support specified common IPv4 ICMP layouts without inventing TCP/UDP ports.

#### Scenario: Supported ICMP block arrives
- **WHEN** a common IPv4 ICMP `block` record is parsed
- **THEN** it SHALL normalize with protocol `icmp`, optional ICMP type/code, no required ports, and be retained by the block policy

#### Scenario: Supported ICMP allow arrives
- **WHEN** a common IPv4 ICMP `pass` record is parsed
- **THEN** it SHALL be retained only when `icmp_traffic` or `all_allow_events` is enabled

#### Scenario: Unsupported ICMP or IPv6 layout arrives
- **WHEN** the parser cannot prove field positions or receives IPv6
- **THEN** it SHALL return bounded parse-failure telemetry and SHALL NOT create a normalized event

### Requirement: Filter configuration security and auditability
Configuration persistence and evaluation SHALL preserve API-key ingestion authentication, super-admin mutation authorization, transaction safety, and sanitized audit evidence.

#### Scenario: Non-super-admin attempts update
- **WHEN** an analyst, viewer, or unauthenticated client calls a mutation endpoint
- **THEN** the request SHALL be denied without changing configuration

#### Scenario: Super admin updates configuration
- **WHEN** a valid update commits
- **THEN** an audit event SHALL record category, safe old/new values, actor, and timestamp without secrets or raw firewall payloads
