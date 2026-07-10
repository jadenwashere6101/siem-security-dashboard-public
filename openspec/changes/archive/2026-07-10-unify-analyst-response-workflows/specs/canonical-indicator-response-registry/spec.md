## ADDED Requirements

### Requirement: Canonical indicator identity and disposition
The system SHALL maintain one canonical registry identity per normalized indicator type and value and SHALL expose its current disposition separately from its requested action and enforcement outcome.

#### Scenario: Same IP is selected from multiple surfaces
- **WHEN** the same normalized IP is acted upon from alerts, Threat Hunt, playbooks, queue work, or the Blocklist form
- **THEN** the system SHALL reuse one registry identity while retaining a distinct provenance event for every request

#### Scenario: Future indicator type is introduced
- **WHEN** the registry later accepts a domain, URL, hash, username, or device identifier
- **THEN** its identity SHALL remain namespaced by indicator type and SHALL NOT collide with an equal-looking value of another type

### Requirement: Append-only response history and provenance
Every response request and terminal or transitional outcome SHALL append an auditable registry event with actor, origin surface, reason, timestamps, and all available related resource identifiers.

#### Scenario: Playbook block request awaits approval
- **WHEN** a playbook requests `block_ip` and approval is required
- **THEN** the registry SHALL record the requested action and awaiting-approval state linked to the playbook execution, step, approval, alert or incident, and canonical outcome

#### Scenario: Historical provenance is incomplete
- **WHEN** a backfilled record cannot be linked with certainty
- **THEN** the registry SHALL identify the relationship as inferred or unknown and SHALL NOT manufacture an actor, source, or success outcome

### Requirement: Idempotent tracking-only blocklist behavior
Every authorized successful `block_ip` command SHALL create or converge on one active SIEM Blocklist tracking record and SHALL explicitly state that no firewall or host enforcement occurred.

#### Scenario: First block request succeeds
- **WHEN** a valid unprotected IP receives an authorized `block_ip` command
- **THEN** the system SHALL create an active Blocklist record, append tracking-only outcome/history, and return the Blocklist and registry identifiers atomically

#### Scenario: Active tracked IP is requested again
- **WHEN** another valid request targets an IP with an active Blocklist record
- **THEN** the system SHALL reuse the active record, append new provenance, and return an idempotent successful tracking result rather than creating a duplicate or reporting firewall enforcement

#### Scenario: Target is protected or invalid
- **WHEN** `block_ip` targets a protected, private, internal, malformed, or otherwise prohibited address
- **THEN** the system SHALL reject it, create no active Blocklist record, and append a truthful rejected outcome where safe

### Requirement: Durable monitoring and escalation
The system SHALL represent monitoring and escalation as durable internal SIEM dispositions with observable state and SHALL NOT report success for log-only behavior.

#### Scenario: Monitoring is selected
- **WHEN** an authorized analyst or automation selects `monitor`
- **THEN** an active watch disposition with reason, owner/origin, start time, and optional expiry SHALL be visible in the registry

#### Scenario: Escalation is selected
- **WHEN** an authorized analyst selects escalation
- **THEN** the configured internal handoff SHALL update or create the required priority, incident, assignment, or escalation record before the outcome is marked escalated

### Requirement: Independent lifecycle semantics
Alert, incident, registry disposition, approval, queue, playbook, and Blocklist statuses SHALL remain distinct and the system SHALL explain rather than silently synchronize them.

#### Scenario: Alert resolves while incident stays open
- **WHEN** an analyst resolves a linked alert without changing its incident
- **THEN** both states SHALL remain valid and the UI SHALL disclose the open linked incident and offer a contextual review handoff
