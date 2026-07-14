## ADDED Requirements

### Requirement: Every playbook Slack notification SHALL pass through notification policy
The system SHALL use notification policy as the single authoritative Slack decision gate for alert-created, incident-created, route-test, and playbook-originated Slack notifications. No playbook path SHALL call the Slack adapter directly without policy evaluation first.

#### Scenario: Playbook Slack step is evaluated by notification policy
- **WHEN** a playbook execution reaches a `notify_slack` step
- **THEN** the executor SHALL call the notification-policy Slack path for that alert or incident, and policy evaluation SHALL decide global enablement, minimum severity, event-kind eligibility, supported source routing, route-specific webhook availability, and compact-vs-detailed formatting before any Slack adapter call occurs.

#### Scenario: Adapter-level real Slack guard remains the final send gate
- **WHEN** notification policy allows a Slack notification and the Slack adapter is invoked
- **THEN** `SOAR_REAL_SLACK_ENABLED` SHALL remain the final adapter-level guard before the HTTP send, rather than being replaced by notification policy.

### Requirement: Equivalent Slack messages SHALL be deduplicated deterministically
The system SHALL suppress duplicate equivalent Slack deliveries for the same alert or incident when they share the same notification purpose, destination route, and delivery stage, even if multiple playbooks match or execute.

#### Scenario: Overlapping honeypot playbooks do not send duplicate equivalent messages
- **WHEN** two playbook paths attempt to send the same investigation-phase Slack notification for one honeypot alert
- **THEN** the first eligible attempt may send and record delivery evidence, and subsequent equivalent attempts SHALL be suppressed using an authoritative deduplication key derived from the alert or incident identity, notification purpose, route key, and delivery stage.

#### Scenario: Distinct lifecycle messages are not collapsed
- **WHEN** an immediate Critical alert notification and a later approved containment outcome notification are generated for the same alert
- **THEN** both SHALL remain independently eligible to send once because they use distinct purpose or delivery-stage identifiers.

### Requirement: Playbook Slack purposes SHALL use a bounded contract
Every Slack notification routed through notification policy SHALL declare or derive one bounded purpose from the approved contract: `immediate_alert`, `incident_created`, `investigation_update`, `containment_outcome`, or `route_test`. Free-form purpose values SHALL NOT be accepted.

#### Scenario: Retained playbook Slack step resolves a bounded purpose
- **WHEN** a retained core playbook Slack step executes
- **THEN** it SHALL be classified as either `investigation_update` or `containment_outcome`, not a free-form string and not an implicit duplicate of `immediate_alert`.

#### Scenario: Immediate alert and incident policy sends keep bounded purposes
- **WHEN** the existing notification-policy path sends for a newly created alert or incident
- **THEN** alert-created sends SHALL use `immediate_alert`, incident-created sends SHALL use `incident_created`, and route tests SHALL use `route_test`.

### Requirement: Slack suppression SHALL NOT fail the playbook or suppress security artifacts
If notification policy suppresses, blocks, or safely skips a Slack notification, the alert, incident, playbook execution, approval flow, containment behavior, audit trail, and UI visibility SHALL remain unchanged except for explicit delivery evidence.

#### Scenario: Policy suppression preserves playbook continuation
- **WHEN** a playbook `notify_slack` step is suppressed because Slack is disabled, the severity is below threshold, the source is unsupported, or the route-specific webhook is missing
- **THEN** the playbook step SHALL record explicit suppression evidence and continue according to existing non-terminal notification-step behavior, without marking the overall playbook failed solely because Slack was suppressed.

#### Scenario: Missing one route-specific webhook does not affect another route
- **WHEN** the pfSense route-specific webhook is missing and a Honeypot notification is evaluated
- **THEN** only pfSense notifications SHALL be suppressed for missing configuration, and Honeypot notifications SHALL continue to use only the Honeypot webhook with no cross-route fallback.

### Requirement: Core playbooks SHALL not keep redundant immediate Slack steps
Each core playbook containing `notify_slack` SHALL either remove a redundant immediate-alert-equivalent Slack step, retain it as a distinct bounded update purpose, or remain unchanged only when it already represents a distinct lifecycle outcome.

#### Scenario: Investigation playbooks do not duplicate immediate alert paging
- **WHEN** a core investigation playbook's `notify_slack` step would render the same investigation-phase Slack intent already sent by the immediate notification-policy alert path
- **THEN** that playbook step SHALL be removed or suppressed by design rather than producing a second equivalent message.

#### Scenario: Containment outcome playbook messaging remains distinct
- **WHEN** `core-v1-spray-success-response` reaches its post-approval Slack step
- **THEN** that retained notification SHALL remain a distinct `containment_outcome` message and SHALL NOT be deduplicated against the initial `immediate_alert` message for the same alert.

### Requirement: Legacy generic Slack webhook behavior SHALL stay outside policy sends
Notification-policy Slack sends SHALL use only the route-specific webhook contract for supported routes and SHALL NOT fall back to `SLACK_WEBHOOK_URL`. The legacy generic webhook path may remain only for explicitly non-policy/manual Slack integration testing that is not part of notification-policy delivery.

#### Scenario: Policy send does not use generic webhook fallback
- **WHEN** notification policy evaluates an eligible pfSense, Honeypot, or critical cross-source Slack notification
- **THEN** delivery SHALL use only that route's approved webhook selection behavior, and a missing route-specific webhook SHALL suppress only that route with clear operational evidence instead of falling back to `SLACK_WEBHOOK_URL`.
