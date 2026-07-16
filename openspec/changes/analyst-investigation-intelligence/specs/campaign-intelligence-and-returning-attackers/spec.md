## ADDED Requirements

### Requirement: Campaign intelligence SHALL create investigation objects without creating alert spam
The system SHALL support campaign intelligence as a durable investigation object and SHALL prefer enrichment, grouping, and visible reasoning over creating additional alerts.

#### Scenario: Campaign context does not require new alerts
- **WHEN** related attacker activity can be explained through a campaign object, enriched alert context, recon activity, or incident linkage
- **THEN** the system SHALL avoid creating a separate campaign alert by default

### Requirement: Campaigns SHALL focus on the target as well as the attacker
The system SHALL determine campaign relationships from target-centered evidence and SHALL NOT rely only on one attacker IP recurring.

#### Scenario: Same destination and service support campaign linkage
- **WHEN** multiple related activities repeatedly target the same destination, destination range, or protected service set across time
- **THEN** the system SHALL be able to group them into the same campaign investigation object

#### Scenario: Returning attacker alone is insufficient
- **WHEN** one attacker IP returns without stronger repeated target, service, timing, or progression evidence
- **THEN** the system SHALL treat that fact as context and SHALL NOT treat it as sufficient campaign proof on its own

### Requirement: Campaign reasoning SHALL be evidence-based and explainable
The system SHALL explain why a campaign relationship exists through visible evidence instead of opaque labels.

#### Scenario: Campaign evidence is visible
- **WHEN** a campaign object links related activity
- **THEN** the system SHALL explain the relationship through evidence such as recurring activity across days, rotating IPs, repeated timing intervals, beacon-like timing, subnet or ASN relationships, repeated destinations, repeated services, or progression

#### Scenario: Coordination is not overstated
- **WHEN** the evidence supports repeated related activity but not strong operator linkage
- **THEN** the system SHALL describe the campaign relationship in bounded language and SHALL NOT overclaim coordination

### Requirement: Returning attackers SHALL become investigation context
Returning attackers SHALL be surfaced as context on existing investigation objects and SHALL NOT become standalone alerts.

#### Scenario: Returning attacker context includes prior history
- **WHEN** an analyst views relevant activity tied to a returning attacker
- **THEN** the system SHALL be able to expose first seen, last seen, days observed, previous incidents, previous responses, campaign membership, repeated destinations, and repeated services when available

#### Scenario: Returning attacker context can raise Investigation Value
- **WHEN** returning-attacker history materially strengthens the investigative importance of current activity
- **THEN** the system SHALL be able to raise Investigation Value and explain the history that caused the increase

### Requirement: Campaign membership SHALL improve workflow navigation
Campaign membership SHALL give analysts clearer investigation pivots across alerts, incidents, recon activities, and target context.

#### Scenario: Analysts can pivot from a member object into the campaign
- **WHEN** an alert, incident, or recon activity belongs to a campaign
- **THEN** the system SHALL provide a bounded entry point to the campaign investigation object

#### Scenario: Campaign history is visible
- **WHEN** an analyst opens a campaign investigation object
- **THEN** the object SHALL summarize current status, history across days, representative member activity, repeated targets or services, and related incidents or responses

### Requirement: Campaign wording SHALL remain understandable at a glance
Campaign labels, badges, and reasons introduced by this capability SHALL be understandable at a glance and SHALL avoid unexplained jargon.

#### Scenario: Plain-English campaign summary
- **WHEN** the system summarizes a campaign
- **THEN** it SHALL prefer a short summary such as `Repeated probing of the same public services across three days` over vague or unexplained labels

