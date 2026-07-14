## ADDED Requirements

### Requirement: Critical alert upgrades a linked lower-severity open incident
When `maybe_create_or_link_incident` links a new alert of severity `critical` to an existing open incident whose severity is not already `critical`, the system SHALL upgrade that incident's `severity` to `CRITICAL` and `priority` to `P1` as part of the same linking operation.

#### Scenario: Existing High/P2 incident upgraded by a Critical alert
- **WHEN** a Critical-severity alert is linked via `maybe_create_or_link_incident` to an existing open incident currently at `severity = "HIGH"` and `priority = "P2"`
- **THEN** the incident's `severity` SHALL become `"CRITICAL"` and `priority` SHALL become `"P1"` after the linking operation completes.

#### Scenario: Already-Critical incident is unaffected
- **WHEN** a Critical-severity alert is linked to an existing open incident already at `severity = "CRITICAL"`
- **THEN** the incident's `severity` and `priority` SHALL remain unchanged, and no redundant update SHALL be issued.

### Requirement: Incidents are never downgraded
No code path SHALL reduce an incident's `severity` or `priority` to a lower value than its current value, regardless of the severity of any alert subsequently linked to it.

#### Scenario: High-severity alert links to an existing Critical incident
- **WHEN** a High-severity alert is linked via `maybe_create_or_link_incident` to an existing open incident at `severity = "CRITICAL"`
- **THEN** the incident's `severity` SHALL remain `"CRITICAL"` and `priority` SHALL remain `"P1"` — the incident SHALL NOT be downgraded to High/P2.

### Requirement: No duplicate incident solely to obtain P1
The system SHALL NOT create a new incident for a source IP that already has an open incident, even when the new alert is Critical and the existing incident is not yet Critical; escalation SHALL always go through the upgrade-on-link path, never through creating a second incident.

#### Scenario: Critical alert with an existing open incident does not create a second incident
- **WHEN** a Critical-severity alert arrives for a source IP that already has an open incident
- **THEN** `maybe_create_or_link_incident` SHALL link the alert to the existing incident and upgrade it per the escalation requirement above, and SHALL NOT insert a new row into `incidents`.

### Requirement: Incident severity escalations are audited
Every incident severity upgrade caused by a Critical alert linkage SHALL be recorded as an audit event, including the incident id, the triggering alert id, the prior severity/priority, and the new severity/priority.

#### Scenario: Escalation produces an audit_log entry
- **WHEN** an incident is upgraded to Critical/P1 by a linked Critical alert
- **THEN** an `audit_log` row SHALL be written with `event_type = "incident_severity_escalated"`, `target_alert_id` set to the triggering alert's id, and `details` containing the incident id, `from_severity`, `to_severity`, `from_priority`, and `to_priority`.

#### Scenario: No audit entry for a no-op escalation
- **WHEN** a Critical alert links to an incident that is already Critical
- **THEN** no `incident_severity_escalated` audit event SHALL be written, since no severity change occurred.
