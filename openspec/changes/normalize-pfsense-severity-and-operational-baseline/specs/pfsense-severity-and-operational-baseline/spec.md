## ADDED Requirements

### Requirement: pfSense detector severity SHALL reflect operational urgency rather than routine firewall noise
The system SHALL normalize severity for the existing pfSense detector families so routine commodity internet noise does not surface as high-urgency operational work by default.

#### Scenario: Port scan remains medium for routine commodity scanning
- **WHEN** pfSense firewall scan activity reflects ordinary low-confidence internet scanning without corroborating breadth, persistence, or reputation
- **THEN** the resulting alert SHALL default to `medium` severity rather than `high` or `critical`

#### Scenario: Repeated deny remains low or medium unless stronger context exists
- **WHEN** pfSense repeated deny activity is dominated by inbound WAN deny noise
- **THEN** the resulting alert SHALL remain `low` or `medium` and SHALL rarely become `high`

#### Scenario: Suspicious allow remains the strongest current pfSense family
- **WHEN** pfSense allows inbound traffic to a sensitive destination port with corroborating repetition, breadth, or reputation
- **THEN** the resulting alert SHALL escalate to `high`, and `critical` SHALL remain reserved for future rule families rather than this normalization change

#### Scenario: Noisy source stays informational
- **WHEN** the system creates a `pfsense_firewall_noisy_source` alert
- **THEN** the alert SHALL remain `low` severity and SHALL NOT become a high-urgency incident source

### Requirement: Operational pfSense views SHALL default to a shared tuning baseline
The system SHALL support a configurable tuning baseline timestamp and SHALL default approved operational pfSense surfaces to showing records created since that baseline.

#### Scenario: Operational views default to since-tuning data
- **WHEN** an analyst opens Dashboard, Recent Alerts, Incidents, SOC Command Center, or Detection Health
- **THEN** the approved pfSense operational counts and views SHALL default to a `Since Tuning` scope derived from the configured baseline timestamp

#### Scenario: Analysts can view all history explicitly
- **WHEN** an analyst switches the approved operational scope from `Since Tuning` to `All History`
- **THEN** the system SHALL include pre-baseline pfSense alerts and incidents without altering stored historical records

### Requirement: Baseline filtering SHALL be consistent across backend operational contracts
The system SHALL apply one shared backend baseline contract to the approved alert, incident, and pfSense operational aggregate routes so current counts remain internally consistent.

#### Scenario: Dashboard and recent-alert counts use the same baseline semantics
- **WHEN** the system returns alert summary metrics and recent pfSense alerts for the same operational scope
- **THEN** both responses SHALL apply the same baseline filter semantics

#### Scenario: Incident pressure and detection health use the same baseline semantics
- **WHEN** the system returns incident pressure metrics and pfSense detection health for the same operational scope
- **THEN** both responses SHALL apply the same baseline filter semantics

### Requirement: Historical pfSense records SHALL remain intact and clearly labeled
The system SHALL preserve all historical pfSense alerts and incidents while clearly indicating when a shown record predates the tuning baseline.

#### Scenario: Pre-tuning alerts remain viewable without mutation
- **WHEN** an analyst views a pfSense alert created before the tuning baseline
- **THEN** the alert SHALL remain searchable and viewable and SHALL include a clear legacy/pre-tuning indicator without rewriting its stored severity or lifecycle

#### Scenario: Pre-tuning incidents remain viewable without bulk closure
- **WHEN** an analyst views an incident linked to pfSense alerts created before the tuning baseline
- **THEN** the incident SHALL remain intact and SHALL be distinguishable from current operational records without deletion, archival, or forced closure

### Requirement: Incident creation SHALL continue to derive from resulting alert severity
The system SHALL preserve the existing alert-severity-to-incident mapping model while ensuring normalized pfSense severity reduces false operational urgency.

#### Scenario: Lower normalized pfSense severity avoids unnecessary incident creation
- **WHEN** a pfSense alert normalizes to `low` or `medium`
- **THEN** the existing incident-creation path SHALL NOT create or link a new incident solely from that alert

#### Scenario: High normalized pfSense severity still creates operational incidents
- **WHEN** a pfSense alert normalizes to `high` or `critical` under the approved detector logic
- **THEN** the existing incident-creation path SHALL continue to create or link incidents using the existing severity-to-priority mapping
