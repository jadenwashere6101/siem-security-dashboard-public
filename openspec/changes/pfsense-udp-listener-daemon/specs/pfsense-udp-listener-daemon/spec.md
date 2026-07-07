## ADDED Requirements

### Requirement: UDP listener daemon binds to configured host and port
The system SHALL provide a future standalone pfSense UDP listener daemon that binds to a configurable UDP host/interface and port, defaulting to high unprivileged UDP port `5514` unless final port confirmation requires otherwise.

#### Scenario: Listener binds to configured UDP host and port
- **WHEN** the listener starts with configured bind host and port values
- **THEN** it binds a UDP socket to those configured values.

#### Scenario: Listener defaults to unprivileged port
- **WHEN** no explicit port is configured
- **THEN** the listener uses UDP port `5514` as the default.

### Requirement: Listener validates sender source IP before parse or forwarding
The listener SHALL treat all UDP senders as untrusted and SHALL validate packet sender IP against a configured pfSense source IP allow-list before parsing or forwarding.

#### Scenario: Authorized source IP is eligible for parsing
- **WHEN** a UDP packet arrives from an allow-listed source IP
- **THEN** the listener proceeds to packet size validation and parser handoff.

#### Scenario: Unauthorized source IP is rejected
- **WHEN** a UDP packet arrives from a source IP that is not allow-listed
- **THEN** the listener rejects the packet before parsing or backend forwarding and logs only safe bounded rejection metadata.

### Requirement: Listener enforces packet size before parser handoff
The listener SHALL enforce the initial 4096-byte UDP packet size limit before UTF-8 decode, parser handoff, or backend forwarding.

#### Scenario: Oversized packet is rejected
- **WHEN** a UDP packet exceeds 4096 bytes
- **THEN** the listener rejects the packet before parser handoff and logs only safe bounded oversized-packet metadata.

#### Scenario: Packet within limit is eligible for parser handoff
- **WHEN** a UDP packet is 4096 bytes or smaller and source IP is authorized
- **THEN** the listener may pass the packet bytes to the parser contract.

### Requirement: Listener uses parser normalizer contract
The listener SHALL use the `pfsense-filterlog-parser-normalizer` contract for UTF-8 safety, control-character sanitization, syslog/filterlog parsing, malformed packet handling, parse failure telemetry, and normalized event generation.

#### Scenario: Valid packet is parsed through parser contract
- **WHEN** an authorized in-size packet contains a supported pfSense filterlog record
- **THEN** the listener uses the parser contract to produce a normalized pfSense firewall event.

#### Scenario: Malformed UTF-8 does not crash listener
- **WHEN** an authorized in-size packet contains malformed UTF-8
- **THEN** the listener fails safely through parser behavior and does not crash.

#### Scenario: Malformed packet does not reach backend
- **WHEN** parser handoff returns parse failure telemetry instead of a normalized event
- **THEN** the listener logs safe bounded parse failure metadata and does not forward the packet to `/ingest/pfsense`.

### Requirement: Listener forwards valid normalized events to backend route
The listener SHALL forward valid normalized pfSense events to the configured backend `/ingest/pfsense` route using the configured ingest API key/header.

#### Scenario: Valid parsed event is forwarded to backend
- **WHEN** the parser returns a valid normalized pfSense event
- **THEN** the listener POSTs that normalized event to `/ingest/pfsense` with the configured API key/header.

#### Scenario: Listener does not write directly to database
- **WHEN** the listener receives and processes any packet
- **THEN** it does not open database connections, call direct DB helpers, or write directly to PostgreSQL.

### Requirement: Listener handles backend failures safely
The listener SHALL handle backend 4xx, backend 5xx, timeout, and network failures without crashing or leaking secrets or raw payloads.

#### Scenario: Backend 4xx response is logged safely
- **WHEN** `/ingest/pfsense` returns a 4xx response
- **THEN** the listener logs safe structured status metadata and does not log API keys or full raw payloads.

#### Scenario: Backend 5xx response is logged safely
- **WHEN** `/ingest/pfsense` returns a 5xx response
- **THEN** the listener logs safe structured status metadata and continues running.

#### Scenario: Network failure does not crash listener
- **WHEN** forwarding to `/ingest/pfsense` times out or fails at the network layer
- **THEN** the listener logs safe structured failure metadata and continues running.

