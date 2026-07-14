## ADDED Requirements

### Requirement: pfSense alerts SHALL persist a normalized target context snapshot
The system SHALL persist a read-only `target_context` object under `alerts.context` for pfSense firewall alerts. `events.raw_payload` SHALL remain the authoritative event source, and the persisted snapshot SHALL contain only the minimal investigation summary needed by the UI.

#### Scenario: Single-target pfSense alert persists exact target fields
- **WHEN** the system creates a `pfsense_firewall_repeated_deny` or `pfsense_firewall_suspicious_allow` alert
- **THEN** `alerts.context.target_context` SHALL include `mode`, `destination_ip`, `destination_port`, `protocol`, `firewall_action`, `attempts`, `first_seen`, `last_seen`, and any available `interface` and `direction` fields

#### Scenario: Multi-target pfSense alert persists aggregate target fields
- **WHEN** the system creates a `pfsense_firewall_port_scan` or `pfsense_firewall_noisy_source` alert
- **THEN** `alerts.context.target_context` SHALL use aggregate fields and SHALL NOT fabricate one exact destination target when the alert window spans multiple targets

### Requirement: pfSense target context SHALL be deterministic per alert family
The system SHALL standardize `target_context` by alert family so downstream UI code can render it without alert-type-specific message parsing.

#### Scenario: Repeated deny and suspicious allow use single-target mode
- **WHEN** the system persists `target_context` for `pfsense_firewall_repeated_deny` or `pfsense_firewall_suspicious_allow`
- **THEN** `target_context.mode` SHALL be `single_target`

#### Scenario: Port scan and noisy source use aggregate-target mode
- **WHEN** the system persists `target_context` for `pfsense_firewall_port_scan` or `pfsense_firewall_noisy_source`
- **THEN** `target_context.mode` SHALL be `aggregate_targets`

#### Scenario: Multi-target aggregation exposes top-target evidence without inventing precision
- **WHEN** the system persists `target_context` for `pfsense_firewall_port_scan` or `pfsense_firewall_noisy_source`
- **THEN** it SHALL include `top_destination_ip`, `top_destination_port`, `attempts`, `first_seen`, and `last_seen`, and SHALL include `distinct_destination_count` and `distinct_port_count` where those aggregates are available

### Requirement: Existing alert APIs SHALL transport target context additively
The system SHALL expose `alerts.context.target_context` through the existing alert APIs and SHALL preserve the current top-level pfSense context fields used by existing consumers.

#### Scenario: Alert list payload exposes target context
- **WHEN** a client requests alerts containing pfSense firewall alerts
- **THEN** each returned pfSense alert SHALL include the additive `context.target_context` object when persisted

#### Scenario: Existing pfSense context fields remain available
- **WHEN** a client requests pfSense alert details or why-fired evidence
- **THEN** existing top-level pfSense context fields SHALL remain available and SHALL NOT be silently replaced by the nested `target_context`

### Requirement: Alert Details SHALL render pfSense target context read-only
The system SHALL render one compact `Target Context` section in `AlertDetailsPanel` for pfSense alerts only, using the persisted `context.target_context` snapshot.

#### Scenario: Single-target fields render as exact destination evidence
- **WHEN** `AlertDetailsPanel` renders a pfSense alert whose `target_context.mode` is `single_target`
- **THEN** it SHALL label and display exact destination evidence including destination IP and destination port where present

#### Scenario: Aggregate fields render as top-target evidence
- **WHEN** `AlertDetailsPanel` renders a pfSense alert whose `target_context.mode` is `aggregate_targets`
- **THEN** it SHALL label and display top-target and distinct-count fields as aggregate evidence rather than as one exact destination

#### Scenario: Missing target evidence renders unavailable state
- **WHEN** `AlertDetailsPanel` renders a pfSense alert with no usable `target_context` evidence
- **THEN** it SHALL show `Unavailable`

#### Scenario: Non-pfSense alerts do not render target context
- **WHEN** `AlertDetailsPanel` renders a non-pfSense alert
- **THEN** it SHALL NOT render the `Target Context` section
