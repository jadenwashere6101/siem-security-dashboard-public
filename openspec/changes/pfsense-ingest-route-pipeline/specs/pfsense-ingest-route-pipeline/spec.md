## ADDED Requirements

### Requirement: pfSense ingest route is authenticated
The system SHALL provide `POST /ingest/pfsense` and SHALL enforce the existing ingest API-key authentication pattern before processing any payload.

#### Scenario: Valid API key allows pfSense payload processing
- **WHEN** a request to `POST /ingest/pfsense` includes a valid ingest API key and valid normalized pfSense payload
- **THEN** the route processes the payload through the centralized ingest pipeline.

#### Scenario: Missing API key is rejected
- **WHEN** a request to `POST /ingest/pfsense` omits the ingest API key
- **THEN** the route rejects the request without calling centralized ingest.

#### Scenario: Invalid API key is rejected
- **WHEN** a request to `POST /ingest/pfsense` includes an invalid ingest API key
- **THEN** the route rejects the request without calling centralized ingest.

### Requirement: pfSense route accepts only normalized parser contract payloads
The route SHALL accept sanitized, parsed pfSense events that conform to the `pfsense-filterlog-parser-normalizer` normalized event contract and SHALL NOT accept raw syslog as the route contract.

#### Scenario: Normalized firewall block candidate is accepted
- **WHEN** a valid normalized pfSense payload uses `event_type="firewall_block"`, `source="pfsense"`, and `source_type="firewall"`
- **THEN** the route accepts the payload for centralized ingest.

#### Scenario: Normalized firewall allow candidate is accepted
- **WHEN** a valid normalized pfSense payload uses `event_type="firewall_allow"`, `source="pfsense"`, and `source_type="firewall"`
- **THEN** the route accepts the payload for centralized ingest.

#### Scenario: Raw syslog payload is rejected
- **WHEN** a request sends raw syslog text instead of the normalized parser contract payload
- **THEN** the route returns a safe 4xx response and does not call centralized ingest.

### Requirement: pfSense route validates required normalized fields
The route SHALL validate required normalized fields before calling centralized ingest, including `event_type`, `severity`, `source_ip`, `source`, `source_type`, `message`, `app_name`, `environment`, and `raw_payload`.

#### Scenario: Missing required fields are rejected
- **WHEN** a pfSense request omits one or more required normalized fields
- **THEN** the route returns a safe 4xx response and does not call centralized ingest.

#### Scenario: Invalid source IP is rejected
- **WHEN** a pfSense request contains an invalid `source_ip`
- **THEN** the route returns a safe 4xx response and does not call centralized ingest.

#### Scenario: Wrong source fields are rejected
- **WHEN** a pfSense request contains `source` or `source_type` values other than `pfsense` and `firewall`
- **THEN** the route returns a safe 4xx response and does not call centralized ingest.

### Requirement: pfSense route validates firewall-specific raw payload fields
The route SHALL validate that `raw_payload` is an object containing safe parsed firewall fields required by the parser contract, including `action`, `interface`, `direction`, `ip_version`, `protocol`, `source_ip`, `destination_ip`, and `destination_port` when present.

#### Scenario: Parsed firewall fields are accepted
- **WHEN** `raw_payload` contains valid parsed pfSense firewall fields from the parser contract
- **THEN** the route remains eligible to call centralized ingest.

#### Scenario: Malformed raw payload is rejected
- **WHEN** `raw_payload` is missing, not an object, or contains malformed firewall field types
- **THEN** the route returns a safe 4xx response and does not call centralized ingest.

### Requirement: pfSense route uses centralized ingest pipeline
The route SHALL call the existing centralized `ingest_normalized_event` flow or equivalent current ingest function for event storage and detection/correlation processing.

#### Scenario: Route calls centralized ingest for valid payload
- **WHEN** a valid pfSense payload is submitted
- **THEN** the route calls the centralized ingest function with `source="pfsense"` and `source_type="firewall"`.

#### Scenario: Route does not directly write events outside centralized ingest
- **WHEN** the pfSense route stores a valid event
- **THEN** event insertion happens through the centralized ingest pipeline rather than a separate direct event insert path.

### Requirement: Existing downstream orchestration is preserved
The pfSense route SHALL preserve existing post-commit detection, correlation, SOAR queue, playbook scheduling, and incident orchestration behavior used by current ingest routes.

#### Scenario: Successful ingest schedules downstream behavior through current flow
- **WHEN** centralized ingest returns alerts for a valid pfSense payload
- **THEN** the route runs the existing post-commit playbook scheduling, queue enqueueing, and incident creation flow for those alerts.

#### Scenario: Parser tests remain separate from route tests
- **WHEN** route/API tests are added for `POST /ingest/pfsense`
- **THEN** those tests focus on route validation, authentication, centralized ingest calls, and orchestration behavior rather than parser internals.

### Requirement: pfSense route returns safe structured responses
The route SHALL return safe structured JSON responses for success and failure and SHALL NOT leak full raw payloads, raw syslog, stack traces, or attacker-controlled content in error responses.

#### Scenario: Successful ingest returns structured response
- **WHEN** a valid pfSense payload is ingested
- **THEN** the route returns a structured success response with any existing safe alert summary fields.

#### Scenario: Malformed payload returns safe 4xx response
- **WHEN** a malformed or invalid pfSense payload is submitted
- **THEN** the route returns a safe 4xx JSON response without echoing full attacker-controlled payload content.

### Requirement: pfSense route applies request bounds where supported
The route SHALL use existing Flask/app request-size protections or a route-level bound where supported by current application patterns.

#### Scenario: Oversized request is rejected safely when bounded
- **WHEN** a pfSense request exceeds the configured request-size bound
- **THEN** the route rejects the request safely without calling centralized ingest.

### Requirement: pfSense route excludes listener, deployment, and detection implementation
This change SHALL NOT implement UDP sockets, listener daemons, systemd services, Azure NSG changes, VM firewall changes, pfSense/uncle handoff, firewall detection rules, SOAR/playbook tuning, parser redesign, or deployment/runtime validation.

#### Scenario: Route spec excludes UDP listener work
- **WHEN** the pfSense route pipeline is implemented later
- **THEN** it does not bind sockets, listen for syslog packets, create systemd units, open ports, or change Azure/VM firewall exposure.

#### Scenario: Route spec excludes detection and SOAR tuning
- **WHEN** the pfSense route pipeline is implemented later
- **THEN** it preserves existing downstream orchestration but does not add firewall detection rules or tune playbooks.