### Requirement: Listener does not retry UDP input by default
The listener SHALL use no-retry/drop-after-attempt behavior for UDP packet forwarding by default unless a later bounded durability design is explicitly specified.

#### Scenario: Forward failure is not retried unboundedly
- **WHEN** backend forwarding fails for a parsed event
- **THEN** the listener records safe failure telemetry and does not enqueue unbounded retries in memory or on disk.

### Requirement: Listener applies rate limiting and backpressure
The listener SHALL provide configurable global and per-source rate limiting or backpressure behavior to prevent unbounded parsing, forwarding, logging, or storage pressure.

#### Scenario: Rate limit behavior is testable
- **WHEN** packet volume exceeds configured limits
- **THEN** the listener drops or defers excess packets according to a deterministic, testable policy and logs safe rate-limit counters.

#### Scenario: Rate-limited packet is not forwarded
- **WHEN** a packet is rejected by listener rate limiting
- **THEN** it is not parsed or forwarded to `/ingest/pfsense`.

### Requirement: Listener emits structured safe logs and metrics
The listener SHALL emit structured safe logs and/or metrics for accepted packets, rejected source IPs, oversized packets, parser failures, rate-limited packets, forwarded events, backend failures, startup, shutdown, and configuration summary.

#### Scenario: Rejected packet logging avoids raw payload retention
- **WHEN** a packet is rejected
- **THEN** logs include safe metadata such as reason, sender IP, packet length, and counters without dumping the full raw packet or raw syslog.

#### Scenario: Secrets are not logged
- **WHEN** the listener logs startup, forwarding, or failure details
- **THEN** logs do not include ingest API key values or other secrets.

### Requirement: Listener supports local synthetic packet testing
The listener SHALL support local synthetic packet testing without Azure NSG changes, VM firewall changes, live external exposure, or production pfSense traffic.

#### Scenario: Synthetic packet can exercise listener path
- **WHEN** a local test sends a synthetic authorized pfSense packet to the configured listener port
- **THEN** the listener can parse and forward the normalized event to the configured local/backend route.

#### Scenario: Rejection cases can be tested locally
- **WHEN** local tests send unauthorized, oversized, malformed, or rate-limited packets
- **THEN** the listener exposes deterministic outcomes that can be asserted without external pfSense traffic.

### Requirement: Listener service deployment files follow existing daemon pattern
Future service files for the listener SHALL follow the existing operator-controlled daemon pattern, including systemd `Type=simple`, repo working directory, environment file configuration, safe journal logging, restart-on-failure behavior, graceful shutdown, and explicit install/update/rollback helper behavior.

#### Scenario: Listener can be started and stopped under systemd pattern
- **WHEN** future systemd files are implemented and installed by an operator
- **THEN** the listener can be started, stopped, restarted, and logged using the existing systemd-style daemon pattern.

#### Scenario: Install helper does not auto-start by default
- **WHEN** a future listener install helper is run without explicit start flags
- **THEN** it installs or updates service files without enabling or starting the listener.

### Requirement: Listener configuration uses environment variables
The listener SHALL support environment variable configuration for bind host, port, pfSense source IP allow-list, backend ingest URL, ingest API key/header name, packet size limit, rate limits, timeout, log level, and test-mode/max-loop controls where applicable.

#### Scenario: Environment config controls listener behavior
- **WHEN** environment variables are provided for listener configuration
- **THEN** the listener uses those values for binding, authorization, parser bounds, forwarding, logging, and test controls.

### Requirement: Listener implementation excludes route, parser redesign, detections, and exposure
This change SHALL NOT implement the Flask `/ingest/pfsense` route, parser redesign, detection rules, SOAR/playbook tuning, Azure NSG rules, VM firewall rules, live external exposure, uncle/pfSense configuration, production traffic collection, or direct database writes.

#### Scenario: Listener spec does not implement cloud or VM firewall exposure
- **WHEN** the listener daemon is implemented later
- **THEN** no Azure NSG rule, VM firewall rule, live external exposure, or production traffic collection is performed by this child spec.

#### Scenario: Listener spec does not implement route or detection behavior
- **WHEN** the listener daemon is implemented later
- **THEN** it consumes the parser contract and forwards to the backend route without adding Flask route behavior, detection rules, or SOAR/playbook tuning.
