## ADDED Requirements

### Requirement: Distinct route outcomes
The pfSense ingest route SHALL distinguish ingested, filtered, rejected, and failed processing without echoing attacker-controlled payloads.

#### Scenario: Retained event is ingested
- **WHEN** a valid retained event completes centralized ingest
- **THEN** the route SHALL return the existing ingested success class and safe alert summary

#### Scenario: Valid event is filtered
- **WHEN** policy filters a valid event
- **THEN** the route SHALL return HTTP 202 or an equivalent distinct non-ingested success with `status=filtered`, a bounded category/reason, and no raw payload

#### Scenario: Invalid event is rejected
- **WHEN** authentication or schema validation fails
- **THEN** the route SHALL return its existing safe rejection and SHALL NOT classify it as policy-filtered

### Requirement: Listener outcome accounting
The listener SHALL distinguish packets rejected at the edge, parse failures, backend failures, backend-filtered events, and successfully ingested events.

#### Scenario: Backend filters event
- **WHEN** the backend returns its filtered outcome
- **THEN** listener `filtered` SHALL increment and `ingested` SHALL not increment

#### Scenario: Backend stores event
- **WHEN** the backend confirms ingestion
- **THEN** listener `ingested` SHALL increment separately from accepted/forwarded transport counts

### Requirement: Bounded aggregate filter metrics
The system SHALL expose aggregate retained/filtered decisions by bounded reason and a reset/start timestamp without persisting individual dropped events or raw payloads.

#### Scenario: Operator views metrics
- **WHEN** an authorized operator requests pfSense filter metrics
- **THEN** the response SHALL show aggregate counts by decision/reason and clarify whether counters reset on process restart

#### Scenario: Routine traffic is filtered repeatedly
- **WHEN** many routine allows are discarded
- **THEN** no per-event database row or raw payload SHALL be created solely for filter observability

### Requirement: Safe operational logging
Filter logs SHALL be structured, bounded, and free of raw firewall payloads and secrets.

#### Scenario: Configuration lookup falls back
- **WHEN** effective policy uses code defaults because overrides are unavailable or invalid
- **THEN** a warning SHALL name the fallback status without printing DB credentials, API keys, or raw event content

#### Scenario: Event is filtered
- **WHEN** a decision is logged
- **THEN** logs SHALL contain only bounded category/reason and safe metadata needed for operations
