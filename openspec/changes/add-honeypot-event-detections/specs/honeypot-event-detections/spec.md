## ADDED Requirements

### Requirement: Honeypot event types are accepted by SIEM ingestion
The system SHALL accept `env_probe`, `admin_probe`, `scanner_detected`, and `credential_stuffing` as valid SIEM event types for normalized ingestion.

#### Scenario: Valid honeypot event is stored
- **WHEN** a normalized event with event type `env_probe`, `admin_probe`, `scanner_detected`, or `credential_stuffing` is ingested with valid required fields
- **THEN** the system stores the event in `events`

#### Scenario: Invalid event type remains rejected
- **WHEN** an event uses an event type outside the configured whitelist
- **THEN** the system rejects the event before storage

### Requirement: Honeypot metadata is stored without schema expansion
The system SHALL store honeypot-specific metadata in `events.raw_payload` unless implementation proves a database schema change is necessary.

#### Scenario: Path metadata is available for probing detections
- **WHEN** a honeypot path-probing event includes a `path` value in `raw_payload`
- **THEN** detection logic can query that path from `raw_payload` without requiring a dedicated path column

#### Scenario: Username metadata is available for credential stuffing detection
- **WHEN** a credential stuffing event includes a `username` value in `raw_payload`
- **THEN** detection logic can query that username from `raw_payload` without requiring a dedicated username column

### Requirement: Raw passwords are never stored
The system MUST NOT store raw password values from honeypot credential events.

#### Scenario: Raw password key is rejected
- **WHEN** a honeypot credential event includes a top-level `password` key or `raw_payload.password`
- **THEN** the system rejects the payload and does not store the password

#### Scenario: Safe credential metadata is accepted
- **WHEN** a credential stuffing event includes `username`, `password_length`, and `credential_present` without a raw password
- **THEN** the system stores the safe metadata and remains eligible for detection

### Requirement: Honeypot detection rules are runtime configurable
The system SHALL define runtime-configurable defaults for `honeypot_env_probe_threshold`, `honeypot_admin_probe_threshold`, `honeypot_scanner_detected`, and `honeypot_credential_stuffing_threshold`.

#### Scenario: Defaults are returned with detection rules
- **WHEN** detection rule defaults are requested
- **THEN** the honeypot rule IDs are present with integer threshold and window parameters

#### Scenario: Runtime override changes detection behavior
- **WHEN** an authorized configuration override changes a honeypot rule threshold or window
- **THEN** the detector uses the effective configured value without requiring code changes

### Requirement: Sensitive path probing uses distinct path counts
The system SHALL create a `honeypot_env_probe_threshold` alert when one source IP probes at least the configured number of distinct sensitive paths within the configured window.

#### Scenario: Distinct env paths trigger alert
- **WHEN** one source IP sends `env_probe` events for at least three distinct paths within ten minutes using default configuration
- **THEN** the system creates one open `honeypot_env_probe_threshold` alert for that source IP

#### Scenario: Repeated single env path does not trigger alert
- **WHEN** one source IP sends repeated `env_probe` events for the same path within the configured window
- **THEN** the system does not create a `honeypot_env_probe_threshold` alert unless the distinct path threshold is met

### Requirement: Admin path probing uses distinct path counts
The system SHALL create a `honeypot_admin_probe_threshold` alert when one source IP probes at least the configured number of distinct admin paths within the configured window.

#### Scenario: Distinct admin paths trigger alert
- **WHEN** one source IP sends `admin_probe` events for at least three distinct paths within ten minutes using default configuration
- **THEN** the system creates one open `honeypot_admin_probe_threshold` alert for that source IP

#### Scenario: Repeated single admin path does not trigger alert
- **WHEN** one source IP sends repeated `admin_probe` events for the same path within the configured window
- **THEN** the system does not create a `honeypot_admin_probe_threshold` alert unless the distinct path threshold is met

### Requirement: Scanner detections create alerts
The system SHALL create a `honeypot_scanner_detected` alert when scanner activity from one source IP meets the configured scanner threshold within the configured window.

#### Scenario: Scanner event triggers alert at default threshold
- **WHEN** one source IP sends a `scanner_detected` event under the default threshold of one
- **THEN** the system creates one open `honeypot_scanner_detected` alert for that source IP

### Requirement: Credential stuffing uses distinct usernames
The system SHALL create a `honeypot_credential_stuffing_threshold` alert when one source IP attempts at least the configured number of distinct usernames within the configured window.

#### Scenario: Distinct usernames trigger credential stuffing alert
- **WHEN** one source IP sends `credential_stuffing` events for at least five distinct usernames within fifteen minutes using default configuration
- **THEN** the system creates one open `honeypot_credential_stuffing_threshold` alert for that source IP

#### Scenario: Repeated username does not trigger credential stuffing alert
- **WHEN** one source IP sends repeated `credential_stuffing` events for the same username within the configured window
- **THEN** the system does not create a `honeypot_credential_stuffing_threshold` alert unless the distinct username threshold is met

### Requirement: Honeypot alerts preserve normal SOAR handoff
The system SHALL return honeypot-created alerts through the existing `alerts_created` flow so post-commit SOAR enqueue, incident creation, and playbook scheduling behavior remains unchanged.

#### Scenario: Created honeypot alert is returned for post-commit handoff
- **WHEN** a honeypot detector creates an alert during normalized ingestion
- **THEN** the alert dictionary is included in `alerts_created` with `alert_id`, `source_ip`, `response_action`, and `severity`

#### Scenario: SOAR behavior is not directly changed
- **WHEN** honeypot detection support is implemented
- **THEN** SOAR worker, approval gate, playbook, protected-target, and integration adapter behavior remain unchanged
