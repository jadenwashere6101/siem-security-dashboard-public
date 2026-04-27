# Password Spraying Detection Spec

## Feature Overview

This change adds password spraying detection to the SIEM by identifying failed login activity from a single source IP against multiple distinct usernames in a short time window.

The scope is intentionally phased:
- confirm event data supports username-based detection
- add backend detection logic for password spraying
- add MITRE ATT&CK mapping for the new alert type
- reuse existing alert creation and duplicate-prevention patterns

This complements the existing failed-login threshold rule by detecting broader credential access behavior rather than repeated failures against a single account.

## Current State

- Existing `failed_login_threshold` detection catches repeated failed logins from the same source IP.
- Current MITRE mapping supports `failed_login_threshold` as:
  - `T1110`
  - `Brute Force`
  - `Credential Access`
- Backend already supports alert creation and duplicate alert prevention.
- Dashboard already displays alerts and MITRE context.
- PDF reports already include MITRE context.
- Full implementation depends on whether failed login events currently include username metadata consistently enough for distinct-user counting.

## Event Data Requirements

Password spraying detection requires failed login event data to include:
- `event_type` or equivalent event classification identifying failed logins
- `source_ip`
- `username`
- event timestamp

Minimum requirement:
- failed login events must include username metadata in a consistent, queryable form

Phase requirement:
- first verify whether username is currently stored consistently in failed login events
- if not, add a safe compatibility phase to capture username before enabling the full rule

## Detection Logic

Detection rule:
- inspect failed login events only
- group by `source_ip`
- within a 15-minute window
- count distinct usernames targeted by that source IP
- if count is 5 or more, generate a password spraying alert

Rule details:
- time window: `15 minutes`
- threshold: `5 distinct usernames`
- grouping key: `source_ip`
- username metric: `COUNT(DISTINCT username)`

This rule must not replace or weaken the existing `failed_login_threshold` rule.
Both rules may coexist and detect different attack patterns.

## Alert Output

When the rule triggers, create an alert with:

- `alert_type`: `password_spraying_threshold`
- `severity`: `high`
- `message`: `Password spraying suspected from <source_ip>: failed logins across <count> usernames`
- `status`: `open`

Duplicate prevention:
- do not create duplicate open alerts for the same:
  - `source_ip`
  - `alert_type`

## MITRE Mapping

Add MITRE ATT&CK mapping for:

- `password_spraying_threshold`
  - `mitre_technique_id`: `T1110.003`
  - `mitre_technique_name`: `Password Spraying`
  - `mitre_tactic`: `Credential Access`

## Backend Requirements

Phase 1 backend work should include:
- verify failed login event records contain username metadata
- add MITRE mapping for `password_spraying_threshold`
- add detection logic using existing alert generation patterns
- reuse existing duplicate open-alert prevention logic
- keep existing `failed_login_threshold` behavior unchanged
- keep existing alert API shape unchanged except for additive new alert type support

## Database/Event Compatibility Requirements

- No schema change is required if failed login events already store username in a usable way.
- If username is not currently stored consistently, implementation must introduce a safe compatibility phase before full rule enablement.
- Any event-data improvement should be additive and should not break existing event ingestion or dashboard behavior.
- Existing alerts without this new rule must remain unaffected.

## Testing Plan

Testing should cover:
- failed logins from one source IP against 5 or more distinct usernames within 15 minutes create one alert
- failed logins from one source IP against fewer than 5 distinct usernames do not create this alert
- repeated failures against one username still remain covered by existing `failed_login_threshold`
- duplicate open `password_spraying_threshold` alerts are not created for the same source IP
- MITRE enrichment for `password_spraying_threshold` appears in alert APIs and downstream views where MITRE context is already supported
- behavior is validated both when username data is present and when compatibility checks fail safely

## Acceptance Criteria

- The system can verify whether failed login events include usable username metadata.
- If username metadata is available, failed login events from the same source IP against 5 or more distinct usernames within 15 minutes create an alert.
- The created alert uses:
  - `alert_type = password_spraying_threshold`
  - `severity = high`
  - `status = open`
- Duplicate open alerts are prevented for the same `source_ip` and `alert_type`.
- Existing `failed_login_threshold` detection remains unchanged.
- MITRE mapping for `password_spraying_threshold` resolves to:
  - `T1110.003`
  - `Password Spraying`
  - `Credential Access`
- Existing frontend behavior does not require change in Phase 1 beyond additive display of the new alert type where current alert rendering already applies.

## Non-Goals

This change does not include:
- changing frontend workflows in Phase 1
- changing existing failed login threshold logic
- account lockout
- adaptive authentication
- identity-provider integration
- geolocation-based password spraying correlation
- cross-IP distributed password spraying detection
- automated response actions for this rule
