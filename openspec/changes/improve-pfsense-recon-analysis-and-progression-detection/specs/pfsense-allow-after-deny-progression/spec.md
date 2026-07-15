## ADDED Requirements

### Requirement: The system SHALL detect same-source inbound allow-after-deny progression as a distinct pfSense behavior
The system SHALL add one narrowly defined pfSense alert family for the case where the same external source first produces qualifying firewall denies and later reaches a firewall allow within a bounded time window.

#### Scenario: Same source with prior denies and later allow qualifies
- **WHEN** the same external source IP produces qualifying firewall denies and later produces an inbound firewall allow within the progression window
- **THEN** the system SHALL evaluate that sequence for `pfsense_firewall_allow_after_deny`

#### Scenario: Outbound allow does not qualify
- **WHEN** the later allow event is outbound rather than inbound
- **THEN** the system SHALL NOT create a `pfsense_firewall_allow_after_deny` alert from that sequence

### Requirement: Allow-after-deny matching SHALL require source continuity and target/service relationship
The system SHALL require the same source IP and a bounded target/service relationship rather than treating any later allow as progression.

#### Scenario: Medium progression can match the same service within the protected range
- **WHEN** the same external source IP later reaches an inbound allow to the same destination port and protocol within the same protected destination range after qualifying denies
- **THEN** the sequence SHALL be eligible for a `medium` allow-after-deny alert even if the exact destination IP changed within that protected range

#### Scenario: High progression requires exact target/service or stronger corroboration
- **WHEN** the same external source IP later reaches an inbound allow to the same destination IP and same destination port and protocol after qualifying denies
- **THEN** the sequence SHALL be eligible for `high` allow-after-deny severity if the remaining requirements in this capability are met

#### Scenario: Unrelated destination or service change does not qualify
- **WHEN** the later allow reaches a different service signature without the required same-target or same-service relationship
- **THEN** the system SHALL NOT create a `pfsense_firewall_allow_after_deny` alert from that sequence

### Requirement: Allow-after-deny SHALL require a minimum deny count and a bounded progression window
The system SHALL define exact minimum deny-count and timing rules so one isolated deny followed by an allow does not create this alert family.

#### Scenario: Medium progression threshold
- **WHEN** a source has at least 3 qualifying prior denies and later reaches a matching inbound allow within 30 minutes
- **THEN** the system SHALL be able to create a `medium` `pfsense_firewall_allow_after_deny` alert

#### Scenario: High progression threshold
- **WHEN** a source has at least `PFSENSE_REPEATED_DENY_THRESHOLD` qualifying prior denies and later reaches a high-confidence matching inbound allow within 30 minutes
- **THEN** the system SHALL be able to create a `high` `pfsense_firewall_allow_after_deny` alert

#### Scenario: Single prior deny does not qualify
- **WHEN** only one qualifying prior deny exists before the later allow
- **THEN** the system SHALL NOT create a `pfsense_firewall_allow_after_deny` alert

### Requirement: Allow-after-deny severity SHALL reflect progression confidence rather than reputation alone
The system SHALL assign `medium` or `high` severity from the deny-to-allow progression evidence and SHALL not use reputation alone to determine severity.

#### Scenario: Matching service progression without exact-target proof is Medium
- **WHEN** a source meets the minimum progression threshold but the later allow only matches the same service within the protected range rather than the exact destination IP
- **THEN** the resulting `pfsense_firewall_allow_after_deny` alert SHALL be `medium`

#### Scenario: Exact-target or sensitive-service progression is High
- **WHEN** a source meets the high progression threshold and the later allow reaches the same exact destination target and service, or reaches a sensitive service with same-source deny history
- **THEN** the resulting `pfsense_firewall_allow_after_deny` alert SHALL be `high`

#### Scenario: Reputation alone does not create High
- **WHEN** a progression candidate carries elevated reputation but does not meet the high-confidence progression conditions in this capability
- **THEN** the resulting `pfsense_firewall_allow_after_deny` alert SHALL NOT become `high` from reputation alone

### Requirement: Allow-after-deny SHALL preserve both deny and allow evidence
The system SHALL preserve the later allow event together with the relevant preceding deny evidence as part of the alert context.

#### Scenario: Progression context includes deny and allow evidence
- **WHEN** the system creates a `pfsense_firewall_allow_after_deny` alert
- **THEN** the resulting context SHALL preserve the allow target evidence together with bounded prior-deny counts, timing, and matching-service or target information

#### Scenario: Related-event inspection can show the progression sequence
- **WHEN** an analyst requests related underlying events for a `pfsense_firewall_allow_after_deny` alert
- **THEN** the system SHALL provide a bounded related-event path that includes both the later allow and the qualifying prior denies

### Requirement: Allow-after-deny response behavior SHALL remain approval-gated and bounded
The system SHALL treat allow-after-deny as an investigation or approved-containment signal without autonomous blocking.

#### Scenario: Medium progression remains investigation-only
- **WHEN** a `pfsense_firewall_allow_after_deny` alert is `medium`
- **THEN** it SHALL NOT automatically create an incident, request `block_ip` approval, or trigger autonomous containment

#### Scenario: High progression is incident-eligible and approval-gated
- **WHEN** a `pfsense_firewall_allow_after_deny` alert is `high`
- **THEN** it SHALL be eligible for a source-specific incident and MAY enter an approval-gated containment path, but SHALL NOT bypass approval before `block_ip`

#### Scenario: Allow-after-deny never auto-blocks
- **WHEN** the system creates any `pfsense_firewall_allow_after_deny` alert
- **THEN** it SHALL NOT automatically execute `block_ip` without an approval-gated path
