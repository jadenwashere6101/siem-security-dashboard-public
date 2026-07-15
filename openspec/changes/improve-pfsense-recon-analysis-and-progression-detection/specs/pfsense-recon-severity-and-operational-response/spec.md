## ADDED Requirements

### Requirement: pfSense reputation SHALL strengthen evidence without independently creating High severity
The system SHALL treat external reputation as supporting context for pfSense detections, not as an independent reason to convert a minimum-threshold commodity scan into `high`. No pfSense alert family SHALL become `critical`.

#### Scenario: Reputation alone cannot create High for inbound repeated deny
- **WHEN** an inbound `pfsense_firewall_repeated_deny` candidate meets only the base repeated-deny threshold and carries `reputation_score >= 70`
- **THEN** the resulting alert SHALL NOT be assigned `high` severity from reputation alone

#### Scenario: Reputation alone cannot create High for ordinary port scan breadth
- **WHEN** a `pfsense_firewall_port_scan` candidate carries `reputation_score >= 70` but only meets the base breadth trigger without strong destination or port breadth
- **THEN** the resulting alert SHALL NOT be assigned `high` severity from reputation alone

#### Scenario: pfSense families never become Critical
- **WHEN** the system creates any pfSense alert in this capability
- **THEN** the inserted severity SHALL be `low`, `medium`, or `high`, and SHALL NOT be `critical`

### Requirement: pfSense repeated deny severity SHALL reflect direction and sustained behavior
The system SHALL assign `pfsense_firewall_repeated_deny` severity from observed behavior against this environment rather than from reputation alone.

#### Scenario: Inbound commodity repeated deny stays Low at the base threshold
- **WHEN** inbound external-source repeated deny activity reaches the configured repeated-deny threshold on one target/service tuple without corroborating progression or outbound/internal-host context
- **THEN** the resulting `pfsense_firewall_repeated_deny` alert SHALL be `low`

#### Scenario: Inbound sustained repeated deny becomes Medium
- **WHEN** inbound external-source repeated deny activity on one target/service tuple reaches at least `threshold * PFSENSE_SEVERITY_ESCALATION_MULTIPLIER`
- **THEN** the resulting `pfsense_firewall_repeated_deny` alert SHALL be `medium`

#### Scenario: Outbound repeated deny becomes High
- **WHEN** repeated deny activity originates from an internal host toward external destinations and meets the configured repeated-deny threshold
- **THEN** the resulting `pfsense_firewall_repeated_deny` alert SHALL be `high`

### Requirement: pfSense port scan severity SHALL require meaningful breadth or corroboration for High
The system SHALL keep the base pfSense port-scan detector visible at `medium`, and SHALL reserve `high` for materially strong breadth or corroborating behavior against this environment.

#### Scenario: Base port scan trigger remains Medium
- **WHEN** a source reaches either the configured distinct-port threshold or the configured distinct-destination-host threshold
- **THEN** the resulting `pfsense_firewall_port_scan` alert SHALL be `medium` unless a High-severity condition in this capability is also met

#### Scenario: Strong stand-alone breadth becomes High
- **WHEN** a pfSense port-scan candidate reaches `distinct_port_count >= threshold * 3` or `distinct_destination_count >= host_threshold * 3`
- **THEN** the resulting `pfsense_firewall_port_scan` alert SHALL be `high`

#### Scenario: Reputation can strengthen but not replace structural breadth
- **WHEN** a pfSense port-scan candidate carries `reputation_score >= 70` and reaches `distinct_port_count >= threshold * 2` or `distinct_destination_count >= host_threshold * 2`
- **THEN** the resulting `pfsense_firewall_port_scan` alert SHALL be `high`

#### Scenario: Reputation without stronger breadth remains Medium
- **WHEN** a pfSense port-scan candidate carries `reputation_score >= 70` but remains below `threshold * 2` distinct ports and below `host_threshold * 2` distinct destination hosts
- **THEN** the resulting `pfsense_firewall_port_scan` alert SHALL remain `medium`

### Requirement: pfSense suspicious allow severity SHALL require corroboration for High
The system SHALL treat `pfsense_firewall_suspicious_allow` as a strong investigation signal while requiring corroborating behavior before assigning `high`.

