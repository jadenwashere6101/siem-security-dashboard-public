## ADDED Requirements

### Requirement: Parser rejects oversized packet input before parsing
The parser SHALL enforce an initial maximum raw packet size of 4096 bytes before UTF-8 decoding, syslog envelope parsing, or pfSense `filterlog` parsing.

#### Scenario: Oversized packet is rejected before parse
- **WHEN** raw input exceeds 4096 bytes
- **THEN** the parser rejects the input without decoding or parsing it and returns bounded sanitized parse-failure telemetry.

#### Scenario: Packet at size limit remains eligible for parse
- **WHEN** raw input is 4096 bytes or smaller
- **THEN** the parser proceeds to UTF-8 handling and later parsing stages.

### Requirement: Parser handles UTF-8 and unsafe control characters safely
The parser SHALL handle malformed UTF-8 without crashing and SHALL strip or replace unsafe control characters before using text in normalized output, logs, or parse-failure telemetry.

#### Scenario: Invalid UTF-8 does not crash parser
- **WHEN** raw input contains malformed UTF-8 bytes
- **THEN** the parser fails safely or decodes with safe replacement and returns either a normalized event or bounded parse-failure telemetry without raising an unhandled exception.

#### Scenario: Unsafe control characters are sanitized
- **WHEN** decoded syslog text contains unsafe control characters
- **THEN** the parser strips or replaces those characters before producing normalized output or parse-failure telemetry.

### Requirement: Parser extracts pfSense filterlog payload from syslog envelope
The parser SHALL parse a recognizable syslog envelope sufficiently to identify and extract a pfSense `filterlog` payload, while treating all envelope fields as untrusted.

#### Scenario: Filterlog payload is extracted
- **WHEN** a syslog message contains a recognizable pfSense `filterlog` marker and payload
- **THEN** the parser extracts the sanitized `filterlog` payload for field parsing.

#### Scenario: Non-filterlog syslog is rejected safely
- **WHEN** a syslog message does not contain a pfSense `filterlog` payload
- **THEN** the parser returns bounded parse-failure telemetry and does not produce a normalized event.

### Requirement: Parser supports common IPv4 TCP filterlog records
The parser SHALL parse common IPv4 TCP pfSense `filterlog` records and extract action, interface, direction, IP version, protocol, source IP, destination IP, source port, destination port, rule identifier, and tracker identifier when those values are present.

#### Scenario: Valid IPv4 TCP filterlog line parses correctly
- **WHEN** a common IPv4 TCP pfSense `filterlog` line is parsed
- **THEN** the parser returns parsed fields including `action`, `interface`, `direction`, `ip_version="4"`, `protocol="tcp"`, `source_ip`, `destination_ip`, `source_port`, `destination_port`, and available `rule_id` or `tracker`.

### Requirement: Parser supports common IPv4 UDP filterlog records
The parser SHALL parse common IPv4 UDP pfSense `filterlog` records and extract action, interface, direction, IP version, protocol, source IP, destination IP, source port, destination port, rule identifier, and tracker identifier when those values are present.

#### Scenario: Valid IPv4 UDP filterlog line parses correctly
- **WHEN** a common IPv4 UDP pfSense `filterlog` line is parsed
- **THEN** the parser returns parsed fields including `action`, `interface`, `direction`, `ip_version="4"`, `protocol="udp"`, `source_ip`, `destination_ip`, `source_port`, `destination_port`, and available `rule_id` or `tracker`.

### Requirement: Parser handles IPv6 and unsupported variants safely
The parser SHALL handle IPv6 records, unknown IP versions, unsupported protocols, and unfamiliar `filterlog` variants without crashing or guessing unsupported field positions.

#### Scenario: IPv6 record is handled safely
- **WHEN** the parser receives a pfSense `filterlog` record for IPv6 before IPv6 support is specified
- **THEN** the parser returns bounded parse-failure telemetry or an explicit unsupported-variant result without producing a misleading IPv4 normalized event.

#### Scenario: Unsupported protocol is handled safely
- **WHEN** the parser receives a `filterlog` record with an unsupported protocol or field layout
- **THEN** the parser returns bounded parse-failure telemetry or an explicit unsupported-variant result without raising an unhandled exception.

