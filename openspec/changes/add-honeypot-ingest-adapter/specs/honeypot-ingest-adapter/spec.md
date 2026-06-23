## ADDED Requirements

### Requirement: Honeypot ingest endpoint is authenticated
The system SHALL provide `POST /ingest/honeypot` and enforce the existing ingest API key model before processing any payload.

#### Scenario: Valid API key allows processing
- **WHEN** a request to `POST /ingest/honeypot` includes a valid ingest API key and valid JSON payload
- **THEN** the system processes the payload through the honeypot adapter

#### Scenario: Missing API key is rejected
- **WHEN** a request to `POST /ingest/honeypot` omits the ingest API key
- **THEN** the system rejects the request without storing an event

#### Scenario: Wrong API key is rejected
- **WHEN** a request to `POST /ingest/honeypot` includes an invalid ingest API key
- **THEN** the system rejects the request without storing an event

### Requirement: Honeypot endpoint accepts native event types
The honeypot adapter SHALL accept `env_probe`, `admin_probe`, `scanner_detected`, `credential_stuffing`, and `http_error` as honeypot-native event types.

#### Scenario: Supported honeypot event type is accepted
- **WHEN** a valid request uses one of the supported honeypot event types
- **THEN** the adapter normalizes the event for SIEM ingestion

#### Scenario: Unsupported honeypot event type is rejected
- **WHEN** a request uses an event type outside the honeypot adapter allowlist
- **THEN** the system rejects the request without storing an event

### Requirement: Honeypot payloads are normalized into existing SIEM events
The honeypot adapter SHALL normalize flat honeypot payloads into the existing `ingest_normalized_event()` contract.

#### Scenario: Source fields are stamped
- **WHEN** a valid honeypot payload is normalized
- **THEN** the normalized event contains `source="honeypot"` and `source_type="honeypot"`

#### Scenario: Timestamp maps to event timestamp
- **WHEN** a valid honeypot payload includes `timestamp`
- **THEN** the normalized event uses that value as `event_timestamp`

#### Scenario: Generated normalized fields are present
- **WHEN** a valid honeypot payload is normalized
- **THEN** the normalized event includes generated `severity`, `message`, `app_name`, and `environment`

### Requirement: Honeypot metadata is preserved in raw payload
The honeypot adapter SHALL preserve safe honeypot-specific fields and future safe metadata in `raw_payload`.

#### Scenario: Known honeypot fields are preserved
- **WHEN** a valid honeypot payload includes `path`, `method`, `user_agent`, `username`, `password_length`, `credential_present`, or `scanner_signature`
- **THEN** those safe fields are present in normalized `raw_payload`

#### Scenario: Future safe metadata is preserved
- **WHEN** a valid honeypot payload includes additional metadata that is not blocked by credential safety rules
- **THEN** that metadata is preserved in normalized `raw_payload`

### Requirement: Raw passwords are rejected
The honeypot adapter MUST reject raw password fields before storage or forwarding into the normalized ingest pipeline.

#### Scenario: Top-level password is rejected
- **WHEN** a honeypot payload includes a top-level `password` field
- **THEN** the system rejects the request and does not store the password

#### Scenario: Nested password is rejected
- **WHEN** a honeypot payload includes a nested `password` field
- **THEN** the system rejects the request and does not store the password

#### Scenario: Safe credential metadata is allowed
- **WHEN** a credential stuffing payload includes `username`, `password_length`, and `credential_present` without a raw password
- **THEN** the system accepts the safe metadata and remains eligible for detection

### Requirement: Honeypot http_error remains http_error
The honeypot adapter SHALL normalize honeypot `http_error` events as SIEM `http_error` events rather than translating them to another event type.

#### Scenario: Honeypot HTTP error preserves event type
- **WHEN** a valid honeypot payload uses `event_type="http_error"`
- **THEN** the normalized event passed to `ingest_normalized_event()` also uses `event_type="http_error"`

### Requirement: Existing detection and SOAR flow is preserved
The honeypot adapter SHALL reuse the existing normalized ingest and post-commit handoff flow without changing detection engine, SOAR worker, approval, playbook, queue, schema, frontend, or correlation behavior.

#### Scenario: Alerts created by normalized ingest are returned
- **WHEN** a honeypot event produces one or more alerts through existing detection behavior
- **THEN** the route response includes those alerts in `alerts_created`

#### Scenario: Post-commit SOAR handoff remains route-level
- **WHEN** honeypot-created alerts are returned from normalized ingestion
- **THEN** existing post-commit enqueue, incident, and playbook scheduling calls handle them without direct SOAR behavior changes
