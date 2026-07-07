## ADDED Requirements

### Requirement: Firewall event taxonomy is explicit after ingestion
The system SHALL treat already-ingested pfSense events with `source="pfsense"` and `source_type="firewall"` as firewall telemetry and SHALL use explicit taxonomy values for `firewall_block`, `firewall_allow`, and derived firewall detection alerts.

#### Scenario: Firewall block event is recognized
- **WHEN** an already-ingested pfSense firewall event has `event_type="firewall_block"` or `raw_payload.action="block"`
- **THEN** detection logic recognizes it as blocked firewall traffic without requiring parser, listener, route, deployment, or runtime behavior.

#### Scenario: Firewall allow event is recognized
- **WHEN** an already-ingested pfSense firewall event has `event_type="firewall_allow"` or `raw_payload.action="pass"`
- **THEN** detection logic recognizes it as allowed firewall traffic without treating the allow as inherently malicious.

### Requirement: Firewall block and allow behavior is differentiated
The system SHALL differentiate routine blocked traffic from risky allowed traffic and SHALL NOT assign high severity solely because a firewall event exists.

#### Scenario: Isolated block remains low signal
- **WHEN** a single inbound `firewall_block` event has no reputation hit, protected target, scan breadth, repetition, or cross-source correlation
- **THEN** the system stores/counts the event and either produces no alert or a low/informational alert according to alert policy.

#### Scenario: Contextual allow may become alert-worthy
- **WHEN** a `firewall_allow` event involves sensitive destination ports, unexpected direction/interface, known-bad source context, public-to-internal exposure, or related suspicious activity
- **THEN** the system may produce a firewall alert with severity based on the supporting context.

### Requirement: Firewall events map to actionable alert types
The system SHALL map qualifying firewall events to specific alert types rather than generic firewall alerts.

#### Scenario: Repeated deny alert is emitted
- **WHEN** blocked traffic from the same source exceeds the repeated-deny threshold within the configured time window
- **THEN** the system emits a `firewall_repeated_deny` alert with aggregate counts and representative firewall fields.

#### Scenario: Port scan alert is emitted
- **WHEN** blocked or suspicious traffic from the same source touches distinct destination ports and/or destinations above the configured threshold within the configured time window
- **THEN** the system emits a `firewall_port_scan` alert.

#### Scenario: Suspicious allow alert is emitted
- **WHEN** allowed firewall traffic meets configured suspicious-allow criteria
- **THEN** the system emits a `firewall_suspicious_allow` alert rather than treating all allows as benign.

### Requirement: Firewall severity guidance is deterministic
The system SHALL assign firewall alert severity using documented criteria that consider action, volume, breadth, protected target, reputation, direction, interface, sensitive port, and correlation evidence.

#### Scenario: Routine isolated block is low severity
- **WHEN** blocked traffic is isolated and lacks escalation criteria
- **THEN** severity is `low` or below according to local alert policy.

#### Scenario: Scan breadth increases severity
- **WHEN** traffic from one source reaches scan thresholds across multiple ports or destinations
- **THEN** severity is at least `medium` and may become `high` when protected targets, known-bad context, or other correlation exists.

#### Scenario: High-confidence suspicious allow escalates
- **WHEN** an allowed firewall event involves a known-bad source, sensitive destination, unexpected inbound direction, or correlated compromise evidence
- **THEN** severity is `high` unless implementation policy documents a lower severity.

### Requirement: Firewall correlation opportunities are represented
The system SHALL support correlation opportunities for firewall events using source IP, destination IP, destination port, protocol, action, direction, interface, time windows, source reputation, and nearby non-firewall alerts.

#### Scenario: Firewall event correlates with source reputation
- **WHEN** a firewall event source IP has known-bad or high-risk reputation context
- **THEN** alert context includes that correlation and severity may increase.

#### Scenario: Firewall event correlates with other detections
- **WHEN** firewall activity occurs near failed login, web probe, honeypot, behavioral reputation, or targeted-correlation alerts involving the same source or target
- **THEN** the system may emit or enrich a `firewall_correlated_activity` alert.

### Requirement: Port scan behavior uses bounded breadth windows
The system SHALL detect port scan behavior using bounded time windows and distinct destination ports and/or destination hosts derived from normalized firewall fields.

#### Scenario: Port breadth threshold is met
- **WHEN** a source contacts more than the configured number of distinct destination ports within the configured time window
- **THEN** a port scan alert is produced with distinct-port count, event count, first-seen time, and last-seen time.

#### Scenario: Port scan does not alert on a single repeated port
- **WHEN** one source repeatedly hits only one destination port without other escalation context
- **THEN** the behavior is handled as repeated deny or noisy-source logic rather than port scan breadth.

### Requirement: Repeated deny detection aggregates duplicates
The system SHALL detect repeated deny behavior and aggregate duplicate blocked events by source, destination, destination port, protocol, and bounded time window.

#### Scenario: Repeated deny aggregates into one alert
- **WHEN** repeated blocked events from the same source to the same destination and port exceed the configured threshold
- **THEN** the system produces one aggregate alert per suppression window instead of one alert per packet.

