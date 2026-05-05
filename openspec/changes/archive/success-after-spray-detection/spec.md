# Successful Login After Password Spray Detection Spec

## Feature Overview

This change adds a higher-severity correlation rule that detects a successful login following password spraying activity from the same source IP.

The scope is intentionally phased and careful:
- verify the event stream includes usable `successful_login` events
- correlate password spraying behavior with a later or overlapping successful login from the same source IP
- create a new critical alert type
- reuse existing alert creation, MITRE enrichment, and duplicate-prevention patterns

This rule is intended to highlight potential credential compromise after a spraying campaign, not replace the underlying password spraying detector.

## Current State

- Password spraying detection already exists:
  - `alert_type: password_spraying_threshold`
  - MITRE:
    - `T1110.003`
    - `Password Spraying`
    - `Credential Access`
- Failed login events include username metadata.
- Geo enrichment works on ingest.
- Alerts already support MITRE display in the UI and PDF reports.
- Existing duplicate open-alert prevention already exists.
- Compatibility with this feature depends on whether `successful_login` events are currently ingested in a consistent, queryable form.

## Event Data Requirements

This feature requires:
- failed login events
- successful login events
- `source_ip`
- event timestamp
- username metadata where available

Minimum event requirements:
- failed login events must remain queryable for distinct-username spraying detection
- successful login events must be ingested in a way that can be queried by `source_ip` and time

Compatibility phase:
- if `successful_login` events are not currently ingested, Phase 1 must first verify and safely add support before enabling this detector

## Detection Logic

Detection rule:
- identify source IPs with password spraying behavior:
  - `5+ distinct usernames`
  - `failed_login`
  - within `15 minutes`
- then detect whether a `successful_login` event occurs from the same `source_ip`
  - during that spraying window
  - or within `15 minutes` after it

Trigger condition:
- same `source_ip`
- password spraying pattern present
- at least one `successful_login` in the allowed correlation window

This rule must not change or weaken the existing `password_spraying_threshold` rule.
Both alerts may coexist when appropriate.

## Alert Output

When the rule triggers, create an alert with:

- `alert_type`: `successful_login_after_spray`
- `severity`: `critical`
- `message`: `Successful login after password spraying detected from <source_ip>`
- `status`: `open`

Duplicate prevention:
- do not create duplicate open alerts for the same:
  - `source_ip`
  - `alert_type`

## MITRE Mapping

Add MITRE ATT&CK mapping for:

- `successful_login_after_spray`
  - `mitre_technique_id`: `T1110.003`
  - `mitre_technique_name`: `Password Spraying`
  - `mitre_tactic`: `Credential Access`

## Backend Requirements

Phase 1 backend work should include:
- verify whether `successful_login` events are currently ingested
- add MITRE mapping for `successful_login_after_spray`
- add correlation logic using the existing event store and alert generation patterns
- reuse existing duplicate open-alert prevention logic
- keep `password_spraying_threshold` behavior unchanged
- keep existing alert API shape unchanged except for additive support of the new alert type

## Testing Plan

Testing should cover:
- a source IP with spraying behavior followed by a `successful_login` creates one `successful_login_after_spray` alert
- a source IP with spraying behavior but no `successful_login` does not create this alert
- a source IP with `successful_login` but without spraying behavior does not create this alert
- duplicate open `successful_login_after_spray` alerts are not created for the same source IP
- existing `password_spraying_threshold` alerts still work unchanged
- MITRE enrichment for `successful_login_after_spray` appears automatically in existing alert views and PDF reports
- compatibility behavior is validated if `successful_login` event support must be added first

## Acceptance Criteria

- The system can verify whether `successful_login` events are available for correlation.
- If `successful_login` events are available, the system creates a critical alert when:
  - a source IP has 5 or more distinct failed login usernames within 15 minutes
  - and a successful login from that same source IP occurs during or within 15 minutes after that activity
- The created alert uses:
  - `alert_type = successful_login_after_spray`
  - `severity = critical`
  - `status = open`
- Duplicate open alerts are prevented for the same `source_ip` and `alert_type`.
- Existing `password_spraying_threshold` detection remains unchanged.
- MITRE mapping for `successful_login_after_spray` resolves to:
  - `T1110.003`
  - `Password Spraying`
  - `Credential Access`
- No frontend change is required in Phase 1 for alert display.

## Non-Goals

This change does not include:
- frontend workflow changes in Phase 1
- changing existing password spraying detection logic
- account lockout
- user attribution confidence scoring
- identity-provider integration
- cross-IP distributed spraying correlation
- automated containment actions
- schema redesign unless compatibility work proves it necessary