#### Scenario: Single qualifying allow remains Medium
- **WHEN** one inbound allow to a sensitive service qualifies for `pfsense_firewall_suspicious_allow` without repeated events, multi-port corroboration, or allow-after-deny progression
- **THEN** the resulting alert SHALL be `medium`

#### Scenario: Repeated or multi-port suspicious allow becomes High
- **WHEN** a `pfsense_firewall_suspicious_allow` candidate reaches `event_count >= high_confidence_repeat_threshold` or `distinct_sensitive_port_count >= distinct_port_escalation_threshold`
- **THEN** the resulting alert SHALL be `high`

#### Scenario: Reputation alone does not create High suspicious allow
- **WHEN** a single qualifying suspicious-allow event carries `reputation_score >= 70` but does not meet any corroborating condition in this capability
- **THEN** the resulting alert SHALL remain `medium`

### Requirement: pfSense noisy source SHALL remain informational
The system SHALL preserve `pfsense_firewall_noisy_source` as a low-severity suppression-focused signal rather than an incident or containment source.

#### Scenario: Noisy source remains Low
- **WHEN** the system creates a `pfsense_firewall_noisy_source` alert
- **THEN** the alert SHALL be `low`

#### Scenario: Noisy source never drives incidents or approvals
- **WHEN** a `pfsense_firewall_noisy_source` alert exists without another stronger pfSense alert for the same source
- **THEN** it SHALL NOT create an automatic incident or block approval

### Requirement: pfSense incident creation SHALL follow operational actionability rather than one-source-one-incident behavior
The system SHALL preserve underlying alerts while limiting automatic pfSense incidents to source-specific or aggregate behaviors that are operationally actionable.

#### Scenario: Low and Medium pfSense alerts do not auto-create incidents
- **WHEN** a pfSense alert in this capability is `low` or `medium`
- **THEN** the automatic incident path SHALL NOT create or link a new incident from that alert alone

#### Scenario: Source-specific High suspicious behavior creates an incident
- **WHEN** a `pfsense_firewall_suspicious_allow` or `pfsense_firewall_allow_after_deny` alert is `high`
- **THEN** the automatic incident path SHALL create or link a source-specific incident for that alert

#### Scenario: Commodity distributed recon does not create per-source incidents
- **WHEN** a `pfsense_firewall_port_scan` or inbound `pfsense_firewall_repeated_deny` alert is enrolled into an active distributed reconnaissance aggregate with coordination status `not_established` or `possible`
- **THEN** the automatic incident path SHALL NOT create a separate per-source incident solely from that member alert

### Requirement: pfSense containment eligibility SHALL be narrower than High severity
The system SHALL separate containment eligibility from severity so routine commodity reconnaissance does not generate approval-gated `block_ip` actions per source.

#### Scenario: Commodity distributed recon is not containment-eligible
- **WHEN** a pfSense alert is classified as routine distributed commodity reconnaissance and enrolled into a distributed reconnaissance aggregate
- **THEN** it SHALL NOT automatically request a `block_ip` approval from that classification alone

#### Scenario: Source-specific High progression remains containment-eligible
- **WHEN** a `pfsense_firewall_suspicious_allow`, `pfsense_firewall_allow_after_deny`, or outbound/internal-host `pfsense_firewall_repeated_deny` alert is `high`
- **THEN** the system MAY route it into an approval-gated containment playbook, and SHALL NOT bypass approval before `block_ip`

### Requirement: Post-fix pfSense operations SHALL remain separable from pre-fix history
The system SHALL preserve historical pfSense artifacts and SHALL allow operators to advance the pfSense tuning baseline after deployment so post-fix operational views are distinguishable from pre-fix noise.

#### Scenario: Historical pfSense artifacts remain unchanged
- **WHEN** this capability is deployed later
- **THEN** existing pfSense alerts, incidents, approvals, and statuses SHALL remain intact and SHALL NOT be rewritten or deleted

#### Scenario: Operators can distinguish pre-fix from post-fix pfSense behavior
- **WHEN** the pfSense tuning baseline is advanced after deployment
- **THEN** operational views that already support pfSense baseline scoping SHALL be able to distinguish pre-fix and post-fix pfSense artifacts without mutating historical rows