#### Scenario: Aggregate alert includes repeated deny context
- **WHEN** a repeated deny alert is produced
- **THEN** it includes event count, first-seen time, last-seen time, source IP, destination IP, destination port, protocol, action, interface, and direction when available.

### Requirement: Noisy source suppression is observable
The system SHALL suppress duplicate low-value firewall alerts from noisy sources while retaining counters and escalation conditions.

#### Scenario: Noisy source is suppressed
- **WHEN** one source repeatedly produces equivalent low-severity firewall events beyond the suppression threshold
- **THEN** duplicate alerts are suppressed for the configured window and suppression counters remain available for alert context or metrics.

#### Scenario: Suppression breaks on escalation
- **WHEN** a suppressed source later meets port scan, protected target, known-bad reputation, suspicious allow, or cross-source correlation criteria
- **THEN** the system may emit a new higher-severity alert despite prior suppression.

### Requirement: MITRE mappings are evidence based
The system SHALL attach MITRE ATT&CK mapping only to firewall detections with sufficient evidence and SHALL avoid assigning techniques to routine isolated firewall noise.

#### Scenario: Port scan maps to reconnaissance
- **WHEN** a `firewall_port_scan` alert is emitted
- **THEN** MITRE mapping includes reconnaissance-oriented context such as network service discovery where supported by the existing MITRE model.

#### Scenario: Routine block has no forced MITRE mapping
- **WHEN** an isolated routine `firewall_block` event is stored or alerted at low severity
- **THEN** the system does not require a MITRE mapping.

### Requirement: Firewall alerts include expected fields
Firewall alerts SHALL include expected fields needed for investigation, correlation, and SOAR decisions.

#### Scenario: Firewall alert fields are populated
- **WHEN** a firewall alert is emitted
- **THEN** it includes alert type, severity, source, source type, source IP, destination IP when available, destination port when available, protocol, action, interface, direction, event count, first-seen time, last-seen time, message, MITRE mapping when applicable, suppression state when applicable, and raw firewall context safe for display.

### Requirement: Firewall alerts map to expected response actions
The system SHALL map firewall detections to explicit `response_action` values appropriate for severity and confidence.

#### Scenario: Low signal firewall event uses monitor action
- **WHEN** a routine low-signal firewall event is represented as an alert
- **THEN** its `response_action` is `monitor_only` or equivalent non-disruptive behavior.

#### Scenario: Enrichment action is queued for actionable firewall alert
- **WHEN** a medium or higher firewall alert is emitted
- **THEN** expected `response_action` values may include `enrich_source_ip`, `create_incident`, or `notify_soc`.

#### Scenario: Block action requires approval path
- **WHEN** a firewall alert recommends blocking a source IP or changing firewall policy
- **THEN** expected `response_action` values include `queue_block_source_ip` or `request_firewall_block_approval` and the action follows approval workflow expectations.

#### Scenario: Suppression action is explicit
- **WHEN** noisy source suppression is applied
- **THEN** expected `response_action` may include `suppress_noisy_source` with visible suppression context.

### Requirement: Playbook triggers respect confidence and severity
The system SHALL trigger SOAR playbooks for firewall alerts according to severity, confidence, and approval requirements.

#### Scenario: Read-only enrichment can trigger automatically
- **WHEN** a firewall alert meets enrichment criteria
- **THEN** read-only source-IP enrichment playbooks may trigger automatically if existing SOAR policy permits.

#### Scenario: High-confidence firewall alert can trigger incident workflow
- **WHEN** a firewall port scan, repeated deny, suspicious allow, or correlated activity alert reaches high confidence or high severity
- **THEN** incident creation and SOC notification playbooks may trigger according to existing playbook policy.

### Requirement: Approval workflow protects disruptive firewall actions
The system SHALL require approval workflow for firewall response actions that are destructive, externally visible, or change blocking/firewall policy unless existing policy explicitly authorizes automatic execution.

#### Scenario: Block recommendation waits for approval
- **WHEN** a firewall alert recommends blocking a source IP
- **THEN** the system queues or requests approval before executing a block action.

#### Scenario: Rejected approval does not execute block
- **WHEN** an approval request for a firewall block is rejected or expires
- **THEN** the block action is not executed and the alert/queue context records the outcome.

### Requirement: Firewall detection validation avoids runtime and deployment scope
Validation for this change SHALL use local/unit/integration-style inputs against already-ingested event structures and SHALL NOT require parser implementation, UDP listener behavior, `/ingest/pfsense`, Azure NSG, VM firewall, systemd, deployment, runtime validation, live pfSense traffic, or uncle handoff.

#### Scenario: Detection validation uses normalized events
- **WHEN** firewall detection validation runs
- **THEN** it supplies normalized pfSense firewall event structures directly through detection/correlation test paths rather than raw syslog, UDP packets, or live routes.

#### Scenario: Scope exclusions remain enforced
- **WHEN** this change is implemented later
- **THEN** it does not implement parser, UDP listener, `/ingest/pfsense`, Azure NSG, VM firewall, systemd, deployment, runtime validation, or uncle handoff behavior.