### Requirement: Parser never crashes on malformed external input
The parser SHALL fail safely for malformed, incomplete, empty, non-filterlog, or otherwise unexpected external input.

#### Scenario: Malformed line does not crash parser
- **WHEN** malformed syslog or malformed `filterlog` text is parsed
- **THEN** the parser returns bounded parse-failure telemetry without raising an unhandled exception.

#### Scenario: Empty input does not crash parser
- **WHEN** empty input is parsed
- **THEN** the parser returns bounded parse-failure telemetry without raising an unhandled exception.

### Requirement: Parse failure telemetry is bounded and sanitized
The parser SHALL produce parse-failure telemetry that contains only bounded sanitized diagnostic fields and avoids broad raw payload retention.

#### Scenario: Parse failure output is bounded
- **WHEN** parsing fails
- **THEN** the failure telemetry includes a bounded reason, failure stage, input byte length when available, and optional sanitized summary capped to an implementation-defined small limit.

#### Scenario: Parse failure does not retain full raw syslog
- **WHEN** parsing fails on attacker-controlled syslog content
- **THEN** the failure telemetry does not include the full raw packet or full raw syslog line by default.

### Requirement: Normalizer emits pfSense firewall unified events
The normalizer SHALL emit successful events using the existing unified event shape with `source="pfsense"`, `source_type="firewall"`, `app_name="pfsense_filterlog"`, traffic `source_ip`, `event_type`, `severity`, `message`, `environment`, optional `event_timestamp`, and a safe `raw_payload`.

#### Scenario: Normalized output matches unified event expectations
- **WHEN** a supported pfSense `filterlog` record is normalized
- **THEN** the normalized event includes the fields required by existing normalized ingest expectations and does not require Flask, DB, network sockets, or detection engine calls.

#### Scenario: Source fields are stamped
- **WHEN** a supported pfSense `filterlog` record is normalized
- **THEN** the normalized event contains `source="pfsense"` and `source_type="firewall"`.

### Requirement: Normalized raw payload contains safe parsed firewall fields
The normalizer SHALL include safe parsed firewall fields in `raw_payload`, including action, interface, direction, IP version, protocol, source IP, destination IP, source port when present, destination port when present, rule identifier when present, tracker identifier when present, and a bounded sanitized summary only when needed.

#### Scenario: Parsed fields are preserved in raw payload
- **WHEN** a supported pfSense `filterlog` record is normalized
- **THEN** `raw_payload` contains safe parsed firewall fields including `action`, `interface`, `direction`, `ip_version`, `protocol`, `source_ip`, `destination_ip`, and available port and rule/tracker fields.

#### Scenario: Raw summary is sanitized and bounded
- **WHEN** the normalizer includes a raw sanitized summary for debugging
- **THEN** that summary is stripped of unsafe control characters and capped to a bounded length.

### Requirement: Action mapping exposes future firewall taxonomy candidates
The normalizer SHALL preserve the original pfSense action and SHALL expose candidate event-type mapping where `block` can map to future `firewall_block` taxonomy and `pass` can map to future `firewall_allow` taxonomy if accepted by later specs.

#### Scenario: Blocked traffic normalizes as firewall block candidate
- **WHEN** a supported pfSense record has action `block`
- **THEN** the normalized event preserves `action="block"` and marks the event as a `firewall_block` candidate without requiring detection-rule implementation.

#### Scenario: Passed traffic normalizes as firewall allow candidate
- **WHEN** a supported pfSense record has action `pass`
- **THEN** the normalized event preserves `action="pass"` and marks the event as a `firewall_allow` candidate without requiring detection-rule implementation.

### Requirement: Parser normalizer is isolated from runtime side effects
The parser/normalizer SHALL be unit-testable without Flask, database connections, network sockets, UDP listeners, systemd services, Azure NSG rules, VM firewall changes, detection rules, SOAR/playbook behavior, or pfSense operator handoff.

#### Scenario: Parser can be tested without runtime services
- **WHEN** unit tests call the parser/normalizer directly with raw packet bytes or sanitized text fixtures
- **THEN** the tests do not require Flask app context, database state, network sockets, VM access, Azure access, or external pfSense configuration.

#### Scenario: Parser performs no direct database writes
- **WHEN** a supported pfSense record is parsed and normalized
- **THEN** the parser/normalizer returns structured data only and performs no direct database write.
