## ADDED Requirements

### Requirement: Critical alerts from bank_app, nginx, and correlation sources are routed for notification
The notification-policy source-routing logic SHALL route Critical-severity alerts whose source is not pfSense or Honeypot (including `bank_app`, `nginx`, and correlation-derived sources such as `web_to_app_attack_pattern`, `spray_then_success_pattern`, and `correlated_activity`) to a single new `critical_cross_source` route, rather than leaving them unrouted or routing them through the pfSense or Honeypot webhook destinations.

#### Scenario: Critical bank_app alert is routed
- **WHEN** `evaluate_notification_policy` evaluates a Critical-severity alert with `source = "bank_app"`, `source_type = "custom"`
- **THEN** it SHALL resolve `route_key = "critical_cross_source"` and `should_notify = True` when Slack is enabled and the alert meets the configured minimum severity, using the `critical_cross_source_destination` configured value as the destination — not the pfSense or Honeypot destination.

#### Scenario: Critical correlation alert is routed
- **WHEN** `evaluate_notification_policy` evaluates a Critical-severity `web_to_app_attack_pattern`-family correlation alert whose `source`/`source_type` do not match pfSense or Honeypot
- **THEN** it SHALL resolve `route_key = "critical_cross_source"` under the same conditions as the scenario above.

#### Scenario: Non-Critical alerts from unmapped sources remain unrouted
- **WHEN** `evaluate_notification_policy` evaluates a non-Critical alert (Low, Medium, or High) whose source is not pfSense or Honeypot
- **THEN** it SHALL resolve `route_key = None` and `should_notify = False` with reason `"source_not_routed"`, unchanged from current behavior — the new route applies only to Critical severity.

#### Scenario: pfSense and Honeypot routing is unaffected
- **WHEN** `evaluate_notification_policy` evaluates any alert whose source is pfSense or Honeypot
- **THEN** it SHALL continue to resolve the existing `pfsense` or `honeypot` route key and destination, regardless of severity — the new Critical cross-source route SHALL NOT intercept these sources.

### Requirement: Immediate Critical notification occurs before any approval gate
For every Critical-severity alert, the notification-policy Slack send (or its recorded suppression) SHALL be attempted synchronously within the ingest request that created the alert, before any playbook `require_approval` step for that alert can be reached by the asynchronous playbook worker.

#### Scenario: Notification attempt precedes approval step execution
- **WHEN** a Critical-severity alert is created by any ingest route
- **THEN** `notify_for_alert` SHALL be invoked for that alert before the ingest request returns its HTTP response, and no playbook `require_approval` step for that alert's triggered playbook execution SHALL have already resolved before that notification attempt is recorded.

### Requirement: Slack failure does not block alert, incident, or containment workflow
A failed, timed-out, or blocked Slack delivery attempt (via either the notification-policy path or a playbook `notify_slack` step) SHALL NOT prevent alert creation, incident creation/linking/escalation, playbook execution, or approval-gated containment from proceeding.

#### Scenario: Slack delivery failure does not roll back the ingest transaction
- **WHEN** the Slack adapter returns a failure or timeout while `notify_for_alert` is processing a Critical alert
- **THEN** the alert row, any incident linkage/escalation, and the playbook pending execution SHALL remain committed, and the failure SHALL be recorded as a `notification_delivery_attempts` row with a `failed` or `timeout` status without raising an exception that aborts the ingest request.

#### Scenario: Missing critical_cross_source destination fails safe
- **WHEN** the `critical_cross_source_destination` policy value is unset or blank and a Critical alert from an unmapped source is evaluated
- **THEN** `evaluate_notification_policy` SHALL return `should_notify = False` with reason `"source_not_routed"`, and processing SHALL continue without error — no alert, incident, or playbook step SHALL be blocked by the missing destination.

### Requirement: No duplicate Critical Slack delivery per alert
For a single Critical alert, the system SHALL send at most one notification-policy Slack message and, where a Critical containment playbook also sends a Slack message on a distinct outcome step, that message SHALL be textually and semantically distinct from the immediate notification-policy message — the same message text SHALL NOT be sent twice for the same alert.

#### Scenario: Ingest routes call the alert-notification path exactly once per alert
- **WHEN** any ingest route (`/ingest`, `/ingest/honeypot`, or any other event-ingest endpoint) processes a batch of newly created alerts
- **THEN** `notify_for_alert` SHALL be invoked exactly once per alert id across the entire request, not once directly and again inside playbook-execution creation.

#### Scenario: Legacy playbook outcome notification differs from the immediate alert page
- **WHEN** `core-v1-spray-success-response`'s trailing `notify_slack` step executes after an approved `block_ip` step
- **THEN** its rendered Slack message text SHALL communicate the containment outcome (e.g., that the IP was blocked following approval) and SHALL NOT be identical to the immediate notification-policy alert-creation message for the same alert.
